#!/usr/bin/env python3
"""Compare original quest-page UI submissions with a small reference model.

Requires the owner's US v2.00 ELF and ISO. Original code runs in ee_emu with
resource, font, localization and GPU callees stubbed. No game bytes are written.
"""
import argparse
import hashlib
import mmap
import struct

from anim_audio_info import iso_files, lmp_entries
from ee_emu import EE
import ref_quest_log as R

ELF_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
PLAYER = 0x4D8AF0
SEED = 0x404464
COSMETIC_SEED = 0x404460


def parchment_size(iso):
    with open(iso, "rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        matches = [entry for name, entry in iso_files(disc).items()
                   if name.endswith("/INVENTRY.LMP")]
        assert len(matches) == 1, len(matches)
        offset, size = matches[0][:2]
        lump = disc[offset:offset + size]
    entries = [(at, size) for name, at, size in lmp_entries(lump)
               if name.lower() == "parchment.tex"]
    assert len(entries) == 1, len(entries)
    at, size = entries[0]
    assert size >= 4
    return struct.unpack_from("<HH", lump, at)


def new_scene(elf, seed):
    e = EE(elf)
    e.follow = set()
    e.mem.w32(SEED, seed)
    e.mem.w32(COSMETIC_SEED, seed ^ 0x55555555)
    panel = e.alloc(0x74)
    return e, panel


def check_route(elf, seed):
    for page, expected_site in ((3, 0x1CD578), (4, 0x1CD594), (5, 0x1CD5CC)):
        e, panel = new_scene(elf, seed)
        e.mem.w32(panel + 0x50, page)
        e.call(0x1CD208, 0, 0, 0, panel, max_steps=100000)
        calls = [(c.site, c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if c.target == 0x1D1DB8]
        assert calls == [(expected_site, page - 3)], (page, calls)
        assert e.mem.u32(SEED) == seed


def check_page(elf, seed, count):
    e, panel = new_scene(elf, seed)
    mem = e.mem
    mem.w32(panel + 0x50, 4)
    mem.w32(PLAYER + 0x43D0, count)
    for i in range(count):
        mem.write(PLAYER + 0x41D0 + 0x40 * i, ("Q%d\0" % i).encode("ascii"))
        mem.write(PLAYER + 0x41F0 + 0x40 * i, ("B%d\0" % i).encode("ascii"))
    before = mem.read(PLAYER + 0x41D0, 8 * 0x40 + 4)
    e.call(0x1D1DB8, 0, 1, 0x34000000, panel, max_steps=100000)
    assert mem.read(PLAYER + 0x41D0, 8 * 0x40 + 4) == before
    assert mem.u32(SEED) == seed
    assert mem.u32(COSMETIC_SEED) == seed ^ 0x55555555

    textures = [(c.site, mem.cstr(c.args[0] & 0xFFFFFFFF, 32),
                 mem.cstr(c.args[1] & 0xFFFFFFFF, 32))
                for c in e.calls if c.target == 0x17365C]
    assert textures == [(0x1D263C, "inventry.lmp", "parchment.tex")], textures
    parchment = [(c.site, tuple(v & 0xFFFFFFFF for v in c.args[:5]))
                 for c in e.calls if c.target == 0x17FB68]
    assert parchment == [(0x1D2668, (0, 0xFFFFFFFC, 104, 5, 0x80808080))], parchment
    lookups = [(c.site, mem.cstr(c.args[0] & 0xFFFFFFFF, 32))
               for c in e.calls if c.target == 0x173C84]
    assert lookups == R.lookups(count), (count, lookups)
    wrapped = [(c.site, tuple(v & 0xFFFFFFFF for v in c.args[:7]))
               for c in e.calls if c.target == 0x181280]
    assert wrapped == R.wrapped_calls(count), (count, wrapped)
    if count:
        fonts = [(c.site, c.args[1] & 0xFFFFFFFF) for c in e.calls
                 if c.target == 0x1800B8]
        assert fonts == [(0x1D26AC, 6)] * count, fonts
        windows = [tuple(v & 0xFFFFFFFF for v in c.args[:4]) for c in e.calls
                   if c.target == 0x1803E0]
        assert windows == [(0, 119, 320, 440)] * count, windows
    else:
        assert not any(c.target == 0x181280 for c in e.calls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", required=True)
    parser.add_argument("--iso", required=True)
    args = parser.parse_args()
    with open(args.elf, "rb") as file:
        assert hashlib.file_digest(file, "sha256").hexdigest() == ELF_SHA256
    assert parchment_size(args.iso) == R.PARCHMENT
    count = 0
    for seed in (20973, 7):
        check_route(args.elf, seed)
        count += 3
        for quests in (0, 1, 2, 8):
            check_page(args.elf, seed, quests)
            count += 1
    print("PASS quest-page original/controlled model: %d probes, two seeds, parchment %s"
          % (count, R.PARCHMENT))


if __name__ == "__main__":
    main()
