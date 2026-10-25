# Creature water services

2026-10-17, SLUS-20973 v2.00. **Observed** from original instructions:
water-chunk query `0x189240–0x189434`, `water_test`
`0x189438–0x189510`, `water_disturb` `0x189514–0x189840`.
Executable contract: `tools/ref_water_services.py`, with authored synthetic
fixtures in `tools/test_ref_water_services.py`.

**Executed:** `tools/difftest_water_services.py local/SLUS_209.73` runs these
three original functions in `ee_emu` with synthetic memory and no service
stubs. All 576 calls match reference results and ordered non-stack stores:
144 each under ps2, ps2g1, chop and nearest arithmetic. This is function-level
interpreter evidence, not a live game, actual water rendering or console test.
The executable hash is checked; missing/wrong inputs fail rather than skip.

## State and finite domain

Caller supplies world memory, relocated spatial tree and chunks, payloads and
allocated ripple grids. These functions allocate nothing. All pointers/words
are little-endian; floats are raw32 through `ref_core`; indices use the
signed/unsigned widths below. Model methods take an already-copied position
tuple (the original copies it to stack before doing work).

| Field | Reader/meaning |
|---|---|
| world+04 | root spatial-tree pointer, `0x189288` |
| world+24 | contiguous chunk table, stride 0x3c, `0x189368–378` |
| chunk+00 | payload pointer, `0x1895f4` |
| chunk+08,+0c,+10 | float minimum x,y,z |
| chunk+14,+18,+1c | float maximum x,y,z |
| chunk+24 | flags; bit 0x80 is water |
| chunk+28,+2c,+30 | signed32 origin coordinates divided by four |
| payload+08 | runtime ripple-grid pointer, zero permitted |
| grid+0xa90 | 32×32 signed16 accumulated disturbances, stride 64 bytes |
| 0x44fcec | cut-skip byte; any nonzero value disables disturb |

**Host refusals:** malformed/cyclic trees beyond a 65,536-node work budget,
split axes outside 0..2, more than 16 pending nodes, query capacity below 2,
nonpositive disturbance radius and nonpositive rounded chunk width. These
guards are not original checks. Preserve already completed writes on refusal.
Admit valid mapped non-overlapping memory and ordinary finite simulation
values; invalid pointers, stack overflow and aliasing into private stack
storage are outside the reference domain. Original abnormal-input behavior
is not replaced with a successful empty result.

## Query traversal, ordering and capacity

**Observed, `0x189240`:** output is a caller-sized pointer array including a
null terminator. Clear output[0] first. Push world.root on a local LIFO stack
(16 pointer cells starting stack+0x20). Pop one node at a time.

At node address N, read its u16 tag:

- Bit 0x8000 clear: tag is a leaf count; read that many u16 chunk indices
  starting N+2, in order. Each resolves at `world.chunks + index*0x3c`.
- Bit 0x8000 set and 0x4000 clear: skip the node.
- Both set: axis=`tag & 0xfff`. Two split thresholds are made from pairs
  of **signed16** loads at N+2,N+4 and N+6,N+8. For each, compute
  `s32((s16(low) | (s16(high)<<16)) << 2)`, then convert to float.
  Do not silently replace this with an unsigned-low 32-bit read.
  If `query.min[axis] <= first`, push left=N+20. If
  `second <= query.max[axis]`, push right=`N+18 + 2*s16(N+18)`.
  Thus when both pass the **right child is visited first**. Words between
  thresholds and the relative right-child offset are not read here.

**Observed, `0x18937c–0x189400`:** only chunks with flag 0x80 qualify.
Reject in X, Y, Z order if `query.max < chunk.min` or `chunk.max < query.min`.
Touching bounds qualify; there is no point-in-polygon, radius-distance,
payload mask, triangle or height-plane test beyond this inclusive AABB.
Do not sort or deduplicate. Duplicate leaf indices remain duplicate results.

On a hit (`0x189404–414`), decrement remaining capacity, store the chunk
pointer, advance output; if remaining==1 stop. Write a final null even when
there were no hits. Therefore capacity 2 yields **at most one** hit and
capacity 16 yields **at most fifteen**, not sixteen. The reference's query
returns a Python list for host use; the original return register is not a
specified count. Optional `out` exposes its ordered memory writes.

