"""Nested stateful UV previews use saved matrices, not invented event playback."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_math import shared_grid
from material_snapshot import cached_uv_chain
from material_surface import diffuse
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh,shader
from test_material_snapshot_view import matrix_tag


def fixture(outer='TexOscillatorTriggered',inner='TexRotator'):
    first=matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),
                      (.25,.5,1.,0.),(0.,0.,0.,1.)))
    second=matrix_tag(((0.,1.,0.,0.),(-1.,0.,0.,0.),
                       (0.,0.,1.,0.),(0.,0.,0.,1.)))
    a=dict(path='Group.First',tags=[
        dict(name='Material',value=dict(id=2,path='Group.Second',**{'class':inner})),first],
        strings=[dict(name='Pack.Group.Image',values=['Pack.Group.First','Pack.Group.Second'])],
        shader=shader(0))
    b=dict(path='Group.Second',tags=[
        dict(name='Material',value=dict(id=3,path='Group.Image',**{'class':'Texture'})),second],
        strings=[dict(name='Pack.Group.Image',values=['Pack.Group.Second'])],
        shader=shader(0))
    if outer=='TexOscillator':
        a['tags'].append(dict(name='UOscillationType',value=3))
    image=dict(path='Group.Image',tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    return {1:(outer,a),2:(inner,b),3:('Texture',image)}


class Resolver:
    dependencies=[]
    def __init__(self,documents):self.documents=documents
    def resolve(self,path,reference):return path,reference['id']
    def read(self,path,identifier,budget=None):
        kind,document=self.documents[identifier]
        return dict(path=document['path'],**{'class':kind}),document


def chain(documents):
    return [dict(doc,**{'class':kind}) for kind,doc in
            (documents[1],documents[2])]


class SnapshotChain(unittest.TestCase):
    def test_saved_order_and_static_geometry(self):
        for outer,inner in (('TexOscillatorTriggered','TexRotator'),
                            ('TexPannerTriggered','TexRotator'),
                            ('TexOscillator','TexRotator'),
                            ('TexRotator','TexOscillatorTriggered')):
            documents=fixture(outer,inner)
            original=copy.deepcopy(documents)
            with self.subTest(outer=outer,inner=inner):
                surface=diffuse(None,Resolver(documents),'fixture',dict(id=1))
                self.assertEqual(surface['uv_rotation'],(0.,1.,-1.,0.))
                self.assertEqual(surface['uv_offset'],(-.5,.25))
                self.assertTrue(surface['uv_snapshot'])
                self.assertFalse(surface['uv0_exact'])
                self.assertFalse(surface['uv_coordinate_exact'])
                self.assertNotIn('uv_chain',surface)
                self.assertNotIn('uv_oscillation',surface)
                self.assertTrue(any('одновременное состояние' in note for note in surface['notes']))
                with self.assertRaisesRegex(ValueError,'supported matching UV'):
                    shared_grid([surface])
                with patch('textured_mesh.ResourceResolver',return_value=Resolver(documents)):
                    geometry=prepare_textured(None,'fixture',mesh(),'static_mesh',
                                              overrides={0:('fixture',1),1:('fixture',1)})
                self.assertNotIn('error',geometry)
                self.assertEqual(geometry['uv'],[[(-1.,.5)]*3]*2)
                self.assertNotIn('uv_base',geometry)
                self.assertTrue(any('только статический снимок' in note
                                    for note in geometry['warnings']))
                self.assertEqual(documents,original)

    def test_unverified_bindings_matrices_or_coordinates_do_not_form_a_snapshot(self):
        surface=dict(uv0_exact=True,stored_mip_sizes=[(2,1)],name='Group.Image')
        changes=('shader','source','projected','dimension','sampler','suffix','order',
                 'child_path','leaf_path','leaf_class','missing_matrix','duplicate_matrix',
                 'duplicate_plane','duplicate_member','nan','perspective','nonplanar',
                 'large_product','unsupported','not_stateful')
        for change in changes:
            documents=fixture()
            a=documents[1][1];b=documents[2][1]
            if change=='shader':b['shader']=shader(1)
            elif change=='source':b['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='projected':a['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='dimension':a['tags'].append(dict(name='TexCoordCount',value=1))
            elif change=='sampler':b['strings'][0]['name']='Pack.Wrong.Image'
            elif change=='suffix':b['strings'][0]['values']=[]
            elif change=='order':a['strings'][0]['values'].reverse()
            elif change=='child_path':a['tags'][0]['value']['path']='Group.Wrong'
            elif change=='leaf_path':b['tags'][0]['value']['path']='Group.Wrong'
            elif change=='leaf_class':b['tags'][0]['value']['class']='Shader'
            elif change=='missing_matrix':b['tags'].pop(1)
            elif change=='duplicate_matrix':a['tags'].append(copy.deepcopy(a['tags'][1]))
            elif change=='duplicate_plane':a['tags'][1]['members'][1]['name']='XPlane'
            elif change=='duplicate_member':a['tags'][1]['members'][0]['members'][1]['name']='X'
            elif change=='nan':a['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            elif change=='perspective':a['tags'][1]['members'][0]['members'][3]['bits']=bits(.1)[0]
            elif change=='nonplanar':a['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            elif change=='large_product':
                for doc in (a,b):
                    doc['tags'][1]['members'][0]['members'][0]['bits']=bits(1e6)[0]
            elif change=='unsupported':documents[2]=('TexEnvMap',b)
            else:documents[1]=('TexRotator',a)
            with self.subTest(change=change),self.assertRaises(ValueError):
                cached_uv_chain(chain(documents),surface)

    def test_invalid_nested_snapshot_keeps_marked_triggered_fallback(self):
        documents=fixture()
        # This invalidates the outer snapshot but leaves the direct child usable.
        documents[1][1]['shader']=shader(1)
        # A directly rendered TexRotator must also be a verifiable fixed rotation.
        # Use a different child that needs no rotation calibration.
        documents[2]=('TexScaler',documents[2][1])
        documents[1][1]['tags'][0]['value']['class']='TexScaler'
        surface=diffuse(None,Resolver(documents),'fixture',dict(id=1))
        self.assertNotIn('uv_snapshot',surface)
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertTrue(any('сохранённая UV-цепочка недоступна' in note
                            for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])

    def test_requires_exact_leaf_and_enforces_chain_limit(self):
        documents=fixture()
        for surface in (dict(uv0_exact=False,stored_mip_sizes=[(2,1)]),
                        dict(uv0_exact=True),
                        dict(uv0_exact=True,fragment_layers=[{}],stored_mip_sizes=[(2,1)])):
            with self.subTest(surface=surface),self.assertRaises(ValueError):
                cached_uv_chain(chain(documents),surface)
        with self.assertRaisesRegex(ValueError,'2..32'):
            cached_uv_chain(chain(documents)[:1],dict(uv0_exact=True,stored_mip_sizes=[(2,1)]))

    def test_resolved_texture_must_match_saved_reference(self):
        documents=fixture()
        for name in ('Group.Wrong','Other.Group.Image','Image',''):
            surface=dict(uv0_exact=True,stored_mip_sizes=[(2,1)],name=name)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'resolved Texture'):
                cached_uv_chain(chain(documents),surface)
        documents[2][1]['tags'][0]['value']['path']='Pack.Group.Image'
        surface=dict(uv0_exact=True,stored_mip_sizes=[(2,1)],name='Group.Image')
        self.assertEqual(cached_uv_chain(chain(documents),surface,'Pack')[1],(-.5,.25))
        with self.assertRaisesRegex(ValueError,'resolved Texture'):
            cached_uv_chain(chain(documents),surface,'WrongPack')
        documents=fixture()
        documents[3][1]['path']='Group.Wrong'
        with self.assertRaises(ValueError):
            diffuse(None,Resolver(documents),'fixture',dict(id=1))


if __name__=='__main__':unittest.main()
