// Standalone x86 experiment: Composition WebView2 -> WGC/D3D11 -> shared D3D9Ex texture.
// No injection, client installation, PNG capture, or modification of game binaries.
#include <windows.h>
#include <mmsystem.h>
#include <d3d11.h>
#include <d3d9.h>
#include <dcomp.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <wrl.h>
#include <WebView2.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <set>

using Microsoft::WRL::ComPtr;
using Microsoft::WRL::Callback;
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;
namespace {
constexpr UINT Side = 512;
using Clock = std::chrono::steady_clock;
std::filesystem::path folder;
HWND host = nullptr;
ComPtr<ID3D11Device> device;
ComPtr<ID3D11DeviceContext> context;
ComPtr<ID3D11Texture2D> shared11;
ComPtr<ID3D11Query> fence;
ComPtr<IDirect3D9Ex> d3d9;
ComPtr<IDirect3DDevice9Ex> device9;
ComPtr<IDirect3DTexture9> shared9;
ComPtr<IDirect3DSurface9> surface9, readback9;
ComPtr<IDCompositionDevice> composition;
ComPtr<IDCompositionTarget> target;
ComPtr<IDCompositionVisual> visual;
ComPtr<ICoreWebView2CompositionController> compositionController;
ComPtr<ICoreWebView2Controller> controller;
ComPtr<ICoreWebView2> web;
GraphicsCaptureItem item{nullptr};
Direct3D11CaptureFramePool pool{nullptr};
GraphicsCaptureSession session{nullptr};
bool ready = false, done = false;
Clock::time_point start, deadline;
unsigned frames = 0, changed = 0;
std::set<unsigned> colors;
unsigned previousColor = 0;
double transferMs = 0, readbackMs = 0;
nlohmann::json report;

double ms(Clock::time_point time) {
    return std::chrono::duration<double, std::milli>(Clock::now()-time).count();
}
void fail(const char* stage, HRESULT result) {
    if (done) return;
    std::printf("FAIL %s HRESULT=0x%08lx\n", stage, static_cast<unsigned long>(result));
    report["failure"] = stage;
    report["hresult"] = static_cast<unsigned long>(result);
    done = true;
}
void check(HRESULT result) { winrt::check_hresult(result); }

void devices() {
    check(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
        D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION, &device, nullptr, &context));
    ComPtr<IDXGIDevice> dxgi;
    check(device.As(&dxgi));
    ComPtr<IDXGIAdapter> adapter;
    check(dxgi->GetAdapter(&adapter));
    DXGI_ADAPTER_DESC desc{};
    check(adapter->GetDesc(&desc));
    report["adapter"] = winrt::to_string(desc.Description);
    report["adapter_luid_low"] = desc.AdapterLuid.LowPart;
    check(DCompositionCreateDevice(dxgi.Get(), IID_PPV_ARGS(&composition)));
    check(composition->CreateTargetForHwnd(host, TRUE, &target));
    check(composition->CreateVisual(&visual));
    check(target->SetRoot(visual.Get()));
    check(composition->Commit());
    check(Direct3DCreate9Ex(D3D_SDK_VERSION, &d3d9));
    UINT ordinal = D3DADAPTER_DEFAULT;
    bool matched = false;
    for (UINT i = 0; i < d3d9->GetAdapterCount(); ++i) {
        LUID luid{};
        if (SUCCEEDED(d3d9->GetAdapterLUID(i, &luid)) && luid.LowPart == desc.AdapterLuid.LowPart &&
            luid.HighPart == desc.AdapterLuid.HighPart) { ordinal = i; matched = true; break; }
    }
    if (!matched) winrt::throw_hresult(D3DERR_NOTAVAILABLE);
    D3DPRESENT_PARAMETERS pp{};
    pp.Windowed = TRUE; pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.hDeviceWindow = host; pp.BackBufferWidth = Side; pp.BackBufferHeight = Side;
    pp.BackBufferFormat = D3DFMT_A8R8G8B8; pp.PresentationInterval = D3DPRESENT_INTERVAL_IMMEDIATE;
    check(d3d9->CreateDeviceEx(ordinal, D3DDEVTYPE_HAL, host,
        D3DCREATE_HARDWARE_VERTEXPROCESSING | D3DCREATE_MULTITHREADED | D3DCREATE_FPU_PRESERVE,
        &pp, nullptr, &device9));
    HANDLE shared = nullptr;
    check(device9->CreateTexture(Side, Side, 1, D3DUSAGE_RENDERTARGET, D3DFMT_A8R8G8B8,
        D3DPOOL_DEFAULT, &shared9, &shared));
    check(device->OpenSharedResource(shared, IID_PPV_ARGS(&shared11)));
    check(shared9->GetSurfaceLevel(0, &surface9));
    check(device9->CreateOffscreenPlainSurface(Side, Side, D3DFMT_A8R8G8B8,
        D3DPOOL_SYSTEMMEM, &readback9, nullptr));
    D3D11_QUERY_DESC q{D3D11_QUERY_EVENT, 0};
    check(device->CreateQuery(&q, &fence));
    report["shared_d3d11_d3d9ex_created"] = true;
}

