#include "package.h"
#include <stdexcept>

namespace ue {
Json Package::metadata() const {
    Json owners=Json::object(),properties=Json::object(),references=Json::array();
    Json objects=Json::array(),issues=Json::array(),enums=Json::object(),constants=Json::object();
    auto propertyKind=[](const std::string& k){return k.size()>=8&&k.substr(k.size()-8)=="Property";};
    for(std::size_t i=0;i<exports.size();++i){
        int id=int(i)+1;auto k=kind(id);
        try{
            if(propertyKind(k)){
                auto v=property(id);
                properties[ref(id)]={{"kind",k},{"owner",ref(entry(id).outer)},
                    {"dimension",v.dim},{"flags",v.flags},{"category",v.category},
                    {"reference",ref(v.ref)},{"metaclass",ref(v.meta)},
                    {"replication_offset",v.replicationOffset}};
            }else if(k=="Class"||k=="Struct"||k=="State"||k=="Function"){
                Json record={{"kind",k},{"super",ref(entry(id).super)},{"export_flags",entry(id).flags}};
                Json fields=Json::array();for(int field:orderedFields(id))fields.push_back(ref(field));
                record["fields"]=fields;
                if(k=="Function"){
                    auto f=function(id);record["flags"]=f.flags;record["native"]=f.native;
                    record["precedence"]=f.precedence;record["replication_offset"]=f.replicationOffset;
                }else{
                    auto s=structure(id,k=="Class",k=="State");
                    if(k=="Class")record["flags"]=s.classFlags;
                    if(k=="Class"||k=="State"){
                        record["state_flags"]=s.stateFlags;record["probe"]=s.probe;record["ignore"]=s.ignore;
                    }
                }
                owners[ref(id)]=record;
            }else if(k=="Enum"){
                enums[ref(id)]=enumeration(id);
            }else if(k=="Const"){
                constants[ref(id)]=constant(id);
            }else if(k!="TextBuffer"){
                objects.push_back({{"path",ref(id)},{"class",ref(entry(id).cls)},
                    {"owner",ref(entry(id).outer)},{"export_flags",entry(id).flags},
                    {"payload_bytes",entry(id).size},{"payload_status","opaque"}});
            }
        }catch(const std::exception& error){issues.push_back({{"scope",ref(id)},{"message",error.what()}});}
    }
    const auto self=lower(path.stem().u8string());
    for(std::size_t i=0;i<imports.size();++i){
        int id=-int(i)-1;const auto& item=imports[i];
        auto full=ref(id);auto dot=full.find('.');
        bool own=dot!=std::string::npos&&lower(full.substr(0,dot))==self;
        Json matches=Json::array();
        if(own){
            auto suffix=lower(full.substr(dot+1));
            for(std::size_t j=0;j<exports.size();++j)
                if(lower(ref(int(j)+1))==suffix&&lower(kind(int(j)+1))==lower(item.importClass))matches.push_back(int(j)+1);
        }
        const bool classImport=lower(item.importClass)=="class"&&lower(item.classPackage)=="core"&&lower(ref(item.outer))==self;
        if(matches.size()>1)issues.push_back({{"scope",full},{"message","Ambiguous self-package import"}});
        references.push_back({{"path",full},{"class",item.classPackage+"."+item.importClass},
            {"owner",ref(item.outer)},{"self_package",own},{"local_export_matches",matches},
            {"status",own?(matches.empty()?(classImport?"native_class_candidate":"unresolved_self_import"):(matches.size()==1?"local_export":"ambiguous_self_import")):"external_unchecked"}});
    }
    return {{"schema_version",1},{"status",issues.empty()?"complete":"partial"},
        {"package",path.stem().u8string()},{"version",version},{"licensee",licensee},
        {"owners",owners},{"properties",properties},{"imports",references},
        {"enumerations",enums},{"constants",constants},
        {"objects",objects},{"issues",issues},
        {"limitations",Json::array({"Native inheritance absent from serialized exports is unknown.",
            "External imports are inventoried, not dependency-resolved.",
            "Object payloads and default-object graphs are not reconstructed by this report.",
            "Field order is serialized metadata, not measured native memory offsets."})}};
}
}
