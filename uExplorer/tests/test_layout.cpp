#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool value,const std::string& message){if(!value)throw std::runtime_error(message);}
static void u32(ue::Bytes& bytes,uint32_t value){for(int i=0;i<4;++i)bytes.push_back(uint8_t(value>>(8*i)));}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Context context(argv[1],{});auto& p=*context.main;p.names={"None","First","Second"};
        for(auto name:{"IntProperty","Struct","Function","DelegateProperty"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        auto add=[&](const char* name,int cls,int outer,ue::Bytes bytes){
            ue::Entry e;e.name=name;e.cls=cls;e.outer=outer;e.offset=p.data.size();e.size=bytes.size();
            p.data.insert(p.data.end(),bytes.begin(),bytes.end());p.exports.push_back(e);p.children[outer].push_back(int(p.exports.size()));
        };
        auto prop=[&](int next,int ref=0){ue::Bytes b{0,0,uint8_t(next)};u32(b,1);u32(b,ref?0x400000:0);b.push_back(0);if(ref)b.push_back(uint8_t(ref));return b;};
        auto fn=[&](int name){ue::Bytes b{0,0,0,0,0,uint8_t(name),0};b.resize(15);u32(b,2);b.insert(b.end(),{4,11,0,0,0});u32(b,0x120000);return b;};
        add("Probe",0,0,ue::Bytes(66,0));              // 1
        add("Last",-1,1,prop(4));                    // 2
        add("FieldFirst",-1,1,prop(2));              // 3
        add("Data",-2,1,ue::Bytes(19,0));            // 4
        add("Last",-1,4,prop(0));                    // 5
        add("First",-1,4,prop(5));                   // 6
        add("Second",-3,1,fn(2));                    // 7
        add("FirstDelegate",-3,1,fn(1));             // 8
        p.exports[7].name="First";
        add("__Second__Delegate",-4,1,prop(8,7));     // 9
        add("__First__Delegate",-4,1,prop(9,8));      // 10
        p.data[p.entry(1).offset+3]=3;
        p.data[p.entry(4).offset+4]=6;
        p.data[p.entry(4).offset+2]=10;
        p.data[p.entry(8).offset+2]=7;
        check(p.orderedFields(1)==std::vector<int>({3,2,4,10,9,8,7}),"Class chain order");
        check(p.orderedFields(4)==std::vector<int>({6,5}),"Struct chain order");
        auto result=context.decompile(1,true);auto source=result["code"].get<std::string>();
        check(result["status"]=="recovered",result.dump());
        check(source.find("    var int First;")<source.find("    var int Last;"),source);
        check(source.find("\nvar int FieldFirst;")<source.find("\nvar int Last;"),source);
        check(source.find("public delegate First();")<source.find("public delegate Second();"),source);
        ue::Entry package;package.name=p.path.stem().u8string();package.importClass="Package";p.imports.push_back(package);
        ue::Entry native;native.name="NativeMesh";native.outer=-5;native.importClass="Class";native.classPackage="Core";p.imports.push_back(native);
        auto local=native;local.name="Probe";p.imports.push_back(local);
        auto metadata=p.metadata();
        check(metadata["status"]=="complete",metadata.dump());
        check(metadata["owners"]["Probe"]["fields"][0]=="Probe.FieldFirst","Metadata reordered fields");
        check(metadata["owners"]["Probe.Second"]["native"]==0&&metadata["owners"]["Probe.Second"]["flags"]==0x120000,"Function contract lost");
        check(metadata["imports"][5]["status"]=="native_class_candidate"&&metadata["imports"][6]["status"]=="local_export","Self-package import evidence");
        // Short-circuit operator parameters carry CPF_SkipParm independently
        // of the native index. Recovery must not drop their source modifier.
        ue::Entry boolean;boolean.name="BoolProperty";boolean.importClass="Class";p.imports.push_back(boolean);
        p.names.push_back("&&");auto operation=fn(3);operation[4]=12;
        operation[operation.size()-7]=130;operation[operation.size()-5]=30;
        for(int i=0;i<4;++i)operation[operation.size()-4+i]=uint8_t(0x23401u>>(8*i));
        add("AndAnd_BoolBool",-3,1,operation);
        auto parameter=[&](int next,uint32_t flags){auto b=prop(next);for(int i=0;i<4;++i)b[7+i]=uint8_t(flags>>(8*i));return b;};
        add("A",-8,11,parameter(13,0x80));
        add("B",-8,11,parameter(14,0x280));
        add("ReturnValue",-8,11,parameter(0,0x580));
        p.data[p.entry(7).offset+2]=11;
        result=context.decompile(1,true);source=result["code"].get<std::string>();
        check(result["status"]=="recovered"&&source.find("operator(30) bool &&(bool A, skip bool B)")!=source.npos,result.dump());
        auto reject=[&](){bool failed=false;try{p.orderedFields(1);}catch(const std::exception&){failed=true;}check(failed,"Invalid chain accepted");check(context.decompile(1,true)["status"]=="partial","Invalid chain silently recovered");check(p.metadata()["status"]=="partial","Metadata concealed invalid chain");};
        p.data[p.entry(7).offset+2]=3;reject(); // cycle
        p.data[p.entry(7).offset+2]=0;
        p.data[p.entry(1).offset+3]=2;reject(); // missing field
        p.data[p.entry(1).offset+3]=5;reject(); // foreign owner
        std::filesystem::remove(argv[1]);std::cout<<"Ordered fields, delegates and invalid chains passed\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
