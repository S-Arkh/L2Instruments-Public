#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <vector>
#include "client_abi.h"
#include "client_profile.h"
#include "extension_api.h"

using Attach = BOOL (WINAPI*)(HMODULE);
using Query = DWORD (WINAPI*)();
using GetBinding = BOOL (WINAPI*)(DWORD, l2ext::BindingInfo*, DWORD);
long liveAllocations = 0;

// Standalone host only: Core normally receives a real allocator from the game.
void* __fastcall allocate(void*, void*, unsigned size, const wchar_t*) {
    auto p = HeapAlloc(GetProcessHeap(), 0, size);
    if (p) ++liveAllocations;
    return p;
}
void __fastcall release(void*, void*, void* p) {
    if (p) { HeapFree(GetProcessHeap(), 0, p); --liveAllocations; }
}
void* __fastcall resize(void* self, void*, void* p, unsigned size, const wchar_t* tag) {
    if (!size) { release(self, nullptr, p); return nullptr; }
    return p ? HeapReAlloc(GetProcessHeap(), 0, p, size) : allocate(self, nullptr, size, tag);
}
void __fastcall noop(void*, void*) {}

void word(std::vector<unsigned char>& code, std::uint32_t value) {
    for (unsigned i = 0; i != 4; ++i) code.push_back(static_cast<unsigned char>(value >> (i * 8)));
}
void constant(std::vector<unsigned char>& code, std::int64_t value) {
    auto pair = l2client::pack(value);
    code.push_back(0x46);
    word(code, pair.high);
    word(code, pair.low);
}
void callOpcode(std::vector<unsigned char>& code, int index = l2client::NativeIndex) {
    code.push_back(static_cast<unsigned char>(0x60 + (index >> 8)));
    code.push_back(static_cast<unsigned char>(index));
}

void integer(std::vector<unsigned char>& code, std::int32_t value) {
    code.push_back(0x1d);
    word(code, static_cast<std::uint32_t>(value));
}
void floating(std::vector<unsigned char>& code, float value) {
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    code.push_back(0x1e);
    word(code, bits);
}
void textConstant(std::vector<unsigned char>& code, const std::wstring& text) {
    code.push_back(0x34); // EX_UnicodeStringConst, UTF-16LE including terminator
    for (auto ch : text) { code.push_back(static_cast<unsigned char>(ch)); code.push_back(static_cast<unsigned char>(ch >> 8)); }
    code.push_back(0); code.push_back(0);
}

std::vector<unsigned char> fileCall(int index, const std::wstring& name, const std::wstring& path) {
    std::vector<unsigned char> code;
    callOpcode(code, index); textConstant(code, name); textConstant(code, path);
    return code;
}

bool evaluateScalar(l2client::Step step, std::vector<unsigned char> code, std::uint32_t expected, const char* label, bool isVoid = false);

