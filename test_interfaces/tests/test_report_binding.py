import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_client_report import verify


class ReportBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.system = self.root/'System'
        self.system.mkdir()
        hashes = {}
        for name in ('Interface.u', 'Interface.xdat', 'Core.dll', 'ExtensionL2.dll'):
            data = name.encode()
            (self.system/name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        self.manifest = self.root/'manifest.json'
        self.manifest.write_text(json.dumps(dict(profile='japan', build_identity='build-a', files=hashes)))
        self.report = self.system/'test.txt'
        self.text = ('Test button clicked.\nProfile=japan\nBuild=build-a\nRUN | check\n'
                     'PASS | check | actual=1 | expected=1\n'
                     'SKIP | pointer | pending\nTOTAL | PASS=1 | FAIL=0 | SKIP=1\n')
        self.report.write_text(self.text)

    def test_valid_binding_retains_skip(self):
        result = verify(self.manifest, self.system)
        self.assertTrue(result['artifact_binding_verified'])
        self.assertEqual(result['totals'], dict(PASS=1, FAIL=0, SKIP=1))

    def test_changed_artifact_rejected(self):
        (self.system/'Core.dll').write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'hashes differ'):
            verify(self.manifest, self.system)

    def test_stale_build_rejected(self):
        self.report.write_text(self.text.replace('build-a', 'build-b'))
        with self.assertRaisesRegex(ValueError, 'header differs'):
            verify(self.manifest, self.system)

    def test_truncated_or_forged_totals_rejected(self):
        for text in (self.text.rsplit('TOTAL', 1)[0], self.text.replace('PASS=1', 'PASS=2')):
            with self.subTest(text=text):
                self.report.write_text(text)
                with self.assertRaises(ValueError):
                    verify(self.manifest, self.system)

    def test_fail_is_bound_but_not_passed(self):
        self.report.write_text(self.text.replace('PASS | check', 'FAIL | check').replace('PASS=1 | FAIL=0', 'PASS=0 | FAIL=1'))
        result = verify(self.manifest, self.system)
        self.assertTrue(result['artifact_binding_verified'])
        self.assertFalse(result['tests_passed'])


if __name__ == '__main__':
    unittest.main()
