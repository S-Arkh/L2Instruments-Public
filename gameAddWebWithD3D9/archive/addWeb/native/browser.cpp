#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shlobj.h>
#include <wrl.h>
#include <WebView2.h>
#include <atomic>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <deque>
#include <string>
#include <algorithm>
#include "browser.h"

using Microsoft::WRL::ComPtr;
using Microsoft::WRL::Callback;
namespace {
struct Request { int command; std::wstring url; };
struct Shared {
    std::mutex mutex;
    HWND owner = nullptr;
    RECT bounds{0, 0, 880, 530};
    bool visible = false;
    bool reloadConfig = false;
    ULONGLONG heartbeat = 0;
    std::deque<Request> requests;
} shared;
std::atomic<int> status{0}; // 0 stopped, 1 starting, 2 ready, negative = failure
std::atomic<bool> started{false};
ComPtr<ICoreWebView2Controller> controller;
ComPtr<ICoreWebView2> web;
HWND host = nullptr;
std::filesystem::path moduleDirectory;
std::filesystem::path dataDirectory;
std::wstring startUrl;
bool initializing = false;

std::filesystem::path modulePath() {
    HMODULE module{};
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&status), &module);
    wchar_t path[32768]{};
    GetModuleFileNameW(module, path, 32768);
    return std::filesystem::path(path).parent_path();
}

std::wstring trim(std::wstring value) {
    const auto first = value.find_first_not_of(L" \t\r\n");
    if (first == std::wstring::npos) return {};
    return value.substr(first, value.find_last_not_of(L" \t\r\n") - first + 1);
}

bool validUrl(const std::wstring& value) {
    std::wstring prefix = value.substr(0, 8);
    std::transform(prefix.begin(), prefix.end(), prefix.begin(), towlower);
    return ((prefix.rfind(L"https://", 0) == 0 && value.size() > 8) ||
            (prefix.rfind(L"http://", 0) == 0 && value.size() > 7)) &&
           value.find_first_of(L"\r\n\t ") == std::wstring::npos;
}

std::wstring configUrl() {
    const std::wstring fallback = L"https://www.youtube.com/";
    std::ifstream input(moduleDirectory / L"startWeb.config", std::ios::binary);
    std::string bytes;
    // Bounded first line; reject malformed UTF-8, missing/empty/oversized values.
    char ch;
    while (input.get(ch) && ch != '\n' && bytes.size() <= 8192) bytes += ch;
    if (bytes.size() > 8192) return fallback;
    if (bytes.compare(0, 3, "\xEF\xBB\xBF") == 0) bytes.erase(0, 3);
    int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(), static_cast<int>(bytes.size()), nullptr, 0);
    if (!count) return fallback;
    std::wstring result(count, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(), static_cast<int>(bytes.size()), result.data(), count);
    result = trim(result);
    return result.find(L'\0') == std::wstring::npos && validUrl(result) ? result : fallback;
}

void logError(const char* where, HRESULT hr) {
    std::ofstream log(dataDirectory / L"addWeb.log", std::ios::app);
    log << where << " HRESULT=0x" << std::hex << static_cast<unsigned long>(hr) << '\n';
    OutputDebugStringA(where);
}

void fail(const char* where, HRESULT hr) {
    status.store(-1);
    logError(where, hr);
    InvalidateRect(host, nullptr, TRUE);
}

void resizeController() {
    if (!controller) return;
    RECT rect{};
    GetClientRect(host, &rect);
    controller->put_Bounds(rect);
    controller->NotifyParentWindowPositionChanged();
}

void initializeWeb() {
    if (initializing) return;
    initializing = true;
    moduleDirectory = modulePath();
#ifdef ADDWEB_PROBE
    dataDirectory = moduleDirectory / L"probe-profile";
#else
    PWSTR appdata{};
    if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &appdata))) {
        dataDirectory = std::filesystem::path(appdata) / L"L2AddWeb" /
            std::to_wstring(std::hash<std::wstring>{}(moduleDirectory.wstring()));
        CoTaskMemFree(appdata);
    } else { fail("LocalAppData unavailable", E_FAIL); return; }
