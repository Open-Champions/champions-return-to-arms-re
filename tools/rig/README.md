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
| `examples/boot-to-hub.rig` | script: power-on to a controllable character in the first level |

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
core without break point support (no `--break`, no `--screen-text`; somewhat faster);
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
most N bytes), `hexN` (N bytes).

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
