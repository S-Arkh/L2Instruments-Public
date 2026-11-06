// Standalone client ABI evidence. Optional registration is process-local only.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include "client_abi.h"
#include "client_profile.h"

namespace {
l2client::Step nativeStep;
bool argumentsValid;
void __fastcall addProbe(void*,void*,l2client::FramePrefix* frame,void* result){
    l2client::Int64Value a{},b{};
    nativeStep(frame,frame->object,&a);
    nativeStep(frame,frame->object,&b);
    argumentsValid=*frame->code==0x16;
    if(argumentsValid)++frame->code;
    auto value=l2client::pack(l2client::unpack(a)+l2client::unpack(b));
    std::memcpy(result,&value,sizeof(value));
}

bool nativeCall(HMODULE core){
    auto table=reinterpret_cast<l2client::Native*>(GetProcAddress(core,l2client::TableExport));
    auto undefined=reinterpret_cast<l2client::Native>(GetProcAddress(core,l2client::UndefinedExport));
    auto registration=reinterpret_cast<l2client::RegisterNative>(GetProcAddress(core,l2client::RegisterExport));
    nativeStep=reinterpret_cast<l2client::Step>(GetProcAddress(core,l2client::StepExport));
    if(!table||!undefined||!registration||!nativeStep)return false;
    // Do not overwrite an existing client native.
    int index=4000;
    while(index<l2client::NativeTableSize&&table[index]!=undefined)++index;
    if(index==l2client::NativeTableSize){std::puts("{\"error\":\"no_unused_test_native_slot\"}");return false;}
    std::printf("{\"test_native_index\":%d,\"requested_slot_occupied\":%s}\n",index,index==4000?"false":"true");
    auto handler=reinterpret_cast<l2client::Native>(addProbe);
    registration(index,&handler);
    bool installed=table[index]==handler;
    bool passed=false;
    if(installed){
        // 5,000,000,000 + 10, both real client INT64 literals.
        unsigned char code[]={0x6f,0xa0,0x46,1,0,0,0,0,0xf2,5,0x2a,
                              0x46,0,0,0,0,10,0,0,0,0x16,0x0b};
        code[0]=static_cast<unsigned char>(0x60+(index>>8));code[1]=static_cast<unsigned char>(index);
        struct { l2client::FramePrefix frame{}; unsigned char spare[128]{}; } storage;
        struct { unsigned before; l2client::Int64Value value; unsigned after; } result{0x13572468,{},0x24681357};
        storage.frame.code=code;argumentsValid=false;
        nativeStep(&storage.frame,nullptr,&result.value);
        passed=argumentsValid&&storage.frame.code==code+21&&
               l2client::unpack(result.value)==5000000010LL&&
               result.before==0x13572468&&result.after==0x24681357;
    }
    registration(index,&undefined);
    return passed&&table[index]==undefined;
}
}

bool literals(l2client::Step step){
    // Standalone process only. Test dispatch, FFrame cursor and result layout
    // before attempting any extension registration or allocator installation.
    unsigned char integer[]={0x1d,0x78,0x56,0x34,0x12,0x0b};
    unsigned char wide[]={0x46,0x04,0x03,0x02,0x01,0x08,0x07,0x06,0x05,0x0b};
    struct { l2client::FramePrefix frame{}; unsigned char spare[128]{}; } storage;
    struct { unsigned before; l2client::Int64Value value; unsigned after; } result;
    result={0x13572468,{0,0},0x24681357};
    storage.frame.code=integer;
    step(&storage.frame,nullptr,&result.value);
    if(storage.frame.code!=integer+5||result.value.high!=0x12345678||result.value.low!=0||
       result.before!=0x13572468||result.after!=0x24681357)return false;
    result.value={0,0};storage.frame.code=wide;
    step(&storage.frame,nullptr,&result.value);
    return storage.frame.code==wide+9&&result.value.high==0x01020304&&result.value.low==0x05060708&&
           result.before==0x13572468&&result.after==0x24681357;
}

int wmain(int argc,wchar_t** argv){
    bool vm=argc==4&&std::wcscmp(argv[3],L"--vm-literals")==0;
    bool native=argc==4&&std::wcscmp(argv[3],L"--vm-native")==0;
    if(argc!=3&&!vm&&!native){
        std::fprintf(stderr,"Usage: client_abi_probe <Core.dll> <dependencies directory> [--vm-literals|--vm-native]\n");return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    SetDllDirectoryW(argv[2]);
    auto core=LoadLibraryW(argv[1]);
    if(!core){std::fprintf(stderr,"Core load error: %lu\n",GetLastError());return 3;}
    auto step=reinterpret_cast<const unsigned char*>(GetProcAddress(core,l2client::StepExport));
    if(!step){FreeLibrary(core);return 4;}
    MEMORY_BASIC_INFORMATION region{};
    if(!VirtualQuery(step,&region,sizeof(region))||region.State!=MEM_COMMIT||
       (region.Protect&(PAGE_GUARD|PAGE_NOACCESS))||
       step+sizeof(l2client::StepPrefix)>static_cast<const unsigned char*>(region.BaseAddress)+region.RegionSize){
        FreeLibrary(core);return 5;
    }
    std::printf("{\"step_prefix\":\"");
    for(unsigned i=0;i<sizeof(l2client::StepPrefix);++i)std::printf("%02x",step[i]);
    std::printf("\",\"known_step_prefix\":%s,\"abi_verified\":false}\n",
        std::memcmp(step,l2client::StepPrefix,sizeof(l2client::StepPrefix))==0?"true":"false");
    std::fflush(stdout);
    if(vm||native){
        auto dispatch=reinterpret_cast<l2client::Step>(GetProcAddress(core,l2client::StepExport));
        bool passed=literals(dispatch);
        std::printf("{\"vm_literals_passed\":%s,\"native_registration_tested\":false}\n",passed?"true":"false");
        if(!passed){FreeLibrary(core);return 6;}
    }
    if(native){
        bool passed=nativeCall(core);
        std::printf("{\"native_int64_call_and_restore_passed\":%s}\n",passed?"true":"false");
        if(!passed){FreeLibrary(core);return 7;}
    }
    FreeLibrary(core);return 0;
}
