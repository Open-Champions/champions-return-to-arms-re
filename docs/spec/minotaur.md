# Minotaur spawn and fight handoff — SLUS_209.73 US v2.00

**Status: MORE.** Addressed class contracts and bounded execution are available;
exact live combat, rendering and loot pickup remain unverified.

**Observed / scope, 2026-10-24:** this is research in `t3/research-minotaur`,
not a native-client implementation. The recovered work is based on `9911a6b`.
Private executable identity is SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
Instruction evidence is the executable and the read-only translation
`local/recomp-out/gen/c_024.cpp`, functions
`fn_00288fdc`, `fn_00289400`, `body_002894b8`, `body_0028a16c`.
All addresses below are EE virtual addresses, not host addresses.

**Observed / continuation:** the interrupted attempt left this handoff,
`difftest_minotaur.py`, `ref_minotaur.py` and `test_ref_minotaur.py` untracked
on `9911a6b`, plus ignored logs/CSVs and the isolated PCSX2 setup below.
The continuation preserved those files and reran both seeds, the private
archive checks and all 657 Python tests successfully before committing them.

**Observed / evidence vocabulary:** “Executed” here qualifies an **Observed**
result in `ee_emu.py`, not a running PS2 game. Calls not followed are recording
stubs. **Inferred** marks integration conclusions. **Unknown** marks evidence
still needed; none is replaced with a guessed constant.

## 1. Why the native client refuses it

**Observed:** `codex/port-warboar` commit `711eae1` (a native-port branch of the Godot repository,
not in this repository) implements a bounded actor
adapter, not Minotaur AI. Its `native/src/campaign_actors.cpp` explicitly throws
`Minotaur_run: Unknown in campaign-combat rounds 2-8` before common tick work.
Nonfatal state dispatch throws `Minotaur_setState: state service Unknown`.
Construction additionally requires `weapon_shield`, `minotaur_variant`,
`minotaur_base_flags`, and `minotaur_initial_state`; the fatal transition requires
`minotaur_death_remainder`. Removing these checks would not implement the class.

**Observed:** `codex/valor-fight` `252f34a` binds the boar services in
`native/src/campaign_fight.cpp::boar_services`; that does not supply a Minotaur
state machine. Its rank/tint/ground-object refusals are separate missing
services. The `work/loop-valor-fight-r2-report.md` fight is a diagnostic-placement
WarBoarSmall kill, not evidence that Minotaurs fail PS2 resource lookup.

**Inferred:** the immediate cause is deliberately incomplete native bindings,
not an invalid Minotaur class or a reason to substitute boar stats/animations.
Existing tests prove those refusals are intentional boundaries, not that all
the required service implementations are intrinsically unavailable.

## 2. Reuse these results rather than reconstructing them again

**Observed / prior evidence pins:**

| Branch / commit | Existing result to reuse |
|---|---|
| `research-campaign-combat` `328b072` | `docs/issues/campaign-combat-handoff.md`, rounds 4–8: real Valor records, factory, definition residency, constructor seams, Minotaur Gold-capable fatal-state call, assisted Play! loader capture |
| `research-combat-ctors` `e9777eb` | base/derived construction and state call-out methodology; not Minotaur full AI |
| `research-combat-ctors-2` `5b92837` | shared hit/fatal-state/loot contracts for 0x110d30, 0x10f2c8 and 0x119938 |
| `research-combat-ctors-3` `9ff6ae0` | full-placement/held-part and PhProp follow-up; not a Minotaur runtime capture |
| `research-combat-ctors-4` `6baf4cd` | `docs/spec/full-placement.md`, `weapon-holder-slots.md`, `docs/combat-runtime.md`, shared fatal-state/loot contracts: shared services and their executed boundaries |
| `research-creature-stats` `eaebc00` | `docs/creature-stats-port-check.md`: `Creature_setStats`, level scaling, unsigned balance lookup and holder attachment difftests |
| `research-boar-ai` `dbc3d59` | `docs/issues/warboar-ai-handoff.md`: shared perception defaults, exact sight geometry, target scoring/leash, movement and damage call-outs; its WarBoar state decisions are not Minotaur decisions |

**Observed:** these branch-only documents are not necessarily present on this
branch; read them in their existing sibling worktrees or with `git show
<commit>:<path>`. This handoff does not copy their research or merge their trees.

## 3. Factory and construction contract

**Observed / prior round 5:** `world_objectFactory` 0x159c94 selects constructor
0x288fdc and allocation size **0x470** for all six Valor `Minotaur` records.
Definition **0x501200**, class vtable **0x5165f0**; tick slot 4 is 0x2894b8,
draw slot 5 is 0x289400, set-state slot 27 is 0x28a16c. Do not use the WarBoar
constructor's register ordering:

