#include "package.h"
#include <stdexcept>

namespace ue {
namespace {
void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
struct NativeReader {
    const Package& p; Reader& r;
    size_t count(size_t stride=1,size_t maximum=1000000){
        int n=r.index();require(n>=0&&size_t(n)<=maximum,"Invalid native array count");
        require(size_t(n)<=(r.end-r.pos)/stride,"Truncated native array");return size_t(n);
    }
    Json words(size_t n){r.require(n*4);Json a=Json::array();while(n--)a.push_back(r.u32());return a;}
    Json shorts(size_t n){r.require(n*2);Json a=Json::array();while(n--)a.push_back(r.u16());return a;}
    Json bytes(size_t n){r.require(n);Json a=Json::array();while(n--)a.push_back(r.byte());return a;}
    template<class F> Json array(size_t stride,F f){auto n=count(stride);Json a=Json::array();while(n--)a.push_back(f());return a;}
    Json vectors(size_t n){return array(n*4,[&]{return words(n);});}
    Json integers(){return array(4,[&]{return r.u32();});}
    Json indices(){return array(2,[&]{return r.u16();});}
    std::string name(){return p.name(r.index());}
    Json reference(){int id=r.index();return {{"id",id},{"path",p.ref(id)},{"class",id?p.kind(id):"None"}};}
    template<class F> Json lazy(size_t stride,F f){
        auto end=r.u32();auto a=array(stride,f);require(end==r.pos,"Invalid native lazy boundary");return a;
    }
    Json box(){Json b={{"coordinate_bits",words(6)}};b["valid"]=r.byte();return b;}
    Json properties(const std::string& kind){
        Json out=Json::array();
        for(;;){
            auto label=name();if(lower(label)=="none")break;
            require(out.size()<10000,"Excessive native properties");
            auto info=r.byte();int type=info&15,code=(info>>4)&7;
            Json t={{"name",label},{"kind",type}};
            std::string structure;if(type==10){structure=name();t["structure"]=structure;}
            const int sizes[]={1,2,4,12,16};
            int size=code<5?sizes[code]:code==5?r.byte():code==6?r.u16():r.i32();
            require(size>=0,"Negative native property size");
            if(type==3){t["value"]=bool(info&128);t["declared_size"]=size;out.push_back(t);continue;}
            if(info&128){
                int b=r.byte(),index=b;
                if(b>=192){index=(b&63)<<24;index|=int(r.byte())<<16;index|=int(r.byte())<<8;index|=r.byte();}
                else if(b>=128)index=((b&63)<<8)|r.byte();
                t["subscript"]=index;
            }
            r.require(size_t(size));Reader v(r.data,r.pos,size_t(size));r.skip(size_t(size));NativeReader n{p,v};
            switch(type){
            case 1:t["value"]=v.byte();break;
            case 2:t["value"]=v.i32();break;
            case 4:t["bits"]=v.u32();break;
            case 5:t["value"]=n.reference();break;
            case 6:t["value"]=n.name();break;
            case 13:t["value"]=v.string();break;
            case 9:
                if(kind=="AnimNotify_PawnStatusVoice"&&lower(label)=="soundname"){
                    t["value"]=n.array(1,[&]{return v.string();});break;
                }
                require((kind=="VertMesh"&&lower(label)=="materials")||
                        (kind=="AnimNotify_RandomSound"&&lower(label)=="sounds"),"Unsupported native property array");
                t["value"]=n.array(1,[&]{return n.reference();});break;
            case 10:
                if(lower(structure)=="vector"||lower(structure)=="rotator")t["words"]=n.words(3);
                else if(lower(structure)=="color")t["bytes"]=n.bytes(4);
                else throw std::runtime_error("Unsupported native property structure");
                break;
            default:throw std::runtime_error("Unsupported native property kind");
            }
            require(v.pos==v.end,"Trailing native property bytes");out.push_back(std::move(t));
        }
        return out;
    }
    Json wedge(){return {{"vertex",r.u16()},{"uv_bits",words(2)}};}
    Json influence(){return {{"weight_bits",r.u32()},{"point",r.u16()},{"bone",r.u16()}};}
    Json lodPrefix(){
        Json d={{"bounds",box()},{"sphere_bits",words(4)}};
        auto version=r.u32();require(version>=5&&version<=7,"Unsupported LodMesh version");
        d["version"]=version;d["vertex_count"]=r.u32();
        if(p.version>=133)d["vertices_bits"]=vectors(3);else d["packed_original_vertices"]=integers();
        d["textures"]=array(1,[&]{return reference();});d["transforms"]=words(9);
        d["face_levels"]=indices();d["faces"]=array(8,[&]{return shorts(4);});d["collapse_wedges"]=indices();
        d["wedges"]=array(10,[&]{return wedge();});d["materials"]=vectors(2);d["lod_fields"]=words(6);
        d["has_impostor"]=r.u32();d["sprite_material"]=reference();d["impostor_transforms"]=words(9);
        d["impostor_color"]=bytes(4);d["impostor_modes"]=words(3);d["skin_tessellation"]=r.u32();
        d["extension_word"]=r.u32();d["extension_bytes"]=bytes(version-5);return d;
    }
    Json section(){return {{"fields",shorts(9)},{"bones",integers()}};}
    Json indexBuffer(){return {{"indices",indices()},{"revision",r.u32()}};}
    Json lod(){
        Json d={{"skinning",integers()},{"skin_points_bits",vectors(4)},{"soft_wedges",r.u32()}};
        d["soft_sections"]=array(19,[&]{return section();});d["rigid_sections"]=array(19,[&]{return section();});
        d["soft_indices"]=indexBuffer();d["rigid_indices"]=indexBuffer();
        d["vertex_header"]=words(3);d["vertices_bits"]=vectors(8);
        d["influences"]=lazy(8,[&]{return influence();});d["wedges"]=lazy(10,[&]{return wedge();});
        d["faces"]=lazy(8,[&]{return shorts(4);});d["points_bits"]=lazy(12,[&]{return words(3);});
        d["fields"]=words(6);d["new_wedges"]=r.u32();
        d["lineage_wedges"]=array(52,[&]{return Json{{"vectors_bits",words(8)},{"bones",bytes(4)},{"weights_bits",words(4)}};});
        return d;
    }
    Json skeletal(){
        auto d=lodPrefix();d["points2_bits"]=vectors(3);
        d["bones"]=array(57,[&]{return Json{{"name",name()},{"flags",r.u32()},{"pose_bits",words(11)},{"children",r.u32()},{"parent",r.u32()}};});
        d["animation"]=reference();d["depth"]=r.u32();
        d["weight_indices"]=array(5,[&]{return Json{{"indices",indices()},{"start",r.u32()}};});
        d["bone_influences"]=array(4,[&]{return shorts(2);});
        d["attach_aliases"]=array(1,[&]{return name();});d["attach_bones"]=array(1,[&]{return name();});
        d["attach_coordinates_bits"]=vectors(12);d["lods"]=array(1,[&]{return lod();});
        d["auxiliary_object"]=reference();d["points_bits"]=lazy(12,[&]{return words(3);});
        d["mesh_wedges"]=lazy(10,[&]{return wedge();});
        d["triangles"]=lazy(12,[&]{return Json{{"wedges",shorts(3)},{"material",r.byte()},{"auxiliary_material",r.byte()},{"smoothing",r.u32()}};});
        d["influences"]=lazy(8,[&]{return influence();});d["collapse"]=lazy(2,[&]{return r.u16();});
        d["face_remap"]=lazy(2,[&]{return r.u16();});d["tail_first"]=r.u32();
        d["tail_float_bits"]=integers();d["tail_words"]=words(2);return d;
    }
    Json sequences(){
        return array(1,[&]{
            Json s={{"scalar_bits",r.u32()},{"name",name()},{"groups",array(1,[&]{return name();})}};
            s["start"]=r.u32();s["frames"]=r.u32();
            s["events"]=array(p.version>=131?10:6,[&]{
                Json e={{"time_bits",r.u32()},{"function",name()},{"object",reference()}};
                auto n=p.version>=131?r.u32():0;require(n<=1000000&&n<=(r.end-r.pos)/2,"Invalid event UTF-16 length");
                e["text_utf16"]=shorts(n);return e;
            });
            s["rate_bits"]=r.u32();s["prefix"]=words(3);s["object"]=reference();s["suffix"]=words(2);
            s["flag"]=r.byte();s["pairs"]=vectors(2);
            s["nested"]=array(5,[&]{return Json{{"word",r.u32()},{"pairs",vectors(2)}};});
            s["final"]=words(2);s["last"]=vectors(2);return s;
        });
    }
    Json track(){return {{"flags",r.u32()},{"rotation_bits",vectors(4)},{"position_bits",vectors(3)},{"time_bits",integers()}};}
    Json animation(){
        auto version=r.u32();require(version==1,"Unsupported MeshAnimation version");Json d={{"version",version}};
        d["bones"]=array(9,[&]{return Json{{"name",name()},{"flags",r.u32()},{"parent",r.u32()}};});
        d["moves"]=lazy(35,[&]{
            auto end=r.u32();Json m={{"header",words(6)},{"bone_indices",integers()}};
            m["tracks"]=array(7,[&]{return track();});m["root"]=track();
            require(end==r.pos,"Invalid animation move boundary");return m;
        });
        d["sequences"]=sequences();return d;
    }
    Json vert(){
        auto d=lodPrefix();d["animated_vertices_bits"]=vectors(8);d["stream_version"]=r.u32();
        d["packed_vertices"]=integers();d["float_bits"]=integers();d["sequences"]=sequences();
        d["packed_normals"]=integers();d["animated_vertex_count"]=r.u32();d["frame_count"]=r.u32();
        d["boxes"]=array(25,[&]{return box();});d["sphere_bits_per_frame"]=vectors(4);return d;
    }
    Json sound(){
        Json d={{"format",name()}};require(lower(d["format"].get<std::string>())=="wav","Unsupported Sound format");
        auto end=r.u32();auto n=count(1,512*1024*1024);auto start=r.pos;r.skip(n);
        require(end==r.pos,"Invalid Sound lazy boundary");
        d["audio_size"]=n;d["audio_hex"]=hex(Bytes(r.data.begin()+start,r.data.begin()+r.pos));return d;
    }
};
bool notify(const std::string& kind){
    static const std::set<std::string> kinds={"AnimNotify_CameraLocation","AnimNotify_Sound","AnimNotify_RandomSound",
        "AnimNotify_AttackShot","AnimNotify_Illusion","AnimNotify_BoneScaleScript","AnimNotify_Effect",
        "AnimNotify_SwimSound","AnimNotify_Channeling","AnimNotify_PlayCustomAnimation",
        "AnimNotify_AttackPreShot","AnimNotify_DestroyEffect","AnimNotify_AttackItem","AnimNotify_ViewShake",
        "AnimNotify_Light","AnimNotify_BoneScale","AnimNotify_AttackVoice","AnimNotify_JumpSound",
        "AnimNotify_LaunchAccumulativeBeam","AnimNotify_ModifyVisBound","AnimNotify_JumpDown","AnimNotify_JumpUp",
        "AnimNotify_PawnStatusVoice","AnimNotify_EventAnimEnd","AnimNotify_BoneDirect","AnimNotify_Ribbon",
        "AnimNotify_HideWeapon","AnimNotify_PendingPawnEffectState","AnimNotify_SkillEffect","AnimNotify_HidePawn",
        "AnimNotify_ScreenFade","AnimNotify_IdleSound"};
    return kinds.count(kind)!=0;
}
}
Json Package::animatedResource(int id,const std::string& operation) const {
    bool profile=version==133&&licensee==40;
    if(operation=="resource_group")profile=true;
    if(operation=="sound"||operation=="resource_group")
        profile=profile||((version==130||version==131)&&licensee==40)||(version==128&&licensee==39)||(version==123&&licensee==23);
    if(operation=="skeletal_mesh")profile=profile||((version==131||version==132)&&licensee==40)||(version==123&&licensee==36);
    if(operation=="mesh_animation")profile=profile||(version==131&&licensee==40)||(version==123&&licensee==36);
    if(operation=="animation_notify")profile=profile||(version==131&&licensee==40);
    if(operation=="vert_mesh")profile=profile||(version==123&&licensee==37);
    require(profile,"Unsupported animated resource profile");
    require(id>0&&size_t(id)<=exports.size(),"Expected resource export ID");auto type=kind(id);
    require((operation=="skeletal_mesh"&&type=="SkeletalMesh")||(operation=="vert_mesh"&&type=="VertMesh")||
            (operation=="mesh_animation"&&type=="MeshAnimation")||(operation=="animation_notify"&&notify(type))||
            (operation=="sound"&&type=="Sound")||(operation=="resource_group"&&type=="Package"),"Resource class does not match operation");
    require(!(entry(id).flags&0x02000000),"Stacked native resource unsupported");
    auto r=reader(id);NativeReader n{*this,r};Json out={{"schema",1},{"path",ref(id)},{"class",type},{"tags",n.properties(type)}};
    auto start=r.pos;Json body=Json::object();
    if(type=="Package")require(out["tags"].empty(),"Nonempty resource group properties");
    if(type=="SkeletalMesh")body=n.skeletal();else if(type=="VertMesh")body=n.vert();
    else if(type=="MeshAnimation")body=n.animation();else if(type=="Sound")body=n.sound();
    require(r.pos==r.end,"Trailing native resource bytes");out["body"]=std::move(body);
    out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;out["remaining_bytes"]=0;
    out["status"]="decoded";out["reconstruction_supported"]=false;return out;
}
}
