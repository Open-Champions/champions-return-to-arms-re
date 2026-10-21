# `Minion_run`: the placement of a held Soul

US `SLUS_209.73` v2.00. Prose of `tools/ref_minion.py`. The comparison is
`tools/difftest_minion.py`; the synthetic tests are `tools/test_ref_combat5.py`. Written
2026-10-21 (research round 5, item 4). Evidence words as in `CONTRIBUTING.md`: **Executed** means
the original ran in `tools/ee_emu.py` and the model agreed on the calls to everything outside the
model (in order, with arguments) and on every byte stored outside the stack; **Observed** means read
at the address.

`docs/spec/attach-matrix.md` §4 and §7 left this open: the held Soul's simulation position is set
by `Minion_run`, not by the Soul (`Soul_run` makes no move while owned, `soul-run.md` §3), and "the
ordering of the Minion's placement against the soul's tick" was *Unknown*. The placement is executed
here as part of the start of `Minion_run` `0x2862c0` (class `Minion`, table `0x5164a8`, slot 4,
`symbols/monsters.tsv`) up to its state dispatch.

## 1. What the call does before it dispatches on the state (*Executed*)

*Executed*: 3,000 cases per seed (20973 and 7), 0 mismatches; 1,299 and 1,270 of them placed a held
object. The span `0x286364`–`0x2863e0` is executed in full (32 of 32 instructions); the whole body is
89 of 1,116 instructions, because the state dispatch (§5) is not reached.

| # | Address | Step |
|---|---|---|
| 1 | `0x2862f8` | `Creature_processDamage(this, model)` with `model` = `(this + 0x24) → +0xc` (the class definition's model word) |
| 2 | `0x286308` | `a = Creature_run(this, model)`; non-zero ends the call (the branch is *likely*, `0x286310`): nothing below runs |
| 3 | `0x286318` | `Creature_updateActive(this)` |
| 4 | `0x286328` | `Creature_stepAnim(this; 1.0)` (`lui 0x3f80`, `0x286320`) |
| 5 | `0x286340` | `Creature_applyKnockback(this; 0.2)` (`0x3e4ccccc`, `lui`/`ori` at `0x286334`/`0x286338`); the result is kept in `s4` for the states |
| 6 | `0x28635c` | the virtual call at the table word `+0x48` plus `0xb8`: the 16-bit adjustment `h` at `+0xb8` and the function at `+0xbc`, called as `(this + h, 0)` (`0x286348`–`0x286360`) |
| 7 | `0x286364`–`0x2863e0` | **the placement**, §2 |
| 8 | `0x2863e4`–`0x2863ec` | `s16 +0x232` (the state) read as a sign-extended halfword; unsigned below `0x18` goes to the state dispatch, anything else (negative included) to the epilogue `0x287400` |

## 2. The placement (`0x286364`–`0x2863e0`)

`+0x3c8` is a handle head: its word is the handle node, and the node's word `+0xc` is the held
object (the same layout as every handle in `docs/spec/object-system.md`).

1. `lw +0x3c8` is tested; zero skips everything to step 8 above (`0x286368`).
2. The position `+0x10`..`+0x1b` is copied to a stack buffer (`ldl`/`ldr`/`lw`, `0x28638c`–`0x2863a0`).
3. `model_getAttachPoint(scale; model, copy of position, s16 facing, this + 0x114, index 0, out p,
   out d)` (`0x2863a8`). The registers are `f12` = the float at `+0xdc`, `a0` = the model,
   `a1` = the position copy, `a2` = `lh +0x38`, `a3` = `this + 0x114` (the anim state), `t0` = 0
   (`0x286388`), `t1` and `t2` the stack buffers for the point and the direction. Its body is
   `docs/spec/animation.md` §8.5 (executed there): the record's origin through the joint matrix, then
   turned by the facing and scaled, plus the position; the anim state is the pose **after** this
   frame's `Creature_stepAnim` (step 4 above).
4. The point is copied to the held object's position: `held + 0x10`..`+0x1b`, 12 bytes
   (`sdl`/`sdr`/`sw`, `0x2863c4`–`0x2863cc`). The direction `d` is computed and **not used**.
5. `held + 0x38` = the low 16 bits of the Minion's facing (`lhu` at `0x2863d4`, `sh` at `0x2863e0`,
   in the delay slot of the next call).
