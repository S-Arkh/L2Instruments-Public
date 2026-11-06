"""Run with a portable bundle's Python; validate isolated imports and editor workflows."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', action='append', default=[], metavar='SCHEMA=FILE')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(sys.executable).resolve().parent.parent
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    # The native module must load without Qt first adding DLL search directories.
    import _interface_core
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtWidgets import QApplication, QProgressDialog
    import PySide6
    import schema_catalog
    import main as editor_module
    import schema_dialog
    from schema_tools import draft_package, import_package, export_package
    for module in (PySide6, _interface_core, schema_catalog, editor_module):
        assert Path(module.__file__).resolve().is_relative_to(bundle), module.__name__
    assert not (bundle / 'schemas/schemas.json').exists()
    manifest = json.loads((bundle / 'BUILDINFO.json').read_text(encoding='utf-8'))
    files = {**manifest['application_files'], **manifest.get('runtime_files', {}),
             'app/' + manifest['core_module']: manifest['core_sha256']}
    for name, digest in files.items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest, name
    QStandardPaths.setTestModeEnabled(True)
    app = QApplication.instance() or QApplication([])
    report = {'isolated_imports': True, 'manifest_verified': True, 'samples': []}
    with tempfile.TemporaryDirectory(prefix='interface-portable-validation-') as directory:
        folder = Path(directory)
        window = editor_module.Editor(QSettings(str(folder / 'settings.ini'), QSettings.Format.IniFormat))
        window.user_schema_directory = folder / 'schemas'
        window.reload_schemas()
        errors = []
        window.error = errors.append
        window.discard_confirmed = lambda **kwargs: True
        def wait():
            deadline = time.monotonic() + 120
            while window.busy or window.tasks:
                app.processEvents()
                if time.monotonic() > deadline:
                    raise TimeoutError('Editor operation timed out')
                time.sleep(.005)
            assert not errors, errors
        try:
            doc = _interface_core.Document(window.schemas.text('ct26.XDAT'))
            doc.create('ct26.XDAT')
            windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
            doc.add_configured(windows, 'ct26.Window', {'name': 'PortableFixture'})
            source = folder / 'fixture.xdat'
            source.write_bytes(doc.serialize())
            window.load_file(str(source), 'ct26.XDAT')
            wait()
            node = window.document.search('PortableFixture')['matches'][0]
            window.mutate(lambda: window.document.set(node, 'name', 'PortableEdited'))
            wait()
            changed = window.document.serialize()
            window.history(False)
            wait()
            assert window.document.serialize() == source.read_bytes()
            window.history(True)
            wait()
            assert window.document.serialize() == changed
            window.save_file()
            wait()
            assert source.read_bytes() == changed
            exported = folder / 'fixture.json'
            window.document.export_json(str(exported))
            window.load_file(str(exported), None)
            wait()
            assert window.document.serialize() == changed
            report['edit_undo_redo_save_json'] = True

            shown = []
            original_show = schema_dialog.show_results
            schema_dialog.show_results = lambda *values: shown.append(values[4])
            try:
                schema_dialog.analyze(window, str(source), 'ct0.XDAT', 'validation')
                wait()
                assert any(r['schema'] == 'ct26.XDAT' and r['compatible'] for r in shown[0])
                shown.clear()
                schema_dialog.analyze(window, str(source), 'ct0.XDAT', 'validation')
                # A previous dialog can still be awaiting Qt's deferred deletion.
                window.findChildren(QProgressDialog)[-1].canceled.emit()
                wait()
                assert not shown
            finally:
                schema_dialog.show_results = original_show
            report['detection_and_cancel'] = True

            package = draft_package(window.schemas.text('ct26.XDAT'), 'ct26.XDAT', 'Portable custom')
            package_file = folder / 'package.json'
            package_file.write_text(json.dumps(package), encoding='utf-8')
            import_package(package_file, window.user_schema_directory, window.schemas)
            window.reload_schemas()
            root = package['versions'][0][1]
            assert export_package(window.schemas.text(root), root)['records'] == package['records']
            custom = _interface_core.Document(window.schemas.text(root))
            custom.create(root)
            assert custom.serialize()
            report['user_package_import_export'] = True

            old = window.document
            malformed = folder / 'unknown.json'
            malformed.write_text('{"schema":"missing.XDAT"}')
            window.load_file(str(malformed), None)
            deadline = time.monotonic() + 30
            while window.busy or window.tasks:
                app.processEvents()
                assert time.monotonic() < deadline
                time.sleep(.005)
            assert errors and window.document is old
            errors.clear()
            report['failed_open_preserves_document'] = True

            for sample in args.sample:
                schema, separator, filename = sample.partition('=')
                if not separator:
                    raise ValueError('--sample requires SCHEMA=FILE')
                original = Path(filename).read_bytes()
                window.load_file(filename, schema)
                wait()
                assert window.document.serialize() == original
                target = folder / 'sample.json'
                window.document.export_json(str(target))
                window.load_file(str(target), None)
                wait()
                assert window.document.serialize() == original
                report['samples'].append({'schema': schema, 'binary_roundtrip': True, 'json_roundtrip': True})
        finally:
            window.close()
            app.processEvents()
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
