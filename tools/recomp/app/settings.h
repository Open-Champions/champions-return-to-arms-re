// settings.h - the picture settings of the application: a small text file of "key = value"
// lines (<data>/settings.txt, or --settings FILE), every one of which the command line can
// override.  docs/issues/native-graphics.md, "Settings".
//
//   window       = 1280x720   the window, in points
//   fullscreen   = no         (F or F11 switches while running)
//   aspect       = auto       the shape of the 3-D view: auto (the window's), 4:3 (the
//                             console's), 16:9, 16:10, 21:9, or any W:H from 4:3 to 32:9
//   resolution   = window     the size the picture is drawn at, whatever the window's:
//                             window (its own pixels), WxH, or Nx (N times the console's lines)
//   antialiasing = 4          samples per pixel of the 3-D scene: off, 2, 4, 8
//   anisotropy   = 16         anisotropic filtering of the 3-D scene's textures: 1 (off) to 16
//   mipmaps      = yes        mip maps for the game's own textures in the 3-D scene
//   art_pack     =            a folder of replacement pictures (tools/play-net/README.md,
//                             "Upscaled art"); empty = the game's own art
//   art_memory   = 3072       megabytes of video memory the pack may take
//   view         = overhead   the camera: overhead (the game's own), action, chase, shoulder,
//                             first; and view.<mode>.<name> = value for each view's own
//                             numbers (fpview.h)
//   world        = views      the world for a camera inside it (fpworld.h): views (while a view
//                             other than overhead is drawn), off, always; and world.clip,
//                             world.persp, world.objects = on | off, world.ceilings,
//                             world.skirts = auto | on | off
//   game_hud     = yes        the game's own HUD layer (player status, gold, compass, minimap,
//                             spell selector); no = left out of the picture (render/gs.h hide_edge)
//   game_hud_text = yes       its second group: the boss meter, the one-line message and the
//                             prompt box (hide_text)
//   music_volume = 1          0..1: the game's music alone; speech and effects stay as they are
//   music.boss   = on         the player's own music for boss fights (bossmusic.h): on | off;
//                             music.boss_dir = the folder (empty: <data>/music/boss/),
//                             music.boss_volume = 0..1
//   frame_cap    = 60         pictures a second: 60, 30 (every other picture is shown), or
//                             0 = no cap (the game then runs as fast as the machine: a
//                             benchmark, not for playing).  The game itself always counts 60
//                             steps a second.
#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace app {

struct Settings {
    int window_w = 960, window_h = 720;
    bool fullscreen = false;
    double aspect = 0;                  // width / height; 0 = the window's own
    int size_w = 0, size_h = 0, scale = 0;      // resolution: exact size, or a factor; neither = the window's
    int samples = 4;
    int anisotropy = 16;
    bool mipmaps = true;
    std::string art_pack;
    int art_memory = 3072;
    int frame_cap = 60;
    bool game_hud = true, game_hud_text = true;     // the game's own HUD layer / its boss meter, message and prompt box
    double music_volume = 1.0;                      // 0..1, the music alone
    std::vector<std::pair<std::string, std::string>> view;     // "view", "view.<mode>.<name>", "controls.*", "world", "world.*", "music.*" lines, for fpview / fpcontrols / fpworld / bossmusic ::setting

    static double parse_aspect(const std::string& text) {
        if (text == "auto" || text == "window" || text.empty()) return 0;
        double a = 0, b = 0;
        if (sscanf(text.c_str(), "%lf:%lf", &a, &b) == 2 && a > 0 && b > 0) return a / b;
        if (sscanf(text.c_str(), "%lf", &a) == 1 && a > 0.5) return a;
        return 0;
    }
    static bool truth(const std::string& text) { return text == "yes" || text == "on" || text == "1" || text == "true"; }

    // One setting by name; false when the name is not one.
    bool set(const std::string& key, const std::string& value) {
        if (key == "window") sscanf(value.c_str(), "%dx%d", &window_w, &window_h);
        else if (key == "fullscreen") fullscreen = truth(value);
        else if (key == "aspect") aspect = parse_aspect(value);
        else if (key == "resolution") {
            size_w = size_h = scale = 0;
            int w = 0, h = 0, n = 0;
            char x = 0;
            if (sscanf(value.c_str(), "%dx%d", &w, &h) == 2 && w > 0 && h > 0) { size_w = w; size_h = h; }
            else if (sscanf(value.c_str(), "%d%c", &n, &x) == 2 && (x == 'x' || x == 'X') && n > 0) scale = n > 16 ? 16 : n;
        }
        else if (key == "antialiasing") samples = (value == "off" || value == "no") ? 0 : atoi(value.c_str());
        else if (key == "anisotropy") { anisotropy = (value == "off" || value == "no") ? 1 : atoi(value.c_str()); if (anisotropy < 1) anisotropy = 1; }
        else if (key == "mipmaps") mipmaps = truth(value);
        else if (key == "art_pack") art_pack = value;
        else if (key == "art_memory") { art_memory = atoi(value.c_str()); if (art_memory < 64) art_memory = 64; }
        else if (key == "frame_cap") frame_cap = atoi(value.c_str());
        else if (key == "game_hud") game_hud = !(value == "off" || value == "no" || value == "0" || value == "false");
        else if (key == "game_hud_text") game_hud_text = !(value == "off" || value == "no" || value == "0" || value == "false");
        else if (key == "music_volume") { music_volume = atof(value.c_str()); music_volume = music_volume < 0 ? 0 : music_volume > 1 ? 1 : music_volume; }
        else if (key == "view" || key.compare(0, 5, "view.") == 0 || key.compare(0, 9, "controls.") == 0 || key.compare(0, 7, "combat.") == 0 || key == "world" || key.compare(0, 6, "world.") == 0 ||
                 key.compare(0, 6, "music.") == 0 || key.compare(0, 10, "cinematic.") == 0)
            view.push_back({key, value});       // controls.*: fpcontrols::setting; world, world.*: fpworld::setting; music.*: bossmusic::setting;
                                                // cinematic.*: cinematic::setting
        else return false;
        return true;
    }

