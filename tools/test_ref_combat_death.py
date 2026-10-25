#!/usr/bin/env python3
"""test_ref_combat_death.py - unit tests of tools/ref_combat_death.py that need no game files.

Made-up memory only: Skeleton_shatter's mask list per group and its one prop per mask with
the part bits passed on, creature_bossRank's gates and its property pairs, the skill-rank
list walk, player_giveExp's cap, points per level band and refill, and anim_findTrack.
Whether the model matches the game is tools/difftest_combat_death.py's business (it needs
the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_death as D                    # noqa: E402

f32 = C.f32
CRE, DEF, STATE, TEXT = 0x100000, 0x110000, 0x120000, 0x130000


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.answers = {'pool_new': 0x150000, 'PhProp_ctor2': 0, 'obj_getPropStr': 0, 'player_recalcStats': 0,
                        'net_isLocalSlot': 1, 'res_find': 0x777, 'sound_playOnObject': 0, 'text_lookup': 0x888,
                        'hud_showMessage': 0}
        self.model = D.Model(self.mem, self)
        self.texts = TEXT

    def get(self, name):
        value = self.answers[name]
        return value if callable(value) else (lambda *args: value)

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]

    def text(self, value, addr=None):
        if addr is None:
            addr, self.texts = self.texts, self.texts + 0x40
        self.mem.poke(addr, len(value) + 1, int.from_bytes(value + b'\0', 'little'))
        return addr


class Shatter(Fixture):
    def test_group_8_one_prop_per_mask_present(self):
        self.mem.poke(CRE + 0x24, 4, DEF)
        self.mem.poke(DEF + 0xC, 4, 0xC00080)
        self.mem.poke(CRE + 0x38, 2, 0x8000)
        self.mem.poke(CRE + 0x220, 8, 0x80 | 0x4 | 0x2 | 0x10000000000000 | 0x100000000)
        self.model.skeleton_shatter(CRE, 8)
        props = self.named('PhProp_ctor2')
        self.assertEqual([p[9][1] for p in props], [0x80, 0x4, 0x2, 0x10000000000000])
        self.assertEqual(props[0][3], 0xFFFF8000)               # the facing, signed
        self.assertEqual(props[0][10:], (0x107, 0))
        self.assertEqual(self.mem.load(CRE + 0x220, 8), 0x100000000)
        self.assertEqual(self.mem.load(D.G_SHATTER_MASKS + 8 * 16, 8), 0)

    def test_bits_go_without_a_block(self):
        self.answers['pool_new'] = 0
        self.mem.poke(CRE + 0x220, 8, 0x3)
        self.model.skeleton_shatter(CRE, 5)
        self.assertEqual(self.named('PhProp_ctor2'), [])
        self.assertEqual(len(self.named('pool_new')), 1)        # only the 0x1 mask: bit 1 is no group-5 mask
        self.assertEqual(self.mem.load(CRE + 0x220, 8), 0x2)

    def test_groups_without_masks(self):
        self.mem.poke(D.G_SHATTER_MASKS, 8, 0x1234)
        self.mem.poke(CRE + 0x220, 8, 0xFFFF)
        for group in (0, 6, 7, 9):
            self.model.skeleton_shatter(CRE, group)
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.mem.load(D.G_SHATTER_MASKS, 8), 0)


class Boss(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        for k, a in enumerate(D.BOSS_NAMES + D.BOSS_LAST):
            self.text(b'Boss%d' % k, a)
        for k, (name, value) in enumerate(D.BOSS_PAIRS):
            self.text(b'Pair%d' % (k // 2), name)
            self.text(b'value%d' % k, value)
        self.mem.poke(CRE + 0xC, 4, 0x20)

    def test_gates(self):
        self.mem.poke(CRE + 0xA8, 8, 1)
        self.assertEqual(self.model.boss_rank(CRE), 1)          # no name: MiniBoss bit
        self.mem.poke(CRE + 0x34, 4, self.text(b'BOSS3'))
        self.assertEqual(self.model.boss_rank(CRE), 2)
        self.mem.poke(CRE + 0xC, 4, 0x40)
        self.assertEqual(self.model.boss_rank(CRE), 0)

    def test_pairs_ask_the_name_property(self):
        self.mem.poke(CRE + 0x34, 4, self.text(b'pair0'))
        self.answers['obj_getPropStr'] = self.text(b'VALUE1')
        self.assertEqual(self.model.boss_rank(CRE), 2)
        self.assertEqual(len(self.named('obj_getPropStr')), 2)  # the first value missed, the second asked again
        self.answers['obj_getPropStr'] = self.text(b'other')
        self.model.calls = []
        self.assertEqual(self.model.boss_rank(CRE), 0)
        self.assertEqual(self.named('obj_getPropStr'), [(CRE, D.S_NAME_PROPERTY, 0)] * 2)


class Ranks(Fixture):
    def test_walk(self):
        rec = D.record(2)
        for k, (ident, rank) in enumerate(((0x3B, 4), (0x53, 0xFFFF), (0x3B, 9))):
            self.mem.poke(rec + D.REC_SKILLS + 4 * k, 2, ident)
            self.mem.poke(rec + D.REC_SKILLS + 4 * k + 2, 2, rank)
        self.mem.poke(rec + D.REC_SKILLS + 12, 2, 0xFFFF)
        self.assertEqual(self.model.get_skill_rank(2, 0x3B), 4)
        self.assertEqual(self.model.get_skill_rank(2, 0x53), 0xFFFFFFFF)
        self.assertEqual(self.model.get_skill_rank(2, 0x40), 0)
        self.mem.poke(CRE + 0x3C8, 4, 2)
        self.assertEqual(self.model.player_slot39(CRE, 0x53), 0xFFFFFFFF)
        self.mem.poke(rec + D.REC_SKILLS, 2, 0xFFFF)
        self.assertEqual(self.model.get_skill_rank(2, 0x53), 0)


class Experience(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        for k in range(81):
            self.mem.poke(D.G_EXP_TABLE + 4 * k, 4, 100 * k * k)
        self.rec = D.record(1)
        self.mem.poke(self.rec + D.REC_LEVEL, 1, 5)
        self.mem.poke(self.rec + D.REC_HP, 4, f32(3.0))
        self.mem.poke(self.rec + D.REC_MAX_HP, 4, f32(80.0))

    def test_two_levels_across_a_band(self):
        self.model.give_exp(1, 3600)
        self.assertEqual(self.mem.load(self.rec + D.REC_LEVEL, 1), 7)
        self.assertEqual(self.mem.load(self.rec + D.REC_SKILL_POINTS, 4), 1 + 2)
        self.assertEqual(self.mem.load(self.rec + D.REC_STAT_POINTS, 1), 6)
        self.assertEqual(self.mem.load(self.rec + D.REC_HP, 4), f32(80.0))
        self.assertEqual(len(self.named('hud_showMessage')), 2)
        self.assertEqual(self.named('sound_playOnObject')[0], (RC.ONE, 0x777, 0))

    def test_cap_and_no_refill_when_dead(self):
        self.mem.poke(self.rec + D.REC_HP, 4, 0x80000000)
        self.answers['net_isLocalSlot'] = 0
        self.model.give_exp(1, 10 ** 9)
        self.assertEqual(self.mem.load(self.rec + D.REC_EXP, 4), 100 * 80 * 80 - 1)
        self.assertEqual(self.mem.load(self.rec + D.REC_LEVEL, 1), 80)
        self.assertEqual(self.mem.load(self.rec + D.REC_HP, 4), 0x80000000)
        self.assertEqual(self.named('res_find'), [])


class Tracks(Fixture):
    def test_find(self):
        self.mem.poke(STATE + 4, 1, 3)
        for k, clip in enumerate((0xA, 0xB, 0xC, 0xD)):
            self.mem.poke(STATE + 8 + 32 * k, 4, clip)
        self.assertEqual(self.model.find_track(STATE, 0xC), STATE + 8 + 64)
        self.assertEqual(self.model.find_track(STATE, 0xD), 0)  # past the count
        self.assertEqual(self.model.find_track(0, 0xA), 0)
        self.mem.poke(STATE + 4, 1, 0x80)                       # a negative count
        self.assertEqual(self.model.find_track(STATE, 0xA), 0)


if __name__ == '__main__':
    unittest.main()
