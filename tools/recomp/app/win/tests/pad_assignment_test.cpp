// Production two-player assignment with mocked XInput; no device or motor injection.
#include "../../pad_win.cpp"
#include <cstdio>
#include <vector>
static bool connected[4];
static XINPUT_GAMEPAD values[4];
static unsigned polls[4];
struct Sent { DWORD slot; WORD left, right; };
static std::vector<Sent> sent;
static DWORD WINAPI get(DWORD slot, XINPUT_STATE* state) {
    ++polls[slot]; *state = {}; state->Gamepad = values[slot];
    return connected[slot] ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
}
static DWORD WINAPI set(DWORD slot, XINPUT_VIBRATION* state) {
    sent.push_back({slot, state->wLeftMotorSpeed, state->wRightMotorSpeed}); return ERROR_SUCCESS;
}
static int checks, failures;
static void check(bool pass, const char* label) { ++checks; if (!pass) { ++failures; std::printf("FAIL %s\n", label); } }
static void reset() {
    for (int i=0;i<4;++i) { connected[i]=false; values[i]={}; polls[i]=0; hostpad::g_connected[i]=false; }
    for (auto& p:hostpad::g_ports) {
        p.slot=p.preferred_slot=-1; p.left_motor=p.right_motor=0; p.generation=0;
        p.name.clear();p.test_attached=false;p.test_buttons=0;for(auto& v:p.test_values)v=0;
    }
    hostpad::g_next_scan=0; hostpad::g_window=nullptr; hostpad::g_log=nullptr;
    hostpad::g_get_state=get; hostpad::g_set_state=set; sent.clear();
}
int main() {
    reset(); connected[0]=connected[1]=connected[2]=true;
    // Matches the idle lower-slot drift observed during the Windows/Parsec diagnosis.
    values[0].sThumbLX=-3356;values[0].sThumbLY=-1869;values[0].sThumbRX=-3255;values[0].sThumbRY=-848;
    rta::PadState a,b;
    check(!hostpad::read(0,a), "idle virtual pads do not occupy player one");
    check(hostpad::xinput_slot(0)==-1&&hostpad::xinput_slot(1)==-1,"both players initially unassigned");
    values[2].wButtons=XINPUT_GAMEPAD_A;
    check(hostpad::read(0,a)&&a.buttons==rta::PAD_CROSS,"a short higher-slot press reaches player one");
    check(hostpad::xinput_slot(0)==2,"first used controller owns player one regardless of Windows order");
    check(hostpad::xinput_slot(1)==-1,"idle Parsec device does not preempt player two");
    check(polls[3]==1,"empty XInput slot is throttled");
    values[1].wButtons=XINPUT_GAMEPAD_START;
    check(hostpad::read(1,b)&&b.buttons==rta::PAD_START,"second used controller reaches player two immediately");
    check(hostpad::xinput_slot(0)==2&&hostpad::xinput_slot(1)==1,"owners remain distinct");
    values[2].wButtons=XINPUT_GAMEPAD_X;values[2].sThumbLX=-32768;
    values[1].wButtons=XINPUT_GAMEPAD_B;values[1].sThumbLY=32767;
    hostpad::read(0,a);hostpad::read(1,b);
    check(a.buttons==rta::PAD_SQUARE&&a.lx==0&&a.ly==128,"player one keeps its own buttons and stick");
    check(b.buttons==rta::PAD_CIRCLE&&b.lx==128&&b.ly==0,"player two keeps its own buttons and stick");
    hostpad::rumble(1,1,128);
    check(sent.size()==1&&sent[0].slot==1&&sent[0].left==32896&&sent[0].right==65535,"player two rumble uses its owning slot");
    hostpad::release_motors();
    check(sent.size()==2&&sent.back().slot==1&&!sent.back().left&&!sent.back().right,"all-player cleanup releases player two");
    connected[2]=false;
    check(!hostpad::read(0,a)&&hostpad::xinput_slot(0)==-1,"disconnect clears only the disconnected owner");
    check(hostpad::read(1,b)&&hostpad::xinput_slot(1)==1,"player two is not promoted to player one");
    connected[2]=true;values[2]={};hostpad::g_next_scan=0;
    check(hostpad::read(0,a)&&hostpad::xinput_slot(0)==2,"reconnected controller retains its old player while neutral");
    check(a.buttons==0&&a.lx==128&&a.ly==128,"release returns neutral input");
    const float axes[6]={};hostpad::test(1,"connect",rta::PAD_UP,axes);
    hostpad::test(1,"set",rta::PAD_UP,axes);hostpad::read(1,b);
    check(b.buttons==rta::PAD_UP&&hostpad::xinput_slot(0)==2,"synthetic player two is isolated from player one");
    hostpad::test(1,"disconnect",0,nullptr);hostpad::read(1,b);
    check(b.buttons==rta::PAD_CIRCLE&&hostpad::xinput_slot(1)==1,"synthetic disconnect restores the same physical owner");
    reset();connected[2]=true;values[2].wButtons=XINPUT_GAMEPAD_A;hostpad::g_window=reinterpret_cast<HWND>(std::uintptr_t(1));
    check(!hostpad::read(0,a)&&hostpad::xinput_slot(0)==-1,"background game never claims a controller");
    reset();hostpad::g_get_state=nullptr;
    check(!hostpad::read(0,a)&&!hostpad::read(1,b),"missing XInput library is safe for both players");
    std::printf("RESULT %d assignment checks, %d failures\n",checks,failures);
    return failures?1:0;
}
