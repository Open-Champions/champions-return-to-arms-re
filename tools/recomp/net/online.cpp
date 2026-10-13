// online.cpp - "one-step online" in the native build.
//
// The emulator-based application presses its own way from power-on to the lobby
// (tools/play-net/src/RtaOnline.cpp: it watches the game's own state in memory and presses
// one button at a time; the account is the application's business - a player name asked
// once, a random password kept per server in <data>/online-login, mode 0600, never shown
// or logged).  That file depends on neither the emulator nor Qt, and the game it watches is
// the same code here, so it is linked as it is.  This file is what joins it to the runtime:
//
//   - it stands in front of the controller source (rta::Hooks::pad, or the script when an
//     application set none): once per vertical blank the driver looks at memory, and while
//     it is pressing, the game sees its buttons and nothing else;
//   - options (netdrv.h): online=lobby|host[:CODE]|join:CODE[+choose], online-name, online-person;
//   - script commands, for tests (the runtime's "app <text>"):
//       app online start lobby|host[:CODE]|join:CODE[+choose]
//       app online stop | app online name NAME | app online       (the last prints the report)
//       app net peers | app net drop | app net sockets | app net arith | app net stall MS
//       app online sheet info|type TEXT|press N|picture FILE   (the window's name question)
//   - a name is asked for on the terminal unless an application took the question over
//     (rtanet::ask_name); the code of a hosted game is printed, or handed to show_code.
#include "netdrv.h"

#include "rt.h"
#include "../../play-net/src/RtaOnline.h"
#include "../../play-net/src/RtaNet.h"

#include <chrono>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <mutex>
#include <sstream>
#include <thread>
#include <vector>
#include <unistd.h>

// RtaOnline.cpp (linked as it is) tells the emulator application's network layer once per
// vertical blank whether the game is in a game's room, for that layer's hold of a peer's
// disconnect (tools/play-net/src/RtaNet.cpp, since 2026-10-13).  That layer is not part of
// a native build: the driver here has the same hold and reads the lobby state word itself
// (netdrv.cpp, udp_receive), so there is nothing to be told.
void Rta::CNet::NoteGame(bool) {}

namespace rtanet {
void (*ask_name)(const std::string& why) = nullptr;
void (*show_code)(const std::string& code) = nullptr;
void (*show_note)(const std::string& note) = nullptr;
void (*show_warning)(const std::string& text) = nullptr;
void (*window_test)(const std::string& text) = nullptr;
}

