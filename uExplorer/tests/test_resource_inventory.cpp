#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>

static void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main(int argc,char** argv){
    try{
        check(argc==2,"Expected fixture path");
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);
        for(auto name:{"StaticMesh","UnknownAsset","ObjectProperty"}){
            ue::Entry e;e.name=name;e.importClass="Class";e.classPackage="Engine";p.imports.push_back(e);
        }
        auto add=[&](const char* name,int cls,int outer,size_t size){
            ue::Entry e;e.name=name;e.cls=cls;e.outer=outer;e.offset=p.data.size();e.size=size;
            p.data.insert(p.data.end(),size,0xff);p.exports.push_back(e);
        };
        add("Owner",0,0,3);add("Shared",-1,0,7);add("Shared",-2,0,11);
        add("Owned",-2,1,5);add("Link",-3,1,9);
        auto result=p.resourceInventory();
        check(result["candidates"].size()==3,"Lost unknown, duplicate-path or owned resource");
        check(result["excluded_script_exports"]==2,"Script metadata classification");
        check(result["types"]["UnknownAsset"]["serial_bytes"]==16,"Wrong byte aggregate");
        check(result["candidates"][2]["outer"]=="Owner","Lost owner identity");
        check(result["imports"][1]["class_package"]=="Engine","Lost typed import");
        check(result["native_bodies_checked"]==false,"Inventory falsely claims body coverage");
        check(!result.contains("file"),"Inventory contains workstation path");
        // Deliberately invalid native payloads must not trigger body decoding.
        check(result["candidates"][0]["serial_bytes"]==7,"Unexpected payload processing");
        std::cout<<"Resource inventory checks passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
