# Mode-B scheduler and terminal-condition boundary

Research date: 2026-10-27. Prior evidence pins: research-arena `17810bb`,
research-arena-match `d4f58da` (audited through round 11). The mode reference and
its existing difftest are imported unchanged from `d4f58da` in `4b20d40`.
This report adds executions, not native-client implementation or live gameplay.

## Documented contract

- **Observed:** `arena_begin` `0x304f5c` returns when mode B at `0x4f7120`
  is clear. In mode B with mode A clear it calls the preload body `0x306440`,
  stores three waves at `0x8e733a`, clears saved-monster count `0x8e7340`, then
  calls `arena_startWave(1)` `0x305ed4` (`0x304f80..0x304fa0`). It does not
  reset the current-wave halfword. Initial arena initialization separately
  stores -1 at `0x8e7338` (`0x304da4..0x304db8`).
- **Observed:** start-wave adds its argument to the wave halfword and subtracts
  it from waves-left; the current wave is interpreted signed for monster-level
  scaling and recipe division (`0x305f44..0x305f7c`, `0x3060ac..0x3060d8`).
  It arms a 180-visit intro and clears intermission. With saved count zero,
  quotient/remainder of wave / 3 selects a recipe modulo the signed recipe
  count at `0x503886` (`0x3061e8..0x30626c`).
- **Observed:** recipes start at `0x503868`, stride six. Header high nibble
  supplies the group count; signed class-index bytes follow it. Remainder zero
  repeats the first class, remainder one uses one fewer group, and remainder
  two uses the full group count (`0x3062ac..0x3063a8`). Count scaling, cap,
  active-slot adjustment, group-remainder distribution and ring RNG follow
  `ref_arena_modes.wave_plan`; each requested class comes through the pointer
  table at `0x5037f0`. These are spawn requests to `0x3065fc`, not proof that
  every requested creature constructs and ticks successfully.
- **Observed:** preload `0x306440` examines the upcoming three waves, suppresses
  duplicate class indices, and calls factory `0x14f6c8` once per distinct
  referenced class. A non-null factory return takes a virtual destruction path
  with argument 3 (`0x306530..0x306550`). **Unknown:** destructor flag semantics;
  the new probe returns null from this factory and does not execute destruction.
- **Observed:** task `0x306b78` decrements the positive intro once per visit and
  latches zero to -1 on the following visit (`0x306ba4..0x306be0`,
  `0x3071f4..0x307264`). With mode A clear, it requests the empty-wave walker
  only on frame multiples of 128 and when the end flag is clear
  (`0x306e40..0x306e90`). Empty count starts intermission at one and calls
  `arena_endRound` `0x307ebc`; it does **not** set terminal flag `0x503894`.
- **Observed:** intermission tests the old counter against 480 offline or 960
  online, while incrementing it (`0x306c04..0x306c2c`). If waves remain,
  expiration calls `arena_nextWave(1)` `0x305e9c`. Otherwise it requests the next
  level: recipe index `((signed_wave + 1) / 3) % recipe_count`, header low nibble
  indexes name-pointer table `0x503798`; it writes orientation -1 and calls the
  name-copy and close services (`0x306c30..0x306d4c`). The last recipe wraps to
  recipe zero. There is no terminal-win comparison in this path.
- **Observed:** the mode-A kill-limit comparison is a separate branch
  (`0x306de8..0x306e3c`). Mode-B exhaustion of playable slots instead chooses
  saved-life retry or terminal defeat (`0x306e98..0x306fa4`); these retry/defeat
  paths were already executed in the pinned round-11 oracle.

## New original-function executions

**Executed:** `tools/difftest_arena_live_scheduler.py`, seeds 20973 and 7, one
through four active players, offline and online. Each of 16 configurations
executes 30 independently reconstructed wave states: two rotations of all five
runtime recipes, all three remainders, including both table-wrap boundaries.
The private tables are read from the executable at runtime; no table contents
or game strings are embedded or printed. Runtime validation checks every recipe
group's signed index resolves to a nonzero class pointer and every map index is
within the seven-entry name table. This is structural evidence, not a native
class-name/constructor mapping or a portable shipped-data export.

**Executed:** original begin, preload, start-wave, ring-step, task, score-tick,
end/rank and same-level next-wave/preparation bodies. Every intro/intermission
visit is executed. Original spawn requests, ring-step count, final RNG, monster
level, wave counters and level-name pointer requests are compared against the
pinned reference and runtime tables. Each configuration produces 32 preload
requests and ten level requests; spawn counts depend on active-player count.
The occupied-grid control prevents intermission despite kill score 32767 and
PvP limit 1, then starts intermission when its walker fixture reports empty.

