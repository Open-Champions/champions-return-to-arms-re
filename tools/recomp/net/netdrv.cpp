// netdrv.cpp - the native build's network: Sony's network library answered at its entries.
//
// On a console the game's netcode, its lobby client (SOEGamesAPI over TCP) and its peer
// library (SOE UdpLibrary) call Sony's libnet, which carries every call by RPC to a TCP/IP
// stack on the I/O processor.  The native build has no I/O processor.  This file supplies
// the library's entries themselves (tools/recomp/net/hle-online.txt) on host sockets, so
// everything above them - framing, encryption, the peer handshake, lockstep - is the
// game's own translated code and sends the bytes it always sent.  Below them it does what
// the emulator-based application's network does under the game's stack
// (tools/play-net/src/RtaNet.cpp), rule for rule:
//
//   - the machine has a made-up own-network address (198.19.x.y, made once and kept);
//   - one host name is answered, the lobby's, with the server's address; nothing else is
//     looked up;
//   - a TCP connection to the server's address (or to an address the server's gateway
//     names for its lobby when the server is on this computer or a private network) is a
//     host connection to the server; other connections are made as they are;
//   - one host UDP socket per UDP port of the game, with the same number when it is free,
//     kept for the whole run: whatever the game sends from that port leaves from that
//     socket and whatever arrives there is the port's, so the lobby server sees the pair
//     the other players have to send to (hole punching), and the netcode that takes the
//     port over at launch keeps the path the peer handshake opened;
//   - datagrams for made-up, broadcast or loop-back addresses are not carried; the
//     server's address on a port that is not the server's is another copy on the server's
//     computer and is reached through the loop-back interface;
//   - every other player heard from is told this copy's patch set (a keep-alive of the
//     game's own UDP library with a mark and the figure after it), and theirs is taken
//     out before the game sees it.
//
// The network configuration (eznetcnf / eznetctl) is answered here too: the setting is
// read from the memory card directory, in the files Sony's set-up program writes and the
// emulator-based application writes (written here when missing), and the interface is
// "up" a moment after the game brings it up.
//
// Nothing here waits: every entry answers at once (the game asks for 0 or 1 ms), with
// libnet's -500 for "not yet".  Options: netdrv.h.  What was run: docs/issues/native-online.md.
#include "netdrv.h"
#include "sock.h"       // the host's sockets: BSD or Winsock (first: on Windows it brings <winsock2.h>, which wants to come before the rest)

#include "rt.h"
#include "funcs.h"
#include "../net2/hooks.h"     // tools/recomp/net2: a game started from a room of our own (docs/issues/native-rendezvous.md)

#include <algorithm>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <thread>

unsigned recomp_patches(const u32 (**words)[2]);
unsigned recomp_patch_set_words();     // rt/runtime.cpp (weak: ~0, a translation older than --extra-pnach)

namespace fs = std::filesystem;

namespace {

// libnet's answers (the game tests the sign, and -500 by value)
const s32 E_NOT_YET = -500;         // nothing waiting / not connected yet (a time-out)
const s32 E_FAILED = -1;            // refused, reset, gone
// socket types of the 0x40-byte parameter block (word 0)
enum { T_DGRAM = 0, T_CONNECT = 1, T_LISTEN = 2, T_RAW = 3 };
// poll bits
enum { P_IN = 1, P_OUT = 4, P_ERR = 8, P_HUP = 0x10 };

const u8 PATCH_SET_MARK[] = {0x00, 0x06, 'R', 'T', 'A', 's', 'e', 't', '1'};
const size_t PATCH_SET_SIZE = sizeof(PATCH_SET_MARK) + 6;
const int64_t PATCH_SET_TIMES[] = {300, 1500, 4000, 9000};     // milliseconds after the first datagram
const u8 ARITH_MARK[] = {0x00, 0x06, 'R', 'T', 'A', 'a', 'r', 'i', '1'};
const size_t ARITH_SIZE = sizeof(ARITH_MARK) + 2;

const u32 MADE_UP_NET = 0xC6120000, MADE_UP_MASK = 0xFFFE0000;      // 198.18.0.0/15, set aside for test networks
const u32 LOOPBACK = 0x7F000001;                                    // 127.0.0.1
const u32 GUEST_SERVER_NAME = 0xC6120002;                           // 198.18.0.2: the server, when this computer has no address

struct Conn {
    int type = T_DGRAM;
    u16 game_port = 0;              // datagram: the game's UDP port
    sock::Handle fd = sock::NONE;   // stream: the host connection
    u32 dest_ip = 0, real_ip = 0;
    u16 dest_port = 0;
    bool connecting = false, connected = false, eof = false, failed = false;
    bool gateway = false, gateway_parsed = false;
    std::vector<u8> head;           // the first bytes from a gateway, for its reply
    u64 out = 0, in = 0;
};
struct Held { u64 due_field = 0; std::vector<u8> data; u32 shown_ip = 0; u16 from_port = 0; };
struct UdpHost { sock::Handle fd = sock::NONE; u16 host_port = 0; std::deque<Held> held; };
struct PeerState {
    int64_t first_heard = 0, last_heard = 0;
    u16 local_port = 0;
    int told = 0;
    bool set_known = false, warned = false;
    u32 patch_set = 0;
    u16 patch_words = 0;
    bool arith_known = false;
    u8 arith_can = 0, arith_does = 0;   // as told: bit 0 the console's, bit 1 the browser's; 0 the console's, 1 the browser's
    int arith_warned = -1;              // the arithmetic of ours the warning was given for
};
// Which arithmetic this copy computes with (docs/issues/mixed-arithmetic.md): the console's
// (results rounded toward zero, tiny numbers taken as zero - what the other builds call
// Play!'s own) or a browser's (to nearest, tiny numbers kept).
enum { ARITH_CONSOLE = 0, ARITH_BROWSER = 1 };
struct Arith {
    bool switchable = false;            // this build can put its processor in either state
    int fixed = -1;                     // net-arith=console|browser: -1 is auto
    int now = ARITH_CONSOLE;
    u8 can() const { return fixed == ARITH_CONSOLE ? 1 : fixed == ARITH_BROWSER ? 2 : switchable ? 3 : 1; }
} A;

struct Driver {
    bool ready = false;
    rtanet::Info info;
    std::set<u32> aliases;
    std::string lobby_name = "con.soegames.net";
    std::set<u16> server_udp_ports = {10101};
    u16 gateway_lo = 40800, gateway_hi = 40817;
    int port_shift = 0;                 // tests: a second server instance on this computer, its ports the usual ones plus this
    bool learn_alias = true, bind_game_ports = true, tell_set = true, local_only = false, log_all = false, write_netcnf = true;
    bool hold_disconnects = true;       // a peer's disconnect is shown to a game in a room half a second late (udp_receive)
    u64 held_total = 0;
    double pace = 59.94;
    std::set<u32> own_addresses;
    FILE* log_file = nullptr;
    std::chrono::steady_clock::time_point start;
    std::map<int, Conn> conns;
    int next_id = 1;
    std::map<u16, UdpHost> udp;
    std::map<u64, u32> seen_as;         // real (address, port) -> the address the game used for it
    std::map<u32, u32> seen_as_any;     // the same by address alone, the latest
    std::set<u64> noted;
    std::map<u64, PeerState> peer;
    // the interface, as eznetctl would report it
    bool if_up = false;
    u64 if_up_field = 0;
    int pending_event = -1;
    // the tick log of a test run
    FILE* tick_log = nullptr;
    std::vector<std::pair<std::string, std::string>> tick_exprs;       // expression, type
    u64 ticks = 0;
    std::multimap<u32, std::string> tick_actions;       // lockstep tick -> "poke <expr> <text>" | "echo <text>" | "quit"
    // pacing of a program without a window
    std::chrono::steady_clock::time_point pace_next;
    bool pace_started = false;
    u64 unanswered = 0;
} D;

int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - D.start).count();
}
u64 key(u32 ip, u16 port) { return ((u64)ip << 16) | port; }
bool is_loopback(u32 ip) { return (ip >> 24) == 127; }
bool is_private(u32 ip) {
    return (ip >> 24) == 10 || (ip >> 20) == 0xAC1 || (ip >> 16) == 0xC0A8 || (ip >> 16) == 0xA9FE || is_loopback(ip);
}
bool is_own(u32 ip) { return is_loopback(ip) || D.own_addresses.count(ip) != 0; }
bool is_server(u32 guest_dest) { return guest_dest == D.info.guest_server_ip || D.aliases.count(guest_dest) != 0; }
bool parse_ip(const std::string& text, u32& out) {
    unsigned a, b, c, d;
    char tail;
    if (sscanf(text.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) != 4 || a > 255 || b > 255 || c > 255 || d > 255) return false;
    out = (a << 24) | (b << 16) | (c << 8) | d;
    return true;
}