```text
Minotaur_ctor(this, typeName, positionPointer, signed16Angle, propertiesPointer)
 -> Creature_ctor(this, typeName, copiedPositionPointer, signed16Angle,
                  definition=0x501200, propertiesPointer; f12=10.0)
```

**Observed:** the class saves `typeName` from a1. The old round-5 probe supplies
an additional unused argument; the body does not require that extra argument.
`Creature_ctor` 0x109d68 → `GameObject_ctor` 0x14cb10 must complete first,
including definition-generation resource resolution, properties, identity,
stats/own RNG, and grid ownership. The nominal base HP argument 10 is replaced
by `Creature_setStats` whenever a type name is present; it is not Minotaur HP.

**Observed / executed:** `difftest_minotaur.py::check_constructor` checks 100
cases per seed with the base constructor **stubbed**, but original class code,
case-insensitive comparison, own RNG and holder setter running. Class-local
results, before `Creature_init` (that final call is stubbed):

| Object offset | Contract / evidence |
|---|---|
| +0x48 | Minotaur vtable 0x5165f0 |
| +0x50 | pointer to embedded `WeaponShield` at `this+0x3c8` |
| +0x3c8 | holder vtable 0x50cda0, initialized before virtual hand calls |
| +0x1c | radius 25, raw f32 0x41c80000 |
| +0xb0 / +0xb4 / +0xb8 | turn 0x3f999999 (approximately 1.2), kind byte 11, speed word zero |
| +0xec / +0xf4 | current global simulation frame / that frame +300 (32-bit stores) |
| +0xa8 | base flags OR 0x200040000; successful state 0 subsequently clears 0x200 |
| +0x232 / +0x46c | state zero / first-charge marker zero |
| +0xe8 | body variant bitset, described below |
| +0x220 | 64-bit return from `model_buildHideMask` 0x179550 |

**Observed:** holder storage initialization also resets flag/entry bytes,
its embedded trails' halfword fields and sentinels (0x289058–0x2890d8).
Use the actual holder constructor/contract, not an uninitialized pointer.
`WeaponShield` slot 1 at 0x11bc18 receives hand 1 / one-based definition entry
21 (first-hand part) and hand 2 / entry 25 (second-hand part), with t3=0x20
still present in the recorded register call. The established setter writes entry bytes and flags;
do not invent semantics for that extra register.

**Observed:** ordinary Minotaur consumes **one own-object RNG draw** after
base initialization and writes `1 << (draw & 1)` at +0xe8. Case-insensitive
`minotaurboss` instead attaches second-hand entry 23, writes variant 4, and skips
that class-local draw. Both call `model_buildHideMask(modelSlot0, variant)`.
Base HP RNG comes earlier. Never replace either own draw with the shared seed.

**Observed / executed continuation:** `difftest_minotaur_ai.py::check_base_flags`
runs the class, `Creature_ctor` and `GameObject_ctor` together in 16 cases per
seed. Property lookups, stat assignment, resources, grid linking, animation
and final init remain call-outs. Starting flags are preserved, with `MiniBoss`
adding 1, `IgnoreDamage` adding 0x1000000000000, and any of `light1`, `light2`,
`ambient` adding 0x40000000 (base 0x10a0dc–0x10a190; the probe selects `light1`).
The class then ORs 0x200040000 and accepted state0 clears 0x200. Thus a zeroed
allocation with none of those overrides has **0x200040000 before final init**;
this is not a claim that scripts/activity/load leave flags unchanged afterwards.
Position, signed16 facing, definition and property pointer forwarding are
also checked. No replacement base-HP formula or resource manager is used.

**Observed / reused placement check:** the six actual Valor Minotaur records
in the Valor placement archive (SHA-256
`8b8a7cb9c88a33ad60d14b7ce8f48918e9c586b199062b0c73e083d4b84c292b`)
have only `name` property entries. There are no placement overrides of the
flags or perception defaults above/below. Later script/save effects remain
outside that statement. The continuation uses the existing
`research-campaign-combat` parser; it does not replace the loader.

**Observed:** final sequence is hide mask → `anim_clear(this+0x114)` 0x1707b0
→ `Minotaur_setState(this,0)` → `obj_runEvery60` 0x14f2b8 → eight definition
event configurations via 0x118378 → `Creature_init` 0x10a230. That last service
must retain terrain, properties, scripts, initial state changes and holder
placement; the bounded constructor test does not supply those effects.

## 4. Stats for every monster level and difficulty

