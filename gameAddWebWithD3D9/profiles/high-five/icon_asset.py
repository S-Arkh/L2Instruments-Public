"""Generate the browser's 32px bronze-framed, italic E icon (no external tools)."""
from pathlib import Path
import math
import struct
import zlib

ROOT = Path(__file__).resolve().parent

def inside(x, y, points):
    result = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj-xi)*(y-yi)/(yj-yi)+xi:
            result = not result
        j = i
    return result

def render():
    # A custom slanted E silhouette, with a warm metal face and dark bevel.
    letter = [(12,7),(25,7),(24,10),(16,10),(15,14),(22,14),
              (21,17),(14,17),(13,22),(22,22),(21,25),(8,25)]
    def pixel(x, y):
        edge = min(x, y, 32-x, 32-y)
        if edge < 1: return (22,22,19)
        if edge < 2: return (151,143,111) if x+y < 32 else (57,51,35)
        if edge < 3: return (66,62,46) if x+y < 32 else (183,163,111)
        if edge < 4: return (15,19,19)
        glow = max(0, 1-math.hypot(x-16,y-12)/24)
        color = (int(22+17*glow), int(29+20*glow), int(29+16*glow))
        if inside(x-1, y-1, letter): color = (5,8,8)
        if inside(x, y, letter):
            color = (int(239-y*2), int(220-y*2.6), int(161-y*2.4))
            if not inside(x-.65, y-.65, letter): color = (255,242,192)
            elif not inside(x+.65, y+.65, letter): color = (110,77,29)
        return color
    rgba = bytearray()
    for y in range(32):
        for x in range(32):
            samples = [pixel(x+(sx+.5)/4,y+(sy+.5)/4) for sy in range(4) for sx in range(4)]
            rgba.extend(sum(p[c] for p in samples)//16 for c in range(3))
            rgba.append(255)
    return bytes(rgba)

def write_assets():
    folder = ROOT / 'assets'
    folder.mkdir(exist_ok=True)
    rgba = render()
    bgra = b''.join(bytes((rgba[i+2],rgba[i+1],rgba[i],rgba[i+3])) for i in range(0,len(rgba),4))
    header = bytearray(18)
    header[2] = 2
    # UE2's importer assumes bottom-up TGA even when the top-origin flag is set.
    struct.pack_into('<HHBB',header,12,32,32,32,0x08)
    bottom_up = b''.join(bgra[y*128:(y+1)*128] for y in reversed(range(32)))
    (folder/'BrowserIcon.tga').write_bytes(header+bottom_up)
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,6,0,0,0))
    png += chunk(b'IDAT',zlib.compress(b''.join(b'\0'+rgba[y*128:(y+1)*128] for y in range(32))))
    (folder/'BrowserIcon.png').write_bytes(png+chunk(b'IEND',b''))
    return folder/'BrowserIcon.tga'

if __name__ == '__main__': write_assets()
