# Live producers for the in-game HUD

SLUS-20973 v2.00. This note closes the display values that
[hud-input-producers.md](hud-input-producers.md) left at the event boundary:
the health and mana bars, the experience line, the one-line message, and
automap reveal from a world position that is not an integer cell centre.
Quick-slot spells and potion items stay the executed contracts in
[hud-quickslots.md](hud-quickslots.md) and hud-input-producers.md sections 1
and 2.

**Evidence.** Observed (O) is an addressed instruction or call. Executed (E)
means `tools/ee_emu.py` ran that original function and `tools/ref_hud_live.py`
or `reveal_world` matched it. Unknown (U) is not established. No game or
console was run. Float results are the default `ee_emu` FPU, not a claim
about the console's last bit.

From the worktree root, with the standard library `dis` imported first
(`tools/dis.py` shadows it):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["tools/difftest_hud_live.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["tools/difftest_hud_inputs.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
```

Repeat each with `--seed 7`. Both seeds: live probe 166 cases and 0 seed
draws (regen 70, bars 25, experience 22, messages 49); automap probe 608
cases and 0 seed draws, including 48 fractional reveals. The stdout is
`local/hud-live-20973.log`, `local/hud-live-7.log`,
`local/hud-inputs-20973.log` and `local/hud-inputs-7.log`. The analysis
suite was 736 tests, 0 failures, in 4.871s (`local/unittest-discover.log`).

## 1. Health and mana bars

The bars read the player record `0x4d8af0 + slot*0x4c30`, not a second copy
on the object. Health is float `+0xac` over `+0xb0`. Mana is float `+0xc0`
over `+0xc4`. `hud_drawPlayerStatus` `0x1d9cd4` runs from the HUD draw task,
once per displayed frame per slot (O, hud-dynamic.md). The fill itself is
Executed here.

**Clip.** `S` is the slot origin plus 15. The four words at `0x53c408` are
12, 478, 167 and 323 (O). Executed draws used 12 (offline slot 0, so x = 27),
0 (slot 0 remote and the only player) and 478 (slot 0 drawn while only slot 1
is local). Online, local slots other than 0 take slot 0's original origin,
and a non-local slot 0 receives the last origin that exchange displaced, or 0
when none did (`0x1d9dec–0x1d9e4c`). Then

```
right = trunc(float(S) + (current / maximum) * 99)
```

Divide, multiply, add, convert. There is no clamp: current above the maximum
passes `S+99` (E, case `n=2`). A zero maximum saturates the way the R5900
divide does. Health current 40 over maximum 0 has right edge `0x7fffffff`,
and mana current -5 over maximum 0 has right edge `0x80000000` (E, case
`n=8`). Health is drawn for every slot that passes the gates.
Mana and experience are drawn only for a local slot. Acknowledged level 0
skips experience and still draws mana (E). The frame is `(g_simFrame >> 2)
% 11`. Y is 46, 56 and 63 for health, experience and mana.

**One simulation tick, `Player_run` then these two calls** (O,
player-tick.md; the bodies are E here). A prediction copy (`object+0xc` bit
`0x20000`) or health `<= 0` returns without changing health, mana or either
pending word. Otherwise, while current is below its maximum:

| | Health `0x1b3b90` | Mana `0x1b3900` |
|---|---|---|
| Step | `maximum * 0x38d1b717` (0.0001) | the same from maximum mana |
| Passive | if `0x1bed48(slot, 0x10) > 0`, multiply by `level * 0x3dcccccc + 0x3f999999` | mask `0x200`, coefficient `0x3e199999`, same bias |
| Object byte | add signed `object+0x477 * 0.0001` | signed `object+0x475` |
| Class 0 | — | the amount becomes 0 (`record+0x50 == 0`) |
| Equipment | for each of the 17 pointers at `record+0x43f0`, multiply by `1 + modifier * 0x3c23d70a` | modifier id `0xc` instead of `0xb` |
| Extra | — | if a blessed spell is present, add `amount * (stat * 0.01)`; the same for a nonzero rank of skill `0x13` |

The amount is then added and capped at the maximum. Pending health
`+0xb4` / mana `+0xc8` is separate and runs even when current is already at
the maximum. While pending is `> 0`, current gains the whole rate (`+0xb8` /
`+0xbc`). Reaching the maximum drops the rest of pending. A rate larger than
pending still adds the whole rate when the maximum is not reached, and
pending then floors at 0 (E). The passive, blessed and skill-rank callees
were stubbed to the integers under test; the multiply, the class-0 clear,
the 17-slot modifier walk and both caps are the original instructions.
`0x1bed48` itself stays the executed player-tick contract.

## 2. Experience

`player_giveExp(slot, amount)` `0x1d3150` is the simulation writer (E, 22
cases). It adds `amount` to signed `record+0x5c` with 32-bit wrap, then
stores the word at `0x41b698` minus 1 when that cap is below the wrapped sum.
That word is experience-table entry 80. The three words read for the bounds
are entry 0 = 0, entry 1 = 1100 and entry 80 = 9999999, so the stored cap is
9999998 (O for the word, E for the store). One call plants `0x00a5a5a5` in
`+0x5c` and adds 1; the word becomes 9999998. While experience is not below
`T[level]`, with `level` the signed byte at `+0x59`:

| Level being left | Skill word at `+0xe8` | Stat byte `+0xec` |
|---|---|---|
| below 6 | +1 | +3 |
| below 16 | +2 | +3 |
| below 26 | +3 | +3 |
| below 36 | +4 | +3 |
| 36 and above | +5 | +3 |

The level byte then increments. Bands 1, 5, 6, 16, 26, 36 and 79 were
executed. The stat byte 254 becomes 1 (E). The skill word is planted at a
nonzero sentinel in those two cases, so the band add is a change from that
sentinel.

`player_recalcStats` `0x1b6458` is called after the increment; this probe
stubs it and only checks the stores that follow. If health is `> 0`, health
and mana become the maxima that recalc left. Health `<= 0` leaves both
currents. Acknowledged level `+0x58` is not written (E). Who raises it is
**U** here.

The green bar uses the acknowledged level, not `+0x59` (E). It is skipped
when that signed byte is not above 0. Otherwise the same 99-wide fill uses
`float(experience - T[ack-1]) / float(T[ack] - T[ack-1])`, with both
subtractions wrapped as 32-bit integers before `cvt.s.w`. Equal thresholds
divide by zero and saturate (E, one planted pair). No clamp.

Every level step calls `hud_showMessage` with 360 frames (`0x168`) and force
0, on every machine. Only the owning machine stores it, and a zero force
with the menu byte `0x41b69d` set keeps the previous message (E). The
level-up sound is local only (E). Level bytes outside 0..80 are **U**.

## 3. Quick-slot spells and belt items

Two different producers, already separated by the earlier notes.

**Spells.** The HUD ring and the A/B buttons read `record+0x4a84` and
`+0x4a85`, which `hud_onQuickSlot` `0x1de28c` writes from message 0. The
eight icons are ability records `+0x4440 + index*0x68`. The selector reads
the raw local pad once per displayed frame, behind the nine gates, and the
handlers run on the simulation tick (E, hud-quickslots.md sections 3 and 4;
hud-input-producers.md section 2). A Godot key that never sends those
messages does not implement this.

**Items.** Potion counts are the bag-2 sums `player_countPotions` writes to
`0x41b940` / `0x41b950`, refreshed when a potion is used, not every frame
(E, hud-quickslots.md section 2). The 17 equipment pointers at `+0x43f0` are
the belt the regen walk reads; modifier ids `0xb` and `0xc` scale the two
bars once per simulation tick (E, section 1). Ammunition at `+0x4410` and
the thrown stack at `+0x43f8` are the quantities notice lines 6 and 7 would
show. Their starters in `Player_run` are still only Observed
(hud-quickslots.md lines 248–249). This probe did not execute them.

## 4. Automap feed

`minimap_draw` `0x1e42e0` reveals from each living player's object position
on the draw, before the projector gate (O and E for the call order,
hud-input-producers.md section 4). `0x16a4b0` converts that position with
`0x16a7dc`:

```
cell = origin + world * 0.25 * 0x3d088888
```

`0x3d088888` is the 1/30 factor, so one cell is 120 world units. The origin
words are `0x4044a8` and `0x4044ac`. A disk of squared radius 64 then raises
only bits 12..15. The level is round-half-away-from-zero of
`(1 - sqrt(dx^2+dy^2) * 0.125) * 254`, clamped to 255, then shifted down
four bits. The greater nibble wins. Bits 0..11 stay (E, 48 fractional
positions per seed, plus the existing 120 integer centres). The loop is
bounded by the loaded width and height. VU1 tile program `0x403e20` and the
`world+0x6c` atlas remain **U**. Icon `vars_get` / `script_runByName` gates
remain **U**.

## 5. On-screen messages

`hud_showMessage(text, frames, slot, force)` `0x1d92a0` (E, inside the 49
message cases):

- Slot `-1` skips the local-slot test. Any other slot returns immediately
  unless `net_isLocalSlot` is true.
- Force is the low byte of the fourth argument. A zero byte returns
  immediately while `g_localMenuOpen` `0x41b69d` is set, including for slot
  `-1`. A nonzero byte stores anyway.
- Otherwise the wide string is copied to `0x86ab78`, the timer halfword
  `0x4f66e0` becomes the low 16 bits of `frames`, and byte `0x4f66e2` stores
  the force byte.

`hud_tickMessage` `0x1d934c` runs once per HUD run tick (O, one caller). It
does nothing while `g_hudSuppressed` `0x4f66a8` is set, while warmup
`0x506048` is set, or while the timer's signed halfword is not positive.
Otherwise the unsigned halfword decreases by 1. Four offline players also
set bust latch `0x4f66a9`; any other count, or a network byte, leaves the
latch (E).

The draw `0x1d93b0` updates alpha `0x4f66ec` once per displayed frame, before
the text calls (E; the boss half was held off by a camera mode other than
1, so the boss meter is not re-executed). A non-positive timer, or a
suppressed HUD with a zero force byte, leaves the old alpha. Below 32 frames
alpha becomes `4 * timer`. Otherwise it rises by 3. A result that is not
below 129 becomes 128.

`hud_clearMessage` `0x1d9330` zeros the timer halfword and leaves the text
(O). Forty call sites pass a frame count in the argument register (O). Only
`player_giveExp` was executed as a caller. The others are named here by the
function that contains the call and the immediate it passes; the condition
that reaches the call is **U** except where an older note already executed
that function.

| Frames | Callers (O) |
|---|---|
| 360 (`0x168`) | `player_giveExp` `0x1d3298` (E) |
| 300 (`0x12c`) | `hud_onMsg` `0x1d8e9c`; HUD draw `0x1dc024` and `0x1dc054`; `Vehicle_run` `0x207e40` |
| 180 (`0xb4`) | `script_setInfo` `0x1431c0`; `newWorld_netGate`; `recall_execute` (two); four sites in `Player_run` (`0x1a6ebc`, `0x1a7af0`, `0x1a8040`, `0x1aafc4`); `Vehicle_run` `0x207d7c`; `save_game` (three); `JumpGate_run`; `JumpGate_interactPrompt`; `DoorSwing_interact`; `Savepoint_interactPrompt` (two); skill `canUse` for ground pound, convert undead, cyclone, harm touch, the five arrow skills, bash, shield bash, and both axes |
| 120 (`0x78`) | `Savepoint_run` `0x28d6a0` |
| 90 (`0x5a`) | `SkillConvertEnemy_canUse`, `SkillRoot_canUse`, and one `SkillResurrect_canUse`; the other resurrect site is 180 |

`script_setInfo` is the level-script producer the play view already draws.
The other rows are real callers with a known frame count and an unknown
branch condition.

## What the client can implement

1. Health and mana bars from the record floats, origin plus 15, the unclamped
   99-wide fill, and the per-tick regen and pending rules above. Current above
   the maximum passes `S+99`. A zero maximum saturates. Offline slot 0 is the
   ordinary play case. Do not invent a second health pool on the object.
2. The experience bar from acknowledged level and `T[ack-1]` / `T[ack]`, with
   the same fill. Drive experience from `player_giveExp`, including the store
   of entry 80 minus 1 when the wrapped sum is above it. The skill word at
   `+0xe8` gains 1, 2, 3, 4, or 5 from the level being left. The stat byte at
   `+0xec` gains 3, and 254 becomes 1. Refill health and mana only when health
   is above 0. Leave acknowledged level unchanged until its writer is executed.
3. The level-up line, and any other line whose caller is later executed, through
   `hud_showMessage`, the per-tick timer and the alpha clamp. A zero force does
   not replace a message while the local menu is open.
4. Quick-slot spells and potion counts from the existing executed selector,
   message 0/1/13 and `player_countPotions` contracts. Scale the bars by the
   17 equipment modifiers. Keep ammunition and thrown notices refused.
5. Automap exploration from player positions, including fractional cells, with
   the nibble rule above. Keep VU1 tiles, the atlas and scripted icons refused.

## Unknown

- VU1 program `0x403e20` and the `world+0x6c` atlas.
- Draw-time icon variable and script gates.
- Ammunition, thrown and camera notice starters.
- The branch condition of every `hud_showMessage` caller except `player_giveExp`.
- The writer of acknowledged level `+0x58`.
- Level bytes outside 0..80, and the body of `player_recalcStats` inside this probe.
- How many displayed frames fall in one simulation tick.
- The console's last bit where it can differ from the `ee_emu` FPU.
