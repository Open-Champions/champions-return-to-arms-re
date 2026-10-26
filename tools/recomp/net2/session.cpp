// session.cpp - the calls of session.h: checks of what was typed, the snapshots, and the
// choice of the body behind them (the service, the mock, or nothing).
#include "session_impl.h"

#include <algorithm>
#include <cstdlib>

namespace net2impl {

const char CODE_ALPHABET[33] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

std::string code_normal(const char* text, size_t want) {
    std::string out;
    if (!text) return out;
    for (const char* p = text; *p; p++) {
        char c = *p;
        if (c == '-' || c == ' ') continue;
        if (c >= 'a' && c <= 'z') c = (char)(c - 32);
        if (!strchr(CODE_ALPHABET, c)) return "";
        out += c;
        if (out.size() > want) return "";
    }
    return out.size() == want ? out : "";
}

std::string friend_code_shown(const std::string& normal) {
    return normal.size() == 8 ? normal.substr(0, 4) + "-" + normal.substr(4) : normal;
}

static bool utf8_ok(const std::string& text) {
    size_t i = 0;
    while (i < text.size()) {
        unsigned char c = (unsigned char)text[i];
        size_t more = c < 0x80 ? 0 : (c >> 5) == 6 ? 1 : (c >> 4) == 14 ? 2 : (c >> 3) == 30 ? 3 : 99;
        if (more == 99 || i + more >= text.size()) return false;
        for (size_t k = 1; k <= more; k++)
            if (((unsigned char)text[i + k] & 0xC0) != 0x80) return false;
        i += more + 1;
    }
    return true;
}

std::string name_problem(const char* name) {
    if (!name) return "A name is needed.";
    std::string text = name;
    if (text.size() < 3) return "A name has at least 3 characters.";
    if (text.size() > 24) return "A name has at most 24 characters.";
    if (!utf8_ok(text)) return "That name is not readable text.";
    if (text.front() == ' ' || text.back() == ' ') return "A name does not begin or end with a blank.";
    for (unsigned char c : text)
        if (c < 0x20 || c == 0x7f) return "A name is plain text.";
    return "";
}

static std::string cleaned(const char* text, size_t most, bool keep_spaces) {
    std::string out;
    if (!text) return out;
    for (const char* p = text; *p; p++) {
        unsigned char c = (unsigned char)*p;
        if (c < 0x20 || c == 0x7f) c = ' ';
        out += (char)c;
    }
    if (!utf8_ok(out)) {
        for (char& c : out)
            if ((unsigned char)c >= 0x80) c = '?';
    }
    while (out.size() > most) out.pop_back();
    while (!out.empty() && ((unsigned char)out.back() & 0xC0) == 0x80) out.pop_back();     // a cut sequence
    if (!out.empty() && (unsigned char)out.back() >= 0xC0) out.pop_back();
    size_t a = out.find_first_not_of(' ');
    size_t b = out.find_last_not_of(' ');
    out = a == std::string::npos ? "" : out.substr(a, b - a + 1);
    (void)keep_spaces;
    return out;
}
std::string clean_text(const char* text, size_t most) { return cleaned(text, most, true); }
std::string clean_label(const char* text, size_t most) { return cleaned(text, most, true); }

bool id_ok(const char* id) {
    if (!id || strlen(id) != 32) return false;
    for (const char* p = id; *p; p++)
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
    return true;
}

void State::sort_friends() {
    std::stable_sort(friends.begin(), friends.end(), [](const net2_friend& a, const net2_friend& b) {
        bool ao = a.presence != NET2_OFFLINE, bo = b.presence != NET2_OFFLINE;
        if (ao != bo) return ao;
        return strcasecmp(a.name, b.name) < 0;
    });
}

void State::room_checks() {
    room.all_ready = room.count > 1;
    room.mismatch = 0;
    room.warning[0] = 0;
    const net2_member* first = nullptr;
    for (int i = 0; i < room.count; i++) {
        const net2_member& m = room.members[i];
        if (!m.host && !m.ready) room.all_ready = 0;
        if (m.fix_set == 0 && m.fix_words == 0 && m.arith_can == 0) continue;    // said nothing about its copy
        if (!first) { first = &m; continue; }
        char text[NET2_TEXT];
        if ((m.fix_words & 0x8000) != (first->fix_words & 0x8000)) {
            // the souls-style combat mode (tools/recomp/app/soulscombat.h) is a room option every copy must have
            snprintf(text, sizeof text, "Hardcore mode is %s for %s and %s for %s: every copy must have it. Do not start.",
                     (m.fix_words & 0x8000) ? "on" : "off", m.name, (first->fix_words & 0x8000) ? "on" : "off", first->name);
            room.mismatch = 1;
            put(room.warning, text);
        } else if ((m.fix_words & 0x4000) != (first->fix_words & 0x4000)) {
            // aiming by looking (tools/recomp/app/fpaim.h), the same kind of room option
            snprintf(text, sizeof text, "Aiming by looking is %s for %s and %s for %s: every copy must have it. Do not start.",
                     (m.fix_words & 0x4000) ? "on" : "off", m.name, (first->fix_words & 0x4000) ? "on" : "off", first->name);
            room.mismatch = 1;
            put(room.warning, text);
        } else if ((m.fix_words & 0x2000) != (first->fix_words & 0x2000)) {
            // Remastered (hold to skip a cut scene, tools/recomp/app/cinematic.h, and the portal's type)
            snprintf(text, sizeof text, "%s plays %s and %s plays %s: every copy must play the same. Do not start.",
                     m.name, (m.fix_words & 0x2000) ? "Remastered" : "Classic", first->name, (first->fix_words & 0x2000) ? "Remastered" : "Classic");
            room.mismatch = 1;
            put(room.warning, text);
        } else if (m.fix_set != first->fix_set || m.fix_words != first->fix_words) {
            snprintf(text, sizeof text, "%s has a different fix set (%08x, %u words) from %s (%08x, %u words): the game would fall out of step. Do not start.",
                     m.name, m.fix_set, m.fix_words, first->name, first->fix_set, first->fix_words);
            room.mismatch = 1;
            put(room.warning, text);
        } else if (m.arith_does != first->arith_does && !room.mismatch) {
            snprintf(text, sizeof text, "%s computes with %s arithmetic and %s with %s: the game would fall out of step. Do not start.",
                     m.name, m.arith_does ? "a browser's" : "the console's", first->name, first->arith_does ? "a browser's" : "the console's");
            room.mismatch = 1;
            put(room.warning, text);
        }
    }
}

// ---- no service at all ---------------------------------------------------------------
namespace {
struct Off : Backend {
    explicit Off(const net2_config& config) {
        s.me.link = NET2_LINK_OFF;
        put(s.me.name, config.name && *config.name ? config.name : "Player");
        put(s.me.problem, "No service was named.");
    }
    int no() { return s.error(NET2_ERR_OFFLINE, "There is no link to a service."); }
    void poll() override {}
    int set_name(const std::string& name) override { put(s.me.name, name); s.event(NET2_EV_ME); return NET2_OK; }
    int set_character(const net2_character* c) override { if (c) s.me.character = *c; else s.me.character = net2_character{}; return NET2_OK; }
    int set_game(const std::string&) override { return NET2_OK; }
    int delete_everything() override { return no(); }
    int friend_add(const std::string&) override { return no(); }
    int friend_op(const char*, const std::string&) override { return no(); }
    int invite(const std::string&) override { return no(); }
    int invite_answer(const std::string&, bool) override { return no(); }
    int host(const net2_options&) override { return no(); }
    int join(const std::string&) override { return no(); }
    int join_friend(const std::string&) override { return no(); }
    int chat(const std::string&) override { return no(); }
    int ready(bool) override { return no(); }
    int set_options(const net2_options&) override { return no(); }
    int kick(int) override { return no(); }
    int start() override { return no(); }
    int leave() override { return NET2_OK; }
    int game_state(const std::string&, bool) override { return NET2_OK; }
};
}  // namespace
Backend* make_off(const net2_config& config) { return new Off(config); }

}  // namespace net2impl

