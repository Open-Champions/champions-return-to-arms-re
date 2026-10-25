# NPC dialog: the gaps — camera, the open checks, the missing box, TestLocation

SLUS-20973 v2.00. Researched 2026-10-21 on `t3/research-dialog-gaps`, continuing
`docs/dialog.md` (`t3/research-dialog` 334578d), whose section 12 listed these as open.

**Status.** Every function and stretch named below was **Executed** in `tools/ee_emu.py`
against `tools/ref_dialog_gaps.py` by `tools/difftest_dialog_gaps.py`: 13 suites, 0 failed
with seed 20973 and with seed 7 (60 cases per suite). The disc was counted with
`tools/dialog_gaps_census.py` (section 8), which runs the original `sscanf` and the
original object factory on the disc records in the emulator. Faults injected into the
reference (an angle, a scale, a dropped gate, a dropped factory branch, a glyph value) made
the matching suites fail. Nothing was run on a game: nothing here is "Ran". Status words:
**O** observed at the address, **I** inferred, **U** unknown, **E** executed (suite named).

Companions: [reference](../../tools/ref_dialog_gaps.py),
[synthetic tests](../../tools/test_ref_dialog_gaps.py) (28, no game file),
[difftest](../../tools/difftest_dialog_gaps.py), [census](../../tools/dialog_gaps_census.py).

Contents: 1 functions · 2 the camera · 3 the 24 open checks · 4 the box where `box.tex` is
not loaded · 5 the cursor glyph · 6 the TestLocation talkers · 7 seeds and lockstep ·
8 disc census · 9 what the native client should implement, ranked · 10 open questions.

## 1. Functions

| Address | Name | What | Status |
|---|---|---|---|
| 0x203bb8 | `Camera_setupDialogView` | conversation camera target from `dialogOffset` and where the players stand | E `view` |
| 0x204250 | `Camera_lookAt` | one step of the swoop in or out | E `lookat` |
| 0x22ff74–0x2300bc | `dialog_runTask`, camera step | swoop loop, far clip, message 3 | E `runcam` |
| 0x2035c8 | `Camera_apply` (forward vector 0) | orientation, shake, `camera_setView` | E `apply` |
| 0x1ebdf8 | `game_isFrozen` | every input combination (512) | E `frozen` |
| 0x1bce88 | `player_pollRecallButton` | recall button | E `recall` |
| 0x203400 | `Camera_update` | the user-control word +0x60 and the mode dispatch | E `camctl` |
| 0x322b48–0x322c00 | `mainloop_runSession`, idle voice | countdown and one cosmetic draw | E `idle` |
| 19 stretches | the other `dialog_isOpen` sites (section 3) | each run to labelled exits | E `sites` |
| 0x22f910 | `dialog_loadBox` | when `box.tex` is looked up | E `box` |
| 0x17b590 | `ui_drawSpriteImpl` | what it reads first from its texture | E `box` |
| 0x1e6b68 | `game_initCamera` | confirm / cancel masks and the button glyph bytes | E `buttons` |
| 0x159c94 | `world_objectFactory` | the property fallback for an unmatched class name | E `factory` |

## 2. The camera

### 2.1 Camera words (the camera object; `g_localCamera` 0x4f8450 points at it)

| Offset | Type | Meaning | Written by | Read by |
|---|---|---|---|---|
| +0x00 … +0x08 | float × 3 | swoop start position (copy of `g_cameraPos` 0x44f038) | setupDialogView 0x204098 | lookAt |
| +0x0c … +0x14 | float × 3 | swoop target position | setupDialogView 0x20406c–0x20407c | lookAt |
| +0x68 / +0x6a | s16 | current yaw / pitch | lookAt 0x20438c / 0x204354 | Camera_apply, setupDialogView |
| +0x76 | s16 | swoop start yaw (= +0x68) | setupDialogView 0x2040b4 | lookAt |
| +0x78 | s16 | swoop target yaw | setupDialogView 0x204084 | lookAt |
| +0x7a | s16 | swoop target pitch | setupDialogView 0x204080 | lookAt |
| +0x7c | s16 | swoop start pitch (= +0x6a) | setupDialogView 0x2040ac | lookAt |
| +0xa8 | float | swoop progress 0 … 1 | setupDialogView 0x204224 (0), lookAt | lookAt |
| +0xac | float | turn factor k | setupDialogView 0x2041cc / 0x204220 | lookAt |
| +0x60 | s32 | user control allowed | Camera_update 0x2034a0 | (`docs/spec/movement-camera.md`) |

