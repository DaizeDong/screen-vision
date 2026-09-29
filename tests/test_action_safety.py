"""Exercise real CLI decisions with a synthetic UIA tree and intercepted OS actions."""
import copy
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/screen-vision/scripts'))
sys.path.insert(0, str(ROOT / 'tools'))
import capture
from make_fixtures import element

_click_spec = importlib.util.spec_from_file_location('screen_vision_click', ROOT/'skills/screen-vision/scripts/click.py')
click = importlib.util.module_from_spec(_click_spec)
_click_spec.loader.exec_module(click)
RAW_CLICK_PHYSICAL = click.C.click_physical
RAW_HAS_INTERACTIVE_DESKTOP = capture.C.has_interactive_desktop


class Control:
    def __init__(self, record, actions, runtime=None, hwnd=0):
        self.record, self.actions = record, actions
        self.runtime = runtime or record['identity']['runtime_id']
        self.NativeWindowHandle = hwnd
        self.ProcessId = 202
        self.children = []
        self.pattern = True
        self.on_get_pattern = lambda: None

    @property
    def BoundingRectangle(self):
        return SimpleNamespace(**dict(zip(('left', 'top', 'right', 'bottom'), self.record['rect'])))

    @property
    def Name(self): return self.record['name']
    @property
    def AutomationId(self): return self.record['automation_id']
    @property
    def ClassName(self): return self.record['class_name']
    @property
    def ControlTypeName(self): return 'ButtonControl'
    @property
    def IsEnabled(self): return self.record['enabled']
    @property
    def IsOffscreen(self): return self.record['offscreen']
    def GetRuntimeId(self): return self.runtime
    def GetChildren(self): return self.children
    def GetFirstChildControl(self): return self.children[0] if self.children else None
    def GetNextSiblingControl(self): return None
    def GetInvokePattern(self):
        self.on_get_pattern()
        return self if self.pattern else None
    def GetTogglePattern(self): return None
    def GetSelectionItemPattern(self): return None
    def GetExpandCollapsePattern(self): return None
    def GetValuePattern(self): return None
    def Invoke(self): self.actions.append(('invoke', self.record['automation_id']))


