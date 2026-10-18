#!/usr/bin/env python3
"""Unit tests of tools/ref_levels.py on synthetic fixtures only.

No game file is read: level names are short identifiers the executable compares against,
and every table, record list, piece and water tile is built here.  The tests check the
model's own logic against the rules written in docs/level-flow.md; nothing here proves
that the model matches the game.

  python3 -m unittest discover -s tools -p 'test_ref_levels.py'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_levels as L                          # noqa: E402
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
