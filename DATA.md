# Private capture storage

[storage.contract.json](storage.contract.json) declares artifact paths and
retention. The existing [CLI and element schema](skills/screen-vision/reference/schema.md)
remains authoritative for capture fields, action validation, and error receipts.

## Storage selection and admission

Discovery uses the fleet_guards companion resolver: `SCREEN_VISION_DATA_DIR`,
then `data/` under `SCREEN_VISION_CONFIG`, then `data/` under a proven sibling
`screen-vision-config` clone. There is no home fallback. Clear inherited DATA_DIR
before switching CONFIG. These selectors choose storage, not a settings registry. Missing
configuration fails before capture; installation can remain uninitialized.

Admission is path-only: no Git or GitHub call runs at capture time, and keeping
DATA out of public repositories is enforced by the commit and push hooks. The
selected directory must exist, be named `data`, and sit outside this tool's
worktree. Each PNG, JSON and exact JSON staging filename must be a declared leaf
in one new directory directly beneath `data/captures/`, with no `.git` component
and no symlink or junction on its path. Mandatory outputs are admitted before
capture; selected OCR and annotation outputs are checked before collection. Only
the two declared JSON staging artifacts are transient. JSON publication rechecks
staging and final destinations before replacement; annotation storage failures
remain errors.

Real screenshots and UI observations belong only in the PRIVATE companion and its
version history.

## Capture artifacts and retention

The default capture creates a new `data/captures/run-<id>/` directory relative to
the companion root:

| Artifact | Retention |
| --- | --- |
| `screen.png` | Keep while the active task or selected final evidence needs the captured frame. |
| `capture.json` | Keep the scope, timestamp, identity, and path receipt with the matching capture. |
| `elements.json` | Keep for current observation/action consumers or selected evidence. |
| `annotated.png` | Optional derived view; remove after inspection unless selected as a deliverable. |
| `ocr-input.png` | Temporary OCR input; remove after OCR and any specific diagnosis finish. |
| `capture.json.tmp`, `elements.json.tmp` | Atomic JSON staging; successful replacement consumes them. Reconcile inactive failures before removal. |

Keep only capture sets supporting current work or explicitly selected final
deliverables. Once the task is accepted and no action, evidence, or diagnosis
depends on a set, its retention ends. A saved observation does not authorize a
future action: the action path still verifies current identity and scope.

`--out-dir` selects one new directory directly beneath `data/captures`. The writer
rejects other DATA roots or output layouts before capture. Supporting an alternate
layout requires a reviewed source and contract change. Failed captures may leave
partial artifacts, so confirm the writer has stopped and inspect the failure receipt before retiring those files. In particular,
`write_json_artifact` creates `<final>.tmp` and then replaces the final JSON. A write or
replacement failure can leave that staging dependency. Do not promote it by hand or
call the capture successful; reconcile it and retry in a new capture directory.

Use skill-smith's shared `storage_contract.py` for `validate`, `check`, `plan`, and
`apply`; do not vendor it here. Contract validation needs no companion. Inventory
and retirement require an initialized PRIVATE companion and a reviewed plan.
These declarations do not implement scheduled cleanup or remove Git history.
