"""Make a controlled metadata variant of the synthetic Generation fixture only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from ue2package import Package, Reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--original-property-mask', action='store_true')
    parser.add_argument('--clear-client-class-bit', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]/'uExplorer/local'
    if not args.out.resolve().is_relative_to(root):
        parser.error('Output must be a new directory under uExplorer/local')
    p = Package(args.package)
    if p.envelope != 'plain' or {e.name for e in p.exports if e.cls == 0} != {'InlineValue', 'PlainValue', 'MetadataOwner'}:
        raise ValueError('Expected the exact synthetic class set and a plain package')
    data = bytearray(p.data)
    changes = []
    def replace(offset, expected, value, label):
        old = struct.unpack_from('<I', data, offset)[0]
        if old != expected:
            raise AssertionError((label, old, expected))
        struct.pack_into('<I', data, offset, value)
        changes.append(dict(object=label, offset=offset, before=old, after=value))
    if args.original_property_mask:
        for name, expected in [('MetadataOwner.Inline', 0x4000008), ('MetadataOwner.Fixed', 0x4000008),
                               ('MetadataOwner.Dynamic.Dynamic', 0x4000008), ('MetadataOwner.Accept.Value', 0x4000188)]:
            _, entry = p.find(name)
            r = Reader(p.data, entry.offset)
            if p.name(r.index()) != 'None':
                raise AssertionError('Unexpected tags')
            r.index(); r.index(); r.take(4)
            replace(r.pos, expected, (expected & ~0x4000008) | 0x400000, name)
    if args.clear_client_class_bit:
        r = Reader(p.data, struct.unpack_from('<i', p.data, 24)[0])
        for entry in p.exports:
            r.index(); r.index(); r.take(4); r.index()
            if entry.cls == 0:
                replace(r.pos, entry.flags, entry.flags & ~0x10000, entry.name)
            r.take(4)
            if r.index():
                r.index()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'Generation.u').write_bytes(data)
    (args.out/'changes.json').write_text(json.dumps(dict(input=p.sha256,
        output=hashlib.sha256(data).hexdigest(), changes=changes), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
