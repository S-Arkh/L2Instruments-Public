#pragma once
#include <nlohmann/json.hpp>
#include <cstdint>
#include <filesystem>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace ue {
using Json = nlohmann::ordered_json;
using Bytes = std::vector<uint8_t>;
std::string lower(std::string s);
std::string leaf(const std::string& s);
std::string hex(const Bytes& b);
std::string utf8(uint32_t c);
struct Reader {
    const Bytes& data; size_t pos, end;
    explicit Reader(const Bytes& b, size_t offset=0, size_t length=SIZE_MAX);
    void require(size_t n) const;
    uint8_t byte(); uint16_t u16(); uint32_t u32(); uint64_t u64();
    int32_t i32(); float f32(); int32_t index();
    void skip(size_t n); std::string string();
};
struct Entry {
    std::string name, importClass, classPackage;
    int outer=0, cls=0, super=0; uint32_t flags=0;
    size_t offset=0, size=0;
};
struct Node {
    int op=0, pc=0, finish=0, target=-1, ref=0, index=0;
    std::string kind, text; Json value;
    std::vector<Node> children;
};
struct Function {
    int id=0, fields[4]{}, native=0, precedence=0, size=0;
    uint32_t flags=0; std::string friendly;
    std::vector<Node> nodes;
};
struct Property {
    int id=0, next=0, dim=0, ref=0, meta=0;
    uint32_t flags=0; std::string kind, category;
};
struct StructInfo {
    int fields[4]{}, size=0, labelOffset=0;
    uint32_t stateFlags=0, classFlags=0;
    uint64_t probe=0, ignore=0;
    std::string friendly;
    std::vector<Node> nodes;
    size_t tail=0;
};
class Package {
public:
    std::filesystem::path path;
    Bytes data;
    std::string envelope="plain";
    int version=0, licensee=0;
    std::vector<std::string> names;
    std::vector<Entry> imports, exports;
    mutable std::map<int,std::string> paths;
    std::map<int,std::vector<int>> children;
    explicit Package(const std::filesystem::path& file);
    const Entry& entry(int id) const;
    std::string name(int id) const;
    std::string ref(int id) const;
    std::string kind(int id) const;
    int find(const std::string& path) const;
    Reader reader(int id) const;
    Function function(int id) const;
    StructInfo structure(int id, bool isClass=false, bool isState=false) const;
    Property property(int id) const;
    std::vector<std::string> enumeration(int id) const;
    std::string constant(int id) const;
    Json scriptText(int id) const;
    Json summary() const;
    const std::vector<int>& members(int id) const;
};
struct Decoder {
    const Package& p; Reader& r; int pc=0; size_t count=0;
    Node expression(int depth=0);
    std::vector<Node> script(int size);
    int reference(bool isName=false);
    int byte(); int word(); int integer();
};
Json nodeJson(const Node& n);
struct Symbol { const Package* p=nullptr; int id=0; explicit operator bool() const { return p && id; } };
class Context {
public:
    std::shared_ptr<Package> main;
    std::vector<std::shared_ptr<Package>> packages;
    std::map<int,std::pair<Symbol,Function>> natives;
    std::set<int> conflicts;
    Json diagnostics=Json::array();
    Context(const std::filesystem::path& file,const std::vector<std::filesystem::path>& dirs);
    Symbol resolve(const Package& from,int id) const;
    Json decompile(int classId,bool force=false) const;
};
Json request(const Json& input);
}
