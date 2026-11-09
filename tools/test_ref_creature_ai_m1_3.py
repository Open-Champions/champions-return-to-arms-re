"""Unit checks of the mission 1-3 creature decision models (no executable)."""
import unittest

import models_creature_ai_m1_3 as MODELS
import ref_creature_ai_m1_3 as R


def run(name, answers=(), **ctx):
    base = dict(state=0, target=1, ev=0, anim=0, clock=100, deadline=50,
                ally=0, seed=1, fields={}, hp=None, holder={})
    base.update(ctx)
    m = R.M(base, answers)
    MODELS.SPECS[name]["model"](m)
    return [e for e in m.events if e[0] not in (
        "processDamage", "baseRun", "updateActive", "stepAnim", "knockback",
        "pickTarget", "pickAlly")]


class Models(unittest.TestCase):
    def test_every_class_has_a_spec_and_entry_table(self):
        self.assertEqual(set(MODELS.SPECS), set(R.CLASSES))
        self.assertEqual(set(MODELS.SET_ENTRY), set(R.CLASSES))
        self.assertEqual(set(MODELS.SLOTS), set(R.CLASSES))

    def test_idle_sight_goes_to_chase(self):
        for name in ("Kobold", "Orc", "Goblin", "Droid", "Froglock",
                     "Amphian", "SeaMonster", "WarWraith"):
            self.assertEqual(run(name, [1])[-1], ("set", 3), name)

    def test_ogre_and_warrior_idle_sight_goes_to_wander(self):
        for name in ("Ogre", "Warrior", "Clockwork"):
            self.assertEqual(run(name, [1]), [("sight", 0), ("set", 1)], name)

    def test_kobold_tough_melee_flags(self):
        events = run("Kobold", state=6, ev=1, fields={0x3CC: 1})
        self.assertEqual(events[0], ("hitInArc", 0.0, 24.0, 0, 6000, 11, 22, 33, 0x440008))

    def test_ogre_blocked_swing_uses_literal_damage(self):
        events = run("Ogre", state=7, ev=1)
        self.assertEqual(events[0], ("hitAll", 0.0, 60.0, 0, 6000, 1, 5, 33, 0x100001))

    def test_wraith_drain_is_offered_once_clock_passes(self):
        self.assertEqual(run("WarWraith", [1], state=3, fields={0x3CC: 99})[-1], ("set", 7))
        self.assertEqual(run("WarWraith", [1], state=3, fields={0x3CC: 100})[-1], ("set", 6))

    def test_census_counts(self):
        hostile = sum(count for level in R.CREATURES.values()
                      for count, _size, _ctor in level.values())
        self.assertEqual(hostile, 807)


if __name__ == "__main__":
    unittest.main()
