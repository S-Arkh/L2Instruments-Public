#include "api.h"
#include "package.h"
#include <cstring>
#include <mutex>
#include <stdexcept>

namespace ue {
Json request(const Json& in){
    static std::unique_ptr<Context> context;static std::string key;
    auto op=in.value("operation",std::string("inspect"));
    if(op=="reset"){context.reset();key.clear();return {{"ok",true}};}
    auto path=std::filesystem::u8path(in.at("path").get<std::string>());
    // Structural auditing does not need dependencies or source-code export.
    if(op=="audit"){Package package(path);return {{"ok",true},{"result",package.audit()}};}
    std::vector<std::filesystem::path> dirs;for(auto& dir:in.value("dependencies",Json::array()))dirs.push_back(std::filesystem::u8path(dir.get<std::string>()));
    auto currentKey=path.u8string()+in.value("dependencies",Json::array()).dump();
    if(in.value("reload",false)||!context||key!=currentKey){auto candidate=std::make_unique<Context>(path,dirs);context=std::move(candidate);key=currentKey;}
    Json out={{"ok",true},{"package",context->main->summary()},{"diagnostics",context->diagnostics}};
    if(op=="inspect")return out;
    if(op=="decompile"){int id=in.contains("class_id")?in.at("class_id").get<int>():context->main->find(in.at("class").get<std::string>());out["result"]=context->decompile(id,in.value("force_bytecode",false));return out;}
    if(op=="function"){int id=context->main->find(in.at("function").get<std::string>());auto f=context->main->function(id);Json nodes=Json::array();for(auto& n:f.nodes)nodes.push_back(nodeJson(n));out["result"]={{"size",f.size},{"native",f.native},{"flags",f.flags},{"nodes",nodes}};return out;}
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
