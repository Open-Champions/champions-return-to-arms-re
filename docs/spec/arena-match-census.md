# Offline mode-B arena recipe census

US `SLUS_209.73` v2.00. Executed 2026-10-21 with the owner's executable, one active
player, `tools/arena_recipe_census.py`. The tool reads the five recipe records at
`0x503868` and the 30-entry class table at `0x5037f0` at run time. Only counts and
class-table indices are reported here; no names or recipe bytes are recorded.

The first recipe requires:

| Wave | Total | Class-table index:count |
|---:|---:|---|
| 0 | 2 | 3:2 |
| 1 | 3 | 1:1, 3:2 |
| 2 | 4 | 0:1, 1:1, 3:2 |

Across all five recipes' first three waves, with one active player, the rank by
spawn count is: 4:11, 25:11, 16:9, 6:8, 3:6, 20:5, 11:4, 12:4, 15:4,
7:3, 1:2, 17:2, 21:2, 26:2, 0:1, 8:1. Indices 3, 1, and 0 are the
minimum class set for the first recipe's waves 0–2, in that order of first use.

**Verification:** `python3 tools/difftest_arena_modes.py
local/SLUS_209.73 --quick --seed 20973` passed
302/302, including original `arena_startWave` calls compared with the wave model.
This is function-level execution with a constructed test state, not a live match.
