#!/usr/bin/env python3
"""Bounded original load execution on synthetic linked objects; counts only.

No constructor, resource loader, scheduler, destructor, or renderer is claimed.
All reached callees execute original instructions; there are no service stubs.
"""
import argparse
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import unittest  # noqa: E402,F401 -- preload stdlib dis before restoring tools/
import dis  # noqa: E402,F401
sys.path.insert(0, HERE)
from ee_emu import EE, MemoryFault  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
LOAD, VARIANT, MODEL, MASK = 0x116920, 0x11A668, 0x3C2738, 0x179550
DEATH, STOP, CLEAR = 0x10BEB8, 0x14F290, 0x1A1698
LINK, UNLINK = 0x1A1738, 0x1A1868
RESET, PUSH, END = 0x1707B0, 0x170838, 0x170BC8
TYPE_A, TYPE_B, TYPE_EQ = 0x3C2608, 0x3C4658, 0x3B1250
FREE, ACTIVE, DELETE, ALWAYS = 0x864EA8, 0x5DB3A8, 0x5DB4E0, 0x5DB4E8
GRID, OFFGRID, STRINGS = 0x5DB4F0, 0x5F76F0, 0x5F8704
EXCLUDE = 0x4039B8
CELL = GRID + 4 * (60 * 120 + 60)
FLAG_MASKS = (0x1000000, 0x100000000, 0x400000, 0x800000, 0x2000000000000)
M64 = (1 << 64) - 1


def require(ok, label):
    if not ok:
        raise AssertionError(label)


def pack(mem, addr, fmt, *values):
    mem.write(addr, struct.pack('<' + fmt, *values))


def write_expected(buf, off, fmt, *values):
    struct.pack_into('<' + fmt, buf, off, *values)


