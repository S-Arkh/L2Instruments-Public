"""Build a self-contained Windows x64 ZIP, then validate its extracted contents."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate_identity(version, revision):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', version):
        raise ValueError('Version must be X.Y.Z with an optional prerelease suffix')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Revision must be a full Git commit SHA')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_pe(path):
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Not a Windows PE: ' + str(path))
    offset = struct.unpack_from('<I', data, 60)[0]
    if data[offset:offset+4] != b'PE\0\0' or struct.unpack_from('<H', data, offset+4)[0] != 0x8664:
        raise ValueError('Expected Windows x64 PE: ' + str(path))


def file_manifest(bundle):
    return {p.relative_to(bundle).as_posix(): digest(p)
            for p in sorted(bundle.rglob('*')) if p.is_file() and p != bundle/'BUILDINFO.json'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--bin', type=Path, required=True, help='Freshly built DLL and CLI directory')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New output directory')
    parser.add_argument('--download', action='store_true', help='Download missing pinned inputs')
    parser.add_argument('--revision', help='Explicit full Git SHA (e.g. when Git runs in WSL); dirty state is recorded as unknown')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Packaging and runtime verification require Windows x64')
    if args.revision:
        revision, dirty = args.revision, None
    else:
        if not shutil.which('git'):
            parser.error('Git for Windows must be in PATH, or pass --revision explicitly')
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    try:
        validate_identity(args.version, revision)
    except ValueError as error:
        parser.error(str(error))
    binaries = [args.bin.resolve()/name for name in ('uexplorer_core.dll', 'uexplorer_cli.exe')]
    for binary in binaries:
        check_pe(binary)
    inputs = json.loads((ROOT/'tools/portable_inputs.json').read_text())
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    for item in inputs:
        target = cache/item['name']
        if not target.exists() and args.download:
            temporary = target.with_suffix('.download')
            try:
                with urllib.request.urlopen(item['url'], timeout=120) as source, temporary.open('wb') as output:
                    shutil.copyfileobj(source, output)
                if digest(temporary) != item['sha256']:
                    raise ValueError('Downloaded input hash mismatch: ' + item['name'])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(target) != item['sha256']:
            raise ValueError('Input hash mismatch: ' + item['name'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    name = f'uExplorer-{args.version}-windows-x64'
    bundle = out/name
    bundle.mkdir()
    for directory in ('runtime', 'packages', 'python', 'bin', 'data', 'licenses'):
        (bundle/directory).mkdir()
    for item in inputs:
        if item['name'].endswith('.txt'):
            shutil.copy2(cache/item['name'], bundle/'licenses'/item['name'])
            continue
        destination = bundle/('runtime' if item['name'].endswith('.zip') else 'packages')
        with zipfile.ZipFile(cache/item['name']) as archive:
            archive.extractall(destination)
    (bundle/'runtime/python312._pth').write_text('python312.zip\n.\n..\n../python\n../packages\nimport site\n', encoding='ascii')
    for pattern in ('msvcp140*.dll', 'concrt140.dll'):
        for dll in (bundle/'packages/PySide6').glob(pattern):
            shutil.copy2(dll, bundle/'runtime'/dll.name)
    for binary in binaries:
        shutil.copy2(binary, bundle/'bin'/binary.name)
    for source in (ROOT/'python').glob('*.py'):
        shutil.copy2(source, bundle/'python'/source.name)
    shutil.copy2(ROOT/'launch.py', bundle/'launch.py')
    shutil.copy2(ROOT.parent/'LICENSE', bundle/'LICENSE')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', bundle/'THIRD_PARTY_NOTICES.md')
    shutil.copy2(ROOT/'docs/PORTABLE_README.md', bundle/'README.md')
    shutil.copytree(ROOT/'docs', bundle/'docs')
    # Research links in the source tree cross into the compiler component.
    # Keep those documents inside the portable root and rewrite only that prefix.
    shutil.copytree(ROOT.parent/'int64/docs', bundle/'docs/compiler')
    for document in (bundle/'docs').glob('*.md'):
        text = document.read_text(encoding='utf-8')
        document.write_text(text.replace('../../int64/docs/', 'compiler/'), encoding='utf-8')
    dist = importlib.metadata.distribution('nlohmann_json')
    if dist.version != '3.12.0':
        raise ValueError('Install requirements-release.txt before packaging')
    license_file = next(p for p in dist.files if str(p).endswith('/licenses/LICENSE'))
    shutil.copy2(dist.locate_file(license_file), bundle/'licenses/nlohmann_json.txt')
    (bundle/'portable.json').write_text(json.dumps({'application': 'uExplorer', 'version': args.version})+'\n', encoding='utf-8')
    (bundle/'Start.cmd').write_bytes(b'@echo off\r\nsetlocal\r\n"%~dp0runtime\\python.exe" -I -B "%~dp0launch.py" %*\r\nset "result=%errorlevel%"\r\nif not "%result%"=="0" pause\r\nexit /b %result%\r\n')
    info = dict(application='uExplorer', version=args.version, revision=revision, dirty=dirty,
                target='Windows x64', python='3.12.10', qt='6.12.0',
                inputs={item['name']: item['sha256'] for item in inputs}, files=file_manifest(bundle))
    (bundle/'BUILDINFO.json').write_text(json.dumps(info, indent=2)+'\n', encoding='utf-8')
    # Publishable output is only created after validating the exact ZIP contents.
    archive = Path(shutil.make_archive(str(out/name), 'zip', out, name))
    unpack = out/'Проверка portable'
    with zipfile.ZipFile(archive) as source:
        source.extractall(unpack)
    subprocess.run([sys.executable, '-B', str(ROOT/'tools/validate_distribution.py'), str(unpack/name)], check=True)
    if file_manifest(unpack/name) != info['files']:
        raise ValueError('Validation changed packaged files')
    publish = out/'publish'
    publish.mkdir()
    archive.rename(publish/archive.name)
    (publish/'SHA256SUMS.txt').write_text(f'{digest(publish/archive.name)}  {archive.name}\n', encoding='ascii')
    (publish/'RELEASE_NOTES.md').write_text(
        f'# uExplorer {args.version} — Windows x64\n\n'
        f'Ревизия исходников: `{revision}`.\n\n'
        'Распакуйте ZIP и запустите **Start.cmd**. Python и Qt включены в комплект.\n\n'
        'Проверено на распакованном архиве: загрузка native DLL, CLI, GUI '
        '(Qt offscreen), экспорт синтетического пакета и локальные настройки.\n\n'
        'BUILDINFO.json содержит хеши файлов и зависимостей; SHA256SUMS.txt — хеш ZIP. '
        'Игровые пакеты, SDK и компилятор ucc64 в архив не входят. '
        'Проверка поставки не доказывает эквивалентность восстановленного кода '
        'оригинальному клиенту.\n', encoding='utf-8')
    print('PASS: verified portable ZIP: ' + str(publish/archive.name))


if __name__ == '__main__':
    main()
