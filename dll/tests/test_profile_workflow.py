import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

EXAMPLE = Path(__file__).resolve().parents[1]
ROOT = EXAMPLE.parent / 'int64'
sys.path.insert(0, str(EXAMPLE / 'tools'))
from core_profiles import analyze, approved, catalog, header, PE
from check_installation import digest, resources, verify
from patch_core import patch_core
from validate_bundle import validate
from local_paths import CLIENT, CLEAR_HF_SYSTEM

integration = unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1',
                                  'Set L2_INTEGRATION=1 and external input paths')


class WorkflowTests(unittest.TestCase):
    def test_generated_header(self):
        self.assertEqual((EXAMPLE / 'src/client_profile.h').read_text(), header())

    @integration
    def test_approved_profiles(self):
        for p in (CLEAR_HF_SYSTEM / 'Core.dll', CLIENT):
            self.assertIsNotNone(analyze(p)['approved_profile'])
            self.assertIn(approved(PE(p))['name'], [x['name'] for x in catalog()['profiles']])

    @integration
    def test_unknown_core_is_reported_but_not_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / 'Core.dll'
            data = bytearray((CLEAR_HF_SYSTEM / 'Core.dll').read_bytes())
            data[-1] ^= 1
            candidate.write_bytes(data)
            result = analyze(candidate)
            self.assertIsNone(result['approved_profile'])
            self.assertFalse(result['missing_exports'])
            with self.assertRaises(ValueError):
                patch_core(candidate, Path(tmp) / 'patched.dll')
            self.assertFalse((Path(tmp) / 'patched.dll').exists())

    @integration
    def test_incorrect_approved_metadata_is_rejected(self):
        image = PE(CLEAR_HF_SYSTEM / 'Core.dll')
        for field in ('rva', 'code'):
            data = catalog()
            profile = next(p for p in data['profiles'] if p['sha256'] == digest(CLEAR_HF_SYSTEM / 'Core.dll'))
            if field == 'rva':
                profile['rvas']['step'] += 1
            else:
                profile['code']['register'] = '00' * 16
            with patch('core_profiles.catalog', return_value=data):
                with self.assertRaises(ValueError):
                    approved(image)

    def test_installation_hashes_missing_files_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / 'system'
            system.mkdir()
            names = ('Core.dll', 'ExtensionL2.dll', 'ExtensionL2.u', 'Engine.dll')
            for name in names:
                (system / name).write_bytes(name.encode())
            manifest = root / 'bundle.json'
            manifest.write_text(json.dumps(dict(schema=1, validation={'status': 'passed'},
                bundle_files={n: digest(system / n) for n in names[:3]},
                target_files={'Engine.dll': digest(system / 'Engine.dll')})))
            self.assertTrue(verify(system, manifest)['files_match'])
            self.assertFalse(resources(system)['conventional_layout_present'])
            for folder in ('Textures', 'SysTextures', 'Maps', 'StaticMeshes', 'Animations', 'Sounds'):
                (root / folder).mkdir()
            (root / 'Textures/Aden_broken_Castle_T.utx').touch()
            (root / 'SysTextures/Default.utx').touch()
            self.assertTrue(resources(system)['conventional_layout_present'])
            (system / 'Core.dll').write_bytes(b'different core')
            (system / 'ExtensionL2.dll').unlink()
            result = verify(system, manifest)
            self.assertFalse(result['files_match'])
            self.assertEqual(set(result['mismatches']), {'Core.dll', 'ExtensionL2.dll'})

    @unittest.skipUnless(os.environ.get('EXTENSION_TEST_TOOLS'), 'Set EXTENSION_TEST_TOOLS for real loader/VM validation')
    def test_real_bundle_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / 'bundle'
            tools = Path(os.environ['EXTENSION_TEST_TOOLS'])
            original = CLEAR_HF_SYSTEM / 'Core.dll'
            patch_core(original, bundle / 'Core.dll')
            shutil.copy2(tools / 'ExtensionL2.dll', bundle / 'ExtensionL2.dll')
            package = Path(os.environ['EXTENSION_TEST_PACKAGE'])
            shutil.copy2(package, bundle / 'ExtensionL2.u')
            report = validate(original, bundle, CLEAR_HF_SYSTEM, tools,
                              Path(os.environ['EXTENSION_TEST_BYTECODE']), os.environ.get('EXTENSION_TEST_WINE'))
            self.assertEqual(len(report['validation']['tests']), 5)
            self.assertEqual(report['validation']['status'], 'passed')
            with self.assertRaises(ValueError):
                validate(original, bundle, CLEAR_HF_SYSTEM, tools,
                         Path(os.environ['EXTENSION_TEST_BYTECODE']), os.environ.get('EXTENSION_TEST_WINE'))


if __name__ == '__main__':
    unittest.main()
