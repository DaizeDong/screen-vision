"""Native source artifact admission, without reading any desktop or real payload."""
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
    # Only the legacy live gh layer is stubbed; shared local proof stays native.
    monkeypatch.setattr(artifact_store, '_verify_repository', lambda root: None)
    return repo, data


@pytest.mark.parametrize('ignored', ['screen.png', 'capture.json', 'elements.json'])
def test_ignored_capture_leaf_refuses_before_directory_creation(private_capture, ignored):
    repo, data = private_capture
    (repo / '.gitignore').write_text('data/captures/*/' + ignored + '\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='ignored'):
        artifact_store.artifact_directory('captures/acme')
    assert not (data / 'captures').exists()


def test_unborn_companion_refuses_before_capture(private_capture):
    repo, data = private_capture
    subprocess.run(['git', '-C', str(repo), 'update-ref', '-d', 'HEAD'], check=True)
    with pytest.raises(RuntimeError):
        artifact_store.artifact_directory('captures/acme')
    assert not (data / 'captures').exists()


def test_json_staging_uses_explicit_transient_owner(private_capture):
    repo, data = private_capture
    (repo / '.gitignore').write_text('*.tmp\n', encoding='utf-8')
    directory = artifact_store.artifact_directory('captures/acme')
    directory.mkdir(parents=True)
    target = directory / 'capture.json'
    capture.write_json_artifact(str(target), {'synthetic': True})
    assert json.loads(target.read_text(encoding='utf-8')) == {'synthetic': True}
    assert not target.with_suffix('.json.tmp').exists()


def test_leaf_refusal_does_not_call_writer(private_capture):
    repo, data = private_capture
    (repo / '.gitignore').write_text('data/captures/*/screen.png\n', encoding='utf-8')
    with pytest.raises(capture.ArtifactWriteError):
        capture.persist_artifact(str(data / 'captures/acme/screen.png'),
                                 lambda: pytest.fail('refused output reached writer'))


@pytest.mark.parametrize('policy', ['missing', 'retired', 'undeclared'])
def test_source_contract_refusal_precedes_capture(private_capture, tmp_path, monkeypatch, policy):
    _, data = private_capture
    storage = artifact_store._storage_module()
    source = tmp_path / 'source'
    source.mkdir()
    contract = json.loads((artifact_store.TOOL_ROOT / 'storage.contract.json').read_text(encoding='utf-8'))
    if policy == 'retired':
        next(row for row in contract['artifacts'] if row['artifact_id'] == 'capture_frames')['retention_rule']['class'] = 'retired'
    elif policy == 'undeclared':
        contract['artifacts'] = [row for row in contract['artifacts'] if row['artifact_id'] != 'capture_frames']
    if policy != 'missing':
        (source / 'storage.contract.json').write_text(json.dumps(contract), encoding='utf-8')
    monkeypatch.setattr(artifact_store, 'TOOL_ROOT', source)
    monkeypatch.setattr(artifact_store, '_storage_module', lambda: storage)
    with pytest.raises(RuntimeError):
        artifact_store.artifact_directory('captures/acme')
    assert not (data / 'captures').exists()


def test_promotion_rechecks_durable_destination(private_capture, monkeypatch):
    repo, data = private_capture
    directory = artifact_store.artifact_directory('captures/acme')
    directory.mkdir(parents=True)
    target = directory / 'capture.json'
    original = json.dump
    def write_and_change_policy(*args, **kwargs):
        original(*args, **kwargs)
        (repo / '.gitignore').write_text('data/captures/*/capture.json\n', encoding='utf-8')
    monkeypatch.setattr(capture.json, 'dump', write_and_change_policy)
    with pytest.raises(capture.ArtifactWriteError, match='ignored'):
        capture.write_json_artifact(str(target), {'synthetic': True})
    assert not target.exists()
    assert Path(str(target) + '.tmp').is_file()
