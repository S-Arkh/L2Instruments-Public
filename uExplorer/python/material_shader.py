"""Recognize a narrow stored-shader alpha route; never execute shader text.

Missing Combiner masks cannot be assigned a universal default: the observed
compiler may evaluate a constant before a texture, even when that swaps inputs.
Only direct Texture/ConstantColor routes and simple alpha copies are recognized.
"""
import re
from pathlib import Path
from texture_decode import property_value

RGB_EXPRESSIONS = {
    'c1.xyz','c2.xyz','c1.xyz*c2.xyz','c1.xyz*c2.xyz*2.f',
    'c1.xyz*c2.xyz*4.f','c1.xyz+c2.xyz','c1.xyz*c2.xyz*mFactor',
    'c1.xyz+c1.w*c2.xyz','c2.w',
    'c1.xyz*result.w+c2.xyz*(1.f-result.w)',
}


def direct_masked_add(document):
    """Accept observed two-direct-texture masked-add shaders, in sampler order."""
    alpha=property_value(document,'AlphaOperation',0)
    if property_value(document,'CombineOperation',0)!=6 or alpha not in (0,2):
        return False
    if any(property_value(document,key,False) for key in
           ('InvertMask','Modulate2X','Modulate4X','UseDiffuseAlpha')):
        return False
    mask=property_value(document,'Mask',None)
    first=property_value(document,'Material1',{})
    if mask is not None:
        if not isinstance(mask,dict):return False
        if mask.get('id') and (alpha!=0 or not isinstance(first,dict)
                or any(mask.get(k)!=first.get(k) for k in ('id','path','class'))):return False
    strings=document.get('strings',[])
    if not isinstance(strings,list) or len(strings)!=2:return False
    refs=[property_value(document,key,{}) for key in ('Material1','Material2')]
    for index,ref in enumerate(refs):
        if (not isinstance(ref,dict) or not ref.get('id')
                or ref.get('class','').rsplit('.',1)[-1]!='Texture'):return False
        item=strings[index]
        if not isinstance(item,dict) or item.get('values'):return False
        path=item.get('name','').casefold();target=ref.get('path','').casefold()
        if not target or not (path==target or path.endswith('.'+target)):return False
        other=refs[1-index]
        if isinstance(other,dict):
            other_path=other.get('path','').casefold()
            if other_path and other_path!=target and (path==other_path or path.endswith('.'+other_path)):
                return False
    expected=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
              'result.xyz=c1.xyz;result.w=a1.w;'
              'float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;')
    expected+=('a1=texcolor1;a2=result;result.xyz=c1.xyz+c1.w*c2.xyz;result.w=a1.w+a2.w;'
               if alpha==2 else 'a1=result;result.xyz=c1.xyz+c1.w*c2.xyz;result.w=a1.w;')
    terminal='c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'
    return document.get('shader') in (expected,expected+terminal)


def implicit_alpha_source(document):
    mask=property_value(document,'Mask',None)
    if isinstance(mask,dict) and mask.get('id'):return None
    if property_value(document,'InvertMask',False):return None
    text=document.get('shader','')
    if not isinstance(text,str) or not text or len(text)>32768:return None
    # Drop only the known terminal vertex-lighting pass, which copies alpha.
    terminal='c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'
    if text.endswith(terminal):text=text[:-len(terminal)]
    references={name:property_value(document,name,{}) for name in ('Material1','Material2')}
    if any(not isinstance(ref,dict) for ref in references.values()):return None
    constants=[name for name,ref in references.items() if ref.get('class','').rsplit('.',1)[-1]=='ConstantColor']
    symbols={'tFactor':constants[0] if len(constants)==1 else None}
    strings=document.get('strings',[])
    for statement in text.split(';'):
        statement=statement.strip()
        if not statement:continue
        texture=re.fullmatch(r'float4 (texcolor\d{1,2})=tex2D\(s\[(\d{1,2})\],tex0\)',statement)
        if texture:
            symbol,index=texture.group(1),int(texture.group(2))
            if index>=len(strings) or strings[index].get('values'):return None
            path=strings[index].get('name','').casefold()
            matches=[name for name,ref in references.items()
                     if ref.get('class','').rsplit('.',1)[-1]=='Texture' and ref.get('id')
                     and ref.get('path') and (path==ref['path'].casefold()
                         or path.endswith('.'+ref['path'].casefold()))]
            # Reused texture inputs are equivalent, but suffix collisions are not.
            if not matches:return None
            if len({references[name]['path'].casefold() for name in matches})!=1:return None
            symbols[symbol]=matches[0]
            continue
        assignment=re.fullmatch(r'(a1|a2)=(tFactor|result|texcolor\d+)',statement)
        if assignment:
            symbols[assignment.group(1)]=symbols.get(assignment.group(2))
            continue
        alpha=re.fullmatch(r'result\.w=(a1|a2)\.w',statement)
        if alpha:
            symbols['result']=symbols.get(alpha.group(1))
            continue
        # RGB-only assignments cannot modify the alpha symbols above.
        if re.fullmatch(r'c[12]=(tFactor|result|texcolor\d+)',statement):continue
        rgb=re.fullmatch(r'(result\.xyz|c[12]\.xyz)=(.+)',statement)
        if rgb and rgb.group(2) in RGB_EXPRESSIONS:continue
        return None
    return symbols.get('result')


