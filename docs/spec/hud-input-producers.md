# HUD input producers and native port order

SLUS-20973 v2.00, researched 2026-10-23 on `t3/research-hud-inputs` from
main `034d0c0`. This is the upstream handoff for the native HUD's four refused
inputs. It joins the already executed arithmetic contracts in
[hud-quickslots.md](hud-quickslots.md), [hud-gold.md](hud-gold.md), and
[hud-minimap.md](hud-minimap.md). The latter contracts came from
`t3/research-hud-gaps` `f7c3964`; player lifecycle came from
`t3/research-player-state` `9c23686`, item handling from `t3/research-items`
`49bc578`, and text lookup from `t3/research-ui-text-gaps` `523b3db`.

**Evidence labels:** Observed (O) means an addressed instruction or call site
in the original ELF; Executed (E) means `tools/ee_emu.py` ran that original
function against constructed state and compared the reference model. Unknown
(U) means this work cannot authorize a native input. No game or console was
run. The new `ref_hud_inputs.py` / `difftest_hud_inputs.py` execute four
upstream properties; the imported quick-slot, gold and minimap difftests
execute their existing downstream properties on seeds 20973 and 7.

## 1. Potion button to notice, count, health and mana

| Producer / input | Address and value | When | Evidence |
|---|---|---|---|
| `Player_run` pad | lockstep pad `0x41bfd8 + 0x58·slot`, pressed +0xc; its 12 short-circuit gates are in `player-tick.md` section 2 | simulation tick; requires record `R+0xac > 0` | O 0x1a5998/0x1a59f0; player-tick.md |
| potion A / B masks | `0x41ba10[slot]` / `0x41ba20[slot]`; A kind 0 health, B kind 1 mana; default R2=0x2, L2=0x1 | `Player_run` calls `Player_usePotion(P,kind,0,0,-1)` on press; B is gated by a level-name check | O; default buttons Ran in `docs/issues/live-rig.md` 4c |
| `Player_usePotion` | 0x1b9cb8; rejects prediction copy flag `P+0xc & 0x20000` or HP ≤ 0 | same simulation tick | E `difftest_hud_quickslots.py use_potion` |
| rates | record `R+0xb8` and `R+0xbc` = min(max HP/mana × 1/480, 0x3effffff) | first writes after the real/alive guard, even if the target is full | E |
| bag 2 | `R+0x2540`, cells 0x48 bytes; count at `R+0x3740`; nine health and nine mana names via pointer tables 0x4ef478/0x4ef4a0 | only if current + pending < maximum; chosen size 0..8 from missing amount, fallback largest available | E `count_potions`, `use_potion` |
| pending heal | HP pending `R+0xb4` or mana pending `R+0xc8` rises by `(size+1)×60`, capped at max − current | same tick; `Player_regenHealth` 0x1b3b90 / `Player_regenMana` 0x1b3900 consume pending at the stored rate later in `Player_run` | E for potion; O for `Player_run` order in player-tick.md 3–4 |
| count and notice | `player_countPotions` 0x1ba5f8 sums signed cell quantities; writes `0x41b940[slot]` health / `0x41b950[slot]` mana | after use/removal; absent kind starts timer line 1/2 for 120 frames; 1..5 left starts line 4/5 for 240 frames | E `count_potions`, `use_potion` |
| draw | timers `0x41b828 + 0x20·slot + 4·line`; rows `0x41b8a8 + same` | notice timer decrements per *displayed frame*, independent of simulation ticks | O/E hud-quickslots.md and hud-dynamic.md |

The local open-inventory route sends inventory drop message 0 instead of
removing the bag cell immediately (`g_localMenuOpen` 0x41b69d, local-slot and
grid gates at 0x1b9fcc). It can momentarily show a different count on that
machine. No potion notice is started for a full target, and the health/mana bar
does not jump directly to its pending total. These are Executed in
`use_potion`; `Player_run` itself was not executed by this new upstream probe.

