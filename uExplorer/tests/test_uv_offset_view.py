"""Offsets are in original texture pixels, independent of the displayed mip."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_math import scaler_offset,shared_grid
from material_surface import diffuse
from textured_mesh import prepare_textured


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def offsets(u,v):
    return dict(tags=[dict(name='UOffset',bits=bits(u)),dict(name='VOffset',bits=bits(v))])


class Offsets(unittest.TestCase):
    def test_native_resolution_and_negative_offsets(self):
        self.assertEqual(scaler_offset(offsets(256,-64),(1024,256)),(.25,-.25))
        self.assertEqual(scaler_offset(offsets(-1000,-1000),(256,256)),(-3.90625,-3.90625))
        for size in (None,(0,256),(256,),(256,999999)):
            with self.assertRaises(ValueError):scaler_offset(offsets(1,0),size)
        for value in (float('nan'),float('inf'),1e30):
            with self.assertRaises(ValueError):scaler_offset(offsets(value,0),(256,256))
        self.assertEqual(scaler_offset(offsets(0,0)),(0.,0.))

    def test_shared_grids_require_equal_offsets_except_constants(self):
        texture=dict(width=2,height=1,pixels=b'\xff'*8,uv_offset=(.25,0))
        self.assertEqual(shared_grid([texture,dict(width=1,height=1,pixels=b'\xff'*4)])['uv_offset'],(.25,0))
        with self.assertRaisesRegex(ValueError,'UV offsets'):
            shared_grid([texture,dict(texture,uv_offset=(0,0))])

    def test_mip_selection_keeps_original_dimensions_and_mesh_offsets(self):
        d=offsets(256,0);d['tags'].append(dict(name='Material',value=dict(id=2,**{'class':'Texture'})))
        documents={
            1:('TexScaler',d),
            2:('Texture',dict(tags=[dict(name='Format',value=5)],
                mips=[dict(width=1024,height=1,data_hex='0000ffff'*1024),
                      dict(width=2,height=1,data_hex='0000ffff00ff00ff')])),
            3:('TexScaler',dict(tags=[dict(name='UScale',bits=bits(.5)),
                                     dict(name='Material',value=dict(id=1,**{'class':'TexScaler'}))]))}
        class Resolver:
            dependencies=[]
            def resolve(self,path,reference):return path,reference['id']
            def read(self,path,identifier,budget=None):
                kind,document=documents[identifier]
                return {'class':kind,'path':str(identifier)},document
        surface=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertEqual(surface['width'],2)
        self.assertEqual(surface['native_size'],(1024,1))
        self.assertEqual(surface['uv_offset'],(.25,0))
        with self.assertRaisesRegex(ValueError,'saved sampler'):
            diffuse(None,Resolver(),'fixture',dict(id=3))
        mesh=dict(vertices=[dict(position_bits=[bits(v) for v in p]) for p in [(0,0,0),(1,0,0),(0,1,0)]],
                  indices=[0,1,2],sections=[dict(first_index=0,face_count=1)],
                  uv_streams=[dict(coordinate_bits=[[bits(0),bits(0)]]*3)])
        with patch('textured_mesh.ResourceResolver',return_value=Resolver()):
            result=prepare_textured(None,'fixture',mesh,'static_mesh',overrides={0:('fixture',1)})
        self.assertNotIn('error',result)
        self.assertEqual(result['uv'],[[(.25,0.)]*3])


if __name__=='__main__':unittest.main()
