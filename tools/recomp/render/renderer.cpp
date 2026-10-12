// renderer.cpp - see renderer.h.
#include "renderer.h"

#include <cstdio>
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
}

void Renderer::vblank(unsigned, uint64_t number) {
    blanks++;
    gs.end_frame(number);
    if (on_frame) on_frame(gs.frame);
    gs.begin_frame();
}

void Renderer::set_memory(const uint8_t* ram, uint32_t size) {
    index.ram = ram;
    index.size = size;
    gs.picture_size = [this](uint32_t tbp, int& width, int& height) {
        TexHeader h;
        if (tbp < 4 || !index.resident(tbp - 4, h)) return false;
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
