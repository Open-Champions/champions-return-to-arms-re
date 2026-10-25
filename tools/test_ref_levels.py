#!/usr/bin/env python3
"""Unit tests of tools/ref_levels.py on synthetic fixtures only.

No game file is read: level names are short identifiers the executable compares against,
and every table, record list, piece and water tile is built here.  The tests check the
model's own logic against the rules written in docs/level-flow.md; nothing here proves
that the model matches the game.

  python3 -m unittest discover -s tools -p 'test_ref_levels.py'

Run it from the repository root as above.  With tools/ as the current directory,
`python3 -m unittest test_ref_levels` fails before any test runs: the current directory is
first on sys.path, so `import inspect` inside unittest picks up tools/dis.py instead of the
standard library's dis (AttributeError: COMPILER_FLAG_NAMES).  Appending tools/ below does
not help there.  Proposed fix, not applied in this branch because 24 tracked files name the
script: `git mv tools/dis.py tools/eedis.py` and update those references (no module
imports it).  docs/level-flow.md 16.6.
"""
import math
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_core as C                            # noqa: E402
import ref_levels as L                          # noqa: E402
import ref_objects as Obj                       # noqa: E402
import ref_world as W                           # noqa: E402

F = W.f32


def rec(cls, *props, x=0.0, y=0.0, z=0.0, angle=0):
    return L.Record(cls, angle, x, y, z, props)


class Names(unittest.TestCase):
    def test_split_at_first_underscore(self):
        self.assertEqual(L.split_request('alpha_beta_gamma'), ('alpha', 'beta_gamma'))
        self.assertEqual(L.split_request('alpha'), ('alpha', ''))
        self.assertEqual(L.qualified_name('alpha', ''), 'alpha')
        self.assertEqual(L.qualified_name('alpha', 'b'), 'alpha_b')

    def test_loading_picture_is_cut_to_eight_characters(self):
        self.assertEqual(L.loading_picture_files('abcdefghij'), ['labcdefg.lmp', 'lmiss.lmp'])
        self.assertEqual(L.loading_picture_files('ab'), ['lab.lmp', 'lmiss.lmp'])

    def test_loading_picture_aliases(self):
        self.assertEqual(L.loading_picture_alias('xbloy'), 'blood1')        # substring rule
        self.assertEqual(L.loading_picture_alias('tormentb'), 'tormb')
        self.assertEqual(L.loading_picture_alias('tormentq'), 'tormentq')  # contains, no key
        self.assertEqual(L.loading_picture_alias('nitdung2'), 'nitdun2')
        self.assertEqual(L.loading_picture_alias('plain'), 'plain')
        self.assertEqual(L.cd_file_name('lab.lmp'), 'LAB.LMP;1')


class LevelTable(unittest.TestCase):
    rows = [L.LevelRow('aa2', monster_level=5), L.LevelRow('aa', monster_level=1),
            L.LevelRow('aa_x', monster_level=9), L.LevelRow('zz', monster_level=3)]

    def test_exact_with_sub_first(self):
        self.assertEqual(L.find_level_row(self.rows, 'aa', 'x').monster_level, 9)

    def test_plain_name_takes_first_prefix_row_in_table_order(self):
        # pass 1 compares 'aa_' and fails; pass 2: 'aa2' starts with 'aa' and comes first
        self.assertEqual(L.find_level_row(self.rows, 'aa', '').name, 'aa2')

    def test_substring_pass_and_default(self):
        self.assertEqual(L.find_level_row(self.rows, 'xzzx', '').name, 'zz')
        self.assertIs(L.find_level_row(self.rows, 'qq', ''), L.DEFAULT_ROW)
        self.assertEqual(L.DEFAULT_ROW.water_pool, 48)
        self.assertEqual(L.DEFAULT_ROW.kill_plane, -100000.0)

    def test_monster_level_store_order(self):
        row = L.LevelRow('aa', monster_level=4)
        self.assertEqual(L.monster_level(row, 1, 'aa'), 6.0)
        self.assertEqual(L.monster_level(row, 1, 'aa', pvp_mode_b=True), 3.0)
        self.assertEqual(L.monster_level(row, 3, 'aa', pvp_mode_b=True), 6 * 0.75 + 61)
        self.assertEqual(L.monster_level(row, 5, 'stomedal'), 1.0)

    def test_level_light_alpha_later_test_wins(self):
        self.assertEqual(L.level_light_alpha(0), 0x80)
        self.assertEqual(L.level_light_alpha(L.LEVEL_FLAG_LIGHT_20), 0x20)
        self.assertEqual(L.level_light_alpha(L.LEVEL_FLAG_LIGHT_20 | L.LEVEL_FLAG_LIGHT_40), 0x40)


class Manifest(unittest.TestCase):
    disc = ['FX.LMP', 'HUD.LMP', 'MAPICONS.LMP', 'ICONS.LMP', 'LOADMISC.LMP', 'GOODDOG.LMP',
            'SKELE_B.LMP', 'LEVA.LMP', 'LEVA.GOB', 'LEVA.TEX', 'TREE.LMP']
    gob = ['leva.lmp', 'env.lmp', 'waterenv.lmp']
    entries = ['leva.world', 'objects.ob', 'script.scr']

    def manifest(self, **kw):
        args = dict(gob_lumps=self.gob, level_entries=self.entries, disc_files=self.disc)
        args.update(kw)
        return L.level_manifest('leva', **args)

    def test_order_and_kinds(self):
        m = self.manifest(model_lumps=['tree'])
        names = [r.name for r in m]
        self.assertLess(names.index('leva.gob'), names.index('leva.world'))
        self.assertLess(names.index('tree.lmp'), names.index('waterenv.lmp'))
        self.assertLess(names.index('waterenv.lmp'), names.index('objects.ob'))
        self.assertIn('leva.lmp'[:8], [r.name[:8] for r in m])          # loading picture found
        req = {r.name: r.required for r in m}
        self.assertTrue(req['leva.tex'])
        self.assertFalse(req['ambient.bin'])
        self.assertFalse(req['dome.lmp'])

    def test_missing_required_is_fatal(self):
        with self.assertRaises(L.MissingResource):
            self.manifest(disc_files=[d for d in self.disc if d != 'LEVA.TEX'])
        with self.assertRaises(L.MissingResource):
            self.manifest(gob_lumps=['leva.lmp', 'env.lmp'])             # no waterenv.lmp
        with self.assertRaises(L.MissingResource):
            self.manifest(model_lumps=['absent'])

    def test_picture_fallback_and_recall_leg(self):
        m = self.manifest(disc_files=[d for d in self.disc if d != 'LEVA.LMP'], recall_leg=True)
        names = [r.name for r in m]
        self.assertIn('lmiss.lmp', names)
        self.assertNotIn('dialog.bin', names)

    def test_gob_offsets_ignore_the_directory(self):
        out = L.gob_lump_offsets([('a.lmp', 0x10), ('gaydark1.lmp', 0x801), ('c.lmp', 1)])
        self.assertEqual(out, [('a.lmp', 0x800, 0x10), ('faydark1.lmp', 0x1000, 0x801),
                               ('c.lmp', 0x2000, 1)])


class Objects(unittest.TestCase):
    def test_round_trip(self):
        blob = L.build_objects([('Player1', 100, 1.5, -2.0, 3.0, ['from=leva', 'default=1']),
                                ('Trigger', 0, 0.0, 0.0, 0.0, ['w=10', 'h=4', 't=go'])])
        rs = L.parse_objects(blob)
        self.assertEqual([r.cls for r in rs], ['Player1', 'Trigger'])
        self.assertEqual(rs[0].prop('from'), 'leva')
        self.assertEqual(rs[0].angle, 100)
        self.assertEqual((rs[0].x, rs[0].y, rs[0].z), (1.5, -2.0, 3.0))
        self.assertIsNone(rs[0].prop('name'))

    def test_save_filter(self):
        self.assertTrue(L.save_filter_admits('torch'))
        self.assertFalse(L.save_filter_admits('Player1'))


