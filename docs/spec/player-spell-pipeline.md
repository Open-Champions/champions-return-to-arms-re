# Player spell pipeline — SLUS-20973 v2.00

Research synthesis, 2026-10-23, branch `t3/research-spells` from main `034d0c0`.
This is a port contract for player-controlled spells. The original instructions are
read at the addresses below; the cited reference models execute individual functions
against `tools/ee_emu.py` on constructed state. A function-level comparison does not
establish a playable native cast or an unbroken whole-game damage path.

**Evidence labels.** Observed = read in the original instructions at the address
shown. Executed = original and reference called in `ee_emu.py` with compared calls,
stores, seed and result. Inferred = composition of separate observations. Unknown =
neither instruction tracing nor the bounded comparisons settled it.

## 1. Selection and request

| Step | Evidence | Address and state |
|---|---|---|
| Raw D-pad opens a local selector after menu, dialog, camera, pause, memory-card and task gates. Direction + ability A/B sends quick-slot message 0. Direction + Use sends quick-cast warning message 13. A direction also masks A/B/Use in local input for three frames. | Observed; Executed in `t3/research-hud-inputs` `44c6720`, `difftest_hud_inputs.py` and predecessor `difftest_hud_quickslots.py` | `hud_spellSelect` 0x1dd270; `net_maskLocalButtons` 0x13e540; raw pads 0x4028d0 + 0x58·slot; button masks 0x41b990/0x41b9a0/0x41b9c0 |
| Message 0 changes quick-slot index A or B, swapping a duplicate assignment. Message 13 queues a forced record only in neutral state; kind 1 gets a warning instead. | Observed; Executed in pinned HUD branch | `hud_onQuickSlot` 0x1de28c; message 13 handler 0x1de340; record `R+0x4a84/85`; forced pointer `P+0x488` |
| Ability A/B pressed in the lockstep pad chooses the matching quick-slot index and a 0x68-byte record. The last chosen button is retained. | Observed; Executed in `ref_player.py`/`difftest_player.py` | `Player_run` 0x1a5030, input 0x1a5768–0x1a5b10; `R+0x4a60`, `R+0x4440 + 0x68·index`; pad 0x41bfd8 + 0x58·slot; ability masks 0x41b990/0x41b9a0 |
| The record's id selects `g_skillTable[id]`; kind is copied from skill+8 when assigned. Kind 7 casts immediately, kind 8 waits for a ranged release, ordinary kinds enter cast state 5. | Observed; Executed for the player state machine | `R+0x4440 + 0x68·index`, id +0x20, kind +0x25; `g_skillTable` 0x41b170; `hud_onAssignSpell` 0x1de61c; `Player_run` 0x1a7034–0x1a709c, 0x1a837c, 0x1a9174 |

`R` is `g_players + 0x4c30·slot` (base 0x4d8af0), `P` the player object.
The selector is a local HUD task; its message must enter the simulation through
the existing message/input path. `g_spellSelectorHeld` 0x41b818 additionally gates
`Player_interact` at 0x1a5c08–0x1a5c1c. It is not a cast cooldown (Observed).

## 2. Admission, timing and mana

