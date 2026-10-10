# Kill, experience, loot and pick-up in a net game: what depends on the machine

The Drundar arena (`drunare`) is reported to go "… IS OUT OF SYNC!" on every two-player run.
`docs/issues/arena-desync.md` traced the monsters, the prediction copy, the pool and the
cutscenes and found nothing that bites every time. This document traces what was left: the
chain that follows a killing blow (damage with weapon and item effects, experience, level-up,
loot, pick-up), on every machine, looking for anything that depends on which machine runs it.

Everything here was read from the executable (decompile and disassembly); nothing was run.
Claims are **Observed** (read at the address given), **Inferred** or **Unknown**. Patch
proposals are **untested**.

## Result in one table

| # | Finding | Kind | Needs | Rank |
|---|---|---|---|---|
| K1 | `Player_run` skips `Player_interact` while a per-slot flag at 0x41b818 is set. Only HUD draw code on the owning machine writes that flag (D-pad held = quick-spell selector open). The other machines always call it | Observed | a "use" press followed by the D-pad within the input delay, next to something interactable | 1 |
| K2 | `Player_usePotion` does not take the potion out of the bag on the owner's machine when that machine's inventory is open; it sends a drop message instead. Every other machine takes it out directly, and then also runs the message | Observed | a potion button followed by the inventory button within the input delay | 2 |
| K3 | The stats page (draw code, owner's machine) calls `Player_recalcDamage`, which writes the record's attack rating and weapon damage (+0xcc, +0xd0, +0xd4). For a dual wielder the last call is for the off-hand weapon | Observed; effect Inferred small | a reader of those fields before the next per-tick recompute | 4 |
| K4 | The stats and skill pages call `player_recalcStats`, which recomputes derived fields of **every** player's record and object on that machine | Observed; found idempotent | a derived field that is stale in lockstep (none found) | 6 |
| K5 | In-flight loot is deleted when 120 units below the first alive player; a failed `pool_new` silently drops a roll's object, and an item whose landing conversion fails is lost | Observed; already G19 and D21 | a wrong alive list, or a full pool | 3, 5 |

**The chain itself is lockstep.** Damage, the kill, the experience split, the level-up, every
loot roll, the dropped objects' physics, gold pick-up and item pick-up are computed by every
machine from shared state, in the same order. No step was found that differs between machines
on every run. K1 and K2 are real per-machine branches inside the tick, but each needs two
button presses within the input delay; neither explains "every time" on its own. See
"Ranked list" and "What to record on two machines".

## Facts the rest depends on

- **F1. Where messages run.** `net_frameLoop` applies each peer's input record and runs that
  peer's game messages (handler call 0x13ad24) before it runs the run tasks (0x13aee0). So a
  record change that arrives as a message in frame F is in place before any object runs in
  frame F, on every machine. **Observed** (docs/netcode.md, "The tick").
- **F2. Input delay.** A pad sample taken in `net_main` call *c* becomes the record of a
  future frame; the tick of a call runs at most up to `g_localInputFrame − 2` (0x1342bc). With
  a lead of *L* frames (minimum 2, more with latency, cap 38) the sample of call *c* is
  simulated in call *c + L − 1*. Draw tasks run after `net_main` in each displayed frame, so
  the last HUD draw before that tick is the one of call *c + L − 2*. **Observed** rules,
  **Inferred** arithmetic.
- **F3. Who the record points at.** Record +0x43d8 is the real player object during a tick
  (the prediction loop restores it, G3). Every "is the killer a player" and "player position"
  read in this chain goes through that pointer inside a tick. **Observed** uses, e.g.
  0x111ec4, 0x156d3c.

## 1. An ordinary player hit

### What the hit reads

Melee: `Player_run` state 1 → `Player_meleeHit` 0x1b6a98 → `Player_recalcDamage` 0x1b7158 →
`damage_apply` 0x1e8230. All **Observed** in those three functions.

| Source | Fields | Used for |
|---|---|---|
| Record, equipment | +0x43f0, +0x43f4 (hands), +0x4434[active set] (primary weapon), +0x443c (second weapon), +0x4a7c (active set), +0x4a86 (weapon class) | which item is the weapon; second weapon on odd combo steps when the dual-wield passive (mask 0x40000) has a rank |
| Weapon item (0x48 bytes in a bag) | definition damage range, definition +0x1a, definition +0x20 (damage-type bits → flags), item flags +8, the four modifier slots at +0x24 | base range, attack rating, flags; **the item itself is the damage descriptor** handed to `damage_apply`, so its modifiers are the effect slots of docs/gameplay.md §2.2 |
| Record, character | +0x50 class, +0x58 acknowledged level (×20 into the attack rating), +0x90 / +0x98 effective strength / dexterity (÷4), passive levels +0xef, skill ranks +0x4b08 (ids 0x3c, 0x3d, 0x30, 0x4f, 0x5c, 0x47) | multipliers |
| Record, results | +0xcc attack rating, +0xd0 / +0xd4 damage range — written by `Player_recalcDamage`, then scaled in place by `Player_meleeHit` (heavy attack, damage multiplier argument) | arguments of `damage_apply` |
| Player object | +0x44c attack request, +0x448 / +0x458 / +0x45c frame stamps, +0x460 combo step, +0x58c state, status counters 2 and 4 (+0x374, +0x37c) | heavy attack, knock-back class, class-5 timing bonus |
| Attached spells | HarmTouch on the attacker (0x1b6fe8, 0x1b7000); BloodLust, GiantGrowth on the attacker; AncestralCall on **any alive player** (alive list, 0x1b7810) | multipliers |
| Inside `damage_apply` | attacker skills 0x21, 0x35, 0x51 (critical chance, with an aura from alive players), skill 0x40 proc, Retribution; on a player victim: object +0xe4 armour, +0x5c…+0x6c resistances, Spirit Shield, Frost Armor, undead shields, skills 9 and 0x52, record +0x4c27 immunity | rolls and amounts (docs/gameplay.md §2.5) |

Ranged: the arrow or thrown object is built in `Player_run` state 0 from the record's stored
values, not from a fresh computation: damage range at 0x1a857c / 0x1a8588 (throw) and
0x1a9188 / 0x1a9194 (arrow), attack rating at 0x1a9204. Those stored values are refreshed
every tick by `Player_weaponSwapInput` 0x1bb718, whose last statement is
`Player_recalcDamage(player, primary weapon of the active set, 1)` (0x1bba58), called earlier
in the same `Player_run` (0x1a5bf0). **Observed.**

`Player_meleeHit` returns at once for the prediction copy (test of 0x20000 at 0x1b6ae8), and
`damage_apply` refuses a copy attacker. **Observed.**

### Is every piece the same on every machine?

- Records are sent whole at launch and are changed afterwards by lockstep code and message
  handlers (F1). Objects are lockstep. Of the two status counters the hit reads, counter 4
  has no setter at all (every access to creature +0x37c outside the clone functions is a
  read — `fieldxref` over the whole program), and counter 2's only setter is the old
  ability path of FINDINGS D15, whose reachability is still Unknown (D16). **Observed.**
- When a monster hits a player, `Player_takeDamage` 0x1b5330 does read `g_localMenuOpen`
  (0x1b53f4), but only to tint this machine's screen; the amount and the shared draw for
  the block animation do not depend on it. Its per-machine early-out is the lockout word
  (0x1b53d4, FINDINGS D26). **Observed.**
- The acknowledged level +0x58 is the one input that lags on purpose: a level-up raises +0x59
  at once, and +0x58 follows only when the owner opens the level-up screen (section 2). It
  moves by message, so it lags identically everywhere. **Observed.**
- **Record fields written outside the tick, on the owner's machine only** (the complete list
  found, by reading every caller of the functions that write them):

