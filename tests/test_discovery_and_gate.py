"""Generated regression scenes; all native and process operations are inert."""
import copy
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import _common as core
from make_fixtures import (title_discovery_cases, owned_gate_cases, owned_gate_scene,
                           incomplete_discovery_capture_cases)


@pytest.mark.parametrize('case', title_discovery_cases(), ids=lambda row: row['id'])
def test_window_discovery_requires_complete_native_results(case, monkeypatch):
    mode = case['id']
    windows = copy.deepcopy(case['windows'])
    if mode == 'absent': windows[0]['title'] = 'Acme first'
    if mode == 'ambiguous': windows[1]['title'] = 'Acme target two'
    if mode == 'empty-title': windows[1]['title'] = ''
    by_handle = {row['hwnd']: row for row in windows}
    last_error, lengths = [0], {}
    def set_error(value): last_error[0] = value
    def get_error(): return last_error[0]
    def visible(hwnd):
        if mode == 'callback-error' and hwnd == windows[1]['hwnd']:
            raise OSError('synthetic visibility failure')
        return 1
    def length(hwnd):
        lengths[hwnd] = lengths.get(hwnd, 0) + 1
        value = len(by_handle[hwnd]['title'])
        if hwnd == windows[1]['hwnd']:
            if mode in ('length-error', 'length-zero-error'):
                set_error(5)
                return value if mode == 'length-error' else 0
            if mode == 'title-race' and lengths[hwnd] > 1: return value + 1
        return value
    def title(hwnd, buffer, capacity):
        text = by_handle[hwnd]['title']
        if hwnd == windows[1]['hwnd']:
            if mode in ('text-zero-error', 'text-zero-noerror'):
                if mode == 'text-zero-error': set_error(5)
                return 0
            if mode == 'text-short':
                buffer.value = text[:-1]
                return 0
            if mode == 'title-growth': text += ' expanded'
        buffer.value = text[:capacity-1]
        return len(buffer.value)
    def rect(hwnd, output):
        if mode == 'rect-false': return 0
        values = [0, 0, 0, 0] if mode == 'rect-empty' else by_handle[hwnd]['rect']
        for name, value in zip(('left', 'top', 'right', 'bottom'), values):
            setattr(output._obj, name, value)
        return 1
    def enumerate_windows(callback, context):
        for row in windows:
            if not callback(row['hwnd'], context): return 0
        if mode == 'enum-error': raise OSError('synthetic enumeration failure')
        return 0 if mode == 'enum-false' else 1
    user32 = SimpleNamespace(IsWindowVisible=visible, GetWindowTextLengthW=length,
                             GetWindowTextW=title, GetWindowRect=rect, EnumWindows=enumerate_windows)
    monkeypatch.setattr(core, 'IS_WINDOWS', True)
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user32,
                        kernel32=SimpleNamespace(SetLastError=set_error, GetLastError=get_error)))
    if case['reject']:
        with pytest.raises(RuntimeError, match='discovery'):
            core.find_window_by_title('target')
    else:
        result = core.find_window_by_title('target')
        expected = None if mode in ('absent', 'ambiguous') else (
            windows[0]['hwnd'], windows[0]['rect'], windows[0]['title'])
        assert result == expected


@pytest.mark.parametrize('case', owned_gate_cases(), ids=lambda row: row['id'])
def test_interactive_gate_stops_at_first_unowned_or_failed_proof(case, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('owned_gate_regression', Path(__file__).with_name('run_gate.py'))
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    initial = owned_gate_scene('base')
    actions, captures, cleanup = [], [], []
    class Child:
        pid = initial['window']['pid']
        polls = 0
        def poll(self):
            self.polls += 1
            return 0 if case['stage'] == 'exited' and self.polls > 1 else None
        def terminate(self): cleanup.append('terminate')
        def wait(self, timeout): cleanup.append('wait')
    def identify(hwnd):
        window = copy.deepcopy(initial['window'])
        if case['stage'] == 'live' and actions: window['pid'] += 1
        return window
    def capture(target, layers='uia'):
        stage = 'base' if layers == '' else ('post' if actions else 'golden')
        fault = case['fault'] if stage == case['stage'] else None
        scene = owned_gate_scene(stage, fault, len(actions))
        captures.append(stage)
        screenshot = tmp_path / ('frame-%d.png' % len(captures))
        gate.C.write_png(screenshot, scene['rgb'], 4, 3)
        elements = tmp_path / ('elements-%d.json' % len(captures))
        elements.write_text(json.dumps(scene['elements']), encoding='utf-8')
        report = scene['report']
        report.update(screenshot=str(screenshot), elements_json=str(elements))
        return report
    def act(argv, **kwargs):
        assert Path(argv[1]).name == 'click.py'
        actions.append(argv)
        return SimpleNamespace(returncode=1 if case['stage'] == 'action' else 0,
                               stdout=json.dumps({'acted': case['stage'] != 'action'}))
    monkeypatch.setattr(gate.C, 'IS_WINDOWS', True)
    monkeypatch.setattr(gate.C, '_can_import', lambda name: True)
    monkeypatch.setattr(gate.C, 'window_identity', identify)
    monkeypatch.setattr(gate.C, 'find_window_by_title', lambda title: (
        initial['window']['hwnd'], initial['window']['rect'], title))
    monkeypatch.setattr(gate.subprocess, 'Popen', lambda *args, **kwargs: Child())
    monkeypatch.setattr(gate.subprocess, 'run', act)
    monkeypatch.setattr(gate, '_run_capture', capture)
    gate.run_interactive()
    assert len(actions) == case['actions']
    assert cleanup == ([] if case['stage'] == 'exited' else ['terminate', 'wait'])
    failed = [row for row in gate.results if row['status'] == 'FAIL']
    if case['id'] == 'healthy':
        assert not failed
        assert captures == ['base', 'golden', 'post', 'post']
        assert any(row['name'] == 'closed_loop_click' and row['status'] == 'PASS' for row in gate.results)
    else:
        assert failed
        assert not any(row['name'] == 'closed_loop_click' and row['status'] == 'PASS' for row in gate.results)


@pytest.mark.parametrize('case', incomplete_discovery_capture_cases(), ids=lambda row: row['id'])
def test_incomplete_discovery_stops_capture_before_any_artifact_or_fallback(case, monkeypatch, capsys):
    import capture
    scene = owned_gate_scene('base')
    window = scene['window']
    def incomplete(title): raise core.WindowDiscoveryError('synthetic incomplete discovery')
    def forbidden(*args, **kwargs): pytest.fail('incomplete discovery reached capture or artifacts')
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(core, 'enum_monitors', lambda: [{'index': 1, 'rect': window['rect']}])
    monkeypatch.setattr(core, 'virtual_screen_rect', lambda: (0, 0, 4, 3))
    monkeypatch.setattr(core, 'find_window_by_title', incomplete)
    monkeypatch.setattr(core, 'has_interactive_desktop', forbidden)
    monkeypatch.setattr(core, 'capture_region', forbidden)
    monkeypatch.setattr(capture, 'artifact_directory', forbidden)
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'window:Acme target'] + case['fallback'])
    assert capture.main() == 3
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is False and result['error'] == 'window_discovery_incomplete'
    assert 'screenshot' not in result