void vlog(bool terminal, const char* format, va_list args) {
    char line[1024];
    vsnprintf(line, sizeof(line), format, args);
    if (D.log_file) { fprintf(D.log_file, "%8lld %s\n", (long long)now_ms(), line); fflush(D.log_file); }
    if (terminal) { printf("[net] %s\n", line); fflush(stdout); }
}

// ---- the arithmetic ----------------------------------------------------------------------
// The translated code computes with the host's own instructions and the runtime puts every
// game thread's processor in the console's state when the thread starts (rt/runtime.cpp,
// thread_main; rt/fpu.h).  A browser copy cannot do that, and the emulator-based application
// changes to the browser's state when one is in the room (FpUtils::SetArithmetic).  This
// build does the same thing in the same place: the thread that runs the game's ticks is put
// in line at every call of the task loop and at every vertical blank.  Only where the
// processor has the two modes and nothing does them in software.
#if defined(__aarch64__) && !defined(RTA_SOFT_RZ) && !defined(__EMSCRIPTEN__)
const bool ARITH_SWITCHABLE = true;
inline void thread_arith(int mode) {
    uint64_t fpcr;
    __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
    uint64_t wanted = fpcr & ~((3ull << 22) | (1ull << 24));           // to nearest, tiny numbers kept
    if (mode == ARITH_CONSOLE) wanted |= (3ull << 22) | (1ull << 24);   // toward zero, flush-to-zero
    if (wanted != fpcr) __asm__ __volatile__("msr fpcr, %0" : : "r"(wanted));
}
#else
const bool ARITH_SWITCHABLE = false;
inline void thread_arith(int) {}
#endif
const char* arith_name(int mode) { return mode == ARITH_BROWSER ? "browser arithmetic" : "the console's arithmetic"; }
const char* arith_can_name(u8 can) { return can == 3 ? "both" : can == 2 ? "the browser's" : "the console's"; }

// ---- guest memory -----------------------------------------------------------------------
u32 rd32(u32 pointer) { u32 a = guest_addr(pointer, 4), v = 0; if (a != ~0u) memcpy(&v, g_ram + a, 4); return v; }
u16 rd16(u32 pointer) { u32 a = guest_addr(pointer, 2); u16 v = 0; if (a != ~0u) memcpy(&v, g_ram + a, 2); return v; }
void wr32(u32 pointer, u32 v) { u32 a = guest_addr(pointer, 4); if (pointer && a != ~0u) memcpy(g_ram + a, &v, 4); }
void wr16(u32 pointer, u16 v) { u32 a = guest_addr(pointer, 2); if (pointer && a != ~0u) memcpy(g_ram + a, &v, 2); }
u8* gptr(u32 pointer, u32 size) { u32 a = pointer ? guest_addr(pointer, size) : ~0u; return a == ~0u ? nullptr : g_ram + a; }
std::string gstr(u32 pointer, u32 limit = 255) {
    std::string text;
    for (u32 i = 0; i < limit; i++) { u8* p = gptr(pointer + i, 1); if (!p || !*p) break; text += (char)*p; }
    return text;
}
// libnet's 16-byte address as the game holds it: a zero word, then the IPv4 address as one
// 32-bit word of the machine (192.168.1.2 is 0xC0A80102, so the bytes in memory run
// backwards).  The peer library converts through text both ways, but the netcode writes
// the word itself (seen: with the bytes read in network order its launch datagrams went
// to the reversed address).
u32 block_ip(u32 pointer) { return rd32(pointer + 4); }
void block_set(u32 pointer, u32 ip) {
    if (u8* p = gptr(pointer, 16)) { memset(p, 0, 16); memcpy(p + 4, &ip, 4); }
}
// arguments 1-8 are in $a0-$a3, $t0-$t3
u32 arg(Ctx* c, int index) { return (u32)c->r[4 + index]; }
void answer(Ctx* c, s32 result) { c->r[2] = (u64)(s64)result; }

// ---- this computer ------------------------------------------------------------------------
// (the sockets themselves are in sock.h)
void list_own_addresses() { sock::own_addresses(D.own_addresses); }
bool resolve_host(const std::string& name, u32& out) {
    if (parse_ip(name, out)) return true;
    return sock::resolve(name, out);
}

