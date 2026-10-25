#!/usr/bin/env python3
"""Unit tests for tools/ref_horsemen_mount.py that need no game files (they build the few
tables the model reads in a blank memory image).  The comparison with the game's own code
is tools/difftest_horsemen_mount.py.

    python3 -m unittest discover -s tools -p 'test_ref_horsemen_mount.py'
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_horsemen_mount as HM                 # noqa: E402
import ref_horsemen_props as HP                 # noqa: E402

RIDER, MOUNT, PLAYERS, DEF, NODES = 0x10000, 0x11000, 0x12000, 0x20000, 0x70000
NODE_RIDER, NODE_MOUNT = NODES, NODES + 0x20


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw))[0]


class Rig:
    """A blank memory with a Horsemen rider and a Nightmare mount, both tables, one class
    definition, four player objects and a node per object for the handles."""

    def __init__(self, answers=None, linked=True):
        self.mem = RC.Memory()
        poke = self.poke = self.mem.poke
        bodies = {AM.VT_HORSEMEN: {4: 0x27236C, 5: 0x2721F8, 27: 0x272F4C},
                  HM.VT_NIGHTMARE: {4: 0x270BBC, 5: 0x270B4C, 10: 0x27142C, 11: 0x271484, 27: 0x27155C}}
        for vt, own in bodies.items():
            for slot in range(1, 40):
                fn = own.get(slot)
                if fn is None and slot in RC.BASE_BODIES and slot not in (10, 11):
                    fn = RC.BASE_BODIES[slot][0]
                if fn is None:
                    fn = {16: 0x3C2738, 25: 0x10E658, 28: 0x10BEB8, 34: 0x3C2708}.get(slot, 0x00F00000 + slot)
                poke(vt + 8 * slot + 4, 4, fn)
        for k in range(1, 0x1C):
            poke(DEF + 8 * k + 4, 4, 0x60000 + 0x40 * k)
        for obj, vt, node in ((RIDER, AM.VT_HORSEMEN, NODE_RIDER), (MOUNT, HM.VT_NIGHTMARE, NODE_MOUNT)):
            poke(obj + 0xC, 4, 0x20)
            poke(obj + 0x24, 4, DEF)
            poke(obj + 0x48, 4, vt)
            poke(obj + 0x44, 4, 12345)
            poke(node + 0xC, 4, obj)
        if linked:
            poke(RIDER + 0x3C8, 4, NODE_MOUNT)
            poke(MOUNT + 0x3C8, 4, NODE_RIDER)
        self.players = [PLAYERS + 0x400 * i for i in range(4)]
        poke(RC.G_NUM_PLAYERS, 4, 4)
        for slot, p in enumerate(self.players):
            poke(p + 0xC, 4, 0x40)
            poke(RC.G_PLAYERS + slot * RC.REC_SIZE + RC.REC_OBJ, 4, p)
        self.answers = dict(answers or {})
        self.model = HM.Model(self.mem, self)

    def get(self, name):
        value = self.answers.get(name)
        if value is None:
            return None
        if callable(value):
            return value
        return lambda *args: value

    def names(self):
        return [name for name, _args in self.model.calls]

    def args_of(self, name):
        return [args for n, args in self.model.calls if n == name]

    def state(self, obj):
        return self.mem.load(obj + 0x232, 2)


class MountLink(unittest.TestCase):
    def test_mount_death_dismounts_the_rider_and_drops_both_links(self):
        rig = Rig()
        rig.poke(RIDER + 0x18, 4, f32(10.0))
        rig.model.nightmare_set_state(MOUNT, 0x14)
        self.assertEqual(rig.state(MOUNT), 0x14)
        self.assertEqual(rig.state(RIDER), 0x23)
        self.assertEqual(rig.mem.load(RIDER + 0x3C8, 4), 0)
        self.assertEqual(rig.mem.load(MOUNT + 0x3C8, 4), 0)
        self.assertEqual(fl(rig.mem.load(RIDER + 0x18, 4)), 58.0)    # lifted 48 units off the saddle
        self.assertEqual(rig.mem.load(MOUNT + 0xC, 4) & 0x4000, 0x4000)
        self.assertNotIn('Creature_dropLoot', rig.names())           # the mount drops nothing itself
        self.assertEqual(rig.args_of('handle_clear'), [(RIDER + 0x3C8,), (MOUNT + 0x3C8,)])

    def test_a_rider_timer_strands_the_rider_when_the_mount_dies(self):
        """The rider's Creature_filterState turns the 0x23 into a state below 0x19, which the
        mounted set-state ignores; the mount drops its own handle all the same."""
        for off, expect in ((0x31C, 0x1B), (0x314, 0x1B), (0x318, 0x1B)):
            rig = Rig()
            rig.poke(RIDER + 0x232, 2, 0x1B)
            rig.poke(RIDER + 0x234, 4, NODE_MOUNT)               # a target, so the cooldown stays
            rig.poke(RIDER + off, 2, 30)
            rig.model.nightmare_set_state(MOUNT, 0x14)
            self.assertEqual(rig.state(RIDER), expect, hex(off))
            self.assertEqual(rig.mem.load(RIDER + 0x3C8, 4), NODE_MOUNT, hex(off))     # still linked
            self.assertEqual(rig.mem.load(MOUNT + 0x3C8, 4), 0)                        # mount let go
            self.assertEqual(rig.state(MOUNT), 0x14)

    def test_every_mount_state_pushes_its_rider_state(self):
        pushes = {0: 0x1B, 5: 0x1B, 0x12: 0x1B, 0x13: 0x1B, 1: 0x1C, 3: 0x1C, 7: 0x1D, 0x10: 0x1D,
                  6: 0x1E, 0x17: 0x1E, 0x18: 0x1F, 0x19: 0x19, 0x1A: 0x1A}
        for mount_state, rider_state in pushes.items():
            rig = Rig()
            rig.poke(RIDER + 0x232, 2, 0x1B)
            rig.model.nightmare_set_state(MOUNT, mount_state)
            self.assertEqual(rig.state(RIDER), rider_state, hex(mount_state))
        for quiet in (2, 4, 9, 0xF, 0x11, 0x15, 0x16, 0x1B, 0x40):
            rig = Rig()
            rig.poke(RIDER + 0x232, 2, 0x1C)
            rig.model.nightmare_set_state(MOUNT, quiet)
            self.assertEqual(rig.state(RIDER), 0x1C, hex(quiet))
            self.assertEqual(rig.state(MOUNT), quiet & 0xFFFF)

    def test_state_8_picks_one_of_three_rider_swings_from_the_mounts_own_generator(self):
        for seed in (1, 2, 3, 12345, 0xFFFFFFFF):
            rig = Rig()
            rig.poke(MOUNT + 0x44, 4, seed)
            expected = 0x20 + (((seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) >> 16) % 3
            rig.model.nightmare_set_state(MOUNT, 8)
            self.assertEqual(rig.state(RIDER), expected)
            self.assertEqual(rig.state(MOUNT), 8)
            self.assertEqual(rig.model.draws, 0)                    # no shared-seed draw
        rig = Rig(linked=False)
        rig.model.nightmare_set_state(MOUNT, 8)
        self.assertEqual(rig.state(MOUNT), 8)
        self.assertEqual(rig.names(), [])

    def test_a_hit_reaction_keeps_the_mounts_state(self):
        rig = Rig()
        rig.poke(MOUNT + 0x232, 2, 7)
        rig.model.nightmare_set_state(MOUNT, 0x12)
        self.assertEqual(rig.state(MOUNT), 7)
        self.assertEqual(rig.state(RIDER), 0x1B)

    def test_the_rider_copies_the_mount_and_takes_its_target(self):
        rig = Rig()
        for i, v in enumerate((100.0, 200.0, 5.0)):
            rig.poke(MOUNT + 0x10 + 4 * i, 4, f32(v))
        rig.poke(MOUNT + 0x38, 2, 0x1234)
        rig.poke(NODES + 0x40 + 0xC, 4, rig.players[2])
        rig.poke(MOUNT + 0x234, 4, NODES + 0x40)
        rig.poke(RIDER + 0x232, 2, 0x1B)
        rig.model.horsemen_run(RIDER)
        self.assertEqual([fl(rig.mem.load(RIDER + 0x10 + 4 * i, 4)) for i in range(3)], [100.0, 200.0, 5.0])
        self.assertEqual(rig.mem.load(RIDER + 0x38, 2), 0x1234)
        self.assertIn(('handle_link', (RIDER + 0x234, rig.players[2], rig.players[2])), rig.model.calls)
        self.assertNotIn('Creature_applyKnockback', rig.names())


class Construction(unittest.TestCase):
    def test_mount_property_reference_addresses_and_values(self):
        self.assertEqual([p.list_addr for p in HP.MOUNT_PROPERTIES],
                         [HM.MOUNT_PROPS + 12 * v for v in range(4)])
        self.assertEqual([p.name for p in HP.MOUNT_PROPERTIES],
                         [b'horsedisease', b'horsewar', b'horsepestilence', b'horsedeath'])
        self.assertTrue(all(p.miniboss == 1 and p.miniboss_text_addr == 0x547320
                            and p.terminator_addr == p.list_addr + 8
                            for p in HP.MOUNT_PROPERTIES))

    def test_mounted_horsemen_builds_a_nightmare_with_the_variants_property_list(self):
        def link(head, obj, _again):
            rig.poke(head, 4, {RIDER: NODE_RIDER, MOUNT: NODE_MOUNT}[obj])
        rig = Rig(linked=False, answers={'pool_new': MOUNT, 'handle_link': link})
        rig.model.horsemen_ctor(RIDER, 0, (0, 0, 0), 0, 0x9000, 2, 1)
        ctor = [args for name, args in rig.model.calls if name == 'GameObject_ctor']
        self.assertEqual(ctor[1], (MOUNT, (0, 0, 0), HM.DEF_NIGHTMARE, HM.MOUNT_PROPS + 24))
        self.assertEqual(rig.mem.load(MOUNT + 0x48, 4), HM.VT_NIGHTMARE)
        self.assertEqual(rig.mem.load(RIDER + 0x3C8, 4), NODE_MOUNT)
        self.assertEqual(rig.mem.load(MOUNT + 0x3C8, 4), NODE_RIDER)
        self.assertEqual(rig.state(RIDER), 0x1B)
        self.assertEqual(rig.state(MOUNT), 0)
        self.assertEqual(rig.mem.load(RIDER + 0xC, 4) & 9, 9)        # rider: not solid, not a target
        self.assertEqual(rig.args_of('pool_new'), [(0x3D8,)])
        self.assertEqual(rig.names()[-1], 'Creature_init')

    def test_constructor_constants(self):
        rig = Rig(linked=False)
        rig.model.nightmare_ctor(MOUNT, 0, (0, 0, 0), 0xFFFF8000, 0)
        load = rig.mem.load
        self.assertEqual(fl(load(MOUNT + 0x1C, 4)), 30.0)
        self.assertEqual(load(MOUNT + 0xB0, 4), HM.F_0_6)
        self.assertEqual(fl(load(MOUNT + 0x3C0, 4)), 2400.0)
        self.assertEqual(load(MOUNT + 0x3AE, 2), 2400)
        self.assertEqual(fl(load(MOUNT + 0xE0, 4)), -20.0)
        self.assertEqual(load(MOUNT + 0xB4, 1), 10)
        self.assertEqual(load(MOUNT + 0x28, 1), 50)
        self.assertEqual(load(MOUNT + 0xA8, 8) & 0x20200040000, 0x20200040000)
        self.assertEqual(load(MOUNT + 0x38, 2), 0x8000)
        self.assertEqual(rig.state(MOUNT), 0)
        params = [a for a in rig.model.calls if a[0] == 'anim_push']
        self.assertEqual(params, [('anim_push', (MOUNT + 0x114, 0x60000 + 0x40 * 3, 1))])
        self.assertEqual(rig.mem.load(0x60000 + 0x40 * 8 + 0x18, 1), 1)
        self.assertEqual(rig.mem.load(0x60000 + 0x40 * 8 + 0x30, 1), 4)


class Charge(unittest.TestCase):
    def test_the_first_player_in_open_ground_becomes_the_target(self):
        answers = iter([0.5] + [-1.0] * 8)          # player 0: blocked at once; player 1: eight misses
        rig = Rig(answers={'terrain_raycast': lambda *a: f32(next(answers))})
        self.assertEqual(rig.model.nightmare_pick_charge_target(MOUNT), 1)
        self.assertEqual(len(rig.args_of('terrain_raycast')), 9)
        self.assertEqual(rig.args_of('handle_link'), [(MOUNT + 0x234, rig.players[1], rig.players[1])])
        directions = [args[2] for args in rig.args_of('terrain_raycast')[1:]]
        self.assertEqual(fl(directions[0][0]), 360.0)
        self.assertEqual(fl(directions[2][1]), 360.0)              # 0x4000 is a quarter turn

    def test_hits_at_zero_or_one_do_not_count(self):
        rig = Rig(answers={'terrain_raycast': f32(1.0)})
        self.assertEqual(rig.model.nightmare_pick_charge_target(MOUNT), 1)
        rig = Rig(answers={'terrain_raycast': f32(0.999)})
        self.assertEqual(rig.model.nightmare_pick_charge_target(MOUNT), 0)
        self.assertEqual(len(rig.args_of('terrain_raycast')), 4)  # one probe per player

    def test_dead_players_are_skipped(self):
        rig = Rig(answers={'terrain_raycast': f32(-1.0)})
        for p in rig.players[:3]:
            rig.poke(p + 0xC, 4, 0x48)
        self.assertEqual(rig.model.nightmare_pick_charge_target(MOUNT), 1)
        self.assertEqual(rig.args_of('handle_link')[0][1], rig.players[3])

    def test_trampling_hits_only_players_outside_a_knockdown(self):
        rig = Rig(answers={'creature_inKnockdownAnim': lambda obj: 1 if obj == rig.players[1] else 0})
        rig.poke(MOUNT + 0x232, 2, 7)
        rig.poke(MOUNT + 0xD0, 2, 30)
        rig.poke(MOUNT + 0xD2, 2, 0xFFFB)
        rig.poke(MOUNT + 0x300, 4, 1000)
        rig.poke(0x13000 + 0xC, 4, 0x20)
        rig.model.nightmare_on_touch_list(MOUNT, (rig.players[0], rig.players[1], 0x13000))
        hits = rig.args_of('damage_apply')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][:6], (rig.players[0], MOUNT, 100000, 0, 0, 0x100041))
        self.assertEqual((fl(hits[0][8]), fl(hits[0][9])), (60.0, -10.0))
        self.assertEqual(rig.mem.load(MOUNT + 0x3D0, 4), 1120)
        self.assertEqual(rig.mem.load(MOUNT + 0xC, 4) & 1, 1)
        rig2 = Rig()
        rig2.model.nightmare_on_touch_list(MOUNT, (rig2.players[0],))
        self.assertEqual(rig2.names(), [])                         # not charging: nothing


class Death(unittest.TestCase):
    def test_the_dead_mount_gallops_off_and_is_deleted_after_100_ticks(self):
        rig = Rig(linked=False)
        rig.poke(MOUNT + 0x232, 2, 0x14)
        rig.poke(MOUNT + 0x3CC, 2, 98)
        rig.poke(MOUNT + 0x38, 2, 0)
        rig.model.nightmare_run(MOUNT)
        self.assertAlmostEqual(fl(rig.mem.load(MOUNT + 0x10, 4)), 11.666666, places=5)
        self.assertEqual(rig.mem.load(MOUNT + 0x3CC, 2), 99)
        self.assertNotIn('obj_delete', rig.names())
        rig.model.nightmare_run(MOUNT)
        self.assertEqual(rig.mem.load(MOUNT + 0x3CC, 2), 100)
        self.assertIn(('obj_delete', (MOUNT,)), rig.model.calls)
        self.assertEqual(rig.mem.load(MOUNT + 0xC, 4) & 0x4002, 0x4002)


if __name__ == '__main__':
    unittest.main()
