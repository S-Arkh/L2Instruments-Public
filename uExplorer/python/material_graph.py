"""Bounded read-only material dependency graph and resource resolution."""
from pathlib import Path
import math
import struct
from resource_view import MATERIALS, TEXTURES
from texture_decode import prepare_texture

MAX_NODES = 128
MAX_BYTES = 64*1024*1024


def references(value, field=''):
    if isinstance(value,dict):
        if {'id','path','class'} <= value.keys():
            if value['id']:yield field,value
        else:
            label=value.get('name',field)
            for key,child in value.items():
                if key not in ('name','class','path'):
                    yield from references(child, label if key=='value' else f'{label}.{key}'.strip('.'))
    elif isinstance(value,list):
        for i,child in enumerate(value):yield from references(child,f'{field}[{i}]')


def float_value(bits):
    value=struct.unpack('<f',struct.pack('<I',bits))[0]
    return value if math.isfinite(value) else str(value)


class ResourceResolver:
    def __init__(self,core,dependencies=()):
        self.core=core;self.dependencies=list(dependencies);self.inventories={}

    def inventory(self,path):
        path=str(Path(path).resolve())
        if path not in self.inventories:
            self.inventories[path]=self.core.request(operation='resource_inventory',path=path)['result']
        return self.inventories[path]

    def resolve(self,path,reference):
        path=Path(path).resolve();identifier=reference['id']
        if identifier>0:return str(path),identifier
        if not identifier:raise ValueError('Empty resource reference')
        parts=reference['path'].split('.')
        if len(parts)<2:raise ValueError('External reference has no package path')
        package=parts[0].casefold();object_path='.'.join(parts[1:])
        roots=[path.parent]
        roots.extend(Path(p).resolve() if Path(p).is_dir() else Path(p).resolve().parent for p in self.dependencies)
        tiers=[(p,) for p in dict.fromkeys(roots)]
        parent=path.parent.parent
        if parent.is_dir():
            tiers.append(tuple(p for p in parent.iterdir() if p.is_dir() and p not in roots and
                         p.name.casefold() in ('textures','systextures','animations','staticmeshes','system')))
        for tier in tiers:
            candidates=[p for root in tier if root.is_dir() for p in root.iterdir()
                        if p.is_file() and p.stem.casefold()==package
                        and p.suffix.casefold() in ('.u','.utx','.ukx','.usx','.unr','.uax')]
            if len(candidates)>1:raise ValueError('Ambiguous resource package: '+parts[0])
            if not candidates:continue
            target=str(candidates[0].resolve())
            matches=[o for o in self.inventory(target)['candidates']
                     if o['path'].casefold() in (object_path.casefold(),reference['path'].casefold())]
            if len(matches)!=1:raise ValueError('Unresolved or ambiguous resource: '+reference['path'])
            return target,matches[0]['id']
        raise ValueError('Missing resource package: '+parts[0])

    def read(self,path,identifier,budget=MAX_BYTES):
        entry=next((o for o in self.inventory(path)['candidates'] if o['id']==identifier),None)
        if entry is None:raise ValueError('Resource export is absent')
        if entry.get('serial_bytes',0)>min(MAX_BYTES,budget):raise ValueError('Resource exceeds remaining graph byte budget')
        kind=entry['class'].rsplit('.',1)[-1]
        operation='texture' if kind in TEXTURES else 'material' if kind in MATERIALS else 'palette' if kind=='Palette' else None
        if operation is None:raise ValueError('Not a material/texture resource: '+kind)
        document=self.core.request(operation=operation,path=str(path),object_id=identifier)['result']
        return entry,document


def prepare_material_graph(core,path,identifier,dependencies=(),cancelled=lambda:False):
    resolver=ResourceResolver(core,dependencies)
    nodes=[];lookup={};pending=[(str(Path(path).resolve()),identifier)]
    total=0
    while pending:
        if cancelled():raise ValueError('Material graph cancelled')
        key=pending.pop(0)
        if key in lookup:continue
        if len(nodes)>=MAX_NODES:break
        node=dict(path=key[0],id=key[1],links=[])
        lookup[key]=len(nodes);nodes.append(node)
        try:
            entry,doc=resolver.read(*key,budget=MAX_BYTES-total);total+=entry.get('serial_bytes',0)
            if total>MAX_BYTES:raise ValueError('Material graph exceeds 64 MiB')
            node.update(name=entry['path'],kind=entry['class'],document=doc)
            for field,reference in references(doc.get('tags',[])):
                link=dict(field=field,reference=reference)
                try:
                    target=resolver.resolve(key[0],reference);link['target']=target
                    if target not in lookup and target not in pending:pending.append(target)
                except (ValueError,RuntimeError) as error:link['error']=str(error)
                node['links'].append(link)
        except (ValueError,RuntimeError) as error:node['error']=str(error)
    for node in nodes:
        for link in node['links']:
            if 'target' in link:
                link['node']=lookup.get(tuple(link['target']))
                if link['node'] is None:link['error']='Graph node limit reached'
    return dict(nodes=nodes,truncated=bool(pending))


def material_thumbnail(core,node,dependencies=()):
    if 'document' not in node:return {'error':node.get('error','No material document')}
    doc=node['document']
    if not doc.get('mips'):return None
    # Bounded thumbnail, preserve the original document for parameter inspection.
    level=next((i for i,m in enumerate(doc['mips']) if max(m['width'],m['height'])<=256),len(doc['mips'])-1)
    return prepare_texture(core,node['path'],doc,level,dependencies=dependencies)
