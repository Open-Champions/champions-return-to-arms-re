#!/usr/bin/env python3
"""test_ref_objects.py - checks of tools/ref_objects.py that need no game files.

These pin the model's own logic (the ordering rules of docs/spec/object-system.md).  That
the model matches the game is the job of tools/difftest_objects.py, which needs the
executable.

    python3 -m unittest discover -s tools -p 'test_ref_objects.py'
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as R                            # noqa: E402
import ref_objects as O                         # noqa: E402
from ref_objects import f32                     # noqa: E402

ORIGIN = [0, 0, 0]


def at(x, y, z=0.0):
    return [f32(x), f32(y), f32(z)]


def box(x0, y0, x1, y1, z0=-1.0, z1=1.0):
    return at(x0, y0, z0), at(x1, y1, z1)


class Recorder:
    """A world whose virtual run calls are recorded and may run a script."""

    def __init__(self):
        self.world = O.World()
        self.world.init()
        self.ran = []
        self.script = {}
        self.world.on_run = self.run

    def run(self, obj):
        self.ran.append(obj)
        action = self.script.pop(obj.addr, None)
        if action:
            action(obj)

    def tick(self):
        self.ran = []
        self.world.run_objects()
        return self.ran

    def new(self, pos=ORIGIN, then='frame', flags=0):
        w = self.world
        obj = w.new_object(0x4C, pos)
        if flags:
            obj.flags |= flags
            w.update_grid_cell(obj)
        if then == 'frame':
            w.run_every_frame(obj)
        elif then == 'r60':
            w.run_every_60(obj)
        elif then == 'r15':
            w.run_every_15(obj)
        return obj


class Creation(unittest.TestCase):
    def test_fields_and_seed(self):
        w = O.World()
        w.init()
        obj = w.new_object(0x4C, at(100.5, -300.25, 7.0))
        self.assertEqual(obj.addr, R.Pool.BASE)
        self.assertEqual((obj.radius, obj.height, obj.flags), (O.F_24, O.F_72, 0))
        self.assertEqual((obj.draw_half_width, obj.draw_height), (25, 73))
        self.assertEqual(w.shared.state, 0x3C6EF35F)        # one step of the generator from 0
        self.assertEqual(obj.seed, 0x3C6E)                  # the 16-bit draw
        row, col = O.cell_coord(obj.pos[1]), O.cell_coord(obj.pos[0])
        self.assertEqual((col, row), (60, 58))
        self.assertIs(w.grid[row * 120 + col].next.obj, obj)
        self.assertIsNone(obj.heads[1].next)                # on no run list

    def test_refused_allocation_draws_nothing(self):
        w = O.World()
        while w.pool.new(3000):
            pass
        while w.pool.new(0x500):
            pass
        while w.pool.new(0x180):
            pass
        seed = w.shared.state
        self.assertIsNone(w.new_object(0x4C, ORIGIN))
        self.assertEqual(w.shared.state, seed)

    def test_cell_boundary_is_at_minus_one(self):
        self.assertEqual([O.cell_coord(f32(v)) for v in (0.0, -0.5, -0.99, -1.0, 255.9, 256.0, -256.9, -257.0)],
                         [60, 60, 60, 59, 60, 61, 59, 58])

    def test_outside_goes_off_grid(self):
        w = O.World()
        for pos in (at(15360.0, 0.0), at(0.0, -15361.0), at(1e20, 0.0)):
            self.assertTrue(w.is_off_grid(w.new_object(0x4C, pos)))
        self.assertFalse(w.is_off_grid(w.new_object(0x4C, at(15359.9, -15360.9))))

    def test_hide_is_read_before_the_property_list_is_stored(self):
        w = O.World()
        self.assertFalse(w.is_off_grid(w.new_object(0x4C, ORIGIN, None, [b'hide=1'])))
        addr = w.pool.new(0x4C)
        self.assertTrue(w.is_off_grid(w.construct(addr, ORIGIN, None, None, stale_props=[b'hide=1'])))

    def test_class_definition_resolved_once_per_generation(self):
        w = O.World()
        calls = []
        w.res_find = lambda lump, name: calls.append((lump, name)) or len(calls)
        definition = O.ClassDef('lump', ['a', 'b'], generation=0)
        w.new_object(0x4C, ORIGIN, definition)
        w.new_object(0x4C, ORIGIN, definition)
        self.assertEqual(calls, [('lump', 'a'), ('lump', 'b')])
        self.assertEqual(definition.entries, [['a', 1], ['b', 2]])
        w.lump_generation += 1
        w.new_object(0x4C, ORIGIN, definition)
        self.assertEqual(len(calls), 4)


class RunOrder(unittest.TestCase):
    def test_last_linked_runs_first_then_slow_lists(self):
        r = Recorder()
        a, b, c = r.new(), r.new(), r.new()
        r.world.frame = 61
        s60, s15 = r.new(then='r60'), r.new(then='r15')     # cursors step first: lists 1 and 1
        self.assertEqual(r.tick(), [c, b, a, s15, s60])
        r.world.frame = 62
        self.assertEqual(r.tick(), [c, b, a])

    def test_new_every_frame_object_waits_a_tick(self):
        r = Recorder()
        a, b = r.new(), r.new()
        made = []
        r.script[b.addr] = lambda obj: made.append(r.new())
        self.assertEqual(r.tick(), [b, a])
        self.assertEqual(r.tick(), [made[0], b, a])

    def test_new_slow_object_can_run_in_the_tick_of_its_creation(self):
        r = Recorder()
        a = r.new()
        r.world.frame = 60 * 5 + r.world.cursor60 + 1
        made = []
        r.script[a.addr] = lambda obj: made.append(r.new(then='r60'))
        self.assertEqual(r.tick(), [a, made[0]])

    def test_falling_asleep_can_run_twice_in_one_tick(self):
        r = Recorder()
        a = r.new()
        w = r.world
        w.cull_by_camera, w.centres = 0, []
        w.frame = 60 * 3 + w.cursor60 + 1
        r.script[a.addr] = lambda obj: w.update_active(obj, 1, 480)
        self.assertEqual(r.tick(), [a, a])

    def test_relink_moves_to_the_front(self):
        r = Recorder()
        a, b = r.new(), r.new()
        r.world.run_every_frame(a)
        self.assertEqual(r.tick(), [a, b])

    def test_flag_and_mask(self):
        r = Recorder()
        a, b = r.new(), r.new()
        a.flags |= O.FLAG_NOT_RUN
        self.assertEqual(r.tick(), [b])
        a.flags = O.FLAG_PREDICTION_COPY
        r.world.exclude_mask = O.FLAG_PREDICTION_COPY
        self.assertEqual(r.tick(), [b])
        r.world.exclude_mask = 0
        self.assertEqual(r.tick(), [b, a])

    def test_frozen_runs_nothing_but_still_flushes(self):
        r = Recorder()
        a, b = r.new(), r.new()
        r.world.is_frozen = lambda: True
        r.world.delete(a)
        self.assertEqual(r.tick(), [])
        self.assertNotIn(a.addr, r.world.objects)
        self.assertIn(b.addr, r.world.objects)

    def test_destroying_the_next_object_skips_it(self):
        r = Recorder()
        a, b, c = r.new(), r.new(), r.new()
        r.script[c.addr] = lambda obj: r.world.destroy(b)
        self.assertEqual(r.tick(), [c, a])
        r.script[c.addr] = lambda obj: r.world.destroy(obj)     # itself
        self.assertEqual(r.tick(), [c, a])
        self.assertEqual(r.tick(), [a])


class Deletion(unittest.TestCase):
    def test_deferred_delete(self):
        r = Recorder()
        w = r.world
        a, b = r.new(), r.new()
        w.delete(a)
        self.assertEqual(w.collect_in_box(*box(-5, -5, 5, 5), 16), [b, a])     # still in the grid
        self.assertEqual(r.tick(), [b])
        self.assertNotIn(a.addr, w.objects)
        self.assertEqual(w.collect_in_box(*box(-5, -5, 5, 5), 16), [b])
        self.assertEqual(w.new_object(0x4C, ORIGIN).addr, a.addr)              # the block is reused first

    def test_delete_from_a_destructor_waits_for_the_next_flush(self):
        r = Recorder()
        w = r.world
        a, b = r.new(), r.new()

        def destroy(obj, flags):
            if obj is a:
                w.delete(b)
            w.destroy(obj, flags)
        w.on_destroy = destroy
        w.delete(a)
        w.flush_delete_list()
        self.assertIn(b.addr, w.objects)
        w.flush_delete_list()
        self.assertNotIn(b.addr, w.objects)

    def test_handles_are_cleared(self):
        w = O.World()
        obj = w.new_object(0x4C, ORIGIN)
        handle = R.Cell('handle')
        w.handles.link(handle, obj.heads[0], obj)
        self.assertIs(handle.next.obj, obj)
        w.destroy(obj)
        self.assertIsNone(handle.next)

    def test_teardown(self):
        r = Recorder()
        w = r.world
        order = []
        w.on_destroy = lambda obj, flags: (order.append(obj), w.destroy(obj, flags))
        far = r.new(at(1e9, 0.0))
        b = r.new(at(300.0, 0.0), flags=O.FLAG_GRID_B)
        a2 = r.new(at(-300.0, 300.0))
        a1 = r.new(at(300.0, 0.0), then='r60')
        w.delete_all_objects()
        self.assertEqual(order, [a1, a2, b, far])           # grid A by row then column, grid B, off-grid
        self.assertEqual((w.objects, w.pool.count_free(), w.cursor60), ({}, 1056, 0))


class Queries(unittest.TestCase):
    def setUp(self):
        self.r = Recorder()
        r = self.r
        self.p = [r.new(at(x, y), then='none') for x, y in
                  ((1300, 1300), (1010, 1300), (1300, 1010), (1010, 1010), (1011, 1011))]
        self.area = box(1005, 1005, 1305, 1305)

    def test_order_rows_columns_newest_first(self):
        p, w = self.p, self.r.world
        self.assertEqual(w.collect_in_box(*self.area, 256), [p[4], p[3], p[2], p[1], p[0]])
        w.update_grid_cell(p[3])                            # a move call, even without moving
        self.assertEqual(w.collect_in_box(*self.area, 256), [p[3], p[4], p[2], p[1], p[0]])

    def test_limit_keeps_the_first_in_walk_order(self):
        p, w = self.p, self.r.world
        self.assertEqual(w.collect_in_box(*self.area, 3), [p[4], p[3]])
        self.assertEqual(w.collect_in_box(*self.area, 1), [])
        self.assertEqual(w.collect_in_box(*self.area, 0), [])

    def test_who_is_never_returned(self):
        p, w = self.p, self.r.world
        p[4].flags = O.FLAG_PREDICTION_COPY
        p[3].flags = O.FLAG_OWN_PLAYER
        p[2].flags = O.FLAG_GRID_B
        w.update_grid_cell(p[2])
        w.move_off_grid(p[1])
        self.assertEqual(w.collect_in_box(*self.area, 256), [p[3], p[0]])
        w.exclude_mask = O.FLAG_OWN_PLAYER
        self.assertEqual(w.collect_in_box(*self.area, 256), [p[0]])

    def test_extent_tests(self):
        p, w = self.p, self.r.world
        lo, hi = box(1035, 1005, 1100, 1020)                # 1034.x is the reach of radius 24 from 1010/1011
        self.assertEqual(w.collect_in_box(lo, hi, 256), [p[4]])
        lo, hi = box(1005, 1005, 1020, 1020, -200.0, -72.5)   # the object stands on z .. z + 72
        self.assertEqual(w.collect_in_box(lo, hi, 256), [])
        lo, hi = box(1005, 1005, 1020, 1020, 71.0, 500.0)
        self.assertEqual(w.collect_in_box(lo, hi, 256), [p[4], p[3]])

    def test_huge_box_wraps_to_nothing(self):
        w = self.r.world
        lo, hi = at(1005, 1005, -1), at(1305, 1e12, 1)
        self.assertEqual(w.collect_in_box(lo, hi, 256), [])

    def test_sphere_list_is_reversed(self):
        p, w = self.p, self.r.world
        head = R.Cell('result')
        added = w.collect_in_sphere(f32(600.0), at(1150, 1150), head)
        self.assertEqual(added, [p[4], p[3], p[2], p[1], p[0]])
        self.assertEqual(R.HandlePool.items(head), [p[0], p[1], p[2], p[3], p[4]])

    def test_find_by_class_needs_a_run_list(self):
        r = self.r
        a = r.new()
        self.assertEqual(r.world.find_by_class(b'10GameObject', 50), [a])


class Names(unittest.TestCase):
    def test_quotes_are_stripped_in_the_record(self):
        w = O.World()
        props = [b'name="Gate Guard" extra', b'speed=3']
        obj = w.new_object(0x4C, ORIGIN, None, props)
        self.assertEqual(props[0], b'name=Gate Guard')
        self.assertEqual(w.names.find(b'gate guard', 4), [obj])
        w.destroy(obj)
        self.assertEqual(w.names.find(b'Gate Guard', 4), [])

    def test_same_name_in_registration_order_and_slot_reuse(self):
        w = O.World()
        k = [w.new_object(0x4C, ORIGIN, None, [b'name=knight']) for _ in range(4)]
        self.assertEqual(w.names.find(b'KNIGHT', 16), k)
        self.assertEqual(w.names.find(b'knight', 3), k[:2])
        self.assertIs(w.names.find_first(b'knight'), k[0])
        w.destroy(k[1])
        fresh = w.new_object(0x4C, ORIGIN, None, [b'name=Knight'])
        self.assertEqual(w.names.find(b'knight', 16), [k[0], fresh, k[2], k[3]])

    def test_hash(self):
        self.assertEqual(O.name_hash(b''), 0)
        self.assertEqual(O.name_hash(b'Door'), O.name_hash(b'dOOR'))
        self.assertTrue(all(0 <= O.name_hash(b'n%d' % i) < 512 for i in range(200)))

    def test_properties(self):
        props = [b'names=x', b'name', b'name=', b'Hide=1', b'hide=7', b'hide=9']
        self.assertEqual(O.props_find(props, b'name'), b'')
        self.assertEqual(O.props_int(props, b'HIDE'), 7)    # the key is lower-cased, the list is not
        self.assertEqual(O.props_int(props, b'hide', 1), 9)
        self.assertEqual(O.props_int(props, b'hide', 2), 0)
        self.assertEqual(O.props_int(None, b'hide'), 0)


class Activity(unittest.TestCase):
    def test_lists_follow_the_answer(self):
        w = O.World()
        obj = w.new_object(0x4C, at(100.0, 0.0))
        w.cull_by_camera, w.centres = 0, [at(0.0, 0.0)]
        self.assertEqual(w.update_active(obj, 0, 480), 1)
        self.assertIs(w.run_active.next.obj, obj)
        self.assertEqual(w.update_active(obj, 1, 480), 1)
        self.assertEqual(w.update_active(obj, 1, 50), 0)
        self.assertIs(w.run60[1].next.obj, obj)
        self.assertEqual(w.update_active(obj, 0, 50), 0)
        obj.flags |= O.FLAG_FAR_ACTIVE
        self.assertEqual(w.update_active(obj, 0, 50), 1)

    def test_camera_and_overflow(self):
        w = O.World()
        obj = w.new_object(0x4C, at(100.0, 0.0))
        w.centres = [at(100.0, 0.0)]
        w.camera_focus = at(9000.0, 0.0)
        self.assertEqual(w.is_active(obj, 480), 0)          # cull_by_camera starts as 1
        w.cull_by_camera = 0
        self.assertEqual(w.is_active(obj, 480), 1)
        self.assertEqual(w.is_active(obj, 46340), 1)
        self.assertEqual(w.is_active(obj, 46341), 0)        # the square no longer fits 32 bits

    def test_set_object_vis(self):
        w = O.World()
        a, b = w.new_object(0x4C, at(1.0, 2.0)), w.new_object(0x4C, at(3.0, 4.0))
        w.network_mode = 1
        w.set_object_vis(None, 0, 0, [a, None, b])
        self.assertEqual((w.cull_by_camera, w.centres), (0, [a.pos, b.pos]))
        w.set_object_vis(None, 0, 1, [a])
        self.assertEqual(w.cull_by_camera, 1)
        w.set_object_vis(None, 1, 1, [a])
        self.assertEqual(w.cull_by_camera, 0)
        w.set_object_vis(b, 0, 1, [a])
        self.assertEqual((w.cull_by_camera, w.centres), (0, [b.pos]))

    def test_near_view_is_a_square(self):
        w = O.World()
        w.cull_by_camera = 0
        player = w.new_object(0x4C, at(0.0, 0.0, 0.0))
        self.assertEqual(w.is_near_view(at(480.0, -480.0, 9999.0), f32(480.0), [None, player]), 1)
        self.assertEqual(w.is_near_view(at(480.5, 0.0), f32(480.0), [player]), 0)


class Reaper(unittest.TestCase):
    def test_cells(self):
        w = O.World()
        w.frame = 0
        self.assertEqual(w.reap_cells(), list(range(1, 17)))
        w.frame = 7
        self.assertEqual(w.reap_cells()[0], 113)
        self.assertEqual(w.reap_cells()[7:9], [120, 121])   # column 119, then the next row
        w.frame = 899
        self.assertEqual(w.reap_cells()[-2:], [14399, 0])

    def test_first_expendable_per_cell(self):
        r = Recorder()
        w = r.world
        keep = r.new(at(-10900.0, -15360.0), then='none', flags=O.FLAG_GRID_B)
        old = r.new(at(-10900.0, -15360.0), then='none', flags=O.FLAG_GRID_B | O.FLAG_EXPENDABLE)
        new = r.new(at(-10900.0, -15360.0), then='none', flags=O.FLAG_GRID_B | O.FLAG_EXPENDABLE)
        in_a = r.new(at(-10900.0, -15360.0), then='none', flags=O.FLAG_EXPENDABLE)
        w.frame, w.pool_free_count, w.network_mode = 1, 250, 1      # not a sampling frame
        self.assertEqual(O.cell_coord(keep.pos[0]), 17)     # frame 1 looks at cells 17..32
        w.run_objects()
        self.assertEqual(sorted(w.objects), sorted(o.addr for o in (keep, old, in_a)))
        del new
        w.network_mode = 0
        w.camera_focus = list(old.pos)
        w.frame = 900 + 1
        w.run_objects()
        self.assertIn(old.addr, w.objects)                  # offline, 200 or more free: spared near the camera
        w.pool_free_count = 199
        w.run_objects()
        self.assertNotIn(old.addr, w.objects)


class Tasks(unittest.TestCase):
    def test_order_and_cursor(self):
        t = O.TaskList()
        for fn, priority in (('c', 10), ('a', 0), ('d', 10), ('b', 0), ('e', 1000)):
            t.add(fn, priority, fn.encode(), 0)
        t.add('draw', 5, b'draw', 1)
        self.assertEqual([task.fn for task in t.tasks], ['a', 'b', 'draw', 'c', 'd', 'e'])
        called = []

        def invoke(fn):
            called.append(fn)
            if fn == 'a':
                t.add('late', 20, b'late', 0)               # behind the cursor: this pass
                t.add('early', -5, b'early', 0)             # at the cursor or before it: next pass
            if fn == 'b':
                t.remove('b')                               # itself: the cursor steps back ...
                t.add('slot', 0, b'slot', 0)                # ... so what takes its place is called now
            if fn == 'c':
                t.remove('d')
        t.call(1, -1, invoke)
        self.assertEqual(called, ['a', 'b', 'slot', 'c', 'late', 'e'])
        self.assertEqual([task.fn for task in t.tasks], ['early', 'a', 'slot', 'draw', 'c', 'late', 'e'])
        called[:] = []
        t.call(0, 1, invoke)
        self.assertEqual(called, ['draw'])
        self.assertTrue(t.is_running(b'early'))
        self.assertFalse(t.is_running(b'Early'))
        self.assertIsNone(t.add('c', 99, b'again', 0))      # a function is registered once

    def test_tick(self):
        w = O.World()
        w.init()
        seen = []
        w.tasks.add('probe', 11, b'probe', 0)
        w.end_of_tick = lambda: seen.append('end')
        w.pads[0].pressed = 0x40
        w.tasks_run(2, lambda fn: seen.append((fn, w.frame, w.pads[0].pressed)) if fn == 'probe' else w.run_objects())
        self.assertEqual(seen, [('probe', 0, 0x40), 'end', ('probe', 1, 0), 'end'])
        self.assertEqual((w.frame, w.pads[0].pressed), (2, 0x40))
        w.network_mode = 1
        w.tasks_run(1, lambda fn: None)
        self.assertEqual(w.frame, 2)                        # the net loop owns the frame number


class Load(unittest.TestCase):
    def test_records_in_file_order(self):
        w = O.World()
        w.init()
        records = [O.Record(b'Skeleton', 0x4000, at(10 * i, 0.0), [b'name=s%d' % i]) for i in range(4)]
        blob = O.RecordBlob(records)
        data = blob.build()
        self.assertEqual((data[:2], blob.size % 8, data[blob.size:blob.size + 1]), (b'\x04\x00', 0, b'\0'))

        def factory(class_name, pos, angle, props):
            obj = w.new_object(0x4C, pos, None, props)
            w.run_every_60(obj)
            return obj
        self.assertEqual(w.load_records(blob, factory), blob.size)
        made = sorted(w.objects.values(), key=lambda o: o.addr)
        self.assertEqual([o.class_name for o in made], [b'Skeleton'] * 4)
        self.assertEqual([w.names.find_first(b's%d' % i) for i in range(4)], made)
        self.assertEqual(w.collect_in_box(*box(-50, -50, 100, 50), 64), made[::-1])   # newest first in the cell
        self.assertEqual([w.run60[i + 1].next.obj for i in range(4)], made)
        skipped = O.RecordBlob(records)
        w.load_records(skipped, factory, filter_only=True)                              # no filter installed
        self.assertEqual(len(w.objects), 4)

    def test_free_spot_and_marker(self):
        w = O.World()
        w.init()
        flat = (lambda radius, pos: 0, lambda radius, pos: pos[2])
        spot, ok = w.find_free_spot(at(100.0, 100.0, 5.0), 36, 24, 0, *flat)
        self.assertEqual(ok, 1)
        self.assertLessEqual(abs(R.to_float(spot[0]) - 100.0), 36.0)
        self.assertEqual(spot[2], f32(5.0))
        spot, ok = w.find_free_spot(at(0.0, 0.0), 36, 24, 0, lambda radius, pos: R.ONE, flat[1])
        self.assertEqual((spot, ok), (at(0.0, 0.0), 0))
        seed = w.shared.state
        marker = w.player1_marker(w.pool.new(0x4C), at(50.0, 50.0), 0x1000, [], b'town', b'', 0, *flat)
        self.assertEqual((marker.flags, w.start_rank), (3, 1))
        self.assertNotEqual(w.shared.state, seed)
        slots = [list(p) for p in w.spawn_pos]
        w.player1_marker(w.pool.new(0x4C), at(900.0, 900.0), 0, [], b'town', b'', 0, *flat)
        self.assertEqual([list(p) for p in w.spawn_pos], slots)             # rank 1 is kept without 'default'
        w.player1_marker(w.pool.new(0x4C), at(900.0, 900.0), 0, [b'from=town'], b'town', b'', 0, *flat)
        self.assertEqual(w.start_rank, 2)
        self.assertNotEqual([list(p) for p in w.spawn_pos], slots)


if __name__ == '__main__':
    unittest.main()
