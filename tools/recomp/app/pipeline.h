// pipeline.h - the picture path of the application: what the runtime hands its picture
// sink (rta::VideoSink) is copied on the game's thread, decoded on a thread of its own
// (VIF1, VU1, GS model: render::Renderer) and comes out as one FrameList per vertical
// blank for whoever draws it.
//
//   game threads   Sink::vif1/gif/reg copy into the frame's batch, with the stores the game
//                  made into VU1 memory and the texture headers that changed (both are read
//                  here, where the game stands still); Sink::vblank hands the batch over
//                  (it waits only while the decoder has not yet taken the one before) and
//                  then waits for the moment the next frame may start (Pacer);
//   decoder        plays batches into a Renderer that owns its VU1 memory and a copy of
//                  main memory; the Renderer's on_frame gets the list.
// The same split as tools/recomp/render/app_main.cpp (rta_render), as a header.
//
// Pacing (Pacer).  The game is let go by a clock, one frame per period, not by whoever
// shows the picture: nothing that happens to a swap can hold the game, its sound or a
// lockstep partner back.  Every picture has a moment it is due on screen; those moments
// are a grid one period apart, and the frame that makes a picture is let go `lead` before
// its moment, `lead` being what the path from there to a drawn picture has lately taken
// (game, decoder, OpenGL: the third longest of the last two seconds, and a margin).  So
// a picture arrives just before it is shown instead of waiting in two hand-overs, and what
// the controller held when its frame began is that much younger; a frame that takes longer
// than any lately did comes late once and makes the lead longer for the next seconds.
// Where the swap waits for the display, the time it returns at says where the display's
// refreshes lie, and the grid is moved toward them a little with every picture; where it
// does not wait (a hidden window, a display that is asleep) the grid is the clock's.
#pragma once
#include "iface.h"
#include "renderer.h"
#include "stream.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <ctime>
#include <mutex>
#include <thread>
#include <vector>
#ifdef __APPLE__
#include <pthread.h>
#include <pthread/qos.h>
#endif

namespace app {

inline double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline void sleep_until_ms(double when) {
    double now = now_ms();
    if (when > now) std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(when - now));
}
inline double thread_cpu_ms() {
    timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}
// The threads a picture passes through are the player's business: the calling thread asks
// to be scheduled as such (macOS: the user-interactive class, ahead of whatever else the
// computer is busy with; elsewhere nothing is asked).
inline void interactive_thread() {
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
}

// When one picture passed which point (milliseconds of now_ms(); 0 = not passed).
struct Timing {
    uint64_t number = 0;
    double released = 0;        // the game was let go for the frame that made it
    double handed = 0;          // the game's thread reached the blank: the batch is complete
    double slot_wait = 0;       // ... and waited this long for the decoder to take the one before
    double decode_start = 0, decode_end = 0;
    double queue_wait = 0;      // the decoder waited this long to hand the list on
    double draw_start = 0, ready = 0;       // the window's thread: OpenGL calls
    double swap_start = 0, shown = 0;
    double due = 0;             // when it was meant to be on screen (0: no such moment)
    double blocked = 0;         // of the way, the time it stood behind the picture before it (decoder or window busy with that one)
    double woke_late = 0;       // the game's thread woke this long after the time it had asked to be let go at
};

// One figure of the path, per picture: sum, count and every value (for the percentile).
struct Figure {
    std::vector<float> values;
    double sum = 0, most = 0;
    void add(double v) { if (v < 0) v = 0; sum += v; if (v > most) most = v; if (values.size() < 400000) values.push_back((float)v); }
    double mean() const { return values.empty() ? 0.0 : sum / values.size(); }
    double percentile(double p) const {
        if (values.empty()) return 0;
        std::vector<float> sorted = values;
        size_t at = (size_t)(p * (sorted.size() - 1) + 0.5);
        std::nth_element(sorted.begin(), sorted.begin() + at, sorted.end());
        return sorted[at];
    }
    void clear() { values.clear(); sum = 0; most = 0; }
};

