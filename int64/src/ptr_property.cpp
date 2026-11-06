#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "ptr_property.h"
#include <cstring>
#include <initializer_list>

namespace ucc64 {
namespace {
static_assert(sizeof(void*)==4);
struct Guid { unsigned words[4]; };
alignas(16) unsigned char storage[0x520];
void* table[46];
void** vtable=table;
using InstanceCtor=void (__thiscall*)(void*);
using Log=void (__thiscall*)(void*,const wchar_t*);
using Class=void* (__thiscall*)(void*);
InstanceCtor baseCtor;
Log output;
Class getClass;
void** warning;
bool registered;
void reportError(const wchar_t* message){
    if(warning&&*warning){
        using Report=void (__thiscall*)(void*,const wchar_t*,int);
        auto report=reinterpret_cast<Report>((*reinterpret_cast<void***>(*warning))[0]);
        report(*warning,message,0x315);
    }
}
void __cdecl construct(void* object){baseCtor(object);std::memcpy(object,&vtable,4);}
void __fastcall serialize(void*,void*,void*,void*,int){}
int __fastcall netSerialize(void*,void*,void*,void*,void*){return 1;}
void __fastcall exportCpp(void*,void*,void* device,int){output(device,L"FPtr");}
// Only the explicit null value is portable across processes. Never import addresses.
const wchar_t* __fastcall importText(void*,void*,const wchar_t* text,void* value,int){
    auto space=[](wchar_t c){return c==L' '||c==L'\t'||c==L'\r'||c==L'\n';};
    const wchar_t* start=text;
    if(start)while(space(*start))++start;
    if(start&&*start==L'0'){
        const wchar_t* end=start+1;
        while(space(*end))++end;
        if(!*end||*end==L','||*end==L')'){
            unsigned zero=0;std::memcpy(value,&zero,sizeof(zero));
            return end;
        }
    }
    // Defaults importing is outside the compiler's appThrowf catch boundary.
    // Report through the SDK feedback device and return its failure sentinel.
    reportError(L"Pointer defaults require literal 0");
    return nullptr;
}
void __fastcall exportText(void*,void*,wchar_t* text,void* value,void*,int){
    unsigned pointer=0;std::memcpy(&pointer,value,sizeof(pointer));
    *text=0;
    if(pointer){reportError(L"Nonzero pointer text export is unsupported");return;}
    text[0]=L'0';text[1]=0;
}
int __fastcall port(void* property,void*){
    auto bytes=static_cast<unsigned char*>(property);
    int dimension=0,size=0;
    std::memcpy(&dimension,bytes+0x34,4);std::memcpy(&size,bytes+0x38,4);
    // Opt this extension into struct text import/export, not archive serialization.
    return dimension>=1&&dimension<=2048&&size==4;
}
template<class T> T symbol(HMODULE core,const char* name){return reinterpret_cast<T>(GetProcAddress(core,name));}
}
bool registerPtrProperty(HMODULE core){
    if(registered)return true;
    auto initialized=symbol<int*>(core,"?GObjInitialized@UObject@@0HA");
    using Constructor=void (__thiscall*)(void*,int,unsigned,unsigned,void*,void*,Guid,
        const wchar_t*,const wchar_t*,const wchar_t*,unsigned,void (__cdecl*)(void*),void*);
    auto ctor=symbol<Constructor>(core,"??0UClass@@QAE@W4EConstructorNative@@KKPAV0@1VFGuid@@PBG33KP6AXPAX@ZP8UObject@@AEXXZ@Z");
    auto parent=symbol<void*>(core,"?PrivateStaticClass@UProperty@@0VUClass@@A");
    auto baseTable=symbol<void**>(core,"??_7UProperty@@6B@");
    auto intTable=symbol<void**>(core,"??_7UIntProperty@@6B@");
    auto staticCtor=symbol<void*>(core,"?StaticConstructor@UObject@@QAEXXZ");
    baseCtor=symbol<InstanceCtor>(core,"??0UProperty@@QAE@XZ");
    output=symbol<Log>(core,"?Log@FOutputDevice@@QAEXPBG@Z");
    getClass=symbol<Class>(core,"?GetClass@UObject@@QBEPAVUClass@@XZ");
    warning=symbol<void**>(core,"?GWarn@@3PAVFFeedbackContext@@A");
    if(!initialized||*initialized||!ctor||!parent||!baseTable||!intTable||!staticCtor||!baseCtor||!output||!getClass||!warning)return false;
    std::memcpy(table,baseTable,sizeof(table));
    // These operations have the same verified four-byte contract as the client.
    for(unsigned slot:{32u,33u,41u,42u})table[slot]=intTable[slot];
    table[35]=reinterpret_cast<void*>(exportCpp);
    table[36]=reinterpret_cast<void*>(serialize);
    table[37]=reinterpret_cast<void*>(netSerialize);
    table[38]=reinterpret_cast<void*>(exportText);
    table[39]=reinterpret_cast<void*>(importText);
    table[44]=reinterpret_cast<void*>(port);
    void* within=nullptr;std::memcpy(&within,static_cast<unsigned char*>(parent)+0x4b0,4);
    ctor(storage,0,0x6c,0x8000,parent,within,Guid{},L"PtrProperty",L"Core",L"",0x04084004,construct,staticCtor);
    registered=true;return true;
}
void* ptrPropertyClass(){return registered?storage:nullptr;}
bool isPtrProperty(void* object){return registered&&object&&getClass(object)==storage;}
}
