"""Read UE2 property/enum metadata for typed bytecode recovery (profiled packages)."""
from ue2package import Package, Reader
from sdk_enums import enum_members


class Types:
    def __init__(self, directory, packages=('Core', 'Engine', 'NWindow', 'Interface')):
        self.properties, self.functions, self.parents, self.enums = {}, {}, {}, {}
        for name in packages:
            p = Package(directory / (name + '.u'))
            qualify = lambda s: s if s == 'None' or s.split('.')[0] in ('Core','Engine','NWindow','Interface') else name + '.' + s
            for i, e in enumerate(p.exports, 1):
                path = qualify(p.ref(i))
                kind = p.ref(e.cls).split('.')[-1]
                if e.cls == 0:
                    self.parents[path.casefold()] = qualify(p.ref(e.super))
                elif kind == 'Enum':
                    members = enum_members(p, p.ref(i))[2]
                    self.enums[path.casefold()] = [p.name(m) for m in members]
                elif kind == 'Function':
                    self.functions[path.casefold()] = qualify(p.function(p.ref(i))['fields'][3])
                elif kind.endswith('Property'):
                    r = Reader(p.data[e.offset:e.offset+e.size])
                    if p.name(r.index()) != 'None':
                        raise ValueError('Tagged property metadata')
                    r.index()
                    next_field = qualify(p.ref(r.index()))
                    dim, flags = r.unpack('<i'), r.unpack('<I')
                    r.index()  # category
                    if flags & 0x20:
                        r.take(2)  # replication offset
                    ref = qualify(p.ref(r.index())) if kind in ('ByteProperty','ObjectProperty','ClassProperty','StructProperty','ArrayProperty') else None
                    self.properties[path.casefold()] = dict(kind=kind, ref=ref, flags=flags, dim=dim, next=next_field)

    def property(self, name):
        return self.properties.get(name.casefold()) or self.properties.get(('Interface.'+name).casefold())

    def function_key(self, name, owner):
        if '.' in name:
            full = name if name.split('.')[0] in ('Core','Engine','NWindow','Interface') else 'Interface.'+name
            return full.casefold()
        cls = owner.rsplit('.', 1)[0]
        if cls.split('.')[0] not in ('Core','Engine','NWindow','Interface'):
            cls = 'Interface.' + cls
        while cls != 'None':
            key = (cls+'.'+name).casefold()
            if key in self.functions:
                return key
            cls = self.parents.get(cls.casefold(), cls.rsplit('.', 1)[0] if cls.count('.') > 1 else 'None')
        return None

    def parameters(self, name, owner):
        key = self.function_key(name, owner)
        field = self.functions.get(key, 'None')
        params, result, seen = [], None, set()
        while field != 'None':
            if field in seen:
                raise ValueError('Cyclic property chain')
            seen.add(field)
            prop = self.property(field)
            if not prop:
                break
            if prop['flags'] & 0x400:
                result = prop
            elif prop['flags'] & 0x80:
                params.append(prop)
            field = prop['next']
        return params, result

    def enum(self, prop):
        if prop and prop['kind'] == 'ByteProperty' and prop['ref'] != 'None':
            return prop['ref']
        return None
