#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <string>

static_assert(sizeof(void*) == 4);
int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    SetDllDirectoryW(argv[1]);
    const std::wstring directory = argv[1];
    HMODULE core = LoadLibraryW((directory + L"\\Core.dll").c_str());
    HMODULE engine = LoadLibraryW((directory + L"\\Engine.dll").c_str());
    if (!core || !engine) { std::printf("DLL load error %lu\n", GetLastError()); return 3; }
    using Size = int (__thiscall*)(void*);
    auto size = reinterpret_cast<Size>(GetProcAddress(core, "?GetPropertiesSize@UStruct@@UAEHXZ"));
    if (!size) return 4;
    for (const char* name : {"UObject", "USubsystem", "UMaterial", "UBitmapMaterial", "UTexture", "AActor"}) {
        std::string symbol = std::string("?PrivateStaticClass@") + name + "@@0VUClass@@A";
        void* cls = reinterpret_cast<void*>(GetProcAddress(core, symbol.c_str()));
        if (!cls) cls = reinterpret_cast<void*>(GetProcAddress(engine, symbol.c_str()));
        if (cls) std::printf("%s native PropertiesSize = %d\n", name, size(cls));
    }
    // Native class registries remain referenced until process exit.
    return 0;
}
