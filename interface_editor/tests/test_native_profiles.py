"""Synthetic native-profile branch coverage, independent of private client files."""
import sys

import pytest
from synthetic_fixtures import ROOT
from _interface_core import Document

sys.path.insert(0, str(ROOT / 'tools'))
from create_native_fixture import fixture


@pytest.mark.parametrize('schema', ['essence_native.XDAT', 'korea_native.XDAT'])
def test_native_profile_branches_lists_json_and_undo(schema):
    catalog = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    doc = fixture(catalog, schema)
    data = doc.serialize()
    parsed = Document(catalog)
    parsed.load_bytes(data, schema)
    assert parsed.serialize() == data
    diagnostic = parsed.diagnose(data, schema, 100000)
    assert diagnostic['compatible'] and diagnostic['cursor'] == len(data)
    assert diagnostic['tail_bytes'] == 0 and not diagnostic['trace_truncated']
    trace = diagnostic['trace']
    assert any(e.get('field') == 'complexText' and e.get('value') == 'Fixture complex text' for e in trace)
    assert sum(e.get('field') == 'drawType' for e in trace) == 4
    byte_fields = [e for e in trace if e.get('kind') == 'byte']
    assert len(byte_fields) == 10 and all(e['size'] == 1 for e in byte_fields)
    assert any(e['value'] == 255 for e in byte_fields)
    assert any(e['path'] == '$.defaultPositionGroups[1].positions[0].x' and e.get('value') == 12 for e in trace)
    assert any(e['path'] == '$.fontDefinition.defaultFontName' and e.get('value') == 'FixtureFont' for e in trace)
    other = 'korea_native.XDAT' if schema == 'essence_native.XDAT' else 'essence_native.XDAT'
    assert not parsed.probe(data, other)['compatible']
    restored = Document(catalog)
    restored.from_json(parsed.to_json())
    assert restored.serialize() == data
    windows = next(n['id'] for n in parsed.children() if n['name'] == 'windows')
    original = parsed.children(windows)[0]['id']
    duplicate = parsed.duplicate(original)
    changed = parsed.serialize()
    assert changed != data
    restored.load_bytes(changed, schema)
    assert restored.serialize() == changed
    parsed.remove(duplicate)
    assert parsed.serialize() == data
    parsed.undo()
    assert parsed.serialize() == changed
    parsed.undo()
    assert parsed.serialize() == data
    parsed.set(0, 'hasFontDefinition', 0)
    no_font = parsed.serialize()
    assert len(no_font) < len(data)
    restored.load_bytes(no_font, schema)
    assert restored.serialize() == no_font
    parsed.undo()
    assert parsed.serialize() == data
