"""Bounded row-vector UV composition in saved modifier order."""
from material_uv import f32,panner_rate,panner_direction,panner_offset,panner_preview_parameters
from material_math import scaler,scaler_offset
from material_rotation import rotation_at,rotation_step
from material_oscillation import oscillator_at,oscillator_parameters,repeat_needs_preview
from material_coordinates import chain_channel,verify_coordinate_shader
from texture_decode import property_value


def chain_matrix(steps,seconds):
    if not 1<=len(steps)<=32:raise ValueError('UV chain exceeds preview limits')
    matrix=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
    for kind,value in steps:
        if kind in ('oscillator','oscillator_preview'):
            (u,v),(x,y)=oscillator_at(value,seconds,preview_repeat=kind=='oscillator_preview')
            next_matrix=((u,0.,0.),(0.,v,0.),(x,y,1.))
        elif kind in ('panner','panner_preview'):
            rate,direction=value
            x,y=(panner_offset(rate,seconds,c) for c in direction)
            next_matrix=((1.,0.,0.),(0.,1.,0.),(x,y,1.))
        elif kind=='matrix_rotation':
            from material_rotation3d import spatial_at
            next_matrix=spatial_at(value,seconds)
        elif kind in ('rotation','fixed'):
            (a,b,c,d),(x,y)=rotation_at(value,seconds) if kind=='rotation' else value
            next_matrix=((a,b,0.),(c,d,0.),(x,y,1.))
        else:raise ValueError('Unsupported UV chain step')
        # Native stage accumulation stores each complete dot product to float32.
        matrix=tuple(tuple(f32(sum(matrix[i][k]*next_matrix[k][j] for k in range(3)))
                           for j in range(3)) for i in range(3))
    return matrix


def oscillator_rotation_chain(document,reference,axes,surface):
    strings=document.get('strings',[])
    if len(strings)!=1 or not isinstance(strings[0],dict):
        raise ValueError('Nested UV requires one verified sampler chain')
    order=strings[0].get('values',[])
    expected=(document.get('path',''),reference.get('path',''))
    if len(order)!=2 or any(not name or not (stored.casefold()==name.casefold()
            or stored.casefold().endswith('.'+name.casefold())) for stored,name in zip(order,expected)):
        raise ValueError('Nested UV modifier order does not match stored shader metadata')
    if surface.get('uv_rotation_animation'):
        rotation=('rotation',surface['uv_rotation_animation'])
    elif 'uv_rotation' in surface:
        rotation=('fixed',(surface['uv_rotation'],surface.get('uv_offset',(0.,0.))))
    else:raise ValueError('Nested oscillator requires a verified rotation')
    return ((('oscillator_preview' if repeat_needs_preview(axes) else 'oscillator'),axes),rotation)


def panner_scaler_chain(document,child,surface):
    """Two direct stages only, in the saved sampler's explicit order."""
    kinds=tuple(d.get('class','').rsplit('.',1)[-1] for d in (document,child))
    if kinds not in (('TexPanner','TexScaler'),('TexScaler','TexPanner')):
        raise ValueError('UV chain requires one panner and one scaler')
    leaf=property_value(child,'Material',{})
    if not isinstance(leaf,dict) or leaf.get('class','').rsplit('.',1)[-1]!='Texture':
        raise ValueError('Panner/scaler chain requires a direct Texture leaf')
    strings=document.get('strings',[])
    child_strings=child.get('strings',[])
    if (not isinstance(strings,list) or len(strings)!=1 or not isinstance(strings[0],dict)
            or not isinstance(child_strings,list) or len(child_strings)!=1
            or not isinstance(child_strings[0],dict)):
        raise ValueError('Panner/scaler requires one verified sampler')
    order=strings[0].get('values')
    names=[d.get('path') for d in (document,child)]
    if (not isinstance(order,list) or len(order)!=2
            or any(not isinstance(name,str) or not name or not isinstance(saved,str)
                   or not (saved.casefold()==name.casefold()
                           or saved.casefold().endswith('.'+name.casefold()))
                   for saved,name in zip(order,names))
            or child_strings[0].get('values')!=order[1:]
            or strings[0].get('name')!=child_strings[0].get('name')):
        raise ValueError('Panner/scaler sampler or modifier order differs')
    sampler=strings[0].get('name')
    target=leaf.get('path')
    if (not isinstance(sampler,str) or not isinstance(target,str) or not target
            or not (sampler.casefold()==target.casefold()
                    or sampler.casefold().endswith('.'+target.casefold()))):
        raise ValueError('Panner/scaler sampler does not match Texture leaf')
    if not surface.get('uv0_exact') or surface.get('fragment_layers'):
        raise ValueError('Panner/scaler requires an exact Texture surface')
    steps=[]
    for kind,doc in zip(kinds,(document,child)):
        if kind=='TexPanner':
            steps.append(('panner',(panner_rate(doc),panner_direction(doc))))
        else:
            u,v=scaler(doc,allow_offsets=True)
            offset=scaler_offset(doc,surface.get('native_size'))
            steps.append(('fixed',((u,0.,0.,v),offset)))
    return tuple(steps)