| Rule | Evidence | Address |
|---|---|---|
| `canUse` is skill virtual slot 1. The requested rank is Player slot 39; mana cost is Skill slot 5. A request with insufficient `R+0xc0` is refused. Kind 1 needs half its listed cost to start. | Observed; Executed through `ref_player.py`/`difftest_player.py`; per-skill costs in `ref_skills_[abc].py` | `Player_run` 0x1a5c6c–0x1a5e28, 0x1a6f84–0x1a6f90; skill table +0x60; Player slot 39 0x3c3b40 |
| Recast counter decrements once per normal player tick; positive counter refuses the cast helper. The skill's recast delay is stored after dispatch, including when cast returns no `Spell`. | Observed; Executed in the player model | `P+0x4ae`; tick 0x1a5030–0x1a5624; `Player_castSkill` 0x1a42b8; skill+0x0c |
| In state 5, cast fires when animation blend value reaches 1.0 offline or 0.5 in a network game. Kind 7 bypasses animation; kind 8 fires at the ranged release. | Observed; Executed in player model | state 5 0x1ab4f8–0x1ab7dc, blend at animation track +8; instant 0x1a7048; ranged 0x1a837c/0x1a9174 |
| The helper checks copy eligibility (skill flag bit 0), calls `canUse`, finds the hand midpoint and first accepted enemy within an arc, then invokes Skill slot 2 `(rank,P,pos,facing)`. A returned `Spell` attaches to `P+0x364`; kind 1 also gets held handle `P+0x588`. A prediction copy destroys its returned spell. | Observed; Executed in player model | `Player_castSkill` 0x1a42b8; `creature_addSpell` 0x11a838; skill+4, +8; `P+0x588` |
| The helper pays cost once and starts recast even when Skill slot 2 returns zero. Kind 1 pays `cost × 1/60` here and again each held phase-2 tick. Held spell is stopped on release, leaving state 5 or exhausted mana. | Observed; Executed in player model | 0x1a42b8; 0x1ab4f8–0x1ab7dc; `Player_updateCast` 0x1a3f70; `R+0xc0`, `P+0x47b` |
| Mana regeneration is real-player-only and capped at `R+0xc4`. Base gain starts at maximum mana × float bits `0x38d1b717`, modified by passive 0x200, `P+0x475`, equipped modifier 0xc, Blessed and Regeneration. Class 0 has no natural base gain. A pending mana potion adds `R+0xbc` per tick while `R+0xc8` remains. | Observed; Executed in player model | `Player_regenMana` 0x1b3900; `R+0xc0/+0xc4/+0xc8/+0xbc`; potion entry `Player_usePotion` 0x1b9cb8 |

The cast helper does **not** recheck available mana after the animation delay;
the request gate checked it earlier. The port must preserve that ordering rather
than moving the debit to button press (Observed: `Player_run`/`Player_castSkill`).
The exact visual time in seconds depends on the clip and animation advance, so a
single universal casting duration is **Unknown**.

## 3. Concrete projectile and damage path: Disease Bolt (skill id 4)

This is an example of an active caster skill that returns **no attached `Spell`**.
The distinction matters: returning zero does not mean no projectile was created.

| Stage | Evidence | Address |
|---|---|---|
| `SkillDiseaseBolt` is kind 0, recast 30 frames. Its cost is the skill's floating-point level formula (base 9); call slot 5 rather than assuming an integer `9 + 2·(rank−1)`. | Observed; Executed for level 0–40 and additional probes in `difftest_skills_a.py` | skill table 0x518468; cast 0x2cb1c0; cost 0x2cb33c |
| Cast allocates 0x7c bytes, constructs `DiseaseBolt`, applies a caster flash, returns zero. Constructor stores facing, owner handles, skill, rank, 350-unit/second horizontal velocity, expiry at frame+300, homing arm at frame+10, and selects the first accepted enemy in a forward arc. | Observed; Executed in `ref_skills_a.py`/`difftest_skills_a.py` | cast 0x2cb1c0; `DiseaseBolt_ctor` 0x2c9eb0; fields +0x38, +0x4c/+0x54, +0x5c/+0x60, +0x64..+0x74; object table 0x5183d8 |
| Projectile run homes after its arm frame, calls `obj_moveAndCollide`, and expires by frame or collision. The touch handler ignores friendly and blocking creatures, asks skill stat 0 for damage, makes one object RNG draw for the upper end, and passes base range plus descriptor type 0x26 to `damage_apply`. | Observed; Executed for call arguments, stores and seeds in the skill model | run 0x2ca1a8; hit 0x2caec8; `damage_apply` 0x1e8230 |
| `damage_apply` rolls and mitigates damage, handles descriptor effects, then calls the victim's damage handler. A type-0x26 entry may create a disease effect; the exact resulting HP delta depends on defender state, resistance and the separate damage pipeline. | Observed; separately Executed in `ref_combat.py`/`difftest_combat.py`; composed end-to-end hit **Unknown** | 0x1e8230; `docs/spec/combat.md` §2; `docs/spec/skills-01-34.md` §4 |

World queries, pool allocation, collision, and `damage_apply` are scripted stubs in
the skill difftest. The model verifies the projectile's outgoing damage call, not a
victim HP change. This is the boundary for a native gameplay acceptance test.

## 4. Reference and verification map

