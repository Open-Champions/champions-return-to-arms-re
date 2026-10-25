#!/usr/bin/env python3
"""Synthetic tests of tools/ref_arrow_hit.py, tools/ref_staticfire.py and tools/ref_minion.py (no
game file needed).  Whether the models match the game is the business of difftest_arrow_hit.py,
difftest_arrow_run.py, difftest_staticfire.py and difftest_minion.py (they need the executable)."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                             # noqa: E402
import ref_creature as RC                        # noqa: E402
import ref_arrow_hit as AH                       # noqa: E402
import ref_staticfire as SF                      # noqa: E402
import ref_minion as MN                          # noqa: E402

M32 = 0xFFFFFFFF


def f(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def g(raw):
    return struct.unpack('<f', struct.pack('<I', raw))[0]


class Answers:
    def __init__(self, table=None):
        self.table = table or {}

    def get(self, name):
        return self.table.get(name, lambda *a: 0)


class Host(AH.HitMixin, SF.FireMixin, RC.Model):
    """A model on made-up memory with the pieces the mixins expect."""

    def __init__(self, table=None, same=None):
        RC.Model.__init__(self, RC.Memory(), Answers(table))
        self.same = same or (lambda a, b: a == b)

    def game_object_ctor_value(self, obj, pos):
        self.draws += 1
        self.calls.append(('GameObject_ctor', (obj, tuple(pos))))
        self.wvec(obj + 0x10, pos)
        self.w32(obj + 0xC, 0)

    def type_of(self, obj):
        return self.call('Creature.v0')

    def same_type(self, a, b):
        return self.same(a, b)


class Timer(unittest.TestCase):
    def test_which_selects_the_timer(self):
        for which, off in enumerate((0x340, 0x344, 0x348, 0x34C, 0x350)):
            h = Host()
            h.Creature_setEffectTimer(0x1000, which, 0, f(2.5))
            self.assertEqual(h.u32(0x1000 + off), f(2.5))
            self.assertEqual(sorted(a for a, _s, _v in h.writes), [0x1000 + off])

    def test_values_from_five_store_nothing(self):
        for which in (5, 6, 0x80000000, 0xFFFFFFFF):
            h = Host()
            h.Creature_setEffectTimer(0x1000, which, 0x2000, f(1.0))
            self.assertEqual(h.writes, [])

    def test_source_list_is_relinked_only_for_a_positive_time(self):
        h = Host()
        h.Creature_setEffectTimer(0x1000, 1, 0x2000, f(1.0))
        self.assertEqual(h.calls, [('handle_clear', (0x1360,)), ('handle_link', (0x1360, 0x2000, 0x2000))])
        h = Host()
        h.Creature_setEffectTimer(0x1000, 1, 0, f(1.0))
        self.assertEqual(h.calls, [('handle_clear', (0x1360,))])
        for seconds in (0, f(-1.0), f(-0.0)):
            h = Host()
            h.Creature_setEffectTimer(0x1000, 1, 0x2000, seconds)
            self.assertEqual(h.calls, [])
            self.assertEqual(h.u32(0x1344), seconds)


class Light(unittest.TestCase):
    def build(self, life, follow=0, frame=1000):
        h = Host()
        h.w32(0x44FDCC, frame)
        # the explosion's values: colour 255, 10, 10, 0 fading to 0; radius 120 to 60; 0.5; life
        fl = [f(255.0), f(10.0), f(10.0), 0, 0, 0, 0, 0, f(120.0), f(60.0), f(0.5), f(life)]
        h.LightEffect_ctor(0x5000, (f(1.0), f(2.0), f(3.0)), follow, 7, *fl)
        return h

    def test_explosion_light_lasts_fifteen_frames(self):
        h = self.build(0.25)
        self.assertEqual(h.u32(0x5000 + 0xB4), 1015)
        self.assertEqual(h.u32(0x5000 + 0x48), 0x50E198)
        self.assertEqual(h.u32(0x5000 + 0xC) & 3, 3)
        self.assertEqual(h.u32(0x5000 + 0xB8), 7)
        self.assertEqual(h.draws, 1)

    def test_life_not_above_zero_is_one_frame(self):
        for life in (0.0, -2.0, 0.01):
            self.assertEqual(self.build(life).u32(0x5000 + 0xB4), 1001)

    def test_steps_and_colours(self):
        h = self.build(1.0)
        # n = 60: radius step (60 - 120) / 60 = -1; colour steps -255 / 60 ...
        self.assertAlmostEqual(g(h.u32(0x5000 + 0xB0)), -1.0, places=5)
        self.assertAlmostEqual(g(h.u32(0x5000 + 0x9C)), -255.0 / 60, places=4)
        self.assertEqual([h.u16(0x5000 + 0x4C + 0xA + 2 * k) for k in range(4)], [255, 10, 10, 0])
        self.assertEqual([h.u16(0x5000 + 0x4C + 0x12 + 2 * k) for k in range(4)], [255, 10, 10, 0])
        self.assertAlmostEqual(g(h.u32(0x5000 + 0x4C + 0x28)), 1 / 14400.0, places=9)

    def test_calls_in_order_and_follow(self):
        h = self.build(0.25)
        self.assertEqual([c[0] for c in h.calls], ['GameObject_ctor', 'light_link', 'obj_runEveryFrame'])
        h = self.build(0.25, follow=0x6000)
        self.assertEqual([c[0] for c in h.calls], ['GameObject_ctor', 'light_link', 'handle_link', 'obj_runEveryFrame'])
        self.assertEqual(h.calls[2][1], (0x5088, 0x6000, 0x6000))


class StaticFire(unittest.TestCase):
    def ctor(self, others, flag=0, life=240, same=None):
        h = Host({'world_collectObjectsInBox': lambda lo, hi, n: list(others),
                  'StaticFire_typeinfo': lambda: 77, 'Creature.v0': lambda: 77}, same=same)
        h.w32(0x700 + 0, f(10.0))
        h.w32(0x700 + 4, f(20.0))
        h.w32(0x700 + 8, f(30.0))
        h.staticfire_ctor(0x1000, 0x700, life, 0x9000, flag, f(240.0), f(0.5))
        return h

    def test_debris_fire_fields(self):
        h = self.ctor([])
        self.assertEqual(h.u32(0x1048), 0x50DA38)
        self.assertEqual(h.u32(0x1000 + 0x50), f(240.0))
        self.assertEqual(h.u32(0x1000 + 0x68), f(12500.0))
        self.assertEqual(h.u32(0x1000 + 0x7C), 240)
        self.assertEqual(h.u32(0x1000 + 0x4A8), 0x9000)
        self.assertEqual(h.u32(0x1000 + 0x4A4), 0x1000 + 0xBC)
        self.assertEqual(h.s16(0x1000 + 0x76), 100)
        self.assertEqual(g(h.u32(0x1000 + 0xB8)), 66.0)
        self.assertEqual(h.u32(0x1000 + 0xC) & 0x40001, 0x40001)

    def test_draws_one_shared_two_own(self):
        h = self.ctor([])
        self.assertEqual(h.draws, 1)                    # the GameObject's; its seed word +0x44 then moved twice
        seed = 0
        for _ in range(2):
            seed = (seed * 0x19660D + 0x3C6EF35F) & M32
        self.assertEqual(h.u32(0x1000 + 0x44), seed)

    def test_four_neighbours_halve_the_life(self):
        self.assertEqual(self.ctor([1, 2, 3]).u32(0x1000 + 0x7C), 240)
        self.assertEqual(self.ctor([1, 2, 3, 4]).u32(0x1000 + 0x7C), 120)
        self.assertEqual(self.ctor([1, 2, 3, 4], life=0xFFFFFFFB).u32(0x1000 + 0x7C), (-5 + 1) >> 1 & M32)
        self.assertEqual(self.ctor([0x1000, 2, 3, 4]).u32(0x1000 + 0x7C), 240)        # the fire itself is skipped

    def test_flag_skips_the_type_test(self):
        h = self.ctor([1, 2], flag=1)
        self.assertNotIn('StaticFire_typeinfo', [c[0] for c in h.calls])
        self.assertEqual([c for c in h.calls if c[0] == 'light_unlink'], [('light_unlink', (0x1080,))])
        h = self.ctor([1, 2], flag=0)
        self.assertEqual([c[1] for c in h.calls if c[0] == 'light_unlink'], [(0x1 + 0x80,), (0x2 + 0x80,)])

    def test_push_leaves_the_ring_when_index_meets_stop(self):
        h = Host()
        h.w16(0x1000 + 0x76, 8)
        h.staticfire_push(0x1000, 0)
        self.assertEqual(h.s16(0x1000 + 0x72), 3)                   # cos 0 = 1 -> 3.7333 truncated
        self.assertEqual(h.s16(0x1000 + 0x74), 0)

    def test_push_walks_the_ring_and_wraps(self):
        h = Host()
        h.w32(0x1000 + 0x4A4, 0x3000)
        h.w16(0x1000 + 0x76, 4)                                     # ring of 4
        h.w16(0x1000 + 0x7A, 2)
        h.w16(0x1000 + 0x78, 1)                                     # 2, 3, 0 are visited
        h.staticfire_push(0x1000, 0)
        touched = {a for a, _s, _v in h.writes if a >= 0x3000}
        self.assertTrue(touched <= {0x3000 + 10 * k + o for k in range(4) for o in (6, 8)})
        self.assertTrue(all((a - 0x3000) // 10 in (0, 2, 3) for a in touched))


class Minion(unittest.TestCase):
    def build(self, held, state=0x20, run=0):
        table = {'Creature_run': lambda *a: run, 'model_getAttachPoint': lambda *a: ((f(1.0), f(2.0), f(3.0)), (0, 0, 0))}
        m = MN.Model(RC.Memory(), Answers(table))
        m.w32(0x1000 + 0x24, 0x2000)
        m.w32(0x2000 + 0xC, 0x3000)
        m.w32(0x1000 + 0x48, 0x4000)
        m.w16(0x4000 + 0xB8, 0x10)
        m.w32(0x1000 + MN.OFFSET_HELD, 0x5000 if held else 0)
        m.w32(0x5000 + 0xC, 0x6000)
        m.w16(0x1000 + 0x38, 0xBEEF)
        m.w16(0x1000 + MN.OFFSET_STATE, state)
        m.w32(0x1000 + 0x10, f(5.0))
        return m

    def test_held_soul_gets_the_point_and_the_facing(self):
        m = self.build(True)
        self.assertEqual(m.minion_run_prefix(0x1000), 'done')
        self.assertEqual([m.u32(0x6010 + 4 * k) for k in range(3)], [f(1.0), f(2.0), f(3.0)])
        self.assertEqual(m.u16(0x6038), 0xBEEF)
        names = [c[0] for c in m.calls]
        self.assertEqual(names, ['Creature_processDamage', 'Creature_run', 'Creature_updateActive',
                                 'Creature_stepAnim', 'Creature_applyKnockback', 'Minion.slot23',
                                 'model_getAttachPoint', 'obj_updateGridCell'])
        self.assertEqual(m.calls[5][1], (0x1010, 0))
        self.assertEqual(m.calls[6][1][0], 0x3000)
        self.assertEqual(m.calls[7][1], (0x6000,))

    def test_no_held_soul_no_placement(self):
        m = self.build(False)
        m.writes = []
        m.minion_run_prefix(0x1000)
        self.assertNotIn('model_getAttachPoint', [c[0] for c in m.calls])
        self.assertEqual([a for a, _s, _v in m.writes], [])

    def test_a_non_zero_run_result_ends_the_call(self):
        m = self.build(True, run=1)
        self.assertEqual(m.minion_run_prefix(0x1000), 'early')
        self.assertEqual([c[0] for c in m.calls], ['Creature_processDamage', 'Creature_run'])

    def test_states_below_the_limit_are_refused(self):
        with self.assertRaises(NotImplementedError):
            self.build(True, state=5).minion_run_prefix(0x1000)


if __name__ == '__main__':
    unittest.main()
