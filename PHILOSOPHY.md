# screen-vision, Design Philosophy

Participating controls publish structured information through accessibility APIs.
The tool reads that information first and uses image processing where the tree
does not provide text. This reduces spatial estimation while retaining explicit
limits for incomplete trees and custom-drawn controls.

## P1, Accessibility data and OCR coverage

UIA provides names, types, states and rectangles. The primary L2a path assigns
confidence 1.0 when availability is verified. Named, visible UIA Text rectangles
define covered pixels: OCR masks them and discards overlapping boxes at IoU > 0.10.
Container names and AutomationIds do not suppress interior OCR. The heavy icon
and grounding vision layer remains off by default. These choices reduce sensitivity
to themes, fonts and model spatial estimates without assuming every control is exposed.

## P2, Verify DPI before using coordinates

Windows can virtualize coordinates for a process without per-monitor DPI awareness,
including stretched screenshots and `(0,0,0,0)` UIA rectangles. A fixed coordinate
offset cannot correct changing monitor scales. `_common` attempts DPI setup on
import and queries effective awareness before coordinates are used. Only verified
per-monitor modes permit Windows capture or actions. Offline checks cover this
decision contract; physical scaling requires an explicit desktop run.

## P3, Re-resolve the target before an action

The caller chooses a Set-of-Mark element ID. `click.py` re-resolves its identity,
prefers coordinate-free UIA `Invoke`/`Toggle`/`Select`, and permits a physical
fallback only after verification. Both paths require fresh Windows UIA identity.
This limits wrong-control actions caused by spatial estimates or stale geometry.
The opt-in closed-loop test invokes its owned fixture twice and checks the display;
offline controls do not establish native input success.

## P4, Separate observation and action

`capture.py` never acts. `click.py` defaults to preview and requires `--confirm`
before dispatch, refusing disabled or offscreen targets. Login, payment and 2FA
remain human operations. Separate commands allow observation without making it
implicitly authorize an input action.

## P5, Report unavailable observations

Missing libraries, mostly black or occluded captures, locked desktops
(`no_interactive_desktop`) and Wayland restrictions appear in JSON warnings or
errors. A failed observation must not be reported as an empty screen. The Windows
capture core uses the standard library; PRIVATE destination proof and verified
actions have additional prerequisites. Missing prerequisites stop the affected
operation with a reason.
