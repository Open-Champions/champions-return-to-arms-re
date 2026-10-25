# Creature and player animation dispatch: which clip, when, and what its events do

2026-10-17, round 3 of the animation research; SLUS-20973 US v2.00; branch
`t3/research-anim` on top of round 2 (`2502e2b`). This extends
[rendered-creature-animation](rendered-creature-animation.md) section 2, whose
coverage boundary said only SmallSpider's dispatch was contracted. Round 2's APIs
(`ref_creature_animation`, its difftest and vectors) are unchanged.

Labels as in CONTRIBUTING: **Observed** (read at the address), **Inferred**, **Unknown**,
and **Executed**: one original function run in `tools/ee_emu.py` on state a script
built. Every per-class number below is Executed by `tools/scan_anim_dispatch.py`; the
committed table `tools/ref_creature_dispatch_data.py` is its output and
`tools/difftest_creature_dispatch.py` re-executes it against the user's own executable.
Nothing here was run on a console, PCSX2, the Play! rig or the recompiled build, and no
rendered Godot creature was checked.

## 1. What a native implementation needs from this document

| Need | Where |
|---|---|
| The clip a creature starts when its AI state changes, with blend, flags and choice rule | section 3 (common base), section 5 (groups), appendix A (every class) |
| When an attack's hit lands, a projectile leaves, a footstep or effect fires | section 4 (event model) and the "Events" / "Event consumers" lines of appendix A |
| When an action, hit reaction or death ends and what state follows | section 3.3 and the "Clip-status transitions" lines of appendix A |
| Player clip selection and events | section 6 |
| What is still not established | section 7 |

Read the result as a contract on **calls into the animation state**, not on clip
names: the setState body names a class-definition entry `k` (pointer at
`def + 8k + 4`, `def = *(creature+0x24)`, round 2 section 1). The `.anm` file names in the
appendix are the identifiers stored at `def + 8k` of the variant-0 definition, given so a
reader can recognise the role; native code must resolve the entry, not the name, because
variants of one class swap definitions (appendix A lists every definition seen).

## 2. How the tables were made (Executed; limits)

`tools/scan_anim_dispatch.py local/SLUS_209.73` (hash-checked) runs three single-function
scans per class of the `docs/monsters.md` 3.1 catalogue (73 classes). Every callee is
auto-stubbed and recorded by `ee_emu` (`follow` mode); a stubbed callee returns 0, or in a
second pass a pointer to a zeroed dummy object. The creature is a zeroed 0x2000-byte block
with a synthetic class definition whose entry k points at a distinct fake clip, and a fake
virtual table whose slot n is a distinct never-executed address, so every animation call
reports *which entry* it was given and every virtual call *which slot*.

1. **setState** (vtable slot 27, `+0x48 → +27*8+4`): each request 0…0x2f.
   `Creature_filterState` 0x10a9c0 is stubbed to accept the request unchanged (its own
   contract is `ref_creature.filter_state`, creature-tick 12.3, and applies **before**
   everything here). `GameObject_rand` 0x1509d0 returns 0…11 and then 25, 50, 75, 99,
   127, 255, 0x7fff, 0xffff; the clip-choosing residue period is the smallest period
   consistent with all of them. Every creature word and every `.sdata/.sbss/.bss`
   global the case read is then set, **one at a time**, to 13 probe values (small
   integers, the pending-damage bits 0x40000…0x380000, floats 1, 100, −1, all ones).
   An outcome is the ordered list of animation and virtual calls plus the u16 stored at
   `+0x232`. Each probe sets one field. Two fields set together are a later executed
   pass (section 7); values outside the probes are still not explored.
2. **constructor** (each listed constructor, variant argument 0, 1, 2 in every later
   register): `creature_setDefEntryParams` 0x118378 calls (entry, four raw32 seconds,
   four masks), animation calls, direct calls of the class's own setState, and the class
   definition handed to `Creature_ctor` 0x109d68 (`t0`).
3. **run** (vtable slot 4) for every case label of the catalogue: `Creature_updateActive`
   returns 1, `Creature_run` 0, `Creature_stepAnim` 0x1162b0 returns one mask at a time
   (0x01…0x80). A call, or a store to the creature, that appears after the step only
   with mask m is a **consumer** of m; a callee that receives the event word under every
   mask (for example `Creature_deadUpdate`) is listed as "event word". The track-flag
   union `+0x11a` is 0 or 0xffff to find transitions taken when the marker/status bits
   clear or set. Consumers behind other unexplored branches (a target in range, a
   timer) are not seen; the hand-read class sections of `docs/monsters-2.md` remain the
   authority for those conditions.

