#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
static void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char** argv){
    try{
        check(argc==2,"Expected fixture path");ue::Bytes header(36,0);
        header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream f(argv[1],std::ios::binary);f.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);p.names={"None","Shader","Material","M","Matrix","XPlane","Plane","X","TwoSided"};
        ue::Entry cls;cls.name="Shader";cls.importClass="Class";p.imports.push_back(cls);
        ue::Entry texture;texture.name="TextureSource";texture.importClass="Texture";p.imports.push_back(texture);
        ue::Bytes b={2,5,0x82,3,0x3a,4,5,0x5a,6,7,7,0x24,0x34,0x12,0xc0,0x7f,0,0,8,0x83,0};
        b.insert(b.end(),92,0);b.push_back(0);b.push_back(0);b.insert(b.end(),4,0);
        ue::Entry object;object.name="TestMaterial";object.cls=-1;object.offset=p.data.size();object.size=b.size();
        p.data.insert(p.data.end(),b.begin(),b.end());p.exports.push_back(object);
        auto result=p.material(1);
        check(result["status"]=="decoded"&&result["remaining_bytes"]==0,"Incomplete material decode");
        check(result["tags"][0]["value"]["path"]=="TextureSource","Material reference lost");
        check(result["tags"][1]["members"][0]["members"][0]["bits"]==0x7fc01234u,"Matrix NaN bits lost");
        check(result["tags"][2]["value"]==true,"Material bool lost");
        auto fails=[&](){try{p.material(1);}catch(const std::exception&){return true;}return false;};
        auto good=p.data;
        p.version=129;p.licensee=39;
        auto stage4=result["native_offset"].get<size_t>()+2+4*14;
        p.data[stage4+1]=0x80;p.data[stage4+10]=0x7b;
        auto stages=p.material(1)["stages"];
        check(stages.size()==5&&stages[4]["bytes"]==ue::Json::array({0,128})&&
              stages[4]["words"]==ue::Json::array({0,0,123}),"Version 129 stage layout lost");
        p.data=good;p.version=133;p.licensee=40;
        p.names.insert(p.names.end(),{"SequenceItems","Time","Action"});
        p.imports[0].name="MaterialSequence";p.paths.erase(-1);
        ue::Bytes sequence={9,0x59,14,1,2,5,0x82,10,0x24,0x34,0x12,0xc0,0x7f,11,1,0xff,0,0};
        sequence.insert(sequence.end(),98,0);
        p.data.assign(object.offset,0);p.data.insert(p.data.end(),sequence.begin(),sequence.end());p.exports[0].size=sequence.size();
        auto fields=p.material(1)["tags"][0]["elements"][0];
        check(fields[0]["value"]["path"]=="TextureSource"&&fields[1]["bits"]==0x7fc01234u&&fields[2]["value"]==255,
              "Material sequence fields lost");
        p.data[object.offset+2]=12;check(fails(),"Truncated sequence accepted");
        p.imports[0].name="Shader";p.paths.erase(-1);p.data=good;p.exports[0].size=object.size;
        p.data[object.offset+10]=1;check(fails(),"Unknown matrix component accepted");p.data=good;
        p.data[object.offset+9]=6;check(fails(),"Truncated matrix plane accepted");p.data=good;
        p.data.push_back(0);++p.exports[0].size;check(fails(),"Opaque material suffix accepted");p.data=good;p.exports[0].size=object.size;
        p.version=126;p.licensee=0;check(fails(),"Unsupported material profile accepted");
        p.version=133;p.licensee=40;p.imports[0].name="Texture";p.paths.erase(-1);
        b.assign(99,0);b.push_back(1);auto boundary=b.size();
        auto word=[&](uint32_t v){for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i)));};
        word(uint32_t(64+b.size()+6));b.push_back(1);b.push_back(0xab);word(1);word(1);b.push_back(0);b.push_back(0);
        p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].offset=64;p.exports[0].size=b.size();
        auto mip=p.material(1)["mips"][0];check(mip["data_hex"]=="ab"&&mip["width"]==1,"Texture mip lost");
        p.data[64+boundary]^=1;check(fails(),"Invalid mip boundary accepted");p.data[64+boundary]^=1;
        p.data.pop_back();--p.exports[0].size;check(fails(),"Truncated texture accepted");
        p.names.push_back("RLEData");p.imports[0].name="MaskTexture";p.paths.erase(-1);
        b={12,0x59,9,2,0,0,0,0,0xff,0xff,0xff,0xff,0};b.insert(b.end(),99,0);
        p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].size=b.size();
        check(p.material(1)["tags"][0]["words"]==ue::Json::array({0u,0xffffffffu}),"Mask RLE bits lost");
        p.data[67]=3;check(fails(),"Truncated RLE array accepted");
        p.names.insert(p.names.end(),{"Drops","ADrop","Type","bParametric"});
        p.version=127;p.licensee=39;p.imports[0].name="WetTexture";p.paths.erase(-1);
        b={13,0x5a,14,4,15,1,19,0,16,0x83,0};b.insert(b.end(),42,0);b.push_back(1);
        word(uint32_t(64+b.size()+5));b.push_back(0);word(128);word(128);b.push_back(7);b.push_back(7);
        p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].size=b.size();
        check(p.material(1)["tags"][0]["members"][0]["value"]==19&&p.material(1)["mips"][0]["data_hex"]=="",
              "WetTexture procedural fields lost");
        p.data[64+9]=3;check(fails(),"Nonparametric empty wet mip accepted");
        p.version=133;p.licensee=40;
        p.imports[0].name="Palette";p.paths.erase(-1);
        b={0,0x40,4};
        for(int i=0;i<256;++i)b.insert(b.end(),{uint8_t(i),uint8_t(255-i),0x80,0xff});
        p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].size=b.size();
        auto colors=p.material(1)["colors"];
        check(colors.size()==256&&colors[17]==ue::Json::array({17,238,128,255}),"Palette color bytes lost");
        p.data[65]=0x41;check(fails(),"Wrong palette size accepted");p.data[65]=0x40;
        p.data.pop_back();--p.exports[0].size;check(fails(),"Truncated palette accepted");
        for(int license:{12,19,23}){
            p.version=123;p.licensee=license;p.imports[0].name="Texture";p.paths.erase(-1);
            b={0};if(license>=16)word(0x89abcdef);
            b.push_back(1);word(0);b.push_back(1);b.push_back(0xab);
            word(1);word(1);b.push_back(0);b.push_back(0);
            p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].size=b.size();
            auto early=p.material(1);
            check(early["mips"][0]["data_hex"]=="ab","Early mip data lost");
            check(early.contains("obsolete_material_word")==bool(license>=16),"Early scalar presence lost");
            if(license>=16)check(early["obsolete_material_word"]==0x89abcdefu,"Early scalar bits lost");
            p.data.push_back(0);++p.exports[0].size;check(fails(),"Early opaque suffix accepted");
            p.data.pop_back();--p.exports[0].size;
            p.licensee=20;check(fails(),"Unverified early profile accepted");
        }
        p.names.push_back("EnvMapType");int envName=int(p.names.size())-1;
        for(int license:{33,34,35,36}){
            p.version=123;p.licensee=license;p.imports[0].name="Texture";p.paths.erase(-1);
            b={0};word(0x89abcdef);
            if(license<36)b.push_back(91);
            for(int i=0;i<18;++i)b.push_back(uint8_t(i+17));
            for(int i=0;i<8;++i){
                b.push_back(uint8_t(i+20));
                if(license<36)b.push_back(uint8_t(i+40));
                for(int j=0;j<126;++j)b.push_back(uint8_t(i*31+j));
            }
            b.insert(b.end(),8,0);word(0x80000000);word(0x7fc12345);word(0x3f800000);
            b.insert(b.end(),16,0);b.push_back(0);word(0x12345678);auto materialEnd=b.size();
            b.push_back(1);word(0);b.push_back(1);b.push_back(0xab);
            word(1);word(1);b.push_back(0);b.push_back(0);
            p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());p.exports[0].size=b.size();
            auto old=p.material(1);
            check(old["legacy_material"]["header"][17]==34&&
                  old["legacy_material"]["stages"][7]["fields"][125]==uint8_t(7*31+125)&&
                  old["legacy_material"]["strings"].size()==16&&
                  old["mips"][0]["data_hex"]=="ab"&&old["words"][1]==0x7fc12345u,
                  "Legacy material layout lost");
            check(old["legacy_material"].contains("flag")==bool(license<36),"Legacy flag gate lost");
            p.data.push_back(0);++p.exports[0].size;check(fails(),"Legacy opaque suffix accepted");
            p.data.pop_back();--p.exports[0].size;
            ue::Bytes env={uint8_t(envName),1,2,2,5,0x82,0};
            env.insert(env.end(),b.begin()+1,b.begin()+materialEnd);
            p.imports[0].name="TexEnvMap";p.paths.erase(-1);
            p.data.assign(64,0);p.data.insert(p.data.end(),env.begin(),env.end());p.exports[0].size=env.size();
            if(license==35){
                auto material=p.material(1);
                check(material["tags"][0]["value"]==2&&material["tags"][1]["value"]["path"]=="TextureSource"&&
                      material["legacy_material"]["stages"].size()==8&&
                      material["remaining_bytes"]==0,"Legacy TexEnvMap fields lost");
                p.data.push_back(0);++p.exports[0].size;check(fails(),"Legacy TexEnvMap suffix accepted");
                p.data.pop_back();--p.exports[0].size;
                p.data.pop_back();--p.exports[0].size;check(fails(),"Truncated legacy TexEnvMap accepted");
            }else check(fails(),"Unverified legacy TexEnvMap profile accepted");
            p.imports[0].name="Combiner";p.paths.erase(-1);check(fails(),"Unverified legacy class accepted");
            p.licensee=32;check(fails(),"Unverified obsolete profile accepted");
        }
        std::cout<<"Material structural checks passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
