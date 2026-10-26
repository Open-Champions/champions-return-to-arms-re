// iop.cpp - the I/O processor, as far as the game can tell.
//
// The game talks to the second processor through Sony's remote procedure calls:
// sceSifBindRpc(client, server id) once per service, then sceSifCallRpc(client, function,
// mode, send buffer, receive buffer, completion function).  Those two library functions
// (and sceSifInitRpc) are replaced here; behind them is one native service per server:
//
//   0x80000006            module loader: every load answers "loaded"; the name is checked on the disc
//   0x80000003            the I/O processor's heap (allocate, free, sizes)
//   0x80000592-0x8000059c the disc drive: search, read, read to I/O-processor memory,
//                         streaming reads, status - on an ISO 9660 image (iso9660.h)
//   0x80000100 / 0x101    controller ports (the pad buffers are written every blank)
//   0x80000900            multitap: none connected
//   0x80000400            memory card: a host directory per card, in the layout the
//                         Play! emulator uses (<root>/mc0/<save directory>/<file>)
//   0x80000701, 0x163a5   sound: sound_rpc() in sound_null.cpp or its replacement
//   0x61766973, 0x50494c42 USB keyboard and headset drivers: nothing plugged in
//
// What each service answers was taken from two sources: the layouts of the Play!
// emulator's own services (read, nothing copied), and a capture of every call and reply of
// a boot of the original in the headless rig (local/recomp-out/ref/).
//
// Time.  A call takes time on the virtual clock: the calling thread waits (other threads
// and interrupts run), or for a no-wait call the completion function runs later where an
// interrupt handler would.  By default the times are short (the game's own protocol is
// kept, loading is as fast as the host reads); with --emulator-timing they are the
// delays the Play! emulator applies, which makes loading take as many frames as there.
#include "rt.h"
#include "host.h"
#include "iso9660.h"
#include "funcs.h"

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <map>
#include <vector>

namespace fs = std::filesystem;

