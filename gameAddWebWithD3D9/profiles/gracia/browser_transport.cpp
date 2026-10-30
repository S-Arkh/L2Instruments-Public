#include "browser_ipc.h"
#include "web_frames.h"
#include <objbase.h>
#include <filesystem>
#include <mutex>
#include <cstring>
#include <string>

namespace {
std::mutex local;
HANDLE mapping = nullptr, ipcMutex = nullptr, process = nullptr, job = nullptr;
browseripc::Shared* shared = nullptr;
unsigned long long consumed = 0;
int failure = 0;
bool visible = false;
void cleanup() {
    // Closing the job terminates the helper and its WebView children.
    if (job) CloseHandle(job);
    if (process) CloseHandle(process);
    if (shared) UnmapViewOfFile(shared);
    if (ipcMutex) CloseHandle(ipcMutex);
    if (mapping) CloseHandle(mapping);
    job = process = ipcMutex = mapping = nullptr; shared = nullptr; consumed = 0;
}
bool alive() { return process && WaitForSingleObject(process, 0) == WAIT_TIMEOUT; }
bool start() {
    if (alive()) return true;
    cleanup();
    HMODULE module{};
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&failure), &module);
    wchar_t path[32768]{}; GetModuleFileNameW(module, path, 32768);
    auto directory = std::filesystem::path(path).parent_path();
    auto exe = directory / L"GraciaBrowserHost.exe";
    GUID guid{};
    if (FAILED(CoCreateGuid(&guid))) { failure = -30; return false; }
    wchar_t guidText[64]{}; StringFromGUID2(guid, guidText, 64);
    std::wstring name = std::wstring(L"Local\\GraciaBrowser-") + guidText;
    mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(browseripc::Shared), name.c_str());
    ipcMutex = CreateMutexW(nullptr, FALSE, (name + L"-mutex").c_str());
    if (mapping) shared = static_cast<browseripc::Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(browseripc::Shared)));
    if (!shared || !ipcMutex) { failure = -30; cleanup(); return false; }
    memset(shared, 0, sizeof(*shared));
    shared->magic = browseripc::Magic; shared->status = 1; shared->muted = -1;
    strcpy_s(shared->performance, "{}");
    job = CreateJobObjectW(nullptr, nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits))) {
        failure = -30; cleanup(); return false;
    }
    std::wstring command = L"\"" + exe.wstring() + L"\" \"" + name + L"\" " + std::to_wstring(GetCurrentProcessId());
    STARTUPINFOW startup{}; startup.cb = sizeof(startup); PROCESS_INFORMATION child{};
    if (!CreateProcessW(exe.c_str(), command.data(), nullptr, nullptr, FALSE, CREATE_SUSPENDED | CREATE_NO_WINDOW,
        nullptr, directory.c_str(), &startup, &child)) { failure = -30; cleanup(); return false; }
    process = child.hProcess;
    if (!AssignProcessToJobObject(job, process) || ResumeThread(child.hThread) == static_cast<DWORD>(-1)) {
        TerminateProcess(process, 1); CloseHandle(child.hThread); failure = -30; cleanup(); return false;
    }
    CloseHandle(child.hThread); failure = 0;
    return true;
}
bool send(browseripc::Operation operation, int a=0, int b=0, int c=0, int d=0, const std::wstring& text={}) {
    std::lock_guard<std::mutex> guard(local);
    if (operation == browseripc::Open && !start()) return false;
    if (!alive()) { if (process) failure = -31; return false; }
    browseripc::Lock lock(ipcMutex);
    if (!lock) { failure = -32; return false; }
    unsigned next = (shared->write + 1) % browseripc::QueueSize;
    if (next == shared->read || text.size() > 8192) { failure = -32; return false; }
    auto& r = shared->queue[shared->write];
    if (operation == browseripc::Hide || operation == browseripc::Close) visible = false;
    if (operation == browseripc::Open || operation == browseripc::Resume) visible = true;
    r.operation=operation; r.a=a; r.b=b; r.c=c; r.d=d;
    memcpy(r.text,text.c_str(),(text.size()+1)*sizeof(wchar_t));
    // Never expose the preceding page after reopening or state close.
    if (operation == browseripc::Open || operation == browseripc::Close) {
        ++shared->generation;
        shared->sequence = 0; consumed = 0; shared->status = operation == browseripc::Open ? 1 : 0;
    }
    shared->write = next;
    return true;
}
bool copy(void* destination, unsigned bytes, bool fresh) {
    std::lock_guard<std::mutex> guard(local);
    if (!destination || bytes != browseripc::PixelBytes || !visible || !alive()) return false;
    browseripc::Lock lock(ipcMutex, 5);
    if (!lock || !shared->sequence || (fresh && consumed == shared->sequence)) return false;
    memcpy(destination,shared->pixels,bytes); consumed = shared->sequence; return true;
}
}
bool webframes::Open() { return send(browseripc::Open); }
void webframes::Hide() { send(browseripc::Hide); }
void webframes::Resume() { send(browseripc::Resume); }
void webframes::Close() { send(browseripc::Close); }
void webframes::Navigate(std::wstring url) { send(browseripc::Navigate,0,0,0,0,url); }
void webframes::Command(std::int32_t c) { send(browseripc::Command,c); }
void webframes::Mouse(std::int32_t k,std::int32_t x,std::int32_t y,std::int32_t m) { send(browseripc::Mouse,k,x,y,m); }
void webframes::Key(std::int32_t k,bool down,std::int32_t m,std::wstring text) { send(browseripc::Key,k,down,m,0,text); }
void webframes::Focus(bool active) { send(browseripc::Focus,active); }
void webframes::Text(std::wstring text) { send(browseripc::Text,0,0,0,0,text); }
std::int32_t webframes::Status() {
    std::lock_guard<std::mutex> guard(local);
    if (failure) return failure;
    if (!process) return 0;
    if (!alive()) return -31;
    browseripc::Lock lock(ipcMutex,5); return lock ? shared->status : 1;
}
std::int32_t webframes::MutedStatus() {
    std::lock_guard<std::mutex> guard(local);
    if (!alive()) return -1;
    browseripc::Lock lock(ipcMutex,5); return lock ? shared->muted : -1;
}
bool webframes::Copy(void* destination,unsigned bytes) { return copy(destination,bytes,false); }
bool webframes::CopyFresh(void* destination,unsigned bytes) { return copy(destination,bytes,true); }
void webframes::ResetPerformance() { send(browseripc::Reset); }
std::string webframes::Performance() {
    std::lock_guard<std::mutex> guard(local);
    if (!alive()) return "{}";
    browseripc::Lock lock(ipcMutex,5); return lock ? shared->performance : "{}";
}
void webframes::Shutdown() { std::lock_guard<std::mutex> guard(local); cleanup(); }
void webframes::AbandonOnProcessExit() {
    // No locks, waits or COM calls under the loader lock. Other handles are
    // reclaimed by the OS; this closes the kill-on-close job immediately.
    if (job) { CloseHandle(job); job = nullptr; }
}
