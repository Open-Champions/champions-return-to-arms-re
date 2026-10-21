#!/usr/bin/env python3
"""Logic checks for tools/ref_arena_modes.py.  Agreement with the executable is
tools/difftest_arena_modes.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_arena_modes as A          # noqa: E402
from ref_core import ONE, TWO, ZERO, from_int, neg, s16          # noqa: E402


class Killer(object):
    def __init__(self, flags, slot=0, owner=0):
        self.flags, self.slot, self.owner = flags, slot, owner


def point(x, y, z, angle):
    return (from_int(x), from_int(y), from_int(z), angle & 0xFFFF)


class ArenaRules(unittest.TestCase):
    def test_lcg_step(self):
        seed, draw = A.lcg(1)
        self.assertEqual(seed, (0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)
        self.assertEqual(draw, seed >> 16)

    def test_kill_choices_and_wrap(self):
        self.assertEqual([A.kill_choice(i) for i in (0, 1, 2, 9)], [5, 10, 25, 25])
        slots = [A.Slot(lives=1)]
        A.lose_life(slots[0], mode_a=False)
        A.lose_life(slots[0], mode_a=False)
        self.assertEqual(s16(slots[0].lives), -1)
        A.lose_life(A.Slot(kills=0), mode_a=True)
        dead = A.Slot(kills=0)
        A.lose_life(dead, mode_a=True)
        self.assertEqual(dead.kills, 0xFFFF)

    def test_reset_and_scoring(self):
        slots = [A.Slot(kills=4, lives=9, snapshot=3, timer=ONE), A.Slot()]
        self.assertEqual(A.reset_scores(slots, True), A.K_MOVE_NET)
        self.assertEqual(A.reset_scores(slots, False), A.K_MOVE_OFF)
        self.assertTrue(all(s.lives == 2 and s.kills == 0 and s.timer == TWO for s in slots))
        pet = Killer(0x20, owner=1)
        A.add_kill(slots, pet, 5, True, 2)
        self.assertEqual(slots[1].kills, 1)
        A.add_kill(slots, Killer(0x20, owner=0xFF), 1, True, 2)
        self.assertEqual(slots[0].kills, 0)          # owner < 0, two players: nobody
        A.add_kill(slots, None, 1, True, 1)
        self.assertEqual(slots[0].kills, 1)          # the only player is credited
        A.add_kill(slots, Killer(0x60, slot=0), 0, True, 2)
        self.assertEqual(slots[0].kills, 1)          # amount 0 in mode A is ignored
        slots[0].lives = 2
        self.assertEqual(A.on_killed(slots, 0, Killer(0x60, slot=0), False, 2), 'suicide')
        self.assertEqual(s16(slots[0].lives), 1)
        self.assertEqual(A.on_killed(slots, 0, Killer(0x60, slot=1), False, 2), 'life')
        self.assertEqual(A.on_killed(slots, 0, None, True, 1), 'kill')
        self.assertEqual(A.on_killed(slots, 0, Killer(0x20000), True, 1, prediction=True), 'ignore')

    def test_respawn_gates(self):
        slot = A.Slot(lives=0)
        self.assertTrue(A.respawn_allowed(slot, False, True, 0))
        slot.lives = 0xFFFF
        self.assertFalse(A.respawn_allowed(slot, False, True, 0))
        self.assertTrue(A.respawn_allowed(slot, True, True, 0))
        self.assertFalse(A.respawn_allowed(A.Slot(lives=2), False, True, 1))
        self.assertFalse(A.respawn_allowed(A.Slot(lives=2), False, False, 0))

    def test_overlay_and_hermite(self):
        self.assertTrue(A.overlay_draws(ZERO, 0))
        self.assertFalse(A.overlay_draws(TWO, 0))
        self.assertFalse(A.overlay_draws(TWO, 4))
        p0 = [from_int(1), from_int(2), from_int(3)]
        p1 = [from_int(4), from_int(5), from_int(6)]
        m0 = [from_int(7), from_int(8), from_int(9)]
        m1 = [from_int(10), from_int(11), from_int(12)]
        self.assertEqual(A.hermite(ZERO, p0, p1, m0, m1), p0)
        self.assertEqual(A.hermite(ONE, p0, p1, m0, m1), p1)
        slot = A.Slot(lives=2, snapshot=0, timer=ZERO)
        A.tick_overlay([slot])
        self.assertNotEqual(slot.timer, ZERO)
        self.assertEqual(slot.snapshot, 0)
        slot.timer = TWO
        A.tick_overlay([slot])
        self.assertEqual(slot.timer, TWO)
        self.assertEqual(A.overlay_anchor_x(100, A.K_259), A.K_259)
        self.assertEqual(A.overlay_anchor_x(400, A.K_259), neg(A.K_259))
        self.assertEqual(A.overlay_anchor_x(100, neg(A.K_259)), neg(A.K_259))

    def test_waves(self):
        count, quot, rem = A.spawn_budget(0, 1)
        self.assertEqual((count, quot, rem), (2, 0, 0))
        self.assertEqual(A.monster_level(0), A.K_FIVE)
        big, _, _ = A.spawn_budget(300, 4)
        self.assertEqual(big, 10 + 4 - 1)
        record = bytes((0x30, 3, 1, 0, 0, 0))
        self.assertEqual(A.recipe_groups(record, 0, 4), [3, 3, 3, 3])
        # high nibble 3, remainder 1 -> 2 groups; 5 monsters -> 3 of class 3, then 2 of class 1
        self.assertEqual(A.recipe_groups(record, 1, 5), [3, 3, 3, 1, 1])
        self.assertEqual(A.recipe_groups(record, 4, 5), [])
        self.assertEqual(A.level_record_index(2, 5), 1)
        self.assertEqual(A.mode_a_next_index(12, 4), 4)
        self.assertEqual(A.mode_a_next_index(0, 4), 1)
        self.assertEqual(A.round_expired(0, False), 'level')
        self.assertEqual(A.round_expired(2, False), 'wave')
        self.assertEqual(A.round_expired(2, True), 'level')
        self.assertTrue(A.intermission_done(A.INTERMISSION_OFFLINE, False))
        self.assertFalse(A.intermission_done(A.INTERMISSION_OFFLINE, True))
        self.assertEqual(A.low_nibble(0x35), 5)
        self.assertEqual(A.high_nibble(0x42), 4)

    def test_pick_and_damage_rules(self):
        points = [point(0, 0, 5, 0x1000), point(128, 0, 1, 0x2000), point(256, 0, 9, 0x0100)]
        focus = (ZERO, ZERO, ZERO)
        searches = []

        def search(centre, spread, radius):
            searches.append((spread, radius))
            return [centre[0], centre[1], centre[2]], 1

        pos, facing, _seed = A.pick_spawn(0, 1, points, 1, False, 0, True, focus, 1, search, focus)
        self.assertEqual(searches, [])
        index = A.lcg(1)[1] % 3
        self.assertEqual(pos, [points[index][0], points[index][1], points[index][2]])
        self.assertEqual(facing, s16(points[index][3] + 0x4000))
        searches.clear()
        pos, facing, _seed = A.pick_spawn(0, 0, points, 7, False, 0, False, focus, 0, search, (from_int(3), from_int(4), from_int(5)))
        # 128 is inside 240, 256 is outside, so the draw is modulo 2 (origin and 128).
        self.assertIn(pos[0], (points[0][0], points[1][0]))
        self.assertNotEqual(pos[0], points[2][0])
        far = [point(256, 0, 0, 0)]
        searches.clear()
        pos, facing, _seed = A.pick_spawn(0, 0, far, 1, False, 0, False, focus, 0, search,
                                           (from_int(3), from_int(4), from_int(5)))
        self.assertEqual(searches, [(0x48, 0x18)])
        self.assertEqual(facing, 0)
        self.assertEqual(pos[0], from_int(3))
        bound = A.armour_bound(from_int(100), 300)
        self.assertNotEqual(bound, from_int(100))
        self.assertEqual(A.pvp_half(from_int(100)), from_int(50))
        self.assertTrue(A.spell_arena_flag(61))
        self.assertFalse(A.spell_arena_flag(60))
        self.assertTrue(A.spell_arena_tint(30))
        self.assertFalse(A.spell_arena_tint(29))
        self.assertFalse(A.spell_arena_tint(-1))
        gold, budget, bought = A.buy_life(100, 100)
        self.assertEqual((gold, budget, bought), (0, 200, True))
        self.assertFalse(A.buy_life(99, 100)[2])


if __name__ == '__main__':
    unittest.main()
