#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>

namespace browseripc {
constexpr unsigned Magic = 0x47574232;
constexpr unsigned PixelBytes = 512 * 512 * 4;
constexpr unsigned QueueSize = 128;
enum Operation { Open, Hide, Resume, Close, Navigate, Command, Mouse, Key, Focus, Text, Reset };
struct Request {
    Operation operation;
    int a, b, c, d;
    wchar_t text[8193];
};
struct Shared {
    unsigned magic;
    unsigned read, write;
    unsigned generation;
    int status, muted;
    unsigned long long sequence;
    Request queue[QueueSize];
    char performance[2048];
    unsigned char pixels[PixelBytes];
};
class Lock {
    HANDLE mutex;
    bool acquired;
public:
    explicit Lock(HANDLE handle, DWORD timeout = 50) : mutex(handle), acquired(false) {
        DWORD result = WaitForSingleObject(handle, timeout);
        acquired = result == WAIT_OBJECT_0 || result == WAIT_ABANDONED;
    }
    ~Lock() { if (acquired) ReleaseMutex(mutex); }
    explicit operator bool() const { return acquired; }
};
}
