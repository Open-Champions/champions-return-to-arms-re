"""Tests for ref_anim.py that need no game file: synthetic clips built with encode_clip.

Run: python3 -m unittest discover -s tools -p test_ref_anim.py

The expected values were worked out by hand from the rules in docs/spec/animation.md (the
clips are chosen so that the arithmetic is exact or the tolerance obvious).  Agreement with
the original machine code is the business of tools/difftest_anim.py, which needs your own
executable and clips.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_anim as A                            # noqa: E402

F = C.f32


def val(raw):
    return C.to_float(raw)


def walker(length=30, sound_times=None, sound_group=0, joint1_y=128):
    """Two joints.  Joint 0 starts at (1, 0, 10) and moves +1 unit per tick along x from
    tick 0; joint 1 hangs 2 units (joint1_y / 64) along y below it.  Bind offsets are minus
    the rest position, so both matrices are pure translations by the travelled distance."""
    return A.Clip(A.encode_clip(
        [((64, 0, 640), (4096, 0, 0, 0)), ((0, joint1_y, 0), (4096, 0, 0, 0))], length,
        keys=[(0, 0, 'p', (256, 0, 0))], bind=[(-64, 0, -640), (-64, -128, -640)],
        sound_times=sound_times, sound_group=sound_group), 'walker')


def steps(system, state, count, speed=A.ONE, **kw):
    return [A.anim_advance(system, speed, state, **kw) for _ in range(count)]


class ClipFormat(unittest.TestCase):
    def test_round_trip(self):
        clip = walker(sound_times=[5, 5, 12], sound_group=3)
        self.assertEqual((clip.joint_count, clip.length), (2, 30))
        self.assertEqual(clip.depth, [0, 1])
        self.assertEqual(clip.bind[1], (-64, -128, -640, 0))
        self.assertEqual(clip.sound_times, [5, 5, 12, 0x7FFFFFFF])
        self.assertEqual(clip.sound_group, 3)
        self.assertEqual(clip.events, [[0, 0]] * 4)
        self.assertEqual(clip.word(10 ** 6), 0)

    def test_too_many_joints(self):
        data = bytearray(walker().data)
        data[0] = 65
        with self.assertRaises(A.HostFault):
            A.Clip(bytes(data))

    def test_sixteen_bit_fields(self):
        clip = A.Clip(A.encode_clip([((-32768, 32767, -1), (-4096, 1, -1, 32767))], 5,
                                    keys=[(3, 0, 'r', (-32768, 32767, 0, -1))]))
        (pos, quat), = A.decode_clip(clip, F(0.0))
        self.assertEqual([val(v) for v in pos], [-512.0, 32767 / 64.0, -1 / 64.0])
        self.assertEqual([val(v) for v in quat], [1 / 4096.0, -1 / 4096.0, 32767 / 4096.0, -1.0])
        (_, quat), = A.decode_clip(clip, F(4.0))        # one tick of velocity after the key at 3
        self.assertEqual(val(quat[3]), -1.0 - 32768 / 131072.0)
        self.assertEqual(val(quat[0]), 1 / 4096.0 + 32767 / 131072.0)


class Decoder(unittest.TestCase):
    def test_values(self):
        clip = walker()
        joints = A.decode_clip(clip, F(5.5))
        self.assertEqual([val(v) for v in joints[0][0]], [6.5, 0.0, 10.0])
        self.assertEqual([val(v) for v in joints[0][1]], [0.0, 0.0, 0.0, 1.0])
        self.assertEqual([val(v) for v in joints[1][0]], [0.0, 2.0, 0.0])

    def test_forward_and_restart_agree(self):
        clip = A.Clip(A.encode_clip(
            [((0, 0, 0), (4096, 0, 0, 0))], 40,
            keys=[(2, 0, 'p', (77, -3, 5)), (9, 0, 'r', (11, -7, 3, 1)), (17, 0, 'p', (-41, 9, 0)),
                  (30, 0, 'r', (-5, 2, 0, 0))]))
        system = A.AnimSystem(decoder_slots=3, pose_buffers=2)
        a, b = A.Track(), A.Track()
        a.clip = b.clip = clip
        for t in (3.0, 10.5, 18.0, 31.25):
            a.time = F(t)
            A.animtrack_decode(system, a)
        b.time = F(31.25)
        A.animtrack_decode(system, b)
        self.assertEqual(a.slot.joints[0], b.slot.joints[0])
        self.assertEqual((a.slot.tick, a.slot.cursor), (b.slot.tick, b.slot.cursor))
        a.time = F(4.0)                                 # going back starts over
        A.animtrack_decode(system, a)
        self.assertEqual(a.slot.tick, 2)

    def test_stream_runs_out(self):
        # no keys: the closing delta of 255 is the first record, taken for a key at tick 255
        clip = A.Clip(A.encode_clip([((0, 0, 0), (4096, 0, 0, 0))], 300))
        A.decode_clip(clip, F(254.9))
        with self.assertRaises(A.HostFault):
            A.decode_clip(clip, F(255.0))

    def test_root_track_skips_joint0_xy(self):
        clip = walker()
        system = A.AnimSystem(decoder_slots=3, pose_buffers=2)
        track = A.Track()
        track.clip, track.flags, track.time = clip, A.ROOT, F(0.0)
        slot = A.animtrack_decode(system, track)
        self.assertEqual([val(v) for v in slot.joints[0][A.PX:A.PZ + 1]], [0.0, 0.0, 10.0])


class Pool(unittest.TestCase):
    def test_first_slots(self):
        pool = A.DecoderPool()
        self.assertEqual([pool.alloc().index, pool.alloc().index], [164, 163])

    def test_pinned_slot_is_skipped(self):
        pool = A.DecoderPool(3)
        tracks = [A.Track() for _ in range(3)]
        tracks[0].flags = A.ROOT
        for track in tracks:
            track.slot = pool.alloc()
            track.slot.owner = track
        taken = pool.alloc()
        self.assertEqual(taken.index, 1)
        self.assertIsNone(tracks[1].slot)
        self.assertEqual(tracks[0].slot.index, 2)
        self.assertEqual([s.index for s in pool.order], [0, 2, 1])

    def test_all_pinned(self):
        pool = A.DecoderPool(2)
        for _ in range(2):
            track = A.Track()
            track.flags = A.YAW
            track.slot = pool.alloc()
            track.slot.owner = track
        with self.assertRaises(A.HostFault):
            pool.alloc()

    def test_alloc_resets_little(self):
        pool = A.DecoderPool(2)
        slot = pool.alloc()
        slot.yaw, slot.joints[0][A.PX], slot.joints[0][A.PZ] = 77, F(3.0), F(4.0)
        pool.alloc()
        again = pool.alloc()
        self.assertIs(again, slot)
        self.assertEqual((again.tick, again.yaw, again.joints[0][A.PX], val(again.joints[0][A.PZ])),
                         (1000000, 77, 0, 4.0))


class Tracks(unittest.TestCase):
    def setUp(self):
        self.system = A.AnimSystem(decoder_slots=8, pose_buffers=4)
        self.a, self.b = walker(), walker(joint1_y=256)

    def test_start_on_empty_state_is_full_after_one_tick(self):
        state = A.AnimState(8)
        A.anim_start(F(0.5), state, self.a, A.LOOP)
        self.assertEqual((val(state.tracks[0].weight), val(state.tracks[0].rate)), (0.0, 1.0))
        A.anim_advance(self.system, A.ONE, state)
        self.assertEqual(val(state.tracks[0].weight), 1.0)
        A.anim_start(F(0.5), state, self.b, A.LOOP)
        A.anim_advance(self.system, A.ONE, state)
        self.assertAlmostEqual(val(state.tracks[1].weight), 1 / 30.0, places=6)

    def test_start_replaces_top_when_full(self):
        state = A.AnimState(2)
        A.anim_push(state, self.a, 0)
        A.anim_push(state, self.a, 0)
        self.assertIsNone(A.anim_push(state, self.b, 0))
        A.anim_start(F(0.0), state, self.b, A.LOOP)
        self.assertEqual(state.count, 2)
        self.assertIs(state.tracks[1].clip, self.b)

    def test_plain_track_is_removed_at_its_end(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, 0)
        steps(self.system, state, 30)
        self.assertEqual(state.count, 1)                # 30 * 0.99999994 < 30
        steps(self.system, state, 1)
        self.assertEqual(state.count, 0)

    def test_report_end(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.REPORT_END)
        steps(self.system, state, 30)
        self.assertEqual(state.flags & 0x480, 0)
        steps(self.system, state, 1)
        self.assertEqual(state.flags & 0x480, 0x480)
        self.assertEqual((state.count, val(state.tracks[0].time)), (1, 30.0))

    def test_blend_in_out_is_gone_at_the_end(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        A.anim_start_blend_in_out(F(0.1), F(0.1), state, self.b, 0)
        track = state.tracks[1]
        self.assertAlmostEqual(val(track.life), 30 / 6.0, places=4)
        self.assertAlmostEqual(val(track.life_rate), -1 / 6.0, places=6)
        steps(self.system, state, 29)
        self.assertEqual(state.count, 2)
        steps(self.system, state, 2)
        self.assertEqual(state.count, 1)

    def test_purge_ends_the_step(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP | A.PERSISTENT)
        A.anim_push(state, self.a, A.LOOP)
        A.anim_start(F(0.0), state, self.b, A.LOOP | A.PURGE_BELOW)
        A.anim_advance(self.system, A.ONE, state)
        self.assertEqual(state.count, 2)
        self.assertIs(state.tracks[1].clip, self.b)
        self.assertEqual(val(state.tracks[0].time), 0.0)        # the survivor was not stepped
        self.assertEqual(state.flags & A.PERSISTENT, 0)         # nor did its flags join
        steps(self.system, state, 5)                            # and it stays frozen while the
        self.assertEqual(val(state.tracks[0].time), 0.0)        # purging track is at full weight
        A.anim_stop(F(0.0), state, self.b)
        A.anim_advance(self.system, A.ONE, state)
        self.assertGreater(val(state.tracks[0].time), 0.9)

    def test_stop(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        A.anim_push(state, self.b, A.LOOP | A.PERSISTENT | A.REPORT_END)
        A.anim_stop(F(0.5), state, self.b)
        self.assertEqual(state.tracks[1].flags, A.LOOP)
        steps(self.system, state, 100)
        self.assertEqual(state.count, 2)                        # faded, never removed
        self.assertLess(val(state.tracks[1].weight), -2.0)
        A.anim_stop(F(0.0), state, self.b)
        self.assertEqual(state.count, 1)

    def test_chained_track_waits(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.REPORT_END)
        state.tracks[1].sound_idx = 9                           # left by an earlier track
        A.anim_push_chained(state, self.b, A.LOOP)
        self.assertEqual(val(state.tracks[1].time), -28.0)
        self.assertEqual(state.tracks[1].sound_idx, 9)
        steps(self.system, state, 28)
        self.assertLess(val(state.tracks[1].time), 0.0)
        steps(self.system, state, 1)
        self.assertGreater(val(state.tracks[1].time), 0.0)
        with self.assertRaises(A.HostFault):
            A.anim_push_chained(A.AnimState(8), self.a, 0)

    def test_event_fires_once_on_its_tick(self):
        self.a.events[0] = [F(0.25), 0x10]                      # 0.25 s = tick 15
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        fired = [k for k, result in enumerate(steps(self.system, state, 30)) if result[0]]
        self.assertEqual(fired, [15])

    def test_event_byte_is_signed(self):
        self.a.events[0] = [F(0.0), 0x80]
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        self.assertEqual(A.anim_advance(self.system, A.ONE, state)[0], -128)

    def test_sync_and_find(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP | A.TALK)
        self.system.sim_frame = 100
        A.anim_sync_to_sim_frame(self.system, state)
        self.assertAlmostEqual(val(state.tracks[0].time), 10.0, places=3)
        self.assertEqual(A.anim_find_track_by_flag(state, A.TALK), 0)
        self.assertEqual(A.anim_find_track_by_flag(state, A.ROOT), -1000000000)
        self.assertIs(A.anim_find_track(state, self.a), state.tracks[0])
        self.assertIsNone(A.anim_find_track(state, self.b))

    def test_randomize_uses_the_cosmetic_generator(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        self.system.cosmetic_seed = 1
        A.anim_randomize_top_time(self.system, state)
        seed = (0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.assertEqual(self.system.cosmetic_seed, seed)
        self.assertAlmostEqual(val(state.tracks[0].time), (seed >> 16) / 65536.0 * 30, places=3)


class RootMotion(unittest.TestCase):
    def setUp(self):
        self.system = A.AnimSystem(decoder_slots=8, pose_buffers=4)
        self.clip = walker()

    def test_delta_follows_the_track_across_the_wrap(self):
        state = A.AnimState(8)
        A.anim_push(state, self.clip, A.LOOP | A.ROOT)
        results = steps(self.system, state, 61)
        for _events, dx, dy, yaw in results:
            self.assertAlmostEqual(val(dx), 1.0, places=4)      # one unit per tick, wrap included
            self.assertEqual((val(dy), yaw), (0.0, 0))
        self.assertLess(val(state.tracks[0].time), 30.0)

    def test_weight_scales_the_delta(self):
        state = A.AnimState(8)
        A.anim_push_with_weights(state, self.clip, A.LOOP | A.ROOT, F(0.25), A.ZERO, A.ONE, A.ZERO)
        self.assertAlmostEqual(val(A.anim_advance(self.system, A.ONE, state)[1]), 0.25, places=5)

    def test_no_output_pointer(self):
        state = A.AnimState(8)
        A.anim_push(state, self.clip, A.LOOP | A.ROOT)
        with self.assertRaises(A.HostFault):
            A.anim_advance(self.system, A.ONE, state, want_root=False)

    def test_rebase_hides_a_jump(self):
        state = A.AnimState(8)
        A.anim_push(state, self.clip, A.LOOP | A.ROOT)
        steps(self.system, state, 3)
        A.anim_jump_top_to_end(self.system, state)
        self.assertAlmostEqual(val(A.anim_advance(self.system, A.ZERO, state)[1]), 0.0, places=5)

    def test_slowed_creature_gets_no_yaw(self):
        state = A.AnimState(8)
        plain = A.creature_step_anim(self.system, A.ONE, state, 0x4000, F(2.0), slow=0, active=False,
                                     delta=(A.ONE, A.ZERO), yaw=1000)
        self.assertEqual((val(plain[1]), plain[3]), (-2.0, 1000))
        slowed = A.creature_step_anim(self.system, A.ONE, state, 0x4000, F(2.0), slow=30, active=False,
                                      delta=(A.ONE, A.ZERO), yaw=1000)
        self.assertAlmostEqual(val(slowed[1]), -1.0, places=5)
        self.assertEqual(slowed[3], 0)

    def test_copy_does_not_copy_the_yaw_baseline(self):
        state = A.AnimState(8)
        A.anim_push(state, self.clip, A.LOOP | A.ROOT | A.YAW)
        steps(self.system, state, 2)
        state.tracks[0].slot.yaw = 1234
        copy = A.anim_state_copy(self.system, state)
        self.assertIsNot(copy.tracks[0].slot, state.tracks[0].slot)
        self.assertEqual(copy.tracks[0].slot.joints, state.tracks[0].slot.joints)
        self.assertEqual(copy.tracks[0].slot.yaw, 0)
        self.assertIsNone(copy.pose)


class Sounds(unittest.TestCase):
    def test_ranges_and_wrap(self):
        system = A.AnimSystem(decoder_slots=4, pose_buffers=2)
        clip = walker(sound_times=[5, 5, 12])
        state = A.AnimState(8)
        A.anim_push(state, clip, A.LOOP)
        steps(system, state, 14)
        self.assertEqual(system.sound_log, [(clip, 0, 2), (clip, 2, 3)])
        self.assertEqual(state.tracks[0].sound_idx, 3)
        steps(system, state, 17)                                # wraps at tick 30
        self.assertEqual(state.tracks[0].sound_idx, 0)
        steps(system, state, 6)
        self.assertEqual(system.sound_log[2:], [(clip, 0, 2)])

    def test_no_position_no_sound(self):
        system = A.AnimSystem(decoder_slots=4, pose_buffers=2)
        clip = walker(sound_times=[5])
        state = A.AnimState(8)
        A.anim_push(state, clip, A.LOOP)
        steps(system, state, 10, sound=False)
        self.assertEqual((system.sound_log, state.tracks[0].sound_idx), ([], 0))

    def test_group_limit_mutes_but_moves_the_cursor(self):
        limits = [0] * 256
        limits[3] = 2                                           # limit - 2 = 0 < count
        system = A.AnimSystem(decoder_slots=4, pose_buffers=2, group_limits=limits)
        clip = walker(sound_times=[5], sound_group=3)
        state = A.AnimState(8)
        A.anim_push(state, clip, A.LOOP)
        steps(system, state, 10)                                # same picture throughout
        self.assertEqual((system.sound_log, state.tracks[0].sound_idx), ([], 1))

    def test_cursor_outside_the_table(self):
        system = A.AnimSystem(decoder_slots=4, pose_buffers=2)
        state = A.AnimState(8)
        A.anim_push(state, walker(), A.REPORT_END)
        steps(system, state, 31)
        state.tracks[1].sound_idx = 9
        A.anim_push_chained(state, walker(sound_times=[5]), A.LOOP)     # starts at time 2.0
        with self.assertRaises(A.HostFault):
            A.anim_advance(system, A.ONE, state)


class Pose(unittest.TestCase):
    def setUp(self):
        self.system = A.AnimSystem(decoder_slots=8, pose_buffers=3)
        self.system.draw_frame = 10
        self.a, self.b = walker(), walker(joint1_y=256)

    def matrix(self, state, joint):
        return [val(v) for v in A.anim_get_joint_matrix(self.system, state, joint)]

    def test_translation_and_hierarchy(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, 0)
        state.tracks[0].time = F(5.0)
        identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        self.assertEqual(self.matrix(state, 0), identity + [5.0, 0.0, 0.0])
        self.assertEqual(self.matrix(state, 1), identity + [5.0, 0.0, 0.0])
        self.assertEqual(self.matrix(state, 99), self.matrix(state, 1))     # clamped
        self.assertEqual(self.matrix(state, -4), self.matrix(state, 0))
        self.assertEqual(state.pose.mats[2], [[0, 0, 0, 0]] * 3)            # joint n is zeroed
        self.assertEqual(state.pose.joint_count, 2)

    def test_rotation(self):
        # a quarter turn about z in the parent: (x, y, z, w) = (0, 0, s, s), stored w first
        s = 2896                                                # 0.70703125 * 4096
        clip = A.Clip(A.encode_clip([((0, 0, 0), (s, 0, 0, s)), ((640, 0, 0), (4096, 0, 0, 0))], 10))
        state = A.AnimState(1)
        A.anim_push(state, clip, 0)
        m = self.matrix(state, 1)
        self.assertAlmostEqual(m[9], 0.0, delta=0.02)           # the child's +x offset now points along +y
        self.assertAlmostEqual(m[10], 10.0, delta=0.02)
        self.assertAlmostEqual(m[1], 1.0, delta=0.001)          # row-vector layout: x axis maps to +y
        self.assertAlmostEqual(m[3], -1.0, delta=0.001)

    def test_root_and_blend(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP | A.ROOT)
        state.tracks[0].time = F(5.0)
        self.assertEqual(self.matrix(state, 0)[9:], [-1.0, 0.0, 0.0])      # x left the pose: 0 + bind
        A.anim_release_caches(state)
        A.anim_push_with_weights(state, self.b, A.LOOP, F(0.5), A.ZERO, A.ONE, A.ZERO)
        state.tracks[1].time = F(5.0)
        # joint 0's x blends 0 (root track) with 6 -> 3; joint 1's y blends 2 with 4 -> 3;
        # world (3, 3, 10) plus the bind offset (-1, -2, -10)
        self.assertEqual(self.matrix(state, 1)[9:], [2.0, 1.0, 0.0])

    def test_cache_rules(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        before = self.matrix(state, 1)
        buf = state.pose
        self.assertIs(buf.owner, state)
        self.assertIs(self.system.poses.order[-1], buf)
        A.anim_push(state, self.b, A.LOOP)                      # a full-weight change ...
        self.assertEqual(self.matrix(state, 1), before)         # ... is not seen: no rebuild
        A.anim_advance(self.system, A.ZERO, state)              # a step detaches
        self.assertIsNone(state.pose)
        self.assertIsNone(buf.owner)
        self.assertEqual(self.matrix(state, 1)[10], before[10] + 2.0)

    def test_no_base_track_reads_the_default_pose(self):
        state = A.AnimState(8)
        A.anim_start(F(0.5), state, self.a, A.LOOP)             # weight 0 until the first step
        self.assertEqual(self.matrix(state, 1), [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0])
        self.assertIsNone(state.pose)

    def test_fallback_and_draw(self):
        state = A.AnimState(8)
        A.anim_push(state, self.a, A.LOOP)
        for buf in self.system.poses.buffers:
            buf.stamp = 9                                       # drawn within the last three pictures
        self.matrix(state, 0)
        self.assertIs(state.pose, self.system.poses.fallback)
        drawn = A.anim_emit_pose(self.system, state)            # the fallback buffer is never drawn
        self.assertIs(drawn, self.system.poses.default)
        self.assertIsNone(state.pose)
        self.system.draw_frame = 20
        drawn = A.anim_emit_pose(self.system, state)
        self.assertIs(drawn, state.pose)
        self.assertEqual(drawn.stamp, 20)
        self.assertIs(self.system.poses.order[-1], drawn)

    def test_newest_buffer_is_never_taken(self):
        first, second = A.AnimState(8), A.AnimState(8)
        for state in (first, second):
            A.anim_push(state, self.a, A.LOOP)
            self.matrix(state, 0)
        self.assertIsNot(first.pose, second.pose)
        self.assertIs(self.system.poses.order[-1], second.pose)

    def test_attach_point_without_state(self):
        pos = [F(100.0), F(200.0), F(300.0)]
        p, d = A.model_get_attach_point(self.system, F(2.0), pos, 0x4000, None, 0,
                                        [F(1.0), F(2.0), F(3.0)], [F(1.0), A.ZERO, A.ZERO])
        for got, want in zip(p, (98.0, 196.0, 306.0)):
            self.assertAlmostEqual(val(got), want, places=3)
        self.assertAlmostEqual(val(d[0]), -1.0, places=5)

    def test_sample_point(self):
        pos = [A.ZERO, A.ZERO, A.ZERO]
        p, radius, matrix = A.model_get_sample_point(self.system, F(2.0), pos, 0x4000, None,
                                                     (16, 0, 32, 0x0304), True)
        self.assertAlmostEqual(val(p[0]), -2.0, places=4)
        self.assertEqual((val(p[2]), val(radius)), (4.0, 0x0304 * 2.0))
        p, radius, matrix = A.model_get_sample_point(self.system, F(2.0), pos, 0, None, None, True)
        self.assertEqual((radius, matrix), (0, C.mat3_set_identity()))

    def test_ftoi(self):
        self.assertEqual(A._ftoi(F(1.0), 12), 4096)
        self.assertEqual(A._ftoi(F(-0.5), 12), -2048)
        self.assertEqual(A._ftoi(F(0.99999), 4), 15)
        self.assertEqual(A._ftoi(F(1e9), 12), 0x7FFFFFFF)
        self.assertEqual(A._ftoi(F(-1e9), 4), -0x80000000)


if __name__ == '__main__':
    unittest.main()
