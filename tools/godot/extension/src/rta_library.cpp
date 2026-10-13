// rta_library.cpp - see rta_library.h.
#include "rta_library.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
static void* open_library(const std::string& path, std::string& error) {
    HMODULE module = LoadLibraryA(path.c_str());
    if (!module) error = "LoadLibrary failed with error " + std::to_string((unsigned long)GetLastError());
    return (void*)module;
}
static void* find_symbol(void* library, const char* name) { return (void*)GetProcAddress((HMODULE)library, name); }
#else
#include <dlfcn.h>
static void* open_library(const std::string& path, std::string& error) {
    void* handle = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) { const char* why = dlerror(); error = why ? why : "dlopen failed"; }
    return handle;
}
static void* find_symbol(void* library, const char* name) { return dlsym(library, name); }
#endif

RtaLibrary& rta_library() {
    static RtaLibrary library;
    return library;
}

bool RtaLibrary::load(const std::string& path) {
    if (loaded) return true;
    void* handle = open_library(path, error);
    if (!handle) return false;
#define RTAG_LOAD(name) \
    name = (decltype(name))find_symbol(handle, #name); \
    if (!name) { error = std::string("the library has no ") + #name; return false; }
    RTAG_FUNCTIONS(RTAG_LOAD)
#undef RTAG_LOAD
    if (rtag_api_version() != RTAG_API_VERSION) {
        error = "the library speaks version " + std::to_string(rtag_api_version()) + " of the interface, this extension " + std::to_string(RTAG_API_VERSION);
        return false;
    }
    loaded = true;
    return true;
}