| Field | Writer (local code) | Read by the simulation? |
|---|---|---|
| +0xcc, +0xd0, +0xd4 | `stats_screen` 0x1d1db8 → `Player_recalcDamage` at 0x1d2c38 and 0x1d2d30 | yes — K3 |
| +0x90…+0x9c, +0xb0, +0xc4, +0x124, +0xdc, hp/mana clamp; object +0x474…+0x477, +0xe4, +0x5c…+0x6c — for **all** players | `player_recalcStats` 0x1b6458 called from `stats_screen` (0x1d2e7c), `skills_screen` (0x1d5950) and item-list code 0x1cdd28 (0x1ce530) | yes — K4 |
| bag item counts (potions) | `Player_usePotion` 0x1b9cb8, local-menu branch | yes — K2 |
| +0x4a74, +0x4a78 | `hud_spellSelect` 0x1dd270 (stores 0x1dd4f8, 0x1dd500, 0x1dd524, 0x1dd55c) | no reader found outside that function. (List changed by `docs/issues/claims-audit.md` row 59: the HUD ability-bar function 0x1de8c4 also reads and writes both, 0x1dee1c–0x1def78, but nothing calls it; `player_initNewCharacter` and `player_importCharacter` store them. Still no simulation reader) |
| +0xed, +0xee, +0x4a58, +0x4a5c | docs/ui.md P4, FINDINGS G8 | menu code only |

- **Order of a message against a hit**: the same everywhere (F1). An equip, a stat point, a
  skill point or a level acknowledgement that lands in frame F is applied before any hit of
  frame F on every machine. What is *not* covered by that rule is local code that acts before
  its message arrives: K1, K2.

### The per-tick gate around weapon recompute and interact

**Observed** at 0x1a5b98–0x1a5c20. After `Player_processDamage`, `Player_run` calls
`Player_weaponSwapInput` and then `Player_interact` unless one of these holds:

| Test | Address | Same on every machine? |
|---|---|---|
| `g_paused` | 0x1a5b9c | yes in a net game (docs/ui.md P3) |
| `g_menuInputLockout` 0x41b4fc | 0x1a5ba8 | zeroed at each tick start; per machine after a menu is closed inside a tick (FINDINGS D26) |
| a dialog is open | 0x1a5bb4 | set by a message |
| camera flag of the slot (`net_getCamFlag`) | 0x1a5bc4 | yes — it is bit 0 of the slot's input record |
| object is the prediction copy | 0x1a5bd4 | by design |
| **0x41b818[slot] ≠ 0** (interact only) | **0x1a5c08** | **no — K1** |

So while the owner has a menu open nothing recomputes the stored damage on any machine (the
camera flag travels in the input), and interact is off for that player everywhere.

## 2. The kill

