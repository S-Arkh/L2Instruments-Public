"""Ordered masked-add evidence and selection of existing shared mip levels."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_shader import direct_masked_add
from material_math import combine
from material_surface import diffuse


def document():
    return dict(tags=[dict(name='CombineOperation',value=6),dict(name='AlphaOperation',value=2),
        dict(name='Material1',value=dict(id=1,path='First',**{'class':'Texture'})),
        dict(name='Material2',value=dict(id=2,path='Second',**{'class':'Texture'}))],
        strings=[dict(name='Fixture.First',values=[]),dict(name='Fixture.Second',values=[])],
        shader='float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
        'result.xyz=c1.xyz;result.w=a1.w;float4 texcolor1=tex2D(s[1],tex0);'
        'c1=texcolor1;c2=result;a1=texcolor1;a2=result;'
        'result.xyz=c1.xyz+c1.w*c2.xyz;result.w=a1.w+a2.w;')


class MaskedAdd(unittest.TestCase):
    def test_first_input_alpha_with_implicit_and_explicit_mask(self):
        d=document();d['tags'][1]['value']=0
        d['shader']=d['shader'].replace('a1=texcolor1;a2=result;','a1=result;').replace('a1.w+a2.w','a1.w')
        a=dict(width=1,height=1,pixels=bytes([100,200,250,37]))
        b=dict(width=1,height=1,pixels=bytes([20,100,200,128]))
        self.assertTrue(direct_masked_add(d))
        self.assertEqual(combine(d,dict(Material1=a,Material2=b))['pixels'],bytes([70,200,255,37]))
        d['tags'].append(dict(name='Mask',value=copy.deepcopy(d['tags'][2]['value'])))
        self.assertTrue(direct_masked_add(d))
        self.assertEqual(combine(d,dict(Material1=a,Material2=b,Mask=a))['pixels'],bytes([70,200,255,37]))
        d['tags'][-1]['value']=copy.deepcopy(d['tags'][3]['value'])
        self.assertFalse(direct_masked_add(d))

    def test_order_alpha_extremes_rounding_and_saturation(self):
        a=dict(width=4,height=1,pixels=bytes([100,200,250,100])*4)
        b=dict(width=4,height=1,pixels=b''.join(bytes([20,100,200,alpha]) for alpha in (0,128,255,1)))
        result=combine(document(),dict(Material1=a,Material2=b))
        self.assertEqual(result['pixels'],bytes([
            20,100,200,100,70,200,255,228,120,255,255,255,20,101,201,101]))

    def test_unproved_routes_flags_and_shader_are_rejected(self):
        self.assertTrue(direct_masked_add(document()))
        for name in ('InvertMask','Modulate2X','Modulate4X','UseDiffuseAlpha','Mask'):
            d=document();d['tags'].append(dict(name=name,value=dict(id=3) if name=='Mask' else True))
            self.assertFalse(direct_masked_add(d))
        for old,new in [('c1.w*c2.xyz','c2.w*c2.xyz'),('tex0','mul(m0,tex0)'),
                        ('a1.w+a2.w','a1.w*a2.w')]:
            d=document();d['shader']=d['shader'].replace(old,new)
            self.assertFalse(direct_masked_add(d))
        d=document();d['strings'].reverse()
        self.assertFalse(direct_masked_add(d))
        d=document();d['tags'][2]['value']['path']='Group.Second'
        d['strings'][0]['name']='Fixture.Group.Second'
        self.assertFalse(direct_masked_add(d))

    def test_common_mip_uses_stored_pixels_not_resampling(self):
        d=document()
        def texture(levels):
            return dict(tags=[dict(name='Format',value=5)],mips=[
                dict(width=w,height=1,data_hex=pixel*w) for w,pixel in levels])
        docs={1:texture([(2,'000064ff')]),
              2:texture([(4,'00000000'),(2,'00640080')])}
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                return (dict(path=str(identifier),**{'class':'Combiner' if identifier==3 else 'Texture'}),
                        d if identifier==3 else docs[identifier])
        original=copy.deepcopy(docs)
        result=diffuse(None,Resolver(),'fixture',dict(id=3))
        self.assertEqual(result['pixels'],bytes([50,100,0,255])*2)
        self.assertEqual(result['width'],2)
        self.assertTrue(any('сохранённый mip' in note for note in result['notes']))
        self.assertEqual(docs,original)
        docs[2]['mips'].pop()
        fragment=diffuse(None,Resolver(),'fixture',dict(id=3))
        self.assertEqual([(s['width'],s['height']) for s in fragment['fragment_layers']],[(2,1),(4,1),(2,1)])
        self.assertFalse(fragment['uv0_exact'])
        self.assertTrue(any('Qt raster' in note for note in fragment['notes']))

    def test_common_mip_does_not_bypass_wrap_validation(self):
        d=document()
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                if identifier==3:return dict(path='Combined',**{'class':'Combiner'}),d
                widths=[2] if identifier==1 else [4,2]
                return dict(path=str(identifier),**{'class':'Texture'}),dict(
                    tags=[dict(name='Format',value=5),dict(name='UClampMode',value=identifier-1)],
                    mips=[dict(width=w,height=1,data_hex='ffffffff'*w) for w in widths])
        with self.assertRaisesRegex(ValueError,'addressing'):
            diffuse(None,Resolver(),'fixture',dict(id=3))


if __name__=='__main__':unittest.main()
