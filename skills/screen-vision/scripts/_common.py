#!/usr/bin/env python3
"""screen-vision shared core.

Zero-dependency essentials so the skill *runs out of the box*: DPI awareness,
a pure-ctypes GDI screen grab, a stdlib PNG writer, monitor enumeration, a
ctypes mouse click, and capability probing. Heavy/optional backends (mss,
uiautomation, winocr, rapidocr, Pillow, pyautogui) are detected lazily and the
pipeline degrades — never hard-crashes — when they are missing.

Coordinates are always PHYSICAL pixels. DPI awareness MUST be set before any
capture/UIA/click call, so callers import this module first and it self-arms.
"""
import os
import sys
import platform
import struct
import zlib
import ctypes

IS_WINDOWS = platform.system() == "Windows"

# --------------------------------------------------------------------------- #
# L0 — DPI awareness (must run before any UI/screenshot/click). Idempotent.    #
# --------------------------------------------------------------------------- #
_DPI_STATE = {"set": False, "level": "none"}


def set_dpi_awareness():
    """Per-Monitor-V2 -> System -> legacy fallback chain. Safe to call repeatedly."""
    if _DPI_STATE["set"] or not IS_WINDOWS:
        _DPI_STATE["set"] = True
        return _DPI_STATE["level"]
    try:
        # PER_MONITOR_AWARE_V2 = -4 (Win10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        _DPI_STATE["level"] = "per_monitor_v2"
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR (Win8.1+)
            _DPI_STATE["level"] = "per_monitor"
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()    # System (Vista+)
                _DPI_STATE["level"] = "system"
            except Exception:
                _DPI_STATE["level"] = "none"
    _DPI_STATE["set"] = True
    return _DPI_STATE["level"]


# Self-arm on import — the #1 documented failure mode is forgetting this.
set_dpi_awareness()


# --------------------------------------------------------------------------- #
# Capability probe                                                            #
# --------------------------------------------------------------------------- #
def _can_import(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def probe_libs():
    return {
        "mss": _can_import("mss"),
        "uiautomation": _can_import("uiautomation"),
        "winocr": _can_import("winocr"),
        "rapidocr": _can_import("rapidocr_onnxruntime"),
        "windows_capture": _can_import("windows_capture"),
        "pillow": _can_import("PIL"),
        "numpy": _can_import("numpy"),
        "pyautogui": _can_import("pyautogui"),
        "pywin32": _can_import("win32gui"),
    }


def is_admin():
    if not IS_WINDOWS:
        try:
            return os.geteuid() == 0
        except Exception:
            return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_wayland():
    return (not IS_WINDOWS) and bool(os.environ.get("WAYLAND_DISPLAY"))


def has_interactive_desktop():
    """False on Session-0 / locked / no-desktop (capture would silently fail)."""
    if not IS_WINDOWS:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_READOBJECTS
        if not hdesk:
            return False
        user32.CloseDesktop(hdesk)
        # GetSystemMetrics(SM_REMOTESESSION=0x1000) -> RDP; still interactive but flag-worthy
        return True
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# Monitor / virtual-screen geometry (physical pixels)                         #
# --------------------------------------------------------------------------- #
def virtual_screen_rect():
    """(left, top, width, height) of the whole virtual desktop. Origin can be negative."""
    if not IS_WINDOWS:
        return (0, 0, 1920, 1080)
    gsm = ctypes.windll.user32.GetSystemMetrics
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
    return (gsm(SM_XVIRTUALSCREEN), gsm(SM_YVIRTUALSCREEN),
            gsm(SM_CXVIRTUALSCREEN), gsm(SM_CYVIRTUALSCREEN))


def _monitor_scale(hmon):
    try:
        shcore = ctypes.windll.shcore
        dx, dy = ctypes.c_uint(), ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0:
            return round(dx.value / 96.0, 4)
    except Exception:
        pass
    return 1.0


def enum_monitors():
    """List of {index, rect:[l,t,r,b], origin:[l,t], physical_size:[w,h], scale, primary}."""
    if not IS_WINDOWS:
        return [{"index": 1, "rect": [0, 0, 1920, 1080], "origin": [0, 0],
                 "physical_size": [1920, 1080], "scale": 1.0, "primary": True}]
    mons = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_double)

    def _cb(hmon, hdc, lprc, lparam):
        r = lprc.contents
        mons.append((hmon, (r.left, r.top, r.right, r.bottom)))
        return 1

    try:
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_cb), 0)
    except Exception:
        pass
    out = []
    for i, (hmon, (l, t, r, b)) in enumerate(mons, 1):
        out.append({
            "index": i, "rect": [l, t, r, b], "origin": [l, t],
            "physical_size": [r - l, b - t], "scale": _monitor_scale(hmon),
            "primary": (l == 0 and t == 0),
        })
    if not out:
        l, t, w, h = virtual_screen_rect()
        out = [{"index": 1, "rect": [l, t, l + w, t + h], "origin": [l, t],
                "physical_size": [w, h], "scale": 1.0, "primary": True}]
    return out


