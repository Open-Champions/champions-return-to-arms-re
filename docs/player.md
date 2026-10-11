# Player: the Player class and the per-player record

Address range 0x1a0000–0x1c0000 (122 functions). Symbols are in `symbols/player.tsv`.
Everything here was read from the executable; nothing was run when it was written. Since
then `Player_run` has been executed tick by tick in `tools/ee_emu.py`
(`docs/spec/player-tick.md`), and part of this document has been seen on the live game —
offline play from scripted input and one machine in a net game, in the Play! emulator,
which is not a PlayStation 2 and not PCSX2 (`FINDINGS.md`, "Run on the live game", rows
V1–V23; `docs/issues/live-rig.md` 4b–4d). What was seen there: the record fields that were
read back (name, class, statistics and their order, hit points, mana, gold, load limit,
speed multiplier, object pointer, bag 2), the potion buttons and the pending-heal fields,
the run speed offline and in a net game. Where that settles something this document had as
Inferred or open, the place is marked **Ran**. The rest was not re-checked on the live
game, and no test patch has been run on one. Each statement is
**Observed** (read at the address given), **Inferred** or **Unknown**.

## What the area does

Two things live side by side and are easy to confuse:

- The **Player object** — a `Creature` (0x3c8 bytes) extended to 0x590 bytes, created by
  `Player_ctor` (0x1a1d28), one per player in the level. It holds position, animation and
  the short-lived state of whatever the player is doing. It is destroyed and re-made on
  death/respawn and on every level change.
- The **player record** — 0x4c30 bytes per slot in `g_players` (0x4d8af0). It holds the
  character: name, class, statistics, hit points and mana, three item bags, equipment
  pointers, ability records, skill ranks, mission progress. The object finds its record
  through its slot index (object +0x3c8); the record points back at the object (+0x43d8).

`Player_run` (0x1a5030, virtual slot 4) is the per-frame simulation of one player. It runs
once per simulated frame for every real player and, on each machine, extra times on the
prediction copy of that machine's own player (object flag 0x20000). The second half of this
document is the audit of what the copy can change.

The start of the range (0x1a00b0–0x1a1b38) is not player code: floor decals, a menu list
widget and the handle-list node pool. The end of the range (0x1bfbc8 on) belongs to the
inventory user interface.

## The player record (`g_players[slot]`, 0x4c30 bytes)

