#include "fixture_context.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool value, const std::string& message) { if(!value)throw std::runtime_error(message); }
static void u32(ue::Bytes& b,uint32_t v) { for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(i*8))); }
static ue::Bytes function(int name,uint32_t flags,const ue::Bytes& script,int size) {
    ue::Bytes b{0,0,0,0,0,uint8_t(name),0};b.resize(b.size()+8);u32(b,uint32_t(size));
    b.insert(b.end(),script.begin(),script.end());b.insert(b.end(),3,0);u32(b,flags);return b;
}
int main(int argc,char** argv) {
    try {
        if(argc!=2&&argc!=3)throw std::runtime_error("Expected fixture path and optional generated-source path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        FixtureContext ctx(argv[1],{});auto& p=*ctx.main;
        p.names={"None","Notify","Test"};
        for(auto name:{"Function","DelegateProperty"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        auto add=[&](const char* name,int cls,int outer,const ue::Bytes& data){
            ue::Entry e;e.name=name;e.cls=cls;e.outer=outer;e.offset=p.data.size();e.size=data.size();
            p.data.insert(p.data.end(),data.begin(),data.end());p.exports.push_back(e);
            p.children[outer].push_back(int(p.exports.size()));
        };
        ue::Bytes cls(66,0);add("Probe",0,0,cls);
        add("Notify",-1,1,function(1,0x120000,{4,11},2));
        ue::Bytes prop{0,0,0};u32(prop,1);u32(prop,0x400000);prop.push_back(0);prop.push_back(2);
        add("__Notify__Delegate",-2,1,prop);
        ue::Bytes script{0x45,1,3,0x44,1, 0x43,3,1,0x16, 0x11,11,11,11,0x20,1, 4,11};
        add("Test",-1,1,function(2,0x20002,script,32));
        auto r=ctx.decompile(1,true);auto code=r["code"].get<std::string>();
        check(r["status"]=="recovered",r.dump());
        for(auto text:{"delegate Notify();","Notify = Notify;","Notify();","(new Class'Probe')"})
            check(code.find(text)!=code.npos,std::string("Missing ")+text+"\n"+code);
        check(code.find("__Notify__Delegate")==code.npos,"Backing property leaked into source");
        auto classFlags=p.entry(1).offset+40;
        p.data[classFlags]=0x40;p.data[classFlags+1]=0x3a;
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        for(auto modifier:{"safereplace","nativereplication","placeable","editinlinenew","collapsecategories"})
            check(code.find(modifier)!=code.npos,std::string("Missing class modifier ")+modifier);
        p.data[classFlags]=0;p.data[classFlags+1]=0;
        auto f=p.function(4);
        check(f.nodes.size()==4&&f.nodes[1].children.size()==1&&f.nodes[1].finish==21,"Delegate arguments/PC were not consumed");
        // Metadata mismatch must retain partial + AST, rather than inventing a name.
        p.data[p.entry(4).offset+19+7]=2; // delegate call name: Test, not Notify
        r=ctx.decompile(1,true);
        check(r["status"]=="partial",r.dump());
        check(r["issues"][0]["code"]=="invalid_delegate_metadata",r.dump());
        check(r["functions"][1]["decoded"]==true&&r["functions"][1]["generated"]==false,"Wrong failure stage");
        p.data[p.entry(4).offset+19+7]=1;
        // A declaration failure after decoding must not be reported as bad bytecode.
        p.data[p.entry(4).offset+4]=3;
        r=ctx.decompile(1,true);
        check(r["functions"][1]["decoded"]==true&&r["functions"][1]["stage"]=="declaration",r.dump());
        check(r["functions"][1].contains("bytecode"),"Declaration failure lost AST");
        p.data[p.entry(4).offset+4]=0;
        // An interior omitted new argument is not silently rewritten to None.
        auto saved=p.exports[3];auto sparse=function(2,0x20002,{0x11,11,0x1f,'X',0,11,0x20,1,4,11},13);
        p.exports[3].offset=p.data.size();p.exports[3].size=sparse.size();p.data.insert(p.data.end(),sparse.begin(),sparse.end());
        r=ctx.decompile(1,true);
        check(r["status"]=="partial"&&r["functions"][1]["decoded"]==true,"Sparse new was silently accepted");
        p.exports[3]=saved;
        // A prefix minus applied to a signed literal must not become a -- token.
        auto classCast=function(2,0x20002,{0x13,1,0x2a,4,11},8);
        p.exports[3].offset=p.data.size();p.exports[3].size=classCast.size();
        p.data.insert(p.data.end(),classCast.begin(),classCast.end());
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find("class<Probe>(None)")!=code.npos,
              "Metaclass cast was rendered as an object cast: "+code);
        p.exports[3]=saved;
        ue::Function negate;negate.flags=0x1010;negate.friendly="-";
        ctx.natives[143]=std::make_pair(ue::Symbol{&p,2},negate);
        ue::Bytes negative{0x8f,0x1d};u32(negative,uint32_t(-30));
        negative.insert(negative.end(),{0x16,4,11});
        auto negated=function(2,0x20002,negative,9);
        p.exports[3].offset=p.data.size();p.exports[3].size=negated.size();
        p.data.insert(p.data.end(),negated.begin(),negated.end());
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find("--30")==code.npos&&code.find("-(-30)")!=code.npos,
              "Prefix negation merged into decrement: "+code);
        p.exports[3]=saved;
        // EX_IntZero/EX_IntOne are constants too, including under primitive casts.
        auto latent=function(2,0x20409,{},0);
        p.exports[3].offset=p.data.size();p.exports[3].size=latent.size();
        p.data.insert(p.data.end(),latent.begin(),latent.end());
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find("native final latent function Test")!=code.npos,
              "Native latent declaration flag lost: "+code);
        p.exports[3]=saved;
        for(uint8_t literal:{uint8_t(0x25),uint8_t(0x26)})for(bool cast:{false,true}){
            ue::Bytes body;if(cast)body.insert(body.end(),{0x39,0x3a});
            body.insert(body.end(),{0x19,0x17,1,0,4,literal,4,11});
            auto data=function(2,0x20002,body,int(body.size()));
            p.exports[3].offset=p.data.size();p.exports[3].size=data.size();
            p.data.insert(p.data.end(),data.begin(),data.end());
            r=ctx.decompile(1,true);code=r["code"].get<std::string>();
            check(r["status"]=="recovered"&&code.find("self.0")==code.npos&&code.find("self.1")==code.npos
                  &&code.find("__UXContextInt(self, ")!=code.npos&&code.find("int(__UXContextInt")==code.npos,
                  "Invalid integer context expression: "+code);
        }
        p.exports[3]=saved;
        // Large verified loops stay structured; arbitrary back edges retain
        // dispatcher recovery rather than being dropped by the fast path.
        for(bool structured:{true,false}){
            ue::Bytes body;
            if(structured)body={7,0,0,0x27};
            body.resize(33000,0x0b);
            body.insert(body.end(),{6,0,0});
            if(structured){body[1]=uint8_t(body.size());body[2]=uint8_t(body.size()>>8);}
            body.insert(body.end(),{4,11});
            auto data=function(2,0x20002,body,int(body.size()));
            p.exports[3].offset=p.data.size();p.exports[3].size=data.size();
            p.data.insert(p.data.end(),data.begin(),data.end());
            r=ctx.decompile(1,true);code=r["code"].get<std::string>();
            check(r["status"]=="recovered",r.dump());
            check((code.find("__RecoveredPC")!=code.npos)!=structured,
                  "Large control-flow recovery selected the wrong path");
        }
        p.exports[3]=saved;
        // A matching class constant must not be rendered as class.static.Const:
        // the SDK requires a function after static, unlike ordinary object.Const.
        ue::Entry constantKind;constantKind.name="Const";constantKind.importClass="Class";p.imports.push_back(constantKind);
        add("One",-3,1,{0,0,0,2,'1',0});
        auto classConstant=function(2,0x20002,{0x12,0x20,1,1,0,4,0x26,4,11},12);
        p.exports[3].offset=p.data.size();p.exports[3].size=classConstant.size();
        p.data.insert(p.data.end(),classConstant.begin(),classConstant.end());
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find(".static.One")==code.npos
              &&code.find("__UXContextInt(Class'Probe', 1)")!=code.npos,code);
        p.exports[3]=saved;
        // A typed context literal must retain the enum result type, even if a
        // same-valued integer Const exists on the receiver.
        for(auto name:{"ByteProperty","Enum"}){ue::Entry entry;entry.name=name;entry.importClass="Class";p.imports.push_back(entry);}
        p.names.push_back("Idle");p.names.push_back("Active");
        add("Mode",-5,1,{0,0,0,2,3,4});
        ue::Bytes returnProperty{0,0,0};u32(returnProperty,1);u32(returnProperty,0x480);
        returnProperty.insert(returnProperty.end(),{0,6});add("ReturnValue",-4,4,returnProperty);
        auto enumContext=function(2,0x20002,{4,0x19,0x17,2,0,1,0x24,1,4,11},10);enumContext[4]=7;
        p.exports[3].offset=p.data.size();p.exports[3].size=enumContext.size();
        p.data.insert(p.data.end(),enumContext.begin(),enumContext.end());
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find("return __UXContextInt_Enum_Probe_Mode(self, Active);")!=code.npos
              &&code.find("static function Probe.Mode __UXContextInt_Enum_Probe_Mode")!=code.npos,code);
        // Long enum names and a member colliding with the shortened helper
        // must still produce a bounded, unique function identifier.
        p.exports[5].name="ModeWithALongNameForContextHelperIdentifierLimit";
        auto shortHelper=(std::string("__UXContextInt_Enum_Probe_")+p.exports[5].name).substr(0,48);
        p.exports[4].name=shortHelper;
        p.paths.clear();p.paths[0]="None";
        r=ctx.decompile(1,true);code=r["code"].get<std::string>();
        check(r["status"]=="recovered"&&code.find("return "+shortHelper+"_1(self, Active);")!=code.npos,code);
        if(argc==3){
            // Supply the real root-class import for an independent compiler
            // check of this synthetic context bytecode's generated source.
            ue::Entry core;core.name="Core";core.importClass="Package";p.imports.push_back(core);
            ue::Entry object;object.name="Object";object.importClass="Class";object.outer=-int(p.imports.size());p.imports.push_back(object);
            p.exports[0].super=-int(p.imports.size());
            auto source=ctx.decompile(1,true)["code"].get<std::string>();
            std::ofstream output(argv[2],std::ios::binary);output<<source;
            if(!output)throw std::runtime_error("Could not write generated context fixture");
            p.exports[0].super=0;
        }
        p.exports[5].name="Mode";p.exports[4].name="One";
        p.paths.clear();p.paths[0]="None";
        p.exports[3]=saved;
        // A non-generated DelegateProperty cannot simply be discarded.
        p.exports[2].name="UnverifiedDelegate";p.paths.clear();p.paths[0]="None";
        r=ctx.decompile(1,true);check(r["status"]=="partial","Unverified delegate declaration was hidden");
        // Each supported package profile uses the same delegate call grammar.
        for(auto profile:{std::pair<int,int>{123,0},{123,37},{126,0},{133,40}}){
            p.version=profile.first;p.licensee=profile.second;
            ue::Bytes nested{0x43,3,1,0x43,3,1,0x16,0x16};ue::Reader reader(nested);ue::Decoder decoder{p,reader};
            auto nodes=decoder.script(20);check(nodes.size()==1&&nodes[0].children.size()==2&&nodes[0].children[0].children.size()==1,"Nested delegate call");
            for(auto bytes:{ue::Bytes{0x43,3,1},ue::Bytes{0x43,3,1,0x43,3,1,0x16},ue::Bytes{0x11,11,11,11}}){
                bool rejected=false;try{ue::Reader rr(bytes);ue::Decoder dd{p,rr};dd.expression();}catch(const std::exception&){rejected=true;}
                check(rejected,"Truncated operands accepted");
            }
        }
        auto replicated=function(2,0x40,{4,11},2);replicated.insert(replicated.end(),{0x34,0x12});
        add("Replicated",-1,1,replicated);
        check(p.function(int(p.exports.size())).replicationOffset==0x1234,"Function replication offset lost");
        --p.exports.back().size;bool truncated=false;
        try{p.function(int(p.exports.size()));}catch(const std::exception&){truncated=true;}
        check(truncated,"Truncated function replication offset accepted");
        {
            // Equal export indices in different packages are different symbols.
            FixtureContext cross(argv[1],{});auto& child=*cross.main;
            auto base=std::make_shared<ue::Package>(argv[1]);base->path="Base.u";
            for(auto* pkg:{&child,base.get()}){
                pkg->names={"None","Test"};pkg->imports.clear();pkg->exports.clear();
                pkg->children.clear();pkg->paths.clear();pkg->paths[0]="None";
                ue::Entry fn;fn.name="Function";fn.importClass="Class";pkg->imports.push_back(fn);
                ue::Entry cl;cl.name=pkg==&child?"Child":"Parent";cl.offset=pkg->data.size();cl.size=66;
                pkg->data.insert(pkg->data.end(),66,0);pkg->exports.push_back(cl);
                auto body=function(1,0x20002,pkg==&child?ue::Bytes{0x1c,0x84,0x16,4,11}:ue::Bytes{4,11},pkg==&child?8:2);
                ue::Entry method;method.name="Test";method.cls=-1;method.outer=1;
                method.offset=pkg->data.size();method.size=body.size();
                pkg->data.insert(pkg->data.end(),body.begin(),body.end());pkg->exports.push_back(method);
                pkg->children[1].push_back(2);pkg->data[cl.offset+3]=2;
            }
            ue::Entry module;module.name="Base";module.importClass="Package";child.imports.push_back(module);
            ue::Entry parent;parent.name="Parent";parent.importClass="Class";parent.outer=-2;child.imports.push_back(parent);
            ue::Entry method;method.name="Test";method.importClass="Function";method.outer=-3;child.imports.push_back(method);
            child.exports[0].super=-3;cross.packages.push_back(base);
            auto recovered=cross.decompile(1,true);
            check(recovered["status"]=="recovered"&&recovered["code"].get<std::string>().find("super.Test();")!=std::string::npos,
                  "Cross-package direct base call became virtual recursion: "+recovered.dump());
            child.exports[1].name="Other";child.names[1]="Other";
            child.paths.clear();child.paths[0]="None";
            recovered=cross.decompile(1,true);
            check(recovered["status"]=="recovered"&&recovered["code"].get<std::string>().find("super.Test();")!=std::string::npos,
                  "Inherited direct call without a local override became virtual: "+recovered.dump());
            auto middle=base->exports[0];middle.name="Middle";middle.super=1;
            middle.offset=base->data.size();base->data.insert(base->data.end(),66,0);
            base->exports.push_back(middle);
            auto override=base->exports[1];override.outer=3;
            base->exports.push_back(override);base->children[3].push_back(4);
            base->data[middle.offset+3]=4;
            auto middleImport=parent;middleImport.name="Middle";
            child.imports.push_back(middleImport);child.exports[0].super=-5;
            child.paths.clear();child.paths[0]="None";base->paths.clear();base->paths[0]="None";
            recovered=cross.decompile(1,true);
            check(recovered["status"]=="recovered"&&recovered["code"].get<std::string>().find("super(Parent).Test();")!=std::string::npos,
                  "Skipped ancestor direct call rebound to nearest override: "+recovered.dump());
        }
        std::filesystem::remove(argv[1]);std::cout<<"Delegate/new generation and decoder checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
