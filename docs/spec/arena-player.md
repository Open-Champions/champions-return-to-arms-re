# Arena player replacement: bounded constructor contract

US `SLUS_209.73` v2.00. **Executed** with
`tools/difftest_arena_player.py` on seeds 20973 and 7. The model compares all
319 final bytes directly written by `Player_ctor` `0x1a1d28`, its 16 external
call targets in order, its player-record link, and the shared seed. The base
`Creature_ctor` and resource/world services are fixed fixtures; their effects
are not part of the 319-byte comparison. The owner disc executable is read only
at run time.

## Constructor calls and draws

The direct call sequence is `Creature_ctor` `0x109d68`, `0x148af8`, `0x14a4f0`,
`sprintf` `0x3b7ef0`, `res_find` `0x17365c`, `sprintf`, `res_find`, `0x355490`,
`0x1707b0`, `0x1b2470`, `obj_runEveryFrame` `0x14f248`, `0x183820`,
`player_recalcStats` `0x1b6458`, `0x3b60c0` twice, and
`game_rebuildAlivePlayers` `0x1e72f8`. The call sites and exact target list are
in `tools/ref_arena_player.py`. None of the constructor's **own** instructions
draws the shared seed `0x404464`. Its `Creature_ctor` call normally includes
one draw in `GameObject_ctor` `0x14cb10`, as separately executed in
`docs/spec/object-system.md` §2.2. The present constructor difftest stubs that
base call, so its seed is unchanged. Resource and world call side effects remain
outside this comparison.

## Direct fields

All offsets in this table are from the 0x590-byte Player block; complete widths
and values, including the small light records, are in the reference model.

| Fields | Direct constructor effect and instruction address |
|---|---|
| `+0x48`, `+0x3c8`, record `+0x43d8` | Player vtable `0x511308` at `0x1a1dc8`; slot at `0x1a2200`; record link at `0x1a221c` (record base `0x4d8af0`, stride `0x4c30`) |
| `+0x3d8,+0x3f0,+0x408,+0x420,+0x438`, `+0x4b8`, `+0x588` | zero handle heads and spell link at `0x1a1ddc–0x1a1ea8` |
| `+0x4d0…+0x50d` | light colour/intensity and reset fields at `0x1a1e38–0x1a1e9c`; `+0x4d2,+0x4d4,+0x4d6,+0x4da,+0x4dc,+0x4de = 188`, `+0x4d8,+0x4e0 = -64`, `+0x4e4,+0x4ec = 300.0`, `+0x4e8,+0x4f0 = 1/90000` |
| `+0x544,+0x548,+0x54c,+0x550,+0x554,+0x558` | model and appearance handles, zero in the absent-resource fixture, `0x1a1ffc–0x1a21f4` |
| `+0xc,+0x1c,+0xb0` | flags `0x4040`, radius 12.0, turn rate 1.4 at `0x1a21f8`, `0x1a2244`, `0x1a223c` |
| `+0x5c…+0x8c`, `+0x36c…+0x3a8` | movement/animation scratch and 16 status counters cleared at `0x1a224c–0x1a229c` |
| `+0x470,+0x58c,+0x461,+0x4b2` | attack duration 1.6, neutral state 2, animation variant 1, idle voice threshold 3600 at `0x1a22d4–0x1a22ec` |
| `+0x3cc,+0x450…+0x45c,+0x462…+0x490,+0x4a8,+0x4ae,+0x4b0` | action/ability/attack latches reset, sound handle `-1`, `0x1a1f08–0x1a2334` |
| `+0x18`, record `+0x4bc8` | vertical position set to 0.75 at `0x1a245c`; countdown cleared at `0x1a24b4` |

The constructor also sets animation-event fields in each resolved model
part definition at `0x1a2394–0x1a241c` and writes the model table pointer cell
`0x4ebbb4` at `0x1a1eec`. This difftest supplies one authored part for all five
lookups, so the reference compares the final aliased cell values. Independent
resource resolution and distinct part assets have not been executed here.

## Arena replacement boundary

In `arena_startWave` `0x305ed4`, the old player's virtual destructor is called
at `0x306028`, `pool_new(0x590)` at `0x306030`, and the returned block is passed
to `Player_ctor` at `0x30604c` as `(block, spawn-position pointer, facing, slot)`.
The constructor links the new object to the full player record. The spawn-point
picker is `arena_pickSpawn` `0x3050a4`, already modelled and difftested in
`tools/ref_arena_modes.py` / `tools/difftest_arena_modes.py`; the base
`GameObject_ctor` copies its chosen position, then `Player_ctor` writes the
vertical component 0.75. `player_respawn` `0x1bd040` has a separate executed
wrapper contract in `docs/spec/arena-match-core.md` and uses a different
placement path. At shutdown, `arena_shutdown` `0x304fb0` clears arena pointers
and tasks; it does not itself destroy the player, as that same contract shows.

## Tick and damage reuse

The full `Player_run` `0x1a5030` state machine has an independently executed
reference and difftest in `tools/ref_player.py` / `tools/difftest_player.py` and
`docs/spec/player-tick.md`; states 2 (neutral), 1 (melee), 0 (ranged), and the
reached movement/ability branches are covered there. The movement call
`Player_move` `0x1b4020` and collision path are covered by
`t3/research-combat-walk` in `docs/spec/combat-movement.md`.
`Player_takeDamage` `0x1b5330` and `Player_processDamage` `0x1b2cc0` are
executed in `t3/research-combat`, `docs/spec/combat-player-defence.md`.
These comparisons use constructed worlds, so they do not prove a live arena
input or asset path.
