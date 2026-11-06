#pragma once
#include <windows.h>

namespace ucc64 {
// Exact SDK only. Must run before UObject initialization, with module lifetime.
bool registerPtrProperty(HMODULE core);
void* ptrPropertyClass();
bool isPtrProperty(void* object);
}
