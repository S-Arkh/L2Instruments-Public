"""Split catalog loading, malformed indexes and generator roundtrips."""
import json
import sys

import pytest
from synthetic_fixtures import ROOT
from _interface_core import Document
from schema_catalog import BUILTIN_INDEX, catalog_text, load_catalog, save_catalog

sys.path.insert(0, str(ROOT / 'tools'))
from build_native_profiles import build
from update_legacy_profiles import update


def test_profiles_are_self_contained_and_all_roots_roundtrip():
    catalog = load_catalog()
    index = json.loads(BUILTIN_INDEX.read_text(encoding='utf-8'))
    for filename in index['profiles']:
        profile = json.loads((BUILTIN_INDEX.parent / filename).read_text(encoding='utf-8'))
        versions = [v for v in catalog['versions'] if v[1] in profile['records']]
        assert versions
        profile['versions'] = versions
        text = json.dumps(profile)
        for _, root in versions:
            doc = Document(text)
            doc.create(root)
            data = doc.serialize()
            restored = Document(catalog_text())
            restored.load_bytes(data, root)
            assert restored.serialize() == data


def test_catalog_write_and_generators_preserve_content(tmp_path):
    catalog = load_catalog()
    for korean in (False, True):
        package = build(catalog, korean)
        assert all(catalog['records'][k] == v for k, v in package['records'].items())
        assert package['versions'][0] in catalog['versions']
    assert update(json.loads(json.dumps(catalog))) == catalog
    index = tmp_path / 'index.json'
    save_catalog(index, catalog)
    assert load_catalog(index) == catalog
    assert list(load_catalog(index)['records']) == list(catalog['records'])
    standalone = tmp_path / 'external.json'
    save_catalog(standalone, catalog)
    assert load_catalog(standalone) == catalog


@pytest.mark.parametrize('fault', ['missing', 'duplicate_file', 'duplicate_record', 'missing_root'])
def test_invalid_index_fails_instead_of_loading_partial_catalog(tmp_path, fault):
    profile = {'format': 1, 'records': {'test.XDAT': {'ops': []}}}
    (tmp_path / 'test.json').write_text(json.dumps(profile))
    index = {'format': 1, 'versions': [['Test', 'test.XDAT']], 'profiles': ['test.json']}
    if fault == 'missing':
        index['profiles'].append('missing.json')
    elif fault == 'duplicate_file':
        index['profiles'].append('test.json')
    elif fault == 'duplicate_record':
        (tmp_path / 'other.json').write_text(json.dumps(profile))
        index['profiles'].append('other.json')
    else:
        index['versions'][0][1] = 'missing.XDAT'
    path = tmp_path / 'index.json'
    path.write_text(json.dumps(index))
    with pytest.raises((ValueError, FileNotFoundError)):
        load_catalog(path)
