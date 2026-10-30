#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <windows.h>
#include <cstdio>
#include <fstream>
#include <filesystem>
#include <vector>
#include <thread>
#include <atomic>
#include <string>
#include <mutex>
#include "game_input.h"
#include "web_frames.h"

namespace {
std::filesystem::path directory;
std::mutex eventMutex;
std::vector<std::string> events;
bool waitEvent(const std::string& text) {
    for (unsigned i = 0; i < 100; ++i) {
        {
            std::lock_guard<std::mutex> lock(eventMutex);
            for (const auto& event : events) if (event.find(text) != std::string::npos) return true;
        }
        Sleep(50);
    }
    std::printf("FAIL missing browser event: %s\n", text.c_str());
    return false;
}
bool waitColor(unsigned color, unsigned timeout = 30000) {
    std::vector<unsigned> pixels(512 * 512);
    ULONGLONG until = GetTickCount64() + timeout;
    while (GetTickCount64() < until) {
        if (webframes::Copy(pixels.data(), static_cast<unsigned>(pixels.size()*4))) {
            unsigned actual = pixels[100*512+100];
            unsigned r = (actual >> 16) & 255, g = (actual >> 8) & 255, b = actual & 255;
            // CapturePreview can apply the machine's monitor color profile.
            // Verify channel order and dominant primary, not exact sRGB bytes.
            if ((actual >> 24) == 255 && ((color == 0xffff0000 && r > 180 && g < 100 && b < 100) ||
                (color == 0xff00ff00 && g > 180 && r < 150 && b < 150))) return true;
        }
        if (webframes::Status() < 0) break;
        Sleep(100);
    }
    std::printf("FAIL color %08x actual=%08x state=%d\n", color, pixels[100*512+100], webframes::Status());
    std::ofstream dump(directory / L"failed-frame.bgra", std::ios::binary);
    dump.write(reinterpret_cast<const char*>(pixels.data()), pixels.size()*4);
    return false;
}
void config(const std::string& value) {
    std::ofstream file(directory / L"options.config", std::ios::binary);
    file << "{\"browser\":{\"startPage\":\"" << value << "\"}}\n";
}
}

