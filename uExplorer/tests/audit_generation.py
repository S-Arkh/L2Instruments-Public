"""Read external client packages and record source-generation regressions, without exporting game code."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from backend import Core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--profile', action='append', help='Label=system-directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--compare-only', action='store_true', help='Compare the existing --output report with --baseline')
    parser.add_argument('--jobs', type=int, default=1, help='Independent profile processes (default: 1)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    profiles = []
    if args.compare_only:
        if not args.baseline:
            parser.error('--compare-only requires --baseline')
        report = json.loads(args.output.read_text(encoding='utf-8'))
    else:
        if not args.library or not args.profile:
            parser.error('--library and --profile are required for an audit')
        report = {'core_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest(), 'packages': []}
        if args.jobs > 1 and len(args.profile) > 1:
            work = args.output.resolve().parent/(args.output.stem+'-profiles')
            work.mkdir(parents=True, exist_ok=False)
            def run_profile(item):
                index, profile = item
                output = work/f'{index}.json'
                subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--library', str(args.library.resolve()),
                                '--profile', profile, '--output', str(output)], check=True)
                result = json.loads(output.read_text(encoding='utf-8'))
                if result['core_sha256'] != report['core_sha256']:
                    raise ValueError('Core binary changed during audit')
                return result['packages']
            with ThreadPoolExecutor(max_workers=min(args.jobs, len(args.profile))) as pool:
                for packages in pool.map(run_profile, enumerate(args.profile)):
                    report['packages'].extend(packages)
        else:
            core = Core(args.library.resolve())
            profiles = args.profile
    for profile in profiles:
        label, directory = profile.split('=', 1)
        files = {p.name.lower(): p for p in Path(directory).iterdir() if p.is_file()}
        for name in ('Core.u', 'Engine.u', 'NWindow.u', 'Interface.u', 'InterfaceClassic.u'):
            path = files.get(name.lower())
            if path is None:
                report['packages'].append({'profile': label, 'file': name, 'absent': True})
                continue
            summary = core.request(operation='inspect', path=str(path.resolve()))['package']
            row = dict(profile=label, file=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       version=summary['version'], licensee=summary['licensee'], modes={})
            audit = core.request(operation='audit', path=str(path.resolve()))['result']
            row['audit_failures'] = audit['failures']
            for force in (False, True):
                classes = []
                mode = 'bytecode' if force else 'auto'
                print(label, name, mode, 'starting', len(summary['classes']), 'classes', flush=True)
                for index, cls in enumerate(summary['classes'], 1):
                    try:
                        response = core.request(operation='decompile', path=str(path.resolve()),
                                                class_id=cls['id'], force_bytecode=force)
                        r = response['result']
                        functions = [{k: f[k] for k in ('name', 'decoded', 'generated') if k in f}
                                     for f in r.get('functions', []) if 'name' in f]
                        classes.append(dict(name=cls['path'], status=r['status'], issues=r.get('issues', []),
                                            functions=functions,
                                            source_sha256=hashlib.sha256(bytes.fromhex(r['raw_hex'])).hexdigest()
                                            if 'raw_hex' in r else None))
                    except RuntimeError as error:
                        classes.append(dict(name=cls['path'], status='failed', error=str(error)))
                    if index % 50 == 0:
                        print(label, name, mode, f'{index}/{len(summary["classes"])}', flush=True)
                issues = Counter(re.sub(r' at PC \d+', '', i['message']) for c in classes for i in c.get('issues', []))
                row['modes'][mode] = dict(counts=dict(Counter(c['status'] for c in classes)),
                                          issues=dict(issues), classes=classes)
                print(label, name, mode, row['modes'][mode]['counts'], flush=True)
            report['packages'].append(row)
    regressions = []
    if args.baseline:
        old = json.loads(args.baseline.read_text(encoding='utf-8'))
        by_key = {(r['profile'], r['file']): r for r in report['packages']}
        for previous in old['packages']:
            key = (previous['profile'], previous['file'])
            current = by_key.get(key, {})
            if previous.get('absent'):
                continue
            if current.get('sha256') != previous['sha256']:
                regressions.append([*key, 'input changed or missing'])
                continue
            if current['audit_failures'] > previous['audit_failures']:
                regressions.append([*key, 'structural audit'])
            for mode, before in previous['modes'].items():
                now = {c['name']: c for c in current['modes'][mode]['classes']}
                for cls in before['classes']:
                    other = now[cls['name']]
                    if (cls['status'] in ('source', 'recovered') and other['status'] != cls['status']) or (cls['status'] != 'failed' and other['status'] == 'failed'):
                        regressions.append([*key, mode, cls['name'], 'status regression'])
                    if cls.get('source_sha256') != other.get('source_sha256'):
                        regressions.append([*key, mode, cls['name'], 'ScriptText changed'])
                    funcs = {f['name']: f for f in other.get('functions', [])}
                    for f in cls.get('functions', []):
                        for field in ('decoded', 'generated'):
                            if f.get(field) is True and funcs.get(f['name'], {}).get(field) is not True:
                                regressions.append([*key, mode, f['name'], field])
    report['regressions'] = regressions
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print('Regressions:', len(regressions), flush=True)
    return bool(regressions)


if __name__ == '__main__':
    raise SystemExit(main())
