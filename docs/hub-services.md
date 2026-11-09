# Hub and hub2 services between missions — SLUS-20973 v2.00

Research date 2026-11-09, branch `t3/research-hub-npcs`. This extends
`docs/spec/hub-npc-services.md` on the same branch (object census and Savepoint
use). It replaces that file's hub2 **Unknown** rows with executed results.
`tools/ref_hub_services.py` is the model. `tools/difftest_hub_services.py`
compares it with the original code in `tools/ee_emu.py` at seeds 20973 and 7.
`tools/test_ref_hub_services.py` holds synthetic checks.

**Labels.** **Observed** means addressed code, or a disc record pinned by
SHA-256. **Executed** means the named original function ran on constructed
state in `tools/ee_emu.py`. **Inferred** means a link between separate
observations. **Unknown** means no accepted evidence. Nothing here comes from a
running console, Play!, or the native client.

**Neutral ids.** This file and the tracked tools contain no script names,
variable names, text keys, item names or dialogue. Script entries are named by
public offset in that hub's `script.scr`. Dialog nodes are `H1.Nxx` (hub) and
`H2.Nxx` (hub2). The difftest resolves the real names from the owner's disc at
run time and never prints them. The private name map stays in untracked
`local/`. Ids used below:

| Id | Meaning | Where the difftest finds it |
|---|---|---|
| `V.started[n]` | per-mission "started" quest variable, n = 1..12 | the twelve `getv` reads, in order, of the entry called by the node-0 condition (`started_names`, difftest lines 367–377) |
| `V.intro` | hub2 intro-heard variable | `getv` in hub2 public `0x28b4` |
| `V.demo` | hub demo variable | `getv` in hub public `0x498` |
| `V.current`, `V.store`, `V.mana`, `V.first` | current mission, vendor store level, mana-restore flag, first-mission help state | first `getv`, first `setv`, last `getv` before `refillPlayerMana`, last `getv` of `start` (`start_sites`, lines 582–595) |
| `I.cleanup` | three quest-item ids removed on hub entry, from 10 + 3 + 4 call sites | literal `removePlayerItem` arguments in `start` |
| `T.shard`, `T.blood` | 10-cell and 13-cell item tables of the two deferred duplicate checks | script data, read by the entries `start` queues |
| `ENT.H1`, `ENT.H2` | the single `setEntrance` literal in each hub | the one `setEntrance` site |
| `K.lock`, `K.use`, `K.warn`, `K.walk` | the callees of the PushTrigger key and action, their shared warning test, and the walk-in rectangle's callee: hub publics `0x3cb0`, `0x49c0`, `0x4234`, `0x4c44`; hub2 `0x1500`, `0x2210`, `0x1a84`, `0x2494` | `callScript` literal in the object's entry |
| `L-INN` | the only other archive whose script names `V.mana` | disc census (`check_inn`, difftest lines 792–822) |

## 1. Everything a player can use in the two hubs

**Observed** (pinned archives, `docs/spec/hub-npc-services.md` lines 20–36 and
`tools/difftest_hub_npcs.py`): hub has 24 object records and hub2 has 21. Each
hub has exactly one `NPC`, one `Savepoint`, one `Portal` (`lump=jumpgate`), one
`PushTrigger`, one rectangular `Trigger` and one ring prop (`apprings` /
`fpprings`). The rest are lights, `Player1` markers, critters (`bflya`/`bflyb`,
`critter=1`, hub only), `Torch` (hub2 only), `clearColor` and `customVars`. None of
these carries a shop, dialog, key, action or trigger property.