using namespace net2impl;

template <class T> static int copy_out(const std::vector<T>& list, T* out, int max) {
    int count = (int)std::min<size_t>(list.size(), max < 0 ? 0 : (size_t)max);
    if (out && count) memcpy(out, list.data(), sizeof(T) * count);
    return out ? count : (int)list.size();      // out == NULL: how many there are
}

#ifdef NET2_NO_SERVICE
namespace net2impl {
Backend* make_service(const net2_config& config) { return make_off(config); }
}
#endif

namespace net2impl {
std::recursive_mutex& big_lock() {
    static std::recursive_mutex lock;
    return lock;
}
}
#define LOCKED std::lock_guard<std::recursive_mutex> hold_(net2impl::big_lock())

// Where the service is, when the program did not say: the environment, then one line in a
// file beside the identity, then the built-in default (none: the owner has not decided
// where the service runs).
static const char* NET2_DEFAULT_SERVICE = "";       // "host:port" once the owner has decided where the service runs
static std::string find_service(const net2_config& config) {
    if (config.service && *config.service) return config.service;
    if (const char* env = getenv("RTA_NET2_SERVICE"))
        if (*env) return env;
    if (config.data_dir && *config.data_dir) {
        std::string path = std::string(config.data_dir) + "/net2-service.txt";
        if (FILE* f = fopen(path.c_str(), "r")) {
            char text[160] = "";
            if (!fgets(text, sizeof text, f)) text[0] = 0;
            fclose(f);
            std::string line = clean_text(text, 120);
            if (!line.empty() && line[0] != '#') return line;
        }
    }
    return NET2_DEFAULT_SERVICE;
}

