#include "package.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected fixture path");
        ue::Bytes plain(36,0);plain[0]=0xc1;plain[1]=0x83;plain[2]=0x2a;plain[3]=0x9e;plain[4]=133;plain[6]=40;
        ue::Bytes wrapped;for(char c:std::string("Lineage2Ver121")){wrapped.push_back(c);wrapped.push_back(0);}
        // Fixed key for the complete basename MiXeD.utx.
        for(auto c:plain)wrapped.push_back(c^166);
        auto save=[&](){std::ofstream f(argv[1],std::ios::binary);f.write(reinterpret_cast<const char*>(wrapped.data()),wrapped.size());if(!f)throw std::runtime_error("Fixture write failed");};
        save();ue::Package p(argv[1]);
        if(p.envelope!="Lineage2Ver121"||p.data!=plain)throw std::runtime_error("Ver121 decoding failed");
        wrapped[28]^=1;save();bool failed=false;
        try{ue::Package invalid(argv[1]);}catch(const std::exception&){failed=true;}
        if(!failed)throw std::runtime_error("Corrupt signature accepted");
        std::cout<<"Ver121 checks passed\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
