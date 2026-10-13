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


def _tool_with_data(tmp_path, monkeypatch, name='toolrootlongname'):
    source = tmp_path / name
    inside = source / 'data'
    inside.mkdir(parents=True)
    monkeypatch.setattr(artifact_store, 'TOOL_ROOT', source.resolve())
    monkeypatch.setattr(artifact_store, '_no_links', lambda path, **kwargs: path)
    return source, inside


def _short_name(path):
    if os.name != 'nt':
        return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    if not length or length >= len(buffer):
        return None
    short = buffer.value
    return short if Path(short).name.lower() != Path(path).name.lower() else None


def _assert_refused(alias, inside, monkeypatch):
    monkeypatch.setitem(os.environ, 'SCREEN_VISION_DATA_DIR', str(alias))
    with pytest.raises(RuntimeError, match='outside the tool'):
        artifact_store.artifact_directory('captures/acme')
    assert list(inside.iterdir()) == []


def test_short_name_alias_of_tool_tree_is_refused(private_capture, tmp_path, monkeypatch):
    source, inside = _tool_with_data(tmp_path, monkeypatch)
    short = _short_name(source)
    if short is None:
        pytest.skip('8.3 short names are not available on this filesystem')
    alias = Path(short) / 'data'
    assert not alias.absolute().is_relative_to(artifact_store.TOOL_ROOT)  # lexical check alone misses it
    _assert_refused(alias, inside, monkeypatch)


def test_dotdot_alias_of_tool_tree_is_refused(private_capture, tmp_path, monkeypatch):
    source, inside = _tool_with_data(tmp_path, monkeypatch)
    (tmp_path / 'elsewhere').mkdir()
    alias = tmp_path / 'elsewhere' / '..' / source.name / 'data'
    assert not alias.absolute().is_relative_to(artifact_store.TOOL_ROOT)
    # The overlap comparison itself must see through '..', not only the reserved-component check.
    assert artifact_store._overlaps_tool_root(alias.absolute())
    monkeypatch.setitem(os.environ, 'SCREEN_VISION_DATA_DIR', str(alias))
    with pytest.raises(RuntimeError):
        artifact_store.artifact_directory('captures/acme')
    assert list(inside.iterdir()) == []


@pytest.mark.skipif(os.name != 'nt', reason='verbatim prefix is Windows-only')
def test_verbatim_prefix_alias_of_tool_tree_is_refused(private_capture, tmp_path, monkeypatch):
    _, inside = _tool_with_data(tmp_path, monkeypatch)
    alias = '\\\\?\\' + str(inside.resolve())
    assert not Path(alias).is_relative_to(artifact_store.TOOL_ROOT)
    _assert_refused(alias, inside, monkeypatch)


def test_verbatim_prefix_is_stripped():
    assert artifact_store._strip_verbatim(r'\\?\C:\x\data') == r'C:\x\data'
    assert artifact_store._strip_verbatim(r'\\?\UNC\host\share\data') == r'\\host\share\data'
    assert artifact_store._strip_verbatim(r'\\?\unc\host\share\data') == r'\\host\share\data'
    assert artifact_store._strip_verbatim(r'C:\x\data') == r'C:\x\data'
