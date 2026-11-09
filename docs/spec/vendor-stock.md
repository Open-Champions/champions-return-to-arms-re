# Vendor stock generation — addressed execution contract

Research date: 2026-10-27. Private executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
This extends the vendor findings at `e2ff7e3` and loading-readiness findings
at `9dd4904`; neither branch is merged here. It resolves their unknown stock
budgets and fixed-descriptor count within the fixtures below. It does not
establish a running-game shop, successful resource I/O, or native readiness.

**Observed** denotes addressed original instructions; **Executed** denotes
those instructions run in `tools/ee_emu.py`; **Inferred** denotes a port
consequence; **Unknown** is deliberately unsupported. All floats below use
the interpreter's default PS2 model, not a console measurement.

## Inputs and refresh boundary

**Observed / Executed** (`difftest_vendor_refresh.py:dispatch`, `timing`,
`stock_refresh`, `menu_preserves_stock`): the session slice
0x323064–0x323104 compares the destination at 0x41b721 against four private
identifiers, read at runtime from 0x554678, 0x554680, 0x554688, 0x554698.
They dispatch `stock(0,1,1)`, `stock(0,1,1)`, `stock(0,2,1)`, and
`stock(0,3,1)` respectively. A nonmatch does nothing. Repeating a matching
destination dispatches again; no previous-stock timestamp or populated-count
gate is consulted. The call occurs after deferred script dispatch, equipment
warm-up and the applicable peer barrier, before loading-screen stop 0x3224d8.
The equipment/peer services are controlled in this ordering probe; watchdog
escape is not proof of actual readiness.

**Observed / Executed** at 0x1c7ba8: mode 0 takes the menu branch and preserves
all three stock buffers. Modes 1, 2, 3 take the same generation body; caller
slot and the third argument do not specialize its items. The body requests
resource 0x538678 through 0x173558 before generating; these tests assert that
request and stub the resource loader.
The complete function returns synchronously after sorting at 0x1c8724.

**Observed / Executed**: two reads through 0x1ed778 at 0x1c7b40 and
0x1c7bc0 use the variable selector at 0x538750. The first read controls scale;
the second controls budget. Difficulty is read at 0x4f719c. The outer body
does not directly read current act 0x88d3d4, monster level 0x4f714c, player
level at record +0x58, or player count 0x4d8ae0. Inner armour generators
0x104ca4 / 0x104758 **do** read player count and class at
`0x4d8af0 + slot*0x4c30 + 0x50`. Their class-4 fraction changes exclusion,
preference and shared RNG consumption (56 executed prefix cases).

**Observed / Executed** (`act_clear`, `act_compare`): the pre-load block
0x320f8c–0x321020 can clear quest variables via 0x1ed728 on an act change,
subject to frontend state, card latch 0x4f8f28 and death-task guards.
**Inferred**: acts affect stock indirectly through this clear and through
the scripts that later store `storeLevel`. The stores, including the one
computed store in each hub, are under "Progression input `storeLevel`" and
"`storeLevel` by mission progress" below. Do not replace the variable with
character level or the act number.

**Observed**: direct calls to 0x1c7af8 occur at 0x116c58, 0x144074,
0x1440c4, 0x18dbb4, 0x22f850, 0x22f86c, 0x3230c4, 0x3230f0; a tail jump
occurs at 0x1eccf0. Only the two session sites supply nonzero modes in these
paths. The command at 0x144010 selects/defer-opens a store, not new stock.
The separate daemon run 0x1d1490 calls 0x1c8a00 after signed frame elapsed
>=121 (seven executed boundary cases). **Observed** (`restock_cases`):
`ShopDaemon_ctor` 0x1d13c8 has no `j`, no `jal`, no address reference, and
no data pointer. `ShopDaemon_run` is the vtable word at 0x50d78c and is not
itself called. Nothing constructs the daemon, so the 121-tick path is not a
live route and is not the ordinary refresh schedule.

## Budgets and descriptor selection

**Observed / Executed** at 0x1c7b48–0x1c7cd8, compared with
`ref_vendor_stock.budget_contract`. Let `s` be the first variable read, `t`
the second, and `d` difficulty. Ordinary fixtures use 0..11 and 1..5; an
out-of-range first read resets scale, but does not sanitize the second read.

