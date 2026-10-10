# Skills 69–101: what execution confirmed

Companion to `docs/spec/skills-69-101.md`, which was written from reading only. Here the
same rules are code — `tools/ref_skills_c.py` — and that code is compared with the
original machine code by `tools/difftest_skills_c.py`, which runs the original functions
under `tools/ee_emu.py`. The specification itself is not rewritten; its errors are listed
in "Corrections" below.

**What "executed" means.** `tools/ee_emu.py` is an instruction interpreter for single
functions, not a console and not the live game (`docs/issues/dynamic-tests.md`). A function
is run on objects the test builds in the interpreter's memory; everything it calls outside
the model is a recording stub answered by a seeded script. "Matched" below means: for every
call the test made, the model and the original made the same calls to the outside in the
same order with the same arguments, stored the same bytes with the same final values
(including a spell's own generator at +0x10 and an object's at +0x44), left the shared
seed 0x404464 the same, and returned the same value. Floats are compared as 32-bit
patterns under the interpreter's floating-point model; results are bit for bit under that
model, which is itself an approximation of the console's unit. Nothing here was observed
on a PlayStation 2 or in the live rig.

(This file is written as the work goes; the table is complete for the rows it has.)

## Status per skill

| Id | Name | Status | What ran |
|---|---|---|---|
| all 33 | statistics | matched | slots 8, 10, 11, 12, 13, 14, 15 and the mana cost, every id, levels 0–40 and a few beyond, statistics 0–4 |
| 69 | retribution | matched | can-use, cast, constructor, run to its end, the heal |
| 70 | unspokenword | matched | cast, constructor, run through its 30 frames, the hit ring with its stun rolls |
| 80 | pusstorm | matched | cast (players and monsters), constructor, run to the last frame, the blob constructor |
| 94 | spiritshield | matched | can-use, cast, constructor, run through all four phases, both particle helpers, the absorb roll |
| 95 | waveofflame | matched | can-use, cast, constructor, run to its end, the hit test |
| 96 | frostarmor | matched | can-use, cast, constructor, run to its end, the on-hit function |
| 100 | lightningstrike | matched | cast (players and monsters), constructor, run to the last frame |
| 101 | coneofshock | matched | cast, constructor, run |
| 87 | tagarsinsects | matched elsewhere | `tools/difftest_arena_monsters.py`; not repeated here |
