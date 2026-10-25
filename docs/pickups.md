# Chests, world items, pickup, and inventory drop (SLUS-20973 v2.00)

Research date: 2026-10-23. This is a native-port handoff, not a claim of a
playable chest-to-inventory path. Addresses below are for the pinned US v2.00
executable (SHA-256 `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`).
**Observed** means read in the original code at the cited address; **Executed**
means a function ran in `tools/ee_emu.py` on synthetic state. The new probes
stub called services and do not execute an integrated level, renderer, physics
world, or inventory UI.

The 2026-10-24 [loot-drop continuation](loot-drop.md) supplies the construction,
physics-input, disc-backed resource/animation, normal Gold contact and starting
equipment contracts that this first handoff left open. Its runtime limits remain
explicit; it does not claim a native or PCSX2 level acceptance result.

## 1. Interaction gate and proximity

**Observed** (`Player_run` 0x1a5b98–0x1a5c20, `Player_interact`
0x1b2640; [kill-loot-xp](issues/kill-loot-xp.md) section 4): while the player
can act, `Player_interact` queries x/y ±48 and z..z+60 around the player,
chooses the nearest object with the interactable bit `0x100000`, calls its
virtual prompt slot 13, and on the matching lockstep pad edge calls slot 14.
The prompt is checked even without a press. A script-active-player slot is set
before the interaction. The use input is manual for chests and item props;
the nearby item is not automatically transferred. `Player_run`'s local HUD
selector byte at 0x41b818 can skip this call on the owning machine (K1 in
that issue); native input parity must retain the existing K1 decision rather
than assume every locally visible prompt can be activated.