| Service | hub | hub2 | Trigger / use entry | Section |
|---|---|---|---|---|
| Mission giver and vendor (one NPC) | object 10 | object 5 | use button → `Creature_interact` 0x116bd8 → the NPC's `dialogScript` entry (public `0x0` in both) → `startDialog` → `dialog_onMsg` 0x22ee2c | 2, 3 |
| Vendor store | same NPC, `shop=1` | same | SHOP choice → `activateStore` 0x144010 (deferred) → store opens at dialog end | 3.3 |
| Mission map | `PushTrigger` 11 | `PushTrigger` 7 | key public `0x98`, action public `0x54` (both hubs) | 5 |
| Walk-in portal signal | `Trigger` 12 | `Trigger` 9 | `t` = public `0xd8` (both hubs) | 5 |
| Portal ring animation | object 0 | object 8 | `action1` = hub `0x4e9c`, hub2 `0x26ec`; `start` sets state 0 | 5.3 |
| Jump gate | `Portal` 6 | `Portal` 0 | `JumpGate_interactPrompt` 0x27d7a0 / `JumpGate_interact` 0x27d754 | 6 |
| Save point | `Savepoint` 8 | `Savepoint` 6 | `Savepoint_interact` 0x28dc30 | 7 |
| Hub-entry services (no object) | `start` public `0x2838` | `start` public `0x134` | run by the level loader | 4 |

**Absent (Observed, both hub archives):** no trainer, bank, stash, healer or
second quest giver. There is no second `NPC` record, and no class outside the
census above. Neither script imports a training, gold, experience, heal or save
native (`ABSENT` in `tools/difftest_hub_npcs.py`). The script also imports no
gold, experience, heal, stat or item-grant native (`NO_SERVICE_NATIVES` in
`tools/difftest_hub_services.py`). **Ambient
dialogs:** none. hub's other two `.dbin` files are an unreferenced backup copy
of the NPC dialog and a one-node cutscene dialog with no condition and no
choices. That cutscene dialog is **Inferred** to belong to the hub's cutscene
entry, public `0x34a4`, which requests a cutscene of the same stem. Its
caller is **Unknown**. hub2's other `.dbin` is a backup
copy. The single `startDialog` site in each script names the live file
(`check_structure`, lines 185–241). Critters and torches have no interaction
property.

## 2. The NPC dialog: node order and start-node rule

**Observed:** a node is 0x448 bytes. Its condition is at +0x01, its choice
count at +0x54, and its choices at +0x58, each 0x54 bytes: key, condition,
action, next (`docs/dialog.md` §3 on `t3/research-dialog-gaps`, lines
175–193). **Executed** (composed, section 3.4): `dialog_onMsg` 0x22ee2c runs
node 0's condition first, then the others in file order, and opens the first
that returns non-zero, or node 0 when none does. `dialog_showNode` 0x230c74
shows the choices whose condition is empty or true. This matches
`ref_hub_services.start_node` / `visible` (ref lines 194–210).

Predicates (all **Executed**: 25 hub and 24 hub2 condition entries × 184
states per seed, 4,600 + 4,416 results equal to the model, difftest lines
380–427). Let A(n) be bit 0 and C(n) bit 1 of player 0's mission byte n at the
current difficulty (`g_players` 0x4d8af0 +0x4bbf + 13·difficulty):

| Kind | Value |
|---|---|
| ACTIVE | any n in 1..12 with A(n), not C(n), and `V.started[n]` ≠ 0 (signed byte) |
| !A(n) | mission n not yet available (the offer branch, or a status-only branch for n = 8, 9) |
| PENDING(n) | A(n), not C(n), and `V.started[n]` = 0 (offered, not yet entered) |
| DEMO | always 0 in this executable (`demoRunning` 0x141764 returns 0) |
| INTRO (hub2) | not A(2) and `V.intro` = 0 |
| C(1), !C(1) (hub2 choice conditions) | mission 1 complete / not complete |

The hub results agree with the 352-state matrix on
`t3/research-mission-unlocks` `2ab82b2` (`docs/spec/mission-unlocks.md` lines
35–85). This file adds hub2 and the choice conditions.

## 3. Dialog nodes, choices and effects

### 3.1 Choice roles and action effects

Each dialog uses exactly three choice keys. **Observed** (structure only):
MORE is the key whose choices all continue to another node; SHOP is the key
whose every action requests the store; END is the rest. END and SHOP choices
always close the conversation (difftest lines 206–217).

