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
    return len(names)


def check_start(path, seed):
    """Execute original CD lookup, resource selection and three dark frames."""
    cases = (("innovat2", 0, "linnova2.lmp", 1),
             ("innovat2", 1, "LINNOVA2.LMP", 2),
             ("innovat2", 2, "linnova2.lmp", 0),
             ("hub", 3, "lhub.lmp", 1),
             ("blood1", 4, "lblood1.lmp", 1),
             ("torment4", 0, "ltorment.lmp", 1))
    titles = ("titleload.tex", "titleloadsp.tex", "titleloadit.tex",
              "titleloadfr.tex", "titleloadgr.tex")
    for name, language, available, hit_on in cases:
        emu = EE(path)
        emu.follow = {0x321C9C, 0x3B96A8, 0x3B8534}  # alias and libc comparisons
        emu.mem.write(0x44FE18, name.encode() + b"\0")
        emu.mem.w32(0x404460, seed)
        emu.mem.w8(0x44FDDC, language)
        emu.mem.w32(0x506090, 0xFFFFFFFF)  # no prior loading thread
        searches, loads, resources = [], [], {}

        def sprintf(e):
            dest = e.r[4] & 0xFFFFFFFF
            value = "l" + e.mem.cstr(e.r[6] & 0xFFFFFFFF)
            e.mem.write(dest, value.encode() + b"\0")
            return len(value)

        def strcat(e):
            dest = e.r[4] & 0xFFFFFFFF
            value = e.mem.cstr(dest) + e.mem.cstr(e.r[5] & 0xFFFFFFFF)
            e.mem.write(dest, value.encode() + b"\0")
            return dest

        def cd_find(e):
            requested = e.mem.cstr(e.r[4] & 0xFFFFFFFF)
            searches.append(requested)
            return int(len(searches) == hit_on and requested.lower() == available.lower())

        def lump_load(e):
            loads.append(e.mem.cstr(e.r[4] & 0xFFFFFFFF))
            return 0x01010000

        def res_find(e):
            label = e.mem.cstr(e.r[5] & 0xFFFFFFFF)
            handle = e.alloc(64)
            resources[label] = handle
            return handle

        emu.stub(0x3B7EF0, function=sprintf)
        emu.stub(0x3B8278, function=strcat)
        emu.stub(0x1724FC, function=cd_find)
        emu.stub(0x173558, function=lump_load)
        emu.stub(0x17365C, function=res_find)
        assert emu.run(0x321E60, until=(0x322400,), max_steps=50000) == "stop"
        candidate = ("l" + R.picture_alias(name))[:8] + ".lmp"
        assert searches == [candidate] * (1 if hit_on == 1 else 2), \
               (name, language, hit_on, searches)
        assert loads == [candidate if hit_on else "lmiss.lmp", "loadmisc.lmp"], loads
        handles = [resources[key] for key in (titles[language], "shot.tex",
                                                "scrollbar.tex", "scrollbar2.tex",
                                                "scrollbar3.tex")]
        assert len(resources) == 5, resources
        draws = [c for c in emu.calls if c.target == SPRITE]
        assert len(draws) == 15
        assert [c.site for c in draws] == [0x3220D0, 0x3220EC, 0x322108,
                                            0x322124, 0x322140] * 3
        for index, draw in enumerate(draws):
            assert tuple(x & 0xFFFFFFFF for x in draw.args[:5]) == \
                   (handles[index % 5], 0, 0, 6, 0x80606060)
        assert len([c for c in emu.calls if c.target == 0x19D8B0]) == 3
        assert len([c for c in emu.calls if c.target == 0x19DA78]) == 3
    return len(cases)


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
        assert [c.args[0] & 0xFFFFFFFF for c in draws] == \
               [0x8ED900, 0x8ED940, 0x8ED9C0, 0x8ED9C0, 0x8EDA00, 0x8EDA00] + \
               [0x8ED980] * 8
        assert [c.args[3] & 0xFFFFFFFF for c in draws[:6]] == [6] * 6
        assert [c.args[4] & 0xFFFFFFFF for c in draws[:6]] == \
               [0x80808080] * 2 + [0x14808080] * 4
        assert [(c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
                for c in draws[6:]] == [(6, 0x80808080)] * 8
        trig = [c for c in emu.calls if c.target in (0x1666E0, 0x166630)]
        assert [c.target for c in trig] == [0x1666E0, 0x166630]
        assert [c.args[0] & 0xFFFFFFFF for c in trig] == \
               [((seed + frame) * 100) & 0xFFFFFFFF] * 2
        assert all(c.fargs[2:4] == (0x3F800000, 0x3F800000) for c in draws[6:])
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
        starts = check_start(path, seed)
        fade = check_fade(path, seed)
        draws = check_draw(path, seed)
        music = check_entry_music(path, seed)
        print("PASS seed=%d alias=%d start=%d draw=%d fade=%d entry_music=%d" %
              (seed, aliases, starts, draws, fade, music))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
