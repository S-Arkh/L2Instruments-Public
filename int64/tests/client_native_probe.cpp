// Calls only value-only exported handlers in the supplied client Core.dll.
// It does not initialize the game or load packages. This is an additional ABI
// check, not a replacement for loading the compiled package in the client.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <vector>
#include "int64_semantics.h"

static_assert(sizeof(void*) == 4);
using Handler = void (__thiscall*)(void*, void*, void*);
struct Frame {
    void* vtable = nullptr;
    void* node = nullptr;
    void* object = nullptr;
    unsigned char* code = nullptr;
    void* locals = nullptr;
    unsigned char spare[128]{};
};
static_assert(offsetof(Frame, code) == 12);

// Minimal host allocator for FString in these isolated value-only tests.
// FMalloc has no leading virtual destructor; Malloc/Realloc/Free are slots 0..2.
void* __fastcall allocate(void*, void*, unsigned bytes, const wchar_t*) {
    return HeapAlloc(GetProcessHeap(), 0, bytes);
}
void __fastcall release(void*, void*, void* data) {
    if (data) HeapFree(GetProcessHeap(), 0, data);
}
void* __fastcall reallocate(void* self, void*, void* data, unsigned bytes, const wchar_t* tag) {
    if (!bytes) { release(self, nullptr, data); return nullptr; }
    if (!data) return allocate(self, nullptr, bytes, tag);
    return HeapReAlloc(GetProcessHeap(), 0, data, bytes);
}
void __fastcall allocatorNoop(void*, void*) {}

