"""UV modifiers over Shader expose a labelled diffuse-only diagnostic."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_graph import ResourceResolver
from material_math import shared_grid
from material_surface import diffuse
from material_uv import timed_uv
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh,shader as coordinate_shader
from test_material_snapshot_view import matrix_tag


def fixture(kind='TexPanner'):
    child_shader=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;c2=diffuse;'
                  'a1=texcolor0;a2=diffuse;result.xyz=c1.xyz*c2.xyz*mFactor;'
                  'result.w=a1.w*a2.w;SpecularMask=result.w;'
                  'float4 texcolor1=tex2D(s[1],tex0);c1=result;c2=texcolor1;'
                  'a1=result;result.xyz=c1.xyz+c1.w*c2.xyz;result.w=a1.w;')
    names=['Fixture.Image','Fixture.Specular']
    child=dict(tags=[dict(name='Diffuse',value=dict(id=3,path='Image',**{'class':'Texture'})),
                     dict(name='Specular',value=dict(id=4,path='Specular',**{'class':'Texture'}))],
               strings=[dict(name=name,values=[]) for name in names],shader=child_shader)
    outer_shader=child_shader
    for index in range(2):
        outer_shader=outer_shader.replace(f'tex2D(s[{index}],tex0)',
            f'tex2D(s[{index}],mul(m{index},float3(tex0.xy,1.f)))')
    tags=[dict(name='Material',value=dict(id=2,path='Shader',**{'class':'Shader'}))]
    if kind=='TexPanner':tags.append(dict(name='PanRate',bits=bits(.5)[0]))
    elif kind=='TexOscillator':
        tags.extend([dict(name='UOscillationType',value=1),
                     dict(name='UOscillationAmplitude',bits=bits(.5)[0])])
    else:
        tags.append(matrix_tag(((0.,1.,0.,0.),(-1.,0.,0.,0.),
                                (.25,.5,1.,0.),(0.,0.,0.,1.))))
    outer=dict(path='Modifier',tags=tags,
               strings=[dict(name=name,values=['Fixture.Modifier']) for name in names],
               shader=outer_shader)
    image=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    return {1:(kind,'Modifier',outer),2:('Shader','Shader',child),
            3:('Texture','Image',image),4:('Texture','Specular',image)}


def multipass_fixture():
    documents=fixture()
    parent=documents[1][2];child=documents[2][2]
    first=child['shader'].split('SpecularMask',1)[0]
    second='float4 texcolor1=tex2D(s[1],tex0);result.xyz=texcolor1.xyz;'
    child['shader']='if(currentpass==0){'+first+'}if(currentpass==1){'+second+'}'
    parent['shader']=child['shader'].replace('tex2D(s[0],tex0)',
        'tex2D(s[0],mul(m0,float3(tex0.xy,1.f)))')
    parent['strings'][1]['values']=[]
    return documents


def shader_panner_snapshot_fixture():
    documents=fixture('TexRotator')
    parent=documents[1][2];child=documents[2][2]
    child['tags'][0]['value']=dict(id=5,path='Inner',**{'class':'TexPanner'})
    child['shader']=parent['shader']
    child['strings'][0]['values']=['Fixture.Inner']
    child['strings'][1]['values']=['Fixture.OtherMod']
    parent['strings'][0]['values'].append('Fixture.Inner')
    parent['strings'][1]['values'].append('Fixture.OtherMod')
    panner=dict(path='Inner',tags=[
        dict(name='Material',value=dict(id=3,path='Image',**{'class':'Texture'})),
        matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),(.5,0.,1.,0.),(0.,0.,0.,1.)))],
        strings=[dict(name='Fixture.Image',values=['Fixture.Inner'])],
        shader=coordinate_shader(0))
    documents[5]=('TexPanner','Inner',panner)
    return documents


class FixtureCore:
    def __init__(self,documents=None):self.documents=documents or fixture()
    def request(self,**fields):
        if fields['operation']=='resource_inventory':
            return dict(result=dict(candidates=[
                dict(id=i,path=path,serial_bytes=0,**{'class':kind})
                for i,(kind,path,_) in self.documents.items()]))
        return dict(result=self.documents[fields['object_id']][2])


class ShaderModifier(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents)
        return diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=1))

    def test_partial_diffuse_is_warned_and_never_exact_composition(self):
        for kind in ('TexPanner','TexOscillator','TexRotator'):
            documents=fixture(kind);original=copy.deepcopy(documents)
            surface=self.surface(documents)
            self.assertTrue(surface['uv_preview_approximate'])
            self.assertFalse(surface['uv_coordinate_exact'])
            self.assertTrue(any('только diffuse' in note and 'остальные карты' in note
                                for note in surface['notes']))
            with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
            core=FixtureCore(documents)
            with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
                geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                          overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
            self.assertNotIn('error',geometry)
            if kind=='TexPanner':
                self.assertEqual(timed_uv(geometry,1.)[0],[(.75,.5)]*3)
            elif kind=='TexOscillator':
                self.assertNotEqual(timed_uv(geometry,.25)[0],geometry['uv'][0])
            else:
                self.assertTrue(surface['uv_snapshot'])
                self.assertTrue(any('только сохранённая UV-матрица' in note for note in surface['notes']))
                self.assertEqual(geometry['uv'][0],[(-.25,.75)]*3)
                self.assertNotIn('uv_base',geometry)
            self.assertEqual(documents,original)

    def test_rejects_unverified_bindings_shaders_and_state(self):
        changes=('parent_shader','child_prefix','child_extra_sample','parent_suffix','child_suffix',
                 'child_path','texture_path','texture_id','diffuse_class','opacity','opacity_class',
                 'source','projected','pivot','jitter')
        for change in changes:
            documents=fixture('TexOscillator' if change in ('pivot','jitter') else 'TexPanner')
            outer=documents[1][2];child=documents[2][2]
            if change=='parent_shader':outer['shader']+='unknown;'
            elif change=='child_prefix':child['shader']='unknown;'+child['shader']
            elif change=='child_extra_sample':child['shader']+='tex2D(s[2],tex0);'
            elif change=='parent_suffix':outer['strings'][1]['values']=['Fixture.Wrong']
            elif change=='child_suffix':child['strings'][0]['values']=['Fixture.Wrong']
            elif change=='child_path':outer['tags'][0]['value']['path']='Wrong'
            elif change=='texture_path':documents[3]=('Texture','Wrong',documents[3][2])
            elif change=='texture_id':child['tags'][0]['value']['id']=4
            elif change=='diffuse_class':child['tags'][0]['value']['class']=None
            elif change=='opacity':child['tags'].append(dict(name='Opacity',value=dict(id=4,path='Specular',**{'class':'Texture'})))
            elif change=='opacity_class':child['tags'].append(dict(name='Opacity',value=dict(id=3,path='Image',**{'class':None})))
            elif change=='source':outer['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='projected':outer['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='pivot':outer['tags'].append(dict(name='UOffset',bits=bits(1.)[0]))
            else:outer['tags'].append(dict(name='VOscillationType',value=3))
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)

    def test_short_sampler_requires_unique_resolved_texture(self):
        documents=fixture()
        documents[1][2]['strings'][0]['name']='Image'
        documents[2][2]['strings'][0]['name']='Image'
        self.assertTrue(self.surface(documents)['uv_preview_approximate'])
        documents[5]=('Texture','Other.Image',documents[3][2])
        with self.assertRaisesRegex(ValueError,'diffuse Texture'):
            self.surface(documents)

    def test_opacity_may_reference_the_same_resolved_texture(self):
        documents=fixture()
        documents[2][2]['tags'].append(dict(name='Opacity',value=dict(id=3,path='Image',**{'class':'Texture'})))
        surface=self.surface(documents)
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertTrue(any('Shader.Opacity' in note for note in surface['notes']))

    def test_ignored_shader_sampler_may_have_its_own_saved_modifier(self):
        documents=fixture()
        parent=documents[1][2];child=documents[2][2]
        child['strings'][1]['values']=['Fixture.OtherMod']
        parent['strings'][1]['values'].append('Fixture.OtherMod')
        child['shader']=child['shader'].replace(
            'tex2D(s[1],tex0)','tex2D(s[1],mul(m1,float3(tex0.xy,1.f)))')
        self.assertTrue(self.surface(documents)['uv_preview_approximate'])
        parent['strings'][1]['values'].reverse()
        with self.assertRaisesRegex(ValueError,'sampler suffix'):
            self.surface(documents)

    def test_ignored_environment_sampler_is_never_rendered_as_diffuse(self):
        for function in ('tex2D','texCUBE'):
            documents=fixture()
            parent=documents[1][2];child=documents[2][2]
            child['shader']=child['shader'].replace(
                'tex2D(s[1],tex0)',f'{function}(s[1],EnvTex.tex4)')
            parent['shader']=parent['shader'].replace(
                'tex2D(s[1],mul(m1,float3(tex0.xy,1.f)))',
                f'{function}(s[1],mul(m1,float4(EnvTex.tex4,1.f)))')
            with self.subTest(function=function):
                surface=self.surface(documents)
                self.assertTrue(surface['uv_preview_approximate'])
                self.assertTrue(any('environment mapping не вычисляется' in note for note in surface['notes']))
                parent['shader']=parent['shader'].replace('EnvTex.tex4','tex0')
                with self.assertRaisesRegex(ValueError,'transformed shader'):
                    self.surface(documents)

    def test_multipass_only_shows_verified_first_diffuse_pass(self):
        documents=multipass_fixture()
        surface=self.surface(documents)
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertTrue(any('другие проходы и их sampler не вычисляются' in note
                            and 'состояния проходов не подтверждены' in note for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        # A later pass and its metadata are deliberately not inspected or executed.
        documents[1][2]['shader']=documents[1][2]['shader'].replace('texcolor1.xyz','unknown.xyz')
        documents[1][2]['strings'][1]={'unverified':'ignored'}
        self.assertTrue(self.surface(documents)['uv_preview_approximate'])

    def test_multipass_rejects_invalid_first_pass_and_binding(self):
        changes=('outer_uv','child_operation','both_extra_assignment','nested_first',
                 'different_first_sampler','outer_suffix','missing_pass_end','wrong_pass')
        for change in changes:
            documents=multipass_fixture()
            parent=documents[1][2];child=documents[2][2]
            if change=='outer_uv':
                parent['shader']=parent['shader'].replace('mul(m0,float3(tex0.xy,1.f))','tex1')
            elif change=='child_operation':
                child['shader']=child['shader'].replace('result.w=a1.w*a2.w','result.w=a1.w')
            elif change=='both_extra_assignment':
                for doc in (parent,child):doc['shader']=doc['shader'].replace(
                    'result.w=a1.w*a2.w;}','result.w=a1.w*a2.w;result.xyz=other;}')
            elif change=='nested_first':
                for doc in (parent,child):doc['shader']=doc['shader'].replace(
                    'result.w=a1.w*a2.w;}','result.w=a1.w*a2.w;{bad;}')
            elif change=='different_first_sampler':
                child['strings'][0]['name']=parent['strings'][0]['name']='Fixture.Specular'
            elif change=='outer_suffix':parent['strings'][0]['values']=['Fixture.Other']
            elif change=='missing_pass_end':parent['shader']=parent['shader'].replace('}','',1)
            else:parent['shader']=parent['shader'].replace('currentpass==0','currentpass==1',1)
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)

    def test_shader_panner_saved_matrices_are_partial_static_snapshot(self):
        documents=shader_panner_snapshot_fixture();original=copy.deepcopy(documents)
        surface=self.surface(documents)
        self.assertTrue(surface['uv_snapshot'])
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv0_exact'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertEqual(surface['uv_rotation'],(0.,1.,-1.,0.))
        self.assertEqual(surface['uv_offset'],(.75,.5))
        self.assertNotIn('uv_pan_rate',surface)
        self.assertTrue(any('могут относиться к разным моментам' in note
                            and 'остальные карты' in note for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['uv'][0],[(.25,.75)]*3)
        self.assertNotIn('uv_base',geometry)
        self.assertEqual(documents,original)
        # Other shader inputs are neither evaluated nor claimed as verified.
        documents[2][2]['strings'][1]={'ignored':True}
        self.assertTrue(self.surface(documents)['uv_snapshot'])

    def test_shader_panner_snapshot_rejects_unverified_inputs(self):
        changes=('outer_shader','shader_prefix','repeat_first_sampler','panner_shader','outer_suffix',
                 'shader_suffix','panner_suffix','shader_ref','panner_ref','texture_ref',
                 'panner_class','texture_class','opacity','outer_source','inner_source',
                 'projected','missing_outer_matrix','missing_inner_matrix','duplicate_matrix',
                 'nonplanar','nonfinite','cycle','short_sampler','duplicate_diffuse',
                 'duplicate_material','duplicate_source','invalid_source_type')
        for change in changes:
            documents=shader_panner_snapshot_fixture()
            parent=documents[1][2];child=documents[2][2];panner=documents[5][2]
            if change=='outer_shader':parent['shader']+='unknown;'
            elif change=='shader_prefix':child['shader']=child['shader'].replace('tex0.xy','tex1.xy',1)
            elif change=='repeat_first_sampler':
                for doc in (parent,child):doc['shader']+='tex2D(s[0],tex0);'
            elif change=='panner_shader':panner['shader']=coordinate_shader(1)
            elif change=='outer_suffix':parent['strings'][0]['values'].reverse()
            elif change=='shader_suffix':child['strings'][0]['values']=['Fixture.Other']
            elif change=='panner_suffix':panner['strings'][0]['values']=['Fixture.Other']
            elif change=='shader_ref':parent['tags'][0]['value']['path']='Wrong'
            elif change=='panner_ref':child['tags'][0]['value']['path']='Wrong'
            elif change=='texture_ref':panner['tags'][0]['value']['path']='Wrong'
            elif change=='panner_class':documents[5]=('TexScaler','Inner',panner)
            elif change=='texture_class':documents[3]=('Cubemap','Image',documents[3][2])
            elif change=='opacity':child['tags'].append(dict(name='Opacity',value=dict(id=3,path='Image',**{'class':'Texture'})))
            elif change=='outer_source':parent['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='inner_source':panner['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='projected':panner['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='missing_outer_matrix':parent['tags'].pop(1)
            elif change=='missing_inner_matrix':panner['tags'].pop(1)
            elif change=='duplicate_matrix':panner['tags'].append(copy.deepcopy(panner['tags'][1]))
            elif change=='nonplanar':panner['tags'][1]['members'][0]['members'][2]['bits']=bits(.1)[0]
            elif change=='nonfinite':panner['tags'][1]['members'][0]['members'][0]['bits']=bits(float('nan'))[0]
            elif change=='cycle':panner['tags'][0]['value']=dict(id=1,path='Modifier',**{'class':'Texture'})
            elif change=='duplicate_diffuse':child['tags'].append(copy.deepcopy(child['tags'][0]))
            elif change=='duplicate_material':panner['tags'].append(copy.deepcopy(panner['tags'][0]))
            elif change=='duplicate_source':
                parent['tags'].extend([dict(name='TexCoordSource',value=0),dict(name='TexCoordSource',value=1)])
            elif change=='invalid_source_type':parent['tags'].append(dict(name='TexCoordSource',value=False))
            else:
                for doc in (parent,child):doc['strings'][0]['name']='Image'
                panner['strings'][0]['name']='Image'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)

    def test_approximate_modifier_limits_remain_visible(self):
        documents=fixture('TexPanner')
        documents[1][2]['tags'].append(dict(name='PanDirection',words=[0,0,4]))
        self.assertTrue(any('Roll:' in note and 'точность не подтверждена' in note
                            for note in self.surface(documents)['notes']))
        documents=fixture('TexOscillator')
        next(tag for tag in documents[1][2]['tags'] if tag['name']=='UOscillationType')['value']=2
        surface=self.surface(documents)
        self.assertTrue(surface['uv_oscillation_preview'])
        self.assertTrue(any('stretch-repeat:' in note and 'точность не подтверждена' in note
                            for note in surface['notes']))

    def test_unknown_oscillator_pivot_or_jitter_use_only_a_saved_snapshot(self):
        for change in ('pivot','jitter'):
            documents=fixture('TexOscillator')
            outer=documents[1][2]
            outer['tags'].append(matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),
                                             (.25,.5,1.,0.),(0.,0.,0.,1.))))
            if change=='pivot':outer['tags'].append(dict(name='UOffset',bits=bits(1.)[0]))
            else:outer['tags'].append(dict(name='VOscillationType',value=3))
            with self.subTest(change=change):
                surface=self.surface(documents)
                self.assertTrue(surface['uv_snapshot'])
                self.assertNotIn('uv_oscillation',surface)
                self.assertFalse(surface['uv_coordinate_exact'])
                self.assertEqual(surface['uv_offset'],(.25,.5))
                self.assertTrue(any('случайное состояние' in note and 'не восстанавливаются' in note
                                    for note in surface['notes']))


if __name__=='__main__':unittest.main()
