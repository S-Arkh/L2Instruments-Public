"""VertexColor preview shows saved UE2 FColor words, not runtime lighting."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_graph import ResourceResolver
from material_math import shared_grid
from material_surface import diffuse
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh


class FixtureCore:
    def request(self,**fields):
        if fields['operation']=='resource_inventory':
            return dict(result=dict(candidates=[
                dict(id=1,path='Color',**{'class':'VertexColor'}),
                dict(id=2,path='Image',**{'class':'Texture'})]))
        if fields['object_id']==1:
            return dict(result=dict(tags=[],strings=[],shader=''))
        return dict(result=dict(tags=[dict(name='Format',value=5)],
                                mips=[dict(width=1,height=1,data_hex='ffffffff')]))


def colored_mesh():
    document=mesh()
    # UE2 serializes FColor as RGBA bytes; words are little-endian.
    document['colors']=[0x44332211,0x88776655,0xccbbaa99]
    return document


class VertexColor(unittest.TestCase):
    def test_saved_rgba_words_do_not_require_uv_streams(self):
        document=colored_mesh();document['uv_streams']=[]
        original=copy.deepcopy(document);core=FixtureCore()
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',document,'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['vertex_colors'][0],
                         [(0x11,0x22,0x33,0x44),(0x55,0x66,0x77,0x88),(0x99,0xaa,0xbb,0xcc)])
        self.assertEqual(geometry['uv'][0],[(0.,0.)]*3)
        self.assertTrue(any('игровое освещение' in note for note in geometry['warnings']))
        self.assertTrue(any('alpha-поток не применяется' in note for note in geometry['warnings']))
        self.assertEqual(document,original)
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([geometry['textures'][0]])

    def test_missing_or_malformed_colors_disable_only_the_affected_material(self):
        for change in ('missing','short','negative','oversize','bool','not_list'):
            document=colored_mesh()
            if change=='missing':document.pop('colors')
            elif change=='short':document['colors'].pop()
            elif change=='negative':document['colors'][0]=-1
            elif change=='oversize':document['colors'][0]=0x100000000
            elif change=='bool':document['colors'][0]=True
            else:document['colors']='invalid'
            core=FixtureCore()
            with self.subTest(change=change),patch('textured_mesh.ResourceResolver',
                                                    return_value=ResourceResolver(core)):
                geometry=prepare_textured(core,'Fixture.utx',document,'static_mesh',
                                          overrides={0:('Fixture.utx',1),1:('Fixture.utx',2)})
            self.assertNotIn('error',geometry)
            self.assertEqual(set(geometry['textures']),{1})
            self.assertTrue(any('Материал 0:' in note and 'цвет' in note
                                for note in geometry['warnings']))
            self.assertNotIn('vertex_colors',geometry)

    def test_skeletal_mesh_does_not_invent_saved_vertex_colors(self):
        document=dict(points_bits=[bits(0,0,0),bits(1,0,0),bits(0,1,0)],
                      mesh_wedges=[dict(vertex=i,uv_bits=bits(.25,.5)) for i in range(3)],
                      triangles=[dict(wedges=[0,1,2],material=0)],
                      textures=[],materials=[[0,0]])
        core=FixtureCore()
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',document,'skeletal_mesh',
                                      overrides={0:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertFalse(geometry['textures'])
        self.assertTrue(any('только для StaticMesh' in note for note in geometry['warnings']))


if __name__=='__main__':unittest.main()
