"""Different mip grids stay separate; raster fallback is explicitly inexact."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_fragment import fragment_surface
from material_math import shared_grid
from portable_smoke import masked_add_alpha_fixture


class Fragment(unittest.TestCase):
    def test_storage_and_composition_gate(self):
        a=dict(width=2,height=1,pixels=bytes([10,20,30,40])*2,wrap=(1,0))
        b=dict(width=1,height=4,pixels=bytes([50,60,70,80])*4,wrap=(0,1))
        original=copy.deepcopy((a,b))
        result=fragment_surface(masked_add_alpha_fixture(),dict(Material1=a,Material2=b))
        self.assertEqual([(s['width'],s['height'],s['wrap']) for s in result['fragment_layers']],
                         [(2,1,(1,0)),(1,4,(0,1)),(2,1,(1,0))])
        self.assertEqual(result['pixels'],a['pixels'])
        self.assertFalse(result['uv0_exact'])
        with self.assertRaises(ValueError):shared_grid([result,a])
        self.assertEqual((a,b),original)

    def test_modified_uv_and_truncated_pixels_rejected(self):
        a=dict(width=2,height=1,pixels=bytes([10,20,30,40])*2)
        for changed in (dict(a,uv_scale=(2.,1.)),dict(a,pixels=b'\0'),
                        dict(a,uv_chain=(('unknown',None),))):
            with self.assertRaises(ValueError):
                fragment_surface(masked_add_alpha_fixture(),dict(Material1=changed,Material2=a))
