#include "browser_ipc.h"
#include "web_frames.h"
#include <cstring>
#include <vector>
#include <string>

int wmain(int argc, wchar_t** argv) {
    if (argc != 3) return 2;
    DWORD parentId = wcstoul(argv[2], nullptr, 10);
    HANDLE parent = OpenProcess(SYNCHRONIZE, FALSE, parentId);
    HANDLE mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, argv[1]);
    std::wstring mutexName = std::wstring(argv[1]) + L"-mutex";
    HANDLE mutex = OpenMutexW(SYNCHRONIZE | MUTEX_MODIFY_STATE, FALSE, mutexName.c_str());
    if (!parent || !mapping || !mutex) return 3;
    auto shared = static_cast<browseripc::Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(browseripc::Shared)));
    if (!shared || shared->magic != browseripc::Magic) return 4;
    std::vector<unsigned char> pixels(browseripc::PixelBytes);
    ULONGLONG lastPerformance = 0;
    while (WaitForSingleObject(parent, 10) == WAIT_TIMEOUT) {
        std::vector<browseripc::Request> requests;
        unsigned generation = 0;
        {
            browseripc::Lock lock(mutex);
            if (!lock) continue;
            generation = shared->generation;
            while (shared->read != shared->write) {
                requests.push_back(shared->queue[shared->read]);
                shared->read = (shared->read + 1) % browseripc::QueueSize;
            }
        }
        for (auto& r : requests) {
            r.text[8192] = 0;
            switch (r.operation) {
            case browseripc::Open: webframes::Open(); break;
            case browseripc::Hide: webframes::Hide(); break;
            case browseripc::Resume: webframes::Resume(); break;
            case browseripc::Close: webframes::Close(); break;
            case browseripc::Navigate: webframes::Navigate(r.text); break;
            case browseripc::Command: webframes::Command(r.a); break;
            case browseripc::Mouse: webframes::Mouse(r.a,r.b,r.c,r.d); break;
            case browseripc::Key: webframes::Key(r.a,r.b!=0,r.c,r.text); break;
            case browseripc::Focus: webframes::Focus(r.a!=0); break;
            case browseripc::Text: webframes::Text(r.text); break;
            case browseripc::Reset: webframes::ResetPerformance(); break;
            }
        }
        bool fresh = webframes::CopyFresh(pixels.data(), browseripc::PixelBytes);
        bool report = GetTickCount64() - lastPerformance >= 1000;
        auto performance = report ? webframes::Performance() : std::string{};
        browseripc::Lock lock(mutex);
        if (!lock) continue;
        if (generation != shared->generation) continue;
        shared->status = webframes::Status();
        shared->muted = webframes::MutedStatus();
        if (fresh) {
            memcpy(shared->pixels, pixels.data(), pixels.size());
            ++shared->sequence;
        }
        if (report) {
            strncpy_s(shared->performance, performance.c_str(), _TRUNCATE);
            lastPerformance = GetTickCount64();
        }
    }
    // The job also terminates this process if the game exits abruptly.
    webframes::Shutdown();
    UnmapViewOfFile(shared);
    CloseHandle(mutex); CloseHandle(mapping); CloseHandle(parent);
    return 0;
}
