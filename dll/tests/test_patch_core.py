import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

EXAMPLE = Path(__file__).resolve().parents[1]
ROOT = EXAMPLE.parent / 'int64'
sys.path.insert(0, str(EXAMPLE / 'tools'))
sys.path.insert(0, str(ROOT / 'tools'))
from patch_core import patch_core, patch_bytes, checksum, CORE_SHA256, CLEAR_HF_SHA256
from check_core_dependencies import check
from verify_profile import PE
from local_paths import CLIENT, CLEAR_HF_SYSTEM


@unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1', 'Set L2_INTEGRATION=1 and external input paths')
class PatchTests(unittest.TestCase):
    def test_clear_hf_patch_preserves_required_exports(self):
        system = CLEAR_HF_SYSTEM
        source = system / 'Core.dll'
        original = PE(source)
        self.assertEqual(hashlib.sha256(original.data).hexdigest(), CLEAR_HF_SHA256)
        expected = {
            '?GRegisterNative@@YAEHABQ8UObject@@AEXAAUFFrame@@QAX@Z@Z': 0x5d680,
            '?GNatives@@3PAP8UObject@@AEXAAUFFrame@@QAX@ZA': 0xea6d0,
            '?Step@FFrame@@QAEXPAVUObject@@QAX@Z': 0x9200,
            '?execUndefined@UObject@@QAEXAAUFFrame@@QAX@Z': 0x5d290,
        }
        for name, rva in expected.items():
            self.assertEqual(original.exports[name], rva)
        self.assertEqual(original.rva(0x9200, 3), b'\x8b\x41\x0c')
        self.assertEqual(original.rva(0x921f, 3), b'\xc2\x08\x00')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'Core.dll'
            report = patch_core(source, output)
            patched = PE(output)
            self.assertEqual(report['profile'], 'clear_hf_0677e909')
            self.assertEqual(report['original_sha256'], CLEAR_HF_SHA256)
            self.assertEqual(patched.exports, original.exports)
            for _, rva, size, _ in original.sections:
                self.assertEqual(patched.rva(rva, size), original.rva(rva, size))
            result = check(system, output)
            self.assertTrue(result['compatible_imports'])
            self.assertGreater(result['checked']['Engine.dll'], 0)
            self.assertIn('?GetCPUCacheLineSize@L2UserHardWareInformation@@QBEHXZ', patched.exports)

    def test_previous_core_is_not_clear_hf_compatible(self):
        result = check(CLEAR_HF_SYSTEM, CLIENT)
        self.assertFalse(result['compatible_imports'])
        self.assertIn('?GetCPUCacheLineSize@L2UserHardWareInformation@@QBEHXZ', result['missing']['Engine.dll'])
        self.assertIn('?SetVGAInfo@L2UserHardWareInformation@@QAEXVFString@@T_LARGE_INTEGER@@@Z', result['missing']['D3DDrv.dll'])

    def test_patch_preserves_original_code_and_imports(self):
        source = CLIENT
        original = PE(source)
        before = hashlib.sha256(original.data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'Core.dll'
            report = patch_core(source, output)
            result = PE(output)
            self.assertEqual(before, CORE_SHA256)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(result.exports, original.exports)
            for _, rva, size, _ in original.sections:
                self.assertEqual(result.rva(rva, size), original.rva(rva, size))
            pe = struct.unpack_from('<I', result.data, 0x3c)[0]
            optional = pe + 24
            self.assertEqual(struct.unpack_from('<H', result.data, pe + 6)[0], len(original.sections) + 2)
            self.assertEqual(struct.unpack_from('<I', result.data, optional + 64)[0], checksum(result.data, optional + 64))
            original_import = struct.unpack_from('<I', original.data, optional + 104)[0]
            new_import = struct.unpack_from('<I', result.data, optional + 104)[0]
            offset = 0
            while any(original.rva(original_import + offset, 20)):
                self.assertEqual(original.rva(original_import + offset, 20), result.rva(new_import + offset, 20))
                offset += 20
            lookup, _, _, dll_name, iat = struct.unpack('<5I', result.rva(new_import + offset, 20))
            self.assertEqual(result.rva(dll_name, 16), b'ExtensionL2.dll\0')
            self.assertEqual(result.rva(lookup, 8), result.rva(iat, 8))
            self.assertEqual(result.rva(new_import + offset + 20, 20), bytes(20))
            entry = struct.unpack_from('<I', result.data, optional + 16)[0]
            stub = result.rva(entry, 43)
            self.assertEqual(stub[:3], b'\x55\x8b\xec')
            self.assertEqual(stub[12], 0xe8)
            self.assertEqual(entry + 17 + struct.unpack_from('<i', stub, 13)[0], int(report['original_entry_rva'], 16))
            self.assertEqual(stub[31:33], b'\xff\x91')
            self.assertEqual(struct.unpack_from('<I', stub, 33)[0], iat)
            self.assertEqual(stub[-3:], b'\xc2\x0c\x00')
            with self.assertRaises(ValueError):
                patch_core(source, output)

    def test_wrong_original_is_rejected(self):
        source = PE(CLIENT)
        changed = bytearray(source.data)
        changed[-1] ^= 1
        with self.assertRaises(ValueError):
            patch_bytes(changed, source)


if __name__ == '__main__':
    unittest.main()
