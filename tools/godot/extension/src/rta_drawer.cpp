// rta_drawer.cpp - see rta_drawer.h.
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/classes/project_settings.hpp>
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
    // Forward+ / Mobile (Metal, Vulkan, Direct3D): the surfaces are stored the other way up than in the Compatibility
    // renderer's OpenGL; a surface read as a texture, the picture shown and the picture written are turned over
    rd = String(rs()->get_current_rendering_method()) != String("gl_compatibility");
    if (rd) flip_surfaces = true;
    // test aids: the two conventions the drawer depends on, to be turned over from outside
    if (getenv("RTA_GODOT_FLIP")) flip_y = (float)atof(getenv("RTA_GODOT_FLIP"));
    if (getenv("RTA_GODOT_TEXFLIP")) flip_surfaces = atoi(getenv("RTA_GODOT_TEXFLIP")) != 0;
    if (getenv("RTA_GODOT_NO_INVERTED")) inverted_depth_ok = false;
    if (getenv("RTA_GODOT_BIAS")) world_bias = (float)atof(getenv("RTA_GODOT_BIAS"));
    if (getenv("RTA_GODOT_STORED")) stored_colours = atoi(getenv("RTA_GODOT_STORED")) != 0;
}

void RtaDrawer::set_shader_code(const String& code) { shader_code = code.utf8().get_data(); }

// The size the picture is drawn at, changed while it runs (the portal's "sharpness"): every surface is sized again.
void RtaDrawer::set_output_size(const Vector2i& size) {
    if (size.x < 16 || size.y < 16 || size == output_size) return;
    output_size = size;
    for (auto& entry : targets) size_target(entry.second);     // (a material is made per scale: the old ones run out unused)
}

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
    last_order.erase(std::remove(last_order.begin(), last_order.end(), pass), last_order.end());
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
    if (variant & V_NOFOG) code += "#define GS_NOFOG\n";
    if (variant & V_NEARFADE) code += "#define GS_NEARFADE\n";
    if (variant & V_MODEL) code += "#define GS_MODEL\n";
    if (variant & V_CONTACT) code += "#define GS_CONTACT\n";
    if (variant & V_STORED) code += "#define GS_STORED_SPACE\n";
    if (variant & V_DECODE) code += "#define GS_DECODE\n";
    if (variant & V_FUSED) code += "#define GS_FUSED\n";
    if (variant & V_REPEAT2) code += "#define GS_REPEAT2\n";
    if (variant & V_SOLID) code += "#define GS_SOLID\n";
    if (variant & V_PREPASS) code += "#define GS_PREPASS\n";
    if (variant & V_ER) code += "#define GS_ER\n";
    if (stored_colours) code += "#define GS_STORED_COLOURS\n";
    code += shader_code;
    Ref<Shader> shader;
    shader.instantiate();
    shader->set_code(String::utf8(code.c_str()));
    shaders[variant] = shader;
    warm_note(variant);
    return shader->get_rid();
}

static std::string warm_path() {
    return ProjectSettings::get_singleton()->globalize_path("user://rta_variants.txt").utf8().get_data();
}

static void warm_load(std::unordered_set<uint32_t>& known) {
    FILE* file = fopen(warm_path().c_str(), "r");
    if (!file) return;
    char line[64];
    while (fgets(line, sizeof line, file)) {
        char* end = nullptr;
        unsigned long v = strtoul(line, &end, 16);
        if (end != line) known.insert((uint32_t)v);
    }
    fclose(file);
}

// a scene variant made for the first time on this machine goes into the list (one line, appended)
void RtaDrawer::warm_note(uint32_t variant) {
    if (!(variant & V_WORLD)) return;
    if (!warm_loaded) { warm_loaded = true; warm_load(warm_known); }
    if (!warm_known.insert(variant).second) return;
    FILE* file = fopen(warm_path().c_str(), "a");
    if (!file) return;
    fprintf(file, "%08x\n", variant);
    fclose(file);
}

// Each listed variant drawn once in the world's scenario, in each vertex layout the scene gives it (the game's normals,
// and with them the corners of the frame before), as one triangle of no area that is never culled
void RtaDrawer::warm_up(RID scenario) {
    if (scenario != warm_scenario) {
        warm_free();
        warm_scenario = scenario;
        if (!warm_loaded) { warm_loaded = true; warm_load(warm_known); }
        warm_todo.assign(warm_known.begin(), warm_known.end());
        std::sort(warm_todo.begin(), warm_todo.end());
        warm_next = 0;
    }
    if (getenv("RTA_WARM") && atoi(getenv("RTA_WARM")) == 0) return;     // test aid: off
    RenderingServer* s = rs();
    const uint64_t t0 = Time::get_singleton()->get_ticks_usec();
    int made = 0;
    // Shader::set_code and each mesh upload are indivisible. Do not compile the entire history in one turn.
    while (warm_next < warm_todo.size() && Time::get_singleton()->get_ticks_usec() - t0 < 1000) {
        const uint32_t variant = warm_todo[warm_next++];
        RID material = s->material_create();
        s->material_set_shader(material, shader_for(variant));
        warm_rids.push_back(material);
        const bool normals = variant & V_NORMALS;
        for (int carry = 0; carry < (normals ? 2 : 1); carry++) {
            const int stride = (normals ? 32 : 20) + (carry ? 16 : 0);
            PackedByteArray positions, attributes;
            positions.resize(3 * 12);
            attributes.resize(3 * stride);
            memset(positions.ptrw(), 0, positions.size());
            memset(attributes.ptrw(), 0, attributes.size());
            RID mesh = s->mesh_create();
            const AABB box(Vector3(-1, -1, -1), Vector3(2, 2, 2));
            add_surface_bytes(mesh, RenderingServer::PRIMITIVE_TRIANGLES, positions, attributes, 3, normals, &box, carry != 0);
            s->mesh_surface_set_material(mesh, 0, material);
            RID instance = s->instance_create();
            s->instance_set_scenario(instance, scenario);
            s->instance_set_base(instance, mesh);
            s->instance_set_ignore_culling(instance, true);
            s->instance_geometry_set_cast_shadows_setting(instance, (variant & V_CASTER) ? RenderingServer::SHADOW_CASTING_SETTING_SHADOWS_ONLY
                                                                                         : RenderingServer::SHADOW_CASTING_SETTING_OFF);
            warm_rids.push_back(instance);
            warm_rids.push_back(mesh);
            made++;
        }
    }
    if (made) warm_frame = frames;
    if (made && warm_next == warm_todo.size())
        UtilityFunctions::print(vformat("rta_godot: drawer: %d earlier scene variants warmed incrementally", (int64_t)warm_todo.size()));
}

void RtaDrawer::warm_free() {
    if (!RenderingServer::get_singleton()) return;
    for (auto it = warm_rids.rbegin(); it != warm_rids.rend(); ++it) rs()->free_rid(*it);
    warm_rids.clear();
}

