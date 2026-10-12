// runtime.cpp - the machine under the translated game.
//
//   rta_native boot   --elf SLUS_209.73 --disc <image.iso> [--card <dir>] [--script F] ...
//   rta_native resume --ram <image> [--spr <image>] --regs <file> --entry <hex> ...
//   (every option: rta::run() at the end of this file)
//
// What is here: guest memory (32 MB, scratchpad, vector-unit memories, the mirrors), a
// virtual clock, the hardware registers the game touches (timers, interrupt controller,
// DMA controller, GS privileged registers), a kernel (threads on host threads with one
// running at a time, semaphores, interrupt and DMA handlers, alarms, vertical blank),
// vector unit 0 (rt/vu0.h).  The I/O processor's services are in iop.cpp and
// sound_null.cpp, scripted input in script.cpp.  What leaves the machine - graphics
// data, sound, network, controller - goes through the interfaces of iface.h; with none
// attached the machine runs headless and the graphics data is walked only for the
// events that feed back into the game.
//
// The kernel keeps its tables IN GUEST MEMORY, in the layout the Play! emulator's
// high-level kernel uses (thread table at 0x11000, semaphores at 0xe000, interrupt
// handlers at 0xa000, DMA handlers at 0xc000, state block at 0x4000; structure layouts
// read in Play!'s PS2OS.h).  That choice is what makes "resume" possible: a memory image
// written by the headless rig (tools/rig) carries the kernel's state with it, so the
// translated game can be started in the middle of a session the original was running.
#include "rt.h"
#include "host.h"
#include "funcs.h"
#include "vu0.h"

#include <cfenv>
#if defined(__x86_64__) || defined(_M_X64)
#include <pmmintrin.h>
#include <xmmintrin.h>
#endif
#include <condition_variable>
#include <cstdarg>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>
#include <chrono>

u8* g_ram;
u32 g_site;
static u8 g_spr[0x4000];
static u8 g_vu1micro[0x4000], g_vu1mem[0x4000];
static Vu0 g_vu0;
static RecompFn* g_table;
static u32 g_text_lo, g_text_hi;
bool g_rt_verbose = false;
rta::Hooks g_hooks;
void (*rt_at_finish)() = nullptr;
static std::vector<std::string> g_boot_args;        // --arg: the arguments of the game's main()
static void final_report();

[[noreturn]] void rt_die(const char* format, ...) {
    va_list args;
    va_start(args, format);
    fprintf(stderr, "rta_native: ");
    vfprintf(stderr, format, args);
    fprintf(stderr, " (last call site 0x%x)\n", g_site);
    va_end(args);
    host::quit(3);
}

static int g_trace_left = 0;
#define TRACE(...) do { if (g_trace_left > 0) { g_trace_left--; fprintf(stderr, __VA_ARGS__); } } while (0)
static std::map<std::string, u64> g_counts;       // things the game asked the platform for
void rt_note(const std::string& what) { g_counts[what]++; }
std::string rt_fmt(const char* format, ...) {
    char buffer[512];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    return buffer;
}


// ---------------------------------------------------------------------------------------
// Virtual clock.  One "unit" is a call or a backward branch in translated code.
// ---------------------------------------------------------------------------------------
static const s64 POLL_UNITS = 20000;
static const u64 CYCLES_PER_UNIT = 4;
static const u64 VBLANK_PERIOD = 4920115;         // CPU cycles per field at 59.94 Hz
static const u64 VBLANK_LENGTH = VBLANK_PERIOD * 22 / 262;
static u64 g_cycles;                              // advanced at polls and when idle
static u64 g_units;                               // total units executed
static u64 g_next_vblank_start = VBLANK_PERIOD, g_next_vblank_end = VBLANK_PERIOD + VBLANK_LENGTH;
static u64 g_fields;

static u64 now(const Ctx* c) {
    if (!c || c->budget > POLL_UNITS) return g_cycles;      // no thread, or the interrupt context
    return g_cycles + (u64)(POLL_UNITS - (c->budget < 0 ? 0 : c->budget)) * CYCLES_PER_UNIT;
}

// ---------------------------------------------------------------------------------------
// Kernel tables in guest memory (Play! layout)
// ---------------------------------------------------------------------------------------
enum { ST_BASE = 0x4000, INTC_BASE = 0xA000, DMAC_BASE = 0xC000, SEMA_BASE = 0xE000, THREAD_BASE = 0x11000,
       KSTACK_TOP = 0x30000 };
enum { ST_IDLE = 0x10, ST_CURRENT = 0x14, ST_VSYNC1 = 0x18, ST_VSYNC2 = 0x1C, ST_THREADQ = 0x20,
       ST_INTCQ = 0x24, ST_DMACQ = 0x28 };
enum { T_VALID = 0, T_NEXT = 4, T_STATUS = 8, T_CONTEXT = 12, T_STACKBASE = 16, T_HEAPBASE = 20, T_PROC = 24,
       T_EPC = 28, T_GP = 32, T_INITPRI = 36, T_PRI = 40, T_SEMA = 44, T_WAKEUPS = 48, T_STACKSIZE = 52, T_SIZE = 56 };
enum { S_VALID = 0, S_COUNT = 4, S_MAX = 8, S_WAITERS = 12, S_WAITNEXT = 16, S_OPTION = 20, S_SIZE = 24 };
enum { H_VALID = 0, H_NEXT = 4, H_CAUSE = 8, H_ADDRESS = 12, H_ARG = 16, H_GP = 20, H_SIZE = 24 };
enum { TH_RUNNING = 1, TH_SLEEPING = 2, TH_WAITING = 3, TH_SUSPENDED = 4, TH_SUSPENDED_WAITING = 5,
       TH_SUSPENDED_SLEEPING = 6, TH_ZOMBIE = 7 };
static const u32 MAX_THREAD = 256, MAX_SEMA = 256, MAX_HANDLER = 128;

static u32 thr(u32 id) { return THREAD_BASE + (id - 1) * T_SIZE; }
static u32 sem(u32 id) { return SEMA_BASE + id * S_SIZE; }
static bool thr_ok(u32 id) { return id >= 1 && id <= MAX_THREAD && W(thr(id) + T_VALID); }
static bool sem_ok(u32 id) { return id < MAX_SEMA && W(sem(id) + S_VALID); }

struct ThreadKill {};
struct GThread {
    u32 id = 0;
    Ctx ctx;
    std::thread host;
    std::condition_variable cv;
    bool kill = false, finished = false;
    u32 entry = 0;
    u32 site = 0;                                 // last call site when it last gave up the processor
};
static std::mutex g_big;
static std::map<u32, GThread*> g_threads;
static GThread* g_cur;
static thread_local GThread* t_self;
static std::set<u32> g_foreign;                   // threads of a resumed image that cannot run here
static bool g_in_irq;
static Ctx g_irq_ctx;
static u32 g_intc_stat, g_intc_mask, g_dmac_stat, g_dmac_pending, g_dmac_ctrl = 1;
static u32 g_gs_csr = 0x4000, g_gs_imr = 0xFF00;
static std::map<u32, u32> g_hw;
static u64 g_frames_wanted = ~0ull;
static u64 g_dma_qwords[10], g_dma_starts[10], g_gs_finish, g_nothing_writes;

static void link_thread(u32 id) {       // into the schedule queue, after equal priorities
    u32 pri = W(thr(id) + T_PRI);
    u32 prev_slot = ST_BASE + ST_THREADQ;
    for (u32 cur = W(prev_slot); cur; cur = W(prev_slot)) {
        if (W(thr(cur) + T_PRI) > pri) break;
        prev_slot = thr(cur) + T_NEXT;
    }
    W(thr(id) + T_NEXT) = W(prev_slot);
    W(prev_slot) = id;
}
static void unlink_thread(u32 id) {
    u32 prev_slot = ST_BASE + ST_THREADQ;
    for (u32 cur = W(prev_slot); cur; cur = W(prev_slot)) {
        if (cur == id) { W(prev_slot) = W(thr(id) + T_NEXT); W(thr(id) + T_NEXT) = 0; return; }
        prev_slot = thr(cur) + T_NEXT;
    }
}
static u32 pick_thread() {
    for (u32 cur = W(ST_BASE + ST_THREADQ); cur; cur = W(thr(cur) + T_NEXT)) {
        if (cur == W(ST_BASE + ST_IDLE)) continue;
        if (W(thr(cur) + T_STATUS) != TH_RUNNING) continue;
        if (g_foreign.count(cur)) continue;
        return cur;
    }
    return 0;
}

static void call_guest(Ctx* c, u32 target) { rt_call(c, target); }

// ---- interrupts ------------------------------------------------------------------------
static void run_handlers(u32 queue_slot, u32 base, u32 cause) {
    bool was = g_in_irq;
    g_in_irq = true;
    u32 saved_site = g_site;
    for (u32 id = W(ST_BASE + queue_slot); id; ) {
        u32 h = base + (id - 1) * H_SIZE;
        u32 next = W(h + H_NEXT);
        if (W(h + H_VALID) && W(h + H_CAUSE) == cause) {
            Ctx* c = &g_irq_ctx;
            c->r[29] = KSTACK_TOP - 0x100;
            c->r[4] = cause;
            c->r[5] = SX32(W(h + H_ARG));
            c->r[28] = SX32(W(h + H_GP));
            c->r[31] = 0;
            c->budget = 1 << 30;
            c->cop0[12] = 0x70030C12;           // interrupts off while a handler runs
            rt_note(rt_fmt("interrupt handler 0x%x for %s %u", W(h + H_ADDRESS), base == INTC_BASE ? "INTC" : "DMAC", cause));
            TRACE("  irq %s %u -> handler 0x%x\n", base == INTC_BASE ? "INTC" : "DMAC", cause, W(h + H_ADDRESS));
            call_guest(c, W(h + H_ADDRESS));
            if ((s32)c->r[2] < 0) break;
        }
        id = next;
    }
    g_site = saved_site;
    g_in_irq = was;
}

// The vertical-blank interrupt is taken a moment after its status bit is raised, not at
// once.  Sony's sceGsSyncV (0x34fde0 -> 0x352e70), which the game calls while it has a
// blank handler of its own installed, clears the bit and then polls for it with
// interrupts on: it only ever sees the bit if the CPU gets to run between the hardware
// raising it and the kernel acknowledging it.  The Play! emulator gives it that window
// (interrupts are looked at after the next slice of code), and so does this.
static const u64 VBLANK_HOLD = 4800;
static u64 g_vblank_hold;
static u32 deliverable() {
    u32 pending = g_intc_stat & g_intc_mask;
    if ((pending & 4) && now(t_self && !g_in_irq ? &t_self->ctx : nullptr) < g_vblank_hold) pending &= ~4u;
    return pending;
}

static void deliver_interrupts() {
    if (g_in_irq) return;
    for (int round = 0; round < 100000 && (g_dmac_pending || deliverable()); round++) {
        if (g_dmac_pending) {
            u32 ch = __builtin_ctz(g_dmac_pending);
            g_dmac_pending &= ~(1u << ch);
            run_handlers(ST_DMACQ, DMAC_BASE, ch);
            g_dmac_stat &= ~(1u << ch);
            continue;
        }
        u32 line = __builtin_ctz(deliverable());
        g_intc_stat &= ~(1u << line);
        run_handlers(ST_INTCQ, INTC_BASE, line);
    }
}

