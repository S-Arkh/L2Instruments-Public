#include "document.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <codecvt>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <limits>
#include <locale>
#include <regex>
#include <set>
#include <stdexcept>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace interface_editor {
namespace {
constexpr std::size_t MaxFile = 256 * 1024 * 1024, MaxNodes = 1000000;
std::filesystem::path path(const std::string& s) { return std::filesystem::u8path(s); }
std::string lower(std::string s) { for (char& c:s) if (c>='A'&&c<='Z') c+=32; return s; }
void require(bool value, const std::string& text) { if (!value) throw std::runtime_error(text); }
std::uint32_t u32(const Bytes& b, std::size_t& p) {
    require(p<=b.size() && b.size()-p>=4,"Unexpected EOF at offset " + std::to_string(p));
    std::uint32_t v=0; for(unsigned i=0;i<4;++i) v|=std::uint32_t(b[p++])<<(i*8); return v;
}
void put32(Bytes& b, std::uint32_t v) { for(unsigned i=0;i<4;++i) b.push_back(static_cast<std::uint8_t>(v>>(i*8))); }
std::int32_t compact(const Bytes& b, std::size_t& p) {
    require(p<b.size(),"Compact integer EOF"); auto first=b[p++];
    std::uint32_t value=first&63; unsigned shift=6; bool more=first&64;
    for(unsigned i=1;more && i<5;++i) {
        require(p<b.size(),"Compact integer EOF"); auto c=b[p++];
        value|=std::uint32_t(c&(i==4?31:127))<<shift; shift+=7; more=i<4 && (c&128);
    }
    require(value<=0x7fffffff,"Compact integer overflow");
    return first&128 ? -static_cast<std::int32_t>(value) : static_cast<std::int32_t>(value);
}
void putCompact(Bytes& b, std::int32_t v) {
    auto n=static_cast<std::uint32_t>(v<0?-std::int64_t(v):v);
    auto first=static_cast<std::uint8_t>((n&63)|(v<0?128:0)); n>>=6;
    b.push_back(first|(n?64:0)); while(n) {auto c=n&127;n>>=7;b.push_back(static_cast<std::uint8_t>(c|(n?128:0)));}
}
std::string readString(const Bytes& b,std::size_t& p) {
    auto n=compact(b,p); std::size_t bytes=static_cast<std::size_t>(n<0?-std::int64_t(n)*2:n);
    require(bytes<=MaxFile && p<=b.size() && bytes<=b.size()-p,"String length exceeds input at "+std::to_string(p));
    if(!n)return {};
    std::string result;
    if(n>0) {
        require(b[p+bytes-1]==0,"Missing string terminator");
        // Preserve bytes >=128 through a reversible Latin-1 display mapping.
        for(std::size_t i=0;i+1<bytes;++i) {auto c=b[p+i];if(c<128)result.push_back(char(c));else{result.push_back(char(0xc0|(c>>6)));result.push_back(char(0x80|(c&63)));}}
    } else {
        require(bytes>=2 && b[p+bytes-1]==0 && b[p+bytes-2]==0,"Missing UTF-16 terminator");
        std::u16string text;for(std::size_t i=0;i+2<bytes;i+=2)text.push_back(char16_t(b[p+i]|(b[p+i+1]<<8)));
        result=std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.to_bytes(text);
    }
    p+=bytes;return result;
}
void putString(Bytes& b,const std::string& text) {
    require(text.find('\0')==std::string::npos,"Embedded NUL is not a valid string");
    if(text.empty()){putCompact(b,0);return;}
    if(std::all_of(text.begin(),text.end(),[](unsigned char c){return c<128;})) {
        putCompact(b,static_cast<std::int32_t>(text.size()+1));b.insert(b.end(),text.begin(),text.end());b.push_back(0);
    } else {
        auto t=std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.from_bytes(text);
        putCompact(b,-static_cast<std::int32_t>(t.size()+1));for(auto c:t){b.push_back(c&255);b.push_back(c>>8);}b.push_back(0);b.push_back(0);
    }
}
Bytes readFile(const std::string& filename) {
    std::ifstream f(path(filename),std::ios::binary|std::ios::ate);require(bool(f),"Cannot open: "+filename);
    auto size=f.tellg(); require(size>=0 && static_cast<std::uint64_t>(size)<=MaxFile,"File too large");
    Bytes data(static_cast<std::size_t>(size));f.seekg(0);f.read(reinterpret_cast<char*>(data.data()),size);require(bool(f),"Cannot read: "+filename);return data;
}
void writeFile(const std::filesystem::path& filename,const Bytes& data) {
    std::ofstream f(filename,std::ios::binary|std::ios::trunc);require(bool(f),"Cannot create output");
    f.write(reinterpret_cast<const char*>(data.data()),static_cast<std::streamsize>(data.size()));f.flush();require(bool(f),"Cannot write output");f.close();require(bool(f),"Cannot close output");
}
void replaceFile(const std::filesystem::path& source,const std::filesystem::path& destination) {
#ifdef _WIN32
    if(!MoveFileExW(source.c_str(),destination.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)) {
        const auto error=GetLastError();
        throw std::runtime_error("Cannot replace " + destination.u8string() + " (Win32 error " + std::to_string(error) + ")");
    }
#else
    std::filesystem::rename(source,destination);
#endif
}
void copyBackup(const std::filesystem::path& source,const std::filesystem::path& destination) {
#ifdef _WIN32
    // The destination is a unique staging file. Avoid MinGW std::filesystem's
    // overwrite_existing path, which failed for an existing .bak on Windows.
    if(!CopyFileW(source.c_str(),destination.c_str(),TRUE)) {
        const auto error=GetLastError();
        throw std::runtime_error("Cannot stage backup of " + source.u8string() + " (Win32 error " + std::to_string(error) + ")");
    }
#else
    std::filesystem::copy_file(source,destination);
#endif
}
std::string hex(const Bytes& bytes) {
    static const char digits[]="0123456789abcdef";
    std::string result;result.reserve(bytes.size()*2);
    for(auto b:bytes){result.push_back(digits[b>>4]);result.push_back(digits[b&15]);}
    return result;
}
Bytes unhex(const Json& value) {
    require(value.is_string(),"Expected a hexadecimal string");
    const auto& text=value.get_ref<const std::string&>();
    require(text.size()%2==0 && text.size()/2<=MaxFile,"Invalid hexadecimal size");
    auto digit=[](char c)->unsigned {if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;throw std::runtime_error("Invalid hexadecimal digit");};
    Bytes out;out.reserve(text.size()/2);
    for(std::size_t i=0;i<text.size();i+=2)out.push_back(static_cast<std::uint8_t>((digit(text[i])<<4)|digit(text[i+1])));
    return out;
}
Json readScalar(const std::string& kind,const Bytes& raw) {
    std::size_t pos=0;Json value;
    if(kind=="string")value=readString(raw,pos);
    else if(kind=="compact")value=compact(raw,pos);
    else {auto bits=u32(raw,pos);if(kind=="float"){float v;std::memcpy(&v,&bits,4);value=double(v);}else if(kind=="color"||kind=="rgba")value=bits;else value=static_cast<std::int32_t>(bits);}
    require(pos==raw.size(),"Extra bytes in raw scalar");return value;
}
bool sameScalar(const Json& a,const Json& b,const std::string& kind) {
    if(kind=="float" && a.is_number() && b.is_number()){
        auto av=a.get<double>(),bv=b.get<double>();
        if(std::isnan(av)&&std::isnan(bv))return true;
        if(av==0 && bv==0)return std::signbit(av)==std::signbit(bv);
    }
    return a==b;
}
Json jsonScalar(const Json& value) {
    if(value.is_number_float()){
        auto v=value.get<double>();
        if(!std::isfinite(v))return std::isnan(v)?Json("NaN"):Json(v<0?"-Infinity":"Infinity");
    }
    return value;
}
Json checkedScalar(const Json& value,const std::string& kind) {
    if(kind=="string"){
        require(value.is_string(),"Expected string value");
        require(value.get_ref<const std::string&>().find('\0')==std::string::npos,"Embedded NUL");return value;
    }
    if(kind=="float"){
        if(value.is_string()){
            auto s=value.get<std::string>();
            if(s=="NaN")return std::numeric_limits<double>::quiet_NaN();
            if(s=="Infinity")return std::numeric_limits<double>::infinity();
            if(s=="-Infinity")return -std::numeric_limits<double>::infinity();
        }
        require(value.is_number()&&std::isfinite(value.get<double>())&&std::abs(value.get<double>())<=std::numeric_limits<float>::max(),"Expected float32 value");return value;
    }
    require(value.is_number_integer(),"Expected integer value");
    if(value.is_number_unsigned())require(value.get<std::uint64_t>()<=UINT32_MAX,"Integer overflow");
    auto v=value.get<std::int64_t>();
    auto minimum=(kind=="color"||kind=="rgba")?std::int64_t(0):(kind=="compact"?-std::int64_t(INT32_MAX):std::int64_t(INT32_MIN));
    auto maximum=(kind=="color"||kind=="rgba")?std::int64_t(UINT32_MAX):std::int64_t(INT32_MAX);
    require(v>=minimum&&v<=maximum,"Integer out of range");return value;
}
}

