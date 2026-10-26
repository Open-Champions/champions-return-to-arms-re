// netshim.cpp - the network of the native build, and what a lockstep test needs with it.
//
// Linked with the translated game and the runtime (tools/recomp/net/build_net.py).  It
// supplies fn_<address> for the functions listed in hle-net.txt:
//
//   - the ten places where the game's netcode enters Sony's network library, with the
//     semantics of the rig's shim (tools/rig/rig.cpp, CNetShim; docs/issues/live-rig.md
//     4d): datagram sockets by connection id, sceInetRecvFrom answering -500 when nothing
//     waits, one interface with the address this machine was given;
//   - gfx_vblankHandler: the frame counter, the exchange with the other machine, the
//     input script;
//   - pad_readPort: the raw 8-byte controller record is overwritten from the script;
//   - tasks_run: the call from net_frameLoop is one lockstep tick - the tick log and the
//     commands a script wants run inside a tick.
//
// Two transports under the sockets:
//
//   RTA_NET_LINK=listen:<path>|connect:<path>
//       the rig's link (CLink): a Unix stream socket, one message each way per vertical
//       blank with the frame number and the datagrams sent since the last one.  The two
//       machines advance strictly together, so a run repeats exactly, and the peer may be
//       another native instance or an rta_rig runner (--link).
//   RTA_NET_UDP=<base port>
//       host UDP sockets on 127.0.0.1, non-blocking.  The game's address a.b.c.d and
//       port p (4000..4015) is host port base + d*16 + (p - 4000); the first three
//       octets are taken to be this machine's.  Paced by the wall clock (RTA_NET_PACE).
//
// On both, RTA_NET_BUS=delay=N,jitter=N,loss=N,seed=N,stallat=F,stall=N is the rig's bus
// model with the rig's generator and seeding (machine B draws from a different stream).
//
// Everything is configured by environment variables because the runtime's main() refuses
// options it does not know:
//
//   RTA_NET_ADDR=a.b.c.d      this machine's address (default 192.168.1.134)
//   RTA_NET_MACHINE=A|B       script lines tagged A: or B:, the bus and fuzz streams
//   RTA_NET_PEERS=a.b.c.d,... where a broadcast goes on UDP (default .132 and .134 of this net)
//   RTA_NET_PACE=<Hz>         vertical blanks per second of wall time; 0 = as fast as it goes
//                             (default: 0 on a link, 59.94 on UDP)
//   RTA_NET_SCRIPT=<file>     input and conditions in the rig's script language (a subset:
//                             wait at until tapuntil press release tap stick pad poke dump
//                             show echo fuzz quit, ontick N <command>, A:/B: tags)
//   RTA_NET_SYM=<f1>:<f2>...  symbol files (hex address, tab, name) for expressions
//   RTA_NET_TICKLOG=<file>    one row per lockstep tick, the rig's tick-log format
//   RTA_NET_WATCH=<file>      its columns, one name=expr:type per line
//   RTA_NET_LOG=<file>        what the library entries were asked (RTA_NET_LOG_ALL=1: every datagram)
//   RTA_NET_FRAMES=<n>        stop after n vertical blanks
//   RTA_NET_PATCH=<file>      "address value" hex words written into memory at start
//                             (the patch words a patched translation was built from)
//   RTA_NET_ARG=<text>        boot argument for the game's main() (a start from power-on):
//                             --net is the developer LAN start, which needs no lobby server
//   RTA_NET_PADLAT=0|1        frames between a script's controller state and the game reading
//                             it (default 1, the usual figure on the rig)
//   RTA_NET_ALLOW_LEVEL=1     do not end the run when a level change becomes pending (exit
//                             code 7); for a runtime that can read the disc
//
// Every function here runs on the host thread that carries the running guest thread, with
// the runtime's one lock held, so nothing here needs a lock of its own.
#include "recomp.h"
#include "funcs.h"
#include "moved.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cinttypes>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <fcntl.h>
#include <map>
#include <netinet/in.h>
#include <string>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

#ifndef RTA_NET_RT_NOTE
#define RTA_NET_RT_NOTE "runtime: unknown"
#endif

// Present in runtimes that have rt.h's rt_finish (prints the runtime's report); absent in
// older ones, where the shim ends the process itself.
extern void rt_finish(int code) __attribute__((weak_import));

namespace {

enum : u32 {
    G_NETFRAME = 0x4027ac,          // the lockstep tick about to run / just run
    G_PEERS = 0x5bf838, PEER_SIZE = 0x44e0, PEER_OOS = 0x44d7,
    G_PENDING_LEVEL = 0x41b6d0,     // name of the level to load next, empty when none
    TICK_RETURN = 0x13aee8,         // return address of the tick's task pass in net_frameLoop
};
const int ERROR_NO_DATA = -500;     // what the game expects from sceInetRecvFrom when nothing waits

std::string fmt(const char* format, ...) {
    char buffer[1024];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    return buffer;
}
[[noreturn]] void die(const char* format, ...) {
    va_list args;
    va_start(args, format);
    fprintf(stderr, "netshim: ");
    vfprintf(stderr, format, args);
    fprintf(stderr, "\n");
    va_end(args);
    fflush(stdout);
    _exit(2);
}
std::string lower(std::string s) { for (auto& ch : s) ch = (char)tolower((unsigned char)ch); return s; }
std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> out;
    size_t at = 0;
    for (;;) {
        size_t next = s.find(sep, at);
        if (next == std::string::npos) { out.push_back(s.substr(at)); break; }
        out.push_back(s.substr(at, next - at));
        at = next + 1;
    }
    if (out.size() == 1 && out[0].empty()) out.clear();
    return out;
}
bool parse_number(const std::string& s, s64& out) {
    if (s.empty()) return false;
    char* end = nullptr;
    out = strtoll(s.c_str(), &end, 0);
    return end && *end == 0;
}
double wall_seconds() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}
double cpu_seconds() {
    rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    return usage.ru_utime.tv_sec + usage.ru_utime.tv_usec * 1e-6 + usage.ru_stime.tv_sec + usage.ru_stime.tv_usec * 1e-6;
}

// ---- guest memory, as the rig's Machine sees it (main memory and its mirrors) -----------
u8* gptr(u32 address, u32 length) {
    if ((address & 0xF0000000u) == 0x70000000u) return nullptr;         // the scratchpad is the runtime's
    u32 physical = party8_at(address) & 0x1FFFFFFFu;   // a table moved for eight players is read where it is (moved.h)
    if ((u64)physical + length > RAM_SIZE) return nullptr;
    return g_ram + physical;
}
u32 read32(u32 address) { u32 v = 0; if (u8* p = gptr(address, 4)) memcpy(&v, p, 4); return v; }
void write32(u32 address, u32 value) { if (u8* p = gptr(address, 4)) memcpy(p, &value, 4); }

// ---- expressions and typed values: the rig's grammar and formats ------------------------
std::unordered_map<std::string, u32> g_symbols;

struct Expr {
    enum Op : u8 { NUM, ADD, SUB, MUL, AND, DEREF };
    struct Node { Op op; u32 value; };
    std::vector<Node> code;
    u32 eval() const {
        u32 stack[34];
        int sp = 0;
        for (const Node& n : code) {
            switch (n.op) {
            case NUM: stack[sp++] = n.value; break;
            case DEREF: stack[sp - 1] = read32(stack[sp - 1]); break;
            case ADD: sp--; stack[sp - 1] += stack[sp]; break;
            case SUB: sp--; stack[sp - 1] -= stack[sp]; break;
            case MUL: sp--; stack[sp - 1] *= stack[sp]; break;
            case AND: sp--; stack[sp - 1] &= stack[sp]; break;
            }
        }
        return sp > 0 ? stack[0] : 0;
    }
};
struct ExprParser {
    std::string text;
    size_t pos = 0;
    Expr parse() {
        Expr e;
        sum(e);
        space();
        if (pos != text.size()) die("cannot parse expression '%s' at '%s'", text.c_str(), text.c_str() + pos);
        if (e.code.size() > 30) die("expression too long: %s", text.c_str());
        return e;
    }
    void space() { while (pos < text.size() && isspace((unsigned char)text[pos])) pos++; }
    bool accept(char ch) { space(); if (pos < text.size() && text[pos] == ch) { pos++; return true; } return false; }
    void sum(Expr& e) {
        product(e);
        for (;;) {
            if (accept('+')) { product(e); e.code.push_back({Expr::ADD, 0}); }
            else if (accept('-')) { product(e); e.code.push_back({Expr::SUB, 0}); }
            else if (accept('&')) { product(e); e.code.push_back({Expr::AND, 0}); }
            else break;
        }
    }
    void product(Expr& e) { atom(e); while (accept('*')) { atom(e); e.code.push_back({Expr::MUL, 0}); } }
    void atom(Expr& e) {
        space();
        if (accept('[')) { sum(e); if (!accept(']')) die("missing ] in '%s'", text.c_str()); e.code.push_back({Expr::DEREF, 0}); return; }
        if (accept('(')) { sum(e); if (!accept(')')) die("missing ) in '%s'", text.c_str()); return; }
        std::string word;
        while (pos < text.size() && (isalnum((unsigned char)text[pos]) || text[pos] == '_' || text[pos] == '.')) word += text[pos++];
        if (word.empty()) die("cannot parse expression '%s' (registers are not available here)", text.c_str());
        if (isdigit((unsigned char)word[0])) {
            s64 value = 0;
            if (!parse_number(word, value)) die("bad number '%s' in '%s' (hex needs 0x)", word.c_str(), text.c_str());
            e.code.push_back({Expr::NUM, (u32)value});
            return;
        }
        auto symbol = g_symbols.find(word);
        if (symbol == g_symbols.end()) die("unknown symbol '%s' in '%s' (RTA_NET_SYM)", word.c_str(), text.c_str());
        e.code.push_back({Expr::NUM, symbol->second});
    }
};

