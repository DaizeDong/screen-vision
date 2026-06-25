# Changelog

All notable changes to this project are documented here (Keep a Changelog style).

## [0.1.0] - 2026-06-25
### Added
- Initial release: accessibility-first desktop screen-vision skill (Windows-first).
- `capture.py` — DPI-aware screenshot + UIA element tree + OCR + IoU fusion → Set-of-Mark PNG and
  physical-pixel element JSON (read-only by default).
- `click.py` — opt-in, dry-run-by-default click by element id; UIA `Invoke`/`Toggle`/`Select` first,
  ctypes physical click fallback.
- `probe.py` — environment/capability self-check (DPI, monitors, backends).
- `_common.py` — stdlib-only floor: Per-Monitor-V2 arming, pure-ctypes GDI capture, stdlib PNG
  writer, monitor enumeration, ctypes click, capability probe.
- `tests/run_gate.py` — program-judgeable eval gate (8 checks; closed-loop click verified on
  Calculator: "7"×2 → display "77").
- Bilingual philosophy-first docs; reference shards `schema.md` + `backends.md`.
