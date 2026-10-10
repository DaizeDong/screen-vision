"""The live PRIVATE check must not depend on which gh account is ACTIVE.

A plain `gh api repos/OWNER/NAME --jq .private` asks only with the account `gh auth switch` last
selected. When another session switched it to an account that cannot see the companion, every
capture was refused. The query now goes through the pinned guards kit, which asks every stored gh
account. These tests run the REAL kit against a synthetic gh (the kit's own fixture generator)
whose active account cannot see the repository; nothing here touches the real gh.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

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


def _switched_gh(tmp_path, monkeypatch, visibility, sees=None):
    fixtures = _kit_fixtures()
    stub = fixtures.make_gh_cli_stub(tmp_path, accounts=['example-owner', 'other-account'],
                                     active='other-account',
                                     sees={'example-owner': [REPOSITORY]} if sees is None else sees,
                                     visibility={REPOSITORY: visibility})
    monkeypatch.setenv('PATH', str(stub['bin']))
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
