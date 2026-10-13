// rta_gamestate.cpp - see rta_gamestate.h.
#include "rta_gamestate.h"

#include "rta_library.h"

#include <godot_cpp/core/class_db.hpp>

// the reader itself: one source for this extension and for the native application
#include "../../../recomp/app/gamestate.cpp"

using namespace godot;

RtaGameState::RtaGameState() {
    reader = rta_gs_create();
    state = rta_gs_state(reader);
}

RtaGameState::~RtaGameState() { rta_gs_destroy(reader); }

bool RtaGameState::update(Object* machine) {
    const uint8_t* ram = (machine && rta_library().loaded) ? rta_library().rtag_memory() : nullptr;
    state = rta_gs_update(reader, ram);
    return ram != nullptr;
}

void RtaGameState::set_aspect(double aspect) { rta_gs_set_aspect(reader, (float)aspect); }
void RtaGameState::set_screen_delay(int frames) { rta_gs_set_screen_delay(reader, frames); }
double RtaGameState::get_cost_usec() const { return rta_gs_cost_usec(reader); }

static void put(float* to, const Variant& v) {
    Vector3 p = v;
    to[0] = p.x; to[1] = p.y; to[2] = p.z;
}

void RtaGameState::set_view(const Dictionary& view) {
    if (view.is_empty() || !view.has("eye")) { rta_gs_set_view(reader, nullptr); return; }
    rta_gs_view v;
    memset(&v, 0, sizeof v);
    v.mode = (int)view.get("mode", 0);
    v.shown = (int)view.get("shown", v.mode);
    v.blend = (float)(double)view.get("blend", 0.0);
    v.active = (bool)view.get("active", false);
    v.fallback = (bool)view.get("fallback", false);
    v.hide_player = (bool)view.get("hide_player", false);
    CharString why = String(view.get("why", "")).utf8();
    strncpy(v.fallback_why, why.get_data(), sizeof v.fallback_why - 1);
    put(v.eye, view["eye"]);
    put(v.forward, view.get("forward", Vector3(1, 0, 0)));
    put(v.up, view.get("up", Vector3(0, 0, 1)));
    put(v.right, view.get("right", Vector3(0, -1, 0)));
    v.fov = (float)(double)view.get("fov", 50.0);
    if (view.has("head")) { put(v.head, view["head"]); v.have_head = 1; }
    v.yaw = atan2f(v.forward[1], v.forward[0]);
    rta_gs_set_view(reader, &v);
}

static Vector3 vec(const float* p) { return Vector3(p[0], p[1], p[2]); }
static String text(const char* s) { return String::utf8(s); }

static PackedFloat32Array status_array(const rta_gs_status* list, uint32_t count) {
    PackedFloat32Array a;
    a.resize((int64_t)count * 4);
    float* w = a.ptrw();
    for (uint32_t k = 0; k < count; k++) {
        w[k * 4 + 0] = list[k].kind;
        w[k * 4 + 1] = list[k].detail;
        w[k * 4 + 2] = list[k].seconds;
        w[k * 4 + 3] = list[k].seconds_most;
    }
    return a;
}