`Creature_takeDamage` 0x116638 subtracts hit points at once, adds the amount to +0xc8, ORs
the flags into +0x2dc, stamps +0x304, and re-links the last-attacker handle +0x2e4 (the owner
for a projectile; the timed-effect source for flag 0x10000000) — only while hit points are
still above zero, so the handle names whoever landed the killing blow. It reads no global but
the frame counter. **Observed.**

`Horsemen_run` calls `Creature_processDamage` 0x110d30 first thing each frame (0x272408,
0x2724a4). At hit points ≤ 0, in order — all **Observed**:

| Step | What | Where |
|---|---|---|
| 1 | flags 0x9; second timers clamped to 1; burn / disintegrate / ice / gib branches (docs/creatures.md C6, arena-desync.md) | 0x111478–0x111d5c |
| 2 | knock-back speed from the damage flags | 0x111d5c–0x111dd4 |
| 3 | virtual slot 27 with state 0x14 → the class's set-state (below) | 0x111de8 |
| 4 | flag 0x2000; stop here for the `Dead` property or creature flag 0x100000000 | 0x111e08 |
| 5 | sum of the players' levels (+0x59, slots below `g_numPlayers`); `xp = int(int(pow(expValue / sum, 1.4)) × 0.75)` | 0x111e40–0x111ea0 |
| 6 | killer slot: the object behind +0x2e4 compared with each record's object pointer; −1 when no player | 0x111ec4 onward |
| 7 | if a player killed: rank of skill 0x3b → a fraction; one draw from the **creature's own** generator; on success `pool_new(0xb8)` and `OniBall_ctor` (which draws the shared seed once) | 0x111f30–0x111fcc |
| 8 | one player: if alive, `player_giveExp(slot, min(xp, table[level+1] − table[level]))`; class 0 gains mana = monster max hit points / 30 — in this one-player branch whoever or whatever made the kill; no killer is needed (`docs/spec/combat.md` section 5, executed) | 0x1120e4 |
| 9 | several: share 0.6 for the killer, 0.4 for the others, 0.5 for all when nobody is the killer; halved for a player whose record hit points are ≤ 0; same cap; class-0 mana for the killer only | 0x1121e8 |

Nothing in steps 5–9 reads the local slot, a camera, an option or the alive list: only
`g_numPlayers`, record hit points, level and class, the level-step table behind the cap of
steps 8 and 9, the killer's skill list (the rank of step 7), and the handle — the last
three named after execution in `docs/issues/dynamic-tests.md` (k19), all lockstep state.
**Observed** (every global
the function reads was listed: `g_numPlayers`, `g_players`, `g_networkMode`, `g_decalDetail`,
the third generator 0x404468 for decals only).

`player_giveExp` 0x1d3150, per level gained: skill points (+0xe8) by level band, stat points
(+0xec) += 3, level (+0x59) += 1, `player_recalcStats` (0x1d3224), hit points and mana
refilled if alive. Then, on the owner's machine only, a sound (0x1d3250–0x1d327c) and the
level-up text for 360 frames (0x1d3298). **Observed.** (Sharpened by execution,
`docs/issues/dynamic-tests.md` k22: only the sound is behind the local-slot test; the
level-up message call is made on every machine, with the slot as its argument.)

**Immediate** on every machine: experience, +0x59, both point pools, maximum hit points and
mana (they use +0x59), the refill. **Waits for the owner**: +0x58 (attack rating and skill
requirements) until the owner's `hud_run` opens the inventory with the level-up flag
(0x1db870: record +0x58 < +0x59 → `menu_openInventory(slot, 1)`), which sends inventory
message 9 from 0x1c1814; and the points themselves, spent by messages 6 and 7. **Observed.**

Counters: no kill counter is touched in `Creature_processDamage`. `Creature_onDeath` calls
the arena score function only in PvP mode B (0x10bfa0). **Observed.**

### What the knight's set-state does (`Horsemen_setState` 0x272f4c, case 0x14)

1. Creature flag 0x20000000000.
2. Variant 3 only: looks up the monster-summoned skeleton by name (0x273278) and, if it is a
   creature, sends it to state 0x14 (0x2732ac). So killing knight 3 removes its skeleton in
   the same tick. *(Not in docs/monsters.md or arena-desync.md.)*
3. `Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this, position, facing, 0)` (0x273314).
4. Weapon-helper slot 11 for hand 1 and hand 2 (0x273344, 0x273374): each held part becomes
   a `PhProp` (`creature_dropHeldPartAsProp` 0x117d30), a grid-B expendable prop.
5. Death animation; virtual slot 28 (0x2733b0) → `Creature_onDeath` 0x10beb8: clears the
   follow flags, runs the `deathScript` property (0x10bf08), and for a non-quiet death
   passes the `dropitem` property to `loot_spawnNamedItem` (0x10bf54).

All inputs are object state and properties. **Observed.** In `drunare` the four knights carry
`dropitem` (two kinds of potion), a `deathscript`, no `MiniBoss`, no `noloot`.

The summoned skeleton gets experience too: its set-state queues the deletion, and steps 4–9
still run. It drops nothing. **Observed** (0x2a91b8; order in the table above).

## 3. Loot

### `Creature_dropLoot` 0x10f2c8

- Nothing when the creature has flag 0x100000000, or the `noloot` property outside PvP
  mode B.
