import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document

SCHEMA = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
FIXTURES = json.loads((ROOT / 'tests/fixtures/manifest.json').read_text())


@pytest.mark.parametrize('fixture', FIXTURES, ids=[f['file'] for f in FIXTURES])
def test_roundtrip(fixture):
    data = (ROOT / 'tests/fixtures' / fixture['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == fixture['sha256']
    doc = Document(SCHEMA)
    doc.load_bytes(data, fixture['schema'])
    assert doc.serialize() == data


def hf():
    doc = Document(SCHEMA)
    doc.load(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    return doc


def button(doc):
    return next(i for i in doc.search('btnCredit')['matches'] if doc.info(i)['type'] == 'Button')


def test_edit_undo_redo_and_save(tmp_path):
    doc = hf()
    original = doc.serialize()
    node = button(doc)
    old = next(p['value'] for p in doc.properties(node) if p['name'] == 'name')
    doc.set(node, 'name', 'btnNativeTest')
    changed = doc.serialize()
    assert changed != original
    assert doc.info(node)['name'] == 'btnNativeTest'
    assert doc.undo() and doc.serialize() == original
    assert doc.info(node)['name'] == old
    assert doc.redo() and doc.serialize() == changed
    target = tmp_path / 'interface.xdat'
    target.write_bytes(original)
    doc.save(str(target))
    assert target.read_bytes() == changed
    assert target.with_suffix('.xdat.bak').read_bytes() == original
    reloaded = Document(SCHEMA)
    reloaded.load(str(target), 'ct26.XDAT')
    assert reloaded.search('btnNativeTest')['matches']


def test_duplicate_delete_and_undo():
    doc = hf(); original = doc.serialize(); node = button(doc)
    clone = doc.duplicate(node)
    assert clone != node
    assert doc.info(clone)['name'] != doc.info(node)['name']
    changed = doc.serialize()
    reload = Document(SCHEMA); reload.load_bytes(changed, 'ct26.XDAT')
    assert reload.serialize() == changed
    with pytest.raises(RuntimeError): doc.set(clone, 'name', doc.info(node)['name'])
    doc.remove(clone)
    assert doc.serialize() == original
    assert doc.undo() and doc.serialize() == changed
    assert doc.undo() and doc.serialize() == original


def test_truncated_and_unknown_schema():
    data = (ROOT / 'tests/fixtures/Interface_high_five.xdat').read_bytes()
    doc = Document(SCHEMA)
    for size in (0, 1, 4, 100, len(data)//2):
        with pytest.raises((RuntimeError, IndexError, ValueError)): doc.load_bytes(data[:size], 'ct26.XDAT')
    with pytest.raises(RuntimeError): doc.load_bytes(data, 'unknown.XDAT')


def test_conditional_fields_and_new_button():
    doc = hf(); original = doc.serialize(); node = button(doc)
    doc.set(node, 'size', 0)
    assert 'size_absolute_width' not in [p['name'] for p in doc.properties(node)]
    changed = doc.serialize()
    reload = Document(SCHEMA); reload.load_bytes(changed, 'ct26.XDAT')
    assert reload.serialize() == changed
    assert doc.undo() and doc.serialize() == original
    parent = doc.info(node)['parent']
    new = doc.add(parent, 'ct26.Button')
    doc.set(new, 'name', 'btnAddedByNativeEditor')
    reload.load_bytes(doc.serialize(), 'ct26.XDAT')
    assert reload.search('btnAddedByNativeEditor')['matches']


def test_unknown_tail_and_failed_open_preserve_document():
    doc = hf()
    data = doc.serialize() + b'custom opaque trailing bytes'
    doc.load_bytes(data, 'ct26.XDAT')
    assert doc.serialize() == data
    with pytest.raises(RuntimeError): doc.load_bytes(b'bad', 'ct26.XDAT')
    assert doc.serialize() == data


def test_dirty_state_after_save_undo_and_branch(tmp_path):
    doc = hf(); node = button(doc)
    doc.set(node, 'name', 'first')
    doc.save(str(tmp_path / 'saved.xdat'))
    assert not doc.summary()['dirty']
    doc.undo()
    assert doc.summary()['dirty']
    doc.set(node, 'name', 'second')
    assert doc.summary()['dirty'] and not doc.redo()