def verify_panner_combiner(parent_path,parent_entry,parent,child_path,child_entry,child,
                           resolver,read_limited,active):
    """Recognize three direct two-Texture routes; never execute saved shader text."""
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    def matches(reference,path,entry,kind):
        if not isinstance(reference,dict) or not reference.get('id'):return False
        saved_kind=reference.get('class');saved_path=reference.get('path');actual=entry.get('class')
        return (isinstance(saved_kind,str) and saved_kind.rsplit('.',1)[-1]==kind
                and isinstance(actual,str) and actual.rsplit('.',1)[-1]==kind
                and isinstance(saved_path,str) and bool(saved_path)
                and saved_path.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    for document,names in ((parent,('Material','TexCoordSource','TexCoordCount','TexCoordProjected',
                                    'PanRate','PanDirection')),
                           (child,('Material1','Material2','Mask','CombineOperation','AlphaOperation',
                                   'Modulate2X','Modulate4X','InvertMask','UseDiffuseAlpha'))):
        tags=document.get('tags')
        if (not isinstance(tags,list) or any(not isinstance(tag,dict)
                or not isinstance(tag.get('name'),str) for tag in tags)):
            raise ValueError('Panner Combiner properties are invalid')
        if any(sum(tag['name'].casefold()==name.casefold() for tag in tags)>1 for name in names):
            raise ValueError('Panner Combiner has duplicate properties')
    if (parent_entry.get('class','').rsplit('.',1)[-1]!='TexPanner'
            or not matches(property_value(parent,'Material',{}),child_path,child_entry,'Combiner')):
        raise ValueError('Panner Combiner reference differs from resolved object')
    source=property_value(parent,'TexCoordSource',15)
    count=property_value(parent,'TexCoordCount',0)
    projected=property_value(parent,'TexCoordProjected',False)
    if (type(source) is not int or source not in (0,15)
            or type(count) is not int or count!=0
            or type(projected) is not bool or projected):
        raise ValueError('Panner Combiner requires unprojected UV0')
    direction=next((tag for tag in parent['tags'] if tag['name'].casefold()=='pandirection'),None)
    if direction is not None:
        words=direction.get('words')
        if (direction['name']!='PanDirection' or not isinstance(words,list) or len(words)!=3
                or any(type(word) is not int or not 0<=word<=0xffffffff for word in words)):
            raise ValueError('Panner Combiner direction layout is not supported')
    color=property_value(child,'CombineOperation',0)
    alpha=property_value(child,'AlphaOperation',0)
    mod2=property_value(child,'Modulate2X',False)
    flags=[property_value(child,name,False) for name in ('Modulate4X','InvertMask','UseDiffuseAlpha')]
    mask=property_value(child,'Mask',None)
    if (type(color) is not int or type(alpha) is not int or type(mod2) is not bool
            or (color,alpha,mod2) not in ((2,0,True),(2,1,True),(3,1,False))
            or any(type(flag) is not bool or flag for flag in flags)
            or mask is not None and (not isinstance(mask,dict) or mask.get('id'))):
        raise ValueError('Panner Combiner operation is not recognized')
    refs=[property_value(child,name,{}) for name in ('Material1','Material2')]
    texture_entries=[]
    for reference in refs:
        if (not isinstance(reference,dict) or not reference.get('id')
                or not isinstance(reference.get('class'),str)
                or reference['class'].rsplit('.',1)[-1]!='Texture'):
            raise ValueError('Panner Combiner requires direct Texture inputs')
        path,identifier=resolver.resolve(child_path,reference)
        if (path,identifier) in active:raise ValueError('Material cycle')
        entry,_=read_limited(path,identifier)
        if not matches(reference,path,entry,'Texture'):
            raise ValueError('Panner Combiner Texture reference differs from resolved object')
        texture_entries.append((path,identifier,entry))
    strings=child.get('strings')
    if (not isinstance(strings,list) or len(strings)!=2
            or strings!=[dict(name=identity(path,entry),values=[])
                         for path,_,entry in texture_entries]):
        raise ValueError('Panner Combiner sampler identities differ')
    parent_name=identity(parent_path,parent_entry)
    if parent.get('strings')!=[dict(name=item['name'],values=[parent_name]) for item in strings]:
        raise ValueError('Panner Combiner sampler suffix differs')
    start=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
           'result.xyz=c1.xyz;result.w=a1.w;'
           'float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;')
    alpha_code=('a1=result;' if alpha==0 else 'a1=texcolor1;a2=result;')
    rgb=('c1.xyz*c2.xyz*2.f' if color==2 else 'c1.xyz+c2.xyz')
    result_alpha=('a1.w' if alpha==0 else 'a1.w*a2.w')
    expected=start+alpha_code+'result.xyz='+rgb+';result.w='+result_alpha+';'
    terminal='c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'
    text=child.get('shader')
    if text not in (expected,expected+terminal):
        raise ValueError('Panner Combiner shader differs')
    transformed=text
    for index in range(2):
        transformed=transformed.replace(f'tex2D(s[{index}],tex0)',
            f'tex2D(s[{index}],mul(m{index},float3(tex0.xy,1.f)))')
    if parent.get('shader')!=transformed:
        raise ValueError('Panner Combiner transformed shader differs')
    return tuple((path,identifier) for path,identifier,_ in texture_entries),color,alpha,2 if mod2 else 1


