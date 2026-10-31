"""Synthetic, redistributable unknown layouts; no client files or local paths."""
import json
import os
from pathlib import Path
import struct
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pytest
from _interface_core import Document
from schema_tools import validate_package, export_package, import_package, report
from schema_research import suggest, apply_change, inspect_samples, scan_anchors


def catalog():
    return {'format': 1, 'versions': [['Synthetic', 'test.XDAT']], 'records': {
        'test.XDAT': {'base': None, 'abstract': False, 'ops': [
            {'op': 'field', 'name': 'items', 'kind': 'list', 'type': 'test.Item', 'default': None}]},
        'test.Item': {'base': None, 'abstract': False, 'ops': [
            {'op': 'field', 'name': 'name', 'kind': 'string', 'default': ''},
            {'op': 'field', 'name': 'enabled', 'kind': 'bool', 'default': 0},
            {'op': 'field', 'name': 'label', 'kind': 'string', 'default': ''}]}}}


def string(value):
    return bytes([len(value) + 1]) + value.encode() + b'\0'


def sample(extra=True, count=3):
    return struct.pack('<i', count) + b''.join(
        string(f'Node{i}') + struct.pack('<i', 1) +
        (struct.pack('<i', 0x7fffffff - i) if extra else b'') + string(f'Label{i}')
        for i in range(count))


def test_trace_failure_paths_conditions_and_document_preserved():
    p = catalog()
    p['records']['test.Item']['ops'].insert(2, {'op': 'if', 'condition': 'enabled', 'yes': [], 'no': []})
    doc = Document(json.dumps(p))
    original = sample(False)
    doc.load_bytes(original, 'test.XDAT')
    result = doc.diagnose(sample(), 'test.XDAT')
    assert result['failure']['path'] == '$.items[0].label'
    assert result['failure']['offset'] == 15
    assert any(e['kind'] == 'condition' and e['value'] is True for e in result['trace'])
    assert doc.serialize() == original
    limited = doc.diagnose(original, 'test.XDAT', 2)
    assert limited['compatible'] and limited['trace_truncated']
    assert len(limited['trace']) == 2
    with pytest.raises(RuntimeError):
        doc.diagnose(original, 'test.XDAT', 0)


def test_recover_unknown_field_across_samples_and_edit_roundtrip():
    p = catalog()
    samples = [sample(count=2), sample(count=5)]
    result = suggest(p, samples, seconds=10)
    matches = [h for h in result['hypotheses'] if h['complete']]
    assert matches
    recovered = apply_change(p, matches[0]['change'])
    assert recovered != p and p == catalog()
    assert all(r['compatible'] and not r['tail_bytes'] for r in inspect_samples(recovered, samples))
    doc = Document(json.dumps(recovered))
    doc.load_bytes(samples[1], 'test.XDAT')
    first = doc.children(doc.children()[0]['id'])[0]['id']
    doc.set(first, 'label', 'Changed length')
    changed = doc.serialize()
    assert changed != samples[1]
    reread = Document(json.dumps(recovered))
    reread.load_bytes(changed, 'test.XDAT')
    assert reread.serialize() == changed
    assert reread.search('Node0')
    assert not reread.probe(changed[:-1], 'test.XDAT')['compatible']


def test_cancel_budget_and_opaque_tail_not_complete():
    p = catalog()
    assert suggest(p, [sample()], cancelled=lambda: True)['stopped'] == 'cancelled'
    assert suggest(p, [sample()], max_trials=0)['trials'] == 0
    p['records']['test.XDAT']['ops'] = [{'op': 'tail'}]
    result = inspect_samples(p, [sample()])[0]
    assert result['compatible'] and result['tail_bytes'] == len(sample())


def test_portable_export_import_and_private_report(tmp_path):
    p = catalog()
    p['private_metadata'] = 'DO_NOT_EXPORT'
    exported = export_package(json.dumps(p), 'test.XDAT')
    assert 'DO_NOT_EXPORT' not in json.dumps(exported)
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(exported))
    installed = import_package(source, tmp_path / 'installed', json.dumps({'records': {}}))
    assert json.loads(installed.read_text()) == exported
    with pytest.raises(ValueError, match='collide'):
        import_package(source, tmp_path / 'installed', json.dumps(p))
    r = report('/private/location/input.xdat', b'private', 'test.XDAT', [
        {'schema': 'test.XDAT', 'compatible': False, 'offset': 4, 'error': 'private', 'hex': 'private', 'label': 'private'}])
    assert 'private' not in json.dumps(r)
    assert 'file' not in r and r['results'][0]['offset'] == 4


