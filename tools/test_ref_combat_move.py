#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_move.py that need no game files (they run in CI).

Every fixture is synthetic: records placed by hand in a sparse memory, call-outs answered
by the test.  The tests pin what docs/spec/combat-movement.md states about the bodies
(touch order and the prediction-copy guard, push-out, stand-on, landing, the inline grid
relink, the walk along the facing, the modes, the swing window, the water draw, the screen
clamp, the root-motion rotation) and that the composed runtime walks a player.  Whether
the bodies match the game is the business of tools/difftest_combat_move.py."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_move as MV                    # noqa: E402

f32 = T.f32
M32 = 0xFFFFFFFF


def fl(bits):
    return struct.unpack('<f', struct.pack('<I', bits & M32))[0]


class Answers:
    """Call-outs answered from a dict of name -> function; the rest by the default shape."""

    def __init__(self, **answers):
        self.answers = answers
        self.log = []

    def get(self, name):
        fn = self.answers.get(name)
        if fn is None and name.startswith('Creature.v'):
            fn = lambda *args: 0                                      # noqa: E731
        if fn is None:
            return None

        def wrapped(*args):
            self.log.append((name, args))
            return fn(*args)
        return wrapped


TABLE = 0x00200000


def world(n=3, spacing=10.0, radius=8.0, flags=0x20):
    """`n` objects on a line along x, `spacing` apart, sharing one table, each with a grid
    node in its cell."""
    mem = RC.Memory()
    mem.poke(T.G_WORLD, 4, 0x00000F00)
    objs = []
    for i in range(n):
        o = 0x00100000 + 0x1000 * i
        mem.poke(o + 0xC, 4, flags)
        mem.poke(o + 0x10, 4, f32(spacing * i))
        mem.poke(o + 0x1C, 4, f32(radius))
        mem.poke(o + 0x20, 4, f32(72.0))
        mem.poke(o + 0x48, 4, TABLE)
        back, node = 0x00300000 + 0x40 * i, 0x00300020 + 0x40 * i
        mem.poke(o + 8, 4, back)
        mem.poke(back + 8, 4, node)
        objs.append(o)
    for slot in range(48):
        mem.poke(TABLE + 8 * slot + 4, 4, 0x00F00000 + 16 * slot)        # not a base body
    model = MV.MoveModel(mem)
    for o in objs:
        cell = model.grid_cell(o)
        first = mem.load(cell, 4)
        node = mem.load(mem.load(o + 8, 4) + 8, 4)
        mem.poke(node + 4, 4, cell)
        mem.poke(node, 4, first)
        mem.poke(cell, 4, node)
        if first:
            mem.poke(first + 4, 4, node)
    return mem, objs


def standard(found, ground=0, slide_hits=0):
    return dict(
        world_collectObjectsInBox=lambda lo, hi, limit: list(found),
        world_slideMove=lambda pos, d, mask, normal, r: slide_hits,
        terrain_heightBelow=lambda w, pos, r: ground,
    )


def touches(answers):
    return [(args[0], args[1]) for name, args in answers.log if name == 'Creature.v6']


