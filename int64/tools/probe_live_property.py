"""Read small property-code samples from an existing x86 client; never execute/write."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path

from verify_profile import PE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--symbol', action='append', default=[])
    parser.add_argument('--rva', action='append', type=lambda s: int(s, 0), default=[])
    parser.add_argument('--size', type=int, default=256)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt' or not 1 <= args.size <= 4096:
        parser.error('Requires Windows and sample size 1..4096')
    core = args.core.resolve()
    pe = PE(core)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != args.sha256.lower():
        raise ValueError('Core hash mismatch')

    class Module(c.Structure):
        _fields_ = [('size', w.DWORD), ('id', w.DWORD), ('pid', w.DWORD),
                    ('global_count', w.DWORD), ('process_count', w.DWORD),
                    ('base', c.c_void_p), ('image_size', w.DWORD),
                    ('handle', w.HMODULE), ('name', w.WCHAR * 256),
                    ('path', w.WCHAR * 260)]

    k = c.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ('Module32FirstW', 'Module32NextW'):
        getattr(k, name).argtypes = [w.HANDLE, c.POINTER(Module)]
        getattr(k, name).restype = w.BOOL
    k.CloseHandle.argtypes = [w.HANDLE]
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p,
                                   c.c_size_t, c.POINTER(c.c_size_t)]
    k.ReadProcessMemory.restype = w.BOOL
    snapshot = k.CreateToolhelp32Snapshot(0x18, args.pid)
    if snapshot == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    base = image_size = None
    try:
        module = Module()
        module.size = c.sizeof(module)
        ok = k.Module32FirstW(snapshot, c.byref(module))
        while ok:
            if Path(module.path).resolve() == core:
                base, image_size = module.base, module.image_size
                break
            ok = k.Module32NextW(snapshot, c.byref(module))
    finally:
        k.CloseHandle(snapshot)
    if base is None:
        raise ValueError('Requested Core.dll is not loaded in this process')
    targets = []
    for symbol in args.symbol:
        matches = [(name, rva) for name, rva in pe.exports.items() if symbol in name]
        if not matches:
            raise ValueError('No export matches ' + symbol)
        targets.extend(matches)
    targets.extend(('rva', rva) for rva in args.rva)
    if not targets:
        parser.error('Specify --symbol or --rva')
    process = k.OpenProcess(0x1010, False, args.pid)
    if not process:
        raise c.WinError(c.get_last_error())
    rows = []
    try:
        for name, rva in dict.fromkeys(targets):
            if rva < 0 or rva + args.size > image_size:
                raise ValueError('Sample outside module')
            buffer = c.create_string_buffer(args.size)
            count = c.c_size_t()
            if not k.ReadProcessMemory(process, base + rva, buffer, args.size,
                                       c.byref(count)) or count.value != args.size:
                raise c.WinError(c.get_last_error())
            rows.append(dict(symbol=name, rva=rva, bytes=buffer.raw.hex()))
    finally:
        k.CloseHandle(process)
    result = dict(core_sha256=digest, base=base, samples=rows)
    # Exclusive creation prevents overwriting earlier observations.
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(f'Read {len(rows)} samples; saved {args.out}')


if __name__ == '__main__':
    main()
