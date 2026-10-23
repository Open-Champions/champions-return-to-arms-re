# Hub vendor and shop contract — SLUS-20973 v2.00

Research date: 2026-10-23. Executable SHA-256:
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
`tools/ref_vendors.py` is the bounded pricing reference and
`tools/difftest_vendors.py` executes original functions in `tools/ee_emu.py`
with seeds 20973 and 7. **Observed** means an executable address or inspected
private archive structure, **Executed** means a named function ran on a
constructed EE fixture, **Inferred** connects these observations, and
**Unknown** is a port refusal. No claim here is a running-game screenshot.

This uses `t3/research-inventory-screen` (`4a8a78a`) for the common item
grid, `t3/research-items` (`49bc578`) for record/value/generator rules, and
`t3/research-story-route` (`703362e`) for the hub conversation. Those are
research inputs, not commits merged into this branch.

## Engaging the hub vendor

**Observed** in the private `HUB.GOB` `objects.ob`: hub object 10 is an `NPC`
with `name=firiona`, `dialogscript=startDia3314`, and `shop=1`. This is the
only `NPC` record in that archive. `tools/difftest_vendors.py:hub_vendor`
checks these properties and the NPC count against the SHA-256-pinned private
`HUB.GOB`; it does not commit archive data. `Creature_interact` 0x116bd8 reaches
`script_startDialog` 0x143824; `dialog_start` 0x22fa50 owns the dialog.
The story-route research executed the fresh-state dialog conditions and its
two ending script actions, one of which calls `activateStore`. It did not
execute the entire proximity/use → dialog choice → shop sequence as one run.
The exact controller approach and choice timing are **Unknown** here.

**Observed** `activateStore` 0x144010 writes an accepted store index (<21)
to 0x4f7150. While dialog is open it sets pending flag 0x4fdd30; dialog-end
code at 0x22f868 later opens the shop. Otherwise the offline path calls
`shop_openOrStock(activePlayer,0,1)` at 0x144070; network play first closes
local menus, then opens a shop only for living local slots (0x14405c–0x1440c4).
This agrees with `docs/script.md` and the `HUB.scr` script structure. Some
shipped hub `activateStore` calls declare an argument without pushing it;
`docs/spec/script-machine.md` §9 records that malformed-call boundary. The
hub NPC must therefore run its authored script, not a made-up vendor trigger.

## Stock and opening

**Observed** `shop_openOrStock` 0x1c7af8 has distinct modes. Mode 0 opens the
local interface. The level-session loop calls modes 1/2/3 at 0x3230c4 and
0x3230f0 after loading `hub`/`hub2`, `islgnome`, or `stobonus` respectively.
The persistent stock at 0x866e78 is three lists of 64 × 0x48-byte records,
each followed by a count, stride 0x1208. Count addresses are 0x868078,
0x869280, and 0x86a488. They represent weapons, armour and other items.

**Observed** stock mode reads quest variable `storeLevel` through `vars_get`
0x1ed778 (0x1c7b40/0x1c7bc0). The fresh hub script initializes this
variable to zero only on its fresh-state branch. The code at
0x1c7cd4–0x1c7d74 calls `item_parseDescriptor` in the fixed-item seed path;
its exact call count and descriptor arguments are **Unknown** until a bounded
stock-mode trace executes modes 1/2/3. The stock path then fills
the lists with `item_generateWithAffixes` 0x104ca4 and
`item_generateFromSpecialTable` 0x104758, using difficulty and store level for
the budget/level cap. It sorts each list by value. The stock loops call
`item_sameIdentityFields` 0x108924 at 0x1c7e28/0x1c8070/0x1c8428; this
compares definition, flags and a word containing the otherwise unwritten
+0x22 item byte, which can change duplicate retries. The separate
`item_appendGeneratedUnique` 0x107d54 has a bounded model in
`docs/spec/items.md` §7.3. Three optional
special-generation decisions read `g_cosmeticSeed` at 0x1c7ea0/0x1c80c4/
0x1c8498 and can draw from `g_randSeed`. The existing code-path analysis in
`docs/issues/sync-breakers.md` §2 shows the seeds equal at this level-load
boundary. The complete stock budget arithmetic and real output lists were
not reproduced by this fixture; their exact values remain **Unknown** for a
native implementation. `ShopDaemon_run` 0x1d1490 is unconstructed and is not
a normal restock route (`docs/ui.md`).