    // Everything switched off: the picture as the console makes it, only larger.
    void plain() { aspect = 4.0 / 3.0; samples = 0; anisotropy = 1; mipmaps = false; art_pack.clear(); }

    // Reads `path`; lines that are not "key = value" with a known key are reported through `note`.
    bool load(const std::string& path, void (*note)(const std::string&) = nullptr) {
        FILE* f = fopen(path.c_str(), "r");
        if (!f) return false;
        char line[1024];
        while (fgets(line, sizeof line, f)) {
            std::string text = line;
            size_t hash = text.find('#');
            if (hash != std::string::npos) text.erase(hash);
            size_t eq = text.find('=');
            if (eq == std::string::npos) continue;
            auto trim = [](std::string s) {
                size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
                return a == std::string::npos ? std::string() : s.substr(a, b - a + 1);
            };
            std::string key = trim(text.substr(0, eq)), value = trim(text.substr(eq + 1));
            if (!key.empty() && !set(key, value) && note) note("settings: unknown line in " + path + ": " + key);
        }
        fclose(f);
        return true;
    }

    // Writes the file with what is set now and a line of explanation for each key.
    // `views`: the view settings as fpview::settings_text() gives them
    bool save(const std::string& path, const char* views = nullptr) const {
        FILE* f = fopen(path.c_str(), "w");
        if (!f) return false;
        auto yes = [](bool b) { return b ? "yes" : "no"; };
        fprintf(f, "# Champions: Return to Arms, native build - picture settings.  Lines are \"key = value\";\n"
                   "# what follows a # is a remark.  Every key can also be given on the command line.\n\n");
        fprintf(f, "window = %dx%d          # the window, in points\n", window_w, window_h);
        fprintf(f, "fullscreen = %s          # F or F11 switches while the game runs\n", yes(fullscreen));
        if (aspect == 0) fprintf(f, "aspect = auto            # the 3-D view: auto (the window's shape), 4:3 (as on the console), 16:9, 16:10, 21:9, W:H\n");
        else fprintf(f, "aspect = %.4f          # the 3-D view: auto (the window's shape), 4:3 (as on the console), 16:9, 16:10, 21:9, W:H\n", aspect);
        if (size_w) fprintf(f, "resolution = %dx%d", size_w, size_h);
        else if (scale) fprintf(f, "resolution = %dx", scale);
        else fprintf(f, "resolution = window");
        fprintf(f, "      # the size the picture is drawn at: window (its own pixels), 3840x2160, or 4x (of the console's lines)\n");
        fprintf(f, "antialiasing = %d         # samples per pixel of the 3-D scene: off, 2, 4, 8\n", samples);
        fprintf(f, "anisotropy = %d          # anisotropic filtering: 1 (off) to 16\n", anisotropy);
        fprintf(f, "mipmaps = %s             # mip maps for the game's own textures in the 3-D scene\n", yes(mipmaps));
        fprintf(f, "art_pack = %s            # a folder of replacement pictures; empty: the game's own art\n", art_pack.c_str());
        fprintf(f, "art_memory = %d         # megabytes of video memory the art pack may take\n", art_memory);
        fprintf(f, "frame_cap = %d           # pictures a second: 60, 30, or 0 for no cap (the game then runs fast: for measuring only)\n", frame_cap);
        fprintf(f, "game_hud = %s            # the game's own HUD layer (status, gold, compass, minimap, spell selector); no: left out of the picture\n", yes(game_hud));
        fprintf(f, "game_hud_text = %s       # the game's boss meter, one-line message and prompt box\n", yes(game_hud_text));
        fprintf(f, "music_volume = %.2f      # 0 to 1: the game's music alone (speech and effects stay as they are)\n", music_volume);
        if (views) fprintf(f, "\n# the camera (docs/issues/native-first-person.md): distances in the game's units (a character is about 60 high), angles in degrees\n%s", views);
        fclose(f);
        return true;
    }
};

}  // namespace app
