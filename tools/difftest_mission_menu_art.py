#!/usr/bin/env python3
"""Bounded original EE mission-map draw/input comparison, seeds 20973 and 7.

Pass the owner's v2.00 ELF. No game resource bytes or disassembly are emitted.
The UI texture/font/localization/GPU callees are stubbed, so this checks API
submissions and control flow, not a displayed retail frame.
"""
import argparse
import hashlib
import mmap
import struct

from ee_emu import EE
from difftest_story_route import MENU_FOLLOW
from anim_audio_info import iso_files, lmp_entries
import ref_mission_menu_art as R

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYER = 0x4d8af0


def scene(path, seed, mission1=1, mission2=0, medal=0):
    e = EE(path)
    m = e.mem
    e.follow = set()
    m.w32(0x404464, seed)
    m.w32(0x4d8ae0, 1)
    m.w32(0x4f719c, 0)
    m.w8(PLAYER + 0x4bbf, 3)
    m.w8(PLAYER + 0x4bbf + 1, mission1)
    m.w8(PLAYER + 0x4bbf + 2, mission2)
    m.w8(PLAYER + 0x4c0d + 1, medal)
    e.call(0x231520, 0)
    return e


def table(e):
    m = e.mem
    for i, (name, x, y) in enumerate(R.MISSION_PICTURES):
        a = 0x4fe540 + i * 0x34
        assert m.cstr(m.u32(a + 0x18), 40) == name
        assert (m.s32(a + 0x2c), m.s32(a + 0x30)) == (x, y)
        actual = tuple(m.cstr(m.u32(a + off), 40) if m.u32(a + off) else None
                       for off in (0, 8, 0x10, 0x14))
        assert actual == R.MISSION_ENTRIES[i], (i, actual)
        alternative = tuple(m.cstr(m.u32(a + off), 40) if m.u32(a + off) else None
                            for off in (4, 0xc, 0x1c))
        assert alternative == R.EVIL_ALTERNATES.get(i, (None, None, None)), (i, alternative)
    a = 0x4fe540 + 12 * 0x34
    assert all(m.u32(a + off) == 0 for off in range(0, 0x20, 4))
    assert tuple(m.u32(a + off) for off in (0x20, 0x24, 0x28, 0x2c, 0x30)) == (1, 1, 1, 0, 0)


def disc_sizes(path):
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        files = iso_files(mm)
        matches = [value for name, value in files.items() if name.endswith('/MSEL.LMP')]
        assert len(matches) == 1
        offset, size = matches[0][:2]
        blob = mm[offset:offset + size]
    dimensions = {name.lower(): struct.unpack_from('<HH', blob, at)
                  for name, at, size in lmp_entries(blob) if name.lower().endswith('.tex')}
    for name, expected in R.MSEL_SIZES.items():
        assert dimensions[name] == expected, (name, dimensions.get(name), expected)
    return len(dimensions)


def draw(path, seed, mission2=0, mission1=1, medal=0, row=0, col=0,
         network=False, prompt=True, pause=False, resource_present=False,
         all_available=False, evil=False):
    e = scene(path, seed, mission1, mission2, medal)
    m = e.mem
    m.w8(0x8e2efc, 2)
    m.w8(0x8e2f0c, row)
    m.w8(0x8e2f0e, row)
    m.w8(0x8e2f0d, col)
    m.w32(0x8e2f04, 127)
    m.w32(0x4f7104, 0x12345678)
    m.w8(0x402791, int(network))
    if all_available:
        for mission in range(1, 13):
            m.w8(PLAYER + 0x4bbf + mission, 1)
    e.follow = MENU_FOLLOW | {0x2331e8, 0x3b8278}
    e.stub(0x1658f0, function=lambda x: x.fset(0, 0.0))
    e.stub(0x1bf8d8, ret=int(evil))
    if resource_present:
        e.stub(0x17365c, ret=1)
    keys = []
    e.stub(0x173c84, function=lambda x: keys.append(x.mem.cstr(x.r[4] & 0xffffffff, 80)) or 0)
    e.stub(0x13d668, ret=int(prompt))
    e.stub(0x18cbfc, ret=int(pause))
    e.reset_log()
    e.call(0x232300, max_steps=1000000)
    textures = [(c.site, m.cstr(c.args[1] & 0xffffffff, 64)) for c in e.calls
                if c.target == 0x17365c]
    sprites = [(c.site, tuple(v & 0xffffffff for v in c.args[1:5]))
               for c in e.calls if c.target == 0x17fb88]
    return e, textures, sprites, keys