void RtaDrawer::retire(RID rid) {
    if (rid.is_valid()) retired.push_back(rid);
}

void RtaDrawer::collect_retired() {
    const uint64_t start = Time::get_singleton()->get_ticks_usec();
    while (!retired.empty() && Time::get_singleton()->get_ticks_usec() - start < 1000) {
        rs()->free_rid(retired.front());
        retired.pop_front();
    }
}

// the blend: colour = (A - B) * C + D, as tools/recomp/render/backend_gl.cpp sets it up; returns false where it is drawn as
// an approximation (source x sf - destination x df: drawn as their sum)
bool RtaDrawer::blend_of(const rtag_draw& d, float& sc, float& sk, float& dc, float& dk, float& fix, int& blend_c, bool& subtract) {
    sc = 0; sk = 1; dc = 0; dk = 0; fix = 1.0f; blend_c = 2; subtract = false;
    if (!d.blend) return true;
    sc = (d.ba == 0 ? 1.0f : 0.0f) - (d.bb == 0 ? 1.0f : 0.0f); sk = d.bd == 0 ? 1.0f : 0.0f;
    dc = (d.ba == 1 ? 1.0f : 0.0f) - (d.bb == 1 ? 1.0f : 0.0f); dk = d.bd == 1 ? 1.0f : 0.0f;
    bool src_negative = sc < 0 && sk == 0, dst_negative = dc < 0 && dk == 0, exact = true;
    if (src_negative && dst_negative) { sc = 0; dc = 0; }
    else if (src_negative) subtract = true;         // destination x df - source x sf: exact where df is 1
    else if (dst_negative) exact = false;
    blend_c = d.bc;
    fix = (float)d.fix / 128.0f;
    return exact;
}

