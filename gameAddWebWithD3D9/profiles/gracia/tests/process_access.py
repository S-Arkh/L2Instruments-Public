"""Read-only diagnosis of WebView parent process access (Windows Python)."""
import ctypes
from ctypes import wintypes as w
import json
import sys
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]
results={}
for name,access in [('synchronize',0x100000),('query_limited',0x1000),('query',0x400),('vm_read',0x10),('duplicate',0x40),('all',0x1fffff)]:
    handle=k.OpenProcess(access,False,int(sys.argv[1]))
    results[name]={'success':bool(handle),'error':ctypes.get_last_error() if not handle else 0}
    if handle:k.CloseHandle(handle)
print(json.dumps(results,indent=2))