static u32 g_gp;                                  // the executable's global pointer
struct Timer { u32 mode = 0, comp = 0, hold = 0; u64 base_cycles = 0; u32 base_count = 0; };
static Timer g_timers[4];
static u64 timer_divisor(const Timer& t) {
    static const u64 divisor[4] = {2, 32, 512, 18740};          // CPU cycles per count
    return divisor[t.mode & 3];
}
// Carry timer n forward to time `t`: count, flags, interrupts.
static void timer_sync(int n, u64 t) {
    Timer& tm = g_timers[n];
    if (!(tm.mode & 0x80)) { if (t > tm.base_cycles) tm.base_cycles = t; return; }
    if (t <= tm.base_cycles) return;
    u64 div = timer_divisor(tm);
    u64 ticks = (t - tm.base_cycles) / div;
    if (!ticks) return;
    tm.base_cycles += ticks * div;
    u64 count = tm.base_count & 0xFFFF;
    u32 comp = tm.comp & 0xFFFF;
    while (ticks) {
        u64 to_comp = comp > count ? comp - count : ~0ull;
        u64 to_wrap = 0x10000 - count;
        u64 step = ticks < to_wrap ? ticks : to_wrap;
        if (to_comp < step) step = to_comp;
        count += step;
        ticks -= step;
        bool match = step == to_comp;
        if (count == 0x10000) {
            count = 0;
            if ((tm.mode & 0x200) && !(tm.mode & 0x800)) { tm.mode |= 0x800; g_intc_stat |= 1u << (9 + n); }
            if (comp == 0) match = true;
        }
        if (match) {
            if ((tm.mode & 0x100) && !(tm.mode & 0x400)) { tm.mode |= 0x400; g_intc_stat |= 1u << (9 + n); }
            if (tm.mode & 0x40) count = 0;
        }
    }
    tm.base_count = (u32)count;
}
// When the next timer interrupt can happen (for the idle machine to wake up at).
static u64 next_timer() {
    u64 best = ~0ull;
    for (int n = 0; n < 4; n++) {
        Timer& tm = g_timers[n];
        if (!(tm.mode & 0x80)) continue;
        u64 count = tm.base_count & 0xFFFF, ticks = ~0ull;
        if ((tm.mode & 0x100) && !(tm.mode & 0x400)) { u64 d = ((tm.comp & 0xFFFF) - count) & 0xFFFF; ticks = d ? d : 0x10000; }
        if ((tm.mode & 0x200) && !(tm.mode & 0x800) && 0x10000 - count < ticks) ticks = 0x10000 - count;
        if (ticks == ~0ull) continue;
        u64 at = tm.base_cycles + ticks * timer_divisor(tm);
        if (at < best) best = at;
    }
    return best;
}
struct Alarm { bool active; u64 due; u32 callback, arg; };
static Alarm g_alarms[16];
static u64 next_alarm() {
    u64 best = ~0ull;
    for (auto& a : g_alarms) if (a.active && a.due < best) best = a.due;
    return best;
}
static void fire_alarms(u64 t) {
    if (g_in_irq) return;
    for (u32 k = 0; k < 16; k++) {
        Alarm& a = g_alarms[k];
        if (!a.active || a.due > t) continue;
        a.active = false;
        bool was = g_in_irq;
        g_in_irq = true;
        u32 saved_site = g_site;
        Ctx* c = &g_irq_ctx;
        c->r[29] = KSTACK_TOP - 0x100;
        c->r[4] = k + 1; c->r[5] = (u32)(t / 18740) & 0xFFFF; c->r[6] = SX32(a.arg);
        c->r[28] = SX32(g_gp);
        c->r[31] = 0;
        c->budget = (s64)1 << 30;
        c->cop0[12] = 0x70030C12;
        rt_note(rt_fmt("alarm callback 0x%x", a.callback));
        call_guest(c, a.callback);
        g_site = saved_site;
        g_in_irq = was;
    }
}

// Things that happen later on the virtual clock: answers of the I/O processor, the end
// of a wait.  They run where an interrupt handler would.
struct Later { u64 due, order; std::function<void()> fn; };
static std::vector<Later> g_later;
static u64 g_later_order;
u64 rt_cycles() { return now(t_self ? &t_self->ctx : nullptr); }
u64 rt_fields() { return g_fields; }
void rt_after(u64 delay, std::function<void()> fn) { g_later.push_back({rt_cycles() + delay, g_later_order++, std::move(fn)}); }
static u64 next_later() {
    u64 best = ~0ull;
    for (auto& l : g_later) if (l.due < best) best = l.due;
    return best;
}
static void fire_later(u64 t) {
    if (g_in_irq) return;
    for (;;) {
        size_t pick = g_later.size();
        for (size_t i = 0; i < g_later.size(); i++)
            if (g_later[i].due <= t && (pick == g_later.size() || g_later[i].due < g_later[pick].due
                                        || (g_later[i].due == g_later[pick].due && g_later[i].order < g_later[pick].order))) pick = i;
        if (pick == g_later.size()) return;
        std::function<void()> fn = std::move(g_later[pick].fn);
        g_later.erase(g_later.begin() + pick);
        g_in_irq = true;
        fn();
        g_in_irq = false;
    }
}
void rt_call_handler(u32 address, u32 a0, u32 a1) {
    bool was = g_in_irq;
    g_in_irq = true;
    u32 saved_site = g_site;
    Ctx* c = &g_irq_ctx;
    c->r[29] = KSTACK_TOP - 0x100;
    c->r[4] = SX32(a0); c->r[5] = SX32(a1);
    c->r[28] = SX32(g_gp);
    c->r[31] = 0;
    c->budget = (s64)1 << 30;
    c->cop0[12] = 0x70030C12;
    call_guest(c, address);
    g_site = saved_site;
    g_in_irq = was;
}

static void on_vblank();
// What the hardware does by itself goes on whether or not the CPU accepts interrupts
// (the status bits are raised; code that polls them with interrupts off sees them).
// What needs the CPU - alarm callbacks, completions - waits until it accepts them.
static void fire_due_events(u64 t, bool accepting = true) {
    if (accepting) {
        fire_alarms(t);
        fire_later(t);
    }
    for (int n = 0; n < 4; n++) timer_sync(n, t);
    while (t >= g_next_vblank_start || t >= g_next_vblank_end) {
        if (g_next_vblank_start <= g_next_vblank_end) {
            g_next_vblank_start += VBLANK_PERIOD;
            g_fields++;
            g_gs_csr |= 8;                      // VSINT
            g_gs_csr ^= 0x2000;                 // FIELD
            if (W(ST_BASE + ST_VSYNC1)) W(W(ST_BASE + ST_VSYNC1) & 0x1FFFFFF) = 1;
            if (W(ST_BASE + ST_VSYNC2)) W(W(ST_BASE + ST_VSYNC2) & 0x1FFFFFF) = (g_gs_csr >> 13) & 1;
            g_intc_stat |= 1u << 2;
            g_vblank_hold = t + VBLANK_HOLD;
            on_vblank();
        } else {
            g_next_vblank_end += VBLANK_PERIOD;
            g_intc_stat |= 1u << 3;
        }
    }
}

// ---- scheduling ------------------------------------------------------------------------
static void wait_for_baton(std::unique_lock<std::mutex>& lock, GThread* self) {
    self->cv.wait(lock, [&] { return g_cur == self; });
    if (self->kill) throw ThreadKill();
}

// The current guest thread reached a point where another may run.  Returns when this
// thread is the one to run.  `gone`: the caller's thread no longer exists (do not wait).
static void reschedule(std::unique_lock<std::mutex>& lock, GThread* self, Ctx* c, bool gone = false) {
    if (c && !gone && c->budget <= POLL_UNITS) {            // account for the part of the slice used
        s64 used = POLL_UNITS - (c->budget < 0 ? 0 : c->budget);
        g_units += used;
        g_cycles += used * CYCLES_PER_UNIT;
        c->budget = POLL_UNITS;
    }
    u64 idle_fields = 0;
    for (;;) {
        bool enabled = gone || !c || (c->cop0[12] & 0x10001) == 0x10001;
        fire_due_events(now(gone ? nullptr : c), enabled);
        if (enabled) deliver_interrupts();
        u32 id = pick_thread();
        if (!gone && id == self->id) { W(ST_BASE + ST_CURRENT) = id; return; }
        if (id) {
            GThread* next = g_threads[id];
            W(ST_BASE + ST_CURRENT) = id;
            g_cur = next;
            next->cv.notify_one();
            if (gone) return;
            self->site = g_site;
            wait_for_baton(lock, self);
            g_site = self->site;
            continue;
        }
        // nobody can run: the machine idles until the next event
        if (!gone && W(thr(self->id) + T_STATUS) == TH_RUNNING) return;
        u64 next_event = g_next_vblank_start < g_next_vblank_end ? g_next_vblank_start : g_next_vblank_end;
        if (next_alarm() < next_event) next_event = next_alarm() > g_cycles ? next_alarm() : g_cycles;
        if (next_later() < next_event) next_event = next_later() > g_cycles ? next_later() : g_cycles;
        if (next_timer() < next_event) next_event = next_timer() > g_cycles ? next_timer() : g_cycles;
        if ((g_intc_stat & g_intc_mask & 4) && g_vblank_hold > g_cycles && g_vblank_hold < next_event) next_event = g_vblank_hold;
        if (c && !gone) c->budget = POLL_UNITS;
        g_cycles = next_event;
        fire_due_events(g_cycles);
        if (g_rt_verbose && (idle_fields < 12 || idle_fields % 100 == 0))
            fprintf(stderr, "idle field %llu: dma starts ch1 %llu ch2 %llu, FINISH %llu | list %u e0 %x e5 %u e6 %u e7 %u dc %x d8 %u e4 %u p40 %x p44 %x p48 %x p4c %x\n",
                    (unsigned long long)idle_fields, (unsigned long long)g_dma_starts[1], (unsigned long long)g_dma_starts[2],
                    (unsigned long long)g_gs_finish, g_ram[0x6f4130], W(0x41b4e0), g_ram[0x41b4e5], g_ram[0x41b4e6], g_ram[0x41b4e7],
                    W(0x41b4dc), g_ram[0x41b4d8], g_ram[0x41b4e4], W(0x6e4040), W(0x6e4044), W(0x6e4048), W(0x6e404c));
        if (++idle_fields > 600) {
            for (u32 t = 1; t <= MAX_THREAD; t++)
                if (W(thr(t) + T_VALID) && W(thr(t) + T_STATUS) != TH_ZOMBIE)
                    fprintf(stderr, "  thread %u: status %u, waits on semaphore %u, procedure 0x%x%s\n", t, W(thr(t) + T_STATUS),
                            W(thr(t) + T_SEMA), W(thr(t) + T_PROC), g_foreign.count(t) ? " (of the image, cannot run)" : "");
            fprintf(stderr, "  INTC stat %x mask %x, DMAC stat %x, GS CSR %x IMR %x\n", g_intc_stat, g_intc_mask, g_dmac_stat, g_gs_csr, g_gs_imr);
            rt_die("every thread has been blocked for ten seconds of game time");
        }
        deliver_interrupts();
    }
}

void rt_poll(Ctx* c) {
    if (g_in_irq || !t_self || c != &t_self->ctx) { c->budget = (s64)1 << 30; return; }
    std::unique_lock<std::mutex> lock(g_big, std::adopt_lock);
    reschedule(lock, t_self, c);
    lock.release();
}

static bool arith_nearest() {
    static int nearest = -1;
    if (nearest < 0) { const char* o = rt_option("arith"); nearest = o && !strcmp(o, "nearest"); }
    return nearest != 0;
}
// One line at the start of a run: which arithmetic the game's threads compute with.
static void say_arithmetic() {
#if defined(RTA_SOFT_RZ)
    printf("arithmetic: toward zero, denormals are zero - in software (RTA_SOFT_RZ)%s\n", arith_nearest() ? "; --opt arith=nearest has no effect in this build" : "");
#elif defined(__EMSCRIPTEN__)
    // no processor mode to set there: without RTA_SOFT_RZ a WebAssembly build computes as the browser does
    printf("arithmetic: to nearest, denormals kept (WebAssembly without RTA_SOFT_RZ) - NOT the console's\n");
#else
    if (arith_nearest()) printf("arithmetic: the host's (to nearest, denormals kept): --opt arith=nearest - NOT the console's\n");
    else printf("arithmetic: toward zero, denormals are zero - the processor's mode on every thread that runs the game's code\n");
#endif
}

static void thread_main(GThread* self) {
    std::unique_lock<std::mutex> lock(g_big);
    t_self = self;
    // The console's floating point rounds toward zero and has no denormals: one is zero
    // when it is read and when it would be the result.  The emulator the translation is
    // compared with runs the game's thread that way (rounding toward zero and
    // flush-to-zero); with rounding alone an add, subtract, multiply, divide, square root,
    // multiply-add, MAX / MIN or compare gives other bits as soon as a denormal is involved
    // (found by directed operand sets against an exact reference; in the sessions compared
    // so far the log is the same with and without it).  Every host thread that runs
    // translated code starts here, interrupt handlers and alarms included (they are
    // delivered on these threads), and vu0.h computes with the host's floats, so this one
    // place covers the main processor, its FPU and the VU0 macro instructions.
    //   RTA_SOFT_RZ (a build without these processor modes, WebAssembly): the float
    //     helpers do the same in software; the processor's mode is left alone.
    //   --opt arith=nearest: neither is set (the host's own arithmetic; not the console's -
    //     for telling apart what depends on it).
#ifndef RTA_SOFT_RZ
    if (!arith_nearest()) {
        fesetround(FE_TOWARDZERO);
#if defined(__aarch64__) || defined(_M_ARM64)
        { uint64_t fpcr; __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr)); fpcr |= 1ull << 24; __asm__ __volatile__("msr fpcr, %0" : : "r"(fpcr)); }
#elif defined(__x86_64__) || defined(_M_X64)
        _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
        _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
#endif
    }
#endif
    try {
        wait_for_baton(lock, self);
        // A procedure that returns to an address with a translation continues there: that
        // is how a thread of a resumed image, entered in the middle of its procedure,
        // gets back into the frames above it when they have entries.
        u32 pc = self->entry;
        for (;;) {
            call_guest(&self->ctx, pc);
            pc = (u32)self->ctx.r[31];
            if (pc < g_text_lo || pc >= g_text_hi || (pc & 3) || !g_table[(pc - g_text_lo) >> 2]) break;
        }
    } catch (ThreadKill&) {
    }
    // the thread procedure returned, or the thread was ended
    self->finished = true;
    if (thr_ok(self->id) && W(thr(self->id) + T_STATUS) != TH_ZOMBIE) {
        W(thr(self->id) + T_STATUS) = TH_ZOMBIE;
        unlink_thread(self->id);
    }
    if (g_cur == self) reschedule(lock, self, nullptr, true);
}

