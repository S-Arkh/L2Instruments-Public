#pragma once
#include <windows.h>
#include <vector>
namespace gpucapture {
HRESULT Start(HWND window);
HRESULT Copy(std::vector<unsigned char>& pixels); // S_FALSE if no new frame
void Stop();
void AbandonOnProcessExit(); // process-termination only: no COM calls under loader lock
}
