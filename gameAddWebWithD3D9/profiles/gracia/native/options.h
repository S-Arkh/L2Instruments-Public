#pragma once
#include <filesystem>
#include <string>

namespace browseroptions {
// Read on every open. Unknown JSON keys are reserved for future extension options.
std::wstring StartPage(const std::filesystem::path& directory);
}
