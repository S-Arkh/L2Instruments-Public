import pytest
from synthetic_fixtures import ROOT
from _interface_core import Document


def test_create_roundtrip_and_failed_create_preserves_edits():
    schema = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(schema)
    doc.create('ct26.XDAT')
    assert doc.summary()['dirty'] and not doc.summary()['file']
    windows = next(n['id'] for n in doc.children(doc.summary()['root']) if n['name'] == 'windows')
    doc.add_configured(windows, 'ct26.Window', {'name': 'OriginalSyntheticWindow'})
    before = doc.serialize()
    with pytest.raises(RuntimeError, match='Unknown schema'):
        doc.create('missing.XDAT')
    assert doc.serialize() == before
    reloaded = Document(schema)
    reloaded.load_bytes(before, 'ct26.XDAT')
    assert reloaded.search('OriginalSyntheticWindow')['matches']
    assert reloaded.serialize() == before