void beginCapture() {
    if (!GraphicsCaptureSession::IsSupported()) winrt::throw_hresult(E_NOTIMPL);
    auto factory = winrt::get_activation_factory<GraphicsCaptureItem, IGraphicsCaptureItemInterop>();
    check(factory->CreateForWindow(host, winrt::guid_of<GraphicsCaptureItem>(), winrt::put_abi(item)));
    ComPtr<IDXGIDevice> dxgi;
    check(device.As(&dxgi));
    winrt::com_ptr<IInspectable> inspectable;
    check(CreateDirect3D11DeviceFromDXGIDevice(dxgi.Get(), inspectable.put()));
    auto wrapped = inspectable.as<IDirect3DDevice>();
    pool = Direct3D11CaptureFramePool::CreateFreeThreaded(wrapped,
        DirectXPixelFormat::B8G8R8A8UIntNormalized, 3, item.Size());
    session = pool.CreateCaptureSession(item);
    session.IsCursorCaptureEnabled(false);
    try { session.IsBorderRequired(false); } catch (const winrt::hresult_error&) {}
    session.StartCapture();
    start = Clock::now();
    ready = true;
}

void sample() {
    if (!ready || done) return;
    auto frame = pool.TryGetNextFrame();
    if (frame) {
        auto access = frame.Surface().as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
        ComPtr<ID3D11Texture2D> source;
        check(access->GetInterface(IID_PPV_ARGS(&source)));
        D3D11_TEXTURE2D_DESC sourceDesc{}, sharedDesc{};
        source->GetDesc(&sourceDesc); shared11->GetDesc(&sharedDesc);
        if (sourceDesc.Width != Side || sourceDesc.Height != Side || sourceDesc.Format != sharedDesc.Format)
            winrt::throw_hresult(E_UNEXPECTED);
        auto transfer = Clock::now();
        context->CopyResource(shared11.Get(), source.Get());
        context->End(fence.Get()); context->Flush();
        while (context->GetData(fence.Get(), nullptr, 0, 0) == S_FALSE) {
            if (ms(transfer) > 2000) winrt::throw_hresult(DXGI_ERROR_DEVICE_HUNG);
            Sleep(0);
        }
        check(device->GetDeviceRemovedReason());
        transferMs += ms(transfer);
        auto reading = Clock::now();
        // Only for proof: read pixels THROUGH D3D9, not through the D3D11 source.
        check(device9->GetRenderTargetData(surface9.Get(), readback9.Get()));
        D3DLOCKED_RECT lock{};
        check(readback9->LockRect(&lock, nullptr, D3DLOCK_READONLY));
        unsigned color = *reinterpret_cast<unsigned*>(static_cast<unsigned char*>(lock.pBits)+100*lock.Pitch+100*4);
        if (frames == 0) {
            std::ofstream out(folder/L"first-frame.bgra", std::ios::binary);
            for (UINT y = 0; y < Side; ++y) out.write(static_cast<char*>(lock.pBits)+y*lock.Pitch, Side*4);
        }
        check(readback9->UnlockRect());
        readbackMs += ms(reading);
        ++frames;
        if (color != previousColor) ++changed;
        previousColor = color; colors.insert(color);
        frame.Close();
    }
    if (ms(start) >= 10000) {
        report["elapsed_seconds"] = ms(start)/1000;
        report["frames"] = frames; report["changed_frames"] = changed;
        report["distinct_colors"] = colors.size();
        report["capture_fps"] = frames/(ms(start)/1000);
        report["changed_fps"] = changed/(ms(start)/1000);
        report["gpu_copy_and_fence_ms_avg"] = transferMs/std::max(1u,frames);
        report["d3d9_readback_ms_avg"] = readbackMs/std::max(1u,frames);
        report["last_pixel"] = previousColor;
        // Canvas has a blue-dominant moving color; reject blank/desktop captures.
        bool correct = (previousColor & 255) > 150 && ((previousColor>>8)&255) < 70;
        report["passed"] = frames > 30 && changed > 20 && correct;
        done = true;
    }
}

