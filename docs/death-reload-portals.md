# Portal reload effects, round 2

STATUS: MORE

Research base `0e3afdb8ce3cdf79746f535d8a2654db37c9e97b`, 2026-10-27.
Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The labels below distinguish addressed instruction observations from synthetic
execution in `tools/ee_emu.py`. Identifiers A, B and C are synthetic aliases;
no asset or factory-name literals are reproduced. No full constructor, running
game, renderer or continuous death/reload execution is claimed.

## R2-P1: three distinct restore families

**Observed:** the record loader at 0x14e808 obtains an object from the selected
factory at 0x14e9a0, then dispatches its slot 8 at 0x14e9c4–0x14e9e8 when
header bit 0 is set. These addressed paths distinguish the following families:

| Synthetic alias | Factory call sites and constructed size | Vtable | Slot 8 / slot 18 |
|---|---|---|---|
| A, two factory selectors | 0x15cec8 / 0x15cf08 -> 0x27c694, 0x164 bytes | 0x50dbe8 | 0x27d998, two-byte loader; no shared state-setter path |
| B, one factory selector | 0x15a0e4 -> 0x24388c, 0x498 bytes | 0x5136d8 | 0x23ceb8 / 0x243c70 |
| C, two factory selectors | 0x15a1dc -> 0x243cd0, 0x448 bytes | 0x513630 | 0x23ceb8 / 0x243e20 |

**Observed:** B and C share a four-byte state loader, which stores the word
at +0x178 *before* calling their different slot-18 functions. Both use slot 19
at 0x23d7ac. B's constructor installs its table at 0x243924; C does so at
0x243d14. A installs its table at 0x27c768. B/C must not be treated as A.

**Executed:** private `local/r2-portals-classification.py` checks three vtables
and calls the original filter 0x15d9c8 with the five addressed selector-data
pointers: 0x532928, 0x532968, 0x532978, 0x533748, 0x533758. All five return 0,
with no stubbed calls. This private probe uses original selector data only in
interpreter memory and emits counts, never its strings.

**Inferred:** these selectors are eligible for the saved-record path rather
than the filter-only reconstruction pass, subject to the separate object flags,
record retention and capacity rules. **Unknown:** this is not an exhaustive
inventory of every object that scripts may use as a portal. No occurrence in
a shipped level, complete factory execution or successful save retention is
established by the filter result.

## R2-P2: A's light, asset, animation and update effects

**Executed:** 168 scenarios call 0x27d998 twice each, covering saved active
bytes 0/1/255, both initially linked/unlinked light states, seven positions,
and four clip conditions. The complete 0x164-byte object is compared against
independent expected bytes after each call. The following services run as
original instructions, with no recording or return-value stubs:

- Light insertion 0x148bc8, including unlinking existing neighbors and inserting
  at the selected cell head. The 90-by-90 grid at 0x5d34d8 uses 256-unit cells,
  bias 11520, and overflow list 0x5db368. Tests include both horizontal bounds,
  a vertical overflow, and fractional coordinates. Coordinates are converted to
  integers before the cell division, as observed at 0x148bf8–0x148c24.
- Asset lookup 0x17365c, including original string comparison 0x3b8534 and
  archive search 0x171de4. Synthetic fixtures cover a cached standalone entry,
  a relocated sorted three-entry archive, and an absent member of a present
  archive. A decoy cache entry exercises skipping a nonmatching archive.
- Clip start 0x170838 at object +0xd8. A successful empty one-track buffer installs
  one clip with flags 3, time 0, unit speed/weight and zero auxiliary state.
  A null lookup produces no track. A preexisting full one-track buffer retains
  its clip, flags and time 19; loading does not reset that buffer first.
- Update registration 0x14f248 and handle insertion/removal 0x1a1738/0x1a1868.
  The object moves ahead of a peer on the active list at 0x5db3a8. All pair
  pointers, backlinks, object identities and free-pool counts are checked.
  Unlink/reallocation swaps the roles of the same two nodes; internal pointer
  identity is not an idempotence promise. Repeated loads create no duplicate
  list members and do not consume additional free nodes in these fixtures.

