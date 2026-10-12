// proof_rt.cpp - what the instrumented translation (instrument.py, proof.h) calls.
//
// Linked into a build of the headless runtime of its own (build_proof.py); the runtime's
// sources are not changed.  Everything is switched on with --opt:
//
//   --opt proof-hits=FILE          at the end of the run: every entry point and how often
//                                  it was reached
//   --opt proof-capture=DIR        record the machine state at the entry of the functions
//   --opt proof-want=FILE          listed in FILE (one hex address per line; without the
//   --opt proof-per=N              file: every entry point), N states per function
//                                  (default 3: its 1st, 2nd, 5th, 20th, 100th ... call)
//   --opt proof-watch=ADDR:LEN     report every change of LEN bytes at ADDR (hex) with the
//   --opt proof-watch-ticks=E:LO:HI  two points of execution it happened between, while
//                                  the simulation tick of episode E is LO..HI
//   --opt proof-watch-log=FILE     (default: standard output)
//   --opt proof-pokes=FILE         memory writes keyed on the game's own time: lines of
//                                  "episode tick frame address hexbytes", applied at the
//                                  first displayed frame at or after that frame of that
//                                  tick (frame counts the displayed frames of one tick as
//                                  rigcompare.py's controller replay does).  session.py
//                                  writes the file from the rig's run of the same script
//   --opt proof-dump=E:TICK:FILE[,E:TICK:FILE...]
//                                  write main memory at the first displayed frame of that
//                                  tick of episode E (an episode ends when the tick counter
//                                  goes back: tools/recomp/rigcompare.py, episodes_of)
//
// A captured state is the register context and all of memory.  Memory is kept as 4 KB
// pages in a store without duplicates (DIR/pages.bin); a state lists the pages that
// changed since the state before it (DIR/captures.bin).  tools/recomp/proof/realproof.py
// reads both and runs each state through the interpreter and through the translation.
#include "rt.h"
#include "proof.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <unordered_map>
#include <vector>

u32 g_proof_hits[PROOF_ENTRIES];
u8 g_proof_want[PROOF_ENTRIES];
u8 g_proof_slow = 1;                    // until the options have been read

static const u32 SIM_TICK = 0x44fdcc, LEVEL_NAME = 0x41b721, FRAME_HOOK = 0x19d8b0;
static const u32 PAGES = (RAM_SIZE >> 12) + 4;      // main memory and the scratchpad
static const u32 SCHEDULE[] = {1, 2, 5, 20, 100, 500, 2500, 12500, 62500, 312500};

static bool g_ready;
static u32 g_frame_hook = ~0u;
static u32 g_episode, g_last_tick;
static u8 g_per[PROOF_ENTRIES];         // states recorded so far

// ---- capture ------------------------------------------------------------------------------
static FILE* g_pages_file;
static FILE* g_cap_file;
static std::vector<u8> g_prev;          // memory as of the last state
static std::vector<u32> g_refs;         // page -> number in the store
struct PageKey { u64 h2; u32 ref; };
static std::unordered_multimap<u64, PageKey> g_store;
static u32 g_store_count;
static u64 g_captures;
static u32 g_per_function = 3;

static const u8* page_ptr(u32 page) {
    return page < (RAM_SIZE >> 12) ? g_ram + ((size_t)page << 12) : rta::scratchpad() + ((size_t)(page - (RAM_SIZE >> 12)) << 12);
}

static u32 store_page(const u8* p) {
    u64 h1 = 0xcbf29ce484222325ull, h2 = 0x9E3779B97F4A7C15ull;
    for (int i = 0; i < 512; i++) {
        u64 w;
        memcpy(&w, p + i * 8, 8);
        h1 = (h1 ^ w) * 0x100000001b3ull;
        h2 = ((h2 << 5) | (h2 >> 59)) ^ w;
        h2 *= 0xff51afd7ed558ccdull;
    }
    auto range = g_store.equal_range(h1);
    for (auto it = range.first; it != range.second; ++it)
        if (it->second.h2 == h2) return it->second.ref;
    fwrite(p, 1, 4096, g_pages_file);
    g_store.insert({h1, PageKey{h2, g_store_count}});
    return g_store_count++;
}

