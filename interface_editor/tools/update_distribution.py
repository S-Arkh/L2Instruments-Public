"""Publish a tested native module and current Python sources into a portable build."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--module', type=Path)
    mode.add_argument('--ui-only', action='store_true', help='Update Python UI without replacing the native module')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--distribution', type=Path, default=ROOT / 'dist/windows')
    args = parser.parse_args()
    out = args.distribution.resolve()
    info_file = out / 'BUILDINFO.json'
    info = json.loads(info_file.read_text(encoding='utf-8'))
    old_module = info.get('core_module', '_xdat_core.pyd')  # upgrade older packages
    expected = {'app/' + old_module: info['core_sha256'], **info.get('application_files', {}), **info.get('runtime_files', {})}
    for name, sha in expected.items():
        if digest(out / name) != sha:
            raise ValueError('Installed package differs from manifest: ' + name)
    if args.ui_only:
        for name, sha in info.get('native_sources', {}).items():
            if digest(ROOT / name) != sha:
                raise ValueError('Native sources changed; rebuild the module first: ' + name)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = out.parent / 'updates' / (stamp + '-previous')
    backup.mkdir(parents=True)
    for name in [*expected, 'BUILDINFO.json', 'README.md']:
        source = out / name
        if source.is_file():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if args.ui_only and old_module != '_interface_core.pyd':
        raise ValueError('The renamed application requires a rebuilt native module')
    files = {} if args.ui_only else {'app/_interface_core.pyd': args.module.resolve()}
    # Main imports its helpers; publish the entry point last.
    for source in sorted((ROOT / 'app').glob('*.py'), key=lambda p: (p.name == 'main.py', p.name)):
        files['app/' + source.name] = source
    files['schemas/schemas.json'] = ROOT / 'schemas/schemas.json'
    files['runtime/zlib1.dll'] = ROOT / 'third_party/windows/zlib1.dll'
    temporary = []
    try:
        for name, source in files.items():
            target = out / name
            temp = target.with_name(target.name + '.update-' + stamp)
            shutil.copy2(source, temp)
            temporary.append(temp)
            if digest(source) != digest(temp):
                raise ValueError('Staged copy differs: ' + name)
        for (name, source), temp in zip(files.items(), temporary):
            os.replace(temp, out / name)
        info['core_module'] = '_interface_core.pyd'
        info['core_sha256'] = digest(out / 'app/_interface_core.pyd')
        info['revision'] = args.revision
        info['application_files'] = {name: digest(out / name) for name in files if name != 'app/_interface_core.pyd' and not name.startswith('runtime/')}
        info['runtime_files'] = {name: digest(out / name) for name in files if name.startswith('runtime/')}
        info['native_sources'] = {name: digest(ROOT / name) for name in ('core/document.cpp', 'core/document.hpp', 'core/textures.cpp', 'core/textures.hpp', 'core/dat.cpp', 'core/dat.hpp', 'bindings/module.cpp')}
        staged_info = info_file.with_suffix('.json.update-' + stamp)
        temporary.append(staged_info)
        staged_info.write_text(json.dumps(info, indent=2), encoding='utf-8')
        os.replace(staged_info, info_file)
        if old_module != '_interface_core.pyd':
            (out / 'app' / old_module).unlink()
    finally:
        for temp in temporary:
            if temp.exists():
                temp.unlink()
    print('Updated:', out)
    print('Previous application files:', backup)
    print('Native SHA256:', info['core_sha256'])


if __name__ == '__main__': main()
