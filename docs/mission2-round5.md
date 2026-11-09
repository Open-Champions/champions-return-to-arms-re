# Mission 2 round 5: in-range use, portals, and the SIF DMA

2026-11-09. Adds to round 4 at `d17b46f`
([mission2-round4.md](mission2-round4.md)). Round 4's tests are not edited.

**STATUS: MORE.** PushTrigger, NPC, Trigger, and portal uses run end to end
under the fixtures below. The portal constructor reads its lumps from the
disc. `game_loadLevel` passes the SIF DMA under an opt-in model and stops on
a VU1 store.

Labels: **Observed** means read from the executable's instructions, with
addresses. **Executed** means the original functions ran in `tools/ee_emu.py`
and the cited test asserts the result. **Inferred** and **Unknown** are
stated as such.

## Syscalls: reuse, plus one new opt-in

Round 4 used a local handler for syscalls 124 and 37. This round copies
`tools/ee_emu.py` and `tools/test_ee_emu.py` unchanged from
`t3/research-death-reload` commit `543ea930` (see
[death-reload-sequence.md](death-reload-sequence.md) on that branch). Every
round-5 boot then opts in to its `install_deci2_kputs` and
`install_terminate_thread`. Their contracts are the death-reload ones. They
are not duplicated here.

**Observed, the caller's contract at `0x35edd0`.** `sceSifSetDma` `0x352da0`
loads v1 = `0x77` (119) and traps at `0x352da4`. `sceSifDmaStat` `0x352d80`
loads v1 = `0x76` (118). The only caller this path reaches is the SPU helper
`0x35ed90(source, destination, size, mode)`:

- Mode 0 returns -1 at `0x35eddc` and makes no syscall.
- Otherwise the helper stores source, destination, size, and 0 at
  `0x8f60c0`–`0x8f60cc`, then calls `sceSifSetDma(0x8f60c0, 1)` at `0x35edc8`.
- `0x35edd0` moves the result to s0. A zero result returns -1.
- With a nonzero result and mode 1, `sceSifDmaStat(result)` is called at
  `0x35edf0`. The call repeats while its return is not negative (`bgez` at
  `0x35edf8`), and the helper then returns 0.
- A nonzero result with any other mode returns 0 with no poll.

Two `jal` sites reach the helper, and both pass mode 1:

- `sound_flushSpuCommands` `0x210cd0` at `0x210e28` does not read the result.
- `sample_uploadToSpu` `0x213ff0` at `0x214120` compares it with -1 at
  `0x214130`.

**Inferred** from those branches: a nonzero 119 result is a queued transfer
id, and a negative 118 result means the transfer finished. The retail id
values and the queue-full case are **Unknown**.

