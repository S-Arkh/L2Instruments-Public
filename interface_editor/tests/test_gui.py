import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import time

from PySide6.QtCore import QPoint, QPointF, Qt, QSettings
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from main import Editor


def test_two_views_search_edit_history_and_reopen(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Editor(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    errors = []
    window.error = errors.append
    window.show()
    def wait(predicate, timeout=30):
        until = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            if time.monotonic() > until:
                raise AssertionError('GUI task timed out: ' + str(errors))
            time.sleep(0.005)
        app.processEvents()
        assert not errors, errors
    fixture = str(ROOT / 'tests/fixtures/Interface_high_five.xdat')
    window.load_file(fixture, 'ct26.XDAT')
    wait(lambda: not window.busy)
    doc = window.document
    assert len(window.model.items) < 20  # no eager creation of all view nodes
    credit = next(i for i in doc.search('btnCredit')['matches'] if doc.info(i)['type'] == 'Button')
    option = next(i for i in doc.search('btnOption')['matches'] if doc.info(i)['type'] == 'Button')
    left, right = window.panes
    left.tree.setCurrentIndex(left.proxy.mapFromSource(window.model.index_for_id(credit)))
    right.tree.setCurrentIndex(right.proxy.mapFromSource(window.model.index_for_id(option)))
    assert left.node_id == credit and right.node_id == option
    resets = []
    window.model.modelReset.connect(lambda: resets.append(True))
    left.search.setText('btnCredit')
    wait(lambda: left.note.text().startswith('Совпадений:'))
    assert right.proxy.visible is None and right.node_id == option
    assert not resets  # filtering must not rebuild the source model
    assert window.model is right.model is left.model
    left.search.clear()
    wait(lambda: left.proxy.visible is None)
    assert left.node_id == credit
    right.tree.setCurrentIndex(right.proxy.mapFromSource(window.model.index_for_id(credit)))
    window.edit(credit, 'name', 'btnNativeTest')
    wait(lambda: not window.busy)
    for pane in window.panes:
        assert next(p['value'] for p in pane.props if p['name'] == 'name') == 'btnNativeTest'
    assert window.document.summary()['dirty']
    window.history(False)
    wait(lambda: not window.busy)
    assert doc.info(credit)['name'] == 'btnCredit' and not doc.summary()['dirty']
    # Load a fresh file without retaining the previous model/proxy graph.
    window.load_file(fixture, 'ct26.XDAT')
    wait(lambda: not window.busy and not window.tasks)
    assert window.document is not doc
    window.close()
    app.processEvents()


def test_compare_scroll_transfer_neighbors_and_json(tmp_path):
    from comparison import ORANGE, RED
    app = QApplication.instance() or QApplication([])
    window = Editor(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    errors = []
    window.error = errors.append
    window.resize(1600, 900)
    window.show()

    def wait(predicate, timeout=40):
        until = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            assert time.monotonic() < until, errors
            time.sleep(0.005)
        app.processEvents()
        assert not errors, errors

    window.load_file(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    wait(lambda: not window.busy)
    doc = window.document
    original = doc.serialize()
    credit = next(i for i in doc.search('btnCredit')['matches'] if doc.info(i)['type'] == 'Button')
    textbox = next(i for i in doc.search('TextBox')['matches'] if doc.info(i)['type'] == 'TextBox')
    left, right = window.panes
    left.reveal(credit)
    right.reveal(textbox)
    window.sync_scroll.setChecked(True)
    window.compare_action.setChecked(True)
    app.processEvents()
    assert left.property_names == right.property_names
    row = left.property_names.index('name')
    assert left.table.item(row, 1).background().color().name() == ORANGE
    assert right.table.item(row, 1).background().color().name() == ORANGE
    row = left.property_names.index('normalTex')
    assert left.table.item(row, 0).background().color().name() == RED
    assert right.table.item(row, 1).text() == 'Нет поля'
    assert not right.table.item(row, 1).flags() & Qt.ItemFlag.ItemIsEditable
    assert doc.serialize() == original

    trees = [p.tree.verticalScrollBar().value() for p in window.panes]
    assert window.shared_scroll.maximum() > 0
    window.shared_scroll.setValue(140)
    assert [p.table.verticalScrollBar().value() for p in window.panes] == [140, 140]
    before = window.shared_scroll.value()
    event = QWheelEvent(QPointF(40, 40), QPointF(40, 40), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(right.table.viewport(), event)
    app.processEvents()
    assert window.shared_scroll.value() > before
    assert left.table.verticalScrollBar().value() == right.table.verticalScrollBar().value()
    assert [p.tree.verticalScrollBar().value() for p in window.panes] == trees

    # Right-only rows must edit by property name, not by the left table's index.
    left_names = {p['name'] for p in left.props}
    prop = next(p for p in right.props if p['name'] not in left_names and p['kind'] == 'string' and not p['enum'] and not p['readonly'])
    row = right.property_names.index(prop['name'])
    right.table.item(row, 1).setText('edited after alignment')
    wait(lambda: not window.busy)
    assert next(p['value'] for p in doc.properties(textbox) if p['name'] == prop['name']) == 'edited after alignment'
    window.history(False)
    wait(lambda: not window.busy)
    assert doc.serialize() == original

    # A property existing in the schema but hidden by a condition gets a reason.
    window.edit(credit, 'useFont', 1)
    wait(lambda: not window.busy)
    row = right.property_names.index('fontName')
    right_font = next(p for p in right.all_props if p['name'] == 'fontName')
    if not right_font['active']:
        assert 'Неактивно' in right.table.item(row, 1).toolTip()
    window.history(False)
    wait(lambda: not window.busy)

    # Transfer clears a conflicting destination filter without changing XDAT.
    right.search.setText('definitely-not-a-node')
    wait(lambda: right.proxy.visible == set())
    window.transfer(0, 1)
    assert right.node_id == left.node_id == credit
    assert not right.search.text() and right.proxy.visible is None
    assert doc.serialize() == original
    right.search.setText('btnCredit')
    wait(lambda: right.proxy.visible is not None and credit in right.proxy.matches)
    window.transfer(0, 1)
    assert right.search.text() == 'btnCredit'
    right.reveal(textbox)
    window.transfer(1, 0)
    assert left.node_id == textbox and doc.serialize() == original

    left.reveal(credit)
    left.neighbors.setChecked(False)
    left.search.setText('btnCredit')
    sibling = next(n['id'] for n in doc.children(doc.info(credit)['parent']) if n['id'] != credit)
    wait(lambda: left.proxy.visible is not None and credit in left.proxy.matches)
    assert sibling not in left.proxy.visible
    left.neighbors.setChecked(True)
    wait(lambda: sibling in left.proxy.visible)
    found = left.proxy.mapFromSource(window.model.index_for_id(credit))
    assert found.data(Qt.ItemDataRole.FontRole).bold()
    assert right.proxy.visible is None
    assert doc.serialize() == original

    window.sync_scroll.setChecked(False)
    app.processEvents()
    right_scroll = right.table.verticalScrollBar().value()
    left.table.verticalScrollBar().setValue(0)
    assert right.table.verticalScrollBar().value() == right_scroll

    output = tmp_path / 'export.json'
    window.export_json_file(str(output))
    wait(lambda: not window.busy)
    assert output.exists() and not doc.summary()['dirty']
    window.load_file(str(output), None)
    wait(lambda: not window.busy and not window.tasks)
    assert window.document.serialize() == original
    assert window.document.summary()['dirty'] and not window.document.summary()['file']
    assert window.version.currentData() == 'ct26.XDAT'
    window.document.save(str(tmp_path / 'imported.xdat'))
    window.close()
    app.processEvents()
