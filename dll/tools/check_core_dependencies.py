"""Check the Core imports of the target client's EXE/DLLs against a Core candidate.

This checks PE import names/ordinals, not game behavior or native-index ownership.
No client binary is executed or changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2] / 'int64'
sys.path.insert(0, str(ROOT / 'tools'))
from verify_profile import PE


def zstring(image, rva):
    result = bytearray()
    for i in range(65536):
        value = image.rva(rva + i, 1)
        if not value or value == b'\0':
            return result.decode('ascii')
        result += value
    raise ValueError('Unterminated PE string')


def exports(image):
    pe = struct.unpack_from('<I', image.data, 60)[0]
    rva = struct.unpack_from('<I', image.data, pe + 24 + 96)[0]
    header = image.rva(rva, 40)
    ordinal_base, functions, names, address_table, name_table, ordinal_table = struct.unpack_from('<6I', header, 16)
    ordinals = {ordinal_base + i for i in range(functions)
                if struct.unpack('<I', image.rva(address_table + 4 * i, 4))[0]}
    named = set()
    for i in range(names):
        index = struct.unpack('<H', image.rva(ordinal_table + 2 * i, 2))[0]
        if ordinal_base + index in ordinals:
            named.add(zstring(image, struct.unpack('<I', image.rva(name_table + 4 * i, 4))[0]))
    return named, ordinals


def core_imports(image):
    pe = struct.unpack_from('<I', image.data, 60)[0]
    rva, size = struct.unpack_from('<II', image.data, pe + 24 + 104)
    if not rva:
        return []
    result = []
    for offset in range(0, size, 20):
        lookup, _, _, name, iat = struct.unpack('<5I', image.rva(rva + offset, 20))
        if not any((lookup, name, iat)):
            break
        if zstring(image, name).casefold() != 'core.dll':
            continue
        for i in range(65536):
            value = struct.unpack('<I', image.rva((lookup or iat) + i * 4, 4))[0]
            if not value:
                break
            result.append(value & 0xffff if value & 0x80000000 else zstring(image, value + 2))
        else:
            raise ValueError('Unterminated Core import thunk list')
    return result


def check(system, core_path):
    system, core_path = Path(system), Path(core_path)
    core = PE(core_path)
    names, ordinals = exports(core)
    report = dict(system=str(system), core=str(core_path),
                  core_sha256=hashlib.sha256(core.data).hexdigest(), checked={}, missing={}, unreadable={})
    for path in sorted(system.iterdir()):
        if path.suffix.casefold() not in ('.exe', '.dll') or path.name.casefold() == 'core.dll':
            continue
        try:
            required = core_imports(PE(path))
            if not required:
                continue
            report['checked'][path.name] = len(required)
            missing = [item for item in required if item not in (ordinals if isinstance(item, int) else names)]
            if missing:
                report['missing'][path.name] = missing
        except (ValueError, UnicodeError, struct.error) as error:
            report['unreadable'][path.name] = str(error)
    if not report['checked']:
        raise ValueError('No Core consumers were checked in this directory')
    report['compatible_imports'] = not report['missing'] and not report['unreadable']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('system', type=Path)
    parser.add_argument('--core', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = check(args.system, args.core)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['compatible_imports'] else 1)
