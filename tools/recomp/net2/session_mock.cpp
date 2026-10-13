// session_mock.cpp - the mock behind session.h: everything a portal's screens can show,
// made up locally.  No socket, no file, no service.
//
// What it plays (times in seconds after net2_open, at "mock-speed=1"):
//   0.6   the link comes up; me = the configured name, friend code MOCK-xxxx
//         six friends: two in a game, one in a joinable room, one in a closed room, one
//         online, one offline (seen two days ago); one friend request waiting; three recent
//         players; one blocked player
//   every 7 s  one friend's presence moves on (offline > online > in a room > in a game ...)
//   12    an invitation from the friend in the joinable room (again 45 s after it is answered)
//   25    a second friend request comes in
//   net2_friend_add(code)   an outgoing request; "accepted" 5 s later (codes starting with N: never)
//   net2_host               the room is open 0.4 s later, code MOCK7; a friend walks in at 3 s,
//                           says hello, is ready at 6 s; a second one at 9 s, ready at 13 s
//   net2_join(code)         a room with a host and one other; when I am ready the host starts
//                           3 s later.  Code FULL2: "the room is full"; NQPE2: "no such room";
//                           LATE2: "the game has started"; BADF2: a member with another fix set
//                           (the mismatch warning)
//   net2_start / the host's start: NET2_EV_START, routes come up 1.5 s later (one direct, one
//                           by relay), and unless the program says otherwise with
//                           net2_game_state() the game "runs" from 3 s on and is over after 40 s
//   net2_chat               my line; a member answers some of them
//   net2_set(n, "mock-speed", "4")   everything four times as fast
#include "session_impl.h"

#include <algorithm>
#include <functional>

namespace net2impl {
namespace {

const char* CLASSES[7] = {"Barbarian", "Wood Elf Ranger", "High Elf Cleric", "Erudite Wizard",
                          "Dark Elf Shadowknight", "Vah Shir Berserker", "Iksar Shaman"};
const char* LEVELS[5] = {"hub", "drunare", "blood1", "kelethin", "strife"};

struct Fake {
    const char* id;
    const char* name;
    const char* code;
    const char* character;
    int cls, level;
};
const Fake FAKES[] = {
    {"6d6f636b000000000000000000000001", "Brannoc", "BRAN-N2C7", "Brannoc Ironhide", 0, 34},
    {"6d6f636b000000000000000000000002", "sylvie_r", "SYLV-9RQ4", "Sylvara", 1, 21},
    {"6d6f636b000000000000000000000003", "Old Mate Dez", "DEZZ-4KTM", "Dezmond the Pious", 2, 47},
    {"6d6f636b000000000000000000000004", "quietwizard", "QWZD-77HX", "Maelis", 3, 12},
    {"6d6f636b000000000000000000000005", "Kat", "KATT-3PPL", "Nyxara", 4, 50},
    {"6d6f636b000000000000000000000006", "Ruk", "RUKK-8WVE", "Rukh the Loud", 5, 8},
    {"6d6f636b000000000000000000000007", "Thorgrim", "THRG-5MAB", "Thorgrim", 0, 29},
    {"6d6f636b000000000000000000000008", "ssleth", "SLTH-6YUN", "Ssleth", 6, 40},
    {"6d6f636b000000000000000000000009", "Wren", "WREN-2DGS", "Wrenna", 1, 17},
    {"6d6f636b00000000000000000000000a", "nomanners", "NMNR-9ZZK", "Gorehowl", 5, 3},
};

struct Timer { int64_t at; std::function<void()> run; };

struct Mock : Backend {
    int64_t start_ms = steady_ms();
    double speed = 1.0;
    double clock = 0;           // mock seconds
    int64_t last_ms = start_ms;
    std::vector<Timer> timers;
    uint32_t fix_set = 0;
    uint16_t fix_words = 0;
    uint8_t arith_can = 0, arith_does = 0;
    int cycle = 0;
    bool program_drives_game = false;
    uint32_t starts = 0;

