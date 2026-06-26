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

Two architecture requirements (ARCHITECTURE.md) are STUBBED below and must be
implemented to satisfy tests/test_gaps_v0_2.py. Implement them in-place; the
contracts are fully specified in each docstring.
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
# Gap 1 — region-targeted OCR pre-filter (ARCHITECTURE.md section 1.5)         #
#   "OCR 铁律: 只对 UIA 缺文字的局部区域跑, 别全屏盲跑."                       #
# --------------------------------------------------------------------------- #
def compute_ocr_regions(region, uia_boxes, grid=8):
    """Return the sub-rectangles of *region* NOT already covered by UIA.

    Instead of OCR-ing the whole screenshot and discarding UIA-overlapping
    results (the anti-pattern v0.1 collect_ocr uses), pre-compute the UIA-empty
    sub-areas so OCR only runs where structured text is missing.

    Parameters
    ----------
    region    : [l, t, r, b] absolute rectangle of the captured area.
    uia_boxes : list of [l, t, r, b] absolute UIA element rectangles.
    grid      : split *region* into grid x grid cells (default 8).

    Returns
    -------
    list of [l, t, r, b] cell rectangles inside *region* whose center does NOT
    fall inside any uia_box. Contract enforced by tests:
      * no uia_boxes        -> cells tile the whole region; union area
                               >= 0.9 * area(region).
      * region fully covered -> [] (or union area <= 0.02 * area(region)).
      * partial cover        -> non-empty; union area < area(region); AND no
                               returned cell's center lies inside any uia_box.

    Suggested implementation: split region into grid*grid equal cells; keep a
    cell iff its center point is outside every uia_box. Pure stdlib only.
    """
    l, t, r, b = region
    width = r - l
    height = b - t
    if width <= 0 or height <= 0:
        return []
    grid = max(1, int(grid))
    out = []
    for gy in range(grid):
        ct = t + int(round(gy * height / grid))
        cb = b if gy == grid - 1 else t + int(round((gy + 1) * height / grid))
        for gx in range(grid):
            cl = l + int(round(gx * width / grid))
            cr = r if gx == grid - 1 else l + int(round((gx + 1) * width / grid))
            if cr <= cl or cb <= ct:
                continue
            cx = (cl + cr) / 2.0
            cy = (ct + cb) / 2.0
            covered = False
            for bx in uia_boxes:
                if bx[0] <= cx <= bx[2] and bx[1] <= cy <= bx[3]:
                    covered = True
                    break
            if not covered:
                out.append([cl, ct, cr, cb])
    return out


# --------------------------------------------------------------------------- #
# Gap 2 — black-screen auto-retry (ARCHITECTURE.md section 1.3)               #
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
