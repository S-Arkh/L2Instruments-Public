"""One saved operation-7 shader is a labelled, filtered GPU diagnostic."""
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
from material_uv import timed_fragment_uv
from textured_mesh import prepare_textured
from test_coordinate_source_view import mesh
from test_shader_modifier_view import FixtureCore


def fixture():
    def ref(identifier,path,kind='Texture'):
        return dict(id=identifier,path=path,**{'class':kind})
    shader=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
            'result.xyz=c1.xyz;result.w=a1.w;'
            'float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;'
            'c2.xyz=c2.w;a1=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w;'
            'c1=diffuse;c2=result;a2=result;'
            'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;')
    combiner=dict(tags=[dict(name='CombineOperation',value=7),
                        dict(name='Material1',value=ref(2,'MaskTexture')),
                        dict(name='Material2',value=ref(3,'ColorTexture')),
                        dict(name='Mask',value=ref(2,'MaskTexture'))],
                  strings=[dict(name='Fixture.MaskTexture',values=[]),
                           dict(name='Fixture.ColorTexture',values=[])],shader=shader)
    first=dict(tags=[dict(name='Format',value=5)],
               mips=[dict(width=2,height=1,data_hex='0000ff8000ff0040')])
    second=dict(tags=[dict(name='Format',value=5),
                      dict(name='AnimNext',value=ref(4,'NextColor'))],
                mips=[dict(width=1,height=1,data_hex='204080ff')])
    next_frame=dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=1,height=1,data_hex='4080c0ff')])
    return {1:('Combiner','Blend',combiner),2:('Texture','MaskTexture',first),
            3:('Texture','ColorTexture',second),4:('Texture','NextColor',next_frame)}


