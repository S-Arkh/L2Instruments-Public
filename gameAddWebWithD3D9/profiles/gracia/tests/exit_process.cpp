#include <windows.h>
#include <cstdio>
int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    HMODULE dll = LoadLibraryW(argv[1]);
    if (!dll) return 3;
    auto start = reinterpret_cast<bool(*)()>(GetProcAddress(dll, "ExitFixtureStart"));
    auto ready = reinterpret_cast<bool(*)()>(GetProcAddress(dll, "ExitFixtureReady"));
    if (!start || !ready || !start()) return 4;
    for (int i=0; i<600 && !ready(); ++i) Sleep(50);
    if (!ready()) { std::puts("FAIL fixture initialization"); return 5; }
    std::puts("READY_FOR_EXIT: active WebView2 and WGC in DLL; calling ExitProcess");
    std::fflush(stdout);
    // Deliberately omit graceful shutdown: test real process detach ordering.
    ExitProcess(0);
}
