"""Generate persistent, versioned theme assets; never replace an existing revision."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil

from PIL import Image, ImageColor, ImageDraw, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(theme_path, revision):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', revision):
        raise ValueError('Revision must contain only letters, numbers, _ and -')
    theme = json.loads(theme_path.read_text(encoding='utf-8'))
    theme_id = theme['id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', theme_id):
        raise ValueError('Invalid theme id')
    target = ROOT / 'assets/generated' / theme_id / revision
    stage = target.with_name(target.name + '.partial')
    preview = ROOT / 'assets/previews' / f'{theme_id}-{revision}.png'
    if target.exists() or stage.exists() or preview.exists():
        raise FileExistsError('Revision already exists; choose a new --revision')
    stage.mkdir(parents=True)
    colors = theme['colors']
    entries, images, seen = [], [], set()
    for spec in theme['assets']:
        name = spec['id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or name in seen:
            raise ValueError('Invalid or duplicate asset id')
        seen.add(name)
        w, h = spec['size']
        if not (1 <= w <= 4096 and 1 <= h <= 4096):
            raise ValueError('Invalid dimensions')
        top, bottom = [ImageColor.getrgb(colors[c]) for c in spec['colors']]
        image = Image.new('RGBA', (w, h))
        draw = ImageDraw.Draw(image)
        for y in range(h):
            t = y / max(h - 1, 1)
            color = tuple(round(a * (1 - t) + b * t) for a, b in zip(top, bottom))
            draw.line((0, y, w - 1, y), fill=color + (255,))
        mask = Image.new('L', (w, h))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=spec['radius'], fill=255)
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=spec['radius'], outline=colors['border'])
        image.putalpha(mask)
        files = {}
        for ext in ('png', 'tga'):
            path = stage / f'{name}.{ext}'
            image.save(path)
            files[ext] = {'path': path.name, 'sha256': sha(path)}
        entries.append({'id': name, 'size': [w, h], 'mode': 'RGBA',
                        'alpha_extrema': list(mask.getextrema()), 'source_resource': None,
                        'usage': 'reusable-concept; requires client mapping', 'parameters': spec, 'files': files})
        images.append((name, image))
    sheet = Image.new('RGB', (720, 370 * ((len(images) + 3) // 4)), '#170f19')
    draw = ImageDraw.Draw(sheet)
    for i, (name, image) in enumerate(images):
        x, y = (i % 4) * 180 + 10, (i // 4) * 370 + 10
        draw.text((x, y), name, fill=colors['text'])
        thumb = image.copy()
        thumb.thumbnail((160, 320))
        sheet.paste(thumb, (x, y + 24), thumb)
    sheet.save(stage / 'preview.png')
    shutil.copyfile(theme_path, stage / 'theme.json')
    shutil.copyfile(Path(__file__), stage / 'generate.py')
    manifest = {'schema': 1, 'theme': theme_id, 'revision': revision,
                'pillow': pillow_version, 'theme_sha256': sha(theme_path),
                'generator_sha256': sha(Path(__file__)), 'assets': entries,
                'preview_sha256': sha(stage / 'preview.png')}
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    stage.rename(target)
    preview.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target / 'preview.png', preview)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme', type=Path, default=ROOT / 'themes/glamour-pink/theme.json')
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    generate(args.theme, args.revision)
