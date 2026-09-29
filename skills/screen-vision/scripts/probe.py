#!/usr/bin/env python3
"""probe.py — environment self-check. Run this first when something looks wrong.

Reports DPI awareness, platform, Wayland, admin rights, interactive desktop,
installed optional backends, and monitor geometry. Everything degrades, so this
tells you WHICH capability is available before you rely on it.

Usage:  python probe.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def gpu_present():
    """Report recognized GPU presence, explicit no-instances, or None with a reason.

    Successful WMIC output must include a Name table with a recognized graphics
    vendor, or the explicit no-instances result. Empty, unfamiliar and failed
    output cannot establish absence. Enumeration has a 30-second budget.
    """
    gpu_present.reason = None
    try:
        import subprocess
        if not C.IS_WINDOWS:
            gpu_present.reason = "not implemented on this platform"
            return None
        budget = 30
        out = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"],
                             capture_output=True, text=True, timeout=budget)
        if out.returncode != 0:
            gpu_present.reason = 'video-controller enumeration exited %s; presence unknown' % out.returncode
            return None
        rows = [line.strip().lower() for line in (out.stdout or '').splitlines() if line.strip()]
        if rows == ['no instance(s) available.']:
            return False
        if len(rows) >= 2 and rows[0] == 'name':
            if any(re.search(r'\b(nvidia|amd|radeon|ati|intel)\b', row) for row in rows[1:]):
                return True
        gpu_present.reason = 'video-controller enumeration returned unrecognized or empty output; presence unknown'
        return None
    except subprocess.TimeoutExpired:
        gpu_present.reason = ("video-controller enumeration exceeded %ss; presence unknown" % budget)
        return None
    except Exception as e:                      # noqa: BLE001 -- reported, not swallowed
        gpu_present.reason = "%s: %s" % (type(e).__name__, e)
        return None



def _gpu(sink):
    """Call gpu_present() and hand the caller the reason it could not answer, if any."""
    v = gpu_present()
    if v is None:
        sink["why"] = getattr(gpu_present, "reason", None) or "unknown"
    return v


def main():
    libs = C.probe_libs()
    dpi_awareness = C.set_dpi_awareness()
    coordinate_error = None
    desktop_ready = C.has_interactive_desktop() is True
    desktop_error = None if desktop_ready else (
        getattr(C.has_interactive_desktop, 'reason', None) or 'Interactive desktop access is unavailable')
    monitors = []
    try:
        C.require_physical_coordinates()
        if desktop_ready:
            monitors = C.enum_monitors()
            C.validate_monitor_geometry(monitors)
    except (RuntimeError, OSError) as exc:
        monitors = []
        coordinate_error = str(exc)
    session_ready = coordinate_error is None and desktop_ready
    report = {
        "ok": session_ready,
        "platform": C.platform.system(),
        "python": sys.version.split()[0],
        "dpi_awareness": dpi_awareness,
        "coordinate_error": coordinate_error,
        "desktop_error": desktop_error,
        "is_wayland": C.is_wayland(),
        "admin": C.is_admin(),
        "interactive_desktop": desktop_ready,
        "libs": libs,
        "monitors": monitors,
        # gpu_present is tri-state: True / False / None. When it is None the reason says why,
        # so a reader can tell a probe that failed from a machine with no GPU.
        "gpu_present": _gpu(report_reason := {}),
        "gpu_present_unknown_because": report_reason.get("why"),
        "capabilities": {
            "screenshot": session_ready and (C.IS_WINDOWS or libs["mss"]),
            "uia_elements": session_ready and C.IS_WINDOWS and libs["uiautomation"],
            "ocr": libs["winocr"] or libs["rapidocr"],
            "annotate": libs["pillow"],
            "click_physical": session_ready and (C.IS_WINDOWS or libs["pyautogui"]),
            "click_invoke": session_ready and C.IS_WINDOWS and libs["uiautomation"],
            "vision_backend": False,  # optional, user-supplied (see backends.md)
        },
        "notes": [],
    }
    if coordinate_error:
        report['notes'].append(coordinate_error)
    if desktop_error:
        report['notes'].append(desktop_error)
    if C.IS_WINDOWS and not libs["uiautomation"]:
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
    return 0 if session_ready else 1


if __name__ == "__main__":
    sys.exit(main())
