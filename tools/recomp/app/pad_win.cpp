// pad_win.cpp - pad_host.h for Windows: game controllers through XInput.
//
// Windows input mapping and motor lifecycle have isolated native regression coverage
// (win/tests/run.py); local app and injected-route evidence is recorded in
// docs/issues/windows-pc-qualification.md. Physical actuation and felt vibration are
// separate checks; a synthetic pad never drives physical motors.
//
// XInput is what an Xbox controller speaks, and what Steam Input or DS4Windows make a
// PlayStation controller speak; a PlayStation controller by itself is not seen here.  The
// library is looked for at run time (xinput1_4.dll of Windows 8 and later, then the older
// names), so a machine without it still starts and plays from the keyboard.
//
// The first of the four XInput slots that has a controller is port 1.  The map and the
// dead zones are pad_mac.mm's: A B X Y are cross circle square triangle, the bumpers L1 R1,
// the triggers L2 R2 (pressed from 0.30), the stick buttons L3 R3, Back is Select; a stick
// inside 0.15 of its centre is at rest and outside it the rest of the travel is spread
// over the whole range.
//
// read() is called on the game's thread at every vertical blank and asks XInput itself
// (the call is cheap for a slot with a controller; an empty slot is slow to ask, so the
// empty slots are looked at only once a second).
#ifdef _WIN32
#include "pad_host.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <xinput.h>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <mutex>

