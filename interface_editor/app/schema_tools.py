"""Schema probing diagnostics and isolated, editable user-schema packages."""
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

from _interface_core import Document


def load_schemas(builtin, directory):
    catalog = json.loads(Path(builtin).read_text(encoding='utf-8'))
    errors = []
    for path in sorted(Path(directory).glob('*.json')):
        try:
            package = json.loads(path.read_text(encoding='utf-8'))
            records = package['records']
            versions = package['versions']
            if not isinstance(records, dict) or not versions:
                raise ValueError('Missing records/versions')
            if set(records) & set(catalog['records']):
                raise ValueError('Schema identifiers collide with installed schemas')
            for label, schema in versions:
                if not isinstance(label, str) or schema not in records:
                    raise ValueError('Invalid schema version')
            Document(json.dumps(package))
            catalog['records'].update(records)
            catalog['versions'].extend(versions)
        except Exception as error:
            errors.append(f'{path}: {error}')
    return json.dumps(catalog, ensure_ascii=False), errors


def probe(document, data, schema, label):
    result = document.probe(data, schema)
    result['label'] = label
    offsets = re.findall(r'@(\d+)|offset (\d+)', result.get('error', ''))
    offset = max((int(a or b) for a, b in offsets), default=0)
    result['offset'] = offset
    start = max(0, min(offset, len(data)) - 32)
    result['hex_start'] = start
    result['hex'] = data[start:start + 96].hex(' ')
    return result


def draft_package(schema_text, base, label):
    catalog = json.loads(schema_text)
    # Include whole namespaces: polymorphic children are selected by on-disk
    # type names. Follow cross-namespace dependencies as well as explicit types.
    prefix = 'user_' + uuid.uuid4().hex[:12] + '_'
    all_namespaces = {key.split('.')[0] for key in catalog['records']}
    namespaces = {base.split('.')[0]}
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
    while True:
        records = {key: value for key, value in catalog['records'].items() if key.split('.')[0] in namespaces}
        dependencies = {s.split('.')[0] for s in strings(records) if '.' in s} & all_namespaces
        if dependencies <= namespaces:
            break
        namespaces.update(dependencies)
    def rename(value):
        if isinstance(value, str):
            return prefix + value if value.split('.')[0] in namespaces and '.' in value else value
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {rename(key): rename(item) for key, item in value.items()}
        return value
    records = rename(copy.deepcopy(records))
    return {'format': 1, 'versions': [[label, rename(base)]], 'records': records,
            'draft': True, 'base_schema': base}


def report(filename, data, selected, results):
    return {'file': str(filename), 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'selected_schema': selected,
            'results': results}