**Observed:** `balance_lookup` 0x223a4c uses the **type name**, not the C++ class.
For the actual `Minotaur` match in the private balance data, the
semantic multipliers are HP ×6, armour ×2, damage ×2.5, attack ×1, XP ×2.5.
These are percentage integers converted by unsigned load and multiplied by
raw f32 **0x3c23d70a**: even 100 does not become exact 1.0. Do not use rounded
decimal multipliers when exact replay matters. A `MinotaurBoss` lookup is a
different row (HP ×8, armour ×4, damage ×2, attack ×2, XP ×3), not the ordinary
Valor row; arbitrary `Minotaur*` suffixes need their own lookup/default behavior.

**Observed / reused executed model:** use `tools/ref_combat.py::monster_stats`
and `::level_scale`, not a new approximate stat implementation. Ordinary
rank-zero, one-player equations below explain those functions; operation order,
PS2 FPU and software-double behavior remain authoritative in that model:

```text
L = raw f32 at g_levelMonsterLevel 0x4f714c
p = five balance_lookup outputs, in HP/armour/damage/attack/XP order
r = GameObject_rand(this) % 5                 # exactly 0..4
damageFactor = mul32(p.damage, 0x3fc51eb8)     # approximately 1.54
HP = toSingleSoftDouble((15.5 + r) * powf(mul32(p.HP,L), 0x3f599999))
HP = difficultyHPScale(HP)                   # below; maxHP gets same result
armour = s16(trunc(mul32(mul32(p.armour,14),L)))
low = s16(trunc(mul32(damageFactor,powf(L,1))))
high = s16(trunc(mul32(add32(damageFactor,damageFactor),powf(L,1))))
if high < low+1: high = s16(low+1)
attack = s16(trunc(mul32(mul32(L,14),p.attack)))
XP = float32(trunc(mul32(powf(mul32(p.XP,L),0x3fa9374b),8)))
```

**Observed:** difficulty HP factors are unchanged on 1, ×1.5 on 2, HP+HP on
3, ×2.5 on 4, ×3 on 5, except `stomedal`/`innpit`. Difficulty also changes
**L before the stat calculation**: if table byte is b, difficulty 1 gives b+2;
2–5 give `(b+2)*0.75 + {34,61,88,115}` in PS2 f32 order. Valor row 50 at
0x4f7210 + 50×0x30 has b=20, hence L is **22, 50.5, 77.5, 104.5, 131.5**.
Damage/armour/attack/XP change with L; they do not gain another arbitrary
difficulty multiplier. HP and maxHP are +0x228/+0x22c; armour +0xe4,
damage +0xd0/+0xd2, attack +0xd4, XP value +0xd8.

**Observed / reused:** rank 1, multiplayer, medal suppression, `Dead`, and
rank/type-specific exceptions remain exactly those in `monster_stats` and the
pinned stats research. For 2–4 players with suppression word 0x4f713c zero,
HP factor gains `1+0.6*(n-1)`, XP gains n, ordinary Minotaur damage gains
`1+0.15*(n-1)`; rank 1 modifies the inputs further. Do not reapply scaling
after the model. `Dead` zeroes current HP, not rolled maxHP.

**Observed / executed:** the new script compares original 0x10a620 with the
existing reference on **4,125 cases per seed**: integer L=1..160 plus all five
Valor scales, each crossed with difficulties 1..5 and all five possible HP
roll residues. It compares HP/maxHP float bits, signed stat fields, XP bits
and ending own seed. Private `local/minotaur/stats-{20973,7}.csv` contains
the per-level/difficulty/own-seed results. Some extra combinations intentionally
cross a Valor L with another difficulty to isolate the two effects. This is
not a measured campaign seed, nor new multiplayer/MinotaurBoss execution.

**Observed / executed Valor summary:** ordinary rank0, one player, matching
level scale/difficulty, all five own-roll residues. HP endpoints below are
**raw f32 bits**, not rounded decimal HP. The private CSVs contain each roll.

| Difficulty | L | HP minimum–maximum bits | Armour | Damage low–high | Attack | XP value |
|---|---:|---|---:|---:|---:|---:|
| 1 | 22 | 0x4475e687–0x449aade9 | 615 | 84–169 | 307 | 1599 |
| 2 | 50.5 | 0x453add8f–0x456b16bc | 1413 | 194–388 | 706 | 4796 |
| 3 | 77.5 | 0x45b3493c–0x45e18daf | 2169 | 298–596 | 1084 | 8449 |
| 4 | 104.5 | 0x46107794–0x4635bfba | 2925 | 402–804 | 1462 | 12544 |
| 5 | 131.5 | 0x4652c28f–0x46849329 | 3681 | 506–1012 | 1840 | 16997 |

