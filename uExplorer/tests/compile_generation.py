"""Stage an external UCC under uExplorer/local and compile the synthetic generation probes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True, help='Read-only compiler System directory')
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New workspace under uExplorer/local')
    parser.add_argument('--library', type=Path, help='Decompile, recompile and compare function ASTs using this core')
    parser.add_argument('--sources', type=Path, default=ROOT/'tests/generation', help='Directory of synthetic .uc examples')
    parser.add_argument('--metadata-probe', type=Path, help='Compare class Within/native flags and property metadata as well')
    parser.add_argument('--expect-error', help='Negative probe: require this compiler diagnostic and no output package')
    parser.add_argument('--check-defaults', action='store_true', help='Also compare canonical generated default blocks after recompilation')
    parser.add_argument('--client-array-sort', action='store_true', help='Enable experimental client opcode 0x47 in the isolated compiler')
    parser.add_argument('--client-enum-profile', choices=['korea290'], help='Explicit compiler-only dependency enum metadata profile')
    parser.add_argument('--scoped-enum-casts', action='store_true', help='Prefer lexical enums in explicit enum casts')
    parser.add_argument('--sdk-sort-probe', type=Path, help='Test-only decoder for SDK packages containing client Sort bytecode')
    parser.add_argument('--semantic-probe', type=Path, help='Run the fixed semantics fixture in the native VM; record its expected reconstruction differences')
    args = parser.parse_args()
    if args.semantic_probe and (args.sources.resolve() != ROOT/'tests/semantics' or not args.library or args.metadata_probe):
        parser.error('--semantic-probe requires --sources tests/semantics and --library; metadata comparison is a separate gate')
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
    if args.sdk_sort_probe and not (args.client_array_sort and args.library):
        parser.error('--sdk-sort-probe requires --client-array-sort and --library')
    if args.expect_error and args.library:
        parser.error('--expect-error cannot be combined with --library')
    if args.check_defaults and not args.library:
        parser.error('--check-defaults requires --library')
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'local'):
        parser.error('Output must be under uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    system = out/'System'
    system.mkdir()
    for source in args.compiler.iterdir():
        if source.is_file() and source.suffix.lower() in ('.exe', '.dll', '.int', '.u', '.ini'):
            shutil.copy2(source, system/source.name)
    for source in (args.launcher, args.launcher.with_name('Ucc64Bridge.dll')):
        shutil.copy2(source, system/source.name)
    (system/'UE2Runtime.ini').write_text('[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n[Core.System]\nPaths=../System/*.u\n\n[Editor.EditorEngine]\nCacheSizeMegs=256\nEditPackages=Core\nEditPackages=Engine\nEditPackages=Generation\n', encoding='ascii')
    shutil.copytree(args.sources, out/'Generation/Classes')
    for source in (out/'Generation/Classes').glob('*.uc'):
        source.write_text(source.read_text(encoding='utf-8-sig'), encoding='utf-16')
    (out/'Generation/Inc').mkdir()
    with (out/'compile.log').open('wb') as log:
        result = subprocess.run([str(system/args.launcher.name), '--system', str(system), 'make', '-NoBind', '-Silent'],
                                cwd=system, stdout=log, stderr=subprocess.STDOUT, timeout=180, env=environment)
    log_text = (out/'compile.log').read_text(errors='replace')
    print(log_text)
    if args.expect_error:
        if result.returncode == 0 or (system/'Generation.u').exists() or args.expect_error not in log_text:
            raise AssertionError('Expected compiler rejection was not observed')
        print('PASS: expected compiler rejection: ' + args.expect_error)
        return
    if result.returncode or not (system/'Generation.u').is_file():
        raise RuntimeError('Probe compilation failed')
    if not args.library:
        return
    sys.path.insert(0, str(ROOT/'python'))
    from backend import Core
    core = Core(args.library.resolve())
    package = system/'Generation.u'
    bytecode_profile = 'sdk-client-sort' if args.client_array_sort else 'auto'
    def snapshot():
        if args.sdk_sort_probe:
            data = json.loads(subprocess.check_output([str(args.sdk_sort_probe.resolve()), str(package)], encoding='utf-8'))
            return data['classes'], data['functions'], data['sources'], data['class_scripts']
        summary = core.request(operation='inspect', path=str(package), reload=True, bytecode_profile=bytecode_profile)['package']
        functions, sources, class_scripts = {}, {}, {}
        for cls in summary['classes']:
            result = core.request(operation='decompile', path=str(package), class_id=cls['id'], force_bytecode=True, bytecode_profile=bytecode_profile)['result']
            if result['status'] != 'recovered':
                raise AssertionError(result['issues'])
            sources[cls['name']] = result['code']
            class_scripts[cls['name']] = result.get('class_script', [])
            for function in result['functions']:
                if 'state' in function:
                    class_scripts[function['state']] = function.get('bytecode', [])
                if 'name' in function:
                    functions[function['name']] = core.request(operation='function', path=str(package), function=function['name'], bytecode_profile=bytecode_profile)['result']
        return summary['classes'], functions, sources, class_scripts
    before_classes, before, sources, before_scripts = snapshot()
    source_checks = args.sources/'expected-generation.json'
    if source_checks.is_file():
        for name, checks in json.loads(source_checks.read_text(encoding='utf-8')).items():
            generated = sources[name]
            for text in checks.get('contains', []):
                if text not in generated:
                    raise AssertionError(f'{name}: missing generated source: {text!r}')
            for text in checks.get('excludes', []):
                if text in generated:
                    raise AssertionError(f'{name}: unexpected generated source: {text!r}')
    def metadata():
        if not args.metadata_probe:
            return None
        rows = json.loads(subprocess.check_output([str(args.metadata_probe.resolve()), str(package)], text=True, encoding='utf-8'))
        return {row.get('class', row.get('property', row.get('state'))): {k: v for k, v in row.items() if k != 'raw'} for row in rows}
    before_meta = metadata()
    (out/'original').mkdir()
    shutil.copy2(package, out/'original/Generation.u')
    for name, code in sources.items():
        (out/'Generation/Classes'/f'{name}.uc').write_text(code, encoding='utf-16')
    package.unlink()
    with (out/'recompile.log').open('wb') as log:
        result = subprocess.run([str(system/args.launcher.name), '--system', str(system), 'make', '-NoBind', '-Silent'],
                                cwd=system, stdout=log, stderr=subprocess.STDOUT, timeout=180, env=environment)
    print((out/'recompile.log').read_text(errors='replace'))
    if result.returncode or not package.is_file():
        raise RuntimeError('Generated source did not compile')
    after_classes, after, after_sources, after_scripts = snapshot()
    after_meta = metadata()
    def canonical(value):
        if isinstance(value, list):
            return [canonical(v) for v in value]
        if isinstance(value, dict):
            # Object table indices can change; symbolic references are retained in text.
            return {k: canonical(v) for k, v in value.items() if k != 'reference'}
        return value
    differences = [name for name in before if canonical(before[name]) != canonical(after.get(name))]
    expected_changes = {'SemanticsProbe.Contexts', 'SemanticsProbe.Flow'} if args.semantic_probe else set()
    errors = [name for name in differences if name not in expected_changes]
    for name in expected_changes & set(before):
        for field in ('native', 'flags', 'replication_offset'):
            if before[name].get(field) != after.get(name, {}).get(field):
                errors.append(name + ': changed ' + field)
    helpers = {'SemanticsProbe.__UXContextInt', 'SemanticsProbe.__UXContextInt_Bool', 'SemanticsProbe.__UXContextInt_Float'} if args.semantic_probe else set()
    if args.semantic_probe and (set(differences) != expected_changes or set(after)-set(before) != helpers):
        errors.append('expected semantic reconstruction/helper coverage changed')
    if canonical(before_scripts) != canonical(after_scripts):
        errors.append('class script/replication conditions changed')
        (out/'class-scripts-before.json').write_text(json.dumps(before_scripts, indent=2), encoding='utf-8')
        (out/'class-scripts-after.json').write_text(json.dumps(after_scripts, indent=2), encoding='utf-8')
    if args.check_defaults:
        for name, source in sources.items():
            if source.partition('defaultproperties\n')[2] != after_sources.get(name, '').partition('defaultproperties\n')[2]:
                errors.append('defaults changed: ' + name)
    # Dependency ordering can move exports without changing class identities.
    if set(before) | helpers != set(after) or sorted((c['name'], c['super']) for c in before_classes) != sorted((c['name'], c['super']) for c in after_classes):
        errors.append('class/function set or inheritance changed')
    if before_meta != after_meta:
        errors.append('class/Within/native/property metadata changed')
        (out/'metadata-before.json').write_text(json.dumps(before_meta, indent=2), encoding='utf-8')
        (out/'metadata-after.json').write_text(json.dumps(after_meta, indent=2), encoding='utf-8')
    report = dict(functions=len(before), errors=errors, metadata_checked=bool(args.metadata_probe), defaults_checked=args.check_defaults,
                  ast_differences=differences, added_functions=sorted(set(after)-set(before)), semantic_runtime_passed=False,
                  client_array_sort=args.client_array_sort, client_enum_profile=args.client_enum_profile, scoped_enum_casts=args.scoped_enum_casts,
                  sdk_sort_probe_sha256=hashlib.sha256(args.sdk_sort_probe.read_bytes()).hexdigest() if args.sdk_sort_probe else None,
                  bridge_sha256=hashlib.sha256((system/'Ucc64Bridge.dll').read_bytes()).hexdigest(),
                  original_sha256=hashlib.sha256((out/'original/Generation.u').read_bytes()).hexdigest(),
                  compiled_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),
                  core_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest())
    (out/'roundtrip.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if errors or differences:
        (out/'ast-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
        (out/'ast-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    if errors:
        raise AssertionError(errors)
    if args.semantic_probe:
        subprocess.run([sys.executable, '-B', str(ROOT.parent/'int64/tests/script_semantics.py'),
                        '--compiler', str(args.compiler.resolve()), '--launcher', str(args.launcher.resolve()),
                        '--probe', str(args.semantic_probe.resolve()), '--original', str(out/'original/Generation.u'),
                        '--recompiled', str(package), '--out', str(out/'runtime')], check=True)
        report['semantic_runtime_passed'] = True
        (out/'roundtrip.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print('PASS: independent VM semantic cases; AST reconstruction differences recorded (not exact equivalence)')
        return
    print('PASS: compiler roundtrip, function flags, PCs, symbolic ASTs and requested metadata match')


if __name__ == '__main__':
    main()
