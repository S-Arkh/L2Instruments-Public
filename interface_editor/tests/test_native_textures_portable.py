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

    def test_package_133_40_texture_and_version_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ModernPreview.utx'
            pixels = bytes([10, 20, 30, 255]) * 16
            def index(value):
                sign = 128 if value < 0 else 0
                value = abs(value)
                result = bytearray([sign | (value & 63) | (64 if value > 63 else 0)])
                value >>= 6
                while value:
                    result.append((value & 127) | (128 if value > 127 else 0))
                    value >>= 7
                return bytes(result)
            names = ['None', 'Core', 'Package', 'Engine', 'Class', 'Texture', 'USize', 'VSize', 'Format', 'Button']
            table = b''.join(index(len(n) + 1) + n.encode() + b'\0' + bytes(4) for n in names)
            imports = b'\x01\x02' + bytes(4) + b'\x03\x01\x04' + struct.pack('<i', -1) + b'\x05'
            offset = 36 + len(table) + len(imports)
            # Properties, 92-byte material prefix (133/40), empty metadata, one BGRA mip.
            payload = b'\x06\x22' + struct.pack('<I', 4) + b'\x07\x22' + struct.pack('<I', 4)
            payload += b'\x08\x01\x05\0' + bytes(92) + bytes(6)
            payload += b'\x01' + bytes(4) + index(64) + bytes([30, 20, 10, 255]) * 16
            payload += struct.pack('<II', 4, 4) + b'\x02\x02'
            exports = index(-2) + b'\0' + bytes(4) + b'\x09' + bytes(4) + index(len(payload)) + index(offset)
            raw = bytearray(struct.pack('<IHH7I', 0x9e2a83c1, 133, 40, 0, len(names), 36,
                                        1, offset + len(payload), 2, 36 + len(table)) + table + imports + payload + exports)
            envelope = 'Lineage2Ver121'.encode('utf-16le')
            key = sum(path.name.lower().encode()) & 255
            path.write_bytes(envelope + bytes(v ^ key for v in raw))
            self.assertEqual(TextureStore(folder).load('ModernPreview.Button')['rgba'], pixels)
            struct.pack_into('<HH', raw, 4, 133, 41)
            path.write_bytes(envelope + bytes(v ^ key for v in raw))
            with self.assertRaisesRegex(RuntimeError, 'Unsupported Unreal texture package version'):
                TextureStore(folder).load('ModernPreview.Button')

    @unittest.skipUnless(os.environ.get('INTERFACE_CLIENT_RESOURCES'), 'Set INTERFACE_CLIENT_RESOURCES')
    def test_client_resource(self):
        store = TextureStore(os.environ['INTERFACE_CLIENT_RESOURCES'])
        texture = store.load('L2UI_CT1.Button.Button_DF')
        self.assertEqual((texture['width'], texture['height']), (32, 32))
        self.assertEqual(texture['grid'], [13, 15, 29, 27, 27, 27])
        store.load('L2UI_CT1.Windows.Windows_DF_Drawer_Bg')
        self.assertEqual(store.package_reads, 1)


if __name__ == '__main__': unittest.main(verbosity=2)
