// pipeline.h - the picture path of the application: what the runtime hands its picture
// sink (rta::VideoSink) is copied on the game's thread, decoded on a thread of its own
// (VIF1, VU1, GS model: render::Renderer) and comes out as one FrameList per vertical
// blank for whoever draws it.
//
//   game threads   Sink::vif1/gif/reg copy into the frame's batch, with the stores the game
//                  made into VU1 memory and the texture headers that changed (both are read
//                  here, where the game stands still); Sink::vblank hands the batch over and
//                  waits while the decoder still holds the one before (this is how the
//                  pacing of the window travels back to the game);
//   decoder        plays batches into a Renderer that owns its VU1 memory and a copy of
//                  main memory; the Renderer's on_frame gets the list.
// The same split as tools/recomp/render/app_main.cpp (rta_render), as a header.
#pragma once
#include "iface.h"
#include "renderer.h"
#include "stream.h"

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <ctime>
#include <mutex>
#include <thread>
#include <vector>

namespace app {

inline double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// One frame of what the sink was handed, in order.
struct Batch {
    struct Record { uint32_t kind, a; uint64_t b; size_t offset, count; };
    std::vector<Record> records;
    std::vector<uint32_t> words;
    void put(uint32_t kind, uint32_t a, uint64_t b, const uint32_t* data, size_t count) {
        records.push_back({kind, a, b, words.size(), count});
        if (count) words.insert(words.end(), data, data + count);
    }
    void clear() { records.clear(); words.clear(); }
};

struct Sink : rta::VideoSink {
    render::Renderer* renderer = nullptr;       // the decoder's; set before the game starts
    // figures (per vertical blank): wall time of the game side, the decoder's own time
    double game_ms = 0, decode_cpu_ms = 0, decode_wall_ms = 0;
    double* waited_downstream_ms = nullptr;     // time on_frame spent waiting, to take out of the decoder's
    uint64_t blanks = 0;

    void start() {
        std::thread decoder([this] { decoder_loop(); });
        decoder.detach();
    }

    void vif1(const uint32_t* words, size_t count) override {
        prepare();
        sync();
        filling.put(render::SK_VIF1, 0, 0, words, count);
    }
    void gif(const uint32_t* words, size_t count) override {
        prepare();
        filling.put(render::SK_GIF, 0, 0, words, count);
    }
    void reg(uint32_t address, uint64_t value) override { filling.put(render::SK_REG, address, value, nullptr, 0); }
    void vblank(unsigned field, uint64_t number) override {
        prepare();
        blanks++;
        if (left_at != 0) game_ms += now_ms() - left_at;
        // the game loads textures as it goes: when the decoder met one it has no header
        // for, look through memory again (it takes milliseconds; the decoder asks once per
        // texture and again only when the list has grown)
        if (renderer->index.missed && blanks - last_scan >= 3) { renderer->index.missed = false; rescan(); }
        filling.put(render::SK_VBLANK, field, number, nullptr, 0);
        std::unique_lock<std::mutex> hold(lock);
        changed.wait(hold, [this] { return !has_waiting; });
        std::swap(waiting, filling);
        has_waiting = true;
        filling.clear();
        changed.notify_all();
        left_at = now_ms();
    }

  private:
    bool first = true;
    Batch filling, waiting;
    std::mutex lock;
    std::condition_variable changed;
    bool has_waiting = false;
    std::vector<uint8_t> ram_copy;              // the decoder's main memory
    std::vector<uint8_t> vu_data, vu_micro;     // VU1 memory as last sent
    render::TexIndex index;                     // over the game's memory, read on the game's thread
    std::vector<uint16_t> blocks;
    uint64_t last_scan = 0;
    double left_at = 0;

