"""Recover PCX/TGA import sources from supplied Engine.u texture exports.

Only P8/RGBA8 textures with validated mip serialization are
supported. Missing/unsupported assets are reported rather than replaced.
"""
import hashlib
from pathlib import Path
import re
import struct
from ue2package import Package, Reader, FormatError


def properties(package, reader):
    result = {}
    while True:
        name = package.name(reader.index())
        if name == 'None':
            return result
        info = reader.byte()
        kind = info & 15
        if kind == 10:
            package.name(reader.index())
        code = (info >> 4) & 7
        size = (1, 2, 4, 12, 16)[code] if code < 5 else reader.unpack({5: '<B', 6: '<H', 7: '<I'}[code])
        if kind == 3:
            value = bytes([bool(info & 128)])
        else:
            if info & 128:
                index = reader.byte()
                if index & 0xc0 == 0xc0:
                    reader.take(3)
                elif index & 128:
                    reader.take(1)
            value = reader.take(size)
        result[name.casefold()] = value


def texture(package, name):
    matches = [e for i, e in enumerate(package.exports, 1)
               if package.ref(i).casefold() == name.casefold()
               and package.ref(e.cls).split('.')[-1].casefold() == 'texture']
    if len(matches) != 1:
        raise FormatError(f'{name}: expected one Texture export, got {len(matches)}')
    entry = matches[0]
    if package.ref(entry.cls).split('.')[-1].casefold() != 'texture' or entry.flags & 0x02000000:
        raise FormatError(f'{name}: unsupported texture class/stack')
    data = package.data[entry.offset:entry.offset + entry.size]
    reader = Reader(data)
    tags = properties(package, reader)
    fmt = tags.get('format', b'\0')
    if fmt not in (b'\0', b'\x05'):
        raise FormatError(f'{name}: unsupported texture format {fmt.hex()}')
    if len(tags.get('usize', b'')) != 4 or len(tags.get('vsize', b'')) != 4:
        raise FormatError(f'{name}: missing texture dimensions')
    width, height = struct.unpack('<I', tags['usize'])[0], struct.unpack('<I', tags['vsize'])[0]
    if not (0 < width <= 4096 and 0 < height <= 4096):
        raise FormatError('Unsupported dimensions')
    palette_bytes = None
    if fmt == b'\0':
        palette_ref = Reader(tags.get('palette', b'')).index()
        if not 0 < palette_ref <= len(package.exports):
            raise FormatError('Palette must be an export in the same package')
        palette = package.exports[palette_ref - 1]
        if package.ref(palette.cls).split('.')[-1].casefold() != 'palette':
            raise FormatError('Wrong palette class')
        pr = Reader(package.data[palette.offset:palette.offset + palette.size])
        properties(package, pr)
        if pr.index() != 256:
            raise FormatError('Expected a 256-color palette')
        palette_bytes = pr.take(1024)
        if pr.pos != len(pr.data):
            raise FormatError('Unexpected palette payload')
    matches = []
    # Licensee-specific native texture metadata precedes the mip array.
    # Find a unique complete sequence whose skip offsets, sizes and bit counts
    # all match; never identify pixels merely by a byte-pattern search.
    for start in range(reader.pos, min(reader.pos + 1024, len(data))):
        r = Reader(data, start)
        try:
            count = r.index()
            if not 1 <= count <= 16:
                continue
            first = None
            for mip in range(count):
                skip = r.unpack('<I')
                size = r.index()
                pixels = r.take(size)
                if skip != entry.offset + r.pos:
                    raise FormatError('Wrong lazy-array skip offset')
                w, h = r.unpack('<I'), r.unpack('<I')
                ubits, vbits = r.byte(), r.byte()
                bytes_per_pixel = 1 if fmt == b'\0' else 4
                if (w, h) != (max(1, width >> mip), max(1, height >> mip)) or size != w * h * bytes_per_pixel:
                    raise FormatError('Wrong mip dimensions')
                if w != 1 << ubits or h != 1 << vbits:
                    raise FormatError('Wrong mip bit counts')
                if mip == 0:
                    first = pixels
            if r.pos == len(data):
                matches.append(first)
        except FormatError:
            continue
    if len(matches) != 1:
        raise FormatError(f'{name}: expected one valid mip sequence, got {len(matches)}')
    return width, height, matches[0], palette_bytes


