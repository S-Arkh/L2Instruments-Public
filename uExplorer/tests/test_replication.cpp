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
        ue::Context ctx(argv[1],{});auto& p=*ctx.main;p.names={"None"};
        ue::Entry imp;imp.name="IntProperty";imp.importClass="Class";p.imports.push_back(imp);
        // Class script starts at byte 18: one True condition at PC 0.
        ue::Bytes cls(67,0);cls[14]=1;cls[18]=0x27;
        ue::Entry owner;owner.name="Probe";owner.offset=p.data.size();owner.size=cls.size();p.exports.push_back(owner);p.data.insert(p.data.end(),cls.begin(),cls.end());
        ue::Bytes prop{0,0,0,1,0,0,0,0x20,0,0,0,0,0,0};
        ue::Entry field;field.name="Counter";field.cls=-1;field.outer=1;field.offset=p.data.size();field.size=prop.size();p.exports.push_back(field);p.data.insert(p.data.end(),prop.begin(),prop.end());p.children[1].push_back(2);
        auto r=ctx.decompile(1,true);
        check(r["status"]=="recovered","Valid replication fixture not recovered");
        check(r["code"].get<std::string>().find("reliable if (true)")!=std::string::npos,"Condition not emitted");
        p.data[field.offset+12]=1;r=ctx.decompile(1,true);
        check(r["status"]=="partial","Invalid replication boundary accepted");
        check(r["code"].get<std::string>().find("replication\n{")==std::string::npos,"Incomplete replication block emitted");
        check(r.contains("class_script"),"Rejected replication lost class AST");
        std::filesystem::remove(argv[1]);std::cout<<"Replication boundary and preservation checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
