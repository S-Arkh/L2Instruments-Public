// Synthetic reproduction of the observed FILE_TYPE_PIPE rejection. Test-only;
// never installed in a client. No real integrity.dll is distributed by this test.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstring>

namespace {
unsigned char readHook[32]{},writeHook[32]{},readOriginal[16]{},writeOriginal[16]{};
void* readTrampoline=readOriginal;void* writeTrampoline=writeOriginal;
void* fileType=nullptr;
bool block(const char* name,unsigned char* hook,unsigned char* original,void** slot) {
    auto entry=reinterpret_cast<unsigned char*>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),name));
    if(!entry||entry[0]!=0xb8)return false; // expected x86 syscall stub
    const unsigned char code[]={0xff,0x74,0x24,0x04,0xff,0x15,0,0,0,0,
        0x83,0xf8,0x03,0x75,0x08,0xb8,0x22,0x00,0x00,0xc0,0xc2,0x24,0x00,0xff,0x25,0,0,0,0};
    memcpy(hook,code,sizeof(code));auto typeSlot=&fileType;
    memcpy(hook+6,&typeSlot,4);memcpy(hook+25,&slot,4);
    memcpy(original,entry,5);original[5]=0xe9;
    auto back=static_cast<LONG>(entry+5-(original+10));memcpy(original+6,&back,4);
    DWORD old;
    if(!VirtualProtect(hook,32,PAGE_EXECUTE_READWRITE,&old)||!VirtualProtect(original,16,PAGE_EXECUTE_READWRITE,&old))return false;
    if(!VirtualProtect(entry,5,PAGE_EXECUTE_READWRITE,&old))return false;
    entry[0]=0xe9;auto jump=static_cast<LONG>(hook-(entry+5));memcpy(entry+1,&jump,4);
    DWORD ignored;VirtualProtect(entry,5,old,&ignored);FlushInstructionCache(GetCurrentProcess(),nullptr,0);return true;
}
}
extern "C" __declspec(dllexport) BOOL InitializePipeBlock() {
    fileType=reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetFileType"));
    return block("NtReadFile",readHook,readOriginal,&readTrampoline)&&block("NtWriteFile",writeHook,writeOriginal,&writeTrampoline);
}