class Fixture:
    def __init__(self, elf, rng, *, flags=0x20, timer=9, model='variants',
                 kind='different', capacity=1, cflags=0x8002000109C00010,
                 target=True, running=True, attached=True):
        self.e = e = EE(elf)
        self.m = m = e.mem
        e.record_writes = False
        self.flags, self.timer, self.model = flags, timer, model
        self.kind, self.capacity, self.cflags = kind, capacity, cflags
        self.running, self.target = running, target
        self.objects = [e.alloc(0x400) for _ in range(4)]
        self.left, self.obj, self.right, self.other = self.objects
        o = self.obj
        self.vt, self.defs, self.model_ptr = e.alloc(0x100), e.alloc(0x40), e.alloc(0x80)
        self.clip, self.old_clip = e.alloc(0x40), e.alloc(0x40)
        self.pose, self.slot = e.alloc(0x620), e.alloc(0x40)
        self.buf, self.text = e.alloc(0x40), e.alloc(0x100)
        self.pool = e.alloc(64 * 0x14)
        self.pool_nodes = {self.pool + i * 0x14 for i in range(64)}
        for i in range(64):
            m.w32(self.pool + i * 0x14, self.pool + (i + 1) * 0x14 if i < 63 else 0)
        m.w32(FREE, self.pool)
        # Empty synthetic world heads and name registry; no world-init scheduler.
        m.write(ACTIVE, bytes(OFFGRID + 8 - ACTIVE))
        m.write(0x5F76F8, bytes(0x1004))
        m.w32(0x4F7120, 0)
        m.w32(EXCLUDE, 0)
        m.write(self.text, b'synthetic_model\0')
        m.write(self.text + 32, b'synthetic_clip\0')
        m.write(self.text + 64, b'synthetic_absent\0')
        m.write(self.text + 96, b'synthetic_kind_a\0')
        m.write(self.text + 128, b'synthetic_kind_b\0')
        # Cached type descriptors are supplied; getters and equality still execute.
        m.w32(0x908130, self.text + (128 if kind == 'equal_name' else 96))
        m.w32(0x9083F0, self.text + 128)
        for off, fn in ((0, TYPE_B if kind == 'same' else TYPE_A),
                        (0x80, MODEL), (0xE0, DEATH), (0xE8, VARIANT)):
            m.w16(self.vt + off, 0)
            m.w32(self.vt + off + 4, fn)
        m.w32(o + 0x48, self.vt)
        m.w32(o + 0x24, self.defs)
        m.w32(self.defs + 8, self.text)
        m.w32(self.defs + 12, 0 if model == 'null' else self.model_ptr)
        m.w32(self.defs + 16, self.text + 32)
        m.w32(self.defs + 20, self.clip)
        pack(m, self.model_ptr + 8, 'Q', 0x12)
        m.w16(self.model_ptr + 0x10, 2 if model == 'variants' else 0)
        m.w8(self.model_ptr + 0x21, 4)
        pack(m, self.model_ptr + 0x40, 'QQQQ', 2, 4, 4, 8)
        self.length = rng.choice((17, 73, 127))
        m.w32(self.clip + 4, self.length)
        m.w32(self.old_clip + 4, 19)
        self.max_hp = rng.choice((64., 128., 160.))
        pack(m, o + 0x228, 'ff', 19., self.max_hp)
        pack(m, o + 0x220, 'Q', 0x8877665544332211)
        pack(m, o + 0xA8, 'Q', cflags)
        m.w8(o + 0x231, 0xFF)
        m.w16(o + 0x232, 7)
        pack(m, o + 0x310, 'BBhHH', 5, 0x9A, timer, 321, 654)
        # Nonzero motion/state witnesses must survive the load byte-for-byte.
        pack(m, o + 0xBC, 'fff', 3., -4., 5.)
        pack(m, o + 0xF8, 'fff', 6., 7., 8.)
        pack(m, o + 0x308, 'ff', -2., 4.)
        self.state = s = o + 0x114
        pack(m, s, 'IBBH', self.pose if attached else 0, int(capacity > 0), capacity, 0x20)
        pack(m, s + 8, 'IIfffffHH', self.old_clip, self.slot if attached else 0,
             0.5, 0.25, 0.75, -0.5, 3., 0x800, 7)
        m.w32(self.pose + 0x610, s if attached else 0)
        m.w32(self.slot + 0x14, s + 8 if attached else 0)
        self.attached = attached
        self.names = []
        for i, obj in enumerate(self.objects[:3]):
            m.w32(obj + 0xC, flags if obj == o else 0x20)
            pack(m, obj + 0x10, 'fff', 0., 0., 0.)
            pack(m, obj + 0x1C, 'ff', 2., 4.)
            m.w8(obj + 0x28, 9)
            name = e.alloc(32)
            m.write(name, ('synthetic_object_%d' % i).encode() + b'\0')
            self.names.append(name)
            # +0x34 remains null: no class-specific audio name is supplied.
            self.call(0x14F120, obj)
            if obj != o or running:
                self.call(0x14F248, obj)
            self.call(0x14BCE0, name, obj)
            if obj != o or target:
                self.call(LINK, obj + 0x234, self.other, self.other)
        if flags & 2:
            self.call(0x14EDD8, o)
        self.grid_objects = [self.right, self.left] if flags & 2 else [self.right, o, self.left]
        self.run_objects = [self.right, o, self.left] if running else [self.right, self.left]
        self.check_list(CELL, self.grid_objects)
        self.check_list(ACTIVE, self.run_objects)
        self.check_graph()
        self.before = m.read(o, 0x400)
        self.peer_before = {p: m.read(p, 0x400) for p in self.objects if p != o}
        self.run_back = m.u32(o + 4)
        self.run_front = m.u32(self.run_back + 8) if self.run_back else 0
        self.registry_before = m.read(0x5F76F8, 0x1004)
        self.pose_before = m.read(self.pose, 0x620)
        self.slot_before = m.read(self.slot, 0x40)

    def call(self, addr, *args):
        return self.e.call(addr, *args, max_steps=30000)

    def chain(self, head):
        nodes, p, prev = [], self.m.u32(head), head
        while p:
            require(p in self.pool_nodes and p not in nodes, 'invalid/cyclic list')
            require(self.m.u32(p + 4) == prev, 'list back pointer')
            partner = self.m.u32(p + 8)
            require(partner in self.pool_nodes and self.m.u32(partner + 8) == p, 'partner')
            nodes.append(p)
            prev, p = p, self.m.u32(p)
        return nodes

    def check_list(self, head, expected):
        require([self.m.u32(n + 12) for n in self.chain(head)] == expected, 'list contents')

    def check_graph(self):
        heads = [CELL, ACTIVE, DELETE, ALWAYS, OFFGRID]
        heads += [o + off for o in self.objects for off in (0, 4, 8, 0x234)]
        used = []
        for head in heads:
            used.extend(self.chain(head))
        require(len(used) == len(set(used)), 'node shared across list heads')
        free, p = [], self.m.u32(FREE)
        while p:
            require(p in self.pool_nodes and p not in free, 'invalid/cyclic free list')
            free.append(p)
            p = self.m.u32(p)
        require(not set(used).intersection(free), 'live node on free list')
        require(set(used + free) == self.pool_nodes, 'lost node')
        return len(free)

    def check_queries(self, dead):
        for obj, name in zip(self.objects, self.names):
            require(self.call(0x14F498, name) == obj, 'name registry result')
        lo, hi, out = self.e.alloc(16), self.e.alloc(16), self.e.alloc(32)
        pack(self.m, lo, 'fff', -1., -1., -1.)
        pack(self.m, hi, 'fff', 1., 1., 1.)
        for mask in (0, 8):
            self.m.w32(EXCLUDE, mask)
            self.m.write(out, b'\xA5' * 32)
            end = self.call(0x14A928, lo, hi, out, 6)
            want = [o for o in self.grid_objects if not (o == self.obj and dead and mask)]
            expected = struct.pack('<%dI' % (len(want) + 1), *want, 0)
            require(self.m.read(out, len(expected)) == expected, 'spatial query result')
            require(end == out + 4 * len(want), 'spatial query end')
            require(self.m.read(out + len(expected), 32 - len(expected)) == b'\xA5' * (32 - len(expected)), 'query sentinel')
        self.check_graph()


