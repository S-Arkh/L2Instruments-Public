"""List themes or export editable/packed/standard PNGs into a new work folder."""
import argparse
import json
import fnmatch
from pathlib import Path
from inventory import ROOT
from asset_store import read, write_json


def export(manifest_path, target, kind):
    m = json.loads(manifest_path.read_text(encoding='utf-8'))
    if m.get('schema') != 2 or 'textures' not in m or 'theme' not in m:
        raise ValueError('Export requires a schema-2 theme manifest')
    target.mkdir(parents=True, exist_ok=False)
    field = {'editable': 'editable_png', 'packed': 'packed_png', 'standard': 'standard_png'}[kind]
    records = []
    for texture in m['textures']:
        import re
        name = texture['resource']
        if not re.fullmatch('[A-Za-z0-9_.-]+', name):
            raise ValueError('Unsafe resource name')
        ref = texture[field]
        (target / (name + '.png')).write_bytes(read(ref))
        records.append({'resource': name, 'exported_sha256': ref['sha256']})
    write_json(target / 'provenance.json', {'profile': m['profile'], 'theme': m['theme'],
                                          'revision': m['revision'], 'kind': kind, 'images': records})
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    archive = sub.add_parser('restore-archive')
    archive.add_argument('--archive', type=Path, required=True)
    archive.add_argument('--out', type=Path, required=True)
    archive.add_argument('--pattern', default='*')
    exp = sub.add_parser('export')
    exp.add_argument('--manifest', type=Path, required=True)
    exp.add_argument('--out', type=Path, required=True)
    exp.add_argument('--kind', choices=('editable', 'packed', 'standard'), default='editable')
    args = parser.parse_args()
    if args.command == 'list':
        for path in sorted((ROOT / 'assets/generated').glob('*/*/*/manifest.json')):
            m = json.loads(path.read_text())
            if m.get('schema') == 2:
                print(m['profile'], m['theme'], m['revision'], len(m['textures']), path.relative_to(ROOT))
    elif args.command == 'restore-archive':
        manifest = json.loads(args.archive.read_text())
        selected = [r for r in manifest['archived_files'] if fnmatch.fnmatchcase(r['original_path'], args.pattern)]
        if not selected:
            raise ValueError('No archived files match')
        args.out.mkdir(parents=True, exist_ok=False)
        for record in selected:
            path = (args.out / record['original_path']).resolve()
            if not path.is_relative_to(args.out.resolve()):
                raise ValueError('Archive path escapes output folder')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read(record['object']))
        print('Restored files:', len(selected))
    else:
        export(args.manifest, args.out, args.kind)
