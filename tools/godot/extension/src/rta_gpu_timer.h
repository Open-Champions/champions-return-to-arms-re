#pragma once
#include <cstdint>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>

namespace godot {
// Presentation GPU execution time, never a simulation clock. Godot 4.5's Metal
// timestamp queries return zero; use completed command buffers.
class RtaGpuTimer : public RefCounted {
    GDCLASS(RtaGpuTimer, RefCounted)
public:
    RtaGpuTimer();
    ~RtaGpuTimer();
    bool is_available() const { return state != nullptr; }
    void begin_frame(bool world_drawn);
    void end_frame();
    Dictionary sample() const;
protected:
    static void _bind_methods();
private:
    void* state = nullptr;
    uint64_t frame = 0;
};
}

#ifdef __APPLE__
void* rta_metal_timer_create(uint64_t queue);
void rta_metal_timer_destroy(void* state);
void rta_metal_timer_begin(void* state, uint64_t frame, bool world_drawn);
void rta_metal_timer_end(void* state);
bool rta_metal_timer_sample(void* state, uint64_t& frame, double& milliseconds);
#endif
