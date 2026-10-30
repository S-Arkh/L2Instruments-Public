#include "int64_semantics.h"
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace ucc64;
void check(bool condition, const char* context) {
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", context); std::exit(1); }
}
int main() {
    const std::int64_t values[] = {0, 1, -1, 2147483647, -2147483648LL,
        2147483648LL, -2147483649LL, 5000000000LL, INT64_MIN, INT64_MAX};
    for (auto value : values) {
        const auto text = std::to_string(value);
        std::int64_t parsed = 123;
        check(parseInteger(text.c_str(), parsed) == ParseResult::Valid && parsed == value, text.c_str());
        const auto words = split(parsed);
        check(((std::uint64_t(words.high) << 32) | words.low) == static_cast<std::uint64_t>(value), "word order");
        std::wstring wide(text.begin(), text.end());
        check(parseInteger(wide.c_str(), parsed) == ParseResult::Valid && parsed == value, "wide literal");
    }
    for (const char* bad : {"9223372036854775808", "-9223372036854775809", "0x8000000000000000",
                            "9999999999999999999999999999999999999999999999"}) {
        std::int64_t value = 7;
        check(parseInteger(bad, value) == ParseResult::Overflow && value == 7, bad);
    }
    for (const char* bad : {"", "+", "-", "0x", "1.5", "12e4", "0xGG", "999999999999999999999.0"}) {
        std::int64_t value = 7;
        check(parseInteger(bad, value) == ParseResult::NotInteger && value == 7, bad);
    }
    std::int64_t value;
    check(parseInteger("-0x8000000000000000", value) == ParseResult::Valid && value == INT64_MIN, "hex minimum");
    check(parseInteger("0xFFFFFFFF", value) == ParseResult::Valid && value == 4294967295LL, "legacy mask");
    check(conversion(Struct, true, Int, false) == 0x15b, "implicit int widening");
    check(conversion(Struct, true, String, false) == 0x5e, "explicit string conversion");
    check(conversion(String, false, Struct, true) == 0x63, "string formatting");
    check(conversion(Int, false, Struct, true) == 0x60, "explicit narrowing only");
    check(conversion(Float, false, Struct, true) == 0x362, "lossy numeric promotion to float");
    check(conversion(Struct, false, Int, false) == NoConversion, "unrelated struct");
    check(conversion(Struct, true, Struct, false) == NoConversion, "no struct reinterpretation");
    check(conversion(Struct, true, Struct, true) == NoConversion, "identity handled by original type checker");
    check(split(5000000000LL).high == 1 && split(5000000000LL).low == 705032704, "client 5e9 layout");
    std::puts("INT64 semantics tests passed");
}
