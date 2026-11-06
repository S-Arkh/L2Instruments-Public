"""Audit all supplied .u packages in isolated original/rebuilt dependency workspaces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'python'), str(ROOT.parent/'int64/tools')]
from backend import Core, atomic_write as backend_atomic_write, component, export_classes, sha256
from ue2package import Reader

PRIMARY = ('Core', 'Engine', 'NWindow', 'Interface', 'InterfaceClassic')
RESOURCE_SUFFIXES = {'.utx', '.uax', '.usx', '.ukx', '.unr'}
# Resource name/import tables share this layout; this does not enable script,
# texture, sound or mesh payload decoding for these additional profiles.
RESOURCE_TABLE_PROFILES = ({(118, n) for n in (0, 6, 11)} |
                           {(123, n) for n in (0, 12, 14, 15, 16, 18, 19, 20, 22, 23, 25, 27, 28, 30, 31, 33, 35, 36, 37, 38)} |
                           {(125, 38), (125, 39), (126, 39), (127, 39), (128, 39), (129, 39),
                            (130, 40), (131, 40), (132, 40), (133, 40)})


def package_payload(data, filename=None):
    """Remove only a verified XOR envelope; leave the serialized package intact."""
    for marker in ('Lineage2Ver111', 'GamekitData111', 'Lineage2Ver121', 'GamekitData121'):
        prefix = marker.encode('utf-16le')
        if data.startswith(prefix):
            key = 0xac
            if marker.endswith('121'):
                if not filename or not Path(filename).name.isascii():
                    raise ValueError('Envelope 121 requires an ASCII source basename')
                key = sum(Path(filename).name.lower().encode('ascii')) & 255
            data = data[len(prefix):].translate(bytes(i ^ key for i in range(256)))
            break
    if data[:4] != b'\xc1\x83\x2a\x9e':
        raise ValueError('Unsupported envelope or invalid package signature')
    return data


def dependency_closure(path, files, cache=None):
    seen = set(); missing = set()
    def visit(p):
        if cache is not None:
            if p not in cache: cache[p] = imported_packages(p)
            imports = cache[p]
        else: imports = imported_packages(p)
        for name in imports:
            if name == path.stem.casefold() or name in seen:
                continue
            seen.add(name)
            if name in files: visit(files[name])
            else: missing.add(name)
    visit(path)
    return sorted(seen), sorted(missing)


def dependency_lookup(profile, mode):
    return {**profile['resources'], **profile['rebuilt']} if mode == 'chain' else {**profile['resources'], **profile['files']}


def atomic_write(path, data):
    # A Windows reader/antivirus can briefly omit FILE_SHARE_DELETE. Retry only
    # sharing/access failures; do not treat disk-full or other I/O errors as transient.
    for attempt in range(8):
        try:
            return backend_atomic_write(path, data)
        except OSError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 7:
                raise
            time.sleep(0.025 * (attempt + 1))


def write_report(rows, report, results_path, complete=False):
    lines = ['Проверка всех .u: декомпиляция и компиляция',
             'СТАТУС: '+('завершена' if complete else 'выполняется'),
             'Компиляция: ORIGINAL — оригинальные зависимости; CHAIN — пересобранные зависимости.',
             'SDK и инструменты закреплены хешами в inputs.json. Исходники вручную не исправлялись.',
             'PASS компиляции не доказывает точность метаданных или клиентскую совместимость.',
             'Режимы компилятора заданы явно для каждого профиля и сохранены в JSON.',
             'Матрица результатов: '+str(results_path), '']
    for row in rows:
        lines.append(row['profile']+'/'+row['file'])
        lines.append('  Декомпиляция: '+json.dumps(row.get('export', row.get('error', 'ожидается')), ensure_ascii=False))
        if 'issues' in row: lines.append('  Замечаний генератора: '+str(row['issues']))
        if row.get('export_report'): lines.append('  Отчёт экспорта: '+row['export_report'])
        for mode in ('original', 'chain'):
            result = row.get(mode, {'status': 'PENDING'})
            lines.append('  '+mode.upper()+': '+result['status'])
            if result.get('reason'): lines.append('    '+result['reason'])
            if result.get('diagnostic'): lines.append('    '+result['diagnostic'])
            if result.get('log'): lines.append('    Лог: '+result['log'])
    atomic_write(report, ('\n'.join(lines)+'\n').encode('utf-8'))


def imported_packages(path):
    """Read only name/import tables, using the same header profiles as C++.

    The int64 bytecode reader deliberately accepts fewer package profiles and
    must not be used as a gate for modern client dependency discovery.
    """
    data = package_payload(path.read_bytes(), path.name)
    reader = Reader(data)
    if reader.unpack('<I') != 0x9e2a83c1:
        raise ValueError('Invalid package signature')
    profile = (reader.unpack('<H'), reader.unpack('<H'))
    script_profile = profile in ((123, 0), (123, 37), (126, 0), (131, 40), (133, 40))
    resource_profile = path.suffix.lower() in RESOURCE_SUFFIXES and profile in RESOURCE_TABLE_PROFILES
    if not (script_profile or resource_profile):
        raise ValueError('Unsupported dependency-table profile: '+str(profile))
    reader.unpack('<I')
    nc, no, ec, eo, ic, io = (reader.unpack('<i') for _ in range(6))
    for count, offset in ((nc, no), (ec, eo), (ic, io)):
        if not 0 <= count <= min(2000000, len(data)) or not 0 <= offset < len(data):
            raise ValueError('Invalid package table bounds')
    names = []
    reader.pos = no
    for _ in range(nc):
        names.append(reader.string()); reader.unpack('<I')
    def name():
        index = reader.index()
        if not 0 <= index < len(names): raise ValueError('Invalid import name index')
        return names[index]
    imports = []
    reader.pos = io
    for _ in range(ic):
        name(); kind = name(); outer = reader.unpack('<i'); value = name()
        imports.append((kind, outer, value))
    roots = set()
    for index in range(len(imports)):
        seen = set()
        while True:
            if index in seen: raise ValueError('Cyclic import outer chain')
            seen.add(index)
            kind, outer, value = imports[index]
            if not outer:
                if kind != 'Package': raise ValueError('Import root is not a package')
                roots.add(value.casefold()); break
            if not -len(imports) <= outer < 0: raise ValueError('Invalid import outer')
            index = -outer-1
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', action='append', required=True, help='Label=read-only System directory')
    parser.add_argument('--asset-root', action='append', default=[], help='Label=read-only resource directory; repeat for additional directories')
    for name in ('compiler', 'launcher', 'library', 'out', 'report'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--json-progress', action='store_true', help='Emit package updates for the parallel coordinator')
    parser.add_argument('--resume', action='store_true', help='Resume an existing hash-matching matrix without repeating completed packages')
    parser.add_argument('--export-cache', type=Path, help='Reuse completed hash-verified exports from an earlier matrix')
    parser.add_argument('--client-sort-profile', action='append', default=[], help='Client label enabling opcode 0x47 compilation')
    parser.add_argument('--scoped-enum-profile', action='append', default=[], help='Client label enabling lexical enum casts')
    parser.add_argument('--client-enum-profile', action='append', default=[], help='ClientLabel=korea290; only explicitly configured labels')
    args = parser.parse_args()
    enum_profiles = dict(item.split('=', 1) for item in args.client_enum_profile)
    if any(value != 'korea290' for value in enum_profiles.values()):
        parser.error('Only korea290 compiler enum profile is currently available')
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'local') or out == ROOT/'local':
        parser.error('Output must be a new directory beneath uExplorer/local')
    previous = json.loads((out/'inputs.json').read_text(encoding='utf-8')) if args.resume else None
    out.mkdir(parents=True, exist_ok=args.resume)
    def snapshot(source, target):
        if args.resume and target.exists():
            if sha256(source) != sha256(target): raise ValueError('Resume input changed: '+str(source))
        else:
            shutil.copy2(source, target)
    tools = out/'tools'; tools.mkdir(exist_ok=args.resume)
    for p in (args.launcher, args.launcher.with_name('Ucc64Bridge.dll'), args.library):
        snapshot(p, tools/p.name)
    core = Core(tools/args.library.name)
    rows = json.loads((out/'results.json').read_text(encoding='utf-8'))['packages'] if args.resume else []
    rows = [r for r in rows if 'original' in r and 'chain' in r]
    completed = {(r['profile'], r['file']) for r in rows}
    profiles = {}
    manifest = {'tools': {p.name: sha256(p) for p in tools.iterdir()}, 'inputs': {}, 'sdk': {}}
    asset_roots = {}
    for item in args.asset_root:
        label, directory = item.split('=', 1)
        asset_roots.setdefault(label, []).append(Path(directory))
    if set(asset_roots) - {item.split('=', 1)[0] for item in args.profile}:
        parser.error('Asset root references an unknown profile')
    if asset_roots: manifest['resources'] = {}
    sdk = out/'sdk'; sdk.mkdir(exist_ok=args.resume)
    for p in args.compiler.iterdir():
        if p.is_file() and p.suffix.lower() in ('.dll', '.exe', '.u', '.int', '.ini'):
            snapshot(p, sdk/p.name); manifest['sdk'][p.name] = sha256(p)
    for item in args.profile:
        label, directory = item.split('=', 1); component(label)
        root = out/label; frozen = root/'inputs'; frozen.mkdir(parents=True, exist_ok=args.resume)
        files = {}
        for p in sorted(Path(directory).iterdir()):
            if p.is_file() and p.suffix.lower() == '.u':
                component(p.stem)
                target = frozen/p.name; snapshot(p, target)
                digest = sha256(target)
                if digest != sha256(p):
                    raise ValueError('Input changed while copying: '+p.name)
                files[p.stem.casefold()] = target
                manifest['inputs'][label+'/'+p.name] = {'path': str(p.resolve()), 'sha256': digest}
        resources = {}; ambiguous = set()
        for directory in asset_roots.get(label, []):
            for p in sorted(directory.rglob('*')):
                if not p.is_file() or p.suffix.lower() not in RESOURCE_SUFFIXES: continue
                key = p.stem.casefold()
                if key in files: ambiguous.add(key); continue
                if key in resources:
                    if sha256(resources[key]) != sha256(p): ambiguous.add(key)
                    continue
                resources[key] = p
        # Freeze only the transitive resource closure used by the script inputs.
        needed = set(); import_cache = {}; resource_errors = {}
        for p in files.values():
            try:
                deps, _ = dependency_closure(p, {**resources, **files}, import_cache)
                if ambiguous.intersection(deps):
                    raise ValueError('Ambiguous resource package roots: '+', '.join(sorted(ambiguous.intersection(deps))))
            except ValueError as error:
                resource_errors[p.stem.casefold()] = str(error)
                continue
            needed.update(d for d in deps if d in resources)
        frozen_resources = {}
        for key in sorted(needed):
            source = resources[key]
            digest = sha256(source)
            manifest['resources'][label+'/'+source.name] = {'path': str(source.resolve()), 'sha256': digest}
            # Resources can exceed free disk space. Pin their hashes here and
            # materialize verified, isolated copies only in each compile workspace.
            frozen_resources[key] = source
        profiles[label] = {'root': root, 'files': files, 'resources': frozen_resources, 'rebuilt': {},
                           'resource_errors': resource_errors, 'import_cache': import_cache, 'loader_blockers': {}}
        for row in rows:
            if row['profile'] == label and row['chain']['status'] == 'PASS':
                artifact = root/'compiled/chain'/row['file']
                if sha256(artifact) != row['chain']['sha256']: raise ValueError('Rebuilt dependency changed')
                profiles[label]['rebuilt'][artifact.stem.casefold()] = artifact
    if previous is not None and manifest != previous:
        raise ValueError('Resume manifest differs from the original snapshot')
    (out/'inputs.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    def save(complete=False):
        atomic_write(out/'results.json', json.dumps({'complete': complete, 'packages': rows}, ensure_ascii=False, indent=2).encode('utf-8'))
        write_report(rows, args.report, out/'results.json', complete)
        if args.json_progress and rows:
            print('MATRIX_ROW '+json.dumps(rows[-1], ensure_ascii=True), flush=True)

    def compile_one(row, profile, path, mode, sources):
        root = profile['root']; workspace = root/'work'; system = workspace/'System'
        if mode == 'original':
            for dep in row['dependencies']:
                if dep in profile['loader_blockers']:
                    return {'status': 'BLOCKED', 'reason': 'SDK dependency load previously failed: '+dep,
                            'evidence_log': profile['loader_blockers'][dep]}
        # This workspace is created exclusively by this runner and reused to
        # bound disk usage; logs and output packages are retained separately.
        if workspace.exists(): shutil.rmtree(workspace)
        shutil.copytree(sdk, system)
        lookup = dependency_lookup(profile, mode)
        required = sum(lookup[dep].stat().st_size for dep in row['dependencies'])
        if required + 1024**3 > shutil.disk_usage(root).free:
            return {'status': 'BLOCKED', 'reason': 'Insufficient workspace disk space for isolated dependencies', 'required_bytes': required}
        for dep in row['dependencies']:
            source = lookup[dep]
            for old in system.iterdir():
                if old.name.casefold() == source.name.casefold(): old.unlink()
            # The stock SDK does not understand client XOR envelopes. Decode
            # only the workspace copy, without changing version or metadata.
            data = source.read_bytes()
            if dep in profile['resources']:
                expected = manifest['resources'][row['profile']+'/'+source.name]['sha256']
                if hashlib.sha256(data).hexdigest() != expected: raise ValueError('Resource changed before staging: '+source.name)
            (system/source.name).write_bytes(package_payload(data, source.name))
        for old in system.iterdir():
            if old.name.casefold() == path.name.casefold(): old.unlink()
        classes = workspace/path.stem/'Classes'; classes.mkdir(parents=True)
        for source in sources.rglob('*.uc'):
            target = classes/source.relative_to(sources); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding='utf-8'), encoding='utf-16')
        (workspace/path.stem/'Inc').mkdir()
        rank = {name.casefold(): i for i, name in enumerate(PRIMARY)}
        ordered = sorted(row['dependencies'], key=lambda n: (rank.get(n, 10), n))
        # Core and Engine must precede other imported packages.
        ordered = sorted(ordered, key=lambda n: 0 if n == 'core' else 1 if n == 'engine' else 2)
        names = [lookup[n].stem for n in ordered if n in profile['files']]+[path.stem]
        paths = ''.join('Paths=../System/*'+suffix+'\n' for suffix in ['.u']+sorted(RESOURCE_SUFFIXES))
        (system/'UE2Runtime.ini').write_text('[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n[Core.System]\n'+paths+'\n[Editor.EditorEngine]\nCacheSizeMegs=256\n'+''.join('EditPackages='+n+'\n' for n in names), encoding='ascii')
        env = dict(os.environ)
        for key in ('UCC64_CLIENT_ARRAY_SORT', 'UCC64_CLIENT_ENUM_PROFILE', 'UCC64_SCOPED_ENUM_CASTS'):
            env.pop(key, None)
        env.update(row['compiler_environment'])
        artifact = root/'compiled'/mode; artifact.mkdir(parents=True, exist_ok=True)
        log = artifact/(path.stem+'.log')
        try:
            with log.open('wb') as stream:
                run = subprocess.run([str(tools/args.launcher.name), '--system', str(system), 'make', '-NoBind', '-Silent'], cwd=system, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout)
            result = {'status': 'PASS' if run.returncode == 0 and (system/path.name).is_file() else 'FAIL', 'exit': run.returncode, 'log': str(log)}
        except subprocess.TimeoutExpired:
            result = {'status': 'TIMEOUT', 'log': str(log)}
        text = log.read_text(encoding='utf-8', errors='replace')
        errors = [line.strip() for line in text.splitlines() if any(t in line.lower() for t in ('error,', 'warning,', 'critical:', 'general protection', 'failed', 'history:'))]
        if errors: result['diagnostic'] = '\n    '.join(errors[:6])
        if result['status'] == 'FAIL':
            result['failure_stage'] = ('dependency_load' if ('ULinkerLoad::Preload' in text or ('FUnrealfileSummary<<' in text and 'LoadSummary' in text))
                                       else 'source_compile' if 'Error,' in text else 'unknown')
            if mode == 'original' and 'engine' in row['dependencies'] and 'ClassProperty Engine.Engine.FlashDevice' in text and 'Assertion failed: MetaClass' in text:
                profile['loader_blockers']['engine'] = str(log)
        if result['status'] == 'PASS':
            target = artifact/path.name; shutil.copy2(system/path.name, target)
            result['sha256'] = sha256(target)
            if mode == 'chain': profile['rebuilt'][path.stem.casefold()] = target
        return result

    tasks = [(label, p) for label, profile in profiles.items() for p in profile['files'].values()]
    rank = {n.casefold(): i for i, n in enumerate(PRIMARY)}
    tasks.sort(key=lambda x: (0 if x[1].stem.casefold() in rank else 1, list(profiles).index(x[0]), rank.get(x[1].stem.casefold(), 99), x[1].name))
    for label, path in tasks:
        if (label, path.name) in completed:
            continue
        profile = profiles[label]
        environment = {}
        if label in args.client_sort_profile: environment['UCC64_CLIENT_ARRAY_SORT'] = '1'
        if label in args.scoped_enum_profile: environment['UCC64_SCOPED_ENUM_CASTS'] = '1'
        if label in enum_profiles: environment['UCC64_CLIENT_ENUM_PROFILE'] = enum_profiles[label]
        row = {'profile': label, 'file': path.name, 'sha256': sha256(path), 'runtime_tested': False, 'compiler_environment': environment}; rows.append(row); save()
        try:
            inspected = core.request(operation='inspect', path=str(path), dependencies=[str(path.parent)])
            classes = inspected['package']['classes']
            def progress(i, total, name):
                if i % 100 == 0 or i == total: print(label, path.name, i, total, flush=True)
            cached = args.export_cache/label/'export'/path.stem if args.export_cache else None
            reports = sorted(cached.glob('export-report-*.json')) if cached else []
            own_export = profile['root']/'export'/path.stem
            own_reports = sorted(own_export.glob('export-report-*.json'))
            if args.resume and own_reports:
                cached, reports = own_export, own_reports
            if reports:
                candidate = json.loads(reports[-1].read_text(encoding='utf-8'))
                if candidate.get('core_sha256') != manifest['tools'][args.library.name]:
                    reports = []
            if reports:
                exported = json.loads(reports[-1].read_text(encoding='utf-8'))
                if exported['sha256'] != row['sha256']:
                    raise ValueError('Cached export input hash mismatch')
                if len(exported['classes']) != len(classes):
                    raise ValueError('Cached export class count mismatch')
                for entry in exported['classes']:
                    if entry.get('file') and sha256(Path(entry['file'])) != entry['output_sha256']:
                        raise ValueError('Cached source changed')
                exported['report_file'] = str(reports[-1])
                sources = cached/'Classes'
            else:
                if args.resume and own_export.exists():
                    index = 1
                    while own_export.with_name(own_export.name+'.interrupted-'+str(index)).exists(): index += 1
                    own_export.rename(own_export.with_name(own_export.name+'.interrupted-'+str(index)))
                exported = export_classes(core, path, classes, profile['root']/'export', dependencies=[str(path.parent)], force=True, progress=progress)
                sources = profile['root']/'export'/path.stem/'Classes'
            row['export'] = exported['counts']; row['export_report'] = exported['report_file']
            row['issues'] = sum(len(c.get('issues', [])) for c in exported['classes'])
            save()
            if exported['counts']['failed'] or exported['counts']['partial']:
                row['original'] = row['chain'] = {'status': 'BLOCKED', 'reason': 'Неполный экспорт'}
            elif not classes:
                row['original'] = row['chain'] = {'status': 'SKIP', 'reason': 'В пакете нет классов UnrealScript; экспорт ресурсов не проверен'}
            elif path.stem.casefold() in profile['resource_errors']:
                row['original'] = row['chain'] = {'status': 'BLOCKED', 'reason': 'Dependency discovery failed: '+profile['resource_errors'][path.stem.casefold()]}
            else:
                deps, missing = dependency_closure(path, dependency_lookup(profile, 'original'), profile['import_cache'])
                row['dependencies'] = deps
                row['resource_dependencies'] = [d for d in deps if d in profile['resources']]
                row['original'] = {'status': 'BLOCKED', 'reason': 'Отсутствуют зависимости: '+', '.join(missing)} if missing else compile_one(row, profile, path, 'original', sources)
                blocked = [d for d in deps if d not in dependency_lookup(profile, 'chain')]
                row['chain'] = {'status': 'BLOCKED', 'reason': 'Не пересобраны зависимости: '+', '.join(blocked)} if blocked else compile_one(row, profile, path, 'chain', sources)
        except Exception as error:
            row['error'] = str(error)
            row.setdefault('original', {'status': 'ERROR', 'reason': str(error)})
            row.setdefault('chain', {'status': 'BLOCKED', 'reason': 'Предыдущий этап не завершён'})
        save(); print(label, path.name, row['original']['status'], row['chain']['status'], flush=True)
    for key, entry in manifest['inputs'].items():
        if sha256(Path(entry['path'])) != entry['sha256']:
            raise ValueError('Original input changed: '+key)
    for key, entry in manifest.get('resources', {}).items():
        if sha256(Path(entry['path'])) != entry['sha256']:
            raise ValueError('Original resource changed: '+key)
    save(complete=True)


if __name__ == '__main__':
    main()
