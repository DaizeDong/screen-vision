# CLI contract + element JSON schema

The agent-facing contract. All coordinates are **physical pixels**; `center` is already absolute
(screenshot-internal coord + region origin). Act only through a fresh identity check; never send
saved coordinates directly to an input API.

## `capture.py`, read the screen (default read-only)

```
python capture.py [options]
  --target       all | monitor:<idx> | window:"<title substr>" | hwnd:<int> | region:<l,t,w,h>
                 default: all  (whole virtual desktop)
  --layers       uia,ocr,vision   comma list; default uia,ocr  (vision is a no-op stub by default)
  --ocr-engine   auto | winocr | rapidocr   default auto (Windows->winocr, else->rapidocr)
  --max-depth    UIA descent cap; default 50
  --clickable-only   keep only interactive elements
  --out-dir      new artifact dir inside configured private data; relative paths are relative to it
                 default: <private-data>/captures/run-<unique-id>
  --allow-full-screen-fallback  explicitly allow invalid narrow targets to resolve to all
  --annotate     true|false   write Set-of-Mark PNG (needs Pillow); default true
  --summary-n    stdout summary rows (largest-area first); default 30
  --json-stdout  also dump the full element list to stdout (default: only summary + paths)
```

stdout (summary + artifact paths):

```json
{
  "ok": true,
  "backend": "mss|gdi",
  "dpi_awareness": "per_monitor_v2",
  "screenshot": "<abs>/screen.png",
  "annotated": "<abs>/annotated.png | null",
  "elements_json": "<abs>/elements.json",
  "capture_manifest": "<abs>/capture.json",
  "capture": {"schema_version": 2, "captured_at": "Unix seconds",
              "requested_target": "window:<title>", "resolved_target": {"kind": "window"},
              "fallback_used": false},
  "monitor": {"index": 1, "origin": [0,0], "scale": 1.5, "physical_size": [2560,1600]},
  "counts": {"total": 142, "uia": 120, "ocr": 18, "vision": 0, "clickable": 63},
  "warnings": ["..."],
  "elements_summary": [ /* first summary-n elements, schema below */ ]
}
```

`ok:false` cases carry an `error` code: `invalid_target`, `target_not_found`,
`artifact_store_unavailable`, `dpi_awareness_unverified`, `capture_failed`, or
`no_interactive_desktop` (locked / Session-0).
Invalid narrow targets do not take a screenshot. A vanished or changed window fails capture even
when full-screen fallback was allowed at initial target resolution. Black/occluded
captures still return `ok:true` but with a `capture: image is ~NN% black ...` warning, never a silent
blank.

## Element JSON schema (each element)

```json
{
  "id": 30,
  "type": "button|text|edit|menuitem|checkbox|list|pane|window|...",
  "label": "Seven",
  "name": "Seven",
  "automation_id": "num7Button",
  "class_name": "Button",
  "source": "uia|ocr|vision",
  "bbox": [x, y, w, h],
  "rect": [left, top, right, bottom],
  "center": [cx, cy],
  "enabled": true,
  "offscreen": false,
  "clickable": true,
  "patterns": ["Invoke"],
  "confidence": 1.0,
  "monitor": 1,
  "scale": 1.5,
  "origin": [0, 0],
  "captured_at": "Unix seconds",
  "capture_rect": [left, top, right, bottom],
  "identity": {"runtime_id": ["UIA integers"], "window_runtime_id": ["UIA integers"],
               "window": {"hwnd": "integer", "pid": "integer",
                          "process_started": "Windows creation FILETIME", "rect": [l,t,r,b]}}
}
```

- `identity` is null when strong window/process/UIA identity is unavailable. Such elements are
  readable but cannot authorize an action.
- `source` lets you filter by trust: `uia` (structured, exact, confidence 1.0) > `ocr` (text only,
  engine confidence) > `vision` (optional backend, off by default).
- `ids` are assigned largest-area-first and are stable within a single capture; the Set-of-Mark
  `annotated.png` uses the same ids.
- OCR elements that overlap a UIA element (IoU > 0.10) are dropped in fusion, UIA wins.

## `click.py`, opt-in click

```
python click.py --elements-json <path> --id <N>
  --button left|right|middle     default left
  --double                       double-click
  --dry-run | --confirm          DEFAULT dry-run (preview only)
  --method auto|invoke|coord     default auto: UIA Invoke/Toggle/Select first, physical coord fallback
```

stdout: `{"ok":true,"acted":false,"dry_run":true,"method":"preview","target":{id,label,center,...}}`
On `--confirm`: `method` becomes `invoke:Invoke` (coordinate-free) or `coord` (physical), `acted:true`.
Disabled/offscreen elements are refused. Every method requires unchanged window/process creation
identity, UIA runtime IDs, properties, geometry and scope, and a capture age of 0 to 60 seconds.
Coordinate fallback also requires the current control under the newly computed center to match.
`recapture_required` always means zero dispatch; `action_outcome_unknown` reports `acted:null`
because the provider failed after dispatch began. Never automatically retry that outcome.
Right/middle/double actions use verified coordinates; `--method invoke` rejects these combinations.

## `probe.py`, environment self-check

`{platform, dpi_awareness, is_wayland, admin, interactive_desktop, libs{...}, monitors[...],
capabilities{screenshot, uia_elements, ocr, annotate, click_physical, click_invoke, vision_backend},
notes[...]}`, run it first to know which capabilities the host can actually deliver.
If physical coordinates cannot be verified, the probe returns `ok:false`, `coordinate_error`,
an empty monitor list and disabled capture/action capabilities, with exit code 1.

## First capture and safe checks

Create a PRIVATE companion repository, clone it, create its `data/` directory, set
`SCREEN_VISION_CONFIG` to the clone, and authenticate `gh` with access to it.
`SCREEN_VISION_DATA_DIR` can select another existing directory within that private repository.
Visibility is checked on each capture. `--out-dir` cannot escape the configured data directory
or overwrite an existing capture. `capture.json` preserves resolved scope, timestamp and paths.

`python -m pytest` runs offline checks. Four live desktop-read tests require
`--interactive-desktop`; this is separate from `python tests/run_gate.py --interactive`, which
creates one synthetic native window, exercises it and cleans only its own process. The default
gate is offline. Missing optional capabilities are reported as skipped, never proven.
