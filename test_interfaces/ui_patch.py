"""Add an ordinary XDAT Test button anchored left of an existing login button.

This changes layout only. A matching script handler must be compiled separately.
GFx buttons are not represented by this operation.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def records(node):
    yield node
    for value in node['fields'].values():
        for child in value.get('items', []):
            if isinstance(child, dict) and 'fields' in child:
                yield from records(child)
        if value.get('object'):
            yield from records(value['object'])


def add_button(document, window_name, login_name, test_name='Btn_CompilerTest', gap=7):
    if gap < 0:
        raise ValueError('Button gap must be nonnegative')
    windows = [r for r in records(document['tree']) if r['type'].endswith('.Window')
               and r['fields'].get('name', {}).get('value') == window_name]
    if len(windows) != 1:
        raise ValueError('Expected exactly one ordinary login window')
    window = windows[0]
    if any(r['fields'].get('name', {}).get('value') == test_name for r in records(window)):
        raise ValueError('Test button already exists')
    locations = []
    for parent in records(window):
        for field in parent['fields'].values():
            for index, item in enumerate(field.get('items', [])):
                if isinstance(item, dict) and item.get('type', '').endswith('.Button') and item['fields'].get('name', {}).get('value') == login_name:
                    locations.append((field['items'], index, item))
    if len(locations) != 1:
        raise ValueError('Expected exactly one ordinary login button')
    items, index, original = locations[0]
    button = copy.deepcopy(original)
    fields = button['fields']
    modern = 'relativeTo' in fields
    values = dict(name=test_name, buttonName=-1, buttonNameText='Test', anchor_x=-float(gap), anchor_y=0.0)
    if modern:
        values.update(relativeTo=login_name, relativePoint=3, anchorPoint=1, usePosition=1, anchored=1)
    else:
        values.update(anchor_ctrl=login_name, anchor_parent=1, anchor_this=3, anchor=1)
    for name, value in values.items():
        if name not in fields or 'value' not in fields[name]:
            raise ValueError('Unsupported button schema field: ' + name)
        fields[name]['value'] = value
    items.insert(index, button)
    return dict(window=window_name, login_button=login_name, test_button=test_name,
                position='left_of_login', gap=gap, script_handler_installed=False,
                client_visual_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--window', required=True)
    parser.add_argument('--login-button', required=True)
    parser.add_argument('--menu-bottom', action='store_true',
                        help='Append Test below the last legacy menu button')
    parser.add_argument('--login-overlay', action='store_true',
                        help='Create a separate ordinary Japanese login-state window')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'test_interfaces/local'):
        parser.error('Output must be a new file beneath test_interfaces/local')
    if out.exists() or out.with_suffix('.json').exists():
        parser.error('Output already exists')
    sys.path.insert(0, str(ROOT/'interface_editor/app'))
    from _interface_core import Document
    from schema_catalog import catalog_text
    catalog = catalog_text()
    source = args.input.read_bytes()
    doc = Document(catalog)
    doc.load_bytes(source, args.schema)
    if doc.serialize() != source:
        raise ValueError('Input schema does not preserve the original bytes')
    data = json.loads(doc.to_json())
    if args.menu_bottom and args.login_overlay:
        parser.error('Choose only one placement mode')
    report = (add_login_overlay(data, args.window, args.login_button) if args.login_overlay
              else add_menu_button(data, args.window, args.login_button) if args.menu_bottom
              else add_button(data, args.window, args.login_button))
    modified = Document(catalog)
    modified.from_json(json.dumps(data))
    result = modified.serialize()
    reloaded = Document(catalog)
    reloaded.load_bytes(result, args.schema)
    if reloaded.serialize() != result:
        raise ValueError('Modified layout failed byte roundtrip')
    # Removing the new control must reconstruct the complete original layout.
    restored = json.loads(reloaded.to_json())
    removed = 0
    for parent in records(restored['tree']):
        if (report.get('original_window_height') is not None and
                parent['type'].endswith('.Window') and
                parent['fields'].get('name', {}).get('value') == report['window']):
            parent['fields']['size_absolute_height']['value'] = report['original_window_height']
        for field in parent['fields'].values():
            items = field.get('items', [])
            for index in range(len(items)-1, -1, -1):
                item = items[index]
                if isinstance(item, dict) and item.get('fields', {}).get('name', {}).get('value') == report.get('remove_control', report['test_button']):
                    del items[index]
                    removed += 1
    check = Document(catalog)
    check.from_json(json.dumps(restored))
    if removed != 1 or check.serialize() != source:
        raise ValueError('Changes extend beyond the added button')
    report.update(input_sha256=hashlib.sha256(source).hexdigest(),
                  output_sha256=hashlib.sha256(result).hexdigest(), schema=args.schema,
                  unrelated_bytes_preserved=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as stream:
        stream.write(result)
    out.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def add_login_overlay(document, window_name, button_name):
    all_records = list(records(document['tree']))
    if any(r['fields'].get('name', {}).get('value') == 'CompilerTestWnd' for r in all_records):
        raise ValueError('Overlay already exists')
    windows = [r for r in all_records if r['type'] == 'essence_native.Window' and
               r['fields'].get('name', {}).get('value') == window_name]
    if len(windows) != 1:
        raise ValueError('Expected one Japanese ordinary window template')
    original = windows[0]
    controls = list(records(original))
    buttons = [r for r in controls if r['type'].endswith('.Button') and
               r['fields'].get('name', {}).get('value') == button_name]
    texts = [r for r in controls if r['type'].endswith('.TextBox')]
    if len(buttons) != 1 or not texts:
        raise ValueError('Missing overlay control templates')
    window, button, text = [copy.deepcopy(r) for r in (original, buttons[0], texts[0])]

    def set_values(record, **values):
        for key, value in values.items():
            if key not in record['fields']:
                raise ValueError('Missing overlay schema field: '+key)
            record['fields'][key]['value'] = value

    set_values(window, name='CompilerTestWnd', script='CompilerTestWnd', state='LoginState',
               size_absolute_width=360, size_absolute_height=90, anchored=1,
               relativePoint=9, anchorPoint=9, relativeTo='', anchor_x=-20.0,
               anchor_y=-40.0, hidden=0, frame=0, exitbutton=0, movable=0,
               draggable=0, alwaysOnTop=1, backTex='undefined')
    set_values(button, name='Btn_CompilerTest', parentName='CompilerTestWnd',
               size_absolute_width=120, size_absolute_height=30, anchored=1,
               relativePoint=1, anchorPoint=1, relativeTo='', anchor_x=230.0,
               anchor_y=50.0, buttonName=-1, buttonNameText='Test')
    set_values(text, name='Txt_Result', parentName='CompilerTestWnd',
               size_absolute_width=360, size_absolute_height=45, anchored=1,
               relativePoint=1, anchorPoint=1, relativeTo='', anchor_x=0.0,
               anchor_y=0.0, text='Compiler tests: System/test.txt', sysstring=-1,
               systemMsg=-1)
    window['fields']['children']['items'] = [text, button]
    for parent in all_records:
        for field in parent['fields'].values():
            items = field.get('items', [])
            if any(item is original for item in items):
                items.append(window)
                return dict(window='CompilerTestWnd', test_button='Btn_CompilerTest',
                            remove_control='CompilerTestWnd', position='login_screen_overlay',
                            script_handler_installed=False, client_visual_tested=False)
    raise ValueError('Window container missing')


def add_menu_button(document, window_name, last_button):
    windows = [r for r in records(document['tree']) if r['type'].endswith('.Window')
               and r['fields'].get('name', {}).get('value') == window_name]
    if len(windows) != 1 or window_name != 'LoginMenuWnd':
        raise ValueError('Expected the legacy LoginMenuWnd')
    window = windows[0]
    controls = list(records(window))
    if any(r['fields'].get('name', {}).get('value') == 'Btn_CompilerTest' for r in controls):
        raise ValueError('Test button already exists')
    buttons = [r for r in controls if r['type'].endswith('.Button')]
    selected = [r for r in buttons if r['fields'].get('name', {}).get('value') == last_button]
    if len(selected) != 1:
        raise ValueError('Expected one template button')
    original = selected[0]
    y = original['fields']['anchor_y']['value']
    if any(b['fields']['anchor_y']['value'] > y for b in buttons):
        raise ValueError('Template must be the last menu button')
    positions = sorted({b['fields']['anchor_y']['value'] for b in buttons})
    if len(positions) < 2:
        raise ValueError('Cannot infer menu row spacing')
    step = positions[-1] - positions[-2]
    button = copy.deepcopy(original)
    for key, value in dict(name='Btn_CompilerTest', buttonName=-1,
                           buttonNameText='Test', anchor_y=y+step).items():
        button['fields'][key]['value'] = value
    for parent in controls:
        for field in parent['fields'].values():
            items = field.get('items', [])
            for index, item in enumerate(items):
                if item is original:
                    items.insert(index+1, button)
                    height = window['fields']['size_absolute_height']['value']
                    window['fields']['size_absolute_height']['value'] = int(height+step)
                    return dict(window=window_name, template_button=last_button,
                                test_button='Btn_CompilerTest', position='bottom_right_menu',
                                row_spacing=step, original_window_height=height,
                                script_handler_installed=False, client_visual_tested=False)
    raise ValueError('Template container not found')


if __name__ == '__main__':
    main()
