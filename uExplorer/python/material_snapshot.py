"""Strictly bound, static previews of serialized stateful UV matrices."""
import math
from pathlib import Path
from material_coordinates import verify_coordinate_shader
from material_rotation import stored_matrix
from material_uv import f32
from texture_decode import property_value


def snapshot_modifier(kind,document):
    return (kind in ('TexOscillatorTriggered','TexPannerTriggered')
            or kind=='TexOscillator' and any(
                property_value(document,axis+'OscillationType',0)==3 for axis in ('U','V')))


def verify_snapshot_coordinates(document):
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('Cached UV snapshot requires unprojected UV0')
    verify_coordinate_shader(document,0,requires_matrix=True)


def planar_uv_matrix(document):
    """Read one complete, bounded stored planar matrix without inferring time."""
    tags=document.get('tags',[])
    if not isinstance(tags,list) or any(not isinstance(tag,dict) for tag in tags):
        raise ValueError('Cached UV snapshot tags are invalid')
    matrices=[tag for tag in tags if tag.get('name')=='M']
    if len(matrices)!=1 or not isinstance(matrices[0].get('members'),list):
        raise ValueError('Cached UV snapshot requires one complete stored matrix')
    planes=matrices[0]['members']
    if (len(planes)!=4 or any(not isinstance(p,dict) for p in planes)
            or {p.get('name') for p in planes}!={'XPlane','YPlane','ZPlane','WPlane'}):
        raise ValueError('Cached UV snapshot matrix planes differ')
    for plane in planes:
        members=plane.get('members')
        if (not isinstance(members,list) or len(members)!=4
                or any(not isinstance(member,dict) for member in members)
                or {member.get('name') for member in members}!={'W','X','Y','Z'}):
            raise ValueError('Cached UV snapshot matrix fields differ')
    matrix=stored_matrix(document)
    if (any(abs(value)>1e6 for row in matrix for value in row)
            or any(row[3]!=0. for row in matrix[:3])
            or [matrix[i][2] for i in range(3)]!=[0.,0.,1.]
            or matrix[3]!=[0.,0.,0.,1.]):
        raise ValueError('Cached UV snapshot matrix is not bounded planar UV')
    return tuple(tuple(row[:3]) for row in matrix[:3])


def cached_uv_snapshot(document,object_path,reference,unique_leaf=False):
    """Return saved planar XY mapping, not a reconstructed runtime state."""
    verify_snapshot_coordinates(document)
    if (not isinstance(reference,dict) or not isinstance(reference.get('class'),str)
            or reference['class'].rsplit('.',1)[-1]!='Texture'
            or not reference.get('id')):
        raise ValueError('Cached UV snapshot requires a direct Texture')
    strings=document.get('strings')
    if (not isinstance(strings,list) or len(strings)!=1 or not isinstance(strings[0],dict)
            or not isinstance(strings[0].get('values'),list)
            or len(strings[0]['values'])!=1):
        raise ValueError('Cached UV snapshot requires one saved modifier and sampler')
    sampler=strings[0].get('name')
    modifier=strings[0]['values'][0]
    target=reference.get('path')
    def matches(saved,name):
        return (isinstance(saved,str) and isinstance(name,str) and bool(name)
                and (saved.casefold()==name.casefold()
                     or saved.casefold().endswith('.'+name.casefold())))
    if not matches(modifier,object_path):
        raise ValueError('Cached UV snapshot modifier binding differs')
    short=isinstance(sampler,str) and bool(sampler) and '.' not in sampler
    if not ((not short and matches(sampler,target)) or
            (short and unique_leaf and isinstance(target,str)
             and (target.casefold()==sampler.casefold()
                  or target.casefold().endswith('.'+sampler.casefold())))):
        raise ValueError('Cached UV snapshot sampler binding differs')
    matrix=planar_uv_matrix(document)
    return (matrix[0][0],matrix[0][1],matrix[1][0],matrix[1][1]),tuple(matrix[2][:2])


