"""Build the example independently of Ucc64Bridge/MinHook."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

EXAMPLE = Path(__file__).resolve().parents[1]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='i686-w64-mingw32-g++')
    parser.add_argument('--out', type=Path, default=EXAMPLE / 'build-mingw')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-B', str(EXAMPLE / 'tools/core_profiles.py'), 'generate'], check=True)
    if subprocess.check_output([args.cxx, '-dumpmachine'], text=True).strip() != 'i686-w64-mingw32':
        raise ValueError('Use a Windows i686 compiler')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    common = [args.cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Wno-cast-function-type', '-Werror',
              '-static', '-I', str(EXAMPLE / 'src')]
    subprocess.run([*common, '-shared', str(EXAMPLE / 'src/extension_runtime.cpp'), str(EXAMPLE / 'src/extensionL2.cpp'), '-Wl,--kill-at',
                    '-o', str(out / 'ExtensionL2.dll')], check=True)
    subprocess.run([*common, '-municode', str(EXAMPLE / 'tests/extension_probe.cpp'),
                    '-o', str(out / 'extension_probe.exe')], check=True)
    subprocess.run([*common, '-municode', str(EXAMPLE / 'tools/extension_bindings.cpp'),
                    '-o', str(out / 'extension_bindings.exe')], check=True)
    subprocess.run([*common, '-municode', str(EXAMPLE / 'tests/client_link_probe.cpp'),
                    '-o', str(out / 'client_link_probe.exe')], check=True)
    result = dict(binding_source='src/extensionL2.cpp', target='Windows x86',
                  files={n: hashlib.sha256((out / n).read_bytes()).hexdigest()
                          for n in ('ExtensionL2.dll', 'extension_probe.exe', 'extension_bindings.exe', 'client_link_probe.exe')},
                  sources={str(p.relative_to(EXAMPLE)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((EXAMPLE / 'src').glob('*')) if p.is_file()})
    (out / 'BUILDINFO.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