namespace {

IopOptions g_opt;
u8* g_iop;                                          // 2 MB
Iso9660 g_disc;
std::map<u32, u32> g_clients;                       // client structure -> server id
std::map<std::pair<u32, u32>, u64> g_calls;         // (server, function) -> count
u64 g_sectors_read, g_sif_dma_bytes;
std::vector<std::string> g_modules;

u32 rd(u32 a) { u32 v; memcpy(&v, g_ram + a, 4); return v; }
void wr(u32 a, u32 v) { memcpy(g_ram + a, &v, 4); }

u64 us(u64 fast, u64 emulator) { return usec_to_cycles(g_opt.emulator_timing ? emulator : fast); }

// ---- one call -----------------------------------------------------------------------------
struct Call {
    u32 server, fn;
    u32 send, ssize, recv, rsize;                   // offsets into g_ram; ~0u when not usable
    u64 delay;                                      // cycles until the answer is there
    bool never = false;                             // the server keeps the call open (a read that waits for a device)
    u32 arg(unsigned i) const { return send != ~0u && (i + 1) * 4 <= ssize ? rd(send + i * 4) : 0; }
    void ret(unsigned i, u32 v) const { if (recv != ~0u && (i + 1) * 4 <= rsize) wr(recv + i * 4, v); }
    const char* text(u32 offset) const { return send != ~0u && offset < ssize ? (const char*)g_ram + send + offset : ""; }
};

// ---- module loader and heap ---------------------------------------------------------------
u32 g_heap_top = 0x11A400;                          // where the reference's heap began after its modules
const u32 HEAP_END = 0x200000;

// A module's own name is in its file: the section of type 0x70000080 (.iopmod) holds
// seven words and a half of header and then the name.  Read from the disc for the
// modules that were loaded, when somebody asks (the network start-up does, once).
std::vector<std::string> g_module_names;            // beside g_modules; "" = not read or not found
int module_by_name(const std::string& wanted) {
    g_module_names.resize(g_modules.size());
    for (size_t k = 0; k < g_modules.size(); k++) {
        if (g_module_names[k].empty()) {
            g_module_names[k] = "?";
            std::string path = g_modules[k];
            size_t colon = path.find(':');
            Iso9660::Entry entry;
            if (!g_disc.find(path.substr(colon == std::string::npos ? 0 : colon + 1).c_str(), &entry) || entry.size < 0x34 || entry.size > 0x400000) continue;
            u32 sectors = (entry.size + Iso9660::SECTOR - 1) / Iso9660::SECTOR;
            std::vector<u8> file((size_t)sectors * Iso9660::SECTOR);
            if (!g_disc.read(entry.sector, sectors, file.data())) continue;
            auto u32at = [&](size_t a) { u32 v = 0; if (a + 4 <= file.size()) memcpy(&v, &file[a], 4); return v; };
            auto u16at = [&](size_t a) { u16 v = 0; if (a + 2 <= file.size()) memcpy(&v, &file[a], 2); return v; };
            u32 shoff = u32at(0x20), shentsize = u16at(0x2E), shnum = u16at(0x30);
            for (u32 n = 0; n < shnum; n++) {
                size_t head = shoff + (size_t)n * shentsize;
                if (u32at(head + 4) != 0x70000080) continue;
                size_t at = u32at(head + 0x10) + 26, end = u32at(head + 0x10) + u32at(head + 0x14);
                std::string name;
                while (at < end && at < file.size() && file[at]) name += (char)file[at++];
                if (!name.empty()) g_module_names[k] = name;
                break;
            }
        }
        if (g_module_names[k] == wanted) return (int)k + 1;
    }
    return 0;
}

void serve_loader(Call& c) {
    if (c.fn == 0xFF) { c.ret(0, 0x2E2E2E2E); return; }     // initialise: the version text the library accepts ("....")
    if (c.fn == 0) {                                // load and start a module: length of arguments, path, arguments
        std::string path = c.text(8);
        size_t colon = path.find(':');
        Iso9660::Entry entry;
        bool found = g_disc.find(path.substr(colon == std::string::npos ? 0 : colon + 1).c_str(), &entry);
        g_modules.push_back(path + (found ? "" : "  (NOT ON THE DISC)"));
        c.ret(0, found ? (u32)g_modules.size() : (u32)-203);
        c.ret(1, 0);
        c.delay = us(200, 3000);
        return;
    }
    if (c.fn == 9) {                                // search a module by its own name (not its file's)
        std::string wanted = c.text(8);
        if (wanted.empty()) wanted = c.text(0);
        int id = module_by_name(wanted);
        c.ret(0, id > 0 ? (u32)id : (u32)-202);     // -202: no such module
        return;
    }
    rt_note(rt_fmt("UNANSWERED module loader function 0x%x", c.fn));
    c.ret(0, (u32)-1);
}

void serve_heap(Call& c) {
    switch (c.fn) {
    case 1: {                                       // allocate
        u32 size = (c.arg(0) + 0xFF) & ~0xFFu;
        if (size > HEAP_END - g_heap_top) { c.ret(0, 0); rt_note("I/O-processor heap exhausted"); return; }
        c.ret(0, g_heap_top);
        g_heap_top += size;
        return;
    }
    case 2: c.ret(0, 0); return;                    // free (nothing is given back; the game frees at shutdown)
    case 5: c.ret(0, 0x200000); return;
    case 6: c.ret(0, HEAP_END - g_heap_top); return;            // largest free block
    case 7: c.ret(0, HEAP_END - g_heap_top + 0x300); return;    // total free
    }
    rt_note(rt_fmt("UNANSWERED heap function 0x%x", c.fn));
    c.ret(0, 0);
}

// ---- disc ---------------------------------------------------------------------------------
u32 g_stream_pos, g_stream_buffer_sectors;
bool g_streaming;
u64 g_disc_busy_until;

bool disc_read(u32 sector, u32 count, u8* into) {
    g_sectors_read += count;
    return g_disc.read(sector, count, into);
}

void serve_disc(Call& c) {
    switch (c.server) {
    case 0x80000592: c.ret(3, 0xFF); return;        // init
    case 0x80000593:                                // drive commands
        switch (c.fn) {
        case 0x01: {                                // clock: status, seconds, minutes, hours, pad, day, month, year (BCD)
            time_t now = time(nullptr);
            struct tm* t = localtime(&now);
            auto bcd = [](int v) { return (u8)(((v / 10) % 10) << 4 | (v % 10)); };
            u8 clock[8] = {0, bcd(t->tm_sec), bcd(t->tm_min), bcd(t->tm_hour), 0, bcd(t->tm_mday), bcd(t->tm_mon + 1), bcd(t->tm_year % 100)};
            c.ret(0, 1);
            if (c.recv != ~0u && c.rsize >= 12) memcpy(g_ram + c.recv + 4, clock, 8);
            return;
        }
        case 0x03: c.ret(0, 0x14); return;          // disc type: PlayStation 2 DVD
        case 0x04: c.ret(0, 0); return;             // last error: none
        case 0x05: c.ret(0, 1); c.ret(1, 0); return;    // tray
        case 0x0C: c.ret(0, g_streaming ? 0x12 : 0x0A); return;     // status: seeking / paused
        case 0x16: c.ret(0, 1); return;             // break
        case 0x22: c.ret(0, 1); return;             // media mode
        case 0x27: c.ret(0, 1); c.ret(1, 0); c.ret(2, 0xFFFFFFF0u); return;    // dual-layer information: one layer
        }
        break;
    case 0x80000595:                                // data commands
        switch (c.fn) {
        case 0x01: case 0x0D: {                     // read sectors to main memory / to I/O-processor memory
            u32 sector = c.arg(0), count = c.arg(1), to = c.arg(2) & 0x1FFFFFFF;
            u8* into = nullptr;
            if (c.fn == 0x01) { u32 a = guest_addr(to, count * 2048); if (a != ~0u) into = g_ram + a; }
            else if (to < 0x200000 && count * 2048 <= 0x200000 - to) into = g_iop + to;
            if (!into) rt_note(rt_fmt("disc read of %u sectors to 0x%x refused (not memory)", count, c.arg(2)));
            else disc_read(sector, count, into);
            c.ret(0, 0);
            c.delay = c.fn == 0x01 ? us(50 + count * 2, 100 + count * 500) : us(50 + count * 2, 16666);
            g_disc_busy_until = rt_cycles() + c.delay;
            return;
        }
        case 0x04: c.ret(0, 1); return;             // table of contents
        case 0x05: return;                          // seek
        case 0x08: c.delay = us(50, 16666); return; // pause
        case 0x09: {                                // stream: sector, count, address, command, mode
            u32 sector = c.arg(0), count = c.arg(1), to = c.arg(2) & 0x1FFFFFF;
            switch (c.arg(3)) {
            case 1: g_stream_pos = sector; g_streaming = true; c.ret(0, 1); return;
            case 2: {
                u32 a = guest_addr(to, count * 2048);
                if (a == ~0u) rt_note(rt_fmt("stream read of %u sectors to 0x%x refused", count, c.arg(2)));
                else disc_read(g_stream_pos, count, g_ram + a);
                g_stream_pos += count;
                c.ret(0, count);
                c.delay = us(50 + count * 2, 16666);
                return;
            }
            case 3: g_streaming = false; c.ret(0, 1); return;
            case 5: g_stream_buffer_sectors = sector; c.ret(0, 1); return;
            case 6: c.ret(0, g_stream_buffer_sectors); return;
            case 4: case 9: g_stream_pos = sector; c.ret(0, 1); return;
            }
            rt_note(rt_fmt("UNANSWERED disc stream command %u", c.arg(3)));
            return;
        }
        case 0x0E:                                  // ready? 2 yes, 6 not yet
            c.ret(0, rt_cycles() < g_disc_busy_until ? 6 : 2);
            c.delay = us(50, rt_cycles() < g_disc_busy_until ? 200 : 16666);
            return;
        }
        break;
    case 0x80000596: return;                        // power-off callback: never answered with data
    case 0x80000597: {                              // search: a 0x24-byte file record, then the path
        if (c.fn != 0) break;
        const char* path = c.text(c.ssize == 0x124 ? 0x20 : 0x24);
        Iso9660::Entry entry;
        bool found = g_disc.find(path, &entry);
        if (found && c.send != ~0u) { wr(c.send, entry.sector); wr(c.send + 4, entry.size); }
        if (!found) rt_note(rt_fmt("disc search: '%s' not found", path));
        c.ret(0, found ? 1 : 0);
        return;
    }
    case 0x8000059A: case 0x8000059C: c.ret(0, 2); return;      // disc ready
    }
    rt_note(rt_fmt("UNANSWERED disc server 0x%x function 0x%x", c.server, c.fn));
}

// ---- controller ports ---------------------------------------------------------------------
// The library reads controller state from a buffer in main memory that the I/O processor
// refreshes every vertical blank: two 0x80-byte records per port and slot, each with a
// frame count at +0x58; the library takes the newer one.  +0 the 32 bytes the controller
// sent (status, mode id, two bytes of buttons with 0 = held, four stick bytes, twelve
// pressures), +0x60 their length, +0x64 the mode table (current id at +0x65), +0x70
// state (6 stable, 5 a request is being carried out), +0x71 request state (0 done, 2
// busy), +0x72 ok.  Bytes not explained here are the constants the original driver left
// there for a DualShock 2.
struct Pad {
    u32 area = 0;                                   // offset into g_ram; 0 = not open
    u8 mode = 0x41, next_mode = 0x41;               // 0x41 digital, 0x73 analog, 0x79 analog with pressures
    u8 lock = 0;
    int busy = 0;                                   // blanks until a mode request is done
    bool connected = false;
    bool adopted = false;                           // taken over from a resumed image: frame counts continue
};
Pad g_pad[2][5];

void pad_record(u8* r, const Pad& p, const rta::PadState& state, u32 frame) {
    memset(r, 0, 0x80);
    if (!p.connected) { memcpy(r + 0x58, &frame, 4); return; }
    u16 held = state.buttons;
    r[1] = p.mode;
    r[2] = (u8)~(held & 0xFF);
    r[3] = (u8)~(held >> 8);
    if (p.mode != 0x41) { r[4] = state.rx; r[5] = state.ry; r[6] = state.lx; r[7] = state.ly; }
    if (p.mode == 0x79) {
        // pressures in the controller's order: right, left, up, down, triangle, circle, cross, square, L1, R1, L2, R2
        static const u16 order[12] = {rta::PAD_RIGHT, rta::PAD_LEFT, rta::PAD_UP, rta::PAD_DOWN, rta::PAD_TRIANGLE, rta::PAD_CIRCLE,
                                      rta::PAD_CROSS, rta::PAD_SQUARE, rta::PAD_L1, rta::PAD_R1, rta::PAD_L2, rta::PAD_R2};
        for (int k = 0; k < 12; k++) r[8 + k] = (held & order[k]) ? 0xFF : 0;
    }
    r[0x1F] = 0x5A;
    r[0x29] = 1; r[0x2A] = r[0x2B] = r[0x2C] = r[0x2D] = 0xFF; r[0x2E] = p.busy ? 5 : 6;
    static const u8 k30[8] = {1, 2, 0, 0x0A, 1, 1, 1, 0x14};
    memcpy(r + 0x30, k30, 8);
    r[0x40] = 2; r[0x42] = 1;
    r[0x50] = 4; r[0x52] = 7;                       // the two modes this controller has
    memcpy(r + 0x58, &frame, 4);
    r[0x60] = p.busy ? 0 : 0x20;
    r[0x64] = 2; r[0x65] = p.mode; r[0x66] = 3; r[0x67] = p.busy ? 0 : 1; r[0x68] = 2; r[0x69] = p.mode == 0x41 ? 0 : 1;
    r[0x6A] = 2; r[0x6B] = 1; r[0x6C] = p.mode == 0x79 ? 1 : 0; r[0x6D] = p.mode == 0x41 ? 0 : 1; r[0x6E] = p.lock;
    r[0x70] = p.busy ? 5 : 6; r[0x71] = p.busy ? 2 : 0; r[0x72] = 1;
    if (p.mode == 0x79) { r[0x78] = 0xFF; r[0x79] = 0xFF; r[0x7A] = 3; }
}

// What a port's controller reports at this blank.  The part of it the script holds reaches
// the game `g_pad_delay` blanks later (default 1): on the console the I/O processor reads
// the controller at the blank and its copy reaches main memory during the frame, after the
// game has read the buffer for that frame.  The reference run in the emulator shows the
// same one-tick lag, and a script written for one machine presses on the same tick on the
// other because of it.  The rest of the answer - what a person holds: keyboard, controller
// - is not made to wait: it is in the game's buffer at the blank it was read at
// (`g_pad_live_delay` blanks later, default 0).  The two are told apart here: a button is
// the script's when the script holds it too, a stick when it is where the script has it.
// (With no source set, everything is the script's: nothing changes for a headless run.)
unsigned g_pad_delay = 1, g_pad_live_delay = 0;
rta::PadState g_pad_history[2][8], g_pad_live_history[2][8];
rta::PadState g_pad_now[2];
void pad_sample(u64 blank) {
    for (unsigned port = 0; port < 2; port++) {
        rta::PadState state, scripted = script_pad(port), live;
        if (g_hooks.pad) g_hooks.pad->read(port, blank, state);
        else state = scripted;
        live.buttons = state.buttons & (u16)~scripted.buttons;
        state.buttons &= scripted.buttons;
        if (state.lx != scripted.lx || state.ly != scripted.ly) { live.lx = state.lx; live.ly = state.ly; state.lx = state.ly = 128; }
        if (state.rx != scripted.rx || state.ry != scripted.ry) { live.rx = state.rx; live.ry = state.ry; state.rx = state.ry = 128; }
        for (unsigned k = 7; k > 0; k--) { g_pad_history[port][k] = g_pad_history[port][k - 1]; g_pad_live_history[port][k] = g_pad_live_history[port][k - 1]; }
        g_pad_history[port][0] = state;
        g_pad_live_history[port][0] = live;
        rta::PadState now = g_pad_history[port][g_pad_delay < 8 ? g_pad_delay : 7];
        const rta::PadState& held = g_pad_live_history[port][g_pad_live_delay < 8 ? g_pad_live_delay : 7];
        now.buttons |= held.buttons;
        if (now.lx == 128 && now.ly == 128) { now.lx = held.lx; now.ly = held.ly; }
        if (now.rx == 128 && now.ry == 128) { now.rx = held.rx; now.ry = held.ry; }
        g_pad_now[port] = now;
    }
}

// Replay of another machine's controller data (--opt pad-replay=FILE; lines "<episode>
// <tick> <frame> <64 hex digits>": the 32 bytes the first port's controller delivered to
// the game in the frame-th displayed frame of that simulation tick; an episode starts
// whenever the tick counter goes back, i.e. at every level start).  A script cannot place
// a press on a given tick on two machines whose frames run late at different moments;
// with the other machine's bytes handed to the game for the same tick, the two
// simulations get the same input whatever their frame timing.  The frames of one tick
// are followed in the other machine's order: while the tick stands still here and the
// other machine has a further frame of it (a menu, a message box: one frame per blank on
// both), that frame's record is used; otherwise the first record of the next tick.
std::map<std::pair<u32, u64>, std::vector<u8>> g_replay;
u32 g_replay_episode, g_replay_last_tick, g_replay_same;
const std::vector<u8>* g_replay_now;
u64 g_replay_used, g_replay_load_rows;
int g_replay_log = -1;
void replay_load(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) rt_die("cannot read %s", path);
    unsigned episode, tick, frame;
    char hex[80];
    while (fscanf(f, "%u %u %u %79s", &episode, &tick, &frame, hex) == 4) {
        std::vector<u8> bytes;
        for (size_t k = 0; k + 1 < strlen(hex) && bytes.size() < 32; k += 2) {
            char pair[3] = {hex[k], hex[k + 1], 0};
            bytes.push_back((u8)strtoul(pair, nullptr, 16));
        }
        if (bytes.size() == 32) g_replay[{episode, ((u64)tick << 32) | frame}] = bytes;
    }
    fclose(f);
    printf("controller replay: %zu frames from %s\n", g_replay.size(), path);
}
// While a level loads, the frames shown are the loading screen's (its own thread:
// loadscreen_renderLoop 0x32187c, between loadscreen_start and loadscreen_stop, flag
// g_loadscreenActive 0x506094); the main loop's next frame after the load is the level's
// first tick, and it goes by what the controller buffer holds then.  The other machine's
// rows of those loading frames say what its controller held while it loaded, and it loaded
// for a different number of frames (the rig three to eight times as many).  Followed frame
// by frame, as the frames of a menu are, the last blank of the load here got one of the
// other machine's loading rows instead of its first-tick row, and a level entered with the
// stick held went another way from tick 1 (docs/issues/native-proof.md 3b.3).  So: at a
// blank at which the loading screen is up, the row handed over is the next tick's first.
//
// Not for the front end's own level ("intro", the title's backdrop): after its load the
// front end runs ten frames of its own before the first tick, and they have to see what
// they saw on the other machine - a button held through the load there is still held,
// and handing the first tick's row (the button let go) during the load makes it a button
// pressed anew afterwards (Ran: the front end then goes another way from tick 222 on).
// What is left as it was, too: a notice over a level before its first tick (the tick
// stands on after the load) is followed by the rows of the standing tick.
void replay_step() {
    g_replay_now = nullptr;
    if (g_replay.empty()) return;
    if (g_replay_log < 0) g_replay_log = getenv("RTA_REPLAY_LOG") ? 1 : 0;
    u32 tick = rd(0x44FDCC);                        // g_simFrame
    if (tick < g_replay_last_tick) g_replay_episode++;
    g_replay_same = tick == g_replay_last_tick ? g_replay_same + 1 : 0;
    g_replay_last_tick = tick;
    bool loading = g_ram[0x506094] != 0;            // g_loadscreenActive
    // The other machine showed another frame at this tick (a menu, a message box): this
    // machine's next frame gets that frame's data.  Otherwise - and through a level load -
    // the next frame computes the next tick.
    auto step = g_replay.find({g_replay_episode, (u64)(tick + 1) << 32});
    auto found = g_replay.find({g_replay_episode, ((u64)tick << 32) | (g_replay_same + 1)});
    bool load_rule = loading && step != g_replay.end() && memcmp(g_ram + 0x41B721, "intro", 6) != 0;      // g_levelName
    if (load_rule) { if (found != g_replay.end() && found->second != step->second) g_replay_load_rows++; found = step; }
    else if (found == g_replay.end()) found = step;
    if (found != g_replay.end()) { g_replay_now = &found->second; g_replay_used++; }
    if (g_replay_log && (g_replay_same || tick <= 2))
        printf("replay: blank %llu episode %u tick %u same %u loading %d -> %s\n", (unsigned long long)rt_fields(), g_replay_episode, tick, g_replay_same,
               (int)loading, found == g_replay.end() ? "nothing" : found == step ? "the next tick's first row" : "a row of this tick");
}

