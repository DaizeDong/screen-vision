"""Reproducible, in-memory synthetic screen-vision test records. No live inputs."""
import copy
import argparse
import json
from pathlib import Path


def title_discovery_cases():
    """Complete and interrupted native enumerations, using fictional windows."""
    modes = ['unique', 'absent', 'ambiguous', 'empty-title', 'enum-false',
             'enum-error', 'length-error', 'length-zero-error', 'text-zero-error', 'text-zero-noerror',
             'text-short', 'title-growth', 'title-race', 'rect-false',
             'rect-empty', 'callback-error']
    return [{'id': mode, 'reject': mode not in ('unique', 'absent', 'ambiguous', 'empty-title'),
             'windows': [{'hwnd': 0x100000101, 'title': 'Acme target', 'rect': [0, 0, 40, 40]},
                         {'hwnd': 0x100000202, 'title': 'Acme other', 'rect': [40, 0, 80, 40]}]}
            for mode in modes]


def owned_gate_cases():
    cases = [{'id': 'healthy', 'stage': None, 'fault': None, 'actions': 2}]
    faults = ['failed', 'scope', 'hwnd', 'pid', 'process_started', 'rect',
              'fallback', 'dimensions', 'element-owner', 'missing-identity']
    for stage in ('golden', 'post'):
        cases.extend({'id': stage + '-' + fault, 'stage': stage, 'fault': fault,
                      'actions': 0 if stage == 'golden' else 1} for fault in faults)
    cases.extend([{'id': 'base-failed', 'stage': 'base', 'fault': 'failed', 'actions': 0},
                  {'id': 'exited-before-bind', 'stage': 'exited', 'fault': 'failed', 'actions': 0},
                  {'id': 'identity-after-action', 'stage': 'live', 'fault': 'pid', 'actions': 1},
                  {'id': 'action-failed', 'stage': 'action', 'fault': 'failed', 'actions': 1}])
    return cases


def ocr_capability_cases():
    """Generate explicit platform/package expectations with synthetic OCR output."""
    expected_backends = {
        True: {
            'Windows': (None, 'rapidocr', 'winocr', 'winocr'),
            'Linux': (None, 'rapidocr', None, 'rapidocr'),
            'Darwin': (None, 'rapidocr', None, 'rapidocr'),
        },
        False: {
            'Windows': (None, 'rapidocr', None, 'rapidocr'),
            'Linux': (None, 'rapidocr', None, 'rapidocr'),
            'Darwin': (None, 'rapidocr', None, 'rapidocr'),
        },
    }
    cases = []
    for pillow, platforms in expected_backends.items():
        for system, backends in platforms.items():
            for index, (winocr, rapidocr) in enumerate(
                    ((False, False), (False, True), (True, False), (True, True))):
                text = 'Acme synthetic text'
                identifier = '%s-winocr%s-rapidocr%s' % (system, winocr, rapidocr)
                cases.append({
                    'id': identifier if pillow else identifier + '-pillowFalse',
                    'system': system, 'expected_backend': backends[index],
                    'libs': {'mss': True, 'uiautomation': False, 'pillow': pillow,
                             'winocr': winocr, 'rapidocr': rapidocr},
                    'png_path': 'synthetic-ocr-input.png',
                    'origin': (0, 0), 'region': (0, 0, 16, 16), 'text': text,
                    'rapidocr_result': ([[1, 1], [9, 1], [9, 5], [1, 5]], text, 0.9),
                    'winocr_result': {'lines': [{'words': [{'text': text,
                        'bounding_rect': {'x': 1, 'y': 1, 'width': 8, 'height': 4}}]}]},
                })
    return cases


def owned_gate_scene(stage, fault=None, actions=0):
    window = copy.deepcopy(element()['identity']['window'])
    window['rect'] = [0, 0, 4, 3]
    target = 'hwnd:' + str(window['hwnd'])
    button = element()
    button.update(name='Seven', label='Seven', rect=[0, 0, 2, 2], bbox=[0, 0, 2, 2],
                  center=[1, 1], capture_rect=window['rect'][:])
    button['identity']['window'] = copy.deepcopy(window)
    display = copy.deepcopy(button)
    display.update(id=1, name='7' * actions, label='7' * actions, type='text', patterns=[],
                   rect=[0, 2, 4, 3], bbox=[0, 2, 4, 1], center=[2, 2], clickable=False)
    report = {'ok': True, 'capture': {'requested_target': target, 'fallback_used': False,
              'resolved_target': {'kind': 'window', 'hwnd': window['hwnd'],
                                  'window_identity': copy.deepcopy(window), 'rect': window['rect'][:]}},
              'monitor': {'physical_size': [4, 3]}}
    resolved = report['capture']['resolved_target']
    if fault == 'failed': report['ok'] = False
    if fault == 'scope': report['capture']['requested_target'] = 'full'
    if fault in ('hwnd', 'pid', 'process_started'):
        resolved['window_identity'][fault] += 1
        if fault == 'hwnd': resolved['hwnd'] += 1
    if fault == 'rect': resolved['rect'] = [10, 10, 14, 13]
    if fault == 'fallback': report['capture']['fallback_used'] = True
    if fault == 'dimensions': report['monitor']['physical_size'] = [5, 3]
    selected = display if stage == 'post' else button
    if fault == 'element-owner': selected['identity']['window']['pid'] += 1
    if fault == 'missing-identity': selected['identity'] = None
    return {'window': window, 'target': target, 'report': report, 'elements': [button, display],
            'rgb': bytes([80, 100, 120] * 12)}


def incomplete_discovery_capture_cases():
    return [{'id': 'narrow', 'fallback': []},
            {'id': 'explicit-fallback', 'fallback': ['--allow-full-screen-fallback']}]


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


