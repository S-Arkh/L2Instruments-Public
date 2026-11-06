// Test-only dialect adapter: SDK headers with explicitly enabled client Sort.
// Never rewrites package bytes or relaxes the public decoder's profile checks.
#include "package.h"
#include <iostream>
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected SDK test package path");
        ue::Context ctx(std::filesystem::u8path(argv[1]),{});
        auto& p=*ctx.main;
        if(p.version!=126||p.licensee!=0)throw std::runtime_error("Expected SDK 126/0 test package");
        auto classes=p.summary()["classes"];
        // The fixture's structure layout is shared; opt in only to the proven
        // client instruction grammar for this in-memory test context.
        p.setBytecodeProfile("sdk-client-sort");
        ue::Json functions=ue::Json::object(),sources=ue::Json::object(),scripts=ue::Json::object();
        for(auto cls:classes){
            int id=cls["id"];auto result=ctx.decompile(id,true);
            if(result["status"]!="recovered")throw std::runtime_error(result["issues"].dump());
            auto name=cls["name"].get<std::string>();sources[name]=result["code"];
            scripts[name]=result.value("class_script",ue::Json::array());
            for(auto item:result["functions"]){
                auto f=p.function(p.find(item["name"]));ue::Json nodes=ue::Json::array();
                for(auto& node:f.nodes)nodes.push_back(ue::nodeJson(node));
                functions[item["name"].get<std::string>()]={{"flags",f.flags},{"size",f.size},{"nodes",nodes}};
            }
        }
        std::cout<<ue::Json{{"classes",classes},{"functions",functions},{"sources",sources},{"class_scripts",scripts}}.dump(2);
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
