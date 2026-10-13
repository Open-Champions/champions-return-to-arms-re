// rta_scene.cpp - RtaDrawer's scene mode: the game's 3-D scene in world space under a Godot camera.
//
// In the plain mode every vertex is a point of the screen and Godot is a rasteriser.  Here
// the draws that make up the 3-D scene (rtag_draw::scene_first: what the vertex programs
// kicked, and what the CPU projected, into the 3-D surface with a depth test) are given to
// Godot where they were in the world before the game projected them (rtag_scene: the library
// turns the projection round per vertex, tools/godot/lib/scene_tap.cpp), and the viewport of
// the 3-D surface gets a perspective camera placed where the game's camera is.  Everything
// else of that surface - the 2-D layer - is drawn as before, in the list's order.
//
//   - the same meshes and the same shader (variant GS_WORLD: Godot's MODELVIEW / PROJECTION
//     instead of a position written by the shader), still in the list's order with each
//     draw's own depth test and write, the depth being Godot's own now;
//   - the game's colours - texture times its vertex light - are the surface's colour: baked
//     light.  With `lit` on (variant GS_LIT) Godot's ambient light and lights decide how much
//     of that colour arrives: a sun with a shadow map darkens what it does not reach, a
//     point light adds to what is near it;
//   - `shadows`: every opaque draw of the scene has a twin that is only drawn into Godot's
//     shadow maps (the ordered draws themselves are in the transparent pass, which does not
//     cast);
//   - the camera follows the game's (world -> view from g_cameraMatrix, field of view from
//     g_projScale), and can be pulled back along its axis, turned round the point it looks
//     at, or set free - which shows what the game never drew for its own view.
//
// Options (set_scene_option): lit 0|1, shadows 0|1, ambient E (energy of the ambient light
// with lit on), pull_back F (distance to the looked-at point times F), orbit DEGREES (round
// the vertical through that point), raise DEGREES (tilt), focus D (distance of that point
// along the view axis; default: where the player stands in the game's own view, 390).
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/variant/basis.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>

#include <cmath>
#include <cstring>

namespace godot {

using namespace rta_variant;

struct RtaDrawer::Scene {
    bool lit = false, shadows = false;
    double ambient = 1.0, pull_back = 1.0, orbit = 0.0, raise = 0.0, focus = 390.0;
    // this frame
    bool valid = false;
    const rtag_scene* tap = nullptr;
    Transform3D game_camera, camera;
    double fov_y = 50.0;
    std::vector<RID> casters;           // shadow-only instances, in the world's scenario
    size_t casters_used = 0;
    RID caster_scenario;
    // figures
    uint64_t world_draws = 0, world_vertices = 0, flat_draws = 0, frames = 0, frames_without_camera = 0;
};

void RtaDrawer::set_scene_mode(bool on) {
    scene_mode = on;
    if (on && !scene) scene = new Scene;
}

void RtaDrawer::set_scene_option(const String& name, double value) {
    if (!scene) scene = new Scene;
    if (name == "lit") scene->lit = value != 0;
    else if (name == "shadows") scene->shadows = value != 0;
    else if (name == "ambient") scene->ambient = value;
    else if (name == "pull_back") scene->pull_back = value;
    else if (name == "orbit") scene->orbit = value;
    else if (name == "raise") scene->raise = value;
    else if (name == "focus") scene->focus = value;
}

RID RtaDrawer::get_world_scenario() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->scenario : RID();
}

RID RtaDrawer::get_world_camera() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->camera : RID();
}

Dictionary RtaDrawer::get_scene_info() const {
    Dictionary info;
    if (!scene) return info;
    info["valid"] = scene->valid;
    info["game_camera"] = scene->game_camera;
    info["camera"] = scene->camera;
    info["fov_y"] = scene->fov_y;
    info["focus"] = scene->game_camera.origin - scene->game_camera.basis.get_column(2) * (real_t)scene->focus;
    double n = scene->frames ? (double)scene->frames : 1;
    info["figures"] = vformat("scene: %d lists (%d without a camera); per list %.1f draws and %.0f vertices in the world, %.1f draws of the 2-D layer", (int64_t)scene->frames,
                              (int64_t)scene->frames_without_camera, scene->world_draws / n, scene->world_vertices / n, scene->flat_draws / n);
    return info;
}

