"""Bounded diagnostic TexPanner time using quantized Pitch/Yaw projected to XY."""
import math
import struct
from material_math import material_float
from texture_decode import property_value


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


class UnverifiedRoll(ValueError):
    """The direction is valid, but the observed precision models disagree."""


def panner_direction(document,*,preview_roll=False):
    direction=next((t for t in document.get('tags',[]) if t['name']=='PanDirection'),None)
    words=[0,0,0]
    if direction is not None:
        words=direction.get('words')
        if (not isinstance(words,list) or len(words)!=3
                or any(not isinstance(v,int) or not 0<=v<=0xffffffff for v in words)):
            raise ValueError('TexPanner direction layout is not supported')
    # Rotator lookup discards two low angle bits and wraps a 16384-entry table.
    # Preserve float32 angle generation; snapping near-cardinal values changes
    # the wrapped phase (a tiny negative component can round to offset 1024).
    def sine(angle,precision='float32'):
        index=(angle>>2)&16383
        angle=2*index*(f32(math.pi) if precision=='float32' else math.pi)/16384
        return f32(math.sin(f32(angle) if precision=='float32' else angle))
    pitch_cos=sine(words[0]+16384)
    result=(f32(pitch_cos*sine(words[1]+16384)),f32(pitch_cos*sine(words[1])))
    if (words[2]>>2)&16383:
        # FRotator::Vector's forward axis does not change under Roll. Cached
        # panners nevertheless show different angle tables and intermediate
        # rounding. Admit a moving nonzero Roll only when both observed tables
        # have bit-identical XY and multiplication by rate cannot round:
        # rate is an integral power of two, >=1 and within preview limits.
        cp=sine(words[0]+16384,'double')
        other=(f32(cp*sine(words[1]+16384,'double')),f32(cp*sine(words[1],'double')))
        rate=material_float(document,'PanRate',f32(.1))
        # A stationary panner has zero displacement for both tables, even
        # where their direction components differ. Do not use this exception
        # for any nonzero velocity, including float32 subnormals.
        if rate==0.:
            return result
        if (struct.pack('<2f',*result)!=struct.pack('<2f',*other)
                or not 1<=abs(rate)<=10000 or math.frexp(abs(rate))[0]!=.5):
            if not preview_roll:
                raise UnverifiedRoll('TexPanner nonzero Roll requires precision-invariant direction and rate')
    return result


def panner_rate(document,*,preview_roll=False):
    panner_direction(document,preview_roll=preview_roll)
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('TexPanner requires unprojected UV0')
    rate=material_float(document,'PanRate',f32(.1))
    if abs(rate)>10000:raise ValueError('TexPanner rate exceeds preview limits')
    return rate


def panner_preview_parameters(document):
    """Expose a marked float32 model when Roll precision is unresolved."""
    try:
        return panner_rate(document),panner_direction(document),False
    except UnverifiedRoll:
        return (panner_rate(document,preview_roll=True),
                panner_direction(document,preview_roll=True),True)


def panner_offset(rate,seconds,component=1.):
    if not math.isfinite(seconds) or not 0<=seconds<=3600:
        raise ValueError('Material preview time must be within 0..3600 seconds')
    if not math.isfinite(rate) or abs(rate)>10000:
        raise ValueError('TexPanner rate exceeds preview limits')
    if not math.isfinite(component) or abs(component)>1:
        raise ValueError('TexPanner direction exceeds unit limits')
    # Preserve both observed float32 boundaries: distance first, then the
    # directional phase. Subtract floor and scale the wrapped phase by 1024.
    distance=f32(f32(rate)*f32(seconds))
    phase=f32(distance*f32(component)/1024)
    return f32((phase-math.floor(phase))*1024)