**Executed** mode 0 at both seeds: 0x1c876c sets offline pause 0x41b4f4;
0x1c87d4/0x1c87d8 set menu flags 0x41b4f8 and `g_shopOpen` 0x41b50c;
0x1c89b4 registers `shop_task` 0x1c6068 as a draw task at priority 50.
`inventory_pollResources` 0x1bfbc8 supplies the shared inventory resource.
This probe stubs audio, texture handles, task registration and local-slot
checks, so it establishes writes and call arguments, not successful I/O.

## Screen, list and cursor

**Executed** `shop_task` → `shop_run` 0x1c74c0 →
`shop_buySellMenu` 0x1c6bb8 on a zero-state fixture: the named lookups are
`buttontop.tex` at 0x1c6c4c, `buysell.tex` at 0x1c6f50, and `front.tex`
at 0x1c6398. Sprite submissions are respectively (66,210,layer 0),
(60,174,layer 0), and (320,0,layer 1). The choice code begins a text batch
at 0x1c6ce0 and makes two localized text draws at 0x1c6d20/0x1c6e8c
(`tools/difftest_vendors.py:screen` checks both call sites and positions);
the fixture does not resolve font glyphs or localized strings. The resource
path also requests `coins.vag` and `shoptick.vag` at 0x1c883c/0x1c8854
(`tools/difftest_vendors.py:open_close` checks both call sites and names).

**Observed** `shop_run` uses the second panel table at 0x86a4b0 for the
choice and enters the common `itemList_update` 0x1d14c8/
`itemList_input` 0x1cd988 for stock or player bags. The stock flag of
`itemGrid_build` 0x1cbbe8 selects the 0x866e78 stock source rather than
player bags (0x1cbc88–0x1cbc9c). The copied 9-column × 75-row grid, three
pages, scroll, picture lookup, selected-item text, small font and detail
frame are specified and executed for inventory mode by
`docs/spec/inventory-screen.md` on `4a8a78a`. That geometry is the common
renderer; stock-mode grid packing, full Buy/Sell cursor transitions and
final pixels were **not** executed in this probe. The native client should
not treat the inventory-mode fixture as a shop screenshot.

**Observed** `itemList_input` sends Buy from 0x1ce1b4 through
`shopmsg_sendBuy` 0x1c5f78. That sender finds the *last* matching stock
record and puts its address in shop message 0. Sell is sent at 0x1ce528
as shop message 1 with grid column/row, bag, item index, panel and mode 1.
The format and last-match behavior were already **Executed** in
`tools/difftest_messages.py`; the current probe does not duplicate its
randomized message suite. Both actions originate in a draw task from local
raw-pad input, and the receiver applies them in the synchronized message
handler. `shop_buySellMenu` also uses `menu_cursorInput` 0x1c6570. Exact
button preconditions for every cursor state remain **Unknown** without a
focused input-state comparison.

## Buying and selling

The receiver is `shop_onMsg` 0x1c5d28 (channel 7). The source record is
local to each machine at the transmitted address; that address is not an
item identifier. **Executed** `shop_buy` 0x1d1240 on six cases per seed with
`item_getValue` 0x1024a8 returning a controlled value:

