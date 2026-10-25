# Player animation selection — SLUS-20973 US v2.00

2026-10-23. Research worktree `t3/research-player-anim` from main `034d0c0`.
This is a function-level trace, not a running-game or native visual check.
**Observed** means read in the original executable at the stated address.
**Executed** means compared with original code in `tools/ee_emu.py` on built state.
**Inferred** is a consequence of those readings. **Unknown** names an open gate.
The detailed state model is `tools/ref_player.py` / `docs/spec/player-tick.md`, the
animation engine is `tools/ref_anim.py` / `docs/spec/animation.md`, and this
worktree adds `tools/ref_player_anim_select.py` for the four persistent slots.
Cross-checks: `t3/research-anim` `5694ae3` (player-animation-dispatch.md) and
`t3/research-player-model` `7f13899` (player-model-resources.md and its ignored
111-slot resource manifest). The combat timing trace is
`t3/research-combat-walk` `e20760a`. None of their commits was copied here.

## 1. Which resource is selected

**Observed:** `Player_ctor` 0x1a1d98–0x1a1db4 chooses one of 12 animation
definitions using player record `R+0x54` (model index) and stores the definition
on the player through its base constructor at `P+0x24`. The record is
`R = 0x4d8af0 + slot*0x4c30`; weapon animation class is signed byte
`R+0x4a86`, 0..7, and changes on equipment paths such as 0x1c2ad4–0x1c2c40.
The body selection from `R+0x54` and animation selection from `R+0x4a86` are
separate axes. The class meanings below come from names and equip behavior;
the exact weapon kind wording is **Inferred**.

**Observed:** a definition has seven header resources and eight rows of 13
resources. A resource pointer for a weapon-row role lives at
`*(P+0x24) + 0x68*class + k`, where `k` is the offset below. In the player-model
manifest's one-based slots, role `j` is slot `8 + 13*class + j`. Repeated names
still occupy separate slots. Resolve each pointer from the model's animation
lump, not from its SELECT body/texture lump.

| Class | Row name prefix | Use | First attack clip at `k=0x74` |
|---:|---|---|---|
| 0 | `ohw_` | one hand | `ohw_atakseq1` |
| 1 | `dhs_` | two hand kind 1 | `dhs_atakseq1` |
| 2 | `dha_` | two hand kind 2 | `dha_atakseq1` |
| 3 | `l_` | long weapon | `l_atakseq1` |
| 4 | `b_` | bow | `b_attacka` |
| 5 | `nw_` | unarmed | `nw_atakseq1` |
| 6 | `ohw_` | thrown weapon | `throw` |
| 7 | `dw_` | dual wield | `dw_atakseq1` |

**Observed**, definition rows at 0x4ec8d0..0x4eefa8 and code uses at
0x1b2470–0x1b2638 / 0x1a7f54–0x1a7fbc: each row has idle `k=0x44`
(`j=0`), walk `0x4c` (`j=1`), run layer 1 `0x54` (`j=2`), run layer 2
`0x5c` (`j=3`), heavy `0x64` (`j=4`), cast `0x6c` (`j=5`), first
attack `0x74` (`j=6`), hit reaction `0x7c` (`j=7`), block `0x84`
(`j=8`), block hit `0x8c` (`j=9`), block alternative `0x94` (`j=10`),
block pose `0x9c` (`j=11`), evade `0xa4` (`j=12`). Both run slots
usually resolve to the same named clip; their **track cells remain distinct**.
Model-specific row fallbacks are literal slot contents, not a native rule to
synthesize a missing pose. See the 111-slot manifest for each model.

## 2. Base pose and movement

**Observed:** `player_resetIdleAnim` 0x1b2470–0x1b2638 returns if the
record has no player at `R+0x43d8` or HP `R+0xac <= 0`. Otherwise it
puts idle, walk, run 1, run 2 into cells 0–3 at `P+0x11c + 0x20*i`.
Cell 0 weight and life are 1; cells 1–3 are 0; each has flags `0x1205`
(loop, report end, keep, persistent). It sets count `P+0x118=4` and
releases animation caches. Constructor 0x1a2330–0x1a2338 and equip paths
call it. A display-only player (`P+0x462`) instead looks up a class-specific
`*_idled` name for cell 0 (0x1b24e8–0x1b25ac); the ordinary player takes
the table idle pointer. **Executed:**
`difftest_player_anim_select.py` calls 0x1b2470 in `ee_emu.py` with
synthetic resolved pointers and compares all four clip, weight, life, flags
and the count, including both guards. It deliberately does not run loading,
cache release, or display-only name resolution.

