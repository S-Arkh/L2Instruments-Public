"""Diagnostic diffuse texture resolution and per-corner UV geometry."""
import math
import struct
from animation_decode import floats
from material_graph import ResourceResolver
from mesh_decode import prepare_mesh
from material_surface import diffuse


def prepare_textured(core,path,document,operation,dependencies=(),overrides=None,frame_selection=None):
    try:
        from material_frames import MAX_FRAME_STEP,select_material_frame
        if frame_selection is not None:
            if (not isinstance(frame_selection,(tuple,list)) or len(frame_selection)!=3
                    or any(type(value) is not int for value in frame_selection)
                    or not 0<=frame_selection[0]<=255 or not 0<=frame_selection[1]<=1
                    or not 0<=frame_selection[2]<=MAX_FRAME_STEP):
                raise ValueError('Invalid manual saved-frame selection')
            frame_selection=tuple(frame_selection)
        result=prepare_mesh(document,operation)
        body=document.get('body',document);refs=[];uv=[];slots=[]
        if operation=='static_mesh':
            for tag in document.get('tags',[]):
                if tag['name'].lower()=='materials':
                    for row in tag['value']:
                        refs.append(next((t['value'] for t in row if t['name'].lower()=='material'),None))
            streams=body.get('uv_streams',[])
            # Neutral faces need topology, not a fabricated texture mapping.
            # Decode the actual stream only for the material that uses it.
            uv=[[(0.,0.) for _ in face] for face in result['polygons']]
            for slot,section in enumerate(body['sections']):
                slots.extend([slot]*section['face_count'])
        elif operation=='skeletal_mesh':
            refs=body['textures']
            for face in body['triangles']:
                uv.append([floats(body['mesh_wedges'][i]['uv_bits'],2) for i in face['wedges']])
                material=face['material']
                if not 0<=material<len(body['materials']):raise ValueError('Invalid mesh material slot')
                slots.append(body['materials'][material][1])
        else:raise ValueError('Textured preview requires StaticMesh or SkeletalMesh')
        if len(uv)!=len(result['polygons']):raise ValueError('UV topology mismatch')
        resolver=ResourceResolver(core,dependencies);textures={};warnings=[]
        frame_error=None;frame_attempted=False
        fragment_inputs=[None]*len(uv)
        vertex_colors=[None]*len(uv)
        faces_by_slot={}
        for i,slot in enumerate(slots):faces_by_slot.setdefault(slot,[]).append(i)
        texture_bytes=0
        for slot in sorted(set(slots)):
            if overrides and slot in overrides:
                target,identifier=overrides[slot]
                reference=dict(id=identifier,path='',**{'class':''})
                warnings.append(f'Материал {slot}: пользовательская подстановка только для просмотра')
            elif slot>=len(refs) or not refs[slot] or not refs[slot].get('id'):
                warnings.append(f'Материал {slot}: отсутствует');continue
            else:target,reference=path,refs[slot]
            try:
                texture=diffuse(core,resolver,target,reference)
                if frame_selection is not None and slot==frame_selection[0]:
                    frame_attempted=True
                    try:
                        texture=select_material_frame(core,resolver,texture,*frame_selection[1:])
                    except (ValueError,RuntimeError,KeyError,IndexError,TypeError,struct.error,OSError) as error:
                        frame_error=str(error)
                        warnings.append(f'Материал {slot}: сохранённый кадр не выбран; '
                                        f'показан исходный кадр: {error}')
                channel=texture.get('uv_channel',0)
                layers=texture.get('fragment_layers',[]) if texture.get('fragment_independent_uv') else []
                channels=[channel]+[layer.get('uv_channel',0) for layer in layers]
                if any(type(value) is not int or not 0<=value<=7 for value in channels):
                    raise ValueError('неверный индекс UV-потока материала')
                selected={}
                selected_colors={}
                if texture.get('vertex_color'):
                    if operation!='static_mesh':
                        raise ValueError('сохранённый поток цветов доступен только для StaticMesh')
                    words=body.get('colors',[])
                    if not isinstance(words,list):
                        raise ValueError('неверный сохранённый поток цветов')
                    for i in faces_by_slot[slot]:
                        values=[]
                        for index in result['polygons'][i]:
                            if index<0 or index>=len(words):
                                raise ValueError('неполный сохранённый поток цветов')
                            word=words[index]
                            if type(word) is not int or not 0<=word<=0xffffffff:
                                raise ValueError('неверное сохранённое значение цвета')
                            values.append(tuple((word>>shift)&255 for shift in (0,8,16,24)))
                        selected_colors[i]=values
                    selected[0]={i:[(0.,0.)]*len(result['polygons'][i]) for i in faces_by_slot[slot]}
                elif operation=='static_mesh':
                    for current in set(channels):
                        if current>=len(streams):
                            raise ValueError(f'отсутствует поток UV{current}')
                        stream=streams[current]
                        if stream.get('coordinate_index',0)!=current:
                            raise ValueError(f'индекс потока UV{current} не подтверждён')
                        rows=stream.get('coordinate_bits',[]);cache={}
                        for i in faces_by_slot[slot]:
                            for index in result['polygons'][i]:
                                if index<0 or index>=len(rows):
                                    raise ValueError(f'неполный поток UV{current}')
                                if index not in cache:
                                    try:cache[index]=floats(rows[index],2)
                                    except (ValueError,TypeError,struct.error) as error:
                                        raise ValueError(f'неверные координаты потока UV{current}: {error}') from error
                                    if any(abs(v)>1e6 for v in cache[index]):
                                        raise ValueError(f'координаты потока UV{current} превышают лимит')
                        selected[current]={i:[cache[index] for index in result['polygons'][i]]
                                           for i in faces_by_slot[slot]}
                elif any(channels):
                    raise ValueError('в этой SkeletalMesh доступен только UV0')
                else:selected[0]={i:list(uv[i]) for i in faces_by_slot[slot]}
                storage=len(texture['pixels'])+sum(len(layer['pixels']) for layer in texture.get('fragment_layers',[]))
                if texture_bytes+storage>64*1024*1024:
                    raise ValueError('Decoded material textures exceed 64 MiB')
                textures[slot]=texture;texture_bytes+=storage
                for i,values in selected[channel].items():
                    uv[i]=values
                    if layers:
                        fragment_inputs[i]=tuple(selected[layer.get('uv_channel',0)][i] for layer in layers)
                    if selected_colors:vertex_colors[i]=selected_colors[i]
            except (ValueError,RuntimeError,KeyError,IndexError,TypeError,struct.error) as error:
                if frame_selection is not None and slot==frame_selection[0]:
                    frame_attempted=True;frame_error=str(error)
                warnings.append(f'Материал {slot}: {error}')
        for texture in textures.values():warnings.extend(texture.get('notes',[]))
        uv_input=([list(face) for face in uv]
                  if any(t.get('fragment_independent_uv') for t in textures.values()) else None)
        for i,slot in enumerate(slots):
            su,sv=textures.get(slot,{}).get('uv_scale',(1.,1.))
            ou,ov=textures.get(slot,{}).get('uv_offset',(0.,0.))
            a,b,c,d=textures.get(slot,{}).get('uv_rotation',(1.,0.,0.,1.))
            uv[i]=[(u*su*a+v*sv*c+ou,u*su*b+v*sv*d+ov) for u,v in uv[i]]
            if any(not math.isfinite(v) or abs(v)>1e6 for pair in uv[i] for v in pair):
                raise ValueError('Transformed UV coordinates exceed preview limits')
        result.update(uv=uv,face_materials=slots,textures=textures,warnings=list(dict.fromkeys(warnings)))
        if frame_selection is not None:
            result['frame_selection']=frame_selection
            if not frame_attempted:frame_error='Selected material slot is unavailable'
            if frame_error is not None:result['frame_error']=frame_error
        if any(face is not None for face in vertex_colors):result['vertex_colors']=vertex_colors
        from material_uv import has_timed_uv,timed_uv,timed_fragment_uv
        if any(has_timed_uv(t) for t in textures.values()):
            result['uv_base']=[list(face) for face in uv]
            result['uv']=timed_uv(result,0.)
        if uv_input is not None:
            result['uv_input']=uv_input
            result['fragment_inputs']=fragment_inputs
            result['fragment_uv']=timed_fragment_uv(result,0.)
        return result
    except (ValueError,KeyError,IndexError,TypeError) as error:
        return {'error':str(error)}
