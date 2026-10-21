# Arena and versus modes

US `SLUS_209.73` v2.00. This is the prose form of `tools/ref_arena_modes.py`.
`tools/difftest_arena_modes.py` runs the original functions in `tools/ee_emu.py` and
compares them with that model (302 checks, plus `tools/test_ref_arena_modes.py` for the
model alone). **Executed** means those runs agreed. **Observed** means the instruction
was read at the address given and was not itself the thing the test called.
Nothing here was seen on a console or on the project's live game.

Two mode words. `g_pvpModeA` is the word at 0x4f711c. `g_pvpModeB` is the word at
0x4f7120. A third word at 0x4f7124 changes facing on the placement ring. The arena task
exists only while mode B is set: `arena_init` 0x304c4c and `arena_begin` 0x304f5c return
at once when it is clear (Observed). Mode A alone therefore never installs the task.
Damage reads mode A on its own, whether or not the task is running.

When both words are set, scoring and the map rotation follow mode A, and the task still
runs because mode B is set. That combination was executed (a kill-limit ending, a map
change, a respawn at −1 life).

## 1. The two tables

Mode A has 13 level-file names at 0x5037b8, then a null pointer. Mode B has 7 at
0x503798, then a null. `arena_levelName` 0x304bc8 returns one of those pointers
(Executed). In mode A the index is `game_scanCm1Vars(0)` 0x1eb950 with no modulo. In
mode B the mode-A word is 0, so the divide of that word by the recipe count leaves
remainder 0: recipe 0, and its low nibble selects the mode-B name.

The file names, in table order:

| Table | Names |
|---|---|
| A, 0x5037b8 | pvpnit, compsto, pvpfire2, pvpval, compdis, pvptor, compwat, pvpinn, pvpblo2, pvparena, pvpblo, pvpbas, pvpfire |
| B, 0x503798 | pvparena, pvpblo, pvpbas, pvpfire, compwat, pvptor, pvpnit |

Five recipe records sit at 0x503868. The count halfword at 0x503886 is 5. Each record is
6 bytes. The first byte's high nibble is a group count (`sll 24; sra 28`) and its low
nibble is a mode-B name index (`sll 28; sra 26`, which is the nibble times 4, then
divided by 4). The other bytes are signed class indices into the name table at 0x5037f0.
The difftest reads those bytes from the executable; they are not copied here.

## 2. The score block

Twelve bytes per slot at 0x503898.

| Offset | What | Start |
|---|---|---|
| +0 | kill count, unsigned halfword | 0 |
| +2 | lives, unsigned halfword, read signed | 2 |
| +4 | snapshot of lives | 0 |
| +8 | overlay timer, float | 2.0 (0x40000000) |

`arena_resetScores` 0x307c80 memsets the 0x30-byte block, then writes 2 lives and the
2.0 timer for each slot that `g_numPlayers` 0x4d8ae0 counts (Executed, two slots, online
and offline). The same call writes the movement factor at record +0x4c20: 0x3fa00000
(1.25) when the network byte 0x402791 is set, 0x3fe00000 (1.75) when it is clear. That
factor is movement (`docs/spec/movement-camera.md`), not a damage scale.

A life or kill halfword is loaded unsigned and stored unsigned. Subtracting from 0 wraps
to 65535, which a signed read treats as −1. That wrap was executed: a mode-B death from
0 lives left the halfword at −1.

Lives 2, 1 and 0 are still in the match. The respawn gate is a signed compare against 0,
so the first value that stops a mode-B respawn is −1. Three deaths from the starting 2,
then out. Mode A does not use this gate (section 4).

## 3. Mode B, the arena

`arena_begin` stores 3 in the waves-left halfword at 0x8e733a and calls
`arena_startWave(1)`. Init has already stored −1 in the wave halfword at 0x8e7338, so
that first call makes wave 0 and waves-left 2. Later calls add their argument to the
wave halfword and subtract it from waves-left. The wave store is `lhu` / `addu` / `sh`
at the top of `arena_startWave` 0x305ed4 (Executed: a call with the halfword preset to
the previous wave left the new wave number). The levels note that the only store of
0x8e7338 is init's −1 is wrong; the map change below uses the stored wave.

