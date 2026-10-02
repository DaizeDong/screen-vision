"""Author-only controls using generated provider trees and shell predicate interpretation."""
import ast
import json
from pathlib import Path
import re
import shlex
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "skills/screen-vision/scripts/capture.py"
GENERATOR = ROOT / "tools/make_fixtures.py"


def generated():
    namespace = {"__name__": "author_synthetic_generator", "__file__": str(GENERATOR)}
    exec(compile(GENERATOR.read_bytes(), str(GENERATOR), "exec"), namespace)
    return namespace


class Node:
    def __init__(self, key, spec, calls):
        self.key, self.spec, self.calls = key, spec, calls
        self.ControlTypeName = spec["type"]
        self.Name = spec["name"]
        self.AutomationId = ""
        self.ClassName = ""
        self.IsOffscreen = spec.get("offscreen", False)
        self.IsEnabled = True
        l, t, r, b = spec["rect"]
        self.BoundingRectangle = SimpleNamespace(left=l, top=t, right=r, bottom=b)
        self.children = []
        self.sibling = None

    def GetFirstChildControl(self):
        self.calls.append((self.key, "child"))
        if self.spec.get("child_error"):
            raise RuntimeError("synthetic child enumeration fault")
        return self.children[0] if self.children else None

    def GetNextSiblingControl(self):
        self.calls.append((self.key, "sibling"))
        if self.spec.get("sibling_error"):
            raise RuntimeError("synthetic sibling enumeration fault")
        return self.sibling


def run_scene(case):
    calls = []
    nodes = {key: Node(key, spec, calls) for key, spec in case["nodes"].items()}
    for key, node in nodes.items():
        node.children = [nodes[name] for name in case["nodes"][key]["children"]]
        for first, second in zip(node.children, node.children[1:]):
            first.sibling = second

    def from_handle(hwnd):
        calls.append(("provider", "handle"))
        if case["id"] == "root-error":
            raise RuntimeError("synthetic missing root")
        return None if case["id"].startswith("root-none") else nodes["root"]

    def desktop():
        calls.append(("provider", "desktop"))
        return None if case["id"] == "desktop-none" else nodes["desktop"]

    provider = SimpleNamespace(ControlFromHandle=from_handle, GetRootControl=desktop)
    common = SimpleNamespace(
        IS_WINDOWS=True, control_identity=lambda *args: None,
        window_identity=lambda hwnd: case["target"]["window_identity"])
    tree = ast.parse(CAPTURE.read_bytes(), str(CAPTURE))
    selected = [node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name in {"_uia_type", "collect_uia", "TargetError", "verify_target"}]
    selected += [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "CLICKABLE_TYPES"
                         for target in node.targets)]
    namespace = {"C": common, "time": SimpleNamespace(time=lambda: 1000.0)}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(CAPTURE), "exec"), namespace)
    previous = sys.modules.get("uiautomation")
    sys.modules["uiautomation"] = provider
    warnings = []
    try:
        result = namespace["collect_uia"](case["target"], 20, case["region"], warnings)
    finally:
        if previous is None:
            sys.modules.pop("uiautomation", None)
        else:
            sys.modules["uiautomation"] = previous
    return result, warnings, calls


def delegate_blocks(source, case):
    """Interpret only the exact leading POSIX test list; no native shell is run."""
    match = re.search(r"^if (.+); then$", source, re.MULTILINE)
    if match is None:
        raise AssertionError("missing delegated-hook admission predicate")
    tokens = shlex.split(match.group(1))
    tests, joins = [], []
    while tokens:
        if tokens.pop(0) != "[":
            raise AssertionError("unsupported shell predicate")
        close = tokens.index("]")
        expr, tokens = tokens[:close], tokens[close + 1:]
        invert = expr[0] == "!"
        if invert:
            expr = expr[1:]
        if len(expr) != 2 or expr[1] != "$_REAL":
            raise AssertionError("unexpected delegate target")
        values = {"-f": case["regular"], "-s": case["size"] > 0,
                  "-x": case["executable"]}
        if expr[0] not in values:
            raise AssertionError("unsupported test operator")
        value = values[expr[0]]
        tests.append(not value if invert else value)
        if tokens:
            op = tokens.pop(0)
            if op not in ("&&", "||"):
                raise AssertionError("unsupported shell Boolean operator")
            joins.append(op)
    result = tests[0]
    for op, value in zip(joins, tests[1:]):
        result = result and value if op == "&&" else result or value
    return result


class Screen12AuthorTests(unittest.TestCase):
    def test_uia_enumeration_reports_incomplete_results(self):
        for case in generated()["uia_integrity_cases"]():
            if case["forbid_desktop_walk"]:
                continue
            with self.subTest(case=case["id"]):
                result, warnings, calls = run_scene(case)
                self.assertEqual([item["label"] for item in result], case["expected_labels"])
                self.assertEqual(bool(warnings), case["warning_required"])
                if case["target"]["kind"] in ("window", "hwnd"):
                    self.assertNotIn(("provider", "desktop"), calls)

    def test_broad_capture_never_deep_walks_desktop_root(self):
        for case in generated()["uia_integrity_cases"]():
            if not case["forbid_desktop_walk"]:
                continue
            with self.subTest(case=case["id"]):
                result, warnings, calls = run_scene(case)
                self.assertEqual(result, [])
                self.assertTrue(warnings)
                self.assertEqual(calls.count(("desktop", "child")), 1)
                self.assertNotIn(("root", "child"), calls)
                self.assertNotIn(("leaf", "child"), calls)

    def test_delegates_require_nonempty_regular_hook(self):
        for name in ("pre-commit", "pre-push"):
            source = (ROOT / ".githooks" / name).read_text(encoding="utf-8")
            for case in generated()["delegate_hook_integrity_cases"]():
                with self.subTest(hook=name, case=case["id"]):
                    self.assertEqual(delegate_blocks(source, case), case["must_block"])
            self.assertIn('exec sh "$_REAL" "$@"', source)

    def test_original_fixture_still_matches_generator(self):
        content = (json.dumps(generated()["element"](), indent=2) + "\n").encode("utf-8")
        self.assertEqual((ROOT / "tests/fixtures/element.json").read_bytes(), content)
