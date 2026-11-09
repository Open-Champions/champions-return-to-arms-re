# Offline death reload: executed boundaries

Research base `e7d8972`, branch `t3/research-death-reload`, 2026-10-27.
Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
**Observed** denotes addressed instruction evidence; **Executed** denotes
synthetic original-function execution in `tools/ee_emu.py`; **Inferred** and
**Unknown** are not execution claims. No console or whole-game run is claimed.

## Round 2 evidence, 2026-10-27

The sections below retain the audited round 1 boundary. **Executed, bounded:**
new additive probes extend it in four addressed documents:

- [Continuous synthetic sequence](death-reload-sequence.md): original lethal
  pending damage, 240 countdown frames, 32 fade frames, real task dispatch,
  act lookup and checkpoint restoration execute without service stubs. Original
  world loading then stops at kernel SYSCALL `0x352e14`, v1 = 124, before
  reconstruction. The registered death task protects the saved-world buffer;
  a no-task control reaches the checkpoint writer. This is not completed reload.
- [Creature effects](death-reload-creature.md): original model-mask, animation,
  base death-handler, run/target-list removal, deferred-delete and type-equality
  effects execute with linked synthetic objects. Name/spatial memberships are
  retained; spatial query exclusion depends on its mask. The virtual `+0xe0`
  call formerly called “motion” below is the base death handler `0x10beb8` in
  the supplied configuration. Nonzero motion fields remain unchanged.
- [Portal effects](death-reload-portals.md): original light, cached-resource,
  animation, grid/run-list and distinct state-portal effects are tested.
- [World-present object effects](death-reload-objects.md): original nonempty
  record dispatch, constructors and class loads are tested for selected
  container/trigger paths; item and door coverage preserves explicit constructor
  boundaries. A separate cached-resource level-state pipeline executes.

**Unknown remains:** complete class/subclass constructor and resource behavior,
script-bearing worlds, platform services, full world reconstruction plus player
creation, and continuous death-to-playable completion. The four probes are
separate fixtures; their results must not be concatenated into a whole-game
claim. The native `blocked_death_reload` gate is still not resolved.

## Round 3 evidence, 2026-11-03