Dictionary RtaGameState::get_frame() const {
    const rta_gamestate& s = *state;
    Dictionary d;
    d["tick"] = (int64_t)s.sim_tick;
    d["phase"] = (int64_t)s.phase;
    d["hud_hidden"] = s.hud_hidden != 0;
    d["level"] = text(s.level);
    d["level_title"] = text(s.level_title);
    d["player_count"] = s.player_count;
    d["local_slot"] = s.local_slot;
    d["creature_count"] = s.creature_count;
    d["creatures_dropped"] = s.creatures_dropped;
    d["boss_uid"] = (int64_t)s.boss_uid;
    d["message"] = text(s.message);
    d["message_frames"] = s.message_frames;
    d["compass_on"] = s.compass_on != 0;
    d["compass_target"] = vec(s.compass_target);
    d["online"] = s.online != 0;
    d["net_notice"] = (int)s.net_notice;
    d["net_notice_slot"] = (int)s.net_notice_slot;
    d["net_stall_frames"] = s.net_stall_frames;
    d["net_exit_frames"] = s.net_exit_frames;
    if (s.chat_count > 0) {
        Array chat;
        for (int k = 0; k < s.chat_count; k++) {
            Array line;
            line.push_back((int)s.chat_slot[k]);
            line.push_back(text(s.chat[k]));
            chat.push_back(line);
        }
        d["chat"] = chat;
    }
    Dictionary v;
    v["mode"] = s.view.mode;
    v["shown"] = s.view.shown;
    v["blend"] = s.view.blend;
    v["active"] = s.view.active != 0;
    v["fallback"] = s.view.fallback != 0;
    v["why"] = text(s.view.fallback_why);
    v["hide_player"] = s.view.hide_player != 0;
    v["eye"] = vec(s.view.eye);
    v["forward"] = vec(s.view.forward);
    v["right"] = vec(s.view.right);
    v["up"] = vec(s.view.up);
    v["fov"] = s.view.fov;
    v["yaw"] = s.view.yaw;
    d["view"] = v;
    Dictionary p;
    p["active"] = s.prompt.active != 0;
    if (s.prompt.active) {
        p["kind"] = (int)s.prompt.kind;
        p["slot"] = (int)s.prompt.slot;
        p["text"] = text(s.prompt.text);
        p["button"] = (int64_t)s.prompt.button;
        p["position"] = vec(s.prompt.position);
        p["object"] = (int64_t)s.prompt.object;
    }
    d["prompt"] = p;
    return d;
}

Dictionary RtaGameState::get_player(int slot) const {
    Dictionary d;
    if (slot < 0 || slot >= RTA_GS_PLAYERS || !state->player[slot].present) { d["present"] = false; return d; }
    const rta_gs_player& p = state->player[slot];
    d["present"] = true;
    d["slot"] = slot;
    d["local"] = p.local != 0;
    d["alive"] = p.alive != 0;
    d["in_menu"] = p.in_menu != 0;
    d["name"] = text(p.name);
    d["class_name"] = text(p.class_name);
    d["class_index"] = p.class_index;
    d["level"] = (int)p.level;
    d["level_ack"] = (int)p.level_acknowledged;
    d["stat_points"] = (int)p.stat_points;
    d["skill_points"] = p.skill_points;
    d["health"] = p.health;
    d["health_max"] = p.health_max;
    d["health_coming"] = p.health_coming;
    d["mana"] = p.mana;
    d["mana_max"] = p.mana_max;
    d["mana_coming"] = p.mana_coming;
    d["xp"] = p.experience;
    d["xp_base"] = p.experience_base;
    d["xp_next"] = p.experience_next;
    d["gold"] = p.gold;
    d["gold_coming"] = p.gold_coming;
    d["health_potions"] = p.health_potions;
    d["mana_potions"] = p.mana_potions;
    d["ammunition"] = p.ammunition;
    d["weapon"] = text(p.weapon);
    d["weapon_class"] = (int)p.weapon_class;
    d["action"] = p.action_state;
    d["target_uid"] = (int64_t)p.target_uid;
    d["position"] = vec(p.position);
    d["height"] = p.height;
    d["facing"] = p.facing;
    d["screen"] = vec(p.screen);
    d["status"] = status_array(p.status, p.status_count);
    d["selector_open"] = p.selector_open != 0;
    d["selector_position"] = (int)p.selector_position;
    Array slots;
    for (int k = 0; k < RTA_GS_SLOTS; k++) {
        const rta_gs_slot& q = p.slot[k];
        Dictionary e;
        e["filled"] = q.filled != 0;
        if (q.filled) {
            e["name"] = text(q.name);
            e["skill_id"] = (int)q.skill_id;
            e["rank"] = (int)q.rank;
            e["kind"] = (int)q.kind;
            e["mana_cost"] = q.mana_cost;
            e["cooldown"] = q.cooldown;
            e["cooldown_most"] = q.cooldown_most;
            e["active"] = q.active != 0;
            e["enough_mana"] = q.enough_mana != 0;
        }
        slots.push_back(e);
    }
    d["slots"] = slots;
    return d;
}