def timed_uv(geometry,seconds):
    from material_rotation import rotation_at
    from material_oscillation import oscillator_at
    from material_chain import chain_matrix
    rates={slot:texture.get('uv_pan_rate',0.) for slot,texture in geometry.get('textures',{}).items()}
    shifts={slot:tuple(panner_offset(rate,seconds,c) for c in
        geometry['textures'][slot].get('uv_pan_direction',(1.,0.))) for slot,rate in rates.items()}
    result=[]
    rotations={slot:rotation_at(t['uv_rotation_animation'],seconds)
               for slot,t in geometry.get('textures',{}).items() if t.get('uv_rotation_animation')}
    oscillations={slot:oscillator_at(t['uv_oscillation'],seconds,
                                    preview_repeat=t.get('uv_oscillation_preview',False))
                   for slot,t in geometry.get('textures',{}).items() if t.get('uv_oscillation')}
    chains={slot:chain_matrix(t['uv_chain'],seconds)
            for slot,t in geometry.get('textures',{}).items() if t.get('uv_chain')}
    for index,face in enumerate(geometry.get('uv_base',geometry.get('uv',[]))):
        ou,ov=shifts.get(geometry['face_materials'][index],(0.,0.))
        values=[(u+ou,v+ov) for u,v in face]
        oscillation=oscillations.get(geometry['face_materials'][index])
        if oscillation:
            (su,sv),(x,y)=oscillation
            values=[(u*su+x,v*sv+y) for u,v in values]
        rotation=rotations.get(geometry['face_materials'][index])
        if rotation:
            (a,b,c,d),(x,y)=rotation
            values=[(u*a+v*c+x,u*b+v*d+y) for u,v in values]
        matrix=chains.get(geometry['face_materials'][index])
        if matrix:
            values=[(u*matrix[0][0]+v*matrix[1][0]+matrix[2][0],
                     u*matrix[0][1]+v*matrix[1][1]+matrix[2][1]) for u,v in values]
        if any(not math.isfinite(x) or abs(x)>1e6 for pair in values for x in pair):
            raise ValueError('Animated UV coordinates exceed preview limits')
        result.append(values)
    return result


def has_timed_uv(texture):
    def animated(surface):
        return bool(surface.get('uv_pan_rate',0.) or surface.get('uv_rotation_animation')
                    or surface.get('uv_oscillation') or surface.get('uv_chain'))
    return bool(animated(texture) or texture.get('fragment_independent_uv') and
                any(animated(layer) for layer in texture.get('fragment_layers',())))


def timed_fragment_uv(geometry,seconds):
    """Transform the same saved input separately for each proven sampler."""
    inputs=geometry.get('uv_input')
    fragment_inputs=geometry.get('fragment_inputs')
    slots=geometry.get('face_materials',[])
    if (inputs is None or len(inputs)!=len(slots)
            or fragment_inputs is not None and len(fragment_inputs)!=len(slots)):
        raise ValueError('Independent fragment UV input topology differs')
    result=[None]*len(inputs)
    by_slot={}
    for index,slot in enumerate(slots):by_slot.setdefault(slot,[]).append(index)
    for slot,texture in geometry.get('textures',{}).items():
        if not texture.get('fragment_independent_uv'):continue
        layers=texture.get('fragment_layers',[])
        if len(layers)!=3:raise ValueError('Independent fragment requires three sampler layers')
        indices=by_slot.get(slot,[])
        if fragment_inputs is not None and any(
                not isinstance(fragment_inputs[index],(list,tuple))
                or len(fragment_inputs[index])!=3
                or any(not isinstance(face,(list,tuple)) or len(face)!=len(inputs[index])
                       for face in fragment_inputs[index]) for index in indices):
            raise ValueError('Independent fragment UV input topology differs')
        transformed=[]
        for layer_index,layer in enumerate(layers):
            if layer_index==2 and texture.get('fragment_operation') in (2,3,7):
                transformed.append(transformed[0])
                continue
            su,sv=layer.get('uv_scale',(1.,1.))
            ou,ov=layer.get('uv_offset',(0.,0.))
            a,b,c,d=layer.get('uv_rotation',(1.,0.,0.,1.))
            base=[]
            for index in indices:
                face=(fragment_inputs[index][layer_index] if fragment_inputs is not None else inputs[index])
                base.append([(u*su*a+v*sv*c+ou,u*su*b+v*sv*d+ov) for u,v in face])
            if any(not math.isfinite(value) or abs(value)>1e6
                   for face in base for pair in face for value in pair):
                raise ValueError('Transformed fragment UV coordinates exceed preview limits')
            transformed.append(timed_uv(dict(uv_base=base,face_materials=[0]*len(base),
                                             textures={0:layer}),seconds))
        for offset,index in enumerate(indices):
            result[index]=tuple(layer[offset] for layer in transformed)
    return result
