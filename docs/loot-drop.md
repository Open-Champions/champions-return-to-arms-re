STATUS: MORE

# Loot construction, pickup, Gold, and starting equipment

Research continuation, 2026-10-24, SLUS_209.73 US v2.00. Started from clean
`t3/research-loot-drop` at `9911a6b`, retaining the pickup handoff at `24f4598`
and its audit correction at `9911a6b`. No earlier unfinished files were present.
The implementation request remains in the native repository; this branch owns
research and probes only. The reviewed native handoff is
`play-pickups/docs/PICKUPS_IMPLEMENTATION_BLOCKERS.md` at `bcfebff`; the existing
fight and ground-item diagnostics were read without changing that worktree.

**Observed** means original instructions/data at an address below. **Executed**
qualifies an Observed contract checked in `ee_emu.py`, with the stated service
boundaries. **Inferred** is a deduction; **Unknown** requires more evidence.
Nothing here is a PCSX2 or native gameplay result. The executable is pinned to
SHA-256 `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The generated translation under the owner's `local/recomp-out/gen-app/` was
checked against addressed instructions in the executable.
The two new probe tools were introduced at local commit
`cbd59bf01bb5ebd4f8f08d88e7677da2caa3b137`; the resource-selector correction
to that implementation is recorded in section 9 below.

## 1. Roll to flying item: exact construction boundary

**Observed / Executed** (`loot_generateDrops` 0x100d54; call sites 0x101230,
0x1013f4, 0x101560, 0x1018a8): all four item categories allocate `0x248` bytes
and call `PhProp_ctor` 0x155a0c with the following ABI. Failed allocation skips
construction; equipment also skips its later angle draw. Generation's existing
level/difficulty/quality/RNG contract remains [items section 8](spec/items.md).

| Input | Original value/source |
| --- | --- |
| f12 | scale `1.0` |
| a0 | successful pool block |
| a1 | temporary position `(source.x + 0.0, source.y, source.z + zOffset)` |
| a2 | executable string address `0x520030` |
| a3, t0 | model and texture string pointers from resource row `0x3e9ce0 + 16 * index`, offsets 0 and 4 |
| t1 | 64-bit mesh inclusion mask `1` |
| t2 | launch flags `0x441` |
| t3 | generated `0x48`-byte item record pointer |

**Observed / Executed** (`item_getResourceIndex` 0x1083f8): `index` is signed
definition halfword `+0x34`; item flag bit 36 adds `(item.flags >> 11) & 31`.
There are two index calls for the model/texture arguments. Do not replace
these inputs with an item-name-derived model or a generic bag mesh.

**Observed / Executed** (0x1018bc–0x101950): equipment receives one additional
shared draw **after construction**:
`angle + ((draw & 0x3fff) - 0x2000)`. Its two horizontal Prop velocities become
`cos(angle) * 24.0 * throwSpeed` and `sin(angle) * 24.0 * throwSpeed`, followed
by another `PhProp_initPhysics(prop, 0x441)`. Other generated categories keep
the constructor's launch. Named drops at 0x100ba0 instead parse, request
`world_findFreeSpot` with spread 36/radius 12, fall back to the source position
if that fails, then construct 36 units above that position with the same
scale/mask/flags/resource-table selection. Keep free-spot and pool failures
separate.

**Observed / Executed** (`PhProp_ctor` 0x155a0c, base 0x153e54): the constructor
copies all 72 record bytes to `+0x148`, installs vtable `0x511ba8`, sets item
marker `+0x238=1` and interactable bit `0x100000`, and clears `0x800` and
`0x4000`. It thus leaves the excluded debris grid and transient-save category.
Its base constructor consumes one shared draw to initialize `+0x44`; facing,
launch and spin then consume the object's own generator. Resource strings are
copied to `+0x54/+0x64/+0xa4`; `res_find` 0x17365c resolves model `+0x4c` and
texture `+0x50`. No resource pointers may be invented when that service fails.
The requested pool block is zero-filled (`pool_new` 0x14fdb8); preserve that
initial state for fields the constructor does not explicitly assign. The
constructor explicitly clears +0x234 and +0x23a, in addition to the item
marker/scale/body work above.

## 2. Launch, rigid body, settling, and removal

**Observed / Executed** (`Prop_launch` 0x1541a0, flags `0x441`): radius becomes
4, every-frame running is requested, and timer `+0x10e` starts at 180. Two own
draws give initial horizontal velocities `(draw / 65536 - 0.5) * 124`; another
gives vertical velocity `260 + (draw / 65536) * 60`. The base also chooses
facing with an own draw. The later equipment override above replaces the two
horizontal values, not the vertical one. With these flags an item-constructor
sound selection takes one more own draw.

**Observed / Executed** (`PhProp_initPhysics` 0x155110–0x155394): this is a
complete input contract, not permission to replace the solver with a parabola.

| Step | Original input/state |
| --- | --- |
| Bounds | `model_getBounds(model +0x4c, mask +0xe8, six integer outputs)` at 0x179400 |
| Dimensions | Each `(max - min)` after multiplying both bounds by scale `+0x240` |
| Body initialization | `rigidbody_init` 0x1682f0, a0=`prop+0x190`, f12/f13=`1.0/1.0`, f14/f15/f16=three dimensions |
| Position | copy object position to `+0x1a0` |
| Linear momentum | Prop velocities at `+0xfc/+0x100/+0x30` multiplied by float bits `0x3c888888`, to `+0x1bc/+0x1c0/+0x1c4` |
| Angular momentum | three own draws, each `(2 * (draw / 65536) - 1) * k`; k=10 when launch flags contain 0x10 or 0x400, otherwise 2 |
| Selected mesh | `+0x22c` is highest included mesh index, or -1 for mask zero |
| Orientation | `quat_fromMat3(prop+0x1ac, prop+0x110)`, normalize, `rigidbody_updateDerived(prop+0x190)` |
| Coefficient field | `+0x23c=0xbecccccc`; flag 0x800 selects `0xbdcccccc` |
| Item flag bit 17 | adds launch flag 0x1000 internally and zeroes inverse-inertia words `+0x194/+0x198/+0x19c` |

**Observed / Executed** (`rigidbody_init` 0x168350; subsequent orientation
replacement 0x155310–0x155328): body initialization draws the cosmetic seed,
but PhProp replaces its initial quaternion with the object matrix. Preserve
both the draw and overwrite. The probes execute these original functions;
they do not assign a substitute orientation. For `0x441`, full PhProp
construction uses eight own draws; equipment's second physics initialization
uses another three. Those are distinct from the one shared constructor draw.

**Observed** (`PhProp_run` 0x155fcc): model hull points are requested at
0x1561b0 through 0x179320; water, terrain sweeps, collision impulses, integration
and damping participate in flight. At 0x156ad4–0x156b70 it settles when the
signed timer is below -220, or when it is nonpositive and all six momentum
components have absolute value below float bits `0x3e4ccccc`. Positive timer
values decrement and prevent settling that call. The timer is not an item
despawn timer.

**Observed / Executed** (0x156c18–0x156d04): settling allocates `0x190` bytes,
calls `ItemProp_ctor3` 0x1592bc with the record and settled matrix, then queues
the flying object for deletion **even if allocation failed**. Its position and
settled transform must be preserved; creating a resting item immediately at
roll time bypasses this loss boundary. Separately, 0x156d14–0x156d6c removes a
flying object more than 120 below the first alive player's object when the
required player/list pointers exist. Resting ctor3 objects request no run list;
there is no age-based expiry in that constructor. Pickup and world teardown
are separate removal routes (0x159b38; 0x14c460).

## 3. Item resource/bounds services and inventory drops

**Observed / Executed** (0x1590ec and 0x1592bc): both select model/texture
through the same resource index/table and use lump identifier address
`0x5326b0`. Both embed the record, install vtable `0x511c38`, set `0x102000`
and clear `0x1800`; item bit 39 additionally clears `0x3000`.

**Observed / Executed**: ctor2 at 0x1590ec calls the named-launch Prop base
0x153e54, including resource lookup, integer bounds, random facing and launch;
it builds its matrix with facing +0x4000 at 0x159294. Original inventory-drop
call 0x1c47f4 supplies launch flags **zero**, not `0x441`. This object uses
`Prop_run` (ItemProp vtable slot 4 at `0x511c5c` points to 0x154514), not the
PhProp rigid body. Ctor3 at 0x1592bc instead calls 0x153ac0 with supplied
matrix, all-bits mesh mask and Prop flags zero; it does not need a fresh bounds
query during construction. These constructors must not be conflated.

**Observed / Executed** (`model_getBounds` 0x179400): signed mesh count at
model `+0x12`, signed LOD-table count at `+0x26`; the six signed-byte bounds of
each included mesh start after `0x28 + countLOD * (meshCount+1) * 4`, stride
10. Included mask bits select the union. These are integer bounds, not render
vertices converted through an approximate axis-aligned box. Zero selection
retains the original sentinel extrema; do not silently make it a unit cube.
The named-launch base at 0x153f5c–0x153fc8 stores each integer midpoint
`(min+max)>>1` as a float at +0xf0/+0xf4/+0xf8, and midpoint-z minus min-z
at +0x108. Its optional position-centering flag is 0x4, absent from both
loot's `0x441` and inventory drop's zero flags.

**Executed** (`probe_loot_drop_resources.py`): resource names are read from the
executable at run time; model/texture/clip bytes come from the owner disc.
A real parsed descriptor at `0x537430` selected resource row 15. Full PhProp
and ItemProp ctor2 bodies, original resource-index lookup, bounds and rigid-body
initialization ran on those bytes on both seeds. Archive lookup is the authored
service; GPU upload/drawing and terrain physics are not acceptance-tested here.

## 4. Ordinary Chest in a level

**Observed / Executed** (factory 0x159c94, 0x15c068–0x15c170, 0x15c374–0x15c3b0):
allocation is `0x88`; constructor arguments are object, placed position, signed
facing, property-list pointer, variant index. **Correction:** the prefix at
`0x532f70` is checked before the exact names at `0x532f78/0x532f80/0x532f88`.
All four addressed names therefore select index 0 through the first branch;
the name at `0x533130` selects 4. Direct ctor tests of indices 1–3 do not prove
the factory reaches those variants. Properties used only by the later Auto
fallback do not override a class match that has already returned.

**Observed / Executed** (`Chest_ctor` 0x292030): `+0x24` receives the resource
descriptor from `0x501698 + 4*index`; descriptor entries are lump identifier
at +0, generation +4, model name/pointer +8/+0xc, texture +0x10/+0x14,
opening clip +0x18/+0x1c. `GameObject_ctor` resolves stale generations using
0x17365c. Vtable is `0x5118d8`; facing is +0x38, variant +0x59; radius/height
become 22/25; flags gain `0x100018`. Animation state is +0x5c, capacity one,
initially cleared, not an already-playing clip.

**Observed** (0x2920c0–0x292244): the first own draw selects a trap below 2000;
two addressed level-name exceptions clear that result. Property key address
`0x5497c0` can replace the default worth multiplier 1.5, and key `0x5497c8`
forces a trap. Remaining gold is a signed halfword at +0x4c, formed as
`r1 % 100 + trunc((r2 % 24 + 12) * (worth * (save_getAct()+1)) * levelFactor04) + 50`,
with float operations in that order. One level exception and a trap clear
gold. Variant bits 0/1/2/4 for gold 0/<40/<80/otherwise, or 8 for a trap,
feed `model_buildHideMask` 0x179550; its low word is stored at +0x54.
The private constant map preserves the exception/property strings.

**Observed / Executed** (`Chest_interact` 0x292a2c): opening pushes descriptor
`+0x1c` onto animation state +0x5c with flags `0x204`, stamps the frame and
requests every-frame running. Placed descriptor, potion and random-worth
loops each construct PhProps **12** above the Chest, lump identifier
`0x549528`, scale 1, mask 1, flags `0x441`, table-selected model/texture and
the generated record. Successful construction is followed by own-angle
scatter, horizontal speed 24, then physics reinitialization. Constructor call
sites are 0x292bfc / 0x292dac / 0x293028. Pool failure bypasses each launch.
The final generator call at 0x293120 is different: f12..f17 are
`36, 2, 0, 0, 5, 0x3f733333`, with Chest position/facing and null filter/force.
It cannot award Gold through that generator's chance input. Second-use
remaining gold goes through `hud_addGoldFloater`, as the earlier pickup
handoff established.

**Observed / Executed** (`Chest_run` 0x2923a8): the original animation advance
sets completion bit `0x80` in animation status +0x62; only then does the
ordinary non-trapped Chest set opened state 2, run actions and stop running.
Draw 0x29288c uses descriptor model/texture +0xc/+0x14 and the same animation
state. Neither a guessed duration nor an AutoChest animation threshold is a
substitute for this status.

**Executed** (`probe_loot_drop_resources.py`): a real disc placement record,
including its original properties, facing and position, goes through the
original factory and constructor. Descriptor `0x501558` resolves actual disc
model/texture/clip bytes; original relocation, `anim_push`, Chest running,
handle/grid/run-list services and completion execute. The selected clip has
length 59 and reaches opened state 2 after 60 run calls, on both seeds.
Sound, renderer, final loot generator and action-script execution are explicit
recording boundaries. Monster level 22 is an authored roll context, **not** a
captured level-entry value. The selected level, record offset and resource
names are only in ignored `local/loot-drop/private-chest-*.json`.

## 5. Manual item pickup and exact input/query boundary

**Observed / Executed** (`Player_interact` 0x1b2640, 0x1b26bc–0x1b2734): the
query is x/y ±48, **z through z+60**, capacity 256. It is not a 48-radius
sphere. The actual box query includes object extents; 0x1b2794–0x1b27d0
chooses the strictly nearest origin in 3-D among objects with bit `0x100000`.
Prompt slot 13 is called without an input edge. With a nonempty prompt and
status 1, activation tests `pad+0xc & g_btnUse[slot]`, where the binding array
starts at `0x41b9c0`; status 2 uses pressed bit `0x10` instead. Slot 14 is
called at 0x1b2b84 only in simulation mode. Held input alone and the display
call do not activate. This contract does not guess a physical controller
button for a remappable use action.

**Observed / Executed upstream and retained** (`itemprop_tryPickup` 0x154dbc;
PhProp 0x155020; ItemProp 0x159b38): flying and settled items both require
manual interaction. A category bag already at count 63 refuses, and
`load + weight > limit` refuses. Accepted helper calls inventory insertion and
load recalculation. Bit 39 tries player slots in order and removes the object
once if any helper accepts; ordinary items try the chosen slot. The helper's
acceptance is distinct from the inventory routine's single-copy-item refusal.
These rules and the K1 input gate in `Player_run` remain [pickups](pickups.md).

## 6. Gold: source, amount, contact, and actual credit

**Observed / Executed** (`AutoContainer_run` 0x23e430; 0x23f1bc–0x23f428): in
the nonexplosive broken state (+0x13c=1, +0x124 mask 0x1 set and 0x4 clear),
the no-placed-item branch makes an **own** draw; below 24000 it requests
`pool_new(0xc0)`. Only a successful allocation makes the amount draw:
`1 + trunc(float(draw & 3) * level_monsterLevelTimes0_4())`, then calls
`Gold_ctor2` at 0x23f420. Position is the container's position, without the
monster generator's scatter. The constructor still makes its own base
object's shared draw. This path must not be reported as monster-generated
Gold or as an ordinary Chest's second-use award.

**Observed / Executed upstream** (`loot_spawnGold` 0x100974): monster-generator
Gold instead uses shared-seed unit-ball sampling, x/y offsets up to 36,
terrain radius 12, and strict height difference below 6. After ten rejected
tries it uses the original position. It then requests `0xc0` bytes. The
positive-amount guard, rejection draws and allocation loss must survive a port.

**Observed / Executed** (`Gold_ctor2` 0x157668): vtable `0x511a88`, amount
`+0x80`, flags `0x220c`, frame `+0x50`, countdown byte `+0x4c=41`, and
every-frame running. Base-object radius/height remain **24/72**; the constructor
does not derive contact bounds from the drawn coin model. `Gold_run`
0x157b58 decrements the byte while nonzero; animation completion can clear
it early and stop running. The drop sound's frame comparison is start+18.
Countdown completion does not despawn the Gold.

**Observed / Executed** (normal movement 0x1b4f9c → 0x14d4b8; contact
0x14d7b4–0x14d9d4): the query is the mover's radius in x/y and z±1000,
capacity 64 (Creature movement uses 16). The narrow test is
`sqrt(dx*dx + dy*dy) + float(0x3a83126e) <
mover.radius + other.radius`. Player constructor store 0x1a2244 sets radius
12, giving a strict **36-unit horizontal sum**, not a new pickup sphere.
Gold's `0x200` bit prevents push-out. The extra vertical overlap test only
runs when either object's flags contain `0x10`; ordinary player/Gold flags
do not, so the box query remains the vertical gate. Tests with Gold 500
above the fixture player still touch; 1001 above does not reach the callback.
Creature movement's other dispatch is 0x114220. The normal mover excludes
prediction copies before calling the other object; Gold also excludes them.

**Observed / Executed** (`Gold_onTouch` 0x157a9c): requires a player toucher,
no prediction-copy bit, countdown zero and amount nonzero. It requests a
HUD floater for the toucher's slot, clears the amount, then queues deletion.
It does not increment the player's balance. Original grid/handle/query/touch/
delete services were executed together; a second overlap cannot award twice.

**Observed / Executed** (0x1dc268, 0x1dcb80): one of eight floaters stores the
amount, slot and starting frame. At age 43 (`3*age >= 128`) its amount joins
per-player pending gold at `0x86ace8 + 4*slot`. Each tick adds
`(pending+7)>>3` to player record `+0xe4` and subtracts it from pending.
The balance caps at 99,999,999. For a nine-gold fixture starting at 500,
ages 0–42 retain 500; age 43 gives 502 with seven pending, then seven further
ticks reach 509. If all eight floaters are occupied, the add function credits
immediately with the same cap. Projection and cosmetic RNG affect presentation,
not this amount/timing contract.

## 7. Normal new-character equipment

**Observed** (`player_initNewCharacter` 0x1b1d70, 0x1b2034 onward): normal
creation sets record gold `+0xe4` to 500 and calls `player_giveStartingItems`
at 0x1b2400 after statistics setup. This starting balance is not a Gold object
or a pending HUD award.

**Observed / Executed** (`player_giveStartingItems` 0x1acc78, ordinary branch
0x1b14a0–0x1b1ba8): the following table identifies exact descriptor addresses,
without committing item names or decoded descriptor text. Armor group A is
`0x537310/0x537340/0x537370`; group B is
`0x5373a0/0x5373d0/0x537400`. All three armor pieces receive equip requests.

| Record class +0x50 | Armor group | Weapon descriptor(s), in grant/equip order | Resulting category-0 bag count |
| --- | --- | --- | ---: |
| 0 | A | `0x537430` | 1 |
| 1 | A | `0x5374b8` | 1 |
| 2 | A | `0x5374e0` | 1 |
| 3 | A | `0x537458`, `0x537488`; two additional grants from `0x536ac8` | 3 |
| 4 | B | `0x537510` | 1 |
| 5 | A | `0x537540`, `0x537430` | 2 |
| 6 | A | `0x537570` | 1 |

**Observed / Executed**: every class also parses each of
`0x537598/0x5375a8/0x5375c0` once and gives it twice, producing three
category-2 stacks of quantity two. The first descriptor's give flag is zero;
the other two use one. Class 3's two ammunition grants merge into quantity
40. Category-1 bags contain three quantity-one armor records. There are
four explicit equip calls for classes 0/1/2/4/6 and five for 3/5. Parser
variants and byte +0x20 overrides are part of the original branches, not
properties to strip off these descriptors. The probes execute the actual
parser and inventory insertion for every class; equipment/stat/skill callbacks
remain recorded services. Complete equipped-pointer/stat recomputation is not
claimed by that test.

**Observed** (0x1acd28–0x1acd44): the large alternate debug catalog requires
the slot pad's held mask 2 **and** debug-cheats byte `0x4f8ee0` nonzero.
It is not the normal starting inventory. Its switches/model-specific catalog
was not exhaustively audited here. The private, locally generated named
mapping is `local/loot-drop/private-starting-equipment.json`.

## 8. Four native blockers: research supplied versus remaining work

| Blocker from bcfebff | New addressed evidence | Remaining boundary |
| --- | --- | --- |
| Full loot PhProp construction/physics inputs | Sections 1–2; all four generator call sites, extra equipment initialization, real disc-backed constructor and rigid-body/bounds execution | Native must bind model hull, terrain, water and physics services and preserve tick/seed/allocation order; a live flight/settle path was not captured |
| Live Chest construction and animation binding | Section 4; factory precedence correction; real placed record through original constructor and real opening clip to completion; all three placed-loot constructor paths checked separately | One disc placement/interpreter case is not a loaded PCSX2/native level; traps, every level variant and rendered interaction remain unverified |
| ItemProp resource/model bounds | Section 3; resource selector/table, named resource service, integer bounds format; actual resource row through full ctor2; supplied-matrix ctor3 separately checked | Native resource lifetime/GPU binding and inventory-drop/world-registry/save/reload integration still need implementation and acceptance tests |
| Gold movement/contact dispatch | Section 6; radius 24/72, player radius 12, original real-grid query → normal movement → touch → HUD credit/deletion | Native needs a real source actor and movement scheduler; this branch does not turn a zero-Gold-chance enemy into a source or implement that client |

**Inferred:** these contracts supply the previously missing call/service
boundaries; they are suitable inputs to a native implementation review.
**Unknown:** whether the implementation passes its real-level acceptance
gates. Keep its refusals until the corresponding services actually work.

## 9. Verification and private evidence

**Executed, all passed:**

| Check | Seed 20973 | Seed 7 |
| --- | ---: | ---: |
| New bounded original-code probes | 1,172/1,172 | 1,172/1,172 |
| Disc-backed Chest opening and PhProp/ItemProp construction | PASS | PASS |
| Existing `difftest_pickups.py` | 17/17 | 17/17 |
| Existing `difftest_items.py --quick -k loot --jobs 1` | 5/5 properties | 5/5 properties |

**Executed:** `python3 -m unittest discover -s tools -p 'test_*.py'` passed
652/652 tests. The serial verification runner exited zero after the final
suite. `git diff --check` passed; only the named research worktree was edited.
No native build, runtime acceptance suite or push was performed.

**Executed:** `tools/difftest_loot_drop.py` checks 1,172 bounded cases per
seed (20973 and 7). This includes 1,024 original generator executions covering
all four constructor sites, synthetic Chest placed properties and allocation
failure, five direct Chest variants, actual factory precedence, full-queue
Gold credit/cap, both movement dispatches, original grid contact/deletion,
manual input edges, settle/allocation loss/culling, seven normal grant
sequences and seven real parser/inventory sequences. External services and
synthetic choices are declared in each probe. The seeded generator tests use
synthetic item generators; they complement, rather than replace, the existing
item-generation differential comparison.

**Executed:** `tools/probe_loot_drop_resources.py` runs the disc-backed case
on both seeds. Reproduction, from this worktree (repeat for seed 7;
`RTA_DISC` points to the owner's local ISO):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loot_drop.py SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_loot_drop_resources.py SLUS_209.73 --iso "$RTA_DISC" --seed 20973 --private-report local/loot-drop/private-chest-20973.json
```

