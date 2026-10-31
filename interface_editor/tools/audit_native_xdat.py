"""Audit a local draft against external samples; emit hashes, never payloads or paths."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from _interface_core import Document
from schema_tools import validate_package


def audit(package, data, schema=None, json_roundtrip=False):
    validate_package(package)
    schema = schema or package['versions'][0][1]
    doc = Document(json.dumps(package))
    diagnostic = doc.diagnose(data, schema, 1)
    result = {
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'compatible': diagnostic['compatible'], 'cursor': diagnostic['cursor'],
        'tail_bytes': diagnostic['tail_bytes'],
        'anomaly_present': diagnostic['first_anomaly'] is not None,
        'roundtrip_identical': False, 'edit_reload': False, 'undo_identical': False,
    }
    if not diagnostic['compatible']:
        return result
    doc.load_bytes(data, schema)
    result['roundtrip_identical'] = doc.serialize() == data
    windows = next(n for n in doc.children() if n['name'] == 'windows')
    window = doc.children(windows['id'])[0]['id']
    prop = next(p for p in doc.properties(window) if p['name'] == 'name')
    edited_name = prop['value'] + '_audit'
    doc.set(window, 'name', edited_name)
    edited = doc.serialize()
    reread = Document(json.dumps(package))
    reread.load_bytes(edited, schema)
    new_windows = next(n for n in reread.children() if n['name'] == 'windows')
    new_window = reread.children(new_windows['id'])[0]['id']
    new_name = next(p['value'] for p in reread.properties(new_window) if p['name'] == 'name')
    result['edit_reload'] = edited != data and new_name == edited_name and reread.serialize() == edited
    doc.undo()
    result['undo_identical'] = doc.serialize() == data
    if json_roundtrip:
        reread.from_json(doc.to_json())
        result['json_roundtrip_identical'] = reread.serialize() == data
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--schema', help='Root identifier when auditing a multi-profile catalog')
    parser.add_argument('--json-roundtrip', action='store_true')
    parser.add_argument('--sample', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = json.loads(args.package.read_text(encoding='utf-8'))
    results = [audit(package, p.read_bytes(), args.schema, args.json_roundtrip) for p in args.sample]
    report = {'format': 1, 'status': 'research',
              'schema': args.schema or package['versions'][0][1],
              'schema_sha256': hashlib.sha256(args.package.read_bytes()).hexdigest(),
              'client_loading_validated': False, 'samples': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    checks = ['compatible', 'roundtrip_identical', 'edit_reload', 'undo_identical']
    if args.json_roundtrip:
        checks.append('json_roundtrip_identical')
    return 0 if all(all(r.get(k, False) for k in checks) for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
