// script.cpp - scripted input, conditions and typed values, in the script language of the
// headless rig (tools/rig/README.md, "Expressions and types" and "Script commands"), so
// that one script can drive the original in the rig and the translation here.
//
// A "frame" is one vertical blank, counted from the start of the run.  The script is
// stepped once per blank, before the controller buffers are written for that blank.
//
// Commands: wait, at, until, press, release, tap, tapuntil, stick, pad, "<frame> buttons
// [lx ly [rx ry]]" (input table), the same with a trailing 1 or 2 for a controller port,
// poke, dump, show, echo, sync, log (ignored), quit.  Commands of the rig that belong to
// the emulator (save, load, break, pnach, netshim, fuzz, ontick, A:/B:) are refused.
#include "rt.h"
#include "moved.h"

#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <vector>

namespace {

std::map<std::string, u32> g_symbols;

const u8* mem_ptr(u32 address, u32 size) {
    if (address >= 0x70000000u && address - 0x70000000u <= 0x4000u - size && size <= 0x4000u)
        return rta::scratchpad() + (address - 0x70000000u);
    u32 a = guest_addr(party8_at(address), size);   // a table moved for eight players is read where it is (moved.h)
    return a == ~0u ? nullptr : g_ram + a;
}

// ---- expressions: symbols, numbers, + - * &, parentheses, [x] = the word stored at x ----
struct Parser {
    const std::string& s;
    size_t i = 0;
    explicit Parser(const std::string& text) : s(text) {}
    void skip() { while (i < s.size() && s[i] == ' ') i++; }
    u32 factor() {
        skip();
        if (i >= s.size()) rt_die("expression '%s' ends early", s.c_str());
        char ch = s[i];
        if (ch == '(') { i++; u32 v = sum(); skip(); if (i < s.size() && s[i] == ')') i++; return v; }
        if (ch == '[') {
            i++;
            u32 a = sum();
            skip();
            if (i < s.size() && s[i] == ']') i++;
            const u8* p = mem_ptr(a, 4);
            u32 v = 0;
            if (p) memcpy(&v, p, 4);
            return v;
        }
        if (ch == '-') { i++; return 0u - factor(); }
        if (ch == '$') rt_die("expression '%s': registers are not available in the native runtime", s.c_str());
        size_t start = i;
        while (i < s.size() && (isalnum((unsigned char)s[i]) || s[i] == '_' || s[i] == '.')) i++;
        std::string word = s.substr(start, i - start);
        if (word.empty()) rt_die("expression '%s': unexpected '%c'", s.c_str(), ch);
        if (isdigit((unsigned char)word[0])) return (u32)strtoul(word.c_str(), nullptr, 0);
        auto it = g_symbols.find(word);
        if (it == g_symbols.end()) rt_die("expression '%s': unknown name %s (is a --sym file missing?)", s.c_str(), word.c_str());
        return party8_at(it->second);       // a moved table's name is its new place: g_players+4*0x4c30 is slot 4 (moved.h)
    }
    u32 product() {
        u32 v = factor();
        for (;;) {
            skip();
            if (i < s.size() && s[i] == '*') { i++; v *= factor(); }
            else return v;
        }
    }
    u32 sum() {
        u32 v = product();
        for (;;) {
            skip();
            if (i >= s.size()) return v;
            if (s[i] == '+') { i++; v += product(); }
            else if (s[i] == '-') { i++; v -= product(); }
            else if (s[i] == '&') { i++; v &= product(); }
            else return v;
        }
    }
};

// ---- typed values -----------------------------------------------------------------------
struct Type { char kind = 'x'; u32 size = 4; };      // u s x f(loat) t(ext) h(ex bytes) c(rc)
Type parse_type(const std::string& t) {
    Type type;
    if (t == "f32") { type.kind = 'f'; return type; }
    if (t.compare(0, 3, "str") == 0) { type.kind = 't'; type.size = (u32)atoi(t.c_str() + 3); return type; }
    if (t.compare(0, 3, "hex") == 0) { type.kind = 'h'; type.size = (u32)atoi(t.c_str() + 3); return type; }
    if (t.compare(0, 3, "crc") == 0) { type.kind = 'c'; type.size = (u32)atoi(t.c_str() + 3); return type; }
    if (t.size() >= 2 && (t[0] == 'u' || t[0] == 's' || t[0] == 'x')) {
        int bits = atoi(t.c_str() + 1);
        if (bits == 8 || bits == 16 || bits == 32) { type.kind = t[0]; type.size = (u32)bits / 8; return type; }
    }
    rt_die("unknown type '%s'", t.c_str());
}

struct Value { bool text = false, real = false; std::string s; double f = 0; s64 n = 0; };
Value read_value(u32 address, const Type& type) {
    Value v;
    const u8* p = mem_ptr(address, type.size);
    if (!p) { v.text = true; v.s = "<unmapped>"; return v; }
    switch (type.kind) {
    case 'u': case 'x': { u32 raw = 0; memcpy(&raw, p, type.size); v.n = raw; break; }
    case 's': {
        u32 raw = 0;
        memcpy(&raw, p, type.size);
        v.n = type.size == 1 ? (s64)(s8)raw : type.size == 2 ? (s64)(s16)raw : (s64)(s32)raw;
        break;
    }
    case 'f': { float raw; memcpy(&raw, p, 4); v.real = true; v.f = raw; break; }
    case 't': v.text = true; for (u32 i = 0; i < type.size && p[i]; i++) v.s += (char)p[i]; break;
    case 'h': v.text = true; for (u32 i = 0; i < type.size; i++) v.s += rt_fmt("%02x", p[i]); break;
    case 'c': {                                         // FNV-1a, as the rig computes it
        u32 hash = 0x811C9DC5u;
        for (u32 i = 0; i < type.size; i++) hash = (hash ^ p[i]) * 0x01000193u;
        v.text = true;
        v.s = rt_fmt("%08x", hash);
        break;
    }
    }
    return v;
}
std::string format_value(const Value& v, const Type& type) {
    if (v.text) {
        if (type.kind != 't') return v.s;
        std::string out;
        for (char ch : v.s) {
            if (ch == '\t') out += "\\t"; else if (ch == '\n') out += "\\n"; else if (ch == '\\') out += "\\\\";
            else if ((unsigned char)ch < 0x20 || (unsigned char)ch >= 0x7F) out += rt_fmt("\\x%02x", (unsigned char)ch);
            else out += ch;
        }
        return out;
    }
    if (v.real) return rt_fmt("%.9g", v.f);
    if (type.kind == 'x') return rt_fmt("%0*llx", (int)type.size * 2, (unsigned long long)v.n);
    return rt_fmt("%lld", (long long)v.n);
}

// "expr:type"; the last ':' outside brackets separates them, the type defaults to x32
void split_typed(const std::string& text, std::string& expr, std::string& type) {
    int depth = 0;
    size_t colon = std::string::npos;
    for (size_t i = 0; i < text.size(); i++) {
        if (text[i] == '[' || text[i] == '(') depth++;
        if (text[i] == ']' || text[i] == ')') depth--;
        if (text[i] == ':' && depth == 0) colon = i;
    }
    if (colon == std::string::npos) { expr = text; type = "x32"; }
    else { expr = text.substr(0, colon); type = text.substr(colon + 1); }
}

struct Condition {
    std::string expr, text;
    Type type;
    int op = 0;                                         // 0 == 1 != 2 < 3 <= 4 > 5 >= 6 changed
    Value want;
    bool test() const {
        Value v = read_value(script_eval(expr), type);
        if (op == 6) return v.text ? v.s != want.s : v.real ? v.f != want.f : v.n != want.n;
        int cmp;
        if (v.text) cmp = v.s.compare(want.s) < 0 ? -1 : v.s == want.s ? 0 : 1;
        else if (v.real) cmp = v.f < want.f ? -1 : v.f == want.f ? 0 : 1;
        else cmp = v.n < want.n ? -1 : v.n == want.n ? 0 : 1;
        switch (op) {
        case 0: return cmp == 0; case 1: return cmp != 0; case 2: return cmp < 0;
        case 3: return cmp <= 0; case 4: return cmp > 0; default: return cmp >= 0;
        }
    }
};

Value parse_literal(const std::string& word, const Type& type) {
    Value v;
    if (type.kind == 't' || type.kind == 'h' || type.kind == 'c') { v.text = true; v.s = word; }
    else if (type.kind == 'f') { v.real = true; v.f = atof(word.c_str()); }
    else if (type.kind == 'x') v.n = (s64)strtoull(word.c_str(), nullptr, 16);
    else v.n = strtoll(word.c_str(), nullptr, 0);
    return v;
}

struct Command {
    enum Kind { WAIT, AT, UNTIL, PRESS, RELEASE, TAP, TAPUNTIL, STICK, PAD, POKE, DUMP, SHOW, ECHO, APP, CALL, QUIT } kind = WAIT;
    int line = 0, port = 0;
    u16 buttons = 0;
    s64 number = 0, number2 = 0;
    bool started = false, keep_going = false;
    u64 deadline = 0, phase_start = 0;
    Condition cond;
    int axis_first = 0, axis_count = 0;
    u8 axis[4] = {128, 128, 128, 128};
    std::vector<std::string> words;
};

std::vector<Command> g_commands;
size_t g_position = 0;
rta::PadState g_pads[2];
int g_line = 0;

u16 parse_buttons(const std::string& text) {
    static const std::map<std::string, u16> names = {
        {"select", rta::PAD_SELECT}, {"l3", rta::PAD_L3}, {"r3", rta::PAD_R3}, {"start", rta::PAD_START},
        {"up", rta::PAD_UP}, {"right", rta::PAD_RIGHT}, {"down", rta::PAD_DOWN}, {"left", rta::PAD_LEFT},
        {"l2", rta::PAD_L2}, {"r2", rta::PAD_R2}, {"l1", rta::PAD_L1}, {"r1", rta::PAD_R1},
        {"triangle", rta::PAD_TRIANGLE}, {"circle", rta::PAD_CIRCLE}, {"cross", rta::PAD_CROSS}, {"x", rta::PAD_CROSS},
        {"square", rta::PAD_SQUARE}, {"none", 0}};
    u16 mask = 0;
    size_t start = 0;
    for (;;) {
        size_t plus = text.find('+', start);
        std::string name = text.substr(start, plus == std::string::npos ? std::string::npos : plus - start);
        auto it = names.find(name);
        if (it == names.end()) rt_die("script line %d: unknown button '%s'", g_line, name.c_str());
        mask |= it->second;
        if (plus == std::string::npos) return mask;
        start = plus + 1;
    }
}

// words[from...] = "<expr:type> <op> <value>" or "<expr:type> changed"; returns the index after it
size_t parse_condition(const std::vector<std::string>& w, size_t from, Condition& c) {
    if (from + 1 >= w.size()) rt_die("script line %d: a condition is missing", g_line);
    std::string type;
    split_typed(w[from], c.expr, type);
    c.type = parse_type(type);
    c.text = w[from] + " " + w[from + 1];
    if (w[from + 1] == "changed") { c.op = 6; return from + 2; }
    static const char* ops[6] = {"==", "!=", "<", "<=", ">", ">="};
    c.op = -1;
    for (int k = 0; k < 6; k++) if (w[from + 1] == ops[k]) c.op = k;
    if (c.op < 0 || from + 2 >= w.size()) rt_die("script line %d: bad condition", g_line);
    c.want = parse_literal(w[from + 2], c.type);
    c.text += " " + w[from + 2];
    return from + 3;
}

void add_line(const std::string& raw) {
    g_line++;
    std::string line = raw.substr(0, raw.find('#'));
    std::vector<std::string> w;
    for (size_t i = 0; i < line.size();) {
        while (i < line.size() && isspace((unsigned char)line[i])) i++;
        size_t start = i;
        while (i < line.size() && !isspace((unsigned char)line[i])) i++;
        if (i > start) w.push_back(line.substr(start, i - start));
    }
    if (w.empty()) return;
    Command c;
    c.line = g_line;
    std::string word = w[0];
    auto number = [&](size_t k, s64 fallback) { return k < w.size() ? strtoll(w[k].c_str(), nullptr, 0) : fallback; };
    auto axes = [&](size_t from, int first) {
        c.axis_first = first;
        for (size_t k = from; k < w.size() && c.axis_count < 4; k++) c.axis[c.axis_count++] = (u8)strtol(w[k].c_str(), nullptr, 0);
    };
    if (isdigit((unsigned char)word[0])) {              // input table: "<frame> buttons [lx ly [rx ry]]"
        Command at;
        at.line = g_line; at.kind = Command::AT; at.number = strtoll(word.c_str(), nullptr, 0);
        g_commands.push_back(at);
        w.erase(w.begin());
        if (w.empty()) return;
        w.insert(w.begin(), "pad");
        word = "pad";
    }
    static const char* padded[] = {"press", "release", "tapuntil", "tap", "stick", "pad"};
    if (word.size() > 1 && (word.back() == '1' || word.back() == '2')) {
        std::string stem = word.substr(0, word.size() - 1);
        for (const char* p : padded) if (stem == p) { c.port = word.back() - '1'; word = stem; break; }
    }
    if (word == "wait") { c.kind = Command::WAIT; c.number = number(1, 1); }
    else if (word == "at") { c.kind = Command::AT; c.number = number(1, 0); }
    else if (word == "until") {
        c.kind = Command::UNTIL;
        size_t k = parse_condition(w, 1, c.cond);
        for (; k < w.size(); k++) {
            if (w[k] == "timeout") c.number = number(++k, 0);
            else if (w[k] == "continue") c.keep_going = true;
        }
    }
    else if (word == "press" || word == "release") {
        if (w.size() < 2) rt_die("script line %d: %s needs buttons", g_line, word.c_str());
        c.kind = word == "press" ? Command::PRESS : Command::RELEASE;
        c.buttons = parse_buttons(w[1]);
    }
    else if (word == "tap") {
        if (w.size() < 2) rt_die("script line %d: tap needs buttons", g_line);
        c.kind = Command::TAP; c.buttons = parse_buttons(w[1]); c.number = number(2, 3); c.number2 = number(3, 0);
    }
    else if (word == "tapuntil") {
        if (w.size() < 5) rt_die("script line %d: tapuntil B period <condition>", g_line);
        c.kind = Command::TAPUNTIL; c.buttons = parse_buttons(w[1]); c.number2 = number(2, 40);
        if (c.number2 < 5) c.number2 = 5;
        size_t k = parse_condition(w, 3, c.cond);
        for (; k < w.size(); k++) if (w[k] == "timeout") c.number = number(++k, 0);
    }
    else if (word == "stick") {
        if (w.size() < 4) rt_die("script line %d: stick L|R x y", g_line);
        c.kind = Command::STICK;
        axes(2, (w[1] == "R" || w[1] == "r") ? 2 : 0);
    }
    else if (word == "pad") {
        if (w.size() < 2) rt_die("script line %d: pad needs buttons", g_line);
        c.kind = Command::PAD; c.buttons = parse_buttons(w[1]); axes(2, 0);
    }
    else if (word == "poke") { if (w.size() < 3) rt_die("script line %d: poke <expr:type> <value>", g_line); c.kind = Command::POKE; c.words = w; }
    else if (word == "dump") { if (w.size() < 4) rt_die("script line %d: dump <expr> <length> <file>", g_line); c.kind = Command::DUMP; c.words = w; }
    else if (word == "show") { c.kind = Command::SHOW; c.words = w; }
    else if (word == "echo" || word == "sync") {
        c.kind = Command::ECHO;
        size_t at = line.find(word);
        std::string rest = line.substr(at + word.size());
        while (!rest.empty() && isspace((unsigned char)rest[0])) rest.erase(0, 1);
        while (!rest.empty() && isspace((unsigned char)rest.back())) rest.pop_back();
        c.words = {word == "sync" ? "sync " + rest : rest};
    }
    else if (word == "app") {                           // for the application linked with the runtime
        c.kind = Command::APP;
        std::string rest = line.substr(line.find(word) + word.size());
        while (!rest.empty() && isspace((unsigned char)rest[0])) rest.erase(0, 1);
        while (!rest.empty() && isspace((unsigned char)rest.back())) rest.pop_back();
        c.words = {rest};
    }
    else if (word == "call") {                          // a test aid: call a function of the game
        if (w.size() < 2) rt_die("script line %d: call <address> [a0 [a1]]", g_line);
        c.kind = Command::CALL; c.words = w;
    }
    else if (word == "log") return;
    else if (word == "quit") c.kind = Command::QUIT;
    else rt_die("script line %d: the command '%s' belongs to the emulator rig and is not available here", g_line, word.c_str());
    g_commands.push_back(c);
}

void poke(const Command& c) {
    std::string expr, type_text;
    split_typed(c.words[1], expr, type_text);
    Type type = parse_type(type_text);
    u32 address = script_eval(expr);
    u8* p = (u8*)mem_ptr(address, type.kind == 't' || type.kind == 'h' ? 1 : type.size);
    if (!p) rt_die("script line %d: poke to 0x%08x, which is not memory", c.line, address);
    if (type.kind == 'f') { float f = (float)atof(c.words[2].c_str()); memcpy(p, &f, 4); }
    else if (type.kind == 't') { memcpy(p, c.words[2].c_str(), c.words[2].size() + 1); }
    else if (type.kind == 'h') {
        for (size_t k = 0; k + 1 < c.words[2].size(); k += 2) p[k / 2] = (u8)strtoul(c.words[2].substr(k, 2).c_str(), nullptr, 16);
    } else {
        u32 v = (u32)(type.kind == 'x' ? strtoull(c.words[2].c_str(), nullptr, 16) : (u64)strtoll(c.words[2].c_str(), nullptr, 0));
        memcpy(p, &v, type.size);
    }
}

}  // namespace