class Markers(unittest.TestCase):
    def decide(self, rank, *props, prev='', entrance='', recall=False):
        return L.marker_decision(rank, rec('Player1', *props), prev, entrance, recall)

    def test_rank_table(self):
        self.assertEqual(self.decide(0), (True, 1))
        self.assertEqual(self.decide(1), (False, 1))
        self.assertEqual(self.decide(1, 'default=1'), (True, 1))
        self.assertEqual(self.decide(1, 'defualt=1'), (False, 1))       # misspelt key
        self.assertEqual(self.decide(1, 'from=old', prev='old'), (True, 2))
        self.assertEqual(self.decide(2, 'default=1'), (False, 2))
        self.assertEqual(self.decide(1, 'from=old', prev='old', recall=True), (False, 1))
        self.assertEqual(self.decide(1, 'from=gate', recall=True), (True, 3))
        self.assertEqual(self.decide(2, 'name=door', entrance='door'), (True, 3))
        self.assertEqual(self.decide(2, 'name=door', entrance='door', recall=True), (False, 2))
        self.assertEqual(self.decide(3, 'name=door', entrance='door'), (False, 3))

    def run_case(self, records, **kw):
        calls = []

        def spot(centre, spread, radius, any_height):
            calls.append((centre, spread, radius, any_height))
            return (centre[0] + len(calls), centre[1], centre[2])

        draws = iter(range(1000, 2000))
        spawn = L.SpawnState()
        took = L.run_markers(spawn, records, kw.pop('prev', ''), kw.pop('entrance', ''),
                             kw.pop('recall', False), spot, lambda: next(draws), **kw)
        return spawn, took, calls

    def test_last_default_wins_first_rank3_wins(self):
        rs = [rec('Player1', x=1), rec('Player1', 'default=1', x=2), rec('Player1', 'default=1', x=3),
              rec('Player1', 'name=e', x=4), rec('Player1', 'name=e', x=5)]
        spawn, took, calls = self.run_case(rs, entrance='e')
        self.assertEqual(took, [0, 1, 2, 3])
        self.assertEqual(spawn.rank, 3)
        self.assertEqual(len(calls), 16)                     # four searches per taking marker
        self.assertEqual(calls[-1][0][0], 4)                 # marker 3 decided the slots
        self.assertTrue(all(c[1:] == (36, 24, False) for c in calls))

    def test_facing_spread(self):
        spawn, _t, _c = self.run_case([rec('Player1', angle=10)])
        self.assertEqual(spawn.facing[0], (10 + 1000 % 4000 - 2000) & 0xFFFF)

    def test_save_load_blocks_markers_and_gate_arrival_overrides(self):
        spawn, took, _c = self.run_case([rec('Player1')], loaded_from_save=True)
        self.assertEqual(took, [])
        spawn, took, calls = self.run_case([rec('Player1'), rec('Portal', x=9), rec('Player1')],
                                           gate_arrival=True, num_players=2)
        self.assertEqual(took, [0, 1])
        self.assertEqual(spawn.rank, 3)
        self.assertEqual([c[3] for c in calls[4:]], [True, True])   # gate: any height, 2 slots

    def test_no_marker_keeps_previous_values(self):
        spawn = L.SpawnState()
        spawn.pos[0] = [5.0, 6.0, 7.0]
        L.run_markers(spawn, [rec('Lantern')], '', '', False, None, None)
        self.assertEqual(spawn.pos[0], [5.0, 6.0, 7.0])
        self.assertEqual(spawn.rank, 0)

    def test_placement(self):
        spawn = L.SpawnState()
        spawn.pos = [[0.0, 0.0, 99.0] for _ in range(4)]
        spawn.facing = [100, 100, 100, 100]
        spawn.rank = 1
        heights = []

        def height(radius, pos):
            heights.append(radius)
            return 4.0

        def spot(c, spread, radius, any_height):
            self.assertEqual((spread, radius, any_height), (36, 14, False))
            return (c[0] + 1.0, c[1], c[2])

        built = L.place_players(spawn, 3, height, spot, alive=lambda s: s != 1,
                                restore_xy=[(7.0, 8.0, 0.0)] * 4)
        self.assertEqual(built, [0, 2])
        self.assertEqual(spawn.pos[0], [7.0, 8.0, 4.0])      # z from terrain, not the marker
        self.assertEqual(spawn.pos[1][0], 8.0)               # scattered and written back
        self.assertEqual(spawn.facing, [100, 8100, 8100, 100])
        self.assertTrue(all(r == 12.0 for r in heights))
        spawn.rank = 3
        L.place_players(spawn, 2, height, spot)
        self.assertEqual(spawn.facing[1], 8100)              # rank 3: no second scatter

    def test_placement_medal_and_pvp(self):
        spawn = L.SpawnState()
        spawn.rank = 3
        h = lambda r, p: 0.0                                 # noqa: E731
        self.assertEqual(L.place_players(spawn, 4, h, None, medal_slot=2), [2])
        self.assertEqual(L.place_players(spawn, 4, h, None, pvp_mode_b=True), [])


class Requests(unittest.TestCase):
    def test_orientation(self):
        self.assertEqual(L.orientation_from_props(None), 0xFF)
        self.assertEqual(L.orientation_from_props(['orientation=3', 'orientation=7']), 7)
        self.assertEqual(L.orientation_from_props(['Orientation=3']), 0xFF)

    def test_buffer_limit(self):
        p = L.Pending()
        p.request('a' * 0x4F)
        with self.assertRaises(ValueError):
            p.request('a' * 0x50)

    def test_net_gate(self):
        self.assertEqual(L.new_world_gate(False, 0, 5, 3), (False, 5))
        self.assertEqual(L.new_world_gate(True, 0, 0, 3), (False, 600))
        self.assertEqual(L.new_world_gate(True, 0, 5, 3), (True, 5))
        self.assertEqual(L.new_world_gate(True, 0, 5, 1), (False, 600))
        self.assertEqual(L.new_world_gate(True, 0, 5, 3, in_post_action=True), (False, 5))

    def test_cancel(self):
        self.assertTrue(L.cancel_pending(True, False, False, False, False))
        self.assertFalse(L.cancel_pending(True, False, True, False, False))
        self.assertFalse(L.cancel_pending(True, False, False, False, True))


ACTS = [[('hub', 100), ('aa', 50), ('aab', 50)], [('hub', 100), ('bb', 70)]]


