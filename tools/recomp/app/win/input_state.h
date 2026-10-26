// Native Windows input state, shared by the window handler and its regression test.
// Only the window thread mutates Keyboard; the game reads its published atomic mask.
#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include "iface.h"
#include <array>
#include <cstdint>

namespace wininput {
enum : std::uint32_t {
    KEY_STICK_UP = 1u << 16, KEY_STICK_DOWN = 1u << 17,
    KEY_STICK_LEFT = 1u << 18, KEY_STICK_RIGHT = 1u << 19
};

inline std::uint32_t key_bits(std::uint32_t key) {
    switch (key) {
    case 'W': return KEY_STICK_UP;
    case 'S': return KEY_STICK_DOWN;
    case 'A': return KEY_STICK_LEFT;
    case 'D': return KEY_STICK_RIGHT;
    case VK_UP: return rta::PAD_UP;
    case VK_DOWN: return rta::PAD_DOWN;
    case VK_LEFT: return rta::PAD_LEFT;
    case VK_RIGHT: return rta::PAD_RIGHT;
    case 'I': return rta::PAD_TRIANGLE;
    case 'J': return rta::PAD_SQUARE;
    case 'K': return rta::PAD_CROSS;
    case 'L': return rta::PAD_CIRCLE;
    case 'Q': return rta::PAD_L1;
    case 'E': return rta::PAD_R1;
    case '1': case VK_NUMPAD1: return rta::PAD_L2;
    case '3': case VK_NUMPAD3: return rta::PAD_R2;
    case 'X': return rta::PAD_L3;
    case 'C': return rta::PAD_R3;
    case VK_RETURN: return rta::PAD_START;
    case VK_BACK: return rta::PAD_SELECT;
    case VK_SPACE: return rta::PAD_SQUARE;
    case VK_SHIFT: case VK_LSHIFT: case VK_RSHIFT: return rta::PAD_R1;
    case VK_TAB: return rta::PAD_R3;
    default: return 0;
    }
}

class Keyboard {
    // Scan code and the extended flag identify the physical key even when NumLock
    // changes its virtual key before release. Posted script keys have no scan code.
    static constexpr unsigned COUNT = 512 + 256;
    std::array<std::uint32_t, COUNT> held_{};
    static unsigned identity(std::uint32_t key, std::uintptr_t message) {
        // lParam bits 16..23 hold the scan code; bit 24 distinguishes extended
        // keys (for example arrows from numpad keys). Reserve slots 512..767
        // for synthetic messages without a scan code; COUNT is the invalid sentinel.
        unsigned scan = unsigned((message >> 16) & 255u);
        return scan ? scan | unsigned((message >> 16) & 256u) : key < 256 ? 512 + key : COUNT;
    }
public:
    std::uint32_t bits() const {
        std::uint32_t result = 0;
        for (auto held : held_) result |= held;
        return result;
    }
    std::uint32_t key(std::uint32_t key, std::uintptr_t message, bool down) {
        unsigned id = identity(key, message);
        if (id < held_.size()) held_[id] = down ? key_bits(key) : 0;
        return bits();
    }
    void clear() { held_.fill(0); }
};

inline int mouse_button(UINT message, WPARAM parameter) {
    switch (message) {
    case WM_LBUTTONDOWN: case WM_LBUTTONUP: return 0;
    case WM_RBUTTONDOWN: case WM_RBUTTONUP: return 1;
    case WM_MBUTTONDOWN: case WM_MBUTTONUP: return 2;
    case WM_XBUTTONDOWN: case WM_XBUTTONUP:
        return HIWORD(parameter) == XBUTTON1 ? 3 : HIWORD(parameter) == XBUTTON2 ? 4 : -1;
    default: return -1;
    }
}
inline bool mouse_down(UINT message) {
    return message == WM_LBUTTONDOWN || message == WM_RBUTTONDOWN ||
           message == WM_MBUTTONDOWN || message == WM_XBUTTONDOWN;
}
}  // namespace wininput