static GThread* make_thread(u32 id, u32 entry) {
    GThread* t = new GThread();
    t->id = id;
    t->entry = entry;
    memset(&t->ctx, 0, sizeof(Ctx));
    t->ctx.budget = POLL_UNITS;
    t->ctx.fcr31 = 0x01000001;
    t->ctx.cop0[12] = 0x70030C13;
    t->ctx.thread = t;
    g_threads[id] = t;
    return t;
}
static void start_host(GThread* t) {
    host::start_thread([](void* p) { thread_main((GThread*)p); }, t, (size_t)256 << 20);
}

[[noreturn]] static void report_and_exit();
static void wake_sema_waiter(u32 id) {
    for (u32 t = 1; t <= MAX_THREAD; t++) {
        if (!W(thr(t) + T_VALID) || W(thr(t) + T_SEMA) != id) continue;
        u32 status = W(thr(t) + T_STATUS);
        if (status == TH_WAITING) { W(thr(t) + T_STATUS) = TH_RUNNING; link_thread(t); }
        else if (status == TH_SUSPENDED_WAITING) W(thr(t) + T_STATUS) = TH_SUSPENDED;
        else continue;
        W(thr(t) + T_SEMA) = 0;
        W(sem(id) + S_WAITERS)--;
        if (g_foreign.count(t)) rt_note(rt_fmt("thread %u of the resumed image was woken (it cannot run here; proc 0x%x)", t, W(thr(t) + T_PROC)));
        return;
    }
}

void rt_signal_sema(u32 id) {
    if (!sem_ok(id)) return;
    if (W(sem(id) + S_WAITERS)) wake_sema_waiter(id);
    else W(sem(id) + S_COUNT)++;
}

// The calling thread waits on the clock.  It is parked the way a thread waiting on a
// semaphore is, on a semaphore number no semaphore has, so that neither SignalSema nor
// WakeupThread from the game ends the wait early.
static const u32 NO_SEMA = 0xFFFF;
void rt_sleep(Ctx* c, u64 delay) {
    if (g_in_irq || !t_self || c != &t_self->ctx || !delay) return;
    GThread* self = t_self;
    u32 me = self->id;
    std::unique_lock<std::mutex> lock(g_big, std::adopt_lock);
    struct Release { std::unique_lock<std::mutex>& l; ~Release() { l.release(); } } release{lock};
    W(thr(me) + T_STATUS) = TH_WAITING;
    W(thr(me) + T_SEMA) = NO_SEMA;
    unlink_thread(me);
    rt_after(delay, [me] {
        if (!thr_ok(me) || W(thr(me) + T_SEMA) != NO_SEMA) return;
        u32 status = W(thr(me) + T_STATUS);
        if (status == TH_WAITING) { W(thr(me) + T_STATUS) = TH_RUNNING; link_thread(me); }
        else if (status == TH_SUSPENDED_WAITING) W(thr(me) + T_STATUS) = TH_SUSPENDED;
        W(thr(me) + T_SEMA) = 0;
    });
    reschedule(lock, self, c);
}

// ---------------------------------------------------------------------------------------
// System calls
// ---------------------------------------------------------------------------------------
static const char* syscall_name(u32 n) {
    switch (n) {
    case 0x02: return "SetGsCrt"; case 0x04: return "Exit"; case 0x10: return "AddIntcHandler";
    case 0x11: return "RemoveIntcHandler"; case 0x12: return "AddDmacHandler"; case 0x13: return "RemoveDmacHandler";
    case 0x14: return "EnableIntc"; case 0x15: return "DisableIntc"; case 0x16: return "EnableDmac";
    case 0x17: return "DisableDmac"; case 0x1A: return "iEnableIntc"; case 0x1B: return "iDisableIntc";
    case 0x1C: return "iEnableDmac"; case 0x1D: return "iDisableDmac"; case 0x20: return "CreateThread";
    case 0x21: return "DeleteThread"; case 0x22: return "StartThread"; case 0x23: return "ExitThread";
    case 0x24: return "ExitDeleteThread"; case 0x25: return "TerminateThread"; case 0x29: return "ChangeThreadPriority";
    case 0x2A: return "iChangeThreadPriority"; case 0x2B: return "RotateThreadReadyQueue"; case 0x2C: return "iRotateThreadReadyQueue";
    case 0x2F: return "GetThreadId"; case 0x30: return "ReferThreadStatus"; case 0x31: return "iReferThreadStatus";
    case 0x32: return "SleepThread"; case 0x33: return "WakeupThread"; case 0x34: return "iWakeupThread";
    case 0x35: return "CancelWakeupThread"; case 0x37: return "SuspendThread"; case 0x39: return "ResumeThread";
    case 0x3C: return "SetupThread"; case 0x3D: return "SetupHeap"; case 0x3E: return "EndOfHeap";
    case 0x40: return "CreateSema"; case 0x41: return "DeleteSema"; case 0x42: return "SignalSema";
    case 0x43: return "iSignalSema"; case 0x44: return "WaitSema"; case 0x45: return "PollSema";
    case 0x46: return "iPollSema"; case 0x47: return "ReferSemaStatus"; case 0x48: return "iReferSemaStatus";
    case 0x4A: return "SetOsdConfigParam"; case 0x4B: return "GetOsdConfigParam"; case 0x64: return "FlushCache";
    case 0x68: return "iFlushCache"; case 0x70: return "GsGetIMR"; case 0x71: return "GsPutIMR";
    case 0x73: return "SetVSyncFlag"; case 0x74: return "SetSyscall"; case 0x76: return "SifDmaStat";
    case 0x77: return "SifSetDma"; case 0x78: return "SifSetDChain"; case 0x79: return "SifSetReg";
    case 0x7A: return "SifGetReg"; case 0x7C: return "Deci2Call"; case 0x7E: return "MachineType";
    case 0x7F: return "GetMemorySize"; case 0xFC: return "SetAlarm"; case 0xFD: return "ReleaseAlarm";
    }
    return "?";
}

static u32 alloc_slot(u32 base, u32 size, u32 first, u32 count) {
    for (u32 i = 0; i < count; i++)
        if (!W(base + i * size)) { memset(g_ram + base + i * size, 0, size); W(base + i * size) = 1; return first + i; }
    return ~0u;
}

static u32 add_handler(u32 queue_slot, u32 base, Ctx* c) {
    u32 cause = (u32)c->r[4], address = (u32)c->r[5], next = (u32)c->r[6], arg = (u32)c->r[7];
    u32 id = alloc_slot(base, H_SIZE, 1, MAX_HANDLER);
    if (id == ~0u) return ~0u;
    u32 h = base + (id - 1) * H_SIZE;
    W(h + H_CAUSE) = cause; W(h + H_ADDRESS) = address; W(h + H_ARG) = arg; W(h + H_GP) = (u32)c->r[28];
    u32 slot = ST_BASE + queue_slot;
    if (next == 0) { W(h + H_NEXT) = W(slot); W(slot) = id; }
    else {
        while (W(slot) && W(slot) != next) slot = base + (W(slot) - 1) * H_SIZE + H_NEXT;
        W(h + H_NEXT) = W(slot); W(slot) = id;       // before `next`, or at the end for -1
    }
    return id;
}
static void remove_handler(u32 queue_slot, u32 base, u32 id) {
    u32 slot = ST_BASE + queue_slot;
    while (W(slot) && W(slot) != id) slot = base + (W(slot) - 1) * H_SIZE + H_NEXT;
    if (W(slot) == id) W(slot) = W(base + (id - 1) * H_SIZE + H_NEXT);
    if (id >= 1 && id <= MAX_HANDLER) W(base + (id - 1) * H_SIZE + H_VALID) = 0;
}

