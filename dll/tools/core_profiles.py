"""Shared approved profiles, header generation and read-only candidate analysis."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct
import sys

EXAMPLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE.parent / 'int64/tools'))
from verify_profile import PE

CATALOG = EXAMPLE / 'core_profiles.json'


def catalog():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    if data['schema'] != 1 or data['abi'] != 'ue2-x86-frame-high-low-v1' or data['native_table_size'] != 4096:
        raise ValueError('Unsupported catalog ABI/schema')
    names, hashes = set(), set()
    for p in data['profiles']:
        if p.get('wide_char_type', 'wchar_t') not in ('wchar_t', 'unsigned_short'):
            raise ValueError('Unsupported 16-bit string ABI')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', p['name']):
            raise ValueError('Profile name must be a C++-safe identifier')
        if p['name'] in names or p['sha256'] in hashes or len(bytes.fromhex(p['sha256'])) != 32:
            raise ValueError('Duplicate or invalid profile')
        names.add(p['name']); hashes.add(p['sha256'])
        if set(p['rvas']) != set(data['exports']) or set(p['code']) != {'register', 'step', 'undefined'}:
            raise ValueError('Incomplete profile')
        if any(type(rva) is not int or not 0 < rva <= 0xffffffff for rva in p['rvas'].values()):
            raise ValueError('Invalid profile RVA')
        if any(len(bytes.fromhex(code)) != 16 for code in p['code'].values()):
            raise ValueError('Expected 16-byte code fingerprints')
        # This relocation-free prefix is also checked at runtime. Different Step
        # implementations need an adapter review, not merely a new hash.
        if p['code']['step'] != '8b410c0fb61083c00189410c8b442408':
            raise ValueError('Unsupported FFrame::Step implementation')
    return data


def approved(image):
    data = catalog()
    digest = hashlib.sha256(image.data).hexdigest()
    p = next((p for p in data['profiles'] if p['sha256'] == digest), None)
    if p is None:
        raise ValueError('Unsupported Core.dll: analyze it with core_profiles.py analyze; candidate is not approval')
    for key, name in data['exports'].items():
        if image.exports.get(name) != p['rvas'][key]:
            raise ValueError('Profile export RVA mismatch: ' + key)
    for key, hex_bytes in p['code'].items():
        expected = bytes.fromhex(hex_bytes)
        if image.rva(p['rvas'][key], len(expected)) != expected:
            raise ValueError('Profile machine code mismatch: ' + key)
    return p


def analyze(path):
    image = PE(path)
    data = catalog()
    rvas = {key: image.exports.get(name) for key, name in data['exports'].items()}
    code = {}
    for key in ('register', 'step', 'undefined'):
        if rvas[key] is not None:
            try:
                code[key] = image.rva(rvas[key], 16).hex()
            except ValueError:
                code[key] = None
    pe = struct.unpack_from('<I', image.data, 60)[0]
    opt = pe + 24
    count = struct.unpack_from('<H', image.data, pe + 6)[0]
    section_table = opt + struct.unpack_from('<H', image.data, pe + 20)[0]
    sections = []
    for i in range(count):
        offset = section_table + i * 40
        virtual_size, rva, raw_size = struct.unpack_from('<III', image.data, offset + 8)
        flags = struct.unpack_from('<I', image.data, offset + 36)[0]
        sections.append(dict(name=image.sections[i][0], rva=rva, size=max(virtual_size, raw_size), flags=flags))
    placement = {}
    for key, rva in rvas.items():
        size = data['native_table_size'] * 4 if key == 'table' else 16
        section = next((s for s in sections if rva is not None and s['rva'] <= rva and rva + size <= s['rva'] + s['size']), None)
        required_flag = 0x80000000 if key == 'table' else 0x20000000
        placement[key] = bool(section and section['flags'] & required_flag)
    try:
        known = approved(image)['name']
    except ValueError:
        known = None
    return dict(schema=1, source=str(Path(path).resolve()), approved_profile=known,
                candidate=dict(name='UNREVIEWED', sha256=hashlib.sha256(image.data).hexdigest(), rvas=rvas, code=code),
                missing_exports=[k for k, v in rvas.items() if v is None],
                heuristic_checks=dict(export_section_permissions_and_capacity=placement,
                                      step_prefix_matches_adapter=code.get('step') == data['profiles'][0]['code']['step']),
                pe=dict(machine='x86', entry_rva=struct.unpack_from('<I', image.data, opt + 16)[0],
                        sections=sections),
                requires_review=['FFrame layout and calling conventions', 'GNatives capacity and initialization',
                                 'INT64 high/low layout', 'original and patched loader/VM tests',
                                 'full client startup'],
                note='Export names/code samples are evidence, not proof of ABI compatibility. No catalog changes made.')


def header():
    data = catalog()
    lines = ['// Generated by tools/core_profiles.py; edit core_profiles.json instead.', '#pragma once',
             '#include <cstdint>', 'namespace l2client {', 'constexpr int NativeIndex = 4000;',
             f'constexpr int NativeTableSize = {data["native_table_size"]};',
              'struct CoreProfile { const char* name; std::uintptr_t registerRva, tableRva, stepRva, undefinedRva; const char* throwExport; const char* assignExport; };',
             'constexpr CoreProfile CoreProfiles[] = {']
    for p in data['profiles']:
        char_type = 'G' if p.get('wide_char_type') == 'unsigned_short' else '_W'
        lines.append('    {"' + p['name'] + '", ' + ', '.join(hex(p['rvas'][k]) for k in ('register', 'table', 'step', 'undefined')) +
                     f', "?appThrowf@@YAXPB{char_type}ZZ", "??4FString@@QAEAAV0@PB{char_type}@Z"' + '},')
    lines.append('};')
    for key, value in data['exports'].items():
        lines.append(f'constexpr const char* {key.title()}Export = "{value}";')
    prefix = bytes.fromhex(data['profiles'][0]['code']['step'])
    lines.append('constexpr unsigned char StepPrefix[] = {' + ', '.join(hex(b) for b in prefix) + '};')
    return '\n'.join(lines + ['}', ''])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    gen = sub.add_parser('generate')
    gen.add_argument('--check', action='store_true')
    scan = sub.add_parser('analyze')
    scan.add_argument('core', type=Path)
    scan.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.command == 'generate':
        target = EXAMPLE / 'src/client_profile.h'
        text = header()
        if args.check:
            if target.read_text(encoding='utf-8') != text:
                raise SystemExit('Generated profile header is stale')
        else:
            target.write_text(text, encoding='utf-8')
    else:
        text = json.dumps(analyze(args.core), indent=2)
        if args.report:
            args.report.write_text(text, encoding='utf-8')
        print(text)
