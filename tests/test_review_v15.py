"""Generated UIA property-failure regressions with inert capture and action boundaries."""
import argparse
import ast
import copy
from contextlib import redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = "skills/screen-vision/scripts/"


def load_definitions(relative, names, namespace):
    """Load selected source definitions without native module initialization."""
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    selected, found = [], set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            matched = {target.id for target in node.targets
                       if isinstance(target, ast.Name) and target.id in names}
            if matched:
                selected.append(node)
                found.update(matched)
    if found != set(names):
        raise AssertionError("Source definition selection is incomplete")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def cases():
    namespace = load_definitions("tools/make_fixtures.py",
                                 {"element", "uia_property_failure_cases"}, {"copy": copy})
    return namespace["uia_property_failure_cases"]()


def collect_case(case):
    helpers = load_definitions("tests/test_review_v12.py", {"Node"},
                               {"SimpleNamespace": SimpleNamespace})

    class PropertyNode(helpers["Node"]):
        def __getattribute__(self, name):
            if name in ("BoundingRectangle", "IsEnabled", "IsOffscreen"):
                spec = object.__getattribute__(self, "spec")
                if name in spec["failures"]:
                    raise RuntimeError("Synthetic unavailable " + name)
                if name == "IsEnabled":
                    return spec["enabled"]
                if name == "IsOffscreen":
                    return spec["offscreen"]
            return super().__getattribute__(name)

    visits = []
    nodes = {key: PropertyNode(key, spec, visits) for key, spec in case["nodes"].items()}
    for key, node in nodes.items():
        node.children = [nodes[child] for child in case["nodes"][key]["children"]]
        for first, second in zip(node.children, node.children[1:]):
            first.sibling = second
    provider = SimpleNamespace(ControlFromHandle=lambda hwnd: nodes["root"])
    common = SimpleNamespace(IS_WINDOWS=True, control_identity=lambda *args: None,
                             window_identity=lambda hwnd: copy.deepcopy(case["window"]))
    namespace = load_definitions(SCRIPTS + "capture.py",
        {"collect_uia", "_uia_type", "verify_target", "TargetError", "CLICKABLE_TYPES"},
        {"C": common, "time": SimpleNamespace(time=lambda: 1000.0)})
    warnings = []
    with patch.dict(sys.modules, {"uiautomation": provider}):
        rows = namespace["collect_uia"](case["target"], 50, case["region"], warnings)
    return rows, warnings, visits


def publish_case(case, rows, upstream_warnings):
    """Exercise the actual capture consumer with synthetic pixels and memory-only writers."""
    pure = load_definitions(SCRIPTS + "pure_ops.py",
        {"_blackness", "capture_with_retry", "compute_ocr_regions", "ocr_pixels"}, {})
    ocr_calls, images, artifacts = [], {}, {}

    class SyntheticWindowDiscoveryError(RuntimeError):
        pass

    def unexpected_annotation(*args):
        raise AssertionError("Annotation is disabled in generated property scenarios")

    def collect(target, depth, region, warnings):
        warnings.extend(upstream_warnings)
        return copy.deepcopy(rows)

    def ocr(path, engine, origin, region, boxes, warnings):
        ocr_calls.append((path, origin, region, boxes))
        return []

    def write_png(path, rgb, width, height):
        images[path] = (rgb, width, height)

    common = SimpleNamespace(
        require_physical_coordinates=lambda: None,
        WindowDiscoveryError=SyntheticWindowDiscoveryError,
        enum_monitors=lambda: [{"index": 1, "rect": case["region"][:],
                               "origin": [0, 0], "scale": 1.0}],
        validate_monitor_geometry=lambda monitors: None,
        has_interactive_desktop=lambda: True, is_wayland=lambda: False,
        write_png=write_png, blackness=lambda *args: 0.0,
        _DPI_STATE={"level": "synthetic"})
    namespace = load_definitions(SCRIPTS + "capture.py", {"capture_main", "monitor_for_rect", "TargetError"}, {
        "argparse": argparse, "json": json, "time": SimpleNamespace(time=lambda: 1000.0),
        "C": common, "P": SimpleNamespace(**pure),
        "os": SimpleNamespace(path=os.path, makedirs=lambda *args, **kwargs: None),
        "resolve_target": lambda *args: {"kind": "region", "rect": case["region"][:]},
        "artifact_directory": lambda requested: "synthetic-output",
        "grab_target": lambda target: (case["rgb"], 16, 16, "synthetic"),
        "persist_artifact": lambda path, writer: writer(),
        "collect_uia": collect, "collect_ocr": ocr, "verify_target": lambda target: None,
        "annotate": unexpected_annotation,
        "write_json_artifact": lambda path, value: artifacts.update({path: copy.deepcopy(value)}),
    })
    output = io.StringIO()
    with patch.object(sys, "argv", ["capture.py", "--target", "region:0,0,16,16",
                                   "--layers", "uia,ocr", "--annotate", "false", "--json-stdout"]):
        with redirect_stdout(output):
            code = namespace["capture_main"]()
    return code, json.loads(output.getvalue()), ocr_calls, images, artifacts


