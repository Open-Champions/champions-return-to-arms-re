# Return to Arms v2.00: kill XP, level-up, and point spending

Scope: SLUS-20973 v2.00, checked with `tools/ee_emu.py` on constructed states.
**Observed** means a rule read from the original instructions at the address
given. **Executed** means an interpreter comparison or probe named here passed.
This is not a live-game or console claim. No experience-table entries are copied.

## Kill award and sharing

**Observed** `Creature_processDamage` 0x111e3c–0x112248: sum the signed earned
levels (`R+0x59`) of the active player slots. Compute
`raw = trunc(powf(creatureExp / float(levelSum), 1.4f))`, then
`xp = trunc(float(raw) * 0.75f)`. The creature's experience value is at
`creature+0xd8`. With one player, an alive record gets `min(xp, cap(level))`;
a dead record gets none. With two or more players, every record gets a share:
0.6 for the last-attacker player, 0.4 for each other player, or 0.5 for each
when no player made the kill. Truncate each share separately, halve it (and
truncate again) for a dead record, then cap it. Thus shares need not sum to
the original XP. `cap(l) = table[l+1] - table[l]` below 80 and `table[l]` from
80 onward. The class-0 killer receives mana equal to monster maximum HP / 30,
clamped to maximum mana, after `giveExp`; a lone class-0 player receives it
when awarded XP. The orb draw and shared-seed constructor are separate from
the XP amount. **Executed** the full kill stretch and model comparison in
`tools/difftest_combat.py`; the model is `tools/ref_combat.py::kill_experience`.

## XP table and level transition

**Observed** the 81-entry signed XP threshold table starts at 0x41b558.
`table[l]` is the total XP needed to leave level `l`; `table[80]-1` is the
stored XP ceiling (entry 80 at 0x41b698). `player_giveExp` 0x1d3150 adds the
award, clamps to that ceiling, and loops while `exp >= table[earnedLevel]`.
Each iteration increases earned level `R+0x59` by one, grants three stat
points at byte `R+0xec`, grants skill points at word `R+0xe8` by the **old**
level band (1 for 1–5, 2 for 6–15, 3 for 16–25, 4 for 26–35, 5 for 36+),
and calls `player_recalcStats` 0x1b6458. `stats_screen` reads that stat byte
at 0x1d1f64 and passes that byte to `sprintf` 0x3b7ef0. Its later load of the
skill word at 0x1d1f84 is compared with 1 at 0x1d1f8c and is not the stat
balance. `skills_screen` reads the skill word at 0x1d57e0 and rejects a
non-positive value at 0x1d57e4 and 0x1d5850. The 1–5 sum is the word store
at 0x1d3214; the +3 is the byte store at 0x1d3220. If current HP was positive, it then
fills current HP and mana to their new maxima. This repeats for multi-level
awards. It does not advance the separately acknowledged level `R+0x58`;
inventory message 9 does that when the owner opens the level-up panel
(`menu_openInventory` 0x1c15c8; `inventory_onJoinPanel` 0x1c0360).
**Executed** `tools/difftest_combat.py` compares `tools/ref_combat.py::give_exp`
against the original, including the per-class stat recalculation and refill.
**Executed** again in `tools/difftest_levelup.py` on seeds 20973 and 7, reading
the threshold words from the executable and not copying them here: one below
`table[old]` does not level; the exact word does. Old levels 5, 6, 15, 16, 25,
26, 35, 36 and 79 grant 1, 2, 2, 3, 3, 4, 4, 5 and 5 skill points. Stat points
are a byte add of 3 (254 becomes 1). With the skill word set to 41 and the
stat byte set to 70, those same old levels store 42, 43, 43, 44, 44, 45, 45,
46 and 46 at `+0xe8` and 73 at `+0xec`. Experience already equal to `table[7]`
at level 5 takes levels 5, 6 and 7. Classes 0–6 produce the same point deltas:
`player_giveExp` does not read the class word. With the object pointer left
null, `player_recalcStats` copies the four base words at `+0x78` to the
effective words at `+0x90` (0x1b64b0) and does not enter its class-constant
chain: 0x1b64d8 branches to 0x1b6a4c when `+0x43d8` is zero. Those maxima stay
the combat comparison.
A current-HP value greater than zero is replaced by the stored maxima; a zero
HP value is left, and mana is left with it. Acknowledged level `R+0x58` is
not written. The shared seed at 0x404464 is not drawn.

## Stat point input gate and handler

