"""The live PRIVATE check must not depend on which gh account is ACTIVE.

A plain `gh api repos/OWNER/NAME --jq .private` asks only with the account `gh auth switch` last
selected. When another session switched it to an account that cannot see the companion, every
capture was refused. The query now goes through the pinned guards kit, which asks every stored gh
account. These tests run the REAL kit against a synthetic gh (the kit's own fixture generator)
whose active account cannot see the repository; nothing here touches the real gh.

The synthetic gh is installed so that a bare `subprocess.run(['gh', ...])` resolves it on every
OS, and it also answers the legacy `gh api repos/OWNER/NAME --jq .private` with the ACTIVE account
only. The previous code therefore fails the call-path tests because it asked only the active
account, not because gh could not be found.
"""
import importlib.util
import io
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/screen-vision/scripts'))
import artifact_store

REPOSITORY = 'example-owner/screen-vision-config'


def _kit_fixtures():
    path = artifact_store.TOOL_ROOT / 'guards/tools/make_fixtures.py'
    spec = importlib.util.spec_from_file_location('_screen_vision_guard_make_fixtures', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Legacy `gh api` answered with the ACTIVE credential only (GH_TOKEN wins, as in real gh); every
# other call goes to the kit's own synthetic gh program unchanged.
_RESOLVABLE_GH = r'''
import json, os, runpy, sys
STATE, PROGRAM = %r, %r
argv = sys.argv[1:]
if argv[:1] != ["api"]:
    sys.argv = [PROGRAM, STATE] + argv
    runpy.run_path(PROGRAM, run_name="__main__")
    sys.exit(0)
with open(STATE, encoding="utf-8") as stream:
    state = json.load(stream)
tokens = {login.casefold(): token for login, token in state["tokens"].items()}
owners = {token: login for login, token in state["tokens"].items()}
explicit = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
credential = explicit or tokens.get(state["active"].casefold())
with open(state["log"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": argv, "credential": owners.get(credential, "unknown") if credential else None,
                          "explicit": bool(explicit), "gh_host": os.environ.get("GH_HOST")}) + "\n")
name = next((arg[len("repos/"):] for arg in argv if arg.startswith("repos/")), "")
if name.casefold() not in {repo.casefold() for repo in state["sees"].get(owners.get(credential, ""), [])}:
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
sys.stdout.write("true\n" if state["visibility"][name.casefold()] in ("PRIVATE", "INTERNAL") else "false\n")
'''


def _resolvable_gh(stub):
    """Install the synthetic gh where a bare `gh` argv resolves it; return that directory.

    The kit's launcher is a .cmd on Windows, which CreateProcess never finds for a bare `gh`
    (it appends only .exe), so the previous code failed there with FileNotFoundError instead of
    the active-account refusal under test. pip's console-script launcher runs the zip appended to
    it with the given interpreter, exactly like any installed entry point."""
    directory = stub['state'].parent / 'gh-resolvable'
    directory.mkdir()
    source = _RESOLVABLE_GH % (str(stub['state']), str(stub['state'].parent / 'gh_stub.py'))
    if os.name == 'nt':
        distlib = importlib.util.find_spec('pip._vendor.distlib')
        assert distlib is not None, 'pip is required to build the synthetic gh.exe'
        name = 't64-arm.exe' if platform.machine().upper() == 'ARM64' else 't64.exe'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('__main__.py', source)
        (directory / 'gh.exe').write_bytes((Path(distlib.origin).parent / name).read_bytes() + b'#!"'
                                           + os.fsencode(sys.executable) + b'" -I\n' + archive.getvalue())
    else:
        script = directory / 'gh_resolvable.py'
        script.write_text(source, encoding='utf-8')
        launcher = directory / 'gh'
        launcher.write_text('#!/bin/sh\nexec "%s" -I "%s" "$@"\n' % (sys.executable, script), encoding='utf-8')
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return directory


def _switched_gh(tmp_path, monkeypatch, visibility, sees=None):
    fixtures = _kit_fixtures()
    stub = fixtures.make_gh_cli_stub(tmp_path, accounts=['example-owner', 'other-account'],
                                     active='other-account',
                                     sees={'example-owner': [REPOSITORY]} if sees is None else sees,
                                     visibility={REPOSITORY: visibility})
    monkeypatch.setenv('PATH', str(_resolvable_gh(stub)))
    for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_HOST', 'GH_ENTERPRISE_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    return fixtures, stub


def test_switched_active_account_still_proves_private(tmp_path, monkeypatch):
    fixtures, stub = _switched_gh(tmp_path, monkeypatch, 'PRIVATE')
    assert artifact_store._github_private(REPOSITORY) == 'true'
    calls = fixtures.gh_stub_calls(stub)
    assert not [call for call in calls if call['argv'][:2] == ['auth', 'switch']]
    assert [call['credential'] for call in calls if call['argv'][:2] == ['repo', 'view']] == ['example-owner']


@pytest.mark.parametrize('visibility', ['PUBLIC', 'INTERNAL'])
def test_public_repository_is_never_reported_private(tmp_path, monkeypatch, visibility):
    _switched_gh(tmp_path, monkeypatch, visibility)
    assert artifact_store._github_private(REPOSITORY) == 'false'


def test_plain_active_account_query_is_the_incident(tmp_path, monkeypatch):
    """Negative control: the stub's active account cannot see the repository, as on 2026-10-09."""
    _fixtures, stub = _switched_gh(tmp_path, monkeypatch, 'PRIVATE')
    result = subprocess.run([str(stub['launcher']), 'repo', 'view', REPOSITORY, '--json', 'nameWithOwner,visibility'],
                            capture_output=True, text=True, env=dict(os.environ, GH_HOST='github.com'),
                            **({'creationflags': 0x08000000} if os.name == 'nt' else {}))
    assert result.returncode != 0


def _synthetic_git(monkeypatch):
    """Answer only the companion's Git configuration; gh goes to the real process layer."""
    real_run = subprocess.run
    url = 'https://github.com/' + REPOSITORY + '.git'

    def run(args, **kwargs):
        if args[0] != 'git':
            return real_run(args, **kwargs)
        if args[3:5] == ['config', '--null']:
            return SimpleNamespace(returncode=0, stdout='remote.origin.url\n' + url + '\0', stderr='')
        if args[3:5] == ['remote', 'get-url']:
            return SimpleNamespace(returncode=0, stdout=url + '\n', stderr='')
        pytest.fail('unexpected git command')
    monkeypatch.setattr(subprocess, 'run', run)


def test_capture_route_proof_asks_any_account(tmp_path, monkeypatch):
    """The production call site in _verify_repository, not only the helper, must ask any account."""
    fixtures, stub = _switched_gh(tmp_path, monkeypatch, 'PRIVATE')
    _synthetic_git(monkeypatch)
    artifact_store._verify_repository(tmp_path / 'companion')
    calls = fixtures.gh_stub_calls(stub)
    assert [call['credential'] for call in calls if call['argv'][:2] == ['repo', 'view']] == ['example-owner']
    assert not [call for call in calls if call['argv'][:1] == ['api'] or call['argv'][:2] == ['auth', 'switch']]


def test_capture_route_proof_refuses_public(tmp_path, monkeypatch):
    _switched_gh(tmp_path, monkeypatch, 'PUBLIC')
    _synthetic_git(monkeypatch)
    with pytest.raises(RuntimeError, match='PUBLIC or visibility is unknown'):
        artifact_store._verify_repository(tmp_path / 'companion')


def test_no_credential_can_see_it_refuses(tmp_path, monkeypatch):
    _switched_gh(tmp_path, monkeypatch, 'PRIVATE', sees={})
    with pytest.raises(RuntimeError, match='no gh credential'):
        artifact_store._github_private(REPOSITORY)


def test_a_kit_without_the_api_refuses(tmp_path, monkeypatch):
    (tmp_path / 'guards/tools').mkdir(parents=True)
    (tmp_path / 'guards/tools/data_boundary.py').write_text('class GitError(RuntimeError):\n    pass\n',
                                                            encoding='utf-8')
    monkeypatch.setattr(artifact_store, 'TOOL_ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='account-independent'):
        artifact_store._github_private(REPOSITORY)
