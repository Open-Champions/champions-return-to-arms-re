# Exit dispatch and gate arrival (SLUS-20973 v2.00)

2026-10-23. Research branch `t3/research-exits-walkin`, pinned to research main
`034d0c0`. **Observed** means an instruction or data reference was read at the
given address. **Executed** means the original function ran in `tools/ee_emu.py`
against synthetic memory and was compared with `tools/ref_exits.py` by
`tools/difftest_exits.py`. No Play! or native-client playthrough was run here.
The executable SHA-256 guard is `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

## 1. Scheduling and shapes

| Field / action | Evidence and meaning |
|---|---|
| `Trigger_ctor` 0x1ecdf4 | **Observed**: reads integer `w` and `h`, forms horizontal rectangle in +0x4c..+0x58 around object x/y (0x1ece44–0x1ececc), stores `script` at +0x5c, flags 3 and calls `obj_runEvery15` 0x14f330 (0x1ececc). This is a slow-list object: its own run is not called on every simulation frame. `runObjects` chooses one of 15 lists per frame; see `docs/spec/object-system.md` 5.1. |
| `Trigger_contains` 0x1ed238 | **Observed, Executed**: slot 17 tests the candidate's x/y at +0x10/+0x14 against inclusive min/max. z, player radius, speed and facing are not read. The 25 boundary pairs were compared with the reference on each seed. |
| `Trigger_run` 0x1ecf3c | **Observed, Executed**: at first run, +0x61 is set and a box query 0x14a928 looks for a `TriggerParams` object by type; the first match is linked at +0x6c, with its +0x4c backpointer set (0x1ecf64–0x1ed050). The difftest starts after this one-time lookup; its linked and unlinked cases run real trigger code with lookup already marked complete. |
| `PushTrigger_ctor` 0x1ec900 | **Observed**: flags are ORed with `0x10000b` at 0x1ec95c–0x1ec96c, marking an interactable object. It has no rectangle walk-in path. Prompt and use are virtual slots 13 and 14 reached through `Player_interact` (see `docs/script.md` P1). |

**Observed** `Trigger_run` 0x1ed028–0x1ed0e0: a nonzero signed delay
at +0x64 is decremented and the run returns; `-1` therefore continues to
decrease and remains disabled unless another writer sets it to zero. With zero
delay, +0x68 becomes `-1`, then slots `0 .. g_numPlayers-1` are checked in
order through `g_players[slot].obj` and virtual slot 17. The first object
inside wins. A found player with nonzero recall countdown 0x41b51d exits
early, before changing +0x68 or the inside flag. Otherwise the found slot
is written to +0x68; a missing player leaves `-1`. Entry/exit compares the
current occupancy with +0x60 (previous occupancy) at 0x1ed0e0. Thus a move
that begins and ends between this trigger's 15-list turns cannot be seen by
this routine (**Inferred** from scheduling and sampling).

## 2. Dispatch and rearming order

**Observed, Executed** `Trigger_run` 0x1ed0e0–0x1ed210, on an occupancy edge:

1. When linked `TriggerParams` exists, read `onOnly` then `offOnly` from it.
   `onOnly` forces the selected action state on; `offOnly` is read second and
   wins if both are nonzero. Call `obj_runActionScripts` 0x14dcc8 on that
   linked object with the selected state. This occurs before the Trigger's
   own script.
2. If selected on, set current script object 0x4039f8 to the Trigger, set
   active player 0x4d8ae4 to the found slot, and run the script at +0x5c
   with `script_runByName` 0x1ed694. On a forced-on *exit*, the found-slot
   local remains zero, so active player is slot 0 (0x1ed0bc–0x1ed168).
   If selected off, run `not` + script name instead. Then clear current
   script object. `script_runByName` invokes the script interpreter; the
   test stubs it and checks only the name, order and returned result.
3. Write the actual occupancy to +0x60. **Observed** at 0x1ed198:
   if neither `onOnly` nor `offOnly` was nonzero, return here. This skips
   `timeout` and `needScriptHit` even when those properties are present.
4. Otherwise, if `timeout` is nonzero and delay was not `-1`, set delay to
   `timeout * 4` and clear +0x60 (0x1ed1a0–0x1ed20c). If delay was `-1`,
   clear +0x60 and keep the delay. If `timeout` is zero, test
   `needScriptHit`: a nonzero value with a zero script result clears
   +0x60 but leaves delay alone; all other cases set delay to `-1` and
   clear +0x60 (0x1ed1e4–0x1ed20c). This branch ordering was corrected
   against the second difftest seed, rather than inferred from property names.

**Observed** `TriggerParams_setActive` 0x1ecdcc is virtual slot 3: when
linked, argument nonzero writes zero delay, argument zero writes `-1`.
`script trigger(name, arg)` 0x142264 reaches slot 3 (see `docs/script.md`).
The trigger's save/load slots 8/9 at 0x1ecef4 / 0x1ecf18 transfer the
four delay bytes and inside byte. A native reimplementation must retain
those five bytes across level state saves.

**Observed, Executed** `PushTrigger_prompt` 0x1eca94–0x1ecc70 evaluates
`key` property scripts in property order, stopping on the first zero. It
returns unusable with `lockMessage` on failure, or usable with `message`
after all pass. The offline key/message paths were compared. In a network
game, `netHostOnly` and `netHostLockMessage` are checked first
(0x1eca98–0x1ecb90); that branch was not dynamically compared here.
**Observed** `PushTrigger_interact` 0x1ecc70–0x1ecd64 requires an `action`
property, refuses `shop` when 0x1ec140 finds an alive player with flag
0x800000, then calls `obj_runActionScripts` with `!offOnly`. `once`
subsequently calls the object's virtual delete slot. There is no evidence
that walking through a PushTrigger runs `action`; proximity/use is the
dispatch path.

## 3. Gate discovery, menu and arrival

**Observed, Executed** `JumpGate_interactPrompt` 0x27d7a0–0x27d974:
hurt gates (+0x4f) return no prompt. Ordinary gates refuse while the
`jumpgate` task is running or the optional `script` predicate returns zero.
The first valid prompt sets found byte +0x4d and calls
`jumpgate_addCurrentLevel` 0x27db60 before testing destination count.
Exactly one destination shows `JumpGateVirgin` and remains unusable. With
more destinations, every *other* alive player must have squared 3D distance
at most `96²` from the gate (0x27d8a0–0x27d93c); otherwise the prompt is
`JumpGateNeedPlayers`. Success shows `JumpGate` and returns usable. Prompt
can be reached from both simulation `Player_run` and local `Player_draw`
(`docs/script.md` P1), so discovery is not confined to an interaction press.
The difftest stubs discovery to append once, then compares the prompt result
and found byte across 64 synthetic combinations per seed.

**Observed** `JumpGate_interact` 0x27d754–0x27d7a0 calls
`JumpGate_openMenu` 0x27da24 after its menu mutex test; network mode has
its own gate at 0x27d778. `jumpgate_menuRun` 0x27dd74 runs an eight-state
task. It disallows choosing the current level and, after confirmation,
counts travel for 180 ticks. At 0x27e1c0–0x27e218 it copies either the
fixed destination 0x8e3c34 or the selected destination-list entry into
pending level 0x41b6d0 and sets entrance orientation byte 0x41b720 to
`0xff`. `docs/level-flow.md` 9 in `t3/research-levels` records list
persistence, act reset and state-machine detail. The menu input, network
mutex and full task timing were read but not dynamically compared here.

**Observed, Executed** `JumpGate_ctor` 0x27c694–0x27cab8 handles `Portal`
and `PortalHurt`. When travel state 0x500ae8 is nonzero and fixed destination
0x8e3c34 is zero, it calls `world_findFreeSpot` 0x14acf8 for every player
slot below 0x4d8ae0, with gate position, spread 36, radius 24 and
`anyHeight=1` (0x27c974–0x27c9dc). Each returned position is stored at
0x4f70d0 + 12*slot. Each slot also draws the shared seed
`seed = seed * 0x19660d + 0x3c6ef35f` and uses its high 16 bits as facing
at 0x4f8410 + 2*slot (0x27c9e0–0x27ca70). Rank 0x4f7108 becomes 3 even
with zero players. A fixed destination skips this arrival block. The
20-case difftest compares rank, seed, every slot, and search arguments.
It stubs base-object construction (copying the supplied position), visual
resources, light/run-list registration and the free-spot result; the input
seed is therefore the value at entry to this arrival branch, after the
real base constructor would draw. Actual terrain placement remains covered
by the separate `t3/research-levels` model and its tests, not by this
synthetic test.

**Observed from `t3/research-levels`**, `Player1_ctor` 0x158928 ranks
markers by first/default, `from` previous level, then named entrance;
`JumpGate_ctor` is a separate rank-3 arrival source. `g_entranceName`
0x4f8468 survives level changes. In the destination level, the *newly
constructed* gate selects arrival when the travel state remains active;
the departure gate does not supply a direct coordinate. The gate task
later clears that state. Whether a particular native level has a suitable
gate and what exact floor is chosen require its level inputs; no such value
is embedded here.

## 4. Ordered native port list for playthrough blocker 6

1. Schedule real `Trigger` records in the 15 slow lists with the same
   cursor and frame order as `runObjects`; connect player x/y and occupancy
   to `Trigger_contains`/`Trigger_run`. Preserve lower-slot priority,
   recall suppression, +0x60/+0x64/+0x68, and the initial rectangle query
   for `TriggerParams`.
2. Bind selected object and active player before dispatch. Run linked
   actions before the Trigger's own `script`/`not...` script; implement the
   exact `onOnly`, `offOnly`, `timeout`, `needScriptHit` and slot-3 enable
   sequence. Persist the five trigger state bytes.
3. Wire `PushTrigger` into normal player proximity/use and prompt paths:
   ordered `key` predicates, host-only branch, `message`/`lockMessage`,
   `shop`, `offOnly`, `once`. Do not auto-dispatch it on walk-in.
4. Retain the pending world request and selected entrance across the level
   boundary. Run the destination object's construction and the Player1
   ranking/free-spot path in record order. Preserve campaign and level
   states required by `docs/level-flow.md` 5–7.
5. Port gate discovery and destination list save/restore/reset, then the
   prompt's script and party-distance predicates and the menu/input state
   machine. Keep the 180-tick travel state through the load, instantiate
   destination gates before final placement, and apply `anyHeight=1`
   searches, seed/facing writes and rank 3. Clear travel through the task
   at its documented time.
6. Run the native client with real, owner-supplied level data: walk into a
   Trigger, interact with a PushTrigger, and travel a gate. Compare
   transition, arrival and save/re-entry traces with the original. The
   isolated emulator comparisons do not establish these integrated flows.

## 5. Verification boundary

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_exits.py --seed 20973`
and `--seed 7` each compare 268 trigger/rectangle, 64 gate-prompt,
48 push-prompt and 20 gate-arrival cases. The test constructs only synthetic
objects and player positions, pins the executable hash, and does not copy
its bytes into a tracked file. The reference and difftest do not execute
the level loader, actual scripts, world collision search, network host
branch, complete jump-gate task or a running game. Those remain separate
acceptance gates.

On both seeds, `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py
~/champions-re/SLUS_209.73 --quick --seed <seed> -k marker` passed 4/4
Player1/free-spot properties across the default and three alternate FPU
models. `-k run` passed 2/2 offline/network run-list properties per seed.
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools
-p 'test_*.py'` passed 652/652. These existing properties support the
dependent marker and scheduling contracts but do not turn this isolated
exit test into native-client acceptance.
