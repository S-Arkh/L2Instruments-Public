"""Opt-in real GPU checks: run with Windows Python, optionally passing a bundle root."""
import json
from pathlib import Path
import sys
import struct
application_python=(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1])/'python'
application_python=application_python.resolve()
sys.path.insert(0,str(application_python))
# Isolated bundled Python omits the script directory; expose only test fixtures.
sys.path.append(str(Path(__file__).resolve().parent))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from mesh_view import MeshCanvas
from material_state import state_for
from material_math import combine
from portable_smoke import masked_add_fixture,masked_add_alpha_fixture
from textured_mesh import prepare_textured
from animation_view import AnimationView
from material_uv import panner_direction
from material_fragment import fragment_surface
from material_rotation import animated_rotation
from material_rotation3d import spatial_animation
from material_oscillation import verified_oscillator_parameters
# Load fixture dependencies from the selected application before importing test
# modules, some of which prepend their source tree to sys.path.
import material_chain
import material_snapshot
import material_frames
application_path=list(sys.path)
from test_rotation_view import fixture as rotation_fixture,stationary_fixture
from test_spatial_rotation_view import double_spatial_fixture
from test_lerp_view import fixture as lerp_fixture
from test_multisample_view import FixtureCore as MultiSampleCore,multiple_channels
from test_combiner_snapshot_view import FixtureCore as CombinerSnapshotCore
from test_vertex_color_view import FixtureCore as VertexColorCore
from test_shader_modifier_view import (FixtureCore as ShaderModifierCore,
                                       fixture as shader_modifier_fixture,multipass_fixture,
                                       shader_panner_snapshot_fixture)
from test_isolated_sampler_view import (fixture as isolated_sampler_fixture,
                                        direct_combiner_fixture)
from test_panner_combiner_view import fixture as panner_combiner_fixture
from test_saved_material_frames import animated_combiner_fixture
from test_alpha_modulate_view import fixture as alpha_modulate_fixture
from test_rotator_nested_isolated_view import fixture as rotator_nested_fixture
from test_material_snapshot_view import matrix_tag
sys.path[:]=application_path


def verify_application_imports():
    """Reject accidental source-tree imports during a packaged GPU check."""
    for file in application_python.glob('*.py'):
        module=sys.modules.get(file.stem)
        if module is not None:
            origin=getattr(module,'__file__',None)
            if origin is None or Path(origin).resolve().parent!=application_python:
                raise RuntimeError(f'Application module {file.stem} loaded outside selected root: {origin}')


verify_application_imports()


