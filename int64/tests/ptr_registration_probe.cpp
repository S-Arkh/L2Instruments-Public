// Exact-SDK, pre-initialization native UClass constructor experiment.
// This queues a probe class only; it does not provide PtrProperty support.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstring>

static_assert(sizeof(void*)==4,"Build Win32");
struct Guid { unsigned words[4]; };
alignas(16) static unsigned char storage[0x600];
static void __cdecl unexpectedConstruct(void*) {
    std::fputs("Unexpected instance construction in queue-only probe\n",stderr);
    ExitProcess(8);
}

int wmain(int argc,wchar_t** argv){
    if(argc!=3){std::fputs("Usage: ptr_registration_probe <copied SDK Core.dll> <dependency directory>\n",stderr);return 2;}
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    SetDllDirectoryW(argv[2]);
    HMODULE core=LoadLibraryW(argv[1]);
    if(!core){std::fprintf(stderr,"Load error: %lu\n",GetLastError());return 3;}
    // The caller must first verify the exact SDK hash with verify_profile.py.
    using Constructor=void (__thiscall*)(void*,int,unsigned,unsigned,void*,void*,Guid,
        const wchar_t*,const wchar_t*,const wchar_t*,unsigned,void (__cdecl*)(void*),void*);
    auto ctor=reinterpret_cast<Constructor>(GetProcAddress(core,
        "??0UClass@@QAE@W4EConstructorNative@@KKPAV0@1VFGuid@@PBG33KP6AXPAX@ZP8UObject@@AEXXZ@Z"));
    auto parent=GetProcAddress(core,"?PrivateStaticClass@UProperty@@0VUClass@@A");
    auto integer=GetProcAddress(core,"?PrivateStaticClass@UIntProperty@@0VUClass@@A");
    auto pending=reinterpret_cast<void**>(GetProcAddress(core,"?GAutoRegister@UObject@@0PAV1@A"));
    auto initialized=reinterpret_cast<int*>(GetProcAddress(core,"?GObjInitialized@UObject@@0HA"));
    auto staticCtor=GetProcAddress(core,"?StaticConstructor@UObject@@QAEXXZ");
    if(!ctor||!parent||!integer||!pending||!initialized||!staticCtor)return 4;
    if(*initialized){std::fputs("Expected pre-initialization SDK\n",stderr);return 5;}
    void* within=nullptr;
    std::memcpy(&within,reinterpret_cast<unsigned char*>(integer)+0x4b0,4);
    void* previous=*pending;
    std::memset(storage+0x520,0xa5,sizeof(storage)-0x520);
    ctor(storage,0,0x6c,0x8000,reinterpret_cast<void*>(parent),within,Guid{},
        L"PtrPropertyProbe",L"Core",L"",0x04084004,unexpectedConstruct,
        reinterpret_cast<void*>(staticCtor));
    void* link=nullptr;std::memcpy(&link,storage+4,4);
    unsigned size=0;std::memcpy(&size,storage+0x40,4);
    bool guard=true;for(unsigned i=0x520;i<sizeof(storage);++i)guard&=storage[i]==0xa5;
    std::printf("queued=%d previous-link=%d property-size=%u guard=%d\n",
        *pending==storage,link==previous,size,guard);
    std::fflush(stdout);
    // Keep module and static storage alive until OS process teardown. No instance
    // exists, and neither appInit nor registration processing is invoked here.
    return *pending==storage&&link==previous&&size==0x6c&&guard?0:6;
}