namespace {

Rta::COnline g_online;
bool g_installed = false, g_person = true;
rta::PadSource* g_inner = nullptr;
std::string g_note;
void (*g_previous_command)(const std::string&, u64) = nullptr;
void (*g_previous_finish)() = nullptr;

// "", "lobby", "host", "host:CODE" or "join:CODE"; "+choose" after host or join: the
// player chooses the character although the one used last is known
bool parse_mode(const std::string& given, Rta::COnline::Goal& goal, std::string& code, bool& choose, std::string& error) {
    goal = Rta::COnline::Goal::Lobby;
    code.clear();
    choose = false;
    std::string mode = given;
    if (mode.size() > 7 && mode.compare(mode.size() - 7, 7, "+choose") == 0) { choose = true; mode.erase(mode.size() - 7); }
    if (mode.empty() || mode == "lobby") return true;
    std::string word = mode.substr(0, mode.find(':'));
    std::string rest = mode.find(':') == std::string::npos ? "" : mode.substr(mode.find(':') + 1);
    for (auto& ch : rest) ch = (char)toupper((unsigned char)ch);
    if (word == "host") { goal = Rta::COnline::Goal::Host; code = rest.empty() ? Rta::COnline::MakeCode() : rest; }
    else if (word == "join") { goal = Rta::COnline::Goal::Join; code = rest; }
    else { error = "'" + given + "' is not lobby, host or join:CODE (host and join may end in +choose)"; return false; }
    error = Rta::COnline::CheckCode(code);
    return error.empty();
}

bool start(const std::string& mode, bool power_on) {
    Rta::COnline::Goal goal;
    std::string code, error;
    bool choose = false;
    if (!parse_mode(mode, goal, code, choose, error)) { rtanet::say("online: %s", error.c_str()); return false; }
    if (rtanet::info().server_ip == 0) { rtanet::say("online: there is no lobby server to go to"); return false; }
    g_online.Start(goal, code, power_on, choose);
    if (goal == Rta::COnline::Goal::Host) {
        rtanet::say("online: hosting a game with the code %s", code.c_str());
        if (rtanet::show_code) rtanet::show_code(code);
    }
    if (goal == Rta::COnline::Goal::Join) rtanet::say("online: joining the game with the code %s", code.c_str());
    return true;
}

void terminal_ask(const std::string& why) {
    if (!g_person || !isatty(STDIN_FILENO)) {
        rtanet::say("online: a player name is needed and nobody can be asked: give --opt online-name=NAME");
        return;
    }
    std::thread([why]() {
        std::string wrong = why;
        for (;;) {
            if (!wrong.empty()) printf("%s\n", wrong.c_str());
            printf("Player name for playing online (3 to 15 letters and digits; empty: not now): ");
            fflush(stdout);
            std::string line;
            if (!std::getline(std::cin, line) || line.empty()) { g_online.DeclineName(); return; }
            wrong = Rta::COnline::CheckName(line);
            if (wrong.empty()) { g_online.GiveName(line); return; }
        }
    }).detach();
}

std::string peers_text() {
    std::ostringstream text;
    const rtanet::Info& I = rtanet::info();
    char figure[64];
    snprintf(figure, sizeof(figure), "set=%08x words=%u arith=%s", I.patch_set, I.patch_words, rtanet::arithmetic() ? "browser" : "console");
    text << figure;
    for (const auto& peer : rtanet::peers()) {
        char one[200];
        const char* arith = !peer.arith_known ? "?" : peer.arith_does ? "browser" : "console";
        if (peer.set_known) snprintf(one, sizeof(one), " [%s:%u set=%08x%s arith=%s heard_ms=%lld silent_ms=%lld]", rtanet::ip_text(peer.ip).c_str(), peer.port, peer.patch_set,
                                     peer.patch_set == I.patch_set ? "" : " DIFFERENT", arith, (long long)peer.heard_ms, (long long)peer.silent_ms);
        else snprintf(one, sizeof(one), " [%s:%u set=? arith=%s heard_ms=%lld silent_ms=%lld]", rtanet::ip_text(peer.ip).c_str(), peer.port, arith, (long long)peer.heard_ms, (long long)peer.silent_ms);
        text << one;
    }
    return text.str();
}

void command(const std::string& text, u64 frame) {
    std::istringstream words(text);
    std::string first, second, third;
    words >> first >> second >> third;
    if (first == "online") {
        if (second == "start") start(third, false);
        else if (second == "stop") g_online.Stop("stopped by the script");
        else if (second == "name") { std::string wrong = Rta::COnline::CheckName(third); if (wrong.empty()) g_online.GiveName(third); else rtanet::say("online: %s", wrong.c_str()); }
        else if (second == "sheet") {       // tests: the window's question (online_mac.mm)
            size_t at = text.find("sheet");
            if (rtanet::window_test) rtanet::window_test(text.substr(at + 5));
            else rtanet::say("online: this program has no window question to test");
        }
        else if (second == "menu") {        // tests: the window's Online menu (online_mac.mm): menu info | menu click N [TEXT]
            if (rtanet::window_test) rtanet::window_test(text.substr(text.find("menu")));
            else rtanet::say("online: this program has no menu to test");
        }
        else printf("[frame %llu] online: %s saved_login=%d\n", (unsigned long long)frame, g_online.Report().c_str(), g_online.HasLogin() ? 1 : 0);
        return;
    }
    if (first == "net") {
        if (second == "peers") printf("[frame %llu] peers: %s\n", (unsigned long long)frame, peers_text().c_str());
        else if (second == "drop") rtanet::drop_tcp();
        else if (second == "stall") {       // tests: this machine stands still (a hitch at the wrong moment)
            int ms = atoi(third.c_str());
            printf("[frame %llu] standing still for %d ms\n", (unsigned long long)frame, ms);
            fflush(stdout);
            if (ms > 0 && ms <= 20000) std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        }
        else if (second == "arith") printf("[frame %llu] arithmetic: %s\n", (unsigned long long)frame, rtanet::arithmetic_text().c_str());
        else if (second == "sockets") printf("[frame %llu] %s\n", (unsigned long long)frame, rtanet::sockets_text().c_str());
        return;
    }
    if (g_previous_command) g_previous_command(text, frame);
    else rt_note("script: app " + text + " (no application to take it)");
}

void finish() {
    const rtanet::Info& I = rtanet::info();
    printf("net: %llu TCP connections (%llu bytes out, %llu in); UDP %llu to the server, %llu from it, %llu to other players, %llu from them, %llu not carried\n",
           (unsigned long long)I.tcp_connections, (unsigned long long)I.tcp_out, (unsigned long long)I.tcp_in, (unsigned long long)I.udp_to_server,
           (unsigned long long)I.udp_from_server, (unsigned long long)I.udp_to_peers, (unsigned long long)I.udp_from_peers, (unsigned long long)I.dropped);
    printf("net: peers: %s\n", peers_text().c_str());
    printf("online: %s\n", g_online.Report().c_str());
    if (g_previous_finish) g_previous_finish();
}

// front end, lobby state 2 (the network window 0x506148), no message box, and the list of
// settings up (window state 3 with a setting) or still being read (state 0)
bool config_offered(const uint8_t* ram) {
    auto word = [ram](u32 address) { u32 value = 0; address &= 0x1FFFFFFF; if (address && address <= RAM_SIZE - 4) memcpy(&value, ram + address, 4); return value; };
    if (ram[0x41B510] != 1 || memcmp(ram + 0x41B721, "intro", 6) != 0) return false;
    if (word(0x4F6B78) != 10 || word(0x506160) != 2) return false;
    u32 window = word(0x506148);
    if (!window || word(window + 0xD88) != 0) return false;
    u32 state = word(window + 0xDB4);
    return state == 0 || (state == 3 && (s32)word(window + 0x4354) > 0);
}

// tests: "app ..." lines for the network from a file (online-commands=FILE), looked for twice
// a second - a way in for a test that drives the window program by its control socket, whose
// own "app" command goes to the window program alone
std::mutex g_request_lock;
std::vector<std::string> g_requests;
std::string g_command_file;
void poll_command_file(uint64_t number) {
    if (g_command_file.empty() || number % 30 != 0) return;
    FILE* f = fopen(g_command_file.c_str(), "r");
    if (!f) return;
    std::vector<std::string> lines;
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        std::string text = line;
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
        if (!text.empty()) lines.push_back(text);
    }
    fclose(f);
    remove(g_command_file.c_str());
    for (const auto& text : lines) { command(text, number); fflush(stdout); }
}