class Acts(unittest.TestCase):
    def test_find_act_prefix_current_first(self):
        names = [[r for r, _s in a] for a in ACTS]
        self.assertEqual(L.find_act(names, 'bb', -1), 1)
        self.assertEqual(L.find_act(names, 'hub2', 1), 1)       # 'hub' prefix, current act first
        self.assertEqual(L.find_act(names, 'hub2', -1), 0)
        self.assertEqual(L.find_act(names, 'qq', 0), -1)
        self.assertEqual(L.act_changed(names, 'qq', 0), (False, 0))
        self.assertEqual(L.act_changed(names, 'bb', 0), (True, 1))

    def test_level_states(self):
        s = L.LevelStates()
        self.assertTrue(s.store('aa', ACTS[0], blob=b'1'))
        self.assertTrue(s.store('hub2', ACTS[0]))               # hub* uses row 0
        self.assertFalse(s.store('aa_x', ACTS[0]))              # qualified key not a row
        self.assertFalse(s.store('bb', ACTS[0]))                # not in the current act
        self.assertFalse(s.store('aa', ACTS[0], card_state=4))
        self.assertEqual(s.lookup('hub2'), (True, 50))

    def test_session_change(self):
        se = L.Session(ACTS)
        se.quest_values = {'q': 3}
        se.pending.request('aa', 0xFF)
        d = se.change()
        self.assertTrue(d['act_changed'])                       # act -1 -> 0
        self.assertEqual((se.level, se.prev, se.act), ('aa', '', 0))
        self.assertEqual(se.gates.names, ['hub'])
        self.assertEqual(se.pending.orientation, L.ORIENT_CONSUMED)
        se.entrance = 'door'
        se.pending.request('aab_s')
        d = se.change(store_blob=b'x')
        self.assertTrue(d['stored'])
        self.assertFalse(d['act_changed'])
        self.assertEqual((se.level, se.sub, se.prev), ('aab', 's', 'aa'))
        self.assertEqual(se.entrance, 'door')                   # not cleared by a change
        se.quest_values['q'] = 5
        se.pending.request('bb')
        d = se.change()
        self.assertTrue(d['act_changed'])
        self.assertEqual(se.quest_values, {'q': 0})
        self.assertEqual(se.states.entries, [])
        self.assertEqual(se.recall_dest, ['None'] * 4)


class Triggers(unittest.TestCase):
    def test_rectangle_and_edges(self):
        t = L.Trigger(10.0, 20.0, 5, 4, 'go')               # x 10..15, y 16..20
        self.assertTrue(t.contains(10.0, 16.0))
        self.assertTrue(t.contains(15.0, 20.0))
        self.assertFalse(t.contains(15.5, 18.0))
        self.assertFalse(t.contains(12.0, 21.0))
        self.assertEqual(t.run([None, (1, 12.0, 18.0), (2, 13.0, 18.0)]), ('go', 1))
        self.assertEqual(t.run([(0, 12.0, 18.0)]), (None, None))     # still inside: no edge
        self.assertEqual(t.run([(0, 0.0, 0.0)], recall_running=True), (None, None))
        self.assertEqual(t.run([(0, 0.0, 0.0)]), ('notgo', None))

    def test_negative_size(self):
        t = L.Trigger(0.0, 0.0, -5, -4, 'go')               # x -5..0, y 0..4
        self.assertTrue(t.contains(-5.0, 4.0))

    def test_push_trigger(self):
        self.assertTrue(L.push_trigger_allowed([]))
        self.assertFalse(L.push_trigger_allowed([1, 0, 1]))


class Gates(unittest.TestCase):
    def test_list(self):
        g = L.GateList()
        g.reset('hub')
        self.assertTrue(g.add_current('aa', 'hub'))
        self.assertFalse(g.add_current('aa', 'hub'))
        self.assertEqual(g.choosable('aa'), ['hub'])
        g.add_current('hub2', 'hub2')                       # stale 'hub' removed on append
        self.assertEqual(g.names, ['aa', 'hub2'])
        for i in range(13):
            g.add_current('l%d' % i, 'hub2')
        self.assertEqual(len(g.names), 15)
        with self.assertRaises(OverflowError):
            g.add_current('one-more', 'hub2')

    def test_prompt(self):
        self.assertEqual(L.gate_prompt(False, False, True, 1, []), (False, 'JumpGateVirgin', True))
        self.assertEqual(L.gate_prompt(True, False, True, 2, [96.0 ** 2]), (True, 'JumpGate', True))
        self.assertEqual(L.gate_prompt(True, False, True, 2, [97.0 ** 2])[1], 'JumpGateNeedPlayers')
        self.assertEqual(L.gate_prompt(False, True, True, 2, []), (False, None, False))


class Recall(unittest.TestCase):
    def test_round_trip(self):
        req, orient, to_hub, restore, dest, saved = L.recall_finish(
            'aa', 's', 2, [(1, 2, 3), (4, 5, 6)], ['None'] * 4, 'hub')
        self.assertEqual((req, orient, to_hub, restore), ('hub', 0xFD, True, None))
        self.assertEqual(dest, ['aa_s', 'aa_s', 'None', 'None'])
        req, orient, to_hub, restore, dest2, _ = L.recall_finish('hub', '', 2, saved, dest, 'hub')
        self.assertEqual((req, to_hub, restore[1]), ('aa_s', False, (4, 5, 6)))

    def test_party_wipe(self):
        self.assertEqual(L.party_wipe('aa', True), ('reload', None))
        self.assertEqual(L.party_wipe('aa', False), ('restart', 'aa'))


class Pieces(unittest.TestCase):
    def test_nearest_inclusive_80_later_wins_ties(self):
        ps = [L.Piece(0, 0, 0, 32767, 0), L.Piece(0, 0, 0, 32767, 0), L.Piece(4 * 200, 0, 0, 32767, 0)]
        self.assertEqual(L.find_moving_piece(ps, (F(0.0), F(0.0), F(0.0))), 1)
        self.assertTrue(ps[1].claimed)
        # the nearest is claimed: no fallback, even though piece 0 is as near
        self.assertEqual(L.find_moving_piece(ps, (F(0.0), F(0.0), F(0.0))), -1)
        # an unrotated cosine is 0x3f7fffff, not 1.0: the pivot is a hair short of x = 200,
        # so a point exactly 80 further along x is outside
        self.assertEqual(L.find_moving_piece(ps, (F(280.0), F(0.0), F(0.0))), -1)
        self.assertEqual(L.find_moving_piece(ps, (F(279.99), F(0.0), F(0.0))), 2)
        up = [L.Piece(0, 0, 320, 32767, 0)]                                       # z = 80
        self.assertEqual(L.find_moving_piece(up, (F(0.0), F(0.0), F(0.0))), 0)   # 80 inclusive
        self.assertEqual(L.find_moving_piece([L.Piece(0, 0, 0, 32767, 0)], (F(0.0), F(0.0), F(81.0))), -1)

    def test_pivot_is_rotated_translation(self):
        x, y, z = L.piece_pivot(L.Piece(400, 0, 40, 0, 32767))        # quarter turn
        self.assertAlmostEqual(W.to_float(x), 0.0, places=3)
        self.assertAlmostEqual(W.to_float(y), 100.0, places=2)
        self.assertEqual(W.to_float(z), 10.0)
        xm, ym, _ = L.piece_pivot(L.Piece(0, 400, 0, 32767, 0, mirrored=True))
        self.assertAlmostEqual(W.to_float(ym), -100.0, places=2)

    def test_release_and_disable(self):
        ps = [L.Piece(0, 0, 0, 32767, 0), L.Piece(4000, 0, 0, 32767, 0)]
        L.find_moving_piece(ps, (F(0.0), F(0.0), F(0.0)))
        off = []
        L.disable_unclaimed(ps, lambda i, on: off.append((i, on)))
        self.assertEqual(off, [(1, False)])
        L.release_piece(ps, -1)
        L.release_piece(ps, 0)
        self.assertFalse(ps[0].claimed)
        self.assertEqual(L.autodoor_pose(True), (False, (0.0, 0.0, -256.0), 0))


def tile(x0, y0, x1, y1, z):
    return L.WaterTile((F(x0), F(y0), F(z)), (F(x1), F(y1), F(z)))


