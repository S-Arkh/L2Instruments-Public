"""Export a real package and compile it in a new, isolated SDK workspace.

External packages and detailed reports remain under ignored local storage.
Successful compilation is not a claim of bytecode or runtime equivalence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from backend import Core, component, export_classes, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-package-sha256', help='Require the known original input hash before export')
    parser.add_argument('--compiler', type=Path, required=True, help='Read-only SDK System directory')
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--dependency', type=Path, action='append', default=[])
    parser.add_argument('--preload', action='append', help='Explicit dependency package name in EditPackages order; repeat as needed')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--client-array-sort', action='store_true', help='Enable experimental client opcode 0x47')
    parser.add_argument('--client-enum-profile', choices=['korea290'], help='Explicit compiler-only dependency enum metadata profile')
    parser.add_argument('--scoped-enum-casts', action='store_true', help='Prefer lexical enums in explicit enum casts')
    args = parser.parse_args()
    package, compiler, out = args.package.resolve(), args.compiler.resolve(), args.out.resolve()
    package_hash = sha256(package)
    if args.expected_package_sha256 and package_hash != args.expected_package_sha256.lower():
        parser.error('Input package hash differs from the expected original')
    if not out.is_relative_to(ROOT/'local') or out == ROOT/'local':
        parser.error('Output must be a new directory beneath uExplorer/local')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    name = component(package.stem)
    out.mkdir(parents=True, exist_ok=False)
    system, tools = out/'System', out/'tools'
    system.mkdir()
    tools.mkdir()
    manifest = {'package': {'path': str(package), 'sha256': package_hash}, 'sdk': {}, 'tools': {}}
    for source in compiler.iterdir():
        if source.is_file() and source.suffix.lower() in ('.exe', '.dll', '.int', '.u', '.ini'):
            manifest['sdk'][source.name] = sha256(source)
            if source.name.lower() != (name+'.u').lower():
                shutil.copy2(source, system/source.name)
    for source in (args.launcher.resolve(), args.launcher.resolve().with_name('Ucc64Bridge.dll'), args.library.resolve()):
        shutil.copy2(source, tools/source.name)
        manifest['tools'][source.name] = sha256(source)
    (out/'inputs.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    dependencies = [str(p.resolve()) for p in args.dependency]
    core = Core(tools/args.library.name)
    inspected = core.request(operation='inspect', path=str(package), dependencies=dependencies)
    def progress(index, total, cls):
        if index % 50 == 0 or index == total:
            print(f'{index}/{total} {cls}', flush=True)
    exported = export_classes(core, package, inspected['package']['classes'], out/'export',
                              dependencies=dependencies, force=True, progress=progress)
    report = {'counts': exported['counts'], 'export_report': exported['report_file'],
              'compiler_exit': None, 'compiled': False, 'runtime_tested': False}
    def save():
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    save()
    if exported['counts']['partial'] or exported['counts']['failed']:
        raise RuntimeError('Export incomplete; see result.json and the export report')
    shutil.copytree(out/'export'/name/'Classes', out/name/'Classes')
    # The old UCC loader does not recognize UTF-8 source. BOM-marked UTF-16
    # preserves the generated code points and avoids treating each UTF-8 byte
    # as a separate character (which also spuriously exceeds token limits).
    for source in (out/name/'Classes').rglob('*.uc'):
        source.write_text(source.read_text(encoding='utf-8'), encoding='utf-16')
    report['compiler_source_encoding'] = 'utf-16-bom'
    (out/name/'Inc').mkdir()
    # UCC needs dependency packages in EditPackages even when their .u already
    # exists. They are loaded, not rebuilt: dependency sources are not copied.
    # Core and Engine are compilation targets too: never preload a dependent
    # package before rebuilding one of these foundational packages.
    preload = [] if name.lower() == 'core' else ['Core'] if name.lower() == 'engine' else ['Core', 'Engine']
    config = compiler/'UE2Runtime.ini'
    if args.preload is not None:
        preload = [component(value) for value in args.preload]
    elif name.lower() not in ('core', 'engine') and config.is_file():
        for line in config.read_text(errors='replace').splitlines():
            match = re.fullmatch(r'\s*EditPackages\s*=\s*([A-Za-z_][A-Za-z_0-9]*)\s*', line, re.I)
            if match and match[1].lower() == name.lower():
                break  # Later packages depend on the target, not vice versa.
            if match and match[1].lower() not in {n.lower() for n in preload}:
                preload.append(match[1])
    preload = [n for n in preload if n.lower() != name.lower()]
    for dependency in preload:
        if not any(p.name.lower() == (dependency+'.u').lower() for p in system.iterdir()):
            raise ValueError('Missing compiled SDK dependency: '+dependency)
    (system/'UE2Runtime.ini').write_text(
        '[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n'
        '[Core.System]\nPaths=../System/*.u\n\n'
        '[Editor.EditorEngine]\nCacheSizeMegs=256\n'+
        ''.join('EditPackages='+n+'\n' for n in preload+[name]), encoding='ascii')
    report['edit_packages'] = preload+[name]
    report['client_array_sort'] = args.client_array_sort
    report['client_enum_profile'] = args.client_enum_profile
    report['scoped_enum_casts'] = args.scoped_enum_casts
    environment = os.environ.copy()
    environment.pop('UCC64_CLIENT_ARRAY_SORT', None)
    environment.pop('UCC64_CLIENT_ENUM_PROFILE', None)
    environment.pop('UCC64_SCOPED_ENUM_CASTS', None)
    if args.scoped_enum_casts:
        environment['UCC64_SCOPED_ENUM_CASTS'] = '1'
    if args.client_enum_profile:
        environment['UCC64_CLIENT_ENUM_PROFILE'] = args.client_enum_profile
    if args.client_array_sort:
        environment['UCC64_CLIENT_ARRAY_SORT'] = '1'
    with (out/'compile.log').open('wb') as log:
        try:
            result = subprocess.run([str(tools/args.launcher.name), '--system', str(system),
                                     'make', '-NoBind', '-Silent'], cwd=system,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout, env=environment)
            report['compiler_exit'] = result.returncode
        except subprocess.TimeoutExpired:
            report['timeout'] = args.timeout
            save()
            raise
    output = system/(name+'.u')
    report['compiled'] = result.returncode == 0 and output.is_file()
    if output.is_file():
        report['output_sha256'] = sha256(output)
    save()
    print(json.dumps(report, indent=2), flush=True)
    if not report['compiled']:
        print((out/'compile.log').read_text(errors='replace')[-6000:])
        raise RuntimeError('External compilation failed; see compile.log')


if __name__ == '__main__':
    main()
