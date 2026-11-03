# Starting-equipment resource mapping, round 4

2026-10-27 draft; audited and re-executed 2026-11-02 at base `269e4da`.
The two interrupted files were retained after review and a complete passing run.

**STATUS: PARTIAL.** Original baseline character initialization now selects and
equips real items, and those items resolve to exact private resources. The
original scanner consumes all four equipped slots in the fixtures below. This
does **not** establish the hub -> first mission -> following-destination route:
there is no normal-arrival player/world/script fixture or transition execution
in this test. Destination-specific mutations remain unknown.

Evidence is US v2.00 function execution in
`tools/difftest_starting_equipment_r4.py`, using unchanged `tools/ee_emu.py` and
existing reference models. Private inputs are read through `local/`; resource
identities and payloads are neither printed nor retained here. No game, client,
renderer, physical disc device or public service was run.

## Starting selection and publication

**Observed, Executed:** the full initializer `0x1b1d70`, starting-item function `0x1acc78`
(caller `0x1b2400`), parser `0x1069b8`, inventory insertion `0x1c1868` and equip
`0x1c27c0`, including their reached callees, return without callee stubs or
instruction patches. This is stronger than the isolated publication store from
round 2. The common equip store remains `0x1c2ce4`.

The fixture sets player count one, player index zero, body indices 0–11, an
authored character name, four appearance arguments minus one, null optional
stats, kind minus one or one, and zero team. It tests both seeds 7 and 20973.
Other globals begin in executable/BSS state; no destination script is attached
and no player object is constructed. Kind selection and arbitrary saved/imported
characters are outside this baseline claim.

All 48 initializations publish four equipped pointers into the real record's
inventory, at record `+0x43f0 + 4*slot`. Their definition slot bytes agree with
their actual published slots. Every reached parser invocation is compared with
`ref_items.parse_descriptor`, including RNG state; untouched item bytes are
excluded according to the existing model's `pack(stale=...)` contract. There
are 364 parser comparisons, not 364 equipped items. This compares modeled fields
only, **not whole-record differential equality**. Preserved/padding bytes come
from the parser's internal stack record, so the destination buffer's previous
bytes would not be a valid oracle for them (see `docs/spec/items.md`, section 2).

**Observed, Executed mapping:** armor slots are always 4, 10 and 12 in these fixtures.
Their definition addresses are `(0x3fb110, 0x3fb150, 0x3fb210)`, except bodies
6/7 use `(0x3fa210, 0x3fa250, 0x3fa310)`.

| Body index | Class index | Weapon slot | Weapon definition address |
|---|---|---|---|
| 0, 1 | 0 | 0 | `0x3f7f50` |
| 2, 3 | 3 | 2 | `0x3f7650` |
| 4, 5 | 1 | 0 | `0x3f8910` |
| 6, 7 | 4 | 2 | `0x3f9250` |
| 8, 9 | 2 | 0 | `0x3f7a10` |
| 10 | 5 | 0 | `0x3f7f50` |
| 11 | 6 | 0 | `0x3f87d0` |

These addresses are observed output checks, not replacement item choices.
**Unknown:** the user's selected body/seed/save and any changes to inventory
between the three destinations. This round does not assert those inputs.

## Actual formatter and loaded metadata

**Observed, Executed:** `0x107edc` runs with its real formatting/string callees on all four
starting items. The 144 armor results in the selection matrix match an authored,
bounded model using private templates read at runtime. For these actual starting
armor definitions, variant bits at item `+8` are zero; the model combines the
definition picture pointer `+0x30`, template addresses `0x52f8f0/0x52f9b0`, body
code table `0x4026d8`, and suffix template `0x52f9b8`. The suffix color is byte
`+7` in prefix row `0x400e50 + item_byte[+0x20]*0x28`. Relevant original sites
are `0x107f1c`, `0x108248/0x108254`, `0x108280` and `0x1082dc`.
This model is deliberately limited to the generated baseline armor; it does
not claim all formatter variants, missing prefixes or special item categories.
Weapon formatter output executes but has no independent formatting model here.

