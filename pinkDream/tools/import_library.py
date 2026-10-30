"""Migrate verified standard source PNGs and package layouts into a reusable library."""
import argparse
import json
from pathlib import Path
from PIL import Image
from inventory import ROOT, inspect
from texture import texture, decode
from asset_store import put, picture, digest, write_json


def migrate(bundle, revision):
    import re
    if not re.fullmatch('[A-Za-z0-9_-]+', revision):
        raise ValueError('Invalid library revision')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    profile = manifest['profile']
    if profile not in ('scryde', 'high-five', 'gracia'):
        raise ValueError('Invalid profile')
    target = ROOT / 'assets/libraries' / profile / revision
    stage = target.with_name(target.name + '.partial')
    if target.exists() or stage.exists():
        raise FileExistsError(target)
    stage.mkdir(parents=True)
    inventory = json.loads((ROOT / 'profiles' / profile / 'inventory-20261029.json').read_text())
    original_hashes = {p['relative_path']: p['sha256'] for p in inventory['packages']}
    lib = {'schema': 2, 'profile': profile, 'revision': revision,
           'source_kind': 'original-top-level-PNG; lower RGB mips regenerated from top; exact original alpha',
           'reference_revision': manifest['revision'], 'packages': [], 'textures': []}
    for f in manifest['files']:
        path = bundle / f['path']
        data = path.read_bytes()
        if digest(data) != f['sha256']:
            raise ValueError('Reference package changed')
        p = inspect(path, True)
        entries = {m['resource']: e for e, m in zip(p['_entries'], p['exports'])}
        lib['packages'].append({'path': f['path'], 'container': put(data, 'utx'),
                                'standard_sha256': original_hashes[f['path']]})
        for m in manifest['mappings']:
            if m['package'] != f['path']:
                continue
            source = ROOT / m['source']
            if digest(source.read_bytes()) != m['source_sha256']:
                raise ValueError('Standard source image changed')
            image = Image.open(source).convert('RGBA')
            t = texture(p, entries[m['resource']])
            if image.size != tuple(m['size']):
                raise ValueError('Source image size mismatch')
            if image.getchannel('A').tobytes() != decode(t['mips'][0]['data'], m['size'], t['format']).getchannel('A').tobytes():
                raise ValueError('Source alpha mismatch')
            lib['textures'].append({'resource': m['resource'], 'package': f['path'],
                                    'format': t['format'], 'size': m['size'], 'standard_png': picture(image),
                                    'mips': [{'size': mip['size'], 'offset': mip['offset'],
                                             'reference_payload': put(mip['data'], 'bin')}
                                            for mip in t['mips']]})
    write_json(stage / 'manifest.json', lib)
    stage.rename(target)
    print(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--revision', required=True)
    a = p.parse_args()
    migrate(a.bundle, a.revision)