#endif
    std::error_code error;
    std::filesystem::create_directories(dataDirectory, error);
    if (error) { fail("Cannot create browser profile", HRESULT_FROM_WIN32(error.value())); return; }
    startUrl = configUrl();
    HMODULE loader = LoadLibraryExW((moduleDirectory / L"WebView2Loader.dll").c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!loader) { fail("WebView2Loader.dll missing", HRESULT_FROM_WIN32(GetLastError())); return; }
    using Create = HRESULT(STDAPICALLTYPE*)(PCWSTR, PCWSTR, ICoreWebView2EnvironmentOptions*, ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*);
    auto create = reinterpret_cast<Create>(GetProcAddress(loader, "CreateCoreWebView2EnvironmentWithOptions"));
    if (!create) { fail("Invalid WebView2Loader", E_NOINTERFACE); return; }
    HRESULT hr = create(nullptr, dataDirectory.c_str(), nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (FAILED(result) || !environment) { fail("Install Microsoft Edge WebView2 Runtime", result); return S_OK; }
                HRESULT h = environment->CreateCoreWebView2Controller(host,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [](HRESULT result, ICoreWebView2Controller* value) -> HRESULT {
                            if (FAILED(result) || !value) { fail("Create controller", result); return S_OK; }
                            controller = value;
                            HRESULT hr = controller->get_CoreWebView2(&web);
                            if (FAILED(hr) || !web) { fail("Get CoreWebView2", hr); return S_OK; }
                            resizeController();
                            controller->put_IsVisible(IsWindowVisible(host));
                            ComPtr<ICoreWebView2Settings> settings;
                            if (SUCCEEDED(web->get_Settings(&settings))) {
                                settings->put_IsStatusBarEnabled(FALSE);
                            }
                            // Keep target=_blank links inside the panel.
                            EventRegistrationToken token{};
#ifdef ADDWEB_PROBE
                            web->add_NavigationCompleted(Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                [](ICoreWebView2* sender, ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                    BOOL success{}; args->get_IsSuccess(&success);
                                    LPWSTR source{}; sender->get_Source(&source);
                                    std::wofstream log(dataDirectory / L"navigation.txt", std::ios::app);
                                    log << L"success=" << success << L" source=" << (source ? source : L"") << L'\n';
                                    CoTaskMemFree(source);
                                    return S_OK;
                                }).Get(), &token);
#endif
                            web->add_NewWindowRequested(Callback<ICoreWebView2NewWindowRequestedEventHandler>(
                                [](ICoreWebView2*, ICoreWebView2NewWindowRequestedEventArgs* args) -> HRESULT {
                                    LPWSTR uri{};
                                    args->put_Handled(TRUE);
                                    if (SUCCEEDED(args->get_Uri(&uri))) {
                                        if (uri && validUrl(uri)) web->Navigate(uri);
                                        CoTaskMemFree(uri);
                                    }
                                    return S_OK;
                                }).Get(), &token);
                            web->add_ProcessFailed(Callback<ICoreWebView2ProcessFailedEventHandler>(
                                [](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs*) -> HRESULT {
                                    fail("WebView2 process failed; restart client", E_FAIL);
                                    return S_OK;
                                }).Get(), &token);
                            hr = web->Navigate(startUrl.c_str());
                            if (FAILED(hr)) fail("Navigate startup URL", hr);
                            else status.store(2);
                            return S_OK;
                        }).Get());
                if (FAILED(h)) fail("Create controller request", h);
                return S_OK;
            }).Get());
    if (FAILED(hr)) fail("Create environment request", hr);
    // Loader stays loaded for the lifetime of the process and its async callbacks.
}

void update() {
    HWND owner;
    RECT rect;
    bool visible;
    bool reloadConfig;
    std::deque<Request> requests;
    HWND foreground = GetForegroundWindow();
    {
        std::lock_guard<std::mutex> lock(shared.mutex);
        owner = shared.owner;
        rect = shared.bounds;
        reloadConfig = shared.reloadConfig;
        shared.reloadConfig = false;
        // Some clients throttle their game thread while the owned browser has
        // keyboard focus. Do not hide the browser just because UC stops ticking.
        visible = shared.visible && (GetTickCount64() - shared.heartbeat < 1500 || foreground == host);
        if (web) requests.swap(shared.requests);
    }
    if (!IsWindow(owner)) { DestroyWindow(host); return; }
    bool active = foreground == owner || foreground == host || GetAncestor(foreground, GA_ROOTOWNER) == owner;
    visible = visible && active && !IsIconic(owner) && IsWindowVisible(owner);
    POINT origin{0, 0};
    ClientToScreen(owner, &origin);
    RECT client{};
    GetClientRect(owner, &client);
    RECT clipped{};
    visible = visible && IntersectRect(&clipped, &rect, &client);
    RECT destination{origin.x + rect.left, origin.y + rect.top, origin.x + rect.right, origin.y + rect.bottom};
    RECT current{};
    GetWindowRect(host, &current);
    if (!EqualRect(&current, &destination)) {
        SetWindowPos(host, nullptr, destination.left, destination.top, rect.right - rect.left,
            rect.bottom - rect.top, SWP_NOACTIVATE | SWP_NOZORDER);
        resizeController();
    }
    if (visible) {
        HRGN region = CreateRectRgn(clipped.left - rect.left, clipped.top - rect.top,
            clipped.right - rect.left, clipped.bottom - rect.top);
        if (!SetWindowRgn(host, region, FALSE)) DeleteObject(region);
    }
    bool wasVisible = IsWindowVisible(host) != FALSE;
    if (visible != wasVisible) {
        ShowWindow(host, visible ? SW_SHOWNOACTIVATE : SW_HIDE);
        if (controller) controller->put_IsVisible(visible);
    }
    if (visible && !initializing) initializeWeb();
    if (reloadConfig && initializing) {
        startUrl = configUrl();
        if (web) web->Navigate(startUrl.c_str());
#ifdef ADDWEB_PROBE
        std::wofstream log(dataDirectory / L"reopen.txt", std::ios::app);
        log << startUrl << L'\n';
#endif
    }
    for (const auto& request : requests) {
        switch (request.command) {
        case 0: web->Navigate(request.url.c_str()); break;
        case 1: web->GoBack(); break;
        case 2: web->GoForward(); break;
        case 3: web->Reload(); break;
        case 4: web->Navigate(startUrl.c_str()); break;
        }
    }
}