def cached_uv_chain(documents,surface,leaf_package=None):
    """Compose stored planar matrices only; they need not represent one game instant."""
    from material_chain import verify_sampler_chain
    kinds=('TexPanner','TexScaler','TexOscillator','TexRotator',
           'TexPannerTriggered','TexOscillatorTriggered')
    if (any(doc.get('class','').rsplit('.',1)[-1] not in kinds for doc in documents)
            or not any(snapshot_modifier(doc.get('class','').rsplit('.',1)[-1],doc)
                       for doc in documents)):
        raise ValueError('Cached UV chain requires a supported stateful modifier')
    verify_sampler_chain(documents,surface)
    if 'stored_mip_sizes' not in surface:
        raise ValueError('Cached UV chain requires an exact direct Texture')
    reference=property_value(documents[-1],'Material',{})
    target=reference.get('path') if isinstance(reference,dict) else None
    actual=surface.get('name')
    if (not isinstance(actual,str) or not actual or not isinstance(target,str) or not target
            or not (target.casefold()==actual.casefold()
                    or isinstance(leaf_package,str) and bool(leaf_package)
                    and target.casefold()==(leaf_package+'.'+actual).casefold())):
        raise ValueError('Cached UV chain resolved Texture differs from saved reference')
    result=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
    for document in documents:
        verify_snapshot_coordinates(document)
        matrix=planar_uv_matrix(document)
        product=tuple(tuple(sum(result[i][k]*matrix[k][j] for k in range(3))
                            for j in range(3)) for i in range(3))
        if any(not math.isfinite(value) or abs(value)>1e6 for row in product for value in row):
            raise ValueError('Cached UV chain matrix exceeds preview limits')
        result=tuple(tuple(f32(value) for value in row) for row in product)
    return (result[0][0],result[0][1],result[1][0],result[1][1]),result[2][:2]