def p8_texture(package, name):
    width, height, pixels, bgra = texture(package, name)
    if bgra is None:
        raise FormatError(f'{name} is not paletted')
    rgb = bytes(c for i in range(0, 1024, 4) for c in (bgra[i + 2], bgra[i + 1], bgra[i]))
    return width, height, pixels, rgb


def encode_tga(width, height, pixels):
    if len(pixels) != width * height * 4:
        raise ValueError('Invalid BGRA8 buffer')
    header = bytearray(18)
    header[2] = 2  # uncompressed true color
    struct.pack_into('<HHBB', header, 12, width, height, 32, 0x28)  # top origin, 8 alpha bits
    return bytes(header) + pixels


def encode_pcx(width, height, pixels, palette):
    if len(pixels) != width * height or len(palette) != 768:
        raise ValueError('Invalid P8 image dimensions/palette')
    stride = (width + 1) & ~1
    header = bytearray(128)
    struct.pack_into('<4B6H', header, 0, 10, 5, 1, 8, 0, 0, width - 1, height - 1, width, height)
    header[65] = 1
    struct.pack_into('<HH', header, 66, stride, 1)
    encoded = bytearray(header)
    for y in range(height):
        row = pixels[y * width:(y + 1) * width] + bytes(stride - width)
        i = 0
        while i < len(row):
            run = 1
            while run < 63 and i + run < len(row) and row[i + run] == row[i]:
                run += 1
            if run > 1 or row[i] >= 192:
                encoded.extend((192 | run, row[i]))
            else:
                encoded.append(row[i])
            i += run
    return bytes(encoded) + b'\x0c' + palette


def recover_imports(package_path, destination):
    package = Package(package_path)
    report = {'package_sha256': package.sha256, 'recovered': {}, 'unresolved': {}}
    for source in (destination / 'Classes').glob('*.uc'):
        text = source.read_bytes().decode('latin1')
        for line in text.splitlines():
            if not re.match(r'\s*#exec\s+Texture\s+Import\s', line, re.I):
                continue
            args = {m[1].casefold(): m[2].strip('"') for m in re.finditer(r'(\w+)\s*=\s*("[^"]*"|\S+)', line)}
            filename = args.get('file', '').replace('\\', '/')
            relative = Path(filename)
            name = args.get('name', relative.stem)
            parts = list(relative.parts)
            if len(parts) >= 2 and parts[0] == '..' and parts[1].casefold() == destination.name.casefold():
                parts = parts[2:]
            if parts and parts[0].casefold() == 'textures':
                parts[0] = 'Textures'
            relative = Path(*parts)
            if relative.is_absolute() or '..' in relative.parts or not filename or not name:
                report['unresolved'][filename] = 'Unsupported import path/name'
                continue
            target = destination / relative
            if target.exists():
                continue
            if relative.suffix.casefold() not in ('.pcx', '.tga'):
                report['unresolved'][filename] = 'Only PCX/TGA recovery is implemented'
                continue
            full_name = args.get('group', '')
            full_name = full_name + '.' + name if full_name else name
            try:
                if relative.suffix.casefold() == '.pcx':
                    width, height, pixels, palette = p8_texture(package, full_name)
                    image = encode_pcx(width, height, pixels, palette)
                else:
                    width, height, pixels, palette = texture(package, full_name)
                    if palette is not None:
                        pixels = b''.join(palette[i * 4:i * 4 + 4] for i in pixels)
                    image = encode_tga(width, height, pixels)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(image)
                report['recovered'][filename] = dict(export=full_name, width=width, height=height,
                    pixels_sha256=hashlib.sha256(pixels).hexdigest(), image_sha256=hashlib.sha256(image).hexdigest())
            except (FormatError, ValueError) as error:
                report['unresolved'][filename] = str(error)
    return report
