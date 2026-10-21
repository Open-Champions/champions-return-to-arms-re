# GameObject constructor: Skills-A completion contract

Research date: 2026-10-17. Executable: SLUS-20973 US v2.00, SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
This supplements the deliberately restricted `ref_skills_a.Model.gameobject_ctor`;
it does not change that pinned model or its existing native vectors.

**Observed:** the following ordering was checked in `0x14cb10–0x14cf88`,
`obj_getPropInt` `0x14c880–0x14c9bc`, and `objNames_add`
`0x14bce0–0x14be54`. Reference: `tools/ref_gameobject_ctor.py`.
Names describe behavior, not recovered source. No live-game claim is made.

## Admitted memory and service boundary

The reference uses the sparse byte memory and ordered write log of `ref_creature`.
Positions are three raw32 words, copied before any object write. All pointers are
32-bit little-endian. `res_find(lump, entry)` and
`handle_link(cell, obj+8, obj)` remain explicit external services, already
contracted in `ref_core`/the Skills handle modules. Their mutations must finish
before the next constructor instruction. Missing callbacks are not success.

The finite domain is valid, non-overlapping object/list/string/table storage,
ASCII NUL-terminated strings, canonical writable `hide`/`name` key storage,
nonnegative property ordinals, and a valid paired node from `handle_link`.
There is no simultaneous writer. The reference caps strings at 511 bytes,
property/resource traversals at a host budget and name probes at 512. These are
**host refusals**, not original checks. Quotes use a 512-byte original stack
scratch; overflow, arbitrary pointer aliasing, invalid lists, non-ASCII ctype
behavior and C integer-overflow portability are outside the claim. Original
nontermination on a full name table is represented by a refusal after its
already-completed quote edits and counter increment.

## Ordered constructor prefix

**Observed, `0x14cb58–0x14cbc0`:** first copy the input position to temporary
storage. Publish the following stores in order (hex offsets from `obj`):

1. u32 `+00=0`, `+04=0`, `+48=0x5122a8`, `+08=0`.
2. raw32 `+1c=24.0`, `+20=72.0`; u32 `+0c=0`.
3. u8 `+28=0x19`, `+29=0x49`.
4. Copied position at `+10,+14,+18`; u32 `+34=0`, `+24=classDef`.

The original uses an unaligned doubleword store pair for XY; the Python write
log normalizes XY to one eight-byte store and Z to one four-byte store, as
existing Skills-A vectors do.
It does not claim the original bus transaction widths. `+2c` is NOT cleared.

**Observed, `0x14cbc4–0x14cc20`:** a non-null definition with generation at
`def+4` different from `0x41bf78` resolves entries from `def+8`, stride 8,
until a null name. Each record is `{name pointer, resolved pointer}`; `def+0`
is the lump-name pointer. Call `res_find(def[0], entry.name)`, then **re-read
obj+24** (`0x14cbfc`) before storing the result at that definition's record+4.
The next record is read from the reloaded definition. Finally copy the then
current global generation into definition+4. Equal generations do no work.

**Observed, `0x14cc24–0x14cce0`:** convert X and Y with the selected EE float
model, add `0x3c00` with 32-bit wrap, interpret as signed, arithmetic shift
right 8. If flag 2 or either index is outside `[0,119]`, use cell
`0x5f76f0`; otherwise `base + 4*(120*row+column)`, base `0x5db4f0`
or `0x5e95f0` when flag `0x800`. Normally flags are zero from the prefix;
a resource callback can change them. Link once with
`handle_link(cell, obj+8, obj)`.

## Hidden-grid relocation

**Observed, `0x14cce4–0x14cd48`:** call `obj_getPropInt(obj, "hide", 0)`
**before** assigning incoming properties. It sees the stale pointer at `obj+2c`.
A newly zeroed pool object therefore ignores `hide` in its incoming list at
this stage. A reused/supplied object can take this path. The integer is true
for any nonzero value, including negative numbers. This is not a flag update.

A handle node is 16 bytes: next `+0`, address of predecessor's link `+4`,
paired node `+8`, target `+c`. Let `N = u32(u32(obj+8)+8)`.
The constructor moves **that existing peer**, not the object-side node:

