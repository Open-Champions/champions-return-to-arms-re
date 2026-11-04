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
The reset's first load is `0x82c40c`, not `0x82c408`. `0x18e708` calls
`0x195bb0`, and that function's store at `0x195c1c` writes 1 at `0x82c408`
when the filled slot is `-1`.

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

## Round 4: TerminateThread syscall 37, 2026-11-03

The round-2 and round-3 traps remain the default.
`EE.install_terminate_thread` is opt-in and composes with
`EE.install_deci2_kputs`. `tools/difftest_death_reload_kputs.py` does not
install it. `tools/difftest_death_reload_thread.py` installs both.

**Observed:** `TerminateThread` `0x352830` loads v1 = `0x25` (37), executes
`SYSCALL` at `0x352834`, and returns through `jr` at `0x352838`. A scan of
`jal` and `j` instructions finds nine call sites and no pointer word. Eight
sites do not read v0:

- `0x17de04` and `0x17e478` load the id word at `0x7cfd04`. The instructions
  after each call reload that word and call `0x353b20` with a1 = 0. The call
  at `0x17e478` is in `0x17e2c8`, which teardown calls at `0x1e5088`. That
  function then calls `texcache_reset` `0x179b08` and `texcache_init` `0x17a1d0`.
- `0x17fe60` loads the same id and returns.
- `0x31ef30` loads the id word at `0x8eafe4` and then calls `0x361250`.
- `0x367824` tail-calls `DeleteThread` `0x3527f0` with the same id.
- `0x368e24`, `0x3a02c4` and `0x3a1268` call `DeleteThread` with the same id.
  After that call, `0x368e34` stores 0 over its id word.

The ninth site, `0x35f3b4`, compares v0 with -1 at `0x35f3bc` before
`DeleteThread`. The retail value is **Unknown**, so the handler rejects that
return address.

**Observed:** `0x353b20` calls `0x3534b0`. That function returns 1 when COP0
Status bit 0 is clear. `0x353b20` then returns -1 and does not execute a
syscall. When the bit is set, `0x353b20` calls `ReferThreadStatus` `0x3528e0`
and calls `_StartThread` `0x352800` only if the first status word equals
`0x10`. What `0x10` means to the kernel is not established here.

**Executed:** the handler accepts only v1 = 37 and only the eight return
addresses above. It writes v0 = 0 and does not read or write guest memory.
That 0 is not a recovered kernel result, and the id word is left unchanged.
Any other syscall number, and syscall 37 at any other return address, raises
the original `CpuTrap`. Both seeds, simple and qualified, with this handler
and the harness `particle_init`, return from `0x352834` once. v0 is 0 at
`0x17e480`. COP0 Status stays 0, so `0x353b20` returns -1, the value present
on entry to `texcache_reset`, and does not call `ReferThreadStatus` or
`_StartThread`. The retail Status value during a death reload is **Unknown**.
This fixture does not execute startup.

**Executed:** teardown still does not return. The next stop is a 2-byte write
to address `0x18` at pc `0x179b30`, return address `0x17e498`. `texcache_reset`
loaded index 0 from `0x7cfe44` and the pointer in the ring slot at `0x7cfd40`.
That pointer is 0, so the store at pointer + `0x18` uses address `0x18`.
`texcache_init`, `CreateThread`, world reconstruction `0x14e808` and
`Player_ctor` `0x1a1d28` are not entered. The id at `0x7cfd04` stays 0.
Checkpoint, directory and saved-world bytes stay unchanged.

**Observed:** the only `jal` to `particle_init` `0x18e648` is at `0x19d818`,
in `engine_init` `0x19d19c`. The only `jal` to `engine_init` is at `0x323e24`,
in `0x323dcc`. The only `jal` to `0x323dcc` is at `0x14fcb8`, in the startup
sequence whose ELF entry is `0x14fa88`. No pointer word holds `particle_init`,
and no `lui` followed within eleven instructions by `addiu` or `ori` on the
same register builds that address. The address of `0x323dcc` built at
`0x30de30` is shifted and stored by `getretmips_unwind` `0x30dde4`; it is not
a call. The entry address built at `0x19ddc8` is subtracted by
`dbg_memoryReport` `0x19dd98`; it is not a call. A call computed some other
way was not searched and is **Unknown**. `game_clearLevel` calls the particle
reset `0x18ebb8` at `0x1e5024` and again at `0x1e5054`. It does not call
`particle_init`.

**Executed:** the continued loader has no call from `0x19d818` and does not
enter `engine_init` or `0x323dcc`. The harness call is not the reload path. A
reload through `game_clearLevel` does not run `particle_init`. Whether the
sentinel words written at boot are still intact when a later death reaches the
reset is **Unknown**. This sequence does not execute that interval.

**Executed, separate:** original `texcache_init` from the loaded image, with
no syscall handler, writes `0x7cfe00` at `0x7cfd40` and then stops at
`CreateThread` `0x3527e0`. The syscall is v1 = 32 at `0x3527e4`, return
address `0x17a37c`, a0 = `0x425e58`. The parameter words are 0, entry
`0x17ca58`, stack `0x7cbd00`, size `0x4000`, the current gp, and 6. gp is 0
in this call because the startup store at `0x14fc40` was not executed. The id
word is still 0: the store of v0 is the delay slot of the following `0x353b20`
call, which has not run. That caller reads v0, so `CreateThread` is not
modelled. The retail thread id is **Unknown**.

