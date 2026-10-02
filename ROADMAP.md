# Roadmap

Current: **v0.1.1**

## v0.1.1 (current)
- Windows-first hybrid pipeline: DPI-aware capture (mss / pure-ctypes GDI fallback) →
  UIA element tree → OCR (winocr / rapidocr) → IoU fusion → Set-of-Mark PNG + element JSON.
- `capture.py` (read-only), `click.py` (opt-in, dry-run-first, UIA-Invoke-preferred), `probe.py`.
- Windows GDI capture and PNG writing use stdlib. Private output verification requires Git and
  authenticated gh; verified actions also require Windows UIA.
- Region OCR subtracts named UIA Text rectangles, crops to the uncovered bounds, and masks
  covered pixels. Full text coverage skips OCR. Capture retries a black frame at most once.
- `tests/run_gate.py` defaults to PNG, effective DPI-contract, IoU, and synthetic OCR checks.
  Explicit `--interactive` adds owned-window identity, PNG dimensions/content, golden UIA and
  closed-loop input checks. Current offline results do not establish a native desktop pass.

## Planned
- **v0.2**, occluded/background-window capture via `windows-capture` (WGC).
- **v0.3**, macOS (atomacos / AXUIElement) and Linux X11 (AT-SPI / pyatspi) native element layers.
- **v0.4**, optional vision backend wiring (OmniParser v2 / grounding VLM) as a user-supplied,
  GPU-gated, off-by-default service (AGPL weights never bundled).
- **Eval**, expand the golden set (Notepad, Settings) and add three-scale DPI (100/125/150%) +
  multi-monitor negative-origin regression once a multi-display host is available.
