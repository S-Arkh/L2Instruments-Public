import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document
SCHEMA = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
FIXTURES = json.loads((ROOT / 'tests/fixtures/manifest.json').read_text())


def hf():
    doc = Document(SCHEMA)
    doc.load(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    return doc


def json_button(tree, name='btnCredit'):
    fields = tree['fields']
    if tree['type'].endswith('.Button') and fields.get('name', {}).get('value') == name:
        return tree
    for entry in fields.values():
        for child in entry.get('items', []):
            result = json_button(child, name)
            if result:
                return result
        if entry.get('object'):
            result = json_button(entry['object'], name)
            if result:
                return result
    return None


@pytest.mark.parametrize('fixture', FIXTURES, ids=[f['file'] for f in FIXTURES])
def test_xdat_json_xdat_identical(fixture):
    original = (ROOT / 'tests/fixtures' / fixture['file']).read_bytes()
    doc = Document(SCHEMA)
    doc.load_bytes(original, fixture['schema'])
    text = doc.to_json()
    assert json.loads(text)['schema'] == fixture['schema']
    imported = Document(SCHEMA)
    imported.from_json(text)
    assert imported.serialize() == original
    assert imported.summary()['dirty'] and not imported.summary()['file']


def test_json_edits_override_raw_and_allow_list_changes(tmp_path):
    doc = hf()
    data = json.loads(doc.to_json())
    button = json_button(data['tree'])
    button['fields']['name']['value'] = 'btnEditedInJSON'
    # Stale original raw bytes are deliberately retained.
    button['fields']['size_absolute_width']['value'] = 177
    doc.from_json(json.dumps(data))
    node = doc.search('btnEditedInJSON')['matches'][0]
    assert next(p['value'] for p in doc.properties(node) if p['name'] == 'size_absolute_width') == 177
    doc.set(node, 'name', 'btnUnsavedExport')
    output = tmp_path / 'document.json'
    doc.export_json(str(output))
    assert doc.summary()['dirty']
    previous = output.read_bytes()
    doc.export_json(str(output))
    assert output.with_suffix('.json.bak').read_bytes() == previous
    restored = Document(SCHEMA)
    restored.open_json(str(output))
    assert restored.serialize() == doc.serialize()
    assert restored.search('btnUnsavedExport')['matches']


def test_invalid_json_keeps_existing_document():
    doc = hf()
    original = doc.serialize()
    source = json.loads(doc.to_json())
    bad = copy.deepcopy(source)
    json_button(bad['tree'])['fields']['size_absolute_width']['value'] = 2**40
    with pytest.raises(RuntimeError): doc.from_json(json.dumps(bad))
    assert doc.serialize() == original
    bad = copy.deepcopy(source)
    json_button(bad['tree'])['fields']['name']['raw'] = 'not-hex'
    with pytest.raises(RuntimeError): doc.from_json(json.dumps(bad))
    bad = copy.deepcopy(source)
    json_button(bad['tree'])['type'] = 'ct26.Shortcut'
    with pytest.raises(RuntimeError): doc.from_json(json.dumps(bad))
    bad = copy.deepcopy(source)
    del json_button(bad['tree'])['fields']['name']
    with pytest.raises((RuntimeError, IndexError)): doc.from_json(json.dumps(bad))
    with pytest.raises((RuntimeError, ValueError)): doc.from_json('{bad JSON')
    assert doc.serialize() == original and not doc.summary()['dirty']


def test_json_nan_tail_and_inactive_fields():
    doc = hf()
    doc.load_bytes(doc.serialize() + b'extra-opaque-tail', 'ct26.XDAT')
    original = doc.serialize()
    data = json.loads(doc.to_json())
    assert 'extra-opaque-tail'.encode().hex() in data['tree']['fields']['_tail']['raw']
    doc.from_json(json.dumps(data))
    assert doc.serialize() == original
    button = json_button(data['tree'])
    button['fields']['anchor_x'] = {'value': 'NaN', 'raw': '0100c07f'}
    button['fields']['fontName']['value'] = 'inactive font is retained'
    doc.from_json(json.dumps(data))
    result = json_button(json.loads(doc.to_json())['tree'])
    assert result['fields']['anchor_x']['raw'] == '0100c07f'
    assert result['fields']['fontName']['value'] == 'inactive font is retained'


def test_json_structural_edit_updates_list_count():
    doc = hf()
    data = json.loads(doc.to_json())
    windows = data['tree']['fields']['windows']
    duplicate = copy.deepcopy(windows['items'][0])
    duplicate['fields']['name']['value'] += '_from_json'
    windows['items'].append(duplicate)
    doc.from_json(json.dumps(data))
    encoded = doc.serialize()
    decoded = Document(SCHEMA)
    decoded.load_bytes(encoded, 'ct26.XDAT')
    assert len(json.loads(decoded.to_json())['tree']['fields']['windows']['items']) == len(windows['items'])


def test_search_neighbors_and_inactive_metadata():
    doc = hf()
    original = doc.serialize()
    credit = next(n for n in doc.search('btnCredit')['matches'] if doc.info(n)['type'] == 'Button')
    parent = doc.info(credit)['parent']
    siblings = {n['id'] for n in doc.children(parent)}
    strict = doc.search('btnCredit')
    context = doc.search('btnCredit', True)
    assert not siblings.issubset(set(strict['visible']))
    assert siblings.issubset(set(context['visible']))
    assert strict['matches'] == context['matches']
    assert any(not p['active'] for p in doc.properties(credit, True))
    assert all(p['active'] for p in doc.properties(credit))
    assert doc.serialize() == original


def test_previous_document_marker_is_still_readable():
    doc = hf(); original = doc.serialize()
    data = json.loads(doc.to_json())
    assert data['format'] == 'interface-editor-document'
    data['format'] = 'xdat-editor-document'
    doc.from_json(json.dumps(data))
    assert doc.serialize() == original
