"""Reproducible x86 Windows build using an existing MinGW-w64 toolchain."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MINHOOK_COMMIT = 'c3fcafdc10146beb5919319d0683e44e3c30d537'


def verify_minhook(minhook):
    manifest = minhook / 'UPSTREAM.json'
    if manifest.exists():
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        if metadata['commit'] != MINHOOK_COMMIT:
            raise ValueError('Expected the bundled MinHook v1.3.4 commit')
        for name, expected in metadata['git_blobs'].items():
            data = (minhook / name).read_bytes()
            actual = hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()
            if actual != expected:
                raise ValueError(f'Bundled MinHook file differs from upstream: {name}')
        return metadata['commit']
    commit = subprocess.check_output(['git', '-C', str(minhook), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != MINHOOK_COMMIT:
        raise ValueError('Expected the official MinHook v1.3.4 commit')
    if subprocess.check_output(['git', '-C', str(minhook), 'diff', '--name-only'], text=True).strip():
        raise ValueError('MinHook working tree contains modifications')
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='i686-w64-mingw32-gcc')
    parser.add_argument('--cxx', default='i686-w64-mingw32-g++')
    parser.add_argument('--minhook-source', type=Path, default=ROOT / 'third_party/minhook')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/win32')
    args = parser.parse_args()
    for compiler in (args.cc, args.cxx):
        triple = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
        if triple != 'i686-w64-mingw32':
            raise ValueError(f'Wrong compiler target: {triple}')
    minhook = args.minhook_source.resolve()
    commit = verify_minhook(minhook)
    out = args.out.resolve()
    objects = out / 'obj'
    objects.mkdir(parents=True, exist_ok=True)
    inputs = ['src/buffer.c', 'src/hook.c', 'src/trampoline.c', 'src/hde/hde32.c']
    compiled = []
    for source in inputs:
        obj = objects / (Path(source).stem + '.o')
        subprocess.run([args.cc, '-O2', '-c', str(minhook / source), '-o', str(obj)], check=True)
        compiled.append(str(obj))
    common = [args.cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Wno-cast-function-type', '-Werror',
              '-static', '-I', str(ROOT / 'src')]
    targets = {
        'Ucc64Bridge.dll': ['-shared', '-I', str(minhook / 'include'), str(ROOT / 'src/editor_bridge.cpp'),
                            *compiled, '-Wl,--kill-at'],
        'ucc64.exe': ['-municode', str(ROOT / 'src/launcher.cpp'), '-lbcrypt', '-lpsapi'],
        'int64_semantics_test.exe': [str(ROOT / 'tests/int64_semantics_test.cpp')],
        'client_native_probe.exe': ['-municode', str(ROOT / 'tests/client_native_probe.cpp')],
    }
    for name, flags in targets.items():
        subprocess.run([*common, *flags, '-o', str(out / name)], check=True)
    shutil.copy2(minhook / 'LICENSE.txt', out / 'MinHook-LICENSE.txt')
    info = {
        'compiler': subprocess.check_output([args.cxx, '--version'], text=True).splitlines()[0],
        'target': 'i686-w64-mingw32',
        'minhook_commit': commit,
        'artifacts': {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in targets},
        'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [*sorted((ROOT / 'src').glob('*')),
                              ROOT / 'tests/int64_semantics_test.cpp', ROOT / 'tests/client_native_probe.cpp',
                              ROOT / 'third_party/minhook/UPSTREAM.json'] if p.is_file()},
    }
    (out / 'BUILDINFO.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