def action_readiness_test_source():
    """Reproduce synthetic desktop-readiness action regressions."""
    return '"""Generated by tools/make_fixtures.py; pure confirmed-action readiness regressions."""\nimport argparse\nimport ast\nimport builtins\nimport copy\nimport io\nimport json\nimport math\nfrom pathlib import Path\nfrom types import SimpleNamespace\nimport unittest\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef click_source():\n    return (ROOT / "skills/screen-vision/scripts/click.py").read_bytes()\n\n\ndef record():\n    return {\n        "id": 0, "type": "button", "label": "Acme action", "name": "Acme action",\n        "automation_id": "acme-action", "class_name": "Button", "source": "uia",\n        "rect": [10, 20, 50, 60], "center": [30, 40], "enabled": True,\n        "offscreen": False, "clickable": True, "patterns": ["Invoke"],\n        "captured_at": 1000.0, "capture_rect": [0, 0, 200, 200],\n        "identity": {\n            "runtime_id": [42, 7], "window_runtime_id": [42, 1],\n            "window": {"hwnd": 101, "pid": 202, "process_started": 303,\n                       "rect": [0, 0, 200, 200]},\n        },\n    }\n\n\nclass World:\n    """Run actual action/CLI definitions against an entirely in-memory desktop."""\n    def __init__(self, ready=True, *, change_at=None, changed=False,\n                 pattern=True, dispatch_failure=False):\n        self.saved = record()\n        self.ready, self.changed, self.change_at = ready, changed, change_at\n        self.pattern, self.dispatch_failure = pattern, dispatch_failure\n        self.events, self.actions, self.output = [], [], []\n        self.argv = []\n        world = self\n\n        class Control:\n            def __init__(self, runtime, children=()):\n                self.runtime, self.children = runtime, list(children)\n\n            def GetChildren(self):\n                return self.children\n\n            @property\n            def BoundingRectangle(self):\n                return SimpleNamespace(**dict(zip(("left", "top", "right", "bottom"),\n                                                 world.saved["rect"])))\n\n            @property\n            def Name(self): return world.saved["name"]\n            @property\n            def AutomationId(self): return world.saved["automation_id"]\n            @property\n            def ClassName(self): return world.saved["class_name"]\n            @property\n            def ControlTypeName(self): return "ButtonControl"\n            @property\n            def IsEnabled(self): return True\n            @property\n            def IsOffscreen(self): return False\n\n            def GetInvokePattern(self):\n                world.events.append("pattern")\n                world.change("pattern")\n                return self if world.pattern else None\n\n            def GetTogglePattern(self): return None\n            def GetSelectionItemPattern(self): return None\n            def GetExpandCollapsePattern(self): return None\n\n            def Invoke(self):\n                world.dispatch("invoke")\n\n        self.control = Control([42, 7])\n        self.root = Control([42, 1], [self.control])\n\n        def from_handle(handle):\n            self.events.append("resolve")\n            self.change("resolve")\n            assert handle == 101\n            return self.root\n\n        def from_point(x, y):\n            self.events.append("hit")\n            self.change("hit")\n            assert [x, y] == [30, 40]\n            return self.control\n\n        def identity(control, root):\n            assert control is self.control and root is self.root\n            self.events.append("identity")\n            return copy.deepcopy(self.saved["identity"])\n\n        self.auto = SimpleNamespace(ControlFromHandle=from_handle, ControlFromPoint=from_point)\n        self.common = SimpleNamespace(\n            IS_WINDOWS=True, has_interactive_desktop=self.readiness,\n            require_physical_coordinates=lambda: self.events.append("dpi"),\n            runtime_id=lambda control: control.runtime, control_identity=identity,\n            click_physical=lambda *args, **kwargs: self.dispatch("coord"),\n        )\n\n        def importing(name, *args, **kwargs):\n            if name != "uiautomation":\n                raise AssertionError("unexpected action import: " + name)\n            self.events.append("uia_import")\n            return self.auto\n\n        class Parser(argparse.ArgumentParser):\n            def parse_args(self, args=None, namespace=None):\n                return super().parse_args(world.argv if args is None else args, namespace)\n\n        def input_file(path, *args, **kwargs):\n            assert path == "synthetic-elements.json"\n            return io.StringIO(json.dumps([self.saved]))\n\n        self.namespace = {\n            "__doc__": "Synthetic confirmed-action contract.",\n            "__builtins__": dict(vars(builtins), __import__=importing),\n            "C": self.common, "math": math, "json": json,\n            "time": SimpleNamespace(time=lambda: 1001.0, monotonic=lambda: 1.0),\n            "argparse": SimpleNamespace(ArgumentParser=Parser),\n            "open": input_file, "print": lambda value: self.output.append(json.loads(value)),\n        }\n        required = {"ActionError", "find_element", "validate_capture", "validate_control",\n                    "resolve_element", "act_on_element", "main", "MAX_CAPTURE_AGE", "PATTERNS"}\n        allowed = required | {"require_ready_desktop"}\n        selected, found = [], set()\n        for node in ast.parse(click_source(), "actual-click.py").body:\n            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in allowed:\n                selected.append(node)\n                found.add(node.name)\n            elif isinstance(node, ast.Assign) and len(node.targets) == 1:\n                target = node.targets[0]\n                if isinstance(target, ast.Name) and target.id in required:\n                    selected.append(node)\n                    found.add(target.id)\n        if not required <= found:\n            raise AssertionError("actual action definition selection is incomplete")\n        exec(compile(ast.Module(body=selected, type_ignores=[]), "actual-click.py", "exec"),\n             self.namespace)\n\n    def change(self, phase):\n        if phase == self.change_at:\n            self.ready = self.changed\n\n    def readiness(self):\n        self.events.append("readiness")\n        if isinstance(self.ready, Exception):\n            raise self.ready\n        return self.ready\n\n    def dispatch(self, method):\n        self.events.append("dispatch:" + method)\n        self.actions.append(method)\n        if self.dispatch_failure:\n            raise RuntimeError("synthetic failure after dispatch started")\n        return True\n\n    def cli(self, method="auto", confirm=True, explicit_preview=False):\n        self.argv = ["--elements-json", "synthetic-elements.json", "--id", "0",\n                     "--method", method]\n        if confirm:\n            self.argv.append("--confirm")\n        elif explicit_preview:\n            self.argv.append("--dry-run")\n        code = self.namespace["main"]()\n        assert len(self.output) == 1\n        return code, self.output[0]\n\n\nclass Screen18ReadinessTests(unittest.TestCase):\n    def assert_refused(self, world, result):\n        code, report = result\n        self.assertEqual(code, 5)\n        self.assertIs(report["ok"], False)\n        self.assertIs(report["acted"], False)\n        self.assertEqual(report["error"], "no_interactive_desktop")\n        self.assertEqual(world.actions, [])\n\n    def test_initial_readiness_refuses_all_confirmed_methods(self):\n        for state in (False, None, 1, "ready", OSError("synthetic query failure")):\n            for method in ("auto", "invoke", "coord"):\n                with self.subTest(state=repr(state), method=method):\n                    world = World(state)\n                    self.assert_refused(world, world.cli(method))\n                    self.assertEqual(world.events, ["dpi", "readiness"])\n\n    def test_resolver_rejects_unready_before_uia(self):\n        for state in (False, None, 1, "ready", RuntimeError("synthetic query failure")):\n            with self.subTest(state=repr(state)):\n                world = World(state)\n                with self.assertRaises(world.namespace["ActionError"]) as caught:\n                    world.namespace["resolve_element"](world.saved)\n                self.assertEqual(caught.exception.code, "no_interactive_desktop")\n                self.assertEqual(world.events, ["dpi", "readiness"])\n                self.assertEqual(world.actions, [])\n\n    def test_readiness_change_during_resolution_or_lookup_blocks_dispatch(self):\n        scenarios = [\n            ("invoke", "resolve", True), ("invoke", "pattern", True),\n            ("auto", "pattern", True), ("coord", "resolve", True),\n            ("coord", "hit", True), ("auto", "hit", False),\n        ]\n        for method, phase, pattern in scenarios:\n            for state in (False, None, OSError("synthetic late query failure")):\n                with self.subTest(method=method, phase=phase, state=repr(state)):\n                    world = World(change_at=phase, changed=state, pattern=pattern)\n                    self.assert_refused(world, world.cli(method))\n                    self.assertEqual(world.events.count("readiness"), 2)\n                    self.assertEqual(world.events[-1], "readiness")\n                    self.assertLess(world.events.index("readiness"),\n                                    world.events.index("uia_import"))\n                    self.assertIn(phase, world.events)\n\n    def test_ready_actions_keep_exact_dispatch_and_query_order(self):\n        for method, pattern, dispatched in (\n            ("invoke", True, "invoke"), ("auto", True, "invoke"),\n            ("coord", True, "coord"), ("auto", False, "coord"),\n        ):\n            with self.subTest(method=method, pattern=pattern):\n                world = World(pattern=pattern)\n                code, report = world.cli(method)\n                self.assertEqual(code, 0)\n                self.assertIs(report["acted"], True)\n                self.assertEqual(world.actions, [dispatched])\n                self.assertEqual(world.events.count("readiness"), 2)\n                self.assertEqual(world.events[-2:], ["readiness", "dispatch:" + dispatched])\n                self.assertLess(world.events.index("readiness"),\n                                world.events.index("uia_import"))\n\n    def test_dry_preview_avoids_readiness_resolution_and_dispatch(self):\n        for explicit in (False, True):\n            with self.subTest(explicit_dry_run=explicit):\n                world = World(RuntimeError("preview must not query readiness"))\n                world.saved.pop("identity")\n                code, report = world.cli(confirm=False, explicit_preview=explicit)\n                self.assertEqual(code, 0)\n                self.assertIs(report["acted"], False)\n                self.assertIs(report["dry_run"], True)\n                self.assertEqual(report["method"], "preview")\n                self.assertEqual(world.events, [])\n                self.assertEqual(world.actions, [])\n\n    def test_dispatch_failure_remains_unknown_without_fallback(self):\n        for method in ("invoke", "coord"):\n            with self.subTest(method=method):\n                world = World(dispatch_failure=True)\n                code, report = world.cli(method)\n                self.assertEqual(code, 5)\n                self.assertIs(report["acted"], None)\n                self.assertEqual(report["error"], "action_outcome_unknown")\n                self.assertEqual(world.actions, [method])\n                self.assertEqual(world.events[-2:], ["readiness", "dispatch:" + method])\n\n    def test_missing_readiness_probe_refuses(self):\n        with self.subTest(probe="absent"):\n            world = World()\n            del world.common.has_interactive_desktop\n            self.assert_refused(world, world.cli("invoke"))\n            self.assertEqual(world.events, ["dpi"])\n'



