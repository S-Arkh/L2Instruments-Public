"""Two independently timed UV samplers are bounded by saved shader provenance."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_graph import ResourceResolver
from material_math import shared_grid
from material_multisample import MULTIPLY_SHADER,TERMINAL
from material_surface import diffuse
from material_uv import has_timed_uv,timed_fragment_uv,timed_uv
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,direct_shader,mesh,shader


def fixture():
    def ref(identifier,path,kind):
        return dict(id=identifier,path=path,**{'class':kind})
    names=('Fixture.PanA','Fixture.PanB')
    samplers=[dict(name='Fixture.White',values=[names[0]]),
              dict(name='Fixture.Color',values=[names[1]])]
    combined=dict(path='Blend',tags=[
        dict(name='CombineOperation',value=2),
        dict(name='Material1',value=ref(2,'PanA','TexPanner')),
        dict(name='Material2',value=ref(3,'PanB','TexPanner'))],
        strings=copy.deepcopy(samplers),shader=MULTIPLY_SHADER+TERMINAL)
    first=dict(path='PanA',tags=[
        dict(name='PanRate',bits=bits(0.)[0]),
        dict(name='Material',value=ref(4,'White','Texture'))],
        strings=[copy.deepcopy(samplers[0])],shader=shader(0))
    second=dict(path='PanB',tags=[
        dict(name='PanRate',bits=bits(.5)[0]),
        dict(name='Material',value=ref(5,'Color','Texture'))],
        strings=[copy.deepcopy(samplers[1])],shader=shader(0))
    white=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='ffffffffffffffff')])
    color=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    coord=dict(path='Coord',tags=[
        dict(name='SourceChannel',value=2),dict(name='TexCoordSource',value=2),
        dict(name='Material',value=ref(1,'Blend','Combiner'))],
        strings=copy.deepcopy(samplers),shader=MULTIPLY_SHADER+TERMINAL)
    return {1:('Combiner','Blend',combined),2:('TexPanner','PanA',first),
            3:('TexPanner','PanB',second),4:('Texture','White',white),
            5:('Texture','Color',color),6:('TexCoordSource','Coord',coord)}


def multiple_channels(channel=1,direct=False):
    documents=fixture();parent=documents[1][2]
    source=dict(path='CoordB',tags=[
        dict(name='SourceChannel',value=channel),dict(name='TexCoordSource',value=channel),
        dict(name='Material',value=dict(id=5 if direct else 3,path='Color' if direct else 'PanB',
                                        **{'class':'Texture' if direct else 'TexPanner'}))],
        strings=[dict(name='Fixture.Color',values=[] if direct else ['Fixture.PanB'])],
        shader=(direct_shader(channel) if direct else shader(channel)))
    documents[7]=('TexCoordSource','CoordB',source)
    parent['tags'][2]['value']=dict(id=7,path='CoordB',**{'class':'TexCoordSource'})
    parent['strings'][1]['values']=[] if direct else ['Fixture.PanB']
    expression=(f'tex{channel}' if direct else f'mul(m1,float3(tex{channel}.xy,1.f))')
    parent['shader']=parent['shader'].replace('mul(m1,float3(tex0.xy,1.f))',expression)
    return documents


class FixtureCore:
    def __init__(self,documents=None):self.documents=documents or fixture()
    def request(self,**fields):
        if fields['operation']=='resource_inventory':
            return dict(result=dict(candidates=[
                dict(id=i,path=path,serial_bytes=0,**{'class':kind})
                for i,(kind,path,_) in self.documents.items()]))
        return dict(result=self.documents[fields['object_id']][2])


class MultiSample(unittest.TestCase):
    def surface(self,documents=None,identifier=1):
        core=FixtureCore(documents)
        return diffuse(core,ResourceResolver(core),'fixture.utx',dict(id=identifier))

    def test_two_saved_sampler_chains_and_independent_time(self):
        documents=fixture();original=copy.deepcopy(documents)
        surface=self.surface(documents)
        self.assertTrue(surface['fragment_independent_uv'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertEqual(surface['fragment_operation'],2)
        self.assertEqual(len(surface['fragment_layers']),3)
        self.assertTrue(has_timed_uv(surface))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])
        core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('fixture.utx',1),1:('fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['uv_input'][0],[(.25,.5)]*3)
        self.assertEqual(geometry['fragment_uv'][0],([(.25,.5)]*3,)*3)
        one=timed_fragment_uv(geometry,1.)
        self.assertEqual(one[0],([(.25,.5)]*3,[(.75,.5)]*3,[(.25,.5)]*3))
        self.assertEqual(timed_uv(geometry,1.)[0],[(.25,.5)]*3)
        self.assertEqual(timed_fragment_uv(geometry,0.),geometry['fragment_uv'])
        self.assertEqual(documents,original)

    def test_conflicting_parent_is_labelled_not_proof_of_game_uv(self):
        surface=self.surface(identifier=6)
        self.assertTrue(surface['fragment_independent_uv'])
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertEqual(surface['uv_channel'],0)
        self.assertTrue(any('свойства выбирают UV2' in note and 'shader выбирает UV0' in note
                            for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])

    def test_unmodified_uv0_textures_keep_the_existing_mip_grid_route(self):
        documents=fixture();parent=documents[1][2]
        parent['tags'][1]['value']=dict(id=4,path='White',**{'class':'Texture'})
        parent['tags'][2]['value']=dict(id=5,path='Color',**{'class':'Texture'})
        for sampler in parent['strings']:sampler['values']=[]
        parent['shader']=(parent['shader']
                          .replace('mul(m0,float3(tex0.xy,1.f))','tex0')
                          .replace('mul(m1,float3(tex0.xy,1.f))','tex0'))
        surface=self.surface(documents)
        self.assertNotIn('fragment_layers',surface)
        self.assertTrue(surface['uv0_exact'])
        self.assertTrue(any('сетке mip' in note for note in surface['notes']))

    def test_independent_uv_channels_and_rewind(self):
        for channel,direct in ((channel,direct) for channel in range(1,8) for direct in (False,True)):
            documents=multiple_channels(channel,direct)
            geometry_source=mesh()
            while len(geometry_source['uv_streams'])<=channel:
                index=len(geometry_source['uv_streams'])
                geometry_source['uv_streams'].append(dict(coordinate_index=index,
                                                          coordinate_bits=[bits(.75,.5)]*3))
            core=FixtureCore(documents)
            with self.subTest(channel=channel,direct=direct):
                surface=self.surface(documents)
                self.assertEqual([layer.get('uv_channel',0) for layer in surface['fragment_layers']],
                                 [0,channel,0])
                with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
                    geometry=prepare_textured(core,'Fixture.utx',geometry_source,'static_mesh',
                                              overrides={0:('Fixture.utx',1),1:('Fixture.utx',2)})
                self.assertIn(0,geometry['textures'])
                self.assertEqual(geometry['fragment_uv'][0][0],[(.25,.5)]*3)
                self.assertEqual(geometry['fragment_uv'][0][1],[(.75,.5)]*3)
                at_one=timed_fragment_uv(geometry,1.)
                expected=.75 if direct else 1.25
                self.assertEqual(at_one[0][1],[(expected,.5)]*3)
                self.assertEqual(timed_fragment_uv(geometry,0.),geometry['fragment_uv'])

    def test_two_nonzero_streams_are_kept_distinct(self):
        documents=multiple_channels(7)
        parent=documents[1][2]
        source=dict(path='CoordA',tags=[
            dict(name='SourceChannel',value=2),dict(name='TexCoordSource',value=2),
            dict(name='Material',value=dict(id=2,path='PanA',**{'class':'TexPanner'}))],
            strings=[dict(name='Fixture.White',values=['Fixture.PanA'])],shader=shader(2))
        documents[8]=('TexCoordSource','CoordA',source)
        parent['tags'][1]['value']=dict(id=8,path='CoordA',**{'class':'TexCoordSource'})
        parent['shader']=parent['shader'].replace('mul(m0,float3(tex0.xy,1.f))',
                                                  'mul(m0,float3(tex2.xy,1.f))')
        geometry_source=mesh()
        while len(geometry_source['uv_streams'])<=7:
            index=len(geometry_source['uv_streams'])
            geometry_source['uv_streams'].append(dict(coordinate_index=index,
                coordinate_bits=[bits(.125 if index==2 else .875,.5)]*3))
        core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',geometry_source,'static_mesh',
                                      overrides={0:('Fixture.utx',1)})
        self.assertEqual(geometry['fragment_uv'][0][0],[(.125,.5)]*3)
        self.assertEqual(geometry['fragment_uv'][0][1],[(.875,.5)]*3)
        self.assertEqual(geometry['fragment_uv'][0][2],[(.125,.5)]*3)
        self.assertEqual(timed_fragment_uv(geometry,1.)[0][1],[(1.375,.5)]*3)

    def test_missing_or_damaged_second_stream_disables_only_its_slot(self):
        for change in ('missing','short','wrong_index','nan'):
            documents=multiple_channels()
            source=mesh()
            if change=='missing':source['uv_streams'].pop()
            elif change=='short':source['uv_streams'][1]['coordinate_bits'].pop()
            elif change=='wrong_index':source['uv_streams'][1]['coordinate_index']=0
            else:source['uv_streams'][1]['coordinate_bits'][0]=bits(float('nan'),.5)
            core=FixtureCore(documents)
            with self.subTest(change=change),patch('textured_mesh.ResourceResolver',
                                                    return_value=ResourceResolver(core)):
                geometry=prepare_textured(core,'Fixture.utx',source,'static_mesh',
                                          overrides={0:('Fixture.utx',1),1:('Fixture.utx',2)})
            self.assertNotIn('error',geometry)
            self.assertEqual(set(geometry['textures']),{1})
            self.assertTrue(any('Материал 0:' in warning and ('UV1' in warning or 'Non-finite' in warning)
                                for warning in geometry['warnings']))

    def test_skeletal_mesh_does_not_invent_a_second_stream(self):
        body=dict(points_bits=[bits(0,0,0),bits(1,0,0),bits(0,1,0)],
                  mesh_wedges=[dict(vertex=i,uv_bits=bits(.25,.5)) for i in range(3)],
                  triangles=[dict(wedges=[0,1,2],material=0)],
                  textures=[],materials=[[0,0]])
        core=FixtureCore(multiple_channels())
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',body,'skeletal_mesh',
                                      overrides={0:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertFalse(geometry['textures'])
        self.assertTrue(any('только UV0' in warning for warning in geometry['warnings']))

    def test_mixed_channel_metadata_must_match_each_branch(self):
        for change in ('parent','source','child_shader','source_shader','sampler','projected','wrapper'):
            documents=multiple_channels();parent=documents[1][2];source=documents[7][2]
            if change=='parent':parent['shader']=parent['shader'].replace('tex1.xy','tex2.xy')
            elif change=='source':source['tags'][0]['value']=source['tags'][1]['value']=2
            elif change=='child_shader':documents[3][2]['shader']=shader(1)
            elif change=='source_shader':source['shader']=shader(0)
            elif change=='sampler':source['strings'][0]['values']=['Fixture.Wrong']
            elif change=='projected':source['tags'].append(dict(name='TexCoordProjected',value=True))
            else:
                coord=documents[6][2]
                coord['shader']=parent['shader'];coord['strings']=copy.deepcopy(parent['strings'])
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents,6 if change=='wrapper' else 1)

    def test_rejects_unproven_shader_references_and_branches(self):
        changes=('shader','operation','alpha','mask','diffuse','sampler','sampler_order',
                 'branch_path','branch_shader','branch_suffix','branch_channel','branch_class',
                 'leaf_identity','cycle','truncated_texture')
        for change in changes:
            documents=fixture()
            parent=documents[1][2];a=documents[2][2];b=documents[3][2]
            if change=='shader':parent['shader']=parent['shader'].replace('c1.xyz*c2.xyz','c1.xyz+c2.xyz')
            elif change=='operation':parent['tags'][0]['value']=3
            elif change=='alpha':parent['tags'].append(dict(name='AlphaOperation',value=1))
            elif change=='mask':parent['tags'].append(dict(name='Mask',value=dict(id=4,path='White',**{'class':'Texture'})))
            elif change=='diffuse':parent['tags'].append(dict(name='UseDiffuseAlpha',value=True))
            elif change=='sampler':parent['strings'][1]['name']='Fixture.Wrong'
            elif change=='sampler_order':parent['strings'].reverse()
            elif change=='branch_path':documents[3]=('TexPanner','Other',b)
            elif change=='branch_shader':b['shader']=shader(1)
            elif change=='branch_suffix':b['strings'][0]['values']=['Fixture.Wrong']
            elif change=='branch_channel':b['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='branch_class':parent['tags'][2]['value']['class']='TexScaler'
            elif change=='leaf_identity':documents[5]=('Texture','Wrong',documents[5][2])
            elif change=='cycle':a['tags'][1]['value']=dict(id=2,path='PanA',**{'class':'TexPanner'})
            else:documents[5][2]['mips'][0]['data_hex']='00'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)

    def test_wrapper_must_match_combiner_shader_and_texture_bindings(self):
        for change in ('shader','sampler','path','wrong_channel','projected'):
            documents=fixture();coord=documents[6][2]
            if change=='shader':coord['shader']=MULTIPLY_SHADER
            elif change=='sampler':coord['strings'][1]['name']='Fixture.Other'
            elif change=='path':coord['tags'][2]['value']['path']='Wrong'
            elif change=='wrong_channel':coord['tags'][0]['value']=coord['tags'][1]['value']=1
            else:coord['tags'].append(dict(name='TexCoordProjected',value=True))
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.surface(documents,6)

    def test_incomplete_input_and_invalid_time_are_rejected(self):
        core=FixtureCore()
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'fixture.utx',mesh(),'static_mesh',overrides={0:('fixture.utx',1)})
        for seconds in (-1.,3601.,float('nan')):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):
                timed_fragment_uv(geometry,seconds)
        broken=dict(geometry,uv_input=[])
        with self.assertRaisesRegex(ValueError,'topology'):
            timed_fragment_uv(broken,0.)
        broken=dict(geometry,fragment_inputs=[None]*len(geometry['uv_input']))
        with self.assertRaisesRegex(ValueError,'topology'):
            timed_fragment_uv(broken,0.)


if __name__=='__main__':unittest.main()
