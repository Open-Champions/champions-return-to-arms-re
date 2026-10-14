// layout.h - the 2-D layer of a wide picture.
//
// Widescreen is made by the game itself (tools/recomp/app/gfx_rt.cpp): its projection is
// narrowed by k = (4/3) / aspect, so the unchanged 1280 x 448 buffer holds a picture of
// the wide view and is shown wide.  Everything the game places in pixels of that buffer
// would be stretched with it by 1 / k.  This puts those things back into shape, in the
// buffer's own coordinates, right after the GS model has made the vertices of a
// primitive:
//
//   3-D geometry (kicked by VU1)          as it is - that is the wide view
//   sprites kicked by VU1 (particles),    narrowed by k about their own centre: they are
//   depth-tested sprites built on the CPU  placed by the projection and sized in pixels
//   2-D (built on the CPU, depth test     menus, text, dialogue: narrowed by k about the
//   "always")                              middle of the screen - the 4:3 layout, centred
//   ... plain, across the whole width     as it is: fades, the letterbox, the clear
//   a picture across the whole width      the 4:3 layout too: a film
//
// and by what the game side says about who made a packet (a mark: the low four bits are
// the kind, the rest a number that differs from call to call):
//
//   EDGE       the HUD: what a call draws is split into clusters along x, and a cluster
//              in the left third keeps its distance to the left edge, one in the right
//              third to the right edge, the rest stays centred
//   WORLD      2-D things at places in the world (names, floating numbers): a cluster is
//              narrowed about its own centre
//   BILLBOARD  quads and fans at places in the world (glows, heat haze): each strip or fan
//              narrowed about its own centre
//   MENU3D     a 3-D figure inside a 4:3 menu (the inventory): the game projects it 4:3
//              and all of it is centred like the menu around it
//
// The scissor of a 2-D primitive (a text box) is moved the same way.
#pragma once
#include "backend.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace render {

struct Layout {
    // M_TEXT: the game's boss meter, one-line message and prompt box - laid out as unmarked 2-D things are (about the
    // centre); the mark only says who drew them, so that a host with a HUD of its own can leave them out (Gs::hide_text)
    enum Mode { M_NONE = 0, M_EDGE = 1, M_WORLD = 2, M_BILLBOARD = 3, M_MENU3D = 4, M_TEXT = 5 };
    enum Anchor { A_NONE, A_CENTRE, A_LEFT, A_RIGHT };
    float k = 1.0f;                     // of the lists being decoded
    uint16_t mark = 0;
    bool enabled = true;                // false: the anamorphic picture as the game drew it (to show the difference)
    float width = 1280.0f, height = 448.0f;     // of the 3-D buffer, logical
    uint64_t moved_2d = 0, moved_sprites = 0, clusters = 0, kept_full = 0;

    bool active() const { return enabled && k != 1.0f; }
    int mode() const { return mark & 15; }
    void set_mark(std::vector<Vertex>& v, uint16_t m) { if (m != mark) { flush(v); mark = m; } }
    void set_k(std::vector<Vertex>& v, float value) { if (value != k) { flush(v); k = value > 0.05f && value <= 1.0f ? value : 1.0f; } }

    static inline float about(float x, float anchor, float k) { return anchor + (x - anchor) * k; }

