"""Standalone unittest: also runs with the portable Windows Python under Wine."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('INTERFACE_MODULE_DIR', str(ROOT / 'app')))
from _interface_core import Document


class SaveRegression(unittest.TestCase):
    def setUp(self):
        self.document = Document((ROOT / 'schemas/schemas.json').read_text(encoding='utf-8'))
        self.original = (ROOT / 'tests/fixtures/Interface_high_five.xdat').read_bytes()
        self.document.load_bytes(self.original, 'ct26.XDAT')
        self.button = next(n for n in self.document.search('btnCredit')['matches']
                           if self.document.info(n)['type'] == 'Button')

    def test_existing_backup_and_repeated_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            # Cyrillic plus spaces also exercises the Win32 wide-path API.
            folder = Path(directory) / '\u0422\u0435\u0441\u0442 System'
            folder.mkdir()
            target = folder / 'Interface.xdat'
            backup = folder / 'Interface.xdat.bak'
            target.write_bytes(self.original)
            backup.write_bytes(b'previous backup already exists')
            previous = self.original
            for name in ('btnSaveFirst', 'btnSaveSecond', 'btnSaveThird'):
                self.document.set(self.button, 'name', name)
                expected = self.document.serialize()
                self.document.save(str(target))
                self.assertEqual(target.read_bytes(), expected)
                self.assertEqual(backup.read_bytes(), previous)
                self.assertFalse(self.document.summary()['dirty'])
                self.assertEqual(sorted(p.name for p in folder.iterdir()), ['Interface.xdat', 'Interface.xdat.bak'])
                previous = expected

    def test_failed_backup_keeps_original_and_dirty_document(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'Interface.xdat'
            target.write_bytes(self.original)
            backup = Path(directory) / 'Interface.xdat.bak'
            backup.mkdir()  # A directory must not be replaced by a backup file.
            sentinel = backup / 'keep.txt'
            sentinel.write_text('preserve me')
            self.document.set(self.button, 'name', 'btnNotSaved')
            with self.assertRaises(RuntimeError):
                self.document.save(str(target))
            self.assertEqual(target.read_bytes(), self.original)
            self.assertEqual(sentinel.read_text(), 'preserve me')
            self.assertTrue(self.document.summary()['dirty'])
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['Interface.xdat', 'Interface.xdat.bak'])

    def test_save_new_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'new.xdat'
            self.document.save(str(target))
            self.assertEqual(target.read_bytes(), self.original)
            self.assertFalse(target.with_suffix('.xdat.bak').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