void rt_syscall(Ctx* c, u32 pc) {
    s32 raw = (s32)c->r[3];
    u32 n = raw < 0 ? (u32)-raw : (u32)raw;
    rt_note(rt_fmt("syscall 0x%02x %s", n, syscall_name(n)));
    TRACE("  syscall %x %s(%x, %x) by thread %u%s at %x\n", n, syscall_name(n), (u32)c->r[4], (u32)c->r[5], t_self ? t_self->id : 0,
          g_in_irq ? " (irq)" : "", (u32)c->r[31]);
    // a handler the game installed itself with SetSyscall (table at 0x10000, as Play! keeps it)
    if (n < 0x200 && n != 0x74 && W(0x10000 + n * 4)) {
        u64 saved_ra = c->r[31];
        rt_call(c, W(0x10000 + n * 4));
        c->r[31] = saved_ra;
        return;
    }
    GThread* self = t_self;
    std::unique_lock<std::mutex> lock(g_big, std::adopt_lock);
    struct Release { std::unique_lock<std::mutex>& l; ~Release() { l.release(); } } release{lock};
    u32 a0 = (u32)c->r[4], a1 = (u32)c->r[5], a2 = (u32)c->r[6], a3 = (u32)c->r[7];
    u64 result = 0;
    bool yield = false;
    u32 me = self ? self->id : 0;
    switch (n) {
    case 0x02: break;                                   // SetGsCrt
    case 0x04: printf("the game called Exit(%d)\n", (s32)a0); report_and_exit();
    case 0x10: result = SX32(add_handler(ST_INTCQ, INTC_BASE, c)); break;
    case 0x11: remove_handler(ST_INTCQ, INTC_BASE, a1); break;
    case 0x12: result = SX32(add_handler(ST_DMACQ, DMAC_BASE, c)); break;
    case 0x13: remove_handler(ST_DMACQ, DMAC_BASE, a1); break;
    case 0x14: case 0x1A: result = !(g_intc_mask & (1u << a0)); g_intc_mask |= 1u << a0; break;
    case 0x15: case 0x1B: result = (g_intc_mask >> a0) & 1; g_intc_mask &= ~(1u << a0); break;
    case 0x16: case 0x1C: result = !(g_dmac_stat & (0x10000u << a0)); g_dmac_stat |= 0x10000u << a0; break;
    case 0x17: case 0x1D: result = (g_dmac_stat >> (16 + a0)) & 1; g_dmac_stat &= ~(0x10000u << a0); break;
    case 0x20: {                                        // CreateThread(param)
        u32 id = alloc_slot(THREAD_BASE, T_SIZE, 1, MAX_THREAD);
        if (id == ~0u) { result = SX32(-1); break; }
        u32 p = a0 & 0x1FFFFFF, t = thr(id);
        W(t + T_STATUS) = TH_ZOMBIE;
        W(t + T_PROC) = W(p + 4); W(t + T_STACKBASE) = W(p + 8); W(t + T_STACKSIZE) = W(p + 12);
        W(t + T_GP) = W(p + 16); W(t + T_INITPRI) = W(p + 20); W(t + T_PRI) = W(p + 20);
        W(t + T_EPC) = W(p + 4);
        result = id;
        break;
    }
    case 0x21: if (thr_ok(a0) && a0 != me) { W(thr(a0) + T_VALID) = 0; } break;
    case 0x22: {                                        // StartThread(id, arg)
        if (!thr_ok(a0)) { result = SX32(-1); break; }
        u32 t = thr(a0);
        GThread* g = make_thread(a0, W(t + T_PROC));
        g->ctx.r[4] = SX32(a1);
        g->ctx.r[28] = SX32(W(t + T_GP));
        g->ctx.r[29] = SX32(W(t + T_STACKBASE) + W(t + T_STACKSIZE) - 0x2A0 - 0x20);
        g->ctx.r[30] = g->ctx.r[29];
        g->ctx.r[31] = 0;
        W(t + T_STATUS) = TH_RUNNING;
        W(t + T_PRI) = W(t + T_INITPRI);
        link_thread(a0);
        start_host(g);
        result = a0;
        yield = true;
        break;
    }
    case 0x23: case 0x24:                               // ExitThread, ExitDeleteThread
        W(thr(me) + T_STATUS) = TH_ZOMBIE;
        unlink_thread(me);
        if (n == 0x24) W(thr(me) + T_VALID) = 0;
        throw ThreadKill();
    case 0x25: case 0x26:                               // TerminateThread
        if (thr_ok(a0) && a0 != me) {
            W(thr(a0) + T_STATUS) = TH_ZOMBIE;
            unlink_thread(a0);
            auto it = g_threads.find(a0);
            if (it != g_threads.end() && !it->second->finished) it->second->kill = true;
        }
        break;
    case 0x29: case 0x2A: {                             // ChangeThreadPriority(id, priority)
        u32 id = a0 ? a0 : me;
        if (!thr_ok(id)) { result = SX32(-1); break; }
        result = W(thr(id) + T_PRI);
        W(thr(id) + T_PRI) = a1;
        if (W(thr(id) + T_STATUS) == TH_RUNNING) { unlink_thread(id); link_thread(id); }
        yield = n == 0x29;
        break;
    }
    case 0x2B: case 0x2C: {                             // RotateThreadReadyQueue(priority)
        for (u32 cur = W(ST_BASE + ST_THREADQ); cur; cur = W(thr(cur) + T_NEXT))
            if (W(thr(cur) + T_PRI) == a0) { unlink_thread(cur); link_thread(cur); break; }
        result = a0;
        yield = n == 0x2B;
        break;
    }
    case 0x2F: result = me; break;
    case 0x30: case 0x31: {                             // ReferThreadStatus(id, out)
        u32 id = a0 ? a0 : me;
        if (!thr_ok(id)) { result = SX32(-1); break; }
        u32 t = thr(id), status = W(t + T_STATUS), out;
        switch (status) {
        case TH_RUNNING: out = id == me ? 1 : 2; break;
        case TH_SLEEPING: case TH_WAITING: out = 4; break;
        case TH_SUSPENDED: out = 8; break;
        case TH_SUSPENDED_SLEEPING: case TH_SUSPENDED_WAITING: out = 12; break;
        default: out = 16;
        }
        if (a1) {
            u32 p = a1 & 0x1FFFFFF;
            W(p) = out; W(p + 4) = W(t + T_PROC); W(p + 8) = W(t + T_STACKBASE); W(p + 12) = W(t + T_STACKSIZE);
            W(p + 16) = W(t + T_GP); W(p + 20) = W(t + T_INITPRI); W(p + 24) = W(t + T_PRI);
        }
        result = out;
        break;
    }
    case 0x32:                                          // SleepThread
        if (W(thr(me) + T_WAKEUPS)) W(thr(me) + T_WAKEUPS)--;
        else { W(thr(me) + T_STATUS) = TH_SLEEPING; unlink_thread(me); yield = true; }
        result = me;
        break;
    case 0x33: case 0x34: {                             // WakeupThread
        if (!thr_ok(a0)) { result = SX32(-1); break; }
        u32 t = thr(a0), status = W(t + T_STATUS);
        if (status == TH_SLEEPING) { W(t + T_STATUS) = TH_RUNNING; link_thread(a0); }
        else if (status == TH_SUSPENDED_SLEEPING) W(t + T_STATUS) = TH_SUSPENDED;
        else W(t + T_WAKEUPS)++;
        if (g_foreign.count(a0)) rt_note(rt_fmt("thread %u of the resumed image was woken (it cannot run here; proc 0x%x)", a0, W(t + T_PROC)));
        result = a0;
        yield = n == 0x33;
        break;
    }
    case 0x35: case 0x36: if (thr_ok(a0)) { result = W(thr(a0) + T_WAKEUPS); W(thr(a0) + T_WAKEUPS) = 0; } break;
    case 0x37: case 0x38: {                             // SuspendThread
        if (!thr_ok(a0)) break;
        u32 t = thr(a0), status = W(t + T_STATUS);
        if (status == TH_RUNNING) { W(t + T_STATUS) = TH_SUSPENDED; unlink_thread(a0); }
        else if (status == TH_WAITING) W(t + T_STATUS) = TH_SUSPENDED_WAITING;
        else if (status == TH_SLEEPING) W(t + T_STATUS) = TH_SUSPENDED_SLEEPING;
        yield = true;
        break;
    }
    case 0x39: case 0x3A: {                             // ResumeThread
        if (!thr_ok(a0)) break;
        u32 t = thr(a0), status = W(t + T_STATUS);
        if (status == TH_SUSPENDED) { W(t + T_STATUS) = TH_RUNNING; link_thread(a0); }
        else if (status == TH_SUSPENDED_WAITING) W(t + T_STATUS) = TH_WAITING;
        else if (status == TH_SUSPENDED_SLEEPING) W(t + T_STATUS) = TH_SLEEPING;
        yield = n == 0x39;
        break;
    }
    case 0x3C: {                                        // SetupThread(gp, stack, size, args, root)
        u32 top = a1 == 0xFFFFFFFFu ? RAM_SIZE - 4096 : a1 + a2;
        u32 t = thr(me);
        g_gp = a0;
        W(t + T_GP) = a0;
        W(t + T_STACKBASE) = top - a2; W(t + T_STACKSIZE) = a2;
        // The argument block: a count, sixteen pointers, then the text.  Without --arg
        // the game starts with no arguments at all (the count is 0); with it the block is
        // filled as the kernel fills it for a start from the disc: the program's name
        // first, then one argument per --arg.
        W(a3 & 0x1FFFFFF) = 0;                          // argc
        W((a3 & 0x1FFFFFF) + 4) = 0;
        if (!g_boot_args.empty()) {
            u32 block = a3 & 0x1FFFFFF, text = block + 4 + 16 * 4, at = text;
            std::vector<std::string> words = {"cdrom0:\\SLUS_209.73;1"};
            words.insert(words.end(), g_boot_args.begin(), g_boot_args.end());
            for (size_t i = 0; i < words.size() && i < 16 && at + words[i].size() + 1 <= text + 256; i++) {
                memcpy(g_ram + at, words[i].c_str(), words[i].size() + 1);
                W(block + 4 + (u32)i * 4) = at;
                at += (u32)words[i].size() + 1;
                W(block) = (u32)i + 1;
            }
        }
        result = top - 0x2A0;
        break;
    }
    case 0x3D: {                                        // SetupHeap(base, size)
        u32 t = thr(me);
        W(t + T_HEAPBASE) = a1 == 0xFFFFFFFFu ? W(t + T_STACKBASE) : a0 + a1;
        result = W(t + T_HEAPBASE);
        break;
    }
    case 0x3E: result = W(thr(me) + T_HEAPBASE); break;
    case 0x40: {                                        // CreateSema(param)
        u32 id = alloc_slot(SEMA_BASE, S_SIZE, 0, MAX_SEMA);
        if (id == ~0u) { result = SX32(-1); break; }
        u32 p = a0 & 0x1FFFFFF;
        W(sem(id) + S_COUNT) = W(p + 8); W(sem(id) + S_MAX) = W(p + 4); W(sem(id) + S_OPTION) = W(p + 20);
        result = id;
        break;
    }
    case 0x41:                                          // DeleteSema
        if (!sem_ok(a0)) { result = SX32(-1); break; }
        while (W(sem(a0) + S_WAITERS)) wake_sema_waiter(a0);
        W(sem(a0) + S_VALID) = 0;
        result = a0;
        break;
    case 0x42: case 0x43:                               // SignalSema, iSignalSema
        if (!sem_ok(a0)) { result = SX32(-1); break; }
        if (W(sem(a0) + S_WAITERS)) wake_sema_waiter(a0);
        else W(sem(a0) + S_COUNT)++;
        result = a0;
        yield = n == 0x42;
        break;
    case 0x44:                                          // WaitSema
        if (!sem_ok(a0)) { result = SX32(-1); break; }
        if (W(sem(a0) + S_COUNT)) W(sem(a0) + S_COUNT)--;
        else {
            W(sem(a0) + S_WAITERS)++;
            W(thr(me) + T_STATUS) = TH_WAITING;
            W(thr(me) + T_SEMA) = a0;
            unlink_thread(me);
            yield = true;
        }
        result = a0;
        break;
    case 0x45: case 0x46:                               // PollSema
        if (!sem_ok(a0) || !W(sem(a0) + S_COUNT)) { result = SX32(-1); break; }
        W(sem(a0) + S_COUNT)--;
        result = a0;
        break;
    case 0x47: case 0x48:                               // ReferSemaStatus(id, out)
        if (!sem_ok(a0)) { result = SX32(-1); break; }
        if (a1) {
            u32 p = a1 & 0x1FFFFFF;
            W(p) = W(sem(a0) + S_COUNT); W(p + 4) = W(sem(a0) + S_MAX); W(p + 12) = W(sem(a0) + S_WAITERS);
        }
        result = a0;
        break;
    case 0x4B: if (a0) W(a0 & 0x1FFFFFF) = 0x00021000; break;    // GetOsdConfigParam: English, NTSC
    case 0x64: case 0x68: break;                        // FlushCache
    case 0x70: result = g_gs_imr; break;
    case 0x71: g_gs_imr = a0; break;
    case 0x73: W(ST_BASE + ST_VSYNC1) = a0; W(ST_BASE + ST_VSYNC2) = a1; break;
    case 0x74: {                                        // SetSyscall(number, handler)
        u32 h = a1 & 0x1FFFFFFF;
        bool translated = h >= g_text_lo && h < g_text_hi && !(h & 3) && g_table[(h - g_text_lo) >> 2];
        // The SDK copies a block of its own kernel-mode code out of its data section into
        // kernel memory (0x80076000) and installs it as system calls 0xfc-0xff (alarms).
        // Code that exists only as data has no translation; the kernel here has alarms
        // of its own, so that registration is dropped.
        if (!translated) rt_note(rt_fmt("SetSyscall(0x%x) to code outside the executable (0x%08x): dropped", a0, a1));
        else if (a0 < 0x200) W(0x10000 + a0 * 4) = h;
        break;
    }
    case 0xFC: case 0xFE: {                             // SetAlarm(scan lines, callback, argument)
        u32 id = 0;
        for (u32 k = 0; k < 16; k++) if (!g_alarms[k].active) { id = k + 1; break; }
        if (!id) { result = SX32(-1); break; }
        g_alarms[id - 1] = {true, now(g_in_irq ? nullptr : c) + (u64)(a0 & 0xFFFF) * 18740, a1, a2};
        result = id;
        break;
    }
    case 0xFD: case 0xFF:                               // ReleaseAlarm(id)
        if (a0 >= 1 && a0 <= 16 && g_alarms[a0 - 1].active) { g_alarms[a0 - 1].active = false; result = 0; }
        else result = SX32(-1);
        break;
    case 0x76: result = SX32(-1); break;                // SifDmaStat: completed
    case 0x77: result = iop_sif_set_dma(a0, a1); break; // SifSetDma(transfers, count): to I/O processor memory
    case 0x78: break;
    case 0x79: break;                                   // SifSetReg
    case 0x7A: result = a0 == 4 ? 0x60000 : 0; break;   // SifGetReg: the I/O processor is ready
    case 0x7C: {                                        // Deci2Call(function, parameters): the debugger link, used for the game's console text
        u32 p = guest_addr(a1, 8);
        static u32 buffers[16];
        static std::string line;
        result = 1;
        if (p == ~0u) break;
        if (a0 == 1) {                                  // open: device, buffer -> id
            u32 id = 0;
            while (id < 16 && buffers[id]) id++;
            if (id == 16) { result = SX32(-1); break; }
            buffers[id] = W(p + 4);
            result = id;
        } else if (a0 == 3 || a0 == 4) {                // send (the text is taken at once), poll (clears "busy")
            u32 id = W(p);
            u32 b = id < 16 && buffers[id] ? guest_addr(buffers[id], 0x14) : ~0u;
            if (b == ~0u) break;
            if (a0 == 4) { W(b + 0x0C) = 0; break; }
            u32 data = W(b + 0x10) ? guest_addr(W(b + 0x10), 12) : ~0u;
            if (data == ~0u) { W(b + 4) = (u32)-1; break; }
            u32 size = W(data);
            for (u32 k = 12; k < size && data + k < RAM_SIZE; k++) {
                char ch = (char)g_ram[data + k];
                if (ch == '\n') { printf("[game] %s\n", line.c_str()); line.clear(); }
                else if (ch != '\r') line += ch;
            }
            W(b + 4) = 0;
        } else if (a0 == 0x10) {                        // kernel puts
            u32 text = guest_addr(W(p), 1);
            if (text != ~0u) printf("[game] %s", (const char*)g_ram + text);
        }
        break;
    }
    case 0x4A: break;                                   // SetOsdConfigParam
    case 0x7E: result = 0x100; break;
    case 0x7F: result = RAM_SIZE; break;
    default:
        rt_note(rt_fmt("UNHANDLED syscall 0x%02x at 0x%x", n, pc));
    }
    c->r[2] = result;
    if (self && !g_in_irq && (yield || true)) reschedule(lock, self, c);
}

// ---------------------------------------------------------------------------------------
// Hardware registers
// ---------------------------------------------------------------------------------------
// Four 16-bit timers.  A timer counts the bus clock (half the CPU clock), that divided by
// 16 or 256, or scan lines; it can raise its interrupt (INTC 9 + n) when the count
// reaches the compare register (mode bit 8, flag bit 10) and when it overflows (bit 9,
// flag bit 11), and return to zero on a compare match (bit 6).  Sony's library builds
// its thread delays and alarms on these interrupts.
static u32 timer_count(int n) {
    timer_sync(n, now(t_self && !g_in_irq ? &t_self->ctx : nullptr));
    return g_timers[n].base_count & 0xFFFF;
}

static u8* phys(u32 addr, u32 size) {
    if (addr & 0x80000000u) {                           // scratchpad flag in a DMA address
        u32 off = addr & 0x3FFF;
        return off + size <= sizeof(g_spr) ? g_spr + off : nullptr;
    }
    addr &= 0x01FFFFFF;
    return addr <= RAM_SIZE - size ? g_ram + addr : nullptr;
}

// ---- what the graphics data would have done, as far as the game can notice ------------
// Nothing is drawn.  The data is walked for the two things that feed back into the
// game: microcode loaded into VU0, and the GS registers SIGNAL / FINISH, which raise the
// GS interrupt the game's renderer waits for.  Along the way the traffic is counted.
static u64 g_gs_writes, g_gs_vertices, g_gs_prims, g_gif_packets, g_vif_unpacks, g_vif_mscal, g_gs_signal;
static u64 g_gs_siglblid;