- Eleven exact-class tests select fixed extra calls for boss classes; `Horsemen` is not one
  of them. `creature_bossRank` 0x10d940 compares the type name with a list of full names;
  the knights' type names (with a digit) match none, so rank is the `MiniBoss` flag: 0.
- A non-zero tint byte +0xa0 triples the gold scale and quadruples the quality row. No writer
  of +0xa0 exists for `Horsemen` (every byte store at that offset was listed).
- Rank 1 and 2 add calls and a per-player loop that draws the **creature's own** generator.
- For a knight: exactly one `loot_generateDrops` call with the numbers above.

Inputs: flags, properties, class, type name, `g_numPlayers`, `g_pvpModeB`. **Observed.**

### `loot_generateDrops` 0x100d54 — every roll is the shared seed 0x404464

| Roll | Draws | Creates |
|---|---|---|
| quality | 1 | — |
| number of gold rolls (1–3) | 1 | — |
| each gold roll | 2 (chance, amount) | `loot_spawnGold` 0x100974: 3 draws per scatter try, up to 10 tries, ended by a terrain-height test; `pool_new(0xc0)`; `Gold_ctor2` |
| consumable | 1, plus 1 on success | parser or `item_generateConsumable`; `pool_new(0x248)`; `PhProp_ctor` |
| reagent | 1 | generator; a success with no qualifying definition **returns from the function** |
| figurine | 1 | same early return |
| equipment | 1; on success 2 for the budget, 1–2 for the category, 1 for preset-or-random, the generator's own, 1 for the throw angle | `pool_new(0x248)`; `PhProp_ctor`; `PhProp_initPhysics` |

Other inputs: `g_numPlayers` (gold ×2.4, gold chance ×1.5, item chance ×2 with more than one
player), the two PvP flags, the quality table, `g_levelMonsterLevel`, `g_difficultyIdx`, the
players' class (+0x50) inside the generators. Every global read by this function, the six
generators, the parser, the value function and the object constructors was listed
mechanically; besides the above they read only the pool table, the terrain, the level flag
word 0x44fe08 and the cosmetic seed in `rigidbody_init`. No option, camera, language or
local-slot read. **Observed.**

Which generator: the shared seed for every roll and every `GameObject_ctor`; the creature's
own (+0x44) for the boss-rank preset choice and for the orb roll; the object's own for launch
velocity and spin; the cosmetic seed 0x404460 once in `rigidbody_init` 0x1682f0 for a
starting orientation that `PhProp_initPhysics` 0x155110 then overwrites completely
(`quat_fromMat3` writes all four components, `rigidbody_updateDerived` rebuilds the rest);
the fourth generator 0x404468 only for decals in the gib branch. **Observed.**

Conditional on a per-machine value: only the pool. Each `pool_new` that returns 0 skips the
constructor and its draws (four sites in `loot_generateDrops`, one in `loot_spawnGold`, one
in `loot_spawnNamedItem`). That is FINDINGS D21.

### The `dropitem` path

`loot_spawnNamedItem` 0x100ba0: parse the descriptor with variant −1 (one shared draw when
the definition has visual variants), `world_findFreeSpot` (three shared draws per try), then
`pool_new(0x248)` and `PhProp_ctor` 36 units up. **Observed.**

### Life of a dropped object

**Item in flight** (`PhProp` carrying an item record, 0x248 bytes). `PhProp_ctor` 0x155a0c
clears the transient and grid-B flags and sets "interactable", so it can be picked up while
it flies. `PhProp_run` 0x155fcc each frame: water test every 8th frame, gravity (0.18, or
0.054 when bit 0x100 of the level flag word is set), hull points against the terrain height,
`rigidbody_integrate`, damping ×0.95, a swept move, a landing sound chosen from item flags.
It comes to rest when its timer +0x10e is below −220, or is ≤ 0 with all six velocity
components under 0.2: then `pool_new(0x190)` and `ItemProp_ctor3` 0x1592bc copy the item
into a resting prop, and the flying object deletes itself **whether or not the allocation
succeeded** (allocation 0x156c18, constructor 0x156c4c, deletion 0x156d00). Otherwise it
deletes itself when it is 120 below the first alive player (0x156d3c, 0x156d68; FINDINGS
G19). Inputs: its own state, terrain, the level flag word, the frame counter, the alive
list, the pool. **Observed.**

**Item at rest** (`ItemProp`, 0x190 bytes): flags 0x102009 — interactable, not solid, in
grid A, not expendable; its prop flags start as "at rest", so it is on no run list. It is
never removed until picked up or the level ends. **Observed** (0x153ac0, 0x1592bc).

**Gold** (0xc0 bytes): `Gold_ctor2` 0x157668 sets a 41-frame countdown and links it to the
every-frame list; `Gold_run` 0x157b58 counts down and unlinks when the spawn animation ends.
Never removed until touched. **Observed.**

**Weapon parts** dropped by the knights are plain launched props (flags 0x1809): grid B,
expendable, converted to a `Prop` at rest; a resting prop that still has its "runs every
frame" bit sinks and is destroyed by its timer (`Prop_run` 0x154514). No box query sees
them.

The interact prompt of both item classes stamps the frame counter into prop +0x104
(0x154d34, 0x159894). The prompt is called from draw code as well as from the tick, so the
stamp is per machine; its only readers are draw functions (`Prop_draw`, `PhProp_draw`,
`ItemProp_draw`, `PushPhysicsProp_draw`). **Observed**; cosmetic.

