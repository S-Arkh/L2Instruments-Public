"""Execute independently specified semantic cases before and after source recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compiler', 'launcher', 'probe', 'original', 'recompiled', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local'):
        parser.error('Output must be a new directory beneath uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    for label, package in (('original', args.original), ('recompiled', args.recompiled)):
        system = out/label
        system.mkdir()
        for source in args.compiler.iterdir():
            if source.is_file() and source.suffix.lower() in ('.exe', '.dll', '.u', '.int', '.ini'):
                shutil.copy2(source, system/source.name)
        shutil.copy2(args.launcher, system/'ucc64.exe')
        shutil.copy2(args.probe, system/'Ucc64Bridge.dll')
        shutil.copy2(package, system/'Generation.u')
        result = subprocess.run([str(system/'ucc64.exe'), '--system', str(system), 'help', '-NoBind'],
                                cwd=system, env=dict(os.environ, UCC_PTR_PROBE_MODE='semantics'),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        (out/(label+'.log')).write_bytes(result.stdout)
        passed = result.returncode == 0 and b'script-semantics=1 cases=10' in result.stdout
        results[label] = dict(exit=result.returncode, passed=passed,
                             sha256=hashlib.sha256(package.read_bytes()).hexdigest())
        print(label, result.stdout.decode(errors='replace'))
    results['probe_sha256'] = hashlib.sha256(args.probe.read_bytes()).hexdigest()
    (out/'result.json').write_text(json.dumps(results, indent=2)+'\n')
    if not all(results[label]['passed'] for label in ('original', 'recompiled')):
        raise AssertionError('Original or recompiled semantic cases failed')


if __name__ == '__main__':
    main()
