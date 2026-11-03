# Exit trigger and level-request handoff, round three

Verified 2026-11-02 against the read-only US v2.00 executable, SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
**Observed** describes addressed original code; **Executed** additionally means
an original body ran in `tools/ee_emu.py` on constructed inputs against an
independently authored expectation. **Inferred** is composition, not an integrated
run. **Unknown** is deliberately unsupported. No running-game result is claimed.

## Walk-in Trigger

**Observed / Executed:** the real constructor `0x1ecdf4` reads serialized `w`,
`h`, and **`t`**, not `script`. With position (0,0), width 10 and height 10 it
constructs the inclusive rectangle [0,10] by [-10,0], installs table `0x511600`,
sets flags 3 and initial found slot -1. Supplying a contradictory `script`
property does not change the selected `t`. This corrects the property wording
in `95760d9:docs/exits-walkin.md:14`; the earlier `18e1a34:docs/level-flow.md:451`
already describes `t` correctly. Test: `tools/difftest_exit_walkin.py:34`.

**Observed / Executed:** first-run discovery `0x1ecf64–0x1ed050` sets +0x61,
queries the rectangle with z bounds -12000/+12000 and limit 128 using the real
`world_collectObjectsInBox` `0x14a928`, then selects the first result whose real
RTTI matches TriggerParams (`0x3c3788`, comparison `0x3b1250`). It writes
Trigger+0x6c and Params+0x4c backpointers. Eight three-candidate type assignments
compare full query order against unchanged `ref_objects.World`, including no
match. A second run does not repeat the lookup even after no match. Test:
`tools/difftest_exit_walkin.py:64`.

**Observed / Executed:** occupancy `0x1ed054–0x1ed0e4` tests player objects in
slot order with original shape predicate `0x1ed238`. Two inside players select
slot 1 before slot 2 even with extreme, different z coordinates. When an inside
player is found during recall, +0x68 has **already** become -1; inside/delay and
script context remain unchanged. Recall does not suppress a no-occupant exit.

**Observed / Executed:** at an edge, the original `0x14dcc8` dispatches linked
actions first using the inherited active player and linked selected object.
Only afterward does Trigger bind itself at `0x4039f8`; an on edge sets active
slot `0x4d8ae4` to the found slot, or 0 on a forced-on exit. Off edges retain the
previous active slot. The second override, `offOnly`, wins over `onOnly`.
The off identifier has the literal `not` prefix. Selected context clears after
scripts. With either override and `timeout=2`, delay becomes 8 and occupancy
clears; without overrides timeout is ignored (`0x1ed198–0x1ed20c`). Thirty-two
edge combinations compare ordered names, contexts and state:
`tools/difftest_exit_walkin.py:92`. Script bodies return a supplied 1; previous
pinned vectors retain the zero-result/needScriptHit cases.

**Observed / Executed:** save `0x1ecf18` and load `0x1ecef4` transfer exactly
four delay bytes and one occupancy byte, with buffer tail preservation.
`TriggerParams_setActive` `0x1ecdcc` writes linked delay 0 for enabled, -1 for
disabled. Ten delay/occupancy pairs compare independently authored payloads,
then both rearm arguments (`tools/difftest_exit_walkin.py:129`).

**Partial:** Trigger construction, grid query, RTTI, shape, real properties,
action dispatcher and serializers execute. Discovery candidates are original
base objects assigned original type-table pointers; this does not establish
all derived constructors or all possible world competitors. Script bodies are
callbacks; existing Rig support stubs remain. The 15-list scheduler is prior
addressed evidence (`95760d9:docs/exits-walkin.md:14`), not a live frame schedule
measured by this extension. **Unknown:** execution of actual level scripts and
an uninterrupted walk-in-to-load transition.

## Keyed PushTrigger and host selection

**Observed / Executed:** host selection `0x13e5a0–0x13e610` returns the first
qualifying slot below player count `0x4d8ae0`. Offline, the first slot qualifies.
Online, the slot must also be below `0x4027c4` and have zero signed inactive byte
at `0x5c3d0d + 0x44e0*slot`. If none qualifies, it returns 0, including a
zero-player state. The oracle compares 800 count/prefix/mask combinations;
this fallback is not proof slot 0 is a connected host. Test:
`tools/difftest_exit_handoff.py:57`; reference `tools/ref_exit_handoff.py:6`.

**Observed / Executed:** prompt `0x1eca94–0x1ecc70` first checks online
`netHostOnly`. If the supplied player differs from that real selector, keys
are not evaluated. Missing `netHostLockMessage` clears the prompt; its presence
enables the fixed localization key at `0x53e2e0`, with host-name setup arguments
`(0, host, 0x4d8af0 + 0x4c30*host, 8)` at `0x1ecb2c`.
The property value itself is not used as the localization key.

**Observed / Executed:** accepted host/offline paths evaluate repeated `key`
properties in order, stopping at the first zero. Failure selects `lockMessage`;
success selects `message` and returns 1 even if message is absent and the
output is empty. Thus usable return and nonempty text are independent gates
for physical use. Active and selected context globals are preserved by the
prompt itself for the supplied nonmutating predicates. Real property lookup
reads lowercase serialized keys; localization, text formatting and script
predicate bodies are supplied. The 768 cases vary slot, host, network,
host-only, message presence and six predicate vectors; see
`tools/difftest_exit_handoff.py:94` and `tools/ref_exit_handoff.py:12`.