**Executed** effects (`check_actions`, lines 430–476: every dialog action plus
the unreferenced writers, each with the dialog open and closed, at both seeds).
The recorded writes outside the stack and script image are exactly these, and
nothing else:

| Effect | Recorded write / call |
|---|---|
| `A(n)` | `setMissionAvailable(n,1)` → bit 0 of mission byte n at the current difficulty, player 0's row only (0x4dd6af + n for difficulty 0). The other difficulty rows and the C bit are unchanged. |
| `+quest` | one `addQuest`: quest entry +0x41d0 title/+0x20 body equal that call's two literals, count +0x43d0 becomes 1 (`quest_add` 0x1d386c) |
| `store` | `changeSwoop(0)` → 0x4fdce4 = 0; `activateStore` → u16 0x4f7150 written. **Dialog open:** byte 0x4fdd30 = 1 and no `shop_openOrStock`. **Dialog closed:** `shop_openOrStock` stub called once and 0x4fdd30 not written. |
| `V.x=1` | one quest-variable entry in 0x86da80 |

No action writes gold (+0xe4), HP, experience, items or any other player-record
byte. No dialog choice charges a fee. **Observed:** `removePlayerItem` is not
reachable from either dialog. Every action entry's native list is one of those
above. The 19 `removePlayerItem` sites per hub are all in `start` and its
deferred checks (section 4). This settles the reach question that
`docs/spec/hub-npc-services.md` lines 62–63 and 90 left open.

**Observed** (asserted in `check_structure`): every store action that a live
dialog reaches pushes the literal 0 to `activateStore`. Since 0 < 21, u16
0x4f7150 becomes 0. The argument-less form, which reads its index from the
script stack above its arguments (`docs/spec/script-builtins.md` lines 43–45),
occurs only in the unreferenced writers below.
**Executed:** both forms write 0x4f7150 in this fixture. The value of the
stack-read form is fixture-dependent, so it is not asserted.

### 3.2 Node tables (Observed structure, Executed effects)

Offsets are script public offsets. "close" is next = −1. A choice with a guard
is shown only when the guard is true.

#### hub

| Node | Condition (`offset`) | Choices: role → action effect → next |
|---|---|---|
| H1.N00 | ACTIVE `0x3f0` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N01 | !A(1) `0x11c` | MORE → none → H1.N02 |
| H1.N02 | !A(1) `0x11c` | MORE → none → H1.N03 |
| H1.N03 | PENDING(1) `0x198` | END → A(1)+quest `0x1e68` → close; SHOP → A(1)+quest+store `0x1ee8` → close |
| H1.N04 | DEMO (0) `0x498` | MORE → none → H1.N05 |
| H1.N05 | DEMO (0) `0x498` | END → V.demo=1 `0x598` → close; SHOP → V.demo=1+store `0x1fc0` → close |
| H1.N06 | DEMO (0) `0x680` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N07 | !A(2) `0x734` | END → A(2) `0x7b0` → close; SHOP → A(2)+store `0x2064` → close |
| H1.N08 | PENDING(2) `0x898` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N09 | !A(3) `0x9a0` | MORE → none → H1.N10 |
| H1.N10 | !A(3) `0x9a0` | END → A(3) `0xa1c` → close; SHOP → A(3)+store `0x2108` → close |
| H1.N11 | PENDING(3) `0xb04` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N12 | !A(4) `0xc0c` | END → A(4)+quest `0x21ac` → close; SHOP → A(4)+quest+store `0x222c` → close |
| H1.N13 | PENDING(4) `0xd70` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N14 | !A(5) `0xe78` | END → A(5) `0xef4` → close; SHOP → A(5)+store `0x2304` → close |
| H1.N15 | PENDING(5) `0xfdc` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N16 | !A(6) `0x10e4` | MORE → none → H1.N17 |
| H1.N17 | !A(6) `0x10e4` | END → A(6)+quest `0x23a8` → close; SHOP → A(6)+quest+store `0x2428` → close |
| H1.N18 | PENDING(6) `0x1248` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N19 | !A(7) `0x1350` | END → A(7) `0x13cc` → close; SHOP → A(7)+store `0x2500` → close |
| H1.N20 | PENDING(7) `0x14b4` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N21 | !A(8) `0x15bc` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N22 | !A(9) `0x1638` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N23 | !A(10) `0x16b4` | MORE → none → H1.N24 |
| H1.N24 | !A(10) `0x16b4` | END → A(10)+quest `0x25a4` → close; SHOP → A(10)+quest+store `0x2624` → close |
| H1.N25 | PENDING(10) `0x1818` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N26 | !A(11) `0x1920` | MORE → A(11)+quest `0x26fc` → H1.N27 |
| H1.N27 | PENDING(11) `0x1a84` | SHOP → store `0x1df8` → close; END → none → close |
| H1.N28 | !A(12) `0x1b8c` | MORE → none → H1.N29 |
| H1.N29 | !A(12) `0x1b8c` | END → A(12) `0x1c08` → close; SHOP → A(12)+store `0x277c` → close |
| H1.N30 | PENDING(12) `0x1cf0` | SHOP → store `0x1df8` → close; END → none → close |