def verify_direct_alpha_modulate(document,path,resolver,read_limited,active):
    """Recognize one saved two-Texture operation 7 without assuming mFactor."""
    names=('Material1','Material2','Mask','CombineOperation','AlphaOperation',
           'Modulate2X','Modulate4X','InvertMask','UseDiffuseAlpha')
    tags=document.get('tags')
    if (not isinstance(tags,list) or any(not isinstance(tag,dict)
            or not isinstance(tag.get('name'),str) for tag in tags)):
        raise ValueError('Alpha-modulate Combiner properties are invalid')
    if any(sum(tag['name'].casefold()==name.casefold() for tag in tags)>1 for name in names):
        raise ValueError('Alpha-modulate Combiner has duplicate properties')
    color=property_value(document,'CombineOperation',0)
    alpha=property_value(document,'AlphaOperation',0)
    flags=[property_value(document,name,False) for name in
           ('Modulate2X','Modulate4X','InvertMask','UseDiffuseAlpha')]
    if (type(color) is not int or color!=7 or type(alpha) is not int or alpha!=0
            or any(type(flag) is not bool or flag for flag in flags)):
        raise ValueError('Alpha-modulate Combiner operation is not recognized')
    targets=[]
    for field in ('Material1','Material2'):
        ref=property_value(document,field,{})
        if (not isinstance(ref,dict) or type(ref.get('id')) is not int or not ref['id']
                or not isinstance(ref.get('class'),str)
                or ref['class'].rsplit('.',1)[-1]!='Texture'
                or not isinstance(ref.get('path'),str) or not ref['path']):
            raise ValueError('Alpha-modulate Combiner requires direct Texture inputs')
        target,identifier=resolver.resolve(path,ref)
        if (target,identifier) in active:raise ValueError('Material cycle')
        entry,_=read_limited(target,identifier)
        identity=Path(target).stem+'.'+entry['path']
        if (entry['class'].rsplit('.',1)[-1]!='Texture'
                or ref['path'].casefold() not in (entry['path'].casefold(),identity.casefold())):
            raise ValueError('Alpha-modulate Texture reference differs from resolved object')
        targets.append((target,identifier,entry,identity))
    if targets[0][:2]==targets[1][:2]:
        raise ValueError('Alpha-modulate requires distinct Texture inputs')
    mask=property_value(document,'Mask',{})
    if (not isinstance(mask,dict) or type(mask.get('id')) is not int or not mask['id']
            or not isinstance(mask.get('class'),str)
            or mask['class'].rsplit('.',1)[-1]!='Texture'
            or not isinstance(mask.get('path'),str) or not mask['path']
            or resolver.resolve(path,mask)!=targets[0][:2]
            or mask['path'].casefold() not in (targets[0][2]['path'].casefold(),
                                                targets[0][3].casefold())):
        raise ValueError('Alpha-modulate requires Mask to resolve to Material1')
    if document.get('strings')!=[dict(name=item[3],values=[]) for item in targets]:
        raise ValueError('Alpha-modulate sampler identities differ')
    expected=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;a1=texcolor0;'
              'result.xyz=c1.xyz;result.w=a1.w;'
              'float4 texcolor1=tex2D(s[1],tex0);c1=texcolor1;c2=result;'
              'c2.xyz=c2.w;a1=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w;'
              'c1=diffuse;c2=result;a2=result;'
              'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;')
    if document.get('shader')!=expected:
        raise ValueError('Alpha-modulate saved shader differs')
    return tuple((target,identifier) for target,identifier,_,_ in targets)