def check_draw(path, seed):
    count = 0
    for available in (0, 1):
        e, tex, sprites, keys = draw(path, seed, mission2=available)
        m = e.mem
        rows, pipes = R.first_view(available)
        names = [name for site, name in tex if site == 0x2328cc]
        assert names == [r[0] for r in rows]
        row_calls = [args for site, args in sprites if site == 0x232908]
        assert row_calls == [(x, y, 4, tint) for _, x, y, tint in rows], row_calls
        pipe_names = [name for site, name in tex if site == 0x232b30]
        pipe_calls = [args for site, args in sprites if site == 0x232bc0]
        assert pipe_names == [p[0] for p in pipes]
        assert pipe_calls == [(x, y, 4, tint) for _, x, y, tint in pipes], pipe_calls
        assert [args[:3] for site, args in sprites if site in (0x232474, 0x2324bc)] == list(R.FRAME_STRIPS)
        assert [name for _, name in tex].count('cosmiclines.tex') == 4
        assert [name for _, name in tex].count('starfield.tex') == 4
        assert [name for _, name in tex].count('starsparkle.tex') == 1
        assert keys == ['Plane_of_War_mis', 'Plane_of_War_mis_title', 'AcceptBack']
        assert any(c.site == 0x232f2c and c.args[0] == 0x12345678 and c.args[1] == 5
                   and c.args[2] == 0x49616a for c in e.calls)
        assert any(c.site == 0x233044 and c.args[:6] == (320, 267, 0, 550, 262, 365)
                   for c in e.calls)
        assert any(c.site == 0x233074 and c.args[:2] == (320, 235) for c in e.calls)
        assert any(c.site == 0x2330f8 and c.args[:2] == (320, 410) for c in e.calls)
        assert any(c.site == 0x2331a8 and c.args[:4] == (25, 230, 590, 215)
                   for c in e.calls)
        count += 1
    for col in (0, 1, 2):
        e, tex, sprites, keys = draw(path, seed, mission1=3, medal=3, col=col)
        assert keys == [*R.detail_keys('Plane_of_War', col), 'AcceptBack']
        glow = R.GLOWS[col]
        assert glow[0] in [name for _, name in tex]
        assert (glow[1], glow[2], 4) in [args[:3] for site, args in sprites
                                         if site in (0x232a9c, 0x2329c0)]
        count += 1
    for prompt, pause, expected in ((False, False, 'clientMissionSelect'),
                                    (False, True, None), (True, False, 'AcceptBack')):
        _, _, _, keys = draw(path, seed, network=True, prompt=prompt, pause=pause)
        assert keys[:2] == list(R.detail_keys('Plane_of_War', 0))
        assert keys[2:] == ([] if expected is None else [expected])
        count += 1
    for (mission1, medal), expected in R.FIRST_ICONS.items():
        e, tex, sprites, _ = draw(path, seed, mission1=mission1, medal=medal,
                                  resource_present=True)
        icon_sites = (0x2325f4, 0x2326a0, 0x232754, 0x2327ec)
        sprite_sites = (0x232630, 0x232734, 0x2327a4, 0x232828)
        actual_names = [name for site, name in tex if site in icon_sites]
        actual_xy = [(args[0], args[1]) for site, args in sprites if site in sprite_sites]
        assert actual_names == [name for name, _, _ in expected], actual_names
        assert actual_xy == [(x, y) for _, x, y in expected], actual_xy
        count += 1
    for row in range(12):
        for unlocked in (False, True):
            _, tex, sprites, _ = draw(path, seed, row=row, all_available=unlocked)
            names = [name for site, name in tex if site == 0x2328cc]
            actual = [args for site, args in sprites if site == 0x232908]
            expected = R.viewport(row, unlocked)
            assert names == [name for name, *_ in expected], (row, unlocked, names)
            assert actual == [tuple(data[1:]) for data in expected], (row, unlocked, actual)
            count += 1
    _, tex, sprites, keys = draw(path, seed, row=11, evil=True)
    assert (0x23286c, 'missairend.tex') in tex
    assert (0x2328a8, (70, 40, 4, 0x7f3c3c3c)) in sprites
    assert keys[:2] == ['Plane_of_Tranquil_mis', 'Plane_of_Tranquil_mis_title']
    count += 1
    return count