def shader_panner_snapshot(parent_path,parent_entry,parent,shader_path,shader_entry,shader,
                           panner_path,panner_entry,panner,texture_path,texture_entry):
    """Bound a static Rotator → Shader → Panner diffuse-only snapshot."""
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    for document,names in ((parent,('Material','TexCoordSource','TexCoordCount','TexCoordProjected')),
                           (shader,('Diffuse','Opacity')),
                           (panner,('Material','TexCoordSource','TexCoordCount','TexCoordProjected'))):
        tags=document.get('tags')
        if (not isinstance(tags,list) or any(not isinstance(tag,dict)
                or not isinstance(tag.get('name'),str) for tag in tags)):
            raise ValueError('Shader snapshot properties are invalid')
        for name in names:
            if sum(tag['name'].casefold()==name.casefold() for tag in tags)>1:
                raise ValueError('Shader snapshot has duplicate properties')
    def matches(reference,path,entry,kind):
        if not isinstance(reference,dict) or not reference.get('id'):return False
        saved_kind=reference.get('class')
        saved_path=reference.get('path')
        return (isinstance(saved_kind,str) and saved_kind.rsplit('.',1)[-1]==kind
                and entry.get('class','').rsplit('.',1)[-1]==kind
                and isinstance(saved_path,str) and bool(saved_path)
                and saved_path.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    if (parent_entry.get('class','').rsplit('.',1)[-1]!='TexRotator'
            or not matches(property_value(parent,'Material',{}),shader_path,shader_entry,'Shader')
            or not matches(property_value(shader,'Diffuse',{}),panner_path,panner_entry,'TexPanner')
            or not matches(property_value(panner,'Material',{}),texture_path,texture_entry,'Texture')):
        raise ValueError('Shader snapshot material references differ from resolved objects')
    opacity=property_value(shader,'Opacity',None)
    if opacity is not None and (not isinstance(opacity,dict) or opacity.get('id')):
        raise ValueError('Shader snapshot requires no separate Opacity')
    for document in (parent,panner):
        source=property_value(document,'TexCoordSource',15)
        count=property_value(document,'TexCoordCount',0)
        projected=property_value(document,'TexCoordProjected',False)
        if (type(source) is not int or source not in (0,15)
                or type(count) is not int or count!=0
                or type(projected) is not bool or projected):
            raise ValueError('Shader snapshot requires unprojected UV0')
    sampler=identity(texture_path,texture_entry)
    inner=identity(panner_path,panner_entry)
    outer=identity(parent_path,parent_entry)
    saved=shader.get('strings');outer_saved=parent.get('strings')
    if (not isinstance(saved,list) or not 1<=len(saved)<=8
            or not isinstance(outer_saved,list) or len(outer_saved)!=len(saved)
            or saved[0]!=dict(name=sampler,values=[inner])
            or outer_saved[0]!=dict(name=sampler,values=[outer,inner])
            or panner.get('strings')!=[dict(name=sampler,values=[inner])]):
        raise ValueError('Shader snapshot diffuse sampler suffix differs')
    prefix=('float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
            'c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;'
            'result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;')
    text=shader.get('shader')
    if (not isinstance(text,str) or len(text)>32768 or not text.startswith(prefix)
            or text.count('tex2D(s[0],')!=1 or 'texCUBE(s[0],' in text
            or parent.get('shader')!=text):
        raise ValueError('Shader snapshot diffuse shader differs')
    verify_coordinate_shader(panner,0,requires_matrix=True)
    first=planar_uv_matrix(parent)
    second=planar_uv_matrix(panner)
    result=tuple(tuple(sum(first[i][k]*second[k][j] for k in range(3))
                       for j in range(3)) for i in range(3))
    if any(not math.isfinite(value) or abs(value)>1e6 for row in result for value in row):
        raise ValueError('Shader snapshot matrix exceeds preview limits')
    result=tuple(tuple(f32(value) for value in row) for row in result)
    return (result[0][0],result[0][1],result[1][0],result[1][1]),result[2][:2]


def isolated_combiner_sampler(parent_path,parent_entry,parent,graph_path,graph_entry,graph,
                              resolver,read_limited,active):
    """Isolate sampler 0 of one saved nested graph; do not evaluate the graph."""
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    def matches(reference,path,entry,kind):
        if not isinstance(reference,dict) or not reference.get('id'):return False
        saved_kind=reference.get('class');saved_path=reference.get('path')
        actual_kind=entry.get('class')
        return (isinstance(saved_kind,str) and saved_kind.rsplit('.',1)[-1]==kind
                and isinstance(actual_kind,str) and actual_kind.rsplit('.',1)[-1]==kind
                and isinstance(saved_path,str) and bool(saved_path)
                and saved_path.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    def unique(document,names):
        tags=document.get('tags')
        if (not isinstance(tags,list) or any(not isinstance(tag,dict)
                or not isinstance(tag.get('name'),str) for tag in tags)):
            raise ValueError('Isolated sampler properties are invalid')
        if any(sum(tag['name'].casefold()==name.casefold() for tag in tags)>1 for name in names):
            raise ValueError('Isolated sampler has duplicate properties')
    unique(parent,('Material','TexCoordSource','TexCoordCount','TexCoordProjected'))
    graph_kind=graph_entry.get('class','').rsplit('.',1)[-1]
    if (parent_entry.get('class','').rsplit('.',1)[-1]!='TexPanner'
            or graph_kind not in ('Shader','Combiner')
            or not matches(property_value(parent,'Material',{}),graph_path,graph_entry,graph_kind)):
        raise ValueError('Isolated sampler requires a resolved Panner → Shader/Combiner')
    stack=list(active)
    def take(path,document,field,kind,*,leaf=False):
        reference=property_value(document,field,{})
        if (not isinstance(reference,dict) or not reference.get('id')
                or not isinstance(reference.get('class'),str)
                or reference['class'].rsplit('.',1)[-1]!=kind):
            raise ValueError('Isolated sampler reference has an unsupported class')
        next_path,identifier=resolver.resolve(path,reference)
        key=(next_path,identifier)
        if key in stack:raise ValueError('Material cycle')
        if len(stack)>=32:raise ValueError('Material chain exceeds 32 nodes')
        entry,doc=read_limited(next_path,identifier)
        if not matches(reference,next_path,entry,kind):
            raise ValueError('Isolated sampler reference differs from resolved object')
        if not leaf:stack.append(key)
        return next_path,identifier,entry,doc
    graph_documents=[]
    if graph_kind=='Shader':
        unique(graph,('Diffuse',))
        graph_documents.append(graph)
        a_path,_,_,a=take(graph_path,graph,'Diffuse','Combiner')
    elif property_value(graph,'CombineOperation',0)==6:
        a_path,a=graph_path,graph
    elif property_value(graph,'CombineOperation',0)==3:
        a_path,a=None,None
    else:
        raise ValueError('Isolated sampler Combiner route differs')
    if a is not None:
        b_path,_,_,b=take(a_path,a,'Material2','Combiner')
    else:
        b_path,b=graph_path,graph
    c_path,_,c_entry,c=take(b_path,b,'Material1','Combiner')
    trigger_path,_,trigger_entry,trigger=take(c_path,c,'Material1','TexOscillatorTriggered')
    rot_path,_,rot_entry,rot=take(trigger_path,trigger,'Material','TexRotator')
    tex_path,tex_id,tex_entry,_=take(rot_path,rot,'Material','Texture',leaf=True)
    path_checks=([(a,'Material2',6,1)] if a is not None else [])+[
        (b,'Material1',3,1),(c,'Material1',2,0)]
    for document,field,color,alpha in path_checks:
        unique(document,(field,'CombineOperation','AlphaOperation'))
        operation=property_value(document,'CombineOperation',0)
        alpha_operation=property_value(document,'AlphaOperation',0)
        if (type(operation) is not int or operation!=color
                or type(alpha_operation) is not int or alpha_operation!=alpha):
            raise ValueError('Isolated sampler Combiner route differs')
        graph_documents.append(document)
    for document in (parent,trigger,rot):
        unique(document,('Material','TexCoordSource','TexCoordCount','TexCoordProjected'))
        source=property_value(document,'TexCoordSource',15)
        count=property_value(document,'TexCoordCount',0)
        projected=property_value(document,'TexCoordProjected',False)
        if (type(source) is not int or source not in (0,15)
                or type(count) is not int or count!=0
                or type(projected) is not bool or projected):
            raise ValueError('Isolated sampler requires unprojected UV0')
    sampler=identity(tex_path,tex_entry)
    trigger_name=identity(trigger_path,trigger_entry)
    rot_name=identity(rot_path,rot_entry)
    outer_name=identity(parent_path,parent_entry)
    outer_strings=parent.get('strings')
    if not isinstance(outer_strings,list) or not outer_strings or not isinstance(outer_strings[0],dict):
        raise ValueError('Isolated sampler has no outer metadata')
    outer_sampler=outer_strings[0].get('name')
    if isinstance(outer_sampler,str) and '.' not in outer_sampler:
        candidates=[entry for entry in resolver.inventory(tex_path)['candidates']
                    if entry.get('path','').rsplit('.',1)[-1].casefold()==outer_sampler.casefold()]
        if len(candidates)!=1 or candidates[0].get('id')!=tex_id:
            raise ValueError('Isolated short sampler is ambiguous')
    elif outer_sampler!=sampler:
        raise ValueError('Isolated sampler texture identity differs')
    if (outer_strings[0]!=dict(name=outer_sampler,values=[outer_name,trigger_name,rot_name])
            or trigger.get('strings')!=[dict(name=sampler,values=[trigger_name,rot_name])]
            or rot.get('strings')!=[dict(name=sampler,values=[rot_name])]):
        raise ValueError('Isolated sampler modifier suffix differs')
    for document in graph_documents:
        strings=document.get('strings')
        if (not isinstance(strings,list) or not strings
                or strings[0]!=dict(name=sampler,values=[trigger_name,rot_name])):
            raise ValueError('Isolated sampler graph suffix differs')
    prefix=('float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
            'c1=texcolor0;a1=texcolor0;result.xyz=c1.xyz;result.w=a1.w;')
    for document in (parent,*graph_documents):
        text=document.get('shader')
        if (not isinstance(text,str) or len(text)>32768 or not text.startswith(prefix)
                or text.count('tex2D(s[0],')!=1 or 'texCUBE(s[0],' in text):
            raise ValueError('Isolated sampler shader differs')
    for document in (trigger,rot):verify_coordinate_shader(document,0,requires_matrix=True)
    result=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
    for document in (parent,trigger,rot):
        matrix=planar_uv_matrix(document)
        product=tuple(tuple(sum(result[i][k]*matrix[k][j] for k in range(3))
                            for j in range(3)) for i in range(3))
        if any(not math.isfinite(value) or abs(value)>1e6 for row in product for value in row):
            raise ValueError('Isolated sampler matrix exceeds preview limits')
        result=tuple(tuple(f32(value) for value in row) for row in product)
    return (tex_path,tex_id,tuple(stack),
            (result[0][0],result[0][1],result[1][0],result[1][1]),result[2][:2])


def isolated_rotator_combiner_sampler(parent_path,parent_entry,parent,graph_path,graph_entry,graph,
                                      resolver,read_limited,active):
    """Inspect only sampler 0 and four saved matrices, not the nested result."""
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    def unique(document,names):
        tags=document.get('tags')
        if (not isinstance(tags,list) or any(not isinstance(tag,dict)
                or not isinstance(tag.get('name'),str) for tag in tags)):
            raise ValueError('Rotator isolated sampler properties are invalid')
        if any(sum(tag['name'].casefold()==name.casefold() for tag in tags)>1 for name in names):
            raise ValueError('Rotator isolated sampler has duplicate properties')
    def matches(reference,path,entry,kind):
        if (not isinstance(reference,dict) or type(reference.get('id')) is not int
                or not reference['id']):return False
        saved_kind=reference.get('class');saved_path=reference.get('path')
        return (isinstance(saved_kind,str) and saved_kind.rsplit('.',1)[-1]==kind
                and entry.get('class','').rsplit('.',1)[-1]==kind
                and isinstance(saved_path,str) and bool(saved_path)
                and saved_path.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    unique(parent,('Material','M','TexCoordSource','TexCoordCount','TexCoordProjected'))
    if (parent_entry.get('class','').rsplit('.',1)[-1]!='TexRotator'
            or not matches(property_value(parent,'Material',{}),graph_path,graph_entry,'Combiner')):
        raise ValueError('Isolated sampler requires a resolved Rotator → Combiner')
    stack=list(active)
    def take(path,document,field,kind,*,leaf=False):
        reference=property_value(document,field,{})
        if (not isinstance(reference,dict) or type(reference.get('id')) is not int
                or not reference['id'] or not isinstance(reference.get('class'),str)
                or reference['class'].rsplit('.',1)[-1]!=kind):
            raise ValueError('Rotator isolated sampler reference has an unsupported class')
        target,identifier=resolver.resolve(path,reference)
        key=(target,identifier)
        if key in stack:raise ValueError('Material cycle')
        if len(stack)>=32:raise ValueError('Material chain exceeds 32 nodes')
        entry,document=read_limited(target,identifier)
        if not matches(reference,target,entry,kind):
            raise ValueError('Rotator isolated sampler reference differs from resolved object')
        if not leaf:stack.append(key)
        return target,identifier,entry,document
    b_path,_,_,b=take(graph_path,graph,'Material2','Combiner')
    c_path,_,_,c=take(b_path,b,'Material2','Combiner')
    rot_path,_,rot_entry,rot=take(c_path,c,'Material1','TexRotator')
    osc_path,_,osc_entry,osc=take(rot_path,rot,'Material','TexOscillator')
    scale_path,_,scale_entry,scale=take(osc_path,osc,'Material','TexScaler')
    tex_path,tex_id,tex_entry,_=take(scale_path,scale,'Material','Texture',leaf=True)
    graphs=((graph,'Material2',5),(b,'Material2',5),(c,'Material1',6))
    for document,field,color in graphs:
        unique(document,(field,'CombineOperation','AlphaOperation'))
        operation=property_value(document,'CombineOperation',0)
        alpha=property_value(document,'AlphaOperation',0)
        if type(operation) is not int or operation!=color or type(alpha) is not int or alpha!=0:
            raise ValueError('Rotator isolated sampler Combiner route differs')
    modifiers=(parent,rot,osc,scale)
    for document in modifiers:
        unique(document,('Material','M','TexCoordSource','TexCoordCount','TexCoordProjected'))
        source=property_value(document,'TexCoordSource',15)
        count=property_value(document,'TexCoordCount',0)
        projected=property_value(document,'TexCoordProjected',False)
        if (type(source) is not int or source not in (0,15)
                or type(count) is not int or count!=0
                or type(projected) is not bool or projected):
            raise ValueError('Rotator isolated sampler requires unprojected UV0')
    sampler=identity(tex_path,tex_entry)
    names=[identity(parent_path,parent_entry),identity(rot_path,rot_entry),
           identity(osc_path,osc_entry),identity(scale_path,scale_entry)]
    saved=parent.get('strings')
    if (not isinstance(saved,list) or not 1<=len(saved)<=8
            or saved[0]!=dict(name=sampler,values=names)):
        raise ValueError('Rotator isolated sampler outer binding differs')
    for document,_,_ in graphs:
        strings=document.get('strings')
        if (not isinstance(strings,list) or not 1<=len(strings)<=8
                or strings[0]!=dict(name=sampler,values=names[1:])):
            raise ValueError('Rotator isolated sampler graph binding differs')
    for index,document in enumerate(modifiers[1:],1):
        if document.get('strings')!=[dict(name=sampler,values=names[index:])]:
            raise ValueError('Rotator isolated sampler modifier binding differs')
        verify_coordinate_shader(document,0,requires_matrix=True)
    prefix=('float4 texcolor0=tex2D(s[0],mul(m0,float3(tex0.xy,1.f)));'
            'c1=texcolor0;a1=texcolor0;result.xyz=c1.xyz;result.w=a1.w;')
    for document in (parent,*(item[0] for item in graphs)):
        text=document.get('shader')
        if (not isinstance(text,str) or len(text)>32768 or not text.startswith(prefix)
                or text.count('tex2D(s[0],')!=1 or 'texCUBE(s[0],' in text):
            raise ValueError('Rotator isolated sampler shader differs')
    result=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
    for document in modifiers:
        matrix=planar_uv_matrix(document)
        product=tuple(tuple(sum(result[i][k]*matrix[k][j] for k in range(3))
                            for j in range(3)) for i in range(3))
        if any(not math.isfinite(value) or abs(value)>1e6 for row in product for value in row):
            raise ValueError('Rotator isolated sampler matrix exceeds preview limits')
        result=tuple(tuple(f32(value) for value in row) for row in product)
    return (tex_path,tex_id,tuple(stack),
            (result[0][0],result[0][1],result[1][0],result[1][1]),result[2][:2])


def cached_combiner_snapshot(document,parent_path,parent_entry,reference,child_path,
                             child_entry,child,surface,resolver,read_limited,active):
    """Preview one saved planar Rotator over a verified one-sampler mip Combiner."""
    if (property_value(document,'TexCoordSource',15) not in (0,15)
            or property_value(document,'TexCoordCount',0)!=0
            or property_value(document,'TexCoordProjected',False)):
        raise ValueError('Cached Combiner UV snapshot requires unprojected UV0')
    if (not surface.get('uv0_exact') or not surface.get('uv_coordinate_exact',True)
            or surface.get('fragment_layers') or surface.get('uv_channel',0)!=0
            or surface.get('uv_chain') or surface.get('uv_rotation_animation')
            or surface.get('uv_oscillation') or surface.get('uv_pan_rate',0.)
            or tuple(surface.get('uv_scale',(1.,1.)))!=(1.,1.)
            or tuple(surface.get('uv_offset',(0.,0.)))!=(0.,0.)
            or tuple(surface.get('uv_rotation',(1.,0.,0.,1.)))!=(1.,0.,0.,1.)):
        raise ValueError('Cached Combiner UV snapshot requires unmodified UV0')
    def identity(path,entry):return Path(path).stem+'.'+entry['path']
    def reference_matches(ref,path,entry):
        name=ref.get('path') if isinstance(ref,dict) else None
        return (isinstance(name,str) and bool(name) and
                name.casefold() in (entry['path'].casefold(),identity(path,entry).casefold()))
    if (child_entry.get('class','').rsplit('.',1)[-1]!='Combiner'
            or not reference_matches(reference,child_path,child_entry)):
        raise ValueError('Cached Combiner reference differs from resolved object')
    refs=[property_value(child,field,{}) for field in ('Material1','Material2')]
    if (any(not isinstance(ref,dict) or not ref.get('id')
            or not isinstance(ref.get('class'),str) for ref in refs)
            or [ref['class'].rsplit('.',1)[-1] for ref in refs]!=['Texture','ConstantColor']):
        raise ValueError('Cached Combiner snapshot requires Texture then ConstantColor')
    mask=property_value(child,'Mask',None)
    if (property_value(child,'CombineOperation',0)!=2 or property_value(child,'AlphaOperation',0)!=0
            or property_value(child,'UseDiffuseAlpha',False) or property_value(child,'InvertMask',False)
            or mask is not None and (not isinstance(mask,dict) or mask.get('id'))
            or property_value(child,'Modulate2X',False) and property_value(child,'Modulate4X',False)):
        raise ValueError('Cached Combiner snapshot requires the verified multiply route')
    strings=child.get('strings')
    if (not isinstance(strings,list) or len(strings)!=1 or not isinstance(strings[0],dict)
            or set(strings[0])!={'name','values'} or strings[0].get('values')!=[]
            or not isinstance(strings[0].get('name'),str) or not strings[0]['name']):
        raise ValueError('Cached Combiner snapshot requires one saved sampler')
    sampler=strings[0]['name']
    if document.get('strings')!=[dict(name=sampler,values=[identity(parent_path,parent_entry)])]:
        raise ValueError('Cached Combiner snapshot modifier binding differs')
    shader=child.get('shader')
    direct='tex2D(s[0],tex0)'
    mapped='tex2D(s[0],mul(m0,float3(tex0.xy,1.f)))'
    factor=('*4.f' if property_value(child,'Modulate4X',False) else
            '*2.f' if property_value(child,'Modulate2X',False) else '')
    expected=('c1=tFactor;a1=tFactor;result.xyz=c1.xyz;result.w=a1.w;'
              'float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;c2=result;a1=result;'
              'result.xyz=c1.xyz*c2.xyz'+factor+';result.w=a1.w;')
    terminal='c1=diffuse;c2=result;a2=result;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a2.w;'
    if (shader not in (expected,expected+terminal)
            or document.get('shader')!=shader.replace(direct,mapped)):
        raise ValueError('Cached Combiner snapshot shader differs')
    seen=set(active)
    for ref in refs:
        path,identifier=resolver.resolve(child_path,ref)
        key=path,identifier
        if key in seen:raise ValueError('Material cycle')
        entry,_=read_limited(path,identifier)
        if (entry.get('class','').rsplit('.',1)[-1]!=ref['class'].rsplit('.',1)[-1]
                or not reference_matches(ref,path,entry)):
            raise ValueError('Cached Combiner operand differs from resolved object')
        if ref['class'].rsplit('.',1)[-1]=='Texture' and identity(path,entry).casefold()!=sampler.casefold():
            raise ValueError('Cached Combiner Texture differs from saved sampler')
    matrix=planar_uv_matrix(document)
    return (matrix[0][0],matrix[0][1],matrix[1][0],matrix[1][1]),matrix[2][:2]