// ---- the network setting on the memory card ------------------------------------------------
// What Sony's set-up program saves for "Ethernet adaptor, automatic address, automatic
// DNS", as tools/play-net/src/Rta.cpp writes it: an index, one combination file and two
// setting files whose text is scrambled (each 16-bit word rotated left by 6, 3, 3, ...
// bits and inverted; the key comes from the console's identification number, and the
// emulator's is the one these files are written for, so a card directory can go back and
// forth between the two builds).
std::vector<u8> netcnf_scramble(const std::string& text) {
    static const unsigned key3[3] = {6, 3, 3};
    std::vector<u8> out;
    size_t index = 0;
    for (size_t i = 0; i + 1 < text.size(); i += 2, index++) {
        unsigned word = (u8)text[i] | ((u8)text[i + 1] << 8), shift = key3[index % 3];
        word = (((word << shift) | (word >> (16 - shift))) & 0xFFFF) ^ 0xFFFF;
        out.push_back((u8)word);
        out.push_back((u8)(word >> 8));
    }
    if (text.size() & 1) {
        unsigned byte = (u8)text.back(), shift = key3[index % 3];
        byte = ((byte << shift) | (byte >> (8 - shift))) & 0xFF;
        out.push_back((u8)(byte ^ 0xFF));
    }
    return out;
}
bool write_file(const fs::path& path, const void* data, size_t size) {
    FILE* f = fopen(path.string().c_str(), "wb");
    if (!f) return false;
    bool ok = fwrite(data, 1, size, f) == size;
    fclose(f);
    return ok;
}
// 0: there already; 1: written; -1: could not
int write_netcnf(const fs::path& card) {
    fs::path dir = card / "BWNETCNF";
    std::error_code ec;
    if (fs::exists(dir / "BWNETCNF", ec)) return 0;
    fs::create_directories(dir, ec);
    const std::string header = "# <Sony Computer Entertainment Inc.>\n\n";
    const std::string index = "0,1,net000.cnf,Combination1\n1,1,ifc000.dat,Setting 1\n2,1,dev000.dat,SCE/Ethernet (Network Adaptor)\n";
    const std::string combination = header + "interface \"ifc000.dat + dev000.dat\" \"ifc000.dat\" \"dev000.dat\"\n";
    auto interface = netcnf_scramble(header + "type nic\ndhcp\n");
    auto device = netcnf_scramble(header + "type nic\nvendor \"SCE\"\nproduct \"Ethernet (Network Adaptor)\"\nphy_config auto\n");
    bool ok = write_file(dir / "net000.cnf", combination.data(), combination.size());
    ok = ok && write_file(dir / "ifc000.dat", interface.data(), interface.size());
    ok = ok && write_file(dir / "dev000.dat", device.data(), device.size());
    ok = ok && write_file(dir / "BWNETCNF", index.data(), index.size());   // last: it is what says a setting exists
    return ok ? 1 : -1;
}
struct Combination { std::string name, interface, device; };
// the settings of the card's index: a line is "<kind>,<state>,<file>,<name>", kind 0 a
// combination, 1 an interface setting, 2 a device; a combination's file names its two parts
std::vector<Combination> read_netcnf() {
    std::vector<Combination> list;
    fs::path dir = fs::path(D.info.card_dir) / "mc0" / "BWNETCNF";
    std::ifstream index(dir / "BWNETCNF");
    std::map<std::string, std::string> shown;       // file -> name
    std::vector<std::pair<std::string, std::string>> combinations;
    std::string line, first_interface, first_device;
    while (std::getline(index, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t a = line.find(','), b = a == std::string::npos ? a : line.find(',', a + 1), c = b == std::string::npos ? b : line.find(',', b + 1);
        if (c == std::string::npos) continue;
        std::string kind = line.substr(0, a), file = line.substr(b + 1, c - b - 1), name = line.substr(c + 1);
        shown[file] = name;
        if (kind == "0") combinations.push_back({file, name});
        if (kind == "1" && first_interface.empty()) first_interface = name;
        if (kind == "2" && first_device.empty()) first_device = name;
    }
    for (const auto& entry : combinations) {
        Combination made;
        made.name = entry.second;
        made.interface = first_interface;
        made.device = first_device;
        std::ifstream body(dir / entry.first);
        std::string text((std::istreambuf_iterator<char>(body)), std::istreambuf_iterator<char>());
        // the quoted words after the first: the interface file, the device file
        std::vector<std::string> quoted;
        for (size_t at = text.find('"'); at != std::string::npos;) {
            size_t end = text.find('"', at + 1);
            if (end == std::string::npos) break;
            quoted.push_back(text.substr(at + 1, end - at - 1));
            at = text.find('"', end + 1);
        }
        for (const auto& word : quoted) {
            auto found = shown.find(word);
            if (found == shown.end()) continue;
            if (word.compare(0, 3, "ifc") == 0) made.interface = found->second;
            if (word.compare(0, 3, "dev") == 0) made.device = found->second;
        }
        list.push_back(made);
        if (list.size() == 6) break;
    }
    return list;
}

// ---- set-up ---------------------------------------------------------------------------------
std::string option(const char* name, const char* fallback = "") {
    const char* value = rt_option(name);
    return value ? value : fallback;
}

void do_setup() {
    D.ready = true;
    D.start = std::chrono::steady_clock::now();
    if (!sock::start()) rtanet::say("the host's network could not be started: the game will not get online");
    rtanet::Info& I = D.info;
    std::string value = option("net-log");
    if (!value.empty()) D.log_file = fopen(value.c_str(), "w");
    D.log_all = option("net-log-all") == "1";
    D.local_only = option("net-local-only") == "1";
    D.bind_game_ports = option("net-ports") != "0";
    D.tell_set = option("net-set-quiet") != "1";
    D.write_netcnf = option("net-netcnf") != "0";
    D.hold_disconnects = option("net-hold-disconnects") != "0";
    value = option("net-pace");
    if (!value.empty()) D.pace = atof(value.c_str());
    // tests: a second lobby server instance on this computer, with every port the usual one
    // plus N (the gateway port is built into the game; the lobby and discovery ports are
    // told by the server)
    value = option("net-port-shift");
    if (!value.empty()) {
        D.port_shift = atoi(value.c_str());
        D.server_udp_ports.insert((u16)(10101 + D.port_shift));
    }
    list_own_addresses();
    // the arithmetic: auto (the console's, a browser's while a browser copy is in the room),
    // or fixed.  The runtime's own --opt arith=nearest leaves every thread in the host's
    // state, which is the browser's: then that is what this copy does and says.
    A.switchable = ARITH_SWITCHABLE;
    value = option("net-arith");
    if (option("arith") == "nearest") { A.fixed = ARITH_BROWSER; A.switchable = false; }
    else if (value == "console") A.fixed = ARITH_CONSOLE;
    else if (value == "browser" && A.switchable) A.fixed = ARITH_BROWSER;
    else if (!value.empty() && value != "auto") rtanet::say("net-arith=%s is not auto, console or browser%s", value.c_str(), value == "browser" ? " (and this build cannot change its arithmetic)" : "");
    A.now = A.fixed == ARITH_BROWSER ? ARITH_BROWSER : ARITH_CONSOLE;

    I.data_dir = option("net-data");
    if (I.data_dir.empty()) I.data_dir = (fs::path(sock::program_dir()).parent_path() / "app-data").string();
    I.card_dir = option("net-card");
    if (I.card_dir.empty()) I.card_dir = (fs::path(I.data_dir) / "card").string();
    std::error_code ec;
    fs::create_directories(I.data_dir, ec);

    // the server
    std::string server = option("net-server");
    I.server_key = server.empty() ? "localhost" : server;
    bool own = false;
    if (server.empty() || server == "localhost") own = true;
    else if (!resolve_host(server, I.server_ip)) rtanet::say("CANNOT find the lobby server '%s': the game will not get online", server.c_str());
    else if (is_loopback(I.server_ip)) own = true;
    if (own) {
        // A server on this computer is reached at the computer's outside address, as the
        // emulator-based application reaches it: the lobby server must see the address
        // other players' copies can use.
        I.server_ip = sock::outside_address();
        if (I.server_ip == 0) {
            I.server_ip = LOOPBACK;
            I.guest_server_ip = GUEST_SERVER_NAME;
            I.server_text = "this computer, which has no network address";
        } else I.server_text = "this computer (" + rtanet::ip_text(I.server_ip) + ")";
    } else if (I.server_ip) I.server_text = server + (rtanet::ip_text(I.server_ip) == server ? "" : " (" + rtanet::ip_text(I.server_ip) + ")");
    if (I.guest_server_ip == 0) I.guest_server_ip = I.server_ip;
    value = option("net-server-public");
    u32 address = 0;
    if (!value.empty() && resolve_host(value, address)) D.aliases.insert(address);
    value = option("net-loopback");
    I.loopback_peers = value == "on" || (value != "off" && is_own(I.server_ip));

    // the machine's own-network address: the game reports it to the lobby server and other
    // players' games try it, so it differs from copy to copy and is kept
    fs::path address_file = fs::path(I.data_dir) / "online-address";
    value = option("net-addr");
    if (value.empty()) { std::ifstream in(address_file); std::getline(in, value); }
    u32 guest = 0;
    if (!parse_ip(value, guest) || (guest & MADE_UP_MASK) != MADE_UP_NET || (guest >> 16) != 0xC613 || (guest & 0xFF) == 0 || (guest & 0xFF) == 255) {
        std::random_device random;
        guest = 0xC6130000 | ((random() % 256) << 8) | (2 + random() % 250);
        if (option("net-addr").empty()) { std::ofstream out(address_file); out << rtanet::ip_text(guest) << "\n"; }
    }
    I.guest_ip = guest;

    // the patch set, as the emulator-based application figures it: FNV-1a over address and
    // value of the fix set's words in address order
    const u32 (*words)[2] = nullptr;
    unsigned count = recomp_patches(&words), set_count = recomp_patch_set_words();
    if (set_count > count) set_count = count;
    std::vector<std::pair<u32, u32>> sorted;
    for (unsigned k = 0; k < set_count; k++) sorted.push_back({words[k][0], words[k][1]});
    std::stable_sort(sorted.begin(), sorted.end(), [](const std::pair<u32, u32>& a, const std::pair<u32, u32>& b) { return a.first < b.first; });
    u32 hash = 2166136261u;
    for (const auto& word : sorted)
        for (u32 v : {word.first, word.second})
            for (int i = 0; i < 4; i++) hash = (hash ^ ((v >> (i * 8)) & 0xFF)) * 16777619u;
    I.patch_set = hash;
    I.patch_words = set_count;

    // the network setting
    if (D.write_netcnf) {
        int wrote = write_netcnf(fs::path(I.card_dir) / "mc0");
        if (wrote < 0) rtanet::say("could not write the network setting to %s/mc0", I.card_dir.c_str());
        else if (wrote > 0) rtanet::log("the network setting was written to the memory card (BWNETCNF)");
    }

    // the tick log of a test run
    value = option("tick-watch-file");
    if (!value.empty() && !option("tick-log").empty() && (D.tick_log = fopen(option("tick-log").c_str(), "w"))) {
        // one "name=expression:type" a line, as the rig's --tick-watch; the first column is
        // this machine's vertical-blank number
#ifndef _WIN32      // (the Windows C library takes no size of 0 here, and has no line buffering: the log is flushed at the end)
        setvbuf(D.tick_log, nullptr, _IOLBF, 0);
#endif
        fprintf(D.tick_log, "frame");
        std::ifstream in(value);
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            size_t colon = line.rfind(':'), equals = line.find('=');
            if (colon == std::string::npos) continue;
            bool named = equals != std::string::npos && equals < colon;
            D.tick_exprs.push_back({named ? line.substr(equals + 1, colon - equals - 1) : line.substr(0, colon), line.substr(colon + 1)});
            fprintf(D.tick_log, "\t%s", (named ? line.substr(0, equals) : line.substr(0, colon)).c_str());
        }
        fprintf(D.tick_log, "\n");
    }
    value = option("tick-do");
    if (!value.empty()) {
        // "<tick> poke <expression> <text>" writes text and a zero byte inside that lockstep
        // tick (a level name into g_pendingLevel on every machine in the same tick, as the
        // rig's "ontick"); "<tick> poke32 <expression> <number>" a word; "<tick> echo <text>";
        // "<tick> quit"
        std::ifstream in(value);
        std::string line;
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            size_t space = line.find(' ');
            if (space != std::string::npos) D.tick_actions.insert({(u32)strtoul(line.c_str(), nullptr, 0), line.substr(space + 1)});
        }
    }
    I.configured = true;
    rtanet::say("server %s; this copy's own-network address %s; patch set %08x (%u words)%s%s", I.server_text.empty() ? "(none)" : I.server_text.c_str(),
                rtanet::ip_text(I.guest_ip).c_str(), I.patch_set, I.patch_words,
                I.loopback_peers ? "; other copies on this computer are reached through the loop-back interface" : "",
                D.local_only ? "; nothing is sent beyond this computer" : "");
}
inline void ensure() { if (!D.ready) do_setup(); }

// ---- UDP -----------------------------------------------------------------------------------
UdpHost& udp_host(u16 game_port) {
    auto found = D.udp.find(game_port);
    if (found != D.udp.end()) return found->second;
    UdpHost entry;
    entry.fd = sock::udp();
    bool same = D.bind_game_ports && game_port >= 1024 && sock::bind_port(entry.fd, game_port);
    if (!same) sock::bind_port(entry.fd, 0);
    sock::receive_buffer(entry.fd, 256 * 1024);
    entry.host_port = sock::local_port(entry.fd);
    rtanet::log("UDP port %u of the game is host port %u%s", game_port, entry.host_port, (D.bind_game_ports && !same) ? " (the same number was taken)" : "");
    return D.udp[game_port] = entry;
}

