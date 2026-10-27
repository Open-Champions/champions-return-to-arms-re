// Exercises the real kernel/IOP with authored procedures and zeroed RAM. No game,
// window, renderer or sound device. run.py also builds this against a baseline revision.
#ifndef RTA_RUNTIME_SOURCE
#define RTA_RUNTIME_SOURCE "../runtime.cpp"
#endif
#include RTA_RUNTIME_SOURCE

#include <cassert>

void orig_0016b998(Ctx*) { assert(false); }
void orig_0019d8b0(Ctx*) { assert(false); }
void orig_003205ec(Ctx*) { assert(false); }
void orig_00322520(Ctx*) { assert(false); }

static constexpr u32 ROOT_PC = 0x100000, WORKER_PC = ROOT_PC + 4, CALLBACK_PC = ROOT_PC + 8;
static constexpr u32 PARAM = 0x400000, CLIENT = PARAM + 0x100, REPLY = PARAM + 0x200;
static constexpr u32 COMPLETIONS = PARAM + 0x300;
static u32 semaphore;
static unsigned rounds = 64;
static const char* snapshot;
static std::vector<u64> trace;

static u32 syscall(Ctx* c, u32 number, u32 a0 = 0, u32 a1 = 0) {
    assert(g_cur == t_self);
    c->r[3] = number;
    c->r[4] = a0;
    c->r[5] = a1;
    rt_syscall(c, ROOT_PC);
    return (u32)c->r[2];
}

static void mark(u32 event) {
    assert(g_cur == t_self);
    trace.push_back(event);
    trace.push_back(rt_cycles());
}

static void callback(Ctx* c) {
    assert(g_in_irq);
    assert(c->r[4] == semaphore);
    W(COMPLETIONS)++;
    rt_signal_sema(semaphore);
}

static void worker(Ctx* c) {
    mark(1);
    assert(syscall(c, 0x44, semaphore) == semaphore); // wait for the root's signal
    mark(2);
    rt_sleep(c, usec_to_cycles(50));
    mark(3);
    // Root may suspend this wait; it must not return until ResumeThread.
    assert(W(thr(t_self->id) + T_STATUS) == TH_RUNNING);
    syscall(c, 0x33, 1);                           // wake the root's SleepThread
    mark(4);
    c->r[31] = 0;                                  // return from the authored procedure
}

static void root(Ctx* c) {
    W(PARAM + 4) = 1;
    semaphore = syscall(c, 0x40, PARAM);
    assert(sem_ok(semaphore));
    // Signal before wait, and wake before sleep: neither notification may be lost.
    syscall(c, 0x42, semaphore);
    syscall(c, 0x44, semaphore);
    syscall(c, 0x33, 1);
    syscall(c, 0x32);
    for (unsigned n = 0; n < rounds; n++) {
        W(PARAM + 4) = WORKER_PC;
        W(PARAM + 8) = 0x200000;
        W(PARAM + 12) = 0x1000;
        W(PARAM + 16) = 0;
        W(PARAM + 20) = 10;                         // higher priority than root
        u32 id = syscall(c, 0x20, PARAM);
        assert(id == 2);
        syscall(c, 0x22, id, n);
        assert(W(thr(id) + T_STATUS) == TH_WAITING);
        assert(W(sem(semaphore) + S_WAITERS) == 1);
        syscall(c, 0x42, semaphore);
        assert(W(thr(id) + T_SEMA) == NO_SEMA);
        if (n & 1) {
            syscall(c, 0x37, id);
            rt_sleep(c, usec_to_cycles(100));
            assert(W(thr(id) + T_STATUS) == TH_SUSPENDED);
            syscall(c, 0x39, id);
        }
        syscall(c, 0x32);
        assert(g_threads[id]->finished);
        assert(W(thr(id) + T_STATUS) == TH_ZOMBIE);
        assert(W(sem(semaphore) + S_WAITERS) == 0);
        assert(W(ST_BASE + ST_THREADQ) == 1);
        assert(W(thr(1) + T_NEXT) == 0);
        syscall(c, 0x21, id);                       // reuse the guest slot next round
        mark(5);
    }

    // Real boot RPC entry points: init, blocking bind, blocking call, async completion.
    fn_00355d68(c);
    c->r[4] = CLIENT; c->r[5] = 0x80000003; c->r[6] = 0;
    fn_00356510(c);
    assert(W(CLIENT + 0x24) != 0);
    auto rpc = [&](bool async) {
        c->r[4] = CLIENT; c->r[5] = 6; c->r[6] = async;
        c->r[7] = 0; c->r[8] = 0; c->r[9] = REPLY; c->r[10] = 4;
        c->r[11] = async ? CALLBACK_PC : 0;
        W((u32)c->r[29]) = semaphore;
        fn_003566f0(c);
        assert(c->r[2] == 0);
        assert(W(REPLY) > 0);
    };
    rpc(false);
    rpc(true);
    assert(W(COMPLETIONS) == 0);
    syscall(c, 0x44, semaphore);
    assert(W(COMPLETIONS) == 1);
    assert(W(W(CLIENT) + 0x10) == 0);

    // SIF status handshake: the IOP's reply must wait for the virtual-clock event.
    W(PARAM) = PARAM + 0x40; W(PARAM + 4) = 0x1000;
    W(PARAM + 8) = 16; W(PARAM + 12) = 1;
    W(PARAM + 0x48) = 0x80000001;
    assert(iop_sif_set_dma(PARAM, 1) == 1);
    assert(W(0x8ef2c4) == 0);
    rt_sleep(c, usec_to_cycles(100));
    assert(W(0x8ef2c4) == 1);
    assert(g_later.empty());
    assert(g_host_threads == 1);
    assert(g_host_threads_made == rounds + 1);
    mark(6);

    FILE* f = fopen(snapshot, "wb");
    assert(f);
    assert(fwrite(g_ram, 1, RAM_SIZE, f) == RAM_SIZE);
    assert(fwrite(trace.data(), sizeof(u64), trace.size(), f) == trace.size());
    assert(fclose(f) == 0);
    printf("PASS: %u thread starts, semaphore/sleep/suspend handoffs, RPC and SIF handshake; %zu trace words\n",
           rounds, trace.size());
    host::quit(0);                                  // same no-destructor exit as the runtime
}