**Observed, Executed:** header loader `0x1a2680` reads the primary header selected
by player count and override, plus the secondary header. Identifier addresses
are `0x535c08` for the single-player primary, `0x535bf8` for the alternative,
and `0x535c28` for the secondary. Current private group counts are respectively
243, 245 and 155. All four count/override combinations from round 2 now read
actual headers and compare their complete transformed bytes.

Each header begins with a group count and twelve-byte group records. The first
two words of each record are relocated by the allocation base; the third is a
record count. Original stores `0x1a275c/0x1a2760` and
`0x1a2804/0x1a2808` perform the two headers' relocations. Globals
`0x8659e0/0x8659e4` point to their group tables; `0x4ef36c/0x4ef370` hold counts.

**Observed, Executed:** actual `0x1a24e8` searches both headers for every formatted starting
item, giving 96 comparisons against an independent group/record search. The
bounded reference separates the final numeric suffix and searches eight-byte
records by their leading signed short. The actual starting identifiers have
this form; malformed names and other normalization branches are not covered.
Original comparisons/searches reach `0x1a2600`, `0x1a2614/0x1a2620` and
`0x1a2628`. All 36 armor requests match the primary and miss the secondary;
the 12 weapon identifiers match the secondary and miss the primary.

**Caution:** that secondary-header match does not make the baseline scanner use
a specialized weapon cache. Its actual weapon branch is the generic table path
described below.

The following are observed byte offsets of the matching armor metadata records
within the single-player primary header. They identify records without copying
resource names. Each cell is an address relative to that header's start.

| Body | Slot 4 | Slot 10 | Slot 12 |
|---|---|---|---|
| 0 | `0x4878` | `0x4a08` | `0x4ff8` |
| 1 | `0x28d8` | `0x2a68` | `0x3058` |
| 2 | `0x177f8` | `0x17938` | `0x17e38` |
| 3 | `0x159e8` | `0x15b28` | `0x16028` |
| 4 | `0xff68` | `0x100a8` | `0x105a8` |
| 5 | `0xe168` | `0xe2a8` | `0xe7a8` |
| 6 | `0xb448` | `0xb588` | `0xba88` |
| 7 | `0x9648` | `0x9788` | `0x9c88` |
| 8 | `0x86a8` | `0x87f8` | `0x8d28` |
| 9 | `0x6808` | `0x6958` | `0x6e88` |
| 10 | `0x13be8` | `0x13d28` | `0x14228` |
| 11 | `0x11de8` | `0x11f28` | `0x12428` |

## Specialized armor: exact range to actual pair

**Observed, Executed by direct orchestration:** for every body's three generated armor
items, the test calls the real formatter, header search and cache lookup
`0x1a2d48`. Slot/cache associations are 4 -> `0x8659e8`,
10 -> `0x865b48`, and 12 -> `0x865f68` for player index zero.

The real cache produces its sector request from the matched metadata:
begin = word `+4`, split = word `+12`, tail = signed short `+10`;
offset = begin * `0x800`, length = (split - begin + tail) * `0x800`.
The source role is identifier address `0x535d30` with cache flags `+0x54/+0x56`
zero. The host reads exactly that range from the uniquely resolved private file.
There is no arbitrary standalone-resource substitution.

Request frame 100, pending frame 103 and service frame 104 exercise the actual
request-relative delay. A separate incomplete control leaves the read pending.
After the host reports completion, original `0x179e10` and `0x179130` transform
the texture and model in order. All 36 pairs, totaling 5,650,432 bytes, match the
existing independent byte models, with a trailing guard unchanged. Original
identity/valid/outstanding publication executes; completion still returns zero
with zero outputs, and the next matching lookup returns the actual two pointers.
The next lookup does not transform them again.