void (*script_app_command)(const std::string& text, u64 frame) = nullptr;

void script_add_symbols(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) rt_die("cannot read %s", path);
    char line[1024];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#') continue;
        char* tab = strchr(line, '\t');
        if (!tab) continue;
        char* end = nullptr;
        u32 address = (u32)strtoul(line, &end, 16);
        if (end != tab) continue;
        char* name = tab + 1;
        size_t length = strcspn(name, "\t\r\n");
        if (length) g_symbols.emplace(std::string(name, length), address);     // the first definition wins
    }
    fclose(f);
}

bool script_load(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return false;
    char line[2048];
    g_line = 0;
    while (fgets(line, sizeof(line), f)) add_line(line);
    fclose(f);
    return true;
}
void script_add_command(const std::string& line) { add_line(line); }
bool script_active() { return g_position < g_commands.size(); }
const rta::PadState& script_pad(unsigned port) { return g_pads[port & 1]; }

u32 script_eval(const std::string& expression) {
    Parser p(expression);
    return p.sum();
}
std::string script_value(u32 address, const std::string& type) {
    Type t = parse_type(type);
    return format_value(read_value(address, t), t);
}

void script_vblank(u64 frame) {
    while (g_position < g_commands.size()) {
        Command& c = g_commands[g_position];
        rta::PadState& pad = g_pads[c.port];
        switch (c.kind) {
        case Command::WAIT:
            if (!c.started) { c.started = true; c.deadline = frame + (u64)c.number; }
            if (frame < c.deadline) return;
            break;
        case Command::AT:
            if (frame < (u64)c.number) return;
            break;
        case Command::UNTIL:
            if (!c.started) {
                c.started = true;
                c.deadline = c.number ? frame + (u64)c.number : 0;
                if (c.cond.op == 6) c.cond.want = read_value(script_eval(c.cond.expr), c.cond.type);
            }
            if (!c.cond.test()) {
                if (c.deadline && frame >= c.deadline) {
                    printf("[frame %" PRIu64 "] TIMEOUT line %d: until %s\n", frame, c.line, c.cond.text.c_str());
                    if (!c.keep_going) rt_finish(3);
                    break;
                }
                return;
            }
            printf("[frame %" PRIu64 "] until %s\n", frame, c.cond.text.c_str());
            break;
        case Command::PRESS: pad.buttons |= c.buttons; break;
        case Command::RELEASE: pad.buttons &= (u16)~c.buttons; break;
        case Command::TAP:                              // held for `number` frames, then released for `number2`
            if (!c.started) { c.started = true; pad.buttons |= c.buttons; c.deadline = frame + (u64)c.number; return; }
            if (frame < c.deadline) return;
            pad.buttons &= (u16)~c.buttons;
            if (c.number2 > 0 && frame < c.deadline + (u64)c.number2) return;
            break;
        case Command::TAPUNTIL: {                       // one 4-frame tap per period; the condition is looked at between taps
            if (!c.started) {
                c.started = true;
                c.deadline = c.number ? frame + (u64)c.number : 0;
                c.phase_start = frame;
                if (c.cond.op == 6) c.cond.want = read_value(script_eval(c.cond.expr), c.cond.type);
            }
            u64 phase = (frame - c.phase_start) % (u64)c.number2;
            if (phase == 0) {
                if (c.cond.test()) { printf("[frame %" PRIu64 "] tapuntil %s\n", frame, c.cond.text.c_str()); break; }
                if (c.deadline && frame >= c.deadline) {
                    printf("[frame %" PRIu64 "] TIMEOUT line %d: tapuntil %s\n", frame, c.line, c.cond.text.c_str());
                    rt_finish(3);
                }
                pad.buttons |= c.buttons;
            } else if (phase == 4) pad.buttons &= (u16)~c.buttons;
            return;
        }
        case Command::STICK: {
            u8* axis[4] = {&pad.lx, &pad.ly, &pad.rx, &pad.ry};
            for (int k = 0; k < c.axis_count && c.axis_first + k < 4; k++) *axis[c.axis_first + k] = c.axis[k];
            break;
        }
        case Command::PAD:
            pad.buttons = c.buttons;
            pad.lx = c.axis_count > 0 ? c.axis[0] : 128; pad.ly = c.axis_count > 1 ? c.axis[1] : 128;
            pad.rx = c.axis_count > 2 ? c.axis[2] : 128; pad.ry = c.axis_count > 3 ? c.axis[3] : 128;
            break;
        case Command::POKE: poke(c); break;
        case Command::DUMP: {
            u32 address = script_eval(c.words[1]), length = (u32)strtoul(c.words[2].c_str(), nullptr, 0);
            const u8* p = mem_ptr(address, length);
            FILE* f = p ? fopen(c.words[3].c_str(), "wb") : nullptr;
            if (!f) rt_die("script line %d: cannot dump 0x%x bytes at 0x%08x to %s", c.line, length, address, c.words[3].c_str());
            fwrite(p, 1, length, f);
            fclose(f);
            break;
        }
        case Command::SHOW: {
            printf("[frame %" PRIu64 "]", frame);
            for (size_t k = 1; k < c.words.size(); k++) {
                std::string expr, type_text;
                size_t eq = c.words[k].find('=');
                std::string name = eq == std::string::npos ? "" : c.words[k].substr(0, eq);
                split_typed(eq == std::string::npos ? c.words[k] : c.words[k].substr(eq + 1), expr, type_text);
                Type type = parse_type(type_text);
                u32 address = script_eval(expr);
                printf(" %s@%08x=%s", name.empty() ? expr.c_str() : name.c_str(), address, format_value(read_value(address, type), type).c_str());
            }
            printf("\n");
            break;
        }
        case Command::ECHO: printf("[frame %" PRIu64 "] %s\n", frame, c.words[0].c_str()); fflush(stdout); break;
        case Command::APP:
            if (script_app_command) script_app_command(c.words[0], frame);
            else rt_note("script: app command without an application (" + c.words[0].substr(0, c.words[0].find(' ')) + ")");
            break;
        case Command::CALL: {
            // Runs at this vertical blank, where an interrupt handler would run, with up to
            // two arguments.  For tests that need the game to do something no button reaches
            // from where the script is (ask for a save without walking to a save point); a
            // function that waits or that the main thread is in the middle of is not safe here.
            u32 address = script_eval(c.words[1]);
            u32 a0 = c.words.size() > 2 ? script_eval(c.words[2]) : 0, a1 = c.words.size() > 3 ? script_eval(c.words[3]) : 0;
            printf("[frame %" PRIu64 "] call 0x%x(%u, %u)\n", frame, address, a0, a1);
            rt_call_handler(address, a0, a1);
            break;
        }
        case Command::QUIT: rt_finish(0);
        }
        g_position++;
    }
}
