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
    """True / False / None, where None means the probe could not answer -- not "no GPU".

    THE TIMEOUT WAS 8 SECONDS AND THE COMMAND TAKES 13. Measured on this machine, three consecutive
    runs of the wmic call: 12.52s, 14.05s, 13.20s, every one of them returning the GPU correctly. So
    the probe timed out 100% of the time, the bare `except Exception: pass` swallowed it, and a
    definite YES was reported as an indistinguishable "unknown" on every single run.

    The slowness is not this command's fault and not fixable by picking a different one. Timed here:
    wmic 16.8s, Get-CimInstance 13.5s, Get-PnpDevice 15.6s. Enumerating display devices is simply
    slow on this box, the same shape as its event log being 50x slower than the others. So the cap
    goes to 30s, comfortably past the measured 17s worst case, rather than to a number that merely
    beats today's median.

    The other half matters more than the number. "Timed out" and "no GPU found" used to share one
    return value, so nothing downstream could tell a failed probe from a real answer. They are now
    separate, and the reason is carried on the function so the report can say which.
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
        txt = (out.stdout or "").lower()
        return any(k in txt for k in ("nvidia", "amd", "radeon", "intel arc"))
    except subprocess.TimeoutExpired:
        # NOT "no GPU". The probe ran out of time and knows nothing either way.
        # The number comes from the variable, not from prose. A message that hardcodes the
        # budget starts lying the first time somebody tunes it, and this message exists
        # precisely to be trusted when nothing else can answer.
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
        # gpu_present is tri-state: True / False / None. When it is None the reason says why,
        # so a reader can tell a probe that failed from a machine with no GPU.
        "gpu_present": _gpu(report_reason := {}),
        "gpu_present_unknown_because": report_reason.get("why"),
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