Document::Document(const std::string& schemaJson):schemas_(Json::parse(schemaJson)) {
    require(schemas_.at("format")==1,"Unsupported schema format");
}
Json Document::versions() const {return schemas_.at("versions");}
const Json& Document::allOps(const std::string& type) const {
    auto cached=operations_.find(type);
    if(cached!=operations_.end())return cached->second;
    const auto& s=schemas_.at("records").at(type);Json ops=Json::array();
    if(!s.at("base").is_null())ops=allOps(s.at("base").get<std::string>());
    for(const auto& o:s.at("ops"))ops.push_back(o);
    return operations_.emplace(type,std::move(ops)).first->second;
}
Field& Document::getField(Node& node,const std::string& name) const {
    for(auto& f:node.fields)if(f.first==name)return f.second;
    throw std::runtime_error(node.type+": unknown field "+name);
}
void Document::initialize(const std::shared_ptr<Node>& n,const std::string& type,unsigned depth) {
    require(depth<128 && next_<MaxNodes,"Object depth/count limit exceeded");
    n->id=next_++;n->type=type;
    // Field specs point into immutable schema JSON, never the temporary flattened ops.
    std::function<void(const Json&)> initOps=[&, depth](const Json& ops){for(const auto& op:ops){
        auto kind=op.at("op").get<std::string>();
        if(kind=="if"){initOps(op.at("yes"));initOps(op.at("no"));continue;}
        if(kind=="tail") {Field f;f.spec=&op;f.value=nullptr;n->fields.emplace_back("_tail",std::move(f));continue;}
        auto name=op.at("name").get<std::string>();
        if(std::any_of(n->fields.begin(),n->fields.end(),[&](auto& x){return x.first==name;}))continue;
        Field f;f.spec=&op;f.value=op.at("default");
        auto k=op.at("kind").get<std::string>();
        if(k=="list"){
            f.child=std::make_shared<Node>();auto& c=*f.child;c.id=next_++;c.parent=n->id;c.type="$list";c.list=true;c.label=name;
            c.itemType=op.at("type").get<std::string>();c.poly=op.value("poly",false);c.compact=op.value("count","")=="compact";
        } else if(k=="object" && !op.value("poly",false)) {
            f.child=std::make_shared<Node>();f.child->parent=n->id;initialize(f.child,op.at("type").get<std::string>(),depth+1);f.child->label=name;
        }
        n->fields.emplace_back(name,std::move(f));
    }};
    std::function<void(const std::string&)> initType=[&](const std::string& t){
        const auto& s=schemas_.at("records").at(t);if(!s.at("base").is_null())initType(s.at("base").get<std::string>());initOps(s.at("ops"));};
    initType(type);
}
bool Document::condition(const Node& n,const std::string& expression) const {
    static const std::regex re(R"(^\s*(!?)(\w+)\s*(?:(==|!=|>=|<=|>|<)\s*(-?\d+))?\s*$)");
    std::smatch m;require(std::regex_match(expression,m,re),"Unsupported condition: "+expression);
    auto& v=getField(const_cast<Node&>(n),m[2]).value;auto value=v.is_boolean()?std::int64_t(v.get<bool>()):(v.is_number()?v.get<std::int64_t>():0);
    bool result=value==1; // Nullable boolean: only 1 is true, not -1.
    if(m[3].matched){auto rhs=std::stoll(m[4]);auto op=m[3].str();result=op==">"?value>rhs:op=="<"?value<rhs:op==">="?value>=rhs:op=="<="?value<=rhs:op=="=="?value==rhs:value!=rhs;}
    if(m[1]=="!")result=!result;
    return result;
}
void Document::parseNode(const std::shared_ptr<Node>& n,const Bytes& data,std::size_t& p,unsigned depth) {
    require(depth<128,"Tree too deep");parseOps(allOps(n->type),n,data,p,depth);
}
void Document::parseOps(const Json& ops,const std::shared_ptr<Node>& n,const Bytes& b,std::size_t& p,unsigned depth) {
    for(const auto& op:ops){
        if(op.at("op")=="if"){parseOps(op.at(condition(*n,op.at("condition"))?"yes":"no"),n,b,p,depth);continue;}
        if(op.at("op")=="tail"){getField(*n,"_tail").raw=Bytes(b.begin()+p,b.end());p=b.size();continue;}
        const std::string name=op.at("name"),kind=op.at("kind");auto& f=getField(*n,name);auto start=p;
        try {
            if(kind=="list") {
                auto list=f.child;auto count=list->compact?compact(b,p):static_cast<std::int32_t>(u32(b,p));
                require(count>=0 && static_cast<std::size_t>(count)<=MaxNodes && static_cast<std::size_t>(count)<=b.size()-p,"Invalid list count");
                list->prefix=Bytes(b.begin()+start,b.begin()+p);list->oldCount=count;
                for(int i=0;i<count;++i){
                    auto item=std::make_shared<Node>();item->parent=list->id;auto tagStart=p;
                    auto type=list->poly?n->type.substr(0,n->type.find('.'))+'.'+readString(b,p):list->itemType;
                    require(schemas_["records"].contains(type),"Unknown control type "+type);
                    initialize(item,type,depth+1);item->tag=Bytes(b.begin()+tagStart,b.begin()+p);parseNode(item,b,p,depth+1);list->items.push_back(item);
                }
            } else if(kind=="object") {
                if(op.value("poly",false)){auto type=n->type.substr(0,n->type.find('.'))+'.'+readString(b,p);f.child=std::make_shared<Node>();f.child->parent=n->id;initialize(f.child,type,depth+1);f.child->tag=Bytes(b.begin()+start,b.begin()+p);}
                parseNode(f.child,b,p,depth+1);
            } else {
                if(kind=="string")f.value=readString(b,p);
                else if(kind=="compact")f.value=compact(b,p);
                else {auto raw=u32(b,p);if(kind=="float"){float v;std::memcpy(&v,&raw,4);f.value=static_cast<double>(v);}else if(kind=="color"||kind=="rgba")f.value=raw;else f.value=static_cast<std::int32_t>(raw);}
                f.raw=Bytes(b.begin()+start,b.begin()+p);
            }
        } catch(const std::exception& e){throw std::runtime_error(n->type+'.'+name+" @"+std::to_string(start)+": "+e.what());}
    }
}
void Document::writeNode(const std::shared_ptr<Node>& n,Bytes& out,unsigned depth) const {
    require(depth<128,"Tree too deep");writeOps(allOps(n->type),n,out,depth);
}
void Document::writeOps(const Json& ops,const std::shared_ptr<Node>& n,Bytes& out,unsigned depth) const {
    for(const auto& op:ops){
        if(op.at("op")=="if"){writeOps(op.at(condition(*n,op.at("condition"))?"yes":"no"),n,out,depth);continue;}
        auto& f=getField(*n,op.at("op")=="tail"?"_tail":op.at("name").get<std::string>());
        if(op.at("op")=="tail"){out.insert(out.end(),f.raw.begin(),f.raw.end());continue;}
        std::string kind=op.at("kind");
        if(kind=="list"){
            const auto& list=*f.child;
            if(list.oldCount==list.items.size()&&!list.prefix.empty())out.insert(out.end(),list.prefix.begin(),list.prefix.end());
            else if(list.compact)putCompact(out,static_cast<std::int32_t>(list.items.size()));else put32(out,static_cast<std::uint32_t>(list.items.size()));
            for(const auto& item:list.items){if(list.poly){if(!item->tag.empty())out.insert(out.end(),item->tag.begin(),item->tag.end());else putString(out,item->type.substr(item->type.find('.')+1));}writeNode(item,out,depth+1);}
        } else if(kind=="object") {
            require(bool(f.child),"Uninitialized object field");if(op.value("poly",false)){if(!f.child->tag.empty())out.insert(out.end(),f.child->tag.begin(),f.child->tag.end());else putString(out,f.child->type.substr(f.child->type.find('.')+1));}writeNode(f.child,out,depth+1);
        } else if(!f.raw.empty())out.insert(out.end(),f.raw.begin(),f.raw.end());
        else if(kind=="string")putString(out,f.value.get<std::string>());
        else if(kind=="compact")putCompact(out,f.value.get<std::int32_t>());
        else if(kind=="float"){float value=f.value.get<float>();std::uint32_t raw;std::memcpy(&raw,&value,4);put32(out,raw);}
        else put32(out,static_cast<std::uint32_t>(f.value.get<std::int64_t>()));
        require(out.size()<=MaxFile,"Output too large");
    }
}
void Document::create(const std::string& schema){
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    require(schemas_["records"].contains(schema),"Unknown schema");
    Document staged(schemas_.dump());staged.root_=std::make_shared<Node>();
    staged.initialize(staged.root_,schema,0);
    load_bytes(staged.serialize(),schema);
    state_=++nextState_;
}
Json Document::probe(const Bytes& bytes,const std::string& schema) const {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    Json result={{"schema",schema},{"compatible",false},{"tail_bytes",0}};
    try {
        Document candidate(schemas_.dump());candidate.load_bytes(bytes,schema);
        require(candidate.serialize()==bytes,"Binary roundtrip mismatch");
        std::size_t tail=0;
        for(const auto& entry:candidate.nodes_)
            for(const auto& field:entry.second->fields)
                if(field.second.spec && field.second.spec->value("op","")=="tail")tail+=field.second.raw.size();
        result["compatible"]=true;result["tail_bytes"]=tail;
    } catch(const std::exception& e) {result["error"]=e.what();}
    return result;
}
void Document::load(const std::string& file,const std::string& schema){auto data=readFile(file);load_bytes(data,schema);std::lock_guard<std::recursive_mutex> lock(mutex_);filename_=file;}
void Document::load_bytes(const Bytes& bytes,const std::string& schema){
    std::lock_guard<std::recursive_mutex> lock(mutex_);require(bytes.size()<=MaxFile,"File too large");
    require(schemas_["records"].contains(schema),"Unknown schema");
    Document staged(schemas_.dump());staged.schema_=schema;staged.root_=std::make_shared<Node>();staged.initialize(staged.root_,schema,0);
    std::size_t p=0;staged.parseNode(staged.root_,bytes,p,0);
    require(p==bytes.size(),"Unparsed bytes at offset "+std::to_string(p)+"; wrong schema or unsupported extension");
    // Nodes' spec pointers refer to staged.schemas_: transfer schema storage too.
    schemas_.swap(staged.schemas_);operations_.clear();root_=staged.root_;schema_=schema;next_=staged.next_;saved_=bytes;filename_.clear();undo_.clear();redo_.clear();state_=savedState_=nextState_=0;++revision_;rebuildIndex();
}
Bytes Document::serialize() const {std::lock_guard<std::recursive_mutex> lock(mutex_);require(bool(root_),"No document");Bytes out;out.reserve(saved_.size());writeNode(root_,out,0);return out;}
void Document::save(const std::string& file){
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto data=serialize();Document check(schemas_.dump());check.load_bytes(data,schema_);require(check.serialize()==data,"Save roundtrip verification failed");
    auto target=path(file);static std::atomic<unsigned> sequence{0};
    auto temp=target;temp+=std::string(".tmp-")+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())+"-"+std::to_string(++sequence);
    auto backupTemp=temp;backupTemp+=".bak";
    try {writeFile(temp,data);auto reread=readFile(temp.u8string());require(reread==data,"Written file differs from snapshot");
        if(std::filesystem::exists(target)){
            auto backup=target;backup+=".bak";
            copyBackup(target,backupTemp);
            replaceFile(backupTemp,backup);
        }
        replaceFile(temp,target);
    }catch(...){std::error_code ec;std::filesystem::remove(temp,ec);std::filesystem::remove(backupTemp,ec);throw;}
    saved_=std::move(data);savedState_=state_;filename_=file;
}
void Document::activeOps(const Json& ops,const Node& n,std::vector<std::string>& names) const {for(const auto& op:ops){if(op.at("op")=="if")activeOps(op.at(condition(n,op.at("condition"))?"yes":"no"),n,names);else if(op.at("op")=="field")names.push_back(op.at("name"));}}
std::vector<std::shared_ptr<Node>> Document::childNodes(const Node& n) const {
    if(n.list)return n.items;
    std::vector<std::shared_ptr<Node>> out;std::vector<std::string> names;activeOps(allOps(n.type),n,names);
    for(const auto& name:names){auto& f=getField(const_cast<Node&>(n),name);if(f.child)out.push_back(f.child);}return out;
}
void Document::index(const std::shared_ptr<Node>& n){nodes_[n->id]=n;for(auto& c:childNodes(*n))index(c);}
void Document::rebuildIndex(){
    nodes_.clear();infoCache_.clear();searchIndex_.clear();if(root_)index(root_);
    for(const auto& entry:nodes_){auto row=nodeInfo(*entry.second);searchIndex_[entry.first]=lower(row["name"].get<std::string>()+" "+row["type"].get<std::string>());infoCache_[entry.first]=std::move(row);}
}
std::shared_ptr<Node> Document::get(std::uint64_t id)const{if(!id){require(bool(root_),"No document");return root_;}auto it=nodes_.find(id);require(it!=nodes_.end(),"Node no longer exists");return it->second;}
Json Document::nodeInfo(const Node& n)const{
    std::string name=n.label;
    if(!n.list)for(const auto& f:n.fields)if((f.first=="name"||f.first=="wnd"||f.first=="windowName")&&f.second.value.is_string()){name=f.second.value.get<std::string>();break;}
    auto type=n.type.substr(n.type.find('.')+1);if(name.empty())name=type;
    return Json{{"id",n.id},{"parent",n.parent},{"name",name},{"type",type},{"list",n.list},{"children",childNodes(n).size()}};
}
Json Document::summary()const{std::lock_guard<std::recursive_mutex> lock(mutex_);return Json{{"schema",schema_},{"file",filename_},{"nodes",nodes_.size()},{"root",root_?root_->id:0},{"revision",revision_},{"undo",undo_.size()},{"redo",redo_.size()},{"dirty",state_!=savedState_}};}
Json Document::info(std::uint64_t id)const{std::lock_guard<std::recursive_mutex> lock(mutex_);return infoCache_.at(get(id)->id);}
Json Document::children(std::uint64_t id)const{std::lock_guard<std::recursive_mutex> lock(mutex_);Json result=Json::array();for(auto& n:childNodes(*get(id)))result.push_back(infoCache_.at(n->id));return result;}
Json Document::properties(std::uint64_t id,bool includeInactive)const{
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto n=get(id);Json result=Json::array();if(n->list)return result;
    std::vector<std::string> active;activeOps(allOps(n->type),*n,active);
    for(const auto& pair:n->fields){const auto& name=pair.first;const auto& f=pair.second;const auto& s=*f.spec;
        if(s.at("op")=="tail"||s.at("kind")=="list"||s.at("kind")=="object")continue;
        bool enabled=std::find(active.begin(),active.end(),name)!=active.end();
        if(!enabled&&!includeInactive)continue;
        result.push_back(Json{{"name",name},{"kind",s.at("kind")},{"type",s.value("type",s.at("kind"))},{"value",f.value},{"enum",s.value("enum",Json::array())},{"readonly",name.rfind("_reserved_",0)==0||!enabled},{"active",enabled}});
    }return result;
}
Json Document::search(const std::string& query,bool neighbors)const{
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto q=lower(query);Json matches=Json::array();std::set<std::uint64_t> visible;
    for(const auto& entry:searchIndex_){auto n=get(entry.first);
        if(entry.second.find(q)!=std::string::npos){matches.push_back(n->id);while(n){visible.insert(n->id);n=n->parent?get(n->parent):nullptr;}}
    }
    if(neighbors){
        std::set<std::uint64_t> expanded;
        std::function<void(const std::shared_ptr<Node>&)> include=[&](const std::shared_ptr<Node>& n){
            if(!expanded.insert(n->id).second)return;
            visible.insert(n->id);for(auto& child:childNodes(*n))include(child);
        };
        for(const auto& id:matches){auto n=get(id.get<std::uint64_t>());include(n->parent?get(n->parent):n);}
    }
    return Json{{"matches",matches},{"visible",visible},{"revision",revision_}};
}
void Document::checkName(const Node& n,const std::string& value)const{
    require(!value.empty(),"Name cannot be empty");if(!n.parent)return;auto parent=get(n.parent);
    for(auto& sibling:childNodes(*parent))if(sibling->id!=n.id)require(lower(nodeInfo(*sibling)["name"].get<std::string>())!=lower(value),"Duplicate sibling name: "+value);
}
Json Document::preview_snapshot(std::uint64_t id)const {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    auto selected=get(id);
    if(selected->list&&selected->parent)selected=get(selected->parent);
    auto root=selected,context=selected;
    bool foundContext=false;
    for(auto parent=selected->parent;parent;){
        auto n=get(parent);auto type=n->type.substr(n->type.find('.')+1);
        if(type=="Window"||type=="ScrollArea"){
            root=n;if(!foundContext){context=n;foundContext=true;}
        }
        parent=n->parent;
    }
    std::size_t count=0;
    std::function<Json(const std::shared_ptr<Node>&,unsigned)> snapshot=[&](const std::shared_ptr<Node>& n,unsigned depth){
        require(++count<=5000&&depth<64,"Preview subtree is too large");
        Json props=Json::object(),children=Json::array();
        if(!n->list){
            std::vector<std::string> active;activeOps(allOps(n->type),*n,active);
            for(const auto& name:active){const auto& f=getField(*n,name);
                if(f.child){if(name=="children"&&f.child->list)for(const auto& c:f.child->items)children.push_back(snapshot(c,depth+1));}
                else props[name]=jsonScalar(f.value);
            }
        }
        return Json{{"id",n->id},{"type",n->type.substr(n->type.find('.')+1)},{"properties",std::move(props)},{"children",std::move(children)}};
    };
    return Json{{"schema",schema_},{"revision",revision_},{"selected",selected->id},{"context",context->id},{"root",snapshot(root,0)}};
}
void Document::commit(Change c){c.beforeState=state_;c.afterState=++nextState_;apply(c,true);undo_.push_back(std::move(c));redo_.clear();++revision_;}
void Document::apply(const Change& c,bool forward){
    if(c.action==0)getField(*c.node,c.field)=forward?c.after:c.before;
    else if(c.action==2)c.node->fields=forward?c.afterFields:c.beforeFields;
    else {bool insert=(c.action==1)==forward;auto& items=c.parent->items;if(insert)items.insert(items.begin()+static_cast<std::ptrdiff_t>(c.position),c.node);else items.erase(items.begin()+static_cast<std::ptrdiff_t>(c.position));}
    rebuildIndex();
    state_=forward?c.afterState:c.beforeState;
}
void Document::set(std::uint64_t id,const std::string& name,const Json& value){
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto n=get(id);auto& f=getField(*n,name);validateValue(*n,name,value);
    if(f.value==value)return;
    Change c;c.node=n;c.field=name;c.before=f;c.after=f;c.after.value=value;c.after.raw.clear();commit(std::move(c));
}
void Document::validateValue(const Node& node,const std::string& name,const Json& value)const{
    const auto& f=getField(const_cast<Node&>(node),name);require(!f.child&&name.rfind('_',0)!=0,"Field is read-only");std::string kind=f.spec->at("kind");
    if(kind=="string"){require(value.is_string(),"Expected string");require(value.get<std::string>().find('\0')==std::string::npos,"Embedded NUL");if(name=="name"||name=="wnd"||name=="windowName")checkName(node,value.get<std::string>());}
    else if(kind=="float")require(value.is_number()&&std::isfinite(value.get<double>())&&std::abs(value.get<double>())<=std::numeric_limits<float>::max(),"Expected finite float32");
    else {require(value.is_number_integer(),"Expected integer");auto v=value.get<std::int64_t>();require(v>=INT32_MIN&&v<=((kind=="color"||kind=="rgba")?std::int64_t(UINT32_MAX):INT32_MAX),"Integer out of range");if(kind=="bool")require(v>=-1&&v<=1,"Boolean must be -1, 0 or 1");}
}
void Document::set_many(std::uint64_t id,const Json& values){
    std::lock_guard<std::recursive_mutex> lock(mutex_);require(values.is_object(),"Expected property map");auto n=get(id);
    for(auto it=values.begin();it!=values.end();++it)validateValue(*n,it.key(),it.value());
    Change c;c.node=n;c.action=2;c.beforeFields=n->fields;c.afterFields=n->fields;bool changed=false;
    for(auto& f:c.afterFields)if(values.contains(f.first)&&f.second.value!=values.at(f.first)){f.second.value=values.at(f.first);f.second.raw.clear();changed=true;}
    if(changed)commit(std::move(c));
}
std::uint64_t Document::add_configured(std::uint64_t id,const std::string& type,const Json& values){
    std::lock_guard<std::recursive_mutex> lock(mutex_);require(values.is_object(),"Expected property map");auto parent=get(id);auto types=allowed_types(id);
    require(std::find(types.begin(),types.end(),Json(type))!=types.end(),"Type is not allowed here");
    auto n=std::make_shared<Node>();n->parent=parent->id;initialize(n,type,0);
    for(auto it=values.begin();it!=values.end();++it)validateValue(*n,it.key(),it.value());
    for(auto it=values.begin();it!=values.end();++it){auto& f=getField(*n,it.key());f.value=it.value();f.raw.clear();}
    for(const auto& f:n->fields)if(f.first=="name")checkName(*n,f.second.value.get<std::string>());
    Change c;c.node=n;c.parent=parent;c.position=parent->items.size();c.action=1;commit(c);return n->id;
}
Json Document::allowed_types(std::uint64_t id)const{
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto n=get(id);require(n->list,"Select a list");Json out=Json::array();
    if(!n->poly){out.push_back(n->itemType);return out;}
    auto package=schema_.substr(0,schema_.find('.'))+'.';
    for(auto it=schemas_["records"].begin();it!=schemas_["records"].end();++it){if(it.key().rfind(package,0)!=0||it.value().value("abstract",false))continue;
        auto type=it.key();while(true){if(type==n->itemType){out.push_back(it.key());break;}const auto& base=schemas_["records"].at(type).at("base");if(base.is_null())break;type=base.get<std::string>();}
    }return out;
}
std::uint64_t Document::add(std::uint64_t id,const std::string& type){
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto parent=get(id);auto types=allowed_types(id);require(std::find(types.begin(),types.end(),Json(type))!=types.end(),"Type is not allowed here");
    auto n=std::make_shared<Node>();n->parent=parent->id;initialize(n,type,0);
    for(auto& f:n->fields)if(f.first=="name"){std::string name="New"+type.substr(type.find_last_of('.')+1);unsigned i=1;while(true){try{checkName(*n,name);break;}catch(const std::exception&){name="New"+type.substr(type.find_last_of('.')+1)+std::to_string(i++);}}f.second.value=name;}
    Change c;c.node=n;c.parent=parent;c.position=parent->items.size();c.action=1;commit(c);return n->id;
}
std::uint64_t Document::duplicate(std::uint64_t id,std::uint64_t target){
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto source=get(id);auto parent=get(target?target:source->parent);auto types=allowed_types(parent->id);require(std::find(types.begin(),types.end(),Json(source->type))!=types.end(),"Incompatible destination list");
    Bytes data;writeNode(source,data,0);auto n=std::make_shared<Node>();n->parent=parent->id;initialize(n,source->type,0);std::size_t p=0;parseNode(n,data,p,0);
    for(auto& f:n->fields)if(f.first=="name"){auto original=f.second.value.get<std::string>();auto name=original+"_copy";unsigned i=2;while(true){try{checkName(*n,name);break;}catch(const std::exception&){name=original+"_copy"+std::to_string(i++);}}f.second.value=name;f.second.raw.clear();}
    Change c;c.node=n;c.parent=parent;c.position=parent->items.size();c.action=1;commit(c);return n->id;
}
void Document::remove(std::uint64_t id){std::lock_guard<std::recursive_mutex> lock(mutex_);auto n=get(id);require(n->parent!=0,"Cannot delete root");auto parent=get(n->parent);require(parent->list,"Only list items can be deleted");Change c;c.node=n;c.parent=parent;c.position=std::find(parent->items.begin(),parent->items.end(),n)-parent->items.begin();c.action=-1;commit(c);}
bool Document::undo(){std::lock_guard<std::recursive_mutex> lock(mutex_);if(undo_.empty())return false;auto c=undo_.back();undo_.pop_back();apply(c,false);redo_.push_back(c);++revision_;return true;}
bool Document::redo(){std::lock_guard<std::recursive_mutex> lock(mutex_);if(redo_.empty())return false;auto c=redo_.back();redo_.pop_back();apply(c,true);undo_.push_back(c);++revision_;return true;}

