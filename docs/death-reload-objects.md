# Death reload object effects: round 2

STATUS: MORE

Research base `0e3afdb8ce3cdf79746f535d8a2654db37c9e97b`, branch
`t3/research-death-reload`, 2026-10-27. Additive evidence for
[round 1](death-reload.md), implemented in
[`difftest_death_reload_objects.py`](../tools/difftest_death_reload_objects.py).
Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

**Observed** means addressed original instruction/data inspection. **Executed**
means original-function execution in `tools/ee_emu.py` against independently
authored synthetic assertions. **Inferred** is an integration consequence, and
**Unknown** remains unsupported. Nothing here was run in a complete game.
JumpGate and other portal-specific behavior are outside this file's claims.

## Executed effects and addressed round-1 gaps

| Finding | Evidence and result |
|---|---|
| OBJ2-1: actual factory and world membership | **Observed / Executed**, `trigger_factory` and `container_records`: 0x14e808 dispatches through 0x5f76f4 to the original factory 0x159c94, allocator 0x14fdb8, constructors, and original virtual slot 8. Trigger constructor 0x1ecdf4, Chest constructor 0x292030 and AutoChest constructor 0x23ad18 all execute. Three saved records become three distinct objects alongside an existing anchor. Tests inspect ordered grid lists and both directions of their paired handle links, class pointers, restored fields and run-list membership. Neither factory nor constructor nor list service is a callback. |
| OBJ2-2: Trigger construction and load | **Observed / Executed**, `trigger_factory`, `container_records`, `level_pipeline`: 0x1ecdf4 constructs zero-width/height synthetic bounds, sets flags 3, links to grid A and the first 15-frame bucket, and initializes +0x68 to -1. Loader 0x1ecef4 consumes five bytes, restores +0x64/+0x60 and preserves this membership. Loading does not execute the Trigger script or move it to the active list. The standalone control uses restored byte 255; the integrated loader uses byte 1. |
| OBJ2-3: Chest/AutoChest construction, cache and animation | **Observed / Executed**, `container_records`: ten mixed-record scenarios cover closed/open and gold 0, 1, 32767, 32768, 65535. Original class/cache setter 0x14f5f0, resource lookup 0x17365c and directory search 0x171de4 execute where reached. The synthetic AutoChest model has one part with explicit bounds; resulting base dimensions remain 12/60 and draw extents become 12/12. Loaders 0x2922cc/0x23b0b4 restore payload, execute animation start/end 0x170838/0x170bc8 and leave an opened clip at time 73, flags 0x204. Open with signed gold <=0 clears 0x100000; positive gold preserves it. No active run registration is added. AutoChest's 32-bit mask 0xa1234567 becomes 64-bit 0xffffffffa1234567; asserting only its low word misses this sign extension. Its constructor-zero +0xe8/+0xec remain zero. |
| OBJ2-4: ItemProp original alternate constructor and resources | **Observed / Executed**, `item_loads`: original constructor 0x1592bc executes item type lookup 0x1083f8, Prop constructor 0x153ac0, base construction and actual grid relinks 0x14f028. It receives an explicit synthetic item record, definition and matrix. Original loader 0x159758 executes nested Prop load 0x158f04, definition decoding, string-table resolution 0x14f688, actual resource lookup/directory search, quaternion conversion and final matrix setter 0x163b30. Eight scenarios cover both bit-39 branches, masks 8/10 and two grid cells. Exact item bytes, pointers, mask, identity-facing transform, grid A membership, empty corresponding grid B cell and unchanged active list are asserted. Final translation comes from base pose, replacing suffix (1,-2,3). Flags become 0x103009 or 0x100009 from this constructor state. |
| OBJ2-5: original door run links and geometry | **Observed / Executed**, `door_loads`: six open/closed scenarios run loaders 0x28ae74, 0x28b1b8, 0x28df24 twice each. Base construction is original; derived piece index/flags and prior 15-frame registration are explicitly supplied. Original 0x14f248 and handle unlink/link 0x1a1868/0x1a1738 move open swing/rolling doors to the active list without duplicates or losing the anchor. Closed cases and secret doors retain their prior bucket. Original collision/height/pose services 0x182b00/0x182b74/0x182c98 execute. Secret-open surface Z becomes -1184 quarter units; rolling load clears terrain bit 2, restores height 123 and leaves pose unchanged. Swing covers zero/half-turn angles and signed direction -1. Grid links remain intact and source piece data remains unchanged. |
| OBJ2-6: nonportal gate state effects | **Observed / Executed**, `gate_loads`: original gate vtable 0x513b68 has load 0x23ceb8, state setter 0x23d680 and passability setter 0x23d7ac. Twelve scenarios supply two constructor-state entries, optional clips, both passability flags, piece participation and an existing run link. Eight valid-state scenarios execute virtual state/passability dispatch, model masking, optional animation start/end and actual world geometry updates. Passable state sets object bit 1, terrain bit 2 and translates the surface from Z=16 to -1008 quarter units; impassable state clears those bits and restores Z=16. With a clip, elapsed counter becomes 74 and track time 73; clip flags are 6/3 according to the supplied state entry. Run/grid membership stays unchanged. |
| OBJ2-7: integrated nonempty saved section | **Observed / Executed**, `level_pipeline`: original level script/object loader 0x217978 performs saved-directory lookup, source copies, automap unpack, object restoration, empty-decal reset and filtered base-level loading. Original resource cache lookup 0x173558 and directory lookup 0x171de4 return a synthetic already-relocated archive. Three saved objects reconstruct through original factory/constructors/loaders. A nonempty base record is rejected by original filter 0x15d9c8; no duplicate Trigger appears. Rank becomes 3, loaded flag clears, null-script setter clears 0x86b270 and the source snapshot remains byte-for-byte unchanged. Scripts are explicitly disabled; the archive contains no script. This replaces round 1's recorded object-loading boundary for these synthetic classes only. |

