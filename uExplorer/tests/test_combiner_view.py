"""Combiner mip arithmetic, bounded graphs and static UV scale integration."""
import copy
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_math import combine,scaler,shared_grid
from material_surface import diffuse
from textured_mesh import prepare_textured


def bits(*values):return list(struct.unpack('<'+'I'*len(values),struct.pack('<'+'f'*len(values),*values)))
def doc(**values):return dict(tags=[dict(name=k,value=v) for k,v in values.items()])
def color(*rgba):return dict(width=1,height=1,pixels=bytes(rgba),uv0_exact=True)
def scale(u,v,**values):
    d=doc(**values)
    d['tags']+= [dict(name='UScale',bits=bits(u)[0]),dict(name='VScale',bits=bits(v)[0])]
    return d


class Resolver:
    dependencies=[]
    def __init__(self,documents):self.documents=documents
    def resolve(self,path,reference):return path,reference['id']
    def read(self,path,identifier,budget=None):
        kind,document=self.documents[identifier]
        return {'class':kind,'path':str(identifier)},document


class Combiner(unittest.TestCase):
    def setUp(self):
        self.inputs={'Material1':color(64,128,255,64),'Material2':color(128,64,128,128),
                     'Mask':color(5,6,7,32)}

    def test_select_multiply_add_and_modulation_precedence(self):
        for operation,expected in [(0,[64,128,255,32]),(1,[128,64,128,32]),
                                   (2,[32,32,128,32]),(3,[192,192,255,32])]:
            self.assertEqual(combine(doc(CombineOperation=operation),self.inputs)['pixels'],bytes(expected))
        result=combine(doc(CombineOperation=2,AlphaOperation=1,Modulate2X=True,Modulate4X=True),self.inputs)
        self.assertEqual(result['pixels'],bytes([129,129,255,32]))
        # RGB modulation flags do not change addition or alpha.
        result=combine(doc(CombineOperation=3,AlphaOperation=2,Modulate4X=True),self.inputs)
        self.assertEqual(result['pixels'],bytes([192,192,255,192]))

    def test_alpha_channels_and_inverted_mask(self):
        for operation,expected in enumerate((32,32,192,64,128)):
            result=combine(doc(AlphaOperation=operation),self.inputs)
            self.assertEqual(result['pixels'][3],expected)
        result=combine(doc(InvertMask=True),self.inputs)
        self.assertEqual(result['pixels'],bytes([64,128,255,223]))
        for operation in (4,5,6,7,255):
            with self.assertRaisesRegex(ValueError,'color operation'):
                combine(doc(CombineOperation=operation),self.inputs)
        with self.assertRaisesRegex(ValueError,'UseDiffuseAlpha'):
            combine(doc(UseDiffuseAlpha=True),self.inputs)

    def test_matching_grids_scales_and_constant_expansion(self):
        texture=dict(width=2,height=1,pixels=bytes([1,2,3,4,5,6,7,8]),
                     uv_scale=(2.,4.),wrap=(1,0),uv0_exact=True)
        values={'Material1':texture,'Material2':color(1,1,1,128)}
        result=combine(doc(CombineOperation=3,AlphaOperation=4),values)
        self.assertEqual(result['pixels'],bytes([2,3,4,128,6,7,8,128]))
        self.assertEqual(result['uv_scale'],(2.,4.))
        for altered,error in [(dict(texture,uv_scale=(1.,1.)),'UV scales'),
                              (dict(texture,wrap=(0,0)),'addressing'),
                              (dict(texture,width=3),'dimensions'),
                              (dict(texture,uv0_exact=False),'UV coordinates')]:
            with self.assertRaisesRegex(ValueError,error):shared_grid([texture,altered])

    def test_missing_inputs_cycles_and_exponential_graph_budget(self):
        leaf=('ConstantColor',dict(tags=[dict(name='Color',bytes=[64,128,255,128])]))
        documents={1:('Combiner',doc(CombineOperation=2,AlphaOperation=1,Material1=dict(id=2),Material2=dict(id=2))),2:leaf}
        self.assertEqual(diffuse(None,Resolver(documents),'fixture',dict(id=1))['pixels'],bytes([16,64,255,64]))
        documents[1]=('Combiner',doc(AlphaOperation=3,Material1=dict(id=1)))
        with self.assertRaisesRegex(ValueError,'cycle'):diffuse(None,Resolver(documents),'fixture',dict(id=1))
        documents[1]=('Combiner',doc(Material1=dict(id=2)))
        with self.assertRaisesRegex(ValueError,'Mask'):diffuse(None,Resolver(documents),'fixture',dict(id=1))
        documents={i:('Combiner',doc(CombineOperation=2,AlphaOperation=1,
                     Material1=dict(id=i+1),Material2=dict(id=i+1))) for i in range(1,8)}
        documents[8]=leaf
        with self.assertRaisesRegex(ValueError,'64 nodes'):diffuse(None,Resolver(documents),'fixture',dict(id=1))

    def test_scaler_validation_and_per_corner_mesh_uv(self):
        self.assertEqual(scaler(scale(.5,.25)),(2.,4.))
        self.assertEqual(scaler(scale(2,1.5)),(.5,struct.unpack('<f',struct.pack('<f',2/3))[0]))
        for u in (0,1e-8,float('inf')):
            with self.assertRaises(ValueError):scaler(scale(u,1))
        d=scale(1,1);d['tags'].append(dict(name='UOffset',bits=bits(1)[0]))
        with self.assertRaisesRegex(ValueError,'offset'):scaler(d)
        with self.assertRaisesRegex(ValueError,'UV0'):scaler(scale(1,1,TexCoordSource=8))
        mesh=dict(vertices=[dict(position_bits=bits(*p)) for p in [(0,0,0),(1,0,0),(0,1,0)]],
                  indices=[0,1,2],sections=[dict(first_index=0,face_count=1)],
                  uv_streams=[dict(coordinate_bits=[bits(0,0),bits(.5,0),bits(0,.25)])])
        original=copy.deepcopy(mesh)
        docs={1:('TexScaler',scale(.5,.25,Material=dict(id=2))),
              2:('Texture',dict(doc(Format=5),mips=[dict(width=1,height=1,data_hex='ffffffff')]))}
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(docs)):
            prepared=prepare_textured(None,'fixture',mesh,'static_mesh',overrides={0:('fixture',1)})
        self.assertNotIn('error',prepared)
        self.assertEqual(prepared['uv'],[[(0.,0.),(1.,0.),(0.,1.)]])
        self.assertEqual(mesh,original)
        mesh['uv_streams'][0]['coordinate_bits'][0]=bits(1e6,0)
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(docs)):
            prepared=prepare_textured(None,'fixture',mesh,'static_mesh',overrides={0:('fixture',1)})
        self.assertIn('UV coordinates',prepared['error'])


if __name__=='__main__':unittest.main()
