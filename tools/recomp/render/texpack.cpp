// texpack.cpp - see texpack.h.  PNG files are read with Qt (QImage), which the OpenGL
// backend links anyway; nothing else of Qt is used.  A build without Qt (the Windows one
// stands in for Qt's OpenGL headers only) defines RTA_NO_QIMAGE: no pack is read then -
// open() finds nothing - and the mip-mapped parts of the game's own textures still work;
// what it needs to read packs is a PNG reader in read_png() below.
#include "texpack.h"

#ifndef RTA_NO_QIMAGE
#include <QImage>
#include <QString>
#endif

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <sys/stat.h>
#ifdef __APPLE__
#include <pthread.h>
#include <sys/qos.h>
#endif

namespace render {

// A PNG file as RGBA8, rows top to bottom, nothing premultiplied.
static bool read_png(const std::string& path, std::vector<uint8_t>& rgba, int& width, int& height) {
#ifndef RTA_NO_QIMAGE
    QImage image(QString::fromStdString(path));
    if (image.isNull()) return false;
    if (image.format() != QImage::Format_RGBA8888) image = image.convertToFormat(QImage::Format_RGBA8888);
    width = image.width(); height = image.height();
    rgba.resize((size_t)width * height * 4);
    for (int y = 0; y < height; y++) memcpy(rgba.data() + (size_t)y * width * 4, image.constScanLine(y), (size_t)width * 4);
    return true;
#else
    (void)path; (void)rgba; (void)width; (void)height;
    return false;
#endif
}

size_t TexPack::open(const std::string& folder) {
    names.clear();
#ifdef RTA_NO_QIMAGE
    (void)folder;
    return 0;
#endif
    dir = folder;
    while (dir.size() > 1 && dir.back() == '/') dir.pop_back();
    struct stat st;
    if (stat((dir + "/replace").c_str(), &st) == 0 && S_ISDIR(st.st_mode)) dir += "/replace";
    DIR* d = opendir(dir.c_str());
    if (!d) return 0;
    while (dirent* e = readdir(d)) {
        size_t n = strlen(e->d_name);
        if (n > 4 && !strcmp(e->d_name + n - 4, ".png")) names.emplace(e->d_name, true);
    }
    closedir(d);
    return names.size();
}

std::string TexPack::find(uint64_t figure, uint64_t palette_figure, uint32_t format, int width, int height) const {
    if (names.empty()) return std::string();
    char name[96];
    snprintf(name, sizeof name, "%016llx-%016llx-p%u-%ux%u.png", (unsigned long long)figure, (unsigned long long)palette_figure, format, (unsigned)width,
             (unsigned)height);
    return names.count(name) ? dir + "/" + name : std::string();
}

void TexPack::start(int threads) {
    if (!workers.empty()) return;
    quit = false;
    for (int k = 0; k < threads; k++) workers.emplace_back([this] { work(); });
}

void TexPack::stop() {
    {
        std::lock_guard<std::mutex> hold(lock);
        quit = true;
        jobs.clear();
        open_jobs = 0;
    }
    wake.notify_all();
    for (std::thread& t : workers) if (t.joinable()) t.join();
    workers.clear();
}

void TexPack::ask(PictureJob job) {
    {
        std::lock_guard<std::mutex> hold(lock);
        if (job.first) jobs.push_front(std::move(job)); else jobs.push_back(std::move(job));
        open_jobs++;
    }
    wake.notify_one();
}

void TexPack::forget(uint32_t texture) {
    std::lock_guard<std::mutex> hold(lock);
    for (auto it = jobs.begin(); it != jobs.end();)
        if (it->texture == texture) { it = jobs.erase(it); open_jobs--; } else ++it;
}

bool TexPack::take(PictureResult& out) {
    std::lock_guard<std::mutex> hold(lock);
    if (done.empty()) return false;
    out = std::move(done.front());
    done.pop_front();
    open_jobs--;
    return true;
}

size_t TexPack::waiting() const {
    std::lock_guard<std::mutex> hold(lock);
    return jobs.size();
}

void TexPack::work() {
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_UTILITY, 0);        // reading never takes a core from the game
#endif
    for (;;) {
        PictureJob job;
        {
            std::unique_lock<std::mutex> hold(lock);
            wake.wait(hold, [this] { return quit || !jobs.empty(); });
            if (quit) return;
            job = std::move(jobs.front());
            jobs.pop_front();
        }
        PictureResult result = make(job);
        std::lock_guard<std::mutex> hold(lock);
        if (quit) return;
        done.push_back(std::move(result));
    }
}