1. `*N.prevLink = N.next` (`0x14cd10`).
2. Re-read `N.next`; if nonzero, `next.prevLink = N.prevLink` (`0x14cd24`).
3. Read old head of `0x5f76f0` after unlinking.
4. Write `N.prevLink = 0x5f76f0`, `N.next = oldHead`, `offGridHead = N`
   (`0x14cd34,38,3c`).
5. Re-read `N.next`; if nonzero write `next.prevLink = N` (`0x14cd48`).

Preserve both identities, both `+8` peer links, targets, object head and free
pool. No free, allocation, second link call or `obj.flags |= 2` occurs. Moving
from the off-grid list to itself is valid: unlink first, then insert at head.

## Property and seed publication

**Observed, `0x14c8b0–0x14c990`:** null `obj+2c` returns zero without touching
the key. Otherwise lowercase each non-NUL key byte **in place**, then re-read
`obj+2c`. The list is a null-terminated array of string pointers. Match the
lowercased key case-sensitively and require the next character to be `=`.
`Hide=1` does not match `hide`. The third argument is a zero-based occurrence
index, not a default value. `atoi` of the selected value returns the integer;
missing values return zero. Leading whitespace/sign and a numeric prefix are
accepted (`0x14c968` calls `0x3b3550`).

**Observed, `0x14cd5c–0x14cd80`:** read shared seed `0x404464`, then store
incoming properties at `obj+2c`, then publish
`seed = (old*0x19660d + 0x3c6ef35f) mod 2^32` to the global, then
`seed >> 16` to `obj+44`. Exactly one shared draw, even without properties.
Keep this ordering if the host records mutations or callback prefixes.

## Constructor names and hash-table ownership

**Observed, `0x14cd84–0x14cf58`:** starting at ordinal zero, search the new
properties for `name=`. The inlined search lowercases the key at `0x5321b0`
and compares exactly four characters. If absent, return. If present, perform
the same ordinal search **again**, add the returned value pointer to the name
table, increment ordinal and repeat. There are two key rewrites per found
name and one final search (unless the property pointer is null). Do not
deduplicate equal names or replace the second search with the first pointer
in an ordered-write implementation.

**Observed, `0x14bd0c–0x14bd4c`:** if the value starts with a double quote,
copy text after it into scratch, truncate at the next quote if present, then
copy back to the **same value address**, including NUL. Old bytes after that
NUL remain. Without a leading quote, leave the value unchanged. Store the
property's value pointer, not a newly allocated copy.

**Observed, `0x14bd50–0x14be34`:** increment u32 count `0x5f86f8` BEFORE
hashing/probing. Fold ASCII uppercase to lowercase for hashing only. Using
signed 32-bit wrap after each operation, start `h=0`; for each byte c:
`h+=c; h+=h<<10; h^=h>>6`; finally `h+=h<<3; h^=h>>11`.
Both right shifts are arithmetic; slot is `h & 511`.

Parallel 512-word arrays: key pointers `0x5f76f8`, object pointers `0x5f7ef8`.
Probe forward with `(slot+1)&511`. Accept a null key, or a non-null key with
null object whose string equals the incoming string case-insensitively.
An occupied equal-name slot is **not** replaced. A tombstone for a different
name is **not** reusable. Store key first (`0x14be30`), object second
(`0x14be34`). Return register is not a specified API result; the reference's
returned index is only an inspection convenience.

## Verification and handoff

`tools/test_ref_gameobject_ctor.py` uses only authored synthetic memory. It
checks ordered prefix/seed publication, stale versus incoming hide, nonempty
and same-list relocation, negative grid boundaries, key mutation/ordinals,
quoted names, duplicates, tombstones, full-table failure and resource generation.
The existing original-instruction harness is `tools/difftest_objects.py`
(`create` and `order.cases`); it compares its established `ref_objects` model,
not automatically this new byte-memory supplement.

**Executed in this pass:** `python3 tools/difftest_gameobject_ctor.py
local/SLUS_209.73` compares this new supplement against `GameObject_ctor`
and its real property/name callees on 64 authored synthetic inputs. All
final fixture/output bytes and ordered stores match. `handle_link` allocation
and `res_find` are deterministic matched stubs; vector-copy and libc
string-copy store widths are excluded from the order comparison but their
final bytes are included. No skipped input or live-game run is counted.

**Fully documented within the stated domain:** the last Skills-A constructor
gap can now be implemented against this supplement. This research does not
credit a 196th native function until the native owner ports and tests it.