**Observed:** these are outgoing stat inputs, not guaranteed player HP loss;
the damage pipeline below still applies. The 1..160 probe interval is a test
domain, not an inferred maximum legal monster level. Use the reused formula
for other levels, including its signed16 conversion/wrap behavior.

## 5. Resource, animation and presentation bindings

**Observed:** definition slot/resource pointer i lives at `def+12+8*i`.
0x118378's event index is **i+1**, not i. The 26 resources in definition order
are identified by indices and authored roles; decoded mappings stay private:

| Zero-based index | Pointer offset | Authored role |
|---|---|---|
| 0, 1 | +0xc, +0x14 | body model and material |
| 2–19 | +0x1c through +0xa4 | eighteen animation resources |
| 20, 21 | +0xac, +0xb4 | first-hand model and material |
| 22, 23 | +0xbc, +0xc4 | alternate second-hand model and material |
| 24, 25 | +0xcc, +0xd4 | ordinary second-hand model and material |

**Observed / execution lookup:** the archive identifier is resolved from the
string pointer at definition +0; resource identifiers come from the string
pointers at `def+8+8*i`. The balance loader 0x223998 supplies its archive and
member references at executable string addresses 0x53fc78 and 0x53fc88.
The probes decode these only from the owned inputs at execution time.
`--out` saves all decoded mappings as ignored `private-members.json`, with
clip mappings also confined to the private CSVs; none is embedded here.

**Observed / prior runtime evidence:** campaign research round 7 saw all 26
`res_find` returns nonzero during an assisted Play! Valor load, along with
six actual constructed Minotaurs. This was **not PCSX2**, not an ordinary gate
transition, and not a Minotaur fight. Reuse its captured resource identities;
do not transplant that capture's heap addresses into the client.

**Observed / executed:** constructor event settings and original animation
relocation/configuration/advancement were checked against the existing
`ref_anim` model on all 18 animation resources. Private clip CSVs record lengths
and emitted masks; these are isolated, fresh-animation-stack, rate-1 advances
starting with probe tick **0**, not real combat frame offsets.

| State / zero-based definition index | Event seconds as raw f32 → mask | Observed isolated tick |
|---|---|---|
| 6 / 4 (+0x2c) | 0x3e4ccccc → 1 | 12 |
| 7 / 5 (+0x34) | 0x3e4ccccc → 1; 0x3f199999 → 1 | 12; 36 |
| 8 / 6 (+0x3c) | 0x3ecccccc → 1 | 24 |
| 9 / 7 (+0x44) | 0x3e4ccccc → 1; 0x3eb851eb → 4 | 12; 21 |
| 10 / 8 (+0x4c) | 0x3e4ccccc → 1 | 12 |
| 11 / 3 (+0x24) | 0x3f199999 → 1 | 36 |
| index 2 (+0x1c) | 0x3f199999 → 1 | 36; no direct attack-state binding here |
| index 12 (+0x6c) | 0x3e4ccccc → 1 | 12; charge overlay, not a separate state |

**Observed:** state animation mapping is in authored `ref_minotaur.state_animation`
and executed against all 24 switch entries plus invalid requests, at three HP
bands and both charge-marker states. `CHANGE` is 0x16cfe0; `BLEND` 0x16ceb0.
Most blend times are raw **0x3dcccccc**, not the host-rounded representation
of decimal 0.1. Preserve flags and both blend arguments, rather than guessing
clip duration as the attack cooldown.

**Observed / executed continuation:** `model_buildHideMask` 0x179550 starts
with the complement of the model's u64 at +8. If u16 +0x10 has mask0x2, each set
selector bit applies its 16-byte row at `model + 16*u8(model+0x21) + 16*bit`:
OR the first u64, then AND the complement of the second. Original instructions
on the private, unmodified definition-index0 model give selector0 → **0x233**, ordinary
selector1 → **0x433**, ordinary selector2 → **0xb3**, boss selector4 → **0x15c**.
The probe compares this metadata calculation and the original return; it
does not claim rendered visibility from the mask alone.

**Observed / executed continuation:** draw 0x289400 obtains model via virtual
slot16, calls `Creature_draw` 0x10b048 with
`(this, model, definition texture slot1, 0)`, retains that result, obtains
model via slot16 **again**, then calls holder slot18 with
`(holder, definition, secondModel, drawResult)` if a holder exists.
This is how held-part presentation joins the body draw, not separate
world enemies. Four zero/nonzero-result/holder cases check this call order;
they do not impose a returned draw-chain value on the class draw method.
Texture/material/part interpretation,
actual visual quality and live animation-to-damage alignment are **Unknown**
in this new probe; the shared holder/placement research supplies the service
contracts, not a new rendered Minotaur proof.

