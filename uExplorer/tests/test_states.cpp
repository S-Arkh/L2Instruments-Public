#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static void u32(ue::Bytes& b,unsigned value){for(int i=0;i<4;++i)b.push_back(uint8_t(value>>(8*i)));}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Context ctx(argv[1],{});auto& p=*ctx.main;p.names={"None","Idle","Begin"};
        ue::Entry imported;imported.name="State";imported.importClass="Class";p.imports.push_back(imported);
        auto generate=[&](int labelTarget,int labelOffset){
            p.data.resize(36);p.exports.clear();p.children.clear();
            ue::Entry owner;owner.name="Probe";owner.offset=p.data.size();owner.size=66;p.exports.push_back(owner);p.data.resize(p.data.size()+66);
            ue::Bytes state{0,0,0,0,0,1,0};state.resize(state.size()+8);u32(state,20);
            state.insert(state.end(),{8,8,11,12,2});u32(state,labelTarget);state.push_back(0);u32(state,65535);
            state.insert(state.end(),8,0);state.insert(state.end(),8,255);state.push_back(uint8_t(labelOffset));state.push_back(uint8_t(labelOffset>>8));u32(state,0);
            ue::Entry entry;entry.name="Idle";entry.cls=-1;entry.outer=1;entry.offset=p.data.size();entry.size=state.size();p.exports.push_back(entry);p.children[1].push_back(2);p.data.insert(p.data.end(),state.begin(),state.end());
            return ctx.decompile(1,true);
        };
        auto r=generate(0,4);check(r["status"]=="recovered","State label fixture rejected");
        check(r["code"].get<std::string>().find("Begin:\n    stop;")!=std::string::npos,"Explicit Stop or label lost");
        r=generate(2,4);check(r["status"]=="partial"&&r["functions"][0].contains("bytecode"),"Label in padding accepted or AST lost");
        r=generate(0,5);check(r["status"]=="partial","Mismatched label table offset accepted");
        std::filesystem::remove(argv[1]);std::cout<<"State label boundary/preservation checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
