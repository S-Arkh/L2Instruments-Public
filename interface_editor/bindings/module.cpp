#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "document.hpp"
#include "textures.hpp"
#include "dat.hpp"
namespace py=pybind11;
using namespace interface_editor;
py::object python(const Json& j) {
    if(j.is_null())return py::none();
    if(j.is_boolean())return py::bool_(j.get<bool>());
    if(j.is_number_unsigned())return py::int_(j.get<std::uint64_t>());
    if(j.is_number_integer())return py::int_(j.get<std::int64_t>());
    if(j.is_number_float())return py::float_(j.get<double>());
    if(j.is_string())return py::str(j.get<std::string>());
    if(j.is_array()){py::list v;for(const auto& x:j)v.append(python(x));return std::move(v);}
    py::dict v;for(auto it=j.begin();it!=j.end();++it)v[py::str(it.key())]=python(it.value());return std::move(v);
}
template<class F> py::object result(F&& f){Json j;{py::gil_scoped_release release;j=f();}return python(j);}
py::dict image_result(const TextureImage& image){
    py::dict d;d["width"]=image.width;d["height"]=image.height;d["format"]=image.format;
    d["rgba"]=py::bytes(reinterpret_cast<const char*>(image.rgba.data()),image.rgba.size());
    d["split9"]=image.split;d["grid"]=py::cast(image.grid);return d;
}
PYBIND11_MODULE(_interface_core,m){
    m.doc()="Native interface document, XDAT and texture services";
    m.def("dat_codecs",[]{return python(dat_codecs());});
    m.def("sysstring_schemas",[]{return python(sysstring_schemas());});
    m.def("register_dat_profile",[](py::dict value){auto j=Json::parse(py::module_::import("json").attr("dumps")(value).cast<std::string>());py::gil_scoped_release release;register_dat_profile(j);});
    m.def("decode_dat",[](py::bytes input,const std::string& filename,const std::string& profile){std::string b=input;DatDecoded d;{py::gil_scoped_release release;d=decode_dat(Bytes(b.begin(),b.end()),filename,profile);}
        py::dict result;result["payload"]=py::bytes(reinterpret_cast<const char*>(d.payload.data()),d.payload.size());result["version"]=d.version;result["profile"]=d.profile;result["footer"]=d.footer;
        result["compressed_suffix"]=py::bytes(reinterpret_cast<const char*>(d.compressedSuffix.data()),d.compressedSuffix.size());return result;
    },py::arg("data"),py::arg("filename"),py::arg("profile")="auto");
    m.def("encode_dat",[](py::bytes input,const std::string& filename,int version,const std::string& profile,bool footer){std::string b=input;Bytes out;{py::gil_scoped_release release;out=encode_dat(Bytes(b.begin(),b.end()),filename,version,profile,footer);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());},
        py::arg("data"),py::arg("filename"),py::arg("version"),py::arg("profile")="standard",py::arg("footer")=true);
    py::class_<SysStrings,std::shared_ptr<SysStrings>>(m,"SysStrings")
        .def(py::init<>())
        .def("load",&SysStrings::load,py::arg("file"),py::arg("schema")="id-ascf-v1",py::arg("encoding")="cp1252",py::arg("profile")="auto",py::call_guard<py::gil_scoped_release>())
        .def("load_bytes",[](SysStrings& s,py::bytes input,const std::string& filename,const std::string& schema,const std::string& encoding,const std::string& profile){std::string b=input;py::gil_scoped_release release;s.load_bytes(Bytes(b.begin(),b.end()),filename,schema,encoding,profile);},
             py::arg("data"),py::arg("filename"),py::arg("schema")="id-ascf-v1",py::arg("encoding")="cp1252",py::arg("profile")="auto")
        .def("summary",[](SysStrings& s){return result([&]{return s.summary();});})
        .def("rows",[](SysStrings& s){return result([&]{return s.rows();});})
        .def("snapshot",[](SysStrings& s){return result([&]{return s.snapshot();});})
        .def("lookup",[](SysStrings& s,std::uint32_t id){return result([&]{return s.lookup(id);});})
        .def("next_id",&SysStrings::next_id,py::call_guard<py::gil_scoped_release>())
        .def("add",&SysStrings::add,py::call_guard<py::gil_scoped_release>())
        .def("set",&SysStrings::set,py::call_guard<py::gil_scoped_release>())
        .def("undo",&SysStrings::undo,py::call_guard<py::gil_scoped_release>())
        .def("redo",&SysStrings::redo,py::call_guard<py::gil_scoped_release>())
        .def("payload",[](SysStrings& s){Bytes b;{py::gil_scoped_release release;b=s.payload();}return py::bytes(reinterpret_cast<const char*>(b.data()),b.size());})
        .def("encoded",[](SysStrings& s,const std::string& filename,int version,const std::string& profile){Bytes b;{py::gil_scoped_release release;b=s.encoded(filename,version,profile);}return py::bytes(reinterpret_cast<const char*>(b.data()),b.size());},py::arg("filename"),py::arg("version")=-1,py::arg("profile")="preserve")
        .def("save",&SysStrings::save,py::arg("file"),py::arg("version")=-1,py::arg("profile")="preserve",py::call_guard<py::gil_scoped_release>());
    m.def("build_texture_package",[](const std::string& name,py::list items,py::bytes guid){
        std::vector<TextureAsset> assets;for(auto item:items){auto d=py::cast<py::dict>(item);TextureAsset a;
            a.name=py::cast<std::string>(d["name"]);a.group=py::cast<std::string>(d["group"]);a.width=py::cast<unsigned>(d["width"]);a.height=py::cast<unsigned>(d["height"]);
            a.contentWidth=py::cast<unsigned>(d["content_width"]);a.contentHeight=py::cast<unsigned>(d["content_height"]);auto raw=py::cast<std::string>(d["rgba"]);a.rgba.assign(raw.begin(),raw.end());assets.push_back(std::move(a));}
        std::string id=guid;Bytes output;{py::gil_scoped_release release;output=build_texture_package(name,assets,Bytes(id.begin(),id.end()));}
        return py::bytes(reinterpret_cast<const char*>(output.data()),output.size());
    });
    py::class_<TextureStore>(m,"TextureStore")
        .def(py::init<const std::string&>(),py::call_guard<py::gil_scoped_release>())
        .def("load",[](TextureStore& store,const std::string& name){TextureImage image;{py::gil_scoped_release release;image=store.load(name);}return image_result(image);})
        .def("clear",&TextureStore::clear,py::call_guard<py::gil_scoped_release>())
        .def_property_readonly("package_reads",&TextureStore::package_reads);
    m.def("decode_texture",[](unsigned format,unsigned w,unsigned h,py::bytes data,py::bytes palette,bool masked){
        std::string raw=data,pal=palette;TextureImage image;{py::gil_scoped_release release;image=decode_texture(format,w,h,Bytes(raw.begin(),raw.end()),Bytes(pal.begin(),pal.end()),masked);}return image_result(image);
    },py::arg("format"),py::arg("width"),py::arg("height"),py::arg("data"),py::arg("palette")=py::bytes(),py::arg("masked")=false);
    py::class_<Document,std::shared_ptr<Document>>(m,"Document")
        .def(py::init<const std::string&>())
        .def("create",&Document::create,py::call_guard<py::gil_scoped_release>())
        .def("load",&Document::load,py::call_guard<py::gil_scoped_release>())
        .def("probe",[](Document& d,py::bytes b,const std::string& s){std::string raw=b;Bytes bytes(raw.begin(),raw.end());return result([&]{return d.probe(bytes,s);});})
        .def("load_bytes",[](Document& d,py::bytes b,const std::string& s){std::string raw=b;Bytes bytes(raw.begin(),raw.end());py::gil_scoped_release release;d.load_bytes(bytes,s);})
        .def("serialize",[](Document& d){Bytes b;{py::gil_scoped_release release;b=d.serialize();}return py::bytes(reinterpret_cast<const char*>(b.data()),b.size());})
        .def("save",&Document::save,py::call_guard<py::gil_scoped_release>())
        .def("to_json",&Document::to_json,py::call_guard<py::gil_scoped_release>())
        .def("from_json",&Document::from_json,py::call_guard<py::gil_scoped_release>())
        .def("export_json",&Document::export_json,py::call_guard<py::gil_scoped_release>())
        .def("open_json",&Document::open_json,py::call_guard<py::gil_scoped_release>())
        .def("versions",[](Document& d){return result([&]{return d.versions();});})
        .def("summary",[](Document& d){return result([&]{return d.summary();});})
        .def("children",[](Document& d,std::uint64_t id){return result([&]{return d.children(id);});},py::arg("id")=0)
        .def("info",[](Document& d,std::uint64_t id){return result([&]{return d.info(id);});})
        .def("properties",[](Document& d,std::uint64_t id,bool inactive){return result([&]{return d.properties(id,inactive);});},py::arg("id"),py::arg("include_inactive")=false)
        .def("search",[](Document& d,const std::string& s,bool neighbors){return result([&]{return d.search(s,neighbors);});},py::arg("query"),py::arg("neighbors")=false)
        .def("preview_snapshot",[](Document& d,std::uint64_t id){return result([&]{return d.preview_snapshot(id);});})
        .def("set",[](Document& d,std::uint64_t id,const std::string& field,py::object value){auto text=py::module_::import("json").attr("dumps")(value).cast<std::string>();auto j=Json::parse(text);py::gil_scoped_release release;d.set(id,field,j);})
        .def("set_many",[](Document& d,std::uint64_t id,py::dict values){auto j=Json::parse(py::module_::import("json").attr("dumps")(values).cast<std::string>());py::gil_scoped_release release;d.set_many(id,j);})
        .def("add_configured",[](Document& d,std::uint64_t id,const std::string& type,py::dict values){auto j=Json::parse(py::module_::import("json").attr("dumps")(values).cast<std::string>());py::gil_scoped_release release;return d.add_configured(id,type,j);})
        .def("add",&Document::add,py::call_guard<py::gil_scoped_release>())
        .def("duplicate",&Document::duplicate,py::arg("id"),py::arg("target_list")=0,py::call_guard<py::gil_scoped_release>())
        .def("remove",&Document::remove,py::call_guard<py::gil_scoped_release>())
        .def("allowed_types",[](Document& d,std::uint64_t id){return result([&]{return d.allowed_types(id);});})
        .def("undo",&Document::undo,py::call_guard<py::gil_scoped_release>())
        .def("redo",&Document::redo,py::call_guard<py::gil_scoped_release>());
}
