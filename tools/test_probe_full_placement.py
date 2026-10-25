#!/usr/bin/env python3
"""Synthetic tests of tools/probe_full_placement.py: its tables and its bookkeeping.
No game file is needed; the probe itself is run by hand (docs/spec/full-placement.md)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import probe_full_placement as P                # noqa: E402


class Tables(unittest.TestCase):
    def test_placements_are_the_native_fixture(self):
        self.assertEqual(P.PLACEMENTS['round5'], {'antqueen': (0, 140), 'skeleton': (70, 140),
                                                  'soul': (-70, 140)})
        self.assertEqual(P.PLACEMENTS['native']['soul'], (-60, 100))
        self.assertEqual(P.SKELIGHTS, (((80, 0), 0x8000), ((-40, 0), 0)))
        self.assertEqual((P.FACING, P.HP), (0xC000, 120.0))

    def test_service_recorded_and_unexecuted_are_disjoint(self):
        self.assertFalse(P.SERVICES & P.RECORDED)
        for name in ('Creature.v20', 'Creature.v0', 'Skeleton_shatter', 'AntQueen_pickFlyDest',
                     'GutChunk_ctor', 'Creature_setCharm', 'Holder.v2', 'Holder.v3', 'Holder.v4'):
            self.assertNotIn(name, P.SERVICES)
            self.assertNotIn(name, P.RECORDED)

    def test_executed_bodies_hold_the_known_entries(self):
        ex = P.executed_bodies()
        for addr in (0x119328, 0x10DED0, 0x236C70, 0x237918, 0x2A5AF4, 0x2A7768, 0x2A9478, 0x1E8230):
            self.assertTrue(addr in ex, hex(addr))
        for addr in RC_RUNS:
            self.assertIn(addr, P.RUN_SWITCHES_ENTRIES)

    def test_round5_bodies_are_executed_and_not_services(self):
        ex = P.executed_bodies()
        for addr in (0x1682F0, 0x167A58, 0x164330, 0x166550,            # the rigid body
                     0x118950, 0x201BD8,                                # a cold arrow's hit, an explosion's light
                     0x2C5240, 0x2C5814, 0x2C6AA8):                     # StaticFire_ctor and what it runs
            self.assertIn(addr, ex, hex(addr))
        for name in ('rigidbody_init', 'quat_fromMat3', 'rigidbody_updateDerived', 'StaticFire_ctor',
                     'Creature_setEffectTimer', 'LightEffect_ctor'):
            self.assertNotIn(name, P.SERVICES)
        for name in ('terrain_sweepCircle', 'path_blockNodes', 'obj_addToAlwaysDraw', 'mem_allocTagged'):
            self.assertIn(name, P.SERVICES)

    def test_run_states_executed(self):
        self.assertTrue({0, 1} <= P.RUN_STATES_EXECUTED['Skeleton_run'])
        self.assertEqual(P.RUN_STATES_EXECUTED['AntQueen_run'], set(range(0x1A)))
        self.assertEqual(P.RUN_STATES_EXECUTED['Soul_run'], set(range(0x23)))    # tools/difftest_soul_run.py
        self.assertIn(0x155A0C, P.executed_bodies())                            # PhProp_ctor, ref_phprop


RC_RUNS = (0x236F78, 0x2A6864, 0x2A9870)
P.RUN_SWITCHES_ENTRIES = {entry for entry, _test in P.RUN_SWITCHES.values()}


class Bookkeeping(unittest.TestCase):
    def _probe(self, stop_first):
        probe = P.Probe.__new__(P.Probe)
        probe.stop_first, probe.first_seen, probe.events, probe.tick = stop_first, {}, [], 5
        return probe

    def test_first_unexecuted_stops(self):
        probe = self._probe(True)
        probe.note_stub('anim_push', probe.classify_name('anim_push'), ())
        probe.note_stub('Creature_init', probe.classify_name('Creature_init'), ())
        with self.assertRaises(P.Stop):
            probe.note_stub('Skeleton_shatter', probe.classify_name('Skeleton_shatter'), ())
        self.assertEqual(probe.first_seen['anim_push'], (5, 'service'))
        self.assertEqual(probe.first_seen['Creature_init'], (5, 'recorded'))
        self.assertEqual(probe.events, [(5, 'Skeleton_shatter')])

    def test_all_mode_keeps_going_and_keeps_the_first_tick(self):
        probe = self._probe(False)
        probe.note_stub('Creature.v20', 'unexecuted', ())
        probe.tick = 9
        probe.note_stub('Creature.v20', 'unexecuted', ())
        self.assertEqual(probe.first_seen['Creature.v20'], (5, 'unexecuted'))
        self.assertEqual(len(probe.events), 2)

    def test_pcs_map_to_their_function(self):
        probe = self._probe(False)
        probe.starts = [0x100000, 0x100100, 0x100200]
        self.assertEqual(probe._functions_run({0x100004, 0x1000FC, 0x100100, 0x100250}),
                         {0x100000, 0x100100, 0x100200})


class Round4(unittest.TestCase):
    """--clips, --run-objects, the box query (docs/spec/full-placement.md 7)."""

    def _probe(self):
        probe = P.Probe.__new__(P.Probe)
        probe.stop_first, probe.first_seen, probe.events, probe.tick = True, {}, [], 0
        probe.run_lists = {'frame': [], 15: [[] for _ in range(15)], 60: [[] for _ in range(60)]}
        probe.cursor = {15: 0, 60: 0}
        probe.where, probe.delete_list = {}, []
        return probe

    def test_anim_bodies_are_only_added_with_clips(self):
        self.assertNotIn(0x16D748, P.executed_bodies())        # anim_advance: the clip clock answers
        self.assertIn(0x16D748, P.ANIM_BODIES)
        self.assertIn(0x1162B0, P.ANIM_BODIES)                  # Creature_stepAnim
        self.assertNotIn(P.ANIMSOUND_FIRE_RANGE, P.ANIM_BODIES)  # sounds stay presentation
        for name in ('sound_playHit', 'light_link', 'light_unlink', 'trail_create'):
            self.assertIn(name, P.SERVICES)
        self.assertIn(0x27DD68, P.executed_bodies())            # jumpgate_getTravelState

    def test_run_lists_follow_the_object_system(self):
        probe = self._probe()
        probe.link(0xA0, 'frame')
        probe.link(0xB0, 'frame')
        self.assertEqual(probe.run_lists['frame'], [0xB0, 0xA0])   # the newest runs first
        probe.link(0xA0, 60)                                        # the cursor steps first: list 1
        self.assertEqual(probe.run_lists['frame'], [0xB0])
        self.assertEqual(probe.run_lists[60][1], [0xA0])
        probe.link(0xC0, 60)
        self.assertEqual(probe.run_lists[60][2], [0xC0])
        probe.unlink(0xC0)
        self.assertEqual(probe.run_lists[60][2], [])
        self.assertNotIn(0xC0, probe.where)
        probe.link(0xB0, 'frame')                                   # again: to the front, once
        self.assertEqual(probe.run_lists['frame'], [0xB0])

    def test_box_query_uses_radius_and_height(self):
        mem = {}

        class View:
            def load(self, addr, size=4, signed=False):
                return mem.get(addr, 0)

        def put(obj, x, y, z, radius, height, flags=0):
            for off, v in ((0x10, x), (0x14, y), (0x18, z), (0x1C, radius), (0x20, height)):
                mem[obj + off] = P.f32(v)
            mem[obj + 0xC] = flags
        put(0x1000, 0.0, 0.0, 0.0, 16.0, 72.0)          # the player: z 0 .. 72
        put(0x2000, 30.0, 0.0, 0.0, 12.0, 72.0)
        put(0x3000, 0.0, 5.0, 0.0, 12.0, 72.0, flags=0x20000)   # a prediction copy
        world = P.World.__new__(P.World)
        world.probe = self._probe()
        world.probe.objects = [0x2000, 0x1000, 0x3000]
        box = lambda lo, hi: ([P.f32(v) for v in lo], [P.f32(v) for v in hi])
        lo, hi = box((-12.8, -11.0, 47.7), (11.2, 13.0, 47.7))     # an arrow at chest height
        self.assertEqual(world.on_world_collectObjectsInBox((lo, hi, 0x10), View(), None).outs[0], [0x1000])
        lo, hi = box((-12.8, -11.0, 80.0), (11.2, 13.0, 90.0))     # above the head
        self.assertEqual(world.on_world_collectObjectsInBox((lo, hi, 0x10), View(), None).outs[0], [])
        lo, hi = box((-50.0, -50.0, 0.0), (50.0, 50.0, 10.0))      # both; at most limit - 1
        self.assertEqual(world.on_world_collectObjectsInBox((lo, hi, 0x10), View(), None).outs[0],
                         [0x2000, 0x1000])
        self.assertEqual(world.on_world_collectObjectsInBox((lo, hi, 2), View(), None).outs[0], [0x2000])

    def test_disc_clips_from_a_lump_directory(self):
        import struct
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            names, blobs = [b'a.anm\0', b'b.mdl\0'], [b'\x01\x02\x03', b'zz']
            head = 4 + 12 * len(names)
            body, recs = b'', []
            for name, blob in zip(names, blobs):
                name_off = head + len(body)
                body += name
                recs.append((name_off, head + len(body), len(blob)))
                body += blob
            data = struct.pack('<I', len(names)) + b''.join(struct.pack('<III', *r) for r in recs) + body
            with open(os.path.join(d, 'TEST.LMP'), 'wb') as f:
                f.write(data)
            disc = P.DiscClips(d)
            self.assertEqual(disc.clip('test.lmp', 'A.ANM'), b'\x01\x02\x03')
            self.assertIsNone(disc.clip('test.lmp', 'c.anm'))
            self.assertIsNone(disc.clip('none.lmp', 'a.anm'))


if __name__ == '__main__':
    unittest.main()