def verify_shader_modifier(document,parent_path,parent_entry,reference,child_path,child_entry,
                           child,surface,resolver,read_limited,active):
    """Prove a saved modifier binding to the direct diffuse sampler only."""
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    def matches(ref,path,entry):
        name=ref.get('path') if isinstance(ref,dict) else None
        return (isinstance(name,str) and bool(name) and
                name.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    if (child_entry.get('class','').rsplit('.',1)[-1]!='Shader'
            or not matches(reference,child_path,child_entry)):
        raise ValueError('UV modifier Shader reference differs from resolved object')
    diffuse=property_value(child,'Diffuse',{})
    opacity=property_value(child,'Opacity',None)
    if (not isinstance(diffuse,dict) or not diffuse.get('id')
            or not isinstance(diffuse.get('class'),str)
            or diffuse['class'].rsplit('.',1)[-1]!='Texture'
            or opacity is not None and not isinstance(opacity,dict)):
        raise ValueError('UV modifier Shader requires direct Texture diffuse and supported Opacity')
    if (not surface.get('uv0_exact') or not surface.get('uv_coordinate_exact',True)
            or surface.get('fragment_layers') or surface.get('uv_channel',0)!=0
            or surface.get('uv_chain') or surface.get('uv_rotation_animation')
            or surface.get('uv_oscillation') or surface.get('uv_pan_rate',0.)
            or tuple(surface.get('uv_scale',(1.,1.)))!=(1.,1.)
            or tuple(surface.get('uv_offset',(0.,0.)))!=(0.,0.)
            or tuple(surface.get('uv_rotation',(1.,0.,0.,1.)))!=(1.,0.,0.,1.)):
        raise ValueError('UV modifier Shader requires unmodified diffuse UV0')
    strings=child.get('strings')
    if (not isinstance(strings,list) or not 1<=len(strings)<=8
            or any(not isinstance(item,dict) or set(item)!={'name','values'}
                   or not isinstance(item.get('name'),str) or not item['name']
                   or not isinstance(item.get('values'),list)
                   or any(not isinstance(value,str) or not value for value in item['values'])
                   for item in strings)
            or strings[0]['values']!=[]):
        raise ValueError('UV modifier Shader requires direct saved samplers')
    outer_identity=identity(parent_path,parent_entry)
    shader=child.get('shader')
    outer_shader=document.get('shader')
    prefix=('float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;c2=diffuse;'
            'a1=texcolor0;a2=diffuse;result.xyz=c1.xyz*c2.xyz')
    if (not isinstance(shader,str) or len(shader)>32768
            or not isinstance(outer_shader,str) or len(outer_shader)>32768):
        raise ValueError('UV modifier Shader diffuse sampler is not recognized')
    outer_strings=document.get('strings')
    multipass=shader.startswith('if(currentpass==0){')
    if multipass:
        if (not isinstance(outer_strings,list) or len(outer_strings)!=len(strings)
                or outer_strings[0]!=dict(name=strings[0]['name'],values=[outer_identity])):
            raise ValueError('UV modifier Shader sampler suffix differs')
        marker='if(currentpass==0){'
        if not outer_shader.startswith(marker):raise ValueError('UV modifier Shader first pass differs')
        end=shader.find('}',len(marker));outer_end=outer_shader.find('}',len(marker))
        if end<0 or outer_end<0:raise ValueError('UV modifier Shader first pass differs')
        body=shader[len(marker):end];outer_body=outer_shader[len(marker):outer_end]
        direct='tex2D(s[0],tex0)'
        mapped='tex2D(s[0],mul(m0,float3(tex0.xy,1.f)))'
        first_pass=(prefix+'*mFactor;result.w=a1.w*a2.w;')
        if body!=first_pass or outer_body!=first_pass.replace(direct,mapped):
            raise ValueError('UV modifier Shader first pass differs')
    else:
        if outer_strings!=[
                dict(name=item['name'],values=[outer_identity]+item['values']) for item in strings]:
            raise ValueError('UV modifier Shader sampler suffix differs')
        if (not shader.startswith(prefix)
                or shader.count('tex2D(')+shader.count('texCUBE(')!=len(strings)):
            raise ValueError('UV modifier Shader diffuse sampler is not recognized')
        expected=shader
        for index in range(len(strings)):
            pairs=[(f'tex2D(s[{index}],tex0)',
                    f'tex2D(s[{index}],mul(m{index},float3(tex0.xy,1.f)))')]
            if index:
                for function in ('tex2D','texCUBE'):
                    pairs.append((f'{function}(s[{index}],EnvTex.tex4)',
                                  f'{function}(s[{index}],mul(m{index},float4(EnvTex.tex4,1.f)))'))
            candidates=[(direct,mapped) for direct,mapped in pairs
                        if shader.count(mapped if strings[index]['values'] else direct)==1]
            if len(candidates)!=1:raise ValueError('UV modifier Shader sampler expression differs')
            direct,mapped=candidates[0]
            if not strings[index]['values']:expected=expected.replace(direct,mapped)
        if outer_shader!=expected:
            raise ValueError('UV modifier Shader transformed shader differs')
    texture_path,texture_id=resolver.resolve(child_path,diffuse)
    if opacity and opacity.get('id'):
        if (not isinstance(opacity.get('class'),str)
                or opacity['class'].rsplit('.',1)[-1]!='Texture'
                or resolver.resolve(child_path,opacity)!=(texture_path,texture_id)):
            raise ValueError('UV modifier Shader requires Opacity to be the same Texture')
    if (texture_path,texture_id) in set(active):raise ValueError('Material cycle')
    texture_entry,_=read_limited(texture_path,texture_id)
    sampler=strings[0]['name']
    sampler_matches=identity(texture_path,texture_entry).casefold()==sampler.casefold()
    if not sampler_matches and '.' not in sampler:
        candidates=[item for item in resolver.inventory(texture_path)['candidates']
                    if item.get('path','').rsplit('.',1)[-1].casefold()==sampler.casefold()]
        sampler_matches=len(candidates)==1 and candidates[0].get('id')==texture_id
    surface_name=surface.get('name')
    if (texture_entry.get('class','').rsplit('.',1)[-1]!='Texture'
            or not matches(diffuse,texture_path,texture_entry)
            or opacity and opacity.get('id') and not matches(opacity,texture_path,texture_entry)
            or not sampler_matches
            or not isinstance(surface_name,str) or surface_name.casefold()!=texture_entry['path'].casefold()):
        raise ValueError('UV modifier Shader diffuse Texture differs from saved sampler')