## 3. The common dispatch base (all ordinary creatures)

### 3.1 Base states

**Executed** for the classes of section 5 marked "base"; the English role names are
**Inferred** from the flags (3.2) and from `docs/monsters.md` 1.4.

| State | Role | Typical call (most classes) | Notes |
|---|---|---|---|
| 0 | idle (passive) | `anim_start(0.1 s, idle, LOOP\|PURGE)` | many classes also set a wander timer from one own draw |
| 1 | walk / wander | `anim_start(0.1 s, walk, LOOP\|PURGE\|ROOT)` then `anim_syncToSimFrame` | path cleared and wander point chosen first |
| 3 | chase | as 1, often the run clip | |
| 5 | idle between attacks | `anim_start(0.1 s, idle-aggressive, LOOP\|PURGE)` (+ sync in some) | |
| 6…0xf | class attacks / casts | `anim_startBlendInOut(0.1 s, 0.1 s, attack, ACT[\|ROOT][\|YAW])` | one entry per state, or one of several by own draw |
| 0x10 | back off while the attack cooldown runs | as 1 with the run or back-up clip | |
| 0x12 | hit reaction | `anim_startBlendInOut(0.1 s, 0.1 s, hit, HIT)` | clip by own draw, or by the pending-damage bits `+0x2dc` |
| 0x13 | stunned | the idle clip again, often 0.3 s | |
| 0x14 | death | `anim_start(0.1–0.3 s, death, PURGE\|END[\|ROOT])`, then virtual slot 28 | one of 2–4 clips by own draw; `Creature_dropLoot` before |

`anim_syncToSimFrame` 0x1709f8 after a locomotion start sets every track's time to
`g_simFrame mod length` (animation section 4), so walk cycles are phase-locked to the
shared frame counter — identical on every machine, and identical across creatures of one
class. Idle starts are not synced except where the table says so.

### 3.2 What the flags mean for dispatch

Track flags are those of [animation](animation.md) 2.1. In dispatch they encode the role:

| Bits | Use in dispatch |
|---|---|
| LOOP 0x1 | idle and locomotion |
| PURGE 0x2 | the new clip deletes everything below it once it reaches full weight — a hard switch after the blend-in |
| END 0x4 | death and other one-shots that must hold their last pose: time is held at the length and status 0x80 (0x400 on the top track) joins `+0x11a` |
| ACT 0x8 | not tested by `anim_advance`; it joins the flag union `+0x11a` while the attack track exists. Run functions leave an attack state when `+0x11a & 8` is clear (**Executed**: "Clip-status transitions") — i.e. when the blend-in/out track has expired at its end |
| HIT 0x10 | the same for hit reactions: state 0x12 leaves (usually to 3) when `+0x11a & 0x10` is clear |
| ROOT 0x800 / YAW 0x4000 | root translation (and for a few side attacks heading) is extracted and moves the creature through `Creature_stepAnim` → `Creature_moveBy` (round 2 section 6) |

**Inferred** marker rule: `anim_startBlendInOut` gives the track `life = length × r`
falling by r per tick, so it removes itself at its end; its ACT/HIT bit therefore leaves
the union on the first advance after the clip ends. A native port must keep the marker
bits in the track flags and the union, not just a "playing" boolean.

### 3.3 Blend timings

`rate(s) = 1/(s × 60)` per tick (1.0 below 1/60 s; animation 4). Typical patterns:
0x3dcccccc = 0.1 s (6 ticks), 0x3e4ccccc = 0.2 s, 0x3e999999 = 0.3 s (18 ticks),
0x3ecccccc = 0.4 s. `anim_start` forces 0 in cell 0 (first track of an empty state),
so a creature's first clip is at full weight after one step. Blend-in/out tracks fade in
over the first value and out over the second, measured back from the clip end.

## 4. Animation events: from constructor to gameplay

### 4.1 Installation (Executed per class; byte order Observed by round 2)

Each constructor calls `creature_setDefEntryParams(def, k, four times, four masks)`
for the clips whose events matter. The four slots live **in the shared clip**
(`clip+0x14+8i` seconds raw32, `clip+0x18+8i` mask byte): every creature of the class,
and every class sharing the `.anm`, sees the last values written. Appendix A gives every
table; `ref_creature_dispatch.install_events` installs one on synthetic clips.

### 4.2 When an event fires

