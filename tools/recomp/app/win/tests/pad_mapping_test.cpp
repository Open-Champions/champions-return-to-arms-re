// Isolated QA harness: includes the production Windows pad implementation.
// No window, input injection, controller driver or calibration is used.
#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <string>
#pragma STDC FENV_ACCESS ON
#include "../../pad_win.cpp"
static int cases=0, failures=0;
static void expect(const char* name, const XINPUT_GAMEPAD& raw, unsigned buttons,
                   int lx=128,int ly=128,int rx=128,int ry=128) {
 rta::PadState state;
 hostpad::from_xinput(raw,state);
 ++cases;
 bool pass=state.buttons==buttons && state.lx==lx && state.ly==ly && state.rx==rx && state.ry==ry;
 if(!pass)++failures;
 std::printf("%s %s buttons=%04x expected=%04x sticks=%u,%u,%u,%u expected=%d,%d,%d,%d\n",
   pass?"PASS":"FAIL",name,state.buttons,buttons,state.lx,state.ly,state.rx,state.ry,lx,ly,rx,ry);
}
int main() {
 std::fesetround(FE_TOWARDZERO);
 std::printf("rounding=FE_TOWARDZERO actual=%d threshold_literal=%a\n",std::fegetround(),double(0.30f));
 struct ButtonCase {const char* name;WORD raw;unsigned ps2;};
 const ButtonCase map[]={
 {"dpad_up",XINPUT_GAMEPAD_DPAD_UP,0x0010},{"dpad_down",XINPUT_GAMEPAD_DPAD_DOWN,0x0040},
 {"dpad_left",XINPUT_GAMEPAD_DPAD_LEFT,0x0080},{"dpad_right",XINPUT_GAMEPAD_DPAD_RIGHT,0x0020},
 {"start",XINPUT_GAMEPAD_START,0x0008},{"back",XINPUT_GAMEPAD_BACK,0x0001},
 {"l3",XINPUT_GAMEPAD_LEFT_THUMB,0x0002},{"r3",XINPUT_GAMEPAD_RIGHT_THUMB,0x0004},
 {"lb",XINPUT_GAMEPAD_LEFT_SHOULDER,0x0400},{"rb",XINPUT_GAMEPAD_RIGHT_SHOULDER,0x0800},
 {"a_cross",XINPUT_GAMEPAD_A,0x4000},{"b_circle",XINPUT_GAMEPAD_B,0x2000},
 {"x_square",XINPUT_GAMEPAD_X,0x8000},{"y_triangle",XINPUT_GAMEPAD_Y,0x1000}};
 XINPUT_GAMEPAD raw{};
 expect("neutral",raw,0);
 for(auto test:map) {raw={};raw.wButtons=test.raw;expect(test.name,raw,test.ps2);}
 raw={};raw.wButtons=0xf3ff;expect("all_fourteen_buttons",raw,0xfcff);
 raw={};raw.bLeftTrigger=76;expect("left_trigger_76_off",raw,0);
 raw.bLeftTrigger=77;expect("left_trigger_77_on",raw,0x0100);
 raw.bLeftTrigger=255;expect("left_trigger_255_on",raw,0x0100);
 raw={};raw.bRightTrigger=76;expect("right_trigger_76_off",raw,0);
 raw.bRightTrigger=77;expect("right_trigger_77_on",raw,0x0200);
 raw.bRightTrigger=255;expect("right_trigger_255_on",raw,0x0200);
 raw.bLeftTrigger=77;raw.bRightTrigger=77;expect("both_triggers_77_on",raw,0x0300);
 raw={};raw.sThumbLX=4915;expect("left_x_inside_deadzone",raw,0);
 raw={};raw.sThumbLY=-4915;expect("left_y_inside_deadzone",raw,0);
 raw={};raw.sThumbRX=4915;raw.sThumbRY=-1;expect("right_inside_deadzone",raw,0);
 raw={};raw.sThumbLX=5120;expect("left_x_just_outside_visible_deadzone",raw,0,129,128);
 raw={};raw.sThumbLX=32767;expect("left_x_max",raw,0,255,128);
 raw={};raw.sThumbLX=-32768;expect("left_x_min",raw,0,0,128);
 raw={};raw.sThumbLY=32767;expect("left_y_up",raw,0,128,0);
 raw={};raw.sThumbLY=-32768;expect("left_y_down",raw,0,128,255);
 raw={};raw.sThumbRX=32767;expect("right_x_max",raw,0,128,128,255,128);
 raw={};raw.sThumbRX=-32768;expect("right_x_min",raw,0,128,128,0,128);
 raw={};raw.sThumbRY=32767;expect("right_y_up",raw,0,128,128,128,0);
 raw={};raw.sThumbRY=-32768;expect("right_y_down",raw,0,128,128,128,255);
 raw={};raw.sThumbLX=16384;expect("left_x_half_rescaled",raw,0,180,128);
 raw={};raw.sThumbLX=-16384;expect("left_x_negative_half_rescaled",raw,0,75,128);
 raw={};raw.sThumbLX=32767;raw.sThumbLY=32767;expect("left_diagonal_radially_limited",raw,0,218,37);
 raw={};raw.sThumbRX=-32768;raw.sThumbRY=-32768;expect("right_diagonal_radially_limited",raw,0,128,128,37,218);
 std::printf("RESULT %d cases, %d failures; production from_xinput; no physical-device proof\n",cases,failures);
 return failures?1:0;
}