**Observed:** neutral `Player_run` state 2 enters `Player_move(P,0,...)`
at 0x1a8094. `Player_move` 0x1b40d8–0x1b420c builds speed scale from
0.861945 offline or normally 0.75 in net play, then record multiplier
`R+0x4c20`, level `g_runSpeed` 0x4f8418, cap 1.2, and a Drowsy factor
when present. The `watmedal` level overrides the net base; PvP mode B and
0x4f7124 also affect that choice. It multiplies scale by stick magnitude,
capped at the scale, to make `s`. See `movement-camera.md` section 4.1 for
the complete conditional order. **Inferred:** speed is continuous input to
a layered blend, not a discrete idle/walk/run state switch.

**Observed**, 0x1b4794–0x1b4a3c, in mode 0:

| Input or field | Original rule |
|---|---|
| playback `r` | `s<0.43`: `s*2.3255813`; `s<0.7`: `(s-0.43)*3.7037034*0.3499999+1`; else `(s-0.7)*3.333333*0.15000009+1.35` |
| blend `B=P+0x46c` | `r>0.01`: add 0.1 per tick up to 1; on overflow reset idle cell time `P+0x134=0`. Otherwise subtract 0.1 down to 0 |
| advance | at `r<0.01` and `B<0.05`, step at 1.0 and return no event; otherwise step at `r` |
| acceleration | `s=min(s,P+0x468+0.05)`, then store `P+0x468=s` |
| weights and lives | cell 1=`B`; cell 2=`float(B*(s-0.45)*3)`; cell 3=`float(B*(s-0.7)*3)` (the latter two use software double before narrowing; negative effective blend clamps to zero in the animation engine) |
| footstep event | return walk event bit 1 below `s=0.6`, run bit 4 from `s=0.6`; `Player_run` calls `Player_footstep` on the returned bits |

At rest the idle layer advances at rate 1.0 after the ramp falls below 0.05.
Walk starts as `B` rises; run layer 1 contributes above `s=0.45` and run
layer 2 above `s=0.7`. **Inferred:** at ordinary offline maximum
`s≈0.862`, the two run weights are about `1.236B` and `0.486B` before
the engine clamps their effective blend. At a net cap of `s=0.75`, they
are `0.9B` and `0.15B`. `Player_move` modes 1, 4 and 6 clear `B` and
base movement weights without stepping; modes 2, 3 and 5 leave those
cells alone (0x1b4b90–0x1b4bd0).

**Observed:** `Player_ctor` 0x1a2388–0x1a241c writes two walk event
slots (0.25/0.75 s, bit 1) and two run slots (0.45/0.95 s, bit 4)
for rows 0–5; row 7 has no such constructor write. `Player_animStep`
0x1b9520 advances `P+0x114` via `anim_advance`, with Drowsy and slow
scaling, and turns root displacement into world axes. `anim_advance`
0x16d748 blends tracks using `min(weight,life)` clipped to 0..1,
advances time and handles loop/end/purge flags (`animation.md` sections
2 and 5). A full-weight action track with purge-below can freeze lower
tracks while the persistent four survive. This matters to restarting the
idle cycle after an action.

**Observed:** `Player_idleFidget` 0x1bc2f8 can start a looping
`<prefix>_idled` by name with 0.5 s blend and flag 1 only with exactly
four tracks and a shared draw below `0xe2`. Stick magnitude over 0.01
fades it out over 0.2 s. This is separate from cell 0's `*_idlea`.

## 3. Actions and transitions

`anim_startBlendInOut` is 0x16ceb0; `anim_start` is 0x16cfe0.
**Observed** rows below cite start sites in the original code. A 0.1 s
blend uses raw `0x3dcccccc`. Animation flags are engine inputs, and
the `P+0x11a` union also carries action markers used by `Player_run`.

