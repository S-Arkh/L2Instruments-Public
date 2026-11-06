// Experimental ABI bridge for the exact UE2 runtime 2226 compiler binary.
// RVAs are relative to Editor.dll's preferred base 0x10200000.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <intrin.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <climits>
#include <set>
#include "MinHook.h"
#include "ptr_property.h"
#include "int64_semantics.h"

#ifdef _MSC_VER
#define CALLER_ADDRESS() _ReturnAddress()
#define BRIDGE_EXPORT
#else
#define CALLER_ADDRESS() __builtin_return_address(0)
#define BRIDGE_EXPORT __attribute__((dllexport))
#endif

static_assert(sizeof(void*) == 4, "Build Win32, not x64");
static_assert(sizeof(wchar_t) == 2);

namespace {
using namespace ucc64;
struct Property {
    int type, arrayDim;
    unsigned flags;
    void* object;
    void* meta;
};
struct Token {
    Property property;
    int kind, name, start, line;
    wchar_t identifier[64];
    unsigned char data[2048];
};
struct Retry { int text, position, line, code; };
static_assert(sizeof(Property) == 20);
static_assert(sizeof(Token) == 0x8a4);
static_assert(offsetof(Token, data) == 0xa4);

using GetConversion = int (__cdecl*)(const Property*, const Property*);
using ConversionCost = int (__thiscall*)(void*, const Property*, const Property*);
using GetToken = int (__thiscall*)(void*, Token*, const Property*, int);
using TokenCtor = Token* (__thiscall*)(Token*, const Property*);
using EmitConstant = void (__thiscall*)(void*, Token*);
using ConvertConstant = void (__thiscall*)(Token*, const Property*);
using CompileExpr = int (__thiscall*)(void*, Property, const wchar_t*, Token*, int, Token*);
using MatchSymbol = int (__thiscall*)(void*, const wchar_t*);
using GetConstInt = int (__thiscall*)(void*, int*, const wchar_t*, void*);
using SaveRetry = void (__thiscall*)(void*, Retry*);
using MoveCode = void (__thiscall*)(void*, const Retry*, const Retry*);
using GetFullName = const wchar_t* (__thiscall*)(void*, wchar_t*);
using StaticClass = void* (__cdecl*)();
using FindObject = void* (__cdecl*)(void*, void*, const wchar_t*, int);
using ThrowError = void (__cdecl*)(const wchar_t*, ...);
using GetDll = void* (__cdecl*)(const wchar_t*);
using ImportText = const wchar_t* (__thiscall*)(void*, const wchar_t*, unsigned char*, int);
using FeedbackSerialize = void (__thiscall*)(void*, const wchar_t*, int);
using FindField = void* (__thiscall*)(void*, void*, const wchar_t*, void*, const wchar_t*);
using NameConstructor = void* (__thiscall*)(int*, const wchar_t*, int);
using ConstructObject = void* (__cdecl*)(void*, void*, int, unsigned, void*, void*, void*);
using ArrayAdd = int (__thiscall*)(void*,int,int);
using NameText = const wchar_t* (__thiscall*)(const int*);

GetConversion originalConversion;
ConversionCost originalConversionCost;
GetToken originalToken;
TokenCtor originalCtor;
EmitConstant originalEmit;
ConvertConstant originalConstant;
GetDll originalGetDll;
ImportText originalImport;
FeedbackSerialize originalFeedback;
FindField originalFindField;
using VarType=int (__thiscall*)(void*,void*,Property*,unsigned*,unsigned,const wchar_t*);
using VarName=void* (__thiscall*)(void*,void*,Property*,unsigned,int,int,const wchar_t*,void*,int,void*);
using FromProperty=Property* (__thiscall*)(Property*,void*);
VarType originalVarType;
VarName originalVarName;
FromProperty originalFromProperty;
constexpr int PointerType=0x505452; // Bridge-only descriptor; never serialized.
NameConstructor constructName;
ConstructObject constructObject;
StaticClass intPropertyClass;
StaticClass arrayPropertyClass, structPropertyClass, functionClass;
using ObjectClass = void* (__thiscall*)(void*);
ObjectClass objectClass;
CompileExpr compileExpr;
MatchSymbol matchSymbol;
GetConstInt getConstInt;
SaveRetry saveRetry;
MoveCode moveCode;
GetFullName fullName;
StaticClass structClass;
FindObject findObject;
FindObject originalFindObject;
thread_local void* activeCompiler=nullptr;
bool scopedEnumCasts=false;
ThrowError throwError;
void** warningDevice;
std::uintptr_t editorBase;
void* int64Struct;
thread_local void* pendingStruct;
bool installed;
void* arraySortFallback;
void* arraySortContinue;
unsigned char sortSerializeTable[0x48];
bool clientArraySort=false;
bool clientEnumProfile=false;
bool clientEnumApplied=false;
StaticClass enumClass;
ArrayAdd arrayAdd;
NameText nameText;

constexpr unsigned Emitted = 0x49363445;
constexpr unsigned Literal = 0x4936344c;

void log(const char* message) {
    std::fprintf(stderr, "[ucc64] %s\n", message);
    std::fflush(stderr);
}

[[noreturn]] void fatal(const wchar_t* message) {
    throwError(L"INT64 extension: %s", message);
    TerminateProcess(GetCurrentProcess(), 86);
    std::abort();
}

void applyClientEnumProfile(){
    if(!clientEnumProfile||clientEnumApplied)return;
    auto object=static_cast<unsigned char*>(findObject(enumClass(),nullptr,L"Engine.Actor.EL2ObjectType",0));
    if(!object)return; // Engine has not been loaded yet.
    // Exact SDK UEnum::Serialize accesses its FName array at +0x34.
    auto array=object+0x34;auto names=*reinterpret_cast<int**>(array);
    int count=*reinterpret_cast<int*>(array+4);
    const wchar_t* oldNames[]={L"EL2_NORMAL",L"EL2_DOOR",L"EL2_CHAIR",L"EL2_AIRSHIPKEY"};
    const wchar_t* newNames[]={L"EL2_NORMAL",L"EL2_DOOR",L"EL2_CHAIR",L"EL2_PUB_CHAIR",
                             L"EL2_AIRSHIPKEY",L"EL2_STATUE",L"EL2_CHAIR_SOCIAL_ACTION"};
    bool already=count==7;
    if(already)for(int i=0;i<7;++i)if(_wcsicmp(nameText(names+i),newNames[i]))already=false;
    if(!already){
        if(count!=4)fatal(L"Client enum profile does not match the SDK enum layout");
        for(int i=0;i<4;++i)if(_wcsicmp(nameText(names+i),oldNames[i]))
            fatal(L"Client enum profile does not match the SDK enum names");
        if(arrayAdd(array,3,sizeof(int))!=4)fatal(L"Could not extend compiler enum metadata");
        names=*reinterpret_cast<int**>(array);
        for(int i=0;i<7;++i)constructName(names+i,newNames[i],1);
    }
    clientEnumApplied=true;
    log("Client enum profile applied in memory: Engine.Actor.EL2ObjectType (7 values)");
}

void* __cdecl scopedEnumFindHook(void* type,void* outer,const wchar_t* name,int exact){
    const auto caller=reinterpret_cast<std::uintptr_t>(CALLER_ADDRESS())-editorBase;
    // CompileConversion looks up enum casts in ANY_PACKAGE, ignoring the class
    // that declared the function. Prefer its lexical fields at this site only.
    if(scopedEnumCasts&&caller==0x73896&&activeCompiler&&type==enumClass()){
        void* scope=*reinterpret_cast<void**>(static_cast<unsigned char*>(activeCompiler)+0x14);
        if(void* local=originalFindField(activeCompiler,scope,name,type,nullptr))return local;
    }
    return originalFindObject(type,outer,name,exact);
}

int __fastcall varTypeHook(void* compiler,void*,void* scope,Property* prop,unsigned* objectFlags,
    unsigned disallow,const wchar_t* context){
    // The SDK itself restores these two cursor fields when type lookahead fails.
    int cursor[2];std::memcpy(cursor,static_cast<unsigned char*>(compiler)+0x6c,sizeof(cursor));
    Token first{},second{};
    bool firstRead=originalToken(compiler,&first,nullptr,0)&&first.kind==1;
    unsigned propertyFlags=firstRead&&!_wcsicmp(first.identifier,L"native")?0x1000:
        firstRead&&!_wcsicmp(first.identifier,L"transient")?0x2000:
        firstRead&&!_wcsicmp(first.identifier,L"out")?0x100:0;
    bool plainPointer=firstRead&&!_wcsicmp(first.identifier,L"pointer");
    bool pointer=plainPointer||(propertyFlags&&originalToken(compiler,&second,nullptr,0)&&second.kind==1&&!_wcsicmp(second.identifier,L"pointer"));
    if(!pointer){
        std::memcpy(static_cast<unsigned char*>(compiler)+0x6c,cursor,sizeof(cursor));
        return originalVarType(compiler,scope,prop,objectFlags,disallow,context);
    }
    const wchar_t* owner=fullName(scope,nullptr);
    bool function=owner&&std::wcsncmp(owner,L"Function ",9)==0;
    bool returnType=owner&&std::wcsncmp(owner,L"Class ",6)==0&&!context&&disallow==~0u;
    if(propertyFlags==0x100)plainPointer=true;
    if(!owner||(!function&&plainPointer&&!returnType)||(function&&!plainPointer)||
       (!function&&(std::wcsncmp(owner,L"Class ",6)!=0)&&(std::wcsncmp(owner,L"Struct ",7)!=0))||(disallow&propertyFlags))
        fatal(L"Pointer declarations require native/transient fields or plain function pointer types");
    *prop=Property{PointerType,1,propertyFlags,nullptr,nullptr};*objectFlags=4;
    return 1;
}

void* __fastcall varNameHook(void* compiler,void*,void* scope,Property* prop,unsigned flags,
    int a,int b,const wchar_t* suppliedName,void* array,int category,void* previous){
    if(prop->type!=PointerType)return originalVarName(compiler,scope,prop,flags,a,b,suppliedName,array,category,previous);
    bool function=std::wcsncmp(fullName(scope,nullptr),L"Function ",9)==0;
    if(prop->arrayDim!=1||(!function&&(suppliedName||(prop->flags!=0x1000&&prop->flags!=0x2000)))||
       (function&&(prop->flags&~0x580u)))
        fatal(L"Only native/transient pointer field declarations are supported");
    Token token{};
    if(suppliedName){
        auto length=std::wcslen(suppliedName);
        if(length>=64)fatal(L"Pointer field name is too long");
        std::memcpy(token.identifier,suppliedName,(length+1)*sizeof(wchar_t));token.kind=1;
    }
    else if(!originalToken(compiler,&token,nullptr,0)||token.kind!=1)
        fatal(L"Expected pointer field name");
    if(originalFindField(compiler,scope,token.identifier,nullptr,nullptr))
        fatal(L"Duplicate or inherited pointer field name");
    int dimension=1;
    if(matchSymbol(compiler,L"[")){
        if(function)fatal(L"Pointer function arrays are unsupported");
        // Same integer/lexical-constant reader and bounds as SDK GetVarNameAndDim.
        if(!getConstInt(compiler,&dimension,nullptr,scope)||dimension<2||dimension>2048)
            fatal(L"Pointer array dimension must be an integer constant from 2 to 2048");
        if(!matchSymbol(compiler,L"]"))fatal(L"Missing ']' after pointer array dimension");
    }
    int fname=0;constructName(&fname,token.identifier,1);
    auto field=static_cast<unsigned char*>(constructObject(ptrPropertyClass(),scope,fname,flags,
        nullptr,*warningDevice,nullptr));
    if(!field)fatal(L"Could not create Core.PtrProperty");
    *reinterpret_cast<int*>(field+0x34)=dimension;
    *reinterpret_cast<unsigned*>(field+0x3c)=prop->flags;
    *reinterpret_cast<int*>(field+0x40)=category;
    // Ordinary declaration path discards incoming array/previous temporaries
    // and appends after the current scope's own children (SDK 0x7e848).
    auto link=static_cast<unsigned char*>(scope)+0x3c;
    while(*reinterpret_cast<void**>(link))link=*reinterpret_cast<unsigned char**>(link)+0x2c;
    std::memcpy(field+0x2c,link,4);std::memcpy(link,&field,4);
    return field;
}

Property* __fastcall fromPropertyHook(Property* self,void*,void* field){
    if(isPtrProperty(field)){
        *self=Property{PointerType,1,0,nullptr,nullptr};
        std::memcpy(&self->arrayDim,static_cast<unsigned char*>(field)+0x34,4);
        std::memcpy(&self->flags,static_cast<unsigned char*>(field)+0x3c,4);
        return self;
    }
    auto result=originalFromProperty(self,field);
    // SDK FPropertyBase(UProperty*) unwraps UArrayProperty to Inner before
    // copying flags (0x7230f, 0x725c0), losing the outer CPF_Optional bit.
    // Restore that bit only for its dynamic-array descriptor (ArrayDim == 0).
    if(result->arrayDim==0){
        unsigned flags=0;std::memcpy(&flags,static_cast<unsigned char*>(field)+0x3c,4);
        // Sort also needs the outer const qualifier; it must not mutate a const
        // array merely because the SDK unwrapped its unqualified Inner.
        result->flags|=flags&(0x10|(clientArraySort?2u:0u));
    }
    return result;
}

bool isInt64Object(void* object) {
    if (!object) return false;
    // UObject::GetFullName includes the object's class before its full path.
    const wchar_t* text = fullName(object, nullptr);
    if (!text) return false;
    const wchar_t* path = std::wcschr(text, L' ');
    return path && _wcsicmp(path + 1, L"Core.Object.INT64") == 0;
}

bool is64(const Property& p) {
    return p.type == Struct && isInt64Object(p.object);
}

void* getInt64Struct() {
    if (!int64Struct)
        int64Struct = findObject(structClass(), nullptr, L"Core.Object.INT64", 0);
    if (!int64Struct) fatal(L"Core.Object.INT64 was not found. Use the matching Object.uc declarations.");
    return int64Struct;
}

template<class T> T address(unsigned rva) {
    return reinterpret_cast<T>(editorBase + rva);
}

void emit(void* compiler, const void* bytes, int size) {
    auto archive = static_cast<unsigned char*>(compiler) + 0x1c;
    auto table = *reinterpret_cast<void***>(archive);
    using Serialize = void (__thiscall*)(void*, const void*, int);
    reinterpret_cast<Serialize>(table[1])(archive, bytes, size);
}

// Called only at CompileExpr's unsupported dynamic-array member branch. The
// receiver is already emitted; use the same retry/code rotation as Insert/Remove.
int __cdecl compileArraySort(void* compiler, unsigned char* frame) {
    int cursor[2];std::memcpy(cursor,static_cast<unsigned char*>(compiler)+0x6c,sizeof(cursor));
    Token token{};
    if(!originalToken(compiler,&token,nullptr,1)||token.kind!=1||_wcsicmp(token.identifier,L"Sort")){
        std::memcpy(static_cast<unsigned char*>(compiler)+0x6c,cursor,sizeof(cursor));
        return 0;
    }
    Property element=*reinterpret_cast<Property*>(frame-0x9d4);
    if(element.arrayDim!=0||(element.flags&2))fatal(L"Sort requires a writable dynamic array");
    // The current script node is also used by the SDK's retry/code writer.
    // The proven Sort encoding references an instance delegate property.
    auto script=*reinterpret_cast<unsigned char**>(static_cast<unsigned char*>(compiler)+0x9c);
    if(script&&!std::wcsncmp(fullName(script,nullptr),L"Function ",9)&&
       (*reinterpret_cast<unsigned*>(script+0x80)&0x2000))
        fatal(L"Sort instance comparator is unavailable in static functions");
    element.arrayDim=1;
    if(!matchSymbol(compiler,L"("))fatal(L"Expected '(' after array.Sort");
    if(!originalToken(compiler,&token,nullptr,1)||token.kind!=1)
        fatal(L"Sort requires a named delegate comparator");
    void* scope=*reinterpret_cast<void**>(static_cast<unsigned char*>(compiler)+0x14);
    auto function=static_cast<unsigned char*>(originalFindField(compiler,scope,token.identifier,nullptr,nullptr));
    if(!function||std::wcsncmp(fullName(function,nullptr),L"Function ",9)||
       !(*reinterpret_cast<unsigned*>(function+0x80)&0x100000))
        fatal(L"Sort comparator must be a delegate");
    unsigned parameters=0,returns=0;
    for(auto field=*reinterpret_cast<unsigned char**>(function+0x3c);field;
        field=*reinterpret_cast<unsigned char**>(field+0x2c)){
        unsigned flags=*reinterpret_cast<unsigned*>(field+0x3c);
        if(!(flags&0x80))continue;
        Property type{};fromPropertyHook(&type,nullptr,field);
        if(flags&0x400){
            if(type.type!=Int||type.arrayDim!=1)fatal(L"Sort comparator must return int");
            ++returns;
        }else{
            if((flags&0x910)||type.type!=element.type||type.arrayDim!=1||
               type.object!=element.object||type.meta!=element.meta)
                fatal(L"Sort comparator parameters must match the array element type");
            ++parameters;
        }
    }
    if(parameters!=2||returns!=1)fatal(L"Sort comparator requires two parameters and an int result");
    wchar_t backing[160];swprintf_s(backing,L"__%ls__Delegate",token.identifier);
    auto property=originalFindField(compiler,scope,backing,nullptr,nullptr);
    if(!property||std::wcsncmp(fullName(property,nullptr),L"DelegateProperty ",17))
        fatal(L"Sort comparator backing property was not found");
    if(!matchSymbol(compiler,L")"))fatal(L"Expected ')' after Sort comparator");
    Retry end{};saveRetry(compiler,&end);
    const unsigned char opcode=0x47;emit(compiler,&opcode,1);
    moveCode(compiler,reinterpret_cast<Retry*>(frame-0x9c),&end);
    const unsigned char instance=1;emit(compiler,&instance,1);emit(compiler,&property,4);
    return 1;
}

#ifdef _MSC_VER
__declspec(naked) void arraySortHook(){
    __asm {
        pushad
        push ebp
        push ebx
        call compileArraySort
        add esp,8
        test eax,eax
        popad
        jz unsupported
        xor esi,esi
        jmp dword ptr [arraySortContinue]
    unsupported:
        jmp dword ptr [arraySortFallback]
    }
}
#else
__attribute__((naked)) void arraySortHook(){
    __asm__ volatile(
        "pushal\n\tpushl %%ebp\n\tpushl %%ebx\n\tcall %P0\n\t"
        "addl $8, %%esp\n\ttestl %%eax,%%eax\n\tpopal\n\tjz 1f\n\t"
        "xorl %%esi,%%esi\n\tjmp *%1\n\t1: jmp *%2\n\t"
        : : "i"(compileArraySort), "m"(arraySortContinue), "m"(arraySortFallback));
}
#endif

bool enableSortSerialization(){
    auto core=reinterpret_cast<unsigned char*>(GetModuleHandleW(L"Core.dll"));
    // Exact SDK SerializeExpr uses a byte dispatch table for opcodes 0..0x45.
    // Sort has two expressions, the same traversal shape as Let/DelegateCmp.
    if(!core||std::memcmp(core+0x2895e,"\x83\xfa\x45\x0f\x87",5)||
       std::memcmp(core+0x28967,"\x0f\xb6\x92",3))return false;
    auto old=core+0x28f64;
    if(old[3]!=31||old[0x0f]!=10||old[0x45]!=10)return false;
    std::memcpy(sortSerializeTable,old,0x46);
    sortSerializeTable[0x46]=old[3]; // Unsupported INT64 literal stays rejected.
    sortSerializeTable[0x47]=old[0x0f];
    DWORD protection;
    if(!VirtualProtect(core+0x2895e,16,PAGE_EXECUTE_READWRITE,&protection))return false;
    core[0x28960]=0x47;
    auto table=sortSerializeTable;std::memcpy(core+0x2896a,&table,4);
    DWORD ignored;VirtualProtect(core+0x2895e,16,protection,&ignored);
    FlushInstructionCache(GetCurrentProcess(),core+0x2895e,16);
    return true;
}

unsigned marker(const Token& t) {
    unsigned value;
    std::memcpy(&value, t.data + 8, 4);
    return value;
}

void mark(Token& t, unsigned value) { std::memcpy(t.data + 8, &value, 4); }

int __cdecl conversionHook(const Property* dest, const Property* source) {
    pendingStruct = nullptr;
    // SDK conversion lookup indexes a 14x14 table without bounds checks.
    if(dest->type==PointerType||source->type==PointerType)return NoConversion;
    const bool d64 = is64(*dest), s64 = is64(*source);
    if (!d64 && !s64) return originalConversion(dest, source);
    // Never widen arrays, enum values, or out parameters via this path.
    if (dest->arrayDim != 1 || source->arrayDim != 1 || (dest->flags & 0x100))
        return NoConversion;
    if ((dest->type == Byte && dest->object) || (source->type == Byte && source->object))
        return NoConversion;
    const int code = conversion(dest->type, d64, source->type, s64);
    if (code != NoConversion && d64) pendingStruct = dest->object;
    return code;
}

int __fastcall conversionCostHook(void* compiler, void*, const Property* dest, const Property* source) {
    if(dest->type==PointerType||source->type==PointerType){
        if(dest->type==PointerType&&source->type==PointerType&&dest->arrayDim==source->arrayDim&&
           (!(dest->flags&0x100)||((source->flags&0x100)&&!(source->flags&2))))return 0;
        return 0x7fffffff;
    }
    const int cost = originalConversionCost(compiler, dest, source);
    // The old resolver uses the maximum argument cost, not the sum. Giving
    // byte->int and byte/int->INT64 the same cost makes ordinary expressions
    // such as byteResult = 255 - intValue ambiguous. Preserve int arithmetic.
    if (cost == 101 && is64(*dest) && (source->type == Int || source->type == Byte))
        return 102;
    return cost;
}

void* __fastcall findFieldHook(void* compiler, void*, void* scope, const wchar_t* name,
                              void* requiredClass, const wchar_t* errorContext) {
    void* found = originalFindField(compiler, scope, name, requiredClass, errorContext);
    if (found || !scope || !name) return found;
    // These three client fields are all IntProperty, ArrayDim=1, flags=0.
    // They are verified imports of the original Interface.u. Build metadata
    // proxies only: NEVER append storage or children to the old native Vehicle.
    // The emitted import resolves to the real Engine.Vehicle field in the game.
    if (_wcsicmp(name, L"MaxFuel") && _wcsicmp(name, L"CurFuel") && _wcsicmp(name, L"DriverID"))
        return nullptr;
    const wchar_t* ownerName = fullName(scope, nullptr);
    if (!ownerName || _wcsicmp(ownerName, L"Class Engine.Vehicle")) return nullptr;
    void* type = intPropertyClass();
    if (requiredClass) {
        void* check = type;
        for (unsigned depth = 0; check && check != requiredClass && depth < 32; ++depth)
            check = *reinterpret_cast<void**>(static_cast<unsigned char*>(check) + 0x28);
        if (check != requiredClass) return nullptr;
    }
    if (void* cached = findObject(type, scope, name, 0)) return cached;
    const auto owner = static_cast<unsigned char*>(scope);
    const int sizeBefore = *reinterpret_cast<int*>(owner + 0x40);
    void* const childrenBefore = *reinterpret_cast<void**>(owner + 0x3c);
    int fname = 0;
    constructName(&fname, name, 1);  // FNAME_Add
    auto property = static_cast<unsigned char*>(constructObject(type, scope, fname,
        0x80004, nullptr, warningDevice ? *warningDevice : nullptr, nullptr)); // Public|Standalone
    if (!property) fatal(L"Could not create client field metadata proxy");
    *reinterpret_cast<int*>(property + 0x34) = 1;  // ArrayDim
    *reinterpret_cast<int*>(property + 0x38) = 4;  // ElementSize
    *reinterpret_cast<unsigned*>(property + 0x3c) = 0;  // PropertyFlags
    *reinterpret_cast<int*>(property + 0x48) = 0;  // unused: compiler emits a symbolic reference
    if (*reinterpret_cast<int*>(owner + 0x40) != sizeBefore ||
        *reinterpret_cast<void**>(owner + 0x3c) != childrenBefore)
        fatal(L"Client field proxy changed native class layout");
    std::fwprintf(stderr, L"[ucc64] Symbolic client field: Engine.Vehicle.%ls\n", name);
    return property;
}

Token* __fastcall ctorHook(Token* self, void*, const Property* prop) {
    Property fixed = *prop;
    const auto caller = reinterpret_cast<std::uintptr_t>(CALLER_ADDRESS()) - editorBase;
    // CompileExpr's automatic-cast result constructor zeroes Struct in the
    // original code. Repair only this call site, after our own conversion.
    if (caller == 0x7a53e && fixed.type == Struct &&
        !fixed.object && pendingStruct) {
        fixed.object = pendingStruct;
        pendingStruct = nullptr;
    }
    return originalCtor(self, &fixed);
}

void __fastcall constantHook(Token* token, void*, const Property* target) {
    if(token->property.type==Bool&&marker(*token)==Emitted)return;
    if(target->type==PointerType){
        int value=1;std::memcpy(&value,token->data,4);
        if(target->arrayDim==1&&token->kind==3&&token->property.type==Int&&value==0){
            token->property={PointerType,1,2,nullptr,nullptr};mark(*token,Literal);
        }
        return;
    }
    if(token->property.type==PointerType)return;
    if (is64(token->property)) return;  // do not feed the value to 32-bit folding
    originalConstant(token, target);
}

void __fastcall emitHook(void* compiler, void*, Token* token) {
    if(token->property.type==Bool&&marker(*token)==Emitted)return;
    if(token->property.type==PointerType&&token->kind==3){
        if(marker(*token)!=Literal)fatal(L"Unexpected pointer constant representation");
        const unsigned char zero=0x25;emit(compiler,&zero,1);return;
    }
    if (!is64(token->property) || token->kind != 3) {
        originalEmit(compiler, token);
        return;
    }
    if (marker(*token) == Emitted) return;
    if (marker(*token) != Literal) fatal(L"Unexpected INT64 constant representation");
    std::int64_t value;
    std::memcpy(&value, token->data, 8);
    // The client's package serializer does not have a verified 0x46 case.
    // Emit the proven primitive cast/string sequence instead, transparently.
    char decimal[32];
    const int count = sprintf_s(decimal, "%lld", static_cast<long long>(value));
    if (count <= 0) fatal(L"Could not format INT64 constant");
    const unsigned char prefix[] = {0x39, 0x5e, 0x1f};
    emit(compiler, prefix, sizeof(prefix));
    emit(compiler, decimal, count + 1);
}

const wchar_t* invalidDefault() {
    // ImportText is not inside CompileExpr's appThrowf catch. Throwing there
    // reaches UCC's generic protection-fault handler. Report through GWarn
    // and return failure using the native ImportText contract instead.
    if (warningDevice && *warningDevice) {
        auto device = static_cast<unsigned char*>(*warningDevice);
        auto table = *reinterpret_cast<void***>(device);
        using Serialize = void (__thiscall*)(void*, const wchar_t*, int);
        reinterpret_cast<Serialize>(table[0])(device,
            L"INT64 extension: Invalid numeric INT64 default value", 0x315);
    }
    return nullptr;
}

void __fastcall feedbackHook(void* device, void*, const wchar_t* text, int event) {
    auto errors = reinterpret_cast<int*>(static_cast<unsigned char*>(device) + 8);
    const int before = *errors;
    originalFeedback(device, text, event);
    // This UCC's ANSI feedback implementation increments NumWarnings for
    // NAME_Error too. Restore the error count so failed compiles exit nonzero.
    if (event == 0x315 && *errors == before) ++*errors;
}

bool containsReplicatedPointer(void* field, std::set<void*>& seen) {
    if(!field||!seen.insert(field).second)return false;
    if(isPtrProperty(field))return true;
    auto bytes=static_cast<unsigned char*>(field);
    auto type=objectClass(field);
    if(type==arrayPropertyClass())
        return containsReplicatedPointer(*reinterpret_cast<void**>(bytes+0x6c),seen);
    const bool function=type==functionClass();
    if(type!=structPropertyClass()&&!function)return false;
    auto scope=function?field:*reinterpret_cast<void**>(bytes+0x6c);
    if(!scope)return false;
    std::set<void*> scopes;
    for(;scope&&scopes.insert(scope).second;
        scope=function?nullptr:*reinterpret_cast<void**>(static_cast<unsigned char*>(scope)+0x28)){
        for(auto child=*reinterpret_cast<void**>(static_cast<unsigned char*>(scope)+0x3c);child;
            child=*reinterpret_cast<void**>(static_cast<unsigned char*>(child)+0x2c)){
            // Function locals are not transmitted; only parameter descriptors count.
            if(function&&!(*reinterpret_cast<unsigned*>(static_cast<unsigned char*>(child)+0x3c)&0x80))continue;
            if(containsReplicatedPointer(child,seen))return true;
        }
    }
    return false;
}

int __fastcall tokenHook(void* compiler, void*, Token* token, const Property* hint, int noConsts) {
    activeCompiler=compiler;
    applyClientEnumProfile();
    const auto caller = reinterpret_cast<std::uintptr_t>(CALLER_ADDRESS()) - editorBase;
    int result = originalToken(compiler, token, hint, noConsts);
    // GetToken only initializes the active scalar payload. A reused token can
    // retain our INT64/PointerEqual emission marker beyond the bool value.
    // A newly lexed bool is never an already-emitted expression.
    if (result && token->kind == 3 && token->property.type == Bool)
        mark(*token, 0);
    if (!result || noConsts) return result;
    // GetIdentifier's GetToken call is used by replication-member parsing.
    // Our declaration parser consumes field names directly through originalToken.
    if(token->kind==1&&caller==0x7c419){
        void* scope=*reinterpret_cast<void**>(static_cast<unsigned char*>(compiler)+0x14);
        std::set<void*> seen;
        if(scope&&containsReplicatedPointer(originalFindField(compiler,scope,token->identifier,nullptr,nullptr),seen))
            fatal(L"Pointer replication is unsupported");
    }

    // Client class-header flag absent from this older parser. Restrict handling
    // to CompileDeclaration's class-attribute loop (verified call site).
    while (caller == 0x80de0 && result && token->kind == 1) {
        const bool noReplication = _wcsicmp(token->identifier, L"nonativereplication") == 0;
        const bool localized = _wcsicmp(token->identifier, L"localized") == 0;
        const bool dynamicRecompile = _wcsicmp(token->identifier, L"dynamicrecompile") == 0;
        if (!noReplication && !localized && !dynamicRecompile) break;
        auto currentClass = *reinterpret_cast<unsigned char**>(
            static_cast<unsigned char*>(compiler) + 0x14);
        if (!currentClass) fatal(L"No class for client class flag");
        auto flags = reinterpret_cast<unsigned*>(currentClass + 0x498);
        if (noReplication) *flags &= ~0x800u;
        if (localized) *flags |= 0x20u;
        if (dynamicRecompile) *flags |= 0x400000u;
        result = originalToken(compiler, token, hint, noConsts);
    }
    if (!result) return result;

    // Consume casts only at CompileExpr's primary-expression GetToken call.
    // Declaration parsing and lookahead must remain side-effect free.
    if (caller == 0x784d3 && token->kind == 1 &&
        _wcsicmp(token->identifier, L"int64") == 0 && matchSymbol(compiler, L"(")) {
        Retry begin{}, end{};
        saveRetry(compiler, &begin);
        Token operand{};
        const Property any{0, 1, 0, nullptr, nullptr};
        if (compileExpr(compiler, any, L"INT64 conversion", &operand, INT_MAX, nullptr) != 1)
            fatal(L"Missing or invalid expression in INT64(...)");
        if (!matchSymbol(compiler, L")")) fatal(L"Missing ')' after INT64 conversion");
        Property dest{Struct, 1, 0, getInt64Struct(), nullptr};
        if (!is64(operand.property)) {
            // Explicit INT64(enum) uses the enum's byte representation. Keep
            // enum widening disabled in implicit conversions/overload ranking.
            Property source=operand.property;
            if(source.type==Byte)source.object=nullptr;
            const int code = conversionHook(&dest, &source);
            if (code == NoConversion) fatal(L"Unsupported source type for INT64 conversion");
            saveRetry(compiler, &end);
            const unsigned char prefix[] = {0x39, static_cast<unsigned char>(code)};
            emit(compiler, prefix, sizeof(prefix));
            moveCode(compiler, &begin, &end);
        }
        token->property = dest;
        token->kind = 3;
        mark(*token, Emitted);
        return result;
    }

    if(token->kind==1&&caller==0x784d3&&!_wcsicmp(token->identifier,L"PointerEqual")){
        if(!matchSymbol(compiler,L"("))fatal(L"Expected '(' after PointerEqual");
        const unsigned char compare=0x9a;emit(compiler,&compare,1);
        const Property pointer{PointerType,1,0,nullptr,nullptr};Token argument{};
        if(compileExpr(compiler,pointer,L"PointerEqual argument",&argument,INT_MAX,nullptr)!=1)
            fatal(L"PointerEqual requires pointer arguments");
        if(!matchSymbol(compiler,L","))fatal(L"Expected ',' in PointerEqual");
        argument=Token{};
        if(compileExpr(compiler,pointer,L"PointerEqual argument",&argument,INT_MAX,nullptr)!=1)
            fatal(L"PointerEqual requires pointer arguments");
        if(!matchSymbol(compiler,L")"))fatal(L"Expected ')' after PointerEqual");
        const unsigned char end=0x16;emit(compiler,&end,1);
        token->property={Bool,1,0,nullptr,nullptr};token->kind=3;mark(*token,Emitted);
        return result;
    }

    if (token->kind == 3 && token->property.type == Int) {
        std::int64_t value;
        const auto parsed = parseInteger(token->identifier, value);
        if (parsed == ParseResult::Overflow) fatal(L"Integer literal is outside signed INT64 range");
        if (parsed != ParseResult::Valid) return result;
        // Preserve legacy 32-bit hexadecimal masks, e.g. 0xffffffff.
        const bool legacyHex = token->identifier[0] == L'0' &&
            (token->identifier[1] == L'x' || token->identifier[1] == L'X') &&
            value >= 0 && static_cast<std::uint64_t>(value) <= UINT32_MAX;
        if (!legacyHex && (value > INT32_MAX || value < INT32_MIN)) {
            token->property = {Struct, 1, 0, getInt64Struct(), nullptr};
            std::memcpy(token->data, &value, 8);
            mark(*token, Literal);
        }
    }
    return result;
}

const wchar_t* __fastcall importHook(void* property, void*, const wchar_t* text,
                                    unsigned char* data, int flags) {
    void* object = *reinterpret_cast<void**>(static_cast<unsigned char*>(property) + 0x6c);
    if (!isInt64Object(object)) return originalImport(property, text, data, flags);
    const wchar_t* begin = text;
    while (*begin == L' ' || *begin == L'\t') ++begin;
    if (*begin == L'(') return originalImport(property, text, data, flags);
    wchar_t number[80];
    size_t count = 0;
    const wchar_t* end = begin;
    while (*end && *end != L',' && *end != L')' && *end != L'\r' && *end != L'\n' &&
           *end != L' ' && *end != L'\t') {
        if (count == 79) return invalidDefault();
        number[count++] = *end++;
    }
    number[count] = 0;
    std::int64_t value;
    if (parseInteger(number, value) != ParseResult::Valid) return invalidDefault();
    const ClientInt64 pair = split(value);
    std::memcpy(data, &pair, sizeof(pair));
    return end;
}

bool hook(void* target, void* replacement, void** original) {
    auto status = MH_CreateHook(target, replacement, original);
    if (status == MH_OK) status = MH_QueueEnableHook(target);
    if (status != MH_OK)
        std::fprintf(stderr, "[ucc64] Hook %p failed: %s\n", target, MH_StatusToString(status));
    return status == MH_OK;
}

bool installPointerSizes() {
    // All seven reads of FPropertyBase's scalar-size table in this exact SDK,
    // including inlined context paths. Preserve flags and non-result registers;
    // only our private tag bypasses the original instruction. ArrayDim is still
    // multiplied by the surrounding SDK code. No type tag is written to packages.
    const unsigned sites[]={0x6f8ea,0x77334,0x774fd,0x77d1c,0x79934,0x79aa2,0x84aaa};
    const unsigned char registers[]={1,3,3,1,0,0,0}; // ECX, EBX, EAX
    for(unsigned i=0;i<7;++i){
        auto instruction=address<unsigned char*>(sites[i]);
        unsigned table=0;std::memcpy(&table,instruction+3,4);
        if(instruction[0]!=0x8b||instruction[1]!=(registers[i]*8+4)||instruction[2]!=0x85||
            table!=editorBase+0xcdb58)return false;
    }
    auto code=static_cast<unsigned char*>(VirtualAlloc(nullptr,7*32,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE));
    if(!code)return false;
    for(unsigned i=0;i<7;++i){
        auto stub=code+i*32;
        const unsigned char prefix[]={0x9c,0x3d,0,0,0,0,0x75,0x0b,0x9d,0xb8,4,0,0,0,0xe9,0,0,0,0,0x9d,0xe9,0,0,0,0};
        std::memcpy(stub,prefix,sizeof(prefix));
        const unsigned tag=PointerType;std::memcpy(stub+2,&tag,4);stub[9]+=registers[i];
        void* fallback=nullptr;
        if(!hook(address<void*>(sites[i]),stub,&fallback))return false;
        auto next=static_cast<unsigned>(editorBase+sites[i]+7-reinterpret_cast<std::uintptr_t>(stub+19));
        auto original=static_cast<unsigned>(reinterpret_cast<std::uintptr_t>(fallback)-reinterpret_cast<std::uintptr_t>(stub+25));
        std::memcpy(stub+15,&next,4);std::memcpy(stub+21,&original,4);
    }
    DWORD previous;
    if(!VirtualProtect(code,7*32,PAGE_EXECUTE_READ,&previous))return false;
    FlushInstructionCache(GetCurrentProcess(),code,7*32);
    return true;
}

bool installEditor(HMODULE module) {
    if (installed) return true;
    editorBase = reinterpret_cast<std::uintptr_t>(module);
    // Launcher also checks SHA256; this guards ABI assumptions for direct use.
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(editorBase + dos->e_lfanew);
    if (nt->OptionalHeader.ImageBase != 0x10200000 ||
        std::memcmp(address<void*>(0x705a0), "\x53\x8b\x1d", 3) != 0 ||
        std::memcmp(address<void*>(0x722c0), "\x55\x8b\xec\x6a\xff", 5) != 0 ||
        std::memcmp(address<void*>(0x7d490), "\x55\x8b\xec\x6a\xff", 5) != 0 ||
        std::memcmp(address<void*>(0x7e4e0), "\x55\x8b\xec\x6a\xff", 5) != 0 ||
        std::memcmp(address<void*>(0x78430), "\x55\x8b\xec\x6a\xff", 5) != 0) return false;
    compileExpr = address<CompileExpr>(0x78430);
    matchSymbol = address<MatchSymbol>(0x73320);
    getConstInt = address<GetConstInt>(0x76740);
    saveRetry = address<SaveRetry>(0x71290);
    moveCode = address<MoveCode>(0x736e0);
    wchar_t sortOption[2]{};
    clientArraySort=GetEnvironmentVariableW(L"UCC64_CLIENT_ARRAY_SORT",sortOption,2)==1&&sortOption[0]==L'1';
    wchar_t scopedOption[2]{};
    scopedEnumCasts=GetEnvironmentVariableW(L"UCC64_SCOPED_ENUM_CASTS",scopedOption,2)==1&&scopedOption[0]==L'1';
    wchar_t enumOption[32]{};
    auto enumOptionSize=GetEnvironmentVariableW(L"UCC64_CLIENT_ENUM_PROFILE",enumOption,32);
    if(enumOptionSize){
        if(enumOptionSize>=32||_wcsicmp(enumOption,L"korea290"))return false;
        clientEnumProfile=true;
    }
    if(clientArraySort){
        auto sortDiagnostic=address<unsigned char*>(0x79467);
        unsigned diagnosticAddress=0;std::memcpy(&diagnosticAddress,sortDiagnostic+1,4);
        if(sortDiagnostic[0]!=0x68||diagnosticAddress!=editorBase+0xc7558)return false;
        arraySortContinue=address<void*>(0x7917a);
        if(!hook(address<void*>(0x79467),reinterpret_cast<void*>(arraySortHook),&arraySortFallback)||
           !enableSortSerialization())return false;
    }
    if (!installPointerSizes() ||
        !hook(address<void*>(0x705a0), reinterpret_cast<void*>(conversionHook), reinterpret_cast<void**>(&originalConversion)) ||
        !hook(address<void*>(0x7d490), reinterpret_cast<void*>(varTypeHook), reinterpret_cast<void**>(&originalVarType)) ||
        !hook(address<void*>(0x7e4e0), reinterpret_cast<void*>(varNameHook), reinterpret_cast<void**>(&originalVarName)) ||
         !hook(address<void*>(0x722c0), reinterpret_cast<void*>(fromPropertyHook), reinterpret_cast<void**>(&originalFromProperty)) ||
        !hook(address<void*>(0x713c0), reinterpret_cast<void*>(conversionCostHook), reinterpret_cast<void**>(&originalConversionCost)) ||
        !hook(address<void*>(0x74870), reinterpret_cast<void*>(findFieldHook), reinterpret_cast<void**>(&originalFindField)) ||
        !hook(address<void*>(0x72760), reinterpret_cast<void*>(ctorHook), reinterpret_cast<void**>(&originalCtor)) ||
        !hook(address<void*>(0x7b590), reinterpret_cast<void*>(tokenHook), reinterpret_cast<void**>(&originalToken)) ||
        !hook(address<void*>(0x72ac0), reinterpret_cast<void*>(emitHook), reinterpret_cast<void**>(&originalEmit)) ||
        !hook(address<void*>(0x74260), reinterpret_cast<void*>(constantHook), reinterpret_cast<void**>(&originalConstant))) return false;
    if (!warningDevice || !*warningDevice) return false;
    auto feedback = (*reinterpret_cast<void***>(*warningDevice))[0];
    if (!hook(feedback, reinterpret_cast<void*>(feedbackHook), reinterpret_cast<void**>(&originalFeedback)) ||
        MH_ApplyQueued() != MH_OK) return false;
    installed = true;
    log("Editor hooks installed (INT64 and native pointer declarations)");
    if(clientArraySort)log("Experimental client array.Sort enabled; requires a client supporting opcode 0x47");
    return true;
}

void* __cdecl getDllHook(const wchar_t* name) {
    void* handle = originalGetDll(name);
    HMODULE editor = GetModuleHandleW(L"Editor.dll");
    if (editor && !installed && !installEditor(editor))
        fatal(L"Could not install Editor.dll hooks");
    return handle;
}

template<class T> T resolve(HMODULE module, const char* name) {
    return reinterpret_cast<T>(GetProcAddress(module, name));
}
}

