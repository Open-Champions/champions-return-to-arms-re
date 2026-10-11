#!/usr/bin/env python3
"""test_ref_skills_a.py - unit tests of tools/ref_skills_a.py that need no game files.

They exercise the model's own logic on made-up memory: the statistics slots on invented
tables, the mana-cost reader on hand-assembled instructions, the weapon-entry rule, the
damage descriptor, the divide rule, attached-spell lookup, the radial damage, and - for the
second pass - Cone of Fire's descriptor, Dismiss Undead's target loop, Shield Bash's turn
target, the Hammer of Wrath's level, the Fire Weapons light and the Wizard Beam's chain.  Whether
the model matches the game is tools/difftest_skills_a.py's business (it needs the
executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402

f32 = C.f32
SKILL, TABLE, CODE = 0x1000, 0x2000, 0x3000
SLOT_FUNCTIONS = {1: 0x3C8218, 2: 0x3C8220, 5: 0x3C82A8, 8: 0x3C82E4, 9: 0x3C85B0, 10: 0x3C85FC, 11: 0x3C8690,
                  12: 0x3C87F0, 13: 0x3C8864, 14: 0x3C88DC, 15: 0x3C88E4}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.mem = RC.Memory()
        self.calls = []
        self.answers = {}
        self.model = SA.Model(self.mem, self)
        for slot, function in SLOT_FUNCTIONS.items():
            self.mem.poke(TABLE + 8 * slot + 4, 4, function)
        self.mem.poke(SKILL + 0x60, 4, TABLE)

    def get(self, name):                        # the callbacks object of the model
        def answer(*args):
            self.calls.append((name, args))
            return self.answers.get(name)
        return answer

    def tier(self, tier, stat, first, base, step):
        offsets = (0xE, 0x18, 0x24) if tier == 1 else (0x38, 0x42, 0x4C)
        self.mem.poke(SKILL + offsets[0] + 2 * stat, 2, first & 0xFFFF)
        self.mem.poke(SKILL + offsets[1] + 2 * stat, 2, base & 0xFFFF)
        self.mem.poke(SKILL + offsets[2] + 4 * stat, 4, f32(step))


class Statistics(Fixture):
    def test_tier1(self):
        self.tier(1, 0, 1, 30, 9.0)
        m = self.model
        self.assertEqual(m.skill_call(SKILL, 10, 0, 0), 0)
        self.assertEqual(m.skill_call(SKILL, 10, 0, 1), 30)
        self.assertEqual(m.skill_call(SKILL, 10, 0, 5), 66)
        self.tier(1, 1, 5, 1, 0.333)
        self.assertEqual(m.skill_call(SKILL, 10, 1, 4), 0)         # below the first level
        self.assertEqual(m.skill_call(SKILL, 10, 1, 7), 2)         # 1 + 0.666 rounds to 2

    def test_negative_values_round_away_from_zero(self):
        self.tier(1, 0, 1, -3, -0.5)
        self.assertEqual(SA.s32(self.model.skill_call(SKILL, 10, 0, 2)), -4)       # -3.5 - 0.5

    def test_tier2_and_cap(self):
        self.tier(1, 0, 1, 100, 10.0)
        self.tier(2, 0, 1, 2, 2.0)
        m = self.model
        self.assertEqual(m.skill_call(SKILL, 11, 0, 30, 0), 60)
        self.assertEqual(m.skill_call(SKILL, 11, 0, 30, 10), 20)       # the level is capped
        self.assertEqual(m.skill_call(SKILL, 11, 0, 0, 10), 0)         # a cap does not revive level 0
        self.tier(2, 0, -1, 0, 0.0)                                    # tier 2 unset: tier 1 answers
        self.assertEqual(m.skill_call(SKILL, 11, 0, 3, 0), 120)
        self.tier(2, 0, -32768, 7, 1.0)                                # any negative first level means unset
        self.assertEqual(m.skill_call(SKILL, 11, 0, 3, 0), 120)

    def test_by_caster_and_by_handle(self):
        self.tier(1, 0, 1, 100, 0.0)
        self.tier(2, 0, 1, 5, 0.0)
        player, monster, node, handle = 0x5000, 0x5100, 0x5200, 0x5300
        self.mem.poke(player + 0xC, 4, 0x60)
        self.mem.poke(monster + 0xC, 4, 0x20)
        m = self.model
        self.assertEqual(m.skill_call(SKILL, 12, 0, 1, player, 0), 100)
        self.assertEqual(m.skill_call(SKILL, 12, 0, 1, monster, 0), 5)
        self.assertEqual(m.skill_call(SKILL, 12, 0, 1, 0, 0), 5)
        self.assertEqual(m.skill_call(SKILL, 13, 0, 1, handle, 0), 5)          # an empty handle
        self.mem.poke(node + 0xC, 4, player)
        self.mem.poke(handle, 4, node)
        self.assertEqual(m.skill_call(SKILL, 13, 0, 1, handle, 0), 100)

    def test_range_plain_and_randomised(self):
        self.tier(1, 0, 1, 30, 0.0)
        m = self.model
        self.assertEqual(m.skill_call(SKILL, 8, 0, 1, 0, f32(0.2)), (24, 36))
        self.assertEqual(m.skill_call(SKILL, 8, 0, 0, 0, f32(0.2)), (1, 1))        # never below 1
        low, high = m.skill_call(SKILL, 8, 0, 1, 1, f32(0.2))
        self.assertEqual(m.draws, 4)                                              # two draws per bound
        self.assertTrue(24 <= low <= 30 <= high <= 36)

    def test_base_init_stats(self):
        self.model.skill_call(SKILL, 9)
        self.assertEqual(self.model.skill_call(SKILL, 10, 3, 4), 9)                # 1 + 2 x (4 - 0)

    def test_mana_cost_shapes(self):
        m, mem = self.model, self.mem
        self.assertEqual(m.mana_cost(SKILL, 7), SA.ONE)                           # the base body
        # addiu a1,a1,-1 ; lui at,0x4000 ; mtc1 at,f2 ; mtc1 a1,f0 ; cvt ; lui at,0x4110 ; mtc1 at,f1 ; mul ; jr ; add
        words = (0x24A5FFFF, 0x3C014000, 0x44811000, 0x44850000, 0x46800020, 0x3C014110, 0x44810800, 0x46020002,
                 0x03E00008, 0x46010000)
        for i, word in enumerate(words):
            mem.poke(CODE + 4 * i, 4, word)
        mem.poke(TABLE + 8 * 5 + 4, 4, CODE)
        self.assertEqual(m.mana_cost(SKILL, 4), f32(15.0))                        # 9 + 2 x 3
        self.tier(1, 4, 1, 55, 4.0)
        thunk = (0x27BDFFF0, 0x0080182D, 0xFFBF0000, 0x24060014, 0x8C620060, 0x24420078)   # slot 15 with n = 20
        for i, word in enumerate(thunk):
            mem.poke(CODE + 0x100 + 4 * i, 4, word)
        mem.poke(TABLE + 8 * 5 + 4, 4, CODE + 0x100)
        self.assertEqual(m.mana_cost(SKILL, 3), f32(63.0))                        # statistic 4 at level 3


class Helpers(Fixture):
    def test_divide_rule(self):
        self.assertEqual(SA.rem(7, 3), 1)
        self.assertEqual(SA.rem(-7, 3), -1)                # truncating, like the machine's div
        self.assertEqual(SA.rem(7, -3), 1)
        self.assertEqual(SA.rem(1234, 0), 1234)            # a zero divisor leaves the dividend
        self.assertEqual(SA.quot(0x10000, 5), 13107)
        self.assertEqual(SA.quot(5, 0), -1)
        self.assertEqual(SA.half_toward_zero(-7), -3)

    def test_descriptor(self):
        self.assertEqual(SA.descriptor(), ('desc', None, None, None, None))
        self.assertEqual(SA.descriptor((0x26, 30, 30, 0)), ('desc', (0x26, 30, 30, 0), None, None, None))
        self.assertEqual(SA.descriptor((0x15, -1, 5, 0))[1], (0x15, 0xFFFF, 5, 0))

    def test_spread_max(self):
        self.assertEqual(SA.spread_max(f32(100.0), 0), f32(100.0))
        self.assertTrue(C.lt(SA.spread_max(f32(100.0), 0xFFFF), f32(120.0)))

    def test_enchant_rule(self):
        m, mem, item = self.model, self.mem, 0x6000
        for k in range(4):
            mem.poke(item + 0x24 + 8 * k, 2, 0xFFFF)
        m.enchant(item, 0x18, 10, 600, 600)
        self.assertEqual([m.s16(item + 0x24 + 2 * j) for j in range(4)], [0x18, 10, 12, 600])
        m.enchant(item, 0x18, 9, 600, 600)                  # a weaker one does not replace it
        self.assertEqual(m.s16(item + 0x26), 10)
        m.enchant(item, 0x18, 45, 31, 31)                   # the aura's limit is compared with the DAMAGE: 10 < 31
        self.assertEqual([m.s16(item + 0x26), m.s16(item + 0x2A)], [45, 31])
        m.enchant(item, 0x18, 50, 31, 31)                   # ... and 45 is not: no refresh
        self.assertEqual(m.s16(item + 0x26), 45)
        m.enchant(item, 0x16, 5, 31, 31)                    # another type takes the next empty slot
        self.assertEqual(m.s16(item + 0x2C), 0x16)
        mem.poke(item + 8, 8, 0x1000000)                    # a thrown weapon is left alone
        m.enchant(item, 0x15, 5, 31, 31)
        self.assertEqual(m.s16(item + 0x34), -1)

    def test_find_spell_by_type(self):
        m, mem = self.model, self.mem
        creature, spells, nodes = 0x7000, (0x7400, 0x7500), (0x7600, 0x7700)
        tables = (0x7800, 0x7900)
        SA.Model.type_info = {0xAAA0: 0x111, 0xBBB0: 0x222}
        for spell, node, table, getter in zip(spells, nodes, tables, (0xAAA0, 0xBBB0)):
            mem.poke(table + 4, 4, getter)
            mem.poke(spell + 0x14, 4, table)
            mem.poke(node + 0xC, 4, spell)
        mem.poke(nodes[0], 4, nodes[1])
        mem.poke(creature + 0x364, 4, nodes[0])
        self.assertEqual(m.find_spell_by_type(creature, 0x222), spells[1])
        self.assertEqual(m.find_spell_by_type(creature, 0x333), 0)
        self.assertEqual(m.carries(creature, 0xAAA0), spells[0])
        mem.poke(nodes[0] + 0xC, 4, 0)                      # a node whose spell is gone is skipped
        self.assertEqual(m.find_spell_by_type(creature, 0x111), 0)

    def test_damage_radial(self):
        m, mem = self.model, self.mem
        table, undead, living = 0x8000, 0x8400, 0x8800
        for obj, kind, x in ((undead, 0x10, 30.0), (living, 0, 10.0)):
            mem.poke(obj + 0xC, 4, 0x20)
            mem.poke(obj + 0x48, 4, table)
            mem.poke(obj + 0xB4, 1, kind)
            mem.poke(obj + 0x10, 4, f32(x))
        self.answers['world_collectObjectsInBox'] = [living, undead]
        m.damage_radial(0, (0, 0, 0), 200, 0xA100900, 0, 0x40, f32(72.0), f32(144.0))
        hits = [args for name, args in self.calls if name == 'Creature.v2']
        self.assertEqual(len(hits), 1)                      # the undead one only
        self.assertEqual(hits[0][0], undead)
        self.assertEqual(hits[0][3], f32(200.0))            # inside the inner radius: the whole amount

    def test_carries_getter_shape(self):
        mem = self.mem
        mem.poke(CODE + 0xC, 4, 0x0C000000 | (0x3CD300 >> 2))
        mem.poke(CODE + 0x18, 4, 0x0C000000 | (0x11A710 >> 2))
        self.assertEqual(SA.carries_getter(self.model.u32, CODE), 0x3CD300)
        self.assertIsNone(SA.carries_getter(self.model.u32, CODE + 0x40))

    def test_tables_are_consistent(self):
        for registry in (SA.SKILL_BODIES, SA.SPELL_BODIES, SA.OBJECT_BODIES):
            for function, method in registry.items():
                self.assertTrue(hasattr(SA.Model, method), '%s at 0x%x' % (method, function))
        self.assertEqual(len(set(SA.MODELLED.values())), len(SA.MODELLED))


class SecondPass(Fixture):
    """The casts and effects added by the second pass, on made-up memory."""
    OBJ_TABLE, OWNER, SPELL, BOLT = 0x8000, 0x9000, 0xA000, 0xB000

    def creature(self, addr, x, y, kind=0x10, flags=0x20):
        mem = self.mem
        mem.poke(addr + 0xC, 4, flags)
        mem.poke(addr + 0x48, 4, self.OBJ_TABLE)
        mem.poke(addr + 0xB4, 1, kind)
        mem.poke(addr + 0x10, 4, f32(x))
        mem.poke(addr + 0x14, 4, f32(y))
        return addr

    def test_cone_of_fire_descriptor(self):
        # a monster's cone at level 2: tier 2 gives 4, a quarter of that is 1, and the maximum - scaled by a
        # quarter a second time - is 0: the range damage_apply's fire entry divides by is v2 - v1 + 1 = 0
        m, mem = self.model, self.mem
        self.tier(1, 0, 1, 380, 11.0)
        self.tier(2, 0, 1, 2, 2.0)
        self.tier(1, 1, 1, 30, 0.2)
        self.tier(2, 1, 1, 30, 0.05)
        owner, victim = self.creature(self.OWNER, 0.0, 0.0), self.creature(0xC000, 40.0, 0.0)
        mem.poke(self.SPELL, 1, 2)
        mem.poke(self.SPELL + 8, 4, SKILL)
        mem.poke(self.SPELL + 0xC, 4, owner)
        mem.poke(RC.G_SIM_FRAME, 4, 1500)                   # a multiple of 15
        self.answers.update({'world_collectObjectsInArc': [victim], 'Creature.v20': 1, 'res_find': 0})
        m.coneoffire_run(self.SPELL, (0, 0, 0), 0)
        hits = [args for name, args in self.calls if name == 'damage_apply']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][6], SA.descriptor((0x15, 1, 0, 0)))
        self.assertEqual(hits[0][5], 0x40)
        # a player's cone at level 1: 380 -> 95, and the maximum is a quarter of 95..114
        del self.calls[:]
        mem.poke(owner + 0xC, 4, 0x60)
        mem.poke(self.SPELL, 1, 1)
        m.coneoffire_run(self.SPELL, (0, 0, 0), 0)
        entry = [args for name, args in self.calls if name == 'damage_apply'][0][6][1]
        self.assertEqual(entry[1], 95)
        self.assertTrue(23 <= entry[2] <= 28 and entry[2] < entry[1])

    def test_dismiss_undead_keeps_the_last_in_box_order(self):
        m, mem = self.model, self.mem
        self.tier(1, 2, 1, 3, 0.25)
        owner = self.creature(self.OWNER, 0.0, 0.0, kind=0, flags=0x60)      # faces along +x (facing 0)
        far, near, mid = (self.creature(0xC000 + 0x400 * i, x, 5.0) for i, x in enumerate((200.0, 50.0, 120.0)))
        self.answers.update({'world_collectObjectsInBox': [far, near, mid], 'Creature.v20': 1, 'trail_create': 7,
                             'res_find': 0, 'sound_playOnObject': 0})
        m.holybolt_ctor(self.BOLT, (0, 0, 0), 0, 5, owner, SKILL)
        self.assertEqual(m.u32(self.BOLT + 0x64), mid)      # not `near`: every undead in front replaces the one before
        self.assertFalse(any(name == 'handle_link' and args[0] == self.BOLT + 0x64 for name, args in self.calls))
        # once one behind the caster has been seen, only a nearer one in front replaces the front one
        behind = self.creature(0xD000, -30.0, 0.0)
        self.answers['world_collectObjectsInBox'] = [near, behind, far, mid]
        m.holybolt_ctor(self.BOLT, (0, 0, 0), 0, 5, owner, SKILL)
        self.assertEqual(m.u32(self.BOLT + 0x64), near)
        # nothing qualifies: no target, and the aim point is 48000 ahead, 36 up
        self.answers['world_collectObjectsInBox'] = []
        m.holybolt_ctor(self.BOLT, (0, 0, 0), 0, 5, owner, SKILL)
        self.assertEqual(m.u32(self.BOLT + 0x64), 0)
        self.assertEqual(m.u32(self.BOLT + 0x68), f32(48000.0))
        self.assertEqual(m.u32(self.BOLT + 0x70), f32(36.0))

    def test_shield_bash_target_is_the_head_entry(self):
        m, mem = self.model, self.mem
        owner = self.creature(self.OWNER, 0.0, 0.0, kind=0, flags=0x60)
        clip, class_def = 0xE000, 0xE100
        mem.poke(owner + 0x24, 4, class_def)
        flagged, plain = self.creature(0xC000, 20.0, 0.0, flags=0x1000020), self.creature(0xC400, 40.0, 0.0)
        self.answers.update({'res_find': clip, 'world_collectObjectsInArc': [flagged, plain]})
        m.shieldbash_ctor(self.SPELL, 3, owner, SKILL)
        self.assertEqual(m.u32(self.SPELL + 0x24), flagged)     # the head, although it is the later entry that qualifies
        self.assertEqual(m.u32(owner + 0x58C), 6)
        self.assertEqual((m.u8(clip + 0x20), m.u32(clip + 0x1C)), (2, 0x3F181040))      # the shared clip header
        self.answers['world_collectObjectsInArc'] = [flagged]
        m.shieldbash_ctor(self.SPELL, 3, owner, SKILL)
        self.assertEqual(m.u32(self.SPELL + 0x24), 0)

    def test_hammer_level_is_one_higher(self):
        m, mem = self.model, self.mem
        self.tier(1, 1, 1, 15, 1.0)
        calls = []
        m.item_parse = lambda text, record: calls.append(text)             # the item tables are game data
        self.answers.update({'res_find': 0, 'sound_playOnObject': 0})
        m.hammer_ctor(self.BOLT, (0, 0, 0), 0x1234, 0, 3, SKILL)
        self.assertEqual(m.u32(self.BOLT + 0xA4), 4)
        self.assertEqual(m.u32(self.BOLT + 0xA8), (15 + 3) * 60)           # statistic 1 at level 4, in frames
        self.assertEqual(calls, [0x550930])
        m.hammer_ctor(self.BOLT, (0, 0, 0), 0, 0, 9, SKILL)
        self.assertEqual(calls[-1], 0x550950)                              # every level above 3 shares one text

    def test_fire_weapons_light(self):
        m, mem = self.model, self.mem
        owner = self.creature(self.OWNER, 0.0, 0.0, kind=0)
        mem.poke(self.SPELL + 0xC, 4, owner)
        mem.poke(RC.G_SIM_FRAME, 4, 1000)
        mem.poke(self.SPELL + 0x18, 4, 1015)                # 15 frames left
        mem.poke(self.SPELL + 0x5C, 4, 0)                   # the opening is long over
        m.fireweapons_run(self.SPELL, (0, 0, 0), 0)
        self.assertAlmostEqual(C.to_float(m.u32(self.SPELL + 0x3C)), 55.0, places=3)    # 15 x (1/30) x 110
        mem.poke(self.SPELL + 0x18, 4, 1000)                # the end: the spell deletes itself
        del self.calls[:]
        m.fireweapons_run(self.SPELL, (0, 0, 0), 0)
        self.assertEqual([name for name, _args in self.calls], ['Spell.v1'])

    def test_wizard_beam_chain(self):
        m, mem = self.model, self.mem
        self.tier(1, 0, 1, 135, 11.0)
        self.tier(1, 1, 1, 8, 0.333)
        owner, target = self.creature(self.OWNER, 0.0, 0.0, kind=0, flags=0x60), self.creature(0xC000, 70.0, 0.0, kind=0)
        mem.poke(target + 0x20, 4, f32(72.0))
        spell = self.SPELL
        mem.poke(spell, 1, 1)
        mem.poke(spell + 8, 4, SKILL)
        mem.poke(spell + 0xC, 4, owner)
        mem.poke(spell + 0x348, 4, f32(16.0))               # what the constructor stores: 2 x statistic 1
        mem.poke(spell + 0x34C, 4, f32(16.0))
        mem.poke(RC.G_SIM_FRAME, 4, 1001)
        self.answers.update({'world_collectObjectsInBox': [], 'res_find': 0})
        m.wizardbeam_run(spell, (0, 0, 0), 0)                # no target: a straight chain of five 16-unit segments
        for i in range(6):
            self.assertAlmostEqual(C.to_float(m.u32(spell + 0x28 + 12 * i)), 16.0 * i, places=3)
            self.assertAlmostEqual(C.to_float(m.u32(spell + 0x2C + 12 * i)), 0.0, places=3)
        self.assertFalse(any(name == 'damage_apply' for name, _args in self.calls))
        # a target near the tip (and nearer than 5 segments from the caster, strictly) on a damage frame: a third of statistic 0, flags 0x100, and the chain is pulled up to it
        mem.poke(RC.G_SIM_FRAME, 4, 1020)
        self.answers.update({'world_collectObjectsInBox': [target], 'Creature.v20': 1, 'model_getSamplePointCount': 0})
        m.wizardbeam_run(spell, (0, 0, 0), 0)
        hits = [args for name, args in self.calls if name == 'damage_apply']
        self.assertEqual(len(hits), 1)
        # 135 x 0.3333333 (the constant is below a third) truncates to 44, not 45
        self.assertEqual((hits[0][0], hits[0][1], hits[0][5], hits[0][8]), (target, owner, 0x100, f32(44.0)))
        self.assertGreater(C.to_float(m.u32(spell + 0x30 + 12 * 5)), 20.0)      # the tip rose toward the target's middle
        self.assertEqual(m.s16(target + 0x96), 0x10)        # the tint


if __name__ == '__main__':
    unittest.main()
