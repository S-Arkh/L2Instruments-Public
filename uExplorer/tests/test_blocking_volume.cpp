#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool value,const char* text){if(!value)throw std::runtime_error(text);}
static void u32(ue::Bytes& out,uint32_t value){for(int i=0;i<4;++i)out.push_back(uint8_t(value>>(8*i)));}
static void set32(ue::Bytes& out,size_t pos,uint32_t value){for(int i=0;i<4;++i)out.at(pos+i)=uint8_t(value>>(8*i));}

int main(int argc,char** argv){
    try{
        check(argc==2,"Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;
        header[4]=133;header[6]=40;
        {std::ofstream file(argv[1],std::ios::binary);file.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);
        p.names={"None","Brush","Location","Vector","MainScale","Scale","SheerRate",
                 "SheerAxis","bBlockPlayers","Mystery","AlienStruct","Touching","bWorldGeometry",
                 "DrawScale","LocationName","bLightChanged","bPendingDelete","bSelected",
                 "bHiddenEd","bAcceptsProjectors","bLockLocationGroup","bHiddenEdGroup",
                 "bForceSunLight","RangeForIgnoredRange","bIgnoredRange","SwayRotationOrig",
                 "bAutoAlignToTerrain","Rotator","Region","PointRegion","Zone","iLeaf","ZoneNumber"};
        auto imported=[&](const char* name,const char* type,int outer){
            ue::Entry e;e.name=name;e.importClass=type;e.outer=outer;p.imports.push_back(e);
        };
        imported("Engine","Package",0);imported("BlockingVolume","Class",-1);imported("Model","Class",-1);
        ue::Entry actor;actor.name="BlockingVolume1";actor.cls=-2;actor.flags=0x02000000;actor.offset=36;
        ue::Entry model;model.name="Model1";model.cls=-3;
        p.exports={actor,model};
        ue::Bytes body={0x82,0x82};
        body.insert(body.end(),8,0xff);u32(body,0xa5b6c7d8u);body.push_back(0x81);
        body.insert(body.end(),{1,5,2,2,0x3a,3});auto vectorOffset=body.size();
        u32(body,0x3f800000u);u32(body,0x80000000u);u32(body,0x40400000u);
        ue::Bytes nested={5,0x3a,3};u32(nested,0x3f800000u);u32(nested,0x3f800000u);
        u32(nested,0x3f800000u);nested.insert(nested.end(),{6,0x24});u32(nested,0);
        nested.insert(nested.end(),{7,1,5,0});
        body.insert(body.end(),{4,0x5a,5,uint8_t(nested.size())});
        auto nestedOffset=body.size();body.insert(body.end(),nested.begin(),nested.end());
        body.insert(body.end(),{8,0x83,12,3,11,0x59,2,1,1,0});
        auto install=[&](const ue::Bytes& data){
            p.data.assign(header.begin(),header.end());p.data.insert(p.data.end(),data.begin(),data.end());
            p.exports[0].size=data.size();
        };
        install(body);
        auto decoded=p.blockingVolume(1);
        check(decoded["status"]=="saved_properties_decoded"&&decoded["brush"]["id"]==2,
              "BlockingVolume properties or brush reference lost");
        check(decoded["frame"]["unknown_word"]==0xa5b6c7d8u&&decoded["frame"]["code_offset"]==-1,
              "Saved frame raw word or offset lost");
        check(decoded["properties"][1]["bits"]==ue::Json::array({0x3f800000u,0x80000000u,0x40400000u})&&
              decoded["properties"][2]["fields"].size()==3&&decoded["properties"][3]["value"]==true&&
              decoded["properties"][4]["value"]==false&&decoded["properties"][5]["value"][0]["id"]==1,
              "Nested, boolean, float-bit or Touching fields lost");
        check(decoded["inherited_defaults_resolved"]==false&&decoded["world_transform_applied"]==false&&
              decoded["runtime_collision_verified"]==false&&decoded["reconstruction_supported"]==false,
              "BlockingVolume scope incorrectly claimed");
        auto fails=[&](){try{p.blockingVolume(1);}catch(const std::exception&){return true;}return false;};
        for(size_t length=0;length<body.size();++length){
            p.exports[0].size=length;check(fails(),"Truncated BlockingVolume accepted");
        }
        p.exports[0].size=body.size();
        for(size_t position:{size_t(0),size_t(1),size_t(2),size_t(14)}){
            auto original=p.data[36+position];p.data[36+position]=0;
            check(fails(),"Invalid saved state frame accepted");p.data[36+position]=original;
        }
        p.exports[0].flags=0;check(fails(),"Missing saved state frame accepted");
        p.exports[0].flags=0x02000000;p.version=132;check(fails(),"Wrong profile accepted");p.version=133;
        p.licensee=39;check(fails(),"Wrong licensee accepted");p.licensee=40;
        p.exports[0].super=-2;check(fails(),"Unexpected actor super accepted");p.exports[0].super=0;
        p.data[36+17]=1;check(fails(),"Brush referring to non-Model accepted");p.data[36+17]=2;
        p.data[36+17]=0x83;check(fails(),"Imported Model brush accepted");p.data[36+17]=2;
        p.data[36+17]=3;check(fails(),"Out-of-range Brush accepted");p.data[36+17]=2;
        p.data[36+body.size()-2]=3;check(fails(),"Invalid Touching reference accepted");
        p.data[36+body.size()-2]=1;
        p.data[36+body.size()-3]=2;check(fails(),"Truncated Touching array accepted");
        p.data[36+body.size()-3]=1;
        p.data[36+19]=6;check(fails(),"Incorrect Location tag type accepted");p.data[36+19]=0x3a;
        p.data[36+nestedOffset+1]=0x2a;check(fails(),"Wrong nested vector width accepted");
        p.data[36+nestedOffset+1]=0x3a;
        p.data.push_back(0);++p.exports[0].size;check(fails(),"Trailing actor bytes accepted");
        p.data.pop_back();--p.exports[0].size;
        set32(p.data,36+vectorOffset,0x7f800001u);
        decoded=p.blockingVolume(1);
        check(decoded["properties"][1]["nonfinite"]==true&&!decoded["properties"][1].contains("value")&&
              decoded["properties"][1]["bits"][0]==0x7f800001u,"Nonfinite vector bits lost");
        install(body);
        auto extra=body;extra.pop_back();extra.insert(extra.end(),{9,0x1a,10,0xde,0xad,0});
        install(extra);decoded=p.blockingVolume(1);
        check(decoded["status"]=="partial"&&decoded["uninterpreted_properties"].size()==1&&
              decoded.dump().find("dead")==std::string::npos,"Unknown property was copied or reported decoded");
        auto indexed=body;indexed.pop_back();
        indexed.insert(indexed.end(),{9,0x81,0x7f,0x10,
                                      9,0x81,0x81,0x45,0x20,
                                      9,0x81,0xc1,0x23,0x45,0x67,0x30,
                                      9,0x83,0});
        install(indexed);decoded=p.blockingVolume(1);
        check(decoded["status"]=="partial"&&decoded["uninterpreted_properties"].size()==4,
              "Unknown indexed and boolean properties not reported");
        check(decoded["properties"][6]["subscript"]==127&&
              decoded["properties"][7]["subscript"]==325&&
              decoded["properties"][8]["subscript"]==0x01234567&&
              !decoded["properties"][9].contains("value"),
              "Indexed property order or unknown boolean value mishandled");
        auto nestedUnknown=body;
        nestedUnknown.insert(nestedUnknown.begin()+nestedOffset+nested.size()-1,{9,1,0x42});
        nestedUnknown[nestedOffset-1]+=3;
        install(nestedUnknown);decoded=p.blockingVolume(1);
        check(decoded["status"]=="partial"&&decoded["uninterpreted_properties"].size()==1&&
              decoded["uninterpreted_properties"][0]["path"]=="BlockingVolume1.MainScale.Mystery"&&
              decoded["properties"][2]["fields"][3]["status"]=="uninterpreted",
              "Unknown nested field not reported");
        auto known=body;known.pop_back();auto knownOffset=known.size();
        known.insert(known.end(),{14,0x5d,5,0x82,0xe9,0,0,0,
                                  15,0x83,16,0x83,17,3,18,3,19,0x83,
                                  20,0x83,21,3,22,0x83,23,0x24});
        u32(known,0x80000000u);
        known.insert(known.end(),{24,0x83,25,0x3a,27});
        u32(known,0x80000000u);u32(known,0);u32(known,0x7fffffffu);
        known.insert(known.end(),{26,0x83,0});
        install(known);decoded=p.blockingVolume(1);
        check(decoded["status"]=="saved_properties_decoded"&&decoded["uninterpreted_properties"].empty()&&
              decoded["properties"][6]["value"]==u8"\u00e9"&&
              decoded["properties"][7]["value"]==true&&decoded["properties"][8]["value"]==true&&
              decoded["properties"][9]["value"]==false&&decoded["properties"][10]["value"]==false&&
              decoded["properties"][11]["value"]==true&&decoded["properties"][12]["value"]==true&&
              decoded["properties"][13]["value"]==false&&decoded["properties"][14]["value"]==true&&
              decoded["properties"][15]["bits"]==0x80000000u&&decoded["properties"][16]["value"]==true&&
              decoded["properties"][17]["value"]==ue::Json::array({INT32_MIN,0,INT32_MAX})&&
              decoded["properties"][18]["value"]==true,
              "Qualified saved string or boolean fields lost");
        auto invalidString=known;invalidString[knownOffset+6]=1;
        install(invalidString);check(fails(),"Unterminated LocationName accepted");
        auto wrongFlagType=known;wrongFlagType[knownOffset+9]=1;
        install(wrongFlagType);check(fails(),"Wrong saved boolean type accepted");
        ue::Bytes region={30,5,0x81,31,0x22};u32(region,0);region.insert(region.end(),{32,1,1});
        auto regionGood=body;regionGood.pop_back();auto regionTag=regionGood.size();
        regionGood.insert(regionGood.end(),{28,0x5a,29,uint8_t(region.size()+1)});
        regionGood.insert(regionGood.end(),region.begin(),region.end());
        regionGood.insert(regionGood.end(),{0,0});
        install(regionGood);decoded=p.blockingVolume(1);
        check(decoded["status"]=="saved_properties_decoded"&&
              decoded["properties"][6]["fields"].size()==3,"Valid Region not decoded");
        auto regionShort=regionGood;regionShort[regionTag+3]=uint8_t(region.size());
        install(regionShort);check(fails(),"Region terminator outside declared payload accepted");
        auto knownIndexed=body;knownIndexed.pop_back();
        knownIndexed.insert(knownIndexed.end(),{13,0xa4,1,0,0,0x80,0x3f,0});
        install(knownIndexed);check(fails(),"Indexed scalar property accepted");
        auto duplicate=body;duplicate.pop_back();duplicate.insert(duplicate.end(),{1,5,2,0});
        install(duplicate);check(fails(),"Duplicate Brush property accepted");
        std::filesystem::remove(argv[1]);
        std::cout<<"BlockingVolume saved-frame and property checks passed\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
