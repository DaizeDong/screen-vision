# Contributing to screen-vision

Keep changes focused on desktop capture, structured element observation and explicitly requested actions.

## Before you change anything

Read [PHILOSOPHY.md](PHILOSOPHY.md). Preserve accessibility-first observation,
effective DPI checks, verified actions, read-only defaults and explicit unavailable
results.

## Verification

Every change must keep the eval gate green:

```bash
python -m pytest               # offline suite; live desktop reads require explicit opt-in
python tests/run_gate.py --json # offline gate; skipped capabilities remain unverified
```

If you add a capability, add a program-judgeable check for it (golden assertion, closed-loop, or
synthetic fixture). State which checks ran and distinguish offline results from native desktop evidence.

## Conventions

- **Coordinates are physical pixels** everywhere; carry `{monitor, scale, origin}` metadata.
- Real runtime artifacts belong in a verified PRIVATE versioned companion. The public repository
  contains only source and generated synthetic fixtures; gitignore is not a data boundary.
- New backends are **optional and probed**, the stdlib floor must keep working with zero installs.
- Keep `SKILL.md` thin; push detail into `skills/screen-vision/reference/*.md`.
- Stdlib-only for the core (`_common.py`); third-party libs are import-guarded and degrade gracefully.

## PRs

Small, focused, with the gate output pasted in. License is MIT; by contributing you agree your work is
released under it.
