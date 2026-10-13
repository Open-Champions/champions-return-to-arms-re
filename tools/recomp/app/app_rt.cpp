// app_rt.cpp - see app_rt.h.
#include "app_rt.h"

#include "rt.h"
#include "host.h"
#include "iso9660.h"

#include <cstdio>
#include <cstring>
#include <vector>

std::string rta_sound_figures() __attribute__((weak));     // tools/recomp/sound/sound_rta.cpp
// tools/recomp/app/film.cpp defines these two when it is part of the program
__attribute__((weak)) bool rta_films_linked() { return false; }
__attribute__((weak)) void rta_films_report() {}

namespace apprt {

void interactive_threads() { host::interactive_threads(true); }
bool films_linked() { return rta_films_linked(); }
void films_report() { rta_films_report(); }
std::string sound_figures() { return rta_sound_figures ? rta_sound_figures() : std::string(); }
rta::PadState script_pad(unsigned port) { return ::script_pad(port); }

static void (*g_command)(const std::string&, uint64_t);
void set_command_handler(void (*handler)(const std::string&, uint64_t)) {
    g_command = handler;
    script_app_command = [](const std::string& text, u64 frame) { if (g_command) g_command(text, frame); };
}
void command(const std::string& text, uint64_t frame) {
    if (script_app_command) script_app_command(text, frame);
    else if (g_command) g_command(text, frame);
}
void thread_figures(unsigned& now, unsigned& made, unsigned& ended) { u32 a = 0, b = 0, c = 0; rt_thread_figures(&a, &b, &c); now = a; made = b; ended = c; }
bool replaying() { const char* file = rt_option("pad-replay"); return file && *file; }
void set_finish_handler(void (*handler)()) { rt_at_finish = handler; }
void finish(int code) { rt_finish(code); }

uint64_t fields() { return rt_fields(); }
double machine_seconds() { return (double)rt_cycles() / (double)CYCLES_PER_SECOND; }

int disc_check(const std::string& image, uint32_t& figure) {
    Iso9660 disc;
    Iso9660::Entry entry;
    figure = 0;
    if (!disc.open(image.c_str())) return 0;
    if (!disc.find("\\SLUS_209.73;1", &entry) || entry.directory || entry.size < 4096) return 1;
    uint32_t sectors = (entry.size + Iso9660::SECTOR - 1) / Iso9660::SECTOR;
    std::vector<uint8_t> data((size_t)sectors * Iso9660::SECTOR);
    if (!disc.read(entry.sector, sectors, data.data())) return 0;
    for (size_t at = 0; at + 4 <= entry.size; at += 4) { uint32_t word; memcpy(&word, data.data() + at, 4); figure ^= word; }
    return 2;
}

bool extract_from_disc(const std::string& image, const char* path_on_disc, const std::string& to) {
    Iso9660 disc;
    Iso9660::Entry entry;
    if (!disc.open(image.c_str()) || !disc.find(path_on_disc, &entry) || entry.directory || !entry.size) return false;
    uint32_t sectors = (entry.size + Iso9660::SECTOR - 1) / Iso9660::SECTOR;
    std::vector<uint8_t> data((size_t)sectors * Iso9660::SECTOR);
    if (!disc.read(entry.sector, sectors, data.data())) return false;
    FILE* f = fopen(to.c_str(), "wb");
    if (!f) return false;
    bool ok = fwrite(data.data(), 1, entry.size, f) == entry.size;
    fclose(f);
    return ok;
}

}  // namespace apprt
