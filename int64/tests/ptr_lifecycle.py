"""Run native registration/save/fresh-process reload in an isolated SDK copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--metadata-probe', type=Path, required=True)
    parser.add_argument('--compiled-package', type=Path, help='Compiled pointer fixture Generation.u')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local'):
        parser.error('Output must be a new directory under uExplorer/local')
    hashes = {
        'Core.dll': '5bff274734cae994353a8c60f4bfe1087dbdd9aa3883c7b2a7eff6ea2f51dc7e',
        'Editor.dll': 'd64995c1282956c6e9d67dd70715a69b5101331aa727a2d44b03e25fd7f2cd2e',
        'UCC.exe': 'c68ba1ce0eab03af23b04dc1c991c3f1cc047a8a2076c6850e3071892806fb65',
    }
    for filename, expected in hashes.items():
        if hashlib.sha256((args.compiler/filename).read_bytes()).hexdigest() != expected:
            raise ValueError('Unsupported SDK: '+filename)
    out.mkdir(parents=True, exist_ok=False)
    system = out/'System'
    system.mkdir()
    for source in args.compiler.iterdir():
        if source.is_file() and source.suffix.lower() in ('.exe', '.dll', '.int', '.u', '.ini'):
            shutil.copy2(source, system/source.name)
    if (system/'PtrProbe.u').exists():
        raise ValueError('Input already contains PtrProbe.u')
    shutil.copy2(args.launcher, system/'ucc64.exe')
    shutil.copy2(args.probe, system/'Ucc64Bridge.dll')
    for mode, marker in (('', 'instance=1 class-identity=1'),
                         ('save', 'pointer-instance=1 saved=1'),
                         ('load', 'loaded=1 pointer-identity=1')):
        result = subprocess.run([str(system/'ucc64.exe'), '--system', str(system), 'help'],
                                cwd=system, env=dict(os.environ, UCC_PTR_PROBE_MODE=mode),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        (out/((mode or 'control')+'.log')).write_bytes(result.stdout)
        text = result.stdout.decode(errors='replace')
        print(text)
        if result.returncode or marker not in text:
            raise AssertionError(f'{mode or "control"} failed: {result.returncode}')
        if mode == 'load' and 'value-contracts=1' not in text:
            raise AssertionError('Value contracts were not verified')
    rows = json.loads(subprocess.check_output([str(args.metadata_probe.resolve()),
                                               str(system/'PtrProbe.u')], text=True))
    prop = next(row for row in rows if row.get('property') == 'Holder.Value')
    if not (prop['kind'] == 'PtrProperty' and prop['dimension'] == 1
            and prop['flags'] == 0x1000 and prop['unread_bytes'] == 0
            and prop['raw'] == '000000010000000010000000'):
        raise AssertionError(prop)
    (out/'metadata.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    result = subprocess.run([str(system/'ucc64.exe'), '--system', str(system), 'help'],
                            cwd=system, env=dict(os.environ, UCC_PTR_PROBE_MODE='missing'),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (out/'missing.log').write_bytes(result.stdout)
    text = result.stdout.decode(errors='replace')
    print(text)
    if result.returncode != 28 or 'missing-PtrProperty-rejected' not in text:
        raise AssertionError('Expected missing native class failure was not observed')
    if args.compiled_package:
        fixture_rows = json.loads(subprocess.check_output([str(args.metadata_probe.resolve()),
                                                           str(args.compiled_package.resolve())], text=True))
        expected = {
            'PointerProbe.CopyParameter.Value': (1, 0x80),
            'PointerProbe.CopyParameter.Destination': (1, 0x180),
            'PointerProbe.CopyParameter.Saved': (1, 0),
            'PointerProbe.ReturnPointer.Value': (1, 0x80),
            'PointerProbe.ReturnPointer.ReturnValue': (1, 0x580),
            'PointerProbe.ClearPointers.Empty': (1, 0),
            'PointerProbe.Handles': (3, 0x1000),
            'PointerProbe.Animations': (2, 0x2000),
        }
        properties = {row.get('property'): row for row in fixture_rows if 'property' in row}
        for name, (dimension, flags) in expected.items():
            row = properties[name]
            if (row['kind'], row['dimension'], row['flags'], row['unread_bytes']) != ('PtrProperty', dimension, flags, 0):
                raise AssertionError(row)
        (out/'fixture-metadata.json').write_text(json.dumps(fixture_rows, indent=2), encoding='utf-8')
        if (system/'Generation.u').exists():
            raise ValueError('SDK input already contains Generation.u')
        shutil.copy2(args.compiled_package, system/'Generation.u')
        result = subprocess.run([str(system/'ucc64.exe'), '--system', str(system), 'help', '-NoBind'],
                                cwd=system, env=dict(os.environ, UCC_PTR_PROBE_MODE='fixture'),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        (out/'fixture.log').write_bytes(result.stdout)
        text = result.stdout.decode(errors='replace')
        print(text)
        if result.returncode or 'compiled-fixture=1 zero-initialized-fields=14 independent-instances=1' not in text:
            raise AssertionError('Compiled pointer fixture initialization failed')
        if 'nested-text-roundtrip=1' not in text or 'pointer-vm-contracts=1' not in text:
            raise AssertionError('Pointer text/VM contracts were not verified')
        if 'compiled-pointer-expressions=1' not in text:
            raise AssertionError('Compiled pointer expressions were not executed')
        if 'compiled-pointer-locals-parameters-null=1' not in text:
            raise AssertionError('Pointer function storage and null values were not verified')
        if 'compiled-pointer-equality=1' not in text:
            raise AssertionError('Pointer comparisons were not verified')
    print('PASS: native registration, pointer metadata save/reload and value contracts')


if __name__ == '__main__':
    main()
