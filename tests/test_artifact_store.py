"""Synthetic destination tests: visibility must be proven before any capture files exist."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/screen-vision/scripts'))
import artifact_store


@pytest.mark.parametrize('visibility', ['false', '', 'null', 'true'])
def test_visibility_is_required_for_versioned_output(tmp_path, monkeypatch, visibility):
    repo = tmp_path/'acme-companion'
    data = repo/'data'
    data.mkdir(parents=True)
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    def run(args, **kwargs):
        if args[0] == 'gh': return SimpleNamespace(returncode=0, stdout=visibility)
        if 'rev-parse' in args: return SimpleNamespace(returncode=0, stdout=str(repo))
        if 'remote' in args:
            return SimpleNamespace(returncode=0, stdout='https://github.com/example-owner/screen-vision-config.git')
        if 'config' in args:
            return SimpleNamespace(returncode=0, stdout='remote.origin.url\nhttps://github.com/example-owner/screen-vision-config.git\0')
        pytest.fail('unexpected external command')
    monkeypatch.setattr(artifact_store.subprocess, 'run', run)
    # The live answer itself comes from the guards kit (test_visibility_any_gh_account.py); here the
    # stubbed process seam keeps answering it in the legacy `gh api ... --jq .private` shape.
    monkeypatch.setattr(artifact_store, '_github_private', lambda identity: artifact_store._run(
        ['gh', 'api', '--hostname', 'github.com', 'repos/' + identity, '--jq', '.private']).strip())
    # Route-only controls; test_artifact_admission exercises the native write gate.
    monkeypatch.setattr(artifact_store, 'authorize_capture_artifact', lambda path: Path(path))
    if visibility == 'true':
        path = artifact_store.artifact_directory('captures/acme')
        assert path == data/'captures/acme'
    else:
        with pytest.raises(RuntimeError, match='PUBLIC|unknown'):
            artifact_store.artifact_directory('captures/acme')
    assert not (data/'captures').exists()


def test_unknown_visibility_command_failure_is_not_private(tmp_path, monkeypatch):
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(artifact_store.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1, stdout=''))
    with pytest.raises(RuntimeError, match='failed'):
        artifact_store.artifact_directory()


def test_escape_from_private_data_is_rejected_before_external_calls(tmp_path, monkeypatch):
    data = tmp_path/'data'; data.mkdir()
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    monkeypatch.setattr(artifact_store.subprocess, 'run', lambda *a, **kw: pytest.fail('escaped path reached external validation'))
    with pytest.raises(RuntimeError, match='reserved|stay within'):
        artifact_store.artifact_directory('../outside')


@pytest.mark.parametrize('requested', ['other/acme', 'captures/nested/acme', 'captures'])
def test_undeclared_capture_layout_is_rejected_before_proof(tmp_path, monkeypatch, requested):
    data = tmp_path/'data'
    data.mkdir()
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    monkeypatch.setattr(artifact_store.subprocess, 'run',
                        lambda *a, **kw: pytest.fail('undeclared layout reached proof'))
    with pytest.raises(RuntimeError, match='captures'):
        artifact_store.artifact_directory(requested)
    assert list(data.iterdir()) == []