def main():
    application=QApplication([]);canvas=MeshCanvas();canvas.resize(400,400);canvas.show()
    background=(24,33,41);source=(80,120,160);alpha=128/255
    def state(mode=0,**values):
        values['FrameBufferBlending']=mode
        return state_for('FinalBlend',dict(tags=[dict(name=k,value=v) for k,v in values.items()]))
    def surface(color,settings,wrap=(0,0),width=1):
        return dict(width=width,height=1,pixels=bytes(color),render_state=settings,wrap=wrap)
    def geometry(textures,depths=(0,),reverse=False,uv=(0,0)):
        points=[];polygons=[]
        for depth in depths:
            start=len(points);points.extend([(-1,depth,-1),(1,depth,-1),(0,depth,1)])
            face=[start,start+1,start+2];polygons.append(face[::-1] if reverse else face)
        return dict(points=points,polygons=polygons,edges=[],uv=[[uv]*3 for _ in polygons],
                    face_materials=list(range(len(polygons))),textures=textures)
    def draw(g):
        canvas.display(g);canvas.yaw=canvas.pitch=0;canvas.style=2;canvas.update();QTest.qWait(40)
        assert canvas.gpu and canvas.gpu.isValid(),'A real OpenGL context is required'
        return canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3]
    def equal(actual,expected):
        assert max(abs(a-b) for a,b in zip(actual,expected))<=2,(actual,expected)
    equations={
        0:lambda s,d:s,1:lambda s,d:2*s*d/255,2:lambda s,d:s*alpha+d*(1-alpha),
        4:lambda s,d:s+d*(1-s/255),5:lambda s,d:d*(1-s/255),
        6:lambda s,d:s*alpha+d,7:lambda s,d:d}
    try:
        rows=[]
        for mode,equation in equations.items():
            actual=draw(geometry({0:surface((*source,128),state(mode))}))
            expected=[round(equation(s,d)) for s,d in zip(source,background)]
            equal(actual,expected);rows.append(dict(mode=mode,actual=actual,expected=expected))
        for threshold,expected in ((128,background),(127,source)):
            equal(draw(geometry({0:surface((*source,128),state(AlphaTest=True,AlphaRef=threshold))})),expected)
        equal(draw(geometry({0:surface((*source,128),state())},reverse=True)),background)
        equal(draw(geometry({0:surface((*source,128),state(TwoSided=True))},reverse=True)),source)
        # Same-depth faces: with ZWrite disabled the second fragment must pass.
        for write in (True,False):
            actual=draw(geometry({0:surface((255,0,0,128),state(2,ZWrite=write)),
                                  1:surface((0,255,0,255),state(2))},depths=(0,0)))
            expected=[255*alpha+background[0]*(1-alpha),background[1]*(1-alpha),background[2]*(1-alpha)] if write else (0,255,0)
            equal(actual,expected)
        # The opaque near face is drawn before the blended far face.
        for test in (True,False):
            actual=draw(geometry({0:surface((0,0,255,255),state()),
                                  1:surface((255,0,0,255),state(2,ZTest=test))},depths=(1,0)))
            equal(actual,(0,0,255) if test else (255,0,0))
        pixels=(255,0,0,255,0,255,0,255)
        equal(draw(geometry({0:surface(pixels,state(),(0,0),2)},uv=(1.25,.5))),(255,0,0))
        equal(draw(geometry({0:surface(pixels,state(),(1,0),2)},uv=(1.25,.5))),(0,255,0))
        combined=combine(dict(tags=[dict(name='CombineOperation',value=2),
            dict(name='AlphaOperation',value=1),dict(name='Modulate4X',value=True)]),
            {'Material1':dict(width=1,height=1,pixels=bytes([64,128,255,64])),
             'Material2':dict(width=1,height=1,pixels=bytes([128,64,128,128]))})
        combined['render_state']=state()
        equal(draw(geometry({0:combined})),(129,129,255))
        def bits(*v):return list(struct.unpack('<'+'I'*len(v),struct.pack('<'+'f'*len(v),*v)))
        def coord_shader(channel):
            return (f'float4 texcolor0=tex2D(s[0],mul(m0,float3(tex{channel}.xy,1.f)));'
                    'c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
                    'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')
        def direct_coord_shader(channel):
            return (f'float4 texcolor0=tex2D(s[0],tex{channel});'
                    'c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
                    'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')
        class Core:
            def __init__(self,offset=0):self.offset=offset
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[dict(id=1,path='Scaler',**{'class':'TexScaler'}),
                                                      dict(id=2,path='Image',**{'class':'Texture'})])}
                if kw['object_id']==1:
                    return {'result':dict(tags=[dict(name='Material',value=dict(id=2,**{'class':'Texture'})),
                                               dict(name='UScale',bits=bits(.5)[0]),
                                               dict(name='UOffset',bits=bits(self.offset)[0])])}
                return {'result':dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])}
        mesh=dict(vertices=[dict(position_bits=bits(*p)) for p in [(-1,0,-1),(1,0,-1),(0,0,1)]],
            indices=[0,1,2],sections=[dict(first_index=0,face_count=1)],
            uv_streams=[dict(coordinate_bits=[bits(.125,.5)]*3)])
        prepared=prepare_textured(Core(),'synthetic.utx',mesh,'static_mesh',overrides={0:('synthetic.utx',1)})
        assert 'error' not in prepared and prepared['textures'],prepared
        equal(draw(prepared),(255,0,0))
        class SnapshotCore(Core):
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Pan',**{'class':'TexPannerTriggered'}),
                        dict(id=2,path='Image',**{'class':'Texture'})])}
                if kw['object_id']==1:
                    rows=((1.,0.,0.,0.),(0.,1.,0.,0.),(.5,0.,1.,0.),(0.,0.,0.,1.))
                    matrix=dict(name='M',members=[dict(name=plane,members=[
                        dict(name=axis,bits=bits(value)[0])
                        for axis,value in zip(('X','Y','Z','W'),row)])
                        for plane,row in zip(('XPlane','YPlane','ZPlane','WPlane'),rows)])
                    return {'result':dict(tags=[matrix,dict(name='Material',value=dict(
                        id=2,path='Image',**{'class':'Texture'}))],
                        strings=[dict(name='Fixture.Image',values=['Fixture.Pan'])],
                        shader=coord_shader(0))}
                return super().request(**kw)
        snapshot_mesh=dict(mesh,uv_streams=[dict(coordinate_bits=[bits(.25,.5)]*3)])
        snapshot=prepare_textured(SnapshotCore(),'synthetic.utx',snapshot_mesh,'static_mesh',
                                  overrides={0:('synthetic.utx',1)})
        assert snapshot['textures'][0]['uv_snapshot']
        assert not snapshot['textures'][0]['uv_coordinate_exact']
        assert any('сохранённая UV-матрица' in note for note in snapshot['warnings'])
        equal(draw(snapshot),(0,255,0))
        class SnapshotChainCore(Core):
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Pan',**{'class':'TexPannerTriggered'}),
                        dict(id=2,path='Image',**{'class':'Texture'}),
                        dict(id=3,path='Rot',**{'class':'TexRotator'})])}
                if kw['object_id'] in (1,3):
                    first=kw['object_id']==1
                    rows=(((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,.5,1.,0.),(0.,0.,0.,1.))
                          if first else
                          ((0.,1.,0.,0.),(-1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)))
                    matrix=dict(name='M',members=[dict(name=plane,members=[
                        dict(name=axis,bits=bits(value)[0])
                        for axis,value in zip(('X','Y','Z','W'),row)])
                        for plane,row in zip(('XPlane','YPlane','ZPlane','WPlane'),rows)])
                    ref=(dict(id=3,path='Rot',**{'class':'TexRotator'}) if first else
                         dict(id=2,path='Image',**{'class':'Texture'}))
                    return {'result':dict(path='Pan' if first else 'Rot',
                        tags=[matrix,dict(name='Material',value=ref)],
                        strings=[dict(name='Fixture.Image',
                                      values=['Fixture.Pan','Fixture.Rot'] if first else ['Fixture.Rot'])],
                        shader=coord_shader(0))}
                return super().request(**kw)
        chain_mesh=dict(mesh,uv_streams=[dict(coordinate_bits=[bits(.25,.25)]*3)])
        chain_snapshot=prepare_textured(SnapshotChainCore(),'synthetic.utx',chain_mesh,'static_mesh',
                                        overrides={0:('synthetic.utx',1)})
        assert chain_snapshot['textures'][0]['uv_snapshot']
        assert not chain_snapshot['textures'][0]['uv_coordinate_exact']
        assert chain_snapshot['uv'][0]==[(-.75,.25)]*3
        assert 'uv_base' not in chain_snapshot
        assert any('только статический снимок' in note for note in chain_snapshot['warnings'])
        equal(draw(chain_snapshot),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        class RollPreviewCore(Core):
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Pan',**{'class':'TexPanner'}),
                        dict(id=2,path='Image',**{'class':'Texture'})])}
                if kw['object_id']==1:
                    return {'result':dict(tags=[
                        dict(name='Material',value=dict(id=2,path='Image',**{'class':'Texture'})),
                        dict(name='PanRate',bits=bits(.5)[0]),
                        dict(name='PanDirection',words=[0,0,4])])}
                return super().request(**kw)
        preview=prepare_textured(RollPreviewCore(),'synthetic.utx',snapshot_mesh,'static_mesh',
                                 overrides={0:('synthetic.utx',1)})
        assert preview['textures'][0]['uv_preview_approximate']
        assert not preview['textures'][0]['uv_coordinate_exact']
        equal(draw(preview),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        class CoordinateCore(Core):
            def __init__(self,channel,direct=False):self.channel=channel;self.direct=direct
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Coord',**{'class':'TexCoordSource'}),
                        dict(id=2,path='Image',**{'class':'Texture'})])}
                if kw['object_id']==1:
                    return {'result':dict(tags=[
                        dict(name='SourceChannel',value=self.channel),
                        dict(name='TexCoordSource',value=self.channel),
                        dict(name='Material',value=dict(id=2,path='Image',**{'class':'Texture'}))],
                        strings=[dict(name='Image',values=[])],
                        shader=(direct_coord_shader if self.direct else coord_shader)(self.channel))}
                return super().request(**kw)
        coordinate_mesh=dict(mesh,uv_streams=[
            dict(coordinate_index=0,coordinate_bits=[bits(.25,.5)]*3),
            dict(coordinate_index=1,coordinate_bits=[bits(.75,.5)]*3)])
        for channel,expected in ((0,(255,0,0)),(1,(0,255,0))):
            for direct in (False,True):
                selected=prepare_textured(CoordinateCore(channel,direct),'synthetic.utx',coordinate_mesh,
                                          'static_mesh',overrides={0:('synthetic.utx',1)})
                assert selected['textures'][0]['uv_channel']==channel,selected
                equal(draw(selected),expected)
        class ConflictingCoordinateCore(CoordinateCore):
            def __init__(self,direct):super().__init__(2,direct)
            def request(self,**kw):
                result=super().request(**kw)
                if kw.get('object_id')==1:
                    result['result']['shader']=(direct_coord_shader if self.direct else coord_shader)(0)
                return result
        conflicting_mesh=dict(coordinate_mesh,uv_streams=coordinate_mesh['uv_streams']+[
            dict(coordinate_index=2,coordinate_bits=[bits(.75,.5)]*3)])
        for direct in (False,True):
            selected=prepare_textured(ConflictingCoordinateCore(direct),'synthetic.utx',conflicting_mesh,
                                      'static_mesh',overrides={0:('synthetic.utx',1)})
            assert selected['textures'][0]['uv_preview_approximate']
            assert not selected['textures'][0]['uv_coordinate_exact']
            assert selected['uv'][0]==[(.25,.5)]*3
            assert any('свойства выбирают UV2' in note and 'shader выбирает UV0' in note
                       for note in selected['warnings'])
            equal(draw(selected),(255,0,0))
        no_uv0=dict(conflicting_mesh,uv_streams=[{},*conflicting_mesh['uv_streams'][1:]])
        selected=prepare_textured(ConflictingCoordinateCore(False),'synthetic.utx',no_uv0,
                                  'static_mesh',overrides={0:('synthetic.utx',1)})
        assert not selected['textures'] and any('UV0' in warning for warning in selected['warnings'])
        multi_mesh=dict(mesh,uv_streams=[dict(coordinate_bits=[bits(.25,.5)]*3)])
        independent=prepare_textured(MultiSampleCore(),'Fixture.utx',multi_mesh,'static_mesh',
                                     overrides={0:('Fixture.utx',1)})
        assert independent['textures'][0]['fragment_independent_uv']
        assert independent['fragment_uv'][0][0]==independent['fragment_uv'][0][1]
        equal(draw(independent),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        assert canvas.geometry['fragment_uv'][0][0]==[(.25,.5)]*3
        assert canvas.geometry['fragment_uv'][0][1]==[(.75,.5)]*3
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        mixed_mesh=dict(mesh,uv_streams=[
            dict(coordinate_index=0,coordinate_bits=[bits(.25,.5)]*3),
            dict(coordinate_index=1,coordinate_bits=[bits(.75,.5)]*3)])
        mixed_channels=prepare_textured(MultiSampleCore(multiple_channels()),'Fixture.utx',
                                       mixed_mesh,'static_mesh',overrides={0:('Fixture.utx',1)})
        assert mixed_channels['fragment_uv'][0][0]==[(.25,.5)]*3
        assert mixed_channels['fragment_uv'][0][1]==[(.75,.5)]*3
        equal(draw(mixed_channels),(0,255,0))
        canvas.material_time(1.);QTest.qWait(40)
        assert canvas.geometry['fragment_uv'][0][1]==[(1.25,.5)]*3
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        combiner_snapshot=prepare_textured(CombinerSnapshotCore(),'Fixture.utx',multi_mesh,'static_mesh',
                                           overrides={0:('Fixture.utx',1)})
        assert combiner_snapshot['textures'][0]['uv_snapshot']
        assert not combiner_snapshot['textures'][0]['uv_coordinate_exact']
        assert combiner_snapshot['uv'][0]==[(-.25,.75)]*3 and 'uv_base' not in combiner_snapshot
        equal(draw(combiner_snapshot),(0,255,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        for word,expected in ((0xff0000ff,(255,0,0)),(0xff00ff00,(0,255,0)),
                              (0xffff0000,(0,0,255))):
            color_mesh=dict(mesh,uv_streams=[],colors=[word]*3)
            vertex_color=prepare_textured(VertexColorCore(),'Fixture.utx',color_mesh,'static_mesh',
                                          overrides={0:('Fixture.utx',1)})
            assert vertex_color['textures'][0]['vertex_color']
            assert not vertex_color['textures'][0]['uv_coordinate_exact']
            assert any('игровое освещение' in note for note in vertex_color['warnings'])
            equal(draw(vertex_color),expected)
        shader_modifier=prepare_textured(ShaderModifierCore(),'Fixture.utx',multi_mesh,'static_mesh',
                                         overrides={0:('Fixture.utx',1)})
        assert shader_modifier['textures'][0]['uv_preview_approximate']
        assert not shader_modifier['textures'][0]['uv_coordinate_exact']
        assert any('только diffuse' in note for note in shader_modifier['warnings'])
        equal(draw(shader_modifier),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        multipass=prepare_textured(ShaderModifierCore(multipass_fixture()),'Fixture.utx',multi_mesh,
                                   'static_mesh',overrides={0:('Fixture.utx',1)})
        assert multipass['textures'][0]['uv_preview_approximate']
        assert any('другие проходы и их sampler не вычисляются' in note
                   and 'состояния проходов не подтверждены' in note for note in multipass['warnings'])
        equal(draw(multipass),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        shader_snapshot_docs=shader_modifier_fixture('TexOscillator')
        shader_snapshot_docs[1][2]['tags'].extend([
            dict(name='UOffset',bits=bits(1.)[0]),
            matrix_tag(((1.,0.,0.,0.),(0.,1.,0.,0.),(.5,0.,1.,0.),(0.,0.,0.,1.)))])
        shader_snapshot=prepare_textured(ShaderModifierCore(shader_snapshot_docs),'Fixture.utx',
                                         multi_mesh,'static_mesh',overrides={0:('Fixture.utx',1)})
        assert shader_snapshot['textures'][0]['uv_snapshot'] and 'uv_base' not in shader_snapshot
        assert any('случайное состояние' in note for note in shader_snapshot['warnings'])
        equal(draw(shader_snapshot),(0,255,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        chain_snapshot=prepare_textured(ShaderModifierCore(shader_panner_snapshot_fixture()),
                                        'Fixture.utx',multi_mesh,'static_mesh',
                                        overrides={0:('Fixture.utx',1)})
        assert chain_snapshot['textures'][0]['uv_snapshot'] and 'uv_base' not in chain_snapshot
        assert chain_snapshot['uv'][0]==[(.25,.75)]*3
        assert any('могут относиться к разным моментам' in note for note in chain_snapshot['warnings'])
        equal(draw(chain_snapshot),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        isolated=prepare_textured(ShaderModifierCore(isolated_sampler_fixture()),'Fixture.utx',multi_mesh,
                                  'static_mesh',overrides={0:('Fixture.utx',1)})
        assert isolated['textures'][0]['isolated_sampler']==0 and 'uv_base' not in isolated
        assert isolated['uv'][0]==[(-.75,.5)]*3
        assert any('не итоговый diffuse' in note and 'opacity' in note for note in isolated['warnings'])
        equal(draw(isolated),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        for operation in (3,6):
            sampler=prepare_textured(ShaderModifierCore(direct_combiner_fixture(operation)),
                                     'Fixture.utx',multi_mesh,'static_mesh',
                                     overrides={0:('Fixture.utx',1)})
            assert sampler['textures'][0]['isolated_sampler']==0 and 'uv_base' not in sampler
            assert sampler['uv'][0]==[(-.75,.5)]*3
            assert any('не итоговый diffuse' in note and 'состояние Texture вместо Combiner' in note
                       for note in sampler['warnings'])
            equal(draw(sampler),(255,0,0))
            canvas.material_time(1.);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        rotator_core=ShaderModifierCore(rotator_nested_fixture())
        rotator_sampler=prepare_textured(rotator_core,'Fixture.utx',multi_mesh,'static_mesh',
                                        overrides={0:('Fixture.utx',1)})
        rotator_frame=prepare_textured(rotator_core,'Fixture.utx',multi_mesh,'static_mesh',
                                       overrides={0:('Fixture.utx',1)},frame_selection=(0,0,1))
        assert rotator_sampler['textures'][0]['isolated_sampler']==0 and 'uv_base' not in rotator_sampler
        assert rotator_sampler['uv'][0]==[(-.75,.5)]*3
        assert rotator_frame['textures'][0]['saved_frame_step']==1
        assert any('не итоговый diffuse' in note and 'четыре' in note.lower()
                   and 'разным моментам' in note for note in rotator_sampler['warnings'])
        equal(draw(rotator_sampler),(255,0,0))
        equal(draw(rotator_frame),(0,0,255))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,0,255))
        for color,alpha_op in ((2,0),(2,1),(3,1)):
            panner_combiner=prepare_textured(ShaderModifierCore(panner_combiner_fixture(color,alpha_op)),
                                             'Fixture.utx',multi_mesh,'static_mesh',
                                             overrides={0:('Fixture.utx',1)})
            pc_surface=panner_combiner['textures'][0]
            assert pc_surface['fragment_independent_uv'] and not pc_surface['uv_coordinate_exact']
            assert [(s['width'],s['height']) for s in pc_surface['fragment_layers']]==[(2,1),(1,1),(2,1)]
            pc_surface['render_state']=state(2)
            first=(255,0,0) if color==2 else (255,64,32)
            second=(0,128,0) if color==2 else (128,255,32)
            opacity=1. if alpha_op==0 else 128/255
            blended=lambda rgb:tuple(round(s*opacity+d*(1-opacity)) for s,d in zip(rgb,background))
            equal(draw(panner_combiner),blended(first))
            canvas.material_time(1.);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],blended(second))
            canvas.material_time(0.);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],blended(first))
        animated_docs=animated_combiner_fixture()
        animated_core=ShaderModifierCore(animated_docs)
        original_frame=prepare_textured(animated_core,'Fixture.utx',multi_mesh,'static_mesh',
                                        overrides={0:('Fixture.utx',1)})
        selected_frame=prepare_textured(animated_core,'Fixture.utx',multi_mesh,'static_mesh',
                                        overrides={0:('Fixture.utx',1)},frame_selection=(0,0,1))
        assert selected_frame['textures'][0]['fragment_layers'][0]['saved_frame_step']==1
        assert any('Шаг AnimNext (диагностика)' in note and 'игровая частота' in note
                   for note in selected_frame['warnings'])
        equal(draw(original_frame),(255,0,0))
        equal(draw(selected_frame),(0,0,64))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,0,64))
        alpha_core=ShaderModifierCore(alpha_modulate_fixture())
        alpha_base=prepare_textured(alpha_core,'Fixture.utx',multi_mesh,'static_mesh',
                                    overrides={0:('Fixture.utx',1)})
        alpha_frame=prepare_textured(alpha_core,'Fixture.utx',multi_mesh,'static_mesh',
                                     overrides={0:('Fixture.utx',1)},frame_selection=(0,1,1))
        assert alpha_base['textures'][0]['fragment_operation']==7
        assert alpha_frame['textures'][0]['fragment_layers'][1]['saved_frame_step']==1
        assert any('mFactor не воспроизводятся' in note and 'итоговый материал не подтверждён' in note
                   for note in alpha_frame['warnings'])
        equal(draw(alpha_base),(64,32,16))
        equal(draw(alpha_frame),(96,64,32))
        alpha_frame['textures'][0]['render_state']=state(2)
        opacity=128/255
        expected=tuple(round(source*opacity+dest*(1-opacity))
                       for source,dest in zip((96,64,32),background))
        equal(draw(alpha_frame),expected)
        incomplete=dict(coordinate_mesh,uv_streams=coordinate_mesh['uv_streams'][:1])
        selected=prepare_textured(CoordinateCore(1),'synthetic.utx',incomplete,
                                  'static_mesh',overrides={0:('synthetic.utx',1)})
        assert not selected['textures'] and any('UV1' in warning for warning in selected['warnings'])
        damaged_uv0=dict(coordinate_mesh,uv_streams=[
            dict(coordinate_index=0,coordinate_bits=[bits(float('nan'),.5)]*3),
            coordinate_mesh['uv_streams'][1]])
        selected=prepare_textured(CoordinateCore(1),'synthetic.utx',damaged_uv0,
                                  'static_mesh',overrides={0:('synthetic.utx',1)})
        assert selected['textures'][0]['uv_channel']==1,selected
        equal(draw(selected),(0,255,0))
        selected=prepare_textured(CoordinateCore(0),'synthetic.utx',damaged_uv0,
                                  'static_mesh',overrides={0:('synthetic.utx',1)})
        assert not selected['textures'] and any('UV0' in warning for warning in selected['warnings'])
        class NestedCoordinateCore(CoordinateCore):
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Coord',**{'class':'TexCoordSource'}),
                        dict(id=2,path='Image',**{'class':'Texture'}),
                        dict(id=3,path='Pan',**{'class':'TexPanner'})])}
                if kw['object_id']==1:
                    return {'result':dict(path='Coord',tags=[
                        dict(name='SourceChannel',value=1),dict(name='TexCoordSource',value=1),
                        dict(name='Material',value=dict(id=3,path='Pan',**{'class':'TexPanner'}))],
                        strings=[dict(name='Image',values=['Pan'])],shader=coord_shader(1))}
                if kw['object_id']==3:
                    return {'result':dict(path='Pan',tags=[
                        dict(name='PanRate',bits=bits(.5)[0]),
                        dict(name='Material',value=dict(id=2,path='Image',**{'class':'Texture'}))],
                        strings=[dict(name='Image',values=['Pan'])],shader=coord_shader(0))}
                return Core.request(self,**kw)
        selected=prepare_textured(NestedCoordinateCore(1),'synthetic.utx',coordinate_mesh,
                                  'static_mesh',overrides={0:('synthetic.utx',1)})
        assert selected['textures'][0]['uv_channel']==1 and 'uv_chain' in selected['textures'][0]
        equal(draw(selected),(0,255,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        class RotationCore(Core):
            def request(self,**kw):
                if kw['operation']=='resource_inventory':
                    return {'result':dict(candidates=[
                        dict(id=1,path='Rotator',**{'class':'TexRotator'}),
                        dict(id=2,path='Image',**{'class':'Texture'})])}
                if kw['object_id']==1:
                    doc=rotation_fixture()
                    doc['tags'].append(dict(name='Material',value=dict(id=2,**{'class':'Texture'})))
                    return {'result':doc}
                result=super().request(**kw)
                result['result']['tags'].extend([dict(name='USize',value=256),dict(name='VSize',value=256)])
                result['result']['mips']=[dict(width=256,height=256,
                    data_hex=('0000ffff'*128+'00ff00ff'*128)*256)]
                return result
        rotated_mesh=dict(mesh,uv_streams=[dict(coordinate_bits=[bits(.125,.75)]*3)])
        rotated=prepare_textured(RotationCore(),'synthetic.utx',rotated_mesh,'static_mesh',
                                 overrides={0:('synthetic.utx',1)})
        assert 'error' not in rotated and rotated['textures'],rotated
        assert .65<rotated['uv'][0][0][0]<.7
        equal(draw(rotated),(0,255,0))
        class AnimatedRotationCore(RotationCore):
            def request(self,**kw):
                result=super().request(**kw)
                if kw.get('object_id')==1 and kw['operation']!='resource_inventory':
                    result['result']['tags'].append(dict(name='TexRotationType',value=1))
                return result
        animated_rotator=prepare_textured(AnimatedRotationCore(),'synthetic.utx',rotated_mesh,
            'static_mesh',overrides={0:('synthetic.utx',1)})
        assert 'uv_base' in animated_rotator,animated_rotator
        equal(draw(animated_rotator),(255,0,0))
        canvas.material_time(1);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        shifted=prepare_textured(Core(offset=1),'synthetic.utx',mesh,'static_mesh',
                                 overrides={0:('synthetic.utx',1)})
        assert 'error' not in shifted and shifted['textures'],shifted
        equal(draw(shifted),(0,255,0))
        implicit=dict(tags=[dict(name='Material1',value=dict(id=1,path='Color',**{'class':'ConstantColor'}))],
                      strings=[],shader='c1=tFactor;a1=tFactor;result.xyz=c1.xyz;result.w=a1.w;')
        implicit_surface=combine(implicit,{'Material1':dict(width=1,height=1,pixels=bytes((*source,128)))})
        implicit_surface['render_state']=state(2)
        equal(draw(geometry({0:implicit_surface})),(52,77,101))
        masked=combine(masked_add_fixture(),{
            'Material1':dict(width=1,height=1,pixels=bytes([100,200,250,100])),
            'Material2':dict(width=1,height=1,pixels=bytes([20,100,200,128]))})
        masked['render_state']=state()
        equal(draw(geometry({0:masked})),(70,200,255))
        for explicit in (False,True):
            first=dict(width=1,height=1,pixels=bytes([100,200,250,37]))
            masked_alpha=combine(masked_add_alpha_fixture(explicit),dict(Material1=first,
                Material2=dict(width=1,height=1,pixels=bytes([20,100,200,128])),Mask=first))
            masked_alpha['render_state']=state(2)
            equal(draw(geometry({0:masked_alpha})),(31,57,72))
        first=dict(width=2,height=1,pixels=bytes([0,0,0,37,255,0,0,37]))
        second=dict(width=4,height=1,pixels=b''.join(bytes([0,0,0,a]) for a in (0,0,255,255)))
        fragment=fragment_surface(masked_add_alpha_fixture(),dict(Material1=first,Material2=second))
        fragment['render_state']=state()
        # At the filtering boundary: 0.5 * 0.5 = 0.25, not pre-baked 0.5.
        equal(draw(geometry({0:fragment},uv=(.5,.5))),(64,0,0))
        assert canvas.gpu.fragment_program and canvas.gpu.layer_ids
        fragment['render_state']=state(2)
        equal(draw(geometry({0:fragment},uv=(.5,.5))),(30,28,35))
        for inverted,expected in ((False,(255,0,0)),(True,(0,255,0))):
            mixed=fragment_surface(lerp_fixture(inverted),dict(
                Material1=dict(width=2,height=1,pixels=bytes([255,0,0,255])*2),
                Material2=dict(width=4,height=1,pixels=bytes([0,255,0,255])*4),
                Mask=dict(width=2,height=2,pixels=bytes([0,0,0,0,0,0,0,255])*2)))
            mixed['render_state']=state()
            equal(draw(geometry({0:mixed},uv=(.25,.5))),expected)
        equal(draw(geometry({0:surface(pixels,state(),width=2)},uv=(.25,.5))),(255,0,0))
        assert not canvas.gpu.layer_ids
        separate=lerp_fixture()
        separate['tags'][0]['value']=6
        separate['shader']=separate['shader'].replace(
            'c1.xyz*result.w+c2.xyz*(1.f-result.w)','c1.xyz+c1.w*c2.xyz')
        mixed=fragment_surface(separate,dict(
            Material1=dict(width=2,height=1,pixels=bytes([100,200,250,37])*2),
            Material2=dict(width=4,height=1,pixels=bytes([20,100,200,128])*4),
            Mask=dict(width=1,height=2,pixels=bytes([0,0,0,91])*2)))
        mixed['render_state']=state(2)
        equal(draw(geometry({0:mixed},uv=(.5,.5))),(40,93,117))
        for inverted,expected in ((False,(127,128,130)),(True,(128,127,130))):
            blended=combine(lerp_fixture(inverted),{
                'Material1':dict(width=1,height=1,pixels=bytes([255,0,30,17])),
                'Material2':dict(width=1,height=1,pixels=bytes([0,255,230,219])),
                'Mask':dict(width=1,height=1,pixels=bytes([99,77,55,128]))})
            blended['render_state']=state()
            equal(draw(geometry({0:blended})),expected)
        animated=geometry({0:dict(surface(pixels,state(),width=2),uv_pan_rate=.25)},uv=(.25,.5))
        equal(draw(animated),(255,0,0))
        canvas.material_time(2);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        assert animated['uv'][0][0]==(.25,.5)
        oscillator=geometry({0:dict(surface(pixels,state(),width=2),
            uv_oscillation=((0,1.,0.,.5),(0,1.,0.,0.)))},uv=(.25,.5))
        oscillator['uv_base']=[list(face) for face in oscillator['uv']]
        equal(draw(oscillator),(255,0,0))
        canvas.material_time(.25);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        stretch=geometry({0:dict(surface(pixels,state(),width=2),
            uv_oscillation=((1,1.,0.,1.,-.25),(0,1.,0.,0.)))},uv=(.25,.5))
        stretch['uv_base']=[list(face) for face in stretch['uv']]
        equal(draw(stretch),(255,0,0))
        canvas.material_time(.25);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        nested=geometry({0:dict(surface(pixels,state(),width=2),uv_chain=(
            ('oscillator',((0,1.,0.,0.),(0,1.,0.,.5))),
            ('fixed',((0.,1.,-1.,0.),(0.,0.)))))},uv=(.5,.75))
        nested['uv_base']=[list(face) for face in nested['uv']]
        from material_uv import timed_uv
        nested['uv']=timed_uv(nested,0.)
        equal(draw(nested),(255,0,0))
        canvas.material_time(.25);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        steps=(('panner',(.5,(1.,0.))),('fixed',((2.,0.,0.,1.),(0.,0.))))
        for chain,expected in ((steps,(255,0,0)),(tuple(reversed(steps)),(0,255,0))):
            composed=geometry({0:dict(surface(pixels,state(),width=2),uv_chain=chain)},uv=(.125,.5))
            composed['uv_base']=[list(face) for face in composed['uv']]
            composed['uv']=timed_uv(composed,0.)
            equal(draw(composed),(255,0,0))
            canvas.material_time(1.);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],expected)
            canvas.material_time(0);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        extended_steps=(('panner',(.25,(1.,0.))),('fixed',((2.,0.,0.,1.),(0.,0.))),
                        ('panner',(.25,(1.,0.))),('fixed',((2.,0.,0.,1.),(0.,0.))))
        extended=geometry({0:dict(surface(pixels,state(),width=2),uv_chain=extended_steps)},uv=(.0625,.5))
        extended['uv_base']=[list(face) for face in extended['uv']]
        extended['uv']=timed_uv(extended,0.)
        equal(draw(extended),(255,0,0))
        canvas.material_time(1/3);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        quarter=('matrix_rotation',dict(fixed_matrix=((0.,0.,1.),(0.,1.,0.),(-1.,0.,0.))))
        spatial=geometry({0:dict(surface(pixels,state(),width=2),
            uv_chain=(quarter,quarter))},uv=(.25,.5))
        spatial['uv_base']=[list(face) for face in spatial['uv']]
        draw(spatial)
        for seconds in (0.,1.,3600.,0.):
            canvas.material_time(seconds);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        stationary=animated_rotation(stationary_fixture(),(256,256))
        still=geometry({0:dict(surface(pixels,state(),width=2),uv_rotation_animation=stationary)},uv=(.25,.5))
        still['uv_base']=[list(face) for face in still['uv']]
        equal(draw(still),(255,0,0))
        for seconds in (1.,3600.,0.):
            canvas.material_time(seconds);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        repeat_preview=geometry({0:dict(surface(pixels,state(),width=2),
            uv_oscillation=((2,1.,0.,2.8284270763397217),(0,1.,0.,0.)),
            uv_oscillation_preview=True)},uv=(.25,.5))
        repeat_preview['uv_base']=[list(face) for face in repeat_preview['uv']]
        equal(draw(repeat_preview),(255,0,0))
        canvas.material_time(.5);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        double_doc=rotation_fixture(True)
        double_doc['tags'][0]['words']=[0,256,0]
        double_doc['tags'].append(dict(name='TexRotationType',value=1))
        double_rotation=animated_rotation(double_doc,(256,256))
        double_geom=geometry({0:dict(surface(pixels,state(),width=2),
                                     uv_rotation_animation=double_rotation)},uv=(.25,.1328125))
        equal(draw(double_geom),(255,0,0))
        canvas.material_time(64.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        double_doc['tags'][0]['words'][1]=255
        approximate_rotation=animated_rotation(double_doc,(256,256),preview_precision=True)
        assert approximate_rotation['preview_approximate']
        approximate_geom=geometry({0:dict(surface(pixels,state(),width=2),
            uv_rotation_animation=approximate_rotation)},uv=(.25,.1328125))
        equal(draw(approximate_geom),(255,0,0))
        canvas.material_time(64.251);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        spatial_doc,_=double_spatial_fixture()
        double_spatial=spatial_animation(spatial_doc,(256,256))
        # At t=16 the transformed U is exactly -.25 (the green texel centre).
        double_chain=geometry({0:dict(surface(pixels,state(),width=2),
            uv_chain=(('matrix_rotation',double_spatial),))},uv=(.25,.20183982798016367))
        double_chain['uv_base']=[list(face) for face in double_chain['uv']]
        equal(draw(double_chain),(255,0,0))
        canvas.material_time(16.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        zero_repeat=verified_oscillator_parameters(dict(tags=[
            dict(name='UOscillationType',value=2),
            dict(name='UOscillationAmplitude',bits=bits(0.)[0]),
            dict(name='VOscillationAmplitude',bits=bits(0.)[0])]),(2,1))
        still_repeat=geometry({0:dict(surface(pixels,state(),width=2),
                                      uv_oscillation=zero_repeat)},uv=(.25,.5))
        still_repeat['uv_base']=[list(face) for face in still_repeat['uv']]
        equal(draw(still_repeat),(255,0,0))
        for seconds in (1.,3600.,0.):
            canvas.material_time(seconds);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        stationary_repeat=verified_oscillator_parameters(dict(tags=[
            dict(name='UOscillationType',value=2),
            dict(name='UOscillationAmplitude',bits=bits(.5)[0]),
            dict(name='UOscillationRate',bits=bits(0.)[0]),
            dict(name='VOscillationAmplitude',bits=bits(0.)[0])]),(2,1))
        still_repeat=geometry({0:dict(surface(pixels,state(),width=2),
                                      uv_oscillation=stationary_repeat)},uv=(.25,.5))
        still_repeat['uv_base']=[list(face) for face in still_repeat['uv']]
        equal(draw(still_repeat),(255,0,0))
        for seconds in (1.,3600.,0.):
            canvas.material_time(seconds);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        still_direction=panner_direction(dict(tags=[
            dict(name='PanDirection',words=[10000,5000,32768]),
            dict(name='PanRate',bits=bits(0.)[0])]))
        still_roll=geometry({0:dict(surface(pixels,state(),width=2),uv_pan_rate=0.,
                                    uv_pan_direction=still_direction)},uv=(.25,.5))
        equal(draw(still_roll),(255,0,0))
        for seconds in (1.,3600.,0.):
            canvas.material_time(seconds);QTest.qWait(40)
            equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        roll_direction=panner_direction(dict(tags=[dict(name='PanDirection',words=[0,0,3])]))
        roll=geometry({0:dict(surface(pixels,state(),width=2),uv_pan_rate=.5,
                              uv_pan_direction=roll_direction)},uv=(.25,.5))
        equal(draw(roll),(255,0,0))
        canvas.material_time(1.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        verified_roll=panner_direction(dict(tags=[
            dict(name='PanDirection',words=[61440,8192,32768]),
            dict(name='PanRate',bits=bits(1.)[0])]))
        rolling=geometry({0:dict(surface(pixels,state(),width=2),uv_pan_rate=1.,
                                 uv_pan_direction=verified_roll)},uv=(.25,.5))
        equal(draw(rolling),(255,0,0))
        canvas.material_time(.5/verified_roll[0]);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0.);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        pitched_direction=panner_direction(dict(tags=[dict(name='PanDirection',words=[12288,0,0])]))
        pitched=geometry({0:dict(surface(pixels,state(),width=2),uv_pan_rate=1.,
                                uv_pan_direction=pitched_direction)},uv=(.25,.5))
        equal(draw(pitched),(255,0,0))
        canvas.material_time(.5/pitched_direction[0]);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        canvas.material_time(0);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(255,0,0))
        vertical=geometry({0:dict(width=1,height=2,pixels=bytes(pixels),
            render_state=state(),uv_pan_rate=.25,uv_pan_direction=(0.,-1.))},uv=(.5,.25))
        equal(draw(vertical),(255,0,0))
        canvas.material_time(2);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        cardinal=panner_direction(dict(tags=[dict(name='PanDirection',words=[0,16384,0])]))
        near_zero=geometry({0:dict(surface(pixels,state(),wrap=(1,0),width=2),
            uv_pan_rate=.5,uv_pan_direction=cardinal)},uv=(.25,.5))
        equal(draw(near_zero),(255,0,0))
        canvas.material_time(1);QTest.qWait(40)
        equal(canvas.gpu.grabFramebuffer().pixelColor(200,200).getRgb()[:3],(0,255,0))
        player=AnimationView();player.resize(500,500);player.show()
        try:
            prepared=dict(kind='skinning',name='Synthetic UV clock',frames=2,rate=1.,vertices=3,
                parents=[0],tracks=[dict(positions=[(0,0,0),(.1,0,0)],
                    rotations=[(0,0,0,1)],times=[0.,1.])],
                weights=[[(0,1.,p)] for p in [(-1,0,-1),(1,0,-1),(0,0,1)]],
                center=(0,0,0),scale=1.,polygons=[[0,1,2]],edges=[],
                uv=[[(.25,.5)]*3],face_materials=[0],
                textures={0:dict(surface(pixels,state(TwoSided=True),width=2),uv_pan_rate=.25)})
            player.display(prepared);player.set_loading(False)
            player.canvas.yaw=player.canvas.pitch=0.
            def player_pixel():
                QTest.qWait(40)
                image=player.canvas.gpu.grabFramebuffer()
                return image.pixelColor(image.width()//2,image.height()//2).getRgb()[:3]
            equal(player_pixel(),(255,0,0))
            player.seek(2000);equal(player_pixel(),(0,255,0))
            player.repeat.setChecked(True);equal(player_pixel(),(255,0,0))
            player.repeat.setChecked(False);player.material_clock.setChecked(False)
            equal(player_pixel(),(255,0,0))
            assert prepared['uv']==[[(.25,.5)]*3]
            # The first sampler is stationary; only the second one moves.
            independent_skin=dict(prepared,textures=independent['textures'],
                uv=independent['uv'],uv_base=independent['uv_base'],
                uv_input=independent['uv_input'],fragment_uv=independent['fragment_uv'],
                face_materials=independent['face_materials'])
            player.material_clock.setChecked(True);player.display(independent_skin)
            player.canvas.yaw=player.canvas.pitch=0.
            assert player.material_clock.isVisible()
            equal(player_pixel(),(255,0,0))
            player.seek(1000);equal(player_pixel(),(0,255,0))
            player.material_clock.setChecked(False);equal(player_pixel(),(255,0,0))
            assert independent_skin['uv_input']==independent['uv_input']
        finally:player.close()
        verify_application_imports()
        print(json.dumps(dict(blends=rows,alpha_threshold=True,culling=True,z_write=True,z_test=True,
                              clamp=True,combiner=True,tex_scaler=True,uv_offset=True,implicit_mask=True,
                              masked_add=True,tex_panner=True,skinning_uv_time=True,planar_panner=True,
                              fixed_rotator=True,animated_rotator=True,tex_oscillator=True,masked_blend=True,
                              oscillator_stretch_pivot=True,nested_uv=True,masked_add_alpha=True,
                              fragment_combiner=True,panner_scaler_chain=True,pitched_panner=True,
                              extended_uv_chain=True,stationary_rotator=True,spatial_rotator=True,
                              zero_repeat_subquantum_roll=True,precision_invariant_roll=True,
                              double_rotator_power2=True,static_uv_channel=True,nested_uv_channel=True,
                              stationary_repeat_and_roll=True,repeat_preview=True,stateful_snapshot=True,
                              nested_stateful_snapshot=True,
                              conflicting_uv2_shader=True,
                              independent_sampler_uv=True,
                              independent_sampler_channels=True,
                              independent_sampler_skinning_uv=True,
                              combiner_uv_snapshot=True,
                              vertex_color_saved_stream=True,
                              shader_modifier_diffuse=True,
                              shader_modifier_snapshot=True,
                              shader_modifier_multipass_first_diffuse=True,
                              shader_panner_snapshot=True,
                              isolated_sampler_snapshot=True,
                              isolated_direct_combiner_snapshot=True,
                              panner_combiner_two_grid=True,
                              saved_material_frame_selection=True,
                              direct_alpha_modulate=True,
                              isolated_rotator_nested_sampler=True,
                              roll_preview=True,rotation_precision_preview=True,
                              application_imports_verified=True,
                              opengl=canvas.gpu.version)))
    finally:
        canvas.clear();canvas.close();application.processEvents()


if __name__=='__main__':main()
