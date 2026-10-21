# Skeleton_isEnemy, the take-damage slots, and six destructors

US `SLUS_209.73` v2.00. Prose of `tools/ref_combat_ctors2.py`. The comparison is
`tools/difftest_combat_ctors2.py`; the synthetic tests are `tools/test_ref_combat_ctors2.py`.
This follows `docs/spec/combat-ctors.md` (constructors, set-states, run prologues).

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, and the result. **Observed**: read at the address. **Inferred** and **Unknown** as
usual. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. How it was run

Part 1, the creatures, is `tools/difftest_combat_ctors.py`'s rig and world. Each AntQueen,
Skeleton and Soul is built by its original constructor with the game's own table, and the
creature base runs for real. These run for real too:

- the bodies below;
- `Creature_dtor` `0x117128` and `GameObject_dtor` `0x14cf90`
  (`tools/ref_combat_monsters.py`, executed by `tools/difftest_combat_monsters.py`, borrowed
  unchanged);
- the eight type-info getters of §2;
- the C library (`rtti_typeInfoEquals` `0x3b1250`, `libc_strcmp` `0x3b8534`, `strncmp`).

The other objects get one of these:

- the game's own table of Skeleton `0x5175f8`, Skelight `0x5174b0`, Soul `0x517740`,
  AntQueen `0x511078`, Player `0x511308` or Demon `0x514b40`. The flags, creature flags,
  team byte `+0x310` and side byte `+0x3d4` are planted.
- the world's synthetic table. Its slot 0 answers a synthetic descriptor; one of these has
  the name `5Demon` at another address, and one has `8Skeleton`.

Every slot of those tables that is not real is a named recording stub.

`Skeleton_isEnemy` is reached in two ways:

- directly;
- from the real `Creature_pickTarget` inside `Skeleton_run`'s prologue. Slot 20 is no
  longer a stub there.

The take-damage entries are the address in slot 2 of each class's table, and the
destructor entries are slot 1. The rig asserts both.

Part 2, the GameObjects, is `tools/difftest_potion_ctors.py`'s rig. Each Fire, LooseFire
and poison-gas cloud is built by its original constructor, and that call is compared too.
Then one of these runs:

- the destructor, with flags 0 to 3, with or without a property list (`name=` entries), an
  owner handle and handle lists;
- for Fire and LooseFire, the object's own run (`Fire_run` `0x1f34e0`, `LooseFire_run`
  `0x202c48`). Its end calls slot 1 with 3, and the real destructor is behind that slot.

`handle_clear`, `objNames_remove`, `pool_free`, `AnimState_dtor`, `0x202500` and an attached
spell's slot 1 are recording stubs on both sides.

Commands:

    python3 -u tools/difftest_combat_ctors2.py --seed 20973 -v
    python3 -u tools/difftest_combat_ctors2.py --seed 7 -v
    python3 -m unittest tools.test_ref_combat_ctors2