static void gs_register(u32 reg, u64 value) {
    g_gs_writes++;
    if (reg == 0x60) {                                  // SIGNAL
        u32 id = (u32)value, mask = (u32)(value >> 32);
        g_gs_siglblid = (g_gs_siglblid & ~(u64)mask) | (id & mask);
        g_gs_signal++;
        g_gs_csr |= 1;
        if (!(g_gs_imr & 0x100)) g_intc_stat |= 1;
    } else if (reg == 0x61) {                           // FINISH
        g_gs_finish++;
        TRACE("  GS FINISH (imr %x)\n", g_gs_imr);
        g_gs_csr |= 2;
        if (!(g_gs_imr & 0x200)) g_intc_stat |= 1;
    } else if (reg == 0x62) {                           // LABEL
        u32 id = (u32)value, mask = (u32)(value >> 32);
        g_gs_siglblid = (g_gs_siglblid & 0xFFFFFFFFull) | ((u64)((u32)(g_gs_siglblid >> 32) & ~mask) | (id & mask)) << 32;
    }
}

// GIF packets: `data` is whole quadwords
static void gif_stream(const u32* data, size_t words) {
    size_t q = 0, total = words / 4;
    while (q < total) {
        u64 lo, hi;
        memcpy(&lo, data + q * 4, 8);
        memcpy(&hi, data + q * 4 + 2, 8);
        q++;
        g_gif_packets++;
        u32 nloop = (u32)lo & 0x7FFF, flg = (u32)(lo >> 58) & 3, nreg = (u32)(lo >> 60) & 15;
        if (!nreg) nreg = 16;
        if ((lo >> 46) & 1) g_gs_prims++;
        if (flg == 0) {                                 // PACKED: one quadword per register
            for (u32 loop = 0; loop < nloop && q < total; loop++)
                for (u32 r = 0; r < nreg && q < total; r++, q++) {
                    u32 id = (u32)(hi >> (4 * r)) & 15;
                    u64 dlo, dhi;
                    memcpy(&dlo, data + q * 4, 8);
                    memcpy(&dhi, data + q * 4 + 2, 8);
                    if (id == 0xE) gs_register((u32)dhi & 0xFF, dlo);
                    else { g_gs_writes++; if (id == 4 || id == 5 || id == 0xC || id == 0xD) g_gs_vertices++; if (id == 0) g_gs_prims++; }
                }
        } else if (flg == 1) {                          // REGLIST: one doubleword per register
            u64 count = (u64)nloop * nreg;
            for (u64 k = 0; k < count && q * 2 + k < total * 2; k++) {
                u32 id = (u32)(hi >> (4 * (k % nreg))) & 15;
                g_gs_writes++;
                if (id == 4 || id == 5 || id == 0xC || id == 0xD) g_gs_vertices++;
            }
            q += (count + 1) / 2;
        } else q += nloop;                              // IMAGE
    }
}

// VIF codes.  which: 0 = VIF0 (microcode goes to VU0), 1 = VIF1
static void vif_stream(const std::vector<u32>& w, int which) {
    u32 cl = 1, wl = 1;
    size_t i = 0, n = w.size();
    while (i < n) {
        u32 code = w[i++];
        u32 cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF, imm = code & 0xFFFF;
        if (cmd == 0x01) { cl = imm & 0xFF; wl = (imm >> 8) & 0xFF; }
        else if (cmd == 0x14 || cmd == 0x15 || cmd == 0x17) g_vif_mscal++;
        else if (cmd == 0x20) i += 1;
        else if (cmd == 0x30 || cmd == 0x31) i += 4;
        else if (cmd == 0x4A) {                         // MPG: microcode
            u32 count = num ? num : 256;
            if (which == 0) {
                for (u32 k = 0; k < count * 2 && i + k < n; k++)
                    memcpy(g_vu0.micro + ((imm * 8 + k * 4) & 0xFFF), &w[i + k], 4);
                rt_note(rt_fmt("VIF0 MPG: %u instructions to VU0 address 0x%x", count, imm));
            }
            i += count * 2;
        } else if (cmd == 0x50 || cmd == 0x51) {        // DIRECT: GIF packets
            size_t count = (size_t)(imm ? imm : 65536) * 4;
            if (count > n - i) count = n - i;
            if (which == 1) gif_stream(w.data() + i, count);
            i += count;
        } else if (cmd >= 0x60) {                       // UNPACK: data for VU memory
            u32 vn = (cmd >> 2) & 3, vl = cmd & 3;
            u32 elements = num ? num : 256;
            if (wl > cl && wl) elements = cl * (elements / wl) + ((elements % wl) < cl ? (elements % wl) : cl);
            u32 bytes = (vn == 3 && vl == 3) ? elements * 2 : elements * (vn + 1) * (4 >> vl);
            i += (bytes + 3) / 4;
            g_vif_unpacks++;
            if (which == 0) rt_note("VIF0 UNPACK (data for VU0 memory, not carried out)");
        }
    }
}

static void dma_start(u32 ch) {
    u32 base = ch < 3 ? 0x10008000 + ch * 0x1000 : ch < 5 ? 0x1000B000 + (ch - 3) * 0x400
             : ch < 8 ? 0x1000C000 + (ch - 5) * 0x400 : 0x1000D000 + (ch - 8) * 0x400;
    u32 chcr = g_hw[base], madr = g_hw[base + 0x10], qwc = g_hw[base + 0x20] & 0xFFFF, tadr = g_hw[base + 0x30];
    u32 sadr = g_hw[base + 0x80];
    g_dma_starts[ch]++;
    u32 mode = (chcr >> 2) & 3, tadr0 = tadr;
    std::vector<u32> stream;
    auto append = [&](u32 addr, u32 quadwords) {
        u8* m = phys(addr, quadwords * 16);
        if (!m) { rt_note(rt_fmt("DMA channel %u: data outside memory", ch)); return; }
        size_t at = stream.size();
        stream.resize(at + quadwords * 4);
        memcpy(stream.data() + at, m, quadwords * 16);
    };
    if (ch == 8 || ch == 9) {                           // scratchpad <-> memory
        if (mode != 0) rt_note(rt_fmt("DMA channel %u in chain mode (not carried out)", ch));
        else {
            u8* m = phys(madr, qwc * 16);
            u32 sp = sadr & 0x3FFF;
            if (m && sp + qwc * 16 <= sizeof(g_spr)) {
                if (ch == 8) memcpy(m, g_spr + sp, qwc * 16); else memcpy(g_spr + sp, m, qwc * 16);
            }
            g_dma_qwords[ch] += qwc;
            g_hw[base + 0x10] = madr + qwc * 16;
            g_hw[base + 0x80] = sadr + qwc * 16;
        }
    } else if (mode == 0) {                             // normal: one block
        if (ch <= 2) append(madr, qwc);
        g_dma_qwords[ch] += qwc;
        g_hw[base + 0x10] = madr + qwc * 16;
    } else if (mode == 1) {                             // source chain
        // The registers are left as the hardware leaves them, because the game's DMA
        // handler reads them to see how far a list got: TADR, MADR, the tag bits in CHCR,
        // and the two-level return stack ASR0/ASR1 with its pointer in CHCR bits 4-5.  A
        // tag with its IRQ bit set ends the transfer when CHCR.TIE is set; starting the
        // channel again continues with the tag at TADR.
        bool tte = chcr & 0x40, tie = chcr & 0x80;
        u32 asp = (chcr >> 4) & 3;
        if (qwc) {                                      // a block left over from before
            if (ch <= 2) append(madr, qwc);
            g_dma_qwords[ch] += qwc;
            madr += qwc * 16;
        }
        for (int guard = 0; guard < 1000000; guard++) {
            u8* tag = phys(tadr, 16);
            if (!tag) { rt_note(rt_fmt("DMA channel %u: chain tag outside memory", ch)); break; }
            u64 t;
            memcpy(&t, tag, 8);
            u32 n = (u32)t & 0xFFFF, id = ((u32)t >> 28) & 7, addr = (u32)(t >> 32);
            chcr = (chcr & 0xFFFF) | ((u32)t & 0xFFFF0000u);
            bool end = false;
            if (ch == 1 && rt_dma_tag) rt_dma_tag(tadr, stream);
            switch (id) {
            case 0: madr = addr; tadr += 16; end = true; break;                 // refe
            case 1: madr = tadr + 16; tadr = madr + n * 16; break;              // cnt
            case 2: madr = tadr + 16; tadr = addr; break;                       // next
            case 3: case 4: madr = addr; tadr += 16; break;                     // ref, refs
            case 5:                                                             // call
                madr = tadr + 16;
                if (asp < 2) { g_hw[base + 0x40 + asp * 0x10] = madr + n * 16; asp++; }
                tadr = addr;
                break;
            case 6:                                                             // ret
                madr = tadr + 16;
                if (asp > 0) { asp--; tadr = g_hw[base + 0x40 + asp * 0x10]; }
                else end = true;
                break;
            case 7: madr = tadr + 16; end = true; break;                        // end
            }
            if (ch <= 2) {
                if (tte && ch != 2) { u32 two[2]; memcpy(two, tag + 8, 8); stream.push_back(two[0]); stream.push_back(two[1]); }
                append(madr, n);
            }
            madr += n * 16;
            g_dma_qwords[ch] += n + 1;
            if (end || (((u32)t & 0x80000000u) && tie)) break;
        }
        chcr = (chcr & ~0x30u) | (asp << 4);
        g_hw[base + 0x30] = tadr;
        g_hw[base + 0x10] = madr;
    }
    TRACE("  dma ch%u from %x: %zu words, now tadr %x asr0 %x | list %u e0 %x e5 %u e6 %u e7 %u dc %x p40 %x p44 %x p48 %x p4c %x\n", ch, tadr0,
          stream.size(), g_hw[base + 0x30], g_hw[base + 0x40], g_ram[0x6f4130], W(0x41b4e0), g_ram[0x41b4e5], g_ram[0x41b4e6],
          g_ram[0x41b4e7], W(0x41b4dc), W(0x6e4040), W(0x6e4044), W(0x6e4048), W(0x6e404c));
    if (ch == 0) vif_stream(stream, 0);
    else if (ch == 1) vif_stream(stream, 1);
    else if (ch == 2) gif_stream(stream.data(), stream.size());
    if (g_hooks.video && !stream.empty()) {
        if (ch == 0) g_hooks.video->vif0(stream.data(), stream.size());
        else if (ch == 1) g_hooks.video->vif1(stream.data(), stream.size());
        else if (ch == 2) g_hooks.video->gif(stream.data(), stream.size());
    }
    g_hw[base] = chcr & ~0x100u;
    g_hw[base + 0x20] = 0;
    g_dmac_stat |= 1u << ch;
    if (g_dmac_stat & (0x10000u << ch)) g_dmac_pending |= 1u << ch;
}

static void deliver_if_enabled() {
    if (!g_in_irq && t_self && (t_self->ctx.cop0[12] & 0x10001) == 0x10001) deliver_interrupts();
}

static u64 hw_read(u32 a, unsigned size) {
    if (a >= 0x10000000 && a < 0x10002000) {
        int n = (a >> 11) & 3;
        switch (a & 0x7FF) {
        case 0x00: return timer_count(n);
        case 0x10: timer_count(n); return g_timers[n].mode;
        case 0x20: return g_timers[n].comp;
        case 0x30: return g_timers[n].hold;
        }
    }
    switch (a) {
    case 0x1000F000: return g_intc_stat;
    case 0x1000F010: return g_intc_mask;
    case 0x1000E010: return g_dmac_stat;
    case 0x1000E000: return g_dmac_ctrl;
    case 0x1000F520: return g_hw[0x1000F590];
    case 0x12001000: return g_gs_csr | 0x4000;          // FIFO empty
    case 0x12001080: return g_gs_siglblid;
    case 0x10003020: case 0x10003800: case 0x10003C00: return 0;    // GIF, VIF0, VIF1 status: idle
    case 0x10002010: return 0;                          // IPU control: not busy
    }
    if (!((a >= 0x10000000 && a < 0x10010000) || (a >= 0x12000000 && a < 0x12002000))) {
        rt_note(rt_fmt("read of nothing at 0x%04xxxxx (gives 0)", a >> 16));
        return 0;
    }
    auto it = g_hw.find(a & ~3u);
    if (a < 0x10008000 || a >= 0x1000E000) rt_note(rt_fmt("hardware read  0x%08x", a & ~0xFu));
    (void)size;
    return it == g_hw.end() ? 0 : it->second;
}

