#include "api.h"
#include "package.h"
#include <cstring>
#include <mutex>
#include <stdexcept>

namespace ue {
namespace {
Json resource(const Package& package,const Json& in){
    auto op=in.at("operation").get<std::string>();
    int id=in.contains("object_id")?in.at("object_id").get<int>():package.find(in.at("object").get<std::string>());
    if(op=="static_mesh")return package.staticMesh(id);
    if(op=="model"||op=="model_collision"||op=="model_level_geometry"||op=="polys"||op=="karma_props")return package.geometry(id,op);
    if(op=="blocking_volume")return package.blockingVolume(id);
    if(op=="material"||op=="texture"||op=="palette"){
        if(op=="palette"&&package.kind(id)!="Palette")throw std::runtime_error("Not a palette export");
        if(op=="texture"&&package.kind(id)!="Texture"&&package.kind(id)!="Cubemap"&&package.kind(id)!="MaskTexture"&&package.kind(id)!="WetTexture")throw std::runtime_error("Not a texture export");
        return package.material(id);
    }
    return package.animatedResource(id,op);
}
}
Json request(const Json& in){
    static std::unique_ptr<Context> context;static std::string key;
    auto op=in.value("operation",std::string("inspect"));
    if(op=="reset"){context.reset();key.clear();return {{"ok",true}};}
    auto path=std::filesystem::u8path(in.at("path").get<std::string>());
    auto profile=in.value("bytecode_profile",std::string("auto"));
    // Structural auditing does not need dependencies or source-code export.
    if(op=="audit"){Package package(path);package.setBytecodeProfile(profile);return {{"ok",true},{"result",package.audit()}};}
    if(op=="metadata"){Package package(path);package.setBytecodeProfile(profile);return {{"ok",true},{"result",package.metadata()}};}
    if(op=="resource_inventory"){Package package(path);return {{"ok",true},{"result",package.resourceInventory()}};}
    if(op=="model"||op=="model_collision"||op=="model_level_geometry"||op=="blocking_volume"||op=="palette"||op=="polys"||op=="karma_props"){Package package(path);return {{"ok",true},{"result",resource(package,in)}};}
    if(op=="resource_batch"){
        const auto& objects=in.at("objects");
        if(!objects.is_array()||objects.empty()||objects.size()>256)throw std::runtime_error("Resource batch requires 1..256 objects");
        Package package(path);Json results=Json::array();
        for(const auto& object:objects)results.push_back(resource(package,object));
        return {{"ok",true},{"result",std::move(results)}};
    }
    if(op=="static_mesh"){Package package(path);int id=in.contains("object_id")?in.at("object_id").get<int>():package.find(in.at("object").get<std::string>());return {{"ok",true},{"result",package.staticMesh(id)}};}
    if(op=="material"){Package package(path);int id=in.contains("object_id")?in.at("object_id").get<int>():package.find(in.at("object").get<std::string>());return {{"ok",true},{"result",package.material(id)}};}
    if(op=="texture"){Package package(path);int id=in.contains("object_id")?in.at("object_id").get<int>():package.find(in.at("object").get<std::string>());
        if(package.kind(id)!="Texture"&&package.kind(id)!="Cubemap"&&package.kind(id)!="MaskTexture"&&package.kind(id)!="WetTexture")throw std::runtime_error("Not a texture export");
        return {{"ok",true},{"result",package.material(id)}};}
    if(op=="skeletal_mesh"||op=="vert_mesh"||op=="mesh_animation"||op=="animation_notify"||op=="sound"||op=="resource_group"){
        Package package(path);int id=in.contains("object_id")?in.at("object_id").get<int>():package.find(in.at("object").get<std::string>());
        return {{"ok",true},{"result",package.animatedResource(id,op)}};
    }
    std::vector<std::filesystem::path> dirs;for(auto& dir:in.value("dependencies",Json::array()))dirs.push_back(std::filesystem::u8path(dir.get<std::string>()));
    auto currentKey=Json::array({path.u8string(),in.value("dependencies",Json::array()),profile}).dump();
    if(in.value("reload",false)||!context||key!=currentKey){auto candidate=std::make_unique<Context>(path,dirs,profile);context=std::move(candidate);key=currentKey;}
    Json out={{"ok",true},{"package",context->main->summary()},{"diagnostics",context->diagnostics}};
    if(op=="inspect")return out;
    if(op=="object"){int id=in.contains("object_id")?in.at("object_id").get<int>():context->main->find(in.at("object").get<std::string>());out["result"]=context->objectDefaults(id);return out;}
    if(op=="decompile"){int id=in.contains("class_id")?in.at("class_id").get<int>():context->main->find(in.at("class").get<std::string>());out["result"]=context->decompile(id,in.value("force_bytecode",false));return out;}
    if(op=="function"){int id=context->main->find(in.at("function").get<std::string>());auto f=context->main->function(id);Json nodes=Json::array();for(auto& n:f.nodes)nodes.push_back(nodeJson(n));out["result"]={{"size",f.size},{"native",f.native},{"flags",f.flags},{"replication_offset",f.replicationOffset},{"nodes",nodes}};return out;}
    throw std::runtime_error("Unknown operation");
}
}
extern "C" int ue_abi_version() noexcept{return 1;}
extern "C" char* ue_request(const char* input) noexcept {
    static std::mutex mutex;try{std::lock_guard<std::mutex> lock(mutex);ue::Json result;
        try{if(!input)throw std::runtime_error("Null request");result=ue::request(ue::Json::parse(input));}
        catch(const std::exception& ex){result={{"ok",false},{"error",ex.what()}};}
        auto text=result.dump(-1,' ',false,ue::Json::error_handler_t::replace);auto memory=new char[text.size()+1];std::memcpy(memory,text.c_str(),text.size()+1);return memory;
    }catch(...){return nullptr;}
}
extern "C" void ue_free(char* output) noexcept {delete[] output;}
