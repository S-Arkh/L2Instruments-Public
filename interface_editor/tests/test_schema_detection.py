import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QComboBox, QPushButton, QProgressDialog, QInputDialog, QFileDialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document
from schema_tools import draft_package, load_schemas, probe
from main import Editor
import schema_dialog

SCHEMA = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
FIXTURES = json.loads((ROOT / 'tests/fixtures/manifest.json').read_text())


@pytest.mark.parametrize('fixture', FIXTURES, ids=[f['file'] for f in FIXTURES])
def test_probe_reference(fixture):
    data = (ROOT / 'tests/fixtures' / fixture['file']).read_bytes()
    result = Document(SCHEMA).probe(data, fixture['schema'])
    assert result['compatible'], result


def test_bad_schema_corruption_and_document_preserved():
    data = (ROOT / 'tests/fixtures/Interface_high_five.xdat').read_bytes()
    document = Document(SCHEMA)
    document.load_bytes(data, 'ct26.XDAT')
    assert not document.probe(data, 'ct0.XDAT')['compatible']
    assert not document.probe(data[:100], 'ct26.XDAT')['compatible']
    assert not document.probe(data, 'missing.XDAT')['compatible']
    assert document.serialize() == data
    result = probe(document, data, 'ct0.XDAT', 'Interlude')
    assert result['error'] and result['hex']


def test_draft_isolated_and_reloadable(tmp_path):
    package = draft_package(SCHEMA, 'ct26.XDAT', 'Custom HF')
    original = json.loads(SCHEMA)
    assert not (set(package['records']) & set(original['records']))
    path = tmp_path / 'custom.json'
    path.write_text(json.dumps(package), encoding='utf-8')
    text, errors = load_schemas(ROOT / 'schemas/schemas.json', tmp_path)
    assert not errors
    data = (ROOT / 'tests/fixtures/Interface_high_five.xdat').read_bytes()
    assert Document(text).probe(data, package['versions'][0][1])['compatible']
    # Editing the draft cannot change the built-in record definitions.
    assert json.loads(text)['records']['ct26.Window'] == original['records']['ct26.Window']
    path.write_text('{bad json', encoding='utf-8')
    text, errors = load_schemas(ROOT / 'schemas/schemas.json', tmp_path)
    assert len(errors) == 1
    assert json.loads(text) == original


def tiny_catalog():
    def record(kind):
        return {'base': None, 'abstract': False, 'ops': [
            {'op': 'field', 'name': 'value', 'kind': kind, 'default': 0}]}
    return json.dumps({'format': 1, 'versions': [['A', 'a.XDAT'], ['B', 'b.XDAT'], ['C', 'c.XDAT']],
        'records': {'a.XDAT': record('int'), 'b.XDAT': record('int'), 'c.XDAT': record('string')}})


def test_multiple_matches_and_tail():
    catalog = json.loads(tiny_catalog())
    catalog['records']['a.XDAT']['ops'].append({'op': 'tail'})
    document = Document(json.dumps(catalog))
    assert document.probe(b'\x01\0\0\0', 'a.XDAT')['compatible']
    assert document.probe(b'\x01\0\0\0', 'b.XDAT')['compatible']
    result = document.probe(b'\x01\0\0\0extra', 'a.XDAT')
    assert result['compatible'] and result['tail_bytes'] == 5


