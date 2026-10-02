"""Focused author controls for bounded UIA traversal, using generated trees."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "skills/screen-vision/scripts/capture.py"
GENERATOR = ROOT / "tools/make_fixtures.py"
ORIGINAL_HELPER = ROOT / "tests/test_review_v12.py"


def generated_cases():
    namespace = {"__name__": "screen13_synthetic_generator", "__file__": str(GENERATOR)}
    exec(compile(GENERATOR.read_bytes(), str(GENERATOR), "exec"), namespace)
    return namespace["uia_sibling_cap_cases"]()


def scene_runner():
    """Reuse only the admitted Node/run_scene helpers; run no original test class."""
    tree = ast.parse(ORIGINAL_HELPER.read_bytes(), str(ORIGINAL_HELPER))
    selected = [node for node in tree.body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                and node.name in {"Node", "run_scene"}]
    if len(selected) != 2:
        raise AssertionError("Original helper identity changed")
    namespace = {"ast": ast, "sys": sys, "SimpleNamespace": SimpleNamespace, "CAPTURE": CAPTURE}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(ORIGINAL_HELPER), "exec"), namespace)
    return namespace["run_scene"]


class Screen13AuthorTests(unittest.TestCase):
    def check_scope(self, scope):
        run = scene_runner()
        for case in generated_cases():
            if case["scope"] != scope:
                continue
            with self.subTest(case=case["id"]):
                result, warnings, calls = run(case)
                self.assertEqual([item["label"] for item in result], case["expected_labels"])
                self.assertEqual(bool(warnings), case["warning_required"])
                partial = [warning for warning in warnings if "partial" in warning]
                self.assertEqual(bool(partial), case["partial_warning_required"])
                if partial:
                    self.assertEqual(len(partial), 1)
                    self.assertIn(str(case["limit"]), partial[0])
                sibling_calls = [call for call in calls if call[1] == "sibling"]
                self.assertEqual(len(sibling_calls), case["expected_sibling_calls"])
                if case["pending_key"] is not None:
                    self.assertNotIn((case["pending_key"], "child"), calls)
                    self.assertNotIn((case["pending_key"], "sibling"), calls)
                if scope == "roots":
                    self.assertEqual(calls.count(("desktop", "child")), 1)
                else:
                    self.assertNotIn(("provider", "desktop"), calls)

    def test_child_cap_exact_and_overflow(self):
        self.check_scope("children")

    def test_nested_child_cap_exact_and_overflow(self):
        self.check_scope("nested-children")

    def test_top_level_cap_exact_and_overflow(self):
        self.check_scope("roots")
