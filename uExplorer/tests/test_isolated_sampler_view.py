"""One saved sampler may be inspected without claiming the surrounding material."""
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
from test_coordinate_source_view import bits,mesh,shader
from test_material_snapshot_view import matrix_tag
from test_shader_modifier_view import FixtureCore


def fixture():
    def ref(identifier,path,kind):
        return dict(id=identifier,path=path,**{'class':kind})
    prefix=('float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
            'c1=texcolor0;a1=texcolor0;result.xyz=c1.xyz;result.w=a1.w;')
    sampler='Fixture.Image'
    order=['Fixture.Triggered','Fixture.Rot']
    first=dict(name=sampler,values=order)
    def graph(tags):return dict(tags=tags,strings=[copy.deepcopy(first)],shader=prefix+'ignored;')
    outer=graph([dict(name='Material',value=ref(2,'Shader','Shader')),
                 matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),(.25,0.,1.,0.),(0.,0.,0.,1.)))])
    outer['path']='Outer'
    outer['strings'][0]=dict(name='Image',values=['Fixture.Outer']+order)
    child=graph([dict(name='Diffuse',value=ref(3,'CombinedA','Combiner')),
                 dict(name='Opacity',value=ref(9,'Opacity','Texture'))])
    a=graph([dict(name='CombineOperation',value=6),dict(name='AlphaOperation',value=1),
             dict(name='Material2',value=ref(4,'CombinedB','Combiner'))])
    b=graph([dict(name='CombineOperation',value=3),dict(name='AlphaOperation',value=1),
             dict(name='Material1',value=ref(5,'CombinedC','Combiner'))])
    c=graph([dict(name='CombineOperation',value=2),
             dict(name='Material1',value=ref(6,'Triggered','TexOscillatorTriggered'))])
    trigger=dict(path='Triggered',tags=[
        dict(name='Material',value=ref(7,'Rot','TexRotator')),
        matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,.25,1.,0.),(0.,0.,0.,1.)))],
        strings=[copy.deepcopy(first)],shader=shader(0))
    rot=dict(path='Rot',tags=[
        dict(name='Material',value=ref(8,'Image','Texture')),
        matrix_tag(((0.,1.,0.,0.),(-1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)))],
        strings=[dict(name=sampler,values=['Fixture.Rot'])],shader=shader(0))
    image=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    return {1:('TexPanner','Outer',outer),2:('Shader','Shader',child),
            3:('Combiner','CombinedA',a),4:('Combiner','CombinedB',b),
            5:('Combiner','CombinedC',c),6:('TexOscillatorTriggered','Triggered',trigger),
            7:('TexRotator','Rot',rot),8:('Texture','Image',image),
            9:('Texture','Opacity',image)}


def direct_combiner_fixture(operation=6):
    """Reuse the same saved first branch without the surrounding Shader."""
    if operation not in (3,6):raise ValueError('Unsupported test route')
    documents=fixture()
    identifier,name=(3,'CombinedA') if operation==6 else (4,'CombinedB')
    documents[1][2]['tags'][0]['value']=dict(id=identifier,path=name,**{'class':'Combiner'})
    return documents