**Executed** in `ref_anim` (animation section 5): during `anim_advance`, for every track
visited top-down, slot i fires when `time/60 ≤ seconds_i < time/60 + step/60` with the
**old** time and `step = speed × 0.99999994`. Masks of all visited tracks are ORed
(sign-extended byte) — a fading-out previous attack still reports its events, and tracks
below a PURGE track at full weight are not visited. For a clip started at time 0 and
stepped at speed 1, an event at s seconds fires on tick `n` with
`(n−1)·step ≤ 60·s < n·step`; Agony's attack-1 hit at 0x3f199999 (0.6 s) fires on tick 37
(test `test_attack_event_lands_on_its_tick_and_marks_the_union`). Speed changes (slow,
Drowsy, kind-3) move the tick through `step`.

### 4.3 Who consumes them (Executed; conventions Inferred)

`Creature_stepAnim` returns the word; the run function's state switch consumes it on
the **same** tick, after knockback and slot 23. Conventions across the classes:

| Mask | Typical use |
|---|---|
| 0x1 | the strike: `Creature_hitTargetInArc` 0x119938 / `Creature_hitAllEnemiesInArc` 0x119b58 / `Creature_hitTargetAtReach` 0x1196e8; for casters and archers the release (projectile constructor or skill slot 2 at `model_getAttachPoint`) |
| 0x2, 0x4 | further strikes of a combo clip, or a chained transition (Badger's charge: mask 2 → setState 6) |
| 0x4, 0x8 on walk/run clips | footsteps in the run *tail* (all states): `fx_spawn`, dust, sometimes an own draw (Cyclops) |
| 0x80 (0x84) on death clips | passed in the event word to `Creature_deadUpdate` 0x1108a0 (blood / sink timing); Badger additionally sets object flag 1 on bit 4 |

Damage itself is the combat contract (`docs/spec/combat.md`, `ref_combat`): the event only
decides the tick. Projectile and effect constructors named in the consumers are the
effects agents' entry points. Sound cues are **not** event masks: they are the `.anm`
sound tables played by `anim_advance` for the top track (animation section 6) and are
presentation-only.

### 4.4 Findings of the consumer scan (Executed)

- Across the 73 run functions: mask 0x1 reaches a hit test in 85 states
  (`Creature_hitAllEnemiesInArc` 39, `Creature_hitTargetInArc` 36,
  `Creature_hitTargetOrPlayerInArc` 10), often with holder slot 17 (the hand's damage
  descriptor) first; masks 0x4/0x8 reach `model_getAttachPoint` + `fx_spawn` or
  `Cyclops_spawnDust` (footsteps) in about 35 states; the event word goes to
  `Creature_deadUpdate` in 30 death states. Counts are of (class, state) rows in
  `CONSUMERS`.
- **A consumer with no installer:** SpiderQueen's death state shakes the camera on mask
  0x8 (`camera_shake`), but no SpiderQueen constructor puts 0x8 on any clip (its tables
  use 0x1, 0x2, 0x4, 0x80). Unless another writer sets that slot on the shared clip, the
  shake never happens. Kept as `ref_creature_dispatch.UNINSTALLED_CONSUMERS`; settle by a
  whole-file search for other `creature_setDefEntryParams` / clip-event writers.
- **Event-driven own draws (shared state):** WarWraith's death state draws its own
  generator on any nonzero event word; Badger, Cyclops (footstep dust), Bubo and others
  draw on specific bits. These draws are shared simulation state: the tick on which an
  event fires (4.2) decides when the object's generator advances, so event timing must be
  exact for a native port to stay in step with the original or a peer.
- Event-driven stores: e.g. Badger sets object flag 1 on its death clip's bit 4,
  Nightmare/RedDragon/VampireLord set class words `+0x3d0`/`+0x3d4` on bit 1 (charge and
  bite windows; see their `docs/monsters-2.md` sections for the readers).
- A call shown as `000000` is a stubbed object's null function pointer (an artefact of
  the dummy object), not a game call.

## 5. Groups

Classes are grouped by `ref_creature_dispatch.group_of`: the roles of states 0, 1 and
0x14 decide the group, `base_deviations` lists the base states (3.1) whose role differs,
and every class's own states follow. Roles come from the flags (`role()`: idle = LOOP,
locomotion = LOOP|ROOT, action = ACT, hit = HIT, death = END then slot 28, oneshot =
anything else); a trailing `?` marks a role seen only under a recorded condition. "hit" and
"death choice" name what picks the clip; "consumers" lists the gameplay calls found behind
event bits (hit tests, projectile/effect constructors, attach points, camera). **Executed**
for the tables; the grouping rule is an authored summary (**Inferred**), and the exact
rows are appendix A, [creature-animation-dispatch-classes](creature-animation-dispatch-classes.md).