| Trigger / player state | Chosen clip | Start, blend, flags | Transition evidence |
|---|---|---|---|
| First melee, state 1 | class row `0x74`, variant 1 | blend in/out 0.1/0.1, `0x802` at 0x1a7fb8–0x1a7f7c | state 2 sets `P+0x461=1`, clears movement layers, records start frame `P+0x448` |
| Heavy melee, state 1 | row `0x64` | blend 0.1/0.1, `0x812` at 0x1a7308 | older skill id `0x25`; only with no active heavy and <6 tracks |
| Bow or thrown shot, state 0 | row `0x74` (`b_attacka` / `throw`) | blend 0.1/0.1, `0x12` at 0x1a7f54–0x1a7f7c | leaves after marker `0x10` clears and attack delay passes; release is frame-based |
| Bow / thrown close melee, state 1 | name `b_attackb` / `nw_atakseq3` | blend 0.1/0.1, `0x802` at 0x1a79fc / 0x1a7a48 | target within 60 after target search; differs from shot |
| Combo continuation, state 1 | named `<prefix>_atakseqN`; bow / thrown as above | start 0.1, `0x802` at 0x1aacdc–0x1aaf00 | `Player_pickAttackAnim` 0x1bba88 writes variant `P+0x461`; the name is looked up in the model's animation lump |
| Hit reaction, state 3 | row `0x7c` | blend 0.1/0.1, `0xa` at 0x1b317c / 0x1b38d0 | stagger or flinch; leaves when marker 8 clears at 0x1ab1f0 |
| Knockdown, state 3 | named `knockdown1_` / `knockdown2_` plus angle suffix `a`..`d` | blend 0.1/0.1, `0x80a` at 0x1b2f40–0x1b30bc | large unresisted knock; chosen from weapon class and relative hit angle |
| Death, state 4 | header `def+0x14` (`dha_death`) for class 2 except models 2,3,6,7; otherwise `def+0xc` (`nw_death`) | start 0.5, `0x206` at 0x1b34c0–0x1b34fc | dead state does not return to neutral; respawn replaces object |
| Cast, state 5 | row `0x6c` | start/blend according to skill kind at 0x1ab760 / 0x1aba80 / 0x1abf64 | cast point is track weight: 1.0 offline, 0.5 net; phase and `0x8000`/`0x20` markers control exit |

**Observed:** on a new melee swing, the combo window is `22.02` frames
(dual wield `17.616`) minus a haste trim, divided by effective swing
speed. A pressed attack after the window starts the next selected variant
and resets `P+0x448` (0x1aacdc–0x1aae5c). The swing returns to neutral
when movement stick >0.8 after 39.3 frames, its per-swing `P+0x470*60`
deadline passes, or the forced-action latch is set (0x1aaf00 onward).
This is the same transition behind the combat-walk branch's
`walk.once` / `mash.stop` / `mash.12` observations. `Player_pickAttackAnim`
depends on model index, weapon class, old variant and a hash of the
simulation frame; it advances one shared random draw whose value is
unused (`player-tick.md` section 9.10). A fixed one-two loop would be
wrong. The detailed variant table is in `t3/research-anim`'s
`docs/spec/player-animation-dispatch.md` section 3.4.

**Observed:** a hit can enter state 3 before the later damage check;
small hits use the row reaction, larger unresisted hits choose a named
knockdown, and an alive damage path can roll an additional flinch
(`Player_processDamage` 0x1b2cc0–0x1b38d0). Death then takes state 4
and the header death clip. `Player_run` state 3 steps at 1.0 until marker
8 is gone; state 4 steps at 1.0 while `g_playerDeadCountdown[slot]>1`
(0x1ab1f0–0x1ab3f0). Neither is a motion-speed-triggered state.

## 4. Native port order and evidence boundary

### 4.1 Record and state handoff for game-folder play (round 2, 2026-10-23)

The class and action fields have different owners. **Observed:** the player's slot
at `P+0x3c8` indexes `R = 0x4d8af0 + slot*0x4c30`; `R+0x43d8` points back to
the player. `R+0x4a86` is the signed weapon animation class byte. `P+0x58c`
is the 32-bit action state. The model index at `R+0x54` selects the body and
animation definition, but does not supply either field. A game-folder player
needs its own record, equipped item definitions, and an executed player object;
the Full fixture's synthetic player cannot be used as that owner's state.

