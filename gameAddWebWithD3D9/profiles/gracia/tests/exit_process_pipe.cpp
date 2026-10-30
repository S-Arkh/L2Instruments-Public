#include <windows.h>
#include <fstream>
int main() {
    auto integrity=LoadLibraryW(L"integrity.dll");
    auto initialize=integrity?reinterpret_cast<BOOL(*)()>(GetProcAddress(integrity,"InitializePipeBlock")):nullptr;
    if(!initialize||!initialize())return 2;
    auto dll=LoadLibraryW(L"exit_fixture_inprocess.dll");
    if(!dll)return 3;
    auto start=reinterpret_cast<bool(*)()>(GetProcAddress(dll,"ExitFixtureStart"));
    auto ready=reinterpret_cast<bool(*)()>(GetProcAddress(dll,"ExitFixtureReady"));
    if(!start||!ready||!start())return 4;
    for(int i=0;i<600&&!ready();++i)Sleep(50);
    if(!ready())return 5;
    {std::ofstream report("exit-ready.json");report<<"{\"active_webview_and_wgc\":true,\"pipe_block_fixture\":true}";}
    ExitProcess(0);
}