**Boundary:** initial population above explicitly orchestrates cache calls; it is
not a claim that the scanner or a real disc device initiated/completed those reads.
Backing buffers are host allocations. The original cache allocation owner,
normal loading loop, device timing/recovery and physical media are not executed.

## Generic weapon and the original scanner

**Observed, Executed:** the generated weapon takes the generic path at scanner call sites
`0x1a34f4/0x1a3510`, through original resource-index function `0x1083f8`.
The row is definition signed short `+0x34`, plus the item variant when flag bit
36 is set; resource pointers occupy `+8/+12` of row
`0x3e9ce0 + index*16`. Original reads are at `0x1a350c/0x1a3520`.

The exact generic source is named by identifier address `0x520030` in resource
loader `0x108434` (lookup call `0x108470`). Reading that private lump into scratch
memory, the test executes original registration `0x171700`, directory/entry
fixup `0x1717d0/0x17153c`, and the **full** resource loader `0x108434` with
`0x17365c`/`0x171de4` resolving the real registered entries. No resource lookup
or transformation callee is stubbed. The full loader's RNG effect also matches
`ref_items.load_resources`.

For each of the 12 generated weapons, both names from the selected model-table
row uniquely match entries in that source. Original entry lookup, lengths,
published row pointers and whole selected model/texture bytes are checked against
the private directory and the two transformation models. These are 12 tested
pairs, not a claim of 12 distinct weapons. The generic loader runs after character
initialization in this fixture; normal bootstrap ordering is not established here.

**Observed, Executed by the original scanner:** `0x1a30b0` receives a bounded player object
containing index zero and reads all four pointers produced by the actual
initializer. The environment gate `0x4f85b0` is explicitly one. No scanner,
formatter, index, cache or string callee is stubbed during these scans.

- With the three exact armor pairs ready and the generic weapon pair absent,
  two scans per body return pending: 24 controls.
- With the exact generic pair registered and published too, two scans per body
  return ready: 24 cases. Each scan calls the actual formatter and matching cache
  lookup for slots 4, 10 and 12, in order, through `0x1a348c/0x1a34b0`.
- Clearing either generic resource pointer for body zero restores pending; each
  pointer is restored after its control. Two missing-pointer controls prevent an
  armor-only or single-pointer completion claim.

The complete player record remains unchanged by the readiness scans. These are
real scanner executions over real generated inventory and exact private resource
data, **not** an all-ready stub, an empty equipment table or an inferred scanner
result from independently successful direct cache calls.

## Adapters, remaining unknowns and verification

The header-loading adapters replace only file-size lookup `0x1724fc`, tagged
allocation `0x14ff88` and blocking read `0x172ad0`. They read the uniquely named
private files, preserve file bytes, and zero allocation padding. Specialized
submission `0x1729e8` is a checked read-only host transport; the completion flag
is explicitly driven by the fixture. Only this transport is stubbed within
cache-pair execution. Generic lump registration/loading and scanner execution
have no stubbed callees. No original instructions, emulator, existing APIs or
test vectors are changed.

**Unknown:** normal character-creation inputs, actual player constructor and
record publication in the loading owner, specialized cache allocation sizes and
ownership, destination scripts' effects on equipment, cache retention/reset
across the three destinations, renderer use, and a returned normal arrival.
Deferred-arrival evidence is in [the arrival report](loading-arrival-r4.md).
This result does not remove either
client refusal or claim a playable hub/mission/following-destination handoff.

Run the new test with:

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_starting_equipment_r4.py local/SLUS_209.73 local/disc
```

Expected evidence counts: 48 initializations; 364 parser comparisons; 144 armor
formatter comparisons; four real-header selections/relocations; 96 metadata
comparisons; 36 exact specialized pairs; 12 generic weapon pairs; 24 pending,
24 ready and two missing-pointer scanner cases. All output is counts only.
The ELF digest is checked before execution. Omitting the folder argument runs
only the initializer/parser/formatter matrix and must not be reported as private
resource or scanner verification.
