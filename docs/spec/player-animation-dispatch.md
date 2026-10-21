# Player animation dispatch

2026-10-17, round 3 of the animation research; SLUS-20973 US v2.00; branch
`t3/research-anim`. Companion of [creature-animation-dispatch](creature-animation-dispatch.md)
(section 6 there summarises this file). Machine-readable rows: `ref_creature_dispatch.PLAYER_*`.

How `Player_run` 0x1a5030 and its helpers choose which clip a player plays, when, with
which blend times and flags, and which animation event bits they consume. Builds on
`docs/spec/player-tick.md` (cited as PT §n), `docs/spec/animation.md` (AN §n) and
`docs/player.md`. Marks: **O** Observed (read at the address given), **I** Inferred,
**U** Unknown, **X** Executed (run in `tools/ee_emu.py`; the run is named). Nothing here
was run on a console or on the live rig.

Conventions: `P` player object, `R` = `g_players + slot*0x4c30`, `cls` = `R+0x4a86`,
`def` = `*(P+0x24)`, `anim(k)` = `*(def + cls*0x68 + k)`. Call notation `fn(blendIn[,
blendOut], clip, flags)`. Track cells start at `P+0x11c` (stride 0x20): cell +8 weight,
+0xc weight rate, +0x10 life, +0x14 life rate, +0x18 time, +0x1c flags (AN §2.1). Note PT §0
labels +8 "the value compared with 1.0 / 10.0" and +0x10 "weight"; by AN §2.1 those are
weight and life respectively, and that reading is used here (**I**, offsets agree).
"Top" = cell `count−1`; `top+0x10 = P + count*0x20 + 0x10c`, `top+0x14 = … + 0x110`.

## 1. Clip table layout and weapon classes

### 1.1 The table is the class definition

| Fact | Mark | Evidence |
|---|---|---|
| `Player_ctor` passes `(&0x4ef330)[R+0x54]` (model index 0–11) as the class definition to the Creature constructor; `P+0x24` is that definition | O / I (store done by the base ctor / `obj_setClassDef`) | 0x1a1d28 head; docs/objects.md `+0x24` |
| Definition layout: `+0` lump name, `+4` generation, then 8-byte entries `{name ptr, resolved clip ptr}` at `+8+8n`, ended by a null name; resolved once per level generation by `res_find(lump, name)` | O | `obj_setClassDef` 0x14f5f0 loop 0x14f630–0x14f660 |
| So the clip of entry *n* is at `def + 0xc + 8n`, its name at `def + 8 + 8n`. `anim(k)` = entry `13*cls + (k−0xc)/8`; the name of the same entry is at `k−4` | O (arithmetic of the two above) | `Player_hasAnim` callers pass names at 0x80/0x98/0xa0 (0x1a6120, 0x1a6138, 0x1a6164) |
| All 12 player definitions (0x4ecc58 bm `ragnar2.lmp`, 0x4ec8d0 bf `sonya2.lmp`, 0x4ee188 wem, 0x4ede00 wef, 0x4eda78 hem, 0x4ed6f0 hef, 0x4ee898 em, 0x4ee510 ef, 0x4ecfe0 dem, 0x4ed368 def, 0x4eec20 vm `vashir.lmp`, 0x4eefa8 im `iksar.lmp`) have exactly 111 entries: 7 header entries, then **8 rows × 13 entries**, one row per weapon class. The stride 0x68 = 13 entries × 8 bytes | O | ELF data at those addresses (model names at 0x4ebbb8) |
| Row `cls` occupies `k` = 0x44 … 0xa4 (slot `j = (k−0x44)/8`, 0..12) | O | same |

### 1.2 Row slots (roles from the clip names of model 0 and from the code that uses them)

| j | k | bm name, class 0 | Used by | Role |
|---|---|---|---|---|
| 0 | 0x44 | `ohw_idlea` | cell 0 by `player_resetIdleAnim`; slot 27 arg 0 | idle (base layer) |
| 1 | 0x4c | `ohw_walk` | cell 1; slot 27 arg 1; ctor writes footstep events | walk |
| 2 | 0x54 | `ohw_jog` | cell 2 | run, layer 1 |
| 3 | 0x5c | `ohw_jog` (same file as j2) | cell 3; ctor writes run-footstep events | run, layer 2 |
| 4 | 0x64 | `ohw_slam` | heavy attack (older id 0x25) | heavy attack |
| 5 | 0x6c | `ohw_jog` (bm/bf/wem/wef), `*_cast` (others) | state 5 all cast paths | cast |
| 6 | 0x74 | `ohw_atakseq1`; bow `b_attacka`; class 6 `throw` | first melee swing, ranged shot / throw | attack 1 / shot |
| 7 | 0x7c | `ohw_hitreaction` | stagger and flinch | hit reaction |
| 8 | 0x84 | `ohw_block` | state 8 | block (raise/hold) |
| 9 | 0x8c | `ohw_blockhit` | `Player_takeDamage` while blocking | block reaction B |
| 10 | 0x94 | `ohw_blockop` | `Player_takeDamage` while blocking | block reaction A |
| 11 | 0x9c | `ohw_blockgo` | state 8 (paused layer) | block pose |
| 12 | 0xa4 | `ohw_evade` | `Player_tryBlockMove` → state 0xb | block move / evade |

Header entries (class-independent): e0 `def+0xc` `nw_death` (death), e1 `def+0x14`
`dha_death` (death with class 2; `silent.vag` in models 2, 3, 6, 7, which the code never
plays because it excludes those models, 0x1b3460–0x1b34ac), e2 `def+0x1c` `silent.vag`,
e3–e6 `def+0x24…0x3c` `nw_walk` (e3 is used by slot 27 in no-combat levels, 0x1b5df8).
**O**.

