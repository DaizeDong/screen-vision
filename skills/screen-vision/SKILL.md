---
name: screen-vision
description: Screenshot and read on-screen UI elements/buttons with pixel coordinates (accessibility tree + OCR); optional click. For desktop/native/game GUIs beyond the browser.
---

# screen-vision

> Governing principle (full text in the repo's `PHILOSOPHY.md`): **read the accessibility tree first,
> use vision only to fill its gaps, and never act on a coordinate you cannot verify.** Structured UIA
> data is exact and model-free; OCR/vision is the fallback, not the default.

## When to use / when to stop

Use this when an agent needs to *see and act on the desktop* — capture the screen, get a structured
list of buttons/text/inputs with **physical-pixel** coordinates, optionally click one.

- Native apps, Win32/WinUI, Electron, games, remote-desktop, any non-browser window → **here**.
- A web page's DOM/elements → **route to Playwright** (it reads the live DOM directly; this tool would
  only OCR pixels). "beyond the browser" in the description is the boundary.
- Generating pixel art / editing an image file → not this skill (`pixel-art` / image tools).

## Workflow (thin)

1. **Probe once** — `python scripts/probe.py`. It reports DPI awareness, monitors, and which backends
   (UIA / OCR / annotate) are available, so you know what the next step can deliver.
2. **Capture (read-only, the default)** — `python scripts/capture.py --target ...`. Writes
   `screen.png`, an optional Set-of-Mark `annotated.png`, and `elements.json` (full), and prints a
   compact JSON summary + artifact paths to stdout. Read the summary to pick an element by **id**.
3. **Decide from JSON, confirm layout from the annotated PNG** — the JSON carries `center`, `rect`,
   `label`, `clickable`, `patterns`, `source`. Read the JSON to save tokens; only `Read` the annotated
   image when you need to eyeball the layout.
4. **Click (opt-in)** — `python scripts/click.py --elements-json <path> --id <N>`. **Dry-run by
   default** (reports what it *would* click). Add `--confirm` to actuate; it prefers a coordinate-free
   UIA `Invoke`/`Toggle`/`SetValue` and only falls back to a physical click when no pattern exists.

```bash
python scripts/capture.py --target 'window:Calculator' --layers uia,ocr --clickable-only
python scripts/click.py   --elements-json <path> --id 30            # dry-run preview
python scripts/click.py   --elements-json <path> --id 30 --confirm  # actuate (Invoke)
```

Full CLI contract + element JSON schema: **`reference/schema.md`**.
Backend choices, install, platform/DPI caveats: **`reference/backends.md`**.

## Hard rules

1. **DPI awareness is non-negotiable.** Scripts set Per-Monitor-V2 on import, before any
   capture/UIA/click. Never bypass it — without it, screenshots are virtualized-stretched, UIA rects
   can read `(0,0,0,0)`, and clicks drift further the farther from the origin.
2. **Read-only by default; clicking is an explicit, dry-run-first opt-in.** Only login / payment /
   2FA / destructive confirmations go to the human — never auto-click those.
3. **Coordinates are physical pixels** with `{monitor, scale, origin}` metadata. Real screen point =
   element `center` (already absolute). Multi-monitor origins can be negative.
4. **Pick elements by `id`; let the script resolve the coordinate.** Never have the model emit raw
   x/y — use the Set-of-Mark id and let `click.py` re-resolve via UIA.
5. **Degrade loud, never silent.** Missing backend, black/occluded capture, locked desktop, Wayland →
   surfaced as a `warnings[]`/error in the JSON, never a confident-but-wrong result.

## Privacy & safety

Screenshots can capture passwords/tokens. Prefer `--target window:...` or `--target region:...` over
full-screen; artifacts land in a temp run dir and are **gitignored**. No secret is ever printed or
committed.

## Progressive loading

This `SKILL.md` is the only always-loaded file. Load `reference/schema.md` (CLI + JSON contract) or
`reference/backends.md` (libraries, install, platform caveats) on demand — never both preemptively.
