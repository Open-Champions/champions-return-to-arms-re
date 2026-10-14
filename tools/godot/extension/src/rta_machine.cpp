// rta_machine.cpp - see rta_machine.h.
#include "rta_machine.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/vector3.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <string>
#ifdef _WIN32
#include <direct.h>
#define chdir _chdir
#else
#include <unistd.h>
#endif
#include <vector>

namespace godot {

static std::string text_of(const Variant& value) {
    String s = value;
    return std::string(s.utf8().get_data());
}

bool RtaMachine::load_library(const String& path) {
    RtaLibrary& lib = rta_library();
    if (!lib.load(std::string(path.utf8().get_data()))) {
        error = String::utf8(lib.error.c_str());
        return false;
    }
    return true;
}

bool RtaMachine::change_directory(const String& path) { return chdir(path.utf8().get_data()) == 0; }

bool RtaMachine::has(const String& feature) const {
    RtaLibrary& lib = rta_library();
    return lib.loaded && lib.rtag_has(feature.utf8().get_data()) != 0;
}

int RtaMachine::start(const Dictionary& config) {
    RtaLibrary& lib = rta_library();
    if (!lib.loaded) { error = "no game library loaded"; return -1; }
    std::string disc = text_of(config.get("disc", "")), data = text_of(config.get("data", "")), workspace = text_of(config.get("workspace", ""));
    std::string elf = text_of(config.get("elf", "")), script = text_of(config.get("script", ""));
    PackedStringArray more = config.get("args", PackedStringArray());
    std::vector<std::string> args;
    for (int64_t k = 0; k < more.size(); k++) args.push_back(std::string(more[k].utf8().get_data()));
    std::vector<const char*> argv;
    for (auto& a : args) argv.push_back(a.c_str());
    rtag_config c;
    memset(&c, 0, sizeof c);
    c.struct_size = sizeof c;
    c.disc = disc.c_str();
    c.data_dir = data.c_str();
    c.workspace = workspace.empty() ? nullptr : workspace.c_str();
    c.elf = elf.empty() ? nullptr : elf.c_str();
    c.script = script.empty() ? nullptr : script.c_str();
    c.lists = (int)config.get("lists", 0);
    c.picture_width = (int)config.get("picture_width", 0);
    c.picture_height = (int)config.get("picture_height", 0);
    c.picture_every_frame = (int)config.get("picture_every_frame", 1);
    c.samples = (int)config.get("samples", 0);
    c.anisotropy = (int)config.get("anisotropy", 1);
    c.mipmaps = (int)config.get("mipmaps", 0);
    c.aspect = (double)config.get("aspect", 0.0);
    c.scene3d = (int)config.get("scene3d", 0);
    c.sound = (int)config.get("sound", RTAG_SOUND_PULL);
    c.gain = (double)config.get("gain", 1.0);
    std::string view = text_of(config.get("view", ""));
    c.view = view.empty() ? nullptr : view.c_str();
    c.emulator_timing = (int)config.get("emulator_timing", 0);
    c.films = (int)config.get("films", 1);
    c.argc = (int)argv.size();
    c.argv = argv.data();
    int result = lib.rtag_start(&c);
    if (result == 0) started = true;
    else error = result == -2 ? "no disc image at that path" : result == -3 ? "the game's executable is not on that disc image" : result == -4 ? "the machine was started before (one run per process)" : "bad configuration";
    return result;
}

void RtaMachine::set_pad(int port, int buttons, int lx, int ly, int rx, int ry) {
    if (!started) return;
    rtag_pad pad;
    pad.buttons = (uint16_t)buttons;
    pad.lx = (uint8_t)CLAMP(lx, 0, 255); pad.ly = (uint8_t)CLAMP(ly, 0, 255);
    pad.rx = (uint8_t)CLAMP(rx, 0, 255); pad.ry = (uint8_t)CLAMP(ry, 0, 255);
    rta_library().rtag_set_pad(port, &pad);
}

int RtaMachine::step(int wait_ms) {
    if (!started) return -1;
    const rtag_frame* next = nullptr;
    int got = rta_library().rtag_step(nullptr, wait_ms, &next);
    if (got == 1) frame = next;
    return got;
}

int RtaMachine::poll(int wait_ms) {
    if (!started) return -1;
    const rtag_frame* next = nullptr;
    int got = rta_library().rtag_poll(wait_ms, &next);
    if (got == 1) frame = next;
    return got;
}

void RtaMachine::run(double hz) { if (started) rta_library().rtag_run(hz); }
void RtaMachine::stop() { if (started) rta_library().rtag_stop(); }
bool RtaMachine::ended() const { return started && rta_library().rtag_ended() != 0; }
int RtaMachine::exit_code() const { return started ? rta_library().rtag_exit_code() : 0; }
String RtaMachine::info() const { return started ? String::utf8(rta_library().rtag_info()) : String(); }
int64_t RtaMachine::fields() const { return started ? (int64_t)rta_library().rtag_fields() : 0; }

Dictionary RtaMachine::get_view() const {
    Dictionary d;
    if (!frame) return d;
    const rtag_view& v = frame->view;
    static const char* const names[5] = {"overhead", "action", "chase", "shoulder", "first"};
    auto vec = [](const float* f) { return Vector3(f[0], f[1], f[2]); };
    d["valid"] = v.valid != 0;
    d["mode"] = v.mode;
    d["mode_name"] = String(v.mode >= 0 && v.mode < 5 ? names[v.mode] : "overhead");
    d["shown"] = v.shown;
    d["blend"] = v.blend;
    d["active"] = v.active != 0;
    d["fallback"] = v.fallback != 0;
    d["fallback_why"] = String::utf8(v.fallback_why);
    d["hide_player"] = v.hide_player != 0;
    d["eye"] = vec(v.eye); d["forward"] = vec(v.forward); d["up"] = vec(v.up); d["right"] = vec(v.right);
    d["fov"] = v.fov;
    d["head"] = vec(v.head);
    d["have_head"] = v.have_head != 0;
    d["yaw"] = v.yaw;
    d["near"] = v.near_plane; d["far"] = v.far_plane;
    d["player"] = vec(v.player);
    d["have_player"] = v.have_player != 0;
    d["facing"] = v.facing;
    d["look_pitch"] = v.look_pitch;
    d["tick"] = (int64_t)v.tick;
    return d;
}

bool RtaMachine::set_option(const String& key, const String& value) {
    return started && rta_library().rtag_set_option(key.utf8().get_data(), value.utf8().get_data()) != 0;
}

bool RtaMachine::fill(rtag_fill& out) const {
    memset(&out, 0, sizeof out);
    if (!started || !rta_library().rtag_fill_get) return false;
    return rta_library().rtag_fill_get(&out) != 0 && out.vertex_count > 0;
}

Dictionary RtaMachine::get_fill_info() const {
    Dictionary d;
    rtag_fill f;
    if (!fill(f)) return d;
    int ceilings = 0, skirts = 0;
    for (uint32_t k = 0; k < f.mesh_count; k++) (f.meshes[k].kind == RTAG_FILL_CEILING ? ceilings : skirts)++;
    d["level"] = String(f.level ? f.level : "");
    d["serial"] = (int64_t)f.serial;
    d["vertices"] = (int64_t)f.vertex_count;
    d["meshes"] = (int64_t)f.mesh_count;
    d["ceilings"] = ceilings;
    d["skirts"] = skirts;
    return d;
}

Dictionary RtaMachine::get_controls_hud() const {
    Dictionary d;
    if (!started || !rta_library().rtag_controls_hud) return d;
    rtag_controls c;
    memset(&c, 0, sizeof c);
    c.struct_size = sizeof c;
    if (!rta_library().rtag_controls_hud(&c)) return d;
    auto mark = [](const rtag_mark& m) {
        Dictionary o;
        o["valid"] = m.valid != 0; o["object"] = (int64_t)m.object; o["x"] = m.x; o["y"] = m.y; o["z"] = m.z;
        o["distance"] = m.distance; o["bearing"] = m.bearing; o["hp"] = m.hp; o["hp_max"] = m.hp_max;
        return o;
    };
    d["blank"] = (int64_t)c.blank; d["tick"] = (int64_t)c.tick; d["view"] = c.view;
    d["look"] = c.look != 0; d["playing"] = c.playing != 0; d["slot"] = c.slot; d["player"] = (int64_t)c.player;
    d["x"] = c.x; d["y"] = c.y; d["z"] = c.z;
    d["look_heading"] = c.look_heading; d["look_pitch"] = c.look_pitch; d["facing"] = c.facing; d["facing_error"] = c.facing_error;
    d["state"] = c.state; d["weapon_class"] = c.weapon_class; d["ranged"] = c.ranged != 0; d["aligning"] = c.aligning != 0;
    d["melee"] = mark(c.melee); d["shot"] = mark(c.shot); d["locked"] = mark(c.locked);
    d["reticle"] = c.reticle != 0;
    d["usable"] = c.usable != 0; d["usable_kind"] = c.usable_kind; d["usable_fade"] = c.usable_fade; d["usable_object"] = (int64_t)c.usable_object;
    d["usable_x"] = c.usable_x; d["usable_y"] = c.usable_y; d["usable_z"] = c.usable_z; d["usable_bearing"] = c.usable_bearing;
    c.usable_text[sizeof c.usable_text - 1] = 0;
    d["usable_text"] = String::utf8(c.usable_text);
    Array threats;
    for (int k = 0; k < c.threat_count && k < 16; k++) {
        const rtag_threat& t = c.threats[k];
        Dictionary o;
        o["object"] = (int64_t)t.object; o["x"] = t.x; o["y"] = t.y; o["z"] = t.z; o["distance"] = t.distance; o["bearing"] = t.bearing;
        o["targets_me"] = t.targets_me != 0; o["attacking"] = t.attacking != 0; o["in_view"] = t.in_view != 0;
        threats.push_back(o);
    }
    d["threat_count"] = c.threat_count; d["threats"] = threats; d["behind"] = c.behind;
    d["swings"] = (int64_t)c.swings; d["hits_dealt"] = (int64_t)c.hits_dealt; d["hits_taken"] = (int64_t)c.hits_taken;
    d["deaths"] = (int64_t)c.deaths; d["respawns"] = (int64_t)c.respawns;
    d["last_hit_bearing"] = c.last_hit_bearing; d["last_hit_amount"] = c.last_hit_amount;
    d["wants_pointer"] = c.wants_pointer != 0;
    return d;
}

void RtaMachine::mouse(double dx, double dy, double wheel) {
    if (started && rta_library().rtag_mouse) rta_library().rtag_mouse((float)dx, (float)dy, (float)wheel);
}

void RtaMachine::mouse_button(int button, bool down) {
    if (started && rta_library().rtag_mouse_button) rta_library().rtag_mouse_button(button, down ? 1 : 0);
}

bool RtaMachine::wants_pointer() const {
    if (!started || !rta_library().rtag_controls_hud) return false;
    rtag_controls c;
    memset(&c, 0, sizeof c);
    c.struct_size = sizeof c;
    return rta_library().rtag_controls_hud(&c) && c.wants_pointer;
}

PackedStringArray RtaMachine::get_shots() const {
    PackedStringArray out;
    if (frame) for (uint32_t k = 0; k < frame->shot_count; k++) out.push_back(String::utf8(frame->shots[k]));
    return out;
}

PackedStringArray RtaMachine::get_host_commands() const {
    PackedStringArray out;
    if (frame) for (uint32_t k = 0; k < frame->host_command_count; k++) out.push_back(String::utf8(frame->host_commands[k]));
    return out;
}

Ref<Image> RtaMachine::get_picture() const {
    if (!frame || !frame->picture || frame->picture_width <= 0) return Ref<Image>();
    PackedByteArray bytes;
    int64_t size = (int64_t)frame->picture_width * frame->picture_height * 4;
    bytes.resize(size);
    uint8_t* to = bytes.ptrw();
    memcpy(to, frame->picture, (size_t)size);
    for (int64_t k = 3; k < size; k += 4) to[k] = 255;      // the surface's alpha is the GS's, not a transparency
    return Image::create_from_data(frame->picture_width, frame->picture_height, false, Image::FORMAT_RGBA8, bytes);
}

int64_t RtaMachine::peek_u32(int64_t address) const {
    const uint8_t* ram = started ? rta_library().rtag_memory() : nullptr;
    if (!ram || address < 0 || address > 0x2000000 - 4) return 0;
    uint32_t v;
    memcpy(&v, ram + address, 4);
    return v;
}
Array RtaMachine::get_lights(const Vector3& at, double radius, int max_count) const {
    Array out;
    const uint8_t* ram = started ? rta_library().rtag_memory() : nullptr;
    if (!ram) return out;
    const uint32_t GRID = 0x5D34D8, OVERFLOW_LIST = 0x5DB368, LAYER = 0x4039A4;
    auto u32 = [&](uint32_t a) { uint32_t v = 0; if (a <= 0x2000000 - 4) memcpy(&v, ram + a, 4); return v; };
    auto f32 = [&](uint32_t a) { float v = 0; if (a <= 0x2000000 - 4) memcpy(&v, ram + a, 4); return v; };
    auto s16 = [&](uint32_t a) { int16_t v = 0; if (a <= 0x2000000 - 2) memcpy(&v, ram + a, 2); return (int)v; };
    const int32_t layer = (int32_t)u32(LAYER);
    std::vector<uint32_t> seen;
    auto walk = [&](uint32_t node) {
        // the game's own lists: a node's first word is the next one (the game changes them while this reads: bounded)
        for (int guard = 0; node && guard < 256 && (int)out.size() < max_count; guard++) {
            node &= 0x1FFFFFF;
            if (node < 0x100000 || node > 0x2000000 - 0x40) break;
            uint32_t next = u32(node);
            if (std::find(seen.begin(), seen.end(), node) != seen.end()) break;
            seen.push_back(node);
            int8_t node_layer = (int8_t)ram[node + 8];
            Vector3 p(f32(node + 0x30), f32(node + 0x34), f32(node + 0x38));
            float r = f32(node + 0x1c);        // what light_collectNear reaches with (falloff +0x28 is 1 / r^2 for the level's lights)
            if (node_layer == (int8_t)layer && std::isfinite(p.x) && std::isfinite(r) && r > 0 && r < 20000 && p.distance_to(at) < radius + r) {
                Dictionary d;
                d["address"] = (int64_t)node;
                d["position"] = p;
                d["colour"] = Color(s16(node + 0x12) / 128.0f, s16(node + 0x14) / 128.0f, s16(node + 0x16) / 128.0f, s16(node + 0x18) / 128.0f);
                d["model_colour"] = Color(s16(node + 0x0a) / 128.0f, s16(node + 0x0c) / 128.0f, s16(node + 0x0e) / 128.0f);
                d["radius"] = r;
                d["radius_2"] = f32(node + 0x20);
                d["falloff"] = f32(node + 0x28);
                d["floor"] = f32(node + 0x2c);
                d["layer"] = (int)node_layer;
                out.push_back(d);
            }
            node = next;
        }
    };
    const int cells = 90;
    int x0 = (int)std::floor((at.x - radius + 11520.0) / 256.0), x1 = (int)std::floor((at.x + radius + 11520.0) / 256.0);
    int y0 = (int)std::floor((at.y - radius + 11520.0) / 256.0), y1 = (int)std::floor((at.y + radius + 11520.0) / 256.0);
    x0 = std::max(x0, 0); y0 = std::max(y0, 0); x1 = std::min(x1, cells - 1); y1 = std::min(y1, cells - 1);
    for (int y = y0; y <= y1; y++)
        for (int x = x0; x <= x1; x++) walk(u32(GRID + 4u * (uint32_t)(y * cells + x)));
    walk(u32(OVERFLOW_LIST));
    return out;
}

double RtaMachine::peek_f32(int64_t address) const {
    const uint8_t* ram = started ? rta_library().rtag_memory() : nullptr;
    if (!ram || address < 0 || address > 0x2000000 - 4) return 0;
    float v;
    memcpy(&v, ram + address, 4);
    return v;
}
String RtaMachine::peek_string(int64_t address, int max_bytes) const {
    const uint8_t* ram = started ? rta_library().rtag_memory() : nullptr;
    if (!ram || address < 0 || max_bytes <= 0 || address + max_bytes > 0x2000000) return String();
    std::string out;
    for (int k = 0; k < max_bytes && ram[address + k]; k++) out.push_back((char)ram[address + k]);
    return String::utf8(out.c_str());
}

void RtaMachine::_bind_methods() {
    ClassDB::bind_method(D_METHOD("load_library", "path"), &RtaMachine::load_library);
    ClassDB::bind_method(D_METHOD("change_directory", "path"), &RtaMachine::change_directory);
    ClassDB::bind_method(D_METHOD("get_error"), &RtaMachine::get_error);
    ClassDB::bind_method(D_METHOD("has", "feature"), &RtaMachine::has);
    ClassDB::bind_method(D_METHOD("start", "config"), &RtaMachine::start);
    ClassDB::bind_method(D_METHOD("set_pad", "port", "buttons", "lx", "ly", "rx", "ry"), &RtaMachine::set_pad);
    ClassDB::bind_method(D_METHOD("step", "wait_ms"), &RtaMachine::step);
    ClassDB::bind_method(D_METHOD("poll", "wait_ms"), &RtaMachine::poll);
    ClassDB::bind_method(D_METHOD("run", "hz"), &RtaMachine::run);
    ClassDB::bind_method(D_METHOD("stop"), &RtaMachine::stop);
    ClassDB::bind_method(D_METHOD("ended"), &RtaMachine::ended);
    ClassDB::bind_method(D_METHOD("exit_code"), &RtaMachine::exit_code);
    ClassDB::bind_method(D_METHOD("info"), &RtaMachine::info);
    ClassDB::bind_method(D_METHOD("fields"), &RtaMachine::fields);
    ClassDB::bind_method(D_METHOD("has_frame"), &RtaMachine::has_frame);
    ClassDB::bind_method(D_METHOD("get_frame_number"), &RtaMachine::get_frame_number);
    ClassDB::bind_method(D_METHOD("get_sim_tick"), &RtaMachine::get_sim_tick);
    ClassDB::bind_method(D_METHOD("get_frame_aspect"), &RtaMachine::get_frame_aspect);
    ClassDB::bind_method(D_METHOD("get_draw_count"), &RtaMachine::get_draw_count);
    ClassDB::bind_method(D_METHOD("get_vertex_count"), &RtaMachine::get_vertex_count);
    ClassDB::bind_method(D_METHOD("get_view"), &RtaMachine::get_view);
    ClassDB::bind_method(D_METHOD("set_option", "key", "value"), &RtaMachine::set_option);
    ClassDB::bind_method(D_METHOD("get_controls_hud"), &RtaMachine::get_controls_hud);
    ClassDB::bind_method(D_METHOD("get_fill_info"), &RtaMachine::get_fill_info);
    ClassDB::bind_method(D_METHOD("mouse", "dx", "dy", "wheel"), &RtaMachine::mouse);
    ClassDB::bind_method(D_METHOD("mouse_button", "button", "down"), &RtaMachine::mouse_button);
    ClassDB::bind_method(D_METHOD("wants_pointer"), &RtaMachine::wants_pointer);
    ClassDB::bind_method(D_METHOD("get_shots"), &RtaMachine::get_shots);
    ClassDB::bind_method(D_METHOD("get_host_commands"), &RtaMachine::get_host_commands);
    ClassDB::bind_method(D_METHOD("get_picture"), &RtaMachine::get_picture);
    ClassDB::bind_method(D_METHOD("peek_u32", "address"), &RtaMachine::peek_u32);
    ClassDB::bind_method(D_METHOD("peek_f32", "address"), &RtaMachine::peek_f32);
    ClassDB::bind_method(D_METHOD("peek_string", "address", "max_bytes"), &RtaMachine::peek_string);
    ClassDB::bind_method(D_METHOD("get_lights", "at", "radius", "max_count"), &RtaMachine::get_lights);
}

}  // namespace godot
