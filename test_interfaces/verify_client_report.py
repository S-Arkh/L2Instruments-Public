"""Bind a client test report to a manifest and the actual installed artifacts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(manifest_path, system):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    required = {'Interface.u', 'Interface.xdat', 'Core.dll', 'ExtensionL2.dll'}
    if set(manifest['files']) != required:
        raise ValueError('Manifest must identify all four client artifacts')
    files = {}
    for path in system.iterdir():
        if path.is_file():
            key = path.name.casefold()
            if key in files:
                raise ValueError('Ambiguous installed filename: '+key)
            files[key] = path
    actual = {name: digest(files[name.casefold()]) for name in sorted(required)}
    if actual != manifest['files']:
        raise ValueError('Installed artifact hashes differ from manifest')
    report = files['test.txt'].read_bytes()
    lines = report.decode('utf-8-sig').splitlines()
    if len(lines) < 4 or lines[:3] != ['Test button clicked.',
            'Profile='+manifest['profile'], 'Build='+manifest['build_identity']]:
        raise ValueError('Report profile/build header differs from manifest')
    counts = Counter()
    cases = []
    for line in lines[3:-1]:
        if line.startswith('RUN | ') and len(line) > 6:
            continue
        match = re.fullmatch(r'(PASS|FAIL|SKIP) \| ([^|]+) \| (.+)', line)
        if not match:
            raise ValueError('Malformed test result line')
        status, name, details = match.groups()
        if any(case['name'] == name.strip() for case in cases):
            raise ValueError('Duplicate test result: '+name.strip())
        if status != 'SKIP' and not re.fullmatch(r'actual=.* \| expected=.*', details):
            raise ValueError('Missing actual/expected values')
        counts[status] += 1
        cases.append(dict(name=name.strip(), status=status, details=details))
    total = re.fullmatch(r'TOTAL \| PASS=(\d+) \| FAIL=(\d+) \| SKIP=(\d+)', lines[-1])
    if not total or tuple(map(int, total.groups())) != tuple(counts[s] for s in ('PASS', 'FAIL', 'SKIP')):
        raise ValueError('Missing or inconsistent final totals')
    if not cases or counts['PASS']+counts['FAIL'] == 0:
        raise ValueError('No executed checks')
    return dict(schema=1, profile=manifest['profile'], build_identity=manifest['build_identity'],
                manifest_sha256=digest(manifest_path), report_sha256=hashlib.sha256(report).hexdigest(),
                installed_files=actual, totals={s: counts[s] for s in ('PASS', 'FAIL', 'SKIP')},
                cases=cases, artifact_binding_verified=True, tests_passed=counts['FAIL'] == 0,
                scope='on-disk artifact and report consistency; not loaded-module attestation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(args.system.resolve()):
        parser.error('Output must be new and outside the installed System directory')
    result = verify(args.manifest, args.system)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('profile', 'totals', 'artifact_binding_verified', 'tests_passed')}))
    if not result['tests_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