struct Type { enum Kind { UINT, SINT, HEXINT, FLOAT, STR, BYTES, CRC } kind = HEXINT; u32 size = 4; };
Type parse_type(const std::string& given) {
    std::string t = lower(given);
    Type type;
    auto sized = [&](const char* prefix, Type::Kind kind, u32 fallback) {
        size_t length = strlen(prefix);
        if (t.compare(0, length, prefix) != 0) return false;
        std::string rest = t.substr(length);
        u32 size = fallback;
        if (!rest.empty()) {
            s64 value = 0;
            if (!parse_number(rest, value) || value <= 0 || value > 0x100000) return false;
            size = (u32)value;
        }
        type.kind = kind;
        type.size = size;
        return true;
    };
    if (t == "f32" || t == "float") { type.kind = Type::FLOAT; return type; }
    if (sized("str", Type::STR, 64) || sized("hex", Type::BYTES, 16) || sized("crc", Type::CRC, 16)) return type;
    if (t.size() >= 2 && (t[0] == 'u' || t[0] == 's' || t[0] == 'x')) {
        s64 bits = 0;
        if (parse_number(t.substr(1), bits) && (bits == 8 || bits == 16 || bits == 32)) {
            type.kind = t[0] == 'u' ? Type::UINT : t[0] == 's' ? Type::SINT : Type::HEXINT;
            type.size = (u32)(bits / 8);
            return type;
        }
    }
    die("unknown type '%s' (u8 s8 u16 s16 u32 s32 x8 x16 x32 f32 strN hexN crcN)", given.c_str());
}
struct Value {
    bool is_text = false, is_float = false;
    s64 integer = 0;
    double real = 0;
    std::string text;
    double as_real() const { return is_float ? real : (double)integer; }
    bool operator==(const Value& o) const {
        if (is_text != o.is_text) return false;
        if (is_text) return text == o.text;
        if (is_float || o.is_float) return as_real() == o.as_real();
        return integer == o.integer;
    }
};
Value read_value(u32 address, const Type& type) {
    Value value;
    const u8* p = gptr(address, type.size);
    if (!p) { value.is_text = true; value.text = "<unmapped>"; return value; }
    u32 raw = 0;
    switch (type.kind) {
    case Type::UINT: case Type::HEXINT: memcpy(&raw, p, type.size); value.integer = raw; break;
    case Type::SINT:
        memcpy(&raw, p, type.size);
        value.integer = type.size == 1 ? (s64)(s8)raw : type.size == 2 ? (s64)(s16)raw : (s64)(s32)raw;
        break;
    case Type::FLOAT: { float f; memcpy(&f, p, 4); value.is_float = true; value.real = f; break; }
    case Type::STR:
        value.is_text = true;
        for (u32 i = 0; i < type.size && p[i] != 0; i++) value.text += (char)p[i];
        break;
    case Type::BYTES:
        value.is_text = true;
        for (u32 i = 0; i < type.size; i++) value.text += fmt("%02x", p[i]);
        break;
    case Type::CRC: {                       // FNV-1a, 32 bits, as the rig's crcN
        u32 hash = 0x811C9DC5u;
        for (u32 i = 0; i < type.size; i++) hash = (hash ^ p[i]) * 0x01000193u;
        value.is_text = true;
        value.text = fmt("%08x", hash);
        break;
    }
    }
    return value;
}
std::string format_value(const Value& value, const Type& type) {
    if (value.is_text) {
        if (type.kind != Type::STR) return value.text;
        std::string out;
        for (unsigned char ch : value.text) {
            if (ch == '\t' || ch == '\n' || ch == '\r' || ch == '\\' || ch < 0x20 || ch >= 0x7f) out += fmt("\\x%02x", ch);
            else out += (char)ch;
        }
        return out;
    }
    if (value.is_float) return fmt("%.9g", value.real);
    if (type.kind == Type::HEXINT) return fmt("%0*" PRIx64, (int)(type.size * 2), value.integer);
    return fmt("%" PRId64, value.integer);
}
struct Watch { std::string name; Expr expr; Type type; };
Watch parse_watch(const std::string& spec) {
    Watch watch;
    std::string rest = spec;
    size_t equals = spec.find('=');
    if (equals != std::string::npos) { watch.name = spec.substr(0, equals); rest = spec.substr(equals + 1); }
    int depth = 0;
    size_t colon = std::string::npos;
    for (size_t i = 0; i < rest.size(); i++) {
        if (rest[i] == '[' || rest[i] == '(') depth++;
        if (rest[i] == ']' || rest[i] == ')') depth--;
        if (rest[i] == ':' && depth == 0) colon = i;
    }
    std::string expr_text = colon == std::string::npos ? rest : rest.substr(0, colon);
    std::string type_text = colon == std::string::npos ? "x32" : rest.substr(colon + 1);
    if (watch.name.empty()) watch.name = expr_text;
    watch.expr = ExprParser{expr_text}.parse();
    watch.type = parse_type(type_text);
    return watch;
}
std::string show(const Watch& w) { u32 a = w.expr.eval(); return fmt("%s@%08x=%s", w.name.c_str(), a, format_value(read_value(a, w.type), w.type).c_str()); }

struct Condition {
    enum Op { EQ, NE, LT, LE, GT, GE, CHANGED } op = EQ;
    Watch watch;
    Value reference;
    std::string text;
    bool test() const {
        Value value = read_value(watch.expr.eval(), watch.type);
        switch (op) {
        case EQ: return value == reference;
        case NE: case CHANGED: return !(value == reference);
        case LT: return value.as_real() < reference.as_real();
        case LE: return value.as_real() <= reference.as_real();
        case GT: return value.as_real() > reference.as_real();
        case GE: return value.as_real() >= reference.as_real();
        }
        return false;
    }
};
Condition parse_condition(const std::vector<std::string>& tokens, size_t first, size_t& next) {
    if (first + 1 >= tokens.size()) die("condition needs '<expr:type> <op> <value>' or '<expr:type> changed'");
    Condition c;
    c.watch = parse_watch(tokens[first]);
    const std::string& op = tokens[first + 1];
    c.text = tokens[first] + " " + op;
    if (op == "changed") { c.op = Condition::CHANGED; next = first + 2; return c; }
    if (op == "==") c.op = Condition::EQ; else if (op == "!=") c.op = Condition::NE; else if (op == "<") c.op = Condition::LT;
    else if (op == "<=") c.op = Condition::LE; else if (op == ">") c.op = Condition::GT; else if (op == ">=") c.op = Condition::GE;
    else die("unknown comparison '%s'", op.c_str());
    if (first + 2 >= tokens.size()) die("condition '%s' needs a value", c.text.c_str());
    const std::string& value = tokens[first + 2];
    c.text += " " + value;
    if (c.watch.type.kind == Type::STR || c.watch.type.kind == Type::BYTES) { c.reference.is_text = true; c.reference.text = value; }
    else {
        s64 integer = 0;
        if (parse_number(value, integer)) {
            c.reference.integer = integer;
            if (c.watch.type.kind == Type::FLOAT) { c.reference.is_float = true; c.reference.real = (double)integer; }
        } else {
            char* end = nullptr;
            double real = strtod(value.c_str(), &end);
            if (!end || *end != 0) die("bad value '%s' in condition", value.c_str());
            c.reference.is_float = true;
            c.reference.real = real;
        }
    }
    next = first + 3;
    return c;
}

// ---- controller ---------------------------------------------------------------------------
// Buttons are kept by the index the rig uses (the Play! emulator's button order), so that
// the rig's "fuzz" command draws the same input here.
enum Button { AX_LX, AX_LY, AX_RX, AX_RY, B_UP, B_DOWN, B_LEFT, B_RIGHT, B_SELECT, B_START, B_SQUARE, B_TRIANGLE,
              B_CIRCLE, B_CROSS, B_L1, B_L2, B_L3, B_R1, B_R2, B_R3, B_MAX };
// bit of each button in the first 16 bits of pad_readPort's record (docs/netcode.md, input record +4)
const u16 RECORD_BIT[B_MAX] = {0, 0, 0, 0, 0x1000, 0x4000, 0x8000, 0x2000, 0x0100, 0x0800, 0x0080, 0x0010,
                               0x0020, 0x0040, 0x0004, 0x0001, 0x0200, 0x0008, 0x0002, 0x0400};
