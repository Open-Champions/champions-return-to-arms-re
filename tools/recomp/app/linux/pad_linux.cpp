// pad_linux.cpp - pad_host.h for Linux: game controllers through SDL2's game controller API
// (its database maps Xbox, PlayStation, Switch and most others onto one layout).
//
// The map and the dead zones are pad_mac.mm's and pad_win.cpp's: A B X Y (south, east,
// west, north) are cross circle square triangle, the shoulders L1 R1, the triggers L2 R2
// (pressed from 0.30), the stick buttons L3 R3, Back is Select; a stick inside 0.15 of its
// centre is at rest and outside it the rest of the travel is spread over the whole range.
//
// SDL's controller state is updated by the event loop of the window's thread; that thread
// calls hostpad::poll() after every round of events, which copies the first controller's
// state into a snapshot.  read() (the game's thread, every vertical blank) takes the snapshot.
#include "pad_host.h"

#include <SDL.h>

#include <atomic>
#include <cmath>
#include <mutex>

namespace hostpad {
namespace {

const float STICK_DEAD_ZONE = 0.15f;
const float TRIGGER_PRESSED = 0.30f;

void (*g_log)(const std::string&);
std::mutex g_lock;
SDL_GameController* g_pad = nullptr;
SDL_JoystickID g_pad_id = -1;
std::string g_name;
std::atomic<uint32_t> g_generation{0};
bool g_have = false, g_in_front = true;
rta::PadState g_state;

bool g_test_attached;
uint16_t g_test_buttons;
float g_test_values[6];

uint8_t axis_byte(float v) {
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
float axis(SDL_GameController* c, SDL_GameControllerAxis a) {
    int v = SDL_GameControllerGetAxis(c, a);
    return v < 0 ? (float)v / 32768.0f : (float)v / 32767.0f;
}
void say(const std::string& line) { if (g_log) g_log(line); }

void open_first() {                     // with g_lock held
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        if (!SDL_IsGameController(i)) continue;
        if (SDL_GameController* c = SDL_GameControllerOpen(i)) {
            g_pad = c;
            g_pad_id = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(c));
            const char* n = SDL_GameControllerName(c);
            g_name = n ? n : "game controller";
            g_generation++;
            say("controller attached: " + g_name + " (port 1)");
            return;
        }
    }
}

}  // namespace

void start(void (*log)(const std::string& line)) {
    std::lock_guard<std::mutex> hold(g_lock);
    g_log = log;
    if (SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) != 0) { say(std::string("controllers: SDL could not start them: ") + SDL_GetError() + "; keyboard only"); return; }
    say("controllers: SDL2 game controllers");
    open_first();
}

// The window's thread, after its events (SDL_CONTROLLERDEVICEADDED/REMOVED among them).
void poll(bool in_front) {
    std::lock_guard<std::mutex> hold(g_lock);
    g_in_front = in_front;
    if (g_pad && !SDL_GameControllerGetAttached(g_pad)) {
        say("controller detached: " + g_name);
        SDL_GameControllerClose(g_pad);
        g_pad = nullptr;
        g_pad_id = -1;
        g_name.clear();
        g_generation++;
    }
    if (!g_pad && SDL_WasInit(SDL_INIT_GAMECONTROLLER)) open_first();
    g_have = g_pad != nullptr;
    if (!g_pad) return;
    static const struct { SDL_GameControllerButton b; uint16_t pad; } map[] = {
        {SDL_CONTROLLER_BUTTON_DPAD_UP, rta::PAD_UP}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, rta::PAD_DOWN},
        {SDL_CONTROLLER_BUTTON_DPAD_LEFT, rta::PAD_LEFT}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, rta::PAD_RIGHT},
        {SDL_CONTROLLER_BUTTON_START, rta::PAD_START}, {SDL_CONTROLLER_BUTTON_BACK, rta::PAD_SELECT},
        {SDL_CONTROLLER_BUTTON_LEFTSTICK, rta::PAD_L3}, {SDL_CONTROLLER_BUTTON_RIGHTSTICK, rta::PAD_R3},
        {SDL_CONTROLLER_BUTTON_LEFTSHOULDER, rta::PAD_L1}, {SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, rta::PAD_R1},
        {SDL_CONTROLLER_BUTTON_A, rta::PAD_CROSS}, {SDL_CONTROLLER_BUTTON_B, rta::PAD_CIRCLE},
        {SDL_CONTROLLER_BUTTON_X, rta::PAD_SQUARE}, {SDL_CONTROLLER_BUTTON_Y, rta::PAD_TRIANGLE}};
    uint16_t buttons = 0;
    for (auto& m : map) if (SDL_GameControllerGetButton(g_pad, m.b)) buttons |= m.pad;
    if (axis(g_pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) >= TRIGGER_PRESSED) buttons |= rta::PAD_L2;
    if (axis(g_pad, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >= TRIGGER_PRESSED) buttons |= rta::PAD_R2;
    g_state.buttons = buttons;
    // SDL's y axes grow downward: up is negative
    stick(axis(g_pad, SDL_CONTROLLER_AXIS_LEFTX), -axis(g_pad, SDL_CONTROLLER_AXIS_LEFTY), g_state.lx, g_state.ly);
    stick(axis(g_pad, SDL_CONTROLLER_AXIS_RIGHTX), -axis(g_pad, SDL_CONTROLLER_AXIS_RIGHTY), g_state.rx, g_state.ry);
}

bool read(rta::PadState& state) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (g_test_attached) {
        state.buttons = g_test_buttons;
        if (g_test_values[4] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_L2;
        if (g_test_values[5] >= TRIGGER_PRESSED) state.buttons |= rta::PAD_R2;
        stick(g_test_values[0], g_test_values[1], state.lx, state.ly);
        stick(g_test_values[2], g_test_values[3], state.rx, state.ry);
        return true;
    }
    if (!g_have || !g_in_front) return false;   // a real controller is listened to only by the window in front
    state = g_state;
    return true;
}

std::string name() {
    std::lock_guard<std::mutex> hold(g_lock);
    return g_test_attached ? std::string("test controller") : g_name;
}

uint32_t generation() { return g_generation; }

void test(const std::string& command, uint16_t buttons, const float values[6]) {
    std::lock_guard<std::mutex> hold(g_lock);
    if (command == "connect") {
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
