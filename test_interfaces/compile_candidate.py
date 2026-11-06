"""Compile an isolated Korean Test interface and assemble verified companion artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from package_candidate import assemble, digest
from script_patch import patch_click

ROOT = Path(__file__).resolve().parents[1]


def build(sources, sdk, tools, layout, native, out, profile='korean'):
    if profile not in ('korean', 'gracia', 'high_five', 'japan'):
        raise ValueError('No verified compilation adapter for this profile')
    modern = profile in ('korean', 'japan')
    login_class = 'Login.uc' if modern else 'LoginMenuWnd.uc'
    sources, sdk, tools, layout, native, out = [
        p.resolve() for p in (sources, sdk, tools, layout, native, out)]
    local = ROOT/'test_interfaces/local'
    if not out.is_relative_to(local) or out == local or out.exists():
        raise ValueError('Output must be a new directory beneath test_interfaces/local')
    if any(out.is_relative_to(p) for p in (sources, sdk, tools, layout, native)):
        raise ValueError('Output must be outside input directories')
    inputs = {p.name: p for p in sources.glob('*.uc')}
    if login_class not in inputs:
        raise ValueError('Missing original exported ' + login_class)
    additions = [ROOT/'dll/ExtensionL2/Classes/ExtensionL2API.uc',
                 *(ROOT/'test_interfaces/scripts').glob('*.uc')]
    if modern:
        additions.extend((ROOT/'test_interfaces/scripts_modern').glob('*.uc'))
    if profile == 'japan':
        additions.extend((ROOT/'test_interfaces/scripts_japan').glob('*.uc'))
    for path in additions:
        if path.name.casefold() in {name.casefold() for name in inputs}:
            raise ValueError('Test class collision: ' + path.name)
        inputs[path.name] = path
    if len({name.casefold() for name in inputs}) != len(inputs):
        raise ValueError('Ambiguous source filenames')
    sdk_files = {p.name: p for p in sdk.iterdir() if p.is_file() and
                 p.suffix.lower() in ('.u', '.dll', '.exe', '.ini', '.int') and
                 p.name.casefold() != 'interface.u'}
    if len({name.casefold() for name in sdk_files}) != len(sdk_files):
        raise ValueError('Ambiguous SDK filenames')
    if not {'core.u', 'engine.u', 'nwindow.u'} <= {n.casefold() for n in sdk_files}:
        raise ValueError('SDK must contain matching Core, Engine and NWindow packages')
    tool_files = {name: tools/name for name in ('ucc64.exe', 'Ucc64Bridge.dll')}
    # Named hashes avoid ambiguous concatenation and include handler/tool/SDK changes.
    provenance = dict(sources={n: digest(p) for n, p in sorted(inputs.items())},
                      sdk={n: digest(p) for n, p in sorted(sdk_files.items())},
                      tools={n: digest(p) for n, p in tool_files.items()},
                      generator={n: digest(ROOT/'test_interfaces'/n) for n in
                                 ('script_patch.py', 'compile_candidate.py')},
                      profile=profile,
                      options=(['client-array-sort', 'scoped-enum-casts'] +
                               ['client-enum-profile=korea290']
                               if modern else []))
    identity = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    text = {name: path.read_text(encoding='utf-8-sig') for name, path in inputs.items()}
    if profile == 'japan':
        text['CompilerTestWnd.uc'] = text['CompilerTestWnd.uc'].replace('__COMPILER_BUILD_ID__', identity)
    else:
        text[login_class] = patch_click(text[login_class], profile, identity, modern)
    out.mkdir(parents=True)
    work = out/'compile'
    system, classes, launcher = work/'System', work/'Interface/Classes', work/'tools'
    for directory in (system, classes, launcher, work/'Interface/Inc'):
        directory.mkdir(parents=True)
    for name, path in sdk_files.items():
        shutil.copy2(path, system/name)
    # Only build Interface; copied dependency packages are loaded, never rebuilt.
    config = next((p for p in system.iterdir() if p.name.casefold() == 'ue2runtime.ini'),
                  system/'UE2Runtime.ini')
    config.write_text('[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n'
                      '[Core.System]\nPaths=../System/*.u\n\n'
                      '[Editor.EditorEngine]\nCacheSizeMegs=256\n'
                      'EditPackages=Core\nEditPackages=Engine\n'
                      'EditPackages=NWindow\nEditPackages=Interface\n', encoding='ascii')
    for name, path in tool_files.items():
        shutil.copy2(path, launcher/name)
    for name, source in text.items():
        (classes/name).write_text(source, encoding='utf-16')
    (out/'inputs.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
    report = dict(profile=profile, build_identity=identity, compiled=False,
                  runtime_tested=False, compiler_exit=None)

    def save():
        (work/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    save()
    env = os.environ.copy()
    for key in ('UCC64_CLIENT_ARRAY_SORT', 'UCC64_CLIENT_ENUM_PROFILE', 'UCC64_SCOPED_ENUM_CASTS'):
        env.pop(key, None)
    if modern:
        env.update(UCC64_CLIENT_ARRAY_SORT='1', UCC64_SCOPED_ENUM_CASTS='1')
        # Original Japan and Korean EL2ObjectType share all seven names/ordinals.
        # The compiler profile retains its historical korea290 identifier.
        env['UCC64_CLIENT_ENUM_PROFILE'] = 'korea290'
    try:
        with (work/'compile.log').open('wb') as log:
            result = subprocess.run([str(launcher/'ucc64.exe'), '--system', str(system),
                                     'make', '-NoBind', '-Silent'], cwd=system, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=600)
        report['compiler_exit'] = result.returncode
    except subprocess.TimeoutExpired:
        report['timeout'] = True
        save()
        raise
    package = system/'Interface.u'
    report['compiled'] = result.returncode == 0 and package.is_file()
    if package.is_file():
        report['sha256'] = digest(package)
    save()
    if not report['compiled']:
        raise RuntimeError('Compilation failed; inspect compile/compile.log')
    return assemble(work, layout, native, out/'candidate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('korean', 'gracia', 'high_five', 'japan'), default='korean')
    for name in ('sources', 'sdk', 'tools', 'layout', 'native', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.sources, args.sdk, args.tools, args.layout, args.native,
                           args.out, args.profile), indent=2))


if __name__ == '__main__':
    main()