@pytest.mark.parametrize('damage', ['base_cycle', 'object_cycle', 'missing_type', 'unknown_kind', 'unknown_op', 'field_collision', 'condition_reference'])
def test_reject_invalid_schema_before_native_recursion(damage):
    p = catalog()
    if damage == 'base_cycle':
        p['records']['test.Item']['base'] = 'test.Item'
    elif damage == 'object_cycle':
        p['records']['test.Item']['ops'].append({'op': 'field', 'kind': 'object', 'name': 'loop', 'type': 'test.XDAT', 'default': None})
        p['records']['test.XDAT']['ops'][0]['kind'] = 'object'
    elif damage == 'missing_type':
        p['records']['test.XDAT']['ops'][0]['type'] = 'absent.Item'
    elif damage == 'unknown_kind':
        p['records']['test.Item']['ops'][0]['kind'] = 'garbage'
    elif damage == 'field_collision':
        p['records']['test.Item']['ops'].append({'op': 'field', 'kind': 'list', 'name': 'name', 'type': 'test.Item', 'default': None})
    elif damage == 'condition_reference':
        p['records']['test.Item']['ops'].append({'op': 'if', 'condition': 'missing', 'yes': [], 'no': []})
    else:
        p['records']['test.Item']['ops'][0]['op'] = 'garbage'
    with pytest.raises(ValueError):
        validate_package(p)


def test_every_builtin_can_export_as_standalone():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'schemas/schemas.json').read_text()
    for _, schema in json.loads(text)['versions']:
        validate_package(export_package(text, schema))


def test_workbench_accept_undo_export_and_background(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QFileDialog
    from main import Editor
    from schema_workbench import SchemaWorkbench
    app = QApplication.instance() or QApplication([])
    editor = Editor(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    editor.schema_text = json.dumps(catalog())
    editor.document = Document(editor.schema_text)
    editor.document.load_bytes(sample(False), 'test.XDAT')
    original = editor.document.serialize()
    errors = []
    editor.error = errors.append
    source = tmp_path / 'sample.xdat'
    source.write_bytes(sample())
    dialog = SchemaWorkbench(editor, source, 'test.XDAT')
    before = dialog.editor.toPlainText()
    def wait():
        deadline = time.monotonic() + 30
        while dialog.running or editor.tasks:
            app.processEvents()
            assert time.monotonic() < deadline
            time.sleep(.005)
        assert not errors
    dialog.run(True)
    wait()
    assert dialog.hypotheses and dialog.trace.topLevelItemCount()
    dialog.choices.setCurrentRow(next(i for i,h in enumerate(dialog.hypotheses) if h['complete']))
    dialog.accept_hypothesis()
    wait()
    assert dialog.results[0]['compatible']
    output = tmp_path / 'export.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(output), 'JSON'))
    dialog.export()
    validate_package(json.loads(output.read_text()))
    dialog.undo_schema()
    assert dialog.editor.toPlainText() == before
    assert editor.document.serialize() == original
    dialog.close()
    editor.close()


def test_anomalies_are_hints_and_anchor_scan_is_bounded():
    p = catalog()
    data = struct.pack('<i', 1) + string('Node') + struct.pack('<i', 777) + string('label')
    result = inspect_samples(p, [data])[0]
    assert result['compatible']
    assert result['first_anomaly']['field'] == 'enabled'
    payload = string('Item') * 20
    hits = scan_anchors(p, payload, 0, limit=3)
    assert len(hits) == 3 and hits[0]['offset'] == 0
    assert not scan_anchors(p, b'Item without framing', 0)


def test_cli_research_export_contains_no_sample_paths(tmp_path):
    import subprocess
    package = tmp_path / 'package.json'
    package.write_text(json.dumps(catalog()))
    data = tmp_path / 'local-private-sample.xdat'
    data.write_bytes(sample())
    output = tmp_path / 'recovered.json'
    tool = Path(__file__).resolve().parents[1] / 'tools/research_schema.py'
    run = subprocess.run([sys.executable, str(tool), '--package', str(package), '--sample', str(data),
                          '--suggest', '--apply', '0', '--output', str(output)],
                         check=True, capture_output=True, text=True)
    assert str(tmp_path) not in run.stdout and data.name not in run.stdout
    assert json.loads(run.stdout)['status'] == 'sample-tested'
    validate_package(json.loads(output.read_text()))
