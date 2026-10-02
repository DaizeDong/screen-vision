"""Win32 boundary regressions; all native calls use synthetic functions."""
import ctypes
import importlib.util
from pathlib import Path
import platform
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest


class NativeFunction:
    def __init__(self, name, result, calls):
        self.name, self.result, self.calls = name, result, calls
        self.argtypes = self.restype = None

    def __call__(self, *args):
        self.calls.append((self.name, args))
        return self.result(*args) if callable(self.result) else self.result


def library(values, calls):
    return SimpleNamespace(**{name: NativeFunction(name, result, calls)
                              for name, result in values.items()})


@pytest.fixture
def core(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'skills/screen-vision/scripts/_common.py'
    spec = importlib.util.spec_from_file_location('synthetic_win32_common', path)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setattr(platform, 'system', lambda: 'Synthetic')
        spec.loader.exec_module(module)
    module.IS_WINDOWS = True
    module._DPI_STATE = {'set': False, 'level': 'none'}
    return module


def dpi_api(monkeypatch, *, context_success=0, shcore_success=-2147024891,
            legacy_success=0, awareness=None, v2=False):
    calls = []
    user = {'SetProcessDpiAwarenessContext': context_success, 'SetProcessDPIAware': legacy_success}
    if awareness is not None:
        user.update(GetThreadDpiAwarenessContext=0x100000007,
                    GetAwarenessFromDpiAwarenessContext=awareness,
                    AreDpiAwarenessContextsEqual=int(v2))
    api = SimpleNamespace(user32=library(user, calls),
                          shcore=library({'SetProcessDpiAwareness': shcore_success}, calls))
    monkeypatch.setattr(ctypes, 'windll', api, raising=False)
    return api, calls


def test_failed_setters_do_not_prove_dpi_awareness(core, monkeypatch):
    _, calls = dpi_api(monkeypatch)
    assert core.set_dpi_awareness() == 'unverified'
    assert [name for name, _ in calls] == ['SetProcessDpiAwarenessContext',
                                         'SetProcessDpiAwareness', 'SetProcessDPIAware']


def test_failed_bool_continues_to_hresult_fallback(core, monkeypatch):
    api, calls = dpi_api(monkeypatch, shcore_success=0)
    def process_awareness(handle, pointer):
        assert handle is None
        pointer._obj.value = 2
        return 0
    api.shcore.GetProcessDpiAwareness = NativeFunction('GetProcessDpiAwareness', process_awareness, calls)
    assert core.set_dpi_awareness() == 'per_monitor'
    assert 'SetProcessDPIAware' not in [name for name, _ in calls]
    assert api.shcore.SetProcessDpiAwareness.restype is ctypes.c_long
    assert api.shcore.GetProcessDpiAwareness.argtypes[0] is ctypes.c_void_p


@pytest.mark.parametrize('awareness,v2,expected', [(2, True, 'per_monitor_v2'),
                                                (2, False, 'per_monitor'),
                                                (1, False, 'system'), (0, False, 'unaware'),
                                                (-1, False, 'unverified')])
def test_existing_thread_awareness_is_reported_honestly(core, monkeypatch, awareness, v2, expected):
    api, _ = dpi_api(monkeypatch, awareness=awareness, v2=v2)
    assert core.set_dpi_awareness() == expected
    assert api.user32.GetThreadDpiAwarenessContext.restype is ctypes.c_void_p
    assert api.user32.SetProcessDpiAwarenessContext.argtypes == [ctypes.c_void_p]


def test_setter_success_without_effective_query_is_unverified(core, monkeypatch):
    dpi_api(monkeypatch, context_success=1)
    assert core.set_dpi_awareness() == 'unverified'


def test_thread_context_change_cannot_reuse_cached_physical_permission(core, monkeypatch):
    api, calls = dpi_api(monkeypatch, context_success=1, awareness=2, v2=True)
    assert core.set_dpi_awareness() == 'per_monitor_v2'
    api.user32.GetAwarenessFromDpiAwarenessContext.result = 1
    assert core.set_dpi_awareness() == 'system'
    assert [name for name, _ in calls].count('SetProcessDpiAwarenessContext') == 1


def test_legacy_process_query_reports_system_awareness(core, monkeypatch):
    api, calls = dpi_api(monkeypatch, legacy_success=1)
    api.user32.IsProcessDPIAware = NativeFunction('IsProcessDPIAware', 1, calls)
    assert core.set_dpi_awareness() == 'system'


def test_failed_thread_query_does_not_borrow_process_awareness(core, monkeypatch):
    api, calls = dpi_api(monkeypatch, awareness=2)
    api.user32.GetThreadDpiAwarenessContext.result = 0
    api.shcore.GetProcessDpiAwareness = NativeFunction('GetProcessDpiAwareness', 0, calls)
    assert core.set_dpi_awareness() == 'unverified'
    assert 'GetProcessDpiAwareness' not in [name for name, _ in calls]


def test_probe_reports_coordinate_unavailability_without_geometry_or_desktop_read(core, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / 'skills/screen-vision/scripts/probe.py'
    spec = importlib.util.spec_from_file_location('synthetic_probe', path)
    probe = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, '_common', core)
    spec.loader.exec_module(probe)
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'unverified')
    monkeypatch.setattr(core, 'probe_libs', lambda: dict.fromkeys(
        ['uiautomation', 'winocr', 'rapidocr', 'pillow', 'mss', 'pyautogui'], True))
    monkeypatch.setattr(core, 'is_admin', lambda: False)
    monkeypatch.setattr(core, 'has_interactive_desktop', lambda: True)
    monkeypatch.setattr(probe, '_gpu', lambda sink: None)
    monkeypatch.setattr(core, 'enum_monitors', lambda: pytest.fail('unknown DPI reached monitor geometry'))
    assert probe.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report['ok'] is False and report['monitors'] == []
    assert report['dpi_awareness'] == 'unverified'
    assert all(report['capabilities'][key] is False for key in
               ('screenshot', 'uia_elements', 'click_physical', 'click_invoke'))


