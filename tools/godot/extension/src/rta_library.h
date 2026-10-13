// rta_library.h - the game library (../../lib/rtag.h) loaded at run time.
//
// The extension holds no game code and does not link the library: it is given the
// library's path (a file that stays on the user's machine) and takes the functions by name.
#pragma once
#include "rtag.h"

#include <string>

#define RTAG_FUNCTIONS(F) \
    F(rtag_api_version) F(rtag_has) F(rtag_start) F(rtag_set_pad) F(rtag_step) F(rtag_poll) F(rtag_run) F(rtag_audio_pull) \
    F(rtag_memory) F(rtag_fields) F(rtag_info) F(rtag_ended) F(rtag_exit_code) F(rtag_stop)

struct RtaLibrary {
#define RTAG_MEMBER(name) decltype(&::name) name = nullptr;
    RTAG_FUNCTIONS(RTAG_MEMBER)
#undef RTAG_MEMBER
    bool loaded = false;
    std::string error;
    bool load(const std::string& path);
};

// The one library of the process (one machine per process: rtag.h).
RtaLibrary& rta_library();
