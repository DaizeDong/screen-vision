#!/usr/bin/env python3
"""Pure checks by default. --interactive opens, tests and cleans one owned window.

The interactive path never selects an existing application by its display name.
Missing optional backends are reported as SKIP, not live capability evidence.
"""
import argparse
import copy
import json
import os
import subprocess
import struct
import zlib
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
    if not C.IS_WINDOWS:
        return rec("dpi_awareness", "SKIP", "non-Windows")
    try:
        C.require_physical_coordinates()
    except (RuntimeError, OSError) as exc:
        rec("dpi_awareness", "FAIL", str(exc))
    else:
        rec("dpi_awareness", "PASS", C._DPI_STATE["level"])


def _read_capture_png(path, expected_size):
    """Validate the stdlib writer's RGB PNG and inspect the persisted pixels."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("capture artifact is not a PNG")
    offset, compressed, header, ended = 8, bytearray(), None, False
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+length]
        crc = struct.unpack(">I", data[offset+8+length:offset+12+length])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("capture PNG checksum mismatch")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            ended = True
        offset += length + 12
    if not ended or header != (*expected_size, 8, 2, 0, 0, 0):
        raise ValueError("capture PNG dimensions or RGB format differ from the owned window")
    width, height = expected_size
    raw = zlib.decompress(compressed)
    stride = width * 3 + 1
    if len(raw) != height * stride or any(raw[row*stride] != 0 for row in range(height)):
        raise ValueError("capture PNG pixel layout is invalid")
    rgb = b"".join(raw[row*stride+1:(row+1)*stride] for row in range(height))
    return C.blackness(rgb, width, height)


def _owned_identity(target, expected_identity):
    if not target.startswith("hwnd:"):
        raise ValueError("owned capture requires an explicit HWND")
    hwnd = int(target.split(":", 1)[1])
    identity = C.window_identity(hwnd)
    if (not isinstance(identity, dict) or identity.get("hwnd") != hwnd
            or any(type(identity.get(key)) is not int or identity[key] <= 0
                   for key in ("hwnd", "pid", "process_started"))
            or (expected_identity is not None and identity != expected_identity)):
        raise ValueError("owned window identity changed or is unavailable")
    rect = identity.get("rect")
    if (not isinstance(rect, list) or len(rect) != 4
            or any(type(value) is not int for value in rect)
            or rect[2] <= rect[0] or rect[3] <= rect[1]):
        raise ValueError("owned window bounds are unavailable")
    return copy.deepcopy(identity)


def _owned_capture(target, expected_identity, layers):
    before = _owned_identity(target, expected_identity)
    result = _run_capture(target, layers=layers)
    metadata = result.get("capture", {})
    resolved = metadata.get("resolved_target", {})
    if (result.get("ok") is not True or metadata.get("requested_target") != target
            or metadata.get("fallback_used") is not False
            or resolved.get("kind") != "window" or resolved.get("hwnd") != before["hwnd"]
            or resolved.get("window_identity") != before or resolved.get("rect") != before["rect"]):
        raise ValueError("capture did not retain the owned window identity and scope")
    l, t, r, b = before["rect"]
    if result.get("monitor", {}).get("physical_size") != [r-l, b-t]:
        raise ValueError("capture dimensions differ from the owned window")
    _owned_identity(target, before)
    return result, before


def t_capture(target, expected_identity=None):
    try:
        result, before = _owned_capture(target, expected_identity, "")
        l, t, r, b = before["rect"]
        size = (r-l, b-t)
        blackness = _read_capture_png(result["screenshot"], size)
        if blackness > 0.98:
            raise ValueError("owned window capture is near-black")
        _owned_identity(target, before)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, struct.error, zlib.error) as exc:
        rec("owned_window_capture", "FAIL", str(exc))
        return False
    else:
        rec("owned_window_capture", "PASS",
            "owned HWND and process verified; PNG matches %dx%d and is not near-black" % size)
        return True


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
    if out.returncode:
        raise RuntimeError("owned-window capture command failed")
    result = json.loads(out.stdout)
    if not isinstance(result, dict):
        raise ValueError("capture receipt must be an object")
    return result


def _read_elements(path):
    with open(path, encoding="utf-8") as handle:
        elements = json.load(handle)
    if not isinstance(elements, list) or any(not isinstance(el, dict) for el in elements):
        raise ValueError("owned capture elements must be a list of objects")
    return elements


def _require_owned_element(element, expected_identity):
    identity = element.get("identity")
    if (element.get("source") != "uia" or not isinstance(identity, dict)
            or identity.get("window") != expected_identity
            or any(not isinstance(identity.get(key), list) or not identity[key]
                   or any(type(part) is not int for part in identity[key])
                   for key in ("runtime_id", "window_runtime_id"))):
        raise ValueError("element identity does not belong to the owned window")


def t_golden_uia(target, expected_identity):
    result, window = _owned_capture(target, expected_identity, "uia")
    elements = _read_elements(result["elements_json"])
    seven = [el for el in elements if el.get("name") == "Seven" and el["type"] == "button"]
    if (len(seven) != 1 or "Invoke" not in seven[0].get("patterns", [])
            or type(seven[0].get("id")) is not int or seven[0]["id"] < 0):
        raise ValueError("owned fixture digit button is missing or ambiguous")
    _require_owned_element(seven[0], window)
    _owned_identity(target, window)
    rec("golden_uia_fixture", "PASS", "owned synthetic digit button")
    return {"elements_path": result["elements_json"], "element": copy.deepcopy(seven[0]),
            "target": target, "window": window}


def t_closed_loop(golden):
    if not golden:
        raise ValueError("no verified fixture button")
    elements_path, target, window = golden["elements_path"], golden["target"], golden["window"]
    saved = golden["element"]
    for expected_text in ("7", "77"):
        _owned_identity(target, window)
        selected = [el for el in _read_elements(elements_path) if el.get("id") == saved["id"]]
        if len(selected) != 1 or selected[0] != saved:
            raise ValueError("golden element changed before action")
        _require_owned_element(selected[0], window)
        _owned_identity(target, window)
        result = subprocess.run([sys.executable, os.path.join(SCRIPTS, "click.py"),
                                 "--elements-json", elements_path, "--id", str(saved["id"]),
                                 "--confirm", "--method", "invoke"],
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        if result.returncode or json.loads(result.stdout).get("acted") is not True:
            raise RuntimeError("verified fixture action failed")
        result, _ = _owned_capture(target, window, "uia")
        display = [el for el in _read_elements(result["elements_json"])
                   if el.get("name") == expected_text]
        if len(display) != 1:
            raise ValueError("owned fixture display does not equal " + expected_text)
        _require_owned_element(display[0], window)
        _owned_identity(target, window)
    rec("closed_loop_click", "PASS", "owned fixture display equals 77")


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
                if process.poll() is not None:
                    raise RuntimeError("owned fixture exited during window discovery")
                target = 'hwnd:' + str(found[0])
                identity = copy.deepcopy(identity)
                if t_capture(target, identity) is not True:
                    raise RuntimeError("owned fixture capture verification failed")
                t_closed_loop(t_golden_uia(target, identity))
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
    if not ((C.IS_WINDOWS and C._can_import("winocr")) or C._can_import("rapidocr_onnxruntime")):
        return rec("ocr_synthetic", "SKIP", "no supported OCR engine installed")
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
    rec("ocr_synthetic", "PASS" if ok else "FAIL",
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
