#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shlobj.h>
#include <wrl.h>
#include <WebView2.h>
#include <atomic>
#include <mutex>
#include <vector>
#include <deque>
#include <filesystem>
#include <fstream>
#include <algorithm>
#include <cstring>
#include <map>
#include <chrono>
#include <nlohmann/json.hpp>
#include "web_frames.h"
#include "options.h"
#include "gpu_capture.h"

using Microsoft::WRL::ComPtr;
using Microsoft::WRL::Callback;
namespace {
constexpr unsigned Side = 512, ByteCount = Side * Side * 4;
struct Request { int command; std::wstring url; };
std::mutex mutex;
std::vector<unsigned char> latest;
std::uint64_t publishedFrame = 0, copiedFrame = 0;
std::deque<Request> requests;
bool visible = false, reopen = false;
std::atomic<int> status{0};
std::atomic<int> mutedStatus{-1};
std::atomic<HWND> host{nullptr};
std::atomic<HWND> ownerWindow{nullptr};
HANDLE thread = nullptr;
ComPtr<ICoreWebView2Controller> controller;
ComPtr<ICoreWebView2> web;
std::vector<unsigned char> decodePixels(ByteCount);
int appliedVisibility = -1;
std::filesystem::path directory;
bool ready = false, stopping = false;
unsigned epoch = 0;
std::wstring home;
constexpr UINT InputMessage = WM_APP + 41;
constexpr UINT UpdateMessage = WM_APP + 42;
constexpr UINT CaptureMessage = WM_APP + 43;
struct Protocol { std::wstring method, params; };
std::deque<Protocol> inputQueue;
bool inputFocused = false, inputBusy = false;
std::map<int, nlohmann::json> heldKeys;
int mouseButtons = 0, mouseX = 0, mouseY = 0;
using Clock = std::chrono::steady_clock;
double milliseconds(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now()-start).count();
}
struct PerformanceData {
    Clock::time_point start = Clock::now();
    unsigned captures = 0, copies = 0;
    double captureMs = 0, decodeMs = 0, copyMs = 0, waitMs = 0;
    double captureMax = 0, decodeMax = 0, copyMax = 0;
} performance;
Clock::time_point lastCompletion{};
ULONGLONG lastPerformanceLog = 0;

void protocolLocked(const wchar_t* method, const nlohmann::json& params) {
    // ensure_ascii makes the JSON safe to widen without losing Unicode escapes.
    auto json = params.dump(-1, ' ', true);
    inputQueue.push_back({method, std::wstring(json.begin(), json.end())});
    if (HWND window = host.load()) PostMessageW(window, InputMessage, 0, 0);
}
void focusLocked(bool active) {
    if (inputFocused == active) return;
    inputFocused = active;
    if (!active) {
        for (auto& item : heldKeys) {
            auto release = item.second;
            release["type"] = "keyUp";
            release.erase("text"); release.erase("unmodifiedText");
            release["modifiers"] = 0;
            protocolLocked(L"Input.dispatchKeyEvent", release);
        }
        heldKeys.clear();
        for (const auto& button : {std::pair<int,const char*>{1,"left"}, {2,"right"}}) {
            if (mouseButtons & button.first) {
                mouseButtons &= ~button.first;
                protocolLocked(L"Input.dispatchMouseEvent", {{"type","mouseReleased"}, {"x",mouseX},
                    {"y",mouseY}, {"button",button.second}, {"buttons",mouseButtons}, {"clickCount",1}});
            }
        }
    }
    protocolLocked(L"Emulation.setFocusEmulationEnabled", {{"enabled",active}});
}
void drainInput() {
    if (!web || inputBusy || stopping) return;
    Protocol packet;
    {
        std::lock_guard<std::mutex> lock(mutex);
        if (inputQueue.empty()) return;
        packet = std::move(inputQueue.front()); inputQueue.pop_front();
    }
    inputBusy = true;
    HRESULT hr = web->CallDevToolsProtocolMethod(packet.method.c_str(), packet.params.c_str(),
        Callback<ICoreWebView2CallDevToolsProtocolMethodCompletedHandler>(
            [](HRESULT result, LPCWSTR) -> HRESULT {
                inputBusy = false;
                if (FAILED(result)) {
                    std::ofstream log(directory / L"web-texture.log", std::ios::app);
                    log << "Input protocol HRESULT=0x" << std::hex << static_cast<unsigned long>(result) << '\n';
                }
                if (!stopping) PostMessageW(host.load(), InputMessage, 0, 0);
                return S_OK;
            }).Get());
    if (FAILED(hr)) { inputBusy = false; PostMessageW(host.load(), InputMessage, 0, 0); }
}

