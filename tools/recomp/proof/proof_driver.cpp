// proof_driver.cpp - runs translated functions from machine states recorded in the running
// game (proof_rt.cpp) and reports what they did.
//
//   proof_driver <captures dir> <jobs.bin> <results.bin>
//
// The other half is tools/recomp/proof/realproof.py, which runs the same states through
// the instruction interpreter (tools/ee_emu.py) and compares.  This is rt/test_driver.cpp
// with another source of inputs: instead of a prepared register set and a few patched
// pages, a job names a recorded state - every register and all 32 MB of memory as they
// were when the game entered the function - and says how calls are to be treated.
// Built like the test driver (-DRECOMP_TEST -DFPU_PS2) from the plain translation.
//
// Memory outside main memory is, on both sides of the comparison:
//   the mirrors of main memory (0x20000000, 0x30000000, 0x80000000, 0xa0000000): main memory;
//   the scratchpad (0x70000000, 16 KB): as recorded;
//   anything else (hardware registers): plain memory, zero when the function starts.
// A system call returns 0 on both sides, as in the test driver.
//
// jobs.bin:  u32 'PJOB', u32 count; per job u32 state number, u32 flags (1 = every call is
//            replaced by "return 0"), s64 budget.  Jobs are in ascending state order.
// results:   the test driver's format (difftest.py, read_results), with the runs of changed
//            bytes carrying full 32-bit addresses.
#include "recomp.h"

#include <csetjmp>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <pthread.h>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <vector>

u8* g_ram;
u8 g_dirty[RAM_SIZE >> 12];
static u8* g_pre;
static u8 g_spr[0x4000], g_spr_pre[0x4000];
static bool g_spr_dirty;
static std::map<u32, std::vector<u8>> g_other;      // page address -> 4 KB, outside everything else
static RecompFn* g_table;
static u32 g_text_lo, g_text_hi;

enum Status { ST_RETURN = 0, ST_FAULT = 1, ST_BUDGET = 2, ST_TRAP = 3, ST_SIGNAL = 4, ST_BADCALL = 5 };

static sigjmp_buf g_jmp;
static u32 g_status, g_info;

static void stop(u32 status, u32 info) {
    g_status = status;
    g_info = info;
    siglongjmp(g_jmp, 1);
}

struct CallRec { u32 site, target, stubbed, pad; u64 args[8]; u32 fargs[8]; };
static std::vector<CallRec> g_calls;
static u32 g_call_total;
static const u32 MAX_CALLS = 512;
static bool g_stub_all;

// where an address outside main memory lives; marks what it touches as written when asked
static u8* outside(u32 addr, unsigned size, bool write) {
    // the mirrors as rt/runtime.cpp folds them (special_memory)
    u32 top = addr & 0xF0000000u;
    u32 low = (top == 0x20000000u || top == 0x30000000u) ? (addr & 0x0FFFFFFFu) : (addr & 0x1FFFFFFFu);
    if ((top == 0x20000000u || top == 0x30000000u || top == 0x80000000u || top == 0xA0000000u) &&
        low < RAM_SIZE && size <= RAM_SIZE - low) {
        if (write) { g_dirty[low >> 12] = 1; g_dirty[(low + size - 1) >> 12] = 1; }
        return g_ram + low;
    }
    if (addr >= 0x70000000u && addr - 0x70000000u <= 0x4000u - size) {
        if (write) g_spr_dirty = true;
        return g_spr + (addr - 0x70000000u);
    }
    if ((addr & 0xFFF) + size > 4096) stop(ST_FAULT, addr);         // straddles two pages of nothing
    std::vector<u8>& page = g_other[addr & ~0xFFFu];
    if (page.empty()) page.assign(4096 + 1, 0);                     // last byte: written
    if (write) page[4096] = 1;
    return page.data() + (addr & 0xFFF);
}