#### hub2

| Node | Condition (`offset`) | Choices: role → action effect → next |
|---|---|---|
| H2.N00 | ACTIVE `0x2ab0` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N01 | INTRO `0x28b4` | MORE if !C(1) → V.intro=1 `0x29bc` → H2.N02; MORE if C(1) → V.intro=1 `0x29bc` → H2.N03 |
| H2.N02 | INTRO `0x28b4` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N03 | !A(2) `0x2af0` | END → A(2) `0x2b6c` → close; SHOP → A(2)+store `0x4224` → close |
| H2.N04 | PENDING(2) `0x2c54` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N05 | !A(3) `0x2d5c` | END → A(3) `0x2dd8` → close; SHOP → A(3)+store `0x42c8` → close |
| H2.N06 | PENDING(3) `0x2ec0` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N07 | !A(4) `0x2fc8` | END → A(4)+quest `0x436c` → close; SHOP → A(4)+quest+store `0x43ec` → close |
| H2.N08 | PENDING(4) `0x312c` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N09 | !A(5) `0x3234` | END → A(5) `0x32b0` → close; SHOP → A(5)+store `0x44c4` → close |
| H2.N10 | PENDING(5) `0x3398` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N11 | !A(6) `0x34a0` | END → A(6) `0x351c` → close; SHOP → A(6)+store `0x4568` → close |
| H2.N12 | PENDING(6) `0x3604` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N13 | !A(7) `0x370c` | MORE → none → H2.N14 |
| H2.N14 | !A(7) `0x370c` | END → A(7) `0x3788` → close; SHOP → A(7)+store `0x460c` → close |
| H2.N15 | PENDING(7) `0x3870` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N16 | !A(8) `0x3978` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N17 | !A(9) `0x39f4` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N18 | !A(10) `0x3a70` | MORE → none → H2.N19 |
| H2.N19 | !A(10) `0x3a70` | MORE → A(10)+quest `0x46b0` → H2.N20 |
| H2.N20 | PENDING(10) `0x3bd4` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N21 | !A(11) `0x3cdc` | END → A(11)+quest `0x4730` → close; SHOP → A(11)+quest+store `0x47b0` → close |
| H2.N22 | PENDING(11) `0x3e40` | SHOP → store `0x41b4` → close; END → none → close |
| H2.N23 | !A(12) `0x3f48` | MORE → none → H2.N24 |
| H2.N24 | !A(12) `0x3f48` | END → A(12) `0x3fc4` → close; SHOP → A(12)+store `0x4888` → close |
| H2.N25 | PENDING(12) `0x40ac` | SHOP → store `0x41b4` → close; END → none → close |

