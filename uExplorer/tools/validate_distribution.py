"""Check a disposable extracted bundle, including its actual Start.cmd entrypoint."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from package_windows import digest, file_manifest

SHIM = '''import json, os, runpy, traceback
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
original = QApplication.exec
def execute(self):
    def finish():
        try:
            window = next(w for w in self.topLevelWidgets() if hasattr(w, 'core'))
            smoke = runpy.run_path(os.environ['UEX_SMOKE'])
            result = smoke['exercise'](window, self, os.environ['UEX_WORK'])
            Path(os.environ['UEX_REPORT']).write_text(json.dumps(result), encoding='utf-8')
            window.close()
        except Exception:
            Path(os.environ['UEX_REPORT']).write_text(json.dumps({'error': traceback.format_exc()}), encoding='utf-8')
        finally:
            self.quit()
    QTimer.singleShot(0, finish)
    return original()
QApplication.exec = execute
'''


def isolated_environment():
    env = {name.upper(): value for name, value in os.environ.items()}
    for name in list(env):
        if name.startswith(('PYTHON', 'QT_', 'PYSIDE', 'UEXPLORER')):
            del env[name]
    windows = Path(env['SYSTEMROOT'])
    env.update(PATH=os.pathsep.join((str(windows/'System32'), str(windows))), QT_QPA_PLATFORM='offscreen')
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, help='Disposable freshly extracted bundle')
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    info_path = bundle/'BUILDINFO.json'
    info_hash = digest(info_path)
    info = json.loads(info_path.read_text(encoding='utf-8'))
    if file_manifest(bundle) != info['files']:
        raise ValueError('Bundle manifest mismatch')
    shim = bundle/'runtime/sitecustomize.py'
    settings = bundle/'data/settings.ini'
    if shim.exists() or settings.exists():
        raise ValueError('Validation requires a fresh disposable bundle')
    with tempfile.TemporaryDirectory(prefix='uexplorer-portable-') as temp:
        report = Path(temp)/'result.json'
        env = isolated_environment()
        env.update(UEX_SMOKE=str(Path(__file__).resolve().parents[1]/'tests/portable_smoke.py'),
                   UEX_WORK=temp, UEX_REPORT=str(report), UEXPLORER_CORE=str(Path(temp)/'wrong.dll'))
        try:
            shim.write_text(SHIM, encoding='utf-8')
            subprocess.run(f'"{env["COMSPEC"]}" /d /c ""{bundle / "Start.cmd"}""',
                           cwd=temp, env=env, stdin=subprocess.DEVNULL, check=True, timeout=90)
            result = json.loads(report.read_text(encoding='utf-8'))
            if not all(result.get(key) is True for key in ('native', 'cli', 'gui', 'export', 'settings')):
                raise ValueError(result)
            print('PASS Start.cmd: ' + json.dumps(result))
        finally:
            shim.unlink(missing_ok=True)
            settings.unlink(missing_ok=True)
    if file_manifest(bundle) != info['files'] or digest(info_path) != info_hash:
        raise ValueError('Startup modified distribution files')


if __name__ == '__main__':
    main()
