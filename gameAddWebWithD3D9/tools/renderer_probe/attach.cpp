#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cwchar>

int wmain(int argc, wchar_t** argv) {
    if (argc != 3) { std::puts("renderer_attach PID absolute-probe-DLL"); return 2; }
    DWORD pid = wcstoul(argv[1], nullptr, 10);
    wchar_t path[32768];
    if (!GetFullPathNameW(argv[2], 32768, path, nullptr) || GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 3;
    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ, FALSE, pid);
    if (!process) { std::printf("OpenProcess: %lu\n", GetLastError()); return 4; }
    SIZE_T size = (wcslen(path) + 1) * sizeof(wchar_t);
    void* remote = VirtualAllocEx(process, nullptr, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote || !WriteProcessMemory(process, remote, path, size, nullptr)) { CloseHandle(process); return 5; }
    auto load = reinterpret_cast<LPTHREAD_START_ROUTINE>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW"));
    HANDLE thread = CreateRemoteThread(process, nullptr, 0, load, remote, 0, nullptr);
    if (!thread) { VirtualFreeEx(process, remote, 0, MEM_RELEASE); CloseHandle(process); return 6; }
    DWORD wait = WaitForSingleObject(thread, 30000), result = 0;
    if (wait == WAIT_OBJECT_0) {
        GetExitCodeThread(thread, &result);
        VirtualFreeEx(process, remote, 0, MEM_RELEASE);
    }
    CloseHandle(thread); CloseHandle(process);
    std::printf("LoadLibrary result: %lu\n", result);
    return result ? 0 : 7;
}
