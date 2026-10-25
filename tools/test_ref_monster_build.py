#!/usr/bin/env python3
"""Synthetic tests of tools/ref_monster_build.py (no game file needed)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C            # noqa: E402
import ref_items as I           # noqa: E402
import ref_monster_build as B   # noqa: E402
import ref_natives as N         # noqa: E402

NAMES = [b'n%d' % k for k in range(B.ARENA_CLASS_COUNT)]
CENTRE = 0x01000000


def arena(wave=0, count=5, angle=0, step=0x1000):
    mem = N.Mem()
    mem.w16(B.G_WAVE, wave)
    mem.w16(B.G_RECIPE_COUNT, count)
    mem.w16(B.G_RING_ANGLE, angle)
    mem.w16(B.G_RING_STEP, step)
    mem.w32(B.G_RING_CENTRE, CENTRE)
    for k, v in enumerate((100.0, -50.0, 7.0)):
        mem.w32(CENTRE + 4 * k, I.f_bits(v))
    mem.w32(B.G_RAND_SEED, 1)
    return mem


def host(misses, obj=0x02000000, pool=0x03000000):
    h = B.Host()
    state = {'n': 0}

    def find(point, rang, radius, anyh):
        state['n'] += 1
        return (1, 2, 3), (0 if state['n'] <= misses else 1)
    h.answers = {'world_findFreeSpot': find, 'world_createObject': lambda *a: obj, 'pool_new': lambda *a: pool}
    return h


class Scale(unittest.TestCase):
    def test_cycle_counts_full_passes(self):
        self.assertEqual(B.arena_cycle(14, 5), 0)
        self.assertEqual(B.arena_cycle(15, 5), C.from_int(1))
        self.assertEqual(B.arena_cycle(45, 5), C.from_int(3))
        self.assertEqual(B.arena_cycle(-16, 5), C.from_int(-1))

    def test_table(self):
        self.assertEqual(B.arena_scale(0, 0), 0x3F800000)
        self.assertEqual(B.arena_scale(0, 5), 0x3F0666A9)
        self.assertEqual(B.arena_scale(C.from_int(1), 14), C.add(C.from_int(1), 0x3F410624))
        with self.assertRaises(B.Fault):
            B.arena_scale(0, 30)


class Ring(unittest.TestCase):
    def test_spawn_by_class(self):
        mem, h = arena(wave=15, angle=0x4000, step=0x2000), host(0)
        obj = B.arena_spawn_monster(mem, h, b'n6', 0, NAMES)
        self.assertEqual(obj, 0x02000000)
        names = [c[0] for c in h.log]
        self.assertEqual(names, ['world_findFreeSpot', 'world_createObject', 'Creature_scaleStats', 'pool_new',
                                 'creature_addSpell', 'virtual', 'virtual'])
        create = h.log[1][1]
        self.assertEqual(create[2], B.s16(0x4000 - 0x8000))
        self.assertEqual(create[3], B.G_ARENA_PROPS)
        self.assertEqual(h.log[2][1][1], C.add(C.from_int(1), 0x3F40C4CD))
        self.assertEqual(mem.u32(obj + 0x0C) & 2, 2)
        self.assertEqual(h.log[5][1], (34, obj, 5000))
        self.assertEqual(h.log[6][1], (27, obj, 0))
        self.assertEqual(mem.u16(B.G_RING_ANGLE), 0x6000)

    def test_spell_record_and_seed(self):
        mem, h = arena(), host(0)
        B.arena_spawn_monster(mem, h, b'n0', 0, NAMES)
        seed = (1 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.assertEqual(mem.u32(B.G_RAND_SEED), seed)
        spell = 0x03000000
        self.assertEqual(mem.u32(spell + 0x0C), 0x02000000)
        self.assertEqual(mem.u32(spell + 0x10), seed >> 16)
        self.assertEqual(mem.u32(spell + 0x14), B.VT_SPELL_ARENA)

    def test_no_spell_no_draw(self):
        mem, h = arena(), host(0, pool=0)
        B.arena_spawn_monster(mem, h, b'n0', 0, NAMES)
        self.assertEqual(mem.u32(B.G_RAND_SEED), 1)
        self.assertIn(('creature_addSpell', (0x02000000, 0)), h.log)

    def test_retries_then_gives_up_after_17(self):
        mem, h = arena(angle=0), host(99)
        self.assertIsNone(B.arena_spawn_monster(mem, h, b'n0', 0, NAMES))
        self.assertEqual(sum(1 for c in h.log if c[0] == 'world_findFreeSpot'), 17)
        self.assertEqual(mem.u16(B.G_RING_ANGLE), (17 * 4000) & 0xFFFF)

    def test_sixteen_misses_still_spawn(self):
        mem, h = arena(angle=0), host(16)
        self.assertIsNotNone(B.arena_spawn_monster(mem, h, b'n0', 0, NAMES))

    def test_existing_creature(self):
        mem, h = arena(angle=0x100), host(0)
        creature = 0x02100000
        mem.w8(creature + 0x231, 9)
        B.arena_spawn_monster(mem, h, None, creature, NAMES)
        self.assertEqual([mem.u32(creature + 0x10 + 4 * k) for k in range(3)], [1, 2, 3])
        self.assertEqual(mem.u8(creature + 0x231), 0)
        self.assertEqual(mem.u16(creature + 0x38), (0x100 - 0x8000) & 0xFFFF)
        self.assertIn(('Creature_clearStatus', (creature,)), h.log)

    def test_create_failure_faults(self):
        mem, h = arena(), host(0, obj=0)
        with self.assertRaises(B.Fault):
            B.arena_spawn_monster(mem, h, b'n0', 0, NAMES)


class Generator(unittest.TestCase):
    def gen(self, mem):
        g = 0x01100000
        for k, v in enumerate((5, 6, 7)):
            mem.w32(g + 0x10 + 4 * k, v)
        mem.w16(g + 0x38, 0x1000)
        mem.w32(g + 0x2C, 0xABC)
        return g

    def test_skeleton_rises(self):
        mem = N.Mem()
        h = B.Host({'world_createObject': lambda *a: 0x02000000})
        obj = B.script_generator_spawn(mem, h, self.gen(mem), 0x555, b'Skeleton', lambda o: b'8Skeleton')
        self.assertEqual(h.log[0], ('world_createObject', (b'Skeleton', (5, 6, 7), B.s16(0x1000 - 0x4000), 0xABC)))
        self.assertEqual(h.log[1], ('virtual', (27, obj, 0x17)))
        self.assertEqual(mem.u64(obj + 0xA8) & (1 << 24), 1 << 24)
        self.assertEqual(mem.u32(obj + 0x34), 0x555)

    def test_other_class_keeps_its_state(self):
        mem = N.Mem()
        h = B.Host({'world_createObject': lambda *a: 0x02000000})
        B.script_generator_spawn(mem, h, self.gen(mem), 0x555, b'Orc', lambda o: b'3Orc')
        self.assertEqual(len(h.log), 1)

    def test_nothing_created(self):
        mem = N.Mem()
        h = B.Host()
        self.assertEqual(B.script_generator_spawn(mem, h, self.gen(mem), 0x555, b'x', None), 0)


class Intern(unittest.TestCase):
    def test_reuse_and_append(self):
        mem = N.Mem()
        a = B.intern_class_name(mem, b'Orc')
        b = B.intern_class_name(mem, b'Skeleton')
        self.assertEqual(B.intern_class_name(mem, b'Orc'), a)
        self.assertEqual(b - a, 24)
        self.assertEqual(mem.u8(B.G_GEN_COUNT), 2)
        self.assertNotEqual(B.intern_class_name(mem, b'orc'), a)

    def test_factory_rows_any_case(self):
        self.assertEqual(B.factory_row(b'WATSKEL'), (0x478, 0x2A5AF4))
        self.assertEqual(B.factory_row(b'nosuch'), (None, None))


if __name__ == '__main__':
    unittest.main()
