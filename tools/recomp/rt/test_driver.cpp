// test_driver.cpp - runs translated functions on prepared inputs and reports what they did.
//
//   recomp_test <elf> <cases.bin> <results.bin>
//
// The other half is tools/recomp/difftest.py, which prepares the same inputs for the
// instruction interpreter (tools/ee_emu.py) and compares.  Built with -DRECOMP_TEST, which
// makes generated code count loop iterations and calls against a budget, route every call
// through rt_test_call (so calls can be recorded and stubbed exactly as the interpreter
// does) and mark the pages it writes.
//
// File formats (little endian) are described next to the code that writes them, in
// difftest.py.
#include "recomp.h"

#include <csetjmp>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#include <sys/mman.h>
#include <vector>

u8* g_ram;
u8 g_dirty[RAM_SIZE >> 12];
static u8* g_base;      // the ELF image, never modified
static u8* g_pre;       // memory as it was when the current case started
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

struct Stub { u32 addr, has_ret; u64 ret; };
static std::vector<Stub> g_stubs;
static bool g_stub_all;

u64 rt_load(u32 addr, unsigned) { stop(ST_FAULT, addr); return 0; }
void rt_store(u32 addr, unsigned, u64) { stop(ST_FAULT, addr); }
void rt_load128(u32 addr, u64*, u64*) { stop(ST_FAULT, addr); }
void rt_store128(u32 addr, u64, u64) { stop(ST_FAULT, addr); }
void rt_syscall(Ctx* c, u32) { c->r[2] = 0; }      // no kernel on either side of the test
void rt_break(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_trap(Ctx*, u32 pc, const char*) { stop(ST_TRAP, pc); }
void rt_unimpl(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_cop2(Ctx*, u32 pc, u32) { stop(ST_TRAP, pc); }
void rt_eret(Ctx*, u32 pc) { stop(ST_TRAP, pc); }
void rt_budget(Ctx*) { stop(ST_BUDGET, 0); }
// the interpreter keeps COP0 as a plain register file
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
    bool stubbed = g_stub_all;
    const Stub* stub = nullptr;
    for (const Stub& s : g_stubs)
        if (s.addr == target) { stub = &s; stubbed = true; break; }
    g_call_total++;
    if (g_calls.size() < MAX_CALLS) {
        CallRec rec;
        rec.site = site; rec.target = target; rec.stubbed = stubbed; rec.pad = 0;
        for (int i = 0; i < 8; i++) { rec.args[i] = c->r[4 + i]; rec.fargs[i] = c->f[12 + i]; }
        g_calls.push_back(rec);
    }
    if (!stubbed) return true;
    if (stub) { if (stub->has_ret) c->r[2] = stub->ret; }
    else c->r[2] = 0;
    return false;
}

static void on_signal(int sig) { stop(ST_SIGNAL, (u32)sig); }

static bool load_elf(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<u8> d(size);
    if (fread(d.data(), 1, size, f) != (size_t)size) { fclose(f); return false; }
    fclose(f);
    u32 phoff; u16 phentsize, phnum;
    memcpy(&phoff, &d[28], 4); memcpy(&phentsize, &d[42], 2); memcpy(&phnum, &d[44], 2);
    for (unsigned i = 0; i < phnum; i++) {
        u32 h[6];
        memcpy(h, &d[phoff + i * phentsize], 24);
        if (h[0] != 1) continue;
        if (h[2] + h[4] > RAM_SIZE) return false;
        memcpy(g_base + h[2], &d[h[1]], h[4]);
    }
    return true;
}

struct Reader {
    const u8* p; const u8* end;
    template <class T> T get() { T v; memcpy(&v, p, sizeof(T)); p += sizeof(T); return v; }
};

static void put(FILE* f, const void* p, size_t n) { fwrite(p, 1, n, f); }
template <class T> static void putv(FILE* f, T v) { fwrite(&v, sizeof(T), 1, f); }

static const char* g_argv[4];
static int g_rc;

static void* run_all(void*) {
    FILE* f = fopen(g_argv[2], "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", g_argv[2]); g_rc = 2; return nullptr; }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<u8> in(size);
    if (fread(in.data(), 1, size, f) != (size_t)size) { g_rc = 2; return nullptr; }
    fclose(f);
    FILE* out = fopen(g_argv[3], "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", g_argv[3]); g_rc = 2; return nullptr; }

    Reader rd{in.data(), in.data() + in.size()};
    u32 magic = rd.get<u32>(), count = rd.get<u32>();
    if (magic != 0x31544352) { fprintf(stderr, "bad case file\n"); g_rc = 2; return nullptr; }
    putv<u32>(out, 0x31525352);
    putv<u32>(out, count);

    std::vector<u32> patched;
    static Ctx ctx;
    for (u32 n = 0; n < count; n++) {
        Ctx* c = &ctx;
        memset(c, 0, sizeof(Ctx));
        u32 func = rd.get<u32>(), flags = rd.get<u32>();
        c->budget = rd.get<s64>();
        for (int i = 0; i < 32; i++) c->r[i] = rd.get<u64>();
        for (int i = 0; i < 32; i++) c->rh[i] = rd.get<u64>();
        c->hi = rd.get<u64>(); c->lo = rd.get<u64>(); c->hi1 = rd.get<u64>(); c->lo1 = rd.get<u64>();
        c->sa = rd.get<u32>(); c->fcr31 = rd.get<u32>();
        for (int i = 0; i < 32; i++) c->f[i] = rd.get<u32>();
        c->acc = rd.get<u32>();
        for (int i = 0; i < 32; i++) c->cop0[i] = rd.get<u32>();
        g_stub_all = flags & 1;
        g_stubs.clear();
        u32 nstubs = rd.get<u32>();
        for (u32 i = 0; i < nstubs; i++) {
            Stub s; s.addr = rd.get<u32>(); s.has_ret = rd.get<u32>(); s.ret = rd.get<u64>();
            g_stubs.push_back(s);
        }
        patched.clear();
        u32 npatch = rd.get<u32>();
        for (u32 i = 0; i < npatch; i++) {
            u32 addr = rd.get<u32>(), len = rd.get<u32>();
            if (addr <= RAM_SIZE && len <= RAM_SIZE - addr) {
                memcpy(g_ram + addr, rd.p, len);
                memcpy(g_pre + addr, rd.p, len);
                for (u32 page = addr >> 12; page <= (addr + len - 1) >> 12; page++) patched.push_back(page);
            }
            rd.p += (len + 3) & ~3u;
        }
        g_calls.clear();
        g_call_total = 0;
        g_status = ST_RETURN;
        g_info = 0;
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

        // memory that differs from the state the case started with, as runs of bytes
        long count_pos = ftell(out);
        putv<u32>(out, 0);
        u32 runs = 0;
        for (u32 page = 0; page < (RAM_SIZE >> 12); page++) {
            if (!g_dirty[page]) continue;
            u32 base = page << 12;
            if (memcmp(g_ram + base, g_pre + base, 4096) != 0) {
                u32 i = 0;
                while (i < 4096) {
                    if (g_ram[base + i] == g_pre[base + i]) { i++; continue; }
                    u32 j = i;
                    while (j < 4096 && g_ram[base + j] != g_pre[base + j]) j++;
                    putv<u32>(out, base + i);
                    putv<u32>(out, j - i);
                    put(out, g_ram + base + i, j - i);
                    u32 pad = (4 - ((j - i) & 3)) & 3, zero = 0;
                    put(out, &zero, pad);
                    runs++;
                    i = j;
                }
            }
            memcpy(g_ram + base, g_base + base, 4096);
            memcpy(g_pre + base, g_base + base, 4096);
            g_dirty[page] = 0;
        }
        for (u32 page : patched) {
            memcpy(g_ram + (page << 12), g_base + (page << 12), 4096);
            memcpy(g_pre + (page << 12), g_base + (page << 12), 4096);
        }
        long end_pos = ftell(out);
        fseek(out, count_pos, SEEK_SET);
        putv<u32>(out, runs);
        fseek(out, end_pos, SEEK_SET);
    }
    fclose(out);
    return nullptr;
}