# --------------------------------------------------------------------------- #
# L1 — screen capture. mss if present, else pure-ctypes GDI. Returns RGB bytes.#
# --------------------------------------------------------------------------- #
def _capture_gdi(left, top, width, height):
    """Pure-ctypes BitBlt grab -> top-down RGB bytes. No third-party deps."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    hdesk = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdesk)
    bmp = gdi32.CreateCompatibleBitmap(hdesk, width, height)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, width, height, hdesk, left, top, SRCCOPY | CAPTUREBLT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = width
    bmi.biHeight = -height  # negative => top-down rows
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0  # BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(bmi), 0)  # DIB_RGB_COLORS
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdesk)
    bgra = buf.raw
    # BGRA -> RGB
    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    return bytes(rgb)


def capture_region(left, top, width, height):
    """Return (rgb_bytes, width, height, backend). Prefers mss, falls back to GDI."""
    width = max(1, int(width))
    height = max(1, int(height))
    try:
        import mss  # type: ignore
        with mss.mss() as sct:
            shot = sct.grab({"left": int(left), "top": int(top),
                             "width": width, "height": height})
            bgra = bytes(shot.raw)
            rgb = bytearray(width * height * 3)
            rgb[0::3] = bgra[2::4]
            rgb[1::3] = bgra[1::4]
            rgb[2::3] = bgra[0::4]
            return bytes(rgb), shot.width, shot.height, "mss"
    except Exception:
        if IS_WINDOWS:
            return _capture_gdi(int(left), int(top), width, height), width, height, "gdi"
        raise RuntimeError("no capture backend available on this platform "
                           "(install 'mss': pip install mss)")


def blackness(rgb, w, h, sample=20000):
    """Fraction of near-black pixels (cheap black-screen / occlusion detector)."""
    n = w * h
    if n == 0:
        return 1.0
    step = max(1, (n // sample)) * 3
    dark = total = 0
    for i in range(0, len(rgb) - 2, step):
        total += 1
        if rgb[i] < 12 and rgb[i + 1] < 12 and rgb[i + 2] < 12:
            dark += 1
    return (dark / total) if total else 1.0


# --------------------------------------------------------------------------- #
# Minimal stdlib PNG writer (no Pillow needed)                                #
# --------------------------------------------------------------------------- #
def write_png(path, rgb, w, h):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit, truecolor RGB
    stride = w * 3
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: none
        raw += rgb[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 6)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))
    return path


# --------------------------------------------------------------------------- #
# Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def iou(a, b):
    """IoU of two [l,t,r,b] rects."""
    al, at, ar, ab = a
    bl, bt, br, bb = b
    il, it_ = max(al, bl), max(at, bt)
    ir, ib = min(ar, br), min(ab, bb)
    iw, ih = max(0, ir - il), max(0, ib - it_)
    inter = iw * ih
    if inter == 0:
        return 0.0
    ua = max(0, ar - al) * max(0, ab - at)
    ub = max(0, br - bl) * max(0, bb - bt)
    union = ua + ub - inter
    return inter / union if union else 0.0


# --------------------------------------------------------------------------- #
# Physical mouse click (ctypes; no pyautogui needed)                          #
# --------------------------------------------------------------------------- #
def click_physical(x, y, button="left", double=False):
    if not IS_WINDOWS:
        try:
            import pyautogui  # type: ignore
            pyautogui.click(x, y, button=button, clicks=2 if double else 1)
            return True
        except Exception:
            return False
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010),
             "middle": (0x0020, 0x0040)}.get(button, (0x0002, 0x0004))
    down, up = flags
    times = 2 if double else 1
    for _ in range(times):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
    return True


def find_window_by_title(substr):
    """Return (hwnd, rect[l,t,r,b], title) of first top-level window whose title contains substr."""
    if not IS_WINDOWS:
        return None
    user32 = ctypes.windll.user32
    substr_l = substr.lower()
    found = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return 1
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return 1
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if substr_l in title.lower():
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append((hwnd, [r.left, r.top, r.right, r.bottom], title))
        return 1

    user32.EnumWindows(EnumProc(_cb), 0)
    return found[0] if found else None