@pytest.fixture
def world(monkeypatch):
    saved = element()
    actions = []
    candidate = Control(copy.deepcopy(saved), actions)
    window = copy.deepcopy(saved['identity']['window'])
    root_record = copy.deepcopy(saved)
    root_record['rect'] = window['rect']
    root = Control(root_record, actions, runtime=[42, 1], hwnd=101)
    root.children = [candidate]
    auto = SimpleNamespace(ControlFromHandle=lambda hwnd: root if hwnd == 101 else None,
                           ControlFromPoint=lambda x, y: candidate)
    monkeypatch.setitem(sys.modules, 'uiautomation', auto)
    monkeypatch.setattr(click.C, 'IS_WINDOWS', True)
    monkeypatch.setattr(click.C, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(click.C, 'window_identity', lambda hwnd: copy.deepcopy(window), raising=False)
    monkeypatch.setattr(click.C, 'click_physical', lambda x, y, **kw: actions.append(('coord', x, y)) or True)
    monkeypatch.setattr(click, 'time', SimpleNamespace(time=lambda: 1001.0, monotonic=lambda: 1.0), raising=False)
    return SimpleNamespace(saved=saved, candidate=candidate, root=root, window=window,
                           auto=auto, actions=actions)


def run_click(world, tmp_path, monkeypatch, capsys, method='auto', confirm=True):
    path = tmp_path / 'elements.json'
    path.write_text(json.dumps([world.saved]), encoding='utf-8')
    args = ['click.py', '--elements-json', str(path), '--id', '0', '--method', method]
    if confirm: args += ['--confirm']
    monkeypatch.setattr(sys, 'argv', args)
    code = click.main()
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('method', ['auto', 'invoke', 'coord'])
@pytest.mark.parametrize('change', ['runtime', 'name', 'automation_id', 'rect', 'pid', 'process_start', 'window_runtime', 'age', 'future', 'missing_identity'])
def test_unverifiable_target_never_acts(world, tmp_path, monkeypatch, capsys, method, change):
    if change == 'runtime': world.candidate.runtime = [42, 999]
    elif change in ('name', 'automation_id'): world.candidate.record[change] = 'Acme other control'
    elif change == 'rect': world.candidate.record['rect'] = [100, 100, 140, 140]
    elif change == 'pid': world.window['pid'] = 999
    elif change == 'process_start': world.window['process_started'] = 999
    elif change == 'window_runtime': world.root.runtime = [42, 999]
    elif change == 'age': world.saved['captured_at'] = 1
    elif change == 'future': world.saved['captured_at'] = 2000
    else: world.saved.pop('identity')
    code, result = run_click(world, tmp_path, monkeypatch, capsys, method)
    assert world.actions == []
    assert code != 0 and result['error'] == 'recapture_required'


def test_verified_identity_can_invoke(world, tmp_path, monkeypatch, capsys):
    code, result = run_click(world, tmp_path, monkeypatch, capsys)
    assert code == 0 and result['acted'] is True
    assert world.actions == [('invoke', 'acme-action')]


def test_auto_coordinates_require_hit_test_even_without_pattern(world, tmp_path, monkeypatch, capsys):
    world.candidate.pattern = False
    world.auto.ControlFromPoint = lambda x, y: Control(element(), [], runtime=[42, 999])
    code, result = run_click(world, tmp_path, monkeypatch, capsys)
    assert world.actions == []
    assert code != 0 and result['error'] == 'recapture_required'


def test_verified_coordinate_fallback_uses_current_rect_not_saved_center(world, tmp_path, monkeypatch, capsys):
    world.candidate.pattern = False
    world.saved['center'] = [9999, 9999]
    code, result = run_click(world, tmp_path, monkeypatch, capsys)
    assert code == 0 and result['acted'] is True
    assert world.actions == [('coord', 30, 40)]


@pytest.mark.parametrize('move_ok,read_ok,position', [
    (False, True, (30, 40)), (True, False, (30, 40)),
    (True, True, (300, 400)), (True, True, (30, 40)),
])
def test_physical_click_requires_confirmed_pointer_position(world, tmp_path, monkeypatch, capsys,
                                                          move_ok, read_ok, position):
    events = []
    class User32:
        def SetCursorPos(self, x, y): return move_ok
        def GetCursorPos(self, pointer):
            pointer._obj.x, pointer._obj.y = position
            return read_ok
        def mouse_event(self, flags, *args): events.append(flags)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=User32()))
    monkeypatch.setattr(click.C, 'click_physical', RAW_CLICK_PHYSICAL)
    code, result = run_click(world, tmp_path, monkeypatch, capsys, method='coord')
    if move_ok and read_ok and position == (30, 40):
        assert code == 0 and result['acted'] is True
        assert events == [0x0002, 0x0004]
    else:
        assert code != 0 and result['acted'] is not True
        assert events == []


def test_pattern_lookup_race_requires_recapture(world, tmp_path, monkeypatch, capsys):
    world.candidate.on_get_pattern = lambda: world.candidate.record.update(name='Acme replaced')
    code, result = run_click(world, tmp_path, monkeypatch, capsys)
    assert world.actions == []
    assert code != 0 and result['error'] == 'recapture_required'


def test_failed_invoke_is_not_retried_as_coordinate(world, tmp_path, monkeypatch, capsys):
    def failed():
        world.actions.append(('invoke_started',))
        raise RuntimeError('synthetic provider disconnected after dispatch')
    world.candidate.Invoke = failed
    code, result = run_click(world, tmp_path, monkeypatch, capsys)
    assert world.actions == [('invoke_started',)]
    assert code != 0 and result['error'] == 'action_outcome_unknown'


def test_dry_default_never_resolves_or_acts(world, tmp_path, monkeypatch, capsys):
    world.auto.ControlFromHandle = lambda hwnd: pytest.fail('dry run touched UIA')
    code, result = run_click(world, tmp_path, monkeypatch, capsys, confirm=False)
    assert code == 0 and result['dry_run'] is True and world.actions == []