void browser() {
    auto loader = LoadLibraryW((folder/L"WebView2Loader.dll").c_str());
    if (!loader) winrt::throw_last_error();
    using Create = HRESULT(STDAPICALLTYPE*)(PCWSTR,PCWSTR,ICoreWebView2EnvironmentOptions*,ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*);
    auto create = reinterpret_cast<Create>(GetProcAddress(loader,"CreateCoreWebView2EnvironmentWithOptions"));
    if (!create) winrt::throw_hresult(E_NOINTERFACE);
    check(create(nullptr,(folder/L"profile").c_str(),nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (FAILED(result)) { fail("environment",result); return S_OK; }
                ComPtr<ICoreWebView2Environment3> env;
                result = environment->QueryInterface(IID_PPV_ARGS(&env));
                if (FAILED(result)) { fail("composition environment",result); return S_OK; }
                result = env->CreateCoreWebView2CompositionController(host,
                    Callback<ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler>(
                        [](HRESULT hr, ICoreWebView2CompositionController* value) -> HRESULT {
                            try {
                                check(hr); compositionController = value;
                                check(compositionController.As(&controller));
                                check(controller->put_Bounds(RECT{0,0,Side,Side}));
                                ComPtr<ICoreWebView2Controller3> scale;
                                check(controller.As(&scale));
                                check(scale->put_ShouldDetectMonitorScaleChanges(FALSE));
                                check(scale->put_RasterizationScale(1));
                                check(compositionController->put_RootVisualTarget(visual.Get()));
                                check(controller->put_IsVisible(TRUE));
                                check(composition->Commit());
                                check(controller->get_CoreWebView2(&web));
                                EventRegistrationToken token{};
                                check(web->add_NavigationCompleted(Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                    [](ICoreWebView2*,ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                        try {
                                            BOOL success = FALSE; check(args->get_IsSuccess(&success));
                                            if (!success) winrt::throw_hresult(E_FAIL);
                                            beginCapture();
                                        } catch (const winrt::hresult_error& e) { fail("WGC start",e.code()); }
                                        return S_OK;
                                    }).Get(), &token));
                                check(web->NavigateToString(L"<!doctype html><style>body{margin:0;overflow:hidden}canvas{display:block}</style>"
                                    L"<canvas width=512 height=512></canvas><script>let c=document.querySelector('canvas').getContext('2d'),n=0;"
                                    L"function draw(){n++;c.fillStyle='rgb('+(64+n%128)+',32,200)';c.fillRect(0,0,512,512);"
                                    L"c.fillStyle='white';c.fillRect((n*7)%512,300,30,80);requestAnimationFrame(draw)}draw()</script>"));
                            } catch (const winrt::hresult_error& e) { fail("composition controller",e.code()); }
                            return S_OK;
                        }).Get());
                if (FAILED(result)) fail("controller request",result);
                return S_OK;
            }).Get()));
}
LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_TIMER) {
        try { sample(); } catch (const winrt::hresult_error& e) { fail("frame transfer",e.code()); }
        return 0;
    }
    return DefWindowProcW(window,message,wparam,lparam);
}
}
int main() {
    wchar_t filename[32768]{};
    GetModuleFileNameW(nullptr,filename,32768);
    folder = std::filesystem::path(filename).parent_path();
    report = {{"pipeline","WebView2 Composition -> WGC/D3D11 -> shared D3D9Ex -> validation readback"},
        {"game_tested",false},{"passed",false},{"png_capture",false}};
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    timeBeginPeriod(1);
    try {
        WNDCLASSW wc{};wc.hInstance=GetModuleHandleW(nullptr);wc.lpfnWndProc=procedure;wc.lpszClassName=L"L2WebGPUProbe";
        RegisterClassW(&wc);
        host=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,wc.lpszClassName,L"L2 GPU browser experiment",
            WS_POPUP,GetSystemMetrics(SM_XVIRTUALSCREEN)-Side-32,GetSystemMetrics(SM_YVIRTUALSCREEN),
            Side,Side,nullptr,nullptr,wc.hInstance,nullptr);
        if (!host) winrt::throw_last_error();
        ShowWindow(host,SW_SHOWNOACTIVATE);
        devices();browser();
        SetTimer(host,1,5,nullptr);
        deadline=Clock::now();
        while (!done && ms(deadline)<45000) {
            MSG message{};
            while (PeekMessageW(&message,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&message);DispatchMessageW(&message); }
            Sleep(1);
        }
        if (!done) fail("probe timeout",HRESULT_FROM_WIN32(WAIT_TIMEOUT));
    } catch (const winrt::hresult_error& e) { fail("device setup",e.code()); }
    if (session) session.Close();
    if (pool) pool.Close();
    if (controller) controller->Close();
    if (host) { KillTimer(host,1);DestroyWindow(host); }
    timeEndPeriod(1);
    std::ofstream(folder/L"result.json") << report.dump(2);
    std::printf("%s\n",report.dump(2).c_str());
    return report.value("passed",false) ? 0 : 1;
}