class AlphaModulate(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents);resolver=ResourceResolver(core)
        return core,resolver,diffuse(core,resolver,'Fixture.utx',dict(id=1))

    def test_gpu_layers_and_manual_frame_are_never_exact_composition(self):
        documents=fixture();original=copy.deepcopy(documents)
        core,resolver,surface=self.surface(documents)
        self.assertEqual(surface['fragment_operation'],7)
        self.assertEqual(surface['fragment_alpha'],0)
        self.assertEqual(surface['saved_frame_mode'],'alpha_modulate')
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'] or surface['uv0_exact'])
        self.assertEqual([(s['width'],s['height']) for s in surface['fragment_layers']],
                         [(2,1),(1,1),(2,1)])
        self.assertEqual(selectable_samplers(surface),[1])
        self.assertTrue(any('Material2.rgb × Material1.alpha' in note
                            and 'mFactor не воспроизводятся' in note
                            and 'итоговый материал не подтверждён' in note
                            for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        selected=select_material_frame(core,resolver,surface,1,1)
        self.assertEqual(selected['fragment_layers'][1]['pixels'],bytes.fromhex('c08040ff'))
        self.assertEqual(selected['fragment_layers'][0]['pixels'],surface['fragment_layers'][0]['pixels'])
        with self.assertRaises(ValueError):shared_grid([selected])
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)},
                                      frame_selection=(0,1,1))
        self.assertNotIn('error',geometry)
        self.assertEqual(geometry['fragment_uv'][0],([(.25,.5)]*3,)*3)
        self.assertEqual(timed_fragment_uv(geometry,1.),geometry['fragment_uv'])
        self.assertNotIn('uv_base',geometry)
        self.assertEqual(documents,original)

    def test_first_sampler_frame_keeps_mask_and_second_sampler_consistent(self):
        documents=fixture()
        documents[2][2]['tags'].append(dict(name='AnimNext',
            value=dict(id=5,path='NextMask',**{'class':'Texture'})))
        documents[5]=('Texture','NextMask',dict(tags=[dict(name='Format',value=5)],
            mips=[dict(width=2,height=1,data_hex='1122334455667788')]))
        core,resolver,surface=self.surface(documents)
        self.assertEqual(selectable_samplers(surface),[0,1])
        selected=select_material_frame(core,resolver,surface,0,1)
        first,second,mask=selected['fragment_layers']
        self.assertEqual(first['pixels'],bytes.fromhex('3322114477665588'))
        self.assertEqual(mask['pixels'],first['pixels'])
        self.assertEqual(selected['pixels'],first['pixels'])
        self.assertEqual(second['pixels'],surface['fragment_layers'][1]['pixels'])
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([selected])

    def test_approximate_fragment_cannot_enter_nested_composition(self):
        documents=fixture()
        ref=lambda identifier,path,kind:dict(id=identifier,path=path,**{'class':kind})
        documents[5]=('Combiner','Outer',dict(tags=[
            dict(name='CombineOperation',value=2),dict(name='AlphaOperation',value=1),
            dict(name='Material1',value=ref(1,'Blend','Combiner')),
            dict(name='Material2',value=ref(2,'MaskTexture','Texture'))]))
        documents[6]=('Shader','Wrapper',dict(tags=[
            dict(name='Diffuse',value=ref(1,'Blend','Combiner'))]))
        documents[7]=('TexScaler','Scale',dict(tags=[
            dict(name='Material',value=ref(6,'Wrapper','Shader'))]))
        core=FixtureCore(documents);resolver=ResourceResolver(core)
        with self.assertRaisesRegex(ValueError,'supported matching UV|verified direct-texture'):
            diffuse(core,resolver,'Fixture.utx',dict(id=5))
        with self.assertRaisesRegex(ValueError,'cannot transform an approximate fragment'):
            diffuse(core,resolver,'Fixture.utx',dict(id=7))

    def test_rejects_unknown_shaders_bindings_and_state(self):
        changes=('operation','alpha','bool_operation','bool_alpha','modulate2','modulate4','invert','diffuse_alpha',
                 'flag_type','first_path','second_path','first_class','second_class','same_inputs',
                 'mask_missing','mask_second','mask_path','mask_class','sampler_order','sampler_suffix',
                 'shader_factor','shader_terminal','shader_extra','duplicate_operation',
                 'duplicate_mask','cycle','truncated')
        for change in changes:
            documents=fixture();doc=documents[1][2];tags=doc['tags']
            if change=='operation':tags[0]['value']=6
            elif change=='alpha':tags.append(dict(name='AlphaOperation',value=1))
            elif change=='bool_operation':tags[0]['value']=True
            elif change=='bool_alpha':tags.append(dict(name='AlphaOperation',value=False))
            elif change=='modulate2':tags.append(dict(name='Modulate2X',value=True))
            elif change=='modulate4':tags.append(dict(name='Modulate4X',value=True))
            elif change=='invert':tags.append(dict(name='InvertMask',value=True))
            elif change=='diffuse_alpha':tags.append(dict(name='UseDiffuseAlpha',value=True))
            elif change=='flag_type':tags.append(dict(name='Modulate4X',value=0))
            elif change=='first_path':tags[1]['value']['path']='Wrong'
            elif change=='second_path':tags[2]['value']['path']='Wrong'
            elif change=='first_class':documents[2]=('Cubemap','MaskTexture',documents[2][2])
            elif change=='second_class':tags[2]['value']['class']='Shader'
            elif change=='same_inputs':tags[2]['value']=copy.deepcopy(tags[1]['value'])
            elif change=='mask_missing':tags.pop(3)
            elif change=='mask_second':tags[3]['value']=copy.deepcopy(tags[2]['value'])
            elif change=='mask_path':tags[3]['value']['path']='Wrong'
            elif change=='mask_class':tags[3]['value']['class']='TexPanner'
            elif change=='sampler_order':doc['strings'].reverse()
            elif change=='sampler_suffix':doc['strings'][0]['values']=['Fixture.Other']
            elif change=='shader_factor':doc['shader']=doc['shader'].replace('*mFactor','',1)
            elif change=='shader_terminal':doc['shader']=doc['shader'].split('c1=diffuse;',1)[0]
            elif change=='shader_extra':doc['shader']+='tex2D(s[0],tex0);'
            elif change=='duplicate_operation':tags.append(copy.deepcopy(tags[0]))
            elif change=='duplicate_mask':tags.append(copy.deepcopy(tags[3]))
            elif change=='cycle':tags[1]['value']=dict(id=1,path='Blend',**{'class':'Texture'})
            else:documents[3][2]['mips'][0]['data_hex']='00'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                self.surface(documents)


if __name__=='__main__':unittest.main()
