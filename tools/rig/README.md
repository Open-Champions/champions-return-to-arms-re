# rta_rig — the game running headless, driven by a script

A small C++ program that runs Champions: Return to Arms (SLUS-20973) on the core of the
[Play!](https://github.com/jpd002/Play-) PlayStation 2 emulator, with no window, no video,
no sound and no speed limit, and lets a script press buttons, read and write memory, apply
patches, log named addresses, stop at code addresses and save or load machine states.

Play! was chosen because it needs **no PS2 BIOS file**: it has its own high-level BIOS.
You need your own disc image of the game. Nothing from the game and nothing from Play! is
in this directory; what the rig has shown so far is in `docs/issues/live-rig.md`.

| File | What it is |
|---|---|
| `rig.cpp` | the runner (one file) |
| `CMakeLists.txt` | builds it against a Play! checkout whose path you give |
| `rig.py` | wrapper: finds the runner and the disc, loads the repository's symbol files, interactive sessions |
| `examples/boot-to-hub.rig` | script: power-on to a controllable character in the first level, offline |
| `examples/net-solo.rig` | script: power-on to a net game on one machine, through the game's developer LAN start |
| `examples/pair-start.rig` | script: two joined machines, power-on to one lockstep net game |
| `examples/pair-arena.rig`, `pair-k1.rig`, `pair-k2.rig` | scripts for a joined pair: into the arena and through its opening; the two divergences found first |
| `examples/pair-chars-start.rig`, `pair-chars.rig`, `pair-chars-same.rig` | a pair whose slot 0 is a melee class; characters with level 25 and skills written in one tick on both machines; the same-class spin case |
| `compare.py` | lines up the tick logs of two machines and finds the first difference; diffs two memory dumps |
| `fuzz.py` | runs many joined pairs unattended on seeded random input and groups the divergences (`--patches FIXES`: every fix section) |
| `sweep.py` | one pair per class skill, both players the same class with that skill; `--predict-audit <file>` on the runner lists what each prediction call left changed |

## Build

Tested on Apple silicon macOS with Apple clang 21, CMake 4.4 and Ninja 1.13, against Play!
commit `83700b2c31e593bc94e845b4b31b797be84dda59`. Qt is not needed.

```
brew install cmake ninja
git clone --recurse-submodules https://github.com/jpd002/Play-.git local/play
cmake -G Ninja -S tools/rig -B local/rig-build \
      -DPLAY_SOURCE_DIR=$PWD/local/play -DCMAKE_BUILD_TYPE=Release
cmake --build local/rig-build --target rta_rig
```

`local/` is ignored by the repository. Options: `-DRTA_RIG_BREAKPOINTS=OFF` builds the
core without break point support (no `--break`, no `--screen-text`; about twice as fast
inside a level — use a second build directory and point `RTA_RIG` at its `rta_rig`);
`-DRTA_RIG_PLAY_LOGS=ON` compiles Play!'s own log calls in (slow, for looking at the
emulator).

