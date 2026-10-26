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
//
// The stand-alone program (options after "--", or tools/recomp/net2/play.sh):
//   --opt net2=host[:friends] | join:CODE     a room at the service, by itself from power-on
//   --opt net2-service=HOST:PORT   (else RTA_NET2_SERVICE, else <data>/net2-service.txt)
//   --opt net2-name=NAME           the display name of a first start
//   --opt net2-data=DIR            where the identity file is (default: the network's data folder)
//   --opt net2-players=N           host: start by itself when N players are in and ready (default 2;
//                                  0: never - somebody says `app net2 start`)
//   --opt net2-level=NAME --opt net2-difficulty=N    the host's options
//   --opt net2-size=N (5..8)                          a room of up to N players (a copy started with --opt party8=1)
//   --opt net2-again=1             after a game: choose a character and be ready again
//   --opt net2-relay=force|never   tests: this machine's routes
//   --opt net2-bind=ADDRESS:PORT   tests: the UDP socket's own address
//   --opt net2-boot=0              do not press cross for the player while the game boots
//   --opt net2-commands=FILE       tests: "net2 ..." lines written to this file are carried out
//   --opt net2-log=FILE            what is said, with the vertical blank
// Script / control: app net2 status | choose [host] | direct SESSION SLOT ADDR,ADDR[,..] [LEVEL] [DIFFICULTY]
//                   | launch | and every command of clicmd.cpp (app net2 room, app net2 chat hello ...)
#include "game.h"
#include "carrier.h"
#include "clicmd.h"
#include "hooks.h"
#include "session_impl.h"

#include "rt.h"
#include "moved.h"
#include "funcs.h"
#include "../net/netdrv.h"

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

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
const u32 A_LAUNCH_RECS = 0x402b90, LAUNCH_REC = 0x144;     // g_launchRecs (docs/netcode.md "Launch")
const u32 A_NUM_PLAYERS = 0x4d8ae0, A_DIFFICULTY = 0x4f719c, A_SAVED_CONFIG = 0x4f8f38;
const u32 A_SEL_TASK_NAME = 0x53ce38;       // "playerSelection"
const u32 A_SEL_PAGE = 0x8e2c02;