### 2.2 `Camera_setupDialogView(cam, npc, side)` 0x203bb8 (E `view`)

Called from `dialog_onMsg` case 0 (0x22ee84) when the swoop flag is set, with the focus
object and message byte `b` (`docs/dialog.md` 2.3–2.4).

1. Up vector (0, 0, 1) on the stack (0x203c08–0x203c14).
   `obj_getPropStr(npc, "dialogOffset" 0x53e660, 0)`. With a value:
   `sscanf(value, "%d,%d,%d,%d" 0x53e670, &dist, &height, &lateral, &pitch)` (0x203c34;
   stack slots +0x60, +0x64, +0x6c, +0x68). Without one: dist, height and pitch = 0
   (0x203c48–0x203c50) and **lateral is not written**: it keeps whatever the stack slot
   held. A value with fewer than four fields leaves the remaining slots the same way. The
   difftest plants values in those slots and the original uses them (E `view`, the
   `none` and `partial` cases). The reference refuses when it is not given them.
2. **Side angle** (only when `side` ≠ 0). Forward f = (`cos16`(facing + 0x4000),
   `sin16`(facing + 0x41c2), 0), facing = s16 npc+0x38 (0x203c5c–0x203c74; the second
   constant really is 0x41c2). For each entry of `g_alivePlayers` 0x4f8440 (count
   0x4f8420), the player object (0x4dcec8 + slot × 0x4c30) is "near" when the 3D distance
   to the NPC is < 80.0 (0x203cb8). For a near player, the horizontal unit offset u
   (`rsqrt`) dotted with f: < −0.2 (0xbe4ccccc) sets C, > 0.2 (0x3e4ccccc) sets A, else B.
   Index (0x203e08–0x203ee4):

   | A B C | 000 | 001 | 010 | 011 | 100 | 101 | 110 | 111 |
   |---|---|---|---|---|---|---|---|---|
   | index | 1 | 0 | 2 if `vec3_dotDelta(npc, f, g_cameraPos)` < 0, else 0 | 0 | 2 | 1 | 2 | 1 |

   Angle = index × −6000 + 6000 (0x203eec–0x203ef8): +6000, 0 or −6000. With `side` = 0 the
   angle is 0.
3. Direction d = (`cos16`, `sin16`)(facing + angle), normalised twice (2D, then 3D with
   z = 0). Side vector s = up × d = (−d.y, d.x, 0).
4. Target (0x204038–0x20407c):
   x = (npc.x + d.x × (dist + 80)) + s.x × lateral,
   y = (npc.y + d.y × (dist + 80)) + s.y × lateral,
   z = (npc.z + (height + 70)) + s.z × lateral, each add in that order.
   Target pitch +0x7a = u16(pitch) + 4000 (0x20401c); target yaw +0x78 =
   −(u16(facing) + angle + 0x4000) (0x204008–0x204018).
5. Start: +0..+8 = `g_cameraPos`, +0x7c = +0x6a, +0x76 = +0x68.
6. Turn factor: k = 1 − (cos Δ + 1) × 0.5, with cos Δ the dot of the normalised
   (`cos16`, `sin16`) of the current yaw and of the target yaw (0x2040b0–0x2041cc). k = 0
   when the camera already faces the target yaw, 1 when it faces away. If the start is
   more than 354.0 (0x204118) from the target, k = 0.85 (0x204214). Progress +0xa8 = 0.

No seed is drawn (E: no write to 0x404460/64/68 in any `view` run).

### 2.3 `Camera_lookAt(cam, steps, out)` 0x204250 (E `lookat`)

- `steps` > 0 returns 1 (arrived, nothing written) when progress is exactly 1.0;
  `steps` < 0 returns 1 when it is exactly 0.0. Otherwise:
- inv = 1 / steps; progress += inv − inv × k × 0.75 (0x2042c8), clamped to 0 … 1.
- h = `math_hermite`(progress, 0, 1, 0, 0) (smoothstep).
- pitch +0x6a = `angle_approach`(h³, −1, −1, +0x7c, +0x7a); yaw +0x68 =
  `angle_approach`(h, −1, −1, +0x76, +0x78).
- `Camera_apply`(start + (target − start) × h per axis, cam, 0); `*out = h` when out ≠ 0.
  Returns 0.
- Arrival is therefore one call **after** the progress reaches the end. Calls until the
  arrival is reported, in / out (reference, whose chains the `lookat` suite compared call
  by call): k = 0: 47 / 47; k = 0.85 (far start): 126 / 126; k = 1: 182 / 181.