bool fileTests(l2client::Step step, HMODULE core, const std::filesystem::path& dll) {
    namespace fs = std::filesystem;
    const auto oldCwd = fs::current_path();
    const auto root = fs::absolute(dll).parent_path();
    const auto name = L"extension-file-probe-" + std::to_wstring(GetCurrentProcessId()) + L".txt";
    const auto other = root / (L"extension-file-dir-" + std::to_wstring(GetCurrentProcessId()));
    if (!fs::create_directory(other)) return false;
    struct Cleanup {
        fs::path cwd, file, directory;
        ~Cleanup() { std::error_code error; fs::current_path(cwd, error); fs::remove(file, error); fs::remove_all(directory, error); }
    } cleanup{oldCwd, root / name, other};
    fs::current_path(other); // deliberately NOT the DLL directory
    const auto baseline = liveAllocations;
    const std::wstring text = L"Credit \u041f\u0440\u0438\u0432\u0435\u0442 \u4e16\u754c\r\nsecond line";
    auto write = [&](const std::wstring& path, const std::wstring& value, bool expected, const char* label) {
        auto code = fileCall(4007, name, path); textConstant(code, value); code.push_back(0x16);
        return evaluateScalar(step, code, expected ? 1 : 0, label);
    };
    auto error = [&](DWORD expected) {
        std::vector<unsigned char> code; callOpcode(code, 4009); code.push_back(0x16);
        return evaluateScalar(step, code, expected, "file error code");
    };
    auto destroy = reinterpret_cast<l2client::StringDestroy>(GetProcAddress(core, "??1FString@@QAE@XZ"));
    auto assign = reinterpret_cast<l2client::StringAssign>(GetProcAddress(core, "??4FString@@QAEAAV0@PB_W@Z"));
    if (!destroy || !assign) return false;
    auto read = [&](const std::wstring& path, const std::wstring& expected) {
        auto code = fileCall(4008, name, path); code.push_back(0x16);
        const auto length = code.size(); code.push_back(0x0b);
        struct { l2client::FramePrefix prefix{}; unsigned char spare[128]{}; } frame;
        frame.prefix.code = code.data();
        l2client::StringValue result{};
        assign(&result, L"old result must be released");
        step(&frame.prefix, nullptr, &result);
        const bool ok = frame.prefix.code == code.data() + length &&
            std::wstring(result.data ? result.data : L"") == expected;
        destroy(&result);
        return ok;
    };
    if (!write(L"", text, true, "UTF-16 string arguments -> UTF-8 file beside DLL") || !error(0)) return false;
    if (!fs::exists(root / name) || fs::exists(other / name) || !read(L"", text) || !error(0)) return false;
    { // Verify actual disk bytes, not just a symmetric encode/decode roundtrip.
        std::ifstream input(root / name, std::ios::binary);
        const std::string bytes((std::istreambuf_iterator<char>(input)), {});
        if (bytes != "Credit \xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82 \xe4\xb8\x96\xe7\x95\x8c\r\nsecond line") return false;
    }
    if (!write(other.wstring(), L"explicit directory", true, "absolute directory") || !read(other.wstring(), L"explicit directory")) return false;
    if (!write(other.filename().wstring(), L"relative directory", true, "relative directory is relative to DLL") || !read(other.wstring(), L"relative directory")) return false;
    // Nested string-returning native used as another native's string argument.
    auto nested = fileCall(4007, name, L"");
    auto source = fileCall(4008, name, other.wstring());
    nested.insert(nested.end(), source.begin(), source.end()); nested.push_back(0x16); nested.push_back(0x16);
    if (!evaluateScalar(step, nested, 1, "nested FString return -> FString argument") || !read(L"", L"relative directory")) return false;
    if (!write(L"", L"", true, "truncate to empty file") || fs::file_size(root / name) != 0 || !read(L"", L"") || !error(0)) return false;
    fs::remove(root / name);
    if (!read(L"", L"") || !error(ERROR_FILE_NOT_FOUND)) return false;
    if (!write((other / "missing").wstring(), L"x", false, "missing directory returns false") || !error(ERROR_PATH_NOT_FOUND)) return false;
    {
        std::ofstream file(root / name, std::ios::binary); file << "\xef\xbb\xbfUTF-8 BOM";
    }
    if (!read(L"", L"UTF-8 BOM") || !error(0)) return false;
    {
        std::ofstream file(root / name, std::ios::binary); file.put(static_cast<char>(0xff));
    }
    if (!read(L"", L"") || !error(ERROR_NO_UNICODE_TRANSLATION)) return false;
    if (liveAllocations != baseline) { std::fprintf(stderr, "FString allocation leak\n"); return false; }
    std::puts("PASS text files: paths, UTF-8, overwrite, empty/missing/invalid files, FString ownership");
    return true;
}
bool evaluateScalar(l2client::Step step, std::vector<unsigned char> code, std::uint32_t expected, const char* label, bool isVoid) {
    const auto length = code.size();
    code.push_back(0x0b);
    struct { l2client::FramePrefix prefix{}; unsigned char spare[128]{}; } frame;
    frame.prefix.code = code.data();
    std::uint32_t result = 0xdeadbeef;
    step(&frame.prefix, nullptr, isVoid ? nullptr : &result);
    if (frame.prefix.code != code.data() + length || (!isVoid && result != expected)) {
        std::fprintf(stderr, "FAIL %s: result=%u\n", label, result);
        return false;
    }
    std::printf("PASS %s\n", label);
    return true;
}

