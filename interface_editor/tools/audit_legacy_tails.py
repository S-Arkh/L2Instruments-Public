"""Compare legacy XDAT trailers across external files; export hashes, never paths."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from inspect_xdat_tail import ROOT, inspect


def audit(samples, catalog_text):
    rows = []
    groups = defaultdict(set)
    for schema, data in samples:
        row = inspect(data, catalog_text, schema)
        if row['compatible'] and row['tail_bytes'] == 20:
            row['payload_sha256'] = hashlib.sha256(data[:-20]).hexdigest()
            groups[row['tail_sha256']].add(row['payload_sha256'])
        rows.append(row)
    return {'format': 1, 'schema_sha256': hashlib.sha256(catalog_text.encode()).hexdigest(),
            'samples': rows,
            'crc32_matches': sum(row.get('checksum_status') == 'match' for row in rows),
            'crc32_mismatches': sum(row.get('checksum_status') == 'mismatch' for row in rows),
            'reused_tails': [{'tail_sha256': tail, 'distinct_payload_sha256': sorted(payloads)}
                             for tail, payloads in sorted(groups.items()) if len(payloads) > 1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'schemas/schemas.json')
    parser.add_argument('--fixtures', type=Path, help='External directory for the bundled legacy fixture manifest')
    parser.add_argument('--sample', action='append', default=[], metavar='SCHEMA=FILE')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    samples = []
    if args.fixtures:
        manifest = json.loads((ROOT / 'tests/integration/fixture-manifest.json').read_text())
        for spec in manifest:
            if not spec['schema'].startswith('ct'):
                continue
            data = (args.fixtures / spec['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != spec['sha256']:
                parser.error('External fixture hash differs from manifest')
            samples.append((spec['schema'], data))
    for sample in args.sample:
        schema, separator, filename = sample.partition('=')
        if not separator:
            parser.error('--sample requires SCHEMA=FILE')
        samples.append((schema, Path(filename).read_bytes()))
    if not samples:
        parser.error('Provide --fixtures or --sample')
    report = audit(samples, args.catalog.read_text(encoding='utf-8'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return int(not all(row['compatible'] for row in report['samples']))


if __name__ == '__main__':
    raise SystemExit(main())
