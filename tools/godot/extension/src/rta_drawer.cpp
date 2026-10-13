// rta_drawer.cpp - see rta_drawer.h.
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/classes/time.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/aabb.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace godot {

namespace {

using namespace rta_variant;

RenderingServer* rs() { return RenderingServer::get_singleton(); }

// shader variants (gs_draw.gdshaderinc)


const AABB EVERYWHERE(Vector3(-1e6, -1e6, -1e6), Vector3(2e6, 2e6, 2e6));

}  // namespace

RtaDrawer::RtaDrawer() {}
RtaDrawer::~RtaDrawer() { release(); }

void RtaDrawer::setup(const Ref<RtaMachine>& p_machine, const RID& p_parent_viewport, const Vector2i& p_output_size, int p_samples) {
    machine = p_machine;
    parent_viewport = p_parent_viewport;
    output_size = p_output_size;
    samples = p_samples;
    // test aids: the two conventions the drawer depends on, to be turned over from outside
    if (getenv("RTA_GODOT_FLIP")) flip_y = (float)atof(getenv("RTA_GODOT_FLIP"));
    if (getenv("RTA_GODOT_TEXFLIP")) flip_surfaces = atoi(getenv("RTA_GODOT_TEXFLIP")) != 0;
    if (getenv("RTA_GODOT_NO_INVERTED")) inverted_depth_ok = false;
    if (getenv("RTA_GODOT_BIAS")) world_bias = (float)atof(getenv("RTA_GODOT_BIAS"));
    if (getenv("RTA_GODOT_STORED")) stored_colours = atoi(getenv("RTA_GODOT_STORED")) != 0;
}

void RtaDrawer::set_shader_code(const String& code) { shader_code = code.utf8().get_data(); }

// ---- surfaces -------------------------------------------------------------------------------

void RtaDrawer::size_target(Target& target) {
    // as the OpenGL backend: a surface as large as the picture is drawn at the output size,
    // any other at its own size times what the picture is enlarged by
    int scale = std::max(1, (int)std::lround((double)output_size.y / 448.0));
    target.pw = target.screen ? output_size.x : target.lw * scale;
    target.ph = target.screen ? output_size.y : target.lh * scale;
    // scene mode: the 3-D surface is looked at through a Godot camera, whose picture has square pixels - the
    // viewport takes the shape of the view (the present pass reads it by its logical size, whatever its pixels)
    if (scene_mode && target.screen && target.lw >= 1024) {
        double shape = machine.is_valid() && machine->current() ? machine->get_frame_aspect() : 4.0 / 3.0;
        target.pw = std::max(16, (int)std::lround(output_size.y * shape));
    }
    for (Pass* pass : target.passes) {
        rs()->viewport_set_size(pass->viewport, target.pw, target.ph);
        pass->drawn_once = false;
    }
}

RtaDrawer::Pass* RtaDrawer::make_pass(Target& target) {
    Pass* pass = new Pass;
    RenderingServer* s = rs();
    pass->scenario = s->scenario_create();
    pass->environment = s->environment_create();
    s->environment_set_background(pass->environment, RenderingServer::ENV_BG_KEEP);     // what was drawn stays: the GS never clears
    s->scenario_set_environment(pass->scenario, pass->environment);
    pass->camera = s->camera_create();
    s->camera_set_orthogonal(pass->camera, 2.0, 0.05, 100.0);
    pass->viewport = s->viewport_create();
    s->viewport_set_size(pass->viewport, target.pw, target.ph);
    s->viewport_set_scenario(pass->viewport, pass->scenario);
    s->viewport_attach_camera(pass->viewport, pass->camera);
    s->viewport_set_clear_mode(pass->viewport, RenderingServer::VIEWPORT_CLEAR_NEVER);
    s->viewport_set_update_mode(pass->viewport, RenderingServer::VIEWPORT_UPDATE_DISABLED);
    s->viewport_set_parent_viewport(pass->viewport, parent_viewport);      // rendered before the window's own viewport
    if (samples >= 2 && target.screen && target.lw >= 1024)
        s->viewport_set_msaa_3d(pass->viewport, samples >= 8 ? RenderingServer::VIEWPORT_MSAA_8X : samples >= 4 ? RenderingServer::VIEWPORT_MSAA_4X : RenderingServer::VIEWPORT_MSAA_2X);
    pass->texture = s->viewport_get_texture(pass->viewport);
    target.passes.push_back(pass);
    all_passes.push_back(pass);
    return pass;
}

void RtaDrawer::free_pass(Pass* pass) {
    RenderingServer* s = rs();
    for (RID instance : pass->instances) s->free_rid(instance);
    for (RID mesh : pass->meshes) s->free_rid(mesh);
    s->viewport_set_active(pass->viewport, false);
    s->free_rid(pass->viewport);
    s->free_rid(pass->camera);
    s->free_rid(pass->scenario);
    s->free_rid(pass->environment);
    all_passes.erase(std::remove(all_passes.begin(), all_passes.end(), pass), all_passes.end());
    delete pass;
}

// ---- shaders and materials ------------------------------------------------------------------

RID RtaDrawer::shader_for(uint32_t variant) {
    auto found = shaders.find(variant);
    if (found != shaders.end()) return found->second->get_rid();
    std::string code = "shader_type spatial;\n";
    if (variant & V_BLEND_SUB) code += "#define GS_BLEND_SUB\n";
    if (variant & V_DEPTH_ALWAYS) code += "#define GS_DEPTH_ALWAYS\n";
    if (variant & V_DEPTH_INVERTED) code += "#define GS_DEPTH_INVERTED\n";
    if (variant & V_DEPTH_WRITE) code += "#define GS_DEPTH_WRITE\n";
    if (variant & V_LINEAR) code += "#define GS_LINEAR\n";
    if (variant & V_REPEAT) code += "#define GS_REPEAT\n";
    if (variant & V_WORLD) code += "#define GS_WORLD\n";
    if (variant & V_LIT) code += "#define GS_LIT\n";
    if (variant & V_CASTER) code += "#define GS_CASTER\n";
    if (variant & V_NORMALS) code += "#define GS_NORMALS\n";
    if (stored_colours) code += "#define GS_STORED_COLOURS\n";
    code += shader_code;
    Ref<Shader> shader;
    shader.instantiate();
    shader->set_code(String::utf8(code.c_str()));
    shaders[variant] = shader;
    return shader->get_rid();
}

RID RtaDrawer::material_for(const rtag_draw& d, const Target& target, bool inverted, RID texture, bool texture_flipped, uint32_t extra) {
    // the blend: colour = (A - B) * C + D, as tools/recomp/render/backend_gl.cpp sets it up
    float sc = 0, sk = 1, dc = 0, dk = 0, fix = 1.0f;
    int blend_c = 2;
    bool subtract = false;
    if (d.blend) {
        sc = (d.ba == 0 ? 1.0f : 0.0f) - (d.bb == 0 ? 1.0f : 0.0f); sk = d.bd == 0 ? 1.0f : 0.0f;
        dc = (d.ba == 1 ? 1.0f : 0.0f) - (d.bb == 1 ? 1.0f : 0.0f); dk = d.bd == 1 ? 1.0f : 0.0f;
        bool src_negative = sc < 0 && sk == 0, dst_negative = dc < 0 && dk == 0;
        if (src_negative && dst_negative) { sc = 0; dc = 0; }
        else if (src_negative) subtract = true;         // destination x df - source x sf: exact where df is 1
        else if (dst_negative) approximated++;          // source x sf - destination x df: drawn as their sum
        blend_c = d.bc;
        fix = (float)d.fix / 128.0f;
    }
    uint32_t variant = extra;
    if (!(extra & V_CASTER)) {
        if (subtract) variant |= V_BLEND_SUB;
        if (d.ztst == 1) { if (d.depth_write) { if (inverted) variant |= V_DEPTH_INVERTED; } else variant |= V_DEPTH_ALWAYS; }
        if (d.depth_write) variant |= V_DEPTH_WRITE;
    }
    bool textured = texture.is_valid();
    if (textured && d.linear) variant |= V_LINEAR;
    if (textured && d.wrap_s == RTAG_WRAP_REPEAT && d.wrap_t == RTAG_WRAP_REPEAT) variant |= V_REPEAT;

    float sx = (float)target.pw / target.lw, sy = (float)target.ph / target.lh;
    float x0 = std::floor(d.scissor[0] * sx + 0.5f), y0 = std::floor(d.scissor[1] * sy + 0.5f);
    float x1 = std::floor(d.scissor[2] * sx + 0.5f), y1 = std::floor(d.scissor[3] * sy + 0.5f);
    if (d.scissor_moved) { x0 = std::floor(d.scissor_x[0] * sx + 0.5f); x1 = std::floor(d.scissor_x[1] * sx + 0.5f); }

    struct Key {
        uint32_t variant; int64_t texture; uint32_t target; float scissor[4];
        uint8_t textured, tfx, tcc, wrap_s, wrap_t, texa_mode, ta0, ta1, aem, atst, aref, fog, fog_colour[3], blend_c, mask_rgb, flipped;
        float st_scale[2], tex_size[2], tex_offset[2], region[4], weave_half, blend[4], fix;
    } key;
    memset(&key, 0, sizeof key);
    key.variant = variant; key.texture = textured ? texture.get_id() : 0; key.target = target.id;
    key.scissor[0] = x0; key.scissor[1] = y0; key.scissor[2] = x1; key.scissor[3] = y1;
    key.textured = textured; key.atst = d.alpha_test ? d.atst : 1; key.aref = d.aref; key.fog = d.fog; memcpy(key.fog_colour, d.fog_colour, 3);
    key.blend_c = (uint8_t)blend_c; key.mask_rgb = d.mask_rgb; key.flipped = texture_flipped;
    key.blend[0] = sc; key.blend[1] = sk; key.blend[2] = dc; key.blend[3] = dk; key.fix = fix;
    if (textured) {
        key.tfx = d.tfx; key.tcc = d.tcc; key.wrap_s = d.wrap_s; key.wrap_t = d.wrap_t;
        key.texa_mode = d.tex_is_target ? d.texa_mode : 0; key.ta0 = d.ta0; key.ta1 = d.ta1; key.aem = d.aem;
        memcpy(key.st_scale, d.st_scale, sizeof key.st_scale); memcpy(key.tex_size, d.tex_size, sizeof key.tex_size);
        memcpy(key.tex_offset, d.tex_offset, sizeof key.tex_offset); memcpy(key.region, d.region, sizeof key.region);
        key.weave_half = d.weave_half;
    }
    std::string bytes((const char*)&key, sizeof key);
    auto found = materials.find(bytes);
    if (found != materials.end()) { found->second.last_used = frames; return found->second.rid; }

    RenderingServer* s = rs();
    RID material = s->material_create();
    s->material_set_shader(material, shader_for(variant));
    s->material_set_param(material, "target_size", Vector2((float)target.lw, (float)target.lh));
    s->material_set_param(material, "target_scale", Vector2(sx, sy));
    s->material_set_param(material, "flip_y", flip_y);
    s->material_set_param(material, "scissor", Quaternion(x0, y0, x1, y1));
    s->material_set_param(material, "textured", textured ? 1 : 0);
    if (textured) {
        s->material_set_param(material, "tex", texture);
        s->material_set_param(material, "tfx", (int)d.tfx);
        s->material_set_param(material, "tcc", d.tcc ? 1 : 0);
        s->material_set_param(material, "st_scale", Vector2(d.st_scale[0], d.st_scale[1]));
        s->material_set_param(material, "tex_size", Vector2(d.tex_size[0], d.tex_size[1]));
        s->material_set_param(material, "tex_offset", Vector2(d.tex_offset[0], d.tex_offset[1]));
        s->material_set_param(material, "tex_flip", texture_flipped ? 1.0f : 0.0f);
        s->material_set_param(material, "wrap_mode", Vector2i(d.wrap_s, d.wrap_t));
        s->material_set_param(material, "region", Quaternion(d.region[0], d.region[1], d.region[2], d.region[3]));
        s->material_set_param(material, "weave_half", d.weave_half);
        s->material_set_param(material, "texa", Quaternion(d.tex_is_target ? (float)d.texa_mode : 0.0f, (float)d.ta0, (float)d.ta1, d.aem ? 1.0f : 0.0f));
    }
    s->material_set_param(material, "fog_colour", Quaternion((float)d.fog_colour[0], (float)d.fog_colour[1], (float)d.fog_colour[2], d.fog ? 1.0f : 0.0f));
    s->material_set_param(material, "atst", d.alpha_test ? (int)d.atst : 1);
    s->material_set_param(material, "aref", (float)d.aref);
    s->material_set_param(material, "blend", Quaternion(sc, sk, dc, dk));
    s->material_set_param(material, "blend_c", blend_c);
    s->material_set_param(material, "fix", fix);
    s->material_set_param(material, "mask_rgb", d.mask_rgb ? 1.0f : 0.0f);
    if (extra & V_WORLD) s->material_set_param(material, "depth_bias", d.depth_write ? 0.0f : world_bias);       // what lies on a surface is drawn on it
    materials[bytes] = {material, frames};
    materials_made++;
    return material;
}

// ---- meshes and instances -------------------------------------------------------------------

RID RtaDrawer::mesh_for(Pass& pass) {
    if (pass.used < pass.meshes.size()) {
        rs()->mesh_clear(pass.meshes[pass.used]);
        return pass.meshes[pass.used];
    }
    RID mesh = rs()->mesh_create();
    pass.meshes.push_back(mesh);
    meshes_made++;
    return mesh;
}

// The instance for the mesh at pass.used (made by mesh_for), drawn `order`-th in its viewport.
RID RtaDrawer::place(Pass& pass, RID material, float order) {
    RenderingServer* s = rs();
    RID mesh = pass.meshes[pass.used];
    s->mesh_surface_set_material(mesh, 0, material);
    RID instance;
    if (pass.used < pass.instances.size()) instance = pass.instances[pass.used];
    else {
        instance = s->instance_create();
        s->instance_set_scenario(instance, pass.scenario);
        s->instance_set_ignore_culling(instance, true);
        s->instance_geometry_set_cast_shadows_setting(instance, RenderingServer::SHADOW_CASTING_SETTING_OFF);
        pass.instances.push_back(instance);
    }
    s->instance_set_base(instance, mesh);
    // the transparent pass draws far to near; a larger offset is "nearer": the list's order
    s->instance_set_pivot_data(instance, order, false);
    pass.used++;
    return instance;
}

void RtaDrawer::add_surface_bytes(RID mesh, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count, bool normals) {
    Dictionary surface;
    surface["primitive"] = primitive;
    surface["format"] = (int64_t)(RenderingServer::ARRAY_FORMAT_VERTEX | RenderingServer::ARRAY_FORMAT_COLOR | RenderingServer::ARRAY_FORMAT_CUSTOM0 |
                                  ((int64_t)RenderingServer::ARRAY_CUSTOM_RGBA_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM0_SHIFT) |
                                  RenderingServer::ARRAY_FLAG_FORMAT_CURRENT_VERSION);
    // scene mode: the game's normal, world space, as three more floats per vertex (after the colour and the texture coordinates)
    if (normals) surface["format"] = (int64_t)surface["format"] | RenderingServer::ARRAY_FORMAT_CUSTOM1 |
                                     ((int64_t)RenderingServer::ARRAY_CUSTOM_RGB_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM1_SHIFT);
    surface["vertex_data"] = positions;
    surface["attribute_data"] = attributes;
    surface["vertex_count"] = count;
    surface["aabb"] = EVERYWHERE;
    rs()->mesh_add_surface(mesh, surface);
}

void RtaDrawer::add_draw(Pass& pass, const rtag_frame& frame, const rtag_draw& d, const Target& target, RID texture, bool texture_flipped, float order) {
    if (!d.count || d.first + d.count > frame.vertex_count) return;
    if (d.ztst == 0) { skipped++; return; }             // the depth test never passes
    // position (3 floats) in one buffer; colour (4 bytes) and texture coordinates with the fog (4 floats) in the other
    PackedByteArray positions, attributes;
    positions.resize((int64_t)d.count * 12);
    attributes.resize((int64_t)d.count * 20);
    uint8_t* p = positions.ptrw();
    uint8_t* a = attributes.ptrw();
    const rtag_vertex* v = frame.vertices + d.first;
    for (uint32_t k = 0; k < d.count; k++, v++, p += 12, a += 20) {
        memcpy(p, &v->x, 12);
        memcpy(a, &v->r, 4);
        float st[4] = {v->s, v->t, v->q, (float)v->fog / 255.0f};
        memcpy(a + 4, st, 16);
    }
    RenderingServer::PrimitiveType primitive = d.prim == RTAG_TRIANGLES ? RenderingServer::PRIMITIVE_TRIANGLES : d.prim == RTAG_LINES ? RenderingServer::PRIMITIVE_LINES
                                                                                                                                        : RenderingServer::PRIMITIVE_POINTS;
    bool twice = d.ztst == 1 && d.depth_write && inverted_depth_ok;     // "always, and write": where the default test passes, and where it fails
    if (twice) depth_always_writes++;
    for (int n = 0; n < (twice ? 2 : 1); n++) {
        RID mesh = mesh_for(pass);
        add_surface_bytes(mesh, primitive, positions, attributes, (int)d.count);
        place(pass, material_for(d, target, n == 1, texture, texture_flipped), order + 0.25f * n);
    }
    draws_submitted++;
    vertices_submitted += d.count;
}

// A rectangle of one surface copied into another: a textured quad.
void RtaDrawer::add_copy(Pass& pass, const rtag_draw& d, const Target& target, const Target& source, RID texture, float order) {
    rtag_draw quad;
    memset(&quad, 0, sizeof quad);
    quad.kind = RTAG_DRAW; quad.prim = RTAG_TRIANGLES; quad.count = 6;
    quad.scissor[2] = target.lw; quad.scissor[3] = target.lh;
    quad.texture = 1; quad.tex_is_target = 1; quad.linear = 1; quad.wrap_s = quad.wrap_t = RTAG_WRAP_CLAMP;
    quad.tex_size[0] = (float)source.lw; quad.tex_size[1] = (float)source.lh;
    quad.st_scale[0] = quad.st_scale[1] = 1;
    quad.region[1] = (float)source.lw; quad.region[3] = (float)source.lh;
    quad.tfx = 1; quad.tcc = 1; quad.atst = 1; quad.ztst = 1; quad.fix = 0x80;
    rtag_vertex corners[6];
    const float x0 = (float)d.copy_dst[0], y0 = (float)d.copy_dst[1], x1 = x0 + d.copy_dst[2], y1 = y0 + d.copy_dst[3];
    const float s0 = (float)d.copy_src[0], t0 = (float)d.copy_src[1], s1 = s0 + d.copy_src[2], t1 = t0 + d.copy_src[3];
    const float xs[6] = {x0, x1, x0, x1, x1, x0}, ys[6] = {y0, y0, y1, y0, y1, y1}, ss[6] = {s0, s1, s0, s1, s1, s0}, ts[6] = {t0, t0, t1, t0, t1, t1};
    for (int k = 0; k < 6; k++) {
        memset(&corners[k], 0, sizeof corners[k]);
        corners[k].x = xs[k]; corners[k].y = ys[k]; corners[k].s = ss[k]; corners[k].t = ts[k]; corners[k].q = 1;
        corners[k].r = corners[k].g = corners[k].b = corners[k].a = 0x80; corners[k].fog = 255;
    }
    rtag_frame one;
    memset(&one, 0, sizeof one);
    one.vertices = corners; one.vertex_count = 6;
    add_draw(pass, one, quad, target, texture, flip_surfaces, order);
}

RtaDrawer::Target* RtaDrawer::world_target() {
    for (auto& entry : targets) if (entry.second.screen && entry.second.lw >= 1024 && !entry.second.passes.empty()) return &entry.second;
    return nullptr;
}

// ---- a frame --------------------------------------------------------------------------------

void RtaDrawer::submit() {
    if (machine.is_null() || !machine->current()) return;
    const rtag_frame& f = *machine->current();
    RenderingServer* s = rs();
    uint64_t t0 = Time::get_singleton()->get_ticks_usec();
    frames++;

    for (uint32_t k = 0; k < f.texture_count; k++) {
        const rtag_texture& t = f.textures[k];
        PackedByteArray bytes;
        bytes.resize((int64_t)t.width * t.height * 4);
        memcpy(bytes.ptrw(), t.rgba, (size_t)t.width * t.height * 4);
        Ref<Image> image = Image::create_from_data(t.width, t.height, false, Image::FORMAT_RGBA8, bytes);
        auto old = textures.find(t.id);
        if (old != textures.end()) s->free_rid(old->second);
        textures[t.id] = s->texture_2d_create(image);
        textures_made++;
    }
    for (uint32_t k = 0; k < f.target_count; k++) {
        const rtag_target& info = f.targets[k];
        Target& target = targets[info.id];
        target.id = info.id; target.lw = info.width; target.lh = info.height; target.screen = info.screen != 0;
        size_target(target);
        if (target.passes.empty()) target.latest = make_pass(target);
    }

    // ---- the runs: which viewport renders which draws, and in what order the viewports go ----
    std::vector<Node> nodes;
    std::unordered_map<uint32_t, int> current;          // target id -> its open node
    struct Read { int reader; uint32_t target; int node; size_t at; };
    std::vector<Read> reads;
    std::vector<int> node_of(f.draw_count, -1);
    std::vector<RID> texture_of(f.draw_count);
    std::vector<Pass*> used_this_frame;
    for (uint32_t i = 0; i < f.draw_count; i++) {
        const rtag_draw& d = f.draws[i];
        auto found = targets.find(d.target);
        if (found == targets.end()) continue;
        Target& target = found->second;
        int n;
        auto open = current.find(d.target);
        bool splittable = !target.screen;
        if (open != current.end() && !(nodes[open->second].sealed && splittable)) n = open->second;
        else {
            Node node;
            node.target = &target;
            node.first_draw = i;
            if (!splittable) node.pass = target.passes[0];
            else {
                // a pass nobody used yet this frame, and not the one that holds what the last frame left
                node.pass = nullptr;
                for (Pass* pass : target.passes)
                    if (pass != target.latest && std::find(used_this_frame.begin(), used_this_frame.end(), pass) == used_this_frame.end()) { node.pass = pass; break; }
                if (!node.pass) node.pass = make_pass(target);
            }
            used_this_frame.push_back(node.pass);
            nodes.push_back(node);
            n = (int)nodes.size() - 1;
            current[d.target] = n;
        }
        nodes[n].last_draw = i;
        nodes[n].count++;
        node_of[i] = n;
        // what the draw reads
        bool reads_surface = d.kind == RTAG_COPY || (d.texture && d.tex_is_target);
        if (reads_surface) {
            auto source = targets.find(d.texture);
            if (source == targets.end() || source->second.id == target.id) { if (source != targets.end()) approximated++; continue; }
            Target& from = source->second;
            auto from_open = current.find(from.id);
            if (from_open == current.end()) {
                texture_of[i] = from.latest ? from.latest->texture : RID();        // what the last list left there
                reads.push_back({n, from.id, -1, i});
            } else {
                Node& writer = nodes[from_open->second];
                texture_of[i] = writer.pass->texture;
                if (from.screen) reads.push_back({n, from.id, from_open->second, i});       // before or after it: known when the list is through
                else { writer.sealed = true; nodes[n].after.push_back(from_open->second); }
            }
        } else if (d.texture) {
            auto t = textures.find(d.texture);
            if (t != textures.end()) texture_of[i] = t->second;
        }
    }
    for (const Read& r : reads) {
        if (r.node >= 0) {
            // a surface that cannot be split (the 3-D surface) was read in the middle of its draws: the reader gets
            // last frame's picture and is rendered first; read after its last draw: rendered after it
            if (nodes[r.node].last_draw > r.at) { nodes[r.node].after.push_back(r.reader); stale_reads++; }
            else nodes[r.reader].after.push_back(r.node);
        } else {
            // read before anything was drawn into it in this list: every run that draws into the same viewport comes later
            Target& from = targets[r.target];
            for (size_t n = 0; n < nodes.size(); n++)
                if (nodes[n].target == &from && nodes[n].pass == from.latest && (int)n != r.reader) nodes[n].after.push_back(r.reader);
        }
    }
    std::vector<int> order;
    {
        std::vector<char> done(nodes.size(), 0);
        while (order.size() < nodes.size()) {
            int pick = -1;
            for (size_t n = 0; n < nodes.size() && pick < 0; n++) {
                if (done[n]) continue;
                bool ready = true;
                for (int before : nodes[n].after) if (!done[before]) { ready = false; break; }
                if (ready) pick = (int)n;
            }
            if (pick < 0) {                             // a circle: the first one left goes (it reads something a frame old)
                for (size_t n = 0; n < nodes.size(); n++) if (!done[n]) { pick = (int)n; break; }
                approximated++;
            }
            done[pick] = 1;
            order.push_back(pick);
        }
    }

    // ---- the draws ----
    for (Pass* pass : all_passes) pass->used = 0;
    Target* world = scene_mode ? world_target() : nullptr;
    if (scene_mode) scene_begin(f);
    for (uint32_t i = 0; i < f.draw_count; i++) {
        if (node_of[i] < 0) continue;
        const rtag_draw& d = f.draws[i];
        Node& node = nodes[node_of[i]];
        float order_in_pass = (float)(i - node.first_draw);
        if (d.kind == RTAG_COPY) {
            auto source = targets.find(d.texture);
            if (source != targets.end() && texture_of[i].is_valid()) add_copy(*node.pass, d, *node.target, source->second, texture_of[i], order_in_pass);
            continue;
        }
        if (scene_mode && node.target == world) {
            if (scene_take(*node.pass, f, d, *node.target, texture_of[i], order_in_pass)) continue;
            // the 2-D layer over (or behind) the world: in the list's order, without the GS's depth, which is not the world's
            rtag_draw flat = d;
            flat.ztst = 1; flat.depth_write = 0; flat.depth_test = 0;
            add_draw(*node.pass, f, flat, *node.target, texture_of[i], d.tex_is_target && flip_surfaces, order_in_pass);
            continue;
        }
        add_draw(*node.pass, f, d, *node.target, texture_of[i], d.tex_is_target && flip_surfaces, order_in_pass);
    }
    if (scene_mode) scene_end(f);

    // instances left over from a frame with more draws show nothing
    for (Pass* pass : all_passes)
        for (size_t k = pass->used; k < pass->instances.size(); k++) s->instance_set_base(pass->instances[k], RID());
    // the viewports in order: activated one after the other, each rendered once
    for (Pass* pass : all_passes) s->viewport_set_active(pass->viewport, false);
    for (int n : order) {
        Pass* pass = nodes[n].pass;
        s->viewport_set_active(pass->viewport, true);
        s->viewport_set_update_mode(pass->viewport, RenderingServer::VIEWPORT_UPDATE_ONCE);
        pass->drawn_once = true;
        nodes[n].target->latest = pass;
        passes_rendered++;
    }

    for (uint32_t k = 0; k < f.dead_texture_count; k++) {
        auto t = textures.find(f.dead_textures[k]);
        if (t == textures.end()) continue;
        s->free_rid(t->second);
        textures.erase(t);
    }
    for (uint32_t k = 0; k < f.dead_target_count; k++) {
        auto t = targets.find(f.dead_targets[k]);
        if (t == targets.end()) continue;
        if (shown == &t->second) shown = nullptr;
        for (Pass* pass : std::vector<Pass*>(t->second.passes)) free_pass(pass);
        targets.erase(t);
    }
    // materials nothing used for two seconds (their textures may be gone)
    if ((frames & 63) == 0)
        for (auto m = materials.begin(); m != materials.end();) {
            if (frames - m->second.last_used > 120) { s->free_rid(m->second.rid); m = materials.erase(m); }
            else ++m;
        }

    auto show = targets.find(f.show_target);
    shown = show == targets.end() ? nullptr : &show->second;
    memcpy(shown_rect, f.show_rect, sizeof shown_rect);
    submit_usec += (double)(Time::get_singleton()->get_ticks_usec() - t0);
}

RID RtaDrawer::get_shown_texture() const { return shown && shown->latest && shown->latest->drawn_once ? shown->latest->texture : RID(); }

Rect2 RtaDrawer::get_shown_region() const {
    if (!shown) return Rect2();
    float sx = (float)shown->pw / shown->lw, sy = (float)shown->ph / shown->lh;
    return Rect2(shown_rect[0] * sx, shown_rect[1] * sy, shown_rect[2] * sx, shown_rect[3] * sy);
}

Ref<Image> RtaDrawer::get_shown_image() const {
    RID texture = get_shown_texture();
    if (!texture.is_valid()) return Ref<Image>();
    Ref<Image> image = rs()->texture_2d_get(texture);
    if (image.is_valid() && image->get_format() != Image::FORMAT_RGB8) image->convert(Image::FORMAT_RGB8);
    return image;
}

void RtaDrawer::dump_surfaces(const String& prefix) const {
    for (auto& entry : targets) {
        const Target& t = entry.second;
        for (size_t k = 0; k < t.passes.size(); k++) {
            if (!t.passes[k]->drawn_once) continue;
            Ref<Image> image = rs()->texture_2d_get(t.passes[k]->texture);
            if (image.is_valid()) image->save_png(prefix + String("-s") + String::num_int64(t.id) + String("-p") + String::num_int64((int64_t)k) + (t.latest == t.passes[k] ? "-latest" : "") + ".png");
        }
    }
}

String RtaDrawer::figures() const {
    double n = frames ? (double)frames : 1;
    return vformat("drawer: %d lists; per list %.1f draws and %.0f vertices submitted, %.2f viewports rendered, %.3f ms in submit(); %d materials made (%d held), %d meshes held, "
                   "%d textures made; draws drawn twice for \"depth always, and write\": %d; reads of a surface in the middle of its own draws (given last frame's picture): %d; "
                   "approximated (a blend this route cannot do, a surface reading itself, a circle of surfaces): %d; draws skipped (depth test never): %d",
                   (int64_t)frames, draws_submitted / n, vertices_submitted / n, passes_rendered / n, submit_usec / 1000.0 / n, (int64_t)materials_made, (int64_t)materials.size(),
                   (int64_t)meshes_made, (int64_t)textures_made, (int64_t)depth_always_writes, (int64_t)stale_reads, (int64_t)approximated, (int64_t)skipped);
}

void RtaDrawer::release() {
    if (!RenderingServer::get_singleton()) return;
    RenderingServer* s = rs();
    scene_release();
    for (Pass* pass : std::vector<Pass*>(all_passes)) free_pass(pass);
    targets.clear();
    for (auto& m : materials) s->free_rid(m.second.rid);
    materials.clear();
    shaders.clear();
    for (auto& t : textures) s->free_rid(t.second);
    textures.clear();
    shown = nullptr;
}

void RtaDrawer::_bind_methods() {
    ClassDB::bind_method(D_METHOD("setup", "machine", "parent_viewport", "output_size", "samples"), &RtaDrawer::setup);
    ClassDB::bind_method(D_METHOD("set_shader_code", "code"), &RtaDrawer::set_shader_code);
    ClassDB::bind_method(D_METHOD("submit"), &RtaDrawer::submit);
    ClassDB::bind_method(D_METHOD("get_shown_texture"), &RtaDrawer::get_shown_texture);
    ClassDB::bind_method(D_METHOD("get_shown_region"), &RtaDrawer::get_shown_region);
    ClassDB::bind_method(D_METHOD("get_shown_image"), &RtaDrawer::get_shown_image);
    ClassDB::bind_method(D_METHOD("figures"), &RtaDrawer::figures);
    ClassDB::bind_method(D_METHOD("dump_surfaces", "prefix"), &RtaDrawer::dump_surfaces);
    ClassDB::bind_method(D_METHOD("release"), &RtaDrawer::release);
    ClassDB::bind_method(D_METHOD("set_scene_mode", "on"), &RtaDrawer::set_scene_mode);
    ClassDB::bind_method(D_METHOD("set_scene_option", "name", "value"), &RtaDrawer::set_scene_option);
    ClassDB::bind_method(D_METHOD("get_scene_info"), &RtaDrawer::get_scene_info);
    ClassDB::bind_method(D_METHOD("get_world_scenario"), &RtaDrawer::get_world_scenario);
    ClassDB::bind_method(D_METHOD("get_world_camera"), &RtaDrawer::get_world_camera);
}

}  // namespace godot
