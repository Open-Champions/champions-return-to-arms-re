# Thrown potions, kinds 1 and 2: what the endings build

US `SLUS_209.73` v2.00. Prose of `tools/ref_potion_ctors.py`; the comparison is
`tools/difftest_potion_ctors.py`, the synthetic tests `tools/test_ref_potion_ctors.py`.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran one function at a
time in `tools/ee_emu.py` on state the difftest built, and the model agreed on the calls
(in order, with arguments), the bytes stored outside the stack, the shared seed
`0x404464` with its draw count, and the result. **Observed**: read at the address.
**Inferred**: follows from those. **Unknown**: not established. Nothing here was run on
a console, in PCSX2 or on the live rig.

## 1. What was already executed, and what was not

- `playerProjectile_run` `0x1ba940`, kinds 1–3 (combat round 4, research-combat branch):
  the kind-1 ending calls `LooseFire_ctor(pool_new(0x54), point, owner)` five times, the
  kind-2 ending `poisonGasSpell_ctor(pool_new(0x70), position, 300, 20, 0, owner, 5)`.
  Both constructors were recording stubs there. The call sites `0x1baff4` and
  `0x1bb0c0` pass exactly those registers (Observed).
- `poisonGasSpell_run` `0x1fd0f0`: Executed in combat round 6 (296 of 303).
- `fx_spawn` `0x1ef270`, every id, and its first-call definition set-up: Executed in
  research-fx `tools/difftest_fx_recipes.py`, with `Fire_ctor` a stub.
- `GameObject_ctor` `0x14cb10` (no properties) and `GameObject_rand` `0x1509d0`:
  Executed by `tools/difftest_skills_a.py`; `math_sin16` `0x1666e0` by
  `tools/difftest_core.py`. Reused here, run for real.
- Not executed anywhere before this: `LooseFire_ctor`, `LooseFire_run`,
  `LooseFire_onTouch`, `Fire_ctor`, `Fire_run`, `poisonGasSpell_ctor`,
  `obj_runEveryFrame`, and `fx_spawn` id 5 with a real `Fire_ctor` behind it.

## 2. Findings

**LooseFire_ctor `0x202b70` (block, position, owner object or 0).** *Executed.*
`GameObject_ctor` (one shared draw), table `0x50e2b8`, owner handle `+0x4c` = 0 and,
with an owner, `handle_link(obj+0x4c, owner, owner)`; end frame `+0x50` =
`g_simFrame + 120`; `fx_spawn(5, own position)`; `obj_runEveryFrame`; flags
`+0xc |= 0x420c`; radius `+0x1c` = 10.0. Table slots: 1 `0x3c6778` (destructor),
4 `0x202c48` (run), 6 `0x1fcb70` (touch) (Observed in the table).

**fx_spawn id 5 (arm `0x1f0ae0`).** *Executed*, given the 24 definition words
`0x4f87bc + 4i` already set. No camera test. One shared draw d: `n = 3 + (d & 1)` fires.
Each fire: three shared draws; point `((x − 6) + float(dx % 12), (y − 6) + float(dy % 12),
z + float(dz % 18))`, `%` the unsigned remainder of the 16-bit draw; `pool_new(0x50)`;
with a block `Fire_ctor(block, point)`. A refused block skips only that fire.

**Fire_ctor `0x2020e0`.** *Executed.* `GameObject_ctor` (one shared draw), table
`0x50f208`, flags `|= 0x4001`, byte `+0x28` = `0xf0`, `obj_runEveryFrame`, life
halfword `+0x4c` = 100.

