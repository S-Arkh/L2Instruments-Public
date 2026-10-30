"""Verify saved image pixels, inherited mappings and real install/rollback on a copy."""
from pathlib import Path
import argparse
import json
import tempfile
import shutil
from PIL import Image
from inventory import ROOT, inspect
from texture import texture, decode
from install import install, rollback, sha


def verify(bundle, base_bundle, temp_root):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    base = json.loads((base_bundle / 'manifest.json').read_text())
    if manifest['base_revision'] != base['revision'] or manifest['profile'] != base['profile']:
        raise ValueError('Wrong base bundle')
    previous = {a['resource']: a for a in base['mappings']}
    current = {a['resource']: a for a in manifest['mappings']}
    if len(current) != len(manifest['mappings']):
        raise ValueError('Duplicate mappings')
    for name, entry in previous.items():
        if current.get(name) != entry:
            raise ValueError(f'Inherited mapping changed: {name}')
    mip_count = 0
    for f in manifest['files']:
        if sha(bundle / f['path']) != f['sha256']:
            raise ValueError('Bundle hash mismatch')
        p = inspect(bundle / f['path'], True)
        entries = {a['resource']: e for e, a in zip(p['_entries'], p['exports'])}
        for a in manifest['mappings']:
            if a['package'] != f['path']:
                continue
            t = texture(p, entries[a['resource']])
            if len(t['mips']) != a['mip_count']:
                raise ValueError('Mip count mismatch')
            for mip, recorded in zip(t['mips'], a['mips']):
                import hashlib
                if hashlib.sha256(mip['data']).hexdigest() != recorded['patched_sha256']:
                    raise ValueError('Mip payload hash mismatch')
                decoded = decode(mip['data'], mip['size'], t['format'])
                if hashlib.sha256(decoded.getchannel('A').tobytes()).hexdigest() != recorded['alpha_sha256']:
                    raise ValueError('Mip alpha mismatch')
            top = t['mips'][0]
            decoded = decode(top['data'], top['size'], t['format'])
            for asset in a['files'].values():
                path = ROOT / asset['path']
                with Image.open(path) as image:
                    if sha(path) != asset['sha256'] or image.convert('RGBA').tobytes() != decoded.tobytes():
                        raise ValueError(f'Saved image mismatch: {path}')
            mip_count += len(t['mips'])
    with tempfile.TemporaryDirectory(dir=temp_root, prefix='pinkdream-verify-') as temp:
        temp = Path(temp)
        client, backup = temp / 'client', temp / 'backup'
        (client / 'SysTextures').mkdir(parents=True)
        for f in manifest['files']:
            shutil.copy2(base_bundle / f['path'], client / f['path'])
        install(client, bundle, backup, check=True)
        if backup.exists():
            raise ValueError('Read-only check created backup')
        install(client, bundle, backup)
        for f in manifest['files']:
            if sha(client / f['path']) != f['sha256']:
                raise ValueError('Installed hash mismatch')
        rollback(backup)
        for f in manifest['files']:
            if sha(client / f['path']) != f['original_sha256']:
                raise ValueError('Restored hash mismatch')
    return {'revision': manifest['revision'], 'textures': len(current), 'mips': mip_count,
            'inherited_unchanged': len(previous), 'new_textures': len(current) - len(previous),
            'image_and_alpha_checks': 'passed', 'isolated_install_rollback': 'passed',
            'game_tested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--base-bundle', type=Path, required=True)
    parser.add_argument('--temp-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(args.report)
    result = verify(args.bundle.resolve(), args.base_bundle.resolve(), args.temp_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(result, indent=2))
