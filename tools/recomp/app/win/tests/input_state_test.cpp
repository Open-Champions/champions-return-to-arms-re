// Build on Windows with the pinned target compiler, -std=c++17 -Itools/recomp/rt.
// Tests the production state and message helpers, without creating a window.
#include "../input_state.h"
#include <cstdio>
#include <string>

static int checks = 0, failures = 0;
static void check(bool pass, const std::string& name) {
    ++checks;
    if (!pass) { ++failures; std::printf("FAIL %s\n", name.c_str()); }
}
static std::uintptr_t scan(unsigned code, bool extended = false) {
    return (std::uintptr_t(code) << 16) | (extended ? std::uintptr_t(1) << 24 : 0);
}
struct Key { unsigned code, scan; };
static void aliases(const char* name, Key a, Key b, std::uint32_t mask) {
    for (int press_order = 0; press_order < 2; ++press_order)
        for (int release_order = 0; release_order < 2; ++release_order) {
            wininput::Keyboard keyboard;
            Key pair[] = {a,b};
            auto key = [&](int k, bool down) {
                return keyboard.key(pair[k].code, scan(pair[k].scan), down);
            };
            std::string label = std::string(name) + "/" + std::to_string(press_order) + "/" + std::to_string(release_order);
            check(key(press_order, true) == mask, label + " first press");
            check(key(1-press_order, true) == mask, label + " overlapping press");
            check(key(release_order, false) == mask, label + " first release keeps alias");
            check(key(1-release_order, false) == 0, label + " last release clears");
        }
}
int main() {
    aliases("block", {'E',0x12}, {VK_SHIFT,0x2a}, rta::PAD_R1);
    aliases("use", {'J',0x24}, {VK_SPACE,0x39}, rta::PAD_SQUARE);
    aliases("map", {'C',0x2e}, {VK_TAB,0x0f}, rta::PAD_R3);
    aliases("left trigger", {'1',0x02}, {VK_NUMPAD1,0x4f}, rta::PAD_L2);
    aliases("right trigger", {'3',0x04}, {VK_NUMPAD3,0x51}, rta::PAD_R2);
    aliases("both physical shifts", {VK_SHIFT,0x2a}, {VK_SHIFT,0x36}, rta::PAD_R1);
    {
        wininput::Keyboard keyboard;
        keyboard.key(VK_NUMPAD1, scan(0x4f), true);
        check(keyboard.key(VK_END, scan(0x4f), false) == 0, "NumLock changes virtual key before release");
        keyboard.key(VK_UP, scan(0x48), true);
        keyboard.key(VK_UP, scan(0x48,true), true);
        check(keyboard.key(VK_UP, scan(0x48), false) == rta::PAD_UP, "extended arrow differs from numpad arrow");
        check(keyboard.key(VK_UP, scan(0x48,true), false) == 0, "extended arrow final release");
        keyboard.key('E',0,true); keyboard.key(VK_SHIFT,0,true);
        check(keyboard.key('E',0,false) == rta::PAD_R1, "posted script aliases remain independent");
        check(keyboard.key(VK_SHIFT,0,false) == 0, "posted alias final release");
        keyboard.key('K',scan(0x25),true); keyboard.key('K',scan(0x25),true);
        check(keyboard.key('K',scan(0x25),false) == 0, "repeat does not count another hold");
        keyboard.key('E',scan(0x12),true);
        keyboard.key(VK_SHIFT,scan(0x2a),true);
        keyboard.key('W',scan(0x11),true);
        check(keyboard.bits() == (rta::PAD_R1|wininput::KEY_STICK_UP), "different actions aggregate");
        keyboard.clear();
        check(keyboard.bits() == 0, "focus loss clears every physical key");
        check(keyboard.key(VK_SHIFT,scan(0x2a),false) == 0, "late release after focus loss stays neutral");
        check(keyboard.key('K',scan(0x25),true) == rta::PAD_CROSS, "fresh input after focus loss works");
        keyboard.clear();
        check(keyboard.key(999,0,true) == 0, "out of range virtual key ignored");
    }
    const UINT down[] = {WM_LBUTTONDOWN,WM_RBUTTONDOWN,WM_MBUTTONDOWN,WM_XBUTTONDOWN,WM_XBUTTONDOWN};
    const UINT up[] = {WM_LBUTTONUP,WM_RBUTTONUP,WM_MBUTTONUP,WM_XBUTTONUP,WM_XBUTTONUP};
    for (unsigned button=0;button<5;++button) {
        WPARAM parameter=button<3 ? 0 : WPARAM(button==3?XBUTTON1:XBUTTON2)<<16;
        check(wininput::mouse_button(down[button],parameter)==int(button), "mouse down index "+std::to_string(button));
        check(wininput::mouse_button(up[button],parameter)==int(button), "mouse up index "+std::to_string(button));
        check(wininput::mouse_down(down[button]), "mouse down edge "+std::to_string(button));
        check(!wininput::mouse_down(up[button]), "mouse up edge "+std::to_string(button));
    }
    check(wininput::mouse_button(WM_XBUTTONDOWN,0)==-1,"invalid side button ignored");
    check(wininput::mouse_button(WM_MOUSEMOVE,0)==-1,"non-button message ignored");
    std::printf("RESULT %d production input checks, %d failures\n",checks,failures);
    return failures ? 1 : 0;
}
