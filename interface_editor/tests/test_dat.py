import json
import os
from pathlib import Path
import struct
import sys
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import SysStrings, decode_dat, encode_dat, dat_codecs, register_dat_profile

FIXTURE = ROOT / 'tests/fixtures/sysstring/fileedit.dat'
SAFE = b'\x0cSafePackage\0'


def table():
    result = SysStrings(); result.load(str(FIXTURE)); return result


def compact(value):
    negative = value < 0; value = abs(value)
    result = bytearray([(value & 63) | (128 if negative else 0)])
    value >>= 6
    if value: result[0] |= 64
    while value:
        b = value & 127; value >>= 7; result.append(b | (128 if value else 0))
    return bytes(result)


def test_synthetic_record_and_trailers():
    current = table()
    original = SysStrings(); original.load(str(ROOT / 'tests/fixtures/sysstring/original.dat'))
    new = {r['id']: r['text'] for r in current.rows()}
    old = {r['id']: r['text'] for r in original.rows()}
    assert len(old) == 1 and len(new) == 2
    assert new[6000] == 'Test Button' and new[805] == 'Credit'
    assert new.keys() - old.keys() == {6000}
    assert all(new[i] == text for i, text in old.items())
    assert current.summary()['profile'] == 'l2encdec'
    assert current.summary()['table_tail_hex'] == SAFE.hex()
    assert current.summary()['footer_crc']


@pytest.mark.parametrize('version', [0, 111, 120, 121, 211, 212, 411, 412, 413, 414])
def test_all_envelopes_roundtrip(version):
    source = table()
    source.add(source.next_id(), 'Тестовая кнопка — 日本語')
    source.set(805, 'Credit\nsecond line')
    encoded = source.encoded('sysstring-e.dat', version, 'l2encdec' if version >= 411 else 'standard')
    loaded = SysStrings()
    loaded.load_bytes(encoded, 'sysstring-e.dat', profile='plain' if version == 0 else 'auto')
    assert loaded.payload() == source.payload()
    assert loaded.rows() == source.rows()
    assert loaded.summary()['table_tail_hex'] == SAFE.hex()
    if version:
        assert struct.unpack_from('<I', encoded, len(encoded)-8)[0] == zlib.crc32(encoded[:-20])


@pytest.mark.parametrize('version', [211, 212])
def test_blowfish_partial_variant(version):
    source = table()
    data = source.encoded('sysstring-e.dat', version, 'blowfish-partial')
    loaded = SysStrings(); loaded.load_bytes(data, 'sysstring-e.dat')
    assert loaded.summary()['profile'] == 'blowfish-partial'
    assert loaded.payload() == source.payload()


@pytest.mark.parametrize('encoding,text', [('cp1251', 'Тест'), ('cp1252', 'Café €'), ('cp949', '테스트'), ('cp932', '日本語'), ('cp936', '中文'), ('cp950', '中文'), ('utf-8', '日本語'), ('latin1', 'é')])
def test_ansi_schema_encodings(encoding, text):
    raw = text.encode(encoding) + b'\0'
    payload = struct.pack('<II', 1, 6000) + compact(len(raw)) + raw + SAFE
    obj = SysStrings(); obj.load_bytes(payload, 'plain.dat', encoding=encoding, profile='plain')
    assert obj.lookup(6000) == text
    assert obj.payload() == payload
    obj.set(6000, 'Unicode текст')
    reloaded = SysStrings(); reloaded.load_bytes(obj.encoded('plain.dat'), 'plain.dat', encoding=encoding, profile='plain')
    assert reloaded.lookup(6000) == 'Unicode текст'