## 4. Pick-up

Nobody "decides and announces". Both kinds of pick-up are computed by every machine inside
the owning player's `Player_run`, with no message.

**Gold — automatic, by touch.** The player's move step calls virtual slot 6 of what it
touches. `Gold_onTouch` 0x157a9c requires: toucher is not the prediction copy, countdown is
0, toucher is a player, amount ≠ 0. It calls `hud_addGoldFloater(slot, position, amount)`,
zeroes the amount and queues the object for deletion. `hud_addGoldFloater` 0x1dc268 takes one
of eight floater slots and stamps the frame counter; with all eight busy it credits record
+0xe4 at once. `hud_tickGold` 0x1dcb80 (run task) moves a floater to the per-slot pending
sum when `(frame − start) × 3 > 127`, then pays one eighth (rounded up) per frame. The camera
matrix and the cosmetic seed are used only for the drawn path and the off-screen byte.
**Observed.** Same frame, same amounts everywhere.

**Items and potions — the use button.** `Player_interact` 0x1b2640 (called at 0x1a5c1c):
box query of ±48 units around the player, nearest object with the interactable flag, its
prompt slot 13 (every frame, button or not), and on a pressed edge in the lockstep pad of
the button the prompt asked for (the slot's use button, or pad bit 0x10),
`g_scriptActivePlayer = slot` and its slot 14. For both item classes
slot 14 (0x155020, 0x159b38) calls the helper 0x154dbc (`itemprop_tryPickup` in
`symbols/killpath.tsv`):

- bag for the item's category already holds 63 items → refuse (sound);
- load limit +0x124 < load +0x120 + item weight → refuse (voice line);
- else sound, the script hook `*gotItemNotify` (no level defines it), `inventory_giveItem`
  0x1c1868, `player_recalcLoad`; the object then destroys itself directly through slot 1.

An item whose flag bit 39 is set is given to every player. `inventory_giveItem` stacks onto
an equal item when the stackable flag is set, else appends and stamps the bag index into
item +0x22, then `player_recalcStats`. Its only network-mode test turns the first-recall help
box off. **Observed.**

**Two players, same item, same frame.** Players run one after the other in run-list order,
which is shared state. The first to run takes the item and the object is destroyed on the
spot, so the second player's box query does not return it. For gold the amount is zeroed
first. Same winner on every machine. **Observed** mechanism, **Inferred** conclusion.

The one per-machine input on this path is the gate in front of `Player_interact`: K1.

## 5. Owner decides and announces, versus computed by all

Computed by all, no message: the hit and all its rolls, the kill, the experience split, the
level-up itself, every loot roll, dropped-object physics, gold pick-up, item pick-up, potion
use from the pad buttons (except K2), weapon-set swap.

Owner decides — every such step in or next to this chain:

| Step | Decision (local code) | Message | Handler |
|---|---|---|---|
| Open the inventory or the level-up screen | `hud_run` 0x1db870 (raw pad, inside the tick) → `menu_openInventory` 0x1c15c8 | game 3/2 state 1 from 0x1c173c | sets object flag 0x400000: controls locked |
| Acknowledge the new level (+0x58) | same; only when +0x58 < +0x59 | inventory 9 from 0x1c1814 | 0x1bfdb0 case 9 |
| Spend a stat point | `stats_screen` 0x1d1db8 (calls at 0x1d24d4–0x1d252c) | inventory 6 | `inventory_onStatPoint` 0x1c2548 |
| Spend a skill point | `skills_screen` 0x1d4660 (0x1d580c, 0x1d58dc) | inventory 7 | `inventory_onSkillPoint` 0x1c2648 |
| Equip / unequip | item list 0x1cdd28 (0x1ce87c, 0x1ce868) | inventory 1 / 2 | 0x1c27c0 / 0x1c2f20 |
| Drop an item | item list (0x1ceb1c) | inventory 0 | `inventory_dropItem` 0x1c4310: shared-seed free-spot search, new `ItemProp` |
| Quick-slot choice, spell assignment | `hud_spellSelect` 0x1dd270 (0x1ddc9c, 0x1ddd0c, 0x1ddcc4) | game 3/0, 3/1, 3/13 | `hud_onMsg` |
| Close the inventory | `inventory_close` 0x1c5100 | game 3/2 state 0 (0x1c5210), inventory 5 (0x1c528c) | flag cleared 10 frames later; weapon class |
| **Take a drunk potion out of the bag, when the local inventory is open** | `Player_usePotion`, tests at 0x1b9fcc (health) and 0x1ba3ac (mana) | inventory 0, mode 2, from 0x1ba050 / 0x1ba430 | `inventory_dropItem` — see K2 |

Two entries of the inventory table in docs/ui.md never occur in a game with one player per
machine: message 10 (its only sender 0x1c55e0 is unreferenced) and message 4 (sent only when
a second local player takes an idle panel, 0x1c01f4 / 0x1c021c). The message-4 handler reads
the slot for its level-up branch from this machine's own panel table (0x1c0400) rather than
from the message; that is per-machine, but unreachable without two players on one machine.
**Observed.**

## Findings

### K1. Interact is gated by a flag only the owner's HUD writes

Chain, all **Observed**:

1. `hud_spellSelect` 0x1dd270 is HUD draw code (called at the end of
   `hud_drawPlayerStatus`, 0x1dacb8, from the HUD draw task). Its first act is
   `net_isLocalSlot(slot)`; for a remote slot it returns (0x1dd2bc–0x1dd2c4).
2. It reads the held word of the slot's **raw** pad (0x4028d8 + slot × 0x58). With any D-pad
   direction held it calls `net_maskLocalButtons(slot, 3, abilityA | abilityB | use)`
   (0x1dd4b8) and stores 1 at 0x41b818[slot] (0x1dd4ec); with none held it stores 0
   (0x1dd504, 0x1dd5e4).
3. 0x41b818 is initialised data, four zero words. `hud_spellSelect` is its only writer
   (global scan including indexed access). So for a remote player's slot it is always 0.
4. `Player_run` loads 0x41b818[slot] at 0x1a5c08 and skips `Player_interact` when it is
   non-zero (0x1a5c0c). No network-mode test. The sister test further down the same
   function **does** have one: at 0x1a6de8 the flag is consulted only when `g_networkMode`
   is 0. *Inferred:* the flag is the offline way of keeping "use" from acting while the
   selector is open; the net-game way is the button mask of step 2; this reader was missed.
5. The mask removes the use button from samples taken *after* the selector was first drawn.
   A use press sampled earlier is already in the input stream and is simulated up to
   *L − 1* displayed frames later (F2).

Verdict: on the owner's machine `Player_interact` does not run for that player during any
tick that follows a HUD draw with the D-pad held; on every other machine it runs. A use
press that reaches the simulation in such a tick interacts on the other machines only. With
the minimum lead of 2 the two buttons must be pressed in the same sample; with latency the
D-pad may follow the use press by up to *L − 2* further frames (*Inferred* from F2).

What then differs: an item or potion is picked up on the other machines and stays on the
ground on the owner's (bags differ until the owner picks it up again, which repairs a
stackable potion exactly); a chest opens on the other machines only, and `Chest_interact`
0x292a2c builds its loot there and then (parser, shared-seed generators and three
`pool_new` sites, 0x292b48–0x292f7c), so the sync check fails in that tick; the same goes
for any other object whose interact changes shared state. In `drunare` the only
interactables are dropped items and the exit trigger, so there K1 produces a silent bag
difference rather than an immediate mismatch. **Inferred** from the Observed gate.