1. Set `q=s` for `0 <= s <= 11`, otherwise `q=-1`. Scale is
   `max(1, f32(f32(q * 0x3eaaaaaa) + 1))`.
2. Form signed integer `1600 * (t + 11*(d-1))`, convert to float and compute
   `powf(x, 0x3f999999) + 0x45dac000`. Call this `B`.
3. `low = trunc(B * 0x3f199999 - 0x453b8000)`;
   `high = trunc(B * 0x3fc00000 + 0x45bb8000)`.
4. The three integer steps are `(high-low)/22`, `/17`, `/6`, truncated toward
   zero. Attempt budget is `low + (progress+1)*step`, not `low+progress*step`.
5. Weapon/armour cap is `trunc(float(24*d-24) + scale*4) + 2`.
   Other ordinary-item cap is `trunc(float(24*d-18) + scale*4)`.
   Every optional special uses the weapon/armour cap.

Each operation is separate raw-float arithmetic; host double expressions may
give different integers. `ref_items.powf` remains unchanged. **Unknown**:
negative power bases, overflowing inputs, out-of-contract difficulty and
actual hardware low-bit rounding. The new reference refuses second reads
outside 0..12 and difficulty outside 1..5.

**Observed / Executed** (`difftest_vendor_stock.py:run_case`): exactly seven
direct fixed-parser calls precede ordinary generation across the three lists.
Four seed the first list from descriptors at 0x538760, 0x538768, 0x538778,
0x538788 (call sites 0x1c7cd4, 0x1c7d14, 0x1c7d44, 0x1c7d74). None seed
the second. The third receives two descriptors through pointer cells
`0x4f4280 + offset` and `0x4f4258 + offset`, then descriptor 0x5388e8.
All calls supply variant -1 and preset flag 0. Their counts increment before
parsing; the parser return is ignored.

At 0x1c81b0–0x1c8368, `offset = tier - 12*min(d,3)` where tier is 44 for
scale <=1.5, 40 for scale <=3.5, otherwise 36. These are byte offsets in
runtime pointer arrays, not literal item names or copied tables. The
executable-backed descriptor contents stay private.

## Counts, retries, duplicate regions, and sorting

**Observed / Executed**: storage starts at 0x866e78, three lists with stride
0x1208 and 64 records of 0x48 bytes; counts are at +0x1200. Counts are reset
individually; whole arrays are not cleared. The first list's fixed four plus
22 accepted ordinary records produce 26 before its special. The second
accepts 17 ordinary records. The third has three fixed records and only six
ordinary **attempts**, so its pre-special count can range from 3 to 9.
Optional specials add at most one per list: normal returning paths therefore
have counts 26..27, 17..18, 3..10. Counts are entries, not the quantity inside
each item record. Fixed and generated quantities come from the original parser
and item definitions, and are included in the defined-byte comparisons.

**Observed / Executed**, first loop 0x1c7d90–0x1c7e94:
call 0x104ca4 with category 0 and suffix request -1. Failure retries the
same progress/budget. A successful duplicate is rejected up to six times;
the seventh can pass. Bit 40 rejects the candidate even after duplicate
retry allowance is exhausted. Acceptance increments count and progress,
and resets the duplicate retry counter. There is no overall retry limit.

**Observed / Executed**, second loop 0x1c7fd8–0x1c80b4:
category 1, suffix request -1; same acceptance/retry progression, with no
outer bit-40 exclusion. The duplicate scan starts at 0x869288, the **old
third list**, not the second list. It runs for the current second-list count.

**Observed / Executed**, third loop 0x1c8398–0x1c8488:
category 2, suffix request 1. Progress advances even on generator failure,
duplicate rejection, or suffix byte +0x21 equal to 0xff. The duplicate scan
starts at 0x86b698, **outside the three stock arrays**, for the current
third-list count. These two scan offsets are asserted against original call
arguments at 0x1c8070 and 0x1c8428. They must not be silently corrected.
**Observed** from the existing deferred-queue layout (`script.md` §2.4,
enqueue 0x1ed52c): 0x86b698 is inside the name-buffer region beginning at
0x86b278, not an unused fourth stock list. Deferred names do not match a
definition address; see "Fixed-item bytes and the name-buffer scan" below.
Do not clear that buffer as a shortcut, and do not clear the previous third
list before the armour scan.