Json Document::jsonNode(const std::shared_ptr<Node>& node,unsigned depth)const {
    require(depth<128,"JSON tree too deep");
    Json fields=Json::object();
    for(const auto& pair:node->fields){
        const auto& f=pair.second;const auto& spec=*f.spec;Json entry;
        if(spec.at("op")=="tail")entry=Json{{"raw",hex(f.raw)}};
        else {
            const std::string kind=spec.at("kind");
            if(kind=="list"){
                Json items=Json::array();for(const auto& item:f.child->items)items.push_back(jsonNode(item,depth+1));
                entry=Json{{"items",std::move(items)},{"prefix",hex(f.child->prefix)}};
            }else if(kind=="object")entry=Json{{"object",f.child?jsonNode(f.child,depth+1):Json(nullptr)}};
            else entry=Json{{"value",jsonScalar(f.value)},{"raw",hex(f.raw)}};
        }
        fields[pair.first]=std::move(entry);
    }
    return Json{{"type",node->type},{"tag",hex(node->tag)},{"fields",std::move(fields)}};
}

bool Document::compatibleType(const std::string& actual,const std::string& expected,bool polymorphic)const {
    const auto& records=schemas_.at("records");
    if(!records.contains(actual))return false;
    if(!polymorphic)return actual==expected;
    if(actual.substr(0,actual.find('.'))!=expected.substr(0,expected.find('.'))||records.at(actual).value("abstract",false))return false;
    auto type=actual;
    for(unsigned i=0;i<128;++i){
        if(type==expected)return true;
        const auto& base=records.at(type).at("base");if(base.is_null())return false;
        type=base.get<std::string>();
    }
    return false;
}