class Water(unittest.TestCase):
    tiles = [tile(0, 0, 120, 120, 10.0), tile(120, 0, 240, 120, 20.0)]

    def test_box(self):
        r = F(12.0)
        self.assertEqual(L.water_test(self.tiles, r, (F(60.0), F(60.0), F(10.0))), (True, F(10.0)))
        self.assertEqual(L.water_test(self.tiles, r, (F(60.0), F(60.0), F(11.0))), (True, F(10.0)))
        self.assertEqual(L.water_test(self.tiles, r, (F(60.0), F(60.0), F(11.5)))[0], False)
        self.assertTrue(L.water_test(self.tiles, r, (F(60.0), F(60.0), F(-50.0)))[0])  # 60 deep
        self.assertFalse(L.water_test(self.tiles, r, (F(60.0), F(60.0), F(-50.5)))[0])
        self.assertTrue(L.water_test(self.tiles, r, (F(-13.0), F(60.0), F(10.0)))[0])   # r + 1
        self.assertFalse(L.water_test(self.tiles, r, (F(-13.5), F(60.0), F(10.0)))[0])

    def test_first_tile_in_walk_order_wins(self):
        r = F(12.0)
        self.assertEqual(L.water_test(self.tiles, r, (F(120.0), F(60.0), F(10.0)))[1], F(10.0))
        self.assertEqual(L.water_test(self.tiles[::-1], r, (F(120.0), F(60.0), F(10.0)))[1], F(20.0))

    def test_disturb_count_hysteresis(self):
        r = F(12.0)
        pos = (F(-12.5), F(60.0), F(10.0))
        self.assertTrue(L.water_test(self.tiles, r, pos)[0])        # entered within r + 1
        self.assertEqual(L.water_disturb_count(self.tiles, r, pos), 0)   # but leaves within r
        self.assertEqual(L.water_disturb_count(self.tiles, r, (F(120.0), F(60.0), F(10.0))), 2)
        self.assertEqual(L.water_disturb_count(self.tiles, r, (F(60.0), F(60.0), F(10.0)), True), 0)
        many = [tile(0, 0, 10, 10, 0.0)] * 20
        self.assertEqual(L.water_disturb_count(many, r, (F(5.0), F(5.0), F(0.0))), 15)

    def test_mask_bit_order(self):
        mask = bytearray(128)
        mask[2 * 3 + 1] = 0x80          # column 3, row 0: bit 15 of the u16
        mask[64 + 2 * 5] = 0x01         # column 5, row 31: bit 0 of the second half
        self.assertEqual(L.water_mask_bit(mask, 0, 3), 1)
        self.assertEqual(L.water_mask_bit(mask, 31, 5), 1)
        self.assertEqual(L.water_mask_bit(mask, 1, 3), 0)



# ---- synthetic .TEX cells: a canonical Huffman encoder written for these tests ----------

def canonical(lengths):
    """{symbol: length} -> (codes {symbol: (value, length)}, sym list, base[18], limit[18])
    in the form the worker reads: code c of length L is valid when c <= limit[L], symbol
    sym[base[L] + c]."""
    order = sorted(lengths, key=lambda sy: (lengths[sy], sy))
    codes, sym, base, limit = {}, [], [0] * 18, [-1] * 18
    code, prev_len = 0, 0
    first = {}
    for sy in order:
        L = lengths[sy]
        code <<= (L - prev_len)
        prev_len = L
        if L not in first:
            first[L] = (code, len(sym))
        codes[sy] = (code, L)
        sym.append(sy)
        code += 1
    for L in range(1, 18):
        if L in first:
            c0, i0 = first[L]
            base[L] = i0 - c0
            limit[L] = c0 + sum(1 for sy in order if lengths[sy] == L) - 1
        else:                   # no code this long: below every longer code's prefix
            longer = [first[k][0] >> (k - L) for k in first if k > L]
            limit[L] = min(longer) - 1 if longer else -1
    return codes, sym, base, limit


def pack_bits(bits):
    while len(bits) % 16:
        bits += '0'
    words = [int(bits[i:i + 16], 2) for i in range(0, len(bits), 16)] + [0, 0]
    return b''.join(w.to_bytes(2, 'little') for w in words)


def build_cell(width, height, blocks, lengths, palette, succ):
    """A cell with one texture.  blocks: {(bx, by): [symbols x 256]} in one rectangle
    covering all keys."""
    codes, sym, base, limit = canonical(lengths)
    book = bytearray()
    stored = bytearray(0x400)
    for i in range(256):
        stored[4 * L.clut_order(i):4 * L.clut_order(i) + 4] = bytes(palette[i])
    book += stored + bytes(succ)
    book += len(sym).to_bytes(4, 'little') + b''.join(x.to_bytes(2, 'little') for x in sym)
    while len(book) % 4:
        book += b'\0'
    book += b''.join(x.to_bytes(4, 'little', signed=True) for x in base + limit)
    xs = [k[0] for k in blocks]
    ys = [k[1] for k in blocks]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    streams = []
    for by in range(y0, y1 + 1):
        for bx in range(x0, x1 + 1):
            streams.append(pack_bits(''.join(format(codes[sy][0], '0%db' % codes[sy][1])
                                             for sy in blocks[(bx, by)])))
    head = bytearray(0x80)
    head[0:4] = (1).to_bytes(4, 'little')
    record_off = 0x80
    nblocks = len(streams)
    book_off = record_off + 4 + 4 + 4 * nblocks + 4
    stream_off = book_off + len(book)
    rec = bytearray(book_off.to_bytes(4, 'little'))
    rec += bytes([x0 & 0xFF, y0 & 0xFF, x1 & 0xFF, y1 & 0xFF])
    o = stream_off
    for st in streams:
        rec += o.to_bytes(4, 'little')
        o += len(st)
    rec += bytes([0xFF, 0, 0, 0])
    hdr = (width.to_bytes(2, 'little') + height.to_bytes(2, 'little') + (0).to_bytes(2, 'little') +
           (0).to_bytes(2, 'little') + (0x010C).to_bytes(2, 'little') + bytes(2) + bytes(4) +
           record_off.to_bytes(4, 'little'))
    head[0x40:0x40 + len(hdr)] = hdr
    return bytes(head + rec + book + b''.join(streams))


