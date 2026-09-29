"""Strict private output boundary until the shared guard exposes visibility proof."""
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
import uuid

TOOL_ROOT = Path(__file__).resolve().parents[3]


def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                errors='strict', timeout=20, check=False)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Cannot verify private artifacts: %s unavailable' % args[0]) from exc
    if result.returncode:
        raise RuntimeError('Cannot verify private artifacts: %s failed' % args[0])
    return result.stdout.strip()


def _repository(remote):
    if '://' in remote:
        parsed = urlsplit(remote)
        if parsed.scheme not in ('https', 'ssh') or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError('Unsupported artifact repository origin')
        host, path = parsed.hostname, parsed.path.lstrip('/')
    else:
        match = re.fullmatch(r'(?:[^@/:\s]+@)?([^/:\s]+):([^\s]+)', remote)
        if not match:
            raise RuntimeError('Artifact origin must identify a GitHub repository')
        host, path = match.groups()
    if host != 'github.com':
        if remote.startswith('https://') or not re.fullmatch(r'[A-Za-z0-9_.-]+', host or ''):
            raise RuntimeError('Cannot prove artifact repository visibility')
        config = _run(['ssh', '-G', host])
        hosts = [line.split(None, 1)[1].lower() for line in config.splitlines()
                 if line.lower().startswith('hostname ')]
        if hosts != ['github.com']:
            raise RuntimeError('Artifact SSH alias must resolve to github.com')
    identity = path.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', identity):
        raise RuntimeError('Artifact origin must identify exactly one owner/repository')
    return identity


def artifact_directory(requested=''):
    """Return a new capture directory in an explicitly configured PRIVATE worktree."""
    data = os.environ.get('SCREEN_VISION_DATA_DIR')
    config = os.environ.get('SCREEN_VISION_CONFIG') or os.environ.get('SCREEN_VISION_CONFIG_DIR')
    if not data and not config:
        raise RuntimeError('Uninitialized: set SCREEN_VISION_CONFIG to a PRIVATE companion clone, '
                           'create its data directory, and authenticate gh to verify visibility.')
    base = Path(data).expanduser() if data else Path(config).expanduser() / 'data'
    if not base.is_dir():
        raise RuntimeError('Configured private data directory does not exist; initialize the companion first.')
    base = base.resolve()
    if base.is_relative_to(TOOL_ROOT) or TOOL_ROOT.is_relative_to(base):
        raise RuntimeError('Artifacts must be outside the tool worktree.')
    candidate = Path(requested).expanduser() if requested else base / 'captures' / ('run-' + uuid.uuid4().hex)
    if requested and not candidate.is_absolute():
        candidate = base / candidate
    if any(part.lower() == '.git' or ':' in part or part.endswith((' ', '.'))
           for part in candidate.parts[1:]):
        raise RuntimeError('Artifact path contains reserved or ambiguous components.')
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        raise RuntimeError('Artifact path must stay within the configured private data directory.')
    existing = candidate
    while not existing.exists():
        existing = existing.parent
    repo = Path(_run(['git', '-C', str(existing), 'rev-parse', '--show-toplevel'])).resolve()
    if not base.is_relative_to(repo) or repo.is_relative_to(TOOL_ROOT) or TOOL_ROOT.is_relative_to(repo):
        raise RuntimeError('Artifacts require a separate versioned private companion.')
    remote = _run(['git', '-C', str(repo), 'config', '--get', 'remote.origin.url'])
    identity = _repository(remote)
    private = _run(['gh', 'api', '--hostname', 'github.com', 'repos/' + identity, '--jq', '.private'])
    if private != 'true':
        raise RuntimeError('Artifact repository is PUBLIC or visibility is unknown; refusing capture.')
    if any((candidate / name).exists() for name in ('screen.png', 'annotated.png', 'elements.json', 'capture.json')):
        raise RuntimeError('Capture output already exists; choose a new output directory.')
    return candidate
