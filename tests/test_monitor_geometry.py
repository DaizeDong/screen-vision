"""Synthetic monitor geometry and narrow-target failure regressions."""
import ctypes
import json
import sys
from types import SimpleNamespace

import pytest

from test_win32_safety import core, probe, library


@pytest.mark.parametrize('result', [0, 1])
def test_failed_or_empty_monitor_enumeration_never_invents_a_monitor(core, monkeypatch, result):
    monkeypatch.setattr(core, 'require_physical_coordinates', lambda: None)
    api = library({'EnumDisplayMonitors': result,
                   'GetSystemMetrics': lambda metric: {76: -1920, 77: 0, 78: 3840, 79: 1080}[metric]}, [])
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=api), raising=False)
    with pytest.raises(RuntimeError, match='monitor|Monitor'):
        core.enum_monitors()


def test_monitor_enumeration_preserves_individual_rectangles_and_pointer_handles(core, monkeypatch):
    monkeypatch.setattr(core, 'require_physical_coordinates', lambda: None)
    handles = [0x100000007, 0x100000019]
    rects = [(-800, 0, 0, 600), (0, 0, 1200, 900)]
    def enumerate_monitors(hdc, clip, callback, data):
        rect_type = callback.argtypes[2]._type_
        for handle, rect in zip(handles, rects):
            assert callback(handle, None, ctypes.pointer(rect_type(*rect)), data) == 1
        return 1
    def dpi(handle, kind, x, y):
        assert handle in handles
        x._obj.value = y._obj.value = 144
        return 0
    calls = []
    user = library({'EnumDisplayMonitors': enumerate_monitors}, calls)
    shcore = library({'GetDpiForMonitor': dpi}, calls)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user, shcore=shcore), raising=False)
    monitors = core.enum_monitors()
    assert [m['rect'] for m in monitors] == [list(rect) for rect in rects]
    assert [m['scale'] for m in monitors] == [1.5, 1.5]
    assert user.EnumDisplayMonitors.argtypes[-1] is ctypes.c_ssize_t
    assert shcore.GetDpiForMonitor.argtypes[0] is ctypes.c_void_p


@pytest.mark.parametrize('monitors', [[], [{'index': 1, 'rect': [0, 0, 0, 1]}],
                                    [{'index': 1, 'rect': [0, 0, 1, -1]}]])
def test_probe_requires_nonempty_positive_monitor_geometry(core, probe, monkeypatch, capsys, monitors):
    monkeypatch.setattr(core, 'probe_libs', lambda: dict.fromkeys(
        ['uiautomation', 'winocr', 'rapidocr', 'pillow', 'mss', 'pyautogui'], True))
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(core, 'require_physical_coordinates', lambda: None)
    monkeypatch.setattr(core, 'enum_monitors', lambda: monitors)
    monkeypatch.setattr(core, 'has_interactive_desktop', lambda: True)
    monkeypatch.setattr(core, 'is_admin', lambda: False)
    monkeypatch.setattr(probe, '_gpu', lambda sink: None)
    assert probe.main() != 0
    result = json.loads(capsys.readouterr().out)
    assert not result['ok'] and not result['capabilities']['screenshot']
    assert result['coordinate_error']


@pytest.mark.parametrize('width,height', [(0, 1080), (1920, 0), (-1, 1080)])
def test_virtual_desktop_requires_usable_dimensions(core, monkeypatch, width, height):
    monkeypatch.setattr(core, 'require_physical_coordinates', lambda: None)
    api = library({'GetSystemMetrics': lambda metric: {76: -100, 77: 0, 78: width, 79: height}[metric]}, [])
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=api), raising=False)
    with pytest.raises(RuntimeError, match='geometry|dimensions'):
        core.virtual_screen_rect()


def test_nonwindows_geometry_comes_from_selected_backend(core, monkeypatch):
    core.IS_WINDOWS = False
    class MonitorBackend:
        monitors = [{'left': -640, 'top': -100, 'width': 1920, 'height': 820},
                    {'left': -640, 'top': 0, 'width': 640, 'height': 480},
                    {'left': 0, 'top': -100, 'width': 1280, 'height': 820}]
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setitem(sys.modules, 'mss', SimpleNamespace(mss=MonitorBackend))
    monitors = core.enum_monitors()
    assert [m['rect'] for m in monitors] == [[-640, 0, 0, 480], [0, -100, 1280, 720]]
    assert core.virtual_screen_rect() == (-640, -100, 1920, 820)


def test_unavailable_nonwindows_geometry_is_not_a_guessed_screen(core, monkeypatch):
    core.IS_WINDOWS = False
    monkeypatch.setitem(sys.modules, 'mss', None)
    with pytest.raises(RuntimeError, match='geometry|monitor'):
        core.enum_monitors()


@pytest.mark.parametrize('target', ['monitor:1', 'all'])
def test_capture_geometry_failure_precedes_artifact_creation(core, monkeypatch, capsys, target):
    import capture
    monkeypatch.setattr(capture, 'C', core)
    monkeypatch.setattr(core, 'require_physical_coordinates', lambda: None)
    monkeypatch.setattr(core, 'enum_monitors', lambda: [])
    monkeypatch.setattr(capture, 'artifact_directory', lambda *a: pytest.fail('unexpected artifact creation'))
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', target, '--allow-full-screen-fallback'])
    assert capture.main() == 3
    result = json.loads(capsys.readouterr().out)
    assert result['error'] == 'monitor_geometry_unavailable'
