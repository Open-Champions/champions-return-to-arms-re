// Authored ABI-only game-library stand-in for the real optional-symbol loader.
#include "../lib/rtag.h"
#include "../lib/rumble_state.h"
#include <cstring>
#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C" __attribute__((visibility("default")))
#endif
static rtag_detail::RumbleState motors;
EXPORT int rtag_api_version() { return RTAG_API_VERSION; }
EXPORT int rtag_has(const char*) { return 0; }
EXPORT int rtag_start(const rtag_config*) { return 0; }
EXPORT void rtag_set_pad(int, const rtag_pad*) {}
EXPORT int rtag_step(const rtag_pad*, int, const rtag_frame**) { return -1; }
EXPORT int rtag_poll(int, const rtag_frame**) { return -1; }
EXPORT void rtag_run(double) {}
EXPORT void rtag_audio_pull(int16_t* out, int frames) { if (out && frames > 0) std::memset(out, 0, size_t(frames) * 4); }
EXPORT const uint8_t* rtag_memory() { return nullptr; }
EXPORT uint64_t rtag_fields() { return 0; }
EXPORT const char* rtag_info() { return "authored rumble ABI stub"; }
EXPORT int rtag_ended() { return 0; }
EXPORT int rtag_exit_code() { return 0; }
EXPORT void rtag_stop() { motors.stop(); }
EXPORT int rtag_set_option(const char*, const char*) { return 0; }
#ifdef TEST_WITH_RUMBLE
EXPORT int rtag_rumble(int port, uint8_t* small, uint8_t* large, uint64_t* generation) {
    return motors.read(port, small, large, generation);
}
EXPORT void test_rumble_command(unsigned port, uint8_t small, uint8_t large) { motors.command(port, small, large); }
#endif
