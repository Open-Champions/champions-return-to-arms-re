import unittest

import ref_core as F
import ref_hud_feeds as H


class AckTest(unittest.TestCase):
    def test_pending_level_opens_the_level_up_panel(self):
        self.assertEqual(H.hud_run_open(set(), 1, 2, 0, True), (1,))
        self.assertEqual(H.hud_run_open(set(), 2, 2, 0, True), (0,))
        self.assertEqual(H.hud_run_open(set(), 5, 3, 0, True), (0,))

    def test_signed_bytes(self):
        self.assertEqual(H.hud_run_open(set(), 0x80, 1, 0, True), (1,))
        self.assertEqual(H.hud_run_open(set(), 1, 0xFF, 0, True), (0,))

    def test_gates_flag_eight_and_health(self):
        for gate in H.ACK_GATES:
            self.assertIsNone(H.hud_run_open({gate}, 1, 2, 0, True))
        self.assertIsNone(H.hud_run_open(set(), 1, 2, 8, True))
        self.assertIsNone(H.hud_run_open(set(), 1, 2, 0, False))

    def test_message_nine_carries_the_earned_level(self):
        self.assertEqual(H.level_ack_message(2, 9), bytes([9, 2, 9]))
        self.assertEqual(H.apply_level_ack(bytes([9, 2, 9])), (2, 9))
        self.assertEqual(H.level_ack_message(0, -1), bytes([9, 0, 0xFF]))


class CallerTest(unittest.TestCase):
    def test_set_info(self):
        self.assertEqual(H.set_info(), {'frames': 180, 'slot': -1, 'force': 0})

    def test_door(self):
        self.assertIsNone(H.door_interact(-10, True, 0, False, False))
        self.assertIsNone(H.door_interact(0, False, 0, False, False))
        self.assertIsNone(H.door_interact(0, True, 1, False, False))
        self.assertIsNone(H.door_interact(0, True, -1, False, False))
        locked = H.door_interact(3, True, 0, False, False)
        self.assertEqual(locked, {'sound': 'default', 'voice': (3, 7), 'message': (180, -1, 0)})
        self.assertEqual(H.door_interact(1, True, 0, True, True)['sound'], 'named')
        self.assertIsNone(H.door_interact(1, True, 0, True, False)['sound'])

    def test_savepoint(self):
        self.assertEqual(H.savepoint_prompt(1, 0, 1, [False], False, 0, 0, 0), (0, None, None))
        self.assertEqual(H.savepoint_prompt(0, 1, 0, [False], False, 0, 0, 0), (0, None, None))
        self.assertEqual(H.savepoint_prompt(0, 0, 1, [False, False], True, 0, 0, 0),
                         (0, 'override', None))
        self.assertEqual(H.savepoint_prompt(0, 0, 1, [False], False, 0, 0, 0), (0, 0x549268, None))
        self.assertEqual(H.savepoint_prompt(0, 0, 1, [False, True], True, 0, 0, 0),
                         (0, 0x549278, None))
        self.assertEqual(H.savepoint_prompt(0, 0, 0, [], False, 1, 0x709, -1), (1, None, 0x549288))
        self.assertEqual(H.savepoint_prompt(0, 0, 0, [], False, 1, 0x708, -1), (1, None, 0x5492a0))
        self.assertEqual(H.savepoint_prompt(0, 0, 0, [], False, 0, 0x709, -1), (1, None, 0x5492b0))

    def test_jumpgate(self):
        self.assertEqual(H.jumpgate_first_prompt(1, 0, False, 0, 0), 'other')
        self.assertEqual(H.jumpgate_first_prompt(0, 1, False, 0, 0), 'stop')
        self.assertEqual(H.jumpgate_first_prompt(0, 0, True, 0, 0), 'stop')
        self.assertEqual(H.jumpgate_first_prompt(0, 0, True, -1, 0), 'message')
        self.assertEqual(H.jumpgate_first_prompt(0, 0, False, 0, 1), 'quiet')

    def test_pickup_has_no_message(self):
        for args in ((False, True), (True, False), (True, True)):
            self.assertNotIn('message', H.pickup(*args)[1])