The tables are `ref_hub_services.NODES`/`ACTIONS` (ref lines 59–150). The
difftest asserts them field by field against the disc (lines 185–241). Where
the two hubs differ for the same mission (Observed and Executed): mission 4's
quest pair is a different pair. Mission 6 adds a quest in hub but not in hub2.
For mission 10 hub2 has no END/SHOP choice: its second MORE adds the quest and
continues to the reminder node. For mission 11 hub adds the quest on a MORE that
continues to the reminder, while hub2 offers END/SHOP, both of which add it.
Missions 8 and 9 are never offered by either NPC. Their nodes only show the
store or close, so their availability comes from elsewhere (in-level writers,
cited in section 8).

**Unreferenced writers (Executed, Observed):** 17 hub and 13 hub2 public
entries have offer-style native lists (`A(n)`, `+quest`, `store`) but are not
named by the live dialog. Every one of them is named by that hub's backup
`.dbin`, which `startDialog` never loads. They are executed, and their effects
equal `ref_hub_services.UNREFERENCED_WRITERS` (ref lines 153–165). This
explains hub `0x7fc`, which `docs/spec/mission-unlocks.md` lines 493–495 left as
"which dialog node reaches it": none in the shipped dialog. Do not wire them.

### 3.3 The store as a dialog service

**Executed:** a SHOP action run inside the dialog only marks the request
(0x4fdd30 = 1) and sets the swoop word to 0. **Observed** in `dialog_runTask`'s
end message (`docs/dialog.md` lines 271–273 on `t3/research-dialog-gaps`): at
the end of the conversation, when a store was requested, offline play calls
`shop_openOrStock(active player, 0, 1)`; net play calls
`net_closeLocalMenus(0)` and opens the shop for the first local slot. The
store's contents, prices and stock are `t3/research-vendor-stock` `fdf6752`
(`docs/spec/vendor-stock.md` lines 15–63 inputs, 228–255 buy/sell prices,
303–322 `V.store`, 324 onward client list). The stock level is the variable
`V.store`, which the hub stores on entry (section 4). **Executed** here: the
two stores that vendor-stock lists as "not a pushed constant" (vendor-stock
lines 313–319) are both `V.current − 1`.

### 3.4 Conversations by progress state

**Executed** (`check_conversations`, lines 519–579) through the original
`dialog_onMsg` / `dialog_showNode` / confirm composition. That composition is
`Probe` from `t3/research-mission-unlocks` `2ab82b2`
`tools/difftest_mission_unlocks.py`, loaded unchanged from that Git object. It
in turn loads the dialog harness from `334578d`. hub has 38 progress states and
76 whole conversations, and hub2 has 45 states and 90 conversations, per seed.
Every path through visible choices to close is run. Opening, visible choices,
`script_runByName` entries, `mission_setAvailable` 0x1bf6d0 calls (hooked
arguments), the store byte and the quest count equal the model at every step.
Each state's difficulty is cycled 0..4. hub2 runs with the evil and decision
bits set. The states are constructed, not played.

The resulting rule (both hubs; k = 1..12; missions below k complete):

| Player's state for mission k | Opening node, hub / hub2 | What the conversation can do |
|---|---|---|
| fresh (mission 1 unavailable) | H1.N01 → N02 → N03 / — | Either N03 choice: A(1) + quest; SHOP also opens the store at close |
| k unavailable, k ∈ {2..7, 10..12} | the !A(k) offer node | END: A(k) (+quest where marked); SHOP: the same plus the store |
| k unavailable, k ∈ {8, 9} | H1.N21/N22, H2.N16/N17 | store or close only; no mission write |
| A(k), not started | PENDING(k) reminder node (hub's mission 1: H1.N03 is both the offer and the reminder) | store or close |
| A(k), started, not complete | node 0 (ACTIVE) | store or close |
| hub2, `V.intro` = 0 and mission 2 unavailable | H2.N01 | MORE sets `V.intro`; with C(1) it continues to the mission-2 offer H2.N03, without it to H2.N02 (store/close) |
| all twelve complete | node 0 (fallback) | store or close |

Priority is file order, not mission order. Example (Executed state
`m9-available-unstarted`): with missions 1–8 complete and mission 9 available
but not started, no PENDING(9) node exists, so the hub opens the mission-10
offer. Gating mission 9 is the mission menu's job (section 5), not the NPC's.
Started missions are detected only through `V.started[n]`, which the level
scripts set (for example `t3/research-story-route-r3` `3c7987c`,
`docs/story-route.md` lines 389–408).

**Suppressors**, cited and not re-run here: recall or a running mission-menu task
blocks the dialog's script dispatch (`docs/spec/mission-unlocks.md` lines
120–126 and 225–232).

