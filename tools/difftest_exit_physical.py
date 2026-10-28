#!/usr/bin/env python3
"""Execute the original physical-use query through slot-14 dispatch.

Run from the repository root: python3 -m tools.difftest_exit_physical
Requires the private hash-pinned executable in local/SLUS_209.73.
Output is counts only. No instruction patch or control-flow bypass is used.
"""
import argparse
import hashlib
import os
import random
import sys
import unittest  # preload before tools/dis.py can shadow the standard library

sys.path.insert(0, os.path.dirname(__file__))
import difftest_objects as D
import ref_core as F
import ref_objects as O
import ref_exit_physical as R

PLAYER_INTERACT = 0x1b2640
QUERY = 0x14a928
ACTIVE = 0x4d8ae4
RECORDS = 0x4d8af0


class PhysicalRig:
    def __init__(self, elf, seed, fpu):
        self.rig = D.Rig(elf, seed, fpu)
        self.ee, self.world = self.rig.emu, self.rig.model
        self.mem = self.ee.mem
        self.player = self.ee.alloc(0x600)
        self.record_player = self.ee.alloc(0x600)
        self.pad = self.ee.alloc(0x58)
        self.vtable = self.ee.alloc(0x100)
        self.targets = self.ee.alloc(24)
        self.ee.stub(self.targets, ret=0)
        self.ee.stub(self.targets + 8, function=self.prompt)
        self.ee.stub(self.targets + 16, function=self.use)
        self.mem.w32(self.vtable + 4, self.targets)
        self.mem.w32(self.vtable + 0x6c, self.targets + 8)
        self.mem.w32(self.vtable + 0x74, self.targets + 16)
        # Generic fixture objects do not match the two presentation-only RTTI
        # categories. Text width, input glyph and drawing are supplied services.
        # UTF-16 copy/concatenation and all Player_interact branches run for real.
        for addr in (0x3b1250, 0x3c2f40, 0x3c3030, 0x1d99f0):
            self.ee.stub(addr, ret=0)
        self.ee.stub(0x181bf8, ret=1)
        self.ee.stub(0x1eacb8, ret=0x41)
        self.ee.hook(QUERY, self.query_entry)
        self.ee.hook(0x1b2738, self.query_return)
        self.events = []
        self.queries = []
        self.effects = 0
        self.cases = 0
        self.prompt_result = 1
        self.first_character = 65

    def new(self, xyz, flags=0x100000, radius=24, height=72):
        args = (0x180, tuple(F.f32(v) for v in xyz), 0, 0, 'none', flags, 0)
        want = self.rig.m_new(*args)
        got = self.rig.e_new(*args)
        assert got == want and got, 'constructor/allocation mismatch'
        assert not self.rig.failures, 'original constructor setup mismatch'
        obj = self.world.objects[got]
        obj.radius, obj.height = F.f32(radius), F.f32(height)
        self.mem.w32(got + 0x1c, obj.radius)
        self.mem.w32(got + 0x20, obj.height)
        self.mem.w32(got + 0x48, self.vtable)
        return got

    def move(self, addr, xyz):
        args = (addr, *(F.f32(v) for v in xyz))
        self.rig.m_move(*args)
        self.rig.e_move(*args)

    def flags(self, addr, value):
        self.rig.m_flags(addr, value)
        self.rig.e_flags(addr, value)
        obj = self.world.objects[addr]
        self.world.update_grid_cell(obj)
        self.rig.ecall(0x14f028, addr)

    def offgrid(self, addr):
        self.rig.m_offgrid(addr)
        self.rig.e_offgrid(addr)

    def prompt(self, e):
        self.events.append(('prompt', e.r[4], e.r[6], self.mem.s32(ACTIVE)))
        self.mem.w16(e.r[5], self.first_character)
        self.mem.w16(e.r[5] + 2, 0)
        return self.prompt_result

    def use(self, e):
        self.events.append(('use', e.r[4], e.r[5], self.mem.s32(ACTIVE)))
        self.effects += 1
        return 0

    def query_entry(self, e):
        lo = tuple(self.mem.u32(e.r[4] + 4*i) for i in range(3))
        hi = tuple(self.mem.u32(e.r[5] + 4*i) for i in range(3))
        assert (lo, hi, e.r[7]) == self.expected_bounds, 'query input mismatch'
        self.output = e.r[6]

    def query_return(self, e):
        out = []
        for i in range(256):
            obj = self.mem.u32(self.output + i*4)
            if not obj:
                break
            out.append(obj)
        else:
            raise AssertionError('query missing terminator')
        assert e.r[2] == self.output + 4*len(out), 'query return pointer'
        self.queries.append(tuple(out))

    def check(self, xyz=(0, 0, 0), slot=0, health=100, vehicle=0,
              has_player=True, result=1, text=65, pressed=0x200, held=0,
              use_mask=0x200, display=0, exclude=0):
        pos = tuple(F.f32(v) for v in xyz)
        x, y, z = pos
        self.expected_bounds = ((F.sub(x, F.f32(48)), F.sub(y, F.f32(48)), z),
                                (F.add(x, F.f32(48)), F.add(y, F.f32(48)),
                                 F.add(z, F.f32(60))), 256)
        self.world.exclude_mask = exclude
        self.mem.w32(O.G_EXCLUDE_MASK, exclude)
        self.mem.w32(self.player + 0x3c8, slot)
        self.mem.w32(self.player + 0x540, vehicle)
        # Deliberately different: the query must use record.obj's position.
        for i, value in enumerate(pos):
            self.mem.w32(self.record_player + 0x10 + 4*i, value)
            self.mem.w32(self.player + 0x10 + 4*i, F.f32(5000))
        self.mem.w32(RECORDS + slot*0x4c30 + 0xac, F.f32(health))
        self.mem.w32(RECORDS + slot*0x4c30 + 0x43d8,
                     self.record_player if has_player else 0)
        self.mem.w32(self.pad + 8, held)
        self.mem.w32(self.pad + 12, pressed)
        self.mem.w32(0x41b9c0 + slot*4, use_mask)
        self.mem.w32(ACTIVE, 0xffffffff)
        self.prompt_result, self.first_character = result, text
        self.events.clear()
        self.queries.clear()
        before = self.effects
        ordered, chosen = R.physical_choice(self.world, pos, F.f32(health),
                                             vehicle, has_player)
        expected = []
        used = chosen is not None and R.dispatch(result, text, pressed, use_mask, display)
        if chosen is not None:
            expected.append(('prompt', chosen, slot, -1))
            if used:
                expected.append(('use', chosen, slot, slot))
        self.rig.ecall(PLAYER_INTERACT, self.player, self.pad, display)
        eligible = not vehicle and health > 0 and has_player
        assert self.queries == ([ordered] if eligible else []), 'ordered query mismatch'
        assert self.events == expected, 'prompt/dispatch/context mismatch'
        assert self.mem.s32(ACTIVE) == (slot if used else -1), 'active player mismatch'
        assert self.effects - before == int(used), 'observable callback effect mismatch'
        self.cases += 1
        return ordered, chosen