**Observed / Executed:** the zero-active branch at 0x27d9d0 skips both the
light and clip calls, but still schedules updates at 0x27da00. It does **not**
unlink an already present light or clear an existing track. Tests preserve both
linked and unlinked supplied states. Nonzero active values link the light even
when the synthetic archive has no matching clip. Thus successful state-byte
restoration alone does not establish complete visual restoration.

**Observed:** A's constructor initializes a one-track capacity at 0x27c750,
places the light 84 units above its base position, links then unlinks it at
0x27c7d0 / 0x27c864, and conditionally links it again at 0x27c95c depending on
+0x4f. The tests supply both resulting link conditions; they do not execute
that constructor, its properties, arrival branch or resource formatting.

## R2-P3: separate light-grid and object-grid controls

**Executed:** six additional light controls run 0x148bc8, relink 0x14a528,
and unlink 0x14a4f0. They move between populated cells and overflow, check the
old and new neighbors and backlinks, and prove that 0x14a528 leaves an
unlinked light unlinked. This differs from the unconditional insertion entry
used by A's loader.

**Executed:** twelve object-grid controls execute first-link 0x14f120 and
relink 0x14f028 with synthetic base objects. Grid A at 0x5db4f0 and grid B at
0x5e95f0 use 120-by-120 cells, bias 15360 and 256-unit cells; out-of-range
positions use 0x5f76f0. Both flag-0x800 branches, lower/upper corners, overflow
and an existing peer are covered. Relink preserves the object's handle pair
and free-pool count. A's own load cases additionally prove that the supplied
object-grid membership remains unchanged while the run list changes.

**Unknown:** these are grid/list effects, not a terrain collision query, a
whole-world registry rebuild or scheduler execution. First-link controls use
flags 0 and 0x800; the flag-2 initial off-grid branch is outside this matrix.
A does not call object-grid insertion from its state loader; that membership
must already have been supplied by construction.

## R2-P4: B/C restore different bounded effects

**Executed:** 96 scenarios execute 0x23ceb8 through the original B/C vtables,
including 0x243c70 or 0x243e20, shared setter 0x23d680, model-mask calculation
0x179550, clip start/end 0x170838/0x170bc8, and passability 0x23d7ac. Inputs
cross two classes, state 0/1/2, looping/nonlooping, present/absent clips,
ordinary/piece-backed state, and default/perturbed inner-effect state.
The complete 0x498-byte fixture, including C's trailing guard region, is
compared with independently authored expectations.

**Observed / Executed** for states 0 and 1 with supplied state count 2:

- The current animation count is cleared, then an available clip is installed
  and moved to its synthetic end time 73. Track flags are 3 for looping and 6
  otherwise. Existing aggregate flags remain ORed; this is not a clean reset
  of every animation field. A missing clip leaves count zero and stale track
  storage untouched. The state counter becomes 74 with a clip, zero without.
- The visited-state mask at +0x180 becomes 0 or 3. A synthetic model table
  independently predicts hidden masks 0 or 2 at +0xc8; the original model-mask
  helper executes, including its per-state add/remove masks.
- Object flag 1 is cleared/set by passability. In piece-backed fixtures the
  original collision setter 0x182b00 and pose setter 0x182c98 also run. For the
  supplied single piece/element/surface, state 0 enables collision and yields
  surface Z 16; state 1 disables it and translates the surface to Z -1008,
  representing 16 - 256*4. This condition is supplied class state, not evidence
  that a shipped portal actually binds a moving piece.
- B's extra setter at 0x243c84–0x243cbc sets inner visibility/counter to 0/0
  and scale to 0.01 for state 0; state 1 sets visibility/counter to 1/180 and
  retains the supplied scale (0.01 or 0.5 in controls). C's setter at
  0x243e20 simply calls the shared setter and leaves the trailing guard intact.
- The supplied helper object at +0x198/+0x1a8, including its +0xfc enabled
  word, remains byte-for-byte unchanged. State action flags 0x18 remain intact.
  No action execution or update-list registration is supplied by these loads;
  the previously supplied run-list membership and free count stay unchanged.

**Observed / Executed:** for out-of-range state 2 with count 2, the loader
still stores 2 at +0x178, while the setter's upper-bound check at
0x23d698–0x23d6a0 skips shared reconstruction. B's extra 0/1 switch also leaves
its fields unchanged. This is an invalid-state control, not a repaired record.
**Unknown:** negative indices, large state counts/masks, malformed pointers,
real model hide tables and animation evaluation are not validated.

