"""Exercise public resource selectors and atomic batch errors through the C ABI."""
import ctypes
import json
from pathlib import Path
import struct
import sys


def index(value):
    negative = value < 0
    value = abs(value)
    first = (value & 63) | (128 if negative else 0)
    value >>= 6
    result = bytearray([first | (64 if value else 0)])
    while value:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
    return result


def fixture(path, version=133, licensee=40, kind='Sound', payload=None, flags=0):
    names = bytearray()
    for name in ('None', 'WAV', 'Core', 'Class', kind, 'Sample'):
        text = name.encode('ascii') + b'\0'
        names += index(len(text)) + text + struct.pack('<I', 0)
    imports = index(2) + index(3) + struct.pack('<i', 0) + index(4)
    base = 56 + len(names) + len(imports)
    offset = base
    while True:
        exports = index(-1) + index(0) + struct.pack('<i', 0) + index(5)
        exports += struct.pack('<I', flags) + index(11 if payload is None else len(payload)) + index(offset)
        new_offset = base + len(exports)
        if new_offset == offset:
            break
        offset = new_offset
    if payload is None:
        payload = index(0) + index(1) + struct.pack('<I', offset + 11) + index(4) + b'RIFF'
    header = struct.pack('<IHH7I', 0x9e2a83c1, version, licensee, 0,
                         6, 56, 1, base, 1, 56 + len(names)) + bytes(20)
    assert len(header) == 56
    path.write_bytes(header + names + imports + exports + payload)


def blocking_fixture(path, payload, version=133, licensee=40):
    table = ('None', 'Core', 'Package', 'Class', 'Engine', 'BlockingVolume',
             'Model', 'SampleVolume', 'SampleModel', 'Brush', 'bWorldGeometry')
    names = bytearray()
    for name in table:
        text = name.encode('ascii') + b'\0'
        names += index(len(text)) + text + struct.pack('<I', 0)
    imports = (index(1) + index(2) + struct.pack('<i', 0) + index(4) +
               index(1) + index(3) + struct.pack('<i', -1) + index(5) +
               index(1) + index(3) + struct.pack('<i', -1) + index(6))
    export_offset = 56 + len(names) + len(imports)
    offset = export_offset
    while True:
        actor = (index(-2) + index(0) + struct.pack('<i', 0) + index(7) +
                 struct.pack('<I', 0x02000000) + index(len(payload)) + index(offset))
        model = (index(-3) + index(0) + struct.pack('<i', 0) + index(8) +
                 struct.pack('<I', 0) + index(0))
        exports = actor + model
        new_offset = export_offset + len(exports)
        if new_offset == offset:
            break
        offset = new_offset
    header = struct.pack('<IHH7I', 0x9e2a83c1, version, licensee, 0,
                         len(table), 56, 2, export_offset, 3, 56 + len(names)) + bytes(20)
    path.write_bytes(header + names + imports + exports + payload)


library, path = Path(sys.argv[1]), Path(sys.argv[2])
dll = ctypes.CDLL(str(library.resolve()))
dll.ue_request.argtypes = [ctypes.c_char_p]
dll.ue_request.restype = ctypes.c_void_p
dll.ue_free.argtypes = [ctypes.c_void_p]


def request(**fields):
    pointer = dll.ue_request(json.dumps(dict(path=str(path), **fields)).encode('utf-8'))
    assert pointer
    try:
        return json.loads(ctypes.string_at(pointer).decode('utf-8'))
    finally:
        dll.ue_free(pointer)


for version, licensee in ((133, 40), (131, 40), (130, 40), (128, 39), (123, 23)):
    fixture(path, version, licensee)
    direct = request(operation='sound', object_id=1)
    assert direct['ok'] and direct['result']['body']['audio_hex'] == '52494646', direct
    assert request(operation='sound', object='Sample') == direct
    batch = request(operation='resource_batch', objects=[
        dict(operation='sound', object_id=1), dict(operation='sound', object='Sample')])
    assert batch == dict(ok=True, result=[direct['result'], direct['result']]), batch
    for objects in ([], [dict(operation='sound', object_id=1)] * 257,
                    [dict(operation='sound', object_id=1), dict(operation='sound', object_id=-1)],
                    [dict(operation='resource_group', object_id=1)],
                    [dict(operation='not_an_operation', object_id=1)]):
        result = request(operation='resource_batch', objects=objects)
        assert result['ok'] is False and 'result' not in result, result
