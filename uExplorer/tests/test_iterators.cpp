#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static void u32(ue::Bytes& b,unsigned v){for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i)));}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Context ctx(argv[1],{});auto& p=*ctx.main;p.names={"None","Each","Run"};
        ue::Entry imported;imported.name="Function";imported.importClass="Class";p.imports.push_back(imported);
        auto generate=[&](const ue::Bytes& script,int size){
            p.exports.clear();p.children.clear();p.data.resize(36);
            ue::Entry owner;owner.name="Probe";owner.offset=p.data.size();owner.size=66;p.exports.push_back(owner);p.data.resize(p.data.size()+66);
            ue::Bytes fn{0,0,0,0,0,2,0};fn.resize(fn.size()+8);u32(fn,size);fn.insert(fn.end(),script.begin(),script.end());fn.insert(fn.end(),3,0);u32(fn,2);
            ue::Entry f;f.name="Run";f.cls=-1;f.outer=1;f.offset=p.data.size();f.size=fn.size();p.exports.push_back(f);p.children[1].push_back(2);p.data.insert(p.data.end(),fn.begin(),fn.end());
            return ctx.decompile(1,true);
        };
        auto r=generate({0x2f,0x1b,1,0x16,11,0,0x0b,0x31,0x30,4,11},14);
        check(r["status"]=="recovered","Valid iterator layout rejected");
        check(r["code"].get<std::string>().find("foreach Each()")!=std::string::npos,"Iterator not emitted");
        r=generate({0x2f,0x1b,1,0x16,10,0,0x0b,0x31,0x30,4,11},14);
        check(r["status"]=="partial"&&r["functions"][0].contains("bytecode"),"Invalid iterator exit lost AST");
        // A return inside the loop without IteratorPop cannot be silently repaired.
        r=generate({0x2f,0x1b,1,0x16,12,0,4,11,0x31,0x30,4,11},15);
        check(r["status"]=="partial","Missing iterator-return cleanup accepted");
        std::filesystem::remove(argv[1]);std::cout<<"Iterator boundary/cleanup checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
