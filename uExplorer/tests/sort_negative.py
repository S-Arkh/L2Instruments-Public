"""Run the named Sort rejection fixtures in isolated SDK copies."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

CASES = {
    'arity': 'Sort comparator requires two parameters',
    'const': 'Sort requires a writable dynamic array',
    'function': 'Sort comparator must be a delegate',
    'missing': 'Sort requires a named delegate comparator',
    'out': "Call to 'Accept': bad or missing parameter 1",
    'result': "Bad or missing expression in 'Return'",
    'return_type': 'Sort comparator must return int',
    'static': 'Sort instance comparator is unavailable',
    **{name: 'Sort comparator parameters must match the array element type'
       for name in ('out_parameter', 'type', 'optional', 'coerce')},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compiler', 'launcher', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--cases', nargs='+', choices=sorted(CASES), default=list(CASES))
    args = parser.parse_args()
    tests = Path(__file__).resolve().parent
    out = args.out.resolve()
    if not out.is_relative_to(tests.parent/'local'):
        parser.error('Output must be under uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in args.cases:
        with (out/(name+'.log')).open('wb') as log:
            result = subprocess.run([sys.executable, '-B', str(tests/'compile_generation.py'),
                '--compiler', str(args.compiler.resolve()), '--launcher', str(args.launcher.resolve()),
                '--out', str(out/name), '--sources', str(tests/'array_sort_unsupported'/
                    (name+'_expression' if name in ('out', 'result') else name)),
                '--client-array-sort', '--expect-error', CASES[name]],
                stdout=log, stderr=subprocess.STDOUT, timeout=240)
        results[name] = dict(passed=result.returncode == 0, diagnostic=CASES[name])
        print(name, 'PASS' if result.returncode == 0 else 'FAIL', flush=True)
    (out/'result.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    if not all(row['passed'] for row in results.values()):
        raise AssertionError('Sort rejection suite failed')


if __name__ == '__main__':
    main()
