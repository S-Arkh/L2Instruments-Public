"""Deterministic TexOscillator arithmetic; jitter requires unavailable state."""
import math
from material_math import material_float
from material_uv import f32
from texture_decode import property_value


class UnverifiedOscillatorPivot(ValueError):
    """Pivot dimensions are not known for this material."""


class StatefulOscillation(ValueError):
    """Jitter depends on runtime random state."""


def oscillator_parameters(document,native_size=None):
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('TexOscillator requires unprojected UV0')
    axes=[]
    for axis in ('U','V'):
        mode=property_value(document,axis+'OscillationType',0)
        if mode==3:
            raise StatefulOscillation('TexOscillator jitter requires native random state')
        if mode not in (0,1,2):
            raise ValueError('TexOscillator jitter requires native random state')
        values=[material_float(document,axis+name,default) for name,default in
                (('OscillationRate',1.),('OscillationPhase',0.),
                 ('OscillationAmplitude',f32(.1)))]
        if any(not math.isfinite(v) or abs(v)>10000 for v in values):
            raise ValueError('TexOscillator parameters exceed preview limits')
        pivot=material_float(document,axis+'Offset',0.)
        if not math.isfinite(pivot) or abs(pivot)>1e6:
            raise ValueError('TexOscillator pivot exceeds preview limits')
        if pivot:
            if not native_size or len(native_size)!=2 or any(n<=0 for n in native_size):
                raise UnverifiedOscillatorPivot('TexOscillator pivot requires original texture dimensions')
            axes.append((mode,*values,f32(pivot/native_size[len(axes)])))
        else:axes.append((mode,*values))
    return tuple(axes)


def verified_oscillator_parameters(document,native_size=None):
    """Accept stretch-repeat only when both observed models are stationary."""
    axes=oscillator_parameters(document,native_size)
    if repeat_needs_preview(axes):
        raise ValueError('TexOscillator nonzero stretch-repeat calibration is not yet complete')
    return axes


def repeat_needs_preview(axes):
    """Nonzero repeat may require an unverified angle-precision choice."""
    return any(axis[0]==2 and axis[3]!=0. and (axis[1]!=0. or axis[2]!=0.)
               for axis in axes)


def oscillator_at(axes,seconds,*,preview_repeat=False):
    if not math.isfinite(seconds) or not 0<=seconds<=3600:
        raise ValueError('Material preview time must be within 0..3600 seconds')
    if any(axis[0] not in (0,1,2) for axis in axes):
        raise ValueError('TexOscillator jitter requires native random state')
    if repeat_needs_preview(axes) and not preview_repeat:
        raise ValueError('TexOscillator nonzero stretch-repeat calibration is not yet complete')
    scale=[];offset=[]
    for axis in axes:
        mode,rate,phase,amplitude=axis[:4]
        if mode==2:
            if amplitude==0. or rate==0. and phase==0.:
                # Both cases are stationary for the considered models.
                wave=0.
            else:
                # Diagnostic choice, not a verified rounding rule. Stored
                # matrices at independently inferred times support the
                # quarter-cycle wave but do not distinguish angle precision.
                time=f32(f32(seconds)*rate)
                fraction=time-math.floor(time)
                angle=f32(fraction*f32(math.pi/2)+phase*f32(math.tau))
                wave=f32(math.sin(angle)*amplitude)
        else:
            time=f32(f32(seconds)*rate)
            fraction=time-math.floor(time)
            angle=f32(fraction*f32(math.tau)+phase*f32(math.tau))
            wave=f32(math.sin(angle)*amplitude)
        scale.append(f32(1.+wave) if mode else 1.)
        offset.append(wave if mode==0 else 0.)
    # Native matrix composition runs for both axes when either pivot is set.
    # Even a pan's cancelling translations can change its final float32 bits.
    if any(len(axis)==5 and axis[4] for axis in axes):
        offset=[f32(f32(f32(-(axis[4] if len(axis)==5 else 0.)*s)+o)
                    +(axis[4] if len(axis)==5 else 0.)) for axis,s,o in zip(axes,scale,offset)]
    return tuple(scale),tuple(offset)
