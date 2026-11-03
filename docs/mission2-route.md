# Mission 2 route, dialog and completion execution

2026-10-27. **STATUS: MORE.** This extends audited base `047adfe` without
changing existing reference APIs or vectors. It closes record identity,
call containment, zero-offset destination decoding and several original
dialog/VM/native gates. It does **not** establish a playable mission:
physical interaction, real inventory delivery/pickup and completed scene
loads remain Unknown. No client code was changed.

All script addresses below are **code-relative**. Native addresses refer
to the hash-checked US v2.00 executable. Level ordinals 0–3 mean the existing
ordered tuple in `ref_mission2.LEVELS`. Private strings, script/dialog bytes,
properties and positions are supplied at runtime; they are not new tracked
fixtures. **Observed** means parsed/asserted location or relationship;
**Executed** means original instructions on constructed state in `ee_emu`,
not a running game. No console, Play! or native client journey ran here.

## Record identity and containment

**Observed**, `difftest_mission2_links.py`: each relevant record has exactly
one matching property, not a union across records. Exact record/entry pairs
and their multiplicities are checked. Instruction decoding locates every
argument push, byte-count push, native call and cleanup inside the expected
half-open entry interval. Every procedure start must have a unique public
entry. Malformed tables, ambiguous properties and unsupported layouts refuse.

| Level | Record | Role | Entry interval | Native call cell |
|---:|---:|---|---|---:|
| 0 | 72 | NPC dialog | `[0x000,0x054)` | `0x03c` |
| 0 | 73 | NPC dialog | `[0x094,0x0e8)` | `0x0d0` |
| 0 | 263 | PushTrigger | `[0x128,0x16c)` | `0x154` |
| 1 | 139 | PushTrigger | `[0x000,0x044)` | `0x02c` |
| 1 | 140 | PushTrigger | `[0x044,0x088)` | `0x070` |
| 2 | 38 | PushTrigger | `[0x000,0x044)` | `0x02c` |
| 2 | 102 | PushTrigger | `[0x044,0x088)` | `0x070` |
| 3 | 31 | PushTrigger | `[0x044,0x088)` | `0x070` |
| 3 | 30 | Boss death | `[0x000,0x044)` | `0x02c` |
| 3 | 58 | Trigger wrapper | `[0x150,0x194)` | `0x17c` |
| 3 | 59 | Trigger wrapper | `[0x194,0x1d8)` | `0x1c0` |
| 3 | 57 | Portal gate | `[0x110,0x150)` | `0x13c` |

Level-0 Portal record 71 has zero script properties. The death/drop
properties coexist on level-3 record 30; its drop argument equals the
turn-in item at level-0 call `0x480`. The 35 contained calls include the
start, offer, turn-in, deferred grant and boss/portal wrappers. The original
record loader `0x14e808` consumes all 699 records / 22,156 bytes; its callback
records fields and does not construct the level.

## Exit requests: zero is a string offset

**Executed**, `difftest_mission2_travel.py`: original loader/binding
`0x13e8f8`/`0x141310`, entry dispatcher `0x1ed694`, VM `0x13ecf8`, native
dispatcher `0x141050`, command `0x143dd0`, address/string conversion
`0x1414a8`/`0x141650`, gate `0x143d04` and writer `0x1472c4` run.

The argument 0 in both middle scripts is **AMX data offset zero**, which
contains a valid string. The old interpretation as a null destination was
incorrect. The executed pending-name route is:

| Source | Entry / call | Destination |
|---|---|---|
| `innovat1` | `0x128` / `0x154` | `inmine1` |
| `inmine1` | `0x000` / `0x02c` | `innovat1` |
| `inmine1` | `0x044` / `0x070` | `inmine2` |
| `inmine2` | `0x000` / `0x02c` | `inmine1` |
| `inmine2` | `0x044` / `0x070` | `innovat2` |
| `innovat2` | `0x044` / `0x070` | `inmine2` |

Original object action dispatcher `0x14dcc8` also runs on the linked
record's property list before entering its script. Seven controls per exit
check offline, online, cooldown refusal, one living
player, active slot -1, post-action bypass and a different active slot.
An allowed ordinary online call sets that slot's cooldown to 600. Refusal
preserves pending name and orientation; post-action and slot -1 bypass the
cooldown. Actual source-record properties supply orientation. The physical
Player-to-trigger/collision path and full load do not execute in these cases.

## Dialog selection and objective effects

**Observed and Executed**, `difftest_mission2_dialog.py`: both unchanged
dialog blobs are read from the first level archive. Their file identities
are checked against the NPC `startDialog` arguments at `0x03c`/`0x0d0`;
the actual native lookup request is checked against those runtime names.
The authored controls are `(1,1)` and `(1,0)`. Resource return and speaker
lookup remain controlled; the NPC constructor/use loop is not executed.