- `steps` = 0 would divide by zero; the game never passes it (only ±45, 0x22ffa0, 0x230010).

### 2.4 The run task's camera step 0x22ff74–0x2300bc (E `runcam`)

`dialog_runTask` copies the three floats 0x44f118, 0x44f124, 0x44f130 — the forward
vector of `g_cameraMatrix` 0x44f110 (symbol note, `camera_setView` 0x18a2b0 writes it) —
**once**, before moving. So the float `docs/dialog.md` 5.1 could not name is the vertical
(z) part of the camera's forward vector.

- Opening (move word 0x8e2d50 = 1): `Camera_lookAt(cam, 45, &h)`; far clip 720.0 if
  forward z > −0.491 (0x22ffbc). If `g_swoopDone` 0x4fdce8 ≠ 0 and not arrived, repeat in
  the same tick (each pass may set the far clip again). Arrived: move = 0.
- Closing (−1): nothing while `g_shopOpen` 0x41b50c ≠ 0. Else `Camera_lookAt(cam, −45,
  &h)`; far clip 1800.0 if forward z < −0.645 (0x230020). Arrived: game message 3
  (`net_sendGameMsg` 0x13db38 with the byte 3), move = 0.
- Either way the task returns after this step; prompt-shown 0x8e2e90 was cleared first.

### 2.5 `Camera_apply(x, y, z, cam, 0)` 0x2035c8 (E `apply`)

Matrix = identity, rotated about X by s16(u16(+0x6a) + 0x3fd3) and about Z by +0x68
(`mat34_rotateAxis` 0x163000 twice). Then, when `g_cameraShake` 0x4f8488 > 0 **and**
(`game_isFrozen()` = 0 **or** `dialog_isOpen()`), three draws of `g_cosmeticSeed`
0x404460 (s₁, s₂, s₃ by s = s × 0x19660d + 0x3c6ef35f) move the position by
((s₁ ≫ 16) × 2⁻¹⁶ − 0.5) × 2 × shake, ((s₂ ≫ 16) × 2⁻¹⁶ − 0.5) × 2 × shake and
((s₃ ≫ 16) × 2⁻¹⁶ − 0.5) × shake, and the shake drops by 0.5 (0x203884). `dialog_isOpen`
is asked only when the game is frozen. Last, `camera_setView(&pos, &matrix)` 0x18a2b0.
The dialog machine calls it from message 0 (`docs/dialog.md` 2.4 step 3) and on every swoop
step, so **a dialog can draw the cosmetic seed** (correcting `docs/dialog.md` section 9).

## 3. The 24 open `dialog_isOpen` checks (E `sites`, `frozen`, `recall`, `camctl`, `apply`, `idle`)

`docs/dialog.md` 6.1 had followed 10 of the 34 call sites. These are the other 24. "Kind":
**sim** gates a game message, the pause or the freeze; **input** gates this machine's pad or
a menu entry; **draw** only drawing; **seed** gates a cosmetic-seed draw. The dialog state
itself is the same on every machine (it is opened and closed by game messages), so these
gates agree across machines.