struct Pacer {
    enum Mode { OFF, QUEUED, AHEAD };
    // OFF     not paced: as fast as the machine goes
    // QUEUED  the way it was: the window's thread holds one picture per period and the wait
    //         travels back through the two hand-overs to the game (--pacing queued)
    // AHEAD   as described at the head of this file (the default)
    Mode mode = OFF;
    double period_ms = 1000.0 / 59.94;
    std::atomic<double> margin_ms{2.0};     // a drawn picture is meant to be there this long before its moment
    double most_lead_ms = 2.5 * 1000.0 / 59.94;
    std::atomic<double> lead_ms{16.0};      // from letting the game go to the picture's moment
    std::atomic<uint64_t> resyncs{0};       // the grid was started again after a stall
    std::atomic<double> slewed_ms{0};       // how far the grid has been moved toward the display, in all
    std::atomic<double> woke_late_ms{0};    // the game's thread woke this much after the time it had asked for, in all ...
    std::atomic<uint64_t> wakes{0};         // ... in this many waits

    // ---- the game's thread ----
    double due = 0;                         // the moment of the picture whose frame is being computed
    double released = 0;                    // when that frame was let go (as it happened)
    double woke_late = 0;                   // ... and how long after the time asked for that was
    // Called at a blank, after the batch has been handed over: returns when the next frame
    // may start.
    void wait_release() {
        if (mode != AHEAD) { released = now_ms(); due = 0; woke_late = 0; return; }
        double slew = 0, lead;
        {
            std::lock_guard<std::mutex> hold(lock);
            if (error_new) { slew = std::max(-0.5, std::min(0.5, 0.1 * error_ms)); error_new = false; }
            if (pipe_count >= 16) {
                // the third longest of what is remembered: one frame that took far longer
                // than the others (a texture load) does not set the lead by itself
                float sorted[PIPES];
                size_t n = std::min(pipe_count, (size_t)PIPES);
                memcpy(sorted, pipes, n * sizeof(float));
                std::nth_element(sorted, sorted + (n - 3), sorted + n);
                double margin = margin_ms;
                lead = std::max(margin + 1.0, std::min(most_lead_ms, sorted[n - 3] + margin));
                lead_ms = lead;
            } else lead = lead_ms;
        }
        double now = now_ms(), next = due + period_ms + slew;
        if (due == 0 || now > next - lead + period_ms) {        // the first frame, or more than a period late: a new grid
            if (due != 0) resyncs++;
            next = now + lead;
        } else {
            slewed_ms = slewed_ms + slew;
            sleep_until_ms(next - lead);
        }
        due = next;
        released = now_ms();
        woke_late = released > next - lead ? released - (next - lead) : 0;
        if (woke_late < period_ms) { woke_late_ms = woke_late_ms + woke_late; wakes++; } else woke_late = 0;       // (a stall is not a late wake)
    }

    // ---- the window's thread ----
    // A picture was drawn (`ready`) and shown (`shown`); `timed`: the swap returned at a
    // refresh of the display, so `shown - due` says how far the grid is off it.
    void presented(const Timing& t, bool timed) {
        if (mode != AHEAD) return;
        std::lock_guard<std::mutex> hold(lock);
        if (t.released > 0 && t.ready > t.released) {
            // the whole way, less the time it stood behind the picture before it: a list
            // that waited for the window's thread to come back from a swap would have waited
            // no longer had it come later (and counting that wait would let the game go ever
            // earlier)
            // (and with what the game's thread woke late by: the grid counts from the time it asked for)
            double pipe = t.ready - t.released - t.blocked + t.woke_late;
            if (pipe < 4 * period_ms) { pipes[pipe_at] = (float)pipe; pipe_at = (pipe_at + 1) % PIPES; pipe_count++; }    // a level load is not what a frame takes
        }
        if (timed && t.due > 0) {
            error_ms = std::max(-period_ms, std::min(period_ms, t.shown - t.due));
            error_new = true;
        }
    }

  private:
    enum { PIPES = 120 };
    std::mutex lock;
    float pipes[PIPES];
    size_t pipe_at = 0, pipe_count = 0;
    double error_ms = 0;
    bool error_new = false;
};

