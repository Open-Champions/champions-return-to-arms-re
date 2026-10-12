// headless_main.cpp - rta_native.exe: the machine with nothing attached, for Windows.
//
// rt/main_headless.cpp with the defaults tools/recomp/native.py gives on the Mac, so that a
// tester types one short line: without --elf the game's executable is copied out of the
// disc image into rta-data beside the program, without --card the memory cards are in
// rta-data\card-headless.  Everything else is the runtime's (rta_native.exe --help).
//
//   rta_native.exe boot --disc "C:\path\image.iso" --fields 1200
//
// Written and compiled on a Mac with a cross-compiler; NOT RUN.
#ifdef _WIN32
#include "app_rt.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

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
        char module[MAX_PATH * 4];
        GetModuleFileNameA(nullptr, module, sizeof module);
        std::string data = module;
        data = data.substr(0, data.find_last_of("\\/")) + "\\rta-data";
        CreateDirectoryA(data.c_str(), nullptr);
        if (!have_elf) {
            std::string elf = data + "\\SLUS_209.73";
            if (GetFileAttributesA(elf.c_str()) == INVALID_FILE_ATTRIBUTES && !apprt::extract_from_disc(disc, "\\SLUS_209.73;1", elf)) {
                fprintf(stderr, "rta_native: no --elf, and SLUS_209.73 could not be copied out of the disc image \"%s\" (give --disc)\n", disc.c_str());
                return 1;
            }
            args.push_back("--elf"); args.push_back(elf);
        }
        if (!have_card) { args.push_back("--card"); args.push_back(data + "\\card-headless"); }
    }
    static std::vector<char*> run_args;
    for (auto& a : args) run_args.push_back(&a[0]);
    rta::Hooks hooks;
    return rta::run((int)run_args.size(), run_args.data(), hooks);
}
#endif  // _WIN32
