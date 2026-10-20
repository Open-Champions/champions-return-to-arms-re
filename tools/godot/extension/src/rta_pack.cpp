// rta_pack.cpp - see rta_pack.h.
#include "rta_pack.h"

#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/rect2i.hpp>
#include <godot_cpp/variant/vector2i.hpp>

#include <dirent.h>
#include <sys/stat.h>
#include <cstdio>
#include <cstring>
#ifdef __APPLE__
#include <pthread.h>
#include <sys/qos.h>
#endif

namespace godot {

size_t RtaPack::open(const std::string& folder) {
    names.clear();
    dir = folder;
    while (dir.size() > 1 && dir.back() == '/') dir.pop_back();
    struct stat st;
    if (stat((dir + "/replace").c_str(), &st) == 0 && S_ISDIR(st.st_mode)) dir += "/replace";
    DIR* d = opendir(dir.c_str());
    if (!d) return 0;
    while (dirent* e = readdir(d)) {
        size_t n = strlen(e->d_name);
        if (n > 4 && !strcmp(e->d_name + n - 4, ".png")) names.emplace(e->d_name);
    }
    closedir(d);
    return names.size();
}

std::string RtaPack::find(const rtag_texture_name& t, int& texels_w, int& texels_h) const {
    if (names.empty() || !t.named) return std::string();
    // as the native program asks (backend_gl.cpp): by the size of what was sent, else by the size TEX0 names
    const int sizes[2][2] = {{t.sent_width, t.sent_height}, {t.named_width, t.named_height}};
    for (const auto& s : sizes) {
        if (s[0] <= 0 || s[1] <= 0) continue;
        char name[96];
        snprintf(name, sizeof name, "%016llx-%016llx-p%u-%ux%u.png", (unsigned long long)t.figure, (unsigned long long)t.palette_figure, t.format,
                 (unsigned)s[0], (unsigned)s[1]);
        if (names.count(name)) { texels_w = s[0]; texels_h = s[1]; return dir + "/" + name; }
    }
    return std::string();
}

void RtaPack::start(int threads) {
    if (!workers.empty()) return;
    quit = false;
    for (int k = 0; k < threads; k++) workers.emplace_back([this] { work(); });
}

void RtaPack::stop() {
    {
        std::lock_guard<std::mutex> hold(lock);
        quit = true;
        jobs.clear();
    }
    wake.notify_all();
    for (std::thread& t : workers) if (t.joinable()) t.join();
    workers.clear();
    std::lock_guard<std::mutex> hold(lock);
    done.clear();
}

void RtaPack::ask(Job job) {
    {
        std::lock_guard<std::mutex> hold(lock);
        // the small ones first (the interface's art is small and always on the screen)
        if (job.width * job.height <= 64 * 64) jobs.push_front(std::move(job)); else jobs.push_back(std::move(job));
    }
    wake.notify_one();
}

void RtaPack::forget(uint32_t texture) {
    std::lock_guard<std::mutex> hold(lock);
    for (auto k = jobs.begin(); k != jobs.end();) k = k->texture == texture ? jobs.erase(k) : k + 1;
}

bool RtaPack::take(Done& out) {
    std::lock_guard<std::mutex> hold(lock);
    if (done.empty()) return false;
    out = std::move(done.front());
    done.pop_front();
    return true;
}

size_t RtaPack::waiting() const {
    std::lock_guard<std::mutex> hold(lock);
    return jobs.size();
}

Ref<Image> RtaPack::make(const Job& job, bool& from_file, bool& woven_out) {
    from_file = false;
    woven_out = false;
    Ref<Image> own;
    if (job.own && job.width > 0 && job.height > 0) {
        PackedByteArray bytes;
        bytes.resize((int64_t)job.own->size());
        memcpy(bytes.ptrw(), job.own->data(), job.own->size());
        own = Image::create_from_data(job.width, job.height, false, Image::FORMAT_RGBA8, bytes);
    }
    Ref<Image> picture;
    if (!job.file.empty()) {
        PackedByteArray png = FileAccess::get_file_as_bytes(String::utf8(job.file.c_str()));
        bool woven = false;
        if (png.size() > 0) {
            Ref<Image> file;
            file.instantiate();
            if (file->load_png_from_buffer(png) == OK && file->get_width() > 0 && job.texels_w > 0 && job.texels_h > 0) {
                if (file->get_format() != Image::FORMAT_RGBA8) file->convert(Image::FORMAT_RGBA8);
                // the file covers texels_w x texels_h from the corner, `scale` times as many pixels
                int scale = std::max(1, (int)(file->get_width() / job.texels_w));
                // a two-field interface picture (upscale.py writes the woven picture twice: twice the factor in y) wants
                // the native program's woven sampling; until the shader has it the game's own is drawn (no garbled text)
                // (held whole as the native program holds it; only when it covers the whole texture)
                if (file->get_height() >= job.texels_h * scale * 2) {
                    if (job.texels_w == job.width && job.texels_h == job.height) {
                        two_field++; picture = file; woven_out = true; from_file = true; read_files++;
                    } else woven = true;
                    file.unref();
                }
            }
            if (file.is_valid() && file->get_width() > 0 && job.texels_w > 0 && job.texels_h > 0) {
                int scale = std::max(1, (int)(file->get_width() / job.texels_w));
                const int fw = job.texels_w * scale, fh = std::min(file->get_height(), job.texels_h * scale);
                const int W = job.width * scale, H = job.height * scale;
                if (fw == W && fh == H) picture = file;
                else if (W <= 8192 && H <= 8192) {
                    // the rest of the page from the game's own pixels, enlarged (the game draws within what was sent)
                    if (own.is_valid()) {
                        picture = own->duplicate();
                        picture->resize(W, H, Image::INTERPOLATE_NEAREST);
                    } else picture = Image::create_empty(W, H, false, Image::FORMAT_RGBA8);
                    picture->blit_rect(file, Rect2i(0, 0, std::min(fw, W), std::min(fh, H)), Vector2i(0, 0));
                }
                if (picture.is_valid()) { from_file = true; read_files++; }
            }
        }
        if (!picture.is_valid() && !woven) failed_files++;
    }
    if (!picture.is_valid()) picture = own;
    if (picture.is_valid()) { picture->generate_mipmaps(); mipmapped++; }
    return picture;
}

void RtaPack::work() {
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_UTILITY, 0);
#endif
    for (;;) {
        Job job;
        {
            std::unique_lock<std::mutex> hold(lock);
            wake.wait(hold, [this] { return quit || !jobs.empty(); });
            if (quit) return;
            job = std::move(jobs.front());
            jobs.pop_front();
        }
        Done d;
        d.texture = job.texture;
        d.serial = job.serial;
        d.image = make(job, d.from_file, d.woven);
        std::lock_guard<std::mutex> hold(lock);
        if (quit) return;
        done.push_back(std::move(d));
    }
}

}  // namespace godot
