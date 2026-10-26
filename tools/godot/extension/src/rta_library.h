// rta_library.h - the game library (../../lib/rtag.h) loaded at run time.
//
// The extension holds no game code and does not link the library: it is given the
// library's path (a file that stays on the user's machine) and takes the functions by name.
#pragma once
#include "rtag.h"

#include <string>

#define RTAG_FUNCTIONS(F) \
    F(rtag_api_version) F(rtag_has) F(rtag_start) F(rtag_set_pad) F(rtag_step) F(rtag_poll) F(rtag_run) F(rtag_audio_pull) \
    F(rtag_memory) F(rtag_fields) F(rtag_info) F(rtag_ended) F(rtag_exit_code) F(rtag_stop) F(rtag_set_option)

// added after version 6 without changing it: null when the library is older
#define RTAG_OPTIONAL_FUNCTIONS(F) F(rtag_controls_hud) F(rtag_mouse) F(rtag_mouse_button) F(rtag_fill_get) F(rtag_texture_names) \
    F(rtag_report_begin) F(rtag_report_finish) F(rtag_build_line) F(rtag_report_told) F(rtag_skeletons_get) F(rtag_frame_age_ms) F(rtag_frame_since_release_ms) F(rtag_release) \
    F(rtag_film_now)

struct RtaLibrary {
#define RTAG_MEMBER(name) decltype(&::name) name = nullptr;
    RTAG_FUNCTIONS(RTAG_MEMBER)
    RTAG_OPTIONAL_FUNCTIONS(RTAG_MEMBER)
#undef RTAG_MEMBER
    bool loaded = false;
    std::string error;
    std::string path;                   // the file it was loaded from
    void* handle = nullptr;
    bool load(const std::string& path);
    void* symbol(const char* name) const;   // any other function of the library by name (null: it has none)
};

// The one library of the process (one machine per process: rtag.h).
RtaLibrary& rta_library();
