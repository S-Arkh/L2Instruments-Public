#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>

// Loader-level regression for the Clear_hf Core/Engine mismatch. No l2.exe,
// network login or UnrealScript package is executed by this host.
int wmain(int argc, wchar_t** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "Usage: client_link_probe.exe <Core.dll> <Engine.dll> <dependencies directory>\n");
        return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetDllDirectoryW(argv[3]);
    HMODULE core = LoadLibraryW(argv[1]);
    if (!core) { std::fprintf(stderr, "Core.dll load failed: %lu\n", GetLastError()); return 3; }
    HMODULE engine = LoadLibraryW(argv[2]);
    if (!engine) { std::fprintf(stderr, "Engine.dll load failed: %lu\n", GetLastError()); return 5; }
    std::puts("PASS target Engine.dll loads with selected Core.dll");
    FreeLibrary(engine);
    FreeLibrary(core);
    return 0;
}