**Observed / Executed**: identity helper 0x108924 compares a non-null second
definition pointer, equal definition, flags, and the whole word at +0x20.
The unwritten halfword +0x22 participates; quantity does not. Eight direct
controls distinguish these cases. The new `same_raw` helper deliberately
does not change the existing `ref_items.same_identity` API or vectors.

**Observed / Executed** at 0x1c8588–0x1c8724: all populated lists are sorted
by ascending signed `item_getValue` (0x1024a8). Swaps copy every byte of the
0x48-byte record. Equal-valued records keep their order. Synthetic equal
values and complete generated lists are compared with an independent stable
sort using the reference valuation.

## Item selection and the two RNG streams

**Observed / Executed**: ordinary and preset calls execute the existing item
module, with selection compared against unchanged `ref_items` (§7 of
`items.md`). Ordinary selection filters definitions by category, cap and
flags; weapon/armour groups and class-4 preference alter eligible rows.
Weapons evaluate 15 rounds, other categories 10, selecting the most valuable
candidate within budget (later equal-valued candidates replace earlier ones).
Prefix/suffix eligibility, parser variant draws and required-level assignment
remain the item module's rules, not a new vendor-specific selection table.

**Observed / Executed** at 0x1c7ea0, 0x1c80c4, 0x1c8498: exactly three
outer draws use seed 0x404460, one after each ordinary loop. Each updates
`seed = seed*0x19660d + 0x3c6ef35f` modulo 2^32 and tests
`float(seed>>16) * 0x37800000 < 0x3dcccccc`. When true, call 0x104758.
No fourth outer draw occurs. Parser/generator draws use shared seed
0x404464; the complete comparison maintains a separate reference RNG
continuously through the entire pass.

Special budgets are `2*(low + n*step)` with n=22, 17, **10** for the three
categories. The third special does not use n=6. The intermediate original
int-to-double-to-int calls do not round the supported integer range.
The outer code appends if the output definition pointer is nonzero, ignoring
the generator return value. It performs no outer duplicate, suffix or bit-40
filter on special records. The probe controls both contradictory return/pointer
cases, and separately executes all three real special generators in one pass.

**Inferred**: reproduce both seeds and the shared-seed consumption order;
replacing this with independent per-item seeds changes stock and future RNG.
`docs/issues/sync-breakers.md` §2 records prior analysis of seed equality at
the ordinary loading boundary. This study varies them independently to test
the stock routine, not to claim live divergence.

## Verification and remaining gates

`tools/difftest_vendor_stock.py PRIVATE_EXECUTABLE` runs original control
flow, arithmetic, raw identity and sorting with synthetic item services.
`--real --extended` additionally executes all parser/generator/value functions
for complete lists across both seeds, difficulty 1..5, modes 1..3, multiple
party compositions and stack residue fills. `--special-only` executes a full
pass with three successful special-roll decisions. Output contains counts
only; private records are never printed or stored in tracked files.

The full-pass comparison independently checks dispatch sequence/arguments,
generator return, every **defined** record byte, shared RNG at each boundary,
the final cosmetic seed, counts, duplicate addresses and final sorted raw
records. `stock_plan` consumes executed raw candidate records to preserve
undefined bytes and then models outer control independently. It is therefore
not an independent reconstruction of all uninitialized memory.
Successful generator returns must be exactly 1; failures must be exactly 0
and preserve the whole destination. Four directed original-generator controls
check both empty eligibility and no-budget-fit failures. Five deliberately
wrong reference mutations (budget, duplicate handling, fixed count, special
selection, sorting) must be rejected by the original-code comparison.

`tools/difftest_vendor_refresh.py PRIVATE_EXECUTABLE` adds 388 EE cases and
three static checks for dispatch/timing, repeat refresh, menu preservation,
variable/act clearing, class fraction and the dormant daemon. It explicitly
stubs item generation, resource I/O, valuation and power where those are not
the subject of its control-flow checks.

