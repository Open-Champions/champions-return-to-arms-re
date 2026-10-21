#!/usr/bin/env python3
"""List constant-string call sites (resource lookups, sound and music requests) in a code range.

Usage: scan_lookup_sites.py path/to/SLUS_209.73 LO HI

Reads MIPS words straight from the executable's loaded image (through tools/ee_emu.py)
and, for every `jal` to a watched function in [LO, HI), reports the call site and
the C strings its first two arguments were built from by a nearby `lui` + `addiu`
pair on the same register. Only direct constant addresses within sixteen instructions
are decoded; anything else is reported as None. Strings printed are resource
identifiers (lump and entry names), never localized text. Nothing is written.
"""
import os
import sys

sys.path.append(os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402

# target: (name, argument registers that hold constant strings)
WATCHED = {
    0x17365C: ("res_find", (4, 5)),           # (lump, entry)
    0x214230: ("sound_playOnObject", ()),     # takes a looked-up entry, not a string
    0x2110E0: ("music_playGlobal", (4,)),     # (name, flags)
    0x215C20: ("stream_playGlobal", (5,)),    # (slot, name, ...)
    0x16CFE0: ("anim_start", ()),
    0x173558: ("lump_load", (4,)),
}
WINDOW = 16


def decode_constant(words, index, reg):
    """Constant address held in `reg` just before words[index], or None."""
    lui = add = None
    for j in range(index - 1, max(index - 1 - WINDOW, -1), -1):
        w = words[j]
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F and rt == reg:                       # lui
            lui = imm
            break
        if op in (0x09, 0x0D) and rt == reg and rs == reg and add is None:  # addiu / ori
            add = imm - 0x10000 if (op == 0x09 and imm & 0x8000) else imm
        elif rt == reg and op not in (0x2B, 0x2A, 0x2E, 0x28, 0x29, 0x2F):
            if add is None and op != 0x00:
                break
    if lui is None or add is None:
        return None
    return ((lui << 16) + add) & 0xFFFFFFFF


def scan(e, lo, hi):
    words = [e.mem.u32(a) for a in range(lo, hi, 4)]
    out = []
    for i, w in enumerate(words):
        if w >> 26 != 3:
            continue
        target = (w & 0x3FFFFFF) << 2
        if target not in WATCHED:
            continue
        name, regs = WATCHED[target]
        strings = []
        # The delay-slot instruction executes before the callee, so it counts.
        before = words[:i] + words[i + 1:i + 2]
        for reg in regs:
            addr = decode_constant(before, len(before), reg)
            text = None
            if addr is not None and e.mem.is_mapped(addr, 1):
                try:
                    text = e.mem.cstr(addr, 64)
                except Exception:
                    text = None
            strings.append(text)
        out.append((lo + 4 * i, name, tuple(strings)))
    return out


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    e = EE(sys.argv[1])
    for site, name, strings in scan(e, int(sys.argv[2], 16), int(sys.argv[3], 16)):
        print("0x%X %s %r" % (site, name, strings))


if __name__ == "__main__":
    main()
