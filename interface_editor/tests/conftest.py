"""Qt setup shared by GUI and image-rendering tests."""
import os
from pathlib import Path
import sys
from synthetic_fixtures import generate


def pytest_sessionstart(session):
    generate()


# Windows' offscreen Qt plugin does not discover the system fonts on its own.
# Without them drawText produces no glyphs, hiding changes of SysString captions.
# Set this before test modules create QApplication; keep explicit overrides.
if sys.platform == 'win32':
    fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    if fonts.is_dir():
        os.environ.setdefault('QT_QPA_FONTDIR', str(fonts))
