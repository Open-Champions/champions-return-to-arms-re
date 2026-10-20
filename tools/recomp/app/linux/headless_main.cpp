// headless_main.cpp - rta_native for Linux: the machine with nothing attached (app/win/headless_main.cpp's
// defaults, for a tester who types one short line): without --elf the game's executable is copied out of
// the disc image into rta-data beside the program, without --card the memory cards are in rta-data/card-headless.
//
//   ./rta_native boot --disc "/path/to/image.iso" --fields 1200
#if defined(__linux__)
#include "app_rt.h"

#include <sys/stat.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    static std::vector<std::string> args(argv, argv + argc);
    bool boot = argc >= 2 && !strcmp(argv[1], "boot"), have_elf = false, have_card = false;
    std::string disc = getenv("RTA_DISC") ? getenv("RTA_DISC") : "";
    for (int k = 2; k < argc; k++) {
        if (!strcmp(argv[k], "--elf")) have_elf = true;
        if (!strcmp(argv[k], "--card")) have_card = true;
        if (!strcmp(argv[k], "--disc") && k + 1 < argc) disc = argv[k + 1];
    }
    if (boot && (!have_elf || !have_card)) {
        char path[4096];
        ssize_t n = readlink("/proc/self/exe", path, sizeof path - 1);
        std::string data = n > 0 ? std::string(path, (size_t)n) : std::string("./rta_native");
        data = data.substr(0, data.find_last_of('/')) + "/rta-data";
        mkdir(data.c_str(), 0755);
        if (!have_elf) {
            std::string elf = data + "/SLUS_209.73";
            if (access(elf.c_str(), F_OK) != 0 && !apprt::extract_from_disc(disc, "\\SLUS_209.73;1", elf)) {
                fprintf(stderr, "rta_native: no --elf, and SLUS_209.73 could not be copied out of the disc image \"%s\" (give --disc)\n", disc.c_str());
                return 1;
            }
            args.push_back("--elf"); args.push_back(elf);
        }
        if (!have_card) { args.push_back("--card"); args.push_back(data + "/card-headless"); }
    }
    static std::vector<char*> run_args;
    for (auto& a : args) run_args.push_back(&a[0]);
    rta::Hooks hooks;
    return rta::run((int)run_args.size(), run_args.data(), hooks);
}
#endif  // __linux__