    explicit Mock(const net2_config& config) {
        s.me.mock = 1;
        s.me.link = NET2_LINK_CONNECTING;
        put(s.me.name, config.name && *config.name && name_problem(config.name).empty() ? config.name : "Player");
        put(s.me.service, "the mock (nothing leaves this program)");
        put(s.me.problem, "Connecting...");
        s.me.new_identity = 1;
        fix_set = config.fix_set;
        fix_words = config.fix_words;
        arith_can = config.arith_can;
        arith_does = config.arith_does;
        after(0.6, [this] { come_up(); });
    }

    void after(double seconds, std::function<void()> run) {
        timers.push_back(Timer{(int64_t)((clock + seconds) * 1000), std::move(run)});
    }

    static net2_character character_of(const Fake& f) {
        net2_character c{};
        put(c.name, f.character);
        put(c.cls, CLASSES[f.cls]);
        c.level = f.level;
        return c;
    }
    static net2_friend friend_of(const Fake& f, int presence) {
        net2_friend out{};
        put(out.id, f.id);
        put(out.name, f.name);
        put(out.friend_code, f.code);
        out.character = character_of(f);
        out.is_friend = 1;
        set_presence(out, presence, 0);
        return out;
    }
    static void set_presence(net2_friend& f, int presence, int variant) {
        f.presence = presence;
        f.room[0] = 0;
        f.level[0] = 0;
        f.joinable = 0;
        f.room_players = 0;
        f.since = unix_now() - 60 * (3 + variant * 7);
        if (presence == NET2_OFFLINE) {
            f.last_seen = unix_now() - 3600 * (2 + variant * 23);
            f.since = 0;
        } else if (presence == NET2_IN_ROOM) {
            f.joinable = variant % 2 == 0;
            f.room_players = 1 + variant % 3;
            if (f.joinable) put(f.room, variant % 4 == 0 ? "MQCK3" : "MQCK5");
        } else if (presence == NET2_IN_GAME) {
            put(f.level, LEVELS[variant % 5]);
            f.room_players = 2 + variant % 3;
        }
    }

    void come_up() {
        s.me.link = NET2_LINK_ONLINE;
        s.me.problem[0] = 0;
        put(s.me.id, "6d6f636b0000000000000000000000ff");
        unsigned h = 2166136261u;
        for (const char* p = s.me.name; *p; p++) h = (h ^ (unsigned char)*p) * 16777619u;
        std::string code = "MQCK";
        for (int i = 0; i < 4; i++, h >>= 5) code += CODE_ALPHABET[h & 31];
        put(s.me.friend_code, friend_code_shown(code));
        s.event(NET2_EV_LINK);
        s.event(NET2_EV_ME);
        const int presence[6] = {NET2_IN_GAME, NET2_IN_ROOM, NET2_ONLINE, NET2_IN_GAME, NET2_IN_ROOM, NET2_OFFLINE};
        for (int i = 0; i < 6; i++) {
            net2_friend f = friend_of(FAKES[i], presence[i]);
            set_presence(f, presence[i], i == 1 ? 0 : i);
            s.friends.push_back(f);
        }
        s.sort_friends();
        s.event(NET2_EV_FRIENDS);
        add_request(FAKES[6], true);
        for (int i = 7; i < 9; i++) {
            net2_friend f = friend_of(FAKES[i], NET2_OFFLINE);
            f.is_friend = 0;
            f.last_seen = unix_now() - 86400 * (i - 6);
            s.recent.push_back(f);
        }
        net2_friend also = friend_of(FAKES[0], NET2_IN_GAME);
        s.recent.push_back(also);
        s.event(NET2_EV_RECENT);
        net2_friend rude = friend_of(FAKES[9], NET2_OFFLINE);
        rude.is_friend = 0;
        s.blocked.push_back(rude);
        after(7, [this] { move_presence(); });
        after(11.4, [this] { send_invite(); });
        after(24.4, [this] { add_request(FAKES[8], true); });
    }

