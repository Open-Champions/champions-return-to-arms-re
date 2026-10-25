# Valor WarBoar AI handoff — SLUS_209.73 US v2.00

Research date: 2026-10-24. **Status: MORE**, not an exact live-game completion.
This closes specific native refusal arguments and documents the class state
machine; PCSX2 gameplay and route-specific player damage remain unverified.
No native files were changed. No original code, disassembly, clips or states
are included in this change.

## Evidence and reuse

- **Observed:** executable SHA-256 is
  `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
  Read-only translation source is `local/recomp-out/gen/`:
  `c_027.cpp` for constructor/run/setState, `c_000.cpp` for base constructor,
  sight and target selection, `c_001.cpp` for movement/event/hit helpers,
  `c_004.cpp` for object RNG. These sources are private evidence, not additions.
- **Observed, reused:** `docs/monsters-2.md`, section “WarBoar”, already
  describes the class at run `0x2ba3a0`, setState `0x2bac60`, constructor
  `0x2ba03c`, table `0x517cf0`. Base contracts remain in
  `docs/spec/creature-tick.md` sections 3, 6, 9, 12;
  `docs/spec/arena-monsters.md` section 2.4;
  `docs/spec/combat.md` sections 3 and 4; and `docs/spec/animation.md`.
  This handoff refines their boundaries, rather than reimplementing them.
- **Observed, reused:** `research-campaign-combat` at
  `328b07202e60b39882df49487d3a645a3c56df5c` contains
  `docs/issues/campaign-combat-handoff.md` and rounds 2–5 probes/models.
  Their constructor/event/loader contracts are retained. Its rounds 7–8
  capture used Play!, a written pending-level request and, later, player HP
  support. They are not PCSX2 or unassisted campaign evidence. Its club
  19–24 range describes player-to-boar damage, not boar-to-player damage.
- **Observed, reused:** `research-combat` at
  `faa70331492e91084f0910071089ae3669e3e8fd` documents the shared combat
  composition in `docs/combat-runtime.md` and rounds 3–6. The native
  `creature-ai` checkout at `aee703ff5fe44cec9b8f8c75d169f5bcd25ad1a0`
  documents HP/callback composition in `docs/COMBAT_CREATURE.md`, and its
  restricted movement adapter in `docs/SESSION_CREATURE.md`. Neither a
  restricted mover nor a passing HP adapter constitutes a complete AI tick.
- **Observed (Executed):** `tools/difftest_warboar_ai.py` executes original
  instructions against authored branch/ABI expectations and the existing
  `ref_core.Lcg`. It uses synthetic memory and recording services, not live
  actor state. Perception booleans, movement, animation steps, base run and
  damage outcomes are stubbed in class probes. Separate probes execute the
  real base constructor, slot-25 wrapper, geometric sight body and multi-hit
  loop with their external dependencies stubbed. The class-constructor probe
  executes both type variants and checks all seven event-registration calls,
  including call sites, entry indices, four masks and four raw f32 times;
  base/resource/event services remain stubbed. No whole-tick equivalence,
  full branch coverage, root trajectory or player HP loss is claimed.

## Why the native boars remain idle

**Observed:** at native `valor-fight` HEAD
`252f34a6bf36ef21fff910270d889c4698e09d76`,
`native/src/campaign_actors.cpp` refuses sight, idle-to-wander, chase and hit
reaction state 18. `work/loop-valor-fight-r1/final-audit/headless/result.json`
records five “slot 25 force argument … not documented” refusals and twelve
state-18 refusals. It builds 78 boars but player HP stays
`32.7999954223633` across 4,015 fight ticks. These are native diagnostics,
not retail damage measurements. Class-port revision `711eae1` exists in
that checkout's history.

**Inferred:** removing only the sight refusal cannot make a faithful fight:
the same runtime still lacks chase/attack/reaction composition and real
animation/World services. A constant distance threshold or periodic damage
timer would conceal these missing contracts rather than implement them.

## Perception, aggro and home range

**Observed (Executed):** states 0 and 1 call virtual slot 25 with
`(this, force=0)` at `0x2ba470` and `0x2ba4cc`. Target selection earlier in
the tick calls slot 23 with `force=0` at `0x2ba42c`. State 0 requests 3
when sight succeeds; state 1 requests **0**, not 3. The latter invokes the
normal idle-entry effects, including the base filter's target clearing.

**Observed (Executed defaults; source `0x109fa8–0x10a094`):** base defaults
are HomeRange 1000, pointblankrange 300, visualrange 500, visualarc `0x4000`.
Each has a same-named integer property override. The supplied Valor archive
contains 78 boar placements and no overrides of these four properties or
`PathName` (case-insensitive key scan). These are placement/default facts,
not proof that a script or restored save never changes them.

**Observed (Executed wrapper `0x10e658`):** try pointblank sight first,
facing 0, arc `0x7fff`, near 0, far pointblankrange; on failure try the
creature facing/visualarc and visualrange. The mode is 1 if forced **or**
visualarc equals `0x7fff`, otherwise 0. Base takeDamage `0x116638` changes
visualarc to `0x7fff` (see creature-tick 12.1). This is not a literal
guarantee of visibility at every bearing.

**Observed (Executed geometry `0x10c810`):** for center distance `d` in XY,
attacker radius `ra`, target radius `rt`, bearing delta wrapped to s16,
the tests are `abs(delta) < arc`, `d - rt - ra < far`, and
`near <= d + rt - ra`. Thus attack “25” is **not** a center-distance
threshold. Far and angular boundaries are strict. The ray starts at the
attacker's half-height, uses the target displacement and radius parameter
raw `0x3f8ccccc`; mode 0 passes terrain mask 3 and nonzero mode mask 0.
Sight succeeds for ray return `< 0` or `> 1`, not for exactly 1.
Mode 1 changes the ray mask; it does **not** bypass terrain.

**Observed, reused (`0x10ded0`, creature-tick 6):** on staggered 32nd
frames, query the grid box position ± HomeRange, capacity `0xc0`, temporarily
excluding flag 8. Score with slot 20, adding one for last attacker and one
for current target; equal scores use XY distance. An unreturned target can
be lost on a scan. This acquisition query itself is not a sight test.
The class only tests slot-25 sight while idle/wandering; chase does not
repeat that gate each tick. Distinguish target acquisition from activation.

**Observed, reused (creature-tick 6/12.2):** inert byte `+0x231` suppresses
target work; no-target timer `+0x316` or cflag `0x4000000` clears the target.
Slot 20 rejects self, absent/non-creature objects, dead/prediction-copy
objects and candidates with cflags `0x4000000` or `0x800`; matching team
bytes are not enemies. Other eligible teams score 1, or 4 for candidate
cflag `0x100000000000`. Last-attacker bias does not bypass these gates.

## Tick, chase and pathing

**Observed (Executed call order):** process pending damage `0x110d30`, base
run `0x112948` (return early when it says so), activity `0x10c0f0` (return
early when false), step animation `0x1162b0` at 1.0, apply knockback
`0x115eb8` at raw `0x3e4ccccc`, slot 23, then switch on state. Root motion
and event bits must come from that animation step, not a wall-clock timer.

**Observed:** state 0 requests 1 if away from home (`0x10eed8`) or
`clock(+0x300) > deadline(+0xf4)`. **Executed:** entering state 0 stores
`deadline = clock + 180`; equality does not expire it. Entering state 1
clears the path `0x11a1e0`, picks a wander destination `0x119618`, starts
definition `+0x94` with flags `0x803`, blend raw `0x3dcccccc`, and syncs
animation time (`0x1709f8`). State 1 otherwise calls `0x119f38`.

**Observed (Executed):** the base constructor initially writes both clock
and deadline to **zero**; constructor initialization is not a call to
setState(0). **Inferred:** a native host must not universally initialize
every new boar with a 180-tick idle grace period. Preserve the actual
constructor/load/setState sequence. **Unknown:** a normal-route capture's
first effective deadline after every loader/script/save effect.

**Observed, reused (creature-tick 11):** ordinary non-follower “away from
home” is the strict 3-D test against squared HomeRange times raw
`0x3f2a7ef9` (square the product), not the target-acquisition leash test.
Wander picks a point near home with reach 300, clamped to HomeRange;
the base helper uses two own draws per attempt, bitwise AND with twice
the integer reach, and terrain-height acceptance for up to ten attempts.
Do not substitute a uniformly random disc. Follower variants have separate
48/120 distance tests; absence of `PathName` in the placements alone does
not prove that scripts never assign follower flags.

**Observed (`0x2ba520–0x2ba770`, Executed decisions):** state 3 with no
target requests 0. With a target, use the ordered attack queries below;
otherwise a target in near 0/far 20/arc `0x7fff` causes turn-to-target
`0x1187e0`; failing that, call `Creature_moveToTarget` `0x1143e8`.

**Observed, reused (creature-tick 9):** moveToTarget aims for the target's
position plus `(target.radius + 5)` toward the boar, retaining target Z.
The base moveTo uses avoidance, staggered obstruction probes, sixteen
waypoint pairs, path callbacks and stuck recovery; it is not straight-line
translation. Its common ending turns then calls moveBy along the resulting
facing. WarBoar speed is zero, radius 30 and turn rate 1.0: locomotion
requires animation root displacement/yaw. Small boars retain radius 30;
the drawing scale difference does not shrink these tests.

## Attack selection and animation timing

**Observed (Executed):** each query uses lead 0. Target queries pass ray
mode 0. “Ahead” means current facing; side cones are facing ±8000, all
with arc 3000 unless stated. Preserve query order and short-circuiting:

| State | Ordered selection | Evidence |
|---|---|---|
| 3 | Target near 0/far 25 ahead: own draw `%5`: 0→8, 1→9, else→6 | Observed, Executed; `0x2ba538–0x2ba5a8` |
| 3 | Else target near 25/far 100 ahead →10 | Observed, Executed; `0x2ba5b0–0x2ba5d8` |
| 3 | Else target near 0/far 25 at +8000 →8, then −8000 →9 | Observed, Executed; `0x2ba5e0–0x2ba650` |
| 3 | Else any enemy in near 0/far 25 ahead: same `%5` choice; then +8000→8, −8000→9 | Observed, Executed; `0x2ba658–0x2ba738` |
| 5 | Target near 0/far 25 ahead: default 6; only if last attack 6, one own draw `%3==0` enables a second draw `%3` selecting 10,8,9 | Observed, Executed; `0x2ba770–0x2ba838` |
| 5 | Else target side cones →8/9, then any enemy ahead→6 or side→8/9; otherwise request 3 only when not rooted | Observed, Executed; `0x2ba840–0x2ba960` |

**Observed (Executed RNG):** these are `GameObject_rand` `0x1509d0`, state
at object `+0x44`, not the shared seed. The probe checks final own seed and
that shared `0x404464` stays unchanged for these stubbed class paths.
No simultaneous attack-slot reservation or group scheduler appears here.

**Observed (Executed entry):** states 6–10 clear `+0x3c8` and write last
attack `+0x3cc`. They use blend-in/out raw `0x3e999999` for both sides
(approximately 0.3 seconds). Resource mapping and source flags:

| State | Definition offset / authored description | Flags | Hit / continuation seconds | Clip ticks | Evidence |
|---|---|---:|---|---:|---|
| 6 | +0x24 / forward close attack | 8 | raw `3e999999` / `3f333333` (~0.3 / 0.7) | 49 | Observed; ctor, setState; private archive metadata |
| 7 | +0x54 / attack unused by class run | 0x808 | raw `3f000000` / `3f666666` (0.5 / ~0.9) | 119 | Observed; same; never requested by this class's run |
| 8 | +0x2c / close attack at facing +8000 | 0x4008 | raw `3e999999` / `3f000000` (~0.3 / 0.5) | 49 | Observed; same |
| 9 | +0x3c / close attack at facing -8000 | 0x4008 | raw `3e999999` / `3f000000` (~0.3 / 0.5) | 49 | Observed; ctor call `0x2ba27c`, setState; private archive metadata |
| 10 | +0x34 / forward approach attack | 0x808 | raw `3e999999` / `3f333333` (~0.3 / 0.7) | 49 | Observed; ctor, setState; private archive metadata |

**Observed:** the class's state-10 label “charge” does not select
the separate 25-tick clip: it selects definition `+0x34` (49 ticks).
Decoded member-name mappings remain private in ignored local evidence.
The constructor writes
event mask 1 at the first listed time and mask 2 at the second, through
`creature_setDefEntryParams` `0x118378`; these are absolute seconds, **not
fractions of clip duration**. All on-disc event slots were zero in the
archive metadata check. `anim_advance` crossing behavior and the speed-1
step raw `0x3f7fffff` are already documented in animation sections 4–6.
**Observed (Executed constructor arguments):** state 9's definition `+0x3c`
is entry 7; call `0x2ba27c` supplies continuation time raw `0x3f000000`
(0.5 seconds), mask 2. `check_constructor_events` checks this registration
for both ordinary and small boars, alongside the other six registrations.
**Unknown:** exact live simulation-frame event intervals under blend,
activity, slow/root/status changes; do not round the table into a cooldown.

## Contact, damage and continuation

**Observed (Executed ABI; hit at `0x2baa10`):** all attack states 6–10 call
zero-velocity moveBy, then on event bit 0 call hitAllEnemiesInArc
`0x119b58`: near 0, far 25, facing, arc 3000, signed halfword min/max
`+0xd0/+0xd2`, attack rating `+0xd4`, flags and final argument 0. Set
`+0x3c8=1` afterwards. The latch gates turning; the original damage branch
tests the event bit, **not** `!hit_frame`. Do not use the native latch to
hide repeated/incorrectly supplied animation events.

**Observed (Executed flags):** normally flags 8; state 7, or state 10 on
a non-small boar, consumes one own draw `%3`: zero→`0x80008`, else
`0x40008`. Small state-10 boars use 8 without that draw. These are additional
damage/knockback flags, not an invented multiplier to damage min/max.

**Observed (Executed multi-victim loop):** hitAllEnemiesInArc collects
position ± `(far * raw 0x3fb33333)` with capacity `0x80`, checks slot 20
and geometric sight per candidate in list order, and calls `damage_apply`
`0x1e8230` for **every** passing enemy. It is neither target-only nor
touch-list damage: WarBoar slot 11 `0x2bac58` is empty.

**Observed, reused (combat 3):** a player's final loss depends on its
armour, block, hit rolls, effects/status and the shared RNG. Armour first
reduces each range endpoint by armour/30, bounded below by half the
endpoint and zero; later attack-vs-armour scaling and the rest of the
documented pipeline still apply. Monster stat scaling/balance supplies
the signed min/max/rating fields; the base ctor's HP argument 10 is not
“boars deal 10”. **Unknown:** a verified normal-route Valor boar's outgoing
field values, victim equipment and actual delivered HP changes. The
multi-hit probe stubs damage; shared combat difftests do not fill that gap.

**Observed:** while animation flag 8 is set, state 6 turns before its hit
latch only, states 7 and 10 may turn throughout; the target must pass near
0/far 10/arc 3000. On event bit 1, a target or any enemy in near 0/far
25/arc 8000 requests state 5. Its next tick performs the state-5 selection;
there is no class-level fixed post-swing delay. Otherwise request 3 only
when animation flag 8 is clear. **Executed:** targeted continuation cases
include marker/no-marker and playing/finished combinations.

## Hit reactions, fleeing, leash and groups

**Observed, reused:** WarBoar inherits `Creature_takeDamage` `0x116638`;
pending damage/reaction processing precedes its AI. creature-tick 3/12.1
already specifies HP subtraction, attacker link, damage flags, visualarc
and reaction requests; those are not new boar algorithms.

**Observed, reused (creature-tick 3.1/3.3):** survived positive damage can
request state 18 unless suppress-reaction flag `0x400000` is set or the
creature is already reacting. Flags intersecting `0x4380000` force that
request; otherwise the ordinary branch uses an own-draw one-in-three
test (with separately documented miniboss/cflag-`0x400` branches). A
request is not the same as an accepted WarBoar state transition. Knockback
is handled independently before the class switch.

**Observed (Executed `0x2bae58–0x2bae9c`):** requesting state 18 while
old state is 6 through 15 retains the old state with no reaction animation.
Otherwise blend definition `+0x6c` (hit reaction) with flags `0x10`,
raw `0x3dcccccc` blend times. State 18 waits for animation flag `0x10`
to clear, then requests 3. State 19 waits for `Creature_isStunOver`
`0x119608`, then requests 3. The wounded model below 25% HP is a drawing
change, not a new attack phase (draw `0x2ba340`).

**Observed, reused (filter `0x10a9c0`):** root redirects disallowed states
to 5 with a target or 0 without one; stun redirects to 19; attack cooldown
redirects to 16. No target clears the cooldown. Preserve filter precedence
and the target clearing on state 0, rather than only changing the enum.
**Observed (Executed class state 16):** until `0x1195f0` reports ready,
call fleeFromTarget `0x119f08` with kind 0; ready requests 0. This is
cooldown-driven retreat, not a proven low-HP fear threshold.

**Observed, reused (pickTarget leash):** when not damaged in the last
480 simulation frames, a candidate beyond HomeRange from home is refused
if it is also farther from home than the boar and farther from the boar
than `(both radii + 60)`. Losing a scan's candidates can return chase to
idle/wander. This is not a hard “cross 1000, teleport and heal” rule.
Flee helper home/avoidance/path rules remain creature-tick 9.4; no
boar-specific heal/reset/teleport appears in the class run/setState.

**Observed:** class queries can attack another enemy when the selected
target is not in a usable cone; damage is multi-victim. Target selection
is per-creature, deterministic in grid-list order. The class has no
ally-count/leader/pack alert call in run/setState. Base processDamage
does notify nearby objects within 600 in single-player (creature-tick
3.1); absence of a class pack call does not erase that shared event.
**Inferred:** do not add synchronized pack activation, surround slots,
attack quotas or low-HP fear based on appearance. **Unknown:** Valor script
or nearby-event effects establishing group activation in real play.

## Reproduction, results and remaining capture work

**Observed (Executed):** from this worktree, with private inputs:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_warboar_ai.py \
  SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_warboar_ai.py \
  SLUS_209.73 --seed 7 \
  --archive local/WARBOAR.LMP \
  --valor local/VALOR.GOB
```

