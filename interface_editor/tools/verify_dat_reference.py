"""Developer-only interoperability check against a separately supplied l2encdec.

The application never invokes this tool. All reference operations use a fresh
temporary directory; the supplied client DAT is only read.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import SysStrings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reference-exe', type=Path, required=True)
    parser.add_argument('--wine', type=Path)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/dat-reference.json')
    args = parser.parse_args()
    source = SysStrings(); source.load(str(args.source))
    payload = source.payload()
    results = []
    def winpath(path):
        return str(path) if os.name == 'nt' else 'Z:' + str(path).replace('/', '\\')
    def run(arguments):
        cmd = ([str(args.wine.resolve()), winpath(args.reference_exe.resolve())] if args.wine else [str(args.reference_exe.resolve())])
        cmd += [winpath(a) if isinstance(a, Path) else a for a in arguments]
        with tempfile.TemporaryFile() as log:
            result = subprocess.run(cmd, cwd=args.reference_exe.parent, stdout=log, stderr=subprocess.STDOUT, timeout=60)
            log.seek(0)
            if result.returncode:
                raise RuntimeError(log.read().decode(errors='replace'))
    with tempfile.TemporaryDirectory(prefix='interface-dat-check-') as temp:
        root = Path(temp)
        plain = root / 'plain'; plain.mkdir()
        original = plain / 'sysstring-e.dat'; original.write_bytes(payload)
        for version in (111, 120, 121, 211, 212, 411, 412, 413, 414):
            folder = root / str(version); folder.mkdir()
            ours = folder / 'sysstring-e.dat'
            ours.write_bytes(source.encoded(ours.name, version, 'l2encdec' if version >= 411 else 'standard'))
            decoded = folder / 'decoded.bin'
            run(['-d', ours, decoded])
            readback = decoded.read_bytes()
            assert readback[:len(payload)] == payload and not any(readback[len(payload):]), version
            reference = folder / 'encoded'; reference.mkdir()
            reference_file = reference / 'sysstring-e.dat'
            run(['-e', str(version), original, reference_file])
            check = SysStrings()
            try:
                check.load(str(reference_file))
            except Exception:
                data = reference_file.read_bytes()
                print('Reference details:', version, len(data), data[-28:].hex(), flush=True)
                raise
            assert check.payload() == payload, version
            results.append(dict(version=version, native_to_reference=True, reference_to_native=True))
            print('PASS', version, flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(args.reference_exe.read_bytes()).hexdigest(), results=results), indent=2), encoding='utf-8')


if __name__ == '__main__': main()
