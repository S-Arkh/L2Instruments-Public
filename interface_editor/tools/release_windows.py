"""Create and verify a versioned release ZIP from a tested Windows x64 module."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from validate_entrypoint import isolated_environment

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_identity(version, revision):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', version):
        raise ValueError('Version must be X.Y.Z with an optional prerelease suffix')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Revision must be a full commit SHA')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    validate_identity(args.version, args.revision)
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    inputs = json.loads((TOOLS / 'portable_inputs.json').read_text())
    for item in inputs:
        target = cache / item['name']
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.download')
            try:
                with urllib.request.urlopen(item['url'], timeout=120) as response:
                    with temporary.open('wb') as output:
                        shutil.copyfileobj(response, output)
                if digest(temporary) != item['sha256']:
                    raise ValueError('Download hash mismatch: ' + item['name'])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(target) != item['sha256']:
            raise ValueError('Cached input hash mismatch: ' + item['name'])

    name = f'InterfaceEditor-{args.version}-windows-x64'
    bundle = work / name
    def run(script, *arguments):
        subprocess.run([sys.executable, '-B', str(TOOLS / script), *map(str, arguments)], check=True)
    run('package_windows.py', '--cache', cache, '--module', args.module.resolve(), '--out', bundle)
    run('finalize_distribution.py', bundle)
    shutil.copy2(ROOT / 'USER_GUIDE.md', bundle / 'USER_GUIDE.md')
    (bundle / 'docs').mkdir()
    for document in sorted((ROOT / 'docs').glob('*.md')):
        shutil.copy2(document, bundle / 'docs' / document.name)
    info_file = bundle / 'BUILDINFO.json'
    info = json.loads(info_file.read_text(encoding='utf-8'))
    info.update(version=args.version, revision=args.revision,
                release_files={p.relative_to(bundle).as_posix(): digest(p)
                               for p in sorted(bundle.rglob('*')) if p.is_file() and p != info_file})
    info_file.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    output = work / 'publish'
    output.mkdir()
    archive = Path(shutil.make_archive(str(output / name), 'zip', work, name))
    if archive.stat().st_size >= 2 * 1024 ** 3:
        raise ValueError('Release asset must be smaller than 2 GiB')
    # Test exactly the archive that will be published, under a Unicode/spaced path.
    unpack = work / 'Проверка portable'
    with zipfile.ZipFile(archive) as source:
        source.extractall(unpack)
    checked = unpack / name
    env = isolated_environment()
    subprocess.run([str(checked / 'runtime/python.exe'), '-B', str(TOOLS / 'validate_distribution.py'),
                    '--output', str(work / 'validation.json')], cwd=unpack, env=env, check=True, timeout=300)
    run('validate_entrypoint.py', checked)
    expected = info['release_files']
    actual = {p.relative_to(checked).as_posix(): digest(p) for p in checked.rglob('*')
              if p.is_file() and p != checked / 'BUILDINFO.json'}
    if actual != expected or (checked / 'BUILDINFO.json').read_bytes() != info_file.read_bytes():
        raise ValueError('Archive files changed or startup instrumentation remains')
    (output / 'SHA256SUMS.txt').write_text(f'{digest(archive)}  {archive.name}\n', encoding='ascii')
    (output / 'RELEASE_NOTES.md').write_text(
        f'Interface Editor {args.version} — Windows 10/11 x64\n\n'
        f'Source commit: `{args.revision}`\n\n'
        'Extract the ZIP and run **Start.cmd**. Python and Qt are included.\n\n'
        'Verified: source tests, packaged-runtime workflows, Start.cmd (Qt offscreen), '
        'archive manifest and SHA256. Uses synthetic data; no game-client validation in CI.\n\n'
        'Verify the download with `Get-FileHash <archive.zip> -Algorithm SHA256` '
        'and compare with SHA256SUMS.txt.\n', encoding='utf-8')
    print('PASS: release archive and entrypoint verified')


if __name__ == '__main__':
    main()