**Partial / fixture boundaries:** active slots and active-slot count are fixed
services; records have positive HP and two lives. Player constructor/allocation,
spawn body, preload factory, grid population/walker, audio, UI, string copy and
level close/load are stubbed. Grid emptiness is supplied, not earned through
combat. Default unselected callees return zero. No score purchase candidates
are supplied; qsort tie order is not exercised. Each wave case starts with fresh
fixture state and the selected wave number. These are not 30 naturally cleared
waves or a continuous match across actual level loads. The level-name pointer
is checked but the name-copy/load implementation is not executed.

## Consequence for the native refusal

**Inferred:** this scheduler describes repeating survival progression, not a
finite five-recipe victory. A native implementation must not invent a final
victory at recipe-table exhaustion: both the addressed modulo operation and
the executed wrap cases request continued progression. **Unknown:** a global
natural mode-B victory condition elsewhere, if any; finite tests of these
bodies cannot exclude an external caller or event. Establishing one requires
an addressed external writer/control path and an original-code execution.

**Unknown:** normal-input kills, later creature ticks, a natural completed
match, rendered results, fixed reward awards/collection, actual next-level
loading, destructor semantics, complete class/factory bindings, purchase qsort
ties and signed-wave overflow gameplay. The bounded scheduler is documented;
the full live-match gate remains partial and must continue to refuse these
unsupported paths. No Play!, PCSX2, console or native gameplay was run here.

## Round 2: later boundaries and terminal input

Research date: 2026-10-27; starting pin `2fbfaa46`.

**Executed:** additive `tools/difftest_arena_terminal.py` runs original task
`0x306b78` at reconstructed intermission-expiry states for waves 29, 44, 149,
299, 2999, 29999 and 32765, offline and online (14 cases). Every case requests
exactly the runtime-table pointer predicted by `level_record_index`, leaves
mode B enabled and terminal/session-exit words zero, and does not call
`0x307ebc`. These are later signed-positive continuation samples, not earned
waves, overflow evidence, or proof that every possible wave continues.

**Executed:** the same probe constructs exhausted player records (zero HP,
negative lives, zero saved-life snapshot and dead countdown), excludes the
128-frame empty-grid visit, and calls the original task for 1–4 active slots,
offline and online, with both terminal-input choices (16 cases). The original
terminal flag store executes at `0x306f94`; the original end/rank bodies run,
intermission stays zero, and no same-wave retry is requested. Each case then
executes the task with its selected button held at fade zero, the immediately
preceding float bit pattern below 1.0, and exactly 1.0. Neither earlier value
accepts the button. At 1.0, confirm calls shutdown and executes the original
level picker `0x304bc8`, requesting recipe-zero's runtime-selected level pointer
while retaining mode B. Cancel clears mode B, sets session exit to one and
requests no level copy. This extends isolated round-1 input vectors into a
bounded defeat-to-input sequence; it is not a natural match completion.

**Observed (heuristic static cross-reference inventory):** `Elf.analyze()` on
the private executable identifies direct terminal-word store references at
`0x304dcc`, `0x306dd4`, and `0x306f94`; the latter is executed above. This
inventory follows the tool's register-pair heuristic, not an exhaustive alias,
indirect-store, DMA, script or external-event proof. No absence-of-victory claim
is justified by this inventory. Private outputs retain addresses/counts only.

**Partial:** active-slot services, player construction, grid, qsort, rendering,
record lookup/restoration services, shutdown, string copy and loader remain
fixture boundaries. The confirm fixture supplies an allocated zero-filled
synthetic saved record; it does not establish valid persistent-record content.
An initial null saved-record probe faulted at `0x3070a8`; using allocated state
corrected that fixture, without changing emulator/reference APIs or vectors.
Fade values are supplied, not produced by a rendered screen. No rewards were
asserted or inferred from restart behavior.

**Unknown:** an external natural mode-B victory, normal-input kills and later
creature ticks, results rendering, fixed award calculation/collection, actual
next-level loading and signed-wave overflow. Priority 1 remains partial;
priorities 2 and 3 remain unresolved. Settling these requires tracing the
external event/writer (if present), a combat-input-to-tick original execution,
and addressed award/load services rather than adding zero-return fixtures.