    // A primitive whose `count` vertices were just appended at `first`.  path: 0 kicked by
    // VU1, else built on the CPU.  strip: a number that changes with every write of PRIM.
    void primitive(std::vector<Vertex>& v, uint32_t first, uint32_t count, int path, bool sprite, bool depth_always, bool textured, bool surface_texture,
                   uint32_t strip) {
        float x0 = v[first].x, x1 = x0, y0 = v[first].y, y1 = y0;
        for (uint32_t i = 1; i < count; i++) {
            x0 = std::min(x0, v[first + i].x); x1 = std::max(x1, v[first + i].x);
            y0 = std::min(y0, v[first + i].y); y1 = std::max(y1, v[first + i].y);
        }
        // plain and across the whole width (fades, the letterbox), or a plain column of the
        // whole height (the game clears its buffers with twenty of those), or a surface
        // drawn back across the width.  A PICTURE across the width - a film's - is not one
        // of these: it is 4:3 and goes to the middle like every other 2-D thing.
        bool across = x0 <= 8.0f && x1 >= width - 8.0f;
        bool full = (across && (!textured || surface_texture)) || (sprite && !textured && y0 <= 4.0f && y1 >= height - 4.0f);
        int m = mode();
        if (m == M_MENU3D) {
            if (full && path != 0) { kept_full++; return; }
            scale(v, first, count, width * 0.5f);
            moved_2d++;
            return;
        }
        if (path == 0) {
            if (sprite) { scale(v, first, count, (x0 + x1) * 0.5f); moved_sprites++; }
            return;
        }
        if (m == M_BILLBOARD) {
            if (sprite) { scale(v, first, count, (x0 + x1) * 0.5f); moved_sprites++; return; }
            if (!pending.empty() && (pending_kind != M_BILLBOARD || pending_strip != strip)) flush(v);
            pending_kind = M_BILLBOARD; pending_strip = strip;
            pending.push_back({first, count, x0, x1});
            return;
        }
        if (!depth_always) {
            if (sprite && !surface_texture && !full) { scale(v, first, count, (x0 + x1) * 0.5f); moved_sprites++; }
            return;
        }
        if (full || surface_texture) { kept_full++; return; }
        if (m == M_EDGE || m == M_WORLD) {
            if (!pending.empty() && pending_kind != m) flush(v);
            pending_kind = m;
            pending.push_back({first, count, x0, x1});
            return;
        }
        scale(v, first, count, width * 0.5f);
        moved_2d++;
    }

    // What becomes of a scissor (x0, x1 in the buffer's pixels) around a 2-D primitive.
    bool scissor(float& x0, float& x1) const {
        if (x0 <= 0.0f && x1 >= width) return false;
        float c = (x0 + x1) * 0.5f, anchor = width * 0.5f;
        if (mode() == M_EDGE) anchor = c < width / 3 ? 0.0f : c > width * 2 / 3 ? width : width * 0.5f;
        x0 = about(x0, anchor, k); x1 = about(x1, anchor, k);
        return true;
    }

    // Decide what was collected for the mark (or strip) that just ended.
    void flush(std::vector<Vertex>& v) {
        if (pending.empty()) return;
        if (pending_kind == M_BILLBOARD) {
            float x0 = pending[0].x0, x1 = pending[0].x1;
            for (const Piece& p : pending) { x0 = std::min(x0, p.x0); x1 = std::max(x1, p.x1); }
            for (const Piece& p : pending) scale(v, p.first, p.count, (x0 + x1) * 0.5f);
            moved_sprites++;
        } else {
            // clusters along x: pieces whose extents lie within `gap` of one another
            float gap = pending_kind == M_EDGE ? 64.0f : 12.0f;
            order.resize(pending.size());
            for (size_t i = 0; i < order.size(); i++) order[i] = (uint32_t)i;
            std::sort(order.begin(), order.end(), [this](uint32_t a, uint32_t b) { return pending[a].x0 < pending[b].x0; });
            size_t start = 0;
            while (start < order.size()) {
                float x0 = pending[order[start]].x0, x1 = pending[order[start]].x1;
                size_t end = start + 1;
                while (end < order.size() && pending[order[end]].x0 <= x1 + gap) { x1 = std::max(x1, pending[order[end]].x1); end++; }
                float c = (x0 + x1) * 0.5f, anchor = c;
                if (pending_kind == M_EDGE) anchor = c < width / 3 ? 0.0f : c > width * 2 / 3 ? width : width * 0.5f;
                for (size_t i = start; i < end; i++) scale(v, pending[order[i]].first, pending[order[i]].count, anchor);
                clusters++;
                start = end;
            }
            moved_2d += pending.size();
        }
        pending.clear();
    }

  private:
    struct Piece { uint32_t first, count; float x0, x1; };
    std::vector<Piece> pending;
    std::vector<uint32_t> order;
    int pending_kind = 0;
    uint32_t pending_strip = 0;
    void scale(std::vector<Vertex>& v, uint32_t first, uint32_t count, float anchor) {
        for (uint32_t i = 0; i < count; i++) v[first + i].x = about(v[first + i].x, anchor, k);
    }
};

}  // namespace render