**Unknown / port gates** that this round does not remove:

- Termination is bounded only in probability. The first two lists have no
  retry limit; "Generation failure" below shows that no supported input
  failed any of 20 reference calls at its smallest budget. That is not a
  fixed upper bound.
- Resource loading completion, persistence/save transactions and exact
  readiness integration. A synchronous stock return on this fixture does not
  complete these other services.
- Real controller/shop rendering, native C++/Godot parity, two-machine stock
  equality, and continuous gameplay. No client files were changed here.
- A loaded save that skips `start` (byte 0x4f8b58) keeps whatever
  `storeLevel` the restored variables hold; that restore was not executed.

## Buy and sell prices

**Observed / Executed** (`difftest_vendor_close.py:price_cases`, 68 cases,
seeds 20973 and 7): `shop_buy` 0x1d1240 and the sell arm of `shop_onMsg`
0x1c5d28. Neither draws `g_randSeed` 0x404464. The reference is
`ref_vendor_stock.buy_price` and `sell_credit`, using the same PS2 float
operations as `ref_items`.

Buy factor starts at 0x3f199999. Definition category byte +0x1d equal to 1
selects 0x3ee66666. Record flags `& 0x30000000000` or definition slot byte
+0x1c equal to 8 selects 1.0 (0x3f800000) afterwards, so that override wins.
Price is `cvt.w.s` of `cvt.s.w(value) * factor`, toward zero. For value 100
the first two factors yield 59 and 44. Signed gold at player +0xe4 is
compared with `slt`. When gold covers the price, the debit is stored in the
delay slot of `inventory_giveItem` 0x1c1868 (0x1d1308–0x1d130c) and the
return value is ignored. Short gold makes no call. The stock record is not
consumed.

Sell reads the bag cell at record +0x130 + index*0x48 + bag*0x1208 with no
empty-cell test. It multiplies the value by 0x41a00000 when slot +0x1c is 8,
when the definition name contains the stem at 0x538660, or when definition
flags `& 0x1c0000000000`. Credit is `cvt.w.s((amount / count) * 0x3d4ccccc)`,
at least 1, then forced to 0 when slot is 8 or definition flags
`& 0x400000000000`. A count of 0 uses the model's division-by-zero pattern
and still completes. Gold is a 32-bit add, then capped at 99,999,999
(0x1c5eb4–0x1c5ecc). `inventory_dropItem` 0x1c4310 is a tail call after the
credit (0x1c5f18). Type 2 does nothing. Type 0 reaches `shop_buy`.

## Gold restock is not the session refresh

**Observed** (`restock_cases`): `shop_restockByGold` 0x1c8a00 has `jal`
sites only at 0x1d1474 and 0x1d14b4, and no `j`, address reference, or data
pointer. `ShopDaemon_ctor` 0x1d13c8 has empty `j`, `jal`, address-reference,
and data-pointer sets. `ShopDaemon_run` 0x1d1490 has those same empty call
and address-reference sets, and one data pointer, the vtable word at
0x50d78c. Nothing constructs the daemon. The 121-tick run remains the
dormant path already executed when that function is called directly
(`difftest_vendor_refresh.py:dormant_daemon_boundary`).

**Observed / Executed** (`restock_cases`, both seeds, gold 0, 1, 2, 100,
1600, −1, −3, 0x7fffffff and −2147483648): the function reads player 0 gold
at 0x4d8bd4 and does not draw either seed. It forces the three counts to
1, 0 and 1, then calls `item_appendGeneratedUnique` 0x107d54 forty-five
times: lists 0x866e78, 0x868080 and 0x869288, categories 0, 1 and 2, and
for each list the budgets gold/2 toward zero, gold, and the 32-bit gold<<1.
Each budget is attempted five times. The attempt index is passed in a2 and
ignored: 0x107d5c overwrites a2, and the generator call at 0x107df4 passes
suffix −1 and level 1 in t0. A client stocking a shop from the session
caller must not call this function and must not restock every 121 frames.

## Fixed-item bytes and the name-buffer scan

