"""Audit external client packages; write path-free, reproducible evidence."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--decoder', type=Path, required=True)
    parser.add_argument('--profile', action='append', required=True,
                        help='Anonymous label=system-directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lib = ctypes.CDLL(str(args.library.resolve()))
    lib.ue_request.argtypes = [ctypes.c_char_p]
    lib.ue_request.restype = ctypes.c_void_p
    lib.ue_free.argtypes = [ctypes.c_void_p]
    lib.ue_free.restype = None
    rows = []
    for profile in args.profile:
        label, directory = profile.split('=', 1)
        for name in ('Core.u', 'Engine.u', 'NWindow.u', 'Interface.u', 'InterfaceClassic.u'):
            path = Path(directory) / name
            raw = path.read_bytes()
            ptr = lib.ue_request(json.dumps({'operation': 'audit', 'path': str(path.resolve())}).encode())
            try:
                result = json.loads(ctypes.string_at(ptr))
            finally:
                lib.ue_free(ptr)
            if not result['ok']:
                raise RuntimeError(f'{label}/{name}: package audit could not run')
            if not raw.startswith('Lineage2Ver111'.encode('utf-16le')):
                raise ValueError(f'{label}/{name}: expected wrapper 111')
            decoded = bytes(b ^ 0xac for b in raw[28:])
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'decoded.u'
                process = subprocess.run([str(args.decoder.resolve()), '-c', 'decode', '-t',
                                          '-o', str(output), str(path.resolve())],
                                         capture_output=True)
                if process.returncode or not output.is_file():
                    raise RuntimeError(f'{label}/{name}: oracle failed')
                match = output.read_bytes() == decoded
            rows.append({'profile': label, 'file': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'decoded_sha256': hashlib.sha256(decoded).hexdigest(),
                         'wrapper': 111, 'oracle_match_without_footer': match,
                         'audit': result['result']})
            print(label, name, 'failures', result['result']['failures'], 'oracle_match', match)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'format': 1, 'packages': rows}, indent=2) + '\n', encoding='utf-8')
    return int(any(not row['oracle_match_without_footer'] or row['audit']['failures'] for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