RID RtaDrawer::material_for(const rtag_draw& d, const Target& target, bool inverted, RID texture, bool texture_flipped, uint32_t extra,
                            const rtag_draw* second, RID second_texture, uint32_t er) {
    float sc, sk, dc, dk, fix;
    int blend_c;
    bool subtract;
    if (!blend_of(d, sc, sk, dc, dk, fix, blend_c, subtract)) approximated++;
    uint32_t variant = extra;
    // stored-space blending (submit): a draw of the 3-D world reads such a surface too (V_DECODE); it is drawn so (V_STORED) only
    // in a Classic world (stored_world: no light of Godot's in it), never a shadow caster's twin
    variant |= (extra & V_WORLD) ? (draw_space & ((extra & V_CASTER) ? V_DECODE : (V_DECODE | V_STORED))) : draw_space;
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

    // the Elden Ring world layer's classes (rta_world.cpp): a byte each, er_class | er_class_b | er_class2 | er_class2_b
    if (!(extra & V_WORLD) || (extra & V_CASTER)) er = 0;
    if (er) variant |= V_ER;
    struct Key {
        uint32_t variant; uint32_t er; int64_t texture; uint32_t target; float scissor[4];
        uint8_t textured, tfx, tcc, wrap_s, wrap_t, texa_mode, ta0, ta1, aem, atst, aref, fog, fog_colour[3], blend_c, mask_rgb, flipped;
        float st_scale[2], tex_size[2], tex_offset[2], region[4], weave_half, blend[4], fix, scale[2];
    } key;
    memset(&key, 0, sizeof key);
    key.variant = variant; key.er = er; key.texture = textured ? texture.get_id() : 0; key.target = target.id;
    key.scissor[0] = x0; key.scissor[1] = y0; key.scissor[2] = x1; key.scissor[3] = y1;
    key.textured = textured; key.atst = d.alpha_test ? d.atst : 1; key.aref = d.aref; key.fog = d.fog; memcpy(key.fog_colour, d.fog_colour, 3);
    key.blend_c = (uint8_t)blend_c; key.mask_rgb = d.mask_rgb; key.flipped = texture_flipped;
    key.blend[0] = sc; key.blend[1] = sk; key.blend[2] = dc; key.blend[3] = dk; key.fix = fix;
    key.scale[0] = sx; key.scale[1] = sy;
    if (textured) {
        key.tfx = d.tfx; key.tcc = d.tcc; key.wrap_s = d.wrap_s; key.wrap_t = d.wrap_t;
        key.texa_mode = d.tex_is_target ? d.texa_mode : 0; key.ta0 = d.ta0; key.ta1 = d.ta1; key.aem = d.aem;
        memcpy(key.st_scale, d.st_scale, sizeof key.st_scale); memcpy(key.tex_size, d.tex_size, sizeof key.tex_size);
        memcpy(key.tex_offset, d.tex_offset, sizeof key.tex_offset); memcpy(key.region, d.region, sizeof key.region);
        // an art pack's two-field picture holds the woven picture itself: the woven line is the coordinate (-1), over the
        // texels the picture covers (the native program's part: render/backend_gl.cpp), from its corner
        key.weave_half = d.weave_half > 0 && woven_textures.count(texture.get_id()) ? -1.0f : d.weave_half;
        // ... and every draw of such a picture samples it over those texels, woven or not, as the native program's does (the
        // game draws a field's sprite now as a field, now not: its second-field frames then fall in the file's second copy)
        if (woven_textures.count(texture.get_id())) {
            auto size = woven_sizes.find(texture.get_id());
            if (size != woven_sizes.end() && size->second.x > 0 && size->second.y > 0) {
                key.tex_size[0] = size->second.x; key.tex_size[1] = size->second.y;
                key.tex_offset[0] = key.tex_offset[1] = 0.0f;
            }
        }
    }
    std::string bytes((const char*)&key, sizeof key);
    // a fused pair (rta_scene.cpp, the level's batches): the first pass's state too, as the "2" parameters
    struct Key2 {
        int64_t texture; uint8_t textured, tfx, tcc, wrap_s, wrap_t, texa_mode, ta0, ta1, aem, blend_c;
        float st_scale[2], tex_size[2], tex_offset[2], region[4], weave_half, blend[4], fix;
    } key2;
    float sc2 = 0, sk2 = 1, dc2 = 0, dk2 = 0, fix2 = 1;
    int blend_c2 = 2;
    if (second) {
        bool subtract2;
        blend_of(*second, sc2, sk2, dc2, dk2, fix2, blend_c2, subtract2);
        memset(&key2, 0, sizeof key2);
        const rtag_draw& e = *second;
        key2.textured = second_texture.is_valid(); key2.texture = key2.textured ? second_texture.get_id() : 0;
        key2.blend_c = (uint8_t)blend_c2; key2.blend[0] = sc2; key2.blend[1] = sk2; key2.blend[2] = dc2; key2.blend[3] = dk2; key2.fix = fix2;
        if (key2.textured) {
            key2.tfx = e.tfx; key2.tcc = e.tcc; key2.wrap_s = e.wrap_s; key2.wrap_t = e.wrap_t;
            key2.texa_mode = e.tex_is_target ? e.texa_mode : 0; key2.ta0 = e.ta0; key2.ta1 = e.ta1; key2.aem = e.aem;
            memcpy(key2.st_scale, e.st_scale, sizeof key2.st_scale); memcpy(key2.tex_size, e.tex_size, sizeof key2.tex_size);
            memcpy(key2.tex_offset, e.tex_offset, sizeof key2.tex_offset); memcpy(key2.region, e.region, sizeof key2.region);
            key2.weave_half = e.weave_half > 0 && woven_textures.count(second_texture.get_id()) ? -1.0f : e.weave_half;
            if (e.wrap_s == RTAG_WRAP_REPEAT && e.wrap_t == RTAG_WRAP_REPEAT) variant |= V_REPEAT2;
        }
        variant |= V_FUSED;
        key.variant = variant;
        bytes.assign((const char*)&key, sizeof key);
        bytes.append((const char*)&key2, sizeof key2);
    }
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
    if (er) {
        s->material_set_param(material, "er_class", (int)(er & 255));
        s->material_set_param(material, "er_class_b", (int)((er >> 8) & 255));
        s->material_set_param(material, "er_class2", (int)((er >> 16) & 255));
        s->material_set_param(material, "er_class2_b", (int)((er >> 24) & 255));
    }
    if (textured) {
        s->material_set_param(material, "tex", texture);
        s->material_set_param(material, "tfx", (int)d.tfx);
        s->material_set_param(material, "tcc", d.tcc ? 1 : 0);
        s->material_set_param(material, "st_scale", Vector2(d.st_scale[0], d.st_scale[1]));
        s->material_set_param(material, "tex_size", Vector2(key.tex_size[0], key.tex_size[1]));
        s->material_set_param(material, "tex_offset", Vector2(key.tex_offset[0], key.tex_offset[1]));
        s->material_set_param(material, "tex_flip", texture_flipped ? 1.0f : 0.0f);
        s->material_set_param(material, "wrap_mode", Vector2i(d.wrap_s, d.wrap_t));
        s->material_set_param(material, "region", Quaternion(d.region[0], d.region[1], d.region[2], d.region[3]));
        s->material_set_param(material, "weave_half", key.weave_half);
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
    if (second) {
        const rtag_draw& e = *second;
        s->material_set_param(material, "textured2", key2.textured ? 1 : 0);
        if (key2.textured) {
            s->material_set_param(material, "tex2", second_texture);
            s->material_set_param(material, "tfx2", (int)e.tfx);
            s->material_set_param(material, "tcc2", e.tcc ? 1 : 0);
            s->material_set_param(material, "st_scale2", Vector2(e.st_scale[0], e.st_scale[1]));
            s->material_set_param(material, "tex_size2", Vector2(e.tex_size[0], e.tex_size[1]));
            s->material_set_param(material, "tex_offset2", Vector2(e.tex_offset[0], e.tex_offset[1]));
            s->material_set_param(material, "wrap_mode2", Vector2i(e.wrap_s, e.wrap_t));
            s->material_set_param(material, "region2", Quaternion(e.region[0], e.region[1], e.region[2], e.region[3]));
            s->material_set_param(material, "weave_half2", key2.weave_half);
            s->material_set_param(material, "texa2", Quaternion(e.tex_is_target ? (float)e.texa_mode : 0.0f, (float)e.ta0, (float)e.ta1, e.aem ? 1.0f : 0.0f));
        }
        s->material_set_param(material, "blend2", Quaternion(sc2, sk2, dc2, dk2));
        s->material_set_param(material, "blend_c2", blend_c2);
        s->material_set_param(material, "fix2", fix2);
    }
    materials[bytes] = {material, frames};
    materials_made++;
    return material;
}

// ---- meshes and instances -------------------------------------------------------------------

RID RtaDrawer::mesh_for(Pass& pass) {
    if (pass.shapes.size() < pass.meshes.size()) pass.shapes.resize(pass.meshes.size(), 0);
    if (pass.used < pass.meshes.size()) {
        rs()->mesh_clear(pass.meshes[pass.used]);
        pass.shapes[pass.used] = 0;
        return pass.meshes[pass.used];
    }
    RID mesh = rs()->mesh_create();
    pass.meshes.push_back(mesh);
    pass.shapes.push_back(0);
    meshes_made++;
    return mesh;
}

// The pool's mesh at pass.used holding this draw's vertices: written again in place when it has the same number of them
// and the same kind of primitive as the draw it held last (a surface made anew makes Godot's buffers and pipelines anew)
RID RtaDrawer::mesh_for_flat(Pass& pass, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count) {
    const uint64_t shape = ((uint64_t)count << 8) | (uint64_t)primitive | 0x80;
    if (pass.shapes.size() < pass.meshes.size()) pass.shapes.resize(pass.meshes.size(), 0);
    if (pass.used < pass.meshes.size() && pass.shapes[pass.used] == shape) {
        RID mesh = pass.meshes[pass.used];
        rs()->mesh_surface_update_vertex_region(mesh, 0, 0, positions);
        rs()->mesh_surface_update_attribute_region(mesh, 0, 0, attributes);
        flat_reused++;
        return mesh;
    }
    RID mesh = mesh_for(pass);
    add_surface_bytes(mesh, primitive, positions, attributes, count);
    pass.shapes[pass.used] = shape;
    return mesh;
}

// A big draw (see rta_drawer.h): the room the pool's mesh at pass.used has, when it fits `count` without more than twice
// as much; else room for 15 % more, in steps of 12,288 corners.  A surface made anew each frame cost Godot a buffer of
// tens of megabytes made and freed a frame.
static const uint64_t BIG_TAG = 0x40 | RenderingServer::PRIMITIVE_TRIANGLES;
int RtaDrawer::big_capacity(Pass& pass, int count) const {
    if (pass.used < pass.shapes.size() && pass.used < pass.meshes.size() && (pass.shapes[pass.used] & 0xff) == BIG_TAG) {
        const int have = (int)(pass.shapes[pass.used] >> 8);
        if (have >= count && have <= count * 2) return have;
    }
    return ((int)((int64_t)count * 115 / 100) / 12288 + 1) * 12288;
}

RID RtaDrawer::mesh_for_big(Pass& pass, const PackedByteArray& positions, const PackedByteArray& attributes, int capacity, const AABB& box) {
    const uint64_t shape = ((uint64_t)capacity << 8) | BIG_TAG;
    if (pass.shapes.size() < pass.meshes.size()) pass.shapes.resize(pass.meshes.size(), 0);
    if (pass.used < pass.meshes.size() && pass.shapes[pass.used] == shape) {
        RID mesh = pass.meshes[pass.used];
        rs()->mesh_surface_update_vertex_region(mesh, 0, 0, positions);
        rs()->mesh_surface_update_attribute_region(mesh, 0, 0, attributes);
        rs()->mesh_set_custom_aabb(mesh, box);
        big_reused++;
        return mesh;
    }
    RID mesh = mesh_for(pass);
    add_surface_bytes(mesh, RenderingServer::PRIMITIVE_TRIANGLES, positions, attributes, capacity, false, &box);
    pass.shapes[pass.used] = shape;
    big_made++;
    return mesh;
}

// The instance for the mesh at pass.used (made by mesh_for), drawn `order`-th in its viewport.
RID RtaDrawer::place(Pass& pass, RID material, float order) {
    RenderingServer* s = rs();
    RID mesh = pass.meshes[pass.used];
    s->mesh_surface_set_material(mesh, 0, material);
    RID instance = instance_for(pass);
    if (pass.overridden[pass.used]) { s->instance_geometry_set_material_override(instance, RID()); pass.overridden[pass.used] = 0; }
    s->instance_set_base(instance, mesh);
    // the transparent pass draws far to near; a larger offset is "nearer": the list's order
    s->instance_set_pivot_data(instance, order, false);
    pass.used++;
    return instance;
}

// The same for a mesh the scene keeps between frames (rta_scene.cpp): its material goes on the instance, the mesh may be
// drawn with another state elsewhere.  The pool's mesh at this place is left as it is.
RID RtaDrawer::place_mesh(Pass& pass, RID mesh, RID material, float order) {
    RenderingServer* s = rs();
    if (pass.used >= pass.meshes.size()) { pass.meshes.push_back(s->mesh_create()); meshes_made++; }
    RID instance = instance_for(pass);
    s->instance_geometry_set_material_override(instance, material);
    pass.overridden[pass.used] = 1;
    s->instance_set_base(instance, mesh);
    s->instance_set_pivot_data(instance, order, false);
    pass.used++;
    return instance;
}

RID RtaDrawer::instance_for(Pass& pass) {
    RenderingServer* s = rs();
    RID instance;
    if (pass.used < pass.instances.size()) instance = pass.instances[pass.used];
    else {
        instance = s->instance_create();
        s->instance_set_scenario(instance, pass.scenario);
        s->instance_set_ignore_culling(instance, true);
        s->instance_geometry_set_cast_shadows_setting(instance, RenderingServer::SHADOW_CASTING_SETTING_OFF);
        pass.instances.push_back(instance);
        pass.overridden.push_back(0);
    }
    return instance;
}

void RtaDrawer::add_surface_bytes(RID mesh, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count, bool normals, const AABB* box, bool carry) {
    Dictionary surface;
    surface["primitive"] = primitive;
    surface["format"] = (int64_t)(RenderingServer::ARRAY_FORMAT_VERTEX | RenderingServer::ARRAY_FORMAT_COLOR | RenderingServer::ARRAY_FORMAT_CUSTOM0 |
                                  ((int64_t)RenderingServer::ARRAY_CUSTOM_RGBA_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM0_SHIFT) |
                                  RenderingServer::ARRAY_FLAG_FORMAT_CURRENT_VERSION);
    // scene mode: the game's normal, world space, as three more floats per vertex (after the colour and the texture coordinates)
    if (normals) surface["format"] = (int64_t)surface["format"] | RenderingServer::ARRAY_FORMAT_CUSTOM1 |
                                     ((int64_t)RenderingServer::ARRAY_CUSTOM_RGB_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM1_SHIFT);
    // a kept model's corners as they were in the game frame before (x, y, z; w 2 when they are, 0 when not): for the
    // pictures between game frames (redraw, gs_draw.gdshaderinc GS_WORLD)
    if (carry) surface["format"] = (int64_t)surface["format"] | RenderingServer::ARRAY_FORMAT_CUSTOM2 |
                                   ((int64_t)RenderingServer::ARRAY_CUSTOM_RGBA_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM2_SHIFT);
    surface["vertex_data"] = positions;
    surface["attribute_data"] = attributes;
    surface["vertex_count"] = count;
    surface["aabb"] = box ? *box : EVERYWHERE;
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
        mesh_for_flat(pass, primitive, positions, attributes, (int)d.count);
        place(pass, material_for(d, target, n == 1, texture, texture_flipped), order + 0.25f * n);
    }
    draws_submitted++;
    vertices_submitted += d.count;
}

