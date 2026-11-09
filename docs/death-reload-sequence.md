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
`jal` and `j` instructions finds nine call sites. A data word at `0x51f7b8`
holds `0x352830` inside the stub-address run at `0x51f71c`–`0x51f8c4`. This
scan found no use of that run as a call. Eight sites do not read v0:

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
only when `0x35bfe8` returns non-zero, and then calls `_StartThread`
`0x352800` only if the first status word equals `0x10`. What `0x10` means to
the kernel is not established here.

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
a call. The entry address built at `0x19ddc8` is subtracted at `0x19dd98`;
it is not a call. A call computed some other way was not searched and is
**Unknown**. `game_clearLevel` calls the particle
reset `0x18ebb8` at `0x1e5024` and again at `0x1e5054`. It does not call
`particle_init`.

**Executed:** the continued loader has no call from `0x19d818` and does not
enter `engine_init` or `0x323dcc`. The harness call is not the reload path. A
reload through `game_clearLevel` does not run `particle_init`. Whether the
sentinel words written at boot are still intact when a later death reaches the
reset is **Unknown**. This sequence does not execute that interval.

**Executed, separate:** original `texcache_init` from the loaded image, with
no syscall handler, writes `0x7cfe00` at `0x7cfd40` and then stops at
`CreateThread` `0x3527e0`. The trap names `0x3527e4` and the emulator pc is
the following instruction, `0x3527e8`. The syscall is v1 = 32, return address
`0x17a37c`, a0 = `0x425e58`. The parameter words are 0, entry
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
branch at `0x35f3bc`; COP0 Status at reload; the result of `0x35bfe8` when
Status bit 16 is set, and therefore whether `ReferThreadStatus` runs;
`_StartThread` when that result is non-zero and the first status word equals
`0x10`; the `CreateThread` id; file loading,
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
the loaded image. The call at `0x14fcb8` does not run. A planted
`0x51525354` at `0x7cfd40` and a planted `0x61626364` at `0x82c408` do not
survive startup. With write recording on, the only stores that overlap
either word are two 16-byte stores of 0 at pc `0x14fbe0`, to `0x7cfd40` and
`0x82c400`. **Observed:** `0x14fbe0` is the `sq $zero` of the loop at
`0x14fbd8`-`0x14fbf0` that clears `.bss` 16 bytes at a time. So both words
are 0 at the stop because startup cleared them, not because nothing wrote
them. **Unknown:** the bytes
from `0x80000000` through `0x8007ffff`. The scan compares the cursor with a1,
and this caller passes a1 = `0x80080000`.

**Executed, separate:** `engine_init` `0x19d19c` is called with gp set to
`0x56c170`, because startup does not reach it. The 8-byte store of zero at
`0x19d1dc` targets a GS privileged register. Round 5 originally mapped
`0x12000000` for `0x2000` bytes of zeroed memory to give it a destination.
**Correction (round 8, audit R7-1):** that map acted as a GS register model.
It accepted every store and read back what it held. The tests now install
`EE.install_modelled_gs_privileged` instead. It accepts 8-byte stores only to
the eight registers this boot uses, records them and keeps nothing. It
answers only 8-byte reads of CSR `0x12001000`, with a modelled 0. Every other
access to that window faults. In this round-5 stop the only CSR read is at
`0x34f780`. With the diagnostic opt-in and the modelled boot
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
**Observed:** inside `0x19b6e4`, the increment at `0x19b75c` and the two
`iSignalSema` calls at `0x19b760` and `0x19b76c` run only when the byte at
`0x8400f8` is nonzero. The first passes the id at `0x8400f0`. The second
passes the id at `0x8400f4`. The loaded image has 0 at `0x8400f8`, so the
branch at `0x19b71c` goes to `0x19b784` instead. This run does not deliver
the handler. **Observed:** `engine_init` enters the waiter at `0x19d394`.
The five calls that do not run are `0x19d3a4`, `0x19d3f0`, `0x19d3fc`,
`0x19d408` and `0x19d82c`. CreateThread `0x3527e0`, `texcache_init` and
`particle_init` do not run.