class MoveWithCollision(unittest.TestCase):
    def test_touch_order_is_the_other_then_the_mover_in_list_order(self):
        mem, (a, b, c) = world(3, spacing=5.0)
        ans = Answers(**standard([c, a, b]))
        model = MV.MoveModel(mem, ans)
        model.move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(touches(ans), [(c, a), (a, c), (b, a), (a, b)])

    def test_the_prediction_copy_touches_nobody_but_itself(self):
        mem, (a, b, _c) = world(3)
        mem.poke(a + 0xC, 4, 0x60 | T.F_PREDICTION_COPY)
        ans = Answers(**standard([b]))
        MV.MoveModel(mem, ans).move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(touches(ans), [(a, b)])

    def test_push_out_sets_bit_2_and_relinks_the_grid(self):
        mem, (a, b, _c) = world(3)
        ans = Answers(**standard([b]))
        model = MV.MoveModel(mem, ans)
        bits = model.move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(bits & 2, 2)
        slides = [args for name, args in ans.log if name == 'world_slideMove']
        self.assertEqual(len(slides), 1)
        self.assertEqual(slides[0][2], 1)                               # mask 1 for a push-out
        node = mem.load(mem.load(a + 8, 4) + 8, 4)
        self.assertEqual(mem.load(model.grid_cell(a), 4), node)          # at the front of its cell

    def test_a_ghost_like_object_is_touched_without_a_push(self):
        mem, (a, b, _c) = world(3)
        mem.poke(b + 0xC, 4, 0x220)
        ans = Answers(**standard([b]))
        bits = MV.MoveModel(mem, ans).move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(bits & 2, 0)
        self.assertEqual(touches(ans), [(b, a), (a, b)])

    def test_standing_on_a_low_object_is_not_a_touch(self):
        mem, (a, b, _c) = world(3)
        mem.poke(b + 0xC, 4, 0x30)
        mem.poke(b + 0x18, 4, f32(-70.0))                                # top at +2, within 5 of a.z
        mem.poke(a + 0x30, 4, f32(-100.0))
        ans = Answers(**standard([b], ground=f32(-500.0)))
        bits = MV.MoveModel(mem, ans).move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(touches(ans), [])
        self.assertEqual(mem.load(a + 0x18, 4), f32(2.0))                # landed on its top
        self.assertEqual(bits & 4, 4)

    def test_skip_flag_1_ignore_and_creatures(self):
        mem, (a, b, c) = world(3, spacing=5.0)
        mem.poke(b + 0xC, 4, 0x21)
        ans = Answers(**standard([b, c]))
        MV.MoveModel(mem, ans).move_with_collision(a, (0, 0, 0), c, 0)
        self.assertEqual(touches(ans), [])
        ans = Answers(**standard([c]))
        MV.MoveModel(mem, ans).move_with_collision(a, (0, 0, 0), 0, 1)
        self.assertEqual(touches(ans), [])

    def test_gravity_and_landing(self):
        mem, (a,) = world(1)
        mem.poke(a + 0x18, 4, f32(10.0))
        ans = Answers(**standard([]))
        model = MV.MoveModel(mem, ans)
        bits = model.move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertEqual(bits, 0)
        self.assertEqual(mem.load(a + 0x30, 4), C.sub(0, 0x410FFFFF))   # vz -= 8.999999
        for _ in range(200):
            bits = model.move_with_collision(a, (0, 0, 0), 0, 0)
            if bits & 4:
                break
        self.assertEqual(bits & 4, 4)
        self.assertEqual(mem.load(a + 0x18, 4), 0)
        self.assertEqual(mem.load(a + 0x30, 4), 0)

    def test_a_tiny_velocity_is_no_slide(self):
        mem, (a,) = world(1)
        ans = Answers(**standard([]))
        MV.MoveModel(mem, ans).move_with_collision(a, (f32(1.0), 0, 0), 0, 0)
        self.assertFalse([n for n, _a in ans.log if n == 'world_slideMove'])
        ans = Answers(**standard([]))
        MV.MoveModel(mem, ans).move_with_collision(a, (f32(60.0), 0, 0), 0, 0)
        self.assertEqual([args[2] for n, args in ans.log if n == 'world_slideMove'], [3])   # creature mask

    def test_grid_cell_rules(self):
        mem, (a,) = world(1)
        model = MV.MoveModel(mem)
        self.assertEqual(model.grid_cell(a), MV.GRID_A + (60 * 120 + 60) * 4)
        mem.poke(a + 0xC, 4, 0x820)
        self.assertEqual(model.grid_cell(a), MV.GRID_B + (60 * 120 + 60) * 4)
        mem.poke(a + 0x10, 4, f32(15400.0))
        self.assertEqual(model.grid_cell(a), MV.GRID_OFF)
        mem.poke(a + 0x10, 4, f32(-15361.0))
        self.assertEqual(model.grid_cell(a), MV.GRID_OFF)

    def test_service_relink_when_not_inline(self):
        mem, (a, b, _c) = world(3)
        ans = Answers(obj_updateGridCell=lambda o: None, **standard([b]))
        MV.MoveModel(mem, ans, inline_grid=False).move_with_collision(a, (0, 0, 0), 0, 0)
        self.assertIn(('obj_updateGridCell', (a,)), ans.log)