**Observed / Executed** (`residue_cases`, 8 cases, both seeds): parsing the
fixed descriptors 0x538760 and 0x5388e8 into a destination filled with 0x00
and again with 0xa5 produces the same bytes, and those bytes match
`parse_descriptor(...).pack` of a zero stale buffer. Those two descriptors
do not keep the previous destination. The seven fixed stock records are
therefore the parser's own bytes, not an unknown stack image.

**Observed**: the only instructions that form 0x86b278 are the addiu sites
0x1ed584 (`script_queueDeferred`) and 0x1ed5ec (`script_runDeferred`). The
category-2 duplicate scan at 0x86b698 is 0x10 bytes into name slot 13 of
half 0 (stride 0x50). **Executed** (`name_cases`): 53,903 four-byte windows
of level-script strings and entry names were compared with every loaded
definition address; none of the nonzero words matched, and the window count
is asserted. Queueing a name into that slot with `script_queueDeferred`
0x1ed52c (flip 1, queued 13), after the 0x50 bytes at 0x86b688 were filled
with a nonzero sentinel, stores the name at the start of the slot. The
stored record and the scan record at 0x86b698 are both nonzero, and
`same_raw` fails against every loaded definition address. A zeroed slot is
not that negative result. While that buffer contains only deferred names,
the category-2 scan does not reject a candidate. The armour scan of the
previous third list is a different region and still can reject; do not
clear it before the armour loop.

## Progression input `storeLevel`

**Observed**: the only addiu sites that form the selector 0x538750 are
0x1c7b0c and 0x1c7bc4, the two reads inside `shop_openOrStock`. No other
instruction forms that address, so no C function stores it by this pointer.

**Executed** (both seeds, library calls stubbed, stop 0x1c7c34): when
0x86da80 is empty, those reads create the name at value 0 and the scale
register f23 is 1.0. The shared seed is unchanged.

**Executed** (`name_cases` disc walk, counts only): the literal `setv`
values are `hub` and `hub2` each `0, 8, 7, 6, 5, 7, 6`, `stobonus` `7`,
and `islgnome` `3`. Each of `hub` and `hub2` also has one `setv` whose
value is not a pushed constant; it is decoded below. `getv` 0, `addv` 0,
and no non-script file contains the name. All sixteen literals are inside
0..11, so they use the scale formula rather than the out-of-range reset.
Act-change clearing to 0 remains the executed path in
`difftest_vendor_refresh.py:act_clear`. A save restore can still write the
byte; that is the generic quest-variable load, not a second formula.

## `storeLevel` by mission progress

Round 3, 2026-11-09. `tools/difftest_vendor_progress.py` group `store`
(lines 167–219) and group `acts` (lines 223–261); reference
`ref_vendor_stock.hub_store_level`. Script offsets are into each archive's
`script.scr` code; no script bytes are copied here.

**Observed** (decoded with `ref_amx`, lines 90–129 and 170–181): every
`storeLevel` store in `hub` and `hub2` is in the entry `start`. Hub stores
sit at 0x29fc, 0x2aa8, 0x2b18, 0x2b88, 0x2bc4, 0x2c3c, 0x2cb4 and 0x2d1c;
hub2 at 0x2cc, 0x378, 0x3e8, 0x458, 0x494, 0x50c, 0x584 and 0x5ec. The
computed store (hub 0x2d1c, hub2 0x5ec) follows `getv(currentMission)`
0x34 bytes earlier (hub 0x2ce8, hub2 0x5b8) and pushes that result minus
1: `stack`, `move.alt`, `const.pri 1`, `sub.alt`, `push.pri`, then the
name and the argument size. So it is `setv(storeLevel, currentMission-1)`.
The literal 8 is the constant that the `scr.py` listing prints as a string
name; the argument of `getMissionAvailable` in the same `start` is the same
constant 8.

**Executed** (lines 196–217, both hubs, seeds 20973 and 7, original
`scr_load` / `scr_interpret` / `script_runByName` with `vars_set` 0x1ed854
recorded; engine services are the named `difftest_natives.Rig` stubs).
With `c = currentMission` (absent counts as 0) and the active difficulty
row of the player's mission bytes (bit 0 available, bit 1 complete):

