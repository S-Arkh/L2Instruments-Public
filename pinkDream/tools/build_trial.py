"""Extract selected textures and tint embedded mips without relocating package data."""
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
from PIL import Image, ImageDraw
from inventory import ROOT, inspect
from texture import texture, decode, tint, FORMATS


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def build(profile_id, revision, client=None, base_bundle=None):
    if not re.fullmatch('[A-Za-z0-9_-]+', revision):
        raise ValueError('Invalid revision')
    profile_dir = ROOT / 'profiles' / profile_id
    profile = json.loads((profile_dir / 'profile.json').read_text())
    selection = json.loads((profile_dir / 'selection.json').read_text())
    inventory = json.loads((profile_dir / 'inventory-20261029.json').read_text())
    pinned = {p['relative_path']: p['sha256'] for p in inventory['packages']}
    client = client or Path(profile['client_root_windows' if os.name == 'nt' else 'client_root_linux'])
    base = json.loads((base_bundle / 'manifest.json').read_text()) if base_bundle else None
    if base and base['profile'] != profile_id:
        raise ValueError('Base profile mismatch')
    base_files = {f['path']: f for f in base['files']} if base else {}
    inherited = {m['resource']: m for m in base['mappings']} if base else {}
    expected = dict(pinned)
    ancestors, seen = [], set()
    cursor = base
    while cursor:
        if cursor['profile'] != profile_id or cursor['revision'] in seen:
            raise ValueError('Invalid base lineage')
        seen.add(cursor['revision'])
        ancestors.append(cursor)
        parent = cursor.get('base_revision')
        if parent and not re.fullmatch('[A-Za-z0-9_-]+', parent):
            raise ValueError('Invalid parent revision')
        cursor = json.loads((ROOT / 'builds' / profile_id / parent / 'manifest.json').read_text()) if parent else None
    for ancestor in reversed(ancestors):
        for f in ancestor['files']:
            if f['original_sha256'] != expected.get(f['path']):
                raise ValueError('Base lineage does not match inventory')
            expected[f['path']] = f['sha256']
    for relative, f in base_files.items():
        if relative not in selection['rules']:
            raise ValueError('Base package missing from selection')
        if digest((base_bundle / relative).read_bytes()) != f['sha256']:
            raise ValueError('Base package hash mismatch')
        expected[relative] = f['sha256']
    for relative in selection['rules']:
        if relative not in pinned or digest((client / relative).read_bytes()) != expected[relative]:
            raise ValueError(f'Unexpected input package: {relative}')
    target = ROOT / 'builds' / profile_id / revision
    assets = ROOT / 'assets/generated' / profile_id / revision
    sources = ROOT / 'assets/source' / profile_id / revision
    preview = ROOT / 'assets/previews' / f'{profile_id}-{revision}.png'
    for path in (target, assets, sources, preview):
        if path.exists() or path.with_name(path.name + '.partial').exists():
            raise FileExistsError(path)
    stage = target.with_name(target.name + '.partial')
    stage.mkdir(parents=True)
    assets.mkdir(parents=True)
    sources.mkdir(parents=True)
    manifest = {'schema': 1, 'profile': profile_id, 'revision': revision,
                'status': 'offline-validated; game-test-required', 'game_tested': False,
                'algorithm': 'pink-endpoints-v1; exact alpha and mip layout preservation',
                'base_revision': base['revision'] if base else None,
                'files': [], 'mappings': []}
    thumbs = []
    for relative, patterns in selection['rules'].items():
        if relative not in profile['packages'] or relative not in pinned:
            raise ValueError('Selection must reference an inventoried package')
        original = (client / relative).read_bytes()
        if digest(original) != expected[relative]:
            raise ValueError(f'Original package changed: {relative}; refresh inventory first')
        p = inspect(client / relative, True)
        patched = bytearray(p['_data'])
        spans, selected = [], []
        for e, meta in zip(p['_entries'], p['exports']):
            name = meta['resource']
            if name in inherited:
                old = inherited[name]
                for asset in old['files'].values():
                    if digest((ROOT / asset['path']).read_bytes()) != asset['sha256']:
                        raise ValueError('Inherited asset was modified')
                if digest((ROOT / old['source']).read_bytes()) != old['source_sha256']:
                    raise ValueError('Inherited source was modified')
                manifest['mappings'].append(old)
                selected.append(name)
                thumbs.append((name, Image.open(ROOT / old['source']).convert('RGBA'),
                               Image.open(ROOT / old['files']['png']['path']).convert('RGBA')))
                continue
            if meta['class'] != 'Engine.Texture' or not any(fnmatch.fnmatchcase(name.lower(), pat.lower()) for pat in patterns):
                continue
            if not re.fullmatch('[A-Za-z0-9_.-]+', name):
                raise ValueError('Unsafe resource name')
            t = texture(p, e)
            record = {'package': relative, 'package_sha256': p['sha256'], 'resource': name,
                      'format': FORMATS[t['format']], 'size': t['mips'][0]['size'],
                      'mip_count': len(t['mips']), 'alpha_policy': 'exact-preservation', 'mips': []}
            for level, mip in enumerate(t['mips']):
                before = decode(mip['data'], mip['size'], t['format'])
                output = tint(mip['data'], t['format'])
                after = decode(output, mip['size'], t['format'])
                if before.getchannel('A').tobytes() != after.getchannel('A').tobytes():
                    raise ValueError(f'Alpha changed: {name} mip {level}')
                start, length = mip['offset'], mip['length']
                patched[start:start + length] = output
                spans.append((start, start + length))
                record['mips'].append({'size': mip['size'], 'offset': start, 'length': length,
                                       'source_sha256': digest(mip['data']), 'patched_sha256': digest(output),
                                       'alpha_sha256': digest(before.getchannel('A').tobytes())})
                if level == 0:
                    source = sources / f'{name}.png'
                    before.save(source)
                    record['source'] = str(source.relative_to(ROOT))
                    record['source_sha256'] = digest(source.read_bytes())
                    record['files'] = {}
                    for ext in ('png', 'tga'):
                        image = assets / f'{name}.{ext}'
                        after.save(image)
                        record['files'][ext] = {'path': str(image.relative_to(ROOT)), 'sha256': digest(image.read_bytes())}
                    thumbs.append((name, before, after))
            manifest['mappings'].append(record)
            selected.append(name)
        if not selected:
            raise ValueError(f'No matching textures: {relative}')
        # Strong byte-level invariant: every byte outside selected mip payloads is unchanged.
        end = 0
        for start, stop in sorted(spans):
            if start < end or patched[end:start] != p['_data'][end:start]:
                raise ValueError('Unexpected change outside selected pixel payloads')
            end = stop
        if patched[end:] != p['_data'][end:]:
            raise ValueError('Unexpected trailing changes')
        if p['envelope'] == 'plain':
            encoded = bytes(patched)
        else:
            header = p['envelope'].encode('utf-16le')
            key = original[len(header)] ^ p['_data'][0]
            encoded = header + bytes(b ^ key for b in patched)
        out = stage / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(encoded)
        reread = inspect(out, True)
        if reread['exports'] != p['exports'] or reread['_data'] != patched:
            raise ValueError('Written package failed roundtrip validation')
        manifest['files'].append({'path': relative, 'original_sha256': digest(original),
                                  'sha256': digest(encoded), 'bytes': len(encoded), 'textures_changed': len(selected),
                                  'outside_mip_payloads_unchanged': True})
        print(relative, len(selected), 'textures; package roundtrip OK')
    sheet = Image.new('RGB', (1000, 150 * ((len(thumbs) + 1) // 2)), '#1c1420')
    draw = ImageDraw.Draw(sheet)
    for i, (name, before, after) in enumerate(thumbs):
        x, y = (i % 2) * 500 + 8, (i // 2) * 150 + 6
        draw.text((x, y), name.split('.', 1)[1][:65], fill='#ffe0ef')
        for j, image in enumerate((before, after)):
            image = image.copy()
            image.thumbnail((235, 110))
            sheet.paste(image, (x + j * 245, y + 26), image)
        draw.text((x, y + 132), 'Original                        PinkDream', fill='#cfa6bf')
    sheet.save(preview)
    manifest['preview'] = str(preview.relative_to(ROOT))
    manifest['preview_sha256'] = digest(preview.read_bytes())
    write_json(stage / 'manifest.json', manifest)
    write_json(assets / 'manifest.json', manifest)
    write_json(sources / 'manifest.json', {'schema': 1, 'profile': profile_id, 'textures': [
        {k: m[k] for k in ('resource', 'package', 'package_sha256', 'format', 'size', 'mip_count', 'source', 'source_sha256')}
        for m in manifest['mappings']]})
    for script in ('build_trial.py', 'inventory.py', 'texture.py'):
        shutil.copyfile(Path(__file__).parent / script, assets / script)
    shutil.copyfile(profile_dir / 'selection.json', assets / 'selection.json')
    stage.rename(target)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('scryde',), required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--client', type=Path)
    parser.add_argument('--base-bundle', type=Path, help='Verified prior bundle already installed in the input client')
    args = parser.parse_args()
    build(args.profile, args.revision, args.client, args.base_bundle)
