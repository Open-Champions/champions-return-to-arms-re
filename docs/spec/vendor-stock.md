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
the scripts that later store `storeLevel`. The authored literal stores are
listed under "Progression input `storeLevel`" below. Do not replace the
variable with character level or the act number. The two non-literal stores
stay unknown.

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

- Termination when all possible candidates fail or the first two lists never
  accept enough records. The original has no overall bound; the probe has an
  instruction limit and the reference scheduler is a resumable generator.
- Resource loading completion, persistence/save transactions and exact
  readiness integration. A synchronous stock return on this fixture does not
  complete these other services.
- Real controller/shop rendering, native C++/Godot parity, two-machine stock
  equality, and continuous gameplay. No client files were changed here.
- Which of the authored `storeLevel` literals is live on a given visit, and
  the two non-literal stores in `hub` and `hub2` (below).

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
value is not a pushed constant. `getv` 0, `addv` 0, and no non-script file
contains the name. All sixteen literals are inside 0..11, so they use the
scale formula rather than the out-of-range reset. **Unknown**: the two
non-literal expressions, and which literal is current when a shop level
loads. Act-change clearing to 0 remains the executed path in
`difftest_vendor_refresh.py:act_clear`. A save restore can still write the
byte; that is the generic quest-variable load, not a second formula.

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
   Keep the scan address. Refuse a shop only for the gates still listed
   above: unbounded failure, resource completion, the two non-literal
   `storeLevel` expressions, rendered UI, and save I/O.