bool allowed(u32 real_ip) { return !D.local_only || is_own(real_ip); }

s32 udp_send(Conn& conn, const u8* data, u32 length, u32 dest_ip, u16 dest_port) {
    if (net2hook::udp_owns && net2hook::udp_owns(conn.game_port)) return net2hook::udp_send(conn.game_port, data, length, dest_ip, dest_port);
    rtanet::Info& I = D.info;
    bool made_up = (dest_ip & MADE_UP_MASK) == MADE_UP_NET && !is_server(dest_ip);
    if (made_up || dest_ip == 0xFFFFFFFF || (dest_ip >> 28) == 0xE || dest_ip == 0 || (is_loopback(dest_ip) && !is_server(dest_ip))) {
        I.dropped++;
        if (D.noted.insert(key(dest_ip, dest_port)).second)
            rtanet::log("UDP to %s:%u not carried (%s)", rtanet::ip_text(dest_ip).c_str(), dest_port, made_up ? "another machine's own-network address" : "not an address on the Internet");
        return (s32)length;
    }
    bool to_server = is_server(dest_ip), server_port = to_server && D.server_udp_ports.count(dest_port) != 0;
    u32 real_ip = to_server ? I.server_ip : dest_ip;
    // the server's address on a port that is not the server's: another copy on the server's
    // computer (a host firewall may drop datagrams between two local programs on the
    // outside address)
    if (to_server && !server_port && I.loopback_peers) real_ip = LOOPBACK;
    if (!allowed(real_ip)) {
        I.dropped++;
        if (D.noted.insert(key(dest_ip, dest_port) | (1ull << 61)).second) rtanet::say("UDP to %s:%u NOT SENT: not this computer (net-local-only)", rtanet::ip_text(real_ip).c_str(), dest_port);
        return (s32)length;
    }
    UdpHost& host = udp_host(conn.game_port);
    sock::send_to(host.fd, data, length, real_ip, dest_port);
    if (real_ip != dest_ip) { D.seen_as[key(real_ip, dest_port)] = dest_ip; D.seen_as_any[real_ip] = dest_ip; }
    else D.seen_as.erase(key(real_ip, dest_port));
    if (server_port) {
        if (I.udp_to_server++ == 0) rtanet::log("first datagram to the server: port %u -> %s:%u (%u bytes)", conn.game_port, rtanet::ip_text(real_ip).c_str(), dest_port, length);
    } else {
        I.udp_to_peers++;
        if (D.noted.insert(key(dest_ip, dest_port) | (1ull << 63)).second)
            rtanet::log("first datagram to another player: port %u -> %s:%u%s (%u bytes)", conn.game_port, rtanet::ip_text(dest_ip).c_str(), dest_port,
                        real_ip == dest_ip ? "" : (real_ip == LOOPBACK ? ", sent through the loop-back interface" : ", sent to the server's host"), length);
    }
    return (s32)length;
}

// A peer's disconnect, held back while this game is in a game's room.
//
// The game's launch has a hole (docs/issues/three-players.md, cause 1): a joiner that takes
// the host's START fills its launch tables from its LIVE connections to the other players
// and then disconnects them all; a joiner reads its socket every tenth frame, so one that
// reads later finds the disconnect of the one that read earlier in the same read as START,
// has no live connection to it any more, and files a wrong address for it.  The launch
// handshake repairs one wrong entry from the datagrams that arrive, but not two joiners
// that are wrong about each other (seen: a launch of four in which two joiners never met,
// docs/issues/native-online.md).  A network that delivered that disconnect half a second
// later would have hidden the hole, and that is what is done here: a datagram that is the
// peer library's disconnect (8 bytes: 00 05, the connection's code, a reason) and arrives
// while the lobby state word says "in a game's room" (6) is kept for 30 vertical blanks, or
// until the state has moved on - by then the tables are filled from connections that were
// all still there.  A player who just leaves the room is seen to leave half a second late.
// Nothing else is ever held, and nothing during a game.  --opt net-hold-disconnects=0: off.
const u32 A_LOBBY_STATE = 0x506160;
const u64 HOLD_FIELDS = 30;
bool in_a_room() { return rd32(A_LOBBY_STATE) == 6; }
bool held_due(const UdpHost& host) {
    return !host.held.empty() && (rt_fields() >= host.held.front().due_field || !in_a_room());
}

// the next datagram for the game on this port; false: none
bool udp_receive(u16 game_port, u8* buffer, size_t capacity, size_t& size, u32& shown_ip, u16& from_port) {
    if (net2hook::udp_owns && net2hook::udp_owns(game_port)) return net2hook::udp_receive(game_port, buffer, capacity, size, shown_ip, from_port);
    rtanet::Info& I = D.info;
    UdpHost& host = udp_host(game_port);
    if (held_due(host)) {
        Held& first = host.held.front();
        size = std::min(first.data.size(), capacity);
        memcpy(buffer, first.data.data(), size);
        shown_ip = first.shown_ip;
        from_port = first.from_port;
        host.held.pop_front();
        return true;
    }
    for (int tries = 0; tries < 32; tries++) {
        u32 from_ip = 0;
        int n = sock::recv_from(host.fd, buffer, capacity, from_ip, from_port);
        if (n < 0) return false;
        // shown to the game as coming from the address it knows the sender by
        shown_ip = from_ip;
        auto seen = D.seen_as.find(key(from_ip, from_port));
        auto seen_any = D.seen_as_any.find(from_ip);
        if (seen != D.seen_as.end()) shown_ip = seen->second;
        else if (seen_any != D.seen_as_any.end()) shown_ip = seen_any->second;
        else if (is_loopback(from_ip) || from_ip == I.server_ip) shown_ip = I.guest_server_ip;     // another copy on the server's host
        if (from_ip == I.server_ip && D.server_udp_ports.count(from_port)) I.udp_from_server++;
        else {
            I.udp_from_peers++;
            if (D.noted.insert(key(from_ip, from_port) | (1ull << 62)).second)
                rtanet::log("first datagram from another player: %s:%u -> port %u%s (%d bytes)", rtanet::ip_text(from_ip).c_str(), from_port, game_port,
                            shown_ip == from_ip ? "" : (", shown to the game as " + rtanet::ip_text(shown_ip)).c_str(), n);
            PeerState& peer = D.peer[key(from_ip, from_port)];
            int64_t now = now_ms();
            if (peer.first_heard == 0 || now - peer.last_heard > 30000) { peer.first_heard = now ? now : 1; peer.told = 0; }    // back after a silence: told again
            peer.last_heard = now;
            peer.local_port = game_port;
            if ((size_t)n == PATCH_SET_SIZE && memcmp(buffer, PATCH_SET_MARK, sizeof(PATCH_SET_MARK)) == 0) {
                const u8* at = buffer + sizeof(PATCH_SET_MARK);
                u32 set = ((u32)at[0] << 24) | (at[1] << 16) | (at[2] << 8) | at[3];
                u16 words = (u16)((at[4] << 8) | at[5]);
                if (!peer.set_known || peer.patch_set != set)
                    rtanet::say("the player at %s:%u has patch set %08x (%u words): %s", rtanet::ip_text(from_ip).c_str(), from_port, set, words,
                                set == I.patch_set ? "the same as this copy" : "DIFFERENT from this copy's");
                peer.set_known = true;
                peer.patch_set = set;
                peer.patch_words = words;
                continue;               // ours, not the game's
            }
            if ((size_t)n == ARITH_SIZE && memcmp(buffer, ARITH_MARK, sizeof(ARITH_MARK)) == 0) {
                // which arithmetic the other copy can compute with and which it does now
                // (docs/issues/mixed-arithmetic.md); what follows from it is check_arith's
                u8 can = buffer[sizeof(ARITH_MARK)], does = buffer[sizeof(ARITH_MARK) + 1];
                if (!peer.arith_known || peer.arith_can != can || peer.arith_does != does)
                    rtanet::say("the player at %s:%u computes with %s (can do: %s)", rtanet::ip_text(from_ip).c_str(), from_port, arith_name(does ? ARITH_BROWSER : ARITH_CONSOLE), arith_can_name(can));
                peer.arith_known = true;
                peer.arith_can = can;
                peer.arith_does = does;
                continue;
            }
            if (D.hold_disconnects && n == 8 && buffer[0] == 0x00 && buffer[1] == 0x05 && in_a_room()) {
                Held held;
                held.due_field = rt_fields() + HOLD_FIELDS;
                held.data.assign(buffer, buffer + n);
                held.shown_ip = shown_ip;
                held.from_port = from_port;
                host.held.push_back(held);
                D.held_total++;
                rtanet::log("a disconnect from the player at %s:%u is shown to the game half a second late (it is in a game's room)", rtanet::ip_text(from_ip).c_str(), from_port);
                continue;
            }
        }
        size = (size_t)n;
        return true;
    }
    return false;
}

