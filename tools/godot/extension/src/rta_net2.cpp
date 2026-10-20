// rta_net2.cpp - see rta_net2.h.  Records of session.h out as Dictionaries, calls in.
#include "rta_net2.h"
#include "rta_library.h"
#include <godot_cpp/classes/resource.hpp>
#include <godot_cpp/classes/resource_loader.hpp>
#include "rta_net2_api.h"

#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/project_settings.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/char_string.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include <cstring>
#include <vector>

// ---- where the functions come from (rta_net2_api.h) ----------------------------------------------
static RtaNet2Api& rta_net2_api() {
    static RtaNet2Api api;
    return api;
}

// The game library: the one RtaMachine loaded, else the one `path` names, else where main.gd looks for it (beside
// the extension in the project's bin/, or in the exported application's own folders).
static bool rta_net2_resolve(const godot::String& path) {
    RtaNet2Api& api = rta_net2_api();
    if (api.ready) return true;
#ifdef RTA_GODOT_NET2_LIBRARY
    using namespace godot;
    RtaLibrary& lib = rta_library();
    if (!lib.loaded) {
        String os_name = OS::get_singleton()->get_name();
        String file = String("librta_game") + (os_name == "Windows" ? ".dll" : (os_name == "macOS" ? ".dylib" : ".so"));
        String exe = OS::get_singleton()->get_executable_path().get_base_dir();
        PackedStringArray candidates;
        if (path.length() > 0) candidates.push_back(path);
        // where the project's own search finds it (res://gamelib.gd: the one chosen once, the installer's per-user place)
        Ref<Resource> finder = ResourceLoader::get_singleton()->load("res://gamelib.gd");
        if (finder.is_valid()) {
            String found = finder->call("find", path);
            if (found.length() > 0) candidates.push_back(found);
        }
        candidates.push_back(ProjectSettings::get_singleton()->globalize_path("res://bin/" + file));
        candidates.push_back(exe.path_join(file));
        candidates.push_back(exe.path_join("../Frameworks/" + file));
        candidates.push_back(exe.path_join("../Resources/" + file));
        for (int64_t k = 0; k < candidates.size() && !lib.loaded; k++)
            if (FileAccess::file_exists(candidates[k])) lib.load(std::string(candidates[k].utf8().get_data()));
        if (!lib.loaded) { api.error = "no game library (" + lib.error + ")"; return false; }
    }
#define RTA_NET2_TAKE(name) api.name = (decltype(api.name))lib.symbol(#name);
    RTA_NET2_FUNCTIONS(RTA_NET2_TAKE)
    RTA_NET2_GAME_FUNCTIONS(RTA_NET2_TAKE)
#undef RTA_NET2_TAKE
#define RTA_NET2_CHECK(name) if (!api.name) { api.error = "the game library " + lib.path + " has no " #name " (built without net2)"; return false; }
    RTA_NET2_FUNCTIONS(RTA_NET2_CHECK)
#undef RTA_NET2_CHECK
    api.from_library = true;
#else
    (void)path;
#define RTA_NET2_TAKE(name) api.name = &::name;
    RTA_NET2_FUNCTIONS(RTA_NET2_TAKE)
#undef RTA_NET2_TAKE
#endif
    api.ready = true;
    return true;
}

