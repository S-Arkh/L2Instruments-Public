"""Bounded material graph evaluation into diagnostic mip-grid surfaces."""
from pathlib import Path
from material_math import combiner_inputs,combine,opacity_surface,scaler,scaler_offset
from material_state import state_for
from material_shader import implicit_alpha_source
from material_uv import panner_preview_parameters
from material_rotation import fixed_rotation,rotation_step
from texture_decode import prepare_texture,property_value


def mark_approximate_uv(surface,note):
    surface['uv0_exact']=False
    surface['uv_coordinate_exact']=False
    surface['uv_preview_approximate']=True
    surface['notes']=surface['notes']+[note]


def diffuse(core,resolver,path,reference):
    remaining=[64,64*1024*1024]

    def evaluate(path,reference,active=(),mip_size=None):
        path,identifier=resolver.resolve(path,reference)
        key=path,identifier
        if key in active:raise ValueError('Material cycle')
        if len(active)>=32:raise ValueError('Material chain exceeds 32 nodes')
        remaining[0]-=1
        if remaining[0]<0:raise ValueError('Material evaluation exceeds 64 nodes')
        entry,doc=resolver.read(path,identifier,budget=remaining[1])
        remaining[1]-=entry.get('serial_bytes',0)
        if remaining[1]<0:raise ValueError('Material evaluation exceeds 64 MiB')
        active=(*active,key);kind=entry['class'].rsplit('.',1)[-1]
        def child(field,mip_size=None):
            ref=property_value(doc,field,None)
            if not isinstance(ref,dict) or not ref.get('id'):
                raise ValueError(f'Missing {kind}.{field} material reference')
            return evaluate(path,ref,active,mip_size)
        def read_limited(proof_path,proof_id):
            remaining[0]-=1
            if remaining[0]<0:raise ValueError('Material evaluation exceeds 64 nodes')
            proof_entry,proof_doc=resolver.read(proof_path,proof_id,budget=remaining[1])
            remaining[1]-=proof_entry.get('serial_bytes',0)
            if remaining[1]<0:raise ValueError('Material evaluation exceeds 64 MiB')
            return proof_entry,proof_doc
        if 'mips' in doc:
            level=next((i for i,m in enumerate(doc['mips']) if max(m['width'],m['height'])<=512),len(doc['mips'])-1)
            if mip_size is not None:
                levels=[i for i,m in enumerate(doc['mips']) if (m['width'],m['height'])==mip_size]
                if len(levels)!=1:raise ValueError('Missing or ambiguous common stored mip')
                level=levels[0]
            result=prepare_texture(core,path,doc,level,dependencies=resolver.dependencies)
            if 'error' in result:raise ValueError(result['error'])
            wrap=[property_value(doc,key,0) for key in ('UClampMode','VClampMode')]
            if any(v not in (0,1) for v in wrap):raise ValueError('Unsupported texture clamp mode')
            surface=dict(result,name=entry['path'],notes=[],wrap=wrap,uv_scale=(1.,1.),
                         native_size=(doc['mips'][0]['width'],doc['mips'][0]['height']),
                         stored_mip_sizes=[(m['width'],m['height']) for m in doc['mips']],
                         uv0_exact=True,render_state=state_for('Texture',doc))
            from material_frames import has_saved_next
            if kind=='Texture' and has_saved_next(doc):
                surface['saved_frame_root']=(path,identifier)
            return surface
        if mip_size is not None:raise ValueError('Common stored mip requires direct Texture inputs')
        if kind=='ConstantColor':
            tag=next((t for t in doc.get('tags',[]) if t['name'].lower()=='color'),None)
            color=tag['bytes'] if tag else [255]*4
            return dict(pixels=bytes(color),width=1,height=1,name=entry['path'],notes=[],
                         uv0_exact=True,uv_scale=(1.,1.),wrap=(0,0),render_state=state_for(kind,doc))
        if kind=='VertexColor':
            if (doc.get('tags')!=[] or doc.get('strings')!=[] or doc.get('shader')!=''):
                raise ValueError('VertexColor saved material form is not recognized')
            return dict(width=1,height=1,pixels=b'\xff\xff\xff\xff',name=entry['path'],
                        wrap=(0,0),uv_scale=(1.,1.),uv0_exact=False,uv_coordinate_exact=False,
                        vertex_color=True,render_state=state_for(kind,doc),notes=[
                            'VertexColor: только сохранённый поток цветов StaticMesh (RGBA); '
                            'игровое освещение и runtime diffuse не подтверждены; '
                            'отдельный alpha-поток не применяется; композиция материалов отключена; '
                            'Qt raster показывает средний цвет грани'])
        if kind=='Combiner':
            if property_value(doc,'CombineOperation',0)==7:
                from material_shader import verify_direct_alpha_modulate
                from material_fragment import alpha_modulate_surface
                targets=verify_direct_alpha_modulate(doc,path,resolver,read_limited,active)
                first,second=(evaluate(target,dict(id=identifier),active) for target,identifier in targets)
                result=alpha_modulate_surface(first,second)
                result['name']=entry['path']
                result['render_state']=state_for('Combiner',doc)
                result['saved_frame_mode']='alpha_modulate'
                result['notes']=first['notes']+second['notes']+[
                    'Combiner alpha-modulate: GPU фильтрует две Texture отдельно и показывает '
                    'Material2.rgb × Material1.alpha; игровое освещение и mFactor не '
                    'воспроизводятся, итоговый материал не подтверждён; Qt raster показывает '
                    'только Material1, игровая анимация кадров Texture не воспроизводится']
                mark_approximate_uv(result,'Композиция материалов с этим preview отключена')
                return result
            from material_multisample import independent_multiply_shader,verify_multiply_bindings
            independent=independent_multiply_shader(doc)
            _,_,fields=combiner_inputs(doc)
            surfaces={field:child(field) for field in fields}
            grids={field:s for field,s in surfaces.items() if (s['width'],s['height'])!=(1,1)}
            sizes={(s['width'],s['height']) for s in grids.values()}
            mip_note=None
            if len(sizes)>1 and all(
                    property_value(doc,field,{}).get('class','').rsplit('.',1)[-1]=='Texture'
                    and 'stored_mip_sizes' in s for field,s in grids.items()):
                common=set.intersection(*(set(s['stored_mip_sizes']) for s in grids.values()))
                common={size for size in common if size!=(1,1) and all(
                    size[0]<=s['width'] and size[1]<=s['height'] for s in grids.values())}
                if common:
                    size=max(common,key=lambda size:(size[0]*size[1],size))
                    for field,s in grids.items():
                        if (s['width'],s['height'])!=size:surfaces[field]=child(field,size)
                    mip_note=f'Combiner: общий сохранённый mip {size[0]}×{size[1]}, без пересэмплирования'
            fragment=independent or (len({(s['width'],s['height']) for s in surfaces.values()})>1
                                     and len(sizes)>1)
            if fragment:
                from material_fragment import fragment_surface
                if independent:
                    verify_multiply_bindings(doc,path,active,read_limited,resolver)
                result=fragment_surface(doc,surfaces,independent=independent)
                if independent:
                    from material_multisample import independent_multiply_profile
                    result['fragment_provenance']=dict(shader=doc['shader'],
                        channels=tuple(part[0] for part in independent_multiply_profile(doc)),
                        strings=[dict(name=item['name'],values=list(item['values']))
                                 for item in doc['strings']])
            else:result=combine(doc,surfaces)
            notes=[note for surface in surfaces.values() for note in surface['notes']]
            if mip_note:notes.append(mip_note)
            if property_value(doc,'CombineOperation',0)==6:
                notes.append('Combiner: masked add подтверждён shader; Material2 + alpha2 × Material1')
            if property_value(doc,'CombineOperation',0)==5:
                notes.append('Combiner: masked blend подтверждён shader; Material1 × (1-mask) + Material2 × mask')
            if independent:
                notes.append('Combiner: независимые UV-цепочки двух sampler, '
                             'игровые часы и освещение не воспроизводятся')
            notes.append('Combiner: GPU смешивает после фильтрации отдельных mip; Qt raster показывает только Material1'
                         if fragment else 'Combiner: вычислено на сетке mip, 8 бит; фильтрация после смешивания')
            implicit=implicit_alpha_source(doc) if property_value(doc,'AlphaOperation',0)==0 else None
            if implicit:notes.append('Combiner: неявный alpha подтверждён сохранённым shader → '+implicit)
            return dict(result,name=entry['path'],notes=notes,render_state=state_for(kind,doc))
        if kind=='Shader':
            result=child('Diffuse')
            opacity=property_value(doc,'Opacity',None)
            if isinstance(opacity,dict) and opacity.get('id'):
                other=child('Opacity')
                result=opacity_surface(result,other)
                result['notes']=result['notes']+other['notes']+['Shader.Opacity: alpha отдельной карты, согласованные UV']
            result['render_state']=state_for(kind,doc)
            result['notes']=result['notes']+['Shader: framebuffer/opacity; освещение и дополнительные карты не исполняются']
            return result
        if kind=='FinalBlend':
            result=child('Material');result['render_state']=state_for(kind,doc)
            return result
        if (kind in ('TexOscillatorTriggered','TexPannerTriggered')
                or kind=='TexOscillator' and any(
                    property_value(doc,axis+'OscillationType',0)==3 for axis in ('U','V'))):
            from material_snapshot import cached_uv_snapshot
            ref=property_value(doc,'Material',{})
            strings=doc.get('strings')
            sampler=(strings[0].get('name') if isinstance(strings,list) and len(strings)==1
                     and isinstance(strings[0],dict) else None)
            target=ref.get('path') if isinstance(ref,dict) else None
            unique_leaf=False
            if (isinstance(ref,dict) and ref.get('id') and isinstance(sampler,str)
                    and sampler and '.' not in sampler and isinstance(target,str)
                    and (target.casefold()==sampler.casefold()
                         or target.casefold().endswith('.'+sampler.casefold()))):
                target_path,target_id=resolver.resolve(path,ref)
                matches=[item for item in resolver.inventory(target_path)['candidates']
                         if item['path'].rsplit('.',1)[-1].casefold()==sampler.casefold()]
                unique_leaf=len(matches)==1 and matches[0]['id']==target_id
            try:
                rotation,offset=cached_uv_snapshot(doc,entry['path'],ref,unique_leaf)
            except ValueError:
                # Keep the existing marked triggered fallback or jitter error.
                pass
            else:
                result=child('Material')
                if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                    raise ValueError('Cached UV snapshot requires an exact direct Texture')
                result['uv_rotation']=rotation
                result['uv_offset']=offset
                result['uv0_exact']=False
                result['uv_coordinate_exact']=False
                result['uv_snapshot']=True
                result['notes']=result['notes']+[
                    kind+': только сохранённая UV-матрица; время, события и случайное состояние '
                    'не воспроизводятся, композиция материалов отключена']
                return result
        modifiers=('TexPanner','TexScaler','TexOscillator','TexRotator','TexCoordSource',
                   'TexPannerTriggered','TexOscillatorTriggered')
        if kind in modifiers:
            ref=property_value(doc,'Material',{})
            if isinstance(ref,dict) and ref.get('class','').rsplit('.',1)[-1] in modifiers:
                from material_chain import modifier_chain
                documents=[dict(doc,**{'class':kind})];chain_path=path;chain_active=active
                while isinstance(ref,dict) and ref.get('class','').rsplit('.',1)[-1] in modifiers:
                    child_path,child_id=resolver.resolve(chain_path,ref)
                    key=child_path,child_id
                    if key in chain_active:raise ValueError('Material cycle')
                    if len(chain_active)>=32:raise ValueError('Material chain exceeds 32 nodes')
                    remaining[0]-=1
                    if remaining[0]<0:raise ValueError('Material evaluation exceeds 64 nodes')
                    child_entry,child_doc=resolver.read(child_path,child_id,budget=remaining[1])
                    remaining[1]-=child_entry.get('serial_bytes',0)
                    if remaining[1]<0:raise ValueError('Material evaluation exceeds 64 MiB')
                    child_kind=child_entry['class'].rsplit('.',1)[-1]
                    if child_kind!=ref['class'].rsplit('.',1)[-1]:
                        raise ValueError('UV chain requires a direct Texture leaf and matching modifier classes')
                    documents.append(dict(child_doc,**{'class':child_kind}))
                    chain_path=child_path;chain_active=(*chain_active,key)
                    ref=property_value(child_doc,'Material',{})
                if not isinstance(ref,dict) or ref.get('class','').rsplit('.',1)[-1]!='Texture':
                    raise ValueError('UV chain requires a direct Texture leaf')
                result=evaluate(chain_path,ref,chain_active)
                from material_snapshot import cached_uv_chain,snapshot_modifier
                if any(snapshot_modifier(d['class'],d) for d in documents):
                    try:
                        leaf_path,_=resolver.resolve(chain_path,ref)
                        rotation,offset=cached_uv_chain(documents,result,Path(leaf_path).stem)
                    except ValueError as error:
                        if kind not in ('TexPannerTriggered','TexOscillatorTriggered'):
                            raise
                        # Preserve the previous labelled child-only fallback.
                        result=child('Material')
                        result['uv0_exact']=False
                        result['uv_coordinate_exact']=False
                        result['notes']=result['notes']+[
                            kind+': показан исходный Material, без эффекта; '
                            'сохранённая UV-цепочка недоступна: '+str(error)]
                        return result
                    result['uv_rotation']=rotation
                    result['uv_offset']=offset
                    result['uv0_exact']=False
                    result['uv_coordinate_exact']=False
                    result['uv_snapshot']=True
                    result['notes']=result['notes']+[
                        'UV: композиция сохранённых матриц '+' → '.join(d['class'] for d in documents)
                        +'; только статический снимок, одновременное состояние, игровое время '
                        'и события не подтверждены; композиция материалов отключена']
                    return result
                result['uv_chain']=modifier_chain(documents,result)
                from material_coordinates import chain_channel
                channel=chain_channel(documents)
                if any(d['class']=='TexCoordSource' for d in documents):
                    result['uv_channel']=channel
                    result['uv0_exact']=channel==0
                    result['uv_coordinate_exact']=True
                    result['notes']=result['notes']+[
                        f'TexCoordSource: UV{channel} из потока модели; игровое исполнение не проверено']
                if any(step[0]=='oscillator_preview' for step in result['uv_chain']):
                    mark_approximate_uv(result,
                        'TexOscillator stretch-repeat: приблизительная диагностическая модель; '
                        'округление угла и игровое время не подтверждены, композиция материалов отключена')
                if any(step[0]=='panner_preview' for step in result['uv_chain']):
                    mark_approximate_uv(result,
                        'TexPanner Roll: приблизительная float32-модель; точность направления '
                        'и времени не подтверждена, композиция материалов отключена')
                if any(isinstance(value,dict) and value.get('preview_approximate')
                       for _,value in result['uv_chain']):
                    mark_approximate_uv(result,
                        'TexRotator: приблизительная модель неоднозначной точности/часов; '
                        'игровая траектория не подтверждена, композиция материалов отключена')
                result['notes']=result['notes']+[
                    'UV: '+' → '.join(d['class'] for d in documents)
                    +'; порядок каждого sampler suffix проверен; float32 matrix composition']
                return result
        if kind=='TexPanner':
            ref=property_value(doc,'Material',{})
            if (isinstance(ref,dict) and isinstance(ref.get('class'),str)
                    and ref['class'].rsplit('.',1)[-1]=='Combiner'):
                from material_shader import verify_panner_combiner
                from material_fragment import panner_combiner_surface
                child_path,child_id=resolver.resolve(path,ref)
                if (child_path,child_id) in active:raise ValueError('Material cycle')
                child_entry,child_doc=read_limited(child_path,child_id)
                nested_active=(*active,(child_path,child_id))
                operation=property_value(child_doc,'CombineOperation',0)
                nested_field='Material2' if operation==6 else 'Material1' if operation==3 else None
                nested_ref=property_value(child_doc,nested_field,{}) if nested_field else {}
                if (isinstance(nested_ref,dict) and isinstance(nested_ref.get('class'),str)
                        and nested_ref['class'].rsplit('.',1)[-1]=='Combiner'):
                    from material_snapshot import isolated_combiner_sampler
                    texture_path,texture_id,chain,rotation,offset=isolated_combiner_sampler(
                        path,entry,doc,child_path,child_entry,child_doc,
                        resolver,read_limited,nested_active)
                    result=evaluate(texture_path,dict(id=texture_id),chain)
                    if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                        raise ValueError('Isolated sampler requires an exact direct Texture')
                    result['uv_rotation']=rotation
                    result['uv_offset']=offset
                    result['uv_snapshot']=True
                    result['isolated_sampler']=0
                    result['saved_frame_mode']='isolated'
                    mark_approximate_uv(result,
                        'TexPanner → Combiner: только отдельный sampler 0, не итоговый diffuse и не '
                        'результат материала; состояние Texture вместо Combiner, остальные ветви, '
                        'их alpha и игровая анимация Texture не воспроизводятся. Сохранённые UV-матрицы '
                        'могут относиться к разным моментам; игровые события и время не '
                        'подтверждены; композиция отключена')
                    return result
                targets,color,alpha,multiplier=verify_panner_combiner(
                    path,entry,doc,child_path,child_entry,child_doc,resolver,read_limited,nested_active)
                first,second=(evaluate(target,dict(id=identifier),nested_active)
                              for target,identifier in targets)
                rate,direction,uncertain=panner_preview_parameters(doc)
                result=panner_combiner_surface(first,second,color,alpha,multiplier,rate,direction)
                result['saved_frame_mode']='panner_combiner'
                result['name']=child_entry['path']
                result['render_state']=state_for('Combiner',child_doc)
                result['notes']=first['notes']+second['notes']+[
                    'TexPanner → Combiner: GPU фильтрует две Texture отдельно перед смешиванием; '
                    'Qt raster показывает только Material1; показаны выбранные сохранённые mip, '
                    'игровая анимация кадров Texture не воспроизводится; игровое освещение и mFactor '
                    'не воспроизводятся, время диагностическое, не игровые часы']
                if uncertain:
                    result['notes'].append('TexPanner Roll: приблизительная float32-модель, точность не подтверждена')
                mark_approximate_uv(result,'Композиция материалов с этим preview отключена')
                return result
        if kind in ('TexPanner','TexOscillator','TexRotator'):
            ref=property_value(doc,'Material',{})
            if isinstance(ref,dict) and ref.get('class','').rsplit('.',1)[-1]=='Shader':
                from material_shader import verify_shader_modifier
                child_path,child_id=resolver.resolve(path,ref)
                if (child_path,child_id) in active:raise ValueError('Material cycle')
                child_entry,child_doc=read_limited(child_path,child_id)
                diffuse_ref=property_value(child_doc,'Diffuse',{})
                if (kind=='TexPanner' and isinstance(diffuse_ref,dict)
                        and isinstance(diffuse_ref.get('class'),str)
                        and diffuse_ref['class'].rsplit('.',1)[-1]=='Combiner'):
                    from material_snapshot import isolated_combiner_sampler
                    texture_path,texture_id,nested_active,rotation,offset=isolated_combiner_sampler(
                        path,entry,doc,child_path,child_entry,child_doc,
                        resolver,read_limited,(*active,(child_path,child_id)))
                    result=evaluate(texture_path,dict(id=texture_id),nested_active)
                    if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                        raise ValueError('Isolated sampler requires an exact direct Texture')
                    result['uv_rotation']=rotation
                    result['uv_offset']=offset
                    result['uv_snapshot']=True
                    result['isolated_sampler']=0
                    result['saved_frame_mode']='isolated'
                    mark_approximate_uv(result,
                        'Shader/Combiner: только отдельный sampler 0, не итоговый diffuse и не '
                        'результат материала; состояние Texture вместо Shader, остальные слои, '
                        'opacity и игровая анимация Texture не воспроизводятся. Сохранённые UV-матрицы '
                        'могут относиться к разным моментам; игровые события и время не '
                        'подтверждены; композиция отключена')
                    return result
                if (kind=='TexRotator' and isinstance(diffuse_ref,dict)
                        and isinstance(diffuse_ref.get('class'),str)
                        and diffuse_ref['class'].rsplit('.',1)[-1]=='TexPanner'):
                    from material_snapshot import shader_panner_snapshot
                    panner_path,panner_id=resolver.resolve(child_path,diffuse_ref)
                    nested_active=(*active,(child_path,child_id))
                    if (panner_path,panner_id) in nested_active:raise ValueError('Material cycle')
                    panner_entry,panner_doc=read_limited(panner_path,panner_id)
                    leaf=property_value(panner_doc,'Material',{})
                    if not isinstance(leaf,dict) or not leaf.get('id'):
                        raise ValueError('Shader snapshot requires a Texture leaf')
                    texture_path,texture_id=resolver.resolve(panner_path,leaf)
                    nested_active=(*nested_active,(panner_path,panner_id))
                    if (texture_path,texture_id) in nested_active:raise ValueError('Material cycle')
                    texture_entry,_=read_limited(texture_path,texture_id)
                    rotation,offset=shader_panner_snapshot(
                        path,entry,doc,child_path,child_entry,child_doc,
                        panner_path,panner_entry,panner_doc,texture_path,texture_entry)
                    result=evaluate(panner_path,leaf,nested_active)
                    if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                        raise ValueError('Shader snapshot requires an exact direct Texture')
                    result['render_state']=state_for('Shader',child_doc)
                    result['uv_rotation']=rotation
                    result['uv_offset']=offset
                    result['uv_snapshot']=True
                    mark_approximate_uv(result,
                        'TexRotator → Shader → TexPanner: только diffuse и композиция сохранённых '
                        'UV-матриц; они могут относиться к разным моментам, анимация, остальные карты '
                        'и игровое освещение не воспроизводятся; композиция материалов отключена')
                    return result
                result=child('Material')
                verify_shader_modifier(doc,path,entry,ref,child_path,child_entry,child_doc,result,
                                       resolver,read_limited,(*active,(child_path,child_id)))
                if child_doc.get('shader','').startswith('if(currentpass==0){'):
                    result['notes']=result['notes']+[
                        'Shader: показан только diffuse первого прохода; другие проходы и их sampler '
                        'не вычисляются, состояния проходов не подтверждены']
                if 'EnvTex.tex4' in child_doc.get('shader',''):
                    result['notes']=result['notes']+[
                        'Shader EnvTex: environment mapping не вычисляется и не подтверждён']
                if kind=='TexPanner':
                    rate,direction,uncertain=panner_preview_parameters(doc)
                    result['uv_pan_rate']=rate
                    result['uv_pan_direction']=direction
                    if uncertain:
                        result['notes']=result['notes']+[
                            'TexPanner Roll: приблизительная float32-модель, точность не подтверждена']
                elif kind=='TexOscillator':
                    from material_oscillation import (oscillator_parameters,repeat_needs_preview,
                                                      StatefulOscillation,UnverifiedOscillatorPivot)
                    try:
                        axes=oscillator_parameters(doc,None)
                    except (StatefulOscillation,UnverifiedOscillatorPivot):
                        from material_snapshot import planar_uv_matrix
                        matrix=planar_uv_matrix(doc)
                        result['uv_rotation']=(matrix[0][0],matrix[0][1],matrix[1][0],matrix[1][1])
                        result['uv_offset']=matrix[2][:2]
                        result['uv_snapshot']=True
                        result['notes']=result['notes']+[
                            'TexOscillator: только сохранённая UV-матрица; pivot, случайное состояние '
                            'и анимация не восстанавливаются']
                    else:
                        result['uv_oscillation']=axes
                        if repeat_needs_preview(axes):
                            result['uv_oscillation_preview']=True
                            result['notes']=result['notes']+[
                                'TexOscillator stretch-repeat: приблизительная модель, точность не подтверждена']
                else:
                    from material_snapshot import planar_uv_matrix
                    if (property_value(doc,'TexCoordSource',15) not in (0,15)
                            or property_value(doc,'TexCoordCount',0)!=0
                            or property_value(doc,'TexCoordProjected',False)):
                        raise ValueError('UV modifier Shader requires unprojected UV0')
                    matrix=planar_uv_matrix(doc)
                    result['uv_rotation']=(matrix[0][0],matrix[0][1],matrix[1][0],matrix[1][1])
                    result['uv_offset']=matrix[2][:2]
                    result['uv_snapshot']=True
                    result['notes']=result['notes']+[
                        'TexRotator: только сохранённая UV-матрица, анимация не воспроизводится']
                mark_approximate_uv(result,
                    kind+' → Shader: только diffuse; остальные карты и игровое освещение '
                    'не воспроизводятся, время и размеры Shader не подтверждены; '
                    'композиция материалов отключена')
                return result
        if kind=='TexCoordSource':
            from material_coordinates import coordinate_channel,verify_direct_source
            channel=coordinate_channel(doc)
            ref=property_value(doc,'Material',{})
            if (channel==2 and isinstance(ref,dict)
                    and ref.get('class','').rsplit('.',1)[-1]=='Combiner'):
                result=child('Material')
                proof=result.get('fragment_provenance',{})
                if (not result.get('fragment_independent_uv') or proof.get('channels')!=(0,0)
                        or doc.get('shader')!=proof.get('shader')
                        or doc.get('strings')!=proof.get('strings')):
                    raise ValueError('TexCoordSource requires matching saved Combiner shader and samplers')
                target_path,_=resolver.resolve(path,ref)
                target=ref.get('path');actual=result.get('name')
                if (not isinstance(target,str) or not target or not isinstance(actual,str) or not actual
                        or target.casefold() not in (actual.casefold(),
                            (Path(target_path).stem+'.'+actual).casefold())):
                    raise ValueError('TexCoordSource resolved Combiner differs from saved reference')
                result['uv_channel']=0
                mark_approximate_uv(result,
                    'TexCoordSource: свойства выбирают UV2, сохранённый shader выбирает UV0; '
                    'показан только диагностический UV0, игровой выбор не подтверждён; '
                    'композиция материалов отключена')
                return result
            if not isinstance(ref,dict) or ref.get('class','').rsplit('.',1)[-1]!='Texture':
                raise ValueError('TexCoordSource currently requires a direct Texture')
            strings=doc.get('strings')
            sampler=(strings[0].get('name') if isinstance(strings,list) and len(strings)==1
                     and isinstance(strings[0],dict) else None)
            target=ref.get('path');unique_leaf=False
            if (isinstance(sampler,str) and '.' not in sampler and isinstance(target,str)
                    and target.casefold().endswith('.'+sampler.casefold())):
                target_path,target_id=resolver.resolve(path,ref)
                matches=[entry for entry in resolver.inventory(target_path)['candidates']
                         if entry['path'].rsplit('.',1)[-1].casefold()==sampler.casefold()]
                unique_leaf=len(matches)==1 and matches[0]['id']==target_id
            shader_fallback=False
            try:
                verify_direct_source(doc,channel,ref,unique_leaf)
            except ValueError:
                # Some stored UV2 sources have a contradictory UV0 shader.
                # Show that shader's input only as an explicitly inexact
                # diagnostic; never treat it as the effective game source.
                if channel!=2:raise
                verify_direct_source(doc,0,ref,unique_leaf)
                shader_fallback=True
            result=child('Material')
            if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                raise ValueError('TexCoordSource requires an exact Texture')
            if shader_fallback:
                leaf_path,_=resolver.resolve(path,ref)
                target=ref.get('path');actual=result.get('name')
                if (not isinstance(target,str) or not target or not isinstance(actual,str) or not actual
                        or target.casefold() not in (actual.casefold(),
                            (Path(leaf_path).stem+'.'+actual).casefold())):
                    raise ValueError('TexCoordSource resolved Texture differs from saved reference')
                result['uv_channel']=0
                mark_approximate_uv(result,
                    'TexCoordSource: свойства выбирают UV2, сохранённый shader выбирает UV0; '
                    'показан только диагностический UV0, игровой выбор не подтверждён; '
                    'композиция материалов отключена')
            else:
                result['uv_channel']=channel
                result['uv0_exact']=channel==0
                result['uv_coordinate_exact']=True
                result['notes']=result['notes']+[
                    f'TexCoordSource: UV{channel} из соответствующего потока модели; '
                    'диагностическое отображение, игровое исполнение не проверено']
            return result
        if kind=='TexScaler':
            factor=scaler(doc,allow_offsets=True);result=child('Material')
            if result.get('fragment_layers') and result.get('uv_preview_approximate'):
                raise ValueError('TexScaler cannot transform an approximate fragment preview')
            if result.get('uv_channel',0)!=0:
                raise ValueError('TexScaler over a nonzero UV source is not yet confirmed')
            if tuple(result.get('uv_rotation',(1.,0.,0.,1.)))!=(1.,0.,0.,1.):
                raise ValueError('TexScaler over rotated UV is not yet confirmed')
            if result.get('uv_pan_rate',0.) or result.get('uv_rotation_animation') or result.get('uv_oscillation') or result.get('uv_chain'):
                raise ValueError('TexScaler over animated UV is not yet confirmed')
            ref=property_value(doc,'Material',{})
            native_size=result.get('native_size') if ref.get('class','').rsplit('.',1)[-1]=='Texture' else None
            offset=scaler_offset(doc,native_size)
            child_scale=result.get('uv_scale',(1.,1.));child_offset=result.get('uv_offset',(0.,0.))
            if any(child_offset) and factor!=(1.,1.):
                raise ValueError('Nested scale over shifted UV is not yet confirmed')
            result['uv_offset']=tuple(a*b+c for a,b,c in zip(child_scale,offset,child_offset))
            result['uv_scale']=tuple(a*b for a,b in zip(factor,result.get('uv_scale',(1.,1.))))
            if any(abs(v)>1e6 or abs(v)<1e-6 for v in result['uv_scale']):
                raise ValueError('Composed UV scale exceeds preview limits')
            result['notes']=result['notes']+['TexScaler: обратный масштаб UV0; offsets в пикселях исходной Texture']
            return result
        if kind=='TexOscillator':
            from material_oscillation import oscillator_parameters,repeat_needs_preview
            ref=property_value(doc,'Material',{})
            if not isinstance(ref,dict) or ref.get('class','').rsplit('.',1)[-1] not in ('Texture','TexRotator'):
                raise ValueError('TexOscillator requires a Texture or verified TexRotator')
            result=child('Material')
            axes=oscillator_parameters(doc,result.get('native_size'))
            approximate=repeat_needs_preview(axes)
            if ref.get('class','').rsplit('.',1)[-1]=='TexRotator':
                from material_chain import oscillator_rotation_chain
                result['uv_chain']=oscillator_rotation_chain(doc,ref,axes,result)
                result.pop('uv_rotation_animation',None)
                result.pop('uv_rotation',None);result.pop('uv_offset',None)
                result['notes']=result['notes']+['UV: oscillator → rotator, порядок проверен по metadata']
            else:
                result['uv_oscillation']=axes
                if approximate:result['uv_oscillation_preview']=True
            if approximate:
                mark_approximate_uv(result,
                    'TexOscillator stretch-repeat: приблизительная диагностическая модель; '
                    'округление угла и игровое время не подтверждены, композиция материалов отключена')
            result['notes']=result['notes']+[
                'TexOscillator: planar pan/stretch, float32; '
                'pivot в исходных texels; диагностические часы']
            return result
        if kind=='TexRotator':
            ref=property_value(doc,'Material',{})
            if isinstance(ref,dict) and ref.get('class','').rsplit('.',1)[-1]=='Combiner':
                from material_snapshot import cached_combiner_snapshot
                child_path,child_id=resolver.resolve(path,ref)
                if (child_path,child_id) in active:raise ValueError('Material cycle')
                child_entry,child_doc=read_limited(child_path,child_id)
                nested=property_value(child_doc,'Material2',{})
                if (property_value(child_doc,'CombineOperation',0)==5
                        and isinstance(nested,dict) and isinstance(nested.get('class'),str)
                        and nested['class'].rsplit('.',1)[-1]=='Combiner'):
                    from material_snapshot import isolated_rotator_combiner_sampler
                    texture_path,texture_id,nested_active,rotation,offset=isolated_rotator_combiner_sampler(
                        path,entry,doc,child_path,child_entry,child_doc,
                        resolver,read_limited,(*active,(child_path,child_id)))
                    result=evaluate(texture_path,dict(id=texture_id),nested_active)
                    if not result.get('uv0_exact') or 'stored_mip_sizes' not in result:
                        raise ValueError('Isolated sampler requires an exact direct Texture')
                    result['uv_rotation']=rotation
                    result['uv_offset']=offset
                    result['uv_snapshot']=True
                    result['isolated_sampler']=0
                    result['saved_frame_mode']='isolated'
                    mark_approximate_uv(result,
                        'TexRotator → Combiner: только отдельный sampler 0, не итоговый diffuse и не '
                        'результат материала; состояние Texture вместо Combiner, остальные ветви '
                        'и их alpha не вычисляются. Четыре сохранённые UV-матрицы могут относиться '
                        'к разным моментам; игровая анимация Texture, время и события не подтверждены; '
                        'композиция отключена')
                    return result
                result=child('Material')
                rotation,offset=cached_combiner_snapshot(
                    doc,path,entry,ref,child_path,child_entry,child_doc,result,
                    resolver,read_limited,(*active,(child_path,child_id)))
                result['uv_rotation']=rotation
                result['uv_offset']=offset
                result['uv0_exact']=False
                result['uv_coordinate_exact']=False
                result['uv_snapshot']=True
                result['notes']=result['notes']+[
                    'TexRotator → Combiner: только сохранённая UV-матрица поверх mip-сетки; '
                    'время и игровые размеры не подтверждены, композиция материалов отключена']
                return result
            if not isinstance(ref,dict) or ref.get('class','').rsplit('.',1)[-1]!='Texture':
                raise ValueError('TexRotator currently requires a direct Texture')
            result=child('Material')
            step=rotation_step(doc,result.get('native_size'),preview_precision=True)
            approximate=isinstance(step[1],dict) and step[1].get('preview_approximate',False)
            if approximate:
                mark_approximate_uv(result,
                    'TexRotator: приблизительная модель неоднозначной точности/часов; '
                    'игровая траектория не подтверждена, композиция материалов отключена')
            if step[0]=='matrix_rotation':
                result['uv_chain']=(step,)
                result['notes']=result['notes']+[
                    'TexRotator: полная 3×3 UV-матрица; XY после композиции, без perspective divide']
                return result
            if property_value(doc,'TexRotationType',0) in (1,2):
                animation=step[1]
                result['uv_rotation_animation']=animation
                result['notes']=result['notes']+[
                    'TexRotator: диагностическое время UV, не игровые часы; начальный t=0; '
                    +('постоянное вращение' if animation['mode']==1 else 'колебание, нулевая фаза')]
                return result
            rotation,offset,precision=fixed_rotation(doc,result.get('native_size'))
            result['uv_rotation']=rotation
            result['uv_offset']=offset
            result['notes']=result['notes']+[
                'TexRotator: фиксированный planar yaw; матрица проверена; угол '+precision]
            return result
        if kind=='TexPanner':
            rate,direction,approximate=panner_preview_parameters(doc)
            ref=property_value(doc,'Material',{})
            if not isinstance(ref,dict) or ref.get('class','').rsplit('.',1)[-1]!='Texture':
                raise ValueError('TexPanner currently requires a direct Texture')
            result=child('Material')
            if 'stored_mip_sizes' not in result:
                raise ValueError('TexPanner currently requires a direct Texture')
            result['uv_pan_rate']=rate
            result['uv_pan_direction']=direction
            if approximate:
                mark_approximate_uv(result,
                    'TexPanner Roll: приблизительная float32-модель; точность направления '
                    'и времени не подтверждена, композиция материалов отключена')
            else:
                result['notes']=result['notes']+[
                    'TexPanner: Pitch/Yaw → XY, Roll с нулевым индексом, нулевой скоростью '
                    'или инвариантными точностью и скоростью; '
                    'квантование 4 единицы; диагностическое время UV, не игровые часы; начальный t=0']
            return result
        result=child('Material')
        result['uv0_exact']=False
        result['uv_coordinate_exact']=False
        result['notes']=result['notes']+[kind+': показан исходный Material, без эффектов']
        return result

    return evaluate(path,reference)
