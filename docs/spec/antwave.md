# The AntWave: AntQueen state 0x19, AntWave_ctor and the AntWave's own slots

US `SLUS_209.73` v2.00. Prose of `tools/ref_antwave.py`. The comparison is
`tools/difftest_antwave.py`; the synthetic tests are `tools/test_ref_antwave.py`.
Written 2026-10-21.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, and the result. **Observed**: read at the address. **Inferred** and **Unknown** as
usual. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. Why

`docs/spec/antqueen-run.md` executed every state of `AntQueen_run`, state 0x19 included, with
`AntWave_ctor` `0x238654` a recording stub. Nothing of the AntWave object had run anywhere:
not the constructor, not its run `0x238938`, draw `0x2387d0` or destructor `0x238750`
(`docs/spec/full-placement.md` §5 item 6). `docs/monsters.md` §7.5 describes a draw-to-
simulation hazard in it, and `docs/monsters-2.md` says no code requests state 0x19.

## 2. Who can request AntQueen state 0x19

Re-checked by two scans of every instruction of the executable (Observed):

1. **Every slot-27 (set-state) virtual call.** A `jalr` whose target was loaded from table
   offset `0xd8`/`0xdc`, with the value of `a1` found in the delay slot or the instructions
   before. 258 call sites. 250 pass a constant; four of them pass 0x19:
   - `Critter_run` `0x255924` and `Critter_applySpecies` `0x256364`, `0x256594`: on the
     Critter the function works on (the object in s1 / s0);
   - `VampireLord_takeDamage` `0x2b942c`: on the VampireLord itself.

   Eight pass a computed value. Seven are on the function's own object: `Vehicle_updateSteering` `0x20cbbc`,
   `Agony_run` `0x233ef4`, `Amphian_run` `0x234b40`, `FatCyclops_run` `0x258590`,
   `Nightmare_setState` `0x27186c`, `Marr_run` `0x283f94`, `Zek_run` `0x2c277c`. The eighth
   (`UdpReliableChannel_FlushCoalesce` `0x39a478`) is not a creature table at all.
2. **Every halfword store to `+0x232`.** None stores the constant 0x19 (constants seen: 0,
   1, 0x14, 0x17, 0x18). The 112 others store a value read back: each class's set-state
   storing its filtered request, the slot-15 clone functions copying the state of the object
   they copy (`0x11c580`–`0x131858`), and `Creature_default_slot27` `0x3c268c`.

Also: `AntQueen_setState` `0x237918` has no direct caller (no `jal`); its address appears
once in the image, in the AntQueen table (slot 27). It holds no constant 0x19, and
`Creature_filterState` `0x10a9c0` can only turn a request into 1, 5, 0x10, 0x13 or 0x14.
`AntWave_ctor` has one caller, `jal` at `0x2376a8` (AntQueen_run state 0x19).

**Result.** No instruction requests 0x19 for an AntQueen (Observed for the constant and
computed sites above). *Inferred*: state 0x19, and with it every AntWave, is unreachable in
this build. *Unknown*: only a path that copies an AntQueen already in 0x19 (the slot-15
clone of the prediction copy) could carry it, and that needs a queen in 0x19 first.

## 3. How it was run, figures and coverage

`tools/difftest_antqueen_run.py`'s rig and world (the queen built by `AntQueen_ctor`,
`AntQueen_run` real to its end, the creature base real underneath), with these real too:
`AntWave_ctor` inside the queen's state 0x19 (instead of the stub), `AntWave_run`,
`AntWave_draw`, `AntWave_dtor`, and under them `Creature_ctor`, `Creature_run`,
`Creature_moveTo` with `Creature_moveBy` and the touch slots 6, 7 and 11 (base bodies of the
AntWave table), the target's `Creature_takeDamage` (base table), `Creature_dtor` `0x117128`
and `GameObject_dtor` `0x14cf90` (`tools/ref_combat_monsters.py`). Recording stubs answered
by the scripted world: `GameObject_ctor`, `handle_link`, `handle_clear`, `pool_new`,
`pool_free`, `particle_spawn`, the property and path services, `world_*`, the target's slot
2 when it carries the Player table (`Player_takeDamage` `0x1b5330`, executed in
`tools/difftest_combat_ptick.py`), and the rest of `tools/difftest_antqueen_run.py`'s list.

