"""Stateful UV snapshots must never masquerade as runtime playback."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_math import shared_grid
from material_snapshot import cached_uv_snapshot
from material_surface import diffuse
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh,shader


def matrix_tag(rows):
    return dict(name='M',members=[
        dict(name=plane,members=[dict(name=field,bits=bits(value)[0])
                                 for field,value in zip(('X','Y','Z','W'),row)])
        for plane,row in zip(('XPlane','YPlane','ZPlane','WPlane'),rows)])


def fixture(kind):
    ref=dict(id=2,path='Group.Image',**{'class':'Texture'})
    tags=[dict(name='Material',value=ref),
          matrix_tag(((2.,3.,0.,0.),(4.,5.,0.,0.),(.25,.5,1.,0.),(0.,0.,0.,1.)))]
    if kind=='TexOscillator':
        tags.append(dict(name='UOscillationType',value=3))
        tags.append(dict(name='CurrentUJitter',bits=bits(.125)[0]))
    doc=dict(tags=tags,strings=[dict(name='Pack.Group.Image',values=['Pack.Group.Osc'])],
             shader=shader(0))
    return ref,doc


class Resolver:
    dependencies=[]
    def __init__(self,kind,doc):self.kind=kind;self.doc=doc
    def resolve(self,path,ref):return path,ref['id']
    def read(self,path,identifier,budget=None):
        if identifier==1:return dict(path='Group.Osc',**{'class':self.kind}),self.doc
        return dict(path='Group.Image',**{'class':'Texture'}),dict(
            tags=[dict(name='Format',value=5)],
            mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])


class Snapshot(unittest.TestCase):
    def test_direct_stateful_surfaces_use_saved_matrix_but_never_compose(self):
        for kind in ('TexOscillator','TexOscillatorTriggered','TexPannerTriggered'):
            ref,doc=fixture(kind)
            surface=diffuse(None,Resolver(kind,doc),'fixture',dict(id=1))
            self.assertEqual(surface['uv_rotation'],(2.,3.,4.,5.))
            self.assertEqual(surface['uv_offset'],(.25,.5))
            self.assertTrue(surface['uv_snapshot'])
            self.assertFalse(surface['uv_coordinate_exact'])
            self.assertFalse(surface['uv0_exact'])
            self.assertTrue(any('только сохранённая UV-матрица' in x for x in surface['notes']))
            self.assertNotIn('uv_oscillation',surface)
            self.assertNotIn('uv_pan_rate',surface)
            with self.assertRaisesRegex(ValueError,'supported matching UV'):
                shared_grid([surface])
            with patch('textured_mesh.ResourceResolver',return_value=Resolver(kind,doc)):
                geometry=prepare_textured(None,'fixture',mesh(),'static_mesh',
                                          overrides={0:('fixture',1),1:('fixture',1)})
            self.assertNotIn('error',geometry)
            self.assertEqual(geometry['uv'][0],[(2.75,3.75)]*3)
            self.assertNotIn('uv_base',geometry)

    def test_invalid_bindings_or_matrices_never_become_snapshots(self):
        ref,original=fixture('TexOscillatorTriggered')
        for change in ('shader','sampler','modifier','source','projected','no_matrix',
                       'duplicate_matrix','duplicate_plane','duplicate_member','nan','perspective','z'):
            doc=copy.deepcopy(original)
            if change=='shader':doc['shader']=shader(1)
            elif change=='sampler':doc['strings'][0]['name']='Pack.Wrong.Image'
            elif change=='modifier':doc['strings'][0]['values']=['Pack.Other']
            elif change=='source':doc['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='projected':doc['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='no_matrix':doc['tags'].pop(1)
            elif change=='duplicate_matrix':doc['tags'].append(copy.deepcopy(doc['tags'][1]))
            elif change=='duplicate_plane':doc['tags'][1]['members'][1]['name']='XPlane'
            elif change=='duplicate_member':doc['tags'][1]['members'][0]['members'][1]['name']='X'
            elif change=='nan':doc['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            elif change=='perspective':doc['tags'][1]['members'][0]['members'][3]['bits']=bits(.1)[0]
            else:doc['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            with self.subTest(change=change),self.assertRaises(ValueError):
                cached_uv_snapshot(doc,'Group.Osc',ref)
            surface=diffuse(None,Resolver('TexOscillatorTriggered',doc),'fixture',dict(id=1))
            self.assertNotIn('uv_snapshot',surface)
            self.assertFalse(surface['uv_coordinate_exact'])
            self.assertTrue(any('без эффектов' in note for note in surface['notes']))

    def test_short_sampler_requires_proven_unique_leaf(self):
        ref,doc=fixture('TexOscillator')
        doc['strings'][0]['name']='Image'
        with self.assertRaisesRegex(ValueError,'sampler'):
            cached_uv_snapshot(doc,'Group.Osc',ref)
        self.assertEqual(cached_uv_snapshot(doc,'Group.Osc',ref,unique_leaf=True)[1],(.25,.5))
        ref=dict(ref,path='Image')
        with self.assertRaisesRegex(ValueError,'sampler'):
            cached_uv_snapshot(doc,'Group.Osc',ref)
        self.assertEqual(cached_uv_snapshot(doc,'Group.Osc',ref,unique_leaf=True)[1],(.25,.5))


if __name__=='__main__':unittest.main()