@pytest.fixture
def probe(core, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'skills/screen-vision/scripts/probe.py'
    spec = importlib.util.spec_from_file_location('synthetic_readiness_probe', path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, '_common', core)
    spec.loader.exec_module(module)
    return module


def unavailable_api(*args):
    raise OSError('synthetic API unavailable')


@pytest.mark.parametrize('opened,closed,expected', [
    (0x100000019, 1, True), (0x100000019, -1, True),
    (0, 1, False), (None, 1, False), (unavailable_api, 1, False),
    (0x100000019, 0, False), (0x100000019, unavailable_api, False),
])
def test_desktop_readiness_requires_acquisition_and_release(core, monkeypatch, opened, closed, expected):
    calls = []
    user32 = library({'OpenInputDesktop': opened, 'CloseDesktop': closed}, calls)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user32), raising=False)
    assert core.has_interactive_desktop() is expected
    assert [name for name, _ in calls].count('CloseDesktop') == int(
        isinstance(opened, int) and opened != 0)
    assert calls[0] == ('OpenInputDesktop', (0, False, 0x0001))
    assert user32.OpenInputDesktop.restype is ctypes.c_void_p
    assert user32.OpenInputDesktop.argtypes == [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    assert user32.CloseDesktop.argtypes == [ctypes.c_void_p]
    assert user32.CloseDesktop.restype is ctypes.c_int
    if expected:
        assert calls[-1] == ('CloseDesktop', (0x100000019,))
        assert core.has_interactive_desktop.reason is None
    else:
        assert core.has_interactive_desktop.reason


@pytest.mark.parametrize('missing', ['OpenInputDesktop', 'CloseDesktop'])
def test_missing_desktop_api_does_not_open_an_unreleasable_handle(core, monkeypatch, missing):
    calls = []
    user32 = library({'OpenInputDesktop': 0x100000019, 'CloseDesktop': 1}, calls)
    delattr(user32, missing)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user32), raising=False)
    assert core.has_interactive_desktop() is False
    assert calls == []


@pytest.mark.parametrize('desktop_ready', [False, True])
def test_probe_separates_installed_libraries_from_session_readiness(
        core, probe, monkeypatch, capsys, desktop_ready):
    libs = dict.fromkeys(['uiautomation', 'winocr', 'rapidocr', 'pillow', 'mss', 'pyautogui'], True)
    monitors = [{'index': 1, 'rect': [0, 0, 200, 200]}]
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    monkeypatch.setattr(core, 'probe_libs', lambda: libs)
    monkeypatch.setattr(core, 'is_admin', lambda: False)
    monkeypatch.setattr(core, 'has_interactive_desktop', lambda: desktop_ready)
    monkeypatch.setattr(probe, '_gpu', lambda sink: None)
    def enum_monitors():
        assert desktop_ready, 'unavailable desktop reached native monitor geometry'
        return monitors
    monkeypatch.setattr(core, 'enum_monitors', enum_monitors)
    assert probe.main() == (0 if desktop_ready else 1)
    report = json.loads(capsys.readouterr().out)
    assert report['ok'] is desktop_ready
    assert report['interactive_desktop'] is desktop_ready
    assert report['libs'] == libs
    assert report['monitors'] == (monitors if desktop_ready else [])
    assert all(report['capabilities'][key] is desktop_ready for key in
               ('screenshot', 'uia_elements', 'click_physical', 'click_invoke'))
    assert report['capabilities']['ocr'] and report['capabilities']['annotate']
    assert bool(report['desktop_error']) is not desktop_ready
    if not desktop_ready:
        assert not any('install' in note.lower() for note in report['notes'])