void pad_refresh(unsigned port, unsigned slot, u64 blank, bool both) {
    Pad& p = g_pad[port][slot];
    if (!p.area) return;
    if (p.busy && --p.busy == 0) p.mode = p.next_mode;
    u8* r = g_ram + p.area;
    u32 f0, f1;
    memcpy(&f0, r + 0x58, 4);
    memcpy(&f1, r + 0xD8, 4);
    rta::PadState state = slot == 0 ? g_pad_now[port] : rta::PadState();
    (void)blank;
    if (both) { pad_record(r, p, state, 0); pad_record(r + 0x80, p, state, 1); return; }
    u8* fresh = f0 < f1 ? r : r + 0x80;
    pad_record(fresh, p, state, (f0 < f1 ? f1 : f0) + 1);
    if (port == 0 && slot == 0 && g_replay_now && !p.busy) memcpy(fresh, g_replay_now->data(), 32);
}

void serve_pad(Call& c) {
    if (c.server == 0x80000101) return;             // the second server carries nothing in this library version
    u32 command = c.arg(0), port = c.arg(1), slot = c.arg(2);
    Pad* p = port < 2 && slot < 5 ? &g_pad[port][slot] : nullptr;
    switch (command) {
    case 0x01: {                                    // open: port, slot, -, buffer
        u32 area = guest_addr(c.arg(4), 0x100);
        if (!p || slot > 3 || area == ~0u) { c.ret(3, 0); return; }
        *p = Pad();
        p->area = area;
        p->connected = slot == 0;                   // no multitap: only the first slot of a port has a controller
        pad_refresh(port, slot, rt_fields(), true);
        c.ret(3, 1);
        c.ret(5, 0x4EEC0 + (port * 4 + slot) * 0x1C4);     // the driver's own record, never read by the game
        return;
    }
    case 0x06:                                      // set main mode: mode (0 digital, 1 analog), lock
        if (!p || !p->connected || p->busy) { c.ret(5, 0); return; }
        p->next_mode = c.arg(3) ? (p->mode == 0x41 ? 0x73 : p->mode) : 0x41;
        p->lock = (u8)c.arg(4);
        p->busy = 4;
        c.ret(5, 1);
        return;
    case 0x07:                                      // set actuators directly
        if (g_hooks.pad && p && c.send != ~0u) g_hooks.pad->rumble(port, g_ram[c.send + 12], g_ram[c.send + 13]);
        c.ret(5, 1);
        return;
    case 0x08: c.ret(5, 1); return;                 // actuator alignment
    case 0x0A:                                      // button information: switches the pressures on
        if (p && p->connected && p->mode != 0x41) { p->next_mode = 0x79; p->busy = 3; }
        c.ret(5, 1);
        return;
    case 0x09: c.ret(3, 0x3FFFF); return;           // button mask
    case 0x0C: c.ret(3, 2); return;                 // number of ports
    case 0x0D: c.ret(3, 1); return;                 // slots of a port: one (no multitap)
    case 0x0E: if (p) p->area = 0; c.ret(3, 1); return;     // close
    case 0x0F: c.ret(3, 1); return;                 // end
    case 0x10: c.ret(3, 1); return;                 // init
    case 0x12: c.ret(3, 0x422); return;             // module version
    }
    rt_note(rt_fmt("UNANSWERED controller command 0x%x", command));
}

