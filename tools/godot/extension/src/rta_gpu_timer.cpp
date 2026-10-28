#include "rta_gpu_timer.h"
#include <godot_cpp/classes/rendering_device.hpp>
#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/callable_method_pointer.hpp>

using namespace godot;

RtaGpuTimer::RtaGpuTimer() {
    auto* server = RenderingServer::get_singleton();
#ifdef __APPLE__
    if (server && server->get_current_rendering_driver_name() == "metal") {
        auto* device = server->get_rendering_device();
        if (device) state = rta_metal_timer_create(device->get_driver_resource(RenderingDevice::DRIVER_RESOURCE_COMMAND_QUEUE, RID(), 0));
        return;
    }
#endif
    rd_available = server && server->get_rendering_device();
}
RtaGpuTimer::~RtaGpuTimer() {
#ifdef __APPLE__
    if (state) rta_metal_timer_destroy(state);
#endif
}
void RtaGpuTimer::set_viewport(const RID& viewport) {
    if (!rd_available && !state) return;
    {
        std::lock_guard<std::mutex> lock(rd_mutex);
        if (viewport == rd_viewport) return;
        rd_viewport = viewport;
        ++rd_epoch;
        rd_batch = 0;
        rd_last_submission = 0;
        rd_valid = false;
        minimum_frame = frame + 1;
    }
    if (rd_available && viewport.is_valid()) RenderingServer::get_singleton()->viewport_set_measure_render_time(viewport, true);
}
void RtaGpuTimer::reset() {
    minimum_frame = frame + 1;
    std::lock_guard<std::mutex> lock(rd_mutex);
    ++rd_epoch;
    rd_batch = 0;
    rd_last_submission = 0;
    rd_valid = false;
}
void RtaGpuTimer::begin_frame(bool world_drawn) {
#ifdef __APPLE__
    if (state) { rta_metal_timer_begin(state, ++frame, world_drawn); return; }
#endif
    if (!rd_available) return;
    RID viewport;
    uint64_t epoch, submission;
    {
        std::lock_guard<std::mutex> lock(rd_mutex);
        viewport = rd_viewport;
        epoch = rd_epoch;
        submission = world_drawn ? ++rd_submission : 0;
    }
    if (!viewport.is_valid()) return;
    // Poll on held frames too: a rendered frame's queries complete later. The
    // bound Ref owns the timer until this queued render-thread call finishes.
    RenderingServer::get_singleton()->call_on_render_thread(callable_mp_static(&RtaGpuTimer::read_rd).bind(Ref<RtaGpuTimer>(this), viewport, (int64_t)epoch, (int64_t)submission));
}
void RtaGpuTimer::read_rd(Ref<RtaGpuTimer> owner, RID viewport, int64_t epoch, int64_t world_frame) {
    auto* device = RenderingServer::get_singleton()->get_rendering_device();
    if (!device) return;
    {
        std::lock_guard<std::mutex> lock(owner->rd_mutex);
        if (owner->rd_epoch != (uint64_t)epoch || owner->rd_viewport != viewport) return;
    }
    const String marker_prefix = String("rta_world_") + String::num_int64((int64_t)owner->get_instance_id()) + "_" + String::num_int64(epoch) + "_";
    const String begin = String("vp_begin_") + String::num_int64((int64_t)viewport.get_id());
    const String end = String("vp_end_") + String::num_int64((int64_t)viewport.get_id());
    const uint64_t batch = device->get_captured_timestamps_frame();
    uint64_t submission = 0;
    unsigned tags = 0;
    unsigned begins = 0, ends = 0;
    uint64_t gpu_begin = 0, gpu_end = 0, cpu_begin = 0, cpu_end = 0;
    for (uint32_t i = 0; i < device->get_captured_timestamps_count(); ++i) {
        const String name = device->get_captured_timestamp_name(i);
        if (name.begins_with(marker_prefix)) {
            const String token = name.substr(marker_prefix.length());
            if (token.is_valid_int() && token.to_int() > 0) { ++tags; submission = (uint64_t)token.to_int(); }
        }
        if (name == begin) {
            ++begins;
            gpu_begin = device->get_captured_timestamp_gpu_time(i);
            cpu_begin = device->get_captured_timestamp_cpu_time(i);
        } else if (name == end) {
            ++ends;
            gpu_end = device->get_captured_timestamp_gpu_time(i);
            cpu_end = device->get_captured_timestamp_cpu_time(i);
        }
    }
    {
        std::lock_guard<std::mutex> lock(owner->rd_mutex);
        if (owner->rd_epoch != (uint64_t)epoch || owner->rd_viewport != viewport) return;
        // Godot's completed-batch ID is diagnostic: it may be relabelled at
        // ring reuse. Our own world token rejects repeated query data too.
        if (submission > owner->rd_last_submission && tags == 1 && begins == 1 && ends == 1 && gpu_begin > 0 && gpu_end > gpu_begin && cpu_end >= cpu_begin) {
            owner->rd_batch = batch;
            owner->rd_last_submission = submission;
            // Godot 4.5.2's Vulkan/D3D12 drivers return nanoseconds here.
            // Subtract integers first, before converting a large absolute time.
            owner->rd_ms = double(gpu_end - gpu_begin) / 1000000.0;
            owner->rd_cpu_ms = double(cpu_end - cpu_begin) / 1000.0;
            owner->rd_valid = true;
        }
    }
    // This marker accompanies only an actual world render. A concurrent reset
    // can leave an old-epoch marker in flight; the parser will reject it.
    if (world_frame > 0) device->capture_timestamp(marker_prefix + String::num_int64(world_frame));
}
void RtaGpuTimer::end_frame() {
#ifdef __APPLE__
    if (state) rta_metal_timer_end(state);
#endif
}
Dictionary RtaGpuTimer::sample() const {
    Dictionary result;
#ifdef __APPLE__
    uint64_t number = 0;
    double milliseconds = 0;
    if (state && rta_metal_timer_sample(state, number, milliseconds) && number >= minimum_frame) {
        result["frame"] = (int64_t)number;
        result["gpu_ms"] = milliseconds;
        result["source"] = "metal";
    }
#endif
    if (rd_available) {
        std::lock_guard<std::mutex> lock(rd_mutex);
        if (rd_valid) {
            result["frame"] = (int64_t)rd_last_submission;
            result["batch"] = (int64_t)rd_batch;
            result["gpu_ms"] = rd_ms;
            result["cpu_ms"] = rd_cpu_ms;
            result["viewport_id"] = (int64_t)rd_viewport.get_id();
            result["generation"] = (int64_t)rd_epoch;
            result["source"] = "rd_viewport";
        }
    }
    return result;
}
void RtaGpuTimer::_bind_methods() {
    ClassDB::bind_method(D_METHOD("is_available"), &RtaGpuTimer::is_available);
    ClassDB::bind_method(D_METHOD("set_viewport", "viewport"), &RtaGpuTimer::set_viewport);
    ClassDB::bind_method(D_METHOD("reset"), &RtaGpuTimer::reset);
    ClassDB::bind_method(D_METHOD("begin_frame", "world_drawn"), &RtaGpuTimer::begin_frame);
    ClassDB::bind_method(D_METHOD("end_frame"), &RtaGpuTimer::end_frame);
    ClassDB::bind_method(D_METHOD("sample"), &RtaGpuTimer::sample);
}