void RtaDrawer::scene_begin(const rtag_frame& f) {
    Scene& sc = *scene;
    RenderingServer* s = RenderingServer::get_singleton();
    sc.frames++;
    sc.tap = f.scene;
    sc.valid = f.scene && f.scene->valid;
    sc.casters_used = 0;
    Target* world = world_target();
    if (!sc.valid || !world) { if (!sc.valid) sc.frames_without_camera++; return; }
    Pass* pass = world->passes[0];
    // The game's camera space is x right, y down, z forward; Godot's is x right, y up, z back.  world_to_view's
    // rows are the camera's axes in the world.
    const float* m = f.scene->world_to_view;
    Vector3 right(m[0], m[1], m[2]), down(m[4], m[5], m[6]), forward(m[8], m[9], m[10]);
    Vector3 position(f.scene->camera_position[0], f.scene->camera_position[1], f.scene->camera_position[2]);
    sc.game_camera = Transform3D(Basis(right, -down, -forward), position);
    sc.fov_y = f.scene->fov_y_degrees;
    Transform3D camera = sc.game_camera;
    if (sc.pull_back != 1.0 || sc.orbit != 0.0 || sc.raise != 0.0) {
        Vector3 focus = position + forward * (real_t)sc.focus;
        Vector3 offset = position - focus;
        Vector3 up(0, 0, 1);                                // the game's world is z up
        offset = offset.rotated(up, (real_t)Math::deg_to_rad(sc.orbit));
        Vector3 side = up.cross(offset).normalized();
        if (side.length() > 0.5f) offset = offset.rotated(side, (real_t)Math::deg_to_rad(-sc.raise));
        offset *= (real_t)sc.pull_back;
        Vector3 eye = focus + offset;
        camera = Transform3D(Basis(), eye).looking_at(focus, up);
    }
    sc.camera = camera;
    s->camera_set_transform(pass->camera, camera);
    double far_plane = f.scene->far_plane * std::max(1.0, sc.pull_back) * 1.5;
    s->camera_set_perspective(pass->camera, (float)sc.fov_y, f.scene->near_plane, (float)far_plane);
    if (sc.lit) s->environment_set_ambient_light(pass->environment, Color(1, 1, 1), RenderingServer::ENV_AMBIENT_SOURCE_COLOR, (float)sc.ambient);
    // a camera that is not the game's sees past what the game drew: black there, not last frame's picture
    s->environment_set_background(pass->environment, sc.pull_back != 1.0 || sc.orbit != 0.0 || sc.raise != 0.0 ? RenderingServer::ENV_BG_CLEAR_COLOR : RenderingServer::ENV_BG_KEEP);
}

bool RtaDrawer::scene_take(Pass& pass, const rtag_frame& f, const rtag_draw& d, const Target& target, RID texture, float order) {
    Scene& sc = *scene;
    if (!sc.valid || d.scene_first < 0 || !d.count || (uint32_t)d.scene_first + d.count > sc.tap->vertex_count || d.first + d.count > f.vertex_count) {
        sc.flat_draws++;
        return false;
    }
    RenderingServer* s = RenderingServer::get_singleton();
    PackedByteArray positions, attributes;
    positions.resize((int64_t)d.count * 12);
    attributes.resize((int64_t)d.count * 20);
    uint8_t* p = positions.ptrw();
    uint8_t* a = attributes.ptrw();
    const rtag_vertex* v = f.vertices + d.first;
    const rtag_scene_vertex* w = sc.tap->vertices + d.scene_first;
    for (uint32_t k = 0; k < d.count; k++, v++, w++, p += 12, a += 20) {
        memcpy(p, &w->x, 12);
        memcpy(a, &v->r, 4);
        float st[4] = {v->s, v->t, v->q, (float)v->fog / 255.0f};
        memcpy(a + 4, st, 16);
    }
    RID mesh = mesh_for(pass);
    add_surface_bytes(mesh, RenderingServer::PRIMITIVE_TRIANGLES, positions, attributes, (int)d.count);
    uint32_t extra = V_WORLD | (sc.lit ? V_LIT : 0);
    place(pass, material_for(d, target, false, texture, false, extra), order);
    // what is opaque also throws a shadow: a twin of the same mesh that Godot only draws into its shadow maps
    if (sc.shadows && d.depth_write && (!d.blend || d.alpha_test)) {
        RID caster;
        if (sc.caster_scenario != pass.scenario) {          // the surface was made again: instances of the old scenario are gone with it
            for (RID old : sc.casters) s->free_rid(old);
            sc.casters.clear();
            sc.caster_scenario = pass.scenario;
        }
        if (sc.casters_used < sc.casters.size()) caster = sc.casters[sc.casters_used];
        else {
            caster = s->instance_create();
            s->instance_set_scenario(caster, pass.scenario);
            s->instance_set_ignore_culling(caster, true);
            s->instance_geometry_set_cast_shadows_setting(caster, RenderingServer::SHADOW_CASTING_SETTING_SHADOWS_ONLY);
            sc.casters.push_back(caster);
        }
        sc.casters_used++;
        s->instance_set_base(caster, mesh);
        s->instance_geometry_set_material_override(caster, material_for(d, target, false, texture, false, V_WORLD | V_CASTER));
    }
    sc.world_draws++;
    sc.world_vertices += d.count;
    draws_submitted++;
    vertices_submitted += d.count;
    return true;
}

void RtaDrawer::scene_end(const rtag_frame&) {
    Scene& sc = *scene;
    RenderingServer* s = RenderingServer::get_singleton();
    for (size_t k = sc.casters_used; k < sc.casters.size(); k++) s->instance_set_base(sc.casters[k], RID());
}

void RtaDrawer::scene_release() {
    if (!scene) return;
    RenderingServer* s = RenderingServer::get_singleton();
    if (s) for (RID caster : scene->casters) s->free_rid(caster);
    delete scene;
    scene = nullptr;
}

}  // namespace godot