What a group shares, and therefore what one native implementation can cover:

- **5.1 root-motion base** and **5.2 steered base**: section 3 as written. Only the entries,
  blend times, choice rules and the class's own states (6 and up, 0x11, 0x17…) differ;
  implement one table-driven setState plus per-class rows. 5.2 differs in that its walk,
  chase and back-off loops carry no ROOT bit, so `Creature_stepAnim` returns no
  displacement and the class's movement helpers (`Creature_moveToTarget`/`moveToDest`)
  move it — do not add root motion to these.
- **5.3 own state machines**: Critter (ambient animals), Soul, NPC and the talking
  creatures (Natasla, Mermaid, GnomeNavigator; roles also come from the script role
  resolver of round 2), the Skeleton family (state 0x14 starts no clip: both hands are
  dropped through the holder and the body shatters into parts, `docs/monsters-2.md`),
  Gnaw (its death clip is LOOP|PURGE|ROOT, not END), AntQueen (an END|HIT death clip
  with an ACT layer above it). Implement from appendix A plus their
  `docs/monsters-2.md` sections; `ref_monsters_1` already executes SmallSpider and Gnaw,
  `ref_arena_monsters` Skelight.
- **5.4 no dispatch**: the class keeps the base slot 27 or starts nothing there (AntWave,
  CdEyeball, CreatureContainer, FireFly, Generator, Teleporter). Their animation, if any,
  is started by run or draw code (FireFly and AntWave: `docs/monsters-2.md`).

### 5.1 Common base, root-motion locomotion (47 classes)