**Executed, same session:** the death sequence then uses that machine. It
still supplies its own player, checkpoint and task list. The planted ring
and particle sentinels are unchanged, and the write log has no store that
overlaps either word. The loader stops on the 4-byte write to address 4 at pc
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

## Round 6: one modelled interrupt per blocked wait, 2026-11-03

The round-5 WaitSema trap remains the default.
`EE.install_modelled_intc` is opt-in and composes with
`EE.install_modelled_boot`. `tools/difftest_death_reload_boot.py` does not
install it. `tools/difftest_death_reload_intc.py` does. Without this opt-in,
syscall `-0x43` still raises `CpuTrap`.

**Observed:** `engine_init` calls AddIntcHandler `0x3526c0` at `0x19d37c`.
That wrapper loads v1 = `0x10` (16). The arguments are cause 2, handler
`0x19b6e4` and next 0. EnableIntc `0x352720` loads v1 = `0x14` (20) and is
reached through `0x353528` with cause 2. `0x19b6e4` returns through `jr ra`
and sets v0 to 0. It does not read a0 before overwriting it. Both exits `jal`
`0x352a10`. That wrapper loads v1 = `-0x43` and executes `SYSCALL`. One delay
slot loads the id at `0x8400f4`. The other signal uses the id loaded from
`0x8400f0`. Both exits add 1 to the word at `0x44fd98`. The loaded image
has 0 at `0x8400f8`. The branch at `0x19b71c` goes to `0x19b784` when that
byte is 0, and the exit at `0x19b8c8` still increments and signals. This run
does not record which exit ran. The word at `0x19b920` is `0x42000038`,
which is `EI`.

**Inferred:** a0 on entry is the cause, because that is AddIntcHandler's
first argument and the body is an ordinary function. This model passes cause
2 in a0. When the handler returns, the interrupted registers are restored,
because the waiter at `0x19d05c` continues with the values it held. The BIOS
save mask is not in this image. Restoring the register file is the model.
The count update for syscall `-0x43` is the same increment the modelled
SignalSema already applies. It does not consult the max word, and it is not
a recovered kernel result. Registration order is the delivery order. This
boot registers one handler, and its next argument is 0.

**Correction (round 8, audit R7-2): every delivery below is taken while COP0
Status disables interrupts.** The emulator starts with Status 0, and nothing
in this boot sets IE (bit 0). The emulator's EI sets only EIE (bit 16).
Status is recorded as 0 at each of the five deliveries. A CPU in that state
would not take the interrupt. Before round 8,
`_deliver_intc_for_sema` never read Status. It now delivers only when IE and
EIE are set and EXL and ERL are clear. `install_modelled_intc(while_disabled=True)`
delivers anyway, as a disclosed modelled exception, and records Status at
each delivery. The intc and mirror tests use that form and assert Status 0
five times. So the five deliveries, the counter, semaphore counts and
everything later in rounds 6 to 8 depend on that model, not on an executed
interrupt. The handler's own EI at `0x19b778`/`0x19b920` is discarded when
the registers are restored.

**Modelled:** the delivery cadence is one run per blocking WaitSema. That
cadence is modelled. It is not a vertical-blank interval. The waits at
`0x19d394`, `0x19d3a4`, `0x19d3f0`, `0x19d3fc` and `0x19d408` each deliver
the handler once. The word at `0x44fd98` becomes 5. A planted `0x11111111`
at `0x44fd94` stays. A planted `0xA5` at `0x44fd9c` becomes 0. That 0 is the GS model's
output, not an executed GS result (audit R7-1). The handler's byte-0 exit
loads CSR `0x12001000` at `0x19b8d8`, keeps bit 13, and stores it at
`0x19b8f8`. The model reads CSR as 0. Before round 8 the read returned the
`0x200` that `0x34f774` had stored in the harness map, and bit 13 of that is
also 0. The tests now assert the model's six CSR reads, `0x34f780` once and
`0x19b8d8` five times, as a check of the model. Semaphore 1's modelled count is
5. Semaphore 2 is waited after each signal, so its modelled count is 0. The
later wait at `0x19d828` does not run.