// every call below goes through the table
#define net2_open (rta_net2_api().net2_open)
#define net2_close (rta_net2_api().net2_close)
#define net2_poll (rta_net2_api().net2_poll)
#define net2_next_event (rta_net2_api().net2_next_event)
#define net2_me (rta_net2_api().net2_me)
#define net2_set_name (rta_net2_api().net2_set_name)
#define net2_set_character (rta_net2_api().net2_set_character)
#define net2_set_game (rta_net2_api().net2_set_game)
#define net2_local_characters (rta_net2_api().net2_local_characters)
#define net2_delete_everything (rta_net2_api().net2_delete_everything)
#define net2_friends (rta_net2_api().net2_friends)
#define net2_recent (rta_net2_api().net2_recent)
#define net2_blocked (rta_net2_api().net2_blocked)
#define net2_requests (rta_net2_api().net2_requests)
#define net2_friend_add (rta_net2_api().net2_friend_add)
#define net2_friend_add_id (rta_net2_api().net2_friend_add_id)
#define net2_friend_accept (rta_net2_api().net2_friend_accept)
#define net2_friend_decline (rta_net2_api().net2_friend_decline)
#define net2_friend_remove (rta_net2_api().net2_friend_remove)
#define net2_block (rta_net2_api().net2_block)
#define net2_unblock (rta_net2_api().net2_unblock)
#define net2_invites (rta_net2_api().net2_invites)
#define net2_invite (rta_net2_api().net2_invite)
#define net2_invite_accept (rta_net2_api().net2_invite_accept)
#define net2_invite_dismiss (rta_net2_api().net2_invite_dismiss)
#define net2_room (rta_net2_api().net2_room)
#define net2_host (rta_net2_api().net2_host)
#define net2_join (rta_net2_api().net2_join)
#define net2_join_friend (rta_net2_api().net2_join_friend)
#define net2_chat (rta_net2_api().net2_chat)
#define net2_ready (rta_net2_api().net2_ready)
#define net2_set_options (rta_net2_api().net2_set_options)
#define net2_kick (rta_net2_api().net2_kick)
#define net2_start (rta_net2_api().net2_start)
#define net2_leave (rta_net2_api().net2_leave)
#define net2_session (rta_net2_api().net2_session)
#define net2_game_state (rta_net2_api().net2_game_state)
#define net2_debug (rta_net2_api().net2_debug)
#define net2_set (rta_net2_api().net2_set)
#define net2_error_text (rta_net2_api().net2_error_text)
#define net2_game_attach (rta_net2_api().net2_game_attach)
#define net2_game_status (rta_net2_api().net2_game_status)
#define net2_game_choose (rta_net2_api().net2_game_choose)
#define net2_game_launch (rta_net2_api().net2_game_launch)
#define net2_game_stop (rta_net2_api().net2_game_stop)

