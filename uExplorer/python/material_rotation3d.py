"""Cached-matrix-gated spatial UV rotations, projected to XY only after composition."""
import math
from functools import lru_cache
from material_uv import f32
from material_rotation import direction,invariant_constant_velocity,rotation_pivot,stored_matrix
from texture_decode import property_value


def words(document,name):
    values=next((t.get('words') for t in document.get('tags',[]) if t['name']==name),[0,0,0])
    if (not isinstance(values,list) or len(values)!=3
            or any(not isinstance(v,int) or not 0<=v<=0xffffffff for v in values)):
        raise ValueError('Spatial TexRotator angle layout is not supported')
    signed=tuple(v if v<0x80000000 else v-0x100000000 for v in values)
    if any(abs(v)>65536 for v in signed):
        raise ValueError('Spatial TexRotator parameters exceed preview limits')
    return signed


def pivot_product(a,b):
    # Pivot construction has float32 products, unlike stage accumulation's
    # complete dot-product storage. Keep these two boundaries distinct.
    return tuple(tuple(f32(sum(f32(a[i][k]*b[k][j]) for k in range(3)))
                       for j in range(3)) for i in range(3))


def spatial_matrix(angles,pivot,precision):
    cp,sp=direction(angles[0]&65535,precision)
    cy,sy=direction(angles[1]&65535,precision)
    cr,sr=direction(angles[2]&65535,precision)
    matrix=((f32(cp*cy),f32(cp*sy),sp),
            (f32(f32(f32(sr*sp)*cy)-f32(cr*sy)),
             f32(f32(f32(sr*sp)*sy)+f32(cr*cy)),f32(-sr*cp)),
            (f32(-f32(f32(cr*sp)*cy)-f32(sr*sy)),
             f32(f32(sr*cy)-f32(f32(cr*sp)*sy)),f32(cr*cp)))
    if not any(pivot):return matrix
    u,v=pivot
    return pivot_product(pivot_product(((1.,0.,0.),(0.,1.,0.),(-u,-v,1.)),matrix),
                         ((1.,0.,0.),(0.,1.,0.),(u,v,1.)))


@lru_cache(maxsize=2)
def direction_table(precision):
    return tuple(direction(index*4,precision) for index in range(16384))


@lru_cache(maxsize=2)
def pitch_candidates(precision):
    result={}
    for index,(_,sine) in enumerate(direction_table(precision)):
        result.setdefault(sine,[]).append(index*4)
    return result


@lru_cache(maxsize=128)
def _precision_search(matrix,pivot):
    """Exhaust bounded table candidates; None means the pair budget was exceeded."""
    u,v=pivot
    groups=[(precision,pitch_candidates(precision).get(matrix[0][2],()))
            for precision in ('float32','double')]
    # Do not pick another table while any indistinguishable near-gimbal pitch
    # was excluded from the search.
    if any(abs(direction(pitch,precision)[0])<1e-5
           for precision,pitches in groups for pitch in pitches):
        return ()
    matches=[]
    for precision,pitches in groups:
        table=direction_table(precision)
        found=False
        for pitch in pitches:
            cp,sp=table[pitch>>2]
            su,sv=f32(sp*u),f32(sp*v)
            # These three entries isolate yaw and roll even with a pivot.
            yaw=[index*4 for index,(cy,sy) in enumerate(table)
                 if f32(f32(cp*cy)+su)==matrix[0][0]
                 and f32(f32(cp*sy)+sv)==matrix[0][1]]
            if not yaw:continue
            roll=[index*4 for index,(_,sr) in enumerate(table)
                  if f32(-sr*cp)==matrix[1][2]]
            if len(yaw)*len(roll)>256:return None
            for y in yaw:
                for r in roll:
                    if spatial_matrix((pitch,y,r),pivot,precision)==matrix:
                        found=True;break
                if found:break
            if found:break
        if found:matches.append(precision)
    return tuple(matches)


def cached_precisions(matrix,pivot):
    """Compare both complete tables and reject an incomplete candidate search."""
    result=_precision_search(tuple(tuple(row) for row in matrix),tuple(pivot))
    if result is None:
        raise ValueError('Spatial TexRotator precision candidate budget exceeded')
    return list(result)


def spatial_animation(document,native_size,*,preview_precision=False):
    mode=property_value(document,'TexRotationType',0)
    if mode not in (0,1,2):raise ValueError('Unsupported spatial TexRotator mode')
    base=words(document,'Rotation')
    rate=words(document,'OscillationRate') if mode==2 else (0,0,0)
    amplitude=words(document,'OscillationAmplitude') if mode==2 else (0,0,0)
    phase=words(document,'OscillationPhase') if mode==2 else (0,0,0)
    pivot=rotation_pivot(document,native_size)
    stored=stored_matrix(document)
    if any(row[3]!=0 for row in stored[:3]) or stored[3]!=[0.,0.,0.,1.]:
        raise ValueError('Spatial TexRotator requires an unprojected stored matrix')
    matrix=tuple(tuple(row[:3]) for row in stored[:3])
    if mode==0 or mode==2 and not any(amplitude) or mode==1 and not any(base):
        angles=(0,0,0) if mode==1 else base
        if not any(spatial_matrix(angles,pivot,p)==matrix for p in ('float32','double')):
            raise ValueError('Stationary spatial TexRotator stored matrix differs')
        return dict(fixed_matrix=matrix)
    matches=cached_precisions(matrix,pivot)
    approximate=False
    if (matches!=['float32']
            and not (matches==['double'] and mode==1 and invariant_constant_velocity(base))):
        if not preview_precision or not matches:
            raise ValueError('Spatial TexRotator cached precision is ambiguous or unsupported')
        approximate=True
    result=dict(mode=mode,base=base,rate=rate,amplitude=amplitude,phase=phase,
                pivot=pivot,precision='float32' if len(matches)>1 else matches[0])
    if approximate:result['preview_approximate']=True
    return result


def spatial_at(animation,seconds):
    if not math.isfinite(seconds) or not 0<=seconds<=3600:
        raise ValueError('Material preview time must be within 0..3600 seconds')
    if 'fixed_matrix' in animation:return animation['fixed_matrix']
    time=f32(seconds)
    if animation['mode']==1:
        angles=[int(f32(v*time)) for v in animation['base']]
    else:
        angles=[]
        for base,rate,amplitude,phase in zip(animation['base'],animation['rate'],
                                             animation['amplitude'],animation['phase']):
            fraction=f32(rate*time/65535)
            wave=math.sin((fraction-math.floor(fraction)+phase)*math.tau)
            angles.append(base+int(f32(wave*amplitude)))
    return spatial_matrix(angles,animation['pivot'],animation['precision'])
