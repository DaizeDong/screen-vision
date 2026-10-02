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
- **Decision it produced:** UIA is L2a, the primary path (confidence 1.0). Visible, named UIA Text
  rectangles define the covered pixels: the OCR input masks them, and OCR boxes overlapping
  them (IoU > 0.10) are discarded. Container names and AutomationIds do not suppress OCR of
  their interior text. The heavy icon/grounding vision layer is off by default.

## P2, DPI awareness comes before any pixel exists

- **Symptom patch:** clicks are off, so add a fudge offset. The offset is wrong on the next monitor /
  scale factor.
- **Root cause:** a non-DPI-aware process is *lied to* by Windows, the screenshot is
  stretch-virtualized and UIA rectangles can read `(0,0,0,0)`. Every downstream coordinate is already
  corrupted before you touch it.
- **Decision it produced:** `_common` attempts DPI setup on import and queries effective awareness
  before coordinates are used. Only verified per-monitor modes permit Windows capture or actions.
  The offline gate checks that contract. Native scaling needs an explicit desktop run; an inert
  return-value test cannot establish physical monitor behavior.

## P3, Never act on a coordinate you cannot verify

- **Symptom patch:** let the model emit raw x/y and click it. Errors compound silently.
- **Root cause:** raw-coordinate grounding has no verification loop; a small spatial error becomes a
  wrong click with no signal.
- **Decision it produced:** the model picks an element by **Set-of-Mark id**, and `click.py`
  re-resolves it, preferring a **coordinate-free** UIA `Invoke`/`Toggle`/`Select` pattern, with a
  physical click only as last resort. Both paths require fresh Windows UIA identity.
  The opt-in closed-loop test invokes the owned fixture twice and verifies its display; offline
  controls do not establish native input success.

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
  desktop (`no_interactive_desktop`), Wayland, as `warnings[]`/`error` in the JSON. The Windows
  capture core uses stdlib, while private destination proof and verified actions have additional
  prerequisites. Missing prerequisites stop the affected operation with a reported reason.
