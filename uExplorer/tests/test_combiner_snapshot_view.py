"""A Rotator over a mip-grid Combiner can show only its stored UV matrix."""
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
from test_implicit_mask_view import document as combiner_document
from test_material_snapshot_view import matrix_tag


def fixture():
    combiner=combiner_document(True)
    combiner['tags'][1]['value']['id']=3
    combiner['tags'][2]['value']['id']=4
    combiner['tags'].append(dict(name='Modulate2X',value=True))
    combiner['shader']=combiner['shader'].replace('c1.xyz*c2.xyz;','c1.xyz*c2.xyz*2.f;')
    outer=dict(path='Rot',tags=[
        dict(name='Material',value=dict(id=2,path='Combined',**{'class':'Combiner'})),
        matrix_tag(((0.,1.,0.,0.),(-1.,0.,0.,0.),(.25,.5,1.,0.),(0.,0.,0.,1.)))],
        strings=[dict(name='Fixture.First',values=['Fixture.Rot'])],
        shader=combiner['shader'].replace('tex2D(s[0],tex0)',
                                           'tex2D(s[0],mul(m0,float3(tex0.xy,1.f)))'))
    texture=dict(tags=[dict(name='Format',value=5)],
                 mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    constant=dict(tags=[dict(name='Color',bytes=[255,255,255,255])])
    return {1:('TexRotator','Rot',outer),2:('Combiner','Combined',combiner),
            3:('Texture','First',texture),4:('ConstantColor','Second',constant)}


class FixtureCore:
    def __init__(self,documents=None):self.documents=documents or fixture()
    def request(self,**fields):
        if fields['operation']=='resource_inventory':
            return dict(result=dict(candidates=[
                dict(id=i,path=path,serial_bytes=0,**{'class':kind})
                for i,(kind,path,_) in self.documents.items()]))
        return dict(result=self.documents[fields['object_id']][2])


class CombinerSnapshot(unittest.TestCase):
    def surface(self,documents=None):
        core=FixtureCore(documents)
        return diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=1))

    def test_stored_matrix_is_static_and_never_composable(self):
        documents=fixture();original=copy.deepcopy(documents)
        surface=self.surface(documents)
        self.assertEqual(surface['uv_rotation'],(0.,1.,-1.,0.))
        self.assertEqual(surface['uv_offset'],(.25,.5))
        self.assertTrue(surface['uv_snapshot'])
        self.assertFalse(surface['uv0_exact'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertTrue(any('время и игровые размеры не подтверждены' in note
                            for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['uv'][0],[(-.25,.75)]*3)
        self.assertNotIn('uv_base',geometry)
        self.assertEqual(documents,original)

    def test_rejects_bad_shader_bindings_and_matrix(self):
        changes=('outer_shader','child_shader','outer_sampler','child_sampler','modifier',
                 'child_path','texture_identity','constant_identity','operation','alpha','mask',
                 'source','projected','missing_matrix','duplicate_matrix','nonplanar','nan')
        for change in changes:
            documents=fixture();outer=documents[1][2];child=documents[2][2]
            if change=='outer_shader':outer['shader']+='unknown;'
            elif change=='child_shader':child['shader']=child['shader'].replace('*2.f','')
            elif change=='outer_sampler':outer['strings'][0]['name']='Fixture.Wrong'
            elif change=='child_sampler':child['strings'][0]['values']=['Fixture.Wrong']
            elif change=='modifier':outer['strings'][0]['values']=['Fixture.Wrong']
            elif change=='child_path':outer['tags'][0]['value']['path']='Wrong'
            elif change=='texture_identity':documents[3]=('Texture','Other',documents[3][2])
            elif change=='constant_identity':documents[4]=('ConstantColor','Other',documents[4][2])
            elif change=='operation':child['tags'][0]['value']=3
            elif change=='alpha':child['tags'].append(dict(name='AlphaOperation',value=1))
            elif change=='mask':child['tags'].append(dict(name='Mask',value=dict(id=3,path='First',**{'class':'Texture'})))
            elif change=='source':outer['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='projected':outer['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='missing_matrix':outer['tags'].pop(1)
            elif change=='duplicate_matrix':outer['tags'].append(copy.deepcopy(outer['tags'][1]))
            elif change=='nonplanar':outer['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            else:outer['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)


if __name__=='__main__':unittest.main()