class NoticeTest(unittest.TestCase):
    def test_low_count(self):
        self.assertEqual([c for c in range(0, 30) if H.low_count(c)], list(range(1, 21)))
        self.assertFalse(H.low_count(0x10000))

    def test_ammo(self):
        self.assertEqual(H.ammo_neutral(True, 5, True), [(6, 0xF0)])
        self.assertEqual(H.ammo_neutral(False, 0, False), [('voice', 5), (3, 0x78)])
        self.assertEqual(H.ammo_attack(True, 5, True), [])
        self.assertEqual(H.ammo_attack(True, 21, False), [])

    def test_thrown_and_swap(self):
        self.assertEqual(H.thrown_release(20), [(7, 0xF0)])
        self.assertEqual(H.thrown_release(21), [])
        self.assertEqual(H.weapon_swap(1, 6), [(7, 0xF0)])
        self.assertEqual(H.weapon_swap(0, 6), [])
        self.assertEqual(H.weapon_swap(1, 4), [])


class IconTest(unittest.TestCase):
    def test_arrow_choice_covers_every_quadrant(self):
        for d in range(-1, 4):
            for angle in (-0x8000, -0x4001, -1, 0, 0x3FFF, 0x4000, 0x7FFF):
                self.assertIn(H.arrow_choice(d, angle), (0, 1, 2, 3))
        self.assertEqual(H.arrow_choice(0, 0), 0)
        self.assertEqual(H.arrow_choice(1, 0), 1)
        self.assertEqual(H.arrow_choice(0, 0x4000), 3)

    def test_register(self):
        self.assertIsNone(H.register_icon((0, 0), 1, None, (0, 0), 0, 0, 0, F.add))
        e = H.register_icon((F.f32(10.0), F.f32(2.0)), 1, True, (F.f32(0.5), F.f32(-2.0)), 3,
                            0x100, 0x200, F.add)
        self.assertEqual((e['x'], e['y'], e['scale']), (F.f32(10.5), F.f32(0.0), H.SCALE_SMALL))
        self.assertEqual(H.pushtrigger_rotate(False, False), 1)
        self.assertEqual(H.pushtrigger_rotate(True, False), 0)

    def test_gate(self):
        self.assertEqual(H.icon_gate(False, 0, False, False, False, 0, 0), (True, False, False))
        self.assertEqual(H.icon_gate(True, 0, False, False, False, 0, 0), (False, True, False))
        self.assertEqual(H.icon_gate(True, -3, True, False, False, 0, 0), (True, False, False))
        self.assertEqual(H.icon_gate(False, 0, False, True, False, 0, 0), (True, False, False))
        self.assertEqual(H.icon_gate(False, 0, False, True, True, 2, 0), (True, False, False))
        self.assertEqual(H.icon_gate(False, 0, False, True, True, 0, 0), (False, False, True))
        self.assertEqual(H.icon_gate(False, 0, False, True, True, 0, -5), (True, False, True))


class TileTest(unittest.TestCase):
    def test_strip_columns(self):
        self.assertEqual(H.strip_columns(0, 30), [(0, 30), (29, 1)])
        self.assertEqual(H.strip_columns(4, 70), [(4, 30), (33, 30), (62, 8)])
        self.assertEqual(H.strip_columns(5, 5), [])

    def test_quad_uses_bottom_right_tile_and_corner_alpha(self):
        src = (0xA << 12) | (3 << 8) | (2 << 5) | 7
        quad = H.tile_quad(0x1200, 0x3400, 0x5600, src)
        self.assertEqual([q[2] for q in quad], [0x12, 0x34, 0x56, 0xA3])
        us = {q[0] for q in quad}
        vs = {q[1] for q in quad}
        self.assertEqual(us, {7 * 160, 7 * 160 + 158})
        self.assertEqual(vs, {3 * 160, 3 * 160 + 158})
        self.assertEqual(quad[0][:2], (7 * 160, 3 * 160 + 158))

    def test_strip_vertices_count(self):
        out = H.strip_vertices(lambda c, r: 0, [4, 5, 6], 10, 5)
        self.assertEqual(len(out), 2 * 4 * 4)

    def test_strip_prim_runs(self):
        self.assertEqual(H.strip_prim_runs(3, 5), [16, 16])
        self.assertEqual(H.strip_prim_runs(1, 30), [])
        self.assertEqual(H.TILE_PRIM & 7, 4)


if __name__ == '__main__':
    unittest.main()
