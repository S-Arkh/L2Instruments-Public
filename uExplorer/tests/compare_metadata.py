"""Compare package metadata with path-free, hash-bound evidence.

Export order and raw serialized property bytes are excluded: reference indices
may move. Symbolic identity spelling and every other probe field are compared.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def inventory(probe, package):
    rows = json.loads(subprocess.check_output(
        [str(probe.resolve()), str(package.resolve())], encoding='utf-8'))
    result = {}
    for row in rows:
        category = next(key for key in ('class', 'state', 'property') if key in row)
        key = (category, row[category].lower())
        if key in result:
            raise ValueError('Duplicate metadata identity: ' + str(key))
        result[key] = {k: v for k, v in row.items() if k != 'raw'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('probe', 'original', 'compiled', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    before = inventory(args.probe, args.original)
    after = inventory(args.probe, args.compiled)
    differences = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a == b:
            continue
        fields = {}
        if a is not None and b is not None:
            for field in sorted(a.keys() | b.keys()):
                if a.get(field) != b.get(field):
                    change = dict(original=a.get(field), compiled=b.get(field))
                    if field.endswith('flags') and isinstance(a.get(field), int) and isinstance(b.get(field), int):
                        change['added_bits'] = hex(b[field] & ~a[field])
                        change['removed_bits'] = hex(a[field] & ~b[field])
                    fields[field] = change
        differences.append(dict(category=key[0], identity=key[1],
                                missing_original=a is None, missing_compiled=b is None,
                                fields=fields))
    report = dict(original_sha256=hashlib.sha256(args.original.read_bytes()).hexdigest(),
                  compiled_sha256=hashlib.sha256(args.compiled.read_bytes()).hexdigest(),
                  probe_sha256=hashlib.sha256(args.probe.read_bytes()).hexdigest(),
                  original_rows=len(before), compiled_rows=len(after),
                  excluded_fields=['raw'], export_order_compared=False,
                  metadata_equal=not differences, runtime_tested=False,
                  differences=differences)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(f'{len(before)} original / {len(after)} compiled rows; '
          f'{len(differences)} differing identities')


if __name__ == '__main__':
    main()
