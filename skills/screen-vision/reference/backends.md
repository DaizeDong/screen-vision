# Backends, install, and platform caveats

screen-vision runs on **stdlib alone** (pure-ctypes GDI capture + a stdlib PNG writer + ctypes click),
and gets sharper as optional backends are added. `probe.py` tells you what is present.

## Install (pick what you need)

```bash
# Recommended core (structured elements + fast capture + annotation)
pip install uiautomation mss pillow

# OCR (text the accessibility tree does not expose) — choose one:
pip install winocr                 # Windows-native, no model download, word-level boxes
pip install rapidocr-onnxruntime   # cross-platform, offline, high accuracy (pulls onnxruntime+opencv)

# Optional: better capture of occluded / hardware-accelerated windows
pip install windows-capture        # WGC; Windows 11 recommended
```

Nothing is mandatory: with zero installs you still get a full-screen PNG + physical click; UIA/OCR/
annotation simply report as unavailable in `warnings[]`.

## Layer → backend map

| Layer | Default backend | Fallback | Notes |
|---|---|---|---|
| L1 capture | `mss` | pure-ctypes GDI BitBlt | GDI works with zero deps on Windows; mss is faster + cross-platform |
| L1 occluded window | `windows-capture` (WGC) | PrintWindow / BitBlt | not bundled; add only if you must read background/GPU windows |
| L2a elements | `uiautomation` (Apache-2.0) | none | the main path; window-scoped, depth-limited, 12s time budget |
| L2b OCR | `winocr` (Win) / `rapidocr-onnxruntime` | none | run only where UIA lacks text; engine `auto` picks per platform |
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
  (`--target window:...`), then descend with `--max-depth`. The walker prunes offscreen subtrees and
  has a hard 12s budget.
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
  (roadmap). Needs Screen-Recording + Accessibility permission per binary.
- **Linux X11**, capture + RapidOCR work; AT-SPI (`pyatspi`) not yet wired.
- Non-Windows monitor rectangles are read from MSS, including negative origins and multiple
  monitors. Unavailable or invalid geometry stops capture. `scale_source=capture_pixel_units`
  denotes capture-pixel units, not a measured native UI scaling factor.
- **Linux Wayland**, silent capture is blocked by design; `probe.py` flags it and capture warns.
