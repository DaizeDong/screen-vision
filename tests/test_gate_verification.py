
"""Gate status and exit-code controls with synthetic DPI/OCR adapters."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import capture
from make_fixtures import verification_gate_cases


@pytest.mark.parametrize('case', verification_gate_cases(), ids=lambda row: row['id'])
def test_gate_status_and_exit_match_runtime_contract(case, tmp_path, monkeypatch, capsys):
    gate_path = Path(__file__).with_name('run_gate.py')
    spec = importlib.util.spec_from_file_location('synthetic_verification_gate', gate_path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    monkeypatch.setattr(gate.C, 'IS_WINDOWS', case['windows'])
    def dpi():
        gate.C._DPI_STATE['level'] = case['level']
        return case['level']
    monkeypatch.setattr(gate.C, 'set_dpi_awareness', dpi)
    # The real coordinate contract is the independent expected result for this level.
    if case['windows'] and case['dpi'] == 'FAIL':
        with pytest.raises(RuntimeError):
            gate.C.require_physical_coordinates()
    else:
        gate.C.require_physical_coordinates()
    def installed(name):
        if case['recognition'] == 'missing_engine':
            return False
        if case['recognition'] == 'winocr_only':
            return name == 'winocr'
        return name in ('winocr', 'rapidocr_onnxruntime')
    monkeypatch.setattr(gate.C, '_can_import', installed)
    images, attempts = [], []
    class Image:
        def save(self, path): images.append(path)
    pil = SimpleNamespace(
        Image=SimpleNamespace(new=lambda *args: Image()),
        ImageDraw=SimpleNamespace(Draw=lambda image: SimpleNamespace(text=lambda *args, **kwargs: None)),
        ImageFont=SimpleNamespace(truetype=lambda *args: object()))
    monkeypatch.setitem(sys.modules, 'PIL', None if case['recognition'] == 'missing_pillow' else pil)
    def recognize(path, engine, origin, region, boxes, warnings):
        attempts.append(path)
        warnings.extend(case['warnings'])
        return [{'label': text} for text in case['labels']]
    monkeypatch.setattr(capture, 'collect_ocr', recognize)
    monkeypatch.setattr(gate, 'run_interactive', lambda: pytest.fail('desktop path was reached'))
    monkeypatch.setattr(sys, 'argv', ['run_gate.py', '--json'])
    code = gate.main()
    result = json.loads(capsys.readouterr().out)
    entries = {row['name']: row for row in result['results']}
    assert entries['dpi_awareness']['status'] == case['dpi']
    assert entries['ocr_synthetic']['status'] == case['ocr']
    assert code == (1 if 'FAIL' in (case['dpi'], case['ocr']) else 0)
    assert result['interactive'] is False
    if case['ocr'] == 'SKIP':
        assert attempts == [] and entries['ocr_synthetic']['detail']
    else:
        assert len(attempts) == 1 and len(images) == 1
        if case['recognition'] == 'empty':
            assert 'Synthetic backend' in entries['ocr_synthetic']['detail']
        if case['recognition'] == 'wrong':
            assert 'acmeother' in entries['ocr_synthetic']['detail']
