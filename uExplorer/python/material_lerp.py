"""Recognize observed direct-texture masked interpolation; never run shader text."""
from texture_decode import property_value


def direct_lerp(document):
    return direct_masked_route(document,5)


def direct_masked_add_mask(document):
    return direct_masked_route(document,6)


def direct_masked_route(document,color):
    if property_value(document,'CombineOperation',0)!=color or property_value(document,'AlphaOperation',0)!=0:
        return False
    if any(property_value(document,key,False) for key in ('Modulate2X','Modulate4X','UseDiffuseAlpha')):
        return False
    refs={key:property_value(document,key,{}) for key in ('Material1','Material2','Mask')}
    mask=refs['Mask']
    if color==5 and (mask is None or isinstance(mask,dict) and not mask.get('id')):
        refs['Mask']=refs['Material1']
    if any(not isinstance(r,dict) or not r.get('id') or r.get('class','').rsplit('.',1)[-1]!='Texture'
           or not r.get('path') for r in refs.values()):return False
    strings=document.get('strings',[])
    def same(a,b):return refs[a]['id']==refs[b]['id'] and refs[a]['path'].casefold()==refs[b]['path'].casefold()
    shared='Material1' if same('Mask','Material1') else 'Material2' if same('Mask','Material2') else None
    inverted=property_value(document,'InvertMask',False)
    if shared and inverted:return False
    if color==6 and (shared or inverted):return False
    order=('Material1','Material2') if shared else ('Material1','Mask','Material2')
    if not isinstance(strings,list) or len(strings)!=len(order):return False
    for item,key in zip(strings,order):
        if not isinstance(item,dict) or item.get('values'):return False
        path=item.get('name','').casefold()
        target=refs[key]['path'].casefold()
        if not (path==target or path.endswith('.'+target)):return False
        for other in refs.values():
            other_path=other['path'].casefold()
            if other_path!=target and (path==other_path or path.endswith('.'+other_path)):return False
    text=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
          'result.xyz=c1.xyz;result.w=a1.w;')
    if shared:
        source='texcolor1' if shared=='Material2' else 'result'
        text+=('float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;'
               f'a1={source};result.xyz=c1.xyz*{source}.w+c2.xyz*(1.f-{source}.w);result.w=a1.w;')
    else:
        text+=('float4 texcolor1=tex2D(s[1],tex0);c2=result;a1=texcolor1;'
               +('a1=1.f-a1;' if inverted else '')
               +'result.xyz=c2.xyz;result.w=a1.w;'
               'float4 texcolor2=tex2D(s[2],tex0);c1=texcolor2;c2=result;a1=result;'
               +('result.xyz=c1.xyz*result.w+c2.xyz*(1.f-result.w);' if color==5
                 else 'result.xyz=c1.xyz+c1.w*c2.xyz;')+'result.w=a1.w;')
    terminal='c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'
    return document.get('shader') in (text,text+terminal)
