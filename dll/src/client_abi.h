#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace l2client {
// Only the verified prefix of FFrame is accessed. Do not treat this as an SDK
// declaration of the entire engine class, or instantiate it inside the game.
struct FramePrefix {
    void* vtable;
    void* node;
    void* object;
    unsigned char* code;
    void* locals;
};
struct Int64Value { std::uint32_t high, low; };
// FString owns a Core-allocated UTF-16 TArray. Never free it with the DLL CRT.
struct StringValue { wchar_t* data; std::int32_t count, capacity; };
static_assert(sizeof(StringValue) == 12 && sizeof(wchar_t) == 2);
static_assert(sizeof(void*) == 4, "Use Win32/x86");
static_assert(offsetof(FramePrefix, code) == 12);
static_assert(offsetof(FramePrefix, object) == 8);
static_assert(sizeof(Int64Value) == 8);

using Native = void (__thiscall*)(void* self, FramePrefix*, void* result);
using Step = void (__thiscall*)(FramePrefix*, void* object, void* result);
// The MSVC single-inheritance UObject member-pointer is a four-byte code
// address in this client. GRegisterNative takes a reference to that pointer.
using RegisterNative = unsigned char (__cdecl*)(int, Native const*);
using ThrowError = void (__cdecl*)(const wchar_t*, ...);
using StringDestroy = void (__thiscall*)(StringValue*);
using StringAssign = StringValue* (__thiscall*)(StringValue*, const wchar_t*);

inline std::int64_t unpack(Int64Value value) {
    std::uint64_t bits = (std::uint64_t(value.high) << 32) | value.low;
    std::int64_t result;
    std::memcpy(&result, &bits, sizeof(result));
    return result;
}
inline Int64Value pack(std::int64_t value) {
    const auto bits = static_cast<std::uint64_t>(value);
    return {std::uint32_t(bits >> 32), std::uint32_t(bits)};
}
}