**Executed, the model.** `EE.install_modelled_sif_dma` is opt-in. It accepts
119 only with return address `0x35edd0`, a0 = `0x8f60c0`, and a1 = 1. It
returns a modelled id counting from 1 and appends
`(id, source, destination, size, attribute)` to `emu.sif_dma`. It reads no
source byte and writes nothing, because there is no IOP memory. It accepts
118 only at return address `0x35edf8` for an id it returned, and gives -1, so
the first poll reports the transfer finished. That is the loop's exit
condition, not a measured time. The other 119 callers (`0x350dd4`,
`0x355ac4`, `0x356d80`, `0x35bdfc`, `0x367884`) and 118 callers (`0x350d68`,
`0x3678a0`) still trap. The model is labelled in the method's docstring.
Evidence: [model](../tools/ee_emu.py#L808-L873),
[unit test](../tools/test_ee_emu.py#L720-L775). The test checks the default
trap, each rejection, the recorded descriptor, and that no store touches the
descriptor.

## Why the PushTrigger use was not entered

**Observed:** `Player_interact` `0x1b2640` calls the prompt through vtable
`+0x68`/`+0x6c` at `0x1b2814`. It passes the text buffer `sp+0x440` in a1 and
the slot in a2, and keeps the prompt result in s5 (delay slot `0x1b2824`).
At `0x1b281c` it loads the buffer's first halfword. When that halfword is 0,
`0x1b2820` branches to `0x1b2b98` and skips both the display and the use.
That is the gate round 4 left **Unknown**.

When the text is not empty:

- The text-width call `text_widthWide` `0x181bf8` at `0x1b29f4` uses the
  font word at `0x4f7100`.
- The use test starts at `0x1b2b1c`. A nonzero display-only argument (s7)
  skips it.
- For prompt result 1, `0x1b2b34`–`0x1b2b44` AND the pad word at `+0xc` with
  the use mask `0x41b9c0[slot]`. When the result is nonzero:
  - the slot is stored at `g_scriptActivePlayer` `0x4d8ae4` (pc `0x1b2b70`);
  - the use is called through vtable `+0x70`/`+0x74`, with the slot in a1
    (`0x1b2b84`).
- Prompt result 2 tests bit `0x10` of the same pad word.

**Observed:** `PushTrigger_prompt` `0x1eca94` runs offline when
`g_networkMode` `0x402791` is 0. It walks each `key` property (call
`0x1ecbf8`) through `script_runByName` `0x1ed694`. A key script that returns
0 selects the lock text, and the prompt returns 0. With no key left, it reads
`message` (`0x1ecc18`):

- Present: `text_lookup` `0x173c84`, `wstr_copy` `0x19e854`, then return 1
  (`0x1ecc4c`).
- Absent: a zero halfword is stored at `0x1ecc50`, then return 1.

Round 4's trigger had no properties, so its prompt returned 1 with an empty
text, and the gate skipped the use.

**Executed:** these cases ran on both seeds:

| Case | Gate halfword, prompt result | Use `0x1ecc70` | `0x4d8ae4` over sentinel |
|---|---|---|---|
| no properties | 0, 1 | not called | unchanged, no store |
| synthetic `message` | `0x4e`, 1 | called once, a1 = 0 | 0, store at `0x1b2b70` |
| `message` and `action` | `0x4e`, 1 | called once | 0, store at `0x1b2b70` |
| `message`, use mask 0 | `0x4e`, 1 | not called | unchanged |
| `message`, pad word 0 | `0x4e`, 1 | not called | unchanged |

`0x4e` is the first character of the text `text_lookup` returns for a miss.
The synthetic value is not a disc text key. With `action`, `PushTrigger_interact`
calls `obj_runActionScripts` `0x14dcc8` with raw = 1, because `offOnly` is
absent. `script_runByName` then receives the synthetic action name once.
Without `action`, neither is called.
Evidence: [push use](../tools/difftest_mission2_r5.py#L222-L266).

## NPC use

**Observed:** the creature constructor reads `ShowName` (call returning to
`0x109f58`), and `Creature_interact` reads `dialogScript` at `0x116d24`.
`obj_getPropStr` lower-cases the key and compares it case-sensitively, so the
properties must be written `showname` and `dialogscript`. The NPC vtable `0x50f590` slot 13
is `Creature_interactPrompt` `0x116d50`, and slot 14 is `Creature_interact`
`0x116bd8`. The use path:

1. requires the name word at `+0x368` and the slot's object word `0x4dcec8`
   (record `+0x43d8`);
2. tests the facing product at `0x116cf4`;
3. calls `menuMutex_tryAcquire` `0x22fc04` at `0x116d00`;
4. stores the slot at `0x4d8ae4` (pc `0x116d28`);
5. runs the `dialogScript` value through `script_runByName`.

**Executed, both seeds.** With the player object at (10, 10, 0) and the NPC
at the origin facing angle 0:

- The prompt returns 1 with text `0x4e`, and `Creature_interact` runs.
- The mutex call returns 0, and the word at `0x4fe53c` goes from 0 to 1.
- `0x4d8ae4` is 0, stored at `0x116d28`.
- The synthetic dialog name reaches `script_runByName` once.

At the NPC's own position, the prompt writes no text and returns 0. The use,
the mutex, and the script are absent, and `0x4d8ae4` keeps its sentinel.
Which test inside the prompt refuses is not traced.
Evidence: [NPC use](../tools/difftest_mission2_r5.py#L269-L300).

## Trigger use

**Observed:** `Trigger_ctor` `0x1ecdf4` takes the property list in a2. At
`0x1ecdf8` it moves a2 to a3 for `GameObject_ctor`, and it stores the `t`
value at `+0x5c` (`0x1ecebc`). Its flags are 3, without the interactable bit
`0x100000` that `Player_interact` tests at `0x1b2788`, so the box query never
offers a Trigger for use. Its use is `Trigger_run` `0x1ecf3c`. For each
player counted at `0x4d8ae0`, it calls slot 17, `Trigger_contains`
`0x1ed238`, at `0x1ed09c`. On entry, it stores the slot at `0x4d8ae4`
(`0x1ed15c`) and calls `script_runByName(+0x5c)` at `0x1ed160`.

**Executed, both seeds.** With `w=100`, `h=100`, and a synthetic `t`, and
the player object at the trigger's position:

- `Trigger_contains` runs once.
- The script name reaches `script_runByName` once.
- `0x4d8ae4` is 0, stored at `0x1ed15c`.
- The byte at `+0x60` reads 1.

At x = 1000 there is no script call and no store, and `+0x60` stays 0.
Evidence: [trigger use](../tools/difftest_mission2_r5.py#L303-L328).

## Portal lump from the disc

**Observed:** `JumpGate_ctor` `0x27c694` asks `res_find` `0x17365c` for
lumps. `res_find` calls `lump_load` `0x173558` at `0x173718`, which works in
four steps:

1. Try `lump_findLoaded` `0x17306c`.
2. On a miss, call `cd_findFile` `0x1724fc`. It formats the name with `%s;1`
   (`0x533eb8`), upper-cases it, and searches the table at the word in
   `0x41bf84`. In this image that word is `0x7ba8a0`. Entries are 32 bytes:
   the name, then the sector at `+0x10` and the size at `+0x14`. The count
   is at `+0x7d00`.
3. A miss there prints and stores to address 0 at `0x17363c`. That is round
   4's fault, because the table is empty in a fresh image.
4. A hit allocates the rounded size plus `0x100`, then calls
   `cd_readBlocking(name, destination, 0, 0)` at `0x1735e4`. `cd_readAsync`
   `0x1729e8` replaces the zero size with the directory size (`movz` at
   `0x172a74`).

The boot code that fills the table is **Unknown**; it was not traced.

**Executed, both seeds:**

- **Without the planted table:** the constructor requests `mapicons.lmp`,
  reads nothing, and faults at `0x17363c` (address 0).
- **With the table** planted from the disc directory that holds `INNOVAT1.GOB`
  (real names and sizes, synthetic sectors `0x1000 + index`):
  - The constructor requests `mapicons.lmp` and then `jumpgate.lmp`.
  - Each is read whole from the disc, one file per name, and both are
    registered as the last two lumps.
  - `sample_uploadToSpu` sends 21 modelled DMAs, all from `0x214120`, each
    with destination word 0 and attribute 0.
  - The constructor returns 0 over a sentinel, with flags `0x00100008` and
    vtable `0x50dbe8`.

The destination word comes from the caller's IOP buffer address, which is
not set in this fixture. Its retail value is **Unknown**.
Evidence: [portal constructor](../tools/difftest_mission2_r5.py#L331-L359).

## Portal use

**Observed:** `JumpGate_interactPrompt` `0x27d7a0` returns 0 in these cases:

- the byte at `+0x4f` is set;
- `task_isRunning` `0x19e5e8` with a0 = `0x547e10` returns nonzero;
- a `script` property returns 0.

On the first prompt it sets `+0x4d` and calls `jumpgate_addCurrentLevel`
`0x27db60` and `hud_showMessage` `0x1d92a0`. When `g_jumpGateDestCount`
`0x8e3c30` is 1, it writes the lock text and returns 0. If another listed
player is farther than 96 units, it writes a wait text and returns 0.
Otherwise it writes the use text and returns 1 (`0x27d954`).
`JumpGate_interact` `0x27d754` calls `JumpGate_openMenu` `0x27da24(slot, 0, 0)`
when `menuMutex_isHeld` `0x22fc2c` returns 0, or in a net game.

**Executed, both seeds.** `g_levelName` `0x41b721` is set to `innovat1`.

- **With no prior destination:** the count becomes 1 (`innovat1`). The prompt
  returns 0 with text `0x4e`, and neither the use nor the menu is called. The
  travel word `0x500ae8` keeps its sentinel.
- **With `hub` planted as the one prior destination:**
  - The list becomes `hub`, `innovat1`, and the prompt returns 1.
  - `JumpGate_interact` runs, `menuMutex_isHeld` returns 0, and
    `JumpGate_openMenu(0, 0, 0)` runs once.
  - Its two `task_add` `0x19e4a0` calls install `jumpgate_menuRun`
    `0x27dd74` and `jumpgate_menuDraw` `0x27e2d0`.
  - `0x500ae8` goes from the sentinel to 0, and `fx.lmp` is read from the disc
    during the call.

The menu tasks are not run. Choosing a destination and writing the next world
name are **Unknown**.
Evidence: [portal use](../tools/difftest_mission2_r5.py#L362-L396).

## `game_loadLevel` past the DMA

**Executed, both seeds.** The setup is the round-4 DMA fixture: `game_clearLevel`
stubbed and `0x44fe18` set to the base name. In addition, the three opt-ins are
installed, the directory table is planted, the font word is set (below), and
the test heap top is raised to `0x01f00000`, where the emulator stack starts.

- `0x35ed90` is called 653 times, all with mode 1, from exactly the two sites
  `0x210e28` and `0x214120`.
- The model records 653 descriptors with ids 1..653. The first is
  `sound_flushSpuCommands`' batch at `0x875c00`, size `0x10`.
- Twenty-three disc reads each hit one file. The first is `equipmnt.lmp` and
  the last two are `linnovat.lmp` and `loadmisc.lmp`.
- The run stops on a 4-byte write at `0x1100ffcc`, pc `0x14877c`, inside
  `light_writeVuConstants` `0x148728`. It is called once in the run, from
  `gfx_beginFrame` `0x19d8b0` at `0x19d8d4`.

That address is in the VU1 data window the function writes through
`0x1100c000`. The emulator does not map it, and this round does not model it.

Without the directory table, one DMA (the `0x875c00` batch) passes, then the
first lump request faults at `0x17363c`, with no disc read.
Evidence: [loader](../tools/difftest_mission2_r5.py#L399-L450).

## Fixture stubs and supplied state

Every round-5 boot installs these. They are not retail results.

- `cd_readBlocking` `0x172ad0` reads one disc file of the requested name at
  the requested offset. Size 0 reads the whole file, per `0x172a74`. A missing
  or duplicate name returns 0.
- `mem_allocTagged` `0x14ff88` is the test bump allocator. `mem_realloc`
  `0x14fe80` returns its pointer argument. `mem_free` `0x150198` returns 0,
  because bump blocks have no header for the real function to read.
- `FlushCache` `0x352c60` and `dbg_checkStack` `0x19d9f8` return 0.
- The loader cases also stub `game_clearLevel` `0x1e4e88` to return 0.

The boots also supply this state:

- `pool_init` and `handle_initPool` run first. The head sentinel is replaced
  by `0x847268`.
- The `cd_findFile` table is planted as described above.
- The font word `0x4f7100`: the fixture makes boot's call at `0x323f6c`,
  `res_find(0x5548c0, 0x5548d0)`, which loads that lump from the disc. It then
  stores the result at `0x4f7100`, standing in for boot's own store at
  `0x323f78`. Boot function `0x323dcc` is not run.
- The player is slot 0, from `player_initNewCharacter` with a null `r11`
  ([mission2-round4.md](mission2-round4.md)). Its GameObject is linked at
  record `+0x43d8` by the fixture.
- The use mask, pad words, destination list, level name, and mutex word are
  planted where each case says.
- Property values and script names are synthetic, drawn from
  `random.Random(seed)`.

## What the native client can implement

- Gate a use on a non-empty prompt text, then on the pad word AND the slot
  mask, then call the use with the slot. Store the slot in the active-player
  word first.
- Read a PushTrigger's prompt from `message`. Run `action` through the action
  scripts, raw unless `offOnly` is set.
- NPC talk: take the menu mutex, store the slot, and run `dialogscript`.
- Trigger: on entry into the rectangle, store the slot and run `t`.
- Portal: append the current level on the first prompt. Refuse while only one
  destination is listed. Otherwise open the menu by adding the run and draw
  tasks.
- Resolve lumps through a name table with whole-file reads.
- Treat `sceSifSetDma` in the SPU helper as an accepted id, and the stat poll
  as finished. This is a model, labelled as such. Refuse other SIF callers.
- Refuse `game_loadLevel` at the VU1 store in `light_writeVuConstants`.

## Still unknown

- The boot function that fills the `cd_findFile` table.
- The retail SIF ids, the queue-full case, the IOP destination address, and
  whether the IOP-side upload completes.
- VU1 data memory and every loader stage after `0x14877c`.
- Which test in `Creature_interactPrompt` refuses at the NPC's own position.
- What `script_runByName` finds with no level script loaded, and the bodies of
  the named scripts.
- Running the jumpgate menu tasks, the destination choice, the next-world
  write, arrival, and destination-list save/load.

## Reproduction

Run from this worktree on the Mac mini, with unittest preloaded so
`tools/dis.py` does not shadow the standard library:

```sh
export PYTHONDONTWRITEBYTECODE=1
D=~/malik-champions/open-champions/private-validation/rta-disc
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["x"]+sys.argv[1:]; runpy.run_path("tools/difftest_mission2_r5.py",run_name="__main__")' local/SLUS_209.73 "$D" --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["x"]+sys.argv[1:]; runpy.run_path("tools/difftest_mission2_r5.py",run_name="__main__")' local/SLUS_209.73 "$D" --seed 7
```

Each seed takes about two minutes and prints four PASS lines and the stub
list.
