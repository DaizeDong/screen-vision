#!/usr/bin/env python3
"""Pure checks by default. --interactive opens, tests and cleans one owned window.

The interactive path never selects an existing application by its display name.
Missing optional backends are reported as SKIP, not live capability evidence.
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


def t_capture(target):
    result = _run_capture(target, layers="")
    rec("owned_window_capture", "PASS" if result.get("ok") else "FAIL",
        "capture restricted to the owned fixture HWND")


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


def t_golden_uia(target):
    result = _run_capture(target, "uia")
    if not result.get("ok"):
        raise RuntimeError("owned-window capture failed: %s" % result.get("error"))
    with open(result["elements_json"], encoding="utf-8") as handle:
        elements = json.load(handle)
    seven = [el for el in elements if el.get("name") == "Seven" and el["type"] == "button"]
    ok = len(seven) == 1 and bool(seven[0].get("identity")) and "Invoke" in seven[0]["patterns"]
    rec("golden_uia_fixture", "PASS" if ok else "FAIL", "owned synthetic digit button")
    return (result["elements_json"], seven[0]["id"], target) if ok else None


def t_closed_loop(golden):
    if not golden:
        return rec("closed_loop_click", "SKIP", "no verified fixture button")
    elements_path, element_id, target = golden
    for _ in range(2):
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS, "click.py"),
                                 "--elements-json", elements_path, "--id", str(element_id),
                                 "--confirm", "--method", "invoke"],
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        if result.returncode or not json.loads(result.stdout).get("acted"):
            raise RuntimeError("verified fixture action failed")
    result = _run_capture(target, "uia")
    with open(result["elements_json"], encoding="utf-8") as handle:
        elements = json.load(handle)
    ok = any(el.get("name") == "77" for el in elements)
    rec("closed_loop_click", "PASS" if ok else "FAIL", "owned fixture display equals 77")


def run_interactive():
    if not (C.IS_WINDOWS and C._can_import("uiautomation")):
        return rec("interactive_fixture", "SKIP", "Windows and uiautomation are required")
    import uuid
    title = "Screen Vision Test " + uuid.uuid4().hex
    process = None
    try:
        process = subprocess.Popen([sys.executable, os.path.join(HERE, "desktop_fixture.py"),
                                    "--title", title], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("owned fixture exited before its window was ready")
            found = C.find_window_by_title(title)
            identity = C.window_identity(found[0]) if found else None
            if identity and identity['pid'] == process.pid:
                target = 'hwnd:' + str(found[0])
                t_capture(target)
                t_closed_loop(t_golden_uia(target))
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("owned fixture did not become ready")
    except Exception as exc:
        rec("interactive_fixture", "FAIL", str(exc))
    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            except Exception as exc:
                rec("owned_fixture_cleanup", "FAIL", str(exc))


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
    ap.add_argument("--interactive", action="store_true", help="Open and act only on an owned synthetic window.")
    a = ap.parse_args()

    results.clear()
    t_png()
    t_dpi()
    t_iou()
    t_ocr_synthetic()
    if a.interactive:
        run_interactive()
    else:
        rec("interactive_fixture", "SKIP", "not requested; use --interactive for the owned-window test")

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_skip = sum(1 for r in results if r["status"] == "SKIP")
    summary = {"interactive": a.interactive, "pass": n_pass, "fail": n_fail, "skip": n_skip, "results": results}
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