@pytest.mark.parametrize('stdout,expected', [
    ('Name\r\nNVIDIA Synthetic Adapter\r\n', True),
    ('Name\nAMD Synthetic Adapter\n', True),
    ('Name\nIntel(R) UHD Graphics Synthetic\n', True),
    ('No Instance(s) Available.\r\n', False),
    ('', None), ('Name\n', None), ('synthetic error\n', None),
    ('NVIDIA Synthetic Adapter\n', None), ('Name\nAcme unknown adapter\n', None),
])
def test_gpu_query_distinguishes_hardware_absence_and_unknown(probe, monkeypatch, stdout, expected):
    result = SimpleNamespace(returncode=0, stdout=stdout, stderr='')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: result)
    assert probe.gpu_present() is expected
    assert bool(probe.gpu_present.reason) is (expected is None)


@pytest.mark.parametrize('stdout', ['', 'Name\nNVIDIA Synthetic Adapter\n', 'No Instance(s) Available.'])
def test_failed_gpu_command_never_asserts_hardware_state(probe, monkeypatch, stdout):
    result = SimpleNamespace(returncode=1, stdout=stdout, stderr='synthetic failure')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: result)
    assert probe.gpu_present() is None
    assert '1' in probe.gpu_present.reason


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('synthetic', 30),
                                   FileNotFoundError('synthetic executable unavailable')])
def test_gpu_exception_is_unknown_and_a_later_success_clears_reason(probe, monkeypatch, failure):
    def failed(*args, **kwargs):
        raise failure
    monkeypatch.setattr(subprocess, 'run', failed)
    sink = {}
    assert probe._gpu(sink) is None
    assert sink['why']
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout='Name\nNVIDIA Synthetic Adapter\n', stderr=''))
    assert probe.gpu_present() is True
    assert probe.gpu_present.reason is None


@pytest.mark.parametrize('level', ['unverified', 'unaware', 'system', 'none'])
@pytest.mark.parametrize('operation', ['capture_region', '_capture_gdi', 'virtual_screen_rect',
                                      'enum_monitors', 'find_window_by_title', 'window_identity',
                                      'click_physical'])
def test_unproven_physical_coordinates_never_reach_native_operations(core, monkeypatch, level, operation):
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail('unverified coordinates reached native API ' + name)
    monkeypatch.setattr(ctypes, 'windll', Forbidden(), raising=False)
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: level)
    monkeypatch.setitem(sys.modules, 'mss', Forbidden())
    args = {'capture_region': (0, 0, 2, 2), '_capture_gdi': (0, 0, 2, 2),
            'virtual_screen_rect': (), 'enum_monitors': (),
            'find_window_by_title': ('Acme',), 'window_identity': (101,), 'click_physical': (1, 2)}
    if operation == 'click_physical':
        assert core.click_physical(*args[operation]) is False
    else:
        with pytest.raises(RuntimeError, match='DPI'):
            getattr(core, operation)(*args[operation])


def gdi_api(monkeypatch, failing=None, failure=0, scanlines=2):
    calls = []
    desk, memory, bitmap, original = (0x100000011, 0x200000022, 0x300000033, 0x400000044)
    state = {'selected': original}
    def select(dc, obj):
        assert dc == memory
        name = 'SelectObject' if obj == bitmap else 'restore'
        if failing == name:
            return failure
        previous = state['selected']
        state['selected'] = obj
        return previous
    def dibits(dc, bmp, start, count, buffer, info, usage):
        if failing == 'GetDIBits':
            return failure
        ctypes.memmove(buffer, bytes([3, 2, 1, 255] * 4), 16)
        return scanlines
    values = dict(GetDC=desk, CreateCompatibleDC=memory, CreateCompatibleBitmap=bitmap,
                  SelectObject=select, BitBlt=1, GetDIBits=dibits,
                  DeleteObject=1, DeleteDC=1, ReleaseDC=1)
    if failing in values and failing not in ('SelectObject', 'GetDIBits'):
        values[failing] = failure
    api = SimpleNamespace(user32=library({key: values[key] for key in ('GetDC', 'ReleaseDC')}, calls),
                          gdi32=library({key: value for key, value in values.items()
                                         if key not in ('GetDC', 'ReleaseDC')}, calls))
    monkeypatch.setattr(ctypes, 'windll', api, raising=False)
    return api, calls, (desk, memory, bitmap, original)