// our patch set, to the players heard from: a few times, as a datagram may be lost
void tell_patch_set() {
    if (!D.tell_set) return;
    int64_t now = now_ms();
    for (auto& entry : D.peer) {
        PeerState& peer = entry.second;
        const int times = (int)(sizeof(PATCH_SET_TIMES) / sizeof(PATCH_SET_TIMES[0]));
        if (peer.told >= times || now - peer.first_heard < PATCH_SET_TIMES[peer.told]) continue;
        peer.told++;
        auto host = D.udp.find(peer.local_port);
        if (host == D.udp.end()) continue;
        u8 datagram[PATCH_SET_SIZE];
        memcpy(datagram, PATCH_SET_MARK, sizeof(PATCH_SET_MARK));
        u8* at = datagram + sizeof(PATCH_SET_MARK);
        at[0] = (u8)(D.info.patch_set >> 24); at[1] = (u8)(D.info.patch_set >> 16); at[2] = (u8)(D.info.patch_set >> 8); at[3] = (u8)D.info.patch_set;
        at[4] = (u8)(D.info.patch_words >> 8); at[5] = (u8)D.info.patch_words;
        u32 to_ip = (u32)(entry.first >> 16);
        u16 to_port = (u16)(entry.first & 0xFFFF);
        if (!allowed(to_ip)) continue;
        sock::send_to(host->second.fd, datagram, sizeof(datagram), to_ip, to_port);
        // and the arithmetic, in the same way (docs/issues/mixed-arithmetic.md): one byte
        // "can do" (bit 0 the console's, which the other builds call Play!'s own; bit 1 a
        // browser's), one byte "does now" (0 or 1)
        u8 arithmetic[ARITH_SIZE];
        memcpy(arithmetic, ARITH_MARK, sizeof(ARITH_MARK));
        arithmetic[sizeof(ARITH_MARK)] = A.can();
        arithmetic[sizeof(ARITH_MARK) + 1] = (u8)A.now;
        sock::send_to(host->second.fd, arithmetic, sizeof(arithmetic), to_ip, to_port);
        if (peer.told == 1) rtanet::log("patch set %08x and the arithmetic (%s; can do: %s) told to the player at %s:%u", D.info.patch_set, arith_name(A.now), arith_can_name(A.can()), rtanet::ip_text(to_ip).c_str(), to_port);
    }
    for (auto& entry : D.peer) {
        PeerState& peer = entry.second;
        if (!peer.set_known || peer.warned || peer.patch_set == D.info.patch_set) continue;
        peer.warned = true;
        rtanet::say("WARNING: a player (%s:%u) has patch set %08x (%u words), this copy %08x (%u words): they would fall out of step",
                    rtanet::ip_text((u32)(entry.first >> 16)).c_str(), (unsigned)(entry.first & 0xFFFF), peer.patch_set, peer.patch_words, D.info.patch_set, D.info.patch_words);
        if (rtanet::show_warning) {
            char text[400];
            snprintf(text, sizeof(text), "Another player's copy of the game is patched differently (its set is %08x with %u words, yours is %08x with %u words). "
                     "The two games would fall out of step. Everyone has to play with the same patch set.", peer.patch_set, peer.patch_words, D.info.patch_set, D.info.patch_words);
            rtanet::show_warning(text);
        }
    }
}

// The choice, by the rule of the emulator-based application (CheckArithmetic in
// tools/play-net/src/Rta.cpp), once per vertical blank on the game's thread:
//   - while the game is in its front end (the lobby and a game's room are there): a player
//     heard in the last 15 s who cannot do the console's arithmetic, or already does a
//     browser's, makes this copy change to browser arithmetic; nobody such, and it changes
//     back.  The second condition carries the choice to copies that do not hear the browser
//     player themselves;
//   - once a level runs nothing is changed (every machine would have to change in the same
//     lockstep tick): a player who cannot follow gets a warning instead;
//   - a change is told to everybody again, from the start.
void check_arith() {
    int64_t now = now_ms();
    bool front_end = g_ram[0x41B510] != 0;          // g_inFrontend
    int want = A.now;
    if (A.fixed >= 0) want = A.fixed;
    else if (!A.switchable) want = ARITH_CONSOLE;
    else if (front_end) {
        want = ARITH_CONSOLE;
        for (const auto& entry : D.peer) {
            const PeerState& peer = entry.second;
            if (!peer.arith_known || now - peer.last_heard > 15000) continue;
            if (!(peer.arith_can & 1) || peer.arith_does == 1) want = ARITH_BROWSER;
        }
    }
    if (want != A.now) {
        A.now = want;
        rtanet::say("arithmetic: the machine now computes %s", want == ARITH_BROWSER ? "as a browser copy's does" : "as the console does again");
        for (auto& entry : D.peer) { entry.second.told = 0; entry.second.first_heard = now ? now : 1; }
    }
    thread_arith(A.now);
    for (auto& entry : D.peer) {
        PeerState& peer = entry.second;
        if (now - peer.last_heard > 15000 || peer.arith_warned == A.now) continue;
        const char* why = nullptr;
        if (peer.arith_known) {
            // it does something else and cannot do ours (a copy that can is on its way)
            if (peer.arith_does != A.now && !(peer.arith_can & (1 << A.now)))
                why = A.now == ARITH_BROWSER ? "cannot compute with browser arithmetic as this game does" : "computes with browser arithmetic and this copy cannot";
            else if (peer.arith_does != A.now && !front_end)
                why = "is on different arithmetic in a running game";
        } else if (A.now == ARITH_BROWSER && peer.set_known && now - peer.first_heard > 6000)
            why = "says nothing about its arithmetic (an older copy) while this game computes as a browser does";
        if (!why) continue;
        peer.arith_warned = A.now;
        rtanet::say("WARNING: the player at %s:%u %s: the game would fall out of step - do not start it", rtanet::ip_text((u32)(entry.first >> 16)).c_str(), (unsigned)(entry.first & 0xFFFF), why);
        if (rtanet::show_warning) rtanet::show_warning("Another player's copy does not compute the way this game does (one of the copies is a browser's and another cannot follow it). The games would fall out of step: do not start the game.");
    }
}

// ---- TCP -----------------------------------------------------------------------------------
// The first reply on a gateway connection says where the lobby is: big-endian length,
// then u16 0x43, u32 tracking number, u32 result, a counted address string, u32 port
// (docs/lobby-protocol.md 2 and 5).  A server at home hands out its public address, which
// a machine on the server's own network often cannot reach; the address the gateway was
// reached at is the one that works, so the named address is taken for the server too.
void gateway_reply(Conn& conn) {
    if (conn.head.size() < 4) return;
    u32 frame = ((u32)conn.head[0] << 24) | (conn.head[1] << 16) | (conn.head[2] << 8) | conn.head[3];
    if (frame < 22 || frame > 256) { conn.gateway_parsed = true; return; }
    if (conn.head.size() < frame) return;
    conn.gateway_parsed = true;
    const u8* p = conn.head.data() + 4;
    auto le32 = [](const u8* q) { return (u32)q[0] | (q[1] << 8) | (q[2] << 16) | ((u32)q[3] << 24); };
    u16 id = (u16)(p[0] | (p[1] << 8));
    u32 result = le32(p + 6), count = le32(p + 10);
    if (id != 0x43 || result != 0 || count > 40 || 18 + count > frame) return;
    std::string text((const char*)p + 14, count);
    u32 named = 0;
    if (!parse_ip(text, named)) { rtanet::log("the server names its lobby as something that is not a dotted address"); return; }
    if (is_server(named)) return;
    bool both_public = !is_private(named) && !is_private(D.info.server_ip);
    if (!D.learn_alias || both_public) { rtanet::log("the server names its lobby as %s; connections there are made as they are", text.c_str()); return; }
    D.aliases.insert(named);
    rtanet::log("the server names its lobby as %s, but it was reached at %s: from now on %s means the server", text.c_str(), rtanet::ip_text(D.info.server_ip).c_str(), text.c_str());
}

void tcp_check(Conn& conn) {            // a connection under way: has it come up?
    if (!conn.connecting || conn.fd == sock::NONE) return;
    int state = sock::connect_check(conn.fd);
    if (state == sock::UNDER_WAY) return;
    conn.connecting = false;
    if (state == sock::CONNECTED) {
        conn.connected = true;
        rtanet::log("TCP -> %s:%u connected", rtanet::ip_text(conn.dest_ip).c_str(), conn.dest_port);
    } else {
        conn.failed = true;
        rtanet::log("TCP -> %s:%u could not connect (%s)", rtanet::ip_text(conn.dest_ip).c_str(), conn.dest_port, sock::error_text(sock::error()).c_str());
    }
}

