#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

static_assert(sizeof(void*) == 4, "Build the launcher for Win32");
namespace fs = std::filesystem;

namespace {
struct Handle {
    HANDLE value = nullptr;
    explicit Handle(HANDLE h = nullptr) : value(h) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};

bool hashMatches(const fs::path& path, const char* expected) {
    Handle file(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                            OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (file.value == INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) return false;
    bool ok = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0;
    unsigned char block[65536], digest[32];
    DWORD count;
    while (ok) {
        if (!ReadFile(file.value, block, sizeof(block), &count, nullptr)) { ok = false; break; }
        if (!count) break;
        ok = BCryptHashData(hash, block, count, 0) >= 0;
    }
    if (ok) ok = BCryptFinishHash(hash, digest, sizeof(digest), 0) >= 0;
    if (hash) BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (!ok) return false;
    char hex[65]{};
    for (unsigned i = 0; i != 32; ++i) sprintf_s(hex + i * 2, 3, "%02x", digest[i]);
    return std::string(hex) == expected;
}

std::wstring quote(const std::wstring& arg) {
    std::wstring out = L"\"";
    size_t slashes = 0;
    for (wchar_t c : arg) {
        if (c == L'\\') { ++slashes; continue; }
        out.append(slashes * (c == L'"' ? 2 : 1), L'\\');
        slashes = 0;
        if (c == L'"') out += L'\\';
        out += c;
    }
    out.append(slashes * 2, L'\\');
    return out + L'"';
}

std::uintptr_t remoteModule(DWORD pid, const wchar_t* name) {
    for (int attempt = 0; attempt != 10; ++attempt) {
        Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid));
        if (snapshot.value == INVALID_HANDLE_VALUE) { Sleep(20); continue; }
        MODULEENTRY32W item{};
        item.dwSize = sizeof(item);
        if (Module32FirstW(snapshot.value, &item)) do {
            if (_wcsicmp(item.szModule, name) == 0)
                return reinterpret_cast<std::uintptr_t>(item.modBaseAddr);
        } while (Module32NextW(snapshot.value, &item));
        break;
    }
    // The loader list may not yet exist in a newly suspended process. Query
    // mapped images directly; ntdll itself is already mapped at this point.
    Handle process(OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid));
    if (!process.value) return 0;
    std::uintptr_t address = 0;
    MEMORY_BASIC_INFORMATION region{};
    while (VirtualQueryEx(process.value, reinterpret_cast<void*>(address), &region, sizeof(region))) {
        if (region.Type == MEM_IMAGE && region.BaseAddress == region.AllocationBase) {
            wchar_t path[32768];
            if (GetMappedFileNameW(process.value, region.AllocationBase, path, 32768) &&
                _wcsicmp(fs::path(path).filename().c_str(), name) == 0)
                return reinterpret_cast<std::uintptr_t>(region.AllocationBase);
        }
        auto next = reinterpret_cast<std::uintptr_t>(region.BaseAddress) + region.RegionSize;
        if (next <= address) break;
        address = next;
    }
    return 0;
}

bool remoteCall(HANDLE process, std::uintptr_t address, void* parameter, DWORD& result) {
    Handle thread(CreateRemoteThread(process, nullptr, 0,
        reinterpret_cast<LPTHREAD_START_ROUTINE>(address), parameter, 0, nullptr));
    if (!thread.value) { std::fprintf(stderr, "CreateRemoteThread failed: %lu\n", GetLastError()); return false; }
    const DWORD wait = WaitForSingleObject(thread.value, 30000);
    if (wait != WAIT_OBJECT_0) { std::fprintf(stderr, "Remote thread wait failed: %lu\n", wait); return false; }
    return GetExitCodeThread(thread.value, &result) != 0;
}