**Observed equip chain:** an inventory message type 1 calls
`inventory_equipItem` 0x1c27c0 with a slot and item-record pointer. The item
points at a definition; definition `+0x1c` is the equipment slot, `+0x1d`
the category, and `+0x1e` the weapon animation class. After the equip check,
a new category-0 weapon other than ammunition (equipment slot 8) writes the
definition's class to `R+0x4a86` at 0x1c2ad4, calls
`player_resetIdleAnim` at 0x1c2b80, and stores the equipped pointer. Bow
and thrown classes 4/6 choose weapon set 1, while other weapon classes
choose set 0 (store at 0x1c29e8). A second one-hand weapon with the dual
wield passive overrides the class with 7 at 0x1c2b64. Shield/unequip paths
can set class 5 (unarmed), 0 or a swapped weapon's class; an equip of an
already equipped pointer skips the class rewrite. See `ref_messages.py`
`_equip_item` / `unequip_item` and `game-messages.md` section 5.3 for the
complete order and guards. **Executed:** the focused class handoff in
`difftest_player_anim_select.py` runs original equip and then original
`player_resetIdleAnim` on ten synthetic cases per seed. Its other equip
callees are stubs; item permission and real bag ownership are not covered.
The difftest asserts the class-store PCs, reset call site, active-set store PC
and value, and absence of those stores on the ammunition guard. Its dual-wield
case checks both the ordinary class store and the class-7 override.

**Observed selector reads:** `player_resetIdleAnim` reads the class byte at
0x1b24b4, then reads the definition pointer at `P+0x24` (0x1b25b0 and
0x1b25c4) and fills four base cells using `class*0x68 + {0x44,0x4c,
0x54,0x5c}`. In action paths, `Player_run` reads `P+0x58c` for its state
switch at 0x1a5e80; its row clip helper reads `R+0x4a86` and
`*(P+0x24) + class*0x68 + role` (`ref_player.py:anim_name`). The two fields
are inputs to the original state machine and clip lookup, not a standalone
pose enum. The original animation flags, frame timers, and track phases
decide when a state finishes.
The focused difftest asserts the class and definition read PCs in the original
reset function on the live selector path, with synthetic resolved pointers.

| Action | State write and exit in the original | Clip selection |
|---|---|---|
| Melee / heavy | Neutral state 2 enters 1 on accepted attack at 0x1a7804–0x1a7fb8; heavy skill 0x25 also enters 1 at 0x1a7308. State 1 returns to 2 on the elapsed-frame, movement, deadline or forced-action checks at 0x1aacdc–0x1aafe0. | First swing uses class row `+0x74`; heavy uses `+0x64`; continuation uses `Player_pickAttackAnim` 0x1bba88 then a model animation-lump name lookup. |
| Bow / thrown | Accepted shot enters 0 from 2 at 0x1a7804–0x1a7fb8; state 0 returns to 2 only after its flag `0x10` clears and the minimum interval passes (0x1a80e0 onward). A close-range hit can enter melee state 1 instead. | Class row `+0x74`, or the separate close-range named clip. |
| Spell | An accepted cast enters 5 from 2 at 0x1a6c30–0x1a7804. The skill-object branch can return to 2 on refusal; in phase 2 it returns to 2 when flag `0x8000` clears. In phase 0, a missing flagged track starts the cast animation (except kind 6) and advances to phase 1 while staying in state 5. Older-skill branches have their own release and mana/phase exits at 0x1ab4f8–0x1ac13c. | Class row `+0x6c` when the branch starts a cast animation; track flag `0x8000` and its blend value govern the cast point. |
| Hit / knockdown | `Player_processDamage` 0x1b2cc0 enters 3 at 0x1b2ed8 or 0x1b380c; `Player_run` returns 3 to 2 after animation marker 8 clears at 0x1ab1f0–0x1ab2f0. | Class row `+0x7c` for a reaction or a named angle-dependent knockdown. |
| Death | `Player_processDamage` writes 4 at 0x1b34fc. State 4 at 0x1ab2f0–0x1ab3f0 has no transition to 2; `player_respawn` 0x1bd040 replaces the object. | Definition header `+0xc` or the class-2 special `+0x14`, as in section 3. |

The state timings above come from `Player_run` and `Player_processDamage`
instruction reads. The player difftest scripts `Player_processDamage` and
animation callbacks, so it does not execute state-3 or state-4 entry.
The focused selector difftest separately executes lethal damage in original
`Player_processDamage` and observes its state-4 store at 0x1b34fc on both
seeds, with callees stubbed; state-3 entry remains an instruction-read claim.
Original `Player_run`
state reads/exits and `ref_player.py` agree on both seeds. The full equip
reference is `ref_messages.py`; `difftest_messages.py` executes original
`inventory_equipItem`, but is a broader seeded message comparison rather
than a game-folder play session. Neither test supplies a loaded, owned
game-folder player or proves rendered playback.

