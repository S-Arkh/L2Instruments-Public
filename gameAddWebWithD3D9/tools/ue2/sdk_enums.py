"""Add client enum metadata to the compiler SDK without altering native storage.

Existing export payloads stay at their original offsets (including texture lazy
arrays). Only enum payloads and a class's child-list reference may be replaced.
This produces a compilation-only package, never a replacement game Engine.u.
"""
from dataclasses import replace
import hashlib
import struct
from ue2package import Package, Reader, FormatError, Entry


def compact(value):
    if not -0x80000000 <= value <= 0x7fffffff:
        raise ValueError('Compact index outside int32')
    n = abs(value)
    first = (n & 63) | (128 if value < 0 else 0)
    n >>= 6
    out = bytearray([first | (64 if n else 0)])
    while n:
        part = n & 127
        n >>= 7
        out.append(part | (128 if n else 0))
    return bytes(out)


def enum_members(package, path):
    matches = [(i, e) for i, e in enumerate(package.exports, 1)
               if package.ref(i).casefold() == path.casefold() and package.ref(e.cls) == 'Core.Enum']
    if len(matches) != 1:
        raise FormatError(f'Expected one Enum export: {path}')
    index, entry = matches[0]
    reader = Reader(package.data[entry.offset:entry.offset + entry.size])
    if package.name(reader.index()) != 'None' or reader.index() != 0:
        raise FormatError('Unexpected enum properties/superclass')
    reader.index()  # UField.Next
    prefix_end = reader.pos
    count = reader.index()
    if not 0 <= count <= 255:
        raise FormatError('Invalid enum member count')
    members = [reader.index() for _ in range(count)]
    if reader.pos != len(reader.data):
        raise FormatError('Trailing enum data')
    return index, entry, members, reader.data[:prefix_end]


def augment(runtime_path, client_path, output, paths):
    runtime, client = Package(runtime_path), Package(client_path)
    if (runtime.version, runtime.licensee, runtime.envelope) != (126, 0, 'plain'):
        raise FormatError('Expected the plain 2226 compiler package')
    if runtime.names[0] != 'None':
        raise FormatError('Unexpected None name index')
    data = bytearray(runtime.data)
    names, flags = list(runtime.names), list(runtime.name_flags)
    lookup = {name.casefold(): i for i, name in enumerate(names)}
    exports = [replace(e) for e in runtime.exports]
    edits = {}
    enum_class = next((-i for i, e in enumerate(runtime.imports, 1) if runtime.ref(-i) == 'Core.Enum'), None)
    if enum_class is None:
        raise FormatError('Core.Enum import missing')

    def name_index(source_index):
        text = client.name(source_index)
        if text.casefold() not in lookup:
            lookup[text.casefold()] = len(names)
            names.append(text)
            flags.append(client.name_flags[source_index])
        return lookup[text.casefold()]

    def save_export(index, payload):
        entry = exports[index - 1]
        entry.offset, entry.size = len(data), len(payload)
        data.extend(payload)

    for path in paths:
        _, source, members, _ = enum_members(client, path)
        target_names = [client.name(i) for i in members]
        existing = [(i, e) for i, e in enumerate(runtime.exports, 1)
                    if runtime.ref(i).casefold() == path.casefold() and runtime.ref(e.cls) == 'Core.Enum']
        if existing:
            index, entry, old_members, prefix = enum_members(runtime, path)
            old_names = [runtime.name(i) for i in old_members]
            new_codes = {name.casefold(): i for i, name in enumerate(target_names)}
            for code, name in enumerate(old_names):
                if name.casefold() in new_codes and new_codes[name.casefold()] != code:
                    raise FormatError(f'Enum changes an existing native value: {path}.{name}')
            if old_names == target_names:
                continue
        else:
            owner_name, _, _ = path.rpartition('.')
            owners = [(i, e) for i, e in enumerate(runtime.exports, 1)
                      if runtime.ref(i).casefold() == owner_name.casefold() and e.cls == 0]
            if len(owners) != 1:
                raise FormatError(f'Enum owner missing: {owner_name}')
            owner_index, _ = owners[0]
            owner = exports[owner_index - 1]
            payload = bytes(data[owner.offset:owner.offset + owner.size])
            r = Reader(payload)
            for _ in range(3):
                r.index()  # Super, Next, ScriptText
            start = r.pos
            old_child = r.index()
            index = len(exports) + 1
            prefix = compact(0) + compact(0) + compact(old_child)
            exports.append(Entry(source.name, owner_index, enum_class, flags=source.flags,
                                 name_index=name_index(source.name_index)))
            save_export(owner_index, payload[:start] + compact(index) + payload[r.pos:])
        encoded = prefix + compact(len(members)) + b''.join(compact(name_index(i)) for i in members)
        save_export(index, encoded)
        edits[path] = dict(export=index, added=not bool(existing), members=target_names)

    name_offset = len(data)
    for name, bits in zip(names, flags):
        try:
            value = name.encode('latin1') + b'\0'
            data.extend(compact(len(value)) + value)
        except UnicodeEncodeError:
            value = name.encode('utf-16le') + b'\0\0'
            data.extend(compact(-len(value) // 2) + value)
        data.extend(struct.pack('<I', bits))
    export_offset = len(data)
    for entry in exports:
        data.extend(compact(entry.cls) + compact(entry.super) + struct.pack('<i', entry.outer))
        data.extend(compact(entry.name_index) + struct.pack('<I', entry.flags) + compact(entry.size))
        if entry.size:
            data.extend(compact(entry.offset))
    struct.pack_into('<4i', data, 12, len(names), name_offset, len(exports), export_offset)
    generations = struct.unpack_from('<i', data, 52)[0]
    if not 1 <= generations <= 100:
        raise FormatError('Unsupported generation table')
    struct.pack_into('<ii', data, 56 + 8 * (generations - 1), len(exports), len(names))
    # Distinct deterministic SDK GUID; source game packages are not overwritten.
    data[36:52] = hashlib.sha256(data).digest()[:16]
    output.write_bytes(data)
    return dict(runtime_sha256=runtime.sha256, client_sha256=client.sha256,
                result_sha256=hashlib.sha256(data).hexdigest(), enums=edits, compilation_only=True)
