#!/usr/bin/env python3
"""probe.py — environment self-check. Run this first when something looks wrong.

Reports DPI awareness, platform, Wayland, admin rights, interactive desktop,
installed optional backends, and monitor geometry. Everything degrades, so this
tells you WHICH capability is available before you rely on it.

Usage:  python probe.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def gpu_present():
    # best-effort, no hard deps
    try:
        import subprocess
        if C.IS_WINDOWS:
            out = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"],
                                 capture_output=True, text=True, timeout=8)
            txt = (out.stdout or "").lower()
            return any(k in txt for k in ("nvidia", "amd", "radeon", "intel arc"))
    except Exception:
        pass
    return None  # unknown


def main():
    libs = C.probe_libs()
    report = {
        "ok": True,
        "platform": C.platform.system(),
        "python": sys.version.split()[0],
        "dpi_awareness": C.set_dpi_awareness(),
        "is_wayland": C.is_wayland(),
        "admin": C.is_admin(),
        "interactive_desktop": C.has_interactive_desktop(),
        "libs": libs,
        "monitors": C.enum_monitors(),
        "gpu_present": gpu_present(),
        "capabilities": {
            "screenshot": True,  # always (mss or pure-ctypes GDI fallback / mss elsewhere)
            "uia_elements": C.IS_WINDOWS and libs["uiautomation"],
            "ocr": libs["winocr"] or libs["rapidocr"],
            "annotate": libs["pillow"],
            "click_physical": True,
            "click_invoke": C.IS_WINDOWS and libs["uiautomation"],
            "vision_backend": False,  # optional, user-supplied (see backends.md)
        },
        "notes": [],
    }
    if not report["capabilities"]["uia_elements"]:
        report["notes"].append("No UIA: install 'uiautomation' for structured element reading "
                               "(otherwise only OCR/vision text is available).")
    if not report["capabilities"]["ocr"]:
        report["notes"].append("No OCR: install 'rapidocr-onnxruntime' (cross-platform) "
                               "or 'winocr' (Windows) to read text not exposed by UIA.")
    if not libs["mss"]:
        report["notes"].append("'mss' not installed: using pure-ctypes GDI capture "
                               "(works on Windows; install mss for speed / cross-platform).")
    if report["is_wayland"]:
        report["notes"].append("Wayland session: silent screen capture is blocked; expect failures.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
