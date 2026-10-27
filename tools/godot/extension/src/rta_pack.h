// rta_pack.h - the art pack and mip maps for the drawer (RtaDrawer.set_art_pack).
//
// An art pack is the folder of PNG files the native OpenGL program draws in place of the game's textures
// (tools/recomp/render/texpack.h, made by tools/play-net/upscale.py): "<figure>-<palette>-p<format>-<width>x<height>.png",
// a whole multiple of that size, covering the texels from the texture's corner, alpha as on the console (128 = opaque).
// The names come from the library (rtag_texture_names).  The folder is listed once; a file is read and its mip maps
// are made by threads of low priority when its texture first arrives, and the texture's RID is then given the
// picture (RenderingServer::texture_replace) - until then the game's own texture is drawn.  Textures without a
// file get mip maps of their own pixels the same way (the game has none: they are what makes a far floor sharp
// under anisotropic filtering instead of shimmering).  Nothing of the pack is copied anywhere.
#pragma once
#include "rtag.h"

#include <godot_cpp/classes/image.hpp>

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

namespace godot {

class RtaPack {
  public:
    struct Job {
        uint32_t texture = 0;
        uint64_t serial = 0;
        std::string file;                           // empty: mip maps of `own` only
        std::shared_ptr<std::vector<uint8_t>> own;  // the game's pixels (RGBA8)
        int width = 0, height = 0;                  // of the texture
        int texels_w = 0, texels_h = 0;             // what the file covers (the size in its name)
    };
    struct Done {
        uint32_t texture = 0;
        uint64_t serial = 0;
        bool from_file = false;
        bool woven = false;                         // a two-field interface picture, held whole (sampled by the woven line)
        int woven_w = 0, woven_h = 0;               // ... the texels it covers (the size in its name): sampled over these
        Ref<Image> image;
    };
    ~RtaPack() { stop(); }
    size_t open(const std::string& folder);         // the folder, or its "replace" subfolder; returns the number of pictures
    const std::string& folder() const { return dir; }
    size_t size() const { return names.size(); }
    std::string find(const rtag_texture_name& n, int& texels_w, int& texels_h) const;
    void start(int threads);
    void stop();
    void ask(Job job);
    void forget(uint32_t texture);
    bool take(Done& out);
    size_t waiting() const;
    std::atomic<uint64_t> read_files{0}, failed_files{0}, mipmapped{0}, two_field{0};

  private:
    std::string dir;
    std::unordered_set<std::string> names;
    std::vector<std::thread> workers;
    mutable std::mutex lock;
    std::condition_variable wake;
    std::deque<Job> jobs;
    std::deque<Done> done;
    bool quit = false;
    void work();
    Ref<Image> make(const Job& job, bool& from_file, bool& woven);
};

}  // namespace godot