class Textures(unittest.TestCase):
    def test_directory(self):
        d = (bytes(4) + b''.join(v.to_bytes(4, 'little', signed=True) for v in (5050, 0x800, 0x100)) +
             b''.join(v.to_bytes(4, 'little', signed=True) for v in (5051, 0x900, 0x40)) +
             (-1).to_bytes(4, 'little', signed=True) + bytes(8))
        self.assertEqual(L.tex_directory(d), {5050: (0x800, 0x100), 5051: (0x900, 0x40)})
        self.assertEqual(L.tex_directory(d.replace((-1).to_bytes(4, 'little', signed=True),
                                                   (-2).to_bytes(4, 'little', signed=True))),
                         {5050: (0x800, 0x100), 5051: (0x900, 0x40)})
        self.assertEqual(L.tex_directory(bytes(4) + bytes(12)), {})          # first id 0
        with self.assertRaises(ValueError):
            L.tex_directory(bytes(4) + (7).to_bytes(4, 'little') * 3)

    def test_cell_ids(self):
        self.assertEqual(L.cell_id(F(0.0), F(0.0)), 5050)
        self.assertEqual(L.cell_id(F(-0.5), F(719.9)), 5049)
        self.assertEqual(L.cell_id(F(0.0), F(720.0)), 5150)
        self.assertEqual(L.cell_id(F(960.0), F(0.0), size=0.0), 5051)
        self.assertEqual(L.wanted_cells(5050)[:3], [4949, 4950, 4951])
        self.assertEqual(len(set(L.wanted_cells(5050))), 9)

    def test_clut_order_is_an_involution(self):
        self.assertEqual(L.clut_order(8), 16)
        self.assertEqual(L.clut_order(16), 8)
        self.assertTrue(all(L.clut_order(L.clut_order(i)) == i for i in range(256)))

    def lengths(self):
        lengths = {i: 9 for i in range(0, 200)}
        lengths.update({200: 3, 201: 4, 0x100: 4, 0x101: 4, 0x102: 5, 0x103: 5, 0x104: 6,
                        0x105: 5, 0x106: 6, 0x10C: 12})
        return lengths

    def test_block_round_trip(self):
        succ = bytes((p * 7 + k * 31) & 0xFF for p in range(256) for k in range(8))
        palette = [(i, 255 - i, i ^ 0x55, i & 0x7F) for i in range(256)]
        symbols, expect, prev = [], [], 0
        pattern = [200, 0x100, 201, 0x101, 0x102, 0x103, 0x104, 0x105, 0x106, 0x10C, 5, 199]
        for i in range(256):
            sy = pattern[i % len(pattern)]
            if sy in (0x101, 0x102, 0x103) and i < 17:
                sy = 200
            if sy == 0x104 and i < 2:
                sy = 201
            if sy == 0x100 and i < 1:
                sy = 200
            if sy < 0x100:
                v = sy
            elif sy < 0x105:
                v = expect[i + L.REL[sy - 0x100]]
            else:
                v = succ[prev * 8 + sy - 0x105]
            symbols.append(sy)
            expect.append(v)
            prev = v
        cell = build_cell(20, 16, {(0, 0): symbols, (1, 0): [7] * 256}, self.lengths(), palette, succ)
        w, h, rows, pal = L.decode_texture(cell, 0x40)
        self.assertEqual((w, h), (20, 16))
        self.assertEqual([rows[r][c] for r in range(16) for c in range(16)], expect)
        self.assertEqual(rows[3][19], 7)
        self.assertEqual(pal[9], palette[9])

    def test_missing_blocks_stay_unwritten(self):
        succ = bytes(0x800)
        palette = [(0, 0, 0, 0)] * 256
        cell = build_cell(32, 32, {(1, 1): [200] * 256}, self.lengths(), palette, succ)
        _w, _h, rows, _p = L.decode_texture(cell, 0x40)
        self.assertIsNone(rows[0][0])
        self.assertEqual(rows[31][31], 200)

    def test_refusals(self):
        cell = bytearray(build_cell(16, 16, {(0, 0): [200] * 256}, self.lengths(),
                                    [(0, 0, 0, 0)] * 256, bytes(0x800)))
        cell[0x48] = 0x0D                           # flags 0x010d: the unused VQ form
        with self.assertRaises(ValueError):
            L.decode_texture(bytes(cell), 0x40)
        self.assertIsNone(L.chunk_texture_header(0, 0x40, {}, b''))
        with self.assertRaises(ValueError):
            L.chunk_texture_header(5050, 0x80, {5050: (0, 0x80)}, (1).to_bytes(4, 'little') + bytes(0x7C))

    def test_uv(self):
        self.assertEqual(L.uv_normalised(16 * 32, 16 * 8, 64, 16), (0.5, 0.5))

    def test_header_state_and_materials(self):
        self.assertEqual(L.chunk_header_state(0), (0x02, None, L.TEST_OPAQUE, 'dynamic', 0))
        self.assertEqual(L.chunk_header_state(0x400), (0x01, None, L.TEST_CUTOUT, 'dynamic', 0))
        self.assertEqual(L.chunk_header_state(0x2200), (0x01, None, L.TEST_OPAQUE, 230, 4))
        self.assertEqual(L.chunk_header_state(0x410)[:3], (0x09, 0x2A, L.TEST_CUTOUT))
        self.assertEqual(L.chunk_header_state(0x10100)[3], -230)
        self.assertEqual(L.batch_material(0x01, L.TEST_CUTOUT), ('mix', 0x2F))
        self.assertEqual(L.batch_material(0x01, L.TEST_CUTOUT, blend_enabled=False), ('opaque', 0x2F))
        self.assertEqual(L.batch_material(0x09, L.TEST_OPAQUE), ('env', None))


if __name__ == '__main__':
    unittest.main()


# ---- round 2 (2026-10-18): docs/level-flow.md section 16 ---------------------------------

class Round2WorldEntry(unittest.TestCase):
    def test_directory_order_not_sorted(self):
        entries = ['zeta.world', 'alpha.world', 'objects.ob']
        self.assertEqual(L.first_entry_with_extension(entries, 'world'), 'zeta.world')
        m = L.level_manifest('leva', gob_lumps=['leva.lmp', 'waterenv.lmp'],
                             level_entries=entries,
                             disc_files=['LEVA.GOB', 'LEVA.TEX', 'LOADMISC.LMP', 'FX.LMP',
                                         'HUD.LMP', 'MAPICONS.LMP', 'ICONS.LMP',
                                         'GOODDOG.LMP', 'SKELE_B.LMP'])
        self.assertEqual([r.name for r in m if r.step == '8'], ['zeta.world'])

    def test_extension_after_last_dot_exact(self):
        f = L.first_entry_with_extension
        self.assertIsNone(f(['world', 'a.WORLD', 'a.world.bak', 'a.worlds'], 'world'))
        self.assertEqual(f(['x.y.world'], 'world'), 'x.y.world')
        self.assertEqual(f(['.world'], 'world'), '.world')
        self.assertEqual(f(['a.world', 'b.ob', 'c.world'], 'world', 1), 'c.world')
        self.assertIsNone(f(['a.world'], 'world', 1))

    def test_no_world_is_required(self):
        with self.assertRaises(L.MissingResource):
            L.level_manifest('leva', gob_lumps=['leva.lmp', 'waterenv.lmp'],
                             level_entries=['objects.ob'],
                             disc_files=['LEVA.GOB', 'LEVA.TEX', 'LOADMISC.LMP', 'FX.LMP',
                                         'HUD.LMP', 'MAPICONS.LMP', 'ICONS.LMP'])


class Round2Light(unittest.TestCase):
    def test_base_level_0x40_wins(self):
        both = L.LEVEL_FLAG_LIGHT_20 | L.LEVEL_FLAG_LIGHT_40
        self.assertIs(L.base_light_level, L.level_light_alpha)
        self.assertEqual(L.base_light_level(both), 0x40)
        self.assertEqual(L.base_light_level(L.LEVEL_FLAG_LIGHT_40), 0x40)
        self.assertEqual(L.base_light_level(0xFFFFFFFF & ~L.LEVEL_FLAG_LIGHT_40), 0x20)

    def test_chunk_constant_order(self):
        self.assertEqual(L.chunk_header_state(0x2200)[3], 230)     # 0x2000 before 0x200
        self.assertEqual(L.chunk_header_state(0x2300)[3], -230)    # 0x100 first
        self.assertEqual(L.chunk_header_state(0x200)[3], 0)