def action_movement_test_source():
    'Reproduce synthetic pointer-movement and injection-boundary regressions.'
    return '"""Generated by tools/make_fixtures.py; synthetic pointer-movement dispatch regressions."""\nimport argparse\nimport ast\nimport builtins\nimport copy\nimport io\nimport json\nimport math\nfrom pathlib import Path\nfrom types import SimpleNamespace\nimport unittest\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef production_source(name):\n    return (ROOT / "skills/screen-vision/scripts" / name).read_bytes()\n\n\ndef generator_source():\n    return (ROOT / "tools/make_fixtures.py").read_bytes()\n\n\ndef regression_source():\n    return Path(__file__).read_bytes()\n\n\ndef record():\n    return {\n        "id": 0, "type": "button", "label": "Acme action", "name": "Acme action",\n        "automation_id": "acme-action", "class_name": "Button", "source": "uia",\n        "rect": [10, 20, 50, 60], "center": [30, 40], "enabled": True,\n        "offscreen": False, "clickable": True, "patterns": [],\n        "captured_at": 1000.0, "capture_rect": [0, 0, 200, 200],\n        "identity": {\n            "runtime_id": [42, 7], "window_runtime_id": [42, 1],\n            "window": {"hwnd": 101, "pid": 202, "process_started": 303,\n                       "rect": [0, 0, 200, 200]},\n        },\n    }\n\n\ndef variants(double=None):\n    return [(method, button, twice)\n            for method in ("coord", "auto")\n            for button in ("left", "right", "middle")\n            for twice in (False, True)\n            if double is None or twice is double]\n\n\ndef selected(source, names, namespace):\n    nodes, found = [], set()\n    for node in ast.parse(source).body:\n        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:\n            nodes.append(node)\n            found.add(node.name)\n        elif isinstance(node, ast.Assign) and len(node.targets) == 1:\n            target = node.targets[0]\n            if isinstance(target, ast.Name) and target.id in names:\n                nodes.append(node)\n                found.add(target.id)\n    assert found == names\n    exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected-production.py", "exec"),\n         namespace)\n\n\nclass World:\n    def __init__(self, fault=None, *, phase="move", pattern=False):\n        self.saved = record()\n        self.window = copy.deepcopy(self.saved["identity"]["window"])\n        self.fault, self.phase, self.pattern = fault, phase, pattern\n        self.trace, self.buttons, self.injected_targets, self.output = [], [], [], []\n        self.ready, self.now, self.pointer = True, 1001.0, (30, 40)\n        self.moved = self.changed = self.hit_error = self.identity_error = False\n        self.argv, self.invoke_calls = [], 0\n        world = self\n\n        class Control:\n            def __init__(self, runtime, *, root=False):\n                self.runtime = list(runtime)\n                self.record = copy.deepcopy(world.saved)\n                self.NativeWindowHandle, self.ProcessId = 101, 202\n                self.children = []\n                if root:\n                    self.record["rect"] = [0, 0, 200, 200]\n\n            def GetRuntimeId(self): return self.runtime\n            def GetChildren(self): return self.children\n            @property\n            def BoundingRectangle(self):\n                return SimpleNamespace(**dict(zip(("left", "top", "right", "bottom"),\n                                                 self.record["rect"])))\n            @property\n            def Name(self): return self.record["name"]\n            @property\n            def AutomationId(self): return self.record["automation_id"]\n            @property\n            def ClassName(self): return self.record["class_name"]\n            @property\n            def ControlTypeName(self): return self.record["type"].capitalize() + "Control"\n            @property\n            def IsEnabled(self): return self.record["enabled"]\n            @property\n            def IsOffscreen(self): return self.record["offscreen"]\n            def GetInvokePattern(self): return self if world.pattern else None\n            def GetTogglePattern(self): return None\n            def GetSelectionItemPattern(self): return None\n            def GetExpandCollapsePattern(self): return None\n            def Invoke(self):\n                world.trace.append("invoke")\n                world.invoke_calls += 1\n\n        self.control = Control([42, 7])\n        self.root = Control([42, 1], root=True)\n        self.root.children = [self.control]\n        self.replacement = Control([42, 999])\n        self.hit = self.control\n\n        def from_handle(hwnd):\n            self.trace.append("resolve")\n            assert hwnd == 101\n            return self.root\n\n        def from_point(x, y):\n            self.trace.append("hit")\n            assert (x, y) == (30, 40)\n            if self.hit_error:\n                raise RuntimeError("synthetic hit-test unavailable")\n            return self.hit\n\n        def window_identity(hwnd):\n            self.trace.append("identity")\n            if self.identity_error:\n                raise RuntimeError("synthetic window identity unavailable")\n            if hwnd != self.window["hwnd"]:\n                return None\n            return copy.deepcopy(self.window)\n\n        class Point:\n            def __init__(self): self.x = self.y = 0\n\n        class User32:\n            def SetCursorPos(self, x, y):\n                world.trace.append("move")\n                if world.fault == "move-error":\n                    raise OSError("synthetic movement failure")\n                if world.fault == "move-false":\n                    return 0\n                world.pointer, world.moved = (x, y), True\n                world.change("move")\n                return 1\n\n            def GetCursorPos(self, ref):\n                world.trace.append("position")\n                if world.fault == "read-error":\n                    raise OSError("synthetic pointer query failure")\n                if world.fault == "read-false":\n                    return 0\n                ref._obj.x, ref._obj.y = world.pointer\n                return 1\n\n            def mouse_event(self, flags, *args):\n                down = flags in (0x0002, 0x0008, 0x0020)\n                world.trace.append("down" if down else "up")\n                world.buttons.append(flags)\n                world.injected_targets.append(None if world.hit is None else list(world.hit.runtime))\n                if down and world.fault in ("down-error", "both-error"):\n                    raise OSError("synthetic error after down may have reached target")\n                if not down:\n                    if len(world.buttons) == 2:\n                        world.change("after-first-up")\n                    if world.fault in ("up-error", "both-error"):\n                        raise OSError("synthetic error after up may have reached target")\n\n        ctypes_facade = SimpleNamespace(\n            windll=SimpleNamespace(user32=User32()),\n            byref=lambda point: SimpleNamespace(_obj=point),\n            wintypes=SimpleNamespace(POINT=Point),\n        )\n\n        def common_import(name, *args, **kwargs):\n            assert name == "ctypes"\n            return ctypes_facade\n\n        common_ns = {\n            "__builtins__": dict(vars(builtins), __import__=common_import),\n            "ctypes": ctypes_facade, "IS_WINDOWS": True,\n            "require_physical_coordinates": lambda: self.trace.append("dpi"),\n            "window_identity": window_identity,\n        }\n        selected(production_source("_common.py"),\n                 {"click_physical", "control_identity", "runtime_id"}, common_ns)\n        self.common = SimpleNamespace(\n            IS_WINDOWS=True, has_interactive_desktop=self.readiness,\n            require_physical_coordinates=common_ns["require_physical_coordinates"],\n            control_identity=common_ns["control_identity"], runtime_id=common_ns["runtime_id"],\n            click_physical=common_ns["click_physical"],\n        )\n        auto = SimpleNamespace(ControlFromHandle=from_handle, ControlFromPoint=from_point)\n\n        def click_import(name, *args, **kwargs):\n            assert name == "uiautomation"\n            return auto\n\n        class Parser(argparse.ArgumentParser):\n            def parse_args(self, args=None, namespace=None):\n                return super().parse_args(world.argv if args is None else args, namespace)\n\n        def input_file(path, *args, **kwargs):\n            assert path == "synthetic-elements.json"\n            return io.StringIO(json.dumps([self.saved]))\n\n        self.click = {\n            "__doc__": "Synthetic pointer movement contract.",\n            "__builtins__": dict(vars(builtins), __import__=click_import),\n            "C": self.common, "math": math, "json": json,\n            "time": SimpleNamespace(time=lambda: self.now, monotonic=lambda: 1.0),\n            "argparse": SimpleNamespace(ArgumentParser=Parser),\n            "open": input_file, "print": lambda value: self.output.append(json.loads(value)),\n        }\n        selected(production_source("click.py"),\n                 {"ActionError", "find_element", "validate_capture", "validate_control",\n                  "require_ready_desktop", "resolve_element", "act_on_element", "main",\n                  "MAX_CAPTURE_AGE", "PATTERNS"}, self.click)\n\n    def change(self, phase):\n        if self.changed or phase != self.phase:\n            return\n        self.changed = True\n        fault = self.fault\n        if fault == "hover-replacement": self.hit = self.replacement\n        elif fault == "hover-empty": self.hit = None\n        elif fault == "runtime": self.control.runtime = [42, 999]\n        elif fault == "window-runtime": self.root.runtime = [42, 999]\n        elif fault in ("hwnd", "pid", "process_started"):\n            self.window[fault] += 1\n        elif fault == "window-rect": self.window["rect"] = [0, 0, 210, 210]\n        elif fault == "geometry": self.control.record["rect"] = [20, 20, 60, 60]\n        elif fault == "disabled": self.control.record["enabled"] = False\n        elif fault == "offscreen": self.control.record["offscreen"] = True\n        elif fault in ("name", "automation_id", "class_name"):\n            self.control.record[fault] = "Acme replacement"\n        elif fault == "type": self.control.record["type"] = "text"\n        elif fault == "capture-age": self.now = 1061.0\n        elif fault == "ready-false": self.ready = False\n        elif fault == "ready-none": self.ready = None\n        elif fault == "ready-error": self.ready = OSError("synthetic readiness query failure")\n        elif fault == "hit-error": self.hit_error = True\n        elif fault == "identity-error": self.identity_error = True\n        elif fault == "wrong-position": self.pointer = (300, 400)\n\n    def readiness(self):\n        self.trace.append("readiness")\n        if self.moved and self.fault == "late-pointer-drift":\n            self.pointer = (300, 400)\n        if isinstance(self.ready, Exception):\n            raise self.ready\n        return self.ready\n\n    def cli(self, method="coord", button="left", double=False):\n        self.argv = ["--elements-json", "synthetic-elements.json", "--id", "0",\n                     "--method", method, "--button", button, "--confirm"]\n        if double:\n            self.argv.append("--double")\n        code = self.click["main"]()\n        assert len(self.output) == 1\n        return code, self.output[0]\n\n\nclass Screen19MovementTests(unittest.TestCase):\n    def assert_refused(self, world, result, code="recapture_required"):\n        status, report = result\n        self.assertEqual(status, 5)\n        self.assertIs(report["ok"], False)\n        self.assertIs(report["acted"], False)\n        self.assertEqual(report["error"], code)\n        self.assertEqual(world.buttons, [])\n        self.assertEqual(world.invoke_calls, 0)\n\n    def test_unchanged_target_revalidated_after_movement_before_each_pair(self):\n        for method, button, double in variants():\n            with self.subTest(method=method, button=button, double=double):\n                world = World()\n                status, report = world.cli(method, button, double)\n                self.assertEqual(status, 0)\n                self.assertIs(report["acted"], True)\n                flags = {"left": [2, 4], "right": [8, 16], "middle": [32, 64]}[button]\n                self.assertEqual(world.buttons, flags * (2 if double else 1))\n                self.assertEqual(world.trace.count("move"), 1)\n                self.assertEqual(world.trace.count("hit"), 3 if double else 2)\n                self.assertTrue(all(value == [42, 7] for value in world.injected_targets))\n                for index, event in enumerate(world.trace):\n                    if event == "down":\n                        self.assertEqual(world.trace[index - 2:index], ["readiness", "position"])\n                self.assertEqual(world.invoke_calls, 0)\n\n    def test_movement_changes_target_window_capture_or_readiness_refuses_before_buttons(self):\n        faults = ("hover-replacement", "hover-empty", "runtime", "window-runtime",\n                  "hwnd", "pid", "process_started", "window-rect", "geometry",\n                  "disabled", "offscreen", "name", "automation_id", "class_name", "type",\n                  "capture-age", "ready-false", "ready-none", "ready-error",\n                  "hit-error", "identity-error")\n        for fault in faults:\n            for method, button, double in variants():\n                with self.subTest(fault=fault, method=method, button=button, double=double):\n                    world = World(fault)\n                    code = "no_interactive_desktop" if fault.startswith("ready-") else "recapture_required"\n                    self.assert_refused(world, world.cli(method, button, double), code)\n                    self.assertEqual(world.trace.count("move"), 1)\n\n    def test_movement_and_pointer_query_failures_emit_no_buttons(self):\n        for fault in ("move-false", "move-error", "read-false", "read-error",\n                      "wrong-position", "late-pointer-drift"):\n            for method, button, double in variants():\n                with self.subTest(fault=fault, method=method, button=button, double=double):\n                    world = World(fault)\n                    self.assert_refused(world, world.cli(method, button, double))\n                    self.assertEqual(world.trace.count("move"), 1)\n\n    def test_second_pair_refusal_is_unknown_without_retry(self):\n        for fault in ("hover-replacement", "runtime", "ready-false", "ready-error",\n                      "hit-error", "wrong-position", "capture-age"):\n            for method, button, double in variants(double=True):\n                with self.subTest(fault=fault, method=method, button=button):\n                    world = World(fault, phase="after-first-up")\n                    status, report = world.cli(method, button, double)\n                    self.assertEqual(status, 5)\n                    self.assertIs(report["acted"], None)\n                    self.assertEqual(report["error"], "action_outcome_unknown")\n                    self.assertEqual(world.buttons, {"left": [2, 4], "right": [8, 16],\n                                                     "middle": [32, 64]}[button])\n                    self.assertEqual(world.trace.count("move"), 1)\n                    self.assertEqual(world.invoke_calls, 0)\n\n    def test_dispatch_errors_attempt_matching_release_once_and_never_retry(self):\n        for fault in ("down-error", "up-error", "both-error"):\n            for method, button, double in variants():\n                with self.subTest(fault=fault, method=method, button=button, double=double):\n                    world = World(fault)\n                    status, report = world.cli(method, button, double)\n                    self.assertEqual(status, 5)\n                    self.assertIs(report["acted"], None)\n                    self.assertEqual(report["error"], "action_outcome_unknown")\n                    self.assertEqual(world.buttons, {"left": [2, 4], "right": [8, 16],\n                                                     "middle": [32, 64]}[button])\n                    self.assertEqual(world.trace.count("down"), 1)\n                    self.assertEqual(world.trace.count("up"), 1)\n                    self.assertEqual(world.trace.count("move"), 1)\n                    self.assertEqual(world.invoke_calls, 0)\n\n    def test_uia_action_does_not_move_or_inject_mouse_buttons(self):\n        for method in ("invoke", "auto"):\n            with self.subTest(method=method):\n                world = World("hover-replacement", pattern=True)\n                status, report = world.cli(method)\n                self.assertEqual(status, 0)\n                self.assertEqual(report["method"], "invoke:Invoke")\n                self.assertIs(report["acted"], True)\n                self.assertEqual(world.buttons, [])\n                self.assertNotIn("move", world.trace)\n                self.assertEqual(world.invoke_calls, 1)\n\n    def test_generator_reproduces_regression(self):\n        namespace = {}\n        selected(generator_source(), {"action_movement_test_source"}, namespace)\n        self.assertEqual(namespace["action_movement_test_source"]().encode("utf-8"),\n                         regression_source())\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, help='Write generated basenames into this directory for boundary verification.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    outputs = {
        root / 'tests/fixtures/element.json': (json.dumps(element(), indent=2) + '\n').encode('utf-8'),
        root / 'tests/test_review_v18.py': action_readiness_test_source().encode('utf-8'),
        root / 'tests/test_review_v19.py': action_movement_test_source().encode('utf-8'),
    }
    if args.out:
        outputs = {args.out / path.name: content for path, content in outputs.items()}
    if args.check:
        if any(not path.is_file() or path.read_bytes() != content
               for path, content in outputs.items()):
            print('Synthetic fixtures are missing or differ from their generator.')
            return 1
        print('Synthetic fixtures match their generator.')
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