**Observed:** the only `jal` to `texcache_setRange` `0x17a3a0` found in the
listing is at `0x19d6f8`, inside `engine_init`, and `0x17a3e0` calls
`texcache_init`. The shutdown calls `texcache_reset` before `texcache_init`.
**Inferred:** a boot that reached the ring store would have made `0x7cfd40`
non-zero before a later reset. This fixture does not run that boot. The zero
slot is the fixture's untouched memory, not a retail reload result.

**Unknown:** the retail result of `TerminateThread`, including for id 0; the
branch at `0x35f3bc`; COP0 Status at reload; `ReferThreadStatus` and
`_StartThread` when Status bit 0 is set; the `CreateThread` id; file loading,
world reconstruction, player construction and playable arrival. These host
calls are a synthetic sequence, not game-main. Keep the native
`blocked_death_reload` boundary.

A native client can implement syscall 37, for a caller that does not read v0,
as a return that leaves the id word unchanged. That does not stop a thread the
client has not created, and it does not restore a world or construct a player.
The caller at `0x35f3bc` still needs the retail result. The original teardown
still stops before world reconstruction, so the client refusal stays.

## Reproduce, round 4

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_thread.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_thread.py local/SLUS_209.73 --seed 7
```

Each seed: four continued loaders, two exact particle-reset faults and two
exact `texcache_reset` faults, plus one separate `CreateThread` stop. No
stubs. Success output reports counts only.

## Round 5: boot before reload, 2026-11-03

The round-2, round-3 and round-4 traps remain the default.
`EE.install_modelled_boot` is opt-in and composes with the two earlier
handlers. Every v0 it writes is modelled. It is not a recovered kernel result.
`tools/difftest_death_reload_boot.py` is the only caller.

**Observed:** startup `0x14fa88` writes gp at `0x14fc40`. The value is
`0x56c170`. Syscall 60 at `0x14fc48` is followed by a move of v0 into sp at
`0x14fc4c`. The arguments are gp in a0, `0x1fc0000` in a1 and `0x40000` in a2.
The modelled sp is a1 + a2 - `0x10`, which is `0x1fffff0`. Syscall 61 at
`0x14fc64` is followed by a call whose delay slot is a nop. That caller does
not read v0. The modelled result is 0.

**Observed / Executed:** the next function calls CreateSema twice, at
`0x35c084` and `0x35c094`. Both callers store v0. The modelled ids are 1 and
2, and those stores are at `0x5075d0` and `0x5075d4`. It then calls SetSyscall
with return addresses `0x35c1d0` and `0x35c1dc`. Neither reads v0. The first
passes number `0x83` and address `0x35c108`. The second passes number `0x5a`
and address `0x35c0d0`. The modelled result is 0. The following syscall is
number 131. Its wrapper returns with `jr ra` and a nop, so the model
transfers to `0x35c108` and leaves ra unchanged.

**Executed:** `0x35c108` reads `0x80000000` and stops. That address is not in
the loaded image. The call at `0x14fcb8` does not run. The ring word
`0x7cfd40` and the particle word `0x82c408` stay 0. **Unknown:** the bytes
from `0x80000000` through `0x8007ffff`. The scan compares the cursor with a1,
and this caller passes a1 = `0x80080000`.

**Executed, separate:** `engine_init` `0x19d19c` is called with gp set to
`0x56c170`, because startup does not reach it. The test maps `0x12000000` for
`0x2000` bytes so the 8-byte store of zero at `0x19d1dc` has a destination.
That map is not a GS model. With the diagnostic opt-in and the modelled boot
handler, execution reaches WaitSema. GetThreadId's modelled result is 1.
ChangeThreadPriority of that id to 10 does not read the old priority.
GsPutIMR, return address `0x34f79c`, and SetGsCrt, return address `0x19d36c`,
do not read v0; both modelled results are 0. AddIntcHandler for cause 2 and
address `0x19b6e4` returns modelled id 1, stored at `0x44fd4c`. EnableIntc,
return address `0x353560`, saves v0; the modelled previous state is 1.
`engine_init` does not read that outer result.

**Executed:** WaitSema at `0x352a24` has a0 = 2 and return address `0x19d05c`.
The semaphore's count is 0, so the handler raises. The waiter `0x19d028`
samples the word at `0x44fd98` and repeats while that word is unchanged.
**Observed:** `0x19b6e4` increments that word and signals the semaphore.
**Observed:** `engine_init` calls the waiter at `0x19d394`, `0x19d3a4`,
`0x19d3f0`, `0x19d3fc` and `0x19d408`. This run stops on the first call. The
handler is not delivered. CreateThread `0x3527e0`, `texcache_init` and
`particle_init` do not run.

**Executed, same session:** the death sequence then uses that machine. It
still supplies its own player, checkpoint and task list. The particle word
and the ring stay 0. The loader stops on the 4-byte write to address 4 at pc
`0x18ec10`, return address `0x1e502c`. World reconstruction `0x14e808` and
`Player_ctor` `0x1a1d28` are not called.

**Unknown:** the retail ids, the retail WaitSema wake, the kernel window
above, file loading, world reconstruction, player construction and playable
arrival. These host calls are not game-main. Keep the native
`blocked_death_reload` boundary.

A native client can use distinct modelled ids where a caller stores
CreateThread, GetThreadId or CreateSema, and it can ignore v0 for the unread
calls named above. That does not leave the GS wait, fill the texture-cache
ring, or construct a player. The original teardown still stops before both,
so the client refusal stays.

## Reproduce, round 5

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_boot.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_boot.py local/SLUS_209.73 --seed 7
```

Each seed: one entry stop, two engine_init WaitSema stops and two
particle-reset faults. No stubs. Success output reports counts only.