| `c` | stored `storeLevel` |
|---|---|
| 0 or absent | 0 |
| 1..6, 10..13 | `c - 1` |
| 7 | 8 if mission 9 is complete; else 7 if mission 9 is available; else 6 if mission 8 is available; else 5 |
| 8 | 6 |
| 9 | 7 |

Each run makes exactly one store and the variable then reads back that
value. All 16 byte pairs of missions 8 and 9, on difficulty rows 0 and 2,
match the table; bytes planted on another difficulty row are ignored
(lines 209–212). `stobonus` `start` stores 7 and `islgnome` `start` stores 3
whatever `currentMission` holds.

**Observed** (lines 182–195, census of all 23 archives that name the
variable): only `hub` and `hub2` read `currentMission`, and only mission
levels store it, once each, as a literal inside `start`:

| mission | levels that store it |
|---|---|
| 1 | `blood1` |
| 2 | `innovat1` |
| 3 | `islc1`, `islcave1` |
| 4 | `wat1`, `water1` |
| 5 | `tormenta` |
| 6 | `swamp1`, `swamp2` |
| 7 | `valor` |
| 8 | `fire1`, `obsfor1` |
| 9 | `storm1`, `storm2`, `storm4` |
| 10 | `fay1`, `fay2` |
| 11 | `nit1`, `nitmar1` |
| 12 | `bossgood`, `bossevil` |

Whether every one of those `start` stores is unconditional was not checked
here; the cited story-route research executes some of them.

**Executed** (lines 223–261): `save_findAct` 0x217d30 searches the current
act's table first, by prefix, then every act from 0. From every current act
-1..12 (13 acts at 0x4f8e7c), `hub` and `hub2` resolve to the current act
(act 0 from -1). So `save_actChanged` 0x217f70 reports no change when the
party returns to a hub, and the pre-load clear at 0x320f8c does not run.
Mission levels resolve to their own act from any current act: `blood1` 0,
`innovat1` 1, `islc1` 2, `wat1` 3, `tormenta` 4, `swamp1`/`swamp2` 5,
`valor` 6, `fire1` 7, `storm1`/`storm2`/`storm4` 8, `fay1`/`fay2` 9,
`nit1` 10, `bossgood`/`bossevil` 11. `islcave1`, `nitmar1`, `obsfor1` and
`water1` are in no act table, which is never an act change.

**Observed** (`docs/script.md` §2.1 lines 427–432 and its table line 450):
`level_loadScriptAndObjects` 0x217978 runs `start` (call 0x217bac) during
the level load, unless the byte at 0x4f8b58 is set. The session stock call
at 0x3230c4 / 0x3230f0 runs after the load ("Inputs and refresh boundary").
So the `storeLevel` a shop generates with is the one its own `start` just
stored.

**Inferred**, from the rows above and the audited story route
(`t3/research-story-route-r3` `019a155`, `docs/story-route.md` §§1 and 6;
`t3/research-mission-unlocks` `7b924e1`): entering a mission level in a new
act clears the quest variables (0x1ed728) and then that level's `start`
stores `currentMission`. Later hub and hub2 visits in that act keep it. The
hub shop level is therefore 0 before mission 1 starts and after mission 1
starts, then 1, 2, 3, 4, 5 after missions 2..6 start, the mission 7 row
(5..8) after `valor` starts, 6 after mission 8 starts, 7 after mission 9,
then 9, 10, 11 after missions 10, 11, 12. The `islgnome` shop is always 3
and the `stobonus` shop always 7. The audited story research executes the
fresh hub branch (`c = 0`), the menu's mission order and act resolution
from acts -1 and 0; the mission-unlocks research supplies the availability
bits. Neither plays a mission level's `start` into a later hub visit, so
this mapping is a consequence of the act rule, not a played sequence.

## Generation failure

`tools/difftest_vendor_progress.py` group `failure` (lines 265–379).

**Executed** (lines 297–308, both seeds, item services stubbed and named in
`stock_rig`): when the category-0 or category-1 generator returns 0 for K
calls in a row (K = 1, 6, 40) and then succeeds, every failed call and the
next one carry the same budget, suffix request, level cap and list count,
and the shared seed is not drawn by the loop. The pass then returns with
counts 26, 17 and 9. A failure therefore costs a retry, not a slot.