Three recipe waves, then a level change. The intermission countdown at 0x8e733c expires
when its value *before* this frame's increment equals 480, or 960 while the network byte
is set (`movn` of 0x3c0 over 0x1e0). The increment is the delay of that compare
(Executed: a counter already at 480 offline, and at 960 online, changed the level; 480
online did not). If waves-left is 0, or mode A is set, the task copies the next file
name into the pending-level buffer at 0x41b6d0 and stores −1 at byte +0x50 of that
buffer. Mode B's record is `((signed wave + 1) / 3) % recipe count`, and that record's
low nibble indexes table B. After the three waves the halfword is 2, so the record is 1,
not 0. Mode A's index is the byte at 0x8e7343: `(byte + 1) mod 13`, and a remainder of 0
is replaced by `game_scanCm1Vars(0)` (Executed, index 12 with the scan stubbed to 2, and
index 0 advancing to 1). The call at 0x1eb000 on this path is `net_closeLocalMenus`, not
the level request. Offline it returns without doing anything.

While waves-left is still nonzero and mode A is clear, the same expiry calls
`arena_nextWave(1)` 0x305e9c and stays on the level (Executed as the call; the body of
`arena_nextWave` was not run). That body is a screen effect 15, then 0x3063fc, then
`arena_startWave` with the same argument (Observed).

### 3.1 What a wave spawns

`arena_startWave` calls `net_closeLocalMenus(0)` first. The monster level stored at
0x4f714c is `float(signed wave) * 0x3f2bc579 + 5` (Executed for waves 0, 1, 2, 3, 5 and
8). Each slot below `g_numPlayers` with lives still at least 0 copies those lives into
the snapshot. A slot already at −1 is skipped, and its old snapshot is left as it was
(Observed in the branch; the executed waves used a player count of 0, so they did not
take the player loop).

Mode A calls `arena_resetScores` and skips the recipe (Executed, two players, no spawn
calls). Mode B with a nonzero saved-monster count at 0x8e7340 respawns that list through
0x3065fc instead of the recipe (Observed; the executed waves left the count at 0 and took
the recipe).

The recipe index is `(signed wave / 3) % recipe count`, and the remainder of the
division by 3 picks the row inside the record. The spawn count starts from

```
acc = float(wave / 3) * 0x3f814738 + float(wave % 3) * 0x3f80a393
```

using the toward-zero MIPS quotient and remainder. When `acc + 2` is at least 0 the
count is `trunc(acc + 2.5)`; otherwise `trunc(acc + 1.5)`. A count of 11 or more is
replaced by 10. Then `net_countActiveSlots()` 0x1ec878 is added and 1 is subtracted
(Executed, active count 1 and 4). Remainder 0 spawns that many of the class in byte +1.
Remainder 1 uses `high nibble − 1` groups; remainder 2 uses the high nibble. Group 0
receives the leftover after an even split. A remainder below 0 or of 3 or more spawns
nothing. Each group, including a group of size 0, takes one ring step; a zero group
divides by zero. The shipped records and the waves above did not hit a zero group.

`arena_setRingStep` 0x3065b0 divides 65535 by the group count, draws once from the
shared generator, and stores the quotient word at 0x8e7364 and the draw halfword at
0x8e7360 (Executed inside the wave). The spawn call 0x3065fc receives the class-name
pointer and a second argument of 0 (Executed as the call arguments). The function that
builds the monster was stubbed, so the constructor is not a result of this round.

The shared generator is inlined, not a call to `Rand.rand`:
`seed = seed * 0x19660d + 0x3c6ef35f`, draw = `seed >> 16`, seed word at 0x404464.
The low 32 bits of the multiply match an unsigned multiply (Executed wherever a test
checked the seed: placement, the ring step, the respawn visit).

After the spawns, `Camera_reset` 0x203210 runs and the delay slot stores 1 at 0x503890.
Earlier in the same function a delay slot stores 0 there. A call that returns has left
the word at 1 (Executed).

The intro counter at 0x5038c8 is set to 180. While it is positive the run task
decrements it and stores 1 at 0x41b500, 0x503890 and 0x41b4fc (Executed, 180 became
179). In mode B, the frame on which the decremented value is 0x84 looks up a resource
and plays a sound (Executed: the counter became 0x84 and one of those calls ran).
When the counter is 0 it becomes 0xffff and the two lock words are cleared, and the
rest of the match logic waits for the next frame (Executed). The same block also
clears 0x503890 (Observed, the store beside the two that were read back).

### 3.2 Deaths, lives, and the end

`arena_onPlayerKilled` 0x305580 is the score writer. A victim object whose flags include
0x20000 returns immediately (Executed). A null killer, or a killer with the creature flag
0x20, scores: mode A calls `arena_addKill(killer, 1)`; mode B decrements the life
halfword. A player killer (flag 0x40) whose slot byte equals the victim is a suicide and
tail-calls `arena_loseLife`. Any other killer also tail-calls `arena_loseLife`
(Executed: the other player, a null killer, a pet, and an object with neither flag).