## 4. Hub-entry services (`start`)

The loader runs `start` on every hub entry (`t3/research-story-route-r3`
`docs/story-route.md` lines 40–58). **Executed** (`check_entry`, lines
597–679; 148 cases per hub per seed):

| Service | Rule | Executed controls |
|---|---|---|
| Mission bits | hub: `setMissionAvailable(0,1)`, `grantMission(0)` → byte 0 = 3. hub2: `setMissionAvailable(1,1)` only, so byte 1 gets bit 0 | 126 states of byte 8/9 and `V.current` |
| Save inhibit | 0x50605c = 0 | planted 1 |
| Vendor store level `V.store` | `V.current` = 0 → 0; = 7 → 8 if C(9), 7 if A(9), 6 if A(8), else 5; = 8 → 6; = 9 → 7; otherwise `V.current` − 1 | `V.current` 0..13 × byte 8 ∈ {0,1,3} × byte 9 ∈ {0,1,3} |
| Player flag 4 | cleared on slots 0..3 unless `V.current` is 7 or 9 (record +0x4c28 bit 4) | six values, four slots |
| Mana restore | if `V.mana` = 1: `V.mana` = 0 and `refillPlayerMana` 0x142494 sets every present player's mana +0xc0 to max +0xc4. Other values (0, 2, −1) leave both unchanged | two players |
| Quest-item cleanup | 17 `removePlayerItem(−1, I.cleanup)` sites (10 + 3 + 4, in that order). For each present player: `inventory_findItemBySubstring`, then `inventory_removeItem` when found | 1, 2, 4 players × found/not found |
| First-mission help | if `V.first` = 1 and some present player lacks flag 3: `V.first` = 2. If `V.first` = 2: `V.first` = 0, flag 3 set on every present player, one help box | `V.first` 0/1/2 × flag 3 |
| Portal ring | `autoPropSetState(ring name, 0)` | native argument recorded |
| Deferred duplicate checks | queues `T.shard` and `T.blood` checks (two `addDeferedCall`) | count of queued calls |

**Executed** (`check_dedupe`, lines 682–715; 24 cases per hub per seed): each
deferred check asks `inventory_countItemByName` for every visited cell and
every present player. It calls `removePlayerItem` once per item whose count is
above 1, so one extra copy is removed per hub entry. **Observed** (the loop
bounds in the original bytecode): the tables have 10 and 13 cells (bounds
checks 0..9 and 0..12), but the loops stop at 9 and 12. The last cell of each
table is never checked. The executed ask counts (9 and 12 per player) confirm
this. `T.shard` loops over slots 0..3, filtered by `onePlayerHasItem`'s own
present-and-alive test (`docs/spec/script-builtins.md` line 637). `T.blood`
loops over the player count that `start` stored.

**Mana restore and `L-INN` (Observed census, Executed store):** one other
archive on the disc names `V.mana`. It stores the literal 1 once (site `0x3958`
in its public `0x200c`), never reads
the flag, imports `zeroPlayerMana` but not `refillPlayerMana`, and has
`newWorld` requests to both hubs. Its storing entry is executed at both seeds
(`check_inn`). The flag is set and the entry draws the shared seed. **Inferred:**
that level zeroes mana while the player is there, and the next hub entry gives
it back. It is a free restore on return, not a paid inn. That level's gold
natives belong to its own wagers, which are outside this note. How a player
reaches `L-INN` is **Unknown** here: no hub object or hub script requests it.