Two-machine test: add latency so the lead is large (0.3 s is enough), stand next to a chest,
press use and then hold a D-pad direction within the delay. Expected unpatched: the chest
opens on the other machine only and "OUT OF SYNC" follows at once. Same with an item on the
ground: it disappears on the other screen only.

Patch: P1.

### K2. A potion drunk while the local inventory is open is paid for differently

Chain, all **Observed**:

1. `Player_run` calls `Player_usePotion(player, kind, 0, 0, −1)` on a pressed potion button
   of the lockstep pad (0x1a5998, 0x1a59f0). The function returns for the prediction copy.
2. After adding the healing (or mana) still to be delivered to the record, it removes the
   potion: if `g_localMenuOpen` is 0, **or** the slot is not local, **or** the item-list
   buffer pointer 0x4ebbb0 is 0, it decrements the stack in the bag and removes the item at
   zero. Otherwise — owner's machine, inventory open — it changes nothing and calls
   `invmsg_sendDrop` with mode 2 (0x1ba050, 0x1ba430), taking the bag index from the cell at
   row and column given by its third and fourth arguments in the local item-list copy.
3. `inventory_dropItem` 0x1c4310, run by every machine when the message arrives, decrements
   the addressed stack on every machine; mode 2 only suppresses the sound and the dropped
   object.
4. `g_localMenuOpen` is set by `menu_openInventory` inside the tick in which `hud_run` sees
   the raw button (0x1c15c8). 0x4ebbb0 is set by the inventory's resource poll 0x1bfbc8,
   called from the inventory draw task, on its first call with the disc idle.
5. The path this branch was written for — drinking from the inventory screen through
   message 10 — has no sender (0x1c55e0 is unreferenced). The only live caller is step 1,
   with zero row and column.

Verdict: if a potion-button sample is simulated after the owner's inventory has opened and
been drawn once, the owner's machine keeps the chosen potion and sends a message that
removes one of whatever sits in the first cell of its potion list; the other machines remove
the chosen potion and then execute the same message. The owner's record and the others' then
disagree by one potion. The window is: inventory button pressed in the same displayed frame
as the potion button or up to *L − 2* frames after it (*Inferred* from F2). The message's
last byte is the −1 passed in step 1; in `inventory_dropItem` it indexes the owner's local
item-list arrays (*Inferred* out of range, local memory only).

A potion count that differs changes which potion a later press picks, or whether one exists,
and from there hit points.

Two-machine test: with added latency press a potion button and at once the inventory button;
compare the stack counts in bag 2 of that player's record (record +0x2540, 0x48 per item,
count at +4) on both machines.

Patches: P2a, P2b.

### K3. The stats page rewrites the record's stored damage

`stats_screen` runs in a draw task on the machine showing the page (it is also the level-up
page). Each displayed frame it calls `Player_recalcDamage(object, primary weapon of the
active set, 1)` (0x1d2c38) to print attack and damage, and for a player with a second
weapon and set 0 active a second time with the off-hand weapon (0x1d2d30). The function
stores into record +0xcc, +0xd0, +0xd4. **Observed.**

