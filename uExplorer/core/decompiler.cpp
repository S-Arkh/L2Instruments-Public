#include "package.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <iterator>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace ue {
static std::string quote(const std::string& s){std::string out="\"";for(char c:s){switch(c){case '\\':out+="\\\\";break;case '"':out+="\\\"";break;case '\r':out+="\\r";break;case '\n':out+="\\n";break;case '\t':out+="\\t";break;default:out+=c;}}return out+'"';}
static std::string join(const std::vector<std::string>& parts,const std::string& sep=", "){std::string r;for(size_t i=0;i<parts.size();++i){if(i)r+=sep;r+=parts[i];}return r;}
static bool propertyKind(const std::string& s){return s.size()>=8&&s.substr(s.size()-8)=="Property";}
Context::Context(const std::filesystem::path& file,const std::vector<std::filesystem::path>& directories,const std::string& bytecodeProfile){
    main=std::make_shared<Package>(file);packages.push_back(main);
    main->setBytecodeProfile(bytecodeProfile);
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
    if(bytecodeProfile=="sdk-client-sort")for(auto& p:packages)if(p->version==126&&p->licensee==0)p->setBytecodeProfile(bytecodeProfile);
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
    Json unrecoveredProperties=Json::array();
    Json unrecoveredDefaults=Json::array();
    std::set<int> replicatedMembers;
    bool classScriptRecovered=false;
    int rootClass=0;
    int currentFunction=0;
    int currentEventParameter=0;
    mutable std::vector<std::string> typeDependencies;
    void typeDependency(Symbol target) const {
        if(!target||target.p!=&p||target.id==rootClass)return;
        std::set<int> ancestry;
        for(auto base=Symbol{&p,rootClass};base&&base.p==&p;base=ctx.resolve(*base.p,base.p->entry(base.id).super)){
            if(!ancestry.insert(base.id).second)throw std::runtime_error("Cyclic class inheritance");
        }
        if(ancestry.count(target.id))return;
        std::vector<std::string> chain;std::set<int> seen;
        for(auto base=target;base&&base.p==&p&&!ancestry.count(base.id);base=ctx.resolve(*base.p,base.p->entry(base.id).super)){
            if(!seen.insert(base.id).second)throw std::runtime_error("Cyclic type dependency inheritance");
            chain.push_back(base.p->entry(base.id).name);
        }
        // The SDK's early dependson parsing needs the owner's parent parsed first.
        for(auto it=chain.rbegin();it!=chain.rend();++it)
            if(std::find(typeDependencies.begin(),typeDependencies.end(),*it)==typeDependencies.end())typeDependencies.push_back(*it);
    }
    std::string qualifiedType(Symbol target) const {
        if(!target)throw std::runtime_error("Unresolved named property type");
        auto owner=target.p->entry(target.id).outer;
        if(owner&&target.p->kind(owner)=="Class"){
            typeDependency({target.p,owner});
            return target.p->entry(owner).name+"."+target.p->entry(target.id).name;
        }
        return target.p->entry(target.id).name;
    }
    std::string stateIgnores(int id,uint64_t mask){
        // Probe-name indices 300..363, verified against the client runtime and
        // old-profile ScriptText. Reserved/aggregate bits are not source events.
        static const char* names[]={"Spawned","Destroyed","GainedChild","LostChild",nullptr,nullptr,
            "Trigger","UnTrigger","Timer","HitWall","Falling","Landed","PhysicsVolumeChange","Touch","UnTouch","Bump",
            "BeginState","EndState","BaseChange","Attach","Detach","ActorEntered","ActorLeaving","ZoneChange",
            "AnimEnd","EndedRotation","InterpolateEnd","EncroachingOn","EncroachedBy","NotifyTurningInPlace",
            "HeadVolumeChange","PostTouch","PawnEnteredVolume","MayFall","CheckDirectionChange","PawnLeavingVolume",
            "Tick","PlayerTick","ModifyVelocity","CheckMovementTransition","SeePlayer","EnemyNotVisible","HearNoise",
            "UpdateEyeHeight","SeeMonster","SeeFriend","SpecialHandling","BotDesireability","NotifyBump",
            "NotifyPhysicsVolumeChange","AIHearSound","NotifyHeadVolumeChange","NotifyLanded","NotifyHitWall",
            "PostNetReceive","PreBeginPlay","BeginPlay","PostBeginPlay",nullptr,"PhysicsChangedFor",
            "ActorEnteredVolume","ActorLeavingVolume","PrepareForMove",nullptr};
        static_assert(sizeof(names)/sizeof(*names)==64);
        std::vector<std::string> ignored;
        for(unsigned bit=0;bit<64;++bit)if(!(mask&(uint64_t(1)<<bit))){
            if(!names[bit]||!findCall(names[bit],{&p,id}))throw std::runtime_error("Unresolved/reserved state ignore bit "+std::to_string(bit));
            ignored.push_back(names[bit]);
        }
        return ignored.empty()?"":"    ignores "+join(ignored)+";\n\n";
    }
    bool contextHelper=false;
    std::map<std::string,std::pair<std::string,std::string>> typedContextHelpers;
    std::string configDeclaration;
    std::string withinDeclaration;
    std::string helper="__UXContextInt";
    void issue(const std::string& scope,const std::string& message){
        std::string code="generation_incomplete";
        if(message.rfind("Unsupported expression ",0)==0)code="unsupported_expression";
        else if(message.rfind("Unsupported property type ",0)==0)code="unsupported_property_type";
        else if(message.rfind("Delegate ",0)==0)code="invalid_delegate_metadata";
        issues.push_back({{"scope",scope},{"message",message},{"code",code}});
    }
    Symbol delegateSignature(Symbol prop) const {
        if(!prop||prop.p->kind(prop.id)!="DelegateProperty")throw std::runtime_error("Delegate property reference is invalid");
        auto signature=ctx.resolve(*prop.p,prop.p->property(prop.id).ref);
        if(!signature||signature.p->kind(signature.id)!="Function"||!(signature.p->function(signature.id).flags&0x100000))
            throw std::runtime_error("Delegate signature is missing or not a delegate function");
        return signature;
    }
    bool delegateStorage(Symbol prop) const {
        auto signature=delegateSignature(prop);
        return prop.p->property(prop.id).dim==1&&prop.p==signature.p&&prop.p->entry(prop.id).outer==signature.p->entry(signature.id).outer
            &&lower(prop.p->entry(prop.id).name)==lower("__"+signature.p->entry(signature.id).name+"__Delegate");
    }
    std::string propertyName(Symbol prop,const std::string& fallback="") const {
        if(!prop){if(!fallback.empty())return leaf(fallback);throw std::runtime_error("Unresolved property reference");}
        if(prop.p->kind(prop.id)=="DelegateProperty"&&delegateStorage(prop)){
            auto signature=delegateSignature(prop);return signature.p->function(signature.id).friendly;
        }
        return prop.p->entry(prop.id).name;
    }
    std::string type(Symbol s,int depth=0) const {
        if(!s||depth>32)throw std::runtime_error("Unresolved/recursive property type");auto v=s.p->property(s.id);auto& k=v.kind;
        if(k=="IntProperty")return "int";if(k=="BoolProperty")return "bool";if(k=="FloatProperty")return "float";if(k=="StrProperty")return "string";if(k=="NameProperty")return "name";
        if(k=="ByteProperty"){
            if(!v.ref)return "byte";
            auto en=ctx.resolve(*s.p,v.ref);
            if(en)return qualifiedType(en);
            return leaf(s.p->ref(v.ref));
        }
        if(k=="ObjectProperty")return leaf(s.p->ref(v.ref));
        if(k=="StructProperty")return qualifiedType(ctx.resolve(*s.p,v.ref));
        if(k=="ClassProperty")return "class<"+leaf(s.p->ref(v.meta))+">";
        if(k=="ArrayProperty"){
            auto inner=type(ctx.resolve(*s.p,v.ref),depth+1);
            return "array<"+inner+(!inner.empty()&&inner.back()=='>'?" >":">");
        }
        if(k=="DelegateProperty")throw std::runtime_error("Delegate property is not compiler-generated storage; declaration syntax is unverified");
        if(k=="PtrProperty"){
            int owner=s.p->entry(s.id).outer;auto kind=owner?s.p->kind(owner):"";
            bool field=(kind=="Class"||kind=="Struct")&&(v.flags==0x1000||v.flags==0x2000);
            bool local=kind=="Function"&&!(v.flags&~0x580u);
            if(v.dim<1||v.dim>2048||(!field&&!local))
                throw std::runtime_error("Unsupported property type PtrProperty: unsupported owner, flags or dimension");
            return "pointer"; // Explicit ucc64 extension spelling, not a recovered original keyword.
        }
        throw std::runtime_error("Unsupported property type "+k);
    }
    std::vector<Symbol> fields(Symbol function) const {
        auto f=function.p->function(function.id);int id=f.fields[3];std::set<int> seen;std::vector<Symbol> result;
        while(id){if(!seen.insert(id).second)throw std::runtime_error("Cyclic function property list");if(function.p->entry(id).outer!=function.id)throw std::runtime_error("Function property owner mismatch");auto prop=function.p->property(id);result.push_back({function.p,id});id=prop.next;}return result;
    }
    std::string declaration(Symbol s,bool parameter=false,const std::string& inlineType="") const {
        auto prop=s.p->property(s.id);std::string out;
        if(parameter){if(prop.flags&0x10)out+="optional ";if(prop.flags&0x100)out+="out ";if(prop.flags&0x800)out+="coerce ";}
        else{if(prop.flags&0x1000)out+="native ";if(prop.flags&2)out+="const ";if(prop.flags&0x2000)out+="transient ";if(prop.flags&0x4000)out+="config ";if(prop.flags&0x8000)out+="localized ";if(prop.flags&0x40000)out+="globalconfig ";}
        out+=(inlineType.empty()?type(s):inlineType)+" "+s.p->entry(s.id).name;if(prop.dim>1)out+="["+std::to_string(prop.dim)+"]";return out;
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
        if(n.kind=="context"||n.kind=="class_context")return nodeType(n.children.at(1),receiver(n.children.at(0),owner));
        if(n.kind=="native"){
            auto found=ctx.natives.find(n.index);
            return found==ctx.natives.end()?Symbol{}:returnType(found->second.first);
        }
        if(n.kind=="final_call")return returnType(ctx.resolve(p,n.ref));
        if(n.kind=="delegate_property")return returnType(delegateSignature(ctx.resolve(p,n.ref)));
        if(n.kind=="virtual_call"||n.kind=="global_call")return returnType(findCall(n.text,owner));
        if(n.kind=="array_element"||n.kind=="dynamic_array_element"){
            auto s=nodeType(n.children.at(1),owner);if(s&&s.p->property(s.id).kind=="ArrayProperty")return ctx.resolve(*s.p,s.p->property(s.id).ref);return s;
        }return {};
    }
    Symbol receiver(const Node& n,Symbol owner) const {
        if(n.kind=="new")return receiver(n.children.at(3),owner);
        if(n.kind=="object"||n.kind=="dynamic_cast"||n.kind=="class_cast")return ctx.resolve(p,n.ref);
        auto prop=nodeType(n,owner);if(!prop)return {};auto v=prop.p->property(prop.id);return ctx.resolve(*prop.p,v.kind=="ClassProperty"?v.meta:v.ref);
    }
    static bool integerConstant(const Node& n){
        return n.kind=="int_zero"||n.kind=="int_one"||(n.kind=="constant"&&n.value.is_number_integer());
    }
    static bool integerContext(const Node& n){
        return (n.kind=="context"||n.kind=="class_context")&&n.children.size()==2&&integerConstant(n.children[1]);
    }
    std::string contextLiteral(const Node& node,Symbol owner,Symbol expected){
        const auto& value=node.children.at(1);
        std::string resultType,zero,suffix;
        if(integerConstant(value)){
            if(expected){
                auto prop=expected.p->property(expected.id);
                if(prop.kind=="ByteProperty"&&prop.ref){
                    auto en=ctx.resolve(*expected.p,prop.ref);
                    if(!en)throw std::runtime_error("Unresolved context enum");
                    auto names=en.p->enumeration(en.id);
                    if(names.empty())throw std::runtime_error("Empty context enum");
                    resultType=type(expected);zero=names[0];suffix="Enum_"+resultType;
                    std::replace(suffix.begin(),suffix.end(),'.','_');
                }
            }
            if(resultType.empty()){
                contextHelper=true;
                return helper+"("+expression(node.children[0],owner)+", "+expression(value,owner)+")";
            }
        }else if(value.kind=="constant"&&value.value.is_number_float()){resultType="float";zero="0.0";suffix="Float";}
        else if(value.kind=="true"||value.kind=="false"){resultType="bool";zero="false";suffix="Bool";}
        else if(value.kind=="name"){resultType="name";zero="'None'";suffix="Name";}
        else if(value.kind=="string"){resultType="string";zero="\"\"";suffix="String";}
        else return {};
        auto found=typedContextHelpers.find(resultType);
        if(found==typedContextHelpers.end()){
            // UCC's token buffer includes its terminating zero. Keep generated
            // identifiers below 64 characters, including collision suffixes.
            auto base=(helper+"_"+suffix).substr(0,48),name=base;bool occupied=true;
            size_t collision=0;
            while(occupied){
                occupied=false;
                std::set<std::pair<const Package*,int>> seen;
                for(auto scope=Symbol{&p,rootClass};scope;scope=ctx.resolve(*scope.p,scope.p->entry(scope.id).super)){
                    if(!seen.insert({scope.p,scope.id}).second)throw std::runtime_error("Cyclic context helper inheritance");
                    for(int id:scope.p->members(scope.id))if(lower(scope.p->entry(id).name)==lower(name))occupied=true;
                }
                for(auto& entry:typedContextHelpers)if(lower(entry.second.first)==lower(name))occupied=true;
                if(occupied)name=base+"_"+std::to_string(++collision);
            }
            found=typedContextHelpers.emplace(resultType,std::make_pair(name,zero)).first;
        }
        return found->second.first+"("+expression(node.children[0],owner)+", "+expression(value,owner,expected)+")";
    }
    std::string namedConstant(const Node& value,Symbol scope) const {
        // A ByteConst can be a folded enum member. A same-valued integer Const
        // is not its type-equivalent source representation (nor its known name).
        if(value.op==0x24)return {};
        std::string text;
        if(value.kind=="int_zero")text="0";
        else if(value.kind=="int_one")text="1";
        else if(value.kind=="constant")text=value.value.dump();
        else if(value.kind=="true"||value.kind=="false")text=value.kind;
        else if(value.kind=="string")text=quote(value.text);
        else if(value.kind=="name")text="'"+value.text+"'";
        else return {};
        std::set<std::pair<const Package*,int>> seen;std::set<std::string> shadowed;
        for(;scope;scope=ctx.resolve(*scope.p,scope.p->entry(scope.id).super)){
            if(!seen.insert({scope.p,scope.id}).second)throw std::runtime_error("Cyclic constant inheritance");
            for(int id:scope.p->members(scope.id)){
                auto name=scope.p->entry(id).name;
                if(!shadowed.insert(lower(name)).second||scope.p->kind(id)!="Const")continue;
                auto original=scope.p->constant(id);
                auto start=original.find_first_not_of(" \t\r\n"),end=original.find_last_not_of(" \t\r\n");
                if(start!=original.npos&&original.substr(start,end-start+1)==text)return name;
            }
        }
        return {};
    }
    std::string eventConstant(const Node& value) const {
        if(!integerConstant(value))return {};
        auto number=value.kind=="int_zero"?int64_t(0):value.kind=="int_one"?int64_t(1):value.value.get<int64_t>();
        std::set<std::string> shadowed;
        if(currentFunction)for(auto field:fields({&p,currentFunction}))shadowed.insert(lower(field.p->entry(field.id).name));
        std::vector<std::string> matches;std::set<std::pair<const Package*,int>> seen;
        for(auto scope=Symbol{&p,rootClass};scope;scope=ctx.resolve(*scope.p,scope.p->entry(scope.id).super)){
            if(!seen.insert({scope.p,scope.id}).second)throw std::runtime_error("Cyclic event constant inheritance");
            for(int id:scope.p->members(scope.id)){
                auto name=scope.p->entry(id).name,key=lower(name);
                if(!shadowed.insert(key).second||key.rfind("ev_",0)!=0||scope.p->kind(id)!="Const")continue;
                auto text=scope.p->constant(id);auto start=text.find_first_not_of(" \t\r\n");
                if(start==text.npos)continue;text=text.substr(start,text.find_last_not_of(" \t\r\n")-start+1);
                try{
                    size_t used=0;auto at=text[0]=='-'||text[0]=='+'?1u:0u;
                    int base=text.size()>at+2&&text[at]=='0'&&(text[at+1]=='x'||text[at+1]=='X')?16:10;
                    auto parsed=std::stoll(text,&used,base);
                    if(used==text.size()&&parsed==number)matches.push_back(name);
                }catch(const std::exception&){}
            }
        }
        // Bytecode retains the value, not the original spelling. Ambiguous aliases
        // remain numeric rather than arbitrarily claiming an original event name.
        return matches.size()==1?matches[0]:std::string{};
    }
    std::string caseExpression(const Node& value,const Node& selector,Symbol owner){
        if(currentEventParameter&&selector.kind=="local"&&selector.ref==currentEventParameter){
            auto name=eventConstant(value);if(!name.empty())return name;
        }
        return expression(value,owner,nodeType(selector,owner));
    }
    std::string expression(const Node& n,Symbol owner,Symbol expected={},bool context=false){
        auto& k=n.kind;auto& c=n.children;
        if(expected){
            auto target=expected.p->property(expected.id);
            auto actual=nodeType(n,owner);
            if(target.kind=="ByteProperty"&&target.ref&&actual){
                auto source=actual.p->property(actual.id);
                if(source.kind=="ByteProperty"){
                    auto wanted=ctx.resolve(*expected.p,target.ref);
                    auto found=source.ref?ctx.resolve(*actual.p,source.ref):Symbol{};
                    if(!found||found.p!=wanted.p||found.id!=wanted.id)
                        return leaf(expected.p->ref(target.ref))+"("+expression(n,owner,{},context)+")";
                }
            }
        }
        // A context selects the callee, not the scope evaluating its arguments.
        auto argumentOwner=context&&currentFunction?Symbol{&p,p.entry(currentFunction).outer}:owner;
        auto e=[&](size_t i){return expression(c.at(i),owner);};
        auto number=[&]()->std::string{if(k=="int_zero")return "0";if(k=="int_one")return "1";return n.value.dump();};
        if(k=="int64_constant")return "INT64("+quote(n.value.dump())+")";
        if(k=="array_sort")return e(0)+".Sort("+e(1)+")";
        if(k=="constant"||k=="int_zero"||k=="int_one"){
            if(n.value.is_number_float()&&!std::isfinite(n.value.get<double>()))throw std::runtime_error("Nonfinite float");
            if(expected){auto prop=expected.p->property(expected.id);if(prop.kind=="ByteProperty"&&prop.ref){int value=std::stoi(number());auto en=ctx.resolve(*expected.p,prop.ref);if(en){auto members=en.p->enumeration(en.id);if(value>=0&&size_t(value)<members.size())return members[value];}return leaf(expected.p->ref(prop.ref))+"("+number()+")";}}
            return number();
        }
        if(k=="local"||k=="instance"||k=="native_parameter")return propertyName(ctx.resolve(p,n.ref),n.text);
        if(k=="default")return "default."+propertyName(ctx.resolve(p,n.ref),n.text);
        if(k=="delegate_property"){
            auto prop=ctx.resolve(p,n.ref);auto signature=delegateSignature(prop);
            if(!n.value.is_string()||lower(n.value.get<std::string>())!=lower(signature.p->function(signature.id).friendly))
                throw std::runtime_error("Delegate expression signature does not match its property");
            std::vector<Symbol> params;
            for(auto param:fields(signature))if((param.p->property(param.id).flags&0x480)==0x80)params.push_back(param);
            std::vector<std::string> args;
            for(size_t i=0;i<c.size()&&c[i].kind!="end_parameters";++i)
                args.push_back(expression(c[i],argumentOwner,i<params.size()?params[i]:Symbol{}));
            return propertyName(prop)+"("+join(args)+")";
        }
        if(k=="delegate_name")return n.text;
        if(k=="new"){
            if(c.size()!=4||c[3].kind=="nothing")throw std::runtime_error("Invalid new expression operands");
            size_t count=3;while(count&&c[count-1].kind=="nothing")--count;
            std::vector<std::string> args;for(size_t i=0;i<count;++i){
                if(c[i].kind=="nothing")throw std::runtime_error("Unsupported new expression: omitted non-trailing operand");
                args.push_back(e(i));
            }
            return "(new"+(count?"("+join(args)+")":"")+" "+e(3)+")";
        }
        if(k=="nothing"||k=="end_parameters")return "";
        if(k=="skip"||k=="bool_variable"||k=="discard_string")return e(0);
        if(k=="true"||k=="false"||k=="self")return k;if(k=="none")return "None";
        if(k=="string")return quote(n.text);if(k=="name")return "'"+n.text+"'";
        if(k=="object"){
            if(!n.ref)return "None";
            auto kind=p.kind(n.ref),path=n.text;
            // Unlike a class literal, the SDK resolves Enum objects by their
            // package-qualified object path even for same-package references.
            if(kind=="Enum"&&n.ref>0)path=p.path.stem().u8string()+"."+path;
            return kind+"'"+path+"'";
        }
        if(k=="native"||k=="final_call"||k=="virtual_call"||k=="global_call"){
            Symbol call;Function f;std::string name=leaf(n.text);
            if(k=="native"){auto it=ctx.natives.find(n.index);if(it==ctx.natives.end())throw std::runtime_error("Unknown/conflicting native "+std::to_string(n.index)+" at PC "+std::to_string(n.pc));call=it->second.first;f=it->second.second;name=f.friendly;}
            else{call=k=="final_call"?ctx.resolve(p,n.ref):findCall(n.text,owner);if(call)f=call.p->function(call.id);}
            std::vector<Symbol> params;if(call)for(auto prop:fields(call))if((prop.p->property(prop.id).flags&0x480)==0x80)params.push_back(prop);
            Symbol enumOperand;
            if(k=="native"&&(f.flags&0x1000)&&(name=="=="||name=="!="||name=="<"||name==">"||name=="<="||name==">="))for(auto& operand:c){
                if(operand.kind=="cast"&&operand.index==0x3a&&!operand.children.empty()){
                    auto candidate=nodeType(operand.children[0],argumentOwner);
                    if(candidate){auto prop=candidate.p->property(candidate.id);if(prop.kind=="ByteProperty"&&prop.ref)enumOperand=candidate;}
                }
            }
            std::vector<std::string> args;for(size_t i=0;i<c.size()&&c[i].kind!="end_parameters";++i){
                auto expectedArg=i<params.size()?params[i]:Symbol{};
                if(currentEventParameter&&k=="native"&&(f.flags&0x1000)&&(name=="=="||name=="!=")&&
                   params.size()==2&&i<2&&c.size()>=2&&
                   params[0].p->property(params[0].id).kind=="IntProperty"&&
                   params[1].p->property(params[1].id).kind=="IntProperty"){
                    const auto& selector=c[1-i];
                    if(selector.kind=="local"&&selector.ref==currentEventParameter){
                        auto event=eventConstant(c[i]);if(!event.empty()){args.push_back(event);continue;}
                    }
                }
                if(i==0&&call&&(f.flags&0x400)&&expectedArg&&expectedArg.p->property(expectedArg.id).kind=="IntProperty"
                   &&(lower(f.friendly)=="registerevent"||lower(f.friendly)=="executeevent"||lower(f.friendly)=="unregisterevent")){
                    auto event=eventConstant(c[i]);if(!event.empty()){args.push_back(event);continue;}
                }
                if(enumOperand&&c[i].kind=="cast"&&c[i].index==0x3a&&!c[i].children.empty()){
                    const auto& operand=c[i].children[0];
                    // A leading foreign enum literal has no parser type hint.
                    // An enum conversion of its numeric value emits ByteConst,
                    // unlike byte(number), which emits an extra primitive cast.
                    if(i==0&&operand.op==0x24){
                        auto prop=enumOperand.p->property(enumOperand.id);
                        args.push_back(leaf(enumOperand.p->ref(prop.ref))+"("+operand.value.dump()+")");
                    }else args.push_back(expression(operand,argumentOwner,operand.kind=="cast"?Symbol{}:enumOperand));
                    continue;
                }
                args.push_back(expression(c[i],argumentOwner,expectedArg));
            }
            if(k=="native"&&(f.flags&0x1000)){
                if(n.index==154&&args.size()==2){
                    auto left=nodeType(c[0],owner),right=nodeType(c[1],owner);
                    if((left&&left.p->kind(left.id)=="PtrProperty")||(right&&right.p->kind(right.id)=="PtrProperty"))
                        return "PointerEqual("+args[0]+", "+args[1]+")";
                }
                if(args.size()==2)return "("+args[0]+" "+name+" "+args[1]+")";
                if(args.size()==1){
                    auto operand=args[0];
                    // Signed constants already contain their sign. Keep prefix
                    // operators lexically separate from it (e.g. -(-30), not --30).
                    if((f.flags&0x10)&&!operand.empty()&&(operand[0]=='-'||operand[0]=='+'))operand="("+operand+")";
                    return "("+((f.flags&0x10)?name+operand:operand+name)+")";
                }
                throw std::runtime_error("Native operator arity mismatch");
            }
            if(k=="global_call")name="global."+name;
            if(k=="final_call"&&!context&&call&&owner&&call.p==owner.p&&call.p->entry(call.id).outer!=owner.id){
                auto same=findCall(name,owner);if(same&&same.id!=call.id)name="super."+name;
            }
            return name+"("+join(args)+")";
        }
        if(k=="context"||k=="class_context"){
            auto recv=receiver(c.at(0),owner);
            // Recover a serialized constant's name when its literal spelling
            // matches exactly. This retains the original context bytecode and
            // null behavior, without adding a helper call or losing its type.
            // The SDK accepts object.Const, but class.static requires a function.
            bool enumExpected=false;
            if(expected){auto prop=expected.p->property(expected.id);enumExpected=prop.kind=="ByteProperty"&&prop.ref;}
            auto constant=k=="context"&&!enumExpected?namedConstant(c.at(1),recv):std::string{};
            if(!constant.empty())return e(0)+(k=="class_context"?".static.":".")+constant;
            auto literal=contextLiteral(n,owner,expected);if(!literal.empty())return literal;
            auto member=expression(c.at(1),recv,{},true);
            return e(0)+(k=="class_context"&&member.rfind("default.",0)!=0?".static.":".")+member;
        }
        if(k=="cast"){
            if(n.index==0x3a&&expected&&c.at(0).kind=="constant"){
                auto prop=expected.p->property(expected.id);
                if(prop.kind=="ByteProperty"&&prop.ref)return expression(c[0],owner,expected);
            }
            // ECastToken 0x39 (the operand of EX_PrimitiveCast) is rotator -> vector.
            if(n.index==0x39)return "vector("+e(0)+")";
            static const std::vector<std::string> cast={"int","bool","float","byte","bool","float","byte","int","float","byte","int","bool","bool","bool","vector","byte","int","bool","float","vector","rotator","bool","rotator","bool","string","string","string","string","string","string","string","string","INT64","INT64","INT64","INT64","INT64","byte","int","bool","float","string"};
            if(n.index<0x3a||n.index>0x63)throw std::runtime_error("Unknown cast "+std::to_string(n.index));auto target=cast.at(size_t(n.index-0x3a));
            if(expected){auto prop=expected.p->property(expected.id);if(prop.kind=="ByteProperty"&&prop.ref&&(target=="byte"||target=="int"))target=leaf(expected.p->ref(prop.ref));}
            if(target=="int"&&integerConstant(c[0]))return e(0);
            if(target=="int"&&integerContext(c[0])&&(c[0].kind=="class_context"||namedConstant(c[0].children[1],receiver(c[0].children[0],owner)).empty()))return e(0);
            return target+"("+e(0)+")";
        }
        if(k=="dynamic_cast"||k=="class_cast")return leaf(n.text)+"("+e(0)+")";
        if(k=="array_element"||k=="dynamic_array_element")return e(1)+"["+e(0)+"]";
        if(k=="array_length")return e(0)+".Length";
        if(k=="struct_member")return e(0)+"."+propertyName(ctx.resolve(p,n.ref),n.text);
        if(k=="struct_equal"||k=="struct_not_equal")return "("+e(0)+(k=="struct_equal"?" == ":" != ")+e(1)+")";
        if(k=="assign"||k=="assign_bool"||k=="assign_delegate")return e(0)+" = "+expression(c.at(1),owner,nodeType(c[0],owner));
        if(k=="array_insert"||k=="array_remove")return e(0)+(k=="array_insert"?".Insert(":".Remove(")+e(1)+", "+e(2)+")";
        if(k=="rotation"||k=="vector"){std::vector<std::string> values;for(auto& value:n.value)values.push_back(value.dump());return (k=="vector"?"vect(":"rot(")+join(values)+")";}
        if(k=="assert")return "assert("+e(0)+")";
        throw std::runtime_error("Unsupported expression "+k+" at PC "+std::to_string(n.pc));
    }
    std::string structuredBody(const Function& f,Symbol owner,const std::string& locals,Symbol ret,bool stateCode=false,
                               const std::map<int,std::vector<std::string>>* labels=nullptr){
        const auto& roots=f.nodes;std::map<int,size_t> positions;
        for(size_t i=0;i<roots.size();++i)positions[roots[i].pc]=i;
        positions[f.size]=roots.size();
        struct Loop { int exit, next; bool iterator; };
        std::vector<Loop> loops;
        std::set<int> emittedLabels;
        auto target=[&](int pc){auto it=positions.find(pc);if(it==positions.end())throw std::runtime_error("Iterator branch into expression");return it->second;};
        auto statement=[&](const Node& n){auto s=expression(n,owner);if(n.kind=="native"&&s.size()>1&&s.front()=='('&&s.back()==')')s=s.substr(1,s.size()-2);return s+";";};
        std::function<std::string(size_t,size_t,int)> block;
        block=[&](size_t first,size_t end,int depth)->std::string{
            if(depth>64)throw std::runtime_error("Iterator control-flow nesting limit");
            std::string out,pad(size_t(depth)*4,' ');
            for(size_t i=first;i<end;){const auto& n=roots[i];
                if(labels){
                    auto found=labels->find(n.pc);
                    if(found!=labels->end()){
                        if(!emittedLabels.insert(n.pc).second)throw std::runtime_error("State label emitted twice");
                        for(auto label=found->second.rbegin();label!=found->second.rend();++label)out+=pad+*label+":\n";
                    }
                }
                if(stateCode&&std::any_of(loops.begin(),loops.end(),[](const Loop& loop){return loop.iterator;})){
                    std::function<void(const Node&)> validate=[&](const Node& node){
                        uint32_t flags=0;
                        if(node.kind=="native"){auto found=ctx.natives.find(node.index);if(found!=ctx.natives.end())flags=found->second.second.flags;}
                        else if(node.kind=="final_call"){auto call=ctx.resolve(p,node.ref);if(call)flags=call.p->function(call.id).flags;}
                        if(flags&8)throw std::runtime_error("Latent call inside iterator is unsupported by the SDK");
                        for(auto& child:node.children)validate(child);
                    };validate(n);
                }
                if(n.kind=="iterator"){
                    size_t pop=target(n.target);
                    if(pop>=end||pop<=i+1||roots[pop].kind!="iterator_pop"||roots[pop-1].kind!="iterator_next")throw std::runtime_error("Unsupported iterator exit layout");
                    loops.push_back({n.target,roots[pop-1].pc,true});
                    auto content=block(i+1,pop-1,depth+1);loops.pop_back();
                    out+=pad+"foreach "+expression(n.children.at(0),owner)+"\n"+pad+"{\n"+content+pad+"}\n";i=pop+1;
                }else if(n.kind=="switch"){
                    std::vector<size_t> cases;size_t at=i+1;
                    for(;;){
                        if(at>=end||roots[at].kind!="case")throw std::runtime_error("Invalid iterator switch case chain");
                        cases.push_back(at);if(roots[at].target==65535)break;
                        auto next=target(roots[at].target);if(next<=at)throw std::runtime_error("Cyclic iterator switch cases");at=next;
                    }
                    size_t exit=at+1;bool hasExit=false;
                    for(size_t j=0;j+1<cases.size();++j){
                        auto last=cases[j+1]-1;
                        if(last>cases[j]&&roots[last].kind=="jump"){
                            auto to=target(roots[last].target);
                            if(to>=at+1&&to<=end){if(hasExit&&exit!=to)throw std::runtime_error("Conflicting switch exit targets");exit=to;hasExit=true;}
                        }
                    }
                    if(!hasExit)throw std::runtime_error("Unverified iterator switch exit");
                    loops.push_back({roots[exit-1].finish,-1,false});
                    std::string content;
                    for(size_t j=0;j<cases.size();++j){
                        size_t begin=cases[j],finish=j+1<cases.size()?cases[j+1]:exit;
                        if(roots[begin].target==65535&&begin+1==finish)continue;
                        content+=pad+"    "+(roots[begin].target==65535?std::string("default"):"case "+caseExpression(roots[begin].children.at(0),n.children.at(0),owner))+":\n";
                        content+=block(begin+1,finish,depth+2);
                    }
                    loops.pop_back();out+=pad+"switch ("+expression(n.children.at(0),owner)+")\n"+pad+"{\n"+content+pad+"}\n";i=exit;
                }else if(n.kind=="jump_if_not"){
                    size_t otherwise=target(n.target);
                    if(otherwise<=i||otherwise>end)throw std::runtime_error("Unsupported iterator conditional boundary");
                    // A backwards edge immediately before the false target is a while.
                    if(otherwise>i+1&&roots[otherwise-1].kind=="jump"&&roots[otherwise-1].target==n.pc){
                        loops.push_back({n.target,n.pc,false});auto content=block(i+1,otherwise-1,depth+1);loops.pop_back();
                        out+=pad+"while ("+expression(n.children.at(0),owner)+")\n"+pad+"{\n"+content+pad+"}\n";i=otherwise;
                    }else{
                        size_t join=otherwise;bool hasElse=false;
                        if(otherwise>i+1&&roots[otherwise-1].kind=="jump"){
                            auto next=target(roots[otherwise-1].target);
                            // Do not mistake break/continue edges for an else join.
                            bool loopEdge=!loops.empty()&&(roots[otherwise-1].target==loops.back().exit||roots[otherwise-1].target==loops.back().next);
                            if(!loopEdge&&next>otherwise&&next<=end){join=next;hasElse=true;}
                        }
                        out+=pad+"if ("+expression(n.children.at(0),owner)+")\n"+pad+"{\n"+block(i+1,otherwise-(hasElse?1:0),depth+1)+pad+"}\n";
                        if(hasElse)out+=pad+"else\n"+pad+"{\n"+block(otherwise,join,depth+1)+pad+"}\n";
                        i=join;
                    }
                }else if(n.kind=="iterator_next"){
                    if(loops.empty()||!loops.back().iterator||i+1>=end||roots[i+1].kind!="jump"||roots[i+1].target!=loops.back().exit)throw std::runtime_error("Unsupported iterator continue layout");
                    out+=pad+"continue;\n";i+=2;
                }else if(n.kind=="iterator_pop"){
                    size_t after=i;while(after<end&&roots[after].kind=="iterator_pop")++after;
                    size_t active=0;for(auto& loop:loops)if(loop.iterator)++active;
                    if(after-i!=active||after>=end||roots[after].kind!="return")throw std::runtime_error("Unsupported iterator cleanup layout");
                    auto value=expression(roots[after].children.at(0),owner,ret);out+=pad+"return"+(value.empty()?"":" "+value)+";\n";i=after+1;
                }else if(n.kind=="jump"){
                    if(loops.empty())throw std::runtime_error("Unstructured jump in iterator function");
                    if(n.target==loops.back().exit)out+=pad+"break;\n";
                    else if(n.target==loops.back().next)out+=pad+"continue;\n";
                    else throw std::runtime_error("Cross-region iterator branch");
                    ++i;
                }else if(stateCode&&n.kind=="stop"){out+=pad+"stop;\n";++i;
                }else if(stateCode&&n.kind=="goto_label"){out+=pad+"goto "+expression(n.children.at(0),owner)+";\n";++i;
                }else if(n.kind=="return"){
                    if(std::any_of(loops.begin(),loops.end(),[](const Loop& loop){return loop.iterator;}))throw std::runtime_error("Iterator return without verified cleanup");
                    auto value=expression(n.children.at(0),owner,ret);
                    if(!value.empty()||i+1!=roots.size())out+=pad+"return"+(value.empty()?"":" "+value)+";\n";++i;
                }else if(n.kind=="nothing"||n.kind=="debug")++i;
                else{out+=pad+statement(n)+"\n";++i;}
            }
            return out;
        };
        auto content=block(0,roots.size(),1);
        if(labels)for(auto& entry:*labels){
            if(entry.first==f.size){
                for(auto label=entry.second.rbegin();label!=entry.second.rend();++label)content+=*label+":\n";
            }else if(!emittedLabels.count(entry.first))throw std::runtime_error("State label on elided control-flow instruction");
        }
        return "{\n"+locals+content+"}\n";
    }
    std::string body(const Function& f,Symbol owner,const std::string& locals,Symbol ret){
        if(std::any_of(f.nodes.begin(),f.nodes.end(),[](const Node& n){return n.kind=="iterator";}))return structuredBody(f,owner,locals,ret);
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
                        out+="            "+(ca.target==65535?std::string("default"):"case "+caseExpression(ca.children.at(0),n.children[0],owner))+": "+route(roots[j+1].pc)+" break;\n";
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
        struct FunctionScope { int& value; int previous; ~FunctionScope(){value=previous;} } restore{currentFunction,currentFunction};
        FunctionScope restoreEvent{currentEventParameter,currentEventParameter};
        currentFunction=id;
        currentEventParameter=0;
        auto scope=p.ref(id);std::string header;Function f;bool decoded=false;
        try{f=p.function(id);decoded=true;std::vector<std::string> params;std::string locals;Symbol ret;
            for(auto prop:fields({&p,id})){auto flags=p.property(prop.id).flags;if(flags&0x400)ret=prop;else if(flags&0x80)params.push_back(declaration(prop,true));else locals+="    local "+type(prop)+" "+p.entry(prop.id).name+(p.property(prop.id).dim>1?"["+std::to_string(p.property(prop.id).dim)+"]":"")+";\n";}
            bool eventHandler=(f.flags&0x800)!=0;
            if(!eventHandler&&lower(f.friendly)=="onevent"){
                Symbol owner{&p,p.entry(id).outer};
                if(owner.p->kind(owner.id)=="State")owner={owner.p,owner.p->entry(owner.id).outer};
                std::set<std::pair<const Package*,int>> seen;
                for(;owner;owner=ctx.resolve(*owner.p,owner.p->entry(owner.id).super)){
                    if(!seen.insert({owner.p,owner.id}).second)throw std::runtime_error("Cyclic event inheritance");
                    auto base=findCall("OnEvent",owner);
                    if(base&&(base.p->function(base.id).flags&0x800)){eventHandler=true;break;}
                }
            }
            if(eventHandler&&lower(f.friendly)=="onevent"&&!ret&&params.size()==2){
                std::vector<Symbol> parameters;
                for(auto prop:fields({&p,id}))if(p.property(prop.id).flags&0x80)parameters.push_back(prop);
                auto first=p.property(parameters[0].id),second=p.property(parameters[1].id);
                if(first.kind=="IntProperty"&&first.dim==1&&second.kind=="StrProperty"&&second.dim==1)
                    currentEventParameter=parameters[0].id;
            }
            if(f.flags&0x400)header+="native"+(f.native?"("+std::to_string(f.native)+")":"")+" ";
            for(auto flag:{std::pair<uint32_t,const char*>{1,"final"},{2,"defined"},{4,"iterator"},{0x100,"simulated"},{0x200,"exec"},{0x2000,"static"},{0x20,"singular"}})if(flag.first!=2&&(f.flags&flag.first))header+=std::string(flag.second)+" ";
            if(f.flags&0x1000)header+=(f.flags&0x10)?"preoperator ":f.precedence?"operator("+std::to_string(f.precedence)+") ":"postoperator ";
            else header+=(f.flags&0x100000)?"delegate ":(f.flags&0x800)?"event ":"function ";
            if(ret)header+=type(ret)+" ";header+=f.friendly+"("+join(params)+")";
            bool inheritedReplication=false;
            if((f.flags&0x40)&&f.replicationOffset==65535&&f.fields[0]){
                auto base=ctx.resolve(p,f.fields[0]);
                if(base&&base.p->kind(base.id)=="Function"){
                    auto parent=base.p->function(base.id);
                    inheritedReplication=(parent.flags&0xc0)==(f.flags&0xc0)&&lower(parent.friendly)==lower(f.friendly);
                }
            }
            if((f.flags&0x40)&&!replicatedMembers.count(id)&&!inheritedReplication)issue(scope,"Network replication declaration is not reconstructed");
            Json report={{"name",scope},{"native",f.native},{"flags",f.flags},{"replication_offset",f.replicationOffset},{"script_size",f.size},{"decoded",true}};
            if((f.flags&0x400)||!(f.flags&2)){functions.push_back(report);return header+";\n";}
            try{auto generated=body(f,{&p,p.entry(id).outer},locals,ret);report["generated"]=true;functions.push_back(report);return header+"\n"+generated;}
            catch(const std::exception& ex){issue(scope,ex.what());report["generated"]=false;report["stage"]="generate";Json ast=Json::array();for(auto& n:f.nodes)ast.push_back(nodeJson(n));report["bytecode"]=ast;functions.push_back(report);return header+"\n{\n    // INCOMPLETE: "+std::string(ex.what())+"\n    // Decoded bytecode is preserved in export-report.json.\n}\n";}
        }catch(const std::exception& ex){issue(scope,ex.what());auto r=p.reader(id);
            Json report={{"name",scope},{"decoded",decoded},{"generated",false},{"stage",decoded?"declaration":"decode"},{"raw_hex",hex(Bytes(p.data.begin()+r.pos,p.data.begin()+r.end))}};
            if(decoded){Json ast=Json::array();for(auto& n:f.nodes)ast.push_back(nodeJson(n));report["bytecode"]=ast;}
            functions.push_back(report);return "// INCOMPLETE function "+scope+": "+ex.what()+"\n";}
    }
    std::string stateBody(int id,const StructInfo& state){
        if(state.nodes.empty())return "";
        size_t end=state.nodes.size();std::map<int,std::vector<std::string>> labels;
        if(state.nodes.back().kind=="label_table"){
            const auto& table=state.nodes.back();if(state.labelOffset!=table.pc+1)throw std::runtime_error("State label table offset mismatch");
            for(const auto& row:table.value){auto name=row.at(0).get<std::string>();int pc=row.at(1).get<int>();
                if(name=="None"){if(pc!=65535)throw std::runtime_error("Invalid state label terminator");continue;}
                if(!std::regex_match(name,std::regex("[A-Za-z_][A-Za-z_0-9]*")))throw std::runtime_error("Unsupported state label name");
                labels[pc].push_back(name);
            }
            --end;while(end&&state.nodes[end-1].kind=="nothing")--end;
        }else if(state.labelOffset!=65535)throw std::runtime_error("Missing state label table");
        if(!end||state.nodes[end-1].kind!="stop")throw std::runtime_error("Missing implicit state Stop");
        // Preserve explicit Stops, but let the compiler supply the final one.
        int finish=state.nodes[--end].pc;
        std::map<int,size_t> positions;for(size_t i=0;i<end;++i)positions[state.nodes[i].pc]=i;positions[finish]=end;
        for(auto& row:labels)if(!positions.count(row.first))throw std::runtime_error("State label is not a statement boundary");
        // Labels may occur inside a conditional or loop. Splitting at each
        // label would discard valid branch targets in the enclosing region.
        Function part;part.id=id;part.size=finish;
        part.nodes.assign(state.nodes.begin(),state.nodes.begin()+end);
        auto block=structuredBody(part,{&p,id},"",{},true,&labels);
        return block.substr(2,block.size()-4);
    }
    std::vector<int> orderedStructs(int owner){
        std::vector<int> result;std::map<int,int> state;
        std::function<void(int)> visit;
        std::function<void(Symbol,std::set<std::pair<const Package*,int>>&)> propertyDependency;
        auto dependency=[&](Symbol target){
            if(target&&target.p==&p&&p.kind(target.id)=="Struct"&&p.entry(target.id).outer==owner)visit(target.id);
        };
        propertyDependency=[&](Symbol field,std::set<std::pair<const Package*,int>>& seen){
            if(!field||!seen.insert({field.p,field.id}).second)throw std::runtime_error("Recursive struct member type");
            auto prop=field.p->property(field.id);
            if(prop.kind=="StructProperty")dependency(ctx.resolve(*field.p,prop.ref));
            else if(prop.kind=="ArrayProperty")propertyDependency(ctx.resolve(*field.p,prop.ref),seen);
        };
        visit=[&](int id){
            if(state[id]==2)return;
            if(state[id]==1)throw std::runtime_error("Cyclic struct declaration dependency: "+p.ref(id));
            state[id]=1;dependency(ctx.resolve(p,p.entry(id).super));
            for(int field:p.members(id))if(propertyKind(p.kind(field))){
                std::set<std::pair<const Package*,int>> seen;propertyDependency({&p,field},seen);
            }
            state[id]=2;result.push_back(id);
        };
        for(int id:p.members(owner))if(p.kind(id)=="Struct")visit(id);
        return result;
    }
    std::string members(int owner,bool isStruct=false){
        std::string out;
        std::set<int> inlineEnums;
        auto children=p.members(owner),structures=children;
        try{structures=orderedStructs(owner);}catch(const std::exception& ex){issue(p.ref(owner),ex.what());}
        for(auto wanted:{"Const","Enum","Struct","Property","Function","State"})for(int id:std::string(wanted)=="Struct"?structures:children){
            auto kind=p.kind(id);if((std::string(wanted)=="Property")?!propertyKind(kind):kind!=wanted)continue;
            try{
                if(kind=="Const")out+="const "+p.entry(id).name+" = "+p.constant(id)+";\n\n";
                else if(kind=="Enum"){
                    if(isStruct)inlineEnums.insert(id);
                    else out+="enum "+p.entry(id).name+"\n{\n    "+join(p.enumeration(id),",\n    ")+"\n};\n\n";
                }
                else if(kind=="Struct")out+="struct "+p.entry(id).name+(p.entry(id).super?" extends "+qualifiedType(ctx.resolve(p,p.entry(id).super)):"")+"\n{\n"+members(id,true)+"};\n\n";
                else if(propertyKind(kind)){auto prop=p.property(id);if((prop.flags&0x20)&&!replicatedMembers.count(id))issue(p.ref(id),"Replicated property; replication block not reconstructed");
                    if(kind=="DelegateProperty"&&delegateStorage({&p,id}))continue;
                    std::string edit;
                    if(prop.flags&1){
                        // Struct members only accept var(); the SDK supplies
                        // their category from the declaring class.
                        auto category=isStruct||prop.category=="None"?std::string{}:prop.category;
                        if(!category.empty()&&(category.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")!=std::string::npos||
                           (category[0]>='0'&&category[0]<='9')))
                            throw std::runtime_error("Unsupported editable category spelling");
                        edit="("+category+")";
                    }
                    std::string inlineType;
                    if(isStruct&&kind=="ByteProperty"&&inlineEnums.count(prop.ref)){
                        inlineType="enum "+p.entry(prop.ref).name+"\n    {\n        "+join(p.enumeration(prop.ref),",\n        ")+"\n    }";
                    }
                    out+=(isStruct?"    var":"var")+edit+" "+declaration({&p,id},false,inlineType)+";\n";
                    if(!inlineType.empty())inlineEnums.erase(prop.ref);
                }
                else if(kind=="Function")out+=function(id)+"\n";
                else if(kind=="State"){
                    auto state=p.structure(id,false,true);std::string ignores;
                    if(state.ignore!=UINT64_MAX){try{ignores=stateIgnores(id,state.ignore);}catch(const std::exception& ex){issue(p.ref(id),ex.what());}}
                    out+=((state.stateFlags&2)?"auto ":"")+std::string("state ")+p.entry(id).name+(p.entry(id).super?" extends "+leaf(p.ref(p.entry(id).super)):"")+"\n{\n"+ignores+members(id);
                    try{out+=stateBody(id,state);}catch(const std::exception& ex){issue(p.ref(id),"State script: "+std::string(ex.what()));out+="    // INCOMPLETE state script: see report\n";}
                    // Non-probe ignored functions remain no-body declarations
                    // emitted by members(), independently of the probe mask.
                    Json ast=Json::array();for(auto& node:state.nodes)ast.push_back(nodeJson(node));
                    functions.push_back({{"state",p.ref(id)},{"flags",state.stateFlags},{"probe",state.probe},{"ignore",state.ignore},{"label_offset",state.labelOffset},{"bytecode",ast}});out+="}\n\n";
                }
            }catch(const std::exception& ex){issue(p.ref(id),ex.what());out+="// INCOMPLETE "+p.ref(id)+": "+ex.what()+"\n";
                if(propertyKind(kind)){
                    auto serial=p.reader(id);
                    Json saved={{"name",p.ref(id)},{"kind",kind},{"raw_hex",hex(Bytes(p.data.begin()+serial.pos,p.data.begin()+serial.end))}};
                    try{auto prop=p.property(id);saved["flags"]=prop.flags;saved["dimension"]=prop.dim;saved["unread_bytes"]=serial.end-prop.tail;}catch(const std::exception&){}
                    unrecoveredProperties.push_back(saved);
                }
            }
        }
        for(int id:inlineEnums)issue(p.ref(id),"Struct-owned enum has no direct byte property declaration");
        return out;
    }
    std::string replication(int owner,const StructInfo& script){
        struct Group { std::vector<int> members; int reliable=-1; };
        std::map<int,Group> groups;std::map<int,const Node*> conditions;
        for(auto& node:script.nodes)conditions.emplace(node.pc,&node);
        for(int id:p.members(owner)){
            auto kind=p.kind(id);int offset=-1,reliable=-1;
            if(propertyKind(kind)){auto prop=p.property(id);offset=prop.replicationOffset;}
            else if(kind=="Function"){
                auto f=p.function(id);if(f.fields[0])continue;
                offset=f.replicationOffset;reliable=(f.flags&0x80)?1:0;
            }
            if(offset<0)continue;
            auto& group=groups[offset];group.members.push_back(id);
            if(reliable>=0){if(group.reliable>=0&&group.reliable!=reliable)throw std::runtime_error("Conflicting replication reliability at shared condition");group.reliable=reliable;}
        }
        if(groups.empty())return "";
        std::string out="replication\n{\n";std::set<int> recovered;
        for(auto& pair:groups){
            auto found=conditions.find(pair.first);if(found==conditions.end())throw std::runtime_error("Replication offset is not an expression boundary");
            auto condition=expression(*found->second,{&p,owner});std::vector<std::string> names;
            for(int id:pair.second.members){names.push_back(p.entry(id).name);recovered.insert(id);}
            out+="    "+std::string(pair.second.reliable==0?"unreliable":"reliable")+" if ("+condition+")\n        "+join(names)+";\n";
        }
        // Commit recovery only once every referenced condition has been rendered.
        replicatedMembers.insert(recovered.begin(),recovered.end());
        classScriptRecovered=groups.size()==conditions.size();
        return out+"}\n\n";
    }
    Symbol defaultProperty(Symbol owner,const std::string& name) const {
        std::set<std::pair<const Package*,int>> seen;
        while(owner&&seen.insert({owner.p,owner.id}).second){
            for(int id:owner.p->members(owner.id))if(propertyKind(owner.p->kind(id))&&lower(owner.p->entry(id).name)==lower(name))return {owner.p,id};
            owner=ctx.resolve(*owner.p,owner.p->entry(owner.id).super);
        }return {};
    }
    std::string structDefault(Reader& r,const std::string& name,int depth=0,Symbol definition={}){
        if(depth>32)throw std::runtime_error("Default struct nesting limit");
        auto kind=lower(name);std::vector<std::string> parts;
        if(kind=="color"){
            for(auto field:{"B","G","R","A"})parts.push_back(std::string(field)+"="+std::to_string(r.byte()));
        }else if(kind=="vector"||kind=="rotator"){
            for(auto field:kind=="vector"?std::vector<std::string>{"X","Y","Z"}:std::vector<std::string>{"Pitch","Yaw","Roll"}){
                auto value=kind=="vector"?Json(r.f32()):Json(r.i32());
                if(value.is_number_float()&&!std::isfinite(value.get<double>()))throw std::runtime_error("Nonfinite default float");
                parts.push_back(field+"="+value.dump());
            }
        }else{
            for(size_t count=0;;++count){
                if(count>100000)throw std::runtime_error("Default struct tag limit");
                auto field=p.name(r.index());if(field=="None")break;
                auto member=defaultProperty(definition,field);
                int info=r.byte(),type=info&15,sizeCode=(info>>4)&7;std::string nested;
                if(type==10)nested=p.name(r.index());
                int size=0;switch(sizeCode){case 0:size=1;break;case 1:size=2;break;case 2:size=4;break;case 3:size=12;break;case 4:size=16;break;case 5:size=r.byte();break;case 6:size=r.u16();break;case 7:size=r.i32();break;}
                int arrayIndex=-1;
                if((info&128)&&type!=3){
                    int b=r.byte();
                    if(b<128)arrayIndex=b;
                    else if(b<192)arrayIndex=((b&63)<<8)|r.byte();
                    else{arrayIndex=(b&63)<<24;arrayIndex|=int(r.byte())<<16;arrayIndex|=int(r.byte())<<8;arrayIndex|=r.byte();}
                    if(!member||arrayIndex>=member.p->property(member.id).dim)
                        throw std::runtime_error("Invalid indexed nested struct default "+field);
                }
                std::string value;
                if(type==3)value=(info&128)?"True":"False";
                else{
                    if(size<0)throw std::runtime_error("Negative nested default size");r.require(size_t(size));Reader v(p.data,r.pos,size_t(size));r.skip(size_t(size));
                    if(type==10){auto nestedType=member?ctx.resolve(*member.p,member.p->property(member.id).ref):Symbol{};value=structDefault(v,nested,depth+1,nestedType);}
                    else if(type==1){
                        int byte=v.byte();value=std::to_string(byte);
                        if(!member)throw std::runtime_error("Unresolved nested byte/enum default "+field);
                        auto prop=member.p->property(member.id);
                        if(prop.ref){auto en=ctx.resolve(*member.p,prop.ref);if(!en)throw std::runtime_error("Unresolved default enum");auto names=en.p->enumeration(en.id);if(size_t(byte)>=names.size())throw std::runtime_error("Invalid default enum value");value=names[byte];}
                    }
                    else if(type==2)value=std::to_string(v.i32());
                    else if(type==4){auto f=v.f32();if(!std::isfinite(f))throw std::runtime_error("Nonfinite default float");value=Json(f).dump();}
                    else if(type==6)value="'"+p.name(v.index())+"'";
                    else if(type==13)value=quote(v.string());
                    else if(type==5){int object=v.index();value=object?p.kind(object)+"'"+p.ref(object)+"'":"None";}
                    else throw std::runtime_error("Unsupported nested default type "+std::to_string(type));
                    if(v.pos!=v.end)throw std::runtime_error("Nested default payload size mismatch");
                }
                parts.push_back(field+(arrayIndex>=0?"["+std::to_string(arrayIndex)+"]":"")+"="+value);
            }
        }
        // The supported SDK's struct ImportText does not trim after commas.
        return "("+join(parts,",")+")";
    }
    std::string arrayDefaultElement(Reader& r,Symbol inner){
        if(!inner)throw std::runtime_error("Unresolved array default element");
        auto prop=inner.p->property(inner.id);
        if(prop.kind=="StrProperty")return quote(r.string());
        if(prop.kind=="NameProperty")return "'"+p.name(r.index())+"'";
        if(prop.kind=="ObjectProperty"||prop.kind=="ClassProperty"){
            int object=r.index();return object?p.kind(object)+"'"+p.ref(object)+"'":"None";
        }
        if(prop.kind=="IntProperty")return std::to_string(r.i32());
        if(prop.kind=="FloatProperty"){auto value=r.f32();if(!std::isfinite(value))throw std::runtime_error("Nonfinite array default");return Json(value).dump();}
        if(prop.kind=="StructProperty")return structDefault(r,leaf(inner.p->ref(prop.ref)),0,ctx.resolve(*inner.p,prop.ref));
        throw std::runtime_error("Unsupported array default element "+prop.kind);
    }
    std::string defaults(int id,const StructInfo& s){
        auto r=p.reader(id);r.pos=s.tail;r.skip(16);int count=r.index();if(count<0||count>1000000)throw std::runtime_error("Invalid class dependency count");for(int i=0;i<count;++i){p.ref(r.index());r.skip(8);}
        count=r.index();if(count<0||count>100000)throw std::runtime_error("Invalid class package imports");while(count--)p.name(r.index());
        int withinId=r.index();auto within=p.ref(withinId);auto config=p.name(r.index());
        if(withinId){
            auto target=ctx.resolve(p,withinId);
            if(!target||target.p->kind(target.id)!="Class")issue(p.ref(id),"Within is not a resolved class: "+within);
            else {
                const auto& entry=target.p->entry(target.id);
                bool rootObject=lower(target.p->path.stem().u8string())=="core"&&entry.outer==0&&lower(entry.name)=="object";
                if(!rootObject){
                    if(target.p==&p&&target.id==id)issue(p.ref(id),"Within cannot be the class itself: "+within);
                    else withinDeclaration=" within "+within;
                }
            }
        }
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
                else if(kind==10){auto property=defaultProperty({&p,id},name);auto definition=property?ctx.resolve(*property.p,property.p->property(property.id).ref):Symbol{};value=structDefault(v,structName,0,definition);
                }else if(kind==9){
                    auto property=defaultProperty({&p,id},name);
                    if(!property||property.p->kind(property.id)!="ArrayProperty")throw std::runtime_error("Unresolved array default property "+name);
                    auto inner=ctx.resolve(*property.p,property.p->property(property.id).ref);
                    int elements=v.index();if(elements<=0||elements>100000)throw std::runtime_error("Unsupported empty/oversized array default "+name);
                    std::string lines;for(int i=0;i<elements;++i)lines+="    "+name+"("+std::to_string(i)+")="+arrayDefaultElement(v,inner)+"\n";
                    if(v.pos!=v.end)throw std::runtime_error("Array default payload size mismatch for "+name);
                    out+=lines;continue;
                }else{issue(p.ref(id)+".default."+name,"Unsupported tagged default type "+std::to_string(kind)+"; raw bytes retained");
                    auto raw=hex(Bytes(p.data.begin()+v.pos,p.data.begin()+v.end));
                    unrecoveredDefaults.push_back({{"name",p.ref(id)+".default."+name},{"tag_type",kind},
                        {"struct_name",structName},{"array_index",arrayIndex},{"raw_hex",raw}});
                    out+="    // INCOMPLETE "+name+" raw="+raw+"\n";continue;}
                if(v.pos!=v.end)throw std::runtime_error("Default payload size mismatch for "+name);
            }
            out+="    "+name+(arrayIndex>=0?"("+std::to_string(arrayIndex)+")":"")+"="+value+"\n";
        }
        if(r.pos!=r.end)throw std::runtime_error("Trailing class/default bytes");return out+"}\n";
    }
};
Json Context::decompile(int classId,bool force) const {
    auto& p=*main;if(classId<1||size_t(classId)>p.exports.size()||p.kind(classId)!="Class")throw std::runtime_error("Select an exported class: package="+p.path.u8string()+", export_id="+std::to_string(classId));
    Writer w{*this,p};w.rootClass=classId;Json result={{"class",p.ref(classId)},{"id",classId},{"method","bytecode"},{"status","recovered"}};
    if(!force){try{auto source=p.scriptText(classId);if(!source.is_null()){
        // Validate the declaration after removing comments, not just a substring.
        auto text=source["text"].get<std::string>();std::string clean=std::regex_replace(text,std::regex(R"(/\*[\s\S]*?\*/|//[^\r\n]*)")," ");
        std::smatch match;if(!std::regex_search(clean,match,std::regex(R"(\bclass\s+([A-Za-z_][A-Za-z_0-9]*))",std::regex::icase))||lower(match[1])!=lower(p.entry(classId).name))throw std::runtime_error("ScriptText class declaration mismatch");
        result["method"]="ScriptText";result["status"]="source";result["code"]=text;result["raw_hex"]=source["raw_hex"];result["encoding"]=source["encoding"];result["issues"]=w.issues;return result;
    }}catch(const std::exception& ex){w.issue(p.ref(classId)+".ScriptText",ex.what());}}
    auto s=p.structure(classId,true);std::string header="class "+p.entry(classId).name+(p.entry(classId).super?" extends "+p.ref(p.entry(classId).super):"");
    if(s.classFlags&1)header+=" abstract";if(s.classFlags&0x80)header+=" transient";
    if(p.entry(classId).flags&0x04000000)header+=" native";
    if(s.classFlags&0x100)header+=" noexport";
    if(s.classFlags&0x200000)header+=" instanced";
    if(s.classFlags&0x400000)header+=" dynamicrecompile";
    for(int id:p.members(classId))while(lower(p.entry(id).name)==lower(w.helper))w.helper+="_";
    std::string replication;
    try{replication=w.replication(classId,s);}catch(const std::exception& ex){w.issue(p.ref(classId)+".replication",ex.what());}
    std::string code=w.members(classId)+replication;
    if(w.contextHelper)code+="// Preserve null-context semantics for an inlined integer constant.\nstatic function int "+w.helper+"(Object Owner, int Value)\n{\n    if (Owner == None) return 0;\n    return Value;\n}\n\n";
    for(auto& entry:w.typedContextHelpers)code+="// Preserve the value type and zero result of a null context.\nstatic function "+entry.first+" "+entry.second.first+"(Object Owner, "+entry.first+" Value)\n{\n    if (Owner == None) return "+entry.second.second+";\n    return Value;\n}\n\n";
    try{code+=w.defaults(classId,s);}catch(const std::exception& ex){w.issue(p.ref(classId)+".defaults",ex.what());auto r=p.reader(classId);result["class_tail_hex"]=hex(Bytes(p.data.begin()+s.tail,p.data.begin()+r.end));code+="// INCOMPLETE defaultproperties: "+std::string(ex.what())+"\n";}
    if(!s.nodes.empty()&&!w.classScriptRecovered)w.issue(p.ref(classId),"Class-level bytecode/replication is not reconstructed");
    for(auto& dependency:w.typeDependencies)header+=" dependson("+dependency+")";
    code=header+w.withinDeclaration+w.configDeclaration+";\n\n"+code;
    result["class_flags"]=s.classFlags;result["functions"]=w.functions;result["issues"]=w.issues;result["status"]=w.issues.empty()?"recovered":"partial";
    if(!s.nodes.empty()){Json script=Json::array();for(auto& node:s.nodes)script.push_back(nodeJson(node));result["class_script"]=script;}
    if(!w.unrecoveredProperties.empty())result["unrecovered_properties"]=w.unrecoveredProperties;
    if(!w.unrecoveredDefaults.empty())result["unrecovered_defaults"]=w.unrecoveredDefaults;
    result["code"]="// uExplorer: "+p.ref(classId)+"; "+result["status"].get<std::string>()+" from bytecode.\n// Recovered source is not a proof of compilation/semantic equivalence.\n\n"+code;
    result["encoding"]="utf-8";return result;
}
}