Offsets are from the start of the record. "init" = `player_initNewCharacter` 0x1b1d70,
"import" = `player_importCharacter` 0x1bd458, "stats" = `player_recalcStats` 0x1b6458.

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | char[0x20] | character name | Observed: init copies the name argument here (string copy 0x3b868c); import copies 0x20 bytes |
| +0x20 | s8[4] | appearance choices (-1 = none); select the model part files | Observed: `Player_ctor` builds four part names from them (0x1a1d28) |
| +0x24 | char[] | name of the level to return to after a recall; default is a 5-byte constant at 0x5375d0 | Observed: init/import copy the constant; `player_recallTick` 0x1b5fa0 stores and reads it |
| +0x44 | Vec3 | position to return to after a recall | Observed: 0x1b5fa0 |
| +0x50 | s32 | class index 0–6, derived from the model index: models 0,1→0; 4,5→1; 8,9→2; 2,3→3; 6,7→4; 10→5; 11→6 | Observed: init. Class 0 loses mana while status counter 2 runs; classes 1 and 4 are the ones the script built-in `isClericOrWizard` accepts (0x1465cc) |
| +0x54 | s32 | character model index 0–11 | Observed: init argument; indexes the model name table 0x4ebbb8 |
| +0x58 | s8 | level the player has acknowledged in the level-up screen (`docs/ui.md`); starts at 1, capped at 50 on import. It, not +0x59, feeds the attack rating at +0xcc | Observed: set from an inventory message in `invmsg_dispatch` 0x1bfdb0, compared with +0x59 by the HUD (0x1d9cd4, 0x1db870), read at 0x1b71b8. The earlier version gave the meaning as Unknown |
| +0x59 | s8 | character level used by the hp/mana formulas | Observed: stats |
| +0x5c | s32 | experience; import clamps it to the limit at 0x41b620 | Observed: import |
| +0x78 | s32[4] | base statistics. Index 0 feeds the load limit, 1 max mana, 3 max hp, so they are strength, intelligence, dexterity, stamina. The earlier version gave the order as Inferred from those uses; it is **Ran** now: a new character's four words read 46, 37, 24, 28, the values the creation screen showed for its four rows in that order, and the load limit read 171 = 46 + 125 (`docs/issues/live-rig.md` 4b) | Observed: init fills from class table 0x4ef400 or from four bytes; stats reads them. Order: Ran |
| +0x90 | s32[4] | effective statistics = base + item modifiers 7, 8, 9, 10 | Observed: stats |
| +0xa8, +0xe3, +0x4c29 | u8 | marker bytes set to 0xaa by init | Observed; purpose Unknown (integrity marker Inferred) |
| +0xac | float | hit points | Known (G3); Observed throughout |
| +0xb0 | float | maximum hit points = level × a + stamina × b − c, constants per class | Observed: stats |
| +0xb4 | float | healing still to be delivered by a potion; +0xb8 is the amount per frame. `Player_usePotion` rewrites both per-tick rates, +0xb8 and +0xbc, on every call before any test other than "real player, alive", so a potion button pressed at full health still stores them (**executed**, `docs/spec/player-tick.md` section 12) | Observed: `Player_regenHealth` 0x1b3b90. **Ran**: after a health potion +0xb4 read 22.698 and fell by +0xb8 = 0.0683 per tick; after a mana potion +0xc8 read 30.82 and fell by +0xbc = 0.0765 per tick (`docs/issues/live-rig.md` 4c) |
| +0xbc | float | mana per frame delivered by a potion | Observed: `Player_regenMana` 0x1b3900 |
| +0xc0 | float | mana | Known (G3) |
| +0xc4 | float | maximum mana = (intelligence − a) × b + level × c, constants per class | Observed: stats |
| +0xc8 | float | mana still to be delivered by a potion | Observed: 0x1b3900 |
| +0xcc | s32 | attack rating = level (+0x58) × 20 + strength / 4 (dexterity / 4 with a bow or thrown weapon) + the weapon's attack rating (item definition +0x1a); init 0xb. Melee passes it to the damage function as `attack`, where it is compared with the victim's armour (`docs/gameplay.md` §2.1). The earlier version of this row called it a damage type | Observed: `Player_recalcDamage` 0x1b71b8–0x1b7270, `Player_meleeHit` 0x1b6a98 |
| +0xd0, +0xd4 | s32 | weapon damage minimum and maximum, rebuilt by `Player_recalcDamage` | Observed: 0x1b6a98 |
| +0xdc | float | sum of item modifier 0x1e × 0.01; lowers the chance of being staggered | Observed: stats; `Player_processDamage` |
| +0xe4 | s32 | gold (init 500) | Observed: init; script gold built-ins |
| +0xec–0xee | s8 | +0xec stat points (3 per level gained); +0xed, +0xee level-up screen bookkeeping (`docs/ui.md`); init 0, 0, 1. The s32 before them, +0xe8, is the skill points | Observed: `player_giveExp` 0x1d3150. The earlier version gave the meaning as Unknown |
| +0xef | s8[0x30] | levels of the 48 class passives, parallel to the class skill table | Observed: `player_getPassiveLevel` 0x1bed48 |
| +0x120 | float | carried load (sum of item weights) | Observed: `player_recalcLoad` 0x1bec10 |
| +0x124 | float | load limit = strength + 125 + 15 × passive 0x40, capped at 9999 | Observed: stats |
| +0x128 | u64 | cleared by script `clearAllSkills` with the passive levels | Observed 0x1458e0; meaning Unknown |
| +0x130 | item[64] | bag 0, 0x48 bytes per item; count at +0x1330 | Observed: 0x1bec10, import |
| +0x1338 | item[64] | bag 1; count at +0x2538 | Observed: same loops (stride 0x1208) |
| +0x2540 | item[64] | bag 2 (potions are counted here); count at +0x3740 | Observed: `player_countPotions` 0x1ba5f8 |
| +0x3748 | 0xa88 bytes | block copied whole on import; same size as one class skill table | Observed size; contents Unknown |
| +0x41d0 | 0x204 bytes | quest list: 8 entries of 0x40 bytes (title[0x20], text[0x20]), then the count at +0x43d0; zeroed on import | Observed: `quest_add` 0x1d386c (`docs/ui.md`). The earlier version gave it as Unknown |
| +0x43d0 | s32 | quest count (0–8); read by prediction and menus | Observed: 0x1d386c. Earlier: Unknown |
| +0x43d4 | s32 | init −1 | Unknown |
| +0x43d8 | ptr | the Player object (the prediction copy while predicting) | Known (G3) |
| +0x43f0 | item*[17] | equipped items by equipment slot (item definition +0x1c). Slot 0 one-hand weapon, 2 two-hand or ranged weapon, 3 shield, 5 and 6 rings, 8 ammunition (+0x4410), 14 and 15 earrings. Two slots were missing from this list (`docs/spec/game-messages.md` 2, 5.3): slot 1 is the second weapon's slot when dual wielding (executed in equip), and slot 7 is a single slot of item category 2 (Observed in unequip only) | Observed: `inventory_equipItem` 0x1c27c0; the 17-entry loops in stats and the regen functions |
| +0x4434 | item*[2] | primary weapon of weapon set 0 and set 1 | Observed: 0x1c27c0, `Player_weaponSwapInput` 0x1bb718 |
| +0x443c | item* | second weapon when dual wielding | Observed: 0x1b6a98 |
| +0x4440 | ability[15] | ability records, 0x68 bytes each (layout below) | Observed: init loop of 15; import copies 0x618 bytes |
| +0x4a5c | float | grows while standing in state 2, shrinks while blocking; no other reader | Known (G8) |
| +0x4a60 | s16 | which ability button was pressed last (0 or 1) | Observed: `Player_run` 0x1a5a88 |
| +0x4a64 | s32 | −1 / +1 request from two buttons | Observed: `Player_pollAbilityCycle` 0x1bf0a8; reader 0x1de8c4 (UI) |
| +0x4a7c | s8 | active weapon set (0 or 1) | Observed: 0x1bb718, 0x1c27c0 |
| +0x4a7d | s8 | weapon swap pending | Observed: 0x1bb718 |
| +0x4a80 | u32 | pad mask of the ability button in use | Observed: 0x1a5a44–0x1a5aa8 |
| +0x4a84, +0x4a85 | s8 | index of the ability record bound to button A and to button B | Observed: instant-ability check after 0x1a5c64, states 1, 2, 5 |
| +0x4a86 | s8 | weapon animation class in use: 0 one-hand, 1 and 2 two-hand kinds, 3 long weapon, 4 bow, 5 unarmed, 6 thrown, 7 dual wield | Observed: copied from item definition +0x1e on equip; selects the attack animation name and combo table in state 1 |
| +0x4a88, +0x4ac8 | 0x40 bytes each | weapon trail state for the main and second weapon; +0x3d hit material, +0x3e a 5-frame timer | Observed: `Player_weaponTrails` 0x1bc768; 0x1b6a98 tail |
| +0x4b08 | {s16 id, s16 rank}[48] | skill ranks, terminated by id −1 | Observed: `player_getSkillRank` 0x1bf330 / `player_setSkillRank` 0x1bf3a0 |
| +0x4bc8 | s8 | countdown; at 0 clears object flag 0x400000 | Observed: `Player_run` tail 0x1ac6f8 |
| +0x4bc9 | s8 | countdown; while non-zero no ability can start | Observed: state 2, 0x1ac74c |
| +0x4bca | s16 | level-change cooldown | Known (D20); decremented at 0x1ac6e8 |
| +0x4bbf + d×13 + m | u8 | mission flags for difficulty d (1–5) and mission m (0–12): bit 0 available, bit 1 complete | Observed: 0x1bf698–0x1bf770 |
| +0x4c0d | s8[13] | medal earned per mission | Observed: 0x1bf7e8, 0x1bf838, 0x1bdb80 |
| +0x4c18 | u64 | bit field. Bits 32–36 (the low five bits of +0x4c1c) hold a character-kind value: init stores its ninth argument, or 1 when that is −1; the only caller that passes anything else is the character screen `playerSel_task`, which passes 2 on its lobby branch (0x228618); script `saveGame` and `net_allPlayersState2` test for 2. +0x4c1a evil bits and +0x4c1b decision bits, one bit per difficulty. The earlier version called bits 32–36 the difficulty index; that is the separate global `g_difficultyIdx` 0x4f719c | Observed: init 0x1b1de8–0x1b1e60, 0x146c34, 0x1ec62c; names.tsv |
| +0x4c20 | float | movement speed multiplier, 1.0 | Observed: `player_speedScale` 0x1bea10 |
| +0x4c24 | s8 | team (PvP) | Observed: `Player_isEnemy` 0x1b5ea8; Player vslot 37 |
| +0x4c26 | s8 | second earring slot unlocked | Observed: 0x1c27c0; script `piercePlayerEar` |
| +0x4c27 | s8 | hit immunity countdown (net games; 60 after a cutscene) | Observed: 0x1bfaf8, 0x1b5438, 0x1a5368 |
| +0x4c28 | u8 | eight script flags | Observed: `player_setFlag` 0x1be398 / `player_getFlag` 0x1bfb80 |

