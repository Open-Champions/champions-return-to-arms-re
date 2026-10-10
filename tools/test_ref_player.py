#!/usr/bin/env python3
"""Unit tests for tools/ref_player.py that need no game files: the model's own logic on a
made-up memory image.  (The comparison with the game's code is tools/difftest_player.py.)"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_player as RP                         # noqa: E402

P = 0x01000000              # the player object
ATTACK, ABILITY_A, BLOCK, POTION_A, SWAP = 0x4000, 0x2000, 0x0400, 0x0100, 0x0800


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class Game:
    """A blank memory image with one living player in slot `slot`, standing in state 2."""

    def __init__(self, slot=0):
        self.mem = mem = RP.Memory()
        self.slot = slot
        self.R = R = RP.G_PLAYERS + slot * RP.REC_SIZE
        self.pad = RP.G_PADS + slot * RP.PAD_SIZE
        mem.write_bytes(RP.S_NEWSTYLE, b'newstyle\0')
        mem.write_bytes(RP.S_BURNINGHANDS, b'burninghands\0')
        mem.write_bytes(RP.G_LEVEL_NAME, b'somewhere\0')
        mem.write_bytes(RP.S_INNPIT, b'innpit\0')
        self.w32(P + 0xC, 0x4060)
        self.w32(P + 0x3C8, slot)
        self.w32(P + 0x58C, 2)
        self.w8(P + 0x482, 15)
        self.w16(P + 0x4B2, 1000)                   # the idle voice is far away
        self.w32(R + 0xAC, f32(100.0))
        self.w32(R + 0xB0, f32(100.0))
        self.w32(R + 0xC0, f32(50.0))
        self.w32(R + 0xC4, f32(50.0))
        self.w32(R + 0x43D8, P)
        self.w32(R + 0x4B08, 0xFFFF)
        self.w32(RP.G_KILL_PLANE, f32(-100000.0))
        self.w32(RP.G_TIMED_MODIFIERS, 0xFFFFFFFF)
        self.w32(RP.G_SIM_FRAME, 5000)
        for addr, mask in ((RP.G_BTN_ATTACK, ATTACK), (RP.G_BTN_ABILITY_A, ABILITY_A), (RP.G_BTN_BLOCK, BLOCK),
                           (RP.G_BTN_POTION_A, POTION_A), (RP.G_BTN_SWAP, SWAP)):
            self.w32(addr + 4 * slot, mask)
        self.callbacks = {'net_isSlotActive': lambda s: 1}

    def w32(self, addr, value):
        self.mem.poke(addr, 4, value)

    def w16(self, addr, value):
        self.mem.poke(addr, 2, value)

    def w8(self, addr, value):
        self.mem.poke(addr, 1, value)

    def press(self, held, pressed=None):
        self.w32(self.pad + 8, held)
        self.w32(self.pad + 0xC, held if pressed is None else pressed)

    def tick(self):
        return RP.Tick(self.mem, P, self.callbacks).run()


def names(outcome):
    return [name for name, _args in outcome.calls]


def call(outcome, name):
    return [args for n, args in outcome.calls if n == name]


class PadChoice(unittest.TestCase):
    def test_living_player_reads_its_own_pad(self):
        game = Game(slot=2)
        self.assertEqual(call(game.tick(), 'Player_move'), [(P, 0, game.pad, 0)])

    def test_dead_player_reads_the_zero_pad(self):
        game = Game()
        game.w32(game.R + 0xAC, 0)
        self.assertEqual(call(game.tick(), 'Player_move'), [(P, 0, RP.G_ZERO_PAD, 0)])

    def test_menu_lockout_swaps_the_pad_only_offline(self):
        for net, pad in ((0, RP.G_ZERO_PAD), (1, None)):
            game = Game()
            game.w32(RP.G_MENU_LOCKOUT, 60)
            game.w8(RP.G_NETWORK_MODE, net)
            self.assertEqual(call(game.tick(), 'Player_move')[0][2], pad or game.pad)

    def test_inactive_slot_reads_the_zero_pad(self):
        game = Game()
        game.callbacks = {}
        self.assertEqual(call(game.tick(), 'Player_move')[0][2], RP.G_ZERO_PAD)


class Gates(unittest.TestCase):
    """The gate at 0x1a5b98-0x1a5c20 around weapon swap (its Player_recalcDamage) and interact."""

    def gate(self, **changes):
        game = Game()
        for key, value in changes.items():
            {'selector': lambda v: game.w32(RP.G_SPELL_SELECTOR, v),
             'lockout': lambda v: game.w32(RP.G_MENU_LOCKOUT, v),
             'paused': lambda v: game.w32(RP.G_PAUSED, v),
             'net': lambda v: game.w8(RP.G_NETWORK_MODE, v),
             'copy': lambda v: game.w32(P + 0xC, 0x4060 | (0x20000 if v else 0))}[key](value)
        out = names(game.tick())
        return 'Player_recalcDamage' in out, 'Player_interact' in out

    def test_open_gate(self):
        self.assertEqual(self.gate(), (True, True))

    def test_k1_selector_stops_interact_only(self):
        self.assertEqual(self.gate(selector=1), (True, False))
        self.assertEqual(self.gate(selector=1, net=1), (True, False))

    def test_d26_lockout_stops_both_also_in_a_net_game(self):
        self.assertEqual(self.gate(lockout=60, net=1), (False, False))
        self.assertEqual(self.gate(lockout=60), (False, False))

    def test_pause_and_copy_stop_both(self):
        self.assertEqual(self.gate(paused=1), (False, False))
        self.assertEqual(self.gate(copy=1), (False, False))


class Potion(unittest.TestCase):
    """K2: how the potion leaves the bag depends on this machine's inventory screen."""

    def game(self):
        game = Game()
        mem, R = game.mem, game.R
        game.w32(R + 0xAC, f32(40.0))
        names_at, definition, text = 0x00900000, 0x00900100, 0x00900200
        mem.write_bytes(text, b'small\0')
        mem.write_bytes(text + 0x10, b'other\0')
        for size in range(9):
            game.w32(RP.G_POTION_NAMES[0] + 4 * size, text if size == 0 else text + 0x10)
        game.w32(definition, text)
        game.w32(R + 0x2540, definition)
        game.w16(R + 0x2540 + 4, 3)
        game.w32(R + 0x3740, 1)
        game.press(POTION_A)
        del names_at
        return game

    @staticmethod
    def pending(game):
        return int(struct.unpack('<f', struct.pack('<I', game.mem.load(game.R + 0xB4, 4)))[0])

    def test_direct_removal(self):
        game = self.game()
        out = game.tick()
        self.assertEqual(game.mem.load(game.R + 0x2540 + 4, 2), 2)
        self.assertNotIn('invmsg_sendDrop', names(out))
        self.assertEqual(self.pending(game), 59)                            # 60 points, less one tick's delivery

    def test_owner_with_inventory_open_sends_a_message_instead(self):
        game = self.game()
        game.w8(RP.G_LOCAL_MENU_OPEN, 1)
        game.w32(RP.G_ITEM_LIST_CELLS, 0x00A00000)
        game.callbacks['net_isLocalSlot'] = lambda s: 1
        out = game.tick()
        self.assertEqual(game.mem.load(game.R + 0x2540 + 4, 2), 3)          # the bag is not touched
        self.assertEqual(len(call(out, 'invmsg_sendDrop')), 1)
        self.assertEqual(self.pending(game), 59)                            # the healing is the same

    def test_other_machine_with_its_inventory_open_removes_directly(self):
        game = self.game()
        game.w8(RP.G_LOCAL_MENU_OPEN, 1)
        game.w32(RP.G_ITEM_LIST_CELLS, 0x00A00000)
        game.tick()
        self.assertEqual(game.mem.load(game.R + 0x2540 + 4, 2), 2)

    def test_prediction_copy_drinks_nothing(self):
        game = self.game()
        game.w32(P + 0xC, 0x4060 | 0x20000)
        game.tick()
        self.assertEqual(game.mem.load(game.R + 0x2540 + 4, 2), 3)
        self.assertEqual(game.mem.load(game.R + 0xB4, 4), 0)


