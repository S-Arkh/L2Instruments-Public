import sys
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package, Reader
from extract_sources import extract, script_text
from compare_interface import canonical
from package_client import wrap
from local_paths import PACKAGES


@unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1', 'Set L2_INTEGRATION=1 and external input paths')
class SourceTests(unittest.TestCase):
    def test_original_source_contains_lost_casts(self):
        package = Package(PACKAGES / 'interface.u')
        _, entry = package.find('CalculatorWnd.ScriptText')
        raw, text, _ = script_text(package, entry)
        self.assertIn('INT64', text.upper())
        self.assertNotIn('UnknownFunction', text)
        self.assertIn('getsystemmessage(3093)', text.casefold())
        self.assertIn('string(a_Number)', text)
        with tempfile.TemporaryDirectory() as directory:
            result = extract(package.path, Path(directory))
            self.assertEqual(len(result['extracted']), 253)
            self.assertEqual(result['rejected'], {})
            self.assertEqual(result['missing'], [])
            self.assertEqual((Path(directory) / 'CalculatorWnd.uc').read_bytes(), raw)

    def test_envelopes_round_trip(self):
        original = Package(PACKAGES / 'interface.u')
        with tempfile.TemporaryDirectory() as directory:
            for envelope in ('Lineage2Ver111', 'GamekitData111', 'plain'):
                path = Path(directory) / (envelope + '.u')
                path.write_bytes(wrap(original.data, envelope))
                reread = Package(path)
                self.assertEqual(reread.data, original.data)
                self.assertEqual(reread.envelope, envelope)


class ComparisonTests(unittest.TestCase):
    def test_safe_constant_cast_folding(self):
        for cast, opcode, value in [('3d', '2c', 255), ('43', '1e', 255.0)]:
            old = dict(memory_size=4, instructions=[
                dict(pc=0, depth=0, opcode='39', kind='cast', cast=cast, value='cast_' + cast),
                dict(pc=2, depth=1, opcode=opcode, kind='constant', value=value)])
            new = dict(memory_size=2, instructions=[dict(pc=0, depth=0, opcode='24', kind='constant', value=255)])
            self.assertEqual(canonical(old, True), canonical(new, True))

    def test_nonintegral_and_overflow_are_not_folded(self):
        for value in (255.5, -1.0, 256.0):
            function = dict(memory_size=7, instructions=[
                dict(pc=0, depth=0, opcode='39', kind='cast', cast='43', value='cast_43'),
                dict(pc=2, depth=1, opcode='1e', kind='constant', value=value)])
            self.assertEqual(len(canonical(function, True)), 2)

    def test_branch_into_operand_is_not_folded(self):
        function = dict(memory_size=7, instructions=[
            dict(pc=0, depth=0, opcode='06', kind='jump', target=5),
            dict(pc=3, depth=0, opcode='39', kind='cast', cast='3d', value='cast_3d'),
            dict(pc=5, depth=1, opcode='2c', kind='constant', value=255)])
        self.assertEqual(len(canonical(function, True)), 3)


if __name__ == '__main__':
    unittest.main()
