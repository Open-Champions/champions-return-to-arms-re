// rta_card.cpp - RtaDrawer's character card: the local player's character alone, for the portal's card (Portrait.texture).
//
// The scene tap hands over every model packet the vertex programs drew, posed and in the world, with the game's normals,
// texel coordinates and the colour the program lit each vertex with (rtag_scene_piece / rtag_scene_full).  The player's
// character is the model packets that stand where the local player stands (rtag_view::player: a cylinder of 34 units
// round the feet, up to 120 above them).  When the host says so (card_focus with capture: scene_view.gd does it while
// the character stands still, every few seconds), the drawer copies those packets - geometry relative to the feet, the
// draw state, its OWN copy of each texture (the game's are freed when their cell goes) - and keeps them as meshes in the
// card's scenario (a SubViewport of the host's: scene_view.gd), with the materials of the scene (the shader's GS_WORLD /
// GS_LIT variant: lit by the card's own lights; the game's vertex light is replaced by one neutral level, so that the
// card looks the same in every level). The host turns it (set_card_turn). In first person card.gd keeps
// the last whole figure: the body switch can hide the player or clip it to the arms.
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/variant/basis.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>

#include <algorithm>
#include <cmath>
#include <cstring>

namespace godot {

using namespace rta_variant;

namespace {
RenderingServer* rs() { return RenderingServer::get_singleton(); }
}

struct RtaDrawer::Card {
    struct Draw {
        rtag_draw state;
        PackedByteArray positions, attributes;
        int corners = 0;
        float lo[3], hi[3];
    };
    struct Held {
        RID mesh, instance, texture;
        rtag_draw state;
        bool textured = false;
    };
    RID scenario;
    bool armed = false;                 // this frame: take the player's packets
    Vector3 feet;
    std::vector<Draw> taking;           // this frame's
    std::vector<Held> held;             // what the card shows
    std::unordered_map<uint32_t, RID> textures;  // one private copy per game texture, shared by its packets
    double turn = 0;
    uint64_t captures = 0, frame_taken = 0;
    int corners_held = 0;
    float height = 0;
};

void RtaDrawer::set_card_scenario(const RID& scenario) {
    if (!card) card = new Card;
    if (card->scenario != scenario) {
        card_clear();
        card->scenario = scenario;
    }
}

void RtaDrawer::card_focus(const Vector3& feet, bool capture) {
    if (!card) card = new Card;
    card->feet = feet;
    card->armed = capture && card->scenario.is_valid();
    card->taking.clear();
}

void RtaDrawer::set_card_turn(double radians) {
    if (!card) return;
    card->turn = radians;
    Transform3D t(Basis(Vector3(0, 0, 1), (real_t)radians), Vector3());
    for (auto& h : card->held) rs()->instance_set_transform(h.instance, t);
}

Dictionary RtaDrawer::get_card_info() const {
    Dictionary d;
    if (!card) return d;
    d["draws"] = (int64_t)card->held.size();
    d["corners"] = card->corners_held;
    d["captures"] = (int64_t)card->captures;
    d["frame"] = (int64_t)card->frame_taken;
    d["height"] = card->height;
    return d;
}

void RtaDrawer::card_clear() {
    if (!card) return;
    RenderingServer* s = rs();
    if (s)
        for (auto& h : card->held) {
            s->free_rid(h.instance);
            s->free_rid(h.mesh);
        }
    if (s) for (auto& t : card->textures) s->free_rid(t.second);
    card->textures.clear();
    card->held.clear();
    card->corners_held = 0;
}

// scene_take, for a draw of model packets from the vertex programs' inputs: the packets that stand where the player stands
void RtaDrawer::card_take(const rtag_scene* tap, const rtag_draw& d, const rtag_scene_piece* pieces, uint32_t count) {
    if (!card || !card->armed) return;
    Card& c = *card;
    Card::Draw out;
    out.state = d;
    for (int a = 0; a < 3; a++) { out.lo[a] = 1e9f; out.hi[a] = -1e9f; }
    std::vector<uint32_t> take;
    for (uint32_t k = 0; k < count; k++) {
        const rtag_scene_piece& p = pieces[k];
        if (p.kind != 2 || p.full_count < 3) continue;
        const rtag_scene_full* v = tap->full + p.full_first;
        double sx = 0, sy = 0, sz = 0;
        for (uint32_t n = 0; n < p.full_count; n++) { sx += v[n].x; sy += v[n].y; sz += v[n].z; }
        float cx = (float)(sx / p.full_count) - c.feet.x, cy = (float)(sy / p.full_count) - c.feet.y, cz = (float)(sz / p.full_count) - c.feet.z;
        if (cx * cx + cy * cy > 34.0f * 34.0f || cz < -12.0f || cz > 120.0f) continue;
        take.push_back(k);
        out.corners += (int)p.full_count;
    }
    if (!out.corners) return;
    out.positions.resize((int64_t)out.corners * 12);
    out.attributes.resize((int64_t)out.corners * 32);
    uint8_t* pp = out.positions.ptrw();
    uint8_t* aa = out.attributes.ptrw();
    for (uint32_t k : take) {
        const rtag_scene_full* v = tap->full + pieces[k].full_first;
        for (uint32_t n = 0; n < pieces[k].full_count; n++, v++, pp += 12, aa += 32) {
            float p[3] = {v->x - c.feet.x, v->y - c.feet.y, v->z - c.feet.z};
            for (int a = 0; a < 3; a++) { out.lo[a] = std::min(out.lo[a], p[a]); out.hi[a] = std::max(out.hi[a], p[a]); }
            memcpy(pp, p, 12);
            // the colour without the level's light (the game lit the vertex for where it stands: blue in a mine, dark
            // in a crypt): one neutral level for every vertex, its alpha kept; the card's own lights give it its shape
            const uint8_t neutral[4] = {0x5c, 0x5c, 0x5c, v->a};
            memcpy(aa, neutral, 4);
            float st[4] = {v->u, v->v, 1.0f, 1.0f};
            memcpy(aa + 4, st, 16);
            memcpy(aa + 20, &v->nx, 12);
        }
    }
    c.taking.push_back(std::move(out));
}

// scene_end: what was taken this frame becomes the card (when it is a whole figure); its materials are kept in use
void RtaDrawer::card_end(const Target& world) {
    if (!card) return;
    Card& c = *card;
    RenderingServer* s = rs();
    int corners = 0;
    float top = 0;
    for (const auto& d : c.taking) { corners += d.corners; top = std::max(top, d.hi[2]); }
    if (c.armed && corners >= 300 && top > 30.0f) {
        card_clear();
        int order = 0;
        for (auto& d : c.taking) {
            Card::Held h;
            h.state = d.state;
            if (d.state.texture && !d.state.tex_is_target) {
                auto cpu = cpu_textures.find(d.state.texture);
                if (cpu == cpu_textures.end()) continue;            // its pixels are not known: left out
                auto shared = c.textures.find(d.state.texture);
                if (shared == c.textures.end()) {
                    PackedByteArray bytes;
                    bytes.resize((int64_t)cpu->second.rgba.size());
                    memcpy(bytes.ptrw(), cpu->second.rgba.data(), cpu->second.rgba.size());
                    RID texture = s->texture_2d_create(Image::create_from_data(cpu->second.w, cpu->second.h, false, Image::FORMAT_RGBA8, bytes));
                    shared = c.textures.emplace(d.state.texture, texture).first;
                }
                h.texture = shared->second;
                h.textured = true;
            } else if (d.state.texture) continue;                   // a surface (a ground shadow, an effect): not the figure
            AABB box(Vector3(d.lo[0], d.lo[1], d.lo[2]), Vector3(d.hi[0] - d.lo[0] + 0.01f, d.hi[1] - d.lo[1] + 0.01f, d.hi[2] - d.lo[2] + 0.01f));
            h.mesh = s->mesh_create();
            add_surface_bytes(h.mesh, RenderingServer::PRIMITIVE_TRIANGLES, d.positions, d.attributes, d.corners, true, &box);
            h.instance = s->instance_create2(h.mesh, c.scenario);
            s->instance_geometry_set_cast_shadows_setting(h.instance, RenderingServer::SHADOW_CASTING_SETTING_OFF);
            s->instance_set_pivot_data(h.instance, (float)order++, false);
            s->instance_set_transform(h.instance, Transform3D(Basis(Vector3(0, 0, 1), (real_t)c.turn), Vector3()));
            c.corners_held += d.corners;
            c.held.push_back(h);
        }
        c.captures++;
        c.frame_taken = frames;
        c.height = top;
    }
    c.taking.clear();
    c.armed = false;
    // the materials: those of the scene for the same state with the card's own texture (looked up every frame, so that
    // the drawer's clean-up of materials nothing used does not take them)
    for (auto& h : c.held) {
        uint32_t extra = V_WORLD | V_NORMALS | (h.state.depth_write ? V_LIT : 0);
        s->instance_geometry_set_material_override(h.instance, material_for(h.state, world, false, h.texture, false, extra));
    }
}

void RtaDrawer::card_free() {
    card_clear();
    delete card;
    card = nullptr;
}

}  // namespace godot
