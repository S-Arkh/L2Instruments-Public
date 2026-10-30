#pragma once
#include <cstdint>
#include <string>

namespace webframes {
bool Open();
void Hide();
void Resume();
void Close();
void Navigate(std::wstring url);
void Command(std::int32_t command);
// CSS coordinates in the fixed 512x512 viewport. kind: move, L down/up,
// R down/up, wheel up/down, double-click down; key modifiers use CDP bits.
void Mouse(std::int32_t kind, std::int32_t x, std::int32_t y, std::int32_t modifiers);
void Key(std::int32_t vk, bool down, std::int32_t modifiers, std::wstring text);
void Focus(bool active);
void Text(std::wstring text);
std::int32_t Status();
std::int32_t MutedStatus(); // -1 unavailable, otherwise queried WebView2 mute state
bool Copy(void* destination, unsigned bytes);
bool CopyFresh(void* destination, unsigned bytes); // single game-texture consumer
void ResetPerformance();
std::string Performance(); // JSON; copy timings exclude D3D upload/render
void Shutdown(); // standalone probe only: call before unloading the module
void AbandonOnProcessExit(); // only DLL_PROCESS_DETACH with non-null reserved
}