namespace godot {

namespace {

String text(const char* s) { return String::utf8(s); }

template <size_t N> void put(char (&to)[N], const String& from) {
    CharString utf8 = from.utf8();
    size_t n = (size_t)utf8.length();
    if (n > N - 1) n = N - 1;
    memcpy(to, utf8.get_data(), n);
    to[n] = 0;
}

Dictionary character_out(const net2_character& c) {
    Dictionary d;
    d["name"] = text(c.name);
    d["cls"] = text(c.cls);
    d["level"] = c.level;
    return d;
}

net2_character character_in(const Dictionary& d) {
    net2_character c{};
    put(c.name, String(d.get("name", "")));
    put(c.cls, String(d.get("cls", "")));
    c.level = (int32_t)(int64_t)d.get("level", 0);
    return c;
}

Dictionary options_out(const net2_options& o) {
    Dictionary d;
    d["level"] = text(o.level);
    d["difficulty"] = o.difficulty;
    d["mode"] = o.mode;
    d["open_to"] = o.open_to;
    d["mission"] = o.mission;
    d["kill_limit"] = o.kill_limit;
    return d;
}

net2_options options_in(const Dictionary& d) {
    net2_options o{};
    put(o.level, String(d.get("level", "")));
    o.difficulty = (int)(int64_t)d.get("difficulty", 0);
    o.mode = (int)(int64_t)d.get("mode", 0);
    o.open_to = (int)(int64_t)d.get("open_to", 0);
    o.mission = (int)(int64_t)d.get("mission", 0);
    o.kill_limit = (int)(int64_t)d.get("kill_limit", 0);
    return o;
}

Dictionary friend_out(const net2_friend& f) {
    Dictionary d;
    d["id"] = text(f.id);
    d["name"] = text(f.name);
    d["friend_code"] = text(f.friend_code);
    d["presence"] = f.presence;
    d["room"] = text(f.room);
    d["joinable"] = f.joinable != 0;
    d["room_players"] = f.room_players;
    d["level"] = text(f.level);
    d["since"] = (int64_t)f.since;
    d["last_seen"] = (int64_t)f.last_seen;
    d["character"] = character_out(f.character);
    d["invited_me"] = f.invited_me != 0;
    d["is_friend"] = f.is_friend != 0;
    d["request_sent"] = f.request_sent != 0;
    return d;
}

typedef int (*friend_list)(net2*, net2_friend*, int);

Array friends_of(net2* n, friend_list call) {
    Array a;
    if (!n) return a;
    int count = call(n, nullptr, 0);        // out == NULL: how many there are
    if (count <= 0) count = 256;
    std::vector<net2_friend> list((size_t)count);
    int got = call(n, list.data(), count);
    for (int k = 0; k < got && k < count; k++) a.push_back(friend_out(list[(size_t)k]));
    return a;
}

}  // namespace

RtaNet2::RtaNet2() {}

RtaNet2::~RtaNet2() { close(); }

bool RtaNet2::has_service() {
#ifdef RTA_GODOT_NET2_LIBRARY
    return rta_net2_resolve(String());     // the game library's net2 talks to the real service
#else
    return false;                           // the extension's own copy: NET2_NO_SERVICE, the mock only
#endif
}

bool RtaNet2::from_library() { return rta_net2_resolve(String()) && rta_net2_api().from_library; }

String RtaNet2::get_error() { return String::utf8(rta_net2_api().error.c_str()); }

bool RtaNet2::open(const Dictionary& config) {
    close();
    if (!rta_net2_resolve(String(config.get("library", "")))) {
        UtilityFunctions::push_warning("RtaNet2: " + get_error());
        return false;
    }
    CharString data_dir = String(config.get("data_dir", "")).utf8();
    CharString service = String(config.get("service", "")).utf8();
    CharString name = String(config.get("name", "")).utf8();
    CharString build = String(config.get("build", "")).utf8();
    net2_config c;
    memset(&c, 0, sizeof c);
    c.struct_size = sizeof c;
    c.data_dir = data_dir.length() > 0 ? data_dir.get_data() : nullptr;
    c.mock = bool(config.get("mock", false)) ? 1 : 0;
    c.service = (!c.mock && has_service() && service.length() > 0) ? service.get_data() : nullptr;
    c.name = name.length() > 0 ? name.get_data() : nullptr;
    c.fix_set = (uint32_t)(int64_t)config.get("fix_set", 0);
    c.fix_words = (uint16_t)(int64_t)config.get("fix_words", 0);
    c.arith_can = (uint8_t)(int64_t)config.get("arith_can", 0);
    c.arith_does = (uint8_t)(int64_t)config.get("arith_does", 0);
    c.build = build.length() > 0 ? build.get_data() : nullptr;
    c.local_only = bool(config.get("local_only", false)) ? 1 : 0;
    handle = net2_open(&c);
    return handle != nullptr;
}

void RtaNet2::close() {
    if (handle) net2_close(handle);
    handle = nullptr;
}

Array RtaNet2::poll() {
    Array events;
    if (!handle) return events;
    net2_poll(handle);
    net2_event e;
    while (net2_next_event(handle, &e)) {
        Dictionary d;
        d["type"] = e.type;
        d["code"] = e.code;
        d["who"] = text(e.who);
        d["who_id"] = text(e.who_id);
        d["room"] = text(e.room);
        d["text"] = text(e.text);
        events.push_back(d);
    }
    return events;
}

Dictionary RtaNet2::me() const {
    Dictionary d;
    if (!handle) return d;
    net2_me_t m;
    memset(&m, 0, sizeof m);
    net2_me(handle, &m);
    d["link"] = m.link;
    d["mock"] = m.mock != 0;
    d["id"] = text(m.id);
    d["name"] = text(m.name);
    d["friend_code"] = text(m.friend_code);
    d["service"] = text(m.service);
    d["problem"] = text(m.problem);
    d["character"] = character_out(m.character);
    d["new_identity"] = m.new_identity != 0;
    return d;
}

int RtaNet2::set_name(const String& name) { return handle ? net2_set_name(handle, name.utf8().get_data()) : NET2_ERR_ARGUMENT; }

int RtaNet2::set_character(const Dictionary& character) {
    if (!handle) return NET2_ERR_ARGUMENT;
    if (String(character.get("name", "")).is_empty()) return net2_set_character(handle, nullptr);
    net2_character c = character_in(character);
    return net2_set_character(handle, &c);
}

int RtaNet2::set_game(const String& level) {
    if (!handle) return NET2_ERR_ARGUMENT;
    return net2_set_game(handle, level.is_empty() ? nullptr : level.utf8().get_data());
}

Array RtaNet2::local_characters(const String& card_dir) const {
    Array a;
    if (!handle) return a;
    net2_character list[32];
    memset(list, 0, sizeof list);
    int got = net2_local_characters(handle, card_dir.utf8().get_data(), list, 32);
    for (int k = 0; k < got && k < 32; k++) a.push_back(character_out(list[k]));
    return a;
}

int RtaNet2::delete_everything() { return handle ? net2_delete_everything(handle) : NET2_ERR_ARGUMENT; }

Array RtaNet2::friends() const { return friends_of(handle, net2_friends); }
Array RtaNet2::recent() const { return friends_of(handle, net2_recent); }
Array RtaNet2::blocked() const { return friends_of(handle, net2_blocked); }

Array RtaNet2::requests() const {
    Array a;
    if (!handle) return a;
    std::vector<net2_request> list(128);
    int got = net2_requests(handle, list.data(), (int)list.size());
    for (int k = 0; k < got && k < (int)list.size(); k++) {
        const net2_request& r = list[(size_t)k];
        Dictionary d;
        d["id"] = text(r.id);
        d["name"] = text(r.name);
        d["friend_code"] = text(r.friend_code);
        d["incoming"] = r.incoming != 0;
        d["when"] = (int64_t)r.when;
        a.push_back(d);
    }
    return a;
}

int RtaNet2::friend_add(const String& friend_code) { return handle ? net2_friend_add(handle, friend_code.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::friend_add_id(const String& id) { return handle ? net2_friend_add_id(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::friend_accept(const String& id) { return handle ? net2_friend_accept(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::friend_decline(const String& id) { return handle ? net2_friend_decline(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::friend_remove(const String& id) { return handle ? net2_friend_remove(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::block(const String& id) { return handle ? net2_block(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::unblock(const String& id) { return handle ? net2_unblock(handle, id.utf8().get_data()) : NET2_ERR_ARGUMENT; }

Array RtaNet2::invites() const {
    Array a;
    if (!handle) return a;
    std::vector<net2_invite_t> list(64);
    int got = net2_invites(handle, list.data(), (int)list.size());
    for (int k = 0; k < got && k < (int)list.size(); k++) {
        const net2_invite_t& v = list[(size_t)k];
        Dictionary d;
        d["from_id"] = text(v.from_id);
        d["from_name"] = text(v.from_name);
        d["room"] = text(v.room);
        d["room_players"] = v.room_players;
        d["character"] = character_out(v.character);
        d["when"] = (int64_t)v.when;
        a.push_back(d);
    }
    return a;
}

int RtaNet2::invite(const String& friend_id) { return handle ? net2_invite(handle, friend_id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::invite_accept(const String& from_id) { return handle ? net2_invite_accept(handle, from_id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::invite_dismiss(const String& from_id) { return handle ? net2_invite_dismiss(handle, from_id.utf8().get_data()) : NET2_ERR_ARGUMENT; }

Dictionary RtaNet2::room() const {
    Dictionary d;
    if (!handle) {
        d["state"] = (int)NET2_ROOM_NONE;
        return d;
    }
    // the record is large (32 chat lines): not on the stack of a script call
    std::vector<net2_room_t> one(1);
    net2_room_t& r = one[0];
    memset(&r, 0, sizeof r);
    net2_room(handle, &r);
    d["state"] = r.state;
    d["code"] = text(r.code);
    d["count"] = r.count;
    d["my_slot"] = r.my_slot;
    d["host_slot"] = r.host_slot;
    Array members;
    for (int k = 0; k < r.count && k < NET2_PLAYERS; k++) {
        const net2_member& m = r.members[k];
        Dictionary e;
        e["slot"] = m.slot;
        e["id"] = text(m.id);
        e["name"] = text(m.name);
        e["character"] = character_out(m.character);
        e["ready"] = m.ready != 0;
        e["host"] = m.host != 0;
        e["me"] = m.me != 0;
        e["is_friend"] = m.is_friend != 0;
        e["fix_set"] = (int64_t)m.fix_set;
        e["fix_words"] = (int)m.fix_words;
        e["arith_can"] = (int)m.arith_can;
        e["arith_does"] = (int)m.arith_does;
        e["route"] = m.route;
        e["rtt_ms"] = m.rtt_ms;
        e["phase"] = m.phase;
        members.push_back(e);
    }
    d["members"] = members;
    d["options"] = options_out(r.options);
    d["all_ready"] = r.all_ready != 0;
    d["mismatch"] = r.mismatch != 0;
    d["warning"] = text(r.warning);
    Array chat;
    for (int k = 0; k < r.chat_count && k < NET2_CHAT_LINES; k++) {
        Dictionary e;
        e["number"] = (int64_t)r.chat[k].number;
        e["from"] = text(r.chat[k].from);
        e["text"] = text(r.chat[k].text);
        chat.push_back(e);
    }
    d["chat"] = chat;
    return d;
}

int RtaNet2::host(const Dictionary& options) {
    if (!handle) return NET2_ERR_ARGUMENT;
    net2_options o = options_in(options);
    return net2_host(handle, &o);
}

int RtaNet2::join(const String& code) { return handle ? net2_join(handle, code.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::join_friend(const String& friend_id) { return handle ? net2_join_friend(handle, friend_id.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::chat(const String& line) { return handle ? net2_chat(handle, line.utf8().get_data()) : NET2_ERR_ARGUMENT; }
int RtaNet2::ready(bool is_ready) { return handle ? net2_ready(handle, is_ready ? 1 : 0) : NET2_ERR_ARGUMENT; }

int RtaNet2::set_options(const Dictionary& options) {
    if (!handle) return NET2_ERR_ARGUMENT;
    net2_options o = options_in(options);
    return net2_set_options(handle, &o);
}

int RtaNet2::kick(int slot) { return handle ? net2_kick(handle, slot) : NET2_ERR_ARGUMENT; }
int RtaNet2::start() { return handle ? net2_start(handle) : NET2_ERR_ARGUMENT; }
int RtaNet2::leave() { return handle ? net2_leave(handle) : NET2_ERR_ARGUMENT; }

Dictionary RtaNet2::session() const {
    Dictionary d;
    d["valid"] = false;
    if (!handle) return d;
    net2_session_t s;
    memset(&s, 0, sizeof s);
    net2_session(handle, &s);
    d["valid"] = s.valid != 0;
    d["session"] = (int64_t)s.session;
    d["count"] = s.count;
    d["my_slot"] = s.my_slot;
    d["host_slot"] = s.host_slot;
    Array players;
    for (int k = 0; k < s.count && k < NET2_PLAYERS; k++) {
        Dictionary e;
        e["id"] = text(s.players[k].id);
        e["name"] = text(s.players[k].name);
        e["character"] = character_out(s.players[k].character);
        players.push_back(e);
    }
    d["players"] = players;
    d["options"] = options_out(s.options);
    d["seed"] = (int64_t)s.seed;
    return d;
}

int RtaNet2::game_state(const String& level, bool running) {
    if (!handle) return NET2_ERR_ARGUMENT;
    return net2_game_state(handle, running ? level.utf8().get_data() : nullptr);
}

String RtaNet2::debug(const String& what) const {
    if (!handle) return String();
    char out[512];
    out[0] = 0;
    net2_debug(handle, what.utf8().get_data(), out, (int)sizeof out);
    return text(out);
}

int RtaNet2::set_value(const String& key, const String& value) {
    return handle ? net2_set(handle, key.utf8().get_data(), value.utf8().get_data()) : NET2_ERR_ARGUMENT;
}

String RtaNet2::error_text(int code) const { return rta_net2_api().ready ? text(net2_error_text(code)) : String(); }

// ---- the game's side (game.h; only the game library has it) ----
bool RtaNet2::has_game() { return rta_net2_resolve(String()) && net2_game_attach != nullptr; }

bool RtaNet2::game_attach() {
    if (!handle || !net2_game_attach) return false;
    net2_game_attach(handle);
    return true;
}

Dictionary RtaNet2::game_status() const {
    Dictionary d;
    if (!net2_game_status) return d;
    net2_game_status_t s;
    memset(&s, 0, sizeof s);
    net2_game_status(&s);
    d["phase"] = s.phase;
    d["launches"] = s.launches;
    d["failed"] = s.failed != 0;
    d["text"] = text(s.text);
    d["character"] = character_out(s.character);
    d["level"] = text(s.level);
    d["tick"] = (int64_t)s.tick;
    d["players"] = s.players;
    d["difficulty_unlocked"] = s.difficulty_unlocked;
    return d;
}

int RtaNet2::game_choose(bool as_host) { return net2_game_choose ? net2_game_choose(as_host ? 1 : 0) : NET2_ERR_ARGUMENT; }
int RtaNet2::game_launch() { return handle && net2_game_launch ? net2_game_launch(handle) : NET2_ERR_ARGUMENT; }
int RtaNet2::game_stop() { return net2_game_stop ? net2_game_stop() : NET2_ERR_ARGUMENT; }

void RtaNet2::_bind_methods() {
    ClassDB::bind_static_method("RtaNet2", D_METHOD("has_service"), &RtaNet2::has_service);
    ClassDB::bind_static_method("RtaNet2", D_METHOD("api_version"), &RtaNet2::api_version);
    ClassDB::bind_static_method("RtaNet2", D_METHOD("from_library"), &RtaNet2::from_library);
    ClassDB::bind_static_method("RtaNet2", D_METHOD("has_game"), &RtaNet2::has_game);
    ClassDB::bind_static_method("RtaNet2", D_METHOD("get_error"), &RtaNet2::get_error);
    ClassDB::bind_method(D_METHOD("game_attach"), &RtaNet2::game_attach);
    ClassDB::bind_method(D_METHOD("game_status"), &RtaNet2::game_status);
    ClassDB::bind_method(D_METHOD("game_choose", "as_host"), &RtaNet2::game_choose);
    ClassDB::bind_method(D_METHOD("game_launch"), &RtaNet2::game_launch);
    ClassDB::bind_method(D_METHOD("game_stop"), &RtaNet2::game_stop);
    ClassDB::bind_method(D_METHOD("open", "config"), &RtaNet2::open);
    ClassDB::bind_method(D_METHOD("close"), &RtaNet2::close);
    ClassDB::bind_method(D_METHOD("is_open"), &RtaNet2::is_open);
    ClassDB::bind_method(D_METHOD("poll"), &RtaNet2::poll);
    ClassDB::bind_method(D_METHOD("me"), &RtaNet2::me);
    ClassDB::bind_method(D_METHOD("set_name", "name"), &RtaNet2::set_name);
    ClassDB::bind_method(D_METHOD("set_character", "character"), &RtaNet2::set_character);
    ClassDB::bind_method(D_METHOD("set_game", "level"), &RtaNet2::set_game);
    ClassDB::bind_method(D_METHOD("local_characters", "card_dir"), &RtaNet2::local_characters);
    ClassDB::bind_method(D_METHOD("delete_everything"), &RtaNet2::delete_everything);
    ClassDB::bind_method(D_METHOD("friends"), &RtaNet2::friends);
    ClassDB::bind_method(D_METHOD("recent"), &RtaNet2::recent);
    ClassDB::bind_method(D_METHOD("blocked"), &RtaNet2::blocked);
    ClassDB::bind_method(D_METHOD("requests"), &RtaNet2::requests);
    ClassDB::bind_method(D_METHOD("friend_add", "friend_code"), &RtaNet2::friend_add);
    ClassDB::bind_method(D_METHOD("friend_add_id", "id"), &RtaNet2::friend_add_id);
    ClassDB::bind_method(D_METHOD("friend_accept", "id"), &RtaNet2::friend_accept);
    ClassDB::bind_method(D_METHOD("friend_decline", "id"), &RtaNet2::friend_decline);
    ClassDB::bind_method(D_METHOD("friend_remove", "id"), &RtaNet2::friend_remove);
    ClassDB::bind_method(D_METHOD("block", "id"), &RtaNet2::block);
    ClassDB::bind_method(D_METHOD("unblock", "id"), &RtaNet2::unblock);
    ClassDB::bind_method(D_METHOD("invites"), &RtaNet2::invites);
    ClassDB::bind_method(D_METHOD("invite", "friend_id"), &RtaNet2::invite);
    ClassDB::bind_method(D_METHOD("invite_accept", "from_id"), &RtaNet2::invite_accept);
    ClassDB::bind_method(D_METHOD("invite_dismiss", "from_id"), &RtaNet2::invite_dismiss);
    ClassDB::bind_method(D_METHOD("room"), &RtaNet2::room);
    ClassDB::bind_method(D_METHOD("host", "options"), &RtaNet2::host);
    ClassDB::bind_method(D_METHOD("join", "code"), &RtaNet2::join);
    ClassDB::bind_method(D_METHOD("join_friend", "friend_id"), &RtaNet2::join_friend);
    ClassDB::bind_method(D_METHOD("chat", "text"), &RtaNet2::chat);
    ClassDB::bind_method(D_METHOD("ready", "ready"), &RtaNet2::ready);
    ClassDB::bind_method(D_METHOD("set_options", "options"), &RtaNet2::set_options);
    ClassDB::bind_method(D_METHOD("kick", "slot"), &RtaNet2::kick);
    ClassDB::bind_method(D_METHOD("start"), &RtaNet2::start);
    ClassDB::bind_method(D_METHOD("leave"), &RtaNet2::leave);
    ClassDB::bind_method(D_METHOD("session"), &RtaNet2::session);
    ClassDB::bind_method(D_METHOD("game_state", "level", "running"), &RtaNet2::game_state);
    ClassDB::bind_method(D_METHOD("debug", "what"), &RtaNet2::debug);
    ClassDB::bind_method(D_METHOD("set_value", "key", "value"), &RtaNet2::set_value);
    ClassDB::bind_method(D_METHOD("error_text", "code"), &RtaNet2::error_text);
}

}  // namespace godot
