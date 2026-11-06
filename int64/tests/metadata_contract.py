"""Assert the bounded SDK metadata contract using the synthetic owner fixture."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from ue2package import Package, Reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compiler', 'tools', 'metadata-probe', 'package', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local'):
        parser.error('Output must be a new directory under uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    scripts = Path(__file__).resolve().parent
    def run(script, *arguments):
        subprocess.run([sys.executable, '-B', str(scripts/script), *map(str, arguments)], check=True)
    for label, options in [('original-mask', ['--original-property-mask', '--clear-client-class-bit']),
                           ('class-bit', ['--clear-client-class-bit'])]:
        run('metadata_variant.py', '--package', args.package, '--out', out/label, *options)
    objects = ';'.join('Generation.'+name for name in ('InlineValue', 'PlainValue', 'MetadataOwner',
        'MetadataOwner.Inline', 'MetadataOwner.Fixed', 'MetadataOwner.Dynamic', 'MetadataOwner.Dynamic.Dynamic',
        'MetadataOwner.Plain', 'MetadataOwner.Accept.Value', 'MetadataOwner.Accept.Control'))
    for label, package in [('compiled', args.package), ('original-mask', out/'original-mask/Generation.u')]:
        target = out/(label+'-lifecycle')
        run('metadata_lifecycle.py', '--compiler', args.compiler, '--tools', args.tools,
            '--metadata-probe', args.metadata_probe, '--package', package, '--objects', objects,
            '--lifecycle', '--out', target)
        result = json.loads((target/'result.json').read_text())
        for index, trial in enumerate(result['passes']):
            for row in trial['records']:
                original = label == 'original-mask' and index == 0 and row['stage'] == 'loaded'
                if row['kind'] == 'class':
                    expected = 0xe0004 if original else 0xf0004
                    assert row['object_flags'] & 0xf0004 == expected, row
                else:
                    name = row['object'].removeprefix('Generation.')
                    expected = {'MetadataOwner.Dynamic': 0x400000, 'MetadataOwner.Plain': 0,
                                'MetadataOwner.Accept.Control': 0x180}.get(name)
                    if expected is None:
                        expected = (0x400000 if original else 0x4400008) | (0x180 if name.endswith('.Value') else 0)
                    assert row['flags'] == expected, row
            text = (target/f'pass-{index}.log').read_text()
            assert 'lifetime rooted-owner-retains=1 cleared-reference-collected=1' in text
            for mask, distinct in [('00400000', 1), ('04000008', 0), ('04400008', 1)]:
                assert f'template flags={mask} inline-distinct={distinct}' in text
                assert f'copy flags={mask} null-owner-shallow=1 owner-distinct=0' in text
            assert 'lifecycle plain-shallow=1 referenced-payload-survives=1 valid=1' in text
        # Stable metadata, not byte equality (the saver may update package GUIDs).
        def inventory(index):
            rows = json.loads((target/f'serialized-{index}.json').read_text())
            package = Package(target/f'pass-{index}.u')
            for row in rows:
                if 'raw' in row:
                    r = Reader(bytes.fromhex(row.pop('raw')))
                    assert package.name(r.index()) == 'None'
                    row['super_reference'] = package.ref(r.index())
                    row['next_reference'] = package.ref(r.index())
            return {r.get('class', r.get('property')): r for r in rows}
        assert inventory(1) == inventory(2)
    # Only one bit differs in this pair; no property-mask confound.
    contexts = []
    for label, package in [('compiled', args.package), ('class-bit', out/'class-bit/Generation.u')]:
        for context in ('editor', 'client', 'server'):
            target = out/(label+'-'+context)
            shutil.copytree(out/'compiled-lifecycle/System', target)
            shutil.copy2(package, target/'Generation.u')
            env = {k: v for k, v in os.environ.items() if not k.startswith('UCC_METADATA_')}
            env.update(UCC_PTR_PROBE_MODE='metadata', UCC_METADATA_PACKAGE='Generation.u',
                       UCC_METADATA_OBJECTS='Generation.InlineValue;Generation.MetadataOwner', UCC_METADATA_CONTEXT=context)
            result = subprocess.run([str(target/'ucc64.exe'), '--system', str(target), 'help', '-NoBind'],
                cwd=target, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            (target/'result.log').write_bytes(result.stdout)
            text = result.stdout.decode(errors='replace')
            rejected = label == 'class-bit' and context == 'client'
            if rejected:
                diagnostic = re.search(r'Object is not packaged: ObjectProperty (Inline|Plain|Fixed|Dynamic|Value|Control)\s', text)
                assert result.returncode == 1 and diagnostic and 'ULinkerLoad::CreateExport' in text and 'metadata-complete=1' not in text, text
            else:
                assert result.returncode == 0 and 'metadata-complete=1' in text, text
            contexts.append(dict(variant=label, context=context, exit=result.returncode,
                package=hashlib.sha256(package.read_bytes()).hexdigest(), log=hashlib.sha256(result.stdout).hexdigest()))
    (out/'contexts.json').write_text(json.dumps(contexts, indent=2), encoding='utf-8')
    print('PASS: save/reload, shallow/template copy, reference GC and isolated client-load-bit controls')


if __name__ == '__main__':
    main()
