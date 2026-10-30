#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>

namespace ucc64 {
enum class ParseResult { NotInteger, Valid, Overflow };

// Parse signed decimal/hexadecimal source literals without using a 32-bit CRT
// conversion. Full-token validation is required before reporting overflow.
template<class Char>
ParseResult parseInteger(const Char* text, std::int64_t& result) {
    if (!text || !*text) return ParseResult::NotInteger;
    bool negative = false;
    if (*text == '-' || *text == '+') negative = *text++ == '-';
    unsigned base = 10;
    if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) {
        base = 16;
        text += 2;
    }
    if (!*text) return ParseResult::NotInteger;
    const std::uint64_t limit = negative ? (std::uint64_t(1) << 63)
                                        : std::uint64_t(INT64_MAX);
    std::uint64_t value = 0;
    bool overflow = false;
    for (; *text; ++text) {
        const auto c = *text;
        const unsigned digit = c >= '0' && c <= '9' ? unsigned(c - '0') :
            c >= 'a' && c <= 'f' ? unsigned(c - 'a' + 10) :
            c >= 'A' && c <= 'F' ? unsigned(c - 'A' + 10) : 255;
        if (digit >= base) return ParseResult::NotInteger;
        if (value > (limit - digit) / base) overflow = true;
        if (!overflow) value = value * base + digit;
    }
    if (overflow) return ParseResult::Overflow;
    result = negative ? (value == (std::uint64_t(1) << 63) ? INT64_MIN : -std::int64_t(value))
                      : std::int64_t(value);
    return ParseResult::Valid;
}

struct ClientInt64 { std::uint32_t high, low; };
static_assert(sizeof(ClientInt64) == 8);
inline ClientInt64 split(std::int64_t value) {
    const auto bits = static_cast<std::uint64_t>(value);
    return {std::uint32_t(bits >> 32), std::uint32_t(bits)};
}

constexpr int NoConversion = 0xff;
constexpr int AutoConversion = 0x100;
// Existing UE2 property categories. INT64 remains CPT_Struct (10) with the
// identity Core.Object.INT64; it is NOT every structure of size eight.
constexpr int Byte = 1, Int = 2, Bool = 3, Float = 4, Struct = 10, String = 13;

inline int conversion(int dest, bool dest64, int source, bool source64) {
    if (dest64 && !source64) {
        switch (source) {
        case Byte: return 0x5a | AutoConversion;
        case Int: return 0x5b | AutoConversion;
        case Bool: return 0x5c;
        case Float: return 0x5d;
        case String: return 0x5e;
        }
    }
    if (source64 && !dest64) {
        switch (dest) {
        case Byte: return 0x5f;
        case Int: return 0x60;
        case Bool: return 0x61;
        case Float: return 0x62 | AutoConversion | 0x200; // lossy: original cost rank 104
        case String: return 0x63;
        }
    }
    return NoConversion;
}
}