struct Pad : rta::PadSource {
    void read(unsigned port, uint64_t number, rta::PadState& state) override {
        if (g_inner) g_inner->read(port, number, state);
        else state = script_pad(port);
        if (port != 0) return;
        rtanet::per_blank(number);
        poll_command_file(number);
        {
            // what the window's menu asked for since the last blank
            std::vector<std::string> lines;
            { std::lock_guard<std::mutex> hold(g_request_lock); lines.swap(g_requests); }
            for (const auto& text : lines) { command(text, number); fflush(stdout); }
        }
        g_online.SetPlayerButtons(state.buttons);
        g_online.Tick(rta::memory(), RAM_SIZE, true);
        if (g_online.Driving()) {
            // the application is pressing its way to the lobby: the game sees its buttons
            // and nothing else, both sticks at rest
            state = rta::PadState();
            state.buttons = (uint16_t)g_online.Buttons();
        }
        // The game's network screen offers "Config" (triangle) while it lists the setting:
        // that restarts the machine into Sony's network settings program on the disc, a
        // second executable this build does not contain - and there is nothing to set (the
        // host's network is used as it is, and the setting is written when it is missing).
        // The emulator-based application does not pass the button on there either.
        if (config_offered(rta::memory())) state.buttons &= (uint16_t)~rta::PAD_TRIANGLE;
        std::string note = g_online.Note();
        if (note != g_note) {
            g_note = note;
            if (rtanet::show_note) rtanet::show_note(note);
        }
    }
    void rumble(unsigned port, uint8_t small_motor, uint8_t large_motor) override {
        if (g_inner) g_inner->rumble(port, small_motor, large_motor);
    }
} g_pad;

}  // namespace

namespace rtanet {

void ask_name_on_terminal(const std::string& why) { terminal_ask(why); }
void request(const std::string& line) { std::lock_guard<std::mutex> hold(g_request_lock); g_requests.push_back(line); }
void give_name(const std::string& name) { g_online.GiveName(name); }
void decline_name() { g_online.DeclineName(); }
std::string check_name(const std::string& name) { return Rta::COnline::CheckName(name); }
std::string online_note() { return g_online.Note(); }
std::string online_report() { return g_online.Report(); }

void online_install() {
    if (g_installed) return;
    g_installed = true;
    const Info& I = info();
    const char* value = rt_option("online-person");
    g_person = !(value && std::string(value) == "0");

    Rta::COnline::Setup setup;
    setup.file = I.data_dir + "/online-login";
    setup.characterFile = I.data_dir + "/online-character";
    setup.server = I.server_key;
    setup.serverText = I.server_text.empty() ? "(none)" : I.server_text;
    setup.personPresent = g_person;
    setup.log = [](const std::string& line) { rtanet::say("%s", line.c_str()); };
    setup.askName = [](const std::string& why) { if (rtanet::ask_name) rtanet::ask_name(why); else terminal_ask(why); };
    setup.cross = rta::PAD_CROSS;
    setup.circle = rta::PAD_CIRCLE;
    setup.triangle = rta::PAD_TRIANGLE;
    setup.square = rta::PAD_SQUARE;
    setup.up = rta::PAD_UP;
    setup.down = rta::PAD_DOWN;
    setup.left = rta::PAD_LEFT;
    setup.right = rta::PAD_RIGHT;
    setup.l1 = rta::PAD_L1;
    setup.r1 = rta::PAD_R1;
    setup.start = rta::PAD_START;
    g_online.Configure(setup);
    value = rt_option("online-name");
    if (value && *value) {
        std::vector<std::string> names;
        std::istringstream list(value);
        std::string name;
        while (std::getline(list, name, ',')) if (!name.empty()) names.push_back(name);
        g_online.QueueNames(names);
    }
    g_online.OnExecutable(true);

    g_inner = g_hooks.pad;
    g_hooks.pad = &g_pad;
    g_previous_command = script_app_command;
    script_app_command = command;
    g_previous_finish = rt_at_finish;
    rt_at_finish = finish;

    value = rt_option("online-commands");
    if (value) g_command_file = value;

    value = rt_option("online");
    if (value) start(value, true);
}

}  // namespace rtanet