The first call has the same arguments as the per-tick call in `Player_weaponSwapInput`, so it
writes what a tick would. The second leaves the off-hand values in the record until the next
tick recompute, and with the menu open there is none on any machine (camera flag). Melee
recomputes inside `Player_meleeHit`; arrows and throws use the stored values but cannot be
started with the menu open. What remains is code that reads the stored values while the
owner sits in the menu: the fire, cold and poison arrow hit functions take the shooter's
record range by address (0x2d6aa0, 0x2d7cfc, 0x2d949c), and a few skill casts read +0xd0 /
+0xd4. A dual wielder holds no bow, so a route needs a second-weapon player with such a
spell still active. **Inferred** unlikely.

Test: dual-wield character, open the stats page, compare record +0xd0 / +0xd4 on both
machines while it is open. Patch: P3.

### K4. Menu draw code recomputes every player's derived statistics

`player_recalcStats` 0x1b6458 takes no argument and loops over all players. For each it
rebuilds the effective statistics from base plus item modifiers 7–10, the stagger resistance
sum, the four bonus bytes at object +0x474, armour (object +0xe4) and resistances (object
+0x5c…+0x6c, zeroed and re-summed by `player_recalcArmor` 0x1b5790), the load limit, maximum
hit points and mana, and clamps hit points and mana to the maxima. `stats_screen` calls it at
its end every displayed frame (0x1d2e7c); `skills_screen` and the item list call it too.
**Observed.**

It is a pure function of record state, so an extra call changes nothing as long as every
lockstep change of its inputs is followed by a lockstep call. Checked: level-up, stat point,
give / remove / drop / equip / unequip all call it. The legacy passive code in
`player_rebuildAbilities` 0x1d34ac that bumps maximum hit points or mana directly (masks 0x80,
0x100) is unreachable: no class tree contains those masks (trees at 0x4f4898…0x4f5a18 read).
The load-limit passive (mask 0x40) is bumped by the same amount the formula gives. The timed
weapon enchantments that `Player_tickEnchantTimers` removes without a recompute are ids
0x15–0x18 and 0x26, which this function does not read. No writer of object +0xe4 exists for
players other than this function. **Observed** for each; **Inferred** harmless. Not checked:
whether any spell writes a player's resistance floats directly (it would also be wiped by
every pick-up, so *Inferred* no).

### K5. Loot against the alive list and the pool

Nothing new in mechanism; listed because it sits on this chain.

- `PhProp_run` 0x156d3c and `Prop_run` 0x154850 delete a moving prop when it is
  120 below the object of `g_alivePlayers[0]`. If the list is wrong on one machine for a
  tick (G11–G13) and the first alive slot differs, an item in flight can be deleted on one
  machine. Flat floor in `drunare`: no.
- Pool: see section 3. A lost landing conversion removes the item itself.
- FINDINGS D26 has one more consequence: the lockout word is also tested at 0x1a5ba8, so in
  the tick in which a machine closes a local menu from inside the simulation, players that
  run later in that tick skip the weapon recompute and interact on that machine only.

## Ranked list: what could put two machines out of sync in an ordinary fight with kills and drops

1. **K1** when a chest (or another object whose interact draws the shared seed) is in reach:
   immediate mismatch.
   With only dropped items in reach (the arena) a silent, usually self-repairing bag
   difference. Needs use-then-D-pad inside the input delay.
2. **K2**: a potion count that differs for good. Needs potion-then-inventory inside the input
   delay; a level-up invites exactly that inventory press.
3. **G11–G13 / G19** (not new): a wrong alive list for part of a tick; on this chain it can
   delete flying loot and changes the AncestralCall and critical-aura scans of a hit.
4. **K3**: second-weapon player with the stats page open and a record-reading spell active.
5. **D21** (not new): a failed `pool_new` on one machine drops a loot object and its draws.
6. **K4**: none found; kept as the place to look if a derived statistic is ever seen to
   differ.
7. Status counters 8 and 10, set by the kill orb (`OniBall_ctor` 0x2940e8, 0x2940f8; touch
   0x294800, 0x294844), are decremented by drawing and so differ per machine; they are read
   only by drawing (FINDINGS D15).

None of these happens on every run. For the arena, the kill → experience → loot → pick-up
chain can be taken off the list of every-run suspects, with K1 and K2 as the two places where
a particular sequence of presses breaks it.

## What to record on two machines

| Observation | Points to |
|---|---|
| Mismatch in the tick a chest or container is opened, opener had the D-pad down | K1 |
| An item lies on one screen and not on the other | K1 |
| 0x41b818 + 4 × slot non-zero on the owner's machine at the mismatch | K1 |
| Potion counts of one player differ between machines before the mismatch | K2 |
| Mismatch with no pick-up, no potion and no menu for many seconds before it | not this chain |

## Patch proposals (all untested)

