#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdlib>
#include <cstring>
#include "client_abi.h"
#include "client_profile.h"
#include "extension_api.h"

#ifdef _MSC_VER
#define L2_EXPORT
#else
#define L2_EXPORT __attribute__((dllexport))
#endif

namespace {
l2client::Step step;
l2client::Native debugInfo;
l2client::ThrowError throwError;
l2client::StringDestroy destroyString;
l2client::StringAssign assignString;
HMODULE installedCore;
DWORD lastStatus;

BOOL fail(DWORD status, const char* message) {
    lastStatus = status;
    OutputDebugStringA(message);
    SetLastError(status);
    return FALSE;
}

[[noreturn]] void argumentError() {
    throwError(L"extensionL2: invalid native parameter stream");
    std::abort();
}

template<class T> T api(HMODULE module, const char* name) {
    return reinterpret_cast<T>(GetProcAddress(module, name));
}
}

void l2ext::readArgument(l2client::FramePrefix* frame, void* output) {
    if (!frame || !frame->code || *frame->code == 0x16) argumentError();
    step(frame, frame->object, output);
}

std::wstring l2ext::readString(l2client::FramePrefix* frame) {
    struct Temporary {
        l2client::StringValue value{};
        ~Temporary() { destroyString(&value); }
    } temporary;
    readArgument(frame, &temporary.value);
    const auto& value = temporary.value;
    return value.data && value.count > 0 ? std::wstring(value.data, value.count - 1) : std::wstring();
}

void l2ext::writeString(void* result, const std::wstring& value) {
    if (result) assignString(static_cast<l2client::StringValue*>(result), value.c_str());
}

void l2ext::finishArguments(void* self, l2client::FramePrefix* frame) {
    if (!frame || !frame->code || *frame->code != 0x16) argumentError();
    ++frame->code;
    if (*frame->code == 0x42) {
        ++frame->code;
        debugInfo(self, frame, nullptr);
    }
}

[[noreturn]] void l2ext::functionFailed() {
    throwError(L"extensionL2: C++ exception in a native function");
    std::abort();
}

// Call after Core's original process-attach entry point has completed, before
// loading ExtensionL2.u or executing its calls. Install once on the startup thread.
extern "C" L2_EXPORT BOOL WINAPI ExtensionL2Attach(HMODULE core) {
    if (!core) return fail(ERROR_MOD_NOT_FOUND, "ExtensionL2: Core.dll is not loaded\n");
    const auto base = reinterpret_cast<std::uintptr_t>(core);
    auto table = api<l2client::Native*>(core, l2client::TableExport);
    auto registerNative = api<l2client::RegisterNative>(core, l2client::RegisterExport);
    auto evaluate = api<l2client::Step>(core, l2client::StepExport);
    auto undefined = api<l2client::Native>(core, l2client::UndefinedExport);
    const l2client::CoreProfile* profile = nullptr;
    for (const auto& candidate : l2client::CoreProfiles) {
        if (reinterpret_cast<std::uintptr_t>(table) == base + candidate.tableRva &&
            reinterpret_cast<std::uintptr_t>(registerNative) == base + candidate.registerRva &&
            reinterpret_cast<std::uintptr_t>(evaluate) == base + candidate.stepRva &&
            reinterpret_cast<std::uintptr_t>(undefined) == base + candidate.undefinedRva) {
            profile = &candidate;
            break;
        }
    }
    if (!profile) return fail(ERROR_BAD_EXE_FORMAT, "ExtensionL2: unsupported Core.dll ABI\n");
    if (std::memcmp(reinterpret_cast<const void*>(evaluate), l2client::StepPrefix,
                    sizeof(l2client::StepPrefix)) != 0)
        return fail(ERROR_BAD_EXE_FORMAT, "ExtensionL2: FFrame::Step code mismatch\n");
    std::size_t count = 0;
    const auto* items = l2ext::bindings(count);
    if (!items || !count || count > l2client::NativeTableSize)
        return fail(ERROR_INVALID_DATA, "extensionL2: invalid binding list\n");
    // Preflight the complete list before changing slots. No package audit.
    for (std::size_t i = 0; i < count; ++i) {
        const auto& binding = items[i];
        if (binding.info.index < 0x100 || binding.info.index >= l2client::NativeTableSize ||
            !binding.handler || !binding.info.name || !*binding.info.name ||
            binding.info.argumentCount > l2ext::MaxArguments)
            return fail(ERROR_INVALID_DATA, "extensionL2: invalid native descriptor\n");
        for (std::size_t j = 0; j < i; ++j) {
            if (binding.info.index == items[j].info.index || !_stricmp(binding.info.name, items[j].info.name))
                return fail(ERROR_DUP_NAME, "extensionL2: duplicate index or UC name\n");
        }
        const auto current = table[binding.info.index];
        if (!current) return fail(ERROR_NOT_READY, "extensionL2: Core table is not initialized\n");
        if (current != undefined && !(installedCore == core && current == binding.handler))
            return fail(ERROR_ALREADY_EXISTS, "extensionL2: a requested native slot is occupied\n");
    }
    step = evaluate;
    debugInfo = api<l2client::Native>(core, "?execDebugInfo@UObject@@QAEXAAUFFrame@@QAX@Z");
    throwError = api<l2client::ThrowError>(core, "?appThrowf@@YAXPB_WZZ");
    destroyString = api<l2client::StringDestroy>(core, "??1FString@@QAE@XZ");
    assignString = api<l2client::StringAssign>(core, "??4FString@@QAEAAV0@PB_W@Z");
    if (!debugInfo || !throwError || !destroyString || !assignString)
        return fail(ERROR_PROC_NOT_FOUND, "ExtensionL2: required Core export is missing\n");
    for (std::size_t i = 0; i < count; ++i) {
        const auto& binding = items[i];
        if (table[binding.info.index] == binding.handler) continue;
        registerNative(binding.info.index, &binding.handler);
        if (table[binding.info.index] != binding.handler)
            return fail(ERROR_INVALID_DATA, "extensionL2: native registration failed\n");
    }
    installedCore = core;
    lastStatus = ERROR_SUCCESS;
    OutputDebugStringA(profile->name);
    OutputDebugStringA("extensionL2: native binding list registered\n");
    return TRUE;
}

extern "C" L2_EXPORT DWORD WINAPI ExtensionL2Index() { return l2client::NativeIndex; }
extern "C" L2_EXPORT DWORD WINAPI ExtensionL2LastStatus() { return lastStatus; }

// Binding introspection is independent of Core.dll and used by the UC generator.
extern "C" L2_EXPORT DWORD WINAPI ExtensionL2Count() {
    std::size_t count = 0;
    l2ext::bindings(count);
    return static_cast<DWORD>(count);
}
extern "C" L2_EXPORT BOOL WINAPI ExtensionL2GetBinding(DWORD ordinal, l2ext::BindingInfo* output, DWORD size) {
    if (!output || size != sizeof(*output)) return FALSE;
    std::size_t count = 0;
    const auto* items = l2ext::bindings(count);
    if (ordinal >= count) return FALSE;
    *output = items[ordinal].info;
    return TRUE;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {
    // Intentionally no registration, loading or engine calls under this DLL's
    // own attach. A patched Core wrapper calls ExtensionL2Attach AFTER Core init.
    return TRUE;
}