## 6. Tick order, aggro and AI

**Observed:** 0x2894b8 has this strict order:

1. model slot 16 → `Creature_processDamage` 0x110d30;
2. model slot 16 again → `Creature_run` 0x112948; nonzero return exits;
3. `Creature_updateActive` 0x10c0f0; zero return exits;
4. holder slot 21 `(holder, definition, this; f12=0.5)` if holder exists;
5. `Creature_stepAnim(this; rate=1)` 0x1162b0, save returned event bits;
6. `Creature_applyKnockback(this; 0x3f333333)` 0x115eb8;
7. virtual slot 23 `Creature_pickTarget(this,0)`; then read signed16 state
   +0x232 and dispatch it.

**Observed / executed continuation:** eight combinations of holder presence,
base tick early exit and active/inactive result compare the complete ordered
prefix and arguments above. These are class control-flow checks; the base
services and holder effects are recording stubs.

**Observed / reused:** aggro is shared `Creature_pickTarget` 0x10ded0, not a
Minotaur-specific fixed chase radius. See `docs/spec/creature-tick.md` section
6: serial-staggered 32-frame scans, HomeRange box/leash, last-attacker/current
target scoring and target-handle lifecycle. `Creature_canSeeTarget` slot 25
0x10e658 supplies point-blank/visual-range/cone tests. `Creature_filterState`
0x10a9c0 runs **before every Minotaur state change**, may rewrite/reject it for
root/stun/cooldown, and clears targets on zero-state selection. Reuse the
base constructor's perception/properties and these helpers; neither an
always-true sight stub nor a hard-coded target implements aggro.

**Observed / reused from WarBoar `dbc3d59`, also executed in the Minotaur base
probe:** default HomeRange1000, pointblankrange300, visualrange500,
visualarc0x4000; same-named properties override them. Slot25 first uses facing0,
arc0x7fff, near0/far pointblankrange; on failure, actual facing/visualarc and
visualrange. `force=0` does not imply terrain is ignored. For distance d,
attacker radius ra, target radius rt and wrapped signed16 bearing delta,
the shared sight geometry requires `abs(delta) < arc`, `d-rt-ra < far`,
and `near <= d+rt-ra`; angular and far boundaries are strict. The terrain ray
still has to pass. See the pinned WarBoar handoff and creature-tick section6
for scan/leash/scoring and section9 for movement/path/terrain. A Minotaur's
radius25 does not turn a far36 attack query into center distance36.

**Observed:** all sight tuples below are `(near, far, facing offset, arc)`
with lead 0 and rayMode 0 at 0x118d40. Arc units are signed16 angle units,
not degrees. Ranges incorporate the shared helper's radius/sight tests.

| State | Observed dispatch behavior / branch evidence |
|---|---|
| 0 | slot25 true →1; otherwise away-from-home 0x10eed8 true →1; otherwise remain. **No WarBoar 180-frame idle timeout** in this state. 0x2895d0–0x289614 |
| 1 | if slot25 true, turn to target then sight `(0,+0x3ae,0,8000)` →3; if slot25 false, move to wander destination. 0x289614–0x289688 |
| 3 | null target →0; sight `(0,12,0,8000)` →5; if target not charging, sight `(0,36,0,8000)` →5; if still not charging and `(0,36,0,32767)` true, turn only; otherwise if hand1 empty and signed +0x468 < age, `(60,300,0,8000)` →12; else move-to-target. 0x289688–0x2897d4 |
| 5 | Mid-HP special guard first (below); otherwise test unarmed forward `(0,36,0,8000)` →6; armed forward same sight →7 or8 by own draw low bit; then hand1-equipped left `+0x4000` →9, right `-0x4000` →10, back `-0x7fff` →11, each `(0,36,offset,8000)`. Then empty-hand1 + cooldown expiry + `(300,60,0,8000)` →12 **with near/far in that order**, not repaired. Then all-around `(0,36,0,32767)` →turn; else if not rooted →3. 0x2897d4–0x289bd0 |
| 6–8 | settle and turn; attack only for saved event bit1; when animation flags +0x11a lack bit8 →5. 0x289bd0–0x289cd4 |
| 9–11 | moveBy(zero input vector, retaining animation root motion), bit1 attack; lack anim bit8 →5. 0x289cd4–0x289ecc |
| 12 | charge state, detailed below. 0x289ecc–0x28a048 |
| 16 | attack-ready helper true →0; otherwise flee-from-target(mode0). 0x28a09c |
| 18 | anim bit0x10 clear →3. 0x28a068 |
| 19 | not-stunned helper true →3. 0x28a084 |
| 20 | moveBy(zero) then deadUpdate(this, savedEvents, zeroOffset, noBlood0; height20). 0x28a0e0 |
| 23 | signed age +0x300 **strictly greater** than +0xf4 →3; equality waits. 0x28a048 |
| 2,4,13–15,17,21,22 and out of range | request state0. 0x28a134 |

