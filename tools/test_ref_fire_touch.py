"""Synthetic tests of tools/ref_fire_touch.py (no game files needed).

The figures are what the model gives; tools/difftest_fire_touch.py is where the model is
compared with the original."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_combat as R                          # noqa: E402
import ref_fire_touch as F                      # noqa: E402

FX_FIRE = R.FX_FIRE


def world(frame=640, difficulty=3, pvp=0):
    w = R.World(seed=0x1234)
    w.frame, w.difficulty, w.pvp_a = frame, difficulty, pvp
    w.players = [R.PlayerRec() for _ in range(4)]
    w.num_players = 4
    return w


def creature(w, tag='v', flags=0x20, fire_res=R.ZERO, burning=R.ZERO, armor=0):
    obj = R.Obj(tag=tag, flags=flags, cls='Creature')
    obj.res = [fire_res] + [R.ZERO] * 4
    obj.status = [burning] + [R.ZERO] * 4
    obj.armor = armor
    obj.hp = obj.max_hp = R.f32(100.0)
    if flags & 0x40:
        obj.slot = len([p for p in w.players if p.obj is not None])
        w.players[obj.slot].obj = obj
    return obj


def fire(owner=None):
    obj = R.Obj(tag='fire', flags=0x420C, cls='Third')
    if owner is not None:
        obj.owner_link, obj.owner = True, owner
    return obj


def hits(w):
    return [e for e in w.events if e[0] == 'take_damage']


class TouchEntry(unittest.TestCase):
    def test_player_value_from_difficulty(self):
        for difficulty, value in ((2, 2), (3, 3), (4, 4), (5, 5), (1, 1), (0, 1), (-1, 1), (6, 1), (9, 1)):
            self.assertEqual(F.touch_entry(0x60, difficulty)[0], (0x15, value, value, 0))

    def test_creature_and_other(self):
        self.assertEqual(F.touch_entry(0x20, 4)[0], (0x15, 8, 8, 0))
        self.assertIsNone(F.touch_entry(0x1, 4))
        self.assertEqual(F.touch_entry(0x40, 4)[0], (0x15, 4, 4, 0))     # 0x40 is tested first


class Touch(unittest.TestCase):
    def test_only_on_frames_divisible_by_twenty(self):
        for frame, acts in ((641, False), (630, False), (660, True), (0, True), (-20, True)):
            w = world(frame)
            v = creature(w)
            self.assertEqual(F.loosefire_touch(w, fire(), v, lambda o, t: 1) is not None, acts)
            if not acts:
                self.assertEqual(w.seed.draws, [])

    def test_creature_alone_seven_draws(self):
        w = world()
        v = creature(w)
        self.assertEqual(F.loosefire_touch(w, fire(), v, lambda o, t: 1), 1)
        self.assertEqual(len(w.seed.draws), 7)              # hit, four chance rolls, 0x15, second roll
        self.assertEqual(hits(w), [('take_damage', 'v', R.f32(8.0), 'fire', F.TOUCH_FLAGS)])
        self.assertEqual(v.status[0], R.TWO)
        self.assertIn(('fx', FX_FIRE, 'v'), w.events)
        self.assertIn(('status_source', 'v', None), w.events)
        self.assertFalse(any(e[0] in ('text', 'pool') for e in w.events))   # 0x1000000: no number

    def test_armour_does_not_change_it(self):
        w = world()
        v = creature(w, armor=3000)
        F.loosefire_touch(w, fire(), v, lambda o, t: 1)
        self.assertEqual(hits(w)[0][2], R.f32(8.0))
        self.assertEqual(len(w.seed.draws), 7)

    def test_resistance(self):
        for res, amount, burn in ((0.25, 6.0, 1.5), (1.0, 0.0, 0.0), (0.5, 4.0, 1.0)):
            w = world()
            v = creature(w, fire_res=R.f32(res))
            F.loosefire_touch(w, fire(), v, lambda o, t: 1)
            self.assertEqual(hits(w)[0][2], R.f32(amount))
            self.assertEqual(v.status[0], R.f32(burn))
            self.assertEqual(F.burn_after_touch(R.f32(res)), R.f32(burn))
            self.assertEqual(any(e[0] == 'status_source' for e in w.events), burn > 0)

    def test_already_burning_no_new_fire_effect_and_no_stacking(self):
        w = world()
        v = creature(w, burning=R.f32(0.5))
        F.loosefire_touch(w, fire(), v, lambda o, t: 1)
        self.assertNotIn(('fx', FX_FIRE, 'v'), w.events)
        self.assertEqual(v.status[0], R.TWO)                # a store, not 2.5

    def test_player_toucher(self):
        for difficulty, amount in ((3, 3.0), (0, 1.0), (5, 5.0)):
            w = world(difficulty=difficulty)
            v = creature(w, flags=0x60)
            F.loosefire_touch(w, fire(), v, lambda o, t: 1)
            self.assertEqual(hits(w)[0][2], R.f32(amount))
            self.assertEqual(len(w.seed.draws), 7)

    def test_player_toucher_pvp_a_halves(self):
        w = world(pvp=1)
        v = creature(w, flags=0x60)
        F.loosefire_touch(w, fire(), v, lambda o, t: 1)
        self.assertEqual(hits(w)[0][2], R.f32(1.5))

    def test_non_creature_empty_descriptor(self):
        w = world()
        v = R.Obj(tag='v', flags=0x1, cls='Third')
        F.loosefire_touch(w, fire(), v, lambda o, t: 1)
        self.assertEqual(len(w.seed.draws), 1)              # the base roll of a non-creature
        self.assertEqual(hits(w)[0][2], R.ZERO)

    def test_owner_says_not_an_enemy(self):
        w = world()
        owner = creature(w, 'o')
        v = creature(w)
        self.assertIsNone(F.loosefire_touch(w, fire(owner), v, lambda o, t: 0))
        self.assertEqual(w.seed.draws, [])
        self.assertEqual(w.events, [('enemy20', 'o', 'v')])

    def test_owner_without_creature_flag_is_ignored(self):
        w = world()
        prop = R.Obj(tag='prop', flags=0x1, cls='Third')
        v = creature(w)
        F.loosefire_touch(w, fire(prop), v, lambda o, t: 0)
        self.assertEqual(hits(w)[0][3], 'fire')
        self.assertNotIn('enemy20', [e[0] for e in w.events])

    def test_player_owner_is_the_attacker_and_the_burn_source(self):
        w = world()
        p = creature(w, 'p', flags=0x60)
        v = creature(w)
        F.loosefire_touch(w, fire(p), v, lambda o, t: 1)
        self.assertEqual(hits(w)[0][3], 'p')
        self.assertIn(('status_source', 'v', 'p'), w.events)
        self.assertEqual(len(w.seed.draws), 8)              # plus the thrower's stun roll


class BurnTick(unittest.TestCase):
    def test_monster(self):
        w = world(672)
        v = creature(w, burning=R.TWO)
        F.burn_tick(w, v)
        self.assertEqual([e[2] for e in hits(w)], [R.ONE, R.ZERO])   # the 0x800000 delivery, then 0
        self.assertEqual(v.status[0], R.TWO)                # 0x10000000: the tick does not set the burn
        self.assertEqual(len(w.seed.draws), 8)              # seven, and the number's FlyingText
        self.assertIn(('text', 1, 0, 0, 0, 0), w.events)

    def test_resisted_monster_still_takes_one(self):
        w = world(672)
        v = creature(w, fire_res=R.f32(0.25), burning=R.TWO)
        F.burn_tick(w, v)
        self.assertEqual(hits(w)[0][2], R.ONE)              # 0.75 accumulated, delivered as 1.0

    def test_player_draws_its_range_and_its_own_stun_roll(self):
        w = world(672)
        v = creature(w, flags=0x60, burning=R.TWO)
        F.burn_tick(w, v, 40)
        self.assertEqual(len(w.seed.draws), 9)              # range, seven, the stun roll
        self.assertEqual(hits(w)[0][3], 'v')

    def test_frames(self):
        self.assertEqual(F.burn_tick_frames(640, R.TWO), [672, 704, 736])
        self.assertEqual(F.burn_tick_frames(600, R.TWO), [608, 640, 672, 704])
        self.assertEqual(F.burn_tick_frames(640, R.ZERO), [])


if __name__ == '__main__':
    unittest.main()