class Round2Recall(unittest.TestCase):
    def run_ticks(self, rc, n, cut=lambda t: False, alive=lambda t: 1):
        return [rc.tick(cut(t), alive(t)) for t in range(n)]

    def test_sixty_calls(self):
        rc = L.RecallCountdown()
        rc.start()
        events = self.run_ticks(rc, 61)
        self.assertEqual(events[0], L.RECALL_AURA)
        self.assertEqual(events[1:59], [None] * 58)
        self.assertEqual(events[59], L.RECALL_FINISH)
        self.assertEqual(events[60], None)
        self.assertFalse(rc.running)

    def test_cutscene_only_matters_on_the_last_call(self):
        rc = L.RecallCountdown()
        rc.start()
        events = self.run_ticks(rc, 60, cut=lambda t: t < 59)
        self.assertEqual(events[59], L.RECALL_FINISH)
        rc.start()
        events = self.run_ticks(rc, 70, cut=lambda t: t == 59)
        self.assertEqual(events[59], L.RECALL_DROPPED_CUTSCENE)
        self.assertEqual(events[60:], [None] * 10)              # lost, not deferred
        self.assertEqual(rc.value, 0)

    def test_nobody_alive_drops(self):
        rc = L.RecallCountdown(1)
        self.assertEqual(rc.tick(False, 0), L.RECALL_DROPPED_NOBODY)
        rc = L.RecallCountdown(1)
        self.assertEqual(rc.tick(True, 0), L.RECALL_DROPPED_CUTSCENE)   # cutscene tested first

    def test_odd_start_values(self):
        self.assertEqual(L.RecallCountdown(1).tick(False, 1), L.RECALL_FINISH)   # no aura
        rc = L.RecallCountdown(61)
        self.assertEqual(rc.tick(False, 1), None)
        self.assertEqual(rc.tick(False, 1), L.RECALL_AURA)
        rc = L.RecallCountdown(0x80)                             # s8 -128: counts down too
        self.assertEqual(rc.tick(False, 1), None)
        self.assertEqual(rc.value, 0x7F)

    def test_request_tick(self):
        self.assertEqual(L.recall_request_tick(100, True), 159)   # net game: message before tasks
        self.assertEqual(L.recall_request_tick(100, False), 160)  # offline: after recallTick


class Round2MovePiece(unittest.TestCase):
    def test_absolute_and_unrotated_nudge(self):
        p = L.Piece(400, -800, 40, 32767, 0)
        open_ = (F(0.0), F(0.0), F(-256.0))
        first = L.move_piece(p, open_, 0)
        self.assertEqual(first, [(399, -800, -984, 32767, 0)])   # sin16(0) = 2**-22
        self.assertEqual(L.move_piece(p, open_, 0), first)       # rest values only
        self.assertEqual(L.move_piece(p, (F(0.0), F(0.0), F(0.0)), 0)[0][2], 40)

    def test_quarter_turn(self):
        p = L.Piece(400, -800, 40, 32767, 0)
        (tx, ty, tz, c, s), = L.move_piece(p, (F(0.0), F(0.0), F(0.0)), 0x4000)
        self.assertEqual((c, s), (0, 32767))
        self.assertEqual((tx, ty, tz), (-800, -399, 40))          # R(-90 deg) of (400, -800)

    def test_mirrored_rotates_the_other_way(self):
        p = L.Piece(400, 0, 0, 32767, 0)
        plain, mirrored = L.move_piece(p, (F(0.0), F(0.0), F(0.0)), 0x4000, (False, True))
        self.assertEqual(plain[:2], (0, -400))                   # R(-90 deg) of (400, 0)
        self.assertEqual(mirrored[:2], (0, 400))                 # R(+90 deg)
        self.assertEqual(L.move_piece(p, (F(0.0),) * 3, 0x4000, ()), [])

    def test_rotation_clamped_and_rounded(self):
        p = L.Piece(0, 0, 0, -0x8000, -0x8000)                   # not a unit vector
        (_, _, _, c, s), = L.move_piece(p, (F(0.0),) * 3, 0x2000)
        self.assertEqual(c, 0)
        self.assertEqual(s, -0x8000)                             # -46341 clamped to -32768

    def test_turns_about_pivot_and_shifts_in_rest_frame(self):
        def draw(t, cos16, sin16, mirrored, local):
            px, py = (local[0] + t[0]) / 4.0, (local[1] + t[1]) / 4.0
            c, s = cos16 / 32767.0, sin16 / 32767.0
            if mirrored:
                return px * c + py * s, px * s - py * c
            return px * c - py * s, px * s + py * c
        for mirrored in (False, True):
            p = L.Piece(1200, -400, 0, 23170, 23170, mirrored)
            off, angle = (12.0, -5.0), 0x1555
            (tx, ty, _, c, s), = L.move_piece(p, (F(off[0]), F(off[1]), F(0.0)), angle)
            r = 23170 / 32767.0
            m = ((r, r), (r, -r)) if mirrored else ((r, -r), (r, r))
            pivot = draw((p.tx, p.ty), p.cos, p.sin, mirrored, (0, 0))
            a = angle / 65536.0 * 2 * math.pi
            for local in ((0, 0), (160, 0), (0, 160), (-80, 240)):
                rest = draw((p.tx, p.ty), p.cos, p.sin, mirrored, local)
                rel = (rest[0] - pivot[0], rest[1] - pivot[1])
                want = (pivot[0] + m[0][0] * off[0] + m[0][1] * off[1]
                        + math.cos(a) * rel[0] - math.sin(a) * rel[1],
                        pivot[1] + m[1][0] * off[0] + m[1][1] * off[1]
                        + math.sin(a) * rel[0] + math.cos(a) * rel[1])
                got = draw((tx, ty), c, s, mirrored, local)
                self.assertAlmostEqual(got[0], want[0], delta=0.5)
                self.assertAlmostEqual(got[1], want[1], delta=0.5)


def _level(origin, size, field, elements):
    return W.Level(W.build_world_file(origin, size, [field], elements))


def _flat(x0, y0, w, h, height, element_z=0, element_xy=(0, 0)):
    samples = [height * 16] * (w * h)
    # Grid origin is negative so a point just below 0 is still a real cell.  A grid
    # that starts at 0 drops those points and terrain_height returns the sentinel.
    level = _level((-2, -2), (8, 8), (x0, y0, w, h, samples),
                   [(0, 0, element_xy[0], element_xy[1], element_z, 32767, 0)])
    return level


