// Windows-only research host. Run solely against an external working copy.
// No DLL exports are called; this tests loader/TLS initialization only.
#include <windows.h>
#include <cstdio>
#include <vector>

int wmain(int argc, wchar_t** argv) {
    if(argc!=2&&argc!=3) { std::fputs("Usage: native_load_probe <working-copy-dll> [private-image-output]\n",stderr);return 2; }
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    std::puts("loader_start");std::fflush(stdout);
    auto module=LoadLibraryExW(argv[1],nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);
    if(!module) { std::printf("loader_error=%lu\n",GetLastError());return 1; }
    std::printf("loader_success base=%p\n",static_cast<void*>(module));std::fflush(stdout);
    if(argc==3) {
        auto base=reinterpret_cast<const unsigned char*>(module);
        IMAGE_DOS_HEADER dos{};IMAGE_NT_HEADERS32 nt{};SIZE_T read=0;
        if(!ReadProcessMemory(GetCurrentProcess(),base,&dos,sizeof(dos),&read)||dos.e_magic!=IMAGE_DOS_SIGNATURE||
           !ReadProcessMemory(GetCurrentProcess(),base+dos.e_lfanew,&nt,sizeof(nt),&read)||nt.Signature!=IMAGE_NT_SIGNATURE||
           nt.OptionalHeader.SizeOfImage>512*1024*1024) return 3;
        auto size=nt.OptionalHeader.SizeOfImage;std::vector<unsigned char> image(size,0);unsigned unreadable=0;
        for(DWORD offset=0;offset<size;offset+=4096) {
            SIZE_T count=(size-offset<4096)?size-offset:4096;
            if(!ReadProcessMemory(GetCurrentProcess(),base+offset,image.data()+offset,count,&read)||read!=count)++unreadable;
        }
        // Memory layout (offset == RVA), not a rebuilt executable image.
        FILE* file=nullptr;
        if(_wfopen_s(&file,argv[2],L"wb")||!file)return 4;
        auto written=std::fwrite(image.data(),1,image.size(),file);std::fclose(file);
        std::printf("image_bytes=%lu unreadable_pages=%u written=%zu\n",size,unreadable,written);std::fflush(stdout);
    }
    // Exit without running detach routines from a partially initialized client.
    TerminateProcess(GetCurrentProcess(),0);
}
