# screen-vision, Design Philosophy

> One test governs every change: **does it fix the framing, or just patch a symptom?**

The framing most screen tools get wrong: they treat the screen as an *image* and ask a model to find
things in it. screen-vision treats the screen as a *structured tree the OS already publishes*, and
falls back to the image only where the tree is silent.

## P1, The accessibility tree is the source of truth; vision is the fallback

- **Symptom patch:** screenshot → vision model → "the button is around (x, y)". Flaky: sensitive to
  theme, font, resolution, anti-aliasing, and the model's spatial guess.
- **Root cause:** the OS already knows every control's name, type, state, and exact rectangle via UI
  Automation. That data is model-free and pixel-exact. Ignoring it and re-deriving it from pixels is
  the actual mistake.
- **Decision it produced:** UIA is L2a, the primary path (confidence 1.0). OCR runs **only** where the
  tree lacks text, and any OCR box overlapping a UIA element (IoU > 0.10) is discarded, UIA wins the
  fusion. The heavy icon/grounding vision layer is off by default.

## P2, DPI awareness comes before any pixel exists

- **Symptom patch:** clicks are off, so add a fudge offset. The offset is wrong on the next monitor /
  scale factor.
- **Root cause:** a non-DPI-aware process is *lied to* by Windows, the screenshot is
  stretch-virtualized and UIA rectangles can read `(0,0,0,0)`. Every downstream coordinate is already
  corrupted before you touch it.
- **Decision it produced:** `_common` arms Per-Monitor-V2 **on import**, before any capture/UIA/click,
  with a System/legacy fallback chain. The eval gate asserts a monitor's PNG equals its *physical*
  size, making "DPI awareness actually engaged" a tested invariant, not a hope.

## P3, Never act on a coordinate you cannot verify

- **Symptom patch:** let the model emit raw x/y and click it. Errors compound silently.
- **Root cause:** raw-coordinate grounding has no verification loop; a small spatial error becomes a
  wrong click with no signal.
- **Decision it produced:** the model picks an element by **Set-of-Mark id**, and `click.py`
  re-resolves it, preferring a **coordinate-free** UIA `Invoke`/`Toggle`/`Select` pattern, with a
  physical click only as last resort. The closed-loop test (click "7" twice → display reads "77")
  makes correctness program-checkable.

## P4, Read-only by default; acting is an explicit, dry-run-first opt-in

- **Symptom patch:** one tool that captures *and* clicks, clicking whenever asked.
- **Root cause:** seeing and acting have very different blast radii; conflating them makes every read
  a potential side effect.
- **Decision it produced:** `capture.py` never acts. `click.py` is a separate verb, **dry-run by
  default**, requiring `--confirm` to actuate, and it refuses disabled/offscreen targets. Login /
  payment / 2FA stay with the human.

## P5, Degrade loud, never silent

- **Symptom patch:** swallow a missing backend or a black screenshot and return an empty list, which
  reads as "nothing on screen".
- **Root cause:** a confident-but-wrong empty result is worse than an error; it sends the agent down a
  false path.
- **Decision it produced:** every gap is surfaced, missing libs, ~all-black/occluded capture, locked
  desktop (`no_interactive_desktop`), Wayland, as `warnings[]`/`error` in the JSON. The whole tool
  runs on stdlib so it *can* always produce *something*, and always says what it could not.
