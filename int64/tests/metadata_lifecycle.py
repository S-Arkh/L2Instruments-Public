"""Capture serialized and SDK-loaded metadata across fresh-process saves."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--metadata-probe', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--objects', required=True, help='Semicolon-separated fully qualified object names')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--lifecycle', action='store_true', help='Run the fixed synthetic value/owner copy controls')
    parser.add_argument('--context', choices=('editor', 'client', 'server'), default='editor')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local'):
        parser.error('Output must be a new directory under uExplorer/local')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    expected = {'Core.dll': '5bff274734cae994353a8c60f4bfe1087dbdd9aa3883c7b2a7eff6ea2f51dc7e',
                'Editor.dll': 'd64995c1282956c6e9d67dd70715a69b5101331aa727a2d44b03e25fd7f2cd2e',
                'UCC.exe': 'c68ba1ce0eab03af23b04dc1c991c3f1cc047a8a2076c6850e3071892806fb65'}
    for filename, value in expected.items():
        if digest(args.compiler/filename) != value:
            raise ValueError('Unsupported SDK: '+filename)
    out.mkdir(parents=True, exist_ok=False)
    system = out/'System'
    system.mkdir()
    for source in args.compiler.iterdir():
        if source.is_file() and source.suffix.lower() in ('.exe', '.dll', '.int', '.u', '.ini'):
            shutil.copy2(source, system/source.name)
    shutil.copy2(args.tools/'ucc64.exe', system/'ucc64.exe')
    shutil.copy2(args.tools/'ptr_lifecycle_probe.dll', system/'Ucc64Bridge.dll')
    package = system/args.package.name
    raw = args.package.read_bytes()
    envelope = 'plain'
    for name in ('Lineage2Ver111', 'GamekitData111'):
        marker = name.encode('utf-16le')
        if raw.startswith(marker):
            raw = bytes(value ^ 0xac for value in raw[len(marker):])
            envelope = name
            break
    if raw[:4] != bytes.fromhex('c1832a9e'):
        raise ValueError('Unsupported package envelope')
    package.write_bytes(raw)
    evidence = {'modules': expected, 'probe': digest(system/'Ucc64Bridge.dll'),
                'launcher': digest(system/'ucc64.exe'), 'metadata_probe': digest(args.metadata_probe),
                'source': digest(args.package), 'envelope': envelope,
                'staged_files': {p.name: digest(p) for p in sorted(system.iterdir()) if p.is_file()},
                'input': digest(package), 'passes': []}
    (out/'inputs.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    for index in range(3):
        serialized = subprocess.check_output([str(args.metadata_probe.resolve()), str(package)], text=True)
        rows = json.loads(serialized)
        (out/f'serialized-{index}.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        shutil.copy2(package, out/f'pass-{index}.u')
        env = dict(os.environ, UCC_PTR_PROBE_MODE='metadata', UCC_METADATA_PACKAGE=package.name,
                   UCC_METADATA_OBJECTS=args.objects, UCC_METADATA_SAVE='Saved.u')
        env.pop('UCC_METADATA_LIFECYCLE', None)
        env['UCC_METADATA_CONTEXT'] = args.context
        if args.lifecycle:
            env['UCC_METADATA_LIFECYCLE'] = '1'
        result = subprocess.run([str(system/'ucc64.exe'), '--system', str(system), 'help', '-NoBind'],
                                cwd=system, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (out/f'pass-{index}.log').write_bytes(result.stdout)
        text = result.stdout.decode(errors='replace')
        print(f'pass={index} exit={result.returncode} log=pass-{index}.log')
        if result.returncode or 'metadata-complete=1' not in text:
            raise AssertionError(f'Native pass {index} failed: {result.returncode}')
        records = [dict(stage=m[0], object=m[1], object_flags=int(m[2], 16), kind=m[3], flags=int(m[4], 16))
                   for m in re.findall(r'metadata stage=([\w-]+) object=(\S+) object_flags=([0-9a-f]+) kind=(\w+) flags=([0-9a-f]+)', text)]
        if len(records) != 2*len(args.objects.split(';')):
            raise AssertionError('Incomplete snapshots')
        evidence['passes'].append({'input': digest(package), 'saved': digest(system/'Saved.u'), 'records': records})
        shutil.copy2(system/'Saved.u', package)
        (system/'Saved.u').unlink()
    (out/'result.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('PASS: three fresh-process metadata captures (differences require interpretation)')


if __name__ == '__main__':
    main()