The whole record is sent to the other machines at launch: `player_packRecord` 0x1be0d0
compresses runs of zero bytes and `player_unpackRecord` 0x1bfa38 expands them (callers
`net_launchTransfer` 0x134c60 and 0x135638). **Observed.** So every machine holds the same
four records, but the four records differ from each other.

### Item record (0x48 bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | ptr | item definition (+0x1c equipment slot, +0x1d hand class, +0x1e weapon animation class) | Observed: 0x1c27c0 |
| +0x04 | s16 | quantity (arrows, thrown weapons, potions) | Observed: `Player_run` 0x1a8890 and later |
| +0x08 | u64 | flags (bit 24 thrown weapon, bits 42–44 arrow kinds, bit 39 see `player_removeFlag39Items`) | Observed: state 0 |
| +0x24 | {s16 id, s16 value, s16 ?, s16 frames}[4] | modifiers. Ids seen: 7–10 statistics, 0xb hp regeneration %, 0xc mana regeneration %, 0x14 attack speed (4.5% each), 0x1e stagger resistance; the ids listed at 0x537c08 are timed | Observed: stats, 0x1b3b90, 0x1b3900, `Player_tickEnchantTimers` 0x1bc560 |

### Ability record (0x68 bytes)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | char[] | name; one fixed name marks an ability implemented by a `Skill` object in `g_skillTable`, any other name takes the older inline code paths | Observed: string compare with 0x535e30 before every use |
| +0x20 | s16 | skill id (−1 empty) | Observed |
| +0x22 | s16 | cooldown in frames, copied to object +0x4ae | Observed |
| +0x24 | u8 | non-zero: the ability may be started from state 2 | Observed |
| +0x25 | u8 | kind: 0 one cast, 1 held (mana per frame), 2 timed, 7 instant (no animation: state 2 calls `Player_castSkill` at once, 0x1a7048), 8 "fire through the ranged state": state 2 asks the skill's "can use" slot and keeps the record at object +0x484 (0x1a7058–0x1a709c), and the next ranged release casts it (0x1a837c, 0x1a9174). (The earlier version called 8 a toggle; `docs/spec/skills-35-68.md` section 4.6.) | Observed: state 2 and state 5 |
| +0x28 | s16 | effect strength (older code) | Observed: argument of the call at 0x1ac400 |
| +0x2c | float | mana cost (older code); 999 means "needs full mana" | Observed |
| +0x30, +0x38, +0x40 | s16[3], s16[4], float | aura colours and fade rate | Observed: state 5 |

