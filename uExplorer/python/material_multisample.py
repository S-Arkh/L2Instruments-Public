"""Recognize one stored two-sampler multiply route without executing shader text."""
from pathlib import Path
from material_coordinates import coordinate_channel,verify_coordinate_shader
from texture_decode import property_value


MULTIPLY_SHADER = (
    'float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
    'c1=texcolor0;a1=texcolor0;result.xyz=c1.xyz;result.w=a1.w;'
    'float4 texcolor1=tex2D(s[1],mul(m1,float3(tex0.xy,1.f)));'
    'c1=texcolor1;c2=result;a1=result;result.xyz=c1.xyz*c2.xyz;result.w=a1.w;')
TERMINAL = 'c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'


def independent_multiply_profile(document):
    if (property_value(document,'CombineOperation',0)!=2
            or property_value(document,'AlphaOperation',0)!=0
            or any(property_value(document,key,False) for key in
                   ('InvertMask','Modulate2X','Modulate4X','UseDiffuseAlpha'))):
        return None
    mask=property_value(document,'Mask',None)
    if mask is not None and (not isinstance(mask,dict) or mask.get('id')):
        return None
    strings=document.get('strings')
    if (not isinstance(strings,list) or len(strings)!=2
            or any(not isinstance(item,dict) or not isinstance(item.get('name'),str)
                   or not item['name'] or not isinstance(item.get('values'),list)
                   or len(item['values'])>30
                   or any(not isinstance(name,str) or not name for name in item['values'])
                   for item in strings)):
        return None
    shader=document.get('shader')
    expressions=[]
    for index,item in enumerate(strings):
        forms=[]
        for channel in range(8):
            matrix=bool(item['values'])
            expression=(f'mul(m{index},float3(tex{channel}.xy,1.f))'
                        if matrix else f'tex{channel}')
            forms.append((channel,matrix,expression))
        expressions.append(forms)
    for first in expressions[0]:
        for second in expressions[1]:
            expected=(MULTIPLY_SHADER.replace('mul(m0,float3(tex0.xy,1.f))',first[2])
                      .replace('mul(m1,float3(tex0.xy,1.f))',second[2]))
            if shader in (expected,expected+TERMINAL):
                # Preserve the existing mip-grid route for two ordinary UV0
                # textures; the GPU-only path is needed for modified or
                # explicitly different coordinate sources.
                if first[:2]==(0,False) and second[:2]==(0,False):return None
                return ((first[0],first[1]),(second[0],second[1]))
    return None


def independent_multiply_shader(document):
    return independent_multiply_profile(document) is not None


def verify_branch(path,reference,sampler,profile,active,read_limited,resolver):
    """Verify exact package/object identities and every serialized sampler suffix."""
    seen=set(active)
    modifiers=('TexPanner','TexScaler','TexOscillator','TexRotator')
    supported=(*modifiers,'TexCoordSource')
    order=sampler['values']
    documents=[]
    while True:
        if (not isinstance(reference,dict) or not reference.get('id')
                or not isinstance(reference.get('class'),str)):
            raise ValueError('Fragment UV branch has no material reference')
        path,identifier=resolver.resolve(path,reference)
        key=path,identifier
        if key in seen:raise ValueError('Material cycle')
        if len(seen)>=32:raise ValueError('Material chain exceeds 32 nodes')
        seen.add(key)
        entry,doc=read_limited(path,identifier)
        kind=entry['class'].rsplit('.',1)[-1]
        identity=Path(path).stem+'.'+entry['path']
        ref_path=reference.get('path')
        if (not isinstance(ref_path,str) or not ref_path
                or ref_path.casefold() not in (entry['path'].casefold(),identity.casefold())
                or kind!=reference['class'].rsplit('.',1)[-1]):
            raise ValueError('Fragment UV reference differs from resolved object')
        if kind=='Texture':
            if identity.casefold()!=sampler['name'].casefold():
                raise ValueError('Fragment UV Texture differs from saved sampler')
            break
        if kind not in supported:
            raise ValueError('Fragment UV branch requires supported modifiers and a Texture')
        documents.append((kind,identity,doc))
        reference=property_value(doc,'Material',{})
    sources=[index for index,(kind,_,_) in enumerate(documents) if kind=='TexCoordSource']
    if len(sources)>1:raise ValueError('Fragment UV branch requires at most one coordinate source')
    channel,_=profile
    if channel and not sources:
        raise ValueError('Fragment UV channel requires an explicit coordinate source')
    source_index=sources[0] if sources else None
    if sources and coordinate_channel(documents[source_index][2])!=channel:
        raise ValueError('Fragment UV source differs from saved shader channel')
    position=0
    for index,(kind,identity,doc) in enumerate(documents):
        if doc.get('strings')!=[dict(name=sampler['name'],values=order[position:])]:
            raise ValueError('Fragment UV sampler suffix differs')
        node_channel=channel if source_index is not None and index<=source_index else 0
        verify_coordinate_shader(doc,node_channel,requires_matrix=bool(order[position:]))
        if kind=='TexCoordSource':continue
        allowed=(15,) if channel else (0,15)
        if (property_value(doc,'TexCoordSource',15) not in allowed
                or property_value(doc,'TexCoordCount',0)!=0
                or property_value(doc,'TexCoordProjected',False)):
            raise ValueError('Fragment UV modifier source is not confirmed')
        if position>=len(order) or identity.casefold()!=order[position].casefold():
            raise ValueError('Fragment UV modifier identity differs from saved sampler')
        position+=1
    if position!=len(order):
        raise ValueError('Fragment UV modifier count differs from saved sampler')


def verify_multiply_bindings(document,path,active,read_limited,resolver):
    profile=independent_multiply_profile(document)
    if profile is None:
        raise ValueError('Unsupported independent-UV Combiner shader')
    for field,item,expected in zip(('Material1','Material2'),document['strings'],profile):
        verify_branch(path,property_value(document,field,{}),item,expected,active,read_limited,resolver)