def player(mem, P=0x00400000, slot=0, facing=0, state=2):
    mem.poke(P + 0xC, 4, 0x60)
    mem.poke(P + 0x1C, 4, f32(12.0))
    mem.poke(P + 0x38, 2, facing & 0xFFFF)
    mem.poke(P + 0x3C8, 4, slot)
    mem.poke(P + 0x58C, 4, state)
    mem.poke(P + 0x118, 1, 4)
    mem.poke(T.G_RUN_SPEED, 4, T.ONE)
    mem.poke(T.G_PLAYERS + slot * T.REC_SIZE + 0x4C20, 4, T.ONE)
    mem.poke(MV.G_SIM_FRAME, 4, 1)                                       # no water test
    return P


PAD = 0x00500000


CALLED_OUT = ('creature_moveSimple', 'Player_animStep', 'Player_clampToScreen')


def mover(mem, answers):
    """A model whose Player_move call-outs are left to the test."""
    return MV.MoveModel(mem, answers, CALLED_OUT)


def player_answers(moved=None, **extra):
    base = dict(
        dialog_isOpen=lambda: 0, net_getCamYaw=lambda slot: 0, net_getCamFlag=lambda slot: 0,
        net_isLocalSlot=lambda slot: 0, Player_animStep=lambda P, speed: 0,
        creature_findSpellByType=lambda c, ti: 0,
        creature_moveSimple=lambda P, W: (moved.append(W) if moved is not None else None) or 0,
    )
    base.update(extra)
    return Answers(**base)


class PlayerMove(unittest.TestCase):
    def test_walk_turns_40_percent_and_moves_along_the_facing(self):
        mem = RC.Memory()
        P = player(mem)
        mem.poke(PAD + 0x14, 4, 0)
        mem.poke(PAD + 0x18, 4, f32(-1.0))                               # up on the stick
        moved = []
        model = mover(mem, player_answers(moved))
        model.player_move(P, 0, PAD)
        target = T.s16(C.atan2_16(0, f32(-1.0)) - 0x41C2)
        self.assertEqual(T.s16(mem.load(P + 0x38, 2)), C.angle_approach(0x3ECCCCCC, MV.MINUS_ONE, MV.MINUS_ONE, 0,
                                                                         target))
        F = T.s16(mem.load(P + 0x38, 2))
        vx, vy = fl(moved[0][0]), fl(moved[0][1])
        speed = 180.0 * fl(0x3F5CA86D)
        self.assertAlmostEqual(vx, speed * fl(C.cos16(F)), delta=0.05)
        self.assertAlmostEqual(vy, speed * fl(C.sin16(F)), delta=0.05)
        self.assertEqual(model.vec(MV.G_MOVE_VELOCITY), tuple(moved[0]))    # the static copy

    def test_mode_2_is_300_forward_and_mode_5_the_given_vector(self):
        for mode, ext, want in ((2, 0, (300.0, 0.0)), (5, (f32(7.0), f32(-3.0), 0), (7.0, -3.0))):
            mem = RC.Memory()
            P = player(mem)
            moved = []
            mover(mem, player_answers(moved)).player_move(P, mode, PAD, ext)
            self.assertAlmostEqual(fl(moved[0][0]), want[0], places=3)
            self.assertAlmostEqual(fl(moved[0][1]), want[1], places=3)

    def test_slow_scales_the_velocity(self):
        mem = RC.Memory()
        P = player(mem)
        mem.poke(P + 0x2FC, 1, 30)
        moved = []
        mover(mem, player_answers(moved)).player_move(P, 2, PAD)
        self.assertAlmostEqual(fl(moved[0][0]), 300.0 * 30 * fl(MV.DT), places=2)

    def test_swing_window_stops_a_scripted_push(self):
        mem = RC.Memory()
        P = player(mem, state=1)
        mem.poke(T.G_PLAYERS + 0x4A86, 1, 0)                              # weapon class 0
        mem.poke(MV.G_SIM_FRAME, 4, 101)
        mem.poke(P + 0x448, 4, 101 - 12)                                  # 12 ticks: inside 9 .. 22.5
        moved = []
        mover(mem, player_answers(moved)).player_move(P, 5, PAD, (f32(50.0), f32(50.0), f32(1.0)))
        self.assertEqual(moved[0][:2], (0, 0))
        mem.poke(P + 0x448, 4, 101 - 30)                                  # outside
        moved = []
        mover(mem, player_answers(moved)).player_move(P, 5, PAD, (f32(50.0), f32(50.0), f32(1.0)))
        self.assertEqual(moved[0][0], f32(50.0))

    def test_entering_water_draws_the_shared_seed_once(self):
        mem = RC.Memory()
        P = player(mem)
        mem.poke(MV.G_SIM_FRAME, 4, 8)
        for i, b in enumerate(b'splash%d\0'):
            mem.poke(MV.S_SPLASH_FMT + i, 1, b)
        ans = player_answers(water_test=lambda w, pos, out, r: (1, f32(5.0)), res_find=lambda lump, name: 7,
                             sound_playOnObject=lambda e, o, v: 0, water_disturb=lambda w, p, a, b: 1)
        model = mover(mem, ans)
        model.player_move(P, 3, PAD)
        self.assertEqual(model.draws, 1)
        self.assertTrue(model.u64(P + 0xA8) & MV.WATER_BIT)
        self.assertIn(('res_find', (MV.S_FX_LUMP, b'splash1')), ans.log)

    def test_landing_with_the_flag_returns_to_neutral(self):
        mem = RC.Memory()
        P = player(mem, state=7)
        mem.poke(P + 0x47D, 1, 1)
        ans = player_answers(creature_moveSimple=lambda P_, W: 4, Player_footstep=lambda P_: None)
        mover(mem, ans).player_move(P, 3, PAD)
        self.assertEqual(mem.load(P + 0x58C, 4), 2)
        self.assertEqual(mem.load(P + 0x482, 1), 15)
        self.assertIn(('Player_footstep', (P,)), ans.log)

    def test_zero_weight_times_negative_difference_is_minus_zero(self):
        self.assertEqual(MV.track_weight(0, 0, T.D_045), C.SIGN)
        self.assertEqual(MV.track_weight(0, f32(0.5), T.D_045), 0)
        self.assertNotEqual(MV.track_weight(T.ONE, f32(0.5), T.D_045), 0)

    def test_calls_made_on_every_move(self):
        mem = RC.Memory()
        P = player(mem)
        ans = player_answers()
        mover(mem, ans).player_move(P, 3, PAD)
        names = [n for n, _a in ans.log]
        self.assertEqual(names[0], 'dialog_isOpen')
        self.assertEqual(names[-1], 'net_getCamFlag')
        self.assertIn('net_getCamYaw', names)