@pytest.fixture
def capture_world(monkeypatch):
    captures = []
    monkeypatch.setattr(capture.C, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(capture.C, 'enum_monitors', lambda: [{'index': 1, 'rect': [0, 0, 200, 200], 'origin': [0, 0], 'scale': 1.0}])
    monkeypatch.setattr(capture.C, 'virtual_screen_rect', lambda: (0, 0, 200, 200))
    monkeypatch.setattr(capture.C, 'find_window_by_title', lambda name: None)
    monkeypatch.setattr(capture.C, 'window_identity', lambda hwnd: None, raising=False)
    monkeypatch.setattr(capture.C, 'has_interactive_desktop', lambda: True)
    monkeypatch.setattr(capture.C, 'capture_region', lambda l, t, w, h: (captures.append([l, t, w, h]) or b'\xff' * (w*h*3), w, h, 'synthetic'))
    monkeypatch.setattr(capture, 'artifact_directory', lambda requested: Path(requested), raising=False)
    return captures


@pytest.mark.parametrize('spec', ['region:1,2,3', 'region:0,0,0,1', 'region:0,0,-1,2', 'monitor:99', 'monitor:abc', 'hwnd:xyz', 'hwnd:0', 'hwnd:101', 'window:Acme missing', 'garbage'])
def test_invalid_narrow_target_never_captures(capture_world, tmp_path, monkeypatch, capsys, spec):
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', spec, '--layers', '', '--out-dir', str(tmp_path/'out')])
    code = capture.main()
    result = json.loads(capsys.readouterr().out)
    assert capture_world == []
    assert code != 0 and result['error'] in ('invalid_target', 'target_not_found')
    assert not (tmp_path/'out').exists()


def test_explicit_full_screen_fallback_reports_requested_and_resolved_scope(capture_world, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'window:Acme missing', '--allow-full-screen-fallback', '--layers', '', '--out-dir', str(tmp_path/'out')])
    assert capture.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert capture_world == [[0, 0, 200, 200]]
    assert result['capture']['requested_target'] == 'window:Acme missing'
    assert result['capture']['resolved_target']['kind'] == 'all'
    assert result['capture']['fallback_used'] is True
    assert json.loads(Path(result['capture_manifest']).read_text())['capture'] == result['capture']


def test_capture_persists_identity_scope_and_timestamp(world, capture_world, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(capture.C, 'window_identity', lambda hwnd: copy.deepcopy(world.window))
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'hwnd:101', '--layers', 'uia', '--out-dir', str(tmp_path/'out'), '--annotate', 'false'])
    assert capture.main() == 0
    result = json.loads(capsys.readouterr().out)
    rows = json.loads(Path(result['elements_json']).read_text())
    row = next(row for row in rows if row['identity']['runtime_id'] == [42, 7])
    assert row['identity'] == element()['identity']
    assert row['capture_rect'] == [0, 0, 200, 200]
    assert row['captured_at'] == result['capture']['captured_at']


def test_window_disappearing_during_grab_is_not_success(world, capture_world, tmp_path, monkeypatch, capsys):
    observations = iter([copy.deepcopy(world.window), copy.deepcopy(world.window), None])
    monkeypatch.setattr(capture.C, 'window_identity', lambda hwnd: next(observations))
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'hwnd:101', '--layers', '', '--out-dir', str(tmp_path/'out')])
    assert capture.main() != 0
    result = json.loads(capsys.readouterr().out)
    assert result['error'] == 'target_not_found'
    assert not (tmp_path/'out/screen.png').exists()


@pytest.mark.parametrize('phase', ['uia_root', 'uia_transient', 'ocr'])
def test_window_replacement_after_grab_cannot_publish_actions(world, capture_world, tmp_path,
                                                           monkeypatch, capsys, phase):
    original_window = copy.deepcopy(world.window)
    def window_snapshot(hwnd):
        observed = copy.deepcopy(world.window)
        if phase == 'uia_transient' and observed != original_window:
            world.window.update(original_window)
        return observed
    monkeypatch.setattr(capture.C, 'window_identity', window_snapshot)
    def replace():
        world.window.update(pid=999, process_started=999)
        world.root.ProcessId = world.candidate.ProcessId = 999
    if phase in ('uia_root', 'uia_transient'):
        def changed_root(hwnd):
            replace()
            return world.root
        world.auto.ControlFromHandle = changed_root
    else:
        def changed_ocr(*args):
            replace()
            return []
        monkeypatch.setattr(capture, 'collect_ocr', changed_ocr)
    layers = 'uia' if phase in ('uia_root', 'uia_transient') else 'ocr'
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'hwnd:101', '--layers', layers,
                                    '--out-dir', str(tmp_path/'out'), '--annotate', 'false'])
    code = capture.main()
    result = json.loads(capsys.readouterr().out)
    assert code != 0 and result['error'] == 'target_not_found'
    assert world.actions == []
    assert not (tmp_path/'out/elements.json').exists()
    assert not (tmp_path/'out/capture.json').exists()


