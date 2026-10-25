#!/usr/bin/env python3
"""test_ref_combat_ctors2.py - unit tests of tools/ref_combat_ctors2.py that need no game files.

Made-up memory only: the lazy type-info descriptors and the name comparison, Skeleton_isEnemy's
r + 1 and its red/blue rule, the charm and death gates, Soul_takeDamage's Demon-only gate,
its null-attacker throw, its six flat particles and their random sample points, the two
take-damage wrappers, and the destructor order of every class.  Whether the model matches
the game is tools/difftest_combat_ctors2.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ctors2 as CT2                 # noqa: E402

f32 = C.f32
SKEL, OTHER, NODE = 0x100000, 0x110000, 0x120000
NAMES = 0x300000
MODEL = 0xC00040


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.answers = {}
        self.model = CT2.Model(self.mem, self)
        # the name strings the getters store (authored copies at the game's addresses)
        for _desc, name, _base in CT2.TYPEINFO.values():
            self.text(name, b'%dX%x' % (len('X%x' % name), name))
        self.text(CT2.TYPEINFO[CT2.TI_SKELETON][1], b'8Skeleton')
        self.text(CT2.TYPEINFO[CT2.TI_DEMON][1], b'5Demon')
        for table, getter in ((CT2.VT_SKELETON, CT2.TI_SKELETON), (CT2.VT_DEMON, CT2.TI_DEMON),
                              (CT2.VT_SKELIGHT, 0x3CC6DC), (CT2.VT_SOUL, 0x3CC7A0)):
            self.mem.poke(table + 4, 4, getter)
            self.mem.poke(table + 8 * 37 + 4, 4, 0x3C2730)          # the base team slot
        self.mem.poke(CT2.VT_SKELETON + 8 * 20 + 4, 4, 0x2A7E04)
        self.mem.poke(CT2.VT_SOUL + 8 * 16 + 4, 4, 0x2AB298)        # Soul_getModel
        self.mem.poke(RC.G_SIM_FRAME, 4, 500)

    def get(self, name):
        if name in self.answers:
            value = self.answers[name]
            return value if callable(value) else (lambda *args: value)
        return None

    def text(self, addr, value):
        self.mem.poke(addr, len(value) + 1, int.from_bytes(value + b'\0', 'little'))

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]

    def creature(self, obj, table, flags=0x20, team=0, side=0):
        self.mem.poke(obj + 0x48, 4, table)
        self.mem.poke(obj + 0xC, 4, flags)
        self.mem.poke(obj + 0x310, 1, team & 0xFF)
        self.mem.poke(obj + 0x3D4, 1, side & 0xFF)


class TypeInfo(Fixture):
    def test_first_use_builds_the_chain(self):
        desc = self.model.typeinfo(CT2.TI_SKELETON)
        creature, gameobject = CT2.TYPEINFO[0x3C2608][0], CT2.TYPEINFO[0x3C7E10][0]
        self.assertEqual(desc, 0x908E20)
        self.assertEqual(self.mem.load(desc + 4, 4), CT2.VT_SI_TYPEINFO)
        self.assertEqual(self.mem.load(desc + 8, 4), creature)
        self.assertEqual(self.mem.load(creature + 8, 4), gameobject)
        self.assertEqual(self.mem.load(gameobject + 4, 4), CT2.VT_USER_TYPEINFO)
        self.assertEqual(self.model.calls, [])                       # nothing is a call-out

    def test_built_once(self):
        self.model.typeinfo(CT2.TI_DEMON)
        self.mem.poke(0x908B80 + 8, 4, 0x1234)                      # a built descriptor is not rebuilt
        self.model.typeinfo(CT2.TI_DEMON)
        self.assertEqual(self.mem.load(0x908B80 + 8, 4), 0x1234)

    def test_equal_by_name(self):
        a, b, na, nb = 0x400000, 0x400010, 0x400100, 0x400200
        self.text(na, b'5Demon')
        self.text(nb, b'5Demon')
        self.mem.poke(a, 4, na)
        self.mem.poke(b, 4, nb)
        self.assertTrue(self.model.typeinfo_equals(a, b))
        self.text(nb, b'5Demox')
        self.assertFalse(self.model.typeinfo_equals(a, b))
        self.assertTrue(self.model.typeinfo_equals(a, a))


class IsEnemy(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.creature(SKEL, CT2.VT_SKELETON, team=0, side=2)

    def test_base_enemy_is_one_more(self):
        self.creature(OTHER, CT2.VT_SKELIGHT, team=1)
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), 2)
        self.mem.poke(OTHER + 0xA8, 8, 0x100000000000)
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), 5)

    def test_red_and_blue(self):
        for mine, theirs, expect in ((2, 1, 1), (1, 2, 1), (2, 2, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (3, 1, 0)):
            self.mem.poke(SKEL + 0x3D4, 1, mine)
            self.creature(OTHER, CT2.VT_SKELETON, team=0, side=theirs)
            self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), expect, (mine, theirs))

    def test_only_an_exact_live_skeleton_and_not_while_charmed(self):
        self.creature(OTHER, CT2.VT_SKELIGHT, team=0, side=1)       # a Skelight of the same team
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), 0)
        self.creature(OTHER, CT2.VT_SKELETON, team=0, side=1)
        self.mem.poke(SKEL + 0x312, 2, 0xFFFF)                      # charmed
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), 0)
        self.mem.poke(SKEL + 0x312, 2, 0)
        self.mem.poke(OTHER + 0xC, 4, 0x20 | 8)                     # dead (base says 0 too)
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, OTHER), 0)

    def test_nothing(self):
        self.assertEqual(self.model.skeleton_is_enemy(SKEL, 0), 0)
        self.assertEqual(self.model.calls, [])


class SoulDamage(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.creature(SKEL, CT2.VT_SOUL)
        self.mem.poke(SKEL + 0x24, 4, 0x500000)                     # class block: model +0xc
        self.mem.poke(0x500000 + 0xC, 4, MODEL)
        self.mem.poke(SKEL + 0x228, 4, f32(10.0))
        self.mem.poke(SKEL + 0xDC, 4, f32(1.0))
        self.mem.poke(SKEL + 0x38, 2, 0x1000)
        self.mem.poke(SKEL + 0x44, 4, 0xBEEF)
        self.answers['model_getSamplePointCount'] = 5
        self.answers['model_getSamplePoint'] = lambda *a: ((f32(1.0), f32(2.0), f32(3.0)), (0, 0, 0))

    def test_only_a_demon_hurts(self):
        self.creature(OTHER, CT2.VT_SKELIGHT)
        self.model.soul_take_damage(SKEL, OTHER, 1, f32(5.0))
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.mem.load(SKEL + 0x228, 4), f32(10.0))

    def test_a_demon_hurts_and_six_flat_particles(self):
        self.creature(OTHER, CT2.VT_DEMON)
        self.model.soul_take_damage(SKEL, OTHER, 1, f32(4.0))
        self.assertEqual(self.mem.load(SKEL + 0x228, 4), f32(6.0))
        spawns = self.named('particle_spawn')
        self.assertEqual(len(spawns), CT2.SOUL_PARTICLES)
        for definition, point, velocity, extra in spawns:
            self.assertEqual(definition, CT2.P_SOUL)
            self.assertEqual(velocity[2], 0)                        # the z word zeroed before the scale
            self.assertEqual(extra, 0)
        points = self.named('model_getSamplePoint')
        self.assertTrue(all(0 <= p[4] < 5 for p in points))
        self.assertTrue(all(p[3] == (0x1000 - 0x4000) & 0xFFFFFFFF for p in points))
        self.assertEqual(self.model.draws, 0)                       # own draws only

    def test_no_sample_points(self):
        self.creature(OTHER, CT2.VT_DEMON)
        self.answers['model_getSamplePointCount'] = 0
        self.model.soul_take_damage(SKEL, OTHER, 1, f32(4.0))
        self.assertEqual(self.named('particle_spawn'), [])

    def test_no_attacker_throws(self):
        with self.assertRaises(CT2.BadTypeid):
            self.model.soul_take_damage(SKEL, 0, 1, f32(4.0))
        self.assertEqual(self.model.calls, [('cxx_throwBadTypeid', ())])


class Wrappers(Fixture):
    def test_take_damage_wrappers(self):
        for method in ('skeleton_take_damage', 'antqueen_take_damage'):
            self.mem.poke(SKEL + 0x228, 4, f32(10.0))
            getattr(self.model, method)(SKEL, 0, 1, f32(3.0))
            self.assertEqual(self.mem.load(SKEL + 0x228, 4), f32(7.0))
            self.assertEqual(self.mem.load(SKEL + 0xC8, 4), f32(3.0) if method == 'skeleton_take_damage'
                             else f32(6.0))


class Dtors(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.answers['iter_begin'] = 0

    def order(self):
        return [(n, a) for n, a in self.model.calls if n in ('handle_clear', 'pool_free', 'AnimState_dtor')]

    def test_skeleton_and_soul(self):
        for method, table in (('skeleton_dtor', CT2.VT_SKELETON), ('soul_dtor', CT2.VT_SOUL)):
            self.model.calls = []
            getattr(self.model, method)(SKEL, 1)
            calls = self.order()
            self.assertEqual(calls[:2], [('handle_clear', (SKEL + 0x3CC,)), ('handle_clear', (SKEL + 0x3C8,))])
            self.assertEqual(calls[-1], ('pool_free', (SKEL,)))
            self.assertEqual(sum(1 for n, _a in calls if n == 'pool_free'), 1)
            self.assertNotEqual(self.mem.load(SKEL + 0x48, 4), table)   # the base tables follow

    def test_no_free_without_bit_0(self):
        for method in ('antqueen_dtor', 'fire_dtor', 'loosefire_dtor', 'poison_gas_dtor'):
            self.model.calls = []
            getattr(self.model, method)(SKEL, 2)
            self.assertEqual(self.named('pool_free'), [], method)

    def test_gameobject_classes(self):
        for method, first in (('fire_dtor', SKEL + 8), ('loosefire_dtor', SKEL + 0x4C),
                              ('poison_gas_dtor', SKEL + 0x4C)):
            self.model.calls = []
            getattr(self.model, method)(SKEL, 3)
            clears = self.named('handle_clear')
            self.assertEqual(clears[0], (first,), method)
            self.assertEqual(clears[-3:], [(SKEL + 8,), (SKEL + 4,), (SKEL,)])
            self.assertEqual(self.named('pool_free'), [(SKEL,)])


if __name__ == '__main__':
    unittest.main()