Per-model differences (**O**, ELF data): rows the race cannot use are filled with
`ohw_idlea` (or `dha_*` for im); `slam` (j4) exists only for bm/bf (others: `jog`/`walk`);
`*_cast` (j5) exists for hem/hef/em/ef/dem/def/vm/im, not bm/bf/wem/wef; im uses the
spellings `hitreact`, `blok*`. The bow row has no block clips (`b_idlea` in j8–j12;
`b_hitreaction` for dem/def) — consistent with `player_canBlock` refusing a bow (PT §9.2).

### 1.3 Weapon classes (`R+0x4a86`)

| cls | Row prefix | Meaning (I, from names and `player.md`) | Special handling |
|---|---|---|---|
| 0 | `ohw_` | one-hand weapon | combo len 7 |
| 1 | `dhs_` | two-hand, kind 1 (sword?) | combo len 7, target box 58 |
| 2 | `dha_` | two-hand, kind 2 (axe?) | combo len 4, sweep hit; death uses e1 `dha_death` |
| 3 | `l_` | long weapon | combo len 9, target box 58 |
| 4 | `b_` | bow | state 0 shot; no block; next swing `b_attackb` |
| 5 | `nw_` | no weapon (unarmed) | combo len 2; block clips are the `ohw_` ones |
| 6 | `ohw_` row, `throw` in j6 | thrown weapon | state 0 throw; next swing `nw_atakseq3` |
| 7 | `dw_` | dual wield | combo len 7; window 17.616 |

How it is set (**O**, `inventory_equipItem` 0x1c27c0): equipping an item whose hand class
(def +0x1d) is 0 and slot (+0x1c) is not 8 copies def +0x1e into `cls` (0x1c2ad4); a
second one-hand weapon in the main-hand slot with passive 0x40000 > 0 sets 7 (0x1c2b64);
removing the two-hander when a shield goes on sets 5 (0x1c2c18), removing the second weapon
sets 0 (0x1c2c38); new character 5 (0x1b21b8); other writers 0x1bd98c (copy from a
buffer), 0x1c1de8, 0x1c2450, 0x1c3020 (5), 0x1c33d4 (0); net message `invmsg_dispatch`
case 5. Every equip path except ammunition (slot 8) then calls `player_resetIdleAnim`
(0x1c2b80, 0x1c2c40).

## 2. State → clip dispatch

Blend raw: 0x3dcccccc = 0.1 s, 0x3e4ccccc = 0.2, 0x3e999999 = 0.3, 0x3f000000 = 0.5.
"BIO" = `anim_startBlendInOut`, "start" = `anim_start`. Flag meanings in §2.1.