    void add_request(const Fake& f, bool incoming) {
        for (auto& r : s.requests)
            if (!strcmp(r.id, f.id)) return;
        for (auto& fr : s.friends)
            if (!strcmp(fr.id, f.id)) return;
        net2_request r{};
        put(r.id, f.id);
        put(r.name, f.name);
        put(r.friend_code, f.code);
        r.incoming = incoming;
        r.when = unix_now();
        s.requests.push_back(r);
        s.event(NET2_EV_REQUESTS, 0, incoming ? std::string(f.name) + " wants to be your friend." : "", f.name, f.id);
    }

    void move_presence() {
        after(7, [this] { move_presence(); });
        if (s.me.link != NET2_LINK_ONLINE || s.friends.empty()) return;
        net2_friend& f = s.friends[(size_t)(cycle * 5 + 2) % s.friends.size()];
        cycle++;
        for (int i = 0; i < s.room.count; i++)
            if (!strcmp(s.room.members[i].id, f.id)) return;         // in my room: leave them be
        set_presence(f, (f.presence + 1) % 4, cycle);
        if (f.presence != NET2_OFFLINE) f.since = unix_now();
        else f.last_seen = unix_now();
        s.sort_friends();
        s.event(NET2_EV_FRIENDS);
    }

    void send_invite() {
        if (s.me.link != NET2_LINK_ONLINE || !s.invites.empty() || s.room.state != NET2_ROOM_NONE) {
            after(20, [this] { send_invite(); });
            return;
        }
        for (auto& f : s.friends) {
            if (f.presence != NET2_IN_ROOM || !f.joinable) continue;
            net2_invite_t inv{};
            put(inv.from_id, f.id);
            put(inv.from_name, f.name);
            put(inv.room, f.room);
            inv.room_players = f.room_players;
            inv.character = f.character;
            inv.when = unix_now();
            s.invites.push_back(inv);
            f.invited_me = 1;
            s.event(NET2_EV_INVITE, 0, std::string(f.name) + " invites you to a game.", f.name, f.id, f.room);
            s.event(NET2_EV_FRIENDS);
            return;
        }
        after(20, [this] { send_invite(); });
    }

    // ---- the room ---------------------------------------------------------------------
    net2_member member_of(const Fake& f, int slot, bool host) {
        net2_member m{};
        m.slot = slot;
        put(m.id, f.id);
        put(m.name, f.name);
        m.character = character_of(f);
        m.host = host;
        m.ready = host;
        m.fix_set = fix_set;
        m.fix_words = fix_words;
        m.arith_can = arith_can ? arith_can : (uint8_t)(fix_set ? 3 : 0);
        m.arith_does = arith_does;
        m.rtt_ms = -1;
        for (auto& fr : s.friends)
            if (!strcmp(fr.id, f.id)) m.is_friend = 1;
        return m;
    }
    net2_member me_member(int slot, bool host) {
        net2_member m{};
        m.slot = slot;
        put(m.id, s.me.id);
        put(m.name, s.me.name);
        m.character = s.me.character;
        m.host = host;
        m.me = 1;
        m.fix_set = fix_set;
        m.fix_words = fix_words;
        m.arith_can = arith_can;
        m.arith_does = arith_does;
        m.route = NET2_ROUTE_SELF;
        m.rtt_ms = 0;
        return m;
    }
    void room_changed() {
        std::sort(s.room.members, s.room.members + s.room.count, [](const net2_member& a, const net2_member& b) { return a.slot < b.slot; });
        s.room.my_slot = s.room.host_slot = 0;
        for (int i = 0; i < s.room.count; i++) {
            if (s.room.members[i].me) s.room.my_slot = s.room.members[i].slot;
            if (s.room.members[i].host) s.room.host_slot = s.room.members[i].slot;
        }
        s.room_checks();
        s.event(NET2_EV_ROOM, 0, "", "", "", s.room.code);
    }
    net2_member* member(const char* id) {
        for (int i = 0; i < s.room.count; i++)
            if (!strcmp(s.room.members[i].id, id)) return &s.room.members[i];
        return nullptr;
    }
    int free_slot() {
        for (int slot = 0; slot < NET2_PLAYERS; slot++) {
            bool used = false;
            for (int i = 0; i < s.room.count; i++) used |= s.room.members[i].slot == slot;
            if (!used) return slot;
        }
        return -1;
    }
    void walk_in(const Fake& f, uint32_t room_serial) {
        if (s.room.state != NET2_ROOM_OPEN || serial != room_serial || s.room.count >= NET2_PLAYERS || member(f.id)) return;
        s.room.members[s.room.count++] = member_of(f, free_slot(), false);
        s.chat_line("", std::string(f.name) + " joined.");
        room_changed();
    }
    void mark_ready(const Fake& f, uint32_t room_serial) {
        if (s.room.state != NET2_ROOM_OPEN || serial != room_serial) return;
        if (net2_member* m = member(f.id)) {
            m->ready = 1;
            room_changed();
        }
    }
    void say(const Fake& f, const char* text, uint32_t room_serial) {
        if (s.room.state == NET2_ROOM_NONE || serial != room_serial || !member(f.id)) return;
        s.chat_line(f.name, text);
    }
    uint32_t serial = 0;        // counts the rooms: a timer of an old room does nothing in a new one

