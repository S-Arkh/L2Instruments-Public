"""Build the Credit-button file-I/O Interface in an isolated compiler workspace."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
COMPILER = PROJECT / 'int64'
DLL = PROJECT / 'dll'
sys.path.insert(0, str(COMPILER / 'tools'))
sys.path.insert(0, str(DLL / 'tools'))
from prepare_interface import prepare
from package_client import package_client
from compare_interface import compare
from check_uc import check as check_uc
from check_installation import digest, local_file
from patch_core import patch_core
from validate_bundle import validate
from ue2package import Package
from local_paths import PACKAGES, CLEAR_HF_SYSTEM


def initialize_sources(prepared):
    classes = HERE / 'src/Classes'
    if classes.exists():
        return classes
    shutil.copytree(prepared, classes)
    target = classes / 'LoginMenuWnd.uc'
    data = target.read_bytes()
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    old = newline.join([b'\t\tSetUIState("CreditState");', b'\t\tInitCreditState();'])
    new = newline.join([
        b'\t\tif (!class\'ExtensionL2API\'.static.WriteTextFile("test.txt", "", class\'ExtensionL2Tests\'.static.Int64Report()))',
        b'\t\t\tShowMessageInLogin("Cannot write test.txt. Error: " $ string(class\'ExtensionL2API\'.static.GetFileError()));',
    ])
    if data.count(old) != 1:
        raise ValueError('Expected exactly one original Credit handler')
    target.write_bytes(data.replace(old, new))
    return classes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-build', type=Path, default=DLL / 'build/Release')
    parser.add_argument('--launcher', type=Path, default=COMPILER / 'dist/win32/ucc64.exe')
    parser.add_argument('--client-core', type=Path, default=CLEAR_HF_SYSTEM / 'Core.dll')
    parser.add_argument('--reference-package', type=Path, default=PACKAGES / 'Interface.u')
    parser.add_argument('--client-system', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=HERE / 'build')
    parser.add_argument('--out', type=Path, default=HERE / 'result')
    parser.add_argument('--wine', type=Path)
    parser.add_argument('--replace', action='store_true', help='Back up and replace an existing result directory after validation')
    args = parser.parse_args()
    native, work, out, system, original = [p.resolve() for p in (
        args.native_build, args.work, args.out, args.client_system, args.client_core)]
    if work.exists():
        raise ValueError('Choose a new --work directory')
    for name in ('Core.dll', 'ExtensionL2.dll', 'Interface.u', 'ExtensionL2.u', 'bundle.json'):
        if (out / name).exists() and not args.replace:
            raise ValueError('Output already contains build artifacts; choose a new --out')
    reference = args.reference_package.resolve()
    if digest(local_file(system, 'Interface.u')) != digest(reference):
        raise ValueError('Target Interface differs from the source profile used by this demo')
    staged_system = prepare(work)
    classes = initialize_sources(work / 'Interface/Classes')
    shutil.copytree(classes, work / 'Interface/Classes', dirs_exist_ok=True)

    def winpath(path):
        path = Path(path).resolve()
        return str(path) if os.name == 'nt' else 'Z:' + str(path).replace('/', '\\')

    generator = native / 'extension_bindings.exe'
    command = ([str(args.wine.resolve()), winpath(generator)] if args.wine else [str(generator)])
    command += [winpath(native / 'ExtensionL2.dll'),
                winpath(DLL / 'ExtensionL2/Classes/ExtensionL2API.uc'), winpath(work / 'bindings.json')]
    subprocess.run(command, check=True, timeout=120)
    shutil.copytree(DLL / 'ExtensionL2', work / 'ExtensionL2')
    ini = staged_system / 'UE2Runtime.ini'
    ini.write_text(ini.read_text().replace('EditPackages=Interface', 'EditPackages=ExtensionL2\nEditPackages=Interface'), encoding='ascii')
    command = [sys.executable, '-B', str(COMPILER / 'tools/run_compile.py'), str(staged_system),
               '--launcher', str(args.launcher.resolve())]
    if args.wine:
        command += ['--wine', str(args.wine.resolve())]
    subprocess.run(command, check=True)
    check_uc(staged_system / 'ExtensionL2.u', work / 'compiled-call.bin', work / 'bindings.json')
    package = Package(staged_system / 'Interface.u')
    function = package.function('LoginMenuWnd.OnClickButton')
    rows = function['instructions']
    call = next(i for i, r in enumerate(rows) if r['kind'] == 'native' and r['index'] == 4007)
    if [r.get('value') for r in rows[call + 1:call + 3]] != ['test.txt', '']:
        raise ValueError('Unexpected Credit output path')
    if not (any(r['kind'] == 'object' and r.get('value', '').casefold() == 'extensionl2.extensionl2tests' for r in rows)
            and any(r['kind'] == 'virtual_call' and r.get('value', '').casefold() == 'int64report' for r in rows)):
        raise ValueError('Credit does not call the int64 report')
    comparison = compare(reference, staged_system / 'Interface.u')
    (work / 'interface-comparison.json').write_text(json.dumps(comparison, indent=2), encoding='utf-8')
    changed = {name.casefold() for name in comparison['changed_functions']}
    if changed != {'loginmenuwnd.onclickbutton'} or any(comparison[key] for key in (
        'decode_errors', 'missing_functions', 'extra_functions', 'function_metadata_differences',
        'class_metadata_differences', 'state_differences')):
        raise ValueError('Unexpected Interface changes; see interface-comparison.json')

    bundle = work / 'result'
    patch_core(original, bundle / 'Core.dll')
    shutil.copy2(native / 'ExtensionL2.dll', bundle / 'ExtensionL2.dll')
    for name in ('Interface', 'ExtensionL2'):
        package_client(staged_system / (name + '.u'), bundle / (name + '.u'), reference)
    manifest = validate(original, bundle, system, native, work / 'compiled-call.bin', args.wine)
    manifest['bundle_files']['Interface.u'] = digest(bundle / 'Interface.u')
    manifest['interface_demo'] = dict(button='LoginMenuWnd.btnCredit', file='test.txt', report='ExtensionL2Tests.Int64Report',
        changed_functions=list(comparison['changed_functions']),
        source_files={p.name: digest(p) for p in sorted(classes.glob('*.uc'))})
    (bundle / 'bundle.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    shutil.copy2(work / 'bindings.json', bundle / 'bindings.json')
    shutil.copy2(work / 'interface-comparison.json', bundle / 'interface-comparison.json')
    shutil.copy2(work / 'compile.log', bundle / 'compile.log')
    for name in ('compiled-call.bin',):
        shutil.copy2(work / name, bundle / name)
    if (native / 'BUILDINFO.json').exists():
        shutil.copy2(native / 'BUILDINFO.json', bundle / 'BUILDINFO.json')
    if out.exists() and args.replace:
        backup = out.parent / 'backups' / (out.name + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.parent.mkdir(parents=True, exist_ok=True)
        out.rename(backup)
        print(f'Previous output preserved: {backup}')
    shutil.copytree(bundle, out, dirs_exist_ok=True)
    print(f'Published verified DLL/UC bundle: {out}')
    print(f'Interface source classes: {classes}')


if __name__ == '__main__':
    main()
