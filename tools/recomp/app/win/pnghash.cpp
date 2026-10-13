// pnghash.cpp - one figure over what render/png_read.h makes of a folder of PNG files.
//
// The Windows program reads the art pack with png_read.h.  On the Mac that reader was
// compared with QImage byte for byte (pngcheck.cpp); this small program lets the same
// reader be checked where it cannot be compared with anything: built for Windows it is
// pnghash.exe in the tester's folder, beside the folder "pngtest" of pictures made by
// pngtest.py (every kind of PNG, and damaged ones; nothing of the game).  It must print
// the figure the Mac prints for the same folder - README.txt has it.
//
//   pnghash FOLDER      every .png in FOLDER and its subfolders, in the order of their names
//
// The figure is FNV-1a (64 bits) over, for every file: its name, whether it was read, its
// width and height, and every byte of its pixels.  No Qt, no library: C++ and <dirent.h>.
#include "png_read.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <string>
#include <sys/stat.h>
#include <vector>

static void list(const std::string& folder, const std::string& shown, std::vector<std::pair<std::string, std::string>>& out, int depth) {
    DIR* d = opendir(folder.c_str());
    if (!d) return;
    while (dirent* e = readdir(d)) {
        std::string name = e->d_name;
        if (name == "." || name == "..") continue;
        std::string path = folder + "/" + name, label = shown.empty() ? name : shown + "/" + name;
        if (name.size() > 4 && name.compare(name.size() - 4, 4, ".png") == 0) { out.push_back({label, path}); continue; }
        struct stat st;
        if (depth < 2 && stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) list(path, label, out, depth + 1);
    }
    closedir(d);
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "pnghash FOLDER\n"); return 2; }
    std::vector<std::pair<std::string, std::string>> files;     // (name as hashed, path)
    list(argv[1], "", files, 0);
    std::sort(files.begin(), files.end());
    uint64_t figure = 1469598103934665603ull, read = 0, refused = 0, pixels = 0;
    auto add = [&figure](const void* data, size_t size) {
        const uint8_t* p = (const uint8_t*)data;
        for (size_t k = 0; k < size; k++) figure = (figure ^ p[k]) * 1099511628211ull;
    };
    std::vector<uint8_t> rgba;
    for (const auto& file : files) {
        int w = 0, h = 0;
        bool ok = pngread::read_file(file.second, rgba, w, h);
        uint8_t head[9] = {(uint8_t)ok, (uint8_t)(w >> 24), (uint8_t)(w >> 16), (uint8_t)(w >> 8), (uint8_t)w,
                           (uint8_t)(h >> 24), (uint8_t)(h >> 16), (uint8_t)(h >> 8), (uint8_t)h};
        add(file.first.data(), file.first.size());
        if (!ok) { memset(head + 1, 0, 8); add(head, 9); refused++; continue; }
        add(head, 9);
        add(rgba.data(), (size_t)w * h * 4);
        read++;
        pixels += (uint64_t)w * h;
    }
    printf("pnghash: %zu files: %llu read (%llu pixels), %llu refused; figure %016llx\n", files.size(), (unsigned long long)read,
           (unsigned long long)pixels, (unsigned long long)refused, (unsigned long long)figure);
    return files.empty() ? 1 : 0;
}
