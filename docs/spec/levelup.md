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

**Observed** inventory message 6 calls `inventory_onStatPoint` 0x1c2548.
For index 0–3, a nonzero `R+0xec` increments base stat word
`R+0x78 + 4*index` and decrements the point byte, then calls
`player_recalcStats`. When the point byte reaches zero it marks `R+0xee = 1`
for the skills half. The handler also accepts script-only indices 4–7 as
free base-stat raises and index 8 as a skill-point grant; the UI sender above
cannot select those. Message-handler behavior is modeled by
`tools/ref_messages.py::on_stat_point` and compared by
`tools/difftest_messages.py`.

## Skill point spending

**Observed** `skills_screen` 0x1d4660. A zero return from the first picture
lookup at 0x1d47b4 leaves before any send (**executed**). That is a missing
resource, not a point-spend rule. The owner slot is the word at 0x4f65ec for
menu argument 0. The class word of that slot selects the tree
(0x1d47c0–0x1d484c). A row is selected when the cursor integers
`trunc(panel+0x44)` and `trunc(panel+0x48)+panel+0x28` lie in
`[panelX+rowX, panelX+rowX+0x32]` and `[rowY+0x9e, rowY+0xd0]`
(0x1d4aac–0x1d4af4). **Executed** with `panel+0x28` zero: an interior point
sends and a point outside the tree does not. The inclusive edges of those two
intervals were not probed.

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
with a planted return: 10 against maximum 10 sends, and 11 does not. The
original virtual bodies were not run, so the meaning of that float for each
skill remains **Inferred** from the slot-5 mana-cost layout. Current mana
`R+0xc0` is not the operand.

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
and half 1. No level was applied and no point was spent. The header, camera,
quest and memory-card steps of `save_load` were not run. **Unknown**: whether
any later caller acknowledges the restored level or clears `R+0xee`.

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
   messages 6 and 9 in the simulation's message order. Keep `R+0xee` as
   presentation bookkeeping. A save image must round-trip both level bytes,
   both point balances and that half byte, and must not apply the pending
   level on load.
5. Port the executed `skills_screen` sender: tree prerequisite, every
   alternative in the table above, including class 4 skill 18 and class 6
   skill 86, rank below 20, acknowledged level, a positive skill-point word,
   and the passive-mask or skill-id send. Compare the planted virtual float
   with maximum mana before the skill send. Then apply the already verified
   message 7 handler. Do not treat the handler as the sender. Leave the
   original per-skill virtual bodies and the cursor-box edges unported until
   they are executed. Class 1 ident 55 exists; its passive-0x40 compare is
   only on the passive-prerequisite chain.
6. Compare verified layers against the existing `ref_combat` and `ref_messages`
   difftests, the stat gate probe and the skill gate probe on seeds 20973 and
   7; verify integration separately in a real level and multiplayer tick
   before claiming play parity.

Related prior research: `t3/research-player-state` 9c23686,
`t3/research-inventory-screen` 4a8a78a, and
`t3/research-campaign-combat` 328b072. Their `docs/spec/combat.md`,
`docs/spec/game-messages.md`, and `docs/issues/kill-loot-xp.md` supply the
models, message structure, and earlier runtime observations used here.