template <class T> static void put(FILE* f, T v) { fwrite(&v, sizeof(T), 1, f); }

static void capture(Ctx* c, u32 number) {
    put<u32>(g_cap_file, 0x50414350u);
    put<u32>(g_cap_file, number);
    put<u32>(g_cap_file, g_proof_addr[number]);
    put<u32>(g_cap_file, g_proof_hits[number]);
    put<u32>(g_cap_file, g_episode);
    put<u32>(g_cap_file, W(SIM_TICK));
    char level[16] = {0};
    memcpy(level, g_ram + LEVEL_NAME, 12);
    fwrite(level, 1, 16, g_cap_file);
    fwrite(c->r, 8, 32, g_cap_file);
    fwrite(c->rh, 8, 32, g_cap_file);
    put<u64>(g_cap_file, c->hi); put<u64>(g_cap_file, c->lo);
    put<u64>(g_cap_file, c->hi1); put<u64>(g_cap_file, c->lo1);
    put<u32>(g_cap_file, c->sa); put<u32>(g_cap_file, c->fcr31);
    fwrite(c->f, 4, 32, g_cap_file);
    put<u32>(g_cap_file, c->acc);
    std::vector<u32> changed;
    for (u32 page = 0; page < PAGES; page++) {
        const u8* now = page_ptr(page);
        u8* before = g_prev.data() + ((size_t)page << 12);
        if (memcmp(now, before, 4096) == 0) continue;
        memcpy(before, now, 4096);
        g_refs[page] = store_page(now);
        changed.push_back(page);
        changed.push_back(g_refs[page]);
    }
    put<u32>(g_cap_file, (u32)(changed.size() / 2));
    if (!changed.empty()) fwrite(changed.data(), 4, changed.size(), g_cap_file);
    g_captures++;
}

// ---- watch --------------------------------------------------------------------------------
static u32 g_watch_addr, g_watch_len;
static u32 g_watch_episode, g_watch_lo, g_watch_hi;
static bool g_watch_set, g_watch_armed;
static std::vector<u8> g_shadow;
static FILE* g_watch_log;
static const char* g_last_kind = "start";
static u32 g_last_where;
static u64 g_watch_events;

static void watch_check(const char* kind, u32 where) {
    if (memcmp(g_ram + g_watch_addr, g_shadow.data(), g_watch_len) != 0) {
        g_watch_events++;
        if (g_watch_events <= 20000) {
            fprintf(g_watch_log, "episode %u tick %u: changed between %s %x and %s %x (last call site %x):", g_episode, W(SIM_TICK),
                    g_last_kind, g_last_where, kind, where, g_site);
            unsigned shown = 0;
            for (u32 i = 0; i < g_watch_len; i++) {
                if (g_ram[g_watch_addr + i] == g_shadow[i]) continue;
                if (shown++ < 24) fprintf(g_watch_log, " +%x:%02x>%02x", i, g_shadow[i], g_ram[g_watch_addr + i]);
            }
            fprintf(g_watch_log, " (%u bytes)\n", shown);
        }
        memcpy(g_shadow.data(), g_ram + g_watch_addr, g_watch_len);
    }
    g_last_kind = kind;
    g_last_where = where;
}

// ---- dumps --------------------------------------------------------------------------------
struct Dump { u32 episode, tick; std::string path; bool done; };
static std::vector<Dump> g_dumps;

struct Poke { u32 episode, tick, frame, addr; std::vector<u8> bytes; };
static std::vector<Poke> g_pokes;
static size_t g_poke_next;
static u32 g_tick_frame;