| State | k / clip | Fn | In / out (raw) | Flags | When / choice rule | Evidence | Mark |
|---|---|---|---|---|---|---|---|
| 0 ranged | 0x74 (`b_attacka`, `throw`) | BIO | 3dcccccc / 3dcccccc | 0x12 | entered from state 2 with cls 4/6 (PT §6 state 2 B.4); `tracks 1..` weight & life zeroed first; leaves when flag 0x10 is gone and `P+0x48c*60 ≤ since` | 0x1a7f54, 0x1a7f7c; leave PT state 0 step 4 | O |
| 0 (scripted) | 0x44 idle, or `def+0x24` if level flag 0x10000000 | start | 3e999999 | 0x3 | Player slot 27 arg 0; state := 0 | 0x1b5df4, 0x1b5e24 | O |
| 1 melee, first swing | 0x74 (`*_atakseq1`) | BIO | 3dcccccc / 3dcccccc | 0x802 | attack in state 2, cls ∉ {4,6}; `+0x461=1`, `+0x460=0`, `+0x470=1.6 s` | 0x1a7fb8 → 0x1a7f7c | O |
| 1 heavy | 0x64 (`*_slam`) | BIO | 3dcccccc / 3dcccccc | 0x812 | older id 0x25, `+0x44c==0`, `count<6`; `+0x470=0.857` | 0x1a7308 | O |
| 1 bow melee | `b_attackb` by name | BIO | 3dcccccc / 3dcccccc | 0x802 | cls 4, target within 60 (own draw ≤ 0.1 or no ammo); `+0x470=0.9` | 0x1a79fc | O |
| 1 thrown melee | `nw_atakseq3` by name | BIO | 3dcccccc / 3dcccccc | 0x802 | cls 6, same test | 0x1a7a48 | O |
| 1 combo step | `<prefix>_atakseq%d` with `%d = +0x461` (cls 0,5,2,1,3,7); `b_attackb` (4); `nw_atakseq3` (6) | start | 3dcccccc | 0x802 | combo window passed (PT state 1 step 9); variant from `Player_pickAttackAnim` (§3.4); cls 4/6 only after 39.6 frames with a target; `+0x470 = 1.6` (0.9 bow) | 0x1aacdc, 0x1aae5c, 0x1aaf00 | O |
| 1 (scripted) | 0x4c walk | start | 3dcccccc | 0x3 | slot 27 arg 1 (not when already 1); then `anim_syncToSimFrame`; `Creature_clearPath`, `P+0xb8=80` | 0x1b5e78, 0x1b5e80 | O |
| 1 end | — | cells 4.. life 1.0, life rate 0xbdaaaaaa | — | — | end of swing → state 2 | PT state 1 step 10 | O |
| 2 neutral | cells 0–3 = 0x44/0x4c/0x54/0x5c | direct stores | — | 0x1205 each | `player_resetIdleAnim`; weights each tick by `Player_move` mode 0 (§3) | 0x1b2470 | O |
| 2 bow aim hold | — | cells 1.. weight rate 0xbdeeeeee; step 1.0; move 1 | — | — | cls 4, both buttons < 0.13 | PT state 2 B.4 | O |
| 3 stagger | 0x7c | BIO | 3dcccccc / 3dcccccc | 0xa | knock level ≥ 1 and "small" (§3.5); not when damage flag 0x400000. With ≥5 tracks the top track first gets life ≤1, life rate 0xbdaaaaaa | 0x1b2ed8 (state), 0x1b317c | O |
| 3 knockdown | `knockdown1_` / `knockdown2_` (cls 2,3) + `a`/`b`/`c`/`d` + `.anm`, by name | BIO | 3dcccccc / 3dcccccc | 0x80a | knock level large and not resisted; skipped if already playing; resisted → `0x308578` (StrongStance phantom) real only, no state change | 0x1b2f40–0x1b30bc, 0x1b301c | O |
| 3 flinch | 0x7c | BIO | 3dcccccc / 3dcccccc | 0xa | damage taken, alive, no 0x400000, state ∉ {3,7,6,10}, `+0x44c≠2`, shared draw < (0.04 − R+0xdc×0.04)×65536 or damage flag 0x4000000 | 0x1b380c (state), 0x1b38d0 | O |
| 3 leave | — | — | — | — | flag 8 gone → state 2 | PT states 3 | O |
| 4 death | `def+0x14` (`dha_death`) if model ∉{2,3,6,7} and cls==2, else `def+0xc` (`nw_death`) | start | 3f000000 | 0x206 | hp ≤ 0 after a spell check; object flags 8 and 1 | 0x1b34c0, 0x1b34e0, 0x1b34fc | O |
| 5 cast (Skill object) | 0x6c | start | 3dcccccc | 0x8003 | phase 0, no 0x8000 track, skill kind ≠ 6; phase 1 fires at weight ≥ 1.0 (0.5 net); kind 0: life ≤1, life rate 0xbd6eeeee; leave when flag 0x8000 gone | 0x1ab760, 0x1ab784 | O |
| 5 older kind 1 / 2 | 0x6c | start | 3dcccccc | 0x8003 | phase 0; kind 2 ends at top weight ≥ 10.0; top life rate 0xbd6eeeee on end | 0x1aba80, 0x1abca0 | O |
| 5 older kind 0 | 0x6c | BIO | 3dcccccc / 3dcccccc | 0x8022 | phase 0; effect at top weight ≥ 1.0; leave when flag 0x20 gone | 0x1abf64, 0x1abf8c | O |
| 5 end (`Player_updateCast`) | — | 0x8000 track capped and faded | — | — | button released / not state 5 / mana ≤ 0 | PT §9.11 | O |
| 6, 0xe | none in `Player_run` | — | — | — | skill code drives the clip (§6) | 0x1a6a28 | O |
| 7 jump | none started here | — | — | — | impulse when top track time ≥ 4.02; on landing `Player_move` sets top life rate 0xbd6eeeee | 0x1a5f98; 0x1b5150–0x1b5170 | O |
| 8 block | 0x9c (`blockgo`) | start | 3dcccccc | 0x2801 | whenever no `blockgo` track | 0x1a6164, 0x1a61b4 | O |
| 8 block | 0x84 (`block`) | start | 3dcccccc | 0x803 | block held and (`+0x47f==0` or neither `evade` nor `block` playing, tested before the step) | 0x1a6120, 0x1a6138, 0x1a6244 | O |
| 8 hit while blocking | 0x94 (`blockop`) | BIO | 3e4ccccc / 3e4ccccc | 0x812 | `Player_takeDamage` 0x1b5330: hit immunity `R+0x4c27` = 0, a non-null argument in s2 (the attacker, **I**), state 8 (state 0xb plays nothing), damage-flag bit 0x40 clear: one shared draw ≤ 0xafc7 (≈ 68.7 %); copy test not checked | 0x1b548c–0x1b5508 | O |
| 8 hit while blocking | 0x8c (`blockhit`) | BIO | 3dcccccc / 3dcccccc | 0x812 | same, draw > 0xafc7 | 0x1b5538 | O |
| 8 release | — | top and below: life rate 0xbdaaaaaa | — | — | released, top weight ≥ 1, count < 7 | PT state 8 | O |
| 9 rush | cell 3 (0x5c run layer 2) | direct stores | rate 0.1/tick | — | every tick: cell 3 weight rate 0.1, life 1.0, life rate 0; step 2.0 | 0x1a6bf0 | O (offsets) / I (that it is "the run clip at double speed") |
| 10 ground pound | `dha_quake` by name | BIO | 3dcccccc / 3dcccccc | 0xa | older id 0xc (0x1a7448), or `SkillGroundPound_cast` on a flag-0x40 object (0x2c72a8, which also writes the event slots); leave when flag 8 gone (top life 1.0, rate 0xbdaaaaaa) | 0x1a7448, 0x2c7224–0x2c72a8 | O |
| 0xb block move | 0xa4 (`evade`) | BIO | 3dcccccc / 3e999999 | 0x808 | swap pressed while blocking; `+0x481 = 47` | 0x1bf218 | O |
| 0xb leave | — | released: top and below life rate 0xbdaaaaaa | — | — | flag 8 gone → 8 (held) or 2 | PT state 0xb | O |
| 0xc war cry | `<prefix>_warcry` by name: cls 0 ohw, 5 nw, 2 dha, 1 dhs, 3 l, 7 dw; **cls 4/6: the stack buffer is never written** | BIO | 3dcccccc / 3dcccccc | 0x22 | older id 0xe, `P+0x374==0`; `P+0x374=0x30c`; leave when flag 0x20 gone | 0x1a70c0–0x1a71b4 | O |
| (war cry, spell) | `ohw_warcry` on a class-0 caster; cls 4/6 not re-run | BIO | 3dcccccc / 3dcccccc | 0x22 | `SpellAncestralCall_ctor`; state becomes 6 at 0x2e0c58, after this blend | 0x2e0a6c–0x2e0c58 | O / X (§6) |
| 0xd riding | `nw_seated` if the lump has it, else `nw_idlea` (by name) | start | 3dcccccc | 0x3 | when no `nw_seated` track and level name ≠ `bronzeht` | 0x1a5f10–0x1a5f78 | O |
| fidget (state 2) | `<prefix>_idled` (cls 1 dhs, 2 dha, 3 l, 4 b, 5 nw, 7 dw, else ohw) by name, lump of the record's object | start | 3f000000 | 0x1 | §3.3 | 0x1bc508, 0x1bc540 | O |
| any (`Player_setNeutral`) | — | top life 1.0, life rate 0xbdaaaaaa; state 2 | — | — | helper | 0x1bebb8 | O |

