"""Inert OCR capability parity controls; no production top-level imports."""
import ast
import builtins
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/screen-vision/scripts'
spec = importlib.util.spec_from_file_location('ocr_fixtures', ROOT / 'tools/make_fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def function_body(filename, name, namespace):
    """Compile one unchanged function while omitting module initialization."""
    source = ast.parse((SCRIPTS / filename).read_text(encoding='utf-8'))
    matches = [node for node in source.body
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise AssertionError('Expected one function: ' + name)
    module = ast.Module(body=matches, type_ignores=[])
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[name]


class OcrCapabilityTests(unittest.TestCase):
    def test_capability_matches_auto_backend(self):
        cases = fixtures.ocr_capability_cases()
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(case=case['id']):
                self.check_case(case)

    def check_case(self, case):
        attempts, executed, image_reads, unexpected_imports = [], [], [], []
        image = object()

        class RapidOCR:
            def __call__(self, path):
                executed.append(('rapidocr', path))
                return [case['rapidocr_result']], None

        def recognize(candidate):
            self.assertIs(candidate, image)
            executed.append(('winocr', case['png_path']))
            return case['winocr_result']

        def image_open(path):
            image_reads.append(path)
            return image

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            attempts.append(name)
            if name == 'rapidocr_onnxruntime':
                if not case['libs']['rapidocr']:
                    raise ImportError('synthetic missing rapidocr')
                return SimpleNamespace(RapidOCR=RapidOCR)
            if name == 'winocr':
                if not case['libs']['winocr']:
                    raise ImportError('synthetic missing winocr')
                return SimpleNamespace(recognize_pil_sync=recognize)
            if name == 'PIL':
                if not case['libs']['pillow']:
                    raise ImportError('synthetic missing Pillow')
                return SimpleNamespace(Image=SimpleNamespace(open=image_open))
            unexpected_imports.append(name)
            raise AssertionError('Unexpected import: ' + name)

        common = SimpleNamespace(
            IS_WINDOWS=case['system'] == 'Windows',
            platform=SimpleNamespace(system=lambda: case['system']),
            probe_libs=lambda: case['libs'].copy(),
            _can_import=lambda name: case['libs']['pillow' if name == 'PIL' else name],
            set_dpi_awareness=lambda: 'synthetic',
            has_interactive_desktop=lambda: True,
            require_physical_coordinates=lambda: None,
            enum_monitors=lambda: [], validate_monitor_geometry=lambda monitors: None,
            is_wayland=lambda: False, is_admin=lambda: False,
        )
        inert_builtins = dict(vars(builtins), __import__=fake_import)
        namespace = {'C': common, 'json': json, 'sys': sys,
                     '_gpu': lambda reason: False, '__builtins__': inert_builtins}
        probe = function_body('probe.py', 'main', namespace)
        collect = function_body('capture.py', 'collect_ocr', namespace)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(probe(), 0)
        report = json.loads(output.getvalue())
        warnings = []
        results = collect(case['png_path'], 'auto', case['origin'],
                          case['region'], [], warnings)
        expected = case['expected_backend']
        self.assertEqual(unexpected_imports, [])
        self.assertEqual(attempts, ['winocr', 'PIL'] if expected == 'winocr'
                         else ['rapidocr_onnxruntime'])
        self.assertEqual(executed, [(expected, case['png_path'])] if expected else [])
        self.assertEqual(image_reads, [case['png_path']] if expected == 'winocr' else [])
        self.assertEqual([item['label'] for item in results],
                         [case['text']] if expected else [])
        self.assertEqual(len(warnings), 0 if expected else 1)
        self.assertIs(report['capabilities']['ocr'], bool(executed))
        self.assertEqual(any(note.startswith('No OCR:') for note in report['notes']),
                         not bool(executed))


if __name__ == '__main__':
    unittest.main()