int main(int argc, char** argv) {
    if (argc != 4) { fprintf(stderr, "usage: recomp_test <elf> <cases.bin> <results.bin>\n"); return 2; }
    for (int i = 0; i < 4; i++) g_argv[i] = argv[i];
    g_base = (u8*)calloc(RAM_SIZE + 4096, 1);
    g_ram = (u8*)malloc(RAM_SIZE + 4096);
    g_pre = (u8*)malloc(RAM_SIZE + 4096);
    if (!load_elf(argv[1])) { fprintf(stderr, "cannot load %s\n", argv[1]); return 2; }
    memcpy(g_ram, g_base, RAM_SIZE + 4096);
    memcpy(g_pre, g_base, RAM_SIZE + 4096);

    g_text_lo = 0xFFFFFFFFu; g_text_hi = 0;
    for (unsigned i = 0; i < g_recomp_entry_count; i++) {
        u32 a = g_recomp_entries[i].addr;
        if (a < g_text_lo) g_text_lo = a;
        if (a + 4 > g_text_hi) g_text_hi = a + 4;
    }
    g_table = (RecompFn*)calloc((g_text_hi - g_text_lo) >> 2, sizeof(RecompFn));
    for (unsigned i = 0; i < g_recomp_entry_count; i++)
        g_table[(g_recomp_entries[i].addr - g_text_lo) >> 2] = g_recomp_entries[i].fn;

    // signals (a host stack overflow from runaway recursion, mostly) end the case
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