**Observed:** B's later update at 0x243b48 first calls its inherited update;
0x243b98–0x243bc4 reads helper +0xfc before growing the small inner scale.
**Unknown:** the later update, helper activation, particle generation, sound,
interaction, script actions and rendered pose are not executed by this probe.
The unchanged helper and retained scale explicitly prevent claiming the whole
portal effect has been reconstructed from its four-byte payload.

## R2-P5: bounded original record dispatch

**Executed:** six scenarios run 0x14e808 with one saved synthetic record,
header bit 0 set, an empty property list, and A/B/C state 0/1. Its actual
virtual loaders and the effects above execute. Expected checks include 40-byte
record consumption, relocated class pointer, header relocation flag, slot-8
payload fields, animation/light/passability effects and preserved grid links.

**Stub boundary:** the only returning stub in these six cases is a synthetic
factory callback. It asserts the synthetic class token, position, angle and
empty properties, then returns an already prepared object. Grid and run-list
membership were installed earlier by original helpers. The delete list is
supplied empty; its original iterator runs, but no destructor is exercised.
This is record-to-load dispatch, not original factory/constructor integration.

## R2-P6: explicit refusal controls and supplied state

**Executed refusal:** with A's archive cache empty, an exception-only hook
stops at resource-load entry 0x173558. No resource pointer or success answer is
invented. The saved bytes and light list have already changed at that boundary;
the update list has not. This proves the probe refuses unsupported resource
loading, not that the original load is transactional or refuses before mutation.

**Executed refusal:** an empty synthetic handle pool makes original update
registration reach a write to address zero at 0x1a1780. The interpreter raises
`MemoryFault`; the test requires that precise address/PC and does not count it
as a successful update. Ordinary tests supply 32 nodes of 20 bytes each and
validate their remaining free chain. Real resource/pool exhaustion recovery is
**Unknown**.

**Supplied state in every ordinary fixture:** zeroed synthetic allocations,
empty grid/list heads, a finite handle pool, base position/flags, original
vtable pointers and any already registered memberships. No full class
constructor runs. A additionally receives light color/radius data and +84 Z,
a synthetic resource name/cache, one-track capacity, optional existing track
and the linked/unlinked light state. Linking preserves the supplied photometric
fields; it does not derive them from the two saved bytes. B/C additionally
receive two state definitions, property flags, a synthetic model hide table,
a preexisting track at time 19 with aggregate flags 0x89, a synthetic helper
whose enabled word is 1, and synthetic moving-piece arrays when applicable.
B's inner state has both default and deliberately perturbed controls. C's extra
bytes after its 0x448-byte object are test guards, not claimed object fields.

**Stub inventory:** no returning stubs in the 168 A, 96 B/C, twelve object-grid
or six light-grid scenarios. Six record scenarios each use the one factory
stub above. The cache-miss refusal uses an exception-only hook, and the empty
pool refusal uses no stub. Entry-observation hooks only collect addresses;
no instruction words, original files, emulator behavior, reference APIs or
existing vectors are changed. The static lookup token at 0x547ee0 is replaced
with synthetic text only in each interpreter instance's data memory.

## Reproduction and acceptance boundary

Run from the assigned research worktree with the existing read-only private
executable input. The standalone script preloads stdlib imports before exposing
`tools/`, preventing its `dis.py` from shadowing stdlib `dis`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_portals.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_portals.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 local/r2-portals-classification.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

**Executed:** each seed reports 290 scenarios: 168 A loads (each executed
twice), twelve object-grid, six light-grid, 96 B/C, six record-dispatch and
two refusal controls. Only A's first saved byte varies with the seed; a second
seed does not add structural coverage. Private classification reports three
tables/five filters. Existing analysis-tool tests pass: 652 tests. New probe
success output contains counts only. Missing/wrong executable pins and disabled
assertions exit unsuccessfully; unsupported execution does not become a pass.

**Unknown / acceptance limit:** real resources and class construction, complete
world reload, B/C helper and update effects, A's travel/arrival behavior, rendered
lights/pose, capacity thinning, terrain queries after construction and a
continuous death-to-playable journey remain unproved. These findings narrow
round 1's callback boundaries; they do not resolve the native death/reload
refusal gate. No client code or acceptance policy is changed.
