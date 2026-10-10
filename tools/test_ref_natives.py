#!/usr/bin/env python3
"""test_ref_natives.py - checks of tools/ref_natives.py that need no game files.

These pin the model's own logic (the rules of docs/spec/script-builtins.md).  That the
model matches the game is the job of tools/difftest_natives.py, which needs the executable.

    python3 -m unittest discover -s tools -p 'test_ref_natives.py'
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_amx                                  # noqa: E402
import ref_core as C                            # noqa: E402
import ref_natives as N                         # noqa: E402

INDEX = {name: index for index, name in enumerate(N.NATIVE_NAMES)}
BAD = 0x7FFF0000                                # an address scr_getAddr refuses


class Script:
    """A small script image: named entry points made of built-in calls."""

    def __init__(self):
        self.data, self.literals, self.program, self.names = [], {}, [], []

    def lit(self, text):
        if text not in self.literals:
            self.literals[text] = 4 * len(self.data)
            padded = text + b'\0' * (4 - len(text) % 4)
            self.data += [int.from_bytes(padded[i:i + 4], 'big') for i in range(0, len(padded), 4)]
        return self.literals[text]

    def call(self, name, *args):
        code = [('PUSH.C', self.lit(a) if isinstance(a, bytes) else a) for a in reversed(args)]
        return code + [('PUSH.C', 4 * len(args)), ('SYSREQ.C', INDEX[name]), ('STACK', 4 * len(args) + 4)]

    def entry(self, name, body, result=None):
        self.names.append(name)
        self.program += [name + ':', ('PROC',)] + body + ([] if result is None else [('CONST.pri', result)]) \
            + [('RETN',)]

    def build(self, game):
        cells, labels = ref_amx.assemble(self.program)
        image = ref_amx.build_image(cells, self.data or [0], [(n, labels[n]) for n in self.names], N.NATIVE_NAMES,
                                    stack_cells=512)
        machine = ref_amx.Machine(image)
        assert machine.load() == 0
        game.set_script(machine)
        return machine


def new_game(players=2):
    game = N.Game()
    game.num_players = players
    return game


class Table(unittest.TestCase):
    def test_every_built_in_is_modelled(self):
        self.assertEqual(len(N.NATIVE_NAMES), 191)
        self.assertEqual(len(set(N.NATIVE_NAMES)), 191)
        self.assertEqual(N.NOT_MODELLED, ())
        self.assertEqual(set(new_game().natives()), set(N.NATIVE_NAMES))

    def test_string_slots_name_built_ins(self):
        self.assertTrue(set(N.STRING_SLOT) <= set(N.NATIVE_NAMES))
        self.assertEqual(N.STRING_SLOT['rootMonster'], N.STRING_SLOT['setCFlag'])


class QuestVariables(unittest.TestCase):
    def test_get_appends_and_names_are_lower_cased(self):
        game = new_game()
        self.assertEqual(game.var_get(b'Door'), 0)
        self.assertEqual(game.quest_vars(), [(b'door', 0)])
        game.var_set(b'DOOR', 5)
        self.assertEqual(game.var_get(b'door'), 5)
        self.assertEqual(len(game.quest_vars()), 1)

    def test_set_clamps_to_a_signed_byte(self):
        game = new_game()
        game.var_set(b'a', 300)
        game.var_set(b'b', -300)
        self.assertEqual(game.quest_vars(), [(b'a', 127), (b'b', -128)])

    def test_clear_keeps_names_and_order(self):
        game = new_game()
        for value, name in enumerate((b'one', b'two', b'three'), 1):
            game.var_set(name, value)
        game.vars_clear_all()
        self.assertEqual(game.quest_vars(), [(b'one', 0), (b'two', 0), (b'three', 0)])
        self.assertEqual(game.var_by_index(1), (b'two', 0))
        self.assertIsNone(game.var_by_index(3))

    def test_addv_returns_the_unclamped_sum(self):
        game = new_game()
        script = Script()
        script.entry('go', script.call('setv', b'q', 100) + script.call('addv', b'q', 100))
        script.build(game)
        self.assertEqual(game.run_script(b'go'), 200)
        self.assertEqual(game.var_get(b'q'), 127)

    def test_profile_set_asks_for_a_save_only_on_change(self):
        game = new_game()
        game.profile_set(b'seen', 1, 1)
        game.profile_set(b'seen', 1, 1)
        game.profile_set(b'seen', 2, 1)
        self.assertEqual([name for name, _args in game.host.log], ['memcard_requestConfigSave'] * 2)


class DeferredAndPost(unittest.TestCase):
    def setUp(self):
        self.game = new_game()
        script = Script()
        script.entry('tick', script.call('setv', b'ran', 1) + script.call('addDeferedCall', b'tock'), 0)
        script.entry('tock', script.call('addv', b'ran', 1), 0)
        script.entry('leave', script.call('newWorld', b'cave'), 0)
        script.build(self.game)

    def test_a_queued_name_runs_on_the_next_tick(self):
        game = self.game
        game.queue_deferred(b'tick')
        self.assertEqual(game.var_get(b'ran'), 0)
        game.run_deferred()                     # nothing was in the half being run
        self.assertEqual(game.var_get(b'ran'), 0)
        game.run_deferred()                     # tick runs and queues tock
        self.assertEqual(game.var_get(b'ran'), 1)
        game.run_deferred()
        self.assertEqual(game.var_get(b'ran'), 2)
        game.run_deferred()
        self.assertEqual(game.var_get(b'ran'), 2)

    def test_the_65th_name_is_dropped(self):
        game = self.game
        for _ in range(70):
            game.queue_deferred(b'tock')
        self.assertEqual(game.defer_queued, 64)
        game.run_deferred()
        game.run_deferred()
        self.assertEqual(game.var_get(b'ran'), 64)

    def test_post_action_runs_once_and_skips_the_net_gate(self):
        game = self.game
        game.network_mode, game.active_player, game.alive_count = 1, 0, 2
        game.mem.w16(game.rec(0) + N.P_NEWWORLD_COOLDOWN, 100)
        game.run_script(b'leave')               # refused: the cooldown runs, two players alive
        self.assertEqual(game.mem.cstr(N.G_PENDING_LEVEL), b'')
        game.set_post_action(b'leave')
        game.run_post_action()                  # not gated
        self.assertEqual(game.mem.cstr(N.G_PENDING_LEVEL), b'cave')
        self.assertEqual(game.in_post_action, 0)
        self.assertEqual(game.mem.cstr(N.G_POST_ACTION), b'')

    def test_missing_entry_point(self):
        game = self.game
        game.draw_frame = 100
        self.assertEqual(game.run_script(b'nowhere'), -1)
        self.assertEqual(game.missing_stamp, 120)


class LevelChange(unittest.TestCase):
    def test_gate_starts_the_cooldown_of_the_active_player(self):
        game = new_game()
        game.network_mode, game.active_player, game.alive_count = 1, 1, 2
        self.assertEqual(game.net_gate(), 0)
        self.assertEqual(game.mem.u16(game.rec(1) + N.P_NEWWORLD_COOLDOWN), 600)
        self.assertEqual(game.net_gate(), 1)
        game.alive_count = 1                    # a lone survivor is never refused
        self.assertEqual(game.net_gate(), 0)

    def test_gate_is_off_outside_net_games(self):
        game = new_game()
        game.active_player = 0
        game.mem.w16(game.rec(0) + N.P_NEWWORLD_COOLDOWN, 5)
        game.alive_count = 2
        self.assertEqual(game.net_gate(), 0)
        self.assertEqual(game.mem.u16(game.rec(0) + N.P_NEWWORLD_COOLDOWN), 5)

    def test_orientation_comes_from_the_selected_object(self):
        game = new_game()
        door = game.new_object([b'door'], props=[b'Orientation=9', b'orientation=3', b'orientation=-2'])
        game.set_next_world(b'hub')
        self.assertEqual(game.pending_orientation, 0xFF)
        game.selected_obj = door.addr
        game.set_next_world(b'hub')
        self.assertEqual(game.pending_orientation, 0xFE)        # the last matching entry wins
        self.assertEqual(game.mem.cstr(N.G_PENDING_LEVEL), b'hub')


class Objects(unittest.TestCase):
    def test_a_shared_name_means_all_objects_in_table_order(self):
        game = new_game()
        first = game.new_object([b'gob'], flags=N.OF_CREATURE)
        second = game.new_object([b'GOB'])
        script = Script()
        script.entry('hide', script.call('hideMonster', b'Gob'), 0)
        script.build(game)
        game.run_script(b'hide')
        self.assertEqual([args[0] for name, args in game.host.log if name == 'obj_moveOffGrid'],
                         [first.addr, second.addr])
        self.assertTrue(first.flags & N.OF_NOT_RUN and second.flags & N.OF_NOT_RUN)
        self.assertEqual(first.u(N.C_HIDDEN_BYTE, 1) & 8, 8)
        self.assertEqual(second.u(N.C_HIDDEN_BYTE, 1) & 8, 0)   # only creatures get the hidden bit
        self.assertTrue(game.world.is_off_grid(first))

    def test_no_null_check_is_a_fault(self):
        game = new_game()
        script = Script()
        script.entry('go', script.call('setNoCollide', b'nobody', 1), 0)
        script.build(game)
        with self.assertRaises(ref_amx.HostFault):
            game.run_script(b'go')

    def test_kill_and_boss_flag(self):
        game = new_game()
        boss = game.new_object([b'boss'], flags=N.OF_CREATURE)
        boss.set_cflags(N.CF_BOSS | N.CF_BOSS_METER)
        script = Script()
        script.entry('go', script.call('setCFlag', b'boss', 0, 0) + script.call('setCFlag', b'boss', 5, 1)
                     + script.call('killMonster', b'boss'), 0)
        script.build(game)
        game.run_script(b'go')
        self.assertEqual(boss.cflags(), 0)
        self.assertEqual(boss.flags, N.OF_CREATURE | 0x2009)
        self.assertEqual(game.host.log, [('creature_startBossMusic', (boss.addr,)),
                                         ('virtual', (N.V_AI_STATE, boss.addr, 0x14))])


class RefusedAddress(unittest.TestCase):
    def setUp(self):
        self.game = new_game()
        self.a = self.game.new_object([b'soul19'], flags=N.OF_CREATURE)
        self.b = self.game.new_object([b'soul20'], flags=N.OF_CREATURE)
        script = Script()
        script.entry('same', script.call('rootMonster', b'soul20') + script.call('setCFlag', BAD, 26, 1)
                     + script.call('rootMonster', BAD), 0)
        script.entry('other', script.call('getv', b'q') + script.call('getRand') + script.call('getv', BAD))
        script.entry('first', script.call('getv', BAD))
        script.build(self.game)

    def test_the_last_pointer_of_the_same_slot_is_used_again(self):
        game = self.game
        game.run_script(b'same')
        self.assertEqual(self.b.cflags(), N.CF_FRIENDLY)
        self.assertEqual(self.a.cflags(), 0)
        self.assertEqual(game.host.log, [('virtual', (N.V_AI_STATE, self.b.addr, 0))] * 2)

    def test_unknown_stack_content_is_refused(self):
        for entry in (b'other', b'first'):
            with self.assertRaises(N.StackGarbage):
                self.game.run_script(entry)


class Players(unittest.TestCase):
    def test_gold_is_split_and_capped(self):
        game = new_game(3)
        game.mem.w32(game.rec(0) + N.P_GOLD, N.MAX_GOLD - 1)
        script = Script()
        script.entry('pay', script.call('givePlayerGold', 100) + script.call('checkPlayerGold'))
        script.entry('take', script.call('takePlayerGold', -100) + script.call('takePlayerGold', 300), 0)
        script.build(game)
        self.assertEqual(game.run_script(b'pay'), N.MAX_GOLD + 33 + 33)
        game.run_script(b'take')
        self.assertEqual([game.mem.s32(game.rec(s) + N.P_GOLD) for s in range(3)], [N.MAX_GOLD + 33 - 100, 0, 0])

    def test_got_item_sound_rewrites_the_active_player(self):
        game = new_game(4)
        game.active_player = 3
        game.mem.w32(game.rec(3) + N.P_HP, C.f32(10.0))
        script = Script()
        script.entry('go', script.call('playGotItemSound'), 0)
        script.build(game)
        game.run_script(b'go')
        self.assertEqual(game.active_player, 1)
        self.assertEqual(game.host.log, [('player_voice', (3, 9))])     # the voice still goes to slot 3

    def test_quest_list_stops_at_the_first_player_who_has_it(self):
        game = new_game(2)
        game.quest_add(b'Find it', b'text')
        self.assertEqual([game.mem.s32(game.rec(s) + N.P_QUEST_COUNT) for s in range(2)], [1, 1])
        game.mem.w32(game.rec(1) + N.P_QUEST_COUNT, 0)          # player 1 loses it
        game.quest_add(b'Find it', b'text')                     # player 0 has it: nobody gets it
        self.assertEqual(game.mem.s32(game.rec(1) + N.P_QUEST_COUNT), 0)
        game.quest_remove(b'Find it')
        self.assertEqual(game.mem.s32(game.rec(0) + N.P_QUEST_COUNT), 0)

    def test_medals_run_the_reward_entries_in_order(self):
        game = new_game(2)
        game.mem.w8(game.rec(1) + N.P_MEDALS + 4, 1)
        script = Script()
        for name in ('firstBronze', 'firstSilver', 'firstGold'):
            script.entry(name, script.call('addDeferedCall', name.encode()), 0)
        script.entry('win', script.call('grantGold', 4), 0)
        script.build(game)
        game.run_script(b'win')
        half = (game.defer_flip & 1) ^ 1
        queued = [game.mem.cstr(N.G_DEFER_NAMES + half * 0x1400 + 0x50 * k) for k in range(game.defer_queued)]
        self.assertEqual(queued, [b'firstBronze', b'firstSilver', b'firstGold', b'firstSilver', b'firstGold'])
        self.assertEqual(game.reward_player, 1)
        self.assertEqual([game.mem.s8(game.rec(s) + N.P_MEDALS + 4) for s in range(2)], [3, 3])

    def test_mission_complete_reaches_all_four_records(self):
        game = new_game(1)
        game.difficulty = 2
        game.mission_set_complete(2, 5, -1)
        self.assertEqual([game.mem.u8(game.mission_byte(s, 2, 5)) for s in range(4)], [2, 2, 2, 2])
        game.mission_set_available(2, 5, 1)
        self.assertEqual([game.mem.u8(game.mission_byte(s, 2, 5)) for s in range(4)], [3, 2, 2, 2])


class Helpers(unittest.TestCase):
    def test_scaled_time_and_rand(self):
        game = new_game()
        script = Script()
        script.entry('time', script.call('getScaledTime', 300))
        script.entry('rand', script.call('getRand'))
        script.build(game)
        self.assertEqual(game.run_script(b'time'), C.to_int(C.mul(C.mul(C.from_int(300), N.F_60), N.F_1_60)))
        game.seed = 1
        self.assertEqual(game.run_script(b'rand'), ((0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) >> 16)
        self.assertEqual(game.draws, 1)

    def test_start_dialog_message(self):
        game = new_game()
        game.active_player = 1
        game.mem.write(N.G_LEVEL_NAME, b'hub\0')
        game.host.handlers['net_isLocalSlot'] = lambda slot: 1
        script = Script()
        script.entry('talk', script.call('startDialog', b'elder', 2, 3), 0)
        script.build(game)
        game.run_script(b'talk')
        names = [name for name, _args in game.host.log]
        self.assertEqual(names, ['lump_load', 'Camera_update', 'net_isLocalSlot', 'Camera_getYaw', 'Camera_getPitch',
                                 'net_sendGameMsg'])
        message = game.host.log[-1][1][1]
        self.assertEqual(message[:8], b'\x00\x05elder\xff')
        self.assertEqual(message[8:12], bytes([1, 2, 3, 0]))
        self.assertEqual(len(message), 8 + 4 + 12 + 4)


if __name__ == '__main__':
    unittest.main()