def case(elf, rng, *, ratio=-0.25, animation='match', bits=127, variant=3,
         optional=5, **state):
    f = Fixture(elf, rng, **state)
    e, m, o = f.e, f.m, f.obj
    dead = ratio <= 0
    matched = dead and animation in ('match', 'null_clip')
    pushed = matched and animation == 'match' and f.capacity > 0
    eligible = bool(bits & 64) and f.timer != -1 and bool(f.flags & 0x20) and not f.flags & 0x40
    deleting = matched and bool(f.flags & 2)
    if animation == 'null_clip':
        m.w32(f.defs + 20, 0)
    m.w32(STRINGS, f.text)
    payload = struct.pack('<If', variant, ratio)
    if dead:
        payload += struct.pack('<i', -1 if animation == 'negative' else 64 if animation == 'absent' else 32)
    payload += struct.pack('<I', bits)
    if bits & 64:
        payload += struct.pack('<i', optional)
    m.write(f.buf, payload + b'\xA5' * (64 - len(payload)))
    want = bytearray(f.before)
    write_expected(want, 0xE8, 'I', variant)
    write_expected(want, 0x228, 'f', ratio * f.max_hp)
    if f.model != 'null':
        masks = (0xFFFFFFFFFFFFFFED, 0xFFFFFFFFFFFFFFEB, 0xFFFFFFFFFFFFFFE5, 0xFFFFFFFFFFFFFFE7)
        write_expected(want, 0x220, 'Q', masks[variant] if f.model == 'variants' else masks[0])
    if dead:
        write_expected(want, 4, 'I', 0)
        write_expected(want, 0xC, 'I', f.flags | 0x2009 | (0x4000 if deleting else 0))
        write_expected(want, 0x232, 'H', 20)
        if f.kind != 'different':
            write_expected(want, 0x28, 'B', 70)
    if deleting:
        require(f.running, 'deletion fixture requires known run-node reuse')
        write_expected(want, 0, 'I', f.run_front)
    if matched:
        write_expected(want, 0x114, 'IBBH', 0, int(pushed), f.capacity, 0xA4 if pushed else 0xA0)
        if pushed:
            write_expected(want, 0x11C, 'IIfffffHH', f.clip, 0, 1., 0., 1., 0., float(f.length), 4, 0)
    new_flags = f.cflags & (M64 ^ 0x8C00000) if matched else f.cflags
    new_flags |= sum(flag for i, flag in enumerate(FLAG_MASKS) if bits & (1 << i))
    write_expected(want, 0xA8, 'Q', new_flags)
    write_expected(want, 0x231, 'B', 0xFF if bits & 32 else 0xFE)
    if eligible:
        write_expected(want, 0x310, 'B', 0)
        write_expected(want, 0x312, 'H', optional & 0xFFFF)
        write_expected(want, 0x234, 'I', 0)
    e.reset_log()
    e.trace = []
    require(f.call(LOAD, o, f.buf) == len(payload), 'consumed length')
    pcs = set(e.trace)
    require(not e.hooks and e.follow is None and not e.patches and not m.auto_mapped, 'execution boundary changed')
    require(not any(c.stubbed for c in e.calls), 'unexpected stub')
    require(m.read(o, 0x400) == want, 'whole object differs')
    require(all(m.read(p, 0x400) == before for p, before in f.peer_before.items()), 'peer object changed')
    require(m.read(f.buf, 64) == payload + b'\xA5' * (64 - len(payload)), 'input changed')
    pose_want, slot_want = bytearray(f.pose_before), bytearray(f.slot_before)
    if matched and f.attached:
        write_expected(pose_want, 0x610, 'I', 0)
    if pushed and f.attached:
        write_expected(slot_want, 0x14, 'I', 0)
    require(m.read(f.pose, 0x620) == pose_want, 'pose owner')
    require(m.read(f.slot, 0x40) == slot_want, 'decoder owner')
    require(m.read(0x5F76F8, 0x1004) == f.registry_before, 'name registry changed')
    f.check_list(CELL, f.grid_objects)
    f.check_list(OFFGRID, [o] if f.flags & 2 else [])
    f.check_list(ALWAYS, [o] if f.flags & 2 else [])
    f.check_list(ACTIVE, [f.right, f.left] if dead else f.run_objects)
    f.check_list(DELETE, [o] if deleting else [])
    f.check_list(o + 0x234, [f.other] if f.target and not eligible else [])
    f.check_list(f.left + 0x234, [f.other])
    f.check_list(f.right + 0x234, [f.other])
    # Each world/target association occupies a front and a back node.
    associations = 3 + (2 + int(f.running and not dead)) + 2 + int(f.target and not eligible)
    associations += int(bool(f.flags & 2)) + int(deleting)
    require(f.check_graph() == 64 - 2 * associations, 'free pool count')
    for addr, reached in ((VARIANT, True), (MODEL, True), (MASK, f.model != 'null'),
                          (STOP, dead), (0x14F688, dead), (TYPE_EQ, dead),
                          (RESET, matched), (PUSH, matched), (END, matched),
                          (DEATH, matched), (0x14F4C0, matched), (0x1192F8, matched),
                          (0x10DBE0, matched), (CLEAR, eligible), (0x14F200, deleting)):
        require((addr in pcs) == reached, 'original branch coverage')
    require(not pcs.intersection((0x109D68, 0x17365C, 0x1ED694, 0x211338,
                                  0x3056CC, 0x16E468, 0x113C48)), 'unclaimed service reached')
    f.check_queries(dead)
    return pcs


