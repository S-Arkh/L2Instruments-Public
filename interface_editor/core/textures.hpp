#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include <array>

namespace interface_editor {
struct TextureImage {
    std::uint32_t width=0,height=0,format=0;
    std::vector<std::uint8_t> rgba;
    bool split=false;
    std::array<int,6> grid{};
};
TextureImage decode_texture(std::uint32_t format,std::uint32_t width,std::uint32_t height,
                            const std::vector<std::uint8_t>& pixels,const std::vector<std::uint8_t>& palette={},bool masked=false);
struct TextureAsset {
    std::string group,name;
    std::uint32_t width=0,height=0,contentWidth=0,contentHeight=0;
    std::vector<std::uint8_t> rgba;
};
std::vector<std::uint8_t> build_texture_package(const std::string& name,const std::vector<TextureAsset>& assets,
                                               const std::vector<std::uint8_t>& guid);
class TextureStore {
public:
    explicit TextureStore(const std::string& directory);
    ~TextureStore();
    TextureImage load(const std::string& reference);
    void clear();
    std::uint64_t package_reads() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
