# HUD fade state at a script host boundary

RTA US v2.00, measured with `tools/difftest_fade_lifetime.py` and the owner's
read-only executable. The executable image starts `g_hudFade` (0x4f66ac) at
zero. `hud_setFade` (0x1df5d0) stores 0 or 128; `hud_stepFade` (0x1df5ec)
adds its signed delta and returns the new value. The two reset and two step
probes match exactly. This confirms the earlier script effect contract.

The direct-call scan found no call to `hud_setFade` in `game_loadLevel`
(0x1e55c0 through the loader's end). An emulated loader body with external
services stubbed retained a planted fade of 37. This is evidence against an
unconditional *direct* fade reset in the loader, not proof about every
callee or front-end transition. No tested source establishes a new 0 or 128
reset on each level entry. Keep the word across fade operations and, in a
client that replaces its script host at a level boundary, carry its known
presentation value forward. For a newly created process with no prior fade,
the observed executable image supplies zero. Other presentation owners may
call the setter, so a future unified HUD owner must share this word.

The difftest requires a private executable supplied by the operator. It
prints counts and status only and does not save source bytes.
