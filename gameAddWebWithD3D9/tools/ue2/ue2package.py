"""Read-only UE2 123/37 and 126/0 inspector. Supports Ver111 package envelopes.

Only the function/bytecode subset required by the reference INT64 functions
is decoded. Unknown tokens fail explicitly; this is not a general decompiler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from dataclasses import dataclass


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def take(self, size: int) -> bytes:
        if size < 0 or self.pos < 0 or self.pos + size > len(self.data):
            raise FormatError(f"Truncated data at {self.pos:#x}, size {size}")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def byte(self):
        return self.unpack('<B')

    def index(self):
        first = self.byte()
        value, shift, more = first & 63, 6, first & 64
        for part in range(4):
            if not more:
                return -value if first & 128 else value
            b = self.byte()
            if part == 3 and b & 0xE0:
                raise FormatError('Compact index exceeds 32 bits')
            value |= (b & 127) << shift
            shift += 7
            more = b & 128
        if more:
            raise FormatError('Unterminated compact index')
        if value > (0x80000000 if first & 128 else 0x7fffffff):
            raise FormatError('Compact index overflow')
        return -value if first & 128 else value

    def string(self):
        size = self.index()
        width = 2 if size < 0 else 1
        raw = self.take(abs(size) * width)
        if size and raw[-width:] != b'\0' * width:
            raise FormatError('Unterminated package string')
        return raw[:-width].decode('utf-16le' if size < 0 else 'latin1') if size else ''


@dataclass
class Entry:
    name: str
    outer: int
    cls: int | str
    size: int = 0
    offset: int = 0
    flags: int = 0
    super: int = 0
    name_index: int = 0
    class_package: str = ''


class Package:
    def __init__(self, path: Path):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.data, self.envelope = raw, 'plain'
        # Both supplied envelopes use a 28-byte UTF-16 header and XOR 0xAC.
        # Validate the decoded package signature/version below in either case.
        for envelope in ('Lineage2Ver111', 'GamekitData111'):
            marker = envelope.encode('utf-16le')
            if raw.startswith(marker):
                self.data = bytes(b ^ 0xAC for b in raw[len(marker):])
                self.envelope = envelope
                break
        r = Reader(self.data)
        if r.unpack('<I') != 0x9E2A83C1:
            raise FormatError('Unsupported envelope or invalid Unreal package signature')
        self.version, self.licensee = r.unpack('<H'), r.unpack('<H')
        if (self.version, self.licensee) not in ((123, 0), (123, 37), (126, 0)):
            raise FormatError(f'Unsupported package version {self.version}/{self.licensee}')
        self.flags = r.unpack('<I')
        nc, no, ec, eo, ic, io = (r.unpack('<i') for _ in range(6))
        for count, offset in ((nc, no), (ec, eo), (ic, io)):
            if count < 0 or count > len(self.data) or not 0 <= offset < len(self.data):
                raise FormatError('Invalid table bounds')
        self.names, self.name_flags = [], []
        r.pos = no
        for _ in range(nc):
            self.names.append(r.string())
            self.name_flags.append(r.unpack('<I'))
        self.imports, self.exports = [], []
        r.pos = io
        for _ in range(ic):
            class_package = self.name(r.index())
            cls = self.name(r.index())
            outer, name = r.unpack('<i'), self.name(r.index())
            self.imports.append(Entry(name, outer, cls, class_package=class_package))
        r.pos = eo
        for _ in range(ec):
            cls, _super = r.index(), r.index()
            outer, name_index = r.unpack('<i'), r.index()
            name = self.name(name_index)
            flags, size = r.unpack('<I'), r.index()
            offset = r.index() if size else 0
            if size < 0 or offset < 0 or offset + size > len(self.data):
                raise FormatError('Invalid export serial bounds')
            self.exports.append(Entry(name, outer, cls, size, offset, flags, _super, name_index))
        self._ref_cache = {0: 'None'}
        for e in self.imports + self.exports:
            self.ref(e.outer)
            if isinstance(e.cls, int):
                self.ref(e.cls)
        self._exports_by_path = {}
        for index, entry in enumerate(self.exports, 1):
            self._exports_by_path.setdefault(self.ref(index), []).append((index, entry))

    def name(self, index):
        if not 0 <= index < len(self.names):
            raise FormatError(f'Invalid name index {index}')
        return self.names[index]

    def ref(self, index, seen=None):
        if index in self._ref_cache:
            return self._ref_cache[index]
        seen = set() if seen is None else seen
        if index in seen:
            raise FormatError('Cycle in outer references')
        seen.add(index)
        table, i = (self.exports, index - 1) if index > 0 else (self.imports, -index - 1)
        if not 0 <= i < len(table):
            raise FormatError(f'Invalid object reference {index}')
        e = table[i]
        result = (self.ref(e.outer, seen) + '.' if e.outer else '') + e.name
        self._ref_cache[index] = result
        return result

    def find(self, name):
        matches = self._exports_by_path.get(name, [])
        if len(matches) != 1:
            raise FormatError(f'Expected one export {name!r}, got {len(matches)}')
        return matches[0]

    def summary(self):
        return dict(file=str(self.path), sha256=self.sha256, envelope=self.envelope,
                    version=self.version, licensee=self.licensee, names=len(self.names),
                    imports=len(self.imports), exports=len(self.exports))

    def class_flags(self, name):
        _, e = self.find(name)
        if e.cls != 0:
            raise FormatError(f'{name} is not a class')
        r = Reader(self.data[e.offset:e.offset + e.size])
        # UClass objects have no leading tagged-property list. UField/UStruct
        # serialization follows directly, then UState and UClass flags.
        fields = [r.index() for _ in range(4)]
        if fields[0] != e.super:
            raise FormatError('Class superclass mismatch')
        if self.name(r.index()) != e.name:
            raise FormatError('Class friendly name mismatch')
        r.index()  # CppText
        r.take(8)  # Line/TextPos
        size = r.unpack('<i')
        if size < 0 or size > len(self.data) * 4:
            raise FormatError('Invalid class script size')
        decoder = Bytecode(self, r)
        while decoder.pc < size:
            decoder.expression()
        if decoder.pc != size:
            raise FormatError('Class script size mismatch')
        r.take(8 + 8 + 2 + 4)  # ProbeMask, IgnoreMask, LabelTableOffset, StateFlags
        return r.unpack('<I')

    def function(self, name):
        _, e = self.find(name)
        if self.ref(e.cls) != 'Core.Function':
            raise FormatError(f'{name} is not a function')
        r = Reader(self.data[e.offset:e.offset + e.size])
        if e.flags & 0x02000000:  # RF_HasStack
            raise FormatError('Function with serialized execution stack is unsupported')
        if self.name(r.index()) != 'None':
            raise FormatError('Function with tagged properties is unsupported')
        fields = [self.ref(r.index()) for _ in range(4)]
        friendly = self.name(r.index())
        cpp_text = self.ref(r.index())
        line, textpos, memory_size = (r.unpack('<i') for _ in range(3))
        if memory_size < 0 or memory_size > len(self.data) * 4:
            raise FormatError('Invalid in-memory script size')
        decoder = Bytecode(self, r)
        while decoder.pc < memory_size:
            decoder.expression()
        if decoder.pc != memory_size:
            raise FormatError(f'Script memory size mismatch: {decoder.pc} != {memory_size}')
        native, precedence, flags = r.unpack('<H'), r.byte(), r.unpack('<I')
        replication = r.unpack('<H') if flags & 0x40 else None
        if r.pos != len(r.data):
            raise FormatError(f'{name}: {len(r.data) - r.pos} unconsumed bytes')
        return dict(name=name, fields=fields, friendly=friendly, cpp_text=cpp_text,
                    line=line, textpos=textpos, memory_size=memory_size, native=native,
                    precedence=precedence, flags=flags, replication=replication,
                    instructions=decoder.rows)

    def state(self, name):
        _, e = self.find(name)
        if self.ref(e.cls) != 'Core.State':
            raise FormatError(f'{name} is not a state')
        r = Reader(self.data[e.offset:e.offset + e.size])
        if self.name(r.index()) != 'None':
            raise FormatError('State tagged properties are unsupported')
        fields = [self.ref(r.index()) for _ in range(4)]
        friendly, cpp_text = self.name(r.index()), self.ref(r.index())
        line, textpos, size = (r.unpack('<i') for _ in range(3))
        if not 0 <= size <= len(self.data) * 4:
            raise FormatError('Invalid state script size')
        decoder = Bytecode(self, r)
        while decoder.pc < size:
            decoder.expression()
        if decoder.pc != size:
            raise FormatError('State script size mismatch')
        probe, ignore, label_offset, flags = r.unpack('<Q'), r.unpack('<Q'), r.unpack('<H'), r.unpack('<I')
        if r.pos != len(r.data):
            raise FormatError('State has trailing data')
        return dict(name=name, fields=fields, friendly=friendly, cpp_text=cpp_text, line=line, textpos=textpos,
                    memory_size=size, probe=probe, ignore=ignore, label_offset=label_offset,
                    flags=flags, instructions=decoder.rows)


CASTS = {0x5A: 'byte_to_int64', 0x5B: 'int_to_int64', 0x5C: 'bool_to_int64',
         0x5D: 'float_to_int64', 0x5E: 'string_to_int64', 0x5F: 'int64_to_byte',
         0x60: 'int64_to_int', 0x61: 'int64_to_bool', 0x62: 'int64_to_float',
         0x63: 'int64_to_string'}


class Bytecode:
    def __init__(self, package, reader):
        self.package, self.r = package, reader
        self.pc, self.rows = 0, []

    def raw(self, fmt):
        self.pc += struct.calcsize(fmt)
        return self.r.unpack(fmt)

    def reference(self, is_name=False):
        # Compact serialized references expand to four bytes in script memory.
        self.pc += 4
        i = self.r.index()
        return self.package.name(i) if is_name else self.package.ref(i)

    def expression(self, depth=0):
        if depth > 128:
            raise FormatError('Bytecode nesting limit exceeded')
        pc, offset = self.pc, self.r.pos
        op = self.raw('<B')
        row = dict(pc=pc, serial=offset, depth=depth, opcode=f'{op:02x}')
        self.rows.append(row)
        child = lambda: self.expression(depth + 1)
        if op >= 0x60:
            index = ((op - 0x60) << 8) + self.raw('<B') if op < 0x70 else op
            row.update(kind='native', index=index)
            while child() != 0x16:
                pass
        elif op in (0, 1, 2, 0x29):
            row.update(kind={0: 'local', 1: 'instance', 2: 'default', 0x29: 'native_parameter'}[op], value=self.reference())
        elif op in (0x04, 0x0F, 0x14):
            row['kind'] = {4: 'return', 15: 'assign', 20: 'assign_bool'}[op]
            child()
            if op != 4:
                child()
        elif op == 0x39:
            cast = self.raw('<B')
            row.update(kind='cast', cast=f'{cast:02x}', value=CASTS.get(cast, f'cast_{cast:02x}'))
            child()
        elif op == 0x2d:
            row['kind'] = 'bool_variable'
            child()
        elif op == 0x18:
            row.update(kind='skip', size=self.raw('<H'))
            row['skip_end'] = self.pc + row['size']
            child()
        elif op in (0x0d, 0x0e, 0x37):
            row['kind'] = {0x0d: 'goto_label', 0x0e: 'discard_string', 0x37: 'array_length'}[op]
            child()
        elif op == 0x09:
            row.update(kind='assert', line=self.raw('<H'))
            child()
        elif op in (0x10, 0x1a, 0x40, 0x41, 0x45, 0x11):
            row['kind'] = {0x10: 'dynamic_array_element', 0x1a: 'array_element', 0x40: 'array_insert',
                           0x41: 'array_remove', 0x45: 'assign_delegate', 0x11: 'new'}[op]
            for _ in range(4 if op == 0x11 else 3 if op in (0x40, 0x41) else 2):
                child()
        elif op in (0x32, 0x33, 0x36):
            row.update(kind={0x32: 'struct_equal', 0x33: 'struct_not_equal', 0x36: 'struct_member'}[op],
                       value=self.reference())
            child()
            if op != 0x36:
                child()
        elif op == 0x2f:
            row['kind'] = 'iterator'
            child()
            row['target'] = self.raw('<H')
        elif op == 0x0c:
            row.update(kind='label_table', labels=[])
            if self.pc & 3:
                raise FormatError('Misaligned label table')
            while True:
                name, target = self.reference(True), self.raw('<I')
                row['labels'].append((name, target))
                if name == 'None':
                    break
        elif op in (0x06, 0x07, 0x0A):
            row.update(kind={6: 'jump', 7: 'jump_if_not', 10: 'case'}[op], target=self.raw('<H'))
            if op == 7 or (op == 10 and row['target'] != 65535):
                child()
        elif op == 5:
            row.update(kind='switch', size=self.raw('<B'))
            child()
        elif op == 0x1C:
            row.update(kind='final_call', value=self.reference())
            while child() != 0x16:
                pass
        elif op in (0x1B, 0x38):
            row.update(kind='virtual_call' if op == 0x1B else 'global_call', value=self.reference(True))
            while child() != 0x16:
                pass
        elif op in (0x19, 0x12):
            row['kind'] = 'context' if op == 0x19 else 'class_context'
            child()
            row.update(skip=self.raw('<H'), result_size=self.raw('<B'))
            row['skip_end'] = self.pc + row['skip']
            child()
        elif op in (0x13, 0x2E):
            row.update(kind='class_cast' if op == 0x13 else 'dynamic_cast', value=self.reference())
            child()
        elif op in (0x1D, 0x1E, 0x24, 0x2C):
            fmt = {0x1D: '<i', 0x1E: '<f', 0x24: '<B', 0x2C: '<B'}[op]
            row.update(kind='constant', value=self.raw(fmt))
        elif op in (0x1F, 0x34):
            chars = []
            while True:
                c = self.raw('<H' if op == 0x34 else '<B')
                if not c:
                    break
                chars.append(chr(c))
            row.update(kind='string', value=''.join(chars))
        elif op in (0x20, 0x21):
            row.update(kind='object' if op == 0x20 else 'name', value=self.reference(op == 0x21))
        elif op in (0x22, 0x23, 0x35):
            row.update(kind={0x22: 'rotation', 0x23: 'vector', 0x35: 'range'}[op],
                       value=[self.raw('<i' if op == 0x22 else '<f') for _ in range(2 if op == 0x35 else 3)])
        elif op == 0x43:
            row.update(kind='delegate_property', value=self.reference(), name=self.reference(True))
        elif op == 0x44:
            row.update(kind='delegate_name', value=self.reference(True))
        elif op == 0x42:
            row.update(kind='debug', version=self.raw('<i'), line=self.raw('<i'), pos=self.raw('<i'))
            chars = []
            while (c := self.raw('<B')) != 0:
                chars.append(chr(c))
            row['value'] = ''.join(chars)
        elif op in (0x08, 0x0B, 0x16, 0x17, 0x25, 0x26, 0x27, 0x28, 0x2A, 0x30, 0x31):
            row['kind'] = {8: 'stop', 11: 'nothing', 22: 'end_parameters', 23: 'self', 37: 'int_zero',
                           38: 'int_one', 39: 'true', 40: 'false', 42: 'none', 48: 'iterator_pop',
                           49: 'iterator_next'}[op]
        else:
            raise FormatError(f'Unsupported opcode {op:#x} at script PC {pc:#x}, serial {offset:#x}')
        return op


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--function', action='append', default=[])
    parser.add_argument('--export')
    args = parser.parse_args()
    p = Package(args.package)
    result = p.summary()
    if args.export:
        i, e = p.find(args.export)
        result['export'] = dict(index=i, name=p.ref(i), cls=p.ref(e.cls), size=e.size,
                                offset=e.offset, data=p.data[e.offset:e.offset + e.size].hex())
    result['functions'] = [p.function(f) for f in args.function]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
