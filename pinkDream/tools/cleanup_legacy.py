"""Archive old loose assets by hash, then remove verified trial build duplicates."""
import argparse
import json
import shutil
from pathlib import Path
from inventory import ROOT
from asset_store import put, read, digest, write_json


def references(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value and value['path'].startswith('assets/objects/'):
            yield value
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def clean(apply=False):
    # Verify the independent library before touching any legacy sources.
    library = ROOT / 'assets/libraries/scryde/standard-ui-v001/manifest.json'
    lib = json.loads(library.read_text())
    for ref in references(lib):
        read(ref)
    names = [f'trial-v00{i}' for i in range(1, 5)]
    roots = [ROOT / parent / name for parent in ('builds/scryde', 'assets/generated/scryde', 'assets/source/scryde') for name in names]
    previews = sorted((ROOT / 'assets/previews').glob('scryde-trial-v*.png'))
    report = {'schema': 1, 'removed': [], 'archived_files': [], 'skipped': [], 'removed_bytes': 0,
              'note': 'No object-store pruning; originals, manual assets and legacy images are retained by hash.'}
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        files = [p for p in root.rglob('*') if p.is_file()]
        is_bundle = root.is_relative_to(ROOT / 'builds')
        known = {}
        if is_bundle:
            manifest = json.loads((root / 'manifest.json').read_text())
            known = {root / f['path']: f['sha256'] for f in manifest['files']}
        problems = []
        for path in files:
            if path.is_symlink():
                problems.append(str(path.relative_to(ROOT)))
            elif path.suffix.lower() == '.utx':
                if path not in known or digest(path.read_bytes()) != known[path]:
                    problems.append(str(path.relative_to(ROOT)))
            elif path.suffix.lower() not in ('.json', '.png', '.tga', '.py', '.md'):
                problems.append(str(path.relative_to(ROOT)))
        if problems:
            report['skipped'].append({'directory': str(root.relative_to(ROOT)), 'unrecognized_or_modified': problems})
        else:
            candidates.append((root, files))
    candidates += [(p, [p]) for p in previews]
    archive = ROOT / 'assets/archives/legacy-trials-v1.json'
    if apply and archive.exists():
        raise FileExistsError('Cleanup was already recorded; do not overwrite archive')
    for root, files in candidates:
        for path in files:
            if path.suffix.lower() != '.utx':
                record = {'original_path': path.relative_to(ROOT).as_posix()}
                if apply:
                    record['object'] = put(path.read_bytes(), path.suffix.lstrip('.'))
                report['archived_files'].append(record)
            report['removed_bytes'] += path.stat().st_size
        report['removed'].append(root.relative_to(ROOT).as_posix())
    if apply:
        # Write the recovery index before deleting any directory.
        archive.parent.mkdir(parents=True, exist_ok=True)
        write_json(archive, report)
        for record in report['archived_files']:
            read(record['object'])
        for root, _ in candidates:
            if root.is_dir():
                shutil.rmtree(root)
            else:
                root.unlink()
    print(json.dumps({k: v for k, v in report.items() if k != 'archived_files'}, indent=2))
    print('Archived loose files:', len(report['archived_files']))


def resume():
    archive = ROOT / 'assets/archives/legacy-trials-v1.json'
    report = json.loads(archive.read_text())
    expected = {}
    for record in report['archived_files']:
        data = read(record['object'])
        relative = record['original_path']
        expected[relative] = record['object']['sha256']
        if relative.startswith('builds/') and relative.endswith('/manifest.json'):
            manifest = json.loads(data)
            parent = str(Path(relative).parent)
            for f in manifest['files']:
                expected[parent + '/' + f['path']] = f['sha256']
    for relative in report['removed']:
        root = (ROOT / relative).resolve()
        if not root.is_relative_to(ROOT) or root == ROOT:
            raise ValueError('Invalid cleanup path')
        if not root.exists():
            continue
        files = list(root.rglob('*')) if root.is_dir() else [root]
        for path in files:
            if path.is_symlink():
                raise ValueError('Unexpected symlink during cleanup resume')
            if path.is_file() and digest(path.read_bytes()) != expected.get(path.relative_to(ROOT).as_posix()):
                raise ValueError(f'File changed since archive: {path}')
    for relative in report['removed']:
        root = ROOT / relative
        if root.is_dir():
            shutil.rmtree(root)
        else:
            root.unlink(missing_ok=True)
    print('Cleanup complete; archived assets verified:', len(report['archived_files']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.resume:
        resume()
    else:
        clean(args.apply)