**Fire_run `0x1f34e0`.** *Executed.* Alpha from the signed life L: L < 20 → 60 −
3(20 − L); L > 80 → 3(100 − L); else 60. `glow_add(position, 255, 150, 0, alpha, word at
0x4f848c, 0, 0; 5, sin16(g_simFrame << 10) × 250 + 8000)`. One `particle_spawn(0x870548)`
from two unit-ball points of the fire's own generator `+0x44`: velocity `(2u.x, 2u.y,
2u.z + 4.8)`, position `(2u'.x, 2u'.y, |2u'.z|)` + the fire's position. Life drops by
one; at ≤ 0 slot 1 with 3. It never draws the shared seed. *Inferred*: a Fire lives 100
runs and is presentation only.

**LooseFire_run `0x202c48`.** *Executed.* Slot 1 with 3 when the signed `+0x50` is
strictly below `g_simFrame`, nothing else. *Inferred*: a LooseFire made on frame F is
deleted by the run of frame F + 121.

**LooseFire_onTouch `0x1fcb70`.** *Executed.* Nothing unless `g_simFrame % 20 == 0`
(signed). The owner is the object behind handle `+0x4c` when its flags have `0x20`;
an owner's slot 20 is asked `(owner, toucher)` and 0 ends the touch. A fresh descriptor
gets one entry `(0x15, v, v, 0)`: a toucher with `0x40` (player) takes v from
`g_difficultyIdx` `0x4f719c` (2, 3, 4, 5 as they are, anything else 1); one with `0x20`
and not `0x40` takes v = 8; any other toucher gets an **empty** descriptor. Then
`damage_apply(toucher, owner or the fire itself, 10000000, 0, 0, 0x100c040, descriptor,
0; 0, 0)`; its result is unused. This sharpens `docs/issues/touch-handlers.md` row 8.
*Inferred*: every LooseFire burns on the same global frames. *Unknown*: what entry type
`0x15` does inside `damage_apply` (the symbol note calls it fire; not executed here).

**poisonGasSpell_ctor `0x202de8` (block, position, life, radius, word, owner, damage).**
*Executed.* A `GameObject`, not a `Spell`: no Spell base and no spell generator.
`GameObject_ctor` (one shared draw), handle `+0x4c` = 0, table `0x50d500`, a second
copy of the position at `+0x50`, end `+0x5c` = `g_simFrame + life`, target radius
`+0x60` (raised to 10 when below 10, signed), `+0x68` = the fifth argument, damage
`+0x6c`, with an owner `handle_link(obj+0x4c, owner, owner)`, flags `|= 3`, current
radius `+0x64` = 10.0, `obj_runEveryFrame`. The potion's arguments give end = frame +
300, target 20, `+0x68` = 0, damage 5. *Unknown*: who reads `+0x50` and `+0x68` (the
round-6 run reads neither).

**obj_runEveryFrame `0x14f248`.** *Executed.* `handle_removeNode(+4)` when `+4` is set,
then `handle_link(0x5db3a8, obj+4, obj)`.

**Shared draws.** *Executed* per call; the sums are *Inferred*. One `LooseFire_ctor`
makes 2 + 3n + (blocks given) draws, n = 3 or 4: 11 to 18
(`ref_potion_ctors.loosefire_draws`, checked against every difftest case). A kind-1
ending is five of those plus its own unit-ball draws and five decal draws. A kind-2
ending makes one draw (the cloud's `GameObject_ctor`) when the pool gives a block.
*Inferred*: the count depends on `pool_new`'s answers, so two machines whose pools
answer differently would part seeds here; whether that can happen is *Unknown*.

## 3. Coverage

`python3 tools/difftest_potion_ctors.py --seed 20973` and `--seed 7`: 2000 cases each,
0 mismatches. Instructions executed of the body:

| Function | Executed | Not executed |
|---|---|---|
| `LooseFire_ctor` `0x202b70` | 54 of 54 | — |
| `LooseFire_run` `0x202c48` | 20 of 20 | — |
| `LooseFire_onTouch` `0x1fcb70` | 162 of 224 | 62: the search for a later descriptor slot after slot 0 (dead: slot 0 is always empty), its branches and padding |
| `poisonGasSpell_ctor` `0x202de8` | 70 of 70 | — |
| `fx_spawn` id-5 arm `0x1f0ae0` | 72 of 72 | — |
| `Fire_ctor` `0x2020e0` | 30 of 30 | — |
| `Fire_run` `0x1f34e0` | 211 of 212 | one padding `nop` at `0x1f353c` |
| `obj_runEveryFrame` `0x14f248` | 18 of 18 | — |

## 4. Open

- `fx_spawn`'s first call (the 24 `particleDef_ctor` calls) is refused by this model; it
  is research-fx's executed recipe.
- A hidden object (`obj_getPropInt(obj, "hide")` nonzero) is refused, as in
  `ref_skills_a.gameobject_ctor`.
- The composed kind-1 / kind-2 endings with these constructors real inside
  `playerProjectile_run` were not run here; the round-4 call arguments match the
  constructors' parameters (Observed at `0x1baff4`, `0x1bb0c0`).
- What calls slot 6 of a LooseFire, and how often, is the touch dispatch's
  (`docs/issues/touch-handlers.md`), not executed here.