| Boundary | Reference model | Original-code difftest |
|---|---|---|
| Selector and quick-slot message | `tools/ref_hud_inputs.py`, `tools/ref_hud_quickslots.py` at `t3/research-hud-inputs` `44c6720` | `tools/difftest_hud_inputs.py`, `tools/difftest_hud_quickslots.py` on that pinned branch |
| Player input, admission, timing, cast helper, mana regeneration | `tools/ref_player.py` | `tools/difftest_player.py` |
| Disease Bolt cast, object run and hit | `tools/ref_skills_a.py` | `tools/difftest_skills_a.py -k s04` |
| Generic damage application | `tools/ref_combat.py` | `tools/difftest_combat.py` |

These tests compare constructed states in `ee_emu.py`, seeded with 20973 and 7.
They do not feed a raw D-pad event all the way to a live enemy death. The pinned
HUD branch is deliberately cited instead of copied into this branch; it is not
present in main `034d0c0`.

### Rerun on 2026-10-23

All commands below set `PYTHONDONTWRITEBYTECODE=1` and passed the private US v2.00
executable by absolute path. The actual path and counts-only logs are under this
worktree's ignored `local/spells-evidence/`; no game bytes or disassembly are tracked.
`SLUS_209.73` in the table abbreviates
`/Users/syndicatemike/champions-re/SLUS_209.73`.

| Command (repeat for `--seed 20973` and `--seed 7`) | Seed 20973 | Seed 7 |
|---|---:|---:|
| `python3 tools/difftest_player.py SLUS_209.73 --seed N` | 31,990 ticks; state 5: 351/0 mismatches | 31,991 ticks; state 5: 386/0 mismatches |
| `python3 tools/difftest_skills_a.py SLUS_209.73 --seed N -k s04` | 1,100 calls, 0 mismatches; skill-4 blocks 82/84 | 896 calls, 0 mismatches; skill-4 blocks 82/84 |
| `python3 tools/difftest_combat.py SLUS_209.73 --seed N -k damage --quick` | 39 properties, 0 failed | 39 properties, 0 failed |
| In pinned HUD worktree `44c6720`: `python3 tools/difftest_hud_quickslots.py SLUS_209.73 --seed N` | 5 properties, 0 failed; selector 1,680 cases | 5 properties, 0 failed; selector 1,680 cases |
| In pinned HUD worktree: `python3 tools/difftest_hud_inputs.py SLUS_209.73 --seed N` | 4 properties / 560 cases, pass | 4 properties / 560 cases, pass |

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p
'test_*.py'` in this worktree: 652 tests, OK. The player runner records a few
constructed ticks where both the original and model read unmapped memory; those
agreements are in its fault property, not live cast successes. The damage run is
`--quick` and tests `damage_apply` separately from Disease Bolt's hit callback.

## 5. Native port order and gates

1. Import the reviewed HUD input/message contract at `44c6720`: D-pad gating,
   quick-slot swap, forced queue and three-frame input mask. Verify selector and
   A/B labels in a rendered local-player session.
2. Represent the 0x68-byte ability record, id/rank, skill kind and quick-slot
   references. Preserve normal and forced requests through the simulation tick.
3. Port request admission: `canUse`, rank-specific mana cost and refusal; then
   recast decrement and state-5 animation threshold. Test offline and network
   thresholds, kind 7 immediate and kind 8 ranged release.
4. Port the cast helper with the original hand position, target scan, copy guard,
   slot-2 dispatch, attachment and held handle rules. Account for cast functions
   returning zero after constructing an independent projectile.
5. Port mana debit, held-per-frame charge, release and regeneration/potion
   ordering. Check exact float bits and cap behavior, including class 0.
6. Port one projectile completely: Disease Bolt construction, world registration,
   frame/position update, homing, touch filtering and deletion. Keep its own and
   shared RNG streams separate.
7. Connect projectile touch to the reviewed `damage_apply` and victim handler.
   Verify actual HP change, effects and death in a real hostile level; the
   isolated skill difftest does not establish this integration.
8. Add other skills by kind and object family using `ref_skills_[abc].py`, with
   their individual refusal and run tests. Verify native visuals and sound only
   after the simulation contract has an actual cast/impact path.

**Unknown / remaining gate:** whole-session selection-to-hit parity, a live
campaign caster against a real target, exact animation clip duration, and console
floating-point behavior outside the interpreter's model. No addresses or values
for these are inferred as native constants.