**Executed, bounded:** the same continuous sequence can return from the
round-2 syscall when `EE.install_deci2_kputs` is installed. That handler is
only syscall 124 function `0x10`, the teardown diagnostic. It leaves the default trap,
the round-2 vectors and every other syscall number unchanged. Teardown is
entered and does not return. Without original `particle_init` `0x18e648`, the
next stop is the null write at `0x18ec10`. After that original init, the next
stop is `TerminateThread` syscall 37 at `0x352834`, with thread id 0. World
reconstruction and player construction are still not reached. Details and the
native-client limit are in
[the sequence note](death-reload-sequence.md#round-3-diagnostic-syscall-124-2026-11-03).

## Round 4 evidence, 2026-11-03

**Executed, bounded:** `EE.install_terminate_thread` is a second opt-in. It
accepts syscall 37 only at the eight callers that do not read v0, writes v0 = 0,
and leaves the thread-id word unchanged. The default trap, the round-2 vectors
and the round-3 `TerminateThread` stop stay in place. With both opt-ins, and
only after the harness calls `particle_init`, teardown passes syscall 37 and
stops at a 2-byte write to address `0x18` in `texcache_reset` `0x179b30`.
The ring slot at `0x7cfd40` is 0. `particle_init` is called from `engine_init`,
which is called from startup, not from `game_clearLevel`. World reconstruction
and player construction are still not reached. Details are in
[round 4 of the sequence note](death-reload-sequence.md#round-4-terminatethread-syscall-37-2026-11-03).

## Round 8 evidence, 2026-11-09

**Executed, bounded, on models only:** with `EE.install_modelled_sif`, the
boot passes the EE half of the SIF command handshake and stops in WaitSema
inside `sceSifBindRpc` for CD server `0x80000592`, called by `sceCdInit`.
That is the first point where the EE needs IOP data. Every result past the
GS model and the five INTC deliveries taken while Status is 0 (audit
R7-1/R7-2) is conditional on those models. Details are in
[round 8 of the sequence note](death-reload-sequence.md#round-8-the-sif-wall-2026-11-09).
[death-reload-client-path.md](death-reload-client-path.md) lists the reload
steps a native client can do with its own loader without the original boot,
and the steps that stay Unknown.

## Automatic action after the countdown

**Observed / Executed:** `game_checkAllDead` 0x1e7438 with one offline player,
zero HP, no living players, loaded campaign, no cutscene/pause, a non-frozen
service answer and both countdowns initially 1 decrements both to zero. It sets
menu lockout 60, closes menus, and executes `deathTask_schedule` 0x1ebd48.
The wrapper sets phase and force-network byte to zero, clears fade through
0x1df5d0, and registers 0x1e75e8 at priority 20 with argument zero through
0x19e4a0. Registration and freeze answers are callbacks, not an actual scheduler.

**Observed / Executed:** phase 0 of `deathTask` 0x1e75e8 advances to phase 1
when the recorded fade service returns 128 for increment 4. On the next call:

- If `save_findAct` 0x217d30 returns a nonnegative result, the original
  `save_reload` 0x22266c calls the original `save_load` 0x221d60. This probe
  does **not** stub either reload function. It restores the synthetic saved
  player record (all 0x4c30 bytes, except the documented +0x43d8 clear),
  saved facing and position, player count, loaded-from-save flag and requests
  the saved level with marker 253; phase becomes 2. Both simple and qualified
  synthetic destinations are tested. Camera/destination decoding, player fixup,
  deferred/quest clearing and act setup are recording callbacks; their effects
  are not proved here. Actual libc string/copy code executes.
- If that lookup returns -1, it requests the current level with marker 253,
  copies max HP into current HP, and removes the task. Comparison of the entire
  current record proves all other record bytes retain their current values in
  this tested branch. This is not evidence of a fresh world reset.

**Observed:** no menu-choice service or input-choice branch occurs along these
instructions. The normal path automatically requests the in-memory checkpoint's
saved level; it does not select or read a memory-card slot. The saved level,
not a hardcoded hub or nearest spatial checkpoint, selects the destination.
Gold, XP, bags and equipment within the restored record roll back to the
snapshot's values; no separate fixed death fee is established.

**Observed:** the alternate-death flag at 0x4f712c redirects phase 0 to phase 10
(0x1e7648–0x1e7658); it is a separate script-driven path, not a menu choice.
Phase 2 waits for an empty pending request and matching qualified names before
removing the task (0x1e7740–0x1e7780). These branches were bounded-tested by
prior audited `t3/research-death-flow` commits `dbb1981` / `8be79eb`; they are
not new execution coverage in this branch. The prior research's references and
vectors were not changed or copied into this pin.

**Observed:** `mainloop_loadRequestedWorld` 0x320edc suppresses storing the dying
world when the death task is present (0x320f00–0x320f44; see `docs/mainloop.md`).
**Inferred:** storing the post-checkpoint dying world before reload would defeat
rollback. Native reload must retain the checkpoint world snapshot, rather than
first overwriting it with the current dead world.

**Unknown:** invalid/uninitialized checkpoint behavior, real scheduler timing,
rendered overlays or platform prompts, the alternate script's revival, and the
full level-load/object-construction completion. The act lookup is still scripted;
its result is not a checkpoint validity test. No new respawn-choice menu, nearest
checkpoint policy, hub fallback, or fresh-world reset is justified.

## Class reconstruction probes

`tools/difftest_death_reload.py` compares original return sizes, memory and call
arguments against independently authored expectations. Counts per seed: four
countdown/scheduler/fade/reload-or-restart chains; three Trigger, twelve Chest,
two JumpGate, six world-backed door, 36 Creature, four ItemProp and four
Chest/AutoChest animation cases: 71 cases total (plus four direct Prop controls). Only the player-record bytes
are randomized; class cases are deterministic controls repeated on each seed.

| Class and address | Executed result and remaining boundary |
|---|---|
| Trigger 0x1ecef4 | Consumes 5 bytes; restores +0x64 word and +0x60 byte for 0, 1, 255. No external service is needed. Does not restore interpreter state. |
| Creature 0x116920 | Restores variant +0xe8, multiplies saved HP ratio by constructed max HP, consumes dead-only animation handle, reapplies five +0xa8 masks, replaces +0x231 bit 0 and conditionally restores +0x312. Dead input sets state 20 and flags 0x2009. Matching synthetic clip calls reset at +0x114, start with flags 4, end, then virtual motion callback with 1; +0x11a gains 0x80. Missing clip skips these animation calls. 36 live/dead/mask/match cases check exact arguments and output. String resolution, virtual variant/motion/type callbacks, animation, stop/list unlink and type check are recorded; complete resulting motion, corpse track and world registration remain Unknown. Optional-word tests use an eligible object; other eligibility branches remain Unknown. |
| Chest 0x2922cc | Twelve boundary cases cover open/closed, gold 0/1/32767 and two synthetic class definitions. Open calls clip start at +0x5c with definition +0x1c and flags 0x204, then end; open with nonpositive signed gold clears 0x100000. Class setter receives the restored variant's definition. Additional execution runs actual animation start/end 0x170838/0x170bc8 and class setter 0x14f5f0 with a current synthetic cache: one appended track, flags 0x204 and time equal to synthetic clip length 73. Closed starts no clip. Asset cache misses and rendered pose remain Unknown. |
| AutoChest 0x23b0b4 | Additional open/closed cases execute the actual clip services at track +0x98, restore its twelve-byte payload and clear 0x100000 for open/zero gold. Trap fuse and subsequent ticking remain Unknown. |
| DoorSwing 0x28ae74 | Original world setters execute with a synthetic relocated world containing one piece/element/surface. Restores angle, signed direction byte and speed; nonzero angle clears 0x100000, sets mask 1 and queues update. Collision setter receives 0, setting terrain-element mask 0x2; pose setter receives signed angle. Zero and half-turn angles are covered with zero XY origin, not arbitrary-angle rendered parity. |
| DoorSecret 0x28b1b8 | Closed/open restore byte. Open executes world collision setter with 0 and pose setter with translation (0,0,-300), angle zero: synthetic surface Z becomes 16-1200=-1184 in quarter units, and 0x100000 clears. Closed leaves world surface unchanged. |
| RollDoor 0x28df24 | Restores open word truncated to halfword, piece index, speed and counter; executes collision setter with 1 (clears terrain-element mask 0x2), reads element height into +0x4e (123 in fixture), and queues update only when open. This load does not call the piece pose setter. Later motion/ticks remain Unknown. |
| JumpGate 0x27d998 | Restores two bytes. Active calls light service at +0x100, asset lookup at +0x90 and clip start at +0xd8 with flags 3. Both states queue update. Exact arguments are checked; light/asset/animation/update services are recorded, so their world/render effects remain Unknown. No general portal-class equivalence is inferred. |
| ItemProp 0x159758 / Prop 0x158f04 | Four cases execute the nested Prop loader, definition-index decoding, quaternion matrix conversion and final matrix setter. Both item state-bit 39 branches and both Prop mask forms (8,10) are covered. Load sets 0x100000, clears 0x800; Prop sets 0x1000; item bit 39 additionally clears 0x3000. Three synthetic strings resolve and copy; model/texture lookup arguments and resulting pointers are checked. Direct Prop controls restore suffix translation (1,-2,3). Final transform uses the base object's pose and facing +0x4000, replacing the Prop suffix translation. Synthetic identity-facing case confirms base (4,5,6) replaces suffix (1,-2,3). String and asset services are callbacks; real resources, arbitrary quaternion/facing and full world registration remain Unknown. |

**Executed world boundary:** door collision 0x182b00, height 0x182b74,
pose 0x182c98 and their math callees run unstubbed. The fixture supplies
relocated arrays with the same fields those functions access. Object update
0x14f248 is recorded, not a real grid/queue rebuild. This is stronger than
recording a pose call, but is not a shipped world or end-to-end loader.

**Unknown:** whole-world factory construction with real resources, all corpse
animation and movement effects, portal variants beyond JumpGate, live/dead
registry integration, class-specific constructor omissions, capacity thinning,
checkpoint creation/restore in a real level, terrain collision queries after a
complete reload, and a continuous death-to-playable journey. These results
narrow `docs/save-world.md`'s unknowns; they do not authorize claiming the native
`blocked_death_reload` gate resolved. Preserve refusal for the remaining effects.

## Reproduce

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Private executable and disassembly links are read-only under ignored `local/`.
Tracked changes contain authored probes and prose, no executable instructions,
raw output, proprietary data, or literal level/asset identifiers.
