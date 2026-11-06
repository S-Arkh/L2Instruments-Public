"""Read-only client inventory for isolated test-interface preparation.

Logical client names do not approve a native ABI or enable compiler extensions.
The native catalog and actual package inheritance are checked independently.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dll/tools'))
sys.path.insert(0, str(ROOT/'uExplorer/python'))
from core_profiles import analyze
from backend import Core

PROFILES = {
    'gracia': {'menu': 'LoginMenuWnd', 'login': 'LoginMenuWnd'},
    'high_five': {'menu': 'LoginMenuWnd', 'login': 'LoginMenuWnd'},
    'japan': {'menu': 'LogInMenu', 'login': 'Login'},
    'korean': {'menu': 'LogInMenu', 'login': 'Login'},
}


def inventory(profile, system, library):
    files = {}
    for path in system.iterdir():
        if path.is_file():
            key = path.name.casefold()
            if key in files:
                raise ValueError('Ambiguous case-insensitive client filename: ' + key)
            files[key] = path
    required = ('core.dll', 'core.u', 'engine.u', 'nwindow.u', 'interface.u')
    missing = sorted(set(required) - files.keys())
    if missing:
        raise ValueError('Missing client inputs: ' + ', '.join(missing))
    native = analyze(files['core.dll'])
    native.pop('source', None)
    core = Core(library.resolve())
    summary = core.request(operation='inspect', path=str(files['interface.u'].resolve()))['package']
    classes = {row['name'].casefold(): row for row in summary['classes']}
    selected = {}
    for role, name in PROFILES[profile].items():
        row = classes.get(name.casefold())
        if row is None:
            raise ValueError('Expected profile class missing: ' + name)
        selected[role] = {'name': row['name'], 'super': row['super']}
    return dict(schema=1, profile=profile,
                inputs={name: hashlib.sha256(files[name].read_bytes()).hexdigest() for name in required},
                login_classes=selected, native_analysis=native,
                report_file='test.txt', report_directory='System',
                 button_position=('bottom_right_menu' if profile in ('gracia', 'high_five')
                                  else 'login_screen_overlay' if profile == 'japan'
                                  else 'left_of_login'),
                native_catalog_match=native['approved_profile'] is not None,
                ui_integration_verified=False, runtime_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--client-system', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    local = ROOT/'test_interfaces/local'
    if not out.is_relative_to(local) or out == local:
        parser.error('Output must be a new file beneath test_interfaces/local')
    report = inventory(args.profile, args.client_system.resolve(), args.library)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in
                      ('profile', 'login_classes', 'native_catalog_match', 'runtime_tested')}, indent=2))


if __name__ == '__main__':
    main()
