"""Create a profile-specific source library directly from inventoried standard UTX."""
import argparse
import fnmatch
import json
import re
from pathlib import Path
from inventory import ROOT, inspect
from texture import texture, decode
from asset_store import digest, put, picture, write_json


def create(profile, client, inventory_path, selection_path, revision):
    for value in (profile, revision):
        if not re.fullmatch('[A-Za-z0-9_-]+', value):
            raise ValueError('Invalid profile/revision')
    cfg = json.loads((ROOT / 'profiles' / profile / 'profile.json').read_text())
    inventory = json.loads(inventory_path.read_text())
    selection = json.loads(selection_path.read_text())
    if inventory['profile'] != profile:
        raise ValueError('Inventory profile mismatch')
    pinned = {p['relative_path']: p['sha256'] for p in inventory['packages']}
    target = ROOT / 'assets/libraries' / profile / revision
    stage = target.with_name(target.name + '.partial')
    if target.exists() or stage.exists():
        raise FileExistsError(target)
    for relative in selection['rules']:
        if relative not in cfg['packages'] or relative not in pinned:
            raise ValueError('Selection package is not inventoried in the profile')
        if digest((client / relative).read_bytes()) != pinned[relative]:
            raise ValueError('Standard package hash mismatch')
    lib = {'schema': 2, 'profile': profile, 'revision': revision,
           'source_kind': 'original-package-all-mips', 'packages': [], 'textures': []}
    for relative, patterns in selection['rules'].items():
        path = client / relative
        p = inspect(path, True)
        lib['packages'].append({'path': relative, 'standard_sha256': pinned[relative],
                                'container': put(path.read_bytes(), 'utx')})
        found = 0
        for entry, meta in zip(p['_entries'], p['exports']):
            name = meta['resource']
            if meta['class'] != 'Engine.Texture' or not any(fnmatch.fnmatchcase(name.lower(), pat.lower()) for pat in patterns):
                continue
            t = texture(p, entry)
            if t['format'] not in (5, 7, 8):
                raise ValueError(f'Image importer does not support format {t["format"]}: {name}')
            top = t['mips'][0]
            record = {'resource': name, 'package': relative, 'format': t['format'], 'size': top['size'],
                      'standard_png': picture(decode(top['data'], top['size'], t['format'])),
                      'mips': [{'size': mip['size'], 'offset': mip['offset'],
                                'reference_payload': put(mip['data'], 'bin')}
                               for mip in t['mips']]}
            roles = {value for pat, value in selection.get('roles', {}).items()
                     if fnmatch.fnmatchcase(name.lower(), pat.lower())}
            if len(roles) > 1:
                raise ValueError(f'Conflicting role rules: {name}')
            if roles:
                record['role'] = roles.pop()
            lib['textures'].append(record)
            found += 1
        if not found:
            raise ValueError(f'No textures matched in {relative}')
    stage.mkdir(parents=True)
    write_json(stage / 'manifest.json', lib)
    (stage / 'selection.json').write_bytes(selection_path.read_bytes())
    stage.rename(target)
    print(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', required=True)
    p.add_argument('--client', type=Path, required=True)
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--revision', required=True)
    a = p.parse_args()
    create(a.profile, a.client, a.inventory, a.selection, a.revision)