| | Seed 20973 | Seed 7 |
|---|---|---|
| Creature calls compared (all entries, set-states and runs included) | 9,776 | 9,918 |
| `Skeleton_isEnemy` direct calls (results 0 / 1 / 2 / 5) | 1,790 (1430 / 31 / 262 / 67) | 1,858 (1469 / 37 / 280 / 72) |
| `Soul_takeDamage` (of them, the null-attacker throw on both sides) | 289 (7) | 289 (8) |
| `Skeleton_takeDamage`, `AntQueen_takeDamage` | 73, 80 | 64, 55 |
| `AntQueen_dtor`, `Skeleton_dtor`, `Soul_dtor` | 23, 45, 43 | 29, 55, 39 |
| GameObject cases: Fire, LooseFire, gas (of them, through the run's slot 1) | 300 (93), 300 (74), 300 | 300 (88), 300 (77), 300 |
| Mismatches | 0 | 0 |

As checks, these model changes were each detected (`--quick`):

- `isEnemy` returning r instead of r + 1;
- a non-flat Soul particle;
- Skeleton's two `handle_clear` swapped.

## 2. Coverage (instructions executed of the body)

| Function | Address | Executed | Not executed |
|---|---|---|---|
| `Skeleton_isEnemy` | `0x2a7e04` | 59 of 59 | |
| `Skeleton_takeDamage` | `0x2a774c` | 7 of 7 | |
| `AntQueen_takeDamage` | `0x2378fc` | 7 of 7 | |
| `Soul_takeDamage` | `0x2aa908` | 150 of 150 | |
| `AntQueen_dtor` | `0x3c3c10` | 24 of 26 | two padding `nop`s, `0x3c3c5c` and `0x3c3c74` |
| `Skeleton_dtor` | `0x3cc5b8` | 29 of 29 | |
| `Soul_dtor` | `0x3cc72c` | 29 of 29 | |
| `Fire_dtor` | `0x3c5050` | 24 of 25 | padding `nop` `0x3c509c` |
| `LooseFire_dtor` | `0x3c6778` | 27 of 27 | |
| `poisonGasSpell_dtor` | `0x3c7878` | 27 of 27 | |
| `GameObject_typeinfo` | `0x3c7e10` | 16 of 16 | |
| `Creature_typeinfo` and the Skeleton, Soul, AntQueen, Skelight, Player and Demon getters | `0x3c2608`, `0x3cc62c`, `0x3cc7a0`, `0x3c3c78`, `0x3cc6dc`, `0x3c3ab8`, `0x3ca81c` | 20 of 20 each | |

Both seeds give the same coverage.

## 3. Type information (what `isEnemy` and `takeDamage` compare)

*Executed.* A getter reads word 0 of its descriptor. When that word is 0:

1. it calls its base class's getter, and the result is not used;
2. it calls `rtti_initSingleBaseTypeInfo` `0x3b12b8` with `(descriptor, name, base
   descriptor)`. That stores `+8` = the base descriptor, `+0` = the name and `+4` = the
   `__si_type_info` table `0x51df48` (its address is formed at `0x3b12bc` and `0x3b12c4`).

GameObject's getter has no base. It calls `0x3b12d8`, which stores `+0` = the name and
`+4` = `0x51df78` (`0x3b12dc`/`0x3b12e4`).

The getter then returns the descriptor. Each getter forms these constants from two
immediate halves:

- the descriptor (getter + `0x4` / `+0xc`);
- the name (getter + `0x24` / `+0x2c`; GameObject `+0x20` / `+0x28`);
- the base descriptor (getter + `0x28` / `+0x30`).

| Getter | Descriptor | Name (address, text) | Base |
|---|---|---|---|
| GameObject `0x3c7e10` | `0x564318` | `0x532210` `10GameObject` | none |
| Creature `0x3c2608` | `0x908130` | `0x530150` `8Creature` | GameObject |
| Skeleton `0x3cc62c` | `0x908e20` | `0x54c168` `8Skeleton` | Creature |
| Soul `0x3cc7a0` | `0x908e30` | `0x54c3e0` `4Soul` | Creature |
| AntQueen `0x3c3c78` | `0x908680` | `0x530a80` `8AntQueen` | Creature |
| Skelight `0x3cc6dc` | `0x908e10` | `0x54c178` `8Skelight` | Creature |
| Player `0x3c3ab8` | `0x9083d0` | `0x530a70` `6Player` | Creature |
| Demon `0x3ca81c` | `0x908b80` | `0x5454a0` `5Demon` | Creature |

All eight descriptors are zero in the executable image, so the first comparison after boot
builds them (Observed in the image; the difftest zeroes them now and then to repeat that
path).

`rtti_typeInfoEquals` `0x3b1250 (a, b)`:

- 1 when the two pointers are equal;
- otherwise 1 when `libc_strcmp(*a, *b)` is 0, else 0.

This is an exact-class test, so a subclass does not match. No draws.

`typeid(*obj)` is a call of slot 0 of the object's table. Its `a0` is whatever register the
caller had (Observed at `0x2a7e40`, `0x2aa93c`), and the getters do not read it.

## 4. Skeleton_isEnemy `0x2a7e04` (slot 20) (skeleton S, other O)

*Executed.* The result is 0, 1, 2 or 5, and all four were seen.

1. `r = Creature_isEnemy(S, O)` `0x119328` (0, 1 or 4; `ref_creature.is_enemy`).
2. A non-zero r returns **r + 1** (the add at `0x2a7e2c`, kept only for a non-zero r at `0x2a7e34`). A base
   enemy therefore scores 2, or 5 with the priority flag `0x100000000000`, as the scoring in
   `Creature_pickTarget` sees it.
3. When `O` is 0, it returns 0.
4. Otherwise, with `r == 0`:
   - `typeid(*O)` against `Skeleton_typeinfo()`. Anything else gives 0.
   - `O+0xc & 8` (dead; tested at `0x2a7e70`) gives 0.
   - `S+0x312` (s16, the charm timer; `0x2a7e7c`) non-zero gives 0.
   - Otherwise the result is 1 when the signed side bytes `S+0x3d4` and `O+0x3d4` are 2
     and 1 (`0x2a7e8c`, `0x2a7e9c`) or 1 and 2 (`0x2a7eb4`, the compare with 2 at `0x2a7ec8`).
     Anything else, side 0 included, gives 0.

Reads:

- `O+0xc`, `O+0xa8`, `O+0x48`, `O+0x3d4`;
- slot 37 of both objects (team byte `+0x310` through the base `0x3c2730`, or the
  object's own slot 37: for the Player table a call-out);
- `S+0x312`, `S+0x3d4`;
- the descriptors and their name strings.

Writes: only a descriptor still to be built.

Calls:

- `Creature_isEnemy`;
- `O`'s slot 0, made only when r is 0;
- `Skeleton_typeinfo`;
- `rtti_typeInfoEquals`.

No shared or own draws.

## 5. The take-damage slots

**Skeleton_takeDamage `0x2a774c` and AntQueen_takeDamage `0x2378fc`.** *Executed.* Each is a
wrapper with a frame: a linked call of `Creature_takeDamage` `0x116638` with the three
integer arguments and the float amount unchanged, then return. They are not tail jumps (`docs/monsters-2.md` says "tail call"), but
the behaviour is the same.

The fields are `Creature_takeDamage`'s (`ref_creature.take_damage`):

- reads `+0x231`, `+0xa8`, `+0x228`, the positions and the attacker's `+0xc` and `+0x4c`;
- writes `+0x3b0`, `+0x304`, `+0x2dc`, `+0x2e0`, the handle `+0x2e4`, `+0x228` and
  `+0xc8`. With creature flag `0x1000000000000` it writes the timers `+0x340`–`+0x350`
  instead.

No draws.

**Soul_takeDamage `0x2aa908` (soul S, attacker A, flags; amount).** *Executed.*

1. With `A == 0` it calls `cxx_throwBadTypeid` `0x3b3338` (`__throw_bad_typeid`). The
   difftest stops both sides at that call (7 and 8 times).
2. `typeid(*A)` is compared with `Demon_typeinfo()`, an exact class, by descriptor or by
   name. Not a Demon: nothing else, no field written and no draw. Players, Skelights,
   Skeletons, Souls and the synthetic classes were all ignored, except the synthetic
   descriptor named `5Demon` at another address, which matches by name.
3. For a Demon, `Creature_takeDamage(S, A, flags, amount)`.
4. `n = model_getSamplePointCount(slot 16)`. With `Soul_getModel`, that is class block
   `+0x1c` while owned (`+0x3c8`), else `+0xc`. With `n == 0` it returns.
5. Otherwise it makes **exactly six** particles (the limit 6 is tested at `0x2aab30`; `n` is never
   re-read). Each one:
   - calls slot 16 again;
   - makes **one own draw** `d` (`GameObject_rand`, word `S+0x44`);
   - takes the index `d % n` (a signed remainder, so the remainder has the dividend's sign; a
     negative `n` works as `|n|`);
   - calls `model_getSamplePoint(model, S+0x114, copy of S+0x10..+0x18, s16(S+0x38 −
     0x4000), index, out, second out; scale S+0xdc)` (the −0x4000 is added at `0x2aa9f4`);
   - builds a unit-ball vector by **own-draw** rejection. That is three draws a try, each
     `2·d·2⁻¹⁶ − 1` (`0x37800000` at `0x2aaa30`, 1.0 at `0x2aaa4c`), tried again while
     `x² + y² + z² > 1`;
   - zeroes the copy's z word (`0x2aaaec`) before the scale, then multiplies x, y and the
     zero by 15 (`0x41700000` at `0x2aaac8`);
   - calls `particle_spawn(0x8e4600, the point, that velocity; 0.0)` (`0x2aaae8`/`0x2aaaf0`,
     `f12 = 0` at `0x2aaaf4`).

So the burst is flat, like `Soul_setState` 0x21's.

Shared draws: none. Own draws: 6 + 3·(tries) per Demon hit. *Inferred*: the particles are
presentation, but the own generator `+0x44` advances, and the next own draw of the Soul
(set-state timers, `Soul_run`) depends on it.

## 6. Destructors (slot 1, `(object, flags)`)

*Executed.* Each one stores its own table at `+0x48` and clears handles in this order. It
then calls its base destructor with 0, and when bit 0 of the flags is set it
tail-jumps to `pool_free(object)`. Bit 1 is not looked at, so flags 2 acts as 0. A
destroyed object ends with the GameObject table `0x5122a8` at `+0x48`: the base
destructors store theirs.

| Destructor | Table (instructions) | Handles cleared, in order | Base | Free (tail `j`) |
|---|---|---|---|---|
| `AntQueen_dtor` `0x3c3c10` | `0x511078` (`0x3c3c14`/`0x3c3c20`) | none | `Creature_dtor` | `0x3c3c54` |
| `Skeleton_dtor` `0x3cc5b8` | `0x5175f8` (`0x3cc5bc`/`0x3cc5c8`) | `+0x3cc` (`0x3cc5d4`), `+0x3c8` (`0x3cc5ec`) | `Creature_dtor` | `0x3cc610` |
| `Soul_dtor` `0x3cc72c` | `0x517740` (`0x3cc730`/`0x3cc73c`) | `+0x3cc` (`0x3cc748`), `+0x3c8` the owner (`0x3cc760`) | `Creature_dtor` | `0x3cc784` |
| `Fire_dtor` `0x3c5050` | `0x50f208` (`0x3c5054`/`0x3c5060`) | none | `GameObject_dtor` | `0x3c5094` |
| `LooseFire_dtor` `0x3c6778` | `0x50e2b8` (`0x3c677c`/`0x3c6788`) | `+0x4c` the owner (`0x3c6794`) | `GameObject_dtor` | `0x3c67c8` |
| `poisonGasSpell_dtor` `0x3c7878` | `0x50d500` (`0x3c787c`/`0x3c7888`) | `+0x4c` the owner (`0x3c7894`) | `GameObject_dtor` | `0x3c78c8` |

`Creature_dtor` (`tools/ref_combat_monsters.py`):

1. table `0x50cc58`;
2. slot 1 with 3 for every spell on `+0x364`, then `iter_end(2)`;
3. `handle_clear` of `+0x364` and `+0x360`;
4. `0x202500(+0x320, 2)`;
5. `handle_clear` of `+0x2e4`, `+0x238` and `+0x234`;
6. `AnimState_dtor(+0x114, 0)`;
7. `GameObject_dtor(c, 0)`.

`GameObject_dtor`:

1. table `0x5122a8`;
2. the `name=` scan of `+0x2c`, with `objNames_remove` for each entry; it lower-cases the
   key `0x5321b0` in place;
3. `handle_clear` of `+8`, `+4` and `+0`.

No destructor here makes a shared or own draw.

Notes:

- *Observed*: `Skeleton_dtor` makes no call for the WeaponShield holder built inline at
  `+0x3d8`, so the holder's own destructor never runs. What `+0x3cc` holds in a Soul is
  Unknown. The Soul constructor writes only `+0x3c8`; `docs/monsters-2.md` names Skeleton's
  `+0x3cc` a handle.
- *Executed*: `Fire_run` at life ≤ 0 and `LooseFire_run` past its end frame call slot 1
  with 3. With the real destructor behind it, the whole end is: run, destructor,
  `GameObject_dtor`, `pool_free`. That was 93 and 74 cases (seed 20973), and 88 and 77
  (seed 7).

## 7. Corrections and sharpenings

- `docs/monsters-2.md`, Soul takeDamage: "up to 6 particles (1 + 3n own draws each)" is
  **exactly six** when the sample-point count is non-zero. Each particle:
  - uses a random sample point (`own draw % n`), not the sequence;
  - is placed at the facing − 0x4000;
  - has a **flat** velocity (z zeroed);
  - uses definition `0x8e4600`.
- `docs/monsters-2.md`, Skeleton takeDamage "tail call to `Creature_takeDamage`": it is a
  call inside a frame. The result is the same, and so is AntQueen's.
- `symbols/monsters.tsv`, `Skeleton_isEnemy` "purpose not established": §4 establishes it.
- `docs/spec/combat-ctors.md` §8 lists `Soul_takeDamage` and `Skeleton_isEnemy` as
  recording stubs. Both are now executed. In the inline destructors, `runtime.tsv`'s "inline
  destructor" bodies are §6.

## 8. Still not executed

- `Skeleton_shatter` `0x2a7ef0` and `AntQueen_pickFlyDest` `0x238150`.
- The Player's own slot 37 `0x3c3b18` and the Demon's own slot 20 `0x25f378`. Both were
  call-outs here.
- `pool_free`, `handle_clear`, `objNames_remove`, `AnimState_dtor`, `0x202500`, the spells'
  slot 1, `model_getSamplePointCount`, `model_getSamplePoint` and `particle_spawn`. All were
  recording stubs.
- What happens after `__throw_bad_typeid` (whether anything catches it), and whether any
  damage source reaches a Soul with no attacker: Unknown.
- In seed 7's first run, one `AntQueen_run` stopped the same way on both sides at
  `0x112b68`, inside `Creature_run`. It is a load through the pointer the scripted world's
  stub `0x21039c` returned (0). This is an artefact of the world, and the AntQueen prologue
  rig was already open to it. It did not occur in the final runs.
