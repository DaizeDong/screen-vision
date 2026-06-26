# Roadmap

Current: **v0.1.1**

## v0.1.0 (current)
- Windows-first hybrid pipeline: DPI-aware capture (mss / pure-ctypes GDI fallback) →
  UIA element tree → OCR (winocr / rapidocr) → IoU fusion → Set-of-Mark PNG + element JSON.
- `capture.py` (read-only), `click.py` (opt-in, dry-run-first, UIA-Invoke-preferred), `probe.py`.
- Stdlib-only floor: full-screen PNG (stdlib writer) + physical click with zero pip installs.
- Program-judgeable eval gate (`tests/run_gate.py`): PNG, DPI proof, capture resolution/black,
  IoU math, golden UIA (Calculator), closed-loop click, synthetic-image OCR.

## Planned
- **v0.2** — region-targeted OCR (run OCR only on UIA-empty sub-regions, not the whole frame);
  occluded/background-window capture via `windows-capture` (WGC) with a black-screen auto-retry.
- **v0.3** — macOS (atomacos / AXUIElement) and Linux X11 (AT-SPI / pyatspi) native element layers.
- **v0.4** — optional vision backend wiring (OmniParser v2 / grounding VLM) as a user-supplied,
  GPU-gated, off-by-default service (AGPL weights never bundled).
- **Eval** — expand the golden set (Notepad, Settings) and add three-scale DPI (100/125/150%) +
  multi-monitor negative-origin regression once a multi-display host is available.
