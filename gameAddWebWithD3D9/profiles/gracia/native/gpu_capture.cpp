#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include "gpu_capture.h"
#include <d3d11.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <wrl.h>
#include <cstring>

using Microsoft::WRL::ComPtr;
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;
namespace {
ComPtr<ID3D11Device> gpuDevice;
ComPtr<ID3D11DeviceContext> gpuContext;
ComPtr<ID3D11Texture2D> staging;
GraphicsCaptureItem captureItem{nullptr};
Direct3D11CaptureFramePool framePool{nullptr};
GraphicsCaptureSession captureSession{nullptr};
bool apartment = false;
constexpr unsigned Side = 512;
}
HRESULT gpucapture::Start(HWND window) {
    try {
        winrt::check_hresult(RoInitialize(RO_INIT_SINGLETHREADED));
        apartment = true;
        if (!GraphicsCaptureSession::IsSupported()) winrt::throw_hresult(E_NOTIMPL);
        winrt::check_hresult(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,D3D11_SDK_VERSION,&gpuDevice,nullptr,&gpuContext));
        ComPtr<IDXGIDevice> dxgi;
        winrt::check_hresult(gpuDevice.As(&dxgi));
        winrt::com_ptr<IInspectable> inspectable;
        winrt::check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.Get(),inspectable.put()));
        auto factory = winrt::get_activation_factory<GraphicsCaptureItem,IGraphicsCaptureItemInterop>();
        winrt::check_hresult(factory->CreateForWindow(window,winrt::guid_of<GraphicsCaptureItem>(),winrt::put_abi(captureItem)));
        framePool = Direct3D11CaptureFramePool::CreateFreeThreaded(inspectable.as<IDirect3DDevice>(),
            DirectXPixelFormat::B8G8R8A8UIntNormalized,3,captureItem.Size());
        captureSession = framePool.CreateCaptureSession(captureItem);
        captureSession.IsCursorCaptureEnabled(false);
        try { captureSession.IsBorderRequired(false); } catch (const winrt::hresult_error&) {}
        D3D11_TEXTURE2D_DESC desc{};
        desc.Width=Side;desc.Height=Side;desc.MipLevels=1;desc.ArraySize=1;
        desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;
        desc.Usage=D3D11_USAGE_STAGING;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        winrt::check_hresult(gpuDevice->CreateTexture2D(&desc,nullptr,&staging));
        captureSession.StartCapture();
        return S_OK;
    } catch (const winrt::hresult_error& e) { Stop(); return e.code(); }
}
HRESULT gpucapture::Copy(std::vector<unsigned char>& pixels) {
    if (!framePool) return E_UNEXPECTED;
    try {
        auto newest = framePool.TryGetNextFrame();
        if (!newest) return S_FALSE;
        // Drop queued older frames instead of accumulating display latency.
        while (auto next = framePool.TryGetNextFrame()) { newest.Close(); newest = next; }
        auto access = newest.Surface().as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
        ComPtr<ID3D11Texture2D> source;
        winrt::check_hresult(access->GetInterface(IID_PPV_ARGS(&source)));
        D3D11_TEXTURE2D_DESC desc{};source->GetDesc(&desc);
        if (desc.Width!=Side || desc.Height!=Side || desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM)
            winrt::throw_hresult(E_UNEXPECTED);
        pixels.resize(Side*Side*4);
        gpuContext->CopyResource(staging.Get(),source.Get());
        D3D11_MAPPED_SUBRESOURCE map{};
        winrt::check_hresult(gpuContext->Map(staging.Get(),0,D3D11_MAP_READ,0,&map));
        for (unsigned y=0;y<Side;++y)
            std::memcpy(pixels.data()+y*Side*4,static_cast<unsigned char*>(map.pData)+y*map.RowPitch,Side*4);
        gpuContext->Unmap(staging.Get(),0);
        newest.Close();
        return S_OK;
    } catch (const winrt::hresult_error& e) { return e.code(); }
}
void gpucapture::Stop() {
    if (captureSession) { captureSession.Close(); captureSession=nullptr; }
    if (framePool) { framePool.Close(); framePool=nullptr; }
    captureItem=nullptr;
    staging.Reset();gpuContext.Reset();gpuDevice.Reset();
    if (apartment) { RoUninitialize(); apartment=false; }
}
void gpucapture::AbandonOnProcessExit() {
    // ExitProcess has already terminated the other threads. Releasing these
    // interfaces now can wait for their dead STA/DWM workers under loader lock.
    // The OS reclaims process resources; suppress only automatic COM Release.
    winrt::detach_abi(captureSession);
    winrt::detach_abi(framePool);
    winrt::detach_abi(captureItem);
    staging.Detach(); gpuContext.Detach(); gpuDevice.Detach();
    apartment = false;
}