namespace hostpad {
namespace {

const float STICK_DEAD_ZONE = 0.15f;
const float TRIGGER_PRESSED = 0.30f;

typedef DWORD(WINAPI* GetState)(DWORD, XINPUT_STATE*);
typedef DWORD(WINAPI* SetState)(DWORD, XINPUT_VIBRATION*);
GetState g_get_state;
SetState g_set_state;
WORD g_left_motor = 0, g_right_motor = 0;
void (*g_log)(const std::string&);
std::mutex g_lock;
int g_slot = -1;                        // the XInput slot that is port 1; -1: none
ULONGLONG g_next_scan;                  // GetTickCount64() at which the empty slots are asked again
std::atomic<uint32_t> g_generation{0};
std::string g_name;
HWND g_window;                          // ours, to know whether the application is in front

// a controller made by test(): read wherever the window is, as on the Mac
bool g_test_attached;
uint16_t g_test_buttons;
float g_test_values[6];

uint8_t axis_byte(float v) {            // -1 .. 1 to 0 .. 255 with 128 in the middle
    float scaled = v >= 0 ? 128.0f + v * 127.0f : 128.0f + v * 128.0f;
    long r = std::lround(scaled);
    return (uint8_t)(r < 0 ? 0 : r > 255 ? 255 : r);
}

// x right, y up, both -1 .. 1; the PlayStation's y grows downward
void stick(float x, float y, uint8_t& out_x, uint8_t& out_y) {
    float length = std::sqrt(x * x + y * y);
    if (!(length > STICK_DEAD_ZONE)) { out_x = out_y = 128; return; }
    float wanted = (length - STICK_DEAD_ZONE) / (1.0f - STICK_DEAD_ZONE);
    if (wanted > 1.0f) wanted = 1.0f;
    out_x = axis_byte(x / length * wanted);
    out_y = axis_byte(-(y / length * wanted));
}

float thumb(SHORT v) { return v < 0 ? (float)v / 32768.0f : (float)v / 32767.0f; }

void from_xinput(const XINPUT_GAMEPAD& g, rta::PadState& state) {
    static const struct { WORD x; uint16_t pad; } map[] = {
        {XINPUT_GAMEPAD_DPAD_UP, rta::PAD_UP}, {XINPUT_GAMEPAD_DPAD_DOWN, rta::PAD_DOWN}, {XINPUT_GAMEPAD_DPAD_LEFT, rta::PAD_LEFT},
        {XINPUT_GAMEPAD_DPAD_RIGHT, rta::PAD_RIGHT}, {XINPUT_GAMEPAD_START, rta::PAD_START}, {XINPUT_GAMEPAD_BACK, rta::PAD_SELECT},
        {XINPUT_GAMEPAD_LEFT_THUMB, rta::PAD_L3}, {XINPUT_GAMEPAD_RIGHT_THUMB, rta::PAD_R3}, {XINPUT_GAMEPAD_LEFT_SHOULDER, rta::PAD_L1},
        {XINPUT_GAMEPAD_RIGHT_SHOULDER, rta::PAD_R1}, {XINPUT_GAMEPAD_A, rta::PAD_CROSS}, {XINPUT_GAMEPAD_B, rta::PAD_CIRCLE},
        {XINPUT_GAMEPAD_X, rta::PAD_SQUARE}, {XINPUT_GAMEPAD_Y, rta::PAD_TRIANGLE}};
    uint16_t buttons = 0;
    for (auto& m : map) if (g.wButtons & m.x) buttons |= m.pad;
    if (g.bLeftTrigger / 255.0f >= TRIGGER_PRESSED) buttons |= rta::PAD_L2;
    if (g.bRightTrigger / 255.0f >= TRIGGER_PRESSED) buttons |= rta::PAD_R2;
    state.buttons = buttons;
    stick(thumb(g.sThumbLX), thumb(g.sThumbLY), state.lx, state.ly);
    stick(thumb(g.sThumbRX), thumb(g.sThumbRY), state.rx, state.ry);
}

void say(const std::string& line) { if (g_log) g_log(line); }

// g_lock held. Remember only successful commands; do not repeatedly write zero
// while unfocused, or interfere with another application's controller use.
void motors(uint8_t small, uint8_t large) {
    WORD left = WORD(large) * 257u, right = small ? 65535u : 0u;
    if (left == g_left_motor && right == g_right_motor) return;
    if (!g_set_state || g_slot < 0) return;
    XINPUT_VIBRATION vibration{left, right};
    DWORD status = g_set_state((DWORD)g_slot, &vibration);
    if (status == ERROR_SUCCESS) {
        g_left_motor = left; g_right_motor = right;
    } else if (status == ERROR_DEVICE_NOT_CONNECTED) {
        g_left_motor = g_right_motor = 0;
    }                                  // retain an outstanding command after a transient failure so a stop can retry
}

// with g_lock held: look through the slots for a controller
void scan() {
    g_next_scan = GetTickCount64() + 1000;
    if (!g_get_state) return;
    for (int slot = 0; slot < 4; slot++) {
        XINPUT_STATE s;
        if (g_get_state((DWORD)slot, &s) == ERROR_SUCCESS) {
            g_slot = slot;
            g_name = "XInput controller " + std::to_string(slot + 1);
            g_generation++;
            say("controller attached: " + g_name + " (port 1)");
            return;
        }
    }
}

bool in_front() {
    if (!g_window) return true;
    return GetForegroundWindow() == g_window;
}

}  // namespace

void set_window(void* hwnd) { g_window = (HWND)hwnd; }

void start(void (*log)(const std::string& line)) {
    std::lock_guard<std::mutex> hold(g_lock);
    g_log = log;
    for (const char* name : {"xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"}) {
        if (HMODULE module = LoadLibraryA(name)) {
            g_get_state = (GetState)(void*)GetProcAddress(module, "XInputGetState");
            if (g_get_state) {
                g_set_state = (SetState)(void*)GetProcAddress(module, "XInputSetState");
                say(std::string("controllers: ") + name);
                break;
            }
        }
    }
    if (!g_get_state) say("controllers: no XInput library on this machine; keyboard only");
    scan();
}

bool read(rta::PadState& state) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (g_test_attached) {
        motors(0, 0);                  // retry a failed stop after synthetic takeover
        state.buttons = g_test_buttons;
        if (g_test_values[4] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_L2;
        if (g_test_values[5] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_R2;
        stick(g_test_values[0], g_test_values[1], state.lx, state.ly);
        stick(g_test_values[2], g_test_values[3], state.rx, state.ry);
        return true;
    }
    if (g_slot < 0) {
        if (GetTickCount64() >= g_next_scan) scan();
        if (g_slot < 0) return false;
    }
    XINPUT_STATE s;
    if (g_get_state((DWORD)g_slot, &s) != ERROR_SUCCESS) {
        say("controller detached: " + g_name);
        motors(0, 0);
        g_left_motor = g_right_motor = 0;
        g_slot = -1;
        g_name.clear();
        g_generation++;
        g_next_scan = GetTickCount64() + 1000;
        return false;
    }
    if (!in_front()) {
        motors(0, 0);                  // a background application must not leave vibration running
        return false;
    }
    from_xinput(s.Gamepad, state);
    return true;
}

void rumble(uint8_t small, uint8_t large) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (g_test_attached) {
        motors(0, 0);                  // scripted pads may only release an outstanding physical command
        return;
    }
    if (!in_front()) small = large = 0;
    motors(small, large);
}

std::string name() {
    std::lock_guard<std::mutex> hold(g_lock);
    return g_test_attached ? std::string("test controller") : g_name;
}

uint32_t generation() { return g_generation; }

void test(const std::string& command, uint16_t buttons, const float values[6]) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (command == "connect") {
        motors(0, 0);                  // a synthetic pad takes over port 1
        g_test_attached = true;
        g_test_buttons = 0;
        for (float& v : g_test_values) v = 0;
        g_generation++;
        say("controller attached: test controller (port 1)");
    } else if (command == "disconnect") {
        if (g_test_attached) { g_generation++; say("controller detached: test controller"); }
        g_test_attached = false;
    } else if (command == "set" || command == "none") {
        g_test_buttons = command == "none" ? 0 : buttons;
        for (int k = 0; k < 6; k++) g_test_values[k] = command == "none" ? 0 : values[k];
    }
}

void keep_timers() {}

}  // namespace hostpad
#endif  // _WIN32
