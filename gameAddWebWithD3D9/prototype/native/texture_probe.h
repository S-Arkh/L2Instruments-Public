#pragma once
#include "base/extension_api.h"

// This specialization is local to the independently staged prototype build.
namespace l2ext {
template<> struct Value<void*> : Scalar<void*, Type::Object> {};
}

namespace textureprobe {
bool Frame(void* texture, std::int32_t phase);
std::int32_t Status();
}
