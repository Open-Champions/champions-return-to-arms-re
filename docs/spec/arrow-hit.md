# The hit paths of the cold and the exploding arrow: `Creature_setEffectTimer` and `LightEffect_ctor`

US `SLUS_209.73` v2.00. Prose of `tools/ref_arrow_hit.py` (the two bodies) and of their place in
`tools/ref_arrow_run.py` (the chains). The comparisons are `tools/difftest_arrow_hit.py` (one call
at a time) and `tools/difftest_arrow_run.py` (the whole chains, now with both bodies real); the
synthetic tests are `tools/test_ref_combat5.py`. Written 2026-10-21 (research round 5, item 2).

Evidence words as in `CONTRIBUTING.md`: **Executed** means the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with arguments),
every byte stored outside the stack, and the shared seed `0x404464` with its draw count;
**Observed** means read at the address. Nothing here ran on a console, in PCSX2 or on the rig.

`docs/spec/arrow-run.md` §7 and §8 named these as the first unexecuted bodies a cold or exploding
arrow meets; they were call-outs there. They run for real now, and `arrow-run.md` §5 is the rest of
the chain.

## 1. The cold arrow's hit, start to end

`ColdArrowProjectile_onHit` `0x2d7aac` (slot 6, `arrow-run.md` §5.4), monster owner, in order:

1. owner handle `+0x4c` empty: nothing.
2. `owner.slot20(victim)` must accept (`Skeleton_isEnemy` `0x2a7e04`).
3. `fx_spawn(10, arrow position)`.
4. `s` = Skill 44 slot 13 (statistic 0, level `+0x68`, cap 0); ONE OWN DRAW (the arrow's `+0x44`
   generator) for the spread; `damage_apply(victim, owner, 100000, 0, 0, 0x40, 0, 0; s, s + spread)`.
5. A victim with flag `0x20` in `+0xc` (a creature or player): `seconds` = slot 13 (statistic 3, cap
   10) `/ 2` (C division, rounded toward zero), added to the victim's **current** `+0x344` as floats,
   then **`Creature_setEffectTimer(victim, 1, owner, that sum)`**.
6. `ColdArrowProjectile_end(arrow, 2)`: burst of `level × 10` particle pairs, sound, `obj_delete`.

## 2. `Creature_setEffectTimer` `0x118950` (creature, which, source; f12 seconds)

*Executed*: 3,000 cases per seed (20973, 7), 0 mismatches; **39 of 40** instructions (the
unexecuted word, `0x118984`, is the padding `nop` before the first jump-table target). The
composed chains of `difftest_arrow_run` run it for every victim with flag `0x20`.

| Step | Address | What |
|---|---|---|
| 1 | `0x118954` | `which` is tested **unsigned** against 5; 5 and above skip the store |
| 2 | `0x11896c`–`0x118980` | jump table at `0x530180` (five words: `0x118988`, `0x118990`, `0x118998`, `0x1189a0`, `0x1189a8`) |
| 3 | table targets | store `seconds` (an `f12` bit pattern) at `creature + 0x340` / `0x344` / `0x348` / `0x34c` / `0x350` for `which` 0 / 1 / 2 / 3 / 4 |
| 4 | `0x1189ac`–`0x1189b4` | `0.0 < seconds` (`c.olt.s`, the zero from `mtc1 $zero`) or the rest is skipped |
| 5 | `0x1189c0` | `handle_clear(creature + 0x360)` (the status-source list, back-pointers cleared) |
| 6 | `0x1189c8`–`0x1189d4` | `source` non-null: `handle_link(creature + 0x360, source, source)` |

- **Reads**: `which`, `source`, the `f12` argument; the 5-slot table; the handle list at `+0x360`
  (through `handle_clear`).
- **Writes**: one of the five timers; `+0x360` (clear then link). Nothing else, **no shared or other
  seed draw**, no allocation.
- A non-positive `seconds` still stores the timer (a value of zero or less) but leaves the source
  list alone; a store with `which` ≥ 5 touches nothing.
- Who reads the timers: `Creature_run` (`docs/spec/creature-tick.md`: `+0x340` is the burn, `+0x344`
  the chill, which also derives the slow amount; some paths clamp each timer to 1.0). This
  document does not execute that consumer.
- The 12 callers include skill code (`ref_skills_b.py` calls it with `which` 0 and 2.0 s, and with 1
  and 3); the Cold arrow uses `which` 1.

## 3. The exploding arrow's explosion

`ExplodeArrowProjectile_explode` `0x2db50c` (`arrow-run.md` §5.5), reason ≠ 0, in order: ONE OWN DRAW
for the sound name; `fx_ringBurst`; `pool_new(0xbc)` and, when the pool gives a block,
**`LightEffect_ctor(block, position, 0, 0; 255.0, 10.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0; 120.0, 60.0, 0.5, 0.25)`**
(the call is at `0x2db728`; in the model's order the values are the colour 255, 10, 10, 0 fading to
0, radius 120 falling to 60, the third value 0.5 and the life 0.25 s; `ref_skills_b.py` `light_effect`); `camera_shake(0; level / 2)`; then the box of
half edge statistic 2 and the per-object damage (`arrow-run.md` §5.5). `ExplodeArrowProjectile_onHit`
`0x2db4f0` calls explode with reason 2 for anything touched.

## 4. `LightEffect_ctor` `0x201bd8` (block, position*, follow, tag; f12–f19, four stack floats)

*Executed*: 3,000 cases per seed, 0 mismatches; **163 of 163** instructions; and inside the
arrows' chains (every Explode explosion with a block). **ONE SHARED DRAW**, inside its
`GameObject_ctor` call.

