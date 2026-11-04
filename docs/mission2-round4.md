# Mission 2 round 4: archive open and the in-range prompt

2026-11-03. Adds to round 3 at `7f8e967`. That round's loader stubs
`lump_load` and `0x171fd8` and faults on a 4-byte read at address 4, pc
`0x001e59ac`. Its `Player_interact` returns the record address before the
box query ([mission2-compose.md](mission2-compose.md)). This round does not
replace those tests.

**STATUS: MORE.** The archive open and a PushTrigger prompt run. The loader
still does not reach that open, and the prompt's use function is not entered.

## Archive open

**Observed:** `gob_loadAll` `0x1737d8` calls `cd_readBlocking` `0x172ad0`
with the name, the destination, the size, and the offset in the four
argument registers. The first call asks for `0x800` bytes at offset 0.
Later calls use the running offset and the rounded lump size.
`FlushCache` `0x352c60` is called next. The fixture stubs it to return 0,
so its body is not entered.

**Observed / Executed** by [the archive case](../tools/difftest_mission2_r4.py#L198-L219).
The read stub is the loading-readiness file adapter: one disc file for the
requested name, then those bytes at the requested offset
([adapter](../tools/difftest_mission2_r4.py#L62-L88)). `g_levelTexName`
`0x44fe18` is set to the base name before the call. `mainloop` writes that
word at `0x321110`; this direct call does not execute that store. With only
`g_levelName` set, the tex request is the name `.tex` and misses.

For `innovat1.gob`, both seeds:

- the first read is `0x800` bytes at offset 0, and it hits one file
- one read is `innovat1.tex`, size `0x5000`, offset 0, one file
- every read hits one file
- the lump count at `0x41bf7c` is written to 3, from an explicit 0
- `lump_findNthByExtension` `0x171fd8` on the level lump, using the
  executable's extension string at `0x53daa8`, returns a non-zero record
- the word at that record `+4` is inside the test heap `0x01000000`–
  `0x01700000` and is mapped

That word is the load at pc `0x001e59ac`. Round 3 faulted there because the
stubbed `0x171fd8` returned 0. The pointer here belongs to the test
allocator, not to `mem_initHeap`. `mem_allocTagged` `0x14ff88` is the bump
allocator at `0x01000000`, aligned to 256, and `mem_realloc` `0x14fe80`
returns the same pointer. The retail heap is still the block `engine_init`
obtains from `mem_malloc` before `mem_initHeap` `0x150598`.

## Where `game_loadLevel` stops

**Observed / Executed**, both seeds, after `pool_init`, `handle_initPool`,
and `particle_init` `0x18e648`. That init returns 2, replacing a sentinel in
the return register. Syscall 124 is accepted only for function `0x10`, and
syscall 37 only for the eight return addresses whose next instructions do
not read the result. Those handlers return 0. Every other syscall stops the
run. This fixture does not change their default trap in `ee_emu.py`.
Evidence: [handler](../tools/difftest_mission2_r4.py#L91-L104) and
[clear fixture](../tools/difftest_mission2_r4.py#L223-L233).

`game_clearLevel` is entered and does not return. The next instruction not
completed is a 2-byte write at address `0x18`, pc `0x00179b30`, inside
`texcache_reset` `0x179b08`. The return address is `0x17e498`.

**Observed / Executed** when `game_clearLevel` `0x1e4e88` and `mem_free`
`0x150198` are stubbed to return 0, so neither body is entered, and
`0x44fe18` holds the base name. No disc read happens. The stop is
`sceSifSetDma` `0x352da0`, syscall 119 (`0x77`) at pc `0x00352da4`.
**Observed:** the caller at `0x35edd0` copies that result and branches on
it. This fixture stops on the syscall, so that copy is not executed. The
retail result is **Unknown**, and the fixture does not invent one.
Evidence: [DMA fixture](../tools/difftest_mission2_r4.py#L237-L251).

## Constructors

**Observed / Executed:** `handle_initPool` `0x1a17d0` replaces sentinel
`0xa5a5a5a5` at the free-list head `0x864ea8` with `0x847268`. The store is
at pc `0x001a181c`. `GameObject_ctor` `0x14cb10` then returns 0, replacing a
sentinel in the return register. One shared-seed step is
`seed * 0x19660d + 0x3c6ef35f`. Sentinel `0xa5a5a5a5` at object `+0x44` is
replaced by that result shifted right 16 bits. The round-3 write fault at
pc `0x001a1780` was this constructor's `handle_link` with a null free list.
Evidence: [constructors](../tools/difftest_mission2_r4.py#L128-L152).

On a fresh pool, both seeds:

| Constructor | Result |
|---|---|
| `PushTrigger_ctor` `0x1ec900` | returns, flags `0x0010000b` over sentinel `0xa5a5a5a5` |
| `Trigger_ctor` `0x1ecdf4` | returns, flags `0x3` over the same sentinel |
| `NPC_ctor` `0x29df04` | returns, flags `0x01100028` over the same sentinel |
| `JumpGate_ctor` `0x27c694` | 4-byte write at address 0, pc `0x0017363c` |

`0x17363c` is the missing-file store in `lump_load`. The portal's lump name
was not supplied. A resident lump for that request is **Unknown**.

## In-range prompt

**Observed:** `Player_interact` `0x1b2640` loads the record float at `+0xac`
and takes `bc1t` to `0x1b2c90` when that float compares `<=` the other
compared register. With the record still zero, the box query is not called.
That is the round-3 return.

**Observed:** `player_initNewCharacter` `0x1b1d70` copies `r11` to `r21` at
`0x1b1ddc`. A null `r21` takes the branch at `0x1b22d8` and skips the byte
load at `0x1b22e0`. A nonzero leftover in `r11` was the address `0x17700`,
which is unmapped, and the load faulted. What a real nonzero `r11` points at
is **Unknown**. The other arguments are slot 0, model 0, a one-letter name,
four zero appearance bytes, null stats, kind 1, and team 0.

**Observed / Executed:** with `r11` null the init returns 0, replacing a
sentinel in the return register. It stores hit-point bits `0x4e6e6b27` at
`0x4d8b9c` over sentinel `0xa5a5a5a5`, stores 0 at the maximum word `+0xb0`
over sentinel `0x5a5a5a5a`, and stores 0 at record `+0x43d8` over sentinel
`0xa5a5a5a5`. A `PushTrigger` and a `GameObject` are then constructed at the
same position. The fixture, not `player_initNewCharacter`, stores the
GameObject at `+0x43d8`. That store is the word loaded at `0x1b26ac`.

`Player_interact` calls `world_collectObjectsInBox` `0x14a928` once,
`PushTrigger_prompt` `0x1eca94` once, and `getPropStr` `0x14f4c0` and
`strlen` `0x3b8dc4` twice each. Those four run for real. The prompt's
return is captured at its return address and is 1. The hook does not
replace the prompt. `PushTrigger_interact` `0x1ecc70` is absent from the
call list. The fixture plants `0x40` at the use mask `0x41b9c0` and at pad
`+8` and `+0xc`. The call does not write those three words. The return
value is `0x4d8ac0` (record `+0x30`) after the return register was sentinel
`0xa5a5a5a5`. Which later test skips the use is **Unknown**.
Evidence: [prompt](../tools/difftest_mission2_r4.py#L157-L194).

## Fixture stubs

Every round-4 boot installs these replacements. They are not retail results.

- `cd_readBlocking` `0x172ad0` reads one file of the requested name from the
  disc directory, at the requested offset, into the destination. A missing
  or duplicate name returns 0.
- `mem_allocTagged` `0x14ff88` is the test bump allocator at `0x01000000`,
  256-byte aligned. A zero size or a size above `0x2000000` returns 0.
- `mem_realloc` `0x14fe80` returns its pointer argument.
- `FlushCache` `0x352c60` returns 0. `dbg_checkStack` `0x19d9f8` returns 0.
- The syscall handler above returns 0 only for the two accepted cases.

The DMA fixture also stubs `game_clearLevel` and `mem_free` to return 0.
`particle_init` on the clear fixture is the original function.

## What the native client can implement

Under these fixtures:

- Open `<base>.gob` with `cd_readBlocking(name, destination, size, offset)`,
  starting with `0x800` bytes at offset 0, and read `0x5000` bytes of
  `<base>.tex` from the name at `0x44fe18`. After that, the world-entry word
  at `+4` is a mapped pointer in the test allocator. Do not treat a missing
  tex name as success: the request becomes `.tex`.
- Call `pool_init` and `handle_initPool` before `GameObject_ctor`.
  `PushTrigger`, `Trigger`, and `NPC` constructors then return with the flags
  above. The portal constructor stops at the missing-file store.
- After `player_initNewCharacter` with a null `r11`, run `Player_interact`
  against a PushTrigger at the linked object's position through the prompt
  that returns 1. Refuse the use at `0x1ecc70`.
- Refuse `game_loadLevel` at `texcache_reset` `0x179b30` when clear is
  entered, and at `sceSifSetDma` when clear is not re-entered. Do not invent
  the DMA result.

## Still unknown

The `sceSifSetDma` result and every loader stage after it, including the
archive open inside `game_loadLevel` rather than by the direct call.
`texcache_reset` on a texture that has a ring slot. Portal construction once
its lump is resident. The test that skips `PushTrigger_interact` after a
prompt result of 1. NPC and Trigger prompts. Arrival, and save/load of the
destination list.

## Reproduction

From this worktree, with unittest preloaded so `tools/dis.py` does not
shadow the standard library. The disc argument is the extracted disc
directory, not an ISO.

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_r4.py",run_name="__main__")' local/SLUS_209.73 <disc-dir> --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_r4.py",run_name="__main__")' local/SLUS_209.73 <disc-dir> --seed 7
```

On the Mac mini the disc directory is
`~/malik-champions/open-champions/private-validation/rta-disc`. Both seeds
pass. Existing compose, offer, and travel vectors are not edited.
