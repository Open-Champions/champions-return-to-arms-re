#!/usr/bin/env python3
"""test_ref_arrow_run.py - unit tests of tools/ref_arrow_run.py that need no game files.

Made-up memory: a Skeleton's MissileWeapon built, flown, touching an idle player, a
creature, an ally, the terrain and nothing; the hit-state lifetimes (player victim: the
same run; creature victim: the next run; terrain: the same run; nothing: 300 runs); the
draws (one shared at construction, one shared per touch that reaches the deflection roll,
none for Penetrating Arrows); no stick for a monster's arrow and a stick for a player's;
the orphaned arrow as its own attacker; the three element-arrow destructors.  Whether the
model matches the game is tools/difftest_arrow_run.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_b as SB                       # noqa: E402
import ref_arrow_run as A                       # noqa: E402

f32 = C.f32
M32 = 0xFFFFFFFF
ARROW, SKEL, PLAYER, CREATURE, ALLY, SCRATCH, NODES = 0x100000, 0x110000, 0x120000, 0x130000, 0x140000, \
    0x150000, 0x160000
STUB_TABLE = 0x170000
FRAME = 5000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & M32


class World:
    """The callbacks: a flat floor at z = 0 (or a wall), a box query that returns the
    objects of `present`, an owner that is the enemy of `enemies`."""

    def __init__(self, test):
        self.t = test
        self.present = []
        self.enemies = set()
        self.wall = None
        self.damage = 1
        self.slot17 = 0
        self.dodge = 0.0

    def get(self, name):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        return handler

    def on_terrain_height(self, world, pos, radius):
        x = C.to_float(pos[0])
        return f32(500.0) if self.wall is not None and x >= self.wall else f32(0.0)

    def on_world_collectObjectsInBox(self, low, high, limit):
        return list(self.present)

    def on_Creature_v20(self, this, other):
        return 1 if other in self.enemies else 0

    def on_damage_apply(self, *args):
        return self.damage

    def on_Creature_v36(self, this):
        return 0

    def on_player_getSkillRank(self, slot, skill):
        return 0

    def on_SkillDodge_getStat0Fraction(self, skill, rank):
        return f32(self.dodge)

    def on_Creature_v0(self):
        return 0x908130

    def on_Creature_v16(self, this):
        return 0x180000

    def on_Skeleton_typeinfo(self):
        return 0x908E20

    def on_trail_create(self, *args):
        return 7

    def on_libc_sprintf(self, fmt, value):
        return ('buf', b'stone_hit_sound')


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.world = World(self)
        self.model = A.Model(self.mem, self.world)
        mem = self.mem
        mem.poke(RC.G_RAND_SEED, 4, 0x2468)
        mem.poke(RC.G_SIM_FRAME, 4, FRAME)
        # the handle-node free list
        for i in range(200):
            mem.poke(NODES + 0x14 * i, 4, NODES + 0x14 * (i + 1) if i < 199 else 0)
        mem.poke(SB.G_HANDLE_FREE, 4, NODES)
        # the arrow classes' tables: the slots this module runs
        for fn, (slot, _m) in A.CLASS_BODIES.items():
            for _e, (_n, table, *_rest) in A.CLASSES.items():
                if (table, fn) in ((A.VT_MISSILE, A.MISSILE_DTOR), (A.VT_MISSILE, A.MISSILE_RUN),
                                   (A.VT_MISSILE, A.MISSILE_ON_TOUCH), (A.VT_MISSILE, A.MISSILE_NEAREST)):
                    mem.poke(table + 8 * slot + 4, 4, fn)
        for slot in range(48):
            mem.poke(STUB_TABLE + 8 * slot + 4, 4, 0x00F00000 + 16 * slot)
        for obj, flags in ((SKEL, 0x20), (PLAYER, 0x60), (CREATURE, 0x20), (ALLY, 0x20)):
            mem.poke(obj + 0xC, 4, flags)
            mem.poke(obj + 0x48, 4, STUB_TABLE)
            mem.poke(obj + 0x1C, 4, f32(12.0))
            mem.poke(obj + 0x20, 4, f32(72.0))
        for k, b in enumerate(b'8Creature\0'):
            mem.poke(0x190000 + k, 1, b)
        for k, b in enumerate(b'8Skeleton\0'):
            mem.poke(0x190020 + k, 1, b)
        mem.poke(0x908130, 4, 0x190000)
        mem.poke(0x908E20, 4, 0x190020)

    def put(self, addr, values):
        for i, v in enumerate(values):
            self.mem.poke(addr + 4 * i, 4, f32(v))

    def calls(self, name):
        return [args for n, args in self.model.calls if n == name]

    def build(self, owner=SKEL, vel=(400.0, 0.0, 0.0), pos=(0.0, 0.0, 54.0)):
        self.put(SCRATCH, pos)
        self.put(SCRATCH + 0x10, vel)
        self.model.skeleton_missile(ARROW, 0, 0, SCRATCH, SCRATCH + 0x10, 0xC000, owner, 3, 5, 200)

    def tick(self):
        self.mem.poke(RC.G_SIM_FRAME, 4, self.mem.load(RC.G_SIM_FRAME, 4) + 1)
        self.model.calls = []
        self.model.vcall(ARROW, 4)

    def place(self, obj, x, y=0.0, z=0.0):
        self.put(obj + 0x10, (x, y, z))


class Construction(Fixture):
    def test_one_shared_draw_and_the_skeleton_fields(self):
        self.build()
        m, mem = self.model, self.mem
        self.assertEqual(m.draws, 1)
        self.assertEqual(mem.load(ARROW + 0x44, 4), lcg(0x2468) >> 16)
        self.assertEqual(mem.load(ARROW + 0x48, 4), A.VT_MISSILE)
        self.assertEqual(mem.load(ARROW + 0xD0, 4), 0)
        self.assertEqual([mem.load(ARROW + o, 4) for o in (0xD4, 0xD8, 0xDC, 0xE0, 0xE4, 0xE8, 0x12C)],
                         [3, 5, 0, 0, 200, 4, 0])
        self.assertEqual(mem.load(ARROW + 0xEC, 4), FRAME + 300)
        self.assertEqual(mem.load(ARROW + 0xCD, 1), 1)
        self.assertEqual(mem.load(ARROW + 0xC, 4) & 0x4081, 0x4081)
        self.assertEqual(m.handle_obj(ARROW + 0x4C), SKEL)
        self.assertEqual(mem.load(ARROW + 0x38, 2), 0xC000)
        self.assertEqual(len(self.calls('trail_create')), 1)            # kind 0, not a cold level
        self.assertEqual(self.calls('light_unlink'), [(ARROW + 0x174,)])

    def test_no_trail_on_a_cold_level(self):
        self.mem.poke(RC.G_LEVEL_FLAGS, 4, 0x100)
        self.build()
        self.assertEqual(self.calls('trail_create'), [])


class Flight(Fixture):
    def test_straight_line_no_gravity_and_300_frames(self):
        self.build(vel=(400.0, 0.0, -6.0))
        runs = 0
        while not self.calls('GameObject_dtor'):
            self.tick()
            runs += 1
            self.assertLess(runs, 400)
        self.assertEqual(runs, 300)
        self.assertEqual([self.mem.load(ARROW + 0x1B0 + 4 * i, 4) for i in range(3)],
                         [f32(400.0), 0, f32(-6.0)])                      # the velocity never changes
        self.assertEqual(self.model.draws, 1)

    def test_terrain_ends_it_in_the_same_run(self):
        self.build()
        self.world.wall = 0.0
        self.tick()
        self.assertTrue(self.calls('GameObject_dtor'))
        self.assertTrue(self.calls('libc_sprintf'))


class Touch(Fixture):
    def test_idle_player_hit_in_the_same_run_one_deflection_draw(self):
        self.build()
        self.place(PLAYER, 5.0, 0.0, 0.0)
        self.world.present = [SKEL, PLAYER]
        self.world.enemies = {PLAYER}
        before = self.model.draws
        self.tick()
        damage = self.calls('damage_apply')
        self.assertEqual(len(damage), 1)
        self.assertEqual(damage[0][:2], (PLAYER, SKEL))
        self.assertEqual(damage[0][5], 4)                               # damage flags 4, no unblockable bit
        self.assertEqual(self.model.draws - before, 1)                  # the deflection roll only
        self.assertEqual(self.calls('player_getSkillRank'), [(0, 2), (0, 0x53)])   # Dodge, not skill 0x5d
        self.assertEqual(self.mem.load(ARROW + 0xCC, 1), 3)
        self.assertTrue(self.calls('GameObject_dtor'))                  # expiry = this frame
        self.assertEqual(self.mem.load(ARROW + 0x128, 4), 0)            # never stuck

    def test_creature_hit_lives_one_more_run_and_never_sticks(self):
        self.build()
        self.place(CREATURE, 5.0)
        self.world.present = [CREATURE]
        self.world.enemies = {CREATURE}
        self.tick()
        self.assertEqual(self.mem.load(ARROW + 0xCC, 1), 1)
        self.assertEqual(self.calls('GameObject_dtor'), [])
        self.assertEqual(self.mem.load(ARROW + 0x128, 4), 0)
        self.tick()
        self.assertTrue(self.calls('GameObject_dtor'))

    def test_ally_is_passed_through(self):
        self.build()
        self.place(ALLY, 5.0)
        self.world.present = [ALLY]
        self.tick()
        self.assertEqual(self.calls('damage_apply'), [])
        self.assertEqual(self.mem.load(ARROW + 0xCC, 1), 0)
        self.assertEqual(self.model.draws, 1)

    def test_orphaned_arrow_is_its_own_attacker(self):
        self.build()
        self.model.handle_clear(SKEL)                                   # the owner is destroyed
        self.place(CREATURE, 5.0)
        self.world.present = [CREATURE]
        self.tick()
        self.assertEqual(self.calls('Creature.v20'), [])
        self.assertEqual(self.calls('damage_apply')[0][:2], (CREATURE, ARROW))

    def test_deflection_deletes_without_damage(self):
        self.build()
        self.place(PLAYER, 5.0)
        self.world.present = [PLAYER]
        self.world.enemies = {PLAYER}
        self.world.dodge = 1.0                                          # chance 100
        roll = (lcg(self.mem.load(RC.G_RAND_SEED, 4)) >> 16) % 100 + 1
        self.tick()
        self.assertEqual(bool(self.calls('obj_delete')), roll < 100)
        if roll < 100:
            self.assertEqual(self.calls('damage_apply'), [])
            self.assertEqual(len(self.calls('item_parseDescriptor')), 3)
            self.assertEqual(self.calls('Player_blockSparks'), [(PLAYER, 0)])
            self.assertEqual(self.mem.load(ARROW + 0xCC, 1), 0)             # no hit state: still touchable

    def test_player_owned_arrow_sticks(self):
        self.mem.poke(PLAYER + 0x3C8, 4, 0)
        self.build(owner=PLAYER)
        self.place(CREATURE, 5.0)
        self.world.present = [CREATURE]
        self.world.enemies = {CREATURE}
        self.world.get = lambda name, base=self.world.get: (lambda *a: 6) \
            if name == 'model_getSamplePointCount' else base(name)
        self.tick()
        self.assertTrue(self.calls('player_getSkillRank')[0][1] == 0x5D)       # Penetrating Arrows
        self.assertEqual(self.model.draws, 1 + 2 + 1)                           # ctor, two, deflection


class Destructors(Fixture):
    def test_lit_arrows(self):
        for fn, table in ((A.FIRE_DTOR, A.VT_FIRE_ARROW), (A.COLD_DTOR, A.VT_COLD_ARROW)):
            self.model.calls = []
            self.model.writes = []
            getattr(self.model, A.METHODS[fn])(ARROW, 3)
            self.assertEqual([c[0] for c in self.model.calls], ['light_dtor', 'GameObject_dtor', 'pool_free'])
            self.assertEqual(self.calls('light_dtor'), [(ARROW + 0x70, 2)])
            self.assertEqual([v for a, s, v in self.model.writes if a == ARROW + 0x48], [table, A.VT_PROJECTILE])

    def test_explode_arrow_has_no_light(self):
        self.model.explodearrow_dtor(ARROW, 1)
        self.assertEqual([c[0] for c in self.model.calls], ['GameObject_dtor', 'pool_free'])
        self.model.calls = []
        self.model.explodearrow_dtor(ARROW, 0)
        self.assertEqual([c[0] for c in self.model.calls], ['GameObject_dtor'])

    def test_missile_dtor_releases_every_handle(self):
        self.build()
        self.model.calls = []
        self.model.missile_dtor(ARROW, 3)
        self.assertEqual(self.mem.load(ARROW + 0x4C, 4), 0)
        self.assertEqual(self.mem.load(ARROW + 0x48, 4), A.VT_PROJECTILE)
        self.assertEqual([c[0] for c in self.model.calls], ['trail_release', 'light_dtor', 'GameObject_dtor',
                                                             'pool_free'])


class Tables(unittest.TestCase):
    def test_executed_and_class_bodies(self):
        self.assertEqual(A.EXECUTED['MissileWeapon_run'], 0x15153C)
        self.assertEqual(A.EXECUTED['ColdArrowProjectile_dtor'], 0x3CDF4C)
        for fn, (slot, method) in A.CLASS_BODIES.items():
            self.assertTrue(hasattr(A.Model, method), method)
            self.assertIn(slot, (1, 4, 6, 17))
        for start, end in A.BODIES.values():
            self.assertLess(start, end)


if __name__ == '__main__':
    unittest.main()
