#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
static void u32(ue::Bytes& b,uint32_t v){for(int i=0;i<4;++i)b.push_back(uint8_t(v>>(8*i)));}
static void set32(ue::Bytes& b,size_t pos,uint32_t v){for(int i=0;i<4;++i)b.at(pos+i)=uint8_t(v>>(8*i));}
int main(int argc,char** argv){
    try{
        check(argc==2,"Expected fixture path");ue::Bytes header(36,0);
        header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);p.names={"None","Materials","Material","EnableCollision"};
        for(auto name:{"StaticMesh","Material"}){ue::Entry e;e.name=name;e.importClass="Class";p.imports.push_back(e);}
        ue::Bytes b={1,0x59,7,1,2,5,0x82,3,0x83,0,0}; // One material, typed import -2, collision true.
        auto box=[&](){b.insert(b.end(),24,0);b.push_back(1);};
        box();b.insert(b.end(),16,0);b.push_back(0);box();
        auto vertexCount=b.size();b.push_back(1);u32(b,0x80000000);b.insert(b.end(),20,0);u32(b,1);
        for(int i=0;i<2;++i){b.push_back(1);u32(b,0xff102030);u32(b,1);}
        b.push_back(1);b.push_back(1);u32(b,0x7fc01234);u32(b,0);u32(b,0);u32(b,1);
        b.push_back(3);auto indexOffset=b.size();b.insert(b.end(),6,0);u32(b,1);
        b.push_back(0);u32(b,1);b.push_back(0); // Wire indices, collision model.
        auto faceLazy=b.size();u32(b,0);b.push_back(1);b.insert(b.end(),64,0);b.insert(b.end(),4,0);
        auto nodeLazy=b.size();u32(b,0);b.push_back(1);b.insert(b.end(),4,0);box();
        auto nodesEnd=b.size();
        u32(b,0);b.push_back(0x82);b.push_back(0);b.insert(b.end(),40,0);
        auto triangleLazy=b.size();u32(b,0);b.push_back(1);b.insert(b.end(),36,0);
        auto channelCount=b.size();u32(b,0);b.insert(b.end(),20,0);
        auto trianglesEnd=b.size();u32(b,8);b.push_back(0);u32(b,0);
        b.push_back(1);u32(b,0x80000000);u32(b,0x3f800000);b.insert(b.end(),16,0);
        auto prefixEnd=b.size();
        ue::Entry mesh;mesh.name="Mesh";mesh.cls=-1;mesh.offset=p.data.size();mesh.size=b.size();
        set32(b,faceLazy,uint32_t(mesh.offset+nodeLazy));set32(b,nodeLazy,uint32_t(mesh.offset+nodesEnd));
        set32(b,triangleLazy,uint32_t(mesh.offset+trianglesEnd));
        p.data.insert(p.data.end(),b.begin(),b.end());p.exports.push_back(mesh);
        auto result=p.staticMesh(1);
        check(result["status"]=="decoded"&&result["remaining_bytes"]==0,"Incomplete body coverage");
        check(result["vertices"][0]["position_bits"][0]==0x80000000u,"Signed zero lost");
        check(result["uv_streams"][0]["coordinate_bits"][0][0]==0x7fc01234u,"NaN payload lost");
        check(result["tags"][0]["value"][0][0]["value"]["id"]==-2,"Material reference lost");
        check(result["license_fields"]["reference_0"]["id"]==-2,"License reference lost");
        check(result["source_triangles"].size()==1,"Source triangles missing");
        auto fails=[&](){try{p.staticMesh(1);}catch(const std::exception&){return true;}return false;};
        auto good=p.data;
        p.data[mesh.offset+faceLazy]^=1;check(fails(),"Bad lazy offset accepted");p.data=good;
        p.data[mesh.offset+indexOffset]=1;check(fails(),"Out of range vertex accepted");p.data=good;
        p.data[mesh.offset+vertexCount]=0x81;check(fails(),"Negative vertex count accepted");p.data=good;
        p.data[mesh.offset+channelCount]=9;check(fails(),"Excessive triangle UV channels accepted");p.data=good;
        p.data[mesh.offset+triangleLazy]^=1;check(fails(),"Bad triangle lazy offset accepted");p.data=good;
        p.exports[0].size=prefixEnd-1;check(fails(),"Truncated node accepted");p.exports[0].size=mesh.size;
        p.data.push_back(0);++p.exports[0].size;check(fails(),"Unknown suffix accepted");p.data=good;p.exports[0].size=mesh.size;
        p.version=126;p.licensee=0;check(fails(),"Unverified profile accepted");
        p.version=123;p.licensee=37;check(fails(),"Modern suffix accepted in legacy profile");
        p.exports[0].size=trianglesEnd+9;p.data.resize(mesh.offset+p.exports[0].size);
        auto legacy=p.staticMesh(1);
        check(legacy["remaining_bytes"]==0&&legacy["auxiliary_words"].empty(),"Legacy StaticMesh boundary failed");
        check(legacy["vertices"]==result["vertices"]&&legacy["source_triangles"]==result["source_triangles"],"Legacy mesh data changed");
        for(auto profile:{std::pair<int,int>{118,0},{123,12},{123,14},{123,15},{123,16},
                          {123,18},{123,36},{123,38},{125,38},{127,39},{132,40}}){
            p.version=profile.first;p.licensee=profile.second;ue::Bytes data;
            auto copy=[&](size_t start,size_t end){data.insert(data.end(),b.begin()+start,b.begin()+end);};
            copy(0,faceLazy);
            auto faces=data.size();if(p.licensee>=17)u32(data,0);
            copy(faceLazy+4,nodeLazy);
            auto nodes=data.size();if(p.licensee>=17)u32(data,0);
            copy(nodeLazy+4,nodesEnd);auto collisionEnd=data.size();
            if(p.licensee){
                copy(nodesEnd,nodesEnd+6);
                int slots=p.licensee<13?5:p.licensee<15?8:p.licensee<37?9:10;
                for(int i=0;i<slots;++i)u32(data,0x80000000u+i);
            }
            auto triangles=data.size();u32(data,0);copy(triangleLazy+4,trianglesEnd);
            auto end=data.size();copy(trianglesEnd,trianglesEnd+5);
            if(p.version>=120)copy(trianglesEnd+5,trianglesEnd+9);
            if(p.version>=125)copy(trianglesEnd+9,b.size());
            // Relocate the fixture as well as its internal lazy boundaries.
            p.exports[0].offset=mesh.offset+113;
            if(p.licensee>=17){
                set32(data,faces,uint32_t(p.exports[0].offset+nodes));
                set32(data,nodes,uint32_t(p.exports[0].offset+collisionEnd));
            }
            set32(data,triangles,uint32_t(p.exports[0].offset+end));
            p.data.assign(p.exports[0].offset,0);p.data.insert(p.data.end(),data.begin(),data.end());
            p.exports[0].size=data.size();auto decoded=p.staticMesh(1);
            check(decoded["vertices"]==result["vertices"]&&decoded["source_triangles"]==result["source_triangles"]&&
                  decoded["remaining_bytes"]==0,"Expanded mesh profile lost fields");
            check(decoded["license_fields"].empty()==(p.licensee==0)&&
                  decoded.contains("trailing_word")== (p.version>=120),"Absent legacy fields exposed");
            p.data[p.exports[0].offset+triangles]^=1;
            check(fails(),"Relocated legacy triangle boundary accepted");
        }
        p.version=123;p.licensee=37;p.imports[0].name="Model";p.paths.erase(-1);
        b={0};box();b.insert(b.end(),16,0);
        b.push_back(1);u32(b,0x7fc01234);u32(b,0);u32(b,0);
        b.push_back(1);u32(b,0x80000000);u32(b,0);u32(b,0);
        b.push_back(1);b.insert(b.end(),25,0);
        auto nodeIndicesOffset=b.size();
        b.insert(b.end(),{0,0,0x81,0x81,0x81,0,0x81}); // node links and hull start
        b.insert(b.end(),32,0);b.insert(b.end(),{0,0,1});auto nodeLeavesOffset=b.size();b.insert(b.end(),20,0);
        b.push_back(1);b.push_back(0x82);u32(b,0);b.insert(b.end(),{0,0,0,0,0x81});
        b.push_back(0);b.insert(b.end(),24,0);
        b.push_back(1);auto pointOffset=b.size();b.insert(b.end(),{0,0x81});
        u32(b,1);auto zoneOffset=b.size();u32(b,0);b.push_back(1);b.push_back(0);
        b.push_back(8);auto planeOffset=b.size();u32(b,0x40000000);u32(b,0xffffffff);
        b.insert(b.end(),24,0);auto leavesOffset=b.size();b.insert(b.end(),{0,0});u32(b,1);u32(b,0);
        auto arraysOffset=b.size();b.insert(b.end(),3,0);
        p.exports[0].offset=64;p.exports[0].size=b.size();
        p.data.assign(64,0);p.data.insert(p.data.end(),b.begin(),b.end());
        auto model=p.geometry(1,"model");
        check(model["remaining_bytes"]==0&&model["surfaces"][0]["material"]["id"]==-2,
              "Model reference or boundary lost");
        check(model["vectors"][0][0]==0x7fc01234u&&model["points"][0][0]==0x80000000u,
              "Model float bits lost");
        auto modelFails=[&](){try{p.geometry(1,"model");}catch(const std::exception&){return true;}return false;};
        for(size_t length=0;length<b.size();++length){
            p.exports[0].size=length;check(modelFails(),"Truncated Model accepted");
        }
        p.exports[0].size=b.size();
        p.data[64+pointOffset]=1;check(modelFails(),"Invalid Model point accepted");p.data[64+pointOffset]=0;
        p.data[64+planeOffset]=1;check(modelFails(),"Invalid Model hull plane accepted");p.data[64+planeOffset]=0;
        p.data.push_back(0);++p.exports[0].size;
        auto extraLegacy=p.geometry(1,"model");
        check(extraLegacy["status"]=="unverified"&&extraLegacy["remaining_bytes"]==1&&
              extraLegacy.contains("warning"),"Unknown Model suffix was not warned");
        p.data.pop_back();--p.exports[0].size;
        p.version=133;p.licensee=40;check(modelFails(),"Unverified Model profile accepted");
        p.data.insert(p.data.end(),5,0);p.exports[0].size+=5;
        auto partial=p.geometry(1,"model_collision");
        check(partial["status"]=="partial"&&partial["remaining_bytes"]==5&&
              partial["reconstruction_supported"]==false&&
              partial["points"]==model["points"]&&partial["hulls"]==model["hulls"],
              "Bounded Model prefix or partial status lost");
        auto fullBrush=p.geometry(1,"model");
        check(fullBrush["status"]=="decoded"&&fullBrush["profile"]==ue::Json::array({133,40})&&
              fullBrush["remaining_bytes"]==0&&
              fullBrush["sections"].empty()&&fullBrush["trailer"]["final_word"]==0&&
              fullBrush["reconstruction_supported"]==false,
              "Complete empty 133/40 brush not decoded");
        auto adjacentData=p.data;
        for(auto profile:{std::pair<int,int>{127,39},{128,39},{130,40},{132,40}}){
            p.version=profile.first;p.licensee=profile.second;
            auto adjacent=p.geometry(1,"model");
            check(adjacent["status"]=="decoded"&&
                  adjacent["profile"]==ue::Json::array({profile.first,profile.second})&&
                  adjacent["points"]==fullBrush["points"]&&adjacent["hulls"]==fullBrush["hulls"]&&
                  adjacent["trailer"]["pairs"].empty()&&adjacent["trailer"]["final_word"]==0&&
                  adjacent["reconstruction_supported"]==false,
                  "Adjacent empty-array Model was not decoded");
            for(size_t i=0;i<5;++i){
                p.data[p.data.size()-5+i]=1;
                auto result=p.geometry(1,"model");
                check(result["status"]=="unverified"&&result.contains("warning")&&
                      result["reconstruction_supported"]==false,
                      "Nonzero adjacent Model suffix was not warned");p.data=adjacentData;
            }
            for(auto offset:{zoneOffset,leavesOffset,leavesOffset+1,arraysOffset+2}){
                p.data[64+offset]=1;
                auto result=p.geometry(1,"model");
                check(result["status"]=="unverified"&&result.contains("warning")&&
                      result["reconstruction_supported"]==false,
                      "Nonempty adjacent Model array was not warned");p.data=adjacentData;
            }
            p.data[64+arraysOffset]=1;p.data.insert(p.data.end(),17,0);
            p.exports[0].size+=17;
            check(p.geometry(1,"model")["status"]=="unverified",
                  "Nonempty adjacent Model sections were not warned");
            p.data=adjacentData;p.exports[0].size-=17;
            // Provide enough bytes for the lightmap count check.
            p.data[64+arraysOffset+1]=1;p.data.insert(p.data.end(),113,0);
            p.exports[0].size+=113;
            check(p.geometry(1,"model")["status"]=="unverified",
                  "Nonempty adjacent Model lightmaps were not warned");
            p.data=adjacentData;p.exports[0].size-=113;
            for(size_t length=0;length<p.exports[0].size;++length){
                auto size=p.exports[0].size;p.exports[0].size=length;
                if(length<size-5)check(modelFails(),"Truncated verified Model prefix accepted");
                else{
                    auto incomplete=p.geometry(1,"model");
                    check(incomplete["status"]=="unverified"&&
                          incomplete["interpretation"]=="opaque"&&incomplete.contains("warning"),
                          "Unknown adjacent suffix was not preserved as an opaque warning");
                }
                p.exports[0].size=size;
            }
        }
        p.version=129;p.licensee=39;
        auto unknown=p.geometry(1,"model");
        check(unknown["status"]=="unverified"&&unknown.contains("warning")&&
              unknown["points"]==fullBrush["points"]&&unknown["reconstruction_supported"]==false,
              "Unknown profile was not processed with a warning");
        p.exports[0].flags=0x02000000;
        auto stacked=p.geometry(1,"model");
        check(stacked["status"]=="unverified"&&stacked["interpretation"]=="opaque"&&
              stacked["raw_preview_hex"].get<std::string>().size()<=512&&
              stacked["reconstruction_supported"]==false,
              "Stacked Model was not preserved as a warned opaque preview");
        p.exports[0].flags=0;
        p.data.insert(p.data.begin()+64,{1,0x83});p.exports[0].size+=2;
        p.version=133;p.licensee=40;
        auto tagged=p.geometry(1,"model");
        check(tagged["status"]=="unverified"&&tagged["uninterpreted_tags"].size()==1&&
              tagged["uninterpreted_tags"][0]["name"]=="Materials"&&
              tagged["points"]==fullBrush["points"],
              "Tagged Model was not processed with a warning");
        p.data=adjacentData;p.exports[0].size-=2;
        p.version=133;p.licensee=40;
        auto partialFails=[&](){try{p.geometry(1,"model_collision");}catch(const std::exception&){return true;}return false;};
        for(size_t i=0;i<5;++i){
            p.data[p.data.size()-5+i]=1;
            check(partialFails(),"Nonzero unknown Model suffix accepted");
            p.data[p.data.size()-5+i]=0;
        }
        for(size_t length=0;length<p.exports[0].size;++length){
            auto previous=p.exports[0].size;p.exports[0].size=length;
            check(partialFails(),"Truncated partial Model accepted");p.exports[0].size=previous;
        }
        p.data.push_back(0);++p.exports[0].size;check(partialFails(),"Extra Model suffix accepted");
        p.data.pop_back();--p.exports[0].size;
        p.version=123;p.licensee=37;check(partialFails(),"Partial path accepted wrong Model profile");
        p.version=133;p.licensee=40;
        ue::Bytes brush=b;brush[pointOffset-1]=3;
        brush.insert(brush.begin()+pointOffset+2,{1,0x81,0x81,0x82});
        brush.insert(brush.end(),5,0);
        p.data.assign(64,0);p.data.insert(p.data.end(),brush.begin(),brush.end());
        p.exports[0].size=brush.size();
        auto brushWithUnused=p.geometry(1,"model_collision");
        check(brushWithUnused["status"]=="partial"&&brushWithUnused["remaining_bytes"]==5&&
              brushWithUnused["invalid_unused_vertices"].size()==2&&
              brushWithUnused["invalid_unused_vertices"][0]["vertex"]==1&&
              brushWithUnused["invalid_unused_vertices"][0]["point"]==1&&
              brushWithUnused["invalid_unused_vertices"][1]["vertex"]==2&&
              brushWithUnused["invalid_unused_vertices"][1]["point"]==-1&&
              brushWithUnused["invalid_unused_vertices"][1]["side"]==-2,
              "Unused invalid brush vertices not reported");
        p.data[64+pointOffset]=1;check(partialFails(),"Invalid used brush vertex accepted");
        p.data[64+pointOffset]=0;
        p.data[64+nodeLeavesOffset-1]=2;check(partialFails(),"Newly used invalid brush vertex accepted");
        p.data[64+nodeLeavesOffset-1]=1;
        p.version=123;p.licensee=37;p.exports[0].size-=5;
        check(modelFails(),"Full legacy Model accepted invalid unused vertices");
        p.version=133;p.licensee=40;
        ue::Bytes level=b;
        set32(level,zoneOffset,1);set32(level,nodeLeavesOffset,0xffffffff);set32(level,nodeLeavesOffset+4,0xffffffff);
        level.insert(level.begin()+zoneOffset+4,21,0); // null actor, two masks, one time word.
        level[pointOffset-1]=2;
        level.insert(level.begin()+pointOffset+2,{1,0x81}); // invalid but unused point index.
        level.resize(level.size()-3);level.insert(level.end(),{1,0xaa,0xbb}); // unparsed nonempty sections.
        p.data.assign(64,0);p.data.insert(p.data.end(),level.begin(),level.end());
        p.exports[0].size=level.size();
        auto levelModel=p.geometry(1,"model_level_geometry");
        check(levelModel["status"]=="partial"&&levelModel["remaining_bytes"]==3&&
              levelModel["render_sections_declared"]==1&&
              levelModel["invalid_unused_vertices"].size()==1&&
              levelModel["reconstruction_supported"]==false,"Partial level geometry status lost");
        auto levelFails=[&](){try{p.geometry(1,"model_level_geometry");}catch(const std::exception&){return true;}return false;};
        p.data[64+pointOffset]=1;check(levelFails(),"Invalid vertex used by a node accepted");
        p.data[64+pointOffset]=0;
        p.data[64+zoneOffset+2]=0; // zoneOffset shifted by the inserted unused vertex.
        check(levelFails(),"Invalid or empty level zones accepted");

        // Independently constructed full 133/40 render data, with multi-byte
        // counts and two absolute lazy boundaries.
        ue::Bytes full=b;full.resize(full.size()-3);
        full.push_back(1);full.push_back(1); // one section, one vertex
        for(uint32_t i=0;i<10;++i)u32(full,i==4?0x7fc12345u:i);
        u32(full,9);full.push_back(0x82);
        for(uint32_t i=0;i<3;++i)u32(full,11+i);
        full.push_back(1); // one lightmap
        full.insert(full.end(),{0,0x81,2,3,4,5,6});
        for(uint32_t i=0;i<25;++i)u32(full,i==10?0x80000000u:i);
        full.push_back(1);full.push_back(0x82);
        full.insert(full.end(),{0x40,0x01}); // bitmap count 64
        for(uint32_t i=0;i<64;++i)full.push_back(uint8_t(i));
        for(uint32_t i=0;i<7;++i)u32(full,20+i);
        full.push_back(0x82);u32(full,0x89abcdefu);
        full.push_back(1);full.push_back(1);full.push_back(0x82); // group, page, level
        full.push_back(2);u32(full,0);u32(full,0xffffffffu);
        for(uint32_t i=0;i<3;++i)u32(full,30+i);
        auto lazy0=full.size();u32(full,0);full.insert(full.end(),{0x40,0x01});
        for(uint32_t i=0;i<64;++i)full.push_back(uint8_t(255-i));
        set32(full,lazy0,uint32_t(64+full.size()));
        auto lazy1=full.size();u32(full,0);full.insert(full.end(),{3,10,20,30});
        set32(full,lazy1,uint32_t(64+full.size()));
        full.push_back(3);u32(full,256);u32(full,128);u32(full,2);
        full.push_back(1);u32(full,123);full.push_back(0x82);
        full.insert(full.end(),{0x40,0x01}); // trailer count 64
        for(uint32_t i=0;i<64;++i){u32(full,i);u32(full,512+i);}
        u32(full,1);
        p.data.assign(64,0);p.data.insert(p.data.end(),full.begin(),full.end());
        p.exports[0].offset=64;p.exports[0].size=full.size();
        auto complete=p.geometry(1,"model");
        check(complete["status"]=="decoded"&&complete["remaining_bytes"]==0&&
              complete["sections"][0]["vertices_bits"][0][4]==0x7fc12345u&&
              complete["sections"][0]["material"]["id"]==-2&&
              complete["lightmaps"][0]["matrix_and_vectors_bits"][10]==0x80000000u&&
              complete["lightmaps"][0]["masks"][0]["bitmap_hex"].get<std::string>().size()==128&&
              complete["lightmaps"][0]["masks"][0]["light"]["id"]==-2&&
              complete["lightmaps"][0]["level"]["id"]==-2&&
              complete["lightmap_groups"][0]["pages"][0]["level"]["id"]==-2&&
              complete["lightmap_groups"][0]["level"]["id"]==-2&&
              complete["lightmap_groups"][0]["pages"][0]["buffers"][0]["data_hex"].get<std::string>().size()==128&&
              complete["lightmap_groups"][0]["pages"][0]["buffers"][1]["data_hex"]=="0a141e"&&
              complete["trailer"]["pairs"].size()==64&&complete["trailer"]["final_word"]==1,
              "Full 133/40 Model fields lost");
        p.data[64+lazy0]^=1;check(modelFails(),"Invalid first Model lazy boundary accepted");p.data[64+lazy0]^=1;
        p.data[64+lazy1]^=1;check(modelFails(),"Invalid second Model lazy boundary accepted");p.data[64+lazy1]^=1;
        p.data[64+pointOffset]=1;check(modelFails(),"Invalid node-used point accepted");p.data[64+pointOffset]=0;
        p.data[64+planeOffset]=1;check(modelFails(),"Invalid node-linked hull accepted");
        p.data[64+nodeIndicesOffset+5]=0x81; // the invalid hull is no longer node-linked
        auto unlinked=p.geometry(1,"model");
        check(unlinked["invalid_unlinked_hull_planes"].size()==1&&
              unlinked["hulls"][0]["planes"][0]==0x40000001u,
              "Unlinked invalid hull was not retained and diagnosed");
        p.data[64+planeOffset]=0;p.data[64+nodeIndicesOffset+5]=0;
        for(size_t length=0;length<full.size();++length){
            p.exports[0].size=length;check(modelFails(),"Truncated full 133/40 Model accepted");
        }
        p.exports[0].size=full.size();p.data.push_back(0);++p.exports[0].size;
        auto extraFull=p.geometry(1,"model");
        check(extraFull["status"]=="unverified"&&extraFull["remaining_bytes"]==1&&
              extraFull.contains("warning"),"Trailing full Model byte was not warned");
        p.data.pop_back();--p.exports[0].size;p.version=132;
        auto expanded=p.geometry(1,"model");
        check(expanded["status"]=="unverified"&&expanded.contains("warning")&&
              expanded["sections"]==complete["sections"]&&
              expanded["lightmaps"]==complete["lightmaps"]&&
              expanded["lightmap_groups"]==complete["lightmap_groups"]&&
              expanded["trailer"]==complete["trailer"],
              "Nonempty adjacent-profile Model was not processed with a warning");
        std::cout<<"StaticMesh and Model checks passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