// Called by the launcher in a remote thread while UCC's primary thread is
// suspended. DllMain never loads Editor or patches executable code.
extern "C" BRIDGE_EXPORT DWORD WINAPI Ucc64Initialize(void*) {
    HMODULE core = GetModuleHandleW(L"Core.dll");
    if (!core) return 1;
    fullName = resolve<GetFullName>(core, "?GetFullName@UObject@@QBEPBGPAG@Z");
    structClass = resolve<StaticClass>(core, "?StaticClass@UStruct@@SAPAVUClass@@XZ");
    findObject = resolve<FindObject>(core, "?StaticFindObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBGH@Z");
    throwError = resolve<ThrowError>(core, "?appThrowf@@YAXPBGZZ");
    warningDevice = resolve<void**>(core, "?GWarn@@3PAVFFeedbackContext@@A");
    intPropertyClass = resolve<StaticClass>(core, "?StaticClass@UIntProperty@@SAPAVUClass@@XZ");
    arrayPropertyClass = resolve<StaticClass>(core, "?StaticClass@UArrayProperty@@SAPAVUClass@@XZ");
    structPropertyClass = resolve<StaticClass>(core, "?StaticClass@UStructProperty@@SAPAVUClass@@XZ");
    functionClass = resolve<StaticClass>(core, "?StaticClass@UFunction@@SAPAVUClass@@XZ");
    objectClass = resolve<ObjectClass>(core, "?GetClass@UObject@@QBEPAVUClass@@XZ");
    constructName = resolve<NameConstructor>(core, "??0FName@@QAE@PBGW4EFindName@@@Z");
    constructObject = resolve<ConstructObject>(core, "?StaticConstructObject@UObject@@SAPAV1@PAVUClass@@PAV1@VFName@@K1PAVFOutputDevice@@1@Z");
    enumClass = resolve<StaticClass>(core,"?StaticClass@UEnum@@SAPAVUClass@@XZ");
    arrayAdd = resolve<ArrayAdd>(core,"?Add@FArray@@QAEHHH@Z");
    nameText = resolve<NameText>(core,"??DFName@@QBEPBGXZ");
    auto loader = resolve<void*>(core, "?appGetDllHandle@@YAPAXPBG@Z");
    auto importer = resolve<void*>(core, "?ImportText@UStructProperty@@UBEPBGPBGPAEH@Z");
    if (!fullName || !structClass || !findObject || !throwError || !warningDevice || !loader || !importer ||
        !intPropertyClass || !arrayPropertyClass || !structPropertyClass || !functionClass || !objectClass ||
        !constructName || !constructObject || !enumClass || !arrayAdd || !nameText) return 2;
    if (MH_Initialize() != MH_OK) return 3;
    if (!registerPtrProperty(core)) return 6;
    if (!hook(loader, reinterpret_cast<void*>(getDllHook), reinterpret_cast<void**>(&originalGetDll)) ||
        !hook(reinterpret_cast<void*>(findObject),reinterpret_cast<void*>(scopedEnumFindHook),reinterpret_cast<void**>(&originalFindObject)) ||
        !hook(importer, reinterpret_cast<void*>(importHook), reinterpret_cast<void**>(&originalImport)) ||
        MH_ApplyQueued() != MH_OK) return 4;
    if (HMODULE editor = GetModuleHandleW(L"Editor.dll"))
        if (!installEditor(editor)) return 5;
    log("Initialized; waiting for the compiler to load Editor.dll");
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {
    // Keep thread notifications enabled: the bridge uses static CRT and TLS.
    return TRUE;
}