**Executed:** the next stop is a 2-byte write at pc `0x19d4b4`, return
address `0x19d498`, to address `0x21800094`. v0 is `0x2300`. That is the word
`0x230000` at `0x83d290`, shifted right by 8; the word is not negative, so
the `0xff` adjustment is not applied. a1 is `0x1800080`, the word at
`0x1800010`. a2 is that word OR `0x20000000`, from the `lui` at `0x19d3a8`.
The cached address `0x1800094` is mapped. The alias is not, so the store does
not complete. The call at `0x19d490` has returned, and s5 holds `0x1000a000`.
`texcache_init`, `particle_init`, world reconstruction `0x14e808` and
`Player_ctor` `0x1a1d28` are not entered. A planted `0x51525354` at
`0x7cfd40` and a planted `0x61626364` at `0x82c408` are unchanged, and the
write log has no store that overlaps either word. Planted neighbors
`0x22222222` at `0x7cfd44` and `0x33333333` at `0x82c40c` stay.

**Observed:** syscall 131 is the body installed for number `0x83` at
`0x35c108`. The call at `0x35c1e4` passes a0 = `0x80000000`, a1 =
`0x80080000` and a2 = `0x35c108`. The body loads the word at the cursor and
compares it with a2. A match returns that address. Reaching a1 without a
match returns 0. **Executed:** the first instruction reads `0x80000000` and
stops. The round-5 boot test now also requires those two arguments. The
bytes from `0x80000000` through `0x8007ffff` are not in the loaded image, so
neither a match nor a miss is modelled. The second search, whose needle is
`0x35c0d0`, does not run.

**Executed, same session:** the death sequence still supplies its own player,
checkpoint and task list. The same two sentinels are unchanged and the write
log still has no overlapping store. The loader stops on the 4-byte write to
address 4 at pc `0x18ec10`, return address `0x1e502c`. World reconstruction
and `Player_ctor` are not called.

**Unknown:** the retail interrupt timing, the retail ids, the kernel window,
whether the uncached store would write the cached bytes, file loading, world
reconstruction, player construction and playable arrival. These host calls
are not game-main. Keep the native `blocked_death_reload` boundary.

A native client can run `0x19b6e4` once for each blocked wait on semaphore 2
and apply that count increment. That passes the five waits and leaves
`0x44fd98` at 5. It does not fill the texture-cache ring or the particle
word, and it does not construct a player. The original teardown still stops
on the null particle slot, so the client refusal stays.

This boot does not unblock the `texcache_reset` store at `0x179b30` reached
from `game_loadLevel`. That store adds `0x18` to the pointer at `0x7cfd40`.
The planted sentinel is still there, so this boot has not stored a ring
pointer. The loader still faults at `0x18ec10` before that store.

