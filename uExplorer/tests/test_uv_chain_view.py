import copy
from pathlib import Path
import sys
import struct
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_chain import chain_matrix,oscillator_rotation_chain,panner_scaler_chain
from material_uv import timed_uv
from material_math import shared_grid


class UVChain(unittest.TestCase):
    def test_panner_scaler_order_and_original_size_offsets(self):
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        pan=dict(path='Pan',**{'class':'TexPanner'},tags=[dict(name='PanRate',bits=bits(.5))])
        scale=dict(path='Scale',**{'class':'TexScaler'},tags=[
            dict(name='UScale',bits=bits(.5)),dict(name='UOffset',bits=bits(64.))])
        for docs,expected in (((pan,scale),.75),((scale,pan),.5)):
            outer,inner=copy.deepcopy(docs)
            outer['strings']=[dict(name='Fixture.Texture',values=['Fixture.'+d['path'] for d in docs])]
            inner['strings']=[dict(name='Fixture.Texture',values=['Fixture.'+inner['path']])]
            inner['tags'].append(dict(name='Material',value=dict(id=3,path='Texture',**{'class':'Texture'})))
            steps=panner_scaler_chain(outer,inner,dict(uv0_exact=True,native_size=(256,128)))
            self.assertEqual(chain_matrix(steps,.5)[2],(expected,0.,1.))
            geometry=dict(uv_base=[[(.125,.25)]],uv=[[(99.,99.)]],face_materials=[0],
                          textures={0:dict(uv_chain=steps)})
            self.assertEqual(timed_uv(geometry,.5),[[(.25+expected,.25)]])
            geometry['uv']=timed_uv(geometry,.5)
            self.assertEqual(timed_uv(geometry,0),[[(.5,.25)]])
            bad=copy.deepcopy(outer);bad['strings'][0]['values'].reverse()
            with self.assertRaisesRegex(ValueError,'order'):
                panner_scaler_chain(bad,inner,dict(uv0_exact=True,native_size=(256,128)))
            bad=copy.deepcopy(inner);bad['strings'][0]['name']='Different.Texture'
            with self.assertRaisesRegex(ValueError,'sampler'):
                panner_scaler_chain(outer,bad,dict(uv0_exact=True,native_size=(256,128)))
            bad=copy.deepcopy(inner);bad['tags'][-1]['value']['path']='Other'
            with self.assertRaisesRegex(ValueError,'Texture leaf'):
                panner_scaler_chain(outer,bad,dict(uv0_exact=True,native_size=(256,128)))

    def test_panner_chain_rejects_invalid_time_and_deeper_leaf(self):
        steps=(('panner',(.5,(1.,0.))),('fixed',((2.,0.,0.,1.),(0.,0.))))
        for time in (-1,3601,float('nan')):
            with self.assertRaises(ValueError):chain_matrix(steps,time)
        with self.assertRaisesRegex(ValueError,'Texture leaf'):
            panner_scaler_chain(dict(**{'class':'TexScaler'}),
                dict(**{'class':'TexPanner'},tags=[
                    dict(name='Material',value=dict(id=3,**{'class':'TexRotator'}))]),{})

    def test_noncommuting_modifier_order_and_rewind(self):
        steps=(('oscillator',((0,1.,0.,.5),(0,1.,0.,0.))),
               ('fixed',((0.,1.,-1.,0.),(0.,0.))))
        matrix=chain_matrix(steps,.25)
        self.assertEqual(matrix,((0.,1.,0.),(-1.,0.,0.),(0.,.5,1.)))
        self.assertEqual(chain_matrix(tuple(reversed(steps)),.25)[2],(.5,0.,1.))
        geometry=dict(uv_base=[[(.25,.5)]],uv=[[(99.,99.)]],face_materials=[0],
                      textures={0:dict(uv_chain=steps)})
        self.assertEqual(timed_uv(geometry,.25),[[(-.5,.75)]])
        geometry['uv']=timed_uv(geometry,.25)
        self.assertEqual(timed_uv(geometry,0),[[(-.5,.25)]])

    def test_saved_order_gate_and_grid_compatibility(self):
        doc=dict(path='Group.Osc',strings=[dict(values=['Test.Group.Osc','Test.Group.Rot'])])
        ref=dict(path='Group.Rot')
        surface=dict(uv_rotation=(0.,1.,-1.,0.),uv_offset=(0.,0.))
        axes=((0,1.,0.,.5),(0,1.,0.,0.))
        steps=oscillator_rotation_chain(doc,ref,axes,surface)
        broken=copy.deepcopy(doc);broken['strings'][0]['values'].reverse()
        with self.assertRaisesRegex(ValueError,'order'):
            oscillator_rotation_chain(broken,ref,axes,surface)
        grid=dict(width=2,height=2,uv_chain=steps)
        self.assertEqual(shared_grid([grid,grid])['uv_chain'],steps)
        with self.assertRaisesRegex(ValueError,'chains'):
            shared_grid([grid,dict(width=2,height=2)])
