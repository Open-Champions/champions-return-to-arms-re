import struct
import unittest

import ref_core as F
import ref_hud_inputs as H
import ref_hud_live as L


def bits(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


class LiveHudTest(unittest.TestCase):
    def test_regen_stops_for_a_copy_and_for_no_health(self):
        hundred, pending, rate = F.from_int(100), F.from_int(12), F.from_int(3)
        mods = [None] * 17
        self.assertEqual(L.regen_health(hundred, hundred, pending, rate, True, 4, 1, mods),
                         (hundred, pending))
        self.assertEqual(L.regen_health(0, hundred, pending, rate, False, 4, 1, mods),
                         (0, pending))
        self.assertEqual(
            L.regen_mana(0, hundred, hundred, pending, rate, False, 1, 2, 1, mods, 5, 1, 4),
            (hundred, pending))

    def test_class_zero_keeps_pending_and_drops_natural_mana(self):
        mana, pending, rate = F.from_int(10), F.from_int(4), F.from_int(4)
        got_mana, got_pending = L.regen_mana(
            F.from_int(20), mana, F.from_int(100), pending, rate, False, 0, 5, 5,
            [None] * 17, 9, 3, 8)
        # The natural term is cleared, so only the rate is added and pending floors at 0.
        self.assertEqual(got_pending, 0)
        self.assertNotEqual(got_mana, mana)

    def test_bar_edges_and_message_alpha(self):
        hundred = F.from_int(100)
        edges = L.bar_edges(12, hundred, hundred, F.from_int(50), hundred, 0, 0, 1100, 1, True)
        self.assertEqual(edges['health'], 27 + 99)
        self.assertEqual(set(edges), {'health', 'experience', 'mana'})
        self.assertNotIn('experience', L.bar_edges(12, hundred, hundred, hundred, hundred,
                                                   0, 0, 1100, 0, True))
        self.assertEqual(list(L.bar_edges(12, hundred, hundred, hundred, hundred,
                                          0, 0, 1100, 1, False)), ['health'])
        self.assertEqual(L.message_alpha(10, 0, 0, 0), 40)
        self.assertEqual(L.message_alpha(32, 0, 0, 0), 3)
        self.assertEqual(L.message_alpha(40, 126, 0, 0), 0x80)
        self.assertEqual(L.message_alpha(20, 15, 1, 0), 15)
        self.assertIsNone(L.show_message(True, True, 0, 180, 0))
        self.assertIsNone(L.show_message(False, True, -1, 180, 0))
        self.assertEqual(L.show_message(False, True, -1, 180, 1)['timer'], 180)
        self.assertEqual(L.tick_message(4, 0, 0, 4, 0, 0), (3, 1))
        self.assertEqual(L.tick_message(4, 0, 0, 4, 1, 0), (3, 0))

    def test_fractional_reveal_keeps_low_bits_at_its_centre(self):
        grid = [0x00AB] * (H.GRID_SIDE * H.GRID_SIDE)
        origin = bits(4)
        result = H.reveal_world(grid, 16, 16, origin, origin, 0, 0)
        centre = result[4 * H.GRID_SIDE + 4]
        self.assertEqual(centre & 0x0FFF, 0x00AB)
        self.assertEqual(centre >> 12, 15)


if __name__ == '__main__':
    unittest.main()