Conn* find(s32 id) {
    auto found = D.conns.find(id);
    return found == D.conns.end() ? nullptr : &found->second;
}

}  // namespace

// ---- for the application ----------------------------------------------------------------------
namespace rtanet {
void setup() { ensure(); }
const Info& info() { return D.info; }
std::string ip_text(uint32_t ip) {
    char text[32];
    snprintf(text, sizeof(text), "%u.%u.%u.%u", ip >> 24, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF);
    return text;
}
void log(const char* format, ...) {
    va_list args;
    va_start(args, format);
    vlog(D.log_file == nullptr, format, args);
    va_end(args);
}
void say(const char* format, ...) {
    va_list args;
    va_start(args, format);
    vlog(true, format, args);
    va_end(args);
}
std::vector<Peer> peers() {
    std::vector<Peer> list;
    int64_t now = now_ms();
    for (const auto& entry : D.peer) {
        Peer peer;
        peer.ip = (u32)(entry.first >> 16);
        peer.port = (u16)(entry.first & 0xFFFF);
        peer.set_known = entry.second.set_known;
        peer.patch_set = entry.second.patch_set;
        peer.patch_words = entry.second.patch_words;
        peer.arith_known = entry.second.arith_known;
        peer.arith_can = entry.second.arith_can;
        peer.arith_does = entry.second.arith_does;
        peer.heard_ms = now - entry.second.first_heard;
        peer.silent_ms = now - entry.second.last_heard;
        list.push_back(peer);
    }
    return list;
}
std::string sockets_text() {
    // what the driver holds open: for a test that plays several games in one run
    unsigned streams = 0, open_streams = 0, datagram = 0, raw = 0;
    for (const auto& entry : D.conns) {
        if (entry.second.type == T_CONNECT) { streams++; if (entry.second.fd != sock::NONE && !entry.second.eof && !entry.second.failed) open_streams++; }
        else if (entry.second.type == T_DGRAM) datagram++;
        else raw++;
    }
    char text[256];
    snprintf(text, sizeof(text), "library sockets: %u streams (%u open), %u datagram, %u raw; host UDP sockets %zu; players heard %zu; ids given %d; disconnects held back %llu",
             streams, open_streams, datagram, raw, D.udp.size(), D.peer.size(), D.next_id - 1, (unsigned long long)D.held_total);
    return text;
}
void drop_tcp() {
    for (auto& entry : D.conns)
        if (entry.second.type == T_CONNECT && entry.second.fd != sock::NONE) { sock::shut(entry.second.fd); log("TCP -> %s:%u cut (a test)", ip_text(entry.second.dest_ip).c_str(), entry.second.dest_port); }
}
const char* option(const char* key) { return rt_option(key); }
int arithmetic() { return A.now; }
std::string arithmetic_text() {
    return std::string(A.now == ARITH_BROWSER ? "browser" : "console") + " (can do: " + arith_can_name(A.can()) + (A.fixed >= 0 ? ", fixed" : "") + ")";
}
void per_blank(uint64_t number) {
    ensure();
    if (net2hook::blank) net2hook::blank(number);
    check_arith();
    tell_patch_set();
    // a program without a window is held to real time: the lobby's time-outs count frames,
    // and the server and the other players answer in real time
    if (D.pace > 0 && !g_hooks.video) {
        auto now = std::chrono::steady_clock::now();
        auto period = std::chrono::nanoseconds((int64_t)(1e9 / D.pace));
        if (!D.pace_started || now - D.pace_next > std::chrono::milliseconds(250)) { D.pace_started = true; D.pace_next = now; }
        D.pace_next += period;
        if (D.pace_next > now) std::this_thread::sleep_until(D.pace_next);
    }
}
}  // namespace rtanet

// ---- the library entries ------------------------------------------------------------------------
// A call that asked to wait and has nothing to give waits, as on the console, where every
// one of these calls is an RPC to the I/O processor that comes back after its time-out:
// the calling game thread is parked for that long on the virtual clock (other threads and
// interrupts run), and the caller looks once more.  This is not cosmetic.  The peer
// library asks with 1 ms on its data socket and 1 ms on its ICMP socket, and the host's
// loop that waits for START to be acknowledged before it disconnects (SRSClient_shutdownUdp
// 0x328770: at most 100 rounds) is only long enough because of those waits: with calls
// that answer at once it is over in 10 ms, the other machine gets START and the
// disconnect in one poll, finds no live connection when it fills its launch tables, and
// the game never starts (seen; docs/issues/native-online.md).
static bool nap(Ctx* c, u32 ms) {
    if (ms == 0 || (s32)ms < 0) return false;
    rt_sleep(c, usec_to_cycles((u64)(ms > 1000 ? 1000 : ms) * 1000));
    return true;
}
void fn_00365ec0(Ctx* c) {                  // sceLibnetInitialize(cd, buffer size, stack size, priority)
    ensure();
    if (D.log_all) rtanet::log("sceLibnetInitialize -> 0");
    answer(c, 0);
}
void fn_00365f88(Ctx* c) { ensure(); answer(c, 0); }       // sceLibnetTerminate(cd)

void fn_00365a08(Ctx* c) {                  // sceInetGetInterfaceList(cd, buf, id list, max)
    ensure();
    wr32(arg(c, 2), 1);
    answer(c, 1);
}
void fn_00365a90(Ctx* c) {                  // sceInetInterfaceControl(cd, buf, interface, code, ptr, len)
    ensure();
    u32 code = arg(c, 3), pointer = arg(c, 4), length = arg(c, 5);
    if (u8* p = gptr(pointer, length)) memset(p, 0, length);
    if (code == 9 && length >= 16) block_set(pointer, D.info.guest_ip);     // the interface's address
    else if (code == 8 && length >= 4) wr32(pointer, 0x43);                 // its flags: up, running
    else if (D.noted.insert(0xC0DE0000ull | code).second) rtanet::log("sceInetInterfaceControl code %u (%u bytes): answered with zeros", code, length);
    answer(c, 0);
}

void fn_003654a8(Ctx* c) {                  // sceInetCreate(cd, buf, 0x40-byte parameter block)
    ensure();
    u32 parameters = arg(c, 2);
    Conn conn;
    conn.type = (int)rd32(parameters);
    u32 local_port = rd32(parameters + 4);
    conn.dest_ip = block_ip(parameters + 8);
    conn.dest_port = (u16)rd32(parameters + 0x18);
    s32 id = D.next_id++;
    if (conn.type == T_DGRAM) {
        conn.game_port = (u16)local_port;
        udp_host(conn.game_port);
    }
    D.conns[id] = conn;
    if (D.log_all || conn.type != T_RAW)
        rtanet::log("sceInetCreate(%s, local port %d%s) -> id %d", conn.type == T_DGRAM ? "datagram" : conn.type == T_CONNECT ? "stream" : conn.type == T_RAW ? "raw" : "?",
                    (s32)local_port, conn.type == T_CONNECT ? (" to " + rtanet::ip_text(conn.dest_ip) + ":" + std::to_string(conn.dest_port)).c_str() : "", id);
    answer(c, id);
}

void fn_00365518(Ctx* c) {                  // sceInetOpen(cd, buf, id, ms)
    ensure();
    Conn* conn = find((s32)arg(c, 2));
    if (!conn) { answer(c, E_FAILED); return; }
    if (conn->type != T_CONNECT) { answer(c, 0); return; }
    if (conn->connected) { answer(c, 0); return; }
    if (conn->connecting) { tcp_check(*conn); answer(c, conn->connected ? 0 : conn->failed ? E_FAILED : E_NOT_YET); return; }
    conn->real_ip = is_server(conn->dest_ip) ? D.info.server_ip : conn->dest_ip;
    conn->gateway = is_server(conn->dest_ip) && conn->dest_port >= D.gateway_lo && conn->dest_port <= D.gateway_hi;
    if (conn->real_ip == 0 || !allowed(conn->real_ip)) {
        rtanet::say("TCP to %s:%u NOT MADE: %s", rtanet::ip_text(conn->real_ip).c_str(), conn->dest_port, conn->real_ip ? "not this computer (net-local-only)" : "no server address");
        conn->failed = true;
        answer(c, E_FAILED);
        return;
    }
    conn->fd = sock::tcp();
    D.info.tcp_connections++;
    rtanet::log("TCP -> %s:%u%s", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, conn->real_ip == conn->dest_ip ? "" : (" (the server, at " + rtanet::ip_text(conn->real_ip) + ")").c_str());
    u16 real_port = conn->gateway ? (u16)(conn->dest_port + D.port_shift) : conn->dest_port;
    int state = conn->fd == sock::NONE ? sock::FAILED : sock::connect(conn->fd, conn->real_ip, real_port);
    if (state == sock::CONNECTED) { conn->connected = true; answer(c, 0); return; }
    if (state == sock::UNDER_WAY) {
        conn->connecting = true;
        tcp_check(*conn);
        answer(c, conn->connected ? 0 : conn->failed ? E_FAILED : E_NOT_YET);
        return;
    }
    rtanet::log("TCP -> %s:%u could not connect (%s)", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, sock::error_text(sock::error()).c_str());
    conn->failed = true;
    answer(c, E_FAILED);
}

