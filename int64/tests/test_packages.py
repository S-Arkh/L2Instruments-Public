import struct
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package, Reader, FormatError

from local_paths import PACKAGES as CLIENT, SYSTEM


class ReaderTests(unittest.TestCase):
    def test_compact_indices(self):
        for raw, value in [('00', 0), ('3f', 63), ('4001', 64), ('81', -1),
                           ('c001', -64), ('7fffffff0f', 2147483647),
                           ('c080808010', -2147483648)]:
            with self.subTest(raw=raw):
                self.assertEqual(Reader(bytes.fromhex(raw)).index(), value)

    def test_rejects_bad_indices(self):
        for raw in ('40', '7fffffffff', '4080808010'):
            with self.subTest(raw=raw), self.assertRaises(FormatError):
                Reader(bytes.fromhex(raw)).index()

    def test_strings_and_bounds(self):
        self.assertEqual(Reader(b'\x03hi\0').string(), 'hi')
        self.assertEqual(Reader(b'\x83h\0i\0\0\0').string(), 'hi')
        with self.assertRaises(FormatError):
            Reader(b'\x03hi!').string()
        with self.assertRaises(FormatError):
            Reader(b'').take(1)


@unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1', 'Set L2_INTEGRATION=1 and external input paths')
class ClientPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = CLIENT / 'Core.u'
        cls.core = Package(core if core.exists() else CLIENT.parent / 'Core.u')
        cls.interface = Package(CLIENT / 'interface.u')

    def test_original_fingerprints(self):
        self.assertIn(self.core.sha256, {
            '8e4261e732958fe0b7b0faa20228d284f7bd535428f02b13eea5df964d1111fc',
            '16cfcc56cc5114da9dd5116482b2896ab9c2daf03f9bd1380c61a1f84930443e',
        })
        self.assertEqual(self.interface.sha256, 'f127c431da3c2c20d299397d21ecf437ec273adfd12633e8ef3bbf22725630c9')

    def test_representation(self):
        for p, name, cls in [(self.core, 'Object.INT64', 'Core.Struct'),
                             (self.core, 'Object.INT64.Left', 'Core.IntProperty'),
                             (self.core, 'Object.INT64.Right', 'Core.IntProperty'),
                             (self.interface, 'CalculatorWnd.m_Operand1', 'Core.StructProperty')]:
            with self.subTest(name=name):
                _, e = p.find(name)
                self.assertEqual(p.ref(e.cls), cls)
        _, e = self.interface.find('CalculatorWnd.m_Operand1')
        r = Reader(self.interface.data[e.offset:e.offset + e.size])
        self.assertEqual(self.interface.name(r.index()), 'None')
        r.index()  # super field
        r.index()  # next field
        self.assertEqual(r.unpack('<i'), 1)  # array dimension
        r.take(4)  # property flags
        r.index()  # category
        self.assertEqual(self.interface.ref(r.index()), 'Core.Object.INT64')
        self.assertEqual(r.pos, e.size)

    def test_get_operand(self):
        f = self.interface.function('CalculatorWnd.GetOperand')
        self.assertEqual(f['memory_size'], 42)
        rows = f['instructions']
        self.assertEqual([(r['pc'], r['cast']) for r in rows if r['kind'] == 'cast'],
                         [(26, '5e'), (37, '5b')])
        self.assertEqual([r['index'] for r in rows if r['kind'] == 'native'], [151, 125])
        self.assertEqual([r['target'] for r in rows if 'target' in r], [36, 40])

    def test_set_numeric(self):
        f = self.interface.function('CalculatorWnd.SetNumeric')
        self.assertEqual(f['memory_size'], 122)
        rows = f['instructions']
        self.assertEqual([r['cast'] for r in rows if r['kind'] == 'cast'], ['63'])
        self.assertEqual([r['index'] for r in rows if r['kind'] == 'native'], [152, 125])
        self.assertIn('NWindow.UIScript.GetSystemMessage', [r.get('value') for r in rows])
        self.assertIn(3093, [r.get('value') for r in rows])

    def test_arithmetic(self):
        f = self.interface.function('CalculatorWnd.Calc')
        self.assertEqual(f['memory_size'], 169)
        rows = f['instructions']
        self.assertEqual([r['index'] for r in rows if r['kind'] == 'native'],
                         [404, 405, 401, 412, 403])
        self.assertEqual([r['cast'] for r in rows if r['kind'] == 'cast'], ['5b'] * 3)

    def test_branch_targets_are_instruction_boundaries(self):
        for name in ('GetOperand', 'SetNumeric', 'Calc'):
            f = self.interface.function('CalculatorWnd.' + name)
            boundaries = {r['pc'] for r in f['instructions'] if r['depth'] == 0}
            for r in f['instructions']:
                if 'target' in r and r['target'] != 65535:
                    self.assertIn(r['target'], boundaries)

    def test_bad_references_rejected(self):
        with self.assertRaises(FormatError):
            self.core.ref(len(self.core.exports) + 1)
        with self.assertRaises(FormatError):
            self.core.name(-1)

    def test_old_compiler_package_layout(self):
        old = Package(SYSTEM / 'Core.u')
        self.assertEqual((old.version, old.licensee), (126, 0))
        function = old.function('Object.RandRange')
        self.assertEqual(function['memory_size'], 26)
        self.assertEqual([r['index'] for r in function['instructions'] if r['kind'] == 'native'],
                         [174, 171, 175, 195])


if __name__ == '__main__':
    unittest.main()
