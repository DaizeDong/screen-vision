# Backends, install, and platform caveats

Windows capture uses pure-ctypes GDI and a stdlib PNG writer. Output verification and verified
actions have the prerequisites below. `probe.py` distinguishes installed backends from operational
capabilities; both physical and pattern-based actions require a ready Windows UIA session.

## Install (pick what you need)

```bash
# Recommended core (structured elements + fast capture + annotation)
pip install uiautomation mss pillow

# OCR (text the accessibility tree does not expose) — choose one:
pip install winocr pillow          # Windows-native OCR plus its required image input dependency
pip install rapidocr-onnxruntime   # cross-platform, offline, high accuracy (pulls onnxruntime+opencv)

```

Windows GDI capture and PNG writing use stdlib, but private artifact validation requires Git and
authenticated `gh`. Actual clicks require fresh Windows UIA identity via `uiautomation`.
OCR and annotation report missing backends in `warnings[]`. Non-Windows capture requires MSS.
WinOCR image input requires Pillow even when annotation is disabled. Importing winocr alone does
not prove Pillow is available. OCR engine auto selects WinOCR only on Windows when both winocr
and PIL can be imported; otherwise it selects the existing RapidOCR path.

## Layer → backend map

| Layer | Default backend | Fallback | Notes |
|---|---|---|---|
| L1 capture | `mss` | pure-ctypes GDI BitBlt | GDI works with zero deps on Windows; mss is faster + cross-platform |
| L1 occluded window | WGC not integrated | current GDI/mss path | installing windows-capture does not enable a WGC backend |
| L2a elements | `uiautomation` (Apache-2.0) | none | the main path; window-scoped, depth-limited, 12s time budget |
| L2b OCR | `winocr` (Win) / `rapidocr-onnxruntime` | none | cropped/masked input excludes named UIA Text rectangles; engine `auto` picks per platform |
| L2c vision | OmniParser / grounding VLM | none | **stub by default**, user-supplied (see AGPL note) |
| annotate | `Pillow` | skipped (JSON still exact) | Set-of-Mark numbered overlay |
| click | UIA `Invoke`/`Toggle`/`Select` | ctypes physical click | pattern path is coordinate-free and most robust |

## DPI (the #1 failure mode)

Import attempts Per-Monitor-V2, then older setters if an API is unavailable or reports failure.
The reported state comes from the effective thread context, or the process query on older Windows.
Physical-coordinate operations require `per_monitor_v2` or `per_monitor`; `system`, `unaware`, and
`unverified` stop capture and actions. Start a fresh process if another library fixed an incompatible
DPI mode. The opt-in desktop tests compare capture dimensions with monitor geometry; offline tests
prove return-value handling and refusal behavior, not actual monitor scaling.

GDI capture checks every acquisition and copy result, restores the previous bitmap before reading,
and requires all requested scanlines. Acquisition, copy, partial-read, and cleanup failures report
`capture_failed`; they cannot produce a successful blank-frame result.

## UIA caveats

- **Never deep-walk from the desktop root**, it can take 30 to 95s. Always scope to a window first
  (`--target window:...`), then descend with `--max-depth`. The walker records each node's own
  offscreen flag and still visits its children. It checks a 12s budget between visits;
  an individual UIA call can take longer.
- **Blind spots** (return an empty/lying tree → use OCR/vision): Chromium/Electron unless launched
  with `--force-renderer-accessibility`, some Qt, Canvas, games, self-drawn DirectUI.
- **Elevated windows**: to read a UAC-elevated app's tree, run Python elevated too, otherwise the
  tree comes back empty (looks like "no elements", isn't).
- Avoid Python 3.7.6 / 3.8.1 (comtypes is broken on exactly those); use ≥ 3.9.

## Optional vision backend (OmniParser / grounding VLM), deferred, AGPL note

The `vision` layer is a documented stub by default. If you wire OmniParser v2 yourself: its
`icon_detect` weights inherit **YOLO's AGPL-3.0** (copyleft), do **not** bundle those weights in a
public/commercial repo; make them user-supplied and keep any API key in an env var (never printed,
never committed). It is also heavy (10 to 35s, GPU), keep it off the fast path.

## Cross-platform status

- **Windows**, first-class (UIA + winocr/rapidocr + GDI/mss).
- **macOS**, best-effort: capture via mss; structured elements (atomacos/AXUIElement) not yet wired
  (roadmap). Readiness checks native Screen Recording permission without prompting, then requires
  usable MSS geometry. X11 variables are irrelevant. Live permission/capture acceptance is pending.
- **Linux X11**, MSS/RapidOCR paths require a display session and live acceptance; AT-SPI is not wired.
- Non-Windows monitor rectangles are read from MSS, including negative origins and multiple
  monitors. Unavailable or invalid geometry stops capture. `scale_source=capture_pixel_units`
  denotes capture-pixel units, not a measured native UI scaling factor.
- **Linux Wayland**, silent capture is blocked by design; `probe.py` flags it and capture warns.
