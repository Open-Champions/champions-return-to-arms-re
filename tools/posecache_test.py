#!/usr/bin/env python3
"""posecache_test.py - execute the skeleton pose cache (FINDINGS D34) and the proposed fix.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -I -B tools/posecache_test.py [path/to/SLUS_209.73] [-v]

What runs.  The game's own animation functions - anim_init, anim_push, anim_clear,
anim_syncToSimFrame, anim_advance, anim_buildPose, animtrack_decode, anim_getJointMatrix,
anim_emitPose, model_getAttachPoint - are executed by tools/ee_emu.py on animation states
this script builds.  The clips are synthetic (three joints, written here in the documented
.anm layout, docs/formats/anim-audio.md); no game data is embedded or read from the disc.

What is modelled, not executed.  ee_emu has no vector unit.  anim_buildPose hands each
joint to a 77-instruction VU0 microprogram (.vutext, 0x3e5c50).  This script reads that
microprogram's words from the executable and interprets them with a small VU0 model that
knows only the instruction forms the program uses (add, subtract, multiply and
multiply-add with broadcast, fixed/float conversion, MR32, LQ, SQ, LOI, B).  The nine COP2
instructions on the EE side (LQC2, QMTC2, CTC2, VCALLMS, QMFC2) are emulated at their
addresses.  Vector arithmetic uses ee_emu's FPU routines, which is an approximation of the
vector unit's own rounding; every comparison below is either exact equality of two runs of
the same arithmetic or a difference thousands of times larger than a rounding step.  If
the microprogram contains a form the model does not know, the script says so and checks
only the cache decisions (which pointer is attached, whether a build ran).

Every line is PASS or FAIL with a check id.  Nothing here shows that a state occurs in a
real game: one function at a time, state built by the script, no second machine.  "Machine
A / machine B" below are two runs that differ only in whether the draw call was made.
docs/issues/pose-cache.md explains each group.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu
from ee_emu import EE, EmuError, M32, M64, float_to_raw, raw_to_float

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- addresses (names.tsv / symbols) ---------------------------------------------------
ANIM_INIT, ANIM_PUSH, ANIM_CLEAR, ANIM_SYNC = 0x16F9A8, 0x170838, 0x1707B0, 0x1709F8
ANIM_ADVANCE, ANIM_BUILD, ANIM_QUERY, ANIM_EMIT = 0x16D748, 0x16ED40, 0x16F720, 0x16F880
ANIM_RELEASE, MODEL_ATTACH_POINT = 0x171118, 0x1754A0
BUILD_LO, BUILD_HI = 0x16ED40, 0x16F720
LIBC_MEMSET, LIBM_POWF = 0x3B60C0, 0x3A5AC8
VU0_CODE, VU0_COUNT = 0x3E5C50, 77
G_SIM_FRAME, G_DRAW_FRAME, G_EXCLUDE_MASK = 0x44FDCC, 0x44FDD0, 0x4039B8
POSE_POOL, POSE_SIZE, POSE_COUNT = 0x791EC0, 0x620, 100
POSE_TAIL, POSE_HEAD, POSE_DEFAULT, POSE_FALLBACK = 0x7B8340, 0x7B8344, 0x7B8380, 0x7B89C0
B_OWNER, B_PREV, B_NEXT, B_STAMP = 0x610, 0x614, 0x618, 0x61C
MASK_TICK, MASK_DRAW = 0x20000, 0x200000

# ---- the two patch variants (docs/issues/pose-cache.md section 8) ------------------------
CAVE = 0x257AB4                     # Cyclops_dropClub: no caller, no pointer (checked below)
CAVE_END = 0x257BA0
PATCH_GATED = [                     # PC-A: rebuild only inside the lockstep tick
    (0x16F73C, 0x14400004, 0x08095EAD),     # bnez v0, use  ->  j cave
    (CAVE + 0x00, 0x27BDFFB0, 0x10400007),  # beqz v0, build
    (CAVE + 0x04, 0x24020001, 0x3C030040),  # lui  v1, 0x40
    (CAVE + 0x08, 0xFFB00030, 0x8C6339B8),  # lw   v1, g_excludeMask
    (CAVE + 0x0C, 0x0080802D, 0x3C010002),  # lui  at, 2
    (CAVE + 0x10, 0xFFB10038, 0x14610005),  # bne  v1, at, use
    (CAVE + 0x14, 0x0000882D, 0x00000000),  # nop
    (CAVE + 0x18, 0x14A2000F, 0xAC400610),  # sw   zero, 0x610(v0)   buffer owner
    (CAVE + 0x1C, 0xFFBF0040, 0xAE000000),  # sw   zero, 0(s0)       state pointer
    (CAVE + 0x20, 0x8E020024, 0x0805BDD1),  # j    0x16f744          build
    (CAVE + 0x24, 0x8E0500E8, 0x00000000),  # nop
    (CAVE + 0x28, 0x0C05E554, 0x0805BDD4),  # j    0x16f750          use the attached pose
    (CAVE + 0x2C, 0x8C44000C, 0x00000000),  # nop
]
PATCH_ALWAYS = [                    # PC-B: every query rebuilds, six words in place
    (0x16F73C, 0x14400004, 0x54400001),     # bnezl v0, +1
    (0x16F740, 0x00C0882D, 0xAC400610),     # sw    zero, 0x610(v0)
    (0x16F744, 0x0C05BB50, 0x00C0882D),     # move  s1, a2
    (0x16F748, 0x0000282D, 0x0C05BB50),     # jal   anim_buildPose
    (0x16F74C, 0x8E020000, 0x0000282D),     # move  a1, zero
    (0x16F750, 0x0040402D, 0x8E080000),     # lw    t0, 0(s0)
]

VERBOSE = False
RESULTS = []


def check(ident, ok, text):
    RESULTS.append((ident, bool(ok)))
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    return bool(ok)


def note(text):
    if VERBOSE:
        print('         ' + text)


# ---------------------------------------------------------------------------------------
# A VU0 model for exactly the instruction forms the pose microprogram uses
# ---------------------------------------------------------------------------------------
class VuUnknown(Exception):
    pass


ONE = 0x3F800000


class VU0:
    def __init__(self, mem):
        self.code = [(mem.u32(VU0_CODE + 8 * i), mem.u32(VU0_CODE + 8 * i + 4))
                     for i in range(VU0_COUNT)]
        self.vf = [[0, 0, 0, 0] for _ in range(32)]
        self.vf[0] = [0, 0, 0, ONE]
        self.acc = [0, 0, 0, 0]
        self.vi = [0] * 16
        self.i_reg = 0
        self.mem = [[0, 0, 0, 0] for _ in range(256)]
        self.executed = 0
        for index in range(VU0_COUNT):          # refuse early if a form is not modelled
            lower, upper = self.code[index]
            self._upper(upper, dry=True)
            if not upper & 0x80000000:
                self._lower(lower, index, dry=True)

    @staticmethod
    def _add(a, b):
        return ee_emu.fp_add(a, b)

    @staticmethod
    def _sub(a, b):
        return ee_emu.fp_sub(a, b)

    @staticmethod
    def _mul(a, b):
        return ee_emu.fp_mul(a, b)

    def _upper(self, w, dry=False):
        """Returns ('vf', index, mask, values) / ('acc', mask, values) / None."""
        op = w & 0x3F
        mask = (w >> 21) & 15
        ft, fs, fd = (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31
        comps = [i for i in range(4) if mask & (8 >> i)]
        vf = self.vf

        def per(fn):
            return None if dry else [fn(i) if i in comps else None for i in range(4)]

        if op < 0x1C:
            kind, bc = op & 0x3C, op & 3
            if dry:
                if kind not in (0x00, 0x04, 0x08, 0x0C, 0x18):
                    raise VuUnknown('upper opcode 0x%02x' % op)
                return None
            t = vf[ft][bc]
            if kind == 0x00:
                return ('vf', fd, per(lambda i: self._add(vf[fs][i], t)))
            if kind == 0x04:
                return ('vf', fd, per(lambda i: self._sub(vf[fs][i], t)))
            if kind == 0x18:
                return ('vf', fd, per(lambda i: self._mul(vf[fs][i], t)))
            if kind == 0x08:
                return ('vf', fd, per(lambda i: self._add(self.acc[i], self._mul(vf[fs][i], t))))
            return ('vf', fd, per(lambda i: self._sub(self.acc[i], self._mul(vf[fs][i], t))))
        if op == 0x1E:                                                  # MULi
            return None if dry else ('vf', fd, per(lambda i: self._mul(vf[fs][i], self.i_reg)))
        if op == 0x28:
            return None if dry else ('vf', fd, per(lambda i: self._add(vf[fs][i], vf[ft][i])))
        if op == 0x2C:
            return None if dry else ('vf', fd, per(lambda i: self._sub(vf[fs][i], vf[ft][i])))
        if op == 0x2A:
            return None if dry else ('vf', fd, per(lambda i: self._mul(vf[fs][i], vf[ft][i])))
        if op >= 0x3C:
            sp = (fd << 2) | (w & 3)
            if sp == 0x2F:
                return None
            if sp < 0x10 or 0x18 <= sp < 0x1C:
                kind, bc = sp & 0x3C, sp & 3
                if dry:
                    if kind not in (0x00, 0x04, 0x08, 0x0C, 0x18):
                        raise VuUnknown('upper special 0x%02x' % sp)
                    return None
                t = vf[ft][bc]
                if kind == 0x18:
                    return ('acc', per(lambda i: self._mul(vf[fs][i], t)))
                if kind == 0x00:
                    return ('acc', per(lambda i: self._add(vf[fs][i], t)))
                if kind == 0x04:
                    return ('acc', per(lambda i: self._sub(vf[fs][i], t)))
                if kind == 0x08:
                    return ('acc', per(lambda i: self._add(self.acc[i], self._mul(vf[fs][i], t))))
                return ('acc', per(lambda i: self._sub(self.acc[i], self._mul(vf[fs][i], t))))
            if 0x10 <= sp <= 0x13:                                      # ITOF0/4/12/15
                scale = float_to_raw(1.0 / (1 << (0, 4, 12, 15)[sp - 0x10]))
                return None if dry else (
                    'vf', ft, per(lambda i: self._mul(ee_emu.fp_from_int(vf[fs][i]), scale)))
            if 0x14 <= sp <= 0x17:                                      # FTOI0/4/12/15
                scale = float_to_raw(float(1 << (0, 4, 12, 15)[sp - 0x14]))
                return None if dry else (
                    'vf', ft, per(lambda i: ee_emu.fp_to_int(self._mul(vf[fs][i], scale)) & M32))
            raise VuUnknown('upper special 0x%02x' % sp)
        raise VuUnknown('upper opcode 0x%02x' % op)

    def _lower(self, w, pc, dry=False):
        """Returns ('vf', index, values) / ('mem', address, values) / ('branch', target) / None."""
        op = w >> 25
        mask = (w >> 21) & 15
        it, is_ = (w >> 16) & 31, (w >> 11) & 31
        imm = w & 0x7FF
        imm = imm - 0x800 if imm & 0x400 else imm
        comps = [i for i in range(4) if mask & (8 >> i)]
        if op == 0x00:                                                  # LQ
            if dry:
                return None
            src = self.mem[(self.vi[is_ & 15] + imm) & 0xFF]
            return ('vf', it, [src[i] if i in comps else None for i in range(4)])
        if op == 0x01:                                                  # SQ
            if dry:
                return None
            return ('mem', (self.vi[it & 15] + imm) & 0xFF,
                    [self.vf[is_][i] if i in comps else None for i in range(4)])
        if op == 0x20:                                                  # B
            return ('branch', (pc + 1 + imm) % 512)
        if op == 0x40 and (w & 0x3F) >= 0x3C:
            sp = (((w >> 6) & 31) << 2) | (w & 3)
            if sp == 0x30:                                              # MOVE (the lower NOP)
                return None if dry else (
                    'vf', it, [self.vf[is_][i] if i in comps else None for i in range(4)])
            if sp == 0x31:                                              # MR32
                if dry:
                    return None
                s = self.vf[is_]
                rotated = [s[1], s[2], s[3], s[0]]
                return ('vf', it, [rotated[i] if i in comps else None for i in range(4)])
            raise VuUnknown('lower special 0x%02x' % sp)
        raise VuUnknown('lower opcode 0x%02x' % op)

    def _apply(self, result):
        if result is None:
            return None
        if result[0] == 'vf':
            _, index, values = result
            if index:
                for i in range(4):
                    if values[i] is not None:
                        self.vf[index][i] = values[i] & M32
        elif result[0] == 'acc':
            for i in range(4):
                if result[1][i] is not None:
                    self.acc[i] = result[1][i] & M32
        elif result[0] == 'mem':
            _, address, values = result
            for i in range(4):
                if values[i] is not None:
                    self.mem[address][i] = values[i] & M32
        elif result[0] == 'branch':
            return result[1]
        return None

    def run(self, start):
        pc, pending, ending = start, None, False
        for _ in range(2000):
            lower, upper = self.code[pc]
            up_result = self._upper(upper)                  # both halves read the old state
            if upper & 0x80000000:
                self.i_reg, lo_result = lower, None
            else:
                lo_result = self._lower(lower, pc)
            self._apply(up_result)
            target = self._apply(lo_result)
            self.executed += 1
            next_pc = pc + 1
            if pending is not None:
                next_pc, pending = pending, None
            if target is not None:
                pending = target
            if ending:
                return
            if upper & 0x40000000:
                ending = True
            pc = next_pc
        raise VuUnknown('microprogram did not end')


def install_cop2(emu, vu):
    """Emulate the EE-side COP2 instructions of anim_buildPose at their addresses."""
    handled = []
    for addr in range(BUILD_LO, BUILD_HI, 4):
        w = emu.mem.u32(addr)
        op = w >> 26
        if op not in (0x12, 0x36, 0x3E):
            continue
        rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31

        def hook(e, addr=addr, w=w, op=op, rs=rs, rt=rt, rd=rd):
            if op == 0x36:                                              # LQC2 vf[rt], off(rs)
                base = (e.r[rs] + ee_emu.sx16(w)) & M32
                if rt:
                    vu.vf[rt] = [e.mem.u32(base + 4 * i) for i in range(4)]
            elif w & 0x02000000:
                if (w & 0x3F) != 0x38:
                    raise VuUnknown('COP2 macro instruction 0x%08x at 0x%x' % (w, addr))
                vu.run((w >> 6) & 0x7FFF)                               # VCALLMS
            elif rs == 5:                                               # QMTC2
                lo64, hi64 = e.r[rt], e.rh[rt]
                if rd:
                    vu.vf[rd] = [lo64 & M32, (lo64 >> 32) & M32, hi64 & M32, (hi64 >> 32) & M32]
            elif rs == 1:                                               # QMFC2
                v = vu.vf[rd]
                e.r[rt] = (v[0] | (v[1] << 32)) & M64
                e.rh[rt] = (v[2] | (v[3] << 32)) & M64
            elif rs == 6:                                               # CTC2
                if rd < 16:
                    vu.vi[rd] = e.r[rt] & 0xFFFF
            else:
                raise VuUnknown('COP2 instruction 0x%08x at 0x%x' % (w, addr))
            e.jump(addr + 4)
        emu.hook(addr, hook)
        handled.append(addr)
    return handled


# ---------------------------------------------------------------------------------------
# Synthetic clips in the documented .anm layout
# ---------------------------------------------------------------------------------------
class BitWriter:
    def __init__(self):
        self.bits = []

    def put(self, value, width):
        value &= (1 << width) - 1
        self.bits += [(value >> i) & 1 for i in range(width - 1, -1, -1)]

    def data(self):
        bits = self.bits + [0] * (-len(self.bits) % 32)
        out = bytearray()
        for i in range(0, len(bits), 16):
            word = 0
            for bit in bits[i:i + 16]:
                word = (word << 1) | bit
            out += struct.pack('<H', word)
        return bytes(out)


def make_clip(emu, length, joints, keys):
    """joints: [(depth, bind offset xyz in 1/64, position xyz in units, quaternion wxyz)].
    keys: [(tick, 'pos' | 'rot', joint, values)] sorted by tick; position velocities in
    1/256 unit per tick, rotation velocities in 1/131072 per tick.  Returns the address."""
    stream = BitWriter()
    for _depth, _bind, pos, quat in joints:
        stream.put(15, 4)
        for v in pos:
            stream.put(int(round(v * 64)), 16)
        stream.put(15, 4)
        for v in quat:
            stream.put(int(round(v * 4096)), 16)
    tick = 0
    for at, kind, joint, values in keys:
        stream.put(at - tick, 8)
        tick = at
        stream.put(1 if kind == 'pos' else 0, 1)
        stream.put(joint, 6)
        stream.put(15, 4)
        for v in values:
            stream.put(v, 16)
    stream.put(255, 8)
    key_data = stream.data() + bytes(16)
    count = len(joints)
    depth_bytes = bytes(d for d, _b, _p, _q in joints) + bytes(-count % 8)   # ld needs 8
    bind = b''.join(struct.pack('<4h', b[0], b[1], b[2], 0) for _d, b, _p, _q in joints)
    size = 0x70 + len(depth_bytes) + len(bind) + len(key_data)
    addr = emu.alloc(size + 0x40)
    depth_at = addr + 0x70
    bind_at = depth_at + len(depth_bytes)
    keys_at = bind_at + len(bind)
    header = bytearray(0x70)
    struct.pack_into('<5I', header, 0, count, length, keys_at, bind_at, depth_at)
    emu.mem.write(addr, bytes(header) + depth_bytes + bind + key_data)
    return addr


IDENT = (1.0, 0.0, 0.0, 0.0)
HALF = 0.70710678


def clip_idle(emu):
    """Clip A: an upright chain whose middle joint turns and whose tip slides."""
    return make_clip(emu, 200, [(0, (0, 0, 0), (0, 0, 45), IDENT),
                                (1, (0, 0, 0), (10, 0, 0), IDENT),
                                (2, (64, 0, 0), (8, 0, 0), IDENT)],
                     [(0, 'rot', 1, (0, 0, 0, 2000)), (0, 'pos', 2, (0, 64, 0))])


def clip_attack(emu):
    """Clip B: the same skeleton in a clearly different pose."""
    return make_clip(emu, 120, [(0, (0, 0, 0), (0, 0, 30), (HALF, 0, 0, HALF)),
                                (1, (0, 0, 0), (0, 12, 0), IDENT),
                                (2, (64, 0, 0), (0, 0, 9), IDENT)],
                     [(0, 'rot', 2, (0, 1500, 0, 0))])


# ---------------------------------------------------------------------------------------
# One "machine": an interpreter with the animation pools initialised
# ---------------------------------------------------------------------------------------
class Machine:
    def __init__(self, elf, patch=None):
        emu = self.emu = EE(elf)
        mem = emu.mem

        def memset(e):
            dst, value, size = e.r[4] & M32, e.r[5] & 0xFF, e.r[6] & M32
            e.mem.write(dst, bytes([value]) * size)
            return dst
        emu.stub(LIBC_MEMSET, function=memset)
        emu.stub(LIBM_POWF, ret=None)
        self.vu = VU0(mem)
        self.cop2 = install_cop2(emu, self.vu)
        emu.call(ANIM_INIT)
        if patch:
            for addr, _old, new in patch:
                emu.patch(addr, new)
        self.clip_a, self.clip_b = clip_idle(emu), clip_attack(emu)
        self.root = emu.alloc(16)
        self.out = emu.alloc(0x40)
        self.dl = emu.alloc(0x4000)
        self.cursor = emu.alloc(16)
        self.pos, self.pos_out, self.dir_out = emu.alloc(16), emu.alloc(16), emu.alloc(16)
        self.model = emu.alloc(0x100)       # one attach record: joint 2, offset (0, 5, 0)
        mem.w8(self.model + 0x22, 4)
        mem.w32(self.model + 0x40, 2)
        mem.wf32(self.model + 0x40 + 0x10, 1.0)
        mem.wf32(self.model + 0x40 + 0x2C, 5.0)
        for i, v in enumerate((1000.0, 2000.0, 30.0)):
            mem.wf32(self.pos + 4 * i, v)
        mem.w32(G_DRAW_FRAME, 1000)
        mem.w32(G_SIM_FRAME, 500)
        mem.w32(G_EXCLUDE_MASK, MASK_TICK)
        self.builds = 0

    # -- state helpers
    def new_state(self, clip, steps=1):
        state = self.emu.alloc(0x110)
        self.emu.mem.w8(state + 5, 8)
        self.emu.call(ANIM_PUSH, state, clip, 1)
        for _ in range(steps):
            self.step(state)
        return state

    def step(self, state):
        self.emu.call(ANIM_ADVANCE, state, 0, self.root, 0, fargs=(1.0,))

    def pose(self, state):
        return self.emu.mem.u32(state)

    def top_time(self, state):
        count = self.emu.mem.s8(state + 4)
        return self.emu.mem.f32(state + 8 + (count - 1) * 0x20 + 0x18)

    def query(self, state, joint=2):
        """anim_getJointMatrix: returns (12 floats, number of anim_buildPose calls)."""
        emu = self.emu
        emu.reset_log()
        emu.call(ANIM_QUERY, state, joint, self.out)
        built = sum(1 for c in emu.calls if c.target == ANIM_BUILD)
        self.builds += built
        return tuple(emu.mem.f32(self.out + 4 * i) for i in range(12)), built

    def attach_point(self, state):
        emu = self.emu
        emu.call(MODEL_ATTACH_POINT, self.model, self.pos, 0x2000, state, 0, self.pos_out, 0,
                 fargs=(1.0,))
        return tuple(emu.mem.f32(self.pos_out + 4 * i) for i in range(3))

    def draw(self, state):
        """anim_emitPose as the draw pass calls it; returns the buffer the display list
        was pointed at (the DMA tag's address field)."""
        emu, mem = self.emu, self.emu.mem
        mem.w32(G_EXCLUDE_MASK, MASK_DRAW)
        mem.w32(self.cursor, self.dl)
        emu.call(ANIM_EMIT, self.cursor, state)
        mem.w32(G_EXCLUDE_MASK, MASK_TICK)
        return (mem.u64(self.dl) >> 32) & M32

    def next_picture(self):
        self.emu.mem.w32(G_DRAW_FRAME, self.emu.mem.u32(G_DRAW_FRAME) + 1)

    def set_tracks_to(self, state, clip):
        self.emu.call(ANIM_CLEAR, state)
        self.emu.call(ANIM_PUSH, state, clip, 1)

    def sync(self, state, frame):
        self.emu.mem.w32(G_SIM_FRAME, frame)
        self.emu.call(ANIM_SYNC, state)

    def release(self, state):
        self.emu.call(ANIM_RELEASE, state)

    def stamp_all(self, value):
        for i in range(POSE_COUNT):
            self.emu.mem.w32(POSE_POOL + i * POSE_SIZE + B_STAMP, value)

    def stamp_some(self, count, value):
        """Give the `count` buffers nearest the old end of the list a recent stamp."""
        mem, buf, done = self.emu.mem, self.emu.mem.u32(POSE_HEAD), 0
        while buf and done < count:
            mem.w32(buf + B_STAMP, value)
            buf, done = mem.u32(buf + B_NEXT), done + 1

    def owners_consistent(self):
        """Every pooled buffer with an owner is the buffer that owner points at."""
        mem = self.emu.mem
        for buf in [POSE_POOL + i * POSE_SIZE for i in range(POSE_COUNT)] + [POSE_FALLBACK]:
            owner = mem.u32(buf + B_OWNER)
            if owner and mem.u32(owner) != buf:
                return False
        return True


def diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def fmt(values):
    return '(' + ', '.join('%.3f' % v for v in values) + ')'


def expected_tip(time):
    """Clip A, joint 2, translation of the matrix the query returns, worked out from the
    clip definition: the tip's world position plus the rotated bind offset (1, 0, 0)."""
    import math
    z = 2000.0 * time / 131072.0
    norm = math.sqrt(1.0 + z * z)
    w, z = 1.0 / norm, z / norm
    cos_t, sin_t = w * w - z * z, 2.0 * w * z
    lx, ly = 8.0, 0.25 * time
    px, py = 10.0 + cos_t * lx - sin_t * ly, sin_t * lx + cos_t * ly
    return (px + cos_t * 1.0, py + sin_t * 1.0, 45.0)


# ---------------------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------------------
def group_a(elf):
    """(a) a query after a step is a fresh build."""
    m = Machine(elf)
    check('a0', len(m.cop2) == 9 and m.vu.executed == 0,
          'anim_buildPose has 9 COP2 instructions and every form of the 77-instruction VU0 '
          'program is modelled (found %d)' % len(m.cop2))
    state = m.new_state(m.clip_a, steps=30)
    check('a1', m.pose(state) == 0, 'after anim_advance nothing is attached to the state')
    first, built = m.query(state)
    check('a2', built == 1 and m.pose(state) != 0,
          'the first query after a step calls anim_buildPose once and leaves a buffer attached')
    stamp = m.emu.mem.s32(m.pose(state) + B_STAMP)
    check('a3', stamp == 0 and m.emu.mem.u32(m.pose(state) + B_OWNER) == state
          and m.emu.mem.u32(POSE_TAIL) == m.pose(state),
          'a simulation build does not stamp its buffer (stamp %d with g_drawFrame 1000), '
          'records the owner and moves the buffer to the recent end' % stamp)
    second, built = m.query(state)
    check('a4', built == 0 and second == first, 'a second query without a step builds nothing')
    want = expected_tip(m.top_time(state))
    got = first[9:12]
    check('a5', diff(want, got) < 0.05,
          'joint 2 of the synthetic clip at time %.1f comes out at %s, the clip definition '
          'gives %s (decoder, blend and VU0 model agree to 1/64 unit steps)'
          % (m.top_time(state), fmt(got), fmt(want)))
    other = Machine(elf)                        # decoder history: jump there in one go
    jumped = other.new_state(other.clip_a, steps=0)
    other.emu.mem.wf32(jumped + 8 + 0x18, m.top_time(state))
    direct, _ = other.query(jumped)
    check('a6', direct == first,
          'the same track time reached by 30 steps or set directly gives bit-identical '
          'matrices (the decoder slot history does not show)')
    m.step(state)
    check('a7', m.pose(state) == 0 and m.owners_consistent(),
          'the next step detaches the pose and clears the buffer owner')


def run_change(elf, drawn, change, patch=None, step_before_query=False):
    """One machine: step, optional draw, track change without a step, query."""
    m = Machine(elf, patch)
    state = m.new_state(m.clip_a, steps=30)
    table = None
    if drawn:
        table = m.draw(state)
    if change == 'push':
        m.set_tracks_to(state, m.clip_b)
    elif change == 'sync':
        m.sync(state, 7)
    if step_before_query:
        m.step(state)
    matrix, built = m.query(state)
    return m, state, matrix, built, table, m.attach_point(state)


def group_b(elf):
    """(b) a draw-built pose survives a track change; the undrawn machine builds fresh."""
    m, state, before, _built, _t, before_point = run_change(elf, False, None)
    for ident, change, label in (('b1', 'push', 'anim_clear + anim_push of another clip'),
                                 ('b4', 'sync', 'anim_syncToSimFrame (frame 7)')):
        ma, sa, fresh, built_a, _ta, point_a = run_change(elf, False, change)
        mb, sb, stale, built_b, table, point_b = run_change(elf, True, change)
        check(ident, built_a == 1 and built_b == 0 and table == mb.pose(sb)
              and mb.emu.mem.s32(table + B_STAMP) == 1000,
              '%s: the machine that drew queries without building (its buffer carries the '
              'draw stamp), the machine that did not draw builds' % label)
        check(ident[0] + str(int(ident[1]) + 1), stale == before and stale != fresh,
              'drawn machine returns the pose from BEFORE the change, undrawn machine the '
              'pose after it: joint matrix differs by up to %.2f, attach point %s against %s'
              % (diff(stale, fresh), fmt(point_b), fmt(point_a)))
        _m1, _s1, c1, _b1, _t1, _p1 = run_change(elf, False, change, step_before_query=True)
        _m2, _s2, c2, _b2, _t2, _p2 = run_change(elf, True, change, step_before_query=True)
        check(ident[0] + str(int(ident[1]) + 2), c1 == c2,
              'control: with an animation step between the change and the query both '
              'machines return the same matrix')
    note('before the change: tip %s, attach point %s' % (fmt(before[9:12]), fmt(before_point)))
    # a pose built by a simulation query is kept by the draw (the draw builds nothing)
    m = Machine(elf)
    state = m.new_state(m.clip_a, steps=30)
    sim_pose, _ = m.query(state)
    buffer_before = m.pose(state)
    table = m.draw(state)
    check('b7', table == buffer_before and m.emu.mem.s32(buffer_before + B_STAMP) == 1000,
          'a pose attached by a simulation query is what the draw sends and stamps; the '
          'draw does not build its own')


def group_c(elf):
    """(c) no free buffer: the static fallback buffer and what staleness then depends on."""
    m = Machine(elf)
    x = m.new_state(m.clip_a, steps=30)
    y = m.new_state(m.clip_b, steps=10)
    x_fresh, _ = m.query(x)
    y_fresh, _ = m.query(y)
    m.step(x)
    m.step(y)                                   # same time +1; rebuild references below
    x_ref, _ = m.query(x)
    y_ref, _ = m.query(y)
    m.release(x)
    m.release(y)
    m.stamp_all(1000)                           # every pooled buffer drawn this picture
    got_x, built = m.query(x)
    mem = m.emu.mem
    check('c1', built == 1 and m.pose(x) == POSE_FALLBACK and mem.u32(POSE_FALLBACK + B_OWNER) == x
          and got_x == x_ref,
          'with all 100 buffers stamped recent a simulation query builds into the static '
          'buffer 0x7b89c0 and the values are the same as from a pooled buffer')
    got_y, built = m.query(y)
    check('c2', built == 1 and m.pose(y) == POSE_FALLBACK and m.pose(x) == 0
          and mem.u32(POSE_FALLBACK + B_OWNER) == y and got_y == y_ref,
          'a second state queried in the same tick takes the static buffer over: the first '
          'state\'s pointer is zeroed before the buffer is overwritten')
    again_x, built = m.query(x)
    check('c3', built == 1 and again_x == x_ref and again_x != y_ref and m.pose(y) == 0,
          'a later query on the first state rebuilds and returns its own pose, not the '
          'second object\'s')
    table = m.draw(x)
    check('c4', table != POSE_FALLBACK and m.pose(x) != POSE_FALLBACK,
          'anim_emitPose never sends the static buffer: it detaches it and, with no buffer '
          'free, draws the default pose 0x%x' % table)

    # staleness then depends on whether the pool was exhausted on this machine
    results = {}
    for name, exhausted in (('free', False), ('exhausted', True)):
        m = Machine(elf)
        x = m.new_state(m.clip_a, steps=30)
        y = m.new_state(m.clip_b, steps=10)
        if exhausted:
            m.stamp_all(1000)
        m.query(x)
        m.set_tracks_to(x, m.clip_b)
        m.query(y)
        results[name] = m.query(x)
    check('c5', results['free'][1] == 0 and results['exhausted'][1] == 1
          and results['free'][0] != results['exhausted'][0],
          'query X, change X\'s tracks, query Y, query X: with buffers free X gets the pose '
          'from before the change; on a machine whose pool is exhausted Y took the static '
          'buffer and X is rebuilt (matrix differs by %.2f)'
          % diff(results['free'][0], results['exhausted'][0]))

    # how long an undrawn simulation-built pose survives
    for ident, recent in (('c6', 0), ('c7', 60)):
        m = Machine(elf)
        x = m.new_state(m.clip_a, steps=30)
        y = m.new_state(m.clip_b, steps=10)
        m.stamp_some(recent, 1000)
        m.query(x)
        count = 0
        while m.pose(x) and count < 300:
            m.release(y)
            m.query(y)
            count += 1
        check(ident, count == 100 - recent,
              'with %d buffers stamped recent, an undrawn pose built by a query is taken '
              'by the %dth later build (expected 100 - %d)' % (recent, count, recent))
    m = Machine(elf)
    x = m.new_state(m.clip_a, steps=30)
    y = m.new_state(m.clip_b, steps=10)
    m.query(x)
    for _ in range(150):
        m.draw(x)                               # the machine that draws X re-stamps it
        m.next_picture()
        m.release(y)
        m.query(y)
    check('c8', m.pose(x) != 0,
          'on a machine that draws the object every picture the same pose is still attached '
          'after 150 pictures and 150 other builds')


def patch_words_ok(elf, patch):
    emu = EE(elf)
    return all(emu.mem.u32(addr) == old for addr, old, _new in patch)


def cave_unreferenced(elf):
    """No jump, call, branch or stored pointer anywhere in the loaded image leads into the
    function used as the code cave."""
    segments, _entry = ee_emu.load_elf_segments(elf)
    hits = []
    for vaddr, blob, _memsz in segments:
        for off in range(0, len(blob) - 3, 4):
            word = struct.unpack_from('<I', blob, off)[0]
            addr = vaddr + off
            inside = CAVE <= addr < CAVE_END
            if CAVE <= word < CAVE_END:
                hits.append(addr)
            op = word >> 26
            if op in (2, 3):
                target = ((addr + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
                if CAVE <= target < CAVE_END and not inside:
                    hits.append(addr)
            elif vaddr == 0x100000 and (op in (1, 4, 5, 6, 7, 20, 21, 22, 23)
                                        or (op == 17 and ((word >> 21) & 31) == 8)):
                target = addr + 4 + ee_emu.sx16(word) * 4
                if CAVE <= target < CAVE_END and not inside:
                    hits.append(addr)
    return hits


def group_d(elf):
    """(d) the patches: the per-machine difference disappears, drawing still gets a pose."""
    hits = cave_unreferenced(elf)
    check('d0', not hits,
          'no call, jump, branch or pointer word in the loaded image leads into '
          '0x%x-0x%x (Cyclops_dropClub), the code cave%s'
          % (CAVE, CAVE_END - 1, '' if not hits else ': ' + ', '.join('0x%x' % h for h in hits)))
    for tag, name, patch in (('e', 'PC-A (rebuild inside the tick only)', PATCH_GATED),
                             ('f', 'PC-B (rebuild always, in place)', PATCH_ALWAYS)):
        check(tag + '0', patch_words_ok(elf, patch),
              '%s: all %d original words quoted for it are the words in the executable'
              % (name, len(patch)))
        for ident, change in ((tag + '1', 'push'), (tag + '2', 'sync')):
            ma, sa, fresh_orig, _b, _t, _p = run_change(elf, False, change)
            m1, s1, undrawn, b1, _t1, p1 = run_change(elf, False, change, patch)
            m2, s2, drawn, b2, table, p2 = run_change(elf, True, change, patch)
            check(ident, undrawn == drawn == fresh_orig and p1 == p2 and b2 == 1
                  and m2.owners_consistent()
                  and m2.emu.mem.u32(table + B_OWNER) == 0 and m2.pose(s2) != table,
                  '%s, %s: drawn and undrawn machine return the same matrix and attach '
                  'point, equal to the unpatched fresh build; the draw-built buffer is left '
                  'unowned and no owner field dangles' % (name.split(' ')[0], change))
        # drawing still gets a pose, and the buffer the picture uses is not overwritten
        m = Machine(elf, patch)
        state = m.new_state(m.clip_a, steps=30)
        table1 = m.draw(state)
        snapshot = m.emu.mem.read(table1, 0x60)
        m.set_tracks_to(state, m.clip_b)
        m.query(state)
        table2 = m.draw(state)
        check(tag + '3', table1 not in (0, POSE_DEFAULT) and table2 == m.pose(state)
              and table2 not in (table1, POSE_DEFAULT) and m.emu.mem.read(table1, 0x60) == snapshot
              and m.emu.mem.s32(table1 + B_STAMP) == 1000 and m.emu.mem.s32(table2 + B_STAMP) == 1000,
              '%s: the draw before and the draw after a patched query each send an attached, '
              'stamped buffer; the first one keeps its contents (it is still reserved by '
              'its stamp)' % name.split(' ')[0])
        # the old buffer can be taken by somebody else without touching this state
        y = m.new_state(m.clip_b, steps=10)
        m.emu.mem.w32(G_DRAW_FRAME, 1010)
        pointer = m.pose(state)
        for _ in range(120):
            m.release(y)
            m.emu.mem.w32(G_EXCLUDE_MASK, MASK_DRAW)
            m.query(y)
            m.emu.mem.w32(G_EXCLUDE_MASK, MASK_TICK)
        check(tag + '4', m.owners_consistent() and m.pose(state) in (pointer, 0),
              '%s: 120 further builds recycle the pool with every owner field still naming '
              'a state that points back at its buffer' % name.split(' ')[0])
        # exhaustion case of c5
        results = []
        for exhausted in (False, True):
            m = Machine(elf, patch)
            x = m.new_state(m.clip_a, steps=30)
            y = m.new_state(m.clip_b, steps=10)
            if exhausted:
                m.stamp_all(1000)
            m.query(x)
            m.set_tracks_to(x, m.clip_b)
            m.query(y)
            results.append(m.query(x)[0])
        check(tag + '5', results[0] == results[1],
              '%s: the sequence of c5 gives the same matrix whether or not the pool is '
              'exhausted' % name.split(' ')[0])
        # cost: builds per query
        m = Machine(elf, patch)
        state = m.new_state(m.clip_a, steps=30)
        in_tick = sum(m.query(state)[1] for _ in range(5))
        m.emu.mem.w32(G_EXCLUDE_MASK, MASK_DRAW)
        in_draw = sum(m.query(state)[1] for _ in range(5))
        m.emu.mem.w32(G_EXCLUDE_MASK, 0)
        offline = sum(m.query(state)[1] for _ in range(5))
        want = (5, 0, 0) if patch is PATCH_GATED else (5, 5, 5)
        check(tag + '6', (in_tick, in_draw, offline) == want,
              '%s: five queries in a row build %d times inside the tick (mask 0x20000), '
              '%d times in the draw / prediction phase (0x200000), %d times with the mask at '
              'its offline value 0 (unpatched: 1, 0, 0)'
              % (name.split(' ')[0], in_tick, in_draw, offline))


GROUPS = (('a', 'a query after a step is a fresh build', group_a),
          ('b', 'a draw-built pose survives a track change', group_b),
          ('c', 'buffer exhaustion and the static buffer', group_c),
          ('d', 'the two patch variants', group_d))


def find_elf(positional):
    for arg in positional:
        if os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), os.path.join(ROOT, 'SLUS_209.73'),
                      'SLUS_209.73'):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    global VERBOSE
    argv = sys.argv[1:] if argv is None else list(argv)
    VERBOSE = '-v' in argv
    elf = find_elf([a for a in argv if not a.startswith('-')])
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path, or set CHAMPIONS_ELF); nothing was run')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable these addresses belong to '
              '(SHA-256 %s); nothing was run' % (elf, digest))
        return 0
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    print('executed in isolation: the game\'s animation functions on synthetic clips; the VU0 '
          'pose microprogram is interpreted by a model in this script')
    for letter, title, function in GROUPS:
        print('--- %s. %s' % (letter, title))
        try:
            function(elf)
        except VuUnknown as exc:
            check(letter + '!', False, 'the VU0 model does not cover this program: %s' % exc)
        except EmuError as exc:
            check(letter + '!', False, 'the interpreter stopped: %s' % exc)
        except (AssertionError, LookupError, ValueError, struct.error) as exc:
            check(letter + '!', False, 'this script could not finish the group: %r' % (exc,))
    passed = sum(1 for _, ok in RESULTS if ok)
    print('%d checks: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