LRESULT CALLBACK windowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
    case WM_TIMER: update(); return 0;
    case WM_SIZE: resizeController(); return 0;
    case WM_SETFOCUS:
        if (controller) controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
        return 0;
    case WM_CLOSE: addweb::Hide(); return 0;
    case WM_PAINT: {
        PAINTSTRUCT ps{};
        HDC dc = BeginPaint(window, &ps);
        RECT rect{}; GetClientRect(window, &rect);
        FillRect(dc, &rect, reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1));
        const wchar_t* text = status.load() < 0 ? L"Browser initialization failed. Install WebView2 Runtime. See %LOCALAPPDATA%\\L2AddWeb log." : L"Starting browser...";
        DrawTextW(dc, text, -1, &rect, DT_CENTER | DT_WORDBREAK);
        EndPaint(window, &ps);
        return 0;
    }
    case WM_DESTROY:
        KillTimer(window, 1);
        if (controller) controller->Close();
        web.Reset(); controller.Reset();
        PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

DWORD WINAPI uiThread(void*) {
    // Do not change process DPI awareness: it belongs to the game. This thread
    // inherits the client's context, matching UC viewport coordinates.
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) { status.store(-2); return 0; }
    WNDCLASSW wc{};
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpfnWndProc = windowProc;
    wc.lpszClassName = L"L2AddWebPanel";
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    RegisterClassW(&wc);
    HWND owner;
    { std::lock_guard<std::mutex> lock(shared.mutex); owner = shared.owner; }
    host = CreateWindowExW(WS_EX_TOOLWINDOW, wc.lpszClassName, L"L2 Browser", WS_POPUP | WS_CLIPCHILDREN,
        0, 0, 880, 530, owner, nullptr, wc.hInstance, nullptr);
    if (host && SetTimer(host, 1, 16, nullptr)) {
        MSG msg{};
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    } else status.store(-3);
    CoUninitialize();
    return 0;
}

BOOL CALLBACK findOwner(HWND window, LPARAM argument) {
    DWORD pid{};
    GetWindowThreadProcessId(window, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(window) || GetWindow(window, GW_OWNER)) return TRUE;
    RECT r{}; GetClientRect(window, &r);
    if (r.right < 320 || r.bottom < 200) return TRUE;
    auto best = reinterpret_cast<HWND*>(argument);
    RECT previous{}; if (*best) GetClientRect(*best, &previous);
    if (r.right * r.bottom > previous.right * previous.bottom) *best = window;
    return TRUE;
}
}

namespace addweb {
bool Show() {
    HWND owner{};
    EnumWindows(findOwner, reinterpret_cast<LPARAM>(&owner));
    if (!owner) { status.store(-4); return false; }
    {
        std::lock_guard<std::mutex> lock(shared.mutex);
        shared.owner = owner;
        shared.visible = true;
        shared.reloadConfig = true;
        shared.heartbeat = GetTickCount64();
    }
    if (!started.exchange(true)) {
        status.store(1);
        HANDLE thread = CreateThread(nullptr, 0, uiThread, nullptr, 0, nullptr);
        if (!thread) { started.store(false); status.store(-5); return false; }
        CloseHandle(thread);
    }
    return status.load() >= 0;
}
void Hide() { std::lock_guard<std::mutex> lock(shared.mutex); shared.visible = false; }
void Bounds(std::int32_t x, std::int32_t y, std::int32_t width, std::int32_t height) {
    if (width < 1 || height < 1 || width > 16384 || height > 16384 || x < -65536 || x > 65536 || y < -65536 || y > 65536) return;
    std::lock_guard<std::mutex> lock(shared.mutex);
    shared.bounds = {x, y, x + width, y + height};
    shared.heartbeat = GetTickCount64();
}
void Navigate(std::wstring url) {
    url = trim(url);
    if (!validUrl(url) || url.size() > 8192) return;
    std::lock_guard<std::mutex> lock(shared.mutex);
    if (shared.requests.size() < 32) shared.requests.push_back({0, std::move(url)});
}
void Command(std::int32_t command) {
    if (command < 1 || command > 4) return;
    std::lock_guard<std::mutex> lock(shared.mutex);
    if (shared.requests.size() < 32) shared.requests.push_back({command, {}});
}
std::int32_t Status() { return status.load(); }
#ifdef ADDWEB_PROBE
std::wstring ProbeConfig() { moduleDirectory = modulePath(); return configUrl(); }
#endif
}