## water_test

**Observed, `0x18948c–0x1894e0`:** with radius r and position p, form:

```
lo = ((px-r)-1, (py-r)-1, pz-1)
hi = ((px+r)+1, (py+r)+1, pz+60)
```

Keep the parentheses/raw32 rounding. Call query with capacity 2. If the
first result exists and heightOut is nonzero, write **chunk.min.z**
(`chunk+0x10`, `0x1894f4–f8`) to heightOut. A miss leaves heightOut unchanged.
Return exactly 0 or 1 for absence/presence. Overlapping chunks use the first
traversal hit, not highest/closest water. Cut-skip does not gate this function.

## water_disturb: query and grid mapping

**Observed, `0x18953c–55c`:** after copying position, read cut-skip. Nonzero
returns zero with no query or grid write. Otherwise use
`lo=(px-r,py-r,pz-1)`, `hi=(px+r,py+r,pz+60)` and query capacity 16
(`0x189560–5d4`). Unlike test, XY has **no additional one-unit padding**.

Visit every result in order. Increment the result count even if its grid
pointer is zero. Duplicate chunks disturb their grid repeatedly. Shared grid
pointers are not deduplicated. The query list is completed before grid writes.

**Observed, `0x189604–6d4`:** grid scale comes from **X width only**, even
on a non-square chunk. In raw32 arithmetic:

```
width = maxX-minX
n     = trunc(width * raw(0x3daaaaaa) + 0.5)   # approx 1/12
inv   = 1 / (float(n)*12)
ox    = float(s32(chunk+28))*0.25
oy    = float(s32(chunk+2c))*0.25
gx    = (((px-ox)*32)*inv)+16
gy    = (((py-oy)*32)*inv)+16
gr    = (r*32)*inv
r2    = gr*gr
k     = strength/r2
```

Z origin is read and a local difference formed, but it is not used in any
grid selection or write after the AABB query. For ordinary finite input this
temporary has no externally visible effect. There is no snap to a customary
tile size or assumption that `width==384`.

## Disturbance writes

**Observed, `0x1896e4–0x189808`:** candidate bounds unusually use the
**original world radius r**, not gr:

```
x0=max(0,trunc((gx-r)-1)); x1=min(31,trunc((gx+r)+1))
y0=max(0,trunc((gy-r)-1)); y1=min(31,trunc((gy+r)+1))
```

If a lower bound exceeds its upper bound that loop is empty. Iterate X
outer, Y inner, both inclusive. Calculate `dy=float(y)-gy`,
`dx=float(x)-gx`, `d2=dy*dy+dx*dx` in that order. Skip only if `r2<d2`.
The comparison is inclusive but raw32 reciprocal error may put a
mathematically-on-circle cell just outside (the synthetic 384-wide,
radius-12 case demonstrates this).

For a visited cell at `grid+0xa90+2*(32*x+y)`:

1. `amount = trunc(strength - d2*k)`.
2. Load old value as **signed16**; add with signed32 wrap.
3. Clamp only values above 32767 to 32767.
4. Store the low 16 bits (`0x1897d8–e8`). Negative overflow wraps; there is
   no lower clamp. Store even a zero increment if the cell passed the test.

There are no accesses to the payload's neighbor indices or 128-byte mask,
no propagation into a neighboring grid and no simulation-step integration
in these functions. Return the number of queried chunks, including ones
without grids and ones for which no cell was changed (`0x18980c–824`).

## Native handoff and remaining boundaries

**Fully documented for the admitted domain:** both services and their exact
water-only query are executable and independently checked against original
instructions. The native owner can replace the service callbacks in the
already-contracted creature water bookkeeping; that caller's staggered
queries, splash sound and RNG remain in `ref_creature.Model._water` and
[creature-tick](creature-tick.md) section 8.

**Unknown/outside this task:** grid allocation/free lifetime, water's later
simulation tick and neighbor exchange, drawn surface height/materials, and
Session ownership of relocated world data. This contract requires supplied
runtime grids; it does not invent missing grid pointers from static WORLD
data. No live gameplay or native Session integration is credited.