| class | base states that differ | own states (role) | attack flags | hit 0x12 choice | death 0x14 choice | consumers (run) |
|---|---|---|---|---|---|---|
| Agony | — | 0x6 action, 0x7 action, 0x8 action, 0x11 idle, 0x17 locomotion | ACT|ROOT | +0x2dc | rand % 2 | Creature_hitTargetInArc |
| Amphian | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0x17 idle | ACT, ACT|ROOT | rand % 2 | rand % 2 | Creature_hitTargetInArc, model_getAttachPoint |
| Arenabeast | 0x12 none | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action, 0xf action, 0x17 hit, 0x18 hit | ACT, ACT|ROOT | fixed | fixed | Creature_hitTargetAtReach, Creature_hitTargetOrPlayerInArc |
| Badger | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action | ACT|ROOT, ACT|ROOT|YAW | rand % 2 | rand % 2 | Creature_hitAllEnemiesInArc |
| BlackWidow | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0x17 idle | ACT, ACT|ROOT | rand % 2, +0x2dc | rand % 4, +0xc | — |
| Bubo | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action | ACT, ACT|ROOT | rand % 2 | rand % 3 | Creature_hitTargetInArc, DiseaseProjectile_ctor, SpellDiseaseEffect_ctor, model_getAttachPoint |
| CastBadger | — | 0x6 action | ACT|ROOT | fixed | fixed | Creature_hitTargetInArc |
| Cazic | 0x12 none | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action, 0xf action | ACT|ROOT, ACT|ROOT|YAW | — | +0x3c9 | Creature_hitAllEnemiesInArc, GroundPoundEffect_ctor, model_getAttachPoint |
| Clockwork | — | 0x6 action, 0x7 action, 0x8 idle, 0x9 locomotion | ACT, ACT|ROOT | rand % 2, +0x3c8 | rand % 3, +0x3c8 | Creature_hitTargetInArc, LightEffect_ctor, decal_add, fx_ringBurst |
| CloudGiant | 0x13 none | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0x17 action | ACT, ACT|ROOT | rand % 2 | rand % 2, +0xc | BoltGoRound_ctor, camera_shake, model_getAttachPoint |
| Creep | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0x11 idle, 0x17 idle, 0x18 action, 0x19 hit, 0x1a locomotion, 0x1b locomotion | ACT|ROOT | rand % 2 | fixed | — |
| Cyclops | — | 0x2 locomotion, 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action | ACT | fixed | fixed | model_getAttachPoint |
| Demon | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0x11 idle | ACT | fixed | +0x460 | — |
| Droid | — | 0x17 death | — | fixed | rand % 2 | PhProp_ctor2 |
| FatCyclops | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0x17 idle | ACT, ACT|ROOT, ACT|ROOT|YAW | fixed | fixed | Creature_hitTargetInArc, dustCloud_ctor, fx_spawn, model_getAttachPoint, poisonGasSpell_ctor |
| FemaleDarkElf | — | 0x6 action, 0x7 action, 0x8 action, 0x11 idle | ACT|ROOT | +0x2dc, +0x3c8 | rand % 4 | Creature_hitTargetInArc |
| Froglock | — | 0x6 action, 0x7 action, 0x8 action, 0x17 hit | ACT | fixed | rand % 2 | — |
| GnawSpawn | 0x12 action | 0x6 action, 0x17 action, 0x18 action, 0x19 action | ACT, ACT|ROOT | rand % 2 | fixed | GutChunk_ctor, fx_spawn, model_getAttachPoint, world_createObject |
| Gnome | — | 0x6 action, 0x17 idle | ACT | fixed | rand % 4 | — |
| Gremlin | — | 0x6 action | ACT|ROOT | fixed | rand % 3 | model_getAttachPoint |
| Hag | — | 0x6 action, 0x7 idle, 0x8 action, 0x9 action, 0xa action, 0x11 idle, 0x17 action, 0x18 oneshot, 0x19 action, 0x1a idle | ACT|0x8000, ACT|ROOT, ACT|TALK, ACT|TALK|ROOT | fixed | rand % 3 | Creature_hitTargetInArc, LightningBolt_ctor |
| Horsemen | — | 0x6 action, 0x7 action, 0x8 action, 0xa action, 0xb action, 0x11 idle, 0x17 action, 0x18 action, 0x19 idle, 0x1a idle, 0x1b idle, 0x1c idle, 0x1d idle, 0x1e idle, 0x1f idle, 0x20 action, 0x21 action, 0x22 action, 0x23 action | ACT, ACT|ROOT, END|ACT|ROOT | +0x3c8 | +0x3c8 | — |
| Innoruuk | 0x13 none | 0x6 action, 0x8 idle, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action, 0x17 action | ACT, ACT|ROOT, ACT|YAW | +0x3c8 | fixed | LightEffect_ctor, camera_shake, fx_modelParticlesNearCamera_1f61c0 |
| IronGuardian | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action | ACT, ACT|ROOT | rand % 4 | fixed | Creature_hitAllEnemiesInArc, model_getAttachPoint |
| Kobold | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0x17 hit | ACT|ROOT | rand % 2, +0x2dc | rand % 4 | — |
| LavaMonster | — | 0x6 action, 0x7 action, 0x8 action | ACT|ROOT | fixed | rand % 2 | MissileWeapon_ctor, model_getAttachPoint |
| MaleDarkElf | — | 0x6 action?, 0x7 action, 0x8 action, 0x9 action, 0x11 idle? | ACT|ROOT | +0x3c8 | rand % 4, +0xc | — |
| Marr | 0x12 none | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0x17 idle, 0x18 idle | ACT|ROOT | — | fixed | Creature_hitAllEnemiesInArc |
| Minion | 0x12 none | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0x17 hit | ACT|ROOT | fixed | fixed | Creature_hitTargetOrPlayerInArc, RainOfFireSpell_ctor, Soul_ctor, model_getAttachPoint |
| Minotaur | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0x17 idle | ACT, ACT|ROOT, ACT|ROOT|YAW, ACT|YAW, LOOP|PURGE|ACT|ROOT | +0x228 | rand % 2 | Creature_hitTargetInArc |
| Mosquito | — | 0x6 action, 0x17 hit | ACT|ROOT | rand % 2 | rand % 4 | — |
| Mummy | — | 0x6 action, 0x7 action, 0x8 action, 0x17 action, 0x18 locomotion | ACT|ROOT | +0x3c8 | rand % 2, +0x3c8 | DustDevil_ctor |
| MummyKing | — | 0x6 action, 0x7 action, 0x8 action, 0x9 idle, 0x17 idle, 0x18 idle | ACT|ROOT | fixed | fixed | — |
| Nightmare | 0x5 oneshot, 0x12 none | 0x6 action, 0x7 oneshot, 0x17 action, 0x18 action, 0x1a idle | ACT | fixed | fixed | Creature_hitAllEnemiesInArc |
| Ogre | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action | ACT|ROOT | rand % 2 | rand % 2 | Creature_hitAllEnemiesInArc |
| RedDragon | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action, 0xf hit, 0x17 oneshot, 0x18 oneshot, 0x19 hit, 0x1a action, 0x1b action, 0x1c action, 0x1d action | ACT, ACT|ROOT, ACT|ROOT|YAW | fixed | fixed | Creature_hitAllEnemiesInArc, fx_spawn, model_getAttachPoint |
| Rondo | 0x3 none | 0x6 action | ACT | fixed | fixed | — |
| Scorpion | — | 0x6 action, 0x17 action, 0x18 action | ACT, ACT|ROOT | fixed | rand % 2 | — |
| SeaMonster | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0x17 action, 0x18 action | ACT, ACT|ROOT | fixed | fixed | — |
| Tormentor | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action, 0x17 locomotion | ACT|ROOT | rand % 2 | rand % 2 | Creature_hitAllEnemiesInArc, Creature_hitTargetInArc, ShockOfFrost_ctor |
| Ulthork | — | 0x6 action, 0x7 action | ACT | rand % 4 | rand % 2 | — |
| UndeadKnight | — | 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0x11 idle, 0x17 action, 0x18 action | ACT|ROOT | +0x3c8 | fixed | — |
| Vampire | 0x13 hit | 0x6 action, 0x7 action, 0x17 locomotion, 0x18 idle, 0x19 action | ACT|ROOT | rand % 2 | rand % 3 | — |
| VampireLord | 0x10 oneshot, 0x12 none, 0x13 none | 0x6 idle, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0x11 idle, 0x17 oneshot, 0x18 oneshot, 0x19 oneshot | ACT|ROOT | fixed | fixed | Creature_hitTargetInArc |
| WarBoar | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action | ACT, ACT|ROOT, ACT|YAW | fixed | rand % 2 | Creature_hitAllEnemiesInArc |
| Warrior | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0x17 idle | ACT|ROOT | fixed | rand % 4 | Creature_hitTargetInArc |
| Zek | — | 0x6 action, 0x7 action, 0x8 action, 0x9 action, 0xa action, 0xb action, 0xc action, 0xd action, 0xe action | ACT|ROOT, ACT|ROOT|YAW | rand % 4 | fixed | Creature_hitAllEnemiesInArc, Creature_hitTargetInArc, GroundPoundEffect_ctor, LightEffect_ctor, decal_add, fx_ringBurst, fx_spawn |