    void open_room(const std::string& code, bool i_host, const net2_options& options) {
        serial++;
        s.room = net2_room_t{};
        s.room.state = NET2_ROOM_OPEN;
        put(s.room.code, code);
        s.room.options = options;
        s.invites.clear();
        for (auto& f : s.friends) f.invited_me = 0;
        uint32_t now = serial;
        if (i_host) {
            s.room.members[s.room.count++] = me_member(0, true);
            s.chat_line("", "Room " + code + " is open. Tell your friends the code.");
            after(3, [this, now] { walk_in(FAKES[2], now); });
            after(4.2, [this, now] { say(FAKES[2], "evening! give me a second to pick a character", now); });
            after(6, [this, now] { mark_ready(FAKES[2], now); });
            after(9, [this, now] { walk_in(FAKES[4], now); });
            after(10, [this, now] { say(FAKES[4], "ready when you are", now); });
            after(13, [this, now] { mark_ready(FAKES[4], now); });
        } else {
            s.room.members[s.room.count++] = member_of(FAKES[1], 0, true);
            s.room.members[s.room.count++] = member_of(FAKES[3], 1, false);
            s.room.members[1].ready = 1;
            s.room.members[s.room.count++] = me_member(2, false);
            if (code == "BADF2") {
                s.room.members[1].fix_set ^= 0x5a5a1234;
                s.room.members[1].fix_words += 1;
                if (!s.room.members[1].arith_can) { s.room.members[1].arith_can = 1; s.room.members[2].arith_can = 1; }
            }
            s.chat_line("", std::string(s.me.name) + " joined.");
            after(1.5, [this, now] { say(FAKES[1], "hey! mark yourself ready and I'll start", now); });
        }
        room_changed();
    }

    void begin_start(uint32_t room_serial) {
        if (s.room.state != NET2_ROOM_OPEN || serial != room_serial) return;
        s.room.state = NET2_ROOM_STARTING;
        net2_session_t& g = s.session;
        g = net2_session_t{};
        g.valid = 1;
        g.session = 0x4d4f434b + ++starts;
        g.count = s.room.count;
        g.my_slot = s.room.my_slot;
        g.host_slot = s.room.host_slot;
        for (int i = 0; i < s.room.count; i++) {
            const net2_member& m = s.room.members[i];
            memcpy(g.players[i].id, m.id, sizeof m.id);
            memcpy(g.players[i].name, m.name, sizeof m.name);
            g.players[i].character = m.character;
            if (!m.me) s.room.members[i].route = NET2_ROUTE_TRYING;
        }
        g.options = s.room.options;
        s.chat_line("", "The game is starting.");
        room_changed();
        s.event(NET2_EV_START, 0, "", "", "", s.room.code);
        uint32_t now = serial, this_start = starts;
        after(1.5, [this, now] {
            if (serial != now || s.room.state != NET2_ROOM_STARTING) return;
            int k = 0;
            for (int i = 0; i < s.room.count; i++) {
                net2_member& m = s.room.members[i];
                if (m.me) continue;
                m.route = k++ == 1 ? NET2_ROUTE_RELAY : NET2_ROUTE_DIRECT;
                m.rtt_ms = m.route == NET2_ROUTE_RELAY ? 71 : 23;
            }
            room_changed();
        });
        after(3, [this, now, this_start] {
            if (serial != now || starts != this_start || program_drives_game || s.room.state != NET2_ROOM_STARTING) return;
            game_state(s.room.options.level[0] ? s.room.options.level : "hub", true);
            program_drives_game = false;
        });
        after(43, [this, now, this_start] {
            if (serial != now || starts != this_start || program_drives_game || s.room.state != NET2_ROOM_IN_GAME) return;
            game_state("", false);
            program_drives_game = false;
        });
    }