def test_uninitialized_artifact_store_does_not_capture(capture_world, monkeypatch, capsys):
    def uninitialized(requested): raise RuntimeError('Configure a private companion')
    monkeypatch.setattr(capture, 'artifact_directory', uninitialized)
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'region:0,0,10,10', '--layers', ''])
    assert capture.main() != 0
    assert capture_world == []
    assert json.loads(capsys.readouterr().out)['error'] == 'artifact_store_unavailable'


def test_desktop_query_failure_refuses_capture_before_artifacts(capture_world, tmp_path, monkeypatch, capsys):
    def unavailable(*args):
        raise OSError('synthetic desktop unavailable')
    monkeypatch.setattr(capture.C, 'IS_WINDOWS', True)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=SimpleNamespace(
        OpenInputDesktop=unavailable, CloseDesktop=lambda handle: 1)))
    monkeypatch.setattr(capture.C, 'has_interactive_desktop', RAW_HAS_INTERACTIVE_DESKTOP)
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'region:0,0,10,10',
                                    '--layers', '', '--out-dir', str(tmp_path/'out')])
    assert capture.main() != 0
    assert json.loads(capsys.readouterr().out)['error'] == 'no_interactive_desktop'
    assert capture_world == [] and not (tmp_path/'out').exists()


def test_unknown_dpi_blocks_capture_even_with_full_screen_fallback(capture_world, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(capture.C, 'IS_WINDOWS', True)
    monkeypatch.setattr(capture.C, 'set_dpi_awareness', lambda: 'unverified')
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'all', '--allow-full-screen-fallback',
                                    '--layers', '', '--out-dir', str(tmp_path/'out')])
    assert capture.main() != 0
    assert json.loads(capsys.readouterr().out)['error'] == 'dpi_awareness_unverified'
    assert capture_world == [] and not (tmp_path/'out').exists()


@pytest.mark.parametrize('method', ['auto', 'invoke', 'coord'])
def test_unknown_dpi_blocks_actions_before_uia_resolution(world, tmp_path, monkeypatch, capsys, method):
    monkeypatch.setattr(click.C, 'set_dpi_awareness', lambda: 'unverified')
    world.auto.ControlFromHandle = lambda hwnd: pytest.fail('unknown DPI reached UIA')
    code, result = run_click(world, tmp_path, monkeypatch, capsys, method=method)
    assert code != 0 and result['error'] == 'dpi_awareness_unverified'
    assert world.actions == []


def test_gate_default_does_not_capture_launch_or_click(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('screen_vision_gate', ROOT/'tests/run_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    def forbidden(*args, **kwargs): pytest.fail('default gate touched the desktop or a process')
    monkeypatch.setattr(gate, 't_capture', forbidden)
    monkeypatch.setattr(gate, 't_golden_uia', forbidden)
    monkeypatch.setattr(gate, 't_closed_loop', forbidden)
    monkeypatch.setattr(gate, 't_ocr_synthetic', lambda: None)
    monkeypatch.setattr(gate.subprocess, 'run', forbidden)
    monkeypatch.setattr(gate.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(sys, 'argv', ['run_gate.py', '--json'])
    assert gate.main() == 0
    assert json.loads(capsys.readouterr().out)['interactive'] is False


def test_interactive_gate_cleans_only_its_owned_process_on_failure(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('screen_vision_gate', ROOT/'tests/run_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    events = []
    class Owned:
        pid = 202
        def poll(self): return None
        def terminate(self): events.append(('terminate', self.pid))
        def wait(self, timeout): events.append(('wait', self.pid))
    def launch(args, **kwargs):
        events.append(('launch', Path(args[1]).name))
        return Owned()
    monkeypatch.setattr(gate.subprocess, 'Popen', launch)
    monkeypatch.setattr(gate.C, 'window_identity', lambda hwnd: element()['identity']['window'])
    monkeypatch.setattr(gate.C, 'find_window_by_title', lambda title: (101, [0, 0, 200, 200], title))
    monkeypatch.setattr(gate.C, '_can_import', lambda name: True)
    monkeypatch.setattr(gate, 't_ocr_synthetic', lambda: None)
    monkeypatch.setattr(gate, 't_capture', lambda *args: None)
    def failed(*args): raise RuntimeError('synthetic capture failure')
    monkeypatch.setattr(gate, 't_golden_uia', failed)
    monkeypatch.setattr(sys, 'argv', ['run_gate.py', '--json', '--interactive'])
    assert gate.main() == 1
    assert events == [('launch', 'desktop_fixture.py'), ('terminate', 202), ('wait', 202)]
    assert json.loads(capsys.readouterr().out)['fail'] >= 1
