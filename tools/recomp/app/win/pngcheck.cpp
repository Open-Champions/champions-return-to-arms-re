// pngcheck.cpp - render/png_read.h against Qt's QImage, file by file, byte for byte.
//
// The Windows program has no Qt and reads the art pack with png_read.h; the macOS program
// reads it with QImage (render/texpack.cpp, read_png).  This runs both readers - QImage
// exactly as texpack.cpp uses it - over every .png file of the folders it is given and
// says whether a single byte differs.  macOS only (it needs Qt); built by
//   python3 tools/recomp/app/build_win.py --pngcheck      -> local/recomp-out/win/standin/pngcheck
//   pngcheck [--threads N] [--verbose] [--list-kinds] FOLDER...
// A file both readers refuse counts as agreement (and is listed with --verbose); a file one
// of them refuses, or that differs in size or in any byte, is a difference and is named.
// Exit code 0: no difference.
#include "png_read.h"

#include <QCoreApplication>
#include <QImage>
#include <QString>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <map>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <vector>

// render/texpack.cpp, read_png, the Qt branch - kept word for word
static bool read_qt(const std::string& path, std::vector<uint8_t>& rgba, int& width, int& height) {
    QImage image(QString::fromStdString(path));
    if (image.isNull()) return false;
    if (image.format() != QImage::Format_RGBA8888) image = image.convertToFormat(QImage::Format_RGBA8888);
    width = image.width(); height = image.height();
    rgba.resize((size_t)width * height * 4);
    for (int y = 0; y < height; y++) memcpy(rgba.data() + (size_t)y * width * 4, image.constScanLine(y), (size_t)width * 4);
    return true;
}

static void list(const std::string& folder, std::vector<std::string>& out, int depth) {
    DIR* d = opendir(folder.c_str());
    if (!d) { fprintf(stderr, "pngcheck: cannot list %s\n", folder.c_str()); return; }
    while (dirent* e = readdir(d)) {
        std::string name = e->d_name;
        if (name == "." || name == "..") continue;
        std::string path = folder + "/" + name;
        if (name.size() > 4 && name.compare(name.size() - 4, 4, ".png") == 0) { out.push_back(path); continue; }
        struct stat st;
        if (depth < 3 && stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) list(path, out, depth + 1);
    }
    closedir(d);
}

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    int threads = 6;
    bool verbose = false, kinds = false;
    std::vector<std::string> files;
    for (int k = 1; k < argc; k++) {
        std::string a = argv[k];
        if (a == "--threads" && k + 1 < argc) threads = atoi(argv[++k]);
        else if (a == "--verbose") verbose = true;
        else if (a == "--list-kinds") kinds = true;
        else list(a, files, 0);
    }
    if (files.empty()) { fprintf(stderr, "pngcheck [--threads N] [--verbose] [--list-kinds] FOLDER...\n"); return 2; }
    if (threads < 1) threads = 1;
    std::atomic<size_t> next{0};
    std::mutex lock;
    uint64_t same = 0, both_refused = 0, differ = 0, only_qt = 0, only_own = 0, pixels = 0, file_bytes = 0;
    double qt_s = 0, own_s = 0;
    std::map<std::string, uint64_t> by_kind;
    auto work = [&]() {
        std::vector<uint8_t> a, b;
        for (;;) {
            size_t k = next++;
            if (k >= files.size()) return;
            const std::string& path = files[k];
            int aw = 0, ah = 0, bw = 0, bh = 0;
            auto t0 = std::chrono::steady_clock::now();
            bool qt = read_qt(path, a, aw, ah);
            auto t1 = std::chrono::steady_clock::now();
            bool own = pngread::read_file(path, b, bw, bh);
            auto t2 = std::chrono::steady_clock::now();
            std::string kind;
            uint64_t size = 0;
            if (FILE* f = fopen(path.c_str(), "rb")) {
                unsigned char head[33];
                size_t n = fread(head, 1, sizeof head, f);
                struct stat st;
                if (fstat(fileno(f), &st) == 0) size = (uint64_t)st.st_size;
                fclose(f);
                char text[64];
                if (n == 33) snprintf(text, sizeof text, "colour type %d, %d bits%s", head[25], head[24], head[28] ? ", interlaced" : "");
                else snprintf(text, sizeof text, "shorter than a header");
                kind = text;
            }
            std::lock_guard<std::mutex> hold(lock);
            qt_s += std::chrono::duration<double>(t1 - t0).count();
            own_s += std::chrono::duration<double>(t2 - t1).count();
            file_bytes += size;
            by_kind[kind]++;
            if (!qt && !own) { both_refused++; if (verbose) printf("both refuse %s\n", path.c_str()); continue; }
            if (qt != own) {
                (qt ? only_qt : only_own)++;
                printf("DIFFERENT: only %s reads %s (%s)\n", qt ? "QImage" : "png_read.h", path.c_str(), kind.c_str());
                continue;
            }
            if (aw != bw || ah != bh || a.size() != b.size()) {
                differ++;
                printf("DIFFERENT: size %d x %d against %d x %d: %s (%s)\n", aw, ah, bw, bh, path.c_str(), kind.c_str());
                continue;
            }
            pixels += (uint64_t)aw * ah;
            if (memcmp(a.data(), b.data(), a.size()) == 0) { same++; continue; }
            differ++;
            size_t first = 0, count = 0;
            for (size_t i = 0; i < a.size(); i++) if (a[i] != b[i]) { if (!count) first = i; count++; }
            printf("DIFFERENT: %zu of %zu bytes; first at pixel (%zu, %zu) channel %zu: QImage %u, png_read.h %u: %s (%s)\n", count, a.size(),
                   (first / 4) % (size_t)aw, (first / 4) / (size_t)aw, first % 4, a[first], b[first], path.c_str(), kind.c_str());
        }
    };
    auto start = std::chrono::steady_clock::now();
    std::vector<std::thread> pool;
    for (int k = 0; k < threads; k++) pool.emplace_back(work);
    for (auto& t : pool) t.join();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    printf("pngcheck: %zu files (%.2f GB): %llu identical in every byte (%.1f million pixels), %llu refused by both, %llu DIFFERENT, "
           "%llu read by QImage only, %llu read by png_read.h only\n", files.size(), file_bytes / 1e9, (unsigned long long)same, pixels / 1e6,
           (unsigned long long)both_refused, (unsigned long long)differ, (unsigned long long)only_qt, (unsigned long long)only_own);
    printf("pngcheck: %.0f s of wall time on %d threads; reading took QImage %.0f s and png_read.h %.0f s (summed over the threads)\n", wall, threads, qt_s, own_s);
    if (kinds) for (auto& entry : by_kind) printf("pngcheck:   %8llu  %s\n", (unsigned long long)entry.second, entry.first.c_str());
    return (differ || only_qt || only_own) ? 1 : 0;
}
