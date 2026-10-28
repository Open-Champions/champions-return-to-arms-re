// renderer.cpp - see renderer.h.
#include "renderer.h"
#include "prof.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace render {

Renderer::Renderer(uint8_t* vu_micro, uint8_t* vu_data) {
    memset(own_micro, 0, sizeof(own_micro));
    memset(own_data, 0, sizeof(own_data));
    vif.vu.micro = vu_micro ? vu_micro : own_micro;
    vif.vu.data = vu_data ? vu_data : own_data;
    vif.gs = &gs;
    vif.vu.user = this;
    vif.vu.kick = [](void* user, uint32_t qword) {
        Renderer* r = (Renderer*)user;
        r->gs.xgkick(r->vif.vu.data, qword);
    };
    gs.begin_frame();
    if (getenv("RTA_VU1_INTERPRET")) vif.vu.use_fast = vif.vu.use_translation = false;     // the reference: every program interpreted
    if (getenv("RTA_VU1_OLD")) vif.vu.use_fast = false; // only the older translation of the main program (when one is linked)
    if (getenv("RTA_GS_SLOW")) { gs.fast_runs = false; gs.copy_kicks = true; }    // ... every vertex through the general path
    if (getenv("RTA_VIF_SLOW")) vif.fast_unpack = false;    // ... every UNPACK field by field
    if (getenv("RTA_GS_FAR")) {
        vif.vu.use_fast = false;                        // the registers are printed as the interpreter keeps them                         // debugging: the VIF codes that led to a far vertex, once
        vif.debug_ring = 1;
        gs.on_far_vertex = [this] {
            static bool done = false;
            if (done) return;
            done = true;
            size_t from = vif.ring.size() > 400 ? vif.ring.size() - 400 : 0;
            for (size_t k = from; k < vif.ring.size(); k++) fprintf(stderr, "   vif: %s\n", vif.ring[k].c_str());
            fprintf(stderr, "   vu1: top %03x itop %03x q %g\n", vif.vu.top, vif.vu.itop, vif.vu.q);
            for (int r = 0; r < 32; r++)
                fprintf(stderr, "   vf%02d %g %g %g %g  (%08x %08x %08x %08x)\n", r, vif.vu.vf[r].f[0], vif.vu.vf[r].f[1], vif.vu.vf[r].f[2], vif.vu.vf[r].f[3],
                        vif.vu.vf[r].u[0], vif.vu.vf[r].u[1], vif.vu.vf[r].u[2], vif.vu.vf[r].u[3]);
            for (uint32_t q = 0x3F0; q < 0x400; q++) {
                float f[4]; memcpy(f, vif.vu.data + q * 16, 16);
                fprintf(stderr, "   data[%03x] %g %g %g %g\n", q, f[0], f[1], f[2], f[3]);
            }
            for (uint32_t q = 0; q < 0x100; q++) {
                uint32_t w[4]; float f[4];
                memcpy(w, vif.vu.data + q * 16, 16); memcpy(f, w, 16);
                fprintf(stderr, "   joint[%02x.%u] %08x %08x %08x %08x  %g %g %g %g\n", q >> 2, q & 3, w[0], w[1], w[2], w[3], f[0], f[1], f[2], f[3]);
            }
            // the whole input half, then the strip in the other half (tag at +0x80)
            for (uint32_t q = 0; q < 0x80; q++) {
                uint32_t w[4]; float f[4];
                memcpy(w, vif.vu.data + ((vif.vu.top + q) & 0x3FF) * 16, 16); memcpy(f, w, 16);
                fprintf(stderr, "   data[top+%02x] %08x %08x %08x %08x  %g %g %g %g\n", q, w[0], w[1], w[2], w[3], f[0], f[1], f[2], f[3]);
            }
            uint32_t other = vif.vu.top == 0x27b ? 0x100 : 0x27b;
            for (uint32_t q = 0x80; q < 0x17b; q++) {
                uint32_t w[4]; float f[4];
                memcpy(w, vif.vu.data + ((other + q) & 0x3FF) * 16, 16); memcpy(f, w, 16);
                fprintf(stderr, "   strip[%03x] %08x %08x %08x %08x  %g %g %g %g\n", q - 0x81, w[0], w[1], w[2], w[3], f[0], f[1], f[2], f[3]);
            }
        };
    }
}

