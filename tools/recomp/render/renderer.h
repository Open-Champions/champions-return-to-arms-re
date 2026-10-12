// renderer.h - the whole renderer above the graphics API as one object: feed it what the
// runtime hands its picture sink (rta::VideoSink, tools/recomp/rt/iface.h) and take a
// FrameList (backend.h) at every vertical blank.  It includes nothing of the runtime, so
// the same object plays back a recorded stream (stream.h).
#pragma once
#include "gs.h"
#include "texindex.h"
#include "vif1.h"

#include <ctime>
#include <functional>
#include <unordered_map>

namespace render {

class Renderer {
  public:
    Vif1 vif;
    Gs gs;
    // Called at each vertical blank with the list built since the last one.  The list is
    // the renderer's; the callee may swap its vectors out but must leave it usable.
    std::function<void(FrameList&)> on_frame;
    uint64_t blanks = 0;

    // VU1's memories: the runtime's (the game also stores into them directly) or, for a
    // playback, the renderer's own.
    explicit Renderer(uint8_t* vu_micro = nullptr, uint8_t* vu_data = nullptr);

    void vif1(const uint32_t* words, size_t count) { vif.feed(words, count); }
    void gif(const uint32_t* words, size_t count) {
        if (!gs.time_paths) { gs.gif(2, words, count / 4); return; }
        timespec a, b;
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
        gs.gif(2, words, count / 4);
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
        gs.stats.path3_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
    }
    void reg(uint32_t address, uint64_t value) { gs.privileged(address, value); }
    void vblank(unsigned field, uint64_t number);

    // A machine resumed from a memory image has no VU1 state: load the main program from
    // the executable's upload packet (940 quadwords at 0x3e5ec0 in main memory) and set
    // what gfx_uploadMicrocode stores directly.  True when the microprogram memory is empty.
    bool needs_program() const;
    void load_program(const uint32_t* packet, size_t words);

    // Main memory (32 MB), when there is one to read: the game's texture headers are looked
    // up in it (texindex.h).  Without it interface art is woven by the size that was sent and
    // a resumed machine draws without the textures its level sent before the image was taken.
    void set_memory(const uint8_t* ram, uint32_t size);
    TexIndex index;

  private:
    uint8_t own_micro[0x4000], own_data[0x4000];
    std::unordered_map<uint32_t, size_t> picture_failed;    // TBP0 -> headers known when its lookup failed
};

}  // namespace render