bool validUrl(const std::wstring& value) {
    auto prefix = value.substr(0, 8);
    std::transform(prefix.begin(), prefix.end(), prefix.begin(), towlower);
    return ((prefix.rfind(L"https://", 0) == 0 && value.size() > 8) ||
            (prefix.rfind(L"http://", 0) == 0 && value.size() > 7)) &&
        value.find_first_of(L"\r\n\t ") == std::wstring::npos &&
        value.find(L'\0') == std::wstring::npos;
}
std::wstring config() {
    return browseroptions::StartPage(directory);
}
void fail(int code, const char* operation, HRESULT hr) {
    status.store(code);
    std::ofstream log(directory / L"web-texture.log", std::ios::app);
    log << operation << " HRESULT=0x" << std::hex << static_cast<unsigned long>(hr) << '\n';
}
void navigate(const std::wstring& url) {
    ++epoch;
    ready = false;
    { std::lock_guard<std::mutex> lock(mutex); latest.clear(); }
    status.store(1);
    HRESULT hr = web->Navigate(url.c_str());
    if (FAILED(hr)) fail(-24, "Navigate", hr);
}
void capture() {
    if (!ready || stopping) return;
    { std::lock_guard<std::mutex> lock(mutex); if (!visible) return; }
    auto started = Clock::now();
    HRESULT hr = gpucapture::Copy(decodePixels);
    if (FAILED(hr)) { fail(-26, "WGC readback", hr); return; }
    if (hr == S_FALSE) return;
    double elapsed = milliseconds(started);
    std::lock_guard<std::mutex> lock(mutex);
    latest.swap(decodePixels); ++publishedFrame;
    ++performance.captures; performance.captureMs += elapsed;
    performance.captureMax = std::max(performance.captureMax, elapsed);
    status.store(2);
}
void update() {
    if (HWND owner = ownerWindow.load()) {
        DWORD pid = 0;
        GetWindowThreadProcessId(owner, &pid);
        if (!IsWindow(owner) || pid != GetCurrentProcessId()) {
            DestroyWindow(host.load());
            return;
        }
    }
    if (!web) return;
    bool active, reload;
    std::deque<Request> queue;
    {
        std::lock_guard<std::mutex> lock(mutex);
        active = visible;
        reload = reopen;
        reopen = false;
        queue.swap(requests);
    }
    if (appliedVisibility != static_cast<int>(active)) {
        controller->put_IsVisible(active);
        ComPtr<ICoreWebView2_8> audio;
        if (SUCCEEDED(web.As(&audio))) {
            audio->put_IsMuted(!active);
            BOOL muted = FALSE;
            if (SUCCEEDED(audio->get_IsMuted(&muted))) mutedStatus.store(muted ? 1 : 0);
        }
        appliedVisibility = static_cast<int>(active);
        if (!active) KillTimer(host.load(), 2);
    }
    if (reload) { home = config(); navigate(home); }
    for (const auto& request : queue) {
        switch (request.command) {
        case 0: navigate(request.url); break;
        case 1: web->GoBack(); break;
        case 2: web->GoForward(); break;
        case 3: web->Reload(); break;
        case 4: navigate(home); break;
        case 5: web->Navigate(L"about:blank"); break;
        }
    }
    if (active) capture();
    if (active && GetTickCount64()-lastPerformanceLog >= 5000) {
        lastPerformanceLog = GetTickCount64();
        std::ofstream log(directory / L"browser-performance.json", std::ios::trunc);
        log << webframes::Performance();
    }
    drainInput();
}
void initialize() {
    HMODULE loader = LoadLibraryExW((directory / L"WebView2Loader.dll").c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!loader) { fail(-20, "WebView2Loader missing", HRESULT_FROM_WIN32(GetLastError())); return; }
    using Create = HRESULT(STDAPICALLTYPE*)(PCWSTR, PCWSTR, ICoreWebView2EnvironmentOptions*, ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*);
    auto create = reinterpret_cast<Create>(GetProcAddress(loader, "CreateCoreWebView2EnvironmentWithOptions"));
    if (!create) { fail(-20, "Invalid loader", E_NOINTERFACE); return; }
    PWSTR appdata{};
    HRESULT hr = SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &appdata);
    if (FAILED(hr)) { fail(-21, "LocalAppData", hr); return; }
    auto profile = std::filesystem::path(appdata) / L"L2TextureWeb" /
        std::to_wstring(std::hash<std::wstring>{}(directory.wstring()));
    CoTaskMemFree(appdata);
    hr = create(nullptr, profile.c_str(), nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (stopping) return S_OK;
                if (FAILED(result) || !environment) { fail(-21, "Create environment", result); return S_OK; }
                HRESULT h = environment->CreateCoreWebView2Controller(host.load(),
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [](HRESULT result, ICoreWebView2Controller* value) -> HRESULT {
                            if (stopping) { if (value) value->Close(); return S_OK; }
                            if (FAILED(result) || !value) { fail(-22, "Create controller", result); return S_OK; }
                            controller = value;
                            controller->put_Bounds(RECT{0, 0, Side, Side});
                            ComPtr<ICoreWebView2Controller3> scaled;
                            if (SUCCEEDED(controller.As(&scaled))) {
                                scaled->put_ShouldDetectMonitorScaleChanges(FALSE);
                                scaled->put_RasterizationScale(1.0);
                            }
                            HRESULT h = controller->get_CoreWebView2(&web);
                             if (FAILED(h)) { fail(-22, "Get web", h); return S_OK; }
                             h = gpucapture::Start(host.load());
                             if (FAILED(h)) { fail(-28, "WGC initialize", h); return S_OK; }
                             ComPtr<ICoreWebView2Settings> settings;
                             if (SUCCEEDED(web->get_Settings(&settings))) {
                                 // No browser-owned desktop menus or JavaScript dialog windows.
                                 settings->put_AreDefaultContextMenusEnabled(FALSE);
                                 settings->put_AreDefaultScriptDialogsEnabled(FALSE);
                                 settings->put_AreDevToolsEnabled(FALSE);
                             }
                             EventRegistrationToken token{};
                             web->add_NewWindowRequested(Callback<ICoreWebView2NewWindowRequestedEventHandler>(
                                 [](ICoreWebView2*, ICoreWebView2NewWindowRequestedEventArgs* args) -> HRESULT {
                                     // Mark handled even for unsupported schemes: never spawn a desktop WebView.
                                     args->put_Handled(TRUE);
                                     LPWSTR uri = nullptr;
                                     if (SUCCEEDED(args->get_Uri(&uri)) && uri) {
                                         std::wstring target(uri);
                                         CoTaskMemFree(uri);
                                         bool active;
                                         { std::lock_guard<std::mutex> lock(mutex); active = visible; }
                                         if (active && validUrl(target)) navigate(target);
                                     }
                                     return S_OK;
                                 }).Get(), &token);
                            web->add_NavigationStarting(Callback<ICoreWebView2NavigationStartingEventHandler>(
                                [](ICoreWebView2*, ICoreWebView2NavigationStartingEventArgs*) -> HRESULT {
                                    ++epoch; ready = false; status.store(1); return S_OK;
                                }).Get(), &token);
                            web->add_NavigationCompleted(Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                [](ICoreWebView2*, ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                    BOOL success{}; args->get_IsSuccess(&success);
                                    // Capture the browser's error page too; log navigation failures separately.
                                    ready = true;
                                    if (!success) {
                                        std::ofstream log(directory / L"web-texture.log", std::ios::app);
                                        log << "Navigation failed; displaying error page\n";
                                    }
                                    return S_OK;
                                }).Get(), &token);
                            web->add_ProcessFailed(Callback<ICoreWebView2ProcessFailedEventHandler>(
                                [](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs*) -> HRESULT {
                                    ready = false; fail(-27, "Browser process failed", E_FAIL); return S_OK;
                                }).Get(), &token);
                            update();
                            return S_OK;
                        }).Get());
                if (FAILED(h)) fail(-22, "Controller request", h);
                return S_OK;
            }).Get());
    if (FAILED(hr)) fail(-21, "Environment request", hr);
}
LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == CaptureMessage) { capture(); return 0; }
    if (message == WM_TIMER && wparam == 2) { KillTimer(window, 2); capture(); return 0; }
    if (message == UpdateMessage) { update(); return 0; }
    if (message == InputMessage) { drainInput(); return 0; }
    if (message == WM_TIMER) { update(); return 0; }
    if (message == WM_CLOSE) { DestroyWindow(window); return 0; }
    if (message == WM_DESTROY) {
        stopping = true;
        KillTimer(window, 1);
        KillTimer(window, 2);
        gpucapture::Stop();
        if (controller) controller->Close();
        web.Reset(); controller.Reset();
        host.store(nullptr);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}
