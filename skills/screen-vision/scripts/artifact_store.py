"""Explicit-only capture storage selection with path-only destination checks.

No Git or GitHub call runs at capture time. The configured companion data directory must
exist and sit outside this tool's worktree; every capture artifact must be a declared leaf in
one new directory directly beneath data/captures/, with no `.git` component and no symlink or
junction on its path. Keeping DATA out of public repositories is enforced at commit and push
time by the hooks.
"""
import os
from functools import lru_cache
from pathlib import Path
import uuid

TOOL_ROOT = Path(__file__).resolve().parents[3]

ARTIFACT_NAMES = frozenset({
    'screen.png', 'capture.json', 'elements.json', 'annotated.png', 'ocr-input.png',
    'capture.json.tmp', 'elements.json.tmp',
})


@lru_cache(maxsize=None)
def _path_rules():
    """The fleet_guards storage_contract module, loaded once per process."""
    try:
        from fleet_guards.runtime import storage_contract
    except ImportError as exc:
        raise RuntimeError('fleet_guards is not installed; run: pip install -e "$(git config --get fleet.guards)"') from exc
    return storage_contract()


def _no_links(path, *, allow_missing=False):
    """Refuse a symlink or junction anywhere on the lexical path (fleet_guards helper)."""
    module = _path_rules()
    try:
        return module.no_links(path, allow_missing=allow_missing)
    except ValueError as exc:
        raise RuntimeError('Capture storage topology refused: ' + str(exc)) from exc


def _reserved(path):
    return any(part.lower() == '.git' or ':' in part or part.endswith((' ', '.'))
               for part in Path(path).parts[1:])


def _strip_verbatim(text):
    r"""Drop a leading \\?\ (or \\?\UNC\) prefix; no further alias handling is attempted."""
    if text[:8].upper() == '\\\\?\\UNC\\':
        return '\\\\' + text[8:]
    if text.startswith('\\\\?\\'):
        return text[4:]
    return text


def _canonical(path):
    """Resolved, case-normalised form, so 8.3 short names and '..' forms compare as their target."""
    resolved = _strip_verbatim(os.path.realpath(_strip_verbatim(os.fspath(path))))
    return Path(os.path.normcase(resolved))


def _overlaps_tool_root(base):
    """True when base and the tool tree contain one another, lexically or after resolution."""
    if base.is_relative_to(TOOL_ROOT) or TOOL_ROOT.is_relative_to(base):
        return True
    real_base, real_root = _canonical(base), _canonical(TOOL_ROOT)
    return real_base.is_relative_to(real_root) or real_root.is_relative_to(real_base)


def _data_base():
    """The companion data directory from the shared resolver; raises with init guidance when missing."""
    try:
        from fleet_guards.runtime import companion_resolver
    except ImportError as exc:
        raise RuntimeError('fleet_guards is not installed; run: pip install -e "$(git config --get fleet.guards)"') from exc
    try:
        root = companion_resolver(source_root=TOOL_ROOT).resolve_data_dir('screen-vision', create=False)
    except Exception as exc:
        raise RuntimeError('Capture storage refused: ' + str(exc)) from exc
    if root is None:
        raise RuntimeError('Uninitialized: set SCREEN_VISION_CONFIG to a private companion clone '
                           'and create its data directory (see DATA.md).')
    base = Path(root)
    _no_links(base)
    base = base.absolute()
    if _reserved(base):
        raise RuntimeError('Artifact path contains reserved or ambiguous components.')
    if base.name != 'data':
        raise RuntimeError('Capture storage must use the companion data/ directory declared by the tool.')
    if _overlaps_tool_root(base):
        raise RuntimeError('Artifacts must be outside the tool worktree.')
    return base


def authorize_capture_artifact(requested, base=None):
    """Admit only this producer's declared capture leaves. Path-only; preserves lexical paths.

    `base` is the data directory a caller already checked with `_data_base()`; without it the
    base is checked here.
    """
    path = Path(requested).expanduser().absolute()
    if path.name not in ARTIFACT_NAMES:
        raise RuntimeError('Undeclared capture artifact filename.')
    base = base or _data_base()
    if _reserved(path):
        raise RuntimeError('Artifact path contains reserved or ambiguous components.')
    if path.parent.parent != base / 'captures':
        raise RuntimeError('Capture artifacts must sit in one directory directly beneath data/captures/.')
    _no_links(path, allow_missing=True)
    return path


def artifact_directory(requested=''):
    """Return a new capture directory beneath the configured companion's data/captures/."""
    base = _data_base()
    candidate = Path(requested).expanduser() if requested else base / 'captures' / ('run-' + uuid.uuid4().hex)
    if requested and not candidate.is_absolute():
        candidate = base / candidate
    if _reserved(candidate):
        raise RuntimeError('Artifact path contains reserved or ambiguous components.')
    _no_links(candidate, allow_missing=True)
    candidate = candidate.absolute()
    if not candidate.is_relative_to(base):
        raise RuntimeError('Artifact path must stay within the configured private data directory.')
    if candidate.parent != base / 'captures':
        raise RuntimeError('Capture output must be one new directory directly beneath data/captures/.')
    if os.path.lexists(candidate):
        raise RuntimeError('Capture output directory already exists; choose a new output directory.')
    for name in ('screen.png', 'capture.json', 'elements.json', 'capture.json.tmp', 'elements.json.tmp'):
        authorize_capture_artifact(candidate / name, base)
    return candidate
