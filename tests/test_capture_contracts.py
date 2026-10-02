
"""Offline capture-contract regressions; scene payloads come from make_fixtures."""
import builtins
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'skills/screen-vision/scripts'), str(ROOT / 'tools')]
import capture
import probe
from make_fixtures import (
    action_capability_cases, capture_contract_cases, capture_contract_scene,
    layer_contract_cases, owned_capture_gate_cases, persistence_contract_cases)


def prepare_capture(scene, tmp_path, monkeypatch, *, layers='uia', retry=False):
    events = []
    clock = [scene['start_time']]
    output = tmp_path / 'capture'
    monkeypatch.setattr(capture.C, 'require_physical_coordinates', lambda: None)
    monkeypatch.setattr(capture.C, 'enum_monitors', lambda: scene['monitors'])
    monkeypatch.setattr(capture.C, 'virtual_screen_rect', lambda: (
        scene['rect'][0], scene['rect'][1], scene['width'], scene['height']))
    monkeypatch.setattr(capture.C, 'window_identity', lambda hwnd: scene['identity'])
    monkeypatch.setattr(capture.C, 'has_interactive_desktop', lambda: True)
    monkeypatch.setattr(capture.C, 'is_wayland', lambda: False)
    monkeypatch.setattr(capture.time, 'time', lambda: clock[0])
    def directory(requested):
        events.append('preflight')
        clock[0] += scene['preflight_delay']
        return output
    def grab(target):
        events.append('grab')
        clock[0] += scene['frame_delay']
        rgb = scene['black_rgb'] if retry and events.count('grab') == 1 else scene['rgb']
        return rgb, scene['width'], scene['height'], 'synthetic'
    monkeypatch.setattr(capture, 'artifact_directory', directory)
    monkeypatch.setattr(capture, 'grab_target', grab)
    monkeypatch.setattr(capture, 'collect_uia', lambda *args: copy.deepcopy(scene['elements']))
    monkeypatch.setattr(capture, 'collect_ocr', lambda *args: [])
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', scene['requested'],
                         '--layers', layers, '--annotate', 'false', '--json-stdout'])
    return events, clock, output


@pytest.mark.parametrize('case', capture_contract_cases(), ids=lambda row: row['id'])
def test_element_monitor_matches_its_own_physical_rectangle(case, tmp_path, monkeypatch, capsys):
    scene = capture_contract_scene(case)
    prepare_capture(scene, tmp_path, monkeypatch)
    assert capture.main() == 0
    result = json.loads(capsys.readouterr().out)
    record = result['elements'][0]
    assert record['rect'] == case['element_rect']
    assert record['monitor'] == case['monitor']
    assert record['scale'] == case['scale']
    assert record['origin'] == scene['rect'][:2]
    if case['monitor'] is None:
        assert any('monitor' in warning for warning in result['warnings'])


@pytest.mark.parametrize('retry', [False, True])
def test_capture_timestamp_tracks_selected_frame_after_preflight(retry, tmp_path, monkeypatch, capsys):
    scene = capture_contract_scene()
    events, clock, output = prepare_capture(scene, tmp_path, monkeypatch, retry=retry)
    assert capture.main() == 0
    result = json.loads(capsys.readouterr().out)
    acquired = result['capture']['captured_at']
    assert events == ['preflight'] + ['grab'] * (2 if retry else 1)
    assert scene['start_time'] + scene['preflight_delay'] <= acquired <= clock[0]
    assert clock[0] - acquired <= scene['frame_delay']
    if retry:
        assert acquired >= clock[0] - scene['frame_delay']
    assert result['elements'][0]['captured_at'] == acquired
    assert json.loads((output / 'capture.json').read_text())['capture']['captured_at'] == acquired


@pytest.mark.parametrize('case', layer_contract_cases(), ids=lambda row: row['id'])
def test_layers_validate_before_capture_and_preserve_capture_only(case, tmp_path, monkeypatch, capsys):
    events, _, output = prepare_capture(capture_contract_scene(), tmp_path, monkeypatch,
                                        layers=case['layers'])
    code = capture.main()
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is case['valid']
    if case['valid']:
        assert code == 0 and events == ['preflight', 'grab']
    else:
        assert code != 0 and result['error'] == 'invalid_layers'
        assert events == [] and not output.exists()


