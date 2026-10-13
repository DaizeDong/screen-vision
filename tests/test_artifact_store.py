"""Synthetic destination tests: capture paths are checked before any capture files exist."""
from pathlib import Path
import subprocess
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/screen-vision/scripts'))
import artifact_store


def test_configured_companion_is_admitted_without_external_calls(tmp_path, monkeypatch):
    repo = tmp_path/'acme-companion'
    data = repo/'data'
    data.mkdir(parents=True)
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('capture admission ran an external command'))
    path = artifact_store.artifact_directory('captures/acme')
    assert path == data/'captures/acme'
    assert not (data/'captures').exists()


@pytest.mark.parametrize('selector', ['', 'missing'])
def test_unconfigured_or_missing_companion_is_uninitialized(tmp_path, monkeypatch, selector):
    for name in ('SCREEN_VISION_DATA_DIR', 'SCREEN_VISION_CONFIG', 'SCREEN_VISION_CONFIG_DIR'):
        monkeypatch.delenv(name, raising=False)
    if selector:
        monkeypatch.setenv('SCREEN_VISION_CONFIG', str(tmp_path/'missing-companion'))
    with pytest.raises(RuntimeError, match='Uninitialized|does not exist'):
        artifact_store.artifact_directory()
    assert not (tmp_path/'missing-companion').exists()


def test_escape_from_private_data_is_rejected(tmp_path, monkeypatch):
    data = tmp_path/'data'; data.mkdir()
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    with pytest.raises(RuntimeError, match='reserved|stay within'):
        artifact_store.artifact_directory('../outside')


@pytest.mark.parametrize('requested', ['other/acme', 'captures/nested/acme', 'captures'])
def test_undeclared_capture_layout_is_rejected(tmp_path, monkeypatch, requested):
    data = tmp_path/'data'
    data.mkdir()
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    with pytest.raises(RuntimeError, match='captures'):
        artifact_store.artifact_directory(requested)
    assert list(data.iterdir()) == []
