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
#include "MinHook.h"
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
NameConstructor constructName;
ConstructObject constructObject;
StaticClass intPropertyClass;
CompileExpr compileExpr;
MatchSymbol matchSymbol;
SaveRetry saveRetry;
MoveCode moveCode;
GetFullName fullName;
StaticClass structClass;
FindObject findObject;
ThrowError throwError;
void** warningDevice;
std::uintptr_t editorBase;
void* int64Struct;
thread_local void* pendingStruct;
bool installed;

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

unsigned marker(const Token& t) {
    unsigned value;
    std::memcpy(&value, t.data + 8, 4);
    return value;
}

void mark(Token& t, unsigned value) { std::memcpy(t.data + 8, &value, 4); }

int __cdecl conversionHook(const Property* dest, const Property* source) {
    pendingStruct = nullptr;
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
    if (is64(token->property)) return;  // do not feed the value to 32-bit folding
    originalConstant(token, target);
}

void __fastcall emitHook(void* compiler, void*, Token* token) {
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

int __fastcall tokenHook(void* compiler, void*, Token* token, const Property* hint, int noConsts) {
    const auto caller = reinterpret_cast<std::uintptr_t>(CALLER_ADDRESS()) - editorBase;
    int result = originalToken(compiler, token, hint, noConsts);
    if (!result || noConsts) return result;

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
            const int code = conversionHook(&dest, &operand.property);
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

bool installEditor(HMODULE module) {
    if (installed) return true;
    editorBase = reinterpret_cast<std::uintptr_t>(module);
    // Launcher also checks SHA256; this guards ABI assumptions for direct use.
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(editorBase + dos->e_lfanew);
    if (nt->OptionalHeader.ImageBase != 0x10200000 ||
        std::memcmp(address<void*>(0x705a0), "\x53\x8b\x1d", 3) != 0 ||
        std::memcmp(address<void*>(0x78430), "\x55\x8b\xec\x6a\xff", 5) != 0) return false;
    compileExpr = address<CompileExpr>(0x78430);
    matchSymbol = address<MatchSymbol>(0x73320);
    saveRetry = address<SaveRetry>(0x71290);
    moveCode = address<MoveCode>(0x736e0);
    if (!hook(address<void*>(0x705a0), reinterpret_cast<void*>(conversionHook), reinterpret_cast<void**>(&originalConversion)) ||
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
    log("Editor hooks installed (experimental INT64 bridge)");
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
    constructName = resolve<NameConstructor>(core, "??0FName@@QAE@PBGW4EFindName@@@Z");
    constructObject = resolve<ConstructObject>(core, "?StaticConstructObject@UObject@@SAPAV1@PAVUClass@@PAV1@VFName@@K1PAVFOutputDevice@@1@Z");
    auto loader = resolve<void*>(core, "?appGetDllHandle@@YAPAXPBG@Z");
    auto importer = resolve<void*>(core, "?ImportText@UStructProperty@@UBEPBGPBGPAEH@Z");
    if (!fullName || !structClass || !findObject || !throwError || !warningDevice || !loader || !importer ||
        !intPropertyClass || !constructName || !constructObject) return 2;
    if (MH_Initialize() != MH_OK) return 3;
    if (!hook(loader, reinterpret_cast<void*>(getDllHook), reinterpret_cast<void**>(&originalGetDll)) ||
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