## 2. Raw D-pad to quick-slot, cast and selector display

| Producer / input | Address and value | When | Evidence |
|---|---|---|---|
| `hud_spellSelect` | 0x1dd270, called by `hud_drawPlayerStatus` 0x1dacb8; skill-sheet caller 0x1d4cd8 | drawn HUD frame, local slot only, record HP `R+0xac > 0` | E `difftest_hud_quickslots.py selector` |
| pad | raw local `g_rawPads` 0x4028d0 + 0x58·slot; held +8, pressed +0xc; Up 0x1000, Right 0x2000, Down 0x4000, Left 0x8000 | after nine ordered gates 0x1dd374–0x1dd404; `g_localMenuOpen` 0x41b69d overrides them | E `gates`, `selector` |
| direction and mask | right then left set dx; up then down set dy; later opposing bit wins. Nonzero direction writes `0x5d0bc8 + 12·slot` as `(max(frames,3), A|B|Use,0)` via `net_maskLocalButtons` 0x13e540 | mask lasts three input frames; `g_spellSelectorHeld` 0x41b818[slot] blocks `Player_interact` | E |
| selector message | configured A `0x41b990`, B `0x41b9a0`, Use `0x41b9c0`; sheet accept `0x41b960[0]` | pressed while direction ≠ −1: A/B send HUD message 0 `(slot,button,index)`; Use sends message 13 `(slot,index)`; sheet sends message 1 | E |
| result | message 0 handler `hud_onQuickSlot` 0x1de28c changes `R+0x4a84/85` and swaps duplicate assignments; message 13 handler 0x1de340 queues ability `P+0x488` in state 2, or shows kind-1 warning | on message dispatch; ability A/B reads `R+0x4440 + 0x68·index` in `Player_run` | O/E hud-quickslots.md, game-messages.md |
| ring | first eight ability records, `g_spellSelectorDir` 0x4f66b8, `g_spellSelectorAlpha` 0x86a8d8 and `R+0x4a74/78` | fades/steps per drawn frame; icons, name and `AssignCast` prompt from skill/text tables | E `selector`; ui-text-gaps supplies text lookup |

The nine gates are, in order: menu input lockout 0x41b4fc, dialog, camera
mode at `g_localCamera` 0x4f8450 +0x34, pause 0x41b4f4, pause menu byte
0x44fa78, busy memory card, medal dialog ticks 0x4f7114, running jumpgate
task, and input-block byte 0x4f66c8. Each gate is compared separately in
`gates`. The selector reads the **raw local pad** from a draw task; its message
handlers are the simulation edge. A Godot key without the configured mask and
message dispatch does not reproduce this producer.

## 3. Gold event to floater, payout and motion

| Event | Call and value | When | Evidence |
|---|---|---|---|
| gold pile touch | `Gold_onTouch` 0x157a9c calls `hud_addGoldFloater` at 0x157b30 with toucher slot `+0x3c8`, pile position `+0x10..18`, amount `+0x80`; then amount 0 and `obj_delete` | real player flag `0x40`, no copy `0x20000`, s8 countdown `+0x4c` = 0, amount nonzero; second touch gets nothing | E `difftest_hud_inputs.py Gold_onTouch` (180 seeded cases) |
| automatic chest | `AutoChest_interact` 0x23b894 calls at 0x23ba1c with s16 `+0xdc`, then clears it | first interaction opens; positive amount stays for a second interaction | O hud-gold.md 2; not executed here |
| chest | `Chest_interact` 0x292a2c calls at 0x293180 with s16 `+0x4c`, then clears it | after opened flag `+0x84` | O hud-gold.md 2; not executed here |
| floater | `hud_addGoldFloater` 0x1dc268 fills first free of 8 records at 0x86a900, each 0x24 bytes; `+0x18` start `g_simFrame` 0x44fdcc, `+0x1c` amount, `+0x20` slot | pickup/chest call on every machine; all eight busy credits record gold directly without a floater | E `difftest_hud_gold.py add` |
| payout | `hud_tickGold` 0x1dcb80 in `hud_run` task 50; age × 3 ≥ 128 releases at tick 43 to pending 0x86ace8[slot]; pays `(pending+7)>>3` per tick into `R+0xe4`, cap 99,999,999 | simulation ticks; `game_clearLevel` flushes remaining and hides counter | E `tick`, `life`, `flush` |
| display | each active local floater resets hold 0x86acd8[slot] to 60; alpha 0x4f6950 rises by 4/frame to 128, then falls by 4/frame after hold 0 | `hud_drawGold` 0x1dc708 per displayed frame; direct gold writers alone leave counter hidden | E `draw`, `life` |

