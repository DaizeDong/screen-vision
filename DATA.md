# Private capture storage

[storage.contract.json](storage.contract.json) declares artifact paths and
retention. The existing [CLI and element schema](skills/screen-vision/reference/schema.md)
remains authoritative for capture fields, action validation, and error receipts.

Set `SCREEN_VISION_CONFIG` to an existing separate PRIVATE companion clone, or
`SCREEN_VISION_DATA_DIR` to its `data` directory. Missing configuration fails before
capture. Installing the tool does not require an empty companion. Real screenshots
and UI observations belong only in the PRIVATE companion and its version history.

The default capture creates a new `data/captures/run-<id>/` directory relative to
the companion root:

| Artifact | Retention |
| --- | --- |
| `screen.png` | Keep while the active task or selected final evidence needs the captured frame. |
| `capture.json` | Keep the scope, timestamp, identity, and path receipt with the matching capture. |
| `elements.json` | Keep for current observation/action consumers or selected evidence. |
| `annotated.png` | Optional derived view; remove after inspection unless selected as a deliverable. |
| `ocr-input.png` | Temporary OCR input; remove after OCR and any specific diagnosis finish. |

Keep only capture sets supporting current work or explicitly selected final
deliverables. Once the task is accepted and no action, evidence, or diagnosis
depends on a set, its retention ends. A saved observation does not authorize a
future action: the action path still verifies current identity and scope.

`--out-dir` can select another new directory inside the private data root. Use one
directory directly beneath `captures`, or declare the alternate layout before use.
The capture writer enforces the private boundary; the shared storage checker checks
the declared layout. Failed captures may leave partial artifacts, so confirm the
writer has stopped and inspect the failure receipt before retiring those files.

Use skill-smith's shared `storage_contract.py` for `validate`, `check`, `plan`, and
`apply`; do not vendor it here. Contract validation needs no companion. Inventory
and retirement require an initialized PRIVATE companion and a reviewed plan.
These declarations do not implement scheduled cleanup or remove Git history.