class IsolatedSampler(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents)
        return diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=1))

    def test_only_first_sampler_and_saved_matrices_are_shown(self):
        documents=fixture();original=copy.deepcopy(documents)
        surface=self.surface(documents)
        self.assertEqual(surface['isolated_sampler'],0)
        self.assertTrue(surface['uv_snapshot'])
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertFalse(surface['uv0_exact'])
        self.assertEqual(surface['uv_rotation'],(0.,1.,-1.,0.))
        self.assertEqual(surface['uv_offset'],(-.25,.25))
        self.assertTrue(any('не итоговый diffuse' in note and 'opacity' in note
                            and 'состояние Texture вместо Shader' in note
                            and 'анимация Texture не воспроизводятся' in note
                            and 'разным моментам' in note for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['uv'][0],[(-.75,.5)]*3)
        self.assertNotIn('uv_base',geometry)
        self.assertEqual(documents,original)
        # Non-first shader inputs and the Shader framebuffer mode are not executed.
        documents[2][2]['shader']=documents[2][2]['shader'].replace('ignored;','unknown;')
        documents[2][2]['tags'].append(dict(name='OutputBlending',value=255))
        documents[8][2]['tags'].append(dict(name='AnimNext',
            value=dict(id=9,path='Opacity',**{'class':'Texture'})))
        isolated=self.surface(documents)
        self.assertEqual(isolated['isolated_sampler'],0)
        self.assertEqual(isolated['pixels'],surface['pixels'])

    def test_fully_qualified_sampler_does_not_use_an_ambiguous_short_name(self):
        documents=fixture()
        documents[1][2]['strings'][0]['name']='Fixture.Image'
        documents[10]=('Texture','Other.Image',documents[8][2])
        self.assertEqual(self.surface(documents)['isolated_sampler'],0)

    def test_direct_nested_combiner_exposes_only_static_first_sampler(self):
        for operation in (3,6):
            documents=direct_combiner_fixture(operation)
            original=copy.deepcopy(documents)
            with self.subTest(operation=operation):
                surface=self.surface(documents)
                self.assertEqual(surface['isolated_sampler'],0)
                self.assertTrue(surface['uv_snapshot'] and surface['uv_preview_approximate'])
                self.assertFalse(surface['uv_coordinate_exact'] or surface['uv0_exact'])
                self.assertEqual(surface['uv_rotation'],(0.,1.,-1.,0.))
                self.assertEqual(surface['uv_offset'],(-.25,.25))
                self.assertNotIn('fragment_layers',surface)
                self.assertTrue(any('не итоговый diffuse' in note
                                    and 'состояние Texture вместо Combiner' in note
                                    and 'анимация Texture не воспроизводятся' in note
                                    and 'разным моментам' in note for note in surface['notes']))
                with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
                core=FixtureCore(documents)
                with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
                    geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                              overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
                self.assertNotIn('error',geometry)
                self.assertEqual(geometry['uv'][0],[(-.75,.5)]*3)
                self.assertNotIn('uv_base',geometry)
                self.assertEqual(documents,original)

    def test_direct_nested_combiner_rejects_unproven_first_sampler(self):
        changes=('outer_shader','outer_suffix','root_ref','root_alpha','nested_ref','nested_alpha',
                 'leaf_ref','leaf_class','trigger_ref','trigger_shader','trigger_suffix',
                 'rot_ref','rot_shader','rot_suffix','first_sampler','duplicate_root_alpha',
                 'duplicate_inner_ref','duplicate_source','source_type','projected',
                 'missing_matrix','duplicate_matrix','nonplanar','nonfinite','cycle','ambiguous')
        for operation in (3,6):
            for change in changes:
                documents=direct_combiner_fixture(operation)
                parent=documents[1][2];a=documents[3][2];b=documents[4][2];c=documents[5][2]
                trigger=documents[6][2];rot=documents[7][2]
                root=a if operation==6 else b
                if change=='outer_shader':parent['shader']=parent['shader'].replace('tex0.xy','tex1.xy',1)
                elif change=='outer_suffix':parent['strings'][0]['values'].reverse()
                elif change=='root_ref':parent['tags'][0]['value']['path']='Wrong'
                elif change=='root_alpha':root['tags'][1]['value']=0
                elif change=='nested_ref':b['tags'][2]['value']['path']='Wrong'
                elif change=='nested_alpha':b['tags'][1]['value']=0
                elif change=='leaf_ref':rot['tags'][0]['value']['path']='Wrong'
                elif change=='leaf_class':documents[8]=('Cubemap','Image',documents[8][2])
                elif change=='trigger_ref':c['tags'][1]['value']['path']='Wrong'
                elif change=='trigger_shader':trigger['shader']=shader(1)
                elif change=='trigger_suffix':trigger['strings'][0]['values'].pop()
                elif change=='rot_ref':trigger['tags'][0]['value']['path']='Wrong'
                elif change=='rot_shader':rot['shader']=shader(1)
                elif change=='rot_suffix':rot['strings'][0]['values']=['Fixture.Other']
                elif change=='first_sampler':c['strings'][0]['name']='Fixture.Other'
                elif change=='duplicate_root_alpha':root['tags'].append(copy.deepcopy(root['tags'][1]))
                elif change=='duplicate_inner_ref':c['tags'].append(copy.deepcopy(c['tags'][1]))
                elif change=='duplicate_source':
                    trigger['tags'].extend([dict(name='TexCoordSource',value=0),
                                            dict(name='TexCoordSource',value=1)])
                elif change=='source_type':parent['tags'].append(dict(name='TexCoordSource',value=False))
                elif change=='projected':rot['tags'].append(dict(name='TexCoordProjected',value=True))
                elif change=='missing_matrix':trigger['tags'].pop(1)
                elif change=='duplicate_matrix':rot['tags'].append(copy.deepcopy(rot['tags'][1]))
                elif change=='nonplanar':rot['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
                elif change=='nonfinite':rot['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
                elif change=='cycle':rot['tags'][0]['value']=dict(id=1,path='Outer',**{'class':'Texture'})
                else:documents[10]=('Texture','Other.Image',documents[8][2])
                with self.subTest(operation=operation,change=change),self.assertRaises((ValueError,RuntimeError)):
                    self.surface(documents)

    def test_rejects_unverified_first_sampler_path_or_matrices(self):
        changes=('outer_shader','shader_prefix','combiner_prefix','extra_first_sample','trigger_shader',
                 'rot_shader','outer_suffix','shader_suffix','combiner_suffix','trigger_suffix',
                 'rot_suffix','shader_ref','diffuse_ref','combiner_ref','trigger_ref','rot_ref',
                 'texture_ref','texture_class','outer_source','trigger_source','projected',
                 'operation','alpha','duplicate_ref','duplicate_op','missing_matrix','duplicate_matrix',
                 'nonplanar','nonfinite','cycle','short_ambiguous','wrong_short_name')
        for change in changes:
            documents=fixture()
            outer=documents[1][2];child=documents[2][2]
            a=documents[3][2];b=documents[4][2];c=documents[5][2]
            trigger=documents[6][2];rot=documents[7][2]
            if change=='outer_shader':outer['shader']=outer['shader'].replace('tex0.xy','tex1.xy',1)
            elif change=='shader_prefix':child['shader']='unknown;'+child['shader']
            elif change=='combiner_prefix':b['shader']=b['shader'].replace('result.xyz=c1.xyz','result.xyz=c2.xyz',1)
            elif change=='extra_first_sample':c['shader']+='tex2D(s[0],tex0);'
            elif change=='trigger_shader':trigger['shader']=shader(1)
            elif change=='rot_shader':rot['shader']=shader(1)
            elif change=='outer_suffix':outer['strings'][0]['values'].reverse()
            elif change=='shader_suffix':child['strings'][0]['values'].reverse()
            elif change=='combiner_suffix':a['strings'][0]['name']='Fixture.Other'
            elif change=='trigger_suffix':trigger['strings'][0]['values'].pop()
            elif change=='rot_suffix':rot['strings'][0]['values']=['Fixture.Other']
            elif change=='shader_ref':outer['tags'][0]['value']['path']='Wrong'
            elif change=='diffuse_ref':child['tags'][0]['value']['path']='Wrong'
            elif change=='combiner_ref':a['tags'][2]['value']['path']='Wrong'
            elif change=='trigger_ref':c['tags'][1]['value']['path']='Wrong'
            elif change=='rot_ref':trigger['tags'][0]['value']['path']='Wrong'
            elif change=='texture_ref':rot['tags'][0]['value']['path']='Wrong'
            elif change=='texture_class':documents[8]=('Cubemap','Image',documents[8][2])
            elif change=='outer_source':outer['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='trigger_source':trigger['tags'].append(dict(name='TexCoordSource',value=2))
            elif change=='projected':rot['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='operation':b['tags'][0]['value']=2
            elif change=='alpha':a['tags'][1]['value']=0
            elif change=='duplicate_ref':trigger['tags'].append(copy.deepcopy(trigger['tags'][0]))
            elif change=='duplicate_op':c['tags'].append(copy.deepcopy(c['tags'][0]))
            elif change=='missing_matrix':trigger['tags'].pop(1)
            elif change=='duplicate_matrix':rot['tags'].append(copy.deepcopy(rot['tags'][1]))
            elif change=='nonplanar':rot['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            elif change=='nonfinite':rot['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            elif change=='cycle':rot['tags'][0]['value']=dict(id=1,path='Outer',**{'class':'Texture'})
            elif change=='short_ambiguous':documents[10]=('Texture','Other.Image',documents[8][2])
            else:outer['strings'][0]['name']='Wrong'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)


if __name__=='__main__':unittest.main()