| Site | Function | Kind | Effect while a dialog is open | Conditions the run varied |
|---|---|---|---|---|
| 0x1548d0 | `Prop_draw` 0x1548bc | draw | returns at once: **props are not drawn** (nor their matrix +0x110 updated) | — |
| 0x156dcc | `PhProp_draw` 0x156db4 | draw | returns at once: physics props not drawn | — |
| 0x18cd08 | `pauseMenu_task` | input | entry `menu_exitmission`: +4 = 5 (not when mode B hides it) | `g_pvpModeB` |
| 0x18ceb4 | `pauseMenu_task` | input | entry `menu_kickplayers`: +4 = 5 instead of 0 | active slot count |
| 0x18d400 | `pauseMenu_task` | input | entry `menu_recall`: +4 = 5 | net, hit points, `jumpgate` task, camera mode |
| 0x18d498 | `pauseMenu_task` | input | entry `menu_changeplayers`: +4 = 5 | no-save zone, net, camera mode |
| 0x18e0e4 | `warpMenu` 0x18e00c | sim | offline: the start button cannot open the pause menu (an open one can still close) | camera mode |
| 0x1a47bc | `Player_draw` | draw | `Player_interact(P, 0, 1)` not called | paused, lockout, spell selector |
| 0x1a4ed8 | `Player_draw` | draw | net game: the `busy.tex` icon (`icons.lmp`) above a remote player with flag 0x400000 not drawn | net, flag 0x400000, local slot |
| 0x1bc07c | `Player_drawMarker` | draw | no player marker | — |
| 0x1bcf18 | `player_pollRecallButton` | sim | no `hudmsg_sendRecall` (E `recall`, full model) | 13 conditions |
| 0x1db5b0 | `hud_drawControllerOut` | sim | offline: no automatic pause menu on a removed controller (the message is still drawn and 0x4f6708 set) | net, pause menu open, front end |
| 0x1dd380 | `hud_spellSelect` | input | no pad reading unless `g_localMenuOpen` 0x41b69d | lockout |
| 0x1de9e0 | 0x1de8c4 (HUD panel, unnamed) | input | no weapon swap / ability cycle / cursor input | lockout, camera mode, paused |
| 0x1dedc4 | 0x1de8c4 | input | its second pad test is skipped | lockout, camera mode, paused |
| 0x1df7bc | `hud_drawCompass` | draw | no compass | compass byte 0x4f66d5 |
| 0x1e0260 | `hud_drawNetCamPrompt` | input | spectator prompt not drawn and confirm does not cycle (the `Camera_cycleSpectated(cam, 0)` before the check still runs) | cutscene, pause menu |
| 0x1ebe8c | `game_isFrozen` | sim | offline: the controller-out flag 0x4f6708 does **not** freeze the game (E `frozen`, 512 combinations) | all inputs |
| 0x1f6b78 | `fx_modelStatusEffects` | seed | returns: no item / status effects on models, **no cosmetic draws there** | flag 0x10000000 of 0x44fe08, model |
| 0x203464 | `Camera_update` | input | +0x60 (user control) = 0 (E `camctl`) | 8 inputs, modes 0/1/2/6 |
| 0x203820 | `Camera_apply` | seed | the shake (3 cosmetic draws) runs even while frozen (E `apply`) | shake, frozen |
| 0x218f14 | `memcard_saveScreen` state 4 | sim | the card screen is abandoned: pause popped offline, state −1, lockout 15, menu state message | net + pending level, cutscene |
| 0x31df40 | 0x31deec (unnamed, net message list) | draw | net game: the list is not drawn (offline it pumps 0x31d34c regardless) | net, front end, word 0x50391c |
| 0x322b8c | `mainloop_runSession` idle voice | seed | `g_idleVoiceCountdown` 0x506054 is held; at 1 it would draw the cosmetic seed once for `player_voice((s ≫ 16) % g_numPlayers, 2)` (E `idle`) | cutscene, paused, local menu, players |

