#include "package.h"
#include <cmath>
#include <cstring>
#include <set>
#include <stdexcept>

namespace ue {
namespace {
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}

Json reference(const Package& p,int id){
    return {{"id",id},{"path",p.ref(id)},{"class",id?p.kind(id):"None"}};
}

void floating(Json& out,Reader& r){
    uint32_t bits=r.u32();float value;
    std::memcpy(&value,&bits,sizeof(value));out["bits"]=bits;
    if(std::isfinite(value))out["value"]=value;
    else out["nonfinite"]=true;
}

int subscript(Reader& r){
    uint32_t first=r.byte();
    if(first<128)return int(first);
    if(first<192)return int(((first&63)<<8)|r.byte());
    uint32_t value=(first&63)<<24;
    value|=uint32_t(r.byte())<<16;
    value|=uint32_t(r.byte())<<8;
    value|=r.byte();
    return int(value);
}

bool admitted(const std::string& parent,const std::string& name,int kind,const std::string& shape,int element){
    auto field=lower(name),type=lower(shape);
    int expected=-1;std::string structure;
    if(parent=="actor"){
        if(field=="brush"||field=="level"||field=="physicsvolume")expected=5;
        else if(field=="tag"||field=="group")expected=6;
        else if(field=="locationname")expected=13;
        else if(field=="touching")expected=9;
        else if(field=="drawscale"||field=="rangeforignoredrange")expected=4;
        else if(field=="location"||field=="prepivot"||field=="postpivot"||
                field=="collocation"||field=="drawscale3d"){expected=10;structure="vector";}
        else if(field=="rotation"||field=="swayrotationorig"){expected=10;structure="rotator";}
        else if(field=="mainscale"||field=="postscale"||field=="tempscale"){expected=10;structure="scale";}
        else if(field=="region"){expected=10;structure="pointregion";}
        else if(field=="texmodifyinfo"){expected=10;structure="texturemodifyinfo";}
        else if(field=="bdynamicactorfilterstate"||field=="bsunaffect"||field=="bworldgeometry"||
                field=="bcollideactors"||field=="bblockactors"||field=="bblockplayers"||
                field=="bblockkarma"||field=="bblockzeroextenttraces"||field=="bblocknonzeroextenttraces"||
                field=="bhidden"||field=="bstatic"||field=="bnodelete"||field=="bdeleteme"||
                field=="bpendingdelete"||field=="blightchanged"||field=="bselected"||
                field=="bhiddened"||field=="bacceptsprojectors"||field=="blocklocationgroup"||
                field=="bhiddenedgroup"||field=="bforcesunlight"||field=="bignoredrange"||
                field=="bautoaligntoterrain")expected=3;
    }else if(parent=="scale"){
        if(field=="scale"){expected=10;structure="vector";}
        else if(field=="sheerrate")expected=4;
        else if(field=="sheeraxis")expected=1;
    }else if(parent=="pointregion"){
        if(field=="zone")expected=5;
        else if(field=="ileaf")expected=2;
        else if(field=="zonenumber")expected=1;
    }else if(parent=="texturemodifyinfo"){
        if(field=="busemodify"||field=="btwoside"||field=="balphablend"||field=="bdummy")expected=3;
        else if(field=="color"){expected=10;structure="color";}
        else if(field=="alphaop"||field=="colorop")expected=2;
    }
    if(expected<0)return false;
    require(kind==expected&&element<0&&(structure.empty()||type==structure),
            "Invalid BlockingVolume property type");
    return true;
}

Json tags(const Package& p,Reader& r,const std::string& scope,const std::string& parent,int depth,Json& unsupported){
    require(depth<=8,"BlockingVolume property nesting exceeds limits");
    Json result=Json::array();std::set<std::pair<std::string,int>> seen;
    for(size_t n=0;;++n){
        require(n<10000,"Too many BlockingVolume property tags");
        auto name=p.name(r.index());if(lower(name)=="none")break;
        auto info=r.byte();int kind=info&15,code=(info>>4)&7;
        auto shape=kind==10?p.name(r.index()):std::string();
        const int sizes[]={1,2,4,12,16};
        int size=code<5?sizes[code]:code==5?r.byte():code==6?r.u16():r.i32();
        require(size>=0,"Negative BlockingVolume property size");
        int element=-1;if(kind!=3&&(info&128))element=subscript(r);
        require(seen.insert({lower(name),element}).second,"Duplicate BlockingVolume property");
        Json tag={{"name",name},{"kind",kind},{"declared_size",size}};
        if(!shape.empty())tag["structure"]=shape;
        if(element>=0)tag["subscript"]=element;
        bool qualified=admitted(parent,name,kind,shape,element);
        if(!qualified)unsupported.push_back({{"path",scope+"."+name},{"kind",kind},
                                             {"structure",shape},{"size",size}});
        if(kind==3){
            if(qualified)tag["value"]=bool(info&128);else tag["status"]="uninterpreted";
            result.push_back(std::move(tag));continue;
        }
        r.require(size_t(size));Reader value(r.data,r.pos,size_t(size));r.skip(size_t(size));
        if(!qualified){tag["status"]="uninterpreted";result.push_back(std::move(tag));continue;}
        bool supported=true;
        if(kind==1){require(size==1,"Invalid BlockingVolume byte property");tag["value"]=value.byte();}
        else if(kind==2){require(size==4,"Invalid BlockingVolume integer property");tag["value"]=value.i32();}
        else if(kind==4){require(size==4,"Invalid BlockingVolume float property");floating(tag,value);}
        else if(kind==5){int id=value.index();tag["value"]=reference(p,id);}
        else if(kind==6)tag["value"]=p.name(value.index());
        else if(kind==13)tag["value"]=value.string();
        else if(kind==9&&lower(name)=="touching"){
            int count=value.index();
            require(count>=0&&count<=4096&&size_t(count)<=value.end-value.pos,
                    "Invalid BlockingVolume Touching count");
            Json objects=Json::array();
            for(int i=0;i<count;++i)objects.push_back(reference(p,value.index()));
            tag["value"]=std::move(objects);
        }else if(kind==10){
            auto type=lower(shape);
            if(type=="vector"){
                require(size==12,"Invalid BlockingVolume vector");
                Json bits=Json::array(),values=Json::array();bool finite=true;
                for(int i=0;i<3;++i){
                    uint32_t word=value.u32();float f;std::memcpy(&f,&word,sizeof(f));bits.push_back(word);
                    if(std::isfinite(f))values.push_back(f);else finite=false;
                }
                tag["bits"]=std::move(bits);
                if(finite)tag["value"]=std::move(values);else tag["nonfinite"]=true;
            }else if(type=="rotator"){
                require(size==12,"Invalid BlockingVolume rotator");
                tag["value"]=Json::array({value.i32(),value.i32(),value.i32()});
            }else if(type=="color"){
                require(size==4,"Invalid BlockingVolume color");
                tag["bytes"]=Json::array({value.byte(),value.byte(),value.byte(),value.byte()});
            }else if(type=="scale"||type=="pointregion"||type=="texturemodifyinfo"){
                tag["fields"]=tags(p,value,scope+"."+name,type,depth+1,unsupported);
            }else supported=false;
        }else supported=false;
        if(supported)require(value.pos==value.end,"Trailing BlockingVolume property bytes");
        else{
            unsupported.push_back({{"path",scope+"."+name},{"kind",kind},
                                   {"structure",shape},{"size",size}});
            tag["status"]="uninterpreted";
        }
        result.push_back(std::move(tag));
    }
    return result;
}
}

