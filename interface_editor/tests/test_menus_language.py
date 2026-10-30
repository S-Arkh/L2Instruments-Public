import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import time

import pytest
from PySide6.QtCore import QSettings, Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QCheckBox, QSpinBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from main import Editor


@pytest.fixture
def ui(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('Левая область/neighbors', True)  # migrate older preference
    window = Editor(settings=settings)
    errors = []
    window.error = errors.append
    window.show()

    def wait(predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            assert time.monotonic() < deadline, errors
            time.sleep(0.005)
        app.processEvents()
        assert not errors, errors

    window.load_file(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    wait(lambda: not window.busy)
    credit = next(n for n in window.document.search('btnCredit')['matches'] if window.document.info(n)['type'] == 'Button')
    for pane in window.panes:
        pane.reveal(credit)
    yield app, window, wait, tmp_path
    wait(lambda: not window.busy and not window.tasks)
    if window.document.summary()['dirty']:
        window.document.save(str(tmp_path / 'cleanup.xdat'))
    window.close()
    app.processEvents()


def send_wheel(widget, delta=-120):
    position = QPoint(widget.width() // 2, widget.height() // 2)
    global_position = widget.mapToGlobal(position)
    event = QWheelEvent(QPointF(position), QPointF(global_position), QPoint(), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_file_and_options_menus_and_shortcuts(ui, monkeypatch):
    app, window, wait, _ = ui
    file_actions = [a for a in window.file_menu.actions() if not a.isSeparator()]
    assert file_actions == [window.open_action, window.save_action, window.save_as_action,
                            window.open_json_action, window.export_json_action]
    assert window.file_button.text() == 'Файл'
    assert all(action not in window.bar.actions() for action in file_actions)
    assert window.sync_scroll in window.options_menu.actions()
    assert window.wheel_values in window.options_menu.actions()
    assert window.language_menu.menuAction() in window.options_menu.actions()
    assert window.sync_scroll not in window.view_bar.actions()
    assert window.sync_scroll.isCheckable() and window.wheel_values.isCheckable()
    assert not window.wheel_values.isChecked()
    assert not window.findChildren(QCheckBox)
    left, right = window.panes
    assert left.options_menu is not right.options_menu
    assert left.options_menu.actions() == [left.neighbors]
    assert left.neighbors.isChecked() and not right.neighbors.isChecked()
    left.neighbors.trigger()
    assert not left.neighbors.isChecked() and not right.neighbors.isChecked()
    called = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args, **kwargs: (called.append(args) or ('', '')))
    window.activateWindow()
    window.setFocus()
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    wait(lambda: len(called) == 1)


def test_wheel_does_not_mutate_until_enabled(ui):
    app, window, wait, _ = ui
    doc = window.document
    left, right = window.panes
    original = doc.serialize()
    row = left.property_names.index('alwaysOnTop')
    combo = left.table.cellWidget(row, 1)
    old_index = combo.currentIndex()
    combo.setFocus()
    window.shared_scroll.setValue(0)
    send_wheel(combo)
    app.processEvents()
    assert combo.currentIndex() == old_index
    assert window.shared_scroll.value() > 0
    assert left.table.verticalScrollBar().value() == right.table.verticalScrollBar().value()
    assert doc.serialize() == original and not doc.summary()['dirty']
    # A spin editor and its line edit obey the same policy.
    spin_row = left.property_names.index('size_absolute_width')
    spin = QSpinBox()
    spin.setRange(0, 1000)
    spin.setValue(98)
    left.table.setCellWidget(spin_row, 1, spin)
    window.shared_scroll.setValue(0)
    send_wheel(spin.lineEdit())
    app.processEvents()
    assert spin.value() == 98 and window.shared_scroll.value() > 0
    # Enable the menu option; a real combo-wheel edit now reaches the document.
    window.wheel_values.trigger()
    assert window.settings.value('wheel_values', False, type=bool)
    window.shared_scroll.setValue(0)
    combo.setFocus()
    before = next(p['value'] for p in doc.properties(left.node_id) if p['name'] == 'alwaysOnTop')
    send_wheel(combo)
    wait(lambda: not window.busy)
    after = next(p['value'] for p in doc.properties(left.node_id) if p['name'] == 'alwaysOnTop')
    assert before != after and doc.summary()['dirty']
    window.history(False)
    wait(lambda: not window.busy)
    assert doc.serialize() == original
    window.wheel_values.setChecked(False)
    row = left.property_names.index('alwaysOnTop')
    send_wheel(left.table.cellWidget(row, 1))
    app.processEvents()
    assert doc.serialize() == original


def test_live_language_switch_and_settings(ui):
    app, window, wait, tmp_path = ui
    doc = window.document
    original = doc.serialize()
    left, right = window.panes
    left.search.setText('btnCredit')
    wait(lambda: left.note.text().startswith('Совпадений:'))
    window.shared_scroll.setValue(112)
    selected = [p.node_id for p in window.panes]
    expanded = [p.expanded_ids.copy() for p in window.panes]
    visible = left.proxy.visible.copy()
    window.language_actions['en'].trigger()
    app.processEvents()
    assert window.file_button.text() == 'File'
    assert window.options_button.text() == 'Options'
    assert window.language_menu.title() == 'Language'
    assert window.open_action.text() == 'Open'
    assert window.wheel_values.text() == 'Change property values with mouse wheel'
    assert left.options_button.text() == 'Pane options'
    assert left.title_label.text() == 'Left pane' and right.title_label.text() == 'Right pane'
    assert window.model.headerData(0, Qt.Orientation.Horizontal) == 'Object'
    assert left.table.horizontalHeaderItem(0).text() == 'Property'
    assert left.note.text().startswith('Matches:')
    assert left.search.text() == 'btnCredit' and left.proxy.visible == visible
    assert selected == [p.node_id for p in window.panes]
    assert expanded == [p.expanded_ids for p in window.panes]
    assert window.shared_scroll.value() == 112
    row = left.property_names.index('alwaysOnTop')
    assert left.table.cellWidget(row, 1).currentText() == 'Not set (-1)'
    assert doc.serialize() == original and not doc.summary()['dirty']
    # Switching language must also preserve an unsaved edit and its history.
    width = next(p['value'] for p in doc.properties(selected[0]) if p['name'] == 'size_absolute_width')
    window.edit(selected[0], 'size_absolute_width', width + 1)
    wait(lambda: not window.busy)
    changed = doc.serialize()
    history_size = doc.summary()['undo']
    window.language_actions['ru'].trigger()
    assert window.file_button.text() == 'Файл'
    wait(lambda: left.note.text().startswith('Совпадений:'))
    assert doc.serialize() == changed and doc.summary()['dirty']
    assert doc.summary()['undo'] == history_size
    window.history(False)
    wait(lambda: not window.busy)
    assert doc.serialize() == original
    window.language_actions['en'].trigger()
    window.wheel_values.setChecked(True)
    window.sync_scroll.setChecked(False)
    left.neighbors.setChecked(False)
    right.neighbors.setChecked(True)
    wait(lambda: not window.tasks)
    window.settings.sync()
    other = Editor(settings=QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    assert other.language == 'en'
    assert other.file_button.text() == 'File'
    assert other.wheel_values.isChecked() and not other.sync_scroll.isChecked()
    assert not other.panes[0].neighbors.isChecked() and other.panes[1].neighbors.isChecked()
    other.close()
    app.processEvents()


def test_application_rename_migrates_settings(tmp_path, monkeypatch):
    import main as module
    app = QApplication.instance() or QApplication([])
    old = QSettings(str(tmp_path / 'old.ini'), QSettings.Format.IniFormat)
    new = QSettings(str(tmp_path / 'new.ini'), QSettings.Format.IniFormat)
    old.setValue('language', 'en')
    old.setValue('wheel_values', True)
    old.setValue('directory', str(ROOT.parent / 'xdat_editor' / 'tests/fixtures'))
    monkeypatch.setattr(module, 'QSettings', lambda org, name: new if name == 'InterfaceEditor' else old)
    window = module.Editor()
    assert window.language == 'en' and window.wheel_values.isChecked()
    assert window.settings.value('directory') == (ROOT / 'tests/fixtures').as_posix()
    assert 'Interface Editor' in window.windowTitle()
    assert new.value('migration_complete', False, type=bool)
    window.close(); app.processEvents()