void Document::importNode(const Json& data,const std::shared_ptr<Node>& node,unsigned depth) {
    require(depth<128&&next_<MaxNodes,"JSON node/depth limit exceeded");
    require(data.is_object()&&data.at("type")==node->type,"JSON object type does not match schema");
    require(data.at("fields").is_object()&&data.at("fields").size()==node->fields.size(),"JSON must contain exactly the schema fields for "+node->type);
    auto tag=unhex(data.value("tag",Json("")));
    if(!tag.empty()){
        std::size_t pos=0;auto name=readString(tag,pos);require(pos==tag.size(),"Invalid type tag");
        if(name==node->type.substr(node->type.find('.')+1))node->tag=std::move(tag);
    }
    for(auto& pair:node->fields){
        const auto& name=pair.first;auto& f=pair.second;const auto& spec=*f.spec;
        try {
            const auto& entry=data.at("fields").at(name);require(entry.is_object(),"Expected field object");
            if(spec.at("op")=="tail"){f.raw=unhex(entry.at("raw"));continue;}
            const std::string kind=spec.at("kind");
            if(kind=="list"){
                auto list=f.child;const auto& items=entry.at("items");
                require(items.is_array()&&items.size()<=MaxNodes,"Invalid JSON list");
                list->prefix=unhex(entry.value("prefix",Json("")));
                if(!list->prefix.empty()){
                    std::size_t pos=0;auto count=list->compact?compact(list->prefix,pos):static_cast<std::int32_t>(u32(list->prefix,pos));
                    require(count>=0&&static_cast<std::size_t>(count)<=MaxNodes&&pos==list->prefix.size(),"Invalid list prefix");
                    list->oldCount=static_cast<std::size_t>(count);
                }
                for(const auto& value:items){
                    auto type=value.at("type").get<std::string>();
                    require(compatibleType(type,list->itemType,list->poly),"Incompatible list element type: "+type);
                    auto child=std::make_shared<Node>();child->parent=list->id;initialize(child,type,depth+1);importNode(value,child,depth+1);list->items.push_back(child);
                }
            }else if(kind=="object"){
                const auto& value=entry.at("object");
                if(value.is_null()){require(spec.value("poly",false),"Missing typed object");f.child.reset();continue;}
                auto type=value.at("type").get<std::string>();
                require(compatibleType(type,spec.at("type"),spec.value("poly",false)),"Incompatible object type");
                if(!f.child){f.child=std::make_shared<Node>();f.child->parent=node->id;initialize(f.child,type,depth+1);}
                importNode(value,f.child,depth+1);
            }else{
                auto value=checkedScalar(entry.at("value"),kind);
                auto raw=unhex(entry.value("raw",Json("")));
                // Human-readable value is authoritative. Keep original encoding only
                // when its decoded value agrees, never let stale raw bytes hide edits.
                if(!raw.empty()&&!sameScalar(readScalar(kind,raw),value,kind))raw.clear();
                f.value=std::move(value);f.raw=std::move(raw);
            }
        }catch(const std::exception& error){throw std::runtime_error(node->type+'.'+name+": "+error.what());}
    }
}

