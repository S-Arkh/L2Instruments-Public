// Exact-SDK registration and metadata persistence experiment in a copied UCC.
// Default: integer registration control. save/load: genuine Core.PtrProperty.
// No compiler syntax or client default-value compatibility is claimed here.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstddef>
#include <cstring>
#include <cwchar>
#include <initializer_list>
#include "MinHook.h"
#include "ptr_property.h"

static_assert(sizeof(void*)==4,"Build Win32");
namespace {
struct Guid { unsigned words[4]; };
alignas(16) unsigned char storage[0x600];
HMODULE core;
using Init=void (__cdecl*)(const wchar_t*,const wchar_t*,void*,void*,void*,void*,void*,void*,int);
Init originalInit;
using InstanceCtor=void (__thiscall*)(void*);
InstanceCtor instanceCtor;
unsigned constructed;
void* registeredClass=storage;
wchar_t mode[16];
bool pointerMode;
using PropertySerialize=void (__thiscall*)(void*,void*);
using PropertyLink=void (__thiscall*)(void*,void*,void*);
PropertySerialize originalPropertySerialize;
PropertyLink originalPropertyLink;
unsigned fieldWord(void* object,unsigned offset){unsigned v;std::memcpy(&v,static_cast<unsigned char*>(object)+offset,4);return v;}
template<class T> T symbol(const char* name) {
    auto p=GetProcAddress(core,name);
    if(!p){std::fprintf(stderr,"Missing export: %s\n",name);ExitProcess(20);}
    return reinterpret_cast<T>(p);
}
void __cdecl construct(void* object) {
    instanceCtor(object);
    ++constructed;
}
unsigned name(const wchar_t* text) {
    unsigned result=0;
    symbol<void (__thiscall*)(void*,const wchar_t*,int)>("??0FName@@QAE@PBGW4EFindName@@@Z")(&result,text,1);
    return result;
}
void __fastcall traceSerialize(void* property,void*,void* archive){
    unsigned before=fieldWord(property,0x3c);
    originalPropertySerialize(property,archive);
    unsigned after=fieldWord(property,0x3c);
    if(before!=after)std::printf("serialize property=%ls archive14=%u before=%08x after=%08x\n",
        symbol<const wchar_t* (__thiscall*)(void*)>("?GetName@UObject@@QBEPBGXZ")(property),fieldWord(archive,0x14),before,after);
}
void __fastcall traceLink(void* property,void*,void* archive,void* previous){
    unsigned before=fieldWord(property,0x3c);
    originalPropertyLink(property,archive,previous);
    unsigned after=fieldWord(property,0x3c);
    if(before!=after)std::printf("link property=%ls before=%08x after=%08x\n",
        symbol<const wchar_t* (__thiscall*)(void*)>("?GetName@UObject@@QBEPBGXZ")(property),before,after);
}
bool valueContracts(void* property) {
    auto table=*static_cast<void***>(property);
    using Copy=void (__thiscall*)(void*,void*,void*,void*);
    unsigned source=0x12345678,dest[2]={0,0xdeadbeef};
    reinterpret_cast<Copy>(table[41])(property,dest,&source,nullptr);
    bool ok=dest[0]==source&&dest[1]==0xdeadbeef;
    using Identical=int (__thiscall*)(void*,const void*,const void*);
    auto identical=reinterpret_cast<Identical>(table[33]);unsigned zero=0;
    ok=ok&&identical(property,dest,&source)&&!identical(property,&source,nullptr)&&identical(property,&zero,nullptr);
    // The observed client serializer performs no archive access or value write.
    using Serialize=void (__thiscall*)(void*,void*,void*,int);
    reinterpret_cast<Serialize>(table[36])(property,nullptr,dest,4);
    ok=ok&&dest[0]==source&&dest[1]==0xdeadbeef;
    using NetSerialize=int (__thiscall*)(void*,void*,void*,void*);
    ok=ok&&reinterpret_cast<NetSerialize>(table[37])(property,nullptr,nullptr,dest)==1;
    using Destroy=void (__thiscall*)(void*,void*);
    reinterpret_cast<Destroy>(table[43])(property,dest);
    ok=ok&&dest[0]==source&&dest[1]==0xdeadbeef;
    using Id=unsigned char (__thiscall*)(void*);
    ok=ok&&reinterpret_cast<Id>(table[45])(property)==static_cast<unsigned char>(name(L"PtrProperty"));
    unsigned dimension=3;std::memcpy(static_cast<unsigned char*>(property)+0x34,&dimension,4);
    unsigned array[3]={1,0,0xffffffff},copied[4]={0,0,0,0xdeadbeef};
    reinterpret_cast<Copy>(table[42])(property,copied,array,nullptr);
    ok=ok&&!std::memcmp(array,copied,sizeof(array))&&copied[3]==0xdeadbeef;
    dimension=1;std::memcpy(static_cast<unsigned char*>(property)+0x34,&dimension,4);
    unsigned element=0,offset=0;
    std::memcpy(&element,static_cast<unsigned char*>(property)+0x38,4);
    std::memcpy(&offset,static_cast<unsigned char*>(property)+0x48,4);
    ok=ok&&element==4&&offset%4==0;
    using Import=const wchar_t* (__thiscall*)(void*,const wchar_t*,void*,int);
    auto import=reinterpret_cast<Import>(table[39]);
    for(const wchar_t* text:{L"0",L" 0 ",L"0,Next=1",L"0)"}){
        unsigned guarded[3]={0xdeadbeef,0xffffffff,0xcafebabe};
        auto end=import(property,text,guarded+1,0);
        ok=ok&&end&&end>text&&(*end==0||*end==L','||*end==L')')&&guarded[0]==0xdeadbeef&&guarded[1]==0&&guarded[2]==0xcafebabe;
    }
    for(const wchar_t* text:{L"1",L"-1",L"0x0",L"0.0",L"0abc",L"0 + 1",L"None",L""}){
        unsigned guarded[3]={0xdeadbeef,0x12345678,0xcafebabe};
        auto end=import(property,text,guarded+1,0);
        ok=ok&&!end&&guarded[0]==0xdeadbeef&&guarded[1]==0x12345678&&guarded[2]==0xcafebabe;
    }
    using Port=int (__thiscall*)(void*);
    using Export=void (__thiscall*)(void*,wchar_t*,void*,void*,int);
    wchar_t text[3]={L'X',L'X',L'Z'};
    reinterpret_cast<Export>(table[38])(property,text,&zero,nullptr,0);
    ok=ok&&reinterpret_cast<Port>(table[44])(property)&&text[0]==L'0'&&text[1]==0&&text[2]==L'Z';
    reinterpret_cast<Export>(table[38])(property,text,&source,nullptr,0);
    ok=ok&&text[0]==0&&text[2]==L'Z';
    std::printf("value-contracts=%d element-size=%u offset=%u dynamic-id=%u\n",ok,element,offset,reinterpret_cast<Id>(table[45])(property));
    return ok;
}
// Exact-SDK VM operand probe. Operands contain loaded UProperty addresses, as
// package relocation would supply them; this does not claim compiler support.
bool pointerVmContracts(void* object,void* source,void* target,void* array){
    struct Frame {
        void* vtable;void* node;void* object;unsigned char* code;void* locals;
        unsigned char spare[128];
    };
    static_assert(offsetof(Frame,code)==12);
    using Handler=void (__thiscall*)(void*,Frame*,void*);
    auto read=symbol<Handler>("?execInstanceVariable@UObject@@QAEXAAUFFrame@@QAX@Z");
    auto let=symbol<Handler>("?execLet@UObject@@QAEXAAUFFrame@@QAX@Z");
    auto element=symbol<Handler>("?execArrayElement@UObject@@QAEXAAUFFrame@@QAX@Z");
    auto location=[object](void* property){
        unsigned offset=0;std::memcpy(&offset,static_cast<unsigned char*>(property)+0x48,4);
        return static_cast<unsigned char*>(object)+offset;
    };
    unsigned char operand[4];std::memcpy(operand,&source,4);
    unsigned result[2]={0,0xdeadbeef},marker=0;
    std::memcpy(&marker,location(source),4);
    Frame frame{};frame.object=object;frame.code=operand;
    read(object,&frame,result);
    bool valid=frame.code==operand+4&&result[0]==marker&&result[1]==0xdeadbeef;
    // Instance-variable destination and source: property identities remain PtrProperty.
    unsigned char copy[10]={0x01};std::memcpy(copy+1,&target,4);
    copy[5]=0x01;std::memcpy(copy+6,&source,4);
    frame.code=copy;let(object,&frame,nullptr);
    unsigned value=0;std::memcpy(&value,location(target),4);
    valid=valid&&frame.code==copy+10&&value==marker;
    // Read element one through EX_ArrayElement, EX_IntOne, EX_InstanceVariable.
    unsigned char indexed[6]={0x26,0x01};std::memcpy(indexed+2,&array,4);
    frame.code=indexed;result[0]=0;element(object,&frame,result);
    std::memcpy(&value,location(array)+4,4);
    valid=valid&&frame.code==indexed+6&&result[0]==value&&result[1]==0xdeadbeef;
    // Assign null only to that array element; adjacent elements are guards.
    unsigned left=0,right=0;std::memcpy(&left,location(array),4);std::memcpy(&right,location(array)+8,4);
    unsigned char clear[8]={0x1a,0x26,0x01};std::memcpy(clear+3,&array,4);clear[7]=0x25;
    frame.code=clear;let(object,&frame,nullptr);
    unsigned cells[3];std::memcpy(cells,location(array),sizeof(cells));
    valid=valid&&frame.code==clear+8&&cells[0]==left&&cells[1]==0&&cells[2]==right;
    std::printf("pointer-vm-contracts=%d\n",valid);
    return valid;
}
void __cdecl initialized(const wchar_t* package,const wchar_t* command,void* malloc,
    void* log,void* error,void* warn,void* files,void* config,int requireConfig) {
    originalInit(package,command,malloc,log,error,warn,files,config,requireConfig);
    if(!std::wcscmp(mode,L"missing")){
        *symbol<int*>("?GIsEditor@@3HA")=1;
        std::puts("negative-load-without-registration");std::fflush(stdout);
        symbol<void* (__cdecl*)(void*,const wchar_t*,unsigned)>("?LoadPackage@UObject@@SAPAV1@PAV1@PBGK@Z")(nullptr,L"PtrProbe.u",0);
        auto loadObject=symbol<void* (__cdecl*)(void*,void*,const wchar_t*,const wchar_t*,unsigned,void*)>("?StaticLoadObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBG2KPAVUPackageMap@@@Z");
        void* object=loadObject(symbol<void*>("?PrivateStaticClass@UProperty@@0VUClass@@A"),nullptr,L"PtrProbe.Holder.Value",nullptr,0,nullptr);
        if(!object){std::puts("missing-PtrProperty-rejected");std::fflush(stdout);ExitProcess(28);}
        ExitProcess(27); // Successful loading is an unexpected negative result.
    }
    auto ready=symbol<int*>("?GObjInitialized@UObject@@0HA");
    auto pending=symbol<void**>("?GAutoRegister@UObject@@0PAV1@A");
    using Find=void* (__cdecl*)(void*,void*,const wchar_t*,int);
    auto find=symbol<Find>("?StaticFindObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBGH@Z");
    void* found=find(nullptr,nullptr,pointerMode?L"Core.PtrProperty":L"Core.PtrRegistrationControl",0);
    std::printf("initialized=%d registered=%d queue-empty=%d callbacks=%u\n",
        *ready,found==registeredClass,*pending==nullptr,constructed);std::fflush(stdout);
    if(!*ready||found!=registeredClass)ExitProcess(21);
    using New=void* (__cdecl*)(void*,void*,unsigned,unsigned,void*,void*,void*);
    auto create=symbol<New>("?StaticConstructObject@UObject@@SAPAV1@PAVUClass@@PAV1@VFName@@K1PAVFOutputDevice@@1@Z");
    if(pointerMode){
        // UCC selects commandlet context after appInit; this hook exits before
        // that step, so explicitly select the editor context for field exports.
        *symbol<int*>("?GIsEditor@@3HA")=1;
        using GetClass=void* (__thiscall*)(void*);
        auto getClass=symbol<GetClass>("?GetClass@UObject@@QBEPAVUClass@@XZ");
        if(!std::wcscmp(mode,L"metadata")){
            auto loadObject=symbol<void* (__cdecl*)(void*,void*,const wchar_t*,const wchar_t*,unsigned,void*)>("?StaticLoadObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBG2KPAVUPackageMap@@@Z");
            auto classType=symbol<void* (__cdecl*)()>("?StaticClass@UClass@@SAPAV1@XZ")();
            auto flags=symbol<unsigned (__thiscall*)(void*)>("?GetFlags@UObject@@QBEKXZ");
            loadObject(classType,nullptr,L"Core.Object",L"Core.u",0,nullptr);
            wchar_t loadContext[16];
            if(GetEnvironmentVariableW(L"UCC_METADATA_CONTEXT",loadContext,16)&&std::wcscmp(loadContext,L"editor")){
                *symbol<int*>("?GIsEditor@@3HA")=0;
                *symbol<int*>("?GIsClient@@3HA")=!std::wcscmp(loadContext,L"client");
                *symbol<int*>("?GIsServer@@3HA")=!std::wcscmp(loadContext,L"server");
            }
            wchar_t packagePath[512],paths[4096],savePath[512];
            auto packageLength=GetEnvironmentVariableW(L"UCC_METADATA_PACKAGE",packagePath,512);
            auto pathsLength=GetEnvironmentVariableW(L"UCC_METADATA_OBJECTS",paths,4096);
            if(!packageLength||packageLength>=512||!pathsLength||pathsLength>=4096)ExitProcess(40);
            auto pkg=symbol<void* (__cdecl*)(void*,const wchar_t*,unsigned)>("?LoadPackage@UObject@@SAPAV1@PAV1@PBGK@Z")(nullptr,packagePath,0);
            struct Entry { const wchar_t* path;void* object; } objects[128]{};
            unsigned count=0;
            wchar_t* context=nullptr;
            for(auto path=wcstok_s(paths,L";",&context);path;path=wcstok_s(nullptr,L";",&context)){
                if(std::wcslen(path)>=512)ExitProcess(44);
                wchar_t segments[512];wcscpy_s(segments,path);
                wchar_t* rest=nullptr;
                auto segment=wcstok_s(segments,L".",&rest);
                segment=wcstok_s(nullptr,L".",&rest);
                if(!segment)ExitProcess(44);
                wchar_t classPath[512];swprintf_s(classPath,L"%ls.%ls",segments,segment);
                auto object=loadObject(classType,nullptr,classPath,nullptr,0,nullptr);
                while(object&&(segment=wcstok_s(nullptr,L".",&rest)))object=find(nullptr,object,segment,0);
                if(!object)ExitProcess(41);
                if(getClass(object)!=classType&&!symbol<int (__thiscall*)(void*,void*)>("?IsA@UObject@@QBEHPAVUClass@@@Z")
                    (object,symbol<void*>("?PrivateStaticClass@UProperty@@0VUClass@@A")))ExitProcess(48);
                if(count==128)ExitProcess(43);
                objects[count++]={path,object};
            }
            auto word=[](void* object,unsigned offset){unsigned v;std::memcpy(&v,static_cast<unsigned char*>(object)+offset,4);return v;};
            auto snapshot=[&](const char* stage){
                for(unsigned i=0;i<count;++i){
                    const auto& item=objects[i];
                    bool cls=getClass(item.object)==classType;
                    std::printf("metadata stage=%s object=%ls object_flags=%08x kind=%s flags=%08x\n",stage,item.path,flags(item.object),cls?"class":"property",word(item.object,cls?0x498:0x3c));
                }
                std::fflush(stdout);
            };
            snapshot("loaded");
            wchar_t lifecycle[8];
            if(GetEnvironmentVariableW(L"UCC_METADATA_LIFECYCLE",lifecycle,8)){
                auto ownerClass=loadObject(classType,nullptr,L"Generation.MetadataOwner",nullptr,0,nullptr);
                auto valueClass=loadObject(classType,nullptr,L"Generation.InlineValue",nullptr,0,nullptr);
                auto plainClass=loadObject(classType,nullptr,L"Generation.PlainValue",nullptr,0,nullptr);
                auto transient=symbol<void* (__cdecl*)()>("?GetTransientPackage@UObject@@SAPAVUPackage@@XZ")();
                auto sourceOwner=create(ownerClass,transient,0,0,nullptr,error,nullptr);
                auto destOwner=create(ownerClass,transient,0,0,nullptr,error,nullptr);
                auto source=create(valueClass,sourceOwner,name(L"MetadataLifetimeValue"),0,nullptr,error,nullptr);
                auto plain=create(plainClass,sourceOwner,0,0,nullptr,error,nullptr);
                auto property=find(nullptr,ownerClass,L"Inline",0);
                auto control=find(nullptr,ownerClass,L"Plain",0);
                auto payload=find(nullptr,valueClass,L"Payload",0);
                if(!sourceOwner||!destOwner||!source||!plain||!property||!control||!payload)ExitProcess(45);
                unsigned value=73;std::memcpy(static_cast<unsigned char*>(source)+word(payload,0x48),&value,4);
                auto copy=symbol<void (__thiscall*)(void*,void*,void*,void*)>("?CopySingleValue@UObjectProperty@@UBEXPAX0PAVUObject@@@Z");
                auto outer=symbol<void* (__thiscall*)(void*)>("?GetOuter@UObject@@QBEPAV1@XZ");
                const unsigned masks[]={0x400000,0x4000008,0x4400008};
                unsigned savedFlags=word(property,0x3c);
                bool valid=true;
                for(unsigned mask:masks){
                    std::memcpy(static_cast<unsigned char*>(property)+0x3c,&mask,4);
                    void* copied=nullptr;copy(property,&copied,&source,nullptr);
                    bool shallow=copied==source;
                    copied=nullptr;copy(property,&copied,&source,destOwner);
                    bool distinct=copied&&copied!=source;
                    unsigned actual=copied?word(copied,word(payload,0x48)):0;
                    std::printf("copy flags=%08x null-owner-shallow=%d owner-distinct=%d destination-outer=%d payload=%u\n",mask,shallow,distinct,copied&&outer(copied)==destOwner,actual);
                    valid=valid&&shallow&&!distinct&&actual==73;
                    std::memcpy(static_cast<unsigned char*>(sourceOwner)+word(property,0x48),&source,4);
                    std::memcpy(static_cast<unsigned char*>(sourceOwner)+word(control,0x48),&plain,4);
                    auto templated=create(ownerClass,transient,0,0,sourceOwner,error,nullptr);
                    auto inlineCopy=templated?reinterpret_cast<void*>(word(templated,word(property,0x48))):nullptr;
                    auto plainCopy=templated?reinterpret_cast<void*>(word(templated,word(control,0x48))):nullptr;
                    std::printf("template flags=%08x inline-distinct=%d inline-outer=%d plain-shallow=%d payload=%u\n",mask,inlineCopy&&inlineCopy!=source,inlineCopy&&outer(inlineCopy)==templated,plainCopy==plain,inlineCopy?word(inlineCopy,word(payload,0x48)):0);
                    valid=valid&&templated&&inlineCopy&&plainCopy==plain&&word(inlineCopy,word(payload,0x48))==73&&
                        ((inlineCopy!=source)==((mask&0x400000)!=0));
                }
                std::memcpy(static_cast<unsigned char*>(property)+0x3c,&savedFlags,4);
                void* copied=nullptr;copy(control,&copied,&plain,destOwner);
                valid=valid&&copied==plain;
                // UObjectProperty destruction is not ownership deletion. Invoke
                // the native virtual entry and verify the referenced payload.
                void* cell=source;
                using Destroy=void (__thiscall*)(void*,void*);
                reinterpret_cast<Destroy>((*static_cast<void***>(property))[43])(property,&cell);
                valid=valid&&word(source,word(payload,0x48))==73;
                std::printf("lifecycle plain-shallow=%d referenced-payload-survives=%d valid=%d\n",copied==plain,word(source,word(payload,0x48))==73,valid);
                if(!valid)ExitProcess(46);
                symbol<void (__thiscall*)(void*)>("?AddToRoot@UObject@@QAEXXZ")(sourceOwner);
                auto collect=symbol<void (__cdecl*)(unsigned)>("?CollectGarbage@UObject@@SAXK@Z");
                collect(0x80000);
                bool retained=find(valueClass,sourceOwner,L"MetadataLifetimeValue",0)==source;
                void* empty=nullptr;std::memcpy(static_cast<unsigned char*>(sourceOwner)+word(property,0x48),&empty,4);
                collect(0x80000);
                bool released=find(valueClass,sourceOwner,L"MetadataLifetimeValue",0)==nullptr;
                std::printf("lifetime rooted-owner-retains=%d cleared-reference-collected=%d\n",retained,released);std::fflush(stdout);
                if(!retained||!released)ExitProcess(47);
            }
            auto saveLength=GetEnvironmentVariableW(L"UCC_METADATA_SAVE",savePath,512);
            if(saveLength>=512)ExitProcess(40);
            if(saveLength){
                int saved=symbol<int (__cdecl*)(void*,void*,unsigned,const wchar_t*,void*,void*)>("?SavePackage@UObject@@SAHPAV1@0KPBGPAVFOutputDevice@@PAVULinkerLoad@@@Z")(pkg,nullptr,4,savePath,error,nullptr);
                snapshot("saved");
                if(!saved)ExitProcess(42);
            }
            std::puts("metadata-complete=1");std::fflush(stdout);ExitProcess(0);
        }
        if(!std::wcscmp(mode,L"semantics")){
            auto loadObject=symbol<void* (__cdecl*)(void*,void*,const wchar_t*,const wchar_t*,unsigned,void*)>("?StaticLoadObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBG2KPAVUPackageMap@@@Z");
            auto classType=symbol<void* (__cdecl*)()>("?StaticClass@UClass@@SAPAV1@XZ")();
            auto objectClass=symbol<void*>("?PrivateStaticClass@UObject@@0VUClass@@A");
            std::printf("root-property-size=%d\n",symbol<int (__thiscall*)(void*)>("?GetPropertiesSize@UStruct@@UAEHXZ")(objectClass));std::fflush(stdout);
            loadObject(classType,nullptr,L"Core.Object",L"Core.u",0,nullptr);
            std::printf("loaded-root-property-size=%d\n",symbol<int (__thiscall*)(void*)>("?GetPropertiesSize@UStruct@@UAEHXZ")(objectClass));std::fflush(stdout);
            auto base=loadObject(classType,nullptr,L"Generation.SemanticsBase",L"Generation.u",0,nullptr);
            if(!base)ExitProcess(34);
            auto cls=loadObject(classType,nullptr,L"Generation.SemanticsProbe",L"Generation.u",0,nullptr);
            auto transient=symbol<void* (__cdecl*)()>("?GetTransientPackage@UObject@@SAPAVUPackage@@XZ")();
            if(!cls)ExitProcess(31);
            auto object=create(cls,transient,0,0,nullptr,error,nullptr);
            if(!object)ExitProcess(32);
            *symbol<int*>("?GIsScriptable@@3HA")=1;
            struct Case { const wchar_t* function;int input,expected; };
            const Case cases[]={{L"Contexts",0,511},{L"Lexical",0,10},{L"Lexical",1,11},
                {L"Flow",-3,7},{L"Flow",0,7},{L"Flow",1,10},{L"Flow",2,20},
                {L"Flow",3,20},{L"Flow",5,18},{L"Flow",9,28}};
            bool valid=true;unsigned count=0;
            for(const auto& item:cases){
                wchar_t path[160];swprintf_s(path,L"Generation.SemanticsProbe.%ls",item.function);
                auto function=find(nullptr,nullptr,path,0);
                if(!function){valid=false;break;}
                struct { unsigned before;int input,result;unsigned after; } args{0x13572468,item.input,-999,0x24681357};
                symbol<void (__thiscall*)(void*,void*,void*,void*)>("?ProcessEvent@UObject@@UAEXPAVUFunction@@PAX1@Z")
                    (object,function,&args.input,&args.result);
                bool passed=args.before==0x13572468&&args.after==0x24681357&&args.input==item.input&&args.result==item.expected;
                std::printf("semantic=%ls input=%d actual=%d expected=%d passed=%d\n",item.function,item.input,args.result,item.expected,passed);
                valid=valid&&passed;++count;
            }
            std::printf("script-semantics=%d cases=%u\n",valid,count);std::fflush(stdout);
            ExitProcess(valid&&count==10?0:33);
        }
        if(!std::wcscmp(mode,L"fixture")){
            auto loadObject=symbol<void* (__cdecl*)(void*,void*,const wchar_t*,const wchar_t*,unsigned,void*)>("?StaticLoadObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBG2KPAVUPackageMap@@@Z");
            auto classType=symbol<void* (__cdecl*)()>("?StaticClass@UClass@@SAPAV1@XZ")();
            auto cls=loadObject(classType,nullptr,L"Generation.PointerChild",L"Generation.u",0,nullptr);
            if(!cls)ExitProcess(29);
            auto defaults=symbol<void* (__thiscall*)(void*)>("?GetDefaultObject@UClass@@QAEPAVUObject@@XZ")(cls);
            auto transient=symbol<void* (__cdecl*)()>("?GetTransientPackage@UObject@@SAPAVUPackage@@XZ")();
            void* first=create(cls,transient,0,0,nullptr,error,nullptr);
            void* second=create(cls,transient,0,0,nullptr,error,nullptr);
            unsigned classSize=0;std::memcpy(&classSize,static_cast<unsigned char*>(cls)+0x40,4);
            auto offset=[](void* field){unsigned result=0;if(field)std::memcpy(&result,static_cast<unsigned char*>(field)+0x48,4);return result;};
            auto data=find(nullptr,nullptr,L"Generation.PointerProbe.Data",0);
            struct Field { const wchar_t* path; unsigned base; unsigned dimension=1; };
            Field fields[]={{L"Generation.PointerProbe.Handle",0},{L"Generation.PointerProbe.OtherHandle",0},
                {L"Generation.PointerProbe.AnimationData",0},{L"Generation.PointerChild.ChildHandle",0},
                {L"Generation.PointerProbe.NativeData.InnerHandle",offset(data)},
                {L"Generation.PointerProbe.NativeData.LinkedAnimationData",offset(data)},
                {L"Generation.PointerProbe.Handles",0,3},
                {L"Generation.PointerProbe.TrailingHandle",0},
                {L"Generation.PointerProbe.Animations",0,2},
                {L"Generation.PointerProbe.NativeData.InnerHandles",offset(data),2}};
            bool valid=defaults&&first&&second&&data;unsigned count=0;
            auto countField=find(nullptr,nullptr,L"Generation.PointerProbe.NativeData.Count",0);
            unsigned countAt=offset(data)+offset(countField);
            if(!countField||countAt+4>classSize)valid=false;
            if(valid)for(void* object:{defaults,first,second}){
                unsigned value=0;std::memcpy(&value,static_cast<unsigned char*>(object)+countAt,4);
                valid=valid&&value==7;
            }
            if(valid){
                auto dataTable=*static_cast<void***>(data);
                using Export=void (__thiscall*)(void*,wchar_t*,void*,void*,int);
                using Import=const wchar_t* (__thiscall*)(void*,const wchar_t*,void*,int);
                wchar_t text[512]{};unsigned restored[64]{};
                unsigned size=0;std::memcpy(&size,static_cast<unsigned char*>(data)+0x38,4);
                auto source=static_cast<unsigned char*>(defaults)+offset(data);
                reinterpret_cast<Export>(dataTable[38])(data,text,source,nullptr,0);
                std::printf("nested-text=%ls size=%u\n",text,size);
                // Stock export omits zero fields relative to an implicit zero baseline.
                valid=size>0&&size<=sizeof(restored)&&std::wcsstr(text,L"Count=7");
                if(valid){
                    auto end=reinterpret_cast<Import>(dataTable[39])(data,text,restored,0);
                    valid=end&&!*end&&!std::memcmp(source,restored,size);
                }
                if(valid){
                    std::memset(restored,0xff,size);
                    auto end=reinterpret_cast<Import>(dataTable[39])(data,
                        L"(InnerHandle=0 ,Count=7,LinkedAnimationData=0,InnerHandles[0]=0,InnerHandles[1]=0)",restored,0);
                    valid=end&&!*end&&!std::memcmp(source,restored,size);
                }
                std::printf("nested-text-roundtrip=%d\n",valid);
            }
            unsigned locations[14]{}, locationCount=0;
            for(auto& field:fields){
                void* prop=find(registeredClass,nullptr,field.path,1);
                unsigned dim=0,size=0;
                if(prop){std::memcpy(&dim,static_cast<unsigned char*>(prop)+0x34,4);std::memcpy(&size,static_cast<unsigned char*>(prop)+0x38,4);}
                if(dim!=field.dimension||size!=4){valid=false;break;}
                if(locationCount+dim>14){valid=false;break;}
                for(unsigned i=0;i<dim;++i)locations[locationCount++]=field.base+offset(prop)+4*i;
            }
            valid=valid&&locationCount==14;
            for(unsigned at:locations){
                if(!valid||at%4||at+4>classSize){valid=false;break;}
                unsigned a,b,c;std::memcpy(&a,static_cast<unsigned char*>(defaults)+at,4);
                std::memcpy(&b,static_cast<unsigned char*>(first)+at,4);std::memcpy(&c,static_cast<unsigned char*>(second)+at,4);
                valid=valid&&a==0&&b==0&&c==0;
                unsigned marker=0x12340000+count;std::memcpy(static_cast<unsigned char*>(first)+at,&marker,4);
                ++count;
            }
            // Existing instance writes must not modify class defaults or another instance.
            unsigned index=0;
            for(unsigned at:locations){
                if(!valid||at+4>classSize){valid=false;break;}
                unsigned a,b,c;std::memcpy(&a,static_cast<unsigned char*>(defaults)+at,4);std::memcpy(&b,static_cast<unsigned char*>(second)+at,4);
                std::memcpy(&c,static_cast<unsigned char*>(first)+at,4);
                valid=valid&&a==0&&b==0&&c==0x12340000+index++;
            }
            std::printf("compiled-fixture=%d zero-initialized-fields=%u independent-instances=%d\n",valid,count,valid);
            if(valid)valid=pointerVmContracts(first,
                find(registeredClass,nullptr,L"Generation.PointerProbe.Handle",1),
                find(registeredClass,nullptr,L"Generation.PointerProbe.OtherHandle",1),
                find(registeredClass,nullptr,L"Generation.PointerProbe.Handles",1));
            auto predicate=[&](const wchar_t* name,bool expected){
                auto function=find(nullptr,nullptr,name,0);if(!function)return false;
                unsigned result[3]={0x13572468,0,0x24681357};
                auto scriptable=symbol<int*>("?GIsScriptable@@3HA");int previous=*scriptable;*scriptable=1;
                symbol<void (__thiscall*)(void*,void*,void*,void*)>("?ProcessEvent@UObject@@UAEXPAVUFunction@@PAX1@Z")
                    (first,function,result+1,result+1);
                *scriptable=previous;
                return result[0]==0x13572468&&result[2]==0x24681357&&(result[1]!=0)==expected;
            };
            valid=valid&&predicate(L"Generation.PointerProbe.EqualPointers",false)&&predicate(L"Generation.PointerProbe.NullPointers",false);
            if(valid){
                auto function=find(nullptr,nullptr,L"Generation.PointerProbe.CopyPointers",0);
                if(!function)valid=false;
                else{
                    auto scriptable=symbol<int*>("?GIsScriptable@@3HA");int wasScriptable=*scriptable;
                    *scriptable=1; // appInit precedes commandlet setup in this isolated probe.
                    symbol<void (__thiscall*)(void*,void*,void*,void*)>("?ProcessEvent@UObject@@UAEXPAVUFunction@@PAX1@Z")
                        (first,function,nullptr,nullptr);
                    *scriptable=wasScriptable;
                    unsigned expected=0;std::memcpy(&expected,static_cast<unsigned char*>(first)+locations[0],4);
                    // OtherHandle, Handles[1], nested InnerHandle, AnimationData.
                    for(unsigned cell:{1u,7u,4u,2u}){
                        unsigned value=0;std::memcpy(&value,static_cast<unsigned char*>(first)+locations[cell],4);
                        valid=valid&&value==expected;
                    }
                }
                std::printf("compiled-pointer-expressions=%d\n",valid);
            }
            valid=valid&&predicate(L"Generation.PointerProbe.EqualPointers",true)&&predicate(L"Generation.PointerProbe.NullPointers",false);
            if(valid){
                auto function=find(nullptr,nullptr,L"Generation.PointerProbe.ClearPointers",0);
                if(!function)valid=false;
                else{
                    auto scriptable=symbol<int*>("?GIsScriptable@@3HA");int wasScriptable=*scriptable;*scriptable=1;
                    symbol<void (__thiscall*)(void*,void*,void*,void*)>("?ProcessEvent@UObject@@UAEXPAVUFunction@@PAX1@Z")
                        (first,function,nullptr,nullptr);
                    *scriptable=wasScriptable;
                    for(unsigned cell:{1u,7u,4u,2u}){
                        unsigned value=1;std::memcpy(&value,static_cast<unsigned char*>(first)+locations[cell],4);
                        valid=valid&&value==0;
                    }
                    for(unsigned at:locations)for(void* object:{defaults,second}){
                        unsigned value=1;std::memcpy(&value,static_cast<unsigned char*>(object)+at,4);valid=valid&&value==0;
                    }
                    unsigned preserved=0;std::memcpy(&preserved,static_cast<unsigned char*>(first)+countAt,4);
                    valid=valid&&preserved==7;
                }
                std::printf("compiled-pointer-locals-parameters-null=%d\n",valid);
            }
            valid=valid&&predicate(L"Generation.PointerProbe.EqualPointers",false)&&predicate(L"Generation.PointerProbe.NullPointers",true);
            std::printf("compiled-pointer-equality=%d\n",valid);
            std::fflush(stdout);ExitProcess(valid&&count==14?0:30);
        }
        if(!std::wcscmp(mode,L"save")){
            auto packageObject=symbol<void* (__cdecl*)(void*,const wchar_t*)>("?CreatePackage@UObject@@SAPAVUPackage@@PAV1@PBG@Z")(nullptr,L"PtrProbe");
            auto structure=symbol<void*>("?PrivateStaticClass@UStruct@@0VUClass@@A");
            void* owner=create(structure,packageObject,name(L"Holder"),4,nullptr,error,nullptr);
            void* property=create(registeredClass,owner,name(L"Value"),4,nullptr,error,nullptr);
            if(!owner||!property||getClass(property)!=registeredClass)ExitProcess(23);
            unsigned friendly=name(L"Holder");
            std::memcpy(static_cast<unsigned char*>(owner)+0x44,&friendly,4);
            // Exact SDK UProperty metadata: ArrayDim +0x34, flags +0x3c.
            unsigned dimension=1,flags=0x1000;
            std::memcpy(static_cast<unsigned char*>(property)+0x34,&dimension,4);
            std::memcpy(static_cast<unsigned char*>(property)+0x3c,&flags,4);
            symbol<void (__thiscall*)(void*,void*)>("?AddCppProperty@UStruct@@UAEXPAVUProperty@@@Z")(owner,property);
            auto save=symbol<int (__cdecl*)(void*,void*,unsigned,const wchar_t*,void*,void*)>("?SavePackage@UObject@@SAHPAV1@0KPBGPAVFOutputDevice@@PAVULinkerLoad@@@Z");
            int saved=save(packageObject,owner,0,L"PtrProbe.u",error,nullptr);
            std::printf("pointer-instance=1 saved=%d callbacks=%u\n",saved,constructed);std::fflush(stdout);ExitProcess(saved?0:24);
        }
        if(!std::wcscmp(mode,L"load")){
            auto load=symbol<void* (__cdecl*)(void*,const wchar_t*,unsigned)>("?LoadPackage@UObject@@SAPAV1@PAV1@PBGK@Z");
            void* loaded=load(nullptr,L"PtrProbe.u",0);
            auto loadObject=symbol<void* (__cdecl*)(void*,void*,const wchar_t*,const wchar_t*,unsigned,void*)>("?StaticLoadObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBG2KPAVUPackageMap@@@Z");
            void* property=loadObject(registeredClass,nullptr,L"PtrProbe.Holder.Value",nullptr,0,nullptr);
            unsigned dimension=0,flags=0;
            if(property){std::memcpy(&dimension,static_cast<unsigned char*>(property)+0x34,4);std::memcpy(&flags,static_cast<unsigned char*>(property)+0x3c,4);}
            bool valid=loaded&&property&&getClass(property)==registeredClass&&dimension==1&&flags==0x1000;
            if(valid)valid=valueContracts(property);
            std::printf("loaded=%d pointer-identity=%d dimension=%u flags=%x callbacks=%u\n",loaded!=nullptr,valid,dimension,flags,constructed);
            std::fflush(stdout);ExitProcess(valid?0:25);
        }
        ExitProcess(26);
    }
    // UProperty's Within is Field: a package is not a valid property outer.
    void* object=create(storage,storage,0,0,nullptr,error,nullptr);
    using Class=void* (__thiscall*)(void*);
    auto getClass=symbol<Class>("?GetClass@UObject@@QBEPAVUClass@@XZ");
    bool valid=object&&getClass(object)==storage&&constructed>0;
    std::printf("instance=%d class-identity=%d callbacks=%u\n",object!=nullptr,valid,constructed);
    std::fflush(stdout);
    // Stop before the commandlet. This control does not save any packages.
    ExitProcess(valid?0:22);
}
}
extern "C" __declspec(dllexport) DWORD WINAPI Ucc64Initialize(void*) {
    core=GetModuleHandleW(L"Core.dll");if(!core)return 10;
    GetEnvironmentVariableW(L"UCC_PTR_PROBE_MODE",mode,16);
    pointerMode=mode[0]!=0;
    if(std::wcscmp(mode,L"")&&std::wcscmp(mode,L"save")&&std::wcscmp(mode,L"load")&&std::wcscmp(mode,L"missing")&&std::wcscmp(mode,L"fixture")&&std::wcscmp(mode,L"semantics")&&std::wcscmp(mode,L"metadata"))return 13;
    if(!std::wcscmp(mode,L"missing"))pointerMode=false;
    if(*symbol<int*>("?GObjInitialized@UObject@@0HA"))return 11;
    using Constructor=void (__thiscall*)(void*,int,unsigned,unsigned,void*,void*,Guid,
        const wchar_t*,const wchar_t*,const wchar_t*,unsigned,void (__cdecl*)(void*),void*);
    auto ctor=symbol<Constructor>("??0UClass@@QAE@W4EConstructorNative@@KKPAV0@1VFGuid@@PBG33KP6AXPAX@ZP8UObject@@AEXXZ@Z");
    void* parent=symbol<void*>(pointerMode?"?PrivateStaticClass@UProperty@@0VUClass@@A":"?PrivateStaticClass@UIntProperty@@0VUClass@@A");
    void* within=nullptr;std::memcpy(&within,static_cast<unsigned char*>(parent)+0x4b0,4);
    instanceCtor=symbol<InstanceCtor>(pointerMode?"??0UProperty@@QAE@XZ":"??0UIntProperty@@QAE@XZ");
    if(pointerMode){
        if(!ucc64::registerPtrProperty(core))return 14;
        registeredClass=ucc64::ptrPropertyClass();
    }else ctor(storage,0,0x6c,0x8000,parent,within,Guid{},L"PtrRegistrationControl",L"Core",L"",
        0x04084004,construct,symbol<void*>("?StaticConstructor@UObject@@QAEXXZ"));
    auto init=symbol<void*>("?appInit@@YAXPBG0PAVFMalloc@@PAVFOutputDevice@@PAVFOutputDeviceError@@PAVFFeedbackContext@@PAVFFileManager@@P6APAVFConfigCache@@XZH@Z");
    if(MH_Initialize()!=MH_OK||MH_CreateHook(init,reinterpret_cast<void*>(initialized),
        reinterpret_cast<void**>(&originalInit))!=MH_OK||MH_EnableHook(init)!=MH_OK)return 12;
    if(!std::wcscmp(mode,L"metadata")){
        auto serialize=symbol<void*>("?Serialize@UObjectProperty@@UAEXAAVFArchive@@@Z");
        auto link=symbol<void*>("?Link@UObjectProperty@@UAEXAAVFArchive@@PAVUProperty@@@Z");
        if(MH_CreateHook(serialize,reinterpret_cast<void*>(traceSerialize),reinterpret_cast<void**>(&originalPropertySerialize))!=MH_OK||
           MH_CreateHook(link,reinterpret_cast<void*>(traceLink),reinterpret_cast<void**>(&originalPropertyLink))!=MH_OK||
           MH_EnableHook(serialize)!=MH_OK||MH_EnableHook(link)!=MH_OK)return 15;
    }
    return 0;
}