### 2.1 Flag bits as the player uses them

| Bit | Engine meaning (AN §2.1) | Player use | Mark |
|---|---|---|---|
| 0x0001 LOOP | wrap | base layers, cast, block, riding, fidget, slot 27 | O |
| 0x0002 PURGE_BELOW | delete non-persistent tracks below at full weight; ends the step loop | every action clip; the four base layers are PERSISTENT so they survive but are **frozen** while such a track sits above at full weight (AN §5 note 1) | O / I (consequence) |
| 0x0004 REPORT_END | hold at end | death (0x206); base layers carry it but LOOP wins | O |
| 0x0008 | not tested by the engine | "wait for this clip" marker of states 3, 10 and 0xb (stagger 0xa, knockdown 0x80a, quake 0xa, evade 0x808) | O |
| 0x0010 | not tested by the engine | marker state 0 waits on (shot 0x12); also carried by heavy attack and block reactions (0x812) — so a heavy attack or block reaction still running delays a later state-0 exit | O / I |
| 0x0020 TALK | cutscene marker | marker of states 0xc and 5 older kind 0 (0x22, 0x8022); the Ancestral Call spell also sets it | O |
| 0x0200 KEEP | not removed at life ≤ 0 | base layers (life 0 on cells 1–3) and death | O |
| 0x0800 ROOT | root motion | attacks, block, evade, knockdown, block reactions, blockgo | O |
| 0x1000 PERSISTENT | survives purge | base layers only | O |
| 0x2000 PAUSED | time frozen | `blockgo` pose layer | O |
| 0x4000 YAW | root yaw | never used by player code (AN §9) | O |
| 0x8000 | not tested by the engine | cast marker: `anim_findTrackByFlag(…, 0x8000)` in state 5 and `Player_updateCast`; state 5 phase 2 leaves when it is gone | O |

Markers are read from `P+0x11a`, the union of the flags of the tracks *visited* by the
last step (AN §2.1): a marked track sitting under a full-weight PURGE_BELOW track is not
visited, so its marker drops out early (**I**).

## 3. Movement, idle reset, fidget, choices

### 3.1 `player_resetIdleAnim` 0x1b2470 (slot) — **O**

Returns when the record has no object or hp ≤ 0. Writes the four base cells directly (no
start function), then `count = 4` and `anim_releaseCaches`:

| Cell | Clip | weight | life | flags | Not written |
|---|---|---|---|---|---|
| 0 | `anim(0x44)`; display-only player (`+0x462`): `dhs_/dha_/l_/b_/dw_idled` for cls 1/2/3/4/7, else `ohw_idled` (cls 5 included, unlike the fidget), by name in the lump of `R+0x43d8`'s definition (0x1b24e8–0x1b25ac) | 1.0 | 1.0 | 0x1205 | time, rates, slot |
| 1 | `anim(0x4c)` | 0 | 0 | 0x1205 | time, rates |
| 2 | `anim(0x54)` | 0 | 0 | 0x1205 | time, rates |
| 3 | `anim(0x5c)` | 0 | 0 | 0x1205 | time, rates |
| 4 | — | 0 | 0 | — | — |

0x1205 = PERSISTENT | KEEP | REPORT_END | LOOP. Called by `Player_ctor` right after
`anim_clear` (0x1a2330–0x1a2338), every equip (§1.3), and 9 more sites.

### 3.2 `Player_move` mode 0 locomotion blend (0x1b479c–0x1b4a3c) — **O**

`s` = stick length × speed scale, capped at the scale (0x1b41c4–0x1b420c; scale 0.861945
offline, 0.75 in a net game, × `R+0x4c20` × 0x4f8418, ≤ 1.2, × Drowsy). Then:

1. Playback rate `r`: `s < 0.43` → `s × 2.3255813` (0x4014d653); `s < 0.7` →
   `(s − 0.43) × 3.7037034 × 0.3499999 + 1.0`; else `(s − 0.7) × 3.333333 × 0.15000009 +
   1.35` (0x406d097a, 0x3eb33330, 0x40555554, 0x3e1999a0, 0x3faccccc).
2. Blend `B = P+0x46c`: `r > 0.01` → `B += 0.1`; above 1.0 it is set to 1.0 **and cell 0's
   time is set to 0** (0x1b4884, so the idle restarts from 0 after moving); else `B −= 0.1`,
   floored at 0.
3. Step: `r < 0.01` and `B < 0.05` → `Player_animStep(P, 1.0)`, result discarded, return
   value 0 (0x1b48e8). Otherwise `e = Player_animStep(P, r)`; return `e & 4` when
   `s ≥ 0.6`, else `e & 1` (0x1b48f8–0x1b4950).
