# Death-to-loader sequence, round 2

2026-10-27; additive research on audited base `0e3afdb8`.
Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

**Executed:** `tools/difftest_death_reload_sequence.py` carries one synthetic
state through original lethal pending-damage processing, frame-task calls,
checkpoint restoration and entry into the world loader. It installs **no
stubs, instruction patches, PC-changing hooks or automatic memory mapping**.
This advances the round 1 chain, but does not establish death-to-playable
completion: the original world-loader attempt stops at an unimplemented kernel
call before world reconstruction.

## Supplied state and executed sequence

**Executed:** four cases cover successful/missing act lookup and simple/qualified
saved destinations. Only synthetic record, camera-tail, destination-store and
world-buffer sentinel bytes vary with the seed; these are not shipped inputs.
The fixture supplies one player, an object with an animation-track capacity of
four and one synthetic clip pointer, no spells/ward or attacker, an empty task
list, offline/unpaused state, a camera, a RAM packet pool and draw-list head,
an initialized stack-guard region, a two-row synthetic act table, and a checkpoint
containing an empty-inventory player record. Constructors and the checkpoint
writer are not executed. The world-buffer sentinel verifies preservation only;
it is not a decoded or reconstructable world fixture.

1. **Observed / Executed:** original countdown reset `0x1ec2b8` initializes the
   party counter `0x4f7194` and four player counters `0x4f84a8` to 240. The
   harness supplies this initialization; its lifecycle caller is not tested.
2. **Observed / Executed:** `Player_processDamage` `0x1b2cc0` receives 100 pending
   damage at object +0xc8 against record HP 40. It reduces HP to zero, sets object
   flags to `0x109`, sets state +0x58c to 4, clears pending damage/flags and
   executes `anim_start` `0x16cfe0`, installing one track with flags `0x206`.
   The original spell-list search `0x11a710` finds no ward in the empty list.
   This begins with supplied pending damage, not a collision or input attack.
3. **Observed / Executed:** 240 calls of `tasks_run(1)` `0x3226e4` execute
   `game_rebuildAlivePlayers` `0x1e72f8`, `game_checkAllDead` `0x1e7438`, real
   freeze checks and idle rumble updates. Every countdown value is asserted.
   On call 240, the original wrapper `0x1ebd48` clears the fade and `task_add`
   `0x19e4a0` installs `0x1e75e8` at priority 20, flags zero. The dispatcher has
   already run in that frame, so the new task first executes on the next call.
4. **Observed / Executed:** the next 32 `tasks_run(1)` calls dispatch the death
   task through `tasks_call` `0x19e798`. `hud_stepFade` `0x1df5ec` increases fade
   by four each call, reaching 128 and phase 1 only on the last call. The
   original rectangle-packet builder `0x17bd30` and draw-list insertion
   `0x16b7f0` execute: 32 entries are emitted into supplied RAM. This is not GS
   submission or evidence of a visible fade.
5. **Observed / Executed:** frame call 273 invokes actual `save_findAct`
   `0x217d30`, including its string comparisons against the supplied table.
   With a match, actual `save_reload` `0x22266c` and `save_load` `0x221d60`
   restore the checkpoint and set phase 2. With no match, the original branch
   requests the current level, changes only HP in the existing player record
   to max HP, and removes itself through original `task_remove` `0x19e664`.
   The entire record comparison checks this distinction. No fresh-world reset
   is established by the latter branch.

**Executed:** the successful branch now also executes its former callback
boundaries: camera load/reset `0x203a20` / `0x203210`, destination-store load
`0x27dd30`, player fixup `0x216ea8`, deferred clearing `0x1eda08`, variable
clearing `0x1ed728`, and act setter `0x2180a8`. Assertions compare the complete
0x4c30-byte player record (including null fixups for saved equipment indices),
pose/facing, camera angles/position/tail, all 0x1e0 destination-store bytes,
destination count, cleared deferred counts and an existing variable's value.
These cover an empty-inventory record, one camera configuration, empty restored
quest list and synthetic destination payload; item fixup with populated bags,
camera presentation and destination interpretation remain outside this probe.

## World-loader stop and checkpoint preservation

**Observed / Executed:** without resetting that successful sequence's memory,
the harness invokes `mainloop_loadRequestedWorld` `0x320edc`. Original
`task_isRunning` `0x19e5e8` finds the still-registered death task, and the
checkpoint store `0x21777c` is not reached. The whole checkpoint buffer,
ten-entry directory and synthetic saved-world payload remain byte-identical.
An independent negative control runs the same original main-loop prefix with
no death task and stops exactly at entry to `0x21777c`, proving that it would
store the current level in that condition. No substitute writer is used.

**Observed / Executed:** the original prefix splits the request into level and
sub-name, clears the pending request, changes marker 253 to 254 and calls
`game_loadLevel` `0x1e55c0` at `0x321148`. That function calls level teardown
`0x1e4e88`, whose diagnostic call at `0x1e4ec0` reaches `0x355490` and ultimately
`Deci2Call` `0x352e10`. Execution stops at **SYSCALL `0x352e14`, v1 = 124**.
The test requires this exact trap; unrelated exceptions fail. No trap is
stubbed, skipped or treated as a successful load. Reconstruction entry
`0x14e808` has not executed, the player-record object pointer remains null,
and the death task remains registered in phase 2.

**Executed, separate controls:** four independent fixtures exercise phase 2
through the actual task list, name builder `0x1ec0f0`, saved-name getter
`0x222688`, string comparison and task removal. Pending request, base-only name
and wrong sub-name retain the task; an empty request and exact qualified-name
match remove it. These controls do **not** resume the failed loader or establish
world readiness. Task removal alone is insufficient evidence of playable reload.