bool RtaDrawer::is_letterbox(const rtag_frame& f, const rtag_draw& d, const Target& target) const {
    // the game's cut-scene letterbox: one draw of sprites (two rectangles, 6 corners each as triangles), every one of
    // them opaque black, across the whole width, a band at the top or the bottom edge
    if (d.kind != RTAG_DRAW || d.texture != 0 || d.made_by == 0 || d.prim != RTAG_TRIANGLES || d.count < 6 || d.count % 6 ||
        d.count > 24 || d.first + d.count > f.vertex_count || target.lw <= 0) return false;
    const float w = (float)target.lw, h = (float)target.lh;
    for (uint32_t q = 0; q < d.count; q += 6) {
        float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
        for (uint32_t k = q; k < q + 6; k++) {
            const rtag_vertex& v = f.vertices[d.first + k];
            if (v.r > 6 || v.g > 6 || v.b > 6) return false;            // black
            if (d.blend && v.a < 0x78) return false;                     // opaque
            x0 = std::min(x0, v.x); x1 = std::max(x1, v.x); y0 = std::min(y0, v.y); y1 = std::max(y1, v.y);
        }
        if (x1 - x0 < w * 0.95f || y1 - y0 > h * 0.3f || y1 - y0 < 2.0f) return false;     // across the whole width, a band
        if (!(y0 <= h * 0.02f || y1 >= h * 0.98f)) return false;                              // at the top or the bottom edge
    }
    return true;
}

