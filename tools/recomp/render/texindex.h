// texindex.h - finding the game's texture headers in main memory.
//
// The renderer draws from what the game sends, but two things are only in the game's own
// records (docs/formats/model-texture.md, ".tex: header"):
//  - the height of the picture in a texture, which says where the second field of a
//    two-field interface picture starts (the size that was sent is rounded up);
//  - the textures a level uploads once, outside the ring of sixteen resident textures (the
//    environment map, the shadow blob): a machine resumed from a memory image never sees
//    them sent, so they are sent again from the packets still in memory.
// A header is recognised by the mark tex_relocate leaves (+0x0a = 0xa7fb) and a packet
// pointer (+0x10) into memory.  The index is rebuilt when a lookup fails (a level loaded).
#pragma once
#include <atomic>
#include <cstdint>
#include <cstring>
#include <vector>

namespace render {

struct TexHeader {
    uint32_t address = 0;       // of the header
    uint32_t packet = 0;        // of its upload packet
    uint16_t width = 0, height = 0, qwords = 0, flags = 0;
};

class TexIndex {
  public:
    const uint8_t* ram = nullptr;
    uint32_t size = 0;
    std::vector<uint32_t> headers;
    uint64_t scans = 0;
    // false: the list of headers is kept by somebody else (the window program's sink, which
    // reads the game's memory on the game's thread); a failed lookup only raises `missed`
    bool auto_rescan = true;
    std::atomic<bool> missed{false};

    static uint16_t u16(const uint8_t* p) { uint16_t v; memcpy(&v, p, 2); return v; }
    static uint32_t u32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }

    void scan() {
        headers.clear();
        scans++;
        if (!ram) return;
        for (uint32_t h = 0x100000; h + 0x40 <= size; h += 4) {
            if (u16(ram + h + 0x0a) != 0xa7fb) continue;
            uint32_t packet = u32(ram + h + 0x10) & 0x1FFFFFFF;
            uint16_t qwords = u16(ram + h + 6);
            if (packet < 0x100000 || (packet & 3) || !qwords || (uint64_t)packet + (uint64_t)qwords * 16 > size) continue;
            if (u16(ram + h) > 2048 || u16(ram + h + 2) > 2048) continue;
            headers.push_back(h);
        }
    }
    TexHeader read(uint32_t h) const {
        TexHeader t;
        t.address = h;
        t.packet = u32(ram + h + 0x10) & 0x1FFFFFFF;
        t.width = u16(ram + h); t.height = u16(ram + h + 2); t.qwords = u16(ram + h + 6); t.flags = u16(ram + h + 8);
        return t;
    }
    // The header of the texture resident at GS block `block` (TEX0 names block + 4).  A
    // texture that lost its blocks keeps the number, so of several the one used last
    // (+0x1c, the draw frame that last queued it) is taken.
    bool resident(uint32_t block, TexHeader& out, bool rescan = true) {
        if (!ram) return false;
        for (int pass = 0; pass < 2; pass++) {
            bool found = false;
            int32_t best = 0;
            for (uint32_t h : headers) {
                if (u16(ram + h + 0x18) != block || u16(ram + h + 0x0a) != 0xa7fb) continue;
                int32_t used = (int32_t)u32(ram + h + 0x1c);
                if (!found || used > best) { out = read(h); best = used; found = true; }
            }
            if (found) return true;
            missed = true;
            if (pass || !rescan || !auto_rescan) break;
            scan();
        }
        return false;
    }
    // A header whose packet transfers its picture to block `tbp`: the destination the game
    // patched into the packet when it sent it (BITBLTBUF, +0x14 for a 32-bit picture, +0x474
    // behind a 256-colour palette, +0xb4 behind a 16-colour one).
    bool sent_to(uint32_t tbp, TexHeader& out) {
        if (!ram) return false;
        if (headers.empty()) scan();
        for (uint32_t h : headers) {
            TexHeader t = read(h);
            uint32_t at = (t.flags & 0x0004) ? 0x474 : (t.flags & 0x2000) ? 0xb4 : 0x14;
            if ((uint64_t)t.packet + at + 2 > size || (uint32_t)t.qwords * 16 < at + 2) continue;
            if (u16(ram + t.packet + at) == tbp && ram[t.packet + at + 4] == 0x50) { out = t; return true; }
        }
        return false;
    }
};

}  // namespace render
