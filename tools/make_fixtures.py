"""Reproducible, in-memory synthetic screen-vision test records. No live inputs."""
import copy
import argparse
import json
from pathlib import Path


def element(captured_at=1000.0):
    return copy.deepcopy({
        'id': 0, 'type': 'button', 'label': 'Acme action', 'name': 'Acme action',
        'automation_id': 'acme-action', 'class_name': 'Button', 'source': 'uia',
        'rect': [10, 20, 50, 60], 'bbox': [10, 20, 40, 40], 'center': [30, 40],
        'enabled': True, 'offscreen': False, 'clickable': True, 'patterns': ['Invoke'],
        'confidence': 1.0, 'monitor': 1, 'scale': 1.0, 'origin': [0, 0],
        'captured_at': captured_at, 'capture_rect': [0, 0, 200, 200],
        'identity': {
            'runtime_id': [42, 7], 'window_runtime_id': [42, 1],
            'window': {'hwnd': 101, 'pid': 202, 'process_started': 303,
                       'rect': [0, 0, 200, 200]},
        },
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, help='Write the generated basename into this directory for boundary verification.')
    args = parser.parse_args()
    path = args.out / 'element.json' if args.out else Path(__file__).resolve().parents[1] / 'tests/fixtures/element.json'
    content = (json.dumps(element(), indent=2) + '\n').encode('utf-8')
    if args.check:
        if not path.is_file() or path.read_bytes() != content:
            print('Synthetic element fixture is missing or differs from its generator.')
            return 1
        print('Synthetic element fixture matches its generator.')
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
