"""Bounded GPU-only combinations of individually sampled direct textures."""
from material_shader import direct_masked_add
from material_lerp import direct_lerp,direct_masked_add_mask
from material_multisample import independent_multiply_shader,independent_multiply_profile
from texture_decode import property_value


def fragment_surface(document,surfaces,*,independent=False):
    if not (independent and independent_multiply_shader(document)
            or not independent and (direct_masked_add(document) or direct_lerp(document)
                                    or direct_masked_add_mask(document))):
        raise ValueError('Different mip grids require a verified direct-texture shader route')
    first=surfaces['Material1'];second=surfaces['Material2']
    mask=surfaces.get('Mask',first)
    layers=[]
    profile=independent_multiply_profile(document) if independent else None
    for index,surface in enumerate((first,second,mask)):
        channel=surface.get('uv_channel',0)
        if (type(channel) is not int or not 0<=channel<=7
                or not surface.get('uv_coordinate_exact',surface.get('uv0_exact',True))
                or channel==0 and not surface.get('uv0_exact',True)
                or surface.get('fragment_layers') or surface.get('uv_snapshot')
                or surface.get('uv_preview_approximate')
                or independent and channel!=profile[0 if index==2 else index][0]):
            raise ValueError('Fragment material requires confirmed matching UV input surfaces')
        if not independent and (channel!=0 or not surface.get('uv0_exact',True)):
            raise ValueError('Fragment material currently requires direct unmodified UV0')
        if (not independent and (surface.get('uv_chain') or surface.get('uv_rotation_animation')
                or surface.get('uv_oscillation') or surface.get('uv_pan_rate',0.)
                or tuple(surface.get('uv_scale',(1.,1.)))!=(1.,1.)
                or any(surface.get('uv_offset',(0.,0.)))
                or tuple(surface.get('uv_rotation',(1.,0.,0.,1.)))!=(1.,0.,0.,1.))):
            raise ValueError('Fragment material currently requires direct unmodified UV0')
        width,height=surface['width'],surface['height']
        if not 1<=width<=512 or not 1<=height<=512 or len(surface['pixels'])!=width*height*4:
            raise ValueError('Invalid fragment material texture storage')
        layers.append(dict(surface) if independent else
                      dict(width=width,height=height,pixels=surface['pixels'],wrap=surface.get('wrap',(0,0))))
    base=dict(first) if independent else dict(width=first['width'],height=first['height'],
        pixels=first['pixels'],wrap=first.get('wrap',(0,0)),uv_scale=(1.,1.))
    base.update(uv0_exact=False,uv_coordinate_exact=False,fragment_layers=layers,
                fragment_operation=property_value(document,'CombineOperation',0),
                fragment_alpha=property_value(document,'AlphaOperation',0),
                fragment_invert=bool(property_value(document,'InvertMask',False)))
    if independent:base['fragment_independent_uv']=True
    return base


def direct_uv0_layers(first,second):
    """Keep exact direct Texture inputs on separate grids."""
    layers=[]
    for surface in (first,second,first):
        if (not surface.get('uv0_exact') or not surface.get('uv_coordinate_exact',True)
                or surface.get('uv_channel',0)!=0 or surface.get('fragment_layers')
                or surface.get('uv_snapshot') or surface.get('uv_preview_approximate')
                or surface.get('uv_chain') or surface.get('uv_rotation_animation')
                or surface.get('uv_oscillation') or surface.get('uv_pan_rate',0.)
                or tuple(surface.get('uv_scale',(1.,1.)))!=(1.,1.)
                or tuple(surface.get('uv_offset',(0.,0.)))!=(0.,0.)
                or tuple(surface.get('uv_rotation',(1.,0.,0.,1.)))!=(1.,0.,0.,1.)):
            raise ValueError('Direct fragment requires unmodified direct UV0 textures')
        width,height=surface['width'],surface['height']
        if not 1<=width<=512 or not 1<=height<=512 or len(surface['pixels'])!=width*height*4:
            raise ValueError('Invalid direct fragment texture storage')
        layers.append(dict(surface))
    return layers


def panner_combiner_surface(first,second,color,alpha,multiplier,rate,direction):
    """Keep direct texture grids independent and apply the same diagnostic pan."""
    if (color,alpha,multiplier) not in ((2,0,2),(2,1,2),(3,1,1)):
        raise ValueError('Unsupported Panner Combiner fragment operation')
    layers=[dict(layer,uv_pan_rate=rate,uv_pan_direction=direction)
            for layer in direct_uv0_layers(first,second)]
    result=dict(layers[0])
    result.update(uv0_exact=False,uv_coordinate_exact=False,fragment_layers=layers,
                  fragment_independent_uv=True,fragment_operation=color,fragment_alpha=alpha,
                  fragment_multiplier=multiplier,fragment_invert=False)
    return result


def alpha_modulate_surface(first,second):
    """Preview the recognized saved RGB/alpha expression, excluding mFactor."""
    layers=direct_uv0_layers(first,second)
    result=dict(layers[0])
    result.update(uv0_exact=False,uv_coordinate_exact=False,fragment_layers=layers,
                  fragment_independent_uv=True,fragment_operation=7,fragment_alpha=0,
                  fragment_multiplier=1,fragment_invert=False)
    return result


VERTEX_SHADER = """#version 120
attribute vec2 secondUV;
attribute vec2 maskUV;
varying vec2 uv0;
varying vec2 uv1;
varying vec2 uv2;
void main() { gl_Position=ftransform(); uv0=gl_MultiTexCoord0.xy; uv1=secondUV; uv2=maskUV; }
"""

FRAGMENT_SHADER = """#version 120
varying vec2 uv0;
varying vec2 uv1;
varying vec2 uv2;
uniform sampler2D firstMap;
uniform sampler2D secondMap;
uniform sampler2D maskMap;
uniform int operation;
uniform int alphaOperation;
uniform int invertMask;
uniform float multiplier;
void main() {
    vec4 a=texture2D(firstMap,uv0);
    vec4 b=texture2D(secondMap,uv1);
    vec4 m=texture2D(maskMap,uv2);
    float maskAlpha=invertMask!=0 ? 1.0-m.a : m.a;
    vec3 rgb=operation==2 ? a.rgb*b.rgb*multiplier : (operation==3 ? a.rgb+b.rgb :
             (operation==7 ? b.rgb*a.a : (operation==5 ? mix(a.rgb,b.rgb,maskAlpha) : b.rgb+b.a*a.rgb)));
    float alpha=(operation==2 || operation==3 || operation==7) ? (alphaOperation==1 ? a.a*b.a : a.a) :
                (operation==5 ? maskAlpha : (alphaOperation==2 ? a.a+b.a : m.a));
    gl_FragColor=clamp(vec4(rgb,alpha),0.0,1.0);
}
"""
