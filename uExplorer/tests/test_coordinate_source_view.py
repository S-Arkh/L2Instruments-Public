"""Explicit coordinate sources, topology and safe material-composition gates."""
import copy
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_math import opacity_surface,shared_grid
from material_surface import diffuse
from material_uv import timed_uv
from textured_mesh import prepare_textured


def bits(*values):
    return list(struct.unpack('<'+'I'*len(values),struct.pack('<'+'f'*len(values),*values)))


def doc(**values):
    return dict(tags=[dict(name=name,value=value) for name,value in values.items()])


def shader(channel):
    return (f'float4 texcolor0=tex2D(s[0],mul(m0,float3(tex{channel}.xy,1.f)));'
            'c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
            'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')


def direct_shader(channel):
    return (f'float4 texcolor0=tex2D(s[0],tex{channel});'
            'c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
            'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')


def fixture():
    return {
        1:('TexCoordSource',dict(doc(SourceChannel=1,TexCoordSource=1,
                                    Material=dict(id=2,path='Image',**{'class':'Texture'})),
                                 strings=[dict(name='Fixture.Image',values=[])],shader=shader(1))),
        2:('Texture',dict(doc(Format=5),mips=[
            dict(width=2,height=1,data_hex='0000ffff00ff00ff')])),
        3:('TexCoordSource',dict(doc(SourceChannel=0,
                                    Material=dict(id=2,path='Image',**{'class':'Texture'})),
                                 strings=[dict(name='Fixture.Image',values=[])],shader=shader(0))),
        4:('TexEnvMap',doc(Material=dict(id=1,path='Coord',**{'class':'TexCoordSource'}))),
        5:('TexScaler',doc(Material=dict(id=1,path='Coord',**{'class':'TexCoordSource'}))),
        7:('VertexColor',dict(doc(),strings=[],shader='')),
    }


class Resolver:
    dependencies=[]
    def __init__(self,documents):self.documents=documents
    def resolve(self,path,reference):return path,reference['id']
    def read(self,path,identifier,budget=None):
        kind,document=self.documents[identifier]
        return dict(path=str(identifier),**{'class':kind}),document


def mesh():
    return dict(vertices=[dict(position_bits=bits(*p)) for p in
                          [(0,0,0),(1,0,0),(0,1,0)]],
                indices=[0,1,2,0,1,2],
                sections=[dict(first_index=0,face_count=1),
                          dict(first_index=3,face_count=1)],
                uv_streams=[dict(coordinate_bits=[bits(.25,.5)]*3,coordinate_index=0),
                            dict(coordinate_bits=[bits(.75,.5)]*3,coordinate_index=1)])