At spawn, the local camera view-projection 0x44f140 projects the world position
to screen x/y (0x1dc268). One **cosmetic** seed draw at 0x404460 rotates the
initial drift; no shared or third seed draw. The draw updates position by its
velocity, pulls toward the slot's text target by 0.0063659 and damps by
0.0877665 each displayed frame. Floater alpha is `max(0,128−3×age)` and its
amount is plain decimal. The off-screen byte `+0x21` is written but no reader
was found in this gold path (O). One displayed frame per tick makes a lone
pickup's counter visible for 133 frames in `life`; the frame-to-tick ratio on
hardware remains U. Script gold, shop and new-character 500 are direct record
writers and do not call the floater (O, hud-gold.md 2).

## 4. World, camera and objects to the minimap projector

| Producer / input | Address and value | When | Evidence |
|---|---|---|---|
| world load | `world_fixup` 0x181d30 calls `automap_loadGrid` 0x168894 at 0x1822a0; world +0x6c texture, +0x70 keep-raw gate, +0x80 grid pointer | level load; missing texture or grid pointer zeroes W/H | O; E `difftest_hud_inputs.py automap_loadGrid` |
| grid | source header x0/y0/W/H s16 at +0/+2/+4/+6, then u16 cells; destination origin 0x4044a8/ac, dimensions 0x4044dc/e0, 216×216 cells at 0x4044f0, stride 432 bytes | copies W cells per row; leaves other runtime cells intact | E `automap_loadGrid` (160 seeded cases) |
| reveal | `minimap_draw` 0x1e4a38 calls 0x16a4b0 for every player's nonnull `R+0x43d8` object using its `+0x10..18` position | each draw-world call after the world/camera gate, **before** the projection gate; raises explored high nibble in a radius-eight-cell disk | O; E integer-cell kernel `draw-time reveal` (120 cases), call order `minimap_draw feed` |
| reveal all | `script_revealMap` 0x141e78 calls `automap_revealAll` 0x16a760; high nibble set to 15 for loaded W×H, flag 0x6e14d4 = 1; `minimap_applyMode` 0x1e3ff0 calls 0x168990 to clear count and flag | script action; flag also widens blip query from 960 to 3840 world units | O 0x16a7d8/0x16a834; E feed radius |
| map mode / zoom | raw pad 0x4028d0 + 0x58·slot and configured map mask 0x41b9e0[slot]; mode 0x4f8400 cycles modulo 3; scale/offset/half-size tables at 0x53e1b8/e8/218; zoom 0x4f71a0 clamped to [0.5,2.0] | `minimap_draw` 0x1e4398–0x1e45b8 before the map gates unless frozen or cutscene; chase offsets by quarter-step per displayed frame | O; mode table E in hud-dynamic.md |
| camera | local camera 0x4f8450, mode +0x34 must equal 1; centre x/y at +0x18/+0x1c, yaw via `Camera_getYaw` 0x207450 | `minimap_draw` calls projector 0x168cac at 0x1e4d00 with these plus scale×zoom and mode sizes | O; E projector `difftest_hud_minimap.py` |
| blip query | box centred on camera x/y and the spectated player's object z; ±960, or ±3840 after reveal-all; `world_collectObjectsInBox` 0x14a928, limit 200, output list at stack and global 0x4f867c | after projector gate 0x16a838 succeeds; network path removes queried `+0xc & 0x40` players then appends `net_objOrGhost` 0x13e180 for each active player's object | O; E `minimap_draw feed` (100 cases) |
| blip callback | `minimap_blipColor` 0x1e40a8 reads 0x4f867c[i], player slot `obj+0x3c8`, record HP, object flags/angle/position | projector asks indices until null; dead-player blink uses bit 0x20 of `g_simFrame`; shadow then coloured triangle at zoom >0.125 | O; E `draw_with_blipColor` |
| static icons | `PushTrigger_ctor` 0x1eca64, `JumpGate_ctor` 0x27c834, `Savepoint_ctor` 0x28ccf0 call icon registrar 0x1689a4; table 0x6e0f90, count 0x6e14d0 | construction/load; projector tests optional quest variable and script per icon at draw time | O call sites and stores; E projector packets with constructed icon entries |