std::string Document::to_json()const {
    std::lock_guard<std::recursive_mutex> lock(mutex_);require(bool(root_),"No document");
    return Json{{"format","interface-editor-document"},{"version",1},{"schema",schema_},{"tree",jsonNode(root_,0)}}.dump(2);
}

void Document::from_json(const std::string& text) {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    require(text.size()<=MaxFile,"JSON file too large");
    auto data=Json::parse(text,[](int depth,Json::parse_event_t,Json&){require(depth<=512,"JSON nesting limit exceeded");return true;});
    require((data.at("format")=="interface-editor-document"||data.at("format")=="xdat-editor-document")&&data.at("version")==1,"Unsupported JSON document format/version");
    auto schema=data.at("schema").get<std::string>();
    bool known=false;for(const auto& item:schemas_.at("versions"))if(item.at(1)==schema)known=true;
    require(known,"Unknown XDAT schema in JSON");
    Document staged(schemas_.dump());staged.schema_=schema;staged.root_=std::make_shared<Node>();staged.initialize(staged.root_,schema,0);
    staged.importNode(data.at("tree"),staged.root_,0);
    auto bytes=staged.serialize();Document verified(schemas_.dump());verified.load_bytes(bytes,schema);
    require(verified.serialize()==bytes,"JSON binary roundtrip validation failed");
    // Publish only after all validation succeeds; retain inactive field values.
    schemas_.swap(staged.schemas_);operations_.clear();root_=staged.root_;schema_=schema;next_=staged.next_;saved_.clear();filename_.clear();
    undo_.clear();redo_.clear();state_=nextState_=1;savedState_=0;++revision_;rebuildIndex();
}

void Document::open_json(const std::string& file) {
    auto bytes=readFile(file);from_json(std::string(bytes.begin(),bytes.end()));
}

void Document::export_json(const std::string& file)const {
    auto text=to_json();Bytes bytes(text.begin(),text.end());
    auto target=path(file),temp=target;temp+=".tmp-json-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
    auto backupTemp=temp;backupTemp+=".bak";
    try {
        writeFile(temp,bytes);require(readFile(temp.u8string())==bytes,"Written JSON differs from snapshot");
        if(std::filesystem::exists(target)){auto backup=target;backup+=".bak";copyBackup(target,backupTemp);replaceFile(backupTemp,backup);}
        replaceFile(temp,target);
    }catch(...){std::error_code ec;std::filesystem::remove(temp,ec);std::filesystem::remove(backupTemp,ec);throw;}
}
}