**Observed:** the mid-HP guard tests current HP strictly below max×raw
0x3f28f5c2 and strictly above max×raw 0x3ea8f5c2 (approximately 66% and 33%).
In state3 entry this band chooses index19 (+0xa4); outside it chooses
index16 (+0x8c). In state5, forward sight `(0,36,0,8000)` in this band picks state6 unless the
target is attacking this Minotaur. Then an own draw `%3 != 0` plus hand2 full
picks state23 (guard); otherwise state6. Thus “low HP always flees” is false.
State23 entry sets flag0x200 and deadline `age + ownDraw%120 + 60`.

**Observed:** state12 entry changes to index16 flags0x80b; only while +0x46c is
zero does it overlay index18 flags8 and set that marker to1. Charge tick
checks animation-presence 0x170d88 for indices16 and12. If index16 is present,
index12 absent and forward sight `(0,36,0,8000)` passes, it changes to index15 flags
0x803 and overlays index12 flags0x818. With a target it turns/settles and
hits only on bit1, with flags **0x100041** and no descriptor. While anim bit8
is set and bit0x10 clear, sight `(0,300,0,8000)` must still pass to continue.
Otherwise, unless bit0x10 is still set while bit8 is set, it schedules
`+0x468 = age + ownDraw%180 + 300` and requests state3. Preserve both timer
fields and the once-only marker; they are not a generic attack interval.

**Observed / executed:** 20 targeted decisions/timer-boundary cases per seed
exercise representative paths at the addressed sight call sites; state23
deadline equality is checked explicitly. Sight, target acquisition, holder
queries, movement, common tick and state transitions are stubbed in this
decision probe. The full state3/state5/charge behavior above is **read**, not
a claim that those 20 cases cover every branch or a real battle.

**Observed / executed continuation:** 116 additional decision cases per seed
check idle/wander, both charge-entry range orders, holder/cooldown equality,
both armed-forward random choices, one-f32-step neighbors of both health
thresholds, guard choices, reaction/stun/flee exits and signed timer edges.
Another **256 charge cases** cross index16/index12 presence, both sight results,
target presence, event0/1 and animation flags0/8/16/24. They compare actual
overlay call arguments, target-dependent hits, exit requests, own RNG and
deadline stores. Sight/animation/movement/base services remain scripted.
No live blend, trajectory or final damage follows from this coverage.

**Observed / executed continuation:** 11 composed state-filter cases execute
0x10a9c0, root/stun/readiness helpers and the original class method together:
root redirect takes precedence, then stun, then cooldown; no target clears
cooldown; defeat clears the status timers; inert state1 is refused before
class-side flag clearing. PvP-mode global refusal and the general filter
model remain reused shared research, not newly exhaustive filter coverage.

## 7. Attack and damage contract

**Observed / executed:** each attack uses `Creature_hitTargetInArc` 0x119938
with facing +0x38, arc **8000**, near **0**, far **36**, signed16 damage low,
high and attack from +0xd0/+0xd2/+0xd4. State6 flags **0x440001**, states7/8
**0x440008**, states9/10/11 **8**. States7–11 fetch holder slot17 descriptor
for hand1 (or null without a holder); state6 passes null. The tick function
does not directly subtract rolled weapon damage from the player.

**Observed / reused executed helper:** hitTargetInArc tests the target through
`creature_canSeeObj` (lead0/rayMode0), then calls `damage_apply` 0x1e8230 with
that victim/attacker, converted low/high, attack, flags and descriptor. There
is no new class-specific enemy/dead test. Armour, hit rolls, guard, elemental
effects, thorns and status damage remain the shared combat contract in
`docs/spec/combat.md` and ctor-round4 `combat-runtime.md`; low/high are not
guaranteed final HP loss. Damage intake is `Creature_takeDamage` 0x116638
(slot2), which subtracts HP and queues pending reaction data for the next
processDamage; do not maintain a second detached Minotaur HP counter.