`arena_loseLife` 0x305650 decrements the kill halfword in mode A and the life halfword
otherwise. `arena_addKill` 0x3056cc always adds 1, not its amount argument. A player is
credited on the slot byte at object +0x3c8. A creature is credited on the signed owner
byte at +0x5a when that byte is at least 0. A null killer, or an object with neither
flag, credits slot 0 when `g_numPlayers` is 1 and returns otherwise. In mode A an amount
of 0 returns before the credit (Observed at the branch; the executed calls all passed 1,
which is what `arena_onPlayerKilled` passes). A pet kill was executed and landed on the
owner's slot.

`arena_addLife` 0x3058c0 adds one life only when mode B is set and mode A is clear
(Executed, both the grant and the two refusals). Its caller outside this file is
SpellResurrect. The purchase inside the run task is separate: `arena_grantLife` 0x307ee0
adds one life, stores 0 in the overlay timer, and stores 0x80 in the HUD word at
0x4f6950 + slot × 4, then plays a cue (Executed through the gold path; the cue calls
were stubbed).

That purchase is the tail of the run task, and the tail runs only while mode A is clear
(Observed, the branch at 0x307170). The count at 0x4f8420 and the slot indices at
0x4f8440 name who may buy. If that slot's gold (record +0xe4) is at least the budget at
0x8e7358, gold decreases by the budget, the budget doubles, and `arena_grantLife` runs.
Init stores 100 there (0x304e70, Observed). One purchase was executed: gold 150 and
budget 100 became gold 50, budget 200, lives 1, timer 0, HUD word 0x80.

`arena_respawnPlayer` 0x305784 returns when mode A is clear and the signed lives are
below 0, when `net_isSlotActive` 0x13dd40 returns 0, or when the intermission halfword
is nonzero. Otherwise it stores 240 in the dead-countdown halfword at
0x4f84a8 + slot × 2, copies lives into the snapshot, calls `arena_pickSpawnPoint(0, slot,
…)`, then `player_respawn(slot, pos, facing, 2, 3)`. The 2 and the 3 are the values
passed (Executed). What `player_respawn` does with them is the spread and radius in
`docs/spec/skills-35-68.md`; that function was stubbed here. After it returns, the arena
caller writes maximum hit points and maximum mana over both current values (Executed,
80 and 40). The screen effect 0x322954 runs when this slot is the local slot and either the
network byte is set or there is one player (the branch at 0x305874). Executed: the
only offline player got it, and a two-player game did not. The world walk 0x14a610 is then called with
`arena_visitCreature` 0x306af0. A player, including a player who also has the creature
flag, takes no draw. A non-player creature takes one shared draw, and bit 0 of that draw
calls the virtual at vtable +0xb8 with argument 1 (Executed, both bits of the draw).

During the intermission, an active slot can still play when its record hit points are
above 0 or its signed lives are at least 0. Inactive slots are skipped. If every slot is
out, the end flag at 0x503894 is set, `arena_openEndPrompt` 0x307ebc runs, and the
countdown is cleared (Executed: lives −1 and 0 hit points).

In the live match an empty-wave scan runs every 128 frames (`g_simFrame` 0x44fdcc
masked with 0x7f) while the end flag is clear. The walk is 0x14a610 with callback
0x3069e8, and a living count of 0 opens the end prompt (Observed; that callback was not
run). The player scan that follows keeps an active slot in while lives are at least 0,
or record hit points are above 0, or the dead countdown is still positive. If every
active slot is out and some active slot still has a snapshot above 0, the task calls
`arena_nextWave(0)` (Executed). If no snapshot is above 0, the end flag is set and the
prompt opens (Executed). A player already at −1 keeps the snapshot from before that
death, because the wave's snapshot copy skips that slot. One tick was executed; a second
tick that would see the same snapshot again was not.

### 3.3 The end prompt

`arena_openEndPrompt` ranks the slots and stores 0 in the fade word at 0x8e735c
(Executed). `arena_rankSlots` 0x307e50 writes slot 0, 1, … into the bytes at 0x8e7348 and
qsorts them with element size 1 and `arena_compareKills` 0x307df0. The comparator returns
−1 when the first slot has more kills. Equal kills return 1 when the first slot's index
is higher, and 0 otherwise (Executed for both orders of a 5-versus-1 pair and of a tie).
The sort that was run put the slot with 5 kills first. The tie order after qsort was not
asserted; the comparator is not a strict ordering when the lower index is the first
argument.