int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    wchar_t path[32768]{};
    GetModuleFileNameW(nullptr, path, 32768);
    directory = std::filesystem::path(path).parent_path();
    auto configPath = directory / L"options.config";
    if (std::filesystem::exists(configPath)) {
        std::puts("Probe directory already has options.config; use an empty test directory"); return 2;
    }
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2,2), &data)) return 3;
    SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) || listen(listener, 8)) return 4;
    int size = sizeof(address);
    getsockname(listener, reinterpret_cast<sockaddr*>(&address), &size);
    std::atomic<bool> stop{false};
    std::thread server([&] {
        while (!stop.load()) {
            fd_set reads; FD_ZERO(&reads); FD_SET(listener, &reads);
            timeval timeout{0, 200000};
            if (select(0, &reads, nullptr, nullptr, &timeout) <= 0) continue;
            SOCKET client = accept(listener, nullptr, nullptr);
            if (client == INVALID_SOCKET) continue;
            DWORD ms = 1000;
            setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));
            char request[4096]{};
            int length = recv(client, request, sizeof(request)-1, 0);
            if (length > 0) {
                if (std::string(request).find("GET /event?") != std::string::npos) {
                    std::lock_guard<std::mutex> lock(eventMutex);
                    events.emplace_back(request);
                }
                bool green = std::string(request).find("GET /green") != std::string::npos;
                std::string html = "<!doctype html><style>body{margin:0;background:";
                html += green ? "#00ff00" : "#ff0000";
                html += ";min-height:1800px}#anim{position:absolute;top:300px;left:300px;width:80px;height:80px;background:#0000ff}</style>"
                    "<div id=anim></div><button style='position:absolute;left:20px;top:200px;width:100px;height:40px' "
                    "onclick=\"fetch('/event?click='+event.isTrusted)\">Click</button>"
                    "<input id=entry style='position:absolute;left:20px;top:250px;width:200px;height:30px' "
                    "oninput=\"fetch('/event?value='+encodeURIComponent(this.value))\">"
                    "<input type=range value=0 style='position:absolute;left:20px;top:150px;width:200px;height:20px' "
                    "oninput=\"fetch('/event?drag='+(this.value>80))\">"
                    "<button style='position:absolute;left:20px;top:350px;width:160px;height:30px' "
                    "onclick=\"window.open('/red','_blank')\">Popup</button>"
                    "<button style='position:absolute;left:20px;top:400px;width:160px;height:30px' "
                    "onclick=\"alert('No desktop dialog');fetch('/event?dialog=returned')\">Dialog</button>"
                    "<script>addEventListener('keydown',e=>fetch('/event?key='+e.key+'&trusted='+e.isTrusted));"
                    "addEventListener('scroll',()=>fetch('/event?scroll='+scrollY));"
                    "let tick=0;function animate(){document.getElementById('anim').style.background="
                    "'rgb('+(tick++%255)+',0,255)';requestAnimationFrame(animate)}animate()</script>";
                std::string response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: "
                    + std::to_string(html.size()) + "\r\n\r\n" + html;
                size_t sent = 0;
                while (sent < response.size()) {
                    int n = send(client, response.data()+sent, static_cast<int>(response.size()-sent), 0);
                    if (n <= 0) break;
                    sent += n;
                }
            }
            closesocket(client);
        }
    });
    std::string base = "http://127.0.0.1:" + std::to_string(ntohs(address.sin_port));
    config(base + "/red");
    bool ok = webframes::Open() && waitColor(0xffff0000);
    if (ok) std::puts("PASS offscreen WebView2 -> WGC/D3D11 -> BGRA red frame (no PNG)");
    std::vector<unsigned> pixels(512*512);
    unsigned first = 0;
    bool changed = false;
    if (ok && webframes::Copy(pixels.data(), static_cast<unsigned>(pixels.size()*4))) {
        first = pixels[320*512+320];
        for (unsigned i = 0; i < 40; ++i) {
            Sleep(100);
            if (webframes::Copy(pixels.data(), static_cast<unsigned>(pixels.size()*4)) &&
                pixels[320*512+320] != first) { changed = true; break; }
        }
    }
    ok = ok && changed;
    if (ok) std::puts("PASS animated HTML produces changing browser pixels");
    if (ok) {
        unsigned captured = 0;
        webframes::ResetPerformance();
        ULONGLONG start = GetTickCount64();
        while (GetTickCount64() - start < 8000) {
            if (webframes::CopyFresh(pixels.data(), static_cast<unsigned>(pixels.size()*4))) ++captured;
            Sleep(1);
        }
        std::printf("METRIC fresh browser frames: %.1f fps over 8 seconds (host only)\n", captured / 8.0);
        std::ofstream(directory / L"benchmark.json") << webframes::Performance();
        ok = captured > 0;
    }
    HWND host = FindWindowW(L"L2TextureCaptureHost", nullptr);
    RECT rect{}, overlap{}, desktop{GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN), 0, 0};
    desktop.right = desktop.left + GetSystemMetrics(SM_CXVIRTUALSCREEN);
    desktop.bottom = desktop.top + GetSystemMetrics(SM_CYVIRTUALSCREEN);
    ok = ok && host && GetWindowRect(host, &rect) && !IntersectRect(&overlap, &rect, &desktop);
    if (ok) std::puts("PASS browser host lies outside virtual desktop");
    webframes::Hide();
    ok = ok && !webframes::Copy(pixels.data(), static_cast<unsigned>(pixels.size()*4));
    config(base + "/green");
    ok = ok && webframes::Open() && waitColor(0xff00ff00);
    if (ok) std::puts("PASS hide/reopen rereads config and produces green frame");
    if (ok) {
        std::wstring url(base.begin(), base.end());
        webframes::Navigate(url + L"/red");
        ok = waitColor(0xffff0000);
        if (ok) std::puts("PASS navigation command changes captured page");
    }
    if (ok) {
        webframes::Mouse(0, 50, 220, 0);
        webframes::Mouse(1, 50, 220, 0); webframes::Mouse(2, 50, 220, 0);
        ok = waitEvent("click=true");
        if (ok) std::puts("PASS browser receives trusted mouse click");
    }
    if (ok) {
        webframes::Mouse(1, 50, 260, 0); webframes::Mouse(2, 50, 260, 0);
        webframes::Key('A', true, 0, L"a"); webframes::Key('A', false, 0, L"");
        webframes::Key('Z', true, 0, L"\u044f"); webframes::Key('Z', false, 0, L"");
        ok = waitEvent("value=a%D1%8F");
        webframes::Key(VK_LEFT, true, 0, L""); webframes::Key(VK_LEFT, false, 0, L"");
        webframes::Key(VK_BACK, true, 0, L""); webframes::Key(VK_BACK, false, 0, L"");
        ok = ok && waitEvent("key=ArrowLeft&trusted=true") && waitEvent("value=%D1%8F");
        if (ok) std::puts("PASS Latin/Cyrillic text, ArrowLeft and Backspace edit real browser input");
    }
    if (ok) {
        webframes::Text(L"test\u0436");
        ok = waitEvent("value=test%D0%B6%D1%8F");
        if (ok) std::puts("PASS EditBox text bridge inserts Unicode exactly once");
    }
    if (ok) {
        HKL previous = GetKeyboardLayout(0);
        HKL russian = LoadKeyboardLayoutW(L"00000419", 0);
        ok = russian && ActivateKeyboardLayout(russian, 0);
        if (ok) {
            webframes::Key(VK_END, true, 0, L"");
            webframes::Key(VK_END, false, 0, L"");
            gameinput::Key('F', true, 0);
            gameinput::Key('F', false, 0);
            ok = waitEvent("value=test%D0%B6%D1%8F%D0%B0");
        }
        ActivateKeyboardLayout(previous, 0);
        if (ok) std::puts("PASS Windows Russian layout -> gameinput Key -> Cyrillic browser text");
    }
    if (ok) {
        webframes::Focus(false);
        webframes::Text(L"BLOCKED");
        webframes::Key('B', true, 0, L"b"); webframes::Key('B', false, 0, L"");
        Sleep(500);
        {
            std::lock_guard<std::mutex> lock(eventMutex);
            for (const auto& event : events)
                if (event.find("key=b&") != std::string::npos || event.find("BLOCKED") != std::string::npos) ok = false;
        }
        if (ok) std::puts("PASS keyboard blocked after browser focus loss");
        webframes::Focus(true);
        webframes::Mouse(1, 30, 160, 0);
        webframes::Mouse(0, 200, 160, 0);
        webframes::Mouse(2, 200, 160, 0);
        ok = ok && waitEvent("drag=true");
        if (ok) std::puts("PASS held left button drags browser range control");
        webframes::Focus(false);
        webframes::Mouse(6, 250, 400, 0);
        ok = ok && waitEvent("scroll=");
        if (ok) std::puts("PASS wheel scrolls real browser page without keyboard focus");
    }
    if (ok) {
        webframes::Hide();
        for (int i = 0; i < 100 && webframes::MutedStatus() != 1; ++i) Sleep(20);
        ok = webframes::MutedStatus() == 1;
        webframes::Focus(true); // hidden UI must not be able to reacquire input
        webframes::Key('Q', true, 0, L"q");
        webframes::Key('Q', false, 0, L"");
        ok = ok && !webframes::Copy(pixels.data(), static_cast<unsigned>(pixels.size()*4));
        webframes::Resume();
        for (int i = 0; i < 100 && webframes::MutedStatus() != 0; ++i) Sleep(20);
        ok = ok && webframes::MutedStatus() == 0;
        webframes::Key('Q', true, 0, L"q"); // restore doesn't grab keyboard
        webframes::Key('Q', false, 0, L"");
        Sleep(300);
        {
            std::lock_guard<std::mutex> lock(eventMutex);
            for (const auto& event : events) if (event.find("key=q&") != std::string::npos) ok = false;
        }
        webframes::Focus(true);
        webframes::Key('R', true, 0, L"r");
        webframes::Key('R', false, 0, L"");
        ok = ok && waitEvent("key=r&");
        if (ok) std::puts("PASS minimize/resume preserves page and blocks keyboard until refocused");
        webframes::Close();
        Sleep(500);
        ok = ok && webframes::MutedStatus() == 1;
        webframes::Resume();
        webframes::Focus(true);
        webframes::Key('C', true, 0, L"c");
        webframes::Key('C', false, 0, L"");
        Sleep(300);
        {
            std::lock_guard<std::mutex> lock(eventMutex);
            for (const auto& event : events) if (event.find("key=c&") != std::string::npos) ok = false;
        }
        webframes::Open();
        ok = ok && waitColor(0xff00ff00);
        if (ok) std::puts("PASS state close unloads old page; next open loads configured home");
    }
    if (ok) {
        std::puts("PASS WebView2 reports muted on hide/close and unmuted on resume");
        webframes::Mouse(1, 70, 365, 0);
        webframes::Mouse(2, 70, 365, 0);
        ok = waitColor(0xffff0000);
        if (ok) std::puts("PASS window.open navigates existing captured WebView instead of a new window");
        webframes::Mouse(1, 70, 415, 0);
        webframes::Mouse(2, 70, 415, 0);
        ok = ok && waitEvent("dialog=returned");
        if (ok) std::puts("PASS JavaScript alert returns without desktop dialog");
    }
    webframes::Hide();
    webframes::Shutdown();
    stop.store(true);
    server.join();
    closesocket(listener);
    WSACleanup();
    std::filesystem::remove(configPath);
    std::ofstream report(directory / L"result.json");
    report << "{\"offscreen_capture_and_input_tests_passed\":" << (ok ? "true" : "false") << ",\"game_tested\":false}\n";
    return ok ? 0 : 1;
}
