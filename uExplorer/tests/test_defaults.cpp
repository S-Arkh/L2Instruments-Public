#include "fixture_context.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        FixtureContext ctx(argv[1],{});auto& p=*ctx.main;p.names={"None","Tint","Color","Settings","Nested","Count","Enabled"};
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
        r=generate({5,0x24,255,255,255,255,0});
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count=__FloatBits(\"FFFFFFFF\")")!=std::string::npos,
              "NaN default payload bits lost");
        r=generate({3,0x5a,4,7,5,0x24,1,0,128,127,0,0});
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count=__FloatBits(\"7F800001\")")!=std::string::npos,
              "Nested signaling NaN bits lost");
        r=generate({1,0x2a,2,65,33,17});
        check(r["status"]=="partial"&&r.contains("class_tail_hex"),"Truncated color not preserved");
        r=generate({3,0x5a,4,6,5,0x22,37,0,0,0,0});
        check(r["status"]=="partial","Nested structure without terminator accepted");
        r=generate({1,0x07,99,0});
        check(r["status"]=="partial"&&r["unrecovered_defaults"][0]["raw_hex"]=="63","Unknown default raw data lost");
        p.names.push_back("'\\\n\r\t\"");
        r=generate({5,6,7,0});
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count='\\'\\\\\\n\\r\\t\"'")!=std::string::npos,
              "Name default delimiter or control characters not escaped");
        r=generate({3,0x5a,4,4,5,6,7,0,0});
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count='\\'\\\\\\n\\r\\t\"'")!=std::string::npos,
              "Nested name default not escaped");
        p.names.pop_back();
        generate({5,1,1,0});
        for(auto name:{"Enum","ByteProperty"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        p.names.push_back("ChoiceZero");p.names.push_back("ChoiceOne");
        auto add=[&](const char* name,int kind,const ue::Bytes& bytes){
            ue::Entry e;e.name=name;e.cls=kind;e.outer=1;e.offset=p.data.size();e.size=bytes.size();
            p.data.insert(p.data.end(),bytes.begin(),bytes.end());p.exports.push_back(e);p.children[1].push_back(int(p.exports.size()));
        };
        add("EChoice",-1,{0,0,0,2,7,8});
        add("Count",-2,{0,0,0,1,0,0,0,0,0,0,0,0,2});
        r=ctx.decompile(1,true);
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count=ChoiceOne")!=std::string::npos,"Enum default lost its symbolic identity");
        p.data[p.entry(1).offset+67]=2;
        check(ctx.decompile(1,true)["status"]=="partial","Out-of-range enum default silently recovered");
        generate({0});
        add("First",1,{5,0x22,7,0,0,0,0});
        r=ctx.decompile(1,true);
        check(r["status"]=="recovered","Default subobject not recovered");
        auto code=r["code"].get<std::string>();
        check(code.find("Begin Object Class=DefaultProbe Name=First")!=code.npos&&
              code.find("        Count=7")!=code.npos&&code.find("End Object")!=code.npos,
              "Default subobject declaration or value missing");
        p.data.push_back(0);++p.exports.back().size;
        auto instance=ctx.objectDefaults(2);
        check(instance["status"]=="partial"&&instance.contains("raw_hex"),"Object operation discards native tail");
        p.data.pop_back();--p.exports.back().size;
        instance=ctx.objectDefaults(2);
        check(instance["status"]=="recovered"&&instance["outer"]=="DefaultProbe"&&
              instance["properties"].get<std::string>().find("Count=7")!=std::string::npos,
              "Object operation loses owner or property values");
        p.exports[1].outer=0;p.paths.erase(2);
        instance=ctx.objectDefaults(2);
        check(instance["status"]=="recovered"&&instance["outer"]=="None"&&instance["path"]=="First",
              "Package-scoped object recovery changes identity");
        p.exports[1].outer=1;p.paths.erase(2);
        p.data.push_back(0);++p.exports.back().size;
        check(ctx.decompile(1,true)["status"]=="partial","Subobject native tail silently discarded");
        generate({3,0x5a,4,13,5,0x59,9,2,3,0,0,0,7,0,0,0,0,0});
        for(auto name:{"Struct","StructProperty","ArrayProperty","IntProperty"}){
            ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);
        }
        add("Nested",-3,ue::Bytes(19,0));
        add("Settings",-4,{0,0,0,1,0,0,0,0,0,0,0,0,2});
        add("Count",-5,{0,0,0,1,0,0,0,0,0,0,0,0,5});
        add("Count",-6,{0,0,0,1,0,0,0,0,0,0,0,0});
        p.exports[3].outer=2;p.exports[4].outer=4;
        p.children[1]={2,3};p.children[2]={4};p.children[4]={5};
        r=ctx.decompile(1,true);
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Settings=(Count=(3,7))")!=std::string::npos,
              "Dynamic array inside a default struct not recovered");
        p.imports.back().name="FloatProperty";
        p.paths.erase(-int(p.imports.size()));
        auto values=p.entry(1).offset+65+8;
        for(int i=0;i<4;++i)p.data[values+i]=255;
        p.data[values+4]=0;p.data[values+5]=0;p.data[values+6]=128;p.data[values+7]=255;
        r=ctx.decompile(1,true);
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Count=(__FloatBits(\"FFFFFFFF\"),__FloatBits(\"FF800000\"))")!=std::string::npos,
              ("Nonfinite array elements lost their exact bits: "+r.dump()).c_str());
        p.names.push_back("Vector");
        r=generate({3,0x3a,9,255,255,255,255,0,0,128,127,0,0,0,128,0});
        check(r["status"]=="recovered"&&r["code"].get<std::string>().find("Settings=(X=__FloatBits(\"FFFFFFFF\"),Y=__FloatBits(\"7F800000\"),Z=-0.0)")!=std::string::npos,
              "Vector nonfinite bits or finite signed zero changed");
        std::filesystem::remove(argv[1]);std::cout<<"Default decoding and malformed payload checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
