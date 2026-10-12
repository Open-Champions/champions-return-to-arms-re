// app_rt.cpp - see app_rt.h.
#include "app_rt.h"

#include "rt.h"
#include "iso9660.h"

#include <cstdio>
#include <vector>

namespace apprt {

rta::PadState script_pad(unsigned port) { return ::script_pad(port); }

static void (*g_command)(const std::string&, uint64_t);
void set_command_handler(void (*handler)(const std::string&, uint64_t)) {
    g_command = handler;
    script_app_command = [](const std::string& text, u64 frame) { if (g_command) g_command(text, frame); };
}
void set_finish_handler(void (*handler)()) { rt_at_finish = handler; }
void finish(int code) { rt_finish(code); }

uint64_t fields() { return rt_fields(); }
double machine_seconds() { return (double)rt_cycles() / (double)CYCLES_PER_SECOND; }

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
