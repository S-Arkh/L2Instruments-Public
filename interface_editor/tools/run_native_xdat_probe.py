"""Run verified x86 native XDAT reader RVAs on working copies (Windows only)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--sample', type=Path, action='append', required=True)
    parser.add_argument('--constructor', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--serializer', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--stack-ctor', action='store_true')
    parser.add_argument('--timeout', type=int, default=25)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error('timeout must be between 1 and 120 seconds')
    module = args.module.resolve()
    cases = []
    for sample in args.sample:
        data = sample.read_bytes()
        row = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        command = [str(args.probe.resolve()), str(module), str(sample.resolve()),
                   hex(args.constructor), hex(args.serializer), str(int(args.stack_ctor))]
        try:
            result = subprocess.run(command, cwd=module.parent, capture_output=True, timeout=args.timeout)
            row['returncode'] = result.returncode
            match = re.search(rb'cursor=(\d+) bytes=(\d+) calls=(\d+) result=(\d+)', result.stdout)
            if match:
                cursor, size, calls, status = map(int, match.groups())
                row.update(cursor=cursor, archive_calls=calls,
                           native_success=result.returncode == 0 and status == 0 and size == len(data),
                           unconsumed_bytes=size - cursor)
            else:
                row['native_success'] = False
        except subprocess.TimeoutExpired:
            row.update(native_success=False, timed_out=True)
        cases.append(row)
    report = {'format': 1, 'scope': 'isolated-native-serializer', 'full_client_ui_validated': False,
              'module_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
              'constructor_rva': hex(args.constructor), 'serializer_rva': hex(args.serializer),
              'stack_constructor': args.stack_ctor, 'cases': cases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if all(row['native_success'] for row in cases) else 1


if __name__ == '__main__':
    raise SystemExit(main())
