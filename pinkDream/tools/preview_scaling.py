"""Compare old seasonal artwork with tile-safe rendering at repeated/stretched sizes."""
import json
from PIL import Image, ImageDraw
from inventory import ROOT
from asset_store import load_image
from theme_render import render


def strip(image, mode):
    if mode == 'tile-horizontal':
        result = Image.new('RGBA', (176, 24))
        for x in range(0, result.width, image.width):
            result.paste(image, (x, 4))
        return result.transpose(Image.Transpose.ROTATE_90).resize((72, 528), Image.Resampling.NEAREST)
    result = Image.new('RGBA', (24, 176))
    if mode == 'tile':
        for y in range(0, result.height, image.height):
            result.paste(image, (4, y))
    else:
        result.paste(image.resize((16, 176), Image.Resampling.BILINEAR), (4, 0))
    return result.resize((72, 528), Image.Resampling.NEAREST)


def main():
    lib = json.loads((ROOT / 'assets/libraries/scryde/standard-ui-v001/manifest.json').read_text())
    textures = {t['resource']: t for t in lib['textures']}
    selected = [
        ('L2UI_CT1.Frames.Frame_DF_Ver_Small_Tile', 'tile'),
        ('L2UI_CT1.Frames.Frame_DF_Hor_Small_Tile', 'tile-horizontal'),
        ('L2UI_CH3.SCROLLBAR.SliderBarCenter', 'stretch'),
        ('patch.Windows.Windows_DF_Vertical_SizeControl_Bg', 'stretch'),
    ]
    sheet = Image.new('RGB', (1160, 1240), '#202027')
    d = ImageDraw.Draw(sheet)
    for row, (theme, previous) in enumerate((('christmas', 'v002'), ('halloween', 'v001'))):
        recipe = json.loads((ROOT / 'themes' / theme / 'theme.json').read_text())
        old_manifest = json.loads((ROOT / 'assets/generated/scryde' / theme / previous / 'manifest.json').read_text())
        old = {t['resource']: t for t in old_manifest['textures']}
        for col, (name, mode) in enumerate(selected):
            x, y = col*290+8, row*620+10
            d.text((x, y), theme+' / '+mode, fill='#ffffff')
            d.text((x, y+18), name.split('.')[-1][:37], fill='#c9bdab')
            source = load_image(textures[name]['standard_png'])
            after, _ = render(source, name, recipe)
            before = load_image(old[name]['packed_png'])
            for i, image in enumerate((before, after)):
                preview = strip(image, mode)
                sheet.paste(preview, (x+i*120, y+50), preview)
            d.text((x, y+585), 'Previous          No ornament', fill='#c9bdab')
    path = ROOT / 'assets/previews/seasonal-scaling-fix.png'
    if path.exists():
        raise FileExistsError(path)
    sheet.save(path)
    print(path)


if __name__ == '__main__':
    main()
