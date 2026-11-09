# Live producers for the in-game HUD

SLUS-20973 v2.00. This note closes the display values that
[hud-input-producers.md](hud-input-producers.md) left at the event boundary:
the health and mana bars, the experience line, the one-line message, and
automap reveal from a world position that is not an integer cell centre.
Round 3 (sections 6–10) adds the writer of acknowledged level `+0x58`, the
branch conditions of the message callers met in ordinary missions, the
ammunition and thrown notices, the scripted map icons, and the data contract of
the automap tile program. Quick-slot spells and potion items stay the executed
contracts in [hud-quickslots.md](hud-quickslots.md) and hud-input-producers.md
sections 1 and 2.

**Evidence.** Observed (O) is an addressed instruction or call. Executed (E)
means `tools/ee_emu.py` ran that original function (or, in section 10,
`tools/vu1_emu.py` ran the VU1 program the original packet loads) and
`tools/ref_hud_live.py`, `reveal_world` or `tools/ref_hud_feeds.py` matched it.
Inferred (I) is reasoning from E or O, not run. Unknown (U) is not
established. No game or console was run. Float results are the default
`ee_emu` FPU, not a claim about the console's last bit.

From the worktree root, with the standard library `dis` imported first
(`tools/dis.py` shadows it):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["tools/difftest_hud_live.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["tools/difftest_hud_inputs.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["tools/difftest_hud_feeds.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
```

Repeat each with `--seed 7`. Both seeds: live probe 166 cases and 0 seed
draws (regen 70, bars 25, experience 22, messages 49); automap probe 608
cases and 0 seed draws, including 48 fractional reveals. The stdout is
`local/hud-live-20973.log`, `local/hud-live-7.log`,
`local/hud-inputs-20973.log` and `local/hud-inputs-7.log`. The round-3 probe
`tools/difftest_hud_feeds.py` is 13 properties: 740 cases on seed 20973 and
723 on seed 7, 0 seed draws. The first property is the 43-site census of
section 5. The two seeds differ only in the random tile
states (100 and 83 strip packets, 712,960 and 523,512 vertices). Its stdout is
`local/hud-feeds-20973.log` and `local/hud-feeds-7.log`. The analysis suite
figures are in section 11.

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
currents. Acknowledged level `+0x58` is not written (E). Its writer is in
section 6.

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
show. Their starters are Executed in section 8.

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
bounded by the loaded width and height. The icon gates are Executed in
section 9 and the tile program's data contract in section 10. The texel
content of the `world+0x6c` atlas stays **U**.

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
(O). There are 43 direct jumps to `hud_showMessage` in `.text`: 40 `jal` and 3
tail-call `j` (O). The `message census` property of `difftest_hud_feeds.py`
scans `.text` and asserts every site and its containing function from
`ghidra_funcs.tsv`. Each site passes a frame count in `a1` (O). Pointer calls
(`jalr`) were not searched (**U**). Only `player_giveExp` was executed as a
caller. The others are named here by the
function that contains the call and the immediate it passes; the condition
that reaches the call is **U** except where an older note already executed
that function.

| Frames | Callers (O) |
|---|---|
| 360 (`0x168`) | `player_giveExp` `0x1d3298` (E) |
| 300 (`0x12c`) | `hud_onMsg` `0x1d8e9c`; HUD draw `0x1dc024` and `0x1dc054`; `Vehicle_run` `0x207e40`; tail jump `0x328140` in the unnamed function `0x328090` (slot −1; `docs/lobby-protocol.md:813` cites that function on the character-creation reply path) |
| 180 (`0xb4`) | `script_setInfo` `0x1431c0`; `newWorld_netGate`; `recall_execute` (two); four sites in `Player_run` (`0x1a6ebc`, `0x1a7af0`, `0x1a8040`, `0x1aafc4`); `Vehicle_run` `0x207d7c`; `save_game` (three); `JumpGate_run`; `JumpGate_interactPrompt`; `DoorSwing_interact`; `DoorSecret_interact` (tail jump `0x28b2f8`, slot −1); `Savepoint_interactPrompt` (two); skill `canUse` for ground pound, convert undead, cyclone, harm touch, the five arrow skills, bash, shield bash, and both axes |
| 120 (`0x78`) | `Savepoint_run` `0x28d6a0` |
| 90 (`0x5a`) | `SkillConvertEnemy_canUse`, `SkillRoot_canUse`, and one `SkillResurrect_canUse` (the other resurrect site is 180, one of the 14 skill sites); tail jump `0x1de3c8` in `hud_onQuickCastWarn` `0x1de340`, the kind-1 ability warning of game message 13 (`docs/issues/doc-corrections.md:1430`), slot in `s0` |

That is 1 + 5 + 32 + 1 + 4 = 43 sites. `script_setInfo` is the level-script
producer the play view already draws. Section 7 executes the branch conditions of the callers an ordinary mission
reaches. The rest keep a known frame count and an unexecuted condition.

## 6. Acknowledged level `+0x58`

**During play** the only store is inventory message 9. Outside play other
writers set the byte. Character creation starts it at 1, and import caps it
at 50 (`docs/player.md:52`, O). The player loop of `save_load` `0x221d60`
overwrites the live record from the save snapshot. `t3/research-levelup`
98a8a47 executed that loop and it put back acknowledged 4
(`docs/spec/levelup.md:186-196` there). The three in-play links, all in
`difftest_hud_feeds.py` (`acknowledge edge` 37 cases, `acknowledge chain` 9):

1. **Edge, `hud_run` `0x1db870`, once per HUD run tick** (E). Interpreter
   (`ack_cases`): nothing is followed, so every callee that is not named here
   returns 0 without running, the three calls at the entry (`0x1db890–0x1db8a0`)
   included. `pauseMenu_isOpen`, `game_isFrozen`, `jumpgate_getTravelState`
   and `task_isRunning` (keyed on its name pointer) answer from the test.
   `menu_openInventory` and `script_runByName` only record their arguments. For each slot
   below the player count `0x4d8ae0`, with `g_rawPads` `0x4028d0 + 0x58*slot`:
   the pressed word `+0xc` must have bit `0x100` and the held word `+0x8` must
   not have bit `0x80` (`0x1db964–0x1db980`). Then 14 gates, in this order:
   `g_localMenuOpen` `0x41b69d`; `pauseMenu_isOpen` `0x18cbfc`;
   `game_isFrozen` `0x1ebdf8`; local camera `*0x4f8450 + 0x34 == 1`;
   `g_cutsceneActive` `0x44fcd0`; input-block byte `0x4f66c8`; word
   `0x503890`; the slot's object `+0x540` when the object exists;
   `jumpgate_getTravelState` `0x27dd68`; `task_isRunning` on the names at
   `0x53c5b0` and `0x53c280`; `g_recallCountdown` `0x41b51d`; a null object
   (record `+0x43d8`); object `+0xc` bit `0x400000`. Each was failed alone and
   stopped the call. With every gate open, object flag `0x8` or health
   `+0xac <= 0` makes no call. Otherwise the signed bytes decide
   (`0x1dbac4–0x1dbaf8`): acknowledged `+0x58` below earned `+0x59` calls
   `menu_openInventory(slot, 1)` and zeroes the glow word `0x86aa50[slot]`;
   anything else calls `menu_openInventory(slot, 0)`. Acknowledged −128 with
   earned 1 is a pending level (E). After any of these three outcomes, every
   player whose record `+0x1330` is above 0 gets one
   `script_runByName(<name at 0x53c5c0>)` (E, recorded call count). Bit `0x100`
   is Select. `docs/issues/live-rig.md:228` confirmed it on the running game by
   holding the button and reading `g_pads`+8 (Ran, for the lockstep pad, with Up
   `0x1000`). `pad_readAll` copies `g_pads` to `g_rawPads`
   (`docs/mainloop.md:257`, O).
2. **Send, `menu_openInventory(slot, levelUp)` `0x1c15c8`** (E, on an owner
   machine and a non-owner machine). Interpreter (`ack_chain_cases`): only
   `menu_openInventory` and `invmsg_dispatch` are followed. `net_isLocalSlot`
   (1 on the owner, 0 on the other machine), `menuMutex_tryAcquire` (0) and
   `net_sendGameMsg` (records the bytes) are stubs. Every other callee returns 0
   without running. Off the owner it returns before any store.
   Offline, a nonzero `menuMutex_tryAcquire` `0x22fc04` also returns early (O;
   the probe answered 0). On the owner it sets `g_localMenuOpen` to 1. With `levelUp` set it sends
   three bytes `{9, slot, signed earned level +0x59}` through
   `net_sendGameMsg` (`0x1c17f8–0x1c1818`). It then stores word 5 at
   `0x4f4090` (`0x1c1834`), byte 1 at `0x4f65c8` (`0x1c1838`), slot at `+0xed`
   and 0 at `+0xee` (`0x1c183c`, `0x1c1840`). All four were checked against
   planted sentinels. The two globals are part of the panel open; what they
   mean is **U**. With `levelUp` 0 it sends nothing and leaves all four. For
   this path, this answers the open `R+0xee` question of `t3/research-levelup`
   98a8a47 (`docs/spec/levelup.md:197` there): opening the panel with a
   pending level clears `+0xee` and sends the acknowledgement. `inventory_onJoinPanel` `0x1c0360` sends the same message
   from inventory message 4 with its level-up flag (prior: `ref_messages.on_join_panel`,
   `difftest_messages.py`).
3. **Store, `invmsg_dispatch` `0x1bfdb0` case 9** (E, on both machines with the
   sent bytes). The record of byte 1 gets byte 2 at `+0x58`. That is the only
   store of the call (the recorded write list).

So a level stays pending, with the pulsing level number and the glow, until
the owner opens the inventory. The green bar then switches to the earned
level on every machine. `t3/research-levelup` keeps the giveExp side and the
save round trip; it names the same message (its `docs/spec/levelup.md`).
`ee_tests.py` k23 executed `menu_openInventory(slot, 1)` and the dispatcher
before; this round adds the `hud_run` gates, both machines, and the two
bookkeeping bytes.

## 7. Message callers in ordinary missions

The 43 direct jumps to `hud_showMessage` (40 `jal`, 3 `j`) are asserted site
by site by `message census` (O, section 5). Pointer calls were not searched.
Below, **E** means the caller ran with `hud_showMessage` followed and its
store checked against a planted timer 77, force 9 and empty text.
Interpreter for every row (`message_machine`): only `hud_showMessage` and its
wide copy `0x19e854` are followed, plus `libc_strcmp` for the door. Every
callee not listed in the row returns 0 without running. `net_isLocalSlot`
returns 1. `text_lookup` records its key and returns a planted one-character
wide string.

| Event | Caller | Condition (E unless marked) | Call |
|---|---|---|---|
| level up | `player_giveExp` `0x1d3298` | every level step (section 2) | 360, slot, 0 |
| script info line | `script_setInfo` `0x14318c` | always; refused while the local menu is open. Stubs: `scr_getString` writes a planted key pointer, `scr_copyString` returns 0 | 180, −1, 0 |
| locked door | `DoorSwing_interact(door, slot)` `0x28aa7c` | slot is not −10, the door has the string property at `0x549070`, and `script_runByName` on it returned 0. Also `player_voice(slot, 7)` and a sound: none when the property at `0x549078` exists and differs from the string at `0x549080`; `res_find(0x549088, 0x549090)` when it equals it; `res_find(0x549088, 0x5490a8)` when the property is absent. Text key `0x5490c0`. Stubs: `obj_getPropStr` / `obj_getPropInt` answer by key address, `script_runByName` returns the planted result, `player_voice` and `res_find` record their arguments, `sound_playOnObject` returns 0 | 180, −1, 0 |
| door opens | same | any other case: no message, interactable bit `0x100000` cleared. The run stops early: door `+0x4c` was planted `0xFFFF` (no world cell), so the rest of the open path did not run (**U**). Same stubs | — |
| save point, refused | `Savepoint_interactPrompt(sp, buffer)` `0x28da58` | memory card idle (`memcard_isBusy` `0x217518`), `net_allPlayersState2` `0x1ec5d8` false, and `game_inNoSaveZone` `0x1e7b78` true. If some active player's object (list `0x4f8440`, count `0x4f8420`) has `+0x540` set, text key `0x549278`. Otherwise the save point's property `0x549258` when present, else key `0x549268`. Returns 0 | 180, −1, 0 |
| save point prompt | same | not in a no-save zone: no message, returns 1, writes a prompt into the buffer: key `0x5492b0` offline; online `0x549288` when word `0x4f8f30 >= 0x709` and `sp+0xc7 == −1`, else `0x5492a0`. Stubs for both rows: `memcard_isBusy`, `net_allPlayersState2` and `game_inNoSaveZone` answer from the test; `obj_getPropStr` / `obj_getPropInt` by key address | — |
| jump gate first use | `JumpGate_interactPrompt(gate, buffer, i)` `0x27d7a0` | `gate+0x4f == 0`, `task_isRunning(0x547e10)` false, the property at `0x547e40` is absent or its script returned nonzero, and `gate+0x4d == 0`: sets `+0x4d = 1`, calls `0x27db60`, text key `0x547e90`. With `+0x4f` set another branch runs; it was not followed. Stubs: `task_isRunning` records its name pointer (`0x547e10` asserted on the first call) and answers from the test, `script_runByName` returns the planted result, `0x27db60` is recorded and not run, properties by key address | 180, word `0x4f8440[i]`, 0 |
| item pickup | `itemprop_tryPickup(slot, item)` `0x154dbc` | its own body never calls it and leaves the planted timer, force and text (E, 60 cases). Full bag (`count + 1 >= 64`): a sound, returns 0. Over the load limit `+0x124`: `player_voice(slot, 0)`, returns 0. Accepted: a sound named from the item flags, `script_runByName(0x532678)`, `inventory_giveItem(slot, item, 1)`, `0x1bec10(slot)`, returns 1 (the arguments shown are asserted). Every callee was a stub that records its name and arguments: `item_weight` (planted float), `res_find`, `sound_playOnObject`, `sprintf`, `script_runByName`, `inventory_giveItem`, `0x1bec10`, `player_voice`. The level-script function that `script_runByName` starts can call `setInfo` (row 2), so a pickup may still put text here through it (**U**). `inventory_giveItem` has no direct jump to `hud_showMessage` (census); its callees did not run | — |

What the census does not contain (I: from the names of the containing
functions, not from reading each reaching condition, and only for direct
jumps): no quest-add or quest-complete caller of its own, so quest and
objective text reaches this line only through `setInfo`. The help box `hud_showHelpMessage` `0x1d9830` is a
different box (`script_addHelpMessage`, `script_addHelpMessageF`, and two
first-pickup hints in `inventory_giveItem` at `0x1c1a50` and `0x1c1c28`). No
containing function is a health check, so there is no low-health line (I).
The reaching condition of about 30 sites, the 17 skill `canUse` sites
included, was not read (section 5). The nearest HUD cue is notice line 1,
"no health potion" (hud-quickslots.md). Not executed here, with their frame
counts in section 5: `DoorSecret_interact` (tail call `0x28b2f8`),
`hud_onQuickCastWarn` (tail call `0x1de3c8`), `0x328090` (tail call
`0x328140`), `Savepoint_run` `0x28d6a0`, `recall_execute`, `newWorld_netGate`,
the four `Player_run` attack refusals, `Vehicle_run`, `save_game`,
`JumpGate_run`, `hud_onMsg`, `hud_netStatusDraw`, and the skill `canUse`
sites (those are in the skill specs).

## 8. Ammunition and thrown notices

The original slices ran with the notice counter `0x1dacf4` stubbed to return
`0x30 + line` and record `(slot, line)`. All 64 timer and row words of
`0x41b828` / `0x41b8a8` were planted, and only the expected words changed (E,
`ammunition notices` 144 and `thrown notices` 148 cases). "Low" is
`(u16 count − 1) < 20` unsigned, so 1 to 20. A count of 0 or 21 and above is
not low.

| Line | Starter | Condition | Timer |
|---|---|---|---|
| 6 low arrows | `Player_run` `0x1a758c–0x1a7678` (neutral-state arrow ability) | ammunition pointer `record+0x4410` set and its count `+4` low; the prediction copy also starts it here | 240 |
| 3 no arrows | same block | not a prediction copy (`object+0xc` bit `0x20000`) and `+0x4410` null; also `player_voice(slot, 5)` | 120 |
| 6, 3 | `Player_run` `0x1a7d4c–0x1a7eb4` (after the bow's ammunition search) | the same two tests, but a prediction copy skips both | 240, 120 |
| 7 low thrown | `Player_run` `0x1a888c`, `SkillFireAxe_cast` `0x319cc4`, `SkillColdAxe_cast` `0x31a5f8` | the stack being thrown is low before its decrement; these slices do not change the count | 240 |
| 7 on swap | `Player_weaponSwapInput` `0x1bb9b0` | the new weapon set `record+0x4a7c` is 1 and that set's weapon word (`+0x4430 + 4*set`, so `+0x4434`) points to an item whose definition has class byte `+0x1e == 6`, at any count. Each set word held its own item, only set 1's with the tested class and the others with the opposite answer, and counts were drawn from 0, 1, 20, 21, 50 and 0xFFFF | 240 |

The count each line shows is the draw's (hud-dynamic.md section 3): line 6
the item at `+0x4410`, line 7 the item at `+0x43f8` when weapon class
`+0x4a86` is 6.

## 9. Map icons

**Registrar `0x1689a4(pos, rotate, name, angle, offset, scale, var, script)`**
(E, 62 cases: 58 through the whole `PushTrigger_ctor` `0x1ec900` with
`GameObject_ctor` stubbed, and 4 direct calls). A null name adds nothing:
called directly with name 0 and real offset, scale, var and script strings,
the registrar leaves the count, the entry words, `res_find` and `sprintf`
untouched (E, 4 calls). Otherwise entry
`0x6e0f90 + 0x1c*count` gets x/y = position + the two `%f` read from the offset
string (0 when it is null), the texture `res_find(0x533be8, <texture name>)`, `+0xc`
rotate, `+0x10` = `0x3f266666` (0.65) when the scale string holds a nonzero
`%d` and 1.0 otherwise, `+0x14` var, `+0x18` script; then count
`0x6e14d0` + 1. The texture name: a name that does not start with the four
bytes at `0x533b60` is formatted with `0x533be0`. One that does picks one of
four fixed arrow names (`0x533ba0`, `0x533bb0`, `0x533bc0`, `0x533bd0`) by
`k = (d − q + 4) % 4`. Here `d` is 0..3 when the name equals the string at
`0x533b68`, `0x533b70`, `0x533b80` or `0x533b90`, else −1, and `q` is the angle
divided by `0x4000` toward zero. `sscanf` was a disclosed stub that parses
`%f`/`%d`; `sprintf` was recorded only.

**Who registers what** (E for PushTrigger, O for the other two). `PushTrigger_ctor`
reads five string properties, `0x53e258` name, `0x53e278` offset, `0x53e288`
scale, `0x53e298` var and `0x53e2a8` script (the symbol table calls them
icon, iconOffset, iconHalfSize, iconValue, iconScript). It registers only when
the name exists: with no name property the registrar is not entered (E,
recorded calls). Rotate is 0 when the name equals the string at `0x53e260` or
`0x53e268`, else 1. The angle is the constructor's third argument. The
integer property `0x53e248` clears object flag bit 0. `JumpGate_ctor`
`0x27c834` (unless its integer property `0x547de0` is set) and
`Savepoint_ctor` `0x28ccf0` register fixed names `0x547df0` / `0x5491c8` with
rotate, offset, scale, var and script all zero. Only PushTrigger icons can
carry the gates.

**Draw gates, phase B of `0x168cac`** (E, 53 cases, with the real `vars_get`
and `script_runByName`, and `scr_findEntry` / `scr_interpret` stubbed).
Entry `+0x14` goes to `vars_get` (`0x1696a4`). The name is lower-cased, and a
value of 0 skips the icon. **A name not in `g_questVars` is appended with
value 0 and the icon is skipped.** So drawing changes the quest table, and
upper-case names match their lower-case entries. Then `+0x18` goes to
`script_runByName` (`0x1696c4`):

- no script machine (`0x86b270` is 0), or `scr_findEntry` returns nonzero:
  the result is −1 and the icon is drawn. A missing entry also sets word
  `0x4f8694` to `g_drawFrame + 0x14` when it was below `g_drawFrame`.
- found: `scr_interpret` runs the level script function **from the draw**.
  The icon is skipped when the result word it leaves is 0, and drawn for any
  other value, −5 included.

Icons that pass are drawn with the alpha of the explored nibble of their
cell, as the existing projector difftest shows.

## 10. Automap tile program: the data contract

(E, `tile packets`: 40 random drawer states per seed from
`difftest_hud_minimap.make_state`. The drawer's display list is checked byte
for byte against `ref_hud_minimap.draw` first. Then every map-strip packet is
fed from its DMA tag through `vu1_emu.py`: 100 packets and 712,960 vertices
on seed 20973, 83 and 523,512 on seed 7, all equal to `ref_hud_feeds`.
`tools/vu1_emu.py` is the interpreter from `t3/research-textures` 199251f,
unchanged.)

- **Cells read.** The visible range `c_min..c_end`, `r_min..r_end` (hud-minimap.md
  step 5) is cut into strips of 30 columns that start 29 apart: the last
  column of one strip is the first of the next. For each strip, every row
  from `r_min` to `r_end − 1` is one `memcpy` of `n` u16 cells from
  `0x4044f0 + row*0x1b0 + col*2`, in row order. No read trace was taken, so
  other grid reads by the tile path are not ruled out.
- **Quads.** Each pair of adjacent rows in a strip is one GS triangle strip:
  one PRIM write of `0x15c` (triangle strip, Gouraud, textured, alpha blend,
  UV coordinates), then four `XYZ2` vertices with ADC 0 for each pair of
  adjacent columns (E: the vertex count after each PRIM write and every
  vertex's PRIM, ADC bit and register are asserted). Corners are in the order
  `(c,r)`, `(c,r+1)`, `(c+1,r)`, `(c+1,r+1)`. A strip of `n` columns and `R`
  rows gives `R−1` PRIM writes and `(R−1)(n−1)` quads. The next quad repeats
  the shared column's two corners with its own UV, so each join triangle has
  two vertices on the same corner. If positions follow the corners, those
  triangles have no area (I; X/Y were not compared). The tile is taken from the cell at
  `(c+1, r+1)`: atlas column = bits 0–4, atlas row = bits 8–11, orientation =
  bits 5–7.
- **UV.** A tile spans GS UV `col*160 .. col*160+158` and `row*160 .. row*160+158`
  (10 texels, 2/16 short of the next tile). The orientation picks one of
  eight assignments of those edges to the four corners (`ref_hud_feeds.ORIENT`;
  orientation 0 is near/near, near/far, far/near, far/far).
- **Alpha.** Each vertex's alpha is the high byte of its own corner cell,
  `(explored << 4) | atlas row`. An unexplored cell with atlas row 0 has
  alpha 0 but is still emitted.
- **Not reduced.** Vertex X/Y were recorded but not fitted to a formula.
  Their relation to the uploaded origin and steps was not established, so
  positions are **U** here. Texel content of the atlas is **U**.

This agrees with `t3/research-textures`: the code at 5d3dd39
(`tools/ref_leveldraw.py` `AUTOMAP_ORIENT` equals `ref_hud_feeds.ORIENT` row
for row) and the doc at 391cf6b (`docs/formats/level-draw.md` section 4),
which ran one fixed argument list. This round runs every strip of
random states on both seeds and pins which cells are read.

## 11. Verification

On the Mac mini, after the final edit, with stdlib `dis` imported first:

- `tools/difftest_hud_feeds.py local/SLUS_209.73 --seed 20973` and `--seed 7`:
  `local/hud-feeds-20973.log`, `local/hud-feeds-7.log` (figures in the
  header above). Each log starts with the commit and the blob hash of the
  difftest it ran. Per seed: census 43, edge 37, chain 9, setInfo 4, door 30,
  save point 18, jump gate 32, pickup 60, ammunition 144, thrown 148,
  registrar 62, icon gates 53, and 100 (seed 20973) or 83 (seed 7) strip
  packets.
- `tools/difftest_hud_live.py` and `tools/difftest_hud_inputs.py` on both seeds,
  rerun unchanged: `local/hud-live-*.log`, `local/hud-inputs-*.log`.
- `python3 -m unittest discover -s tools -p 'test_*.py'`:
  `local/unittest-discover.log`.

Mutation check (not retained, round 3 before this fix): nineteen one-line
changes to `ref_hud_feeds.py`, covering the conditions above. Each made the
difftest fail. The checks added in the fix (census, panel globals, stub
arguments, swap sets, direct registrar call, PRIM runs) compare against
fixed values in the difftest and were not mutation-tested.

## What the client can implement

1. Health and mana bars from the record floats, origin plus 15, the unclamped
   99-wide fill, and the per-tick regen and pending rules (section 1). Current
   above the maximum passes `S+99`. A zero maximum saturates. Do not invent a
   second health pool on the object.
2. Experience from `player_giveExp` (section 2). The green bar uses
   acknowledged level. Raise acknowledged level only through message 9:
   when the owner presses raw bit `0x100` with the 14 gates of section 6 open,
   an alive object without flag 8, and acknowledged below earned, open the
   level-up panel, zero the glow word, and send `{9, slot, earned}`. Every
   machine then stores the earned byte at `+0x58`. Set `+0xed` = slot and
   `+0xee` = 0 on the owner.
3. The one-line message through `hud_showMessage`, the per-tick timer and the
   alpha clamp (section 5), for these producers: level-up (360 frames, the
   slot), script `setInfo`, locked door, refused save point and first jump
   gate use (180 frames), with the exact conditions in section 7. A zero force
   does not replace a message while the local menu is open. The pickup code
   itself puts no text here; a pickup's level script can, through `setInfo`.
   Show no low-health line and no quest-specific line (I, from the census of
   direct callers).
4. Quick-slot spells and potion counts from the existing executed contracts.
   Scale the bars by the 17 equipment modifiers. Start notice lines 3, 6 and 7
   from the five starters in section 8 with their counts and prediction-copy
   rules.
5. Automap exploration from player positions, including fractional cells
   (section 4).
6. Map icons from PushTrigger properties, jump gates and save points
   (section 9). At draw time call `vars_get` with lower-casing, append unknown
   names with 0, and skip on 0. Run the named script function and skip only
   on a 0 result; draw when there is no machine or no such function.
7. Automap tiles: carry the strip, row and quad layout, the bottom-right tile
   choice, the eight orientations, the UV rectangle and the per-corner alpha,
   one triangle strip per row pair (section 10). The atlas texture must come from the world file.

## Unknown

- Texel content of the `world+0x6c` atlas, and the screen X/Y the tile program
  computes (section 10).
- The bodies of the level script functions an icon or a locked door runs.
- Callers of section 7 that were not executed, their reaching conditions,
  pointer calls to `hud_showMessage`, and the camera notice line 0.
- Whether a pickup's level script, or the callees of `inventory_giveItem`, put
  text on the message line. The door's open path past the world cell.
- What word 5 at `0x4f4090` and byte 1 at `0x4f65c8` mean.
- The `inventory_onJoinPanel` path is prior evidence only.
- Level bytes outside 0..80, and the body of `player_recalcStats` inside this probe.
- How many displayed frames fall in one simulation tick.
- The console's last bit where it can differ from the `ee_emu` FPU.