void RtaDrawer::redraw(double t) {
    if (last_order.empty()) return;
    RenderingServer* s = rs();
    if (scene_mode) {
        scene_tween(t);
        tween_global = true;            // (scene_view.gd adds the global: only a host that asks for pictures between sets it)
        s->global_shader_parameter_set("rta_tween", Vector4((real_t)t, 0, 0, 0));
    }
    for (Pass* pass : all_passes) s->viewport_set_active(pass->viewport, false);
    for (Pass* pass : last_order) {
        s->viewport_set_active(pass->viewport, true);
        s->viewport_set_update_mode(pass->viewport, RenderingServer::VIEWPORT_UPDATE_ONCE);
    }
    redraws++;
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
    // (a list that takes long, logged with its parts: RTA_SUBMIT_LOG=MS)
    static const int slow_log = getenv("RTA_SUBMIT_LOG") ? atoi(getenv("RTA_SUBMIT_LOG")) : 0;
    const size_t materials_before = materials.size(), shaders_before = shaders.size();
    const uint64_t meshes_before = meshes_made;
    uint64_t t_textures = 0, t_draws = 0, t_end = 0;

    // the Elden Ring world layer reads every texture of the scene as it arrives (rta_world.cpp): by its name, and its texels
    uint32_t world_named = 0;
    if (scene_mode && f.texture_count && rta_library().rtag_texture_names) {
        world_names.resize(f.texture_count);
        world_named = rta_library().rtag_texture_names(world_names.data(), f.texture_count);
    }
    for (uint32_t k = 0; k < f.texture_count; k++) {
        const rtag_texture& t = f.textures[k];
        if (scene_mode) world_classify(t, k < world_named && world_names[k].id == t.id ? &world_names[k] : nullptr);
        PackedByteArray bytes;
        bytes.resize((int64_t)t.width * t.height * 4);
        memcpy(bytes.ptrw(), t.rgba, (size_t)t.width * t.height * 4);
        Ref<Image> image = Image::create_from_data(t.width, t.height, false, Image::FORMAT_RGBA8, bytes);
        auto old = textures.find(t.id);
        if (old != textures.end()) { woven_textures.erase(old->second.get_id()); woven_sizes.erase(old->second.get_id()); s->free_rid(old->second); }
        textures[t.id] = s->texture_2d_create(image);
        textures_made++;
        texture_serial.erase(t.id);
        if (scene_mode) {                               // its pixels, for what the fill cuts out of the level's textures
            CpuTexture& copy = cpu_textures[t.id];
            copy.w = t.width; copy.h = t.height;
            copy.rgba.assign(t.rgba, t.rgba + (size_t)t.width * t.height * 4);
        }
        if (scene_mode && t.width >= THUMB && t.height >= THUMB) {
            Thumb& thumb = thumbs[t.id];
            const int cw = t.width / THUMB, ch = t.height / THUMB;
            for (int ty = 0; ty < THUMB; ty++)
                for (int tx = 0; tx < THUMB; tx++) {
                    uint32_t sum = 0;
                    for (int y = 0; y < ch; y += 2)
                        for (int x = 0; x < cw; x += 2) {
                            const uint8_t* px = t.rgba + ((size_t)(ty * ch + y) * t.width + tx * cw + x) * 4;
                            sum += px[0] * 2 + px[1] * 5 + px[2];
                        }
                    const int n = ((ch + 1) / 2) * ((cw + 1) / 2);
                    thumb.lum[ty * THUMB + tx] = (uint8_t)std::min<uint32_t>(sum / (uint32_t)(n * 8), 255);
                }
        }
    }
    pack_frame(f);                                      // the art pack's pictures and mip maps (rta_pack.h)
    if (slow_log) t_textures = Time::get_singleton()->get_ticks_usec();
    if (scene_mode && std::fabs(f.aspect - last_aspect) > 0.001f) {     // the view's shape changed: the 3-D surface's viewport follows
        last_aspect = f.aspect;
        for (auto& entry : targets) if (entry.second.screen) size_target(entry.second);
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
    std::vector<uint8_t> decode_of(f.draw_count, 0);   // the texture is a surface that holds stored values (V_DECODE)
    // Forward+ / Mobile: which surfaces are drawn in stored values (V_STORED) - every one but the 3-D world's while it has
    // the scene in it; the Compatibility renderer blends stored values anyway
    Target* world_now = scene_mode ? world_target() : nullptr;
    bool world_has_scene = false;
    if (world_now)
        for (uint32_t i = 0; i < f.draw_count && !world_has_scene; i++) if (f.draws[i].target == world_now->id && f.draws[i].scene_first >= 0) world_has_scene = true;
    static const bool stored_on = !getenv("RTA_GODOT_LINEAR_BLEND");     // (a test aid: blending in linear light, as before)
    // ... and the world's too in Classic (stored_world), where nothing of Godot's own light is in it: the GS's blending exactly
    const bool world_stored = stored_world && !scene_lit();
    auto stored_for = [&](const Target* t) { return stored_on && rd && (!(t == world_now && world_has_scene) || world_stored); };
    std::vector<Pass*> used_this_frame;
    std::unordered_set<uint32_t> blob_read, other_read;     // surfaces read this frame by left-out ground shadows / by anything else
    std::unordered_set<int> read_in_frame;                  // runs read by a draw of this frame that is drawn
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
            node.pass->stored_next = stored_for(&target);
            nodes.push_back(node);
            n = (int)nodes.size() - 1;
            current[d.target] = n;
        }
        nodes[n].last_draw = i;
        nodes[n].count++;
        node_of[i] = n;
        // what the draw reads
        bool reads_surface = d.kind == RTAG_COPY || (d.texture && d.tex_is_target);
        if (reads_surface && world_now && &target == world_now && scene_drops_blob(f, d)) {
            // the game's own ground shadow, left out in the scene where Godot throws real ones (rta_scene.cpp): its
            // surface need not be drawn for it
            blob_read.insert(d.texture);
            continue;
        }
        if (reads_surface) {
            other_read.insert(d.texture);
            auto source = targets.find(d.texture);
            if (source == targets.end() || source->second.id == target.id) { if (source != targets.end()) approximated++; continue; }
            Target& from = source->second;
            auto from_open = current.find(from.id);
            if (from_open == current.end()) {
                texture_of[i] = from.latest ? from.latest->texture : RID();        // what the last list left there
                decode_of[i] = from.latest && from.latest->stored;
                reads.push_back({n, from.id, -1, i});
            } else {
                Node& writer = nodes[from_open->second];
                read_in_frame.insert(from_open->second);
                texture_of[i] = writer.pass->texture;
                decode_of[i] = writer.pass->stored_next;
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

    if (draw_log > 0) {                                 // debugging (log_draws): each draw's state, its first vertex
        draw_log--;
        String t = vformat("frame %d: shows target %d (%d %d %d %d); targets", (int64_t)f.number, (int64_t)f.show_target, f.show_rect[0], f.show_rect[1], f.show_rect[2], f.show_rect[3]);
        for (const auto& entry : targets) t += vformat(" %d:%dx%d%s", (int64_t)entry.first, entry.second.lw, entry.second.lh, String(entry.second.screen ? "(screen)" : ""));
        UtilityFunctions::print(t);
        for (uint32_t i = 0; i < f.draw_count; i++) {
            const rtag_draw& d = f.draws[i];
            const rtag_vertex* v = d.count ? &f.vertices[d.first] : nullptr;
            UtilityFunctions::print(vformat("draw %d: kind %d prim %d by %d target %d tex %d%s tfx %d tcc %d | test %d atst %d aref %d afail %d | z %d/%d/%d | blend %d %d%d%d%d fix %d | mask %d%d | fog %d | scissor %d %d %d %d | %d vertices",
                (int64_t)i, d.kind, d.prim, d.made_by, (int64_t)d.target, (int64_t)d.texture, String(d.tex_is_target ? " (surface)" : ""), d.tfx, d.tcc, d.alpha_test, d.atst, d.aref, d.afail,
                d.depth_test, d.ztst, d.depth_write, d.blend, d.ba, d.bb, d.bc, d.bd, d.fix, d.mask_rgb, d.mask_a, d.fog, d.scissor[0], d.scissor[1], d.scissor[2], d.scissor[3], (int64_t)d.count) +
                (v ? vformat(" | first %.0f %.0f rgba %d %d %d %d", v->x, v->y, v->r, v->g, v->b, v->a) : String()) +
                (d.texture ? vformat(" | size %.0fx%.0f off %.1f %.1f st %.3f %.3f weave %.1f base %.1f linear %d wrap %d %d", d.tex_size[0], d.tex_size[1],
                    d.tex_offset[0], d.tex_offset[1], d.st_scale[0], d.st_scale[1], d.weave_half, d.weave_base, d.linear, d.wrap_s, d.wrap_t) +
                    (v ? vformat(" st0 %.2f %.2f q %.2f", v->s, v->t, v->q) : String()) +
                    [&]() -> String {
                        auto t = textures.find(d.texture);
                        if (d.tex_is_target || t == textures.end() || !woven_textures.count(t->second.get_id())) return String();
                        auto w = woven_sizes.find(t->second.get_id());
                        return vformat(" woven %s", w != woven_sizes.end() ? String(w->second) : String("?"));
                    }() : String()));
        }
    }
    // runs into a small surface that no drawn draw reads: its readers this frame are only the game's ground shadows the
    // scene leaves out (Godot throws real shadows), and the last run of a surface is kept when a later list may read it
    std::vector<char> skip(nodes.size(), 0);
    for (size_t n = 0; n < nodes.size(); n++) {
        const Target* t = nodes[n].target;
        if (t->screen || t->id == f.show_target || !blob_read.count(t->id) || read_in_frame.count((int)n)) continue;
        auto last = current.find(t->id);
        if (last != current.end() && last->second == (int)n && other_read.count(t->id)) continue;
        skip[n] = 1;
        passes_skipped++;
    }
    // ---- the draws ----
    for (Pass* pass : all_passes) pass->used = 0;
    Target* world = scene_mode ? world_target() : nullptr;
    frame_texture_of = &texture_of;
    if (scene_mode) scene_begin(f);
    world_finish();
    for (uint32_t i = 0; i < f.draw_count; i++) {
        if (node_of[i] < 0 || skip[node_of[i]]) continue;
        const rtag_draw& d = f.draws[i];
        Node& node = nodes[node_of[i]];
        float order_in_pass = (float)(i - node.first_draw);
        draw_space = (node.pass->stored_next ? V_STORED : 0) | (decode_of[i] ? V_DECODE : 0);
        if (d.kind == RTAG_COPY) {
            auto source = targets.find(d.texture);
            if (source != targets.end() && texture_of[i].is_valid()) add_copy(*node.pass, d, *node.target, source->second, texture_of[i], order_in_pass);
            continue;
        }
        if (scene_mode && node.target == world) {
            if (scene_take(*node.pass, f, d, *node.target, texture_of[i], order_in_pass)) continue;
            if (letterbox_off && is_letterbox(f, d, *node.target)) { letterbox_left_out++; continue; }
            // the 2-D layer over (or behind) the world: in the list's order, without the GS's depth, which is not the world's
            rtag_draw flat = d;
            flat.ztst = 1; flat.depth_write = 0; flat.depth_test = 0;
            add_draw(*node.pass, f, flat, *node.target, texture_of[i], d.tex_is_target && flip_surfaces, order_in_pass);
            continue;
        }
        add_draw(*node.pass, f, d, *node.target, texture_of[i], d.tex_is_target && flip_surfaces, order_in_pass);
    }
    draw_space = 0;
    if (slow_log) t_draws = Time::get_singleton()->get_ticks_usec();
    if (scene_mode) scene_end(f);
    if (slow_log) t_end = Time::get_singleton()->get_ticks_usec();
    frame_texture_of = nullptr;

    // instances left over from a frame with more draws show nothing
    for (Pass* pass : all_passes)
        for (size_t k = pass->used; k < pass->instances.size(); k++) s->instance_set_base(pass->instances[k], RID());
    // the viewports in order: activated one after the other, each rendered once
    for (Pass* pass : all_passes) s->viewport_set_active(pass->viewport, false);
    last_order.clear();
    if (scene_mode && tween_global) s->global_shader_parameter_set("rta_tween", Vector4(0, 0, 0, 0));
    static int pass_log = getenv("RTA_PASS_LOG") ? atoi(getenv("RTA_PASS_LOG")) : 0;    // test aid: the passes of every 600th list
    if (pass_log > 0 && frames % 600 == 0) {
        pass_log--;
        String line = vformat("rta_drawer: list %d renders %d passes:", (int64_t)frames, (int64_t)order.size());
        for (int n : order) line += vformat(" [target %d %dx%d (logical %dx%d)%s draws %d]", (int64_t)nodes[n].target->id, (int64_t)nodes[n].target->pw, (int64_t)nodes[n].target->ph,
                                            (int64_t)nodes[n].target->lw, (int64_t)nodes[n].target->lh, nodes[n].target == world ? " WORLD" : (nodes[n].target == shown ? " SHOWN" : ""), (int64_t)nodes[n].count);
        UtilityFunctions::print(line);
    }
    for (int n : order) {
        if (skip[n]) continue;
        Pass* pass = nodes[n].pass;
        // what a picture between game frames renders again: the world and the surface shown (which copies it)
        if (nodes[n].target == world || nodes[n].target->id == f.show_target) last_order.push_back(pass);
        s->viewport_set_active(pass->viewport, true);
        s->viewport_set_update_mode(pass->viewport, RenderingServer::VIEWPORT_UPDATE_ONCE);
        pass->drawn_once = true;
        pass->stored = pass->stored_next;
        nodes[n].target->latest = pass;
        passes_rendered++;
    }

    for (uint32_t k = 0; k < f.dead_texture_count; k++) {
        if (pack) pack->forget(f.dead_textures[k]);
        texture_serial.erase(f.dead_textures[k]);
        auto t = textures.find(f.dead_textures[k]);
        if (t == textures.end()) continue;
        s->free_rid(t->second);
        textures.erase(t);
        thumbs.erase(f.dead_textures[k]);
        cpu_textures.erase(f.dead_textures[k]);
        world_tex.erase(f.dead_textures[k]);
        world_prepared.erase(f.dead_textures[k]);
        world_seen_frame.erase(f.dead_textures[k]);
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
            if (frames - m->second.last_used > 120) { retire(m->second.rid); m = materials.erase(m); }
            else ++m;
        }

    auto show = targets.find(f.show_target);
    shown = show == targets.end() ? nullptr : &show->second;
    memcpy(shown_rect, f.show_rect, sizeof shown_rect);
    collect_retired();
    const uint64_t t1 = Time::get_singleton()->get_ticks_usec();
    submit_usec += (double)(t1 - t0);
    if (slow_log && t1 - t0 > (uint64_t)slow_log * 1000)
        UtilityFunctions::print(vformat("rta_drawer: list %d took %.1f ms: textures %.1f (%d new), runs and draws %.1f, scene end %.1f, rest %.1f; %d materials, %d shaders, %d meshes made",
                                        (int64_t)frames, (t1 - t0) / 1000.0, (t_textures - t0) / 1000.0, (int64_t)f.texture_count, (t_draws - t_textures) / 1000.0,
                                        (t_end - t_draws) / 1000.0, (t1 - t_end) / 1000.0, (int64_t)(materials.size() - materials_before),
                                        (int64_t)(shaders.size() - shaders_before), (int64_t)(meshes_made - meshes_before)));
}

RID RtaDrawer::get_shown_texture() const { return shown && shown->latest && shown->latest->drawn_once ? shown->latest->texture : RID(); }

Rect2 RtaDrawer::get_shown_region() const {
    if (!shown) return Rect2();
    float sx = (float)shown->pw / shown->lw, sy = (float)shown->ph / shown->lh;
    // Forward+: the texture holds the picture bottom up - these are its rows; get_shown_flipped() says to turn it over
    if (rd) return Rect2(shown_rect[0] * sx, (float)shown->ph - (shown_rect[1] + shown_rect[3]) * sy, shown_rect[2] * sx, shown_rect[3] * sy);
    return Rect2(shown_rect[0] * sx, shown_rect[1] * sy, shown_rect[2] * sx, shown_rect[3] * sy);
}

bool RtaDrawer::get_shown_stored() const { return shown && shown->latest && shown->latest->drawn_once && shown->latest->stored; }

Ref<Image> RtaDrawer::get_shown_image() const {
    RID texture = get_shown_texture();
    if (!texture.is_valid()) return Ref<Image>();
    Ref<Image> image = rs()->texture_2d_get(texture);
    if (image.is_valid() && image->get_format() != Image::FORMAT_RGB8) image->convert(Image::FORMAT_RGB8);
    if (image.is_valid() && get_shown_stored()) {
        // stored values under Godot's sRGB curve (V_STORED): the curve taken off, as view.gd does on the screen
        static uint8_t table[256];
        static bool made = false;
        if (!made) {
            for (int k = 0; k < 256; k++) {
                double c = k / 255.0, l = c <= 0.04045 ? c / 12.92 : std::pow((c + 0.055) / 1.055, 2.4);
                table[k] = (uint8_t)std::lround(std::min(1.0, l) * 255.0);
            }
            made = true;
        }
        PackedByteArray bytes = image->get_data();
        uint8_t* p = bytes.ptrw();
        for (int64_t k = 0; k < bytes.size(); k++) p[k] = table[p[k]];
        image = Image::create_from_data(image->get_width(), image->get_height(), false, Image::FORMAT_RGB8, bytes);
    }
    if (image.is_valid() && rd) image->flip_y();
    return image;
}

void RtaDrawer::log_draws(int frames) { draw_log = frames; }

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
                   "approximated (a blend this route cannot do, a surface reading itself, a circle of surfaces): %d; draws skipped (depth test never): %d; pictures drawn again between game frames: %d; runs not rendered (surfaces only the left-out ground shadows read): %.2f a list",
                   (int64_t)frames, draws_submitted / n, vertices_submitted / n, passes_rendered / n, submit_usec / 1000.0 / n, (int64_t)materials_made, (int64_t)materials.size(),
                   (int64_t)meshes_made, (int64_t)textures_made, (int64_t)depth_always_writes, (int64_t)stale_reads, (int64_t)approximated, (int64_t)skipped, (int64_t)redraws, passes_skipped / n) +
           vformat("; big draws written in place %d, made %d", (int64_t)big_reused, (int64_t)big_made) +
           (pack ? vformat("; art pack: %d pictures in the folder, textures named %d, found %d, replaced %d (%d from files, %d with mip maps of their own), %d files unreadable, %d of them two-field interface pictures (sampled by the woven line), %d waiting",
                           (int64_t)pack->size(), (int64_t)pack_named, (int64_t)pack_found, (int64_t)pack_replaced, (int64_t)pack_replaced_files,
                           (int64_t)(pack_replaced - pack_replaced_files), (int64_t)pack->failed_files.load(), (int64_t)pack->two_field.load(), (int64_t)pack->waiting()) : String());
}