## Reproduce, round 6

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_intc.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_intc.py local/SLUS_209.73 --seed 7
```

Each seed: two engine_init stops on the uncached store and two
particle-reset faults. No stubs. Success output reports counts only.

## Round 7: main-RAM mirrors through engine_init's SIF stop, 2026-11-09

Every opt-in below is off by default. The round-5 and round-6 tests do not
install them and their stops are unchanged.
`tools/difftest_death_reload_mirror.py` installs them on top of the round-6
machine.

### The uncached store at `0x19d4b4`

**Observed:** `engine_init` forms `0x20000000` in s4 with `lui` at
`0x19d3a8`. It forms `0x1800000` with `lui` at `0x19d420` and passes it to
`tex_relocate` `0x179e10` at `0x19d490`. At `0x19d49c` it loads the word at
offset `0x10` of that block. Round 6 read that word as `0x1800080`. At
`0x19d4ac` it ORs the word with s4, and at `0x19d4b4` it stores a halfword at
offset `0x14` of the result. A `sync` follows at `0x19d4b8`, then
`0x350680`, which writes the GIF channel. The same OR, halfword store and
`sync` repeat at `0x19d514`-`0x19d524` for the block at `0x188c100`.
`0x1800080` is below `0x02000000`, inside the 32 MB main-RAM window. The
register blocks this code uses are formed with `lui` of `0x1000` and
`0x1200`. **Observed:** `0x30000000` is also ORed onto main-RAM addresses, at
`0x16bed0` (base `0x6f4140`) and `0x19d990` (base `0x44fe80`).

**Inferred:** `0x21800094` is the uncached alias of main-RAM byte
`0x1800094`, written so the DMA that follows reads the new value. This is
the EE's uncached window at `0x20000000`. `0x30000000` is the
uncached-accelerated window. It is not a hardware register block.

**Model:** `EE.install_ram_mirrors` sends an address in `0x20000000` or
`0x30000000` whose low 28 bits are below `0x02000000` to the same backing
page as the cached address. There is no cache. If the cached page is not
mapped, the access still faults and names the address the instruction used.
Register windows are not aliased.

### Other stops, and what each opt-in models

- **Main RAM past the image.** **Observed:** SetupHeap at `0x14fc64` is
  passed start `0x90a434` and size -1. That is the end of the second
  `PT_LOAD`. SetupThread at `0x14fc48` is passed
  stack base `0x1fc0000`. On the 32 MB path, `0x19d58c`-`0x19d5c8` ask
  `mem_malloc` `0x150680` for `0x16a5bcc` bytes. `mem_initHeap` `0x150598`
  fills the block with `0xa5`, one byte per iteration, at `0x1505c8`.
  **Model:** `EE.install_modelled_main_ram` creates a missing page from
  `0x90a434` up to `0x1fc0000` zeroed on first access. That zero is the
  absence of a store, not a measured retail value. Below `0x90a434` nothing
  changes, so the null-based faults at address 4 and `0x18` still fault.
- **EndOfHeap**, syscall 62 at `0x3529c0`, accepted only for return address
  `0x353138`, by its own opt-in `EE.install_modelled_end_of_heap` (moved out
  of `install_modelled_boot` in round 8, audit R7-3). That caller compares v0 with the requested break.
  **Inferred:** a size of -1 ends at the stack base. **Model:** v0 =
  `0x1fc0000`. It is not a recovered kernel limit.
- **GIF and VIF1 channel words.** **Observed:** `0x350680` waits through
  `0x350190`, which spins while bit `0x100` of the channel word at offset 0
  is set. It then writes offsets `0x10`, `0x20` and 0, setting `0x101`.
  `sceGsSyncPath` `0x34fe78` tests bit `0x100` at `0x10009000` and
  `0x1000a000`, `0x10003c00` under mask `0x1f000003`, and `0x10003020`
  under mask `0xc00`. **Model:** `EE.install_modelled_dma_idle` makes offsets
  0, `0x10` and `0x20` of those two channels storage, plus the two status
  words. A read of offset 0 returns the stored word with bit `0x100` clear.
  That is a channel that has finished at once. No transfer reaches a GS.
  Other channels still fault.
- **VPU_STAT.** **Observed:** `0x34ff5c` and `0x34ff7c` are CFC2 of control
  register 29 into `$6`, then a test of bit `0x100`. **Model:**
  `EE.install_modelled_vpu_stat` returns 0 for that encoding only. Any other
  COP2 instruction still stops.
- **FlushCache**, syscall 100 at `0x352c60`, accepted only for return
  addresses `0x19d628` and `0x355744`, by its own opt-in
  `EE.install_modelled_flush_cache` (round 8, audit R7-3). Only the mirror
  test and later tests install these two. The round-5 and round-6 tests do
  not. **Observed:** each is a `lui` that
  replaces its register, and neither path reads v0 first. **Model:** v0 = 0.
  This emulator has no cache, so nothing else changes.
- **The startup semaphore.** **Observed:** the allocator waits at `0x3b61c8`
  on the id at `0x5075d0`, which startup's CreateSema at `0x35c084` stores at
  `0x35c098`. So `engine_init` runs on the machine startup left, after
  startup stops at `0x35c108`. sp is reset to the test stack. gp is the
  startup value, `0x56c170`. Startup's CreateSema calls create ids 1 and 2,
  so the waits in `engine_init` use id 4. Five modelled deliveries of
  `0x19b6e4` pass them, as in round 6.

### Executed

Each seed and each fixture form give the same result.

1. Startup stops at `0x35c108` reading `0x80000000`, as in round 5. With
   write recording on, the only stores that overlap `0x7cfd40` or
   `0x82c408` are the two 16-byte `.bss` clears of 0 at `0x14fbe0`. The test
   then empties the log, so each later stage is checked on its own.
2. `engine_init` passes both uncached stores. Right after `0x19d4b4`, the
   cached halfword at `0x1800094` is `0x2300` (address `0x21800080` +
   `0x14`). Right after `0x19d520`, the cached halfword at `0x188c194` is
   `0x2bc0` (address `0x2188c180` + `0x14`). `tex_relocate` returns to
   `0x19d498` and `0x19d4f0`. The GIF words hold `0x101` at `0x1000a000`,
   `0x188c180` at `0x1000a010` and `0x8c08` at `0x1000a020`. The semaphore
   ids at `0x8400f0` and `0x8400f4` are 3 and 4.
3. `mem_malloc` returns `0x90a600`, stored at `0x8400e8`. The size
   `0x16a57cc` is stored at `0x8400ec`. `mem_initHeap` runs its fill loop to
   the end. The last byte, at `0x1fafdcb`, is `0xa5`. This is about 166
   million instructions, all executed. **Observed:** the ELF's third
   `PT_LOAD` is `0x1800000` to `0x1918200`. Both blocks sent to the GIF are
   in it, and both are inside the heap block. After the fill, the halfwords
   at `0x1800094` and `0x188c194` are `0xa5a5`. **Inferred:** retail reuses
   that segment as heap once the uploads are sent. Whether a retail DMA has
   finished reading it by then is Unknown.
4. **Next stop:** `engine_init` calls `0x19ba98` at `0x19d638`. That calls
   `0x355d68` at `0x19baa8`, which calls `0x355608` at `0x355db0`.
   FlushCache at `0x35573c` returns. At `0x35574c` the 4-byte read of
   `0x1000e010` faults, return address `0x355744`. The ring word and the
   particle word have no store in this stage.

**Observed, past the stop:** `0x35574c` tests bit `0x20` of `0x1000e010`
and, when set, writes `0x20` back. `0x355764` reads `0x1000c000`. The
function calls the wrappers at `0x352dc0`, `0x352de0` and `0x352df0`, which
load syscall numbers `0x78`, `0x79` and `0x7a`. The loop at
`0x355800`-`0x35580c` repeats the `0x352df0` call until v0 is nonzero.
**Inferred:** this is SIF setup, and that loop waits for the IOP. There is
no IOP here, so no model is added for `0x1000e010`, `0x1000c000` or those
syscalls. The stop is where the EE starts waiting on the other processor.

**Not reached:** `0x17a3a0` at `0x19d6f8` (the `texcache_init` path),
`particle_init` `0x18e648` at `0x19d818`, and the waiter at `0x19d828`.

### Death sequence on the same machine

The death sequence then runs on that machine, with TerminateThread
installed, as in round 6. The test heap the fixture uses is moved to
`0x4000000`, above 32 MB. The game heap now covers `0x90a600` to
`0x1fafdcc`, and the default test heap at `0x1000000` sits inside it.
**Executed:** the loader stops on the 4-byte write to address 4 at pc
`0x18ec10`, return address `0x1e502c`. Request byte `0x41b720` is 254.
World reconstruction `0x14e808`, `Player_ctor` `0x1a1d28`, `texcache_init`
and `particle_init` are not called. No store overlaps the ring or particle
word. Both are 0. No call is stubbed.

**`texcache_reset` at `0x179b30`:** still blocked. That store adds `0x18` to
the pointer at `0x7cfd40`. In this session that word is 0 from the `.bss`
clear, and `texcache_init`, which round 4 saw write `0x7cfe00` there, is
after the SIF stop. The loader also faults at `0x18ec10` before reaching it.

**Unknown:** the IOP side of SIF setup and what `0x1000e010` holds at
`0x35574c`. Retail heap contents before the fill. Whether retail DMA
finishes before the first poll. Retail ids, interrupt timing, file loading,
world reconstruction, player construction and playable arrival. Native
`blocked_death_reload` stays.

## Reproduce, round 7

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_mirror.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_reload_mirror.py local/SLUS_209.73 --seed 7
```

Each seed: two engine_init stops at the SIF status read, and two
particle-reset faults. Each run executes the heap fill twice, about 340
million instructions. No stubs. Success output reports counts only.
