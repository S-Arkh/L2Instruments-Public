"""Saved sampler suffixes, noncommuting UV order, and traversal limits."""
import copy
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_chain import chain_matrix
from material_surface import diffuse
from material_uv import timed_uv
from material_math import shared_grid
from material_rotation import direction,rotation_matrix
from test_rotation_view import fixture as rotation_fixture


def fixture(kinds=('TexPanner','TexScaler','TexPanner')):
    def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
    count=len(kinds);docs={}
    for index,kind in enumerate(kinds,1):
        next_kind=kinds[index] if index<count else 'Texture'
        name=f'M{index}'
        docs[index]=dict(path=name,**{'class':kind},tags=[
            dict(name='Material',value=dict(id=index+1,path=f'M{index+1}',**{'class':next_kind})),
            dict(name='PanRate',bits=bits(.25 if index==1 else .5))] if kind=='TexPanner' else [
            dict(name='Material',value=dict(id=index+1,path=f'M{index+1}',**{'class':next_kind})),
            dict(name='UScale',bits=bits(.5))],
            strings=[dict(name=f'Fixture.M{count+1}',values=[f'Fixture.M{i}' for i in range(index,count+1)])])
    docs[count+1]=dict(path=f'M{count+1}',**{'class':'Texture'},
        tags=[dict(name='Format',value=5)],mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    return docs


class Resolver:
    dependencies=[]
    def __init__(self,docs):self.docs=docs
    def resolve(self,path,ref):return path,ref['id']
    def read(self,path,identifier,budget=None):
        doc=self.docs[identifier]
        return dict(path=doc['path'],**{'class':doc['class']}),doc


class ExtendedUV(unittest.TestCase):
    def test_three_stage_order_and_absolute_time(self):
        docs=fixture();original=copy.deepcopy(docs)
        result=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertEqual(result['uv_scale'],(1.,1.))
        self.assertNotIn('uv_pan_rate',result)
        self.assertEqual(chain_matrix(result['uv_chain'],2),((2.,0.,0.),(0.,1.,0.),(2.,0.,1.)))
        geometry=dict(uv_base=[[(.25,.5)]],uv=[[(99.,99.)]],face_materials=[0],textures={0:result})
        geometry['uv']=timed_uv(geometry,2)
        self.assertEqual(geometry['uv'],[[(2.5,.5)]])
        self.assertEqual(timed_uv(geometry,0),[[(.5,.5)]])
        self.assertEqual(docs,original)

    def test_four_stages_and_suffix_binding_rejections(self):
        docs=fixture(('TexPanner','TexPanner','TexScaler','TexPanner'))
        result=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertEqual(chain_matrix(result['uv_chain'],2)[2],(4.,0.,1.))
        for change in ('order','sampler','leaf'):
            broken=copy.deepcopy(docs)
            if change=='order':broken[2]['strings'][0]['values'].reverse()
            elif change=='sampler':broken[3]['strings'][0]['name']='Fixture.Other'
            else:broken[4]['tags'][0]['value']['path']='Other'
            with self.assertRaisesRegex(ValueError,'sampler|order'):
                diffuse(None,Resolver(broken),'fixture',dict(id=1))

    def test_zero_repeat_verified_and_nonzero_preview_in_chain(self):
        docs=fixture(('TexOscillator','TexPanner'))
        zero=struct.unpack('<I',struct.pack('<f',0.))[0]
        docs[1]['tags'] += [dict(name='UOscillationType',value=2),
                            dict(name='UOscillationAmplitude',bits=zero)]
        result=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertEqual(result['uv_chain'][0][1][0][0],2)
        self.assertEqual(chain_matrix(result['uv_chain'],1)[2][0],.5)
        docs[1]['tags'][-1]['bits']=struct.unpack('<I',struct.pack('<f',.125))[0]
        result=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertEqual(result['uv_chain'][0][0],'oscillator_preview')
        self.assertTrue(result['uv_preview_approximate'])
        self.assertFalse(result['uv_coordinate_exact'])
        self.assertTrue(any('приблизительная' in note for note in result['notes']))
        self.assertNotEqual(chain_matrix(result['uv_chain'],.5),
                            chain_matrix(result['uv_chain'],0))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([result])

    def test_noninvariant_roll_marks_whole_chain_as_approximate(self):
        docs=fixture(('TexPanner','TexScaler'))
        docs[1]['tags'].append(dict(name='PanDirection',words=[10000,5000,32768]))
        surface=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertEqual(surface['uv_chain'][0][0],'panner_preview')
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertTrue(any('TexPanner Roll: приблизительная' in note for note in surface['notes']))
        self.assertNotEqual(chain_matrix(surface['uv_chain'],1),chain_matrix(surface['uv_chain'],0))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])

    def test_noninvariant_rotation_marks_whole_chain_as_approximate(self):
        docs=fixture(('TexPanner','TexRotator'))
        rotation=rotation_fixture(True)
        rotation['tags'][1]['bits']=struct.unpack('<I',struct.pack('<f',0.))[0]
        rows=rotation_matrix(*direction(53000,'double'),(0.,0.))
        for plane,row in zip(rotation['tags'][2]['members'],rows):
            for member,value in zip(plane['members'],row):
                member['bits']=struct.unpack('<I',struct.pack('<f',value))[0]
        rotation['tags'] += [dict(name='TexRotationType',value=1),
                             dict(name='Material',value=dict(id=3,path='M3',**{'class':'Texture'}))]
        rotation.update(path='M2',strings=[dict(name='Fixture.M3',values=['Fixture.M2'])])
        rotation['class']='TexRotator'
        docs[2]=rotation
        surface=diffuse(None,Resolver(docs),'fixture',dict(id=1))
        self.assertTrue(surface['uv_chain'][1][1]['preview_approximate'])
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertTrue(any('TexRotator: приблизительная' in note for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])

    def test_cycles_depth_and_unsupported_leaf(self):
        docs=fixture();docs[3]['tags'][0]['value']=dict(id=1,path='M1',**{'class':'TexPanner'})
        with self.assertRaisesRegex(ValueError,'cycle'):
            diffuse(None,Resolver(docs),'fixture',dict(id=1))
        with self.assertRaisesRegex(ValueError,'32 nodes'):
            diffuse(None,Resolver(fixture(('TexPanner',)*33)),'fixture',dict(id=1))
        docs=fixture();docs[3]['tags'][0]['value']['class']='Shader'
        with self.assertRaisesRegex(ValueError,'direct Texture'):
            diffuse(None,Resolver(docs),'fixture',dict(id=1))