PackedFloat32Array RtaGameState::get_creatures() const {
    const int STRIDE = 14;
    PackedFloat32Array a;
    int n = state->creature_count;
    a.resize((int64_t)n * STRIDE);
    float* w = a.ptrw();
    for (int k = 0; k < n; k++, w += STRIDE) {
        const rta_gs_creature& c = state->creature[k];
        w[0] = (float)c.uid;
        w[1] = (float)c.flags;
        w[2] = c.health;
        w[3] = c.health_max;
        w[4] = c.screen[0];
        w[5] = c.screen[1];
        w[6] = c.screen[2];
        w[7] = c.position[0];
        w[8] = c.position[1];
        w[9] = c.position[2];
        w[10] = c.height;
        w[11] = c.facing;
        w[12] = (float)c.target_slot;
        w[13] = (float)c.boss_rank;
    }
    return a;
}

String RtaGameState::get_creature_name(int index) const {
    if (index < 0 || index >= state->creature_count) return String();
    return text(state->creature[index].name);
}

PackedFloat32Array RtaGameState::get_creature_status(int index) const {
    if (index < 0 || index >= state->creature_count) return PackedFloat32Array();
    return status_array(state->creature[index].status, state->creature[index].status_count);
}

Array RtaGameState::get_events() const {
    Array out;
    for (int k = 0; k < state->event_count; k++) {
        const rta_gs_event& e = state->event[k];
        Dictionary d;
        d["kind"] = (int)e.kind;
        d["slot"] = (int)e.slot;
        d["uid"] = (int64_t)e.uid;
        d["amount"] = e.amount;
        d["heavy"] = e.heavy != 0;
        d["position"] = vec(e.position);
        d["text"] = text(e.text);
        out.push_back(d);
    }
    return out;
}

Vector3 RtaGameState::project(const Vector3& world) const {
    float in[3] = {world.x, world.y, world.z}, out[3];
    rta_gs_project(reader, in, out);
    return Vector3(out[0], out[1], out[2]);
}

void RtaGameState::_bind_methods() {
    ClassDB::bind_method(D_METHOD("update", "machine"), &RtaGameState::update);
    ClassDB::bind_method(D_METHOD("set_aspect", "aspect"), &RtaGameState::set_aspect);
    ClassDB::bind_method(D_METHOD("set_view", "view"), &RtaGameState::set_view);
    ClassDB::bind_method(D_METHOD("set_screen_delay", "frames"), &RtaGameState::set_screen_delay);
    ClassDB::bind_method(D_METHOD("get_frame"), &RtaGameState::get_frame);
    ClassDB::bind_method(D_METHOD("get_player", "slot"), &RtaGameState::get_player);
    ClassDB::bind_method(D_METHOD("get_creatures"), &RtaGameState::get_creatures);
    ClassDB::bind_method(D_METHOD("get_creature_name", "index"), &RtaGameState::get_creature_name);
    ClassDB::bind_method(D_METHOD("get_creature_status", "index"), &RtaGameState::get_creature_status);
    ClassDB::bind_method(D_METHOD("get_events"), &RtaGameState::get_events);
    ClassDB::bind_method(D_METHOD("project", "world"), &RtaGameState::project);
    ClassDB::bind_method(D_METHOD("get_cost_usec"), &RtaGameState::get_cost_usec);
    ClassDB::bind_method(D_METHOD("get_struct_size"), &RtaGameState::get_struct_size);
}
