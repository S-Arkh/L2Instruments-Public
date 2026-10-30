#include <windows.h>
#include "web_frames.h"
extern "C" __declspec(dllexport) bool ExitFixtureStart() { return webframes::Open(); }
extern "C" __declspec(dllexport) bool ExitFixtureReady() { return webframes::Status() == 2; }
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID reserved) {
#ifndef REPRODUCE_OLD_EXIT
    if (reason == DLL_PROCESS_DETACH && reserved) webframes::AbandonOnProcessExit();
#endif
    return TRUE;
}