// One frame of what the sink was handed, in order.
struct Batch {
    struct Record { uint32_t kind, a; uint64_t b; size_t offset, count; };
    std::vector<Record> records;
    std::vector<uint32_t> words;
    Timing timing;
    void put(uint32_t kind, uint32_t a, uint64_t b, const uint32_t* data, size_t count) {
        records.push_back({kind, a, b, words.size(), count});
        if (count) words.insert(words.end(), data, data + count);
    }
    // A level's textures arrive in one frame (tens of megabytes): the three batches that
    // go round would each keep that much for ever, so a buffer that large is given back.
    void clear() {
        records.clear();
        if (words.capacity() > (4u << 20)) std::vector<uint32_t>().swap(words); else words.clear();
    }
};

struct Sink : rta::VideoSink {
    render::Renderer* renderer = nullptr;       // the decoder's; set before the game starts
    // figures (per vertical blank): wall time of the game side, the decoder's own time
    double game_ms = 0, decode_cpu_ms = 0, decode_wall_ms = 0;
    double* waited_downstream_ms = nullptr;     // time on_frame spent waiting, to take out of the decoder's
    uint64_t blanks = 0;
    Pacer pacer;                                // set up before the game starts
    Timing current;                             // of the batch the decoder is playing (read in on_frame, on its thread)

    void start() {
        std::thread decoder([this] { interactive_thread(); decoder_loop(); });
        decoder.detach();
    }

    void vif1(const uint32_t* words, size_t count) override {
        prepare();
        sync();
        filling.put(render::SK_VIF1, 0, 0, words, count);
    }
    void gif(const uint32_t* words, size_t count) override {
        prepare();
        filling.put(render::SK_GIF, 0, 0, words, count);
    }
    void reg(uint32_t address, uint64_t value) override { filling.put(render::SK_REG, address, value, nullptr, 0); }
    void vblank(unsigned field, uint64_t number) override {
        prepare();
        blanks++;
        double now = now_ms();
        if (left_at != 0) game_ms += now - left_at;
        // the game loads textures as it goes: when the decoder met one it has no header
        // for, look through memory again (it takes milliseconds; the decoder asks once per
        // texture and again only when the list has grown)
        if (renderer->index.missed && blanks - last_scan >= 3) { renderer->index.missed = false; rescan(); }
        filling.put(render::SK_VBLANK, field, number, nullptr, 0);
        filling.timing = Timing();
        filling.timing.number = number;
        filling.timing.released = pacer.released;
        filling.timing.woke_late = pacer.woke_late;
        filling.timing.due = pacer.due;
        filling.timing.handed = now;
        {
            std::unique_lock<std::mutex> hold(lock);
            changed.wait(hold, [this] { return !has_waiting; });
            filling.timing.slot_wait = now_ms() - now;
            std::swap(waiting, filling);
            has_waiting = true;
            filling.clear();
            changed.notify_all();
        }
        // the frame after this one is let go when its picture's moment asks for it; the
        // controller is read after this returns (rt/runtime.cpp, on_vblank)
        pacer.wait_release();
        left_at = pacer.released;
    }

  private:
    bool first = true;
    Batch filling, waiting;
    std::mutex lock;
    std::condition_variable changed;
    bool has_waiting = false;
    std::vector<uint8_t> ram_copy;              // the decoder's main memory
    std::vector<uint8_t> vu_data, vu_micro;     // VU1 memory as last sent
    render::TexIndex index;                     // over the game's memory, read on the game's thread
    std::vector<uint16_t> blocks;
    uint64_t last_scan = 0;
    double left_at = 0;

