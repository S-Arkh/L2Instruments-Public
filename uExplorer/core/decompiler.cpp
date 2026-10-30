#include "package.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace ue {
static std::string quote(const std::string& s){std::string out="\"";for(char c:s){switch(c){case '\\':out+="\\\\";break;case '"':out+="\\\"";break;case '\r':out+="\\r";break;case '\n':out+="\\n";break;case '\t':out+="\\t";break;default:out+=c;}}return out+'"';}
static std::string join(const std::vector<std::string>& parts,const std::string& sep=", "){std::string r;for(auto& s:parts){if(!r.empty())r+=sep;r+=s;}return r;}
static bool propertyKind(const std::string& s){return s.size()>=8&&s.substr(s.size()-8)=="Property";}
Context::Context(const std::filesystem::path& file,const std::vector<std::filesystem::path>& directories){
    main=std::make_shared<Package>(file);packages.push_back(main);
    std::vector<std::filesystem::path> dirs{file.parent_path()};dirs.insert(dirs.end(),directories.begin(),directories.end());
    std::map<std::string,std::filesystem::path> available;
    for(auto& dir:dirs){std::error_code ec;if(!std::filesystem::is_directory(dir,ec))continue;for(auto& entry:std::filesystem::directory_iterator(dir))if(entry.is_regular_file()&&lower(entry.path().extension().u8string())==".u")available.emplace(lower(entry.path().stem().u8string()),entry.path());}
    std::set<std::string> visited{lower(file.stem().u8string())};
    for(size_t at=0;at<packages.size();++at){
        auto current=packages[at];
        for(auto& e:current->imports)if(e.outer==0&&e.importClass=="Package"){
            auto key=lower(e.name);if(!visited.insert(key).second)continue;
            if(packages.size()>=64){diagnostics.push_back("Dependency limit (64 packages)");continue;}
            auto found=available.find(key);if(found==available.end()){diagnostics.push_back("Missing dependency: "+e.name+".u");continue;}
            try{packages.push_back(std::make_shared<Package>(found->second));}catch(const std::exception& ex){diagnostics.push_back("Dependency "+e.name+": "+ex.what());}
        }
    }
    for(auto& p:packages)for(size_t i=0;i<p->exports.size();++i){int id=int(i)+1;if(p->kind(id)!="Function")continue;
        try{auto f=p->function(id);if(!f.native)continue;auto it=natives.find(f.native);if(it!=natives.end()&&(it->second.second.friendly!=f.friendly||((it->second.second.flags^f.flags)&0x1010)))conflicts.insert(f.native);else natives.emplace(f.native,std::make_pair(Symbol{p.get(),id},std::move(f)));}
        catch(const std::exception& ex){diagnostics.push_back(p->path.filename().u8string()+":"+p->ref(id)+": "+ex.what());}
    }
    for(int n:conflicts){natives.erase(n);diagnostics.push_back("Conflicting native index: "+std::to_string(n));}
}
Symbol Context::resolve(const Package& from,int id) const {
    if(!id)return {};if(id>0)return {&from,id};auto path=from.ref(id);auto dot=path.find('.');if(dot==path.npos)return {};
    auto pkg=lower(path.substr(0,dot));for(auto& p:packages)if(lower(p->path.stem().u8string())==pkg)return {p.get(),p->find(path.substr(dot+1))};return {};
}
struct Writer {
    const Context& ctx;const Package& p;
    Json issues=Json::array(), functions=Json::array();
    bool contextHelper=false;
    std::string configDeclaration;
    std::string helper="__UXContextInt";
    void issue(const std::string& scope,const std::string& message){issues.push_back({{"scope",scope},{"message",message}});}
    std::string type(Symbol s,int depth=0) const {
        if(!s||depth>32)throw std::runtime_error("Unresolved/recursive property type");auto v=s.p->property(s.id);auto& k=v.kind;
        if(k=="IntProperty")return "int";if(k=="BoolProperty")return "bool";if(k=="FloatProperty")return "float";if(k=="StrProperty")return "string";if(k=="NameProperty")return "name";
        if(k=="ByteProperty"){
            if(!v.ref)return "byte";
            auto en=ctx.resolve(*s.p,v.ref);
            if(en){auto owner=en.p->entry(en.id).outer;return (owner?en.p->entry(owner).name+".":"")+en.p->entry(en.id).name;}
            return leaf(s.p->ref(v.ref));
        }
        if(k=="ObjectProperty"||k=="StructProperty")return leaf(s.p->ref(v.ref));
        if(k=="ClassProperty")return "class<"+leaf(s.p->ref(v.meta))+">";
        if(k=="ArrayProperty")return "array<"+type(ctx.resolve(*s.p,v.ref),depth+1)+">";
        throw std::runtime_error("Unsupported property type "+k);
    }
    std::vector<Symbol> fields(Symbol function) const {
        auto f=function.p->function(function.id);int id=f.fields[3];std::set<int> seen;std::vector<Symbol> result;
        while(id){if(!seen.insert(id).second)throw std::runtime_error("Cyclic function property list");if(function.p->entry(id).outer!=function.id)throw std::runtime_error("Function property owner mismatch");auto prop=function.p->property(id);result.push_back({function.p,id});id=prop.next;}return result;
    }
    std::string declaration(Symbol s,bool parameter=false) const {
        auto prop=s.p->property(s.id);std::string out;
        if(parameter){if(prop.flags&0x10)out+="optional ";if(prop.flags&0x100)out+="out ";if(prop.flags&0x800)out+="coerce ";}
        else{if(prop.flags&2)out+="const ";if(prop.flags&0x2000)out+="transient ";if(prop.flags&0x4000)out+="config ";if(prop.flags&0x8000)out+="localized ";if(prop.flags&0x40000)out+="globalconfig ";}
        out+=type(s)+" "+s.p->entry(s.id).name;if(prop.dim>1)out+="["+std::to_string(prop.dim)+"]";return out;
    }
    Symbol returnType(Symbol s) const {if(!s)return {};for(auto prop:fields(s))if(prop.p->property(prop.id).flags&0x400)return prop;return {};}
    Symbol findCall(const std::string& name,Symbol owner) const {
        std::set<std::string> seen;
        while(owner){auto key=owner.p->path.u8string()+":"+owner.p->ref(owner.id);if(!seen.insert(key).second)break;
            for(int i:owner.p->members(owner.id))if(owner.p->kind(i)=="Function"&&lower(owner.p->entry(i).name)==lower(name))return {owner.p,i};
            if(owner.p->kind(owner.id)=="State")owner={owner.p,owner.p->entry(owner.id).outer};else owner=ctx.resolve(*owner.p,owner.p->entry(owner.id).super);
        }return {};
    }
    Symbol nodeType(const Node& n,Symbol owner) const {
        if(n.kind=="local"||n.kind=="instance"||n.kind=="default"||n.kind=="struct_member")return ctx.resolve(p,n.ref);
        if(n.kind=="bool_variable"||n.kind=="skip")return nodeType(n.children.at(0),owner);
        if(n.kind=="context"||n.kind=="class_context")return nodeType(n.children.at(1),owner);
        if(n.kind=="final_call")return returnType(ctx.resolve(p,n.ref));
        if(n.kind=="virtual_call"||n.kind=="global_call")return returnType(findCall(n.text,owner));
        if(n.kind=="array_element"||n.kind=="dynamic_array_element"){
            auto s=nodeType(n.children.at(1),owner);if(s&&s.p->property(s.id).kind=="ArrayProperty")return ctx.resolve(*s.p,s.p->property(s.id).ref);return s;
        }return {};
    }
    Symbol receiver(const Node& n,Symbol owner) const {
        if(n.kind=="object"||n.kind=="dynamic_cast"||n.kind=="class_cast")return ctx.resolve(p,n.ref);
        auto prop=nodeType(n,owner);if(!prop)return {};auto v=prop.p->property(prop.id);return ctx.resolve(*prop.p,v.kind=="ClassProperty"?v.meta:v.ref);
    }
    std::string expression(const Node& n,Symbol owner,Symbol expected={},bool context=false){
        auto& k=n.kind;auto& c=n.children;
        auto e=[&](size_t i){return expression(c.at(i),owner);};
        auto number=[&]()->std::string{if(k=="int_zero")return "0";if(k=="int_one")return "1";return n.value.dump();};
        if(k=="constant"||k=="int_zero"||k=="int_one"){
            if(n.value.is_number_float()&&!std::isfinite(n.value.get<double>()))throw std::runtime_error("Nonfinite float");
            if(expected){auto prop=expected.p->property(expected.id);if(prop.kind=="ByteProperty"&&prop.ref){int value=std::stoi(number());auto en=ctx.resolve(*expected.p,prop.ref);if(en){auto members=en.p->enumeration(en.id);if(value>=0&&size_t(value)<members.size())return members[value];}return leaf(expected.p->ref(prop.ref))+"("+number()+")";}}
            return number();
        }
        if(k=="local"||k=="instance"||k=="native_parameter")return leaf(n.text);
        if(k=="default")return "default."+leaf(n.text);
        if(k=="nothing"||k=="end_parameters")return "";
        if(k=="skip"||k=="bool_variable"||k=="discard_string")return e(0);
        if(k=="true"||k=="false"||k=="self")return k;if(k=="none")return "None";
        if(k=="string")return quote(n.text);if(k=="name")return "'"+n.text+"'";
        if(k=="object"){if(!n.ref)return "None";return p.kind(n.ref)+"'"+n.text+"'";}
        if(k=="native"||k=="final_call"||k=="virtual_call"||k=="global_call"){
            Symbol call;Function f;std::string name=leaf(n.text);
            if(k=="native"){auto it=ctx.natives.find(n.index);if(it==ctx.natives.end())throw std::runtime_error("Unknown/conflicting native "+std::to_string(n.index)+" at PC "+std::to_string(n.pc));call=it->second.first;f=it->second.second;name=f.friendly;}
            else{call=k=="final_call"?ctx.resolve(p,n.ref):findCall(n.text,owner);if(call)f=call.p->function(call.id);}
            std::vector<Symbol> params;if(call)for(auto prop:fields(call))if((prop.p->property(prop.id).flags&0x480)==0x80)params.push_back(prop);
            std::vector<std::string> args;for(size_t i=0;i<c.size()&&c[i].kind!="end_parameters";++i)args.push_back(expression(c[i],owner,i<params.size()?params[i]:Symbol{}));
            if(k=="native"&&(f.flags&0x1000)){
                if(args.size()==2)return "("+args[0]+" "+name+" "+args[1]+")";
                if(args.size()==1)return "("+((f.flags&0x10)?name+args[0]:args[0]+name)+")";
                throw std::runtime_error("Native operator arity mismatch");
            }
            if(k=="global_call")name="global."+name;
            if(k=="final_call"&&!context&&call&&owner&&call.p==owner.p&&call.p->entry(call.id).outer!=owner.id){
                auto same=findCall(name,owner);if(same&&same.id!=call.id)name="super."+name;
            }
            return name+"("+join(args)+")";
        }
        if(k=="context"||k=="class_context"){
            if(c.at(1).kind=="constant"&&c[1].value.is_number_integer()){
                contextHelper=true;return helper+"("+e(0)+", "+e(1)+")";
            }
            auto recv=receiver(c.at(0),owner);return e(0)+(k=="class_context"?".static.":".")+expression(c.at(1),recv,{},true);
        }
        if(k=="cast"){
            static const std::vector<std::string> cast={"int","bool","float","byte","bool","float","byte","int","float","byte","int","bool","bool","bool","vector","byte","int","bool","float","vector","rotator","bool","rotator","bool","string","string","string","string","string","string","string","string","INT64","INT64","INT64","INT64","INT64","byte","int","bool","float","string"};
            if(n.index<0x3a||n.index>0x63)throw std::runtime_error("Unknown cast "+std::to_string(n.index));auto target=cast.at(size_t(n.index-0x3a));
            if(expected){auto prop=expected.p->property(expected.id);if(prop.kind=="ByteProperty"&&prop.ref&&(target=="byte"||target=="int"))target=leaf(expected.p->ref(prop.ref));}
            if(target=="int"&&(c[0].kind=="int_zero"||c[0].kind=="int_one"||(c[0].kind=="constant"&&c[0].value.is_number_integer())))return e(0);
            return target+"("+e(0)+")";
        }
        if(k=="dynamic_cast"||k=="class_cast")return leaf(n.text)+"("+e(0)+")";
        if(k=="array_element"||k=="dynamic_array_element")return e(1)+"["+e(0)+"]";
        if(k=="array_length")return e(0)+".Length";
        if(k=="struct_member")return e(0)+"."+leaf(n.text);
        if(k=="struct_equal"||k=="struct_not_equal")return "("+e(0)+(k=="struct_equal"?" == ":" != ")+e(1)+")";
        if(k=="assign"||k=="assign_bool")return e(0)+" = "+expression(c.at(1),owner,nodeType(c[0],owner));
        if(k=="array_insert"||k=="array_remove")return e(0)+(k=="array_insert"?".Insert(":".Remove(")+e(1)+", "+e(2)+")";
        if(k=="rotation"||k=="vector"){std::vector<std::string> values;for(auto& value:n.value)values.push_back(value.dump());return (k=="vector"?"vect(":"rot(")+join(values)+")";}
        if(k=="assert")return "assert("+e(0)+")";
        throw std::runtime_error("Unsupported expression "+k+" at PC "+std::to_string(n.pc));
    }
    std::string body(const Function& f,Symbol owner,const std::string& locals,Symbol ret){
        auto& roots=f.nodes;std::map<int,size_t> positions;for(size_t i=0;i<roots.size();++i)positions[roots[i].pc]=i;
        bool flow=false;for(auto& n:roots)if(n.kind=="jump"||n.kind=="jump_if_not"||n.kind=="switch")flow=true;
        std::string pcName="__RecoveredPC";for(auto s:fields({&p,f.id}))while(lower(s.p->entry(s.id).name)==lower(pcName))pcName+="_";
        std::string out="{\n"+locals;
        auto statement=[&](const Node& n){auto s=expression(n,owner);if(n.kind=="native"&&s.size()>1&&s.front()=='('&&s.back()==')')s=s.substr(1,s.size()-2);return s+";";};
        if(!flow){for(auto& n:roots){if(n.kind=="nothing"||n.kind=="debug")continue;if(n.kind=="return"){auto value=expression(n.children.at(0),owner,ret);if(value.empty()&&&n==&roots.back())continue;out+="    return"+(value.empty()?"":" "+value)+";\n";}else out+="    "+statement(n)+"\n";}return out+"}\n";}
        std::set<int> labels{0,f.size};
        for(size_t i=0;i<roots.size();++i){auto& n=roots[i];if(n.kind=="jump"||n.kind=="jump_if_not"||n.kind=="case"){
            if(n.target!=65535){if(!positions.count(n.target)&&n.target!=f.size)throw std::runtime_error("Branch into expression");labels.insert(n.target);}if(i+1<roots.size())labels.insert(roots[i+1].pc);
        }if(n.kind=="return"&&i+1<roots.size())labels.insert(roots[i+1].pc);if(n.kind=="case"||n.kind=="switch")labels.insert(n.pc);}
        out+="    local int "+pcName+";\n    "+pcName+" = 0;\n    while (true)\n    {\n        switch ("+pcName+")\n        {\n";
        for(size_t i=0;i<roots.size();){out+="        case "+std::to_string(roots[i].pc)+":\n";bool done=false;
            do{auto& n=roots[i];auto next=i+1<roots.size()?roots[i+1].pc:f.size;
                auto route=[&](int target){return pcName+" = "+std::to_string(target)+";";};
                if(done)throw std::runtime_error("Expression after terminator");
                if(n.kind=="jump"){out+="            "+route(n.target)+"\n";done=true;}
                else if(n.kind=="jump_if_not"){out+="            if ("+expression(n.children.at(0),owner)+") "+route(next)+"\n            else "+route(n.target)+"\n";done=true;}
                else if(n.kind=="switch"){
                    out+="            switch ("+expression(n.children.at(0),owner)+")\n            {\n";size_t j=i+1;std::set<size_t> seen;
                    for(;;){if(j>=roots.size()||!seen.insert(j).second||roots[j].kind!="case"||j+1>=roots.size())throw std::runtime_error("Invalid switch case chain");auto& ca=roots[j];
                        out+="            "+(ca.target==65535?std::string("default"):"case "+expression(ca.children.at(0),owner,nodeType(n.children[0],owner)))+": "+route(roots[j+1].pc)+" break;\n";
                        if(ca.target==65535)break;j=positions.at(ca.target);
                    }out+="            }\n";done=true;
                }else if(n.kind=="return"){auto value=expression(n.children.at(0),owner,ret);out+="            "+(value.empty()?route(-1):"return "+value+";")+"\n";done=true;}
                else if(n.kind!="case"&&n.kind!="nothing"&&n.kind!="debug")out+="            "+statement(n)+"\n";
                ++i;if(i==roots.size()||labels.count(roots[i].pc)){if(!done)out+="            "+route(next)+"\n";break;}
            }while(true);out+="            break;\n";
        }
        return out+"        default: "+pcName+" = -1; break;\n        }\n        if ("+pcName+" == -1) break;\n    }\n}\n";
    }
    std::string function(int id){
        auto scope=p.ref(id);std::string header;
        try{auto f=p.function(id);std::vector<std::string> params;std::string locals;Symbol ret;
            for(auto prop:fields({&p,id})){auto flags=p.property(prop.id).flags;if(flags&0x400)ret=prop;else if(flags&0x80)params.push_back(declaration(prop,true));else locals+="    local "+type(prop)+" "+p.entry(prop.id).name+(p.property(prop.id).dim>1?"["+std::to_string(p.property(prop.id).dim)+"]":"")+";\n";}
            if(f.flags&0x400)header+="native"+(f.native?"("+std::to_string(f.native)+")":"")+" ";
            for(auto flag:{std::pair<uint32_t,const char*>{1,"final"},{2,"defined"},{4,"iterator"},{0x100,"simulated"},{0x200,"exec"},{0x2000,"static"},{0x20,"singular"}})if(flag.first!=2&&(f.flags&flag.first))header+=std::string(flag.second)+" ";
            if(f.flags&0x1000)header+=(f.flags&0x10)?"preoperator ":f.precedence?"operator("+std::to_string(f.precedence)+") ":"postoperator ";
            else header+=(f.flags&0x800)?"event ":"function ";
            if(ret)header+=type(ret)+" ";header+=f.friendly+"("+join(params)+")";
            if(f.flags&0x40)issue(scope,"Network replication declaration is not reconstructed");
            Json report={{"name",scope},{"native",f.native},{"flags",f.flags},{"script_size",f.size},{"decoded",true}};
            if((f.flags&0x400)||!(f.flags&2)){functions.push_back(report);return header+";\n";}
            try{auto generated=body(f,{&p,p.entry(id).outer},locals,ret);report["generated"]=true;functions.push_back(report);return header+"\n"+generated;}
            catch(const std::exception& ex){issue(scope,ex.what());report["generated"]=false;Json ast=Json::array();for(auto& n:f.nodes)ast.push_back(nodeJson(n));report["bytecode"]=ast;functions.push_back(report);return header+"\n{\n    // INCOMPLETE: "+std::string(ex.what())+"\n    // Decoded bytecode is preserved in export-report.json.\n}\n";}
        }catch(const std::exception& ex){issue(scope,ex.what());auto r=p.reader(id);functions.push_back({{"name",scope},{"decoded",false},{"raw_hex",hex(Bytes(p.data.begin()+r.pos,p.data.begin()+r.end))}});return "// INCOMPLETE function "+scope+": "+ex.what()+"\n";}
    }
    std::string members(int owner,bool isStruct=false){
        std::string out;
        for(auto wanted:{"Const","Enum","Struct","Property","Function","State"})for(int id:p.members(owner)){
            auto kind=p.kind(id);if((std::string(wanted)=="Property")?!propertyKind(kind):kind!=wanted)continue;
            try{
                if(kind=="Const")out+="const "+p.entry(id).name+" = "+p.constant(id)+";\n\n";
                else if(kind=="Enum")out+="enum "+p.entry(id).name+"\n{\n    "+join(p.enumeration(id),",\n    ")+"\n};\n\n";
                else if(kind=="Struct")out+="struct "+p.entry(id).name+(p.entry(id).super?" extends "+leaf(p.ref(p.entry(id).super)):"")+"\n{\n"+members(id,true)+"};\n\n";
                else if(propertyKind(kind)){auto prop=p.property(id);if(prop.flags&0x20)issue(p.ref(id),"Replicated property; replication block not reconstructed");out+=(isStruct?"    var ":"var ")+declaration({&p,id})+";\n";}
                else if(kind=="Function")out+=function(id)+"\n";
                else if(kind=="State"){
                    auto state=p.structure(id,false,true);out+=((state.stateFlags&2)?"auto ":"")+std::string("state ")+p.entry(id).name+(p.entry(id).super?" extends "+leaf(p.ref(p.entry(id).super)):"")+"\n{\n"+members(id);
                    if(state.nodes.size()==1&&state.nodes[0].kind=="stop")out+="    stop;\n";
                    else if(!state.nodes.empty()){issue(p.ref(id),"State label/latent bytecode needs manual reconstruction");Json ast=Json::array();for(auto& n:state.nodes)ast.push_back(nodeJson(n));functions.push_back({{"state",p.ref(id)},{"bytecode",ast}});out+="    // INCOMPLETE state script: see report\n";}
                    if(state.ignore!=UINT64_MAX)issue(p.ref(id),"State ignore mask retained in report, ignores declaration not reconstructed");
                    functions.push_back({{"state",p.ref(id)},{"flags",state.stateFlags},{"probe",state.probe},{"ignore",state.ignore},{"label_offset",state.labelOffset}});out+="}\n\n";
                }
            }catch(const std::exception& ex){issue(p.ref(id),ex.what());out+="// INCOMPLETE "+p.ref(id)+": "+ex.what()+"\n";}
        }return out;
    }
    std::string defaults(int id,const StructInfo& s){
        auto r=p.reader(id);r.pos=s.tail;r.skip(16);int count=r.index();if(count<0||count>1000000)throw std::runtime_error("Invalid class dependency count");for(int i=0;i<count;++i){p.ref(r.index());r.skip(8);}
        count=r.index();if(count<0||count>100000)throw std::runtime_error("Invalid class package imports");while(count--)p.name(r.index());
        auto within=p.ref(r.index());auto config=p.name(r.index());
        if(within!="Core.Object"&&within!="None")issue(p.ref(id),"Nondefault within: "+within);
        if(s.classFlags&4){
            if(lower(config)=="none")configDeclaration=" config";
            else if(std::regex_match(config,std::regex("[A-Za-z_][A-Za-z_0-9]*")))configDeclaration=" config("+config+")";
            else issue(p.ref(id),"Unsupported config class name: "+config);
        }
        count=r.index();if(count<0||count>100000)throw std::runtime_error("Invalid hide category count");while(count--)p.name(r.index());
        std::string out="defaultproperties\n{\n";
        for(size_t tags=0;;++tags){if(tags>100000)throw std::runtime_error("Default tag limit");auto name=p.name(r.index());if(name=="None")break;int info=r.byte(),kind=info&15,sizeCode=(info>>4)&7;std::string structName;
            if(kind==10)structName=p.name(r.index());
            int size=0;switch(sizeCode){case 0:size=1;break;case 1:size=2;break;case 2:size=4;break;case 3:size=12;break;case 4:size=16;break;case 5:size=r.byte();break;case 6:size=r.u16();break;case 7:size=r.i32();break;}
            int arrayIndex=-1;if((info&128)&&kind!=3){int b=r.byte();if(b<128)arrayIndex=b;else if(b<192)arrayIndex=((b&63)<<8)|r.byte();else{arrayIndex=(b&63)<<24;arrayIndex|=int(r.byte())<<16;arrayIndex|=int(r.byte())<<8;arrayIndex|=r.byte();}}
            std::string value;
            if(kind==3)value=(info&128)?"True":"False";
            else{if(size<0)throw std::runtime_error("Negative default size");r.require(size_t(size));Reader v(p.data,r.pos,size_t(size));r.skip(size_t(size));
                if(kind==1)value=std::to_string(v.byte());else if(kind==2)value=std::to_string(v.i32());else if(kind==4)value=Json(v.f32()).dump();else if(kind==6)value="'"+p.name(v.index())+"'";
                else if(kind==13)value=quote(v.string());else if(kind==5){int object=v.index();value=object?p.kind(object)+"'"+p.ref(object)+"'":"None";}
                else if(kind==10&&(lower(structName)=="vector"||lower(structName)=="rotator")){
                    std::vector<std::string> parts;for(auto label:lower(structName)=="vector"?std::vector<std::string>{"X","Y","Z"}:std::vector<std::string>{"Pitch","Yaw","Roll"})parts.push_back(label+"="+(lower(structName)=="vector"?Json(v.f32()).dump():std::to_string(v.i32())));value="("+join(parts)+")";
                }else{issue(p.ref(id)+".default."+name,"Unsupported tagged default type "+std::to_string(kind)+"; raw bytes retained");out+="    // INCOMPLETE "+name+" raw="+hex(Bytes(p.data.begin()+v.pos,p.data.begin()+v.end))+"\n";continue;}
                if(v.pos!=v.end)throw std::runtime_error("Default payload size mismatch for "+name);
            }
            out+="    "+name+(arrayIndex>=0?"("+std::to_string(arrayIndex)+")":"")+"="+value+"\n";
        }
        if(r.pos!=r.end)throw std::runtime_error("Trailing class/default bytes");return out+"}\n";
    }
};
Json Context::decompile(int classId,bool force) const {
    auto& p=*main;if(classId<1||size_t(classId)>p.exports.size()||p.kind(classId)!="Class")throw std::runtime_error("Select an exported class: package="+p.path.u8string()+", export_id="+std::to_string(classId));
    Writer w{*this,p};Json result={{"class",p.ref(classId)},{"id",classId},{"method","bytecode"},{"status","recovered"}};
    if(!force){try{auto source=p.scriptText(classId);if(!source.is_null()){
        // Validate the declaration after removing comments, not just a substring.
        auto text=source["text"].get<std::string>();std::string clean=std::regex_replace(text,std::regex(R"(/\*[\s\S]*?\*/|//[^\r\n]*)")," ");
        std::smatch match;if(!std::regex_search(clean,match,std::regex(R"(\bclass\s+([A-Za-z_][A-Za-z_0-9]*))",std::regex::icase))||lower(match[1])!=lower(p.entry(classId).name))throw std::runtime_error("ScriptText class declaration mismatch");
        result["method"]="ScriptText";result["status"]="source";result["code"]=text;result["raw_hex"]=source["raw_hex"];result["encoding"]=source["encoding"];result["issues"]=w.issues;return result;
    }}catch(const std::exception& ex){w.issue(p.ref(classId)+".ScriptText",ex.what());}}
    auto s=p.structure(classId,true);std::string header="class "+p.entry(classId).name+(p.entry(classId).super?" extends "+p.ref(p.entry(classId).super):"");
    if(s.classFlags&1)header+=" abstract";if(s.classFlags&0x80)header+=" transient";if(s.classFlags&0x1000)header+=" native";
    if(s.classFlags&0x400000)header+=" dynamicrecompile";
    for(int id:p.members(classId))while(lower(p.entry(id).name)==lower(w.helper))w.helper+="_";
    std::string code=w.members(classId);
    if(w.contextHelper)code+="// Preserve null-context semantics for an inlined integer constant.\nstatic function int "+w.helper+"(Object Owner, int Value)\n{\n    if (Owner == None) return 0;\n    return Value;\n}\n\n";
    try{code+=w.defaults(classId,s);}catch(const std::exception& ex){w.issue(p.ref(classId)+".defaults",ex.what());auto r=p.reader(classId);result["class_tail_hex"]=hex(Bytes(p.data.begin()+s.tail,p.data.begin()+r.end));code+="// INCOMPLETE defaultproperties: "+std::string(ex.what())+"\n";}
    if(!s.nodes.empty())w.issue(p.ref(classId),"Class-level bytecode/replication is not reconstructed");
    code=header+w.configDeclaration+";\n\n"+code;
    result["class_flags"]=s.classFlags;result["functions"]=w.functions;result["issues"]=w.issues;result["status"]=w.issues.empty()?"recovered":"partial";
    result["code"]="// uExplorer: "+p.ref(classId)+"; "+result["status"].get<std::string>()+" from bytecode.\n// Recovered source is not a proof of compilation/semantic equivalence.\n\n"+code;
    result["encoding"]="utf-8";return result;
}
}
