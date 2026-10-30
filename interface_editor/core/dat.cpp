// Lineage DAT framing and SysString codec. Format/key attribution: LICENSE.dat-format.
// Crypto primitives use the stable public OpenSSL 3 ABI; compression uses zlib.
#include "dat.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <codecvt>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <locale>
#include <memory>
#include <stdexcept>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#include <iconv.h>
#endif

namespace interface_editor {
namespace {
constexpr std::size_t Limit=64*1024*1024;
void need(bool ok,const std::string& message){if(!ok)throw std::runtime_error(message);}
std::filesystem::path path(const std::string& value){return std::filesystem::u8path(value);}
std::uint32_t read32(const Bytes& b,std::size_t& p){need(p<=b.size()&&b.size()-p>=4,"Unexpected end of DAT");std::uint32_t n=0;for(unsigned i=0;i<4;++i)n|=std::uint32_t(b[p++])<<(8*i);return n;}
void put32(Bytes& b,std::uint32_t value){for(unsigned i=0;i<4;++i)b.push_back(std::uint8_t(value>>(8*i)));}
std::int32_t readIndex(const Bytes& b,std::size_t& p){need(p<b.size(),"ASCF length is truncated");auto first=b[p++];std::uint32_t n=first&63;bool more=first&64;unsigned shift=6;
    for(unsigned i=1;more&&i<5;++i){need(p<b.size(),"ASCF length is truncated");auto c=b[p++];need(i!=4||(c&0xe0)==0,"ASCF length overflow");n|=std::uint32_t(c&(i==4?31:127))<<shift;shift+=7;more=i<4&&(c&128);}
    need(n<=INT32_MAX,"ASCF length overflow");return first&128?-std::int32_t(n):std::int32_t(n);}
void putIndex(Bytes& b,std::int32_t value){auto n=std::uint32_t(value<0?-std::int64_t(value):value);auto first=std::uint8_t((n&63)|(value<0?128:0));n>>=6;b.push_back(first|(n?64:0));while(n){auto c=n&127;n>>=7;b.push_back(std::uint8_t(c|(n?128:0)));}}
Bytes readFile(const std::string& filename){std::ifstream f(path(filename),std::ios::binary|std::ios::ate);need(bool(f),"Cannot open SysString: "+filename);auto size=f.tellg();need(size>=0&&std::uint64_t(size)<=Limit*2,"DAT file is too large");Bytes b(static_cast<std::size_t>(size));f.seekg(0);f.read(reinterpret_cast<char*>(b.data()),size);need(bool(f),"Cannot read SysString");return b;}
std::string hex(const Bytes& data){static const char chars[]="0123456789abcdef";std::string s;for(auto v:data){s+=chars[v>>4];s+=chars[v&15];}return s;}

// Only public opaque BN handles and the documented BF_KEY structure are used.
struct Bignum;struct BnContext;
struct BlowfishKey {std::uint32_t p[18],s[1024];};
class Library {
    void* handle_=nullptr;
public:
    explicit Library(bool crypto){
#ifdef _WIN32
        auto name=crypto?L"libcrypto-3.dll":L"zlib1.dll";
        std::vector<std::filesystem::path> folders;
        wchar_t buf[32768];
        auto add=[&](HMODULE h){auto n=GetModuleFileNameW(h,buf,32768);if(n&&n<32768){auto parent=std::filesystem::path(buf).parent_path();folders.push_back(parent);folders.push_back(parent/L"DLLs");}};
        add(nullptr);
        for(const auto* python:{L"python312.dll",L"python3.dll"})if(auto h=GetModuleHandleW(python))add(h);
        if(auto h=GetModuleHandleW(name))add(h);
        static int anchor;
        HMODULE self=nullptr;
        if(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(&anchor),&self)){
            auto n=GetModuleFileNameW(self,buf,32768);if(n&&n<32768){auto app=std::filesystem::path(buf).parent_path();folders.push_back(app);folders.push_back(app.parent_path()/L"runtime");folders.push_back(app.parent_path()/L"third_party/windows");}
        }
        for(const auto& folder:folders){auto file=folder/name;if(std::filesystem::is_regular_file(file)){handle_=reinterpret_cast<void*>(LoadLibraryExW(file.c_str(),nullptr,LOAD_WITH_ALTERED_SEARCH_PATH));if(handle_)break;}}
#else
        handle_=dlopen(crypto?"libcrypto.so.3":"libz.so.1",RTLD_NOW|RTLD_LOCAL);
#endif
        need(handle_!=nullptr,crypto?"OpenSSL 3 runtime was not found":"zlib runtime was not found");
        // These two process-wide dependencies remain loaded until process exit.
    }
    template<class T>T symbol(const char* name){
#ifdef _WIN32
        auto address=reinterpret_cast<void*>(GetProcAddress(reinterpret_cast<HMODULE>(handle_),name));
#else
        auto address=dlsym(handle_,name);
#endif
        need(address!=nullptr,std::string("Missing codec library symbol: ")+name);return reinterpret_cast<T>(address);
    }
};
struct Crypto {
    Library library{true};
    Bignum* (*create)()=library.symbol<Bignum*(*)()>("BN_new");
    void (*free)(Bignum*)=library.symbol<void(*)(Bignum*)>("BN_free");
    int (*hex2bn)(Bignum**,const char*)=library.symbol<int(*)(Bignum**,const char*)>("BN_hex2bn");
    Bignum* (*fromBytes)(const unsigned char*,int,Bignum*)=library.symbol<Bignum*(*)(const unsigned char*,int,Bignum*)>("BN_bin2bn");
    int (*toBytes)(const Bignum*,unsigned char*,int)=library.symbol<int(*)(const Bignum*,unsigned char*,int)>("BN_bn2binpad");
    int (*cmp)(const Bignum*,const Bignum*)=library.symbol<int(*)(const Bignum*,const Bignum*)>("BN_cmp");
    BnContext* (*context)()=library.symbol<BnContext*(*)()>("BN_CTX_new");
    void (*freeContext)(BnContext*)=library.symbol<void(*)(BnContext*)>("BN_CTX_free");
    int (*power)(Bignum*,const Bignum*,const Bignum*,const Bignum*,BnContext*)=library.symbol<int(*)(Bignum*,const Bignum*,const Bignum*,const Bignum*,BnContext*)>("BN_mod_exp");
    void (*bfKey)(BlowfishKey*,int,const unsigned char*)=library.symbol<void(*)(BlowfishKey*,int,const unsigned char*)>("BF_set_key");
    void (*bfEncrypt)(std::uint32_t*,const BlowfishKey*)=library.symbol<void(*)(std::uint32_t*,const BlowfishKey*)>("BF_encrypt");
    void (*bfDecrypt)(std::uint32_t*,const BlowfishKey*)=library.symbol<void(*)(std::uint32_t*,const BlowfishKey*)>("BF_decrypt");
};
Crypto& crypto(){static Crypto api;return api;}
struct Zlib {
    Library library{false};
    unsigned long (*bound)(unsigned long)=library.symbol<unsigned long(*)(unsigned long)>("compressBound");
    int (*compress)(unsigned char*,unsigned long*,const unsigned char*,unsigned long,int)=library.symbol<int(*)(unsigned char*,unsigned long*,const unsigned char*,unsigned long,int)>("compress2");
    int (*uncompress)(unsigned char*,unsigned long*,const unsigned char*,unsigned long*)=library.symbol<int(*)(unsigned char*,unsigned long*,const unsigned char*,unsigned long*)>("uncompress2");
    unsigned long (*crc)(unsigned long,const unsigned char*,unsigned int)=library.symbol<unsigned long(*)(unsigned long,const unsigned char*,unsigned int)>("crc32");
};
Zlib& zlib(){static Zlib api;return api;}
std::uint32_t checksum(const Bytes& b){return std::uint32_t(zlib().crc(0,b.data(),static_cast<unsigned>(b.size())));}

struct RsaProfile{std::string name,n,decode,encode;int version;};
std::vector<RsaProfile>& profiles(){static std::vector<RsaProfile> values{
    {"l2encdec","75b4d6de5c016544068a1acf125869f43d2e09fc55b8b1e289556daf9b8757635593446288b3653da1ce91c87bb1a5c18f16323495c55d7d72c0890a83f69bfd1fd9434eb1c02f3e4679edfa43309319070129c267c85604d87bb65bae205de3707af1d2108881abb567c3b3d069ae67c3a4c6a3aa93d26413d4c66094ae2039","1d","30b4c2d798d47086145c75063c8e841e719776e400291d7838d3e6c4405b504c6a07f8fca27f32b86643d2649d1d5f124cdd0bf272f0909dd7352fe10a77b34d831043d9ae541f8263c6fe3d1c14c2f04e43a7253a6dda9a8c1562cbd493c1b631a1957618ad5dfe5ca28553f746e2fc6f2db816c7db223ec91e955081c1de65",0},
    {"original-411","8c9d5da87b30f5d7cd9dc88c746eaac5bb180267fa11737358c4c95d9adf59dd37689f9befb251508759555d6fe0eca87bebe0a10712cf0ec245af84cd22eb4cb675e98eaf5799fca62a20a2baa4801d5d70718dcd43283b8428f1387aec6600f937bfc7bb72404d187d3a9c438f1ffce9ce365dccf754232ff6def038a41385","1d","",411},
    {"original-412","a465134799cf2c45087093e7d0f0f144e6d528110c08f674730d436e40827330eccea46e70acf10cdda7d8f710e3b44dcca931812d76cd7494289bca8b73823f57efc0515b97e4a2a02612ccfa719cf7885104b06f2e7e2cc967b62e3d3b1aadb925db94cbc8cd3070a4bb13f7e202c7733a67b1b94c1ebc0afcbe1a63b448cf","25","",412},
    {"original-413","97df398472ddf737ef0a0cd17e8d172f0fef1661a38a8ae1d6e829bc1c6e4c3cfc19292dda9ef90175e46e7394a18850b6417d03be6eea274d3ed1dde5b5d7bde72cc0a0b71d03608655633881793a02c9a67d9ef2b45eb7c08d4be329083ce450e68f7867b6749314d40511d09bc5744551baa86a89dc38123dc1668fd72d83","35","",413},
    {"original-414","ad70257b2316ce09dfaf2ebc3f63b3d673b0c98a403950e26bb87379b11e17aed0e45af23e7171e5ec1fbc8d1ae32ffb7801b31266eef9c334b53469d4b7cbe83284273d35a9aab49b453e7012f374496c65f8089f5d134b0eb3d1e3b22051ed5977a6dd68c4f85785dfcc9f4412c81681944fc4b8ce27caf0242deaa5762e8d","25","",414}
};return values;}
std::mutex& profileMutex(){static std::mutex mutex;return mutex;}
std::vector<RsaProfile> allProfiles(){std::lock_guard<std::mutex> lock(profileMutex());return profiles();}
RsaProfile profileFor(const std::string& name,int version){for(const auto& p:allProfiles())if(p.name==name&&(p.version==0||p.version==version))return p;throw std::runtime_error("Unknown/mismatched RSA profile: "+name);}
bool writable(int version,const std::string& profile){return version<411||!profileFor(profile,version).encode.empty();}

Bytes rsa(const Bytes& data,const RsaProfile& profile,bool encode){
    need(data.size()%128==0,"Truncated RSA block");auto& api=crypto();Bignum *n=nullptr,*e=nullptr;
    using Number=std::unique_ptr<Bignum,void(*)(Bignum*)>;
    need(api.hex2bn(&n,profile.n.c_str())>0,"Invalid RSA modulus");Number modulus(n,api.free);
    const auto& exponent=encode?profile.encode:profile.decode;need(!exponent.empty(),"This RSA profile is decode-only; explicitly select a compatible write profile");
    need(api.hex2bn(&e,exponent.c_str())>0,"Invalid RSA exponent");Number exp(e,api.free),input(api.create(),api.free),output(api.create(),api.free);
    std::unique_ptr<BnContext,void(*)(BnContext*)> context(api.context(),api.freeContext);need(input&&output&&context,"RSA allocation failed");
    Bytes result(data.size());
    for(std::size_t p=0;p<data.size();p+=128){need(api.fromBytes(data.data()+p,128,input.get())!=nullptr&&api.cmp(input.get(),modulus.get())<0,"RSA block exceeds modulus");
        need(api.power(output.get(),input.get(),exp.get(),modulus.get(),context.get())==1,"RSA transform failed");need(api.toBytes(output.get(),result.data()+p,128)==128,"RSA output failed");}
    return result;
}
Bytes blowfish(Bytes data,int version,bool encode,bool pad=true){
    if(encode&&pad)data.resize((data.size()+7)/8*8,0);
    auto key=version==211?std::string("31==-%&@!^+][;'.]94-"):std::string("[;'.]94-&@%!^+]-31==");key.push_back('\0');
    auto& api=crypto();BlowfishKey schedule{};api.bfKey(&schedule,int(key.size()),reinterpret_cast<const unsigned char*>(key.data()));
    Bytes result;result.reserve(data.size());
    std::size_t pos=0;while(data.size()-pos>=8){std::uint32_t words[2]{read32(data,pos),read32(data,pos)};(encode?api.bfEncrypt:api.bfDecrypt)(words,&schedule);put32(result,words[0]);put32(result,words[1]);}
    result.insert(result.end(),data.begin()+pos,data.end()); // legacy l2encdec leaves a partial final block clear
    return result;
}
int detect(const Bytes& b){
    const std::string prefix="Lineage2Ver";bool matches=b.size()>=22;
    for(unsigned i=0;matches&&i<prefix.size();++i)matches=b[i*2]==std::uint8_t(prefix[i])&&b[i*2+1]==0;
    if(!matches)return 0;
    need(b.size()>=28,"Truncated Lineage DAT header");int version=0;
    for(unsigned i=11;i<14;++i){need(b[i*2]>='0'&&b[i*2]<='9'&&b[i*2+1]==0,"Invalid Lineage DAT header");version=version*10+b[i*2]-'0';}
    need(version==111||version==120||version==121||version==211||version==212||(version>=411&&version<=414),"Unsupported DAT envelope: "+std::to_string(version));return version;
}
unsigned filenameKey(const std::string& filename){unsigned value=0;for(unsigned char c:path(filename).filename().u8string()){need(c<128,"Ver121 requires an ASCII basename (directory names may be Unicode)");if(c>='A'&&c<='Z')c+=32;value+=c;}return value&255;}
Bytes xorData(Bytes b,int version,const std::string& filename){auto fixed=version==111?0xac:version==121?filenameKey(filename):0;for(std::size_t i=0;i<b.size();++i){auto n=unsigned(i+0xe6);auto key=version==120?((((n>>4)&15)^((n>>12)&15))<<4)|((n&15)^((n>>8)&15)):fixed;b[i]^=std::uint8_t(key);}return b;}
std::string decodeAnsi(const std::string& input,const std::string& encoding){
    need(encoding=="cp1252"||encoding=="cp1251"||encoding=="cp949"||encoding=="cp932"||encoding=="cp936"||encoding=="cp950"||encoding=="utf-8"||encoding=="latin1","Unsupported ANSI encoding");
    if(input.empty())return {};
#ifdef _WIN32
    UINT page=encoding=="cp1252"?1252:encoding=="cp1251"?1251:encoding=="cp949"?949:encoding=="cp932"?932:encoding=="cp936"?936:encoding=="cp950"?950:encoding=="latin1"?28591:CP_UTF8;
    int size=MultiByteToWideChar(page,MB_ERR_INVALID_CHARS,input.data(),int(input.size()),nullptr,0);need(size>0,"Invalid encoded ASCF string");
    std::wstring wide(size,L'\0');need(MultiByteToWideChar(page,MB_ERR_INVALID_CHARS,input.data(),int(input.size()),wide.data(),size)==size,"ASCF decode failed");
    std::u16string text(wide.begin(),wide.end());return std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.to_bytes(text);
#else
    const char* name=encoding=="latin1"?"ISO-8859-1":encoding.c_str();auto handle=iconv_open("UTF-8",name);need(handle!=reinterpret_cast<iconv_t>(-1),"Encoding is unavailable");
    std::string output(input.size()*4+4,'\0');char* in=const_cast<char*>(input.data());char* out=output.data();std::size_t left=input.size(),space=output.size();
    auto result=iconv(handle,&in,&left,&out,&space);iconv_close(handle);need(result!=std::size_t(-1)&&left==0,"Invalid encoded ASCF string");output.resize(output.size()-space);return output;
#endif
}
std::string readString(const Bytes& data,std::size_t& pos,const std::string& encoding){
    auto n=readIndex(data,pos);if(!n)return {};auto bytes=std::size_t(n<0?-std::int64_t(n)*2:n);need(bytes<=Limit&&pos<=data.size()&&bytes<=data.size()-pos,"Truncated ASCF string");auto start=pos;pos+=bytes;
    need(data[pos-1]==0&&(n>0||data[pos-2]==0),"Missing ASCF terminator");
    std::string text;if(n>0)text=decodeAnsi(std::string(data.begin()+start,data.begin()+pos-1),encoding);
    else{std::u16string s;for(auto i=start;i+2<pos;i+=2)s.push_back(char16_t(data[i]|(data[i+1]<<8)));text=std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.to_bytes(s);}
    need(text.find('\0')==std::string::npos,"Embedded NUL in SysString");return text;
}
void putString(Bytes& out,const std::string& text){
    need(text.size()<=1024*1024&&text.find('\0')==std::string::npos,"Invalid/oversized SysString text");
    if(text.empty()){putIndex(out,0);return;}
    if(std::all_of(text.begin(),text.end(),[](unsigned char c){return c<128;})){putIndex(out,int(text.size()+1));out.insert(out.end(),text.begin(),text.end());out.push_back(0);}
    else{auto wide=std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.from_bytes(text);putIndex(out,-int(wide.size()+1));for(auto c:wide){out.push_back(c&255);out.push_back(c>>8);}out.push_back(0);out.push_back(0);}
}
void atomicWrite(const std::string& filename,const Bytes& data){
    auto target=path(filename),temp=target;temp+=".tmp-dat-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());auto backupTemp=temp;backupTemp+=".bak";
    auto replace=[](const auto& source,const auto& dest){
#ifdef _WIN32
        if(!MoveFileExW(source.c_str(),dest.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))throw std::runtime_error("Cannot replace DAT/backup, Win32 error "+std::to_string(GetLastError()));
#else
        std::filesystem::rename(source,dest);
#endif
    };
    try {std::ofstream f(temp,std::ios::binary|std::ios::trunc);need(bool(f),"Cannot create DAT temporary file");f.write(reinterpret_cast<const char*>(data.data()),static_cast<std::streamsize>(data.size()));f.flush();need(bool(f),"DAT write failed");f.close();need(readFile(temp.u8string())==data,"Written DAT differs from snapshot");
        if(std::filesystem::exists(target)){auto backup=target;backup+=".bak";
#ifdef _WIN32
            need(CopyFileW(target.c_str(),backupTemp.c_str(),TRUE)!=0,"Cannot stage DAT backup");
#else
            std::filesystem::copy_file(target,backupTemp);
#endif
            replace(backupTemp,backup);
        }replace(temp,target);
    }catch(...){std::error_code e;std::filesystem::remove(temp,e);std::filesystem::remove(backupTemp,e);throw;}
}
}