class AnimStepAndClamp(unittest.TestCase):
    def test_root_is_rotated_into_world_axes(self):
        mem = RC.Memory()
        P = player(mem, facing=0x4000)

        def advance(state, sound, root, yaw, speed):
            mem.poke(root, 4, f32(2.0))
            mem.poke(root + 4, 4, f32(0.0))
            return 5
        model = MV.MoveModel(mem, Answers(anim_advance=advance))
        self.assertEqual(model.player_anim_step(P, T.ONE), 5)
        # facing +y: rotation by F - 0x4000 = 0 gives (-rx, ...) = (-2, 0)
        self.assertAlmostEqual(fl(mem.load(P + 0xBC, 4)), -2.0, places=4)
        self.assertAlmostEqual(fl(mem.load(P + 0xC0, 4)), 0.0, places=4)

    def test_own_player_has_no_sound_position(self):
        mem = RC.Memory()
        P = player(mem)
        mem.poke(P + 0xC, 4, 0x60 | MV.F_OWN_SOUND)
        seen = []
        model = MV.MoveModel(mem, Answers(anim_advance=lambda s, snd, r, y, sp: seen.append(snd) or 0))
        model.player_anim_step(P, T.ONE)
        self.assertEqual(seen, [0])

    def clamp(self, normals, V, points=None):
        mem = RC.Memory()
        P = player(mem)
        mem.poke(P + 0x18, 4, f32(10.0))
        points = points or [(0, 0, 0)] * 4

        def planes(pos):
            for i, n in enumerate(normals):
                for j in range(3):
                    mem.poke(MV.G_SCREEN_NORMALS + 12 * i + 4 * j, 4, f32(n[j]))
                    mem.poke(MV.G_SCREEN_POINTS + 12 * i + 4 * j, 4, f32(points[i][j]))
        model = MV.MoveModel(mem, Answers(game_buildScreenEdgePlanes=planes))
        return model.player_clamp_to_screen_vec(P, tuple(f32(v) for v in V))

    def test_inside_every_plane_changes_nothing(self):
        r, V, mask = self.clamp([(0, 0, 1)] * 4, (100.0, 0, 0))
        self.assertEqual((r, mask), (0, 0))

    def test_one_plane_removes_the_outward_component(self):
        r, V, mask = self.clamp([(1, 0, 0), (0, 0, 1), (0, 0, 1), (0, 0, 1)], (-100.0, 0, 0))
        self.assertEqual((r, mask), (0, 0))                              # on the plane: not outside
        r, V, mask = self.clamp([(1, 0, -1), (0, 0, 1), (0, 0, 1), (0, 0, 1)], (-100.0, 30.0, 0))
        self.assertEqual((r, mask), (1, 1))
        self.assertAlmostEqual(fl(V[0]), 0.0, delta=0.01)
        self.assertAlmostEqual(fl(V[1]), 30.0, delta=0.01)

    def test_two_planes_stop_the_step(self):
        r, V, mask = self.clamp([(1, 0, -1), (0, 1, 0), (0, 0, 1), (0, 0, 1)], (-100.0, -100.0, 0),
                                points=[(0, 0, 0), (0, 5, 0), (0, 0, 0), (0, 0, 0)])
        self.assertEqual(mask, 3)
        self.assertEqual((r, V), (1, (0, 0, 0)))