**Inferred composition:** combine this prompt contract with original
`Player_interact` `0x1b2640`, its active-slot write `0x1b2b70`, and use dispatch
`0x1b2b84` documented in `docs/exits-r3-physical.md:61`; accepted dispatch then
reaches actions `0x1ecc70` / `0x14dcc8` and immediate once destruction documented
in `docs/exits-r3-push-lifecycle.md:11`. These are separately executed boundaries,
not one uninterrupted keyed-exit trace. **Unknown:** BLOOD1's actual key script
results, item/quest effects, host transport authority and whole script execution.
The string `blood1_keyed_exit_host_action` names the consumer requirement; it
is not evidence that those level-specific conditions have been established.

## What reaches the level-change path

**Observed / Executed:** `newWorld` `0x143dd0` and `simpleNewWorld` `0x143e70`
call the original network gate `0x143d04` unless post-action byte `0x4f8698`
is nonzero. Offline or active slot -1 permits the request without changing a
cooldown. Online with a valid supplied slot, nonzero cooldown at player record
+0x4bca and alive count `0x4f8420 >= 2` refuses; otherwise cooldown becomes 600.
The 144 combinations compare rejection without buffer/menu changes, and allowed
calls to `net_closeLocalMenus(0)` before the pending request. Local identity,
notification presentation and menu closure are supplied services; transport,
vehicle ejection and actual menu effects are not executed.

**Observed / Executed:** `script_setNextWorld` `0x1472c4–0x1473b0` copies the
qualified destination string to `0x41b6d0`. It scans the selected object's
properties at +0x2c for exact lowercase `orientation=`; the **last** matching
property wins, parsed as decimal and truncated to a byte at `0x41b720`.
Absent selected object or matching property gives 255. Uppercase `Orientation`
is not a match here. `simpleNewWorld` writes 255 regardless of selected object.
Seven deterministic helper cases execute without any stubbed callees, in
addition to the handler matrix (`tools/difftest_exit_handoff.py:157`).

**Observed / Executed:** both allowed and rejected requests preserve named
entrance `0x4f8468` and post-action buffer `0x86fa80`. The original `setEntrance`
command `0x142a94` writes the former; `postAction` `0x143ee4` through setter
`0x1eda9c` writes the latter. Six long/short/empty synthetic-name cases verify
the separate buffers and unmodified tails. Argument decode/conversion
`0x1414a8` / `0x141650` are stubs in command tests: this establishes handlers
on supplied decoded strings, not VM parsing of real scripts. Copies, property
scan and integer parsing execute originally. No pending buffer contains a
computed destination coordinate or selected-object pointer.

**Observed in prior evidence, not executed as a whole here:** the consumer is
`mainloop_loadRequestedWorld` `0x320edc`: save old state, handle act changes,
retain previous qualified level, split and clear pending level, copy/reset
orientation, load destination and place players. Source:
`18e1a34:docs/level-flow.md:383–401`, retained unchanged in `local/pinned-exits/`.
**Inferred:** the client can model a request with destination, orientation,
retained named entrance and post-action state; it must separately implement
consumer sequencing and persistence. **Unknown:** whole-load timing, atomicity,
complete living/dead derived-object state, geometry and constructor RNG.

## Portal path and remaining acceptance

**Observed / Executed in existing round-three tests:** opener `0x27da24`
retains exact fixed-destination pointer or null and installs actual tasks.
State-5 task `0x27dd74` advances entry counters through 180; entry 181 copies
fixed destination or selected list slot to `0x41b6d0`, writes orientation 255,
and enters state 6. Travel remains live through the request; terminal states
6/7 are tested separately. Evidence: `docs/exits-r3-gate-lifecycle.md:75`,
`:106`, `:121`; original countdown vectors are unchanged at
`95760d9:tools/difftest_exits.py:340`.

**Observed / Executed in retained pinned tests:** destination Portal construction
`0x27c694` uses real `world_findFreeSpot` `0x14acf8` on supplied terrain/object
queries, writes per-slot position/facing and rank 3 when travel is active and
fixed destination is null. Source: `95760d9:docs/exits-walkin.md:153–182`.
**Unknown:** full menu states 0–4, rendered confirmation, destination world
construction and final live arrival. No generic destination-name heuristic or
fabricated coordinate closes this boundary.

**Inferred implementation order:** consume Trigger records and their saved
state; dispatch linked/script contexts faithfully; use the complete ordered
physical query and real key/host predicates for PushTrigger; execute actual
actions, then destruction and record persistence; carry the four request
fields above; finally integrate Portal menu, travel lifetime and destination
construction. **Unknown until integrated validation:** removal of
`walk_in_exit_trigger` and `blood1_keyed_exit_host_action`. No client files or
refusals were changed by this research task.

## Verification

Run from the named research worktree; original input is only read via
`local/SLUS_209.73`. Both new tools verify its hash, bound entry calls at 100,000
instructions, avoid original instruction patches and automatic mapping, and
print only counts on success or failure. `unittest` is preloaded before tools
can shadow standard-library `dis`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_walkin --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_walkin --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_handoff --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_handoff --seed 7
```

Per seed: walk-in **90 entry calls / 309 assertions**, 8 initial lookups,
32 edge cases and 10 save/rearm cases; handoff **1,725 entry calls / 8,617
assertions**, 800 host cases, 768 prompts, 144 requests, 7 direct orientation
cases and 6 side-buffer cases. All pass with zero failures. Original nested
callees are not counted as entry calls. Retained round-three/pinned regressions
and full unittest results are recorded in `work/cursor-report.md`.
