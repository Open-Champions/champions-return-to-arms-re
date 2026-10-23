#!/usr/bin/env python3
"""Bounded loading-screen and transition comparison against RTA US v2.00.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loading.py local/SLUS_209.73
Only synthetic names, directories and texture dimensions are used. GPU, IOP, CD,
thread scheduling, and actual picture pixels are outside this function-level test.
"""
import hashlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE  # noqa: E402
import ref_loading as R  # noqa: E402

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SPRITE = 0x17FB68
ROTATED = 0x17FB18
DRAW_SITES = (0x321938, 0x321994, 0x3219D8, 0x3219FC, 0x321A20,
              0x321A4C, 0x321B10, 0x321B34, 0x321B58, 0x321B88,
              0x321BB4, 0x321BD8, 0x321BFC, 0x321C20)
DIMENSIONS = {0x8ED900: (640, 320), 0x8ED940: (184, 78),
              0x8ED980: (640, 128), 0x8ED9C0: (640, 96),
              0x8EDA00: (640, 96)}


def check_alias(path, seed):
    names = ("blood1", "blofoo", "BLOOD1", "innovat2", "innovat1",
             "valor", "valor2", "bastion2", "nitdung1", "nitdung2",
             "nitdung3", "nitdung4", "tormenta", "tormentb", "torment2",
             "torment3", "torment4", "pvpfire2", "hub")
    emu = EE(path)
    emu.mem.w32(0x404464, seed)
    for name in names:
        raw = name.encode("ascii") + b"\0"
        ptr = emu.alloc(len(raw))
        emu.mem.write(ptr, raw)
        got = emu.mem.cstr(emu.call(0x321C9C, ptr))
        assert got == R.picture_alias(name), (name, got)
        candidate = ("l" + got)[:8] + ".lmp"
        assert R.picture_lump(name, {candidate}) == candidate
        assert R.picture_lump(name, {candidate.upper()}) == candidate
        assert R.picture_lump(name, set()) == "lmiss.lmp"
    return len(names)


def check_draw(path, seed):
    frames = (0, 1, 239, 639, 640, 641, seed % 640)
    for frame in frames:
        emu = EE(path)
        emu.follow = {0x1666E0, 0x166630}  # real sine/cosine; UI and GPU are captured
        emu.mem.w32(0x506098, frame)
        emu.mem.w32(0x50609C, seed)
        emu.stub(0x17FFA0, function=lambda e: DIMENSIONS[e.r[4] & 0xFFFFFFFF][0])
        emu.stub(0x17FFA8, function=lambda e: DIMENSIONS[e.r[4] & 0xFFFFFFFF][1])
        emu.stub(0x19DA78, function=lambda e: e.mem.w8(0x5060A0, 1))
        emu.call(0x32187C, max_steps=100000)
        draws = [c for c in emu.calls if c.target in (SPRITE, ROTATED)]
        assert tuple(c.site for c in draws) == DRAW_SITES
        assert sum(c.target == SPRITE for c in draws) == 6
        assert sum(c.target == ROTATED for c in draws) == 8
        assert [(c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                for c in draws[:2]] == [(0, 100), (228, 185)]
        x0, x1 = R.strip_positions(frame)
        assert [c.args[1] & 0xFFFFFFFF for c in draws[2:6]] == \
               [x0, x1 & 0xFFFFFFFF, x0, x1 & 0xFFFFFFFF]
        assert [c.args[2] for c in draws[2:6]] == [0, 0, 352, 352]
        assert emu.mem.u32(0x506098) == frame + 1
        assert not any(0x181000 <= c.target < 0x182000 for c in emu.calls)  # no font/text
    return len(frames)


def check_fade(path, seed):
    # The inner present pass is isolated; packet submission is outside this slice.
    values = (0, 1, 4, 120, 123, 124, 125, 127, 128, 129, 132, 133, 255)
    emu = EE(path)
    emu.mem.w32(0x404464, seed)
    for value in values:
        for address in (0x44FD8C, 0x44FD90, 0x44FD94):
            emu.mem.w32(address, value)
        emu.r[10] = 0x44FD8C
        emu.r[11] = 128
        emu.run(0x19CF0C, until=(0x19CF98,), max_steps=100)
        assert tuple(emu.mem.u32(a) for a in (0x44FD8C, 0x44FD90, 0x44FD94)) == \
               (R.fade_channel(value),) * 3, value
    emu.call(0x19B6BC, -128, -128, -128)
    assert tuple(emu.mem.u32(a) for a in (0x44FD8C, 0x44FD90, 0x44FD94)) == (0, 0, 0)
    return len(values) + 1


def check_entry_music(path, seed):
    cases = ((False, ("plain", "mx_enttag_a", "mx_enttag_b")),
             (False, ("plain", "other")), (False, ()),
             (True, ("mx_enttag_a",)))
    for recall, names in cases:
        emu = EE(path)
        emu.follow = {0x3B96A8}  # real case-sensitive strstr
        emu.mem.w32(0x404464, seed)
        emu.mem.w8(0x41B51C, int(recall))
        emu.r[2] = seed
        emu.r[3] = 0x400000  # inherited from 0x1e59b8
        emu.r[6] = int(recall)
        directory = emu.alloc(0x50 * (len(names) + 1))
        emu.mem.write(directory, b"".join(n.encode() + b"\0" +
                      bytes(0x4F - len(n)) for n in names) + bytes(0x50))
        emu.stub(0x216860, ret=directory)
        for addr in (0x215F48, 0x211338, 0x1EC0E0, 0x355490):
            emu.stub(addr)
        emu.run(0x1E59C0, until=(0x1E5A98,), max_steps=100000)
        events = [c for c in emu.calls if c.target in (0x215F48, 0x211338)]
        action, name = R.entry_music(names, recall)
        if action == "keep":
            assert not events
        elif action == "stop":
            assert len(events) == 1 and events[0].target == 0x211338
            assert events[0].args[0] == 2
        else:
            assert len(events) == 1 and events[0].target == 0x215F48
            assert emu.mem.cstr(events[0].args[0] & 0xFFFFFFFF) == name
            assert events[0].args[1] == 2
    return len(cases)


def main(path):
    with open(path, "rb") as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA256, "wrong executable"
    for seed in (20973, 7):
        aliases = check_alias(path, seed)
        fade = check_fade(path, seed)
        draws = check_draw(path, seed)
        music = check_entry_music(path, seed)
        print("PASS seed=%d alias=%d draw=%d fade=%d entry_music=%d" %
              (seed, aliases, draws, fade, music))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
