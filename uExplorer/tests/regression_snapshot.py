"""Run compiler/exporter contracts against a copied, hash-bound tool snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SUITES = ('generation', 'expressions', 'metadata', 'defaults', 'replication',
          'iterators', 'states', 'int64_enums', 'optional_arrays', 'enum_collisions',
          'pointers', 'pointer_replication_controls', 'metadata_lifecycle', 'array_sort',
          'struct_enums', 'reference_defaults', 'state_labels', 'class_defaults', 'indexed_defaults')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compiler', 'tools', 'explorer', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--runtime-probe', type=Path, help='Native lifecycle DLL; may be built by another compiler')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'uExplorer/local'):
        parser.error('Output must be a new directory beneath uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    tools = out/'tools'; tools.mkdir()
    for directory, names in [(args.tools, ('ucc64.exe', 'Ucc64Bridge.dll')),
                             (args.explorer, ('uexplorer_core.dll', 'uexplorer_metadata_probe.exe'))]:
        for name in names:
            shutil.copy2(directory/name, tools/name)
    shutil.copy2(args.runtime_probe or args.tools/'ptr_lifecycle_probe.dll', tools/'ptr_lifecycle_probe.dll')
    tracked = [p for directory in ('int64/src', 'int64/tests', 'uExplorer/core', 'uExplorer/tests')
               for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ('.cpp', '.h', '.py', '.uc')]
    sources = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in tracked}
    binaries = {p.name: digest(p) for p in tools.iterdir()}
    inputs = {p.name: digest(p) for p in args.compiler.iterdir() if p.is_file() and p.suffix.lower() in ('.dll', '.exe', '.u', '.ini', '.int')}
    result = dict(sources=sources, tools=binaries, sdk=inputs, checks={})
    (out/'inputs.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    def run(label, script, *arguments):
        with (out/(label+'.log')).open('wb') as log:
            process = subprocess.run([sys.executable, '-B', str(ROOT/script), *map(str, arguments)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        result['checks'][label] = dict(passed=process.returncode == 0, exit=process.returncode)
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(label, 'PASS' if process.returncode == 0 else 'FAIL', flush=True)
        return process.returncode == 0
    common = ['--compiler', args.compiler.resolve(), '--launcher', tools/'ucc64.exe']
    for suite in SUITES:
        options = ['--scoped-enum-casts'] if suite == 'enum_collisions' else []
        if suite in ('struct_enums', 'reference_defaults', 'class_defaults', 'indexed_defaults'): options += ['--check-defaults']
        if suite == 'array_sort': options += ['--client-array-sort']
        run(suite, 'uExplorer/tests/compile_generation.py', *common, '--library', tools/'uexplorer_core.dll',
            '--metadata-probe', tools/'uexplorer_metadata_probe.exe', '--sources', ROOT/'uExplorer/tests'/suite,
            '--out', out/suite, *options)
    run('semantics', 'uExplorer/tests/compile_generation.py', *common, '--library', tools/'uexplorer_core.dll',
        '--sources', ROOT/'uExplorer/tests/semantics', '--semantic-probe', tools/'ptr_lifecycle_probe.dll',
        '--scoped-enum-casts', '--out', out/'semantics')
    run('sort-profile', 'uExplorer/tests/test_sort_profile.py', '--library', tools/'uexplorer_core.dll',
        '--package', out/'array_sort/System/Generation.u')
    run('sort-negative', 'uExplorer/tests/sort_negative.py', *common, '--out', out/'sort-negative')
    run('pointer-negative', 'int64/tests/pointer_compiler.py', *common, '--out', out/'pointer-negative')
    run('pointer-runtime', 'int64/tests/ptr_lifecycle.py', *common, '--probe', tools/'ptr_lifecycle_probe.dll',
        '--metadata-probe', tools/'uexplorer_metadata_probe.exe', '--compiled-package', out/'pointers/System/Generation.u',
        '--out', out/'pointer-runtime')
    run('metadata-runtime', 'int64/tests/metadata_contract.py', '--compiler', args.compiler.resolve(),
        '--tools', tools, '--metadata-probe', tools/'uexplorer_metadata_probe.exe',
        '--package', out/'metadata_lifecycle/System/Generation.u', '--out', out/'metadata-runtime')
    result['unchanged'] = (all(digest(ROOT/name) == value for name, value in sources.items()) and
        all(digest(tools/name) == value for name, value in binaries.items()) and
        all(digest(args.compiler/name) == value for name, value in inputs.items()))
    result['passed'] = result['unchanged'] and all(c['passed'] for c in result['checks'].values())
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    if not result['passed']:
        raise AssertionError('Snapshot regression failed; inspect individual logs')
    print('PASS: snapshot unchanged and all compiler/exporter/runtime contracts passed')


if __name__ == '__main__':
    main()
