#!/usr/bin/env python3
"""test_ref_potion_ctors.py - unit tests of tools/ref_potion_ctors.py that need no game files.

Made-up memory only: the fields each constructor leaves, the shared-seed draws of
fx_spawn id 5 and of a whole LooseFire, a refused pool, Fire_run's alpha and lifetime,
LooseFire_run's end test, LooseFire_onTouch's gate, owner and descriptor, and the radius
floor of poisonGasSpell_ctor.  Whether the model matches the game is
tools/difftest_potion_ctors.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_potion_ctors as PC                   # noqa: E402

f32 = C.f32
OBJ, NODE, OWNER, OTHER = 0x1000, 0x2000, 0x3000, 0x4000
BLOCKS = [0x10000 + 0x100 * i for i in range(8)]
POS = (f32(100.0), f32(-50.0), f32(12.0))


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.calls = []
        self.answers = {}
        self.pool = list(BLOCKS)
        self.model = PC.Model(self.mem, self)
        for i in range(PC.FX_DEF_COUNT):
            self.mem.poke(PC.FX_DEF_FLAGS + 4 * i, 4, 1)
        self.mem.poke(PC.G_RAND_SEED, 4, 0x12345678)
        self.mem.poke(PC.G_SIM_FRAME, 4, 1000)

    def get(self, name):                        # the callbacks object of the model
        def answer(*args):
            self.calls.append((name, args))
            if name == 'pool_new':
                return self.pool.pop(0) if self.pool else 0
            return self.answers.get(name)
        return answer

    def named(self, name):
        return [args for n, args in self.calls if n == name]


class FxSpawnFive(Fixture):
    def test_count_points_and_draws(self):
        seed = 0x12345678
        seed = lcg(seed)
        count = 3 + ((seed >> 16) & 1)
        expect = []
        for _fire in range(count):
            draws = []
            for _axis in range(3):
                seed = lcg(seed)
                draws.append(seed >> 16)
            expect.append((C.add(C.sub(POS[0], C.SIX), C.from_int(draws[0] % 12)),
                           C.add(C.sub(POS[1], C.SIX), C.from_int(draws[1] % 12)),
                           C.add(POS[2], C.from_int(draws[2] % 18))))
            seed = lcg(seed)                     # the Fire's own GameObject_ctor
        self.model.fx_spawn(5, POS)
        self.assertEqual(len(self.named('pool_new')), count)
        made = [self.model.vec(b + 0x10) for b in BLOCKS[:count]]
        self.assertEqual(made, expect)
        self.assertEqual(self.model.draws, 1 + 4 * count)
        self.assertEqual(self.mem.load(PC.G_RAND_SEED, 4), seed)

    def test_refused_block_skips_only_that_fire(self):
        plan = [0, BLOCKS[0], 0, BLOCKS[1]]
        self.pool = list(plan)
        self.model.fx_spawn(5, POS)
        fires = len(self.named('pool_new'))
        made = sum(1 for block in plan[:fires] if block)
        self.assertEqual(self.model.draws, 1 + 3 * fires + made)
        self.assertEqual(len([a for a in self.named('handle_link') if a[0] == PC.G_ACTIVE_LIST]), made)
        self.assertEqual(self.mem.load(BLOCKS[0] + 0x48, 4), PC.VT_FIRE)

    def test_other_ids_and_unmade_definitions_refuse(self):
        with self.assertRaises(NotImplementedError):
            self.model.fx_spawn(8, POS)
        self.mem.poke(PC.FX_DEF_FLAGS + 4 * 23, 4, 0)
        with self.assertRaises(NotImplementedError):
            self.model.fx_spawn(5, POS)
        self.assertEqual(self.model.draws, 0)


class Fire(Fixture):
    def test_ctor_fields(self):
        self.mem.poke(OBJ + 0xC, 4, 0x10)
        self.model.fire_ctor(OBJ, POS)
        m = self.model
        self.assertEqual(m.u32(OBJ + 0x48), PC.VT_FIRE)
        self.assertEqual(m.u32(OBJ + 0xC), 0x4001)          # GameObject_ctor clears the flags first
        self.assertEqual(m.u8(OBJ + 0x28), 0xF0)
        self.assertEqual(m.u16(OBJ + 0x4C), 100)
        self.assertEqual(m.vec(OBJ + 0x10), POS)
        self.assertEqual(m.draws, 1)
        self.assertIn((PC.G_ACTIVE_LIST, OBJ + 4, OBJ), self.named('handle_link'))

    def alpha_at(self, life):
        self.calls = []
        self.mem.poke(OBJ + 0x4C, 2, life & 0xFFFF)
        self.model.fire_run(OBJ)
        return RC.s32(self.named('glow_add')[0][4])

    def test_alpha(self):
        self.assertEqual(self.alpha_at(100), 0)
        self.assertEqual(self.alpha_at(81), 57)
        self.assertEqual(self.alpha_at(80), 60)
        self.assertEqual(self.alpha_at(20), 60)
        self.assertEqual(self.alpha_at(19), 57)
        self.assertEqual(self.alpha_at(1), 3)
        self.assertEqual(self.alpha_at(0), 0)
        self.assertEqual(self.alpha_at(-1), -3)

    def test_life_and_delete(self):
        self.mem.poke(OBJ + 0x4C, 2, 2)
        self.model.fire_run(OBJ)
        self.assertEqual(self.model.u16(OBJ + 0x4C), 1)
        self.assertFalse(self.named('Creature.v1'))
        self.model.fire_run(OBJ)
        self.assertEqual(self.named('Creature.v1'), [(OBJ, 3)])
        self.assertEqual(self.model.draws, 0)                # own generator only

    def test_particle_rises(self):
        self.mem.poke(OBJ + 0x44, 4, 0xCAFEBABE)
        for i, word in enumerate(POS):
            self.mem.poke(OBJ + 0x10 + 4 * i, 4, word)
        self.mem.poke(OBJ + 0x4C, 2, 50)
        self.model.fire_run(OBJ)
        (definition, point, velocity, back), = self.named('particle_spawn')
        self.assertEqual(definition, PC.FIRE_PARTICLE)
        self.assertEqual(back, C.ZERO)
        self.assertFalse(C.lt(point[2], POS[2]))            # |2u'.z| is added
        self.assertTrue(C.lt(f32(2.7), velocity[2]))         # 2u.z + 4.8 with |u.z| <= 1


class LooseFire(Fixture):
    def test_ctor_fields_and_draws(self):
        self.mem.poke(PC.G_SIM_FRAME, 4, 0xFFFFFFF0)
        plan = [BLOCKS[0], 0, BLOCKS[1], BLOCKS[2]]
        self.pool = list(plan)
        self.model.loosefire_ctor(OBJ, POS, OWNER)
        m = self.model
        self.assertEqual(m.u32(OBJ + 0x48), PC.VT_LOOSEFIRE)
        self.assertEqual(m.u32(OBJ + 0x50), 0x68)            # frame + 120, wrapping
        self.assertEqual(m.u32(OBJ + 0xC), 0x420C)
        self.assertEqual(m.u32(OBJ + 0x1C), PC.F_TEN)
        links = self.named('handle_link')
        self.assertEqual(links[1], (OBJ + 0x4C, OWNER, OWNER))
        self.assertEqual(links[-1], (PC.G_ACTIVE_LIST, OBJ + 4, OBJ))
        self.assertEqual(m.draws, PC.loosefire_draws(plan[:len(self.named('pool_new'))]))

    def test_no_owner_no_link(self):
        self.model.loosefire_ctor(OBJ, POS, 0)
        self.assertFalse([a for a in self.named('handle_link') if a[0] == OBJ + 0x4C])

    def test_draw_bounds(self):
        self.assertEqual(PC.loosefire_draws([0, 0, 0]), 11)
        self.assertEqual(PC.loosefire_draws([1, 1, 1, 1]), 18)
        self.assertEqual(PC.loosefire_draws([1, 0, 1]), 13)

    def test_run_end(self):
        self.mem.poke(OBJ + 0x50, 4, 1000)
        self.model.loosefire_run(OBJ)
        self.assertFalse(self.calls)                         # end == frame: alive
        self.mem.poke(OBJ + 0x50, 4, 999)
        self.model.loosefire_run(OBJ)
        self.assertEqual(self.calls, [('Creature.v1', (OBJ, 3))])


class Touch(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.mem.poke(PC.G_SIM_FRAME, 4, 2000)

    def touch(self, flags, difficulty=0):
        self.calls = []
        self.mem.poke(OTHER + 0xC, 4, flags)
        self.mem.poke(PC.G_DIFFICULTY, 4, difficulty & 0xFFFFFFFF)
        self.model.loosefire_on_touch(OBJ, OTHER)
        hits = self.named('damage_apply')
        return hits[0] if hits else None

    def test_gate(self):
        self.mem.poke(PC.G_SIM_FRAME, 4, 2001)
        self.assertIsNone(self.touch(0x20))
        self.mem.poke(PC.G_SIM_FRAME, 4, (-40) & 0xFFFFFFFF)
        self.assertIsNotNone(self.touch(0x20))

    def test_descriptors(self):
        for level, value in ((0, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 1), (-1, 1)):
            hit = self.touch(0x40, level)
            self.assertEqual(hit[6], ('desc', (0x15, value, value, 0), None, None, None))
        self.assertEqual(self.touch(0x60, 4)[6][1], (0x15, 4, 4, 0))   # a player is a player first
        self.assertEqual(self.touch(0x20, 4)[6][1], (0x15, 8, 8, 0))
        hit = self.touch(0x4081)
        self.assertEqual(hit[6], ('desc', None, None, None, None))
        self.assertEqual(hit[:6], (OTHER, OBJ, PC.TOUCH_RATING, 0, 0, PC.TOUCH_FLAGS))
        self.assertEqual(hit[7:], (0, C.ZERO, C.ZERO))

    def test_owner(self):
        self.mem.poke(OBJ + 0x4C, 4, NODE)
        self.mem.poke(NODE + 0xC, 4, OWNER)
        self.mem.poke(OWNER + 0xC, 4, 0x4081)                # not a creature: the fire is the attacker
        self.assertEqual(self.touch(0x20)[1], OBJ)
        self.assertFalse(self.named('Creature.v20'))
        self.mem.poke(OWNER + 0xC, 4, 0x20)
        self.answers['Creature.v20'] = 1
        self.assertEqual(self.touch(0x20)[1], OWNER)
        self.assertEqual(self.named('Creature.v20'), [(OWNER, OTHER)])
        self.answers['Creature.v20'] = 0
        self.assertIsNone(self.touch(0x20))


class PoisonGas(Fixture):
    def test_potion_call(self):
        self.model.poison_gas_ctor(OBJ, POS, 0x12C, 0x14, 0, OWNER, 5)
        m = self.model
        self.assertEqual(m.u32(OBJ + 0x48), PC.VT_POISON_GAS)
        self.assertEqual(m.vec(OBJ + 0x50), POS)
        self.assertEqual(m.u32(OBJ + 0x5C), 1300)
        self.assertEqual(m.u32(OBJ + 0x60), 20)
        self.assertEqual(m.u32(OBJ + 0x64), PC.F_TEN)
        self.assertEqual(m.u32(OBJ + 0x68), 0)
        self.assertEqual(m.u32(OBJ + 0x6C), 5)
        self.assertEqual(m.u32(OBJ + 0xC), 3)
        self.assertEqual(m.draws, 1)
        self.assertIn((OBJ + 0x4C, OWNER, OWNER), self.named('handle_link'))

    def test_radius_floor(self):
        for given, kept in ((9, 10), (10, 10), (11, 11), (0xFFFFFFFF, 10), (0x80000000, 10), (0x7FFFFFFF, 0x7FFFFFFF)):
            self.model.poison_gas_ctor(OBJ, POS, 1, given, 7, 0, 25)
            self.assertEqual(self.model.u32(OBJ + 0x60), kept)
            self.assertEqual(self.model.u32(OBJ + 0x68), 7)


if __name__ == '__main__':
    unittest.main()
