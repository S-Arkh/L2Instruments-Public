#pragma once
#include <nlohmann/json.hpp>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace interface_editor {
using Json = nlohmann::ordered_json;
using Bytes = std::vector<std::uint8_t>;
struct Node;
struct Field {
    const Json* spec = nullptr;
    Json value;
    Bytes raw;
    std::shared_ptr<Node> child;
};
struct Node {
    std::uint64_t id = 0, parent = 0;
    std::string type, label, itemType;
    bool list = false, poly = false, compact = false;
    std::vector<std::pair<std::string, Field>> fields;
    std::vector<std::shared_ptr<Node>> items;
    Bytes prefix, tag;
    std::size_t oldCount = 0;
};
class Document {
public:
    explicit Document(const std::string& schemaJson);
    void create(const std::string& schema);
    void load(const std::string& file, const std::string& schema);
    void load_bytes(const Bytes& bytes, const std::string& schema);
    Json probe(const Bytes& bytes, const std::string& schema) const;
    Bytes serialize() const;
    void save(const std::string& file);
    std::string to_json() const;
    void from_json(const std::string& text);
    void export_json(const std::string& file) const;
    void open_json(const std::string& file);
    Json versions() const;
    Json summary() const;
    Json children(std::uint64_t id) const;
    Json info(std::uint64_t id) const;
    Json properties(std::uint64_t id, bool includeInactive = false) const;
    Json search(const std::string& query, bool neighbors = false) const;
    Json preview_snapshot(std::uint64_t id) const;
    void set(std::uint64_t id, const std::string& field, const Json& value);
    void set_many(std::uint64_t id, const Json& values);
    std::uint64_t add_configured(std::uint64_t list, const std::string& type, const Json& values);
    std::uint64_t duplicate(std::uint64_t id, std::uint64_t targetList = 0);
    std::uint64_t add(std::uint64_t list, const std::string& type);
    void remove(std::uint64_t id);
    Json allowed_types(std::uint64_t list) const;
    bool undo();
    bool redo();
private:
    Json schemas_;
    std::shared_ptr<Node> root_;
    std::unordered_map<std::uint64_t,std::shared_ptr<Node>> nodes_;
    std::unordered_map<std::uint64_t,Json> infoCache_;
    std::unordered_map<std::uint64_t,std::string> searchIndex_;
    mutable std::unordered_map<std::string,Json> operations_;
    std::string schema_, filename_;
    std::uint64_t next_ = 1, revision_ = 0;
    std::uint64_t state_ = 0, savedState_ = 0, nextState_ = 0;
    Bytes saved_;
    mutable std::recursive_mutex mutex_;
    struct Change { std::shared_ptr<Node> node; std::string field; Field before, after;
                    std::shared_ptr<Node> parent; std::size_t position = 0; int action = 0;
                    std::uint64_t beforeState = 0, afterState = 0;
                    std::vector<std::pair<std::string,Field>> beforeFields,afterFields; };
    std::vector<Change> undo_, redo_;
    std::shared_ptr<Node> get(std::uint64_t id) const;
    Field& getField(Node& node, const std::string& name) const;
    void initialize(const std::shared_ptr<Node>& node, const std::string& type, unsigned depth);
    void parseNode(const std::shared_ptr<Node>& node, const Bytes& data, std::size_t& pos, unsigned depth);
    void parseOps(const Json& ops, const std::shared_ptr<Node>& node, const Bytes& data, std::size_t& pos, unsigned depth);
    void writeNode(const std::shared_ptr<Node>& node, Bytes& out, unsigned depth) const;
    void writeOps(const Json& ops, const std::shared_ptr<Node>& node, Bytes& out, unsigned depth) const;
    void activeOps(const Json& ops, const Node& node, std::vector<std::string>& names) const;
    const Json& allOps(const std::string& type) const;
    bool condition(const Node& node, const std::string& expression) const;
    void index(const std::shared_ptr<Node>& node);
    void rebuildIndex();
    std::vector<std::shared_ptr<Node>> childNodes(const Node& node) const;
    Json nodeInfo(const Node& node) const;
    void checkName(const Node& node, const std::string& name) const;
    void validateValue(const Node& node,const std::string& name,const Json& value) const;
    void commit(Change change);
    void apply(const Change& change, bool forward);
    Json jsonNode(const std::shared_ptr<Node>& node, unsigned depth) const;
    void importNode(const Json& data, const std::shared_ptr<Node>& node, unsigned depth);
    bool compatibleType(const std::string& actual, const std::string& expected, bool polymorphic) const;
};
}
