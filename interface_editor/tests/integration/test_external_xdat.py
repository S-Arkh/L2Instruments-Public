"""Opt-in checks against independently supplied real XDAT fixtures."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from _interface_core import Document
from schema_catalog import profile_text

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((Path(__file__).parent / 'fixture-manifest.json').read_text())


@pytest.mark.skipif(not os.environ.get('INTERFACE_XDAT_FIXTURES'),
                    reason='Set INTERFACE_XDAT_FIXTURES to an external fixture directory')
@pytest.mark.parametrize('fixture', MANIFEST, ids=[f['file'] for f in MANIFEST])
def test_external_roundtrip(fixture):
    data = (Path(os.environ['INTERFACE_XDAT_FIXTURES']) / fixture['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == fixture['sha256']
    text = profile_text(fixture['schema'])
    doc = Document(text)
    doc.load_bytes(data, fixture['schema'])
    assert doc.serialize() == data
    imported = Document(text)
    imported.from_json(doc.to_json())
    assert imported.serialize() == data