**Unknown:** original top-level frame driving, collision-produced lethal
damage, ward-present behavior, constructor validity beyond the accessed fields,
populated inventory restoration, kernel/IOP/resource completion, full world
teardown/reconstruction, player construction and return to playable gameplay.
The host calls original frame functions and then the original loader explicitly;
this is continuous synthetic state, not an uninterrupted game-main execution.
Keep the native `blocked_death_reload` boundary for the unresolved whole flow.

## Reproduce

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_sequence.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_sequence.py local/SLUS_209.73 --seed 7
```

Each seed: four sequences with 273 frame calls apiece, including two exact
world-loader trap checks, plus four separate completion controls and one
checkpoint-store reachability control. Success output reports counts only.

## Round 3: diagnostic syscall 124, 2026-11-03

The round-2 trap remains the default. `EE.install_deci2_kputs` is opt-in and
does not change that test. `tools/difftest_death_reload_kputs.py` repeats the
successful sequence, installs the handler, and continues
`mainloop_loadRequestedWorld`.

**Observed:** `Deci2Call` `0x352e10` loads v1 = `0x7c` (124) and executes
`SYSCALL` at `0x352e14`, then `jr` at `0x352e18`. Twelve wrappers at
`0x35e218`–`0x35e438` pass a function number in a0 and a stack parameter block
in a1, and return v0 unchanged. The teardown diagnostic uses function `0x10`
only: `game_clearLevel` calls `dbg_printf` `0x355490` at `0x1e4ec0`; that calls
formatter `0x354590` with callback `0x355300`; the callback calls buffered putc
`0x354240`; putc calls wrapper `0x35e428` for byte `0x0a` or when the count at
`0x507504` has reached `0x7e`. The wrapper stores the string pointer as
parameter word 0 and sets a0 = `0x10`. The branch at `0x354280` does not read
v0, and `0x35531c` replaces v0 with 1. This path does not observe a kernel
result or a status word. Other function numbers at those wrappers, including
1 at `0x35e218`, 3 at `0x35e288` and 4 at `0x35e2b8`, are not this call.

**Executed:** the handler accepts only v1 = 124 and a0 = `0x10`. It writes
v0 = 0 and does not read the string. The retail return value is **Unknown**;
no caller on this path reads v0, so the written 0 is not a recovered kernel
result. Any other syscall number still raises the original unhandled-syscall
`CpuTrap`. Any other Deci2 function number raises `CpuTrap` and names a0.
Both seeds, simple and qualified, return from `0x352e10` once. The checkpoint,
directory and saved-world bytes stay unchanged, and the checkpoint writer
`0x21777c` is not entered.

**Executed, no `particle_init`:** teardown `0x1e4e88` is entered and does not
return. The next stop is a 4-byte write to address `0x4` at pc `0x18ec10`,
with return address `0x1e502c` (call at `0x1e5024`). `0x18ebb8` loads the id at
`0x82c40c` and the pointer at `0x82c4e8`. Both are 0. Both addresses lie past
the ELF file bytes, in the zeroed tail of the loaded segment. The id is not the
`-1` sentinel the comparison at `0x18ec04` requires, so the following store uses
the null pointer. World reconstruction `0x14e808` and `Player_ctor` `0x1a1d28`
are not called. `g_taskCount` stays 1.

**Observed:** `particle_init` `0x18e648` is the function that stores `-1` across
`0x82c408`–`0x82c484` at `0x18e6e4`, then calls the same reset at `0x18e7d0`.
The reset's first load is `0x82c40c`, not `0x82c408`. `0x195c1c`, called from
init at `0x18e708`, stores 1 at `0x82c408` after that fill.

**Executed, original `particle_init` before the loader:** the call returns 3.
What 3 represents is **Unknown**. Afterwards `0x82c40c`–`0x82c484` are `-1`,
`0x82c400` is `0x82c300` (the store at `0x18ee18`), `0x82c408` is 1, and
`g_taskCount` is 3 after the two `task_add` calls at `0x18e7fc` and `0x18e818`.
The same loader passes the null-pointer store. Teardown still does not return.
The next stop is `TerminateThread` `0x352830`: syscall v1 = 37 (`0x25`) at
`0x352834`, a0 = 0, return address `0x17e480`. That call is in `0x17e2c8`,
reached from teardown at `0x1e5088`. a0 is the word at `0x7cfd04`, which is 0.
The instructions at `0x17e480` do not read v0; they call `0x353b20` with the
same id. `0x17a1d0` has not been entered. The kernel result of terminating id 0
is **Unknown**, so this syscall is not modelled.

**Unknown:** Deci2 function numbers other than `0x10`, the retail result of
function `0x10`, use of the diagnostic text, finishing `0x18ebb8` from the
zeroed BSS, `TerminateThread` for an id this fixture never created, file
loading, world reconstruction, player construction and playable arrival.
These host calls are a synthetic sequence,
not game-main. Keep the native `blocked_death_reload` boundary.

A native client can implement syscall 124 function `0x10` as a no-effect return
for this diagnostic. That does not restore a world or construct a player. The
original teardown still stops before both, so the client refusal stays.

## Reproduce, round 3

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_kputs.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_kputs.py local/SLUS_209.73 --seed 7
```

Each seed: four continued loaders, two exact particle-reset faults and two
exact `TerminateThread` stops. No stubs. Success output reports counts only.
