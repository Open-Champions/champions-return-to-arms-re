// Isolated production implementation test. Fake callbacks never contact a controller.
// Build with -Itools/recomp/rt -Itools/recomp/app -static -luser32 -lkernel32.
#include "../../pad_win.cpp"
#include <cstdio>
#include <vector>
struct Sent { DWORD slot; WORD left, right; };
static std::vector<Sent> sent;
static DWORD send_result=ERROR_SUCCESS, read_result=ERROR_SUCCESS;
static DWORD WINAPI send_state(DWORD slot, XINPUT_VIBRATION* value) {
    sent.push_back({slot,value->wLeftMotorSpeed,value->wRightMotorSpeed});
    return send_result;
}
static DWORD WINAPI read_state(DWORD, XINPUT_STATE* state) {
    *state={};
    return read_result;
}
static int checks=0,failures=0;
static void check(bool pass,const char* name) {
    ++checks;
    if(!pass) {++failures;std::printf("FAIL %s\n",name);}
}
static void reset() {
    hostpad::g_slot=2;
    hostpad::g_window=nullptr;
    hostpad::g_test_attached=false;
    hostpad::g_get_state=read_state;
    hostpad::g_set_state=send_state;
    hostpad::g_left_motor=hostpad::g_right_motor=0;
    send_result=read_result=ERROR_SUCCESS;
    sent.clear();
}
int main() {
    reset();
    hostpad::rumble(1,128);
    check(sent.size()==1 && sent.back().slot==2,"first attached slot receives rumble");
    check(sent.back().left==32896 && sent.back().right==65535,"PS2 large amplitude and small on/off map to XInput motors");
    hostpad::rumble(1,128);
    check(sent.size()==1,"unchanged motor command is coalesced");
    hostpad::rumble(0,0);
    check(sent.size()==2 && sent.back().left==0 && sent.back().right==0,"explicit shutdown releases both motors");
    hostpad::rumble(0,0);
    check(sent.size()==2,"neutral controller receives no repeated writes");
    reset();
    hostpad::rumble(255,255);
    check(sent.size()==1 && sent.back().left==65535 && sent.back().right==65535,"maximum and nonzero small motor are bounded");
    hostpad::g_window=reinterpret_cast<HWND>(std::uintptr_t(1));
    rta::PadState state;
    check(!hostpad::read(state),"real pad is suppressed out of foreground");
    check(sent.size()==2 && sent.back().left==0 && sent.back().right==0,"background read stops vibration");
    hostpad::read(state);
    check(sent.size()==2,"background polling does not interfere with other applications");
    hostpad::rumble(1,255);
    check(sent.size()==2,"background rumble cannot start motors");
    reset();
    hostpad::rumble(1,200);
    read_result=ERROR_DEVICE_NOT_CONNECTED;
    check(!hostpad::read(state) && hostpad::g_slot==-1,"detach removes the active slot");
    check(sent.size()==2 && sent.back().left==0 && sent.back().right==0,"detach releases motors before dropping slot");
    reset();
    hostpad::rumble(1,200);
    hostpad::test("connect",0,nullptr);
    check(sent.size()==2 && sent.back().left==0 && sent.back().right==0,"synthetic takeover releases real motors");
    hostpad::rumble(1,255);
    check(sent.size()==2,"synthetic pad never rumbles hardware");
    hostpad::test("disconnect",0,nullptr);
    hostpad::rumble(0,255);
    check(sent.size()==3 && sent.back().left==65535 && sent.back().right==0,"real pad works after synthetic disconnect");
    reset();
    hostpad::g_set_state=nullptr;
    hostpad::rumble(1,255);
    check(sent.empty(),"missing optional XInputSetState is safe");
    reset();
    hostpad::g_slot=-1;
    hostpad::rumble(1,255);
    check(sent.empty(),"no connected slot is safe");
    reset();
    hostpad::rumble(1,128);
    send_result=ERROR_GEN_FAILURE;
    hostpad::rumble(0,0);
    send_result=ERROR_SUCCESS;
    hostpad::rumble(0,0);
    check(sent.size()==3 && hostpad::g_left_motor==0 && hostpad::g_right_motor==0,"failed stop is retried until successful");
    reset();
    hostpad::rumble(1,128);
    send_result=ERROR_GEN_FAILURE;
    hostpad::test("connect",0,nullptr);
    check(hostpad::g_test_attached && hostpad::g_left_motor!=0,"failed takeover stop stays outstanding");
    send_result=ERROR_SUCCESS;
    hostpad::read(state);
    check(sent.size()==3 && sent.back().left==0 && sent.back().right==0,"synthetic read retries physical stop");
    hostpad::rumble(1,255);
    check(sent.size()==3,"synthetic pad still cannot start motors after retry");
    reset();
    send_result=ERROR_GEN_FAILURE;
    hostpad::rumble(1,128);
    send_result=ERROR_SUCCESS;
    hostpad::rumble(1,128);
    check(sent.size()==2 && hostpad::g_left_motor==32896,"failed start is retried instead of cached");
    std::printf("RESULT %d production rumble checks, %d failures; no physical vibration proof\n",checks,failures);
    return failures?1:0;
}