void serve_multitap(Call& c) {
    switch (c.fn) {
    case 1: c.ret(1, 1); return;                    // port open: ok
    case 2: c.ret(1, 1); return;                    // port close
    case 3: c.ret(1, 0); return;                    // connection: none
    case 5: c.ret(0, 0x310); return;                // module version
    case 6: c.ret(0, 1); return;
    }
    rt_note(rt_fmt("UNANSWERED multitap function 0x%x", c.fn));
}

// ---- memory card --------------------------------------------------------------------------
// A card is a directory: <root>/mc0, <root>/mc1.  A save is a directory in it, its files
// plain files; ':' and '\' in a name are written %3A and %5C.  This is how the Play!
// emulator keeps cards, so a card directory can be moved between it and this runtime.
const u32 MC_NO_ENTRY = (u32)-4, MC_DENIED = (u32)-5, MC_NOT_EMPTY = (u32)-6;
FILE* g_mc_file[5];
std::string g_mc_cwd[2];
bool g_mc_known[2];
struct McEntry { u8 raw[0x40]; };
std::vector<McEntry> g_mc_found;
size_t g_mc_found_at;
u64 g_mc_bytes_read, g_mc_bytes_written;

std::string mc_absolute(const std::string& path) {
    std::vector<std::string> parts;
    size_t start = 0;
    for (;;) {
        size_t slash = path.find('/', start);
        std::string part = path.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
        if (part == "..") { if (!parts.empty()) parts.pop_back(); }
        else if (!part.empty() && part != ".") parts.push_back(part);
        if (slash == std::string::npos) break;
        start = slash + 1;
    }
    std::string out;
    for (auto& part : parts) out += "/" + part;
    return out;
}
std::string mc_encode(const std::string& name) {
    std::string out;
    for (char ch : name) {
        if (ch == ':') out += "%3A"; else if (ch == '\\') out += "%5C"; else out += ch;
    }
    return out;
}
std::string mc_decode(const std::string& name) {
    std::string out;
    for (size_t i = 0; i < name.size(); i++) {
        if (name[i] == '%' && i + 2 < name.size() + 0 && isxdigit((unsigned char)name[i + 1]) && isxdigit((unsigned char)name[i + 2])) {
            out += (char)strtoul(name.substr(i + 1, 2).c_str(), nullptr, 16);
            i += 2;
        } else out += name[i];
    }
    return out;
}
fs::path mc_root(u32 port) { return fs::path(g_opt.card_root) / (port ? "mc1" : "mc0"); }
// the card's path for a name the game gave (relative names are below the current directory)
std::string mc_guest(u32 port, const std::string& name) {
    return mc_absolute(!name.empty() && name[0] == '/' ? name : g_mc_cwd[port] + "/" + name);
}
fs::path mc_host(u32 port, const std::string& guest) {
    fs::path p = mc_root(port);
    size_t start = 1;
    while (start < guest.size()) {
        size_t slash = guest.find('/', start);
        p /= mc_encode(guest.substr(start, slash == std::string::npos ? std::string::npos : slash - start));
        if (slash == std::string::npos) break;
        start = slash + 1;
    }
    return p;
}