    void prepare() {
        if (!first) return;
        first = false;
        ram_copy.assign(rta::memory(), rta::memory() + 0x2000000);
        vu_data.assign(0x4000, 0);
        vu_micro.assign(0x4000, 0);
        index.ram = rta::memory();
        index.size = 0x2000000;
        rescan();
    }
    void rescan() {
        // every header new to the list is sent once; the known ones keep their state
        std::vector<uint32_t> old_headers = index.headers;
        std::vector<uint16_t> old_blocks = blocks;
        index.scan();
        blocks.assign(index.headers.size(), 0xFFFF);
        size_t at = 0;                          // both lists are in address order
        for (size_t k = 0; k < index.headers.size(); k++) {
            while (at < old_headers.size() && old_headers[at] < index.headers[k]) at++;
            if (at < old_headers.size() && old_headers[at] == index.headers[k]) blocks[k] = old_blocks[at];
        }
        last_scan = blanks;
    }
    void sync() {                               // on the game's thread, before a transfer is queued
        const uint8_t* d = rta::vu1_data();
        for (uint32_t q = 0; q < 0x400; q++)
            if (memcmp(d + q * 16, vu_data.data() + q * 16, 16)) {
                memcpy(vu_data.data() + q * 16, d + q * 16, 16);
                filling.put(render::SK_VU1DATA, q, 0, (const uint32_t*)(d + q * 16), 4);
            }
        if (memcmp(rta::vu1_micro(), vu_micro.data(), 0x4000)) {
            memcpy(vu_micro.data(), rta::vu1_micro(), 0x4000);
            filling.put(render::SK_VU1MICRO, 0, 0, (const uint32_t*)rta::vu1_micro(), 0x1000);
        }
        for (size_t k = 0; k < blocks.size(); k++) {
            const uint8_t* h = index.ram + index.headers[k];
            uint16_t block = render::TexIndex::u16(h + 0x18);
            if (block == blocks[k]) continue;
            blocks[k] = block;
            uint32_t words[8];
            memcpy(words, h, 32);
            filling.put(render::SK_RAM, index.headers[k], 0, words, 8);
        }
    }
    void play(const Batch& batch) {
        render::Renderer& r = *renderer;
        for (const Batch::Record& e : batch.records) {
            const uint32_t* w = batch.words.data() + e.offset;
            switch (e.kind) {
            case render::SK_VIF1: r.vif1(w, e.count); break;
            case render::SK_GIF: r.gif(w, e.count); break;
            case render::SK_REG: r.reg(e.a, e.b); break;
            case render::SK_VBLANK: r.vblank(e.a, e.b); break;
            case render::SK_VU1DATA: memcpy(r.vif.vu.data + (e.a & 0x3FF) * 16, w, 16); break;
            case render::SK_VU1MICRO: memcpy(r.vif.vu.micro, w, 0x4000); r.vif.vu.micro_changed(); break;
            case render::SK_RAM:                // a texture header (32 bytes)
                if ((uint64_t)e.a + e.count * 4 <= ram_copy.size()) memcpy(ram_copy.data() + e.a, w, e.count * 4);
                if (std::find(r.index.headers.begin(), r.index.headers.end(), e.a) == r.index.headers.end()) r.index.headers.push_back(e.a);
                break;
            default: break;
            }
        }
    }
    void decoder_loop() {
        Batch mine;
        bool started = false;
        for (;;) {
            {
                std::unique_lock<std::mutex> hold(lock);
                changed.wait(hold, [this] { return has_waiting; });
                std::swap(mine, waiting);
                has_waiting = false;
                changed.notify_all();
            }
            if (!started) {
                started = true;
                renderer->set_memory(ram_copy.data(), (uint32_t)ram_copy.size());
                renderer->index.auto_rescan = false;
                // a machine resumed from a memory image never sent its VU1 program
                if (resumed && renderer->needs_program()) renderer->load_program((const uint32_t*)(ram_copy.data() + 0x3e5ec0), 940 * 4);
            }
            current = mine.timing;
            double c0 = thread_cpu_ms();
            double w0 = now_ms(), waited0 = waited_downstream_ms ? *waited_downstream_ms : 0;
            current.decode_start = w0;
            if (decoder_free > current.handed) current.blocked += std::min(w0, decoder_free) - current.handed;
            play(mine);
            decode_cpu_ms += thread_cpu_ms() - c0;
            decode_wall_ms += now_ms() - w0 - ((waited_downstream_ms ? *waited_downstream_ms : 0) - waited0);
            mine.clear();
            decoder_free = now_ms();
        }
    }
    double decoder_free = 0;                    // when the decoder was done with the batch before

  public:
    bool resumed = false;                       // the machine starts from a memory image
};

}  // namespace app