Json dat_codecs(){Json result=Json::array();for(int version:{0,111,120,121,211,212,411,412,413,414}){
    if(version<411){result.push_back(Json{{"version",version},{"profile",version?"standard":"plain"},{"read",true},{"write",true}});if(version==211||version==212)result.push_back(Json{{"version",version},{"profile","blowfish-partial"},{"read",true},{"write",true}});}
    else for(const auto& p:allProfiles())if(!p.version||p.version==version)result.push_back(Json{{"version",version},{"profile",p.name},{"read",true},{"write",!p.encode.empty()}});
}return result;}
Json sysstring_schemas(){return Json::array({Json{{"id","id-ascf-v1"},{"name","SysString: uint32 ID + ASCF"},{"layout","uint32 count; repeated uint32 id + compact ASCII/UTF-16 string; opaque tail"},{"presets",Json::array({"C3","Interlude","Freya","High Five","Lindvior","Helios","Grand Crusade"})}}});}
void register_dat_profile(const Json& p){auto name=p.at("name").get<std::string>();auto n=p.at("modulus").get<std::string>();auto d=p.at("decode_exponent").get<std::string>();auto e=p.value("encode_exponent",std::string());int version=p.at("version");
    auto hexadecimal=[](const std::string& s){return !s.empty()&&s.size()<=256&&std::all_of(s.begin(),s.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F');});};
    need(name.rfind("custom-",0)==0&&name.size()<=64&&n.size()==256&&hexadecimal(n)&&hexadecimal(d)&&(e.empty()||hexadecimal(e))&&version>=411&&version<=414,"Invalid custom RSA profile");
    need(n.find_first_not_of('0')!=std::string::npos&&d.find_first_not_of('0')!=std::string::npos&&(e.empty()||e.find_first_not_of('0')!=std::string::npos),"Invalid zero RSA parameter");
    std::lock_guard<std::mutex> lock(profileMutex());for(const auto& existing:profiles())if(existing.name==name){need(existing.n==n&&existing.decode==d&&existing.encode==e&&existing.version==version,"Profile name is already used");return;}profiles().push_back({name,n,d,e,version});
}
DatDecoded decode_dat(const Bytes& bytes,const std::string& filename,const std::string& profile){
    need(bytes.size()<=Limit*2,"DAT too large");DatDecoded out;out.version=detect(bytes);
    if(!out.version){need(profile=="plain","No DAT header: explicitly choose the plain profile");out.profile="plain";out.payload=bytes;return out;}
    need(profile!="plain","The file has an encrypted DAT header");std::size_t end=bytes.size();
    if(end>=48&&std::all_of(bytes.end()-20,bytes.end()-8,[](auto c){return c==0;})&&std::all_of(bytes.end()-4,bytes.end(),[](auto c){return c==0;})){
        std::size_t p=end-8;auto expected=read32(bytes,p);Bytes body(bytes.begin(),bytes.end()-20);need(checksum(body)==expected,"DAT footer CRC32 mismatch");out.footer=true;end-=20;
    }
    Bytes body(bytes.begin()+28,bytes.begin()+end);
    if(out.version<200){out.payload=xorData(body,out.version,filename);out.profile="standard";return out;}
    if(out.version<400){out.payload=blowfish(body,out.version,false);out.profile=body.size()%8||profile=="blowfish-partial"?"blowfish-partial":"standard";return out;}
    need(!body.empty()&&body.size()%128==0,"Truncated RSA DAT or unsupported footer");
    std::vector<RsaProfile> candidates;
    if(profile=="auto"){for(const auto& p:allProfiles())if(!p.version||p.version==out.version)candidates.push_back(p);}
    else candidates.push_back(profileFor(profile=="original"?"original-"+std::to_string(out.version):profile,out.version));
    for(const auto& p:candidates){try{
        auto blocks=rsa(body,p,false);Bytes packed;
        for(std::size_t i=0;i<blocks.size();i+=128){auto size=blocks[i+3];need(size>0&&size<=124,"Invalid RSA block size");auto start=128-size-((124-size)%4);packed.insert(packed.end(),blocks.begin()+i+start,blocks.begin()+i+start+size);}
        std::size_t pos=0;auto size=read32(packed,pos);need(size>0&&size<=Limit,"Invalid decompressed DAT size");Bytes payload(size);unsigned long length=size,used=static_cast<unsigned long>(packed.size()-4);
        need(zlib().uncompress(payload.data(),&length,packed.data()+4,&used)==0&&length==size,"DAT zlib validation failed");
        out.payload=std::move(payload);out.profile=p.name;out.compressedSuffix=Bytes(packed.begin()+4+used,packed.end());return out;
    }catch(const std::exception&){if(profile!="auto")throw;}}
    throw std::runtime_error("No RSA profile could decode and validate this DAT");
}
Bytes encode_dat(const Bytes& payload,const std::string& filename,int version,const std::string& profile,bool footer,const Bytes& suffix){
    need(!payload.empty()&&payload.size()<=Limit,"Invalid DAT payload size");
    if(!version){need(suffix.empty(),"Cannot convert an RSA suffix to plain");return payload;}
    Bytes output;for(char c:std::string("Lineage2Ver")+std::to_string(version)){output.push_back(std::uint8_t(c));output.push_back(0);}need(detect(output)==version,"Invalid output envelope");Bytes body;
    if(version<200){need(suffix.empty(),"Cannot convert an RSA suffix to XOR");body=xorData(payload,version,filename);}
    else if(version<400){need(suffix.empty(),"Cannot convert an RSA suffix to Blowfish");body=blowfish(payload,version,true,profile!="blowfish-partial");}
    else {auto p=profileFor(profile,version);need(!p.encode.empty(),"Selected RSA profile is decode-only");unsigned long size=zlib().bound(static_cast<unsigned long>(payload.size()));Bytes compressed(size);
        need(zlib().compress(compressed.data(),&size,payload.data(),static_cast<unsigned long>(payload.size()),9)==0,"DAT compression failed");compressed.resize(size);Bytes packed;put32(packed,std::uint32_t(payload.size()));packed.insert(packed.end(),compressed.begin(),compressed.end());packed.insert(packed.end(),suffix.begin(),suffix.end());Bytes blocks;
        for(std::size_t i=0;i<packed.size();i+=124){auto count=std::min<std::size_t>(124,packed.size()-i);std::array<std::uint8_t,128> block{};block[3]=std::uint8_t(count);auto start=128-count-((124-count)%4);std::copy_n(packed.begin()+i,count,block.begin()+start);blocks.insert(blocks.end(),block.begin(),block.end());}body=rsa(blocks,p,true);
    }
    output.insert(output.end(),body.begin(),body.end());if(footer){auto crc=checksum(output);output.insert(output.end(),12,0);put32(output,crc);output.insert(output.end(),4,0);}return output;
}

void SysStrings::parse(const DatDecoded& decoded,const std::string& encoding){
    need(decoded.payload.size()<=Limit,"SysString too large");std::size_t pos=0;auto count=read32(decoded.payload,pos);need(count<=1000000&&count<=decoded.payload.size()/5,"Invalid SysString row count");
    for(unsigned i=0;i<count;++i){Row row;row.id=read32(decoded.payload,pos);auto start=pos;row.text=readString(decoded.payload,pos,encoding);row.raw=Bytes(decoded.payload.begin()+start,decoded.payload.begin()+pos);need(!index_.count(row.id),"Duplicate SysString ID "+std::to_string(row.id));index_[row.id]=rows_.size();rows_.push_back(std::move(row));}
    tail_=Bytes(decoded.payload.begin()+pos,decoded.payload.end());
    if((decoded.version==211||decoded.version==212)&&decoded.profile!="blowfish-partial"){const Bytes marker{12,'S','a','f','e','P','a','c','k','a','g','e',0};std::size_t keep=0;
        if(tail_.size()>=marker.size()&&std::equal(marker.begin(),marker.end(),tail_.begin()))keep=marker.size();
        if(tail_.size()-keep<=7&&std::all_of(tail_.begin()+keep,tail_.end(),[](auto b){return b==0;}))tail_.resize(keep);
        else ambiguousPadding_=true;
    }
}
void SysStrings::load(const std::string& file,const std::string& schema,const std::string& encoding,const std::string& profile){load_bytes(readFile(file),file,schema,encoding,profile);}
void SysStrings::load_bytes(const Bytes& data,const std::string& filename,const std::string& schema,const std::string& encoding,const std::string& profile){
    std::lock_guard<std::recursive_mutex> lock(mutex_);need(schema=="id-ascf-v1","Unsupported SysString schema");decodeAnsi("check",encoding);
    auto decoded=decode_dat(data,filename,profile);SysStrings staged;staged.parse(decoded,encoding);
    rows_=std::move(staged.rows_);index_=std::move(staged.index_);tail_=std::move(staged.tail_);ambiguousPadding_=staged.ambiguousPadding_;
    original_=data;packedSuffix_=decoded.compressedSuffix;file_=filename;schema_=schema;encoding_=encoding;version_=decoded.version;profile_=decoded.profile;footer_=decoded.footer;loaded_=true;
    undo_.clear();redo_.clear();state_=savedState_=nextState_=0;++revision_;
}
Json SysStrings::summary()const{std::lock_guard<std::recursive_mutex> lock(mutex_);return Json{{"file",file_},{"schema",schema_},{"encoding",encoding_},{"version",version_},{"profile",profile_},{"rows",rows_.size()},
    {"dirty",state_!=savedState_},{"revision",revision_},{"undo",undo_.size()},{"redo",redo_.size()},{"footer_crc",footer_},{"table_tail_hex",hex(tail_)},{"compressed_suffix_bytes",packedSuffix_.size()},
    {"can_encode",loaded_&&!ambiguousPadding_&&writable(version_,profile_)},{"ambiguous_padding",ambiguousPadding_}};}
Json SysStrings::rows()const{std::lock_guard<std::recursive_mutex> lock(mutex_);Json result=Json::array();for(const auto& row:rows_)result.push_back(Json{{"id",row.id},{"text",row.text}});return result;}
Json SysStrings::snapshot()const{std::lock_guard<std::recursive_mutex> lock(mutex_);Json result=Json::object();for(const auto& row:rows_)result[std::to_string(row.id)]=row.text;return Json{{"revision",revision_},{"strings",std::move(result)}};}
Json SysStrings::lookup(std::uint32_t id)const{std::lock_guard<std::recursive_mutex> lock(mutex_);auto i=index_.find(id);return i==index_.end()?Json(nullptr):Json(rows_[i->second].text);}
std::uint32_t SysStrings::next_id()const{std::lock_guard<std::recursive_mutex> lock(mutex_);std::uint32_t result=1;for(const auto& entry:index_)if(entry.first<INT32_MAX)result=std::max(result,entry.first+1);if(result==INT32_MAX){result=1;while(index_.count(result)&&result<INT32_MAX)++result;}need(result<INT32_MAX,"No available UI string ID");return result;}
void SysStrings::reindex(){index_.clear();for(std::size_t i=0;i<rows_.size();++i)index_[rows_[i].id]=i;}
void SysStrings::apply(const Change& c,bool forward){if(c.added){if(forward)rows_.insert(rows_.begin()+static_cast<std::ptrdiff_t>(c.index),c.after);else rows_.erase(rows_.begin()+static_cast<std::ptrdiff_t>(c.index));}else rows_[c.index]=forward?c.after:c.before;state_=forward?c.afterState:c.beforeState;reindex();++revision_;}
void SysStrings::add(std::uint32_t id,const std::string& text){std::lock_guard<std::recursive_mutex> lock(mutex_);need(loaded_,"No SysString loaded");need(!index_.count(id),"SysString ID already exists");need(rows_.size()<1000000,"Too many rows");Bytes check;putString(check,text);Change c{rows_.size(),true,{},Row{id,text,{}},state_,++nextState_};apply(c,true);undo_.push_back(c);redo_.clear();}
void SysStrings::set(std::uint32_t id,const std::string& text){std::lock_guard<std::recursive_mutex> lock(mutex_);auto found=index_.find(id);need(found!=index_.end(),"SysString ID not found");auto& row=rows_[found->second];if(row.text==text)return;Bytes check;putString(check,text);Change c{found->second,false,row,Row{id,text,{}},state_,++nextState_};apply(c,true);undo_.push_back(c);redo_.clear();}
bool SysStrings::undo(){std::lock_guard<std::recursive_mutex> lock(mutex_);if(undo_.empty())return false;auto c=undo_.back();undo_.pop_back();apply(c,false);redo_.push_back(c);return true;}
bool SysStrings::redo(){std::lock_guard<std::recursive_mutex> lock(mutex_);if(redo_.empty())return false;auto c=redo_.back();redo_.pop_back();apply(c,true);undo_.push_back(c);return true;}
Bytes SysStrings::payload()const{std::lock_guard<std::recursive_mutex> lock(mutex_);need(loaded_,"No SysString loaded");Bytes data;put32(data,std::uint32_t(rows_.size()));for(const auto& row:rows_){put32(data,row.id);if(row.raw.empty())putString(data,row.text);else data.insert(data.end(),row.raw.begin(),row.raw.end());need(data.size()<=Limit,"SysString too large");}data.insert(data.end(),tail_.begin(),tail_.end());return data;}
Bytes SysStrings::encoded(const std::string& filename,int version,const std::string& profile)const{
    std::lock_guard<std::recursive_mutex> lock(mutex_);need(loaded_,"No SysString loaded");need(!ambiguousPadding_,"Unknown Blowfish suffix: cannot separate data from padding");
    int target=version<0?version_:version;std::string key=profile=="preserve"?profile_:profile;
    if(target>=411&&key=="standard")throw std::runtime_error("Explicitly choose an RSA write profile");
    if(target>=411&&!writable(target,key)){
        need(target==version_&&key==profile_&&state_==savedState_,"Original RSA profile is decode-only; explicitly choose a compatible write profile");return original_;
    }
    return encode_dat(payload(),filename,target,key,target? (target==version_?footer_:true):false,packedSuffix_);
}
void SysStrings::save(const std::string& filename,int version,const std::string& profile){
    std::lock_guard<std::recursive_mutex> lock(mutex_);auto bytes=encoded(filename,version,profile);auto target=version<0?version_:version;auto key=profile=="preserve"?profile_:profile;
    SysStrings verify;verify.load_bytes(bytes,filename,schema_,encoding_,target==0?"plain":key);need(verify.payload()==payload(),"SysString save verification failed");
    atomicWrite(filename,bytes);original_=bytes;file_=filename;version_=verify.version_;profile_=(target==211||target==212)&&key=="blowfish-partial"?key:verify.profile_;footer_=verify.footer_;packedSuffix_=verify.packedSuffix_;savedState_=state_;
}
}
