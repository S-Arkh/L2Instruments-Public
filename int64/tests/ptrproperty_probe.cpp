// Isolated inspection of exported property entry points. Never calls a property method.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cwchar>
#include <initializer_list>
#include <cstring>
#include <string>

static_assert(sizeof(void*)==4,"Use the matching x86 process");
int wmain(int argc,wchar_t** argv){
    const bool exports=argc==5&&!std::wcscmp(argv[1],L"--exports");
    if(!exports&&(argc!=4||(std::wcscmp(argv[1],L"--mapped")&&std::wcscmp(argv[1],L"--load")))){
        std::fprintf(stderr,"Usage: ptrproperty_probe --mapped|--load <absolute Core.dll> <dependency directory>\n"
                            "       ptrproperty_probe --exports <absolute DLL> <dependency directory> <ASCII export filter>\n");return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    SetDllDirectoryW(argv[3]);
    const bool load=exports||std::wcscmp(argv[1],L"--load")==0;
    std::printf("stage=before-load mode=%s\n",load?"initialized":"mapped-no-initialization");
    std::fflush(stdout);
    HMODULE module=LoadLibraryExW(argv[2],nullptr,load?0:DONT_RESOLVE_DLL_REFERENCES);
    if(!module){std::fprintf(stderr,"Core.dll load failed: %lu\n",GetLastError());return 3;}
    std::printf("mode=%s\n",load?"initialized":"mapped-no-initialization");
    if(exports){
        std::string filter;
        for(auto p=argv[4];*p;++p){if(*p>127)return 4;filter.push_back(static_cast<char>(*p));}
        auto base=reinterpret_cast<const unsigned char*>(module);
        auto dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
        auto nt=reinterpret_cast<const IMAGE_NT_HEADERS*>(base+dos->e_lfanew);
        auto dir=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
        if(!dir.VirtualAddress)return 5;
        auto table=reinterpret_cast<const IMAGE_EXPORT_DIRECTORY*>(base+dir.VirtualAddress);
        auto names=reinterpret_cast<const DWORD*>(base+table->AddressOfNames);
        for(DWORD i=0;i<table->NumberOfNames;++i){
            auto name=reinterpret_cast<const char*>(base+names[i]);
            if(!std::strstr(name,filter.c_str()))continue;
            auto entry=reinterpret_cast<const unsigned char*>(GetProcAddress(module,name));
            MEMORY_BASIC_INFORMATION info{};
            if(!entry||!VirtualQuery(entry,&info,sizeof(info))||info.State!=MEM_COMMIT||
                (info.Protect&(PAGE_NOACCESS|PAGE_GUARD))||
                entry+256>static_cast<const unsigned char*>(info.BaseAddress)+info.RegionSize)continue;
            std::printf("%s rva=%08x bytes=",name,static_cast<unsigned>(entry-base));
            for(unsigned j=0;j<256;++j)std::printf("%02x",entry[j]);
            std::puts("");
        }
        FreeLibrary(module);return 0;
    }
    for(const char* name:{"?StaticClass@UPtrProperty@@SAPAVUClass@@XZ",
                         "?ExportCppItem@UPtrProperty@@UBEXAAVFOutputDevice@@H@Z",
                         "?SerializeItem@UPtrProperty@@UBEXAAVFArchive@@PAXH@Z",
                         "?Link@UPtrProperty@@UAEXAAVFArchive@@PAVUProperty@@@Z",
                         "?StaticClass@UIntProperty@@SAPAVUClass@@XZ"}){
        auto entry=reinterpret_cast<const unsigned char*>(GetProcAddress(module,name));
        std::printf("%s: ",name);
        if(!entry){std::puts("absent");continue;}
        MEMORY_BASIC_INFORMATION info{};
        if(!VirtualQuery(entry,&info,sizeof(info))||info.State!=MEM_COMMIT||
           (info.Protect&(PAGE_NOACCESS|PAGE_GUARD))||
           entry+16>static_cast<const unsigned char*>(info.BaseAddress)+info.RegionSize){
            std::puts("unreadable");continue;
        }
        for(int i=0;i<16;++i)std::printf("%02x",entry[i]);
        std::puts("");
    }
    FreeLibrary(module);return 0;
}