void fn_00365560(Ctx* c) {                  // sceInetClose(cd, buf, id, ms)
    ensure();
    s32 id = (s32)arg(c, 2);
    if (Conn* conn = find(id)) {
        if (conn->type == T_CONNECT) {
            sock::close(conn->fd);
            rtanet::log("TCP -> %s:%u closed by the game (%llu bytes out, %llu in)", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, (unsigned long long)conn->out, (unsigned long long)conn->in);
        } else if (D.log_all) rtanet::log("sceInetClose(id %d)", id);
        D.conns.erase(id);      // a datagram socket's host socket stays: the port's path is kept
    }
    answer(c, 0);
}

void fn_00365830(Ctx* c) {                  // sceInetSendTo(cd, buf, id, ptr, len, flags, addr, port, ms)
    ensure();
    Conn* conn = find((s32)arg(c, 2));
    u32 length = arg(c, 4);
    const u8* data = gptr(arg(c, 3), length);
    if (!conn || conn->type != T_DGRAM || !data) { answer(c, conn ? (s32)length : E_FAILED); return; }
    u32 dest = block_ip(arg(c, 6));
    u16 port = (u16)arg(c, 7);
    if (D.log_all) {
        char head[64] = "";
        for (u32 i = 0; i < length && i < 16; i++) snprintf(head + 3 * i, 4, " %02x", data[i]);
        rtanet::log("sceInetSendTo(port %u -> %s:%u, %u bytes, first%s)", conn->game_port, rtanet::ip_text(dest).c_str(), port, length, head);
    }
    u32 type = 0;
    if (length >= 12) memcpy(&type, data, 4);
    if (g_party8_wide && (type == 0xbd3f || type == 0xbd42) && length <= 2040) {
        // a game of five to eight: the sender's whole active mask rides behind the packet (moved.h PARTY8_TRAILER)
        u8 wide[2048];
        memcpy(wide, data, length);
        const u32 trailer = PARTY8_TRAILER | party8_active_mask(g_ram);
        memcpy(wide + length, &trailer, 4);
        s32 sent = udp_send(*conn, wide, length + 4, dest, port);
        answer(c, sent == (s32)(length + 4) ? (s32)length : sent);
        return;
    }
    answer(c, udp_send(*conn, data, length, dest, port));
}

void fn_00365670(Ctx* c) {                  // sceInetRecvFrom(cd, buf, id, ptr, len, flags, addr out, port out, ms)
    ensure();
    s32 id = (s32)arg(c, 2);
    u32 length = arg(c, 4), ms = rd32((u32)c->r[29]);       // the ninth argument is on the stack
    for (int attempt = 0; attempt < 2; attempt++) {
        Conn* conn = find(id);
        u8* into = gptr(arg(c, 3), length);
        if (!conn || conn->type != T_DGRAM || !into) break;
        u8 buffer[2048];
        size_t size = 0;
        u32 shown = 0;
        u16 port = 0;
        if (!udp_receive(conn->game_port, buffer, sizeof(buffer), size, shown, port)) {
            if (attempt == 0 && nap(c, ms)) continue;
            break;
        }
        u32 type = 0;
        if (size >= 12) memcpy(&type, buffer, 4);
        if (g_party8_wide && (type == 0xbd3f || type == 0xbd42)) {
            // a game of five to eight: the sender's active mask is the trailer (moved.h); the game sees the packet as sent
            u32 trailer = 0;
            if (size >= 16) memcpy(&trailer, buffer + size - 4, 4);
            if ((trailer & 0xFF000000u) == PARTY8_TRAILER) { g_party8_rx_mask = trailer & 0xFF; size -= 4; }
            else g_party8_rx_mask = 0x100;
        }
        if (size > length) size = length;
        memcpy(into, buffer, size);
        block_set(arg(c, 6), shown);
        wr32(arg(c, 7), port);
        wr32(arg(c, 5), 0);
        if (D.log_all) {
            char head[64] = "";
            for (size_t i = 0; i < size && i < 16; i++) snprintf(head + 3 * i, 4, " %02x", buffer[i]);
            rtanet::log("sceInetRecvFrom(port %u) -> %zu bytes from %s:%u, first%s", conn->game_port, size, rtanet::ip_text(shown).c_str(), port, head);
        }
        answer(c, (s32)size);
        return;
    }
    answer(c, E_NOT_YET);
}

void fn_00365780(Ctx* c) {                  // sceInetSend(cd, buf, id, ptr, len, flags, ms)
    ensure();
    Conn* conn = find((s32)arg(c, 2));
    u32 length = arg(c, 4);
    const u8* data = gptr(arg(c, 3), length);
    if (!conn || conn->type != T_CONNECT || !data) { answer(c, E_FAILED); return; }
    tcp_check(*conn);
    // a connection the server has closed answers the game's next send with an error, as
    // a reset would on a console
    if (conn->failed || conn->eof || conn->fd == sock::NONE) { answer(c, E_FAILED); return; }
    if (!conn->connected) { answer(c, E_NOT_YET); return; }
    int sent = sock::send(conn->fd, data, length);
    if (sent >= 0) {
        conn->out += sent;
        D.info.tcp_out += sent;
        if (D.log_all) rtanet::log("sceInetSend(%u bytes) -> %d", length, sent);
        answer(c, (s32)sent);
    } else if (sent == sock::AGAIN) answer(c, E_NOT_YET);
    else {
        rtanet::log("TCP -> %s:%u lost while sending (%s)", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, sock::error_text(sock::error()).c_str());
        conn->failed = true;
        answer(c, E_FAILED);
    }
}

void fn_003655a8(Ctx* c) {                  // sceInetRecv(cd, buf, id, ptr, len, flags, ms)
    ensure();
    s32 id = (s32)arg(c, 2);
    u32 length = arg(c, 4), ms = arg(c, 6);
    for (int attempt = 0; attempt < 2; attempt++) {
        Conn* conn = find(id);
        u8* into = gptr(arg(c, 3), length);
        if (!conn || !into) { answer(c, E_FAILED); return; }
        if (conn->type != T_CONNECT) {      // the raw (ICMP) socket beside a datagram socket: nothing ever waits there
            if (attempt == 0 && nap(c, ms)) continue;
            break;
        }
        tcp_check(*conn);
        if (conn->failed || conn->fd == sock::NONE) { answer(c, E_FAILED); return; }
        if (conn->eof) { answer(c, 0); return; }
        int got = conn->connected ? sock::recv(conn->fd, into, length) : sock::AGAIN;
        if (got > 0) {
            conn->in += got;
            D.info.tcp_in += got;
            if (conn->gateway && !conn->gateway_parsed) {
                conn->head.insert(conn->head.end(), into, into + got);
                gateway_reply(*conn);
            }
            wr32(arg(c, 5), 0);
            if (D.log_all) rtanet::log("sceInetRecv -> %d bytes", got);
            answer(c, (s32)got);
            return;
        }
        if (got == 0) {
            conn->eof = true;
            rtanet::log("TCP -> %s:%u closed by the server (%llu bytes out, %llu in)", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, (unsigned long long)conn->out, (unsigned long long)conn->in);
            answer(c, 0);
            return;
        }
        if (got == sock::LOST) {
            rtanet::log("TCP -> %s:%u lost (%s)", rtanet::ip_text(conn->dest_ip).c_str(), conn->dest_port, sock::error_text(sock::error()).c_str());
            conn->failed = true;
            answer(c, E_FAILED);
            return;
        }
        if (attempt == 0 && nap(c, ms)) continue;
        break;
    }
    answer(c, E_NOT_YET);
}

void fn_003651e0(Ctx* c) {                  // sceInetPoll(cd, buf, pollfd array, count, ms): {id, u16 events, u16 revents}
    ensure();
    u32 list = arg(c, 2), count = arg(c, 3), ms = arg(c, 4);
    s32 ready = 0;
    for (int attempt = 0; attempt < 2; attempt++) {
        ready = 0;
        for (u32 i = 0; i < count && i < 64; i++) {
            u32 at = list + i * 8;
            Conn* conn = find((s32)rd32(at));
            u16 events = rd16(at + 4), revents = 0;
            if (!conn) revents = 0x20;
            else if (conn->type == T_CONNECT) {
                tcp_check(*conn);
                if (conn->failed) revents = P_ERR | P_HUP;
                else if (conn->connected) {
                    if (events & P_OUT) revents |= P_OUT;
                    if ((events & P_IN) && sock::readable(conn->fd)) revents |= P_IN;
                }
            } else if (conn->type == T_DGRAM) {
                if (events & P_OUT) revents |= P_OUT;
                if ((events & P_IN) && (held_due(udp_host(conn->game_port)) || sock::readable(udp_host(conn->game_port).fd))) revents |= P_IN;
            }
            wr16(at + 6, revents);
            if (revents) ready++;
        }
        if (ready || attempt || !nap(c, ms)) break;
    }
    answer(c, ready);
}

