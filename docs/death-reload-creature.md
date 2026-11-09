# Creature load: linked synthetic effects, round 2

2026-10-27; research base `0e3afdb8ce3cdf79746f535d8a2654db37c9e97b`,
branch `t3/research-death-reload`. Additive probe:
`tools/difftest_death_reload_creature.py`. Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

**Executed:** 180 synthetic load cases and one expected resource refusal per
seed, in the unchanged `tools/ee_emu.py`. No stubs, instruction patches,
automatic memory mapping, resource files, or constructor execution. Existing
reference APIs, vectors, emulator, and round-1 probe remain unchanged.
These findings extend the Creature row in [round 1](death-reload.md); they do
not establish a complete world reload or a playable death/reload journey.

## Addressed findings

### R2-C1: the callback called “motion” in round 1

**Observed / Executed:** the dispatch at `0x116a48–0x116a58` selects vtable
offset `+0xe0`, with argument 1. With the supplied base implementation this
executes the death handler at `0x10beb8`, not a movement routine. The probe
supplies that actual function address in a synthetic table and executes its
instructions and reached callees. It is called only after a matching animation
name entry is found. Negative string handles and unmatched names skip it.

**Executed:** nonzero motion witnesses at object `+0xbc/+0xc0/+0xc4`,
`+0xf8/+0xfc/+0x100`, and `+0x308/+0x30c` retain their supplied values, as
checked by comparison of the entire 0x400-byte object. Stopping the run list
does not establish that velocities, destinations, or pending movement are
cleared. `0x113c48` and animation root decoding `0x16e468` are explicitly
checked as unvisited by these loads.

**Unknown:** subclass overrides of `+0xe0`, actual movement after loading,
collision resolution, subsequent corpse ticks, and rendered pose.

### R2-C2: original variant/model effects

**Observed / Executed:** `0x116950–0x116984` restores variant `+0xe8` and HP
`+0x228`, then dispatches to `0x11a668`. The actual model getter `0x3c2738`
and mask routine `0x179550` execute. The fixture tests a null model, a model
without variant processing, and a model with two authored variant records,
with input variants 0, 1, 2 and 3. Null preserves `+0x220`; the other cases
replace it with independently specified expected 64-bit masks. The initial
model mask and records are synthetic, not copied model data.

**Unknown:** constructing the class definition, resolving model resources,
and deriving valid model/variant combinations from shipped assets. A valid
model pointer is a supplied prerequisite, not a proved constructor effect.

### R2-C3: live/dead world membership and registry effects

**Observed / Executed:** `0x116984–0x1169b0` treats reconstructed HP equal to
zero or below as dead, sets state `+0x232` to 20, ORs object flags with
`0x2009`, and calls `0x14f290`. That routine executes `0x1a1868` on the
existing run-list link. Both nodes are returned to the synthetic free pool,
the object's `+4` head becomes zero, and neighboring links remain correct.
Positive HP retains the existing run membership. An initially absent run
link is also covered.

**Executed:** setup itself uses original grid insertion `0x14f120`, active
run registration `0x14f248`, name insertion `0x14bce0`, paired-node linking
`0x1a1738`, and, for flag-2 controls, always-draw insertion `0x14edd8`.
The subject is between two peers in the active list and, normally, the
spatial cell. Three synthetic names are registered. The original name query
`0x14f498 -> 0x14bf58` still returns each corresponding object after the load,
and the whole name table is unchanged. Spatial/off-grid and always-draw
memberships also remain linked.

**Executed:** original box query `0x14a928` returns all three in-grid objects
with exclude mask `0` at `0x4039b8`. With mask `8`, it omits a loaded dead
subject and retains both peers; a live subject remains. Flag-2 subjects were
placed off-grid by the original setup and are absent from both box queries.
Each query checks exact result order, terminator, return pointer, and an
untouched output suffix. This demonstrates these registry/query operations
on the supplied world; it is not a whole-world or terrain-collision test.

**Inferred:** run-list removal alone cannot be treated as removal from all
world registries, and exclusion from this spatial query depends on its mask.

### R2-C4: animation and cache ownership really execute

