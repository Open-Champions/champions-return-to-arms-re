// texpack.h - pictures drawn in place of the game's textures, and mip maps for the game's
// own: the part of the work that is not graphics calls.
//
// A pack is a folder of PNG files named as the emulator-based build names textures
// (tools/play-net/README.md, "Texture dump and replacement" and "Upscaled art"; made by
// tools/play-net/upscale.py): "<figure>-<palette>-p<format>-<width>x<height>.png", of any
// whole multiple of that size, alpha as on the console (128 = opaque).  The folder is
// listed once.  A file is read when its texture is first drawn, by threads of low
// priority: until it is there the game's own texture is drawn.
//
// What a reader hands back is ready for the graphics card: the picture - or only the part
// of it the game draws with, plus a margin - and its mip maps.  A level texture is a page
// of which the game uses a corner; the rest would cost video memory for nothing, and mip
// maps made from the whole page would bleed the rest into the corner.  The same is done,
// without a file, for the game's own textures (it has no mip maps at all), which is what
// gives the 3-D scene mip maps and makes anisotropic filtering worth having.
//
// Two-field interface pictures: upscale.py writes the woven, enlarged picture twice into a
// file of twice the vertical factor.  Such a file is known by that (factor in y = 2 x
// factor in x) and is always held whole; the backend samples its first copy with the
// woven line as the coordinate.
#pragma once
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace render {

struct PictureJob {
    uint32_t texture = 0;               // whose picture
    uint64_t serial = 0;                // the answer carries it back
    std::string file;                   // read this PNG ...
    std::shared_ptr<const std::vector<uint8_t>> own;    // ... or take these pixels (RGBA8, own_width x own_height)
    int own_width = 0, own_height = 0;
    int texels_w = 0, texels_h = 0;     // the texels the picture is stretched over (the size in its name)
    bool part = false;                  // only box (texels: x0, y0, x1, y1) and `margin` texels round it
    float box[4] = {0, 0, 0, 0};
    int margin = 4;
    bool first = false;                 // ahead of the others (interface art: small, and always on the screen)
};

struct PictureResult {
    uint32_t texture = 0;
    uint64_t serial = 0;
    bool ok = false;
    bool from_file = false;
    bool two_field = false;             // a two-field interface picture laid out by upscale.py
    bool whole = true;
    int part[4] = {0, 0, 0, 0};         // the texels held: x0, y0, x1, y1
    struct Level { int width = 0, height = 0; std::vector<uint8_t> rgba; };
    std::vector<Level> levels;
    size_t bytes() const { size_t n = 0; for (const Level& l : levels) n += l.rgba.size(); return n; }
};

class TexPack {
  public:
    ~TexPack() { stop(); }
    // List `folder` (or its "replace" subfolder when it has one).  Returns the number of pictures.
    size_t open(const std::string& folder);
    const std::string& folder() const { return dir; }
    size_t size() const { return names.size(); }
    // The file for a texture of this name, or an empty string.
    std::string find(uint64_t figure, uint64_t palette_figure, uint32_t format, int width, int height) const;

    void start(int threads = 3);
    void stop();
    void ask(PictureJob job);
    void forget(uint32_t texture);      // jobs for it that have not started are dropped
    bool take(PictureResult& out);      // one finished picture, if any
    size_t waiting() const;
    int outstanding() const { return open_jobs.load(); }    // asked for and not yet taken (or dropped)

    // Made in the calling thread (the game's own small textures).
    static PictureResult make(const PictureJob& job);

  private:
    std::string dir;
    std::unordered_map<std::string, bool> names;
    std::vector<std::thread> workers;
    mutable std::mutex lock;
    std::condition_variable wake;
    std::deque<PictureJob> jobs;
    std::deque<PictureResult> done;
    bool quit = false;
    std::atomic<int> open_jobs{0};
    void work();
};

}  // namespace render
