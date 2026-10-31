"""Unsigned byte fields must not consume adjacent native archive fields."""
import json
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from _interface_core import Document
from schema_tools import validate_package


def document():
    package = {'format': 1, 'versions': [['Byte fixture', 'test.XDAT']], 'records': {
        'test.XDAT': {'base': None, 'ops': [
            {'op': 'field', 'name': 'width', 'kind': 'byte', 'default': 0},
            {'op': 'field', 'name': 'height', 'kind': 'byte', 'default': 0},
            {'op': 'field', 'name': 'offset', 'kind': 'byte', 'default': 0},
            {'op': 'field', 'name': 'sentinel', 'kind': 'int', 'default': 0}]}}}
    validate_package(package)
    return Document(json.dumps(package))


def test_byte_alignment_edit_undo_json_and_truncation():
    doc = document()
    raw = bytes([0, 128, 255]) + struct.pack('<i', 0x12345678)
    doc.load_bytes(raw, 'test.XDAT')
    assert {p['name']: p['value'] for p in doc.properties(0)} == {
        'width': 0, 'height': 128, 'offset': 255, 'sentinel': 0x12345678}
    assert doc.serialize() == raw
    doc.set(0, 'width', 255)
    assert doc.serialize() == b'\xff' + raw[1:]
    reread = document()
    reread.from_json(doc.to_json())
    assert reread.serialize() == doc.serialize()
    doc.undo()
    assert doc.serialize() == raw
    result = doc.diagnose(raw[:2], 'test.XDAT', 10)
    assert not result['compatible']
    assert result['failure']['field'] == 'offset'
    assert result['cursor'] == 2


@pytest.mark.parametrize('value', [-1, 256, 2**32, 1.5, '255'])
def test_invalid_byte_edit_is_atomic(value):
    doc = document()
    raw = bytes(7)
    doc.load_bytes(raw, 'test.XDAT')
    with pytest.raises(RuntimeError):
        doc.set(0, 'width', value)
    assert doc.serialize() == raw


def test_byte_default_cannot_wrap_on_creation():
    package = {'format': 1, 'versions': [['Invalid byte', 'test.XDAT']], 'records': {
        'test.XDAT': {'base': None, 'ops': [
            {'op': 'field', 'name': 'width', 'kind': 'byte', 'default': 256}]}}}
    with pytest.raises(ValueError, match='Byte default'):
        validate_package(package)
    doc = Document(json.dumps(package))
    with pytest.raises(RuntimeError, match='out of range'):
        doc.create('test.XDAT')
