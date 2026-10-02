"""Live desktop reads require an explicit pytest option; ordinary tests are offline."""
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/screen-vision/scripts'))
sys.path.insert(0, str(ROOT / 'tools'))


def pytest_addoption(parser):
    parser.addoption('--interactive-desktop', action='store_true', default=False,
                     help='Allow tests marked interactive_desktop to read the current desktop.')


def pytest_configure(config):
    config.addinivalue_line('markers', 'interactive_desktop: reads the current desktop with explicit opt-in')


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--interactive-desktop'):
        marker = pytest.mark.skip(reason='live desktop read not requested (--interactive-desktop)')
        for item in items:
            if 'interactive_desktop' in item.keywords:
                item.add_marker(marker)
