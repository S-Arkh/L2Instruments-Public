"""Bounded UE2 framebuffer state; no game shaders or native code are executed."""
from texture_decode import property_value

# Factor names describe RGB equations; unsupported engine-specific modes are
# rejected rather than inheriting a previous object's OpenGL state.
BLENDS = {
    'overwrite': (1, 0),
    'modulate': (0x0306, 0x0300),       # destination color, source color
    'alpha': (0x0302, 0x0303),
    'translucent': (1, 0x0301),
    'darken': (0, 0x0301),
    'brighten': (0x0302, 1),
    'invisible': (0, 1),
}
FINAL_MODES = {0:'overwrite',1:'modulate',2:'alpha',4:'translucent',
               5:'darken',6:'brighten',7:'invisible'}
SHADER_MODES = {0:'overwrite',1:'alpha',2:'modulate',3:'translucent',
                4:'invisible',5:'brighten',6:'darken'}


def state_for(kind,document):
    def value(name,default):return property_value(document,name,default)
    state=dict(blend='overwrite',alpha_test=False,alpha_ref=0,
               z_write=True,z_test=True,two_sided=False)
    if kind=='FinalBlend':
        mode=value('FrameBufferBlending',0)
        if mode not in FINAL_MODES:raise ValueError(f'Unsupported FinalBlend mode {mode}')
        state.update(blend=FINAL_MODES[mode],z_test=value('ZTest',True))
    elif kind=='Shader':
        mode=value('OutputBlending',0)
        if mode not in SHADER_MODES:raise ValueError(f'Unsupported Shader blend {mode}')
        state['blend']=SHADER_MODES[mode]
        opacity=value('Opacity',None)
        if mode==0 and isinstance(opacity,dict) and opacity.get('id'):state['blend']='alpha'
        state['alpha_test']=mode==1
    else:
        masked=value('bMasked',False);alpha=value('bAlphaTexture',False)
        state.update(blend='alpha' if masked or alpha else 'overwrite',
                     alpha_test=bool(masked or alpha),
                     alpha_ref=204 if masked or (alpha and value('Format',0)==3) else 25.5,
                     two_sided=value('bTwoSided',False))
        return state
    state.update(z_write=value('ZWrite',True),two_sided=value('TwoSided',False),
                 alpha_test=value('AlphaTest',state['alpha_test']),
                 alpha_ref=value('AlphaRef',0))
    if not isinstance(state['alpha_ref'],int) or not 0<=state['alpha_ref']<=255:
        raise ValueError('Invalid material AlphaRef')
    return state


def render_order(geometry,projected,states):
    """Opaque depth-writing faces first, then blended faces back to front."""
    def key(row):
        index,face=row
        slot=geometry.get('face_materials',[])
        state=states.get(slot[index],{}) if slot else {}
        blended=state.get('blend','alpha')!='overwrite' or not state.get('z_write',True)
        return blended,sum(projected[i][2] for i in face)/len(face)
    return sorted(enumerate(geometry['polygons']),key=key)
