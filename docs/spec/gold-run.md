# The gold pile's frame and pickup down to the credit, and the item props' pickup

US `SLUS_209.73` v2.00. Prose of `tools/ref_gold.py`. The comparison is
`tools/difftest_gold.py`; the synthetic tests are `tools/test_ref_gold.py`.
Written 2026-10-21 for item 2 of `docs/spec/full-placement.md` §6.5 ("`Gold_run`,
`Gold_onTouch`; the item props' run and pickup").

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, the cosmetic seed `0x404460` with its draw count, and every result. **Observed**:
read at the address. **Inferred**: follows from those. Nothing here ran on a console, in
PCSX2 or on the live rig.

## 1. In brief

- A gold pile is touched, not used. `Gold_onTouch` takes it when the toucher is a player
  (object flag `0x40`), is not the prediction copy (`0x20000`), the pile's countdown is 0
  and its amount is not 0. **The whole amount goes to the toucher's slot** (its object
  `+0x3c8`). Nothing on the gold path reads `g_numPlayers` or splits. *Executed*.
- **The credit is deferred.** The touch fills one of eight HUD floaters with (amount,
  slot, frame). 43 ticks later `hud_tickGold` moves it to a per-slot pending sum, which is
  then paid into `g_players[slot] +0xe4` at (p + 7) >> 3 a tick. With all eight floaters
  busy the amount is credited at once. Both paths cap the gold at 99,999,999. *Executed*.
- The timing uses only `g_simFrame`. The floater's screen path uses this machine's camera
  `g_viewProj` `0x44f140` and **one cosmetic draw** (`0x404460`). The off-screen byte and
  the path are never read by the credit. **No shared draw anywhere on the pickup path.**
  *Executed*.
- The pile's own frame (`Gold_run`) is a 41-tick countdown that only gates the pickup.
  *Executed*.
- Items are taken with the use button. Slot 14 of `PhProp` (in flight) and of `ItemProp`
  (at rest) is the same code. It calls `itemprop_tryPickup`, which refuses on a bag of 63 or
  on weight, and otherwise gives the item. *Executed*.
- A loot item that came to rest (`ItemProp_ctor3`) has **no per-frame body**: it never
  joins the run list. *Executed*.
- An item dropped from the bag or given at full load (`ItemProp_ctor2`, launch 0 at every
  call site) runs `Prop_run`:
  - it falls and slides;
  - after 180 ticks it stops running;
  - it is deleted at once if it lies 120 below the first alive player.

  *Executed*.

## 2. How it was run

These bodies run for real:

- the ten pickup bodies: `Gold_run` `0x157b58`, `Gold_onTouch` `0x157a9c`,
  `hud_addGoldFloater` `0x1dc268`, `hud_tickGold` `0x1dcb80`, `hud_flushGold` `0x1dc5f4`,
  `itemprop_tryPickup` `0x154dbc`, `PhProp_interact` `0x155020`, `ItemProp_interact`
  `0x159b38`, `PhProp_interactPrompt` `0x154d10`, `ItemProp_interactPrompt` `0x159870`;
- the item constructors: `ItemProp_ctor3` `0x1592bc`, `ItemProp_ctor2` `0x1590ec`,
  `Prop_ctorNamed` `0x153ac0`, `item_getResourceIndex` `0x1083f8`, and the frame of a
  launched `Prop`/`ItemProp`, `Prop_run` `0x154514`;
- under them, already executed elsewhere: `mat4_transformPoint` `0x165ee0` and
  `mat34_setPosRotZ` `0x163b30` (`tools/difftest_core.py`); `Gold_ctor2` `0x157668`,
  `Prop_ctorNamedLaunch` `0x153e54`, `Prop_launch` `0x1541a0` (`tools/difftest_phprop.py`);
  `GameObject_ctor` `0x14cb10` and `GameObject_rand` `0x1509d0`; `libc_strcpy`.

`libc_sprintf` is a stub that records (format, value), or (format) for a format without a
conversion, and writes the text the library would write. Every other callee is a recording
stub, answered by the same seeded script on both sides. Two stubs act on memory:

- `anim_advanceUnitSpeed` sets bit `0x80` of the anim state's `+6` (pile `+0x5e`) in 8 % of
  calls, as a clip's end would;
- `player_itemWeight` answers a float in `f0`;
- `terrain_sweepCircle` answers a fraction in `f0` and writes a normal to its out vector.
  `terrain_heightBelow` answers a height near the prop's z, or −1e9.

Entries (one call each, unless marked as a sequence):

