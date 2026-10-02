#!/usr/bin/env python3
"""screen-vision shared core.

Zero-dependency essentials so the skill *runs out of the box*: DPI awareness,
a pure-ctypes GDI screen grab, a stdlib PNG writer, monitor enumeration, a
ctypes mouse click, and capability probing. Heavy/optional backends (mss,
uiautomation, winocr, rapidocr, Pillow, pyautogui) are detected lazily and the
pipeline can use available backends when optional libraries are missing.

Coordinates are PHYSICAL pixels. Import attempts DPI setup; coordinate-sensitive
operations require verified effective per-monitor awareness and fail otherwise.
"""
import os
import sys
import platform
import struct
import zlib
import ctypes

IS_WINDOWS = platform.system() == "Windows"

# The scripts emit `ensure_ascii=False` JSON. On a non-English Windows console a
# redirected stdout pipe defaults to the locale codepage (e.g. cp936), which
# corrupts any non-ASCII UIA label and breaks the documented UTF-8 JSON contract
# for downstream readers. Pin both streams to UTF-8 (best-effort, Py3.7+).
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8")
    except Exception:
        pass

# --------------------------------------------------------------------------- #
# L0, DPI awareness (must run before any UI/screenshot/click). Idempotent.    #
# --------------------------------------------------------------------------- #
_DPI_STATE = {"set": False, "level": "none"}


def _win32_function(library, name, result_type, argument_types):
    function = getattr(library, name)
    function.restype = result_type
    function.argtypes = argument_types
    return function


def _effective_dpi_awareness():
    """Query the calling thread; use process awareness only on older Windows."""
    user32 = ctypes.windll.user32
    try:
        context_fn = _win32_function(user32, 'GetThreadDpiAwarenessContext', ctypes.c_void_p, [])
    except AttributeError:
        context_fn = None
    if context_fn is not None:
        try:
            context = context_fn()
            if not context:
                return 'unverified'
            query = _win32_function(user32, 'GetAwarenessFromDpiAwarenessContext',
                                    ctypes.c_int, [ctypes.c_void_p])
            awareness = query(context)
            if awareness == 2:
                try:
                    equal = _win32_function(user32, 'AreDpiAwarenessContextsEqual', ctypes.c_int,
                                            [ctypes.c_void_p, ctypes.c_void_p])
                    if equal(context, ctypes.c_void_p(-4)):
                        return 'per_monitor_v2'
                except (AttributeError, OSError):
                    pass  # The awareness query still proved per-monitor v1 or v2.
            return {0: 'unaware', 1: 'system', 2: 'per_monitor'}.get(awareness, 'unverified')
        except Exception:
            # A failed current-thread query cannot be replaced by a process default.
            return 'unverified'
    try:
        query = _win32_function(ctypes.windll.shcore, 'GetProcessDpiAwareness', ctypes.c_long,
                                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)])
    except (AttributeError, OSError):
        try:
            legacy = _win32_function(user32, 'IsProcessDPIAware', ctypes.c_int, [])
            return 'system' if legacy() else 'unaware'
        except (AttributeError, OSError):
            return 'unverified'
    try:
        awareness = ctypes.c_int(-1)
        if query(None, ctypes.byref(awareness)) == 0:
            return {0: 'unaware', 1: 'system', 2: 'per_monitor'}.get(awareness.value, 'unverified')
    except (AttributeError, OSError):
        pass
    return 'unverified'


def set_dpi_awareness():
    """Attempt setup once, but recheck effective thread awareness on every call."""
    if not IS_WINDOWS:
        return 'none'
    if not _DPI_STATE['set']:
        setters = [('user32', 'SetProcessDpiAwarenessContext', ctypes.c_int,
                    [ctypes.c_void_p], (ctypes.c_void_p(-4),), 'bool'),
                   ('shcore', 'SetProcessDpiAwareness', ctypes.c_long, [ctypes.c_int], (2,), 'hresult'),
                   ('user32', 'SetProcessDPIAware', ctypes.c_int, [], (), 'bool')]
        for library_name, name, result_type, argument_types, args, contract in setters:
            try:
                function = _win32_function(getattr(ctypes.windll, library_name), name,
                                           result_type, argument_types)
                result = function(*args)
                succeeded = result == 0 if contract == 'hresult' else bool(result)
                if succeeded:
                    break
            except (AttributeError, OSError):
                continue
        _DPI_STATE['set'] = True
    _DPI_STATE['level'] = _effective_dpi_awareness()
    return _DPI_STATE['level']


