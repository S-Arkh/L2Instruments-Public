"""Inspect initialized client PtrProperty exports in an isolated DLL copy.

Absence is a profile capability boundary, not proof about every legacy client.
The probe never invokes a property method or substitutes an integer property.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SYMBOLS = (
    '?StaticClass@UPtrProperty@@SAPAVUClass@@XZ',
    '?ExportCppItem@UPtrProperty@@UBEXAAVFOutputDevice@@H@Z',
    '?SerializeItem@UPtrProperty@@UBEXAAVFArchive@@PAXH@Z',
    '?Link@UPtrProperty@@UAEXAAVFArchive@@PAVUProperty@@@Z',
)
CONTROL = '?StaticClass@UIntProperty@@SAPAVUClass@@XZ'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'probe', 'out'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--expect-exports', required=True, choices=('present', 'absent'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local') or out.is_relative_to(args.system.resolve()):
        parser.error('Output must be a new isolated directory beneath uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    system = out/'System'
    system.mkdir()
    hashes = {}
    for source in args.system.iterdir():
        if source.is_file() and source.suffix.lower() == '.dll':
            shutil.copy2(source, system/source.name)
            hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    core = next(p for p in system.iterdir() if p.name.casefold() == 'core.dll')
    probe = system/'ptrproperty_probe.exe'
    shutil.copy2(args.probe, probe)
    result = subprocess.run([str(probe), '--load', str(core), str(system)],
                            cwd=system, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (out/'probe.log').write_bytes(result.stdout)
    lines = result.stdout.decode('ascii', errors='replace').splitlines()
    exports = {}
    for symbol in (*SYMBOLS, CONTROL):
        rows = [line[len(symbol)+2:] for line in lines if line.startswith(symbol+': ')]
        exports[symbol] = rows[0] if len(rows) == 1 else 'missing-observation'
    def readable(value):
        return len(value) == 32 and all(c in '0123456789abcdef' for c in value)
    expected = (all(readable(exports[s]) for s in SYMBOLS) if args.expect_exports == 'present'
                else all(exports[s] == 'absent' for s in SYMBOLS))
    passed = result.returncode == 0 and readable(exports[CONTROL]) and expected
    report = dict(passed=passed, exit=result.returncode, expected=args.expect_exports,
                  exports=exports, dll_sha256=hashes,
                  probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                  scope='initialized DLL export availability; not client gameplay or network replication')
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS' if passed else 'FAIL', args.expect_exports, 'PtrProperty exports; UIntProperty control')
    if not passed:
        raise AssertionError('Client pointer contract differs from expectation')


if __name__ == '__main__':
    main()