void append32(std::vector<unsigned char>& data, std::uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) data.push_back(static_cast<unsigned char>(value >> (8 * i)));
}
void literal(std::vector<unsigned char>& code, std::int64_t value) {
    const auto words = ucc64::split(value);
    code.push_back(0x46);
    append32(code, words.high);
    append32(code, words.low);
}
bool call(HMODULE core, const char* name, std::vector<unsigned char>& code,
          void* result, size_t expectedConsumed) {
    auto fn = reinterpret_cast<Handler>(GetProcAddress(core, name));
    if (!fn) { std::fprintf(stderr, "Missing %s\n", name); return false; }
    Frame frame;
    frame.code = code.data();
    fn(nullptr, &frame, result);
    if (static_cast<size_t>(frame.code - code.data()) != expectedConsumed) {
        std::fprintf(stderr, "Wrong code consumption: %s\n", name);
        return false;
    }
    return true;
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 3) {
        std::fprintf(stderr, "Usage: client_native_probe.exe <absolute client Core.dll> <dependency directory>\n");
        return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetDllDirectoryW(argv[2]);
    HMODULE core = LoadLibraryW(argv[1]);
    if (!core) {
        std::fprintf(stderr, "Load client Core.dll failed: %lu\n", GetLastError());
        HMODULE image = LoadLibraryExW(argv[1], nullptr, DONT_RESOLVE_DLL_REFERENCES);
        if (image) {
            auto base = reinterpret_cast<unsigned char*>(image);
            auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(image);
            auto nt = reinterpret_cast<IMAGE_NT_HEADERS32*>(base + dos->e_lfanew);
            auto entry = base + nt->OptionalHeader.AddressOfEntryPoint;
            std::fprintf(stderr, "Mapped entry %p:", entry);
            for (int i = 0; i < 16; ++i) std::fprintf(stderr, " %02x", entry[i]);
            std::fprintf(stderr, "\n");
            FreeLibrary(image);
        }
        return 3;
    }
    const auto equal = [](ucc64::ClientInt64 value, std::int64_t expected) {
        const auto words = ucc64::split(expected);
        return value.high == words.high && value.low == words.low;
    };
    ucc64::ClientInt64 result{};
    std::vector<unsigned char> code{0x1d};
    append32(code, 0xffffffff);
    code.push_back(0x0b);
    if (!call(core, "?execIntToINT64@UObject@@QAEXAAUFFrame@@QAX@Z", code, &result, 5) || !equal(result, -1)) return 4;
    std::puts("PASS client int(-1) -> INT64 (sign extension and word order)");

    struct Arithmetic { const char* name; std::int64_t a, b, result; };
    const Arithmetic cases[] = {
        {"Add", 5000000000LL, 10, 5000000010LL},
        {"Subtract", -5000000000LL, 10, -5000000010LL},
        {"Multiply", 5000000000LL, 2, 10000000000LL},
        {"Divide", -10000000000LL, 2, -5000000000LL}
    };
    for (const auto& item : cases) {
        code.clear();
        literal(code, item.a);
        literal(code, item.b);
        code.push_back(0x16);
        code.push_back(0x0b);
        char symbol[160];
        sprintf_s(symbol, "?exec%s_INT64INT64@UObject@@QAEXAAUFFrame@@QAX@Z", item.name);
        if (!call(core, symbol, code, &result, 19) || !equal(result, item.result)) return 5;
        std::printf("PASS client INT64 %s\n", item.name);
    }
    code.clear();
    literal(code, INT64_MAX);
    literal(code, INT64_MIN);
    code.push_back(0x16);
    code.push_back(0x0b);
    int comparison = 0;
    if (!call(core, "?execGreater_INT64INT64@UObject@@QAEXAAUFFrame@@QAX@Z", code, &comparison, 19) || comparison != 1) return 6;
    std::puts("PASS client signed comparison INT64_MAX > INT64_MIN");

    code = {0x2c, 255, 0x0b};
    std::uint32_t byteResult = 0xaabbcc00;
    if (!call(core, "?execIntToByte@UObject@@QAEXAAUFFrame@@QAX@Z", code, &byteResult, 2) ||
        byteResult != 0xaabbccff) return 12;
    code = {0x1e};
    append32(code, 0x437f0000);  // IEEE float 255.0
    code.push_back(0x0b);
    byteResult = 0xaabbcc00;
    if (!call(core, "?execFloatToByte@UObject@@QAEXAAUFFrame@@QAX@Z", code, &byteResult, 5) ||
        byteResult != 0xaabbccff) return 13;
    code = {0x24, 255, 0x0b};
    int intResult = 0;
    if (!call(core, "?execByteToInt@UObject@@QAEXAAUFFrame@@QAX@Z", code, &intResult, 2) ||
        intResult != 255) return 14;
    std::puts("PASS client byte-literal conversion equivalences used by package comparison");

    auto allocatorGlobal = reinterpret_cast<void**>(GetProcAddress(core, "?GMalloc@@3PAVFMalloc@@A"));
    if (!allocatorGlobal) {
        std::fprintf(stderr, "Client allocator export is missing\n");
        return 7;
    }
    void* allocatorVtable[] = {reinterpret_cast<void*>(allocate), reinterpret_cast<void*>(reallocate),
        reinterpret_cast<void*>(release), reinterpret_cast<void*>(allocatorNoop),
        reinterpret_cast<void*>(allocatorNoop), reinterpret_cast<void*>(allocatorNoop),
        reinterpret_cast<void*>(allocatorNoop)};
    struct { void** vtable; } allocator{allocatorVtable};
    // Before appInit the client supplies a placeholder allocator. Use the
    // harness allocator for the isolated FString tests, even if it is non-null.
    *allocatorGlobal = &allocator;
    struct String { wchar_t* data; int num, max; };
    using StringDestructor = void (__thiscall*)(void*);
    auto destroyString = reinterpret_cast<StringDestructor>(GetProcAddress(core, "??1FString@@QAE@XZ"));
    if (!destroyString) return 8;
    for (std::int64_t value : {std::int64_t(5000000000LL), INT64_MIN, INT64_MAX}) {
        char number[32];
        sprintf_s(number, "%lld", static_cast<long long>(value));
        // The VM has consumed 0x39 before entering execPrimitiveCast.
        code.assign({0x5e, 0x1f});
        for (const char* p = number;; ++p) { code.push_back(*p); if (!*p) break; }
        const size_t consumed = code.size();
        code.push_back(0x0b);
        // Payload of the expression emitted for a large source literal.
        if (!call(core, "?execPrimitiveCast@UObject@@QAEXAAUFFrame@@QAX@Z", code,
                  &result, consumed) || !equal(result, value)) return 9;
        code.clear();
        literal(code, value);
        code.push_back(0x0b);
        String text{};
        if (!call(core, "?execINT64ToString@UObject@@QAEXAAUFFrame@@QAX@Z", code, &text, 9)) return 10;
        wchar_t expected[32];
        swprintf_s(expected, L"%lld", static_cast<long long>(value));
        if (!text.data || std::wcscmp(text.data, expected) != 0) return 11;
        destroyString(&text);
        std::printf("PASS emitted literal %s and client string round-trip\n", number);
    }
    FreeLibrary(core);
    return 0;
}
