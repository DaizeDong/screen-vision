# screen-vision

Capture a desktop window and read UI elements with physical-pixel coordinates through accessibility data and OCR. Verified actions are optional.

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accessibility-first](https://img.shields.io/badge/Reads-UIA%20%2B%20OCR-green?style=flat)](skills/screen-vision/reference/backends.md)
[![Read-only default](https://img.shields.io/badge/Click-opt--in%20%2F%20dry--run-green?style=flat)](skills/screen-vision/reference/schema.md)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#languages)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.1-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## Design Philosophy

The accessibility tree exposes names, states and geometry for controls that participate in
Windows UI Automation. Reading that structure avoids estimating those properties from pixels.
OCR fills the uncovered text regions; it does not turn an OCR box into verified action authority.
Custom-drawn controls and incomplete accessibility trees remain explicit limits.

Coordinates are useful only in the right context. The tool verifies effective DPI awareness,
records the owning process and window, and re-resolves the saved UIA identity before an action.
This can require a new capture after a layout change or after the capture expires. Refusing a
stale target is preferable to applying an action to a different control.

Capture and action are separate commands. Capture first verifies a PRIVATE destination because
screen pixels can contain personal data; action defaults to a dry run and needs explicit confirmation.
Synthetic checks exercise those decisions. Native input, monitor scaling and platform permissions
require their own desktop acceptance.

[Read the full design philosophy](PHILOSOPHY.md).

## Scope

This CLI skill performs one capture/parse/return invocation without a resident
MCP server. Its three commands are:

- `probe.py`: report DPI, monitor geometry and available backends.
- `capture.py`: write a screenshot and structured elements with physical-pixel
  coordinates, plus optional Set-of-Mark annotation.
- `click.py`: preview or explicitly execute an action by element ID, preferring
  UIA `Invoke` and allowing a verified physical fallback.

Use it for desktop, native, Win32, WinUI, Electron, game and remote-desktop
windows. Use Playwright for web DOM access and image tools for image creation or
editing.

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

## Config

Select an existing PRIVATE companion with `SCREEN_VISION_CONFIG`, or its exact
`data/` directory with `SCREEN_VISION_DATA_DIR`, and authenticate `gh`. Storage
selection is explicit-only: DATA_DIR, CONFIG, then CONFIG_DIR. Clear inherited
DATA_DIR before switching CONFIG. Installation can remain uninitialized.

Capture requires a committed companion, current PRIVATE route proof and declared,
versionable artifact paths. Each run uses a new directory directly beneath
`data/captures/`. [DATA.md](DATA.md) defines initialization, transport restrictions,
source-owned output admission and recovery of failed JSON staging.

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
  user-supplied stub (AGPL weights are not bundled, see [backends](skills/screen-vision/reference/backends.md)).
- Reading an elevated (UAC) window requires running Python elevated too.

## Languages

English (`README.md`, authoritative) · 中文 (`README_CN.md`)

## Roadmap · Contributing · License

See [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE) (MIT).