## The Player object beyond the Creature part

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x3c8 | s32 | slot index | Known |
| +0x3cc | u8 | set when the shot of state 0 has been released | Observed |
| +0x448 | s32 | frame number at which the current action started | Observed: every state |
| +0x44c | s32 | attack request: 0 none, 1 another swing queued, 2 heavy attack | Observed: states 1, 2 |
| +0x450 | s32 | "repeat the ability" latch | Observed |
| +0x454 | s32 | block requested this frame | Observed: 0x1a5e2c |
| +0x458, +0x45c | s32 | frame stamps of the attack chain | Observed: state 1 |
| +0x460, +0x461 | s8 | combo step; attack animation variant | Observed: state 1, 0x1bba88 |
| +0x462 | u8 | display-only player (menu model); not registered in `g_players` | Observed: ctor |
| +0x463 | u8 | fidget animation running | Observed: 0x1bc2f8 |
| +0x464 | u8 | written by `Player_draw`: 0 drawn, 1 not drawn | Observed: 0x1a48c4 / 0x1a48c8 |
| +0x468, +0x46c | float | last speed; walk/run blend | Observed: `Player_move` |
| +0x470 | float | length of the current attack in seconds | Observed |
| +0x474 | s8[4] | bonuses derived from the four effective statistics (+0x475 mana regeneration, +0x477 hp regeneration) | Observed: stats, regen functions |
| +0x47b | u8 | cast phase 0/1/2 | Observed: state 5 |
| +0x47c–0x47e | u8 | flags of state 7 | Observed |
| +0x47f | u8 | blocking | Observed: state 8 |
| +0x480 | u8 | kind of ranged shot: 0 plain, 1/2/3/5/6 special arrows, 7 throw. The values 1–6 are stored only by the older inline ability ids (0x1a74f8–0x1a7544); the bow skills that are `Skill` objects go through +0x484 instead | Observed: states 0, 2 |
| +0x481 | u8 | frames during which the stick is ignored | Observed: 0x1b4020 top |
| +0x482 | u8 | set to 15 while on the ground, counts down otherwise | Observed: 0x1b4020 |
| +0x484 | ptr | ability record of a kind-8 ability waiting for the next ranged release (stored at 0x1a709c, cleared at 0x1a7094 when the skill refuses); "toggle" in the earlier version | Observed |
| +0x488 | ptr | ability record forced from outside; cleared each frame unless casting | Observed |
| +0x48c | float | minimum time between attacks | Observed |
| +0x4a8 | s32 | handle of a looping sound, −1 none | Observed |
| +0x4ae | s16 | ability cooldown | Observed |
| +0x4b0, +0x4b2 | s16 | idle frames; threshold for the idle voice line | Observed: 0x1a5450 block |
| +0x4b4 | s16 | spawn protection countdown (60, or 90 in a net game) | Observed: 0x1b8f28 |
| +0x4b8 | handle list | targets of a sweeping attack | Observed |
| +0x4bc, +0x4c0 | float | last movement velocity | Observed |
| +0x4c8, +0x504 | light | two light objects; +0x504 is the coloured aura light | Observed: ctor, run tail |
| +0x540 | ptr | vehicle being ridden | Observed: state 0xd |
| +0x544–0x558 | handles | body model and appearance parts | Observed: ctor |
| +0x55c | s32 | net games: a melee hit lands only while this is 0; set to 16 while blocking | Observed: 0x1aa6ec–0x1aa738 |
| +0x588 | handle | the held (channelled) spell | Known (G2) |
| +0x58c | s32 | action state | below |

### Virtual slots of Player (table 0x511308)

Slots not listed are inherited from Creature.

| Slot | Function | Meaning | Evidence |
|---|---|---|---|
| 1 | 0x1a1bb8 | destructor | Known |
| 2 | 0x1b5330 `Player_takeDamage` | queue damage | Observed |
| 4 | 0x1a5030 `Player_run` | | Known |
| 5 | 0x1a46c0 `Player_draw` | | Known |
| 6 | 0x1beaf0 `Player_onTouch` | rush skill contact | Observed |
| 15 | 0x11e870 | clone | Known |
| 16 | 0x3c3b38 | returns the body model (+0x544) | Observed |
| 20 | 0x1b5ea8 `Player_isEnemy` | | Observed |
| 27 | 0x1b5d68 | sets state 0 or 1 with an animation | Observed; purpose Unknown |
| 29, 30 | 0x3c3b08, 0x3c3b10 | empty | Observed |
| 37 | 0x3c3b18 | returns the team byte (record +0x4c24) | Observed |
| 39 | 0x3c3b40 | skill rank for a skill id | Observed |

