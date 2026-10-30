"""Native DAT regression suite for embedded Windows Python (no pytest/Qt)."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('INTERFACE_MODULE_DIR', str(ROOT / 'app')))
from _interface_core import SysStrings, encode_dat


class DatPortableTests(unittest.TestCase):
    def test_all_headers_and_footer_variants(self):
        source = SysStrings(); source.load(str(ROOT / 'tests/fixtures/sysstring/fileedit.dat'))
        self.assertEqual(source.lookup(6000), 'Test Button')
        for version in (0, 111, 120, 121, 211, 212, 411, 412, 413, 414):
            for footer in (False, True):
                with self.subTest(version=version, footer=footer):
                    raw = encode_dat(source.payload(), 'sysstring-e.dat', version, 'l2encdec' if version >= 411 else 'standard', footer)
                    table = SysStrings(); table.load_bytes(raw, 'sysstring-e.dat', profile='plain' if version == 0 else 'auto')
                    self.assertEqual(table.payload(), source.payload())
                    self.assertEqual(table.summary()['footer_crc'], footer and version != 0)

    def test_unicode_save_and_existing_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / '\u0421\u0442\u0440\u043e\u043a\u0438'; folder.mkdir()
            file = folder / 'sysstring-e.dat'
            table = SysStrings(); table.load(str(ROOT / 'tests/fixtures/sysstring/fileedit.dat'))
            identifier = table.next_id()
            table.add(identifier, '\u0422\u0435\u0441\u0442 Windows')
            table.save(str(file))
            old = file.read_bytes()
            table.set(identifier, '\u65e5\u672c\u8a9e')
            table.save(str(file))
            self.assertEqual(file.with_suffix('.dat.bak').read_bytes(), old)
            check = SysStrings(); check.load(str(file))
            self.assertEqual(check.lookup(identifier), '\u65e5\u672c\u8a9e')
            self.assertEqual(check.lookup(6000), 'Test Button')
            self.assertEqual(check.summary()['table_tail_hex'], '0c536166655061636b61676500')


if __name__ == '__main__': unittest.main(verbosity=2)