// ---- the art pack and mip maps (rta_pack.h) -------------------------------------------------

int64_t RtaDrawer::set_art_pack(const String& folder, bool mipmaps) {
    if (pack) { delete pack; pack = nullptr; }
    pack_mipmaps = mipmaps;
    std::string dir = folder.utf8().get_data();
    size_t found = 0;
    if (!dir.empty() || mipmaps) {
        pack = new RtaPack;
        if (!dir.empty()) found = pack->open(dir);
        pack->start(3);
    }
    if (!dir.empty() && machine.is_valid()) machine->set_option("name_textures", "1");
    return (int64_t)found;
}

Dictionary RtaDrawer::get_pack_info() const {
    Dictionary d;
    d["folder"] = pack ? String::utf8(pack->folder().c_str()) : String();
    d["pictures"] = pack ? (int64_t)pack->size() : 0;
    d["mipmaps"] = pack_mipmaps;
    d["named"] = (int64_t)pack_named;
    d["found"] = (int64_t)pack_found;
    d["replaced"] = (int64_t)pack_replaced;
    d["replaced_from_files"] = (int64_t)pack_replaced_files;
    d["waiting"] = pack ? (int64_t)pack->waiting() : 0;
    d["files_failed"] = pack ? (int64_t)pack->failed_files.load() : 0;
    return d;
}

