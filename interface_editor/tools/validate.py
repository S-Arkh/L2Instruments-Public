"""Read-only validation and timing of supplied fixtures and a client XDAT."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('INTERFACE_MODULE_DIR', str(ROOT / 'app')))
from _interface_core import Document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path)
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'tests/fixtures')
    parser.add_argument('--report', type=Path, default=ROOT / 'build/validation.json')
    parser.add_argument('--json-roundtrip', action='store_true')
    parser.add_argument('--client-only', action='store_true')
    args = parser.parse_args()
    schema_text = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    specs = json.loads(schema_text)
    fixtures = [] if args.client_only else json.loads((args.fixtures / 'manifest.json').read_text())
    if args.client_only and not args.client:
        parser.error('--client-only requires --client')
    cases = [(args.fixtures / f['file'], f['schema']) for f in fixtures]
    if args.client:
        cases.append((args.client, 'ct26.XDAT'))
    results = []
    for file, schema in cases:
        original = file.read_bytes()
        doc = Document(schema_text)
        start = time.perf_counter()
        doc.load_bytes(original, schema)
        load_seconds = time.perf_counter() - start
        start = time.perf_counter()
        assert doc.serialize() == original, file
        write_seconds = time.perf_counter() - start
        timings = []
        for i in range(20):
            start = time.perf_counter()
            result = doc.search('btnCredit' if i % 2 else 'Login')
            timings.append((time.perf_counter() - start) * 1000)
        row = dict(file=str(file), schema=schema, sha256=hashlib.sha256(original).hexdigest(),
                   bytes=len(original), nodes=doc.summary()['nodes'], roundtrip=True,
                   load_seconds=round(load_seconds, 4), write_seconds=round(write_seconds, 4),
                   search_median_ms=round(statistics.median(timings), 3), search_max_ms=round(max(timings), 3))
        if args.json_roundtrip:
            text = doc.to_json()
            restored = Document(schema_text)
            restored.from_json(text)
            assert restored.serialize() == original, file
            row['json_roundtrip'] = True
            row['json_utf8_bytes'] = len(text.encode('utf-8'))
        results.append(row)
        print(f"PASS {file.name}: {row['nodes']} nodes, load {load_seconds:.3f}s, search median {row['search_median_ms']}ms", flush=True)
    tested = {row['schema'] for row in results}
    report = dict(platform=platform.platform(), python=sys.version, files=results,
                  versions=[dict(label=label, schema=schema, fixture_tested=schema in tested) for label, schema in specs['versions']])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__': main()