def require_physical_coordinates():
    """Refuse virtualized or unverified Windows coordinates, including system DPI."""
    if IS_WINDOWS:
        level = set_dpi_awareness()
        if level not in ('per_monitor_v2', 'per_monitor'):
            raise RuntimeError('DPI awareness is %s; verified per-monitor awareness is required '
                               'for physical coordinates' % level)


# Self-arm on import, the #1 documented failure mode is forgetting this.
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
    """Check Windows desktop access, macOS capture permission, or Linux display state."""
    has_interactive_desktop.reason = None
    if not IS_WINDOWS and platform.system() == "Darwin":
        try:
            core_graphics = ctypes.CDLL(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            preflight = _win32_function(core_graphics, "CGPreflightScreenCaptureAccess",
                                       ctypes.c_bool, [])
            if not preflight():
                has_interactive_desktop.reason = "macOS Screen Recording permission is unavailable"
                return False
            return True
        except (AttributeError, OSError) as exc:
            has_interactive_desktop.reason = (
                "macOS Screen Recording permission could not be verified: " + type(exc).__name__)
            return False
    if not IS_WINDOWS:
        available = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if not available:
            has_interactive_desktop.reason = 'No display session is configured'
        return available
    try:
        user32 = ctypes.windll.user32
        # Resolve the release function before acquiring a handle we own.
        close_desktop = _win32_function(user32, 'CloseDesktop', ctypes.c_int, [ctypes.c_void_p])
        open_desktop = _win32_function(user32, 'OpenInputDesktop', ctypes.c_void_p,
                                       [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32])
        hdesk = open_desktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not hdesk:
            has_interactive_desktop.reason = 'OpenInputDesktop could not access the input desktop'
            return False
        if not close_desktop(hdesk):
            has_interactive_desktop.reason = 'CloseDesktop failed; desktop probe did not complete'
            return False
        return True
    except Exception as exc:
        has_interactive_desktop.reason = '%s: %s' % (type(exc).__name__, exc)
        return False


# --------------------------------------------------------------------------- #
# Monitor / virtual-screen geometry (physical pixels)                         #
# --------------------------------------------------------------------------- #
def virtual_screen_rect():
    """(left, top, width, height) of the whole virtual desktop. Origin can be negative."""
    if not IS_WINDOWS:
        monitor = _backend_monitors()[0]
        return tuple(monitor[key] for key in ('left', 'top', 'width', 'height'))
    require_physical_coordinates()
    gsm = _win32_function(ctypes.windll.user32, 'GetSystemMetrics', ctypes.c_int, [ctypes.c_int])
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
    rect = (gsm(SM_XVIRTUALSCREEN), gsm(SM_YVIRTUALSCREEN),
            gsm(SM_CXVIRTUALSCREEN), gsm(SM_CYVIRTUALSCREEN))
    if rect[2] <= 0 or rect[3] <= 0:
        raise RuntimeError('Virtual desktop geometry has invalid dimensions')
    return rect


def validate_monitor_geometry(monitors):
    """Reject missing or degenerate physical monitor rectangles before target selection."""
    if not isinstance(monitors, list) or not monitors:
        raise RuntimeError('Monitor geometry is unavailable')
    indexes = set()
    for monitor in monitors:
        if not isinstance(monitor, dict):
            raise RuntimeError('Invalid monitor geometry')
        rect, index = monitor.get('rect'), monitor.get('index')
        if (type(index) is not int or index < 1 or index in indexes
                or not isinstance(rect, (list, tuple)) or len(rect) != 4
                or any(type(value) is not int for value in rect)
                or rect[2] <= rect[0] or rect[3] <= rect[1]):
            raise RuntimeError('Invalid monitor geometry or index')
        indexes.add(index)


def _backend_monitors():
    """Read MSS monitor metadata; never replace unavailable geometry with a guessed size."""
    try:
        import mss
        with mss.mss() as backend:
            monitors = [dict(monitor) for monitor in backend.monitors]
        if len(monitors) < 2:
            raise ValueError('no physical monitors')
        for monitor in monitors:
            if (any(type(monitor.get(key)) is not int for key in ('left', 'top', 'width', 'height'))
                    or monitor['width'] <= 0 or monitor['height'] <= 0):
                raise ValueError('invalid monitor dimensions')
        return monitors
    except Exception as exc:
        raise RuntimeError('Capture-backend monitor geometry is unavailable') from exc


def _monitor_scale(hmon):
    try:
        shcore = ctypes.windll.shcore
        dx, dy = ctypes.c_uint(), ctypes.c_uint()
        query = _win32_function(shcore, 'GetDpiForMonitor', ctypes.c_long,
                                [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint),
                                 ctypes.POINTER(ctypes.c_uint)])
        if query(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value > 0 and dy.value > 0:
            return round(dx.value / 96.0, 4)
    except (AttributeError, OSError) as exc:
        raise RuntimeError('Monitor DPI scale is unavailable') from exc
    raise RuntimeError('Monitor DPI scale query failed')


def enum_monitors():
    """List of {index, rect:[l,t,r,b], origin:[l,t], physical_size:[w,h], scale, primary}."""
    if not IS_WINDOWS:
        out = []
        for index, monitor in enumerate(_backend_monitors()[1:], 1):
            l, t, w, h = (monitor[key] for key in ('left', 'top', 'width', 'height'))
            out.append({'index': index, 'rect': [l, t, l+w, t+h], 'origin': [l, t],
                        'physical_size': [w, h], 'scale': 1.0, 'scale_source': 'capture_pixel_units',
                        'primary': l == 0 and t == 0})
        validate_monitor_geometry(out)
        return out
    require_physical_coordinates()
    mons = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_ssize_t)

    invalid_geometry = []
    def _cb(hmon, hdc, lprc, lparam):
        if not hmon or not lprc:
            invalid_geometry.append(True)
            return 0
        r = lprc.contents
        if r.right <= r.left or r.bottom <= r.top:
            invalid_geometry.append(True)
            return 0
        mons.append((hmon, (r.left, r.top, r.right, r.bottom)))
        return 1

    try:
        enumerate_monitors = _win32_function(ctypes.windll.user32, 'EnumDisplayMonitors', ctypes.c_int,
                                             [ctypes.c_void_p, ctypes.c_void_p, MONITORENUMPROC, ctypes.c_ssize_t])
        succeeded = enumerate_monitors(None, None, MONITORENUMPROC(_cb), 0)
    except (AttributeError, OSError) as exc:
        raise RuntimeError('Monitor enumeration is unavailable') from exc
    if not succeeded or not mons or invalid_geometry:
        raise RuntimeError('Monitor enumeration failed or returned no valid monitors')
    out = []
    for i, (hmon, (l, t, r, b)) in enumerate(mons, 1):
        out.append({
            "index": i, "rect": [l, t, r, b], "origin": [l, t],
            "physical_size": [r - l, b - t], "scale": _monitor_scale(hmon),
            "primary": (l == 0 and t == 0),
        })
    validate_monitor_geometry(out)
    return out


