// testerkit_app.h - what the three programs (app_main.cpp, win_main.cpp, linux/linux_main.cpp) tell a report
// about their view and mode settings (testerkit.h, Setup::describe): the camera, the two room modes, the picture.
#pragma once
#include "fpaim.h"
#include "fpview.h"
#include "settings.h"
#include "soulscombat.h"

#include <cstdio>
#include <string>

namespace testerkit {
inline std::string describe_app(const app::Settings& s, const std::string& extra) {
    char text[1024];
    char resolution[48];
    if (s.size_w > 0) snprintf(resolution, sizeof resolution, "%dx%d", s.size_w, s.size_h);
    else if (s.scale > 0) snprintf(resolution, sizeof resolution, "%dx", s.scale);
    else snprintf(resolution, sizeof resolution, "window");
    char aspect[32];
    if (s.aspect > 0) snprintf(aspect, sizeof aspect, "%.4f", s.aspect); else snprintf(aspect, sizeof aspect, "auto");
    snprintf(text, sizeof text,
             "view = %s\naim = %s\ncombat = %s\naspect = %s\nresolution = %s\nantialiasing = %d\nanisotropy = %d\nmipmaps = %s\n"
             "art_pack = %s\nframe_cap = %d\ngame_hud = %s\ngame_hud_text = %s\nmusic_volume = %.2f\n",
             fpview::mode_name(fpview::mode()), fpaim::wanted() ? "where you look" : "the game's", soulscombat::wanted() ? "souls" : "the game's",
             aspect, resolution, s.samples, s.anisotropy, s.mipmaps ? "yes" : "no", s.art_pack.empty() ? "none" : "yes", s.frame_cap,
             s.game_hud ? "on" : "off", s.game_hud_text ? "on" : "off", s.music_volume);
    return text + extra;
}
}  // namespace testerkit
