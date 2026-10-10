"""Explicit-only capture storage selection with strict private publication proof."""
import os
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

TOOL_ROOT = Path(__file__).resolve().parents[3]

ARTIFACT_IDS = {
    'screen.png': 'capture_frames', 'capture.json': 'capture_manifests',
    'elements.json': 'observed_elements', 'annotated.png': 'annotated_frames',
    'ocr-input.png': 'ocr_working_frames', 'capture.json.tmp': 'capture_json_staging',
    'elements.json.tmp': 'elements_json_staging',
}


def _storage_module():
    path = TOOL_ROOT / 'guards/tools/storage_contract.py'
    try:
        spec = importlib.util.spec_from_file_location('screen_capture_storage_contract', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, AttributeError) as exc:
        raise RuntimeError('Initialize pinned guards artifact admission before capture.') from exc


def _github_private(identity):
    """Live PRIVATE answer for OWNER/NAME, independent of the ACTIVE gh account.

    A plain `gh api repos/OWNER/NAME` asks only with whichever account `gh auth switch` last
    selected, so an active account that cannot see the companion refused every capture. The
    pinned guards kit asks with the owner's stored account, then every other stored account, then
    gh's default, and refuses only when none can see it. Returns 'true' only for PRIVATE."""
    path = TOOL_ROOT / 'guards/tools/data_boundary.py'
    try:
        spec = importlib.util.spec_from_file_location('screen_capture_visibility_boundary', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as exc:
        raise RuntimeError('Initialize pinned guards visibility query before capture.') from exc
    ask = getattr(module, 'query_github_visibility', None)
    if not callable(ask):
        raise RuntimeError('Guards dependency lacks the account-independent visibility API')
    try:
        visibility = ask(identity)
    except module.GitError as exc:
        raise RuntimeError('Cannot verify private artifacts: no gh credential can see the companion') from exc
    return 'true' if visibility == 'PRIVATE' else 'false'


def authorize_capture_artifact(requested):
    """Admit only this producer's concrete capture leaves, preserving lexical paths."""
    path = Path(requested).expanduser().absolute()
    identifier = ARTIFACT_IDS.get(path.name)
    if identifier is None or len(path.parents) < 4:
        raise RuntimeError('Undeclared capture artifact filename.')
    root = path.parents[3]
    try:
        return _storage_module().authorize_artifact_write(
            TOOL_ROOT, root, path.relative_to(root).as_posix(), artifact_id=identifier).path
    except (OSError, RuntimeError, ValueError, AttributeError) as exc:
        raise RuntimeError('Capture artifact admission refused: ' + str(exc)) from exc


def _run(args):
    env = {name: value for name, value in os.environ.items()
           if name.casefold() not in {'git_pager', 'gh_pager', 'pager'}}
    env['GIT_OPTIONAL_LOCKS'] = '0'
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                errors='strict', timeout=20, check=False,
                                env=env)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Cannot verify private artifacts: %s unavailable' % args[0]) from exc
    if result.returncode:
        raise RuntimeError('Cannot verify private artifacts: %s failed' % args[0])
    return result.stdout.rstrip("\r\n")



_HTTPS_PERFORMANCE_KEYS = {
    "version", "maxrequests", "minsessions", "postbuffer", "lowspeedlimit",
    "lowspeedtime", "keepaliveidle", "keepaliveinterval", "keepalivecount",
}
_HTTPS_PERFORMANCE_ENV = {"git_http_low_speed_limit", "git_http_low_speed_time"}


def _verify_https_environment():
    """Refuse known overrides before HTTPS transport or visibility proof."""
    for name in os.environ:
        key = name.casefold()
        if (key in {"http_proxy", "https_proxy", "all_proxy", "curl_ca_bundle",
                    "ssl_cert_file", "ssl_cert_dir", "curl_ssl_backend", "git_exec_path"}
                or key.startswith(("git_ssl_", "git_proxy_ssl_"))
                or (key.startswith("git_http_") and key not in _HTTPS_PERFORMANCE_ENV)):
            raise RuntimeError("Companion HTTPS transport has an unproved environment override")


def _verify_https_transport(config_entries):
    """Refuse unproved Git HTTPS settings, including every URL-scoped occurrence."""
    _verify_https_environment()
    # Keep every occurrence: an empty final value cannot erase an earlier override.
    for key, value in config_entries:
        key = key.casefold()
        option = key.rsplit(".", 1)[-1]
        if key.startswith("remote.") and option.startswith("proxy"):
            raise RuntimeError("Companion HTTPS transport has an unproved remote proxy")
        if not key.startswith("http."):
            continue
        if option in _HTTPS_PERFORMANCE_KEYS:
            continue
        if option == "sslverify" and value is not None and value.strip().casefold() in {"true", "yes", "on", "1"}:
            continue
        raise RuntimeError("Companion HTTPS transport has an unproved HTTP configuration override")


def _repository(remote):
    """Only canonical GitHub HTTPS transport is currently proved."""
    if (not isinstance(remote, str) or any(c.isspace() for c in remote)
            or '\\' in remote):
        raise RuntimeError('Artifact origin has an unproved URL form')
    try:
        parsed = urlsplit(remote)
        allowed = (parsed.scheme == 'https' and parsed.hostname == 'github.com'
                   and parsed.port in (None, 443) and parsed.username is None
                   and parsed.password is None and not parsed.query and not parsed.fragment)
    except ValueError:
        allowed = False
    if not allowed:
        raise RuntimeError('Artifact transport is unproved; initialize a PRIVATE companion with '
                           'https://github.com/OWNER/REPOSITORY.git. SSH is not currently verified.')
    identity = parsed.path.removeprefix('/').removesuffix('.git')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', identity)
            or any(part in ('.', '..') for part in identity.split('/'))):
        raise RuntimeError('Artifact origin must identify exactly one owner/repository')
    return identity