// Each frame: the new textures are handed to the pack's threads; what they finished replaces its texture's picture
// (the RID stays: materials keep pointing at it). Stop after 2 ms or ~48 MB; a burst of ready images must not
// consume a whole game frame. A single texture upload is indivisible. Pixels and mipmaps are unchanged.
void RtaDrawer::pack_frame(const rtag_frame& f) {
    if (!pack) return;
    RenderingServer* s = rs();
    if (f.texture_count) {
        uint32_t named = 0;
        if (pack->size() && rta_library().rtag_texture_names) {
            name_buffer.resize(f.texture_count);
            named = rta_library().rtag_texture_names(name_buffer.data(), f.texture_count);
        }
        for (uint32_t k = 0; k < f.texture_count; k++) {
            const rtag_texture& t = f.textures[k];
            RtaPack::Job job;
            job.texture = t.id;
            job.width = t.width; job.height = t.height;
            if (k < named && name_buffer[k].id == t.id && name_buffer[k].named) {
                pack_named++;
                job.file = pack->find(name_buffer[k], job.texels_w, job.texels_h);
                if (!job.file.empty()) pack_found++;
            }
            if (job.file.empty() && !pack_mipmaps) continue;
            job.own = std::make_shared<std::vector<uint8_t>>(t.rgba, t.rgba + (size_t)t.width * t.height * 4);
            job.serial = ++pack_serial;
            texture_serial[t.id] = job.serial;
            pack->ask(std::move(job));
        }
    }
    size_t handed = 0;
    const uint64_t upload_start = Time::get_singleton()->get_ticks_usec();
    RtaPack::Done done;
    while (handed < (48u << 20) && Time::get_singleton()->get_ticks_usec() - upload_start < 2000 && pack->take(done)) {
        auto want = texture_serial.find(done.texture);
        if (want == texture_serial.end() || want->second != done.serial || done.image.is_null()) continue;
        auto t = textures.find(done.texture);
        if (t == textures.end()) continue;
        texture_serial.erase(want);
        s->texture_replace(t->second, s->texture_2d_create(done.image));
        if (done.woven) {
            woven_textures.insert(t->second.get_id());
            woven_sizes[t->second.get_id()] = Vector2((float)done.woven_w, (float)done.woven_h);
        } else {
            woven_textures.erase(t->second.get_id());
            woven_sizes.erase(t->second.get_id());
        }
        handed += (size_t)done.image->get_data_size();
        pack_replaced++;
        if (done.from_file) pack_replaced_files++;
    }
}

