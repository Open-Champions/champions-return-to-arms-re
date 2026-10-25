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
and calls `player_recalcStats` 0x1b6458. If current HP was positive, it then
fills current HP and mana to their new maxima. This repeats for multi-level
awards. It does not advance the separately acknowledged level `R+0x58`;
inventory message 9 does that when the owner opens the level-up panel
(`menu_openInventory` 0x1c15c8; `inventory_onJoinPanel` 0x1c0360).
**Executed** `tools/difftest_combat.py` compares `tools/ref_combat.py::give_exp`
against the original, including the per-class stat recalculation and refill.

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

**Unknown**: the skill-screen sender contract has no committed original-code
probe. Prior address notes place `skills_screen` at 0x1d4660 and candidate
`invmsg_sendSkillPoint` 0x1c57b8 calls at 0x1d580c (passive mask) and
0x1d58dc (skill ID). They describe node availability, rank/level checks at
0x1d54d8–0x1d57c0, and a virtual-call result compared with `R+0xc4` at
0x1d5850–0x1d58dc. These candidate call sites, their arguments, and the
conditions that permit each send still need a bounded `skills_screen` probe
with positive and suppressing cases on seeds 20973 and 7. Full class-specific
screen pricing and prerequisites remain Unknown. Do not substitute the
handler's acceptance rule for the screen's sender rule.

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
652 tests. The skill sender remains unprobed and Unknown as described above.

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
   presentation bookkeeping.
5. Probe the original `skills_screen` sender on seeds 20973 and 7. Assert both
   candidate call sites and arguments, then isolate the node, rank, level and
   virtual-result gates with positive and suppressing cases before porting
   availability, cost, or message 7 sending. Port the separately verified
   handler's passive/skill-rank and ability-list changes.
6. Compare verified layers against the existing `ref_combat` and `ref_messages`
   difftests and the stat gate probe on seeds 20973 and 7; verify integration
   separately in a real level and multiplayer tick before claiming play parity.

Related prior research: `t3/research-player-state` 9c23686,
`t3/research-inventory-screen` 4a8a78a, and
`t3/research-campaign-combat` 328b072. Their `docs/spec/combat.md`,
`docs/spec/game-messages.md`, and `docs/issues/kill-loot-xp.md` supply the
models, message structure, and earlier runtime observations used here.