class Round3Placement(unittest.TestCase):
    """The start is the spawn slot, then the highest sample within 12.  A floor more than
    12 above z = 0 is still ground.  Acts do not choose the slot; a previous level name,
    an entrance name, a gate and a recall do, and none of them clears a stale xy."""

    def test_radius_word_is_twelve(self):
        self.assertEqual(L.PLACEMENT_RADIUS, F(12.0))
        self.assertEqual(L.PLACEMENT_RADIUS, 0x41400000)

    def test_snap_keeps_xy_and_a_floor_above_twelve(self):
        spawn = L.SpawnState()
        spawn.pos[0] = [F(3.0), F(-4.0), F(0.0)]
        spawn.pos[1] = [F(9.0), F(9.0), F(1.0)]
        spawn.facing = [100, 200, 300, 400]
        spawn.rank = 1
        seen = []

        def height(radius, pos):
            seen.append((radius, pos))
            return F(20.0)

        def spot(*_args):
            raise AssertionError('slot 0 is not searched')

        L.place_players(spawn, 1, height, spot)
        self.assertEqual(seen, [(12.0, (F(3.0), F(-4.0), F(0.0)))])
        self.assertEqual(spawn.pos[0], [F(3.0), F(-4.0), F(20.0)])
        self.assertEqual(spawn.pos[1], [F(9.0), F(9.0), F(1.0)])   # other slots stay
        self.assertEqual(spawn.facing, [100, 200, 300, 400])
        self.assertEqual(spawn.rank, 1)

    def test_high_floor_fails_the_origin_below_test_and_passes_the_snap(self):
        level = _flat(-4, -4, 8, 8, 0, element_z=20)
        origin = (F(0.0), F(0.0), F(0.0))
        self.assertEqual(W.terrain_height_below(level, F(4.0), origin), W.NO_FLOOR)
        self.assertEqual(W.terrain_height(level, F(4.0), origin), F(20.0))
        self.assertEqual(W.terrain_height(level, L.PLACEMENT_RADIUS, origin), F(20.0))
        spawn = L.SpawnState()

        def height(radius, pos):
            return W.terrain_height(level, F(radius), tuple(F(v) for v in pos))

        L.place_players(spawn, 1, height, lambda *a: a[0])
        self.assertEqual(spawn.pos[0], [0.0, 0.0, F(20.0)])

    def test_radius_twelve_reaches_a_sample_radius_four_misses(self):
        # Nearest sample sits 8 world units out: inside 12, outside 4.
        level = _flat(2, 0, 4, 2, 30)
        origin = (F(0.0), F(0.0), F(0.0))
        self.assertEqual(W.terrain_height(level, F(4.0), origin), W.NO_FLOOR)
        self.assertEqual(W.terrain_height(level, L.PLACEMENT_RADIUS, origin), F(30.0))
        marker = (F(400.0), F(0.0), F(0.0))
        far = _flat(0, 0, 4, 4, 0, element_z=8, element_xy=(400, 0))
        self.assertEqual(W.terrain_height(far, L.PLACEMENT_RADIUS, origin), W.NO_FLOOR)
        self.assertEqual(W.terrain_height(far, L.PLACEMENT_RADIUS, marker), F(8.0))

    def test_search_rejects_a_floor_six_above_and_the_snap_still_takes_it(self):
        level = _flat(-40, -40, 80, 80, 0, element_z=20)
        centre = (F(0.0), F(0.0), F(0.0))
        world = Obj.World()
        world.shared = C.SharedRandom(20973)
        pos, ok = world.find_free_spot(
            centre, 36, 24, False,
            lambda r, p: W.terrain_test_flag1(level, r, p),
            lambda r, p: W.terrain_height(level, r, p))
        self.assertEqual(ok, 0)
        self.assertEqual(pos, [F(0.0), F(0.0), F(0.0)])
        spawn = L.SpawnState()
        spawn.pos[0] = list(pos)
        L.place_players(spawn, 1, lambda r, p: W.terrain_height(level, F(r), p),
                        lambda *a: a[0])
        self.assertEqual(spawn.pos[0][2], F(20.0))
        self.assertEqual(L.player_ctor_z(tuple(spawn.pos[0]), L.PLACEMENT_RADIUS,
                                         lambda r, p: W.terrain_height(level, r, p)),
                         F(20.0))

    def test_a_floor_under_six_is_accepted_and_six_exactly_is_not(self):
        def search(height):
            level = _flat(-40, -40, 80, 80, 0, element_z=height)
            world = Obj.World()
            world.shared = C.SharedRandom(1)
            return world.find_free_spot(
                (F(0.0), F(0.0), F(0.0)), 36, 24, False,
                lambda r, p: W.terrain_test_flag1(level, r, p),
                lambda r, p: W.terrain_height(level, r, p))
        low, ok_low = search(5)
        high, ok_high = search(6)
        self.assertEqual(ok_low, 1)
        self.assertEqual(low[2], F(5.0))
        self.assertEqual(ok_high, 0)
        self.assertEqual(high[2], F(0.0))

    def test_ctor_snap_uses_the_stored_radius_and_ignores_z(self):
        seen = []

        def height(radius, pos):
            seen.append((radius, pos[2]))
            return F(4.0)

        z = L.player_ctor_z((F(1.0), F(2.0), F(99.0)), L.PLACEMENT_RADIUS, height)
        self.assertEqual(z, F(4.0))
        self.assertEqual(seen, [(L.PLACEMENT_RADIUS, F(99.0))])

    def test_from_marker_beats_the_origin_and_recall_keeps_its_own_xy(self):
        records = [rec('Player1', 'default=1', x=0.0, y=0.0, z=0.0),
                   rec('Player1', 'from=hub', x=50.0, y=8.0, z=1.0)]
        spawn = L.SpawnState()
        spawn.pos[0] = [F(9.0), F(9.0), F(9.0)]          # previous level, not cleared
        took = L.run_markers(spawn, records, 'hub', '', False, lambda c, *_a: c, lambda: 0)
        self.assertEqual(len(took), 2)                   # default, then from, last wins
        self.assertEqual(spawn.pos[0][:2], [50.0, 8.0])
        self.assertEqual(spawn.rank, 2)
        L.place_players(spawn, 1, lambda r, p: F(3.0), lambda *a: a[0],
                        restore_xy=[(F(1.5), F(2.5), F(0.0))])
        self.assertEqual(spawn.pos[0], [F(1.5), F(2.5), F(3.0)])

    def test_gate_sets_rank_three_then_the_same_snap(self):
        gate = rec('Portal', x=12.0, y=0.0, z=40.0)
        spawn = L.SpawnState()
        seen = []

        def spot(centre, spread, radius, any_height):
            seen.append((spread, radius, any_height, centre))
            return centre

        L.run_markers(spawn, [gate], '', '', False, spot, lambda: 0x1111,
                      gate_arrival=True, num_players=1)
        self.assertEqual(spawn.rank, 3)
        self.assertEqual(seen, [(36, 24, True, (12.0, 0.0, 40.0))])
        L.place_players(spawn, 1, lambda r, p: F(7.0),
                        lambda *a: (_ for _ in ()).throw(AssertionError('rank 3')))
        self.assertEqual(spawn.pos[0], [12.0, 0.0, F(7.0)])
        self.assertEqual(spawn.pos[1], [0.0, 0.0, 0.0])

    def test_no_marker_keeps_the_stale_slot(self):
        spawn = L.SpawnState()
        spawn.pos[0] = [F(4.0), F(5.0), F(6.0)]
        spawn.facing[0] = 99
        L.run_markers(spawn, [rec('Lantern')], 'hub', 'door', False, lambda *a: a[0], lambda: 0)
        L.place_players(spawn, 1, lambda r, p: F(1.0), lambda *a: a[0])
        self.assertEqual(spawn.rank, 0)
        self.assertEqual(spawn.pos[0], [F(4.0), F(5.0), F(1.0)])
        self.assertEqual(spawn.facing[0], 99)


class Round3Arena(unittest.TestCase):
    def test_ring_angle(self):
        self.assertEqual(L.arena_ring_angle(0, 1), 0)          # s16(65535) * 0
        self.assertEqual(L.arena_ring_angle(1, 1), W.s16(-1))
        self.assertEqual(L.arena_ring_angle(2, 4), W.s16(16383 * 2))
        self.assertEqual(L.arena_ring_angle(2, 3), W.s16(21845 * 2))
        with self.assertRaises(ValueError):
            L.arena_ring_angle(0, 0)

    def test_first_search_and_the_wider_retry(self):
        entry = (F(10.0), F(-4.0), F(2.0))
        calls = []

        def search(centre, spread, radius, any_height):
            calls.append((spread, radius, any_height, centre))
            if spread == L.ARENA_FIRST_SPREAD:
                return centre, 0
            return (centre[0], centre[1], F(6.0)), 1

        pos, facing, ok = L.arena_initial_place(
            entry, 0, 1, False, search, table_facing=True, table_angle=0x1000)
        self.assertEqual([c[0] for c in calls], [36, 240])
        self.assertEqual(calls[0][1:], (24, False, calls[1][3]))
        self.assertEqual(ok, 1)
        self.assertEqual(pos[2], F(6.0))
        self.assertEqual(facing, (0x1000 - 0x4000 - 0x8000) & 0xFFFF)
        calls.clear()
        pos, facing, ok = L.arena_initial_place(
            entry, 0, 1, True, lambda c, s, r, a: (c, 1), table_facing=True, table_angle=0x1000)
        self.assertEqual(ok, 1)
        self.assertEqual(facing, (0x1000 - 0x4000) & 0xFFFF)   # mode A: no extra half-turn
        self.assertEqual(pos[2], entry[2])

    def test_facing_from_the_offset_when_the_flag_is_clear(self):
        entry = (F(0.0), F(0.0), F(0.0))

        def search(centre, spread, radius, any_height):
            self.assertEqual(spread, 36)
            return (F(3.0), F(4.0), centre[2]), 1

        _pos, facing, ok = L.arena_initial_place(entry, 1, 4, True, search)
        dx, dy = F(3.0), F(4.0)
        want = W.s16(-0x4000 - C.atan2_16(dx, dy)) & 0xFFFF
        self.assertEqual(ok, 1)
        self.assertEqual(facing, want)


