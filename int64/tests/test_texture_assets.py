import sys
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package, FormatError
from texture_assets import p8_texture, encode_pcx, texture, encode_tga
from local_paths import PACKAGES


@unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1', 'Set L2_INTEGRATION=1 and external input paths')
class TextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Package(PACKAGES / 'Engine.u')

    def test_original_texture_pixels_round_trip_pcx(self):
        for name, size in [('S_Actor', 32), ('S_LockLocation', 16), ('S_AutoAlignToTerrain', 16)]:
            with self.subTest(name=name):
                w, h, pixels, palette = p8_texture(self.package, name)
                self.assertEqual((w, h), (size, size))
                pcx = encode_pcx(w, h, pixels, palette)
                self.assertEqual(pcx[:4], bytes([10, 5, 1, 8]))
                self.assertEqual(pcx[-769:], b'\x0c' + palette)
                decoded = bytearray()
                i = 128
                while i < len(pcx) - 769:
                    b = pcx[i]
                    i += 1
                    if b >= 192:
                        decoded.extend([pcx[i]] * (b & 63))
                        i += 1
                    else:
                        decoded.append(b)
                self.assertEqual(bytes(decoded), pixels)

    def test_non_texture_rejected(self):
        with self.assertRaises(FormatError):
            p8_texture(self.package, 'Actor')

    def test_texture_and_class_name_collision(self):
        w, h, pixels, _ = p8_texture(self.package, 'SubActionFOV')
        self.assertEqual((w, h, len(pixels)), (32, 32, 1024))

    def test_rgba_mips_to_tga(self):
        w, h, pixels, palette = texture(self.package, 'WireframeTexture')
        self.assertEqual((w, h), (256, 256))
        self.assertIsNone(palette)
        tga = encode_tga(w, h, pixels)
        self.assertEqual(tga[16:18], b'\x20\x28')
        self.assertEqual(tga[18:], pixels)


if __name__ == '__main__':
    unittest.main()
