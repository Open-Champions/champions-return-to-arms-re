#!/usr/bin/env python3
"""Compare two machines of one net game (see README.md, "Two machines").

    compare.py ticks A.tick.tsv B.tick.tsv
        Lines the two tick logs up by lockstep tick (column "net") and reports the
        first tick at which a shared column differs, and which columns ever differ.
        Columns whose name starts with "l_" are per machine by design and only counted.

    compare.py mem A.ram B.ram [--baseline A0.ram B0.ram] [--all] [--top N] [--min BYTES]
        Diffs two dumps of EE memory taken at the same tick (script command
        "ontick N dump 0 0x2000000 file"), groups what differs by named symbol or, in
        the heap, by run of nearby bytes, and leaves out the regions listed in IGNORE
        below, which hold state that is per machine by design. --all shows those too.
        --baseline names a pair of dumps from an earlier tick at which the tick logs
        still agreed: every byte that already differed there is per machine by
        observation and is left out as well (repeatable). Two machines in sync differ
        in several hundred kilobytes (pose buffers, render lists, the peer table, the
        order of some heap blocks), so a diff without a baseline is mostly that.

Exit code 0: nothing shared differs; 1: something does; 2: bad input.
Standard library only. Dumps and logs are game data: keep them under local/.
"""
import glob
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- what may differ between two machines that are in sync ---------------------------
#
# (start, end, reason). Addresses are EE addresses; end is exclusive. Every entry was
# either read in the documents or seen to differ between two machines whose tick logs
# agreed; the reason says which. Audit this list before trusting a "nothing differs".
IGNORE = [
    (0x00000000, 0x00100000, "kernel area of the emulator's BIOS: thread contexts, timing"),
    (0x01f00000, 0x02000000, "top of memory: the main thread's stack"),
]

# Regions found through pointers in the dump itself: (name, pointer address, size, reason)
IGNORE_POINTED = [
    ("prediction copy", 0x004027BC, 0x590, "g_ghost: this machine's copy of its own player (flag 0x20000)"),
]


def load_symbols():
    table = []
    files = [os.path.join(ROOT, "names.tsv")] + sorted(glob.glob(os.path.join(ROOT, "symbols", "*.tsv")))
    for path in files:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 2:
                    continue
                try:
                    table.append((int(fields[0], 16), fields[1]))
                except ValueError:
                    pass
    table.sort()
    return table


def symbol_for(table, address):
    """Nearest symbol at or below the address, as 'name+0x12'."""
    import bisect
    index = bisect.bisect_right(table, (address, "￿")) - 1
    if index < 0:
        return ""
    base, name = table[index]
    if address - base > 0x20000:
        return ""
    return name if address == base else "%s+0x%x" % (name, address - base)


# --- tick logs ------------------------------------------------------------------------

def read_ticks(path):
    with open(path, errors="replace") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        rows = {}
        order = []
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(header):
                continue
            row = dict(zip(header, fields))
            key = int(row["net"])
            if key not in rows:          # a tick is logged once; keep the first if not
                rows[key] = row
                order.append(key)
    return header, rows, order


def compare_ticks(path_a, path_b, context=2):
    header_a, a, order_a = read_ticks(path_a)
    header_b, b, order_b = read_ticks(path_b)
    shared = [c for c in header_a if c in header_b and c not in ("frame", "net") and not c.startswith("l_")]
    local = [c for c in header_a if c in header_b and c.startswith("l_")]
    ticks = [t for t in order_a if t in b]
    first_by_column = {}
    count_by_column = {}
    local_differs = {c: 0 for c in local}
    pacing = 0
    for tick in ticks:
        ra, rb = a[tick], b[tick]
        if ra["frame"] != rb["frame"]:
            pacing += 1
        for column in shared:
            if ra[column] != rb[column]:
                first_by_column.setdefault(column, tick)
                count_by_column[column] = count_by_column.get(column, 0) + 1
        for column in local:
            if ra[column] != rb[column]:
                local_differs[column] += 1
    print("ticks: A has %d (%s..%s), B has %d (%s..%s), compared %d" % (
        len(order_a), order_a[0] if order_a else "-", order_a[-1] if order_a else "-",
        len(order_b), order_b[0] if order_b else "-", order_b[-1] if order_b else "-", len(ticks)))
    print("ticks run on different frames of the two machines: %d" % pacing)
    print("per-machine columns that differ (expected): " +
          (", ".join("%s on %d ticks" % (c, n) for c, n in local_differs.items() if n) or "none"))
    if not first_by_column:
        print("RESULT: no shared column differs on any tick")
        return 0
    first = min(first_by_column.values())
    print("RESULT: shared state differs; first tick %d (frame %s on A, %s on B)" % (
        first, a[first]["frame"], b[first]["frame"]))
    print("columns, in order of first difference:")
    for column, tick in sorted(first_by_column.items(), key=lambda item: item[1]):
        print("  %-12s first at tick %-7d on %d ticks" % (column, tick, count_by_column[column]))
    position = ticks.index(first)
    print("around the first difference (A | B):")
    for tick in ticks[max(0, position - context):position + context + 1]:
        differing = [c for c in shared if a[tick][c] != b[tick][c]]
        shown = differing or ["seed"]
        print("  tick %d: %s" % (tick, "; ".join("%s %s | %s" % (c, a[tick][c], b[tick][c]) for c in shown)))
    return 1


