#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool v,const std::string& message){if(!v)throw std::runtime_error(message);}
static void u32(ue::Bytes& b,uint32_t v){for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i)));}
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Context ctx(argv[1],{});auto& p=*ctx.main;p.names={"None","Convert"};
        for(auto name:{"Function","PtrProperty","IntProperty"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        auto add=[&](const char* name,int type,int outer,const ue::Bytes& bytes){
            ue::Entry e;e.name=name;e.cls=type;e.outer=outer;e.offset=p.data.size();e.size=bytes.size();
            p.data.insert(p.data.end(),bytes.begin(),bytes.end());p.exports.push_back(e);p.children[outer].push_back(int(p.exports.size()));
        };
        ue::Bytes cls(66,0);cls[41]=1;cls[62]=1;add("Object",0,0,cls);p.exports[0].flags=0x04000000;
        // A local Core.Object reference is the same default Within as imported Core.Object.
        p.path="Core.u";auto result=ctx.decompile(1,true);auto code=result["code"].get<std::string>();
        check(result["status"]=="recovered",result.dump());
        check(code.find(" native noexport;")!=code.npos&&code.find(" within ")==code.npos,"Root Object flags/Within");
        // A similarly named class in another package is not Core.Object.
        p.path="Other.u";result=ctx.decompile(1,true);check(result["status"]=="partial","Unrelated Object treated as root");
        add("Owner",0,0,ue::Bytes(66,0));p.data[p.entry(1).offset+62]=2;
        result=ctx.decompile(1,true);check(result["code"].get<std::string>().find(" within Owner")!=std::string::npos,result.dump());
        ue::Bytes prop{0,0,0};u32(prop,1);u32(prop,0x1002);prop.push_back(0);add("NativeHandle",-3,1,prop);
        result=ctx.decompile(1,true);check(result["code"].get<std::string>().find("var native const int NativeHandle;")!=std::string::npos,result.dump());
        p.data[p.entry(1).offset+62]=3;result=ctx.decompile(1,true);check(result["status"]=="partial","Non-class Within accepted");
        p.data[p.entry(1).offset+62]=2;
        // Keep the native pointer's metadata and original bytes; do not replace its type.
        add("Handle",-2,1,prop);result=ctx.decompile(1,true);
        check(result["status"]=="partial",result.dump());
        auto saved=result["unrecovered_properties"][0];
        check(saved["kind"]=="PtrProperty"&&saved["flags"]==0x1002&&saved["dimension"]==1&&saved["raw_hex"]==ue::hex(prop),saved.dump());
        p.data[p.exports[3].offset+7]=0;result=ctx.decompile(1,true);
        check(result["status"]=="recovered"&&result["code"].get<std::string>().find("var native pointer Handle;")!=std::string::npos,"Verified native pointer declaration not emitted");
        p.data[p.exports[3].offset+7]=2;
        // Truncated property metadata must still preserve raw bytes.
        --p.exports[3].size;result=ctx.decompile(1,true);
        check(result["status"]=="partial"&&!result["unrecovered_properties"][0].contains("flags"),result.dump());
        ++p.exports[3].size;
        // Cast discriminator 0x39 is separate from its EX_PrimitiveCast opcode.
        for(auto profile:{std::pair<int,int>{123,0},{123,37},{126,0},{133,40}}){
            p.version=profile.first;p.licensee=profile.second;
            ue::Bytes cast{0x39,0x39,0x22};u32(cast,1);u32(cast,2);u32(cast,3);
            ue::Reader reader(cast);ue::Decoder decoder{p,reader};auto nodes=decoder.script(15);
            check(nodes.size()==1&&nodes[0].kind=="cast"&&nodes[0].index==57&&nodes[0].children[0].kind=="rotation","Cast tree/PC");
            for(auto bytes:{ue::Bytes{0x39},ue::Bytes{0x39,0x39},ue::Bytes{0x39,0x39,0x22,0}}){
                bool failed=false;try{ue::Reader rr(bytes);ue::Decoder dd{p,rr};dd.expression();}catch(const std::exception&){failed=true;}
                check(failed,"Truncated cast accepted");
            }
        }
        ue::Bytes netprop{0,0,0};u32(netprop,1);u32(netprop,0x20);netprop.insert(netprop.end(),{0,0x34,0x12});
        add("Replicated",-3,1,netprop);
        check(p.property(int(p.exports.size())).replicationOffset==0x1234,"Property replication offset lost");
        --p.exports.back().size;bool truncated=false;
        try{p.property(int(p.exports.size()));}catch(const std::exception&){truncated=true;}
        check(truncated,"Truncated property replication offset accepted");
        // Export-table order is not declaration order: a struct may refer to a
        // later sibling, directly or through a dynamic-array inner property.
        for(auto name:{"Struct","StructProperty","ArrayProperty"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        add("Container",-4,2,ue::Bytes(19,0));
        add("Inner",-4,2,ue::Bytes(19,0));
        ue::Bytes member{0,0,0};u32(member,1);u32(member,0);member.push_back(0);
        auto nested=member;nested.push_back(7);add("Value",-5,6,nested);
        add("Count",-3,7,member);
        auto array=member;array.push_back(11);add("Items",-6,6,array);
        add("Items",-5,10,nested);
        result=ctx.decompile(2,true);code=result["code"].get<std::string>();
        check(result["status"]=="recovered"&&code.find("struct Inner\n")<code.find("struct Container\n")
              &&code.find("array<Owner.Inner> Items")!=code.npos,result.dump());
        // By-value recursive declarations must not silently report recovery.
        p.data[p.entry(8).offset+12]=6;
        result=ctx.decompile(2,true);
        check(result["status"]=="partial"&&result["issues"].dump().find("Cyclic struct declaration")!=std::string::npos,result.dump());
        std::filesystem::remove(argv[1]);std::cout<<"Within/native metadata, pointer preservation and cast checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
