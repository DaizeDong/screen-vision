# Changelog

All notable changes to this project are documented here (Keep a Changelog style).

## [Unreleased]

- Bind concrete runtime writer destinations and transaction files to canonical source artifact admission before creation. Offline regression controls preserve PRIVATE, retention, topology and versioning refusals.


### Storage review threshold
- Set a 64 MiB companion working-data review threshold. Required observations and
  recovery state stay protected when the threshold is exceeded.

### Changed
- Invalid or missing narrow targets now fail without a screenshot by default. Full-screen fallback requires `--allow-full-screen-fallback` and is recorded in the capture manifest. This supersedes the implicit fallback documented for 0.1.1.
- Verify the PRIVATE artifact destination before capture and keep each capture in a new directory.
- Require fresh process, window and UIA identity for every action; expired or changed targets request recapture, and uncertain action outcomes require inspection before retry.
- Verify effective DPI awareness, limit OCR to uncovered text regions, and separate offline checks from explicit interactive desktop acceptance.
- Explain why accessibility data, private capture storage and action validation have different roles.

### Fixed
- Declare both atomic JSON staging paths and inactive failure recovery. Restrict capture layout to data/captures/<run> and document the current explicit-only storage selectors.
- Accept pager settings while removing them from Git and GitHub subprocess environments.
- Keep Chinese setup guidance aligned with private-storage and complete window-title discovery requirements.

## [0.1.1] - 2026-06-25
### Added
- `pure_ops.compute_ocr_regions()`, region-targeted OCR pre-filter (ARCH 1.5): split the captured
  region into UIA-empty sub-rects so OCR never blind-runs over the whole frame.
- `pure_ops.capture_with_retry()`, black-screen auto-retry (ARCH 1.3): re-grab a near-black frame,
  bounded by `max_attempts`.
- `capture.py` now wires both: black-frame re-grab on the L1 path, and OCR is skipped entirely when
  UIA already covers the captured region.
### Fixed
- `capture.py` malformed `--target` (e.g. `region:1,2,3`, `monitor:abc`, `hwnd:xyz`, zero/negative
  region) no longer raises an uncaught `ValueError` traceback; it degrades to full-screen with a
  warning and still emits ok JSON (exit 0), honoring the "never hard-crash" contract.
- Docs: `click.py` quickstart example now includes the required `--elements-json <path>` argument.

## [0.1.0] - 2026-06-25
### Added
- Initial release: accessibility-first desktop screen-vision skill (Windows-first).
- `capture.py`, DPI-aware screenshot + UIA element tree + OCR + IoU fusion → Set-of-Mark PNG and
  physical-pixel element JSON (read-only by default).
- `click.py`, opt-in, dry-run-by-default click by element id; UIA `Invoke`/`Toggle`/`Select` first,
  ctypes physical click fallback.
- `probe.py`, environment/capability self-check (DPI, monitors, backends).
- `_common.py`, stdlib-only floor: Per-Monitor-V2 arming, pure-ctypes GDI capture, stdlib PNG
  writer, monitor enumeration, ctypes click, capability probe.
- `tests/run_gate.py`, program-judgeable eval gate (8 checks; closed-loop click verified on
  Calculator: "7"×2 → display "77").
- Bilingual philosophy-first docs; reference shards `schema.md` + `backends.md`.
