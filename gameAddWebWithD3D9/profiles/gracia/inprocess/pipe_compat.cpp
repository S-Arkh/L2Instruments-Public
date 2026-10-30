#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "pipe_compat.h"
#include <winternl.h>
#include <cstring>
#include <cwchar>
#include <string>
#include <atomic>
#include <cstdio>
#include <algorithm>

namespace {
using NtIo=NTSTATUS(NTAPI*)(HANDLE,HANDLE,PVOID,PVOID,PIO_STATUS_BLOCK,PVOID,ULONG,PLARGE_INTEGER,PULONG);
using NtQueryFile=NTSTATUS(NTAPI*)(HANDLE,PIO_STATUS_BLOCK,PVOID,ULONG,FILE_INFORMATION_CLASS);
using ToError=ULONG(WINAPI*)(NTSTATUS);
using Read=BOOL(WINAPI*)(HANDLE,LPVOID,DWORD,LPDWORD,LPOVERLAPPED);
using Write=BOOL(WINAPI*)(HANDLE,LPCVOID,DWORD,LPDWORD,LPOVERLAPPED);
NtIo nativeRead=nullptr,nativeWrite=nullptr;
Read normalRead=nullptr;Write normalWrite=nullptr;
NtQueryFile queryFile=nullptr;ToError toError=nullptr;
pipecompat::Log logger=nullptr;
std::atomic<bool> enabled{false};
std::atomic<int> traces{0};

// Accept only the observed integrity.dll detour that rejects FILE_TYPE_PIPE.
// No ntdll instructions or integrity.dll pointers are modified.
NtIo originalIo(const char* name) {
    auto entry=reinterpret_cast<const unsigned char*>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),name));
    if(!entry || entry[0]!=0xe9)return nullptr;
    int displacement;memcpy(&displacement,entry+1,4);
    auto target=entry+5+displacement;
    HMODULE owner{};
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(target),&owner) || owner!=GetModuleHandleW(L"integrity.dll")){logger("Detour owner mismatch",0,target);return nullptr;}
    auto header=reinterpret_cast<const IMAGE_DOS_HEADER*>(owner);
    auto pe=reinterpret_cast<const IMAGE_NT_HEADERS*>(reinterpret_cast<const unsigned char*>(owner)+header->e_lfanew);
    auto imageEnd=reinterpret_cast<const unsigned char*>(owner)+pe->OptionalHeader.SizeOfImage;
    if(target+29>imageEnd)return nullptr;
    const unsigned char head[]={0xff,0x74,0x24,0x04,0xff,0x15};
    const unsigned char body[]={0x83,0xf8,0x03,0x75,0x08,0xb8,0x22,0x00,0x00,0xc0,0xc2,0x24,0x00,0xff,0x25};
    if(memcmp(target,head,sizeof(head)) || memcmp(target+10,body,sizeof(body))){logger("Detour bytes mismatch",0,target);return nullptr;}
    auto fileTypeSlot=*reinterpret_cast<void* const* const*>(target+6);
    auto fileTypeExport=GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetFileType");
    if(*fileTypeSlot!=reinterpret_cast<void*>(&GetFileType) && *fileTypeSlot!=reinterpret_cast<void*>(fileTypeExport)){logger("Detour GetFileType mismatch",0,*fileTypeSlot);return nullptr;}
    auto slot=*reinterpret_cast<NtIo const* const*>(target+25);
    MEMORY_BASIC_INFORMATION region{};
    if(!VirtualQuery(slot,&region,sizeof(region)) || region.State!=MEM_COMMIT || region.AllocationBase!=owner || reinterpret_cast<const unsigned char*>(slot)+sizeof(*slot)>imageEnd){logger("Detour slot mismatch",0,slot);return nullptr;}
    auto original=*slot;
    if(!VirtualQuery(reinterpret_cast<void*>(original),&region,sizeof(region)) || region.State!=MEM_COMMIT ||
        !(region.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))){logger("Detour trampoline mismatch",region.Protect,reinterpret_cast<void*>(original));return nullptr;}
    logger(name,0,target);
    return original;
}
bool webviewPipe(HANDLE file) {
    if(GetFileType(file)!=FILE_TYPE_PIPE)return false;
    struct { ULONG length; wchar_t name[1024]; } info{};
    IO_STATUS_BLOCK io{};
    NTSTATUS result=queryFile(file,&io,&info,sizeof(info),static_cast<FILE_INFORMATION_CLASS>(9));
    if(traces.fetch_add(1)<12) {
        char text[2048]{};
        std::snprintf(text,sizeof(text),"WebView pipe query length=%lu name=%.*ls",info.length,
            static_cast<int>(std::min<ULONG>(info.length/2,1023)),info.name);
        logger(text,result,file);
    }
    if(result<0 || info.length>sizeof(info.name) || (info.length%2))return false;
    std::wstring name(info.name,info.length/sizeof(wchar_t));
    // Mojo generates local pipes named mojo.<host PID>.<thread/random...>.
    const auto prefix=L"\\mojo."+std::to_wstring(GetCurrentProcessId())+L".";
    const auto local=L"\\LOCAL"+prefix;
    return name.compare(0,prefix.size(),prefix)==0 || name.compare(0,local.size(),local)==0;
}
BOOL transfer(NtIo operation,HANDLE file,PVOID buffer,DWORD bytes,LPDWORD transferred,LPOVERLAPPED overlap) {
    if(transferred)*transferred=0;
    IO_STATUS_BLOCK local{};
    auto io=overlap?reinterpret_cast<PIO_STATUS_BLOCK>(&overlap->Internal):&local;
    LARGE_INTEGER offset{};HANDLE event=nullptr;PVOID context=nullptr;
    if(overlap){
        offset.LowPart=overlap->Offset;offset.HighPart=overlap->OffsetHigh;
        overlap->Internal=0x103;event=overlap->hEvent;
        if(!(reinterpret_cast<ULONG_PTR>(event)&1))context=overlap;
    }
    NTSTATUS status=operation(file,event,nullptr,context,io,buffer,bytes,overlap?&offset:nullptr,nullptr);
    if(status==0x103 && !overlap){
        if(WaitForSingleObject(file,INFINITE)!=WAIT_OBJECT_0)return FALSE;
        status=io->Status;
    }
    if(status>=0 && status!=0x103){if(transferred)*transferred=static_cast<DWORD>(io->Information);return TRUE;}
    if(transferred && status==static_cast<NTSTATUS>(0x80000005))*transferred=static_cast<DWORD>(io->Information);
    SetLastError(toError(status));return FALSE;
}
BOOL WINAPI readPipe(HANDLE file,LPVOID buffer,DWORD bytes,LPDWORD transferred,LPOVERLAPPED overlap) {
    if(!enabled || !webviewPipe(file))return normalRead(file,buffer,bytes,transferred,overlap);
    return transfer(nativeRead,file,buffer,bytes,transferred,overlap);
}
BOOL WINAPI writePipe(HANDLE file,LPCVOID buffer,DWORD bytes,LPDWORD transferred,LPOVERLAPPED overlap) {
    if(!enabled || !webviewPipe(file))return normalWrite(file,buffer,bytes,transferred,overlap);
    return transfer(nativeWrite,file,const_cast<void*>(buffer),bytes,transferred,overlap);
}
bool replace(void** slot,void* value) {
    DWORD protection;
    if(!VirtualProtect(slot,sizeof(void*),PAGE_READWRITE,&protection))return false;
    InterlockedExchangePointer(slot,value);
    DWORD ignored;VirtualProtect(slot,sizeof(void*),protection,&ignored);return true;
}
}
bool pipecompat::Install(HMODULE runtime,Log log) {
    if(enabled)return true;
    logger=log;
    wchar_t flag[8]{};
    if(GetEnvironmentVariableW(L"GRACIA_WEBVIEW_PIPE_COMPAT",flag,8) && flag[0]==L'0'){log("Pipe compatibility explicitly disabled",0,nullptr);return false;}
    nativeRead=originalIo("NtReadFile");nativeWrite=originalIo("NtWriteFile");
    if(!nativeRead||!nativeWrite){log("Pipe compatibility: unsupported detour",ERROR_NOT_SUPPORTED,nullptr);return false;}
    auto nt=GetModuleHandleW(L"ntdll.dll");
    queryFile=reinterpret_cast<NtQueryFile>(GetProcAddress(nt,"NtQueryInformationFile"));
    toError=reinterpret_cast<ToError>(GetProcAddress(nt,"RtlNtStatusToDosError"));
    if(!queryFile||!toError)return false;
    auto base=reinterpret_cast<unsigned char*>(runtime);
    auto dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE)return false;
    auto pe=reinterpret_cast<IMAGE_NT_HEADERS*>(base+dos->e_lfanew);
    if(pe->Signature!=IMAGE_NT_SIGNATURE)return false;
    auto rva=pe->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if(!rva)return false;
    void** readSlot=nullptr;void** writeSlot=nullptr;
    for(auto desc=reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base+rva);desc->Name;++desc) {
        if(!desc->OriginalFirstThunk)continue;
        auto names=reinterpret_cast<IMAGE_THUNK_DATA*>(base+desc->OriginalFirstThunk);
        auto slots=reinterpret_cast<IMAGE_THUNK_DATA*>(base+desc->FirstThunk);
        for(;names->u1.AddressOfData;++names,++slots) {
            if(IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))continue;
            auto name=reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base+names->u1.AddressOfData)->Name;
            if(!strcmp(reinterpret_cast<char*>(name),"ReadFile"))readSlot=reinterpret_cast<void**>(&slots->u1.Function);
            if(!strcmp(reinterpret_cast<char*>(name),"WriteFile"))writeSlot=reinterpret_cast<void**>(&slots->u1.Function);
        }
    }
    if(!readSlot||!writeSlot){log("Pipe compatibility: runtime imports unavailable",ERROR_NOT_SUPPORTED,nullptr);return false;}
    HMODULE self{};
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(&readPipe),&self))return false;
    normalRead=reinterpret_cast<Read>(*readSlot);normalWrite=reinterpret_cast<Write>(*writeSlot);
    if(!replace(readSlot,reinterpret_cast<void*>(&readPipe)))return false;
    if(!replace(writeSlot,reinterpret_cast<void*>(&writePipe))){replace(readSlot,reinterpret_cast<void*>(normalRead));return false;}
    enabled=true;log("Pipe compatibility installed for WebView runtime imports",0,runtime);return true;
}
