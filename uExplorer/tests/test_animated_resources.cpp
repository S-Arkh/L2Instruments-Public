#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {
void check(bool ok){if(!ok)throw std::runtime_error("Animated resource check failed");}
template<class F> void rejects(F f){try{f();}catch(const std::exception&){return;}throw std::runtime_error("Malformed resource accepted");}
void word(ue::Bytes& b,uint32_t v){for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i)));}
void zeros(ue::Bytes& b,size_t n){b.insert(b.end(),n,0);}
void set(ue::Bytes& b,size_t at,uint32_t v){for(int i=0;i<4;++i)b.at(at+i)=uint8_t(v>>(8*i));}
void prefix(ue::Bytes& b,int version){
    zeros(b,41);word(b,version);word(b,1);
    b.push_back(1);word(b,0x80000000);word(b,0x7fc01234);word(b,0);
    b.push_back(1);b.push_back(1); // Texture self-reference.
    zeros(b,32);word(b,0x12345678); // Original rotation word.
    zeros(b,5); // Face levels, faces, collapsed wedges, wedges and materials.
    zeros(b,24);word(b,0);b.push_back(1); // LOD fields, impostor flag/material.
    zeros(b,36+4+12+8);
    for(int i=5;i<version;++i)b.push_back(uint8_t(17+i));
}
void sequences(ue::Bytes& b){
    b.push_back(1);word(b,0x80000000);b.push_back(1);b.push_back(1);b.push_back(1);
    word(b,0);word(b,2);b.push_back(1);
    word(b,0x3f000000);b.push_back(1);b.push_back(1);word(b,3);
    b.insert(b.end(),{65,0,0,0,0,0xd8}); // Preserve embedded zero and unpaired UTF-16 unit.
    word(b,0x7fc01234);zeros(b,12);b.push_back(1);zeros(b,8);b.push_back(3);
    b.push_back(0);b.push_back(0);zeros(b,8);b.push_back(0);
}
}
int main(int argc,char** argv){
    try{
        check(argc==2);ue::Bytes header(36,0);set(header,0,0x9e2a83c1);header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);p.names={"None","Run","Materials","PlayAnimationName","PlayRandomPercent","WAV","Attach","SoundName"};
        ue::Entry cls;cls.name="SkeletalMesh";cls.importClass="Class";p.imports.push_back(cls);
        ue::Entry mesh;mesh.name="Example";mesh.cls=-1;p.exports.push_back(mesh);
        auto install=[&](const ue::Bytes& b,size_t offset=64){
            p.paths.clear();p.paths[0]="None";
            p.data.assign(offset,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].offset=offset;p.exports[0].size=b.size();
        };
        for(int version:{5,6,7}){
            ue::Bytes b={0};prefix(b,version);b.push_back(0); // points2
            b.push_back(1);b.push_back(1);word(b,7);word(b,0x7fc05678);zeros(b,40);word(b,0);word(b,0);
            b.push_back(1);word(b,1);zeros(b,6); // weight, influence, attachment and LOD arrays
            b.push_back(1); // auxiliary object
            std::vector<size_t> lazy;
            for(int i=0;i<6;++i){lazy.push_back(b.size());word(b,uint32_t(64+b.size()+5));b.push_back(0);}
            word(b,9);b.push_back(1);word(b,0x80000000);zeros(b,8);install(b);
            auto result=p.animatedResource(1,"skeletal_mesh");auto body=result["body"];
            check(body["version"]==version&&body["extension_bytes"].size()==size_t(version-5));
            check(body["bones"][0]["pose_bits"][0]==0x7fc05678u&&body["animation"]["path"]=="Example");
            check(body["transforms"][8]==0x12345678&&body["vertices_bits"][0][1]==0x7fc01234u);
            for(auto at:lazy){auto bad=b;bad[at]^=1;install(bad);rejects([&]{p.animatedResource(1,"skeletal_mesh");});}
            auto relocated=b;for(auto at:lazy)set(relocated,at,uint32_t(1024+at+5));install(relocated,1024);
            check(p.animatedResource(1,"skeletal_mesh")["body"]==body);
            auto packed=b;packed.erase(packed.begin()+55,packed.begin()+63);
            for(auto at:lazy)set(packed,at-8,uint32_t(64+at-8+5));
            for(auto profile:{std::pair<int,int>{131,40},{132,40},{123,36}}){
                p.version=profile.first;p.licensee=profile.second;install(packed);
                check(p.animatedResource(1,"skeletal_mesh")["body"]["packed_original_vertices"][0]==0x80000000u);
            }
            p.version=133;p.licensee=40;
            auto bad=b;bad.push_back(0);install(bad);rejects([&]{p.animatedResource(1,"skeletal_mesh");});
        }
        p.imports[0].name="VertMesh";
        ue::Bytes b={2,0x59,2,1,1,0}; // Materials object-reference array.
        prefix(b,7);b.push_back(0);word(b,2);b.push_back(1);word(b,0xffffffff);b.push_back(0);
        sequences(b);b.push_back(1);word(b,0xaabbccdd);word(b,1);word(b,2);b.push_back(0);b.push_back(0);install(b);
        auto result=p.animatedResource(1,"vert_mesh");
        check(result["tags"][0]["value"][0]["path"]=="Example");
        check(result["body"]["packed_vertices"][0]==0xffffffffu&&result["body"]["packed_normals"][0]==0xaabbccddu);
        check(result["body"]["sequences"][0]["events"][0]["text_utf16"]==ue::Json::array({65,0,0xd800}));
        b.pop_back();install(b);rejects([&]{p.animatedResource(1,"vert_mesh");});
        p.imports[0].name="MeshAnimation";b={0};word(b,1);b.push_back(0);
        auto end=b.size();word(b,0);b.push_back(1);auto local=b.size();word(b,0);
        zeros(b,24);b.push_back(0);b.push_back(0);word(b,0);zeros(b,3);
        set(b,end,uint32_t(64+b.size()));set(b,local,uint32_t(64+b.size()));sequences(b);install(b);
        check(p.animatedResource(1,"mesh_animation")["body"]["moves"].size()==1);
        b[local]^=1;install(b);rejects([&]{p.animatedResource(1,"mesh_animation");});
        p.imports[0].name="AnimNotify_PlayCustomAnimation";b={3,6,1,4,0x22};word(b,35);b.insert(b.end(),{6,0xd3,0,0});install(b);
        result=p.animatedResource(1,"animation_notify");check(result["tags"][0]["value"]=="Run"&&result["tags"][1]["value"]==35);
        check(result["tags"][2]["value"]==true&&result["tags"][2]["declared_size"]==0);
        b.push_back(0);install(b);rejects([&]{p.animatedResource(1,"animation_notify");});
        p.imports[0].name="AnimNotify_PawnStatusVoice";b={7,0x59,7,2,0,0x82,0x5c,0xd5,0,0,0};install(b);
        check(p.animatedResource(1,"animation_notify")["tags"][0]["value"]==ue::Json::array({"","\xed\x95\x9c"}));
        b[2]=6;install(b);rejects([&]{p.animatedResource(1,"animation_notify");});
        p.imports[0].name="Sound";b={0,5};word(b,64+11);b.insert(b.end(),{4,0x52,0x49,0x46,0x46});install(b);
        result=p.animatedResource(1,"sound");check(result["body"]["audio_hex"]=="52494646");
        p.version=131;check(p.animatedResource(1,"sound")["body"]==result["body"]);p.version=133;
        b[2]^=1;install(b);rejects([&]{p.animatedResource(1,"sound");});
        rejects([&]{p.animatedResource(1,"vert_mesh");});rejects([&]{p.animatedResource(-1,"sound");});
        p.version=123;rejects([&]{p.animatedResource(1,"sound");});
        std::cout<<"Animated resource fields, relocation and rejection checks passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
