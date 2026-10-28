// The production handoff, driven by authored commands only. No game or physical pad.
#include "../lib/rtag.h"
#include "../lib/rumble_state.h"
#include <atomic>
#include <cstdio>
#include <thread>
#include <type_traits>

static_assert(RTAG_API_VERSION == 6, "optional handoff must not change the interface version");
static_assert(std::is_same<decltype(&rtag_rumble), int (*)(int, uint8_t*, uint8_t*, uint64_t*)>::value,
              "C ABI uses raw motor bytes and caller-owned output pointers");
static int checks = 0, failures = 0;
static void check(bool pass, const char* label) {
    ++checks;
    if (!pass) { ++failures; std::printf("FAIL %s\n", label); }
}
struct Snapshot { uint8_t small = 99, large = 99; uint64_t generation = 99; };
static Snapshot read(const rtag_detail::RumbleState& state, int port, int* result = nullptr) {
    Snapshot out;
    const int got = state.read(port, &out.small, &out.large, &out.generation);
    if (result) *result = got;
    return out;
}
static bool neutral(const Snapshot& s) { return s.small == 0 && s.large == 0; }
int main() {
    rtag_detail::RumbleState state;
    int valid = 0;
    auto a = read(state, 0, &valid);
    check(valid == 1 && neutral(a) && a.generation == 0, "first port starts neutral");
    auto b = read(state, 1, &valid);
    check(valid == 1 && neutral(b) && b.generation == 0, "second port starts independently neutral");
    for (int port : {-1, 2, 100}) {
        a = read(state, port, &valid);
        check(valid == 0 && neutral(a) && a.generation == 0, "invalid port clears caller output");
    }
    check(state.read(0, nullptr, nullptr, nullptr) == 1, "optional output pointers");
    state.command(0, 1, 128);
    a = read(state, 0); b = read(state, 1);
    check(a.small == 1 && a.large == 128 && a.generation == 1, "small on/off byte and half strong amplitude retained");
    check(neutral(b) && b.generation == 0, "first port command does not vibrate second port");
    state.command(1, 255, 47);
    b = read(state, 1); a = read(state, 0);
    check(b.small == 255 && b.large == 47 && b.generation == 1, "nonbinary small command remains raw uint8");
    check(a.small == 1 && a.large == 128 && a.generation == 1, "second port command does not overwrite first port");
    state.command(0, 1, 128);
    a = read(state, 0);
    check(a.generation == 2, "repeated command advances generation for host reapplication");
    check(read(state, 0).generation == a.generation, "reading never consumes a command");
    state.command(0, 0, 255);
    a = read(state, 0);
    check(a.small == 0 && a.large == 255 && a.generation == 3, "full strong amplitude and weak off retained");
    state.command(2, 9, 9);
    check(read(state, 0).generation == 3 && read(state, 1).generation == 1, "invalid callback cannot change either port");
    state.stop(); a = read(state, 0); b = read(state, 1);
    check(neutral(a) && a.generation == 4, "stop publishes first neutral release");
    check(neutral(b) && b.generation == 2, "stop publishes second neutral release");
    state.command(0, 255, 255); state.command(1, 255, 255); state.stop();
    check(neutral(read(state, 0)) && read(state, 0).generation == 4 &&
          neutral(read(state, 1)) && read(state, 1).generation == 2,
          "late writes and repeated stop cannot restart motors");

    rtag_detail::RumbleState concurrent;
    std::atomic<bool> done{false}, coherent{true};
    std::thread writer([&] {
        for (unsigned i = 0; i < 20000; ++i)
            concurrent.command(0, (i & 1) ? 1 : 255, (i & 1) ? 25 : 250);
        done = true;
    });
    std::thread reader([&] {
        uint64_t previous = 0;
        do {
            const auto s = read(concurrent, 0);
            if (s.generation < previous || (!neutral(s) && !((s.small == 1 && s.large == 25) || (s.small == 255 && s.large == 250))))
                coherent = false;
            previous = s.generation;
        } while (!done.load());
    });
    writer.join(); reader.join();
    check(coherent && read(concurrent, 0).generation == 20000, "concurrent reads observe coherent monotonic snapshots");
    check(neutral(read(concurrent, 1)) && read(concurrent, 1).generation == 0, "busy first port leaves second port untouched");

    rtag_detail::RumbleState racing;
    std::atomic<bool> begin{false}, stopped{false}, late_neutral{true};
    std::thread late_writer([&] {
        while (!begin.load()) std::this_thread::yield();
        for (unsigned i = 0; i < 20000; ++i) {
            racing.command(i & 1, 255, 255);
            if (stopped.load() && (!neutral(read(racing, 0)) || !neutral(read(racing, 1)))) late_neutral = false;
        }
    });
    begin = true;
    racing.stop(); stopped = true;
    const auto stopped0 = read(racing, 0), stopped1 = read(racing, 1);
    late_writer.join();
    check(late_neutral && neutral(read(racing, 0)) && neutral(read(racing, 1)), "stop wins callbacks racing on both ports");
    check(read(racing, 0).generation == stopped0.generation && read(racing, 1).generation == stopped1.generation,
          "generation stops changing after final release");
    std::printf("RESULT %d production rumble handoff checks, %d failures; authored commands, no physical vibration proof\n", checks, failures);
    return failures ? 1 : 0;
}
