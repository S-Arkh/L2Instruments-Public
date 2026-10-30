"""Prepare separate client-test DATs; never modify the supplied input file."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import SysStrings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'examples/sysstring_test')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Choose a new output directory')
    args.out.mkdir(parents=True)
    table = SysStrings(); table.load(str(args.source))
    original = {r['id']: r['text'] for r in table.rows()}
    unchanged = args.out / 'sysstring-e-roundtrip.dat'
    table.save(str(unchanged))
    check = SysStrings(); check.load(str(unchanged))
    assert {r['id']: r['text'] for r in check.rows()} == original
    identifier = table.next_id()
    table.add(identifier, 'Interface Editor Test')
    output = args.out / 'sysstring-e.dat'
    table.save(str(output))
    check.load(str(output))
    actual = {r['id']: r['text'] for r in check.rows()}
    assert actual.keys() - original.keys() == {identifier}
    assert all(actual[key] == value for key, value in original.items())
    report = dict(source=str(args.source), source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                  added_id=identifier, text=actual[identifier], original_rows=len(original), result_rows=len(actual),
                  profile=check.summary(), game_tested=False,
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (unchanged, output)})
    (args.out / 'verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__': main()
