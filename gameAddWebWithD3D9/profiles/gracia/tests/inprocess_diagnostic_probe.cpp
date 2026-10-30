// Run the existing frame/input suite with real client modules loaded first.
// This fixture does not launch, install into, or alter the client.
#define main frame_suite_main
#include "frame_probe.cpp"
#undef main
#include <float.h>
#include <objbase.h>

namespace clientfixture {
void* __fastcall allocate(void*,void*,unsigned size,const wchar_t*) { return HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,size); }
void __fastcall release(void*,void*,void* p) { if(p) HeapFree(GetProcessHeap(),0,p); }
void* __fastcall resize(void* self,void*,void* p,unsigned size,const wchar_t* tag) {
    if(!size){release(self,nullptr,p);return nullptr;}
    return p?HeapReAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,p,size):allocate(self,nullptr,size,tag);
}
void __fastcall noop(void*,void*) {}
void* methods[]={reinterpret_cast<void*>(allocate),reinterpret_cast<void*>(resize),reinterpret_cast<void*>(release),
    reinterpret_cast<void*>(noop),reinterpret_cast<void*>(noop),reinterpret_cast<void*>(noop),reinterpret_cast<void*>(noop)};
struct { void** vtable; } heap{methods};
}
int wmain(int argc,wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    if(argc>1) SetDllDirectoryW(argv[1]);
    for(int i=2;i<argc;++i) {
        auto path=std::filesystem::path(argv[1])/argv[i];
        HMODULE module=LoadLibraryW(path.c_str());
        std::wprintf(L"LOAD %s => %p error=%lu FP=%08x\n",path.c_str(),module,module?0:GetLastError(),_controlfp(0,0));
        std::fflush(stdout);
        if(!module) return 3;
        using Initialize=BOOL(*)();
        auto initialize=reinterpret_cast<Initialize>(GetProcAddress(module,"InitializePipeBlock"));
        if(initialize && !initialize())return 4;
        auto allocator=reinterpret_cast<void**>(GetProcAddress(module,"?GMalloc@@3PAVFMalloc@@A"));
        if(allocator) *allocator=&clientfixture::heap;
    }
    int result=frame_suite_main();
    if(GetModuleHandleW(L"integrity.dll")) {
        HANDLE r{},w{};DWORD n{};
        bool stillBlocked=CreatePipe(&r,&w,nullptr,0) && !WriteFile(w,"x",1,&n,nullptr) && GetLastError()==ERROR_ACCESS_DENIED;
        if(r)CloseHandle(r);if(w)CloseHandle(w);
        std::ofstream report(directory/L"pipe-isolation.json");
        report<<"{\"frame_suite_exit\":"<<result<<",\"ordinary_pipe_still_blocked\":"<<(stillBlocked?"true":"false")<<"}";
        report.close();if(!stillBlocked)result=10;
    }
    std::fflush(stdout);
    // Loaded UE modules expect a game teardown; do not run their static cleanup
    // against a standalone fixture. This exit also exercises browser detach.
    ExitProcess(result);
}
