"""Copy the original compiler into int64/compiler without modifying the source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from verify_profile import ROOT, HASHES
from import_runtime_sdk import ENGINE_HASH


def import_compiler(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination already exists; choose a new directory')
    system = source / 'System'
    for name, expected in {**HASHES, 'Engine.dll': ENGINE_HASH}.items():
        if hashlib.sha256((system / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Unsupported compiler binary: {name}')
    if not (source / 'Core/Classes/Object.uc').is_file():
        raise ValueError('Core/Classes/Object.uc is missing')
    target_system = destination / 'System'
    target_system.mkdir(parents=True)
    for file in system.iterdir():
        if file.is_file() and file.suffix.lower() in ('.exe', '.dll', '.u', '.int', '.ini'):
            shutil.copy2(file, target_system / file.name)
    shutil.copytree(source / 'Core', destination / 'Core')
    files = {}
    for file in sorted(destination.rglob('*')):
        if not file.is_file():
            continue
        relative = file.relative_to(destination)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != hashlib.sha256((source / relative).read_bytes()).hexdigest():
            raise ValueError(f'Copy verification failed: {relative}')
        files[relative.as_posix()] = digest
    manifest = dict(source=str(source), purpose='Original compiler baseline for staging workspaces',
                    files=files)
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Copied and verified {len(files)} files: {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Original compiller directory containing System and Core')
    parser.add_argument('--destination', type=Path, default=ROOT / 'compiler')
    args = parser.parse_args()
    import_compiler(args.source, args.destination)