const RecompEntry g_recomp_entries[] = {{ROOT_PC, root}, {WORKER_PC, worker}, {CALLBACK_PC, callback}};
const unsigned g_recomp_entry_count = 3;

int main(int argc, char** argv) {
    assert(argc == 4);
    snapshot = argv[2];
    g_ram = (u8*)calloc(RAM_SIZE + 4096, 1);
    assert(g_ram);
    g_text_lo = ROOT_PC; g_text_hi = CALLBACK_PC + 4;
    g_table = (RecompFn*)calloc(3, sizeof(RecompFn));
    for (auto& e : g_recomp_entries) g_table[(e.addr - g_text_lo) / 4] = e.fn;
    IopOptions opt; opt.card_root = argv[3];
    iop_init(opt);
    std::unique_lock<std::mutex> lock(g_big);
    GThread* main = make_thread(1, ROOT_PC);
    W(thr(1) + T_VALID) = 1; W(thr(1) + T_STATUS) = TH_RUNNING; W(thr(1) + T_PRI) = 20;
    main->ctx.r[29] = 0x300000;
    link_thread(1);
    g_cur = main;
    std::string which = argv[1];
    if (which == "valid") {
        start_host(main);
        lock.unlock();
        // Bounded externally by run.py; the worker exits the process after its assertions.
        for (;;) host::sleep_us(10000);
    }
    t_self = main;
    if (which == "last-slot") {
        for (u32 id = 1; id <= MAX_THREAD; id++) {
            W(thr(id) + T_NEXT) = id < MAX_THREAD ? id + 1 : 0;
            W(thr(id) + T_STATUS) = TH_SLEEPING;
        }
        W(thr(256) + T_STATUS) = TH_RUNNING;
        assert(pick_thread() == 256);
        unlink_thread(256);
        assert(W(thr(255) + T_NEXT) == 0);
        assert(pick_thread() == 0);
        return 0;
    }
    // Deliberately damaged synthetic queues: this reproduces the fault mechanism,
    // not the unknown writer that damaged the historical game's queue.
    if (which == "bad-head") W(ST_BASE + ST_THREADQ) = 0xccdbdc;
    else {
        W(ST_BASE + ST_THREADQ) = 2;
        W(thr(2) + T_NEXT) = which == "cycle" ? 2 : 0xccdbdc;
    }
    if (which == "bad-pick") pick_thread();
    else if (which == "bad-link") link_thread(1);
    else if (which == "bad-rotate") syscall(&main->ctx, 0x2b, 99);
    else rt_sleep(&main->ctx, usec_to_cycles(50));
    assert(!"damaged queue was not rejected");
}
