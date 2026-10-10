#!/usr/bin/env python3
"""Which gameplay functions can reach machine-local state?

For each virtual function of the named classes, follow direct calls (jal) to a fixed depth
and report every read of state that is not part of the lockstep simulation: the cosmetic
seed (g_cosmeticSeed), the camera, the local player slot, audio stream status, the disc
busy test (cd_isBusy), the hardware timer and render-loop counters. Virtual calls are not
followed, so this under-reports. It also over-reports: the address tracker never forgets a
register that is overwritten, and every "hardware timer" line it has printed so far is a
false positive (the constant 0x10000000 used as a flag bit or display-list tag; FINDINGS
D33). The tracker's other limits are listed in docs/issues/rescan.md section 9.
Function bodies come from ghidra_funcs.tsv when present.

  python3 localstate.py <elf> Class [Class ...]
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps2elf import Elf
import symtab
from vtab import find_vtables

LOCAL_DATA = {
    0x404460: "cosmetic seed", 0x44f048: "camera focus", 0x44f04c: "camera focus",
    0x44f038: "camera position", 0x506048: "render settle counter", 0x44fdd0: "render frame counter",
    0x10000000: "hardware timer",
}
LOCAL_CALLS = {
    0x13e1f0: "local player slot", 0x216480: "audio stream position", 0x211b20: "audio stream status",
    0x172be8: "disc busy (cd_isBusy)", 0x1ebd90: "near camera (480)",
}
CONDITIONAL = {0x1e77c0: "isNearView (camera only during net cutscenes)",
               0x14db08: "obj_updateActive (camera only during net cutscenes)"}
# functions that are presentation by construction: do not descend into them
STOP = {0x355490, 0x2134e8, 0x18f3f8, 0x1e7c40, 0x16d360, 0x16d558}


def main():
    e = Elf(sys.argv[1]); e.analyze()
    names = symtab.load(os.path.dirname(os.path.abspath(sys.argv[1])))
    site2tgt = {s: t for t, ss in e.refs.items() for s in ss}
    callees, touches = {}, {}
    # whole function bodies from Ghidra (entry -> [(first, last)]), so that the cases of a
    # state switch are scanned too
    bodies = {}
    gf = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "ghidra_funcs.tsv")
    if os.path.exists(gf):
        for line in open(gf):
            ent, _, body = line.rstrip("\n").split("\t")
            bodies[int(ent, 16)] = [tuple(int(x, 16) for x in r.split("-")) for r in body.split(",") if r]

    def scan(f):
        if f in callees:
            return
        cs, ts = [], []
        if f in bodies:
            pcs = [pc for lo, hi in bodies[f] for pc in range(lo, hi + 1, 4)]
        else:
            # not a known function entry: fall back to the heuristic boundaries, which stop
            # at the first jump-table target and so can miss the cases of a switch
            s, t = e.func_of(f)
            if s is None:
                callees[f], touches[f] = cs, ts; return
            pcs = range(s, min(t, s + 0x4000), 4)
        for pc in pcs:
            w = e.u32(pc)
            if w is None:
                continue
            if w >> 26 == 3:
                tgt = (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
                if tgt in LOCAL_CALLS: ts.append((pc, LOCAL_CALLS[tgt]))
                elif tgt in CONDITIONAL: ts.append((pc, "? " + CONDITIONAL[tgt]))
                elif tgt not in STOP: cs.append(tgt)
            d = site2tgt.get(pc)
            if d in LOCAL_DATA:
                ts.append((pc, LOCAL_DATA[d]))
        callees[f], touches[f] = cs, ts

    vts = find_vtables(e)
    for cls in sys.argv[2:]:
        for addr, (name, ents) in sorted(vts.items()):
            if name != cls:
                continue
            print(f"== {cls} (vtable 0x{addr:x})")
            seen_report = set()
            for slot, (delta, fn) in enumerate(ents, 1):
                if not fn:
                    continue
                # breadth-first to depth 4
                frontier, seen = [(fn, [fn])], {fn}
                for depth in range(5):
                    nxt = []
                    for f, path in frontier:
                        scan(f)
                        for pc, what in touches[f]:
                            key = (f, what)
                            if key in seen_report:
                                continue
                            seen_report.add(key)
                            chain = " > ".join(names.get(x, f"{x:x}") for x in path)
                            print(f"   slot[{slot:2}] {what:44} at {pc:x}   via {chain}")
                        for c in callees[f]:
                            if c not in seen:
                                seen.add(c); nxt.append((c, path + [c]))
                    frontier = nxt


if __name__ == "__main__":
    main()
