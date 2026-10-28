// Host-side motor handoff only: no game state or controller/device calls.
#pragma once
#include <cstdint>
#include <mutex>

namespace rtag_detail {
class RumbleState {
    struct Motors { uint8_t small = 0, large = 0; uint64_t generation = 0; } ports[2];
    mutable std::mutex lock;
    bool stopped = false;
  public:
    void command(unsigned port, uint8_t small, uint8_t large) {
        if (port >= 2) return;
        std::lock_guard<std::mutex> hold(lock);
        if (stopped) return;                  // a game callback racing stop cannot restart a motor
        ports[port].small = small;
        ports[port].large = large;
        ++ports[port].generation;             // repeats are new commands too; reads never consume them
    }
    int read(int port, uint8_t* small, uint8_t* large, uint64_t* generation) const {
        if (small) *small = 0;
        if (large) *large = 0;
        if (generation) *generation = 0;
        if (port < 0 || port >= 2) return 0;
        std::lock_guard<std::mutex> hold(lock);
        if (small) *small = ports[port].small;
        if (large) *large = ports[port].large;
        if (generation) *generation = ports[port].generation;
        return 1;
    }
    void stop() {
        std::lock_guard<std::mutex> hold(lock);
        if (stopped) return;
        stopped = true;
        for (auto& p : ports) {
            p.small = p.large = 0;
            ++p.generation;                   // the neutral release is observable on each port
        }
    }
};
} // namespace rtag_detail