extern "C" {

net2* net2_open(const net2_config* given) {
    net2_config config{};
    if (given) memcpy(&config, given, std::min<size_t>(given->struct_size ? given->struct_size : sizeof config, sizeof config));
    net2* n = new net2;
    LOCKED;
    std::string service = find_service(config);
    bool mock = config.mock || service == "mock";
    config.service = service.c_str();
    if (mock) n->body = make_mock(config);
    else if (!service.empty()) n->body = make_service(config);
    else n->body = make_off(config);
    return n;
}

void net2_close(net2* n) {
    LOCKED;
    if (!n) return;
    delete n->body;
    delete n;
}

void net2_poll(net2* n) { LOCKED; if (n) n->body->poll(); }

int net2_next_event(net2* n, net2_event* out) {
    LOCKED;
    if (!n || n->body->s.events.empty()) return 0;
    if (out) *out = n->body->s.events.front();
    n->body->s.events.pop_front();
    return 1;
}

void net2_me(net2* n, net2_me_t* out) { LOCKED; if (n && out) *out = n->body->s.me; }

int net2_set_name(net2* n, const char* name) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    std::string problem = name_problem(name);
    if (!problem.empty()) return n->body->s.error(NET2_ERR_ARGUMENT, problem);
    return n->body->set_name(name);
}

int net2_set_character(net2* n, const net2_character* character) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    if (!character) return n->body->set_character(nullptr);
    net2_character c{};
    put(c.name, clean_label(character->name, 24));
    put(c.cls, clean_label(character->cls, 20));
    c.level = character->level < 0 ? 0 : character->level > 999 ? 999 : character->level;
    return n->body->set_character(&c);
}

int net2_set_game(net2* n, const char* level) {
    LOCKED;
    return n ? n->body->set_game(clean_label(level, 20)) : NET2_ERR_ARGUMENT;
}

int net2_local_characters(net2* n, const char* card_dir, net2_character* out, int max) {
    LOCKED;
    if (!out || max <= 0) return 0;
    int count = card_characters(card_dir, out, max);
    if (count == 0 && n && n->body->s.me.mock && (!card_dir || !*card_dir)) {
        // the mock, asked without a card: three to draw a list with
        static const net2_character FAKES[3] = {{"Brakka", "Barbarian", 34}, {"Lirael", "Ranger", 12}, {"Old Tessa", "Cleric", 47}};
        for (; count < 3 && count < max; count++) out[count] = FAKES[count];
    }
    return count;
}

int net2_delete_everything(net2* n) { LOCKED; return n ? n->body->delete_everything() : NET2_ERR_ARGUMENT; }

int net2_friends(net2* n, net2_friend* out, int max) { LOCKED; return n ? copy_out(n->body->s.friends, out, max) : 0; }
int net2_recent(net2* n, net2_friend* out, int max) { LOCKED; return n ? copy_out(n->body->s.recent, out, max) : 0; }
int net2_blocked(net2* n, net2_friend* out, int max) { LOCKED; return n ? copy_out(n->body->s.blocked, out, max) : 0; }
int net2_requests(net2* n, net2_request* out, int max) { LOCKED; return n ? copy_out(n->body->s.requests, out, max) : 0; }
int net2_invites(net2* n, net2_invite_t* out, int max) { LOCKED; return n ? copy_out(n->body->s.invites, out, max) : 0; }

