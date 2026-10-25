#!/usr/bin/env python3
"""Synthetic tests for tools/ref_items_gaps.py (no game file needed)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_items_gaps as R      # noqa: E402


class Mem:
    def __init__(self):
        self.b = {}

    def load(self, a, n):
        return int.from_bytes(bytes(self.b.get(a + i, 0) for i in range(n)), 'little')

    def store(self, a, n, v):
        for i, x in enumerate((v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')):
            self.b[a + i] = x

    def u8(self, a): return self.load(a, 1)
    def u32(self, a): return self.load(a, 4)
    def w8(self, a, v): self.store(a, 1, v)
    def w32(self, a, v): self.store(a, 4, v)


CTX = 0x1000


def lobby(own, count=4, kind=0, room=(3, 2, 7, 4)):
    m = Mem()
    m.w32(R.G_LOBBY_CTX, CTX)
    m.w8(CTX + R.LOBBY_OWN, own)
    for off, v in zip((R.ROOM_DIFFICULTY, R.ROOM_MODE, R.ROOM_KILL_LIMIT, R.ROOM_MISSION), room):
        m.w8(CTX + R.LOBBY_ROOM + off, v)
    m.w8(R.SETTINGS + R.S_COUNT, count)
    m.w8(R.SETTINGS + R.S_FLAGS, 0xF8)
    m.w8(R.G_CHAR_KIND, kind)
    R.lobby_set_host(m)
    return m


class Lobby(unittest.TestCase):
    def test_player_zero_is_host_and_takes_room(self):
        m = lobby(0, kind=1)
        self.assertEqual(m.u8(R.SETTINGS + R.S_FLAGS), R.FLAG_HOST | R.FLAG_KIND_B)
        self.assertEqual([m.u8(R.SETTINGS + o) for o in (2, 3, 4, 5)], [3, 2, 5, 7])

    def test_other_numbers_are_not_host_and_old_flags_are_cleared(self):
        m = lobby(2)
        self.assertEqual(m.u8(R.SETTINGS + R.S_FLAGS), R.FLAG_KIND_A)
        self.assertEqual(m.u8(R.SETTINGS + R.S_DIFFICULTY), 0)

    def test_count_grows_to_cover_own_number(self):
        self.assertEqual(lobby(3, count=2).u8(R.SETTINGS + R.S_COUNT), 4)
        self.assertEqual(lobby(1, count=2).u8(R.SETTINGS + R.S_COUNT), 2)

    def test_mission_is_room_value_plus_one_wrapping(self):
        m = lobby(0, room=(1, 1, 1, 0xFF))
        self.assertEqual(m.u8(R.SETTINGS + R.S_MISSION), 0)


class Menu(unittest.TestCase):
    def test_selection_sets_host(self):
        m = Mem()
        m.w8(R.SETTINGS, 0xFF)
        R.frontend_set_host(m, 1)
        self.assertEqual(m.u8(R.SETTINGS), 1)
        self.assertEqual(m.u8(R.SETTINGS + R.S_DIFFICULTY), 1)
        R.frontend_set_host(m, 0)
        self.assertEqual(m.u8(R.SETTINGS), 0)

    def test_kind_bits_keep_host_bit(self):
        m = Mem()
        m.w8(R.SETTINGS, 1)
        m.w8(R.G_CHAR_KIND, 4)          # & 3 == 0
        R.frontend_set_kind(m)
        self.assertEqual(m.u8(R.SETTINGS), 1 | R.FLAG_KIND_A)
        self.assertEqual(m.u8(R.SETTINGS + R.S_0A), 0xFF)


class Launch(unittest.TestCase):
    def test_record_addresses(self):
        self.assertEqual(R.own_record(0), 0x402B90)
        self.assertEqual(R.own_record(3), 0x402B90 + 3 * 0x144)
        self.assertEqual(R.own_record(0xFF), 0x402B90 - 0x144)

    def test_fill_only_for_host(self):
        m = Mem()
        rec = R.own_record(1)
        m.w32(rec + R.R_CM1, 0x55555555)
        self.assertEqual(R.launch_fill_host_fields(m, rec, 4), [])
        self.assertEqual(m.u32(rec + R.R_CM1), 0x55555555)
        m.w8(R.SETTINGS, R.FLAG_HOST)
        for o, v in ((2, 5), (3, 2), (4, 9), (5, 30)):
            m.w8(R.SETTINGS + o, v)
        self.assertEqual(R.launch_fill_host_fields(m, rec, 4), [(R.GAME_SCAN_CM1, 1)])
        self.assertEqual(m.u32(rec + R.R_CM1), 4)
        self.assertEqual([m.u8(rec + o) for o in (0xA0, 0xA1, 0xA2, 0xA3)], [5, 2, 30, 9])

    def receive(self, mode, cm1=7):
        m = Mem()
        m.w8(R.LAUNCH_RECS + R.R_MODE, mode)
        m.w8(R.LAUNCH_RECS + R.R_DIFFICULTY, 0xFE)
        m.w32(R.LAUNCH_RECS + R.R_CM1, cm1)
        calls = R.launch_receive(m)
        flags = tuple(m.u32(a) for a in (R.G_PVP_MODE_A, R.G_PVP_MODE_B, R.G_MODE_3))
        return calls, flags, m

    def test_receive_modes(self):
        self.assertEqual(self.receive(0)[:2], ([], (0, 0, 0)))
        self.assertEqual(self.receive(1)[:2], ([], (0, 1, 0)))
        self.assertEqual(self.receive(2)[:2], ([(R.GAME_SET_CM1, 7)], (1, 1, 0)))
        self.assertEqual(self.receive(3)[:2], ([(R.GAME_SET_CM1, 7)], (1, 1, 1)))
        self.assertEqual(self.receive(4)[:2], ([], (0, 0, 0)))
        self.assertEqual(self.receive(0x83)[:2], ([], (0, 0, 0)))

    def test_receive_difficulty_is_signed(self):
        self.assertEqual(self.receive(0)[2].u32(R.G_DIFFICULTY), 0xFFFFFFFE)

    def test_composition(self):
        self.assertEqual(R.cm1_word_after_launch(4, 9, 2), 4)
        self.assertEqual(R.cm1_word_after_launch(4, 9, 1), 9)


if __name__ == '__main__':
    unittest.main()
