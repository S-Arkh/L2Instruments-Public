"""Prepare an isolated compiler workspace for ExtensionL2.u."""
import argparse
from pathlib import Path
import shutil
import sys

EXAMPLE = Path(__file__).resolve().parents[1]
ROOT = EXAMPLE.parent / 'int64'
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_smoke import prepare


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    system = prepare(args.destination)
    shutil.copytree(EXAMPLE / 'ExtensionL2', system.parent / 'ExtensionL2')
    ini = system / 'UE2Runtime.ini'
    ini.write_text(ini.read_text(encoding='ascii').replace('EditPackages=Int64Smoke', 'EditPackages=ExtensionL2'),
                   encoding='ascii')
    print(system)
