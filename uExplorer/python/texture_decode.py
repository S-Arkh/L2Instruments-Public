"""Preview pixel decoding only; serialized package interpretation stays in C++."""
import struct

FORMATS = {0: 'P8', 3: 'DXT1', 5: 'RGBA8 (BGRA storage)', 7: 'DXT3', 8: 'DXT5', 10: 'G16'}
MAX_PIXELS = 16 * 1024 * 1024


def property_value(texture, name, default=None):
    return next((t.get('value', default) for t in texture.get('tags', [])
                 if t['name'].casefold() == name.casefold()), default)


def faces(texture):
    return {t.get('subscript', 0): t['value'] for t in texture.get('tags', [])
            if t['name'].casefold() == 'faces' and isinstance(t.get('value'), dict)
            and 0 <= t.get('subscript', 0) < 6}


def rgb565(value):
    r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def decode_pixels(data, width, height, format_id, palette=None, masked=False):
    """Return tightly packed RGBA8; retain original package/palette unmodified."""
    if not 0 < width <= 16384 or not 0 < height <= 16384 or width*height > MAX_PIXELS:
        raise ValueError('Texture preview exceeds 16 million pixels or has invalid dimensions')
    area = width * height
    expected = (area if format_id == 0 else area*4 if format_id == 5 else
                area*2 if format_id == 10 else
                ((width+3)//4)*((height+3)//4)*(8 if format_id == 3 else 16)
                if format_id in (3, 7, 8) else None)
    if expected is None:
        raise ValueError('Unsupported texture preview format')
    if len(data) != expected:
        raise ValueError('Mip has no pixel storage' if not data else 'Invalid mip pixel storage size')
    if format_id == 5:
        out = bytearray(data)
        out[0::4], out[2::4] = data[2::4], data[0::4]
        return bytes(out)
    if format_id == 10:
        out = bytearray(area*4)
        # Fixed full-range 16-bit grayscale, no auto-contrast.
        out[0::4] = out[1::4] = out[2::4] = data[1::2]
        out[3::4] = b'\xff'*area
        return bytes(out)
    if format_id == 0:
        if palette is None or len(palette) != 256:
            raise ValueError('P8 preview requires a resolved 256-color palette')
        colors = []
        for i, color in enumerate(palette):
            if len(color) != 4 or any(not isinstance(v, int) or not 0 <= v <= 255 for v in color):
                raise ValueError('Invalid palette color')
            r, g, b, a = color  # UE1/UE2 FColor serialization is RGBA.
            colors.append(bytes((r, g, b, 0 if masked and i == 0 else a)))
        out = bytearray(area*4)
        for channel in range(4):
            out[channel::4] = data.translate(bytes(c[channel] for c in colors))
        return bytes(out)
    out = bytearray(area*4)
    stride = 8 if format_id == 3 else 16
    blocks_x = (width+3)//4
    for by in range((height+3)//4):
        for bx in range(blocks_x):
            block = data[(by*blocks_x+bx)*stride:(by*blocks_x+bx+1)*stride]
            color_offset = 0 if format_id == 3 else 8
            c0, c1, codes = struct.unpack_from('<HHI', block, color_offset)
            rgb0, rgb1 = rgb565(c0), rgb565(c1)
            colors = [(*rgb0, 255), (*rgb1, 255)]
            if c0 > c1 or format_id != 3:
                colors += [tuple((2*a+b)//3 for a, b in zip(rgb0, rgb1))+(255,),
                           tuple((a+2*b)//3 for a, b in zip(rgb0, rgb1))+(255,)]
            else:
                colors += [tuple((a+b)//2 for a, b in zip(rgb0, rgb1))+(255,), (0,0,0,0)]
            if format_id == 7:
                alpha_bits = int.from_bytes(block[:8], 'little')
                alphas = [((alpha_bits >> (i*4)) & 15)*17 for i in range(16)]
            elif format_id == 8:
                a0, a1 = block[:2]; table = [a0, a1]
                if a0 > a1:
                    table += [((7-i)*a0+i*a1)//7 for i in range(1, 7)]
                else:
                    table += [((5-i)*a0+i*a1)//5 for i in range(1, 5)] + [0,255]
                alpha_bits = int.from_bytes(block[2:8], 'little')
                alphas = [table[(alpha_bits >> (i*3)) & 7] for i in range(16)]
            for i in range(16):
                x, y = bx*4+i%4, by*4+i//4
                if x >= width or y >= height:
                    continue
                color = colors[(codes >> (i*2)) & 3]
                if format_id != 3:
                    color = color[:3]+(alphas[i],)
                offset = (y*width+x)*4; out[offset:offset+4] = bytes(color)
    return bytes(out)


def prepare_texture(core, path, document, level=0, face=-1, dependencies=()):
    """Keep selectors usable even when the selected mip cannot be decoded."""
    result = dict(level=level, face=face, mip_sizes=[])
    try:
        texture,path = resolve_texture(core, path, document, face,dependencies)
        result['mip_sizes'] = [(m['width'], m['height']) for m in texture.get('mips', [])]
        result.update(prepare_mip(core, path, texture, level,dependencies))
    except (ValueError, RuntimeError) as error:
        result['error'] = str(error)
    return result


def resolve_texture(core, path, document, face,dependencies=()):
    texture = document
    if face != -1:
        reference = faces(document).get(face)
        if not reference or not reference.get('id',0):
            raise ValueError('Cubemap face is absent')
        from material_graph import ResourceResolver
        path,identifier=ResourceResolver(core,dependencies).resolve(path,reference)
        texture = core.request(operation='texture', path=path, object_id=identifier)['result']
    return texture,path


def prepare_mip(core, path, texture, level,dependencies=()):
    mips = texture.get('mips', [])
    if not 0 <= level < len(mips):
        raise ValueError('Texture has no requested mip level')
    mip = mips[level]; format_id = property_value(texture, 'Format', 0)
    if mip['width'] * mip['height'] > MAX_PIXELS:
        raise ValueError('Mip exceeds 16 million pixels; select a smaller mip')
    palette = None
    if format_id == 0:
        reference = property_value(texture, 'Palette', {})
        if not isinstance(reference, dict) or not reference.get('id',0):
            raise ValueError('P8 palette is absent')
        from material_graph import ResourceResolver
        palette_path,identifier=ResourceResolver(core,dependencies).resolve(path,reference)
        palette = core.request(operation='palette', path=palette_path, object_id=identifier)['result']['colors']
    if len(mip['data_hex']) > 128*1024*1024:
        raise ValueError('Encoded mip exceeds 64 MiB')
    pixels = decode_pixels(bytes.fromhex(mip['data_hex']), mip['width'], mip['height'],
                           format_id, palette, property_value(texture, 'bMasked', False))
    return dict(pixels=pixels, width=mip['width'], height=mip['height'],
                format=FORMATS[format_id], level=level,
                mip_sizes=[(m['width'], m['height']) for m in mips])
