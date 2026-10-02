#!/usr/bin/env python3
"""pure_ops.py — pure-logic core for screen-vision (NO native deps).

WHY THIS FILE EXISTS (read before editing)
------------------------------------------
The native modules (_common/capture/click/probe) must import ctypes (DPI) and
mss/uiautomation (capture/UIA). Those are deliberately kept OUT of this file so
that the pure, hermetic, platform-independent logic lives somewhere that is:

  * unit-testable without a GUI / hardware / network, and
  * safely auto-patchable by the self-evolve harness, whose patch import-gate
    only admits a tiny stdlib whitelist
    ({json, math, re, typing, dataclasses, collections, itertools, functools,
      pathlib, datetime, decimal}).

RULE FOR ANY EDIT (human or agent): keep this file importing ONLY from that
whitelist (builtins need no import). Do NOT add ctypes / mss / os / sys / struct
/ zlib / numpy here, or the patch gate will reject the change.

The pure helpers cover exact OCR regions, masked OCR pixels, and bounded
black-frame retries. Their contracts are specified in each docstring.
"""


def _blackness(rgb, w, h, sample=20000):
    """Fraction of near-black pixels — cheap black-screen / occlusion detector.

    rgb : bytes-like RGB buffer (3 bytes/pixel, row-major).
    w, h: pixel dimensions.
    Returns a float in [0.0, 1.0]; 1.0 when there are no pixels.
    Pure stdlib (builtins only). Used by capture_with_retry.
    """
    n = w * h
    if n == 0:
        return 1.0
    step = max(1, (n // sample)) * 3
    dark = total = 0
    i = 0
    end = len(rgb) - 2
    while i < end:
        total += 1
        if rgb[i] < 12 and rgb[i + 1] < 12 and rgb[i + 2] < 12:
            dark += 1
        i += step
    return (dark / total) if total else 1.0


# --------------------------------------------------------------------------- #
# Gap 1, region-targeted OCR pre-filter (ARCHITECTURE.md section 1.5)         #
#   "OCR 铁律: 只对 UIA 缺文字的局部区域跑, 别全屏盲跑."                       #
# --------------------------------------------------------------------------- #

def compute_ocr_regions(region, uia_boxes, grid=8):
    """Subtract proven text rectangles from the capture, in absolute pixels.

    The returned disjoint rectangles cover every unexposed pixel and contain no
    covered pixels. The retained grid argument is accepted for caller compatibility;
    exact subtraction avoids clipping text at arbitrary grid-cell boundaries.
    """
    l, t, r, b = region
    if r <= l or b <= t:
        return []
    regions = [[l, t, r, b]]
    for box in uia_boxes:
        remaining = []
        for left, top, right, bottom in regions:
            il, it = max(left, box[0]), max(top, box[1])
            ir, ib = min(right, box[2]), min(bottom, box[3])
            if il >= ir or it >= ib:
                remaining.append([left, top, right, bottom])
                continue
            candidates = ([left, top, right, it], [left, ib, right, bottom],
                          [left, it, il, ib], [ir, it, right, ib])
            remaining.extend(rect for rect in candidates if rect[2] > rect[0] and rect[3] > rect[1])
        regions = remaining
    return regions


def ocr_pixels(rgb, width, height, origin, regions):
    """Crop to the uncovered bounds and mask text-covered pixels in memory."""
    if len(rgb) != width * height * 3 or not regions:
        raise ValueError('OCR requires a complete RGB frame and uncovered regions')
    ox, oy = origin
    left = min(rect[0] for rect in regions)
    top = min(rect[1] for rect in regions)
    right = max(rect[2] for rect in regions)
    bottom = max(rect[3] for rect in regions)
    if not (ox <= left < right <= ox + width and oy <= top < bottom <= oy + height):
        raise ValueError('OCR regions must stay inside the captured frame')
    crop_width, crop_height = right - left, bottom - top
    pixels = bytearray(b'\xff' * (crop_width * crop_height * 3))
    for l, t, r, b in regions:
        for row in range(t, b):
            source = ((row - oy) * width + l - ox) * 3
            target = ((row - top) * crop_width + l - left) * 3
            pixels[target:target + (r-l)*3] = rgb[source:source + (r-l)*3]
    return bytes(pixels), crop_width, crop_height, [left, top]


# --------------------------------------------------------------------------- #
# Gap 2, black-screen auto-retry (ARCHITECTURE.md section 1.3)               #
#   "每步对结果做黑屏检测 -> 自动回退或把窗口前置后重抓."                     #
# --------------------------------------------------------------------------- #
def capture_with_retry(grab_fn, max_attempts=3, black_threshold=0.98):
    """Grab a frame, re-shooting while it looks (near-)black, bounded by attempts.

    Parameters
    ----------
    grab_fn : zero-arg callable returning a tuple (rgb, w, h, backend), where
              rgb is a bytes-like RGB buffer.
    max_attempts   : hard cap on grab_fn() calls (never exceed it).
    black_threshold: a grab is "black" when _blackness(rgb,w,h) > this value.

    Returns
    -------
    dict with keys: rgb, w, h, backend, attempts, blackness.
    Behavior enforced by tests:
      * call grab_fn(); if blackness > black_threshold AND attempts remain,
        grab again; otherwise return the current grab.
      * return the first non-black grab; if all attempts are black, return the
        last one. `attempts` == number of grab_fn() calls actually made.
      * MUST NOT call grab_fn() more than max_attempts times.

    Pure stdlib only (uses _blackness above).
    """
    max_attempts = max(1, int(max_attempts))
    attempts = 0
    rgb = b""
    w = h = 0
    backend = None
    blk = 1.0
    while attempts < max_attempts:
        rgb, w, h, backend = grab_fn()
        attempts += 1
        blk = _blackness(rgb, w, h)
        if blk <= black_threshold:
            break
    return {"rgb": rgb, "w": w, "h": h, "backend": backend,
            "attempts": attempts, "blackness": blk}
