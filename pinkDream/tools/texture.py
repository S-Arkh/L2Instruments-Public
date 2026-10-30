"""Strict embedded mip reader for Lineage II UE2 123/37 and 125/38."""
import struct
from PIL import Image
from inventory import Reader

FORMATS = {3: 'DXT1', 5: 'BGRA8', 7: 'DXT3', 8: 'DXT5'}


def string(r):
    n = r.index()
    r.take(abs(n) * (2 if n < 0 else 1))


def texture(package, entry):
    if (package['version'], package['licensee']) not in ((123, 37), (125, 38)):
        raise ValueError('Unsupported texture serialization version')
    base = entry['offset']
    r = Reader(package['_data'][base:base + entry['size']])
    names, props = package['_names'], {}
    while True:
        idx = r.index()
        if not 0 <= idx < len(names):
            raise ValueError('Invalid property name')
        name = names[idx]
        if name == 'None':
            break
        info = r.number('B')
        kind, size_code = info & 15, (info >> 4) & 7
        if kind == 10:
            r.index()  # struct name precedes size extension
        size = [1, 2, 4, 12, 16][size_code] if size_code < 5 else r.number(['B', '<H', '<I'][size_code - 5])
        if info & 128 and kind != 3:
            first = r.number('B')
            if first & 128:
                r.take(3 if first & 64 else 1)
        value = r.take(size) if kind != 3 else bytes([bool(info & 128)])
        props[name] = value
    r.take(36)  # FLineageShaderProperty, version <129: fixed fields
    stages = r.index()
    if not 0 <= stages <= 1024:
        raise ValueError('Invalid material stages')
    for _ in range(stages):
        string(r)
        count = r.index()
        if not 0 <= count <= 1024:
            raise ValueError('Invalid stage strings')
        for _ in range(count):
            string(r)
    string(r)  # shader code
    r.take(4)  # material version
    count = r.index()
    if not 1 <= count <= 16:
        raise ValueError('Invalid mip count')
    fmt = props.get('Format', b'\0')[0]
    if fmt not in FORMATS:
        raise ValueError(f'Unsupported texture format {fmt}')
    mips = []
    for _ in range(count):
        lazy_end = r.number('<i')
        length = r.index()
        offset = r.pos
        pixels = r.take(length)
        if lazy_end != base + r.pos:
            raise ValueError('Lazy array end mismatch')
        w, h = r.number('<i'), r.number('<i')
        ub, vb = r.number('B'), r.number('B')
        if not 1 <= w <= 8192 or not 1 <= h <= 8192:
            raise ValueError('Invalid mip size')
        expected = w * h * 4 if fmt == 5 else ((w + 3) // 4) * ((h + 3) // 4) * (8 if fmt == 3 else 16)
        if length != expected:
            raise ValueError(f'Mip size mismatch: {length} != {expected}')
        mips.append({'offset': base + offset, 'length': length, 'size': [w, h], 'data': pixels})
    if r.pos != entry['size']:
        raise ValueError(f'Unparsed texture tail: {entry["size"] - r.pos}')
    for key, dim in [('USize', 0), ('VSize', 1)]:
        if key in props and struct.unpack('<i', props[key])[0] != mips[0]['size'][dim]:
            raise ValueError('Property dimensions differ from top mip')
    return {'format': fmt, 'mips': mips}


def decode(data, size, fmt):
    if fmt == 5:
        return Image.frombytes('RGBA', tuple(size), data, 'raw', 'BGRA')
    return Image.frombytes('RGBA', tuple(size), data, 'bcn', ({3: 1, 7: 2, 8: 3}[fmt], FORMATS[fmt]))


def pink(rgb):
    # Preserve luminance/detail, lift highlights towards blush pink.
    y = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000 / 255
    return tuple(round(a + (b - a) * y) for a, b in zip((24, 8, 22), (255, 190, 225)))


def tint(data, fmt):
    out = bytearray(data)
    if fmt == 5:
        for i in range(0, len(out), 4):
            red, green, blue = pink((out[i + 2], out[i + 1], out[i]))
            out[i:i + 3] = bytes((blue, green, red))
        return bytes(out)
    stride = 8 if fmt == 3 else 16
    for block in range(0, len(out), stride):
        i = block + (0 if fmt == 3 else 8)
        c0, c1 = struct.unpack_from('<HH', out, i)
        def convert(c):
            rgb = ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)
            r, g, b = pink(rgb)
            return (round(r * 31 / 255) << 11) | (round(g * 63 / 255) << 5) | round(b * 31 / 255)
        a, b = convert(c0), convert(c1)
        # DXT1 endpoint order selects alpha mode. Preserve mode and index bits.
        if fmt == 3 and (a > b) != (c0 > c1):
            if a != b:
                a, b = b, a
            elif c0 > c1:
                a, b = (a + 1, b) if a < 65535 else (a, b - 1)
        struct.pack_into('<HH', out, i, a, b)
    return bytes(out)
