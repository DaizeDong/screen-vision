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
   on a cropped, masked image that excludes named UIA Text rectangles. Window/pane names and
   AutomationIds do not establish text coverage; OCR fusion uses the same text rectangles.
   This follows the hybrid
   detection Microsoft's UFO² uses.
2. **DPI awareness before anything else.** The single biggest reason screen tools mis-click is a
   non-DPI-aware process: Windows stretch-virtualizes the screenshot and UIA rectangles drift. The
   scripts attempt Per-Monitor-V2 on import and query effective awareness before using coordinates.
   Unverified, unaware, or system-aware contexts stop capture and actions. Offline tests exercise
   these decisions; actual monitor scaling requires the separately enabled desktop tests.
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

Windows capture has a stdlib GDI/PNG path. Verified actions require fresh Windows UIA identity
through `uiautomation`. WinOCR image OCR requires both `winocr` and `Pillow`; RapidOCR is the
alternative OCR path. `Pillow` also provides annotation.
Capture also needs Git and the authenticated GitHub CLI to verify its private artifact destination.

## Install

```
/plugin install github:DaizeDong/screen-vision
```

Or clone manually:

```bash
git clone --recurse-submodules https://github.com/DaizeDong/screen-vision.git ~/.claude/plugins/screen-vision
```

Recommended backends (optional, the tool degrades without them):

```bash
pip install uiautomation mss pillow            # elements + fast capture + annotation
pip install winocr pillow                      # OCR (Windows-native, Pillow required), or:
pip install rapidocr-onnxruntime               # OCR (cross-platform)
```

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

## Capture output and action validation

Each run writes `screen.png`, optional `annotated.png`, `elements.json`, and `capture.json`.
The manifest records requested and resolved scope, capture time and artifact paths. A generated
[synthetic element example](tests/fixtures/element.json) shows the current identity fields.

Create a PRIVATE companion repository and clone it using
`git clone https://github.com/OWNER/REPOSITORY.git`. Set `SCREEN_VISION_CONFIG` to that clone,
create its `data/` directory, and authenticate `gh` with access to it. Capture checks every
configured and effective fetch/push URL and proves each repository PRIVATE before reading the screen.
Only canonical GitHub HTTPS routes (default port or 443) are currently admitted. SSH is unverified
and refused. URL rewrites, transport overrides, proxies, and alternate TLS trust settings also refuse.
Pager settings (`GIT_PAGER`, `GH_PAGER`, `PAGER`) are accepted and removed from captured subprocess environments.
`--out-dir` selects a new directory within that data root; it cannot overwrite a prior capture.

A narrow target that is invalid or missing returns an error without a screenshot. Scope expands
only with `--allow-full-screen-fallback`, and that choice is recorded in the manifest.
Title discovery must finish successfully for every visible window; incomplete enumeration,
failed title reads or changed titles reject discovery before a match can be selected.

All action methods re-resolve the saved UIA runtime identity inside its owning window and verify
process creation time, element properties and geometry. Captures expire for action after 60 seconds.
Coordinate fallback also checks the current hit target. OCR-only or old records cannot authorize a
click. `recapture_required` means inspect and capture again; `action_outcome_unknown` means inspect
the application result before retrying. Dry-run remains the default and does not touch UIA.

## Verification

`python -m pytest` is safe offline by default. The four real desktop-read checks require the explicit
`--interactive-desktop` option. `python tests/run_gate.py --json` runs offline checks; add
`--interactive` only when ready to open and act on a dedicated synthetic window. The gate cleans
only the child process it created. Every action and outcome is checked against that window's
HWND, PID and process creation time; any failed or mismatched proof stops the gate immediately.
Skipped checks do not prove desktop capability.

## Limitations

- The implementation is **Windows-first**. macOS uses the native Screen Recording permission
  preflight, then MSS geometry; it does not require X11 environment variables. Linux uses display
  session variables and MSS. Native macOS/Linux capture and OCR still require live acceptance.
  Their accessibility layers (atomacos / AT-SPI) are not wired. Wayland can block silent capture.
- UIA blind spots (Chromium/Electron without `--force-renderer-accessibility`, Qt, Canvas, games)
  need the OCR fallback; the heavy vision backend (OmniParser / grounding VLM) is a deferred,
  user-supplied stub (AGPL weights are not bundled, see `reference/backends.md`).
- Reading an elevated (UAC) window requires running Python elevated too.

## Languages

English (`README.md`, authoritative) · 中文 (`README_CN.md`)

## Roadmap · Contributing · License

See [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE) (MIT).
