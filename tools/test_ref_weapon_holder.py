#!/usr/bin/env python3
"""test_ref_weapon_holder.py - unit tests of tools/ref_weapon_holder.py that need no game files.

Made-up memory only: the element setters (the four slots freed, one shared draw, slot 0
taken, the kind-to-id table, kind 6 sharing kind 1's Skill), damageDesc_getElement's last
match and its 0x1f/0x18 pair, the hand tests of both classes (WeaponShield's slot 13 sets
bit 0), slot 11's two drops, and the part-drop gates and flags.  Whether the model matches
the game is tools/difftest_weapon_holder.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_weapon_holder as WH                  # noqa: E402

f32 = C.f32
H, CRE, DEF, SKILL, TABLE = 0x100000, 0x110000, 0x120000, 0x130000, 0x140000


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.answers = {'Skill.v11': 100, 'Creature.v16': 0xC00080, 'model_getAttachPoint': 0,
                        'pool_new': 0x150000, 'PhProp_ctor': 0}
        self.model = WH.Model(self.mem, self)
        self.mem.poke(SKILL + 0x60, 4, TABLE)
        for index in (12, 13, 14, 25, 26):
            self.mem.poke(WH.G_SKILL_TABLE + 4 * index, 4, SKILL)
        self.mem.poke(RC.G_LEVEL_MONSTER_LEVEL, 4, f32(10.0))
        self.mem.poke(RC.G_RAND_SEED, 4, 0)
        for k in range(4):
            self.mem.poke(H + 0x50 + 0x24 + 8 * k, 2, 0xFFFF)

    def get(self, name):
        value = self.answers[name]
        return value if callable(value) else (lambda *args: value)

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]

    def slot(self, k):
        return self.mem.load(H + 0x50 + 0x24 + 8 * k, 2), self.mem.load(H + 0x50 + 0x26 + 8 * k, 2), \
            self.mem.load(H + 0x50 + 0x28 + 8 * k, 2), self.mem.load(H + 0x50 + 0x2A + 8 * k, 2)


class Elements(Fixture):
    def test_slot_0_gets_the_id_and_the_rolled_value(self):
        self.mem.poke(H + 0x50 + 0x24 + 8, 2, 0x26)             # an old entry elsewhere is freed
        self.model.set_kind_2(H, 1)
        ident, a, b, zero = self.slot(0)
        self.assertEqual((ident, a, zero), (0x16, 100, 0))
        d = (0x3C6EF35F >> 16)                                  # the draw from seed 0
        v = C.to_int(C.mul(C.mul(C.from_int(100), WH.F_0_2), C.mul(C.from_int(d), WH.F_2M16)))
        self.assertEqual(b, 100 + v)
        self.assertEqual(self.slot(1)[0], 0xFFFF)
        self.assertEqual(self.model.draws, 1)
        self.assertEqual(self.named('Skill.v11'), [(SKILL, 0, 10, 0)])

    def test_kind_table(self):
        for method, ident in (('set_kind_1', 0x15), ('set_kind_6', 0x1F), ('set_kind_2', 0x16),
                              ('set_kind_3', 0x17), ('set_kind_4', 0x18), ('set_kind_5', 0x26)):
            getattr(self.model, method)(H, 0)
            self.assertEqual(self.slot(0)[0], ident, method)

    def test_hand_2_and_negative_hands_set_nothing(self):
        for hand in (2, 3, 0xFFFFFFFF):
            self.model.set_kind_1(H, hand)
        self.assertEqual(self.model.writes, [])

    def test_kind_0_and_7_only_free(self):
        self.mem.poke(H + 0x50 + 0x24, 2, 0x15)
        self.model.set_element(H, 1, 0)
        self.model.set_element(H, 1, 7)
        self.assertEqual(self.slot(0)[0], 0xFFFF)
        self.assertEqual(self.model.draws, 0)
        self.model.set_element(H, 1, 0x103)                    # kind & 0xff = 3
        self.assertEqual(self.slot(0)[0], 0x17)

    def test_get_element_last_match_and_the_pair(self):
        for ids, want in (((0x15, 0x26, 0xFFFF, 0xFFFF), 1), ((0x15, 0x16, 0xFFFF, 0x26), 2),
                          ((0x1F, 0xFFFF, 0xFFFF, 0xFFFF), 6), ((0x18, 0x15, 0x26, 0x1F), 6),
                          ((0x26, 0x23, 0, 0xFFFF), 0)):
            for k, ident in enumerate(ids):
                self.mem.poke(H + 0x50 + 0x24 + 8 * k, 2, ident)
            self.assertEqual(self.model.get_element(H + 0x50), want, ids)
            self.assertEqual(self.model.ws_element(H, 1), want)
            self.assertEqual(self.model.ws_element(H, 2), 0)

    def test_skeleton_element_round_trip(self):
        for element, (slot, kind, ident, reported) in WH.SKELETON_ELEMENTS.items():
            method = {2: 'set_kind_1', 3: 'set_kind_6', 4: 'set_kind_2'}[slot]
            getattr(self.model, method)(H, 1)
            self.assertEqual(self.slot(0)[0], ident)
            self.assertEqual(self.model.ws_element(H, 1), reported)


class Hands(Fixture):
    def test_set_part(self):
        self.model.ws_set_part(H, 2, 0x162)
        self.assertEqual((self.mem.load(H + 0x98, 1), self.mem.load(H + 4, 1)), (0x62, 2))
        self.model.ws_set_part(H, 1, 0x52)
        self.assertEqual(self.mem.load(H + 4, 1), 3)
        self.model.ws_set_part(H, 2, 0)
        self.assertEqual(self.mem.load(H + 4, 1), 1)
        self.model.w1_set_part(H, 2, 0x60)                      # Weapon1: hand 1 only
        self.assertEqual(self.mem.load(H + 4, 1), 1)

    def test_shield_hide_sets_bit_0(self):
        self.mem.poke(H + 4, 1, 2)
        self.model.ws_hide(H, 0)
        self.assertEqual(self.mem.load(H + 4, 1), 1)
        self.mem.poke(H + 4, 1, 3)
        self.model.w1_hide(H, 1)
        self.assertEqual(self.mem.load(H + 4, 1), 2)

    def test_queries(self):
        self.mem.poke(H + 4, 1, 2)
        self.mem.poke(H + 8, 1, 0x52)
        self.mem.poke(H + 0x98, 1, 0x60)
        self.assertEqual([self.model.ws_carried(H, k) for k in (0, 1, 2)], [0, 0, 1])
        self.assertEqual([self.model.ws_part(H, k) for k in (0, 1, 2)], [0, 0x52, 0x60])
        self.assertEqual([self.model.w1_part(H, k) for k in (0, 1, 2)], [0, 0x52, 0])
        self.assertEqual([self.model.ws_descriptor(H, k) for k in (0, 1, 2)], [0, H + 0x50, 0])
        self.assertEqual([self.model.w1_descriptor(H, k) for k in (0, 1, 2)], [0, H + 0x50, 0])

    def test_colours(self):
        self.model.set_colour_b(H, 0, 0x1FF, 2, 3, 0x104)
        self.assertEqual([self.mem.load(H + 0x68 + 2 * k, 2) for k in range(4)], [0xFF, 2, 3, 4])


class Drop(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        rec = 0x160000
        self.mem.poke(DEF, 4, 0xAAAA)
        self.mem.poke(DEF + 8 * 0x52, 4, 0xBBBB)
        self.mem.poke(DEF + 8 * 0x52 + 4, 4, rec)
        self.mem.poke(DEF + 8 * 0x53, 4, 0xCCCC)
        self.mem.poke(rec + 0x13, 1, 0xFE)
        self.mem.poke(CRE + 0xC, 4, 0x20)
        self.mem.poke(CRE + 0x24, 4, DEF)
        self.mem.poke(CRE + 0x48, 4, 0x170000)
        self.mem.poke(CRE + 0x38, 2, 0x1000)
        self.mem.poke(CRE + 0xDC, 4, f32(1.25))
        self.mem.poke(H + 4, 1, 3)
        self.mem.poke(H + 8, 1, 0x52)
        self.mem.poke(H + 0x98, 1, 0x52)

    def test_both_hands_dropped_with_the_creature_definition(self):
        self.model.ws_drop(H, 0, CRE, 0, 0)
        props = self.named('PhProp_ctor')
        self.assertEqual(len(props), 2)
        self.assertEqual(props[0][3:], (0xAAAA, 0xBBBB, 0xCCCC, 1, 0x4001, 0))
        self.assertEqual(self.mem.load(H + 4, 1), 0)
        point = self.named('model_getAttachPoint')[0]
        self.assertEqual(point[3], (0x1000 - 0x4000) & 0xFFFFFFFF)
        self.assertEqual(point[5], 0xFFFFFFFE)                  # the bone byte is signed

    def test_gates_and_flags(self):
        self.mem.poke(CRE + 0xA8, 8, 0x1000000)
        self.model.ws_drop(H, 1, CRE, DEF, 3)
        self.assertEqual(self.named('PhProp_ctor')[0][7], 0x103)
        self.assertEqual(self.mem.load(H + 4, 1), 2)
        self.mem.poke(CRE + 0xC, 4, 0x22)                       # flag 2: nothing
        self.model.ws_drop(H, 2, CRE, DEF, 0)
        self.assertEqual(len(self.named('PhProp_ctor')), 1)
        self.assertEqual(self.mem.load(H + 4, 1), 0)            # the bit is cleared anyway

    def test_no_block_no_prop(self):
        self.answers['pool_new'] = 0
        self.model.w1_drop(H, 1, CRE, DEF, 0)
        self.assertEqual(self.named('PhProp_ctor'), [])
        self.assertEqual(len(self.named('pool_new')), 1)


if __name__ == '__main__':
    unittest.main()
