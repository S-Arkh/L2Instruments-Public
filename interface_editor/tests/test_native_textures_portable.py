"""Native tests runnable with the embedded Windows Python, without Qt/pytest."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('INTERFACE_MODULE_DIR', str(ROOT / 'app')))
from _interface_core import TextureStore, build_texture_package, decode_texture


class NativeTextureTests(unittest.TestCase):
    def test_write_read_and_rebuild(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'NativePreview.utx'
            pixel = bytes([200, 50, 100, 160]) * (32 * 16)
            asset = dict(name='Button', group='Buttons', width=32, height=16,
                         content_width=30, content_height=15, rgba=pixel)
            guid = bytes(range(16))
            encoded = build_texture_package('NativePreview', [asset], guid)
            path.write_bytes(encoded)
            raw = bytes(v ^ (sum(path.name.lower().encode()) & 255) for v in encoded[28:])
            self.assertEqual(struct.unpack_from('<II', raw), (0x9e2a83c1, 125 | (38 << 16)))
            self.assertEqual(raw[36:52], guid)
            texture = TextureStore(folder).load('NativePreview.Buttons.Button')
            self.assertEqual(texture['rgba'], pixel)
            self.assertEqual(texture['grid'], [0, 30, 30, 0, 15, 15])
            self.assertEqual(build_texture_package('NativePreview', [asset], guid), encoded)

    def test_dxt_transparency(self):
        block = struct.pack('<HHI', 0, 0xffff, 0xffffffff)
        self.assertEqual(decode_texture(3, 4, 4, block)['rgba'], bytes(64))

    @unittest.skipUnless(os.environ.get('INTERFACE_CLIENT_RESOURCES'), 'Set INTERFACE_CLIENT_RESOURCES')
    def test_client_resource(self):
        store = TextureStore(os.environ['INTERFACE_CLIENT_RESOURCES'])
        texture = store.load('L2UI_CT1.Button.Button_DF')
        self.assertEqual((texture['width'], texture['height']), (32, 32))
        self.assertEqual(texture['grid'], [13, 15, 29, 27, 27, 27])
        store.load('L2UI_CT1.Windows.Windows_DF_Drawer_Bg')
        self.assertEqual(store.package_reads, 1)


if __name__ == '__main__': unittest.main(verbosity=2)