struct Pad { u32 buttons = 0; u8 axis[4] = {0x80, 0x80, 0x80, 0x80}; };
u32 parse_buttons(const std::string& text) {
    static const std::map<std::string, int> names = {
        {"up", B_UP}, {"down", B_DOWN}, {"left", B_LEFT}, {"right", B_RIGHT}, {"select", B_SELECT}, {"start", B_START},
        {"square", B_SQUARE}, {"triangle", B_TRIANGLE}, {"circle", B_CIRCLE}, {"cross", B_CROSS}, {"x", B_CROSS},
        {"l1", B_L1}, {"l2", B_L2}, {"l3", B_L3}, {"r1", B_R1}, {"r2", B_R2}, {"r3", B_R3}};
    u32 mask = 0;
    std::string list = lower(text);
    for (auto& ch : list) if (ch == ',' || ch == '|') ch = '+';
    for (const auto& name : split(list, '+')) {
        if (name.empty() || name == "none" || name == "-") continue;
        auto it = names.find(name);
        if (it == names.end()) die("unknown button '%s'", name.c_str());
        mask |= 1u << it->second;
    }
    return mask;
}
struct FuzzButton { const char* group; Button button; u32 rate, hold_min, hold_span; };
const FuzzButton FUZZ_BUTTONS[] = {             // the rig's table: presses per thousand frames, hold in frames
    {"fight", B_CROSS, 60, 2, 8}, {"fight", B_CIRCLE, 10, 2, 20}, {"fight", B_TRIANGLE, 10, 2, 20}, {"fight", B_R1, 10, 10, 40},
    {"fight", B_L1, 4, 2, 4}, {"cast", B_CIRCLE, 40, 2, 20}, {"cast", B_TRIANGLE, 40, 2, 20}, {"potion", B_R2, 8, 2, 4},
    {"potion", B_L2, 8, 2, 4}, {"use", B_SQUARE, 15, 2, 6}, {"dpad", B_UP, 6, 4, 30}, {"dpad", B_DOWN, 6, 4, 30},
    {"dpad", B_LEFT, 6, 4, 30}, {"dpad", B_RIGHT, 6, 4, 30}, {"select", B_SELECT, 4, 2, 3}, {"start", B_START, 3, 2, 3},
    {"l3r3", B_L3, 2, 2, 3}, {"l3r3", B_R3, 2, 2, 3},
};
enum : u32 { FUZZ_MOVE = 1u << 30, FUZZ_RSTICK = 1u << 31 };

// ---- the bus model (the rig's BusModel) -------------------------------------------------
struct Bus {
    u32 delay = 0, jitter = 0, loss = 0;
    u64 stall_at = 0, stall_frames = 0;
    u64 state = 0x9E3779B97F4A7C15ull;
    u64 next() {
        state ^= state >> 12;
        state ^= state << 25;
        state ^= state >> 27;
        return state * 0x2545F4914F6CDD1Dull;
    }
};

struct Wire {                       // a datagram on its way to another machine
    u64 deliver_frame = 0;
    u8 source[4] = {};
    u32 source_port = 0;
    u8 destination[4] = {};
    u32 destination_port = 0;
    std::vector<u8> data;
};
struct Datagram { std::vector<u8> data; u8 address[4] = {}; u32 port = 0; u64 frame = 0; };
struct Socket { u32 type = 0, port = 0; std::deque<Datagram> queue; int fd = -1; };

// ---- script -------------------------------------------------------------------------------
struct Command {
    enum Kind { WAIT, AT, UNTIL, PRESS, RELEASE, TAP, TAPUNTIL, STICK, PAD, POKE, DUMP, SHOW, ECHO, FUZZ, QUIT, NOP } kind = WAIT;
    int line = 0;
    s64 number = 0, number2 = 0;
    u32 buttons = 0;
    u8 axis[4] = {0x80, 0x80, 0x80, 0x80};
    int axis_first = 0, axis_count = 0;
    bool flag = false;
    std::string text;
    Condition condition;
    std::vector<Watch> watches;
    Watch target;
    std::vector<u8> bytes;
    bool started = false;
    u64 deadline = 0, phase_start = 0;
    u64 rng = 0;
    u32 fuzz_mask = 0, stick_hold[2] = {}, button_hold[B_MAX] = {};
};

struct Shim {
    bool started = false, finished = false;
    u8 own[4] = {134, 1, 168, 192};         // low byte first, as the game keeps addresses
    char machine = 'A';
    u64 frame = 0, ticks = 0;
    u64 frames_wanted = 0;
    double start_wall = 0, start_cpu = 0, pace = 0;
    // sockets
    std::map<s32, Socket> sockets;
    s32 next_id = 1;
    u64 calls[10] = {}, sent = 0, received = 0, lost = 0, crossed = 0;
    FILE* log = nullptr;
    bool log_all = false;
    // transports
    int link_fd = -1;
    std::string link_spec;
    bool linked = false;                    // datagrams for other machines leave this one
    Bus bus;
    std::vector<Wire> outbox;
    int udp_base = 0;
    std::vector<u8> udp_peers;              // last octets a broadcast goes to
    // tick log and script
    FILE* tick_log = nullptr;
    std::vector<Watch> tick_watches;
    std::vector<Command> commands;
    std::multimap<u32, Command> tick_actions;
    size_t position = 0;
    bool script_given = false, script_done = false;
    Pad pad;                                // what the script holds now
    Pad pad_seen;                           // what the game reads: the script's state one blank earlier
    bool pad_override = false;
    int pad_latency = 1;
    bool stop_on_level = true;
    bool oos_reported[4] = {};
    u64 nothing_reads = 0, nothing_stores = 0;  // --wrap-memory: accesses where nothing is
};
Shim S;

void net_log(const char* format, ...) {
    if (!S.log) return;
    va_list args;
    va_start(args, format);
    fprintf(S.log, "frame=%" PRIu64 " ", S.frame);
    vfprintf(S.log, format, args);
    fprintf(S.log, "\n");
    va_end(args);
}
std::string hex(const std::vector<u8>& data, size_t limit) {
    std::string text;
    for (size_t i = 0; i < data.size() && i < limit; i++) text += fmt("%02x", data[i]);
    return text;
}

// ---- the link (the rig's CLink wire format) ------------------------------------------------
const u32 LINK_MAGIC = 0x52494731;
void link_open(const std::string& spec) {
    size_t colon = spec.find(':');
    if (colon == std::string::npos) die("RTA_NET_LINK wants listen:<path> or connect:<path>");
    std::string mode = spec.substr(0, colon), path = spec.substr(colon + 1);
    sockaddr_un address = {};
    address.sun_family = AF_UNIX;
    if (path.size() >= sizeof(address.sun_path)) die("RTA_NET_LINK: path too long");
    strcpy(address.sun_path, path.c_str());
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) die("RTA_NET_LINK: cannot make a socket");
    if (mode == "listen") {
        unlink(path.c_str());
        if (bind(fd, (sockaddr*)&address, sizeof(address)) != 0 || listen(fd, 1) != 0) die("RTA_NET_LINK: cannot listen on %s", path.c_str());
        S.link_fd = accept(fd, nullptr, nullptr);
        close(fd);
        unlink(path.c_str());
        if (S.link_fd < 0) die("RTA_NET_LINK: accept failed");
    } else if (mode == "connect") {
        for (int attempt = 0; attempt < 600 && S.link_fd < 0; attempt++) {
            if (connect(fd, (sockaddr*)&address, sizeof(address)) == 0) S.link_fd = fd;
            else usleep(100000);
        }
        if (S.link_fd < 0) die("RTA_NET_LINK: nobody is listening on %s", path.c_str());
    } else die("RTA_NET_LINK wants listen:<path> or connect:<path>");
}
void link_send(u64 frame, bool bye, const std::vector<Wire>& datagrams) {
    std::vector<u8> m;
    auto put32 = [&](u32 v) { m.insert(m.end(), (u8*)&v, (u8*)&v + 4); };
    auto put64 = [&](u64 v) { m.insert(m.end(), (u8*)&v, (u8*)&v + 8); };
    put32(LINK_MAGIC); put32(bye ? 1 : 0); put64(frame); put32((u32)datagrams.size());
    for (const Wire& d : datagrams) {
        put64(d.deliver_frame);
        m.insert(m.end(), d.source, d.source + 4); put32(d.source_port);
        m.insert(m.end(), d.destination, d.destination + 4); put32(d.destination_port);
        put32((u32)d.data.size());
        m.insert(m.end(), d.data.begin(), d.data.end());
    }
    const u8* p = m.data();
    size_t left = m.size();
    while (left > 0) {
        ssize_t n = write(S.link_fd, p, left);
        if (n <= 0) return;             // the other side is gone; the next receive reports it
        p += n; left -= (size_t)n;
    }
}
bool link_read(void* into, size_t size) {
    u8* p = (u8*)into;
    while (size > 0) {
        ssize_t n = read(S.link_fd, p, size);
        if (n <= 0) return false;
        p += n; size -= (size_t)n;
    }
    return true;
}
bool link_receive(u64& frame, bool& bye, std::vector<Wire>& datagrams) {
    u32 magic = 0, flags = 0, count = 0;
    if (!link_read(&magic, 4) || magic != LINK_MAGIC || !link_read(&flags, 4) || !link_read(&frame, 8) || !link_read(&count, 4)) return false;
    bye = flags & 1;
    for (u32 i = 0; i < count; i++) {
        Wire d;
        u32 length = 0;
        if (!link_read(&d.deliver_frame, 8) || !link_read(d.source, 4) || !link_read(&d.source_port, 4) || !link_read(d.destination, 4)
            || !link_read(&d.destination_port, 4) || !link_read(&length, 4) || length > 0x10000) return false;
        d.data.resize(length);
        if (length && !link_read(d.data.data(), length)) return false;
        datagrams.push_back(std::move(d));
    }
    return true;
}

