#!/usr/bin/env python3
"""test_ref_attach_matrix.py - unit tests of tools/ref_attach_matrix.py that need no game
files.

Made-up memory: a pose buffer's quantisation (1/4096, 1/64) and transposition, the joint
clamp at both ends, the pose builder and the default pose, the attach record address, the
model-space matrix's scale, the world matrix's unscaled rotation and placed offset, the
creature's fields, and the Soul model's routing of the two call-outs.  Whether the model
matches the game is tools/difftest_attach_matrix.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_attach_matrix as AT                  # noqa: E402

f32, fl = C.f32, C.to_float
M32 = 0xFFFFFFFF
MODEL, POSE, STATE, CREATURE, DEF = 0x100000, 0x110000, 0x120000, 0x130000, 0x140000


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = AT.Model(self.mem, self)
        self.built = []

    def get(self, name):
        if name == 'anim_buildPose':
            def build(state, flag):
                self.built.append((state, flag))
                if getattr(self, 'attach_on_build', None):
                    self.mem.poke(state, 4, self.attach_on_build)
            return build
        return None

    def pose(self, buf, joints):
        """joints: list of 3x4 integer rows (s16)."""
        self.mem.poke(buf + 8, 2, len(joints) & 0xFFFF)
        for j, rows in enumerate(joints):
            for k, row in enumerate(rows):
                for r, v in enumerate(row):
                    self.mem.poke(buf + 0x10 + 0x18 * j + 8 * k + 2 * r, 2, v & 0xFFFF)

    def record(self, header, index, joint, matrix):
        self.mem.poke(MODEL + 0x22, 1, header)
        rec = MODEL + 16 * header + 0x34 * index
        self.mem.poke(rec, 4, joint & M32)
        for k, v in enumerate(matrix):
            self.mem.poke(rec + 4 + 4 * k, 4, f32(v))
        return rec

    def floats(self, m):
        return [round(fl(v), 4) for v in m]


IDENTITY_ROWS = [[4096, 0, 0, 0], [0, 4096, 0, 0], [0, 0, 4096, 0]]
IDENTITY = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0]


class JointMatrix(Fixture):
    def test_quantised_and_transposed(self):
        """Row k of the stored joint is column k of the result; 4096 is 1.0, 64 is 1.0."""
        self.pose(POSE, [[[4096, 2048, 0, 64], [0, 4096, -1024, 128], [1, 0, 4096, -640]]])
        self.mem.poke(STATE, 4, POSE)
        m = self.floats(self.model.anim_get_joint_matrix(STATE, 0))
        self.assertEqual(m[0:3], [1.0, 0.0, round(1 / 4096, 4)])
        self.assertEqual(m[3:6], [0.5, 1.0, 0.0])
        self.assertEqual(m[6:9], [0.0, -0.25, 1.0])
        self.assertEqual(m[9:12], [1.0, 2.0, -10.0])
        self.assertEqual(self.built, [])

    def test_clamped_at_both_ends(self):
        self.pose(POSE, [IDENTITY_ROWS, [[0, 4096, 0, 64], [4096, 0, 0, 0], [0, 0, 4096, 0]]])
        self.mem.poke(STATE, 4, POSE)
        low = self.model.anim_get_joint_matrix(STATE, 0xFFFFFFFF)
        self.assertEqual(low, self.model.anim_get_joint_matrix(STATE, 0))
        high = self.model.anim_get_joint_matrix(STATE, 0x7FFFFFFF)
        self.assertEqual(high, self.model.anim_get_joint_matrix(STATE, 1))
        self.assertEqual(self.floats(high)[9], 1.0)

    def test_no_pose_builds_then_reads_default(self):
        self.pose(AT.DEFAULT_POSE, [[[0, 0, 0, 640], [0, 0, 0, 0], [0, 0, 0, 0]]])
        m = self.model.anim_get_joint_matrix(STATE, 0)
        self.assertEqual(self.built, [(STATE, 0)])
        self.assertEqual(self.model.calls, [('anim_buildPose', (STATE, 0))])
        self.assertEqual(self.floats(m)[9], 10.0)

    def test_builder_attaches_a_pose(self):
        self.pose(POSE, [[[0, 0, 0, 64 * 3], [0, 0, 0, 0], [0, 0, 0, 0]]])
        self.attach_on_build = POSE
        self.assertEqual(self.floats(self.model.anim_get_joint_matrix(STATE, 0))[9], 3.0)

    def test_empty_pose_reads_joint_minus_one(self):
        """A pose with no joints: last = -1, so joint -1 (the 0x18 bytes before) is read."""
        self.pose(POSE + 0x18, [])
        for k in range(3):
            self.mem.poke(POSE + 0x10 + 8 * k + 6, 2, 64 * (k + 1))
        self.mem.poke(STATE, 4, POSE + 0x18)
        self.assertEqual(self.floats(self.model.anim_get_joint_matrix(STATE, 5))[9:12], [1.0, 2.0, 3.0])


class AttachMatrix(Fixture):
    def test_record_address(self):
        self.assertEqual(AT.attach_record(MODEL, 3, 2), MODEL + 0x30 + 0x68)
        self.assertEqual(AT.attach_record(MODEL, 3, M32), MODEL + 0x30 - 0x34)

    def test_model_space_scaled_without_state(self):
        """No state: identity joint; the record's matrix times scale - both rotation and
        offset."""
        self.record(3, 1, 7, [1, 0, 0, 0, 1, 0, 0, 0, 1, 5, 6, 7])
        m = self.floats(self.model.model_get_attach_matrix(f32(2.0), MODEL, 0, 1))
        self.assertEqual(m, [2.0, 0, 0, 0, 2.0, 0, 0, 0, 2.0, 10.0, 12.0, 14.0])
        self.assertEqual(self.model.calls, [])

    def test_joint_word_selects_the_joint(self):
        self.pose(POSE, [IDENTITY_ROWS, [[4096, 0, 0, 64 * 4], [0, 4096, 0, 0], [0, 0, 4096, 0]]])
        self.mem.poke(STATE, 4, POSE)
        self.record(4, 0, 1, IDENTITY)
        m = self.floats(self.model.model_get_attach_matrix(f32(1.0), MODEL, STATE, 0))
        self.assertEqual(m[9:12], [4.0, 0.0, 0.0])


class WorldMatrix(Fixture):
    def test_rotation_unscaled_offset_placed(self):
        """Facing 0 turns by +0x4000: x goes to y.  The rotation is the record's (1/scale
        then scale); the offset is scaled, turned and added to the position."""
        self.record(3, 0, 0, [1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 0, 0])
        pos = (f32(100.0), f32(200.0), f32(5.0))
        m = self.floats(self.model.model_get_attach_world_matrix(f32(2.0), MODEL, pos, 0, 0, 0))
        self.assertEqual(m[0:9], [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0])
        self.assertEqual(m[9:12], [100.0, 220.0, 5.0])

    def test_facing_is_narrowed(self):
        self.record(3, 0, 0, IDENTITY)
        pos = (0, 0, 0)
        a = self.model.model_get_attach_world_matrix(f32(1.0), MODEL, pos, 0x12345, 0, 0)
        b = self.model.model_get_attach_world_matrix(f32(1.0), MODEL, pos, 0x2345, 0, 0)
        self.assertEqual(a, b)

    def test_creature_fields(self):
        """creature_getAttachMatrix0: scale +0xdc, model via +0x24 -> +0xc, position +0x10,
        facing +0x38, anim state +0x114, index 0."""
        self.record(3, 0, 0, [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 30])
        self.mem.poke(CREATURE + 0x24, 4, DEF)
        self.mem.poke(DEF + 0xC, 4, MODEL)
        self.mem.poke(CREATURE + 0xDC, 4, f32(0.5))
        for k, v in enumerate((1.0, 2.0, 3.0)):
            self.mem.poke(CREATURE + 0x10 + 4 * k, 4, f32(v))
        self.mem.poke(CREATURE + 0x38, 2, 0xC000)
        self.pose(POSE, [IDENTITY_ROWS])
        self.mem.poke(CREATURE + 0x114, 4, POSE)
        m = self.floats(self.model.creature_get_attach_matrix0(CREATURE))
        self.assertEqual(m[9:12], [1.0, 2.0, 18.0])
        self.assertEqual(self.built, [])

    def test_entry_stores_twelve_words(self):
        self.record(3, 0, 0, IDENTITY)
        self.model.attach_matrix_entry(MODEL, 0, 0, 0x150000, f32(1.0))
        self.assertEqual([a for a, _s, _v in self.model.writes], [0x150000 + 4 * k for k in range(12)])
        self.assertEqual(self.model.draws, 0)


class Routing(unittest.TestCase):
    def test_soul_model_runs_the_bodies(self):
        C.set_fpu('ps2')
        mem = RC.Memory()
        model = AT.SoulModel(mem, {})
        mem.poke(MODEL + 0x22, 1, 3)
        for k, v in enumerate(IDENTITY):
            mem.poke(MODEL + 0x30 + 4 + 4 * k, 4, f32(v))
        out = model.call('model_getAttachMatrix', MODEL, 0, 0, f32(1.0))
        self.assertEqual(len(out), 12)
        self.assertEqual(model.calls, [])
        self.assertNotIn('creature_getAttachMatrix0', AT.SOUL_EXTERNALS)
        self.assertIn('anim_buildPose', AT.SOUL_EXTERNALS)

    def test_executed(self):
        self.assertEqual(AT.EXECUTED, {'creature_getAttachMatrix0': 0x287940, 'model_getAttachWorldMatrix': 0x175330,
                                       'model_getAttachMatrix': 0x1795F8})


if __name__ == '__main__':
    unittest.main()