@pytest.mark.parametrize('case', persistence_contract_cases(), ids=lambda row: row['id'])
def test_artifact_write_error_is_structured_and_has_no_success_manifest(case, tmp_path, monkeypatch, capsys):
    _, _, output = prepare_capture(capture_contract_scene(), tmp_path, monkeypatch,
                                    layers=case['layers'])
    original = builtins.open
    def opening(path, mode='r', *args, **kwargs):
        name = Path(path).name if isinstance(path, (str, Path)) else ''
        if name in (case['filename'], case['filename'] + '.tmp') and any(c in mode for c in 'wx'):
            raise OSError(28, 'Synthetic volume is full', str(path))
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', opening)
    assert capture.main() != 0
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is False and result['error'] == 'artifact_write_failed'
    assert Path(result['artifact']).name == case['filename']
    assert 'Synthetic volume is full' in result['detail']
    assert not (output / 'capture.json').exists()


def test_existing_output_directory_is_refused_before_grab(tmp_path, monkeypatch, capsys):
    events, _, output = prepare_capture(capture_contract_scene(), tmp_path, monkeypatch)
    output.mkdir()
    assert capture.main() != 0
    result = json.loads(capsys.readouterr().out)
    assert not result['ok'] and result['error'] == 'artifact_store_unavailable'
    assert events == ['preflight'] and list(output.iterdir()) == []


@pytest.mark.parametrize('case', action_capability_cases(), ids=lambda row: row['id'])
def test_probe_actions_require_the_verified_platform_and_uia(case, monkeypatch, capsys):
    scene = capture_contract_scene()
    monkeypatch.setattr(probe.C, 'IS_WINDOWS', case['windows'])
    monkeypatch.setattr(probe.C.platform, 'system', lambda: case['system'])
    monkeypatch.setattr(probe.C, 'probe_libs', lambda: case['libs'])
    monkeypatch.setattr(probe.C, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(probe.C, 'require_physical_coordinates', lambda: None)
    monkeypatch.setattr(probe.C, 'has_interactive_desktop', lambda: case['ready'])
    monkeypatch.setattr(probe.C, 'enum_monitors', lambda: scene['monitors'])
    monkeypatch.setattr(probe.C, 'is_wayland', lambda: False)
    monkeypatch.setattr(probe.C, 'is_admin', lambda: False)
    monkeypatch.setattr(probe, '_gpu', lambda sink: None)
    assert probe.main() == (0 if case['ready'] else 1)
    result = json.loads(capsys.readouterr().out)
    assert result['capabilities']['click_physical'] is case['expected']
    assert result['capabilities']['click_invoke'] is case['expected']
    assert result['libs'] == case['libs']


@pytest.mark.parametrize('case', owned_capture_gate_cases(), ids=lambda row: row['id'])
def test_owned_capture_gate_checks_identity_size_and_real_png(case, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('synthetic_capture_gate', ROOT / 'tests/run_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    scene, report = case['scene'], copy.deepcopy(case['report'])
    path = tmp_path / 'synthetic.png'
    gate.C.write_png(path, scene['rgb'], scene['width'], scene['height'])
    if case['png_invalid']:
        path.write_bytes(b'')
    report['screenshot'] = str(path)
    identity = copy.deepcopy(scene['identity'])
    calls = []
    def identify(hwnd):
        calls.append(hwnd)
        value = copy.deepcopy(identity)
        if case['window_changed'] and len(calls) > 1:
            value['process_started'] += 1
        return value
    monkeypatch.setattr(gate.C, 'window_identity', identify)
    monkeypatch.setattr(gate, '_run_capture', lambda *args, **kwargs: report)
    gate.t_capture(scene['requested'])
    assert gate.results == [dict(name='owned_window_capture',
                                status=case['expected'], detail=gate.results[0]['detail'])]
    assert gate.results[0]['detail']
