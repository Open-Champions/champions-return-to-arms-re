#!/usr/bin/env python3
"""Synthetic tests of tools/ref_dialog_gaps.py and tools/dialog_gaps_census.py (the contract
in docs/spec/dialog-gaps.md).  No game file is needed; tools/difftest_dialog_gaps.py
compares the same behaviour with the original functions."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C  # noqa: E402
import ref_dialog_gaps as R  # noqa: E402
import dialog_gaps_census as G  # noqa: E402
from test_dialog_census import build_script, push, sysreq  # noqa: E402

C.set_fpu('ps2')
F = C.f32


class Offset(unittest.TestCase):
    def test_four_fields(self):
        self.assertEqual(R.parse_dialog_offset('10,-20,30,40'), ((10, -20, 30, 40), 4))

    def test_absent_keeps_the_stale_lateral_only(self):
        self.assertEqual(R.parse_dialog_offset(None, (1, 2, 3, 4)), ((0, 0, 3, 0), 0))

    def test_partial_keeps_stale_slots(self):
        self.assertEqual(R.parse_dialog_offset('5,6', (1, 2, 3, 4)), ((5, 6, 3, 4), 2))
        self.assertEqual(R.parse_dialog_offset('5 ,6,7,8', (1, 2, 3, 4)), ((5, 2, 3, 4), 1))
        self.assertEqual(R.parse_dialog_offset(' 7, -3,+12,9'), ((7, -3, 12, 9), 4))
        self.assertEqual(R.parse_dialog_offset('x', (1, 2, 3, 4)), ((1, 2, 3, 4), 0))

    def test_view_refuses_an_unknown_stack_value(self):
        with self.assertRaises(ValueError):
            R.setup_dialog_view(R.View(), (0, 0, 0), 0, 0, [], (0, 0, 0), None)


class Side(unittest.TestCase):
    def test_table(self):
        want = {(0, 0, 0): 1, (0, 0, 1): 0, (0, 1, 1): 0, (1, 0, 0): 2, (1, 1, 0): 2,
                (1, 0, 1): 1, (1, 1, 1): 1}
        for flags, idx in want.items():
            self.assertEqual(R.side_index(*flags, behind_camera=lambda: 1 / 0), idx, flags)
        self.assertEqual(R.side_index(0, 1, 0, lambda: True), 2)
        self.assertEqual(R.side_index(0, 1, 0, lambda: False), 0)


class View(unittest.TestCase):
    def setUp(self):
        self.v = R.View(yaw=0, pitch=100)

    def test_straight_view_in_front_of_facing(self):
        info = R.setup_dialog_view(self.v, (F(10), F(20), F(5)), 0, 0, [], (F(10), F(0), F(0)), '0,0,0,0')
        self.assertEqual(info['angle'], 0)
        self.assertEqual(C.to_float(self.v.target[0]), 90.0)        # 10 + cos(0) * 80
        self.assertAlmostEqual(C.to_float(self.v.target[1]), 20.0, places=4)
        self.assertEqual(C.to_float(self.v.target[2]), 75.0)        # 5 + 70
        self.assertEqual(self.v.target_pitch, 4000)
        self.assertEqual(self.v.target_yaw, C.s16(-0x4000))
        self.assertEqual((self.v.start_yaw, self.v.start_pitch, self.v.progress), (0, 100, 0))

    def test_far_start_uses_085(self):
        R.setup_dialog_view(self.v, (F(0), F(0), F(0)), 0, 0, [], (F(1000), F(0), F(0)), '0,0,0,0')
        self.assertEqual(self.v.k, R.FAR_K)

    def test_lateral_moves_sideways(self):
        R.setup_dialog_view(self.v, (F(0), F(0), F(0)), 0, 0, [], (F(0), F(0), F(0)), '0,0,10,0')
        self.assertAlmostEqual(C.to_float(self.v.target[1]), 10.0, places=4)

    def test_side_with_a_player_in_front(self):
        info = R.setup_dialog_view(self.v, (F(0), F(0), F(0)), 0, 1, [(F(0), F(50), F(0))],
                                   (F(0), F(0), F(0)), '0,0,0,0')
        self.assertEqual(info['flags'], (1, 0, 0))
        self.assertEqual(info['angle'], -6000)


class LookAt(unittest.TestCase):
    def view(self, k=C.ZERO):
        v = R.View()
        v.target = [F(100), F(0), F(0)]
        v.k = k
        return v

    def test_arrives_one_call_after_one(self):
        v = self.view()
        n = 0
        while True:
            res, _h, _p = R.look_at(v, 45)
            n += 1
            if res:
                break
        self.assertEqual(v.progress, C.ONE)
        self.assertGreaterEqual(n, 46)
        self.assertEqual(R.look_at(v, 45)[0], 1)
        res, h, pos = R.look_at(v, -45)
        self.assertEqual(res, 0)
        self.assertTrue(C.lt(h, C.ONE))

    def test_turn_factor_slows(self):
        fast, slow = self.view(C.ZERO), self.view(C.ONE)
        R.look_at(fast, 45)
        R.look_at(slow, 45)
        self.assertTrue(C.lt(slow.progress, fast.progress))

    def test_zero_steps_refused(self):
        with self.assertRaises(ValueError):
            R.look_at(self.view(), 0)

    def test_run_task_camera(self):
        v = self.view()
        acts, _ = R.run_task_camera(v, -1, 0, 1, F(-0.9))
        self.assertEqual(acts, [])                       # closing waits for the shop
        v.progress = C.ZERO
        acts, _ = R.run_task_camera(v, -1, 0, 0, F(-0.9))
        self.assertEqual(acts, [('far_clip', R.FAR_CLIP_CLOSE), ('arrived',), ('send', 3)])
        v.progress = F(0.99)
        acts, _ = R.run_task_camera(v, 1, 1, 0, F(-0.1))
        self.assertEqual([a[0] for a in acts], ['apply', 'far_clip', 'far_clip', 'arrived'])


class Apply(unittest.TestCase):
    def test_no_shake_no_draw(self):
        _p, _m, shake, seed, draws = R.camera_apply((0, 0, 0), 0, 0, C.ZERO, 5, 0, 0)
        self.assertEqual((shake, seed, draws), (C.ZERO, 5, 0))

    def test_frozen_shakes_only_with_a_dialog(self):
        self.assertEqual(R.camera_apply((0, 0, 0), 0, 0, F(2), 5, 1, 0)[4], 0)
        pos, _m, shake, seed, draws = R.camera_apply((0, 0, 0), 0, 0, F(2), 5, 1, 1)
        self.assertEqual(draws, 3)
        self.assertEqual(seed, R.lcg(R.lcg(R.lcg(5))))
        self.assertEqual(C.to_float(shake), 1.5)

    def test_matrix_is_rotation(self):
        _p, m, *_ = R.camera_apply((0, 0, 0), 0, -0x3FD3, C.ZERO, 0, 0, 0)
        self.assertEqual((m[0], m[9:]), (C.ONE, [0, 0, 0]))
        self.assertLess(abs(C.to_float(m[1])), 1e-3)   # sin16(0) is not exactly 0


class Gates(unittest.TestCase):
    def test_frozen(self):
        self.assertEqual(R.game_is_frozen(R.Frozen(network=1, paused=7)), 7)
        self.assertEqual(R.game_is_frozen(R.Frozen(controller_out=1)), 1)
        self.assertEqual(R.game_is_frozen(R.Frozen(controller_out=1, dialog=1)), 0)
        self.assertEqual(R.game_is_frozen(R.Frozen(player_select=1, sim_frame=59, paused=1)), 0)
        self.assertEqual(R.game_is_frozen(R.Frozen(cutscene=1, warmup=3)), 3)

    def test_recall(self):
        base = {k: False for k in R.RECALL_CHECKS}
        base.update(slot=2, use=True, b100=True)
        self.assertEqual(R.recall_poll([base]), [2])
        self.assertEqual(R.recall_poll([dict(base, dialog=True)]), [])

    def test_camera_control(self):
        self.assertEqual(R.camera_update_control(0, 1, 0, 0, 0, 0, 0, 0), 1)
        self.assertEqual(R.camera_update_control(0, 1, 0, 0, 0, 1, 0, 0), 0)
        self.assertEqual(R.camera_update_control(0, 0, 0, 0, 0, 0, 0, 0), 0)

    def test_idle_voice(self):
        self.assertEqual(R.idle_voice(5, 0, 0, 0, 1, 2, 9), (5, 9, None))
        self.assertEqual(R.idle_voice(5, 0, 0, 0, 0, 2, 9), (4, 9, None))
        cd, seed, slot = R.idle_voice(2, 0, 0, 0, 0, 3, 9)
        self.assertEqual((cd, seed, slot), (1, R.lcg(9), (R.lcg(9) >> 16) % 3))

    def test_every_site_gates_on_the_dialog(self):
        open_labels = {'skip', 'blocked', 'disabled', 'fallback', 'abort', 'held', 'hidden',
                       'shown+disabled', 'hidden+disabled'}
        passing = {'pause_exit': {}, 'pause_kick': {'active': 2}, 'pause_recall': {'cam_mode': 1},
                   'pause_change': {'cam_mode': 1}, 'warp_menu': {'cam_mode': 1},
                   'player_name': {'network': 1, 'flag400000': 1}, 'compass': {'compass_on': 1},
                   'hud_panel_input': {'cam_mode': 1}, 'hud_panel_button': {'cam_mode': 1},
                   'status_fx': {'model': 1}, 'net_messages': {'network': 1, 'list_on': 1},
                   'idle_voice': {'countdown': 5, 'players': 1}}
        for name in R.SITES:
            if name in ('recall_button', 'is_frozen', 'camera_control', 'camera_shake'):
                continue
            c = dict(passing.get(name, {}))
            closed = R.site_outcome(name, dict(c, dialog=0))
            opened = R.site_outcome(name, dict(c, dialog=1))
            self.assertNotEqual(closed, opened, name)
            self.assertIn(opened, open_labels | {'unchanged'} if name != 'pause_exit' else {'disabled'}, name)
        self.assertEqual(len(R.SITES), 24)


class Box(unittest.TestCase):
    def test_load(self):
        self.assertEqual(R.load_box('intro', 0, 7, 9), 7)
        self.assertEqual(R.load_box('level', 1, 7, 9), 7)
        self.assertEqual(R.load_box('Intro', 0, 7, 9), 9)       # strcmp is case-sensitive
        self.assertEqual(R.load_box('level', 0, 7, 0), 0)

    def test_null_texture_refused(self):
        with self.assertRaises(ValueError):
            R.box_sprite_reads(0)

    def test_buttons(self):
        self.assertEqual(R.init_camera_buttons(1)[R.G_GLYPH_CONFIRM], 0x7E)
        self.assertEqual(R.init_camera_buttons(1)[0x41BFBC], 0x40)
        self.assertEqual(R.init_camera_buttons(0)[R.G_GLYPH_CONFIRM], 0x7B)
        self.assertEqual(R.init_camera_buttons(0)[0x41BFBC], 0x20)
        self.assertEqual(R.init_camera_buttons(2), {0x4F85B4: 0, 0x4F7134: 0})


class Factory(unittest.TestCase):
    def test_keys_are_case_sensitive_after_lowering(self):
        self.assertEqual(R.props_get_str(['autoprop=1'], 'AutoProp'), '1')
        self.assertIsNone(R.props_get_str(['AutoProp=1'], 'AutoProp'))
        self.assertIsNone(R.props_get_str(['autoprop'], 'AutoProp'))
        self.assertEqual(R.props_get_int(['autoprop= 3'], 'AutoProp'), 3)
        self.assertEqual(R.props_get_int(['autoprop=x'], 'AutoProp'), 0)

    def test_order(self):
        self.assertIsNone(R.factory_fallback(['dialogscript=t', 'showname=s', 'key=k']))
        self.assertEqual(R.factory_fallback(['autoprop=1', 'halo2=1']), 'AutoPropLP')
        self.assertEqual(R.factory_fallback(['autoprop=1']), 'AutoProp/Door/Switch')
        self.assertEqual(R.factory_fallback(['autoswitch=1']), 'AutoProp/Door/Switch')
        self.assertEqual(R.factory_fallback(['creaturecontainer=1', 'autoprop=1']), 'CreatureContainer')
        self.assertEqual(R.factory_fallback(['generator=']), 'Generator')
        self.assertEqual(R.factory_fallback(['critter=0', 'smokegen=0']), 'SmokeGen')


class Census(unittest.TestCase):
    def test_records_keep_key_case(self):
        strings = b'\0TestLocation\0name="spk" x\0dialogScript=talk\0'
        table = 8 + 32
        rec = struct.pack('<ihh3f', 1, 32, 0, 0.0, 0.0, 0.0) + struct.pack('<3i', 14, 27, 0)
        blob = struct.pack('<hHi', 1, 0, table) + rec + strings
        got = G.raw_records(blob)
        self.assertEqual(got, [('TestLocation', ['name="spk" x', 'dialogScript=talk'])])
        self.assertEqual(G.reg_name(got[0][1]), 'spk')
        self.assertIsNone(R.factory_fallback(got[0][1]))

    def test_start_calls(self):
        imports = ['startDialog', 'callScript']
        a = [0x2E] + push(lambda o: o['B']) + push(4) + sysreq(1) + [0x30]
        b_start = len(a) * 4
        b = [0x2E] + push(0) + push(1) + push(lambda o: o['npc']) + push(12) + sysreq(0) + [0x30]   # pushed last-first
        s = G.Script(build_script([(0, 'A'), (b_start, 'B')], imports, a + b, ['npc', 'B']))
        self.assertEqual(G.start_calls(s, 'A'), [(1, 0, 'npc')])
        self.assertEqual(G.start_calls(s, 'nope'), [])


if __name__ == '__main__':
    unittest.main()