| Operation | Contract |
|---|---|
| Buy price | `trunc_ps2_f32(value × factor)`; factor 0x3f199999 (nominal 0.6), category 1 uses 0x3ee66666 (0.45), and item flags `& 0x30000000000` or definition slot 8 override with 1.0. For value 100, the first two give 59 and 44 under the interpreter's default FPU. The EE FPU is a model, not a console measurement. |
| Debit and insert | If signed gold at player +0xe4 covers price, subtract it and call `inventory_giveItem(slot,record,1)` 0x1c1868. The call result is ignored. The failing-insert fixture still lost gold. Insufficient gold sent no insertion call. The original stock record was not consumed. |
| Sell credit | `shop_onMsg` computes `max(1,trunc_ps2_f32((itemValue / count) × 0x3d4ccccc))`, with a ×20 adjustment for the special 20-at-a-time kinds. Definition slot 8 or flag bit 46 pays zero. The fixture's one-count/value-100 ordinary item credited 4, not 5. Gold is capped at 99,999,999. |
| Remove | The handler then calls `inventory_dropItem` 0x1c4310 with mode 1; the sale pays before that call. The bounded fixture stubs its internals. `docs/spec/game-messages.md` §5 covers actual bag removal, shifting/copy updates and the lack of a sell-side empty-cell check. |

Inventory insertion may merge stacks, append to one of three 64-record bags,
or refuse a full bag/single-copy item; exact behavior is in
`docs/spec/game-messages.md` §5 and the item model. The sale path may credit
gold before a removal refusal. The message handler does not validate every
wire index. Do not silently replace these original behaviors in a parity
port; any safety change needs a separately stated rule.

## Exit and ordered native port

**Executed** `shop_close` 0x1d0ab8 after the opened fixture. It clears
`g_shopOpen` and menu flag 0x41b4f8, sets input lockout 0x41b4fc to 60,
removes task 0x1c6068 at 0x1d0b58 and clears offline pause at 0x1d0b7c.
It calls `inventory_unloadResources` 0x1c54d0 at 0x1d0b4c; the probe checks
the call but stubs its internals. **Observed** in net mode it
sends a null-channel shop-closed message, whose receiver is empty
(`docs/ui.md`). The exact local close button path and death-close timing are
outside this bounded probe.

1. Keep the authored hub NPC/dialog/script route, including deferred
   `activateStore`, the disc-checked vendor properties, actual local-slot
   gates and quest `storeLevel`. Verify
   NPC use through shop opening in an integrated hub run.
2. Port mode 1/2/3 stock generation from the original item functions and
   value/sort rules. Trace the fixed-descriptor call count and arguments;
   resolve budget arithmetic, seeded duplicate retries and stock-mode packing
   with a focused comparison before accepting stock parity.
3. Load the selected disc's shop textures, inventory item pictures and fonts;
   request the two checked audio resources, and render the Buy/Sell choice and
   shared item grid by their submitted layers, text-draw positions, cursor and
   copy addresses. Compare original/native captures with known
   stock, language and frame before claiming visual parity.
4. Wire raw local input to the observed Buy/Sell messages. Preserve channel
   routing, stock addresses, gold arithmetic, bag insertion/removal and the
   ignored insertion result. Validate stacks, full bags and zero-credit kinds.
5. Implement `shop_close`, task removal, inventory resource unload,
   menu-state message and input lockout; test both explicit exit and
   shopper-death exit in an integrated session.

## Verification boundary

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_vendors.py` passed one
disc-backed archive check and 24 bounded EE checks across the two seeds with
zero mismatches on the 2026-10-23 audit-fix rerun. The controlled item value,
resource handles and service stubs are named in the probe. The full unit suite
passed 652 tests in the same serial background run with bytecode writes off.
Serial background rerun with `PYTHONDONTWRITEBYTECODE=1` and the pinned
executable: `difftest_inventory_screen.py` on `4a8a78a` passed 38/38;
`difftest_items.py --quick --jobs 1 -k shop` passed 1/1 property with five
stock lists and ten appends, and `-k value-random` passed 1/1 with 4,000
records; `difftest_messages.py --quick` passed 44/44 properties (including
all 14 shop-handler and all eight shop-buy basic blocks);
`difftest_story_route.py` on `703362e` passed both seeds and 26 menu
snapshots each; `difftest_mission_menu_art.py` passed 39 draw and 20 input
cases per seed plus the 32-entry disc header check; and
`python3 -m unittest discover -s tools -p 'test_*.py'` passed 652 tests.
All eight commands returned zero; their serial output is ignored under
`local/vendor-checks.log`. Neither a function-level comparison nor existing
branch research establishes native vendor gameplay or raster parity.