`arena_drawPrompt` 0x3075dc adds 0x3c61029b to the fade, stores it, and if the sum is
above 1.0 stores 1.0, then draws (Executed: one step from 0, and a value already at 1.0
staying there). The run task reads that float and accepts the confirm and cancel buttons
only when it compares equal to 1.0. `docs/skills.md` records that the draw task and its
helpers write this word and nothing else that would change the match. This round did not
re-check every store in the draw task. The run task does read the word, so a machine
that did not run the draw task would disagree about when the buttons count. Whether
every lockstep machine runs the draw task was not settled here.

Confirm, once the fade is 1.0 and the end flag is set, restores each active player's
saved record, calls `arena_shutdown`, copies `arena_levelName` into the pending buffer,
and leaves mode B set (Executed: shutdown ran, one name was copied, mode B stayed 1).
Cancel stores 0 in mode B and 1 in `g_sessionExitCode` 0x41b508, and copies no name
(Executed). The earlier claim that the run task clears mode B on the end prompt is this
cancel path.

## 4. Mode A, versus

Kills, not lives. A kill-limit byte at 0x4f8408 is read sign-extended. The front end at
0x1e1a58 stores 5 when its index is 0, 10 when the index is 1, and 25 otherwise
(Observed). The net launch at 0x137484 copies message byte +0xa2 with an unsigned load
and a byte store into the same address (Observed); the match then sign-extends it. The
file image of the byte is 0. A limit of 0 makes any kill halfword of 0 or more end the
match. The compare that was executed used a limit of 10: a kill halfword of 10 opened
the end prompt, and 9 did not.

Opening the prompt sets the countdown to 1 and calls `arena_openEndPrompt`. There is no
monster wave. `arena_startWave` resets the scores (lives back to 2, timer 2.0) and skips
the recipe. Respawn ignores the life counter: a slot at −1 still respawns while the
intermission is 0 and the slot is active (Executed). The intermission gate still
applies. When the intermission expires, mode A always changes level, including when
waves-left is not 0 (Executed). The rotation is section 1's `(index + 1) mod 13`, with 0
replaced by the scan.

Mode A still keeps the life halfwords. It does not read them for the kill limit, the
respawn gate, or `arena_addLife`.

## 5. Where a player appears

`arena_pickSpawnPoint` 0x3050a4. The spawn table is the pointer at 0x503888. Each entry
is 16 bytes: xyz and a signed halfword angle at +0xc. `arena_registerSpawn` 0x30503c
writes one entry. Index −1 appends at the count byte 0x8e7342 and increments it; any
other index overwrites that slot and leaves the count alone (Executed). The level
factories pass 0 for the start and −1 for an alternate. A count of 0 on the draw paths
below divides by zero.

**a0 ≠ 0, the wave placement.** The ring is centred on entry 0. The radius is 180
(0x43340000) in mode A and 36 (0x42100000) otherwise. The angle is the low 16 bits of
`s16(65535 / count) * slot`, where count is `net_countActiveSlots` when that count is
above 0 and a zero word otherwise. z is copied from entry 0. `world_findFreeSpot` is
called with spread 36 and radius 24. If its ok byte is 0, one retry uses spread 240 and
radius 24. There is no third search (Executed, including the retry).

Facing, when the facing pointer is nonzero. If the word at 0x4f7124 is set, facing is
that slot's table angle minus 0x4000. Otherwise it is
`s16(−0x4000 − math_atan2_16(pos.x − entry.x, pos.y − entry.y))`, with `math_atan2_16`
at 0x166798. Mode B then subtracts 0x8000. All of these are the low 16 bits (Executed,
scramble set and clear, mode A and mode B). The direct stores found for 0x4f7124 are
zeroes. What a session writes through the pointers taken at 0x13748c and 0x1e1910, and
what net message +0xf4 contains, is **Unknown**. The branch itself was executed both
ways on a value the test stored.

**a0 = 0, the respawn.** A network game draws one index, `draw % count`, from the shared
generator and sets facing to that entry's angle plus 0x4000 (Executed, seed 20973).
Offline, an entry is a candidate when the xy distance from its point to `g_cameraFocus`
0x44f048 is strictly below 240 (0x43700000). The draw is then modulo the number of
candidates, and facing is again the angle plus 0x4000 (Executed). If no point is inside
240, `Camera_getTarget` 0x207478 reads the camera at the pointer 0x4f8450 and
`world_findFreeSpot` is called with that target, spread 72 and radius 24, and facing is
stored as 0 (Executed). The levels note that names this point 0x45f048 is an arithmetic
error: the address built by the `lui` / `addiu` pair is 0x44f048, which is
`g_cameraFocus`.

