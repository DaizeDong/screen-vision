
"""Generated offline controls for private routes, OCR execution, and desktop readiness."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/screen-vision/scripts'))
sys.path.insert(0, str(ROOT / 'tools'))
import artifact_store
import capture
from make_fixtures import screen_scene, transport_cases
from test_win32_safety import core, probe, library


@pytest.mark.parametrize('case', transport_cases(), ids=lambda case: case['id'])
def test_private_route_proof_precedes_capture(case, tmp_path, monkeypatch):
    repo = tmp_path / 'acme-companion'
    data = repo / 'data'
    data.mkdir(parents=True)
    monkeypatch.setenv('SCREEN_VISION_DATA_DIR', str(data))
    for key, value in case['env'].items():
        monkeypatch.setenv(key, value)
    calls = []
    entries = [('remote.origin.url', case['origin'])] + case['extra']
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == 'gh':
            value = case['private']
        elif args[0] == 'ssh':
            value = 'hostname github.com\nport 22\nuser git\n'
        elif 'rev-parse' in args:
            value = str(repo)
        elif 'remote' in args:
            value = '\n'.join(case['push'] if '--push' in args else case['fetch'])
        elif '--get' in args:
            value = case['origin']
        elif 'config' in args:
            value = ''.join(key + '\n' + value + '\0' for key, value in entries)
        else:
            pytest.fail('unexpected command')
        return SimpleNamespace(returncode=0, stdout=value)
    monkeypatch.setattr(artifact_store.subprocess, 'run', run)
    # The live answer itself comes from the guards kit (test_visibility_any_gh_account.py); here the
    # stubbed process seam keeps answering it in the legacy `gh api ... --jq .private` shape.
    monkeypatch.setattr(artifact_store, '_github_private', lambda identity: artifact_store._run(
        ['gh', 'api', '--hostname', 'github.com', 'repos/' + identity, '--jq', '.private']).strip())
    monkeypatch.setattr(artifact_store, 'authorize_capture_artifact', lambda path: Path(path))
    if case['allow']:
        assert artifact_store.artifact_directory('captures/acme') == data / 'captures/acme'
        assert any(args[0] == 'gh' for args, kw in calls)
        assert all(kw.get('env', {}).get('GIT_OPTIONAL_LOCKS') == '0'
                   for args, kw in calls if args[0] == 'git')
        assert all(not {'GIT_PAGER', 'GH_PAGER', 'PAGER'} & kw['env'].keys()
                   for args, kw in calls)
        assert all(os.environ[key] == value for key, value in case['env'].items())
    else:
        with pytest.raises(RuntimeError):
            artifact_store.artifact_directory('captures/acme')
    assert not (data / 'captures').exists()
    assert not any(args[0] == 'ssh' for args, kw in calls)


def capture_scene(scene, engine, tmp_path, monkeypatch, capsys):
    region = scene['rect']
    monkeypatch.setattr(capture.C, 'require_physical_coordinates', lambda: None)
    monitor = {'index': 1, 'rect': region, 'origin': region[:2],
               'physical_size': [64, 64], 'scale': 1.0}
    monkeypatch.setattr(capture.C, 'enum_monitors', lambda: [monitor])
    monkeypatch.setattr(capture.C, 'has_interactive_desktop', lambda: True)
    monkeypatch.setattr(capture.C, 'is_wayland', lambda: False)
    monkeypatch.setattr(capture, 'resolve_target', lambda *args: {'kind': 'all', 'rect': region,
                         'origin': region[:2], 'monitor': monitor})
    monkeypatch.setattr(capture, 'artifact_directory', lambda *args: tmp_path / 'capture')
    monkeypatch.setattr(capture, 'authorize_capture_artifact', lambda path: Path(path))
    monkeypatch.setattr(capture, 'grab_target', lambda *args: (scene['rgb'], 64, 64, 'synthetic'))
    monkeypatch.setattr(capture, 'collect_uia', lambda *args: scene['elements'])
    inputs, images = [], {}
    def write_png(path, rgb, width, height):
        images[str(path)] = (rgb, width, height)
    monkeypatch.setattr(capture.C, 'write_png', write_png)
    def recognize(path):
        pixels, width, height = images[str(path)]
        inputs.append((pixels, width, height))
        return [([[1, 1], [min(8, width), 1], [min(8, width), min(8, height)], [1, min(8, height)]],
                 scene['missing'], 0.9)], None
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(RapidOCR=lambda: recognize))
    class FakeImage:
        def __init__(self, path):
            self.path = path
        def __enter__(self): return self
        def __exit__(self, *args): return False
    def winocr(image):
        res, _ = recognize(image.path)
        return {'lines': [{'words': [{'text': text, 'bounding_rect':
                {'x': 1, 'y': 1, 'width': box[1][0] - 1, 'height': box[2][1] - 1}}
                for box, text, score in res]}]}
    monkeypatch.setitem(sys.modules, 'PIL', SimpleNamespace(Image=SimpleNamespace(open=FakeImage)))
    monkeypatch.setitem(sys.modules, 'winocr', SimpleNamespace(recognize_pil_sync=winocr))
    monkeypatch.setattr(sys, 'argv', ['capture.py', '--target', 'all', '--ocr-engine', engine,
                         '--annotate', 'false', '--json-stdout'])
    assert capture.main() == 0
    return json.loads(capsys.readouterr().out), inputs


@pytest.mark.parametrize('kind', ['container', 'empty', 'covered', 'partial', 'unnamed'])
@pytest.mark.parametrize('origin', [(40, 80), (-100, -60)])
@pytest.mark.parametrize('engine', ['rapidocr', 'winocr'])
def test_ocr_backend_receives_uncovered_pixels(kind, origin, engine, tmp_path, monkeypatch, capsys):
    scene = screen_scene(kind, origin)
    result, inputs = capture_scene(scene, engine, tmp_path, monkeypatch, capsys)
    ocr = [item for item in result['elements'] if item['source'] == 'ocr']
    if kind == 'covered':
        assert inputs == [] and ocr == []
    else:
        assert len(inputs) == 1 and len(ocr) == 1
        pixels, width, height = inputs[0]
        if kind == 'partial':
            assert (width, height) == (64, 47)
            assert scene['covered_color'] not in pixels
            assert ocr[0]['rect'][:2] == [origin[0] + 1, origin[1] + 18]
        else:
            assert (width, height) == (64, 64)
            assert ocr[0]['rect'][:2] == [origin[0] + 1, origin[1] + 1]


def test_collect_uia_keeps_named_root_without_losing_ocr(tmp_path, monkeypatch, capsys):
    scene = screen_scene('container')
    class Control:
        ControlTypeName = 'WindowControl'
        Name = scene['elements'][0]['name']
        AutomationId = 'acme-canvas'
        ClassName = 'AcmeCanvas'
        IsOffscreen = False
        IsEnabled = True
        BoundingRectangle = SimpleNamespace(left=0, top=0, right=64, bottom=64)
        def GetFirstChildControl(self): return None
    monkeypatch.setattr(capture.C, 'IS_WINDOWS', True)
    monkeypatch.setattr(capture.C, 'control_identity', lambda *args: None)
    monkeypatch.setitem(sys.modules, 'uiautomation',
                        SimpleNamespace(ControlFromHandle=lambda hwnd: Control()))
    scene['elements'] = capture.collect_uia({'kind': 'hwnd', 'hwnd': 101}, 50, scene['rect'], [])
    assert scene['elements'][0]['label'] == 'ACME CANVAS'
    result, inputs = capture_scene(scene, 'rapidocr', tmp_path, monkeypatch, capsys)
    assert inputs and result['counts']['ocr'] == 1


@pytest.mark.parametrize('allowed', [True, False])
def test_darwin_permission_is_independent_of_x11(core, monkeypatch, allowed):
    core.IS_WINDOWS = False
    monkeypatch.setattr(core.platform, 'system', lambda: 'Darwin')
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    calls = []
    api = library({'CGPreflightScreenCaptureAccess': allowed}, calls)
    monkeypatch.setattr(core.ctypes, 'CDLL', lambda path: api)
    assert core.has_interactive_desktop() is allowed
    assert [name for name, args in calls] == ['CGPreflightScreenCaptureAccess']
    assert api.CGPreflightScreenCaptureAccess.argtypes == []
    if not allowed:
        assert 'Screen Recording' in core.has_interactive_desktop.reason


def test_darwin_unavailable_permission_api_refuses(core, monkeypatch):
    core.IS_WINDOWS = False
    monkeypatch.setattr(core.platform, 'system', lambda: 'Darwin')
    monkeypatch.setenv('DISPLAY', ':synthetic')
    monkeypatch.setattr(core.ctypes, 'CDLL', lambda path: SimpleNamespace())
    assert core.has_interactive_desktop() is False
    assert core.has_interactive_desktop.reason


def test_linux_headless_still_refuses(core, monkeypatch):
    core.IS_WINDOWS = False
    monkeypatch.setattr(core.platform, 'system', lambda: 'Linux')
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    assert core.has_interactive_desktop() is False


def test_darwin_probe_uses_permission_and_geometry(core, probe, monkeypatch, capsys):
    core.IS_WINDOWS = False
    monkeypatch.setattr(core.platform, 'system', lambda: 'Darwin')
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setattr(core.ctypes, 'CDLL',
                        lambda path: library({'CGPreflightScreenCaptureAccess': True}, []))
    monkeypatch.setattr(core, 'probe_libs', lambda: dict.fromkeys(
        ['mss', 'uiautomation', 'winocr', 'rapidocr', 'pillow', 'pyautogui'], True))
    monkeypatch.setattr(core, 'enum_monitors', lambda: [{'index': 1, 'rect': screen_scene()['rect']}])
    monkeypatch.setattr(core, 'is_admin', lambda: False)
    monkeypatch.setattr(probe, '_gpu', lambda sink: None)
    assert probe.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] and result['capabilities']['screenshot']


@pytest.mark.parametrize('origin', [(40, 80), (-100, -60)])
def test_masked_interior_excludes_only_known_pixels(origin, tmp_path, monkeypatch, capsys):
    scene = screen_scene('interior', origin)
    result, inputs = capture_scene(scene, 'rapidocr', tmp_path, monkeypatch, capsys)
    pixels, width, height = inputs[0]
    assert (width, height) == (64, 64)
    for row in range(64):
        for column in range(64):
            at = (row * 64 + column) * 3
            expected = b'\xff\xff\xff' if 20 <= row < 40 and 20 <= column < 40 else scene['rgb'][at:at+3]
            assert pixels[at:at+3] == expected
    assert result['counts']['ocr'] == 1


def test_region_subtraction_tiles_exact_uncovered_union():
    import pure_ops
    scene = screen_scene('interior')
    boxes = [scene['elements'][-1]['rect'], [30, 30, 50, 50]]
    regions = pure_ops.compute_ocr_regions(scene['rect'], boxes)
    for y in range(64):
        for x in range(64):
            covered = any(l <= x < r and t <= y < b for l, t, r, b in boxes)
            count = sum(l <= x < r and t <= y < b for l, t, r, b in regions)
            assert count == (0 if covered else 1)


def test_duplicate_ocr_results_are_merged(monkeypatch):
    scene = screen_scene('empty')
    row = ([[1, 1], [8, 1], [8, 8], [1, 8]], scene['missing'], 0.9)
    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime',
                        SimpleNamespace(RapidOCR=lambda: lambda path: ([row, row], None)))
    results = capture.collect_ocr('synthetic.png', 'rapidocr', scene['origin'], scene['rect'], [], [])
    assert len(results) == 1
