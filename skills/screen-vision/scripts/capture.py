#!/usr/bin/env python3
"""capture.py — screenshot the screen and read its UI elements (default READ-ONLY).

Pipeline: L0 DPI-aware (auto) -> L1 capture (mss/GDI) -> L2a UIA tree -> L2b OCR
(only where UIA has no text) -> L3 IoU fusion (UIA wins) -> L4 dual output
(Set-of-Mark PNG + element JSON). All coordinates are physical pixels.

Usage:
  python capture.py [--target all|monitor:<i>|window:"<title>"|hwnd:<n>|region:l,t,w,h]
                    [--layers uia,ocr,vision] [--ocr-engine auto|winocr|rapidocr]
                    [--max-depth 50] [--clickable-only] [--out-dir DIR]
                    [--annotate true|false] [--summary-n 30] [--json-stdout]

Degrades gracefully: missing libs become warnings, never crashes. stdout is a
compact JSON summary + artifact paths; the full element list is written to disk.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402
import pure_ops as P  # noqa: E402  (pure-stdlib helpers: black-retry, region-OCR)
from artifact_store import artifact_directory

CLICKABLE_TYPES = {
    "button", "menuitem", "checkbox", "radiobutton", "tabitem", "listitem",
    "hyperlink", "link", "splitbutton", "combobox", "edit", "input", "slider",
    "treeitem", "menu", "scrollbar", "togglebutton",
}


# --------------------------------------------------------------------------- #
# L2a, UIA tree (Windows). Window-scoped, depth-limited, pruned.             #
# --------------------------------------------------------------------------- #
def _uia_type(control_type_name):
    t = (control_type_name or "").replace("Control", "").lower()
    return t or "unknown"


def collect_uia(target, max_depth, region, warnings):
    """Return list of element dicts from the UI Automation tree, or [] if unavailable."""
    if not C.IS_WINDOWS:
        warnings.append("uia: skipped (non-Windows; accessibility layer not implemented)")
        return []
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        warnings.append("uia: 'uiautomation' not installed -> structural layer skipped "
                        "(pip install uiautomation)")
        return []

    verify_target(target)
    roots = []
    try:
        if target.get("kind") == "window" and target.get("hwnd"):
            try:
                roots = [auto.ControlFromHandle(target["hwnd"])]
            except Exception:
                roots = []
        if not roots and target.get("kind") in ("window", "hwnd") and target.get("hwnd"):
            roots = [auto.ControlFromHandle(target["hwnd"])]
        if not roots and target.get("kind") == "window":
            warnings.append("uia: requested window unavailable; no desktop fallback")
            return []
        if not roots:
            # whole desktop: enumerate top-level windows (NEVER a deep walk from root)
            desktop = auto.GetRootControl()
            roots = []
            child = desktop.GetFirstChildControl()
            guard = 0
            while child and guard < 200:
                try:
                    if child.ControlTypeName in ("WindowControl", "PaneControl") and child.Name:
                        roots.append(child)
                except Exception:
                    pass
                child = child.GetNextSiblingControl()
                guard += 1
            if not roots:
                roots = [desktop]
    except Exception as e:
        warnings.append("uia: root resolution failed (%s)" % e)
        return []

    rl, rt, rr, rb = region  # clip rect (physical px)
    out = []
    deadline = time.time() + 12.0  # hard time budget; UIA can be pathologically slow

    def patterns_of(ctrl):
        pats = []
        for nm, getter in (("Invoke", "GetInvokePattern"), ("Value", "GetValuePattern"),
                           ("Toggle", "GetTogglePattern"), ("Selection", "GetSelectionItemPattern"),
                           ("Expand", "GetExpandCollapsePattern")):
            try:
                if getattr(ctrl, getter)() is not None:
                    pats.append(nm)
            except Exception:
                pass
        return pats

    def walk(ctrl, depth, root):
        if time.time() > deadline or depth > max_depth:
            return
        try:
            r = ctrl.BoundingRectangle
            l, t, rr2, bb2 = r.left, r.top, r.right, r.bottom
        except Exception:
            l = t = rr2 = bb2 = 0
        w, h = rr2 - l, bb2 - t
        onscreen_overlap = not (rr2 <= rl or l >= rr or bb2 <= rt or t >= rb)
        if w > 0 and h > 0 and onscreen_overlap:
            try:
                off = bool(ctrl.IsOffscreen)
            except Exception:
                off = False
            try:
                en = bool(ctrl.IsEnabled)
            except Exception:
                en = True
            ctype = _uia_type(getattr(ctrl, "ControlTypeName", ""))
            pats = patterns_of(ctrl)
            clickable = bool(pats) or ctype in CLICKABLE_TYPES
            name = ""
            try:
                name = ctrl.Name or ""
            except Exception:
                pass
            aid = ""
            try:
                aid = ctrl.AutomationId or ""
            except Exception:
                pass
            cls = ""
            try:
                cls = ctrl.ClassName or ""
            except Exception:
                pass
            # keep only meaningful nodes: has a name/id OR is interactive
            if name or aid or clickable:
                try:
                    identity = C.control_identity(ctrl, root)
                except Exception:
                    identity = None
                if (target.get("kind") == "window" and identity is not None
                        and identity["window"] != target["window_identity"]):
                    raise TargetError("UIA window changed after capture; resolve it again", "target_not_found")
                out.append({
                    "type": ctype, "label": name, "name": name,
                    "automation_id": aid, "class_name": cls, "source": "uia",
                    "rect": [l, t, rr2, bb2], "bbox": [l, t, w, h],
                    "center": [(l + rr2) // 2, (t + bb2) // 2],
                    "enabled": en, "offscreen": off, "clickable": clickable,
                    "patterns": pats, "confidence": 1.0, "identity": identity,
                })
        # descend (prune offscreen subtrees)
        try:
            kid = ctrl.GetFirstChildControl()
        except Exception:
            kid = None
        guard = 0
        while kid and guard < 400 and time.time() <= deadline:
            walk(kid, depth + 1, root)
            try:
                kid = kid.GetNextSiblingControl()
            except Exception:
                break
            guard += 1

    for root in roots:
        try:
            walk(root, 0, root)
        except TargetError:
            raise
        except Exception as e:
            warnings.append("uia: walk error (%s)" % e)
    verify_target(target)
    if time.time() > deadline:
        warnings.append("uia: hit 12s time budget; tree may be partial (narrow --target)")
    return out


# --------------------------------------------------------------------------- #
# L2b, OCR (only fills text the UIA tree is missing).                         #
# --------------------------------------------------------------------------- #
def collect_ocr(png_path, engine, origin, region, uia_boxes, warnings):
    ox, oy = origin
    rl, rt, rr, rb = region
    results = []

    def add(text, poly_or_box, conf):
        text = (text or "").strip()
        if not text:
            return
        xs = poly_or_box[0::2] if len(poly_or_box) > 4 else [poly_or_box[0], poly_or_box[2]]
        ys = poly_or_box[1::2] if len(poly_or_box) > 4 else [poly_or_box[1], poly_or_box[3]]
        l = int(min(xs)) + ox
        t = int(min(ys)) + oy
        r = int(max(xs)) + ox
        b = int(max(ys)) + oy
        results.append({
            "type": "text", "label": text, "name": text, "automation_id": "",
            "class_name": "", "source": "ocr", "rect": [l, t, r, b],
            "bbox": [l, t, r - l, b - t], "center": [(l + r) // 2, (t + b) // 2],
            "enabled": True, "offscreen": False, "clickable": False,
            "patterns": [], "confidence": round(float(conf), 3),
        })

    eng = engine
    if eng == "auto":
        eng = "winocr" if (C.IS_WINDOWS and C._can_import("winocr")) else "rapidocr"

    if eng == "rapidocr":
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            ocr = RapidOCR()
            res, _ = ocr(png_path)
            for box, txt, score in (res or []):
                poly = [c for pt in box for c in pt]
                add(txt, poly, score)
        except Exception as e:
            warnings.append("ocr(rapidocr): unavailable (%s); pip install rapidocr-onnxruntime" % e)
    elif eng == "winocr":
        try:
            import winocr  # type: ignore
            from PIL import Image  # type: ignore
            img = Image.open(png_path)
            r = winocr.recognize_pil_sync(img)
            for line in r.get("lines", []):
                for w in line.get("words", []):
                    br = w.get("bounding_rect", {})
                    box = [br.get("x", 0), br.get("y", 0),
                           br.get("x", 0) + br.get("width", 0),
                           br.get("y", 0) + br.get("height", 0)]
                    add(w.get("text", ""), box, 0.9)
        except Exception as e:
            warnings.append("ocr(winocr): unavailable (%s); needs Windows OCR lang pack + Pillow" % e)
    else:
        warnings.append("ocr: unknown engine '%s'" % eng)

    # only keep OCR text NOT already covered by a UIA element (fusion preview)
    kept = []
    for o in results:
        if all(C.iou(o["rect"], u) <= 0.10 for u in uia_boxes):
            kept.append(o)
    return kept


# --------------------------------------------------------------------------- #
# L4, Set-of-Mark annotation (best-effort; needs Pillow). No-op otherwise.   #
# --------------------------------------------------------------------------- #
def annotate(png_path, out_path, elements, origin, warnings):
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        warnings.append("annotate: Pillow not installed -> annotated PNG skipped "
                        "(pip install pillow). JSON coordinates are still exact.")
        return None
    ox, oy = origin
    try:
        img = Image.open(png_path).convert("RGB")
        d = ImageDraw.Draw(img)
        for e in elements:
            l, t, r, b = e["rect"]
            x0, y0, x1, y1 = l - ox, t - oy, r - ox, b - oy
            color = (255, 60, 60) if e["clickable"] else (60, 160, 255)
            d.rectangle([x0, y0, x1, y1], outline=color, width=2)
            tag = str(e["id"])
            tx, ty = max(0, x0), max(0, y0 - 12)
            d.rectangle([tx, ty, tx + 8 * len(tag) + 4, ty + 12], fill=color)
            d.text((tx + 2, ty), tag, fill=(255, 255, 255))
        img.save(out_path)
        return out_path
    except Exception as e:
        warnings.append("annotate: failed (%s)" % e)
        return None


# --------------------------------------------------------------------------- #
# Target resolution                                                          #
# --------------------------------------------------------------------------- #
class TargetError(ValueError):
    def __init__(self, detail, code="invalid_target"):
        super().__init__(detail)
        self.code = code


def resolve_target(spec, monitors, warnings):
    spec = spec.strip()
    vx, vy, vw, vh = C.virtual_screen_rect()
    if spec == "all":
        return {"kind": "all", "rect": [vx, vy, vx + vw, vy + vh],
                "origin": [vx, vy], "monitor": monitors[0] if monitors else None}
    if spec.startswith("monitor:"):
        try:
            idx = int(spec.split(":", 1)[1])
        except ValueError as exc:
            raise TargetError("monitor requires an integer index") from exc
        monitor = next((m for m in monitors if m["index"] == idx), None)
        if monitor is None:
            raise TargetError("requested monitor does not exist", "target_not_found")
        return {"kind": "monitor", "rect": monitor["rect"], "origin": monitor["origin"], "monitor": monitor}
    if spec.startswith("region:"):
        try:
            l, t, w, h = map(int, spec.split(":", 1)[1].split(","))
        except ValueError as exc:
            raise TargetError("region requires l,t,w,h as four integers") from exc
        if w <= 0 or h <= 0 or not (vx <= l < l+w <= vx+vw and vy <= t < t+h <= vy+vh):
            raise TargetError("region must have positive dimensions and stay inside the virtual desktop")
        return {"kind": "region", "rect": [l, t, l+w, t+h], "origin": [l, t], "monitor": None}
    if spec.startswith("hwnd:"):
        try:
            hwnd = int(spec.split(":", 1)[1])
        except ValueError as exc:
            raise TargetError("hwnd requires a positive integer") from exc
        if hwnd <= 0:
            raise TargetError("hwnd requires a positive integer")
    elif spec.startswith("window:"):
        title = spec.split(":", 1)[1].strip().strip('"').strip("'")
        if not title:
            raise TargetError("window title cannot be empty")
        found = C.find_window_by_title(title)
        if not found:
            raise TargetError("window title is absent or ambiguous; use an explicit HWND", "target_not_found")
        hwnd = found[0]
    else:
        raise TargetError("unknown target; use all, monitor:, window:, hwnd:, or region:")
    identity = C.window_identity(hwnd)
    if identity is None:
        raise TargetError("window is absent, minimized, or its process cannot be verified", "target_not_found")
    rect = identity["rect"]
    return {"kind": "window", "hwnd": hwnd, "rect": rect, "origin": rect[:2],
            "monitor": None, "window_identity": identity}


def verify_target(target):
    """Keep the originally resolved window binding through capture and publication."""
    if target["kind"] == "window" and C.window_identity(target["hwnd"]) != target["window_identity"]:
        raise TargetError("window changed during capture; resolve it again", "target_not_found")


def grab_target(target):
    verify_target(target)
    l, t, r, b = target["rect"]
    result = C.capture_region(l, t, r-l, b-t)
    verify_target(target)
    return result


def main():
    ap = argparse.ArgumentParser(description="Screenshot + read on-screen UI elements (read-only).")
    ap.add_argument("--target", default="all")
    ap.add_argument("--allow-full-screen-fallback", action="store_true",
                    help="Explicitly allow invalid narrow targets to capture the whole desktop.")
    ap.add_argument("--layers", default="uia,ocr")
    ap.add_argument("--ocr-engine", default="auto", choices=["auto", "winocr", "rapidocr"])
    ap.add_argument("--max-depth", type=int, default=50)
    ap.add_argument("--clickable-only", action="store_true")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--annotate", default="true", choices=["true", "false"])
    ap.add_argument("--summary-n", type=int, default=30)
    ap.add_argument("--json-stdout", action="store_true")
    a = ap.parse_args()

    warnings = []
    try:
        C.require_physical_coordinates()
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": "dpi_awareness_unverified", "detail": str(exc)}))
        return 3
    layers = [x.strip() for x in a.layers.split(",") if x.strip()]
    try:
        monitors = C.enum_monitors()
        C.validate_monitor_geometry(monitors)
    except (RuntimeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "monitor_geometry_unavailable", "detail": str(exc)}))
        return 3
    fallback_used = False
    try:
        target = resolve_target(a.target, monitors, warnings)
    except (RuntimeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "monitor_geometry_unavailable", "detail": str(exc)}))
        return 3
    except TargetError as exc:
        if not a.allow_full_screen_fallback:
            print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc),
                              "requested_target": a.target,
                              "next_step": "Correct the target or explicitly request full-screen capture."}))
            return 2
        warnings.append("explicit full-screen fallback: " + str(exc))
        target = resolve_target("all", monitors, warnings)
        fallback_used = True
    captured_at = time.time()
    capture_metadata = {"schema_version": 2, "captured_at": captured_at,
                        "requested_target": a.target, "resolved_target": target,
                        "fallback_used": fallback_used}

    if not C.has_interactive_desktop():
        print(json.dumps({"ok": False, "error": "no_interactive_desktop",
                          "detail": getattr(C.has_interactive_desktop, 'reason', None)
                          or "Interactive desktop access is unavailable."}))
        return 3

    try:
        out_dir = str(artifact_directory(a.out_dir))
        os.makedirs(out_dir, exist_ok=True)
    except (RuntimeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "artifact_store_unavailable", "detail": str(exc),
                          "next_step": "Configure and verify the private companion before capture."}))
        return 2

    if C.is_wayland():
        warnings.append("platform: Wayland blocks silent screen capture; results may be empty.")

    # L1 capture
    rect = target["rect"]
    l, t, r, b = rect
    origin = [l, t]
    # ARCH 1.3: black-screen auto-retry, re-grab once if the frame comes back near-black.
    try:
        _cap = P.capture_with_retry(lambda: grab_target(target), max_attempts=2, black_threshold=0.98)
    except (TargetError, RuntimeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": getattr(exc, "code", "capture_failed"),
                          "detail": str(exc), "capture": capture_metadata}))
        return 3
    rgb, w, h, backend = _cap["rgb"], _cap["w"], _cap["h"], _cap["backend"]
    if _cap["attempts"] > 1:
        warnings.append("capture: re-grabbed %d extra time(s) after a near-black frame "
                        "(ARCH 1.3 black-screen auto-retry)" % (_cap["attempts"] - 1))
    screen_png = os.path.join(out_dir, "screen.png")
    C.write_png(screen_png, rgb, w, h)
    blk = C.blackness(rgb, w, h)
    if blk > 0.98:
        warnings.append("capture: image is ~%.0f%% black (occluded/minimized/protected window?). "
                        "Bring the window to the foreground or use --target window:..." % (blk * 100))

    # L2a UIA
    elements = []
    if "uia" in layers:
        try:
            elements += collect_uia(target, a.max_depth, rect, warnings)
        except TargetError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc),
                              "capture": capture_metadata}))
            return 3
    uia_boxes = [e["rect"] for e in elements]

    # L2b OCR (fills only UIA-missing text). ARCH 1.5: never blind full-screen OCR ,
    # skip entirely when UIA already covers the captured region.
    if "ocr" in layers:
        ocr_regions = P.compute_ocr_regions(rect, uia_boxes)
        if not ocr_regions:
            warnings.append("ocr: skipped — UIA covers the whole captured region "
                            "(ARCH 1.5: no blind full-screen OCR)")
        else:
            elements += collect_ocr(screen_png, a.ocr_engine, origin, rect, uia_boxes, warnings)

    # L2c vision (optional, default OFF, not bundled; AGPL backend is user-supplied)
    if "vision" in layers:
        warnings.append("vision: optional OmniParser/grounding backend not bundled "
                        "(AGPL weights are user-supplied). See reference/backends.md.")

    # filter + de-dup identical rects + assign ids
    if a.clickable_only:
        elements = [e for e in elements if e.get("clickable")]
    # stamp monitor/scale/origin metadata
    scale = (target.get("monitor") or {}).get("scale", monitors[0]["scale"] if monitors else 1.0)
    mon_idx = (target.get("monitor") or {}).get("index", 0)
    for e in elements:
        e["monitor"] = mon_idx
        e["scale"] = scale
        e["origin"] = origin
        e["captured_at"] = captured_at
        e["capture_rect"] = rect
        e.setdefault("identity", None)
    # order by area desc (big, salient first), then assign stable ids
    elements.sort(key=lambda e: -(e["bbox"][2] * e["bbox"][3]))
    for i, e in enumerate(elements):
        e["id"] = i
    # canonical field order
    ordered = [{k: e[k] for k in ("id", "type", "label", "name", "automation_id",
                                  "class_name", "source", "bbox", "rect", "center",
                                  "enabled", "offscreen", "clickable", "patterns",
                                  "confidence", "monitor", "scale", "origin",
                                  "captured_at", "capture_rect", "identity")}
               for e in elements]

    try:
        verify_target(target)
    except TargetError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc),
                          "capture": capture_metadata}))
        return 3
    elements_json = os.path.join(out_dir, "elements.json")
    with open(elements_json, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)

    annotated = None
    if a.annotate == "true" and ordered:
        annotated = annotate(screen_png, os.path.join(out_dir, "annotated.png"),
                             ordered, origin, warnings)

    counts = {
        "total": len(ordered),
        "uia": sum(1 for e in ordered if e["source"] == "uia"),
        "ocr": sum(1 for e in ordered if e["source"] == "ocr"),
        "vision": sum(1 for e in ordered if e["source"] == "vision"),
        "clickable": sum(1 for e in ordered if e["clickable"]),
    }
    summary = ordered[:max(0, a.summary_n)]
    result = {
        "ok": True,
        "capture": capture_metadata,
        "backend": backend,
        "dpi_awareness": C._DPI_STATE["level"],
        "screenshot": screen_png,
        "annotated": annotated,
        "elements_json": elements_json,
        "monitor": {"index": mon_idx, "origin": origin, "scale": scale,
                    "physical_size": [w, h]},
        "counts": counts,
        "warnings": warnings,
        "elements_summary": summary,
    }
    result["capture_manifest"] = os.path.join(out_dir, "capture.json")
    with open(result["capture_manifest"], "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    if a.json_stdout:
        result["elements"] = ordered
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
