"""A bounded Panner over two direct textures samples each grid on the GPU."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_graph import ResourceResolver
from material_math import shared_grid
from material_surface import diffuse
from material_uv import timed_fragment_uv,timed_uv
from textured_mesh import prepare_textured
from test_coordinate_source_view import bits,mesh
from test_shader_modifier_view import FixtureCore


def fixture(color=2,alpha=0):
    def ref(identifier,path,kind):return dict(id=identifier,path=path,**{'class':kind})
    assert (color,alpha) in ((2,0),(2,1),(3,1))
    names=['Fixture.First','Fixture.Second']
    child_shader=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
                  'result.xyz=c1.xyz;result.w=a1.w;'
                  'float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;')
    child_shader+=('a1=result;' if alpha==0 else 'a1=texcolor1;a2=result;')
    child_shader+=('result.xyz=c1.xyz*c2.xyz*2.f;' if color==2 else
                   'result.xyz=c1.xyz+c2.xyz;')
    child_shader+=('result.w=a1.w;' if alpha==0 else 'result.w=a1.w*a2.w;')
    child_shader+=('c1=diffuse;c2=result;a2=result;'
                   'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;')
    tags=[dict(name='CombineOperation',value=color),dict(name='AlphaOperation',value=alpha),
          dict(name='Material1',value=ref(3,'First','Texture')),
          dict(name='Material2',value=ref(4,'Second','Texture'))]
    if color==2:tags.append(dict(name='Modulate2X',value=True))
    child=dict(tags=tags,strings=[dict(name=n,values=[]) for n in names],shader=child_shader)
    parent_shader=child_shader
    for index in range(2):
        parent_shader=parent_shader.replace(f'tex2D(s[{index}],tex0)',
            f'tex2D(s[{index}],mul(m{index},float3(tex0.xy,1.f)))')
    parent=dict(path='Pan',tags=[dict(name='Material',value=ref(2,'Blend','Combiner')),
                                  dict(name='PanRate',bits=bits(.5)[0])],
                strings=[dict(name=n,values=['Fixture.Pan']) for n in names],shader=parent_shader)
    first=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
    second=dict(tags=[dict(name='Format',value=5)],
                mips=[dict(width=1,height=1,data_hex='20408080')])
    return {1:('TexPanner','Pan',parent),2:('Combiner','Blend',child),
            3:('Texture','First',first),4:('Texture','Second',second)}


class PannerCombiner(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents)
        return diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=1))

    def test_independent_grids_share_diagnostic_uv_and_never_compose(self):
        for color,alpha in ((2,0),(2,1),(3,1)):
            documents=fixture(color,alpha);original=copy.deepcopy(documents)
            with self.subTest(color=color,alpha=alpha):
                surface=self.surface(documents)
                self.assertTrue(surface['fragment_independent_uv'])
                self.assertTrue(surface['uv_preview_approximate'])
                self.assertFalse(surface['uv_coordinate_exact'])
                self.assertEqual((surface['fragment_operation'],surface['fragment_alpha'],
                                  surface['fragment_multiplier']),(color,alpha,2 if color==2 else 1))
                self.assertEqual([(layer['width'],layer['height']) for layer in surface['fragment_layers']],
                                 [(2,1),(1,1),(2,1)])
                self.assertTrue(any('фильтрует две Texture отдельно' in note and 'не игровые часы' in note
                                    and 'анимация кадров Texture не воспроизводится' in note
                                    for note in surface['notes']))
                with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
                core=FixtureCore(documents)
                with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
                    geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                              overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
                self.assertNotIn('error',geometry)
                self.assertEqual(geometry['fragment_uv'][0],([(.25,.5)]*3,)*3)
                self.assertEqual(timed_uv(geometry,1.)[0],[(.75,.5)]*3)
                self.assertEqual(timed_fragment_uv(geometry,1.)[0],([(.75,.5)]*3,)*3)
                self.assertEqual(timed_fragment_uv(geometry,0.),geometry['fragment_uv'])
                self.assertEqual(documents,original)

    def test_unrecognized_shader_properties_and_bindings_are_rejected(self):
        changes=('operation','alpha','modulate2','modulate4','invert','diffuse_alpha','mask',
                 'parent_shader','child_shader','parent_suffix','child_sampler','child_suffix',
                 'child_path','first_path','second_path','first_class','second_class',
                 'cycle','projected','source','duplicate_operation','duplicate_parent_ref','truncated',
                 'source_type','count_type','projected_type','flag_type','duplicate_rate',
                 'duplicate_direction','direction_name','direction_word_type')
        for change in changes:
            documents=fixture();parent=documents[1][2];child=documents[2][2]
            if change=='operation':child['tags'][0]['value']=4
            elif change=='alpha':child['tags'][1]['value']=2
            elif change=='modulate2':child['tags'][4]['value']=False
            elif change=='modulate4':child['tags'].append(dict(name='Modulate4X',value=True))
            elif change=='invert':child['tags'].append(dict(name='InvertMask',value=True))
            elif change=='diffuse_alpha':child['tags'].append(dict(name='UseDiffuseAlpha',value=True))
            elif change=='mask':child['tags'].append(dict(name='Mask',value=dict(id=3,path='First',**{'class':'Texture'})))
            elif change=='parent_shader':parent['shader']+='unknown;'
            elif change=='child_shader':child['shader']=child['shader'].replace('*2.f','')
            elif change=='parent_suffix':parent['strings'][1]['values']=['Fixture.Wrong']
            elif change=='child_sampler':child['strings'][1]['name']='Fixture.Wrong'
            elif change=='child_suffix':child['strings'][0]['values']=['Fixture.Wrong']
            elif change=='child_path':parent['tags'][0]['value']['path']='Wrong'
            elif change=='first_path':child['tags'][2]['value']['path']='Wrong'
            elif change=='second_path':child['tags'][3]['value']['path']='Wrong'
            elif change=='first_class':documents[3]=('Cubemap','First',documents[3][2])
            elif change=='second_class':child['tags'][3]['value']['class']='TexPanner'
            elif change=='cycle':child['tags'][2]['value']=dict(id=1,path='Pan',**{'class':'Texture'})
            elif change=='projected':parent['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='source':parent['tags'].append(dict(name='TexCoordSource',value=1))
            elif change=='duplicate_operation':child['tags'].append(copy.deepcopy(child['tags'][0]))
            elif change=='duplicate_parent_ref':parent['tags'].append(copy.deepcopy(parent['tags'][0]))
            elif change=='source_type':parent['tags'].append(dict(name='TexCoordSource',value=False))
            elif change=='count_type':parent['tags'].append(dict(name='TexCoordCount',value=False))
            elif change=='projected_type':parent['tags'].append(dict(name='TexCoordProjected',value=0))
            elif change=='flag_type':child['tags'].append(dict(name='Modulate4X',value=0))
            elif change=='duplicate_rate':parent['tags'].append(copy.deepcopy(parent['tags'][1]))
            elif change=='duplicate_direction':
                parent['tags'].extend([dict(name='PanDirection',words=[0,0,0]),
                                       dict(name='pandirection',words=[0,1,0])])
            elif change=='direction_name':parent['tags'].append(dict(name='pandirection',words=[0,0,0]))
            elif change=='direction_word_type':parent['tags'].append(dict(name='PanDirection',words=[0,False,0]))
            else:documents[4][2]['mips'][0]['data_hex']='00'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)

    def test_noninvariant_roll_has_an_explicit_warning(self):
        documents=fixture()
        documents[1][2]['tags'].append(dict(name='PanDirection',words=[0,0,4]))
        surface=self.surface(documents)
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertTrue(any('Roll:' in note and 'точность не подтверждена' in note
                            for note in surface['notes']))

    def test_approximate_fragment_cannot_be_wrapped_in_scaler_even_when_stationary(self):
        documents=fixture()
        documents[1][2]['tags'][1]['bits']=bits(0.)[0]
        documents[5]=('TexScaler','Scale',dict(tags=[
            dict(name='Material',value=dict(id=1,path='Pan',**{'class':'TexPanner'}))]))
        core=FixtureCore(documents)
        with self.assertRaisesRegex(ValueError,'UV chain requires a direct Texture leaf'):
            diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=5))
        documents[5][2]['tags'][0]['value']=dict(id=6,path='Wrapper',**{'class':'Shader'})
        documents[6]=('Shader','Wrapper',dict(tags=[
            dict(name='Diffuse',value=dict(id=1,path='Pan',**{'class':'TexPanner'}))]))
        with self.assertRaisesRegex(ValueError,'cannot transform an approximate fragment'):
            diffuse(core,ResourceResolver(core),'Fixture.utx',dict(id=5))


if __name__=='__main__':unittest.main()