class CoordinateSource(unittest.TestCase):
    def test_direct_source_and_composition(self):
        resolver=Resolver(fixture())
        first=diffuse(None,resolver,'fixture',dict(id=1))
        second=diffuse(None,resolver,'fixture',dict(id=3))
        self.assertEqual(first['uv_channel'],1)
        self.assertFalse(first['uv0_exact'])
        self.assertTrue(first['uv_coordinate_exact'])
        self.assertEqual(shared_grid([first,first])['uv_channel'],1)
        mixed=opacity_surface(first,first)
        self.assertEqual(mixed['uv_channel'],1)
        self.assertTrue(mixed['uv_coordinate_exact'])
        self.assertEqual(second['uv_channel'],0)
        with self.assertRaisesRegex(ValueError,'channels'):
            shared_grid([first,second])
        with self.assertRaisesRegex(ValueError,'channels'):
            opacity_surface(first,second)
        with self.assertRaisesRegex(ValueError,'Invalid material UV channel'):
            shared_grid([first,dict(first,uv_channel=True)])
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([dict(second,uv0_exact=False,uv_coordinate_exact=True)])
        fallback=diffuse(None,resolver,'fixture',dict(id=4))
        self.assertFalse(fallback['uv_coordinate_exact'])
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([fallback,first])
        with self.assertRaisesRegex(ValueError,'sampler|shader'):
            diffuse(None,resolver,'fixture',dict(id=5))

    def test_rejects_ambiguous_source_or_non_direct_texture(self):
        for change in ('missing','source','negative','too_high','bool',
                        'projected','dimensions','nested','shader','sampler','modifier'):
            documents=fixture()
            tags=documents[1][1]['tags']
            if change=='missing':tags.pop(0)
            elif change=='source':tags[1]['value']=0
            elif change=='negative':tags[0]['value']=-1
            elif change=='too_high':tags[0]['value']=8
            elif change=='bool':tags[0]['value']=True
            elif change=='projected':tags.append(dict(name='TexCoordProjected',value=True))
            elif change=='dimensions':tags.append(dict(name='TexCoordCount',value=1))
            elif change=='nested':tags[-1]['value']['class']='Shader'
            elif change=='shader':documents[1][1]['shader']=shader(0)
            elif change=='sampler':documents[1][1]['strings'][0]['name']='Fixture.Wrong'
            else:documents[1][1]['strings'][0]['values']=['UnexpectedModifier']
            with self.subTest(change=change),self.assertRaises(ValueError):
                diffuse(None,Resolver(documents),'fixture',dict(id=1))

    def test_conflicting_uv2_shader_is_labelled_uv0_fallback_not_composable(self):
        for stored_shader in (shader(0),direct_shader(0)):
            documents=fixture()
            source=documents[1][1]
            source['tags'][0]['value']=source['tags'][1]['value']=2
            source['shader']=stored_shader
            # A correctly resolved Texture has this actual path, not just a
            # sampler string that happens to match the serialized reference.
            class NamedResolver(Resolver):
                def read(self,path,identifier,budget=None):
                    entry,document=super().read(path,identifier,budget)
                    if identifier==2:entry['path']='Image'
                    return entry,document
            with self.subTest(shader=stored_shader):
                resolver=NamedResolver(documents)
                surface=diffuse(None,resolver,'fixture',dict(id=1))
                self.assertEqual(surface['uv_channel'],0)
                self.assertTrue(surface['uv_preview_approximate'])
                self.assertFalse(surface['uv0_exact'])
                self.assertFalse(surface['uv_coordinate_exact'])
                self.assertTrue(any('свойства выбирают UV2' in note and 'shader выбирает UV0' in note
                                    for note in surface['notes']))
                with self.assertRaisesRegex(ValueError,'supported matching UV'):
                    shared_grid([surface])
                with patch('textured_mesh.ResourceResolver',return_value=resolver):
                    geometry=prepare_textured(None,'fixture',mesh(),'static_mesh',
                                              overrides={0:('fixture',1),1:('fixture',3)})
                self.assertEqual(geometry['uv'][0],[(.25,.5)]*3)
                self.assertTrue(any('свойства выбирают UV2' in note for note in geometry['warnings']))
                self.assertNotIn('uv_base',geometry)

    def test_conflicting_shader_does_not_bypass_other_gates(self):
        for change in ('other_channel','bad_shader','sampler','modifier','projected',
                       'source','wrong_texture'):
            documents=fixture();source=documents[1][1]
            source['tags'][0]['value']=source['tags'][1]['value']=2
            source['shader']=shader(0)
            if change=='other_channel':source['tags'][0]['value']=source['tags'][1]['value']=3
            elif change=='bad_shader':source['shader']=shader(1)
            elif change=='sampler':source['strings'][0]['name']='Fixture.Wrong'
            elif change=='modifier':source['strings'][0]['values']=['Wrong']
            elif change=='projected':source['tags'].append(dict(name='TexCoordProjected',value=True))
            elif change=='source':source['tags'][1]['value']=0
            class NamedResolver(Resolver):
                def read(self,path,identifier,budget=None):
                    entry,document=super().read(path,identifier,budget)
                    if identifier==2:entry['path']='Wrong' if change=='wrong_texture' else 'Image'
                    return entry,document
            with self.subTest(change=change),self.assertRaises(ValueError):
                diffuse(None,NamedResolver(documents),'fixture',dict(id=1))

    def test_direct_shader_short_sampler_and_default_stream(self):
        documents=fixture()
        documents[1][1]['tags'][-1]['value']['path']='Group.Image'
        documents[1][1]['strings'][0]['name']='Image'
        documents[1][1]['shader']=direct_shader(1)
        class InventoryResolver(Resolver):
            def inventory(self,path):
                return dict(candidates=[dict(id=2,path='Group.Image',**{'class':'Texture'})])
        result=diffuse(None,InventoryResolver(documents),'fixture',dict(id=1))
        self.assertEqual(result['uv_channel'],1)
        class Ambiguous(InventoryResolver):
            def inventory(self,path):
                result=super().inventory(path)
                result['candidates'].append(dict(id=9,path='Other.Image',**{'class':'Texture'}))
                return result
        with self.assertRaisesRegex(ValueError,'sampler'):
            diffuse(None,Ambiguous(documents),'fixture',dict(id=1))
        default=fixture()
        default[3][1]['tags'].pop(0)
        default[3][1]['shader']=direct_shader(0)
        self.assertEqual(diffuse(None,Resolver(default),'fixture',dict(id=3))['uv_channel'],0)

    def test_vertex_color_is_only_a_marked_saved_stream_diagnostic(self):
        result=diffuse(None,Resolver(fixture()),'fixture',dict(id=7))
        self.assertTrue(result['vertex_color'])
        self.assertFalse(result['uv_coordinate_exact'])
        self.assertTrue(any('игровое освещение' in note for note in result['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([result])
        documents=fixture()
        documents[7][1]['shader']='unknown'
        with self.assertRaisesRegex(ValueError,'not recognized'):
            diffuse(None,Resolver(documents),'fixture',dict(id=7))

    def test_static_mesh_uses_each_materials_selected_uv(self):
        original=mesh();untouched=copy.deepcopy(original)
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(fixture())):
            result=prepare_textured(None,'fixture',original,'static_mesh',
                                    overrides={0:('fixture',1),1:('fixture',3)})
        self.assertNotIn('error',result)
        self.assertEqual(result['uv'],[[(.75,.5)]*3,[(.25,.5)]*3])
        self.assertEqual(set(result['textures']),{0,1})
        self.assertEqual(original,untouched)

    def test_explicit_additional_static_streams(self):
        for channel in (2,7):
            documents=fixture()
            documents[1][1]['tags'][0]['value']=channel
            documents[1][1]['tags'][1]['value']=channel
            documents[1][1]['shader']=shader(channel)
            geometry=mesh()
            while len(geometry['uv_streams'])<=channel:
                index=len(geometry['uv_streams'])
                geometry['uv_streams'].append(dict(coordinate_index=index,
                    coordinate_bits=[bits(index/8,.5)]*3))
            with self.subTest(channel=channel),patch('textured_mesh.ResourceResolver',
                                                     return_value=Resolver(documents)):
                result=prepare_textured(None,'fixture',geometry,'static_mesh',
                                        overrides={0:('fixture',1),1:('fixture',3)})
            self.assertEqual(result['uv'][0],[(channel/8,.5)]*3)
            self.assertEqual(result['uv'][1],[(.25,.5)]*3)

    def test_missing_incomplete_or_misidentified_stream_drops_only_affected_slot(self):
        for change in ('missing','short','wrong_index','nan','too_large'):
            original=mesh()
            if change=='missing':original['uv_streams'].pop()
            elif change=='short':original['uv_streams'][1]['coordinate_bits'].pop()
            elif change=='wrong_index':original['uv_streams'][1]['coordinate_index']=0
            elif change=='nan':original['uv_streams'][1]['coordinate_bits'][0]=bits(float('nan'),.5)
            else:original['uv_streams'][1]['coordinate_bits'][0]=bits(1e7,.5)
            with self.subTest(change=change),patch('textured_mesh.ResourceResolver',
                                                    return_value=Resolver(fixture())):
                result=prepare_textured(None,'fixture',original,'static_mesh',
                                        overrides={0:('fixture',1),1:('fixture',3)})
            self.assertNotIn('error',result)
            self.assertEqual(set(result['textures']),{1})
            self.assertTrue(any('Материал 0:' in warning and ('UV1' in warning or 'Non-finite' in warning)
                                for warning in result['warnings']))
            self.assertFalse(any('TexCoordSource: UV1' in warning for warning in result['warnings']))

    def test_damaged_uv0_does_not_disable_valid_uv1(self):
        for change in ('missing','short','wrong_index','nan','too_large'):
            original=mesh()
            stream=original['uv_streams'][0]
            if change=='missing':original['uv_streams'][0]={}
            elif change=='short':stream['coordinate_bits'].pop()
            elif change=='wrong_index':stream['coordinate_index']=1
            elif change=='nan':stream['coordinate_bits'][0]=bits(float('nan'),.5)
            else:stream['coordinate_bits'][0]=bits(1e7,.5)
            with self.subTest(change=change),patch('textured_mesh.ResourceResolver',
                                                    return_value=Resolver(fixture())):
                result=prepare_textured(None,'fixture',original,'static_mesh',
                                        overrides={0:('fixture',1),1:('fixture',3)})
            self.assertNotIn('error',result)
            self.assertEqual(set(result['textures']),{0})
            self.assertEqual(result['uv'][0],[(.75,.5)]*3)
            self.assertEqual(result['uv'][1],[(0.,0.)]*3)
            self.assertTrue(any('Материал 1:' in warning for warning in result['warnings']))

    def test_no_static_uv_streams_preserves_neutral_geometry(self):
        original=mesh();original['uv_streams']=[]
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(fixture())):
            result=prepare_textured(None,'fixture',original,'static_mesh',
                                    overrides={0:('fixture',1),1:('fixture',3)})
        self.assertNotIn('error',result)
        self.assertEqual(result['textures'],{})
        self.assertEqual(result['uv'],[[(0.,0.)]*3]*2)
        self.assertTrue(any('Материал 0:' in warning and 'UV1' in warning for warning in result['warnings']))
        self.assertTrue(any('Материал 1:' in warning and 'UV0' in warning for warning in result['warnings']))

    def test_skeletal_mesh_does_not_invent_a_second_stream(self):
        body=dict(points_bits=[bits(0,0,0),bits(1,0,0),bits(0,1,0)],
                  mesh_wedges=[dict(vertex=i,uv_bits=bits(.25,.5)) for i in range(3)],
                  triangles=[dict(wedges=[0,1,2],material=0)],
                  textures=[],materials=[[0,0]])
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(fixture())):
            result=prepare_textured(None,'fixture',body,'skeletal_mesh',overrides={0:('fixture',1)})
        self.assertNotIn('error',result)
        self.assertEqual(result['textures'],{})
        self.assertTrue(any('только UV0' in warning for warning in result['warnings']))

    def test_saved_nested_source_and_panner_chain(self):
        for outer in ('source','panner'):
            documents=fixture()
            source=documents[1][1]
            source['path']='Coord'
            panner=dict(path='Pan',tags=[
                dict(name='PanRate',bits=bits(.5)[0]),
                dict(name='Material',value=dict(id=2,path='Image',**{'class':'Texture'}))])
            documents[6]=('TexPanner',panner)
            if outer=='source':
                source['tags'][-1]['value']=dict(id=6,path='Pan',**{'class':'TexPanner'})
                ordered=(source,panner);names=('Coord','Pan');identifier=1
            else:
                panner['tags'][-1]['value']=dict(id=1,path='Coord',**{'class':'TexCoordSource'})
                ordered=(panner,source);names=('Pan','Coord');identifier=6
            for index,document in enumerate(ordered):
                document['strings']=[dict(name='Fixture.Image',
                                         values=['Fixture.'+name for name in names[index:] if name!='Coord'])]
                document['shader']=shader(1 if index<=ordered.index(source) else 0)
            with self.subTest(outer=outer):
                surface=diffuse(None,Resolver(documents),'fixture',dict(id=identifier))
                self.assertEqual(surface['uv_channel'],1)
                self.assertTrue(surface['uv_coordinate_exact'])
                self.assertEqual([kind for kind,_ in surface['uv_chain']],['panner'])
                with patch('textured_mesh.ResourceResolver',return_value=Resolver(documents)):
                    result=prepare_textured(None,'fixture',mesh(),'static_mesh',
                                            overrides={0:('fixture',identifier),1:('fixture',3)})
                self.assertEqual(result['uv'][0],[(.75,.5)]*3)
                self.assertEqual(timed_uv(result,1.)[0],[(1.25,.5)]*3)
                self.assertEqual(timed_uv(result,0.)[0],[(.75,.5)]*3)
                panner['tags'].append(dict(name='TexCoordSource',value=0))
                with self.assertRaisesRegex(ValueError,'NoChange'):
                    diffuse(None,Resolver(documents),'fixture',dict(id=identifier))
                panner['tags'].pop()
                panner_channel=1 if ordered.index(panner)<=ordered.index(source) else 0
                panner['shader']=direct_shader(panner_channel)
                with self.assertRaisesRegex(ValueError,'shader'):
                    diffuse(None,Resolver(documents),'fixture',dict(id=identifier))
                panner['shader']=shader(1-panner_channel)
                with self.assertRaisesRegex(ValueError,'shader'):
                    diffuse(None,Resolver(documents),'fixture',dict(id=identifier))
                panner['shader']=shader(panner_channel)
                ordered[0]['strings'][0]['values'][0]='Fixture.Wrong'
                with self.assertRaisesRegex(ValueError,'order'):
                    diffuse(None,Resolver(documents),'fixture',dict(id=identifier))

    def test_approximate_repeat_keeps_uv1_but_cannot_compose(self):
        documents=fixture()
        source=documents[1][1]
        source['path']='Coord'
        source['tags'][-1]['value']=dict(id=6,path='Osc',**{'class':'TexOscillator'})
        source['strings']=[dict(name='Fixture.Image',values=['Fixture.Osc'])]
        source['shader']=shader(1)
        osc=dict(path='Osc',tags=[
            dict(name='Material',value=dict(id=2,path='Image',**{'class':'Texture'})),
            dict(name='UOscillationType',value=2),
            dict(name='UOscillationAmplitude',bits=bits(.5)[0])],
            strings=[dict(name='Fixture.Image',values=['Fixture.Osc'])],shader=shader(0))
        documents[6]=('TexOscillator',osc)
        surface=diffuse(None,Resolver(documents),'fixture',dict(id=1))
        self.assertEqual(surface['uv_channel'],1)
        self.assertEqual(surface['uv_chain'][0][0],'oscillator_preview')
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'])
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([surface])
        with patch('textured_mesh.ResourceResolver',return_value=Resolver(documents)):
            result=prepare_textured(None,'fixture',mesh(),'static_mesh',
                                    overrides={0:('fixture',1),1:('fixture',3)})
        self.assertEqual(result['uv'][0],[(.75,.5)]*3)
        self.assertNotEqual(timed_uv(result,.5)[0],result['uv'][0])
        self.assertEqual(timed_uv(result,0.)[0],result['uv'][0])


if __name__=='__main__':unittest.main()