# --------------------------------------------------------------------------- #
# L1, screen capture. mss if present, else pure-ctypes GDI. Returns RGB bytes.#
# --------------------------------------------------------------------------- #
def _capture_gdi(left, top, width, height):
    """Pure-ctypes BitBlt grab -> top-down RGB bytes. No third-party deps."""
    require_physical_coordinates()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    handle, integer, unsigned = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint
    get_dc = _win32_function(user32, 'GetDC', handle, [handle])
    release_dc = _win32_function(user32, 'ReleaseDC', integer, [handle, handle])
    create_dc = _win32_function(gdi32, 'CreateCompatibleDC', handle, [handle])
    create_bitmap = _win32_function(gdi32, 'CreateCompatibleBitmap', handle, [handle, integer, integer])
    select = _win32_function(gdi32, 'SelectObject', handle, [handle, handle])
    blit = _win32_function(gdi32, 'BitBlt', integer,
                           [handle, integer, integer, integer, integer, handle, integer, integer, unsigned])
    delete_bitmap = _win32_function(gdi32, 'DeleteObject', integer, [handle])
    delete_dc = _win32_function(gdi32, 'DeleteDC', integer, [handle])

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    get_bits = _win32_function(gdi32, 'GetDIBits', integer,
                               [handle, handle, unsigned, unsigned, ctypes.c_void_p,
                                ctypes.POINTER(BITMAPINFOHEADER), unsigned])
    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = width
    bmi.biHeight = -height  # negative => top-down rows
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0  # BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    hdesk = mem = bmp = previous = None
    selected = False
    invalid_objects = (None, 0, -1, ctypes.c_void_p(-1).value)
    try:
        hdesk = get_dc(None)
        if not hdesk:
            raise RuntimeError('GetDC failed')
        mem = create_dc(hdesk)
        if not mem:
            raise RuntimeError('CreateCompatibleDC failed')
        bmp = create_bitmap(hdesk, width, height)
        if not bmp:
            raise RuntimeError('CreateCompatibleBitmap failed')
        previous = select(mem, bmp)
        if previous in invalid_objects:
            raise RuntimeError('SelectObject failed')
        selected = True
        if not blit(mem, 0, 0, width, height, hdesk, left, top, SRCCOPY | CAPTUREBLT):
            raise RuntimeError('BitBlt failed')
        # GetDIBits requires the bitmap to be deselected from every DC.
        if select(mem, previous) in invalid_objects:
            raise RuntimeError('SelectObject restore failed')
        selected = False
        scanlines = get_bits(hdesk, bmp, 0, height, buf, ctypes.byref(bmi), 0)
        if scanlines != height:
            raise RuntimeError('GetDIBits returned %s of %s scanlines' % (scanlines, height))
    finally:
        primary_error = sys.exc_info()[1]
        errors = []

        def release(name, function, *args, invalid=(None, 0)):
            try:
                if function(*args) in invalid:
                    raise RuntimeError('returned failure')
                return True
            except Exception as exc:
                errors.append('%s: %s' % (name, exc))
                return False

        if selected:
            selected = not release('SelectObject restore', select, mem, previous, invalid=invalid_objects)
        if selected and mem:
            # A failed restore leaves the bitmap selected; dispose the DC first.
            release('DeleteDC', delete_dc, mem)
            mem = None
        if bmp:
            release('DeleteObject', delete_bitmap, bmp)
        if mem:
            release('DeleteDC', delete_dc, mem)
        if hdesk:
            release('ReleaseDC', release_dc, None, hdesk)
        if errors:
            detail = 'GDI cleanup failed: ' + '; '.join(errors)
            if primary_error is not None:
                detail = str(primary_error) + '; ' + detail
            raise RuntimeError(detail) from primary_error
    bgra = buf.raw
    # BGRA -> RGB
    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    return bytes(rgb)