    // ---- Backend ------------------------------------------------------------------------
    void poll() override {
        int64_t now = steady_ms();
        clock += (double)(now - last_ms) / 1000.0 * speed;
        last_ms = now;
        // a timer may add timers: run by index, on a copy of what is due
        for (;;) {
            size_t due = timers.size();
            for (size_t i = 0; i < timers.size(); i++)
                if ((double)timers[i].at <= clock * 1000 && (due == timers.size() || timers[i].at < timers[due].at)) due = i;
            if (due == timers.size()) break;
            std::function<void()> run = std::move(timers[due].run);
            timers.erase(timers.begin() + (long)due);
            run();
        }
    }
    bool online() { return s.me.link == NET2_LINK_ONLINE; }
    int offline() { return s.error(NET2_ERR_OFFLINE, "There is no link to the service yet."); }

    int set_name(const std::string& name) override {
        put(s.me.name, name);
        if (net2_member* m = member(s.me.id)) { put(m->name, name); room_changed(); }
        s.event(NET2_EV_ME);
        return NET2_OK;
    }
    int set_character(const net2_character* c) override {
        s.me.character = c ? *c : net2_character{};
        if (net2_member* m = member(s.me.id)) { m->character = s.me.character; room_changed(); }
        s.event(NET2_EV_ME);
        return NET2_OK;
    }
    int set_game(const std::string&) override { return NET2_OK; }
    int delete_everything() override {
        if (!online()) return offline();
        after(0.4, [this] {
            s.friends.clear(); s.recent.clear(); s.blocked.clear(); s.requests.clear(); s.invites.clear();
            if (s.room.state != NET2_ROOM_NONE) { s.room = net2_room_t{}; serial++; s.event(NET2_EV_ROOM); }
            put(s.me.name, "Player");
            put(s.me.friend_code, "MQCK-NEW2");
            s.me.character = net2_character{};
            s.event(NET2_EV_DELETED, 0, "Everything the service held about you is deleted.");
            s.event(NET2_EV_ME); s.event(NET2_EV_FRIENDS); s.event(NET2_EV_REQUESTS); s.event(NET2_EV_RECENT); s.event(NET2_EV_INVITE);
        });
        return NET2_OK;
    }

