#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include "game_input.h"
#include "web_frames.h"

namespace {
HHOOK wheelHook = nullptr;
bool wheelHover = false;
int surfaceLeft = 0, surfaceTop = 0, surfaceWidth = 0, surfaceHeight = 0;
int wheelRemainder = 0, wheelCount = 0;
bool gameForeground() {
    DWORD pid = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &pid);
    return pid == GetCurrentProcessId();
}
LRESULT CALLBACK mouseHook(int code, WPARAM message, LPARAM data) {
    if (code == HC_ACTION && message == WM_MOUSEWHEEL && wheelHover && gameForeground()) {
        const auto* event = reinterpret_cast<const MOUSEHOOKSTRUCTEX*>(data);
        POINT point = event->pt;
        if (ScreenToClient(GetForegroundWindow(), &point) &&
            point.x >= surfaceLeft && point.y >= surfaceTop &&
            point.x < surfaceLeft + surfaceWidth && point.y < surfaceTop + surfaceHeight) {
            wheelRemainder += static_cast<short>(HIWORD(event->mouseData));
            int modifiers = (GetKeyState(VK_SHIFT) < 0 ? 8 : 0) |
                (GetKeyState(VK_CONTROL) < 0 ? 2 : 0) | (GetKeyState(VK_MENU) < 0 ? 1 : 0);
            while (wheelRemainder >= WHEEL_DELTA || wheelRemainder <= -WHEEL_DELTA) {
                bool up = wheelRemainder > 0;
                webframes::Mouse(up ? 5 : 6, (point.x-surfaceLeft)*512/surfaceWidth,
                    (point.y-surfaceTop)*512/surfaceHeight, modifiers);
                wheelRemainder += up ? -WHEEL_DELTA : WHEEL_DELTA;
                wheelCount = (wheelCount + 1) % 1000000;
            }
            return 1;
        }
    }
    return CallNextHookEx(wheelHook, code, message, data);
}
}

bool gameinput::LeftPressed() {
    return gameForeground() && (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
}
std::int32_t gameinput::Poll(bool active, bool hover, std::int32_t left, std::int32_t top,
                            std::int32_t width, std::int32_t height) {
    active = active && gameForeground() && width > 0 && height > 0;
    wheelHover = active && hover;
    surfaceLeft = left; surfaceTop = top; surfaceWidth = width; surfaceHeight = height;
    if (active && !wheelHook)
        wheelHook = SetWindowsHookExW(WH_MOUSE, mouseHook, nullptr, GetCurrentThreadId());
    if (!active) {
        if (wheelHook) UnhookWindowsHookEx(wheelHook);
        wheelHook = nullptr;
        wheelRemainder = 0;
    }
    return wheelCount * 2 + (wheelHook ? 1 : 0);
}

bool gameinput::Mouse(std::int32_t kind, std::int32_t left, std::int32_t top,
                     std::int32_t width, std::int32_t height, std::int32_t modifiers) {
    if (width < 1 || height < 1 || width > 16384 || height > 16384) return false;
    HWND game = GetForegroundWindow();
    DWORD pid = 0;
    GetWindowThreadProcessId(game, &pid);
    if (!game || pid != GetCurrentProcessId()) return false;
    POINT point{};
    if (!GetCursorPos(&point) || !ScreenToClient(game, &point)) return false;
    int x = point.x-left, y = point.y-top;
    if (x < 0 || y < 0 || x >= width || y >= height) return false;
    webframes::Mouse(kind, x*512/width, y*512/height, modifiers);
    return true;
}

void gameinput::Key(std::int32_t key, bool down, std::int32_t modifiers) {
    // Verified EInputKey values match VK codes for these keys in HF Engine.u.
    if (key < 8 || key > 222 || key == 185 || (key >= 200 && key <= 218)) return;
    std::wstring text;
    if (down && !(modifiers & 7)) {
        BYTE state[256]{};
        GetKeyboardState(state);
        state[VK_SHIFT] = (modifiers & 8) ? 0x80 : 0;
        state[VK_CONTROL] = state[VK_MENU] = 0;
        wchar_t chars[16]{};
        HKL layout = GetKeyboardLayout(0);
        int count = ToUnicodeEx(key, MapVirtualKeyExW(key, MAPVK_VK_TO_VSC, layout),
            state, chars, 16, 4, layout); // don't mutate the game's dead-key state
        if (count > 0 && chars[0] >= 32) text.assign(chars, count);
        if (key == VK_RETURN) text = L"\r";
    }
    webframes::Key(key, down, modifiers, std::move(text));
}