[[noreturn]] void finish(int code) {
    S.finished = true;
    if (S.link_fd >= 0 && code != 6) link_send(S.frame, true, {});
    double wall = wall_seconds() - S.start_wall, cpu = cpu_seconds() - S.start_cpu;
    double load[3] = {0, 0, 0};
    getloadavg(load, 3);
    static const char* names[10] = {"sceLibnetInitialize", "sceInetGetInterfaceList", "sceInetInterfaceControl", "sceInetCreate", "sceInetOpen",
                                    "sceInetClose", "sceInetSendTo", "sceInetRecvFrom", "net_loadModules", "net_linkCheck"};
    printf("net shim: machine %c, frames=%" PRIu64 " ticks=%" PRIu64 " wall=%.3fs cpu=%.3fs: %.1f ticks per second of wall time "
           "(%.2fx real time at 59.94), %.1f frames per second, %.1f ticks per cpu-second of this process; load average %.1f\n",
           S.machine, S.frame, S.ticks, wall, cpu, wall > 0 ? S.ticks / wall : 0, wall > 0 ? S.ticks / wall / 59.94 : 0,
           wall > 0 ? S.frame / wall : 0, cpu > 0 ? S.ticks / cpu : 0, load[0]);
    printf("net shim: %" PRIu64 " datagrams sent (%" PRIu64 " to another machine, %" PRIu64 " lost on the bus), %" PRIu64 " received; calls:",
           S.sent, S.crossed, S.lost, S.received);
    for (int i = 0; i < 10; i++) printf(" %s=%" PRIu64, names[i], S.calls[i]);
    printf("\n");
#ifdef RTA_NET_WRAP_MEMORY
    printf("net shim: accesses where nothing is, answered as the emulator answers: %" PRIu64 " reads, %" PRIu64 " stores\n", S.nothing_reads, S.nothing_stores);
#endif
    printf("net shim: exit code %d\n", code);
    if (S.log) fclose(S.log);
    if (S.tick_log) fclose(S.tick_log);
    fflush(stdout);
    fflush(stderr);
    if (&rt_finish != nullptr) rt_finish(code);
    _exit(code);
}