def transport_cases():
    """Generate only fictional repository identities, routes, and settings."""
    origin = 'https://github.com/example-owner/screen-vision-config.git'
    cases = [
        {'id': 'canonical', 'allow': True},
        {'id': 'pager', 'env': {'GIT_PAGER': 'cat'}, 'allow': True},
        {'id': 'pager-commands', 'env': {'GIT_PAGER': 'synthetic-unavailable-pager',
                                      'GH_PAGER': 'synthetic-unavailable-pager',
                                      'PAGER': 'synthetic-unavailable-pager'}, 'allow': True},
        {'id': 'canonical-port', 'origin': origin.replace('github.com/', 'github.com:443/'), 'allow': True},
        {'id': 'nonstandard-port', 'origin': origin.replace('github.com/', 'github.com:8443/')},
        {'id': 'ssh-port', 'origin': 'ssh://git@github.com:2222/example-owner/screen-vision-config.git'},
        {'id': 'ssh-unproved', 'origin': 'git@github.com:example-owner/screen-vision-config.git'},
        {'id': 'userinfo', 'origin': origin.replace('github.com', 'git@github.com')},
        {'id': 'host', 'origin': origin.replace('github.com', 'example.invalid')},
        {'id': 'public-push', 'extra': [('remote.origin.pushurl', 'https://github.com/example-owner/public-output.git')], 'push': ['https://github.com/example-owner/public-output.git'], 'private': 'false'},
        {'id': 'effective-push', 'push': ['https://example.invalid/example-owner/screen-vision-config.git']},
        {'id': 'effective-fetch', 'fetch': ['https://example.invalid/example-owner/screen-vision-config.git']},
        {'id': 'visibility-public', 'private': 'false'},
        {'id': 'visibility-unknown', 'private': ''},
        {'id': 'extra-remote', 'extra': [('remote.archive.url', 'https://example.invalid/acme/archive.git')]},
    ]
    for key, value in [
        ('url.https://example.invalid/.insteadof', 'https://github.com/'),
        ('url.https://example.invalid/.pushinsteadof', 'https://github.com/'),
        ('core.sshcommand', 'synthetic-command'),
        ('core.gitproxy', 'synthetic-command'),
        ('remote.origin.receivepack', 'synthetic-command'),
        ('remote.origin.uploadpack', 'synthetic-command'),
        ('remote.origin.vcs', 'synthetic-helper'),
        ('http.proxy', 'https://example.invalid'),
        ('http.sslverify', 'false'),
        ('http.https://github.com/.sslverify', 'false'),
        ('http.sslcainfo', 'synthetic-ca'),
        ('http.followredirects', 'true'),
        ('http.extraheader', 'synthetic-header'),
        ('http.https://github.com/.proxy', ''),
        ('remote.origin.proxy', ''),
    ]:
        cases.append({'id': 'config-' + key, 'extra': [(key, value)]})
    cases.append({'id': 'duplicate-http', 'extra': [('http.sslverify', 'false'), ('http.sslverify', 'true')]})
    for key in ['HTTP_PROXY', 'https_proxy', 'ALL_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                'CURL_CA_BUNDLE', 'CURL_SSL_BACKEND', 'GIT_SSL_NO_VERIFY',
                'GIT_PROXY_SSL_CAINFO', 'GIT_EXEC_PATH', 'GIT_HTTP_USER_AGENT',
                'GIT_SSH_COMMAND', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_GLOBAL',
                'GIT_DIR', 'GIT_WORK_TREE', 'GH_HOST', 'GH_CONFIG_DIR']:
        for value in ['', 'synthetic-value']:
            cases.append({'id': 'env-' + key + ('-empty' if not value else ''), 'env': {key: value}})
    for key in ['version', 'maxrequests', 'minsessions', 'postbuffer', 'lowspeedlimit',
                'lowspeedtime', 'keepaliveidle', 'keepaliveinterval', 'keepalivecount']:
        cases.append({'id': 'performance-' + key, 'extra': [('http.' + key, '1')], 'allow': True})
    for value in ['true', 'yes', 'on', '1', ' TRUE ']:
        cases.append({'id': 'verify-' + value.strip(), 'extra': [('http.https://github.com/.sslverify', value)], 'allow': True})
    cases.append({'id': 'no-proxy-only', 'env': {'NO_PROXY': 'github.com'}, 'allow': True})
    for key in ['remote.pushdefault', 'branch.main.remote', 'branch.main.pushremote']:
        cases.append({'id': 'selector-good-' + key, 'extra': [(key, 'origin')], 'allow': True})
        cases.append({'id': 'selector-url-' + key,
                      'extra': [(key, 'https://example.invalid/acme/output.git')]})
        cases.append({'id': 'selector-unknown-' + key, 'extra': [(key, 'unconfigured')]})
        cases.append({'id': 'selector-local-' + key, 'extra': [(key, '.')]})
    for case in cases:
        case.setdefault('origin', origin)
        case.setdefault('extra', [])
        case.setdefault('fetch', [case['origin']])
        case.setdefault('push', [case['origin']])
        case.setdefault('private', 'true')
        case.setdefault('env', {})
        case['env'].setdefault('GIT_PAGER', 'cat')
        case.setdefault('allow', False)
    return cases