// '?' is one optional character and '*' any run of characters, '/' included
bool mc_match(const char* pattern, const char* text) {
    if (!*pattern) return !*text;
    if (*pattern == '*') {
        for (const char* t = text;; t++) {
            if (mc_match(pattern + 1, t)) return true;
            if (!*t) return false;
        }
    }
    if (*pattern == '?') return mc_match(pattern + 1, text) || (*text && mc_match(pattern + 1, text + 1));
    return *text == *pattern && mc_match(pattern + 1, text + 1);
}

McEntry mc_entry(const std::string& name, u32 size, u16 attributes, const fs::path* stamp_from) {
    McEntry e;
    memset(e.raw, 0, sizeof(e.raw));
    if (stamp_from) {
        std::error_code ec;
        auto ftime = fs::last_write_time(*stamp_from, ec);
        if (!ec) {
            auto system = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
                ftime - fs::file_time_type::clock::now() + std::chrono::system_clock::now());
            time_t seconds = std::chrono::system_clock::to_time_t(system);
            struct tm* t = localtime(&seconds);
            u16 year = (u16)(t->tm_year + 1900);
            u8 stamp[8] = {0, (u8)t->tm_sec, (u8)t->tm_min, (u8)t->tm_hour, (u8)t->tm_mday, (u8)(t->tm_mon + 1), (u8)year, (u8)(year >> 8)};   // the card's month is 1..12
            memcpy(e.raw, stamp, 8);
            memcpy(e.raw + 8, stamp, 8);
        }
    }
    memcpy(e.raw + 0x10, &size, 4);
    memcpy(e.raw + 0x14, &attributes, 2);
    strncpy((char*)e.raw + 0x20, name.c_str(), 0x1F);
    return e;
}

void mc_search(const fs::path& base, const fs::path& dir, const std::string& pattern, bool& found) {
    std::vector<fs::path> children;
    std::error_code ec;
    for (auto& element : fs::directory_iterator(dir, ec)) children.push_back(element.path());
    std::sort(children.begin(), children.end());
    for (auto& child : children) {
        std::string relative = child.generic_string().substr(base.generic_string().size());
        bool directory = fs::is_directory(child, ec);
        if (mc_match(pattern.c_str(), relative.c_str())) {
            if (directory) {
                u32 count = 0;
                for (auto& inner : fs::directory_iterator(child, ec)) { (void)inner; count++; }
                g_mc_found.push_back(mc_entry(mc_decode(child.filename().string()), count, 0x8427, &child));
            } else {
                g_mc_found.push_back(mc_entry(mc_decode(child.filename().string()), (u32)fs::file_size(child, ec), 0x8497, &child));
            }
            found = true;
        }
        if (directory && !found) mc_search(base, child, pattern, found);
    }
}

