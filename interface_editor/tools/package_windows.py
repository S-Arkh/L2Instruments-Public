"""Cross-build a portable Windows x64 distribution from downloaded official archives.

Inputs are explicit local archives/toolchain paths; no downloads.
The portable directory includes CPython and Qt Essentials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def export_definition(dll):
    data = dll.read_bytes()
    pe = struct.unpack_from('<I', data, 60)[0]
    machine, count = struct.unpack_from('<HH', data, pe + 4)
    assert machine == 0x8664
    optional = pe + 24
    sections = optional + struct.unpack_from('<H', data, pe + 20)[0]
    table = []
    for i in range(count):
        offset = sections + 40 * i
        size, rva, raw_size, raw = struct.unpack_from('<4I', data, offset + 8)
        flags = struct.unpack_from('<I', data, offset + 36)[0]
        table.append((rva, max(size, raw_size), raw, flags))
    def offset(rva):
        for start, size, raw, flags in table:
            if start <= rva < start + size:
                return raw + rva - start
        raise ValueError('Invalid export RVA')
    export_rva = struct.unpack_from('<I', data, optional + 112)[0]
    export = offset(export_rva)
    names, funcs_rva, names_rva, ords_rva = struct.unpack_from('<4I', data, export + 24)
    lines = ['LIBRARY python312.dll', 'EXPORTS']
    for i in range(names):
        name_rva = struct.unpack_from('<I', data, offset(names_rva) + 4*i)[0]
        start = offset(name_rva)
        name = data[start:data.index(0, start)].decode('ascii')
        ordinal = struct.unpack_from('<H', data, offset(ords_rva) + 2*i)[0]
        function = struct.unpack_from('<I', data, offset(funcs_rva) + 4*ordinal)[0]
        executable = any(rva <= function < rva + size and flags & 0x20000000 for rva, size, raw, flags in table)
        lines.append(name + ('' if executable else ' DATA'))
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--cxx', required=True)
    parser.add_argument('--dlltool', required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/windows')
    parser.add_argument('--resume', action='store_true', help='Retry an incomplete package (without BUILDINFO.json)')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and (not args.resume or (out / 'BUILDINFO.json').exists()):
        raise ValueError('Choose a new output directory')
    out.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve()
    runtime = out / 'runtime'
    runtime.mkdir(exist_ok=True)
    embed = cache / 'python-3.12.10-embed-amd64.zip'
    with zipfile.ZipFile(embed) as archive:
        archive.extractall(runtime)
    shutil.copy2(ROOT / 'third_party/windows/zlib1.dll', runtime / 'zlib1.dll')
    (runtime / 'python312._pth').write_text('python312.zip\n.\n../app\n../packages\nimport site\n', encoding='ascii')
    packages = out / 'packages'
    packages.mkdir(exist_ok=True)
    wheels = [cache / 'pyside6_essentials-6.12.0-cp310-abi3-win_amd64.whl', cache / 'shiboken6-6.12.0-cp310-abi3-win_amd64.whl']
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(packages)
    headers = cache / 'interface-python312-headers'
    headers.mkdir(exist_ok=True)
    source = cache / 'Python-3.12.10.tgz'
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            relative = member.name.removeprefix('Python-3.12.10/')
            if member.isfile() and (relative.startswith('Include/') or relative == 'PC/pyconfig.h'):
                destination = headers / (relative.removeprefix('Include/') if relative != 'PC/pyconfig.h' else 'pyconfig.h')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.extractfile(member).read())
    definition = headers / 'python312.def'
    definition.write_text(export_definition(runtime / 'python312.dll'), encoding='ascii')
    library = headers / 'libpython312.a'
    subprocess.run([args.dlltool, '-d', str(definition), '-l', str(library), '-D', 'python312.dll'], check=True)
    import pybind11
    import nlohmann_json
    app = out / 'app'
    app.mkdir(exist_ok=True)
    command = [args.cxx, '-std=c++17', '-O2', '-shared', '-static', '-static-libgcc', '-static-libstdc++',
               '-DMS_WIN64', '-I'+str(headers), '-I'+str(pybind11.get_include()), '-I'+str(nlohmann_json.get_include()),
               '-I'+str(ROOT / 'core'), str(ROOT / 'core/document.cpp'), str(ROOT / 'core/textures.cpp'), str(ROOT / 'core/dat.cpp'), str(ROOT / 'bindings/module.cpp'),
               str(library), '-o', str(app / '_interface_core.pyd')]
    subprocess.run(command, check=True)
    for file in (ROOT / 'app').glob('*.py'):
        shutil.copy2(file, app / file.name)
    shutil.copytree(ROOT / 'schemas', out / 'schemas', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'LICENSE.acmi', out / 'LICENSE.acmi')
    for name in ('LICENSE', 'LICENSE.dat-format', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, out / name)
    (out / 'Start.cmd').write_text('@echo off\r\n"%~dp0runtime\\python.exe" "%~dp0app\\main.py" %*\r\nif errorlevel 1 pause\r\n', encoding='ascii')
    manifest = dict(python='3.12.10', qt='6.12.0', target='Windows x64',
        inputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [embed, source, *wheels]},
        core_module='_interface_core.pyd',
        runtime_files={'runtime/zlib1.dll': hashlib.sha256((runtime / 'zlib1.dll').read_bytes()).hexdigest()},
        core_sha256=hashlib.sha256((app / '_interface_core.pyd').read_bytes()).hexdigest())
    (out / 'BUILDINFO.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(out)


if __name__ == '__main__': main()
