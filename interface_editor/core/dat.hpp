#pragma once
#include "document.hpp"
#include <map>

namespace interface_editor {
struct DatDecoded {
    Bytes payload, compressedSuffix;
    int version=0;
    std::string profile;
    bool footer=false;
};
Json dat_codecs();
Json sysstring_schemas();
void register_dat_profile(const Json& profile);
DatDecoded decode_dat(const Bytes& bytes,const std::string& filename,const std::string& profile="auto");
Bytes encode_dat(const Bytes& payload,const std::string& filename,int version,const std::string& profile,
                 bool footer=true,const Bytes& compressedSuffix={});

class SysStrings {
public:
    void load(const std::string& file,const std::string& schema="id-ascf-v1",const std::string& encoding="cp1252",const std::string& profile="auto");
    void load_bytes(const Bytes& data,const std::string& filename,const std::string& schema,const std::string& encoding,const std::string& profile);
    Json summary() const;
    Json rows() const;
    Json snapshot() const;
    Json lookup(std::uint32_t id) const;
    std::uint32_t next_id() const;
    void add(std::uint32_t id,const std::string& text);
    void set(std::uint32_t id,const std::string& text);
    bool undo();
    bool redo();
    Bytes payload() const;
    Bytes encoded(const std::string& filename,int version=-1,const std::string& profile="preserve") const;
    void save(const std::string& file,int version=-1,const std::string& profile="preserve");
private:
    struct Row { std::uint32_t id=0;std::string text;Bytes raw; };
    struct Change {std::size_t index;bool added;Row before,after;std::uint64_t beforeState,afterState;};
    std::vector<Row> rows_;
    std::map<std::uint32_t,std::size_t> index_;
    Bytes tail_, original_, packedSuffix_;
    std::string file_,schema_="id-ascf-v1",encoding_="cp1252",profile_;
    int version_=0;
    bool footer_=false,ambiguousPadding_=false,loaded_=false;
    std::uint64_t revision_=0,state_=0,savedState_=0,nextState_=0;
    std::vector<Change> undo_,redo_;
    mutable std::recursive_mutex mutex_;
    void parse(const DatDecoded& decoded,const std::string& encoding);
    void reindex();
    void apply(const Change& c,bool forward);
};
}