4. Acceleration limit: `s = min(s, P+0x468 + 0.05)` (0x1b4954–0x1b497c).
5. Weights (weight and life both): cell 1 = `B`; cell 2 = `float(B × (s − 0.45) × 3.0)`;
   cell 3 = `float(B × (s − 0.7) × 3.0)`, in software double (0x3af468 subtract, 0x3af4d0
   multiply, 0x3afb90 to float; constants 0x5376b0 = 0.45, 0x5376b8 = 0.7, 3.0 built at
   0x1b4984). `P+0x468 = s`. Negative results blend as 0.
6. Modes 1, 4, 6 instead zero the velocity, `B`, and weight and life of cells 1–3, and do
   not step (0x1b4b90–0x1b4bd0). Modes 2, 3, 5 neither step nor touch the cells.

Consequences (**I**, arithmetic): standing still idles at speed 1; while stopping (`r` ≈ 0,
`B` falling over ≤ 10 ticks) the whole state is stepped at the tiny rate `r`; at the net
cap `s = 0.75` (multipliers 1.0) run layer 1 reaches 0.9·B, layer 2 0.15·B and `r = 1.375`;
offline at 0.861945, 1.236·B, 0.486·B and `r = 1.431`.

### 3.3 `Player_idleFidget` 0x1bc2f8 — **O** (PT §9.1 has the draw)

Stick > 0.01 with `+0x463` set: clear it; cells 4.. get life 1.0, life rate 0xbdaaaaaa
(0.2 s fade). Else with exactly 4 tracks: one shared draw; `< 0xe2` and no fidget running →
`anim_start(0.5, res_find(lump of R+0x43d8's def, "<prefix>_idled.anm"), 1)`, `+0x463 = 1`.
The fidget loops until the stick moves or an action clears the tracks. Because the draw
depends on the track count, animation state is lockstep state (**I**).

### 3.4 `Player_pickAttackAnim` 0x1bba88 — **X** (unrecorded script)

Run: an ad-hoc `tools/ee_emu.py` script, **not kept in the repository** (so this table is
Executed once but not reproducible from a named test; `docs/spec/player-tick.md` 9.10 has the
recorded model comparison of the same function), called 0x1bba88 for every model
0–11 × class 0–7 × old variant 0–7 × the 12 hash intervals the code compares against
(9,216 calls, callees auto-stubbed, `net_isLocalSlot` stubbed to 0). `h` = low 16 bits of
`g_simFrame × 0x19660d + 0x3c6ef35f` (the shared seed is advanced but unused; PT §9.10).
Notation `{a; b@x; c@y}` = `a` for `h < x`, `b` for `x ≤ h < y`, `c` above.

| Models | cls | old → new |
|---|---|---|
| all but 9, 11 | 0 | 1→{2; 4@7fff}, 2→{1; 3@5555; 5@aaaa}, 3→{2; 4@7fff}, 4→{1; 3@5555; 5@aaaa}, 0/5/6/7→{2; 4@bb80} |
| all but 9, 11 | 1, 5 | 1→2, 2→{1; 3@7fff}, 3→2, others unchanged |
| all but 11 | 2, 3 | 1→{2; 4@7fff}, 2→{1; 3@7fff}, 3→{2; 4@7fff}, 4→{1; 3@7fff}, others unchanged |
| all | 4, 6 | unchanged (names do not use it) |
| all | 7 | 1→2, everything else →1 |
| 9 (def) | 0 | 1→{2; 3@5555; 5@aaaa}, 2→{1; 3@7fff}, 3→4, 4→{2; 5@7fff}, 5→{4; 3@5555; 1@aaaa}, 0/6/7 unchanged |
| 9 | 5 | 1→2, 2→3, 3→1 |
| 11 (im) | 0 | 0/5/6/7→{1; 3@7fff}, 1→{2; 4@7000; 5@e000}, 2→{3; 1@6aa8; 5@d334}, 3→{4; 2@7000; 5@e000}, 4→{5; 1@53ed; 3@aaaa} |
| 11 | 1 | as general |
| 11 | 2 | as general except 3→{2; 4@bb80} |
| 11 | 5 | 0/1/5/6/7→{2; 4@7fff}, 2→{1; 3@6d60; 4@dac0}, 3→{2; 4@bb80}, 4→{2; 3@7fff} |

Every swing starts at variant 1 (`atakseq1`, state 2 sets `+0x461 = 1`).

### 3.5 Hit, stagger, knockdown, death — `Player_processDamage` 0x1b2cc0 — **O**

1. Knock level from damage flags `P+0x2dc` (skipped in states 6, 10): 0x40000 → 1 (dist
   100), 0x80000 → 2 (150), 0x100000 → 3 (200), 0x200000 → 3 (250); one shared draw `% 100 <
   resist` (resist from skill 0x3e through 0x30851c) = "resisted". PvP mode A: level − 1,
   distance halved.
2. `rel = (s16)(P+0x2e0 − facing)` (hit angle). "Small" = `level < 2`, except in state 8
   with `|rel| ≥ 0x6000`, where `level − 1 < 2`.
3. Small, or not resisted: state 3, `+0x448 = frame`, `player_voice(slot, 0xc)`, rebase
   request for a local slot. Small: stagger clip (table row "3 stagger"). Large: knockdown
   name `knockdown2_` for cls 2/3 else `knockdown1_`, suffix `a` for `|rel| ≥ 0x6000`, `c`
   for `−0x6000 < rel ≤ −0x2000`, `b` for `−0x2000 < rel ≤ 0x2000`, `d` otherwise.
4. Then damage; dead → death clip (state 4); alive → flinch roll (row "3 flinch").

## 4. Event bits consumed

Event slots are written by code (AN §7.3). Writers found (**O**):