Slots of other classes that `Player_run` relies on (**Observed** at the call sites):
creature slot 12 (table +0x60) "you are being aimed at" with kind 2 (ranged) or 3 (melee);
slot 17 (+0x88) set aim point; slot 26 (+0xd0) turn toward a point. `Skill` (table at
skill +0x60): slot 1 "can this player use it", slot 2 cast (returns a Spell), slot 5 mana
cost for a rank. `Spell` (table at spell +0x14): slot 1 with argument 3 ends it.

## The action state machine (+0x58c)

| State | Meaning | Entered from | Left to |
|---|---|---|---|
| 0 | ranged attack: bow shot, or throw when +0x480 is 7 | state 2 with a bow or thrown weapon and the attack button (0x1a7b04 on); Player slot 27 | 2 when the animation flag clears and the minimum interval has passed |
| 1 | melee swing and combo | state 2 (attack button, or heavy attack skill 0x25) | 2 at the end of the swing; 8 if block is held |
| 2 | neutral: standing or moving; every action starts here | constructor; end of every other state | 0, 1, 5, 8, 10, 0xc |
| 3 | staggered or knocked down | `Player_processDamage` 0x1b2ed8 and 0x1b380c | 2 when the hit animation ends |
| 4 | dead | `Player_processDamage` 0x1b34fc | never; the object is replaced by `player_respawn` 0x1bd040 |
| 5 | casting an ability | state 2 | 2 when released, finished, refused or out of mana |
| 6 | under control of a skill (leap-type skills supply the velocity) | skill code 0x2d17c8, 0x2de640, 0x2e09b4, 0x2face4, 0x30016c, 0x301714, 0x303254 | the same skills set 2 |
| 7 | airborne (a jump impulse, then falling) | no direct store of 7 found; Unknown | 2 on landing (`Player_move`) |
| 8 | blocking | states 1, 2, 0xb when block is held and `player_canBlock` | 2 on release; 0xb |
| 9 | rush forward (movement mode 2); contact handled by `Player_onTouch` | skill code 0x2c8864 | skill code |
| 10 | ground-pound style skill; animation events do area damage | state 2 older skill id 0xc; skill code 0x2c71ec | 2 |
| 0xb | block move: swap button pressed while blocking | `Player_tryBlockMove` 0x1bf150 | 8 or 2 |
| 0xc | war-cry (older skill id 0xe) | state 2 | 2 |
| 0xd | riding a vehicle | 0x208f08 | 2 (the copy predicts the dismount button) |
| 0xe | skill-held state with no handling in `Player_run` | 0x311638 | skill code |

All **Observed** in `Player_run`'s switch at 0x1a5e80 and the stores listed; the short
English names are mine.

Order of work in `Player_run` each frame: `Creature_run`; mirror hp to object +0x228;
timers; idle voice; choose the pad (a zeroed pad at 0x8667f0 replaces the real one while
controls are locked); aura light fade; potion buttons; ability button selection; health and
mana regeneration and item timers; kill plane; `Player_processDamage`; weapon swap and
interact; the state switch; aura light; `Player_updateCast`; record countdowns.

That list reads as if every tick reached its end. Three exits skip the tail, and with it
`Player_updateCast` and the record countdowns (**executed**, `docs/spec/player-tick.md`
sections 1, 6, 7 and 12): the scripted-control exit, taken when object +0x231 is non-zero
(test at 0x1a55a4), which also skips regeneration, the kill plane and
`Player_processDamage`; state 0xb while `g_recallCountdown` is non-zero (0x1a6588); and
record +0x4a60 holding anything other than 0 or 1 while the aura light is on (0x1ac4c0).

Two net-game differences inside the state machine (**Observed**): the melee hit is applied
on frame 1 of the swing instead of at 16 frames ÷ attack speed (0x1aa6ec–0x1aa738), and the
ranged release time is halved (0x1a80e0 on). Movement speed is 0.75 instead of 0.861945.
The first of these needs a condition the sentence left out, though the field table above
has it: on frame 1 **only when +0x55c is 0** (the word is loaded at 0x1aa6ec and counted
down at 0x1aa730). +0x55c is 16 after any tick in state 8 or 0xb and falls by one per tick
spent in state 1 in a net game, and frame 1 is the only hit frame, so no swing lands until
16 melee ticks have passed since the last block (**executed**, `docs/spec/player-tick.md`
state 1 step 7 and section 12). The two speeds are **Ran** on the live game: 2.585831 to
2.585844 units per tick offline against 180 × 0.861945 / 60 = 2.585835, from the first
tick, and 2.25000 per tick in a net game (`docs/issues/live-rig.md` 4c, 4d; FINDINGS V3).

