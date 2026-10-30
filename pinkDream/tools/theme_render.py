"""Deterministic seasonal rendering from standard artwork, never from a prior theme."""
import math
from PIL import Image, ImageDraw, ImageOps


def role(name, size):
    n = name.lower()
    w, h = size
    if any(x in n for x in ('equipslot', 'jewelslot', 'inventoryback', 'slotbox', 'equipbg', 'brooch', 'mask')):
        return 'atlas'
    # Small tiled/stretched pieces must never receive corner art or stripes.
    # Match before 'btn' and horizontal 'frame': these groups include scrollbar
    # arrow buttons and tiny frame slices used by the shortcut drag rail.
    if any(x in n for x in ('scrollbar', 'windowscroll', 'slider', 'sizecontrol')):
        return 'plain-control' if ('btn' in n or 'scrollup' in n or 'scrolldown' in n) else 'stretch'
    if ('frame' in n and ('_ver_' in n or '_hor_small_' in n or '_tile' in n)):
        return 'stretch'
    if 'frame' in n and min(w, h) <= 16 and 'btn' not in n:
        return 'stretch'
    if 'radarmap_df_bg' in n or n.endswith('radar_back') or n.endswith('radarback'):
        return 'radar'
    if ('hor' in n and ('frame' in n)) or 'titlebar' in n:
        return 'title'
    if any(x in n for x in ('button', 'btn', 'tab_', 'chattab', 'chatting_tab')):
        return 'control'
    if any(x in n for x in ('frame', 'ring', 'scroll', 'slider')):
        return 'trim'
    return 'surface'