def _lattice_misses(level, centre, radius_limit, query):
    """Integer offsets inside radius_limit. A miss is a radius-`query` height of the sentinel."""
    cx, cy, cz = centre
    fx, fy = W.to_float(cx), W.to_float(cy)
    limit = int(radius_limit)
    misses = tested = 0
    for ix in range(-limit, limit + 1):
        for iy in range(-limit, limit + 1):
            if ix * ix + iy * iy > limit * limit:
                continue
            tested += 1
            pos = (F(fx + ix), F(fy + iy), cz)
            if W.terrain_height(level, query, pos) == W.NO_FLOOR:
                misses += 1
    return misses, tested


class Round4ArenaEntry(unittest.TestCase):
    """How an arena name advances, which record byte selects a table slot, and why the
    Start marker stays in entry 0. Synthetic records only."""

    def test_mode_a_step_and_the_wrap_back_to_the_saved_index(self):
        self.assertEqual(L.arena_mode_a_next(0, 4), 1)
        self.assertEqual(L.arena_mode_a_next(7, 4), 8)
        self.assertEqual(L.arena_mode_a_next(11, 9), 12)
        self.assertEqual(L.arena_mode_a_next(12, 4), 4)     # remainder 0 is replaced
        self.assertEqual(L.arena_mode_a_next(12, 0), 0)
        for saved in range(10):
            seen = [saved]
            index = saved
            for _ in range(13):
                index = L.arena_mode_a_next(index, saved)
                if index == saved:
                    break
                seen.append(index)
            self.assertIn(10, seen)
            self.assertIn(12, seen)
            self.assertEqual(8 in seen, saved <= 8)
        with self.assertRaises(ValueError):
            L.arena_mode_a_next(-1, 0)

    def test_record_byte_keeps_the_low_nibble_times_four(self):
        self.assertEqual(L.arena_record_table_offset(0x30), 0)
        self.assertEqual(L.arena_record_table_offset(0x31), 4)
        self.assertEqual(L.arena_record_table_offset(0x35), 20)
        self.assertEqual(L.arena_record_table_offset(0x33), 12)
        self.assertEqual(L.arena_record_table_offset(0x42), 8)
        # Low nibble 8 sets the sign bit of the left shift. The high nibble is shifted away.
        self.assertLess(L.arena_record_table_offset(0x08), 0)
        self.assertEqual(L.arena_record_table_offset(0x80), 0)

    def test_the_start_overwrites_entry_zero_and_alternates_append(self):
        entries, count = L.arena_register_spawn([], 1, 0, (0.0, 0.0, 0.0), 0)
        self.assertEqual(count, 1)
        self.assertEqual(entries[0][0], (0.0, 0.0, 0.0))
        start = (F(10.0), F(-4.0), F(2.0))
        entries, count = L.arena_register_spawn(entries, count, 0, start, 0x1234)
        self.assertEqual(count, 1)                          # Start does not increment
        alt = (F(3.0), F(4.0), F(5.0))
        entries, count = L.arena_register_spawn(entries, count, -1, alt, 0x10)
        self.assertEqual(count, 2)
        self.assertEqual(entries[0][0], start)              # still the Start, not the alternate
        self.assertEqual(entries[1][0], alt)
        self.assertEqual(entries[0][1], 0x1234)

    def test_slot_zero_is_the_same_ring_for_every_player_count(self):
        entry = (F(10.0), F(-4.0), F(2.0))
        one = L.arena_ring_centre(entry, 0, 1, True)
        self.assertEqual(one, L.arena_ring_centre(entry, 0, 2, True))
        self.assertEqual(one, L.arena_ring_centre(entry, 0, 4, True))
        self.assertEqual(L.arena_ring_angle(0, 1), 0)
        ox = W.fmul(C.cos16(0), L.ARENA_RING_MODE_A)
        oy = W.fmul(C.sin16(0), L.ARENA_RING_MODE_A)
        self.assertEqual(ox, L.ARENA_RING_MODE_A)           # cos16(0) is exactly 1
        self.assertEqual(one, (W.fadd(entry[0], ox), W.fadd(entry[1], oy), entry[2]))
        self.assertNotEqual(oy, 0)                          # sin16(0) is not zero


class Round4Ground(unittest.TestCase):
    """A search can only return a point inside its spread, or the centre. On a disc that
    is entirely a floor, the seed and a rejecting object still snap onto ground. On a
    disc with a hole, an accepted sample snaps to the sentinel."""

    def _search(self, level, centre, seed, with_object):
        world = Obj.World()
        world.shared = C.SharedRandom(seed)
        if with_object:
            world.construct(0x1000, centre)
        return world.find_free_spot(
            centre, L.ARENA_FIRST_SPREAD, L.ARENA_SEARCH_RADIUS, False,
            lambda r, p: W.terrain_test_flag1(level, r, p),
            lambda r, p: W.terrain_height(level, r, p))

    def _snap(self, level, pos):
        return L.player_ctor_z(tuple(pos), L.PLACEMENT_RADIUS,
                               lambda r, p: W.terrain_height(level, r, p))

    def test_a_solid_disc_keeps_ground_for_every_sampled_point(self):
        level = _flat(-40, -40, 80, 80, 0)
        centre = (F(0.0), F(0.0), F(0.0))
        misses, tested = _lattice_misses(level, centre, 37, F(11.25))
        self.assertEqual(misses, 0)
        self.assertEqual(tested, 4293)
        # 11.25 plus the half-unit diagonal is still under the placement radius of 12,
        # and 37 leaves more than that diagonal outside a spread of 36.
        self.assertLess(11.25 + (0.5 * 0.5 + 0.5 * 0.5) ** 0.5, 12.0)
        failed = 0
        for seed in list(range(16)) + [20973]:
            for with_object in (False, True):
                pos, ok = self._search(level, centre, seed, with_object)
                if not ok:
                    failed += 1
                # A total failure keeps the last accepted point, or the centre. Both are
                # inside the disc, so the radius-12 snap is still a floor.
                self.assertNotEqual(self._snap(level, pos), W.NO_FLOOR)
        self.assertGreater(failed, 0)

    def test_a_hole_lets_one_seed_keep_ground_and_another_lose_it(self):
        level = _flat(0, 0, 1, 1, 0)
        centre = (F(0.0), F(0.0), F(0.0))
        self.assertNotEqual(W.terrain_height(level, L.PLACEMENT_RADIUS, centre), W.NO_FLOOR)
        kept = lost = 0
        lost_ok = None
        for seed in range(32):
            pos, ok = self._search(level, centre, seed, False)
            if self._snap(level, pos) == W.NO_FLOOR:
                lost += 1
                lost_ok = ok
            else:
                kept += 1
        self.assertGreater(kept, 0)
        self.assertGreater(lost, 0)
        self.assertEqual(lost_ok, 1)

