// Instrumented in-process host. The shared/generated implementation remains
// the control implementation used by the proven helper build.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>
#include <float.h>
#include <cstdio>
#include <algorithm>
#include <WebView2.h>
#include <wrl.h>
#include <psapi.h>
#include "pipe_compat.h"

namespace browserdiagnostic {
wchar_t logPath[32768]{};
DWORD sta=0;
using CreateEnvironment=HRESULT(STDAPICALLTYPE*)(PCWSTR,PCWSTR,ICoreWebView2EnvironmentOptions*,ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*);
CreateEnvironment originalCreate=nullptr;
void record(const char* event, DWORD code=0, const void* address=nullptr) {
    if(!logPath[0])return;
    char line[1024]{};
    HMODULE module{};wchar_t name[MAX_PATH]{};
    if(address && GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(address),&module))GetModuleFileNameW(module,name,MAX_PATH);
    int count=std::snprintf(line,sizeof(line),"tick=%llu pid=%lu tid=%lu sta=%lu %s code=0x%08lx address=%p module=%ls rva=0x%lx\r\n",
        GetTickCount64(),GetCurrentProcessId(),GetCurrentThreadId(),sta,event,code,address,name,
        address&&module?static_cast<unsigned long>(reinterpret_cast<ULONG_PTR>(address)-reinterpret_cast<ULONG_PTR>(module)):0);
    HANDLE file=CreateFileW(logPath,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file!=INVALID_HANDLE_VALUE){DWORD written;WriteFile(file,line,static_cast<DWORD>(count>0?std::min(count,1023):0),&written,nullptr);CloseHandle(file);}
}
LONG CALLBACK exception(EXCEPTION_POINTERS* info) {
    // Observe first-chance failures; do not swallow or alter exception handling.
    record("first-chance",info->ExceptionRecord->ExceptionCode,info->ExceptionRecord->ExceptionAddress);
    return EXCEPTION_CONTINUE_SEARCH;
}
void api(const char* name,const void* address) {
    char text[256]{};int length=std::snprintf(text,sizeof(text),"%s bytes=",name);
    for(int i=0;i<16;++i)length+=std::snprintf(text+length,sizeof(text)-length,"%02x",static_cast<const unsigned char*>(address)[i]);
    record(text,0,address);
}
HRESULT STDAPICALLTYPE createEnvironment(PCWSTR folder,PCWSTR profile,ICoreWebView2EnvironmentOptions* options,ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler* handler) {
    Microsoft::WRL::ComPtr<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler> original=handler;
    return originalCreate(folder,profile,options,Microsoft::WRL::Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
        [original](HRESULT hr,ICoreWebView2Environment* environment)->HRESULT {
            record("Environment callback",hr);
            if(environment) {
                HMODULE runtime{};
                auto method=(*reinterpret_cast<void***>(environment))[0];
                GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(method),&runtime);
                if(runtime)pipecompat::Install(runtime,record);
                LPWSTR version{};environment->get_BrowserVersionString(&version);
                char text[512]{};std::snprintf(text,sizeof(text),"Runtime version=%ls",version?version:L"unknown");record(text);CoTaskMemFree(version);
                Microsoft::WRL::ComPtr<ICoreWebView2Environment5> events;
                if(SUCCEEDED(environment->QueryInterface(IID_PPV_ARGS(&events)))) {
                    EventRegistrationToken token{};
                    events->add_BrowserProcessExited(Microsoft::WRL::Callback<ICoreWebView2BrowserProcessExitedEventHandler>(
                        [](ICoreWebView2Environment*,ICoreWebView2BrowserProcessExitedEventArgs* args)->HRESULT {
                            UINT32 pid{};COREWEBVIEW2_BROWSER_PROCESS_EXIT_KIND kind{};
                            args->get_BrowserProcessId(&pid);args->get_BrowserProcessExitKind(&kind);
                            char event[128]{};std::snprintf(event,sizeof(event),"BrowserProcessExited pid=%u",pid);record(event,kind);return S_OK;
                        }).Get(),&token);
                }
            }
            HRESULT result=original->Invoke(hr,environment);record("Environment callback returned",result);return result;
        }).Get());
}
FARPROC WINAPI getProc(HMODULE module,LPCSTR name) {
    auto result=GetProcAddress(module,name);
    if(reinterpret_cast<ULONG_PTR>(name)>65535 && strcmp(name,"CreateCoreWebView2EnvironmentWithOptions")==0 && result) {
        originalCreate=reinterpret_cast<CreateEnvironment>(result);
        record("CreateEnvironment export",0,reinterpret_cast<void*>(result));
        return reinterpret_cast<FARPROC>(&createEnvironment);
    }
    return result;
}
BOOL WINAPI destroyWindow(HWND window) {record("DestroyWindow",0,window);return DestroyWindow(window);}
HRESULT WINAPI initializeCOM(LPVOID reserved,DWORD flags) {
    HMODULE module{};
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&sta),&module);
    GetModuleFileNameW(module,logPath,32768);
    wchar_t* slash=wcsrchr(logPath,L'\\');if(slash)wcscpy_s(slash+1,32768-(slash+1-logPath),L"inprocess-diagnostic.log");
    sta=GetCurrentThreadId();
    wchar_t verbose[8]{};
    const bool diagnostic=GetEnvironmentVariableW(L"GRACIA_WEBVIEW_DIAGNOSTICS",verbose,8)>0;
    if(diagnostic)AddVectoredExceptionHandler(1,exception);
    unsigned int fp=0;_controlfp_s(&fp,0,0);
    record("STA entry FP control",fp);
    HANDLE reader{},writer{};
    if(CreatePipe(&reader,&writer,nullptr,0)) {
        DWORD written=0;BOOL ok=WriteFile(writer,"test",4,&written,nullptr);
        record("Anonymous pipe WriteFile",ok?0:GetLastError());
        CloseHandle(reader);CloseHandle(writer);
    }
    record("STA DPI awareness",static_cast<DWORD>(GetAwarenessFromDpiAwarenessContext(GetThreadDpiAwarenessContext())));
    wchar_t dpi[8]{};
    if(GetEnvironmentVariableW(L"GRACIA_TEST_DPI",dpi,8)) {
        SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        record("STA isolated DPI awareness",static_cast<DWORD>(GetAwarenessFromDpiAwarenessContext(GetThreadDpiAwarenessContext())));
    }
    if(diagnostic) {
    record("ole32.CoInitializeEx",0,reinterpret_cast<void*>(&CoInitializeEx));
    record("ole32.CoCreateInstance",0,reinterpret_cast<void*>(&CoCreateInstance));
    record("kernel32.CreateProcessW",0,reinterpret_cast<void*>(&CreateProcessW));
    api("CoInitializeEx",reinterpret_cast<void*>(&CoInitializeEx));
    api("CoUninitialize",reinterpret_cast<void*>(&CoUninitialize));
    api("GetMessageW",reinterpret_cast<void*>(&GetMessageW));
    api("CreateProcessW",reinterpret_cast<void*>(&CreateProcessW));
    api("CreateNamedPipeW",reinterpret_cast<void*>(&CreateNamedPipeW));
    api("GetCurrentProcessId",reinterpret_cast<void*>(&GetCurrentProcessId));
    api("GetCurrentThreadId",reinterpret_cast<void*>(&GetCurrentThreadId));
    api("DuplicateHandle",reinterpret_cast<void*>(&DuplicateHandle));
    api("GetFileType",reinterpret_cast<void*>(&GetFileType));
    for(auto name:{"NtCreateNamedPipeFile","NtOpenProcess","NtQueryInformationProcess","NtQueryInformationFile","NtFsControlFile","NtReadFile","NtWriteFile","NtCreateUserProcess"})
        api(name,reinterpret_cast<void*>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),name)));
    for(ULONG_PTR address=0;address<0x80000000;) {
        MEMORY_BASIC_INFORMATION region{};
        if(!VirtualQuery(reinterpret_cast<void*>(address),&region,sizeof(region)))break;
        if(region.Type==MEM_IMAGE && region.BaseAddress==region.AllocationBase) {
            char mapped[1024]{};GetMappedFileNameA(GetCurrentProcess(),region.AllocationBase,mapped,sizeof(mapped));
            record(mapped,0,region.AllocationBase);
        }
        ULONG_PTR next=reinterpret_cast<ULONG_PTR>(region.BaseAddress)+region.RegionSize;
        if(next<=address)break;address=next;
    }
    }
    HRESULT hr=CoInitializeEx(reserved,flags);
    record("CoInitializeEx",hr);
    return hr;
}
}

#define CoInitializeEx browserdiagnostic::initializeCOM
#define GetProcAddress browserdiagnostic::getProc
#define DestroyWindow browserdiagnostic::destroyWindow
#include "../native/web_frames.cpp"
#undef CoInitializeEx
#undef GetProcAddress
#undef DestroyWindow
