"""Legacy trailers remain intact across edits; inspection must not invent checksums."""
import json
import struct
import sys
import zlib

import pytest
from synthetic_fixtures import ROOT
from _interface_core import Document

sys.path.insert(0, str(ROOT / 'tools'))
from inspect_xdat_tail import inspect


@pytest.mark.parametrize('schema', ['ct24.XDAT', 'ct26.XDAT'])
@pytest.mark.parametrize('tail', [b'', struct.pack('<5I', 0, 7, 19, 0x12345678, 0), b'arbitrary trailer'])
def test_legacy_tail_edit_json_and_undo(schema, tail):
    catalog = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(catalog)
    doc.create(schema)
    windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
    doc.add_configured(windows, schema.replace('.XDAT', '.Window'), {'name': 'TailFixture'})
    original = doc.serialize() + tail
    doc.load_bytes(original, schema)
    assert doc.serialize() == original
    windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
    window = doc.children(windows)[0]['id']
    doc.set(window, 'name', 'LongerTailFixtureName')
    edited = doc.serialize()
    diagnostic = doc.diagnose(edited, schema, 1)
    assert diagnostic['compatible'] and diagnostic['tail_bytes'] == len(tail)
    if tail:
        assert edited[-len(tail):] == tail
    restored = Document(catalog)
    restored.from_json(doc.to_json())
    assert restored.serialize() == edited
    doc.undo()
    assert doc.serialize() == original
    report = inspect(original, catalog, schema)
    assert report['tail_bytes'] == len(tail)
    if len(tail) == 20:
        assert report['words_le'] == [0, 7, 19, 0x12345678, 0]
        assert not report['word12_matches_payload_crc32']
        assert report['preservation'] == 'verbatim'
    else:
        assert 'words_le' not in report
    assert 'TailFixture' not in json.dumps(report)


@pytest.mark.parametrize('schema', ['ct24.XDAT', 'ct26.XDAT'])
def test_legacy_checksum_is_inspected_but_never_rewritten(schema):
    catalog = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(catalog)
    doc.create(schema)
    payload = doc.serialize()
    tail = struct.pack('<5I', 0, 7, 19, zlib.crc32(payload), 0)
    original = payload + tail
    doc.load_bytes(original, schema)
    report = doc.diagnose(original, schema, 1)['legacy_tail']
    assert report['checksum_matches'] and report['offset'] == len(payload)
    props = {p['name']: p for p in doc.properties(0)}
    assert props['_tail_crc32']['value'] == zlib.crc32(payload)
    assert all(props[name]['readonly'] for name in props if name.startswith('_tail_'))
    with pytest.raises((RuntimeError, IndexError)):
        doc.set(0, '_tail_crc32', 0)
    windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
    doc.add_configured(windows, schema.replace('.XDAT', '.Window'), {'name': 'ChecksumEdit'})
    edited = doc.serialize()
    assert edited[-20:] == tail
    assert not doc.diagnose(edited, schema, 1)['legacy_tail']['checksum_matches']
    assert inspect(edited, catalog, schema)['checksum_status'] == 'mismatch'
    doc.undo()
    assert doc.serialize() == original
    assert doc.diagnose(original, schema, 1)['legacy_tail']['checksum_matches']


@pytest.mark.parametrize('tail', [b'', b'opaque trailer', bytes(range(20)), b'\0' * 19, b'\0' * 21])
def test_nonmatching_trailers_remain_opaque(tail):
    catalog = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(catalog)
    doc.create('ct26.XDAT')
    data = doc.serialize() + tail
    doc.load_bytes(data, 'ct26.XDAT')
    assert 'legacy_tail' not in doc.diagnose(data, 'ct26.XDAT', 1)
    assert not any(p['name'].startswith('_tail_') for p in doc.properties(0))
    assert doc.serialize() == data
