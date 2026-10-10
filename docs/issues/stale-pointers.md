# Stale pointers and address-dependent behaviour

Scope: simulation code whose result could depend on where an object sits in memory — plain
object pointers kept across frames, pointers to the prediction copy kept by simulation
objects, and behaviour that depends on address values or allocation order.

Everything here was read from the executable (SLUS_209.73, v2.00); **nothing was run, and
every patch proposal is untested.** Each statement is **Observed** (read at the address
given), **Inferred** or **Unknown**. The scanner used is `tools/rawptr.py`; what it can and
cannot see is described in section 7. `FINDINGS.md` and `patches/` were not edited; proposed
ledger rows are in section 9.

> Status: work in progress. Sections marked *(pending)* are not written yet.

## 1. Result in short

- **The pool is the same on every machine, except for one block.** Three size classes
  (`docs/objects.md`). The only per-machine allocation found is the prediction copy
  (0x590 bytes, so always the 3000-byte class), and after it has first been made it is
  always freed and re-made back to back, which gives it the same block again. No draw
  function allocates from the pool (section 5.1). So in classes 0 and 1 — every monster,
  projectile, prop, effect and spell — a stale pointer reads the same bytes on every
  machine: wrong behaviour, but the same wrong behaviour. A stale-pointer *desync* needs a
  per-machine difference in the 3000-byte class, a per-machine difference in *when* the
  pointee is destroyed, or one of the already-listed one-machine object creations (D16,
  D28, D29, K1).
- **Resurrect (SB3) reads a freed player object, and the read is the same on every
  machine.** `player_respawn` frees the old `Player` and allocates the new one with nothing
  in between, the free list is last-in-first-out, so the new object is at the old address
  and `SkillResurrect_isSlotBeingRaised` reads the new object's slot number (section 3).
- **No simulation object keeps the address of the prediction copy** within reach of direct
  calls (section 4).
- **No ordering, hashing or keying by object address** was found, and nothing walks the pool
  in address order (section 5).

## 2. Background facts used below

| Fact | Kind | Where |
|---|---|---|
| `pool_free` pushes the block on its class's free list and overwrites only the first word (the object's "who refers to me" head); the rest of the dead object stays as the destructor left it | Observed | 0x150470 |
| `pool_new` takes the head of the first class that is big enough and has a free block, and zero-fills it | Observed | 0x14fdb8 |
| The pool tables (0x403a10–0x403a4c) and the pool memory (0x5f88c0) are referenced only by `pool_init`, `pool_new`, `pool_free`, `pool_countFree`; the handle-node pool (0x847268) only by its init and its debug walk | Observed (`tools/gxref.py`) | 0x14fcd8, 0x14fdb8, 0x150470, 0x150410; 0x1a17d0, 0x1a14f0 |
| Requests above 0x500 bytes (3000-byte class): `Player` 0x590 (`mainloop_loadRequestedWorld` 0x3213f8, `player_respawn` 0x1bd138 / 0x1bd168, `cut_setup` 0x19af54 / 0x19afd0, `arena_startWave` 0x306030, `Player_clone` 0x11e894), CloudGiant 0x538, WaveMaker 0x768, boats 0x938 (`world_objectFactory`), `WaveMaker_clone` | Observed (constant size argument of all 761 `pool_new` call sites; 3 sites pass a computed size: 0x2f7048, 0x2f81e0, 0x3124b0) | — |
| The prediction copy is re-made by "destroy old, clone new" with nothing between the two, at the end of `net_frameLoop`, when (more than 30 frames unconfirmed or the force counter is set) and the local player has an object and the game is not paused and the local pause menu is closed | Observed | 0x13b204–0x13b558 |

Consequence (Inferred): once a machine has a copy, re-making it never changes which block it
uses. Machines can differ in the 3000-byte class only if their *first* copy after a level
load is made on different sides of another allocation in that class (the first copy is made
1–31 ticks in, E6; later if the pause menu is open), or if one machine has no copy.

## 3. The Resurrect path (SB3) *(pending: detail)*

## 4. Pointers to the prediction copy *(pending)*

## 5. Address values and allocation order *(pending)*

## 6. Raw object pointers, class by class *(pending)*

## 7. The scanner

`python3 -I -B tools/rawptr.py SLUS_209.73 fields|stores|globals|ptrmath|keeps|func`.
It walks every function once in address order with a small value tracker and records word
stores, loads through a tracked base, calls and arithmetic. It over-reports (a register
reused on another path) and under-reports (values taken from stack arrays, pointers reached
only through indirect calls). Every hit used in this document was read in the decompile.

## 8. Not determined *(pending)*

## 9. Proposed ledger rows *(pending)*