// a table moved for eight players is where it is (rt/moved.h); the same address otherwise
u8 rd8(u32 a) { a = party8_at(a); return g_ram && a < RAM_SIZE ? g_ram[a] : 0; }
u32 rd32(u32 a) { a = party8_at(a); u32 v = 0; if (g_ram && a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
float rdf(u32 a) { a = party8_at(a); float v = 0; if (g_ram && a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
void wr8(u32 a, u8 v) { a = party8_at(a); if (g_ram && a < RAM_SIZE) g_ram[a] = v; }
void wr32(u32 a, u32 v) { a = party8_at(a); if (g_ram && a <= RAM_SIZE - 4) memcpy(g_ram + a, &v, 4); }
std::string rdstr(u32 a, u32 limit) {
    a = party8_at(a);
    std::string text;
    for (u32 i = 0; g_ram && i < limit && a + i < RAM_SIZE && g_ram[a + i]; i++) text += (char)g_ram[a + i];
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

typedef std::lock_guard<std::recursive_mutex> Hold;

struct Game {
    bool installed = false;
    int phase = NET2_GAME_BOOTING;
    int launches = 0;
    bool failed = false;
    std::string text = "the game is starting";
    bool title_seen = false;
    // requests, carried out by the game's thread
    int want_choose = -1;               // 0 / 1: as joiner / as host
    bool want_launch = false;
    net2_direct direct{};               // the description of the launch asked for
    // the session whose datagrams are carried
    n2::Carrier own_carrier;            // a direct launch by fixed addresses
    n2::Carrier* carrier = nullptr;
    bool carrying = false;
    u64 blank = 0, launch_blank = 0, boot_press_until = 0, boot_next_press = 0, title_since = 0;
    net2_options options{};
    net2_character character{};
    std::string level;                  // the level last told to the room
    void (*previous_command)(const std::string&, u64) = nullptr;
    rta::PadSource* inner_pad = nullptr;
    bool drive_boot = false;
    FILE* log = nullptr;
    // the room this program is attached to
    net2* session = nullptr;
    bool own_session = false;           // made here (the stand-alone program): polled and its events printed here
    uint32_t launched_session = 0;      // the start that was taken up
    int64_t start_seen_ms = 0;
    bool told_running = false;
    // the stand-alone program's own way to a room
    std::string want_room;              // "host", "host:friends", "join:CODE"
    bool asked_room = false, asked_ready = false, again = false;
    int want_players = 2;
    int64_t last_start_try = 0;
    std::string command_file, shown_code;
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

net2_character read_character(u32 record) {
    net2_character c{};
    net2impl::put(c.name, net2impl::clean_label(rdstr(record, 31).c_str(), 24));
    u32 cls = rd32(record + PLAYER_CLASS);
    net2impl::put(c.cls, cls < 7 ? net2impl::CLASS_WORDS[cls] : "?");
    c.level = (s8)rd8(record + PLAYER_LEVEL);
    return c;
}

// the room is told what became of its start
void tell_room(const char* level) {
    if (G.session) net2_game_state(G.session, level);
}

// ---- carried out on the game's thread ----------------------------------------------------
// The game's own code can reach a vertical blank, and a host that gates the blanks (the Godot library: tools/godot/lib/rtag.cpp
// lets the game go one blank at a time) may at that moment be waiting for the big lock in a net2_* call of its own (the
// portal's net2_poll, net2_room, net2_game_status once a frame): the lock must not be held across a call of the game.
// do_choose and do_launch run under on_tasks' one Hold; around each call into the game it is let go and taken again.
u64 call_unheld(Ctx* c, void (*fn)(Ctx*), u64 a0 = 0, u64 a1 = 0) {
    net2impl::big_lock().unlock();
    u64 r = call(c, fn, a0, a1);
    net2impl::big_lock().lock();
    return r;
}

void do_choose(Ctx* c, bool host) {
    // The character screens take two things from the game that was played before: for how
    // many players (g_numPlayers - after a net game the number that was in it: the screens
    // then wait for a second controller), and the difficulty (above the first they only
    // take an imported character: seen as "the screens came up and cross did nothing" on
    // the way into a second game).  As at power-on: one player, the first difficulty.
    wr32(A_NUM_PLAYERS, 1);
    wr32(A_DIFFICULTY, 1);
    for (u32 k = 0; k < SETTINGS_SIZE; k++) wr8(A_SETTINGS + k, 0);   // byte by byte: the address and port tables in it may be moved (moved.h)
    wr32(A_FE_NET, 1);
    wr8(A_SETTINGS + 2, 1);
    wr8(A_SETTINGS + 3, 0);
    wr8(A_SETTINGS + 0, host ? 1 : 0);
    wr32(A_CHOSEN_POINTER, A_CHOSEN);
    wr32(A_FE_STATE, 10);
    call_unheld(c, fn_001e3ba0);                           // frontend_startPlayerSelect
    G.failed = false;
    set_phase(NET2_GAME_CHOOSING, "the game's character screens are up");
}

// A game of five to eight (app/party8.h): the game's address and port tables have four entries, at fixed distances
// from one another that net_launchTransfer's loop over the players reaches with one pointer (0x1350d8-0x1351c8), so
// for players 4..7 it reads other words.  Its launch records have room for eight (moved), and in a room every
// machine's address is known (player k is GAME_NET + k, GAME_PORT): what the loop writes for k >= 4 is written here
// afterwards, field for field as the loop writes it for 0..3.
void launch_ended(bool failed, const std::string& text);
void party8_records(int count) {
    const u32 recs = party8_at(A_LAUNCH_RECS);
    for (int k = 4; k < count && k < NET2_PLAYERS; k++) {
        const u32 r = recs + (u32)k * LAUNCH_REC;
        const u32 ip = n2::GAME_NET + (u32)k;
        const u8 bytes[4] = {(u8)(ip >> 24), (u8)(ip >> 16), (u8)(ip >> 8), (u8)ip};      // as the address table holds them
        for (int b = 0; b < 4; b++) { wr8(r + 4 + (u32)b, bytes[3 - b]); wr8(r + 0x24 + (u32)b, 0); }   // the second address: empty (do_launch)
        wr32(r + 0x30, n2::GAME_PORT);
        wr32(r + 0x34, n2::GAME_PORT);
        for (u32 b = 0; b < 16; b++) wr8(r + 0x10 + b, rd8(r + b));      // the address block the sends use
        wr32(r + 0x38, n2::GAME_PORT);
        wr32(r + 0x40, (u32)k);
        wr32(r + 0x44, 0);
        wr32(r + 0x64, 0);
    }
}
// ... and at the end of the launch the game sets +0x44c0 = 1 for the peers 0..3 only (a countdown from 3, 0x13766c)
// ... and the two input-codec states of each peer (+0x10 and +0x60: four 16-byte channel states with 128.0 at +8, and
// 0xc bytes after them) are set up by net_shutdown 0x1393f8 for the four peers of its table only (its loop ends at
// g_peers + 0x11380): peers 4..7 are given the same starting states here, before the first input packet - with zeroes
// a sender's encoder and its receivers' decoder would start from different states (Ran: player 5's stick read
// differently by everyone else from the first tick)
void party8_peers(int count) {
    const u32 peers = party8_at(A_PEERS);
    for (int k = 4; k < count && k < NET2_PLAYERS; k++) {
        const u32 p = peers + (u32)k * PEER_SIZE;
        wr32(p + 0x44c0, 1);
        for (u32 state : {0x10u, 0x60u}) {
            for (u32 b = 0; b < 0x4c; b += 4) wr32(p + state + b, 0);
            for (u32 ch = 0; ch < 4; ch++) wr32(p + state + ch * 0x10 + 8, 0x43000000u);   // 128.0f
        }
    }
}

void do_launch(Ctx* c) {
    const net2_direct& d = G.direct;
    if (d.count > 4 && !(net2hook::party8_capable && net2hook::party8_capable() == 1 && net2hook::party8_game)) {
        launch_ended(true, "a game of more than four players needs a copy started for rooms of up to eight");
        return;
    }
    G.options = d.options;
    // what the front end's state 7 does once a character is chosen
    wr8(A_SETTINGS + 10, 0xff);
    u8 bits = (u8)((d.my_slot == 0 ? 1 : 0) | ((rd8(A_QUICK + 0x29) & 3) == 0 ? 2 : 4));
    wr8(A_SETTINGS + 0, bits);
    if (d.my_slot == 0) {
        // the host's choices travel to the others in the handshake (the game's own way)
        wr8(A_SETTINGS + 2, (u8)(d.options.difficulty >= 1 && d.options.difficulty <= 4 ? d.options.difficulty : 1));
        // the game's own three modes (net2_options.mode: 0 play missions, 1 arena co-operative, 2 arena versus), the
        // mission (mode 0: 0 = from the hub; else the net menu's 1..13) and versus's kill limit, as its net menu
        // (states 7 to 9, docs/ui.md) leaves them in the settings block: the mode, the entry chosen, the limit's entry
        const int mode = d.options.mode >= 0 && d.options.mode <= 2 ? d.options.mode : 0;
        const int limit = d.options.kill_limit >= 25 ? 2 : (d.options.kill_limit >= 10 ? 1 : 0);
        wr8(A_SETTINGS + 3, (u8)mode);
        wr8(A_SETTINGS + 4, (u8)(mode == 0 ? (d.options.mission >= 0 && d.options.mission <= 13 ? d.options.mission : 0) : 0));
        wr8(A_SETTINGS + 5, (u8)(mode == 2 ? limit : 0));
    }
    // frontend_startNetGame 0x1e21e0, its branch for "no lobby"
    wr8(A_LAUNCHING, 1);
    wr8(A_DEV_LOBBY, 0);
    call_unheld(c, fn_0019d8a4, 10);
    call_unheld(c, fn_0019d028);
    call_unheld(c, fn_001397a0, 0);                        // net_gameInit(0)
    wr32(A_LOBBY_LAUNCH, 0);
    wr8(A_SETTINGS + 7, (u8)d.count);
    wr8(A_SETTINGS + 8, 0);
    wr8(A_SETTINGS + 9, (u8)d.my_slot);
    // A game of five to eight (party8_records): the second address table - the "internal" address the game turns to
    // when a packet comes from its own outside address (two consoles behind one router, docs/netcode.md "Launch") -
    // is left empty.  In a room every address is distinct, so nothing needs it; and a player 4..7 looks for its own
    // outside address at addr1[own], which is the second table's entry own-4: empty, no packet ever matches it.
    const bool wide = d.count > 4;
    for (int k = 0; k < 4; k++) {           // the game's tables have four entries (a room of five to eight: party8_records)
        u32 ip = n2::GAME_NET + (u32)k;
        const u8 bytes[4] = {(u8)(ip >> 24), (u8)(ip >> 16), (u8)(ip >> 8), (u8)ip};
        const u8 none[4] = {0, 0, 0, 0};
        memcpy(g_ram + party8_at(A_ADDR1 + k * 4), bytes, 4);
        memcpy(g_ram + party8_at(A_ADDR2 + k * 4), wide ? none : bytes, 4);
        wr32(A_PORT1 + k * 4, n2::GAME_PORT);
        wr32(A_PORT2 + k * 4, n2::GAME_PORT);   // (players 4..7 read their own port at port1[own]: these, all GAME_PORT)
    }
    // a game of five to eight: the hard-coded fours become eight before the launch's first loop over the peers
    if (wide) net2hook::party8_game(d.count);
    G.carrying = true;
    call_unheld(c, fn_00134c60);                           // net_launchTransfer
    if (wide) party8_records(d.count);
    G.launch_blank = G.blank;
    G.told_running = false;
    char text[200];
    snprintf(text, sizeof text, "launching: player %d of %d, session %08x, settings bits %02x, character %s (%s %d)", d.my_slot + 1, d.count, d.session, bits,
             G.character.name, G.character.cls, G.character.level);
    set_phase(NET2_GAME_LAUNCHING, text);
}

void on_tasks(Ctx* c, bool from_tick) {
    if (from_tick) return;
    Hold hold(net2impl::big_lock());
    if (G.want_choose >= 0 && G.phase == NET2_GAME_TITLE && at_title()) {
        int host = G.want_choose;
        G.want_choose = -1;
        do_choose(c, host != 0);
    } else if (G.phase == NET2_GAME_CHOOSING) {
        // the character screens are a task of the game; when it is gone the choice is made or given up
        if (call(c, fn_0019e5e8, A_SEL_TASK_NAME) == 0) {
            if (rd8(A_CHOSEN) == 1) {
                G.character = read_character(A_PLAYERS);
                // a character just made is a summary until the launch builds its record: the
                // name is in the summary, the level is the first
                if (!G.character.name[0]) {
                    // the record is not built yet: the class word read from it would be the first
                    // class whatever was chosen (seen: an Iksar shown as "Barbarian"); it is told
                    // once the game runs and the record exists
                    net2impl::put(G.character.name, net2impl::clean_label(rdstr(A_QUICK, 31).c_str(), 24));
                    G.character.cls[0] = 0;
                }
                if (G.character.level < 1) G.character.level = 1;
                char text[160];
                snprintf(text, sizeof text, "a character is chosen: %s (%s, level %d)", G.character.name, G.character.cls, G.character.level);
                set_phase(NET2_GAME_CHOSEN, text);
                if (G.session) net2_set_character(G.session, &G.character);
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

void launch_ended(bool failed, const std::string& text) {
    if (net2hook::party8_game) net2hook::party8_game(0);  // a game of five to eight is over: the fours are four again
    if (net2hook::souls_room) net2hook::souls_room(-1);     // the room's game is over: the souls mode is this copy's setting again
    if (net2hook::aim_room) net2hook::aim_room(-1);         // ... and so is aiming by looking
    if (net2hook::cine_room) net2hook::cine_room(-1);       // ... and hold to skip
    G.carrying = false;
    if (G.carrier == &G.own_carrier) G.own_carrier.end();
    G.failed = failed;
    G.level.clear();
    tell_room(nullptr);
    G.asked_ready = false;
    G.title_since = 0;
    set_phase(NET2_GAME_BUSY, text);        // the title screen is taken up again once it has stood for a second
}

void on_after(Ctx* c, bool from_tick) {
    (void)c;
    if (from_tick) return;
    Hold hold(net2impl::big_lock());
    if (G.phase != NET2_GAME_LAUNCHING || rd8(A_LAUNCHING) != 0) return;
    // net_launchUpdate has answered: 2 (launched: the front end has set the network mode and
    // left) or -1 (failed or cancelled: the front end stays)
    if (rd8(A_NETWORK_MODE) == 1) {
        if (G.direct.count > 4) party8_peers(G.direct.count);
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
        launch_ended(true, "the launch did not complete (a player could not be reached, or it was cancelled)");
    }
}

// ---- the souls-style combat mode, a room option (app/soulscombat.h) -------------------------------
// The copy's description says whether it plays with the mode: bit 0x8000 of the word count (no fix set has that
// many words) and, folded into the figure, the mode's numbers.  A joiner takes the host's choice and says so again;
// a copy without the mode says nothing of it, and the room then shows a mismatch and does not start.
void souls_describe(uint32_t& set, uint16_t& words) {
    if (net2hook::souls_wanted && net2hook::souls_wanted() == 1) { words |= 0x8000; if (net2hook::souls_figure) set ^= net2hook::souls_figure(); }
    // aiming by looking (app/fpaim.h), the same way: bit 0x4000
    if (net2hook::aim_wanted && net2hook::aim_wanted() == 1) { words |= 0x4000; if (net2hook::aim_figure) set ^= net2hook::aim_figure(); }
    // hold to skip a cut scene (app/cinematic.h): bit 0x2000, Remastered's
    if (net2hook::cine_wanted && net2hook::cine_wanted() == 1) { words |= 0x2000; if (net2hook::cine_figure) set ^= net2hook::cine_figure(); }
    // a copy that can play a game of five to eight (app/party8.h): bit 0x1000 (the room service's capacity follows it)
    if (net2hook::party8_capable && net2hook::party8_capable() == 1) words |= 0x1000;
}
void follow_souls() {
    if (!G.session) return;
    net2_room_t room;
    net2_room(G.session, &room);
    if (room.state != NET2_ROOM_OPEN || room.my_slot == room.host_slot) return;
    const net2_member* host = nullptr;
    for (int k = 0; k < room.count; k++) if (room.members[k].host) host = &room.members[k];
    if (!host || (host->fix_set == 0 && host->fix_words == 0)) return;
    bool host_on = (host->fix_words & 0x8000) != 0, host_aim = (host->fix_words & 0x4000) != 0;
    bool souls = net2hook::souls_wanted && net2hook::souls_want && host_on != (net2hook::souls_wanted() == 1);
    bool aim = net2hook::aim_wanted && net2hook::aim_want && host_aim != (net2hook::aim_wanted() == 1);
    if (!souls && !aim) return;
    if (souls) net2hook::souls_want(host_on);
    if (aim) net2hook::aim_want(host_aim);
    const rtanet::Info& info = rtanet::info();
    uint32_t set = info.patch_set;
    uint16_t words = (uint16_t)info.patch_words;
    souls_describe(set, words);
    char text[64];
    snprintf(text, sizeof text, "fix=%08x words=%u", set, words);
    net2_set(G.session, "copy", text);
    if (souls) say("the host plays with Hardcore mode %s: so does this copy now", host_on ? "on" : "off");
    if (aim) say("the host plays with aiming by looking %s: so does this copy now", host_aim ? "on" : "off");
}

// ---- the room ------------------------------------------------------------------------------
// A start of the room this program is attached to is taken up: once the routes stand (or
// four seconds have passed: the relay carries what is not straight yet) the launch is asked for.
void follow_room(int64_t now) {
    if (!G.session) return;
    net2_room_t room;
    net2_session_t start;
    net2_room(G.session, &room);
    net2_session(G.session, &start);
    if (room.state != NET2_ROOM_STARTING || !start.valid || start.session == G.launched_session) return;
    if (G.start_seen_ms == 0) G.start_seen_ms = now;
    n2::Carrier* carrier = net2impl::carrier_of(G.session->body);
    if (!carrier) {
        // the mock, or no service: there is nobody to play with
        G.launched_session = start.session;
        G.start_seen_ms = 0;
        say("the room started, but this session has no route to anybody (a mock): no launch");
        tell_room(nullptr);
        return;
    }
    if (G.phase != NET2_GAME_CHOSEN) {
        if (now - G.start_seen_ms < 8000) return;       // the character screens may just be closing
        G.launched_session = start.session;
        G.start_seen_ms = 0;
        say("the room started but no character is chosen on this machine: not launching");
        tell_room(nullptr);
        return;
    }
    if (!carrier->routes_ready() && now - G.start_seen_ms < 4000) return;
    G.launched_session = start.session;
    G.start_seen_ms = 0;
    net2_direct d{};
    d.session = start.session;
    d.count = start.count;
    d.my_slot = start.my_slot;
    d.host_slot = start.host_slot;
    d.options = start.options;
    for (int k = 0; k < start.count && k < NET2_PLAYERS; k++) memcpy(d.players[k].name, start.players[k].name, sizeof d.players[k].name);
    // the souls-style combat mode (app/soulscombat.h) is a room option: every copy has it or none; a room whose copies
    // differ is not launched here (net2_start refuses it at the host; this is for a host that did not ask)
    if (net2hook::souls_room) {
        bool all = room.count > 0, any = false;
        for (int k = 0; k < room.count; k++) { bool on = (room.members[k].fix_words & 0x8000) != 0; all = all && on; any = any || on; }
        if (any && !all) {
            G.launched_session = start.session;
            G.start_seen_ms = 0;
            say("the room started, but its copies do not all have Hardcore mode: not launching");
            tell_room(nullptr);
            return;
        }
        net2hook::souls_room(all ? 1 : 0);
        say("Hardcore mode: %s for this game", all ? "on" : "off");
    }
    // aiming by looking (app/fpaim.h) likewise
    if (net2hook::aim_room) {
        bool all = room.count > 0, any = false;
        for (int k = 0; k < room.count; k++) { bool on = (room.members[k].fix_words & 0x4000) != 0; all = all && on; any = any || on; }
        if (any && !all) {
            G.launched_session = start.session;
            G.start_seen_ms = 0;
            say("the room started, but its copies do not all aim by looking: not launching");
            tell_room(nullptr);
            return;
        }
        net2hook::aim_room(all ? 1 : 0);
        say("aiming by looking: %s for this game", all ? "on" : "off");
    }
    // hold to skip a cut scene (app/cinematic.h) likewise
    if (net2hook::cine_room) {
        bool all = room.count > 0, any = false;
        for (int k = 0; k < room.count; k++) { bool on = (room.members[k].fix_words & 0x2000) != 0; all = all && on; any = any || on; }
        if (any && !all) {
            G.launched_session = start.session;
            G.start_seen_ms = 0;
            say("the room started, but its copies do not all hold to skip (Remastered and Classic mixed): not launching");
            tell_room(nullptr);
            return;
        }
        net2hook::cine_room(all ? 1 : 0);
        say("hold to skip: %s for this game", all ? "on" : "off");
    }
    G.direct = d;
    G.carrier = carrier;
    G.want_launch = true;
    say("the room started: session %08x, %d players, I am player %d; routes: %s", start.session, start.count, start.my_slot + 1, carrier->text().c_str());
}

// The stand-alone program: to a room by itself, the character screens, ready, and for a
// host the start when enough players are in.
void play_by_itself(int64_t now) {
    if (!G.session || !G.own_session) return;
    net2_me_t me;
    net2_room_t room;
    net2_me(G.session, &me);
    net2_room(G.session, &room);
    if (me.link != NET2_LINK_ONLINE || G.want_room.empty()) return;
    bool hosting = G.want_room.compare(0, 4, "host") == 0;
    if (room.state == NET2_ROOM_NONE) {
        if (G.asked_room || G.phase == NET2_GAME_BOOTING) return;
        G.asked_room = true;
        if (hosting) {
            net2_options o{};
            if (const char* level = rt_option("net2-level")) net2impl::put(o.level, level);
            if (const char* difficulty = rt_option("net2-difficulty")) o.difficulty = atoi(difficulty);
            if (const char* size = rt_option("net2-size")) o.max_players = atoi(size);   // a room of up to eight (5..8)
            o.open_to = G.want_room == "host:friends" ? NET2_OPEN_FRIENDS : NET2_OPEN_CODE;
            net2_host(G.session, &o);
        } else if (G.want_room.compare(0, 5, "join:") == 0) net2_join(G.session, G.want_room.c_str() + 5);
        return;
    }
    if (room.state != NET2_ROOM_OPEN) return;
    if (G.phase == NET2_GAME_TITLE && G.want_choose < 0 && (G.launches == 0 || G.again)) net2_game_choose(hosting);
    if (G.phase != NET2_GAME_CHOSEN) return;
    if (room.my_slot != room.host_slot) {
        if (!G.asked_ready) { G.asked_ready = true; net2_ready(G.session, 1); }
        return;
    }
    // every machine of the room must be back from the game before (its phase 0), ready, and enough of them
    bool all_back = true;
    for (int i = 0; i < room.count; i++) all_back &= room.members[i].phase == 0;
    if (G.want_players >= 2 && room.count >= G.want_players && room.all_ready && all_back && now - G.last_start_try > 2000) {
        G.last_start_try = now;
        if (room.mismatch) say("WARNING: starting although the copies differ: %s", room.warning);
        net2_start(G.session);
    }
}

void run_command(const std::string& text);

void poll_command_file(uint64_t number) {
    if (G.command_file.empty() || number % 30 != 0) return;
    FILE* f = fopen(G.command_file.c_str(), "r");
    if (!f) return;
    std::vector<std::string> lines;
    char line[512];
    while (fgets(line, sizeof line, f)) {
        std::string text = line;
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
        if (!text.empty()) lines.push_back(text);
    }
    fclose(f);
    remove(G.command_file.c_str());
    for (const auto& text : lines) run_command(text.compare(0, 5, "net2 ") == 0 ? text.substr(5) : text);
}

void on_blank(uint64_t number) {
    Hold hold(net2impl::big_lock());
    G.blank = number;
    int64_t now = net2impl::steady_ms();
    if (G.session && G.own_session) {
        net2_poll(G.session);
        net2_event e;
        while (net2_next_event(G.session, &e)) {
            if (e.type == NET2_EV_ROOM && e.room[0] && e.room != G.shown_code) {
                G.shown_code = e.room;
                say("ROOM CODE %s - tell it to your friends", e.room);
                if (rtanet::show_code) rtanet::show_code(e.room);
            }
            net2_cli_event(e);
        }
    }
    if (G.carrier) G.carrier->poll(now);
    poll_command_file(number);
    bool front = in_front_end();
    switch (G.phase) {
    case NET2_GAME_BOOTING:
    case NET2_GAME_BUSY:
        // the menu must have stood for a second: it fades in, and a choice made in its first
        // frames finds the character screens' data not loaded yet (seen at boot and again
        // after a game: the screens came up and took no button)
        if (!at_title()) G.title_since = 0;
        else if (G.title_since == 0) G.title_since = number;
        else if (number - G.title_since >= 60) { G.title_seen = true; set_phase(NET2_GAME_TITLE, "the game is at its title screen"); }
        break;
    case NET2_GAME_LOADING:
    case NET2_GAME_RUNNING:
        if (G.phase == NET2_GAME_LOADING && !front && rd8(A_NETWORK_MODE) == 1 && (s32)rd32(A_NET_FRAME) > 0 && rd8(A_LEVEL_NAME) != 0 &&
            rdstr(A_LEVEL_NAME, 20) != "intro") {
            char text[96];
            snprintf(text, sizeof text, "the game runs: level %s", rdstr(A_LEVEL_NAME, 20).c_str());
            set_phase(NET2_GAME_RUNNING, text);
        }
        if (G.phase == NET2_GAME_RUNNING && number % 60 == 0) {
            // presence: the level's name when it changes, the character when it gains a level
            std::string level = rdstr(A_LEVEL_NAME, 20);
            if (level != G.level && !level.empty() && level != "intro") {
                G.level = level;
                tell_room(level.c_str());
                set_phase(NET2_GAME_RUNNING, "the game runs: level " + level);     // the status follows the level
            }
            u32 my_slot = (u32)G.direct.my_slot;
            net2_character mine = read_character(party8_at(A_PLAYERS) + my_slot * PLAYER_SIZE);   // slot 4..7: past the old table (moved.h)
            if (G.session && mine.name[0] && (mine.level != G.character.level || strcmp(mine.name, G.character.name) || strcmp(mine.cls, G.character.cls))) {
                G.character = mine;
                net2_set_character(G.session, &mine);
            }
        }
        if (front && rd8(A_NETWORK_MODE) == 0 && G.blank - G.launch_blank > 120) launch_ended(false, "the game is over: back at the title screen");
        break;
    case NET2_GAME_TITLE:
        if (!front && G.title_seen) set_phase(NET2_GAME_BUSY, "the game is elsewhere (an offline game)");
        break;
    default:
        break;
    }
    follow_souls();
    follow_room(now);
    play_by_itself(now);
}

// ---- the game's datagrams ---------------------------------------------------------------
bool udp_owns(uint16_t game_port) { return G.carrying && G.carrier && game_port == n2::GAME_PORT; }

int32_t udp_send(uint16_t, const uint8_t* data, uint32_t length, uint32_t dest_ip, uint16_t) {
    Hold hold(net2impl::big_lock());
    u32 slot = dest_ip - n2::GAME_NET;
    if (slot < NET2_PLAYERS && G.carrier) G.carrier->send((int)slot, data, length);
    return (int32_t)length;
}

bool udp_receive(uint16_t, uint8_t* buffer, size_t capacity, size_t& size, uint32_t& shown_ip, uint16_t& from_port) {
    Hold hold(net2impl::big_lock());
    if (!G.carrier) return false;
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

void run_command(const std::string& text) {
    std::istringstream words(text);
    std::string verb;
    words >> verb;
    std::string rest;
    std::getline(words, rest);
    while (!rest.empty() && rest[0] == ' ') rest.erase(0, 1);
    unsigned long long frame = G.blank;
    if (verb == "status") {
        net2_game_status_t s;
        net2_game_status(&s);
        printf("[frame %llu] net2: phase=%s launches=%d failed=%d tick=%u players=%d level=%s character=%s;%s;%d fe=%u page=%u text=%s\n", frame,
               phase_name(s.phase).c_str(), s.launches, s.failed, s.tick, s.players, s.level, s.character.name, s.character.cls, s.character.level,
               rd32(A_FE_STATE), rd8(A_SEL_PAGE), s.text);
        printf("[frame %llu] net2: game: in-front-end=%u level=%s fade=%.2f first-pass=%08x running=%08x lobby=%u chosen=%u launching=%u netmode=%u peers=%u\n", frame,
               rd8(A_IN_FRONTEND), rdstr(A_LEVEL_NAME, 12).c_str(), rdf(A_FE_FADE), rd32(A_FE_FIRST_PASS), rd32(A_FE_RUNNING), rd32(A_LOBBY_STATE),
               rd8(A_CHOSEN), rd8(A_LAUNCHING), rd8(A_NETWORK_MODE), rd32(A_NUM_PEERS));
        if (G.carrier) printf("[frame %llu] net2: carrier: %s\n", frame, G.carrier->text().c_str());
    } else if (verb == "choose") {
        int r = net2_game_choose(rest == "host" || rest == "1");
        if (r) printf("[frame %llu] net2: choose: %s\n", frame, net2_error_text(r));
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
        if (r) printf("[frame %llu] net2: direct: %s\n", frame, net2_error_text(r));
    } else if (verb == "launch") {
        int r = G.session ? net2_game_launch(G.session) : NET2_ERR_STATE;
        if (r) printf("[frame %llu] net2: launch: %s\n", frame, net2_error_text(r));
    } else if (G.session) {
        bool quit = false;
        double wait = 0;
        net2_cli_command(G.session, text, quit, wait);
    } else {
        printf("[frame %llu] net2: '%s' needs a session (--opt net2=host | join:CODE, or net2_game_attach)\n", frame, verb.c_str());
    }
    fflush(stdout);
}

void command(const std::string& text, u64 frame) {
    if (text.compare(0, 4, "net2") != 0 || (text.size() > 4 && text[4] != ' ')) {
        if (G.previous_command) G.previous_command(text, frame);
        else rt_note("script: app " + text + " (no application to take it)");
        return;
    }
    Hold hold(net2impl::big_lock());
    run_command(text.size() > 5 ? text.substr(5) : "status");
}

// the controller: while the game boots, cross is pressed for the player (the memory card
// questions and the logos), as the one-step online does; hands off once the front end is up
struct Pad : rta::PadSource {
    void read(unsigned port, uint64_t number, rta::PadState& state) override {
        if (G.inner_pad) G.inner_pad->read(port, number, state);
        else state = script_pad(port);
        if (port != 0 || !G.drive_boot || G.phase != NET2_GAME_BOOTING) return;
        if (in_front_end()) { state = rta::PadState(); return; }
        if (number >= G.boot_next_press) { G.boot_press_until = number + 6; G.boot_next_press = number + 46; }
        state = rta::PadState();
        if (number < G.boot_press_until) state.buttons = rta::PAD_CROSS;
    }
    void rumble(unsigned port, uint8_t small_motor, uint8_t large_motor) override {
        if (G.inner_pad) G.inner_pad->rumble(port, small_motor, large_motor);
    }
} g_pad;

std::string option(const char* key, const char* fallback = "") {
    const char* value = rt_option(key);
    return value ? value : fallback;
}

// The bug report's lines about the room (net2hook::room_describe, app/testerkit.h): the code, the state and every
// member's copy - slot, host or this machine, fix set and word count, arithmetic, route and round trip.  No names.
// The lock is only tried: the report never waits for the network.
void room_describe(char* out, size_t size) {
    out[0] = 0;
    std::unique_lock<std::recursive_mutex> hold(net2impl::big_lock(), std::try_to_lock);
    if (!hold.owns_lock()) { snprintf(out, size, "online = (the room was busy)\n"); return; }
    if (!G.session) return;
    net2_room_t room;
    net2_room(G.session, &room);
    static const char* STATES[] = {"none", "joining", "open", "starting", "in game"};
    static const char* ROUTES[] = {"none", "trying", "direct", "relay", "self"};
    if (room.state == NET2_ROOM_NONE) { snprintf(out, size, "online = a session, no room\n"); return; }
    int n = snprintf(out, size, "online = room %s, %s, %d players, this machine slot %d, host slot %d, game phase %s\n", room.code,
                     room.state >= 0 && room.state <= 4 ? STATES[room.state] : "?", room.count, room.my_slot, room.host_slot, phase_name(G.phase).c_str());
    for (int k = 0; k < room.count && n > 0 && n < (int)size; k++) {
        const net2_member& m = room.members[k];
        n += snprintf(out + n, size - n, "peer.%d = %s%sfix %08x words %u arith %u/%u route %s rtt %d ms phase %d\n", m.slot, m.host ? "host, " : "",
                      m.me ? "this machine, " : "", m.fix_set, m.fix_words, m.arith_can, m.arith_does, m.route >= 0 && m.route <= 4 ? ROUTES[m.route] : "?",
                      m.rtt_ms, m.phase);
    }
    if (room.mismatch && n > 0 && n < (int)size) snprintf(out + n, size - n, "online_warning = %s\n", room.warning);
}

void install() {
    if (G.installed) return;
    G.installed = true;
    net2hook::room_describe = room_describe;
    G.previous_command = script_app_command;
    script_app_command = command;
    if (const char* file = rt_option("net2-log")) G.log = fopen(file, "w");
    G.command_file = option("net2-commands");
    G.want_room = option("net2");
    // cross through the boot is pressed for a player who asked for a room; a test may ask for it alone
    G.drive_boot = option("net2-boot", G.want_room.empty() ? "0" : "1") == "1";
    if (G.drive_boot) {
        G.inner_pad = g_hooks.pad;
        g_hooks.pad = &g_pad;
    }
    if (G.want_room.empty()) return;
    // the stand-alone program's own session
    const rtanet::Info& info = rtanet::info();
    static std::string data, service, name, build;
    data = option("net2-data", info.data_dir.c_str());
    service = option("net2-service");
    name = option("net2-name");
    net2_config config{};
    config.struct_size = sizeof config;
    config.data_dir = data.c_str();
    config.service = service.empty() ? nullptr : service.c_str();
    config.name = name.empty() ? nullptr : name.c_str();
    config.fix_set = info.patch_set;
    config.fix_words = (uint16_t)info.patch_words;
    souls_describe(config.fix_set, config.fix_words);
    config.arith_does = (uint8_t)rtanet::arithmetic();
    config.arith_can = config.arith_does ? 2 : 1;
    config.build = "native";
    config.local_only = option("net-local-only") == "1";
    G.session = net2_open(&config);
    G.own_session = true;
    G.again = option("net2-again") == "1";
    G.want_players = atoi(option("net2-players", "2").c_str());
    std::string relay = option("net2-relay");
    if (!relay.empty()) net2_set(G.session, "relay", relay.c_str());
    std::string bind = option("net2-bind");
    if (!bind.empty()) net2_set(G.session, "bind", bind.c_str());
    say("going to a room by itself: %s (fix set %08x, %u words; described as %08x / %04x)", G.want_room.c_str(), info.patch_set, info.patch_words,
        config.fix_set, config.fix_words);
}

void first_blank(uint64_t number) {
    {
        Hold hold(net2impl::big_lock());
        install();
    }
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
    Hold hold(net2impl::big_lock());
    *out = net2_game_status_t{};
    out->phase = G.phase;
    out->launches = G.launches;
    out->failed = G.failed;
    net2impl::put(out->text, G.text);
    // what the game's own menu would let a host take (options_get4f8f38Level 0x1ec448)
    u32 flags = rd32(A_SAVED_CONFIG);
    out->difficulty_unlocked = (flags & 0x40) ? 5 : (flags & 0x20) ? 4 : (flags & 0x11) ? 3 : (flags & 0xc) ? 2 : 1;
    if (G.phase >= NET2_GAME_CHOSEN && G.phase <= NET2_GAME_RUNNING) out->character = G.character;
    if (G.phase == NET2_GAME_RUNNING) {
        net2impl::put(out->level, rdstr(A_LEVEL_NAME, 20));
        out->tick = rd32(A_NET_FRAME);
        u32 peers = rd32(A_NUM_PEERS);
        for (u32 k = 0; k < peers && k < NET2_PLAYERS; k++)
            if (rd8(party8_at(A_PEERS) + k * PEER_SIZE + PEER_DROPPED) == 0) out->players++;
    }
}

int net2_game_choose(int as_host) {
    Hold hold(net2impl::big_lock());
    if (G.phase == NET2_GAME_CHOSEN) return NET2_OK;
    if (G.phase != NET2_GAME_TITLE && G.phase != NET2_GAME_BOOTING) return NET2_ERR_STATE;
    G.want_choose = as_host ? 1 : 0;
    return NET2_OK;
}

int net2_game_launch_direct(const net2_direct* description) {
    if (!description) return NET2_ERR_ARGUMENT;
    Hold hold(net2impl::big_lock());
    const net2_direct& d = *description;
    if (d.count < 2 || d.count > NET2_PLAYERS || d.my_slot < 0 || d.my_slot >= d.count) return NET2_ERR_ARGUMENT;
    if (G.phase != NET2_GAME_CHOSEN) return NET2_ERR_STATE;
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

void net2_game_attach(net2* n) {
    Hold hold(net2impl::big_lock());
    if (G.session && G.own_session && G.session != n) net2_close(G.session);
    G.session = n;
    G.own_session = false;
}

int net2_game_launch(net2* n) {
    Hold hold(net2impl::big_lock());
    if (!n) return NET2_ERR_ARGUMENT;
    if (G.session != n) { G.session = n; G.own_session = false; }
    net2_session_t start;
    net2_session(n, &start);
    if (!start.valid) return NET2_ERR_STATE;
    if (start.session == G.launched_session) G.launched_session = 0;       // asked for by hand: once more
    return NET2_OK;
}

int net2_game_stop(void) {
    // Not built: a launch under way ends by the game's own time-out or its circle button, a
    // running game by the pause menu's "Exit Game".
    return NET2_ERR_STATE;
}

}  // extern "C"
