"""Check indexed UFunction declarations in the supplied client packages."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2] / 'int64'
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package
from local_paths import PACKAGES


def audit(index=4000):
    if not 0x100 <= index < 4096:
        raise ValueError('Choose an extended native index in 256..4095')
    client = PACKAGES
    found = []
    for relative in ('Core.u', 'Engine.u', 'NWindow.u', 'UWindow.u', 'interface.u'):
        package = Package(client / relative)
        count = 0
        for i, entry in enumerate(package.exports, 1):
            if package.ref(entry.cls) != 'Core.Function':
                continue
            function = package.function(package.ref(i))
            if function['native']:
                count += 1
            if function['native'] == index:
                found.append(f'{relative}: {function["name"]}')
        print(f'{relative}: checked {count} indexed native declarations')
    if found:
        raise ValueError('Native index already declared: ' + '; '.join(found))
    print(f'Index {index} is unused in these packages. The DLL also checks the live GNatives slot.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=int, default=4000)
    audit(parser.parse_args().index)