void serve_card(Call& c) {
    c.delay = us(100, 2713);
    u32 fn = c.fn & 0xFF;
    std::error_code ec;
    if (fn == 0xFE || fn == 0x70) { c.ret(0, 0); c.ret(1, 0x20A); c.ret(2, 0x20E); return; }
    if (fn == 0x14) { c.ret(0, 0); return; }
    if (fn == 0x15) { c.ret(0, 1); return; }
    // file commands: handle, -, -, size, offset, origin, buffer, parameter block, 16 bytes of data
    if (fn == 3 || fn == 4 || fn == 5 || fn == 6 || fn == 0x0A) {
        u32 handle = c.arg(0), size = c.arg(3), offset = c.arg(4), origin = c.arg(5);
        FILE* f = handle < 5 ? g_mc_file[handle] : nullptr;
        if (fn == 5 && c.arg(7)) { u32 p = guest_addr(c.arg(7), 8); if (p != ~0u) { wr(p, 0); wr(p + 4, 0); } }
        if (!f) { c.ret(0, fn == 5 || fn == 6 ? MC_DENIED : (u32)-1); return; }
        u32 buffer = guest_addr(c.arg(6), size);
        switch (fn) {
        case 3: fclose(f); g_mc_file[handle] = nullptr; c.ret(0, 0); return;
        case 4: fseek(f, (long)(s32)offset, origin == 1 ? SEEK_CUR : origin == 2 ? SEEK_END : SEEK_SET); c.ret(0, (u32)ftell(f)); return;
        case 5: {
            size_t got = buffer == ~0u ? 0 : fread(g_ram + buffer, 1, size, f);
            fseek(f, ftell(f), SEEK_SET);
            g_mc_bytes_read += got;
            c.ret(0, (u32)got);
            return;
        }
        case 6: {
            // the first `origin` bytes come inside the command (the unaligned head of the caller's buffer)
            u32 total = 0;
            if (origin && origin <= 16) total += (u32)fwrite(g_ram + c.send + 0x20, 1, origin, f);
            if (buffer != ~0u) total += (u32)fwrite(g_ram + buffer, 1, size, f);
            fflush(f);
            g_mc_bytes_written += total;
            c.ret(0, total);
            return;
        }
        default: fflush(f); c.ret(0, 0); return;
        }
    }
    u32 port = c.arg(1 - 1), slot = c.arg(1);       // path commands: port, slot, flags, max entries, table, name
    if (fn == 1) {                                  // card information: -, port, slot, want formatted, want free, want type, -, out
        port = c.arg(1);
        if (port >= 2) { c.ret(0, (u32)-2); return; }
        u32 out = guest_addr(c.arg(7), 0x94);
        if (out != ~0u) {
            if (c.arg(5)) wr(out, 2);               // a PlayStation 2 card
            if (c.arg(4)) wr(out + 4, 0x2000);      // free clusters of 1,024 bytes
            if (c.arg(3)) wr(out + 0x90, 1);        // formatted
        }
        c.ret(0, g_mc_known[port] ? 0 : (u32)-1);   // -1: a card that was not there at the last call
        g_mc_known[port] = true;
        return;
    }
    (void)slot;
    if (port >= 2) { c.ret(0, (u32)-1); return; }
    u32 flags = c.arg(2), table = c.arg(4);
    s32 max_entries = (s32)c.arg(3);
    std::string name = c.text(0x14);
    switch (fn) {
    case 2: {                                       // open; flag 0x40 alone makes a directory
        fs::path host = mc_host(port, mc_guest(port, name));
        if (flags == 0x40) {
            if (fs::exists(host, ec)) { c.ret(0, MC_NO_ENTRY); return; }
            c.ret(0, fs::create_directory(host, ec) ? 0 : (u32)-1);
            return;
        }
        if ((flags & 0x200) && !fs::exists(host, ec)) {
            FILE* made = fopen(host.string().c_str(), "wb");
            if (!made) { c.ret(0, MC_NO_ENTRY); return; }
            fclose(made);
        }
        if ((flags & 0x400) && fs::exists(host, ec)) { FILE* cut = fopen(host.string().c_str(), "wb"); if (cut) fclose(cut); }
        u32 handle = 0;
        while (handle < 5 && g_mc_file[handle]) handle++;
        FILE* f = handle < 5 && fs::is_regular_file(host, ec) ? fopen(host.string().c_str(), "r+b") : nullptr;
        if (!f) { c.ret(0, MC_NO_ENTRY); return; }
        g_mc_file[handle] = f;
        c.ret(0, handle);
        return;
    }
    case 0x0C: {                                    // change directory; the old one is written to `table`
        u32 out = table ? guest_addr(table, 256) : ~0u;
        if (out != ~0u) {
            std::string old = g_mc_cwd[port].empty() ? "/" : g_mc_cwd[port];
            strncpy((char*)g_ram + out, old.c_str(), 255);
        }
        std::string wanted = mc_guest(port, name);
        if (fs::is_directory(mc_host(port, wanted), ec)) { g_mc_cwd[port] = wanted; c.ret(0, 0); }
        else c.ret(0, MC_NO_ENTRY);
        return;
    }
    case 0x0D: {                                    // directory listing; flags 0 starts one, otherwise it continues
        if (flags == 0) {
            g_mc_found.clear();
            g_mc_found_at = 0;
            fs::path base = name[0] == '/' ? mc_root(port) : mc_host(port, g_mc_cwd[port]);
            if (!fs::exists(base, ec)) { c.ret(0, MC_NO_ENTRY); return; }
            std::string pattern = name;
            if (pattern.compare(0, 2, "./") == 0) pattern = pattern.substr(1);
            if (pattern.empty() || pattern[0] != '/') pattern = "/" + pattern;
            if (pattern.size() > 1 && pattern.back() == '/') pattern.pop_back();
            std::string folder = pattern.substr(0, pattern.rfind('/') + 1);
            if (!fs::exists(base / fs::path(folder.substr(1)), ec)) { c.ret(0, MC_NO_ENTRY); return; }
            if (mc_match(pattern.c_str(), (folder + ".").c_str())) g_mc_found.push_back(mc_entry(".", 0, 0x8427, nullptr));
            if (mc_match(pattern.c_str(), (folder + "..").c_str())) g_mc_found.push_back(mc_entry("..", 0, 0x8427, nullptr));
            bool found = false;
            mc_search(base, base, pattern, found);
        }
        u32 count = 0;
        u32 out = max_entries > 0 ? guest_addr(table, (u32)max_entries * 0x40) : ~0u;
        while (max_entries > 0 && count < (u32)max_entries && g_mc_found_at < g_mc_found.size()) {
            if (out != ~0u) memcpy(g_ram + out + count * 0x40, g_mc_found[g_mc_found_at].raw, 0x40);
            g_mc_found_at++;
            count++;
        }
        c.ret(0, count);
        return;
    }
    case 0x0E: {                                    // set file information: only a new name is carried out
        u32 entry = guest_addr(table, 0x40);
        if ((flags & 0x10) && entry != ~0u) {
            fs::path from = mc_host(port, mc_guest(port, name));
            fs::path to = from.parent_path() / mc_encode((const char*)g_ram + entry + 0x20);
            if (from != to) {
                if (!fs::exists(from, ec)) { c.ret(0, MC_NO_ENTRY); return; }
                fs::rename(from, to, ec);
                if (ec) { c.ret(0, (u32)-1); return; }
            }
        }
        c.ret(0, 0);
        return;
    }
    case 0x0F: {                                    // delete
        fs::path host = mc_host(port, mc_guest(port, name));
        if (!fs::exists(host, ec)) { c.ret(0, MC_NO_ENTRY); return; }
        if (fs::is_directory(host, ec) && !fs::is_empty(host, ec)) { c.ret(0, MC_NOT_EMPTY); return; }
        c.ret(0, fs::remove(host, ec) ? 0 : (u32)-1);
        return;
    }
    case 0x12: c.ret(0, fs::is_directory(mc_root(port) / fs::path(name[0] == '/' ? name.substr(1) : name), ec) ? 0xFE : MC_NO_ENTRY); return;
    }
    rt_note(rt_fmt("UNANSWERED memory card function 0x%x", c.fn));
    c.ret(0, (u32)-1);
}