**Observed / Executed:** the string resolver `0x14f688` uses the supplied
synthetic table at `0x5f8704`; negative handles return null. The loader's scan
at `0x1169cc–0x116a04` runs the original string comparison `0x3b8534`, skips
a nonmatching first resource name, and either matches the second entry or
reaches the zero terminator. No string-resolution callback remains.

**Observed / Executed:** a matched nonnull clip with capacity one runs reset
`0x1707b0`, push `0x170838`, and end `0x170bc8`. The old count is reset and
one cell is installed at `object+0x11c`: authored clip pointer, decoder slot
zero, weight/life 1, weight/life rates zero, time equal to synthetic clip
length, flags 4, and sound cursor zero. The prior decoder's owner at
`slot+0x14` is cleared. End detaches the old pose, clears its owner at
`pose+0x610`, and the loader adds state flag `0x80` at `object+0x11a`.
With supplied state flags `0x20`, the result is `0xa4`.

**Executed:** zero capacity and a matching name with null clip both leave
count zero after reset; no new cell or decoder release occurs. End still
detaches the pose, state flags become `0xa0`, and the death handler still
executes. Negative handles and positive unmatched names preserve the entire
supplied animation state and its cache owners, and skip the death handler.
Null pose/decoder controls cover the no-owner branches.

**Observed / Executed:** the pushed flags are 4, so end does not take its
`0x800` root-decoding branch at `0x170c14–0x170c20`. No root-motion decoder
success is inferred from reaching the clip's final time.

**Unknown:** pose reconstruction/drawing, cache allocation, real clip format
and resource compatibility, animation advancement, events, audio, and root
motion. The clip length is supplied; the clip is not a usable shipped asset.

### R2-C5: death-handler effects and deferred deletion

**Observed / Executed:** `0x10bee8–0x10bef4` clears `0x08c00000` from the
64-bit flags at `+0xa8`, preserving unrelated high bits. Later loader stores
at `0x116ab0–0x116b34` OR the five saved masks back into that word. Independent
expectations check the ordering, including bits restored after the handler
clears them. Absent saved bits do not otherwise clear preexisting flags.

**Executed:** the actual property getter `0x14f4c0` returns absent because
`+0x2c` is supplied null. The handler's argument 1 skips the optional item
creation branch. Global `0x4f7120` is supplied zero, avoiding the competitive
score branch. The actual audio-selection path `0x1192f8 -> 0x10dbe0` returns
no selection because `+0x34` is supplied null. Script dispatch `0x1ed694`,
audio enqueue `0x211338`, and score service `0x3056cc` are checked unvisited;
none is replaced with a success answer.

**Observed / Executed:** with object flag 2 and a matched animation entry,
`0x10bf60–0x10bf7c` adds flag `0x4000`, calls end again, and executes deferred
delete `0x14f200` and the actual pair-link operation `0x1a1738`. The subject
joins list `0x5db4e0`; its name, off-grid and always-draw links still exist
at return. Negative/unmatched animation controls do not join the delete list.

**Unknown:** deletion-list flushing, destructor execution, script-bearing
properties, item spawning, competitive state, and class-specific audio.
Being queued for deletion is not proof the object was destroyed.

### R2-C6: original type comparison and optional-word eligibility

**Observed / Executed:** every dead load reaches the type dispatch at
`0x116a64–0x116a98`, the original getters `0x3c2608`/`0x3c4658`, and equality
`0x3b1250`. Synthetic cached descriptors cover distinct names, the same
descriptor, and distinct descriptors with equal names. Equality sets byte
`+0x28` to 70; inequality preserves its initial 9. These are equality
branches, not a demonstrated inheritance/subclass test. Lazy type-descriptor
initialization remains outside this fixture.

**Observed / Executed:** when saved bit 6 is set, `0x116b60–0x116ba8` always
consumes the extra word. Applying it additionally requires existing signed
halfword `+0x312 != -1`, object flag `0x20` set, and flag `0x40` clear.
The matrix independently exercises all three rejection conditions with live,
zero-HP and negative-HP inputs. Accepted input clears only the low byte at
`+0x310`, stores the word truncated to `+0x312`, and executes `0x1a1698`
on the target head `+0x234`, followed by explicitly zeroing that head.
Values -1, 0, 5 and `0x10005` cover signed, zero and truncation results.
Absent saved bit 6 preserves the supplied timer and target link.