One change each. PCSX2 form: `patch=1,EE,<address>,word,<new>`. Original words were read from
the executable.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| P1 | 0x001a5c0c | 54600006 | 00000000 | The branch that skips `Player_interact` when 0x41b818[slot] is set becomes a no-op: interact is called for every player on every machine. In a net game the owner's own use presses are still masked out of the input while the selector is open | Offline, pressing use with the selector open now also interacts with whatever is in reach | Each machine protects its own player; a mix is safe (a patched machine does what remote machines already do) |
| P2a | 0x001b9fcc | 8043b69d | 00001821 | The load of `g_localMenuOpen` in the health-potion branch reads as 0: the potion always leaves the bag directly, no drop message | The owner's open inventory screen may show the old count until reopened | Same as P1 |
| P2b | 0x001ba3ac | 8043b69d | 00001821 | The same for the mana-potion branch | Same | Same as P1 |
| P3 | 0x001d2d30 | 0c06dc56 | 00000000 | The stats page no longer recomputes for the off-hand weapon, so the record keeps the primary weapon's values | The second damage range printed on the stats page repeats the first | Each machine for itself; a mix is safe |

## Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| new | The kill chain is lockstep: experience uses only the player count, record levels, record hit points and the last-attacker handle (and, added after execution in `docs/issues/dynamic-tests.md` k19, the record's class, the level-step table and the killer's skill list — all lockstep); every loot roll draws the shared seed; gold is taken by touch and items by the use button inside the taker's own `Player_run`, with no message | Observed | 0x111e40–0x1121e8; 0x100d54; 0x157a9c; 0x1b2640, 0x154dbc |
| new | `Player_run` skips `Player_interact` while 0x41b818[slot] is non-zero; only `hud_spellSelect`, HUD draw code that returns for remote slots, writes it (D-pad held). A use press already in the input stream therefore interacts on the other machines only | Observed (gate, writer); Inferred (window) | 0x1a5c08–0x1a5c1c; 0x1dd2bc, 0x1dd4b8, 0x1dd4ec, 0x1dd504, 0x1dd5e4; contrast 0x1a6de8 |
| new | `Player_usePotion` leaves the bag untouched on the owner's machine when its inventory is open and sends a drop message instead; other machines decrement and then also run the message | Observed | 0x1b9fcc–0x1ba050, 0x1ba3ac–0x1ba430; 0x1c4310 |
| new | Menu draw code writes player records: `stats_screen` → `Player_recalcDamage` (+0xcc, +0xd0, +0xd4) and → `player_recalcStats` for all players; `skills_screen` and 0x1cdd28 → `player_recalcStats`; `hud_spellSelect` → +0x4a74, +0x4a78 | Observed | 0x1d2c38, 0x1d2d30, 0x1d2e7c, 0x1d5950, 0x1ce530, 0x1dd4f8 |
| new | A level-up changes +0x59, both point pools, maxima and the refill at once on every machine; the attack-rating level +0x58 follows by inventory message 9, sent when the owner opens the level-up screen | Observed | 0x1d3150; 0x1db870; 0x1c1814; 0x1b7158 |
| new | When knight variant 3 dies its set-state sends the summoned skeleton to the death state in the same tick | Observed | 0x273278, 0x2732ac |
| new | A flying item's landing conversion deletes the flying object even when the allocation of the resting prop failed | Observed | `PhProp_run`: 0x156c18, 0x156c4c, 0x156d00 |
| D26 (add) | The lockout word also gates the per-tick weapon recompute and interact | Observed | 0x1a5ba8 |

## Corrections to earlier documents

- docs/ui.md P4 says everything the item, stat and skill screens change goes through
  messages. `stats_screen` and `skills_screen` call `player_recalcStats`, and `stats_screen`
  calls `Player_recalcDamage`; both write records (and objects) directly. The scan behind
  that statement looked for direct stores, not calls.
- docs/ui.md, inventory channel: message 10 has no sender; message 4 is sent only for a
  second local player.
- docs/player.md lists potion use as "guarded against the copy". True, but the removal of
  the potion has a second, per-machine branch (K2).
- docs/gameplay.md §9 asks what the descriptor is embedded in: for a melee hit it is the
  weapon's item record itself; the effect slots are the item's modifier slots.
- docs/monsters.md, Horsemen: case 0x14 of the set-state also kills the summoned skeleton
  for variant 3, and drops both held weapon parts.
- docs/issues/arena-desync.md, "Other ways out of the world", should add the same.

## Not done

- The virtual calls inside `damage_apply` for a type-0x29 proc (which skill, and who writes
  a 0x29 modifier into an item — the parser does not) and victim slot 30 were not read.
- The other implementations of interact (slot 14) and of the prompt (slot 13) — containers,
  NPCs, save points, levers, vehicles — were not read for K1's consequences; for `Chest`
  only the calls its interact makes were listed.
- `inventory_equipItem` was scanned for per-machine reads (it reads this machine's panel
  table only to choose a notice flag), not read line by line.
- Whether any spell writes a player's resistance floats or maxima directly (K4).
- The character checksum 0x1bdc98 covers at least experience, gold, both level bytes and
  the effective statistics (first part of the function read); when it is exchanged, and
  whether K2 would show as a checksum failure instead of a sync error, was not followed.
- `rigidbody_integrate` and the terrain helpers were taken as pure functions of their
  arguments; their bodies were not read.
- `Player_processDamage` (the victim side of a monster's hit) was not re-read here; its
  three local-slot tests were only seen to set the prediction-rebase flag.
- The item list code 0x1cdd28 (third caller of `player_recalcStats`) was not read.
