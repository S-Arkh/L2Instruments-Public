"""Missing masks use a proved stored alpha route, never a universal default."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_shader import implicit_alpha_source
from material_math import combine
from material_surface import diffuse


def document(constant=False):
    refs=[dict(id=1,path='First',**{'class':'Texture'}),
          dict(id=2,path='Second',**{'class':'ConstantColor' if constant else 'Texture'})]
    d=dict(tags=[dict(name='CombineOperation',value=2),
                 dict(name='Material1',value=refs[0]),dict(name='Material2',value=refs[1])])
    if constant:
        d['strings']=[dict(name='Fixture.First',values=[])]
        d['shader']=('c1=tFactor;a1=tFactor;result.xyz=c1.xyz;result.w=a1.w;'
            'float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;c2=result;a1=result;'
            'result.xyz=c1.xyz*c2.xyz;result.w=a1.w;')
    else:
        d['strings']=[dict(name='Fixture.First',values=[]),dict(name='Fixture.Second',values=[])]
        d['shader']=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
            'result.xyz=c1.xyz;result.w=a1.w;float4 texcolor1=tex2D(s[1],tex0);'
            'c1=texcolor1;c2=result;a1=result;result.xyz=c1.xyz*c2.xyz;result.w=a1.w;')
    return d


class ImplicitAlpha(unittest.TestCase):
    def test_compiler_order_can_change_the_implicit_source(self):
        surfaces={name:dict(width=1,height=1,pixels=bytes([255,255,255,alpha]))
                  for name,alpha in [('Material1',20),('Material2',200)]}
        for constant,source,alpha in [(False,'Material1',20),(True,'Material2',200)]:
            d=document(constant);original=copy.deepcopy(d)
            self.assertEqual(implicit_alpha_source(d),source)
            self.assertEqual(combine(d,surfaces)['pixels'][3],alpha)
            self.assertEqual(d,original)

    def test_unsupported_code_and_unknown_mapping_are_not_guessed(self):
        for suffix in ('result.w=a1.w*a2.w;','texcolor0.w=0.f;',
                       'result.xyz=unknown();','a1=unknown;'):
            d=document();d['shader']+=suffix
            self.assertIsNone(implicit_alpha_source(d))
        d=document();d['shader']=d['shader'].replace(',tex0)',',mul(m0,tex0))')
        self.assertIsNone(implicit_alpha_source(d))
        d=document();d['strings'][0]['name']='Other.Unknown'
        self.assertIsNone(implicit_alpha_source(d))
        d=document();d['strings'][0]['values']=['UnsupportedModifier']
        self.assertIsNone(implicit_alpha_source(d))
        d=document();d['shader']=''
        self.assertIsNone(implicit_alpha_source(d))
        d=document();d['tags'].append(dict(name='InvertMask',value=True))
        self.assertIsNone(implicit_alpha_source(d))

    def test_explicit_mask_and_ambiguous_suffix(self):
        d=document();d['tags'].append(dict(name='Mask',value=dict(id=3)))
        self.assertIsNone(implicit_alpha_source(d))
        d=document()
        d['tags'][1]['value']['path']='Group.Image';d['tags'][2]['value']['path']='Image'
        d['strings'][0]['name']='Fixture.Group.Image'
        self.assertIsNone(implicit_alpha_source(d))
        d=document()
        d['tags'][2]['value']=copy.deepcopy(d['tags'][1]['value'])
        d['strings'][1]['name']='Fixture.First'
        self.assertEqual(implicit_alpha_source(d),'Material1')

    def test_unused_animated_input_is_not_evaluated(self):
        d=dict(tags=[dict(name='Material1',value=dict(id=1,path='Color',**{'class':'ConstantColor'})),
                     dict(name='Material2',value=dict(id=2,path='Animated',**{'class':'TexOscillatorTriggered'}))],
               strings=[],shader='c1=tFactor;a1=tFactor;result.xyz=c1.xyz;result.w=a1.w;'
                                  'c2=result;a1=result;result.xyz=c2.xyz;result.w=a1.w;')
        visited=[]
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                visited.append(identifier)
                if identifier==3:return {'class':'Combiner','path':'Combined'},d
                if identifier==1:return {'class':'ConstantColor','path':'Color'},dict(tags=[dict(name='Color',bytes=[1,2,3,77])])
                raise AssertionError('Unused animated input must not be evaluated')
        result=diffuse(None,Resolver(),'fixture',dict(id=3))
        self.assertEqual(visited,[3,1])
        self.assertEqual(result['pixels'],bytes([1,2,3,77]))
        self.assertTrue(any('Material1' in note for note in result['notes']))


if __name__=='__main__':unittest.main()