DWORD WINAPI run(void*) {
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) { status.store(-28); return 0; }
    HMODULE module{};
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&status), &module);
    wchar_t path[32768]{};
    GetModuleFileNameW(module, path, 32768);
    directory = std::filesystem::path(path).parent_path();
    WNDCLASSW wc{};
    wc.hInstance = module; wc.lpfnWndProc = procedure; wc.lpszClassName = L"L2TextureCaptureHost";
    RegisterClassW(&wc);
    HWND window = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, wc.lpszClassName,
        L"L2 browser frame source", WS_POPUP | WS_CLIPCHILDREN,
        GetSystemMetrics(SM_XVIRTUALSCREEN) - static_cast<int>(Side) - 32, GetSystemMetrics(SM_YVIRTUALSCREEN),
        Side, Side, nullptr, nullptr, module, nullptr);
    host.store(window);
    if (window) {
        ShowWindow(window, SW_SHOWNOACTIVATE);
        if (SetTimer(window, 1, 10, nullptr)) {
            initialize();
            MSG message{};
            while (GetMessageW(&message, nullptr, 0, 0) > 0) { TranslateMessage(&message); DispatchMessageW(&message); }
        } else { fail(-29, "Timer", HRESULT_FROM_WIN32(GetLastError())); DestroyWindow(window); }
    } else fail(-29, "Capture host", HRESULT_FROM_WIN32(GetLastError()));
    CoUninitialize();
    return 0;
}
}

