"""Explicit, bounded mip-grid material arithmetic (not a game shader runtime)."""
import struct
from texture_decode import property_value
from animation_decode import floats
from material_shader import implicit_alpha_source,direct_masked_add
from material_lerp import direct_lerp,direct_masked_add_mask
from material_multisample import independent_multiply_shader


def shared_grid(surfaces):
    """Allow a 1x1 constant on any grid; otherwise require identical sampling."""
    if any(not s.get('uv_coordinate_exact',s.get('uv0_exact',True))
           or (s.get('uv_channel',0)==0 and not s.get('uv0_exact',True)) for s in surfaces):
        raise ValueError('Material composition requires supported matching UV coordinates')
    if any(type(s.get('uv_channel',0)) is not int or not 0<=s.get('uv_channel',0)<=7
           for s in surfaces):
        raise ValueError('Invalid material UV channel')
    grids=[s for s in surfaces if (s['width'],s['height'])!=(1,1)]
    reference=grids[0] if grids else surfaces[0]
    size=reference['width'],reference['height']
    if any((s['width'],s['height'])!=size for s in grids):
        raise ValueError('Material mip dimensions differ; resampling is not yet supported')
    wrap=tuple(reference.get('wrap',(0,0)))
    scale=tuple(reference.get('uv_scale',(1.,1.)))
    offset=tuple(reference.get('uv_offset',(0.,0.)))
    rotation=tuple(reference.get('uv_rotation',(1.,0.,0.,1.)))
    rotation_animation=reference.get('uv_rotation_animation')
    oscillation=reference.get('uv_oscillation')
    chain=reference.get('uv_chain')
    pan_rate=reference.get('uv_pan_rate',0.)
    pan_direction=tuple(reference.get('uv_pan_direction',(1.,0.)))
    channel=reference.get('uv_channel',0)
    if any(s.get('uv_channel',0)!=channel for s in grids):
        raise ValueError('Material UV channels differ')
    if any(tuple(s.get('wrap',(0,0)))!=wrap for s in grids):
        raise ValueError('Material addressing modes differ')
    if any(tuple(s.get('uv_scale',(1.,1.)))!=scale for s in grids):
        raise ValueError('Material UV scales differ')
    if any(tuple(s.get('uv_offset',(0.,0.)))!=offset for s in grids):
        raise ValueError('Material UV offsets differ')
    if any(tuple(s.get('uv_rotation',(1.,0.,0.,1.)))!=rotation for s in grids):
        raise ValueError('Material UV rotations differ')
    if any(s.get('uv_rotation_animation')!=rotation_animation for s in grids):
        raise ValueError('Material UV rotation animations differ')
    if any(s.get('uv_oscillation')!=oscillation for s in grids):
        raise ValueError('Material UV oscillations differ')
    if any(s.get('uv_chain')!=chain for s in grids):
        raise ValueError('Material UV chains differ')
    if any(s.get('uv_pan_rate',0.)!=pan_rate for s in grids):
        raise ValueError('Material UV animation rates differ')
    if pan_rate and any(tuple(s.get('uv_pan_direction',(1.,0.)))!=pan_direction for s in grids):
        raise ValueError('Material UV animation directions differ')
    return dict(width=size[0],height=size[1],wrap=wrap,uv_scale=scale,uv_offset=offset,
                uv_pan_rate=pan_rate,uv_pan_direction=pan_direction,uv_channel=channel,
                uv0_exact=channel==0,uv_coordinate_exact=True,
                uv_rotation=rotation,uv_rotation_animation=rotation_animation,uv_oscillation=oscillation,uv_chain=chain)


def grid_pixels(surface,grid):
    count=grid['width']*grid['height']
    pixels=surface['pixels']
    if len(pixels)!=surface['width']*surface['height']*4:
        raise ValueError('Invalid material pixel storage')
    return pixels*count if (surface['width'],surface['height'])==(1,1) else pixels


def opacity_surface(diffuse,opacity):
    grid=shared_grid([diffuse,opacity])
    pixels=bytearray(grid_pixels(diffuse,grid))
    pixels[3::4]=grid_pixels(opacity,grid)[3::4]
    return dict(diffuse,**grid,pixels=bytes(pixels))


