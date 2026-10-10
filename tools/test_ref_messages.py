#!/usr/bin/env python3
"""test_ref_messages.py - unit tests of tools/ref_messages.py that need no game files.

They exercise the model's own logic on a memory image built here: made-up item definitions
and records, not game data.  That the model equals the game is the business of
tools/difftest_messages.py, which needs the executable.

  python3 -m unittest tools/test_ref_messages.py      (or run the file)
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_messages as RM                       # noqa: E402

DEFS = 0x00300000           # made-up definition rows, 0x40 bytes each
NAMES = 0x00310000
OBJECT = 0x00320000


class FakeTables:
    """What tools/ref_items.py reads from a Tables object for the equip test."""
    circlet_stem_equip = b'circlet'

    def __init__(self):
        self.by_addr = {}


class Definition:
    pass


class World:
    def __init__(self, net=True):
        self.mem = RM.Memory()
        self.tables = FakeTables()
        self.calls = []
        self.local = {0}
        self.answers = {}
        m = self.mem
        m.poke(RM.G_NETWORK_MODE, 1, 1 if net else 0)
        m.poke(RM.G_NUM_PLAYERS, 4, 2)
        for addr, text in ((RM.S_STACK_STEM_DROP, b'javelin'), (RM.S_STACK_STEM_SELL, b'javelin'),
                           (RM.S_UNIQUE_A, b'relic-a'), (RM.S_UNIQUE_B, b'relic-b'), (RM.S_RECALL_NAME, b'homestone')):
            for k, c in enumerate(text + b'\0'):          # made-up stand-ins for the game's strings
                m.poke(addr + k, 1, c)
        self.machine = RM.Machine(m, self.tables, self)
        self.ids = self.machine.register_all()
        del m.log[:]
        for slot in range(2):
            R = RM.G_PLAYERS + slot * RM.REC_SIZE
            m.poke(R + RM.R_OBJECT, 4, OBJECT + slot * 0x600)
            m.poke(R + RM.R_WEAPON_CLASS, 1, 5)
            for i in range(48):
                m.poke(R + RM.R_SKILL_RANKS + 4 * i, 2, 0xFFFF)
        self.next_def = 0

    # the callbacks object
    def get(self, name):
        def answer(*args):
            if name == 'net_isLocalSlot':
                return int(RM.s32(args[0]) in self.local)
            if name == 'net_getLocalPlayerSlot':
                return sorted(self.local)[args[0]]
            if name == 'world_findFreeSpot':
                return (1, 2, 3)
            return self.answers.get(name, 0)
        return answer

    def definition(self, name, slot, category, subtype=0, flags=0):
        m, i = self.mem, self.next_def
        self.next_def += 1
        addr, text = DEFS + i * 0x40, NAMES + i * 0x20
        for k, c in enumerate(name + b'\0'):
            m.poke(text + k, 1, c)
        m.poke(addr, 4, text)
        m.poke(addr + 0x1C, 1, slot)
        m.poke(addr + 0x1D, 1, category)
        m.poke(addr + 0x1E, 1, subtype)
        m.poke(addr + 0x28, 8, flags)
        d = Definition()
        d.addr, d.name, d.slot, d.category, d.subtype, d.flags, d.damage_bits = addr, name, slot, category, subtype, flags, 0
        self.tables.by_addr[addr] = d
        return addr

    def give(self, slot, definition, count=1, flags=0):
        """Append a record the way inventory_giveItem leaves it; returns its address."""
        m = self.mem
        R = RM.G_PLAYERS + slot * RM.REC_SIZE
        bag = m.load(definition + 0x1D, 1)
        n = m.load(R + RM.R_BAG_COUNT + bag * RM.BAG_SIZE, 4)
        item = R + RM.R_BAGS + bag * RM.BAG_SIZE + n * RM.ITEM_SIZE
        m.poke(item, 4, definition)
        m.poke(item + 4, 2, count)
        m.poke(item + 8, 8, flags)
        m.poke(item + 0x20, 2, 0xFFFF)
        m.poke(item + 0x22, 2, n)
        for k in range(4):
            m.poke(item + 0x24 + 8 * k, 2, 0xFFFF)
        m.poke(R + RM.R_BAG_COUNT + bag * RM.BAG_SIZE, 4, n + 1)
        return item

    def deliver(self, message):
        family, data = message
        self.machine.calls = []
        self.machine.deliver(self.ids[family], data)
        return [name for name, _args in self.machine.calls]

    def rec(self, slot, offset, size=4):
        return self.mem.load(RM.G_PLAYERS + slot * RM.REC_SIZE + offset, size)


class Channels(unittest.TestCase):
    def test_start_up_order_gives_the_ids(self):
        w = World()
        self.assertEqual(w.ids, {'cutscene': 0, 'voice': 1, 'dialog': 2, 'game': 3, 'null': 4,
                                 'inventory': 5, 'text': 6, 'shop': 7})
        self.assertEqual(w.machine.register_handler(RM.H_SHOP), 7)      # found, not added again

    def test_message_lengths(self):
        self.assertEqual(len(RM.msg_drop(0, 1, 2, 3, 4, 0, 0)[1]), 13)
        self.assertEqual(len(RM.msg_sell(0, 1, 2, 3, 4, 0)[1]), 13)
        self.assertEqual(len(RM.msg_equip(0, 0x4D9000)[1]), 8)
        self.assertEqual(len(RM.msg_assign_spell(0, 1, 1, 5)[1]), 16)
        self.assertEqual(RM.msg_load_level()[1], b'\x0b\0\0\0')         # the name is not sent
        self.assertEqual(RM.msg_new_world(b'hub')[1], b'\x07hub\0')

    def test_net_send_goes_to_the_local_ring(self):
        w = World()
        w.local = {1}
        w.machine.send(w.ids['inventory'], RM.msg_level_ack(1, 9)[1])
        peer = RM.G_PEERS + RM.PEER_SIZE
        ring = peer + 0xC + 0x24A0
        self.assertEqual([w.mem.load(ring + i, 1) for i in range(5)], [5, 3, 9, 1, 9])
        self.assertEqual(w.mem.load(peer + 0x44AC, 4), 5)
        self.assertEqual(w.rec(1, RM.R_ACK_LEVEL, 1), 0)                # not executed yet

    def test_offline_send_runs_the_handler_at_once(self):
        w = World(net=False)
        w.machine.send(w.ids['inventory'], RM.msg_level_ack(1, 9)[1])
        self.assertEqual(w.rec(1, RM.R_ACK_LEVEL, 1), 9)


class Inventory(unittest.TestCase):
    def test_drop_takes_one_and_removes_the_last(self):
        w = World()
        potion = w.definition(b'tonic', 16, 2)
        gem = w.definition(b'pebble', 16, 2)
        w.give(0, potion, 2)
        w.give(0, gem, 1)
        calls = w.deliver(RM.msg_drop(0, 0, 2, 0, 0, 0, 0))
        self.assertEqual(w.rec(0, RM.R_BAGS + 2 * RM.BAG_SIZE + 4, 2), 1)
        self.assertEqual(w.rec(0, RM.R_BAG_COUNT + 2 * RM.BAG_SIZE), 2)
        self.assertIn('world_findFreeSpot', calls)
        w.answers['pool_new'] = 0x00330000
        w.deliver(RM.msg_drop(0, 0, 2, 0, 0, 0, 0))
        self.assertEqual(w.rec(0, RM.R_BAG_COUNT + 2 * RM.BAG_SIZE), 1)
        self.assertEqual(w.rec(0, RM.R_BAGS + 2 * RM.BAG_SIZE), gem)    # the gap is closed
        self.assertEqual(w.rec(0, RM.R_BAGS + 2 * RM.BAG_SIZE + 0x22, 2), 0)        # and renumbered
        self.assertEqual(w.mem.load(0x00330000 + 0x14C, 2), 1)          # the dropped object's stack

    def test_drop_of_an_empty_cell_does_nothing(self):
        w = World()
        self.assertEqual(w.deliver(RM.msg_drop(0, 7, 1, 0, 0, 0, 0)), ['net_allPlayersState2'])
        self.assertEqual(w.mem.log, [])

    def test_ammunition_leaves_twenty_at_a_time(self):
        w = World()
        arrows = w.definition(b'darts', 8, 0)
        item = w.give(0, arrows, 45)
        w.deliver(RM.msg_drop(0, 0, 0, 0, 0, 0, 2))
        self.assertEqual(w.mem.load(item + 4, 2), 25)

    def test_removal_repoints_equipment(self):
        w = World()
        hat, boots = w.definition(b'hat', 9, 1), w.definition(b'boots', 12, 1)
        first, second = w.give(0, hat), w.give(0, boots)
        w.deliver(RM.msg_equip(0, second))
        self.assertEqual(w.rec(0, RM.R_EQUIP + 12 * 4), second)
        w.deliver(RM.msg_drop(0, 0, 1, 0, 0, 0, 1))
        self.assertEqual(w.rec(0, RM.R_EQUIP + 12 * 4), first)          # the record moved down

    def test_two_handed_weapon_clears_the_hands(self):
        w = World()
        sword, shield, maul = w.definition(b'sword', 0, 0), w.definition(b'targe', 3, 1), w.definition(b'maul', 2, 0, 1)
        a, b, c = w.give(0, sword), w.give(0, shield), w.give(0, maul)
        w.deliver(RM.msg_equip(0, a))
        w.deliver(RM.msg_equip(0, b))
        self.assertEqual((w.rec(0, RM.R_EQUIP), w.rec(0, RM.R_EQUIP + 12)), (a, b))
        w.deliver(RM.msg_equip(0, c))
        self.assertEqual([w.rec(0, RM.R_EQUIP + 4 * k) for k in range(4)], [0, 0, c, 0])
        self.assertEqual(w.rec(0, RM.R_WEAPON_CLASS, 1), 1)
        self.assertEqual(w.rec(0, RM.R_SET_WEAPON), c)

    def test_bow_goes_to_the_second_set(self):
        w = World()
        bow = w.definition(b'bow', 2, 0, 4)
        item = w.give(0, bow)
        calls = w.deliver(RM.msg_equip(0, item))
        self.assertEqual((w.rec(0, RM.R_ACTIVE_SET, 1), w.rec(0, RM.R_SET_WEAPON + 4)), (1, item))
        self.assertIn('vars_set', calls)

    def test_stat_points(self):
        w = World()
        w.mem.poke(RM.G_PLAYERS + RM.R_STAT_POINTS, 1, 1)
        w.deliver(RM.msg_stat_point(0, 2))
        self.assertEqual((w.rec(0, RM.R_BASE_STATS + 8), w.rec(0, RM.R_STAT_POINTS, 1), w.rec(0, RM.R_LVLUP_DONE, 1)),
                         (1, 0, 1))
        w.deliver(RM.msg_stat_point(0, 2))                              # none left: nothing is raised
        self.assertEqual(w.rec(0, RM.R_BASE_STATS + 8), 1)
        w.deliver(RM.msg_stat_point(0, 6))                              # the free raise needs no point
        self.assertEqual(w.rec(0, RM.R_BASE_STATS + 8), 2)
        w.deliver(RM.msg_stat_point(0, 8))
        self.assertEqual(w.rec(0, RM.R_SKILL_POINTS), 1)


class Game(unittest.TestCase):
    def test_quick_slots_exchange(self):
        w = World()
        R = RM.G_PLAYERS
        w.mem.poke(R + RM.R_QUICK_A, 1, 3)
        w.mem.poke(R + RM.R_QUICK_B, 1, 5)
        w.deliver(RM.msg_quick_slot(0, 0, 5))
        self.assertEqual((w.rec(0, RM.R_QUICK_A, 1), w.rec(0, RM.R_QUICK_B, 1)), (5, 3))
        w.deliver(RM.msg_quick_slot(0, 1, 7))
        self.assertEqual((w.rec(0, RM.R_QUICK_A, 1), w.rec(0, RM.R_QUICK_B, 1)), (5, 7))

    def test_menu_state(self):
        w = World()
        w.deliver(RM.msg_menu_state(0, 2))
        self.assertEqual(w.mem.load(OBJECT + 0xC, 4), 0xC00000)
        w.deliver(RM.msg_menu_state(0, 0))
        self.assertEqual(w.mem.load(OBJECT + 0xC, 4), 0x400000)         # 0x400000 is left to Player_run
        self.assertEqual(w.rec(0, RM.R_MENU_COUNTDOWN, 1), 10)
        self.assertEqual([w.mem.load(RM.G_INPUT_LOCK + 4 * k, 4) for k in range(3)], [0x3C, 0xF0, 0])

    def test_menu_state_without_an_object_is_ignored(self):
        w = World()
        w.mem.poke(RM.G_PLAYERS + RM.R_OBJECT, 4, 0)
        w.deliver(RM.msg_menu_state(0, 1))
        self.assertEqual(w.mem.log, [])

    def test_checksum_mismatch_disconnects_the_other_slot(self):
        w = World()
        w.mem.poke(RM.G_CHECKSUM_EXPECTED, 4, 0x1111)
        w.mem.poke(RM.G_CHECKSUM_EXPECTED + 8, 4, 0x2222)
        w.deliver(RM.msg_checksum(0, 0x1111, 0))
        calls = w.deliver(RM.msg_checksum(1, 0x9999, 0))
        self.assertEqual(calls, ['net_getLocalPlayerSlot', 'net_disconnectPlayer'])
        self.assertEqual(w.mem.load(RM.G_CHECKSUM_FAILED, 4), 1)

    def test_load_level_reads_past_its_four_bytes(self):
        w = World()
        w.machine.deliver(w.ids['game'], RM.msg_load_level()[1] + b'blood1\0')
        self.assertEqual(bytes(w.mem.load(RM.G_PENDING_LEVEL + i, 1) for i in range(7)), b'blood1\0')
        self.assertEqual(w.mem.load(RM.G_MENU_LOCKOUT, 4), 0x3C)


class Shop(unittest.TestCase):
    def test_buy_needs_the_gold_and_ignores_a_full_bag(self):
        w = World()
        ring = w.definition(b'band', 5, 2)
        d = w.tables.by_addr[ring]
        d.price = 100
        stock = 0x00340000
        w.mem.poke(stock, 4, ring)
        w.mem.poke(stock + 4, 2, 1)
        w.mem.poke(RM.G_PLAYERS + RM.R_GOLD, 4, 58)                     # 100 x 0.6 truncates to 59
        w.deliver(RM.msg_buy(0, stock))
        self.assertEqual((w.rec(0, RM.R_GOLD), w.rec(0, RM.R_BAG_COUNT + 2 * RM.BAG_SIZE)), (58, 0))
        w.mem.poke(RM.G_PLAYERS + RM.R_GOLD, 4, 500)
        w.deliver(RM.msg_buy(0, stock))
        self.assertEqual((w.rec(0, RM.R_GOLD), w.rec(0, RM.R_BAG_COUNT + 2 * RM.BAG_SIZE)), (441, 1))
        w.mem.poke(RM.G_PLAYERS + RM.R_BAG_COUNT + 2 * RM.BAG_SIZE, 4, 64)
        w.deliver(RM.msg_buy(0, stock))                                 # paid for, not received
        self.assertEqual((w.rec(0, RM.R_GOLD), w.rec(0, RM.R_BAG_COUNT + 2 * RM.BAG_SIZE)), (382, 64))


if __name__ == '__main__':
    unittest.main()