**Observed / executed:** 96 attack event/animation cases per seed compare
call arguments and next-state requests for states6–11, with masks0/1/4/5 and
anim flags0/8/16/24. Event4 on definition index7 alone makes **no hit**. The original
probe's descriptor getter returns zero. The continuation adds **48 cases**
that execute the real WeaponShield slot17 (0x11be20) and
`Creature_hitTargetInArc`, with target/no-target, sight pass/fail and
holder/no-holder. Hand1 returns `holder+0x50` (actor+0x418), forwarded to
`damage_apply` for states7–11; state6 still forwards null. Signed negative
and positive stat fields are checked through their float conversions.
Descriptor contents, geometric sight and damage outcomes remain call-outs
or synthetic memory; live player HP loss is **Unknown**.

## 8. Defeat, corpse and loot

**Observed / reused:** common processDamage initiates state20 through virtual
slot27 when HP reaches zero, sets the defeat flags, awards XP and handles
attacker/loot-for-killer effects. The class state method supplies the ordinary
loot/defeat-animation/onDeath sequence; do not add a duplicate XP award there.
Reuse `Creature_processDamage` and `player_giveExp` from the existing combat
contracts. Neither entering state20 nor a floating damage number alone proves
an integrated kill or an inventory reward.

**Observed / executed:** after the shared state filter accepts state20,
0x28a564–0x28a694 does, in order:

1. copy position, pass signed16 facing and null filter to `Creature_dropLoot`
   0x10f2c8 with f12..f17 raw bits **0x42100000, 0x40000000, 0x3fcccccc,
   0x3f199999, 0x3fb33333, 0x3e800000**;
2. holder slot11 0x11bc90, first hand1 then hand2, `(holder, hand, this,0,0)`;
3. own-object RNG low bit selects definition index10 or11, change flags0x806,
   blend raw0x3e4ccccc;
4. virtual slot28 `(this,0)` → inherited `Creature_onDeath` 0x10beb8;
5. finally store state20 at +0x232.

**Observed:** six floats above mean zOffset36, throwSpeed2, goldScale≈1.6,
goldChance≈0.6, qualityRow≈1.4, itemChance0.25, in that order (shared
`drop_loot` contract in ctor-round4 `ref_combat_monsters.py`). The raw
patterns are authoritative. The holder calls are **drop-part services**, not
proof that the held parts are player inventory drops; their physics objects,
placement and allocation are shared researched services.

**Observed / prior executed evidence:** campaign round4 already ran this
defeat→loot-generator seam with ordinary rank, no tint, one player, level22,
fresh shared seeds: seed20973 requests Gold; seed7 does not. Those are
synthetic seeds, not the seed after a live Valor fight. Reuse the actual
`Creature_dropLoot` rank/tint/eligibility branches and `loot_generateDrops`
0x100d54; do not set goldChance zero as for a WarBoar or assume a guaranteed
gold object. Rank1/2 and tint alter calls/scaling, and the generator has
early-return paths. Actual ground objects, landing, pickup and player-record
credit need the shared Gold/PhProp/pickup chain, not a direct HUD increment.

**Observed / reused execution refreshed:** the continuation calls only
`research-campaign-combat`'s existing `check_minotaur_source`, using its
actual first Valor record and the same private executable. Seed20973 gives
one Gold request and 645 shared draws; seed7 gives none and 7 draws. The
logged outcomes are respectively `done` and `no equipment roll`. The existing
generator model agrees with the original; constructors, physics/terrain and
world publication remain recording stubs. These are not 645 draws consumed
by the Minotaur class itself, nor live seed-stream measurements.

**Observed:** state18 (hit reaction) drops both held parts only below the
strict maxHP×0x3ea8f5c2 threshold, then blends index13 flags0x810.
State16 writes cooldown60 at +0x318 and runs/rewinds; state19 changes to
index14 with blend0x3e999999. State20's later tick uses shared corpse sinking,
blood and deletion via `Creature_deadUpdate` 0x1108a0, not immediate despawn.

**Observed / executed continuation:** 17 cases cover four class defeat
sequences (holder/no-holder and two own seeds), four draw sequences, six
reaction-drop threshold cases and three corpse-event forwards. Defeat call
snapshots show the old state remains stored through loot, holder drops,
defeat animation and onDeath; state20 is stored afterwards. This prevents
reordering those side effects or treating a dropped held part as an inventory
award. Corpse sinking/deletion bodies themselves are reused shared research.

## 9. Verification, capture limitation and remaining work

**Observed / executed:** execute these from this worktree; outputs remain ignored:

