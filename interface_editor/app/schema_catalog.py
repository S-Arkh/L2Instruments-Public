"""Load profile files into the catalog consumed by the native core.

Standalone JSON catalogs remain supported for external research tools.
"""
import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock


BUILTIN_INDEX = Path(__file__).resolve().parents[1] / 'schemas/index.json'


class SchemaRepository:
    """Index-only discovery and a bounded LRU of self-contained profile catalogs."""

    def __init__(self, index=BUILTIN_INDEX, directory=None, cache_size=3):
        self.index = Path(index)
        self.directory = Path(directory) if directory is not None else None
        self.cache_size = max(1, cache_size)
        self._cache = OrderedDict()
        self._lock = RLock()
        self._signature = None
        self._profiles = {}
        self.refresh()

    @staticmethod
    def _stamp(path):
        try:
            stat = path.stat()
            return str(path), stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return str(path), None, None

    def _files_signature(self):
        users = sorted(self.directory.glob('*.json')) if self.directory else []
        return tuple(self._stamp(p) for p in [self.index, *dict.fromkeys(self._profiles.values()), *users])

    def refresh(self):
        with self._lock:
            if self._signature is not None and self._files_signature() == self._signature:
                return
            index = json.loads(self.index.read_text(encoding='utf-8'))
            profiles = {}
            if 'profiles' in index:
                for filename in index['profiles']:
                    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.json'):
                        raise ValueError('Invalid schema profile filename')
                    namespace = Path(filename).stem
                    if namespace in profiles:
                        raise ValueError('Duplicate schema profile: ' + filename)
                    profiles[namespace] = self.index.parent / filename
            else:
                profiles = {name.split('.')[0]: self.index for name in index['records']}
            versions = index['versions'][:]
            if index.get('format') != 1 or any(root.split('.')[0] not in profiles for _, root in versions):
                raise ValueError('Invalid schema index')
            self._profiles = profiles
            self._user_roots = {}
            self._user_records = set()
            self.errors = []
            self._cache.clear()
            if self.directory:
                from schema_tools import validate_package
                from _interface_core import Document
                for path in sorted(self.directory.glob('*.json')):
                    try:
                        if path.stat().st_size > 16 * 1024 * 1024:
                            raise ValueError('Schema package too large')
                        package = validate_package(json.loads(path.read_text(encoding='utf-8')))
                        if self.collides(package['records']):
                            raise ValueError('Schema identifiers collide with installed schemas')
                        Document(json.dumps(package))
                        self._user_records.update(package['records'])
                        for _, root in package['versions']:
                            self._user_roots[root] = path
                        versions.extend(package['versions'])
                    except Exception as error:
                        self.errors.append(f'{path}: {error}')
            self.versions = versions
            self._signature = self._files_signature()

    def collides(self, records):
        if self._user_records.intersection(records):
            return True
        # Read builtin structures only if an import actually uses their namespaces.
        paths = {self._profiles[name.split('.')[0]] for name in records
                 if name.split('.')[0] in self._profiles}
        return any(set(json.loads(path.read_text(encoding='utf-8'))['records']).intersection(records)
                   for path in paths)

    def text(self, schema):
        with self._lock:
            if schema in self._cache:
                self._cache.move_to_end(schema)
                return self._cache[schema][1]
            if schema not in {root for _, root in self.versions}:
                raise ValueError('Unknown schema: ' + str(schema))
            if schema in self._user_roots:
                from schema_tools import validate_package, package_info
                package = validate_package(json.loads(self._user_roots[schema].read_text(encoding='utf-8')))
                package['package_info'] = {root: package_info(package) for _, root in package['versions']}
            else:
                records = {}
                pending = [schema.split('.')[0]]
                loaded = set()
                def references(value):
                    if isinstance(value, dict):
                        for key, item in value.items():
                            reference = key == 'base' or (key == 'type' and value.get('kind') in ('object', 'list'))
                            if reference and isinstance(item, str) and '.' in item:
                                yield item
                            else:
                                yield from references(item)
                    elif isinstance(value, list):
                        for item in value:
                            yield from references(item)
                while pending:
                    namespace = pending.pop()
                    if namespace in loaded:
                        continue
                    if namespace not in self._profiles:
                        raise ValueError('Missing schema dependency: ' + namespace)
                    profile = json.loads(self._profiles[namespace].read_text(encoding='utf-8'))
                    if profile.get('format') != 1:
                        raise ValueError('Invalid schema profile: ' + namespace)
                    # Whole namespaces include implicit polymorphic control types.
                    selected = {k: v for k, v in profile['records'].items() if k.split('.')[0] == namespace}
                    if not selected:
                        raise ValueError('Empty schema profile: ' + namespace)
                    records.update(selected)
                    loaded.add(namespace)
                    pending.extend(ref.split('.')[0] for ref in references(selected)
                                   if ref.split('.')[0] not in loaded)
                if schema not in records:
                    raise ValueError('Missing schema root: ' + schema)
                missing = set(references(records)) - records.keys()
                if missing:
                    raise ValueError('Missing schema records: ' + ', '.join(sorted(missing)))
                package = {'format': 1, 'versions': [v for v in self.versions if v[1] in records], 'records': records}
            text = json.dumps(package, ensure_ascii=False, separators=(',', ':'))
            self._cache[schema] = (package, text)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return text


def profile_text(schema, path=BUILTIN_INDEX):
    return SchemaRepository(path).text(schema)


def load_catalog(path=BUILTIN_INDEX):
    path = Path(path)
    catalog = json.loads(path.read_text(encoding='utf-8'))
    if 'profiles' not in catalog:
        return catalog
    if catalog.get('format') != 1 or 'records' in catalog:
        raise ValueError('Invalid schema index')
    records = {}
    seen = set()
    for filename in catalog['profiles']:
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.json'):
            raise ValueError('Invalid schema profile filename')
        if filename in seen:
            raise ValueError('Duplicate schema profile: ' + filename)
        seen.add(filename)
        profile = json.loads((path.parent / filename).read_text(encoding='utf-8'))
        if profile.get('format') != 1 or not isinstance(profile.get('records'), dict):
            raise ValueError('Invalid schema profile: ' + filename)
        if records.keys() & profile['records'].keys():
            raise ValueError('Duplicate schema records: ' + filename)
        records.update(profile['records'])
    for label, schema in catalog['versions']:
        if not isinstance(label, str) or schema not in records:
            raise ValueError('Invalid schema version: ' + str(schema))
    return {'format': catalog['format'], 'versions': catalog['versions'], 'records': records}


def catalog_text(path=BUILTIN_INDEX):
    return json.dumps(load_catalog(path), ensure_ascii=False, separators=(',', ':'))


def save_catalog(path, catalog):
    """Write a split index, or preserve the standalone format of external catalogs."""
    path = Path(path)
    if path.name != 'index.json':
        path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return
    profiles = {}
    for name, record in catalog['records'].items():
        namespace = name.split('.')[0]
        if not namespace or not all(c.isalnum() or c == '_' for c in namespace):
            raise ValueError('Invalid schema namespace: ' + namespace)
        profiles.setdefault(namespace + '.json', {})[name] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    for filename, records in profiles.items():
        text = json.dumps({'format': 1, 'records': records}, ensure_ascii=False, indent=2) + '\n'
        (path.parent / filename).write_text(text, encoding='utf-8')
    index = {'format': catalog['format'], 'versions': catalog['versions'], 'profiles': list(profiles)}
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