@pytest.mark.parametrize('stage', ['GetDC', 'CreateCompatibleDC', 'CreateCompatibleBitmap',
                                  'SelectObject', 'BitBlt', 'GetDIBits', 'restore'])
def test_gdi_stage_failure_raises_and_releases_only_acquired_resources(core, monkeypatch, stage):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    _, calls, handles = gdi_api(monkeypatch, failing=stage)
    with pytest.raises(RuntimeError):
        core._capture_gdi(-20, 10, 2, 2)
    names = [name for name, _ in calls]
    assert ('ReleaseDC' in names) == (stage != 'GetDC')
    assert ('DeleteDC' in names) == (stage not in ('GetDC', 'CreateCompatibleDC'))
    assert ('DeleteObject' in names) == (stage not in ('GetDC', 'CreateCompatibleDC', 'CreateCompatibleBitmap'))
    if stage == 'restore':
        assert names.index('DeleteDC') < names.index('DeleteObject')
    if stage in ('BitBlt', 'GetDIBits'):
        assert ('SelectObject', (handles[1], handles[3])) in calls


@pytest.mark.parametrize('error_handle', [-1, ctypes.c_void_p(-1).value])
def test_gdi_error_sentinel_is_not_a_selected_object(core, monkeypatch, error_handle):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    gdi_api(monkeypatch, failing='SelectObject', failure=error_handle)
    with pytest.raises(RuntimeError, match='SelectObject'):
        core._capture_gdi(0, 0, 2, 2)


@pytest.mark.parametrize('scanlines', [0, 1, 3])
def test_incomplete_or_invalid_scanline_count_never_returns_pixels(core, monkeypatch, scanlines):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    gdi_api(monkeypatch, scanlines=scanlines)
    with pytest.raises(RuntimeError, match='GetDIBits'):
        core._capture_gdi(0, 0, 2, 2)


@pytest.mark.parametrize('stage', ['DeleteObject', 'DeleteDC', 'ReleaseDC'])
def test_cleanup_failure_is_reported_after_other_releases(core, monkeypatch, stage):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    _, calls, _ = gdi_api(monkeypatch, failing=stage)
    with pytest.raises(RuntimeError, match=stage):
        core._capture_gdi(0, 0, 2, 2)
    assert [name for name, _ in calls][-3:] == ['DeleteObject', 'DeleteDC', 'ReleaseDC']


def test_nonzero_cleanup_bool_is_success_even_when_negative(core, monkeypatch):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    api, _, _ = gdi_api(monkeypatch)
    api.gdi32.DeleteObject.result = -1
    api.gdi32.DeleteDC.result = -1
    assert core._capture_gdi(0, 0, 2, 2) == bytes([1, 2, 3] * 4)


def test_native_copy_exception_still_restores_and_releases(core, monkeypatch):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    api, calls, handles = gdi_api(monkeypatch)
    def failed(*args):
        raise OSError('synthetic copy failure')
    api.gdi32.BitBlt.result = failed
    with pytest.raises(OSError, match='synthetic copy failure'):
        core._capture_gdi(0, 0, 2, 2)
    assert ('SelectObject', (handles[1], handles[3])) in calls
    assert [name for name, _ in calls][-3:] == ['DeleteObject', 'DeleteDC', 'ReleaseDC']


def test_successful_gdi_capture_restores_before_read_and_preserves_large_handles(core, monkeypatch):
    monkeypatch.setattr(core, 'set_dpi_awareness', lambda: 'per_monitor_v2')
    api, calls, handles = gdi_api(monkeypatch)
    assert core._capture_gdi(-20, 10, 2, 2) == bytes([1, 2, 3] * 4)
    names = [name for name, _ in calls]
    restore = calls.index(('SelectObject', (handles[1], handles[3])))
    assert restore < names.index('GetDIBits') < names.index('DeleteObject')
    assert ('ReleaseDC', (None, handles[0])) in calls
    for name, lib in [('GetDC', api.user32), ('CreateCompatibleDC', api.gdi32),
                      ('CreateCompatibleBitmap', api.gdi32), ('SelectObject', api.gdi32)]:
        assert getattr(lib, name).restype is ctypes.c_void_p
    for name in ('BitBlt', 'GetDIBits', 'DeleteObject', 'DeleteDC'):
        assert getattr(api.gdi32, name).argtypes[0] is ctypes.c_void_p
    assert api.gdi32.GetDIBits.argtypes[1] is ctypes.c_void_p
