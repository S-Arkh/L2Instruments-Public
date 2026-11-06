"""Synthetic package -> native API/CLI -> widgets -> byte-exact source export."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

SOURCE = b'class PortableExample extends Object;\r\n// Synthetic portable fixture\r\n'


def compact(value):
    negative = value < 0
    value = abs(value)
    first = (value & 63) | (128 if negative else 0)
    value >>= 6
    result = bytearray([first | (64 if value else 0)])
    while value:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
    return bytes(result)


def fixture(path):
    names = ['None', 'Core', 'Class', 'TextBuffer', 'PortableExample', 'ScriptText']
    strings = b''.join(compact(len(name)+1)+name.encode()+b'\0'+struct.pack('<I', 0) for name in names)
    imports = compact(1)+compact(2)+struct.pack('<i', 0)+compact(3)
    # UClass fields: super, next, ScriptText, children; empty script and state metadata.
    cls = b'\0\0\x02\0\0\0'+bytes(8)+struct.pack('<i', 0)+bytes(26)
    text = b'\0'+bytes(8)+compact(len(SOURCE)+1)+SOURCE+b'\0'
    def entry(kind, outer, name, data, offset):
        return compact(kind)+compact(0)+struct.pack('<i', outer)+compact(name)+struct.pack('<I', 0)+compact(len(data))+compact(offset)
    exports = entry(0, 0, 4, cls, 1024)+entry(-1, 1, 5, text, 1024+len(cls))
    header = struct.pack('<IHHIiiiiii', 0x9e2a83c1, 123, 0, 0, len(names), 36,
                         2, 36+len(strings)+len(imports), 1, 36+len(strings))
    tables = header+strings+imports+exports
    path.write_bytes(tables+bytes(1024-len(tables))+cls+text)


def exercise(window, application, directory):
    from backend import export_classes
    from PySide6.QtCore import QSettings
    import backend
    root = Path(backend.__file__).resolve().parents[1]
    directory = Path(directory)
    package = directory/'Synthetic.u'
    fixture(package)
    core = window.core
    expected_core = root/'bin'/('uexplorer_core.dll' if sys.platform == 'win32' else 'libuexplorer_core.so')
    assert core.library.resolve() == expected_core.resolve(), core.library
    classes = core.request(operation='inspect', path=str(package))['package']['classes']
    assert len(classes) == 1 and classes[0]['name'] == 'PortableExample', classes
    result = core.request(operation='decompile', path=str(package), class_id=1)['result']
    assert result['status'] == 'source' and bytes.fromhex(result['raw_hex']) == SOURCE, result
    cli = root/'bin'/('uexplorer_cli.exe' if sys.platform == 'win32' else 'uexplorer_cli')
    response = subprocess.run([str(cli)], input=json.dumps(dict(operation='decompile', path=str(package), class_id=1)),
                              capture_output=True, text=True, encoding='utf-8', check=True, timeout=30)
    assert json.loads(response.stdout)['result'] == result
    invalid = directory/'Invalid.u'
    invalid.write_bytes(bytes(36))
    try:
        core.request(operation='inspect', path=str(invalid))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Invalid package accepted')
    invalid.unlink()
    export_classes(core, package, classes, directory/'export')
    assert (directory/'export/Synthetic/Classes/PortableExample.uc').read_bytes() == SOURCE
    try:
        export_classes(core, package, classes, directory/'export')
    except FileExistsError:
        pass
    else:
        raise AssertionError('Export silently overwrote an existing file')
    def wait():
        deadline = time.monotonic()+30
        while window.worker is not None:
            application.processEvents()
            if time.monotonic() > deadline:
                raise AssertionError('GUI worker timeout')
            time.sleep(.01)
    window.populate(str(directory))
    assert window.files.count() == 1
    window.files.setCurrentRow(0)
    wait()
    assert window.class_list.count() == 1, window.log.toPlainText()
    window.class_list.setCurrentRow(0)
    wait()
    assert window.code.toPlainText() == SOURCE.decode().replace('\r\n', '\n')
    assert window.code.isReadOnly() and window.selected_button.isEnabled()
    window.settings.sync()
    assert window.settings.status() == QSettings.Status.NoError
    if (root/'portable.json').exists():
        assert Path(window.settings.fileName()).resolve() == root/'data/settings.ini'
        saved = QSettings(str(root/'data/settings.ini'), QSettings.Format.IniFormat)
        assert saved.value('directory') == str(directory)
    return dict(native=True, cli=True, gui=True, export=True, settings=True)


def main():
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    with tempfile.TemporaryDirectory(prefix='uexplorer-smoke-') as temp:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, temp)
        application = QApplication([])
        window = MainWindow()
        window.show()
        try:
            print(json.dumps(exercise(window, application, temp)))
        finally:
            window.close()


if __name__ == '__main__':
    main()