    const Fake* fake_by_code(const std::string& normal) {
        for (const Fake& f : FAKES)
            if (code_normal(f.code, 8) == normal) return &f;
        return nullptr;
    }
    const Fake* fake_by_id(const std::string& id) {
        for (const Fake& f : FAKES)
            if (id == f.id) return &f;
        return nullptr;
    }
    void befriend(const Fake& f) {
        s.requests.erase(std::remove_if(s.requests.begin(), s.requests.end(), [&](const net2_request& r) { return !strcmp(r.id, f.id); }), s.requests.end());
        for (auto& fr : s.friends)
            if (!strcmp(fr.id, f.id)) return;
        s.friends.push_back(friend_of(f, NET2_ONLINE));
        for (auto& r : s.recent)
            if (!strcmp(r.id, f.id)) { r.is_friend = 1; r.request_sent = 0; }
        s.sort_friends();
        s.event(NET2_EV_REQUESTS);
        s.event(NET2_EV_FRIENDS);
        s.event(NET2_EV_RECENT);
    }
    int ask(const Fake* f, const std::string& normal) {
        if (!online()) return offline();
        after(0.5, [this, f, normal] {
            if (normal == code_normal(s.me.friend_code, 8)) { s.error(NET2_ERR_ARGUMENT, "That is your own friend code."); return; }
            if (!f) { s.error(NET2_ERR_NOT_FOUND, "Nobody has the friend code " + friend_code_shown(normal) + "."); return; }
            for (auto& fr : s.friends)
                if (!strcmp(fr.id, f->id)) { s.error(NET2_ERR_STATE, std::string(f->name) + " is your friend already."); return; }
            for (auto& r : s.requests)
                if (!strcmp(r.id, f->id) && r.incoming) { befriend(*f); s.event(NET2_EV_NOTICE, 0, std::string(f->name) + " had asked you already: you are friends now."); return; }
            add_request(*f, false);
            for (auto& r : s.recent)
                if (!strcmp(r.id, f->id)) { r.request_sent = 1; s.event(NET2_EV_RECENT); }
            s.event(NET2_EV_NOTICE, 0, "Asked " + std::string(f->name) + ". They have to accept.");
            if (f->name[0] != 'n' && f->name[0] != 'N')
                after(5, [this, f] {
                    bool waiting = false;
                    for (auto& r : s.requests) waiting |= !strcmp(r.id, f->id) && !r.incoming;
                    if (!waiting) return;
                    befriend(*f);
                    s.event(NET2_EV_NOTICE, 0, std::string(f->name) + " accepted: you are friends now.", f->name, f->id);
                });
        });
        return NET2_OK;
    }
    int friend_add(const std::string& code) override { return ask(fake_by_code(code), code); }
    int friend_op(const char* op, const std::string& id) override {
        if (!online()) return offline();
        std::string what = op;
        const Fake* f = fake_by_id(id);
        if (what == "add-id") return ask(f, f ? code_normal(f->code, 8) : "ZZZZZZZZ");
        after(0.3, [this, what, id, f] {
            auto drop_request = [&] {
                size_t before = s.requests.size();
                s.requests.erase(std::remove_if(s.requests.begin(), s.requests.end(), [&](const net2_request& r) { return id == r.id; }), s.requests.end());
                if (before != s.requests.size()) s.event(NET2_EV_REQUESTS);
                return before != s.requests.size();
            };
            auto drop_friend = [&] {
                size_t before = s.friends.size();
                s.friends.erase(std::remove_if(s.friends.begin(), s.friends.end(), [&](const net2_friend& x) { return id == x.id; }), s.friends.end());
                for (auto& r : s.recent)
                    if (id == r.id) r.is_friend = 0;
                if (before != s.friends.size()) { s.event(NET2_EV_FRIENDS); s.event(NET2_EV_RECENT); }
            };
            if (what == "accept") {
                bool had = false;
                for (auto& r : s.requests) had |= id == r.id && r.incoming;
                if (!had || !f) { s.error(NET2_ERR_NOT_FOUND, "There is no such request."); return; }
                befriend(*f);
            } else if (what == "decline") {
                if (!drop_request()) s.error(NET2_ERR_NOT_FOUND, "There is no such request.");
            } else if (what == "remove") {
                drop_friend();
            } else if (what == "block") {
                drop_request();
                drop_friend();
                s.invites.erase(std::remove_if(s.invites.begin(), s.invites.end(), [&](const net2_invite_t& i) { return id == i.from_id; }), s.invites.end());
                s.event(NET2_EV_INVITE);
                for (auto& b : s.blocked)
                    if (id == b.id) return;
                net2_friend b{};
                put(b.id, id);
                put(b.name, f ? f->name : "(somebody)");
                s.blocked.push_back(b);
                s.event(NET2_EV_FRIENDS);
            } else if (what == "unblock") {
                s.blocked.erase(std::remove_if(s.blocked.begin(), s.blocked.end(), [&](const net2_friend& b) { return id == b.id; }), s.blocked.end());
                s.event(NET2_EV_FRIENDS);
            }
        });
        return NET2_OK;
    }