class Screen15PropertyTests(unittest.TestCase):
    def test_property_failures_are_unknown_and_keep_healthy_descendants(self):
        for case in cases():
            with self.subTest(case=case["id"]):
                rows, warnings, visits = collect_case(case)
                self.assertEqual([row["label"] for row in rows], case["expected_labels"])
                self.assertEqual(len(warnings), len(case["failed_properties"]))
                for name in case["failed_properties"]:
                    self.assertTrue(any(name in warning and "incomplete" in warning
                                        for warning in warnings))
                child = next(row for row in rows if row["label"] == "Acme descendant")
                self.assertIs(child["enabled"], True)
                self.assertIs(child["offscreen"], False)
                self.assertEqual(child["confidence"], 1.0)
                self.assertIn(("child", "child"), visits)
                subject = next((row for row in rows if row["label"] == "Acme text"), None)
                if subject is not None:
                    self.assertIs(subject["enabled"], case["expected_enabled"])
                    self.assertIs(subject["offscreen"], case["expected_offscreen"])
                    self.assertEqual(subject["confidence"], case["expected_confidence"])

    def test_unknown_visibility_does_not_mask_or_skip_ocr(self):
        for case in cases():
            with self.subTest(case=case["id"]):
                rows, warnings, _ = collect_case(case)
                code, result, calls, images, artifacts = publish_case(case, rows, warnings)
                self.assertEqual(code, 0)
                self.assertIs(result["ok"], True)
                self.assertEqual(bool(calls), case["needs_ocr"])
                self.assertTrue(all(warning in result["warnings"] for warning in warnings))
                if case["id"] != "bounds-failed":
                    subject = next(row for row in result["elements"] if row["label"] == "Acme text")
                    self.assertIs(subject["enabled"], case["expected_enabled"])
                    self.assertIs(subject["offscreen"], case["expected_offscreen"])
                    self.assertEqual(subject["confidence"], case["expected_confidence"])
                self.assertIn(result["capture_manifest"], artifacts)
                self.assertEqual(artifacts[result["capture_manifest"]]["warnings"], result["warnings"])
                if case["needs_ocr"]:
                    self.assertEqual(images[calls[0][0]], (case["rgb"], 16, 16))

    def test_unknown_captured_availability_cannot_authorize_action(self):
        namespace = load_definitions(SCRIPTS + "click.py", {"ActionError", "validate_capture", "MAX_CAPTURE_AGE"},
                                     {"math": math, "time": SimpleNamespace(time=lambda: 1001.0)})
        for case in cases():
            if case["action"] is None:
                continue
            with self.subTest(case=case["id"]):
                if case["action_allowed"]:
                    namespace["validate_capture"](case["action"])
                else:
                    with self.assertRaises(namespace["ActionError"]) as rejected:
                        namespace["validate_capture"](case["action"])
                    self.assertEqual(rejected.exception.code, "recapture_required")


if __name__ == "__main__":
    unittest.main()
