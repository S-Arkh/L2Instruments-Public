"""Create a native-compatible compiler SDK and recover the client's script sources."""
import argparse
from pathlib import Path
import shutil
import json
import hashlib
from verify_profile import ROOT, SYSTEM, verify
from local_paths import PACKAGES, INTERFACE_CLASSES, RUNTIME_SDK
from uc_declarations import normalize_file
from texture_assets import recover_imports
from extract_sources import extract
from compilation_sdk import object_with_runtime_storage
from ue2package import Package
from extract_sources import script_text
from sdk_enums import augment


def prepare(destination, runtime_sdk=None):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError(f'Destination already exists: {destination}')
    verify()
    runtime_sdk = Path(runtime_sdk) if runtime_sdk else RUNTIME_SDK
    manifest = json.loads((runtime_sdk / 'manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['files'].items():
        if hashlib.sha256((runtime_sdk / 'System' / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Runtime SDK checksum mismatch: {name}')
    source = INTERFACE_CLASSES
    if not source.is_dir():
        raise ValueError(f'Missing interface source directory: {source}')
    destination.mkdir(parents=True)
    system = destination / 'System'
    system.mkdir()
    for path in SYSTEM.iterdir():
        if path.is_file() and path.suffix.lower() in ('.dll', '.exe', '.u', '.int', '.ini'):
            # Core/NWindow are rebuilt; Engine/Editor use the verified SDK.
            if path.name.lower() not in ('core.u', 'engine.u', 'nwindow.u', 'interface.u', 'interface_old.u'):
                shutil.copy2(path, system / path.name)
    shutil.copytree(SYSTEM.parent / 'Core', destination / 'Core')
    (destination / 'nwindow/Inc').mkdir(parents=True)
    shutil.copytree(source, destination / 'Interface/Classes')
    report = {'declarations_moved': {}, 'constructive_header_modifiers': {}, 'normalization_errors': {}}
    packages = PACKAGES
    report['original_sources'] = {
        name: extract(packages / filename, destination / folder / 'Classes')
        for name, filename, folder in [('Engine', 'Engine.u', 'ClientReference/Engine'),
                                      ('NWindow', 'NWindow.u', 'nwindow'),
                                      ('Interface', 'interface.u', 'Interface')]
    }
    for name, source_report in report['original_sources'].items():
        if source_report['rejected'] or source_report['missing']:
            raise ValueError(f'Incomplete embedded sources for {name}: {source_report}')
    # Use the proven native-compatible Engine binary instead of instantiating
    # client Texture/Material layouts inside the old Engine.dll.
    report['engine_sdk_enums'] = augment(runtime_sdk / 'System/Engine.u', packages / 'Engine.u',
        system / 'Engine.u', ['Actor.EL2ObjectType', 'Interactions.EInputKey'])
    shutil.copy2(runtime_sdk / 'System/Editor.u', system / 'Editor.u')
    report['runtime_sdk'] = manifest
    report['runtime_core_sources'] = extract(runtime_sdk / 'System/Core.u', destination / 'Core/Classes')
    core_path = packages / 'Core.u'
    if not core_path.exists():
        core_path = packages.parent / 'Core.u'
    client_core = Package(core_path)
    runtime_core = Package(runtime_sdk / 'System/Core.u')
    _, client_object = client_core.find('Object.ScriptText')
    _, runtime_object = runtime_core.find('Object.ScriptText')
    _, client_text, _ = script_text(client_core, client_object)
    _, runtime_text, _ = script_text(runtime_core, runtime_object)
    object_text = object_with_runtime_storage(client_text, runtime_text)
    (destination / 'Core/Classes/Object.uc').write_bytes(object_text.encode('latin1'))
    report['core_object_storage'] = 'Runtime 2226 native fields; client types/constants/functions preserved'
    # The original Interface.u imports exactly Core, Engine and NWindow.
    (system / 'UE2Runtime.ini').write_text(
        '[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n'
        '[Core.System]\nPaths=../System/*.u\n\n'
        '[Editor.EditorEngine]\nCacheSizeMegs=256\n'
        'EditPackages=Core\nEditPackages=Engine\nEditPackages=NWindow\nEditPackages=Interface\n', encoding='ascii')
    for path in destination.glob('*/Classes/*.uc'):
        try:
            normalized = normalize_file(path)
            if normalized['moved']:
                report['declarations_moved'][str(path.relative_to(destination))] = normalized['moved']
            if normalized['constructive_removed']:
                report['constructive_header_modifiers'][str(path.relative_to(destination))] = normalized['constructive_removed']
        except (ValueError, IndexError) as error:
            report['normalization_errors'][str(path.relative_to(destination))] = str(error)
    report['engine_assets'] = recover_imports(
        packages / 'Engine.u', destination / 'ClientReference/Engine')
    (destination / 'source-preparation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if report['normalization_errors']:
        raise ValueError('Source normalization failed; inspect source-preparation.json')
    return system


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--runtime-sdk', type=Path)
    args = parser.parse_args()
    print(prepare(args.destination, args.runtime_sdk))