# --- memory -----------------------------------------------------------------------------

def differing_runs(a, b, gap=32):
    """Byte ranges that differ, merged when closer than 'gap' bytes."""
    runs = []
    page = 4096
    size = min(len(a), len(b))
    for start in range(0, size, page):
        if a[start:start + page] == b[start:start + page]:
            continue
        for offset in range(start, min(start + page, size)):
            if a[offset] != b[offset]:
                if runs and offset - runs[-1][1] < gap:
                    runs[-1][1] = offset + 1
                else:
                    runs.append([offset, offset + 1])
    return runs


def compare_memory(path_a, path_b, show_all=False, top=40, minimum=1, baselines=()):
    with open(path_a, "rb") as handle:
        a = handle.read()
    with open(path_b, "rb") as handle:
        b = handle.read()
    # bytes that already differed in a baseline pair are made equal before the diff
    if baselines:
        a = bytearray(a)
        masked = 0
        for base_a, base_b in baselines:
            with open(base_a, "rb") as handle:
                a0 = handle.read()
            with open(base_b, "rb") as handle:
                b0 = handle.read()
            for start, end in differing_runs(a0, b0, gap=8):
                a[start:end] = b[start:end]
                masked += end - start
        a = bytes(a)
        print("baseline: %d bytes that already differed there are left out" % masked)
    if len(a) != len(b):
        print("dumps differ in size: %d and %d bytes" % (len(a), len(b)))
    table = load_symbols()
    ignore = list(IGNORE)
    for name, pointer, size, reason in IGNORE_POINTED:
        for label, dump in (("A", a), ("B", b)):
            if pointer + 4 <= len(dump):
                target = struct.unpack_from("<I", dump, pointer)[0] & 0x1FFFFFFF
                if target:
                    ignore.append((target, target + size, "%s of machine %s: %s" % (name, label, reason)))
    # player objects, for labelling only
    labels = []
    for slot in range(4):
        pointer = 0x4D8AF0 + slot * 0x4C30 + 0x43D8
        if pointer + 4 <= len(a):
            target = struct.unpack_from("<I", a, pointer)[0] & 0x1FFFFFFF
            if target:
                labels.append((target, target + 0x590, "object of player %d" % slot))

    runs = differing_runs(a, b)
    kept, ignored = [], {}
    for start, end in runs:
        reason = None
        for low, high, why in ignore:
            if start >= low and end <= high:
                reason = why
                break
        if reason and not show_all:
            ignored[reason] = ignored.get(reason, 0) + (end - start)
        else:
            kept.append((start, end, reason))
    total = sum(end - start for start, end, _ in kept)
    print("differing runs: %d in all, %d outside the ignore list (%d bytes)" % (len(runs), len(kept), total))
    for reason, size in sorted(ignored.items(), key=lambda item: -item[1]):
        print("  ignored %7d bytes: %s" % (size, reason))

    # group by symbol (data and bss) or by 4 KB of heap
    groups = {}
    for start, end, reason in kept:
        if end - start < minimum:
            continue
        name = symbol_for(table, start)
        label = None
        for low, high, text in labels:
            if low <= start < high:
                label = "%s +0x%x" % (text, start - low)
        if label:
            key = label.split(" +")[0]
        elif name and start < 0x0090A434:
            key = name.split("+")[0]
        else:
            key = "heap %08x" % (start & ~0xFFF)
        groups.setdefault(key, []).append((start, end, name, label, reason))
    print("groups (%d), largest first:" % len(groups))
    ranked = sorted(groups.items(), key=lambda item: -sum(e - s for s, e, _, _, _ in item[1]))
    for key, entries in ranked[:top]:
        size = sum(e - s for s, e, _, _, _ in entries)
        print("  %-34s %6d bytes in %d runs" % (key, size, len(entries)))
        for start, end, name, label, reason in entries[:4]:
            length = min(end - start, 16)
            print("      %08x..%08x %-30s A=%s B=%s%s" % (
                start, end, (label or name)[:30], a[start:start + length].hex(), b[start:start + length].hex(),
                "  [ignored: %s]" % reason if reason else ""))
    if len(ranked) > top:
        print("  ... %d more groups (use --top)" % (len(ranked) - top))
    return 1 if kept else 0


def main(argv):
    if len(argv) >= 3 and argv[0] == "ticks":
        return compare_ticks(argv[1], argv[2])
    if len(argv) >= 3 and argv[0] == "mem":
        options = argv[3:]
        top = int(options[options.index("--top") + 1]) if "--top" in options else 40
        minimum = int(options[options.index("--min") + 1]) if "--min" in options else 1
        baselines = [(options[i + 1], options[i + 2]) for i, o in enumerate(options) if o == "--baseline"]
        return compare_memory(argv[1], argv[2], "--all" in options, top, minimum, baselines)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