```sh
for seed in 20973 7; do
  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_minotaur.py \
    SLUS_209.73 --seed "$seed" \
    --iso "$HOME/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso" \
    --out local/minotaur/continuation
  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_minotaur_ai.py \
    SLUS_209.73 --seed "$seed" \
    --iso "$HOME/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso"
done
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

**Observed / executed results:** each seed passes 168 state/health/charge,
96 event/attack, 100 constructor and 20 initial decision cases, plus 4,125
stats cases and 18 original clip relocation/configuration/advancement checks.
The continuation adds **476 cases per seed**: ordered tick8, decisions116,
charge256, descriptor/hit forwarding48, state-filter11, defeat/draw/corpse17,
base flags/ABI16, private-model masks4. Total: **4,985 cases per seed** plus
18 clips, zero mismatches; 657 Python tests pass. These are case counts, not
instruction-coverage percentages, native acceptance or full-fight validation.

**Observed / MINO-01 correction:** the five complete additions contain zero
case-insensitive matches for the 77 member/archive identifiers decoded from
the owned balance/actor inputs, and zero standalone tokens matching any of
the eighteen private animation stems. The input-derived scanner and all
decoded mappings stay ignored under `local/minotaur/audit-fixes/`.
Both probes resolve private identifiers through executable addresses or
definition indices at execution time; tracked text uses indices, offsets and
authored descriptions. The correction preserves the numeric contracts and
the existing Unknown boundaries. Seed20973/7 and the 657-test suite were
repeated; the private stats/clip CSVs match the preceding evidence byte for
byte. Fix evidence: `seed-{20973,7}.log`, `ai-{20973,7}.log`, `unittest.log`,
`member-name-scan.log`, `csv-parity.log` and `evidence.json` in that directory.

**Observed / private evidence:** `local/minotaur/continuation/` contains
`recovered-{20973,7}.log`, `ai-{20973,7}.log`, `stats-{20973,7}.csv`,
`clips-{20973,7}.csv`, `shared-loot.log`, `unittest-recovered.log`,
`unittest-final.log` and the evidence manifest. No new gameplay pictures exist.
The recovered research was committed as `9f7616a`; the continuation is a
separate local commit. No native implementation files are changed here.

**Observed:** no native/Godot build was necessary or performed. No source,
disc, translation, emulator config or other worktree was modified outside
this worktree; no processes were killed by name. No public-server contact,
push, branch creation or PR operation was performed.

**Observed / capture prerequisite, not gameplay:** installed PCSX2 reports
v2.8.2. A separate `-datapath <worktree>/local/pcsx2` configuration/boot attempt
created `local/pcsx2/PCSX2/inis/PCSX2.ini` with
`SetupWizardIncomplete=true`. Both that profile's BIOS directory and the
existing `~/Library/Application Support/PCSX2/bios` directory contain no
BIOS file. During continuation the interrupted boot was still running as
PID50442, with its command line selecting this worktree's isolated datapath.
SIGTERM did not stop it; SIGKILL to that **exact PID** did, and a subsequent
PID check confirmed exit. Existing user profiles were not changed. Private logs:
`local/minotaur/pcsx2-{config,boot}*`. **No PCSX2 game frame or Minotaur
capture was obtained; there are no new gameplay pictures.**

**Unknown / remaining exact-playback requirements:**

- PCSX2 gameplay capture: supply an owner-provided legally dumped BIOS and complete
  setup in the isolated profile; use a legitimate Valor save/route, record
  character/difficulty/equipment/settings/patch and starting-state hashes,
  simulation frame/seed and a Minotaur's constructor, attack, hit, defeat and
  pickup sequence. Do not relabel the prior assisted Play! capture as PCSX2.
- Live blend/overlay/root-motion timing, shared sight/terrain/holder effects,
  runtime descriptor contents, final damage and exact animation appearance are not
  established by class-local stubs or fresh-stack clip stepping. Capture and
  cross-check these against the runtime, preserving inherited base state.
- The adapter still needs real state-filter, holder tick/query/drop/draw,
  model-hide, animation stack/events/root motion, common tick/targeting,
  terrain/movement and class dispatch bindings. This research does not remove
  refusals or execute a native Minotaur encounter.
- An end-to-end Minotaur kill→XP→loot→ground-object→pickup→credit, including
  any rank/tint variants requested by the real records, remains unverified.
  Apply existing shared contracts; do not fill these services with no-ops.

**Inferred / port order:** implement the services in constructor order, bind
all class states (including filter rewrites), then execute the ordered tick and
event-driven damage path, followed by holder/corpse/loot services. Keep one
authoritative world object/HP/RNG identity and explicit unsupported paths
until each service is grounded. This is sufficient to replace the current
“Unknown” labels with addressed implementation tasks, not to claim exact
playability has already been achieved.