**Executed:** target setup links the subject and two peers to a fourth
synthetic object. Removal unlinks both target nodes, preserves the peers,
and returns exactly two nodes to the free pool. Empty target controls also
execute. After each load, all 64 supplied pool nodes are accounted for once
across the live lists and free chain, with checked backlinks, partner links,
no cycles and no live/free overlap. All three peer objects are compared
byte-for-byte with their pre-load state.

### R2-C7: fail-closed missing resource control

**Executed refusal:** a separate no-stub control supplies unmapped model
pointer `0x0bad0000`. Load stops at `0x179550`, reading two bytes at
`0x0bad0010`, with `MemoryFault`. The test rejects another fault location,
normal completion, or any later stop/death-handler execution. Variant and
HP writes have already occurred; this is **not** an atomic rollback claim.
The pool and object list heads remain unchanged at this boundary.

**Unknown:** full constructor/resource/runtime completion. This refusal
demonstrates that a missing resource cannot silently count as a successful
load. It does not describe a valid resource-loading fallback.

## Supplied state and remaining boundaries

**Executed fixture contract:** each run starts in a fresh `EE` instance with
the pinned executable. Four zeroed 0x400-byte objects, a 64-node pool, empty
world heads/grids/name tables, and all synthetic buffers are explicitly
allocated/supplied. Original setup links three objects, registers their
synthetic names, and establishes target associations. No factory or class
constructor runs. Position is zero, radius 2, height 4, with no terrain.

The subject has a synthetic vtable containing actual addressed functions
with zero this-adjustments, a supplied definition/model/clip, cached synthetic
type names, null properties and class-name pointer, state 7, HP 19 and max HP
chosen from 64/128/160. Model flags, initial show mask, two variant records,
flag words, timer/team bytes, and nonzero motion witnesses are supplied.
Animation supplies capacity/count, one prior cell, a pose owner and a decoder
owner (or null-owner controls); capacity-zero controls retain an unused cell
as a preservation witness. Clip length is selected from 17/73/127. These
values test the addressed effects; they are not a reconstruction of a complete
constructor's invariants or a real class combination.

**Remaining stubs: none.** The test rejects nonempty hooks, automatic call
stubbing, patches, automatic memory mapping, or recorded stubbed calls.
The omitted constructor, cache allocation, resource acquisition, scheduler,
scripts, terrain, runtime services and renderer are bypassed by supplied
state or unselected branches, not implemented by the fixture. Their success
remains **Unknown**. Names and registries are synthetic. No public service
was contacted and no running-game observation is claimed.

**Inferred:** the executed boundaries justify a more precise local restore
contract, including list/cache effects and the animation-dependent handler.
They do not resolve the client `blocked_death_reload` refusal or justify an
end-to-end reload acceptance claim.

## Reproduction and counts

From this worktree:

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_creature.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_creature.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

The standalone probe removes `tools/` from the import path, preloads stdlib
`unittest` and `dis`, then restores it before importing the unchanged emulator.
The executable pin is checked before execution; each original call has a
30,000-instruction limit. Expected output uses authored whole-object edits,
fixed mask results, list membership/order, pool accounting, owner fields,
query results and exact payload consumption, not the save writer or an
existing reference model. Original-PC reachability checks verify the selected
and skipped callees, independently of the memory comparisons.

Per seed: 96 HP/animation/eligibility/type cases; 24 model/variant cases;
36 saved/preexisting-flag cases; 16 flag-2/capacity-zero cases; six optional
value/equal-name cases; two absent-link/cache-owner cases. Total: **180 loads,
one expected refusal, zero stubs**. Seeds vary only supplied max HP and clip
length; the branch matrix is deterministic. Success output is counts-only:
`PASS cases=180 refusals=1 stubs=0`.

**Executed verification:** both seeds passed; repository discovery passed
652 tests (5.261 seconds). Private retained results:
`local/r2-creature-verified20973.log`, `local/r2-creature-verified7.log`, and
`local/r2-creature-unit-tests.log`. No commit was made; the parent owns review
and commit of these two additive files.

Private inspection excerpts and execution logs are new regular files named
`local/r2-creature*`. Existing private input links are read only. No raw
instruction listing, executable bytes, or extracted resource strings are
included in these authored tracked files.