## Functions that matter

| Address | Name | Note |
|---|---|---|
| 0x1a1d28 | `Player_ctor` | |
| 0x1a5030 | `Player_run` | 30 KB |
| 0x1b4020 | `Player_move` | position changes come from here (through creature move 0x1186d8) |
| 0x1b2cc0 | `Player_processDamage` | pending damage → hp, stagger, death |
| 0x1b5330 | `Player_takeDamage` | |
| 0x1b6a98 | `Player_meleeHit` | |
| 0x1a42b8 | `Player_castSkill` | only route by which `Skill` objects are cast by a player |
| 0x1a3f70 | `Player_updateCast` | |
| 0x1b9520 | `Player_animStep` | |
| 0x1b6458 | `player_recalcStats` | |
| 0x1b1d70 | `player_initNewCharacter` | |
| 0x1bd040 | `player_respawn` | |
| 0x1b5fa0 | `player_recallTick` | |
| 0x1be0d0 / 0x1bfa38 | `player_packRecord` / `player_unpackRecord` | |
| 0x1bfdb0 | `invmsg_dispatch` | inventory changes arrive as game messages and are applied here |

## Per-machine state

### Places where shared state can be changed differently on one machine

1. **The copy's death rebuilds the alive list.** `Player_processDamage` calls
   `game_rebuildAlivePlayers` at 0x1b3504 with no test for the copy; `Player_run` calls
   `Player_processDamage` at 0x1a5b90, also unguarded. The rebuild reads the object pointer
   in each record, which during prediction is the copy, and drops slots whose object has
   the dead flag. The table pointer, hp and mana are restored after prediction but the
   list is not; `tasks_run` (0x3226e4) rebuilds it only at the *end* of each simulated
   frame. **Observed.** Consequence: after the copy dies in prediction, the next simulated
   frame on that machine runs with its own player missing from `g_alivePlayers` while the
   other machines still have it. About 50 functions read that list (monsters, scripts,
   skills). **Inferred** to desynchronise. How the copy can die ahead of the real player:
   the earlier version named the kill plane first, because its code is applied to the copy
   too (0x1a5b38–0x1a5b8c writes 1,000,000 pending damage, no guard — **Observed**). That
   route does not exist in this build: the plane is −100000 in all 90 rows of the level
   table (0x4f7210 + n × 0x30 + 8), so no level enables it (G15,
   `docs/issues/prediction-copy.md`; `docs/issues/arena-desync.md`). What remains is a copy
   cloned while damage was pending — **Observed** there (G12, G14). This is G11–G13; G10,
   which this item was first compared with, is withdrawn. Also at
   0x1b351c the copy's death calls `net_closeLocalMenus(1)` (local UI only).
2. **`mission_getMedal` reads the local player's record.** 0x1bf838 calls
   `net_getLocalPlayerSlot` (0x1bf868) and reads that record's medal byte unless its third
   argument is set. Script built-ins `getMedal` (0x142188) and `runMedalSuccess` (0x1417a4,
   call at decompile line 64) pass 0; nine level scripts (`*MEDAL`) call `getMedal`.
   **Observed.** Each record carries its owner's medals, so two machines can get different
   answers inside a lockstep script. **Inferred** hazard; only the medal levels are
   affected. (Callers 0x231360, 0x2313b4, 0x231438 pass 1 and read slot 0.)
3. **`Player_castSkill` runs some skills for the copy.** For the copy, a skill whose flag
   word (+4) has bit 0 set has its cast function called (0x1a4598, vslot 2) and the
   returned spell is destroyed straight away (0x1a45d0). Anything else the cast
   function changes stays changed. **Observed.** Which skills carry bit 0 is set by static
   constructors and was not read — **Unknown** here; `docs/skills.md` has since read them:
   only Cyclone (ids 41, 84; constructor 0x2d13ec) and AncestralCall (51; 0x2e0640) set
   it. Their "can use" functions (vslot 1) are
   called for the copy from 0x1a4358, 0x1a5d54, 0x1a7088 and 0x1ab618 as well and must be
   free of side effects.
4. **Older ability paths have no test for the copy.** They are taken only by ability
   records whose name is not the `Skill` marker (see D15/D16 for whether any character
   has one). **Observed**, all in `Player_run`:
   - 0x1a74b0 stores 1 to record +0x4a7c (active weapon set) for skill ids 4, 5, 6, 0x12,
     0x13;
   - 0x1a67b4 (state 0xc), 0x1abe68, 0x1ac120, 0x1ac378 create a `LightEffect` object;
     0x1ac02c creates a projectile-class object (0x293704); 0x1ac164 creates an
     `UnholyAura` (0x29486c). The object constructor's draw from `g_randSeed` is restored,
     the object itself stays in this machine's world;
   - 0x1ac400 does area damage (`world_damageInRadius` 0x161270). Harmless for the copy:
     the call ends in `damage_apply`, which returns before reading or drawing anything
     when the attacker carries the copy flag 0x20000 (0x1e828c–0x1e82a4;
     `docs/issues/prediction-copy.md` section 3.2). The object creations above remain.
   The status-counter stores on the same paths (0x1a71c4, 0x1abda0, 0x1abe90, 0x1ac068)
   go to the copy's own object while predicting and are not shared state.
   The matching code for the heavy attack (0x1a73e4) and for state 10 (0x1a6950,
   0x1a69bc) *is* guarded, which suggests the unguarded paths are leftovers.