// ---- dispatch -----------------------------------------------------------------------------
bool serve(Call& c) {
    switch (c.server) {
    case 0x80000006: serve_loader(c); return true;
    case 0x80000003: serve_heap(c); return true;
    case 0x80000592: case 0x80000593: case 0x80000595: case 0x80000596: case 0x80000597: case 0x8000059A: case 0x8000059C:
        serve_disc(c); return true;
    case 0x80000100: case 0x80000101: serve_pad(c); return true;
    case 0x80000900: case 0x80000901: case 0x80000902: case 0x80000903: serve_multitap(c); return true;
    case 0x80000400: serve_card(c); return true;
    case 0x50494C42:                                // USB headset driver: nothing plugged in
        if (c.fn == 0x10) { c.ret(2, 0x1090400); c.ret(8, 0x530); }    // init: driver version 1.09.004, largest packet
        // 1: enumerate (lgAudEnumerate 0x36c1a0 asks for device 0, 1, 2 ... until an answer
        // has bit 31 set; a net game does that after its first ticks): no such device
        if (c.fn == 1) c.ret(0, 0x8000000Au);
        return true;
    case 0x61766973:                                // USB keyboard driver
        // 3: versions - the library sends its own (1.06) and wants the driver's beside it;
        // 1: read - answered when a key arrives, so with no keyboard never
        if (c.fn == 3 && c.recv != ~0u && c.rsize >= 8) { g_ram[c.recv + 6] = 0x06; g_ram[c.recv + 7] = 0x01; }
        if (c.fn == 1) c.never = true;
        return true;
    }
    if (sound_rpc(c.server, c.fn, c.send, c.ssize, c.recv, c.rsize)) return true;
    return false;
}

// A no-wait call is "in progress" for the library while the packet it points at carries
// the call's number and the busy bit (sceSifCheckStatRpc 0x3568f0 reads exactly that).
// The packets are 64 small blocks at 0xff000, below the executable, which nothing else uses.
const u32 PACKETS = 0x000FF000;
u32 g_packet_next, g_call_number = 1;

}  // namespace

u8* iop_ram() { return g_iop; }

void iop_init(const IopOptions& options) {
    g_opt = options;
    g_iop = (u8*)calloc(0x200000, 1);
    if (!g_opt.disc.empty() && !g_disc.open(g_opt.disc.c_str())) rt_die("cannot read the disc image %s", g_opt.disc.c_str());
    std::error_code ec;
    fs::create_directories(mc_root(0), ec);
    fs::create_directories(mc_root(1), ec);
    if (const char* delay = rt_option("pad-delay")) g_pad_delay = (unsigned)atoi(delay);
    if (const char* delay = rt_option("pad-live-delay")) g_pad_live_delay = (unsigned)atoi(delay);
    if (const char* replay = rt_option("pad-replay")) replay_load(replay);
    // A resumed image has its controller ports open already; name their buffers to drive them.
    for (unsigned port = 0; port < 2; port++) {
        const char* text = rt_option(port ? "pad1" : "pad0");
        if (!text) continue;
        Pad& p = g_pad[port][0];
        p.area = (u32)strtoul(text, nullptr, 16);
        p.mode = p.next_mode = 0x79;
        p.lock = 3;
        p.connected = p.adopted = true;
    }
}

// The library's client structures are static data of the executable, so an image taken
// from the emulator has them at these addresses (the binds of a boot of the original).
void iop_adopt() {
    static const u32 known[][2] = {
        {0x008F8A68, 0x80000592}, {0x0050A7C0, 0x80000593}, {0x008F2780, 0x80000006}, {0x009098F0, 0x61766973},
        {0x008FEC80, 0x50494C42}, {0x008F23C0, 0x80000003}, {0x008EDF80, 0x80000100}, {0x008EDFA8, 0x80000101},
        {0x008EE280, 0x80000900}, {0x008F8A40, 0x80000597}, {0x00509E10, 0x80000595}, {0x008F6140, 0x80000701},
        {0x00877160, 0x000163A5}, {0x008F7240, 0x80000400}};
    unsigned taken = 0;
    for (auto& k : known)
        if (rd(k[0] + 0x24)) { g_clients[k[0]] = k[1]; taken++; }     // bound in the image
    g_heap_top = 0x1AAC00;                          // after the four allocations of the game's start-up
    g_stream_buffer_sectors = 0x28;
    g_mc_known[0] = g_mc_known[1] = true;
    printf("adopted %u clients of the image\n", taken);
}

void iop_vblank(u64 number) {
    pad_sample(number);
    replay_step();
    for (unsigned port = 0; port < 2; port++)
        for (unsigned slot = 0; slot < 5; slot++) pad_refresh(port, slot, number, false);
}