Json Package::blockingVolume(int id) const {
    const auto& e=entry(id);
    require(id>0&&version==133&&licensee==40&&kind(id)=="BlockingVolume"&&
            lower(ref(e.cls))=="engine.blockingvolume","Unsupported BlockingVolume class/profile");
    require(!e.super&&(e.flags&0x02000000),"Unsupported BlockingVolume object header");
    require(e.size<=64*1024*1024,"BlockingVolume exceeds preview limits");
    Reader r(data,e.offset,e.size);
    int node=r.index(),state=r.index();auto probe=r.u64();auto word=r.u32();
    require(node==e.cls&&state==e.cls&&probe==0xffffffffffffffffULL,
            "Unsupported BlockingVolume saved state frame");
    int codeOffset=r.index();
    require(codeOffset==-1,"Unsupported BlockingVolume saved code offset");
    Json unsupported=Json::array();
    auto properties=tags(*this,r,ref(id),"actor",0,unsupported);
    require(r.pos==r.end,"Trailing BlockingVolume native bytes");
    int brush=0;bool found=false;
    for(const auto& tag:properties)if(lower(tag["name"].get<std::string>())=="brush"){
        require(!found&&!tag.contains("subscript")&&tag["kind"]==5,"Invalid BlockingVolume Brush");
        brush=tag["value"]["id"].get<int>();found=true;
    }
    require(found&&brush>0&&kind(brush)=="Model","BlockingVolume Brush is not a local Model");
    return {{"schema",1},{"path",ref(id)},{"class",ref(e.cls)},
            {"status",unsupported.empty()?"saved_properties_decoded":"partial"},
            {"frame",{{"node",reference(*this,node)},{"state_node",reference(*this,state)},
                      {"probe_mask","ffffffffffffffff"},{"unknown_word",word},{"code_offset",codeOffset}}},
            {"properties",properties},{"uninterpreted_properties",unsupported},
            {"brush",reference(*this,brush)},{"serialized_bytes",e.size},
            {"inherited_defaults_resolved",false},{"world_transform_applied",false},
            {"runtime_collision_verified",false},{"reconstruction_supported",false},
            {"scope","saved frame and properties only; no execution or inherited defaults"}};
}
}