bool evaluate(l2client::Step step, std::vector<unsigned char> code, std::int64_t expected, const char* label) {
    const auto length = code.size();
    code.push_back(0x0b); // next instruction, as in an actual function
    struct { l2client::FramePrefix prefix{}; unsigned char spare[128]{}; } frame;
    frame.prefix.code = code.data();
    l2client::Int64Value result{};
    step(&frame.prefix, nullptr, &result); // VM dispatch, NOT a direct call to the DLL handler
    if (frame.prefix.code != code.data() + length || l2client::unpack(result) != expected) {
        std::fprintf(stderr, "FAIL %s: value=%lld, consumed=%u expected=%u\n", label,
            static_cast<long long>(l2client::unpack(result)),
            unsigned(frame.prefix.code - code.data()), unsigned(length));
        return false;
    }
    std::printf("PASS %s: %lld\n", label, static_cast<long long>(expected));
    return true;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 5) {
        std::fprintf(stderr, "Usage: extension_probe.exe <Core.dll> <dependencies dir> <ExtensionL2.dll> <manual|patched> [compiled-call.bin] [compiled-write.bin]\n");
        return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetDllDirectoryW(argv[2]);
    HMODULE core = LoadLibraryW(argv[1]);
    if (!core) { std::fprintf(stderr, "Core load failed: %lu\n", GetLastError()); return 3; }
    auto table = reinterpret_cast<l2client::Native*>(GetProcAddress(core, l2client::TableExport));
    auto undefined = reinterpret_cast<l2client::Native>(GetProcAddress(core, l2client::UndefinedExport));
    auto step = reinterpret_cast<l2client::Step>(GetProcAddress(core, l2client::StepExport));
    if (!table || !undefined || !step) return 4;
    const bool manual = std::wcscmp(argv[4], L"manual") == 0;
    if (!manual && std::wcscmp(argv[4], L"patched") != 0) return 2;
    if (manual ? table[l2client::NativeIndex] != undefined : table[l2client::NativeIndex] == undefined) {
        std::fprintf(stderr, "Unexpected registration state for selected mode\n"); return 5;
    }
    HMODULE module = LoadLibraryW(argv[3]);
    if (!module) { std::fprintf(stderr, "ExtensionL2 load failed: %lu\n", GetLastError()); return 6; }
    auto attach = reinterpret_cast<Attach>(GetProcAddress(module, "ExtensionL2Attach"));
    auto index = reinterpret_cast<Query>(GetProcAddress(module, "ExtensionL2Index"));
    auto status = reinterpret_cast<Query>(GetProcAddress(module, "ExtensionL2LastStatus"));
    auto count = reinterpret_cast<Query>(GetProcAddress(module, "ExtensionL2Count"));
    auto describe = reinterpret_cast<GetBinding>(GetProcAddress(module, "ExtensionL2GetBinding"));
    if (!attach || !index || !status || !count || !describe || index() != l2client::NativeIndex || count() < 10) return 7;
    std::vector<l2ext::BindingInfo> bindings(count());
    for (DWORD i = 0; i < count(); ++i) {
        if (!describe(i, &bindings[i], sizeof(bindings[i]))) return 7;
    }
    if (manual) {
        // Simulate a different module owning the index. The installer must not overwrite it.
        auto occupied = reinterpret_cast<l2client::Native>(GetProcAddress(core, "?execIntZero@UObject@@QAEXAAUFFrame@@QAX@Z"));
        table[l2client::NativeIndex] = occupied;
        if (attach(core) || status() != ERROR_ALREADY_EXISTS || table[l2client::NativeIndex] != occupied) return 8;
        table[l2client::NativeIndex] = undefined;
        std::puts("PASS occupied native index is not overwritten");
        const auto last = bindings.back().index;
        table[last] = occupied;
        if (attach(core)) return 8;
        for (const auto& item : bindings) {
            if (table[item.index] != (item.index == last ? occupied : undefined)) return 8;
        }
        table[last] = undefined;
        std::puts("PASS whole-list preflight: no partial registration");
    } else {
        std::puts("PASS patched Core registered the new function automatically");
    }
    if (!attach(core) || !attach(core) || status() != ERROR_SUCCESS) return 9;
    for (const auto& item : bindings) if (table[item.index] == undefined) return 9;
    std::puts("PASS installation is idempotent");
    auto allocator = reinterpret_cast<void**>(GetProcAddress(core, "?GMalloc@@3PAVFMalloc@@A"));
    if (!allocator) return 10;
    void* vtable[] = {reinterpret_cast<void*>(allocate), reinterpret_cast<void*>(resize),
        reinterpret_cast<void*>(release), reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop),
        reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop)};
    struct { void** vtable; } heap{vtable};
    *allocator = &heap;
    struct Case { std::int64_t a, b, expected; };
    const Case cases[] = {
        {5000000000LL, 10, 5000000010LL}, {-5000000000LL, -10, -5000000010LL},
        {INT64_MAX, 1, INT64_MAX}, {INT64_MIN, -1, INT64_MIN},
        {INT64_MAX, INT64_MIN, -1}, {0, 0, 0}, {INT64_MIN, INT64_MAX, -1}
    };
    for (const auto& item : cases) {
        std::vector<unsigned char> code;
        callOpcode(code);
        constant(code, item.a);
        constant(code, item.b);
        code.push_back(0x16);
        if (!evaluate(step, code, item.expected, "VM SaturatingAdd64")) return 11;
    }
    std::vector<unsigned char> nested;
    callOpcode(nested);
    callOpcode(nested);
    constant(nested, INT64_MAX);
    constant(nested, 1);
    nested.push_back(0x16);
    constant(nested, -1);
    nested.push_back(0x16);
    if (!evaluate(step, nested, INT64_MAX - 1, "nested native expressions")) return 12;
    std::vector<unsigned char> scalar;
    callOpcode(scalar, 4001);
    integer(scalar, 100); integer(scalar, 10); integer(scalar, 20); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 20, "int parameters and result")) return 15;
    scalar.clear(); callOpcode(scalar, 4002); integer(scalar, -4); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 1, "BOOL result uses four bytes")) return 16;
    scalar.clear(); callOpcode(scalar, 4003); floating(scalar, 1.5f); floating(scalar, 2.0f); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0x40400000, "float parameters and result")) return 17;
    scalar.clear(); callOpcode(scalar, 4004); integer(scalar, 123456); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0, "void method on C++ helper class", true)) return 18;
    scalar.clear(); callOpcode(scalar, 4005); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 123456, "zero-argument method and C++ class state")) return 19;
    scalar.clear(); callOpcode(scalar, 4006); scalar.push_back(0x28); integer(scalar, 12); integer(scalar, 34); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 34, "BOOL parameter and left-to-right argument order")) return 20;
    if (!fileTests(step, core, argv[3])) return 21;
    scalar.clear(); callOpcode(scalar, 4015); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0, "WebStatus through actual Core VM")) return 24;
    scalar.clear(); callOpcode(scalar, 4012);
    integer(scalar, 25); integer(scalar, 65); integer(scalar, 880); integer(scalar, 530); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0, "WebBounds four-argument native bridge", true)) return 25;
    scalar.clear(); callOpcode(scalar, 4011); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0, "WebHide native bridge", true)) return 26;
    if (argc >= 6) {
        std::ifstream input(std::filesystem::path(argv[5]), std::ios::binary);
        if (!input) return 13;
        std::vector<unsigned char> compiled((std::istreambuf_iterator<char>(input)), {});
        if (!evaluate(step, compiled, 2147483648LL, "actual UCC-generated ExampleCall")) return 14;
    }
    if (argc >= 7) {
        const auto target = std::filesystem::absolute(argv[3]).parent_path() / "test.txt";
        if (std::filesystem::exists(target)) { std::fprintf(stderr, "Refusing to overwrite existing test.txt in probe\n"); return 22; }
        std::ifstream input(std::filesystem::path(argv[6]), std::ios::binary);
        if (!input) return 22;
        std::vector<unsigned char> compiled((std::istreambuf_iterator<char>(input)), {});
        if (!evaluateScalar(step, compiled, 1, "actual UCC-generated Credit WriteTextFile")) return 22;
        std::ifstream file(target, std::ios::binary);
        const std::string text((std::istreambuf_iterator<char>(file)), {});
        file.close();
        std::filesystem::remove(target);
        if (text != "Credit button clicked.") return 22;
        std::puts("PASS Credit bytecode writes expected test.txt beside DLL");
    }
    // VM tests are finished; no UObject/UFunction cache remains in this host.
    FreeLibrary(core);
    FreeLibrary(module);
    return 0;
}
