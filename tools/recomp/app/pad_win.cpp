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
// The first two controllers used claim PS2 ports 1 and 2 independently. Idle virtual
// devices do not occupy a player merely because Windows assigned them a lower slot. Removing one
// never promotes the other. A vacant port prefers its previous XInput index on rescan;
// XInput provides slot indices, not persistent physical device identity. The map and the
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
const unsigned PORT_COUNT = 2;

typedef DWORD(WINAPI* GetState)(DWORD, XINPUT_STATE*);
typedef DWORD(WINAPI* SetState)(DWORD, XINPUT_VIBRATION*);
GetState g_get_state;
SetState g_set_state;
void (*g_log)(const std::string&);
std::mutex g_lock;
ULONGLONG g_next_scan;
HWND g_window;
bool g_connected[4] = {};

struct Port {
    int slot = -1;
    int preferred_slot = -1;
    WORD left_motor = 0, right_motor = 0;
    std::atomic<uint32_t> generation{0};
    std::string name;
    bool test_attached = false;
    uint16_t test_buttons = 0;
    float test_values[6] = {};
};
Port g_ports[PORT_COUNT];

// P1 aliases keep the existing isolated production-source regression harness intact.
int& g_slot = g_ports[0].slot;
WORD& g_left_motor = g_ports[0].left_motor;
WORD& g_right_motor = g_ports[0].right_motor;
std::atomic<uint32_t>& g_generation = g_ports[0].generation;
std::string& g_name = g_ports[0].name;
bool& g_test_attached = g_ports[0].test_attached;
uint16_t& g_test_buttons = g_ports[0].test_buttons;
float (&g_test_values)[6] = g_ports[0].test_values;

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

// g_lock held. Each physical slot has its own successful-command cache and retries.
void motors(unsigned port, uint8_t small, uint8_t large) {
    if (port >= PORT_COUNT) return;
    Port& p = g_ports[port];
    WORD left = WORD(large) * 257u, right = small ? 65535u : 0u;
    if (left == p.left_motor && right == p.right_motor) return;
    if (!g_set_state || p.slot < 0) return;
    XINPUT_VIBRATION vibration{left, right};
    DWORD status = g_set_state((DWORD)p.slot, &vibration);
    if (status == ERROR_SUCCESS) {
        p.left_motor = left; p.right_motor = right;
    } else if (status == ERROR_DEVICE_NOT_CONNECTED) {
        p.left_motor = p.right_motor = 0;
    }                                  // transient failure leaves the command outstanding
}

