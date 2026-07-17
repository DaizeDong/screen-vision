# Design Brief, screen-vision

> Step-0 research was completed during planning (6 parallel recon tracks: screenshot-apis,
> ui-element-tree, ocr-vision, agent-computer-use, existing-tools-antipatterns, packaging-as-skill).
> The full synthesized architecture is the authoritative source; this brief is the auditable summary.
> Full architecture: `CodesResearch/_skill-builds/09-screen-vision/ARCHITECTURE.md`.

## Best references (match-or-beat)
- **Microsoft UFO² / UI Automation**, hybrid control detection (structured UIA + vision fallback);
  the IoU>10% UIA-wins fusion rule is taken directly from this lineage.
- **OmniParser v2** (Set-of-Mark element list), the dual-output pattern (annotated PNG + element
  JSON, shared numeric ids) and "let the model pick an id, not raw xy".
- **mss / windows-capture (WGC)**, modern capture; **DXcam is stale (2023), do not use**.
- **winocr (Windows.Media.Ocr) / rapidocr-onnxruntime**, fast/native vs cross-platform OCR.

## Frontier ideas to incorporate
- Coordinate-free actuation via UIA `Invoke`/`Toggle`/`Value` patterns (robust to occlusion/scroll/DPI).
- Set-of-Mark grounding (model selects id; script re-resolves the coordinate) over raw-xy grounding.
- Capability probing + graceful degradation so the skill is useful on any host (stdlib floor).

## Anti-patterns to avoid
- Forgetting DPI awareness (the #1 mis-click cause) → arm Per-Monitor-V2 on import, assert it in tests.
- Deep-walking the UIA tree from the desktop root (30 to 95s) → scope to a window, limit depth, time-box.
- Pixel/template matching as the primary path (SikuliX-style; breaks on theme/res/font) → fallback only.
- Bundling OmniParser `icon_detect` weights (AGPL-3.0 copyleft) → user-supplied, off by default.
- Returning an empty list on failure (reads as "nothing on screen") → degrade loud with warnings.

## Proof bar (how we will show it is tested-real)
Program-judgeable (`tests/run_gate.py`, no human): PNG validity; DPI proof (monitor PNG == physical
size); capture non-black + resolution match; IoU fusion math; **golden UIA set** (Calculator: digit-7
button exists, type=button, Invoke pattern, clickable); **closed-loop click** (invoke "7"×2 → display
reads "77"); synthetic-image OCR round-trip. Current status: 8/8 PASS on the build host.

## Scope & focus (one job, <=3 modules)
One job: capture the screen and read/optionally-act on its UI elements, **beyond the browser**.
Three verbs: `capture.py` (read), `click.py` (opt-in act), `probe.py` (self-check) + shared `_common`.
Web DOM → Playwright; image generation → out of scope.
