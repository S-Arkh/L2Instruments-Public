"""Inspect one sampler from a nested Rotator/Combiner without evaluating it."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_frames import select_material_frame,selectable_samplers
from material_graph import ResourceResolver
from material_math import shared_grid
from material_surface import diffuse
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh,shader
from test_material_snapshot_view import matrix_tag
from test_shader_modifier_view import FixtureCore


def fixture():
    def ref(identifier,path,kind):
        return dict(id=identifier,path=path,**{'class':kind})
    prefix=('float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
            'c1=texcolor0;a1=texcolor0;result.xyz=c1.xyz;result.w=a1.w;')
    sampler='Fixture.Image'
    names=['Fixture.Outer','Fixture.Rot','Fixture.Osc','Fixture.Scale']
    def graph(tags):
        return dict(tags=tags,strings=[dict(name=sampler,values=names[1:])],
                    shader=prefix+'other branches are not evaluated;')
    outer=graph([dict(name='Material',value=ref(2,'First','Combiner')),
                 matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),(.25,0.,1.,0.),(0.,0.,0.,1.)))])
    outer['strings']=[dict(name=sampler,values=names)]
    first=graph([dict(name='CombineOperation',value=5),
                 dict(name='Material2',value=ref(3,'Second','Combiner'))])
    second=graph([dict(name='CombineOperation',value=5),
                  dict(name='Material2',value=ref(4,'Third','Combiner'))])
    third=graph([dict(name='CombineOperation',value=6),
                 dict(name='Material1',value=ref(5,'Rot','TexRotator'))])
    def modifier(identifier,path,kind,values,rows):
        return dict(tags=[dict(name='Material',value=ref(identifier,path,kind)),matrix_tag(rows)],
                    strings=[dict(name=sampler,values=values)],shader=shader(0))
    rot=modifier(6,'Osc','TexOscillator',names[1:],
                 ((0.,1.,0.,0.),(-1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)))
    osc=modifier(7,'Scale','TexScaler',names[2:],
                 ((1.,0.,0.,0.),(0.,1.,0.,0.),(.125,0.,1.,0.),(0.,0.,0.,1.)))
    scale=modifier(8,'Image','Texture',names[3:],
                   ((2.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)))
    image=dict(tags=[dict(name='Format',value=5),
                     dict(name='AnimNext',value=ref(9,'Next','Texture'))],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    next_frame=dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='ff0000ffff0000ff')])
    return {1:('TexRotator','Outer',outer),2:('Combiner','First',first),
            3:('Combiner','Second',second),4:('Combiner','Third',third),
            5:('TexRotator','Rot',rot),6:('TexOscillator','Osc',osc),
            7:('TexScaler','Scale',scale),8:('Texture','Image',image),
            9:('Texture','Next',next_frame)}


class RotatorNestedIsolated(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents);resolver=ResourceResolver(core)
        return core,resolver,diffuse(core,resolver,'Fixture.utx',dict(id=1))

    def test_only_first_sampler_and_four_saved_matrices_are_shown(self):
        documents=fixture();original=copy.deepcopy(documents)
        core,resolver,surface=self.surface(documents)
        self.assertEqual(surface['isolated_sampler'],0)
        self.assertTrue(surface['uv_snapshot'] and surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'] or surface['uv0_exact'])
        self.assertEqual(surface['uv_rotation'],(0.,1.,-2.,0.))
        self.assertEqual(surface['uv_offset'],(.25,.25))
        self.assertNotIn('fragment_layers',surface)
        self.assertTrue(any('не итоговый diffuse' in note
                            and 'состояние Texture вместо Combiner' in note
                            and 'остальные ветви' in note and 'разным моментам' in note
                            for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['uv'][0],[(-.75,.5)]*3)
        self.assertNotIn('uv_base',geometry)
        self.assertEqual(documents,original)

    def test_saved_frame_is_independent_of_snapshot_and_never_exact(self):
        core,resolver,surface=self.surface(fixture())
        self.assertEqual(selectable_samplers(surface),[0])
        selected=select_material_frame(core,resolver,surface,0,1)
        self.assertEqual(selected['pixels'],bytes.fromhex('0000ffff0000ffff'))
        self.assertEqual(selected['uv_rotation'],surface['uv_rotation'])
        self.assertEqual(selected['uv_offset'],surface['uv_offset'])
        self.assertTrue(selected['uv_snapshot'] and selected['uv_preview_approximate'])
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([selected])
        with self.assertRaises(ValueError):select_material_frame(core,resolver,surface,1,1)

    def test_nested_composition_rejects_the_approximate_sampler(self):
        documents=fixture()
        documents[10]=('Combiner','OuterBlend',dict(tags=[
            dict(name='CombineOperation',value=2),dict(name='AlphaOperation',value=1),
            dict(name='Material1',value=dict(id=1,path='Outer',**{'class':'TexRotator'})),
            dict(name='Material2',value=dict(id=8,path='Image',**{'class':'Texture'}))]))
        core=FixtureCore(documents)
        with self.assertRaisesRegex(ValueError,'supported matching UV|verified direct-texture'):
            diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=10))

    def test_unverified_route_bindings_and_matrices_are_rejected(self):
        changes=('parent_ref','parent_kind','first_operation','first_alpha','second_ref',
                 'second_operation','second_alpha','third_ref','third_operation','third_alpha',
                 'inner_ref','osc_ref','scale_ref','texture_ref','texture_class','bool_id',
                 'parent_sampler','parent_suffix','graph_sampler','graph_suffix','modifier_suffix',
                 'parent_shader','graph_shader','extra_first_sample','inner_shader','osc_shader',
                 'scale_shader','parent_source','inner_source_type','osc_count','scale_projected_type',
                 'duplicate_ref','duplicate_operation','duplicate_source','missing_matrix',
                 'duplicate_matrix','case_duplicate_matrix','nonplanar','nonfinite','cycle')
        for change in changes:
            documents=fixture()
            parent,first,second,third,rot,osc,scale=(documents[i][2] for i in range(1,8))
            if change=='parent_ref':parent['tags'][0]['value']['path']='Wrong'
            elif change=='parent_kind':parent['tags'][0]['value']['class']='Shader'
            elif change=='first_operation':first['tags'][0]['value']=4
            elif change=='first_alpha':first['tags'].append(dict(name='AlphaOperation',value=1))
            elif change=='second_ref':first['tags'][1]['value']['path']='Wrong'
            elif change=='second_operation':second['tags'][0]['value']=6
            elif change=='second_alpha':second['tags'].append(dict(name='AlphaOperation',value=False))
            elif change=='third_ref':second['tags'][1]['value']['path']='Wrong'
            elif change=='third_operation':third['tags'][0]['value']=3
            elif change=='third_alpha':third['tags'].append(dict(name='AlphaOperation',value=1))
            elif change=='inner_ref':third['tags'][1]['value']['path']='Wrong'
            elif change=='osc_ref':rot['tags'][0]['value']['path']='Wrong'
            elif change=='scale_ref':osc['tags'][0]['value']['path']='Wrong'
            elif change=='texture_ref':scale['tags'][0]['value']['path']='Wrong'
            elif change=='texture_class':documents[8]=('Cubemap','Image',documents[8][2])
            elif change=='bool_id':scale['tags'][0]['value']['id']=True
            elif change=='parent_sampler':parent['strings'][0]['name']='Image'
            elif change=='parent_suffix':parent['strings'][0]['values'].reverse()
            elif change=='graph_sampler':second['strings'][0]['name']='Fixture.Other'
            elif change=='graph_suffix':third['strings'][0]['values'].reverse()
            elif change=='modifier_suffix':osc['strings'][0]['values'].reverse()
            elif change=='parent_shader':parent['shader']=parent['shader'].replace('tex0.xy','tex1.xy',1)
            elif change=='graph_shader':second['shader']='unknown;'+second['shader']
            elif change=='extra_first_sample':third['shader']+='tex2D(s[0],tex0);'
            elif change=='inner_shader':rot['shader']=shader(1)
            elif change=='osc_shader':osc['shader']=shader(1)
            elif change=='scale_shader':scale['shader']=shader(1)
            elif change=='parent_source':parent['tags'].append(dict(name='TexCoordSource',value=2))
            elif change=='inner_source_type':rot['tags'].append(dict(name='TexCoordSource',value=False))
            elif change=='osc_count':osc['tags'].append(dict(name='TexCoordCount',value=1))
            elif change=='scale_projected_type':scale['tags'].append(dict(name='TexCoordProjected',value=0))
            elif change=='duplicate_ref':osc['tags'].append(copy.deepcopy(osc['tags'][0]))
            elif change=='duplicate_operation':second['tags'].append(copy.deepcopy(second['tags'][0]))
            elif change=='duplicate_source':
                parent['tags'].extend([dict(name='TexCoordSource',value=0),
                                       dict(name='TexCoordSource',value=1)])
            elif change=='missing_matrix':osc['tags'].pop(1)
            elif change=='duplicate_matrix':rot['tags'].append(copy.deepcopy(rot['tags'][1]))
            elif change=='case_duplicate_matrix':
                extra=copy.deepcopy(rot['tags'][1]);extra['name']='m';rot['tags'].append(extra)
            elif change=='nonplanar':scale['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            elif change=='nonfinite':osc['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            else:scale['tags'][0]['value']=dict(id=1,path='Outer',**{'class':'Texture'})
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)


if __name__=='__main__':unittest.main()
