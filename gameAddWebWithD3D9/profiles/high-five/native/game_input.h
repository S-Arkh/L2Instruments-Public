#pragma once
#include <cstdint>
namespace gameinput {
bool Mouse(std::int32_t kind, std::int32_t left, std::int32_t top,
           std::int32_t width, std::int32_t height, std::int32_t modifiers);
void Key(std::int32_t key, bool down, std::int32_t modifiers);
bool LeftPressed();
std::int32_t Poll(bool active, bool hover, std::int32_t left, std::int32_t top,
                  std::int32_t width, std::int32_t height);
}
