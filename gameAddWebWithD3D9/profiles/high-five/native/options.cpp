#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <fstream>
#include <algorithm>
#include <cwctype>
#include <nlohmann/json.hpp>
#include "options.h"

std::wstring browseroptions::StartPage(const std::filesystem::path& directory) {
    const std::wstring fallback = L"https://www.youtube.com/";
    std::ifstream input(directory / L"options.config", std::ios::binary);
    if (!input) return fallback;
    // Limit total input; a future configuration can contain more than the URL.
    std::string bytes(65537, '\0');
    input.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    bytes.resize(static_cast<std::size_t>(input.gcount()));
    if (input.bad() || bytes.size() > 65536) return fallback;
    auto document = nlohmann::json::parse(bytes, nullptr, false);
    if (!document.is_object()) return fallback;
    auto browser = document.find("browser");
    if (browser == document.end() || !browser->is_object()) return fallback;
    auto page = browser->find("startPage");
    if (page == browser->end() || !page->is_string()) return fallback;
    auto url = page->get<std::string>();
    if (url.empty() || url.size() > 8192) return fallback;
    int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, url.data(), static_cast<int>(url.size()), nullptr, 0);
    if (!size) return fallback;
    std::wstring result(size, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, url.data(), static_cast<int>(url.size()), result.data(), size);
    auto first = result.find_first_not_of(L" \r\n\t"), last = result.find_last_not_of(L" \r\n\t");
    if (first == std::wstring::npos) return fallback;
    result = result.substr(first, last-first+1);
    auto prefix = result.substr(0, 8);
    std::transform(prefix.begin(), prefix.end(), prefix.begin(), towlower);
    if (!((prefix.rfind(L"https://", 0) == 0 && result.size() > 8) ||
          (prefix.rfind(L"http://", 0) == 0 && result.size() > 7))) return fallback;
    for (wchar_t c : result) if (c <= 32 || c == 127) return fallback;
    return result;
}