@pytest.fixture
def ui(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Editor(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    window.user_schema_directory = tmp_path / 'schemas'
    window.schema_text = tiny_catalog()
    window.reload_schemas = lambda: None
    errors = []
    window.error = errors.append
    def wait():
        deadline = time.monotonic() + 30
        while window.busy or window.tasks:
            app.processEvents()
            assert time.monotonic() < deadline
            time.sleep(0.005)
        assert not errors, errors
    yield window, wait
    wait()
    window.close()
    app.processEvents()


def test_wrong_selection_offers_switch(ui, tmp_path, monkeypatch):
    window, wait = ui
    path = tmp_path / 'input.xdat'
    path.write_bytes(b'\x01\0\0\0')
    shown = []
    def choose(dialog):
        combo = dialog.findChild(QComboBox)
        shown.append(combo.count())
        combo.setCurrentIndex(1)
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Переключиться и открыть').click()
        return 1
    monkeypatch.setattr(QDialog, 'exec', choose)
    window.load_file(str(path), 'c.XDAT')
    wait()
    assert shown == [2]
    assert window.document.summary()['schema'] == 'b.XDAT'
    assert window.document.serialize() == path.read_bytes()


@pytest.mark.parametrize('schema', ['essence_native.XDAT', 'korea_native.XDAT'])
def test_native_profile_gui_open_edit_save(ui, tmp_path, monkeypatch, schema):
    sys.path.insert(0, str(ROOT / 'tools'))
    from create_native_fixture import fixture
    window, wait = ui
    window.schema_text = SCHEMA
    assert window.version.findData(schema) >= 0
    source = tmp_path / 'native.xdat'
    original = fixture(SCHEMA, schema).serialize()
    source.write_bytes(original)
    window.load_file(str(source), schema)
    wait()
    assert window.version.currentData() == schema
    doc = window.document
    windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
    node = doc.children(windows)[0]['id']
    window.mutate(lambda: doc.set(node, 'name', 'GuiNativeFixtureEdited'))
    wait()
    target = tmp_path / 'edited.xdat'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
    window.save_file(True)
    wait()
    assert target.read_bytes() == doc.serialize() != original
    assert source.read_bytes() == original
    restored = Document(SCHEMA)
    restored.load(str(target), schema)
    assert restored.search('GuiNativeFixtureEdited')['matches']


def test_no_match_keeps_existing_document(ui, tmp_path, monkeypatch):
    window, wait = ui
    window.document = Document(tiny_catalog())
    window.document.load_bytes(b'\x01\0\0\0', 'a.XDAT')
    old = window.document
    path = tmp_path / 'broken.xdat'
    path.write_bytes(b'\xff')
    offered = []
    def dismiss(dialog):
        offered.extend(b.text() for b in dialog.findChildren(QPushButton))
        return 0
    monkeypatch.setattr(QDialog, 'exec', dismiss)
    window.load_file(str(path), 'a.XDAT')
    wait()
    assert 'Создать черновик схемы…' in offered
    assert window.document is old


def test_cancel_analysis(ui, tmp_path, monkeypatch):
    window, wait = ui
    path = tmp_path / 'input.xdat'
    path.write_bytes(b'\x01\0\0\0')
    shown = []
    monkeypatch.setattr(schema_dialog, 'show_results', lambda *args: shown.append(True))
    schema_dialog.analyze(window, str(path), 'c.XDAT', 'failed')
    progress = window.findChild(QProgressDialog)
    progress.canceled.emit()
    wait()
    assert not shown and window.document is None


def test_create_draft_and_recheck_edited_layout(ui, tmp_path, monkeypatch):
    window, wait = ui
    data = b'\x01\0\0\0\x02\0\0\0'
    path = tmp_path / 'custom.xdat'
    path.write_bytes(data)
    text = tiny_catalog()
    results = [probe(Document(text), data, schema, label)
               for label, schema in json.loads(text)['versions']]
    assert not any(r['compatible'] for r in results)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args: ('My custom format', True))
    def create(dialog):
        combo = dialog.findChild(QComboBox)
        combo.setCurrentIndex(combo.findData('a.XDAT'))
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Создать черновик схемы…').click()
        return 0
    monkeypatch.setattr(QDialog, 'exec', create)
    schema_dialog.show_results(window, str(path), 'a.XDAT', data, results, 'failed')
    draft = next(window.user_schema_directory.glob('*.json'))
    package = json.loads(draft.read_text(encoding='utf-8'))
    schema = package['versions'][0][1]
    assert not Document(json.dumps(package)).probe(data, schema)['compatible']
    package['records'][schema]['ops'].append(
        {'op': 'field', 'name': 'extra', 'kind': 'int', 'default': 0})
    draft.write_text(json.dumps(package), encoding='utf-8')
    builtin = tmp_path / 'builtin.json'
    builtin.write_text(text, encoding='utf-8')
    reloaded, errors = load_schemas(builtin, window.user_schema_directory)
    assert not errors
    assert Document(reloaded).probe(data, schema)['compatible']
