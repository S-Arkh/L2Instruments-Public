"""Import the matching public UE2 Runtime installer as a compilation-only SDK.

The installer is treated as an archive, never executed. Only a fixed allowlist
is extracted, and compiler DLLs are checked against the user's exact binaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from verify_profile import HASHES

ARCHIVE_SHA1 = '2356fafdf7dd77b3f74f766f28dcd451849dfb9b'
ENGINE_HASH = 'a89b7c00697808861c9c86b003014d4c7f4a732ecf476440b4c187c880a710b6'
URL = 'https://archive.org/download/ue2runtime_inst/UE2Runtime-22261903.exe'


def import_sdk(installer, destination):
    installer, destination = Path(installer), Path(destination)
    if destination.exists():
        raise ValueError('Choose a new SDK directory')
    raw = installer.read_bytes()
    if hashlib.sha1(raw).hexdigest() != ARCHIVE_SHA1:
        raise ValueError('Not the verified UE2 Runtime 2226.19.03 installer')
    with ZipFile(installer) as archive:
        for name, expected in {**HASHES, 'Engine.dll': ENGINE_HASH}.items():
            if hashlib.sha256(archive.read('System/' + name)).hexdigest() != expected:
                raise ValueError(f'Compiler binary mismatch: {name}')
        files = {name: archive.read('System/' + name)
                 for name in ('Core.u', 'Engine.u', 'Editor.u', 'License.int')}
    system = destination / 'System'
    system.mkdir(parents=True)
    for name, data in files.items():
        (system / name).write_bytes(data)
    manifest = dict(source_url=URL, installer_sha1=ARCHIVE_SHA1,
                    installer_sha256=hashlib.sha256(raw).hexdigest(),
                    matched_binaries={**HASHES, 'Engine.dll': ENGINE_HASH},
                    files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(import_sdk(args.installer, args.destination), indent=2))
