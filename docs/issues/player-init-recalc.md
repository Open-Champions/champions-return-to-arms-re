# What a new character's record holds: `player_initNewCharacter` and the first recalc

**Executed** with `tools/difftest_player_init.py` (60 cases: 12 models × class start
statistics and four caller-supplied sets). The function runs with every callee real; the
single stub is `SkillNaturalResistance_getStat0Fraction` 0x308a7c (armour only), and only in
the follow-up recalc.

## Signature (from the entry code 0x1b1d70–0x1b1de8)

`player_initNewCharacter(slot, model, name, a, b, c, d, statBytes, kind, …)`: `a`–`d` (a3,
t0–t2) are the four appearance bytes stored at record +0x20 (−1 = none), `statBytes` (t3)
is a pointer to four signed bytes copied to +0x78, or null to copy the class row of
0x4ef400 (0x1b22d8–0x1b2374), and the stack word at +0x60 is the character kind
(`docs/player.md` +0x4c18).

## After init alone

| Field | Value | How |
|---|---|---|
| everything | zero | memset 0x3b60c0 of 0x4c30 bytes at 0x1b1dfc |
| experience +0x5c | 0 | nothing stores it afterwards |
| level +0x59, acknowledged +0x58 | 1, 1 | stored by init |
| gold +0xe4 | 500 | stored by init |
| base statistics +0x78 | the caller's bytes, else the class row | 0x1b22d8 / 0x1b2308 |
| effective statistics +0x90 | = base | the copy loop at the top of `player_recalcStats` (0x1b64b0), which runs for every slot below `g_numPlayers` before the object test (set to 1 here) |
| maximum hit points +0xb0 | **0.0** | never written (the record was zeroed) |
| maximum mana +0xc4 | **10.0** | stored at 0x1b20a0 |
| hit points +0xac, mana +0xc0 | **0x4e6e6b27** (about 1.0e9) | stored at 0x1b23e8, 0x1b23ec |
| player object +0x43d8 | null | the object does not exist yet |
| items | bag counts 1–3 / 3 / 3, 4 pieces equipped | `player_giveStartingItems` 0x1b2400 |

`player_recalcStats` is called from init at 0x1b23f8 (before the starting items), but it
skips the maxima for a slot whose object pointer is null (0x1b64d4; the same contract
`tools/ref_combat.py` `recalc_stats` documents). So init alone leaves max HP 0 and max
mana 10.

## First recalc with the object present

With a placeholder object pointer the recalc runs the whole path. For all 60 cases:

- effective statistics equal base: the starting gear carries no statistic modifier 7–10
  (and so no figurine bonus from `player_recalcArmor`: it feeds the same block);
- maximum HP and mana equal `ref_combat` formula (docs/data-tables.md 4.3) bit for bit at
  level 1 on the effective statistics;
- the 1.0e9 current values are trimmed to the maxima (0x1b6a30–0x1b6a48).

This matches `docs/issues/live-rig.md` 4b: a created class-6 character in the first
level read hit points 32.8 / 32.8 and mana 36.7 with statistics 46, 37, 24, 28.

## What this does not establish

Which caller performs the first object-present recalc in play (not traced here). The object
placeholder is zeroed memory, so everything that reads object fields (armour bonus bytes,
resistances) is outside this note.
