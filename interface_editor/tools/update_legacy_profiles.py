"""Annotate the optional HF/Gracia CRC trailer and verified sample protocols."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from schema_catalog import BUILTIN_INDEX, load_catalog, save_catalog
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
    parser.add_argument('--catalog', type=Path, default=BUILTIN_INDEX)
    args = parser.parse_args()
    catalog = update(load_catalog(args.catalog))
    save_catalog(args.catalog, catalog)


if __name__ == '__main__':
    main()
