"""Import external browser inputs into ignored workspaces; never edit a client."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO/'int64/tools'))


def named(folder, name):
    matches = [p for p in folder.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) != 1 or not matches[0].is_file():
        raise ValueError(f'Expected one {name} in {folder}')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['high-five', 'gracia'], required=True)
    parser.add_argument('--client-system', type=Path, required=True)
    parser.add_argument('--compiler-workspace', type=Path,
                        help='Prepared int64 workspace with System, Core and nwindow (HF only)')
    parser.add_argument('--launcher-dir', type=Path, help='Built ucc64.exe and Ucc64Bridge.dll directory')
    args = parser.parse_args()
    client = args.client_system.resolve()
    if args.profile == 'high-five' and not args.compiler_workspace:
        parser.error('high-five requires --compiler-workspace')
    base = ROOT/'archive/addWeb' if args.profile == 'high-five' else ROOT/'profiles/gracia'
    inputs = base/'inputs'
    if inputs.exists():
        raise ValueError(f'Inputs already exist: {inputs}; keep a separate copy before rebuilding')
    names = ['Core.dll','Engine.dll','D3DDrv.dll','NWindow.dll','Core.u','Engine.u','NWindow.u','Interface.u','Interface.xdat']
    if args.profile == 'high-five':
        names.append('ExtensionL2.u')
    sources = {name: named(client, name) for name in names}
    inputs.mkdir(parents=True)
    for name, source in sources.items():
        shutil.copy2(source, inputs/name)
    if args.launcher_dir:
        (ROOT/'toolchain').mkdir(exist_ok=True)
        for name in ['ucc64.exe','Ucc64Bridge.dll']:
            shutil.copy2(args.launcher_dir/name, ROOT/'toolchain'/name)
    if args.profile == 'high-five':
        from ue2package import Package
        workspace = base/'workspace'
        for folder in ['System','Core','nwindow']:
            shutil.copytree(args.compiler_workspace/folder, workspace/folder)
        # The original HF workflow expects a matching, already patched Core and ExtensionL2 API package.
        (workspace/'System/ExtensionL2.u').write_bytes(Package(inputs/'ExtensionL2.u').data)
        ini = workspace/'System/UE2Runtime.ini'
        text = ini.read_text()
        if 'EditPackages=ExtensionL2' not in text:
            text = text.replace('EditPackages=Interface', 'EditPackages=ExtensionL2\nEditPackages=Interface')
        ini.write_text(text)
        (base/'result/system').mkdir(parents=True)
        spec = importlib.util.spec_from_file_location('browser_ui', base/'prepare_ui.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
    print('Prepared local inputs:', base)


if __name__ == '__main__':
    main()