The driver, each tick: puts the queen in state 0x19 with a target and the wave frame
(`+0xf4 = clock + 121`) a quarter of the time, so she spawns waves through `pool_new`
(0x3d8-byte blocks, refused 8% of the time); then every live wave draws (half the ticks)
and runs, until its run deletes it. Half the queen's waves are **left alone** to the end of
their life; on the others the driver drops the target handle (as a target's death would),
moves the clock onto a multiple of 60 and the lifetime near the clock, and destroys some
from outside (`AntWave_dtor`, flags 0–3). Targets are moved onto waves (inside, on and
outside the radius) and switched between the base table, the hooked table and the Player
table. `AntWave_ctor` is also entered directly (dirty or zeroed blocks, lifetimes 0–600 and
−1, any facing, target radius 0–45).

    python3 -u tools/difftest_antwave.py -v                 # seed 20973
    python3 -u tools/difftest_antwave.py -v --seed 7
    python3 -m unittest tools.test_ref_antwave

Four runs of 3,000 ticks per seed (machines A and B, seed and seed + 1).

| | Seed 20973 | Seed 7 |
|---|---|---|
| `AntQueen_run` / `AntQueen_ctor` | 11,966 / 152 | 11,971 / 154 |
| waves the queen spawned (`AntWave_ctor` real inside `AntQueen_run`) | 151 | 155 |
| `AntWave_ctor` entered directly | 53 | 51 |
| `AntWave_run` | 45,753 | 45,454 |
| `AntWave_draw` | 22,876 | 22,818 |
| `AntWave_dtor` entered directly | 36 | 33 |
| All calls compared | 80,836 | 80,481 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |
| target hits (the target's slot 2 from `0x238a18`); through the Player stub | 361; 75 | 376; 78 |
| deletions by the run: target lost / lifetime | 15 / 137 | 21 / 136 |
| waves left alone, runs from constructor to deletion | 63 waves, every one 601 | 63 waves, every one 601 |
| own-generator draws: `AntWave_draw` / `Creature_moveTo` (both on the wave's `+0x44`) | 44,100 / 477 | 44,211 / 442 |
| shared draws made inside `AntWave_run` / `_draw` / `_ctor` / `_dtor` | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

**Multi-frame result (Executed).** A wave the queen builds with lifetime 600 is run 601 times
and deleted by its own run on the 601st (`+0x3cc` = 600 < clock 601): 126 such lives, from
the queen's `pool_new` through to `pool_free`, with 0 mismatches on any of the frames.

| Function | Address | Instructions executed (both seeds) |
|---|---|---|
| `AntWave_ctor` | `0x238654`–`0x23874c` | 63 of 63 |
| `AntWave_dtor` | `0x238750`–`0x2387cc` | 32 of 32 |
| `AntWave_draw` | `0x2387d0`–`0x238934` | 90 of 90 |
| `AntWave_run` | `0x238938`–`0x238a88` | 85 of 85 |
| `AntQueen_run` (context) | `0x236f78` | 593 of 607 (the 14 dead ones of `antqueen-run.md` §2) |

**Checks** (`--quick`, model mutated, then restored): the damage period 60 → 30 gives 20
mismatching run calls; the draw period 3 → 4 gives 894 of 2,150 draw calls mismatching.

## 4. The class

Table `0x50d298` (`tools/vtab.py`). Own slots: 1 `AntWave_dtor` `0x238750`, 4 `AntWave_run`
`0x238938`, 5 `AntWave_draw` `0x2387d0`, 15 `AntWave_clone` `0x11fcd0`. Every other slot is a
Creature base body: 2 `Creature_takeDamage`, 6 and 7, 10, **11 the touch list
`Creature_slot11` `0x11a448` (empty)**, 17, 20, 23, 25, 26, **27 `Creature_default_slot27`
`0x3c2688`** (a bare store of the request), … The AntWave has **no touch handler of its
own**: what it does to its target is in its run (§5.3). Size 0x3d8 (`pool_new` at
`0x237668`). No class definition (`+0x24` = 0 from `Creature_ctor`).

| Field | Width | Meaning | Written by | Evidence |
|---|---|---|---|---|
| `+0x48` | word | table `0x50d298` | ctor, dtor | Executed |
| `+0xb0` | float | turn rate 0.6 | ctor | Executed |
| `+0xb8` | float | speed 100 | ctor | Executed |
| `+0x1c` | float | radius = target radius + 10 (5 first, overwritten) | ctor | Executed |
| `+0x300` | word | creature clock, 0 from `Creature_ctor`, +1 per `Creature_run` | ctor, run | Executed |
| `+0x3c8` | word | the clock at birth (always 0); never read by the class | ctor | Executed |
| `+0x3cc` | word | the clock at which it dies (`clock + lifetime`), signed | ctor | Executed |
| `+0x3d0` | handle | the target | ctor (`handle_link`), dtor (`handle_clear`) | Executed |
| `+0xc` | word | object flags \|= 1 | ctor | Executed |
| `+0x44` | word | own generator (seeded by `GameObject_ctor`) | draw, `Creature_moveTo` | Executed |

## 5. The bodies

### 5.1 In AntQueen state 0x19 (`antqueen-run.md` §3, now with the constructor real)

Each tick in 0x19: `fadeBankTracks`; with a target and `clock == +0xf4 − 120` (32-bit
equality): `pool_new(0x3d8)` and, with a block, `AntWave_ctor(block, target object,
(x + cos16 f · (r + 10), y + sin16 f · (r + 10), z), f, 600)`; then `+0xf4` expired and
fewer than four tracks → state 3. *Inferred* from `AntQueen_setState`'s 0x19 arm
(`+0xf4 = clock + 120 + d % 60`, own draw, `docs/spec/combat-ctors.md`): one request makes
one wave, `d % 60` ticks later, and none when `d % 60` is 0 (the clock has passed the frame
before the run tests it).

### 5.2 AntWave_ctor `0x238654` (block, target object, position, facing, lifetime)

1. `Creature_ctor(10000.0, block, no type name, copy of the position, s16 facing, no class
   definition, no properties)` (`0x2386ac`; 10000 = `0x461c4000` at `0x238658`/`0x23865c`).
   That is `GameObject_ctor` (one **shared** draw, which seeds `+0x44` — the executed contract
   of `docs/spec/gut-chunk.md`; a stub here) and the property reads with no list.
2. `+0xb0 = 0.6` (`0x3f199999`, `0x2386bc`/`0x2386c0`), `+0xb8 = 100` (`0x42c80000`,
   `0x2386b4`), `+0x1c = 5` (`0x40a00000`, `0x2386cc`).
3. `+0x48 = 0x50d298` (`0x2386c8`/`0x2386dc`), `+0x3c8 = clock`, `+0x3cc = clock +
   lifetime` (32-bit add, `0x23870c`), `+0x1c = target +0x1c + 10.0` (`0x41200000`,
   `0x2386f0`), `+0x3d0 = 0`, `+0xc |= 1`.
4. `handle_link(+0x3d0, target, target)` (`0x238728`), `obj_runEveryFrame(block)`
   (`0x238730`).

Reads the target's `+0x1c` and the wave's `+0x300`, `+0xc`. No draw of its own.

### 5.3 AntWave_run `0x238938` (slot 4)

1. `Creature_run(wave, no model)` (`0x238948`; result not tested): the clock +1, the base
   timers.
2. No target handle `+0x3d0`: slot 1 (the destructor) with 3 (`0x238a5c`–`0x238a74`), and
   return.
3. `Creature_moveTo(wave, copy of the target's position)` (`0x238980`): walk at speed 100,
   turn rate 0.6. `Creature_moveTo` counts as arrived when the squared distance is below the
   wave's radius squared, so the wave stops on its target.
4. When the signed clock `% 60` is 0 (`div`/`mfhi`, 60 at `0x23898c`): `d` = target position
   − wave position (target re-read through the handle), and when `(dx² + dy²) + dz²` is
   **strictly** below `+0x1c²` (`c.olt.s`, `0x2389ec`): the **target's** slot 2 (take
   damage) with (`this` wave, flags `0x100`; amount 1.0) (`0x2389f8`–`0x238a18`; 0x100 at
   `0x238a08`, 1.0 at `0x238a00`). The meaning of damage flag 0x100 is not established.
5. When the signed `+0x3cc` is below the signed clock: slot 1 with 3 (`0x238a20`–`0x238a4c`).

So a wave walks to its target, and while within its radius takes **1 hit point every 60 of
its own ticks**, at most 10 times in a life of 600 (clocks 60, 120, …, 600), then deletes
itself on its 601st run. Draws: none of its own. Under it, `Creature_moveTo` draws the
wave's own generator when a side-step starts (477 / 442 times in the runs above) and its
last-resort teleport `world_findFreeSpot` (a stub here, 7 / 3 calls) draws the shared seed
(`tools/ref_creature.py`); `Creature_run`'s burn tick draws the shared seed. A Player
target's `Player_takeDamage` draws the shared seed when it blocks in state 8
(its note in `symbols/`; executed in `tools/difftest_combat_ptick.py`). None of those shared draws occurred inside
the bodies run here (the shared seed was compared on every call).

### 5.4 AntWave_draw `0x2387d0` (slot 5)

When the signed clock `% 3` is 0 (3 at `0x2387d4`): a unit-ball vector from **own** draws of
`+0x44` (`GameObject_rand` at `0x238808`, `0x238830`, `0x238850`; each `2·(d·2⁻¹⁶) − 1`,
2⁻¹⁶ `0x37800000` at `0x238800`, again while `(x² + y²) + z² > 1`, 1.0 at `0x23881c`); the
point `position + v · 10` (10 at `0x2388b0`); `particle_spawn(0x4febe0, point, (0, 0, 0);
0.0)` (`0x2388c0`/`0x2388c8`, `0x238918`). No shared or cosmetic seed draw.

**The hazard of `docs/monsters.md` §7.5, Executed in part.** The draw and the run's
`Creature_moveTo` advance the same word `+0x44` (44,100 and 477 draws on the same waves in
the seed-20973 runs). A machine that calls the draw a different number of times moves the
wave's side-step directions apart. Whether the draw runs once per simulation tick on every
machine is a property of the frame loop, not of these bodies: *Unknown* here. The hazard is
moot while state 0x19 has no requester (§2).

### 5.5 AntWave_dtor `0x238750` (slot 1: object, flags)

`+0x48 = 0x50d298`; when `+0x3d0` is non-zero, `handle_clear(+0x3d0)` and then
`handle_clear(+0x3d0)` again (the member's own destructor, then the explicit clear); when it
is zero, only once (`0x238774`–`0x238788`). `Creature_dtor(wave, 0)` (`0x238794`), and with
flag bit 0 a tail jump to `pool_free(wave)` (`0x2387b4`). No draw.

## 6. Constants (Observed)

| Value | Use | Address |
|---|---|---|
| 0x3d8, 600 | block size, lifetime the queen passes | `0x237668`, `0x2376a4` |
| `0x50d298` | AntWave table | `0x2386c8`/`0x2386dc`, `0x238754`/`0x23876c` |
| 10000.0 `0x461c4000` | `Creature_ctor` hit points | `0x238658`/`0x23865c` |
| 0.6 `0x3f199999` | turn rate `+0xb0` | `0x2386bc`/`0x2386c0` |
| 100.0 `0x42c80000` | speed `+0xb8` | `0x2386b4` |
| 5.0 `0x40a00000` | first radius | `0x2386cc` |
| 10.0 `0x41200000` | radius past the target's; draw spread | `0x2386f0`; `0x2388b0` |
| 60 | damage period | `0x23898c` |
| 0x100, 1.0 | damage flags and amount | `0x238a08`, `0x238a00` |
| 3 | delete flags of slot 1; draw period | `0x238a38`/`0x238a60`; `0x2387d4` |
| `0x4febe0` | particle definition (`Ant_initParticleDefs`) | `0x2388c0`/`0x2388c8` |
| 2⁻¹⁶ `0x37800000`, 1.0 | unit-ball draws | `0x238800`, `0x23881c` |

## 7. Corrections

- `docs/monsters-2.md` (AntWave constructor): `+0x3c8` is the clock at birth, and the clock
  is 0 then (`Creature_ctor` zeroes it), so `+0x3c8` = 0 and `+0x3cc` = the lifetime itself.
  The radius is written twice (5, then target + 10).
- `docs/monsters.md` §7.5: "every 60 frames damages the target when within its radius" is
  the target's slot 2 with amount 1.0 and flags 0x100, distance strictly below the radius,
  on the wave's own clock. The destructor clears the target handle twice.
- `docs/spec/antqueen-run.md` §7 and `docs/spec/full-placement.md` §5 item 6:
  `AntWave_ctor` and the object's run, draw and destructor are executed now.

## 8. Still not executed

- `AntWave_clone` `0x11fcd0` (slot 15, the copy constructor of the prediction copy).
- `GameObject_ctor` inside the constructor (a stub here; executed in
  `tools/difftest_phprop.py`), `world_findFreeSpot`, `particle_spawn`, `pool_new`,
  `pool_free`, `handle_link`, `handle_clear`: services.
- What calls the draw slot and how often per simulation tick on each machine (§5.4).
- A requester of state 0x19: none found (§2).