    void prepare() {
        if (!first) return;
        first = false;
        ram_copy.assign(rta::memory(), rta::memory() + 0x2000000);
        vu_data.assign(0x4000, 0);
        vu_micro.assign(0x4000, 0);
        index.ram = rta::memory();
        index.size = 0x2000000;
        rescan();
    }
    void rescan() {
        // every header new to the list is sent once; the known ones keep their state
        std::vector<uint32_t> old_headers = index.headers;
        std::vector<uint16_t> old_blocks = blocks;
        index.scan();
        blocks.assign(index.headers.size(), 0xFFFF);
        size_t at = 0;                          // both lists are in address order
        for (size_t k = 0; k < index.headers.size(); k++) {
            while (at < old_headers.size() && old_headers[at] < index.headers[k]) at++;
            if (at < old_headers.size() && old_headers[at] == index.headers[k]) blocks[k] = old_blocks[at];
        }
        last_scan = blanks;
    }
    void sync() {                               // on the game's thread, before a transfer is queued
        const uint8_t* d = rta::vu1_data();
        for (uint32_t q = 0; q < 0x400; q++)
            if (memcmp(d + q * 16, vu_data.data() + q * 16, 16)) {
                memcpy(vu_data.data() + q * 16, d + q * 16, 16);
                filling.put(render::SK_VU1DATA, q, 0, (const uint32_t*)(d + q * 16), 4);
            }
        if (memcmp(rta::vu1_micro(), vu_micro.data(), 0x4000)) {
            memcpy(vu_micro.data(), rta::vu1_micro(), 0x4000);
            filling.put(render::SK_VU1MICRO, 0, 0, (const uint32_t*)rta::vu1_micro(), 0x1000);
        }
        for (size_t k = 0; k < blocks.size(); k++) {
            const uint8_t* h = index.ram + index.headers[k];
            uint16_t block = render::TexIndex::u16(h + 0x18);
            if (block == blocks[k]) continue;
            blocks[k] = block;
            uint32_t words[8];
            memcpy(words, h, 32);
            filling.put(render::SK_RAM, index.headers[k], 0, words, 8);
        }
    }
    void play(const Batch& batch) {
        render::Renderer& r = *renderer;
        for (const Batch::Record& e : batch.records) {
            const uint32_t* w = batch.words.data() + e.offset;
            switch (e.kind) {
            case render::SK_VIF1: r.vif1(w, e.count); break;
            case render::SK_GIF: r.gif(w, e.count); break;
            case render::SK_REG: r.reg(e.a, e.b); break;
            case render::SK_VBLANK: r.vblank(e.a, e.b); break;
            case render::SK_VU1DATA: memcpy(r.vif.vu.data + (e.a & 0x3FF) * 16, w, 16); break;
            case render::SK_VU1MICRO: memcpy(r.vif.vu.micro, w, 0x4000); r.vif.vu.micro_changed(); break;
            case render::SK_RAM:                // a texture header (32 bytes)
                if ((uint64_t)e.a + e.count * 4 <= ram_copy.size()) memcpy(ram_copy.data() + e.a, w, e.count * 4);
                if (std::find(r.index.headers.begin(), r.index.headers.end(), e.a) == r.index.headers.end()) r.index.headers.push_back(e.a);
                break;
            default: break;
            }
        }
    }
    void decoder_loop() {
        Batch mine;
        bool started = false;
        for (;;) {
            {
                std::unique_lock<std::mutex> hold(lock);
                changed.wait(hold, [this] { return has_waiting; });
                std::swap(mine, waiting);
                has_waiting = false;
                changed.notify_all();
            }
            if (!started) {
                started = true;
                renderer->set_memory(ram_copy.data(), (uint32_t)ram_copy.size());
                renderer->index.auto_rescan = false;
                // a machine resumed from a memory image never sent its VU1 program
                if (resumed && renderer->needs_program()) renderer->load_program((const uint32_t*)(ram_copy.data() + 0x3e5ec0), 940 * 4);
            }
            timespec a, b;
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
            double w0 = now_ms(), waited0 = waited_downstream_ms ? *waited_downstream_ms : 0;
            play(mine);
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
            decode_cpu_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
            decode_wall_ms += now_ms() - w0 - ((waited_downstream_ms ? *waited_downstream_ms : 0) - waited0);
            mine.clear();
        }
    }

  public:
    bool resumed = false;                       // the machine starts from a memory image
};

}  // namespace app
