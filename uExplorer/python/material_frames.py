"""Bounded, manual inspection of serialized Texture.AnimNext links."""
from pathlib import Path
from texture_decode import prepare_texture

MAX_FRAME_STEP=31
MAX_FRAME_BYTES=64*1024*1024


def saved_next(document):
    tags=document.get('tags')
    if (not isinstance(tags,list) or any(not isinstance(tag,dict)
            or not isinstance(tag.get('name'),str) for tag in tags)):
        raise ValueError('Invalid Texture properties')
    matches=[tag for tag in tags if tag['name'].casefold()=='animnext']
    if len(matches)>1:raise ValueError('Duplicate Texture.AnimNext properties')
    if not matches:return None
    reference=matches[0].get('value')
    if not isinstance(reference,dict) or type(reference.get('id')) is not int:
        raise ValueError('Invalid Texture.AnimNext reference')
    if reference['id']==0:return None
    if (not isinstance(reference.get('class'),str)
            or reference['class'].rsplit('.',1)[-1]!='Texture'
            or not isinstance(reference.get('path'),str) or not reference['path']):
        raise ValueError('Texture.AnimNext must name a Texture')
    return reference


def has_saved_next(document):
    try:return saved_next(document) is not None
    except ValueError:return False


def select_saved_frame(core,resolver,surface,step):
    """Select one stored frame by following links; do not infer runtime timing."""
    if type(step) is not int or not 0<=step<=MAX_FRAME_STEP:
        raise ValueError('Saved frame step is outside preview limits')
    root=surface.get('saved_frame_root')
    if (not isinstance(root,(tuple,list)) or len(root)!=2
            or not isinstance(root[0],str) or type(root[1]) is not int or root[1]<=0):
        raise ValueError('Sampler has no inspectable saved frame chain')
    if not step:return dict(surface,saved_frame_step=0)
    remaining=MAX_FRAME_BYTES
    def read(path,identifier):
        nonlocal remaining
        entry,document=resolver.read(path,identifier,budget=remaining)
        used=entry.get('serial_bytes',0)
        if type(used) is not int or not 0<=used<=remaining:
            raise ValueError('Saved frame chain exceeds the 64 MiB read budget')
        remaining-=used
        if entry.get('class','').rsplit('.',1)[-1]!='Texture':
            raise ValueError('Saved frame is not a direct Texture')
        return entry,document
    path,identifier=root
    entry,document=read(path,identifier)
    seen={(str(Path(path).resolve()),identifier)}
    for _ in range(step):
        reference=saved_next(document)
        if reference is None:raise ValueError('Texture.AnimNext ended before the selected step')
        path,identifier=resolver.resolve(path,reference)
        key=(str(Path(path).resolve()),identifier)
        if key in seen:raise ValueError('Texture.AnimNext cycle; no implicit loop is assumed')
        seen.add(key)
        entry,document=read(path,identifier)
        identity=Path(path).stem+'.'+entry['path']
        if reference['path'].casefold() not in (entry['path'].casefold(),identity.casefold()):
            raise ValueError('Texture.AnimNext differs from the resolved object')
    mips=document.get('mips',[])
    if (not mips or (mips[0]['width'],mips[0]['height'])!=tuple(surface.get('native_size',()))):
        raise ValueError('Saved frame native dimensions differ from the source Texture')
    size=(surface['width'],surface['height'])
    levels=[i for i,mip in enumerate(mips) if (mip['width'],mip['height'])==size]
    if len(levels)!=1:raise ValueError('Saved frame lacks one matching stored mip')
    prepared=prepare_texture(core,path,document,levels[0],dependencies=resolver.dependencies)
    if 'error' in prepared:raise ValueError(prepared['error'])
    return dict(surface,pixels=prepared['pixels'],saved_frame_step=step,
                saved_frame_name=entry['path'])


def selectable_samplers(surface):
    """Limit manual inspection to the explicitly labelled complex previews."""
    mode=surface.get('saved_frame_mode')
    if mode=='isolated':
        candidates=[surface]
    elif mode in ('panner_combiner','alpha_modulate') and len(surface.get('fragment_layers',[]))==3:
        candidates=surface['fragment_layers'][:2]
    else:
        return []
    return [index for index,layer in enumerate(candidates) if layer.get('saved_frame_root')]


def select_material_frame(core,resolver,surface,sampler,step):
    if type(sampler) is not int or sampler not in selectable_samplers(surface):
        raise ValueError('Selected sampler has no inspectable saved frame chain')
    result=dict(surface)
    if result['saved_frame_mode']=='isolated':
        result=select_saved_frame(core,resolver,result,step)
    else:
        layers=list(result['fragment_layers'])
        layers[sampler]=select_saved_frame(core,resolver,layers[sampler],step)
        if sampler==0:
            layers[2]=dict(layers[0])
            result['pixels']=layers[0]['pixels']
        result['fragment_layers']=layers
    result['notes']=result.get('notes',[])+[
        f'Шаг AnimNext (диагностика): sampler {sampler}, шаг {step}; только сохранённый кадр, '
        'игровая частота, синхронизация и события не подтверждены; '
        'выбран один sampler одного материала, остальные остаются на исходных кадрах; '
        'адресация и render-state текущего preview не меняются, декодирование использует '
        'свойства выбранного кадра; частота просмотра задаётся пользователем, загрузка '
        'может замедлять просмотр']
    return result