### 5.2 Common base, steered locomotion (walk/run loops without ROOT) (10 classes)

| class | base states that differ | own states (role) | attack flags | hit 0x12 choice | death 0x14 choice | consumers (run) |
|---|---|---|---|---|---|---|
| Ant | — | 0x6 action, 0x7 action | ACT | fixed | rand % 3 | — |
| FireBeetle | — | 0x6 action, 0x7 action, 0x17 action | ACT | fixed | rand % 4, +0xc | — |
| Ghoul | — | 0x6 action, 0x7 action, 0x17 idle, 0x18 idle, 0x1a action | ACT, PURGE|END|ACT | rand % 3 | +0xc | — |
| Goblin | — | 0x2 idle, 0x4 idle, 0x6 action, 0x7 action, 0x8 action, 0x11 idle, 0x17 idle | ACT | rand % 3, +0x2dc | +0xc | — |
| Orc | — | 0x2 idle, 0x4 idle, 0x6 action, 0x7 action, 0x11 idle, 0x17 idle | ACT | rand % 4 | rand % 5, +0x478 | Creature_hitTargetInArc |
| SmallSpider | 0x3 none, 0x5 none, 0x10 none, 0x12 none, 0x13 none | — | — | fixed | rand % 4, +0xc | — |
| SpiderQueen | — | 0x6 action, 0x7 action, 0x8 action, 0x9 idle, 0xa action, 0xc action, 0x17 action, 0x18 action | ACT | fixed | +0xc | Creature_hitTargetAtReach, PoisonProjectile_ctor, camera_shake, model_getAttachPoint |
| WarWraith | — | 0x6 action, 0x7 action, 0x11 idle | ACT | fixed | fixed | — |
| WoodElfSoldier | — | 0x2 idle, 0x6 action, 0x17 idle, 0x18 action?, 0x19 action? | ACT | +0x3cc | fixed | — |
| Wraith | — | 0x6 action, 0x7 action, 0x11 idle, 0x17 action | ACT | fixed | fixed | Skeleton_ctor |

### 5.3 Own state machines (10 classes)

The run switch, timers, target tests and seed draws are executed in
[own-state-machines](own-state-machines.md). The rows below stay the clip
contract for the state that switch requests.