void Renderer::vblank(unsigned, uint64_t number) {
    blanks++;
    gs.end_frame(number);
    if (on_frame) { RTA_PROF_SCOPE(prof::P_HOST); on_frame(gs.frame); }
    gs.begin_frame();
}

void Renderer::set_memory(const uint8_t* ram, uint32_t size) {
    index.ram = ram;
    index.size = size;
    gs.picture_size = [this](uint32_t tbp, int& width, int& height) {
        TexHeader h;
        // a block nothing was found for is asked for again only when more headers are
        // known (each failed lookup makes whoever keeps the list look through memory)
        auto failed = picture_failed.find(tbp);
        // (where the list is kept by somebody else a lookup is a walk over the known headers, cheap: asked again at the
        // next blank - the frames in between draw the picture woven by the sent size, garbled; where a failed lookup
        // looks through memory itself, at most every 30 blanks)
        static const uint64_t retry = getenv("RTA_PICTURE_RETRY") ? strtoull(getenv("RTA_PICTURE_RETRY"), nullptr, 10) : 1;   // (a test aid)
        const uint64_t again = index.auto_rescan ? 30 : retry;
        if (failed != picture_failed.end() && failed->second.headers == index.headers.size() && blanks - failed->second.blank < again) return false;
        static const bool log = getenv("RTA_PICTURE_LOG") != nullptr;      // (debugging: which lookups fail, and for how long)
        if (!index.resident_at(tbp, h)) {
            if (log && failed == picture_failed.end()) fprintf(stderr, "picture: block %u not found at blank %llu (%zu headers)\n", tbp, (unsigned long long)blanks, index.headers.size());
            uint64_t first = failed != picture_failed.end() ? failed->second.first : blanks;
            picture_failed[tbp] = {index.headers.size(), blanks, first};
            return false;
        }
        if (log && failed != picture_failed.end())
            fprintf(stderr, "picture: block %u found at blank %llu after %llu blanks: %u x %u (header 0x%x)\n", tbp, (unsigned long long)blanks,
                    (unsigned long long)(blanks - failed->second.first), h.width, h.height, h.address);
        picture_failed.erase(tbp);
        width = h.width; height = h.height;
        return true;
    };
    gs.restore_texture = [this](uint32_t tbp) {
        TexHeader h;
        if (!index.sent_to(tbp, h)) return false;
        if (gs.trace < 0) fprintf(stderr, "restoring the texture at block %u from the header at 0x%x: %u x %u, flags %04x, %u quadwords at 0x%x\n", tbp, h.address,
                                  h.width, h.height, h.flags, h.qwords, h.packet);
        // the packet as the game last sent it, destinations included
        std::vector<uint32_t> words((size_t)h.qwords * 4);
        memcpy(words.data(), index.ram + h.packet, words.size() * 4);
        gs.gif(3, words.data(), h.qwords);
        return true;
    };
}

bool Renderer::needs_program() const {
    for (unsigned k = 0; k < 0x4000; k++) if (vif.vu.micro[k]) return false;
    return true;
}

void Renderer::load_program(const uint32_t* packet, size_t words) {
    // the packet starts with a DMA tag whose upper half already holds VIF codes
    if (words < 4) return;
    vif.feed(packet + 2, words - 2);
    static const uint32_t empty_tag[4] = {0x00008000, 0, 0, 0};    // qword 0x3f6: no data, end of packet
    memcpy(vif.vu.data + 0x3F6 * 16, empty_tag, 16);
}

}  // namespace render
