"""Path-only capture admission, without reading any desktop or real payload."""
import os
import json
import subprocess
from pathlib import Path

import pytest

import artifact_store
import capture
from make_fixtures import build_versioned_capture_storage


@pytest.fixture
def private_capture(tmp_path, monkeypatch):
    repo, data, environment = build_versioned_capture_storage(tmp_path)
    monkeypatch.setattr(os, 'environ', environment)
    return repo, data


def test_admission_runs_no_git_or_gh(private_capture, monkeypatch):
    _, data = private_capture

    def no_process(*args, **kwargs):
        raise AssertionError('capture admission must not run Git or gh')

    monkeypatch.setattr(subprocess, 'run', no_process)
    monkeypatch.setattr(subprocess, 'check_output', no_process)
    directory = artifact_store.artifact_directory('captures/acme')
    assert directory == data / 'captures' / 'acme'
    assert not (data / 'captures').exists()


def test_json_staging_writes_complete_manifest(private_capture):
    _, data = private_capture
    directory = artifact_store.artifact_directory('captures/acme')
    directory.mkdir(parents=True)
    target = directory / 'capture.json'
    capture.write_json_artifact(str(target), {'synthetic': True})
    assert json.loads(target.read_text(encoding='utf-8')) == {'synthetic': True}
    assert not target.with_suffix('.json.tmp').exists()


@pytest.mark.parametrize('leaf', ['undeclared.png', 'screen.png.bak'])
def test_undeclared_leaf_does_not_call_writer(private_capture, leaf):
    _, data = private_capture
    with pytest.raises(capture.ArtifactWriteError):
        capture.persist_artifact(str(data / 'captures/acme' / leaf),
                                 lambda: pytest.fail('refused output reached writer'))


@pytest.mark.parametrize('relative', ['screen.png', 'captures/screen.png', 'captures/a/b/screen.png',
                                      'captures/.git/screen.png'])
def test_leaf_outside_one_capture_directory_is_refused(private_capture, relative):
    _, data = private_capture
    with pytest.raises(capture.ArtifactWriteError):
        capture.persist_artifact(str(data / relative),
                                 lambda: pytest.fail('refused output reached writer'))


def test_data_directory_inside_tool_worktree_is_refused(private_capture, tmp_path, monkeypatch):
    source = tmp_path / 'tool'
    inside = source / 'data'
    inside.mkdir(parents=True)
    monkeypatch.setattr(artifact_store, 'TOOL_ROOT', source)
    monkeypatch.setitem(os.environ, 'SCREEN_VISION_DATA_DIR', str(inside))
    monkeypatch.setattr(artifact_store, '_no_links', lambda path, **kwargs: path)
    with pytest.raises(RuntimeError, match='outside the tool'):
        artifact_store.artifact_directory('captures/acme')
    assert list(inside.iterdir()) == []


def test_data_directory_must_be_named_data(private_capture, monkeypatch):
    repo, _ = private_capture
    other = repo / 'exports'
    other.mkdir()
    monkeypatch.setitem(os.environ, 'SCREEN_VISION_DATA_DIR', str(other))
    with pytest.raises(RuntimeError, match='data/'):
        artifact_store.artifact_directory('captures/acme')
    assert list(other.iterdir()) == []
