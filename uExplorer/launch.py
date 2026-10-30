"""Bootstrap regular Python or the existing embedded runtime without modifying it."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'python'))
if sys.platform=='win32':
    packages=ROOT.parent/'interface_editor/dist/windows/packages'
    if packages.is_dir():sys.path.append(str(packages))
from app import main
raise SystemExit(main())
