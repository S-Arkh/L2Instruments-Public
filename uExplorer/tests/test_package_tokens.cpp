#include "package.h"
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

static void check(bool value) { if(!value) throw std::runtime_error("check failed"); }
template<class F> static void rejects(F f) {
    bool failed=false;try { f(); } catch(const std::exception&) { failed=true; }
    check(failed);
}
int main(int argc,char** argv) {
    try {
        if(argc!=2)throw std::runtime_error("Expected temporary fixture path");
        // Empty table fixture: no client data required.
        ue::Bytes header(36,0);header[0]=0xc1;header[1]=0x83;header[2]=0x2a;header[3]=0x9e;
        header[4]=133;header[6]=40;
        {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
        ue::Package p(argv[1]);check(p.version==133&&p.licensee==40);
        for(int64_t value:{int64_t(0),int64_t(-1),std::numeric_limits<int64_t>::min(),std::numeric_limits<int64_t>::max()}) {
            ue::Bytes bytes{0x46};auto bits=uint64_t(value);
            for(int i=0;i<8;++i)bytes.push_back(uint8_t(bits>>(8*i)));
            bytes.push_back(0x25);ue::Reader r(bytes);ue::Decoder d{p,r};auto nodes=d.script(10);
            check(nodes.size()==2&&nodes[0].value.get<int64_t>()==value);
            check(nodes[0].finish==9&&nodes[1].pc==9&&r.pos==bytes.size());
        }
        ue::Bytes sort{0x47,1,0,1,0,0x25};ue::Reader r(sort);ue::Decoder d{p,r};auto nodes=d.script(12);
        check(nodes.size()==2&&nodes[0].kind=="array_sort"&&nodes[0].children.size()==2);
        check(nodes[0].finish==11&&nodes[1].pc==11&&r.pos==sort.size());
        for(auto bytes:{ue::Bytes{0x46,0,0},ue::Bytes{0x47,1,0},ue::Bytes{0x48}}) {
            rejects([&]{ue::Reader rr(bytes);ue::Decoder dd{p,rr};dd.expression();});
        }
        for(auto profile:{std::pair<int,int>{123,37},{126,0}}) {
            header[4]=uint8_t(profile.first);header[6]=uint8_t(profile.second);
            {std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(header.data()),header.size());}
            ue::Package old(argv[1]);ue::Bytes bytes{0x1d,0xff,0xff,0xff,0xff};
            ue::Reader rr(bytes);ue::Decoder dd{old,rr};check(dd.script(5)[0].value.get<int>()==-1);
            rejects([&]{ue::Reader sr(sort);ue::Decoder sd{old,sr};sd.expression();});
            ue::Bytes wide(9,0);wide[0]=0x46;
            rejects([&]{ue::Reader wr(wide);ue::Decoder wd{old,wr};wd.expression();});
        }
        p.names={"None"};ue::Entry cls;cls.name="DelegateProperty";cls.importClass="Class";p.imports.push_back(cls);
        ue::Entry prop;prop.name="Comparator";prop.cls=-1;prop.size=14;p.exports.push_back(prop);
        p.data={0,0,0,1,0,0,0,0,0,0,0,0,2};p.exports[0].size=p.data.size();
        auto v=p.property(1);check(v.ref==2&&v.tail==p.data.size());
        p.data.pop_back();p.exports[0].size=p.data.size();rejects([&]{p.property(1);});
        std::filesystem::remove(argv[1]);std::cout<<"Package token checks passed\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
