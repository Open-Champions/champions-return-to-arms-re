# The non-literal `generateMonster` arguments

US `SLUS_209.73` v2.00. This note closes the item in `docs/script-items.md` section 10:
"the 15 non-literal `generateMonster` class names were not classified". It covers how each
of the 15 calls produces its arguments, which class names they can reach, which seed draws
pick them, and what the original factory does with each name.

| File | What |
|---|---|
| `tools/generator_names_census.py` | the classifier (a symbolic replay of each call's statement), the factory probe, and the difftest of the shuffle functions |
| `tools/test_generator_names_census.py` | 11 tests on authored synthetic scripts, no game file needed |

Labels: **Executed** means run on the original script machine in `tools/ee_emu.py` against
`tools/ref_amx.py`, or run through the original `world_objectFactory`. **Observed** means
read from the script bytecode by the tool. **Inferred** means reasoned from those two.
Everything below is a count. No script, level, object or string from the disc is named. The
class names quoted are rows of the executable's factory table (`docs/objects.md`).

## 1. Correction: which argument is computed (Observed)

`generateMonster(generator, className)` is native `ss` (`docs/script-items.md` 5.1). The
script machine pushes the arguments last first, then the byte count, then `SYSREQ.C`.
`tools/items_census.py` takes the cells just before the call as the arguments. When one
argument is an expression, its instructions sit between the pushes, so the earlier census
can name the wrong argument. Replaying each statement symbolically gives:

| Generator | Class name | Calls | Scripts |
|---|---|---:|---:|
| literal | literal | 121 | – |
| literal | row of a string table | **12** | 2 |
| row of a string table | literal | **3** | 2 |
| total | | 136 | 11 |

The earlier census reported "class not literal 15". **12** of those calls compute the class
name. In the other **3**, the class name is a literal and the *generator* is computed. Those 3
add 2 literal class names that the 121 calls do not use, so there are 18 distinct literal
class names in all (the earlier census counted 16).

Every computed argument has the same shape. It is the address of row *i* of a two-level
array (`table[i]`):
`PUSH.C base; LOAD.pri i; BOUNDS n; POP.alt; IDXADDR; MOVE.alt; LOAD.I; ADD; PUSH.pri`.
The row address is base + 4i + cell(base + 4i), and the array has n + 1 rows. No call
builds a string at run time, reads one from a parameter, or uses a native to produce it.

## 2. The class-name tables (Observed, then Executed)

The 12 computed class names read 3 string tables in 2 scripts: 35 rows in all, 28 distinct
strings. **No table is ever written.** Every reference to an address inside a table (its
indirection vector or its row bytes) is an element read. So each table's rows are a closed
set of candidates.

The index is never a literal or a plain counter. In both scripts it is an element of a small
cell array (the *index table*), `index = itable[k]`, and k only steps through that array.
In each script the index table is filled by one entry function that calls `getRand`. That
function is a Fisher-Yates-style shuffle: `j = getRand() % i`, swap, for i from the top down
to 1.

| Script | Class tables | Rows | Index table | Shuffle draws per run | Rows the index can reach |
|---|---:|---:|---:|---:|---|
| first | 1 (6 calls, two index variables) | 17 | 5 cells | **4** | 4 of 17 |
| second | 2 (6 calls, one index variable) | 9 + 9 | 6 cells | **7** (two `getRand() % 3` choices, then a 5-step shuffle) | 3 of 9 in each |

**Executed.** `generator_names_census.py --difftest` runs each shuffle entry function on
both the original machine (`scr_interpret` and the original `SYSREQ` path, as
`tools/difftest_amx.py` places a shipped script) and on `ref_amx.Machine`. `getRand` is
answered on both sides by the same sequence: `seed = seed × 0x19660d + 0x3c6ef35f`, result
`seed >> 16` (`docs/spec/script-builtins.md` 87), from a random start. Each case compares the
native trace, the error, the result, the machine words and every data byte.

| Seed | Functions | Runs | Differ | Host faults | `getRand` calls per run |
|---|---:|---:|---:|---:|---|
| 20973 | 2 | 600 | 0 | 0 | 4 and 7, always |
| 7 | 2 | 600 | 0 | 0 | 4 and 7, always |

A deliberately desynchronised sequence (the original side one draw ahead) made 9 of 10
cases differ, so the comparison does detect a change. The index-table values seen after the
shuffle are the same set on both seeds. They are always valid row numbers, and they reach
**10 of the 35 rows**: 9 distinct class names.

The index variables hold 0 in the image. A spawn that ran before the shuffle would read
row 0. In the first script row 0 is reachable anyway. In the second, whether a spawn can run
before the shuffle depends on which entry points the level starts first (Unknown here).

## 3. What the factory makes of them (Executed)

Every literal and every candidate was run through the original `world_objectFactory`
0x159c94 in `tools/ee_emu.py`. After `pool_new`, every call is stubbed, and the constructor
is taken to be the first call that receives the block in a0. (`items_census.factory_probe`
stubs the first call after `pool_new` instead. The `prefix Orc` row of `docs/objects.md`
calls 0x217edc before its constructor, so that probe stopped on 2 names.)

| Names | Constructor | Skeleton constructor 0x2a5af4 | No object | 24 bytes or more |
|---|---:|---:|---:|---:|
| 18 literal | 17 | **1** | 0 | 0 |
| 28 table candidates | 27 | 1 | 0 | 0 |
| 9 reachable candidates | 9 | **0** | 0 | 0 |

The 9 reachable candidates reach 6 constructors. In `docs/objects.md` these are the rows
`== Cyclops / CyclopsGrey / CyclopsNew` (0x2566d4), `prefix MaleDarkElf` (0x25afd8),
`prefix Orc` (0x2a0954), `== Scorpion` (0x2a4d68), `== Vampire` (0x2b69d0) and
`prefix fgoblin, Goblin` (0x26a624). The one candidate that reaches the Skeleton constructor
sits in a row the index never takes.

**The Skeleton rise can be reached from a shipped script.** It does not come through a
computed class name. It comes through a literal one. **2 of the 3 generator-computed calls**
pass a literal class name that the factory builds with the Skeleton constructor 0x2a5af4.
`ScriptGenerator_spawn` sends an object whose dynamic type is exactly `Skeleton` to AI state
0x17 (`docs/script-items.md` 5.1). So those 2 calls rise whenever their generator object is
a `ScriptGenerator`. Whether it is depends on the level records (Unknown in this note; see
the generator census). `docs/script-items.md` 7 said that no shipped call reaches the
Skeleton constructor. That holds for the 121 fully literal calls only.

## 4. The computed generators (Observed)

The 3 generator-computed calls read 2 tables (10 and 17 rows) of generator *names*. In one
script the index is a loop counter over all rows. In the other, one call takes a counter
that the script steps down, and the other takes **`getRand() % 16`: one shared-seed draw per
call**, which picks one of the first 16 of the 17 rows. Which of those names belong to
`ScriptGenerator` objects is a level-record question (Unknown here).

## 5. Limits and the intern table (Observed)

- No literal and no candidate is 24 bytes or longer. The `strcpy` overrun of the 24-byte
  entries at 0x5d32c8 cannot happen from shipped scripts.
- At most 16 distinct class names per script, counting every candidate row (6 counting
  literals only). The s8 count at 0x4f8409 stays far below 127.

## 6. Seed draws (Observed, and Executed for the shuffles)

| Where | Draws |
|---|---|
| the shuffle entry functions (class-name index tables) | 4 per run in one script, 7 per run in the other, every run |
| the random-generator call | 1 per call (`getRand() % 16`) |
| `generateMonster` itself, and the row read | none |

These are `getRand` calls, which advance the shared seed (`docs/script.md` 87). A client
that runs the shuffle with a different number of draws, or skips it, desynchronises the
seed in a net game. It also picks different monsters.

## 7. What the native client should do

1. **Evaluate the arguments as the script machine does.** It needs no special case: these
   are ordinary two-level array reads of constant data. A client that runs the bytecode
   faithfully gets the right name. No table is written, so a client may also pre-resolve the
   candidates from the image.
2. **Run the shuffle entry functions with real `getRand` draws** (4 and 7 per run). The
   reachable class names are then the 9 above. Each reaches a constructor, and none is
   `Skeleton`.
3. **The Skeleton rise is the blocker, not the computed names.** The 2 literal-Skeleton calls
   behind computed generators make the AI-state-0x17 rise reachable. The native client
   currently refuses the rise. Implement it, or keep the refusal counted, once the generator
   census says which of those generator names are `ScriptGenerator` objects.
4. **Fix the census label.** Count 12 calls with a computed class name, 3 with a computed
   generator, and 18 distinct literal class names.

## 8. Runs

- `python3 tools/generator_names_census.py --disc <private copy> --elf <SLUS_209.73>
  --difftest --cases 300 --seed 20973` and `--seed 7`: 136 calls in 11 scripts, the shapes
  above. Difftest: 600 runs, 0 differences, on each seed. Output in
  `local/census/gen-names-census-*.txt` (untracked). The `--detail` files there hold the
  strings and stay untracked.
- `python3 -m unittest tools/test_generator_names_census.py`: 11 tests.

## 9. Open

- Which of the computed and literal generator names are `ScriptGenerator` objects (needs the
  level records).
- Whether a spawn in the second script can run before its shuffle and so read row 0.
- The first script's 5-cell index table holds only 4 distinct values after the shuffle. Which
  cell repeats, and whether the round counter ever reads it, was not traced.
