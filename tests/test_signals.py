#!/usr/bin/env python3
"""Hermetic, program-judgeable signal tests for screen-vision.

pytest-discoverable mirror of the deterministic subset of ARCHITECTURE.md
section 4 evaluation signals. Unlike tests/run_gate.py (which launches
Calculator and performs real clicks for the full closed-loop proof), this
module is HERMETIC: pure logic + read-only screenshot only — no GUI windows
are opened, no synthetic clicks are issued, no network is touched. This makes
it safe to run repeatedly inside an automated evaluation sandbox (e.g.
self-evolve's A-tier program-adjudication provider) without side effects on the
live desktop.

Each check is a real assertion (not a placeholder). GUI/host-dependent parts
degrade to pytest.skip rather than failing on non-Windows / headless hosts.
"""
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "skills", "screen-vision", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))

import _common as C  # noqa: E402


# --------------------------------------------------------------------------- #
# section 4.x, pure geometry / fusion math (host-independent, always run)     #
# --------------------------------------------------------------------------- #
def test_iou_overlap_above_fusion_threshold():
    # IoU fusion rule (ARCH section 1.7): overlapping boxes must score > 0.10.
    a = [0, 0, 100, 100]
    overlap = [10, 10, 110, 110]
    assert C.iou(a, overlap) > 0.10


def test_iou_disjoint_is_zero():
    assert C.iou([0, 0, 100, 100], [200, 200, 300, 300]) == 0.0


def test_iou_identity_is_one():
    assert abs(C.iou([3, 4, 50, 60], [3, 4, 50, 60]) - 1.0) < 1e-9


def test_blackness_all_black_is_one():
    rgb = bytes([0, 0, 0] * (8 * 8))
    assert C.blackness(rgb, 8, 8) >= 0.99


def test_blackness_all_white_is_zero():
    rgb = bytes([255, 255, 255] * (8 * 8))
    assert C.blackness(rgb, 8, 8) == 0.0


def test_blackness_empty_is_one():
    assert C.blackness(b"", 0, 0) == 1.0


# --------------------------------------------------------------------------- #
# section 4.1, PNG writer correctness (stdlib, host-independent)              #
# --------------------------------------------------------------------------- #
def test_png_writer_header_and_dims(tmp_path):
    w, h = 5, 3
    rgb = bytes([10, 20, 30] * (w * h))
    p = str(tmp_path / "sig.png")
    C.write_png(p, rgb, w, h)
    head = open(p, "rb").read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    gw, gh = struct.unpack(">II", head[16:24])
    assert (gw, gh) == (w, h)


# --------------------------------------------------------------------------- #
# section 1.2 / 4.1, DPI awareness self-arm                                   #
# --------------------------------------------------------------------------- #
def test_dpi_awareness_armed():
    lvl = C.set_dpi_awareness()
    if not C.IS_WINDOWS:
        pytest.skip("non-Windows host")
    assert lvl in ("per_monitor_v2", "per_monitor", "system")


# --------------------------------------------------------------------------- #
# section 1.3 / 4.3, monitor geometry sanity (no GUI; pure win32 metrics)     #
# --------------------------------------------------------------------------- #
def test_enum_monitors_shape():
    mons = C.enum_monitors()
    assert isinstance(mons, list) and len(mons) >= 1
    for m in mons:
        l, t, r, b = m["rect"]
        assert r > l and b > t  # non-degenerate
        assert m["physical_size"] == [r - l, b - t]  # size derived from rect
        assert m["origin"] == [l, t]
        assert m["scale"] > 0


# --------------------------------------------------------------------------- #
# section 4.1, capture resolution match (read-only screenshot; DPI proof)     #
# --------------------------------------------------------------------------- #
def test_capture_resolution_matches_monitor():
    if not C.IS_WINDOWS:
        pytest.skip("non-Windows host")
    m = C.enum_monitors()[0]
    l, t, r, b = m["rect"]
    rgb, w, h, backend = C.capture_region(l, t, r - l, b - t)
    # DPI-aware proof: captured pixel dims == monitor PHYSICAL size.
    assert [w, h] == m["physical_size"], "got %dx%d want %s via %s" % (
        w, h, m["physical_size"], backend)
    # captured bytes form a complete RGB buffer
    assert len(rgb) == w * h * 3


