"""ref_attach_matrix.py - the two attach-point matrices a held Soul's burst reads
(Soul_run state 0x1d, Soul_setState 0x21, Soul_draw), with the bodies underneath them.

Reference contract, executed against the original by tools/difftest_attach_matrix.py
(docs/spec/attach-matrix.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    creature_getAttachMatrix0   0x287940 (creature, out mat34)
    model_getAttachWorldMatrix  0x175330 (f12 scale, model, position, facing, anim state or 0,
                                          attach index, out mat34)
    model_getAttachMatrix       0x1795f8 (f12 scale, model, anim state or 0, attach index,
                                          out mat34)
    anim_getJointMatrix         0x16f720 (anim state, joint, out mat34): tools/ref_anim.py's
                                          anim_get_joint_matrix, here on raw memory (a pose
                                          buffer is a pointer in the state's first word)

The matrix helpers they call (mat34_setIdentity 0x165680, mat34_mul 0x162808, mat3_scale
0x165cc0, mat34_setPosRotZScale 0x163cb8) are tools/ref_core.py's bodies, executed by
tools/difftest_core.py, and run for real here.  The only call-out is anim_buildPose
0x16ed40 (tools/ref_anim.py, executed by tools/difftest_anim.py), reached when a state has
no pose yet.

Matrices are twelve float patterns in ref_core's row-vector layout: rows 0-2 the rotation,
row 3 (words 9-11) the translation; a point is v * M + t.

No body here draws from any generator.
"""
import ref_core as C
import ref_creature as RC
import ref_soul_run as SR
from ref_creature import Ext, M32, s16, s32

CREATURE_GET_ATTACH_MATRIX0 = 0x287940
MODEL_GET_ATTACH_WORLD_MATRIX = 0x175330
MODEL_GET_ATTACH_MATRIX = 0x1795F8
ANIM_GET_JOINT_MATRIX = 0x16F720
ANIM_BUILD_POSE = 0x16ED40

DEFAULT_POSE = 0x7B8380         # the pose read when a state has none (0x16f75c / 0x16f760)
ONE = RC.ONE                    # 1.0 (0x1753fc: the reciprocal of the scale)
K_QUAT = 0x39800000             # 1/4096, rotation of a pose matrix (0x16f77c)
K_POS = 0x3C800000              # 1/64, translation of a pose matrix (0x16f814)
FACING_BIAS = 0x4000            # added to the facing for the world turn (0x175448)
RECORD_SIZE = 0x34              # one attach record (index * 0x34, 0x17538c.. / 0x17960c..)
POSE_JOINT_SIZE = 0x18          # one joint of a pose buffer: three rows of four s16 at +0x10
ATTACH_INDEX_SOUL = 0           # the index both Soul call sites pass (0x287988, 0x2aa744)

MODELLED = {
    'creature_getAttachMatrix0': CREATURE_GET_ATTACH_MATRIX0,
    'model_getAttachWorldMatrix': MODEL_GET_ATTACH_WORLD_MATRIX,
    'model_getAttachMatrix': MODEL_GET_ATTACH_MATRIX,
    'anim_getJointMatrix': ANIM_GET_JOINT_MATRIX,
    # tools/ref_core.py's matrix bodies, executed by tools/difftest_core.py, run for real
    'mat34_setIdentity': 0x165680, 'mat34_mul': 0x162808, 'mat3_scale': 0x165CC0,
    'mat34_setPosRotZScale': 0x163CB8,
}
# the bodies tools/difftest_attach_matrix.py adds to what was executed before (name -> entry);
# anim_getJointMatrix was executed by tools/difftest_anim.py and runs for real here again
EXECUTED = {'creature_getAttachMatrix0': CREATURE_GET_ATTACH_MATRIX0,
            'model_getAttachWorldMatrix': MODEL_GET_ATTACH_WORLD_MATRIX,
            'model_getAttachMatrix': MODEL_GET_ATTACH_MATRIX}

EXTERNALS = {
    'anim_buildPose': Ext(ANIM_BUILD_POSE, 'pi', 0, 'n', '(anim state, for draw 0): may attach a pose'),
}


def attach_record(model, header, index):
    """The address of attach record `index`: model + 16 * u8(model + 0x22) + 0x34 * index
    (32-bit wrap, the index taken as it comes)."""
    return (model + 16 * header + RECORD_SIZE * index) & M32