Each stretch was run from before the conditions it lists to labelled exits on both sides
of the branch, with the dialog open and closed and the other conditions varied; every
site reached both outcomes (E `sites`). What the code then does on the open side (the
right-hand effects beyond the branch, e.g. the card screen's clean-up) was read (O), not
run, except for the six functions run whole (`frozen`, `recall`, `camctl`, `apply`,
`idle`, and the pause entries' stored values, which the stretches check). Pause entry +4:
5 is stored when a condition fails and 0 when all pass (I: 5 = not selectable). With the
10 sites of `docs/dialog.md` 6.1 this covers all 34.

## 4. The box where `box.tex` is not loaded (E `box`)

- `dialog_loadBox` 0x22f910 runs from `game_loadLevel` 0x1e617c. `strcmp(g_levelName
  0x44fe18, "intro")` is case-sensitive; in `intro` or with `g_pvpModeB` 0x4f7120 set it
  writes nothing. Otherwise word 0x4fe538 = `res_find("dlgbox.lmp", "box.tex")` (0 when
  absent).
- 0x4fe538 is initialised data in the executable with the value **0**, and these two are
  its only accesses (`tools/gxref.py`: the store 0x22f960, the load 0x230ad8). So in
  `intro` and arena mode B the word is 0 if no earlier level loaded the box, or the
  previous level's `box.tex` address.
- The draw passes it straight to `ui_drawSprite` 0x17fb68 → `ui_drawSpriteImpl` 0x17b590,
  which first reads the s16 width (+0) and height (+2) of the texture. With 0 the run
  faults reading address 0 (E). On a console that is kernel memory; what it holds is U.
- **This never happens with the shipped data**: `intro` has 117 objects, none with
  `dialogScript`, no `startDialog` call and no `.dbin`; the seven mode-B arena levels (the
  table at 0x503798, `docs/arena-modes.md` on `t3/research-arena-match`) have 686 objects
  and likewise none of the three (section 8). Nothing else opens a dialog.
- `dlgbox.lmp` is a loose file on the disc (not inside a GOB); its `box.tex` header is
  560 × 156, as `docs/dialog.md` 7 states.

## 5. The cursor glyph byte 0x41b978 (E `buttons`)

`dialog_drawTask` prints the cursor and the "more" mark with `"%c"` of the byte at
0x41b978 (`docs/dialog.md` 7). Its only writer is `game_initCamera` 0x1e6b68 (gxref), by
the s8 at 0x41b69c (also read by `config_setDefaults` 0x1e6238):

| 0x41b69c | 0x41b978 | 0x41b97c | `g_btnConfirmMask` 0x41bfbc | `g_btnCancelMask` 0x41bfb8 | also |
|---|---|---|---|---|---|
| 1 | 0x7e | 0x7b | 0x40 | 0x20 | 0x41b968 = 0x10, 0x41b96c = 0x7c, 0x41b970 = 0x80, 0x41b974 = 0x7d, 0x41b960 = 0x40, 0x41b964 = 0x7e |
| 0 | 0x7b | 0x7e | 0x20 | 0x140 | 0x41b968 = 0x80, 0x41b96c = 0x7c, 0x41b960 = 0x20, 0x41b964 = 0x7b |
| other | not written | | | | |

Both paths also clear 0x4f85b4 and 0x4f7134 (0x1e6bd0–0x1e6bd8), after `Camera_init`
(first time only, flag 0x4f834c) and `skills_callVslot9All`. The executable's initial
byte at 0x41b69c is 1, so with no other writer the cursor is character 0x7e of
`gamefontmed.fnt`; which button picture that glyph holds is in the font, not here. No
lui-based writer of 0x41b69c was found (gxref); a copy through a pointer (the options
file) is not excluded (U).

## 6. The TestLocation talkers (E `factory`)

`TestLocation` is not a string anywhere in the executable's data, so no class test of
`world_objectFactory` 0x159c94 matches it (`docs/objects.md` "The object factory"). The
factory then tries properties, in this order (0x15d690–0x15d998; each key lower-cased in
place by `props_getInt` 0x14f730 / `props_getStr` 0x14f850, then matched
**case-sensitively** against the start of each `key=value` entry):

| Test | Constructor (pool size) |
|---|---|
| `CreatureContainer` int ≠ 0 | 0x243624 (0x3d0) |
| `AutoContainer` ≠ 0 | light: 0x24259c (0x150), else 0x23d93c (0x148) |
| `AutoChest` ≠ 0 | light: 0x241468 (0x100), else 0x23ad18 (0xf8) |
| `AutoProp` ≠ 0 | light: 0x2416c4 (0x448), else 0x23c44c (0x198) |
| `AutoEmitter` ≠ 0 | 0x240dc8 (0x60) |
| `AutoDoor` or `AutoSwitch` ≠ 0 | 0x23c44c (0x198) |
| `Critter` ≠ 0 | 0x2547fc (0x448) |
| `Generator` present | 0x2657a0 (0x3e8) |
| `SmokeGen` present | 0x31d180 (0x490) |
| none | **returns 0: the record makes no object** |

"light" = `propList_hasAnyLight` 0x23a2b4: `ParticleEmitter`, `DynamicLight`, `Halo`, or
the same with 0…3 appended, non-zero. Ints are newlib `atoi` of the value.

On the disc there are **145** `TestLocation` records; 2 carry `dialogScript`, `showName`
and `dialogOffset`, 1 carries `key`; none has a fallback key or an upper-case key. The
original factory, run on each of the 145 records in the emulator, made **no object for any
of them** (the reference agrees), and no script string names the class. So the two
`TestLocation` talkers do not exist in the game: nobody can talk to them, their
conversations are never opened from them, and the `key` prompt record is inert. The native
client should create nothing for this class (no error, no talker).

## 7. Seeds and lockstep

Calls that draw a seed, reached from or gated by the dialog:

| Call | Seed | Draws | When |
|---|---|---|---|
| `Camera_apply` 0x2035c8 | `g_cosmeticSeed` 0x404460 | 3 | shake > 0 and (not frozen or a dialog open); every swoop step and message 0 call it |
| idle voice 0x322bc0 | `g_cosmeticSeed` | 1 | countdown reaches 1; **held while a dialog is open** |
| `fx_modelStatusEffects` 0x1f6ac8 | cosmetic (symbol note) | any | **skipped while a dialog is open** |
| `Camera_setupDialogView`, `Camera_lookAt`, the run task's camera step | none | 0 | E: no write to 0x404460/64/68 |

None of these touches `g_randSeed` 0x404464 or 0x404468 (E `seeds`: no suite wrote a
generator word except the cosmetic draws above, which match the reference exactly).
Everything in this document reads either shared state or per-machine state that is the
same on every machine while a dialog is open; the camera, the far clip, the shake and the
cosmetic seed are per machine (as in `docs/dialog.md` 9).

## 8. Disc census (counts only; `tools/dialog_gaps_census.py --disc`)

US v2.00, 120 GOB archives with 120 level scripts; original `sscanf` and factory run in
`ee_emu`.

| What | Count |
|---|---|
| `TestLocation` records / with `dialogScript` / `showName` / `dialogOffset` / `key` | 145 / 2 / 2 / 2 / 1 |
| … with a factory fallback key / factory result "no object" (original, reference) | 0 / 145, 145 |
| script string literals naming the class | 0 |
| `intro`: lumps / objects / talkers / `startDialog` calls / `.dbin` | 1 / 117 / 0 / 0 / 0 |
| arena mode B (7 table names): lumps / objects / talkers / `startDialog` / `.dbin` | 7 / 686 / 0 / 0 / 0 |
| `dlgbox.lmp` loose files / with `box.tex` / header 560 × 156 | 1 / 1 / 1 |
| `startDialog` calls reached from a talker's `dialogScript` with the swoop flag | 23 |
| … with `b` ≠ 0 (the player-side test runs) | 4 |
| … whose dialog name is a registered object name / several objects | 23 / 4 |
| … speaker `dialogOffset` fields converted: 4 / absent | 19 / 4 |

So 19 swoop openings are fully determined; in **4** the speaker has no `dialogOffset` and
the camera's sideways offset is the stale stack word (section 10).

## 9. What the native client should implement, ranked

The native dialog port (`open-champions` worktree `dialog`, report
`work/loop-dialog-r1-report.md`) runs the camera words with the move arriving at once,
passes the UI fade as 1.0, gates only `Player_run` / `Player_move`, does not draw the
cursor, and refuses `TestLocation`. In order of value:

1. **The camera swoop** (2.2–2.4): `Camera_setupDialogView`, `Camera_lookAt` with the
   47…182-call arrival, the repeat while `g_swoopDone`, the far clip by forward z, closing
   held while the shop is open, message 3 only on arrival. This fixes when a conversation
   really ends (message 3, so the post action, the pending level and the deferred shop).
   The 4 openings without `dialogOffset` need section 10 settled first; until then refuse
   or report them, do not pick a value.
2. **Draw gates while open** (3): props and physics props hidden, no player marker,
   compass, remote busy icons, interact prompt or net message list.
3. **Input and menu gates while open** (3): start button cannot pause offline, four
   pause entries unavailable, no recall message, no spell selector or HUD panel input,
   camera user control off, no automatic pause on a removed controller, the card save
   screen abandoned, and `game_isFrozen`'s exception for the controller-out flag.
4. **The cursor glyph** (5): character 0x7e (layout byte 1, the executable's value) or
   0x7b (layout 0) of gamefontmed — unblocks the cursor and "more" mark the port does not
   draw.
5. **Cosmetic-seed parity** (2.5, 7): the three shake draws in `Camera_apply`, the idle
   voice held, status effects skipped while open.
6. **TestLocation** (6): create no object; 145 records, all inert.
7. **The box without `box.tex`** (4): nothing to build; unreachable with the shipped data.
   If a mod opens a dialog there, refuse rather than draw.

## 10. Open questions

- **The stale lateral offset** in the 4 swoop openings whose speaker has no
  `dialogOffset` (and any value with fewer than four fields): it is the word at
  `sp − 0x64` of `dialog_onMsg`'s frame as the last deeper call left it. Running message 0
  with every callee real (scripts, text measuring, lump loading) or watching the camera in
  those openings on the game would settle it.
- The meaning of the pause-entry value 5 (I: not selectable) and the name of the HUD panel
  0x1de8c4 and of 0x31deec (net message list) are not established.
- What address 0 holds on a console (only matters for a dialog in `intro` or arena mode B,
  which the disc never opens).
- Whether anything copies the options file over 0x41b69c (section 5).
- `Camera_apply` with a forward vector (its fifth argument ≠ 0) was not modelled; the
  dialog never passes one.
- No run on a game.