**Observed** `stats_screen` 0x1d1db8 reads the owner pad edge word at
`0x41bfe8 + 88*padIndex`, where the pad index comes from the local panel at
0x4f65ec. At 0x1d2474–0x1d2498 it requires the `0x40` edge mask from
0x41bfbc and a zero panel gate word at 0x4f65cc. Its level-up stat half
also requires screen argument 2, `R+0xee == 0`, and the timing expression at
0x1d1eb4–0x1d1edc to be at least 3000. The selected row word at 0x4f65d0
maps 0–3 to calls of `invmsg_sendStatPoint` 0x1c5780 at
0x1d24d4/0x1d24f4/0x1d2510/0x1d252c. Other rows do not send.
**Executed** `tools/difftest_levelup.py` runs the original screen with both
seeds: all four rows send their own index; wrong page, edge, panel state,
level-up half, or timer gate suppresses the send. A zero point balance still
sends; the message handler owns that check. This closes the stat-point input
gate left **Unknown** in `t3/research-inventory-screen` 4a8a78a, for this
constructed level-up page state. Full menu navigation and rendered selection
remain **Unknown** in this probe.

**Observed** the stat screen has no pointer box: `stats_screen` never loads
the cursor floats at `panel+0x44`/`+0x48`. Its row is the list cursor of
`menu_cursorInput` 0x1c6570, called at 0x1d2350 with four rows on the panel
struct at 0x4f65b8, so 0x4f65d0 is that struct's `+0x18` row and the "panel
gate" 0x4f65cc is its `+0x14` move direction. The direction comes from the
held pad word at `0x4028d8 + 88*slot` (0x1c6438): bit 0x4000 or 0x200000
starts a move of +1 only while the row is at most 2, bit 0x1000 or 0x100000
a move of −1 only while the row is above 0. The row changes when the move's
smoothing (`math_hermite` 0x1658f0) finishes, then `+0x14` returns to 0.
**Executed** (`tools/difftest_progression.py:397-457`, both seeds): one held
frame starts `+1` from row 1 and `−1` from row 2; row 3 held down and row 0
held up stay put with direction 0 for 40 frames (no wrap); holding down from
row 0 for 200 frames visits rows 1, 2, 3 one step at a time, and up from 3
returns to 0. A confirm edge on the frame a move starts does not send; the
same edge with nothing held sends row 1 from 0x1d24f4. The early returns of
`menu_cursorInput` on 0x41b518+slot, 0x86a680+4·slot and 0x41b928 were left
zero and are **Observed** only.

**Observed** inventory message 6 calls `inventory_onStatPoint` 0x1c2548.
For index 0–3, a nonzero `R+0xec` increments base stat word
`R+0x78 + 4*index` and decrements the point byte, then calls
`player_recalcStats`. When the point byte reaches zero it marks `R+0xee = 1`
for the skills half. The handler also accepts script-only indices 4–7 as
free base-stat raises and index 8 as a skill-point grant; the UI sender above
cannot select those. Message-handler behavior is modeled by
`tools/ref_messages.py::on_stat_point` and compared by
`tools/difftest_messages.py`.

**Executed** what a spend changes, end to end
(`tools/difftest_progression.py:464-587`). The combat rig of
`tools/difftest_combat.py` runs the original `inventory_onStatPoint` and,
through it, the original `player_recalcStats` (its object pointer is a live
player object, so the class-constant chain runs). The expectation is the
spend rule above followed by `tools/ref_combat.py::recalc_stats`. 64 generated
players per seed, stat index `case % 4`, point bytes 0, 1, 2, 5 or 40, all
equal (45 and 52 of them had a point to spend). Against the same world
recalculated without the spend, the fields that moved were only: index 0
(strength) the load limit `R+0x124`, index 1 (intelligence) maximum mana
`R+0xc4`, index 2 (dexterity) the object's armour, index 3 (stamina) maximum
hit points `R+0xb0`; the effective words `R+0x90` and the object's bonus
bytes follow the base word. A spend that reaches zero points leaves
`R+0xee = 1`. No spend writes `R+0x58`. Equipment modifiers, the load cap and
the class constants are the combat comparison's random cases, not retail
characters.

## Skill point spending

**Observed** `skills_screen` 0x1d4660. A zero return from the first picture
lookup at 0x1d47b4 leaves before any send (**executed**). That is a missing
resource, not a point-spend rule. The owner slot is the word at 0x4f65ec for
menu argument 0. The class word of that slot selects the tree
(0x1d47c0–0x1d484c). A row is selected when the cursor integers
`trunc(panel+0x44)` and `trunc(panel+0x48)+panel+0x28` lie in
`[panelX+rowX, panelX+rowX+0x32]` and `[rowY+0x9e, rowY+0xd0]`
(0x1d4aac–0x1d4af4). **Executed** with `panel+0x28` zero: an interior point
sends and a point outside the tree does not.