class Composed(unittest.TestCase):
    def test_a_player_walks_with_a_moving_stick(self):
        rt = MV.MoveRuntime()
        P = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        rt.stick(0, 1.0, 0.0)
        for _ in range(10):
            rt.tick()
        x = fl(rt.u32(P + 0x10))
        self.assertGreater(x, 20.0)
        self.assertLessEqual(abs(T.s16(rt.mem.load(P + 0x38, 2)) + 0x1C2), 8)     # toward 0x4000 - 0x41c2
        rt2 = MV.MoveRuntime()
        P2 = rt2.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        rt2.stick(0, 1.0, 0.0)
        for _ in range(10):
            rt2.tick()
        self.assertEqual(rt.u32(P + 0x10), rt2.u32(P2 + 0x10))           # deterministic

    def test_walking_into_a_monster_touches_it_and_pushes_out(self):
        rt = MV.MoveRuntime()
        P = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        c = rt.spawn_skelight((40.0, -2.0, 0.0), team=1)
        rt.stick(0, 1.0, 0.0)
        pushed = False
        for _ in range(30):
            rt.tick()
            if rt.mem.load(P + 0x490, 1) & 2:
                pushed = True
        self.assertTrue(pushed)
        x = fl(rt.u32(P + 0x10))
        self.assertLess(x, 40.0 - 12.0)                                   # held off by the radii
        self.assertTrue(rt.model.u64(c + 0xA8) & (1 << 59))              # Creature_onTouch: a player

    def test_the_screen_clamp_needs_authored_planes(self):
        rt = MV.MoveRuntime()
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.spawn_player(1, (100.0, 0.0, 0.0))
        rt.stick(0, 1.0, 0.0)
        with self.assertRaises(T.Unsupported):
            rt.tick()


if __name__ == '__main__':
    unittest.main()


class CreatureKnockbackInMoveRuntime(unittest.TestCase):
    """Regression: MoveModel's Player_move water helper once had the name of ref_creature's
    Creature_moveBy water helper and hid it, so a creature knocked back in a MoveRuntime
    failed.  Same expectations as round 1's knock-back test."""

    def test_a_creature_knock_back_reaches_the_creature_water_helper(self):
        rt = MV.MoveRuntime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), cflags=0)
        rt.mem.poke(c + 0x2E8, 4, C.f32(100.0))
        shared = rt.u32(T.G_RAND_SEED)
        rt.model.apply_knockback(c, C.f32(0.7))
        self.assertEqual(rt.u32(T.G_RAND_SEED), shared)
        self.assertEqual(rt.u32(c + 0x2E8), C.f32(98.0))
        self.assertGreater(rt.u32(c + 0x10), 0)
