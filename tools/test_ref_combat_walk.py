#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_walk.py that need no game files (they run in CI).

Synthetic fixtures only: actors placed by hand on the authored flat floor with the authored
animation timelines of tools/test_ref_combat_full.py.  The tests pin what
docs/spec/combat-walk.md states: an attack hands control back to walking (and a press
every 12 ticks never does), FullRuntime refuses world_findFreeSpot where a walking player
pins an armed Skelight, and WalkRuntime answers it with ref_objects' search on the same
shared seed and world.  Whether the bodies match the game is tools/difftest_combat_walk.py's
business."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_full as F                     # noqa: E402
import ref_combat_walk as W                     # noqa: E402
import test_ref_combat_runtime as R1            # noqa: E402

fl = C.to_float


def armed(rt):
    p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
    rt.give_weapon(0, dmg=(30, 40), attack=50, dmg_type=8)
    return p


def state(rt, p):
    return rt.model.s32(p + 0x58C)


class AttackThenWalk(unittest.TestCase):
    """Player_run state 1 ends 40 ticks after its swing started when the stick is past 0.8."""

    def run_presses(self, presses, ticks):
        rt = W.WalkRuntime()
        p = armed(rt)
        rt.stick(0, 1.0, 0.0)
        xs, states = [], []
        for t in range(ticks):
            if t in presses:
                rt.press_attack(0)
            rt.tick()
            xs.append(fl(rt.u32(p + 0x10)))
            states.append(state(rt, p))
        return xs, states

    def test_one_swing_then_walking(self):
        xs, states = self.run_presses({30}, 120)
        self.assertEqual(states[30], 1)
        end = next(t for t in range(31, 120) if states[t] == 2)
        self.assertEqual(end, 70)                                       # 40 ticks after the swing
        self.assertTrue(all(s == 2 for s in states[end:]))
        self.assertTrue(all(b > a for a, b in zip(xs[end + 1:], xs[end + 2:])))   # it keeps walking
        self.assertEqual(xs[31:end + 1], [xs[30]] * (end - 30))          # no step during the swing

    def test_a_press_every_12_ticks_never_hands_back(self):
        presses = set(range(24, 400, 12))
        xs, states = self.run_presses(presses, 400)
        self.assertTrue(all(s == 1 for s in states[24:]))
        self.assertEqual(len(set(xs[24:])), 1)

    def test_presses_then_none_walks_again(self):
        presses = set(range(24, 24 + 12 * 6, 12))
        xs, states = self.run_presses(presses, 260)
        end = max(t for t in range(1, 260) if states[t - 1] == 1 and states[t] == 2)
        self.assertTrue(all(s == 2 for s in states[end:]))
        self.assertGreater(xs[-1], xs[end] + 100.0)


class FreeSpotBesideAWalker(unittest.TestCase):
    """A walking player beside an armed Skelight: Creature_moveTo's stuck recovery."""

    TICKS = 700

    def fight(self, rt):
        p = armed(rt)
        s = rt.spawn_skelight((24.0, 24.0, 0.0), facing=0x8000, hp=120.0)
        R1.swing_clips(rt, s)
        return p, s

    def walk(self, rt, t):
        if t < 16:
            rt.stick(0, 0.0, 0.0)
        else:
            rt.stick(0, 1.0 if (t // 60) % 2 == 0 else -1.0, 0.0)

    def test_full_runtime_refuses(self):
        rt = F.FullRuntime()
        self.fight(rt)
        with self.assertRaises(T.Unsupported) as caught:
            for t in range(self.TICKS):
                self.walk(rt, t)
                rt.tick()
        self.assertIn('world_findFreeSpot', str(caught.exception))

    def test_walk_runtime_answers_with_the_shared_search(self):
        rt = W.WalkRuntime()
        p, s = self.fight(rt)
        spots = []
        for t in range(self.TICKS):
            self.walk(rt, t)
            mark = len(rt.trace)
            rt.tick()
            spots += [e for e in rt.trace[mark:] if e and e[0] == 'findFreeSpot']
        self.assertTrue(spots)
        for _name, centre, spread, radius, any_height, pos, ok in spots:
            self.assertEqual((spread, radius, any_height), (72, 12, 0))     # Creature_moveTo's arguments
            self.assertEqual(ok, 1)
            self.assertEqual(pos[2], 0)                                      # the flat floor
            dx, dy = fl(pos[0]) - fl(centre[0]), fl(pos[1]) - fl(centre[1])
            self.assertLessEqual(dx * dx + dy * dy, 72.0 * 72.0)

    def test_the_search_draws_the_shared_seed(self):
        rt = W.WalkRuntime()
        rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, hp=120.0)
        before = rt.u32(T.G_RAND_SEED)
        pos, ok = rt.svc_world_findFreeSpot((0, 0, 0), 72, 12, 0)
        self.assertNotEqual(rt.u32(T.G_RAND_SEED), before)
        self.assertEqual(ok, 1)
        # the creature itself stands at the centre: the found point is clear of it
        dx, dy = fl(pos[0]), fl(pos[1])
        self.assertGreater(dx * dx + dy * dy, 12.0 * 12.0 + 12.0 * 12.0)


if __name__ == '__main__':
    unittest.main()
