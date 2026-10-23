import unittest

import ref_hud_inputs as H


class AutomapInputsTest(unittest.TestCase):
    def test_loader_preserves_unwritten_cells_and_texture_gate(self):
        old = [0x1234] * (H.GRID_SIDE ** 2)
        w, h, origin, grid = H.load_grid(1, 1, 0, -3, 4, 2, 2,
                                        [1, 2, 3, 4], old_grid=old)
        self.assertEqual((w, h, origin), (2, 2, (-3.0, 4.0)))
        self.assertEqual((grid[:3], grid[216:219]), ([1, 2, 0x1234], [3, 4, 0x1234]))
        self.assertEqual(H.load_grid(0, 1, 0, 0, 0, 2, 2, [1, 2, 3, 4],
                                     7, 8, (9.0, 10.0), old)[0:3], (0, 0, (9.0, 10.0)))

    def test_reveal_changes_only_high_nibble_and_keeps_maximum(self):
        grid = [0x002a] * (H.GRID_SIDE ** 2)
        grid[10 * H.GRID_SIDE + 10] = 0xf02a
        result = H.reveal_integer_cell(grid, 20, 20, 10, 10)
        self.assertEqual(result[10 * H.GRID_SIDE + 10], 0xf02a)
        self.assertEqual(result[10 * H.GRID_SIDE + 11] & 0x0fff, 0x02a)
        self.assertEqual(result[10 * H.GRID_SIDE + 19], 0x002a)

    def test_blip_source_order_and_radius(self):
        nearby = [(10, 0), (11, 0x40), (12, 0)]
        players = [(11, 21), (None, 22), (13, 23)]
        self.assertEqual(H.blip_sources(nearby, players, False), [10, 11, 12])
        self.assertEqual(H.blip_sources(nearby, players, True), [10, 12, 21, 23])
        self.assertEqual(H.blip_query_box(100, 200, 300, False),
                         ((-860.0, -760.0, -660.0), (1060.0, 1160.0, 1260.0), 200))

    def test_gold_touch_is_once_and_real_player_only(self):
        pos = (1, 2, 3)
        self.assertEqual(H.gold_touch(0x40, 0, 25, 2, pos),
                         (0, [('coin_sound',), ('add_floater', 2, pos, 25), ('delete',)]))
        self.assertEqual(H.gold_touch(0x40, 0, 0, 2, pos), (0, []))
        self.assertEqual(H.gold_touch(0x20040, 0, 25, 2, pos), (25, []))


if __name__ == '__main__':
    unittest.main()