## Run

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 -I -B tools/rig/rig.py --frames 600 --watch g_randSeed:x32 --watch g_drawFrame:u32
```

The wrapper passes everything on to `local/rig-build/rta_rig`, adding `--disc`, `--data
local/rig-out/playdata` and one `--sym` per symbol file (`names.tsv`, `symbols/*.tsv`), so
names can be used wherever an address is expected. The runner can also be called directly;
`rta_rig --help` lists the options.

The disc image is only read. Everything the emulator writes — its configuration, the
memory-card directory with the game's save files, state files — goes under the `--data`
directory; keep that, and any logs and dumps, under `local/rig-out/`.

### Options

| Option | Meaning |
|---|---|
| `--disc <image>` | disc image (ISO and whatever else Play! reads) |
| `--data <dir>` | emulator data directory; a new directory is a blank memory card |
| `--arg <text>` | argument for the game's `main()`; repeatable |
| `--load <state>` | load a state after booting |
| `--save-at-end <state>` | save a state when the run ends |
| `--frames <n>` | stop after n frames of this run |
| `--script <file>`, `--do "<command>"` | script commands (below); `--do` commands run after the file |
| `--interactive` | then read commands from standard input; the machine stands still while waiting |
| `--until <expr:type> <op> <value>` | stop when true; exit code 3 if `--frames` comes first |
| `--sym <file.tsv>` | symbol file: hex address, tab, name |
| `--watch <name=expr:type>` | a value to log; `--watch-file` takes one per line |
| `--log <file.tsv>`, `--log-every <n>`, `--log-on-change` | write the watches per frame |
| `--break <addr[,opts]>`, `--break-log <file>` | log the registers when the EE reaches an address |
| `--pc-histogram` | where the EE program counter is at each vertical blank |
| `--fps-every <n>` | print the emulation speed every n frames |
| `--profile` | sample the machine thread; print where the wall time went |
| `--net-shim <a.b.c.d>`, `--net-log <file>`, `--net-log-all` | the libnet shim (below) |
| `--machine A\|B`, `--link listen:<path>\|connect:<path>`, `--bus delay=N,jitter=N,loss=N,seed=N` | two joined machines (below) |
| `--tick-log <file>`, `--tick-watch <name=expr:type>`, `--tick-at <addr>` | one row per lockstep tick (below) |
| `--predict-audit <file>` | what each call of `net_predictLocalPlayer` 0x131d88 left changed, outside a short ignore list (`AuditIgnored`): address, symbol, calls, first tick, old and new word, and the object class and field (pool) or allocating function (heap); also whether any grid cell or the off-grid list changed the order or the set of its real objects |
| `--predict-trace <file>`, `--trace-range <addr:length[:stride][,all][,name=N]>`, `--trace-ticks <lo:hi>`, `--trace-raw <n>` | which code writes the watched words: writers gathered by site, writing block and call chain (below) |
| `--fp-round nearest\|up\|down\|zero` | force a floating-point rounding mode on this machine (Play! runs the EE with round-toward-zero); for float-mismatch experiments |
| `--no-code-protect`, `--video-thread`, `--throttle`, `--play-logs` | emulator behaviour, see `--help` |

A **frame** is one vertical blank of the emulated machine. Frame numbers count from the
start of the run, also after `--load`.

Exit codes: 0 done, 2 bad option or script, 3 a condition timed out, 4 `--frames` ended
before the script did, 5 a state could not be saved.

### Expressions and types

An address is an expression: a symbol name, a number (`0x…` hex, otherwise decimal),
`+ - *`, parentheses, `[x]` for the 32-bit word stored at x, and `$pc`, `$ra`, `$sp`,
`$a0` … for EE registers. A watch is `name=expr:type` or just `expr:type`:

```
g_randSeed:x32
hp=g_players+0xac:f32
x=[g_players+0x43d8]+0x10:f32        # field 0x10 of the object the record points at
```

Types: `u8 s8 u16 s16 u32 s32` (decimal), `x8 x16 x32` (hex), `f32`, `strN` (text, at
most N bytes), `hexN` (N bytes), `crcN` (a 32-bit checksum of N bytes, for comparing a
block between two machines). `&` is available in expressions as well.

### Script commands

One per line, run in order; `#` starts a comment.

| Command | Effect |
|---|---|
| `wait N` | let N frames pass |
| `at N` | wait until frame N of this run |
| `until <expr:type> <op> <value> [timeout N] [continue]` | wait for a condition; `op` is `== != < <= > >=`, or write `<expr:type> changed`. On time-out the run stops with exit code 3 unless `continue` is given |
| `press B`, `release B` | hold or let go of buttons: `cross circle square triangle l1 l2 l3 r1 r2 r3 start select up down left right`, joined by `+` |
| `tap B [hold [gap]]` | press for `hold` frames (default 3), then wait `gap` frames |
| `tapuntil B period <condition> [timeout N]` | tap every `period` frames until the condition holds |
| `stick L\|R x y` | stick position, 0–255, 128 is centre |
| `pad B [lx ly [rx ry]]` | the whole controller state at once (`none` for no buttons) |
| `<frame> B [lx ly [rx ry]]` | the same from a given frame on: an input table, one line per change |
| `press2`, `tap2`, `stick2`, `pad2` … | the same for the second controller port |
| `poke <expr:type> <value>` | write memory (`x…` types take hex digits) |
| `pnach <file> <section>` | apply the `patch=1,EE,<addr>,word,<value>` lines under `[section]` of a PCSX2 patch file; `*` means every section, `Net test*` a prefix. Old and new word are printed |
| `save <file>`, `load <file>` | save or load a machine state |
| `dump <expr> <length> <file>` | write memory to a file |
| `show <watch> …` | print values now |
| `echo text`, `log on\|off`, `sync [token]` | print a line; switch the frame log; print a marker and flush |
| `break <addr[,opts]>`, `unbreak <addr>` | add or remove a break point |
| `netshim` | replace the game's libnet entry points (needs `--net-shim`) |
| `fuzz <seed> <frames> <groups>` | seeded random input: `move`, `rstick`, `fight`, `cast`, `potion`, `use`, `dpad`, `select`, `start`, `l3r3`, `idle`, joined by commas |
| `ontick <N> <command>` | run `poke`, `pnach`, `dump`, `show`, `echo`, `save`, `press`, `release`, `break` or `quit` inside lockstep tick N. `ontick N break <addr>,val=tick=g_netFrame:s32` for many functions, on both machines, followed by `ontick N+2 quit`, logs which functions ran in those ticks; the difference between the two logs is the code that ran on one machine only |
| `A: <command>`, `B: <command>` | only on that one of two joined machines; the other lets the same number of frames pass |
| `quit` | end the run |

Patches are applied when the script says so, which must be after the executable is in
memory (any frame of a booted run is). Code patches take effect at once: the rig discards
Play!'s translation of the touched page.

### Break points

`--break <addr>[,option…]` logs a line each time the EE reaches the address: frame, pc,
return address (with the name of the function it lies in), `a0`–`a3`, `t0`–`t3` (the fifth
to eighth arguments in this program's calling convention), `v0`, `sp`, `f12`–`f15`.

| Option | Adds |
|---|---|
| `name=N` | a label (default: the symbol at the address) |
| `str=REG`, `wstr=REG[:LENREG]` | the C string, or the 16-bit string, a register points at |
| `mem=EXPR:LEN` | LEN bytes at an address |
| `val=NAME=EXPR:TYPE` | a typed value |
| `ret` | a second line with `v0`, `v1`, `f0` when the function returns |
| `limit=N` | stop logging after N hits (hits are still counted) |
| `quiet` | count only; the totals are printed at the end |
| `collect` | gather the strings of each frame and print them once per change |
| `stop` | end the run there |

A break point takes effect where a translated block is entered. Function entries always
start a block, and so do return addresses; an address in the middle of straight-line code
does not, and is silently never reported.

`rig.py --screen-text` sets `collect` break points on the game's three text-drawing entry
points (`text_drawWideImpl`, `text_drawWrapped`, `text_drawWrappedCentered`), which gives
a running transcript of the text on the screen — the only way to see menus without video.
The transcript is game text: keep it under `local/`, do not commit it.

### Finding the code that writes a word

Play! has no write break points, and a real break per block would change the machine's
timing. With `--predict-trace` the rig installs its own EE executor (a subclass of
Play!'s) and, at the first traced prediction call, puts a break point on every instruction
of the executable. Play! then compiles a call to the break-point filter into the head of
every translated block; the rig's filter looks at the watched ranges and lets the block
run on, so nothing leaves the executor and the run is the same as without the trace. A
word that differs from its shadow was written by the block entered before. The output has
one line per site, writing block and call chain (the chain is kept from `jal` return
addresses), with a count and the first and last tick; `--trace-raw N` adds the first N
writes one by one in `<file>.raw`.

A range is watched inside prediction calls only; `,all` watches it everywhere (use it with
`--trace-ticks` for anything but a few words: every block of the game then compares the
range). `:stride` folds an array into its element's fields. The writer is known to the
block; read the store in `tools/dis.py`. A word written by Play!'s kernel emulation rather
than by game code is blamed on the block that happened to be running. Recompiling every
block with a check costs about a minute per machine at the start.

```
python3 -I -B tools/rig/fuzz.py --states local/rig-out/run4 --seeds 402:1 --patches FIXES --no-rerun \
    --extra "--predict-trace local/rig-out/t-%M.tsv --trace-range 0x631134:4,all --trace-ticks 4741:4933 --trace-raw 4000" ...
```

### The libnet shim

`--net-shim <address>` gives the machine an IPv4 address and prepares replacements for the
ten places where the game's netcode enters Sony's network library (`sceInetCreate`,
`sceInetSendTo`, `sceInetRecvFrom` and seven more; the list with addresses is in
`rig.cpp`, class `CNetShim`, and in `docs/issues/live-rig.md` 4d). The script command
`netshim` installs them: each entry is overwritten by a four-instruction stub that stores
to an address the rig has claimed (0x1e000000 + 4 × call number), and the rig does the
call's work on the host. It works in both build flavours.

At present the "network" is a bus inside the one process: a datagram sent to the machine's
own address or to a broadcast address can be received from the next frame on, anything
else is logged and dropped. That is enough for the game's developer LAN start to run a
net game on one machine (`examples/net-solo.rig`); joining two runners is the next step.
`--net-log` records every call and the first bytes of every datagram.

A state saved inside a net game does not contain the shim's sockets. Loading it with
`--net-shim` given again works for one machine (the stubs are in the saved memory).

### Two machines

Two runner processes can be joined into one net game. They are connected by a local
socket (`--link listen:<path>` on one, `--link connect:<path>` on the other) and advance
strictly together: at every vertical blank each sends the other its frame number and the
datagrams its game sent since the last one, and waits for the other's message for the same
frame. What a machine receives therefore depends on frame numbers only, and a pair of runs
repeats exactly from the same states, scripts and `--bus` seed.

`--bus delay=N,jitter=N,loss=N,seed=N` says what happens to a datagram that crosses:
`delay` frames are added to every one, up to `jitter` more to each (which reorders them),
and `loss` in a thousand are dropped; all of it is drawn from a generator seeded by `seed`.
`stallat=F,stall=N` is an outage: nothing sent during the N frames from frame F crosses.
With no `--bus` a datagram sent in one frame can be received in the next.

The launcher does the pairing:

```
python3 -I -B tools/rig/rig.py pair local/rig-out/run1 \
    --script tools/rig/examples/pair-start.rig --save-at-end local/rig-out/run1/%M.zip
python3 -I -B tools/rig/rig.py pair local/rig-out/run2 --bus delay=10,jitter=6,loss=100,seed=6 \
    --a-load local/rig-out/run1/a.zip --b-load local/rig-out/run1/b.zip --script my.rig
python3 -I -B tools/rig/compare.py ticks local/rig-out/run2/a.tick.tsv local/rig-out/run2/b.tick.tsv
```

Machine A is 192.168.1.132 and plays slot 1; machine B is 192.168.1.134 and plays slot 0
(the game's lobby orders its peers that way). Each has its own data directory
(`local/rig-out/pair-a`, `pair-b`). Without `--a-load` / `--b-load` both are booted with
the argument `--net`. `--a-arg X` / `--b-arg X` give one machine an extra option; `%M`
in an option becomes `a` or `b`. Both run the same script; lines tagged `A:` or `B:` act
on one machine while the other waits the same number of frames. In the output directory
each machine leaves `a.out` / `b.out`, the shim's log, and the **tick log**.

The tick log (`--tick-log`, needs break point support) has one row per lockstep tick,
written when the EE reaches 0x13aee8 — the instruction after the tick's task pass in
`net_frameLoop`, where `g_netFrame` still holds the tick's number and the shared seed and
the positions are the ones the game is about to hash. The launcher's default columns are
the tick, the shared seed, the level, and for both players position, facing, action
state, hit points, mana, gold, experience and a checksum of each bag, plus the sync record
the game stored for the previous tick and the out-of-sync flags. Columns named `l_…` are
per machine by design (`rig.py`, `tick_watches`). More are added with `--tick-watch`.

`compare.py ticks` lines two tick logs up by tick and reports the first tick at which a
shared column differs, and every column that ever differs. `compare.py mem` diffs two
memory dumps taken in the same tick (`ontick N dump 0 0x2000000 file` on both machines)
and groups the differences by symbol; its ignore list is a table at the top of the file,
and `--baseline` leaves out every byte that already differed at an earlier tick when the
tick logs still agreed. Two machines in sync differ in about half a megabyte (pose
buffers, render lists, the peer table, the order of some heap blocks), so without a
baseline the diff is mostly that.

### Fuzzing two machines

```
python3 -I -B tools/rig/fuzz.py --states local/rig-out/run1 --out local/rig-out/fz \
    --seeds 200:36 --frames 12000 --jobs 5 --try-patches \
    --levels strife,drunare,hub --groups "move,fight,potion,use,dpad,select,start" \
    --bus "none;delay=3,jitter=3,loss=50"
```

runs one pair per seed from the two states (`a.zip`, `b.zip` in `--states`, as left by
`examples/pair-start.rig`). Seed number *i* takes level *i* mod L, input mix *i* mod M and
bus setting *i* mod B from the lists (lists are separated by `;`, except levels). A pair
whose level is not the states' own is sent there by writing the pending level in one
tick on both machines. Each pair gets fresh copies of the two memory-card directories,
plays `fuzz <seed> <frames> <mix>` on both controllers, and is compared with
`compare.py`. A pair that differs is run again to see that it repeats, and with
`--try-patches` once more per "Net test" section of the patch file (the lag sections
excepted: they move the timing, which hides a coincidence without fixing it) to see
which section removes the difference.

By default the sections for the two known causes, K1 and K2, are applied on both machines
(`--patches none`, `--patches FIXES` for every fix section, or `--patches "name;name"`,
changes that). `--no-rerun` skips the second run of a pair that differed. `--prelude FILE` puts script
lines before the fuzz; `--extra "…"` passes options to `rig.py pair` (for example
`--extra "--b-arg --fp-round --b-arg nearest"`); `--keep` keeps the logs of pairs that
agreed too.

A pair in which one machine dropped the other at the first differing tick (random input
found the pause menu's kick entry, or left the game) is reported as a kick or leave, not
as a desync. `rig.py pair` kills a machine that is still running two minutes after the
other has ended (`RTA_PAIR_GRACE`).

The printed summary gives pairs, ticks, and per class of divergence — the shared columns
that differ at the first differing tick, with player numbers folded together — the pairs
in it and the sections that removed it. `OUT/summary.tsv` has one line per pair with the
first tick of every differing column; the logs of divergent pairs stay under `OUT/`.

### Interactive sessions

Loading a state costs a few seconds, and more for the code to be translated again. To
explore without paying that for every step, keep one runner alive:

```
python3 -I -B tools/rig/rig.py session start --screen-text --load local/rig-out/states/x.zip
python3 -I -B tools/rig/rig.py session send "tap cross" "wait 60" "show g_frontendState:u32"
python3 -I -B tools/rig/rig.py session stop
```

`send` prints what the runner wrote while it carried the commands out. The machine does not
advance between commands. `--name N` runs several sessions side by side.

### Repeatability

The emulated machine is deterministic: the same state and the same script give the same
frame log and the same memory, byte for byte (checked over 286 frames of play, all 32 MB).
A script written against one state therefore keeps working. Two things break this: a
different memory-card directory, and anything that changes the emulator build.

## What the rig changes in Play!'s behaviour

Nothing in Play!'s source is modified. Three things are done differently from Play!'s own
front ends, all in `rig.cpp`:

- The video handler has no thread. Play!'s handlers take every graphics register write as a
  queued call for a video thread; the rig's null handler lets the calls queue up and runs
  them on the machine thread once per frame. `--video-thread` restores the usual
  arrangement.
- `mprotect` is wrapped so that the rig can count, and with `--no-code-protect` refuse,
  Play!'s write-protection of host pages that hold translated code.
- The frame limiter preference is off unless `--throttle` is given.