**Executed** (lines 309–315): the third list makes exactly six attempts
whatever fails, and its count is 3 plus the successes.

**Executed** (lines 316–326): a category-0 or category-1 generator that
always fails is called more than 500 times in 400,000 instructions with an
identical argument and count row, and the function never returns. That is
the original's behaviour: there is no overall bound.

**Executed / reference** (`fit_cases`, lines 331–379): at the smallest
budget of each list (progress 0, `low + step`) for every `storeLevel` 0..11
and difficulty 1..5, both categories and both seeds, 20 consecutive calls
of the unchanged `ref_items.generate_with_affixes` never fail: 240
contexts, 4,800 calls, longest failure run 0. The original 0x104ca4
at the two extremes (`storeLevel` 0 difficulty 1, `storeLevel` 11
difficulty 5) matches that reference return and shared seed call by call
(32 calls). Budgets only rise with progress. **Inferred**: within
the supported inputs each call has a positive success chance, so the loops
end with probability 1; a generator change that empties a group at some
level would hang the original.

## Shop menu state machine

`tools/difftest_vendor_progress.py` group `menu` (lines 383–636); reference
`ref_vendor_stock` `choice_step`, `list_cancel`, `buy_allowed`. Executed
with the original `shop_task` 0x1c6068, `shop_run` 0x1c74c0,
`shop_buySellMenu` 0x1c6bb8, `menu_cursorInput` 0x1c6570 and helper
0x1c6438, join scan 0x1c5b48, `itemList_update` 0x1d14c8, `itemList_input`
0x1cd988 and `shop_close` 0x1d0ab8 live, both seeds. Stubs (lines 383–392):
local slot 1, resource ready 1, a 32×32 texture header, item value 100,
item weight 1.0, one-cell picture size; drawing, text, sound, network,
menu-state message and task calls return 0 and are recorded. The stock and
bag grids come from the original `itemGrid_build` 0x1cbbe8 into test
buffers at `g_itemListCells` 0x4ebbb0 and 0x4f4228. No frame is rendered.

Panels are at 0x86a4b0 + panel×0x74: +0x4c state, +0x18 row, +0x14 cursor
direction, +0x3c cursor animation, +0x34 pad slot, +0x54 saved row. Pad
words are at 0x4028d0 + slot×0x58: +0x8 held, +0xc pressed, +0x10 held.
States: 3 Buy/Sell choice, 0 stock list, 1 own bags, 2 idle.

| from | input | to, effect | evidence |
|---|---|---|---|
| closed | `shop_openOrStock(slot,0,_)` | panel 0 state 3 with pad slot 0; panel 1 state 2, slot -1; `g_shopOpen` 1; offline pause 1 | lines 469–473 |
| 3 | Up / Down held (0x1000 / 0x4000, or 0x100000 / 0x200000) | direction ±1 when another row exists; +0x3c rises by 0x3dba2e8b a tick; the row changes on the 11th tick | lines 474–488 |
| 3 | confirm while +0x3c ≠ 0 | ignored | lines 480–481 |
| 3 | confirm, row 0 | state 0; `menu_resetListState` 0x1d1380 | lines 497–498 |
| 3 | confirm, row 1 | state 1; 0x1c4e88(slot, panel, 0) | lines 489–492 |
| 0 or 1 | cancel | state 3, row restored from +0x54; sound 0x1cdb34 | lines 492–495, 533–535 |
| 0 | list confirm over a stock cell | the checks below, then shop msg 0 | lines 500–526 |
| 1 | list confirm over a bag cell | the sale sequence below | lines 537–584 |
| 0 or 1 | any, while lockout 0x41b4fc ≠ 0 | the list reads the zero pad 0x86a6b0; cancel ignored | lines 529–532 |
| 3 | cancel | state 2, unless the panel's word at 0x4f4878 or 0x4f4880 is set | lines 585–590 |
| 2 | next tick, both panels 2 or one player | 0x1de0dc, `shop_close`: `g_shopOpen` 0, lockout 60, pause 0, task removed | lines 592–600 |
| 2 (panel 1) | another living local player presses confirm | panel 1 state 3 with that pad slot; `itemGrid_build` | lines 612–622 |
| any | shopper HP ≤ 0 | state 2, but only on the offline two-player path of `shop_task` | lines 602–611 |

