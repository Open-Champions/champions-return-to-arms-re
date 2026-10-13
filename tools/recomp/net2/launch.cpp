// launch.cpp - the direct launch (game.h): the game's own lockstep session started from a
// room of our own, with no lobby screen; and the stand-alone program's way to a room from
// its command line (--opt net2=host | join:CODE).  docs/issues/native-rendezvous.md.
//
// What is done to the game, all of it from the game's main thread before or after a pass
// of its run tasks (netdrv.cpp's entry tasks_run 0x3226e4, hooks.h):
//
//   choose   what the game's own developer menu does on the way to a net game without a
//            lobby (frontend_run 0x1e08f0, states 1 and 6): clear the net settings block
//            0x402a30, set the "net game" flag 0x4f70a0 and the host bit, point the "chosen"
//            pointer 0x86ad54 at 0x4fbbe2, and start the character screens
//            (frontend_startPlayerSelect 0x1e3ba0).  The front end is parked in state 10
//            ("waiting for the lobby"), in which it draws its background and does nothing
//            while the lobby state word is 0.
//   launch   what frontend_startNetGame 0x1e21e0 does on its developer branch, with the
//            launch tables written from the description instead of from its four fixed
//            addresses: launch flag 0x402793, net_gameInit(0) 0x1397a0, player count
//            0x402a37, host 0x402a38 (always player 0), own number 0x402a39, both address
//            tables 0x402b3b / 0x402b4b and both port tables 0x402b5c / 0x402b6c, then
//            net_launchTransfer 0x134c60.  From there the game's own front end runs its
//            launch handshake (net_launchUpdate 0x135638) every frame: the machines exchange
//            their characters, count down and load the first level.
//   addresses the game is told: player k is 10.77.0.(k+1), port 4000, on every machine
//            (carrier.h).  Its datagrams on that port are carried by net2 (hooks.h).
//
// Nothing of the game's code is changed and no word of it is patched.
#include "game.h"
#include "carrier.h"
#include "hooks.h"
#include "session_impl.h"

#include "rt.h"
#include "funcs.h"
#include "../net/netdrv.h"

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <sstream>
#include <string>