def capture_region(left, top, width, height):
    """Return (rgb_bytes, width, height, backend). Prefers mss, falls back to GDI."""
    require_physical_coordinates()
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
def click_physical(x, y, button="left", double=False, *, before_injection=None):
    if not IS_WINDOWS:
        if before_injection is not None:
            return False
        try:
            import pyautogui  # type: ignore
            pyautogui.click(x, y, button=button, clicks=2 if double else 1)
            return True
        except Exception:
            return False
    try:
        require_physical_coordinates()
    except RuntimeError:
        return False
    user32 = ctypes.windll.user32
    from ctypes import wintypes as W
    x, y = int(x), int(y)
    try:
        if not user32.SetCursorPos(x, y):
            return False
    except Exception:
        return False
    flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010),
             "middle": (0x0020, 0x0040)}.get(button, (0x0002, 0x0004))
    down, up = flags
    dispatched = False

    def position_confirmed():
        try:
            position = W.POINT()
            matched = bool(user32.GetCursorPos(ctypes.byref(position))) and (position.x, position.y) == (x, y)
        except Exception:
            matched = False
        if not matched and dispatched:
            raise RuntimeError('pointer position changed after physical dispatch started')
        return matched

    for _ in range(2 if double else 1):
        if not position_confirmed():
            return False
        if before_injection is not None:
            try:
                before_injection()
            except Exception as exc:
                if dispatched:
                    raise RuntimeError('target revalidation failed after physical dispatch started') from exc
                raise
        if not position_confirmed():
            return False
        # A native call may deliver the down event before reporting an error.
        dispatched = True
        try:
            user32.mouse_event(down, 0, 0, 0, 0)
        finally:
            user32.mouse_event(up, 0, 0, 0, 0)
    return True


class WindowDiscoveryError(RuntimeError):
    """Native discovery did not establish a complete set of candidate windows."""