bool inject(const PROCESS_INFORMATION& process, const fs::path& bridge) {
    // ntdll is mapped before process initialization; KernelBase may not yet be
    // present in a CREATE_SUSPENDED process. Translate LdrLoadDll's RVA.
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    FARPROC load = GetProcAddress(ntdll, "LdrLoadDll");
    const auto remoteNtdll = remoteModule(process.dwProcessId, L"ntdll.dll");
    if (!load || !remoteNtdll) { std::fprintf(stderr, "Could not locate remote ntdll\n"); return false; }
    const auto remoteLoad = remoteNtdll + reinterpret_cast<std::uintptr_t>(load) -
                            reinterpret_cast<std::uintptr_t>(ntdll);
    const std::wstring path = bridge.wstring();
    if (path.size() > 32766) return false;
    struct LoadArgs {
        std::uint32_t function;
        std::uint16_t length, maximum;
        std::uint32_t buffer, module;
    };
    static_assert(sizeof(LoadArgs) == 16);
    const size_t size = sizeof(LoadArgs) + (path.size() + 1) * sizeof(wchar_t);
    void* memory = VirtualAllocEx(process.hProcess, nullptr, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!memory) return false;
    LoadArgs args{static_cast<std::uint32_t>(remoteLoad),
                  static_cast<std::uint16_t>(path.size() * 2),
                  static_cast<std::uint16_t>((path.size() + 1) * 2),
                  static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(memory) + sizeof(LoadArgs)), 0};
    std::vector<unsigned char> payload(size);
    std::memcpy(payload.data(), &args, sizeof(args));
    std::memcpy(payload.data() + sizeof(args), path.c_str(), size - sizeof(args));
    // DWORD __stdcall load(LoadArgs* a) { return a->function(0,0,&a->length,&a->module); }
    const unsigned char stub[] = {
        0x55, 0x8b, 0xec, 0x8b, 0x45, 0x08, 0x8d, 0x48, 0x0c, 0x51,
        0x8d, 0x48, 0x04, 0x51, 0x6a, 0x00, 0x6a, 0x00, 0xff, 0x10,
        0x5d, 0xc2, 0x04, 0x00
    };
    void* code = VirtualAllocEx(process.hProcess, nullptr, sizeof(stub), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!code) return false;
    SIZE_T written;
    DWORD previous, status = ~0u;
    const bool writeOk = WriteProcessMemory(process.hProcess, memory, payload.data(), size, &written) && written == size &&
        WriteProcessMemory(process.hProcess, code, stub, sizeof(stub), &written) && written == sizeof(stub) &&
        VirtualProtectEx(process.hProcess, code, sizeof(stub), PAGE_EXECUTE_READ, &previous) &&
        FlushInstructionCache(process.hProcess, code, sizeof(stub));
    const bool loadOk = writeOk && remoteCall(process.hProcess, reinterpret_cast<std::uintptr_t>(code), memory, status);
    // On failure the caller terminates the child, reclaiming remote allocations.
    if (!loadOk) return false;
    SIZE_T read;
    const bool readOk = ReadProcessMemory(process.hProcess, memory, &args, sizeof(args), &read) && read == sizeof(args);
    VirtualFreeEx(process.hProcess, code, 0, MEM_RELEASE);
    VirtualFreeEx(process.hProcess, memory, 0, MEM_RELEASE);
    if (!readOk || status || !args.module) {
        std::fprintf(stderr, "LdrLoadDll failed: NTSTATUS 0x%08lx\n", status);
        return false;
    }
    HMODULE local = LoadLibraryExW(bridge.c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES);
    if (!local) return false;
    auto init = GetProcAddress(local, "Ucc64Initialize");
    const auto rva = reinterpret_cast<std::uintptr_t>(init) - reinterpret_cast<std::uintptr_t>(local);
    FreeLibrary(local);
    if (!init) return false;
    status = ~0u;
    if (!remoteCall(process.hProcess, args.module + rva, nullptr, status)) return false;
    if (status) std::fprintf(stderr, "Ucc64Initialize failed: %lu\n", status);
    return status == 0;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 4 || std::wstring(argv[1]) != L"--system") {
        std::fprintf(stderr, "Usage: ucc64.exe --system <isolated System directory> make [-NoBind]\n");
        return 2;
    }
    try {
        const fs::path system = fs::canonical(argv[2]);
        struct Identity { const wchar_t* name; const char* hash; };
        const Identity identities[] = {
            {L"UCC.exe", "c68ba1ce0eab03af23b04dc1c991c3f1cc047a8a2076c6850e3071892806fb65"},
            {L"Core.dll", "5bff274734cae994353a8c60f4bfe1087dbdd9aa3883c7b2a7eff6ea2f51dc7e"},
            {L"Editor.dll", "d64995c1282956c6e9d67dd70715a69b5101331aa727a2d44b03e25fd7f2cd2e"}
        };
        for (const auto& file : identities) {
            if (!hashMatches(system / file.name, file.hash)) {
                std::fwprintf(stderr, L"Unsupported or missing compiler binary: %ls\n", file.name);
                return 3;
            }
        }
        wchar_t exe[32768];
        if (!GetModuleFileNameW(nullptr, exe, 32768)) return 4;
        const auto bridge = fs::path(exe).parent_path() / L"Ucc64Bridge.dll";
        if (!fs::exists(bridge)) { std::fprintf(stderr, "Ucc64Bridge.dll not found\n"); return 4; }
        std::wstring command = quote((system / L"UCC.exe").wstring());
        for (int i = 3; i < argc; ++i) command += L" " + quote(argv[i]);
        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        PROCESS_INFORMATION child{};
        if (!CreateProcessW((system / L"UCC.exe").c_str(), command.data(), nullptr, nullptr,
                            FALSE, CREATE_SUSPENDED, nullptr, system.c_str(), &startup, &child)) {
            std::fprintf(stderr, "CreateProcess failed: %lu\n", GetLastError()); return 5;
        }
        Handle process(child.hProcess), thread(child.hThread);
        if (!inject(child, bridge)) {
            std::fprintf(stderr, "INT64 bridge injection failed; UCC was not resumed (Win32 error %lu)\n", GetLastError());
            TerminateProcess(child.hProcess, 6);
            WaitForSingleObject(child.hProcess, 5000);
            return 6;
        }
        if (ResumeThread(child.hThread) == DWORD(-1)) { TerminateProcess(child.hProcess, 7); return 7; }
        if (WaitForSingleObject(child.hProcess, INFINITE) != WAIT_OBJECT_0) return 8;
        DWORD result;
        if (!GetExitCodeProcess(child.hProcess, &result)) return 8;
        return static_cast<int>(result);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 9;
    }
}
