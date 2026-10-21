#!/usr/bin/env python3
"""test_ref_holder_slots.py - unit tests of tools/ref_holder_slots.py that need no game files.

Made-up memory only: the gates and arguments of the drawing slots 18-20 and of
creature_drawHeldPart, the effect update slots 21/22 (its gates, the 'attacking' range,
no stores, no draws; Weapon2's second hand), and the save/load slots 23/24 (layouts,
sizes, the element rebuilt with a shared draw, element 5 lost).  Whether the model
matches the game is tools/difftest_holder_slots.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_weapon_holder as WH                  # noqa: E402
import ref_holder_slots as HS                   # noqa: E402

f32 = C.f32
H, CRE, DEF, SKILL, STABLE, CTABLE, HTABLE, BUF, REC = (0x100000, 0x110000, 0x120000, 0x130000, 0x140000,
                                                       0x150000, 0x160000, 0x170000, 0x180000)
# slot 8 / slot 16 bodies of each class (Observed in the game's tables)
CLASS_8_16 = {'Weapon1': (0x11AFF0, 0x11B148), 'WeaponShield': (0x3C2500, 0x3C25C0),
              'Weapon2': (HS.W2_SET_ELEMENT, HS.W2_GET_ELEMENT)}


class Fixture(unittest.TestCase):
    cls = 'Weapon1'

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.answers = {'Skill.v11': 100, 'Creature.v16': 0xC00080, 'isNearView': 1,
                        'model_getAttachPoint': (1, 2, 3), 'model_getAttachWorldMatrix': tuple(range(12)),
                        'model_draw': 0, 'model_drawPart': 0, 'fx_modelStatusEffects': 0}
        self.model = HS.Model(self.mem, self)
        poke = self.mem.poke
        poke(SKILL + 0x60, 4, STABLE)
        for index in (12, 13, 14, 25, 26):
            poke(WH.G_SKILL_TABLE + 4 * index, 4, SKILL)
        poke(RC.G_LEVEL_MONSTER_LEVEL, 4, f32(10.0))
        poke(RC.G_RAND_SEED, 4, 0)
        for desc in (H + 0x50, H + HS.DESC2):
            for k in range(4):
                poke(desc + 0x24 + 8 * k, 2, 0xFFFF)
        # the holder's table: slots 8 and 16 the class's bodies
        set8, get16 = CLASS_8_16[self.cls]
        poke(H, 4, HTABLE)
        poke(HTABLE + 8 * 8 + 4, 4, set8)
        poke(HTABLE + 8 * 16 + 4, 4, get16)
        # a creature: table +0x48 (slot 16 adjust 0), position, facing, scale
        poke(CRE + 0x48, 4, CTABLE)
        for k, v in enumerate((10.0, 20.0, 30.0)):
            poke(CRE + 0x10 + 4 * k, 4, f32(v))
        poke(CRE + 0x38, 2, 0xC000)
        poke(CRE + 0xDC, 4, f32(1.25))
        poke(CRE + 0x24, 4, DEF)
        for part in range(0x100):
            poke(DEF + 8 * part + 4, 4, REC + 0x20 * part)
            poke(REC + 0x20 * part + 0x13, 1, part % 7)

    def get(self, name):
        value = self.answers[name]
        return value if callable(value) else (lambda *args: value)

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]

    def names(self):
        return [n for n, _a in self.model.calls]


class Drawing(Fixture):
    def test_slot_18_reads_the_part_word_and_the_next_one(self):
        self.mem.poke(H + 4, 1, 1)
        self.mem.poke(H + 8, 1, 5)
        self.model.entry(0x11B198, H, DEF, 0x77, 0x88)
        self.assertEqual(self.named('model_drawPart'),
                         [(REC + 0xA0, REC + 0xC0, 0, 0x77, 0x88, 0xFFFFFFFF, 0xFFFFFFFF, 0)])

    def test_slot_18_gates(self):
        self.mem.poke(H + 8, 1, 5)
        for bits, d, parent, chain in ((0, DEF, 1, 1), (1, 0, 1, 1), (1, DEF, 0, 1), (1, DEF, 1, 0)):
            self.mem.poke(H + 4, 1, bits)
            self.model.entry(0x11B198, H, d, parent, chain)
        self.mem.poke(H + 4, 1, 1)
        self.mem.poke(H + 8, 1, 0)
        self.model.entry(0x11B198, H, DEF, 1, 1)
        self.assertEqual(self.model.calls, [])

    def test_two_handed_slot_18_draws_the_hand_2_part(self):
        self.mem.poke(H + 4, 1, 2)
        self.mem.poke(H + 0x98, 1, 3)
        self.model.entry(0x11BE40, H, DEF, 1, 2)
        self.assertEqual([a[0] for a in self.named('model_drawPart')], [REC + 0x60])

    def test_slot_19_ignores_the_holder_part(self):
        self.mem.poke(H + 4, 1, 1)
        self.model.entry(0x11B208, H, 0x11, 0x22, 0x33, 0x44)
        self.model.entry(0x11B208, H, 0x11, 0x22, 0x33, 0)
        self.assertEqual(self.named('model_drawPart'), [(0x11, 0x22, 0, 0x33, 0x44, 0xFFFFFFFF, 0xFFFFFFFF, 0)])

    def test_draw_held_part_calls(self):
        self.mem.poke(H + 4, 1, 1)
        self.mem.poke(H + 8, 1, 3)
        self.mem.poke(CRE + 0x220, 8, 0x1122334455667788)
        self.model.entry(0x11B270, H, CRE)
        self.assertEqual(self.names(), ['Creature.v16', 'model_getAttachPoint', 'Creature.v16',
                                        'model_getAttachWorldMatrix', 'model_draw'])
        pos = self.model.vec(CRE + 0x10)
        self.assertEqual(self.named('model_getAttachPoint'),
                         [(f32(1.25), 0xC00080, pos, 0xFFFFC000, CRE + 0x114, 3, 0)])
        self.assertEqual(self.named('model_draw'), [(REC + 0x60, REC + 0x60, 1, (1, 2, 3), tuple(range(12)),
                                                     CRE + 0x114, (0x55667788, 0x11223344), 0, 0)])
        self.assertEqual(self.model.writes, [])

    def test_draw_held_part_negative_bone(self):
        self.mem.poke(REC + 0x60 + 0x13, 1, 0x80)
        self.model.draw_held_part(H + 4, 3, CRE)
        self.model.draw_held_part(H + 4, 0, CRE)
        self.model.draw_held_part(H + 4, 3, 0)
        self.assertEqual(self.model.calls, [])


class Effects(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.mem.poke(H + 4, 1, 1)
        self.mem.poke(H + 8, 1, 2)

    def test_full_call(self):
        self.mem.poke(CRE + 0x232, 2, 8)
        self.model.entry(0x11B2A8, H, DEF, CRE, f12=f32(0.5))
        self.assertEqual(self.names(), ['isNearView', 'Creature.v16', 'fx_modelStatusEffects'])
        pos = self.model.vec(CRE + 0x10)
        self.assertEqual(self.named('isNearView'), [(CRE + 0x10, pos, HS.NEAR_VIEW_RADIUS)])
        self.assertEqual(self.named('fx_modelStatusEffects'),
                         [(f32(0.5), f32(1.25), H + 0x50, REC + 0x40, H + 0xC, pos, 0xFFFFC000, 0xC00080,
                           CRE + 0x114, 1, 0, 0)])
        self.assertEqual((self.model.writes, self.model.draws), ([], 0))

    def test_attacking_is_states_6_to_15(self):
        for state, flag in ((5, 0), (6, 1), (15, 1), (16, 0), (0xFFFF, 0), (0, 0)):
            self.model.calls = []
            self.mem.poke(CRE + 0x232, 2, state)
            self.model.entry(0x11B2A8, H, DEF, CRE, f12=0)
            self.assertEqual(self.named('fx_modelStatusEffects')[0][9], flag, state)

    def test_gates(self):
        self.answers['isNearView'] = 0
        self.model.entry(0x11B2A8, H, DEF, CRE, f12=0)
        self.assertEqual(self.names(), ['isNearView'])
        self.answers['isNearView'] = 1
        self.model.calls = []
        self.mem.poke(CRE + 0x231, 1, 8)
        self.model.entry(0x11B2A8, H, DEF, CRE, f12=0)
        self.assertEqual(self.names(), ['isNearView'])
        self.mem.poke(CRE + 0x231, 1, 0)
        self.model.calls = []
        self.mem.poke(CRE + 0xC, 4, 2)                          # hidden: not even the view test
        self.model.entry(0x11B2A8, H, DEF, CRE, f12=0)
        self.mem.poke(CRE + 0xC, 4, 0)
        self.model.entry(0x11B2A8, H, 0, CRE, f12=0)
        self.model.entry(0x11B2A8, H, DEF, 0, f12=0)
        self.mem.poke(H + 8, 1, 0)
        self.model.entry(0x11B2A8, H, DEF, CRE, f12=0)
        self.assertEqual(self.model.calls, [])

    def test_slot_22_takes_the_model_word_and_not_the_part(self):
        self.mem.poke(H + 8, 1, 0)
        self.model.entry(0x11B3E8, H, 0x4242, CRE, f12=0)
        self.assertEqual(self.named('fx_modelStatusEffects')[0][3], 0x4242)

    def test_weapon2_second_hand(self):
        self.mem.poke(H + 4, 1, 3)
        self.mem.poke(H + 0x98, 1, 4)
        self.model.entry(0x118058, H, DEF, CRE, f12=0)
        fx = self.named('fx_modelStatusEffects')
        self.assertEqual([(a[2], a[3], a[4]) for a in fx], [(H + 0x50, REC + 0x40, H + 0xC),
                                                            (H + 0xE0, REC + 0x80, H + 0x9C)])
        self.assertEqual(len(self.named('isNearView')), 2)


class SaveLoad(Fixture):
    def test_weapon1_save(self):
        self.mem.poke(H + 4, 1, 0x81)
        self.mem.poke(H + 8, 1, 0x60)
        self.mem.poke(H + 0x50 + 0x24 + 8, 2, 0x1F)
        self.assertEqual(self.model.entry(0x11B510, H, BUF), 3)
        self.assertEqual([self.mem.load(BUF + k, 1) for k in range(3)], [0x81, 0x60, 6])

    def test_weapon1_load_rebuilds_the_element(self):
        for k, v in enumerate((1, 0x52, 2)):
            self.mem.poke(BUF + k, 1, v)
        self.assertEqual(self.model.entry(0x11B580, H, BUF), 3)
        self.assertEqual((self.mem.load(H + 4, 1), self.mem.load(H + 8, 1)), (1, 0x52))
        self.assertEqual(self.mem.load(H + 0x50 + 0x24, 2), 0x16)
        self.assertEqual(self.model.draws, 1)
        self.assertEqual(self.named('Skill.v11'), [(SKILL, 0, 10, 0)])

    def test_element_0_frees_without_a_draw_and_5_builds_kind_5(self):
        self.mem.poke(H + 0x50 + 0x24, 2, 0x15)
        self.mem.poke(BUF + 2, 1, 0)
        self.model.entry(0x11B580, H, BUF)
        self.assertEqual((self.mem.load(H + 0x50 + 0x24, 2), self.model.draws), (0xFFFF, 0))
        self.mem.poke(BUF + 2, 1, 5)                            # never written by a save
        self.model.entry(0x11B580, H, BUF)
        self.assertEqual(self.mem.load(H + 0x50 + 0x24, 2), 0x26)

    def test_round_trip_table(self):
        for element, (kind, ident) in HS.ROUND_TRIP.items():
            self.mem.poke(BUF + 2, 1, element)
            self.model.entry(0x11B580, H, BUF)
            got = self.mem.load(H + 0x50 + 0x24, 2)
            self.assertEqual(got, 0xFFFF if ident is None else ident)
            self.model.entry(0x11B510, H, BUF + 8)
            self.assertEqual(self.mem.load(BUF + 10, 1), element)


class SaveLoadShield(Fixture):
    cls = 'WeaponShield'

    def test_layout(self):
        self.mem.poke(H + 4, 1, 3)
        self.mem.poke(H + 8, 1, 0x5E)
        self.mem.poke(H + 0x98, 1, 0x62)
        self.assertEqual(self.model.entry(0x11BFB8, H, BUF), 4)
        self.assertEqual([self.mem.load(BUF + k, 1) for k in range(4)], [3, 0x5E, 0, 0x62])
        self.mem.poke(BUF + 3, 1, 0x60)
        self.assertEqual(self.model.entry(0x11C048, H, BUF), 4)
        self.assertEqual(self.mem.load(H + 0x98, 1), 0x60)


class SaveLoadWeapon2(Fixture):
    cls = 'Weapon2'

    def test_layout_and_two_elements(self):
        for k, v in enumerate((3, 0x52, 1, 0x54, 3)):
            self.mem.poke(BUF + k, 1, v)
        self.assertEqual(self.model.entry(0x11BB70, H, BUF), 5)
        self.assertEqual((self.mem.load(H + 0x50 + 0x24, 2), self.mem.load(H + 0xE0 + 0x24, 2)), (0x15, 0x17))
        self.assertEqual(self.model.draws, 2)
        self.assertEqual(self.model.entry(0x11BAC0, H, BUF + 8), 5)
        self.assertEqual([self.mem.load(BUF + 8 + k, 1) for k in range(5)], [3, 0x52, 1, 0x54, 3])

    def test_slot_8_hand_0_builds_both(self):
        self.model.entry(HS.W2_SET_ELEMENT, H, 0, 0x104)
        self.assertEqual((self.mem.load(H + 0x50 + 0x24, 2), self.mem.load(H + 0xE0 + 0x24, 2)), (0x18, 0x18))
        self.assertEqual(self.model.draws, 2)

    def test_slot_16_hands(self):
        self.mem.poke(H + 0xE0 + 0x24, 2, 0x16)
        self.mem.poke(H + 0x50 + 0x24, 2, 0x17)
        self.assertEqual([self.model.entry(HS.W2_GET_ELEMENT, H, hand) for hand in (0, 1, 2, 3)], [0, 3, 2, 0])


class Tables(unittest.TestCase):
    def test_executed_covers_every_slot_body(self):
        bodies = {fn for table in HS.TABLE_SLOTS.values() for fn in table.values()}
        self.assertTrue(bodies <= set(HS.EXECUTED.values()))
        self.assertEqual(set(HS.BODY_END), set(HS.EXECUTED.values()))


if __name__ == '__main__':
    unittest.main()