def find_window_by_title(substr):
    """Return a unique visible match only after complete, checked title discovery."""
    if not IS_WINDOWS:
        return None
    require_physical_coordinates()
    user32 = ctypes.windll.user32
    substr_l = substr.lower()
    found = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    try:
        visible = _win32_function(user32, 'IsWindowVisible', ctypes.c_int, [ctypes.c_void_p])
        title_length = _win32_function(user32, 'GetWindowTextLengthW', ctypes.c_int, [ctypes.c_void_p])
        read_title = _win32_function(user32, 'GetWindowTextW', ctypes.c_int,
                                    [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int])
        read_rect = _win32_function(user32, 'GetWindowRect', ctypes.c_int,
                                   [ctypes.c_void_p, ctypes.POINTER(RECT)])
        enumerate_windows = _win32_function(user32, 'EnumWindows', ctypes.c_int,
                                            [EnumProc, ctypes.c_ssize_t])
        # windll does not use ctypes' private last-error copy. Query the OS value.
        clear_error = _win32_function(ctypes.windll.kernel32, 'SetLastError', None, [ctypes.c_uint32])
        last_error = _win32_function(ctypes.windll.kernel32, 'GetLastError', ctypes.c_uint32, [])
    except (AttributeError, OSError) as exc:
        raise WindowDiscoveryError('Window title discovery APIs are unavailable') from exc

    failures = []

    def checked_length(hwnd):
        clear_error(0)
        length = title_length(hwnd)
        if last_error() or length < 0:
            raise RuntimeError('Window title length query failed')
        return length

    def _cb(hwnd, lparam):
        try:
            if not visible(hwnd):
                return 1
            n = checked_length(hwnd)
            # One spare character makes growth at the original buffer boundary detectable.
            buf = ctypes.create_unicode_buffer(n + 2)
            clear_error(0)
            copied = read_title(hwnd, buf, n + 2)
            error = last_error()
            title = buf.value
            units = len(title.encode('utf-16-le')) // 2
            if (error or copied < 0 or (n > 0 and copied == 0) or copied != units or copied > n
                    or checked_length(hwnd) != n):
                raise RuntimeError('Window title retrieval was incomplete or changed')
            if substr_l in title.lower():
                r = RECT()
                if not read_rect(hwnd, ctypes.byref(r)) or r.right <= r.left or r.bottom <= r.top:
                    raise RuntimeError('Matched window bounds are unavailable')
                found.append((hwnd, [r.left, r.top, r.right, r.bottom], title))
            return 1
        except Exception as exc:
            # ctypes callbacks cannot propagate exceptions to their caller.
            failures.append(exc)
            return 0

    try:
        complete = enumerate_windows(EnumProc(_cb), 0)
    except Exception as exc:
        raise WindowDiscoveryError('Window title discovery failed') from exc
    if not complete or failures:
        raise WindowDiscoveryError('Window title discovery was incomplete') from (failures[0] if failures else None)
    return found[0] if len(found) == 1 else None


def window_identity(hwnd):
    """Read HWND, PID, process creation time and physical bounds; fail closed."""
    if not IS_WINDOWS or not isinstance(hwnd, int) or hwnd <= 0:
        return None
    require_physical_coordinates()
    from ctypes import wintypes as W
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.IsWindow.argtypes = [W.HWND]
    user32.IsWindowVisible.argtypes = [W.HWND]
    user32.IsIconic.argtypes = [W.HWND]
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel32.OpenProcess.restype = W.HANDLE
    kernel32.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    kernel32.CloseHandle.argtypes = [W.HANDLE]
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    pid, rect = W.DWORD(), W.RECT()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (W.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, *[ctypes.byref(v) for v in (created, exited, kernel, user)]):
            return None
        return {'hwnd': hwnd, 'pid': pid.value,
                'process_started': (created.dwHighDateTime << 32) | created.dwLowDateTime,
                'rect': [rect.left, rect.top, rect.right, rect.bottom]}
    finally:
        kernel32.CloseHandle(handle)


def runtime_id(control):
    value = list(control.GetRuntimeId())
    if not value or any(type(part) is not int for part in value):
        raise ValueError('missing UIA runtime identity')
    return value


def control_identity(control, root):
    window = window_identity(int(root.NativeWindowHandle))
    if not window or control.ProcessId != window['pid']:
        raise ValueError('window/process identity unavailable')
    return {'runtime_id': runtime_id(control), 'window_runtime_id': runtime_id(root),
            'window': window}
