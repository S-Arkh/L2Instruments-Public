"""Copy documentation/licenses and attest Python/schema files in an existing package."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('distribution', type=Path, nargs='?', default=ROOT / 'dist/windows')
    args = parser.parse_args()
    out = args.distribution
    manifest = json.loads((out / 'BUILDINFO.json').read_text())
    assert hashlib.sha256((out / 'app/_interface_core.pyd').read_bytes()).hexdigest() == manifest['core_sha256']
    files = [Path('app') / p.name for p in (ROOT / 'app').glob('*.py')]
    files.append(Path('schemas/schemas.json'))
    hashes = {}
    for relative in files:
        original = (ROOT / relative).read_bytes()
        if (out / relative).read_bytes() != original:
            raise ValueError('Packaged source differs: ' + str(relative))
        hashes[relative.as_posix()] = hashlib.sha256(original).hexdigest()
    licenses = out / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'LICENSE.dat-format', licenses / 'DAT-format.txt')
    shutil.copy2(ROOT / 'third_party/windows/ZLIB-LICENSE.txt', licenses / 'zlib.txt')
    for name, expected in manifest.get('runtime_files', {}).items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected
    for name in ('pybind11', 'nlohmann_json'):
        dist = importlib.metadata.distribution(name)
        license_file = next(p for p in dist.files if str(p).endswith('/licenses/LICENSE'))
        shutil.copy2(dist.locate_file(license_file), licenses / (name + '.txt'))
    shutil.copy2(ROOT / 'docs/PORTABLE_README.md', out / 'README.md')
    manifest['application_files'] = hashes
    (out / 'BUILDINFO.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Package sources and core hash verified:', out)


if __name__ == '__main__': main()