class Seed(unittest.TestCase):
    def test_idle_fidget_draws_once_with_four_tracks(self):
        game = Game()
        game.w8(P + 0x118, 4)
        game.w32(RP.G_RAND_SEED, 12345)
        out = game.tick()
        self.assertEqual(out.draws, 1)
        self.assertEqual(out.seed, (12345 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)

    def test_no_draw_with_another_track_count(self):
        game = Game()
        game.w8(P + 0x118, 5)
        self.assertEqual(game.tick().draws, 0)

    def test_idle_voice_draw(self):
        game = Game()
        game.w8(P + 0x118, 5)
        game.w16(P + 0x4B0, 10)
        game.w16(P + 0x4B2, 10)
        out = game.tick()
        self.assertEqual(out.draws, 1)
        self.assertEqual(call(out, 'player_voice'), [(0, 1)])
        self.assertEqual(game.mem.load(P + 0x4B0, 2), 0)


class States(unittest.TestCase):
    def test_attack_starts_a_swing(self):
        game = Game()
        game.press(ATTACK)
        game.w32(P + 0x448, 4000)
        out = game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 1)
        self.assertEqual(game.mem.load(P + 0x448, 4), 5000)
        self.assertEqual(call(out, 'anim_startBlendInOut')[0][2], 0x802)
        self.assertNotIn('Player_move', names(out))                       # the switch is left at once

    def test_block_needs_something_to_block_with(self):
        game = Game()
        game.press(BLOCK, 0)
        game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 2)
        game = Game()
        game.w32(game.R + 0x43FC, 0x00900000)                              # a shield
        game.press(BLOCK, 0)
        game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 8)
        self.assertEqual(game.mem.load(P + 0x454, 4), 1)

    def test_no_combat_level_refuses_the_block(self):
        game = Game()
        game.w32(game.R + 0x43FC, 0x00900000)
        game.w32(RP.G_LEVEL_FLAGS, 0x10000000)
        game.press(BLOCK, 0)
        game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 2)

    def test_hit_reaction_ends_when_the_flag_clears(self):
        game = Game()
        game.w32(P + 0x58C, 3)
        game.w16(P + 0x11A, 8)
        game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 3)
        game.w16(P + 0x11A, 0)
        game.tick()
        self.assertEqual(game.mem.load(P + 0x58C, 4), 2)

    def test_record_countdowns_are_for_real_players_only(self):
        for copy, left in ((0, 4), (1, 5)):
            game = Game()
            game.w32(P + 0xC, 0x4060 | (0x20000 if copy else 0))
            game.w8(game.R + 0x4BC9, 5)
            game.w8(game.R + 0x4C27, 5)
            game.tick()
            self.assertEqual(game.mem.load(game.R + 0x4BC9, 1), left)
            self.assertEqual(game.mem.load(game.R + 0x4C27, 1), left)

    def test_scripted_control_leaves_early(self):
        game = Game()
        game.w8(P + 0x231, 1)
        out = game.tick()
        self.assertEqual(out.returned, 'scripted')
        self.assertNotIn('Player_processDamage', names(out))


if __name__ == '__main__':
    unittest.main()
