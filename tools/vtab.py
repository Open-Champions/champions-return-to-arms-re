#!/usr/bin/env python3
"""GCC 2.95 vtable helpers for SLUS_209.73 (entries are {s16 delta, s16 pad, u32 fn};
entry 0's fn is the class's type_info getter, which references the mangled class name;
the functions follow, slot 1 first, and a {0, 0} entry ends the table). A class compiled
without type information has __pure_virtual in entry 0 and is listed as vt<table address>.

  python3 vtab.py <elf> list                 # every vtable found, with class name
  python3 vtab.py <elf> show <hexaddr|Class> # entries of one vtable, marking functions
                                             # that appear in no other class's vtable
"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps2elf import Elf


# The descriptor initialisers a type_info getter calls (GCC __rtti_user, __rtti_si,
# __rtti_class, __rtti_ptr) and __pure_virtual.
TINFO_INIT = (0x3B12D8, 0x3B12B8, 0x3B1290, 0x3B25C8)
PURE_VIRTUAL = 0x3AD348


def tf_name(e, fn):
    """Class name of a type_info getter function, or None.

    A getter may first initialise the descriptors of its base classes (inlined), so it can
    hold several class names. Its own class is the one initialised last: the name passed in
    $a1 to the last initialiser call before it returns. The instructions are read here, up
    to the first jump out (jr or j), because the heuristic function table mis-sizes some
    getters."""
    if fn % 4:
        return None
    reg, name, pc = {}, None, fn
    while pc < fn + 0x200:
        w = e.u32(pc)
        if w is None or w >> 26 == 2 or w & 0xFC1FFFFF == 8:  # j / jr: the function ends
            break
        call = w >> 26 == 3  # jal: its delay slot runs before the callee
        x = (e.u32(pc + 4) or 0) if call else w
        rs, rt, imm = (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
        if x >> 26 == 0x0F:  # lui
            reg[rt] = imm << 16
        elif x >> 26 in (0x09, 0x19) and rs in reg:  # addiu / daddiu
            reg[rt] = (reg[rs] + imm - (imm & 0x8000) * 2) & 0xFFFFFFFF
        elif x >> 26 in (0x09, 0x19):
            reg.pop(rt, None)
        if call:
            if (pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2) in TINFO_INIT:
                name = e.cstr(reg.get(5, 0))
            reg = {r: v for r, v in reg.items() if 16 <= r <= 23}  # callee-saved only
            pc += 4
        pc += 4
    if name and re.match(r"^P?\d+[A-Za-z_]\w*$", name):
        return re.sub(r"^\d+", "", name)
    return None


def find_vtables(e):
    """Scan .data for {0, tf_fn} headers followed by {delta, fn} entries."""
    a, o, sz = e.sections[".data"]
    cache = {}
    out = {}

    def entries(j):
        """The functions of the table whose header is at offset j, up to its {0, 0} entry."""
        ents = []
        k = j + 8
        while k + 8 <= sz:
            delta, pad, fn = struct.unpack_from("<hhI", e.d, o + k)
            if not e.in_text(fn) or pad != 0:
                break
            ents.append((delta, fn))
            k += 8
        return ents

    for j in range(0, sz - 15, 4):
        d0, fn0 = struct.unpack_from("<II", e.d, o + j)
        if d0 != 0 or not e.in_text(fn0):
            continue
        if fn0 not in cache:
            cache[fn0] = tf_name(e, fn0)
        name = cache[fn0]
        if not name:
            continue
        ents = entries(j)
        if ents:
            out[a + j] = (name, ents)
    # vtables sit back to back. One that follows another's {0, 0} entry and starts with
    # {delta, __pure_virtual} belongs to a class compiled without type information: it has
    # no name of its own and is not part of the table before it.
    for cur in sorted(out):
        j = cur - a + 8 * (len(out[cur][1]) + 1)
        while j + 24 <= sz and a + j + 8 not in out and e.d[o + j:o + j + 8] == bytes(8):
            j += 8
            delta, pad, fn = struct.unpack_from("<hhI", e.d, o + j)
            ents = entries(j)
            if fn != PURE_VIRTUAL or pad != 0 or not ents:
                break
            out[a + j] = (f"vt{a + j:x}", ents)
            j += 8 * (len(ents) + 1)
    return out


def main():
    e = Elf(sys.argv[1])
    e.analyze()
    vts = find_vtables(e)
    if sys.argv[2] == "list":
        for addr, (name, ents) in sorted(vts.items()):
            print(f"0x{addr:08x} {name:28} {len(ents)} entries")
        return
    key = sys.argv[3]
    targets = [a for a, (n, _) in vts.items() if n == key or f"{a:x}" == key.lower().replace("0x", "")]
    owners = {}
    for a, (n, ents) in vts.items():
        for _, fn in ents:
            owners.setdefault(fn, set()).add(n)
    for a in sorted(targets):
        name, ents = vts[a]
        print(f"vtable 0x{a:08x} class {name}")
        for i, (delta, fn) in enumerate(ents):
            others = sorted(owners[fn] - {name})
            tag = "UNIQUE" if not others else f"shared with {len(others)}: {', '.join(others[:4])}"
            s, t = e.func_of(fn) if fn else (0, 0)
            print(f"  [{i + 1:3}] delta={delta:<4} fn=0x{fn:08x} size={t - s:<5} {tag}")


if __name__ == "__main__":
    main()
