"""Create a fresh, isolated UCC smoke workspace. Never changes the source compiler."""
import argparse
from pathlib import Path
import shutil
from verify_profile import ROOT, SYSTEM, verify


def prepare(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError(f'Destination already exists: {destination}; choose a new directory')
    verify()
    source_core = SYSTEM.parent / 'Core'
    if not (source_core / 'Classes/Object.uc').is_file():
        raise ValueError(f'Missing compiler Core sources: {source_core}')
    destination.mkdir(parents=True)
    # Copy only required runtime assets, not legacy batch files which delete .u.
    system = destination / 'System'
    system.mkdir()
    for path in SYSTEM.iterdir():
        if path.is_file() and path.suffix.lower() in ('.dll', '.exe', '.u', '.int', '.ini'):
            if path.name.lower() != 'core.u':  # recompile Object.uc with INT64 declarations
                shutil.copy2(path, system / path.name)
    shutil.copytree(source_core, destination / 'Core')
    shutil.copytree(ROOT / 'smoke/Int64Smoke', destination / 'Int64Smoke')
    (system / 'UE2Runtime.ini').write_text(
        '[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n'
        '[Core.System]\nPaths=../System/*.u\n\n'
        '[Editor.EditorEngine]\nCacheSizeMegs=256\n'
        'EditPackages=Core\nEditPackages=Int64Smoke\n', encoding='ascii')
    return system


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(prepare(args.destination))
