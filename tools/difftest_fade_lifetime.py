#!/usr/bin/env python3
"""Bounded HUD fade probes on the owner's RTA US v2.00 executable.

Usage: python3 tools/difftest_fade_lifetime.py /path/to/SLUS_209.73
Only counts and pass/fail are printed. The input is never written.
"""
import struct
import sys

from ee_emu import EE, load_elf_segments

FADE = 0x4F66AC
SET = 0x1DF5D0
STEP = 0x1DF5EC
LOAD_START, LOAD_END = 0x1E55C0, 0x1E6220


def main(path):
    image = EE(path)
    assert image.mem.u32(FADE) == 0, "ELF fade image is not zero"
    # Count direct JALs to the setter. This bounds the claim about the level
    # loader itself; indirect calls and callees of the loader remain outside it.
    sites = []
    for base, blob, _ in load_elf_segments(path)[0]:
        for offset in range(0, len(blob) - 3, 4):
            word = struct.unpack_from("<I", blob, offset)[0]
            if word >> 26 == 3 and (((base + offset + 4) & 0xF0000000) |
                                     ((word & 0x3FFFFFF) << 2)) == SET:
                sites.append(base + offset)
    assert sites and not any(LOAD_START <= site < LOAD_END for site in sites)

    cases = [(0, 0), (1, 128)]
    for on, expected in cases:
        e = EE(path)
        e.mem.w32(FADE, 37)
        e.call(SET, on)
        assert e.mem.u32(FADE) == expected
        assert any(w[1] == FADE and w[3] == expected for w in e.writes)
    for start, delta, expected in [(0, 40, 40), (128, -16, 112)]:
        e = EE(path)
        e.follow = set()  # only the presentation draw callee is stubbed
        e.mem.w32(FADE, start)
        result = e.call(STEP, delta)
        assert result == expected and e.mem.u32(FADE) == expected

    # With external level services stubbed, the loader's own body leaves a
    # planted fade value in place. This does not establish all callee behavior.
    e = EE(path)
    e.follow = set()
    e.mem.auto_map = True
    e.mem.w32(FADE, 37)
    e.call(LOAD_START, 0x400000, max_steps=250000)
    assert e.mem.u32(FADE) == 37
    assert not any(w[1] == FADE for w in e.writes)
    print("PASS: ELF zero; 2 setter and 2 step cases; loader-body retention; %d direct setter sites, none in loader" % len(sites))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