## 6. The overlay

The overlay is the life counter `arena_drawHud` 0x305904 draws, and only while mode B is
set, mode A is clear, `g_inFrontend` 0x41b510 is 0 and `g_localMenuOpen` 0x41b69d is 0
(Observed at the four branches; the executed draw had all four in the drawing state).
A slot is drawn while its timer is strictly below 2.0.

`arena_tickOverlay` 0x307f68 leaves a timer that compares equal to 2.0 alone (Executed).
Any other timer gains 0x3c2af07f. A result above 2.0 is replaced with 2.0 and the current
lives are copied into the snapshot (Observed at 0x307fc0). The executed step started at
0, stayed below 2, and left the snapshot alone.

For each of five glyphs, k = 0..4, the parameter is
`max(0, timer − k * 0x3cf5c28f)`. The glyph is drawn when that value is at most 1
(Executed through `vec3_hermite` 0x162310: the parameter and the output matched). k = 0
uses the font word at 0x4f7100; the others use 0x4f7104. The colour byte is `128 − 16k`
and the second figure passed to 0x1ec360 is `2000 − 200k`.

The curve is a hermite from the anchor to the screen position. The anchor words at
0x4f6730 (x) and 0x4f6710 (y) are integers converted with `cvt.s.w`, and so is the point
`0x1e0430` writes. The outgoing tangent starts at (259, 290, 0). The incoming tangent is
(−500, −500, 0). If the screen x is strictly above 320 and the outgoing x tangent is
still positive, that tangent is negated, and the negated value is the one later slots in
the same call see (Executed: slot 0 at screen x 100 left it positive, slot 1 at 400
received the negation). The basis, in the order the function multiplies, is
`h00 = (2t³ − 3t²) + 1`, `h01 = −2t³ + 3t²`, `h10 = (t³ − 2t²) + t`, `h11 = t³ − t²`,
and each axis is `((p0·h00 + p1·h01) + m0·h10) + m1·h11`. t = 0 returns p0 and t = 1
returns p1 (Executed).

`SpellArena_run` 0x305bbc reads the same intro counter. While the signed counter is at
least 61 it sets bit 1 of the flag word at owner +0xc (`spell + 0xc` is the owner).
Below 61 it clears that bit with a mask of −3, so bit 0 stays (Executed from 0x13 down
to 0x11 at counters 40, 10 and −1, and from 0x11 up to 0x13 at counter 180). Below 30
it returns after the flag store: no particles and no tint (Executed). At 30 and above
it tints eight halfwords, two copies of (0x56, 0x35, 0x21, 0x3d) at owner +0x90
(Executed at 180, where the particle count truncates to 0, and at 40, where the loop
ran). The particle calls in this difftest were stubbed and the joint count was forced
to 1. The positions themselves were executed on `t3/research-combat` (that worktree's
`docs/spec/combat-round6.md`, 184 of 184): `int(23 × (1 − (counter − 30) × 0x3bda740d))`
samples, every fourth from one definition and the rest from another, and a non-positive
count still writes the tint. During play the counter sits at −1 once the intro has
finished, and only the flag clear runs.

## 7. Damage, versus a story fight

The pipeline is `damage_apply` 0x1e8230, already matched in `docs/spec/combat.md` and
`tools/ref_combat.py`. This round ran it twice on the same hit, seed 20973, attack
rating 100000, no critical, an empty descriptor, and the cutscene flag set so the music
counter did not move.

Mode A adds two steps that a story fight skips.

- Armour mitigation applies to a player victim always, and to every victim while mode A
  is on. The cut is armour times 1/30 (0x3d088888), then each end of the range is kept
  at least half of itself and at least 0. A monster with armour 300 and a flat 100 was
  unchanged with mode A clear, and matched that bound with mode A set.
- After the rest of the pipeline, mode A and a player victim multiply the damage by 0.5.
  A player with armour 0 and a flat 40 took half the mode-off amount when mode A was
  set. The monster was not halved: its mitigated amount differed from half of the
  unmitigated 100.

The stun chance at 0x308c10 is 0 while mode A is on (`docs/spec/combat.md` section 4).
The mode-A player hit produced no stun event.

Mode B does not enter either step. It does not mitigate a non-player, and it does not
halve a player. The half is mode A's, after mitigation, and only for a player victim.

Floating damage numbers for a player victim are drawn in mode A, for a different player
attacker, and not in the front-block case (mode A, player state 8 or 0xb, flags 0x20040
clear). That gate is the one in `docs/spec/combat.md`; this round's hits did not assert
the text.
