"""Verify an installed bundle against its manifest and inspect client resources."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_file(directory, name):
    if Path(name).name != name or '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('Manifest file names must be basenames')
    matches = [p for p in Path(directory).iterdir() if p.name.casefold() == name.casefold() and p.is_file()]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one {name} in {directory}')
    return matches[0]


def resources(system):
    root = Path(system).resolve().parent
    directories = {p.name.casefold(): p for p in root.iterdir() if p.is_dir()}
    missing = [name for name in ('Textures', 'SysTextures', 'Maps', 'StaticMeshes', 'Animations', 'Sounds')
               if name.casefold() not in directories]
    packages = []
    for folder, name in (('Textures', 'Aden_broken_Castle_T.utx'), ('SysTextures', 'Default.utx')):
        directory = directories.get(folder.casefold())
        if not directory or not any(p.name.casefold() == name.casefold() for p in directory.iterdir()):
            packages.append(folder + '/' + name)
    return dict(root=str(root), missing_directories=missing, missing_reference_packages=packages,
                conventional_layout_present=not missing and not packages,
                note='Heuristic for conventional HF layout; custom Paths in client INI are not decoded.')


def verify(system, manifest):
    data = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if data.get('schema') != 1 or data.get('validation', {}).get('status') != 'passed':
        raise ValueError('Expected a validated bundle manifest schema 1')
    expected = {**data['target_files'], **data['bundle_files']}
    if not {'Core.dll', 'ExtensionL2.dll', 'ExtensionL2.u'} <= set(data['bundle_files']):
        raise ValueError('Incomplete bundle manifest')
    mismatches = {}
    for name, sha in expected.items():
        try:
            actual = digest(local_file(system, name))
            if actual != sha:
                mismatches[name] = dict(expected=sha, actual=actual)
        except ValueError as error:
            mismatches[name] = str(error)
    return dict(system=str(Path(system).resolve()), files_match=not mismatches,
                mismatches=mismatches, resources=resources(system))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('system', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.system, args.manifest)
    text = json.dumps(result, indent=2)
    if args.report:
        args.report.write_text(text, encoding='utf-8')
    print(text)
    # Resource warnings are distinct from byte-exact installation failures.
    raise SystemExit(0 if result['files_match'] else 1)
