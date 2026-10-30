"""Validate a prepared bundle in isolated loader/VM hosts; publish its manifest."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from core_profiles import approved, CATALOG, PE
from patch_core import patch_bytes
from check_core_dependencies import check
from check_installation import digest, local_file, resources
from check_uc import check as check_uc


def validate(original, bundle, system, tools, bytecode, wine=None, file_bytecode=None):
    original, bundle, system, tools, bytecode = [Path(p).resolve() for p in (original, bundle, system, tools, bytecode)]
    manifest = bundle / 'bundle.json'
    if manifest.exists():
        raise ValueError('Bundle already has a manifest; prepare a new destination')
    if os.name != 'nt' and not wine:
        raise ValueError('Pass --wine for Windows probes outside Windows')
    image = PE(original)
    profile = approved(image)
    expected, _ = patch_bytes(image.data, image)
    if local_file(bundle, 'Core.dll').read_bytes() != expected:
        raise ValueError('Prepared Core does not equal the patch of selected original')
    for name in ('ExtensionL2.dll', 'ExtensionL2.u'):
        local_file(bundle, name)
    if not bytecode.is_file():
        raise ValueError('Compiled UC call bytes are required')
    if file_bytecode is not None:
        file_bytecode = Path(file_bytecode).resolve(strict=True)
    imports = check(system, bundle / 'Core.dll')
    if not imports['compatible_imports']:
        raise ValueError('Target imports do not match Core: ' + json.dumps(imports))
    # Require real target entry/engine files even when other DLLs import Core.
    target_names = sorted(set(imports['checked']) | {local_file(system, 'Engine.dll').name,
                                                   local_file(system, 'l2.exe').name})
    targets = {name: digest(local_file(system, name)) for name in target_names
               if name.casefold() != 'extensionl2.dll'}
    binaries = {name: digest(local_file(bundle, name)) for name in ('Core.dll', 'ExtensionL2.dll', 'ExtensionL2.u')}
    probes = {name: digest(local_file(tools, name)) for name in ('client_link_probe.exe', 'extension_probe.exe', 'extension_bindings.exe')}
    logdir = bundle / 'validation'
    logdir.mkdir(exist_ok=True)
    results = []

    def winpath(path):
        return str(path) if os.name == 'nt' else 'Z:' + str(path).replace('/', '\\')

    with tempfile.TemporaryDirectory(prefix='extension-validation-') as temporary:
        stage = Path(temporary)
        # Use a single isolated search directory, never installed Core/Extension.
        for path in system.iterdir():
            if path.is_file() and path.suffix.casefold() in ('.dll', '.manifest') and path.name.casefold() not in ('core.dll', 'extensionl2.dll'):
                shutil.copy2(path, stage / path.name)
        for name in probes:
            shutil.copy2(local_file(tools, name), stage / name)
        shutil.copy2(local_file(bundle, 'ExtensionL2.dll'), stage / 'ExtensionL2.dll')
        engine = local_file(stage, 'Engine.dll')

        def run(label, exe, arguments):
            executable = stage / exe
            command = ([str(Path(wine).resolve()), winpath(executable)] if wine else [str(executable)])
            command += [winpath(p) if isinstance(p, Path) else p for p in arguments]
            log = logdir / (label + '.log')
            with log.open('wb') as output:
                result = subprocess.run(command, cwd=stage, stdout=output, stderr=subprocess.STDOUT, timeout=120)
            results.append(dict(name=label, exit_code=result.returncode, log=log.name))
            if result.returncode:
                raise RuntimeError(f'{label} failed ({result.returncode}); see {log}')

        run('binding-metadata', 'extension_bindings.exe',
            [stage / 'ExtensionL2.dll', stage / 'ExtensionL2API.uc', stage / 'bindings.json'])
        check_uc(local_file(bundle, 'ExtensionL2.u'), stage / 'compiled-call.bin', stage / 'bindings.json')
        if (stage / 'compiled-call.bin').read_bytes() != bytecode.read_bytes():
            raise ValueError('Supplied VM fixture does not match bundled ExtensionL2.u')
        for mode, core in (('manual', original), ('patched', bundle / 'Core.dll')):
            shutil.copy2(core, stage / 'Core.dll')
            run(mode + '-loader', 'client_link_probe.exe', [stage / 'Core.dll', engine, stage])
            arguments = [stage / 'Core.dll', stage, stage / 'ExtensionL2.dll', mode, stage / 'compiled-call.bin']
            if file_bytecode:
                shutil.copy2(file_bytecode, stage / 'compiled-write.bin')
                arguments.append(stage / 'compiled-write.bin')
            run(mode + '-vm', 'extension_probe.exe', arguments)

    # Do not attest a file set modified while probes were running.
    if any(digest(local_file(system, n)) != h for n, h in targets.items()) or any(digest(local_file(bundle, n)) != h for n, h in binaries.items()):
        raise ValueError('Inputs changed during validation')
    report = dict(schema=1, profile=profile['name'], original_sha256=profile['sha256'],
                  catalog_sha256=digest(CATALOG), bundle_files=binaries, target_files=targets,
                  target_system=str(system), probe_files=probes, compiled_call_sha256=digest(bytecode),
                  imports=imports, resources=resources(system),
                  validation=dict(status='passed', host='Windows' if os.name == 'nt' else 'Wine', tests=results,
                                  full_game_startup='not tested by this command'))
    if file_bytecode:
        report['compiled_write_sha256'] = digest(file_bytecode)
    manifest.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--bytecode', type=Path, required=True)
    parser.add_argument('--wine', type=Path)
    parser.add_argument('--file-bytecode', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.original, args.bundle, args.system, args.tools, args.bytecode, args.wine, args.file_bytecode), indent=2))
