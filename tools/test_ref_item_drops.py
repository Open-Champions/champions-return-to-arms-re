#!/usr/bin/env python3
"""Synthetic tests of tools/ref_item_drops.py (no game file needed)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_natives as N          # noqa: E402
import ref_script_items as R     # noqa: E402
import ref_item_drops as D       # noqa: E402

M32 = 0xFFFFFFFF


class Host:
    def __init__(self, bounds=(0, 0, 0, 0, 0, 0)):
        self.log, self.bounds = [], bounds

    def call(self, name, *args):
        self.log.append(name)
        if name == 'model_getBounds':
            return [v & M32 for v in self.bounds]
        return 0


def world(launch_seed=0x1234):
    mem = N.Mem()
    definition = 0x00200000
    mem.store(definition + 0x34, 4, 2)                  # model row 2
    for row in range(4):
        mem.store(D.MODEL_TABLE + 16 * row, 4, 0x00210000 + row * 0x20)
        mem.store(D.MODEL_TABLE + 16 * row + 4, 4, 0x00210010 + row * 0x20)
        mem.write(0x00210000 + row * 0x20, b'm%d\0' % row)
        mem.write(0x00210010 + row * 0x20, b't%d\0' % row)
    mem.write(D.S_ITEM_LUMP, b'lump\0')
    item = 0x00220000
    mem.store(item, 4, definition)
    mem.store(item + 4, 2, 1)
    mem.store(R.G_RAND_SEED, 4, launch_seed)
    return mem, item


class GroundTests(unittest.TestCase):
    def ctor(self, launch=0, flags=0, options=0):
        mem, item = world()
        mem.store(item + 8, 8, flags)
        mem.store(D.G_PROP_OPTIONS, 4, options)
        host = Host((-10, -20, 0, 10, 20, 30))
        g = D.Ground(mem, None, host)
        block = 0x00300000
        g.itemprop_ctor2(block, (0, 0, 0), item, launch)
        return mem, g, block, host

    def test_one_shared_draw(self):
        mem, g, block, _h = self.ctor()
        self.assertEqual(mem.load(R.G_RAND_SEED, 4), (0x1234 * 0x19660D + 0x3C6EF35F) & M32)
        self.assertEqual(g.own_draws, 1)

    def test_launch_draws(self):
        for launch, own in ((0, 1), (1, 3), (8, 3), (0x10, 4), (0x20, 2), (0x40, 2), (0x19, 8), (0x1FFFF, 10)):
            _m, g, _b, _h = self.ctor(launch)
            self.assertEqual(g.own_draws, own, hex(launch))

    def test_fields(self):
        mem, g, b, host = self.ctor()
        self.assertEqual(mem.load(b + 0x48, 4), D.VT_ITEMPROP)
        self.assertEqual(mem.read(b + 0x148, 0x48), mem.read(0x00220000, 0x48))
        self.assertEqual(mem.load(b + 0xE8, 8), (1 << 64) - 1)
        self.assertEqual(mem.read(b + 0x64, 3), b'm2\0')
        self.assertEqual(mem.read(b + 0xA4, 3), b't2\0')
        flags = mem.load(b + 0xC, 4)
        self.assertEqual(flags & 0x1800, 0)
        self.assertTrue(flags & 0x102000 == 0x102000)
        self.assertEqual(mem.load(b + 0x10E, 2), 0xB4)
        self.assertEqual(host.log.count('obj_updateGridCell'), 2)

    def test_flag_bit_39_clears_0x3000(self):
        mem, _g, b, _h = self.ctor(flags=1 << 39)
        self.assertEqual(mem.load(b + 0xC, 4) & 0x3000, 0)

    def test_variant_row(self):
        mem, item = world()
        mem.store(item + 8, 8, 0x1000000000 | (1 << 11))
        g = D.Ground(mem, None, Host())
        self.assertEqual(g.resource_index(item), 3)

    def test_null_definition_faults(self):
        mem, item = world()
        mem.store(item, 4, 0)
        with self.assertRaises(D.Fault):
            D.Ground(mem, None, Host()).itemprop_ctor2(0x00300000, (0, 0, 0), item, 0)

    def test_unaligned_item_faults(self):
        mem, item = world()
        mem.write(item + 4, mem.read(item, 0x48))
        mem.store(item + 4, 4, 0x00200000)
        with self.assertRaises(D.Fault):
            D.Ground(mem, None, Host()).itemprop_ctor2(0x00300000, (0, 0, 0), item + 4, 0)


class RandomTests(unittest.TestCase):
    def test_blank_record(self):
        mem = N.Mem()
        mem.write(0x1000, b'\xAA' * 0x48)
        D.blank_record(mem, 0x1000)
        data = mem.read(0x1000, 0x48)
        self.assertEqual(data[:0x10], b'\xAA' * 0x10)
        self.assertEqual(data[0x10:0x20], bytes(16))
        self.assertEqual(data[0x20:0x22], b'\xFF\xFF')
        for k in range(4):
            self.assertEqual(struct.unpack_from('<h', data, 0x24 + 8 * k)[0], -1)
        self.assertEqual(data[0x44:], b'\xAA' * 4)

    def test_constants(self):
        self.assertEqual(D.TRIES, 10)
        self.assertEqual(sorted(D.SPECIAL_ITEMS), [1, 2, 3])
        self.assertEqual(D.ITEM_BLOCK, 0x190)


if __name__ == '__main__':
    unittest.main()