// One level from the one above: each pixel the mean of the two by two it covers (the last
// column or row twice where the size is odd).  All four channels alike: alpha is a value
// of its own here (128 = opaque, and for level textures 0 is opaque too), not a weight.
static void halve(const PictureResult::Level& from, PictureResult::Level& to) {
    to.width = std::max(1, from.width / 2);
    to.height = std::max(1, from.height / 2);
    to.rgba.resize((size_t)to.width * to.height * 4);
    for (int y = 0; y < to.height; y++) {
        int y0 = std::min(2 * y, from.height - 1), y1 = std::min(2 * y + 1, from.height - 1);
        const uint8_t* a = from.rgba.data() + (size_t)y0 * from.width * 4;
        const uint8_t* b = from.rgba.data() + (size_t)y1 * from.width * 4;
        uint8_t* out = to.rgba.data() + (size_t)y * to.width * 4;
        for (int x = 0; x < to.width; x++) {
            int x0 = std::min(2 * x, from.width - 1) * 4, x1 = std::min(2 * x + 1, from.width - 1) * 4;
            for (int c = 0; c < 4; c++) out[x * 4 + c] = (uint8_t)((a[x0 + c] + a[x1 + c] + b[x0 + c] + b[x1 + c] + 2) >> 2);
        }
    }
}

PictureResult TexPack::make(const PictureJob& job) {
    PictureResult r;
    r.texture = job.texture;
    r.serial = job.serial;
    std::vector<uint8_t> file;
    const uint8_t* source = nullptr;
    int sw = 0, sh = 0;
    size_t stride = 0;
    if (job.own) {
        source = job.own->data(); sw = job.own_width; sh = job.own_height; stride = (size_t)sw * 4;
        if (job.own->size() < stride * sh) return r;
    } else {
        if (!read_png(job.file, file, sw, sh)) return r;
        source = file.data(); stride = (size_t)sw * 4;
        r.from_file = true;
    }
    int tw = job.texels_w, th = job.texels_h;
    if (tw <= 0 || th <= 0 || sw <= 0 || sh <= 0) return r;
    bool multiple = sw % tw == 0 && sh % th == 0;
    int fx = multiple ? sw / tw : 1, fy = multiple ? sh / th : 1;
    r.two_field = r.from_file && multiple && fy == 2 * fx;
    int x0 = 0, y0 = 0, x1 = tw, y1 = th;
    if (job.part && multiple && !r.two_field) {
        int bx0 = std::max(0, (int)std::floor(job.box[0]) - job.margin), by0 = std::max(0, (int)std::floor(job.box[1]) - job.margin);
        int bx1 = std::min(tw, (int)std::ceil(job.box[2]) + job.margin), by1 = std::min(th, (int)std::ceil(job.box[3]) + job.margin);
        if (bx1 > bx0 && by1 > by0 && (uint64_t)(bx1 - bx0) * (by1 - by0) * 10 < (uint64_t)tw * th * 9) {
            x0 = bx0; y0 = by0; x1 = bx1; y1 = by1;
            r.whole = false;
        }
    }
    r.part[0] = x0; r.part[1] = y0; r.part[2] = x1; r.part[3] = y1;
    int px0 = multiple ? x0 * fx : 0, py0 = multiple ? y0 * fy : 0;
    int pw = multiple ? (x1 - x0) * fx : sw, ph = multiple ? (y1 - y0) * fy : sh;
    r.levels.emplace_back();
    PictureResult::Level& top = r.levels.back();
    top.width = pw; top.height = ph;
    top.rgba.resize((size_t)pw * ph * 4);
    for (int y = 0; y < ph; y++) memcpy(top.rgba.data() + (size_t)y * pw * 4, source + (size_t)(py0 + y) * stride + (size_t)px0 * 4, (size_t)pw * 4);
    while (r.levels.back().width > 1 || r.levels.back().height > 1) {
        PictureResult::Level next;
        halve(r.levels.back(), next);
        r.levels.push_back(std::move(next));
    }
    r.ok = true;
    return r;
}

}  // namespace render