The native port order for this handoff is: (1) construct the selected
game-folder player's record, slot link and item-definition pointers from
verified session data; (2) run equip/unequip and weapon swap so class
changes and base-cell resets follow the original guards; (3) execute that
same owner's `Player_run` and damage/skill producers, exposing `P+0x58c`
and the frame/track markers; (4) feed those owned values, model definition
and clip slots to the animation dispatch; (5) compare rendered transitions
for weapon swap, melee, cast, hit and death. A missing owner link or action
producer remains an explicit refusal.

1. Bind the actual model-index animation definition and its ordered
   111 resource slots to the class body. Preserve duplicates and absent
   resources; resolve each clip from the model's animation lump. Use the
   player-model manifest as a reference, not as proof of loaded pointers.
2. Implement the four persistent base cells and reset calls for spawn and
   equipment changes; retain separate walk and two run cells even when two
   pointers name the same file. Support loop, keep, persistent and cache
   behavior from `ref_anim.py` before measuring poses.
3. Port `Player_move`'s speed scale, mode-0 playback rate, ramp, acceleration
   and layer weights in the original operation order; route walk/run event
   bits into footsteps. Include net, level and Drowsy speed inputs.
4. Start first attack/shot, combo, heavy, cast, block, hit/knockdown and
   death tracks with their actual flags and blend times. Port
   `Player_pickAttackAnim`'s model/class/frame-dependent variant selection
   and the name lookup for follow-up attacks.
5. Drive action transitions from the original frame, track weight, and
   marker conditions. Port the animation engine's time advance, root
   displacement, track purge and end behavior before treating a pose as
   gameplay parity. Compare idle→move→stop, attack→move, hit→death and
   weapon swap on both seeds and in a rendered native session.

**Executed boundary:** the new base-selector difftest checks synthetic
resolved pointers only. `difftest_player.py` compares the broader player
tick against `ref_player.py`, but its animation calls and hit/death entry
are scripted callbacks; it cannot establish loaded clip poses or rendered
transitions. `difftest_anim.py` can compare `ref_anim.py` with original
animation code only when local extracted `.anm` inputs are supplied.
**Unknown:** full native pose, timing, and visual agreement for the
player across all 12 models; a rendered playthrough is required.

## 5. Verification on this worktree

All commands below used `PYTHONDONTWRITEBYTECODE=1` and the read-only
`SLUS_209.73` input, whose SHA-256 was
checked by each difftest. No generated data was placed in tracked files.

| Command (prefix omitted) | Result |
|---|---|
| `python3 tools/difftest_player_anim_select.py SLUS_209.73 --seed 20973` | 96/96 base selection, 10/10 equip-to-selector cases and 1/1 lethal state entry; 0 mismatches |
| same with `--seed 7` | 96/96 base selection, 10/10 equip-to-selector cases and 1/1 lethal state entry; 0 mismatches |
| `python3 tools/difftest_player.py SLUS_209.73 --seed 20973` | 31,990 compared ticks; all reported properties pass, including 2,500 isolated `Player_pickAttackAnim` calls; scripted animation responses as described above |
| same with `--seed 7` | 31,991 compared ticks; all reported properties pass, including 2,500 isolated `Player_pickAttackAnim` calls |
| `python3 -m unittest discover -s tools -p 'test_*.py'` | 652 tests, OK |

The player difftest records 10 and 9 original unmapped-memory faults at
0x1ab7c0 across its eight sequences for seeds 20973 and 7 respectively;
the reference predicts those faults, so the test reports them as passes.
It compares only the other ticks' writes/calls/seeds. No extracted `.anm`
set was present in this worktree, so `difftest_anim.py`'s clip-dependent
pose comparison was not run here; its earlier branch evidence is cited,
not represented as a fresh result.

Round 2 reran the two player difftest seeds (31,990 and 31,991 compared
ticks, plus 2,500 isolated attack-variant calls per seed), the selector
including ten equip-to-base handoffs and one original lethal state entry per
seed, and the 652-test unit suite.
All passed with `PYTHONDONTWRITEBYTECODE=1`. The ten focused handoffs use
synthetic item definitions, including class-byte probes that do not assert
the existence of a corresponding shipped item.

2026-10-23 audit FIX: `difftest_player_anim_select.py` now asserts the exact
equip class-store, dual-wield override, reset call, active-set store and
selector-read sites on both seeds, including the ammunition guard. Reruns
passed 96/96 base cases, 10/10 equip handoffs and 1/1 lethal entry per seed;
`difftest_player.py` compared 31,990 and 31,991 ticks respectively; the full
unit suite passed 652/652. The spell row above now separates the phase-0
missing-track cast start from the phase-2 flag-clear exit.
