"""Detect a supported client and build Test in a new isolated workspace.

Requires a matching, already prepared compiler SDK. Client originals and SDK
inputs are never edited. Actual client execution remains a separate check.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dll/tools'))
sys.path.insert(0, str(ROOT/'uExplorer/python'))
from backend import Core, export_classes
from core_profiles import analyze
from prepare_native_profile import prepare
from compile_candidate import build
from package_candidate import digest

ADAPTERS = {
    'gracia_epilogue_0941cac5': ('gracia', 'ct24.XDAT', 'LoginMenuWnd', 'btnReplay', '--menu-bottom'),
    'clear_hf_0677e909': ('high_five', 'ct26.XDAT', 'LoginMenuWnd', 'btnReplay', '--menu-bottom'),
    'korean_modern_964ff724': ('korean', 'korea_native.XDAT', 'LogIn', 'Btn_Login', None),
    'japan_modern_74eac821': ('japan', 'essence_native.XDAT', 'UIEasyLoginWnd', 'loginButton', '--login-overlay'),
}


def inventory(directory):
    result = {}
    for path in directory.iterdir():
        if path.is_file():
            key = path.name.casefold()
            if key in result:
                raise ValueError('Ambiguous input filename: '+key)
            result[key] = path
    return result


def run(originals, dependencies, sdk, tools, native_build, library, out):
    originals, dependencies, sdk, tools, native_build, library, out = [p.resolve() for p in
        (originals, dependencies, sdk, tools, native_build, library, out)]
    local = ROOT/'test_interfaces/local'
    if out.exists() or out == local or not out.is_relative_to(local):
        raise ValueError('Output must be a new directory under test_interfaces/local')
    if any(out.is_relative_to(p) for p in (originals, dependencies, sdk, tools, native_build, library.parent)):
        raise ValueError('Output must be outside input directories')
    files = inventory(originals)
    dep_files = inventory(dependencies)
    for name in ('core.dll', 'core.u', 'interface.u', 'interface.xdat'):
        if name not in files:
            raise ValueError('Original input missing: '+name)
    analysis = analyze(files['core.dll'])
    analysis.pop('source', None)
    out.mkdir(parents=True)
    report = dict(schema=1, analysis=analysis, stages={}, completed=False,
                  client_runtime_verified=False,
                  original_files={n: digest(p) for n, p in files.items()
                                  if n in ('core.dll', 'core.u', 'interface.u', 'interface.xdat')})

    def save():
        (out/'pipeline.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    save()
    adapter = ADAPTERS.get(analysis['approved_profile'])
    if adapter is None:
        raise ValueError('No UI adapter for detected Core; inspect pipeline.json')
    profile, schema, window, button, mode = adapter
    report['profile'] = profile
    stage = 'dependencies'
    try:
        for name in ('engine.u', 'nwindow.u'):
            path = files.get(name, dep_files.get(name))
            if path is None:
                raise ValueError('Missing original dependency: '+name)
            report.setdefault('package_dependencies', {})[name] = digest(path)
        core = Core(library)
        dirs = [str(dependencies)]
        inspected = core.request(operation='inspect', path=str(files['interface.u']), dependencies=dirs)
        if any('Missing dependency:' in message for message in inspected.get('diagnostics', [])):
            raise ValueError('Unresolved package dependencies')
        report['stages'][stage] = 'passed'
        save()
        stage = 'export'
        exported = export_classes(core, files['interface.u'], inspected['package']['classes'],
                                  out/'export', dependencies=dirs, force=True)
        report['export_counts'] = exported['counts']
        if exported['counts']['partial'] or exported['counts']['failed']:
            raise ValueError('Incomplete export; inspect local export report')
        report['stages'][stage] = 'passed'
        save()
        stage = 'native'
        prepare(files['core.dll'], dependencies, native_build, out/'native')
        report['stages'][stage] = 'passed'
        save()
        stage = 'layout'
        command = [sys.executable, '-B', str(ROOT/'test_interfaces/ui_patch.py'),
                   '--input', str(files['interface.xdat']), '--schema', schema,
                   '--window', window, '--login-button', button,
                   '--out', str(out/'layout/Interface.xdat')]
        if mode:
            command.append(mode)
        with (out/'layout.log').open('wb') as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        report['stages'][stage] = 'passed'
        save()
        stage = 'compile_and_package'
        manifest = build(out/'export'/files['interface.u'].stem/'Classes', sdk, tools,
                         out/'layout', out/'native', out/'build', profile)
        report['stages'][stage] = 'passed'
        report['build_identity'] = manifest['build_identity']
        report['candidate_manifest_sha256'] = digest(out/'build/candidate/manifest.json')
        report['completed'] = True
        save()
        return report
    except Exception as error:
        report['stages'][stage] = 'failed'
        # Full error text may contain private paths and stays in local logs.
        report['error_type'] = type(error).__name__
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('originals', 'dependencies', 'sdk', 'tools', 'native-build', 'library', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.originals, args.dependencies, args.sdk, args.tools, args.native_build,
                 args.library, args.out)
    print(json.dumps({k: result[k] for k in ('profile', 'stages', 'completed', 'build_identity')}, indent=2))


if __name__ == '__main__':
    main()
