"""Bootstrap regular Python or the existing embedded runtime without modifying it."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'python'))
if sys.platform=='win32':
    packages=ROOT.parent/'interface_editor/dist/windows/packages'
    if packages.is_dir():sys.path.append(str(packages))


def main():
    if sys.version_info < (3, 10):
        print('uExplorer requires Python 3.10 or newer.')
        return 1
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except (ImportError, OSError) as error:
        print('uExplorer: PySide6 could not be loaded: ' + str(error))
        print('Use run.cmd to select a working environment, or install requirements.txt with this Python.')
        return 1
    if '--check-runtime' in sys.argv[1:]:
        print('Python: ' + sys.executable)
        print('Qt: ' + QtCore.qVersion())
        return 0
    from app import main as run_app
    return run_app()


if __name__ == '__main__':
    raise SystemExit(main())
