#include "package.h"
#include <set>
#include <stdexcept>

namespace ue {
namespace {
void check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int size(Reader& r,int info){
    const int fixed[]={1,2,4,12,16};int code=(info>>4)&7;
    int n=code<5?fixed[code]:code==5?r.byte():code==6?r.u16():r.i32();
    check(n>=0,"Negative material property size");return n;
}
int count(Reader& r){int n=r.index();check(n>=0&&n<=1024,"Excessive material array");return n;}
Json words(Reader& r,int n){Json a=Json::array();for(int i=0;i<n;++i)a.push_back(r.u32());return a;}
Json bytes(Reader& r,int n){Json a=Json::array();for(int i=0;i<n;++i)a.push_back(r.byte());return a;}
Json matrix(const Package& p,Reader& r,bool plane=false){
    Json fields=Json::array();std::set<std::string> seen;
    for(;;){
        auto name=p.name(r.index()),key=lower(name);if(key=="none")break;
        bool known=plane?(key=="x"||key=="y"||key=="z"||key=="w"):
                         (key=="xplane"||key=="yplane"||key=="zplane"||key=="wplane");
        check(known&&seen.insert(key).second,"Invalid material matrix member");
        int info=r.byte();check(!(info&128),"Indexed material matrix member");
        check((info&15)==(plane?4:10),"Invalid material matrix member type");
        if(!plane)check(lower(p.name(r.index()))=="plane","Invalid material plane structure");
        auto n=size(r,info);r.require(n);Reader v(r.data,r.pos,size_t(n));r.skip(n);
        Json field={{"name",name}};
        if(plane){check(n==4,"Invalid material plane float width");field["bits"]=v.u32();}
        else field["members"]=matrix(p,v,true);
        check(v.pos==v.end,"Trailing material matrix member bytes");fields.push_back(std::move(field));
    }
    return fields;
}
Json tags(const Package& p,Reader& r,bool sequence=false,bool mask=false,bool wet=false){
    Json fields=Json::array();
    for(;;){
        auto name=p.name(r.index());if(lower(name)=="none")break;
        check(fields.size()<10000,"Excessive material properties");
        int info=r.byte(),kind=info&15;std::string structure;
        if(kind==10)structure=p.name(r.index());
        int n=size(r,info);Json tag={{"name",name},{"kind",kind}};
        if(kind==3){tag["value"]=bool(info&128);tag["declared_size"]=n;fields.push_back(tag);continue;}
        if(info&128){
            int b=r.byte(),index=b;
            if(b>=192){index=(b&63)<<24;index|=int(r.byte())<<16;index|=int(r.byte())<<8;index|=r.byte();}
            else if(b>=128)index=((b&63)<<8)|r.byte();
            tag["subscript"]=index;
        }
        r.require(n);Reader v(r.data,r.pos,size_t(n));r.skip(n);
        if(kind==1)tag["value"]=v.byte();
        else if(kind==2)tag["value"]=v.i32();
        else if(kind==4)tag["bits"]=v.u32();
        else if(kind==5){int id=v.index();tag["value"]={{"id",id},{"path",p.ref(id)},{"class",id?p.kind(id):"None"}};}
        else if(kind==6)tag["value"]=p.name(v.index());
        else if(kind==13)tag["value"]=v.string();
        else if(kind==9&&mask&&lower(name)=="rledata"){
            int n=v.index();check(n>=0&&n<=1000000,"Invalid mask RLE count");
            tag["words"]=words(v,n);
        }
        else if(kind==9&&sequence&&lower(name)=="sequenceitems"){
            int total=v.index();check(total>=0&&total<=65536,"Invalid material sequence count");
            Json items=Json::array();
            for(int i=0;i<total;++i){
                auto fields=tags(p,v);check(fields.size()<=64,"Excessive sequence fields");
                for(const auto& field:fields){
                    auto name=lower(field["name"].get<std::string>());int type=field["kind"];
                    check(!field.contains("subscript")&&((name=="material"&&type==5)||(name=="time"&&type==4)||
                          (name=="action"&&type==1)),"Unsupported sequence field");
                }
                items.push_back(std::move(fields));
            }
            tag["elements"]=std::move(items);
        }
        else if(kind==10){
            tag["structure"]=structure;
            if(lower(structure)=="color")tag["bytes"]=bytes(v,4);
            else if(lower(structure)=="rotator")tag["words"]=words(v,3);
            else if(lower(structure)=="matrix")tag["members"]=matrix(p,v);
            else if(wet&&lower(structure)=="adrop"){
                check(lower(name)=="drops"&&tag.value("subscript",0)<256,"Invalid water drop selector");
                auto fields=tags(p,v);std::set<std::string> seen;
                const std::set<std::string> allowed={"type","depth","x","y","bytea","byteb","bytec","byted"};
                for(const auto& field:fields){
                    auto name=lower(field["name"].get<std::string>());
                    check(allowed.count(name)&&seen.insert(name).second&&field["kind"]==1&&!field.contains("subscript"),
                          "Unsupported water drop field");
                }
                tag["members"]=std::move(fields);
            }
            else throw std::runtime_error("Unsupported material structure: "+structure);
        }else throw std::runtime_error("Unsupported material property: "+name);
        check(v.pos==v.end,"Trailing material property bytes");fields.push_back(std::move(tag));
    }
    return fields;
}
}
Json Package::material(int id) const {
    bool early=version==123&&(licensee==12||licensee==19||licensee==23);
    bool legacy=version==123&&licensee>=33&&licensee<=36;
    check((version>=130&&version<=133&&licensee==40)||
          (version==123&&(licensee==37||licensee==38))||
          (version==125&&(licensee==38||licensee==39))||
          (version>=126&&version<=129&&licensee==39)||early||legacy,"Unsupported material profile");
    static const std::set<std::string> classes={"Shader","FinalBlend","Combiner","TexCoordSource",
        "TexPanner","FadeColor","TexOscillator","TexEnvMap","VertexColor","TexRotator",
        "ColorModifier","TexPannerTriggered","TexScaler","ConstantColor","Texture","Cubemap",
        "TexOscillatorTriggered","TexPlanningPanner","FresnelMaterial","MaterialSequence","L2ColorModifier","MaskTexture","WetTexture","Palette"};
    check(id>0&&size_t(id)<=exports.size(),"Expected material export ID");
    check(!(entry(id).flags&0x02000000),"Stacked material unsupported");
    check(classes.count(kind(id))!=0,"Not a supported material export");
    check(!early||kind(id)=="Texture"||(kind(id)=="Palette"&&licensee==12)||
          (kind(id)=="Shader"&&licensee==23),"Unsupported early material class");
    check(!legacy||kind(id)=="Texture"||kind(id)=="Shader"||kind(id)=="Palette"||
          (licensee==35&&kind(id)=="TexEnvMap"),
           "Unsupported legacy material class");
    check(kind(id)!="MaskTexture"||(version==133&&licensee==40),"Unsupported MaskTexture profile");
    check(kind(id)!="WetTexture"||(version==127&&licensee==39),"Unsupported WetTexture profile");
    auto r=reader(id);Json out={{"schema",1},{"path",ref(id)},{"class",kind(id)},
        {"tags",tags(*this,r,kind(id)=="MaterialSequence",kind(id)=="MaskTexture",kind(id)=="WetTexture")}};
    auto start=r.pos;
    if(kind(id)=="Palette"){
        check(count(r)==256,"Palette requires 256 colors");Json colors=Json::array();
        for(int i=0;i<256;++i)colors.push_back(bytes(r,4));
        check(r.pos==r.end,"Trailing palette native bytes");
        out["colors"]=std::move(colors);out["native_offset"]=start;
        out["decoded_native_bytes"]=r.pos-start;out["remaining_bytes"]=0;
        out["status"]="decoded";out["reconstruction_supported"]=false;return out;
    }
    if(early){
        if(licensee>=16)out["obsolete_material_word"]=r.u32();
    }else if(legacy){
        out["obsolete_material_word"]=r.u32();
        Json old;old["licensee"]=licensee;
        if(licensee<36)old["flag"]=r.byte();
        old["header"]=bytes(r,18);
        Json records=Json::array();
        for(int i=0;i<8;++i){
            Json record;record["first"]=r.byte();
            if(licensee<36)record["second"]=r.byte();
            record["fields"]=bytes(r,126);
            records.push_back(std::move(record));
        }
        old["stages"]=std::move(records);
        out["colors"]=bytes(r,8);out["words"]=words(r,3);
        Json names=Json::array();
        for(int i=0;i<16;++i)names.push_back(r.string());
        old["strings"]=std::move(names);out["legacy_material"]=std::move(old);
        out["shader"]=r.string();out["material_version"]=r.u32();
    }else{
    out["material_header"]=bytes(r,2);Json stages=Json::array();
    for(int i=0;i<(version<129?1:5);++i){
        Json stage;stage["bytes"]=bytes(r,version<130?2:6);stage["words"]=words(r,version<130?3:2);stages.push_back(std::move(stage));
    }
    out["stages"]=std::move(stages);out["colors"]=bytes(r,8);out["words"]=words(r,3);
    Json strings=Json::array();int n=count(r);
    for(int i=0;i<n;++i){
        auto name=r.string();int m=count(r);Json values=Json::array();
        for(int j=0;j<m;++j)values.push_back(r.string());
        strings.push_back({{"name",name},{"values",std::move(values)}});
    }
    out["strings"]=std::move(strings);out["shader"]=r.string();out["material_version"]=r.u32();
    }
    if(kind(id)=="Texture"||kind(id)=="Cubemap"||kind(id)=="MaskTexture"||kind(id)=="WetTexture"){
        bool parametric=false;
        for(const auto& tag:out["tags"])if(lower(tag["name"].get<std::string>())=="bparametric"&&tag["kind"]==3)
            parametric=parametric||tag["value"].get<bool>();
        int format=0;for(const auto& tag:out["tags"])if(lower(tag["name"].get<std::string>())=="format"){
            check(tag["kind"]==1,"Invalid texture Format property");format=tag["value"].get<int>();
        }
        int levels=count(r);check(levels<=32,"Excessive texture mips");Json mips=Json::array();
        for(int i=0;i<levels;++i){
            auto end=r.u32();int length=r.index();check(length>=0,"Negative mip length");r.require(size_t(length));
            auto at=r.pos;r.skip(size_t(length));check(!end||end==r.pos,"Invalid texture lazy boundary");
            auto w=r.u32(),h=r.u32();auto ub=r.byte(),vb=r.byte();
            check(w&&h&&w<=16384&&h<=16384&&ub<=14&&vb<=14,"Invalid mip dimensions");
            size_t expected=0,area=size_t(w)*h;
            if(format==0)expected=area;else if(format==5)expected=area*4;else if(format==10)expected=area*2;
            else if(format==3||format==7||format==8)expected=size_t((w+3)/4)*((h+3)/4)*(format==3?8:16);
            else throw std::runtime_error("Unsupported texture format");
            bool empty=((version==133&&(format==7||format==5))||(version==132&&format==5))&&
                i>0&&i+1==levels&&w==1&&h==1&&ub==0&&vb==0&&length==0;
            bool procedural=kind(id)=="WetTexture"&&parametric&&format==0&&levels==1&&length==0&&
                ((w==128&&ub==7)||(w==256&&ub==8))&&h==w&&vb==ub;
            check(size_t(length)==expected||empty||procedural,"Invalid mip storage size");
            mips.push_back({{"width",w},{"height",h},{"ubits",ub},{"vbits",vb},{"data_hex",hex(Bytes(r.data.begin()+at,r.data.begin()+at+length))}});
        }
        out["mips"]=std::move(mips);
    }
    check(r.pos==r.end,"Trailing material native bytes");
    out["native_offset"]=start;out["decoded_native_bytes"]=r.pos-start;out["remaining_bytes"]=0;
    out["status"]="decoded";out["reconstruction_supported"]=false;return out;
}
}
