// Diagnostic only: observe the game's actual device; do not replace rendering.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d9.h>
#include <MinHook.h>
#include <cstdio>

namespace {
HMODULE module;
using EndScene = HRESULT (STDMETHODCALLTYPE*)(IDirect3DDevice9*);
EndScene original;
volatile LONG observed = 0;
void log(const char* text) {
    wchar_t path[32768];
    DWORD n = GetModuleFileNameW(module, path, 32768);
    if (!n || n > 32700) return;
    wchar_t* last = wcsrchr(path, L'\\');
    if (!last) return;
    swprintf_s(last + 1, 32768 - (last + 1 - path), L"renderer-%lu.log", GetCurrentProcessId());
    FILE* file = nullptr;
    if (!_wfopen_s(&file, path, L"ab") && file) { fputs(text, file); fclose(file); }
}
HRESULT STDMETHODCALLTYPE observe(IDirect3DDevice9* device) {
    if (InterlockedCompareExchange(&observed, 1, 0) == 0) {
        IDirect3DDevice9Ex* ex = nullptr;
        HRESULT hr = device->QueryInterface(__uuidof(IDirect3DDevice9Ex), reinterpret_cast<void**>(&ex));
        D3DDEVICE_CREATION_PARAMETERS creation{};
        HRESULT params = device->GetCreationParameters(&creation);
        char text[512];
        sprintf_s(text, "actual_device=1 pid=%lu thread=%lu QueryInterface_IDirect3DDevice9Ex=0x%08lx parameters=0x%08lx adapter=%u behavior=0x%08lx\n",
                  GetCurrentProcessId(), GetCurrentThreadId(), static_cast<unsigned long>(hr),
                  static_cast<unsigned long>(params), creation.AdapterOrdinal, creation.BehaviorFlags);
        log(text);
        if (ex) ex->Release();
    }
    return original(device);
}
DWORD WINAPI start(void*) {
    WNDCLASSW wc{}; wc.lpfnWndProc = DefWindowProcW; wc.hInstance = module; wc.lpszClassName = L"L2RendererDeviceProbe";
    RegisterClassW(&wc);
    HWND window = CreateWindowW(wc.lpszClassName, L"", WS_POPUP, 0, 0, 32, 32, nullptr, nullptr, module, nullptr);
    IDirect3D9* api = Direct3DCreate9(D3D_SDK_VERSION);
    IDirect3DDevice9* device = nullptr;
    D3DPRESENT_PARAMETERS pp{}; pp.Windowed = TRUE; pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.hDeviceWindow = window; pp.BackBufferWidth = pp.BackBufferHeight = 32;
    HRESULT hr = api && window ? api->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, window,
        D3DCREATE_SOFTWARE_VERTEXPROCESSING | D3DCREATE_MULTITHREADED, &pp, &device) : E_FAIL;
    void* target = device ? (*reinterpret_cast<void***>(device))[42] : nullptr;
    if (device) device->Release();
    if (api) api->Release();
    if (window) DestroyWindow(window);
    UnregisterClassW(wc.lpszClassName, module);
    if (FAILED(hr) || !target) { log("probe_device_creation_failed\n"); return 1; }
    if (MH_Initialize() != MH_OK || MH_CreateHook(target, reinterpret_cast<void*>(&observe), reinterpret_cast<void**>(&original)) != MH_OK ||
        MH_EnableHook(target) != MH_OK) { log("hook_install_failed\n"); return 2; }
    log("observation_armed; no game device or texture replaced\n");
    return 0;
}
}
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void*) {
    if (reason == DLL_PROCESS_ATTACH) {
        module = instance;
        DisableThreadLibraryCalls(instance);
        HANDLE thread = CreateThread(nullptr, 0, start, nullptr, 0, nullptr);
        if (thread) CloseHandle(thread);
    }
    return TRUE;
}