def run(elf, seed, fpu):
    rng = random.Random(seed)
    p = PhysicalRig(elf, seed, fpu)
    # Same-cell ties follow most recent insertion/movement, not record order.
    a = p.new((10, 10, 0))
    b = p.new((10, 10, 0))
    assert p.check()[1] == b
    p.move(a, (10, 10, 0))
    assert p.check()[1] == a
    # A generic competing interactable wins without any exit-class whitelist.
    competitor = p.new((2, 2, 0))
    assert p.check()[1] == competitor
    assert p.check(result=0)[1] == competitor  # no fallback to a farther prompt
    p.flags(competitor, 0)
    assert p.check()[1] == a
    p.flags(a, 0x120000)  # prediction copy
    assert p.check()[1] == b
    p.flags(b, 0x100800)  # secondary grid
    assert p.check()[1] is None
    p.flags(a, 0x100400)
    assert p.check(exclude=0x400)[1] is None
    p.flags(a, 0x100000)
    p.offgrid(a)
    assert p.check()[1] is None
    p.move(a, (10, 10, 0))
    assert p.check()[1] == a
    # Row/column ordering beats later insertion when ties occupy different cells.
    p.move(a, (-10, 0, 0))
    p.flags(b, 0x100000)
    p.move(b, (10, 0, 0))
    assert p.check()[1] == a
    p.move(a, (0, -10, 0))
    p.move(b, (0, 10, 0))
    assert p.check()[1] == a
    p.move(a, (500, 500, 0))
    p.move(b, (500, 500, 0))
    # Extent touches are inclusive, including one-sided height, not centre tests.
    extent = p.new((72, 0, 0))
    assert p.check()[1] == extent
    p.move(extent, (72.25, 0, 0))
    assert p.check()[1] is None
    p.move(extent, (0, 0, -72))
    assert p.check()[1] == extent
    p.move(extent, (0, 0, -72.25))
    assert p.check()[1] is None
    p.move(extent, (0, 0, 60))
    assert p.check()[1] == extent
    p.move(extent, (0, 0, 60.25))
    assert p.check()[1] is None
    # Large extents do not extend the grid-cell search beyond its fixed margin.
    giant = p.new((256, 0, 0), radius=300)
    assert p.check()[1] is None
    p.move(giant, (500, 500, 0))
    # Exact 10,000,000 squared-distance limit: membership is not enough.
    bounded = p.new((120, 0, -3160), radius=72, height=4000)
    ordered, chosen = p.check()
    assert bounded in ordered and chosen is None
    p.move(bounded, (119, 0, -3160))
    assert p.check()[1] == bounded
    p.move(bounded, (120, 0, -3161))
    ordered, chosen = p.check()
    assert bounded in ordered and chosen is None
    p.move(bounded, (500, 500, 0))
    p.move(extent, (3, 3, 0))
    for slot in range(4):
        for health, vehicle, present in ((0, 0, True), (-1, 0, True),
                                        (100, 1, True), (100, 0, False)):
            p.check(slot=slot, health=health, vehicle=vehicle, has_player=present)
        for result in (0, 1, 2, 3):
            for text in (0, 32, 65):
                for pressed, display in ((0, 0), (0x10, 0), (0x200, 0),
                                         (0x210, 0), (0x210, 1)):
                    p.check(slot=slot, result=result, text=text, pressed=pressed,
                            held=0x210, display=display)
        p.check(slot=slot, use_mask=0, pressed=0x210)
    # Fractional coordinates exercise the selected EE floating-point arithmetic.
    for _ in range(64):
        xyz = tuple(rng.choice((-32.25, -0.5, 0, 16.125, 255.5)) for _ in range(3))
        p.move(extent, tuple(v + rng.choice((-72, -48, 0, 48, 72)) for v in xyz))
        p.check(xyz, slot=rng.randrange(4), exclude=rng.choice((0, 0x400)))
    regular = p.cases
    # Truncation precedes usability and distance. 255 nonusable results can hide
    # the nearest interactable completely until its grid link moves to the front.
    c = PhysicalRig(elf, seed, fpu)
    nearest = c.new((1, 1, 0))
    for _ in range(260):
        c.new((20, 20, 0), flags=0)
    order, chosen = c.check()
    assert len(order) == 255 and nearest not in order and chosen is None
    c.move(nearest, (1, 1, 0))
    order, chosen = c.check()
    assert len(order) == 255 and order[0] == nearest and chosen == nearest
    print(f'PASS exit physical seed={seed} fpu={fpu} cases={regular+c.cases} '
          f'crowd_objects=261 control_flow_bypasses=0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default='local/SLUS_209.73')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--fpu', choices=('ps2', 'ps2g1', 'chop', 'nearest', 'all'), default='all')
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != D.EXPECTED_SHA256:
            parser.error('executable hash mismatch')
    models = ('ps2', 'ps2g1', 'chop', 'nearest') if args.fpu == 'all' else (args.fpu,)
    for fpu in models:
        try:
            run(args.elf, args.seed, fpu)
        except Exception as exc:
            # Emulator diagnostics can contain original instruction values.
            # Keep those private even when a new case fails unexpectedly.
            print(f'FAIL exit physical seed={args.seed} fpu={fpu} '
                  f'error_type={type(exc).__name__} failures=1')
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
