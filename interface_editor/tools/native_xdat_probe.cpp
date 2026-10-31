// Private x86 research host: invoke a verified native constructor/serializer RVA.
// Arguments and client artifacts stay local. No client file is ever written.
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static_assert(sizeof(void*) == 4, "Build this research host with the x86 MSVC toolchain");

static std::vector<unsigned char> input;
static size_t cursor = 0, calls = 0;
static void* __fastcall allocate(void*, void*, unsigned count, const wchar_t*) { return std::malloc(count); }
static void* __fastcall reallocate(void*, void*, void* old, unsigned count, const wchar_t*) { return std::realloc(old, count); }
static void __fastcall release(void*, void*, void* block) { std::free(block); }
static void __fastcall noop(void*, void*) {}

static void finish(unsigned code) {
    std::printf("cursor=%zu bytes=%zu calls=%zu result=%u\n", cursor, input.size(), calls, code);
    std::fflush(stdout);
    TerminateProcess(GetCurrentProcess(), code);
}

static void __fastcall read_bytes(void*, void*, void* destination, int count) {
    ++calls;
    if (count < 0 || static_cast<size_t>(count) > input.size() - cursor) finish(10);
    if (count) std::memcpy(destination, input.data() + cursor, count);
    cursor += count;
}

static int __fastcall tell(void*, void*) { return static_cast<int>(cursor); }
static int __fastcall size(void*, void*) { return static_cast<int>(input.size()); }
static void __fastcall seek(void*, void*, int position) {
    if (position < 0 || static_cast<size_t>(position) > input.size()) finish(11);
    cursor = position;
}
static LONG WINAPI crash(EXCEPTION_POINTERS* info) {
    std::printf("exception=%08lx\n", info->ExceptionRecord->ExceptionCode);
    MEMORY_BASIC_INFORMATION region{};
    if (VirtualQuery(info->ExceptionRecord->ExceptionAddress, &region, sizeof(region)))
        std::printf("exception_rva=%zx\n", reinterpret_cast<size_t>(info->ExceptionRecord->ExceptionAddress) - reinterpret_cast<size_t>(region.AllocationBase));
    finish(12);
    return EXCEPTION_EXECUTE_HANDLER;
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 6) {
        std::fputs("Usage: native_xdat_probe <working-copy-NWindow> <sample> <ctor-RVA> <serializer-RVA> <stack-ctor:0|1>\n", stderr);
        return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
    SetUnhandledExceptionFilter(crash);
    FILE* file = nullptr;
    if (_wfopen_s(&file, argv[2], L"rb") || !file) return 3;
    std::fseek(file, 0, SEEK_END);
    long length = std::ftell(file);
    if (length < 0 || length > 256 * 1024 * 1024) { std::fclose(file); return 3; }
    std::rewind(file);
    input.resize(length);
    auto count = std::fread(input.data(), 1, input.size(), file);
    std::fclose(file);
    if (count != input.size()) return 3;
    auto module = LoadLibraryExW(argv[1], nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    auto core = GetModuleHandleW(L"Core.dll");
    if (!module || !core) finish(4);
    // The minimal loader does not run appInit. Supply its allocator dependency.
    auto allocator_global = GetProcAddress(core, "?GMalloc@@3PAVFMalloc@@A");
    if (!allocator_global) finish(7);
    void* allocator_table[] = {reinterpret_cast<void*>(allocate), reinterpret_cast<void*>(reallocate),
                              reinterpret_cast<void*>(release), reinterpret_cast<void*>(noop),
                              reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop)};
    void** allocator = allocator_table;
    *reinterpret_cast<void**>(allocator_global) = &allocator;
    auto archive_ctor = GetProcAddress(core, "??0FArchive@@QAE@XZ");
    if (!archive_ctor) finish(5);
    std::puts("archive_ctor_start"); std::fflush(stdout);
    alignas(16) unsigned char archive[4096] = {};
    reinterpret_cast<void(__thiscall*)(void*)>(archive_ctor)(archive);
    // FArchive vtable offsets verified for the investigated 32-bit clients.
    void* table[24];
    std::memcpy(table, *reinterpret_cast<void***>(archive), sizeof(table));
    table[1] = reinterpret_cast<void*>(read_bytes);
    table[0x28 / 4] = reinterpret_cast<void*>(tell);
    table[0x2c / 4] = reinterpret_cast<void*>(size);
    table[0x3c / 4] = reinterpret_cast<void*>(seek);
    *reinterpret_cast<void***>(archive) = table;
    *reinterpret_cast<int*>(archive + 0x10) = 1; // loading
    *reinterpret_cast<int*>(archive + 0x14) = 0; // saving
    *reinterpret_cast<int*>(archive + 0x1c) = 1; // persistent
    auto object = VirtualAlloc(nullptr, 65536, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!object) finish(6);
    auto base = reinterpret_cast<unsigned char*>(module);
    auto ctor = base + std::wcstoul(argv[3], nullptr, 0);
    auto serializer = base + std::wcstoul(argv[4], nullptr, 0);
    std::puts("manager_ctor_start"); std::fflush(stdout);
    if (std::wcstoul(argv[5], nullptr, 0))
        reinterpret_cast<void(__stdcall*)(void*)>(ctor)(object);
    else reinterpret_cast<void(__thiscall*)(void*)>(ctor)(object);
    std::puts("native_serialize_start"); std::fflush(stdout);
    reinterpret_cast<void(__thiscall*)(void*, void*)>(serializer)(object, archive);
    finish(0); // Avoid client detach/global teardown in this minimal host.
    return 0;
}