| Entry | What it varies |
|---|---|
| goldRun | countdown 0, 1, 0x29, negative; `+0x50` equal to frame − 18 or not; the clip-end bit before the call and from the anim stub |
| goldTouch | toucher flags: player, prediction copy, monster, random; countdown; amount 0; floaters free or all busy; gold near the cap |
| floater | random cameras and positions; 40 % on the off-screen edges (w 19.99–250, \|x\| 699.5–710 w, \|y\| 299.5–310 w) |
| tickGold, flushGold | floaters with start frames around the 43-tick edge, slot bytes 0–3 and −1; pending sums including negative ones |
| tryPickup | bag counts around 63, load against limit (equal included), every sound flag |
| phInteract, itemInteract | item flag bit 39 or not, `g_numPlayers` 0–4, every slot's record |
| phPrompt, itemPrompt | stack counts 0, 1, 2, 3, 99, −1, −32768, 32767 |
| itemCtor3, itemCtor2, propNamed | dirty or zeroed blocks, variant rows (bit 36), bit 39, every prop flag and launch mix |
| propRun | `Prop_run` on dirty props: moving or at rest, prop flag 2, life around 0, −60 and −300, spin around 10, slides and bounces; 30 % on the 120-below edge |
| **pile** (sequence) | the real `Gold_ctor2` on a zeroed block at frame F; N ticks of `Gold_run` (`g_simFrame` stepped); one or two touches (player, copy, monster); M ticks of `hud_tickGold`; sometimes `hud_flushGold` |
| **itemLife** (sequence) | `ItemProp_ctor3` on a zeroed block; 1–5 ticks of the prompt; `ItemProp_interact` |
| **dropLife** (sequence) | `ItemProp_ctor2` (launch 0 mostly) on a zeroed block; 1–400 ticks of `Prop_run`; `ItemProp_interact` |

In 75 % of the pile cases nothing is pending and no floater can fall due during the case,
so the payout of this one pile can be measured.

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_gold.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_gold.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_gold.py      (22 tests)

| | Seed 20973 | Seed 7 |
|---|---|---|
| Cases (3,000 per entry, 1,000 piles) | 49,000 | 49,000 |
| Mismatches (calls, writes, seeds, results, faults) | 0 | 0 |
| goldTouch: taken / credited at once (all floaters busy) | 652 / 272 | 653 / 283 |
| pile: taken / floater filled / direct credit | 504 / 357 / 147 | 473 / 344 / 129 |
| pile, clean: paid in full / partly / not yet / capped | 154 / 125 / 65 / 13 | 144 / 110 / 73 / 10 |
| pile: drop sound / clip end stopped it | 224 / 794 | 176 / 777 |
| tryPickup: given / refused (bag) / refused (load) | 1,019 / 1,156 / 825 | 1,042 / 1,111 / 847 |
| phInteract: given to 1, 2, 3, 4 players | 1,005, 222, 53, 7 | 1,033, 206, 57, 3 |
| itemCtor3 calls to `obj_runEveryFrame` | 0 of 3,000 | 0 of 3,000 |
| propRun: stopped / slot-1 delete / 120-below delete / swept | 750 / 238 / 764 / 1,141 | 721 / 221 / 786 / 1,147 |
| dropLife: stopped running / 120-below delete / picked up | 2,078 / 503 / 1,194 | 2,109 / 476 / 1,156 |
| Shared draws | 1 per pile, item and prop construction; 0 elsewhere | the same |
| Cosmetic draws | 1 per filled floater | the same |

Coverage, the same on both seeds:

| Function | Address | Executed |
|---|---|---|
| `Gold_run` | `0x157b58` | 43 of 43 |
| `Gold_onTouch` | `0x157a9c` | 47 of 47 |
| `hud_addGoldFloater` | `0x1dc268` | 227 of 227 |
| `hud_tickGold` | `0x1dcb80` | 62 of 62 |
| `hud_flushGold` | `0x1dc5f4` | 69 of 69 |
| `itemprop_tryPickup` | `0x154dbc` | 153 of 153 |
| `PhProp_interact` | `0x155020` | 58 of 58 |
| `ItemProp_interact` | `0x159b38` | 58 of 58 |
| `PhProp_interactPrompt` | `0x154d10` | 43 of 43 |
| `ItemProp_interactPrompt` | `0x159870` | 43 of 43 |
| `ItemProp_ctor3` | `0x1592bc` | 103 of 103 |
| `ItemProp_ctor2` | `0x1590ec` | 116 of 116 |
| `Prop_ctorNamed` | `0x153ac0` | 114 of 114 |
| `item_getResourceIndex` | `0x1083f8` | 15 of 15 |
| `Prop_run` | `0x154514` | 234 of 234 |
| `Gold_ctor2` (in the pile) | `0x157668` | 59 of 59 |

Mutation checks (`--quick`, `PYTHONDONTWRITEBYTECODE=1`, model restored after each). Each
change below was detected:

- `Gold_run`'s sound frame 0x11 instead of 0x12: goldRun calls 100, pile calls 16.
- The credit delay 0x7e instead of 0x80: tickGold writes 114, pile writes 17.
- 704.0 instead of 700.0 (`0x44300000`): floater writes 9.
- 302.0 instead of 300.0: floater writes 8.
- 21.0 instead of 20.0: floater writes 4.
- The bag limit `< 0x3f` instead of `< 0x40`: tryPickup calls 47, results 25; phInteract 49;
  itemInteract 53.
- The item flags mask `0xffffefff` instead of `0xffffe7ff`: itemCtor3, itemCtor2, itemLife
  writes 300 of 300.
