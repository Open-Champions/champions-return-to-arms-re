#!/usr/bin/env python3
"""Bounded original portal-load effects with synthetic fixtures and count-only output.

No constructor, renderer or continuous death/reload claim. See the companion doc.
All expectations are authored here, without importing a reference implementation.
"""
import argparse
import hashlib
import itertools
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import unittest  # noqa: E402,F401 -- preload stdlib dis before adding tools/
import dis  # noqa: E402,F401
sys.path.insert(0, HERE)
from ee_emu import EE, MemoryFault  # noqa: E402

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
LIGHT_GRID, LIGHT_OVERFLOW = 0x5d34d8, 0x5db368
GRID_A, GRID_B, OFFGRID = 0x5db4f0, 0x5e95f0, 0x5f76f0
RUN, FREE = 0x5db3a8, 0x864ea8
VISITED = (0x14a4f0, 0x14a528, 0x148bc8, 0x17365c, 0x171de4, 0x170838, 0x170bc8,
           0x14f248, 0x1a1738, 0x1a1868, 0x14f120, 0x14f028,
           0x23ceb8, 0x23d680, 0x23d7ac, 0x243c70, 0x243e20,
           0x179550, 0x182b00, 0x182c98, 0x14e808)


def put(e, p, fmt, *values):
    e.mem.write(p, struct.pack('<' + fmt, *values))


def read(e, p, fmt):
    return struct.unpack('<' + fmt, e.mem.read(p, struct.calcsize('<' + fmt)))


def fixture(elf):
    e = EE(elf)
    e.record_writes = False
    e.seen = set()
    for addr in VISITED:
        e.hook(addr, lambda cpu, addr=addr: cpu.seen.add(addr))
    e.mem.write(LIGHT_GRID, bytes(90*90*4))
    e.mem.w32(LIGHT_OVERFLOW, 0)
    e.mem.write(RUN, bytes(0x5f76f4-RUN))
    pool = e.alloc(32*20)
    for i in range(32):
        e.mem.w32(pool+20*i, pool+20*(i+1) if i < 31 else 0)
    e.mem.w32(FREE, pool)
    return e


def call(e, addr, *args):
    return e.call(addr, *args, max_steps=200000)


def unstubbed(e):
    assert not e.patches and e.follow is None
    assert not any(c.stubbed for c in e.calls)
    assert not e.notes