static void per_frame() {
    u32 tick = W(SIM_TICK);
    if (tick < g_last_tick) g_episode++;
    g_tick_frame = tick == g_last_tick ? g_tick_frame + 1 : 0;
    g_last_tick = tick;
    while (g_poke_next < g_pokes.size()) {
        const Poke& p = g_pokes[g_poke_next];
        bool due = g_episode != p.episode ? g_episode > p.episode : tick != p.tick ? tick > p.tick : g_tick_frame >= p.frame;
        if (!due) break;
        if (p.addr < RAM_SIZE && p.bytes.size() <= RAM_SIZE - p.addr) memcpy(g_ram + p.addr, p.bytes.data(), p.bytes.size());
        if (g_episode != p.episode || tick != p.tick)
            printf("proof: poke for episode %u tick %u applied late, at episode %u tick %u\n", p.episode, p.tick, g_episode, tick);
        g_poke_next++;
    }
    for (Dump& d : g_dumps) {
        if (d.done || d.episode != g_episode || tick < d.tick) continue;
        d.done = true;
        FILE* f = fopen(d.path.c_str(), "wb");
        if (f) { fwrite(g_ram, 1, RAM_SIZE, f); fclose(f); }
        printf("proof: episode %u tick %u: memory %s %s\n", g_episode, tick, f ? "written to" : "NOT written to", d.path.c_str());
    }
    if (g_watch_set) {
        bool inside = g_episode == g_watch_episode && tick + 1 >= g_watch_lo && tick <= g_watch_hi;
        if (inside && !g_watch_armed) {
            memcpy(g_shadow.data(), g_ram + g_watch_addr, g_watch_len);
            g_last_kind = "frame";
            g_last_where = tick;
        }
        g_watch_armed = inside;
        g_proof_slow = inside ? 1 : 0;
    }
}

// ---- set-up -------------------------------------------------------------------------------
static void proof_finish();
static void (*g_chain)();