def test_plain_requires_explicit_choice_and_bad_input_is_transactional():
    obj = table(); previous = obj.payload()
    with pytest.raises(RuntimeError): obj.load_bytes(previous, 'raw.dat')
    bad = bytearray(FIXTURE.read_bytes()); bad[40] ^= 1
    with pytest.raises(RuntimeError, match='CRC32'): obj.load_bytes(bytes(bad), 'sysstring-e.dat')
    with pytest.raises(RuntimeError): obj.load_bytes('Lineage2Ver999'.encode('utf-16le') + bytes(128), 'bad.dat')
    with pytest.raises(RuntimeError): obj.load_bytes(FIXTURE.read_bytes(), 'sysstring-e.dat', schema='ct26.XDAT')
    assert obj.payload() == previous
    with pytest.raises(RuntimeError): obj.add(6000, 'duplicate')
    with pytest.raises(RuntimeError): obj.add(6001, 'embedded\0nul')
    assert obj.payload() == previous and not obj.summary()['dirty']


def test_filename_key_and_repeated_save(tmp_path):
    obj = table(); before = obj.payload()
    folder = tmp_path / 'Тест System'; folder.mkdir()
    file = folder / 'sysstring-e.dat'
    obj.save(str(file), 121, 'standard')
    obj.add(obj.next_id(), 'added')
    obj.save(str(file))
    assert file.with_suffix('.dat.bak').exists()
    check = SysStrings(); check.load(str(file)); assert check.payload() == obj.payload()
    with pytest.raises(RuntimeError): check.load_bytes(file.read_bytes(), 'wrong-name.dat')
    obj.undo(); assert obj.payload() == before and obj.summary()['dirty']
    obj.redo(); assert obj.payload() == check.payload()
    target = folder / 'copy.dat'; obj.save(str(target))
    again = SysStrings(); again.load(str(target)); assert again.payload() == obj.payload()


def test_decode_only_custom_profile_requires_explicit_write_choice():
    n = '75b4d6de5c016544068a1acf125869f43d2e09fc55b8b1e289556daf9b8757635593446288b3653da1ce91c87bb1a5c18f16323495c55d7d72c0890a83f69bfd1fd9434eb1c02f3e4679edfa43309319070129c267c85604d87bb65bae205de3707af1d2108881abb567c3b3d069ae67c3a4c6a3aa93d26413d4c66094ae2039'
    register_dat_profile(dict(name='custom-readonly-test', version=413, modulus=n, decode_exponent='1d'))
    obj = SysStrings(); obj.load(str(FIXTURE), profile='custom-readonly-test')
    assert not obj.summary()['can_encode']
    assert obj.encoded('copy.dat') == FIXTURE.read_bytes()
    obj.add(obj.next_id(), 'new')
    with pytest.raises(RuntimeError, match='decode-only'): obj.encoded('copy.dat')
    converted = obj.encoded('copy.dat', 413, 'l2encdec')
    check = SysStrings(); check.load_bytes(converted, 'copy.dat')
    assert check.rows() == obj.rows()
    assert all(not p['write'] for p in dat_codecs() if p['profile'].startswith('original-'))


def test_rsa_independent_python_decode():
    # Independent framing/math check, in addition to l2encdec interoperability.
    obj = table(); obj.add(obj.next_id(), 'sample')
    data = obj.encoded('sysstring-e.dat')
    n = int('75b4d6de5c016544068a1acf125869f43d2e09fc55b8b1e289556daf9b8757635593446288b3653da1ce91c87bb1a5c18f16323495c55d7d72c0890a83f69bfd1fd9434eb1c02f3e4679edfa43309319070129c267c85604d87bb65bae205de3707af1d2108881abb567c3b3d069ae67c3a4c6a3aa93d26413d4c66094ae2039', 16)
    packed = bytearray()
    for i in range(28, len(data)-20, 128):
        block = pow(int.from_bytes(data[i:i+128], 'big'), 29, n).to_bytes(128, 'big')
        count = block[3]; start = 128-count-((124-count) % 4)
        packed.extend(block[start:start+count])
    assert zlib.decompress(packed[4:]) == obj.payload()
    assert struct.unpack_from('<I', packed)[0] == len(obj.payload())
