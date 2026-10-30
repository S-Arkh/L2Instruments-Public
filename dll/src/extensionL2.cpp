// YOUR EXTENSION: put C++ functions/helper classes here, then add L2_NATIVE
// entries below. build.ps1 generates the UC declarations from their C++ types.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include "extension_api.h"
#include <atomic>
#include <filesystem>
#include <climits>

namespace {
thread_local DWORD fileError = ERROR_SUCCESS;
int moduleAnchor;

struct FileHandle {
    HANDLE value;
    ~FileHandle() { if (value != INVALID_HANDLE_VALUE) CloseHandle(value); }
};

std::filesystem::path textFilePath(const std::wstring& name, const std::wstring& directory) {
    if (name.empty()) { fileError = ERROR_INVALID_NAME; return {}; }
    HMODULE module = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&moduleAnchor), &module)) {
        fileError = GetLastError(); return {};
    }
    std::wstring buffer(32768, L'\0');
    const DWORD size = GetModuleFileNameW(module, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (!size || size >= buffer.size()) {
        fileError = size ? ERROR_FILENAME_EXCED_RANGE : GetLastError(); return {};
    }
    buffer.resize(size);
    const auto base = std::filesystem::path(buffer).parent_path();
    // Empty/relative directories are relative to this DLL, never to the process CWD.
    return (base / std::filesystem::path(directory) / std::filesystem::path(name)).lexically_normal();
}

class TextFiles {
public:
    static bool Write(std::wstring name, std::wstring directory, std::wstring text) {
        fileError = ERROR_SUCCESS;
        const auto path = textFilePath(name, directory);
        if (fileError) return false;
        if (text.size() > INT_MAX) { fileError = ERROR_FILE_TOO_LARGE; return false; }
        std::string bytes;
        if (!text.empty()) {
            const int length = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(),
                static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
            if (!length) { fileError = GetLastError(); return false; }
            bytes.resize(length);
            if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(),
                static_cast<int>(text.size()), bytes.data(), length, nullptr, nullptr)) {
                fileError = GetLastError(); return false;
            }
        }
        FileHandle file{CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                                   CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr)};
        if (file.value == INVALID_HANDLE_VALUE) { fileError = GetLastError(); return false; }
        DWORD written = 0;
        if (!WriteFile(file.value, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr)) {
            fileError = GetLastError(); return false;
        }
        if (written != bytes.size()) { fileError = ERROR_WRITE_FAULT; return false; }
        if (!FlushFileBuffers(file.value)) { fileError = GetLastError(); return false; }
        return true;
    }

    static std::wstring Read(std::wstring name, std::wstring directory) {
        fileError = ERROR_SUCCESS;
        const auto path = textFilePath(name, directory);
        if (fileError) return {};
        FileHandle file{CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                                   OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr)};
        if (file.value == INVALID_HANDLE_VALUE) { fileError = GetLastError(); return {}; }
        LARGE_INTEGER size{};
        if (!GetFileSizeEx(file.value, &size)) { fileError = GetLastError(); return {}; }
        if (size.QuadPart > INT_MAX) { fileError = ERROR_FILE_TOO_LARGE; return {}; }
        std::string bytes(static_cast<std::size_t>(size.QuadPart), '\0');
        DWORD read = 0;
        if (!ReadFile(file.value, bytes.data(), static_cast<DWORD>(bytes.size()), &read, nullptr)) {
            fileError = GetLastError(); return {};
        }
        if (read != bytes.size()) { fileError = ERROR_READ_FAULT; return {}; }
        if (bytes.compare(0, 3, "\xef\xbb\xbf") == 0) bytes.erase(0, 3);
        if (bytes.empty()) return {};
        const int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(),
                                               static_cast<int>(bytes.size()), nullptr, 0);
        if (!length) { fileError = GetLastError(); return {}; }
        std::wstring text(length, L'\0');
        if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(),
            static_cast<int>(bytes.size()), text.data(), length)) {
            fileError = GetLastError(); return {};
        }
        // UE2 FString assignment uses a NUL terminator; reject binary content.
        if (text.find(L'\0') != std::wstring::npos) { fileError = ERROR_INVALID_DATA; return {}; }
        return text;
    }

    static std::int32_t Error() { return static_cast<std::int32_t>(fileError); }
};

class L2Math {
public:
    static std::int64_t SaturatingAdd64(std::int64_t a, std::int64_t b) {
        if (b > 0 && a > INT64_MAX - b) return INT64_MAX;
        if (b < 0 && a < INT64_MIN - b) return INT64_MIN;
        return a + b;
    }
    static std::int32_t ClampInt(std::int32_t value, std::int32_t minimum, std::int32_t maximum) {
        if (minimum > maximum) { const auto swap = minimum; minimum = maximum; maximum = swap; }
        return value < minimum ? minimum : value > maximum ? maximum : value;
    }
    static bool IsEven(std::int32_t value) { return value % 2 == 0; }
    static float ScaleFloat(float value, float factor) { return value * factor; }
    static std::int32_t SelectInt(bool chooseA, std::int32_t a, std::int32_t b) { return chooseA ? a : b; }
};

// This is an ordinary C++ helper class, not a new UObject class. Its state
// lives in the extension DLL; UC accesses it through the registered functions.
class L2Counter {
public:
    static void Set(std::int32_t value) { storage().store(value); }
    static std::int32_t Get() { return storage().load(); }
private:
    static std::atomic<std::int32_t>& storage() {
        static std::atomic<std::int32_t> value{0};
        return value;
    }
};
}

const l2ext::Binding* l2ext::bindings(std::size_t& count) {
    static const Binding items[] = {
        L2_NATIVE(4000, SaturatingAdd64, &L2Math::SaturatingAdd64),
        L2_NATIVE(4001, ClampInt,        &L2Math::ClampInt),
        L2_NATIVE(4002, IsEven,          &L2Math::IsEven),
        L2_NATIVE(4003, ScaleFloat,      &L2Math::ScaleFloat),
        L2_NATIVE(4004, SetCounter,      &L2Counter::Set),
        L2_NATIVE(4005, GetCounter,      &L2Counter::Get),
        L2_NATIVE(4006, SelectInt,       &L2Math::SelectInt),
        L2_NATIVE(4007, WriteTextFile,   &TextFiles::Write),
        L2_NATIVE(4008, ReadTextFile,    &TextFiles::Read),
        L2_NATIVE(4009, GetFileError,    &TextFiles::Error),
    };
    count = sizeof(items) / sizeof(items[0]);
    return items;
}
