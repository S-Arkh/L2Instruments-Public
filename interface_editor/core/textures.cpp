// Read-only UE2 texture support. Native mip layout follows acmi MipMapInfo
// (LICENSE.acmi); image decoding and bounded package reader are implemented here.
#include "textures.hpp"
#include <algorithm>
#include <codecvt>
#include <filesystem>
#include <fstream>
#include <list>
#include <locale>
#include <mutex>
#include <set>
#include <stdexcept>
#include <unordered_map>

namespace interface_editor {
namespace {
using Bytes=std::vector<std::uint8_t>;
constexpr std::size_t MaxPackage=512*1024*1024,PackageBudget=512*1024*1024;
void check(bool b,const std::string& message){if(!b)throw std::runtime_error(message);}
std::string lower(std::string s){for(char& c:s)if(c>='A'&&c<='Z')c+=32;return s;}
struct Reader {
    const Bytes& data;std::size_t pos,end;
    explicit Reader(const Bytes& b,std::size_t p=0,std::size_t size=0):data(b),pos(p),end(size?p+size:b.size()){check(p<=b.size()&&end<=b.size(),"Invalid texture bounds");}
    void skip(std::size_t n){check(pos<=end&&n<=end-pos,"Truncated texture/package");pos+=n;}
    std::uint8_t byte(){skip(1);return data[pos-1];}
    std::uint16_t u16(){auto lo=byte();auto hi=byte();return std::uint16_t(lo|(hi<<8));}
    std::uint32_t u32(){std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(byte())<<(8*i);return v;}
    std::int32_t index(){auto first=byte();std::uint32_t v=first&63;bool more=first&64;unsigned shift=6;
        for(unsigned i=1;more&&i<5;++i){auto b=byte();check(i!=4||(b&0xe0)==0,"Compact index overflow");v|=std::uint32_t(b&(i==4?31:127))<<shift;shift+=7;more=i<4&&(b&128);}
        check(v<=0x7fffffff,"Compact index overflow");return first&128?-static_cast<std::int32_t>(v):static_cast<std::int32_t>(v);}
    std::string string(){auto n=index();if(!n)return {};auto size=std::size_t(n<0?-std::int64_t(n)*2:n);auto start=pos;skip(size);
        check(data[pos-1]==0&&(n>0||data[pos-2]==0),"Invalid string terminator");
        if(n>0)return std::string(data.begin()+start,data.begin()+pos-1);
        std::u16string s;for(auto i=start;i+2<pos;i+=2)s.push_back(char16_t(data[i]|data[i+1]<<8));return std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.to_bytes(s);}
    Bytes take(std::size_t n){auto p=pos;skip(n);return Bytes(data.begin()+p,data.begin()+pos);}
};
struct Entry {std::string name;int outer=0,cls=0;std::size_t offset=0,size=0;std::uint32_t flags=0;};
struct Package {
    Bytes data;unsigned version=0,license=0;std::vector<std::string> names;
    std::vector<Entry> imports,exports;std::unordered_map<std::string,std::size_t> paths;
    explicit Package(const std::filesystem::path& path){
        std::ifstream f(path,std::ios::binary|std::ios::ate);check(bool(f),"Cannot open texture package");auto size=f.tellg();check(size>=36&&std::uint64_t(size)<=MaxPackage,"Unsupported package size");
        data.resize(static_cast<std::size_t>(size));f.seekg(0);f.read(reinterpret_cast<char*>(data.data()),size);check(bool(f),"Cannot read texture package");
        const std::u16string prefix=u"Lineage2Ver";
        bool envelope=true;for(std::size_t i=0;i<prefix.size();++i)if(data[2*i]!=prefix[i]||data[2*i+1])envelope=false;
        if(envelope){
            std::string marker;for(unsigned i=0;i<14;++i)marker.push_back(char(data[2*i]));
            unsigned key=0;
            if(marker=="Lineage2Ver111")key=0xac;
            else if(marker=="Lineage2Ver121"){for(unsigned char c:lower(path.filename().u8string()))key+=c;key&=255;}
            else throw std::runtime_error("Unsupported UTX envelope: "+marker);
            data.erase(data.begin(),data.begin()+28);for(auto& b:data)b^=static_cast<std::uint8_t>(key);
        }
        Reader r(data);check(r.u32()==0x9e2a83c1,"Not an Unreal texture package");auto versions=r.u32();version=versions&0xffff;license=versions>>16;
        check((version>=100&&version<=129)||(version==133&&license==40),"Unsupported Unreal texture package version");r.u32();
        auto nc=r.u32(),no=r.u32(),ec=r.u32(),eo=r.u32(),ic=r.u32(),io=r.u32();
        for(auto pair:{std::make_pair(nc,no),std::make_pair(ec,eo),std::make_pair(ic,io)})check(pair.first<=1000000&&pair.second<data.size(),"Invalid package table");
        r.pos=no;for(unsigned i=0;i<nc;++i){names.push_back(r.string());r.u32();}
        r.pos=io;for(unsigned i=0;i<ic;++i){r.index();auto cls=name(r.index());Entry e;e.outer=static_cast<int>(r.u32());e.name=name(r.index());imports.push_back(e);}
        r.pos=eo;for(unsigned i=0;i<ec;++i){Entry e;e.cls=r.index();r.index();e.outer=static_cast<int>(r.u32());e.name=name(r.index());e.flags=r.u32();auto n=r.index();check(n>=0,"Negative export size");e.size=n;e.offset=n?std::size_t(r.index()):0;check(e.offset<=data.size()&&e.size<=data.size()-e.offset,"Invalid export bounds");exports.push_back(e);}
        for(std::size_t i=0;i<exports.size();++i)paths.emplace(lower(ref(static_cast<int>(i+1))),i);
    }
    const std::string& name(int i)const{check(i>=0&&std::size_t(i)<names.size(),"Invalid name reference");return names[i];}
    std::string ref(int i,unsigned depth=0)const{if(!i)return {};check(depth<64,"Cyclic object reference");const auto& entries=i>0?exports:imports;auto n=i>0?std::int64_t(i)-1:-std::int64_t(i)-1;check(n>=0&&std::size_t(n)<entries.size(),"Invalid object reference");const auto& e=entries[std::size_t(n)];return (e.outer?ref(e.outer,depth+1)+".":"")+e.name;}
    using Props=std::unordered_map<std::string,Bytes>;
    Props properties(Reader& r)const{
        Props props;
        for(unsigned count=0;count<10000;++count){auto key=lower(name(r.index()));if(key=="none")return props;
            auto info=r.byte();auto kind=info&15;if(kind==10)r.index();auto code=(info>>4)&7;
            std::size_t size=code<5?std::array<unsigned,5>{1,2,4,12,16}[code]:code==5?r.byte():code==6?r.u16():r.u32();
            if(kind==3){props[key]=Bytes{std::uint8_t(bool(info&128))};continue;}
            if(info&128){auto index=r.byte();if((index&0xc0)==0xc0)r.skip(3);else if(index&128)r.skip(1);}
            props[key]=r.take(size);
        }throw std::runtime_error("Too many texture properties");
    }
    static int integer(const Props& p,const std::string& name,int fallback=0){auto it=p.find(name);if(it==p.end())return fallback;check(it->second.size()==4,"Invalid integer texture property");Reader r(it->second);return static_cast<int>(r.u32());}
    TextureImage texture(const std::string& name)const{
        auto found=paths.find(lower(name));check(found!=paths.end(),"Texture export not found: "+name);const auto& e=exports[found->second];
        auto cls=lower(ref(e.cls));check(cls=="engine.texture"||cls=="engine.masktexture","Unsupported texture class: "+cls);check(!(e.flags&0x02000000),"Stacked texture export unsupported");
        Reader r(data,e.offset,e.size);auto p=properties(r);
        auto fmt=p.count("format")&&!p.at("format").empty()?p.at("format")[0]:0;
        auto width=integer(p,"usize"),height=integer(p,"vsize");check(width>0&&height>0&&width<=8192&&height<=8192,"Invalid texture dimensions");
        Bytes palette;
        if(fmt==0){check(p.count("palette"),"P8 texture has no palette");Reader pr(p.at("palette"));auto idx=pr.index();check(idx>0&&std::size_t(idx)<=exports.size(),"External palette is unsupported");const auto& pe=exports[idx-1];Reader pal(data,pe.offset,pe.size);properties(pal);check(pal.index()==256,"Expected 256-entry palette");palette=pal.take(1024);}
        if(license<=12){}else if(license<=28)r.skip(4);else if(license<=32){}else if(license<=36){r.skip(license==36?1058:1067);for(unsigned i=0;i<17;++i)r.string();r.u32();}
        else{r.skip(version==129||license>=40?92:36);auto count=r.index();check(count>=0&&count<=1024,"Invalid material metadata");for(int i=0;i<count;++i){r.string();auto extra=r.byte();for(unsigned j=0;j<extra;++j)r.string();}r.string();r.u32();}
        auto count=r.index();check(count>0&&count<=16,"Invalid mip count");TextureImage image;
        for(int i=0;i<count;++i){auto skip=r.u32();auto size=r.index();check(size>=0,"Invalid mip length");auto pixels=r.take(std::size_t(size));check(skip==0||skip==r.pos,"Invalid mip skip offset");auto w=r.u32(),h=r.u32();auto ubits=r.byte(),vbits=r.byte();check(w==std::max(1u,unsigned(width)>>i)&&h==std::max(1u,unsigned(height)>>i)&&ubits<=16&&vbits<=16,"Invalid mip dimensions");
            if(i==0)image=decode_texture(fmt,w,h,pixels,palette,p.count("bmasked")&&p.at("bmasked")[0]);
        }
        check(r.pos==r.end,"Unexpected texture payload suffix");
        image.split=p.count("bsplit9texture")&&p.at("bsplit9texture")[0];
        for(unsigned i=0;i<3;++i){image.grid[i]=integer(p,"split9x"+std::to_string(i+1));image.grid[i+3]=integer(p,"split9y"+std::to_string(i+1));}
        return image;
    }
};
}

TextureImage decode_texture(std::uint32_t format,std::uint32_t width,std::uint32_t height,const Bytes& pixels,const Bytes& palette,bool masked){
    check(width&&height&&width<=8192&&height<=8192&&std::uint64_t(width)*height<=16*1024*1024,"Texture exceeds image limit");
    auto blocks=((width+3)/4)*((height+3)/4);std::size_t expected=0;
    if(format==0)expected=std::size_t(width)*height;else if(format==5)expected=std::size_t(width)*height*4;else if(format==10)expected=std::size_t(width)*height*2;
    else if(format==3)expected=blocks*8;else if(format==7||format==8)expected=blocks*16;else throw std::runtime_error("Unsupported pixel format "+std::to_string(format));
    check(pixels.size()==expected,"Pixel buffer size mismatch");check(format!=0||palette.size()==1024,"Invalid P8 palette");
    TextureImage out;out.width=width;out.height=height;out.format=format;out.rgba.resize(std::size_t(width)*height*4);
    if(format==0||format==5||format==10){for(std::size_t i=0;i<std::size_t(width)*height;++i){auto d=&out.rgba[i*4];
        if(format==5){d[0]=pixels[i*4+2];d[1]=pixels[i*4+1];d[2]=pixels[i*4];d[3]=pixels[i*4+3];}
        else if(format==0){auto index=pixels[i];d[0]=palette[index*4];d[1]=palette[index*4+1];d[2]=palette[index*4+2];d[3]=masked&&index==0?0:255;}
        else{auto gray=(unsigned(pixels[i*2])|(unsigned(pixels[i*2+1])<<8))>>8;d[0]=d[1]=d[2]=std::uint8_t(gray);d[3]=255;}}
        return out;
    }
    auto rgb=[](unsigned v){auto r=(v>>11)&31,g=(v>>5)&63,b=v&31;return std::array<unsigned,4>{(r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2),255};};
    for(unsigned by=0;by<(height+3)/4;++by)for(unsigned bx=0;bx<(width+3)/4;++bx){
        auto block=&pixels[(by*((width+3)/4)+bx)*(format==3?8:16)];auto c=block+(format==3?0:8);
        unsigned c0=c[0]|c[1]<<8,c1=c[2]|c[3]<<8;std::array<std::array<unsigned,4>,4> colors{rgb(c0),rgb(c1),{}, {}};
        for(unsigned k=0;k<3;++k){colors[2][k]=(colors[0][k]*2+colors[1][k])/3;colors[3][k]=(colors[0][k]+colors[1][k]*2)/3;}colors[2][3]=colors[3][3]=255;
        if(format==3&&c0<=c1){for(unsigned k=0;k<3;++k)colors[2][k]=(colors[0][k]+colors[1][k])/2;colors[3]={0,0,0,0};}
        std::uint32_t indices=std::uint32_t(c[4])|(std::uint32_t(c[5])<<8)|(std::uint32_t(c[6])<<16)|(std::uint32_t(c[7])<<24);
        std::array<unsigned,8> alpha{};std::uint64_t alphaBits=0;
        if(format==8){alpha[0]=block[0];alpha[1]=block[1];if(alpha[0]>alpha[1])for(unsigned j=1;j<=6;++j)alpha[j+1]=((7-j)*alpha[0]+j*alpha[1])/7;
            else{for(unsigned j=1;j<=4;++j)alpha[j+1]=((5-j)*alpha[0]+j*alpha[1])/5;alpha[6]=0;alpha[7]=255;}for(unsigned j=0;j<6;++j)alphaBits|=std::uint64_t(block[j+2])<<(8*j);}
        for(unsigned py=0;py<4;++py)for(unsigned px=0;px<4;++px){unsigned i=py*4+px,x=bx*4+px,y=by*4+py;if(x>=width||y>=height)continue;
            auto value=colors[(indices>>(2*i))&3];if(format==7)value[3]=((block[i/2]>>(4*(i%2)))&15)*17;else if(format==8)value[3]=alpha[(alphaBits>>(3*i))&7];
            auto d=&out.rgba[(std::size_t(y)*width+x)*4];for(unsigned k=0;k<4;++k)d[k]=std::uint8_t(value[k]);}
    }return out;
}

struct TextureStore::Impl {
    std::string directory;std::unordered_map<std::string,std::filesystem::path> files;
    struct Cached {std::shared_ptr<Package> package;std::uintmax_t size;std::filesystem::file_time_type modified;};
    std::unordered_map<std::string,Cached> cache;std::list<std::string> lru;std::size_t bytes=0;std::uint64_t reads=0;mutable std::mutex mutex;
    explicit Impl(const std::string& dir):directory(dir){
        auto root=std::filesystem::u8path(dir);check(std::filesystem::is_directory(root),"Resource directory does not exist");
        std::vector<std::filesystem::path> folders{root};
        auto add=[&](const std::filesystem::path& base){for(const auto& e:std::filesystem::directory_iterator(base))if(e.is_directory()){auto n=lower(e.path().filename().u8string());if(n=="systextures"||n=="textures")folders.push_back(e.path());}};
        add(root);if(lower(root.filename().u8string())=="system")add(root.parent_path());
        for(const auto& folder:folders)for(const auto& e:std::filesystem::directory_iterator(folder))if(e.is_regular_file()&&lower(e.path().extension().u8string())==".utx")files.emplace(lower(e.path().stem().u8string()),e.path());
    }
};
TextureStore::TextureStore(const std::string& directory):impl_(std::make_unique<Impl>(directory)){}
TextureStore::~TextureStore()=default;
TextureImage TextureStore::load(const std::string& reference){
    std::lock_guard<std::mutex> lock(impl_->mutex);auto dot=reference.find('.');check(dot!=std::string::npos,"Texture reference needs a package name");auto name=lower(reference.substr(0,dot));
    auto file=impl_->files.find(name);check(file!=impl_->files.end(),"Texture package not found: "+name);
    auto size=std::filesystem::file_size(file->second);auto modified=std::filesystem::last_write_time(file->second);auto it=impl_->cache.find(name);
    if(it!=impl_->cache.end()&&(it->second.size!=size||it->second.modified!=modified)){impl_->bytes-=it->second.package->data.size();impl_->cache.erase(it);impl_->lru.remove(name);it=impl_->cache.end();}
    if(it==impl_->cache.end()){
        auto package=std::make_shared<Package>(file->second);++impl_->reads;
        while(!impl_->lru.empty()&&impl_->bytes+package->data.size()>PackageBudget){auto old=impl_->lru.back();impl_->lru.pop_back();impl_->bytes-=impl_->cache.at(old).package->data.size();impl_->cache.erase(old);}
        impl_->bytes+=package->data.size();it=impl_->cache.emplace(name,Impl::Cached{package,size,modified}).first;
    }
    impl_->lru.remove(name);impl_->lru.push_front(name);return it->second.package->texture(reference.substr(dot+1));
}
void TextureStore::clear(){std::lock_guard<std::mutex> lock(impl_->mutex);impl_->cache.clear();impl_->lru.clear();impl_->bytes=0;}
std::uint64_t TextureStore::package_reads()const{std::lock_guard<std::mutex> lock(impl_->mutex);return impl_->reads;}

std::vector<std::uint8_t> build_texture_package(const std::string& package,const std::vector<TextureAsset>& assets,const Bytes& guid){
    auto identifier=[](const std::string& s){return !s.empty()&&s.size()<=63&&
        ((s[0]>='A'&&s[0]<='Z')||(s[0]>='a'&&s[0]<='z')||s[0]=='_')&&
        std::all_of(s.begin(),s.end(),[](char c){return (c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_';});};
    check(identifier(package),"Invalid package name");check(!assets.empty()&&assets.size()<=4096,"Invalid asset count");check(guid.size()==16,"Package GUID must have 16 bytes");
    std::vector<std::string> names{"None","Core","Package","Engine","Class","Texture","Format","UBits","VBits","USize","VSize","UClamp","VClamp","bAlphaTexture","bSplit9Texture","Split9X1","Split9X2","Split9X3","Split9Y1","Split9Y2","Split9Y3"};
    std::unordered_map<std::string,int> nameIndex;for(std::size_t i=0;i<names.size();++i)nameIndex[names[i]]=int(i);
    auto ni=[&](const std::string& s){auto it=nameIndex.find(s);if(it!=nameIndex.end())return it->second;int n=int(names.size());names.push_back(s);nameIndex[s]=n;return n;};
    std::vector<std::string> groups;std::set<std::string> seen;
    std::uint64_t pixelBytes=0;
    for(const auto& a:assets){
        check(identifier(a.name)&&lower(a.name)!="none"&&(a.group.empty()||(identifier(a.group)&&lower(a.group)!="none")),"Invalid texture/group name");
        check(seen.insert(lower(a.group+'.'+a.name)).second,"Duplicate texture name");
        check(a.width&&a.height&&a.width<=4096&&a.height<=4096&&!(a.width&(a.width-1))&&!(a.height&(a.height-1)),"Texture dimensions must be powers of two, at most 4096");
        check(a.contentWidth&&a.contentHeight&&a.contentWidth<=a.width&&a.contentHeight<=a.height,"Invalid content rectangle");
        check(a.rgba.size()==std::size_t(a.width)*a.height*4,"Invalid RGBA image size");pixelBytes+=a.rgba.size();check(pixelBytes<=192*1024*1024,"Texture project exceeds package budget");
        for(const auto& group:groups)check(lower(group)!=lower(a.group)||group==a.group,"Inconsistent group spelling");
        ni(a.name);if(!a.group.empty()&&std::find(groups.begin(),groups.end(),a.group)==groups.end()){groups.push_back(a.group);ni(a.group);}
    }
    auto u32=[](Bytes& b,std::uint32_t n){for(unsigned i=0;i<4;++i)b.push_back(std::uint8_t(n>>(8*i)));};
    auto compact=[](Bytes& b,std::int32_t n){auto v=std::uint32_t(n<0?-std::int64_t(n):n);auto c=std::uint8_t((v&63)|(n<0?128:0));v>>=6;b.push_back(c|(v?64:0));while(v){c=std::uint8_t(v&127);v>>=7;b.push_back(c|(v?128:0));}};
    auto string=[&](Bytes& b,const std::string& s){if(s.empty()){compact(b,0);return;}compact(b,std::int32_t(s.size()+1));b.insert(b.end(),s.begin(),s.end());b.push_back(0);};
    Bytes nameTable;for(const auto& name:names){string(nameTable,name);u32(nameTable,0x00070010);}
    Bytes imports;
    auto import=[&](const std::string& cls,int outer,const std::string& name){compact(imports,ni("Core"));compact(imports,ni(cls));u32(imports,std::uint32_t(outer));compact(imports,ni(name));};
    import("Package",0,"Engine");import("Class",-1,"Texture");import("Class",-4,"Package");import("Package",0,"Core");
    struct Export {int cls,outer,name;std::uint32_t flags;std::size_t offset,size;};
    std::vector<Export> exports;Bytes payload;auto payloadBase=64+nameTable.size()+imports.size();
    for(const auto& group:groups){auto offset=payloadBase+payload.size();compact(payload,ni("None"));exports.push_back({-3,0,ni(group),0x00070004,offset,payloadBase+payload.size()-offset});}
    for(const auto& a:assets){
        Bytes object;
        auto byteProp=[&](const std::string& key,unsigned value){compact(object,ni(key));object.push_back(0x01);object.push_back(std::uint8_t(value));};
        auto intProp=[&](const std::string& key,unsigned value){compact(object,ni(key));object.push_back(0x22);u32(object,value);};
        auto boolProp=[&](const std::string& key){compact(object,ni(key));object.push_back(0xd3);object.push_back(0);};
        boolProp("bAlphaTexture");boolProp("bSplit9Texture");
        intProp("Split9X1",0);intProp("Split9X2",a.contentWidth);intProp("Split9X3",a.contentWidth);
        intProp("Split9Y1",0);intProp("Split9Y2",a.contentHeight);intProp("Split9Y3",a.contentHeight);
        byteProp("Format",5);unsigned ub=0,vb=0;while((1u<<ub)<a.width)++ub;while((1u<<vb)<a.height)++vb;
        byteProp("UBits",ub);byteProp("VBits",vb);intProp("USize",a.width);intProp("VSize",a.height);intProp("UClamp",a.width);intProp("VClamp",a.height);compact(object,ni("None"));
        // HF 125/38 simple texture material metadata, same shader as Button_DF.
        u32(object,256);object.insert(object.end(),32,0);compact(object,1);
        string(object,package+'.'+(a.group.empty()?"":a.group+'.')+a.name);object.push_back(0);
        string(object,"float4 texcolor0=tex2D(s[0],tex0);c1=texcolor0;c2=diffuse;a1=texcolor0;a2=diffuse;result.xyz=c1.xyz*c2.xyz*mFactor;result.w=a1.w*a2.w;");u32(object,52822323);
        compact(object,1);auto skipPosition=object.size();u32(object,0);compact(object,std::int32_t(a.rgba.size()));
        for(std::size_t i=0;i<a.rgba.size();i+=4){object.push_back(a.rgba[i+2]);object.push_back(a.rgba[i+1]);object.push_back(a.rgba[i]);object.push_back(a.rgba[i+3]);}
        auto offset=payloadBase+payload.size();auto skip=std::uint32_t(offset+object.size());for(unsigned i=0;i<4;++i)object[skipPosition+i]=std::uint8_t(skip>>(8*i));
        u32(object,a.width);u32(object,a.height);object.push_back(std::uint8_t(ub));object.push_back(std::uint8_t(vb));
        int outer=a.group.empty()?0:int(std::find(groups.begin(),groups.end(),a.group)-groups.begin()+1);
        exports.push_back({-2,outer,ni(a.name),0x000f0004,offset,object.size()});payload.insert(payload.end(),object.begin(),object.end());
    }
    Bytes table;for(const auto& e:exports){compact(table,e.cls);compact(table,0);u32(table,std::uint32_t(e.outer));compact(table,e.name);u32(table,e.flags);compact(table,std::int32_t(e.size));compact(table,std::int32_t(e.offset));}
    Bytes result;u32(result,0x9e2a83c1);u32(result,125|(38u<<16));u32(result,1);
    u32(result,unsigned(names.size()));u32(result,64);u32(result,unsigned(exports.size()));u32(result,unsigned(payloadBase+payload.size()));u32(result,4);u32(result,unsigned(64+nameTable.size()));
    result.insert(result.end(),guid.begin(),guid.end());u32(result,1);u32(result,unsigned(exports.size()));u32(result,unsigned(names.size()));
    result.insert(result.end(),nameTable.begin(),nameTable.end());result.insert(result.end(),imports.begin(),imports.end());result.insert(result.end(),payload.begin(),payload.end());result.insert(result.end(),table.begin(),table.end());
    check(result.size()<=MaxPackage,"Texture package too large");
    Bytes encrypted;for(char c:std::string("Lineage2Ver121")){encrypted.push_back(std::uint8_t(c));encrypted.push_back(0);}unsigned key=0;for(unsigned char c:lower(package+".utx"))key+=c;
    for(auto b:result)encrypted.push_back(b^std::uint8_t(key));
    return encrypted;
}
}
