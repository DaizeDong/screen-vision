#!/usr/bin/env python3
"""v0.2 capability-gap signals (RED on purpose -> headroom for self-evolve).

These two tests encode genuine, currently-UNIMPLEMENTED architecture
requirements (see ARCHITECTURE.md). They are HERMETIC: pure logic + a fake
capture callable; no GUI, no network, no hardware. They are expected to FAIL
on the v0.1 baseline and turn GREEN only once the underlying capability is
implemented in scripts/_common.py — giving self-evolve's A-tier acceptor a
legitimate (fail -> pass) headroom pair (= real capability gain, not test
padding).

Closed gaps:
  1. region-targeted OCR pre-filter  (ARCH section 1.5 "OCR 铁律: 别全屏盲跑")
     The v0.1 collect_ocr() OCRs the WHOLE screenshot then drops UIA-covered
     results (the exact "blind full-screen OCR" anti-pattern the arch forbids).
     Required: C.compute_ocr_regions(region, uia_boxes) returning the
     UIA-EMPTY sub-rectangles to OCR.
  2. black-screen auto-retry  (ARCH section 1.3 "黑屏检测 -> 自动重抓")
     blackness() exists but is dead code, never wired into capture. Required:
     C.capture_with_retry(grab_fn, ...) that re-shoots on a near-black grab.

Contracts (what an implementation MUST satisfy):

  compute_ocr_regions(region, uia_boxes, grid=8) -> list[[l, t, r, b]]
    region    : [l, t, r, b] absolute rect of the captured area
    uia_boxes : list of [l, t, r, b] absolute UIA element rects
    returns   : sub-rectangles inside `region` NOT covered by any uia_box.
                - no boxes        -> union area >= 0.9 * region area
                - region fully    -> []
                  covered
                - partial cover   -> non-empty, union area < region area,
                                     and no returned rect's center lies inside
                                     any covering uia_box.

  capture_with_retry(grab_fn, max_attempts=3, black_threshold=0.98) -> dict
    grab_fn() -> (rgb_bytes, w, h, backend)
    returns dict with keys: rgb, w, h, backend, attempts, blackness
    behavior: grab; if blackness(rgb,w,h) > black_threshold and attempts
              remain, re-grab; return first non-black grab (or last attempt
              if all black). Must never loop past max_attempts.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "skills", "screen-vision", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))

import _common as C  # noqa: E402


def _area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def _center_in(rect, box):
    cx = (rect[0] + rect[2]) / 2.0
    cy = (rect[1] + rect[3]) / 2.0
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


# --------------------------------------------------------------------------- #
# Gap 1 — region-targeted OCR pre-filter                                       #
# --------------------------------------------------------------------------- #
def test_compute_ocr_regions_exists():
    assert hasattr(C, "compute_ocr_regions"), \
        "missing compute_ocr_regions (ARCH 1.5 region-targeted OCR)"
    assert callable(C.compute_ocr_regions)


def test_compute_ocr_regions_no_uia_covers_region():
    region = [0, 0, 800, 600]
    out = C.compute_ocr_regions(region, [])
    assert isinstance(out, list) and out, "no uia boxes -> must return region(s)"
    union = sum(_area(r) for r in out)
    assert union >= 0.9 * _area(region), "no-uia union should ~cover region"


def test_compute_ocr_regions_full_cover_is_empty():
    region = [0, 0, 800, 600]
    out = C.compute_ocr_regions(region, [[-10, -10, 810, 610]])
    assert out == [] or sum(_area(r) for r in out) <= 0.02 * _area(region), \
        "region fully covered by UIA -> nothing left to OCR"


def test_compute_ocr_regions_partial_cover_excludes_box():
    region = [0, 0, 800, 600]
    box = [0, 0, 800, 300]  # covers the top half
    out = C.compute_ocr_regions(region, [box])
    assert out, "partial cover -> some empty area remains"
    union = sum(_area(r) for r in out)
    assert union < _area(region), "must shrink vs full region"
    for r in out:
        assert not _center_in(r, box), \
            "returned OCR cell center must not fall inside a UIA box"


# --------------------------------------------------------------------------- #
# Gap 2 — black-screen auto-retry                                             #
# --------------------------------------------------------------------------- #
def _black(w, h):
    return b"\x00" * (w * h * 3)


def _white(w, h):
    return b"\xff" * (w * h * 3)


def test_capture_with_retry_exists():
    assert hasattr(C, "capture_with_retry"), \
        "missing capture_with_retry (ARCH 1.3 black-screen auto-retry)"
    assert callable(C.capture_with_retry)


def test_capture_with_retry_reshoots_on_black():
    w, h = 16, 16
    seq = [(_black(w, h), w, h, "gdi"), (_white(w, h), w, h, "mss")]
    calls = {"n": 0}

    def grab():
        r = seq[min(calls["n"], len(seq) - 1)]
        calls["n"] += 1
        return r

    res = C.capture_with_retry(grab, max_attempts=3, black_threshold=0.98)
    assert isinstance(res, dict)
    assert res["attempts"] == 2, "should re-shoot exactly once past the black grab"
    assert res["blackness"] <= 0.02, "final grab must be the non-black one"


def test_capture_with_retry_no_retry_when_clean():
    w, h = 16, 16
    calls = {"n": 0}

    def grab():
        calls["n"] += 1
        return (_white(w, h), w, h, "mss")

    res = C.capture_with_retry(grab, max_attempts=3, black_threshold=0.98)
    assert res["attempts"] == 1, "clean first grab -> no retry"
    assert calls["n"] == 1


def test_capture_with_retry_bounded_when_all_black():
    w, h = 16, 16
    calls = {"n": 0}

    def grab():
        calls["n"] += 1
        return (_black(w, h), w, h, "gdi")

    res = C.capture_with_retry(grab, max_attempts=2, black_threshold=0.98)
    assert res["attempts"] == 2, "must stop at max_attempts even if still black"
    assert calls["n"] == 2, "must not loop past max_attempts"