def verify_sampler_chain(documents,surface):
    """Validate every saved sampler suffix and its direct Texture binding."""
    if not 2<=len(documents)<=32:
        raise ValueError('UV chain requires 2..32 modifiers')
    if not surface.get('uv0_exact') or surface.get('fragment_layers'):
        raise ValueError('UV chain requires an exact direct Texture')
    channel=chain_channel(documents)
    has_source=any(d.get('class','').rsplit('.',1)[-1]=='TexCoordSource' for d in documents)
    if has_source:
        source_index=next(i for i,d in enumerate(documents)
                          if d.get('class','').rsplit('.',1)[-1]=='TexCoordSource')
        for index,doc in enumerate(documents):
            strings=doc.get('strings')
            has_matrix=(isinstance(strings,list) and len(strings)==1
                        and isinstance(strings[0],dict) and bool(strings[0].get('values')))
            # A child below the source is cached as a standalone UV0 material;
            # the outer shader applies the selected source to the whole suffix.
            verify_coordinate_shader(doc,channel if index<=source_index else 0,
                                     requires_matrix=has_matrix)
    def matches(saved,name):
        return (isinstance(saved,str) and isinstance(name,str) and bool(name)
                and (saved.casefold()==name.casefold()
                     or saved.casefold().endswith('.'+name.casefold())))
    first=documents[0].get('strings')
    if not isinstance(first,list) or len(first)!=1 or not isinstance(first[0],dict):
        raise ValueError('UV chain requires one saved sampler')
    order=first[0].get('values')
    sampler=first[0].get('name')
    matrix_documents=[doc for doc in documents
                      if doc.get('class','').rsplit('.',1)[-1]!='TexCoordSource']
    if not isinstance(order,list) or len(order)!=len(matrix_documents):
        raise ValueError('UV chain modifier count differs from saved sampler')
    position=0
    for index,doc in enumerate(documents):
        strings=doc.get('strings')
        if (not isinstance(strings,list) or len(strings)!=1
                or not isinstance(strings[0],dict)
                or strings[0].get('name')!=sampler
                or strings[0].get('values')!=order[position:]):
            raise ValueError('UV chain sampler or modifier order differs')
        if doc.get('class','').rsplit('.',1)[-1]!='TexCoordSource':
            if not matches(order[position],doc.get('path')):
                raise ValueError('UV chain sampler or modifier order differs')
            position+=1
        ref=property_value(doc,'Material',{})
        if not isinstance(ref,dict) or not ref.get('id'):
            raise ValueError('UV chain has no Material reference')
        if index+1<len(documents):
            expected=(documents[index+1].get('path') if has_source else ref.get('path'))
            saved=(ref.get('path') if has_source else order[index+1])
            if not matches(saved,expected):
                raise ValueError('UV chain Material reference differs from saved order')
        elif (ref.get('class','').rsplit('.',1)[-1]!='Texture'
              or not matches(sampler,ref.get('path'))):
            raise ValueError('UV chain sampler does not match direct Texture leaf')


def modifier_chain(documents,surface):
    """Validate every suffix of one saved sampler chain before composing it."""
    verify_sampler_chain(documents,surface)
    size=surface.get('native_size');steps=[]
    for doc in documents:
        kind=doc.get('class','').rsplit('.',1)[-1]
        if kind=='TexPanner':
            rate,direction,approximate=panner_preview_parameters(doc)
            step=('panner_preview' if approximate else 'panner',(rate,direction))
        elif kind=='TexScaler':
            u,v=scaler(doc,allow_offsets=True)
            step=('fixed',((u,0.,0.,v),scaler_offset(doc,size)))
        elif kind=='TexOscillator':
            axes=oscillator_parameters(doc,size)
            step=('oscillator_preview' if repeat_needs_preview(axes) else 'oscillator',axes)
        elif kind=='TexRotator':
            step=rotation_step(doc,size,preview_precision=True)
        elif kind=='TexCoordSource':
            # The saved sampler omits this source: it chooses the input
            # stream and must not introduce an extra matrix multiplication.
            continue
        else:raise ValueError('Unsupported UV chain modifier')
        steps.append(step)
    return tuple(steps)