Arguments: `a0` the block (`pool_new(0xbc)`, zero-filled); `a1` a pointer to the position (three
floats, copied to the stack first, `0x201c54`–`0x201c68`); `a2` an object to follow or 0; `a3` a tag
word; `f12`–`f15` the start colour (r, g, b, a); `f16`–`f19` the end colour; the stack words at
`sp + 0x00`, `0x08`, `0x10`, `0x18` of the caller (the eight-byte slots; floats in the low half):
the radius, the end radius, a third value, the **life in seconds**.

| Step | Address | What |
|---|---|---|
| 1 | `0x201c74` | `GameObject_ctor(block, position copy, 0, 0)`: the shared draw |
| 2 | `0x201cd0`–`0x201cd8` | table `+0x48` = `0x50e198` (`lui 0x51` / `addiu -0x1e68`); the run is `LightEffect_run` `0x1ee050` (`docs/spec/combat-spells.md`) |
| 3 | `0x201ce0` / `0x201d50` | bytes `+0x55` and `+0x54` = 0 |
| 4 | `0x201d08`–`0x201d10` | position copied to `+0x7c`..`+0x87` |
| 5 | `0x201d14`–`0x201d38` | radius `+0x68`, `+0x70`; `1.0 / radius²` at `+0x6c` and `+0x74` (division by zero for radius 0: the R5900 result `0x7fffffff`); `+0x78` = the third value |
| 6 | `0x201c98`–`0x201d48` | start colour truncated (`cvt.w.s`) to signed 16-bit at `+0x56`..`+0x5c` and again at `+0x5e`..`+0x64` |
| 7 | `0x201d4c` | `light_link(block + 0x4c)` |
| 8 | `0x201d54`–`0x201d68` | `+0x88` = 0; flags `+0xc` \|= 3 (not solid: the finders of victims and contacts skip it) |
| 9 | `0x201d64`–`0x201d70` | `follow` non-null: `handle_link(block + 0x88, follow, follow)` |
| 10 | `0x201d78`–`0x201de0` | frames `n = trunc(life × 60.0)` (`lui 0x4270` at `0x201d80`); `n` ≤ 0 becomes 1 (`slt` / `movn`); end frame `+0xb4` = `g_simFrame` (`0x44fdcc`) + `n` |
| 11 | `0x201da0`–`0x201dc4` | start colour as floats at `+0x8c`..`+0x98`; radius at `+0xac` |
| 12 | `0x201de8`–`0x201e10` | steps `(end − start) / n` (one divide `1.0 / n`, then a multiply each): colour `+0x9c`, `+0xa0`, `+0xa4`, `+0xa8`; radius `+0xb0` |
| 13 | `0x201e14` | `obj_runEveryFrame(block)` |
| 14 | `0x201e1c` | `+0xb8` = the tag |

- **Fields read**: the position (through the pointer), the nine+ float arguments, `+0xc` (flags,
  after `GameObject_ctor`), `g_simFrame`.
- **Calls, in order**: `GameObject_ctor` (`handle_link(grid cell, block + 8, block)`,
  `obj_getPropInt(block, "hide", 0)`), `light_link(block + 0x4c)`, optional `handle_link`,
  `obj_runEveryFrame(block)`.
- **Draws**: shared ×1 (the GameObject's); own, cosmetic: none.
- The light's lifetime is therefore `max(trunc(life × 60), 1)` frames for the Explode arrow's
  `life = 0.25`: **15 frames** (`0.25 × 60.0` is exact), which `LightEffect_run` then ends by its own
  slot 1 (`combat-spells.md`).
- The model here and the spell-side `ref_combat_spells.svc_LightEffect_ctor` (written from
  disassembly, *Observed*) agree on the fields the spell code keeps; the full record is this
  document's.

## 5. What the chains showed (the elemental arrow chains)

`difftest_arrow_run` (the build, flight, hit, end and destructor of each arrow class on the
Skeleton's arguments, `arrow-run.md` §3) was re-run with both bodies real:

| Seed | Cases | Calls compared | Mismatches | Before (round 4) |
|---|---|---|---|---|
| 20973 | 600 | 75,264 | 0 | 75,264 / 0 |
| 7 | 600 | 77,455 | 0 | 77,455 / 0 |

(The case and call counts are unchanged because the random streams are: the model answers each
call exactly as the stubs did.) The one new instruction span the chains miss is the `follow`
link (`0x201d6c`–`0x201d78`): the Explode arrow passes no follow object. The direct entry
reaches it. The cold arrow's setEffectTimer reaches `which` = 1 only; the direct entry covers
0–4 and the skipped values.

## 6. Checks of the comparison itself

300 cases each, model restored after each:

| Mutation | Result |
|---|---|
| frames `n ≥ 0` instead of `n > 0` (a zero life divides by zero) | `light` FAIL 74 / 300 |
| the `which` limit 4 instead of 5 | `timer` FAIL 21 / 300 |

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_hit.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_hit.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_run.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_run.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_combat5.py

| Seed | `timer` | `light` |
|---|---|---|
| 20973 | 3,000 / 0 | 3,000 / 0 |
| 7 | 3,000 / 0 | 3,000 / 0 |

(cases / mismatches.)

## 7. What a native port needs from this

- `Creature_setEffectTimer` and `LightEffect_ctor` as bodies, with the arguments of §1–§4; the cold
  arrow adds `float(stat 3 / 2)` to the old `+0x344`, it does not set it.
- For the Explode arrow the light is a solid-less object that holds a frame counter and a fixed life;
  its one shared draw (in `GameObject_ctor`) is the one a sync check sees.
- Still call-outs, as in `arrow-run.md` §8: `damage_apply`, `fx_ringBurst`, `camera_shake`,
  `light_link` / `light_unlink` / `light_relink`.