5. **Target notification from the copy.** In state 1 the chosen target's slot 12 is called
   with kind 3 at 0x1aa5b8, no guard (the ranged equivalent with kind 2 is guarded).
   **Observed.** No class handles kind 3 today (the ten overrides test only kinds 0 and 2),
   so this is latent.
6. **Script hook from the copy.** 0x1a90f0 runs the arrow-shot notify script by name with
   no guard. **Observed.** No level script on the disc defines it; latent.
7. **Record +0x4a5c** is written by the copy (0x1a6270, 0x1a629c, 0x1a8078, 0x1a8084).
   Already G8; nothing reads it.
8. **`Player_takeDamage` early-outs** (0x1b536c–0x1b53f4) on `g_recallCountdown`, the
   jump-gate state 0x500ae8 (through 0x27dd68), `g_menuInputLockout` 0x41b4fc and
   `g_exitCountdown` 0x4f694a. **Observed.** If any of these differs between machines for
   one frame, damage is dropped on one machine only. The earlier version left "whether
   they can differ" **Unknown**; two of the four are now answered:
   - 0x4f694a cannot differ. It is set by game message 8 (0x1d907c) and `hud_run`, a run
     task, subtracts one on every tick with no per-machine condition (0x1db8ec–0x1db8f0):
     lockstep (`docs/issues/draw-sim-leaks.md` U5; `docs/issues/claims-audit.md` row 87).
   - 0x41b4fc can differ inside a tick. It is zeroed at the top of every net tick, but
     per-machine code can set it again before `Player_takeDamage` reads it — the local
     player dying with a menu open, the medal countdown, an automatic jump gate (FINDINGS
     D26; `draw-sim-leaks.md` U3).
   - The recall countdown is set by a game message handler; the jump-gate state was not
     followed here.

### Per-machine reads that only reach local presentation (checked)

- `Player_draw` writes object +0x464 and the globals at 0x4d8a30/0x4d8a38; `Player_run`
  reads +0x464 only to decide whether to run `Player_weaponTrails` (0x1a5638).
  **Observed**; trails use the cosmetic seed.
- `Player_draw` calls `Player_interact` in display mode for the local slot (0x1a4800). In
  that mode it writes only the prompt globals (0x4d8ac0, 0x4d8ad0, text at 0x864f50) and
  never `g_scriptActivePlayer`. **Observed.** It does call slot 13 (prompt) of nearby
  objects from draw code; those functions belong to other areas and were not read.
- `player_voice` 0x1b7ba8 reads `net_isLocalSlot`, `g_localMenuOpen` and the audio status;
  it writes only the cosmetic seed. **Observed** (ghostreach lists no other store).
- State 1 uses `net_isLocalSlot` (0x1aa6f4) only to choose the frames on which swing
  sounds play; those sounds draw from a third generator at 0x404468 (0x1aa990), which is
  therefore not synchronised. **Observed.** Other users of 0x404468 (0x110d30, 0x24c994,
  0x284b68, 0x2c7808, 0x2ee068, 0x308578) were not read. (The earlier version gave
  0x2eec08, an address inside `HammerOfWrath_run` 0x2ee068.)
- `Player_animStep` passes no position for the machine's own real player (object flag
  0x200000), which makes the animation code skip sound cues and not advance the cue
  cursor; the returned event bits do not depend on it. **Observed** (0x16d748).
- `Player_move` takes the camera yaw from the per-slot word at 0x5d0bc0 (0x13e0c8), which
  `net_frameLoop` fills from the input record (0x13ac9c). The screen-edge clamp
  (`Player_clampToScreen`, view planes) is used only when `g_networkMode` is 0.
  **Observed.**
- The aura globals (0x4d8a40–0x4d8ab0, 0x8659a0) and the HUD message timers 0x41b840 /
  0x41b8c0 (0x1a75d0) are advanced by the copy too; their only readers are `Player_draw`,
  `Player_run`'s own light code and the HUD. (More writers than this document lists:
  `player_recallTick`, `Player_updateCast` and `player_resetAuraLights` for the aura
  globals; `Player_usePotion`, `Player_weaponSwapInput` and the two axe skills for the
  hint timers — `docs/issues/claims-audit.md` row 86. No simulation reader, so the
  statement stands.) Floor decals added in state 4 (0x1ab4b4) and
  `hud_showMessage` calls (0x1a6ebc, 0x1a7af0, 0x1a8040, 0x1aafc4) are likewise
  unguarded and local. **Observed.**

### Checked and found guarded against the copy

