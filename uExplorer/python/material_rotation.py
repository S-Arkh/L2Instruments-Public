"""Fixed planar rotation, gated by the complete stored matrix."""
import math
from functools import lru_cache
from animation_decode import floats
from material_uv import f32
from texture_decode import property_value


def rotation_words(document,name='Rotation',fixed=False):
    words=next((t.get('words') for t in document.get('tags',[]) if t['name']==name),[0,0,0])
    if (not isinstance(words,list) or len(words)!=3
            or any(not isinstance(v,int) or not 0<=v<=0xffffffff for v in words)):
        raise ValueError('TexRotator angle layout is not supported')
    # Only fixed angles may discard the table's low bits here. A small
    # nonzero angular velocity can grow into nonplanar rotation over time.
    mask=0xfffc if fixed else 0xffffffff
    if words[0]&mask or words[2]&mask:
        raise ValueError('TexRotator currently requires zero Pitch/Roll')
    return words


def rotation_pivot(document,native_size):
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('TexRotator requires unprojected UV0')
    def scalar(name):
        tag=next((t for t in document.get('tags',[]) if t['name']==name),None)
        value=floats([tag['bits']],1)[0] if tag else 0.
        if not math.isfinite(value) or abs(value)>1e6:
            raise ValueError('TexRotator pivot exceeds preview limits')
        return value
    u,v=scalar('UOffset'),scalar('VOffset')
    if not native_size or len(native_size)!=2 or any(n<=0 for n in native_size):
        raise ValueError('TexRotator requires original texture dimensions')
    return f32(u/native_size[0]),f32(v/native_size[1])


def stored_matrix(document):
    try:
        matrix=next(t for t in document['tags'] if t['name']=='M')
        planes={p['name']:{a['name']:floats([a['bits']],1)[0]
                          for a in p['members']} for p in matrix['members']}
        stored=[[planes[p][a] for a in ('X','Y','Z','W')]
                for p in ('XPlane','YPlane','ZPlane','WPlane')]
    except (StopIteration,KeyError,TypeError,ValueError) as error:
        raise ValueError('TexRotator requires a complete stored matrix') from error
    return stored


def direction(angle,precision):
    def sine(a):
        value=2*((a>>2)&16383)*(f32(math.pi) if precision=='float32' else math.pi)/16384
        return f32(math.sin(f32(value) if precision=='float32' else value))
    return sine(angle+16384),sine(angle)


def rotation_matrix(c,s,pivot):
    u,v=pivot
    # Native translation composition rounds each product and the dot sum
    # before adding the pivot. Sequential pivot-minus-product is different.
    x=f32(u+f32(f32(-u*c)+f32(v*s)))
    y=f32(v+f32(f32(-u*s)-f32(v*c)))
    return [[c,s,0.,0.],[-s,c,0.,0.],[x,y,1.,0.],[0.,0.,0.,1.]]


def fixed_rotation(document,native_size):
    if property_value(document,'TexRotationType',0)!=0:
        raise ValueError('TexRotator currently requires fixed rotation')
    words=rotation_words(document,fixed=True)
    pivot=rotation_pivot(document,native_size)
    stored=stored_matrix(document)
    for precision in ('float32','double'):
        c,s=direction(words[1],precision)
        calculated=rotation_matrix(c,s,pivot)
        if calculated==stored:
            return (c,s,-s,c), tuple(calculated[2][:2]), precision
    raise ValueError('TexRotator stored matrix does not match verified fixed rotation')


@lru_cache(maxsize=2)
def direction_indices(precision):
    return {direction(index*4,precision):index*4 for index in range(16384)}


def invariant_constant_velocity(values):
    """Power-of-two integer speeds multiply float32 time without rounding."""
    return all(value==0 or (abs(value)&(abs(value)-1))==0 for value in values)


def animated_rotation(document,native_size,*,preview_precision=False):
    mode=property_value(document,'TexRotationType',0)
    if mode not in (1,2):raise ValueError('Unsupported animated TexRotator mode')
    def signed(name):
        value=rotation_words(document,name)[1]
        value=value if value<0x80000000 else value-0x100000000
        if abs(value)>65536:raise ValueError('TexRotator angle/rate exceeds preview limits')
        return value
    yaw=signed('Rotation')
    rate=signed('OscillationRate') if mode==2 else 0
    amplitude=signed('OscillationAmplitude') if mode==2 else 0
    if mode==2 and any(rotation_words(document,'OscillationPhase')):
        raise ValueError('TexRotator oscillation phase is not yet verified')
    pivot=rotation_pivot(document,native_size)
    stored=stored_matrix(document)
    # TR_Constant uses Rotation as angular velocity. With zero velocity both
    # precision tables produce identity for the entire trajectory, not merely
    # at the cached instant. Still require the complete cached identity.
    if mode==1 and yaw==0:
        if stored!=rotation_matrix(1.,0.,pivot):
            raise ValueError('Stationary TexRotator requires a stored identity matrix')
        return dict(mode=mode,yaw=0,rate=0,amplitude=0,pivot=pivot,precision='invariant')
    matches=[]
    for precision in ('float32','double'):
        c,s=stored[0][:2]
        if (c,s) in direction_indices(precision) and rotation_matrix(c,s,pivot)==stored:
            matches.append(precision)
    # A cardinal matrix may fit both tables: it cannot select a precision
    # for the rest of an animated trajectory.
    approximate=False
    if len(matches)!=1:
        if not preview_precision or not matches:
            raise ValueError('Animated TexRotator precision is ambiguous or matrix is unsupported')
        # Explicit diagnostic choice only; a cached cardinal angle cannot
        # identify the table used by a later moving angle.
        matches=['float32']
        approximate=True
    if (matches[0]!='float32'
            and not (mode==1 and invariant_constant_velocity((yaw,)))):
        if not preview_precision:
            raise ValueError('Animated TexRotator double-angle clock arithmetic is not yet verified')
        approximate=True
    result=dict(mode=mode,yaw=yaw,rate=rate,amplitude=amplitude,pivot=pivot,
                precision=matches[0])
    if approximate:result['preview_approximate']=True
    return result


def rotation_at(animation,seconds):
    if not math.isfinite(seconds) or not 0<=seconds<=3600:
        raise ValueError('Material preview time must be within 0..3600 seconds')
    if animation['precision']=='invariant':
        return (1.,0.,0.,1.),(0.,0.)
    time=f32(seconds)
    if animation['mode']==1:
        angle=int(f32(animation['yaw']*time))
    else:
        phase=f32(animation['rate']*time/65535)
        wave=math.sin((phase-math.floor(phase))*math.tau)
        angle=animation['yaw']+int(f32(wave*animation['amplitude']))
    c,s=direction(angle&65535,animation['precision'])
    matrix=rotation_matrix(c,s,animation['pivot'])
    return (c,s,-s,c),tuple(matrix[2][:2])


def rotation_step(document,native_size,*,preview_precision=False):
    try:
        if property_value(document,'TexRotationType',0) in (1,2):
            return ('rotation',animated_rotation(document,native_size))
        rotation,offset,_=fixed_rotation(document,native_size)
        return ('fixed',(rotation,offset))
    except ValueError:
        from material_rotation3d import spatial_animation
        try:
            return ('matrix_rotation',spatial_animation(document,native_size))
        except ValueError:
            if not preview_precision:raise
            try:
                return ('rotation',animated_rotation(document,native_size,preview_precision=True))
            except ValueError:
                return ('matrix_rotation',spatial_animation(document,native_size,preview_precision=True))
