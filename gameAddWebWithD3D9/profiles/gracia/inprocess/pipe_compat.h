#pragma once
#include <windows.h>
namespace pipecompat {
using Log=void(*)(const char*,DWORD,const void*);
bool Install(HMODULE runtime,Log log);
}