def _check_environment():
    _verify_https_environment()
    allowed_git = {'git_optional_locks', 'git_pager'} | _HTTPS_PERFORMANCE_ENV
    for name in os.environ:
        key = name.casefold()
        if ((key.startswith('git_') and key not in allowed_git)
                or key in {'gh_host', 'gh_config_dir'}):
            raise RuntimeError('Artifact validation has an unproved command environment override')


def _verify_repository(repo):
    """Prove every configured and effective fetch/push destination before capture."""
    raw = _run(['git', '-C', str(repo), 'config', '--null', '--list'])
    if not raw.endswith('\0'):
        raise RuntimeError('Cannot verify private artifacts: malformed Git configuration')
    entries = []
    remotes = set()
    selectors = []
    identities = set()
    for record in raw[:-1].split('\0'):
        key, separator, value = record.partition('\n')
        if not key:
            raise RuntimeError('Cannot verify private artifacts: malformed Git configuration')
        entries.append((key, value if separator else None))
        lower = key.casefold()
        option = lower.rsplit('.', 1)[-1]
        if ((lower.startswith('url.') and option in {'insteadof', 'pushinsteadof'})
                or lower in {'core.sshcommand', 'core.gitproxy'}
                or (lower.startswith('remote.') and option in {'receivepack', 'uploadpack', 'vcs'})):
            raise RuntimeError('Artifact Git transport has an unproved configuration override')
        if (lower == 'remote.pushdefault'
                or (lower.startswith('branch.') and option in {'remote', 'pushremote'})):
            selectors.append(value)
            continue
        if lower.startswith('remote.'):
            name = key[7:].rsplit('.', 1)[0]
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                raise RuntimeError('Artifact remote name cannot be verified')
            remotes.add(name)
            if option in {'url', 'pushurl'}:
                identities.add(_repository(value))
    _verify_https_transport(entries)
    if 'origin' not in remotes:
        raise RuntimeError('Artifact repository requires a verified origin')
    if any(selected not in remotes for selected in selectors):
        raise RuntimeError('Artifact publication selector must name a verified configured remote')
    for remote in sorted(remotes):
        for direction in ([], ['--push']):
            effective = _run(['git', '-C', str(repo), 'remote', 'get-url', *direction, '--all', remote])
            urls = effective.splitlines()
            if not urls:
                raise RuntimeError('Artifact effective destination is missing')
            for url in urls:
                identities.add(_repository(url))
    for identity in sorted(identities):
        _verify_https_environment()
        if _github_private(identity) != 'true':
            raise RuntimeError('Artifact repository is PUBLIC or visibility is unknown; refusing capture.')


def artifact_directory(requested=''):
    """Return a new capture directory in an explicitly configured PRIVATE worktree."""
    _check_environment()
    data = os.environ.get('SCREEN_VISION_DATA_DIR')
    config = os.environ.get('SCREEN_VISION_CONFIG') or os.environ.get('SCREEN_VISION_CONFIG_DIR')
    if not data and not config:
        raise RuntimeError('Uninitialized: set SCREEN_VISION_CONFIG to a PRIVATE companion clone, '
                           'create its data directory, and authenticate gh to verify visibility.')
    base = Path(data).expanduser() if data else Path(config).expanduser() / 'data'
    if not base.is_dir():
        raise RuntimeError('Configured private data directory does not exist; initialize the companion first.')
    storage = _storage_module()
    try:
        storage.no_links(base)
    except ValueError as exc:
        raise RuntimeError('Capture storage topology refused: ' + str(exc)) from exc
    base = base.absolute()
    if base.is_relative_to(TOOL_ROOT) or TOOL_ROOT.is_relative_to(base):
        raise RuntimeError('Artifacts must be outside the tool worktree.')
    candidate = Path(requested).expanduser() if requested else base / 'captures' / ('run-' + uuid.uuid4().hex)
    if requested and not candidate.is_absolute():
        candidate = base / candidate
    if any(part.lower() == '.git' or ':' in part or part.endswith((' ', '.'))
           for part in candidate.parts[1:]):
        raise RuntimeError('Artifact path contains reserved or ambiguous components.')
    try:
        storage.no_links(candidate, allow_missing=True)
    except ValueError as exc:
        raise RuntimeError('Capture storage topology refused: ' + str(exc)) from exc
    candidate = candidate.absolute()
    if not candidate.is_relative_to(base):
        raise RuntimeError('Artifact path must stay within the configured private data directory.')
    if candidate.parent != base / 'captures':
        raise RuntimeError('Capture output must be one new directory directly beneath data/captures/.')
    existing = candidate
    while not existing.exists():
        existing = existing.parent
    repo = Path(_run(['git', '-C', str(existing), 'rev-parse', '--show-toplevel'])).resolve()
    if not base.is_relative_to(repo) or repo.is_relative_to(TOOL_ROOT) or TOOL_ROOT.is_relative_to(repo):
        raise RuntimeError('Artifacts require a separate versioned private companion.')
    if base != repo / 'data':
        raise RuntimeError('Capture storage must use the companion data/ directory declared by the tool.')
    _verify_repository(repo)
    if os.path.lexists(candidate):
        raise RuntimeError('Capture output directory already exists; choose a new output directory.')
    for name in ('screen.png', 'capture.json', 'elements.json', 'capture.json.tmp', 'elements.json.tmp'):
        authorize_capture_artifact(candidate / name)
    return candidate