**Observed** the box words: `panelX` is the word at `panel+0` and the panel is
0x4f4040 for menu argument 0 (0x1d46a8–0x1d46b0); the two cursor integers are
`cvt.w.s` of `panel+0x44` and of `panel+0x48`, the second plus the word at
`panel+0x28` (0x1d4734–0x1d47a8); `rowY` has no panel offset. Each bound is a
`slt` reject, so all four edges are inside. **Executed**
(`tools/difftest_progression.py:362-391`, both seeds) on class 0 node 0 and
class 3 node 4 with `(panel+0, panel+0x28)` of (0, 0), (40, 13) and (−24, −13),
14 cursor points each: the low and high x and y edges and both corners send;
one past any edge does not. `x_hi + 0.75` sends and `x_hi + 1.25` does not,
`y_hi + 0.75` sends and `y_lo − 0.25` does not: the conversion truncates in
this interpreter (the console's rounding mode for `cvt.w.s` is the
interpreter's model, not a capture). The x edges move with `panel+0`, and the
y edges do not; `panel+0x28` shifts only the cursor.

The confirm edge is `pad+0xc &` the mask at 0x41bfbc. In this executable that
mask is 0x40. Edge 0 and edge 0x10 do not send; edge 0x40 can. While
`panel+0x30` is zero and `panel+0x50` is 5, the same call stores `pad+8 & 2`
at 0x4f4878 (0x1d5010–0x1d5040). A nonzero word there skips the send
(0x1d54d8–0x1d54e0). **Executed**: page 5 with held bit 2 suppresses; page 0
does not latch that bit; a preset 1 suppresses on page 0; `panel+0x30 == 1`
keeps a zero gate on page 5 and still sends. `R+0xee` is not read: half 1
still sends. Slots 0 and 1 were both executed.

The prerequisite walk is 0x1d5530–0x1d576c. A prerequisite of −1 passes. A
prerequisite of 0 passes when skill 60 or skill 61 has rank at least 1
(**executed** each skill alone, and neither). Otherwise a passive prerequisite
needs that mask's rank at least 1, and a skill prerequisite needs that id's
rank at least 1. These further alternatives also pass when the primary does
not, **executed** on the row that carries the id:

| Class | Row ident | Also unlocked by rank ≥ 1 of | Send |
|---|---|---|---|
| 2 | passive 0x40 | skill 0x3b | passive mask |
| 3 | skill 33 | skill 0x30 | skill id |
| 3 | skill 74 | skill 0x2f | skill id |
| 3 | passive 0x40 | skill 0x3d | passive mask |
| 4 | skill 57 | skill 1 | skill id |
| 2 | skill 97 | skill 0x28 | skill id |
| 2 | skill 40 | skill 0x0b | skill id |
| 4 | skill 95 | skill 18 | skill id |
| 6 | skill 90 | skill 86 | skill id |

Class 1 node 4 is ident 55. That row exists, and its prerequisite kind is 1,
so the passive-0x40 compare at 0x1d558c is only on the passive-prerequisite
chain and does not see it (**executed**: mask 0x40 does not send). Class 4
node 19 is ident 95 and class 6 node 9 is ident 90. Both rows sit inside the
terminator, both prerequisite kinds take the skill chain, and both
alternatives are the rows above.

Rank 20 does not send; rank 19 does (0x1d5778). The level test is
acknowledged `R+0x58 < row.need + current rank` (0x1d57a8–0x1d57bc).
**Executed**: acknowledged 0 with earned 40 does not send a need-1 row;
acknowledged 1 with earned 1 does. The passive-table walk must see a row
before `END` (0x1d4d88–0x1d5774). **Executed**: writing `END` over the first
runtime name suppresses the send. Signed skill points `R+0xe8` must be
greater than zero (0x1d57e4 and 0x1d5850). Zero and −1 do not send. That is
the screen's only price check. `skills_nextRankCost` 0x1d436c was stubbed;
its displayed result was not compared.

A kind-0 row then calls `invmsg_sendSkillPoint` at 0x1d580c with
`(slot, 0, low 32 bits of the row mask)`. A kind-1 row calls the skill
object's virtual entry at vtable+0x28 (0x1d5874–0x1d5884) and sends at
0x1d58dc with `(slot, 1, skill id)` only when the returned float is
`<=` maximum mana at `R+0xc4` (`c.ole.s`, 0x1d5890–0x1d5898). **Executed**
with a planted return: 10 against maximum 10 sends, and 11 does not. Current
mana `R+0xc0` is not the operand.

**Observed** vtable+0x28 is slot 5, `manaCost(level)`, and the level passed
is `player_getSkillRank(slot, id) + 1` (0x1d5858, 0x1d5870): the cost of the
rank being bought. On a refusal, for a local owner only (`net_isLocalSlot`
at 0x1d58ec), the screen plays `game_butn_cantdo.anm` and opens
`hud_showPlayerNotice` 0x1d9954 with the keys
`NotEnoughMana` and `NotEnoughManaDesc` (0x1d58ec–0x1d5948). **Executed** the
original bodies; see "What learning does on rows 1–2" below.

Once the prerequisite, row count, rank and level have passed, the screen
calls `player_recalcStats` at 0x1d5950 even when the point balance or the
float compare refuses the send. An earlier miss does not. **Executed** as
call presence; the body was stubbed and remains the combat comparison.
`R+0xee` still does not change.

**Observed** inventory message 7 calls `inventory_onSkillPoint` 0x1c2648.
It returns when points `R+0xe8 <= 0`. With kind 0, its value is a passive
mask: below rank 20 it spends exactly one point, rebuilds abilities at
0x1d34ac, and raises the passive rank. With nonzero kind, its value is a
skill ID: below rank 20 it spends one point, raises an existing rank or adds
an ability record (kind-3 skills set rank 1 directly). The handler itself
does not check class, prerequisites, level, or screen price and does not call
`player_recalcStats`. `tools/ref_messages.py::on_skill_point` and
`tools/difftest_messages.py` cover the original handler in constructed
message streams. `t3/research-campaign-combat` 328b072 also records a live
rig skill-point spend, distinct from this isolated interpreter evidence.
The screen's sender rule is the section above; the handler still accepts a
message the screen would not have sent.

### What learning does on rows 1–2

"Row" here is a distinct node `y` in the class tree, read at run time from
the trees after `classSkills_init` 0x1ac7a8; the two smallest values are rows
1 and 2. Need levels, positions and prerequisites are read from the
executable and not copied here. **Executed** the nodes they hold
(`tools/difftest_progression.py:127-136`):

| Class | Row 1 | Row 2 |
|---|---|---|
| 0 | skills 60, 61 | passives 0x20000, 0x10; skill 2 (dodge) |
| 1 | skill 60 | skill 16 (holystrike); passive 0x40 |
| 2 | skills 60, 61 | skill 4 (diseasebolt); passive 0x10; skill 59 (lifetap) |
| 3 | skills 60, 48 (archery), 61 | skills 33 (rangercriticalhit), 46 (multifire); passive 0x40 |
| 4 | skill 60 | skills 23 (shockoffrost), 37 (shock); passive 0x200 |
| 5 | skills 60, 61, 79 (throwing) | skills 76 (roar), 72 (summonaxe) |
| 6 | skills 60, 61 | skills 89 (poisonbolt), 88 (drowsy); passive 0x200 |

The Skill objects are the game's own, built by the static initialiser
0x16ac74 and the statistics pass 0x1ebca0 inside the interpreter. 0x16ac74
runs every static constructor and one of them sets the seed word, so each
probe plants its seed afterwards (`tools/difftest_progression.py:79-108`).

**Mana cost (slot 5), executed** (`tools/difftest_progression.py:229-311`,
both seeds). For each of the 26 skill nodes and current ranks 0, 1, 9 and 19,
the skill's own slot-5 body runs at `rank + 1` with only Skill code followed
and no stubbed call. Its result equals the slot-5 model of
`tools/ref_skills_a.py`, `ref_skills_b.py` or `ref_skills_c.py` bit for bit:
104 bodies per seed, 16 distinct skills. The skill screen then runs with
that real body. Maximum mana equal to the result sends `(slot, 1, id)` from
0x1d58dc. One float below (−FLT_MIN when the cost is 0) sends nothing and
opens the notice from 0x1d5948 with both keys, giving 208 screen runs per
seed. Each run makes exactly one slot-5 call, from 0x1d5884, with
`(skill + adjust, rank + 1)`, and calls `player_recalcStats` once from
0x1d5950. The formulas themselves are the per-skill specs
(`docs/spec/skills-01-34.md`, `skills-35-68.md`, `skills-69-101.md`) and the
statistic tables in `docs/skills.md`. They are not restated here. Executed
results: skills 60, 61 and 79 return the base 1.0, skill 48 returns its
statistic 4, and skills 2 and 59 return 0. **Inferred** consequences: a
character whose maximum mana is below 1.0 cannot buy 60, 61 or 79. Each
archery rank needs maximum mana of at least the new rank. Dodge and Life Tap
always pass this compare.

**Learning, executed.** On every sent case the original message-7 handler
then runs on the same memory (`tools/difftest_progression.py:274-294`):
104 per seed. Points go from 3 to 2. `player_getSkillRank` then reads
`rank + 1`. The only stores are the point word, the rank list at `R+0x4b08`
and the ability records at `R+0x4440`. For rank 0, a kind-3 skill (60, 61,
48, 79, 2, 59 here) gets `player_setSkillRank(slot, id, 1)` (tail jump
0x1c2768). Every other kind gets `player_addSkillAbility` (tail jump
0x1c2784), which fills the first free record (`+0x20 == −1`) with the name
`newstyle` and the id. Above rank 0 no record is added. **Observed**
`player_setSkillRank` 0x1bf3a0 appends a new id at the old terminator and
stores no new terminator (0x1bf418–0x1bf434). What follows it in a real
record is **Unknown**. Neither path calls `player_recalcStats` or writes
`R+0x58`.

**Passive nodes, executed** (`tools/difftest_progression.py:317-356`): the 7
passive nodes of rows 1–2 at ranks 0, 1 and 19, 21 per seed. Each sends
`(slot, 0, mask)` from 0x1d580c. The handler raises the rank byte to
`rank + 1`, spends one point, calls `player_rebuildAbilities` 0x1d34ac and
ORs the mask into the u64 at `R+0x128` (`sd` at 0x1d37e8). With load limit
100.0, the first rank of mask 0x40 leaves 115.0. A later rank (mask already
in `R+0x128`) and every other mask leave it, and maximum HP and mana are
unchanged for these masks.

**Rank effects, executed** through the combat rig, with the expectation from
`tools/ref_combat.py` (`tools/difftest_progression.py:464-587`):

- Skills 60, 61, 48, 79 at ranks 0, 1, 9, 19, 48 cases per seed. The original
  handler raises the rank, then the original `Player_recalcDamage` 0x1b7158
  runs with a weapon of damage type 1 (60), type 8 (61), animation class 4
  (48) or 6 (79). Attack and the damage range equal `recalc_damage` at the
  new rank. The rig's stand-in Skill objects were given the kind word that
  the game's own initialiser leaves for these four ids. Their statistic
  getters are the rig's scripted stubs. So for 48 and 79 the fraction
  itself is checked separately: the original
  `SkillArchery_getStat0Fraction` 0x2dbcac and `SkillThrowing_getStat0Fraction`
  0x304b54 equal the skill models at the learned rank, on the real objects
  (8 per seed).
- Passive 0x40 at ranks 0, 1, 5, 19 for classes 1 and 3, 16 cases per seed:
  the handler, then the original `player_recalcStats`, equal `recalc_stats`
  with the raised rank (load limit `+15.0` per rank).

**Unknown here:** what masks 0x20000, 0x10 and 0x200 change in play. Their
readers were not executed. For the other row-2 skills (passives 2 and 59;
casts 4, 16, 23, 33, 37, 46, 72, 76, 88 and 89), the effect of the new rank
was not re-run after a learn. Their getters and cast bodies are compared on
their own in the skill difftests (`docs/spec/skills-*-executed.md`).

## Save and restore

**Executed** `save_snapshotPlayer` 0x216c80 for slots 0 and 1. The 0x4c30-byte
copy at 0x879ec0 keeps acknowledged level, earned level, experience, skill
points, stat points, class, and the bytes at `+0xed` and `+0xee`. A null
equipment pointer becomes −1. The object pointer is copied. `player_giveExp`
is not called. The shared seed is not drawn.

**Executed** the player loop inside `save_load` 0x221d60, from 0x221ec0
through the return to the next slot, for one pending record. Before that
loop the fixture directly stores different live levels, experience, both
point balances and the half byte. Those stores are not a stat or skill
handler. The loop then overwrites the live record with the snapshot,
`save_fixupPlayer` 0x216ea8 runs, and the object pointer is zero. The restore
put back earned 6, acknowledged 4, the saved experience and point balances,
and half 1. No level was applied and no point was spent. That probe did not
run the header, camera, quest or memory-card steps.

**Executed** `save_load` from its entry, and the same image through load
screen step 4 (`tools/difftest_progression.py:764-943`, seeds 20973 and 7, 6
runs per seed). The image is not hand-made. The original `save_build`
0x221914 builds it from state A: level `hub`, sub-level `west`, a one-act
table naming `hub` (the planted act row has the shape used by
`t3/research-save-screen`), a camera object at 0x4f8450, the view words at
0x44f110, minimap mode 2, two players with a pending level (earned 6,
acknowledged 4), difficulty 3, a play time, and three quest variables set
through the original `vars_set` 0x1ed854. Then direct stores change every
restored field (state B), and `vars_clearAll` plus a new variable `r3late`
run. Followed for real: `Camera_saveState`/`Camera_loadState`
0x203918/0x203a20 with `Camera_reset` 0x203210, the jump-gate writer and
reader 0x27dcf4/0x27dd30, `save_snapshotPlayer`, `save_fixupPlayer` with its
index helpers, `vars_getByIndex`/`vars_clearAll`/`vars_set`, `save_setAct`
0x2180a8 with `memcard_isBusy`, `save_findAct`/`save_getAct`,
`level_getQualifiedName` and the C library. Stubbed and recorded:
`save_storeLevelState` 0x21777c (world body, `docs/save-world.md` on
`t3/research-save-world`), `script_clearDeferred` 0x1eda08, four camera
helpers that `Camera_reset` calls (0x207308, 0x207310, 0x207318, 0x2035c8),
and `inventory_shareQuestItems` 0x1c4fa8. Results:

- Header: the 0x70 bytes land at 0x879e38. The pending name 0x41b6d0 and the
  side name 0x8e1a98 are `hub_west`, the marker 0x41b720 is 0xfd, the loaded
  flag 0x8e1ad6 is 1, the autosave countdown 0x88d40c is 99, and the live
  level name 0x41b721 is untouched. Difficulty 0x4f719c, play time 0x88d414,
  minimap mode 0x4f8400, `g_numPlayers` and act 0x88d3d4 come back.
- Camera: `Camera_loadState(camera, image+0x70)` at 0x221e74. Then
  `jumpgate_loadDestinations(image+0x70+0xc4)` at 0x221e80. The 13 view
  words at 0x44f110–0x44f143 come back. The other camera words are partly reset
  by `Camera_reset`, so the check is that a second `save_build` reproduces
  the camera section exactly.
- Players: `save_fixupPlayer` runs for slots 0 and 1 (0x22201c). Both records
  get back their acknowledged and earned levels, experience, both point
  balances, `+0xed`, `+0xee` and class. No level is applied.
- Quest variables: one `vars_set` per saved record from 0x222098, after
  `vars_clearAll`. **Executed** `vars_set` clamps to a signed byte, so 200 is
  saved as 127. `vars_clearAll` zeroes values and keeps names. A variable
  created after the save, `r3late`, therefore survives the load with value
  0 and appears in the next save.
- `inventory_shareQuestItems(0)` is called from 0x2221ac and 0x4f85b4 is
  cleared only when that word is 1. Words 0 and 2 leave it and make no call.
  `script_clearDeferred` is called once from 0x222074.
- A second `save_build` after the load reproduces bytes `+0` to `+0x13418` of
  the first image (header, camera, jump gates, minimap, player count and
  player blocks).
- Load screen: with `memcard_loadScreen` 0x219360 at load step 4 (card read
  finished, buffer at 0x4f8eec, flag 0x8e1ab9 set), the screen copies the
  whole 0x4bc78-byte image into `g_saveBuffer` 0x895580 and calls `save_load`
  from 0x219830. Every result above holds again. This is the step
  `t3/research-save-screen` c8895e2 ran with these callees stubbed
  (`docs/save-screen.md` lines 258–279 there). The card read, the card queue
  and the 0xf0-byte level directory remain that note's and the save-world
  note's. No memory-card I/O ran here.

**Unknown**: whether any later caller acknowledges the restored level or
clears `R+0xee`, and the level loader's use of the restored state
(`docs/save-world.md`, `t3/research-save-world`).

## Acknowledged level `R+0x58`

This answers the open question shared with `t3/research-hud-inputs`. Its
0642904/fb24f5e notes listed "the writer of acknowledged level `+0x58`" as
unknown, and its 0dc311c round answers it from the HUD side.

**Observed** (`tools/difftest_progression.py:593-650`): `.text` has 24 byte
stores with the literal offset 0x58. Of their functions, only
`player_importCharacter` 0x1bd458 (0x1bd520, 0x1bd528, 0x1bd57c) stores into
a player record. `DoorSwing_interact` also addresses `g_players`, but its two
stores use `$17`, which 0x28aa90 copies from the door argument. The only
store to the absolute 0x4d8b48 (`g_players + 0x58`) is 0x1bff6c in
`invmsg_dispatch`, case 9. A literal scan cannot see computed bases. The
creation store below uses base `R+0x50` with offset 8. The scan alone
therefore does not close the list. The executed writers below add what it
misses, and any other computed-base store stays **Unknown**.

**Executed** (`tools/difftest_progression.py:651-758`, both seeds, 12 per
seed):

- `menu_openInventory(slot, 1)` sends exactly one 3-byte game message
  `{9, slot, R+0x59}` from 0x1c1814. It stores `R+0xed = slot`, `R+0xee = 0`,
  panel `+0x50 = 5` and 0x4f65c8 = 1, and does not write `R+0x58`.
  `menu_openInventory(slot, 0)` sends nothing. **Observed** `hud_run`
  0x1db870 opens the menu only when hit points are above 0. It then passes 1
  when `R+0x58 < R+0x59` (0x1dbabc–0x1dbad8) and clears 0x86aa50+4·slot.
  Otherwise it passes 0 (0x1dbaf8). The pad edge and the gates before that
  call were executed on `t3/research-hud-inputs` 0dc311c
  (`docs/spec/hud-live-producers.md` section 6, lines 223–265 there). They
  were not rerun here. That note reaches the same message-9 store; the
  creation, import and save writers below are the non-play writers it does
  not list.
- `invmsg_dispatch` 0x1bfdb0 on `{9, slot, level, x}` makes one store: the
  low byte of the halfword at message +2 into `R(slot)+0x58`, at 0x1bff6c.
  `R+0x59` is unchanged.
- `inventory_onJoinPanel(panel, slot, 1)` takes the owner from the panel's
  word `+0x34`, not from its slot argument. Executed with the two different:
  it sends `{9, owner, R(owner)+0x59}` from 0x1c0478, stores
  `R(owner)+0xed = owner` and `+0xee = 0`, and writes neither record's
  `+0x58`.
- `player_initNewCharacter` 0x1b1d70 clears the record and stores 1 into
  `+0x59` (0x1b216c) and `+0x58` (0x1b2170).
- `player_importCharacter(slot, src)` copies both level bytes and caps each at
  50 (60 → 50, 51 → 50, 50 stays).
- `save_load` restores the saved byte as part of the player block (above).

So in play the acknowledged level rises only through message 9, carrying the
earned level when the owner opens the menu with a level-up pending. In
lockstep each machine applies it in message order (`docs/spec/game-messages.md`).
`player_giveExp`, the stat and skill handlers and `save_load`'s fix-up do not
raise it. **Unknown**: stores through other computed bases that none of these
probes reach.

## Verification on 2026-10-23

All commands used `PYTHONDONTWRITEBYTECODE=1` and the locally held,
SHA-256-pinned SLUS_209.73 v2.00 executable. `difftest_combat.py --quick
--seed {20973,7} -k player` passed 28 properties per seed; the same with
`-k 'kill experience'` passed 14 per seed. `difftest_messages.py --quick
--seed {20973,7}` passed 44 properties per seed, including 81/71 stat
messages and 65/82 passive plus 63/75 skill messages. The pinned inventory
branch's `difftest_inventory_screen.py` passed 38 properties across both
seeds. `difftest_levelup.py` passed 15 sender-gate cases per seed.
`python3 -m unittest discover -s tools -p 'test_*.py'` passed 652 tests.
The quick comparisons are bounded samples; the full suite is the Python
unit suite, not a full game integration run.

Audit fix rerun on 2026-10-23: `PYTHONDONTWRITEBYTECODE=1` level-up difftest
passed 15 stat sender cases on each seed; the full Python unit suite passed
652 tests. The skill sender was unprobed at that commit.

## Verification on 2026-11-03

Stdout for this audit-fix rerun is the untracked
`local/levelup-r3-difftest.log` and `local/levelup-r3-unittest.log`.

On the Mac mini, `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_levelup.py local/SLUS_209.73`
passed, and each of these lines is in that log for seeds 20973 and 7:
15 stat-point sender gates, 44 skill-point sender gates, 48 level-grant
cases, 9 point-balance sentinel crosses, and the pending level-up snapshot
and restore. `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'`
passed 652 tests in 4.754s; the unit log records `Ran 652 tests in 4.754s` followed by `OK`. The
executable was the same pinned SLUS_209.73. Seeds 20973 and 7 agreed. This
is interpreter evidence on constructed state, not a live level or a memory card.

## Verification on 2026-11-09

On the Mac mini, from the research worktree, with the pinned SLUS_209.73.
Stdout is the untracked `local/levelup-r4-progression.log`,
`local/levelup-r4-levelup.log`, `local/levelup-r4-companions.log` and
`local/levelup-r4-unittest.log`, produced after the last edit of this note
and of the tool.

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_progression.py local/SLUS_209.73`
passed with these lines for each of seeds 20973 and 7: 104 slot-5 mana bodies
of rows 1-2 (16 skills), 208 skill-screen mana compares, 104 sent skill points
applied by message 7, 8 archery/throwing fractions, 21 passive nodes, 84
cursor-box edge cases, 12 stat-screen row cursor edges, 64 stat spends, 48
skill learns followed by `Player_recalcDamage`, 16 passive 0x40 learns, 12
acknowledged-level writers and 6 `save_load` runs; plus one static line for
the `+0x58` store scan.
`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_levelup.py local/SLUS_209.73`
still passed its 15, 44, 48 and 9 cases and the pending restore on both seeds.
The companion models this note leans on passed again:
`difftest_combat.py --quick --seed {20973,7} -k player` (28 properties per
seed) and `difftest_messages.py --quick --seed {20973,7}` (44 per seed). The unit suite
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'`
passed 652 tests. Its log has the line `Ran 652 tests in` with that run's time,
and then `OK`. Interpreter evidence on constructed state: no console,
no pixels, no memory-card I/O, no live level.

## What the client can implement now

Executed in this note and its tools, so the client can stop refusing them:

1. The skill-screen box: `panel+0 + rowX ≤ trunc(x) ≤ that + 0x32` and
   `rowY + 0x9e ≤ trunc(y) + panel+0x28 ≤ rowY + 0xd0`, all edges inclusive.
2. The stat-screen row: a four-row list cursor that clamps at rows 0 and 3,
   moves one row per finished move, and blocks the stat send while a move is
   running (`+0x14` nonzero).
3. The mana compare with the real cost: call the skill's own slot 5 at
   `rank + 1` and send only when it is `<=` maximum mana. A refusal shows the
   `NotEnoughMana` notice to a local owner. For the 16 skills of rows 1–2 the
   ported slot-5 models are bit-exact with the original.
4. Message 7 on what the screen sent: one point, rank + 1, and, for a new
   non-passive skill, an ability record named `newstyle`. Passives also OR
   their mask into `R+0x128`, and passive 0x40's first rank adds 15.0 load
   once.
5. Stat spends and the learned ranks of 60, 61, 48, 79 and passive 0x40
   through `recalc_stats` / `recalc_damage` as in `tools/ref_combat.py`.
   Strength moves load, intelligence maximum mana, dexterity armour, and
   stamina maximum hit points.
6. Acknowledged level: raise `R+0x58` only from message 9 `{9, slot, earned}`,
   sent by opening the menu with `R+0x58 < R+0x59` (or by a level-up panel
   join). Creation sets 1. Import caps at 50. A save restores the saved
   byte.
7. `save_load` without the card: header copy, camera and jump-gate sections
   at their measured offsets, players with fix-up, quest variables
   (clear values, keep names, then set, values clamped to a signed byte),
   act, difficulty, time, minimap mode, player count, pending `name_sub`
   level with marker 0xfd, loaded flag, countdown 99, and the 0x4f85b4 == 1
   quest-item share. Then load screen step 4 as in `t3/research-save-screen`.

Still refused or unknown: memory-card I/O and the level directory body
(save-screen and save-world notes); the gameplay effect of passives 0x20000,
0x10, 0x200 and of nodes beyond row 2; the `skills_nextRankCost` display;
rendered selection (the `hud_run` gate before the menu opens is executed on
`t3/research-hud-inputs` 0dc311c); stores to `R+0x58` through computed bases
these probes do not reach.

## Ordered native port list

1. Read the original XP curve and class/skill tables from the authorized
   runtime inputs; preserve the 81-entry boundary and the separate earned
   and acknowledged level bytes. Do not embed guessed table values.
2. Port the exact kill award arithmetic, per-recipient truncation, dead
   shares, per-kill cap, and class-0 mana ordering; preserve shared-seed draw
   order and the last-attacker identity.
3. Port `giveExp` as a loop over thresholds, grants, stat recalculation and
   alive-only HP/mana refill, including awards crossing several levels.
4. Port the owner-local level-up panel and stat sender gate, then apply
   messages 6 and 9 in the simulation's message order. Raise `R+0x58` only
   from message 9, which carries the earned level. Keep `R+0xee` as
   presentation bookkeeping. A save image must round-trip both level bytes,
   both point balances and that half byte, and must not apply the pending
   level on load.
5. Port the executed `skills_screen` sender: tree prerequisite, every
   alternative in the table above, including class 4 skill 18 and class 6
   skill 86, rank below 20, acknowledged level, a positive skill-point word,
   and the passive-mask or skill-id send. Compare the skill's own slot-5
   cost at `rank + 1` with maximum mana before the skill send (executed for
   rows 1–2; other rows use the same call and their slot-5 models from the
   skill difftests). Then apply the already verified message 7 handler. Do
   not treat the handler as the sender. Use the inclusive cursor box above.
   Class 1 ident 55 exists; its passive-0x40 compare is only on the
   passive-prerequisite chain.
6. Compare verified layers against the existing `ref_combat` and `ref_messages`
   difftests, the stat gate probe and the skill gate probe on seeds 20973 and
   7; verify integration separately in a real level and multiplayer tick
   before claiming play parity.

Related prior research: `t3/research-player-state` 9c23686,
`t3/research-inventory-screen` 4a8a78a, and
`t3/research-campaign-combat` 328b072. Their `docs/spec/combat.md`,
`docs/spec/game-messages.md`, and `docs/issues/kill-loot-xp.md` supply the
models, message structure, and earlier runtime observations used here.