void fn_00365288(Ctx* c) {                  // sceInetName2Address(cd, buf, flags, addr out, name, ms, retries)
    ensure();
    std::string name = gstr(arg(c, 4));
    u32 ip = 0;
    if (parse_ip(name, ip)) { block_set(arg(c, 3), ip); answer(c, 0); return; }    // the peer library converts every address through text
    std::string lower = name;
    for (auto& ch : lower) ch = (char)tolower((unsigned char)ch);
    bool known = lower == D.lobby_name && D.info.guest_server_ip != 0;
    rtanet::log("name lookup for %s -> %s", name.c_str(), known ? rtanet::ip_text(D.info.guest_server_ip).c_str() : "no such name (only the lobby's is answered)");
    if (known) { block_set(arg(c, 3), D.info.guest_server_ip); answer(c, 0); }
    else answer(c, E_FAILED);
}

void fn_00365348(Ctx* c) {                  // sceInetAddress2String(cd, buf, out, size, addr)
    ensure();
    std::string text = rtanet::ip_text(block_ip(arg(c, 4)));
    u32 size = arg(c, 3);
    if (u8* out = gptr(arg(c, 2), size)) { if (size) { strncpy((char*)out, text.c_str(), size - 1); out[size - 1] = 0; } }
    answer(c, 0);
}

void fn_00364fb8(Ctx* c) {                  // libnet_callRpc(cd, function, buffer, send size, receive size): an entry nobody answered above
    ensure();
    D.unanswered++;
    if (D.noted.insert(0xCA110000ull | arg(c, 1)).second) rtanet::say("network library function 0x%x is NOT ANSWERED (called from 0x%x)", arg(c, 1), (u32)c->r[31]);
    answer(c, E_FAILED);
}

// ---- the network configuration clients ----------------------------------------------------------
void fn_00367da8(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCnfInit
void fn_00367e98(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCnfExit
void fn_00367f18(Ctx* c) {                  // ezNetCnfGetCount(device): settings on the card
    ensure();
    s32 count = (s32)read_netcnf().size();
    rtanet::log("network settings on the memory card: %d", count);
    answer(c, count);
}
void fn_00367fd8(Ctx* c) {                  // ezNetCnfGetCombinationList(device, 7, list): 0x800 bytes
    ensure();
    // 48 bytes of head (six entries; two words that were 1 on the emulator), then six
    // entries of 200 bytes: state (0 a setting, -8 none), kind (2), and three names of 64
    // bytes: the combination, the setting shown in the list, the device
    u32 list = arg(c, 2);
    u8* p = gptr(list, 0x800);
    if (!p) { answer(c, E_FAILED); return; }
    memset(p, 0, 0x800);
    auto found = read_netcnf();
    wr32(list, 6);
    wr32(list + 4, 1);
    wr32(list + 8, 1);
    for (u32 i = 0; i < 6; i++) {
        u32 entry = list + 48 + i * 200;
        if (i >= found.size()) { wr32(entry, (u32)-8); continue; }
        wr32(entry + 4, 2);
        strncpy((char*)p + 48 + i * 200 + 8, found[i].name.c_str(), 63);
        strncpy((char*)p + 48 + i * 200 + 0x48, found[i].interface.c_str(), 63);
        strncpy((char*)p + 48 + i * 200 + 0x88, found[i].device.c_str(), 63);
    }
    answer(c, 0);
}
void fn_00368270(Ctx* c) {                  // ezNetCnfGetProperties(device, combination, properties): 0x1340 bytes
    ensure();
    // the properties are handed back to ezNetCtlSetProperties unread: there is no
    // interface to configure, the host's network is used as it is
    if (u8* p = gptr(arg(c, 2), 0x1340)) memset(p, 0, 0x1340);
    answer(c, 0);
}
void fn_0037a5d8(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCtlInit
void fn_0037a6c8(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCtlExit
void fn_0037a750(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCtlSetProperties
void fn_0037a868(Ctx* c) { ensure(); answer(c, 0); }       // ezNetCtlSetCombination
void fn_0037aac8(Ctx* c) {                  // ezNetCtlUpInterface
    ensure();
    if (!D.if_up) { D.if_up = true; D.if_up_field = rt_fields(); rtanet::log("the game brings its network interface up"); }
    answer(c, 0);
}
void fn_0037ab58(Ctx* c) {                  // ezNetCtlDownInterface
    ensure();
    if (D.if_up) rtanet::log("the game takes its network interface down");
    D.if_up = false;
    D.pending_event = 0xb;                  // "stopped": what the callers wait for
    answer(c, 0);
}
void fn_0037abe8(Ctx* c) {                  // ezNetCtlGetStatus(status, text, text size): 56 bytes
    ensure();
    // as read on the emulator with the interface up: 1, 0, "eth0", ... 2, 0, state 3
    // (started), link 1.  The interface is "starting" (1) for a third of a second first.
    u32 status = arg(c, 0);
    if (u8* p = gptr(status, 0x38)) {
        memset(p, 0, 0x38);
        if (D.if_up) {
            wr32(status, 1);
            memcpy(p + 8, "eth0", 4);
            wr32(status + 0x28, 2);
            wr32(status + 0x30, rt_fields() - D.if_up_field >= 20 ? 3 : 1);
            wr32(status + 0x34, 1);
        }
    }
    if (u8* text = gptr(arg(c, 1), 1)) *text = 0;
    answer(c, 0);
}
void fn_0037ad38(Ctx* c) {                  // ezNetCtlWaitEventTO(time-out, milliseconds)
    ensure();
    if (D.pending_event >= 0) { s32 event = D.pending_event; D.pending_event = -1; answer(c, event); return; }
    s32 ms = (s32)arg(c, 0);
    if (ms > 0) rt_sleep(c, usec_to_cycles((u64)(ms > 2000 ? 2000 : ms) * 1000));
    answer(c, -1);
}

// ---- the game's own two entries of the developer LAN start ----------------------------------------
void fn_00137a10(Ctx* c) { ensure(); answer(c, 1); }       // net_loadModules: not run; an interface id
void fn_0013e638(Ctx* c) { ensure(); answer(c, 1); }       // net_linkCheck: the line is up

// ---- hooks ----------------------------------------------------------------------------------------
void fn_00323dcc(Ctx* c) {                  // main(argc, argv)
    ensure();
    rtanet::online_install();
    orig_00323dcc(c);
}

void fn_003226e4(Ctx* c) {                  // tasks_run: from net_frameLoop it is one lockstep tick
    u32 ra = (u32)c->r[31];
    thread_arith(A.now);                    // the thread that runs the ticks computes as chosen
    if (net2hook::tasks) net2hook::tasks(c, ra == 0x13aee8);
    orig_003226e4(c);
    if (net2hook::after) net2hook::after(c, ra == 0x13aee8);
    if (ra != 0x13aee8) return;
    D.ticks++;
    if (D.tick_log) {
        fprintf(D.tick_log, "%llu", (unsigned long long)rt_fields());
        for (const auto& watch : D.tick_exprs) fprintf(D.tick_log, "\t%s", script_value(script_eval(watch.first), watch.second).c_str());
        fprintf(D.tick_log, "\n");
    }
    if (D.tick_actions.empty()) return;
    u32 tick = rd32(0x4027ac);              // g_netFrame: still this tick's number
    auto range = D.tick_actions.equal_range(tick);
    bool quit = false;
    for (auto it = range.first; it != range.second; ++it) {
        std::istringstream words(it->second);
        std::string verb, target, text;
        words >> verb;
        if (verb == "poke") {
            words >> target >> text;
            size_t colon = target.find(':');
            u32 address = script_eval(colon == std::string::npos ? target : target.substr(0, colon));
            if (u8* p = gptr(address, (u32)text.size() + 1)) memcpy(p, text.c_str(), text.size() + 1);
            printf("[tick %u] field %llu: poke %s %s\n", tick, (unsigned long long)rt_fields(), target.c_str(), text.c_str());
        } else if (verb == "poke32") {
            words >> target >> text;
            u32 address = script_eval(target);
            wr32(address, (u32)strtoul(text.c_str(), nullptr, 0));
            printf("[tick %u] field %llu: poke32 %s %s\n", tick, (unsigned long long)rt_fields(), target.c_str(), text.c_str());
        } else if (verb == "echo") printf("[tick %u] field %llu: %s\n", tick, (unsigned long long)rt_fields(), it->second.c_str() + 5 < it->second.c_str() + it->second.size() ? it->second.c_str() + 5 : "");
        else if (verb == "quit") quit = true;
    }
    D.tick_actions.erase(range.first, range.second);
    if (quit) { if (D.tick_log) fflush(D.tick_log); rt_finish(0); }
}
