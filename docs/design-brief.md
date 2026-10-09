# Design Brief, screen-vision

> This brief documents the shipped capture, discovery and verification contracts.
> See [PHILOSOPHY.md](../PHILOSOPHY.md) for the design principles and
> [the schema reference](../skills/screen-vision/reference/schema.md) for output fields.

## Source references
- **Microsoft UFO² / UI Automation**, hybrid control detection (structured UIA + vision fallback);
  the IoU>10% UIA-wins fusion rule is taken directly from this lineage.
- **OmniParser v2** (Set-of-Mark element list), the dual-output pattern (annotated PNG + element
  JSON, shared numeric ids) and "let the model pick an id, not raw xy".
- **mss / windows-capture (WGC)**, modern capture; **DXcam is stale (2023), do not use**.
- **winocr (Windows.Media.Ocr) / rapidocr-onnxruntime**, fast/native vs cross-platform OCR.

## Design choices
- Coordinate-free actuation via UIA `Invoke`/`Toggle`/`Value` patterns (robust to occlusion/scroll/DPI).
- Set-of-Mark grounding (model selects id; script re-resolves the coordinate) over raw-xy grounding.
- Capability probing + graceful degradation so the skill is useful on any host (stdlib floor).

## Anti-patterns to avoid
- Unverified DPI awareness → attempt Per-Monitor-V2 on import and check the effective mode before coordinates are used.
- Deep-walking the UIA tree from the desktop root (30 to 95s) → scope to a window, limit depth, time-box.
- Pixel/template matching as the primary path (SikuliX-style; breaks on theme/res/font) → fallback only.
- Bundling OmniParser `icon_detect` weights (AGPL-3.0 copyleft) → user-supplied, off by default.
- Returning an empty list on failure → preserve the unavailable observation as a warning or error.

## Verification gate and evidence boundary
`tests/run_gate.py` defaults to offline checks: PNG writer validity, the effective Windows DPI
contract, IoU math, and synthetic-image OCR. Missing optional OCR dependencies produce SKIP.

`--interactive` explicitly enables a newly created, uniquely named owned window. Its capture
check verifies HWND/process identity before and after capture, retained scope, persisted PNG
dimensions, and non-black pixels. Every golden and post-action receipt must retain the same
HWND, PID, process creation time and bounds. The gate checks the display after each invocation
and stops before any further action when a receipt, element identity or command fails.

The earlier Calculator/8-of-8 description was historical; it is not a current receipt for this
gate. Offline controls establish decision behavior. Native DPI scaling, capture, UIA and input
require a separately authorized desktop run; no current native pass is claimed here.

## Scope
One job: capture the screen and read/optionally-act on its UI elements, **beyond the browser**.
Three verbs: `capture.py` (read), `click.py` (opt-in act), `probe.py` (self-check) + shared `_common`.
Web DOM → Playwright; image generation → out of scope.