class AttachBodies:
    """The four bodies on a memory image (a mix-in for any ref_creature.Model)."""

    def read_matrix(self, addr):
        return [self.u32((addr + 4 * k) & M32) for k in range(12)]

    def anim_get_joint_matrix(self, state, joint):
        """anim_getJointMatrix 0x16f720 (state, joint, out) -> 12 patterns.

        buf = the state's first word; when 0, anim_buildPose(state, 0) and the word is read
        again; still 0: the default pose 0x7b8380.  The joint (a signed word) is clamped:
        below 0 -> 0, then above s16(buf + 8) - 1 -> that (so a pose with no joints reads
        joint -1).  With p = buf + 0x18 * joint + 0x10 (three rows of four s16):
            out[3r + k] = float(s16 p[8k + 2r]) * 1/4096      (r, k = 0..2)
            out[9 + k]  = float(s16 p[8k + 6]) * 1/64"""
        buf = self.u32(state)
        if not buf:
            self.call('anim_buildPose', state, 0)
            buf = self.u32(state)
        if not buf:
            buf = DEFAULT_POSE
        j = s32(joint)
        if j < 0:
            j = 0
        last = self.s16(buf + 8) - 1
        if last < j:
            j = last
        base = (buf + POSE_JOINT_SIZE * j + 0x10) & M32
        out = [C.mul(C.from_int(self.s16((base + 8 * k + 2 * r) & M32)), K_QUAT)
               for r in range(3) for k in range(3)]
        return out + [C.mul(C.from_int(self.s16((base + 8 * k + 6) & M32)), K_POS) for k in range(3)]

    def joint_or_identity(self, state, rec):
        """The joint matrix of the record's joint word (+0), or the identity with no state."""
        if state:
            return self.anim_get_joint_matrix(state, self.u32(rec))
        return C.mat34_set_identity()

    def model_get_attach_world_matrix(self, scale, model, pos, facing, state, index):
        """model_getAttachWorldMatrix 0x175330 (f12 scale, a0 model, a1 pos, a2 facing,
        a3 state or 0, t0 index, t1 out) -> 12 patterns.

        rec = the attach record; J = the joint matrix (identity without a state);
        out = mat34_mul(rec + 4 (a mat34), J); the nine rotation words times 1/scale
        (div.s 1.0 / scale, once); then out = mat34_mul(out, mat34_setPosRotZScale(scale,
        pos, s16(s16 facing + 0x4000))).  The rotation therefore comes out unscaled and
        the record's offset scaled, turned and placed at pos."""
        rec = attach_record(model, self.u8(model + 0x22), index)
        pos = tuple(pos)
        j = self.joint_or_identity(state, rec)
        out = C.mat34_mul(self.read_matrix(rec + 4), j)
        inv = C.div(ONE, scale)
        out = [C.mul(v, inv) for v in out[:9]] + out[9:]
        world = C.mat34_set_pos_rot_z_scale(scale, pos, s16(s16(facing) + FACING_BIAS))
        return C.mat34_mul(out, world)

    def model_get_attach_matrix(self, scale, model, state, index):
        """model_getAttachMatrix 0x1795f8 (f12 scale, a0 model, a1 state or 0, a2 index,
        a3 out) -> 12 patterns: mat34_mul(rec + 4, J), then mat34_mul with
        mat3_scale(scale, identity) - the model-space matrix, no position or facing."""
        rec = attach_record(model, self.u8(model + 0x22), index)
        j = self.joint_or_identity(state, rec)
        out = C.mat34_mul(self.read_matrix(rec + 4), j)
        return C.mat34_mul(out, C.mat3_scale(scale, C.mat34_set_identity()))

    def creature_get_attach_matrix0(self, c):
        """creature_getAttachMatrix0 0x287940 (creature, out) -> 12 patterns:
        model_getAttachWorldMatrix(+0xdc scale, the class definition's model (+0x24 -> +0xc),
        a copy of the position +0x10, s16 facing +0x38, the anim state +0x114, index 0)."""
        return self.model_get_attach_world_matrix(self.u32(c + 0xDC), self.u32(self.u32(c + 0x24) + 0xC),
                                                  self.vec(c + 0x10), self.s16(c + 0x38), (c + 0x114) & M32,
                                                  ATTACH_INDEX_SOUL)

    # ---- entries that write the result through the out pointer, as the original does ----
    def _store(self, out, m):
        for k, v in enumerate(m):
            self.w32((out + 4 * k) & M32, v)

    def joint_matrix_entry(self, state, joint, out):
        self._store(out, self.anim_get_joint_matrix(state, joint))

    def world_matrix_entry(self, model, pos, facing, state, index, out, scale):
        self._store(out, self.model_get_attach_world_matrix(scale, model, pos, facing, state, index))

    def attach_matrix_entry(self, model, state, index, out, scale):
        self._store(out, self.model_get_attach_matrix(scale, model, state, index))

    def creature_matrix_entry(self, c, out):
        self._store(out, self.creature_get_attach_matrix0(c))


class Model(AttachBodies, RC.Model):
    """The bodies alone; anim_buildPose is the one callback."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return None


class SoulModel(AttachBodies, SR.Model):
    """tools/ref_soul_run.py's Soul_run with the two matrix call-outs of states 0x1d run as
    bodies (what tools/difftest_attach_matrix.py's second part executes)."""

    def call(self, name, *args):
        if name == 'creature_getAttachMatrix0':
            return tuple(self.creature_get_attach_matrix0(args[0] & M32))
        if name == 'model_getAttachMatrix':
            model, state, index, scale = (a & M32 for a in args)
            return tuple(self.model_get_attach_matrix(scale, model, state, index))
        return SR.Model.call(self, name, *args)


SOUL_EXTERNALS = dict(SR.EXTERNALS)
for _name in ('creature_getAttachMatrix0', 'model_getAttachMatrix'):
    del SOUL_EXTERNALS[_name]
SOUL_EXTERNALS.update(EXTERNALS)
