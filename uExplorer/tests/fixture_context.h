#pragma once
#include "package.h"
#include <stdexcept>

// Synthetic in-memory fixtures use one-byte references. Supply the UField
// links that real serialized class/struct/state exports require. Function
// parameter chains remain explicit so their own negative tests stay intact.
struct FixtureContext : ue::Context {
    using ue::Context::Context;
    ue::Json decompile(int id,bool force) {
        auto& p=*main;
        if(p.exports.size()>=64)throw std::runtime_error("Fixture needs multi-byte references");
        for(std::size_t i=0;i<p.exports.size();++i){
            auto kind=p.kind(int(i)+1);
            if(kind!="Class"&&kind!="Struct"&&kind!="State")continue;
            std::vector<int> fields;
            for(int child:p.members(int(i)+1)){
                auto k=p.kind(child);
                if(k=="Function"||k=="State"||k=="Struct"||k=="Enum"||k=="Const"||
                   (k.size()>=8&&k.substr(k.size()-8)=="Property"))fields.push_back(child);
            }
            p.data.at(p.exports[i].offset+(kind=="Class"?3:4))=fields.empty()?0:uint8_t(fields.front());
            for(std::size_t j=0;j<fields.size();++j)
                p.data.at(p.entry(fields[j]).offset+2)=j+1<fields.size()?uint8_t(fields[j+1]):0;
        }
        return ue::Context::decompile(id,force);
    }
};
