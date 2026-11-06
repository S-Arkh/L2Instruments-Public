"""Exercise Start.cmd in a disposable bundle with isolated GUI settings."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


SHIM = '''from pathlib import Path
import json, os, sys
from PySide6.QtCore import QSettings, QStandardPaths, QTimer
from PySide6.QtWidgets import QApplication
bundle = Path(sys.executable).resolve().parent.parent
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, os.environ['PROBE_SETTINGS'])
QStandardPaths.setTestModeEnabled(True)
original = QApplication.exec
def execute(self):
    def finish():
        try:
            import _interface_core, schema_catalog
            window = next(w for w in self.topLevelWidgets() if hasattr(w, 'schemas'))
            result = dict(start_cmd=True, versions=window.version.count(),
                          startup_cache_empty=not window.schemas._cache,
                          bundled_core=Path(_interface_core.__file__).resolve().is_relative_to(bundle),
                          bundled_loader=Path(schema_catalog.__file__).resolve().is_relative_to(bundle),
                          schema_errors=len(window.schema_errors))
            Path(os.environ['PROBE_REPORT']).write_text(json.dumps(result), encoding='utf-8')
            window.close()
        finally:
            self.quit()
    QTimer.singleShot(1000, finish)
    return original()
QApplication.exec = execute
'''


def isolated_environment():
    env = {name.upper(): value for name, value in os.environ.items()}
    for name in list(env):
        if name.upper().startswith(('PYTHON', 'QT_', 'PYSIDE')):
            del env[name]
    windows = Path(env['SYSTEMROOT'])
    env.update(PATH=os.pathsep.join((str(windows / 'System32'), str(windows))),
               PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    shim = bundle / 'runtime/sitecustomize.py'
    if shim.exists():
        raise ValueError('Unexpected existing startup instrumentation')
    with tempfile.TemporaryDirectory(prefix='entrypoint-') as temp:
        report = Path(temp) / 'result.json'
        env = isolated_environment()
        env.update(PROBE_SETTINGS=temp, PROBE_REPORT=str(report))
        try:
            shim.write_text(SHIM, encoding='utf-8')
            subprocess.run(f'"{env["COMSPEC"]}" /d /c ""{bundle / "Start.cmd"}""',
                           cwd=temp, env=env, stdin=subprocess.DEVNULL, timeout=60, check=True)
            result = json.loads(report.read_text(encoding='utf-8'))
            assert result['versions'] == 26 and result['schema_errors'] == 0, result
            assert all(result[k] for k in ('start_cmd', 'startup_cache_empty', 'bundled_core', 'bundled_loader'))
            print(json.dumps(result))
        finally:
            shim.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