// g_lock held, foreground only. Poll connected devices every frame, including
// unassigned ones, so a short press can claim a player. Throttle only empty slots.
// Reconnect existing owners first; another player's controller never changes ports.
void scan() {
    if (!g_get_state) return;
    ULONGLONG now = GetTickCount64();
    bool probe_empty = now >= g_next_scan;
    if (probe_empty) g_next_scan = now + 1000;
    bool used[4] = {};
    for (const Port& p : g_ports) if (p.slot >= 0 && p.slot < 4) used[p.slot] = true;
    XINPUT_STATE states[4] = {};
    bool present[4] = {};
    for (int slot = 0; slot < 4; ++slot) {
        if (!g_connected[slot] && !used[slot] && !probe_empty) continue;
        present[slot] = g_get_state((DWORD)slot, &states[slot]) == ERROR_SUCCESS;
        g_connected[slot] = present[slot];
    }
    auto attach = [&](unsigned port, int slot) {
        Port& p = g_ports[port];
        p.slot = p.preferred_slot = slot;
        used[slot] = true;
        p.name = "XInput controller " + std::to_string(slot + 1);
        ++p.generation;
        say("controller attached: " + p.name + " (port " + std::to_string(port + 1) + ")");
    };
    auto available = [&](int slot) {
        if (slot < 0 || slot >= 4 || used[slot]) return false;
        return present[slot];
    };
    for (unsigned port = 0; port < PORT_COUNT; ++port) {
        Port& p = g_ports[port];
        if (!p.test_attached && p.slot < 0 && available(p.preferred_slot)) attach(port, p.preferred_slot);
    }
    for (unsigned port = 0; port < PORT_COUNT; ++port) {
        if (g_ports[port].slot >= 0 || g_ports[port].test_attached) continue;
        for (int slot = 0; slot < 4; ++slot) {
            bool reserved = false;
            for (unsigned other = 0; other < PORT_COUNT; ++other)
                if (other != port && g_ports[other].preferred_slot == slot) reserved = true;
            if (reserved || !available(slot)) continue;
            rta::PadState input;
            from_xinput(states[slot].Gamepad, input);
            if (!input.buttons && input.lx == 128 && input.ly == 128 && input.rx == 128 && input.ry == 128) continue;
            attach(port, slot);
            break;
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
    say("controllers: press a button on player 1's controller, then player 2's; keyboard also controls player 1");
}

bool read(unsigned port, rta::PadState& state) {
    if (port >= PORT_COUNT) return false;
    std::lock_guard<std::mutex> hold(g_lock);
    Port& p = g_ports[port];
    if (p.test_attached) {
        motors(port, 0, 0);             // retry a failed stop after this port's synthetic takeover
        state.buttons = p.test_buttons;
        if (p.test_values[4] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_L2;
        if (p.test_values[5] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_R2;
        stick(p.test_values[0], p.test_values[1], state.lx, state.ly);
        stick(p.test_values[2], p.test_values[3], state.rx, state.ry);
        return true;
    }
    if (!in_front()) { motors(port, 0, 0); return false; }
    scan();
    if (p.slot < 0) return false;
    XINPUT_STATE state_now;
    if (g_get_state((DWORD)p.slot, &state_now) != ERROR_SUCCESS) {
        say("controller detached: " + p.name + " (port " + std::to_string(port + 1) + ")");
        motors(port, 0, 0);
        p.left_motor = p.right_motor = 0;
        p.preferred_slot = p.slot;
        p.slot = -1;
        p.name.clear();
        ++p.generation;
        g_next_scan = GetTickCount64() + 1000;
        return false;
    }
    if (!in_front()) {
        motors(port, 0, 0);
        return false;
    }
    from_xinput(state_now.Gamepad, state);
    return true;
}

bool read(rta::PadState& state) { return read(0, state); }

void rumble(unsigned port, uint8_t small, uint8_t large) {
    if (port >= PORT_COUNT) return;
    std::lock_guard<std::mutex> hold(g_lock);
    if (g_ports[port].test_attached) {
        motors(port, 0, 0);             // synthetic input can only release existing physical motors
        return;
    }
    if (!in_front()) small = large = 0;
    motors(port, small, large);
}

void rumble(uint8_t small, uint8_t large) { rumble(0, small, large); }

void release_motors() {
    std::lock_guard<std::mutex> hold(g_lock);
    for (unsigned port = 0; port < PORT_COUNT; ++port) motors(port, 0, 0);
}

std::string name(unsigned port) {
    if (port >= PORT_COUNT) return {};
    std::lock_guard<std::mutex> hold(g_lock);
    return g_ports[port].test_attached ? std::string("test controller") : g_ports[port].name;
}
std::string name() { return name(0); }

uint32_t generation(unsigned port) { return port < PORT_COUNT ? g_ports[port].generation.load() : 0; }
uint32_t generation() { return generation(0); }

int xinput_slot(unsigned port) {
    if (port >= PORT_COUNT) return -1;
    std::lock_guard<std::mutex> hold(g_lock);
    return g_ports[port].slot;           // backing physical slot even during synthetic takeover
}

void test(unsigned port, const std::string& command, uint16_t buttons, const float values[6]) {
    if (port >= PORT_COUNT) return;
    std::lock_guard<std::mutex> hold(g_lock);
    Port& p = g_ports[port];
    if (command == "connect") {
        motors(port, 0, 0);
        p.test_attached = true;
        p.test_buttons = 0;
        for (float& v : p.test_values) v = 0;
        ++p.generation;
        say("controller attached: test controller (port " + std::to_string(port + 1) + ")");
    } else if (command == "disconnect") {
        if (p.test_attached) {
            ++p.generation;
            say("controller detached: test controller (port " + std::to_string(port + 1) + ")");
        }
        p.test_attached = false;
    } else if (command == "set" || command == "none") {
        p.test_buttons = command == "none" ? 0 : buttons;
        for (int k = 0; k < 6; ++k) p.test_values[k] = command == "none" ? 0 : values[k];
    }
}
void test(const std::string& command, uint16_t buttons, const float values[6]) { test(0, command, buttons, values); }

void keep_timers() {}

}  // namespace hostpad
#endif  // _WIN32