| Clip | Slots `{seconds, mask}` | Writer |
|---|---|---|
| `anim(0x4c)` walk, rows 0–5 | {0.25, 1}, {0.75, 1} | `Player_ctor` 0x1a2388–0x1a241c |
| `anim(0x5c)` run layer 2, rows 0–5 (same clip as 0x54) | {0.45, 4}, {0.95, 4} | same |
| `anim(0xa4)` evade, rows 0–5 | {0.25, 1}, {0.75, 1} | same |
| `dha_quake` | {0.25, 1}, {0.5, 2}, {0.75, 4}, {1.4779719, 8} | `SkillGroundPound_cast` 0x2c723c–0x2c72ac |

The ctor loop runs 6 times (counter 5 → −1, 0x1a2380/0x1a2418): row 7 (`dw_`) gets no
events (**O**); row 6 shares row 0's clips (**I**: same names resolve to the same clip). Where
a row reuses one file in several slots (bow j12 = `b_idlea` = idle; wem/wef rows 1–3 all
`ohw_idlea`) the idle clip receives footstep events too (**I**).

| State | Mask | Effect | Evidence | Mark |
|---|---|---|---|---|
| 2 | `move(0)` return & 5 (1 walk below s 0.6, 4 run from 0.6) | `Player_footstep` | 0x1b48f8–0x1b4950; PT state 2 B.5 | O |
| 0xb | step & 5 | `Player_footstep` | 0x1a6588 on | O |
| scripted 1 (`+0x231`) | step & 1 | `Player_footstep`, then `Creature_moveToDest` | 0x1a55a4–0x1a5610 | O |
| 10 | 1 | `player_voice(slot, 10)` + sound `spel_bw_pound.anm` (copy too) | 0x1a6824–0x1a685c | O |
| 10 | 1 / 2 / 4 (real only) | `world_damageInRadius` 24 units from P at facing −0x4000 / 0 / +0x4000, z + 60 | 0x1a6818 on | O |
| 10 | 8 (real only) | `GroundPoundEffect` (rank of skill 0x26) | 0x1a69bc region | O |
| all others | none | melee hit, arrow/throw release, cast release and swing sounds are **frame or weight counts**, not events (PT states 0, 1, 5) | PT §6 | O |

Not events but timing anchors: melee hit `since == trunc(16.02/speed)` offline; release
`since == trunc(base/speed)`; cast at cast-track weight ≥ 1.0 (start rate `1/(0.1×60)`, so
≈ 6 ticks, **I**); older kind 2 at top weight ≥ 10.0 (≈ 60 ticks, **I**); state 7 impulse
at top time ≥ 4.02.

## 5. Net-game differences relevant to animation (all **O** unless marked)

| Item | Offline | Net game | Evidence |
|---|---|---|---|
| melee hit | `t == trunc(16.02/speed)` | `t == 1` and `P+0x55c == 0` (16 after block) | 0x1aa6ec–0x1aa738 |
| ranged release | base 22 / 11 frames | 11 / 5 | 0x1a80e0 |
| cast point (weight) | 1.0 | 0.5 (≈3 ticks, **I**) | 0x1ab7b8 |
| move mode in states 0, 5 | 1 | 6 (same effect on the locomotion cells) | PT §6; 0x1b4b90 |
| speed cap → blend | 0.861945 | 0.75 (§3.2 consequences, **I**) | 0x1b4108–0x1b4148 |
| clip sound events | played | not for the machine's own real player (no sound position) | `Player_animStep`; player.md |
| swing sound / shout t = 6, 9 | always | only non-local slot or the copy | 0x1aa6f4 |
| state 3 / 4 entry | — | local slot sets `g_forceGhostRebase` | 0x1b2ee0, processDamage death tail |

## 6. Skill-driven states 6, 7, 9 and 0xe

2026-10-20. `Player_run` starts no clip for states 6 and 0xe (0x1a6a28). State 9 only
rewrites locomotion cell 3 (0x1a6bf0, section 2). The clips below come from the skill
constructors. Each constructor was called in `tools/ee_emu.py` on a zeroed player with
object flag 0x40, weapon class reading as 0, and every callee stubbed. The soft-float
band was not followed: following it never reaches the state store. Weapon classes 4 and
6 were not varied, so a class-0 name (`ohw_`, `bash`, `cyclone1`) is what ran. Rows:
`ref_skill_anim`. Re-run: `difftest_skill_anim.py`.

### 6.1 State 6

All seven store action state 6 and start one clip. Blends are raw32 0x3dcccccc (0.1 s)
where a blend is passed. A name in the last column is looked up and is not a second
player clip.

| Constructor | State store | Clip and call | Flags | Also looked up |
|---|---|---|---|---|
| `SkillCyclone_cast` 0x2d17c8 | 0x2d18f8 | `cyclone1.anm`, `anim_push` 0x2d1980 | 0x23 | `spel_bw_cyclone.anm` at 0x2d19f0 |
| `SpellBash_ctor` 0x2de640 | 0x2de6c4 | `bash.anm`, blend 0x2de6ec | 0x812 | — |
| `SpellAncestralCall_ctor` 0x2e09b4 | 0x2e0c58, after the blend | `ohw_warcry.anm`, blend 0x2e0b6c | 0x22 | `spel_bw_ancestral.anm` at 0x2e0a38 |
| `SpellShieldBash_ctor` 0x2face4 | 0x2fad68 | `bash.anm`, blend 0x2fad90 | 0x812 | — |
| roar 0x30016c | 0x300204 | `ohw_roar.anm`, blend 0x300374 | 0x22 | `spel_vb_roar.anm` at 0x300388 |
| battle cry 0x301714 | 0x3017e0 | `ohw_battlecry.anm`, blend 0x301944 | 0x22 | `spel_vb_battlecry.anm` at 0x301958 |
| blood lust 0x303254 | 0x303318 | `ohw_bloodlust.anm`, blend 0x30344c | 0x822 | — |