int net2_friend_add(net2* n, const char* friend_code) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    std::string code = code_normal(friend_code, 8);
    if (code.empty()) return n->body->s.error(NET2_ERR_ARGUMENT, "A friend code is eight letters and digits, like K7QF-2MXD.");
    return n->body->friend_add(code);
}
static int friend_op(net2* n, const char* op, const char* id) {
    if (!n) return NET2_ERR_ARGUMENT;
    if (!id_ok(id)) return n->body->s.error(NET2_ERR_ARGUMENT, "That is not a player.");
    return n->body->friend_op(op, id);
}
int net2_friend_add_id(net2* n, const char* id) { LOCKED; return friend_op(n, "add-id", id); }
int net2_friend_accept(net2* n, const char* id) { LOCKED; return friend_op(n, "accept", id); }
int net2_friend_decline(net2* n, const char* id) { LOCKED; return friend_op(n, "decline", id); }
int net2_friend_remove(net2* n, const char* id) { LOCKED; return friend_op(n, "remove", id); }
int net2_block(net2* n, const char* id) { LOCKED; return friend_op(n, "block", id); }
int net2_unblock(net2* n, const char* id) { LOCKED; return friend_op(n, "unblock", id); }

int net2_invite(net2* n, const char* friend_id) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    if (!id_ok(friend_id)) return n->body->s.error(NET2_ERR_ARGUMENT, "That is not a player.");
    if (n->body->s.room.state != NET2_ROOM_OPEN) return n->body->s.error(NET2_ERR_STATE, "You are not in a room that is open.");
    return n->body->invite(friend_id);
}
int net2_invite_accept(net2* n, const char* from_id) {
    LOCKED;
    if (!n || !id_ok(from_id)) return NET2_ERR_ARGUMENT;
    if (n->body->s.room.state != NET2_ROOM_NONE) return n->body->s.error(NET2_ERR_STATE, "Leave the room you are in first.");
    return n->body->invite_answer(from_id, true);
}
int net2_invite_dismiss(net2* n, const char* from_id) {
    LOCKED;
    if (!n || !id_ok(from_id)) return NET2_ERR_ARGUMENT;
    return n->body->invite_answer(from_id, false);
}

void net2_room(net2* n, net2_room_t* out) { LOCKED; if (n && out) *out = n->body->s.room; }

static net2_options clean_options(const net2_options* given) {
    net2_options o{};
    if (given) {
        put(o.level, clean_label(given->level, 20));
        o.difficulty = given->difficulty < 0 || given->difficulty > 9 ? 0 : given->difficulty;
        o.mode = given->mode < 0 || given->mode > 9 ? 0 : given->mode;
        o.open_to = given->open_to == NET2_OPEN_FRIENDS ? NET2_OPEN_FRIENDS : NET2_OPEN_CODE;
        o.mission = given->mission < 0 || given->mission > 13 ? 0 : given->mission;
        o.kill_limit = given->kill_limit < 0 || given->kill_limit > 99 ? 0 : given->kill_limit;
    }
    return o;
}

