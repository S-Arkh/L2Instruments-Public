cmake_minimum_required(VERSION 3.24)
project(ExtensionL2 LANGUAGES CXX)
if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
    message(FATAL_ERROR "Build this client ABI example for Windows x86 (VS2022 -A Win32)")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_custom_target(generate_core_profiles
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/core_profiles.py" generate
    BYPRODUCTS "${CMAKE_CURRENT_SOURCE_DIR}/src/client_profile.h"
    VERBATIM)
add_library(ExtensionL2 SHARED src/extension_runtime.cpp src/extensionL2.cpp)
add_dependencies(ExtensionL2 generate_core_profiles)
add_executable(extension_bindings tools/extension_bindings.cpp)
target_include_directories(extension_bindings PRIVATE src)
add_executable(extension_probe tests/extension_probe.cpp)
add_executable(client_link_probe tests/client_link_probe.cpp)
add_dependencies(extension_probe ExtensionL2)
target_include_directories(extension_probe PRIVATE src)
if(MSVC)
    target_sources(ExtensionL2 PRIVATE src/ExtensionL2.def)
    target_compile_options(ExtensionL2 PRIVATE /W4 /EHsc /utf-8)
    target_compile_options(extension_probe PRIVATE /W4 /EHsc /utf-8)
    target_compile_options(extension_bindings PRIVATE /W4 /EHsc /utf-8)
    target_compile_options(client_link_probe PRIVATE /W4 /EHsc /utf-8)
elseif(MINGW)
    set_target_properties(ExtensionL2 PROPERTIES PREFIX "")
    target_link_options(ExtensionL2 PRIVATE -static -Wl,--kill-at)
    target_link_options(extension_probe PRIVATE -static -municode)
    target_link_options(extension_bindings PRIVATE -static -municode)
    target_link_options(client_link_probe PRIVATE -static -municode)
endif()
add_custom_target(generate_native_uc
    COMMAND extension_bindings "$<TARGET_FILE:ExtensionL2>"
        "${CMAKE_CURRENT_SOURCE_DIR}/ExtensionL2/Classes/ExtensionL2API.uc"
        "${CMAKE_CURRENT_BINARY_DIR}/bindings.json"
    DEPENDS ExtensionL2 extension_bindings
    VERBATIM)