Gold uses the player's movement/touch callback rather than this ±48 prompt
query (`Gold_onTouch` 0x157a9c). The initial probes left its geometry unknown.
**Observed / Executed in the continuation:** Gold retains radius 24/height 72
from 0x14cb10; player radius 12 is stored at 0x1a2244. Original movement
requires horizontal distance plus float bits 0x3a83126e below the radius sum
(36 for these objects), after the movement box query. This is not a proximity
sphere; see [the original grid/contact and vertical checks](loot-drop.md#6-gold-source-amount-contact-and-actual-credit).

**Observed/Executed** (`Chest_interactPrompt` 0x29297c–0x292a2c;
`tools/difftest_pickups.py` on seeds 20973/7): unopened chests show
`OpenChest`; opened chests with positive remaining gold show `PickUpGold`
formatted with that amount. An opened, zero-gold chest still returns a true
prompt status without requesting text or formatting, but the object's
interactable flag controls reachability. These are direct synthetic-state
prompt calls, not proof that the prompt reaches a player in a level.
`ItemProp` prompt and interact are virtual slots 13/14 at 0x159870 and
0x159b38; the flying `PhProp` item uses slot 14 at 0x155020.

## 2. Ordinary Chest state and loot

**Observed** (`Chest_interact` 0x292a2c–0x2931bc; `Chest_run`
0x2923a8–0x29288c; [monsters](monsters.md) section 5): first use pushes
the opening animation (`anim_push` 0x170838, flags `0x204`), sets +0x84 to 1,
requests every-frame running (`obj_runEveryFrame` 0x14f248), and stamps +0x50
with `g_simFrame` 0x44fdcc. If +0x4c gold is zero or negative, it clears
interactable bit `0x100000` at +0x0c. The item sequence is the chest's placed
`item` descriptors, `potions`, placed `random` worth entries, then one
`loot_generateDrops` 0x100d54 call. That Chest call passes zero gold scale
and chance at 0x2930d0–0x293120 (both zero in the recorded call on seeds
20973/7), so it is an item roll. The chest's +0x4c gold is a separate
second-use award, not an item placed in a bag. Named,
consumable and equipment items become flying item props. Second use sets
hide mask +0x54 to 1, calls `hud_addGoldFloater` 0x1dc268 for the interacting
slot and remaining amount, and zeroes +0x4c. `Chest_run` advances the lid
animation. With completion bit `0x80` at +0x62, it sets state +0x84 to 2,
runs action scripts and leaves the run list. Trap choice +0x58 can route the
run to a timed explosion; this probe does not execute that path.

**Executed** (`tools/difftest_pickups.py`, both seeds): with no placed item,
potion or random properties and called services stubbed, opening at frame 100
made exactly one animation push, run-list request and generator request;
the generator's gold scale and chance arguments were both zero;
state became 1. Zero chest gold cleared the interactable bit, positive gold
kept it. A second interaction with nine gold made one HUD floater request,
zeroed gold and set hide mask 1. A non-trapped completed lid made one action
script call and one run-list removal, with state 2. These are bounded branch
checks, not a check of animation playback, trap timing or generated loot.

**Observed/Executed upstream:** `t3/research-save-world` at `e7d8972`,
`docs/save-world.md` rows Opened chests/Dropped items: `Chest_saveState`
0x292284 writes exactly 12 bytes: hide mask +0x54, gold +0x4c, choice bytes
+0x58/+0x59, opened state +0x84. It does not serialize descriptor properties;
saved spawned items have their own records. Its synthetic writer/reader cases
do not establish all load-side animation, flag or callback effects, so those
remain **Unknown**. `AutoChest` has a distinct 12-byte payload and must not be
decoded as an ordinary Chest.

`AutoChest` is another family. **Observed** ([monsters-2](monsters-2.md)
section 9.2): `AutoChest_interact` 0x23b894 transitions closed +0xd8=0 to
opening 1 and schedules +0xe8; the later `AutoChest_run` 0x23b170 calls
`AutoChest_dropLoot` 0x23ba3c at 0x23b674, after the lid reaches its threshold.
Its placed `spawncreep`, `item`, `potions`, and `random` parameters and default
three generator calls differ from Chest. `AutoContainer_run` 0x23e430 has its
own inline loot. **Ran upstream:** `t3/research-campaign-combat` at `328b072`
captured `AutoContainer_run` Gold creation at frames 1723 and 1795, followed
by touch and delayed HUD credit; that Gold did not come from the WarBoar kill
(`docs/issues/campaign-combat-handoff.md`, research round 8). This handoff
does not equate a regular Chest, AutoChest and AutoContainer.

## 3. World item lifetime and pickup

**Observed** ([items spec](spec/items.md) section 8 and
[kill-loot-xp](issues/kill-loot-xp.md) sections 3–4):

| Stage | Original address | Contract and loss boundary |
| --- | --- | --- |
| Generated loot | `loot_generateDrops` 0x100d54; `loot_spawnGold` 0x100974 | Shared-seed quality, gold and item rolls; Gold scatter checks terrain and can fail allocation. `tools/ref_items.py` / `tools/difftest_items.py` compare records, roll order and ending seed. |
| Named item | `loot_spawnNamedItem` 0x100ba0 | Parses a descriptor, searches a free spot, allocates a 0x248-byte `PhProp`; a missing pool block loses the object. |
| Flying item | `PhProp_ctor` 0x155a0c; `PhProp_run` 0x155fcc | Item record at +0x148; interactable during flight. Gravity, terrain/sweep, water and damping settle it. On the rest condition it allocates a 0x190-byte `ItemProp` via 0x1592bc; the flying object is deleted even if this allocation fails (0x156c18–0x156d00). It can also be culled far below the first alive player. |
| Resting item | `ItemProp_ctor3` 0x1592bc; `ItemProp_interact` 0x159b38 | In grid A and off run lists; stays until accepted pickup or level teardown. The world item carries a 0x48-byte item record. |
| Gold | `Gold_ctor2` 0x157668; `Gold_run` 0x157b58; `Gold_onTouch` 0x157a9c | 41-frame spawn countdown; automatic player touch only after it reaches zero, with nonzero amount and no prediction copy. Touch requests a HUD floater and deletes the Gold object. The floater credits record +0xe4 later (`hud_tickGold` 0x1dcb80). |

**Observed** (`itemprop_tryPickup` 0x154dbc–0x155020): both flying
`PhProp_interact` 0x155020 and resting `ItemProp_interact` 0x159b38 use the
same helper. It refuses when the destination category bag has **63** items
already (at 0x154e10–0x154e1c), even though `inventory_giveItem` alone can
fill cell 64. It also refuses when current load + item weight exceeds limit
(0x154e54–0x154e70). On success it plays a material sound, runs
`*gotItemNotify`, calls `inventory_giveItem` 0x1c1868, and recalculates
load. The caller removes the world object after a successful pickup. Item
flag bit 39 changes the caller to try every player; the object is removed if
any player accepts it.

**Executed** (`tools/difftest_pickups.py`, both seeds): category count 62
accepted, count 63 refused, load 90 + weight 11 at limit 100 refused,
and 90 + 10 accepted. Success made one give-item and load-recalculation
request; refusal made neither. A two-player `ItemProp_interact` with player 0
full and player 1 eligible gave only to player 1 and invoked the object's
destructor once, with and without the shared-item bit. With both players
eligible and player 1 chosen, the ordinary item gave only to player 1, while
bit 39 gave to players 0 then 1; each path invoked one destructor. World grid
removal and inventory mutation are stubbed here; `tools/difftest_messages.py` executes
`inventory_giveItem` itself.

**Observed** (`inventory_giveItem` 0x1c1868; [game messages](spec/game-messages.md)
section 5.1): the definition category selects one of three 64-cell bags.
Stackable records merge into the first equal definition/flags/prefix/suffix
record. Nonstackable records append at the bag count and stamp their bag index
at +0x22; two named single-copy entries can be refused. The function returns
an index or -1 and recalculates derived player state. `itemprop_tryPickup`
does not check the returned index. Thus the helper's count/load gates and
`inventory_giveItem`'s unique-item refusal are separate: an accepted pickup
can delete its world object even if the inventory call returns -1. A live
integrated probe of that combination remains **Unknown**. Script gifts have
another unchecked -1 path (`t3/research-items` at `49bc578c`,
`docs/script-items.md` section 2.4); that branch can lose the item.

**Observed/Executed upstream:** the save-world branch stores an `ItemProp`
item record plus its variable `Prop` suffix in its object record; it is
separate from the bag item. Exact load-side effects for all prop-state branches
remain **Unknown** (`docs/save-world.md`).

## 4. Inventory-to-world drop

**Observed/Executed upstream** ([game messages](spec/game-messages.md)
section 2 type 0; `tools/ref_messages.py` / `tools/difftest_messages.py`):
the local inventory sends message 0 via `invmsg_sendDrop` 0x1c59d0. Every
machine handles it through `invmsg_dispatch` 0x1bfdb0 into
`inventory_dropItem` 0x1c4310. For mode 0, it removes one item, or up to 20
ammunition/thrown units, from the bag's record; asks `world_findFreeSpot`
0x14acf8 for a point near the player (radius `0x30`, clearance `0xc`);
allocates a 0x190-byte `ItemProp`; then sets dropped stack quantity +0x14c
to the taken count. A fully depleted bag entry is removed, equipment and local
grid-copy pointers are repaired, and load/stats are recalculated. Mode 1 is
shop sale; mode 2 and above remove silently without placing a world item.
The original can consume the inventory item when pool allocation fails; port
that loss only with the matching pool policy and recorded refusal behavior.

The native `Machine::drop_item` in
`native/src/messages.cpp` of the Godot repository (branch `codex/playable-integration`)
currently requires `world_findFreeSpot` to return a typed position before
`ItemProp_ctor2` can run. Its `messages_tests.cpp` explicitly verifies an
`Unsupported` refusal when a position is unavailable, after `pool_new` was
called. That is a **native integration boundary**, not evidence of a world
object placed in a real level. The source and test were inspected read-only;
this research branch changes neither native implementation nor its tests.

## 5. Ordered native port and acceptance list

1. Expose the real-level object query and pad-edge path to `Player_interact`:
   ±48 query, nearest interactable, prompt slot 13, then slot 14 on use.
   Keep the known K1 input gate explicit. Preserve the ordinary Chest prompt's
   closed, opened-with-gold, and opened-with-zero-gold branches.
2. Represent ordinary Chest, AutoChest and AutoContainer as distinct states.
   Port their own opening, action, trap and loot timing, including the ordinary
   Chest's zero gold scale and chance at its generator call; restore each saved
   payload with branch-specific executable evidence before claiming parity.
3. Connect shared/own RNG, item definition tables and the verified
   `ref_items` generator to terrain/free-spot placement, bounded pool
   allocation and concrete `PhProp`, `ItemProp` and `Gold` objects. Preserve
   the original order of draws and documented allocation-loss points.
4. Tick flying-item settle/conversion and Gold countdown/touch in world order.
   Implement manual item pickup and automatic Gold touch as separate paths.
5. Give a successful item through the correct bag/stack/weight rules. Test
   62/63/64 cells, exact load limit, unique-item refusal, and shared items
   with both players eligible and a chosen slot. Test deletion against a real
   object registry. Credit Gold through the HUD
   floater timing and also test the eight-floater-full case.
6. Supply a real typed `world_findFreeSpot` result and `ItemProp_ctor2` world
   registration to native inventory mode-0 drop; test stack decrement,
   equipment pointer repair, refused placement and pickup of the dropped
   object. Keep shop/silent modes separate.
7. Verify a chest-to-world-to-bag path and an inventory-to-world-to-bag path
   in a real level, including save/reload of still-present items. The bounded
   difftests here cannot supply that acceptance evidence.

## Verification and reproduction

All runs set `PYTHONDONTWRITEBYTECODE=1` and use the pinned private executable
by absolute path, read-only. `tools/difftest_pickups.py` builds only synthetic
state; it never writes game bytes or raw disassembly to tracked files. Run it
with `--seed 20973` and `--seed 7`. Relevant existing checks are
`tools/difftest_items.py` filtered for `loot`, `gold`, and `named` with
`--quick --jobs 1`; `tools/difftest_messages.py --quick --steps 1000`;
the save-world branch's `tools/difftest_save_world.py`; and the full
`python3 -m unittest discover -s tools -p 'test_*.py'` suite.

The 2026-10-23 serial background run passed with zero failures:

| Check | Seed 20973 | Seed 7 |
| --- | ---: | ---: |
| Initial bounded pickup/chest probe | 11/11 cases | 11/11 cases |
| Existing `difftest_items.py -k loot` | 5/5 properties, including 150 generator calls | 5/5 properties, including 150 generator calls |
| Existing message difftest, 100 messages in each run | 44/44 properties | 44/44 properties |
| Save-world difftest | Chest 16, ItemProp 16 plus body/reload and other object cases passed | Same cases passed |

The explicit `-k gold` and `-k named` reruns also passed (one property each
per seed); both were already included by `-k loot`. After the audit fix, the
expanded pickup difftest passed **17/17** cases on each seed, and the full
repository unit suite passed **652/652** in a serial background run. Logs and
the initial serial runner remain ignored under this worktree's `local/`; no
executable or derived game bytes are committed.