| class | base states that differ | own states (role) | attack flags | hit 0x12 choice | death 0x14 choice | consumers (run) |
|---|---|---|---|---|---|---|
| AntQueen | 0x1 idle, 0x3 idle, 0x10 none, 0x14 action | 0x6 action, 0x7 action?, 0x8 action, 0x9 action, 0xa action, 0x17 action, 0x18 action, 0x19 action | ACT | fixed | fixed | Creature_hitTargetOrPlayerInArc |
| Critter | 0x3 none, 0x5 none, 0x12 none, 0x13 none, 0x14 none | 0x16 locomotion, 0x17 idle, 0x18 locomotion, 0x19 idle, 0x1a locomotion | — | — | — | — |
| Gnaw | 0x12 none, 0x14 locomotion | 0x6 action | ACT|ROOT | — | fixed | Creature_hitTargetInArc |
| GnomeNavigator | 0x1 none, 0x5 oneshot, 0x10 none, 0x12 none | — | — | fixed | fixed | — |
| Mermaid | 0x3 none, 0x5 hit, 0x10 none, 0x13 none, 0x14 oneshot | — | — | fixed | fixed | — |
| NPC | 0x3 none, 0x5 none, 0x10 none, 0x12 none, 0x13 none, 0x14 none | — | — | — | — | — |
| Natasla | 0x1 none, 0x3 none, 0x5 none, 0x10 none, 0x12 none, 0x13 none, 0x14 none | — | — | fixed | fixed | — |
| Skeleton | 0x14 none | 0x6 action, 0x7 action, 0x8 action, 0x11 idle, 0x17 hit | ACT|ROOT | fixed | fixed | — |
| Skelight | 0x12 none, 0x14 none | 0x6 action | ACT|ROOT | fixed | fixed | — |
| Soul | 0x0 oneshot, 0x1 oneshot, 0x3 oneshot, 0x5 oneshot, 0x10 oneshot, 0x12 oneshot, 0x13 oneshot, 0x14 oneshot | 0x17 oneshot, 0x18 oneshot, 0x19 oneshot, 0x1a oneshot, 0x1b oneshot, 0x1c oneshot, 0x1d oneshot, 0x1e oneshot, 0x1f oneshot, 0x20 oneshot, 0x21 oneshot, 0x22 oneshot | ACT, END|ACT | +0x3c8 | +0x3c8 | — |

### 5.4 No animation dispatch in setState (6 classes)

AntWave, CdEyeball, CreatureContainer, FireFly, Generator, Teleporter.

## 6. Player

Full contract: [player-animation-dispatch](player-animation-dispatch.md) (**Observed** by
reading unless marked). The player does **not** use the creature setState dispatch; its
clips are chosen inline by `Player_run` 0x1a5030's action switch (`+0x58c`),
`Player_processDamage` 0x1b2cc0, `Player_takeDamage` 0x1b5330, `Player_move` 0x1b4020 and
`player_resetIdleAnim` 0x1b2470. Summary:

- **Table:** `anim(k) = *(def + cls×0x68 + k)`, `def` one of twelve 111-entry definitions
  (by model), 7 shared entries (two deaths, `nw_walk`) then eight weapon-class rows of 13
  (`k` 0x44 idle, 0x4c walk, 0x54/0x5c run layers, 0x64 heavy, 0x6c cast, 0x74 attack 1 /
  shot, 0x7c hit, 0x84 block, 0x8c/0x94 block reactions, 0x9c block pose, 0xa4 evade).
  `ref_creature_dispatch.player_entry(cls, k)` converts to this module's entry index.
  Combo variants, knockdowns (`knockdown{1,2}_{a,b,c,d}` by hit angle), war cry, fidget,
  ground pound and riding are resolved **by name** in the lump at run time.
- **Locomotion is four persistent base layers** (idle, walk, two run layers; flags 0x1205)
  written directly and weighted every tick by `Player_move` from the stick (`+0x46c` blend,
  ±0.1 per tick, rate knees 0.43/0.7), not started per state as for creatures.
- **Markers** are the creature ones plus 0x20 and 0x8000 (cast): the code waits for the
  marker bit to leave the union `+0x11a` (state 3 on 8, state 0 on 0x10, 0xc on 0x20, 5 on
  0x8000).
- **Events:** only footsteps (walk {0.25 s, 0.75 s} mask 1, run layer 2 {0.45, 0.95} mask 4,
  evade mask 1; installed by `Player_ctor` for rows 0–5, dual wield has none) and the
  ground-pound clip (masks 1/2/4 area damage, 8 effect; installed by
  `SkillGroundPound_cast`). **Melee hits, arrow/throw releases and cast releases are frame
  or weight counts, not events** (melee `since == trunc(16.02/speed)`, net frame 1; cast at
  cast-track weight ≥ 1.0, 0.5 in a net game). Combat and effects code must take player
  timing from `docs/spec/player-tick.md`, not from clip events.