// ---- sockets ------------------------------------------------------------------------------
int udp_host_port(u8 last_octet, u32 port) { return S.udp_base + last_octet * 16 + (int)(port - 4000); }
void udp_bind(Socket& socket) {
    if (!S.udp_base || socket.fd >= 0) return;
    if (socket.port < 4000 || socket.port > 4015) { net_log("udp: port %u is outside 4000..4015, the socket stays local", socket.port); return; }
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in address = {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons((u16)udp_host_port(S.own[0], socket.port));
    int on = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    if (fd < 0 || bind(fd, (sockaddr*)&address, sizeof(address)) != 0) die("udp: cannot bind 127.0.0.1:%d (%s)", ntohs(address.sin_port), strerror(errno));
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
    socket.fd = fd;
    net_log("udp: port %u is 127.0.0.1:%d", socket.port, ntohs(address.sin_port));
}
// A connection id the shim did not hand out (the memory image was taken inside a net
// game) is taken to be the game's own socket, which is on port 4000.
Socket& socket_of(s32 id) {
    auto found = S.sockets.find(id);
    if (found != S.sockets.end()) return found->second;
    Socket socket;
    socket.port = 4000;
    if (id >= S.next_id) S.next_id = id + 1;
    Socket& made = S.sockets[id] = socket;
    udp_bind(made);
    return made;
}
void enqueue(Socket& socket, const Datagram& datagram) {     // in order of delivery frame, arrival order within one
    auto position = socket.queue.end();
    while (position != socket.queue.begin() && (position - 1)->frame > datagram.frame) --position;
    socket.queue.insert(position, datagram);
}
void deliver(const Wire& wire) {                             // from the other machine
    bool broadcast = wire.destination[0] == 0xff;
    if (!broadcast && memcmp(wire.destination, S.own, 4) != 0) {
        net_log("bus: datagram for %d.%d.%d.%d is not for this machine, dropped", wire.destination[3], wire.destination[2], wire.destination[1], wire.destination[0]);
        return;
    }
    Datagram datagram;
    datagram.data = wire.data;
    memcpy(datagram.address, wire.source, 4);
    datagram.port = wire.source_port;
    datagram.frame = wire.deliver_frame;
    socket_of(1);
    for (auto& socket : S.sockets)
        if (socket.second.port == wire.destination_port) enqueue(socket.second, datagram);
}
void udp_flush() {                                           // datagrams whose delay has passed go out
    size_t kept = 0;
    for (size_t i = 0; i < S.outbox.size(); i++) {
        Wire& wire = S.outbox[i];
        if (wire.deliver_frame > S.frame + 1) { if (kept != i) S.outbox[kept] = std::move(wire); kept++; continue; }
        int fd = -1;
        for (auto& socket : S.sockets) if (socket.second.port == wire.source_port && socket.second.fd >= 0) fd = socket.second.fd;
        if (fd < 0) continue;
        std::vector<u8> targets;
        if (wire.destination[0] == 0xff) targets = S.udp_peers; else targets.push_back(wire.destination[0]);
        for (u8 octet : targets) {
            if (octet == S.own[0]) continue;
            sockaddr_in to = {};
            to.sin_family = AF_INET;
            to.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            to.sin_port = htons((u16)udp_host_port(octet, wire.destination_port));
            sendto(fd, wire.data.data(), wire.data.size(), 0, (sockaddr*)&to, sizeof(to));
        }
    }
    S.outbox.resize(kept);
}
void udp_drain() {                                           // what arrived becomes receivable from this frame on
    u8 buffer[0x10000];
    for (auto& entry : S.sockets) {
        Socket& socket = entry.second;
        if (socket.fd < 0) continue;
        for (;;) {
            sockaddr_in from = {};
            socklen_t length = sizeof(from);
            ssize_t n = recvfrom(socket.fd, buffer, sizeof(buffer), 0, (sockaddr*)&from, &length);
            if (n < 0) break;
            int offset = (int)ntohs(from.sin_port) - S.udp_base;
            if (offset < 0 || offset >= 256 * 16) continue;         // not one of ours
            Datagram datagram;
            datagram.data.assign(buffer, buffer + n);
            datagram.address[0] = (u8)(offset / 16);
            memcpy(datagram.address + 1, S.own + 1, 3);
            datagram.port = 4000 + offset % 16;
            datagram.frame = S.frame;
            enqueue(socket, datagram);
        }
    }
}

void exchange_with_peer() {
    link_send(S.frame, false, S.outbox);
    S.outbox.clear();
    u64 peer_frame = 0;
    bool bye = false;
    std::vector<Wire> incoming;
    if (!link_receive(peer_frame, bye, incoming)) { printf("[frame %" PRIu64 "] the other machine is gone\n", S.frame); finish(6); }
    if (bye) { printf("[frame %" PRIu64 "] the other machine ended its run\n", S.frame); finish(6); }
    if (peer_frame != S.frame) { printf("[frame %" PRIu64 "] the other machine is at frame %" PRIu64 ": the two are out of step\n", S.frame, peer_frame); finish(6); }
    for (const Wire& wire : incoming) deliver(wire);
}

// ---- script: parsing ------------------------------------------------------------------------
std::vector<std::string> tokenize(const std::string& line) {
    std::vector<std::string> out;
    size_t i = 0;
    while (i < line.size()) {
        if (isspace((unsigned char)line[i])) { i++; continue; }
        if (line[i] == '#') break;
        std::string token;
        if (line[i] == '"') { i++; while (i < line.size() && line[i] != '"') token += line[i++]; if (i < line.size()) i++; }
        else while (i < line.size() && !isspace((unsigned char)line[i])) token += line[i++];
        out.push_back(token);
    }
    return out;
}
void parse_line(const std::string& text, int number);
void parse_tokens(std::vector<std::string> tokens, int line) {
    if (tokens.empty()) return;
    auto rejoin = [&](size_t first) {
        std::string rest;
        for (size_t k = first; k < tokens.size(); k++) {
            bool quote = tokens[k].find(' ') != std::string::npos || tokens[k].empty();
            rest += (k > first ? " " : "") + (quote ? "\"" + tokens[k] + "\"" : tokens[k]);
        }
        return rest;
    };
    if (tokens[0] == "A:" || tokens[0] == "B:" || tokens[0] == "a:" || tokens[0] == "b:") {
        bool mine = toupper((unsigned char)tokens[0][0]) == S.machine;
        size_t before = S.commands.size();
        auto actions_before = S.tick_actions;
        parse_line(rejoin(1), line);
        if (mine) return;
        S.tick_actions = actions_before;
        std::vector<Command> kept;                      // the other machine's command: let the same frames pass
        for (size_t k = before; k < S.commands.size(); k++) {
            Command other = S.commands[k];
            switch (other.kind) {
            case Command::WAIT: case Command::AT: case Command::UNTIL: kept.push_back(other); break;
            case Command::TAP: other.kind = Command::WAIT; other.number += other.number2; kept.push_back(other); break;
            case Command::TAPUNTIL: other.buttons = 0; kept.push_back(other); break;
            case Command::FUZZ: other.kind = Command::WAIT; other.number = other.number2; kept.push_back(other); break;
            default: break;
            }
        }
        S.commands.resize(before);
        S.commands.insert(S.commands.end(), kept.begin(), kept.end());
        return;
    }
    if (lower(tokens[0]) == "ontick") {
        s64 tick = 0;
        if (tokens.size() < 3 || !parse_number(tokens[1], tick)) die("script line %d: ontick <tick> <command>", line);
        size_t before = S.commands.size();
        parse_line(rejoin(2), line);
        for (size_t k = before; k < S.commands.size(); k++) S.tick_actions.emplace((u32)tick, S.commands[k]);
        S.commands.resize(before);
        return;
    }
    Command c;
    c.line = line;
    size_t i = 0;
    std::string word = lower(tokens[i++]);
    auto need = [&](size_t count) { if (tokens.size() < i + count) die("script line %d: '%s' needs more arguments", line, word.c_str()); };
    auto number = [&](const std::string& t) { s64 v = 0; if (!parse_number(t, v)) die("script line %d: bad number '%s'", line, t.c_str()); return v; };
    if (isdigit((unsigned char)word[0])) {              // "<frame> <buttons> [lx ly [rx ry]]"
        Command at;
        at.kind = Command::AT; at.line = line; at.number = number(word);
        S.commands.push_back(at);
        word = "pad";
    }
    if (word.size() > 1 && word.back() == '1') word.pop_back();          // port 1 is the only port driven here
    if (word == "wait") { need(1); c.kind = Command::WAIT; c.number = number(tokens[i]); }
    else if (word == "at") { need(1); c.kind = Command::AT; c.number = number(tokens[i]); }
    else if (word == "until") {
        c.kind = Command::UNTIL;
        size_t next = 0;
        c.condition = parse_condition(tokens, i, next);
        if (next < tokens.size() && lower(tokens[next]) == "timeout") {
            if (next + 1 >= tokens.size()) die("script line %d: timeout needs a frame count", line);
            c.number = number(tokens[next + 1]);
            next += 2;
        }
        if (next < tokens.size() && lower(tokens[next]) == "continue") c.flag = true;
    }
    else if (word == "press" || word == "release") { need(1); c.kind = word == "press" ? Command::PRESS : Command::RELEASE; c.buttons = parse_buttons(tokens[i]); }
    else if (word == "tap") {
        need(1);
        c.kind = Command::TAP;
        c.buttons = parse_buttons(tokens[i]);
        c.number = tokens.size() > i + 1 ? number(tokens[i + 1]) : 3;
        c.number2 = tokens.size() > i + 2 ? number(tokens[i + 2]) : 0;
    }
    else if (word == "tapuntil") {
        need(4);
        c.kind = Command::TAPUNTIL;
        c.buttons = parse_buttons(tokens[i]);
        c.number2 = number(tokens[i + 1]) < 8 ? 8 : number(tokens[i + 1]);
        size_t next = 0;
        c.condition = parse_condition(tokens, i + 2, next);
        if (next + 1 < tokens.size() && lower(tokens[next]) == "timeout") c.number = number(tokens[next + 1]);
    }
    else if (word == "stick") {
        need(3);
        c.kind = Command::STICK;
        std::string which = lower(tokens[i]);
        if (which != "l" && which != "r" && which != "left" && which != "right") die("script line %d: stick L|R x y", line);
        c.axis_first = which[0] == 'l' ? 0 : 2;
        c.axis_count = 2;
        c.axis[0] = (u8)number(tokens[i + 1]);
        c.axis[1] = (u8)number(tokens[i + 2]);
    }
    else if (word == "pad") {
        need(1);
        c.kind = Command::PAD;
        c.buttons = parse_buttons(tokens[i]);
        for (size_t k = 0; k < 4 && i + 1 + k < tokens.size(); k++) { c.axis[k] = (u8)number(tokens[i + 1 + k]); c.axis_count = (int)k + 1; }
    }
    else if (word == "poke") {
        need(2);
        c.kind = Command::POKE;
        c.target = parse_watch(tokens[i]);
        const Type& type = c.target.type;
        const std::string& value = tokens[i + 1];
        if (type.kind == Type::FLOAT) { float f = strtof(value.c_str(), nullptr); c.bytes.resize(4); memcpy(c.bytes.data(), &f, 4); }
        else if (type.kind == Type::STR) { c.bytes.assign(value.begin(), value.end()); c.bytes.push_back(0); }
        else if (type.kind == Type::BYTES) {
            if (value.size() % 2) die("script line %d: odd number of hex digits", line);
            for (size_t k = 0; k + 1 < value.size(); k += 2) c.bytes.push_back((u8)strtoul(value.substr(k, 2).c_str(), nullptr, 16));
        } else {
            s64 v = type.kind == Type::HEXINT ? (s64)strtoull(value.c_str(), nullptr, 16) : number(value);
            c.bytes.resize(type.size);
            memcpy(c.bytes.data(), &v, type.size);
        }
    }
    else if (word == "dump") { need(3); c.kind = Command::DUMP; c.target.expr = ExprParser{tokens[i]}.parse(); c.number = number(tokens[i + 1]); c.text = tokens[i + 2]; }
    else if (word == "show") { need(1); c.kind = Command::SHOW; for (size_t k = i; k < tokens.size(); k++) c.watches.push_back(parse_watch(tokens[k])); }
    else if (word == "echo") { c.kind = Command::ECHO; for (size_t k = i; k < tokens.size(); k++) c.text += (k > i ? " " : "") + tokens[k]; }
    else if (word == "fuzz") {
        need(3);
        c.kind = Command::FUZZ;
        c.number = number(tokens[i]);
        c.number2 = number(tokens[i + 1]);
        for (const auto& group : split(lower(tokens[i + 2]), ',')) {
            bool known = group == "idle";
            if (group == "move") { c.fuzz_mask |= FUZZ_MOVE; known = true; }
            if (group == "rstick") { c.fuzz_mask |= FUZZ_RSTICK; known = true; }
            for (const auto& entry : FUZZ_BUTTONS) if (group == entry.group) { c.fuzz_mask |= 1u << entry.button; known = true; }
            if (!known) die("script line %d: unknown fuzz group '%s'", line, group.c_str());
        }
    }
    else if (word == "quit") c.kind = Command::QUIT;
    else if (word == "netshim" || word == "sync" || word == "log") c.kind = Command::NOP;   // the rig's own business
    else if (word == "pnach") {
        // translated code cannot be patched while it runs: a patched build is another program
        printf("script line %d: pnach is not carried out here (build_net.py --pnach makes the patched program)\n", line);
        c.kind = Command::NOP;
    }
    else die("script line %d: command '%s' is not available in the native shim", line, word.c_str());
    S.commands.push_back(c);
}
void parse_line(const std::string& text, int number) { parse_tokens(tokenize(text), number); }

// ---- script: running --------------------------------------------------------------------------
bool poke(u32 address, const std::vector<u8>& bytes) {
    u8* p = gptr(address, (u32)bytes.size());
    if (!p) return false;
    memcpy(p, bytes.data(), bytes.size());
    return true;
}
void dump(const Command& c, const char* where) {
    u32 address = c.target.expr.eval(), length = (u32)c.number;
    const u8* p = gptr(address, length);
    FILE* file = p ? fopen(c.text.c_str(), "wb") : nullptr;
    if (file) { fwrite(p, 1, length, file); fclose(file); }
    printf("%s frame %" PRIu64 ": %s %s\n", where, S.frame, file ? "dumped" : "DUMP FAILED", c.text.c_str());
}

void step_script() {
    while (!S.finished && S.position < S.commands.size()) {
        Command& c = S.commands[S.position];
        Pad& pad = S.pad;
        switch (c.kind) {
        case Command::WAIT:
            if (!c.started) { c.started = true; c.deadline = S.frame + c.number; }
            if (S.frame < c.deadline) return;
            break;
        case Command::AT:
            if (S.frame < (u64)c.number) return;
            break;
        case Command::UNTIL:
            if (!c.started) {
                c.started = true;
                c.deadline = c.number ? S.frame + c.number : 0;
                if (c.condition.op == Condition::CHANGED) c.condition.reference = read_value(c.condition.watch.expr.eval(), c.condition.watch.type);
            }
            if (!c.condition.test()) {
                if (c.deadline && S.frame >= c.deadline) {
                    printf("[frame %" PRIu64 "] TIMEOUT line %d: until %s\n", S.frame, c.line, c.condition.text.c_str());
                    if (!c.flag) finish(3);
                    break;
                }
                return;
            }
            printf("[frame %" PRIu64 "] until %s\n", S.frame, c.condition.text.c_str());
            break;
        case Command::PRESS: pad.buttons |= c.buttons; break;
        case Command::RELEASE: pad.buttons &= ~c.buttons; break;
        case Command::TAP:
            if (!c.started) { c.started = true; pad.buttons |= c.buttons; c.deadline = S.frame + c.number; return; }
            if (S.frame < c.deadline) return;
            pad.buttons &= ~c.buttons;
            if (c.number2 > 0 && S.frame < c.deadline + c.number2) return;
            break;
        case Command::TAPUNTIL: {
            if (!c.started) {
                c.started = true;
                c.deadline = c.number ? S.frame + c.number : 0;
                c.phase_start = S.frame;
                if (c.condition.op == Condition::CHANGED) c.condition.reference = read_value(c.condition.watch.expr.eval(), c.condition.watch.type);
            }
            u64 phase = (S.frame - c.phase_start) % (u64)c.number2;
            bool done = false;
            if (phase == 0) {
                if (c.condition.test()) { printf("[frame %" PRIu64 "] tapuntil %s\n", S.frame, c.condition.text.c_str()); done = true; }
                else if (c.deadline && S.frame >= c.deadline) { printf("[frame %" PRIu64 "] TIMEOUT line %d: tapuntil %s\n", S.frame, c.line, c.condition.text.c_str()); finish(3); }
                else pad.buttons |= c.buttons;
            } else if (phase == 4) pad.buttons &= ~c.buttons;
            if (!done) return;
            break;
        }
        case Command::STICK: for (int k = 0; k < c.axis_count; k++) pad.axis[c.axis_first + k] = c.axis[k]; break;
        case Command::PAD:
            pad.buttons = c.buttons;
            for (int k = 0; k < 4; k++) pad.axis[k] = k < c.axis_count ? c.axis[k] : 0x80;
            break;
        case Command::POKE: {
            u32 address = c.target.expr.eval();
            if (!poke(address, c.bytes)) printf("[frame %" PRIu64 "] poke %s: address %08x is not mapped\n", S.frame, c.target.name.c_str(), address);
            break;
        }
        case Command::DUMP: dump(c, "[script]"); break;
        case Command::SHOW: {
            std::string line = fmt("[frame %" PRIu64 "]", S.frame);
            for (const Watch& w : c.watches) line += " " + show(w);
            printf("%s\n", line.c_str());
            break;
        }
        case Command::ECHO: printf("[frame %" PRIu64 "] %s\n", S.frame, c.text.c_str()); break;
        case Command::FUZZ: {
            if (!c.started) {
                c.started = true;
                c.deadline = S.frame + c.number2;
                c.rng = 0x9E3779B97F4A7C15ull ^ ((u64)c.number * 0x100000001B3ull) ^ (S.machine == 'B' ? 0x5851F42D4C957F2Dull : 0);
            }
            auto next = [&c]() {
                c.rng ^= c.rng >> 12;
                c.rng ^= c.rng << 25;
                c.rng ^= c.rng >> 27;
                return (u32)((c.rng * 0x2545F4914F6CDD1Dull) >> 32);
            };
            if (S.frame >= c.deadline) {
                for (const auto& entry : FUZZ_BUTTONS) if (c.fuzz_mask & (1u << entry.button)) pad.buttons &= ~(1u << entry.button);
                for (int k = 0; k < 4; k++) pad.axis[k] = 0x80;
                break;
            }
            for (int stick = 0; stick < 2; stick++) {
                if (!(c.fuzz_mask & (stick == 0 ? FUZZ_MOVE : FUZZ_RSTICK))) continue;
                if (c.stick_hold[stick] > 0) { c.stick_hold[stick]--; continue; }
                u32 choice = next() % 8;
                u8 x = 0x80, y = 0x80;
                if (choice >= 2 && choice <= 5) {
                    static const u8 full[8][2] = {{0x80, 0x00}, {0xff, 0x00}, {0xff, 0x80}, {0xff, 0xff}, {0x80, 0xff}, {0x00, 0xff}, {0x00, 0x80}, {0x00, 0x00}};
                    u32 direction = next() % 8;
                    x = full[direction][0];
                    y = full[direction][1];
                } else if (choice >= 6) {
                    x = (u8)next();
                    y = (u8)next();
                }
                pad.axis[stick * 2] = x;
                pad.axis[stick * 2 + 1] = y;
                c.stick_hold[stick] = 5 + next() % 55;
            }
            for (const auto& entry : FUZZ_BUTTONS) {
                if (!(c.fuzz_mask & (1u << entry.button))) continue;
                u32& hold = c.button_hold[entry.button];
                if (hold > 0) { if (--hold == 0) pad.buttons &= ~(1u << entry.button); }
                else if (next() % 1000 < entry.rate) { pad.buttons |= 1u << entry.button; hold = entry.hold_min + next() % entry.hold_span; }
            }
            return;
        }
        case Command::QUIT: finish(0);
        case Command::NOP: break;
        }
        S.position++;
    }
    if (S.position >= S.commands.size()) S.script_done = true;
}

void on_tick() {
    S.ticks++;
    u32 tick = read32(G_NETFRAME);
    if (S.tick_log) {
        fprintf(S.tick_log, "%" PRIu64, S.frame);
        for (const Watch& w : S.tick_watches) fprintf(S.tick_log, "\t%s", format_value(read_value(w.expr.eval(), w.type), w.type).c_str());
        fprintf(S.tick_log, "\n");
    }
    for (u32 n = 0; n < 4; n++)
        if (!S.oos_reported[n] && g_ram[party8_at(G_PEERS + n * PEER_SIZE + PEER_OOS)]) {
            S.oos_reported[n] = true;
            printf("[tick %u] frame %" PRIu64 ": the game holds peer %u OUT OF SYNC\n", tick, S.frame, n);
        }
    // A level name is pending: the main loop will load it after this call.  Until the
    // runtime reads the disc, the run ends here instead of running on garbage.
    if (S.stop_on_level && g_ram[G_PENDING_LEVEL]) {
        char name[17] = {};
        memcpy(name, g_ram + G_PENDING_LEVEL, 16);
        printf("[tick %u] frame %" PRIu64 ": level change to '%s' is pending; the run ends here (RTA_NET_ALLOW_LEVEL=1 lets it go on)\n", tick, S.frame, name);
        finish(7);
    }
    auto range = S.tick_actions.equal_range(tick);
    bool quit = false;
    for (auto it = range.first; it != range.second; ++it) {
        Command& c = it->second;
        switch (c.kind) {
        case Command::POKE: poke(c.target.expr.eval(), c.bytes); break;
        case Command::DUMP: dump(c, fmt("[tick %u]", tick).c_str()); break;
        case Command::SHOW: {
            std::string line = fmt("[tick %u]", tick);
            for (const Watch& w : c.watches) line += " " + show(w);
            printf("%s\n", line.c_str());
            break;
        }
        case Command::ECHO: printf("[tick %u] frame %" PRIu64 ": %s\n", tick, S.frame, c.text.c_str()); break;
        case Command::PRESS: S.pad.buttons |= c.buttons; break;
        case Command::RELEASE: S.pad.buttons &= ~c.buttons; break;
        case Command::QUIT: quit = true; break;
        case Command::NOP: break;
        default: printf("[tick %u] ontick: this command cannot run inside a tick (line %d)\n", tick, c.line); break;
        }
    }
    S.tick_actions.erase(range.first, range.second);
    if (quit) finish(0);
}

// ---- start --------------------------------------------------------------------------------
void start() {
    if (S.started) return;
    S.started = true;
    setvbuf(stdout, nullptr, _IOLBF, 0);
    auto env = [](const char* name) -> std::string { const char* v = getenv(name); return v ? v : ""; };
    std::string value = env("RTA_NET_ADDR");
    if (!value.empty()) {
        unsigned a, b, c, d;
        if (sscanf(value.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4 || a > 255 || b > 255 || c > 255 || d > 255) die("RTA_NET_ADDR wants a.b.c.d");
        S.own[0] = (u8)d; S.own[1] = (u8)c; S.own[2] = (u8)b; S.own[3] = (u8)a;
    }
    value = env("RTA_NET_MACHINE");
    if (!value.empty()) { S.machine = (char)toupper((unsigned char)value[0]); if (S.machine != 'A' && S.machine != 'B') die("RTA_NET_MACHINE A or B"); }
    for (const auto& path : split(env("RTA_NET_SYM"), ':')) {
        FILE* f = fopen(path.c_str(), "r");
        if (!f) die("cannot read symbol file %s", path.c_str());
        char line[2048];
        while (fgets(line, sizeof(line), f)) {
            if (line[0] == '#' || line[0] == '\n') continue;
            auto fields = split(std::string(line, strcspn(line, "\r\n")), '\t');
            if (fields.size() < 2 || fields[1].empty()) continue;
            char* end = nullptr;
            u32 address = (u32)strtoul(fields[0].c_str(), &end, 16);
            if (!end || *end != 0) continue;
            g_symbols.emplace(fields[1], address);
        }
        fclose(f);
    }
    value = env("RTA_NET_BUS");
    for (const auto& part : split(value, ',')) {
        size_t equals = part.find('=');
        s64 number = 0;
        if (equals == std::string::npos || !parse_number(part.substr(equals + 1), number) || number < 0) die("RTA_NET_BUS delay=N,jitter=N,loss=N,seed=N,stallat=F,stall=N");
        std::string key = part.substr(0, equals);
        if (key == "delay") S.bus.delay = (u32)number;
        else if (key == "jitter") S.bus.jitter = (u32)number;
        else if (key == "loss") S.bus.loss = (u32)number;
        else if (key == "seed") S.bus.state = 0x9E3779B97F4A7C15ull ^ ((u64)number * 0x100000001B3ull);
        else if (key == "stallat") S.bus.stall_at = (u64)number;
        else if (key == "stall") S.bus.stall_frames = (u64)number;
        else die("RTA_NET_BUS: unknown key '%s'", key.c_str());
    }
    if (S.machine == 'B') S.bus.state ^= 0xD6E8FEB86659FD93ull;
    value = env("RTA_NET_LOG");
    if (!value.empty() && !(S.log = fopen(value.c_str(), "w"))) die("cannot write %s", value.c_str());
    S.log_all = !env("RTA_NET_LOG_ALL").empty();
    value = env("RTA_NET_FRAMES");
    if (!value.empty()) S.frames_wanted = strtoull(value.c_str(), nullptr, 0);
    value = env("RTA_NET_PATCH");
    if (!value.empty()) {
        FILE* f = fopen(value.c_str(), "r");
        if (!f) die("cannot read %s", value.c_str());
        unsigned address, word, count = 0;
        while (fscanf(f, "%x %x", &address, &word) == 2) { write32(address, word); count++; }
        fclose(f);
        printf("net shim: %u patch words written into memory\n", count);
    }
    value = env("RTA_NET_WATCH");
    if (!value.empty()) {
        FILE* f = fopen(value.c_str(), "r");
        if (!f) die("cannot read %s", value.c_str());
        char line[1024];
        while (fgets(line, sizeof(line), f)) {
            std::string spec(line, strcspn(line, "\r\n"));
            if (!spec.empty() && spec[0] != '#') S.tick_watches.push_back(parse_watch(spec));
        }
        fclose(f);
    }
    value = env("RTA_NET_TICKLOG");
    if (!value.empty()) {
        if (!(S.tick_log = fopen(value.c_str(), "w"))) die("cannot write %s", value.c_str());
        fprintf(S.tick_log, "frame");
        for (const Watch& w : S.tick_watches) fprintf(S.tick_log, "\t%s", w.name.c_str());
        fprintf(S.tick_log, "\n");
    }
    value = env("RTA_NET_SCRIPT");
    if (!value.empty()) {
        FILE* f = fopen(value.c_str(), "r");
        if (!f) die("cannot read script %s", value.c_str());
        char line[4096];
        int number = 0;
        while (fgets(line, sizeof(line), f)) parse_line(std::string(line, strcspn(line, "\r\n")), ++number);
        fclose(f);
        S.script_given = true;
        S.pad_override = true;
    }
    S.link_spec = env("RTA_NET_LINK");
    value = env("RTA_NET_UDP");
    if (!value.empty()) {
        if (!S.link_spec.empty()) die("RTA_NET_LINK and RTA_NET_UDP exclude each other");
        S.udp_base = atoi(value.c_str());
        if (S.udp_base < 1024 || S.udp_base + 256 * 16 > 65535) die("RTA_NET_UDP wants a base port between 1024 and 61439");
        std::string peers = env("RTA_NET_PEERS");
        if (peers.empty()) S.udp_peers = {132, 134};
        for (const auto& peer : split(peers, ',')) {
            unsigned a, b, c, d;
            if (sscanf(peer.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4 || d > 255) die("RTA_NET_PEERS wants a.b.c.d,...");
            S.udp_peers.push_back((u8)d);
        }
        S.pace = 59.94;
        S.linked = true;
    }
    if (!env("RTA_NET_ALLOW_LEVEL").empty()) S.stop_on_level = false;
    value = env("RTA_NET_PADLAT");
    if (!value.empty()) S.pad_latency = atoi(value.c_str());
    value = env("RTA_NET_PACE");
    if (!value.empty()) S.pace = atof(value.c_str());
    printf("net shim: machine %c, address %d.%d.%d.%d, %s; bus delay=%u jitter=%u loss=%u; %s\n", S.machine, S.own[3], S.own[2], S.own[1], S.own[0],
           !S.link_spec.empty() ? ("link " + S.link_spec).c_str() : S.udp_base ? fmt("UDP on 127.0.0.1, base port %d", S.udp_base).c_str() : "no other machine",
           S.bus.delay, S.bus.jitter, S.bus.loss, RTA_NET_RT_NOTE);
    if (!S.link_spec.empty()) {
        printf("waiting for the other machine (%s)\n", S.link_spec.c_str());
        link_open(S.link_spec);
        S.linked = true;
        printf("joined; this is machine %c\n", S.machine);
    }
    S.start_wall = wall_seconds();
    S.start_cpu = cpu_seconds();
}

void on_vblank() {
    start();
    S.frame++;
    if (S.link_fd >= 0) exchange_with_peer();
    else if (S.udp_base) { udp_flush(); udp_drain(); }
    if (S.pace > 0) {
        double due = S.start_wall + S.frame / S.pace, now = wall_seconds();
        if (due > now) usleep((useconds_t)((due - now) * 1e6));
    }
    // On the rig a controller state set at one vertical blank is what the game reads in
    // the frame after the next blank (measured: the same script moved a player one tick
    // earlier here); the same latency is kept so that one script gives one game.
    if (S.pad_latency) S.pad_seen = S.pad;
    if (S.script_given) {
        step_script();
        if (S.script_done && S.frames_wanted == 0) finish(0);
    }
    if (!S.pad_latency) S.pad_seen = S.pad;
    if (S.frames_wanted && S.frame >= S.frames_wanted) finish(S.script_given && !S.script_done ? 4 : 0);
}

// ---- the library entries ----------------------------------------------------------------------
enum Call { LIBNET_INIT, GET_INTERFACE_LIST, INTERFACE_CONTROL, CREATE, OPEN, CLOSE, SEND_TO, RECV_FROM, LOAD_MODULES, LINK_CHECK };
// arguments 1-8 are in $a0-$a3, $t0-$t3
u32 arg(Ctx* c, int index) { return (u32)c->r[4 + index]; }
void answer(Ctx* c, s32 result) { c->r[2] = (u64)(s64)result; }

void send_to(Ctx* c) {
    s32 id = (s32)arg(c, 2);
    u32 pointer = arg(c, 3), length = arg(c, 4), address_block = arg(c, 6), port = arg(c, 7);
    Datagram datagram;
    if (const u8* p = gptr(pointer, length)) datagram.data.assign(p, p + length);
    u8 destination[4] = {};
    if (const u8* p = gptr(address_block, 8)) memcpy(destination, p + 4, 4);
    Socket& sender = socket_of(id);
    memcpy(datagram.address, S.own, 4);
    datagram.port = sender.port;
    datagram.frame = S.frame + 1;
    bool broadcast = destination[0] == 0xff, to_self = memcmp(destination, S.own, 4) == 0;
    const char* fate = "no receiver on the bus, dropped";
    if (broadcast || to_self) {
        for (auto& other : S.sockets) {
            if (other.second.port != port) continue;
            enqueue(other.second, datagram);
            fate = "queued for this machine";
        }
    }
    if (S.linked && (broadcast || !to_self)) {
        // the bus model: loss, then delay and jitter (the rig's order of draws)
        bool lost = S.bus.loss != 0 && S.bus.next() % 1000 < S.bus.loss;
        if (S.bus.stall_frames != 0 && S.frame >= S.bus.stall_at && S.frame < S.bus.stall_at + S.bus.stall_frames) lost = true;
        u32 extra = S.bus.jitter ? (u32)(S.bus.next() % (S.bus.jitter + 1)) : 0;
        if (lost) { fate = broadcast ? "queued here, lost on the bus" : "lost on the bus"; S.lost++; }
        else {
            Wire wire;
            wire.deliver_frame = S.frame + 1 + S.bus.delay + extra;
            memcpy(wire.source, S.own, 4);
            wire.source_port = sender.port;
            memcpy(wire.destination, destination, 4);
            wire.destination_port = port;
            wire.data = datagram.data;
            S.outbox.push_back(std::move(wire));
            S.crossed++;
            if (S.udp_base) udp_flush();        // a datagram with no delay left goes out at once
            fate = broadcast ? "queued here and sent across" : "sent across";
        }
    }
    S.sent++;
    if (S.log && (S.log_all || length <= 8))
        net_log("sceInetSendTo(id=%d, len=%d, to %d.%d.%d.%d:%d) first=%s -> %s", id, length, destination[3], destination[2], destination[1],
                destination[0], port, hex(datagram.data, 16).c_str(), fate);
    answer(c, (s32)length);
}

void recv_from(Ctx* c) {
    s32 id = (s32)arg(c, 2);
    u32 pointer = arg(c, 3), length = arg(c, 4), flags_pointer = arg(c, 5), address_out = arg(c, 6), port_out = arg(c, 7);
    s32 result = ERROR_NO_DATA;
    Socket& receiver = socket_of(id);
    if (!receiver.queue.empty() && receiver.queue.front().frame <= S.frame) {
        Datagram datagram = std::move(receiver.queue.front());
        receiver.queue.pop_front();
        u32 size = length < datagram.data.size() ? length : (u32)datagram.data.size();
        if (u8* p = gptr(pointer, size)) memcpy(p, datagram.data.data(), size);
        if (u8* p = gptr(address_out, 16)) { memset(p, 0, 16); memcpy(p + 4, datagram.address, 4); }
        if (port_out) write32(port_out, datagram.port);
        if (flags_pointer) write32(flags_pointer, 0);
        result = (s32)size;
        S.received++;
        if (S.log && (S.log_all || size <= 8))
            net_log("sceInetRecvFrom(id=%d) -> %d bytes from %d.%d.%d.%d:%d first=%s", id, size, datagram.address[3], datagram.address[2],
                    datagram.address[1], datagram.address[0], datagram.port, hex(datagram.data, 16).c_str());
    }
    answer(c, result);
}

}  // namespace

#ifdef RTA_NET_WRAP_MEMORY
// build_net.py --wrap-memory: an access to an address where nothing is.
//
// The game makes such accesses in play (Player_run 0x1ab7c0 reads a float through a track
// index it did not test, docs/spec/player-tick.md "An out-of-bounds read in the original":
// seen at tick 5,115 of a fight).  The runtime stops there; the Play! emulator gives every
// byte of such a read the value 0xCC and drops such a store (its MemoryMap.cpp), and the
// game runs on.  A native machine that plays against an emulator has to do the same, so
// with this option runtime.cpp is compiled with its four functions renamed (…_rt) - the
// source is not touched - and the ones below stand in front of them.  The test for
// "something is there" repeats the runtime's own decoding and has to follow it.
u64 rt_load_rt(u32 addr, unsigned size);
void rt_store_rt(u32 addr, unsigned size, u64 value);
void rt_load128_rt(u32 addr, u64* lo, u64* hi);
void rt_store128_rt(u32 addr, u64 lo, u64 hi);
static bool something_there(u32 a, unsigned size) {
    u32 top = a >> 28;
    if (top == 2 || top == 3) {
        if ((a & 0x0FFFFFFFu) <= RAM_SIZE - size) return true;
    } else if (top >= 8 && top <= 0xB) {
        u32 p = a & 0x1FFFFFFFu;
        if (p <= RAM_SIZE - size) return true;
        a = p;
    }
    if (a >= 0x70000000u && a <= 0x70004000u - size) return true;      // scratchpad
    if (a >= 0x11000000u && a <= 0x11010000u - size) return true;      // vector-unit memories
    if (a >= 0x10000000u && a < 0x14000000u) return true;              // hardware registers
    if (a >= 0x1FC00000u && a < 0x20000000u) return true;              // boot ROM
    return false;
}
static void nothing(const char* what, u32 addr, unsigned size, u64& counter) {
    if (counter++ < 8)
        printf("net shim: %s of %u bytes at 0x%08x, where nothing is (last call site 0x%x, tick %u, frame %" PRIu64 "): as on the emulator\n",
               what, size, addr, g_site, read32(G_NETFRAME), S.frame);
}
u64 rt_load(u32 addr, unsigned size) {
    if (something_there(addr, size)) return rt_load_rt(addr, size);
    nothing("read", addr, size, S.nothing_reads);
    return 0xCCCCCCCCCCCCCCCCull >> (64 - 8 * (size > 8 ? 8 : size));
}
void rt_store(u32 addr, unsigned size, u64 value) {
    if (something_there(addr, size)) { rt_store_rt(addr, size, value); return; }
    nothing("store", addr, size, S.nothing_stores);
}
void rt_load128(u32 addr, u64* lo, u64* hi) {
    if (something_there(addr, 16)) { rt_load128_rt(addr, lo, hi); return; }
    nothing("read", addr, 16, S.nothing_reads);
    *lo = *hi = 0xCCCCCCCCCCCCCCCCull;
}
void rt_store128(u32 addr, u64 lo, u64 hi) {
    if (something_there(addr, 16)) { rt_store128_rt(addr, lo, hi); return; }
    nothing("store", addr, 16, S.nothing_stores);
}
#endif

void fn_00365ec0(Ctx* c) {                  // sceLibnetInitialize
    start();
    S.calls[LIBNET_INIT]++;
    net_log("sceLibnetInitialize(cd=%08x, %x, %x, %x) -> 0", arg(c, 0), arg(c, 1), arg(c, 2), arg(c, 3));
    answer(c, 0);
}
void fn_00365a08(Ctx* c) {                  // sceInetGetInterfaceList
    start();
    S.calls[GET_INTERFACE_LIST]++;
    write32(arg(c, 2), 1);
    net_log("sceInetGetInterfaceList -> 1 interface, id 1");
    answer(c, 1);
}
void fn_00365a90(Ctx* c) {                  // sceInetInterfaceControl
    start();
    S.calls[INTERFACE_CONTROL]++;
    // code 9 asks for the interface's address: a 16-byte block, address in bytes 4-7
    u32 code = arg(c, 3), pointer = arg(c, 4), length = arg(c, 5);
    if (code == 9 && length >= 8)
        if (u8* p = gptr(pointer, length)) { memset(p, 0, length); memcpy(p + 4, S.own, 4); }
    net_log("sceInetInterfaceControl(id=%d, code=%d, ptr=%08x, len=%d) -> 0", arg(c, 2), code, pointer, length);
    answer(c, 0);
}
void fn_003654a8(Ctx* c) {                  // sceInetCreate
    start();
    S.calls[CREATE]++;
    // parameter block: word 0 the type (0 for the datagram sockets the game opens), word 1 the local port
    u32 parameters = arg(c, 2);
    Socket socket;
    socket.type = read32(parameters);
    socket.port = read32(parameters + 4);
    s32 id = S.next_id++;
    Socket& made = S.sockets[id] = socket;
    udp_bind(made);
    net_log("sceInetCreate(type=%d, port=%d) -> id %d", socket.type, socket.port, id);
    answer(c, id);
}
void fn_00365518(Ctx* c) {                  // sceInetOpen
    start();
    S.calls[OPEN]++;
    net_log("sceInetOpen(id=%d, ms=%d) -> 0", arg(c, 2), arg(c, 3));
    answer(c, 0);
}
void fn_00365560(Ctx* c) {                  // sceInetClose
    start();
    S.calls[CLOSE]++;
    auto found = S.sockets.find((s32)arg(c, 2));
    if (found != S.sockets.end()) { if (found->second.fd >= 0) close(found->second.fd); S.sockets.erase(found); }
    net_log("sceInetClose(id=%d) -> 0", arg(c, 2));
    answer(c, 0);
}
void fn_00365830(Ctx* c) { start(); S.calls[SEND_TO]++; send_to(c); }          // sceInetSendTo
void fn_00365670(Ctx* c) { start(); S.calls[RECV_FROM]++; recv_from(c); }      // sceInetRecvFrom
void fn_00137a10(Ctx* c) {                  // net_loadModules
    start();
    S.calls[LOAD_MODULES]++;
    net_log("net_loadModules -> 1 (not run: the modules are not needed)");
    answer(c, 1);                           // an interface id; the caller then asks for its address
}
void fn_0013e638(Ctx* c) { start(); S.calls[LINK_CHECK]++; answer(c, 1); }     // net_linkCheck

void fn_00323dcc(Ctx* c) {                  // main(argc, argv)
    // The runtime starts the game with no arguments.  With RTA_NET_ARG the argument block
    // the start-up code gave the kernel (0x5f8740: count, sixteen pointers, then text) is
    // filled as a loader would fill it: the program's name, then the arguments.
    const char* given = getenv("RTA_NET_ARG");
    if (given && *given) {
        const u32 block = 0x5f8740, text = block + 4 + 16 * 4;
        std::vector<std::string> words = {"cdrom0:\\SLUS_209.73;1"};
        for (const auto& word : split(given, ' ')) if (!word.empty()) words.push_back(word);
        u32 at = text;
        for (size_t i = 0; i < words.size() && i < 16 && at + words[i].size() + 1 <= text + 256; i++) {
            memcpy(g_ram + at, words[i].c_str(), words[i].size() + 1);
            write32(block + 4 + (u32)i * 4, at);
            at += (u32)words[i].size() + 1;
            write32(block, (u32)i + 1);
        }
        c->r[4] = read32(block);
        c->r[5] = block + 4;
        printf("net shim: main() gets %u arguments (%s)\n", read32(block), given);
    }
    orig_00323dcc(c);
}

void fn_003646c8(Ctx* c) {                  // sceSifMInitRpc (libmrpc), called by net_gameInit before sceLibnetInitialize
    // It sends the I/O processor SIF command 0x80000001 and then polls sceSifGetSreg(1)
    // (the word at 0x8ef2c4) until the multi-thread RPC manager there has answered.  That
    // manager carries the network library's calls, all of which are replaced here, so
    // nothing will answer: the word is set as the answer would set it and the original runs.
    start();
    write32(0x8ef2c0 + 4, 1);
    orig_003646c8(c);
}

void fn_0036c1a0(Ctx* c) {                  // lgAudEnumerate(index, description)
    // A net game lists the USB headsets after its first ticks (0x31f634): it asks for
    // index 0, 1, 2 ... until an answer has bit 31 set.  The headset driver's answer comes
    // from the runtime's I/O-processor services; while that answer carries no data for
    // this function the list never ends (seen: 181,038 calls in 3,000 fields, the main
    // thread never back in the session loop).  The original runs; an answer without the
    // error bit becomes the library's own error code, which says "no headset".
    orig_0036c1a0(c);
    if (!((u32)c->r[2] & 0x80000000u)) c->r[2] = (u64)(s64)(s32)0x8000000Au;
}

void fn_0019b6e4(Ctx* c) {                  // gfx_vblankHandler: once per vertical blank
    on_vblank();
    orig_0019b6e4(c);
}

void fn_0017421c(Ctx* c) {                  // pad_readPort(port, out 8-byte record)
    u32 port = arg(c, 0), out = arg(c, 1);
    orig_0017421c(c);
    if (!S.pad_override || port != 0) return;
    u8* record = gptr(out, 8);
    if (!record) return;
    u16 buttons = 0;
    const Pad& pad = S.pad_seen;
    for (int b = B_UP; b < B_MAX; b++) if (pad.buttons & (1u << b)) buttons |= RECORD_BIT[b];
    memcpy(record, &buttons, 2);
    record[2] = pad.axis[AX_LX]; record[3] = pad.axis[AX_LY];
    record[4] = pad.axis[AX_RX]; record[5] = pad.axis[AX_RY];
    // the two pressure bytes the game reads (L1, R1): full when held, as the emulator's controller gives them
    record[6] = (pad.buttons & (1u << B_L1)) ? 0xFF : 0;
    record[7] = (pad.buttons & (1u << B_R1)) ? 0xFF : 0;
    c->r[2] = 1;
}

void fn_003226e4(Ctx* c) {                  // tasks_run: from net_frameLoop it is one lockstep tick
    u32 ra = (u32)c->r[31];
    orig_003226e4(c);
    if (ra == TICK_RETURN) { start(); on_tick(); }
}