    int invite(const std::string& id) override {
        if (!online()) return offline();
        const Fake* f = fake_by_id(id);
        bool is_friend = false;
        int presence = NET2_OFFLINE;
        for (auto& fr : s.friends)
            if (id == fr.id) { is_friend = true; presence = fr.presence; }
        if (!f || !is_friend) return s.error(NET2_ERR_NOT_FOUND, "Only a friend can be invited.");
        if (presence == NET2_OFFLINE) return s.error(NET2_ERR_REFUSED, std::string(f->name) + " is not online.");
        s.event(NET2_EV_NOTICE, 0, "Invited " + std::string(f->name) + ".");
        uint32_t now = serial;
        after(4, [this, f, now] {
            if (presence_of(f->id) == NET2_IN_GAME) { if (serial == now) s.chat_line("", std::string(f->name) + " is in a game and did not come."); return; }
            walk_in(*f, now);
            for (auto& fr : s.friends)
                if (!strcmp(fr.id, f->id)) { set_presence(fr, NET2_IN_ROOM, 0); put(fr.room, s.room.code); fr.room_players = s.room.count; s.event(NET2_EV_FRIENDS); }
        });
        after(7, [this, f, now] { mark_ready(*f, now); });
        return NET2_OK;
    }
    int presence_of(const char* id) {
        for (auto& fr : s.friends)
            if (!strcmp(fr.id, id)) return fr.presence;
        return NET2_OFFLINE;
    }
    int invite_answer(const std::string& id, bool accept) override {
        std::string room;
        for (auto& i : s.invites)
            if (id == i.from_id) room = i.room;
        if (room.empty()) return s.error(NET2_ERR_NOT_FOUND, "That invitation is gone.");
        s.invites.erase(std::remove_if(s.invites.begin(), s.invites.end(), [&](const net2_invite_t& i) { return id == i.from_id; }), s.invites.end());
        for (auto& f : s.friends)
            if (id == f.id) f.invited_me = 0;
        s.event(NET2_EV_INVITE);
        s.event(NET2_EV_FRIENDS);
        after(45, [this] { send_invite(); });
        return accept ? join(room) : NET2_OK;
    }

