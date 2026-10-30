"""Read-only inventory of UE2 texture package tables, including XOR envelopes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct

ROOT = Path(__file__).resolve().parents[1]


class Reader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError('Truncated package')
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def number(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def index(self):
        first = self.number('B')
        value, more, shift = first & 63, first & 64, 6
        for _ in range(4):
            if not more:
                return -value if first & 128 else value
            b = self.number('B')
            value |= (b & 127) << shift
            more, shift = b & 128, shift + 7
        if more or value > 0x80000000:
            raise ValueError('Invalid compact index')
        return -value if first & 128 else value


def inspect(path, include_data=False):
    raw = path.read_bytes()
    result = {'file': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    data, envelope = raw, 'plain'
    for marker in ('Lineage2Ver111', 'Lineage2Ver121', 'GamekitData111', 'GamekitData121'):
        header = marker.encode('utf-16le')
        if raw.startswith(header):
            body = raw[len(header):]
            if not body:
                raise ValueError('Empty envelope')
            key = 0xac if marker.endswith('111') else body[0] ^ 0xc1
            data, envelope = bytes(b ^ key for b in body), marker
            break
    r = Reader(data)
    if r.number('<I') != 0x9e2a83c1:
        raise ValueError('Unsupported envelope/signature')
    version, licensee = r.number('<H'), r.number('<H')
    result.update(envelope=envelope, version=version, licensee=licensee)
    if (version, licensee) not in ((123, 37), (125, 38), (123, 0), (126, 0)):
        raise ValueError(f'Unsupported version {version}/{licensee}')
    r.number('<I')
    nc, no, ec, eo, ic, io = [r.number('<i') for _ in range(6)]
    for count, offset in ((nc, no), (ec, eo), (ic, io)):
        if not 0 <= count <= 1000000 or not 0 <= offset < len(data):
            raise ValueError('Invalid table bounds')
    names = []
    r.pos = no
    for _ in range(nc):
        n = r.index()
        b = r.take(abs(n) * (2 if n < 0 else 1))
        names.append(b.decode('utf-16le' if n < 0 else 'latin1').rstrip('\0'))
        r.number('<I')

    def name(index):
        if not 0 <= index < len(names):
            raise ValueError('Invalid name reference')
        return names[index]

    imports, exports = [], []
    r.pos = io
    for _ in range(ic):
        package, cls = name(r.index()), name(r.index())
        outer, obj = r.number('<i'), name(r.index())
        imports.append({'name': obj, 'outer': outer, 'class': cls, 'package': package})
    r.pos = eo
    for _ in range(ec):
        cls, parent, outer, obj = r.index(), r.index(), r.number('<i'), name(r.index())
        flags, size = r.number('<I'), r.index()
        offset = r.index() if size else 0
        if size < 0 or offset < 0 or offset + size > len(data):
            raise ValueError('Invalid export bounds')
        exports.append({'name': obj, 'outer': outer, 'class_ref': cls,
                        'size': size, 'offset': offset})

    def ref(i, visited=()):
        if not i:
            return ''
        if i in visited:
            raise ValueError('Cyclic reference')
        table, index = (exports, i - 1) if i > 0 else (imports, -i - 1)
        if not 0 <= index < len(table):
            raise ValueError('Invalid object reference')
        entry = table[index]
        prefix = ref(entry['outer'], visited + (i,))
        return (prefix + '.' if prefix else '') + entry['name']

    result['exports'] = [{'resource': path.stem + '.' + ref(i),
                          'class': ref(e['class_ref']), 'serial_size': e['size']}
                         for i, e in enumerate(exports, 1)]
    result['export_count'] = len(exports)
    result['texture_count'] = sum(e['class'] == 'Engine.Texture' for e in result['exports'])
    result['image_metadata_status'] = 'not-extracted'
    if include_data:
        result['_data'] = data
        result['_names'] = names
        result['_entries'] = exports
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('scryde', 'high-five', 'gracia'), required=True)
    parser.add_argument('--client', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads((ROOT / 'profiles' / args.profile / 'profile.json').read_text())
    client = args.client or Path(profile['client_root_windows' if os.name == 'nt' else 'client_root_linux'])
    report = {'schema': 1, 'profile': args.profile, 'packages': [], 'game_tested': False}
    for relative in profile['packages']:
        try:
            entry = inspect(client / relative)
        except (OSError, ValueError) as error:
            entry = {'error': str(error)}
        entry['relative_path'] = relative
        report['packages'].append(entry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2, ensure_ascii=False)
        out.write('\n')
    print(args.output)
    if any('error' in p for p in report['packages']):
        raise SystemExit('Some packages could not be inspected; see report')


if __name__ == '__main__':
    main()
