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
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Schema package too large')
            package = json.loads(path.read_text(encoding='utf-8'))
            validate_package(package)
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
            for _, schema in versions:
                catalog.setdefault('package_info', {})[schema] = package_info(package)
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
    # Shareable reports deliberately exclude paths, binary excerpts and values.
    safe = []
    for r in results:
        item = {key: r[key] for key in ('schema', 'compatible', 'tail_bytes', 'offset') if key in r}
        if r.get('failure'):
            item['offset'] = r['failure']['offset']
        if r.get('first_anomaly'):
            item['first_anomaly_offset'] = r['first_anomaly']['offset']
        safe.append(item)
    return {'format': 2, 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'selected_schema': selected,
            'results': safe}


def validate_package(package):
    """Validate the declarative language before native initialization/recursion."""
    if not isinstance(package, dict) or package.get('format') != 1 or not isinstance(package.get('records'), dict):
        raise ValueError('Unsupported schema package')
    records = package['records']
    if not records or len(records) > 10000:
        raise ValueError('Invalid record count')
    identifier = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+$')
    kinds = {'int', 'float', 'string', 'compact', 'byte', 'bool', 'enum', 'color', 'rgba', 'list', 'object'}
    edges = {}
    for name, record in records.items():
        if not identifier.fullmatch(name) or not isinstance(record, dict):
            raise ValueError('Invalid record identifier')
        base = record.get('base')
        if base is not None and base not in records:
            raise ValueError(f'Missing base: {name}')
        edges[name] = [base] if base else []

        def walk(ops, depth=0):
            if depth > 64 or not isinstance(ops, list) or len(ops) > 10000:
                raise ValueError('Invalid operations/depth')
            for op in ops:
                if op.get('op') == 'if':
                    if not re.fullmatch(r'\s*!?\w+\s*(?:(?:==|!=|>=|<=|>|<)\s*-?\d+)?\s*', op.get('condition', '')):
                        raise ValueError('Invalid condition')
                    walk(op['yes'], depth + 1)
                    walk(op['no'], depth + 1)
                elif op.get('op') == 'tail':
                    if op.get('layout', '') not in ('', 'legacy-crc32'):
                        raise ValueError('Unknown tail layout')
                    continue
                elif op.get('op') == 'field':
                    kind = op.get('kind')
                    if kind not in kinds or not re.fullmatch(r'\w+', op.get('name', '')) or op.get('name') == '_tail' or 'default' not in op:
                        raise ValueError(f'Invalid field in {name}')
                    if kind == 'byte' and (type(op['default']) is not int or not 0 <= op['default'] <= 255):
                        raise ValueError('Byte default must be an integer between 0 and 255')
                    if kind in ('object', 'list'):
                        if op.get('type') not in records:
                            raise ValueError(f'Missing field type in {name}')
                        if kind == 'object' and not op.get('poly', False):
                            edges[name].append(op['type'])
                        if kind == 'list' and op.get('count', '') not in ('', 'int', 'compact'):
                            raise ValueError('Invalid list count encoding')
                else:
                    raise ValueError('Unknown schema operation')
        walk(record.get('ops'))
    visiting, visited = set(), set()

    def visit(name, depth=0):
        if name in visiting or depth >= 128:
            raise ValueError('Recursive base/object initialization')
        if name in visited:
            return
        visiting.add(name)
        for child in edges[name]:
            visit(child, depth + 1)
        visiting.remove(name)
        visited.add(name)
    for name in records:
        visit(name)
    # initialize() shares one Field per name, including inactive branches. A
    # scalar/list collision would otherwise leave a null child in native parsing.
    signatures = {}
    def fields(name):
        if name in signatures:
            return signatures[name]
        record = records[name]
        found = dict(fields(record['base'])) if record['base'] else {}
        conditions = []
        def collect(ops):
            for op in ops:
                if op['op'] == 'if':
                    conditions.append(re.match(r'\s*!?(\w+)', op['condition']).group(1))
                    collect(op['yes'])
                    collect(op['no'])
                elif op['op'] == 'field':
                    kind = op['kind']
                    signature = (kind, op.get('type') if kind in ('list', 'object') else None,
                                 op.get('poly', False), op.get('count', 'int'))
                    if op['name'] in found and found[op['name']] != signature:
                        raise ValueError(f'Conflicting field definitions: {name}.{op["name"]}')
                    found[op['name']] = signature
        collect(record['ops'])
        for field in conditions:
            if field not in found or found[field][0] in ('string', 'list', 'object'):
                raise ValueError(f'Invalid condition field: {name}.{field}')
        signatures[name] = found
        return found
    for name in records:
        fields(name)
    versions = package.get('versions')
    if not isinstance(versions, list) or not versions:
        raise ValueError('Missing versions')
    for entry in versions:
        if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str) or entry[1] not in records:
            raise ValueError('Invalid version')
    return package


def export_package(schema_text, schema):
    """Self-contained package, preserving identifiers and omitting local metadata."""
    catalog = json.loads(schema_text)
    package = draft_package(schema_text, schema, next(label for label, key in catalog['versions'] if key == schema))
    prefix = package['versions'][0][1][:-len(schema)]
    def restore(value):
        if isinstance(value, str):
            return value[len(prefix):] if value.startswith(prefix) else value
        if isinstance(value, list):
            return [restore(v) for v in value]
        if isinstance(value, dict):
            return {restore(k): restore(v) for k, v in value.items()}
        return value
    result = {'format': 1, 'versions': restore(package['versions']), 'records': restore(package['records'])}
    result.update(package_info(catalog.get('package_info', {}).get(schema, catalog)))
    return validate_package(result)


def package_info(package):
    """Only portable, structured provenance; no free-form machine information."""
    revision = package.get('revision', 1)
    if not isinstance(revision, int) or not 1 <= revision <= 1000000:
        revision = 1
    result = {'revision': revision, 'status': 'draft'}
    evidence = []
    for item in package.get('validation', []) if isinstance(package.get('validation', []), list) else []:
        if (isinstance(item, dict) and re.fullmatch('[a-f0-9]{64}', str(item.get('sha256', '')))
                and isinstance(item.get('size'), int) and 0 <= item['size'] <= 256 * 1024 * 1024
                and isinstance(item.get('tail_bytes'), int) and 0 <= item['tail_bytes'] <= item['size']
                and isinstance(item.get('roundtrip'), bool)):
            evidence.append({key: item[key] for key in ('sha256', 'size', 'roundtrip', 'tail_bytes')})
    if evidence:
        result['validation'] = evidence
        if all(item['roundtrip'] and not item['tail_bytes'] for item in evidence):
            result['status'] = 'sample-tested'
    return result


def validation_info(samples, results):
    return package_info({'validation': [
        {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
         'roundtrip': result['compatible'], 'tail_bytes': result['tail_bytes']}
        for data, result in zip(samples, results)]})


def import_package(source, directory, catalog_text):
    source = Path(source)
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Schema package too large')
    package = validate_package(json.loads(source.read_text(encoding='utf-8')))
    catalog = json.loads(catalog_text)
    if set(package['records']) & set(catalog['records']):
        raise ValueError('Schema identifiers collide with installed schemas')
    # Whitelist portable content; do not propagate arbitrary metadata or paths.
    portable = {key: package[key] for key in ('format', 'versions', 'records')}
    portable.update(package_info(package))
    encoded = json.dumps(portable, ensure_ascii=False, indent=2)
    target = Path(directory) / ('schema_' + hashlib.sha256(encoded.encode()).hexdigest()[:16] + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as output:
        output.write(encoded)
    return target