**Executed**: the choice uses the masks at 0x41bfbc (confirm) and 0x41bfb8
(cancel). The lists confirm with 0x41b970 instead, and the choice confirm
does not buy (lines 527–528). `game_initCamera` 0x1e6b68 writes them by the
region byte 0x41b69c. The shipped `.data` byte is 1: confirm 0x40, cancel
0x20, list confirm 0x80. Region 0 writes 0x20, 0x140 and leaves 0x41b970
at its static 0; other values write nothing (lines 623–636).

**Executed buy checks** (lines 500–526, value 100, price 59): gold below
the price shows a message (0x1d9954) and sends nothing; a bag count of 64
at player +0x1330 plays a sound only; carried weight +0x120 plus the item
weight above capacity +0x124 shows a message and calls 0x1b7ba8. Otherwise
`shopmsg_sendBuy` 0x1c5f78 gets the slot and the grid cell address, then
0x1bec10. The sender does not change gold; `shop_buy` on the receiver
debits ("Buy and sell prices").

**Executed sale** (lines 537–584): a list confirm sets the pending word
0x86a680 + panel×4 and is handled in the same tick. Record flag bit 38
refuses with a message. If `0x1c41d8` (the record is one of the player's
equipped pointers) is true, the yes/no prompt 0x1dadc0 runs with the
panel's 0x4f4880 word at 100: result 0 keeps the sale pending and holds
cancel, 1 abandons it, 2 sends. A send writes the 13-byte shop msg 1
(type 1, slot, …, mode 1) through 0x13db38, clears pending, sets 0x4f4218
+ panel×4 to 3 and sets byte +0x47a of the object at player +0x43d8; that
byte holds a second send.

**Unknown**: pixels, the analogue free cursor beyond the tested cell, net
play (0x402791 set) beyond the single-panel path, who clears byte +0x47a,
and stacked-item quantity entry.

## What a client can implement

1. On a load whose destination is one of the four names at 0x554678,
   0x554680, 0x554688 and 0x554698, generate stock with mode 1, 2 or 3
   as that caller does. Repeat the generation on every such load. Mode 0
   opens the shop and keeps the lists.
2. Use `storeLevel` (default 0, including the creating read), difficulty
   at 0x4f719c, both seeds, and the class-4 fraction for armour. Apply the
   budget, retry, duplicate-scan and stable sort contract above. Keep the
   previous third list until armour generation has finished scanning it.
3. Take fixed records from the parser. Take ordinary and special records
   from the existing item generators. Do not invent a 121-tick restock and
   do not call 0x1c8a00.
4. Charge `buy_price` and credit `sell_credit`. Debit before `giveItem`
   and ignore its result. Credit before `dropItem`. Cap gold at 99,999,999.
5. Treat a category-2 duplicate scan of deferred names as a non-match.
   Keep the scan address.
6. Get `storeLevel` by running each level's authored `start`, or, for a
   client that does not run scripts, from `hub_store_level(currentMission,
   mission bytes)` in `hub`/`hub2`, 7 in `stobonus` and 3 in `islgnome`.
   Store `currentMission` from the mission level's `start`, clear quest
   variables only on an act change, and do not treat a hub return as one.
7. Retry a failed weapon or armour attempt at the same budget with no slot
   used, give the third list exactly six attempts, and keep the loops
   unbounded as the original does; a safety cap is a deviation and must be
   stated as one.
8. Drive the shop with the state table in "Shop menu state machine": choice
   3, lists 0 and 1, idle 2, the 11-tick cursor, region-1 masks 0x40 / 0x20
   and list confirm 0x80, the local buy checks, the pending sale with the
   equipped prompt and send latch, the two-player join, close on idle and
   lockout 60.
9. Refuse only for the gates still listed above: resource completion,
   save-load `storeLevel`, rendered UI and pixels, net-play menus, and
   save I/O.
