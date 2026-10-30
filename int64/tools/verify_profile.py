"""Check the exact compiler ABI and independently extract client INT64 registrations."""
import hashlib
import json
import struct
from pathlib import Path


from local_paths import ROOT, SYSTEM, CLIENT
HASHES = {
    'Editor.dll': 'd64995c1282956c6e9d67dd70715a69b5101331aa727a2d44b03e25fd7f2cd2e',
    'Core.dll': '5bff274734cae994353a8c60f4bfe1087dbdd9aa3883c7b2a7eff6ea2f51dc7e',
    'UCC.exe': 'c68ba1ce0eab03af23b04dc1c991c3f1cc047a8a2076c6850e3071892806fb65',
}


class PE:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        pe = struct.unpack_from('<I', self.data, 0x3c)[0]
        if self.data[:2] != b'MZ' or self.data[pe:pe + 4] != b'PE\0\0':
            raise ValueError('Invalid PE')
        machine, count = struct.unpack_from('<HH', self.data, pe + 4)
        optional_size = struct.unpack_from('<H', self.data, pe + 20)[0]
        opt = pe + 24
        if machine != 0x14c or struct.unpack_from('<H', self.data, opt)[0] != 0x10b:
            raise ValueError('Expected x86 PE32')
        self.base = struct.unpack_from('<I', self.data, opt + 28)[0]
        self.sections = []
        for i in range(count):
            off = opt + optional_size + i * 40
            name = self.data[off:off + 8].rstrip(b'\0').decode('ascii')
            _, rva, size, raw = struct.unpack_from('<4I', self.data, off + 8)
            self.sections.append((name, rva, size, raw))
        self.exports = {}
        export_rva, export_size = struct.unpack_from('<II', self.data, opt + 96)
        if not export_rva:
            return
        header = self.rva(export_rva, 40)
        functions, names, function_table, name_table, ordinal_table = struct.unpack_from('<5I', header, 20)
        for i in range(names):
            n = struct.unpack('<I', self.rva(name_table + i * 4, 4))[0]
            ordinal = struct.unpack('<H', self.rva(ordinal_table + i * 2, 2))[0]
            if ordinal >= functions:
                raise ValueError('Invalid export ordinal')
            target = struct.unpack('<I', self.rva(function_table + ordinal * 4, 4))[0]
            raw_name = bytearray()
            while (b := self.rva(n + len(raw_name), 1)) != b'\0':
                raw_name += b
            if not export_rva <= target < export_rva + export_size:
                self.exports[raw_name.decode('ascii')] = target

    def rva(self, address, size):
        for _, rva, length, raw in self.sections:
            if rva <= address and address + size <= rva + length:
                return self.data[raw + address - rva:raw + address - rva + size]
        raise ValueError(f'RVA {address:#x}+{size:#x} not in file-backed section')

    def section(self, name):
        _, rva, size, _ = next(s for s in self.sections if s[0] == name)
        return rva, self.rva(rva, size)

    def registrations(self):
        # MSVC-generated initializers, confirmed by disassembly:
        # mov eax,[pointer]; mov [duplicate-index],index; mov [table+4*index],eax.
        text_rva, text = self.section('.text')
        found = []
        for i in range(len(text) - 20):
            if text[i] != 0xa1 or text[i + 5:i + 7] != b'\xc7\x05' or text[i + 15] != 0xa3:
                continue
            pointer = struct.unpack_from('<I', text, i + 1)[0]
            index = struct.unpack_from('<I', text, i + 11)[0]
            slot = struct.unpack_from('<I', text, i + 16)[0]
            try:
                handler = struct.unpack('<I', self.rva(pointer - self.base, 4))[0]
            except ValueError:
                continue
            found.append(dict(handler_rva=handler - self.base, index=index,
                              table=slot - index * 4, initializer_rva=text_rva + i))
        return found


def verify():
    for name, expected in HASHES.items():
        actual = hashlib.sha256((SYSTEM / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Unsupported compiler {name}: {actual}')
    editor, core, client = PE(SYSTEM / 'Editor.dll'), PE(SYSTEM / 'Core.dll'), PE(CLIENT)
    if editor.base != 0x10200000:
        raise ValueError('Unexpected Editor base')
    # Verify the exact call site used by the primary-expression hook.
    call = editor.rva(0x784ce, 5)
    if call[0] != 0xe8:
        raise ValueError('GetToken call site changed')
    thunk = 0x784d3 + struct.unpack('<i', call[1:])[0]
    jump = editor.rva(thunk, 5)
    if jump[0] != 0xe9 or thunk + 5 + struct.unpack('<i', jump[1:])[0] != 0x7b590:
        raise ValueError('GetToken thunk changed')
    header_call = editor.rva(0x80ddb, 5)
    if header_call[0] != 0xe8 or 0x80de0 + struct.unpack('<i', header_call[1:])[0] != thunk:
        raise ValueError('Class-attribute GetToken call changed')
    if editor.rva(0x7141a, 3) != b'\xc2\x08\x00':
        raise ValueError('ConversionCost must pop two arguments (__thiscall)')
    if editor.rva(0x74976, 3) != b'\xc2\x10\x00':
        raise ValueError('FindField must pop four arguments (__thiscall)')
    symbols = [
        '?GetFullName@UObject@@QBEPBGPAG@Z',
        '?StaticClass@UStruct@@SAPAVUClass@@XZ',
        '?StaticFindObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBGH@Z',
        '?appThrowf@@YAXPBGZZ', '?appGetDllHandle@@YAPAXPBG@Z',
        '?GWarn@@3PAVFFeedbackContext@@A',
        '?StaticClass@UIntProperty@@SAPAVUClass@@XZ',
        '??0FName@@QAE@PBGW4EFindName@@@Z',
        '?StaticConstructObject@UObject@@SAPAV1@PAVUClass@@PAV1@VFName@@K1PAVFOutputDevice@@1@Z',
        '?ImportText@UStructProperty@@UBEPBGPBGPAEH@Z',
    ]
    for name in symbols:
        if name not in core.exports:
            raise ValueError(f'Missing required Core export: {name}')
    registrations = client.registrations()
    results, nonindexed = {}, []
    for name, rva in client.exports.items():
        if name.startswith('?exec') and ('INT64' in name):
            matches = [r for r in registrations if r['handler_rva'] == rva]
            if not matches and name.split('@')[0] in ('?execAddParamINT64', '?execGetParamINT64'):
                nonindexed.append(name)
                continue
            if len(matches) != 1:
                raise ValueError(f'Expected one native registration for {name}, got {len(matches)}')
            results[name.split('@')[0][1:]] = matches[0]
    return dict(hashes=HASHES, editor_base=hex(editor.base), core_exports=symbols,
                primary_get_token_return_rva=hex(0x784d3), client_registrations=results,
                nonindexed_native_exports=nonindexed)


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
