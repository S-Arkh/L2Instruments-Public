#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include "texture_probe.h"

// Host-only layout fixture: execute real Engine::Init and revision code without
// starting the game. UObject construction/GC and Canvas still require a game test.
void* __fastcall allocate(void*, void*, unsigned size, const wchar_t*) {
    return HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, size);
}
void __fastcall release(void*, void*, void* p) { if (p) HeapFree(GetProcessHeap(), 0, p); }
void* __fastcall resize(void* self, void*, void* p, unsigned size, const wchar_t* tag) {
    if (!size) { release(self, nullptr, p); return nullptr; }
    return p ? HeapReAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, p, size) : allocate(self, nullptr, size, tag);
}
void __fastcall noop(void*, void*) {}
template<class T> T& field(void* p, unsigned offset) {
    return *reinterpret_cast<T*>(static_cast<unsigned char*>(p) + offset);
}
int wmain(int argc, wchar_t** argv) {
    if (argc != 4) return 2;
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetDllDirectoryW(argv[3]);
    HMODULE core = LoadLibraryW(argv[1]);
    if (!core) return 3;
    auto allocator = reinterpret_cast<void**>(GetProcAddress(core, "?GMalloc@@3PAVFMalloc@@A"));
    if (!allocator) return 4;
    void* methods[] = {reinterpret_cast<void*>(allocate), reinterpret_cast<void*>(resize),
        reinterpret_cast<void*>(release), reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop),
        reinterpret_cast<void*>(noop), reinterpret_cast<void*>(noop)};
    struct { void** vtable; } heap{methods};
    *allocator = &heap;
    HMODULE engine = LoadLibraryW(argv[2]);
    if (!engine) { std::printf("Engine load failed: %lu\n", GetLastError()); return 5; }
    const auto base = reinterpret_cast<std::uintptr_t>(engine);
    alignas(16) unsigned char texture[1024]{};
    alignas(16) unsigned char render[64]{};
    field<void*>(texture, 0) = GetProcAddress(engine, "??_7UTexture@@6B@");
    field<void*>(texture, 0x104) = render;
    field<void*>(render, 0) = reinterpret_cast<void*>(base + 0x5436dc);
    field<void*>(render, 0xc) = texture;
    if (!textureprobe::Frame(texture, 1)) {
        std::printf("Texture frame failed: %d\n", textureprobe::Status()); return 6;
    }
    auto mip = field<void*>(texture, 0xf4);
    if (!mip || field<int>(texture, 0xf8) != 1 || field<int>(texture, 0x5c) != 256 ||
        field<int>(texture, 0x60) != 256 || field<int>(mip, 0x20) != 256*256*4) return 7;
    auto pixels = field<std::uint32_t*>(mip, 0x1c);
    if (!pixels || pixels[1+256] != 0xffff0000 || pixels[100+256] != 0xff00ff00 || pixels[200+256] != 0xff0000ff) return 8;
    using Revision = int (__thiscall*)(void*);
    auto revision = reinterpret_cast<Revision>((*reinterpret_cast<void***>(render))[2]);
    const int first = revision(render);
    if (field<unsigned>(texture, 0xa8) & 0x80 || revision(render) != first) return 9;
    if (!textureprobe::Frame(texture, 2) || revision(render) != first+1) return 10;
    // An accidental HF layout must be rejected before calling Engine::Init.
    field<void*>(texture, 0x104) = nullptr;
    field<void*>(texture, 0x108) = render;
    if (textureprobe::Frame(texture, 3) || textureprobe::Status() != -5) return 11;
    std::puts("PASS real Gracia Engine Init: 256x256 RGBA8, mip allocation/pixels, dirty/revision, HF-layout rejection (host fixture)");
    std::fflush(stdout);
    ExitProcess(0);
}
