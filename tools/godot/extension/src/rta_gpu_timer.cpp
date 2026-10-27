#include "rta_gpu_timer.h"
#include <godot_cpp/classes/rendering_device.hpp>
#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/core/class_db.hpp>

using namespace godot;

RtaGpuTimer::RtaGpuTimer() {
#ifdef __APPLE__
    auto* server = RenderingServer::get_singleton();
    if (server && server->get_current_rendering_driver_name() == "metal") {
        auto* device = server->get_rendering_device();
        if (device) state = rta_metal_timer_create(device->get_driver_resource(RenderingDevice::DRIVER_RESOURCE_COMMAND_QUEUE, RID(), 0));
    }
#endif
}
RtaGpuTimer::~RtaGpuTimer() {
#ifdef __APPLE__
    if (state) rta_metal_timer_destroy(state);
#endif
}
void RtaGpuTimer::begin_frame(bool world_drawn) {
#ifdef __APPLE__
    if (state) rta_metal_timer_begin(state, ++frame, world_drawn);
#endif
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
    if (state && rta_metal_timer_sample(state, number, milliseconds)) {
        result["frame"] = (int64_t)number;
        result["gpu_ms"] = milliseconds;
    }
#endif
    return result;
}
void RtaGpuTimer::_bind_methods() {
    ClassDB::bind_method(D_METHOD("is_available"), &RtaGpuTimer::is_available);
    ClassDB::bind_method(D_METHOD("begin_frame", "world_drawn"), &RtaGpuTimer::begin_frame);
    ClassDB::bind_method(D_METHOD("end_frame"), &RtaGpuTimer::end_frame);
    ClassDB::bind_method(D_METHOD("sample"), &RtaGpuTimer::sample);
}
