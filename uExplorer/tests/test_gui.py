"""Exercise actual widgets, background loading and code preview offscreen."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
INPUTS=Path(os.environ.get('UEXPLORER_GRACIA_SYSTEM', str(ROOT.parent/'local/gracia/System')))
sys.path[:0]=[str(ROOT/'python'),str(ROOT.parent/'interface_editor/dist/windows/packages')]
from PySide6.QtWidgets import QApplication
from app import MainWindow

app=QApplication([])
window=MainWindow()
window.populate(str(INPUTS))
def wait():
    deadline=time.monotonic()+90
    while window.worker is not None:
        app.processEvents()
        if time.monotonic()>deadline:raise AssertionError('Worker timeout')
        time.sleep(.01)
for i in range(window.files.count()):
    if window.files.item(i).text().casefold()=='interface.u':
        window.files.setCurrentRow(i);break
wait()
assert window.class_list.count()==239
window.class_list.setCurrentRow(0);wait()
assert window.code.isReadOnly() and 'class ' in window.code.toPlainText()
assert window.selected_button.isEnabled() and window.all_button.isEnabled()
window.class_filter.setText('LoginMenuWnd')
assert sum(not window.class_list.item(i).isHidden() for i in range(window.class_list.count()))==1
window.class_filter.clear()
# Repeatedly switch packages with an active class selection. Clearing the list
# must not start a stale preview and prevent the new inspect request.
for package in ('NWindow.u','Interface.u','NWindow.u','Interface.u'):
    for i in range(window.files.count()):
        if window.files.item(i).text().casefold()==package.casefold():
            window.files.setCurrentRow(i);break
    wait()
    expected=window.core.request(operation='inspect',path=window.package)['package']['classes']
    assert window.classes==expected,(package,window.log.toPlainText())
    assert window.class_list.count()==len(expected)
    window.class_list.setCurrentRow(0);wait()
    assert window.result is not None,window.log.toPlainText()
    assert window.result['class']==window.class_list.currentItem().text()
assert 'Traceback' not in window.log.toPlainText(),window.log.toPlainText()
window.populate(str(INPUTS))
assert window.worker is None and not window.classes and window.result is None
window.close();app.processEvents()
print('PASS GUI: load, preview, filtering, repeated package switches and directory reset')
