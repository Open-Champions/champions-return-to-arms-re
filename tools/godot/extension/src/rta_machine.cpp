// rta_machine.cpp - see rta_machine.h.
#include "rta_machine.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/vector3.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

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
    ClassDB::bind_method(D_METHOD("get_shots"), &RtaMachine::get_shots);
    ClassDB::bind_method(D_METHOD("get_host_commands"), &RtaMachine::get_host_commands);
    ClassDB::bind_method(D_METHOD("get_picture"), &RtaMachine::get_picture);
    ClassDB::bind_method(D_METHOD("peek_u32", "address"), &RtaMachine::peek_u32);
    ClassDB::bind_method(D_METHOD("peek_f32", "address"), &RtaMachine::peek_f32);
    ClassDB::bind_method(D_METHOD("peek_string", "address", "max_bytes"), &RtaMachine::peek_string);
}

}  // namespace godot
