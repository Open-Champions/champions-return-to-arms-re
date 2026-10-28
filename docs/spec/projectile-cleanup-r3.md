# Projectile cleanup: round 3

2026-10-27. Bounded original-function research for the cleanup refusal retained
by the `play-spells-r2` audit. IDs and addresses identify the evidence; this
document contains no extracted names or resources.

**Executed** means original instructions ran in `tools/ee_emu.py` against an
independent Python reference on synthetic state. **Observed** identifies a
directly checked original table field. **Inferred** identifies a composition or
generalization. **Unknown** remains outside that evidence. None means a live
game or playable-client test.

## Established contract

| Evidence | Contract |
|---|---|
| Observed, checked on every rig creation | Slot 1 of table `0x5183d8` points to `0x3ccfd4`; slot 1 of table `0x5120b8` points to `0x3c2940`. Both this-adjustments are zero. |
| Executed: `0x3ccfd4` | Clears the object's handle heads at `+0x58`, `+0x54`, `+0x4c`, in that order, then enters base destructor `0x14cf90` with flags zero. It does not call `0x3c2940` on this path. |
| Executed: `0x3c2940` | Clears `+0x4c`, then enters `0x14cf90` with flags zero. |
| Executed: `0x14cf90` through both derived entries | Restores the base table, removes populated synthetic name entries, and clears heads `+8`, `+4`, `+0` in that order. Grid/off-grid, run, draw, external-reference and deferred-delete links are compared through real list operations. |
| Executed: `0x150470` | Exactly one pool release follows base cleanup when tested outer flags have bit 0 set; none when clear. Tested flags are `0`, `1`, `2`, `3`, `0x80000000`, `0x80000001`, `0xffffffff`. The bit-0 rule for other flags is Inferred from the reference and these controls. |
| Executed: `0x2ca1a8` -> `0x3ccfd4` | With homing unarmed, deadline equality ends ID 4 immediately through slot 1 with flags 3. The surviving case is one frame before the deadline. Ground-result bit 0 ends it; object-result bit 1 ends it only with nonzero `+0x78`. The pre-destruction RNG word `+0x44` and deadline `+0x70` match the existing flight reference, including terminal cases. |
| Executed: `0x14f200` / `0x14f3a8` | A separately requested deferred deletion uses the original derived slot on flush. An excluded queued object survives a flush and is destroyed after the exclusion mask is cleared. This queue route is separate from ID 4's immediate terminal destruction. |

The real handle clear (`0x1a1698`), handle link (`0x1a1738`), pool allocation and
release, base construction (`0x14cb10`), and object registries run underneath
these cases. The comparison checks complete nonempty grid and run chains, all
name slots, live base-object fields, allocator heads, external handle chains,
and periodic/final complete node and pool free lists. Nonfreeing destructor
cases also compare the surviving base vtable. Derived data beyond the explicitly
compared fields is not claimed as a complete object-memory comparison.

## Probe and controls

`tools/difftest_spell_cleanup.py` retains the earlier uncommitted probe's sound
core and expands it. The earlier 39 cases passed before editing. The revised
74 cases include the original flag/link matrix, queue and terminal boundaries,
32 combinations of four schedules, grid/off-grid and draw linkage with populated
synthetic names, filtered deferred deletion, distinct handle targets, and owner
destruction before projectile destruction. Seeds 20973 and 7 each pass **74
cases / 210 compared operations / 0 mismatches**. Each run rejects three wrong
reference contracts: omitted derived handles, inverted release flag, and swapped
clear order. These controls do not modify executable instructions.

Run from the worktree with the owner's executable under ignored `local/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,sys,runpy; sys.path.insert(0,"tools"); sys.argv=["tools/difftest_spell_cleanup.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0],run_name="__main__")'
```

Repeat with seed `7`. Output is counts only. The digest guard rejects other
executables. Preloading `unittest` avoids the repository's `tools/dis.py`
shadowing the Python standard library.

## Boundaries retained

**Partial:** The fixture uses the real base constructor and then installs the
derived table and synthetic fields/links. It does not run the complete cast and
derived constructor before each cleanup. Existing flight reference APIs and
historical vectors are unchanged. The original base-table callback wrapper in
the object rig remains; the two derived slots under test retain their original
entries and execute directly.

**Partial:** Movement (`0x1509f8`) returns scripted collision bits. Particles,
sound and effect-spawn endpoints are silent stubs, and resource lookup uses the
object rig's synthetic resolver. These do not establish actual terrain,
presentation resources, damage or victim HP. Other inherited object-rig hooks
are disclosed in `tools/difftest_objects.py`; no live scheduler is booted.

**Unknown:** Wrapped/signed frame-boundary gameplay, continuous original
selection-to-hit-to-cleanup execution, destructor correctness for other derived
tables, real-world contact results, campaign reachability, and native integration.
The client may use this addressed cleanup contract after a separate port and
validation; this research did not modify or run the playable client.
