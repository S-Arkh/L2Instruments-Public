#pragma once
#include "client_abi.h"
#include <array>
#include <tuple>
#include <type_traits>
#include <utility>
#include <string>

namespace l2ext {
constexpr unsigned MaxArguments = 8;
enum class Type : std::uint32_t { Void, Byte, Int, Bool, Float, Int64, String };
struct BindingInfo {
    std::uint32_t index;
    const char* name;
    Type result;
    std::uint32_t argumentCount;
    Type arguments[MaxArguments];
};
static_assert(sizeof(BindingInfo) == 48);
struct Binding { BindingInfo info; l2client::Native handler; };

// Runtime adapter services. They are initialized by ExtensionL2Attach.
void readArgument(l2client::FramePrefix* frame, void* output);
void finishArguments(void* self, l2client::FramePrefix* frame);
[[noreturn]] void functionFailed();
std::wstring readString(l2client::FramePrefix* frame);
void writeString(void* result, const std::wstring& value);

template<class> constexpr bool UnsupportedType = false;
template<class T> struct Value {
    static_assert(UnsupportedType<T>, "Unsupported native type. Use int32_t, int64_t, uint8_t, bool, float, std::wstring or void return.");
};
template<class T, Type Kind> struct Scalar {
    static constexpr Type type = Kind;
    static T read(l2client::FramePrefix* frame) {
        T value{};
        readArgument(frame, &value);
        return value;
    }
    static void write(void* result, T value) {
        if (result) std::memcpy(result, &value, sizeof(value));
    }
};
template<> struct Value<std::int32_t> : Scalar<std::int32_t, Type::Int> {};
template<> struct Value<std::uint8_t> : Scalar<std::uint8_t, Type::Byte> {};
template<> struct Value<float> : Scalar<float, Type::Float> {};
template<> struct Value<void> { static constexpr Type type = Type::Void; };
template<> struct Value<std::wstring> {
    static constexpr Type type = Type::String;
    static std::wstring read(l2client::FramePrefix* frame) { return readString(frame); }
    static void write(void* result, const std::wstring& value) { writeString(result, value); }
};
template<> struct Value<bool> {
    static constexpr Type type = Type::Bool;
    static bool read(l2client::FramePrefix* frame) {
        std::int32_t value = 0; // Unreal BOOL is four bytes, not sizeof(C++ bool).
        readArgument(frame, &value);
        return value != 0;
    }
    static void write(void* result, bool value) {
        Value<std::int32_t>::write(result, value ? 1 : 0);
    }
};
template<> struct Value<std::int64_t> {
    static constexpr Type type = Type::Int64;
    static std::int64_t read(l2client::FramePrefix* frame) {
        l2client::Int64Value value{};
        readArgument(frame, &value);
        return l2client::unpack(value);
    }
    static void write(void* result, std::int64_t value) {
        const auto words = l2client::pack(value);
        if (result) std::memcpy(result, &words, sizeof(words));
    }
};

template<auto Function, class Signature = decltype(Function)> struct Adapter;
template<auto Function, class Result, class... Args>
struct Adapter<Function, Result (*)(Args...)> {
    static_assert(sizeof...(Args) <= MaxArguments, "Too many native arguments");
    static_assert((std::is_same_v<Args, std::decay_t<Args>> && ...), "References/out parameters need a dedicated ABI adapter");
    static constexpr std::array<Type, sizeof...(Args)> argumentTypes{Value<Args>::type...};

    template<std::size_t... I>
    static void read(std::tuple<Args...>& values, l2client::FramePrefix* frame, std::index_sequence<I...>) {
        (void)values;
        (void)frame;
        // Comma fold guarantees UC arguments are evaluated LEFT TO RIGHT.
        ((std::get<I>(values) = Value<Args>::read(frame)), ...);
    }
    static void __fastcall execute(void* self, void*, l2client::FramePrefix* frame, void* result) {
        std::tuple<Args...> values{};
        read(values, frame, std::index_sequence_for<Args...>{});
        finishArguments(self, frame);
        bool failed = false;
        if constexpr (std::is_void_v<Result>) {
            try { std::apply(Function, values); } catch (...) { failed = true; }
        } else {
            Result value{};
            try { value = std::apply(Function, values); } catch (...) { failed = true; }
            if (!failed) Value<Result>::write(result, value);
        }
        // Convert C++ exceptions after leaving the catch block. The engine's
        // own exception must not be caught again by this adapter.
        if (failed) functionFailed();
    }
    static Binding make(unsigned index, const char* name) {
        Binding binding{{index, name, Value<Result>::type, sizeof...(Args), {}},
                        reinterpret_cast<l2client::Native>(execute)};
        for (std::size_t i = 0; i < argumentTypes.size(); ++i)
            binding.info.arguments[i] = argumentTypes[i];
        return binding;
    }
};

template<auto Function>
Binding bind(unsigned index, const char* name) { return Adapter<Function>::make(index, name); }

// Implemented in extensionL2.cpp. This list is the source of truth for BOTH
// runtime registration and generation of ExtensionL2API.uc.
const Binding* bindings(std::size_t& count);
}

#define L2_NATIVE(Index, ScriptName, Function) ::l2ext::bind<Function>(Index, #ScriptName)