def halloween(source, name, recipe, kind):
    p, cfg = recipe['palette'], recipe['decoration']
    gray = ImageOps.grayscale(source)
    alpha = source.getchannel('A')
    tinted = ImageOps.colorize(gray, p['shadow'], p['bone'], mid=p['purple'])
    if kind in ('atlas', 'surface'):
        image = Image.blend(source.convert('RGB'), tinted, .28).convert('RGBA')
    else:
        image = tinted.convert('RGBA')
    d = ImageDraw.Draw(image)
    opaque = alpha.point(lambda a: 255 if a >= 180 else 0)
    box = opaque.getbbox()
    if box and kind in ('title', 'radar', 'trim', 'control'):
        x0, y0, x1, y1 = box
        if kind == 'control':
            d.line((x0, y0, x1-1, y0), fill=p['pumpkin'], width=2)
        if kind in ('title', 'trim', 'radar'):
            # Corner webs remain inside the original material silhouette.
            radius = min(cfg['web_radius'], (x1-x0)//2, (y1-y0)//2)
            for corner, sign in ((x0, 1), (x1-1, -1)):
                for angle in (0, math.pi/6, math.pi/3, math.pi/2):
                    d.line((corner, y0, corner+sign*round(radius*math.cos(angle)), y0+round(radius*math.sin(angle))), fill=p['web'])
                for r in range(5, radius+1, 5):
                    pts = [(corner+sign*round(r*math.cos(a*math.pi/12)), y0+round(r*math.sin(a*math.pi/12))) for a in range(7)]
                    d.line(pts, fill=p['web'])
        if kind == 'title' and x1-x0 >= 24 and y1-y0 >= 20:
            py = min(y1-7, y0+14)
            # Pumpkins and bones alternate; the middle of the text area is left quiet.
            for index, x in enumerate(range(x0+10, x1-6, cfg['ornament_spacing'])):
                if index % 2 == 0:
                    d.ellipse((x-6, py-5, x+6, py+5), fill=p['pumpkin'], outline=p['orange_shadow'])
                    d.arc((x-3, py-5, x+3, py+5), 90, 270, fill=p['orange_shadow'])
                    d.line((x, py-7, x+1, py-5), fill=p['stem'], width=2)
                    d.polygon([(x-4, py-2), (x-1, py-2), (x-2, py)], fill=p['shadow'])
                    d.polygon([(x+1, py-2), (x+4, py-2), (x+2, py)], fill=p['shadow'])
                    d.line((x-2, py+2, x, py+3, x+3, py+2), fill=p['shadow'])
                else:
                    d.line((x-5, py, x+5, py+2), fill=p['bone'], width=2)
                    for bx, by in ((x-5, py), (x+5, py+2)):
                        d.ellipse((bx-2, by-2, bx+1, by+1), fill=p['bone'])
                        d.ellipse((bx-1, by, bx+2, by+3), fill=p['bone'])
            if x1-x0 >= 80:
                sx, sy = x1-12, min(y1-5, y0+22)
                d.line((sx, y0, sx, sy), fill=p['web'])
                d.ellipse((sx-2, sy-2, sx+2, sy+2), fill=p['spider'])
                for dy in (-2, 0, 2):
                    d.line((sx-5, sy+dy-2, sx, sy+dy, sx+5, sy+dy-2), fill=p['spider'])
    image.putalpha(alpha)
    return image, kind


def render(source, name, recipe, role_override=None):
    alpha = source.getchannel('A')
    gray = ImageOps.grayscale(source)
    if recipe['algorithm'] == 'glamour-standard-v1':
        out = ImageOps.colorize(gray, recipe['palette']['shadow'], recipe['palette']['highlight']).convert('RGBA')
        out.putalpha(alpha)
        return out, 'pink'
    kind = role_override or role(name, source.size)
    if kind not in ('atlas', 'surface', 'title', 'radar', 'control', 'trim', 'stretch', 'plain-control'):
        raise ValueError('Unknown resource role')
    if kind in ('stretch', 'plain-control'):
        # Keep the standard bevels/arrow glyphs and each state's original lightness,
        # but introduce no new spatial detail that tiling/stretching can break.
        p = recipe['palette']
        highlight = p['plain_control_light'] if kind == 'plain-control' else p['stretch_light']
        out = ImageOps.colorize(gray, p['stretch_shadow'], highlight).convert('RGBA')
        out.putalpha(alpha)
        return out, kind
    if recipe['algorithm'] == 'halloween-standard-v2':
        return halloween(source, name, recipe, kind)
    if recipe['algorithm'] != 'christmas-candy-v3':
        raise ValueError('Unknown theme renderer')
    p, cfg = recipe['palette'], recipe['decoration']
    w, h = source.size
    if kind == 'atlas':
        # Preserve slot symbols and atlas topology; no procedural drawings across regions.
        out = Image.blend(source.convert('RGB'), ImageOps.colorize(gray, '#091a13', p['cream']), .24).convert('RGBA')
    elif kind == 'surface':
        out = Image.blend(source.convert('RGB'), ImageOps.colorize(gray, '#07170f', p['cream']), .32).convert('RGBA')
    else:
        accent = p['candy'] if kind == 'control' else p['fir']
        out = ImageOps.colorize(gray, '#100d0b', p['cream'], mid=accent).convert('RGBA')
    d = ImageDraw.Draw(out)
    # Decorations use the existing visible silhouette; alpha/UV and hit area stay intact.
    opaque = alpha.point(lambda a: 255 if a >= 180 else 0)
    box = opaque.getbbox()
    if box and kind in ('title', 'radar', 'control', 'trim'):
        x0, y0, x1, y1 = box
        if kind == 'control':
            # Candy edge only; retain the original central glyph/detail.
            for x in range(x0, x1):
                color = p['candy'] if ((x + y0) // cfg['stripe_width']) % 2 else p['cream']
                d.line((x, y0, x, min(y0 + 1, y1 - 1)), fill=color)
        if kind in ('title', 'trim'):
            # Follow the alpha contour instead of painting a rectangle over cutouts.
            for x in range(x0, x1):
                ys = [y for y in range(y0, y1) if opaque.getpixel((x, y))]
                if ys:
                    y = ys[0]
                    for yy in range(y, min(y + cfg['stripe_depth'], y1)):
                        color = p['candy'] if ((x + yy) // cfg['stripe_width']) % 2 else p['cream']
                        d.point((x, yy), fill=color)
        if kind == 'title' and w >= 24 and h >= 24:
            # Fir strand, coloured fairy lights and hanging baubles on title segments.
            ybase = min(y1 - 6, y0 + 8)
            points = [(x, ybase + round(3 * math.sin((x-x0) * math.pi / max(1, x1-x0)))) for x in range(x0, x1)]
            if len(points) > 1:
                d.line(points, fill=p['fir'], width=3)
            for k, x in enumerate(range(x0 + 5, x1 - 2, cfg['garland_spacing'])):
                y = ybase + round(3 * math.sin((x-x0) * math.pi / max(1, x1-x0)))
                color = p['lights'][k % len(p['lights'])]
                r = cfg['bulb_radius']
                d.line((x, y, x, y+4), fill=p['gold'])
                d.ellipse((x-r, y+3-r, x+r, y+3+r), fill=color)
                if k % 2 == 0 and y + 13 < y1:
                    r = cfg['ornament_radius']
                    d.line((x+7, y, x+7, y+9), fill=p['gold'])
                    d.ellipse((x+7-r, y+9-r, x+7+r, y+9+r), fill=p['candy'])
                    d.point((x+6, y+7), fill=p['cream'])
        if kind == 'radar':
            # Follow visible decorative border, avoiding map centre/mask.
            candidates = []
            for x in range(x0, x1, 14):
                ys = [y for y in range(y0, y1) if opaque.getpixel((x, y))]
                if ys:
                    candidates.append((x, ys[0]))
            for k, (x, y) in enumerate(candidates):
                d.ellipse((x-2, y, x+2, y+4), fill=p['lights'][k % len(p['lights'])])
    out.putalpha(alpha)
    return out, kind
