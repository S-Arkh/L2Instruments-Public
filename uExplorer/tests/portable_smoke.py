"""Synthetic package -> native API/CLI -> widgets -> byte-exact source export."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import io
import math
import wave

SOURCE = b'class PortableExample extends Object;\r\n// Synthetic portable fixture\r\n'


def masked_add_fixture():
    return dict(tags=[dict(name='CombineOperation',value=6),dict(name='AlphaOperation',value=2),
        dict(name='Material1',value=dict(id=1,path='First',**{'class':'Texture'})),
        dict(name='Material2',value=dict(id=2,path='Second',**{'class':'Texture'}))],
        strings=[dict(name='Fixture.First',values=[]),dict(name='Fixture.Second',values=[])],
        shader='float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
        'result.xyz=c1.xyz;result.w=a1.w;float4 texcolor1=tex2D(s[1],tex0);'
        'c1=texcolor1;c2=result;a1=texcolor1;a2=result;'
        'result.xyz=c1.xyz+c1.w*c2.xyz;result.w=a1.w+a2.w;')


def compact(value):
    negative = value < 0
    value = abs(value)
    first = (value & 63) | (128 if negative else 0)
    value >>= 6
    result = bytearray([first | (64 if value else 0)])
    while value:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
    return bytes(result)


def masked_blend_fixture():
    document=masked_add_fixture()
    document['tags'][0]['value']=5
    document['tags'][1]['value']=0
    document['tags'].append(dict(name='Mask',value=document['tags'][3]['value']))
    document['shader']=document['shader'].replace('a2=result;','').replace(
        'c1.xyz+c1.w*c2.xyz','c1.xyz*texcolor1.w+c2.xyz*(1.f-texcolor1.w)').replace(
        'result.w=a1.w+a2.w','result.w=a1.w')
    return document


def masked_add_alpha_fixture(explicit=False):
    document=masked_add_fixture()
    document['tags'][1]['value']=0
    document['shader']=document['shader'].replace('a1=texcolor1;a2=result;','a1=result;').replace(
        'result.w=a1.w+a2.w','result.w=a1.w')
    if explicit:document['tags'].append(dict(name='Mask',value=document['tags'][2]['value']))
    return document


def fixture(path):
    names = ['None', 'Core', 'Class', 'TextBuffer', 'PortableExample', 'ScriptText']
    strings = b''.join(compact(len(name)+1)+name.encode()+b'\0'+struct.pack('<I', 0) for name in names)
    imports = compact(1)+compact(2)+struct.pack('<i', 0)+compact(3)
    # UClass fields: super, next, ScriptText, children; empty script and state metadata.
    cls = b'\0\0\x02\0\0\0'+bytes(8)+struct.pack('<i', 0)+bytes(26)
    text = b'\0'+bytes(8)+compact(len(SOURCE)+1)+SOURCE+b'\0'
    def entry(kind, outer, name, data, offset):
        return compact(kind)+compact(0)+struct.pack('<i', outer)+compact(name)+struct.pack('<I', 0)+compact(len(data))+compact(offset)
    exports = entry(0, 0, 4, cls, 1024)+entry(-1, 1, 5, text, 1024+len(cls))
    header = struct.pack('<IHHIiiiiii', 0x9e2a83c1, 123, 0, 0, len(names), 36,
                         2, 36+len(strings)+len(imports), 1, 36+len(strings))
    tables = header+strings+imports+exports
    path.write_bytes(tables+bytes(1024-len(tables))+cls+text)


def exercise(window, application, directory):
    from backend import export_classes
    from PySide6.QtCore import QSettings
    import backend
    root = Path(backend.__file__).resolve().parents[1]
    directory = Path(directory)
    package = directory/'Synthetic.u'
    fixture(package)
    core = window.core
    expected_core = root/'bin'/('uexplorer_core.dll' if sys.platform == 'win32' else 'libuexplorer_core.so')
    assert core.library.resolve() == expected_core.resolve(), core.library
    classes = core.request(operation='inspect', path=str(package))['package']['classes']
    assert len(classes) == 1 and classes[0]['name'] == 'PortableExample', classes
    result = core.request(operation='decompile', path=str(package), class_id=1)['result']
    assert result['status'] == 'source' and bytes.fromhex(result['raw_hex']) == SOURCE, result
    cli = root/'bin'/('uexplorer_cli.exe' if sys.platform == 'win32' else 'uexplorer_cli')
    response = subprocess.run([str(cli)], input=json.dumps(dict(operation='decompile', path=str(package), class_id=1)),
                              capture_output=True, text=True, encoding='utf-8', check=True, timeout=30)
    assert json.loads(response.stdout)['result'] == result
    invalid = directory/'Invalid.u'
    invalid.write_bytes(bytes(36))
    try:
        core.request(operation='inspect', path=str(invalid))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Invalid package accepted')
    invalid.unlink()
    export_classes(core, package, classes, directory/'export')
    assert (directory/'export/Synthetic/Classes/PortableExample.uc').read_bytes() == SOURCE
    try:
        export_classes(core, package, classes, directory/'export')
    except FileExistsError:
        pass
    else:
        raise AssertionError('Export silently overwrote an existing file')
    def wait():
        deadline = time.monotonic()+30
        while window.worker is not None:
            application.processEvents()
            if time.monotonic() > deadline:
                raise AssertionError('GUI worker timeout')
            time.sleep(.01)
    window.populate(str(directory))
    assert window.files.count() == 1
    window.files.setCurrentRow(0)
    wait()
    assert window.class_list.count() == 1, window.log.toPlainText()
    window.class_list.setCurrentRow(0)
    wait()
    assert window.code.toPlainText() == SOURCE.decode().replace('\r\n', '\n')
    assert window.code.isReadOnly() and window.selected_button.isEnabled()
    window.settings.sync()
    assert window.settings.status() == QSettings.Status.NoError
    if (root/'portable.json').exists():
        assert Path(window.settings.fileName()).resolve() == root/'data/settings.ini'
        saved = QSettings(str(root/'data/settings.ini'), QSettings.Format.IniFormat)
        assert saved.value('directory') == str(directory)
    resources = resource_widgets(application)
    return dict(native=True, cli=True, gui=True, export=True, settings=True, **resources)


def resource_widgets(application):
    """Exercise the shipped QtMultimedia/backend and resource widgets."""
    from PySide6.QtTest import QTest
    from PySide6.QtMultimedia import QMediaPlayer
    from texture_decode import decode_pixels
    from texture_view import TextureView
    from mesh_decode import prepare_mesh
    from mesh_view import MeshView
    from animation_view import AnimationView
    from vertmesh_decode import prepare_vertmesh
    from sound_view import SoundView
    from audio_analysis import waveform
    from resource_compare import differences
    from compare_view import CompareView
    from material_view import MaterialView
    from skinning import prepare_skin
    from material_state import state_for
    from material_math import combine,scaler,scaler_offset
    from material_shader import implicit_alpha_source
    from material_uv import panner_offset,panner_direction,timed_uv
    from material_rotation import fixed_rotation,animated_rotation,rotation_at,rotation_matrix,direction
    from material_oscillation import oscillator_at
    from material_chain import chain_matrix,modifier_chain
    from material_fragment import fragment_surface
    texture,mesh,animation,sound,comparison = TextureView(),MeshView(),AnimationView(),SoundView(),CompareView()
    try:
        pixels=decode_pixels(bytes([0,0,255,128]),1,1,5)
        texture.display(dict(pixels=pixels,width=1,height=1,format='RGBA8',mip_sizes=[(1,1)],level=0))
        assert texture.canvas.item.pixmap().toImage().pixelColor(0,0).getRgb()==(255,0,0,128)
        def bits(*v):return struct.unpack('<'+'I'*len(v),struct.pack('<'+'f'*len(v),*v))
        prepared=prepare_mesh(dict(polygons=[dict(vertices_bits=[bits(0,0,0),bits(1,0,0),bits(0,1,0)])]),'polys')
        mesh.display(prepared);assert not mesh.grab().isNull()
        track=dict(positions=[(0,0,0),(1,0,0)],rotations=[(0,0,0,1)],times=[0,1])
        prepared=dict(parents=[0,0],tracks=[track,dict(track,positions=[(0,0,1)])],
                      frames=2,rate=1,names=['Root','Child'],name='Synthetic',
                      center=(0,0,0),scale=2)
        animation.display(prepared);animation.set_loading(False)
        animation.slider.setValue(500)
        assert len(animation.canvas.geometry['points'])==2
        assert not animation.timer.isActive()
        animation.play.click();assert animation.timer.isActive()
        animation.clear();assert not animation.timer.isActive()
        vertex_doc=dict(body=dict(vertex_count=3,animated_vertex_count=3,frame_count=2,
            packed_original_vertices=[0,2,4096,2,4,4098],
            transforms=[0x3f800000]*3+[0]*6,wedges=[dict(vertex=i) for i in range(3)],
            faces=[[0,1,2,0]],sequences=[dict(name='Vertex',start=0,frames=2,rate_bits=0x3f800000)]))
        animation.load(vertex_doc,'vert_mesh')
        animation.display(prepare_vertmesh(vertex_doc,0));animation.set_loading(False)
        animation.slider.setValue(500)
        assert len(animation.canvas.geometry['polygons'])==1
        assert animation.canvas.geometry['points'][0]==(-.5,-.5,0.)
        animation.play.click();assert animation.timer.isActive()
        animation.clear();assert not animation.timer.isActive()
        vertex_doc['body'].pop('packed_original_vertices')
        vertex_doc['body']['vertices_bits']=[bits(*point) for point in
            [(0.25,0,0),(2,0,0),(0,2,0),(2.25,0,0),(4,0,0),(2,2,0)]]
        animation.load(vertex_doc,'vert_mesh')
        animation.display(prepare_vertmesh(vertex_doc,0));animation.set_loading(False)
        animation.slider.setValue(500)
        geometry=animation.canvas.geometry
        assert abs(geometry['points'][0][0]*geometry['scale']+geometry['center'][0]-1.25)<1e-9
        animation.clear()
        vertex_doc['body']['sequences'][0]['frames']=3
        assert 'error' in prepare_vertmesh(vertex_doc,0)
        assert prepare_vertmesh(vertex_doc,1)['diagnostic_frames']
        surface=dict(prepared)
        surface.update(points=[(-1,0,-1),(1,0,-1),(0,0,1)],polygons=[[0,1,2]],edges=[],
                       uv=[[(0,0),(1,0),(.5,1)]],face_materials=[0],
                       textures={0:dict(pixels=bytes([255,0,0,255]),width=1,height=1)})
        surface['textures'][0]['render_state']=state_for('FinalBlend',dict(tags=[]))
        combined=combine(dict(tags=[dict(name='CombineOperation',value=3),
                                    dict(name='AlphaOperation',value=3)]),
            {'Material1':dict(width=1,height=1,pixels=bytes([200,0,0,255])),
             'Material2':dict(width=1,height=1,pixels=bytes([55,0,0,255]))})
        assert combined['pixels']==bytes([255,0,0,255])
        assert scaler(dict(tags=[dict(name='UScale',bits=bits(.5)[0])]))==(2.,1.)
        assert scaler_offset(dict(tags=[dict(name='UOffset',bits=bits(64)[0])]),(256,256))==(.25,0.)
        implicit=dict(tags=[dict(name='Material1',value=dict(id=1,path='Color',**{'class':'ConstantColor'}))],
                      strings=[],shader='c1=tFactor;a1=tFactor;result.xyz=c1.xyz;result.w=a1.w;')
        assert implicit_alpha_source(implicit)=='Material1'
        fragment=fragment_surface(masked_add_alpha_fixture(),dict(
            Material1=dict(width=2,height=1,pixels=bytes([255,0,0,37])*2),
            Material2=dict(width=1,height=4,pixels=bytes([0,255,0,128])*4)))
        assert [(s['width'],s['height']) for s in fragment['fragment_layers']]==[(2,1),(1,4),(2,1)]
        assert not fragment['uv0_exact']
        for explicit in (False,True):
            first=dict(width=1,height=1,pixels=bytes([100,200,250,37]))
            masked_alpha=combine(masked_add_alpha_fixture(explicit),dict(
                Material1=first,Material2=dict(width=1,height=1,pixels=bytes([20,100,200,128])),Mask=first))
            assert masked_alpha['pixels']==bytes([70,200,255,37])
        blended=combine(masked_blend_fixture(),{
            'Material1':dict(width=1,height=1,pixels=bytes([255,0,30,17])),
            'Material2':dict(width=1,height=1,pixels=bytes([0,255,230,128])),
            'Mask':dict(width=1,height=1,pixels=bytes([0,255,230,128]))})
        assert blended['pixels']==bytes([127,128,130,128])
        masked=combine(masked_add_fixture(),{
            'Material1':dict(width=1,height=1,pixels=bytes([100,200,250,100])),
            'Material2':dict(width=1,height=1,pixels=bytes([20,100,200,128]))})
        assert masked['pixels']==bytes([70,200,255,228])
        assert panner_offset(-.25,1)==1023.75
        assert timed_uv(dict(uv=[[(.25,.5)]],face_materials=[0],
            textures={0:dict(uv_pan_rate=.25)}),2)==[[(.75,.5)]]
        vertical=panner_direction(dict(tags=[dict(name='PanDirection',words=[0,49152,0])]))
        pitched=panner_direction(dict(tags=[dict(name='PanDirection',words=[10000,5000,0])]))
        assert panner_direction(dict(tags=[dict(name='PanDirection',words=[10000,5000,3])]))==pitched
        invariant_roll=dict(tags=[dict(name='PanDirection',words=[61440,8192,32768]),
                                  dict(name='PanRate',bits=bits(1.)[0])])
        assert panner_direction(invariant_roll)==(.6532814502716064,.6532814502716064)
        try:panner_direction(dict(tags=[dict(name='PanDirection',words=[0,0,4])]))
        except ValueError:pass
        else:raise AssertionError('Unverified nonzero Roll was accepted')
        assert tuple(panner_offset(.699999988079071,658.9370727539062,c) for c in pitched)==(
            235.14512634277344,122.23058319091797)
        assert vertical==(0.,-1.)
        rotation_rows=((0.,-1.,0.,0.),(1.,0.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))
        rotation_doc=dict(tags=[dict(name='Rotation',words=[0,49152,0]),
            dict(name='M',members=[dict(name=name,members=[
                dict(name=axis,bits=bits(value)[0]) for axis,value in zip(('X','Y','Z','W'),row)])
                for name,row in zip(('XPlane','YPlane','ZPlane','WPlane'),rotation_rows)])])
        assert fixed_rotation(rotation_doc,(64,256))[:2]==((0.,-1.,1.,0.),(0.,0.))
        rotation_doc['tags'][0]['words']=[1,49152,3]
        assert fixed_rotation(rotation_doc,(64,256))[:2]==((0.,-1.,1.,0.),(0.,0.))
        assert rotation_at(dict(precision='invariant'),3600)==((1.,0.,0.,1.),(0.,0.))
        c,s=direction(53000,'double')
        double_rows=rotation_matrix(c,s,(0.,0.))
        double_doc=dict(tags=[dict(name='Rotation',words=[0,256,0]),
            dict(name='TexRotationType',value=1),
            dict(name='M',members=[dict(name=name,members=[
                dict(name=axis,bits=bits(value)[0]) for axis,value in zip(('X','Y','Z','W'),row)])
                for name,row in zip(('XPlane','YPlane','ZPlane','WPlane'),double_rows)])])
        double_animation=animated_rotation(double_doc,(256,256))
        assert double_animation['precision']=='double'
        assert rotation_at(double_animation,207.03125)[0][:2]==(c,s)
        double_doc['tags'][0]['words'][1]=255
        try:animated_rotation(double_doc,(256,256))
        except ValueError:pass
        else:raise AssertionError('Unverified double-angle velocity was accepted')
        assert animated_rotation(double_doc,(256,256),preview_precision=True)['preview_approximate']
        from material_rotation3d import spatial_animation,spatial_at
        spatial_rows=((.9582323431968689,.25492045283317566,.12963896989822388,0.),
                      (-.2570899724960327,.9663874506950378,0.,0.),
                      (-.1252814680337906,-.03332887962460518,.991561233997345,0.),
                      (0.,0.,0.,1.))
        spatial_doc=dict(tags=[dict(name='Rotation',words=[256,512,0]),
            dict(name='TexRotationType',value=1),
            dict(name='M',members=[dict(name=name,members=[
                dict(name=axis,bits=bits(value)[0]) for axis,value in zip(('X','Y','Z','W'),row)])
                for name,row in zip(('XPlane','YPlane','ZPlane','WPlane'),spatial_rows)])])
        spatial=spatial_animation(spatial_doc,(256,256))
        assert spatial['precision']=='double'
        assert spatial_at(spatial,5.3)==tuple(tuple(row[:3]) for row in spatial_rows[:3])
        quarter=((0.,0.,1.),(0.,1.,0.),(-1.,0.,0.))
        spatial_step=('matrix_rotation',dict(fixed_matrix=quarter))
        assert spatial_at(spatial_step[1],3600)==quarter
        assert chain_matrix((spatial_step,spatial_step),0)==((-1.,0.,0.),(0.,1.,0.),(0.,0.,-1.))
        assert oscillator_at(((0,1.,0.,.5),(0,1.,0.,0.)),.25)==((1.,1.),(.5,0.))
        assert oscillator_at(((1,1.,0.,1.,-.25),(0,1.,0.,0.)),.25)==((2.,1.),(.25,0.))
        from material_oscillation import verified_oscillator_parameters
        repeat_doc=dict(tags=[dict(name='UOscillationType',value=2),
                              dict(name='UOscillationAmplitude',bits=bits(0.)[0]),
                              dict(name='VOscillationAmplitude',bits=bits(0.)[0])])
        repeat=verified_oscillator_parameters(repeat_doc,(2,1))
        assert oscillator_at(repeat,3600)==((1.,1.),(0.,0.))
        repeat_doc['tags'][1]['bits']=bits(.1)[0]
        try:verified_oscillator_parameters(repeat_doc,(2,1))
        except ValueError:pass
        else:raise AssertionError('Unverified nonzero stretch-repeat was accepted')
        preview=((2,1.,0.,1.),(0,1.,0.,0.))
        try:oscillator_at(preview,.5)
        except ValueError:pass
        else:raise AssertionError('Unverified repeat ran without explicit preview')
        assert oscillator_at(preview,.5,preview_repeat=True)[0][0]>1.7
        assert chain_matrix((('oscillator',((0,1.,0.,.5),(0,1.,0.,0.))),
            ('fixed',((0.,1.,-1.,0.),(0.,0.)))),.25)[2]==(0.,.5,1.)
        steps=(('panner',(.5,(1.,0.))),('fixed',((2.,0.,0.,1.),(0.,0.))))
        assert chain_matrix(steps,.75)[2]==(.75,0.,1.)
        assert chain_matrix(tuple(reversed(steps)),.75)[2]==(.375,0.,1.)
        documents=[]
        for index in range(3):
            documents.append(dict(path=f'M{index}',**{'class':'TexPanner'},
                tags=[dict(name='Material',value=dict(id=index+2,path=f'M{index+1}',
                      **{'class':'Texture' if index==2 else 'TexPanner'}))],
                strings=[dict(name='Fixture.M3',values=[f'Fixture.M{i}' for i in range(index,3)])]))
        extended=modifier_chain(documents,dict(uv0_exact=True,native_size=(2,1)))
        assert len(extended)==3 and chain_matrix(extended,0)[2]==(0.,0.,1.)
        oscillator=dict(mode=2,yaw=0,rate=1500,amplitude=2500,pivot=(0.,0.),precision='float32')
        assert rotation_at(oscillator,3067.29541015625)[0][:2]==(
            .9735566973686218,.22844547033309937)
        assert timed_uv(dict(uv=[[(.25,.5)]],face_materials=[0],
            textures={0:dict(uv_pan_rate=.25,uv_pan_direction=vertical)}),2)==[[(.25,1024.)]]
        mesh.canvas.display(surface);mesh.canvas.style=2
        mesh.canvas.yaw=mesh.canvas.pitch=0.;mesh.canvas.resize(300,300)
        assert mesh.canvas.grab().toImage().pixelColor(150,150).red()==255
        material=MaterialView()
        try:
            material.load(dict(nodes=[dict(path='synthetic',id=1,name='Color',kind='ConstantColor',
                                           links=[],document=dict(tags=[]))],truncated=False))
            assert material.nodes.count()==1 and material.parameters.isReadOnly()
        finally:material.clear();material.deleteLater()
        bones=[dict(name='Root',parent=0,pose_bits=bits(0,0,0,1,0,0,0,1,0,0,0))]
        skin_mesh=dict(body=dict(bones=bones,points_bits=[bits(0,0,0),bits(1,0,0),bits(0,0,1)],
            mesh_wedges=[dict(vertex=i) for i in range(3)],triangles=[dict(wedges=[0,1,2])],
            influences=[dict(point=i,bone=0,weight_bits=bits(1)[0]) for i in range(3)]))
        motion=dict(body=dict(bones=bones,sequences=[dict(name='Move',frames=2,rate_bits=bits(1)[0])],
            moves=[dict(header=[0,0,0,bits(2)[0],0,0],bone_indices=[0],
                tracks=[dict(position_bits=[bits(0,0,0),bits(1,0,0)],
                             rotation_bits=[bits(0,0,0,1)],time_bits=bits(0,1))])]))
        pair=dict(mesh=skin_mesh,animation=motion,body=motion['body'],
            surface=dict(uv=[[(.25,.5)]*3],face_materials=[0],
                textures={0:dict(width=1,height=1,pixels=b'\xff'*4,uv_pan_rate=.25)}))
        skin=prepare_skin(pair,0);assert 'error' not in skin,skin
        animation.load(pair,'skinning');animation.display(skin);animation.set_loading(False)
        initial=animation.canvas.geometry['points'][0][0]
        animation.slider.setValue(500)
        assert animation.canvas.geometry['points'][0][0]>initial
        assert animation.canvas.geometry['uv']==[[(.375,.5)]*3]
        animation.material_clock.setChecked(False)
        assert animation.canvas.geometry['uv']==[[(.25,.5)]*3]
        animation.material_clock.setChecked(True);animation.stop()
        assert animation.canvas.geometry['uv']==[[(.25,.5)]*3]
        animation.clear()
        assert differences(dict(value_bits=0),dict(value_bits=0x80000000))
        assert comparison.details.isReadOnly()
        audio=io.BytesIO()
        with wave.open(audio,'wb') as output:
            output.setparams((1,2,8000,0,'NONE',''))
            output.writeframes(b''.join(struct.pack('<h',int(12000*math.sin(2*math.pi*440*i/8000)))
                                       for i in range(16000)))
        sound.mute.setChecked(True);sound.load(audio.getvalue(),waveform(audio.getvalue()),'Synthetic')
        assert sound.player.playbackState()==QMediaPlayer.StoppedState
        sound.toggle()
        deadline=time.monotonic()+10
        while not sound.plot.levels and time.monotonic()<deadline:QTest.qWait(10)
        assert sound.player.error()==QMediaPlayer.NoError,sound.player.errorString()
        assert sound.plot.levels,'Portable multimedia backend produced no decoded audio buffers'
        sound.clear();assert sound.buffer is None
        return dict(texture=True,geometry=True,animation=True,vertmesh=True,audio=True,comparison=True,
                    materials=True,textured_raster=True,skinning=True,stored_frames=True,material_state=True,
                    combiner=True,tex_scaler=True,uv_offset=True,implicit_mask=True,masked_add=True,
                     tex_panner=True,skinning_uv_time=True,planar_panner=True,fixed_rotator=True,
                     animated_rotator=True,tex_oscillator=True,masked_blend=True,
                     oscillator_stretch_pivot=True,nested_uv=True,masked_add_alpha=True,
                     fragment_preparation=True,panner_scaler_chain=True,pitched_panner=True,
                     extended_uv_chain=True,stationary_rotator=True,spatial_rotator=True,
                     zero_repeat_subquantum_roll=True,precision_invariant_roll=True,
                     double_rotator_power2=True)
    finally:
        for widget in (texture,mesh,animation,sound,comparison):
            widget.clear();widget.deleteLater()
        application.processEvents()


def main():
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    with tempfile.TemporaryDirectory(prefix='uexplorer-smoke-') as temp:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, temp)
        application = QApplication([])
        window = MainWindow()
        window.show()
        try:
            print(json.dumps(exercise(window, application, temp)))
        finally:
            window.close()


if __name__ == '__main__':
    main()