Potion use (0x1a5998, 0x1a59f0; G8 — the guard against the copy holds, but for real
players the removal of the potion from the bag has a per-machine branch on this machine's
inventory screen, 0x1b9fcc and 0x1ba3ac in `Player_usePotion`: K2,
`docs/issues/kill-loot-xp.md`). Weapon swap and interact (0x1a5bf0, 0x1a5c1c). Health
and mana regeneration and item timers (tests inside 0x1b3b90, 0x1b3900, 0x1bc560). Hit
immunity countdown (0x1a5368). Ability button selection (0x1a5a44–0x1a5aac). Thrown
projectile creation, ammunition count and item removal (0x1a86f0, 0x1a881c, 0x1a8884,
0x1a8958). Arrow creation, arrow count, item removal and the ammunition pointer (0x1a9240,
0x1a9344, 0x1a944c, 0x1a9520, 0x1a9544). Ranged target notification. `Player_meleeHit`
(returns for the copy). Heavy-attack `LightEffect` (0x1a73e4). State 10 area damage and
`GroundPoundEffect` (0x1a6950, 0x1a69bc). State 6 skill polling. The record countdowns at
the end (0x1ac6e8–0x1ac74c). `Player_onTouch`. In `Player_processDamage`: the blood prop
and the knock-back skill. In `Player_move`: the rush contact call.

Writes that the prediction loop restores and so need no guard: every `g_randSeed` draw in
`Player_run` and its direct callees (0x1a549c, 0x1a64c4, 0x1a8420 … 0x1ab490, and in
0x1bba88, 0x1bc2f8, 0x1bcc20, 0x1b4020, 0x1b2cc0), and the mana stores at 0x1a5b04,
0x1a7278, 0x1a94ac, 0x1ab6c0 and in `Player_castSkill`.

## Not read

`Creature_run` and everything under it, creature move/collide 0x1186d8, the damage function
0x1e8230, the `net_closeLocalMenus` subtree, `playerProjectile_run` 0x1ba940 (called
`Projectile_runThrown` in the earlier version; it is slot 4 of table 0x50e470, class
`playerProjectile`),
`player_giveStartingItems` 0x1acc78 (20 KB of item grants), `Player_recalcDamage` beyond
its interface, `Player_drawEquipped` 0x1a3580 (decompile failed), the equipment-cache
functions in detail, and the menu list widget. Of ghostreach's 812 reachable functions I
checked the direct callees of `Player_run` and the player-record writers; the deeper
engine, sound and library entries were judged by what they write, not read. "The
player-record writers" means the ones that tool lists, and its list is short: it does not
print indexed stores. The field audit names the record writers it misses among functions
the copy can reach — `Player_regenHealth`, `Player_regenMana`, `Player_takeDamage`,
`Player_usePotion`, `OniBall_onTouch`, `hud_addGoldFloater`, `inventory_giveItem`,
`inventory_equipItem` and four stores of `Player_run` itself — and says which contain a
test of the copy flag and which depend on their callers; whether each test guards each
store was not re-read there (`docs/issues/field-claims-audit.md` 6.3).

## Open questions

- Which `Skill` objects have flag bit 0 (run for the copy)? Read the static constructors
  that fill the objects at 0x6e14d8 onward, or dump skill +4 from a memory snapshot.
  (Answered in `docs/skills.md`: ids 41, 84 and 51.)
- Does creature move/collide (0x1186d8) call the "touched" slot of other objects when the
  mover is the copy? That would be shared state changed by the copy. (Answered in
  `docs/objects.md`: 0x1186d8 goes to `obj_moveWithCollision` 0x14d4b8, which tests the
  mover's 0x20000 flag at 0x14d9ac and skips the other object's slot 6; the copy's own
  slot 6 still runs. `docs/spec/movement-camera.md` read the same test, 0x14d9b0–0x14d9b8,
  and agrees.)
- State 7: what sets it? No store of 7 to +0x58c exists as a constant; look for a computed
  store or a clone from another object.
- State 0xd for the copy calls the vehicle's slot 17 with the player's position (0x1a5efc)
  and then 0x14f028 (0x1a5f04); whether the vehicle is changed by that was not established.
  (Answered in `docs/issues/prediction-copy.md` section 3.2: the slot is
  `Vehicle_getRiderPose` 0x2088a0, a getter; the vehicle is not changed.)
- Record +0x128 and +0x3748: meanings. (+0x58 versus +0x59, +0xe8–0xee and +0x43d0 were
  listed here too; `docs/ui.md` answers them and the record table now says so.)
- Which button is the health potion and which the mana potion (`g_btnPotionA/B`).
  Answered on the live game (**Ran**, `docs/issues/live-rig.md` 4c; FINDINGS V5): potion A
  (`g_btnPotionA`, mask 0x2, R2 by default) is the health potion and potion B
  (`g_btnPotionB`, mask 0x1, L2 by default) the mana potion. R2 at full health consumes
  nothing; below it the bag-2 quantity drops by one.
- Whether `player_importCharacter` reads the previous game's save format (layout and the
  level cap of 50 suggest it — Inferred).
- names.tsv calls 0x1309f0 `clone_50d590`; vtables.txt gives table 0x50d590 to class
  `Teleporter`.