u64 rt_load(u32 addr, unsigned size) {
    u64 v = 0;
    memcpy(&v, outside(addr, size, false), size);
    return v;
}
void rt_store(u32 addr, unsigned size, u64 value) { memcpy(outside(addr, size, true), &value, size); }
void rt_load128(u32 addr, u64* lo, u64* hi) {
    u8* p = outside(addr, 16, false);
    memcpy(lo, p, 8); memcpy(hi, p + 8, 8);
}
void rt_store128(u32 addr, u64 lo, u64 hi) {
    u8* p = outside(addr, 16, true);
    memcpy(p, &lo, 8); memcpy(p + 8, &hi, 8);
}
void rt_syscall(Ctx* c, u32) { c->r[2] = 0; }
void rt_break(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_trap(Ctx*, u32 pc, const char*) { stop(ST_TRAP, pc); }
void rt_unimpl(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_cop2(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_eret(Ctx*, u32 pc) { stop(ST_TRAP, pc); }
void rt_budget(Ctx*) { stop(ST_BUDGET, 0); }
u32 rt_mfc0(Ctx* c, u32, unsigned reg) { return c->cop0[reg]; }
void rt_mtc0(Ctx* c, u32, unsigned reg, u32 value) { c->cop0[reg] = value; }

void rt_call(Ctx* c, u32 target) {
    if (target >= g_text_lo && target < g_text_hi && !(target & 3)) {
        RecompFn fn = g_table[(target - g_text_lo) >> 2];
        if (fn) { fn(c); return; }
    }
    stop(ST_BADCALL, target);
}

bool rt_test_call(Ctx* c, u32 site, u32 target) {
    if (--c->budget < 0) rt_budget(c);
    g_call_total++;
    if (g_calls.size() < MAX_CALLS) {
        CallRec rec;
        rec.site = site; rec.target = target; rec.stubbed = g_stub_all; rec.pad = 0;
        for (int i = 0; i < 8; i++) { rec.args[i] = c->r[4 + i]; rec.fargs[i] = c->f[12 + i]; }
        g_calls.push_back(rec);
    }
    if (!g_stub_all) return true;
    c->r[2] = 0;
    return false;
}

static void on_signal(int sig) { stop(ST_SIGNAL, (u32)sig); }

template <class T> static void putv(FILE* f, T v) { fwrite(&v, sizeof(T), 1, f); }
static void put(FILE* f, const void* p, size_t n) { fwrite(p, 1, n, f); }

static u32 put_runs(FILE* out, const u8* now, const u8* before, u32 base, u32 length) {
    u32 runs = 0, i = 0;
    while (i < length) {
        if (now[i] == before[i]) { i++; continue; }
        u32 j = i;
        while (j < length && now[j] != before[j]) j++;
        putv<u32>(out, base + i);
        putv<u32>(out, j - i);
        put(out, now + i, j - i);
        u32 pad = (4 - ((j - i) & 3)) & 3, zero = 0;
        put(out, &zero, pad);
        runs++;
        i = j;
    }
    return runs;
}

static const char* g_argv[4];
static int g_rc;
static const u32 PAGES = (RAM_SIZE >> 12) + 4;

struct State { u32 addr; Ctx ctx; };

static void* run_all(void*) {
    std::string dir = g_argv[1];
    int pages_fd = open((dir + "/pages.bin").c_str(), O_RDONLY);
    struct stat st;
    if (pages_fd < 0 || fstat(pages_fd, &st) != 0) { fprintf(stderr, "cannot read %s/pages.bin\n", g_argv[1]); g_rc = 2; return nullptr; }
    const u8* store = (const u8*)mmap(nullptr, st.st_size, PROT_READ, MAP_PRIVATE, pages_fd, 0);
    FILE* caps = fopen((dir + "/captures.bin").c_str(), "rb");
    FILE* jobs = fopen(g_argv[2], "rb");
    FILE* out = fopen(g_argv[3], "wb");
    if (store == MAP_FAILED || !caps || !jobs || !out) { fprintf(stderr, "cannot open the inputs\n"); g_rc = 2; return nullptr; }
    u32 magic = 0, count = 0;
    if (fread(&magic, 4, 1, jobs) != 1 || fread(&count, 4, 1, jobs) != 1 || magic != 0x424F4A50u) { fprintf(stderr, "bad job file\n"); g_rc = 2; return nullptr; }
    putv<u32>(out, 0x31525352);
    putv<u32>(out, count);

    std::vector<u32> want(PAGES, 0), have(PAGES, ~0u);     // page -> number in the store: recorded state / in g_ram now
    long state_number = -1;
    State state;
    static Ctx ctx;
    for (u32 n = 0; n < count; n++) {
        u32 number, flags; s64 budget;
        if (fread(&number, 4, 1, jobs) != 1 || fread(&flags, 4, 1, jobs) != 1 || fread(&budget, 8, 1, jobs) != 1) { g_rc = 2; return nullptr; }
        while (state_number < (long)number) {               // read on to the wanted state
            u32 head[6]; char level[16];
            if (fread(head, 4, 6, caps) != 6 || head[0] != 0x50414350u) { fprintf(stderr, "state %u is not in the file\n", number); g_rc = 2; return nullptr; }
            fread(level, 1, 16, caps);
            memset(&state.ctx, 0, sizeof(Ctx));
            state.addr = head[2];
            Ctx* s = &state.ctx;
            fread(s->r, 8, 32, caps); fread(s->rh, 8, 32, caps);
            fread(&s->hi, 8, 1, caps); fread(&s->lo, 8, 1, caps); fread(&s->hi1, 8, 1, caps); fread(&s->lo1, 8, 1, caps);
            fread(&s->sa, 4, 1, caps); fread(&s->fcr31, 4, 1, caps);
            fread(s->f, 4, 32, caps); fread(&s->acc, 4, 1, caps);
            u32 changed = 0;
            fread(&changed, 4, 1, caps);
            for (u32 i = 0; i < changed; i++) {
                u32 pair[2];
                if (fread(pair, 4, 2, caps) != 2) { g_rc = 2; return nullptr; }
                if (pair[0] < PAGES) want[pair[0]] = pair[1];
            }
            state_number++;
        }
        for (u32 page = 0; page < PAGES; page++) {
            bool ram = page < (RAM_SIZE >> 12);
            if (have[page] == want[page]) continue;
            const u8* src = store + (size_t)want[page] * 4096;
            if ((size_t)(want[page] + 1) * 4096 > (size_t)st.st_size) { fprintf(stderr, "page store too short\n"); g_rc = 2; return nullptr; }
            if (ram) { memcpy(g_ram + ((size_t)page << 12), src, 4096); memcpy(g_pre + ((size_t)page << 12), src, 4096); }
            else { u32 o = (page - (RAM_SIZE >> 12)) << 12; memcpy(g_spr + o, src, 4096); memcpy(g_spr_pre + o, src, 4096); }
            have[page] = want[page];
        }
        Ctx* c = &ctx;
        *c = state.ctx;
        c->budget = budget;
        c->r[31] = 0xFF0;                           // the interpreter's return address
        c->fcr31 = (c->fcr31 & 0x00800000u) | 0x01000001u;
        g_stub_all = flags & 1;
        g_calls.clear();
        g_call_total = 0;
        g_status = ST_RETURN;
        g_info = 0;
        g_spr_dirty = false;
        g_other.clear();
        u32 func = state.addr;
        if (sigsetjmp(g_jmp, 1) == 0) {
            if (func >= g_text_lo && func < g_text_hi && !(func & 3) && g_table[(func - g_text_lo) >> 2])
                g_table[(func - g_text_lo) >> 2](c);
            else { g_status = ST_BADCALL; g_info = func; }
        }
        putv<u32>(out, g_status);
        putv<u32>(out, g_info);
        put(out, c->r, sizeof(c->r));
        put(out, c->rh, sizeof(c->rh));
        putv<u64>(out, c->hi); putv<u64>(out, c->lo); putv<u64>(out, c->hi1); putv<u64>(out, c->lo1);
        putv<u32>(out, c->sa); putv<u32>(out, c->fcr31);
        put(out, c->f, sizeof(c->f));
        putv<u32>(out, c->acc);
        putv<u32>(out, g_call_total);
        putv<u32>(out, (u32)g_calls.size());
        if (!g_calls.empty()) put(out, g_calls.data(), g_calls.size() * sizeof(CallRec));
        long count_pos = ftell(out);
        putv<u32>(out, 0);
        u32 runs = 0;
        for (u32 page = 0; page < (RAM_SIZE >> 12); page++) {
            if (!g_dirty[page]) continue;
            u32 base = page << 12;
            runs += put_runs(out, g_ram + base, g_pre + base, base, 4096);
            memcpy(g_ram + base, g_pre + base, 4096);
            g_dirty[page] = 0;
        }
        if (g_spr_dirty) {
            runs += put_runs(out, g_spr, g_spr_pre, 0x70000000u, 0x4000);
            memcpy(g_spr, g_spr_pre, 0x4000);
        }
        static const u8 zeroes[4096] = {0};
        for (auto& kv : g_other)
            if (kv.second[4096]) runs += put_runs(out, kv.second.data(), zeroes, kv.first, 4096);
        long end_pos = ftell(out);
        fseek(out, count_pos, SEEK_SET);
        putv<u32>(out, runs);
        fseek(out, end_pos, SEEK_SET);
    }
    fclose(out);
    return nullptr;
}

int main(int argc, char** argv) {
    if (argc != 4) { fprintf(stderr, "usage: proof_driver <captures dir> <jobs.bin> <results.bin>\n"); return 2; }
    for (int i = 0; i < 4; i++) g_argv[i] = argv[i];
    g_ram = (u8*)calloc(RAM_SIZE + 4096, 1);
    g_pre = (u8*)calloc(RAM_SIZE + 4096, 1);
    g_text_lo = 0xFFFFFFFFu; g_text_hi = 0;
    for (unsigned i = 0; i < g_recomp_entry_count; i++) {
        u32 a = g_recomp_entries[i].addr;
        if (a < g_text_lo) g_text_lo = a;
        if (a + 4 > g_text_hi) g_text_hi = a + 4;
    }
    g_table = (RecompFn*)calloc((g_text_hi - g_text_lo) >> 2, sizeof(RecompFn));
    for (unsigned i = 0; i < g_recomp_entry_count; i++)
        g_table[(g_recomp_entries[i].addr - g_text_lo) >> 2] = g_recomp_entries[i].fn;
    stack_t alt;
    alt.ss_sp = malloc(1 << 16); alt.ss_size = 1 << 16; alt.ss_flags = 0;
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = on_signal;
    sa.sa_flags = SA_ONSTACK | SA_NODEFER;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, (size_t)1 << 30);
    pthread_t thread;
    struct Boot { static void* run(void* p) {
        sigaltstack((stack_t*)p, nullptr);
        return run_all(nullptr);
    } };
    sigaction(SIGSEGV, &sa, nullptr);
    sigaction(SIGBUS, &sa, nullptr);
    sigaction(SIGFPE, &sa, nullptr);
    sigaction(SIGILL, &sa, nullptr);
    if (pthread_create(&thread, &attr, Boot::run, &alt) != 0) { fprintf(stderr, "no thread\n"); return 2; }
    pthread_join(thread, nullptr);
    return g_rc;
}