    int host(const net2_options& options) override {
        if (!online()) return offline();
        s.room.state = NET2_ROOM_JOINING;
        s.event(NET2_EV_ROOM);
        after(0.4, [this, options] { if (s.room.state == NET2_ROOM_JOINING) open_room("MQCK7", true, options); });
        return NET2_OK;
    }
    int join(const std::string& code) override {
        if (!online()) return offline();
        s.room.state = NET2_ROOM_JOINING;
        put(s.room.code, code);
        s.event(NET2_EV_ROOM);
        after(0.5, [this, code] {
            if (s.room.state != NET2_ROOM_JOINING) return;
            int problem = code == "FULL2" ? NET2_ERR_FULL : code == "NQPE2" ? NET2_ERR_NOT_FOUND : code == "LATE2" ? NET2_ERR_REFUSED : 0;
            if (problem) {
                s.room = net2_room_t{};
                s.event(NET2_EV_ROOM);
                s.error(problem, problem == NET2_ERR_FULL ? "That room is full." : problem == NET2_ERR_NOT_FOUND ? "There is no room with the code " + code + "." : "That game has already started.");
                return;
            }
            net2_options options{};
            put(options.level, "");
            options.difficulty = 1;
            open_room(code, false, options);
        });
        return NET2_OK;
    }
    int join_friend(const std::string& id) override {
        for (auto& f : s.friends)
            if (id == f.id) {
                if (f.presence != NET2_IN_ROOM || !f.joinable) return s.error(NET2_ERR_REFUSED, std::string(f.name) + " is not in a room you can walk into.");
                return join(f.room);
            }
        return s.error(NET2_ERR_NOT_FOUND, "That is not one of your friends.");
    }
    int chat(const std::string& text) override {
        s.chat_line(s.me.name, text);
        uint32_t now = serial;
        if (s.room.count > 1 && (text.find('?') != std::string::npos || s.room.chat_count % 3 == 0)) {
            const net2_member* other = nullptr;
            for (int i = 0; i < s.room.count; i++)
                if (!s.room.members[i].me) other = &s.room.members[i];
            std::string id = other->id;
            after(1.6, [this, id, now] {
                const Fake* f = fake_by_id(id);
                if (f) say(*f, "sounds good", now);
            });
        }
        return NET2_OK;
    }
    int ready(bool ready) override {
        net2_member* m = member(s.me.id);
        if (!m) return NET2_ERR_STATE;
        m->ready = ready;
        room_changed();
        uint32_t now = serial;
        if (ready && s.room.my_slot != s.room.host_slot)
            after(3, [this, now] {
                if (serial != now || s.room.state != NET2_ROOM_OPEN) return;
                net2_member* mine = member(s.me.id);
                if (mine && mine->ready && !s.room.mismatch) begin_start(now);
                else if (s.room.mismatch) say(FAKES[1], "the room says our copies differ - not starting", now);
            });
        return NET2_OK;
    }
    int set_options(const net2_options& options) override {
        s.room.options = options;
        room_changed();
        return NET2_OK;
    }
    int kick(int slot) override {
        for (int i = 0; i < s.room.count; i++)
            if (s.room.members[i].slot == slot) {
                s.chat_line("", std::string(s.room.members[i].name) + " was sent out of the room.");
                for (int k = i; k + 1 < s.room.count; k++) s.room.members[k] = s.room.members[k + 1];
                s.room.count--;
                room_changed();
                return NET2_OK;
            }
        return s.error(NET2_ERR_NOT_FOUND, "Nobody is in that place.");
    }
    int start() override {
        if (s.room.mismatch) s.event(NET2_EV_NOTICE, 0, "Starting although the copies differ.");
        begin_start(serial);
        return NET2_OK;
    }
    int leave() override {
        if (s.room.state == NET2_ROOM_NONE) return NET2_OK;
        serial++;
        s.room = net2_room_t{};
        s.session = net2_session_t{};
        s.event(NET2_EV_ROOM);
        return NET2_OK;
    }
    int game_state(const std::string& level, bool running) override {
        program_drives_game = true;
        if (s.room.state != NET2_ROOM_STARTING && s.room.state != NET2_ROOM_IN_GAME) return NET2_ERR_STATE;
        if (running) {
            s.room.state = NET2_ROOM_IN_GAME;
            room_changed();
        } else {
            s.room.state = NET2_ROOM_OPEN;
            s.session.valid = 0;
            for (int i = 0; i < s.room.count; i++) {
                net2_member& m = s.room.members[i];
                m.ready = m.host;
                if (!m.me) { m.route = NET2_ROUTE_NONE; m.rtt_ms = -1; }
                bool known = false;
                for (auto& r : s.recent) known |= !strcmp(r.id, m.id);
                if (!m.me && !known) {
                    const Fake* f = fake_by_id(m.id);
                    if (f) { net2_friend r = friend_of(*f, NET2_IN_ROOM); r.is_friend = m.is_friend; s.recent.insert(s.recent.begin(), r); }
                }
            }
            s.event(NET2_EV_RECENT);
            s.chat_line("", "The game is over. The room is open again.");
            room_changed();
            s.event(NET2_EV_GAME_OVER, 0, "", "", "", s.room.code);
        }
        (void)level;
        return NET2_OK;
    }
    int debug(const std::string& what, std::string& out) override {
        char text[160];
        snprintf(text, sizeof text, "mock: %s, clock %.1f s, speed %.1f, %zu timers, room serial %u", what.c_str(), clock, speed, timers.size(), serial);
        out = text;
        return NET2_OK;
    }
    int set(const std::string& key, const std::string& value) override {
        if (key == "mock-speed") {
            double v = atof(value.c_str());
            if (v < 0.1 || v > 1000) return NET2_ERR_ARGUMENT;
            speed = v;
            return NET2_OK;
        }
        if (key == "relay") return NET2_OK;
        return NET2_ERR_ARGUMENT;
    }
};

}  // namespace

Backend* make_mock(const net2_config& config) { return new Mock(config); }

}  // namespace net2impl