**Observed:** private archive SHA-256
`b19dadfafb4d40f2d54ea1e9e4600e773f5dfe1c502d154e549f45e10bb75e5c`;
Valor SHA-256
`8b8a7cb9c88a33ad60d14b7ce8f48918e9c586b199062b0c73e083d4b84c292b`.
Only hashes, numeric metadata and authored explanations from these archives
are published.

**Observed (Executed audit fixes WBAI-01/WBAI-02):** the probes pass 530
cases per seed (20973/7), including two constructor variants checking seven
event registrations each. Both runs use `PYTHONDONTWRITEBYTECODE=1`.
The seed-7 archive/placement scan also passes. A case-insensitive check of
all 70 private archive member names finds zero occurrences in this handoff;
decoded mappings stay in ignored local logs.
The reused `difftest_creature.py --seed 20973 --ticks 12 -k monster/base/A/off`
compares 81 calls; `difftest_combat.py --seed 7 --quick -k damage` reports
39 properties, zero failures (including 315 player-victim cases in its
reported sample). `python3 -m unittest discover -s tools -p 'test_*.py'`
passes 652 tests, rerun with `PYTHONDONTWRITEBYTECODE=1` after the audit
fixes. These are bounded regressions, not full movement coverage.

**Observed:** evidence logs are ignored under this worktree's
`local/boar-ai/`: `seed-20973.log`, `seed-7.log`, `shared-creature.log`,
`shared-damage.log`, `unittest.log`, `pcsx2-preflight.log`.
Audit-fix reruns are under `local/boar-ai/audit-fixes/`:
`seed-20973.log`, `seed-7.log`, `unittest.log`, `member-name-scan.log`.
PCSX2 identifies itself as v2.8.2. An isolated `-datapath … -testconfig
-earlyconsolelog` preflight did not finish in 25 seconds; its log ends
after DataRoot selection, before a VM/game identity. Only the launched
child PID was terminated. The standard PCSX2 BIOS directory was empty
at inspection. That is not proof that no BIOS exists anywhere, nor proof
of the timeout's cause. No existing emulator configuration was edited.

**Unknown:** a real PCSX2 Valor fight capture, exact visual/root trajectories,
effective script/save overrides and first-state timing, attack-marker frame
spacing, observed player damage/knockback and group/leash behavior. There
are **no new gameplay pictures**. To close these: obtain a working PCSX2
configuration with the owner's BIOS and a legitimate Valor state; record
ELF/disc/config/save identities, player stats/equipment, actor pointers,
target/state/clock fields, animation events, outgoing min/max/rating, and
damage callbacks before/after HP. Capture unobstructed approach, an occluded
approach, close/side/charge attacks, an interrupted chase, a retreat past
home and multiple boars. Keep input/state changes explicit and separate
an assisted test from normal campaign behavior. Do not replace this missing
evidence with the earlier Play! capture or a native headless result.