def combiner_inputs(document):
    color=property_value(document,'CombineOperation',0)
    alpha=property_value(document,'AlphaOperation',0)
    if type(color) is not int or type(alpha) is not int:
        raise ValueError('Invalid Combiner operation type')
    # L2's enum index 7 differs from the generic UE2 "Use_Color_From_Mask".
    # Masked add is allowed only for a fully recognized direct-texture route.
    if (color not in (0,1,2,3) and not direct_masked_add(document)
            and not direct_lerp(document) and not direct_masked_add_mask(document)):
        raise ValueError(f'Unsupported Combiner color operation {color}')
    if alpha not in range(5):raise ValueError(f'Unsupported Combiner alpha operation {alpha}')
    if property_value(document,'UseDiffuseAlpha',False):
        raise ValueError('Combiner.UseDiffuseAlpha semantics are not confirmed')
    needed={'Material1'} if color==0 else {'Material2'} if color==1 else {'Material1','Material2'}
    needed.update({0:('Material1',) if independent_multiply_shader(document) else
                      (implicit_alpha_source(document) or 'Mask',),1:('Material1','Material2'),2:('Material1','Material2'),
                   3:('Material1',),4:('Material2',)}[alpha])
    return color,alpha,sorted(needed)


def combine(document,surfaces):
    color,alpha,needed=combiner_inputs(document)
    grid=shared_grid([surfaces[name] for name in needed])
    channels={name:grid_pixels(surfaces[name],grid) for name in needed}
    count=grid['width']*grid['height'];pixels=bytearray(count*4)
    multiplier=4 if property_value(document,'Modulate4X',False) else 2 if property_value(document,'Modulate2X',False) else 1
    for channel in range(4):
        if channel<3 and color in (0,1):
            pixels[channel::4]=channels['Material1' if color==0 else 'Material2'][channel::4]
        elif channel<3:
            a,b=channels['Material1'][channel::4],channels['Material2'][channel::4]
            if color==6:
                pixels[channel::4]=bytes(min(255,y+(x*alpha2+127)//255)
                    for x,y,alpha2 in zip(a,b,channels['Material2'][3::4]))
            elif color==5:
                mask=channels[implicit_alpha_source(document) or 'Mask'][3::4]
                if property_value(document,'InvertMask',False):mask=bytes(255-v for v in mask)
                pixels[channel::4]=bytes((x*(255-m)+y*m+127)//255 for x,y,m in zip(a,b,mask))
            else:
                pixels[channel::4]=bytes(min(255,(x*y*multiplier+127)//255) if color==2 else min(255,x+y)
                                         for x,y in zip(a,b))
        elif alpha==0:
            values=channels[implicit_alpha_source(document) or 'Mask'][3::4]
            pixels[3::4]=bytes(255-v for v in values) if property_value(document,'InvertMask',False) else values
        elif alpha in (3,4):
            pixels[3::4]=channels['Material1' if alpha==3 else 'Material2'][3::4]
        else:
            a,b=channels['Material1'][3::4],channels['Material2'][3::4]
            pixels[3::4]=bytes((x*y+127)//255 if alpha==1 else min(255,x+y) for x,y in zip(a,b))
    return dict(grid,pixels=bytes(pixels))


def material_float(document,name,default):
    tag=next((t for t in document.get('tags',[]) if t['name'].casefold()==name.casefold()),None)
    return floats([tag['bits']],1)[0] if tag else default


def scaler(document,allow_offsets=False):
    def number(name,default):return material_float(document,name,default)
    if not allow_offsets and (number('UOffset',0)!=0 or number('VOffset',0)!=0):
        raise ValueError('TexScaler offsets require scaler_offset and original dimensions')
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('TexScaler requires unprojected UV0')
    values=number('UScale',1),number('VScale',1)
    if any(abs(v)<1e-6 or abs(v)>1e6 for v in values):
        raise ValueError('TexScaler scale is zero or exceeds preview limits')
    # The serialized engine matrix stores float32 coefficients. Round each
    # reciprocal at that boundary, rather than comparing a Python float64 2/3
    # directly with its stored float32 representation.
    return tuple(struct.unpack('<f',struct.pack('<f',1/v))[0] for v in values)


def scaler_offset(document,native_size=None):
    values=[material_float(document,name,0) for name in ('UOffset','VOffset')]
    if not any(values):return (0.,0.)
    if not native_size or len(native_size)!=2 or any(not isinstance(v,int) or not 0<v<=16384 for v in native_size):
        raise ValueError('TexScaler offsets require a direct Texture with original dimensions')
    offsets=tuple(value/size for value,size in zip(values,native_size))
    if any(abs(v)>1e6 for v in offsets):raise ValueError('TexScaler offsets exceed preview limits')
    return tuple(struct.unpack('<f',struct.pack('<f',v))[0] for v in offsets)
