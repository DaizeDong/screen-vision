
"""Focused author controls for actual UIA depth truncation."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "skills/screen-vision/scripts/capture.py"
GENERATOR = ROOT / "tools/make_fixtures.py"
ORIGINAL_HELPER = ROOT / "tests/test_review_v12.py"


def generated_cases(name):
    tree = ast.parse(GENERATOR.read_bytes(), str(GENERATOR))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(selected) != 1:
        raise AssertionError("Synthetic generator identity changed")
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(GENERATOR), "exec"), namespace)
    return namespace[name]()


def run_scene(case, initial_warnings=()):
    """Execute admitted collector definitions against generated provider objects."""
    tree = ast.parse(ORIGINAL_HELPER.read_bytes(), str(ORIGINAL_HELPER))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Node"]
    if len(selected) != 1:
        raise AssertionError("Original Node helper identity changed")
    helpers = {"SimpleNamespace": SimpleNamespace}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(ORIGINAL_HELPER), "exec"), helpers)

    class ObservedNode(helpers["Node"]):
        def __getattribute__(self, name):
            if name == "BoundingRectangle":
                self.calls.append((self.key, "bounds"))
            return super().__getattribute__(name)

    calls = []
    nodes = {key: ObservedNode(key, spec, calls) for key, spec in case["nodes"].items()}
    for key, node in nodes.items():
        node.children = [nodes[name] for name in case["nodes"][key]["children"]]
        for first, second in zip(node.children, node.children[1:]):
            first.sibling = second

    def from_handle(hwnd):
        calls.append(("provider", "handle"))
        return nodes["root"]

    def desktop():
        calls.append(("provider", "desktop"))
        return nodes["desktop"]

    provider = SimpleNamespace(ControlFromHandle=from_handle, GetRootControl=desktop)
    common = SimpleNamespace(IS_WINDOWS=True, control_identity=lambda *args: None,
                             window_identity=lambda hwnd: case["target"]["window_identity"])
    tree = ast.parse(CAPTURE.read_bytes(), str(CAPTURE))
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name in {"_uia_type", "collect_uia", "TargetError", "verify_target"}]
    selected += [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "CLICKABLE_TYPES"
                         for target in node.targets)]
    if len(selected) != 5:
        raise AssertionError("Collector definition identity changed")
    namespace = {"C": common, "time": SimpleNamespace(time=lambda: 1000.0)}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(CAPTURE), "exec"), namespace)
    previous = sys.modules.get("uiautomation")
    sys.modules["uiautomation"] = provider
    warnings = list(initial_warnings)
    try:
        result = namespace["collect_uia"](case["target"], case.get("max_depth", 20), case["region"], warnings)
    finally:
        if previous is None:
            sys.modules.pop("uiautomation", None)
        else:
            sys.modules["uiautomation"] = previous
    return result, warnings, calls


class Screen14AuthorTests(unittest.TestCase):
    def check_depth(self, case):
        result, warnings, calls = run_scene(case)
        self.assertEqual([item["label"] for item in result], case["expected_labels"])
        self.assertEqual(bool(warnings), case["partial_warning_required"])
        if case["partial_warning_required"]:
            self.assertEqual(len(warnings), 1)
            self.assertIn("partial", warnings[0])
            self.assertIn("depth", warnings[0])
            self.assertIn(str(case["max_depth"]), warnings[0])
        for key in case["skipped_keys"]:
            self.assertNotIn((key, "bounds"), calls)
            self.assertNotIn((key, "child"), calls)
        self.assertNotIn(("provider", "desktop"), calls)

    def test_exact_depth_leaves_do_not_warn(self):
        for case in generated_cases("uia_depth_cap_cases"):
            if not case["partial_warning_required"]:
                with self.subTest(case=case["id"]):
                    self.check_depth(case)

    def test_actual_depth_truncation_warns_once(self):
        for case in generated_cases("uia_depth_cap_cases"):
            if case["partial_warning_required"]:
                with self.subTest(case=case["id"]):
                    self.check_depth(case)

    def test_existing_warning_is_preserved(self):
        case = next(row for row in generated_cases("uia_depth_cap_cases") if row["id"] == "branches-overflow")
        _, warnings, _ = run_scene(case, ["synthetic upstream note"])
        self.assertEqual(warnings[0], "synthetic upstream note")
        self.assertEqual(len(warnings), 2)
        self.assertIn("partial", warnings[1])

    def test_repaired_sibling_caps_are_preserved(self):
        for case in generated_cases("uia_sibling_cap_cases"):
            with self.subTest(case=case["id"]):
                result, warnings, calls = run_scene(case)
                self.assertEqual([item["label"] for item in result], case["expected_labels"])
                self.assertEqual(bool(warnings), case["warning_required"])
                partial = [warning for warning in warnings if "partial" in warning]
                self.assertEqual(bool(partial), case["partial_warning_required"])
                if partial:
                    self.assertEqual(len(partial), 1)
                self.assertEqual(sum(call[1] == "sibling" for call in calls), case["expected_sibling_calls"])
                if case["pending_key"] is not None:
                    self.assertNotIn((case["pending_key"], "bounds"), calls)
                    self.assertNotIn((case["pending_key"], "child"), calls)
                    self.assertNotIn((case["pending_key"], "sibling"), calls)