static void hw_write(u32 a, unsigned size, u64 value) {
    u32 v = (u32)value;
    (void)size;
    if (g_hooks.video && ((a >= 0x12000000 && a < 0x12002000) || (a >= 0x10003000 && a < 0x10004000)))
        g_hooks.video->reg(a, value);
    if (a >= 0x10000000 && a < 0x10002000) {
        int n = (a >> 11) & 3;
        Timer& t = g_timers[n];
        u64 t_now = now(t_self && !g_in_irq ? &t_self->ctx : nullptr);
        timer_sync(n, t_now);
        switch (a & 0x7FF) {
        case 0x00: t.base_count = v & 0xFFFF; if (t_now > t.base_cycles) t.base_cycles = t_now; return;
        case 0x10:                                      // the two flag bits are cleared by writing 1
            if (!(t.mode & 0x80) && t_now > t.base_cycles) t.base_cycles = t_now;
            t.mode = (v & 0x3FF) | (t.mode & 0xC00 & ~v);
            return;
        case 0x20: t.comp = v & 0xFFFF; return;
        case 0x30: t.hold = v & 0xFFFF; return;
        }
    }
    switch (a) {
    case 0x1000F000: g_intc_stat &= ~v; return;
    case 0x1000F010: g_intc_mask ^= v & 0x7FFF; return;
    case 0x1000E010: g_dmac_stat = (g_dmac_stat & ~(v & 0xFFFF)) ^ (v & 0xFFFF0000u); return;
    case 0x1000E000: g_dmac_ctrl = v; return;
    case 0x12001000: g_gs_csr &= ~(v & 0x1F); if (v & 0x200) g_gs_csr = 0x4000; return;
    case 0x12001010: g_gs_imr = v; return;
    case 0x1000F180: putchar((int)(v & 0xFF)); return;  // serial output
    }
    if (!((a >= 0x10000000 && a < 0x10010000) || (a >= 0x12000000 && a < 0x12002000))) {
        g_nothing_writes++;                              // no device there: the store is lost, as on the console
        return;
    }
    g_hw[a & ~3u] = v;
    if (a >= 0x10008000 && a < 0x1000E000) {
        bool chcr = a < 0x1000B000 ? (a & 0xFFF) == 0 : (a & 0x3FF) == 0;
        if (chcr && (v & 0x100)) {
            u32 ch = a < 0x1000B000 ? (a - 0x10008000) >> 12 : a < 0x1000C000 ? 3 + ((a - 0x1000B000) >> 10)
                   : a < 0x1000D000 ? 5 + ((a - 0x1000C000) >> 10) : 8 + ((a - 0x1000D000) >> 10);
            if (ch < 10) { dma_start(ch); deliver_if_enabled(); }
        }
        return;
    }
    rt_note(rt_fmt("hardware write 0x%08x", a & ~0xFu));
}

static u8* special_memory(u32& a, unsigned size) {
    // main memory seen again: uncached at 0x20000000, uncached "accelerated" at 0x30000000
    // (the game builds its display lists through that one), and the two kernel segments
    u32 top = a >> 28;
    if (top == 2 || top == 3) {
        u32 p = a & 0x0FFFFFFF;
        if (p <= RAM_SIZE - size) return g_ram + p;
    } else if (top == 8 || top == 9 || top == 0xA || top == 0xB) {
        u32 p = a & 0x1FFFFFFF;
        if (p <= RAM_SIZE - size) return g_ram + p;
        a = p;
    }
    if (a >= 0x70000000 && a <= 0x70004000 - size) return g_spr + (a - 0x70000000);
    if (a >= 0x11000000 && a <= 0x11001000 - size) return g_vu0.micro + (a - 0x11000000);
    if (a >= 0x11004000 && a <= 0x11005000 - size) return g_vu0.mem + (a - 0x11004000);
    if (a >= 0x11008000 && a <= 0x1100C000 - size) return g_vu1micro + (a - 0x11008000);
    if (a >= 0x1100C000 && a <= 0x11010000 - size) return g_vu1mem + (a - 0x1100C000);
    return nullptr;
}

// An access to an address where nothing is.  The game makes such accesses in ordinary play
// (Player_run 0x1ab7c0 reads a float through a track index it did not test,
// docs/spec/player-tick.md; a button pressed while the publisher's logo shows makes the
// allocator read 24 bytes below a null pointer, call site 0x1501b0).  The reference
// emulator answers such a read with 0xCC in every byte and drops such a store, and the
// game runs on; this machine does the same, so that it stays in step with a game played
// there, and counts them for the report.  `--opt strict-memory=1` stops the run instead
// (what this runtime did before: useful when looking for a fault of the translation).
static u64 g_nothing_loads, g_nothing_stores;
static bool g_strict_memory = false;
struct NothingSeen { u32 addr, site; unsigned size; u64 field; bool store; };
static std::vector<NothingSeen> g_nothing_seen;       // the first few, for the report
static void nothing_there(bool store, u32 addr, unsigned size) {
    if (g_strict_memory) rt_die("%s of %u bytes at 0x%08x, which is nothing", store ? "store" : "load", size, addr);
    (store ? g_nothing_stores : g_nothing_loads)++;
    if (g_nothing_seen.size() < 16) {
        for (auto& s : g_nothing_seen) if (s.addr == addr && s.site == g_site && s.store == store) return;
        g_nothing_seen.push_back({addr, g_site, size, g_fields, store});
    }
}

u64 rt_load(u32 addr, unsigned size) {
    u32 a = addr;
    if (u8* p = special_memory(a, size)) { u64 v = 0; memcpy(&v, p, size); return v; }
    if (a >= 0x10000000 && a < 0x14000000) return hw_read(a, size);
    if (a >= 0x1FC00000 && a < 0x20000000) return 0;
    nothing_there(false, addr, size);
    return 0xCCCCCCCCCCCCCCCCull >> (64 - 8 * (size > 8 ? 8 : size));
}
void rt_store(u32 addr, unsigned size, u64 value) {
    u32 a = addr;
    if (u8* p = special_memory(a, size)) { memcpy(p, &value, size); return; }
    if (a >= 0x10000000 && a < 0x14000000) { hw_write(a, size, value); return; }
    nothing_there(true, addr, size);
}
void rt_load128(u32 addr, u64* lo, u64* hi) {
    u32 a = addr;
    if (u8* p = special_memory(a, 16)) { memcpy(lo, p, 8); memcpy(hi, p + 8, 8); return; }
    if (a >= 0x10000000 && a < 0x14000000) { *lo = hw_read(a, 8); *hi = 0; return; }
    nothing_there(false, addr, 16);
    *lo = *hi = 0xCCCCCCCCCCCCCCCCull;
}
void rt_store128(u32 addr, u64 lo, u64 hi) {
    u32 a = addr;
    if (u8* p = special_memory(a, 16)) { memcpy(p, &lo, 8); memcpy(p + 8, &hi, 8); return; }
    if (a >= 0x10000000 && a < 0x14000000) {            // a quadword pushed into a FIFO by hand
        std::vector<u32> q(4);
        memcpy(q.data(), &lo, 8); memcpy(q.data() + 2, &hi, 8);
        rt_note(rt_fmt("128-bit store to FIFO 0x%08x", a));
        if (a == 0x10004000) { vif_stream(q, 0); if (g_hooks.video) g_hooks.video->vif0(q.data(), 4); }
        else if (a == 0x10005000) { vif_stream(q, 1); if (g_hooks.video) g_hooks.video->vif1(q.data(), 4); }
        else if (a == 0x10006000) { gif_stream(q.data(), 4); if (g_hooks.video) g_hooks.video->gif(q.data(), 4); }
        return;
    }
    nothing_there(true, addr, 16);
}

void rt_call(Ctx* c, u32 target) {
    if (target >= g_text_lo && target < g_text_hi && !(target & 3)) {
        RecompFn fn = g_table[(target - g_text_lo) >> 2];
        if (fn) { fn(c); return; }
    }
    rt_die("call to 0x%08x, which has no translation", target);
}
void rt_break(Ctx*, u32 pc, u32 code) { rt_die("BREAK %u at 0x%x", code, pc); }
void rt_trap(Ctx*, u32 pc, const char* what) { rt_die("%s at 0x%x", what, pc); }
void rt_unimpl(Ctx*, u32 pc, u32 word) { rt_die("untranslated instruction %08x at 0x%x", word, pc); }
void rt_eret(Ctx* c, u32 pc) {
    // return from exception: to ErrorEPC when the ERL bit is set, else to EPC
    u32 status = c->cop0[12];
    u32 target = (status & 4) ? c->cop0[30] : c->cop0[14];
    rt_mtc0(c, pc, 12, status & ~((status & 4) ? 4u : 2u));
    if (target != (u32)c->r[31]) rt_die("ERET at 0x%x returns to 0x%x, not to the caller", pc, target);
}
// The CPU's cycle counter.  The game seeds its random generators from it when an offline
// session starts, so a run that is to be compared with another machine's needs the values
// that machine read: --count-at <site>=<v1>,<v2>,... gives the reads at one code address
// their values in order; after the list, and everywhere else, the virtual clock answers.
static std::map<u32, std::vector<u32>> g_count_forced;
u32 rt_mfc0(Ctx* c, u32 pc, unsigned reg) {
    if (reg == 9) {
        auto forced = g_count_forced.find(pc);
        if (forced != g_count_forced.end() && !forced->second.empty()) {
            u32 value = forced->second.front();
            forced->second.erase(forced->second.begin());
            rt_note(rt_fmt("read of the CPU cycle counter at 0x%x answered with a given value", pc));
            return value;
        }
        rt_note(rt_fmt("read of the CPU cycle counter at 0x%x", pc));
        return (u32)now(c);
    }
    return c->cop0[reg];
}
void rt_mtc0(Ctx* c, u32, unsigned reg, u32 value) {
    u32 before = c->cop0[reg];
    c->cop0[reg] = value;
    // interrupts switched back on: what came in meanwhile is taken now
    if (reg == 12 && (value & 0x10001) == 0x10001 && (before & 0x10001) != 0x10001 && t_self && c == &t_self->ctx)
        deliver_if_enabled();
}

// ---- vector unit 0 from the main CPU -----------------------------------------------------
void rt_cop2(Ctx* c, u32 pc, u32 w) {
    u32 op = w >> 26, rs = (w >> 21) & 31, rt = (w >> 16) & 31, rd = (w >> 11) & 31;
    Vu0& v = g_vu0;
    if (op == 0x36 || op == 0x3E) {                     // LQC2 / SQC2 ft, offset(base)
        u32 addr = (u32)c->r[rs] + (u32)(s32)(s16)w;
        if (op == 0x36) {
            u64 lo, hi;
            if (addr <= RAM_SIZE - 16) { memcpy(&lo, g_ram + addr, 8); memcpy(&hi, g_ram + addr + 8, 8); }
            else rt_load128(addr, &lo, &hi);
            if (rt) { memcpy(&v.vf[rt][0], &lo, 8); memcpy(&v.vf[rt][2], &hi, 8); }
        } else {
            u64 lo, hi;
            memcpy(&lo, &v.vf[rt][0], 8); memcpy(&hi, &v.vf[rt][2], 8);
            if (addr <= RAM_SIZE - 16) { memcpy(g_ram + addr, &lo, 8); memcpy(g_ram + addr + 8, &hi, 8); }
            else rt_store128(addr, lo, hi);
        }
        return;
    }
    switch (rs) {
    case 1:                                             // QMFC2
        if (rt) { memcpy(&c->r[rt], &v.vf[rd][0], 8); memcpy(&c->rh[rt], &v.vf[rd][2], 8); }
        return;
    case 2:                                             // CFC2
        if (rt) c->r[rt] = rd < 16 ? (u64)v.vi[rd] : SX32(v.control[rd]);
        return;
    case 5:                                             // QMTC2
        if (rd) { memcpy(&v.vf[rd][0], &c->r[rt], 8); memcpy(&v.vf[rd][2], &c->rh[rt], 8); }
        return;
    case 6:                                             // CTC2
        if (rd == 0) return;
        if (rd < 16) v.vi[rd] = (u16)c->r[rt]; else v.control[rd] = (u32)c->r[rt];
        return;
    }
    if (rs >= 16 && (w & 63) == 0x38) {                 // VCALLMS
        vu0_run(v, (w >> 6) & 0x7FFF);
        return;
    }
    rt_die("COP2 instruction %08x at 0x%x is not implemented", w, pc);
}

// ---------------------------------------------------------------------------------------
// The renderer's back end.  gfx_dmaHandler(-1) starts sending a finished frame: eight
// lists of draw packets, texture uploads on the GIF channel and draw packets on VIF1,
// driven from then on by DMA and GS interrupts, and it signals a semaphore when the last
// list has gone.  This is the place where a native renderer takes the frame; headless,
// the frame is counted and reported as sent.  (Letting the original state machine run
// against the DMA model above works for four of the eight lists of the first frame and
// then waits forever for texture memory that only a real drawing GS frees.)
// ---------------------------------------------------------------------------------------
static u64 g_draw_frames, g_draw_packets, g_draw_textured;
static bool g_hle_renderer = false;
void fn_0016b998(Ctx* c) {
    if ((s32)c->r[4] != -1) { orig_0016b998(c); return; }
    u32 buffer = (g_ram[0x41B4D9] ^ 1) & 1;             // the buffer about to be sent
    bool taken = g_hooks.video && g_hooks.video->frame(g_draw_frames, buffer);
    if (!taken && !g_hle_renderer) { orig_0016b998(c); return; }
    g_ram[0x41B4D9] ^= 1;
    for (u32 list = 0; list < 8; list++) {
        u32 head = W(0x6F4070 + (buffer * 8 + list) * 4);
        u32 node = head && head < RAM_SIZE - 16 ? W(head + 0xC) : 0;
        for (int guard = 0; node && node < RAM_SIZE - 16 && guard < 100000; guard++) {
            g_draw_packets++;
            if (W(node + 8)) g_draw_textured++;
            node = W(node + 0xC);
        }
    }
    g_draw_frames++;
    g_ram[0x6F4130] = 8;                                // all eight lists done
    W(0x41B4DC) = 0;                                    // no channel busy
    W(0x41B4E0) = 2;
    g_ram[0x41B4E4] = 1;                                // completion reported
    g_ram[0x41B4D8] = 0;                                // not sending
    u32 id = W(0x6E4060);
    if (sem_ok(id)) { if (W(sem(id) + S_WAITERS)) wake_sema_waiter(id); else W(sem(id) + S_COUNT)++; }
    c->r[2] = 0;
}

