#include "package.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace ue {
static void bad(const std::string& message) { throw std::runtime_error(message); }
std::string lower(std::string s) { for(auto& c:s) if(c>='A'&&c<='Z') c+=32; return s; }
std::string leaf(const std::string& s) { auto i=s.rfind('.');return i==s.npos?s:s.substr(i+1); }
std::string hex(const Bytes& b) { std::string s;static const char* d="0123456789abcdef";for(auto c:b){s+=d[c>>4];s+=d[c&15];}return s; }
std::string utf8(uint32_t c) {
    if(c>0x10ffff || (c>=0xd800&&c<=0xdfff)) bad("Invalid Unicode scalar");
    std::string s;
    if(c<128) s+=char(c);
    else if(c<2048){s+=char(0xc0|(c>>6));s+=char(0x80|(c&63));}
    else if(c<65536){s+=char(0xe0|(c>>12));s+=char(0x80|((c>>6)&63));s+=char(0x80|(c&63));}
    else {s+=char(0xf0|(c>>18));s+=char(0x80|((c>>12)&63));s+=char(0x80|((c>>6)&63));s+=char(0x80|(c&63));}return s;
}
Reader::Reader(const Bytes& b,size_t offset,size_t length):data(b),pos(offset),end(b.size()) {
    if(offset>b.size() || (length!=SIZE_MAX && length>b.size()-offset)) bad("Reader bounds");
    if(length!=SIZE_MAX)end=offset+length;
}
void Reader::require(size_t n) const {if(pos>end || n>end-pos)bad("Truncated data at serial offset "+std::to_string(pos));}
uint8_t Reader::byte(){require(1);return data[pos++];}
uint16_t Reader::u16(){auto a=byte();return uint16_t(a|(uint16_t(byte())<<8));}
uint32_t Reader::u32(){auto a=u16();return uint32_t(a)|(uint32_t(u16())<<16);}
uint64_t Reader::u64(){auto a=u32();return uint64_t(a)|(uint64_t(u32())<<32);}
int32_t Reader::i32(){auto n=u32();int32_t v;std::memcpy(&v,&n,4);return v;}
float Reader::f32(){auto n=u32();float v;std::memcpy(&v,&n,4);return v;}
void Reader::skip(size_t n){require(n);pos+=n;}
int32_t Reader::index(){
    unsigned f=byte(),shift=6;uint64_t v=f&63;bool more=(f&64)!=0;
    for(int i=0;more&&i<4;++i){unsigned b=byte();if(i==3&&(b&0xe0))bad("Compact index exceeds 32 bits");v|=uint64_t(b&127)<<shift;shift+=7;more=(b&128)!=0;}
    if(more||v>((f&128)?0x80000000ull:0x7fffffffull))bad("Invalid compact index");
    return int32_t((f&128)?-int64_t(v):int64_t(v));
}
std::string Reader::string(){
    int64_t n=index();size_t count=size_t(n<0?-n:n);require(count*(n<0?2:1));
    std::string s;
    for(size_t i=0;i<count;++i){uint32_t c=n<0?u16():byte();if(i+1==count){if(c)bad("Unterminated package string");break;}
        if(n<0 && c>=0xd800&&c<=0xdbff){if(i+2>=count)bad("Truncated surrogate");uint32_t lo=u16();++i;if(lo<0xdc00||lo>0xdfff)bad("Invalid surrogate");c=0x10000+((c-0xd800)<<10)+(lo-0xdc00);}s+=utf8(c);
    }return s;
}
Package::Package(const std::filesystem::path& file):path(file){
    std::ifstream in(file,std::ios::binary|std::ios::ate);if(!in)bad("Cannot open package: "+file.u8string());
    auto length=in.tellg();if(length<36||length>512*1024*1024)bad("Package size outside 36 bytes..512 MiB");
    data.resize(size_t(length));in.seekg(0);if(!in.read(reinterpret_cast<char*>(data.data()),length))bad("Package read failed");
    for(const std::string marker:{"Lineage2Ver111","GamekitData111"}){
        Bytes prefix;for(char c:marker){prefix.push_back(uint8_t(c));prefix.push_back(0);}
        if(data.size()>=prefix.size()&&std::equal(prefix.begin(),prefix.end(),data.begin())){data.erase(data.begin(),data.begin()+prefix.size());for(auto& c:data)c^=0xac;envelope=marker;break;}
    }
    Reader r(data);if(r.u32()!=0x9e2a83c1)bad("Unsupported envelope or invalid Unreal signature");
    version=r.u16();licensee=r.u16();if(!((version==123&&(licensee==0||licensee==37))||(version==126&&licensee==0)))bad("Unsupported package version "+std::to_string(version)+"/"+std::to_string(licensee));
    r.u32();int nc=r.i32(),no=r.i32(),ec=r.i32(),eo=r.i32(),ic=r.i32(),io=r.i32();
    for(auto pair:{std::pair<int,int>{nc,no},{ec,eo},{ic,io}})if(pair.first<0||pair.first>2000000||size_t(pair.first)>data.size()||pair.second<0||size_t(pair.second)>=data.size())bad("Invalid table bounds");
    r.pos=size_t(no);for(int i=0;i<nc;++i){names.push_back(r.string());r.u32();}
    r.pos=size_t(io);for(int i=0;i<ic;++i){Entry e;e.classPackage=name(r.index());e.importClass=name(r.index());e.outer=r.i32();e.name=name(r.index());imports.push_back(e);}
    r.pos=size_t(eo);for(int i=0;i<ec;++i){Entry e;e.cls=r.index();e.super=r.index();e.outer=r.i32();e.name=name(r.index());e.flags=r.u32();int size=r.index(),offset=size?r.index():0;if(size<0||offset<0||size_t(offset)>data.size()||size_t(size)>data.size()-size_t(offset))bad("Invalid export bounds");e.size=size_t(size);e.offset=size_t(offset);exports.push_back(e);children[e.outer].push_back(i+1);}
    paths[0]="None";
    for(int i=-int(imports.size());i<=int(exports.size());++i){ref(i);if(i>0){ref(entry(i).cls);ref(entry(i).super);}}
}
const Entry& Package::entry(int id) const {int64_t i=id>0?int64_t(id)-1:-int64_t(id)-1;auto& t=id>0?exports:imports;if(!id||i<0||size_t(i)>=t.size())bad("Invalid object reference "+std::to_string(id));return t[size_t(i)];}
std::string Package::name(int id) const {if(id<0||size_t(id)>=names.size())bad("Invalid name index");return names[size_t(id)];}
std::string Package::ref(int id) const {
    auto it=paths.find(id);if(it!=paths.end())return it->second;
    std::set<int> seen;std::vector<int> chain;int at=id;
    while(!paths.count(at)){if(!seen.insert(at).second||chain.size()>256)bad("Cyclic/too deep outer reference");chain.push_back(at);at=entry(at).outer;}
    std::string s=paths.at(at);for(auto i=chain.rbegin();i!=chain.rend();++i){auto& e=entry(*i);s=(e.outer?s+".":"")+e.name;paths[*i]=s;}return paths.at(id);
}
std::string Package::kind(int id) const {const auto& e=entry(id);return id<0?e.importClass:(e.cls?leaf(ref(e.cls)):"Class");}
int Package::find(const std::string& pathName) const {for(size_t i=0;i<exports.size();++i)if(lower(ref(int(i)+1))==lower(pathName))return int(i)+1;return 0;}
Reader Package::reader(int id) const {auto& e=entry(id);if(id<1)bad("Import has no serialized data");if(e.flags&0x02000000)bad("Serialized execution stack unsupported");return Reader(data,e.offset,e.size);}
const std::vector<int>& Package::members(int id) const {static const std::vector<int> empty;auto i=children.find(id);return i==children.end()?empty:i->second;}
int Decoder::reference(bool){pc+=4;return r.index();}
int Decoder::byte(){++pc;return r.byte();}int Decoder::word(){pc+=2;return r.u16();}int Decoder::integer(){pc+=4;return r.i32();}
Node Decoder::expression(int depth){
    if(depth>128||++count>1000000)bad("Bytecode complexity limit");
    Node n;n.pc=pc;n.op=byte();int op=n.op;
    auto child=[&](){n.children.push_back(expression(depth+1));};
    auto args=[&](){do{child();}while(n.children.back().op!=0x16);};
    if(op>=0x60){n.kind="native";n.index=op<0x70?((op-0x60)<<8)+byte():op;args();}
    else switch(op){
    case 0:case 1:case 2:case 0x29:n.kind=op==0?"local":op==1?"instance":op==2?"default":"native_parameter";n.ref=reference();n.text=p.ref(n.ref);break;
    case 4:case 15:case 20:n.kind=op==4?"return":op==15?"assign":"assign_bool";child();if(op!=4)child();break;
    case 0x39:n.kind="cast";n.index=byte();child();break;
    case 0x2d:n.kind="bool_variable";child();break;
    case 0x18:n.kind="skip";n.index=word();child();break;
    case 0x0d:case 0x0e:case 0x37:n.kind=op==13?"goto_label":op==14?"discard_string":"array_length";child();break;
    case 9:n.kind="assert";n.index=word();child();break;
    case 0x10:case 0x1a:case 0x40:case 0x41:case 0x45:case 0x11:
        n.kind=op==0x10?"dynamic_array_element":op==0x1a?"array_element":op==0x40?"array_insert":op==0x41?"array_remove":op==0x45?"assign_delegate":"new";
        for(int i=0;i<(op==0x11?4:(op==0x40||op==0x41)?3:2);++i)child();break;
    case 0x32:case 0x33:case 0x36:n.kind=op==0x32?"struct_equal":op==0x33?"struct_not_equal":"struct_member";n.ref=reference();n.text=p.ref(n.ref);child();if(op!=0x36)child();break;
    case 0x2f:n.kind="iterator";child();n.target=word();break;
    case 0x0c:n.kind="label_table";if(pc&3)bad("Misaligned label table");n.value=Json::array();for(;;){auto text=p.name(reference(true));int target=integer();n.value.push_back({text,target});if(text=="None")break;}break;
    case 6:case 7:case 10:n.kind=op==6?"jump":op==7?"jump_if_not":"case";n.target=word();if(op==7||(op==10&&n.target!=65535))child();break;
    case 5:n.kind="switch";n.index=byte();child();break;
    case 0x1c:n.kind="final_call";n.ref=reference();n.text=p.ref(n.ref);args();break;
    case 0x1b:case 0x38:n.kind=op==0x1b?"virtual_call":"global_call";n.text=p.name(reference(true));args();break;
    case 0x19:case 0x12:n.kind=op==0x19?"context":"class_context";child();n.target=word();n.index=byte();child();break;
    case 0x13:case 0x2e:n.kind=op==0x13?"class_cast":"dynamic_cast";n.ref=reference();n.text=p.ref(n.ref);child();break;
    case 0x1d:case 0x1e:case 0x24:case 0x2c:n.kind="constant";if(op==0x1e){pc+=4;n.value=r.f32();}else n.value=op==0x1d?integer():byte();break;
    case 0x1f:case 0x34:n.kind="string";for(;;){uint32_t c=op==0x34?word():byte();if(!c)break;if(op==0x34&&c>=0xd800&&c<=0xdbff){auto lo=word();if(lo<0xdc00||lo>0xdfff)bad("Invalid bytecode surrogate");c=0x10000+((c-0xd800)<<10)+(lo-0xdc00);}n.text+=utf8(c);}break;
    case 0x20:case 0x21:n.kind=op==0x20?"object":"name";n.ref=reference();n.text=op==0x20?p.ref(n.ref):p.name(n.ref);break;
    case 0x22:case 0x23:case 0x35:n.kind=op==0x22?"rotation":op==0x23?"vector":"range";n.value=Json::array();for(int i=0;i<(op==0x35?2:3);++i){if(op==0x22)n.value.push_back(integer());else{pc+=4;n.value.push_back(r.f32());}}break;
    case 0x43:n.kind="delegate_property";n.ref=reference();n.text=p.ref(n.ref);n.value=p.name(reference(true));break;
    case 0x44:n.kind="delegate_name";n.text=p.name(reference(true));break;
    case 0x42:n.kind="debug";integer();integer();integer();while(byte()!=0){}break;
    case 8:n.kind="stop";break;case 11:n.kind="nothing";break;case 22:n.kind="end_parameters";break;case 23:n.kind="self";break;
    case 37:n.kind="int_zero";break;case 38:n.kind="int_one";break;case 39:n.kind="true";break;case 40:n.kind="false";break;case 42:n.kind="none";break;case 48:n.kind="iterator_pop";break;case 49:n.kind="iterator_next";break;
    default:bad("Unsupported opcode "+std::to_string(op)+" at PC "+std::to_string(n.pc)+", serial "+std::to_string(r.pos-1));
    }
    n.finish=pc;return n;
}
std::vector<Node> Decoder::script(int size){if(size<0||size_t(size)>p.data.size()*4)bad("Invalid script memory size");std::vector<Node> nodes;while(pc<size)nodes.push_back(expression());if(pc!=size)bad("Script memory-size mismatch");return nodes;}
StructInfo Package::structure(int id,bool isClass,bool isState) const {
    auto r=reader(id);if(!isClass&&name(r.index())!="None")bad("Tagged struct properties unsupported");
    StructInfo s;for(int& f:s.fields){f=r.index();ref(f);}s.friendly=name(r.index());ref(r.index());r.skip(8);s.size=r.i32();Decoder d{*this,r};s.nodes=d.script(s.size);
    if(isState||isClass){s.probe=r.u64();s.ignore=r.u64();s.labelOffset=r.u16();s.stateFlags=r.u32();}
    if(isClass)s.classFlags=r.u32();s.tail=r.pos;return s;
}
Function Package::function(int id) const {
    if(kind(id)!="Function")bad("Not a function");auto s=structure(id);Function f;f.id=id;std::copy(std::begin(s.fields),std::end(s.fields),f.fields);f.size=s.size;f.friendly=s.friendly;f.nodes=std::move(s.nodes);
    auto r=reader(id);r.pos=s.tail;f.native=r.u16();f.precedence=r.byte();f.flags=r.u32();if(f.flags&0x40)r.u16();if(r.pos!=r.end)bad("Trailing function data: "+ref(id));return f;
}
Property Package::property(int id) const {
    auto r=reader(id);if(name(r.index())!="None")bad("Tagged property metadata unsupported");r.index();Property v;v.id=id;v.next=r.index();v.kind=kind(id);v.dim=r.i32();v.flags=r.u32();v.category=name(r.index());if(v.flags&0x20)r.u16();
    if(v.kind=="ByteProperty"||v.kind=="ObjectProperty"||v.kind=="ClassProperty"||v.kind=="StructProperty"||v.kind=="ArrayProperty")v.ref=r.index();
    if(v.kind=="ClassProperty")v.meta=r.index();if(v.dim<0||v.dim>1000000)bad("Invalid property dimension");return v;
}
std::vector<std::string> Package::enumeration(int id) const {auto r=reader(id);if(name(r.index())!="None")bad("Enum properties unsupported");r.index();r.index();int count=r.index();if(count<0||count>256)bad("Invalid enum count");std::vector<std::string> v;while(count--)v.push_back(name(r.index()));if(r.pos!=r.end)bad("Trailing enum bytes");return v;}
std::string Package::constant(int id) const {auto r=reader(id);if(name(r.index())!="None")bad("Const properties unsupported");r.index();r.index();auto text=r.string();if(r.pos!=r.end)bad("Trailing const bytes");return text;}
Json Package::scriptText(int id) const {
    auto s=structure(id,true);int textId=s.fields[2];if(textId<=0||kind(textId)!="TextBuffer")return nullptr;
    auto r=reader(textId);if(name(r.index())!="None")bad("TextBuffer tagged properties unsupported");r.skip(8);auto start=r.pos;int count=r.index();auto bytesStart=r.pos;r.pos=start;auto text=r.string();if(r.pos!=r.end)bad("Trailing ScriptText bytes");
    Bytes raw(data.begin()+bytesStart,data.begin()+r.pos);if(count>0&&!raw.empty())raw.pop_back();if(count<0&&raw.size()>=2){raw.resize(raw.size()-2);raw.insert(raw.begin(),{0xff,0xfe});}
    if(text.find_first_not_of(" \r\n\t")==text.npos)return nullptr;
    return Json{{"text",text},{"raw_hex",hex(raw)},{"encoding",count<0?"utf-16":"latin1"}};
}
Json Package::summary() const {
    Json classes=Json::array();for(size_t i=0;i<exports.size();++i)if(exports[i].cls==0)classes.push_back({{"id",i+1},{"name",exports[i].name},{"path",ref(int(i)+1)},{"super",ref(exports[i].super)}});
    return {{"file",path.u8string()},{"version",version},{"licensee",licensee},{"envelope",envelope},{"names",names.size()},{"imports",imports.size()},{"exports",exports.size()},{"classes",classes}};
}
Json nodeJson(const Node& n){Json c=Json::array();for(auto& child:n.children)c.push_back(nodeJson(child));return {{"pc",n.pc},{"end",n.finish},{"opcode",n.op},{"kind",n.kind},{"reference",n.ref},{"text",n.text},{"value",n.value},{"index",n.index},{"target",n.target},{"children",c}};}
}