colors = bytes(range(256)) * 4
fixture(path, kind='Palette', payload=index(0) + index(256) + colors)
direct = request(operation='palette', object_id=1)
assert direct['ok'] and direct['result']['colors'][1] == [4, 5, 6, 7], direct
assert request(operation='palette', object='Sample') == direct
assert request(operation='resource_batch', objects=[dict(operation='palette', object_id=1)]) == dict(ok=True, result=[direct['result']])
assert request(operation='texture', object_id=1)['ok'] is False
for payload in (index(0) + index(255) + colors, index(0) + index(256) + colors[:-1],
                index(0) + index(256) + colors + b'\0'):
    fixture(path, kind='Palette', payload=payload)
    assert request(operation='palette', object_id=1)['ok'] is False
fixture(path)
assert request(operation='palette', object_id=1)['ok'] is False
fixture(path, version=129, licensee=39, kind='Model', payload=b'\xff')
unverified = request(operation='model', object_id=1)
assert unverified['ok'] and unverified['result']['status'] == 'unverified'
assert unverified['result']['interpretation'] == 'opaque'
assert unverified['result']['raw_preview_hex'] == 'ff'
assert unverified['result']['reconstruction_supported'] is False
assert request(operation='resource_batch', objects=[
    dict(operation='model', object_id=1)]) == dict(ok=True, result=[unverified['result']])
fixture(path, kind='Model', payload=b'\xff')
assert request(operation='model', object_id=1)['ok'] is False
fixture(path, kind='Model', payload=b'\xff', flags=0x02000000)
stacked = request(operation='model', object_id=1)
assert stacked['ok'] and stacked['result']['interpretation'] == 'opaque'
assert stacked['result']['status'] == 'unverified' and stacked['result']['raw_preview_hex'] == 'ff'
for kind, operation in (('Polys', 'polys'), ('KMeshProps', 'karma_props')):
    if kind == 'Polys':
        payload = (index(0) + struct.pack('<II', 1, 2) + index(1) + bytes(48)
                   + struct.pack('<III', 0x80000000, 0x7fc01234, 0) + struct.pack('<I', 7)
                   + index(0) + index(1) + index(5) + index(-1) + index(12345)
                   + struct.pack('<II', 0x80000000, 0xffffffff))
    else:
        payload = index(0) + struct.pack('<9I', 0x7fc01234, *([0] * 8)) + bytes(4)
    fixture(path, kind=kind, payload=payload)
    direct = request(operation=operation, object_id=1)
    assert direct['ok'], direct
    if kind == 'Polys':
        polygon = direct['result']['polygons'][0]
        assert polygon['vertices_bits'][0] == [0x80000000, 0x7fc01234, 0]
        assert polygon['item_name'] == 'Sample' and polygon['material']['id'] == 1
        assert polygon['link'] == -1 and polygon['brush_polygon'] == 12345
        malformed = payload[:9] + index(17) + payload[10:]
    else:
        assert direct['result']['scalar_bits'][0] == 0x7fc01234
        malformed = payload[:-1] + index(1)
    assert request(operation=operation, object='Sample') == direct
    assert request(operation='resource_batch', objects=[dict(operation=operation, object_id=1)]) == dict(ok=True, result=[direct['result']])
    assert request(operation='resource_batch', objects=[dict(operation=operation, object_id=1), dict(operation='sound', object_id=1)])['ok'] is False
    for bad in (payload[:-1], payload + b'\0', malformed):
        fixture(path, kind=kind, payload=bad)
        assert request(operation=operation, object_id=1)['ok'] is False

payload = (index(-2) + index(-2) + b'\xff' * 8 + struct.pack('<I', 0x12345678) +
           index(-1) + index(9) + b'\x05' + index(2) +
           index(10) + b'\x03' + index(0))
blocking_fixture(path, payload)
direct = request(operation='blocking_volume', object_id=1)
assert direct['ok'] and direct['result']['frame']['unknown_word'] == 0x12345678, direct
assert direct['result']['brush']['path'] == 'SampleModel'
assert direct['result']['properties'][1]['value'] is False
assert direct['result']['reconstruction_supported'] is False
assert request(operation='blocking_volume', object='SampleVolume') == direct
assert request(operation='resource_batch', objects=[
    dict(operation='blocking_volume', object_id=1),
    dict(operation='blocking_volume', object='SampleVolume')]) == dict(
        ok=True, result=[direct['result'], direct['result']])
for objects in ([dict(operation='blocking_volume', object_id=2)],
                [dict(operation='blocking_volume', object_id=1),
                 dict(operation='blocking_volume', object_id=2)]):
    result = request(operation='resource_batch', objects=objects)
    assert result['ok'] is False and 'result' not in result, result
for bad in (payload[:-1], payload + b'\0'):
    blocking_fixture(path, bad)
    assert request(operation='blocking_volume', object_id=1)['ok'] is False
blocking_fixture(path, payload, version=132)
assert request(operation='blocking_volume', object_id=1)['ok'] is False
print('Public resource API selector and atomic batch checks passed')