- The variant field `& 0x0f` instead of `& 0x1f`: itemCtor3 writes 14, itemCtor2 8.
- Prop flags `| 3` instead of `| 1`: itemCtor3 calls and writes 300 of 300.
- `Prop_run`'s gravity `0x41d80000` instead of `0x41d7ffff`: propRun calls 2, writes 171.
- The sink threshold −61 instead of −60: propRun writes 14.
- The 121.0 instead of 120.0: propRun calls 43.
- The spin decay 9 instead of 10: propRun writes 150.

The delay 0x81 is **not** a detectable change: `3d ≥ 128` and `3d ≥ 129` both mean d ≥ 43,
since no multiple of 3 is 128.

## 3. The pile's fields

Built by `Gold_ctor2` (`docs/spec/gut-chunk.md` §7b): a 0xc0-byte `GameObject` with table
`0x511a88`.

| Offset | Width | Meaning | Written by | Read by |
|---|---|---|---|---|
| `+0x0c` | u32 | object flags; `0x220c` added by the ctor | ctor | — (the touch reads the **toucher's**) |
| `+0x10`–`+0x18` | 3 × f32 | position | ctor | `Gold_onTouch` (copied for the floater), `Gold_run` (passed to the anim step) |
| `+0x1c` | f32 | radius 24.0 (from `GameObject_ctor`) | ctor | the touch dispatch (§7) |
| `+0x4c` | s8 | the countdown, `0x29` = 41 | ctor; `Gold_run` | `Gold_run`, `Gold_onTouch` |
| `+0x50` | u32 | `g_simFrame` at construction | ctor | `Gold_run` (the sound frame) |
| `+0x58` | anim state | the coin clip, resref `0x6e01b0`, pushed with `0x204` | ctor; `anim_advanceUnitSpeed` | `Gold_run` |
| `+0x5e` | u16 | anim state `+6`; bit `0x80` = the clip ended (*Inferred* from its use) | the anim step | `Gold_run` |
| `+0x80` | u32 | the amount | ctor; `Gold_onTouch` (0) | `Gold_onTouch` |

`Gold_draw` (slot 5, `0x157c04`) also writes `+0x84` onwards and advances the pile's own
generator `+0x44` (three `GameObject_rand` draws per sparkle when `(g_simFrame + k) % 60 ==
59`, `0x157dd0`–`0x157e58`). That is draw code; nothing here reads those fields
(*Observed*, not executed).

The table `0x511a88`: slot 4 `Gold_run`, 5 `Gold_draw`, 6 `Gold_onTouch`, 8 `Gold_loadState`
`0x157a84`, 9 `Gold_saveState` `0x157a6c`, 15 `Gold_clone` `0x11d850`. Slots 2, 3, 7 and
10–14 are the `GameObject` defaults (*Observed*). So the per-frame slots are 4 (run) and 5
(draw) only.

## 4. Gold_run `0x157b58` (pile), slot 4

*Executed*, in this order:

1. Nothing when the s8 `+0x4c` is 0 (`0x157b68`).
2. When `+0x50` equals `g_simFrame − 18` (`0x157b74`–`0x157b80`; `g_simFrame` `0x44fdcc`):
   - `res_find(0x532478 "fx.lmp", 0x532838 the coin drop sound)`;
   - `sound_playOnObject(entry, pile; 1.0)`. The 1.0 is `0x3f800000` at `0x157ba0`.

   This is the clink 18 ticks after the drop.
3. `anim_advanceUnitSpeed(+0x58, +0x10, 0, 0)` (`0x157bbc`).
4. `+0x4c` is re-read. When it is non-zero, it is lowered by one (`0x157bd4`).
5. When the halfword `+0x5e` has `0x80` (`0x157be0`): `+0x4c` = 0 and
   `obj_stopRunning(pile)` (`0x157bec`, with the store in the delay slot).

No draws and no other stores.

- **Consequence (Executed, `test_whole_life`):** when the countdown reaches 0 before the
  clip ends, `obj_stopRunning` is never called. The pile then stays on the run list and
  `Gold_run` returns at step 1 every tick.
- The pickup is possible after `min(41 ticks, the clip's end)`.
- How long the coin clip is: **Unknown** (it needs the clip's data). The probe's clip clock
  raises no end bit, so there the countdown always runs its 41 ticks.

## 5. Gold_onTouch `0x157a9c` (pile, toucher), slot 6

*Executed*, in this order:

1. The toucher's flags `+0xc` are read once (`0x157ab4`). Each test below that fails ends
   the touch:
   - no `0x20000` (`0x157aa0`, `0x157ab8`) — the toucher is not the prediction copy;
   - s8 `+0x4c` = 0 (`0x157ac4`);
   - `0x40` (`0x157ad0`) — the toucher is a player;
   - `+0x80` ≠ 0 (`0x157adc`).
2. `res_find(0x532478 "fx.lmp", 0x532820 the coin pick-up sound)` and
   `sound_playOnObject(entry, pile; 1.0)`.
3. `hud_addGoldFloater(toucher +0x3c8, copy of +0x10..+0x18, +0x80)` (`0x157b30`). The slot
   is read after the sound call.
4. `+0x80` = 0 (`0x157b38`).
5. `obj_delete(pile)` (`0x157b3c`): the deferred delete.

There is no game message, no `g_numPlayers` and no draw. A second toucher in the same tick
finds the amount 0 and gets nothing (*Executed*, pile cases with two touchers;
`test_second_toucher_gets_nothing`).

## 6. The credit

### 6.1 The floaters (`0x86a900`, 8 × 0x24)

| Offset | Width | Meaning | Used by the credit |
|---|---|---|---|
| `+0x00`, `+0x04` | f32 | screen x, y (from this machine's camera) | no |
| `+0x08` | f32 | z/w, then overwritten with 0 | no |
| `+0x0c`, `+0x10`, `+0x14` | f32 | the drift (`+0x14` = 0) | no |
| `+0x18` | u32 | start frame (`g_simFrame`) | yes |
| `+0x1c` | u32 | amount; 0 = free | yes |
| `+0x20` | s8 | slot | yes |
| `+0x21` | u8 | off-screen flag | no (only `hud_drawGold`, `docs/issues/native-graphics.md`) |

`g_goldFloaters` `0x86a918` in `symbols/` is entry 0's `+0x18`. The code reaches every
entry from `0x86a900` (*Observed*, as `docs/issues/claims-audit.md` item 3 says).
`g_goldPending` `0x86ace8` is s32[4].

### 6.2 hud_addGoldFloater `0x1dc268` (slot, world position, amount)

*Executed*, in this order:

1. The 12-byte position is copied to the stack.
2. The first floater whose `+0x1c` is 0 is taken (`0x1dc2a8`–`0x1dc2e0`). Entry 0 is tested
   first, then 1–7.
3. **None free** (`0x1dc2e8`): `g_players + slot × 0x4c30` `+0xe4` (`0x4d8bd4`) gets the
   amount added, and the 32-bit sum is stored. When the signed sum is above 99,999,999, the
   cap is stored over it. The cap is `0x5f5e0ff`, built at `0x1dc2f4`/`0x1dc2fc`. A
   wrapped negative sum stays. Nothing else happens: no cosmetic draw.
4. **Otherwise** the entry gets:
   - `+0x1c` = amount, `+0x20` = slot (byte), `+0x18` = `g_simFrame` (read at
     `0x1dc338`), `+0x21` = 0;
   - presentation (§6.3).

### 6.3 The floater's screen path (presentation)

- (p, w) = `mat4_transformPoint(g_viewProj 0x44f140, position)` (`0x1dc374`).
- `+0x21` = 1 when any of these holds:
  - w < 20.0 (`0x41a00000`, `0x1dc380`);
  - w × 700.0 < \|p.x\| (`0x442f0000`, `0x1dc398`);
  - w × 300.0 < \|p.y\| (`0x43960000`, `0x1dc3b8`).

  The tests stop at the first that holds.
- `+0x00` = p.x × (1/w) × 0.5 + 320.0 and `+0x04` = p.y × (1/w) + 240.0.
  - The constants are 0.5 at `0x1dc408`, 240.0 `0x43700000` at `0x1dc418` and 320.0
    `0x43a00000` at `0x1dc424`.
  - 1/w is one `div.s` at `0x1dc404`.
  - `+0x08` = p.z/w, then 0.
- The target is (float(s32 `0x4f6730`[slot]), float(s32 `0x4f6710`[slot]), 0).
  - x is 50, 590, 50, 590 and y is 200, 200, 250, 250 in the executable image.
  - d = target − (`+0`, `+4`, −0.0), normalised with `rsqrt.s` (`0x1dc564`).
- **One cosmetic draw** (`0x404460`, `0x1dc578`–`0x1dc5a0`): c = seed >> 16, and
  k = (c × 2⁻¹⁶ − 0.5) × 9.0 (`0x41100000`, `0x1dc494`).
- `+0x0c` = d.y × k, `+0x10` = −d.x × k and `+0x14` = 0.

### 6.4 hud_tickGold `0x1dcb80`, every tick

It is called first thing by `hud_run` `0x1db870` (`0x1db890`), a run task (`docs/ui.md`).
*Executed*, in this order:

1. For floaters 0–7: an entry with a non-zero amount moves when
   `(g_simFrame − +0x18) × 3`, as a signed 32-bit value, is not below 128 (`0x1dcbb0`–
   `0x1dcbc0`). That is 43 ticks.
   - `+0x1c` = 0;
   - `g_goldPending[s8 +0x20]` += the amount.
2. For slots 0–3, with p = `g_goldPending[slot]`: when p > 0,
   - step = (p + 7) >> 3 (arithmetic, `0x1dcc1c`–`0x1dcc24`);
   - record `+0xe4` += step, capped as in §6.2 (`0x1dcc30`);
   - pending = p − step.

The 120-gold pile of `test_whole_life` pays 15, 14, 12, 10, … and reaches 120 in
player 2's record only. A negative pending sum is never paid and never cleared here.
Nothing here reads the screen fields: **the credit is lockstep wherever the camera
looks** (*Executed*; the floater, tick and pile entries ran with random cameras).

### 6.5 hud_flushGold `0x1dc5f4` (from `game_clearLevel` `0x1e4f10`)

*Executed*, in this order:

1. Every busy floater's amount goes into record(s8 slot) `+0xe4` at once (capped), and the
   floater is freed.
2. Every positive pending sum of slots 0–3 goes in the same way, and the pending sum becomes
   0. A negative one is left as it is.
3. The words `0x4f6950 + 4s` and `0x86acd8 + 4s` (s = 0..3) are set to 0. Their readers
   were not looked for (**Unknown**).

### 6.6 Who gets what

- Gold credited by a pickup: the toucher's slot only, the whole amount. *Executed*: the
  pile and touch entries ran with `g_numPlayers` 0–4, and the gold bodies have no load of
  `0x4d8ae0` (*Observed*).
- The only multiplayer factor is upstream. `loot_generateDrops` makes bigger piles with
  more than one player (gold × 2.4, `docs/issues/kill-loot-xp.md`). The player who walks
  over the pile gets all of it.
- The script command `givePlayerGold`, by contrast, gives each slot amount /
  `g_numPlayers` (§9).

## 7. What a probe must supply for a pile to be picked up

1. **Construction**:
   - `pool_new(0xc0)` (refused blocks skip everything, `docs/objects.md` O1);
   - `Gold_ctor2` (`ref_phprop.Model.gold_ctor2`): one shared draw, `obj_runEveryFrame`.
2. **Every tick while on the run list**: slot 4 of table `0x511a88` (`+0x24` → `0x157b58`)
   with `g_simFrame` advanced. Its only service is the anim step: a stub with no end bit is
   faithful to a probe without a clip clock, and the countdown then ends after 41 ticks.
3. **The touch**: the player's own move, `obj_moveWithCollision` `0x14d4b8`
   (`docs/spec/combat-movement.md` §2, *Executed* there).
   - The box query must return the pile: it must lack flag 1.
   - √(dx² + dy²) + 0.001 must be below the player's radius + 24.0.
   - Flags `0x220c` have no `0x10`, so there is no height test. They have `0x200`, so the
     pile is touched without being pushed.
   - The dispatch calls the pile's slot 6 with the player unless the **mover** has
     `0x20000`. Then it calls the player's own slot 6 (`0x1beaf0`) with the pile.
   - `Creature_moveBy` reaches slot 6 too (with monsters, or the copy, G25/G26); both are
     refused here.
4. **The player's fields**:
   - object `+0x0c`: `0x40` set, `0x20000` clear;
   - object `+0x3c8`: the slot;
   - the radius `+0x1c` and the position, for the dispatch.
5. **The credit**: `hud_tickGold` every tick after the touch (it is part of `hud_run`; the
   rest of `hud_run` reads raw pads and need not run).
   - Memory: the floaters `0x86a900`–`0x86aa20`, `g_goldPending`, `g_players[slot] +0xe4`.
   - For the presentation only: `g_viewProj`, the HUD tables `0x4f6710`/`0x4f6730` and
     the cosmetic seed.
   - The gold arrives 43 ticks after the touch, an eighth at a time.
6. `obj_delete` of the pile at the touch.

## 8. The item props

### 8.1 Their life (*Observed* in `docs/issues/kill-loot-xp.md` §3; the parts marked are executed here)

| Made by | Object | Per-frame body | Pickup |
|---|---|---|---|
| `loot_generateDrops`, `loot_spawnNamedItem` (loot, `dropitem`): `PhProp_ctor` with an item record, flags `0x100000` (interactable) | `PhProp`, 0x248 bytes, table `0x511ba8` | `PhProp_run` `0x155fcc`: **not executed here**. Its settle path calls `ItemProp_ctor3` | slot 14 `PhProp_interact` (*Executed*) |
| `PhProp_run` at rest (`0x156c4c`) | `ItemProp`, 0x190 bytes, table `0x511c38`, by `ItemProp_ctor3` (*Executed*) | **none**: prop flags 0 → no `obj_runEveryFrame` (*Executed*, 0 calls in 6,000 cases) | slot 14 `ItemProp_interact` (*Executed*) |
| `givePlayerItem`, `giveOnePlayerItem` (full load), `inventory_dropItem` `0x1c47f4`, two more call sites (`0x146130`, `0x146234`) and `0x1c24a4`: `ItemProp_ctor2` (*Executed*) | `ItemProp` that **runs every frame** (`Prop_launch` calls `obj_runEveryFrame`; only launch bit `0x80` would stop it, and every call site passes launch 0) | slot 4 of `ItemProp` = `Prop_run` `0x154514` (*Executed*, §8.8): it falls, stops after its 180-tick life | slot 14 `ItemProp_interact` |

### 8.2 itemprop_tryPickup `0x154dbc` (slot, item record) → 1 taken, 0 refused

*Executed*, in this order:

1. w = `player_itemWeight(slot, item)` (`0x154dd8`, float in f0).
2. The bag is the item's category: the s8 at definition (item `+0`) `+0x1d`.
3. **Refused (bag)** when the count `g_players[slot] +0x1330 + bag × 0x1208`, plus one, is
   not below 64 (`0x154e10`–`0x154e18`). So 63 items already refuse; `inventory_giveItem`
   itself would go to 64.
   - `res_find(fx.lmp, 0x5325b8 the can't-do button sound)`;
   - `sound_playOnObject(entry, 0; 1.0)`: no object;
   - returns 0.
4. **Refused (load)** unless load `+0x120` + w ≤ limit `+0x124` (`c.ole.s`, `0x154e68`).
   An exact fit is taken.
   - `player_voice(slot, 0)` (`0x154ffc`);
   - returns 0.
5. **Taken**:
   1. The sound is chosen by the item's 64-bit flags `+8`, first match:

      | Bit | Sound | Format at |
      |---|---|---|
      | `0x800000` | `inv_equip_mdwp_wd` | `0x5325d0` |
      | `0x200000` | `inv_equip_chain` | `0x5325e8` |
      | `0x40000` | `inv_equip_mdwp_mtl` | `0x532600` |
      | `0x100000` | `inv_equip_leather` | `0x532618` |
      | `0x80000` | `inv_equip_cloth` | `0x532630` |
      | `0x1000000` | `inv_equip_potion` | `0x532648` |
      | none of these | `inv_equip_jewelry` | `0x532660` |

      The tests of `0x4000000`, `0x2000000` and `0x10000000` at `0x154f50`–`0x154f78` all
      lead to the jewelry name.
   2. It is `sprintf`'d (no conversion), then `res_find(fx.lmp, text)` and
      `sound_playOnObject(entry, g_players[slot] +0x43d8; 1.0)`.
   3. `script_runByName(0x532678 "*gotItemNotify")`.
   4. `inventory_giveItem(slot, item, 1)`. **Its result is ignored.**
   5. `player_recalcLoad(slot)`.
   6. Returns 1.

No draws, and no stores of its own.

- **Inferred** (from this execution and `inventory_giveItem`'s refusals, executed in
  `tools/difftest_messages.py`): a refused give still returns 1, and the prop is deleted.
- This difftest's give stub answers −1 in a third of the cases, and the destructor followed
  every time.
- So picking up a second `heart` or `shell` (`0x537e08`, `0x537e10`, the two names that may
  be held once) destroys it.

### 8.3 PhProp_interact `0x155020` / ItemProp_interact `0x159b38` (prop, slot), slot 14

The same instructions. *Executed*:

- **With item flag bit 39** (`+0x150`, `0x155024`/`0x155028`): `itemprop_tryPickup(k,
  prop +0x148)` is called for k = 0 .. `g_numPlayers` − 1. The count is re-read after every
  call.
  - Each player takes their **own copy**, under their own bag and load tests.
  - It is taken when any of them took it.
- **Otherwise**: only the given slot tries.
- **Taken, and the prop is not null**: slot 1 `(prop + adj, 3)`, the destructor that deletes
  it (`PhProp_dtor` `0x3c2fc8`, `ItemProp_dtor` `0x3c2ed8`; stubs here).

A refused pickup leaves the prop where it is.

### 8.4 PhProp_interactPrompt `0x154d10` / ItemProp_interactPrompt `0x159870` (prop, wide out) → 1, slot 13

The same instructions. *Executed*:

- `+0x104` = `g_simFrame` (`0x154d34`). Only draw functions read it, and draw code calls the
  prompt too, so the stamp is per machine (`kill-loot-xp.md`).
- The text is built with these calls:
  - `text_lookup(0x5325a0 "PickUp")`, then `wstr_cat`;
  - `wstr_catAscii(0x5325a8 " ")`;
  - `itemName_buildLocalizedName(prop +0x148, 1)`, then `wstr_cat`;
  - when the s16 stack count `+0x14c` (record `+4`) is 2 or more: `sprintf(" x %d", count)`
    and `wstr_catAscii`.

### 8.5 ItemProp_ctor3 `0x1592bc` (obj, position, item record, matrix): an item at rest

*Executed*, in this order:

1. The names come from row r of `0x3e9ce0` (16-byte rows: `+0` model, `+4` texture).
   r = `item_getResourceIndex(item)`, asked twice.
   - `item_getResourceIndex` `0x1083f8`: the s16 definition `+0x34`, plus bits 11–15 of
     the flag word when its bit 36 is set.
2. `Prop_ctorNamed(obj, copy of the position, 0x5326b0 "equipmnt.lmp", model, texture,
   mask −1, prop flags 0, matrix)` (`0x159344`).
3. Table `0x511c38`.
4. The record is set up as `PhProp_ctor` does:
   - the empty record at `+0x148`;
   - the item's 0x48 bytes copied over it with `ld`/`sd`, so the source must be 8-aligned.
5. Flags |= `0x102000`, then `& 0xffffe7ff` (`0x1593f4`–`0x15941c`). With item bit 39,
   `& 0xffffcfff` as well.
6. `obj_updateGridCell(obj)`.

On a zeroed block the flags end as `0x102009` (`0x100009` with bit 39). The prop flags
`+0x140` end as 1. There is **one shared draw** (`GameObject_ctor`) and no own draw.

### 8.6 Prop_ctorNamed `0x153ac0` (obj, position, lump, model, texture, 64-bit mask, prop flags, matrix)

*Executed*, in this order:

1. `GameObject_ctor(obj, copy, 0, 0)`: one shared draw.
2. Flags |= `0x1809` (`0x153b50`), table `0x511d58`, `obj_updateGridCell`.
3. `+0x140` = prop flags | 1. Radius `+0x1c` = 4.0 (`0x40800000`, `0x153b60`).
4. The matrix's 0x30 bytes go to `+0x110`.
5. The names are copied to `+0x54`, `+0x64` and `+0xa4`. `+0x4c` and `+0x50` =
   `res_find(+0x54, +0x64 / +0xa4)`.
6. `+0xe8` = the mask.
7. Prop flag 2: `obj_runEveryFrame` and flags |= `0x4000`. Prop flag 4: flags |= `0x1000`.

### 8.7 ItemProp_ctor2 `0x1590ec` (obj, position, item record, launch)

*Executed*, in this order:

1. `Prop_ctorNamedLaunch(obj, copy, "equipmnt.lmp", the row's names, mask −1, launch)`
   (`0x159170`; `docs/spec/gut-chunk.md` §5–6). This is one shared draw, the facing's own
   draw and the launch's own draws, and it always calls `obj_runEveryFrame`.
2. The record and flags as §8.5.
3. `+0x110` = `mat34_setPosRotZ(the position now, s16(u16 +0x38 + 0x4000))` (`0x159294`).

All seven call sites pass launch 0 (`move a3, zero` at `0x145c7c`, `0x145cd4`, `0x145ec8`,
`0x146134`, `0x146238`, `0x1c24a8`, `0x1c47f8`; *Observed*). With launch 0 that is 1 shared
and 1 own draw (the facing), life 180, and the prop stays on the run list.

### 8.8 Prop_run `0x154514` (prop), slot 4 of `Prop` and of `ItemProp`

*Executed*, in this order:

1. **While prop flag 1 (`+0x140`) is clear** (the prop is moving):
   1. The step is (`+0xfc` × 1/60, `+0x100` × 1/60, 0). 1/60 is `0x3c888888` at
      `0x154550`.
   2. When 0.001 (`0x3a83126e`, `0x15455c`) < x² + y² of the step:
      - t = `terrain_sweepCircle(g_world 0x44fdc8, copy of the position, step, 1, normal
        out; radius +0x1c)` (`0x1545cc`);
      - the position gains step × t, stored in the order y, z, x; then
        `obj_updateGridCell`;
      - when t < 1.0 and d = 0.001 − (n.x × `+0xfc` + n.y × `+0x100`) > 0:
        `+0x100` += n.y × d × 1.5 and `+0xfc` += n.x × d × 1.5 (`0x3fc00000`, `0x15466c`).
   3. ground = `terrain_heightBelow(g_world, copy of the position; radius)` (`0x1546b8`).
   4. vz = `+0x30` − 26.999998 (`0x41d7ffff`, `0x1546c8`), and z = `+0x18` + vz × 1/60.
      Both are stored.
   5. When z ≤ `+0x108` + ground and vz ≤ 0:
      - z = `+0x108` + ground;
      - `+0xfc` and `+0x100` × 0.98 (`0x3f7ae147`);
      - `+0x30` = −vz × 0.4 (`0x3ecccccc`) when vz < −0.1 (`0xbdcccccc`), else 0.
   6. The spin: halfword `+0x38` += `+0x10c`, then `+0x10c` −= 10, and 0 when the result is
      negative as an s16.
2. **Every tick**: the life `+0x10e` loses one (halfword).
   - When it is ≤ 0 and prop flag 1 is clear: flag 1 is set. Unless `+0x140` has 2,
     `obj_stopRunning(prop)` follows, and the tick ends.
3. Below −60 (s16, `0x1547dc`): `+0x18` and the matrix z `+0x13c` lose 0.1 (`0x3dcccccc`).
   Below −300 (`0x1547ec`): slot 1 `(prop + adj, 3)` deletes it and the tick ends.
4. With `g_numPlayers` > 0 and `g_alivePlayers[0]` (`0x4f8440`) ≥ 0: when the object of
   that record exists and the prop's z + 120.0 (`0x42f00000`) < its z, `obj_delete(prop)`.
   This is the item version of FINDINGS G19.

No draws. A prop at rest that still runs (prop flag 2: gut chunks and bones,
`docs/spec/phprop-run.md` §8) skips step 1. Its life keeps falling, so it sinks after −60
and goes at −300.

An `ItemProp_ctor2` item (life 180, prop flags 0) therefore does the following
(*Executed*, `dropLife` and `test_falls_lands_and_rests_after_180`):

1. It falls and bounces.
2. After 180 ticks it gets flag 1 and leaves the run list.
3. Its z is then fixed, and it is never sunk or deleted by age.

It can still be deleted by the 120-below test on any tick while it runs. It can be picked
up all the time: flags `0x100000` from §8.5.

## 9. Cross-check with branch `t3/research-items` (read with `git show`, not merged)

Read: `docs/script-items.md`, `tools/ref_script_items.py`, `tools/difftest_script_items.py`.

Agreements:

| Their claim | Here | Address |
|---|---|---|
| Gold is record `+0xe4`, s32, capped at 99,999,999 by storing the sum and then the cap; a wrapped negative sum stays | the same idiom in all three credit bodies | `0x1dc2f0`, `0x1dcc30`, `0x1dc624`, `0x1dc688` (theirs `0x146300`–`0x14630c`) |
| Record layout: `+0x120` load, `+0x124` limit, bags at `+0x130 + bag × 0x1208` with the count at `+0x1200`, `+0x43d8` the object, the bag is definition `+0x1d` | `itemprop_tryPickup` reads exactly these | `0x154df0`, `0x154e10`, `0x154e54`–`0x154e60`, `0x154fcc` |
| A dropped item is `pool_new(0x190)` + `ItemProp_ctor2(block, position, record, 0)` | 0x190 is `ItemProp`'s size (`ItemProp_clone`); `ItemProp_ctor2` executed | `0x145c78`, `0x145cd0`, `0x145ef0` |
| §10 open item "`ItemProp_ctor2`'s own draw was not re-run" | now executed: 1 shared draw (`GameObject_ctor`) plus own draws (facing, and the launch's; launch 0 gives the facing only). Their "one [draw] inside `ItemProp_ctor2` per ground item" is right for the shared seed | `0x159170` |
| `inventory_giveItem` returns −1 for a full bag or a second held-once item, and their handlers ignore it | the pickup ignores it too (§8.2) | `0x154fe4` |

Differences between the script path and the pickup path. These are not errors on either
branch; they are two rules a port must not merge:

| Rule | Script give (theirs) | Pickup (here) |
|---|---|---|
| Weight test | load + w **<** limit (`c.olt.s`), or w exactly 0 | load + w **≤** limit (`c.ole.s`, `0x154e68`); no zero exception is needed |
| Full bag | no count test: `inventory_giveItem`'s −1 loses the item | count + 1 < 64 tested first (`0x154e18`), refused with a sound; the item stays on the ground |
| On failure | dropped as an `ItemProp_ctor2` at the player | the prop stays; `player_voice(slot, 0)` |
| Gold | `givePlayerGold`: each slot gets amount / `g_numPlayers` (C division) | the toucher gets the whole amount; no division |
| Several players | the loop gives each slot its own parse | bit 39 gives each slot its own copy; otherwise only the user |

Disagreements: none found in their text about these functions. One gap in theirs: the item
the bag-full give drops (`ItemProp_ctor2`) **runs every frame** for 180 ticks (`Prop_run`,
§8.8), unlike a loot item that came to rest (§8.1). It falls to the ground there, and is
deleted if it is 120 below the first alive player. Their note does not say what the dropped
item does after it is made.

## 10. Corrections and sharpenings to other documents

- `docs/issues/kill-loot-xp.md` §3 says `Gold_run` "counts down and unlinks when the spawn
  animation ends". It unlinks **only** if the clip ends while the countdown is still
  running. A countdown that reaches 0 first leaves the pile on the run list for good, with
  an empty body each tick (§4).
- The same document, §3, says an item at rest is "on no run list". *Executed* (§8.5): this
  holds for `ItemProp_ctor3`. It does **not** hold for an `ItemProp` made by
  `ItemProp_ctor2` (script give at full load, inventory drop). That one runs `Prop_run` for
  its 180-tick life and then leaves the run list (§8.8).
- `docs/spec/phprop-run.md` (another lane of this round, untracked when this was written)
  models `ItemProp_ctor3` and `Prop_ctorNamed` too. Its §8 text agrees with §8.5–8.6 here
  in every step. Its §11 lists `Prop_run` as not executed; §8.8 here executes it.
- `symbols/`: `g_goldFloaters` `0x86a918` is entry 0's `+0x18`; the array starts at
  `0x86a900` (§6.1, proposed note change in the final report).

## 11. Still not executed

- `PhProp_run` `0x155fcc` (about 890 instructions): the flying item's frame and its settle
  into `ItemProp_ctor3`. Another lane of this round has a clone for it (`local/ghidra-phrun`).
- `Gold_draw` `0x157c04` (282 instructions; draw, own generator `+0x44`), `Gold_saveState`,
  `Gold_loadState`, `Gold_clone`, and `Gold_ctor` `0x157754` (the factory pile of a level).
- `Player_interact` `0x1b2640` with an interactable object in reach (only the empty case is
  executed, `docs/spec/combat-player-defence.md` §4).
- The callees that stayed stubs:
  - `inventory_giveItem` (executed in `tools/difftest_messages.py`);
  - `player_itemWeight` and `player_recalcLoad` (executed on `t3/research-items` only);
  - `itemName_buildLocalizedName` (`tools/difftest_items.py`);
  - `obj_delete` and `obj_stopRunning` (`tools/difftest_objects.py`);
  - `obj_updateGridCell`, `obj_runEveryFrame`, `terrain_sweepCircle`, `terrain_heightBelow`;
  - `anim_advanceUnitSpeed`, `anim_clear`, `anim_push`, `resref_get`;
  - `res_find`, `sound_playOnObject`, `player_voice`, `script_runByName`, `text_lookup`,
    `wstr_cat`, `wstr_catAscii`, `handle_link`, `obj_getPropInt`;
  - the three destructors.
- `hud_run` around `hud_tickGold`, and `hud_drawGold`.
- The readers of `0x4f6950[4]` and `0x86acd8[4]`.
- The length of the coin clip `0x6e01b0`.
