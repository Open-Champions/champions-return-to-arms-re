#!/usr/bin/env python3
"""Unit tests of tools/ref_world.py that need no game file.

They check the model's own logic on small levels built with ref_world.build_world_file;
whether the model matches the game is the business of tools/difftest_world.py.

  python3 -m unittest discover -s tools -p 'test_ref_world.py'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_world as R                           # noqa: E402

F = R.f32


def point(x, y, z=0.0):
    return [F(x), F(y), F(z)]


def room(pillar=None, pieces=()):
    """One 40 x 40 field (samples -20 .. 19, i.e. world -80 .. 76) on an element at the
    origin: floor 0; a wall 40 high from x = 40; a flag-2 line at y = -40; a flag-4 line at
    y = 40; an 11-high ledge from x = -60 down; optionally one pillar sample."""
    samples = []
    for j in range(-20, 20):
        for i in range(-20, 20):
            height, flags = 0, 0
            if i >= 10:
                height = 40
            elif i <= -15:
                height = 11
            elif j == -10:
                flags = 2
            elif j == 10:
                flags = 4
            if pillar and (i, j) == pillar[:2]:
                height, flags = pillar[2], pillar[3]
            samples.append(height * 16 + flags)
    data = R.build_world_file((-1, -1), (2, 2), [(-20, -20, 40, 40, samples)],
                              [(0, 4, 0, 0, 0, 32767, 0)], pieces=pieces)
    return R.Level(data)


def grid_level(width, height, blocked=()):
    """A path grid with every link between open neighbours, origin (0, 0)."""
    dirs = ((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))
    cells = []
    for row in range(height):
        for col in range(width):
            links = 0
            if (col, row) not in blocked:
                for bit, (dx, dy) in enumerate(dirs):
                    c2, r2 = col + dx, row + dy
                    if 0 <= c2 < width and 0 <= r2 < height and (c2, r2) not in blocked:
                        links |= 1 << bit
            cells.append(links)
    data = R.build_world_file((0, 0), (1, 1), [(0, 0, 2, 2, [0, 0, 0, 0])], [(0, 0, 0, 0, 0, 32767, 0)],
                              path=(0, 0, width, height, cells))
    return R.Level(data)


class Arithmetic(unittest.TestCase):
    def tearDown(self):
        R.set_fpu()

    def test_truncation_and_limits(self):
        self.assertEqual(R.fdiv(R.ONE, F(3.0)), 0x3EAAAAAA)          # not ...ab
        self.assertEqual(R.fdiv(R.ONE, R.ZERO), R.FMAX)
        self.assertEqual(R.fdiv(R.MINUS_ONE, R.ZERO), 0xFFFFFFFF)
        self.assertEqual(R.fmul(R.FMAX, F(2.0)), R.FMAX)
        self.assertEqual(R.fadd(F(1.0), F(-1.0)), 0)
        self.assertEqual(R.f2i(F(-2.75)), -2)
        self.assertEqual(R.f2i(R.FMAX), 0x7FFFFFFF)
        self.assertEqual(R.i2f(-1000000), R.NO_FLOOR)
        self.assertTrue(R.flt(F(-0.0), F(1e-30)) and not R.flt(F(-0.0), R.ZERO))

    def test_floor_and_ceil(self):
        for value, low, high in ((2.5, 2.0, 3.0), (-2.5, -3.0, -2.0), (7.0, 7.0, 7.0), (0.25, 0.0, 1.0),
                                 (-0.25, -1.0, -0.0)):
            self.assertEqual(R.floorf(F(value)), F(low))
            self.assertEqual(R.ceilf(F(value)), F(high))

    def test_axis_aligned_cosine_is_not_one(self):
        # 32767 * 0x38000100 truncates to the float just below 1.0; rounding gives 1.0
        self.assertEqual(R.fmul(R.i2f(32767), R.K_INV_32767), 0x3F7FFFFF)
        R.set_fpu('nearest')
        self.assertEqual(R.fmul(R.i2f(32767), R.K_INV_32767), R.ONE)


class Heights(unittest.TestCase):
    def test_floor_wall_and_nothing(self):
        level = room()
        self.assertEqual(R.terrain_height(level, F(12.0), point(0, 0)), F(0.0))
        self.assertEqual(R.terrain_height(level, F(12.0), point(34, 0)), F(40.0))   # disc reaches the wall
        self.assertEqual(R.terrain_height(level, F(12.0), point(20, 0)), F(0.0))
        self.assertEqual(R.terrain_height(level, F(12.0), point(500, 500)), R.NO_FLOOR)
        self.assertEqual(R.terrain_height(level, F(0.0), point(0, 0)), R.NO_FLOOR)   # strict disc test

    def test_height_below_ignores_what_is_more_than_12_up(self):
        level = room()
        self.assertEqual(R.terrain_height_below(level, F(12.0), point(34, 0, 0.0)), F(0.0))
        self.assertEqual(R.terrain_height_below(level, F(12.0), point(34, 0, 28.0)), F(40.0))
        self.assertEqual(R.terrain_height_below(level, F(12.0), point(34, 0, 27.9)), F(0.0))

    def test_height_at_point(self):
        level = room()
        self.assertEqual(R.terrain_height_at_point(level, point(50, 3)), F(40.0))
        self.assertEqual(R.terrain_height_at_point(level, point(3, 3)), F(0.0))
        self.assertEqual(R.terrain_height_at_point(level, point(5000, 3)), F(0.0))   # off the grid: 0, not -1000000

    def test_flag1_test(self):
        level = room(pillar=(3, 3, 0, 1))
        self.assertEqual(R.terrain_test_flag1(level, F(12.0), point(12, 12)), R.ONE)
        self.assertEqual(R.terrain_test_flag1(level, F(12.0), point(-30, 0)), R.ZERO)
        self.assertEqual(R.terrain_test_flag1(level, F(12.0), point(0, -40)), R.ZERO)   # flag 2 is not flag 1

    def test_moving_piece_fixup_and_switch(self):
        level = room(pillar=(0, 0, 5, 1), pieces=(0,))
        self.assertEqual(level.elements[0].hf.hi, 2000)
        self.assertEqual(R.terrain_height(level, F(4.0), point(-1, -1)), F(2000.0))
        level.set_piece_collision(0, 0)
        self.assertEqual(R.terrain_height(level, F(4.0), point(-1, -1)), R.NO_FLOOR)
        level.set_piece_collision(0, 1)
        level.set_piece_height(0, F(-30.9))
        self.assertEqual(level.get_piece_height(0), -30)
        self.assertEqual(R.terrain_height(level, F(4.0), point(-1, -1)), F(1970.0))


class Sweeps(unittest.TestCase):
    def test_free_and_blocked(self):
        level = room()
        t, normal = R.terrain_sweep_circle(level, F(12.0), point(0, 0), point(20, 0), R.MASK_OBJECT)
        self.assertEqual((t, normal), (R.ONE, None))
        t, normal = R.terrain_sweep_circle(level, F(12.0), point(0, 0), point(60, 0), R.MASK_OBJECT)
        self.assertAlmostEqual(R.to_float(t), 7.0 / 15.0, places=5)      # centre stops 3 samples short
        self.assertAlmostEqual(R.to_float(normal[0]), -1.0, places=5)
        self.assertEqual(normal[2], R.ZERO)

    def test_step_rule(self):
        level = room()
        # the ledge is 11 up: walked onto; from 1 lower it is 12 up: a wall
        self.assertEqual(R.terrain_sweep_circle(level, F(12.0), point(-20, 0, 0), point(-40, 0), 1)[0], R.ONE)
        self.assertNotEqual(R.terrain_sweep_circle(level, F(12.0), point(-20, 0, -1), point(-40, 0), 1)[0], R.ONE)

    def test_masks(self):
        level = room()
        down = point(0, -40)
        self.assertEqual(R.terrain_sweep_circle(level, F(12.0), point(0, 0), down, R.MASK_OBJECT)[0], R.ONE)
        self.assertEqual(R.terrain_sweep_circle(level, F(12.0), point(0, 0), down, R.MASK_PLAYER)[0], R.ONE)
        self.assertNotEqual(R.terrain_sweep_circle(level, F(12.0), point(0, 0), down, R.MASK_CREATURE)[0], R.ONE)
        up = point(0, 40)
        self.assertEqual(R.terrain_sweep_circle(level, F(12.0), point(0, 0), up, R.MASK_CREATURE)[0], R.ONE)
        self.assertNotEqual(R.terrain_sweep_circle(level, F(12.0), point(0, 0), up, R.MASK_PLAYER)[0], R.ONE)
        self.assertEqual([R.mover_mask(f) for f in (0, 0x20, 0x40, 0x60)], [1, 3, 5, 5])

    def test_normal_is_taken_a_quarter_of_the_way(self):
        level = room(pillar=(5, 2, 40, 0))               # a lone post at world (20, 8)
        t, normal = R.terrain_sweep_circle(level, F(12.0), point(-20, 0), point(60, 0), 1)
        along = 10.0 - 5.0 ** 0.5                        # samples travelled to contact
        self.assertAlmostEqual(R.to_float(t), along / 15.0, places=5)
        nx, ny = (-20.0 + along) - 20.0, 0.0 - 8.0       # centre advanced by `along` WORLD units
        size = (nx * nx + ny * ny) ** 0.5
        self.assertAlmostEqual(R.to_float(normal[0]), nx / size, places=5)
        self.assertAlmostEqual(R.to_float(normal[1]), ny / size, places=5)

    def test_slide_along_a_wall(self):
        level = room()
        hit, pos, normal = R.world_slide_move(level, F(12.0), point(20, 0), point(30, 20), 1)
        self.assertEqual(hit, 1)
        self.assertLess(R.to_float(pos[0]), 28.1)        # stopped by the wall at x = 40
        self.assertGreater(R.to_float(pos[1]), 15.0)     # but carried along it
        hit, pos, normal = R.world_slide_move(level, F(12.0), point(0, 0), point(10, 5), 1)
        self.assertEqual((hit, normal), (0, None))
        self.assertEqual(pos, point(10, 5))

    def test_ground_step_and_object_move(self):
        level = room()
        pos, vz, landed = R.ground_step(level, F(12.0), point(0, 0, 0.1), R.ZERO)
        self.assertEqual((pos[2], vz, landed), (F(0.0), R.ZERO, 1))
        pos, vz, landed = R.ground_step(level, F(12.0), point(0, 0, 50.0), R.ZERO)
        self.assertEqual(landed, 0)
        self.assertAlmostEqual(R.to_float(pos[2]), 50.0 - 8.999999 / 60.0, places=4)
        pos, vz, bits = R.object_move(level, F(12.0), point(20, 0, 0), point(600, 0, 0), R.ZERO, 0x40)
        self.assertEqual(bits, 1 | 4)
        pos, hit = R.projectile_step(level, F(12.0), point(20, 0, 5), point(1200, 0, 0))
        self.assertEqual(hit, 1)
        self.assertLess(R.to_float(pos[0]), 28.1)


class Rays(unittest.TestCase):
    def test_horizontal_vertical_and_flags(self):
        level = room()
        t = R.terrain_raycast(level, R.ONE, point(0, 0, 5), point(60, 0, 0), 0)
        # the wall begins at sample 10 (x = 40) but the march advances by the element's
        # cosine, 0.99999994, so after ten steps it is still in sample 9: the hit is at 11
        self.assertAlmostEqual(R.to_float(t), 44.0 / 60.0, places=5)
        self.assertEqual(R.terrain_raycast(level, R.ONE, point(0, 0, 5), point(30, 0, 0), 0), R.MINUS_ONE)
        self.assertEqual(R.terrain_raycast(level, R.ONE, point(0, 0, 50), point(60, 0, 0), 0), R.MINUS_ONE)
        self.assertEqual(R.terrain_raycast(level, R.ONE, point(2, 2, 30), point(0, 0, -1), 0), F(30.0))
        self.assertEqual(R.terrain_raycast(level, R.ONE, point(2, 2, 30), point(0, 0, 1), 0), R.MINUS_ONE)
        down = point(0, -60, 0)
        self.assertEqual(R.terrain_raycast(level, R.ONE, point(0, 0, 5), down, 0), R.MINUS_ONE)
        self.assertNotEqual(R.terrain_raycast(level, R.ONE, point(0, 0, 5), down, 3), R.MINUS_ONE)

    def test_world_raycast_objects(self):
        level = room()
        post = R.Circle(0, F(20.0), F(0.0), F(4.0))
        ghost = R.Circle(1, F(10.0), F(0.0), F(4.0))
        things = lambda lo, hi: [ghost, post]            # noqa: E731
        t, hit = R.world_raycast(level, R.ONE, point(0, 0, 5), point(60, 0, 0), 0, things)
        self.assertIs(hit, post)
        self.assertAlmostEqual(R.to_float(t), 16.0 / 60.0, places=5)
        t, hit = R.world_raycast(level, R.ONE, point(0, 0, 5), point(60, 0, 0), 0, things, ignore=post)
        self.assertIsNone(hit)
        self.assertEqual(R.world_raycast(level, R.ONE, point(2, 2, 30), point(0, 0, -1), 0)[0], R.MINUS_ONE)


class Paths(unittest.TestCase):
    def run_one(self, level, start, goal, kind=0, radius=0.0, capacity=16, finder=None):
        finder = finder or R.PathFinder(level)
        log = []
        entry = finder.request(kind, F(radius), point(*start), point(*goal), log.append, capacity)
        finder.service(True)
        return entry, log, finder

    def test_straight_path_and_format(self):
        level = grid_level(12, 6)
        entry, log, finder = self.run_one(level, (24, 48), (192, 48))
        self.assertEqual(log, [1])
        self.assertEqual(entry.path[0], (24, 48))        # the start node comes first
        self.assertEqual(entry.path[-1], (-1, -1))
        self.assertEqual(entry.path[-2], (192, 48))      # (168, 48) is 24 away: not strictly inside 24
        self.assertEqual(len(entry.path), 9)
        # the first step lands in ring 3, each straight continuation two rings on: the goal
        # node is entered while round 13 is worked, and the round counter is then 14
        self.assertEqual(finder.round, 14)

    def test_capacity_and_radius_floor(self):
        level = grid_level(12, 6)
        entry, _log, _f = self.run_one(level, (24, 48), (192, 48), capacity=4)
        self.assertEqual(entry.path, [(24, 48), (48, 48), (72, 48), (-1, -1)])
        self.assertEqual(entry.radius, R.K_24)           # type 0 raises the radius to 24
        entry, _log, _f = self.run_one(level, (24, 48), (192, 48), kind=2, radius=5.0)
        self.assertEqual(entry.radius, F(5.0))

    def test_detour_and_failure(self):
        wall = {(5, r) for r in range(0, 5)}
        level = grid_level(12, 6, wall)
        entry, log, _f = self.run_one(level, (24, 24), (216, 24))
        self.assertEqual(log, [1])
        self.assertIn((120, 120), entry.path)            # through the gap in the last row
        closed = grid_level(12, 6, {(5, r) for r in range(0, 6)})
        entry, log, _f = self.run_one(closed, (24, 24), (216, 24))
        self.assertEqual((log, entry.path), ([0], [(-1, -1)]))

    def test_eighty_rounds(self):
        level = grid_level(60, 3)
        entry, log, finder = self.run_one(level, (0, 24), (59 * 24, 24))
        self.assertEqual(log, [0])                       # 58 nodes away: more than 80 rounds allow
        self.assertEqual(finder.iterations, 85)          # 80 counted rounds, then five empty ones

    def test_block_counter_and_marks_cleared(self):
        level = grid_level(12, 6)
        R.path_block_nodes(level, F(0.0), point(120, 48))
        self.assertTrue(level.path_cells[2 * 12 + 5] >> 16)
        entry, log, finder = self.run_one(level, (24, 48), (216, 48))
        self.assertEqual(log, [1])
        self.assertNotIn((120, 48), entry.path)
        R.path_unblock_nodes(level, F(0.0), point(120, 48))
        self.assertFalse(any(cell >> 16 for cell in level.path_cells))
        self.run_one(level, (48, 48), (216, 48), finder=finder)          # clears the first search's marks
        marked = [i for i, cell in enumerate(level.path_cells) if cell & 0xFF00]
        entry2, _log, finder2 = self.run_one(grid_level(12, 6), (48, 48), (216, 48))
        fresh = [i for i, cell in enumerate(finder2.level.path_cells) if cell & 0xFF00]
        self.assertEqual(marked, fresh)

    def test_suspended_search_equals_blocking(self):
        wall = {(5, r) for r in range(0, 5)}
        blocking, _log, _f = self.run_one(grid_level(12, 6, wall), (24, 24), (216, 24))
        level = grid_level(12, 6, wall)
        finder = R.PathFinder(level)
        log = []
        entry = finder.request(0, F(0.0), point(24, 24), point(216, 24), log.append)
        calls = 0
        while not log:
            ticks = iter([0, 0, 7600, 9500])             # start, one round, suspend, leave
            finder.service(False, lambda: next(ticks))
            calls += 1
        self.assertGreater(calls, 5)
        self.assertEqual((log, entry.path), ([1], blocking.path))

    def test_queue_full_and_dead_requester(self):
        level = grid_level(12, 6)
        finder = R.PathFinder(level)
        log = []
        entries = [finder.request(0, F(0.0), point(24, 48), point(96, 48), log.append) for _ in range(130)]
        self.assertEqual(sum(e is None for e in entries), 3)             # 127 fit
        self.assertEqual(log, [0, 0, 0])
        entries[0].requester = None
        finder.service(True)
        self.assertEqual(log.count(1), 126)
        self.assertIsNone(entries[0].result)

    def test_goal_types_two_and_three_accept_outside_the_radius(self):
        level = grid_level(12, 6)
        entry, log, _f = self.run_one(level, (24, 48), (216, 48), kind=2, radius=50.0)
        self.assertEqual(log, [1])
        self.assertEqual(len(entry.path), 3)             # the first neighbour is already "far enough"


if __name__ == '__main__':
    unittest.main()