int net2_host(net2* n, const net2_options* options) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    if (n->body->s.room.state != NET2_ROOM_NONE) return n->body->s.error(NET2_ERR_STATE, "Leave the room you are in first.");
    return n->body->host(clean_options(options));
}
int net2_join(net2* n, const char* code) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    std::string normal = code_normal(code, 5);
    if (normal.empty()) return n->body->s.error(NET2_ERR_ARGUMENT, "A room code is five letters and digits, like H4KQ7.");
    if (n->body->s.room.state != NET2_ROOM_NONE) return n->body->s.error(NET2_ERR_STATE, "Leave the room you are in first.");
    return n->body->join(normal);
}
int net2_join_friend(net2* n, const char* friend_id) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    if (!id_ok(friend_id)) return n->body->s.error(NET2_ERR_ARGUMENT, "That is not a player.");
    if (n->body->s.room.state != NET2_ROOM_NONE) return n->body->s.error(NET2_ERR_STATE, "Leave the room you are in first.");
    return n->body->join_friend(friend_id);
}
int net2_chat(net2* n, const char* text) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    std::string line = clean_text(text, 120);
    if (line.empty()) return NET2_ERR_ARGUMENT;
    if (n->body->s.room.state == NET2_ROOM_NONE || n->body->s.room.state == NET2_ROOM_JOINING)
        return n->body->s.error(NET2_ERR_STATE, "You are not in a room.");
    return n->body->chat(line);
}
static int in_open_room(net2* n, bool host) {
    const net2_room_t& room = n->body->s.room;
    if (room.state != NET2_ROOM_OPEN) return n->body->s.error(NET2_ERR_STATE, "You are not in a room that is open.");
    if (host && room.my_slot != room.host_slot) return n->body->s.error(NET2_ERR_STATE, "Only the host can do that.");
    return NET2_OK;
}
int net2_ready(net2* n, int ready) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    int r = in_open_room(n, false);
    return r ? r : n->body->ready(ready != 0);
}
int net2_set_options(net2* n, const net2_options* options) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    int r = in_open_room(n, true);
    return r ? r : n->body->set_options(clean_options(options));
}
int net2_kick(net2* n, int slot) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    int r = in_open_room(n, true);
    if (r) return r;
    if (slot < 0 || slot >= NET2_PLAYERS || slot == n->body->s.room.my_slot) return NET2_ERR_ARGUMENT;
    return n->body->kick(slot);
}
int net2_start(net2* n) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    int r = in_open_room(n, true);
    if (r) return r;
    if (n->body->s.room.count < 2) return n->body->s.error(NET2_ERR_STATE, "A game needs at least two players.");
    // the souls-style combat mode is all or nothing (room_checks): a room whose copies differ in it is not started
    const net2_room_t& room = n->body->s.room;
    for (int i = 1; i < room.count; i++)
        if ((room.members[i].fix_words & 0x8000) != (room.members[0].fix_words & 0x8000))
            return n->body->s.error(NET2_ERR_REFUSED, "Not every copy in the room plays with Hardcore mode.");
    for (int i = 1; i < room.count; i++)
        if ((room.members[i].fix_words & 0x4000) != (room.members[0].fix_words & 0x4000))
            return n->body->s.error(NET2_ERR_REFUSED, "Not every copy in the room aims by looking.");
    // hold to skip a cut scene (tools/recomp/app/cinematic.h; bit 0x2000 is Remastered's): the same
    for (int i = 1; i < room.count; i++)
        if ((room.members[i].fix_words & 0x2000) != (room.members[0].fix_words & 0x2000))
            return n->body->s.error(NET2_ERR_REFUSED, "Not every copy in the room plays Remastered (hold to skip a cut scene).");
    return n->body->start();
}
int net2_leave(net2* n) { LOCKED; return n ? n->body->leave() : NET2_ERR_ARGUMENT; }

void net2_session(net2* n, net2_session_t* out) { LOCKED; if (n && out) *out = n->body->s.session; }
int net2_game_state(net2* n, const char* level) {
    LOCKED;
    if (!n) return NET2_ERR_ARGUMENT;
    return n->body->game_state(clean_label(level, 20), level != nullptr);
}

int net2_debug(net2* n, const char* what, char* out, int size) {
    LOCKED;
    if (!n || !out || size <= 0) return NET2_ERR_ARGUMENT;
    std::string text;
    int r = n->body->debug(what ? what : "", text);
    put(out, (size_t)size, text);
    return r;
}
int net2_set(net2* n, const char* key, const char* value) {
    LOCKED;
    if (!n || !key) return NET2_ERR_ARGUMENT;
    return n->body->set(key, value ? value : "");
}

const char* net2_error_text(int code) {
    LOCKED;
    switch (code) {
    case NET2_OK: return "ok";
    case NET2_ERR_OFFLINE: return "no link to the service";
    case NET2_ERR_ARGUMENT: return "that cannot be right (empty, too long, not a code)";
    case NET2_ERR_STATE: return "not now (not in a room, not the host, already in a room)";
    case NET2_ERR_LIMIT: return "too many or too fast";
    case NET2_ERR_NOT_FOUND: return "not found";
    case NET2_ERR_FULL: return "the room is full";
    case NET2_ERR_REFUSED: return "refused";
    case NET2_ERR_SERVICE: return "the service refused";
    }
    return "unknown";
}

}  // extern "C"
