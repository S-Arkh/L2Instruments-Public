"""Detect a known Core profile and validate an isolated native-only bundle.

Unknown inputs receive a diagnostic report, not a speculative patch. Client
packages and UI integration are separate from these loader/VM checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from core_profiles import analyze
from patch_core import patch_core


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(core, dependencies, native, out):
    core, dependencies, native, out = [p.resolve() for p in (core, dependencies, native, out)]
    if out == core.parent or out.is_relative_to(core.parent) or out.is_relative_to(dependencies) or out.is_relative_to(native):
        raise ValueError('Output must be outside all input directories')
    if out.exists():
        raise ValueError('Output directory must be new')
    analysis = analyze(core)
    analysis.pop('source', None)
    required = ('ExtensionL2.dll', 'client_link_probe.exe', 'extension_probe.exe')
    for name in required:
        if not (native/name).is_file():
            raise ValueError('Missing native build file: ' + name)
    out.mkdir(parents=True)
    report = dict(schema=1, analysis=analysis, tests={}, native_bundle_verified=False,
                  client_ui_tested=False, package_compilation_tested=False)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    save()
    if not analysis['approved_profile']:
        raise ValueError('Unknown Core profile; inspect report.json for exports and ABI requirements')
    system = out/'System'
    system.mkdir()
    seen = set()
    for path in dependencies.iterdir():
        if not path.is_file() or path.suffix.lower() not in ('.dll', '.int'):
            continue
        name = path.name.casefold()
        if name in seen:
            raise ValueError('Ambiguous dependency filename: ' + name)
        seen.add(name)
        if name not in ('core.dll', 'extensionl2.dll'):
            shutil.copy2(path, system/path.name)
    engine = next((p for p in system.iterdir() if p.name.casefold() == 'engine.dll'), None)
    if engine is None:
        raise ValueError('Engine.dll dependency missing')
    for name in required:
        shutil.copy2(native/name, system/name)
    report['tools'] = {name: digest(system/name) for name in required}
    report['patch'] = patch_core(core, system/'Core.dll')
    save()
    commands = {
        'loader': [system/'client_link_probe.exe', system/'Core.dll', engine, system],
        'vm': [system/'extension_probe.exe', system/'Core.dll', system, system/'ExtensionL2.dll', 'patched'],
    }
    # Co-location is intentional: Windows searches the executable directory
    # before SetDllDirectory. Otherwise two ExtensionL2 modules can be loaded.
    for name, command in commands.items():
        try:
            result = subprocess.run([str(arg) for arg in command], cwd=system,
                                    capture_output=True, timeout=90)
            (out/(name+'.log')).write_bytes(result.stdout+result.stderr)
            report['tests'][name] = dict(exit=result.returncode, passed=result.returncode == 0)
        except subprocess.TimeoutExpired:
            report['tests'][name] = dict(passed=False, timeout=True)
        save()
        if not report['tests'][name]['passed']:
            raise RuntimeError(name+' check failed; inspect the local log')
    bundle = out/'client'
    bundle.mkdir()
    for name in ('Core.dll', 'ExtensionL2.dll'):
        shutil.copy2(system/name, bundle/name)
    report['files'] = {p.name: digest(p) for p in bundle.iterdir()}
    report['native_bundle_verified'] = True
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('core', 'dependencies', 'native-build', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.core, args.dependencies, args.native_build, args.out)
    print(json.dumps(dict(profile=report['analysis']['approved_profile'],
                          tests=report['tests'], native_bundle_verified=True), indent=2))


if __name__ == '__main__':
    main()
