import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import time

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import SysStrings
from main import Editor
from strings_dialog import StringsDialog
from localization import StringCatalog


def test_strings_edit_assign_preview_and_independent_languages(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Editor(QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    errors = []; window.error = errors.append; window.show()
    def wait(predicate):
        deadline = time.monotonic() + 30
        while not predicate():
            app.processEvents(); time.sleep(.01)
            assert time.monotonic() < deadline, errors
        app.processEvents(); assert not errors, errors
    window.load_file(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    wait(lambda: not window.busy)
    english = SysStrings(); english.load(str(ROOT / 'tests/fixtures/sysstring/fileedit.dat'))
    en = window.strings.attach(english, 'English')
    russian = SysStrings(); russian.load(str(ROOT / 'tests/fixtures/sysstring/fileedit.dat'))
    russian.set(6000, 'Тестовая кнопка'); russian.save(str(tmp_path / 'sysstring-ru.dat'))
    ru = window.strings.attach(russian, 'Русский')
    window.strings.activate(en['id'])
    doc = window.document
    credit = next(n for n in doc.search('btnCredit')['matches'] if doc.info(n)['type'] == 'Button')
    pane = window.panes[0]; pane.reveal(credit)
    window.assign_string_id(6000, pane, credit, 'buttonName')
    wait(lambda: not window.busy)
    props = {p['name']: p['value'] for p in doc.properties(credit)}
    assert props['buttonName'] == 6000 and props['buttonNameText'] == 'undefined'
    assert doc.summary()['undo'] == 1
    pane.tabs.setCurrentIndex(1)
    wait(lambda: pane.preview.result is not None)
    assert not any('SysString #6000' in w for w in pane.preview.result.warnings)
    first = bytes(pane.preview.result.image.constBits())
    before = doc.serialize()
    window.strings.activate(ru['id'])
    wait(lambda: pane.preview.result is not None)
    assert window.strings.snapshot()[6000] == 'Тестовая кнопка'
    assert bytes(pane.preview.result.image.constBits()) != first
    assert doc.serialize() == before
    window.strings.edit(ru, 6000, 'Новое имя')
    wait(lambda: pane.preview.result is not None)
    assert window.strings.dirty and doc.serialize() == before
    new_id = window.strings.suggest_id(); assert new_id > 6000
    window.strings.change_translations(new_id, {en['id']: 'New string', ru['id']: 'Новая строка'}, new=True)
    assert english.lookup(new_id) == 'New string' and russian.lookup(new_id) == 'Новая строка'
    import pytest
    with pytest.raises(ValueError): window.strings.change_translations(6000, {en['id']: 'collision'}, new=True)
    assert english.lookup(6000) == 'Test Button'
    dialog = StringsDialog(window, select=True)
    dialog.search.setText(str(new_id))
    row = next(i for i, r in enumerate(dialog.model.rows) if r['id'] == new_id)
    dialog.table.setCurrentIndex(dialog.proxy.mapFromSource(dialog.model.index(row, 0)))
    dialog.choose(); assert dialog.selected_id == new_id
    dialog.deleteLater()
    pane.tabs.setCurrentIndex(0)
    for entry in window.strings.entries:
        entry['table'].save(str(tmp_path / (entry['id'] + '.dat')))
        window.strings.refresh(entry)
    doc.save(str(tmp_path / 'interface.xdat'))
    wait(lambda: not window.tasks)
    window.close(); app.processEvents()


def test_dat_manager_write_profile_and_restore(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat)
    window = Editor(settings)
    table = SysStrings(); table.load(str(ROOT / 'tests/fixtures/sysstring/fileedit.dat'))
    entry = window.strings.attach(table, 'English')
    dialog = StringsDialog(window)
    assert entry['info']['version'] == 413
    assert dialog.version.currentData() == -1 and dialog.write_profile.currentData() == 'preserve'
    assert dialog.save_button.isEnabled()
    dialog.version.setCurrentIndex(dialog.version.findData(121))
    dialog.write_profile.setCurrentIndex(dialog.write_profile.findData('standard'))
    assert dialog.save_button.isEnabled()
    dialog.deleteLater(); app.processEvents()
    window.close(); app.processEvents()
    restored = Editor(QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    errors = []; restored.error = errors.append
    deadline = time.monotonic() + 30
    while restored.strings.active is None or restored.tasks:
        app.processEvents(); time.sleep(.01)
        assert time.monotonic() < deadline, errors
    assert restored.strings.snapshot()[6000] == 'Test Button'
    assert restored.strings.active['info']['version'] == 413  # output combo was not a silent conversion
    restored.close(); app.processEvents()
