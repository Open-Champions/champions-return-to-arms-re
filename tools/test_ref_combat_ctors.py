#!/usr/bin/env python3
"""test_ref_combat_ctors.py - unit tests of tools/ref_combat_ctors.py that need no game files.

Made-up memory only: the Skeleton prefix table and the fields it leaves, the AntQueen
hit-point draw and rear-attack direction, the Soul's skipped state-0 entry, its airhub
rewrite, its owner and thrown filters and its flat burst, the Skeleton set-state's flag
clears and its dead blocking-flinch branch, and the three run prologues' order.  Whether
the model matches the game is tools/difftest_combat_ctors.py's business (it needs the
executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ctors as CT                   # noqa: E402

f32 = C.f32
CRE, ENEMY, NODE, OWNER = 0x100000, 0x110000, 0x120000, 0x130000
RECORDS = 0x200000
TEXT = 0x300000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF


class Fixture(unittest.TestCase):
    answers = {}

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = CT.Model(self.mem, self)
        self.answers = dict(self.answers)
        rec = RECORDS
        for block, count in ((CT.DEF_ANTQUEEN, 25), (CT.DEF_SOUL, 19), (CT.SKEL_COMMON, 72)):
            for k in range(2, count):
                self.mem.poke(block + 8 * k + 4, 4, rec)
                rec += 0x40
        for n in range(4):
            self.mem.poke(CT.DEF_SKELETON + CT.DEF_SKELETON_STEP * n + 0xC, 4, 0xC00040)
        self.mem.poke(CT.DEF_ANTQUEEN + 0xC, 4, 0xC00040)
        self.mem.poke(CT.DEF_SOUL + 0xC, 4, 0xC00040)
        self.mem.poke(CT.DEF_SOUL + 0x1C, 4, 0xC00080)
        self.mem.poke(RC.G_SIM_FRAME, 4, 500)

    def get(self, name):                        # the callbacks object of the model
        if name == 'GameObject_ctor':           # what the stub leaves: the class definition
            return lambda obj, pos, class_def, props: self.mem.poke(obj + 0x24, 4, class_def)
        if name in self.answers:
            value = self.answers[name]
            return lambda *args: value
        return None

    def text(self, addr, value):
        self.mem.poke(addr, len(value) + 1, int.from_bytes(value + b'\0', 'little'))

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]


class Skeleton(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        texts = (b'skeletonred', b'skeletonblue', b'skeletonswordohwred', b'skeletonswordohwblue',
                 b'skeletonsworddhwred', b'skeletonsworddhwblue', b'skeletonaxered', b'skeletonaxeblue',
                 b'skeletonspearred', b'skeletonspearblue', b'skeletonbowred', b'skeletonbowblue',
                 b'skeletonswordohw', b'skeletonsworddhw', b'skeletonaxe', b'skeletonspear', b'skeletonbow')
        for (addr, _kind, _side), value in zip(CT.SKEL_PREFIXES, texts):
            self.text(addr, value)

    def build(self, name, model_set=0, seed=0x1234):
        self.text(TEXT, name)
        self.mem.poke(CRE + 0x44, 4, seed)
        self.model.skeleton_ctor(CRE, (0, 0, 0), 0x4000, 0, TEXT, model_set)
        return self.mem.load(CRE + 0x3D0, 4), self.mem.load(CRE + 0x3D4, 1)

    def test_prefixes(self):
        self.assertEqual(self.build(b'skeletonbowblue'), (4, 2))         # blue bow is red
        self.assertEqual(self.build(b'skeletonaxeblue'), (2, 1))
        self.assertEqual(self.build(b'skeletonspear'), (3, 0))
        self.assertEqual(self.build(b'skeletonsworddhwred'), (1, 2))

    def test_side_only_keeps_the_drawn_kind(self):
        kind, side = self.build(b'skeletonred', seed=0x1234)
        self.assertEqual(side, 2)
        self.assertEqual(kind, (lcg(0x1234) >> 16) % 5)

    def test_home_range_and_holder(self):
        self.build(b'skeletonaxered')
        self.assertEqual(self.mem.load(CRE + 0x3C0, 4), CT.F_200)
        self.assertEqual(self.mem.load(CRE + 0x50, 4), CRE + 0x3D8)
        self.build(b'watskel')
        self.assertEqual(self.mem.load(CRE + 0x3C0, 4), CT.F_1000)
        self.assertEqual(self.mem.load(CRE + 0x3D8, 4), 0x50CDA0)            # WeaponShield table

    def test_ctor_enters_state_zero_through_set_state(self):
        self.build(b'skeletonbow')
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 0)
        self.assertEqual(self.mem.load(CRE + 0xF4, 4), 120)                  # clock 0 + 120
        self.assertEqual([n for n, _a in self.model.calls][-2:], ['obj_runEvery60', 'Creature_init'])

    def test_bow_event_slots(self):
        self.build(b'skeletonbow')
        record = self.mem.load(CT.SKEL_COMMON + 8 * 0x39 + 4, 4)
        self.assertEqual((self.mem.load(record + 0x18, 1), self.mem.load(record + 0x20, 1)), (2, 1))
        self.assertEqual((self.mem.load(record + 0x14, 4), self.mem.load(record + 0x1C, 4)), (CT.F_0_2, CT.F_1_3))

    def test_set_state_clears_blocking_and_never_flinches_blocked(self):
        self.build(b'skeletonswordohw')
        self.mem.poke(CRE + 0xA8, 8, 0x200A00)
        self.model.calls.clear()
        self.model.skeleton_set_state(CRE, 0x12)
        self.assertEqual(self.mem.load(CRE + 0xA8, 8) & 0x200A00, 0)
        clip = self.mem.load(CT.SKEL_COMMON + 0x34, 4)                        # kind 0 row, +0x34
        self.assertEqual(self.named('anim_startBlendInOut')[0][1], clip)
        self.mem.poke(CRE + 0xA8, 8, 0x200A00)
        self.model.skeleton_set_state(CRE, 0x17)
        self.assertEqual(self.mem.load(CRE + 0xA8, 8) & 0x200A00, 0x200800)


class AntQueen(Fixture):
    def build(self):
        self.model.antqueen_ctor(CRE, TEXT, (0, 0, 0), 0, 0)

    def test_hit_point_argument_uses_the_unseeded_generator(self):
        self.build()
        d = lcg(0) >> 16
        self.assertEqual(self.mem.load(CRE + 0x228, 4), C.from_int(d % 14 + 4))
        self.assertEqual(self.mem.load(CRE + 0x3D8, 4), 180 + (lcg(lcg(0)) >> 16) % 180)
        self.assertEqual(self.mem.load(CRE + 0xF4, 4), 0)                    # state 0 without its entry

    def rear(self, x, y):
        self.build()
        self.mem.poke(CRE + 0x234, 4, NODE)
        self.mem.poke(ENEMY + 0x10, 4, f32(x))
        self.mem.poke(ENEMY + 0x14, 4, f32(y))
        self.answers['creature_findEnemyInCone'] = ENEMY
        self.model.calls.clear()
        self.model.antqueen_set_state(CRE, 7)
        clip = self.named('anim_startBlendInOut')[0][1]
        return [k for k in (4, 5, 6) if self.mem.load(CT.DEF_ANTQUEEN + 8 * k + 4, 4) == clip][0]

    def test_rear_attack_direction(self):
        self.assertEqual(self.rear(-100.0, 0.0), 4)          # straight behind: centre
        self.assertEqual(self.rear(-100.0, -60.0), 6)        # bearing -0x5000 + 0x7fff: above 2000
        self.assertEqual(self.rear(-100.0, 60.0), 5)

    def test_rear_attack_without_target_only_stores(self):
        self.build()
        self.model.calls.clear()
        self.model.antqueen_set_state(CRE, 7)
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 7)
        self.assertEqual(self.named('anim_startBlendInOut'), [])


class Soul(Fixture):
    def build(self, owner=0, level=b'drunare'):
        self.text(CT.G_LEVEL_NAME, level)
        self.text(CT.S_AIRHUB, b'airhub')
        self.model.soul_ctor(CRE, TEXT, (0, 0, 0), 0, 0, owner)

    def test_state_zero_entry_is_skipped(self):
        self.build()
        self.assertEqual((self.mem.load(CRE + 0x232, 2), self.mem.load(CRE + 0xF4, 4)), (0, 0))
        self.assertEqual(self.mem.load(CRE + 0xA8, 8) >> 63, 1)

    def test_airhub_rewrites_every_request(self):
        self.build(level=b'AirHub')
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 0x22)
        self.model.soul_set_state(CRE, 1)
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 0x22)

    def test_owned_soul_accepts_only_held_states(self):
        self.build(owner=OWNER)
        self.mem.poke(CRE + 0x3C8, 4, NODE)
        self.model.soul_set_state(CRE, 0x14)
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 0)
        self.model.soul_set_state(CRE, 0x1B)
        self.assertEqual((self.mem.load(CRE + 0x232, 2), self.mem.load(CRE + 0x3C8, 4)), (0x1B, 0))
        self.model.soul_set_state(CRE, 0x1D)
        self.assertEqual(self.mem.load(CRE + 0x232, 2), 0x1B)            # thrown: nothing accepted

    def test_burst_is_flat(self):
        self.build()
        self.answers['model_getSamplePointCount'] = 2
        self.answers['model_getSamplePoint'] = ((f32(1.0), f32(2.0), f32(3.0)), (0, 0, 0))
        self.model.soul_set_state(CRE, 0x21)
        spawns = self.named('particle_spawn')
        self.assertEqual(len(spawns), 4)
        self.assertTrue(all(args[2][2] == 0 for args in spawns))
        self.assertEqual(self.mem.load(CRE + 0xC, 4) & 0x4002, 0x4002)

    def test_model_slot(self):
        self.build()
        self.assertEqual(self.model.soul_get_model(CRE), 0xC00040)
        self.mem.poke(CRE + 0x3C8, 4, NODE)
        self.assertEqual(self.model.soul_get_model(CRE), 0xC00080)


class Prologues(Fixture):
    def order(self, method, active):
        self.model.calls.clear()
        self.model.update_active = lambda c: active
        self.model.process_damage = lambda c, m: self.model.calls.append(('processDamage', (m,)))
        self.model.run = lambda c, m: self.model.calls.append(('run', (m,))) and 0
        self.model.step_anim = lambda c, s: self.model.calls.append(('stepAnim', (s,)))
        self.model.move_by = lambda c, v: self.model.calls.append(('moveBy', (v,)))
        self.model.vcall = lambda obj, slot, *a: self.model.calls.append(('v%d' % slot, a)) or 0xC00040
        getattr(self.model, method)(CRE)
        return [n for n, _a in self.model.calls]

    def test_antqueen_ignores_activity(self):
        self.assertEqual(self.order('antqueen_run_prologue', 0),
                         ['processDamage', 'run', 'stepAnim', 'Creature_applyKnockback', 'v23'])

    def test_skeleton_stops_when_inactive_and_updates_its_holder(self):
        self.assertEqual(self.order('skeleton_run_prologue', 0), ['processDamage', 'run'])
        self.mem.poke(CRE + 0x50, 4, CRE + 0x3D8)
        self.mem.poke(CRE + 0x3D8, 4, 0x50CDA0)
        self.assertIn('Holder.v21', self.order('skeleton_run_prologue', 1))

    def test_soul_moves_by_zero_unless_held(self):
        names = self.order('soul_run_prologue', 1)
        self.assertEqual(names, ['v16', 'processDamage', 'v16', 'run', 'stepAnim', 'Creature_applyKnockback', 'v23',
                                 'moveBy'])
        self.mem.poke(CRE + 0x3C8, 4, NODE)
        self.assertNotIn('moveBy', self.order('soul_run_prologue', 1))


if __name__ == '__main__':
    unittest.main()
