# Contributing to screen-vision

Thanks for your interest. screen-vision is small on purpose — one job (read the screen, optionally act
on it), three verbs.

## Before you change anything

Read [PHILOSOPHY.md](PHILOSOPHY.md). A change is only accepted if it fits the five principles —
especially: **UIA before vision (P1)**, **DPI awareness before pixels (P2)**, **verifiable clicks
(P3)**, **read-only default (P4)**, **degrade loud (P5)**. A "feature" that violates one of these is a
regression, not a contribution.

## The bar: prove it, don't assert it

Every change must keep the eval gate green:

```bash
python tests/run_gate.py        # 8 program-judgeable checks (SKIP is allowed, FAIL is not)
```

If you add a capability, add a program-judgeable check for it (golden assertion, closed-loop, or
synthetic fixture). "It looks right" is not acceptance — a passing check is.

## Conventions

- **Coordinates are physical pixels** everywhere; carry `{monitor, scale, origin}` metadata.
- **No secrets, ever** — nothing is printed or committed; runtime artifacts are gitignored.
- New backends are **optional and probed** — the stdlib floor must keep working with zero installs.
- Keep `SKILL.md` thin; push detail into `skills/screen-vision/reference/*.md`.
- Stdlib-only for the core (`_common.py`); third-party libs are import-guarded and degrade gracefully.

## PRs

Small, focused, with the gate output pasted in. License is MIT; by contributing you agree your work is
released under it.
