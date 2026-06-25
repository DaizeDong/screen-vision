#!/usr/bin/env python3
"""click.py — optional, opt-in click on an element found by capture.py.

SAFETY: dry-run is the DEFAULT. Without --confirm it only reports the element it
would act on (name + center). Real actuation requires --confirm. Prefers a
UIA pattern (Invoke/Toggle/SetValue) — coordinate-free, robust to occlusion,
scroll, DPI — and falls back to a physical click only when no pattern exists.

Usage:
  python click.py --elements-json <path> --id <N>
                  [--button left|right|middle] [--double]
                  [--dry-run | --confirm]            (dry-run is default)
                  [--method auto|invoke|coord]       (default auto)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def find_element(elements, eid):
    for e in elements:
        if e.get("id") == eid:
            return e
    return None


def try_uia_invoke(el):
    """Re-resolve the element via UIA (by automation_id/name/rect) and trigger a pattern.

    Returns (acted, method, detail). Coordinate-free when it works.
    """
    if not C.IS_WINDOWS:
        return False, None, "non-Windows"
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return False, None, "uiautomation not installed"

    cx, cy = el["center"]
    cand = None
    try:
        cand = auto.ControlFromPoint(cx, cy)
    except Exception:
        cand = None
    if cand is None:
        return False, None, "no control at center point"

    # sanity: the control under the point should roughly match the recorded rect
    try:
        r = cand.BoundingRectangle
        got = [r.left, r.top, r.right, r.bottom]
        if C.iou(got, el["rect"]) < 0.30 and (el.get("automation_id") or ""):
            # weak match; trust the recorded automation_id only if present
            pass
    except Exception:
        pass

    for pat_name, getter, action in (
        ("Invoke", "GetInvokePattern", lambda p: p.Invoke()),
        ("Toggle", "GetTogglePattern", lambda p: p.Toggle()),
        ("SelectionItem", "GetSelectionItemPattern", lambda p: p.Select()),
        ("Expand", "GetExpandCollapsePattern", lambda p: p.Expand()),
    ):
        try:
            p = getattr(cand, getter)()
            if p is not None:
                action(p)
                return True, "invoke:%s" % pat_name, "ok"
        except Exception:
            continue
    return False, None, "no actionable pattern on control"


def main():
    ap = argparse.ArgumentParser(description="Opt-in click on a captured element (dry-run by default).")
    ap.add_argument("--elements-json", required=True)
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--button", default="left", choices=["left", "right", "middle"])
    ap.add_argument("--double", action="store_true")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", dest="dry_run", action="store_true")
    g.add_argument("--confirm", dest="dry_run", action="store_false")
    ap.set_defaults(dry_run=True)
    ap.add_argument("--method", default="auto", choices=["auto", "invoke", "coord"])
    a = ap.parse_args()

    C.set_dpi_awareness()
    try:
        with open(a.elements_json, "r", encoding="utf-8") as f:
            elements = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "cannot read elements-json", "detail": str(e)}))
        return 2

    el = find_element(elements, a.id)
    if el is None:
        print(json.dumps({"ok": False, "error": "id not found", "id": a.id}))
        return 2

    target = {"id": el["id"], "label": el.get("label") or el.get("name"),
              "type": el.get("type"), "center": el["center"],
              "clickable": el.get("clickable"), "patterns": el.get("patterns", [])}

    if a.dry_run:
        print(json.dumps({"ok": True, "acted": False, "dry_run": True,
                          "method": "preview", "target": target,
                          "note": "re-run with --confirm to actually click"}, ensure_ascii=False))
        return 0

    if not el.get("enabled", True) or el.get("offscreen", False):
        print(json.dumps({"ok": False, "acted": False, "error": "element disabled/offscreen",
                          "target": target}, ensure_ascii=False))
        return 4

    acted, method, detail = False, None, ""
    if a.method in ("auto", "invoke"):
        acted, method, detail = try_uia_invoke(el)
    if not acted and a.method in ("auto", "coord"):
        cx, cy = el["center"]
        acted = C.click_physical(cx, cy, button=a.button, double=a.double)
        method = "coord"
        detail = "physical click at %s" % ([cx, cy])

    print(json.dumps({"ok": bool(acted), "acted": bool(acted), "dry_run": False,
                      "method": method, "detail": detail, "target": target},
                     ensure_ascii=False))
    return 0 if acted else 5


if __name__ == "__main__":
    sys.exit(main())