static void ready() {
    g_ready = true;
    g_proof_slow = 0;
    for (u32 n = 0; n < PROOF_ENTRIES; n++)
        if (g_proof_addr[n] == FRAME_HOOK) g_frame_hook = n;
    if (g_frame_hook != ~0u) g_proof_want[g_frame_hook] = 1;
    g_chain = rt_at_finish;
    rt_at_finish = proof_finish;
    if (const char* per = rt_option("proof-per")) g_per_function = (u32)atoi(per);
    if (const char* dir = rt_option("proof-capture")) {
        std::string base = dir;
        g_pages_file = fopen((base + "/pages.bin").c_str(), "wb");
        g_cap_file = fopen((base + "/captures.bin").c_str(), "wb");
        if (!g_pages_file || !g_cap_file) rt_die("proof: cannot write into %s", dir);
        setvbuf(g_pages_file, nullptr, _IOFBF, 1 << 20);
        g_prev.assign((size_t)PAGES << 12, 0);
        g_refs.assign(PAGES, 0);
        std::vector<u8> zero(4096, 0);
        store_page(zero.data());                    // page 0 of the store: zeroes
        std::vector<char> wanted(PROOF_ENTRIES, 0);
        if (const char* list = rt_option("proof-want")) {
            FILE* f = fopen(list, "r");
            if (!f) rt_die("proof: cannot read %s", list);
            std::unordered_map<u32, u32> by_addr;
            for (u32 n = 0; n < PROOF_ENTRIES; n++) by_addr[g_proof_addr[n]] = n;
            char line[256];
            while (fgets(line, sizeof line, f)) {
                char* end;
                u32 addr = (u32)strtoul(line, &end, 16);
                if (end == line) continue;
                auto it = by_addr.find(addr);
                if (it != by_addr.end()) wanted[it->second] = 1;
            }
            fclose(f);
        } else {
            wanted.assign(PROOF_ENTRIES, 1);
        }
        for (u32 n = 0; n < PROOF_ENTRIES; n++)
            if (wanted[n]) g_proof_want[n] = 1;
    }
    if (const char* watch = rt_option("proof-watch")) {
        if (sscanf(watch, "%x:%x", &g_watch_addr, &g_watch_len) != 2 || g_watch_addr + g_watch_len > RAM_SIZE)
            rt_die("proof: --opt proof-watch=ADDR:LEN (hex)");
        g_shadow.assign(g_watch_len, 0);
        g_watch_set = true;
        g_watch_hi = ~0u;
        if (const char* ticks = rt_option("proof-watch-ticks"))
            if (sscanf(ticks, "%u:%u:%u", &g_watch_episode, &g_watch_lo, &g_watch_hi) != 3)
                rt_die("proof: --opt proof-watch-ticks=EPISODE:LO:HI");
        const char* log = rt_option("proof-watch-log");
        g_watch_log = log ? fopen(log, "w") : stdout;
        if (!g_watch_log) rt_die("proof: cannot write %s", log);
    }
    if (const char* pokes = rt_option("proof-pokes")) {
        FILE* f = fopen(pokes, "r");
        if (!f) rt_die("proof: cannot read %s", pokes);
        char line[4096];
        while (fgets(line, sizeof line, f)) {
            Poke p;
            char hex[2048];
            if (sscanf(line, "%u %u %u %x %2047s", &p.episode, &p.tick, &p.frame, &p.addr, hex) != 5) continue;
            for (size_t i = 0; hex[i] && hex[i + 1]; i += 2) {
                unsigned byte;
                sscanf(hex + i, "%2x", &byte);
                p.bytes.push_back((u8)byte);
            }
            g_pokes.push_back(p);
        }
        fclose(f);
        printf("proof: %zu memory writes from %s\n", g_pokes.size(), pokes);
    }
    if (const char* dumps = rt_option("proof-dump")) {
        std::string text = dumps;
        size_t at = 0;
        while (at < text.size()) {
            size_t end = text.find(',', at);
            if (end == std::string::npos) end = text.size();
            std::string item = text.substr(at, end - at);
            Dump d;
            char path[1024];
            if (sscanf(item.c_str(), "%u:%u:%1023s", &d.episode, &d.tick, path) != 3) rt_die("proof: --opt proof-dump=E:TICK:FILE");
            d.path = path;
            d.done = false;
            g_dumps.push_back(d);
            at = end + 1;
        }
    }
}

void proof_enter(Ctx* c, u32 number) {
    if (!g_ready) ready();
    if (g_watch_armed) watch_check("entry of", g_proof_addr[number]);
    if (number == g_frame_hook) per_frame();
    if (g_cap_file && g_proof_want[number] && number != g_frame_hook) {
        u8 done = g_per[number];
        if (done >= g_per_function || done >= sizeof(SCHEDULE) / sizeof(SCHEDULE[0])) g_proof_want[number] = 0;
        else if (g_proof_hits[number] >= SCHEDULE[done]) {
            capture(c, number);
            g_per[number] = done + 1;
        }
    }
}

void proof_return(Ctx*, u32 site) {
    if (g_watch_armed) watch_check("return to", site);
}

static void proof_finish() {
    if (const char* path = rt_option("proof-hits")) {
        FILE* f = fopen(path, "w");
        if (f) {
            for (u32 n = 0; n < PROOF_ENTRIES; n++)
                if (g_proof_hits[n]) fprintf(f, "%08x\t%u\n", g_proof_addr[n], g_proof_hits[n]);
            fclose(f);
        }
    }
    u32 reached = 0;
    for (u32 n = 0; n < PROOF_ENTRIES; n++) reached += g_proof_hits[n] != 0;
    printf("proof: %u of %u entry points reached; %llu states recorded in %u pages; %llu watch events\n", reached, PROOF_ENTRIES,
           (unsigned long long)g_captures, g_store_count, (unsigned long long)g_watch_events);
    if (g_cap_file) fclose(g_cap_file);
    if (g_pages_file) fclose(g_pages_file);
    if (g_watch_log && g_watch_log != stdout) fclose(g_watch_log);
    if (g_chain) g_chain();
}
