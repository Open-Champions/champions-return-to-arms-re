// recorder.h - a picture sink that writes what it is handed to a stream file (stream.h),
// and passes everything on to another sink when given one.
//
// Besides the calls of the interface it records the two things the renderer reads from
// the machine itself: VU1 memory as the CPU's direct stores changed it (the game writes a
// few constants straight into VU1 data memory, section 4.1 of docs/spec/render-pipeline.md)
// and main memory - all of it once at the start, then the 32 bytes of a texture header
// whenever the game gives the texture other GS blocks (texindex.h says what is read there).
#pragma once
#include "iface.h"
#include "stream.h"
#include "texindex.h"

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
    TexIndex index;
    std::vector<uint16_t> blocks;       // +0x18 of every indexed header as last recorded
    void start() {
        if (started) return;
        started = true;
        // main memory once (the renderer reads the executable's VU1 upload packet and the
        // game's texture headers from it), then the headers' block fields as they change
        const uint32_t* ram = (const uint32_t*)rta::memory();
        for (uint32_t at = 0; at < 0x2000000; at += 0x100000) out.put(SK_RAM, at, 0, ram + at / 4, 0x100000 / 4);
        index.ram = rta::memory();
        index.size = 0x2000000;
        index.scan();
        blocks.assign(index.headers.size(), 0);
        for (size_t k = 0; k < blocks.size(); k++) blocks[k] = TexIndex::u16(index.ram + index.headers[k] + 0x18);
    }
    void sync_headers() {
        for (size_t k = 0; k < blocks.size(); k++) {
            const uint8_t* h = index.ram + index.headers[k];
            if (TexIndex::u16(h + 0x18) == blocks[k]) continue;
            blocks[k] = TexIndex::u16(h + 0x18);
            uint32_t words[8];
            memcpy(words, h, 32);
            out.put(SK_RAM, index.headers[k], 0, words, 8);
        }
    }
    void vif1(const uint32_t* words, size_t count) override {
        if (active()) { start(); sync_vu(); sync_headers(); out.put(SK_VIF1, 0, 0, words, count); }
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
