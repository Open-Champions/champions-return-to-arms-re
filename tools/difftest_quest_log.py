#!/usr/bin/env python3
"""Compare original quest-page UI submissions with a small reference model.

Requires the owner's US v2.00 ELF and ISO. Original code runs in ee_emu with
resource, font, localization and GPU callees stubbed. No game bytes are written.
"""
import argparse
import hashlib
import mmap
import struct

from anim_audio_info import gob_entries, iso_files, lmp_entries
from ee_emu import EE
import ref_quest_log as R
import scr

ELF_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
PLAYER = 0x4D8AF0
SEED = 0x404464
COSMETIC_SEED = 0x404460


def disc_file(disc, files, name):
    matches = [entry for path, entry in files.items() if path.endswith("/" + name)]
    assert len(matches) == 1, (name, len(matches))
    offset, size = matches[0][:2]
    return disc[offset:offset + size]


def parchment_size(disc, files):
    lump = disc_file(disc, files, "INVENTRY.LMP")
    entries = [(at, size) for name, at, size in lmp_entries(lump)
               if name.lower() == "parchment.tex"]
    assert len(entries) == 1, len(entries)
    at, size = entries[0]
    assert size >= 4
    return struct.unpack_from("<HH", lump, at)


def disc_script(disc, files, level):
    gob = disc_file(disc, files, level.upper() + ".GOB")
    lumps = [(off, size) for name, off, size in gob_entries(gob)
             if name.lower() == level + ".lmp"]
    assert len(lumps) == 1, (level, lumps)
    off, size = lumps[0]
    lump = gob[off:off + size]
    scripts = [(off, size) for name, off, size in lmp_entries(lump)
               if name.lower() == "script.scr"]
    assert len(scripts) == 1, (level, scripts)
    off, size = scripts[0]
    return lump[off:off + size]


class ScriptCheck:
    """Read only addressed checks of shipped script cells, without a listing."""

    def __init__(self, image):
        self.image = image
        parsed = scr.parse(image)
        self.start, self.end = parsed["code"]
        self.entries = {name: offset for offset, name in parsed["internals"]}
        self.natives = [name for _, name in parsed["externals"]]
        self.strings = dict(scr.strings(image, *parsed["strings"]))

    def word(self, offset):
        assert offset % 4 == 0 and 0 <= offset < self.end - self.start, hex(offset)
        return struct.unpack_from("<I", self.image, self.start + offset)[0]

    def words(self, offset, *expected):
        got = tuple(self.word(offset + 4 * i) for i in range(len(expected)))
        assert got == expected, (hex(offset), got, expected)

    def call(self, offset, native, *args):
        self.words(offset, 0x7B, self.natives.index(native))
        # The script pushes arguments right-to-left, then their byte count.
        for i, expected in enumerate((*reversed(args), len(args) * 4)):
            at = offset - 8 * (len(args) + 1 - i)
            assert self.word(at) == 0x27, (hex(at), self.word(at))
            value = self.word(at + 4)
            if isinstance(expected, str):
                assert self.strings.get(value) == expected, (hex(at), value)
            elif expected is None:
                assert value in self.strings and self.strings[value], (hex(at), value)
            else:
                assert value == expected, (hex(at), value, expected)


def check_mission_scripts(disc, files):
    hub = ScriptCheck(disc_script(disc, files, "hub"))
    for entry, start, site in (("setMissic270", 0x07B0, 0x07E4),
                               ("setMissid125", 0x07FC, 0x0830)):
        assert hub.entries[entry] == start, (entry, hub.entries[entry])
        hub.words(start, 0x2E)
        hub.call(site, "setMissionAvailable", 2, 1)

    for level, entry, demo, non_demo, counter, notice_cmp, notice_skip, notice, \
            threshold, threshold_skip, grant, home, alternate in (
                ("strife", 0x19E8, 0x1A0C, 0x1B78, 0x15C, 0x1A38,
                 0x1A7C, 0x1A6C, 0x1A88, 0x1B00, 0x1ABC, 0x1AE8, 0x1B94),
                ("drundar", 0x1918, 0x193C, 0x1AA8, 0x30, 0x1968,
                 0x19AC, 0x199C, 0x19B8, 0x1A30, 0x19EC, 0x1A18, 0x1AC4)):
        script = ScriptCheck(disc_script(disc, files, level))
        assert script.entries["exitzone"] == entry, (level, script.entries["exitzone"])
        script.words(entry, 0x2E)
        script.call(demo, "demoRunning")
        script.words(demo + 0x10, 0x35, non_demo)
        script.words(notice_cmp - 8, 0x01, counter)
        script.words(notice_cmp, 0x69, 70)
        script.words(notice_cmp + 8, 0x35, notice_skip)
        script.call(notice, "addHelpMessage", None, None)
        script.words(threshold, 0x02, counter, 0x0B, 150, 0x40, threshold_skip)
        script.call(grant, "grantMission", 1)
        script.call(home, "newWorld", "hub")
        script.call(alternate, "newWorld", "drunarm" if level == "strife" else "drunare")
    return 3


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
        fonts = [(c.site, tuple(v & 0xFFFFFFFF for v in c.args[:4])) for c in e.calls
                 if c.target == 0x1800B8]
        assert fonts == [(0x1D26AC, (0, 6, 0x80323C3C, 0xFFFFFFFF))] * count, fonts
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
    with open(args.iso, "rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        files = iso_files(disc)
        assert parchment_size(disc, files) == R.PARCHMENT
        scripts = check_mission_scripts(disc, files)
    count = 0
    for seed in (20973, 7):
        check_route(args.elf, seed)
        count += 3
        for quests in (0, 1, 2, 8):
            check_page(args.elf, seed, quests)
            count += 1
    print("PASS quest-log: %d original/controlled page probes, two seeds, %d disc scripts, parchment %s"
          % (count, scripts, R.PARCHMENT))


if __name__ == "__main__":
    main()