def screen_scene(kind='container', origin=(0, 0)):
    """Generate UIA records and a coded RGB frame, never desktop pixels."""
    x, y = origin
    rect = [x, y, x + 64, y + 64]
    root = element()
    root.update(type='window', name='ACME CANVAS', label='ACME CANVAS',
                rect=rect, bbox=[x, y, 64, 64], center=[x+32, y+32], clickable=False,
                patterns=[], identity=None)
    elements = [] if kind == 'empty' else [root]
    if kind in ('partial', 'covered', 'unnamed'):
        record = element()
        height = 64 if kind == 'covered' else 17
        record.update(type='text', name='' if kind == 'unnamed' else 'ACME KNOWN',
                      label='' if kind == 'unnamed' else 'ACME KNOWN',
                      rect=[x, y, x+64, y+height], bbox=[x, y, 64, height],
                      center=[x+32, y+height//2], clickable=False, patterns=[], identity=None)
        elements.append(record)
    if kind == 'interior':
        record = element()
        record.update(type='text', name='ACME KNOWN', label='ACME KNOWN',
                      rect=[x+20, y+20, x+40, y+40], bbox=[x+20, y+20, 20, 20],
                      center=[x+30, y+30], clickable=False, patterns=[], identity=None)
        elements.append(record)
    rgb = b''.join(bytes((23, 41, 59) if row < 17 else (101, 131, 151)) * 64 for row in range(64))
    return {'rect': rect, 'origin': [x, y], 'elements': elements, 'rgb': rgb,
            'missing': 'ACME MISSING', 'covered_color': bytes((23, 41, 59))}


def verification_gate_cases():
    """Generate explicit readiness and recognition outcomes for offline gate tests."""
    cases = []
    for level in ('per_monitor_v2', 'per_monitor', 'system', 'unverified', 'none'):
        cases.append({'id': 'dpi-' + level, 'level': level, 'recognition': 'expected',
                      'dpi': 'PASS' if level in ('per_monitor_v2', 'per_monitor') else 'FAIL',
                      'ocr': 'PASS', 'windows': True})
    for recognition, expected in [('empty', 'FAIL'), ('wrong', 'FAIL'),
                                  ('missing_engine', 'SKIP'), ('missing_pillow', 'SKIP')]:
        cases.append({'id': 'ocr-' + recognition, 'level': 'per_monitor_v2',
                      'recognition': recognition, 'dpi': 'PASS', 'ocr': expected, 'windows': True})
    cases.append({'id': 'both-fail', 'level': 'system', 'recognition': 'empty',
                  'dpi': 'FAIL', 'ocr': 'FAIL', 'windows': True})
    cases.append({'id': 'nonwindows-winocr-only', 'level': 'none', 'recognition': 'winocr_only',
                  'dpi': 'SKIP', 'ocr': 'SKIP', 'windows': False})
    cases.append({'id': 'nonwindows-supported-ocr', 'level': 'none', 'recognition': 'expected',
                  'dpi': 'SKIP', 'ocr': 'PASS', 'windows': False})
    for case in cases:
        case['labels'] = ['Open Settings'] if case['recognition'] == 'expected' else (
            ['Acme Other'] if case['recognition'] == 'wrong' else [])
        case['warnings'] = ['Synthetic backend returned no recognized text'] if case['recognition'] == 'empty' else []
    return cases


def capture_contract_cases():
    """Generate monitor, timing, persistence, and layer scenarios from constants."""
    cases = []
    for scope in ('all', 'region', 'window'):
        for placement, rect, index, scale in (
                ('primary', [-56, 4, -40, 20], 1, 1.0),
                ('secondary', [8, 4, 24, 20], 2, 1.5),
                ('spanning', [-8, 4, 8, 20], None, None),
                ('outside', [140, 4, 156, 20], None, None)):
            cases.append({'id': scope + '-' + placement, 'scope': scope,
                          'element_rect': rect, 'monitor': index, 'scale': scale})
    return cases


def capture_contract_scene(case=None):
    """Return an entirely synthetic two-monitor desktop and a bound owned window."""
    case = case or {'scope': 'all', 'element_rect': [8, 4, 24, 20]}
    rect = [-64, 0, 64, 32]
    monitors = [
        {'index': 1, 'rect': [-64, 0, 0, 32], 'origin': [-64, 0],
         'physical_size': [64, 32], 'scale': 1.0, 'primary': True},
        {'index': 2, 'rect': [0, 0, 64, 32], 'origin': [0, 0],
         'physical_size': [64, 32], 'scale': 1.5, 'primary': False}]
    identity = {'hwnd': 101, 'pid': 202, 'process_started': 303, 'rect': rect}
    scope = case['scope']
    requested = {'all': 'all', 'region': 'region:-64,0,128,32', 'window': 'hwnd:101'}[scope]
    record = element()
    l, t, r, b = case['element_rect']
    record.update(rect=[l, t, r, b], bbox=[l, t, r-l, b-t],
                  center=[(l+r)//2, (t+b)//2])
    return {'rect': rect, 'monitors': monitors, 'identity': identity,
            'requested': requested, 'elements': [record],
            'rgb': bytes((89, 121, 153)) * (128*32),
            'black_rgb': bytes(128*32*3), 'width': 128, 'height': 32,
            'start_time': 1000.0, 'preflight_delay': 75.0, 'frame_delay': 2.0}


def layer_contract_cases():
    return [{'id': 'unknown', 'layers': 'not-a-layer', 'valid': False},
            {'id': 'mixed', 'layers': 'uia,not-a-layer', 'valid': False},
            {'id': 'case-sensitive', 'layers': 'UIA', 'valid': False},
            {'id': 'capture-only', 'layers': '', 'valid': True},
            {'id': 'whitespace-only', 'layers': ' , ', 'valid': True},
            {'id': 'uia', 'layers': 'uia', 'valid': True},
            {'id': 'vision', 'layers': 'vision', 'valid': True}]


def persistence_contract_cases():
    return [{'id': name, 'filename': name, 'layers': 'ocr' if name == 'ocr-input.png' else ''}
            for name in ('screen.png', 'ocr-input.png', 'elements.json', 'capture.json')]


def action_capability_cases():
    return [{'id': '%s-uia%s-ready%s' % (system, uia, ready),
             'system': system, 'windows': system == 'Windows', 'uia': uia,
             'ready': ready, 'expected': system == 'Windows' and uia and ready,
             'libs': {'mss': True, 'pyautogui': True, 'uiautomation': uia,
                      'winocr': False, 'rapidocr': False, 'pillow': False}}
            for system in ('Windows', 'Linux', 'Darwin')
            for uia in (False, True) for ready in (False, True)]


def owned_capture_gate_cases():
    """Generate accepted and refused capture reports, including dishonest quality metadata."""
    cases = []
    for kind in ('healthy', 'black', 'wrong-size', 'wrong-hwnd', 'wrong-pid',
                 'fallback', 'wrong-scope', 'changed-window', 'invalid-png', 'failed'):
        scene = capture_contract_scene({'scope': 'window', 'element_rect': [8, 4, 24, 20]})
        resolved = {'kind': 'window', 'hwnd': scene['identity']['hwnd'],
                    'rect': scene['rect'], 'window_identity': copy.deepcopy(scene['identity'])}
        report = {'ok': True, 'capture': {'requested_target': scene['requested'],
                  'resolved_target': resolved, 'fallback_used': False},
                  'monitor': {'physical_size': [scene['width'], scene['height']]},
                  'quality': {'blackness': 0.0, 'valid_dimensions': True}, 'warnings': []}
        if kind == 'black':
            scene['rgb'] = scene['black_rgb']
        elif kind == 'wrong-size':
            scene['width'] = 64
            scene['rgb'] = bytes((89, 121, 153)) * (64*32)
        elif kind == 'wrong-hwnd':
            resolved['hwnd'] += 1
        elif kind == 'wrong-pid':
            resolved['window_identity']['pid'] += 1
        elif kind == 'fallback':
            report['capture']['fallback_used'] = True
        elif kind == 'wrong-scope':
            resolved['kind'] = 'all'
        elif kind == 'failed':
            report['ok'] = False
        cases.append({'id': kind, 'scene': scene, 'report': report,
                      'png_invalid': kind == 'invalid-png',
                      'window_changed': kind == 'changed-window',
                      'expected': 'PASS' if kind == 'healthy' else 'FAIL'})
    return cases


def uia_integrity_cases():
    """Generate UIA trees and provider faults without inspecting a real desktop."""
    cases = []
    modes = (
        'healthy', 'root-none-window', 'root-none-hwnd', 'root-error',
        'child-error', 'sibling-error', 'nested-child-error',
        'healthy-broad', 'desktop-none', 'top-child-error', 'top-sibling-error',
        'no-qualified-top', 'empty-desktop', 'offscreen-parent',
        'outside-parent', 'empty-healthy',
    )
    for mode in modes:
        root = {'name': 'Acme root', 'type': 'WindowControl', 'children': ['leaf'],
                'rect': [0, 0, 40, 40]}
        leaf = {'name': 'Acme leaf', 'type': 'ButtonControl', 'children': [],
                'rect': [4, 4, 12, 12]}
        desktop = {'name': 'Acme desktop', 'type': 'PaneControl',
                   'children': ['root'], 'rect': [0, 0, 100, 100]}
        nodes = {'root': root, 'leaf': leaf, 'desktop': desktop}
        kind = 'all' if mode in ('healthy-broad', 'desktop-none', 'top-child-error',
                                'top-sibling-error', 'no-qualified-top', 'empty-desktop') else 'window'
        if mode == 'root-none-hwnd':
            kind = 'hwnd'
        expected = ['Acme root', 'Acme leaf']
        warn = mode not in ('healthy', 'healthy-broad', 'offscreen-parent',
                            'outside-parent', 'empty-healthy')
        if mode.startswith('root-none') or mode in ('root-error', 'desktop-none',
                                                   'top-child-error', 'no-qualified-top', 'empty-desktop'):
            expected = []
        if mode == 'child-error':
            root['child_error'] = True
            expected = ['Acme root']
        if mode == 'sibling-error':
            leaf['sibling_error'] = True
        if mode == 'nested-child-error':
            leaf['child_error'] = True
        if mode == 'top-child-error':
            desktop['child_error'] = True
        if mode == 'top-sibling-error':
            root['sibling_error'] = True
        if mode == 'no-qualified-top':
            root['type'] = 'GroupControl'
        if mode == 'empty-desktop':
            desktop['children'] = []
        if mode == 'offscreen-parent':
            root['offscreen'] = True
        if mode == 'outside-parent':
            root['rect'] = [200, 200, 240, 240]
            expected = ['Acme leaf']
        if mode == 'empty-healthy':
            root.update(name='', type='GroupControl', children=[])
            expected = []
        target = {'kind': kind, 'hwnd': 101,
                  'window_identity': {'hwnd': 101, 'pid': 202}}
        cases.append({'id': mode, 'nodes': nodes, 'target': target,
                      'region': [0, 0, 100, 100], 'expected_labels': expected,
                      'warning_required': warn,
                      'forbid_desktop_walk': mode in ('no-qualified-top', 'empty-desktop')})
    return cases


def delegate_hook_integrity_cases():
    """Generate regular-file, content-size and execute-bit predicate controls."""
    cases = []
    for regular in (False, True):
        for size in (0, 20):
            for executable in (False, True):
                cases.append({'id': 'regular%s-size%s-exec%s' % (regular, size, executable),
                              'regular': regular, 'size': size, 'executable': executable,
                              'must_block': not regular or size == 0})
    return cases


def uia_sibling_cap_cases():
    """Generate exact and overflow UIA sibling caps without native provider calls."""
    cases = []
    for scope, limit in (("children", 400), ("nested-children", 400), ("roots", 200)):
        for count in (0, limit - 1, limit, limit + 1, limit + 5):
            root = {"name": "Acme root", "type": "WindowControl",
                    "children": [], "rect": [0, 0, 40, 40]}
            desktop = {"name": "Acme desktop", "type": "PaneControl",
                       "children": ["root"], "rect": [0, 0, 100, 100]}
            nodes = {"root": root, "desktop": desktop}
            keys = ["node-%03d" % index for index in range(count)]
            for key in keys:
                nodes[key] = {"name": "Acme " + key,
                              "type": "WindowControl" if scope == "roots" else "ButtonControl",
                              "children": [], "rect": [4, 4, 12, 12]}
            if scope == "roots":
                desktop["children"] = keys
                expected = ["Acme " + key for key in keys[:limit]]
            elif scope == "nested-children":
                root["children"] = ["branch"]
                nodes["branch"] = {"name": "Acme branch", "type": "PaneControl",
                                   "children": keys, "rect": [0, 0, 40, 40]}
                expected = ["Acme root", "Acme branch"] + ["Acme " + key for key in keys[:limit]]
            else:
                root["children"] = keys
                expected = ["Acme root"] + ["Acme " + key for key in keys[:limit]]
            cases.append({
                "id": "%s-%d" % (scope, count), "scope": scope, "count": count, "limit": limit,
                "nodes": nodes, "target": {"kind": "all" if scope == "roots" else "hwnd",
                                          "hwnd": 101, "window_identity": {"hwnd": 101, "pid": 202}},
                "region": [0, 0, 100, 100], "expected_labels": expected,
                "warning_required": count > limit or (scope == "roots" and count == 0),
                "partial_warning_required": count > limit,
                "pending_key": keys[limit] if count > limit else None,
                "expected_sibling_calls": min(count, limit) + (1 if scope == "nested-children" else 0),
            })
    return cases

def uia_depth_cap_cases():
    """Generate exact-depth and actual truncation trees without native providers."""
    cases = []
    for name, limit, heights in (
        ("below-default", 50, [49]),
        ("exact-default", 50, [50]),
        ("beyond-default", 50, [51]),
        ("root-only", 0, []),
        ("cap-zero-overflow", 0, [1]),
        ("exact-one", 1, [1]),
        ("beyond-one", 1, [2]),
        ("branches-overflow", 2, [3, 3, 3]),
        ("mixed-branches", 2, [2, 3]),
    ):
        root = {"name": "Acme root", "type": "WindowControl",
                "children": [], "rect": [0, 0, 40, 40]}
        nodes = {"root": root}
        expected = [root["name"]]
        skipped = []
        for branch, height in enumerate(heights):
            parent = "root"
            for depth in range(1, height + 1):
                key = "branch-%d-depth-%d" % (branch, depth)
                nodes[key] = {"name": "Acme " + key, "type": "ButtonControl",
                              "children": [], "rect": [4, 4, 12, 12]}
                nodes[parent]["children"].append(key)
                if depth <= limit:
                    expected.append(nodes[key]["name"])
                else:
                    skipped.append(key)
                parent = key
        cases.append({
            "id": name, "nodes": nodes, "max_depth": limit,
            "target": {"kind": "hwnd", "hwnd": 101,
                       "window_identity": {"hwnd": 101, "pid": 202}},
            "region": [0, 0, 100, 100], "expected_labels": expected,
            "skipped_keys": skipped, "partial_warning_required": bool(skipped),
        })
    return cases


def uia_property_failure_cases():
    """Generate unavailable UIA properties and healthy descendant observations."""
    recipes = [
        ("healthy", [], True, False, True, False, 1.0, False),
        ("disabled", [], False, False, False, False, 1.0, False),
        ("offscreen", [], True, True, True, True, 1.0, True),
        ("enabled-failed", ["IsEnabled"], False, False, None, False, None, False),
        ("offscreen-failed", ["IsOffscreen"], True, True, True, None, None, True),
        ("both-state-failed", ["IsEnabled", "IsOffscreen"], False, True, None, None, None, True),
        ("bounds-failed", ["BoundingRectangle"], True, False, True, False, None, True),
    ]
    cases = []
    for (name, failures, enabled, offscreen, expected_enabled, expected_offscreen,
         confidence, needs_ocr) in recipes:
        rect = [0, 0, 16, 16]
        window = {"hwnd": 101, "pid": 202, "process_started": 303, "rect": rect[:]}
        nodes = {
            "root": {"name": "", "type": "WindowControl", "rect": rect[:],
                     "children": ["subject"], "enabled": True, "offscreen": False, "failures": []},
            "subject": {"name": "Acme text", "type": "TextControl", "rect": rect[:],
                        "children": ["child"], "enabled": enabled, "offscreen": offscreen,
                        "failures": failures[:]},
            "child": {"name": "Acme descendant", "type": "ButtonControl", "rect": [4, 4, 8, 8],
                      "children": [], "enabled": True, "offscreen": False, "failures": []},
        }
        action = element()
        action.update(enabled=expected_enabled, offscreen=expected_offscreen, confidence=confidence)
        cases.append({
            "id": name, "nodes": nodes, "region": rect, "window": window,
            "target": {"kind": "window", "hwnd": 101, "rect": rect[:], "window_identity": window},
            "expected_labels": ["Acme descendant"] if name == "bounds-failed" else
                               ["Acme text", "Acme descendant"],
            "expected_enabled": expected_enabled, "expected_offscreen": expected_offscreen,
            "expected_confidence": confidence, "failed_properties": failures[:],
            "needs_ocr": needs_ocr, "rgb": bytes((61, 97, 131)) * (16 * 16),
            "action": None if name == "bounds-failed" else action, "action_allowed": name == "healthy",
        })
    return cases
