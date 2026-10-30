"""Extract intact ScriptText exports; do not decompile or invent function bodies."""
import argparse
import hashlib
import json
from pathlib import Path
from ue2package import Package, Reader, FormatError
from uc_declarations import tokens


def script_text(package, entry):
    r = Reader(package.data[entry.offset:entry.offset + entry.size])
    if entry.flags & 0x02000000 or package.name(r.index()) != 'None':
        raise FormatError('Unsupported UTextBuffer properties/stack')
    r.take(8)  # Pos, Top
    count = r.index()
    if count > 0:
        raw = r.take(count)
        if not raw.endswith(b'\0'):
            raise FormatError('Unterminated ANSI source')
        source, encoding = raw[:-1], 'ansi-bytes'
        text = source.decode('latin1')
    elif count < 0:
        raw = r.take(-count * 2)
        if not raw.endswith(b'\0\0'):
            raise FormatError('Unterminated Unicode source')
        source, encoding = b'\xff\xfe' + raw[:-2], 'utf-16le'
        text = raw[:-2].decode('utf-16le')
    else:
        source, text, encoding = b'', '', 'empty'
    if r.pos != len(r.data):
        raise FormatError('Unconsumed UTextBuffer payload')
    return source, text, encoding


def extract(package_path, class_dir):
    package = Package(package_path)
    class_dir = Path(class_dir)
    class_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem.casefold(): p for p in class_dir.glob('*.uc')}
    report = dict(package=str(package.path), package_sha256=package.sha256,
                  extracted={}, rejected={}, missing=[])
    for index, entry in enumerate(package.exports, 1):
        if entry.name != 'ScriptText' or package.ref(entry.cls).split('.')[-1] != 'TextBuffer':
            continue
        name = package.ref(index)
        try:
            if not 0 < entry.outer <= len(package.exports):
                raise FormatError('ScriptText owner is not an export')
            owner = package.exports[entry.outer - 1]
            if owner.cls != 0 or not owner.name.isidentifier():
                raise FormatError('ScriptText owner is not a class')
            owner_reader = Reader(package.data[owner.offset:owner.offset + owner.size])
            owner_reader.index()
            owner_reader.index()
            if owner_reader.index() != index:
                raise FormatError('ScriptText is not the active source referenced by its class')
            source, text, encoding = script_text(package, entry)
            ts = tokens(text)
            at = next((i for i, t in enumerate(ts) if t.text.casefold() == 'class'), None)
            if at is None or at + 1 == len(ts) or ts[at + 1].text.casefold() != owner.name.casefold():
                raise FormatError('Source class declaration does not match package owner')
            target = existing.get(owner.name.casefold(), class_dir / (owner.name + '.uc'))
            before = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            target.write_bytes(source)
            report['extracted'][owner.name] = dict(export=index, encoding=encoding, size=len(source),
                sha256=hashlib.sha256(source).hexdigest(), replaced_sha256=before)
        except (ValueError, UnicodeError) as error:
            report['rejected'][name] = str(error)
    report['missing'] = [e.name for e in package.exports if e.cls == 0 and e.name not in report['extracted']]
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise ValueError('CLI extraction requires a new destination')
    result = extract(args.package, args.destination / 'Classes')
    (args.destination / 'extraction.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"Extracted {len(result['extracted'])}; missing {len(result['missing'])}; rejected {len(result['rejected'])}")