def test_capture_region_not_all_black():
    if not C.IS_WINDOWS:
        pytest.skip("non-Windows host")
    m = C.enum_monitors()[0]
    l, t, r, b = m["rect"]
    rgb, w, h, _ = C.capture_region(l, t, min(256, r - l), min(256, b - t))
    # A live desktop region must not be ~fully black (occlusion/black-screen guard).
    assert C.blackness(rgb, w, h) < 0.98


# --------------------------------------------------------------------------- #
# section 3.2, element JSON schema contract (every field the agent relies on) #
# --------------------------------------------------------------------------- #
REQUIRED_ELEMENT_KEYS = {
    "id", "type", "label", "name", "automation_id", "class_name", "source",
    "bbox", "rect", "center", "enabled", "offscreen", "clickable", "patterns",
    "confidence", "monitor", "scale", "origin",
}


def test_capture_emits_schema_complete_elements():
    """Run capture.py read-only on a tiny region; every emitted element must
    carry the full ARCH section 3.2 schema, source in {uia,ocr,vision}, and a
    center consistent with its rect. No GUI launched, no click issued."""
    import json
    import subprocess

    out = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "capture.py"),
         "--target", "region:0,0,300,200", "--layers", "uia,ocr",
         "--summary-n", "0", "--annotate", "false"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0, "capture.py crashed: %s" % out.stderr[-400:]
    res = json.loads(out.stdout)
    assert res.get("ok") is True
    assert "counts" in res and "elements_json" in res
    els = json.load(open(res["elements_json"], encoding="utf-8"))
    for e in els:
        missing = REQUIRED_ELEMENT_KEYS - set(e.keys())
        assert not missing, "element missing keys %s" % missing
        assert e["source"] in ("uia", "ocr", "vision")
        l, t, r, b = e["rect"]
        cx, cy = e["center"]
        assert l <= cx <= r and t <= cy <= b  # center inside rect


def test_capture_degrades_without_crash_on_empty_region():
    """Robustness (section 4.6): a 1x1 region must still return ok JSON, exit 0,
    never crash, even if no backends find elements."""
    import json
    import subprocess

    out = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "capture.py"),
         "--target", "region:0,0,1,1", "--layers", "uia",
         "--summary-n", "0", "--annotate", "false"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0
    res = json.loads(out.stdout)
    assert res.get("ok") is True
    assert int(res["counts"]["total"]) >= 0


# --------------------------------------------------------------------------- #
# section 4.6, malformed --target must degrade gracefully (never hard-crash)  #
# Regression guard for the audit spec-gap: capture.py self-documents "degrades #
# gracefully, never hard-crashes", but a short/non-numeric region/monitor/hwnd #
# spec used to raise an uncaught ValueError traceback (exit != 0). It must now  #
# fall back to full-screen with a warning and still emit ok JSON, exit 0.      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", [
    "region:1,2,3",        # too few segments
    "region:0,0,0,0",      # zero-size
    "region:0,0,-5,-5",    # negative size
    "region:a,b,c,d",      # non-numeric
    "monitor:abc",         # non-numeric monitor index
    "hwnd:xyz",            # non-numeric window handle
])
def test_capture_malformed_target_degrades_no_crash(spec):
    import json
    import subprocess

    out = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "capture.py"),
         "--target", spec, "--layers", "uia", "--summary-n", "0", "--annotate", "false"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0, "hard-crashed on %r: %s" % (spec, out.stderr[-400:])
    res = json.loads(out.stdout)
    assert res.get("ok") is True, "non-ok result on %r: %s" % (spec, out.stdout[-300:])
    warns = res.get("warnings", [])
    assert any(("malformed" in w) or ("full screen" in w) or ("falling back" in w)
               for w in warns), "expected a graceful-fallback warning, got %s" % warns