// System call 0x77, sceSifSetDma: `count` records of (source in main memory, destination
// in I/O-processor memory, size, flags).  The data is there when the call returns.
u32 iop_sif_set_dma(u32 list, u32 count) {
    for (u32 i = 0; i < count; i++) {
        u32 record = guest_addr(list + i * 16, 16);
        if (record == ~0u) break;
        u32 from = guest_addr(rd(record), rd(record + 8)), to = rd(record + 4) & 0x1FFFFFFF, size = rd(record + 8);
        if (from == ~0u || to >= 0x200000 || size > 0x200000 - to) {
            rt_note(rt_fmt("SifSetDma of 0x%x bytes from 0x%x to 0x%x refused", size, rd(record), rd(record + 4)));
            continue;
        }
        memcpy(g_iop + to, g_ram + from, size);
        g_sif_dma_bytes += size;
        if (rd(record + 12) & ~0u) rt_note(rt_fmt("SifSetDma with flags 0x%x", rd(record + 12)));
        // A command packet (flagged; 16 bytes of header with the command number in the
        // third word).  0x80000001 sets a status register on the other side; the
        // multi-thread RPC library (sceSifMInitRpc 0x3646c8) sends it and then polls its own
        // status register 1 - the word at 0x8ef2c4, sceSifGetSreg(1) - until the manager on
        // the I/O processor (MSIFRPC.IRX) has set it in return.  That manager's calls are
        // all replaced in a network build, so its only act here is this answer.
        if (rd(record + 12) && size >= 16 && rd(from + 8) == 0x80000001u) {
            rt_note("SIF command 0x80000001 (status register): answered as the multi-thread RPC manager does");
            rt_after(usec_to_cycles(50), [] { wr(0x8EF2C4, 1); });
        }
    }
    return 1;
}

void iop_report() {
    if (g_calls.empty()) return;
    printf("I/O processor: calls by server and function:\n");
    u32 last = 0;
    for (auto& kv : g_calls) {
        if (kv.first.first != last) { printf("%s  0x%08x:", last ? "\n" : "", kv.first.first); last = kv.first.first; }
        printf(" %x x%llu", kv.first.second, (unsigned long long)kv.second);
    }
    printf("\n  %zu modules asked for; %llu disc sectors read; memory card: %llu bytes read, %llu written; %llu bytes sent to I/O-processor memory\n",
           g_modules.size(), (unsigned long long)g_sectors_read, (unsigned long long)g_mc_bytes_read,
           (unsigned long long)g_mc_bytes_written, (unsigned long long)g_sif_dma_bytes);
    for (auto& m : g_modules) if (m.find("NOT ON") != std::string::npos) printf("  module %s\n", m.c_str());
    if (!g_replay.empty()) printf("  controller replay: %llu blanks took their data from the replay file; at %llu blanks of a level load the next tick's first row was handed over "
                                  "where the other machine's loading frame held something else\n", (unsigned long long)g_replay_used, (unsigned long long)g_replay_load_rows);
}

// ---- the three library functions the runtime supplies ------------------------------------
void fn_00355d68(Ctx* c) { c->r[2] = 0; }           // sceSifInitRpc: nothing to shake hands with

void fn_00356510(Ctx* c) {                          // sceSifBindRpc(client, server id, mode)
    u32 client = guest_addr((u32)c->r[4], 0x28), server = (u32)c->r[5];
    if (client == ~0u) { c->r[2] = SX32(-1); return; }
    Call probe = {server, 0xFFFFFFFFu, ~0u, 0, ~0u, 0, 0};
    bool known = server == 0x80000701u || server == 0x000163A5u;
    if (!known) {
        switch (server) {
        case 0x80000006: case 0x80000003: case 0x80000592: case 0x80000593: case 0x80000595: case 0x80000596: case 0x80000597:
        case 0x8000059A: case 0x8000059C: case 0x80000100: case 0x80000101: case 0x80000900: case 0x80000400: case 0x50494C42:
        case 0x61766973: known = true;
        }
    }
    (void)probe;
    if (!known) rt_note(rt_fmt("bind to UNKNOWN server 0x%08x (answered as present; its calls return nothing)", server));
    g_clients[client] = server;
    wr(client + 0x00, 0);                           // no packet pending
    wr(client + 0x08, (u32)-1);
    wr(client + 0x10, 0);
    wr(client + 0x14, 0x1F0000);                    // the server's buffer on the other side
    wr(client + 0x18, 0x1F0000);
    wr(client + 0x24, 0x1E0000 | (u32)g_clients.size());    // non-zero: bound
    c->r[2] = 0;
    if (!((u32)c->r[6] & 1)) rt_sleep(c, us(100, 1000));
}

void fn_003566f0(Ctx* c) {                          // sceSifCallRpc(client, function, mode, send, size, receive, size, end function, end argument)
    u32 client = guest_addr((u32)c->r[4], 0x28), mode = (u32)c->r[6];
    u32 end_fn = (u32)c->r[11], end_arg = LD32((u32)c->r[29]);
    c->r[2] = 0;
    if (client == ~0u) { c->r[2] = SX32(-1); return; }
    auto bound = g_clients.find(client);
    if (bound == g_clients.end()) {
        // A client bound before a resumed image was taken: its receive buffer keeps the
        // last answer the emulator's I/O processor gave.
        rt_note(rt_fmt("call to function 0x%x of a client bound before the image (0x%x): left unanswered", (u32)c->r[5], (u32)c->r[4]));
        return;
    }
    Call call;
    call.server = bound->second;
    call.fn = (u32)c->r[5];
    call.ssize = (u32)c->r[8];
    call.rsize = (u32)c->r[10];
    call.send = call.ssize ? guest_addr((u32)c->r[7], call.ssize) : ~0u;
    call.recv = call.rsize ? guest_addr((u32)c->r[9], call.rsize) : ~0u;
    call.delay = us(50, 500);
    g_calls[{call.server, call.fn}]++;
    if (!serve(call)) rt_note(rt_fmt("UNANSWERED call: server 0x%08x function 0x%x (send %u, receive %u bytes)", call.server, call.fn, call.ssize, call.rsize));
    wr(client + 0x1C, end_fn);
    wr(client + 0x20, end_arg);
    if (mode & 1) {                                 // no wait: completion comes later, as an interrupt would
        u32 packet = PACKETS + (g_packet_next++ & 63) * 0x40;
        u32 number = g_call_number++;
        memset(g_ram + packet, 0, 0x40);
        wr(packet + 0x10, 1);
        wr(packet + 0x18, number);
        wr(client + 0x00, packet);
        wr(client + 0x04, number);
        if (!call.never) rt_after(call.delay, [packet, end_fn, end_arg] {
            wr(packet + 0x10, 0);
            if (end_fn) rt_call_handler(end_fn, end_arg);
        });
        return;
    }
    if (call.never) rt_die("a blocking call to server 0x%08x function 0x%x would never return", call.server, call.fn);
    wr(client + 0x00, 0);
    if (end_fn) rt_after(call.delay, [end_fn, end_arg] { rt_call_handler(end_fn, end_arg); });
    rt_sleep(c, call.delay);
}
