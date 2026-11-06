#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Context ctx(argv[1],{});auto& p=*ctx.main;p.names={"None","Tint","Color","Settings","Nested","Count","Enabled"};
        auto generate=[&](const ue::Bytes& tags){
            p.data.resize(36);p.exports.clear();p.children.clear();ue::Bytes cls(65,0);cls.insert(cls.end(),tags.begin(),tags.end());
            ue::Entry e;e.name="DefaultProbe";e.offset=p.data.size();e.size=cls.size();p.exports.push_back(e);p.data.insert(p.data.end(),cls.begin(),cls.end());
            return ctx.decompile(1,true);
        };
        auto r=generate({1,0x2a,2,65,33,17,129,0});
        check(r["status"]=="recovered","Color fixture not recovered");
        check(r["code"].get<std::string>().find("Tint=(B=65,G=33,R=17,A=129)")!=std::string::npos,"Color channel order or struct separators changed");
        // Nested tagged structure: int Count=37, bool Enabled=true, terminator.
        r=generate({3,0x5a,4,9,5,0x22,37,0,0,0,6,0x83,0,0});
        check(r["status"]=="recovered","Nested fixture not recovered");
        check(r["code"].get<std::string>().find("Settings=(Count=37,Enabled=True)")!=std::string::npos,"Nested defaults changed");
        r=generate({1,0x2a,2,65,33,17});
        check(r["status"]=="partial"&&r.contains("class_tail_hex"),"Truncated color not preserved");
        r=generate({3,0x5a,4,6,5,0x22,37,0,0,0,0});
        check(r["status"]=="partial","Nested structure without terminator accepted");
        r=generate({1,0x07,99,0});
        check(r["status"]=="partial"&&r["unrecovered_defaults"][0]["raw_hex"]=="63","Unknown default raw data lost");
        std::filesystem::remove(argv[1]);std::cout<<"Default decoding and malformed payload checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
