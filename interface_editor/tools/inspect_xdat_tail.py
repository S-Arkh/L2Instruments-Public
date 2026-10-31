"""Inspect bytes left after an XDAT schema, without exporting client payloads or paths."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document


def inspect(data, schema_text, schema):
    result = Document(schema_text).diagnose(data, schema, 1)
    size = result['tail_bytes']
    report = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
              'schema': schema, 'compatible': result['compatible'],
              'tail_bytes': size, 'tail_offset': len(data) - size if result['compatible'] else None}
    if not result['compatible'] or size != 20:
        return report
    tail = data[-20:]
    words = struct.unpack('<5I', tail)
    crc = zlib.crc32(data[:-20])
    shape = words[0] == 0 and words[4] == 0
    report.update(tail_sha256=hashlib.sha256(tail).hexdigest(),
                  words_le=list(words), payload_crc32=crc,
                  word12_matches_payload_crc32=words[3] == crc,
                  interpretation='legacy-crc32-envelope' if shape else 'unrecognized-five-words',
                  checksum_status=('match' if words[3] == crc else 'mismatch') if shape else 'unclassified',
                  unknown_word_offsets=[0, 4, 8, 16], preservation='verbatim')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, action='append', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'schemas/schemas.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    text = args.catalog.read_text(encoding='utf-8')
    reports = [inspect(p.read_bytes(), text, args.schema) for p in args.sample]
    args.output.write_text(json.dumps({'format': 1, 'samples': reports}, indent=2) + '\n', encoding='utf-8')
    return 0 if all(r['compatible'] for r in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