void RtaDrawer::release() {
    if (!RenderingServer::get_singleton()) return;
    RenderingServer* s = rs();
    for (RID rid : retired) s->free_rid(rid);
    retired.clear();
    world_prepared.clear();
    warm_free();
    warm_scenario = RID();
    if (pack) { delete pack; pack = nullptr; }
    texture_serial.clear();
    scene_release();
    fill_free();
    card_free();
    cpu_textures.clear();
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
    ClassDB::bind_method(D_METHOD("get_shown_flipped"), &RtaDrawer::get_shown_flipped);
    ClassDB::bind_method(D_METHOD("get_shown_image"), &RtaDrawer::get_shown_image);
    ClassDB::bind_method(D_METHOD("figures"), &RtaDrawer::figures);
    ClassDB::bind_method(D_METHOD("dump_surfaces", "prefix"), &RtaDrawer::dump_surfaces);
    ClassDB::bind_method(D_METHOD("log_draws", "frames"), &RtaDrawer::log_draws);
    ClassDB::bind_method(D_METHOD("get_shown_stored"), &RtaDrawer::get_shown_stored);
    ClassDB::bind_method(D_METHOD("release"), &RtaDrawer::release);
    ClassDB::bind_method(D_METHOD("set_scene_mode", "on"), &RtaDrawer::set_scene_mode);
    ClassDB::bind_method(D_METHOD("set_art_pack", "folder", "mipmaps"), &RtaDrawer::set_art_pack);
    ClassDB::bind_method(D_METHOD("get_pack_info"), &RtaDrawer::get_pack_info);
    ClassDB::bind_method(D_METHOD("set_world_layer", "on", "table"), &RtaDrawer::set_world_layer);
    ClassDB::bind_method(D_METHOD("get_world_info", "frames_back"), &RtaDrawer::get_world_info);
    ClassDB::bind_method(D_METHOD("get_grass", "eye", "radius", "max_points"), &RtaDrawer::get_grass);
    ClassDB::bind_method(D_METHOD("get_grass_epoch"), &RtaDrawer::get_grass_epoch);
    ClassDB::bind_method(D_METHOD("world_reset"), &RtaDrawer::world_reset);
    ClassDB::bind_method(D_METHOD("set_world_hide", "volumes"), &RtaDrawer::set_world_hide);
    ClassDB::bind_method(D_METHOD("get_world_hide"), &RtaDrawer::get_world_hide);
    ClassDB::bind_method(D_METHOD("world_dump", "path"), &RtaDrawer::world_dump);
    ClassDB::bind_method(D_METHOD("set_scene_option", "name", "value"), &RtaDrawer::set_scene_option);
    ClassDB::bind_method(D_METHOD("get_scene_info"), &RtaDrawer::get_scene_info);
    ClassDB::bind_method(D_METHOD("get_piece_textures"), &RtaDrawer::get_piece_textures);
    ClassDB::bind_method(D_METHOD("get_world_scenario"), &RtaDrawer::get_world_scenario);
    ClassDB::bind_method(D_METHOD("set_hidden_objects", "objects"), &RtaDrawer::set_hidden_objects);
    ClassDB::bind_method(D_METHOD("set_hidden_skinned", "objects"), &RtaDrawer::set_hidden_skinned);
    ClassDB::bind_method(D_METHOD("get_world_camera"), &RtaDrawer::get_world_camera);
    ClassDB::bind_method(D_METHOD("get_world_viewport"), &RtaDrawer::get_world_viewport);
    ClassDB::bind_method(D_METHOD("redraw", "t"), &RtaDrawer::redraw);
    ClassDB::bind_method(D_METHOD("get_letterbox_left_out"), &RtaDrawer::get_letterbox_left_out);
    ClassDB::bind_method(D_METHOD("get_scene_camera"), &RtaDrawer::get_scene_camera);
    ClassDB::bind_method(D_METHOD("get_world_environment"), &RtaDrawer::get_world_environment);
    ClassDB::bind_method(D_METHOD("describe_frame", "max_lines"), &RtaDrawer::describe_frame);
    ClassDB::bind_method(D_METHOD("get_sky_info"), &RtaDrawer::get_sky_info);
    ClassDB::bind_method(D_METHOD("sky_reset"), &RtaDrawer::sky_reset);
    ClassDB::bind_method(D_METHOD("set_output_size", "size"), &RtaDrawer::set_output_size);
    ClassDB::bind_method(D_METHOD("set_fill_shader", "shader", "skirt_shader"), &RtaDrawer::set_fill_shader, DEFVAL(Ref<Shader>()));
    ClassDB::bind_method(D_METHOD("get_fill_info"), &RtaDrawer::get_fill_info);
    ClassDB::bind_method(D_METHOD("set_card_scenario", "scenario"), &RtaDrawer::set_card_scenario);
    ClassDB::bind_method(D_METHOD("card_focus", "feet", "capture"), &RtaDrawer::card_focus);
    ClassDB::bind_method(D_METHOD("set_card_turn", "radians"), &RtaDrawer::set_card_turn);
    ClassDB::bind_method(D_METHOD("get_card_info"), &RtaDrawer::get_card_info);
    ClassDB::bind_method(D_METHOD("get_output_size"), &RtaDrawer::get_output_size);
}

}  // namespace godot
