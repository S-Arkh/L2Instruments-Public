#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <cstdint>
#include <cstring>
#include <vector>
#include "texture_probe.h"
#ifdef BROWSER_TEXTURE
#include "web_frames.h"
#endif

namespace {
#ifdef BROWSER_TEXTURE
constexpr int Side = 512;
#else
constexpr int Side = 256;
#endif
constexpr int Bytes = Side * Side * 4;
using Init = void (__thiscall*)(void*, int, int);
Init initialize;
void* textureVtable;
void* interfaceVtable;
DWORD ownerThread;
int status;

template<class T> T& field(void* p, unsigned offset) {
    return *reinterpret_cast<T*>(static_cast<unsigned char*>(p) + offset);
}

bool engineHash(HMODULE engine) {
    wchar_t path[32768];
    DWORD length = GetModuleFileNameW(engine, path, 32768);
    if (!length || length >= 32768) return false;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                              nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    unsigned char digest[32]{};
    const unsigned char expected[32] = {
        0x94,0x46,0x05,0xe8,0x67,0xb1,0x79,0x25,0x33,0x6d,0xc1,0x27,0xdd,0x03,0xa6,0x07,
        0x6f,0x7b,0x5f,0xfc,0xc1,0x98,0x8a,0xb4,0xa0,0x77,0xa8,0x5c,0x09,0x90,0x44,0x17};
    bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0;
    if (ok) ok = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0;
    unsigned char buffer[65536];
    while (ok) {
        DWORD read = 0;
        if (!ReadFile(file, buffer, sizeof(buffer), &read, nullptr)) { ok = false; break; }
        if (!read) break;
        ok = BCryptHashData(hash, buffer, read, 0) >= 0;
    }
    if (ok) ok = BCryptFinishHash(hash, digest, sizeof(digest), 0) >= 0;
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    CloseHandle(file);
    return ok && std::memcmp(digest, expected, sizeof(digest)) == 0;
}

bool resolve() {
    HMODULE engine = GetModuleHandleW(L"Engine.dll");
    if (!engine || !engineHash(engine)) { status = -1; return false; }
    auto base = reinterpret_cast<std::uintptr_t>(engine);
    auto init = GetProcAddress(engine, "?Init@UTexture@@UAEXHH@Z");
    auto table = GetProcAddress(engine, "??_7UTexture@@6B@");
    if (reinterpret_cast<std::uintptr_t>(init) != base + 0x1c4510 ||
        reinterpret_cast<std::uintptr_t>(table) != base + 0x4e358c) {
        status = -2; return false;
    }
    initialize = reinterpret_cast<Init>(init);
    textureVtable = reinterpret_cast<void*>(table);
    interfaceVtable = reinterpret_cast<void*>(base + 0x581904);
    ownerThread = GetCurrentThreadId();
    return true;
}
}

bool textureprobe::Frame(void* texture, std::int32_t phase) {
    static_assert(sizeof(void*) == 4, "HF x86 only");
    if (!texture) { status = -4; return false; }
    if (!initialize && !resolve()) return false;
    if (ownerThread != GetCurrentThreadId()) { status = -3; return false; }
    if (field<void*>(texture, 0) != textureVtable) { status = -4; return false; }
    void* render = field<void*>(texture, 0x108);
    if (!render || field<void*>(render, 0) != interfaceVtable ||
        field<void*>(render, 0xc) != texture) { status = -5; return false; }

    // UC creates and owns this transient Texture. Only initialize an empty one;
    // never resize or overwrite an existing asset passed by accident.
    if (field<int>(texture, 0xfc) == 0) {
        if (field<int>(texture, 0x5c) || field<int>(texture, 0x60)) { status = -6; return false; }
        field<unsigned char>(texture, 0x54) = 5; // HF TEXF_RGBA8: 4 bytes/pixel
        initialize(texture, Side, Side); // engine allocates and owns mip storage
    }
    if (field<unsigned char>(texture, 0x54) != 5 || field<int>(texture, 0x5c) != Side ||
        field<int>(texture, 0x60) != Side || field<int>(texture, 0xfc) != 1) {
        status = -7; return false;
    }
    void* mip = field<void*>(texture, 0xf8);
    if (!mip || field<int>(mip, 0x20) != Bytes || field<int>(mip, 0x24) < Bytes) {
        status = -8; return false;
    }
    auto pixels = field<std::uint32_t*>(mip, 0x1c);
    if (!pixels) { status = -9; return false; }
#ifdef BROWSER_TEXTURE
    (void)phase;
    if (webframes::CopyFresh(pixels, Bytes)) {
        field<std::uint32_t>(texture, 0xa8) |= 0x80;
        status = 1;
    } else {
        status = webframes::Status() < 0 ? webframes::Status() : 2;
    }
    return status >= 0;
#else
    const unsigned frame = static_cast<unsigned>(phase);
    for (unsigned y = 0; y < Side; ++y) {
        for (unsigned x = 0; x < Side; ++x) {
            const bool checker = (((x + frame * 4) / 32) ^ (y / 32)) & 1;
            std::uint32_t color = checker ? 0xffe0a020 : 0xff204080;
            if (y < 24) color = x < 85 ? 0xffff0000 : x < 170 ? 0xff00ff00 : 0xff0000ff;
            if (x == 0 || y == 0 || x == Side-1 || y == Side-1) color = 0xffffffff;
            pixels[y * Side + x] = color; // opaque BGRA bytes on x86
        }
    }
    field<std::uint32_t>(texture, 0xa8) |= 0x80; // dirty -> render-interface revision
    status = 1;
    return true;
#endif
}

std::int32_t textureprobe::Status() { return status; }
