#include "api.h"
#include <iostream>
#include <iterator>
#include <string>
int main(){std::string input((std::istreambuf_iterator<char>(std::cin)),{});auto result=ue_request(input.c_str());if(!result){std::cerr<<"Core allocation failure\n";return 2;}std::string text(result);ue_free(result);std::cout<<text<<'\n';return text.find("\"ok\":false")!=text.npos?1:0;}
