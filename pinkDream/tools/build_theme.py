"""Build a self-contained themed release from an immutable standard-image library."""
import argparse
import io
import json
import re
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, __version__ as pillow_version
from inventory import ROOT, inspect
from texture import decode, FORMATS
from asset_store import put, read, picture, load_image, digest, write_json
from theme_render import render


def encode(image, fmt, reference):
    if fmt == 5:
        return image.tobytes('raw', 'BGRA')
    if fmt not in (7, 8):
        raise ValueError('Theme image import currently supports BGRA8, DXT3 and DXT5')
    # DDS compressor requires complete 4x4 blocks, even for small mip levels.
    w, h = image.size
    padded = Image.new('RGBA', (max(4, (w+3)//4*4), max(4, (h+3)//4*4)))
    padded.paste(image, (0, 0))
    if padded.width > w:
        padded.paste(image.crop((w-1, 0, w, h)).resize((padded.width-w, h)), (w, 0))
    if padded.height > h:
        padded.paste(padded.crop((0, h-1, padded.width, h)).resize((padded.width, padded.height-h)), (0, h))
    out = io.BytesIO()
    padded.save(out, format='DDS', pixel_format=FORMATS[fmt])
    payload = bytearray(out.getvalue()[128:])
    if len(payload) != len(reference):
        raise ValueError('Encoded payload size mismatch')
    # RGB may change; preserve original BC2/BC3 alpha blocks exactly.
    for i in range(0, len(payload), 16):
        payload[i:i+8] = reference[i:i+8]
    return bytes(payload)


def build(library_path, recipe_path, revision, overrides=None):
    library_bytes, recipe_bytes = library_path.read_bytes(), recipe_path.read_bytes()
    lib, recipe = json.loads(library_bytes), json.loads(recipe_bytes)
    theme, profile = recipe['id'], lib['profile']
    for value in (revision, theme, profile):
        if not re.fullmatch('[A-Za-z0-9_-]+', value):
            raise ValueError('Invalid profile/theme/revision')
    target = ROOT / 'builds' / profile / theme / revision
    assets = ROOT / 'assets/generated' / profile / theme / revision
    stage = target.with_name(target.name + '.partial')
    asset_stage = assets.with_name(assets.name + '.partial')
    for path in (target, assets, stage, asset_stage):
        if path.exists():
            raise FileExistsError(f'Choose a new revision: {path}')
    records = {t['resource']: t for t in lib['textures']}
    if len(records) != len(lib['textures']):
        raise ValueError('Duplicate library resources')
    override_paths = {}
    if overrides:
        for path in overrides.glob('*.png'):
            if path.stem not in records:
                raise ValueError(f'Unknown override resource: {path.name}')
            override_paths[path.stem] = path
    stage.mkdir(parents=True)
    asset_stage.mkdir(parents=True)
    (asset_stage / 'library.json').write_bytes(library_bytes)
    (asset_stage / 'recipe.json').write_bytes(recipe_bytes)
    manifest = {'schema': 2, 'profile': profile, 'theme': theme, 'revision': revision,
                'status': 'offline-validated; game-test-required', 'game_tested': False,
                'library_sha256': digest(library_bytes), 'recipe_sha256': digest(recipe_bytes),
                'pillow': pillow_version, 'source_kind': lib['source_kind'],
                'files': [], 'textures': [], 'tools': {}}
    for filename in ('build_theme.py', 'theme_render.py', 'asset_store.py', 'inventory.py', 'texture.py'):
        data = (Path(__file__).parent / filename).read_bytes()
        (asset_stage / filename).write_bytes(data)
        manifest['tools'][filename] = digest(data)
    thumbs = []
    for package in lib['packages']:
        relative = package['path']
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        original = read(package['container'])
        path.write_bytes(original)
        p = inspect(path, True)
        patched = bytearray(p['_data'])
        spans, count = [], 0
        for t in lib['textures']:
            if t['package'] != relative:
                continue
            name = t['resource']
            if not re.fullmatch('[A-Za-z0-9_.-]+', name):
                raise ValueError('Unsafe texture name')
            source = load_image(t['standard_png'])
            image, role = render(source, name, recipe, t.get('role'))
            override_ref = None
            if name in override_paths:
                image = Image.open(override_paths[name]).convert('RGBA')
                if image.size != source.size or image.getchannel('A').tobytes() != source.getchannel('A').tobytes():
                    raise ValueError(f'Override size/alpha differs from standard: {name}')
                override_ref = picture(image)
                role = 'manual-override'
            record = {'resource': name, 'package': relative, 'role': role, 'format': FORMATS[t['format']],
                      'standard_png': t['standard_png'], 'size': list(source.size),
                      'editable_png': picture(image), 'override': override_ref, 'mips': []}
            resource_dir = asset_stage / name
            resource_dir.mkdir()
            source.save(resource_dir / 'standard.png')
            image.save(resource_dir / 'editable.png')
            for level, mip in enumerate(t['mips']):
                reference = read(mip['reference_payload'])
                alpha = decode(reference, mip['size'], t['format']).getchannel('A')
                scaled = image.resize(tuple(mip['size']), Image.Resampling.LANCZOS)
                scaled.putalpha(alpha)
                encoded = encode(scaled, t['format'], reference)
                decoded = decode(encoded, mip['size'], t['format'])
                if decoded.getchannel('A').tobytes() != alpha.tobytes():
                    raise ValueError('Encoded alpha differs from standard')
                start, stop = mip['offset'], mip['offset'] + len(reference)
                if p['_data'][start:stop] != reference or len(encoded) != len(reference):
                    raise ValueError('Library payload/layout mismatch')
                patched[start:stop] = encoded
                spans.append((start, stop))
                png, raw = picture(decoded), put(encoded, 'bin')
                record['mips'].append({'size': mip['size'], 'offset': start, 'payload': raw, 'png': png,
                                       'alpha_sha256': digest(alpha.tobytes())})
                decoded.save(resource_dir / f'mip-{level:02}.png')
                if level == 0:
                    decoded.save(resource_dir / 'texture.png')
                    decoded.save(resource_dir / 'texture.tga')
                    record['packed_png'], record['packed_tga'] = png, picture(decoded, 'TGA')
                    thumbs.append((name, role, source, decoded))
            manifest['textures'].append(record)
            count += 1
        end = 0
        for start, stop in sorted(spans):
            if start < end or patched[end:start] != p['_data'][end:start]:
                raise ValueError('Changes outside mapped pixel payloads')
            end = stop
        if patched[end:] != p['_data'][end:]:
            raise ValueError('Changes outside mapped pixel payloads')
        header = b'' if p['envelope'] == 'plain' else p['envelope'].encode('utf-16le')
        key = original[len(header)] ^ p['_data'][0] if header else 0
        output = header + bytes(v ^ key for v in patched)
        path.write_bytes(output)
        reread = inspect(path, True)
        if reread['_data'] != patched or reread['exports'] != p['exports']:
            raise ValueError('Package roundtrip failed')
        # Library covers every prior pink change; unchanged parts match the standard package.
        manifest['files'].append({'path': relative, 'sha256': digest(output), 'bytes': len(output),
                                  'original_sha256': digest(original),
                                  'accepted_input_sha256': sorted({digest(original), package['standard_sha256']}),
                                  'textures_changed': count, 'outside_mip_payloads_unchanged': True})
        print(relative, count, 'textures; validated')
    # Paginated previews stay useful as the library grows, rather than a 50,000px strip.
    previews = asset_stage / 'previews'
    previews.mkdir()
    focus = [item for item in thumbs if item[1] in ('title', 'radar') and item[2].width >= 32][:20]
    pages = [('highlights', focus)] + [(f'page-{i//20+1:02}', thumbs[i:i+20]) for i in range(0, len(thumbs), 20)]
    for title, items in pages:
        sheet = Image.new('RGB', (1100, max(1, (len(items)+1)//2)*190), '#18241e')
        draw = ImageDraw.Draw(sheet)
        for i, (name, role, before, after) in enumerate(items):
            x, y = (i%2)*550+8, (i//2)*190+8
            draw.text((x, y), name[-75:], fill='#ffefcf')
            for j, image in enumerate((before, after)):
                preview = image.copy()
                preview.thumbnail((260, 140))
                sheet.paste(preview, (x+j*270, y+25), preview)
            draw.text((x, y+165), 'Standard                         '+theme, fill='#b5d9c4')
        sheet.save(previews / (title+'.png'))
    manifest['previews'] = {path.name: digest(path.read_bytes()) for path in previews.glob('*.png')}
    # Hash every convenient loose file too; stored objects are independently verified on reuse.
    manifest['loose_files'] = {p.relative_to(asset_stage).as_posix(): digest(p.read_bytes())
                               for p in asset_stage.rglob('*') if p.is_file()}
    write_json(asset_stage / 'manifest.json', manifest)
    write_json(stage / 'manifest.json', manifest)
    asset_stage.rename(assets)
    stage.rename(target)
    print(target)
    print(assets / 'previews/highlights.png')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library', required=True, type=Path)
    p.add_argument('--theme', required=True, type=Path)
    p.add_argument('--revision', required=True)
    p.add_argument('--overrides', type=Path)
    a = p.parse_args()
    build(a.library, a.theme, a.revision, a.overrides)
