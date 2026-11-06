// Read-only metadata probe for external fixtures and compiler roundtrip tests.
#include "package.h"
#include <iostream>
int main(int argc,char** argv) {
    try {
        const bool enumsOnly=argc==3&&std::string(argv[2])=="--enums-only";
        const bool enumImports=argc==3&&std::string(argv[2])=="--enum-imports";
        if(argc!=2&&!enumsOnly&&!enumImports)throw std::runtime_error("Expected package path and optional enum mode");
        ue::Package p(std::filesystem::u8path(argv[1]));ue::Json rows=ue::Json::array();
        if(enumImports){
            for(size_t i=0;i<p.imports.size();++i){int id=-int(i)-1;if(p.kind(id)=="Enum")rows.push_back(p.ref(id));}
            std::cout<<rows.dump(2)<<'\n';return 0;
        }
        for(size_t i=0;i<p.exports.size();++i){
            int id=int(i)+1;auto kind=p.kind(id);
            if(enumsOnly){
                if(kind=="Enum")rows.push_back({{"enum",p.ref(id)},{"values",p.enumeration(id)}});
                continue;
            }
            if(kind=="Class"){
                auto s=p.structure(id,true);auto r=p.reader(id);r.pos=s.tail;r.skip(16);
                int count=r.index();for(int j=0;j<count;++j){r.index();r.skip(8);}
                count=r.index();for(int j=0;j<count;++j)r.index();
                int within=r.index();auto config=p.name(r.index());
                rows.push_back({{"class",p.ref(id)},{"flags",s.classFlags},{"object_flags",p.entry(id).flags},{"within",p.ref(within)},
                                {"within_kind",within?p.kind(within):"None"},{"config",config}});
            }else if(kind=="State"){
                auto s=p.structure(id,false,true);
                rows.push_back({{"state",p.ref(id)},{"flags",s.stateFlags},{"probe",s.probe},{"ignore",s.ignore},
                                {"label_offset",s.labelOffset},{"script_size",s.size}});
            }else if(kind.size()>=8&&kind.substr(kind.size()-8)=="Property"){
                auto v=p.property(id);auto r=p.reader(id);
                rows.push_back({{"property",p.ref(id)},{"kind",kind},{"flags",v.flags},{"dimension",v.dim},{"category",v.category},
                                {"replication_offset",v.replicationOffset},
                                {"type_reference",p.ref(v.ref)},{"class_reference",p.ref(v.meta)},
                                {"unread_bytes",r.end-v.tail},{"raw",ue::hex(ue::Bytes(p.data.begin()+r.pos,p.data.begin()+r.end))}});
            }
        }
        std::cout<<rows.dump(2)<<'\n';return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
