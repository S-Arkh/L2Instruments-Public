"""Annotate the optional HF/Gracia CRC trailer and verified sample protocols."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'ct24.XDAT': 'Gracia Epilogue (protocol 152)',
          'ct26.XDAT': 'High Five (protocol 268)'}


def update(catalog):
    for version in catalog['versions']:
        if version[1] in LABELS:
            version[0] = LABELS[version[1]]
    for schema in LABELS:
        tail = next(op for op in catalog['records'][schema]['ops'] if op['op'] == 'tail')
        tail['layout'] = 'legacy-crc32'
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'schemas/schemas.json')
    args = parser.parse_args()
    catalog = update(json.loads(args.catalog.read_text(encoding='utf-8')))
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


if __name__ == '__main__':
    main()