// ---------------------------------------------------------------------------------------
// Films.  movie_update 0x3205ec decodes one picture per frame with Sony's MPEG library,
// which works through the Image Processing Unit (commands at 0x10002000, data through DMA
// channels 3 and 4).  This machine has no such unit: a command is never answered and the
// library polls for the answer for ever.  Until there is one, a film ends at its first
// update - the game goes on as it does when a film has played to its end (g_movieFinished
// 0x50602c, which splash_introMovie 0x321788 waits for).  `--opt films=original` runs the
// game's own code instead (it then hangs in the first film unless a button skips it first).
// ---------------------------------------------------------------------------------------
static u64 g_films_skipped;
void fn_003205ec(Ctx* c) {
    static int original = -1;
    if (original < 0) { const char* o = rt_option("films"); original = o && !strcmp(o, "original"); }
    if (original) { orig_003205ec(c); return; }
    if (!g_ram[0x50602C]) g_films_skipped++;
    g_ram[0x50602C] = 1;
    c->r[2] = 1;
}

// ---------------------------------------------------------------------------------------
// Level music and fast loading.  mainloop_pollAmbientAudio 0x322520 runs once per displayed
// frame and counts the word at 0x50608c down; a level load leaves 60 in it.  When it
// reaches 0 it is set to a random 4 to 6 minutes, and the level's music is started -
// unless stream_queuedFlags(2) 0x216310 shows a music entry (flag 0x20) active or queued
// on the music stream; then nothing is started until the next 4 to 6 minutes are over.
// On a console the level load takes longer (6 s for the first level) than the fade the
// level change put on the old music (stop markers in the stream's queue; 3.07 s from full
// volume), so at frame 60 of the level the stream is free.  With this machine's fast I/O
// the load takes 2.6 s, the title music is still fading at frame 60, and the first level
// stays without music for minutes (docs/issues/native-sound.md 4.5, native-app.md).
//
// The game's rule is left as it is; the countdown is held at its last step while the music
// that is in the way is one a queued stop marker is about to end, so that the start falls
// on the first frame the stream is free: what the console's timing gives.  One draw from
// the generator at 0x404460 per start, as there.  `--opt music-start=original` switches
// the hold off (the game then behaves exactly as its code says, also under fast loading).
// ---------------------------------------------------------------------------------------
static u64 g_music_holds;
void fn_00322520(Ctx* c) {
    static int original = -1;
    if (original < 0) { const char* o = rt_option("music-start"); original = o && !strcmp(o, "original"); }
    if (!original && W(0x50608C) == 1) {
        const u32 stream = 0x876C10 + 2 * 0x1C4;            // g_streams[2]: music
        bool music_active = W(stream + 0x14) != 0 && (W(stream + 0x20) & 0x20);
        bool stop_queued = false;
        u32 count = W(stream + 0x1C0);
        for (u32 k = 0; k < count && k < 8; k++)
            if ((W(stream + 0x6C + k * 0x30) & 2) && !g_ram[stream + 0x40 + k * 0x30]) stop_queued = true;
        if (music_active && stop_queued) { W(0x50608C) = 2; g_music_holds++; }
    }
    orig_00322520(c);
}

// ---------------------------------------------------------------------------------------
// Watches, in the format of the rig's tick log (expressions and types: script.cpp)
// ---------------------------------------------------------------------------------------
struct Watch { std::string name, expr, type; };
static std::vector<Watch> g_watches;
static FILE* g_log;
static bool g_log_fields = false;                 // one row per vertical blank instead of per displayed frame
static u64 g_frame;
static double g_seconds = 0;
static u64 g_dump_frame = ~0ull;
static std::string g_dump_path;
static std::chrono::steady_clock::time_point g_start_time;
static u64 g_fields_wanted = ~0ull;
static bool g_script_given = false;
static int g_exit_code = 0;

static void log_row(u64 number) {
    fprintf(g_log, "%llu", (unsigned long long)number);
    for (auto& w : g_watches) fprintf(g_log, "\t%s", script_value(script_eval(w.expr), w.type).c_str());
    fprintf(g_log, "\n");
}

[[noreturn]] static void report_and_exit() {
    if (rt_at_finish) { void (*fn)() = rt_at_finish; rt_at_finish = nullptr; fn(); }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_start_time).count();
    printf("frames=%llu wall=%.3fs: %.0f frames per second, %.1fx real time at 59.94; fields=%llu units=%llu\n",
           (unsigned long long)g_frame, wall, g_frame / wall, g_frame / wall / 59.94, (unsigned long long)g_fields,
           (unsigned long long)g_units);
    printf("VU0: %llu microprogram calls, %llu instructions\n", (unsigned long long)g_vu0.calls, (unsigned long long)g_vu0.instructions);
    for (int ch = 0; ch < 10; ch++)
        if (g_dma_starts[ch]) printf("DMA channel %d: %llu transfers, %llu quadwords (discarded)\n", ch,
                                     (unsigned long long)g_dma_starts[ch], (unsigned long long)g_dma_qwords[ch]);
    printf("graphics data walked: %llu GIF packets, %llu GS register writes, %llu vertices, %llu primitives, "
           "%llu FINISH, %llu SIGNAL; VIF1: %llu UNPACK, %llu microprogram starts (VU1 not run)\n",
           (unsigned long long)g_gif_packets, (unsigned long long)g_gs_writes, (unsigned long long)g_gs_vertices,
           (unsigned long long)g_gs_prims, (unsigned long long)g_gs_finish, (unsigned long long)g_gs_signal,
           (unsigned long long)g_vif_unpacks, (unsigned long long)g_vif_mscal);
    printf("renderer back end: %llu frames handed over, %llu draw packets (%llu textured), %.0f per frame\n",
           (unsigned long long)g_draw_frames, (unsigned long long)g_draw_packets, (unsigned long long)g_draw_textured,
           g_draw_frames ? (double)g_draw_packets / g_draw_frames : 0.0);
    printf("stores to addresses where no device is (lost): %llu\n", (unsigned long long)g_nothing_writes);
    if (g_music_holds) printf("level music: the start countdown was held for %llu frames while the old music faded out\n", (unsigned long long)g_music_holds);
    if (g_films_skipped) printf("films ended at their first picture (no Image Processing Unit): %llu\n", (unsigned long long)g_films_skipped);
    printf("accesses to addresses where nothing is: %llu loads (answered with 0xCC bytes), %llu stores (dropped)\n",
           (unsigned long long)g_nothing_loads, (unsigned long long)g_nothing_stores);
    for (auto& n : g_nothing_seen)
        printf("  %s of %u bytes at 0x%08x, last call site 0x%x, first at field %llu\n", n.store ? "store" : "load", n.size, n.addr, n.site,
               (unsigned long long)n.field);
    printf("what the game asked the platform for:\n");
    for (auto& kv : g_counts) printf("  %10llu  %s\n", (unsigned long long)kv.second, kv.first.c_str());
    iop_report();
    sound_report();
    if (g_log) fclose(g_log);
    host::quit(g_exit_code);
}
void rt_finish(int code) { g_exit_code = code; report_and_exit(); }

static u64 g_script_offset;                       // the script's frame numbers run this far ahead of the blank count
static void on_vblank() {
    script_vblank(g_fields + g_script_offset);
    iop_vblank(g_fields);
    sound_vblank();
    if (g_hooks.video) g_hooks.video->vblank((g_gs_csr >> 13) & 1, g_fields);
    if (g_log && g_log_fields) log_row(g_fields);
    if (g_fields >= g_fields_wanted) report_and_exit();
    if (g_script_given && !script_active() && g_fields_wanted == ~0ull && g_frames_wanted == ~0ull) report_and_exit();
}



void (*rt_frame_hook)(Ctx* c, int phase);
void (*rt_dma_tag)(u32 tag_address, std::vector<u32>& stream);
void fn_0019d8b0(Ctx* c) {                              // gfx_beginFrame: once per displayed frame
    if (g_log && !g_log_fields) log_row(g_frame);
    if (g_frame == g_dump_frame) {
        FILE* f = fopen(g_dump_path.c_str(), "wb");
        if (f) { fwrite(g_ram, 1, RAM_SIZE, f); fclose(f); }
    }
    if (g_frame >= g_frames_wanted) report_and_exit();
    g_frame++;
    if (rt_frame_hook) rt_frame_hook(c, 0);
    orig_0019d8b0(c);
    if (rt_frame_hook) rt_frame_hook(c, 1);
}

// ---------------------------------------------------------------------------------------
static bool read_file(const char* path, u8* into, size_t size) {
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    size_t got = fread(into, 1, size, f);
    fclose(f);
    return got == size;
}

// The words of a patch set the translation was made with (recomp.py --pnach writes
// patches.cpp into the generated directory; a translation without patches has none).
__attribute__((weak)) unsigned recomp_patches(const u32 (**words)[2]) { *words = nullptr; return 0; }

static bool load_elf(const char* path, u32* entry) {
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<u8> d(size);
    bool ok = fread(d.data(), 1, size, f) == (size_t)size;
    fclose(f);
    if (!ok) return false;
    u32 phoff; u16 phentsize, phnum;
    memcpy(entry, &d[24], 4);
    memcpy(&phoff, &d[28], 4); memcpy(&phentsize, &d[42], 2); memcpy(&phnum, &d[44], 2);
    for (unsigned i = 0; i < phnum; i++) {
        u32 h[6];
        memcpy(h, &d[phoff + i * phentsize], 24);
        if (h[0] == 1 && h[2] + h[4] <= RAM_SIZE) memcpy(g_ram + h[2], &d[h[1]], h[4]);
    }
    return true;
}

static std::map<std::string, std::string> g_options;
const char* rt_option(const char* key) {
    auto it = g_options.find(key);
    return it == g_options.end() ? nullptr : it->second.c_str();
}

