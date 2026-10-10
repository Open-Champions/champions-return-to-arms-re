#!/usr/bin/env python3
"""Unit tests for tools/ref_arena_monsters.py that need no game files (they build the few
tables the model reads in a blank memory image).  The comparison with the game's own code
is tools/difftest_arena_monsters.py.

    python3 -m unittest discover -s tools -p 'test_ref_arena_monsters.py'
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402

C, PET, PLAYER, DEF, TABLES, SPELL, BLOCK, SKILL = 0x10000, 0x11000, 0x12000, 0x20000, 0x30000, 0x40000, 0x41000, 0x50000


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw))[0]


class Rig:
    """A blank memory with one creature of the wanted class, a skeleton, a player object
    and the class tables the model dispatches on."""

    def __init__(self, table=AM.VT_HORSEMEN, answers=None):
        self.mem = RC.Memory()
        poke = self.mem.poke
        bodies = {AM.VT_HORSEMEN: {4: 0x27236C, 27: 0x272F4C}, AM.VT_SKELIGHT: {4: 0x2A8B84, 27: 0x2A91B8},
                  AM.VT_ZEK: {4: 0x2C2440, 27: 0x2C382C, 2: 0x2C34E4, 35: 0x2C3C54}}
        for vt, own in bodies.items():
            for slot in range(1, 40):
                fn = own.get(slot)
                if fn is None and slot in RC.BASE_BODIES:
                    fn = RC.BASE_BODIES[slot][0]
                if fn is None:
                    fn = {16: 0x3C2738, 25: 0x10E658, 28: 0x10BEB8, 34: 0x3C2708}.get(slot, 0x00F00000 + slot)
                poke(vt + 8 * slot + 4, 4, fn)
        for k in range(1, 0x1C):                 # class definition: entry k -> a distinct pointer
            poke(DEF + 8 * k + 4, 4, 0x60000 + 0x40 * k)
        for obj, vt in ((C, table), (PET, AM.VT_SKELIGHT)):
            poke(obj + 0xC, 4, 0x20)
            poke(obj + 0x24, 4, DEF)
            poke(obj + 0x48, 4, vt)
            poke(obj + 0x44, 4, 12345)
        poke(PLAYER + 0xC, 4, 0x40)
        poke(PLAYER + 0x48, 4, AM.VT_HORSEMEN)
        self.answers = dict(answers or {})
        self.model = AM.Model(self.mem, self)

    def get(self, name):
        value = self.answers.get(name)
        if value is None:
            return None
        if callable(value):
            return value
        return lambda *args: value

    def names(self):
        return [name for name, _args in self.model.calls]

    def args_of(self, name):
        return [args for n, args in self.model.calls if n == name]


class Arithmetic(unittest.TestCase):
    def test_divisions_round_toward_zero(self):
        self.assertEqual([AM.third_toward_zero(v) for v in (30, 31, 2, -1, -5, -6)], [10, 10, 0, 0, -1, -2])
        self.assertEqual([AM.half_toward_zero(v) for v in (30, 31, 1, -1, -5, 0xFFFB)], [15, 15, 0, 0, -2, -2])

    def test_scaled_time_is_one_short(self):
        self.assertEqual([AM.scaled_time(n) for n in (1, 2, 61, 301, 302, 1502)], [0, 1, 60, 300, 301, 1501])


class Script(unittest.TestCase):
    @staticmethod
    def frames_until(script, event, paused=()):
        count = 0
        while event not in script.log:
            script.frame(1 if count in paused else 0)
            count += 1
            if count > 5000:
                raise AssertionError('never happened')
        return count - 1                         # the first frame() is the Script task of the death's own frame

    def test_fourth_knight_starts_the_second_cutscene_302_frames_later(self):
        script = AM.ArenaScript()
        for index in (3, 1, 4):
            script.knight_death(index)
            script.frame()
        self.assertEqual(script.front, [])       # three dead: nothing is counting
        script.knight_death(2)
        self.assertEqual(self.frames_until(script, ('cutScene', 'cazic')), 302)
        self.assertEqual(script.q['sawcaz'], 1)

    def test_a_pause_stops_the_count(self):
        script = AM.ArenaScript()
        for index in (1, 2, 3, 4):
            script.knight_death(index)
        self.assertEqual(self.frames_until(script, ('cutScene', 'cazic'), paused=range(10, 60)), 352)

    def test_avatar_counter_runs_at_double_rate_after_the_sound(self):
        script = AM.ArenaScript()
        script.avatar_death()
        self.assertEqual(self.frames_until(script, ('soundSequence',)), 252)
        self.assertEqual(script.front, ['bossDefeatedDelay', 'bossDefeatedDelay'])     # two copies from now on
        before = script.g[0]
        script.frame()
        self.assertEqual(script.g[0], before + 2)
        script2 = AM.ArenaScript()
        script2.avatar_death()
        self.assertEqual(self.frames_until(script2, ('cutScene', 'bossdefeated')), 877)
        self.assertEqual(script2.q['killedAv'], 1)
        script2.frame(1)                          # the other copy: paused by the cutscene, does nothing more
        self.assertEqual(script2.front, [])
        self.assertEqual(script2.log.count(('cutScene', 'bossdefeated')), 1)

    def test_trigger_plays_the_opening_once(self):
        script = AM.ArenaScript()
        script.incoming()
        script.incoming()
        self.assertEqual(script.log, [('cutScene', 'knights'), ('postAction', 'nosave'), ('setCFlag', 'avatar', 0, 1)])


class Horsemen(unittest.TestCase):
    def test_an_unknown_state_number_is_stored_after_a_nested_chase(self):
        rig = Rig()
        rig.model.horsemen_set_state(C, 9)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 9)
        self.assertEqual(rig.args_of('anim_start'), [(C + 0x114, 0x60000 + 0x40 * 0xD, 0x803, AM.F_0_1)])
        self.assertIn('anim_syncToSimFrame', rig.names())

    def test_a_mounted_knight_cannot_enter_the_death_state(self):
        rig = Rig()
        rig.mem.poke(C + 0x3C8, 4, 0x70000)
        rig.mem.poke(C + 0xA8, 8, 0x200)
        rig.model.horsemen_set_state(C, 0x14)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0)
        self.assertEqual(rig.mem.load(C + 0xA8, 8), 0)          # but creature flag 0x200 is gone
        self.assertNotIn('Creature_dropLoot', rig.names())

    def test_the_summoner_takes_its_skeleton_with_it(self):
        rig = Rig(answers={'world_findObjectByName': PET})
        rig.mem.poke(C + 0x470, 1, 3)
        rig.mem.poke(C + 0x50, 4, C + 0x3D0)
        rig.mem.poke(C + 0x3D0, 4, TABLES)
        rig.model.horsemen_set_state(C, 0x14)
        self.assertEqual(rig.mem.load(PET + 0x232, 2), 0x14)
        self.assertEqual(rig.mem.load(PET + 0xC, 4), 0x22)      # hidden; nothing sets the dead bit here
        self.assertIn(('obj_delete', (PET,)), rig.model.calls)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0x14)
        self.assertEqual([args[1] for args in rig.args_of('Holder.v11')], [1, 2])     # both hands dropped
        order = rig.names()
        self.assertLess(order.index('obj_delete'), order.index('Creature_dropLoot'))
        self.assertIn('creature_stopBossMusic', order)          # slot 28 ran

    def test_the_other_variants_do_not_look_for_a_skeleton(self):
        rig = Rig(answers={'world_findObjectByName': PET})
        rig.mem.poke(C + 0x470, 1, 2)
        rig.model.horsemen_set_state(C, 0x14)
        self.assertNotIn('world_findObjectByName', rig.names())

    def test_hit_reaction_is_ignored_during_a_state_6_swing(self):
        rig = Rig()
        rig.mem.poke(C + 0x232, 2, 6)
        rig.mem.poke(C + 0x11A, 2, 8)
        rig.model.horsemen_set_state(C, 0x12)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 6)
        rig.mem.poke(C + 0x232, 2, 7)
        rig.model.horsemen_set_state(C, 0x12)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0x12)

    def test_charging_needs_a_facing_target_faster_than_100(self):
        rig = Rig()
        node = 0x70000
        rig.mem.poke(node + 0xC, 4, PLAYER)
        rig.mem.poke(C + 0x234, 4, node)
        rig.mem.poke(PLAYER + 0x10, 4, f32(100.0))               # the target stands east of the knight
        rig.mem.poke(PLAYER + 0x308, 4, f32(150.0))
        for facing, expected in ((0, 1), (0x3FFE, 1), (0x4000, 0), (0x8000, 0), (0xC002, 1)):
            rig.mem.poke(PLAYER + 0x38, 2, facing)
            self.assertEqual(rig.model.is_target_charging(C), expected, hex(facing))
        rig.mem.poke(PLAYER + 0x38, 2, 0)
        rig.mem.poke(PLAYER + 0x308, 4, f32(100.0))
        self.assertEqual(rig.model.is_target_charging(C), 0)     # exactly 100 is not "faster"


class Skelight(unittest.TestCase):
    def test_set_state(self):
        rig = Rig(AM.VT_SKELIGHT)
        rig.mem.poke(C + 0x232, 2, 6)
        rig.model.skelight_set_state(C, 0x12)                     # no hit reaction: the state stays
        self.assertEqual(rig.mem.load(C + 0x232, 2), 6)
        self.assertEqual(rig.model.calls, [])
        rig.model.skelight_set_state(C, 9)                        # an unknown number is idle
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0)

    def test_death_has_no_loot_and_no_death_script(self):
        rig = Rig(AM.VT_SKELIGHT, answers={'model_getSamplePointCount': 7})
        rig.model.skelight_set_state(C, 0x14)
        names = rig.names()
        self.assertEqual(names.count('fx_spawn'), 3)             # sample points 0, 3 and 6
        self.assertEqual([a[4] for a in rig.args_of('model_getSamplePoint')], [0, 3, 6])
        self.assertEqual(names[-1], 'obj_delete')
        self.assertNotIn('Creature_dropLoot', names)
        self.assertNotIn('obj_getPropStr', names)
        self.assertEqual(rig.mem.load(C + 0xC, 4), 0x22)

    def test_damage_waits_while_rising(self):
        rig = Rig(AM.VT_SKELIGHT)
        rig.mem.poke(C + 0x232, 2, 0x17)
        rig.mem.poke(C + 0xC8, 4, f32(50.0))                      # pending damage
        rig.mem.poke(C + 0x228, 4, f32(-10.0))                    # and no hit points left
        rig.model.skelight_run(C)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0x17)
        self.assertEqual(rig.mem.load(C + 0xC8, 4), f32(50.0))
        self.assertEqual(rig.names()[-1], 'fx_spawn')


class Zek(unittest.TestCase):
    def test_unknown_state_is_idle_without_a_clip(self):
        rig = Rig(AM.VT_ZEK)
        rig.mem.poke(C + 0x232, 2, 5)
        rig.model.zek_set_state(C, 0xF)
        self.assertEqual(rig.mem.load(C + 0x232, 2), 0)
        self.assertEqual(rig.names(), ['handle_clear'] if rig.names() else [])

    def test_nothing_runs_while_not_active(self):
        rig = Rig(AM.VT_ZEK)
        rig.mem.poke(C + 0x464, 4, 1)                              # a wave is out
        rig.mem.poke(C + 0x232, 2, 5)
        rig.model.zek_run(C)                                       # no activity centre: not active
        self.assertNotIn('anim_advance', rig.names())
        self.assertNotIn('fx_spawn', rig.names())
        self.assertEqual(rig.mem.load(C + 0x232, 2), 5)

    def test_wave_steers_toward_its_enemy_by_140_a_tick(self):
        rig = Rig(AM.VT_ZEK)
        node = 0x70000
        rig.mem.poke(node + 0xC, 4, PLAYER)
        rig.mem.poke(PLAYER + 0x10, 4, f32(400.0))                # the enemy is due east of the wave
        rig.mem.poke(C + 0x460, 4, node)
        rig.mem.poke(C + 0x464, 4, 1)
        rig.mem.poke(C + 0x468, 2, 0)                              # and the wave heads east
        rig.mem.poke(C + 0x46C, 4, f32(100.0))
        rig.model._zek_wave(C)
        self.assertEqual(fl(rig.mem.load(C + 0x46C, 4)), 105.0)
        self.assertEqual(abs(RC.s16(rig.mem.load(C + 0x468, 2))), 140)     # it dithers around the bearing
        self.assertEqual(rig.mem.load(C + 0x464, 4), 1)
        self.assertEqual(rig.names(), ['terrain_height', 'fx_spawn'])

    def test_wave_ends_on_a_step_and_draws_once(self):
        rig = Rig(AM.VT_ZEK, answers={'terrain_height': f32(13.5)})
        rig.mem.poke(C + 0x464, 4, 1)
        rig.mem.poke(C + 0x46C, 4, f32(100.0))
        seed = rig.mem.load(C + 0x44, 4)
        rig.model._zek_wave(C)
        self.assertEqual(rig.mem.load(C + 0x464, 4), 0)
        self.assertEqual(fl(rig.mem.load(C + 0x46C, 4)), 100.0)    # the step was undone
        self.assertEqual(rig.mem.load(C + 0x44, 4), (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)
        self.assertEqual(rig.model.draws, 0)                       # nothing from the shared seed
        self.assertEqual(rig.args_of('combat_applyAreaDamage')[0][4:], (0x80840, 0, f32(40.0), f32(180.0)))


class Skills(unittest.TestCase):
    def test_can_use_asks_for_the_shared_monster_name(self):
        rig = Rig(answers={'world_findObjectByName': 0})
        rig.mem.poke(AM.G_SUMMON_MONSTER_NAME, 4, 0x54FDB0)
        self.assertEqual(rig.model.summon_can_use(SKILL, C), 1)
        self.assertEqual(rig.model.calls, [('world_findObjectByName', (0x54FDB0,))])
        rig.answers['world_findObjectByName'] = PET
        self.assertEqual(rig.model.summon_can_use(SKILL, C), 0)
        rig.mem.poke(PLAYER + 0x3C8, 4, 4)                         # a fifth player slot is refused unasked
        rig.model.calls.clear()
        self.assertEqual(rig.model.summon_can_use(SKILL, PLAYER), 0)
        self.assertEqual(rig.model.calls, [])

    def cast(self, chance, blocks):
        pool = list(blocks)
        rig = Rig(answers={'pool_new': lambda size: pool.pop(0), 'Skill.v12': lambda *a: (10, chance)[a[1]]})
        rig.mem.poke(SKILL + 0x60, 4, TABLES)                      # a skill table of unknown functions
        rig.mem.poke(AM.G_RAND_SEED, 4, 1)
        spell = rig.model.summon_cast(SKILL, 3, C, (f32(10.0), f32(20.0), 0), 0)
        return rig, spell

    def test_summon_draws_two_or_three_times(self):
        rig, spell = self.cast(0, (BLOCK, SPELL))
        self.assertEqual((spell, rig.model.draws), (SPELL, 2))    # the roll, the spell's own seed
        self.assertEqual(rig.mem.load(BLOCK + 0x48, 4), AM.VT_SKELIGHT)
        self.assertEqual(rig.mem.load(BLOCK + 0x232, 2), 0x17)     # rising
        self.assertEqual(rig.mem.load(BLOCK + 0x460, 4), 10)       # its level is the skill's statistic 0
        self.assertEqual(rig.mem.load(BLOCK + 0xC, 4) & 0x4020, 0x4020)
        self.assertEqual(rig.mem.load(SPELL + 0xC, 4), C)
        rig, spell = self.cast(100, (BLOCK, SPELL))
        self.assertEqual((spell, rig.model.draws), (SPELL, 3))    # ... and which element
        self.assertEqual(sum(name in ('Holder.v2', 'Holder.v4', 'Holder.v6') for name in rig.names()), 1)

    def test_summon_without_a_block_still_draws_once(self):
        rig, spell = self.cast(100, (0,))
        self.assertEqual((spell, rig.model.draws), (0, 1))
        self.assertIn('sound_playAtPos', rig.names())

    def test_tagar_spell_starts_ahead_of_its_caster(self):
        rig = Rig(answers={'pool_new': SPELL, 'Skill.v14': 4})
        rig.mem.poke(SKILL + 0x60, 4, TABLES)
        rig.mem.poke(C + 0x10, 4, f32(100.0))
        rig.mem.poke(C + 0x18, 4, f32(5.0))
        spell = rig.model.tagar_cast(SKILL, 9, C, (0, 0, 0), 0x1234)
        self.assertEqual((spell, rig.model.draws), (SPELL, 1))
        self.assertEqual(rig.mem.load(SPELL, 1), 4)                # the level is slot 14's answer
        x, y, z = [fl(rig.mem.load(SPELL + 0x88 + 4 * i, 4)) for i in range(3)]
        self.assertEqual((x, z), (124.0, 53.0))                    # 24 ahead (the caster faces east), 48 up
        self.assertAlmostEqual(y, 0.0, places=4)                   # the game's sine of 0 is not exactly 0
        self.assertEqual(rig.mem.load(SPELL + 0x80, 2), 0xFFFF)
        self.assertEqual(rig.mem.load(SPELL + 0x7C, 4), 0x4000101F)


if __name__ == '__main__':
    unittest.main()
