import sys
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from verify_profile import verify


@unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1', 'Set L2_INTEGRATION=1 and external input paths')
class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = verify()

    def test_cast_registrations(self):
        names = ['ByteToINT64', 'IntToINT64', 'BoolToINT64', 'FloatToINT64', 'StringToINT64',
                 'INT64ToByte', 'INT64ToInt', 'INT64ToBool', 'INT64ToFloat', 'INT64ToString']
        for index, name in enumerate(names, 0x5a):
            item = self.profile['client_registrations']['exec' + name]
            self.assertEqual(item['index'], index)
            self.assertEqual(item['table'], 0x150ec2d8)

    def test_arithmetic_registrations(self):
        names = ['Subtract_PreINT64', 'Multiply_INT64INT64', 'Multiply_INT64Float',
                 'Divide_INT64INT64', 'Add_INT64INT64', 'Subtract_INT64INT64',
                 'AddEqual_INT64INT64', 'SubtractEqual_INT64INT64', 'Less_INT64INT64',
                 'Greater_INT64INT64', 'LessEqual_INT64INT64', 'GreaterEqual_INT64INT64',
                 'EqualEqual_INT64INT64', 'NotEqual_INT64INT64']
        for index, name in enumerate(names, 400):
            item = self.profile['client_registrations']['exec' + name]
            self.assertEqual(item['index'], index)
            self.assertEqual(item['table'], 0x150ec6d8)

    def test_constant_registration(self):
        self.assertEqual(self.profile['client_registrations']['execINT64Const']['index'], 0x46)

    def test_primary_call(self):
        self.assertEqual(self.profile['primary_get_token_return_rva'], '0x784d3')


if __name__ == '__main__':
    unittest.main()
