"""Render-state boundaries, wrapper precedence and pass ordering."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_state import state_for,render_order
from textured_mesh import diffuse


def doc(**values):
    return dict(tags=[dict(name=k,value=v) for k,v in values.items()])


class States(unittest.TestCase):
    def test_final_blend_rejects_unconfirmed_modes_and_alpha(self):
        self.assertEqual(state_for('FinalBlend',doc(FrameBufferBlending=2))['blend'],'alpha')
        self.assertTrue(state_for('FinalBlend',doc())['z_write'])
        for value in (3,8,9,10,11,12,255):
            with self.assertRaises(ValueError):state_for('FinalBlend',doc(FrameBufferBlending=value))
        for value in (-1,256):
            with self.assertRaises(ValueError):state_for('FinalBlend',doc(AlphaRef=value))
        state=state_for('FinalBlend',doc(ZWrite=False,ZTest=False,AlphaTest=True,AlphaRef=128))
        self.assertFalse(state['z_write']);self.assertFalse(state['z_test'])
        self.assertTrue(state['alpha_test']);self.assertEqual(state['alpha_ref'],128)

    def test_shader_masked_opacity_and_texture_flags(self):
        self.assertTrue(state_for('Shader',doc(OutputBlending=1))['alpha_test'])
        self.assertEqual(state_for('Shader',doc(Opacity=dict(id=-1)))['blend'],'alpha')
        self.assertEqual(state_for('Texture',doc())['blend'],'overwrite')
        self.assertEqual(state_for('Texture',doc(bMasked=True))['alpha_ref'],204)
        self.assertEqual(state_for('Texture',doc(bAlphaTexture=True,Format=3))['alpha_ref'],204)

    def test_outer_final_blend_overrides_inner_shader(self):
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                kind,document={
                    1:('FinalBlend',doc(Material=dict(id=2),FrameBufferBlending=4,ZWrite=False)),
                    2:('Shader',doc(Diffuse=dict(id=3),OutputBlending=2)),
                    3:('Texture',dict(doc(Format=5,UClampMode=1),
                                      mips=[dict(width=1,height=1,data_hex='001020ff')]))
                }[identifier]
                return {'class':kind,'path':kind},document
        result=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertEqual(result['render_state']['blend'],'translucent')
        self.assertFalse(result['render_state']['z_write'])
        self.assertEqual(result['wrap'],[1,0])

    def test_opaque_first_then_blended_far_to_near(self):
        geometry=dict(polygons=[[0],[1],[2]],face_materials=[0,1,2])
        states={0:dict(blend='alpha'),1:dict(blend='overwrite'),2:dict(blend='alpha')}
        order=render_order(geometry,[(0,0,-1),(0,0,0),(0,0,1)],states)
        self.assertEqual([i for i,_ in order],[1,0,2])

    def test_opacity_reads_alpha_not_rgb_and_rejects_cycles(self):
        documents={
            1:('Shader',doc(Diffuse=dict(id=2),Opacity=dict(id=3))),
            2:('Texture',dict(doc(Format=5),mips=[dict(width=2,height=1,data_hex='102030ff405060ff')])),
            3:('Texture',dict(doc(Format=5),mips=[dict(width=2,height=1,data_hex='ffffff20000000c0')]))}
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                kind,document=documents[identifier]
                return {'class':kind,'path':kind},document
        result=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertEqual(result['pixels'],bytes.fromhex('30201020605040c0'))
        documents[1]=('Shader',doc(Diffuse=dict(id=2),Opacity=dict(id=1)))
        with self.assertRaisesRegex(ValueError,'cycle'):diffuse(None,Resolver(),'fixture',dict(id=1))
        # Shared diffuse/opacity leaves are legitimate, not graph cycles.
        documents[1]=('Shader',doc(Diffuse=dict(id=2),Opacity=dict(id=2)))
        self.assertEqual(diffuse(None,Resolver(),'fixture',dict(id=1))['pixels'][3::4],b'\xff\xff')
        documents[1]=('Shader',doc(Diffuse=dict(id=2),Opacity=dict(id=3)))
        documents[3]=('Texture',dict(doc(Format=5,UClampMode=1),
                                    mips=[dict(width=2,height=1,data_hex='0000004000000040')]))
        with self.assertRaisesRegex(ValueError,'addressing'):diffuse(None,Resolver(),'fixture',dict(id=1))
        documents[3]=('Texture',dict(doc(Format=5),
                                    mips=[dict(width=3,height=1,data_hex='00000040'*3)]))
        with self.assertRaisesRegex(ValueError,'dimensions'):diffuse(None,Resolver(),'fixture',dict(id=1))
        documents[3]=('ConstantColor',dict(tags=[dict(name='Color',bytes=[1,2,3,64])]))
        self.assertEqual(diffuse(None,Resolver(),'fixture',dict(id=1))['pixels'][3::4],b'\x40\x40')


if __name__=='__main__':unittest.main()
