"""Strict diagnostic selection of serialized TexCoordSource streams."""
from texture_decode import property_value


def coordinate_channel(document):
    # TexCoordSource defaults to Stream0; unlike other TexModifiers its
    # TexCoordSource default is not NoChange. A missing SourceChannel is
    # accepted only for Stream0, later corroborated by its saved shader.
    channel=property_value(document,'SourceChannel',None)
    source=property_value(document,'TexCoordSource',0)
    if channel is None and type(source) is int and source==0:
        channel=0
    if (type(channel) is not int or not 0<=channel<=7
            or type(source) is not int or source!=channel):
        raise ValueError('TexCoordSource requires matching explicit stream and SourceChannel')
    if (property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('TexCoordSource requires unprojected 2D coordinates')
    return channel


def verify_coordinate_shader(document,channel,requires_matrix=False):
    """Recognize one saved sampler/stream expression; never execute shader text."""
    tail=('c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
          'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')
    matrix=f'float4 texcolor0=tex2D(s[0],mul(m0,float3(tex{channel}.xy,1.f)));'+tail
    direct=f'float4 texcolor0=tex2D(s[0],tex{channel});'+tail
    if document.get('shader') not in ((matrix,) if requires_matrix else (matrix,direct)):
        raise ValueError('TexCoordSource requires a verified single-sampler stream shader')


def verify_direct_source(document,channel,reference,unique_leaf=False):
    verify_coordinate_shader(document,channel)
    strings=document.get('strings')
    if (not isinstance(strings,list) or len(strings)!=1 or not isinstance(strings[0],dict)
            or strings[0].get('values')!=[]):
        raise ValueError('TexCoordSource requires one unmodified saved sampler')
    sampler=strings[0].get('name');target=reference.get('path')
    if (not isinstance(sampler,str) or not sampler or not isinstance(target,str) or not target
            or not (sampler.casefold()==target.casefold()
                    or sampler.casefold().endswith('.'+target.casefold())
                    or (unique_leaf and '.' not in sampler
                        and target.casefold().endswith('.'+sampler.casefold())))):
        raise ValueError('TexCoordSource sampler does not match the Texture')


def chain_channel(documents):
    sources=[doc for doc in documents if doc.get('class','').rsplit('.',1)[-1]=='TexCoordSource']
    if not sources:return 0
    if len(sources)!=1:raise ValueError('UV chain requires at most one coordinate source')
    channel=coordinate_channel(sources[0])
    if channel and any(property_value(doc,'TexCoordSource',15)!=15
                       for doc in documents if doc is not sources[0]):
        raise ValueError('UV chain over nonzero stream requires NoChange on other modifiers')
    return channel
