#include "package.h"
#include <algorithm>
#include <stdexcept>

namespace ue {
namespace {
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
size_t count(Reader& r,size_t stride,size_t maximum=1000000){
    int n=r.index();
    require(n>=0&&size_t(n)<=maximum,"Invalid StaticMesh array count");
    require(size_t(n)<=(r.end-r.pos)/stride,"Truncated StaticMesh array");
    return size_t(n);
}
size_t modelCount(Reader& r,size_t stride,size_t maximum,bool adjacent,bool& unverified){
    int n=r.index();
    if(adjacent&&n>0)unverified=true;
    require(n>=0&&size_t(n)<=maximum,"Invalid Model array count");
    require(size_t(n)<=(r.end-r.pos)/stride,"Truncated Model array");
    return size_t(n);
}
Json words(Reader& r,size_t n){
    r.require(n*4);Json out=Json::array();
    for(size_t i=0;i<n;++i)out.push_back(r.u32());
    return out;
}
Json box(Reader& r){
    Json out={{"min_bits",words(r,3)},{"max_bits",words(r,3)}};
    auto valid=r.byte();require(valid<=1,"Invalid StaticMesh box flag");out["valid"]=valid;
    return out;
}
int subscript(Reader& r){
    int b=r.byte();if(b<128)return b;
    if(b<192)return ((b&63)<<8)|r.byte();
    int n=(b&63)<<24;n|=int(r.byte())<<16;n|=int(r.byte())<<8;return n|r.byte();
}
Json reference(const Package& p,int id){
    return {{"id",id},{"path",p.ref(id)},{"class",id?p.kind(id):"None"}};
}
Json tags(const Package& p,Reader& r,bool nested=false){
    Json out=Json::array();
    for(;;){
        auto name=p.name(r.index());if(lower(name)=="none")break;
        require(out.size()<10000,"Excessive StaticMesh properties");
        int info=r.byte(),kind=info&15,code=(info>>4)&7;
        std::string structure;if(kind==10)structure=p.name(r.index());
        const int sizes[]={1,2,4,12,16};
        int size=code<5?sizes[code]:code==5?r.byte():code==6?r.u16():r.i32();
        require(size>=0,"Negative StaticMesh property size");
        Json tag={{"name",name},{"kind",kind}};
        if(kind==3){tag["value"]=bool(info&128);tag["declared_size"]=size;out.push_back(tag);continue;}
        if(info&128)tag["subscript"]=subscript(r);
        r.require(size_t(size));Reader v(r.data,r.pos,size_t(size));r.skip(size_t(size));
        if(kind==9&&!nested&&lower(name)=="materials"){
            Json materials=Json::array();auto n=count(v,1,65536);
            for(size_t i=0;i<n;++i)materials.push_back(tags(p,v,true));
            tag["value"]=std::move(materials);
        }else if(kind==5)tag["value"]=reference(p,v.index());
        else if(kind==6)tag["value"]=p.name(v.index());
        else if(kind==1)tag["value"]=v.byte();
        else if(kind==2)tag["value"]=v.i32();
        else if(kind==4)tag["bits"]=v.u32();
        else throw std::runtime_error("Unsupported StaticMesh property: "+name);
        require(v.pos==v.end,"Trailing StaticMesh property bytes");out.push_back(std::move(tag));
    }
    return out;
}
// Model tags outside the observed empty-tag form are retained as metadata,
// not interpreted as proof of their property or reference semantics.
Json modelTagHeaders(const Package& p,Reader& r){
    Json out=Json::array();
    for(;;){
        auto name=p.name(r.index());if(lower(name)=="none")break;
        require(out.size()<10000,"Excessive Model properties");
        int info=r.byte(),kind=info&15,code=(info>>4)&7;
        std::string structure;if(kind==10)structure=p.name(r.index());
        const int sizes[]={1,2,4,12,16};
        int size=code<5?sizes[code]:code==5?r.byte():code==6?r.u16():r.i32();
        require(size>=0,"Negative Model property size");
        Json tag={{"name",name},{"kind",kind},{"declared_size",size}};
        if(kind==10)tag["structure"]=structure;
        if(kind==3)tag["boolean_bit"]=bool(info&128);
        else{
            if(info&128)tag["subscript"]=subscript(r);
            r.skip(size_t(size));
        }
        out.push_back(std::move(tag));
    }
    return out;
}
void lazyEnd(const Reader& r,uint32_t end){
    require(!end||end==r.pos,"Invalid StaticMesh lazy-array offset");
}
std::string byteArrayHex(Reader& r,size_t maximum){
    auto n=count(r,1,maximum);r.require(n);
    Bytes data(r.data.begin()+r.pos,r.data.begin()+r.pos+n);r.skip(n);
    return hex(data);
}
}

Json Package::geometry(int id,const std::string& operation) const {
    auto type=kind(id);
    if(operation=="model"||operation=="model_collision"||operation=="model_level_geometry"){
        const bool level=operation=="model_level_geometry";
        const bool partial=operation!="model";
        const bool adjacent=!partial&&(((version==127||version==128)&&licensee==39)||
                                         ((version==130||version==132)&&licensee==40));
        const bool legacy=!partial&&version==123&&licensee==37;
        const bool known133=!partial&&version==133&&licensee==40;
        const bool fullObserved=!partial&&!legacy;
        require(id>0&&type=="Model"&&(!partial||(version==133&&licensee==40)),
                "Unsupported Model class/profile");
        bool unverified=!partial&&!legacy&&!known133&&!adjacent;
        auto opaque=[&](const std::string& reason){
            const auto& e=entry(id);Reader raw(data,e.offset,e.size);
            auto size=std::min<size_t>(e.size,256);raw.require(size);
            Bytes preview(raw.data.begin()+raw.pos,raw.data.begin()+raw.pos+size);
            return Json{{"schema",1},{"path",ref(id)},{"class",type},
                        {"profile",Json::array({version,licensee})},
                        {"status","unverified"},{"interpretation","opaque"},
                        {"warning","Model layout is unverified; only a bounded raw preview is available"},
                        {"reason",reason},{"serialized_bytes",e.size},{"raw_preview_hex",hex(preview)},
                        {"decoded_native_bytes",0},{"remaining_bytes",e.size},
                        {"reconstruction_supported",false},
                        {"scope","opaque saved bytes; no geometry or runtime behavior established"}};
        };
        if(!partial&&(entry(id).flags&0x02000000))
            return opaque("Serialized execution stack is not interpreted");
        require(!(entry(id).flags&0x02000000),"Stacked Model unsupported");
        auto parse=[&]() -> Json {
        auto r=reader(id);auto tagStart=r.pos;auto firstTag=name(r.index());Json modelTags=Json::array();
        if(lower(firstTag)!="none"){
            require(!partial,"Unsupported Model properties");
            unverified=true;r.pos=tagStart;modelTags=modelTagHeaders(*this,r);
        }
        auto start=r.pos;
        Json out={{"schema",1},{"path",ref(id)},{"class",type},{"bounds",box(r)},
                  {"sphere_bits",words(r,4)}};
        if(!modelTags.empty())out["uninterpreted_tags"]=std::move(modelTags);
        for(auto field:{"vectors","points"}){
            Json a=Json::array();auto n=count(r,12);
            for(size_t i=0;i<n;++i)a.push_back(words(r,3));
            out[field]=std::move(a);
        }
        Json nodes=Json::array();auto n=count(r,87);
        for(size_t i=0;i<n;++i){
            Json node={{"plane_bits",words(r,4)},{"zone_mask",words(r,2)},{"flags",r.byte()}};
            for(auto key:{"vertex_pool","surface","back","front","coplanar","collision_bound","render_bound"})
                node[key]=r.index();
            node["spheres_bits"]=words(r,8);
            node["zones"]=Json::array({r.byte(),r.byte()});node["vertex_count"]=r.byte();
            node["leaves"]=words(r,2);node["render_indices"]=words(r,3);nodes.push_back(node);
        }
        out["nodes"]=nodes;
        Json surfaces=Json::array();n=count(r,35);
        for(size_t i=0;i<n;++i){
            Json s={{"material",reference(*this,r.index())},{"flags",r.u32()}};
            for(auto key:{"base","normal","texture_u","texture_v","brush_polygon"})s[key]=r.index();
            s["actor"]=reference(*this,r.index());s["plane_bits"]=words(r,4);
            s["light_map_scale_bits"]=r.u32();s["license_word"]=r.u32();surfaces.push_back(s);
        }
        out["surfaces"]=surfaces;
        Json vertices=Json::array();n=count(r,2);
        for(size_t i=0;i<n;++i)vertices.push_back(Json::array({r.index(),r.index()}));
        out["vertices"]=vertices;out["shared_sides"]=r.u32();
        auto zoneCount=r.u32();
        if(adjacent&&zoneCount)unverified=true;
        if(legacy&&zoneCount)unverified=true;
        require(fullObserved?zoneCount<=64:level?(zoneCount>0&&zoneCount<=64):zoneCount==0,
                "Unsupported Model zones");
        Json zones=Json::array();
        if(level||fullObserved)for(uint32_t i=0;i<zoneCount;++i){
            Json zone={{"actor",reference(*this,r.index())},
                       {"connectivity",words(r,2)},{"visibility",words(r,2)},
                       {"render_time_bits",r.u32()}};
            zones.push_back(std::move(zone));
        }
        if(level||fullObserved)out["zones"]=zones;
        out["polys"]=reference(*this,r.index());
        Json bounds=Json::array();n=count(r,25);
        for(size_t i=0;i<n;++i)bounds.push_back(box(r));
        out["render_bounds"]=bounds;
        Json hulls=Json::array();n=count(r,4);size_t offset=0;std::set<int> hullOffsets;
        std::map<int,size_t> hullNumbers;
        while(n){
            hullOffsets.insert(int(offset));hullNumbers[int(offset)]=hulls.size();Json planes=Json::array();
            for(;;){
                require(n>0,"Missing Model hull terminator");
                auto word=r.u32();--n;++offset;if(word==0xffffffffU)break;
                require(fullObserved||(word&0x3fffffffU)<nodes.size(),"Invalid Model hull plane");
                planes.push_back(word);
            }
            require(n>=6,"Truncated Model hull bounds");
            hulls.push_back({{"planes",planes},{"bounds_bits",words(r,6)}});n-=6;offset+=6;
        }
        out["hulls"]=hulls;
        Json leaves=Json::array(),lights=Json::array();
        if(level||fullObserved){
            n=modelCount(r,11,1000000,adjacent,unverified);
            for(size_t i=0;i<n;++i){
                Json leaf={{"zone",r.index()},{"permeating",r.index()},{"volumetric",r.index()},
                           {"visible_zones",words(r,2)}};
                leaves.push_back(std::move(leaf));
            }
            n=modelCount(r,1,1000000,adjacent,unverified);
            for(size_t i=0;i<n;++i)lights.push_back(reference(*this,r.index()));
            out["leaves"]=leaves;out["lights"]=lights;
        }else{
            auto leafCount=r.index();if(legacy&&leafCount)unverified=true;
            require(leafCount==0,"Unsupported Model leaves");
            auto lightCount=r.index();if(legacy&&lightCount)unverified=true;
            require(lightCount==0,"Unsupported Model lights");
        }
        out["root_outside"]=r.u32();out["linked"]=r.u32();
        if(!level&&!fullObserved)for(int i=0;i<3;++i){
            auto size=r.index();if(legacy&&size)unverified=true;
            require(size==0,"Unsupported Model render arrays");
        }
        auto valid=[](int value,size_t size){return value>=0&&size_t(value)<size;};
        for(const auto& s:surfaces){
            require(valid(s["base"],out["points"].size()),"Invalid Model surface point");
            for(auto key:{"normal","texture_u","texture_v"})
                require(valid(s[key],out["vectors"].size()),"Invalid Model surface vector");
        }
        std::vector<bool> used(vertices.size(),false);
        for(const auto& node:nodes){
            require(valid(node["surface"],surfaces.size()),"Invalid Model surface index");
            int first=node["vertex_pool"],length=node["vertex_count"];
            require(first>=0&&size_t(first)<=vertices.size()&&
                    size_t(length)<=vertices.size()-size_t(first),"Invalid Model vertex range");
            for(int i=0;i<length;++i)used[size_t(first+i)]=true;
            for(auto key:{"back","front","coplanar"})
                require(node[key]==-1||valid(node[key],nodes.size()),"Invalid Model node link");
            require(node["collision_bound"]==-1||hullOffsets.count(node["collision_bound"]),
                    "Invalid Model hull offset");
            if(fullObserved&&node["collision_bound"]!=-1)
                for(const auto& plane:hulls[hullNumbers.at(node["collision_bound"].get<int>())]["planes"])
                    require((plane.get<uint32_t>()&0x3fffffffU)<nodes.size(),
                            "Invalid Model node-linked hull plane");
            require(node["render_bound"]==-1||valid(node["render_bound"],bounds.size()),
                    "Invalid Model render bound");
            if(level){
                for(const auto& zone:node["zones"])
                    require(zone.get<uint32_t>()<zoneCount,"Invalid Model node zone");
                for(const auto& leaf:node["leaves"]){
                    auto index=leaf.get<uint32_t>();
                    require(index==0xffffffffU||index<leaves.size(),"Invalid Model node leaf");
                }
            }
        }
        Json invalidUnused=Json::array();
        for(size_t i=0;i<vertices.size();++i){
            const auto& v=vertices[i];
            if(!valid(v[0],out["points"].size())){
                require((partial||fullObserved)&&!used[i],"Invalid Model vertex point");
                invalidUnused.push_back({{"vertex",i},{"point",v[0]},{"side",v[1]}});
            }
        }
        if(level){
            for(const auto& leaf:leaves){
                int zone=leaf["zone"],permeating=leaf["permeating"],volumetric=leaf["volumetric"];
                require(zone>=0&&uint32_t(zone)<zoneCount,"Invalid Model leaf zone");
                require((permeating==-1||valid(permeating,lights.size()))&&
                        (volumetric==-1||valid(volumetric,lights.size())),"Invalid Model leaf light index");
            }
            require(r.end-r.pos<=64*1024*1024,"Model render remainder exceeds preview limits");
            Reader render(r.data,r.pos,r.end-r.pos);
            auto sections=count(render,1,65536);
            require(sections>0,"Unsupported empty Model level render data");
            out["invalid_unused_vertices"]=std::move(invalidUnused);
            out["render_sections_declared"]=sections;
            out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;
            out["remaining_bytes"]=r.end-r.pos;out["status"]="partial";
            out["reconstruction_supported"]=false;
            out["scope"]="checked level geometry prefix; render data and runtime collision excluded";
            return out;
        }
        if(partial){
            // The 133/40 brush corpus has five zero bytes after the checked
            // arrays. Their fields are not understood; never copy or report
            // them as decoded, and reject any other suffix or render layout.
            require(r.end-r.pos==5,"Unsupported Model collision suffix length");
            for(size_t i=r.pos;i<r.end;++i)
                require(r.data[i]==0,"Unsupported Model collision suffix");
            if(!invalidUnused.empty())out["invalid_unused_vertices"]=std::move(invalidUnused);
            out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;
            out["remaining_bytes"]=5;out["status"]="partial";
            out["reconstruction_supported"]=false;
            out["scope"]="checked geometry prefix; unknown suffix and runtime collision excluded";
            return out;
        }
        if(fullObserved){
            out["profile"]=Json::array({version,licensee});
            Json invalidHulls=Json::array();
            for(size_t i=0;i<hulls.size();++i)
                for(size_t j=0;j<hulls[i]["planes"].size();++j)
                    if((hulls[i]["planes"][j].get<uint32_t>()&0x3fffffffU)>=nodes.size())
                        invalidHulls.push_back({{"hull",i},{"plane",j},{"word",hulls[i]["planes"][j]}});
            out["invalid_unused_vertices"]=std::move(invalidUnused);
            out["invalid_unlinked_hull_planes"]=std::move(invalidHulls);
            Json sections=Json::array();n=modelCount(r,17,65536,adjacent,unverified);
            for(size_t i=0;i<n;++i){
                Json vertices=Json::array();auto num=count(r,40);
                for(size_t j=0;j<num;++j)vertices.push_back(words(r,10));
                Json section={{"vertices_bits",std::move(vertices)},{"revision",r.u32()},
                              {"material",reference(*this,r.index())},{"words",words(r,3)}};
                sections.push_back(std::move(section));
            }
            out["sections"]=std::move(sections);
            Json lightmaps=Json::array();n=modelCount(r,113,1000000,adjacent,unverified);
            for(size_t i=0;i<n;++i){
                Json indices=Json::array();for(int j=0;j<7;++j)indices.push_back(r.index());
                Json record={{"indices",std::move(indices)},{"matrix_and_vectors_bits",words(r,25)}};
                Json masks=Json::array();auto num=count(r,30,100000);
                for(size_t j=0;j<num;++j){
                    Json mask={{"light",reference(*this,r.index())},
                               {"bitmap_hex",byteArrayHex(r,64*1024*1024)},{"words",words(r,7)}};
                    masks.push_back(std::move(mask));
                }
                record["masks"]=std::move(masks);record["level"]=reference(*this,r.index());
                record["revision"]=r.u32();lightmaps.push_back(std::move(record));
            }
            out["lightmaps"]=std::move(lightmaps);
            Json groups=Json::array();n=modelCount(r,3,65536,adjacent,unverified);
            for(size_t i=0;i<n;++i){
                Json pages=Json::array();auto pageCount=count(r,28,4096);
                for(size_t j=0;j<pageCount;++j){
                    Json page={{"level",reference(*this,r.index())}};
                    page["indices"]=words(r,count(r,4));page["words"]=words(r,3);
                    Json buffers=Json::array();
                    for(int k=0;k<2;++k){
                        auto end=r.u32();auto data=byteArrayHex(r,64*1024*1024);lazyEnd(r,end);
                        buffers.push_back({{"has_lazy_offset",end!=0},{"data_hex",std::move(data)}});
                    }
                    page["buffers"]=std::move(buffers);page["format"]=r.byte();
                    page["dimensions_and_revision"]=words(r,3);pages.push_back(std::move(page));
                }
                Json group={{"pages",std::move(pages)}};
                group["indices"]=words(r,count(r,4));group["level"]=reference(*this,r.index());
                groups.push_back(std::move(group));
            }
            out["lightmap_groups"]=std::move(groups);
            if(adjacent){
                if(r.end-r.pos!=5)unverified=true;
                for(size_t i=r.pos;i<r.end;++i)
                    if(r.data[i]!=0){unverified=true;break;}
            }
            Json pairs=Json::array();n=count(r,8);
            for(size_t i=0;i<n;++i)pairs.push_back(words(r,2));
            out["trailer"]={{"pairs",std::move(pairs)},{"final_word",r.u32()}};
            if(r.pos!=r.end)unverified=true;
            out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;
            out["remaining_bytes"]=r.end-r.pos;out["status"]=unverified?"unverified":"decoded";
            out["reconstruction_supported"]=false;
            if(unverified)out["warning"]="Model layout is unverified; fields use an assumed 133/40 layout";
            out["scope"]=unverified?"unverified layout interpretation; runtime rendering and collision excluded":
                         adjacent?"observed empty-array Model structure; runtime rendering and collision excluded":
                                   "saved Model structure; runtime rendering and collision excluded";
            return out;
        }
        if(!partial&&r.pos!=r.end)unverified=true;
        else require(r.pos==r.end,"Trailing Model native bytes");
        out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;
        out["remaining_bytes"]=r.end-r.pos;out["status"]=unverified?"unverified":"decoded";
        if(unverified){
            out["profile"]=Json::array({version,licensee});
            out["warning"]="Model layout is unverified; unknown bytes or properties remain";
            out["reconstruction_supported"]=false;
            out["scope"]="unverified layout interpretation; runtime rendering and collision excluded";
        }
        return out;
        };
        try{return parse();}
        catch(const std::runtime_error& error){
            if(!partial&&unverified)return opaque(error.what());
            throw;
        }
    }
    require((operation=="polys"&&type=="Polys")||(operation=="karma_props"&&type=="KMeshProps"),
            "Geometry class does not match operation");
    require((version==123&&licensee==37)||(version==127&&licensee==39)||
            (type=="Polys"&&version==128&&licensee==39)||
            ((version==130||version==132||version==133)&&licensee==40),"Unsupported geometry profile");
    require(!(entry(id).flags&0x02000000),"Stacked geometry is unsupported");
    auto r=reader(id);require(lower(name(r.index()))=="none","Unsupported geometry properties");
    auto start=r.pos;Json out={{"schema",1},{"path",ref(id)},{"class",type},{"tags",Json::array()}};
    if(type=="KMeshProps"){
        out["scalar_bits"]=words(r,9);Json arrays=Json::array();
        for(int i=0;i<4;++i){require(r.index()==0,"Unsupported nonempty Karma geometry");arrays.push_back(Json::array());}
        out["geometry_arrays"]=std::move(arrays);
    }else{
        auto n=r.u32(),capacity=r.u32();
        require(n<=1000000&&capacity>=n&&capacity<=1000000,"Invalid polygon count or capacity");
        out["capacity"]=capacity;Json polygons=Json::array();
        for(uint32_t i=0;i<n;++i){
            int vertices=r.index();require(vertices>=0&&vertices<=16,"Invalid polygon vertex count");
            Json poly={{"base_bits",words(r,3)},{"normal_bits",words(r,3)},
                       {"texture_u_bits",words(r,3)},{"texture_v_bits",words(r,3)}};
            Json points=Json::array();for(int j=0;j<vertices;++j)points.push_back(words(r,3));
            poly["vertices_bits"]=std::move(points);poly["flags"]=r.u32();
            poly["actor"]=reference(*this,r.index());poly["material"]=reference(*this,r.index());
            poly["item_name"]=name(r.index());poly["link"]=r.index();poly["brush_polygon"]=r.index();
            poly["light_map_scale_bits"]=r.u32();poly["license_word"]=r.u32();polygons.push_back(std::move(poly));
        }
        out["polygons"]=std::move(polygons);
    }
    require(r.pos==r.end,"Trailing geometry native bytes");
    out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;out["remaining_bytes"]=0;
    out["status"]="decoded";out["reconstruction_supported"]=false;return out;
}
Json Package::staticMesh(int id) const {
    const std::set<int> legacy={12,14,15,16,18,19,20,22,23,25,28,31,33,35,36,37,38};
    require((version==118&&licensee==0)||(version==123&&legacy.count(licensee))||
            (version==125&&(licensee==38||licensee==39))||(version>=126&&version<=128&&licensee==39)||
            (version>=130&&version<=133&&licensee==40),"Unsupported StaticMesh profile");
    require(kind(id)=="StaticMesh","Not a StaticMesh export");
    require(!(entry(id).flags&0x02000000),"Stacked StaticMesh is unsupported");
    auto r=reader(id);Json out={{"schema",1},{"path",ref(id)},{"tags",tags(*this,r)}};
    auto nativeStart=r.pos;
    out["bounds"]=box(r);out["sphere_bits"]=words(r,4);
    Json sections=Json::array();auto n=count(r,14,65536);
    for(size_t i=0;i<n;++i){
        Json s={{"flags",r.u32()},{"first_index",r.u16()},{"first_vertex",r.u16()},
                {"last_vertex",r.u16()},{"section_word",r.u16()},{"face_count",r.u16()}};
        sections.push_back(std::move(s));
    }
    out["mesh_bounds"]=box(r);
    Json vertices=Json::array();auto vertexCount=count(r,24,65536);
    for(size_t i=0;i<vertexCount;++i)vertices.push_back({{"position_bits",words(r,3)},{"normal_bits",words(r,3)}});
    out["vertices"]=std::move(vertices);out["vertex_revision"]=r.u32();
    for(auto field:{"colors","alpha"}){
        auto size=count(r,4,65536);out[field]=words(r,size);
        out[std::string(field)+"_revision"]=r.u32();
    }
    Json uv=Json::array();n=count(r,9,8);
    for(size_t i=0;i<n;++i){
        Json values=Json::array();auto size=count(r,8,65536);
        for(size_t j=0;j<size;++j)values.push_back(words(r,2));
        uv.push_back({{"coordinate_bits",std::move(values)},{"coordinate_index",r.u32()},{"revision",r.u32()}});
    }
    out["uv_streams"]=std::move(uv);
    for(auto field:{"indices","wire_indices"}){
        Json values=Json::array();n=count(r,2);
        for(size_t i=0;i<n;++i){auto index=r.u16();require(index<vertexCount,"Invalid StaticMesh vertex index");values.push_back(index);}
        out[field]=std::move(values);out[std::string(field)+"_revision"]=r.u32();
    }
    for(const auto& section:sections){
        auto first=section["first_index"].get<size_t>(),faces=section["face_count"].get<size_t>();
        require(first<=out["indices"].size()&&faces<=(out["indices"].size()-first)/3,"Invalid StaticMesh section range");
        if(faces)require(section["first_vertex"].get<size_t>()<=section["last_vertex"].get<size_t>()&&
                         section["last_vertex"].get<size_t>()<vertexCount,"Invalid StaticMesh section vertices");
    }
    out["sections"]=std::move(sections);
    out["collision_model"]=reference(*this,r.index());
    auto end=licensee>=17?r.u32():0;n=count(r,68);
    Json faces=Json::array();
    for(size_t i=0;i<n;++i){
        Json face={{"plane_bits",words(r,16)}};Json indices=Json::array();
        for(int j=0;j<3;++j){int index=r.index();require(index>=0&&size_t(index)<vertexCount,"Invalid collision vertex index");indices.push_back(index);}
        face["vertices"]=std::move(indices);int material=r.index();
        require(material>=0,"Negative collision material index");face["material_index"]=material;
        faces.push_back(std::move(face));
    }
    lazyEnd(r,end);out["collision_faces"]=std::move(faces);
    end=licensee>=17?r.u32():0;n=count(r,29);Json nodes=Json::array();
    for(size_t i=0;i<n;++i){
        Json links=Json::array();for(int j=0;j<4;++j)links.push_back(r.index());
        nodes.push_back({{"indices",std::move(links)},{"bounds",box(r)}});
    }
    lazyEnd(r,end);out["collision_nodes"]=std::move(nodes);
    // Lineage license extensions: fixed-width scalar slots and two UObject
    // references. Slot names reflect serialized order, not guessed semantics.
    // Native serializer evidence distinguishes these from opaque byte storage.
    Json extension=Json::object();
    if(licensee>=6){
        int slots=2+(licensee>=7?2:0)+(licensee>=11)+(licensee>=13)+
            (licensee>=14?2:0)+(licensee>=15)+(licensee>=37);
        extension={{"word_0",r.u32()},{"reference_0",reference(*this,r.index())},
                   {"reference_1",reference(*this,r.index())},{"words_1_10",words(r,slots)}};
    }
    out["license_fields"]=std::move(extension);
    end=r.u32();n=count(r,60);Json triangles=Json::array();
    for(size_t i=0;i<n;++i){
        Json triangle={{"position_bits",words(r,9)}};
        auto channels=r.i32();require(channels>=0&&channels<=8,"Invalid source triangle UV count");
        Json coordinates=Json::array();for(int j=0;j<channels;++j)coordinates.push_back(words(r,6));
        triangle["uv_bits"]=std::move(coordinates);
        triangle["colors"]=words(r,3);triangle["material_index"]=r.u32();triangle["smoothing_mask"]=r.u32();
        triangles.push_back(std::move(triangle));
    }
    lazyEnd(r,end);out["source_triangles"]=std::move(triangles);
    out["internal_version"]=r.u32();out["trailing_reference"]=reference(*this,r.index());
    if(version>=120)out["trailing_word"]=r.u32();
    Json auxiliary=Json::array(),auxiliaryWords=Json::array();
    if(version>=125){
        n=count(r,8,1000000);
        for(size_t i=0;i<n;++i)auxiliary.push_back(words(r,2));
        auxiliaryWords=words(r,4);
    }
    out["auxiliary_uv_bits"]=std::move(auxiliary);out["auxiliary_words"]=std::move(auxiliaryWords);
    require(r.pos==r.end,"Trailing StaticMesh native bytes");
    out["native_offset"]=nativeStart;out["decoded_native_bytes"]=r.pos-nativeStart;
    out["remaining_offset"]=r.pos;out["remaining_bytes"]=r.end-r.pos;
    out["status"]="decoded";out["reconstruction_supported"]=false;
    return out;
}
}