Native messages at `0x22ee2c` select nodes through `0x230c74` and the actual
script dispatcher/VM. The test does not substitute script predicate returns.
The first dialog has five nodes; the second has four. Each has one choice,
with no separate choice condition. Their addressed selection contract is:

| Dialog/node | Predicate entry | Choice action | Continuation |
|---|---:|---:|---|
| 0/0 | `0x16c` | none | close |
| 0/1 | `0x1dc` | none | node 2 |
| 0/2 | `0x1dc` | `0x2e0` | close |
| 0/3 | `0x360` | `0x418` | close |
| 0/4 | `0x4f0` | none | close |
| 1/0 | `0x5b0` | none | close |
| 1/1 | `0x810` | `0x910` | close |
| 1/2 | `0x990` | `0x418` | close |
| 1/3 | `0xa44` | none | close |

Dialog 0 offers/accepts in zero alignment; dialog 1 in nonzero alignment.
In the matching alignment, no objective item plus finish-variable 0 selects
the offer; possession selects turn-in, including when finish is already 1.
No item plus finish 1 selects the final non-action node. No item plus finish
-1 or 2 falls back to node 0 when every predicate fails. Opposite alignment
selects node 0. Possession sums all player slots through native handler
`0x145590`; inventory counts themselves are controlled services.

The offer tests the finish key (pool `0x4c`), not the conversation key
(pool `0x74`) written by the offer. Original offers `0x2e0`/`0x910` call
journal addition `0x1433c8` → `0x1d386c` then variable setter `0x143540`.
They use the same title and distinct bodies. Original turn-in `0x418`:

1. Writes finish = 1 through `0x143540` / `0x1ed854`.
2. Runs item-removal handler `0x14598c` for all player slots.
3. Removes the journal title through `0x143448` / `0x1d3968`.
4. Registers entry `0xc98` through `0x144160` / `0x1ed52c`.

The native selector follows dialog 0's node 1 → node 2 before the offer
action. Recall/menu admission and unfinished reveal/text/blend suppress
actions; positive follow-ups execute them. **Confirm does not recheck the
node predicate:** changing controlled possession from one to zero after
selection still runs turn-in and queues the reward, with no inventory
removal when search reports no item. Whether that change can occur during
live dialog is Unknown. Neither a new possession check nor idempotent reward
semantics should be inferred from the existing path.

## Deferred completion and auxiliary branches

**Executed**, `difftest_mission2_route.py`, against unchanged `ref_amx` and
`ref_natives`: all compared calls require no unexpected implicit stubs and
compare result, external call sequence, written bytes, VM state/memory and
shared RNG. Four synthetic living players are used; these are not imported
retail records. The independent addressed predicate model is
`ref_mission2_route.py`.

The 756-state matrix covers fourteen predicates, both alignments, item
counts 0/1/2 and finish/conversation values -1/0/1. It distinguishes equality
to zero, equality to one and general truthiness. Additional tests execute
both NPC request entries, busy-dialog suppression, notification wrappers,
offer/turn-in sequences and first/repeat intro paths.

Start `0xb00` sets mission-2 availability, writes two distinct variables
with 1/2 and posts `0xbe0`. Native post dispatcher `0x1edac0` clears its
buffer before calling the entry and restores the in-post flag afterward.
Entry `0xbe0` requests the cutscene only when its guard is zero, then sets
the guard. Actual cutscene completion is a controlled external boundary.

With empty deferred counters, turn-in leaves mission completion clear.
The first `0x1ed5a0` call promotes the queued name; the second executes
`0xc98`. The original item-give handler `0x145a88` runs, followed by
`grantMission(2)` at script `0xd00` → native `0x1420a4` → `0x1bf770`.
Completion bit 1 becomes set in all four records at the active difficulty.
A third task call has no queued reward and emits no lower-service calls.
Duplicate-item cleanup requests one removal for a living slot whose
controlled count exceeds one; the reward body is not a possession-gated
transaction. Descriptor parsing, insertion, weight/load recalculation,
search and removal remain stubs: this proves the completion write and
request ordering, **not actual reward delivery**.

The auxiliary exchanges at `0x790`/`0x1278` are executed standalone without
fixing their two-argument packet to three-argument `givePlayerItem`. In this
top-level call the extra read comes from the saved AMX frame and is zero;
it is not an authored third argument or a promise about nested invocation.
Their live reachability is Unknown. Existing APIs/vectors are unchanged.

## Boss, death and portal gate

**Executed:** Trigger wrapper `0x150` calls `0x21c`. First visit requests
the cutscene, sets its seen variable and posts `0x32c`. That post enables
save inhibition (`0x1473b4`) then calls `0x39c`, which sets creature flag 0
through `0x144714` / `0x1445fc` on a synthetic named creature. Repeat visit
calls `0x39c` directly; it **does not set save inhibition**. Physical Trigger
entry and the actual loaded boss identity/AI remain Unknown here.