`minimap_draw` skips the map when offline local-alive slot/object is absent,
world texture or grid pointer is absent, death task or memory-card state
4/8 is active, camera mode is not 1, spectated slot/object is missing, or
spectated HP is below zero (O 0x1e4320–0x1e4ab0). Projector 0x16a838
also needs enough display-list space and half-width ≥2 (E). Modes 0/1/2
target full, corner and hidden views; the chase means mode 2 can still
show map cells during its transition. The reveal loop runs before the
spectated-player and display-list checks, so exploration may advance even
on a call that renders no map. `drawWorld` task 30 calls `minimap_draw`
at 0x1ebc60 (O); the source object's movement is not a map-specific tick.

**Unknown:** VU1 tile arithmetic at 0x403e20 is read but unexecuted; the
world +0x6c tile atlas layout remains undecoded. Arbitrary fractional
world-position reveal values are outside `ref_hud_inputs.py`'s integer-centre
model. Script gates on icons can have effects during draw; their safety in a
native online port is unestablished. These stay refused despite the EE
projector packet difftest.

## Ordered native port list

1. **Player tick and inventory edge.** Bring the original per-slot pad masks,
   `Player_run` potion press, bag-2 cells/names, `Player_usePotion` pending and
   rates, inventory removal/drop message, and regen into one live player.
   Publish potion count and notice timers only from that edge. Test a missing
   potion, a small stack, full health, menu-open removal and both kinds.
2. **Selector input and message dispatch.** Carry raw local held/pressed words,
   nine gates, configured A/B/Use/accept masks and three-frame mask; send
   messages 0/1/13 and let their tick handlers update quick slots or queue
   cast. Then drive the ring from skill records and the text lookup.
3. **Gold events and credit.** Wire real gold touch and both chest interactions
   to floater creation, then task-50 payout/flush. Couple the draw's local
   hold/alpha and motion to the active floater records. Direct record gold
   changes retain their original hidden-counter behaviour.
4. **Automap state and draw feed.** Load the world's texture/grid; reveal from
   each player object on `drawWorld`; carry raw map-mode input, local camera,
   spectated object and the query/ghost list into the EE projector. Add
   static icons only with their constructor metadata and a safe decision for
   quest-variable/script gates. Keep VU tile rendering and atlas identity
   refused until their separate evidence is established.

## Validation boundary

`difftest_hud_inputs.py` compares original instruction effects for 160 grid
loads, 120 exact integer-centre reveals, 100 draw-feed calls and 180 gold
touches per seed. `difftest_hud_quickslots.py`, `difftest_hud_gold.py` and
`difftest_hud_minimap.py` compare the previously pinned downstream reference
models. These are function-level executions with stubbed external services,
not an in-game playthrough or proof of a native producer. All tracked files
are authored models, tests and documentation; no disassembly or game bytes.