def fail_closed(elf, rng):
    f = Fixture(elf, rng)
    m, o = f.m, f.obj
    m.w32(f.defs + 12, 0x0BAD0000)
    pack(m, f.buf, 'IfiI', 3, -0.25, -1, 127)
    before_pool = m.read(f.pool, 64 * 0x14)
    before_heads = [m.u32(o + i) for i in (0, 4, 8, 0x234)]
    f.e.reset_log()
    f.e.trace = []
    try:
        f.call(LOAD, o, f.buf)
    except MemoryFault as exc:
        require((exc.pc, exc.addr, exc.size) == (MASK, 0x0BAD0010, 2), 'resource refusal moved')
    else:
        raise AssertionError('unmapped resource unexpectedly succeeded')
    require(STOP not in f.e.trace and DEATH not in f.e.trace, 'refusal crossed boundary')
    require(m.read(f.pool, 64 * 0x14) == before_pool, 'refusal changed links')
    require([m.u32(o + i) for i in (0, 4, 8, 0x234)] == before_heads, 'refusal changed heads')
    require(m.u32(o + 0xE8) == 3, 'pre-refusal variant write missing')
    require(m.read(o + 0x228, 4) == struct.pack('<f', -0.25 * f.max_hp), 'pre-refusal HP write missing')
    require(not f.e.hooks and not f.e.patches and f.e.follow is None, 'probe was stubbed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as src:
        require(hashlib.sha256(src.read()).hexdigest() == SHA256, 'wrong executable pin')
    rng = random.Random(args.seed)
    count, pcs = 0, set()

    def run(**kwargs):
        nonlocal count
        pcs.update(case(args.elf, rng, **kwargs))
        count += 1

    for ratio in (0.5, 0., -0.25):
        for animation in ('match', 'negative', 'absent', 'null_clip'):
            for flags, timer in ((0x20, 9), (0x20, -1), (0, 9), (0x60, 9)):
                for kind in ('different', 'same'):
                    run(ratio=ratio, animation=animation, flags=flags, timer=timer, kind=kind)
    for ratio in (0.5, -0.25):
        for model in ('null', 'basic', 'variants'):
            for variant in range(4):
                run(ratio=ratio, model=model, variant=variant)
    for ratio in (0.5, -0.25):
        for bits in (0, 1, 2, 4, 8, 16, 32, 64, 127):
            for cflags in (0, 0x8002000109C00010):
                run(ratio=ratio, bits=bits, cflags=cflags)
    for animation in ('match', 'negative', 'absent', 'null_clip'):
        for ratio in (0.5, -0.25):
            run(ratio=ratio, animation=animation, flags=0x22)
            run(ratio=ratio, animation=animation, capacity=0)
    for optional in (-1, 0, 0x10005):
        for ratio in (0.5, -0.25):
            run(ratio=ratio, optional=optional, kind='equal_name')
    for ratio in (0.5, -0.25):
        run(ratio=ratio, running=False, target=False, attached=False)
    fail_closed(args.elf, rng)
    require({LOAD, VARIANT, MASK, STOP, DEATH, CLEAR, LINK, UNLINK,
             RESET, PUSH, END, TYPE_A, TYPE_B, TYPE_EQ}.issubset(pcs), 'aggregate coverage')
    print('PASS cases=%d refusals=1 stubs=0' % count)


if __name__ == '__main__':
    main()