Original `Creature_onDeath` `0x10beb8` runs with the authored boss record's
properties installed. Native property lookup `0x14f4c0` selects wrapper
`0x000` → `0x46c`. The latter sets the portal key to 1 at script `0x4a0`
and clears save inhibition at `0x4cc`. This occurs **before** the drop call
at native `0x10bf54`. Quiet death still runs the death script but suppresses
the named-item call. Eight controls independently remove the death/drop
properties and toggle quiet. The compared death model covers drawn,
non-PvP creatures; boss music and `loot_spawnNamedItem` `0x100ba0` are
stubbed. A loot request is not an instantiated or picked-up item.

Portal entry `0x110` returns the signed gate byte. Wrapper `0x194` emits
its message only when it is zero. Entry `0x088` returns the OR of one
variable being nonzero and another being zero. The last level's start
queues `0x4e4`; that entry requeues itself and tests duplicate possessions
on its 61st execution, not its 60th. Native deferred promotion/consumption
and the 60/61/62 boundaries are compared.

## Portal request and the remaining load boundary

**Executed**, `difftest_mission2_travel.py`: prompt `0x27d7a0` reads the
actual Portal property and executes entry `0x110`. False gate, variant
byte `+0x4f` and an existing menu task suppress access. Discovery byte
`+0x4d` and destination insertion `0x27db60` are checked. Discovery occurs
before the other-player distance refusal; the threshold is squared distance
9216: an axial distance 96 passes; the immediately larger float and 97/100
fail. The prompt itself never
writes the pending level.

Interaction `0x27d754`, mutex `0x22fc2c`, menu setup `0x27da24` and task
insertion `0x19e4a0` register run/draw functions `0x27dd74`/`0x27e2d0` at
priority 20. Offline busy dialog suppresses registration; online busy
dialog does not. The menu selects a runtime destination-list row or an
explicit runtime pointer. It does not imply an unconditional return to
one fixed level or a completed mission.

Eight controlled sequences drive the original prompt, interaction and menu:
false gate, idle input, cancel, same-row confirm, valid confirm and combined
cancel/confirm, including local-pause guard variants. Cancel wins;
current-row confirm stays in selection. Valid
confirm eventually copies the selected name to `0x41b6d0` and orientation
255 to `0x41b720`. State 5 tests its **input counter** before increment:
180 still waits; 181 accepts. Cancellation restores offline pause and
removes tasks. These functions are called explicitly by the harness; the
physical Player interaction and scheduler loop are not executed.

Four separately prepared same-act requests execute `0x320edc`, crossing
old/new synthetic entrance suffixes. It preserves previous level, splits current
level/sub-name, clears the request, saves orientation at `0x41b7c1`, resets
`0x41b720` to 254 and reaches `0x321148` → loader `0x1e55c0`. A throwing
entry hook stops **before any loader instruction**; it is not a successful
load stub. Serialization, act lookup, pending character selection and audio
fade are controlled. Original full loading, I/O, object/resource creation,
player placement, saved-world restoration and arrival remain Unknown.

## Reproduction and remaining implementation gates

All commands run from this worktree; inputs stay in ignored `local/`.
Preload stdlib unittest before importing tools to avoid `tools/dis.py`:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_links.py",run_name="__main__")' local/SLUS_209.73 local
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_route.py",run_name="__main__")' local/SLUS_209.73 local --seed 20973
python3 tools/difftest_mission2_dialog.py local/SLUS_209.73 local --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_travel.py",run_name="__main__")' local/SLUS_209.73 local --seed 20973
python3 -m unittest discover -s tools -p 'test_*.py'
```

Repeat the three seeded new tools with seed 7. The dialog comparison reads
the unchanged model/harness from local Git object
`334578d310179760daff20ea6098353a54958df8`; a checkout without that object
must obtain the reviewed research dependency before that tool can run.
It does not fetch anything automatically or contact a server.

Results: strict links 12, one unlinked Portal, 35 bounded calls; 28 authored
negative/positive unit tests and 222 private malformed-input controls.
Per seed: route 798 states / 1,007 original comparisons; dialog 96
selector/action cases, 432 direct predicate checks and 14 additional
controls; travel 91 controls. The unchanged original mission difftest also
passes both seeds with 699 records, 22,156 bytes and 660 factory selections.
The complete analysis suite passes 680 tests. These counts describe
research assertions, not mission completion or play coverage.

The client can use the addressed mappings, string-offset semantics,
dialog/action selection and queue timing without inventing destinations
or granting completion at enqueue time. Before widening its current
refusals it still needs original/native comparisons of actual bag effects
and boss-item pickup, physical NPC/Trigger/Portal dispatch, loaded boss
identity/combat, full transition/arrival with carried records, and save/load
through those exits. This research provides no mission-3 unlock rule and
does not resolve cross-act inventory handoffs. The subsequent
[2026-11-02 offer and hub-request tests](mission2-offer-hub.md) establish
bounded hub dialog/menu requests, with physical use and full arrival still Unknown.