The tools only read owner inputs. Generated names, decoded placement data and
resource mappings go under this worktree's ignored `local/loot-drop/`, never
into tracked fixtures. Logs: `seed-{20973,7}.log`, `resources-{20973,7}.log`,
`pickups-{20973,7}.log`, `items-{20973,7}.log`, `unit-tests.log`.
The constant-string map is `private-constants.json`; no decoded names are
required to reproduce the public address-only probes.
The checked PCSX2 prerequisite state is `pcsx2-prerequisites.json`.

**Observed / Executed — LOOT-01 correction, 2026-10-25:** the resource probe
now reads its placement-member identifier from executable address `0x53f010`.
Its standalone-resource directory comes from the parent of the selected
archive path in the runtime ISO index. Neither selector is a decoded literal
in the probe. Decoded selector mappings stay in the ignored report
`local/loot-drop/loot-01/private-runtime-selection.json`.

**Executed:** the identifier scan covers both complete added probe sources,
this complete handoff, and every added line in `FINDINGS.md`, `docs/pickups.md`
and `docs/objects.md` since `9911a6b`. It found **zero matches** against 8,720
case-folded nonpublic identifier candidates from the private mappings,
filename-shaped executable strings, all 994 ISO file paths, 120 GOB archive
directories and 941 LMP member directories. The user-supplied executable
identity and Gold contract label are the only public-term exclusions;
decoded member, file and directory selectors are not excluded. Negative
controls detect both audited selectors in the pre-fix probe at `7cb3620`
(lines 67 and 99), and neither in the corrected source. The helper, full
corpus, mappings and scan results remain under ignored
`local/loot-drop/loot-01/`; `identifier-scan.json` records scope and counts.

**Executed, correction rerun:** all four checks in the table above passed
again on seeds 20973 and 7, and the required unit suite passed 652/652 tests.
Both disc-probe JSON results exactly match their saved pre-correction reports.
Fresh logs, private disc reports and the nine zero exit codes in
`verification.json` are under ignored `local/loot-drop/loot-01/`.

**Unknown / not captured:** original PCSX2 flight, natural pickup, visuals,
live source-container placement and level save/reload. The installed PCSX2
application was found, but the standard user profile's BIOS directory and
the inspected isolated research profile's BIOS directory were empty. This
is a statement about those checked routes, not an exhaustive absence claim.
No other agent's running emulator was controlled, stopped or reused. No new
PCSX2 pictures exist. The real-disc interpreter checks above do not substitute
for that missing capture. Continue with an owner-provided usable PCSX2 BIOS/
profile, then record one repeatable source → flight/settle → pickup → balance/
inventory sequence and save/reload before upgrading runtime claims.
