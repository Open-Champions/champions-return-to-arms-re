#include "rta_gpu_timer.h"
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <objc/runtime.h>
#include <algorithm>
#include <memory>
#include <mutex>
#include <vector>

namespace {
struct Frame {
    uint64_t number = 0;
    bool closed = false;
    unsigned pending = 0;
    std::vector<std::pair<double, double>> spans;
};
struct State {
    id<MTLCommandQueue> queue;
    std::shared_ptr<Frame> current;
    uint64_t latest = 0;
    double milliseconds = 0;
};
using TimerHandle = std::shared_ptr<State>;
std::mutex mutex;
std::weak_ptr<State> active;
IMP original_commit = nullptr;
Class hooked_class = Nil;

void publish(State& state, const Frame& frame) {
    if (!frame.closed || frame.pending || frame.spans.empty() || frame.number <= state.latest) return;
    auto spans = frame.spans;
    std::sort(spans.begin(), spans.end());
    double start = spans[0].first, end = spans[0].second, seconds = 0;
    for (size_t i = 1; i < spans.size(); ++i) {
        if (spans[i].first > end) { seconds += end - start; start = spans[i].first; }
        end = std::max(end, spans[i].second);
    }
    seconds += end - start;
    if (seconds > 0) { state.latest = frame.number; state.milliseconds = seconds * 1000.0; }
}

// A passive observer of this renderer's queue only. No extra GPU commands,
// counters, waits, changed descriptors or retained buffers. The public commit
// selector is installed once on the concrete class returned by Metal, without
// depending on a private driver class name. Hot reload is disabled for this
// extension; pending callbacks own their state until completion.
void observed_commit(id<MTLCommandBuffer> buffer, SEL selector) {
    TimerHandle state;
    std::shared_ptr<Frame> frame;
    {
        std::lock_guard<std::mutex> lock(mutex);
        state = active.lock();
        if (state && buffer.commandQueue == state->queue && state->current && !state->current->closed) {
            frame = state->current;
            ++frame->pending;
        }
    }
    if (frame) {
        [buffer addCompletedHandler:^(id<MTLCommandBuffer> completed) {
            std::lock_guard<std::mutex> lock(mutex);
            const double start = completed.GPUStartTime, end = completed.GPUEndTime;
            if (completed.status == MTLCommandBufferStatusCompleted && start > 0 && end > start) frame->spans.emplace_back(start, end);
            --frame->pending;
            publish(*state, *frame);
        }];
    }
    ((void (*)(id, SEL))original_commit)(buffer, selector);
}
}

void* rta_metal_timer_create(uint64_t queue_pointer) {
    if (!queue_pointer) return nullptr;
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)(void*)(uintptr_t)queue_pointer;
    id<MTLCommandBuffer> buffer = [queue commandBuffer];
    Class cls = object_getClass(buffer);
    std::lock_guard<std::mutex> lock(mutex);
    if (!active.expired() || (hooked_class && hooked_class != cls)) return nullptr;
    if (!hooked_class) {
        Method method = class_getInstanceMethod(cls, @selector(commit));
        if (!method) return nullptr;
        original_commit = method_getImplementation(method);
        if (!class_addMethod(cls, @selector(commit), (IMP)observed_commit, method_getTypeEncoding(method)))
            method_setImplementation(method, (IMP)observed_commit);
        hooked_class = cls;
    }
    auto state = std::make_shared<State>();
    state->queue = queue;
    active = state;
    return new TimerHandle(std::move(state));
}
void rta_metal_timer_destroy(void* pointer) {
    auto* handle = static_cast<TimerHandle*>(pointer);
    {
        std::lock_guard<std::mutex> lock(mutex);
        if (active.lock() == *handle) active.reset();
        (*handle)->current.reset();
    }
    delete handle;
}
void rta_metal_timer_begin(void* pointer, uint64_t number, bool world_drawn) {
    std::lock_guard<std::mutex> lock(mutex);
    auto& state = **static_cast<TimerHandle*>(pointer);
    state.current.reset();
    if (world_drawn) { state.current = std::make_shared<Frame>(); state.current->number = number; }
}
void rta_metal_timer_end(void* pointer) {
    std::lock_guard<std::mutex> lock(mutex);
    auto& state = **static_cast<TimerHandle*>(pointer);
    if (state.current) { state.current->closed = true; publish(state, *state.current); }
}
bool rta_metal_timer_sample(void* pointer, uint64_t& number, double& milliseconds) {
    std::lock_guard<std::mutex> lock(mutex);
    const auto& state = **static_cast<TimerHandle*>(pointer);
    number = state.latest; milliseconds = state.milliseconds;
    return number != 0;
}