6. `obj_updateGridCell(held)` (`0x2863dc`): the held object moves to the grid cell its new position is in.

**Fields read**: `+0x24`, `+0x48` (and the table words `+0xb8`, `+0xbc`), `+0x3c8`, the node's
`+0xc`, `+0x10`..`+0x18`, `+0x38`, `+0xdc`, `+0x114` (an address, the anim state's own fields are
`model_getAttachPoint`'s), `+0x232`; the class definition's `+0xc`. **Fields written**: the held
object's `+0x10`..`+0x18` and `+0x38`, nothing of the Minion's. **Seed draws** in this span and in
the call-outs of §1: none of its own (the callees `Creature_processDamage`, `Creature_run`,
`Creature_stepAnim` and the virtual slot have their own, executed elsewhere).

Constants (all *Observed*): the scale and facing are fields; 1.0 `0x3f800000`, 0.2 `0x3e4ccccc`, the
vtable offset `0xb8`, the grid call `0x14f028`, the state limit `0x18` (`sltiu` at `0x2863e8`), the
attach index 0 (`move $8, $zero` at `0x286388`).

## 3. What this settles

- **The held Soul is placed every Minion tick, after the Minion's own move and animation step and
  before its state handler runs.** A Minion state that reads the held Soul's position (a throw or
  a release) therefore sees this frame's attach point, computed from the pose of this frame.
- The placement happens even when the Soul is in a state whose own run does nothing with its
  position (state `0x1d`, `attach-matrix.md` §4): the Soul's position is the attach point and
  nothing else moves it.
- **The ordering against the Soul's own tick** is the run-list order (`object-system.md` §5.5): the
  Soul's `Soul_run` makes no move and in state `0x1d` uses only the matrices, so the position it
  holds when it runs is the previous tick's or this tick's according to which was linked more
  recently; whether `Soul_run` reads its own `+0x10`..`+0x18` in an owned state other than
  `0x1d` is not established here (*Unknown*; `soul-run.md` §3 lists the reads).
- A native port needs: the attach point (the animation research's formula), the position and
  facing copy, and the grid update, once per Minion tick, with no seed draw.

## 4. The model and the test

The original ran with every callee (§1 steps 1–6 and 8) a recording stub answering from a script
shared with the model: `Creature_run` 0, 1 or 2, a point and a direction for
`model_getAttachPoint`. The Minion block, the held object and the node were filled with random
words first. Cases: a held handle or none (70 % held), `Creature_run` non-zero 40 % of the time,
facings and scales of any value, states `0x18`..`0xffff` (the only ones the model accepts; a lower
state raises `NotImplementedError` in the model).

Checks of the comparison itself (200 cases each, model restored after each): the facing copied to
`+0x3a` instead of `+0x38`: FAIL 84 / 200; the position copy's facing read from `+0x3a`: FAIL 84 / 200.

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_minion.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_minion.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_combat5.py

| Seed | Cases | Placed a held object | Mismatches |
|---|---|---|---|
| 20973 | 3,000 | 1,299 | 0 |
| 7 | 3,000 | 1,270 | 0 |

## 5. Not executed

- The state dispatch and every Minion state (`0x2863ec`–`0x287400`; 1,027 of 1,116 instructions of
  the body): a jump table on `s16 +0x232` below `0x18`. What a Minion does in each state is
  *Unknown* here.
- The five callees' own bodies (`Creature_processDamage` `0x110d30`, `Creature_run` `0x112948`,
  `Creature_updateActive` `0x10c0f0`, `Creature_stepAnim` `0x1162b0`, `Creature_applyKnockback`
  `0x115eb8`): executed in earlier rounds for creatures in general (`creature-tick.md`), not under this
  caller. The virtual slot at `+0xb8` of the Minion table is not identified.
- Who sets `+0x3c8` (the pick-up) and clears it (the release): not found in this round.
