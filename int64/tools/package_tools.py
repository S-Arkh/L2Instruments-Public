"""Package and smoke-check the standalone Win32 compiler launcher and bridge."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--revision', required=True, help='Full source Git commit SHA')
    parser.add_argument('--variant', choices=('msvc', 'mingw'), required=True)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('The extracted launcher smoke test requires Windows')
    if not re.fullmatch('[0-9a-f]{40}', args.revision):
        parser.error('--revision must be a full Git SHA')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    name = 'ucc64-windows-x86-'+args.variant
    bundle = out/name; (bundle/'bin').mkdir(parents=True)
    for filename in ('ucc64.exe', 'Ucc64Bridge.dll'):
        source = args.tools/filename
        data = source.read_bytes()
        if len(data) < 64 or data[:2] != b'MZ':
            raise ValueError('Expected PE: '+filename)
        offset = struct.unpack_from('<I', data, 60)[0]
        if data[offset:offset+4] != b'PE\0\0' or struct.unpack_from('<H', data, offset+4)[0] != 0x14c:
            raise ValueError('Expected x86 PE: '+filename)
        shutil.copy2(source, bundle/'bin'/filename)
    shutil.copy2(ROOT/'LICENSE', bundle/'LICENSE')
    shutil.copy2(ROOT/'int64/third_party/minhook/LICENSE.txt', bundle/'MinHook-LICENSE.txt')
    shutil.copy2(ROOT/'int64/docs/COMPILER_BUNDLE.md', bundle/'README.md')
    files = {p.relative_to(bundle).as_posix(): digest(p) for p in sorted(bundle.rglob('*')) if p.is_file()}
    (bundle/'BUILDINFO.json').write_text(json.dumps(dict(revision=args.revision, variant=args.variant,
        target='Windows x86', files=files, scope='compiler tools; external matching SDK required'), indent=2)+'\n', encoding='utf-8')
    archive = out/(name+'.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                info = zipfile.ZipInfo(name+'/'+p.relative_to(bundle).as_posix())
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, p.read_bytes())
    extracted = out/'Проверка комплекта'
    with zipfile.ZipFile(archive) as z:
        z.extractall(extracted)
    check = extracted/name
    for path, value in files.items():
        if digest(check/path) != value:
            raise AssertionError('Extracted file hash differs: '+path)
    env = dict(os.environ)
    env['PATH'] = str(Path(os.environ['SYSTEMROOT'])/'System32')
    result = subprocess.run([str(check/'bin/ucc64.exe')], cwd=out, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    if result.returncode != 2 or b'Usage: ucc64.exe' not in result.stdout:
        raise AssertionError('Extracted launcher usage smoke failed')
    if any(digest(check/path) != value for path, value in files.items()):
        raise AssertionError('Smoke test changed bundle files')
    publish = out/'publish'; publish.mkdir()
    archive.rename(publish/archive.name)
    (publish/'SHA256SUMS.txt').write_text(digest(publish/archive.name)+'  '+archive.name+'\n', encoding='ascii')
    print('PASS: extracted Win32 compiler bundle and launcher usage; compilation requires external SDK')


if __name__ == '__main__':
    main()
