# CLI contract + element JSON schema

The agent-facing contract. All coordinates are **physical pixels**; `center` is already absolute
(screenshot-internal coord + region origin), so it can be passed straight to a click.

## `capture.py` — read the screen (default read-only)

```
python capture.py [options]
  --target       all | monitor:<idx> | window:"<title substr>" | hwnd:<int> | region:<l,t,w,h>
                 default: all  (whole virtual desktop)
  --layers       uia,ocr,vision   comma list; default uia,ocr  (vision is a no-op stub by default)
  --ocr-engine   auto | winocr | rapidocr   default auto (Windows->winocr, else->rapidocr)
  --max-depth    UIA descent cap; default 50
  --clickable-only   keep only interactive elements
  --out-dir      artifact dir; default: <temp>/screen-vision/run-<timestamp>
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
  "monitor": {"index": 1, "origin": [0,0], "scale": 1.5, "physical_size": [2560,1600]},
  "counts": {"total": 142, "uia": 120, "ocr": 18, "vision": 0, "clickable": 63},
  "warnings": ["..."],
  "elements_summary": [ /* first summary-n elements, schema below */ ]
}
```

`ok:false` cases carry an `error` code: `no_interactive_desktop` (locked / Session-0). Black/occluded
captures still return `ok:true` but with a `capture: image is ~NN% black ...` warning — never a silent
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
  "origin": [0, 0]
}
```

- `source` lets you filter by trust: `uia` (structured, exact, confidence 1.0) > `ocr` (text only,
  engine confidence) > `vision` (optional backend, off by default).
- `ids` are assigned largest-area-first and are stable within a single capture; the Set-of-Mark
  `annotated.png` uses the same ids.
- OCR elements that overlap a UIA element (IoU > 0.10) are dropped in fusion — UIA wins.

## `click.py` — opt-in click

```
python click.py --elements-json <path> --id <N>
  --button left|right|middle     default left
  --double                       double-click
  --dry-run | --confirm          DEFAULT dry-run (preview only)
  --method auto|invoke|coord     default auto: UIA Invoke/Toggle/Select first, physical coord fallback
```

stdout: `{"ok":true,"acted":false,"dry_run":true,"method":"preview","target":{id,label,center,...}}`
On `--confirm`: `method` becomes `invoke:Invoke` (coordinate-free) or `coord` (physical), `acted:true`.
Disabled/offscreen elements are refused with an error rather than mis-clicked.

## `probe.py` — environment self-check

`{platform, dpi_awareness, is_wayland, admin, interactive_desktop, libs{...}, monitors[...],
capabilities{screenshot, uia_elements, ocr, annotate, click_physical, click_invoke, vision_backend},
notes[...]}` — run it first to know which capabilities the host can actually deliver.