- **Executed:** `Player_pickAttackAnim` transitions over all models × classes × variants ×
  hash intervals (9,216 calls; ad-hoc script, not kept, see that document 3.4).
- **Correction** folded into `docs/spec/player-tick.md` §0: track +8 is weight and +0x10
  life (the old note swapped the names; offsets were right).
- Open: who writes player state 7; the bow/thrown war-cry name buffer that is never
  written; stale fields left by `player_resetIdleAnim`. States 6, 9 and 0xe are executed
  in [player-animation-dispatch](player-animation-dispatch.md) section 6.

## 7. Open and unknown

- **Two fields set together** (**Executed**, 2026-10-20): `select` still records one
  field at a time and still raises on any other condition, including an OR of two
  recorded values. `ref_field_precedence` is the combination contract, re-executed by
  `difftest_field_precedence.py`. Agony setState 0x234168 request 0x12, word +0x2dc:
  any bit of 0x380000 (0x80000, 0x100000 or 0x200000) selects blend entry 0xd; otherwise
  bit 0x40000 selects entry 9; otherwise entry 0xa. Both a knockback bit and 0x40000
  follow 0xd. Where the two conditions are on different words, one field's clip wins:
  FemaleDarkElf 0x12 takes +0x2dc bit 0x80000 over
  form +0x3c8 = 1; Horsemen death takes form +0x3c8 = 1 (stores state 0, no clip) over
  +0x470 = 3; VampireLord states 3, 5 and 0x11 take +0x3c8 = 1 over +0x3cc = 1;
  Clockwork death takes form +0x3c8 over object flag +0xc = 2. A field compared for
  equality is not a mask: Clockwork +0x3c8 is a form index, so 1|2 plays form 3 and
  2|4 passes a null clip. Thresholds on values outside the original 13 probes are still
  **Unknown**. The ten own-machine run switches stay in
  [own-state-machines](own-state-machines.md); their setState rows had no second field
  condition for this pass to combine.
- **Random choices**: periodic residues are exact for the probed draws (0…11 and eight
  large values); a choice that is not periodic is kept as executed points
  (`rand_points`). The *order* of several draws in one case (timer draw before clip draw)
  is in the class bodies of `docs/monsters-2.md` and the executable models, not here.
- **Consumers behind unexplored branches** (**Unknown** for those): the run scan follows
  only the branches a zero creature with callees returning 0 or an object takes. A hit
  that needs "target in range" true while other helpers are false is not seen. Blind
  spots of this scan: Skelight never reaches `Creature_stepAnim` on stub state (its run is
  executed by `ref_arena_monsters`); LavaMonster loops to the 30,000-step cap when callees
  return objects; Soul 0x14/0x1b/0x22 and WarWraith 0x14 fault under object returns.
- **Event times** are executed constructor arguments; whether another writer later
  changes a shared clip's slots (another class sharing the `.anm`, skill code — the spin
  skill moves a clip's event time, `docs/spec/skills-35-68.md`) is not established per clip.
- **Sound cues** (`.anm` sound tables, `game_animEventFoley` for id −2) are presentation and
  were not mapped per class.
- **Rendered check** (**Unknown**): no original model/clip pair was played through these
  tables in a renderer; no console or rig run. Settle with native traces of the same
  synthetic requests (`difftest_creature_dispatch.py` vectors), then a private known
  creature recorded in the rig.

## 8. Reproduce

```sh
python3 -m unittest discover -s tools -p 'test_*.py'
python3 tools/difftest_creature_dispatch.py local/SLUS_209.73        # needs your executable
python3 tools/difftest_field_precedence.py local/SLUS_209.73       # two fields at once
python3 tools/difftest_skill_anim.py local/SLUS_209.73             # player states 6, 9, 0xe
# regenerate (private outputs stay under local/):
python3 tools/scan_anim_dispatch.py local/SLUS_209.73 local/anim-dispatch-scan.json
python3 tools/scan_anim_dispatch.py --runs local/SLUS_209.73 local/runs-anim-dispatch.json
python3 tools/scan_anim_dispatch.py --emit local/SLUS_209.73 local/anim-dispatch-scan.json \
    local/runs-anim-dispatch.json > tools/ref_creature_dispatch_data.py
python3 tools/scan_anim_dispatch.py --markdown local/anim-dispatch-scan.json   # appendix A
```

## Appendix A

Every class, generated: [creature-animation-dispatch-classes](creature-animation-dispatch-classes.md).