def cell(pos, light=False, flags=0):
    dim, bias = (90, 11520) if light else (120, 15360)
    x, y = ((int(v)+bias)//256 for v in pos[:2])
    if not (0 <= x < dim and 0 <= y < dim):
        return LIGHT_OVERFLOW if light else OFFGRID
    return (LIGHT_GRID if light else GRID_B if flags & 0x800 else GRID_A) + 4*(dim*y+x)


def handles(e, head):
    """Validate both sides of each intrusive handle pair, return object identities."""
    out, prev, node = [], head, e.mem.u32(head)
    seen = set()
    while node:
        assert node not in seen and len(seen) < 32
        seen.add(node)
        assert e.mem.u32(node+4) == prev
        other, obj = e.mem.u32(node+8), e.mem.u32(node+12)
        assert e.mem.u32(other+8) == node
        assert e.mem.u32(other+12) == 0
        assert e.mem.u32(e.mem.u32(other+4)) == other
        out.append(obj)
        prev, node = node, e.mem.u32(node)
    return out


def light_list(e, head):
    out, prev, node = [], head, e.mem.u32(head)
    while node:
        assert node not in out and len(out) < 8
        assert e.mem.u32(node+4) == prev
        out.append(node)
        prev, node = node, e.mem.u32(node)
    return out


def free_count(e):
    seen, p = set(), e.mem.u32(FREE)
    while p:
        assert p not in seen and len(seen) < 33
        seen.add(p)
        p = e.mem.u32(p)
    return len(seen)


def asset(e, obj, mode):
    """Supply a cached standalone entry or a relocated, sorted synthetic archive."""
    e.mem.write(obj+0x90, b'syn_pack\0')
    # Replace only data in the emulator; never patch instructions or the input ELF.
    e.mem.write(0x547ee0, b'syn_clip\0')
    e.mem.write(0x7b9480, bytes(0x50))
    e.mem.write(0x7b9480, b'syn_decoy\0')
    e.mem.write(0x7b94a8, b'syn_pack\0')
    e.mem.w32(0x41bf7c, 2)
    resource = e.alloc(0x200)
    if mode == 'direct':
        e.mem.write(resource, b'syn_clip\0')
        put(e, 0x7b94b8, 'II', resource, 1)
        clip = resource+0x100
    else:
        put(e, 0x7b94b8, 'II', resource, 0)
        e.mem.w16(resource, 3)
        clip = e.alloc(0x40)
        for i, name in enumerate((b'syn_aaa', b'syn_clip', b'syn_zzz')):
            token = e.alloc(16)
            e.mem.write(token, (b'syn_other' if mode == 'missing' and i == 1 else name)+b'\0')
            put(e, resource+4+12*i, 'III', token, clip if i == 1 else 0, 0)
    e.mem.w32(clip+4, 73)
    return 0 if mode == 'missing' else clip


def gate_fixture(elf, pos, initially_lit, mode, full=False):
    e = fixture(elf)
    obj, buf, peer = e.alloc(0x180), e.alloc(8), e.alloc(0x180)
    e.mem.w32(obj+0x48, 0x50dbe8)
    e.mem.w32(obj+0xc, 0x100008)
    put(e, obj+0x10, 'fff', *pos)
    put(e, peer+0x10, 'fff', *pos)
    e.mem.w8(obj+0x4f, initially_lit)
    e.mem.w8(obj+0xdd, 1)  # supplied one-track constructor capacity
    clip = asset(e, obj, mode)
    if full:
        e.mem.w8(obj+0xdc, 1)
        put(e, obj+0xe0, 'IIfffffHH', clip, 0, 1., 0., 1., 0., 19., 9, 0)
        e.mem.w16(obj+0xde, 9)
    light, neighbor = obj+0x100, peer+0x100
    # Supplied radius/colour state is preserved by linking, not reconstructed here.
    put(e, light+8, '8H', 0, 140, 140, 300, 65520, 140, 140, 300)
    put(e, light+0x1c, '5f', 240., 0.125, 240., 0.125, 0.)
    put(e, light+0x30, 'fff', pos[0], pos[1], pos[2]+84.)
    put(e, neighbor+0x30, 'fff', pos[0], pos[1], pos[2]+84.)
    call(e, 0x148bc8, neighbor)
    if initially_lit:
        call(e, 0x148bc8, light)
    call(e, 0x14f120, peer)
    call(e, 0x14f120, obj)
    call(e, 0x14f248, obj)
    call(e, 0x14f248, peer)
    e.seen.clear()
    e.reset_log()
    return e, obj, buf, peer, clip


def gate_cases(elf, rng):
    count = 0
    positions = ((0., 0., 0.), (-11520., 0., 3.), (-11521., 0., -2.),
                 (11519., 11519., 5.), (11520., 0., 1.), (0., -11521., 0.),
                 (-256.75, 255.75, 8.))
    for active, lit, pos, mode in itertools.product((0, 1, 255), (0, 1), positions,
                                                   ('direct', 'archive', 'missing', 'full')):
        full = mode == 'full'
        e, obj, buf, peer, clip = gate_fixture(elf, pos, lit, 'direct' if full else mode, full)
        saved = rng.randrange(256)
        put(e, buf, 'BB', saved, active)
        before = bytearray(e.mem.read(obj, 0x164))
        free_before = free_count(e)
        next_handle = e.mem.u32(e.mem.u32(obj+4)+8)
        assert call(e, 0x27d998, obj, buf) == 2
        expected = bytearray(before)
        expected[0x4d:0x4f] = bytes((saved, active))
        # Unlink/reallocate swaps the roles of the same two handle nodes.
        struct.pack_into('<I', expected, 4, next_handle)
        if active:
            struct.pack_into('<II', expected, 0x100, peer+0x100, cell(pos, light=True))
        if active and clip and not full:
            expected[0xdc] = 1
            struct.pack_into('<H', expected, 0xde, 3)
            struct.pack_into('<IIfffffHH', expected, 0xe0, clip, 0, 1., 0., 1., 0., 0., 3, 0)
        assert e.mem.read(obj, 0x164) == expected
        assert handles(e, RUN) == [obj, peer]
        assert handles(e, cell(pos)) == [obj, peer]
        assert light_list(e, cell(pos, light=True)) == ([obj+0x100, peer+0x100] if active or lit else [peer+0x100])
        assert free_count(e) == free_before
        assert {0x14f248, 0x1a1738, 0x1a1868} <= e.seen
        assert (0x148bc8 in e.seen) == bool(active)
        assert (0x17365c in e.seen) == bool(active)
        assert (0x170838 in e.seen) == bool(active)
        assert (0x171de4 in e.seen) == (bool(active) and mode in ('archive', 'missing'))
        # Reloading again does not duplicate list entries or exceed clip capacity.
        struct.pack_into('<I', expected, 4, e.mem.u32(e.mem.u32(obj+4)+8))
        call(e, 0x27d998, obj, buf)
        assert e.mem.read(obj, 0x164) == expected
        assert handles(e, RUN) == [obj, peer]
        assert free_count(e) == free_before
        unstubbed(e)
        count += 1
    return count


def light_cases(elf):
    count = 0
    for pos in ((512., 0., 0.), (11520., 0., 0.), (-11521., 0., 0.),
                (0., -11521., 0.), (-11520., 11519., 0.), (0., 0., 0.)):
        e = fixture(elf)
        node, old_peer, new_peer = (e.alloc(0x40) for _ in range(3))
        old, new = cell((0., 0.), light=True), cell(pos, light=True)
        put(e, new_peer+0x30, 'fff', *pos)
        for light in (old_peer, node, new_peer):
            call(e, 0x148bc8, light)
        put(e, node+0x30, 'fff', *pos)
        call(e, 0x14a528, node)
        assert light_list(e, new) == ([node, new_peer, old_peer] if new == old else [node, new_peer])
        if new != old:
            assert light_list(e, old) == [old_peer]
        call(e, 0x14a4f0, node)
        assert read(e, node, 'II') == (0, 0)
        assert light_list(e, new) == ([new_peer, old_peer] if new == old else [new_peer])
        # Relink is a no-op for an unlinked node; load's link entry is different.
        call(e, 0x14a528, node)
        assert read(e, node, 'II') == (0, 0)
        unstubbed(e)
        count += 1
    return count


def grid_cases(elf):
    count = 0
    for flags, pos in itertools.product((0, 0x800),
            ((0., 0., 0.), (-15360., -15360., 0.), (-15361., 0., 0.),
             (15359., 15359., 0.), (15360., 0., 0.), (0., 15360., 0.))):
        e = fixture(elf)
        obj, peer = e.alloc(0x180), e.alloc(0x180)
        e.mem.w32(obj+0xc, flags)
        for o in (peer, obj):
            call(e, 0x14f120, o)
        old = cell((0., 0.))
        assert handles(e, old) == ([obj, peer] if not flags else [peer])
        free_before, handle = free_count(e), e.mem.u32(obj+8)
        put(e, obj+0x10, 'fff', *pos)
        call(e, 0x14f028, obj)
        target = cell(pos, flags=flags)
        assert handles(e, target) == ([obj, peer] if target == old else [obj])
        if target != old:
            assert handles(e, old) == [peer]
        assert e.mem.u32(obj+8) == handle and free_count(e) == free_before
        unstubbed(e)
        count += 1
    return count


def state_fixture(elf, table, state, looping, with_clip, door, inner_dirty=False):
    e = fixture(elf)
    obj, buf, model, clip = (e.alloc(n) for n in (0x4a0, 8, 0x100, 0x40))
    e.mem.w32(obj+0x48, table)
    e.mem.w32(obj+0xc, 0x100008)
    e.mem.w32(obj+0x90, model)
    e.mem.w8(obj+0x9d, 1)
    e.mem.w8(obj+0x9c, 1)
    e.mem.w16(obj+0x9e, 0x89)
    put(e, obj+0xa0, 'IIfffffHH', clip, 0, 1., 0., 1., 0., 19., 9, 0)
    e.mem.w32(obj+0x11c, int(door))
    e.mem.w32(obj+0x120, 2)
    e.mem.w32(clip+4, 73)
    for s in range(2):
        put(e, obj+0x128+8*s, 'II', clip if with_clip else 0, 0x18 | s | (2 if looping else 0))
    put(e, obj+0x178, 'IIQ', 0, 91, 0x1234)
    # Synthetic model hide-state table: start with no hidden meshes; state 0 hides
    # bit 0, state 1 hides bit 1 and unhides bit 0. Independent expected mask 0/2.
    put(e, model+8, 'QH', 0xffffffffffffffff, 2)
    e.mem.w8(model+0x21, 4)
    put(e, model+0x40, 'QQQQ', 1, 0, 2, 1)
    put(e, obj+0x448, 'IIf', 7 if inner_dirty else 0, 51 if inner_dirty else 0,
        0.5 if inner_dirty else 0.01)
    helper = e.alloc(0x184, fill=0x5a)
    e.mem.w32(helper+0xfc, 1)
    e.mem.w32(obj+0x198, helper)
    e.mem.w32(obj+0x1a8, helper)
    world, piece, element, surface = (e.alloc(0x100) for _ in range(4))
    e.mem.w32(0x44fdc8, world)
    e.mem.w32(world+0x54, piece)
    e.mem.w32(world+0x20, element)
    e.mem.w32(world+0x24, surface)
    put(e, piece, 'Ih', 0, 1)
    put(e, piece+8, 'iii', 0, 0, 16)
    put(e, piece+0x14, 'hhh', 32767, 0, 0)
    e.mem.w16(element+0x10, 0x12)
    e.mem.w32(surface+0x24, 0)
    call(e, 0x14f120, obj)
    # This run membership is supplied constructor state, not a loader side effect.
    call(e, 0x14f248, obj)
    e.mem.w32(buf, state)
    e.seen.clear()
    e.reset_log()
    return e, obj, buf, clip, element, surface


def state_cases(elf):
    count = 0
    for table, state, looping, with_clip, door, inner_dirty in itertools.product(
            (0x5136d8, 0x513630), (0, 1, 2), (False, True), (False, True),
            (False, True), (False, True)):
        e, obj, buf, clip, element, surface = state_fixture(elf, table, state, looping, with_clip, door, inner_dirty)
        before = bytearray(e.mem.read(obj, 0x498))
        free_before = free_count(e)
        helper = e.mem.u32(obj+0x1a8)
        helper_before = e.mem.read(helper, 0x184)
        assert call(e, 0x23ceb8, obj, buf) == 4
        want = bytearray(before)
        struct.pack_into('<I', want, 0x178, state)
        if state < 2:
            want[0x9c] = 0
            struct.pack_into('<IQ', want, 0x17c, 74 if with_clip else 0, 3 if state else 0)
            struct.pack_into('<Q', want, 0xc8, 2 if state else 0)
            struct.pack_into('<I', want, 0xc, 0x100008 | state)
            if with_clip:
                want[0x9c] = 1
                flag = 3 if looping else 6
                struct.pack_into('<H', want, 0x9e, 0x89 | flag)
                struct.pack_into('<IIfffffHH', want, 0xa0, clip, 0, 1., 0., 1., 0., 73., flag, 0)
            if table == 0x5136d8:
                struct.pack_into('<II', want, 0x448, state, 180 if state else 0)
                if state == 0:
                    struct.pack_into('<f', want, 0x450, 0.01)
        assert e.mem.read(obj, 0x498) == want
        assert e.mem.read(helper, 0x184) == helper_before
        assert handles(e, RUN) == [obj] and free_count(e) == free_before
        assert 0x14f248 not in e.seen
        assert (0x23d7ac in e.seen) == (state < 2)
        if door and state < 2:
            assert {0x182b00, 0x182c98} <= e.seen
            assert e.mem.u16(element+0x10) == (0x12 if state else 0x10)
            assert read(e, surface+0x28, 'iii') == (0, 0, -1008 if state else 16)
        else:
            assert e.mem.u16(element+0x10) == 0x12
            assert read(e, surface+0x28, 'iii') == (0, 0, 0)
        unstubbed(e)
        count += 1
    return count


def dispatch_cases(elf):
    """Original record loader + real virtual loads; only factory returns supplied state."""
    count = 0
    for kind, state in itertools.product(('syn_a', 'syn_b', 'syn_c'), (0, 1)):
        if kind == 'syn_a':
            e, obj, buf, peer, clip = gate_fixture(elf, (0., 0., 0.), 0, 'archive')
            payload = bytes((7, state))
        else:
            table = 0x5136d8 if kind == 'syn_b' else 0x513630
            e, obj, buf, clip, element, surface = state_fixture(elf, table, state, False, True, True)
            payload = struct.pack('<I', state)
        blob = e.alloc(0x80)
        put(e, blob, 'HHI', 1, 1, 40)
        put(e, blob+8, 'IhhfffI', 0, 32, 123, 0., 0., 0., 0)
        e.mem.write(blob+32, payload)
        e.mem.write(blob+40, kind.encode()+b'\0')
        factory = e.alloc(4)
        calls = []
        def supplied(cpu):
            assert cpu.mem.cstr(cpu.r[4]) == kind
            assert read(cpu, cpu.r[5], 'fff') == (0., 0., 0.)
            assert cpu.r[6] == 123 and cpu.mem.u32(cpu.r[7]) == 0
            calls.append(obj)
            return obj
        e.stub(factory, function=supplied)
        e.mem.w32(0x5f76f4, factory)
        assert call(e, 0x14e808, blob, 0) == 40
        assert calls == [obj] and e.mem.u32(obj+0x34) == blob+40
        assert e.mem.u16(blob+2) == 3
        assert handles(e, cell((0., 0.)))[0] == obj
        assert e.mem.u32(0x5db4e0) == 0  # supplied empty delete list
        if kind == 'syn_a':
            assert e.mem.read(obj+0x4d, 2) == payload
            assert e.mem.u8(obj+0xdc) == state
            assert light_list(e, cell((0., 0.), light=True)) == ([obj+0x100, peer+0x100] if state else [peer+0x100])
            assert handles(e, RUN) == [obj, peer]
        else:
            assert e.mem.u32(obj+0x178) == state
            assert e.mem.u32(obj+0x17c) == 74
            assert read(e, obj+0xb8, 'f') == (73.,)
            assert e.mem.u16(element+0x10) == (0x12 if state else 0x10)
            if kind == 'syn_b':
                assert read(e, obj+0x448, 'II') == (state, 180 if state else 0)
        assert len([c for c in e.calls if c.stubbed]) == 1
        assert not e.patches and not e.notes
        count += 1
    return count


class UnsupportedResource(Exception):
    pass


def refusal_cases(elf):
    e, obj, buf, peer, clip = gate_fixture(elf, (0., 0., 0.), 0, 'direct')
    e.mem.w32(0x41bf7c, 0)
    put(e, buf, 'BB', 7, 1)
    run_before = e.mem.read(obj+4, 4)
    def refuse(cpu):
        assert cpu.r[4] == obj+0x90
        raise UnsupportedResource()
    # No fabricated asset answer: stop at the first unmodelled resource-load call.
    e.hook(0x173558, refuse)
    try:
        call(e, 0x27d998, obj, buf)
    except UnsupportedResource:
        assert e.mem.read(obj+0x4d, 2) == b'\x07\x01'
        assert light_list(e, cell((0., 0.), light=True)) == [obj+0x100, peer+0x100]
        assert e.mem.read(obj+4, 4) == run_before and 0x14f248 not in e.seen
    else:
        raise AssertionError('unmodelled resource load was not refused')
    e = fixture(elf)
    obj = e.alloc(0x180)
    e.mem.w32(FREE, 0)
    try:
        call(e, 0x14f248, obj)
    except MemoryFault as exc:
        assert exc.pc == 0x1a1780 and exc.addr == 0
    else:
        raise AssertionError('empty handle pool did not fail closed')
    return 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf')
    p.add_argument('--seed', type=int, default=20973)
    args = p.parse_args()
    if not __debug__:
        raise SystemExit('assertions must be enabled')
    with open(args.elf, 'rb') as f:
        if hashlib.sha256(f.read()).hexdigest() != SHA:
            raise SystemExit('wrong executable pin')
    counts = (gate_cases(args.elf, random.Random(args.seed)), grid_cases(args.elf),
              light_cases(args.elf), state_cases(args.elf), dispatch_cases(args.elf), refusal_cases(args.elf))
    print('PASS cases=%d loads=%d grids=%d lights=%d variants=%d dispatch=%d refusals=%d' %
          (sum(counts), *counts))


if __name__ == '__main__':
    main()
