# screen-vision

Screenshot any desktop window and get its buttons + text as pixel-accurate, clickable JSON, accessibility-first, vision as fallback.

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accessibility-first](https://img.shields.io/badge/Reads-UIA%20%2B%20OCR-green?style=flat)](skills/screen-vision/reference/backends.md)
[![Read-only default](https://img.shields.io/badge/Click-opt--in%20%2F%20dry--run-green?style=flat)](skills/screen-vision/reference/schema.md)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#languages)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.1-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## ⭐ Read this first, the design philosophy

Most "let the agent see the screen" tools start from a screenshot and ask a vision model "where is the
button?". That is backwards. The operating system already exposes a **structured accessibility tree**
(UI Automation) where every control's name, type, state, and exact rectangle are facts, no model, no
guessing, no anti-aliasing or DPI ambiguity. So screen-vision is built on one principle:

> **Read the accessibility tree first; use vision (OCR / icon models) only to fill its gaps; and never
> act on a coordinate you cannot verify.**

Three decisions follow directly from that, and they are why this is reliable where pixel-matching tools
are flaky:

1. **UIA is the source of truth, vision is the fallback.** Structured elements come back with
   confidence 1.0 and an `Invoke` pattern you can trigger *without coordinates at all*. OCR only runs
   where the tree has no text, and overlapping OCR is discarded (UIA wins). This is the same hybrid
   detection Microsoft's UFO² uses.
2. **DPI awareness before anything else.** The single biggest reason screen tools mis-click is a
   non-DPI-aware process: Windows stretch-virtualizes the screenshot and UIA rectangles drift. The
   scripts arm Per-Monitor-V2 *on import*, and the test suite proves it (a 2560×1600 @150% panel must
   yield a 2560×1600 PNG).
3. **Read-only by default; clicking is an explicit, dry-run-first opt-in.** Seeing the screen is safe;
   acting on it is not. Login / payment / 2FA stay with the human.

📜 **[Read the full design philosophy → PHILOSOPHY.md](PHILOSOPHY.md)** (each principle with the
patch-vs-root contrast and the real decision it produced).

---

## What it is (and isn't)

It is a **CLI-script skill** (not an MCP server, capture→parse→return is stateless, so no resident
socket/token cost) that gives an agent three verbs:

- **`probe.py`**, what can this host actually do (DPI, monitors, which backends are installed)?
- **`capture.py`**, screenshot + a structured element list with **physical-pixel** coordinates
  (`screen.png` + Set-of-Mark `annotated.png` + `elements.json`).
- **`click.py`**, optional, dry-run-by-default click on an element by `id` (UIA `Invoke` first,
  physical click only as fallback).

It is **for** desktop / native / Win32 / WinUI / Electron / game / remote-desktop windows, anything
**beyond the browser**.

It is **not for** web pages, those have a live DOM, so route to **Playwright**. It is also not an
image generator/editor (that is `pixel-art` / image tools).

It runs on **stdlib alone** (pure-ctypes screen grab + a stdlib PNG writer + ctypes click) and gets
sharper as you add `uiautomation` (elements), `winocr`/`rapidocr` (OCR), and `Pillow` (annotation).

## Install

```
/plugin install github:DaizeDong/screen-vision
```

Or clone manually:

```bash
git clone https://github.com/DaizeDong/screen-vision.git ~/.claude/plugins/screen-vision
```

Recommended backends (optional, the tool degrades without them):

```bash
pip install uiautomation mss pillow            # elements + fast capture + annotation
pip install winocr                             # OCR (Windows-native), or:
pip install rapidocr-onnxruntime               # OCR (cross-platform)
```

(Maintainer setup: source lives in `CodesClaude/screen-vision`, deployed to
`~/.claude/skills/screen-vision` via a PowerShell junction to `skills/screen-vision`.)

## Quick start

> "Use screen-vision to read the buttons on screen and click Save."

```bash
python skills/screen-vision/scripts/probe.py
python skills/screen-vision/scripts/capture.py --target 'window:Calculator' --clickable-only
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30            # dry-run
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30 --confirm  # actuate
```

## How to invoke

Trigger words: *take a screenshot and read the buttons, what UI elements are on screen, find the X
button and give coordinates, click the OK button in this desktop app, read the screen, GUI automation
beyond the browser.*

## Example output

`capture.py` on Calculator returns (abbreviated):

```json
{"id": 30, "type": "button", "label": "Seven", "automation_id": "num7Button",
 "source": "uia", "center": [337, 1047], "clickable": true, "patterns": ["Invoke"],
 "scale": 1.5, "origin": [0, 0]}
```

`click.py --elements-json <path> --id 30 --confirm` → `{"acted": true, "method": "invoke:Invoke"}` and the display reads `77`
after two clicks, a closed-loop, program-verifiable result (see `tests/run_gate.py`).

## Limitations

- v0.1 is **Windows-first**. macOS/Linux capture + OCR work; their native accessibility layers
  (atomacos / AT-SPI) are not yet wired (capture-only fallback). Wayland blocks silent capture.
- UIA blind spots (Chromium/Electron without `--force-renderer-accessibility`, Qt, Canvas, games)
  need the OCR fallback; the heavy vision backend (OmniParser / grounding VLM) is a deferred,
  user-supplied stub (AGPL weights are not bundled, see `reference/backends.md`).
- Reading an elevated (UAC) window requires running Python elevated too.

## Languages

English (`README.md`, authoritative) · 中文 (`README_CN.md`)

## Roadmap · Contributing · License

See [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE) (MIT).