namespace {

// ---- the game's memory (names.tsv, symbols/, docs/ui.md, docs/netcode.md) -------------------
const u32 A_IN_FRONTEND = 0x41b510, A_LEVEL_NAME = 0x41b721, A_PENDING_LEVEL = 0x41b6d0;
const u32 A_FE_STATE = 0x4f6b78, A_FE_FADE = 0x4d8a10, A_FE_NET = 0x4f70a0, A_FE_FIRST_PASS = 0x4f6b70, A_FE_RUNNING = 0x4f83f8;
const u32 A_SETTINGS = 0x402a30, SETTINGS_SIZE = 0x14c;     // +0 bits (1 host, 2 quick character, 4 full character), +2 difficulty,
                                                            // +3 mode, +4 mission, +5 kill limit, +7 players, +8 host, +9 own number
const u32 A_ADDR1 = 0x402b3b, A_ADDR2 = 0x402b4b, A_PORT1 = 0x402b5c, A_PORT2 = 0x402b6c;
const u32 A_CHOSEN_POINTER = 0x86ad54, A_CHOSEN = 0x4fbbe2, A_QUICK = 0x4fdb80;   // the 0x2c-byte summary of the chosen character
const u32 A_LAUNCHING = 0x402793, A_DEV_LOBBY = 0x402792, A_NETWORK_MODE = 0x402791, A_LOBBY_LAUNCH = 0x4f7134;
const u32 A_LOBBY_STATE = 0x506160;
const u32 A_NET_FRAME = 0x4027ac, A_NUM_PEERS = 0x4027c4, A_PEERS = 0x5bf838, PEER_SIZE = 0x44e0, PEER_DROPPED = 0x44d5;
const u32 A_PLAYERS = 0x4d8af0, PLAYER_SIZE = 0x4c30, PLAYER_CLASS = 0x50, PLAYER_LEVEL = 0x59;
const u32 A_SEL_TASK_NAME = 0x53ce38;       // "playerSelection"
const u32 A_SEL_PAGE = 0x8e2c02;

u8 rd8(u32 a) { return a < RAM_SIZE ? g_ram[a] : 0; }
u32 rd32(u32 a) { u32 v = 0; if (a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
float rdf(u32 a) { float v = 0; if (a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
void wr8(u32 a, u8 v) { if (a < RAM_SIZE) g_ram[a] = v; }
void wr32(u32 a, u32 v) { if (a <= RAM_SIZE - 4) memcpy(g_ram + a, &v, 4); }
std::string rdstr(u32 a, u32 limit) {
    std::string text;
    for (u32 i = 0; i < limit && a + i < RAM_SIZE && g_ram[a + i]; i++) text += (char)g_ram[a + i];
    return text;
}

// A call of one of the game's functions from here: its registers are put back afterwards.
u64 call(Ctx* c, void (*fn)(Ctx*), u64 a0 = 0, u64 a1 = 0) {
    Ctx saved = *c;
    c->r[4] = a0;
    c->r[5] = a1;
    fn(c);
    u64 result = c->r[2];
    s64 budget = c->budget;
    *c = saved;
    c->budget = budget;
    return result;
}

struct Game {
    bool installed = false;
    std::recursive_mutex lock;
    int phase = NET2_GAME_BOOTING;
    int launches = 0;
    bool failed = false;
    std::string text = "the game is starting";
    bool title_seen = false;
    // requests, carried out by the game's thread
    int want_choose = -1;               // 0 / 1: as joiner / as host
    bool want_launch = false, want_stop = false;
    net2_direct direct{};               // the description of the launch asked for
    bool direct_set = false;
    // the session whose datagrams are carried
    n2::Carrier own_carrier;          // a direct launch by fixed addresses
    n2::Carrier* carrier = nullptr;
    bool carrying = false;
    u64 blank = 0, launch_blank = 0, boot_press_until = 0, boot_next_press = 0, title_since = 0;
    net2_options options{};
    int count = 0, me = 0;
    net2_character character{};
    bool quiet = false;
    void (*previous_command)(const std::string&, u64) = nullptr;
    rta::PadSource* inner_pad = nullptr;
    bool drive_boot = false;
    FILE* log = nullptr;
} G;

void say(const char* format, ...) {
    char text[512];
    va_list args;
    va_start(args, format);
    vsnprintf(text, sizeof text, format, args);
    va_end(args);
    printf("net2: %s\n", text);
    fflush(stdout);
    if (G.log) { fprintf(G.log, "[%llu] %s\n", (unsigned long long)G.blank, text); fflush(G.log); }
}

void set_phase(int phase, const std::string& text) {
    if (phase == G.phase && text == G.text) return;
    G.phase = phase;
    G.text = text;
    say("%s", text.c_str());
}

bool in_front_end() { return rd8(A_IN_FRONTEND) == 1 && rdstr(A_LEVEL_NAME, 8) == "intro"; }
// the title screen's menu, drawn and taking input: the front end's own first pass has been
// made (0x4f6b70 is cleared by it: it loads what the character screens need)
bool at_title() {
    return in_front_end() && rd32(A_FE_STATE) == 0 && rd32(A_LOBBY_STATE) == 0 && rdf(A_FE_FADE) >= 1.0f && rd32(A_FE_FIRST_PASS) == 0 &&
           rd32(A_FE_RUNNING) == 1;
}

void read_character() {
    G.character = net2_character{};
    net2impl::put(G.character.name, net2impl::clean_label(rdstr(A_PLAYERS, 31).c_str(), 24));
    static const char* CLASSES[7] = {"Barbarian", "Wood Elf Ranger", "High Elf Cleric", "Erudite Wizard", "Dark Elf Shadowknight",
                                     "Vah Shir Berserker", "Iksar Shaman"};
    u32 cls = rd32(A_PLAYERS + PLAYER_CLASS);
    net2impl::put(G.character.cls, cls < 7 ? CLASSES[cls] : "?");
    G.character.level = (s8)rd8(A_PLAYERS + PLAYER_LEVEL);
}

// ---- carried out on the game's thread ----------------------------------------------------
void do_choose(Ctx* c, bool host) {
    memset(g_ram + A_SETTINGS, 0, SETTINGS_SIZE);
    wr32(A_FE_NET, 1);
    wr8(A_SETTINGS + 2, 1);
    wr8(A_SETTINGS + 3, 0);
    wr8(A_SETTINGS + 0, host ? 1 : 0);
    wr32(A_CHOSEN_POINTER, A_CHOSEN);
    wr32(A_FE_STATE, 10);
    call(c, fn_001e3ba0);                           // frontend_startPlayerSelect
    G.failed = false;
    set_phase(NET2_GAME_CHOOSING, "the game's character screens are up");
}

void do_launch(Ctx* c) {
    const net2_direct& d = G.direct;
    G.count = d.count;
    G.me = d.my_slot;
    G.options = d.options;
    // what the front end's state 7 does once a character is chosen
    wr8(A_SETTINGS + 10, 0xff);
    u8 bits = (u8)((d.my_slot == 0 ? 1 : 0) | ((rd8(A_QUICK + 0x29) & 3) == 0 ? 2 : 4));
    wr8(A_SETTINGS + 0, bits);
    if (d.my_slot == 0) {
        wr8(A_SETTINGS + 2, (u8)(d.options.difficulty >= 1 && d.options.difficulty <= 5 ? d.options.difficulty : 1));
        wr8(A_SETTINGS + 3, 0);                     // co-operative; the other modes are the game's own versus kinds
        wr8(A_SETTINGS + 4, 0);
        wr8(A_SETTINGS + 5, 0);
    }
    // frontend_startNetGame 0x1e21e0, its branch for "no lobby"
    wr8(A_LAUNCHING, 1);
    wr8(A_DEV_LOBBY, 0);
    call(c, fn_0019d8a4, 10);
    call(c, fn_0019d028);
    call(c, fn_001397a0, 0);                        // net_gameInit(0)
    wr32(A_LOBBY_LAUNCH, 0);
    wr8(A_SETTINGS + 7, (u8)d.count);
    wr8(A_SETTINGS + 8, 0);
    wr8(A_SETTINGS + 9, (u8)d.my_slot);
    for (int k = 0; k < NET2_PLAYERS; k++) {
        u32 ip = n2::GAME_NET + (u32)k;
        const u8 bytes[4] = {(u8)(ip >> 24), (u8)(ip >> 16), (u8)(ip >> 8), (u8)ip};
        memcpy(g_ram + A_ADDR1 + k * 4, bytes, 4);
        memcpy(g_ram + A_ADDR2 + k * 4, bytes, 4);
        wr32(A_PORT1 + k * 4, n2::GAME_PORT);
        wr32(A_PORT2 + k * 4, n2::GAME_PORT);
    }
    G.carrying = true;
    call(c, fn_00134c60);                           // net_launchTransfer
    G.launch_blank = G.blank;
    char text[160];
    snprintf(text, sizeof text, "launching: player %d of %d, settings bits %02x, character %s (%s %d)", d.my_slot + 1, d.count, bits, G.character.name,
             G.character.cls, G.character.level);
    set_phase(NET2_GAME_LAUNCHING, text);
}

void on_tasks(Ctx* c, bool from_tick) {
    if (from_tick) return;
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    if (G.want_choose >= 0 && G.phase == NET2_GAME_TITLE && at_title()) {
        int host = G.want_choose;
        G.want_choose = -1;
        do_choose(c, host != 0);
    } else if (G.phase == NET2_GAME_CHOOSING) {
        // the character screens are a task of the game; when it is gone the choice is made or given up
        if (call(c, fn_0019e5e8, A_SEL_TASK_NAME) == 0) {
            if (rd8(A_CHOSEN) == 1) {
                read_character();
                char text[160];
                snprintf(text, sizeof text, "a character is chosen: %s (%s, level %d)", G.character.name, G.character.cls, G.character.level);
                set_phase(NET2_GAME_CHOSEN, text);
            } else {
                wr32(A_FE_STATE, 0);
                wr32(A_FE_NET, 0);
                G.failed = true;
                set_phase(NET2_GAME_TITLE, "the character screens were left without a character");
            }
        }
    } else if (G.want_launch && G.phase == NET2_GAME_CHOSEN && in_front_end()) {
        G.want_launch = false;
        do_launch(c);
    }
}

void on_after(Ctx* c, bool from_tick) {
    (void)c;
    if (from_tick) return;
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    if (G.phase != NET2_GAME_LAUNCHING || rd8(A_LAUNCHING) != 0) return;
    // net_launchUpdate has answered: 2 (launched: the front end has set the network mode and
    // left) or -1 (failed or cancelled: the front end stays)
    if (rd8(A_NETWORK_MODE) == 1) {
        if (G.options.level[0]) {
            // another first level than the game's own: the pending name, replaced on every
            // machine alike before anything is loaded
            memset(g_ram + A_PENDING_LEVEL, 0, 32);
            memcpy(g_ram + A_PENDING_LEVEL, G.options.level, strnlen(G.options.level, 20));
        }
        G.launches++;
        char text[160];
        snprintf(text, sizeof text, "launched after %llu blanks: %u players, first level %s", (unsigned long long)(G.blank - G.launch_blank), rd32(A_NUM_PEERS),
                 rdstr(A_PENDING_LEVEL, 20).c_str());
        set_phase(NET2_GAME_LOADING, text);
    } else {
        wr32(A_FE_STATE, 0);
        wr32(A_FE_NET, 0);
        G.carrying = false;
        G.failed = true;
        set_phase(NET2_GAME_TITLE, "the launch did not complete (a player could not be reached, or it was cancelled)");
    }
}

void on_blank(uint64_t number) {
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    G.blank = number;
    if (G.carrier) G.carrier->poll(net2impl::steady_ms());
    bool front = in_front_end();
    switch (G.phase) {
    case NET2_GAME_BOOTING:
        // the menu must have stood for a second: it fades in, and a choice made in its first
        // frames finds the character screens' data not loaded yet
        if (!at_title()) G.title_since = 0;
        else if (G.title_since == 0) G.title_since = number;
        else if (number - G.title_since >= 60) { G.title_seen = true; set_phase(NET2_GAME_TITLE, "the game is at its title screen"); }
        break;
    case NET2_GAME_LOADING:
        if (!front && rd8(A_NETWORK_MODE) == 1 && (s32)rd32(A_NET_FRAME) > 0 && rdstr(A_LEVEL_NAME, 20) != "intro") {
            char text[96];
            snprintf(text, sizeof text, "the game runs: level %s", rdstr(A_LEVEL_NAME, 20).c_str());
            set_phase(NET2_GAME_RUNNING, text);
        }
        // fall through
    case NET2_GAME_RUNNING:
        if (front && rd8(A_NETWORK_MODE) == 0 && G.blank - G.launch_blank > 120) {
            G.carrying = false;
            if (G.carrier == &G.own_carrier) G.own_carrier.end();
            set_phase(at_title() ? NET2_GAME_TITLE : NET2_GAME_BUSY, "the game is over: back at the title screen");
        }
        break;
    case NET2_GAME_BUSY:
        if (at_title()) set_phase(NET2_GAME_TITLE, "the game is at its title screen");
        break;
    case NET2_GAME_TITLE:
        if (!front && G.title_seen) set_phase(NET2_GAME_BUSY, "the game is elsewhere (an offline game)");
        break;
    default:
        break;
    }
}

// ---- the game's datagrams ---------------------------------------------------------------
bool udp_owns(uint16_t game_port) { return G.carrying && G.carrier && game_port == n2::GAME_PORT; }

int32_t udp_send(uint16_t, const uint8_t* data, uint32_t length, uint32_t dest_ip, uint16_t) {
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    u32 slot = dest_ip - n2::GAME_NET;
    if (slot < NET2_PLAYERS) G.carrier->send((int)slot, data, length);
    return (int32_t)length;
}

bool udp_receive(uint16_t, uint8_t* buffer, size_t capacity, size_t& size, uint32_t& shown_ip, uint16_t& from_port) {
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    int from = 0;
    int got = G.carrier->receive(from, buffer, capacity);
    if (got < 0) {
        G.carrier->poll(net2impl::steady_ms());
        got = G.carrier->receive(from, buffer, capacity);
        if (got < 0) return false;
    }
    size = (size_t)got;
    shown_ip = n2::GAME_NET + (u32)from;
    from_port = n2::GAME_PORT;
    return true;
}

// ---- script and control: "app net2 ..." ---------------------------------------------------
std::string phase_name(int phase) {
    static const char* NAMES[] = {"booting", "title", "choosing", "chosen", "launching", "loading", "running", "busy"};
    return phase >= 0 && phase <= 7 ? NAMES[phase] : "?";
}

void command(const std::string& text, u64 frame) {
    std::istringstream words(text);
    std::string first, verb;
    words >> first;
    if (first != "net2") {
        if (G.previous_command) G.previous_command(text, frame);
        else rt_note("script: app " + text + " (no application to take it)");
        return;
    }
    words >> verb;
    std::string rest;
    std::getline(words, rest);
    while (!rest.empty() && rest[0] == ' ') rest.erase(0, 1);
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    if (verb == "status") {
        net2_game_status_t s;
        net2_game_status(&s);
        printf("[frame %llu] net2: phase=%s launches=%d failed=%d tick=%u players=%d level=%s character=%s;%s;%d fe=%u page=%u text=%s\n",
               (unsigned long long)frame, phase_name(s.phase).c_str(), s.launches, s.failed, s.tick, s.players, s.level, s.character.name,
               s.character.cls, s.character.level, rd32(A_FE_STATE), rd8(A_SEL_PAGE), s.text);
        printf("[frame %llu] net2: game: in-front-end=%u level=%s fade=%.2f first-pass=%08x running=%08x lobby=%u chosen=%u launching=%u netmode=%u\n",
               (unsigned long long)frame, rd8(A_IN_FRONTEND), rdstr(A_LEVEL_NAME, 12).c_str(), rdf(A_FE_FADE), rd32(A_FE_FIRST_PASS), rd32(A_FE_RUNNING),
               rd32(A_LOBBY_STATE), rd8(A_CHOSEN), rd8(A_LAUNCHING), rd8(A_NETWORK_MODE));
        if (G.carrier) printf("[frame %llu] net2: carrier: %s\n", (unsigned long long)frame, G.carrier->text().c_str());
    } else if (verb == "choose") {
        net2_game_choose(rest == "host" || rest == "1");
    } else if (verb == "direct") {
        // direct SESSION MY_SLOT ADDRESS,ADDRESS[,ADDRESS[,ADDRESS]] [LEVEL] [DIFFICULTY]
        net2_direct d{};
        std::istringstream more(rest);
        std::string session, list, level;
        int difficulty = 0;
        more >> session >> d.my_slot >> list >> level >> difficulty;
        d.session = (uint32_t)strtoul(session.c_str(), nullptr, 16);
        std::istringstream each(list);
        std::string one;
        while (std::getline(each, one, ',') && d.count < NET2_PLAYERS) net2impl::put(d.players[d.count++].address, one);
        if (level != "-" && !level.empty()) net2impl::put(d.options.level, level);
        d.options.difficulty = difficulty;
        int r = net2_game_launch_direct(&d);
        if (r) printf("[frame %llu] net2: direct: %s\n", (unsigned long long)frame, net2_error_text(r));
    } else if (verb == "stop") {
        net2_game_stop();
    } else {
        printf("[frame %llu] net2: unknown command '%s'\n", (unsigned long long)frame, verb.c_str());
    }
    fflush(stdout);
}

// the controller: while the game boots, cross is pressed for the player (the memory card
// questions and the logos), as the one-step online does
struct Pad : rta::PadSource {
    void read(unsigned port, uint64_t number, rta::PadState& state) override {
        if (G.inner_pad) G.inner_pad->read(port, number, state);
        else state = script_pad(port);
        if (port != 0 || !G.drive_boot || G.phase != NET2_GAME_BOOTING) return;
        if (in_front_end()) { state = rta::PadState(); return; }      // the title screen is coming up: hands off
        if (number >= G.boot_next_press) { G.boot_press_until = number + 6; G.boot_next_press = number + 46; }
        state = rta::PadState();
        if (number < G.boot_press_until) state.buttons = rta::PAD_CROSS;
    }
    void rumble(unsigned port, uint8_t small_motor, uint8_t large_motor) override {
        if (G.inner_pad) G.inner_pad->rumble(port, small_motor, large_motor);
    }
} g_pad;

void install() {
    if (G.installed) return;
    G.installed = true;
    G.previous_command = script_app_command;
    script_app_command = command;
    if (const char* file = rt_option("net2-log")) G.log = fopen(file, "w");
    const char* boot = rt_option("net2-boot");
    G.drive_boot = boot && std::string(boot) == "1";
    if (G.drive_boot) {
        G.inner_pad = g_hooks.pad;
        g_hooks.pad = &g_pad;
    }
}

void first_blank(uint64_t number) {
    install();
    on_blank(number);
}

struct Install {
    Install() {
        net2hook::blank = first_blank;
        net2hook::tasks = on_tasks;
        net2hook::after = on_after;
        net2hook::udp_owns = udp_owns;
        net2hook::udp_send = udp_send;
        net2hook::udp_receive = udp_receive;
    }
} g_install;

}  // namespace

extern "C" {

void net2_game_status(net2_game_status_t* out) {
    if (!out) return;
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    *out = net2_game_status_t{};
    out->phase = G.phase;
    out->launches = G.launches;
    out->failed = G.failed;
    net2impl::put(out->text, G.text);
    if (G.phase >= NET2_GAME_CHOSEN && G.phase <= NET2_GAME_RUNNING) out->character = G.character;
    if (G.phase == NET2_GAME_RUNNING) {
        net2impl::put(out->level, rdstr(A_LEVEL_NAME, 20));
        out->tick = rd32(A_NET_FRAME);
        u32 peers = rd32(A_NUM_PEERS);
        for (u32 k = 0; k < peers && k < NET2_PLAYERS; k++)
            if (rd8(A_PEERS + k * PEER_SIZE + PEER_DROPPED) == 0) out->players++;
    }
}

int net2_game_choose(int as_host) {
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    if (G.phase != NET2_GAME_TITLE && G.phase != NET2_GAME_BOOTING && G.phase != NET2_GAME_CHOSEN) return NET2_ERR_STATE;
    if (G.phase == NET2_GAME_CHOSEN) return NET2_OK;
    G.want_choose = as_host ? 1 : 0;
    return NET2_OK;
}

int net2_game_launch_direct(const net2_direct* description) {
    if (!description) return NET2_ERR_ARGUMENT;
    std::lock_guard<std::recursive_mutex> hold(G.lock);
    const net2_direct& d = *description;
    if (d.count < 2 || d.count > NET2_PLAYERS || d.my_slot < 0 || d.my_slot >= d.count) return NET2_ERR_ARGUMENT;
    if (G.phase != NET2_GAME_CHOSEN && G.phase != NET2_GAME_CHOOSING) return NET2_ERR_STATE;
    n2::Endpoint where[NET2_PLAYERS];
    for (int k = 0; k < d.count; k++)
        if (!n2::parse_endpoint(d.players[k].address, where[k])) return NET2_ERR_ARGUMENT;
    std::string problem;
    G.own_carrier.close();
    if (!G.own_carrier.open(d.bind[0] ? d.bind : d.players[d.my_slot].address, problem)) {
        say("%s", problem.c_str());
        return NET2_ERR_SERVICE;
    }
    G.own_carrier.begin(d.session, d.count, d.my_slot);
    G.own_carrier.policy(n2::RELAY_NEVER);
    for (int k = 0; k < d.count; k++)
        if (k != d.my_slot) G.own_carrier.fixed(k, where[k]);
    G.carrier = &G.own_carrier;
    G.direct = d;
    G.want_launch = true;
    return NET2_OK;
}

void net2_game_attach(net2*) {}
int net2_game_launch(net2*) { return NET2_ERR_STATE; }
int net2_game_stop(void) { return NET2_ERR_STATE; }

}  // extern "C"