**No healer.** No hub service restores HP. The only HP effect on hub ground is
the Savepoint's co-op resurrection (section 7).

## 5. Mission map trigger, walk-in signal and ring

### 5.1 PushTrigger (the mission giver's menu)

**Observed:** both hubs' `PushTrigger` records name the same key (public
`0x98`) and action (public `0x54`), have `nethostonly=1`, and use radii 79/78.
**Executed** (`check_travel`, lines 728–789; 120 states × 5 cases per hub per
seed):

| Entry | Rule |
|---|---|
| key `0x98` → `K.lock` | usable iff some n in 1..11 has A(n) and not C(n), **or A(12)**. Mission 12's completion bit is not read, so after mission 12 is offered the map stays usable even once it is complete (`ref_hub_services.key_usable`) |
| action `0x54` → `K.use` | if some A(n), not C(n), `V.started[n]` ≠ 0 (K.warn): help box and a deferred pause entry, no entrance write, no menu. Otherwise `setEntrance(ENT.H1 / ENT.H2)` → `g_entranceName` 0x4f8468, then `activateMissionMenu` 0x143fa8 → `missionMenu_open` stub, **unless** a dialog is open or the recall countdown 0x41b51d is set (entrance still written) |

No case writes a mission byte, quest or other player-record byte. The two hubs
differ only in the entrance literal. The menu itself (row selection,
story/evil level per row, confirm writes `g_pendingLevel` 0x41b6d0 and
orientation 0xff) is `t3/research-story-route-r3` `3c7987c`
`docs/story-route.md` lines 226–270 and 331–367, and
`t3/research-mission-unlocks` `docs/spec/mission-unlocks.md` lines 127–232
(cancel, launch, task lifetime).

### 5.2 Walk-in Trigger

**Executed:** the rectangle's `t` entry (public `0xd8`) dispatches the `trigger`
native with (ring name, 0) once. That happens only when K.warn is false and
the key is usable. A second walk-in on the same loaded script does not
dispatch again (script global one-shot). This holds in both hubs. The virtual
slot-3 call it makes on the named ring is `t3/research-story-route-r3`
`docs/story-route.md` lines 62–84. Its rendered effect is **Inferred**.

### 5.3 Ring props

**Executed:** the ring's `action1` entry (hub `0x4e9c`, hub2 `0x26ec`) dispatches
`autoPropSetState(name, 2)`, the looping state. `start` sets state 0. With
`actionatend=01`, the prop runs `action1` when its triggered state finishes.
That sequencing is **Inferred** from the property names, not executed. The
rings are visual only: no player-record write.

## 6. Jump gate (`Portal`)

Cited, not re-run (`t3/research-exits-walkin` `95760d9`,
`docs/exits-walkin.md` lines 111–190). The prompt (0x27d7a0) adds the current
level to the gate list, shows a first-visit prompt with only one destination, needs
nearby living party members, and otherwise is usable. Use (0x27d754) opens
`JumpGate_openMenu` 0x27da24. The menu's state 5 writes the pending level and
orientation 0xff (0x27e1a8–0x27e218). There is no fee. Arrival placement is the
`JumpGate_ctor` branch. The gate is separate from the mission map: it travels
only to levels already discovered (`t3/research-exits-r3` `e86f3de`,
`docs/exits-r4-travel.md` lines 10–69 for act and directory handling).

## 7. Save point

**Executed** on this branch (`tools/difftest_hub_npcs.py`,
`docs/spec/hub-npc-services.md` lines 91–92): the prompt goes through
`text_lookup`. Use requires `memcard_isBusy` and `menuMutex_isHeld` to return 0.
It writes object +0x84 = 1 and +0xc4 = 1, calls `memcard_requestSave`
0x2175b4, and writes no player-record byte (no fee). The screen it opens is
`t3/research-save-screen` `c8895e2` `docs/save-screen.md`: phases lines 22–31,
the save machine and its gates lines 181–299, and the client list lines
300–326 (`memcard_requestSave` opens only from card state −1 with a living
player, lines 246–253). Co-op resurrection at the point is
`docs/spec/hub-npc-services.md` line 92 (Observed, not executed here).

