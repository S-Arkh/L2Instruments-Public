#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <cstdio>
#include "options.h"

int main() {
    auto root = std::filesystem::temp_directory_path() / (L"l2-options-test-" + std::to_wstring(GetCurrentProcessId()));
    if (!std::filesystem::create_directory(root)) return 2;
    const auto file = root / "options.config";
    const std::wstring fallback = L"https://www.youtube.com/";
    bool ok = browseroptions::StartPage(root) == fallback;
    auto check = [&](const std::string& json, const std::wstring& expected) {
        { std::ofstream output(file, std::ios::binary); output << json; }
        bool passed = browseroptions::StartPage(root) == expected;
        ok = ok && passed;
        if (!passed) std::puts("FAIL options case");
    };
    check(R"({"browser":{"startPage":"https://example.org/one"},"future":{"enabled":true}})", L"https://example.org/one");
    check(R"({"browser":{"startPage":"http://example.org/two?a=1&b=2"}})", L"http://example.org/two?a=1&b=2");
    check(R"({"browser":{"startPage":"https:\/\/example.org/\u0430"}})", L"https://example.org/\u0430");
    check("\xef\xbb\xbf{\"browser\":{\"startPage\":\"https://example.org/\"}}", L"https://example.org/");
    for (const auto* invalid : {"", "{", "[]", "{}", "{\"browser\":null}",
        "{\"browser\":{\"startPage\":123}}", "{\"browser\":{\"startPage\":\"javascript:alert(1)\"}}",
        "{\"browser\":{\"startPage\":\"https://example.org/\\u0000\"}}",
        "{\"browser\":{\"startPage\":\"https://example.org/a b\"}}",
        "{\"browser\":{\"startPage\":\"https://example.org/\"}} trailing"}) check(invalid, fallback);
    check(std::string(65537, ' '), fallback);
    std::filesystem::remove(file);
    { std::ofstream legacy(root / "startWeb.config"); legacy << "https://legacy.example/"; }
    ok = ok && browseroptions::StartPage(root) == fallback;
    std::filesystem::remove_all(root);
    std::puts(ok ? "PASS JSON options: reload, UTF-8/escapes/BOM, future keys, fallback, legacy ignored" : "FAIL JSON options");
    return ok ? 0 : 1;
}
