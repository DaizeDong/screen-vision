# Contributing to screen-vision

Keep changes focused on desktop capture, structured element observation and explicitly requested actions.

## Before you change anything

Read [PHILOSOPHY.md](PHILOSOPHY.md). Preserve accessibility-first observation,
effective DPI checks, verified actions, read-only defaults and explicit unavailable
results.

## Conventions

- **Coordinates are physical pixels** everywhere; carry `{monitor, scale, origin}` metadata.
- Real runtime artifacts belong in a private versioned companion. The public repository
  contains only source; gitignore is not a data boundary.
- New backends are **optional and probed**, the stdlib floor must keep working with zero installs.
- Keep `SKILL.md` thin; push detail into `skills/screen-vision/reference/*.md`.
- Stdlib-only for the core (`_common.py`); third-party libs are import-guarded and degrade gracefully.

## PRs

Small, focused, with the gate output pasted in. License is MIT; by contributing you agree your work is
released under it.