## 8. Client-implementable list

1. **Objects.** One NPC (dialog + `shop=1`), Savepoint, Portal gate,
   PushTrigger, walk-in Trigger and ring prop per hub. No trainer, bank, stash,
   healer or ambient talker. Critters and torches are decoration.
2. **Hub entry.** On each load run `start`'s services in section 4's order:
   mission bits, save inhibit, `V.store` by the store-level rule, flag 4, mana
   restore when `V.mana` = 1, the 17-site quest-item cleanup, the first-mission
   help, ring state 0. Then queue the two duplicate checks: 9 and 12 visited
   cells, one removal per item held more than once.
3. **NPC dialog.** Pick the start node by section 2's predicates in file order,
   falling back to node 0. Show only the choices whose guard is true. Run the
   chosen action before moving on, then follow next or close. Use section 3.2's
   tables, keyed by node index and public offset.
4. **Store.** A SHOP action sets the swoop to 0 and marks the store request.
   Open the store when the conversation ends: offline
   `shop_openOrStock(active, 0, 1)`. Stock comes from `V.store` and difficulty
   (vendor-stock). Never open it inside the dialog.
5. **Mission offers.** END and SHOP on an offer node set A(k) (and a quest where
   marked). The two choices differ only in the store. Missions 8 and 9 are
   never offered by the NPC. Do not wire the backup-only writers.
6. **Mission map.** Key = section 5.1's rule, including the mission-12 quirk.
   Use: warn while a started mission is incomplete. Otherwise write the hub's
   entrance and open the menu, unless a dialog is open or recall is counting.
   The menu itself follows story-route-r3 §6.
7. **Walk-in.** Dispatch the ring trigger once per hub load under the same gate.
8. **Jump gate and save point.** As cited in sections 6 and 7. No fees anywhere.

**Still Unknown:** physical proximity/use of these specific objects in a live
session; dialog text, voice and camera pixels; who reaches `L-INN` and the
cutscene entry `0x34a4`; the stack-read store index; the actual bag cell that
`removePlayerItem` deletes; whether the native client reproduces any of this.

## 9. Verification (both seeds)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_hub_services.py","--elf","local/SLUS_209.73","--data","<disc>/BG/DATA"]; runpy.run_path("tools/difftest_hub_services.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_hub_npcs.py","--elf","local/SLUS_209.73","--iso","local/disc.iso"]; runpy.run_path("tools/difftest_hub_npcs.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,unittest; unittest.main(module=None, argv=["u","discover","-s","tools","-p","test_*.py"])'
```

`--data` may be replaced by `--iso` for the disc image. The difftest needs the
Git object `2ab82b2` (and `334578d`, which that file loads) in the local
repository. Results are in `work/cursor-report.md`. The retained PASS logs are
in untracked `local/hub-services-*.log`.

**Stubs, disclosed per claim group:**

- Conditions, actions, entry and travel: the plain script rig
  (`difftest_natives.Rig`) runs real handlers and stubs every `ref_natives.EXT`
  service. `dialog_isOpen`, `inventory_findItemBySubstring` and
  `inventory_countItemByName` are answered as each case states. All other
  stubs (`missionMenu_open`, `shop_openOrStock`, `hud_showHelpMessage`,
  `text_lookup`, `inventory_removeItem`, ...) return 0 and are recorded.
- Conversations: the pinned `Probe` runs the real dialog machine with synthetic
  localisation and the seeded `difftest_natives.Responder` for the other
  services. Its `dialog_isOpen` 0x22fbc0 is a stub. Here it is answered 1,
  because a choice action runs inside the open dialog's message handler
  (`docs/dialog.md` line 271). Without that override the store branch follows
  the responder's random answer: seed 20973 then takes the offline-open branch
  for some states.
- Player objects for the duplicate checks are zero-filled synthetic blocks.
  There are one to four players. Nothing is loaded from a save.
