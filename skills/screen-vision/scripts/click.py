#!/usr/bin/env python3
"""Preview by default; act only on a fresh, revalidated UIA identity and scope."""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

MAX_CAPTURE_AGE = 60.0
PATTERNS = (('Invoke', 'GetInvokePattern', 'Invoke'),
            ('Toggle', 'GetTogglePattern', 'Toggle'),
            ('SelectionItem', 'GetSelectionItemPattern', 'Select'),
            ('Expand', 'GetExpandCollapsePattern', 'Expand'))


class ActionError(Exception):
    def __init__(self, detail, code='recapture_required'):
        super().__init__(detail)
        self.code = code


def find_element(elements, eid):
    if not isinstance(elements, list):
        raise ValueError('elements-json must contain a list')
    matches = [el for el in elements if isinstance(el, dict) and el.get('id') == eid]
    if len(matches) != 1:
        raise ValueError('element ID is missing or ambiguous')
    return matches[0]


def validate_capture(el):
    try:
        age = time.time() - float(el['captured_at'])
        if not math.isfinite(age) or not 0 <= age <= MAX_CAPTURE_AGE:
            raise ValueError('capture is expired or has a future timestamp')
        identity = el['identity']
        if el['source'] != 'uia' or not identity['runtime_id'] or not identity['window_runtime_id']:
            raise ValueError('element has no verifiable UIA identity')
        window = identity['window']
        if any(type(window[key]) is not int or window[key] <= 0 for key in ('hwnd', 'pid', 'process_started')):
            raise ValueError('incomplete window/process identity')
        l, t, r, b = el['rect']
        sl, st, sr, sb = el['capture_rect']
        if not (sl <= l < r <= sr and st <= t < b <= sb):
            raise ValueError('element is outside the captured scope')
        if not el['enabled'] or el['offscreen']:
            raise ValueError('element was disabled or offscreen')
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ActionError(str(exc)) from exc


def validate_control(control, root, el):
    """Recheck process lifetime and semantic/physical identity immediately before dispatch."""
    validate_capture(el)
    if C.control_identity(control, root) != el['identity']:
        raise ActionError('window, process or UIA runtime identity changed')
    rect = control.BoundingRectangle
    current = [rect.left, rect.top, rect.right, rect.bottom]
    fields = (('Name', 'name'), ('AutomationId', 'automation_id'), ('ClassName', 'class_name'))
    if any(getattr(control, prop) != el.get(field) for prop, field in fields):
        raise ActionError('element name, automation ID or class changed')
    if control.ControlTypeName.replace('Control', '').lower() != el['type']:
        raise ActionError('element type changed')
    if current != el['rect'] or not control.IsEnabled or control.IsOffscreen:
        raise ActionError('element geometry or availability changed')
    return [(current[0] + current[2]) // 2, (current[1] + current[3]) // 2]


def resolve_element(el):
    validate_capture(el)
    if not C.IS_WINDOWS:
        raise ActionError('verified desktop actions require Windows UIA')
    try:
        C.require_physical_coordinates()
    except RuntimeError as exc:
        raise ActionError(str(exc), 'dpi_awareness_unverified') from exc
    try:
        import uiautomation as auto
        root = auto.ControlFromHandle(el['identity']['window']['hwnd'])
        if root is None:
            raise ActionError('captured window no longer exists')
        stack, matches, count = [(root, 0)], [], 0
        deadline = time.monotonic() + 3.0
        while stack:
            node, depth = stack.pop()
            count += 1
            if count > 10000 or depth > 50 or time.monotonic() > deadline:
                raise ActionError('UIA lookup exceeded its bounded search; narrow and recapture')
            if C.runtime_id(node) == el['identity']['runtime_id']:
                matches.append(node)
            stack.extend((child, depth + 1) for child in node.GetChildren())
        if len(matches) != 1:
            raise ActionError('element runtime ID is absent or ambiguous in the captured window')
        control = matches[0]
        validate_control(control, root, el)
        return auto, root, control
    except ActionError:
        raise
    except Exception as exc:
        raise ActionError('UIA re-resolution unavailable: %s' % exc) from exc


def act_on_element(el, method='auto', button='left', double=False):
    auto, root, control = resolve_element(el)
    use_patterns = method in ('auto', 'invoke') and button == 'left' and not double
    if method == 'invoke' and not use_patterns:
        raise ActionError('right/middle/double actions require method coord', 'invalid_action')
    if use_patterns:
        for name, getter, action in PATTERNS:
            try:
                pattern = getattr(control, getter)()
            except Exception as exc:
                raise ActionError('pattern availability cannot be verified: %s' % exc) from exc
            if pattern is None:
                continue
            validate_control(control, root, el)
            try:
                getattr(pattern, action)()
            except Exception as exc:
                raise ActionError('UIA dispatch failed; inspect the result before retrying: %s' % exc,
                                  'action_outcome_unknown') from exc
            return 'invoke:' + name
    if method == 'invoke':
        raise ActionError('verified element has no actionable UIA pattern', 'action_unavailable')
    center = validate_control(control, root, el)
    hit = auto.ControlFromPoint(*center)
    if hit is None:
        raise ActionError('no control under the freshly resolved center')
    validate_control(hit, root, el)
    center = validate_control(control, root, el)
    try:
        acted = C.click_physical(*center, button=button, double=double)
    except Exception as exc:
        raise ActionError('physical dispatch outcome unknown: %s' % exc, 'action_outcome_unknown') from exc
    if not acted:
        raise ActionError('physical dispatch did not confirm success', 'action_outcome_unknown')
    return 'coord'


def try_uia_invoke(el):
    """Compatibility helper; failure never authorizes a coordinate fallback."""
    try:
        return True, act_on_element(el, method='invoke'), 'ok'
    except Exception as exc:
        return False, None, str(exc)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elements-json', required=True)
    ap.add_argument('--id', type=int, required=True)
    ap.add_argument('--button', default='left', choices=['left', 'right', 'middle'])
    ap.add_argument('--double', action='store_true')
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--dry-run', dest='dry_run', action='store_true')
    group.add_argument('--confirm', dest='dry_run', action='store_false')
    ap.set_defaults(dry_run=True)
    ap.add_argument('--method', default='auto', choices=['auto', 'invoke', 'coord'])
    args = ap.parse_args()
    try:
        with open(args.elements_json, encoding='utf-8') as handle:
            el = find_element(json.load(handle), args.id)
    except (OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'acted': False, 'error': 'invalid_elements', 'detail': str(exc)}))
        return 2
    target = {key: el.get(key) for key in ('id', 'label', 'type', 'center', 'clickable', 'patterns')}
    if args.dry_run:
        print(json.dumps({'ok': True, 'acted': False, 'dry_run': True, 'method': 'preview',
                          'target': target, 'note': 'Preview does not validate current identity. --confirm rechecks it.'}))
        return 0
    try:
        method = act_on_element(el, args.method, args.button, args.double)
    except Exception as exc:
        code = exc.code if isinstance(exc, ActionError) else 'recapture_required'
        print(json.dumps({'ok': False, 'acted': False if code != 'action_outcome_unknown' else None,
                          'dry_run': False, 'error': code, 'detail': str(exc), 'target': target,
                          'next_step': 'Inspect the application state and capture again before another action.'}))
        return 5
    print(json.dumps({'ok': True, 'acted': True, 'dry_run': False, 'method': method, 'target': target}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