namespace rta {
uint8_t* memory() { return g_ram; }
uint8_t* scratchpad() { return g_spr; }
uint8_t* vu1_micro() { return g_vu1micro; }
uint8_t* vu1_data() { return g_vu1mem; }

static void usage() {
    fprintf(stderr,
        "rta_native boot --elf SLUS_209.73 --disc <image.iso> [options]\n"
        "rta_native resume --ram <image> [--spr <image>] --regs <file> --entry <hex> [options]\n"
        "  --disc <image>        ISO 9660 image of your disc, read in place (default: $RTA_DISC)\n"
        "  --card <dir>          memory cards: <dir>/mc0 and <dir>/mc1, one host directory per card\n"
        "                        (the layout of the Play! emulator's <data>/vfs); default ./rta-card\n"
        "  --script <file>       scripted input and conditions (the rig's script language)\n"
        "  --do \"<command>\"      one more script command; repeatable\n"
        "  --sym <file.tsv>      symbol file (hex address, tab, name) for expressions; repeatable\n"
        "  --watch <name=expr:type>, --watch-file <file>, --log <out.tsv>\n"
        "                        values logged once per displayed frame (entry of gfx_beginFrame);\n"
        "                        --log-fields logs once per vertical blank instead\n"
        "  --frames <n>          stop after n displayed frames; --fields <n>: after n vertical blanks\n"
        "  --dump-at <frame> <file>   write main memory at a displayed frame\n"
        "  --emulator-timing     the I/O processor answers after the delays the Play! emulator uses\n"
        "                        (default: as fast as the game's own protocol allows)\n"
        "  --count-at <hex site>=<hex>[,<hex>...]   values for the reads of the CPU cycle counter at one\n"
        "                        code address, in order (the offline session seeds: 3229f0, 322a00)\n"
        "  --adopt               resume: the services of this runtime answer the clients the image had\n"
        "                        bound in the emulator (disc, memory card, sound, ...); without it their\n"
        "                        calls are left unanswered, which is enough for a run without input\n"
        "  --script-offset <n>   the script's frame numbers start at n instead of 0 (a script written\n"
        "                        for the rig, which had run n frames when the resumed image was taken)\n"
        "  --hle-renderer        do not send draw data through DMA; count and report frames as sent\n"
        "  --opt key=value       an option for a module linked with the runtime (rt_option); repeatable\n"
        "  --arg <text>          one argument for the game's main(), after the program's name; repeatable\n"
        "                        (without it main() gets no arguments at all, as in the compared runs)\n"
        "  --seconds <s>         stop after s seconds of wall time and say where the game is\n"
        "  --verbose, --trace <n>\n");
}

int run(int argc, char** argv, const Hooks& hooks) {
    g_hooks = hooks;
    if (argc < 2) { usage(); return 2; }
    std::string mode = argv[1], ram, spr, regs, elf, log_path, script;
    std::vector<std::string> extra_commands;
    IopOptions iop;
    bool adopt = false;
    if (const char* disc = getenv("RTA_DISC")) iop.disc = disc;
    iop.card_root = "rta-card";
    u32 entry = 0;
    auto add_watch = [](std::string s) {
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
        if (s.empty() || s[0] == '#') return;
        size_t eq = s.find('='), colon = s.rfind(':');
        if (colon == std::string::npos) rt_die("bad watch %s", s.c_str());
        if (eq == std::string::npos || eq > colon) g_watches.push_back({s.substr(0, colon), s.substr(0, colon), s.substr(colon + 1)});
        else g_watches.push_back({s.substr(0, eq), s.substr(eq + 1, colon - eq - 1), s.substr(colon + 1)});
    };
    for (int i = 2; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string { if (i + 1 >= argc) rt_die("%s needs a value", a.c_str()); return argv[++i]; };
        if (a == "--ram") ram = next();
        else if (a == "--spr") spr = next();
        else if (a == "--regs") regs = next();
        else if (a == "--elf") elf = next();
        else if (a == "--entry") entry = (u32)strtoul(next().c_str(), nullptr, 16);
        else if (a == "--frames") g_frames_wanted = strtoull(next().c_str(), nullptr, 0);
        else if (a == "--fields") g_fields_wanted = strtoull(next().c_str(), nullptr, 0);
        else if (a == "--watch") add_watch(next());
        else if (a == "--watch-file") {
            std::string path = next();
            FILE* f = fopen(path.c_str(), "r");
            if (!f) rt_die("cannot read %s", path.c_str());
            char line[512];
            while (fgets(line, sizeof(line), f)) add_watch(line);
            fclose(f);
        }
        else if (a == "--log") log_path = next();
        else if (a == "--log-fields") g_log_fields = true;
        else if (a == "--dump-at") { g_dump_frame = strtoull(next().c_str(), nullptr, 0); g_dump_path = next(); }
        else if (a == "--verbose") g_rt_verbose = true;
        else if (a == "--seconds") g_seconds = atof(next().c_str());
        else if (a == "--hle-renderer") g_hle_renderer = true;
        else if (a == "--trace") g_trace_left = atoi(next().c_str());
        else if (a == "--disc") iop.disc = next();
        else if (a == "--card") iop.card_root = next();
        else if (a == "--emulator-timing") iop.emulator_timing = true;
        else if (a == "--arg") g_boot_args.push_back(next());
        else if (a == "--adopt") adopt = true;
        else if (a == "--script-offset") g_script_offset = strtoull(next().c_str(), nullptr, 0);
        else if (a == "--count-at") {
            std::string spec = next();
            size_t eq = spec.find('=');
            if (eq == std::string::npos) rt_die("--count-at wants <hex address>=<hex value>[,<hex value>...]");
            std::vector<u32>& values = g_count_forced[(u32)strtoul(spec.substr(0, eq).c_str(), nullptr, 16)];
            for (size_t at = eq + 1; at < spec.size();) {
                size_t comma = spec.find(',', at);
                values.push_back((u32)strtoul(spec.substr(at, comma == std::string::npos ? std::string::npos : comma - at).c_str(), nullptr, 16));
                if (comma == std::string::npos) break;
                at = comma + 1;
            }
        }
        else if (a == "--script") script = next();
        else if (a == "--do") extra_commands.push_back(next());
        else if (a == "--sym") script_add_symbols(next().c_str());
        else if (a == "--opt") {
            std::string kv = next();
            size_t eq = kv.find('=');
            g_options[kv.substr(0, eq)] = eq == std::string::npos ? "" : kv.substr(eq + 1);
        }
        else if (a == "--help") { usage(); return 0; }
        else rt_die("unknown option %s", a.c_str());
    }
    g_ram = (u8*)calloc(RAM_SIZE + 4096, 1);
    g_text_lo = 0xFFFFFFFFu; g_text_hi = 0;
    for (unsigned i = 0; i < g_recomp_entry_count; i++) {
        u32 a = g_recomp_entries[i].addr;
        if (a < g_text_lo) g_text_lo = a;
        if (a + 4 > g_text_hi) g_text_hi = a + 4;
    }
    g_table = (RecompFn*)calloc((g_text_hi - g_text_lo) >> 2, sizeof(RecompFn));
    for (unsigned i = 0; i < g_recomp_entry_count; i++)
        g_table[(g_recomp_entries[i].addr - g_text_lo) >> 2] = g_recomp_entries[i].fn;
    memset(&g_vu0, 0, sizeof(g_vu0));
    g_vu0.vf[0][3] = 1.0f;
    memset(&g_irq_ctx, 0, sizeof(g_irq_ctx));
    g_irq_ctx.fcr31 = 0x01000001;

    if (!script.empty() && !script_load(script.c_str())) rt_die("cannot read %s", script.c_str());
    for (auto& line : extra_commands) script_add_command(line);
    g_script_given = !script.empty() || !extra_commands.empty();
    if (!log_path.empty()) {
        g_log = fopen(log_path.c_str(), "w");
        if (!g_log) rt_die("cannot write %s", log_path.c_str());
        fprintf(g_log, "frame");
        for (auto& w : g_watches) fprintf(g_log, "\t%s", w.name.c_str());
        fprintf(g_log, "\n");
    }
    if (const char* strict = rt_option("strict-memory")) g_strict_memory = atoi(strict) != 0;
    iop_init(iop);

    std::unique_lock<std::mutex> lock(g_big);
    GThread* main_thread = nullptr;
    if (mode == "resume") {
        if (ram.empty() || regs.empty() || !entry) rt_die("resume needs --ram, --regs and --entry");
        if (!read_file(ram.c_str(), g_ram, RAM_SIZE)) rt_die("cannot read %s", ram.c_str());
        if (!spr.empty() && !read_file(spr.c_str(), g_spr, sizeof(g_spr))) rt_die("cannot read %s", spr.c_str());
        u32 current = W(ST_BASE + ST_CURRENT);
        if (!thr_ok(current)) rt_die("the image's kernel state names no current thread");
        main_thread = make_thread(current, entry);
        FILE* f = fopen(regs.c_str(), "r");
        if (!f) rt_die("cannot read %s", regs.c_str());
        char name[32];
        unsigned value;
        static const char* names[32] = {"zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5",
                                        "t6", "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1",
                                        "gp", "sp", "fp", "ra"};
        while (fscanf(f, "%31s %x", name, &value) == 2)
            for (int n = 1; n < 32; n++)
                if (!strcmp(name, names[n])) main_thread->ctx.r[n] = SX32(value);
        fclose(f);
        g_gp = (u32)main_thread->ctx.r[28];
        // every other thread of the image stays as it is: its context is in guest memory
        // at an arbitrary instruction, which translated code cannot be entered at
        // -- unless it sleeps in a kernel call (its saved pc is the `jr $ra` of the call's
        // wrapper) and the return address has an entry; then it continues there.
        u32 resumable = 0;
        for (u32 t = 1; t <= MAX_THREAD; t++) {
            if (!W(thr(t) + T_VALID) || t == current) continue;
            u32 context = W(thr(t) + T_CONTEXT), epc = W(thr(t) + T_EPC), status = W(thr(t) + T_STATUS);
            u32 ra = context && context < RAM_SIZE - 0x2A0 ? W(context + 31 * 16) : 0;
            bool ok = status != TH_ZOMBIE && epc >= g_text_lo && epc < g_text_hi && W(epc) == 0x03E00008u
                      && ra >= g_text_lo && ra < g_text_hi && !(ra & 3) && g_table[(ra - g_text_lo) >> 2];
            if (!ok) { if (status != TH_ZOMBIE) g_foreign.insert(t); continue; }
            GThread* g = make_thread(t, ra);
            for (int n = 1; n < 32; n++) { memcpy(&g->ctx.r[n], g_ram + context + n * 16, 8); memcpy(&g->ctx.rh[n], g_ram + context + n * 16 + 8, 8); }
            memcpy(g->ctx.f, g_ram + context + 0x200, 128);
            g->ctx.fcr31 = W(context + 0x280);
            g->ctx.acc = W(context + 0x284);
            start_host(g);
            resumable++;
            printf("thread %u of the image continues at 0x%x (procedure 0x%x, status %u)\n", t, ra, W(thr(t) + T_PROC), status);
        }
        // the image's VU0 microprogram memory is not in main memory: load the one program
        // the executable has (77 instructions at 0x3e5c50, to VU address 0)
        memcpy(g_vu0.micro, g_ram + 0x3E5C50, 77 * 8);
        // The interrupt masks and timer modes live in hardware registers, which the image
        // does not carry: every interrupt cause and DMA channel the image has a handler
        // for is enabled, timer 0 counts as the game's engine_init sets it.
        for (u32 h = 0; h < MAX_HANDLER; h++) {
            if (W(INTC_BASE + h * H_SIZE)) g_intc_mask |= 1u << W(INTC_BASE + h * H_SIZE + H_CAUSE);
            if (W(DMAC_BASE + h * H_SIZE)) g_dmac_stat |= 0x10000u << W(DMAC_BASE + h * H_SIZE + H_CAUSE);
        }
        g_intc_mask &= ~((1u << 9) | (1u << 10) | (1u << 11) | (1u << 12));     // no timer interrupts
        g_gs_imr = 0x7C00;                              // SIGNAL and FINISH reach the game
        g_timers[0].mode = 0x82;
        if (adopt) iop_adopt();
        printf("resumed: thread %u runs from 0x%x (sp 0x%x); %u other threads continue, %zu cannot\n", current, entry,
               (u32)main_thread->ctx.r[29], resumable, g_foreign.size());
    } else if (mode == "boot") {
        if (elf.empty()) rt_die("boot needs --elf");
        if (!load_elf(elf.c_str(), &entry)) rt_die("cannot load %s", elf.c_str());
        {
            // the translated code already is the patched code; memory has to read the same
            const u32 (*words)[2] = nullptr;
            unsigned count = recomp_patches(&words);
            for (unsigned k = 0; k < count; k++) if (words[k][0] <= RAM_SIZE - 4) W(words[k][0]) = words[k][1];
            if (count) printf("patched: %u words of the fix set this translation was made with\n", count);
        }
        W(thr(1) + T_VALID) = 1;
        W(thr(1) + T_STATUS) = TH_RUNNING;
        link_thread(1);
        W(ST_BASE + ST_CURRENT) = 1;
        main_thread = make_thread(1, entry);
        printf("booting: entry 0x%x\n", entry);
    } else rt_die("unknown mode %s", mode.c_str());

    say_arithmetic();
    g_start_time = std::chrono::steady_clock::now();
    g_cur = main_thread;
    start_host(main_thread);
    lock.unlock();
    main_thread->cv.notify_one();
    for (;;) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_start_time).count();
        if (g_seconds > 0 && wall > g_seconds) {        // diagnostics: where is it after this long?
            printf("stopped after %.0f s of wall time; last call site 0x%x, field %llu\n", wall, g_site, (unsigned long long)g_fields);
            for (u32 t = 1; t <= MAX_THREAD; t++)
                if (W(thr(t) + T_VALID) && W(thr(t) + T_STATUS) != TH_ZOMBIE)
                    printf("  thread %u: status %u, semaphore %u, procedure 0x%x, priority %u, last call site 0x%x\n", t, W(thr(t) + T_STATUS),
                           W(thr(t) + T_SEMA), W(thr(t) + T_PROC), W(thr(t) + T_PRI),
                           g_threads.count(t) ? (g_cur == g_threads[t] ? g_site : g_threads[t]->site) : 0);
            printf("  INTC stat %x mask %x, DMAC stat %x, GS CSR %x IMR %x, main thread status register %x\n", g_intc_stat, g_intc_mask,
                   g_dmac_stat, g_gs_csr, g_gs_imr, main_thread->ctx.cop0[12]);
            // return addresses found on the stack of the thread that was running: words that
            // point just behind a call instruction (not a proof of the call chain, a guide)
            if (g_cur) {
                printf("  stack of thread %u (sp 0x%x), possible return addresses:", g_cur->id, (u32)g_cur->ctx.r[29]);
                u32 sp = (u32)g_cur->ctx.r[29] & 0x1FFFFFF;
                for (u32 a = sp, found = 0; a < sp + 0x1000 && a < RAM_SIZE - 4 && found < 24; a += 4) {
                    u32 v = W(a);
                    if (v < g_text_lo + 8 || v >= g_text_hi || (v & 3)) continue;
                    u32 call = W(v - 8);
                    if ((call >> 26) == 3 || (call & 0xFC00003F) == 9) { printf(" %x", v); found++; }
                }
                printf("\n");
            }
            g_exit_code = 4;
            report_and_exit();
        }
        if (main_thread->finished) { printf("the main thread ended\n"); report_and_exit(); }
    }
}
}  // namespace rta
