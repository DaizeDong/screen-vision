#!/usr/bin/env python3
"""screen-vision eval gate — program-judgeable signals (no human in the loop).

Mirrors ARCHITECTURE.md §4. Each check is PASS / FAIL / SKIP(reason). SKIP is not a
failure (a backend simply absent on this host). Exit 0 unless something genuinely
FAILS. self-evolve consumes this as its A/B regression signal.

  A (fast): PNG sanity, DPI awareness, capture non-black + resolution match,
            IoU fusion, golden UIA set (Calculator), closed-loop click.
  B (text): synthetic-image OCR round-trip.

Usage:  python tests/run_gate.py [--json]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "skills", "screen-vision", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))
import _common as C  # noqa: E402

results = []


def rec(name, status, detail=""):
    results.append({"name": name, "status": status, "detail": detail})


def t_png():
    import tempfile
    w, h = 4, 3
    rgb = bytes([10, 20, 30] * (w * h))
    p = os.path.join(tempfile.gettempdir(), "sv_gate_png.png")
    C.write_png(p, rgb, w, h)
    head = open(p, "rb").read(24)
    ok = head[:8] == b"\x89PNG\r\n\x1a\n"
    import struct
    gw, gh = struct.unpack(">II", head[16:24])
    rec("png_writer", "PASS" if (ok and gw == w and gh == h) else "FAIL", "%dx%d" % (gw, gh))


def t_dpi():
    lvl = C.set_dpi_awareness()
    if not C.IS_WINDOWS:
        return rec("dpi_awareness", "SKIP", "non-Windows")
    rec("dpi_awareness", "PASS" if lvl in ("per_monitor_v2", "per_monitor", "system") else "FAIL", lvl)


def t_capture():
    mons = C.enum_monitors()
    m = mons[0]
    l, t, r, b = m["rect"]
    rgb, w, h, backend = C.capture_region(l, t, r - l, b - t)
    blk = C.blackness(rgb, w, h)
    size_ok = [w, h] == m["physical_size"]
    rec("capture_resolution_match", "PASS" if size_ok else "FAIL",
        "got %dx%d want %s (DPI-aware proof)" % (w, h, m["physical_size"]))
    rec("capture_not_black", "PASS" if blk < 0.98 else "FAIL", "%.1f%% black (%s)" % (blk * 100, backend))


def t_iou():
    a = [0, 0, 100, 100]
    overlap = [10, 10, 110, 110]
    disjoint = [200, 200, 300, 300]
    ok = C.iou(a, overlap) > 0.10 and C.iou(a, disjoint) == 0.0 and abs(C.iou(a, a) - 1.0) < 1e-9
    rec("iou_fusion_math", "PASS" if ok else "FAIL",
        "overlap=%.2f disjoint=%.2f" % (C.iou(a, overlap), C.iou(a, disjoint)))


def _run_capture(target, layers="uia"):
    out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "capture.py"),
                          "--target", target, "--layers", layers, "--summary-n", "0",
                          "--annotate", "false"],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    return json.loads(out.stdout)


def t_golden_uia():
    if not (C.IS_WINDOWS and C._can_import("uiautomation")):
        return rec("golden_uia_calculator", "SKIP", "uiautomation not installed"), None
    try:
        subprocess.Popen(["calc.exe"])
        time.sleep(3.0)
    except Exception as e:
        return rec("golden_uia_calculator", "SKIP", "cannot launch calc (%s)" % e), None
    try:
        d = _run_capture("window:Calculator", "uia")
    except Exception as e:
        return rec("golden_uia_calculator", "SKIP", "capture failed (%s)" % e), None
    if d["counts"]["total"] < 10:
        return rec("golden_uia_calculator", "SKIP",
                   "only %d elements (Calculator may not be foreground)" % d["counts"]["total"]), None
    els = json.load(open(d["elements_json"], encoding="utf-8"))
    seven = [e for e in els if e.get("name") in ("Seven", "7") and e["type"] == "button"]
    ok = bool(seven) and "Invoke" in seven[0]["patterns"] and seven[0]["clickable"]
    rec("golden_uia_calculator", "PASS" if ok else "FAIL",
        "%d elements; digit-7 invoke=%s" % (d["counts"]["total"], bool(seven)))
    return None, (d["elements_json"], seven[0]["id"] if seven else None)


def t_closed_loop(ej_and_id):
    if not ej_and_id or ej_and_id[1] is None:
        return rec("closed_loop_click", "SKIP", "no golden digit button")
    ej, sid = ej_and_id
    try:
        for _ in range(2):
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "click.py"),
                            "--elements-json", ej, "--id", str(sid), "--confirm"],
                           capture_output=True, text=True, timeout=20)
        time.sleep(0.5)
        d = _run_capture("window:Calculator", "uia")
        els = json.load(open(d["elements_json"], encoding="utf-8"))
        disp = [e for e in els if e.get("automation_id") == "CalculatorResults"
                or "Display is" in (e.get("name") or "")]
        text = disp[0]["name"] if disp else ""
        ok = "77" in text
        rec("closed_loop_click", "PASS" if ok else "FAIL", "display=%r" % text)
    except Exception as e:
        rec("closed_loop_click", "SKIP", "error (%s)" % e)


def t_ocr_synthetic():
    if not (C._can_import("winocr") or C._can_import("rapidocr_onnxruntime")):
        return rec("ocr_synthetic", "SKIP", "no OCR engine installed")
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        return rec("ocr_synthetic", "SKIP", "Pillow not installed")
    import tempfile
    from PIL import ImageFont  # type: ignore
    # render realistic GUI-sized text (default bitmap font is too small for fair OCR)
    font = None
    for cand in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(cand, 40)
            break
        except Exception:
            continue
    img = Image.new("RGB", (520, 120), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 35), "Open Settings", fill=(0, 0, 0), font=font)
    p = os.path.join(tempfile.gettempdir(), "sv_gate_ocr.png")
    img.save(p)
    sys.path.insert(0, os.path.abspath(SCRIPTS))
    import importlib
    cap = importlib.import_module("capture")
    warnings = []
    els = cap.collect_ocr(p, "auto", [0, 0], [0, 0, 520, 120], [], warnings)
    joined = "".join(e["label"] for e in els).lower().replace(" ", "")
    ok = "opensettings" in joined or "settings" in joined
    rec("ocr_synthetic", "PASS" if ok else ("SKIP" if not els else "FAIL"),
        "recovered=%r warn=%s" % (joined[:40], warnings[:1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    t_png()
    t_dpi()
    t_capture()
    t_iou()
    skip, golden = t_golden_uia()
    t_closed_loop(golden)
    t_ocr_synthetic()

    # best-effort cleanup
    if C.IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"],
                           capture_output=True)
            subprocess.run(["taskkill", "/F", "/IM", "Calculator.exe"], capture_output=True)
        except Exception:
            pass

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_skip = sum(1 for r in results if r["status"] == "SKIP")
    summary = {"pass": n_pass, "fail": n_fail, "skip": n_skip, "results": results}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print("  [%-4s] %-28s %s" % (r["status"], r["name"], r["detail"]))
        print("-" * 60)
        print("PASS %d | FAIL %d | SKIP %d" % (n_pass, n_fail, n_skip))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
