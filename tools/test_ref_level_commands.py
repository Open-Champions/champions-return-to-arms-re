#!/usr/bin/env python3
"""Unit tests of tools/ref_level_commands.py on hand-made memory (no game data).  The
comparison with the original code is tools/difftest_level_commands.py."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_level_commands as L          # noqa: E402
import ref_natives as N                 # noqa: E402


class Fake:
    """Just what Bodies needs of a ref_natives.Game."""

    def __init__(self):
        self.mem = N.Mem()
        self.runs = []

    def run_script(self, name):
        self.runs.append((name, self.mem.u32(L.G_SELECTED_OBJ)))
        return 0

    def obj_at(self, addr):
        return self.objects[addr]


def bodies():
    game = Fake()
    log = []

    def record(name, *args):
        log.append((name, args))
        return 0
    return game, L.Bodies(game, record), log


def vtable(mem, at, slots):
    for slot, function in slots.items():
        mem.w32(at + 8 * slot + 4, function)


class AutoPropTests(unittest.TestCase):
    def setUp(self):
        self.game, self.b, self.log = bodies()
        mem = self.mem = self.game.mem
        self.o = 0x100000
        vtable(mem, 0x5000, {18: L.AUTOPROP_SET_STATE, 19: L.AUTOPROP_SET_PASSABLE})
        mem.w32(self.o + L.O_VTABLE, 0x5000)
        mem.w32(self.o + L.O_FLAGS, L.OF_AUTOPROP | 1)
        mem.w32(self.o + L.AP_STATES, 2)
        model = 0x200000
        mem.w64(model + 8, 0xF0)
        mem.w16(model + 0x10, 2)
        mem.w8(model + 0x21, 4)             # records from model + 0x40
        mem.w64(model + 0x40, 0x0F)         # state-0 record: or 0x0f
        mem.w64(model + 0x50, 0x0F)         # state-1 record
        mem.w64(model + 0x58, 0x01)         # ... and clear bit 0
        mem.w32(self.o + L.AP_MODEL, model)
        mem.w8(self.o + L.AP_ANIM + 5, 1)
        clip = 0x300000
        mem.w32(clip + 4, 61)
        mem.w32(self.o + L.AP_ANIMS, clip)
        mem.w32(self.o + L.AP_ANIMS + 8, clip)
        mem.w32(self.o + L.AP_STATE_FLAGS + 8, L.SF_PASSABLE)

    def test_state_zero(self):
        self.mem.w32(self.o + L.AP_STATE, 1)
        self.mem.w64(self.o + L.AP_REACHED, 3)
        self.b.virtual(self.o, 18, 0)
        m = self.mem
        self.assertEqual(m.u32(self.o + L.AP_STATE), 0)
        self.assertEqual(m.u64(self.o + L.AP_REACHED), 0)
        self.assertEqual(m.u64(self.o + L.AP_MASK), ~0xF0 & L.M64)
        self.assertEqual(m.u32(self.o + L.AP_COUNTER), 62)
        self.assertEqual(m.u8(self.o + L.AP_ANIM + 4), 1)
        self.assertEqual(m.u16(self.o + L.AP_ANIM + 8 + 0x1C), 6)
        self.assertEqual(m.u32(self.o + L.O_FLAGS) & 1, 0)
        self.assertEqual(self.log, [])

    def test_state_one(self):
        self.b.virtual(self.o, 18, 1)
        m = self.mem
        self.assertEqual(m.u64(self.o + L.AP_REACHED), 3)
        self.assertEqual(m.u64(self.o + L.AP_MASK), ((~0xF0 | 0x0F) & ~0x1) & L.M64)
        self.assertEqual(m.u32(self.o + L.O_FLAGS) & 1, 1)

    def test_out_of_range(self):
        before = bytes(self.mem.read(self.o, 0x200))
        self.b.virtual(self.o, 18, 2)
        self.assertEqual(bytes(self.mem.read(self.o, 0x200)), before)

    def test_door(self):
        m = self.mem
        m.w32(self.o + L.AP_KIND, L.AK_DOOR)
        world = 0x400000
        m.w32(L.G_WORLD, world)
        m.w32(world + 0x54, world + 0x100)
        m.w32(world + 0x20, world + 0x400)
        m.w32(self.o + L.AP_PIECE, 1)
        m.w16(world + 0x100 + 28 + 0x18, 2)
        self.b.virtual(self.o, 18, 1)
        self.assertEqual(m.u16(world + 0x400 + 72 + 0x10) & 2, 2)
        self.assertEqual(self.log, [('world_movePiece', (world, 1, (0, 0, L.F_MINUS_256), 0))])


class GnomeTests(unittest.TestCase):
    def test_death(self):
        game, b, log = bodies()
        m = game.mem
        o = 0x100000
        vtable(m, 0x5000, {27: L.GNOME_SET_STATE, 28: L.CREATURE_ON_DEATH})
        m.w32(o + L.O_VTABLE, 0x5000)
        props = 0x500000
        m.w32(o + L.O_PROPS, props)

        class Obj:
            pass
        obj = Obj()
        obj.props = [b'name=g', b'deathscript=dies']
        game.objects = {o: obj}
        m.write(L.S_DEATH_SCRIPT, b'deathScript\0')
        m.write(L.S_DROP_ITEM, b'dropitem\0')
        cls = 0x600000
        m.w32(o + L.C_CLASS, cls)
        m.w32(cls + L.CLASS_DEATH_ANIMS + 8 * ((0x3C6EF35F >> 16) & 3), 0x700000)
        m.w8(o + L.C_ANIM + 5, 2)
        m.w32(L.G_SELECTED_OBJ, 0x1234)
        b.virtual(o, 27, 0x14)
        self.assertEqual(m.s16(o + L.C_AI_STATE), 0x14)
        self.assertEqual(m.u32(o + L.C_RAND), 0x3C6EF35F)
        self.assertEqual(m.u32(o + L.C_ANIM + 8), 0x700000)
        self.assertEqual(game.runs, [(b'dies', o)])
        self.assertEqual(m.u32(L.G_SELECTED_OBJ), 0)
        self.assertEqual(m.read(L.S_DEATH_SCRIPT, 11), b'deathscript')
        self.assertEqual(log, [('creature_bossMusicName', (o,))])

    def test_gate_refuses(self):
        game, b, log = bodies()
        m = game.mem
        for addr, value in ((L.G_ARENA, 1), (L.G_GATE_C, 1)):
            m.w32(addr, value)
        o = 0x100000
        m.w16(o + L.C_AI_STATE, 3)
        self.assertEqual(b.gnome_set_state(o, 0x14), 1)
        self.assertEqual(m.s16(o + L.C_AI_STATE), 3)


class SoundAndLumpTests(unittest.TestCase):
    def test_last_free_player(self):
        game, b, log = bodies()
        m = game.mem
        seq = 0x300000
        for k in (3, 9):
            m.w8(L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * k + 5, 1)
        for k in range(L.SOUND_SEQS):
            if k not in (3, 9):
                m.w8(L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * k + 4, 1)
                m.w32(L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * k + 8, 0x310000)
        m.w8(0x310000 + 0x3C, 7)
        m.w16(L.G_SOUND_SERIAL, 0x7F)
        handle = b.sound_play_on_object(seq, 0, L.F_1)
        self.assertEqual(handle, 9 | 0x7F << 8 | 0x8000)
        self.assertEqual(m.u16(L.G_SOUND_SERIAL), 0)
        b.sound_set_plays_while_frozen(handle)
        self.assertEqual(m.u8(L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * 9 + 0x3B), 1)
        self.assertEqual(b.sound_play_on_object(0, 0, L.F_1), L.M32)

    def test_loaded_lump_stores_nothing(self):
        game = Fake()
        b = L.Bodies(game, lambda name, *args: 0x7A0000 if name == 'lump_findLoaded' else 0)
        self.assertEqual(b.lump_load(b'x.lmp'), 0x7A0000)
        self.assertEqual(game.mem.writes, [])


if __name__ == '__main__':
    unittest.main()
