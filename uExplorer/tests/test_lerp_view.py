"""Masked blend register provenance and integer mip-grid oracle."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_lerp import direct_lerp
from material_math import combine


def fixture(inverted=False):
    return dict(tags=[dict(name='CombineOperation',value=5),
        dict(name='InvertMask',value=inverted),
        *[dict(name=k,value=dict(id=i,path=n,**{'class':'Texture'}))
          for i,(k,n) in enumerate((('Material1','A'),('Material2','B'),('Mask','M')),1)]],
        strings=[dict(name='Test.'+n,values=[]) for n in ('A','M','B')],
        shader=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
                'result.xyz=c1.xyz;result.w=a1.w;'
                'float4 texcolor1=tex2D(s[1],tex0);c2=result;a1=texcolor1;'
                +('a1=1.f-a1;' if inverted else '')
                +'result.xyz=c2.xyz;result.w=a1.w;'
                'float4 texcolor2=tex2D(s[2],tex0);c1=texcolor2;c2=result;a1=result;'
                'result.xyz=c1.xyz*result.w+c2.xyz*(1.f-result.w);result.w=a1.w;'))


class Lerp(unittest.TestCase):
    def test_implicit_first_alpha_requires_exact_shader(self):
        from portable_smoke import masked_add_alpha_fixture
        doc=masked_add_alpha_fixture()
        doc['tags'][0]['value']=5
        doc['shader']=doc['shader'].replace('c1.xyz+c1.w*c2.xyz',
            'c1.xyz*result.w+c2.xyz*(1.f-result.w)')
        inputs=dict(Material1=dict(width=1,height=1,pixels=bytes([255,0,30,128])),
                    Material2=dict(width=1,height=1,pixels=bytes([0,255,230,17])))
        self.assertTrue(direct_lerp(doc))
        self.assertEqual(combine(doc,inputs)['pixels'],bytes([127,128,130,128]))
        doc['shader']=doc['shader'].replace('a1=result;','a1=texcolor1;')
        self.assertFalse(direct_lerp(doc))

    def test_separate_mask_add_preserves_mask_alpha(self):
        from material_lerp import direct_masked_add_mask
        doc=fixture();doc['tags'][0]['value']=6
        doc['shader']=doc['shader'].replace('c1.xyz*result.w+c2.xyz*(1.f-result.w)',
                                           'c1.xyz+c1.w*c2.xyz')
        inputs=dict(Material1=dict(width=1,height=1,pixels=bytes([100,200,250,37])),
                    Material2=dict(width=1,height=1,pixels=bytes([20,100,200,128])),
                    Mask=dict(width=1,height=1,pixels=bytes([0,0,0,91])))
        self.assertTrue(direct_masked_add_mask(doc))
        self.assertEqual(combine(doc,inputs)['pixels'],bytes([70,200,255,91]))
        doc['strings'][1],doc['strings'][2]=doc['strings'][2],doc['strings'][1]
        self.assertFalse(direct_masked_add_mask(doc))

    def test_mask_endpoints_rounding_and_inversion(self):
        def surface(values):return dict(width=3,height=1,pixels=bytes(values))
        inputs=dict(Material1=surface([255,0,30,17]*3),Material2=surface([0,255,230,219]*3),
                    Mask=surface([99,77,55,0,99,77,55,128,99,77,55,255]))
        self.assertEqual(combine(fixture(),inputs)['pixels'],
                         bytes([255,0,30,0,127,128,130,128,0,255,230,255]))
        self.assertEqual(combine(fixture(True),inputs)['pixels'],
                         bytes([0,255,230,255,128,127,130,127,255,0,30,0]))

    def test_unrecognized_or_misbound_shader_is_rejected(self):
        original=fixture();self.assertTrue(direct_lerp(original))
        for replacement in ('c2.xyz*result.w+c1.xyz*(1.f-result.w)','c1.xyz+c2.xyz'):
            doc=copy.deepcopy(original)
            doc['shader']=doc['shader'].replace('c1.xyz*result.w+c2.xyz*(1.f-result.w)',replacement)
            self.assertFalse(direct_lerp(doc))
        doc=copy.deepcopy(original);doc['strings'][0],doc['strings'][2]=doc['strings'][2],doc['strings'][0]
        self.assertFalse(direct_lerp(doc))
        doc=copy.deepcopy(original);doc['tags'].append(dict(name='UseDiffuseAlpha',value=True))
        self.assertFalse(direct_lerp(doc))
        doc=copy.deepcopy(original);doc['strings'][0]['values']=['UnknownModifier']
        self.assertFalse(direct_lerp(doc))
