#pragma once
#ifdef _WIN32
#ifdef UEX_BUILD
#define UEX_API __declspec(dllexport)
#else
#define UEX_API __declspec(dllimport)
#endif
#else
#define UEX_API __attribute__((visibility("default")))
#endif
extern "C" {
// UTF-8 JSON input/output; returned memory belongs to the DLL.
UEX_API char* ue_request(const char* input) noexcept;
UEX_API void ue_free(char* output) noexcept;
UEX_API int ue_abi_version() noexcept;
}
