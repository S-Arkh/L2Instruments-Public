"""Verify the compiler-produced smoke package against proven client encodings."""
import argparse
from pathlib import Path
from ue2package import Package, FormatError, Reader


def tagged_defaults(package, reader):
    result = {}
    while True:
        name = package.name(reader.index())
        if name == 'None':
            return result
        if name not in ('Amount', 'FixedValues', 'Left', 'Right'):
            raise FormatError('Unexpected property in smoke defaults')
        info = reader.byte()
        kind = info & 15
        struct_name = package.name(reader.index()) if kind == 10 else None
        size_code = (info >> 4) & 7
        size = (1, 2, 4, 12, 16)[size_code] if size_code < 5 else reader.unpack(
            {5: '<B', 6: '<H', 7: '<I'}[size_code])
        index = reader.byte() if info & 128 else 0
        if index >= 128:
            raise FormatError('Smoke defaults use only array indices 0 and 1')
        payload = Reader(reader.take(size))
        if kind == 10 and struct_name == 'INT64':
            value = tagged_defaults(package, payload)
        elif kind == 2 and size == 4:
            value = payload.unpack('<i')
        else:
            raise FormatError('Unexpected smoke property type')
        if payload.pos != len(payload.data) or (name, index) in result:
            raise FormatError('Invalid smoke default payload')
        result[name, index] = value


def check_defaults(package):
    _, export = package.find('Int64Probe')
    data = package.data[export.offset:export.offset + export.size]
    # Class metadata is outside this limited decoder. Locate an unambiguous,
    # fully parsed tagged-property suffix, not a raw integer byte-pattern match.
    matches = []
    for offset in range(len(data)):
        reader = Reader(data, offset)
        try:
            props = tagged_defaults(package, reader)
            if reader.pos == len(data) and set(props) == {('Amount', 0), ('FixedValues', 0), ('FixedValues', 1)}:
                matches.append(props)
        except (FormatError, UnicodeError):
            continue
    if len(matches) != 1:
        raise FormatError(f'Expected one tagged default suffix, got {len(matches)}')
    expected = {('Amount', 0): 5000000000, ('FixedValues', 0): -1,
                ('FixedValues', 1): 9223372036854775807}
    for key, value in expected.items():
        words = matches[0][key]
        if set(words) - {('Left', 0), ('Right', 0)}:
            raise FormatError(f'Unexpected INT64 fields: {words}')
        actual = (words.get(('Left', 0), 0) << 32) + (words.get(('Right', 0), 0) & 0xffffffff)
        if actual != value:
            raise FormatError(f'{key}: default {actual} != {value}')
        print(f'OK default {key[0]}[{key[1]}] = {actual}')


def check(path):
    package = Package(path)
    expected = {
        'Widen': (['5b'], []),
        'ParseValue': (['5e'], []),
        'FormatValue': (['63'], []),
        'LargeLiteral': (['5e'], ['5000000000']),
        'Minimum': (['5e'], ['-9223372036854775808']),
        'Maximum': (['5e'], ['9223372036854775807']),
        'NamedConstant': (['5e'], ['5000000000']),
        'Narrow': (['60'], []),
    }
    for name, (casts, strings) in expected.items():
        f = package.function('Int64Probe.' + name)
        rows = f['instructions']
        actual = [r['cast'] for r in rows if r['kind'] == 'cast']
        literals = [r['value'] for r in rows if r['kind'] == 'string']
        if actual != casts or literals != strings:
            raise FormatError(f'{name}: expected casts/strings {casts}/{strings}, got {actual}/{literals}')
        print(f'OK {name}: casts={actual}, constants={literals}')
    rows = package.function('Int64Probe.Arithmetic')['instructions']
    indices = [r['index'] for r in rows if r['kind'] == 'native']
    if indices != [404, 406, 407, 409, 401]:
        raise FormatError(f'Arithmetic uses wrong native indices: {indices}')
    if any(r['cast'] != '5b' for r in rows if r['kind'] == 'cast'):
        raise FormatError('Unexpected arithmetic conversion')
    print('OK Arithmetic: native indices match client INT64 operators')
    rows = package.function('Int64Probe.Nested')['instructions']
    if [r['cast'] for r in rows if r['kind'] == 'cast'] != ['5b', '5e']:
        raise FormatError('Wrong nested casts')
    rows = package.function('Int64Probe.MixedFloat')['instructions']
    if [r['cast'] for r in rows if r['kind'] == 'cast'] != ['62']:
        raise FormatError('Wrong float promotion')
    rows = package.function('Int64Probe.LegacyMask')['instructions']
    if [r.get('value') for r in rows if r['kind'] == 'constant'] != [-1]:
        raise FormatError('Legacy 32-bit hex mask changed')
    for name, expected in [('ByteArithmetic', [147]), ('IntArithmetic', [146]), ('MixedByte', [404])]:
        rows = package.function('Int64Probe.' + name)['instructions']
        if [r['index'] for r in rows if r['kind'] == 'native'] != expected:
            raise FormatError(f'Wrong overload selected for {name}')
    print('OK overload ranking: byte/int arithmetic stays 32-bit; mixed INT64 widens')
    check_defaults(package)
    if not package.class_flags('FlagBase') & 0x800 or package.class_flags('FlagChild') & 0x800:
        raise FormatError('NoNativeReplication did not clear the inherited class flag')
    print('OK NoNativeReplication: inherited flag cleared in serialized UClass')
    if not package.class_flags('LocalizedProbe') & 0x20:
        raise FormatError('Localized class flag was not preserved')
    print('OK localized: class flag preserved')
    if not package.class_flags('DynamicProbe') & 0x400000:
        raise FormatError('DynamicRecompile class flag was not preserved')
    print('OK dynamicrecompile: class flag preserved')
    print('Bytecode and tagged defaults passed. Full package execution in the client is still required.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    check(parser.parse_args().package)
