#!/usr/bin/env python3
"""Synthetic tests of tools/ref_hide_monster.py (no game file needed)."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as R                    # noqa: E402
import ref_hide_monster as H            # noqa: E402
import ref_objects as O                 # noqa: E402


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


NEAR = (f32(10.0), f32(10.0), 0)
FAR = (f32(20000.0), 0, 0)


class World:
    def __init__(self):
        self.w = O.World()
        self.w.init()
        self.bytes = {}

    def new(self, name, flags=0, pos=NEAR, byte=0):
        obj = self.w.new_object(0x590, pos, props=[b'name=' + name] if name is not None else None)
        if flags:
            obj.flags |= flags
            self.w.update_grid_cell(obj)
        if flags & H.FLAG_CREATURE:
            self.bytes[obj.addr] = byte
        return obj

    def off(self, obj):
        return self.w.is_off_grid(obj)

    def cell_front(self, obj):
        head = self.w.home_cell(obj, False)
        first = next(iter(R.walk(head, 0)), None)
        return first


class HideShow(unittest.TestCase):
    def test_hide_creature_sets_flag_byte_and_off_grid(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE, byte=0x41)
        self.assertEqual(H.hide_monster(t.w, b'boss', t.bytes), 0)
        self.assertTrue(t.off(c))
        self.assertEqual(c.flags & H.FLAG_NOT_RUN, H.FLAG_NOT_RUN)
        self.assertEqual(t.bytes[c.addr], 0x49)

    def test_non_creature_byte_untouched(self):
        t = World()
        d = t.new(b'door')
        H.hide_monster(t.w, b'door', t.bytes)
        self.assertTrue(t.off(d))
        self.assertNotIn(d.addr, t.bytes)
        self.assertEqual(d.flags, H.FLAG_NOT_RUN)

    def test_show_reverses_and_keeps_other_bits(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE | 0x1000, byte=0x09)
        H.hide_monster(t.w, b'boss', t.bytes)
        H.show_monster(t.w, b'boss', t.bytes)
        self.assertFalse(t.off(c))
        self.assertEqual(c.flags, H.FLAG_CREATURE | 0x1000)
        self.assertEqual(t.bytes[c.addr], 0x01)

    def test_hide_twice_is_idempotent_for_state(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE)
        H.hide_monster(t.w, b'boss', t.bytes)
        H.hide_monster(t.w, b'boss', t.bytes)
        self.assertTrue(t.off(c))
        self.assertEqual(t.bytes[c.addr], 8)

    def test_show_object_not_hidden_moves_it_to_front_of_cell(self):
        t = World()
        a = t.new(b'a')
        b = t.new(b'b')
        self.assertIs(t.cell_front(a), b)       # the later link is in front
        H.show_monster(t.w, b'a', t.bytes)
        self.assertIs(t.cell_front(a), a)       # showMonster relinks even when not hidden

    def test_show_clears_flag_set_by_other_means(self):
        t = World()
        d = t.new(b'door', H.FLAG_NOT_RUN)
        H.show_monster(t.w, b'door', t.bytes)
        self.assertEqual(d.flags & H.FLAG_NOT_RUN, 0)

    def test_every_object_of_the_name_in_any_case(self):
        t = World()
        objs = [t.new(b'k1') for _ in range(5)] + [t.new(b'K1')]
        other = t.new(b'k2')
        H.hide_monster(t.w, b'k1', t.bytes)
        self.assertTrue(all(t.off(o) for o in objs))
        self.assertFalse(t.off(other))

    def test_name_with_no_object_does_nothing(self):
        t = World()
        d = t.new(b'door')
        before = d.flags
        self.assertEqual(H.hide_monster(t.w, b'nobody', t.bytes), 0)
        self.assertEqual(H.show_monster(t.w, b'', t.bytes), 0)
        self.assertEqual(d.flags, before)
        self.assertFalse(t.off(d))

    def test_show_outside_grid_stays_off_grid(self):
        t = World()
        f = t.new(b'far', pos=FAR)
        self.assertTrue(t.off(f))
        H.show_monster(t.w, b'far', t.bytes)
        self.assertTrue(t.off(f))

    def test_show_grid_b_goes_to_grid_b(self):
        t = World()
        g = t.new(b'g', O.FLAG_GRID_B)
        H.hide_monster(t.w, b'g', t.bytes)
        H.show_monster(t.w, b'g', t.bytes)
        self.assertFalse(t.off(g))
        self.assertIs(t.cell_front(g), g)       # front of its grid-B cell (flag 0x800)
        lo, hi = (f32(-100.0), f32(-100.0), f32(-1000.0)), (f32(100.0), f32(100.0), f32(1000.0))
        self.assertNotIn(g, t.w.collect_in_box(lo, hi, 64))

    def test_hidden_object_not_in_box_query(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE)
        lo, hi = (f32(-100.0), f32(-100.0), f32(-1000.0)), (f32(100.0), f32(100.0), f32(1000.0))
        self.assertIn(c, t.w.collect_in_box(lo, hi, 64))
        H.hide_monster(t.w, b'boss', t.bytes)
        self.assertNotIn(c, t.w.collect_in_box(lo, hi, 64))
        H.show_monster(t.w, b'boss', t.bytes)
        self.assertIn(c, t.w.collect_in_box(lo, hi, 64))

    def test_no_seed_draw(self):
        t = World()
        t.new(b'boss', H.FLAG_CREATURE)
        seed = t.w.shared.state
        H.hide_monster(t.w, b'boss', t.bytes)
        H.show_monster(t.w, b'boss', t.bytes)
        self.assertEqual(t.w.shared.state, seed)

    def test_trace_and_needs(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE)
        d = t.new(b'boss')
        trace = []
        H.hide_monster(t.w, b'boss', t.bytes, trace)
        self.assertEqual(sorted(trace), sorted([('obj_moveOffGrid', c.addr), ('obj_moveOffGrid', d.addr)]))
        needs = dict((a, (cr, link)) for a, cr, link in H.needs(t.w, b'boss'))
        self.assertEqual(needs[c.addr], (True, True))
        self.assertEqual(needs[d.addr], (False, True))

    def test_destroyed_object_not_found(self):
        t = World()
        c = t.new(b'boss', H.FLAG_CREATURE)
        t.w.destroy(c, 3)
        self.assertEqual(H.hide_monster(t.w, b'boss', t.bytes), 0)

    def test_deleted_object_still_found(self):
        t = World()
        d = t.new(b'door')
        t.w.delete(d)
        H.hide_monster(t.w, b'door', t.bytes)
        self.assertTrue(t.off(d))
        self.assertEqual(d.flags & H.FLAG_NOT_RUN, H.FLAG_NOT_RUN)


if __name__ == '__main__':
    unittest.main()
