"""Lazy loading, cache invalidation, dependency closure and JSON schema discovery."""
import json
from pathlib import Path

import pytest
from _interface_core import Document
from schema_catalog import BUILTIN_INDEX, SchemaRepository, catalog_text, load_catalog, save_catalog
from schema_tools import draft_package, import_package, probe_profile, export_package
from json_schema import document_schema


def test_startup_reads_only_index_and_cache_is_bounded(monkeypatch):
    reads = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        reads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    repository = SchemaRepository(cache_size=2)
    assert reads == [BUILTIN_INDEX]
    text = repository.text('essence_native.XDAT')
    assert reads == [BUILTIN_INDEX, BUILTIN_INDEX.parent / 'essence_native.json']
    assert repository.text('essence_native.XDAT') is text
    repository.refresh()
    assert repository.text('essence_native.XDAT') is text
    assert len(reads) == 2
    for _, schema in repository.versions:
        repository.text(schema)
    assert len(repository._cache) == 2


def test_all_profiles_match_full_catalog_and_detection():
    full = Document(catalog_text())
    repository = SchemaRepository()
    for schema in dict.fromkeys(root for _, root in repository.versions):
        full.create(schema)
        data = full.serialize()
        selected = Document(repository.text(schema))
        selected.create(schema)
        assert selected.serialize() == data
        selected.load_bytes(data, schema)
        restored = Document(repository.text(document_schema_from_text(selected.to_json())))
        restored.from_json(selected.to_json())
        assert restored.serialize() == data
        # Detection results must agree even for a mismatched profile.
        for candidate in ('ct26.XDAT', schema):
            assert Document(repository.text(candidate)).probe(data, candidate) == full.probe(data, candidate)


def document_schema_from_text(text):
    return json.loads(text)['schema']


def test_refresh_invalidates_changed_and_deleted_profiles(tmp_path):
    index = tmp_path / 'index.json'
    save_catalog(index, load_catalog())
    repository = SchemaRepository(index)
    original = repository.text('ct0.XDAT')
    path = tmp_path / 'ct0.json'
    data = json.loads(path.read_text())
    data['records']['ct0.XDAT']['test_marker'] = 'changed'
    path.write_text(json.dumps(data))
    repository.refresh()
    assert repository.text('ct0.XDAT') != original
    path.unlink()
    repository.refresh()
    result = probe_profile(repository, b'', 'ct0.XDAT', 'Interlude')
    assert result['schema_error'] and not result['compatible']
    assert Document(repository.text('ct26.XDAT'))


def test_dependency_closure_includes_polymorphic_namespace(tmp_path):
    catalog = {'format': 1, 'versions': [['A', 'a.XDAT'], ['Unused', 'c.XDAT']], 'records': {
        'a.XDAT': {'base': None, 'ops': [{'op': 'field', 'name': 'children', 'kind': 'list',
                                       'type': 'b.Base', 'poly': True, 'default': None}]},
        'a.Child': {'base': 'b.Base', 'ops': []},
        'b.Base': {'base': None, 'abstract': True, 'ops': []},
        'b.Child': {'base': 'b.Base', 'ops': []},
        'c.XDAT': {'base': None, 'ops': []}}}
    index = tmp_path / 'index.json'
    save_catalog(index, catalog)
    (tmp_path / 'c.json').write_text('broken')
    repository = SchemaRepository(index)
    text = repository.text('a.XDAT')
    assert set(json.loads(text)['records']) == {'a.XDAT', 'a.Child', 'b.Base', 'b.Child'}
    doc = Document(text)
    doc.create('a.XDAT')
    children = doc.children()[0]['id']
    assert doc.allowed_types(children) == ['a.Child']
    doc.add(children, 'a.Child')
    restored = Document(text)
    restored.load_bytes(doc.serialize(), 'a.XDAT')
    assert restored.serialize() == doc.serialize()


def test_user_import_metadata_edit_and_removal(tmp_path):
    repository = SchemaRepository(directory=tmp_path / 'installed')
    package = draft_package(repository.text('ct26.XDAT'), 'ct26.XDAT', 'Custom')
    package['revision'] = 7
    source = tmp_path / 'package.json'
    source.write_text(json.dumps(package))
    target = import_package(source, repository.directory, repository)
    repository.refresh()
    assert not repository.errors
    root = package['versions'][0][1]
    assert export_package(repository.text(root), root)['revision'] == 7
    with pytest.raises(ValueError, match='collide'):
        import_package(source, repository.directory, repository)
    package['revision'] = 8
    target.write_text(json.dumps(package))
    repository.refresh()
    assert export_package(repository.text(root), root)['revision'] == 8
    target.unlink()
    repository.refresh()
    with pytest.raises(ValueError, match='Unknown schema'):
        repository.text(root)


@pytest.mark.parametrize('before', [None, {'schema': 'wrong', 'text': '\\"}[' * 30000}, [1, True, None]])
def test_json_header_ignores_nested_schema_and_large_strings(tmp_path, before):
    path = tmp_path / 'document.json'
    path.write_text(json.dumps({'tree': before, 'schema': 'ct26.XDAT'}), encoding='utf-8')
    assert document_schema(path) == 'ct26.XDAT'


@pytest.mark.parametrize('text', ['{}', '[]', '{"schema": null}', '{"tree":{"schema":"ct0.XDAT"}}', '{'])
def test_json_header_rejects_missing_or_invalid_schema(tmp_path, text):
    path = tmp_path / 'document.json'
    path.write_text(text)
    with pytest.raises(ValueError):
        document_schema(path)
