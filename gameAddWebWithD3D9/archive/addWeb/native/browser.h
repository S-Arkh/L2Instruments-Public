#pragma once
#include <cstdint>
#include <string>
namespace addweb {
bool Show();
void Hide();
void Bounds(std::int32_t x, std::int32_t y, std::int32_t width, std::int32_t height);
void Navigate(std::wstring url);
void Command(std::int32_t command);
std::int32_t Status();
#ifdef ADDWEB_PROBE
std::wstring ProbeConfig();
#endif
}