`SpellAncestralCall_ctor` does store state 6. The blend itself is the range
0x2e0a6c–0x2e0b6c; the store is the later instruction. On this player the war-cry name
is the class-0 `ohw_warcry`. The same scan of `+0x58c` shows a constant 2 near each of
these stores (0x2d1bf8, 0x2ded6c, 0x2e0df4, 0x2fb41c, 0x300540, 0x301bc4, 0x303660).
Those leave stores were not executed this round. `docs/player.md` already reads them as
the return to state 2.

### 6.2 State 9

`SkillCharge_cast` 0x2c8864 stores 9 at 0x2c88e8 and again at 0x2c88f0 when object flag
0x40 is set. With that flag clear the state stays 0. Neither call starts a clip.
**Executed.** The cell-3 weight rate, life and double step at 0x1a6bf0 stay the
Observed reading in section 2. That address sits inside `Player_run`; calling it as its
own entry did not reproduce the stores, and it was not re-executed as part of `Player_run`.

### 6.3 State 0xe

`SpellShadowStep_ctor` 0x311638 stores 14 at 0x31173c and ORs 0x5 into the object flags
(0x40 becomes 0x45). It looks up `spel_de_shadowstep.anm` at 0x31179c and calls 0x214428
(from 0x3117cc). That helper's `anim_push` at 0x21451c uses flags 0x4 and blend 1.0
(raw32 0x3f800000). The constructor then loops; the run was stopped after the push.
Destructor 0x311da0, on the skill whose constructor had stored the player at skill+0xc,
stores state 2 (the constant at 0x311dfc) and returns the flags to 0x40. **Executed.**

### 6.4 State 7

An executed scan of `.text` found 64 direct stores through offset 0x58c. None is the
immediate 7. The constants include the state-6, state-9 and state-0xe stores above, plus
zeros (0x1a7b54, 0x1a7cec, 0x1b5e00, 0x1b5e30) and the landing store of 2 at 0x1b5168.
0x11f15c copies `+0x58c` from one player to another (load at 0x11f150, store at
0x11f15c). The other unresolved store is 0x1abd10, inside `Player_run`, which writes a
register; nothing in the 48 instructions above it puts 7 there. The addiu of 7 at
0x1a9cfc is stored to the stack (0x1a9d04), not to the player. Who enters state 7 is **Unknown**. The handler that waits until the top
track's time is at least 4.02 (0x1a5f98) is unchanged from section 2.

### 6.5 Still open

| Item | How to settle |
|---|---|
| Who sets state 7, and which clip the 4.02 s wait is measured on | a path that puts 7 in the register stored at 0x1abd10, or a writer outside a direct `+0x58c` store |
| War-cry and roar names for weapon classes 4 and 6 | re-run the constructors with `+0x4a86` set to 4 and 6 |
| Whether all `atakseq1..5`, `knockdown*`, `*_warcry`, `*_idled`, `nw_seated` exist in each lump (a missing name resolves to 0; what `anim_start` does with a null clip was not read) | list the lumps' clip names from a disc; read `anim_start` 0x16cfe0 for a null test |
| What the stale stack buffer holds for the cls 4/6 war cry in `Player_run` | execute 0x1a70b4 with a known stack in `tools/ee_emu.py` |
| Rates, times and slot pointers that `player_resetIdleAnim` leaves stale in cells 0–3 — can a stale cell-0 weight rate drift the idle weight? | execute a sequence (attack, then reset) through `anim_advance` |
| Direction convention of `P+0x2e0` (is `a` the front?) | read the writers in `Creature_takeDamage`-type code (0x116700 …) |
| Whether the prediction copy and the real player can disagree on track count (fidget draw) | difftest over the copy path with real `Player_move` |
| `Player_move` modes 2/3/5 and their relation to cells 1–3 beyond "not touched" | read 0x1b4bd8–0x1b4c30 fully |
| Clip names for the menu model (`inventory_selectIdleAnim` 0x1c3f08) | read it |

## 7. Machine-readable summary (Observed / Executed only)

The same rows are importable as `ref_creature_dispatch.PLAYER_DISPATCH`,
`PLAYER_EVENTS` and `PLAYER_EVENT_SLOTS`.