bool webframes::Open() {
    std::lock_guard<std::mutex> lock(mutex);
    HWND foreground = GetForegroundWindow();
    DWORD pid = 0;
    GetWindowThreadProcessId(foreground, &pid);
    if (foreground && foreground != host.load() && pid == GetCurrentProcessId())
        ownerWindow.store(GetAncestor(foreground, GA_ROOT));
    performance = PerformanceData{}; lastCompletion = {};
    visible = true; reopen = true; latest.clear(); requests.clear();
    focusLocked(false);
    if (!thread) {
        status.store(1);
        thread = CreateThread(nullptr, 0, run, nullptr, 0, nullptr);
        if (!thread) { status.store(-28); return false; }
    }
    return status.load() >= 0;
}
void webframes::Hide() {
    std::lock_guard<std::mutex> lock(mutex);
    visible = false; focusLocked(false);
    if (HWND window = host.load()) PostMessageW(window, UpdateMessage, 0, 0);
}
void webframes::Resume() {
    std::lock_guard<std::mutex> lock(mutex);
    if (!visible) { performance = PerformanceData{}; lastCompletion = {}; }
    visible = true;
    if (HWND window = host.load()) PostMessageW(window, UpdateMessage, 0, 0);
}
void webframes::Close() {
    std::lock_guard<std::mutex> lock(mutex);
    visible = false; reopen = false; latest.clear(); requests.clear();
    focusLocked(false);
    // Stop the previous screen's media and page activity, even when minimized.
    requests.push_back({5, {}});
    if (HWND window = host.load()) PostMessageW(window, UpdateMessage, 0, 0);
}
void webframes::Focus(bool active) {
    std::lock_guard<std::mutex> lock(mutex);
    focusLocked(active && visible);
}
void webframes::Text(std::wstring text) {
    if (text.empty() || text.size() > 8192) return;
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(),
        static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    if (size <= 0) return;
    std::string utf8(size, '\0');
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(),
        static_cast<int>(text.size()), utf8.data(), size, nullptr, nullptr);
    std::lock_guard<std::mutex> lock(mutex);
    if (visible && inputFocused) protocolLocked(L"Input.insertText", {{"text",utf8}});
}
void webframes::Mouse(std::int32_t kind, std::int32_t x, std::int32_t y, std::int32_t modifiers) {
    if (kind < 0 || kind > 7 || x < 0 || y < 0 || x >= 512 || y >= 512) return;
    std::lock_guard<std::mutex> lock(mutex);
    if (!visible) return;
    mouseX = x; mouseY = y;
    if (kind == 1 || kind == 3 || kind == 7) focusLocked(true);
    bool down = kind == 1 || kind == 3 || kind == 7;
    bool up = kind == 2 || kind == 4;
    bool wheel = kind == 5 || kind == 6;
    const char* button = (kind == 1 || kind == 2 || kind == 7) ? "left" :
        (kind == 3 || kind == 4) ? "right" : "none";
    int bit = (kind == 3 || kind == 4) ? 2 : 1;
    if (down) mouseButtons |= bit;
    if (up) mouseButtons &= ~bit;
    if (kind == 0 && mouseButtons)
        button = (mouseButtons & 1) ? "left" : "right";
    nlohmann::json event = {{"type", down ? "mousePressed" : up ? "mouseReleased" : wheel ? "mouseWheel" : "mouseMoved"},
        {"x",x}, {"y",y}, {"button",button}, {"buttons",mouseButtons}, {"modifiers",modifiers & 15}};
    if (down || up) event["clickCount"] = kind == 7 ? 2 : 1;
    if (wheel) { event["deltaX"] = 0; event["deltaY"] = kind == 5 ? -120 : 120; }
    // Coalesce hover moves; preserve ordering of all button/key transitions.
    if (kind == 0 && !inputQueue.empty() && inputQueue.back().method == L"Input.dispatchMouseEvent" &&
        inputQueue.back().params.find(L"mouseMoved") != std::wstring::npos) inputQueue.pop_back();
    protocolLocked(L"Input.dispatchMouseEvent", event);
}
void webframes::Key(std::int32_t vk, bool down, std::int32_t modifiers, std::wstring text) {
    if (vk < 8 || vk > 222 || text.size() > 64) return;
    std::lock_guard<std::mutex> lock(mutex);
    if (!visible || !inputFocused) return;
    nlohmann::json event = {{"type",down ? (text.empty() ? "rawKeyDown" : "keyDown") : "keyUp"},
        {"windowsVirtualKeyCode",vk}, {"nativeVirtualKeyCode",vk}, {"modifiers",modifiers & 15}};
    const std::map<int, const char*> names{{8,"Backspace"},{9,"Tab"},{13,"Enter"},{16,"Shift"},
        {17,"Control"},{18,"Alt"},{27,"Escape"},{32," "},{33,"PageUp"},{34,"PageDown"},
        {35,"End"},{36,"Home"},{37,"ArrowLeft"},{38,"ArrowUp"},{39,"ArrowRight"},{40,"ArrowDown"},
        {45,"Insert"},{46,"Delete"}};
    if (auto found = names.find(vk); found != names.end()) event["key"] = found->second;
    else if (vk >= 65 && vk <= 90) event["key"] = std::string(1, static_cast<char>(vk + ((modifiers & 8) ? 0 : 32)));
    if (down) {
        event["autoRepeat"] = heldKeys.count(vk) != 0;
        if (!text.empty()) {
            int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
            if (size > 0) {
                std::string utf8(size, '\0');
                WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), utf8.data(), size, nullptr, nullptr);
                event["text"] = utf8; event["unmodifiedText"] = utf8;
                if (!names.count(vk)) event["key"] = utf8;
            }
        }
        heldKeys[vk] = event;
    } else heldKeys.erase(vk);
    protocolLocked(L"Input.dispatchKeyEvent", event);
}
void webframes::Navigate(std::wstring url) {
    if (!validUrl(url)) return;
    std::lock_guard<std::mutex> lock(mutex);
    if (requests.size() < 32) requests.push_back({0, std::move(url)});
}
void webframes::Command(std::int32_t command) {
    if (command < 1 || command > 4) return;
    std::lock_guard<std::mutex> lock(mutex);
    if (requests.size() < 32) requests.push_back({command, {}});
}
std::int32_t webframes::Status() { return status.load(); }
std::int32_t webframes::MutedStatus() { return mutedStatus.load(); }
bool webframes::Copy(void* destination, unsigned bytes) {
    std::lock_guard<std::mutex> lock(mutex);
    if (bytes != ByteCount || latest.size() != ByteCount || !visible) return false;
    std::memcpy(destination, latest.data(), ByteCount);
    return true;
}
bool webframes::CopyFresh(void* destination, unsigned bytes) {
    auto started = Clock::now();
    std::lock_guard<std::mutex> lock(mutex);
    if (bytes != ByteCount || latest.size() != ByteCount || !visible || copiedFrame == publishedFrame)
        return false;
    std::memcpy(destination, latest.data(), ByteCount);
    copiedFrame = publishedFrame;
    double copyMs = milliseconds(started);
    ++performance.copies; performance.copyMs += copyMs;
    performance.copyMax = std::max(performance.copyMax, copyMs);
    return true;
}
void webframes::ResetPerformance() {
    std::lock_guard<std::mutex> lock(mutex);
    performance = PerformanceData{};
    lastCompletion = {};
}
std::string webframes::Performance() {
    std::lock_guard<std::mutex> lock(mutex);
    double seconds = milliseconds(performance.start)/1000;
    double n = performance.captures ? performance.captures : 1;
    double copies = performance.copies ? performance.copies : 1;
    return nlohmann::json{{"pipeline","WGC D3D11 readback -> HF CPU mip (no PNG)"},
        {"elapsed_seconds",seconds}, {"captures",performance.captures},
        {"copies",performance.copies}, {"capture_fps",performance.captures/std::max(seconds,0.001)},
        {"copy_fps",performance.copies/std::max(seconds,0.001)},
        {"capture_ms_avg",performance.captureMs/n}, {"capture_ms_max",performance.captureMax},
        {"decode_ms_avg",performance.decodeMs/n}, {"decode_ms_max",performance.decodeMax},
        {"copy_ms_avg",performance.copyMs/copies}, {"copy_ms_max",performance.copyMax},
        {"scheduler_wait_ms_avg",performance.waitMs/n},
        {"gpu_upload_measured",false}}.dump(2);
}
void webframes::Shutdown() {
    HWND window = host.load();
    if (window) PostMessageW(window, WM_CLOSE, 0, 0);
    if (thread && window) WaitForSingleObject(thread, INFINITE);
}
void webframes::AbandonOnProcessExit() {
    // No locks, waits, Close, Release, or cross-thread COM calls here.
    gpucapture::AbandonOnProcessExit();
    web.Detach(); controller.Detach();
}
