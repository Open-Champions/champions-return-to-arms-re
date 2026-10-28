#pragma once
#include <cstdint>
#include <mutex>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/rid.hpp>

namespace godot {
// Presentation GPU execution time, never a simulation clock. Metal uses
// completed command buffers; RD renderers use completed world-viewport queries.
class RtaGpuTimer : public RefCounted {
    GDCLASS(RtaGpuTimer, RefCounted)
public:
    RtaGpuTimer();
    ~RtaGpuTimer();
    bool is_available() const { return state != nullptr || rd_available; }
    void set_viewport(const RID& viewport);
    void reset();
    void begin_frame(bool world_drawn);
    void end_frame();
    Dictionary sample() const;
protected:
    static void _bind_methods();
private:
    static void read_rd(Ref<RtaGpuTimer> owner, RID viewport, int64_t epoch, int64_t world_frame);
    void* state = nullptr;
    uint64_t frame = 0, minimum_frame = 0;
    bool rd_available = false;
    mutable std::mutex rd_mutex;
    RID rd_viewport;
    uint64_t rd_epoch = 1, rd_batch = 0, rd_submission = 0, rd_last_submission = 0;
    bool rd_valid = false;
    double rd_ms = 0, rd_cpu_ms = 0;
};
}

#ifdef __APPLE__
void* rta_metal_timer_create(uint64_t queue);
void rta_metal_timer_destroy(void* state);
void rta_metal_timer_begin(void* state, uint64_t frame, bool world_drawn);
void rta_metal_timer_end(void* state);
bool rta_metal_timer_sample(void* state, uint64_t& frame, double& milliseconds);
#endif