```python
F01, F02, F03, F05 = 0x3dcccccc, 0x3e4ccccc, 0x3e999999, 0x3f000000
PLAYER_DISPATCH = {
    0: [dict(k=0x74, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x12,
             when='enter state 0 from state 2 (weapon class 4 or 6)', evidence='0x1a7f7c'),
        dict(k=0x44, fn='anim_start', blend_in=F03, blend_out=None, flags=0x3,
             when='Player slot 27 arg 0 (def+0x24 instead when level flag 0x10000000)', evidence='0x1b5e24')],
    1: [dict(k=0x74, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x802,
             when='first swing from state 2', evidence='0x1a7fb8'),
        dict(k=0x64, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x812,
             when='heavy attack, older id 0x25', evidence='0x1a7308'),
        dict(k='b_attackb.anm', fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x802,
             when='class 4 close target', evidence='0x1a79fc'),
        dict(k='nw_atakseq3.anm', fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x802,
             when='class 6 close target', evidence='0x1a7a48'),
        dict(k='<prefix>_atakseq%d.anm (+0x461)', fn='anim_start', blend_in=F01, blend_out=None, flags=0x802,
             when='combo step after Player_pickAttackAnim', evidence='0x1aae5c'),
        dict(k='b_attackb / nw_atakseq3', fn='anim_start', blend_in=F01, blend_out=None, flags=0x802,
             when='combo step, class 4/6, after 39.6 frames with a target', evidence='0x1aaf00'),
        dict(k=0x4c, fn='anim_start', blend_in=F01, blend_out=None, flags=0x3,
             when='Player slot 27 arg 1, unless already state 1', evidence='0x1b5e78')],
    2: [dict(k=(0x44, 0x4c, 0x54, 0x5c), fn='direct_store', blend_in=None, blend_out=None, flags=0x1205,
             when='player_resetIdleAnim: cells 0..3, weights 1,0,0,0', evidence='0x1b2470'),
        dict(k='<prefix>_idled.anm', fn='anim_start', blend_in=F05, blend_out=None, flags=0x1,
             when='Player_idleFidget: 4 tracks, shared draw < 0xe2, no fidget', evidence='0x1bc508')],
    3: [dict(k=0x7c, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0xa,
             when='small knock (level<2, or level-1<2 blocking a |rel|>=0x6000 hit)', evidence='0x1b317c'),
        dict(k='knockdown{1,2}_{a,b,c,d}.anm', fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x80a,
             when='large knock not resisted, not already playing', evidence='0x1b30bc'),
        dict(k=0x7c, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0xa,
             when='flinch roll on damage', evidence='0x1b38d0')],
    4: [dict(k='def+0x14', fn='anim_start', blend_in=F05, blend_out=None, flags=0x206,
             when='death, model not 2/3/6/7 and class 2', evidence='0x1b34c0'),
        dict(k='def+0xc', fn='anim_start', blend_in=F05, blend_out=None, flags=0x206,
             when='death otherwise', evidence='0x1b34e0')],
    5: [dict(k=0x6c, fn='anim_start', blend_in=F01, blend_out=None, flags=0x8003,
             when='Skill-object cast phase 0, no 0x8000 track, skill kind != 6', evidence='0x1ab784'),
        dict(k=0x6c, fn='anim_start', blend_in=F01, blend_out=None, flags=0x8003,
             when='older record kind 1, phase 0', evidence='0x1aba80'),
        dict(k=0x6c, fn='anim_start', blend_in=F01, blend_out=None, flags=0x8003,
             when='older record kind 2, phase 0', evidence='0x1abca0'),
        dict(k=0x6c, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x8022,
             when='older record kind 0, phase 0', evidence='0x1abf8c')],
    8: [dict(k=0x9c, fn='anim_start', blend_in=F01, blend_out=None, flags=0x2801,
             when='no blockgo track', evidence='0x1a61b4'),
        dict(k=0x84, fn='anim_start', blend_in=F01, blend_out=None, flags=0x803,
             when='block held and (+0x47f==0 or neither evade nor block playing)', evidence='0x1a6244'),
        dict(k=0x94, fn='anim_startBlendInOut', blend_in=F02, blend_out=F02, flags=0x812,
             when='Player_takeDamage in state 8, shared draw <= 0xafc7', evidence='0x1b5508'),
        dict(k=0x8c, fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0x812,
             when='Player_takeDamage in state 8, shared draw > 0xafc7', evidence='0x1b5538')],
    10: [dict(k='dha_quake.anm', fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0xa,
              when='older id 0xc', evidence='0x1a7448'),
         dict(k='dha_quake.anm', fn='anim_startBlendInOut', blend_in=F01, blend_out=F01, flags=0xa,
              when='SkillGroundPound_cast, writes the 4 event slots', evidence='0x2c72a8')],
    0xb: [dict(k=0xa4, fn='anim_startBlendInOut', blend_in=F01, blend_out=F03, flags=0x808,
               when='Player_tryBlockMove: swap pressed while blocking', evidence='0x1bf218')],
    0xc: [dict(k='<prefix>_warcry.anm (class 4/6: unwritten buffer)', fn='anim_startBlendInOut',
               blend_in=F01, blend_out=F01, flags=0x22, when='older id 0xe, P+0x374 == 0', evidence='0x1a71b4')],
    0xd: [dict(k='nw_seated.anm or nw_idlea.anm', fn='anim_start', blend_in=F01, blend_out=None, flags=0x3,
               when='no nw_seated track, level name != bronzeht', evidence='0x1a5f78')],
}
PLAYER_EVENTS = {
    2: [(0x5, 'Player_footstep (move(0) returns bit 4 when s >= 0.6, bit 1 below)', 'evidence 0x1b48f8')],
    0xb: [(0x5, 'Player_footstep', 'evidence 0x1a6588')],
    'scripted_1': [(0x1, 'Player_footstep, then Creature_moveToDest', 'evidence 0x1a55a4')],
    10: [(0x1, 'player_voice 10 + sound spel_bw_pound.anm; area damage at facing-0x4000 (real only)', 'evidence 0x1a6824'),
         (0x2, 'area damage ahead, 24 units (real only)', 'evidence 0x1a6818'),
         (0x4, 'area damage at facing+0x4000 (real only)', 'evidence 0x1a6818'),
         (0x8, 'GroundPoundEffect, rank of skill 0x26 (real only)', 'evidence 0x1a69bc')],
}
EVENT_SLOTS = {   # written by code; {seconds raw, mask}
    'anim(0x4c), rows 0-5': [(0x3e800000, 1), (0x3f400000, 1)],          # 0x1a2388
    'anim(0x5c), rows 0-5': [(0x3ee66666, 4), (0x3f733333, 4)],          # 0x1a2388
    'anim(0xa4), rows 0-5': [(0x3e800000, 1), (0x3f400000, 1)],          # 0x1a2388
    'dha_quake.anm': [(0x3e800000, 1), (0x3f000000, 2), (0x3f400000, 4), (0x3fbd2e2f, 8)],  # 0x2c723c
}
```