**Observed / Executed invalid-state control**, OBJ2-6: 0x23cee4 writes the saved
word to +0x178 *before* calling the state setter. State 2 with supplied count 2
is rejected by 0x23d698–0x23d6a4, but the stored word remains 2. Four controls
assert unchanged timer, masks, animation, terrain and run/grid links. This is
not a valid reconstructed state. Negative states and damaged inputs are
**Unknown**; no blanket state-validation claim follows from the upper bound.

## Supplied state, stubs, and exact limits

**Executed fixture prerequisites** for all 38 scenarios:

- Original pool initializer 0x14fcd8 and handle initializer 0x1a17d0 execute.
  The fixture supplies the random seed and list cursor, and uses initially
  zero list heads from the executable image. It does not execute world task
  scheduling or boot. An original base constructor creates an anchor and
  original 0x14f248 registers it before each object test.
- 0x44fdc8 points to a synthetic relocated world with one piece, one terrain
  element and one surface. The piece has position (0,0,16) in quarter units,
  an explicit direction vector, element height 123 and mask 0x12. This is
  nonempty geometry, not a shipped world's archive or collision-query proof.
- Resource fixtures supply already-relocated cache entries, directory
  pointers, one-part model bounds, opaque texture pointers and a clip of
  length 73. The class-definition generation is current (9). Synthetic
  string substitutions change data tokens/suffixes only in interpreter memory;
  no executable instructions are patched. Resource misses are not silently
  assigned pointers.
- Container constructors use empty properties except the synthetic property
  selecting the automatic container route. Act index 2, offline scale 1 and
  a synthetic current destination are supplied. Item tests use definition
  index 7, a zeroed type-0 definition and an unprotected constructor item;
  loader facing 0xc000 is supplied after alternate construction. Matrix and
  saved-payload expectations are authored independently of save functions.
- Door derived constructors are **not** executed: piece index 0, flags
  0x100000 and prior 15-frame registration are supplied after original base
  construction. Gate derived constructor 0x242e7c is **not** executed:
  original vtable, model, track capacity 1, two state/clip/flag entries,
  moving-piece flag and index 0 are supplied after base construction.
  Gate timer/mask sentinels are deliberate pre-load controls.
- Integrated loading uses a synthetic saved-directory entry and a relocated
  archive; map input is zeroed, decal count is zero, script is absent and
  script entry points are disabled through 0x4f8b58. Object sections and the
  base-level record list are nonempty. Automap and empty-decal routines execute,
  but nonempty decals, script behavior and detailed automap parity are not
  asserted by this object-focused test.

**Executed stub inventory: none.** All probes assert empty `hooks` and
`patches`; there is no `stub`, `follow` whitelist, instruction replacement,
resource callback or successful constructor substitute. Memory setup above
is supplied state, not evidence that boot, file loading, arbitrary constructors
or resource relocation can produce that state.

**Executed failure boundaries**, `unresolved_boundaries`, two per seed:

1. Original resource lookup 0x17365c with an uncached synthetic archive reaches
   0x173558, then stops at `SYSCALL` 0x352e14, register v1=124. The interpreter
   has no modeled kernel service. No return is substituted and no object is
   fabricated.
2. Original factory 0x159c94 selects primary ItemProp constructor 0x159458;
   original descriptor path 0x1069b8 is entered. Without the resource/definition
   prerequisites established for that route, execution reaches the same kernel
   stop before loader 0x159758. **This failure is not transactional:** a partial
   object already exists in grid B with flags 0x1809. The test checks this
   partial state and rejects successful completion. It does not claim failure
   before all mutations, valid descriptor resolution or a usable item.

## What a native save_loadWorld still needs

**Inferred from OBJ2-1 through OBJ2-7:** saved bytes alone are insufficient.
The native operation needs a relocated world/piece mapping, initialized
object and handle pools, a registered class factory, constructor property
semantics, current class/resource caches, string-table and definition-index
bindings, valid state/clip tables, and actual list/grid registration. It must
retain the checkpoint's source data, reconstruct eligible saved objects and
then apply the base-level filter. It must restore state through each class's
effects, including clip completion and gate/door collision/pose changes.
Returning a recorded factory pointer or recording an update call proves none
of those list or geometry effects.

**Unknown / still refused:** whole-game resource loading; primary ItemProp
factory descriptor/resource completion; general door/gate constructors and
state definitions; arbitrary item rotations or facing; real textures/rendered
poses; Trigger script execution and nonzero trigger bounds; trap fuses or
subsequent container/gate ticks; invalid checkpoint recovery, pool exhaustion,
deleted-record policies, nonempty delete-list flushing, terrain queries and a
continuous death-to-playable journey. Synthetic cache hits do not establish
real asset availability. The native `blocked_death_reload` refusal remains enforced.

## Verification

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_objects.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_objects.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
git diff --check
```

**Executed:** each standalone seed prints only `PASS 38 cases; 2 expected
boundaries`. The 38 scenarios include four invalid gate-state controls and
66 total original object-loader invocations, including repeated door loads.
Item payload bytes and the second item position vary by seed; other state
matrices are deterministic, with seeded constructor randomness. The two
expected kernel traps are verified refusals, not successful reloads.
Unit discovery: 652 tests passed. Private logs and addressed inspection
scratch files are `local/r2-objects*`; no tracked raw game data or disassembly.
Existing reference APIs, vectors and emulator files remain unchanged.