def input_phase(e):
    m = e.mem
    e.follow = MENU_FOLLOW
    e.stub(0x13e150, ret=0)
    e.stub(0x13dd40, ret=1)
    e.stub(0x18cbfc, ret=0)
    for _ in range(17):
        m.w32(0x41bfe4, 0)
        e.call(0x2316fc, max_steps=400000)
    assert m.s8(0x8e2efc) == 2


def check_input(path, seed):
    cases = ((1, 0, 0, 0x40, (5, 0, 0), 'menu_main_accept.anm'),
             (1, 0, 0, 0x20, (4, 0, 0), 'menu_main_accept.anm'),
             (1, 0, 0, 0x8000, (2, 0, 0), None),
             (1, 0, 0, 0x4000, (2, 0, 0), None),
             (3, 0, 0, 0x8000, (2, 0, 1), 'menu_main_toggle.anm'),
             (3, 0, 1, 0x8000, (2, 0, 1), 'menu_main_toggle.anm'),
             (3, 0, 3, 0x8000, (2, 0, 1), 'menu_main_toggle.anm'),
             (1, 1, 0, 0x4000, (2, 1, 0), 'menu_main_toggle.anm'))
    for mission1, mission2, medal, button, expected, sound in cases:
        e = scene(path, seed, mission1, mission2, medal)
        input_phase(e)
        m = e.mem
        if button == 0x4000:
            m.w8(0x8e2f0c, 0)
        m.w32(0x41bfe4, button)
        e.reset_log()
        e.call(0x2316fc, max_steps=400000)
        assert (m.s8(0x8e2efc), m.s8(0x8e2f0c), m.s8(0x8e2f0d)) == expected
        sounds = [m.cstr(c.args[1] & 0xffffffff, 40) for c in e.calls
                  if c.target == 0x17365c]
        assert sounds == ([] if sound is None else [sound]), sounds
        assert m.u32(0x404464) == seed
    for medal, expected in ((0, 1), (1, 1), (2, 1), (3, 2)):
        e = scene(path, seed, 3, 0, medal)
        input_phase(e)
        m = e.mem
        m.w8(0x8e2f0d, 1)
        m.w32(0x41bfe4, 0x8000)
        e.call(0x2316fc, max_steps=400000)
        assert m.s8(0x8e2f0d) == expected
    return len(cases) + 4


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', required=True)
    p.add_argument('--iso', help='optional read-only MSEL.LMP texture-header check')
    args = p.parse_args()
    with open(args.elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == ELF_SHA256
    if args.iso:
        print('PASS disc MSEL.LMP: %d texture entries; selected dimensions match' % disc_sizes(args.iso))
    for seed in (20973, 7):
        e = scene(args.elf, seed)
        table(e)
        draws = check_draw(args.elf, seed)
        inputs = check_input(args.elf, seed)
        print('PASS seed %d: 13 mission rows, %d draw cases, %d input cases' %
              (seed, draws, inputs))


if __name__ == '__main__':
    main()
