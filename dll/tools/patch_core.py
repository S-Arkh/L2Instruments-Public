"""Patch a NEW COPY of a supported original client Core.dll to load ExtensionL2.dll.

Adds an import and a small entry-point wrapper. Existing section data, exports,
IAT addresses and function bodies are preserved. Never executes the input DLL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2] / 'int64'
sys.path.insert(0, str(ROOT / 'tools'))
from verify_profile import PE
from core_profiles import catalog, approved

CORE_SHA256 = next(p['sha256'] for p in catalog()['profiles'] if p['name'] == 'client_b3fb9af3')
CLEAR_HF_SHA256 = next(p['sha256'] for p in catalog()['profiles'] if p['name'] == 'clear_hf_0677e909')
CORE_PROFILES = {p['sha256']: p['name'] for p in catalog()['profiles']}


def align(value, alignment):
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError('Invalid PE alignment')
    return (value + alignment - 1) & -alignment


def checksum(data, checksum_offset):
    total = 0
    for i in range(0, len(data), 2):
        if checksum_offset <= i < checksum_offset + 4:
            continue
        word = data[i] | ((data[i + 1] if i + 1 < len(data) else 0) << 8)
        total += word
        total = (total & 0xffff) + (total >> 16)
    total = (total & 0xffff) + (total >> 16)
    return (total + len(data)) & 0xffffffff


def entry_stub(rva, original_entry, attach_iat):
    code = bytearray(b'\x55\x8b\xec')             # push ebp; mov ebp,esp
    code += b'\xff\x75\x10\xff\x75\x0c\xff\x75\x08'  # original DllMain args
    at = len(code)
    code += b'\xe8' + struct.pack('<i', original_entry - (rva + at + 5))
    code += b'\x85\xc0\x74\x00'                  # failed original attach -> return FALSE
    failed_jump = len(code) - 1
    code += b'\x83\x7d\x0c\x01\x75\x00'       # only DLL_PROCESS_ATTACH (1)
    reason_jump = len(code) - 1
    code += b'\x8b\x4d\x08\x51'                 # ecx=Core base; push Core base
    code += b'\xff\x91' + struct.pack('<I', attach_iat)  # call [Core+IAT RVA]
    done = len(code)
    code += b'\x8b\xe5\x5d\xc2\x0c\x00'      # restore frame; ret 12
    code[failed_jump] = done - failed_jump - 1
    code[reason_jump] = done - reason_jump - 1
    return bytes(code)


def patch_bytes(original, image):
    if original != image.data:
        raise ValueError('PE image and input bytes differ')
    digest = hashlib.sha256(original).hexdigest()
    approved(image)
    if digest not in CORE_PROFILES:
        raise ValueError('Unsupported Core.dll: use an original DLL matching a known client profile')
    pe = struct.unpack_from('<I', original, 0x3c)[0]
    optional = pe + 24
    count = struct.unpack_from('<H', original, pe + 6)[0]
    optional_size = struct.unpack_from('<H', original, pe + 20)[0]
    table = optional + optional_size
    section_alignment, file_alignment = struct.unpack_from('<II', original, optional + 32)
    headers_size = struct.unpack_from('<I', original, optional + 60)[0]
    end_headers = table + (count + 2) * 40
    first_raw = min(raw for _, _, size, raw in image.sections if size)
    if end_headers > min(headers_size, first_raw) or any(original[table + count * 40:end_headers]):
        raise ValueError('No unused space for two extra section headers')
    old_entry = struct.unpack_from('<I', original, optional + 16)[0]
    import_rva, import_size = struct.unpack_from('<II', original, optional + 104)
    descriptors = bytearray()
    for offset in range(0, import_size, 20):
        item = image.rva(import_rva + offset, 20)
        if not any(item):
            break
        descriptors += item
    else:
        raise ValueError('Import descriptor terminator missing')

    virtual_end = max(struct.unpack_from('<I', original, optional + 56)[0],
                      *(va + max(struct.unpack_from('<I', original, table + i * 40 + 8)[0], size)
                        for i, (_, va, size, _) in enumerate(image.sections)))
    code_rva = align(virtual_end, section_alignment)
    code_size = len(entry_stub(code_rva, old_entry, 0))
    data_rva = align(code_rva + code_size, section_alignment)
    imports = bytearray(descriptors + bytes(40))  # new DLL + zero terminator
    lookup_offset = align(len(imports), 4)
    iat_offset = lookup_offset + 8
    hint_offset = iat_offset + 8
    hint = b'\0\0ExtensionL2Attach\0'
    dll_offset = hint_offset + len(hint)
    imports += bytes(lookup_offset - len(imports))
    imports += struct.pack('<II', data_rva + hint_offset, 0) * 2
    imports += hint + b'ExtensionL2.dll\0'
    struct.pack_into('<5I', imports, len(descriptors), data_rva + lookup_offset, 0, 0,
                     data_rva + dll_offset, data_rva + iat_offset)
    stub = entry_stub(code_rva, old_entry, data_rva + iat_offset)
    code_raw = align(len(original), file_alignment)
    code_raw_size = align(len(stub), file_alignment)
    data_raw = code_raw + code_raw_size
    data_raw_size = align(len(imports), file_alignment)
    result = bytearray(original)
    result += bytes(data_raw + data_raw_size - len(result))
    result[code_raw:code_raw + len(stub)] = stub
    result[data_raw:data_raw + len(imports)] = imports
    for index, (name, va, size, raw, raw_size, flags) in enumerate([
            (b'.ndcode', code_rva, len(stub), code_raw, code_raw_size, 0x60000020),
            (b'.nddata', data_rva, len(imports), data_raw, data_raw_size, 0xc0000040)]):
        struct.pack_into('<8sIIIIIIHHI', result, table + (count + index) * 40,
                         name, size, va, raw_size, raw, 0, 0, 0, 0, flags)
    struct.pack_into('<H', result, pe + 6, count + 2)
    struct.pack_into('<I', result, optional + 16, code_rva)
    struct.pack_into('<I', result, optional + 56, align(data_rva + len(imports), section_alignment))
    for field, extra in ((4, code_raw_size), (8, data_raw_size)):
        old = struct.unpack_from('<I', original, optional + field)[0]
        struct.pack_into('<I', result, optional + field, old + extra)
    struct.pack_into('<II', result, optional + 104, data_rva, len(descriptors) + 40)
    # Invalidate bound-import metadata, if any: the loader resolves all imports.
    struct.pack_into('<II', result, optional + 96 + 11 * 8, 0, 0)
    struct.pack_into('<I', result, optional + 64, checksum(result, optional + 64))
    return bytes(result), dict(profile=CORE_PROFILES[digest], original_sha256=digest,
                               original_entry_rva=hex(old_entry), wrapper_rva=hex(code_rva),
                               import_directory_rva=hex(data_rva), attach_iat_rva=hex(data_rva + iat_offset),
                               added_sections=['.ndcode (RX)', '.nddata (RW)'])


def patch_core(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError('Output must be a new file, different from the original Core.dll')
    image = PE(source)
    result, report = patch_bytes(image.data, image)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(result)
    patched = PE(destination)
    if patched.exports != image.exports:
        raise ValueError('Export table changed unexpectedly')
    for _, rva, size, _ in image.sections:
        if patched.rva(rva, size) != image.rva(rva, size):
            raise ValueError('Original section contents changed')
    report.update(patched_sha256=hashlib.sha256(result).hexdigest(),
                  required_dll='ExtensionL2.dll', required_export='ExtensionL2Attach',
                  original_sections_preserved=True)
    destination.with_suffix('.patch.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(patch_core(args.source, args.output), indent=2))
