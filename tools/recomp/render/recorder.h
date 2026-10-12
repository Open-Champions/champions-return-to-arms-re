// recorder.h - a picture sink that writes what it is handed to a stream file (stream.h),
// and passes everything on to another sink when given one.
//
// Besides the calls of the interface it records the two things the renderer reads from
// the machine itself: VU1 memory as the CPU's direct stores changed it (the game writes a
// few constants straight into VU1 data memory, section 4.1 of docs/spec/render-pipeline.md)
// and, once, the main VU1 program's upload packet from the executable's data (a resumed
// memory image does not carry VU1 memory, so the renderer loads the program from there).
#pragma once
#include "iface.h"
#include "stream.h"

namespace render {

struct Recorder : rta::VideoSink {
    StreamWriter out;
    rta::VideoSink* next = nullptr;
    uint64_t first_frame = 0, last_frame = ~0ull, frames = 0;    // displayed frames to record
    std::vector<uint8_t> vu_data, vu_micro;
    bool started = false;

    bool active() const { return frames >= first_frame && frames <= last_frame; }
    void sync_vu() {
        // what the CPU stored directly into VU1 memory since the last look
        if (vu_data.empty()) { vu_data.assign(0x4000, 0); vu_micro.assign(0x4000, 0); }
        const uint8_t* d = rta::vu1_data();
        const uint8_t* m = rta::vu1_micro();
        for (uint32_t q = 0; q < 0x400; q++)
            if (memcmp(d + q * 16, vu_data.data() + q * 16, 16)) {
                memcpy(vu_data.data() + q * 16, d + q * 16, 16);
                out.put(SK_VU1DATA, q, 0, (const uint32_t*)(d + q * 16), 4);
            }
        if (memcmp(m, vu_micro.data(), 0x4000)) {
            memcpy(vu_micro.data(), m, 0x4000);
            out.put(SK_VU1MICRO, 0, 0, (const uint32_t*)m, 0x1000);
        }
    }
    void start() {
        if (started) return;
        started = true;
        // the executable's VU1 upload packet (0x3e5ec0, 940 quadwords) and the two words
        // the renderer needs to know a resumed image by
        out.put(SK_RAM, 0x3e5ec0, 0, (const uint32_t*)(rta::memory() + 0x3e5ec0), 940 * 4);
    }
    void vif1(const uint32_t* words, size_t count) override {
        if (active()) { start(); sync_vu(); out.put(SK_VIF1, 0, 0, words, count); }
        if (next) next->vif1(words, count);
    }
    void vif0(const uint32_t* words, size_t count) override {
        if (active()) { start(); out.put(SK_VIF0, 0, 0, words, count); }
        if (next) next->vif0(words, count);
    }
    void gif(const uint32_t* words, size_t count) override {
        if (active()) { start(); out.put(SK_GIF, 0, 0, words, count); }
        if (next) next->gif(words, count);
    }
    void reg(uint32_t address, uint64_t value) override {
        if (active()) { start(); out.put(SK_REG, address, value, nullptr, 0); }
        if (next) next->reg(address, value);
    }
    void vblank(unsigned field, uint64_t number) override {
        if (active()) { start(); out.put(SK_VBLANK, field, number, nullptr, 0); }
        if (next) next->vblank(field, number);
    }
    bool frame(uint64_t number, unsigned buffer) override {
        frames++;
        if (active()) { start(); out.put(SK_FRAME, buffer, number, nullptr, 0); }
        if (frames == last_frame + 1 && out.file) fflush(out.file);
        return next ? next->frame(number, buffer) : false;
    }
};

}  // namespace render
