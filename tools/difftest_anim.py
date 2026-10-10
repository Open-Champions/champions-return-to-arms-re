#!/usr/bin/env python3
"""difftest_anim.py - compare tools/ref_anim.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00) and a directory of .anm files extracted from your
own disc (entries of the .LMP lumps; tools/gob.py unpacks them).  Without either the
script says so and exits 0.

  python3 tools/difftest_anim.py [path/to/SLUS_209.73] <dir with .anm files>
                                 [--quick] [--all] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the samples
    --all     run the decoder property over every clip in the directory (slow)
    --seed N  seed of the random choices (default 20973); one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL functions are executed by tools/ee_emu.py (an instruction interpreter,
    not a console) on memory this script prepares: the clip files are copied in and
    relocated by the game's own anm_relocate, the pools are set up by the game's own
    anim_init, and every operation (push, start, stop, advance, query, draw ...) is applied
    to the original and to the model.  After each operation the original's memory is
    compared BYTE FOR BYTE with an image built from the model: the whole state structure
    (header and every track cell, stale ones included), the decoder slots of its tracks,
    the returned event bits, the root-motion floats (as 32-bit patterns) and the yaw.  At
    intervals and at the end of each sequence all 165 decoder slots (0xf1c bytes each),
    both list orders, the pose buffers, the sound-cue table and the random seed are
    compared too.

    "Bit for bit" therefore means: identical under the interpreter's floating-point model.
    The default model gets the full sample; the properties are then repeated on a smaller
    sample under the three other adder models and with the multiplier-bias and
    divide-rounding switches (docs/issues/dynamic-tests.md, "Floating point").

The vector unit
    anim_buildPose composes the joint matrices with a 77-instruction VU0 microprogram
    (0x3e5c50) reached through COP2 instructions, which ee_emu does not implement.  This
    script supplies them: the seven COP2 instructions of anim_buildPose are hooked at their
    addresses, and class Vu0 below interprets the microprogram's own instruction words,
    read from your executable (only the instruction forms that program uses).  Its adder
    and multiplier are the interpreter's FPU routines; whether the real vector unit rounds
    the same way in every last bit is not established.  The pose properties thus show that
    the model performs the microprogram's operations in the microprogram's order.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError, M32, M64       # noqa: E402
import ref_core as C                            # noqa: E402
import ref_anim as A                            # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'all': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
COVER = {}                      # what the random sequences actually reached


def cover(what, count=1):
    if count:
        COVER[what] = COVER.get(what, 0) + count

# ---- addresses in SLUS_209.73 -----------------------------------------------------------
ANIM_INIT, ANM_RELOCATE, DECODE = 0x16F9A8, 0x1707B8, 0x16E468
PUSH, PUSH_WEIGHTS, PUSH_CHAINED, CLEAR = 0x170838, 0x1708C0, 0x170938, 0x1707B0
START, START_IN_OUT, STOP, DROP = 0x16CFE0, 0x16CEB0, 0x16D1A0, 0x16CB50
SYNC, RANDOMIZE, JUMP_END, SNAP_END, SYNC_BELOW = 0x1709F8, 0x16D0B8, 0x170BC8, 0x170C80, 0x170B08
RELEASE, DTOR, FIND, FIND_FLAG = 0x171118, 0x171098, 0x170D88, 0x171178
FADE_IN, FADE_OUT, SET_WEIGHT = 0x170E00, 0x170EE8, 0x170FC8
ADVANCE, COPY, BUILD_POSE, GET_MATRIX, EMIT_POSE = 0x16D748, 0x16FFE8, 0x16ED40, 0x16F720, 0x16F880
BUILD_LO, BUILD_HI = 0x16ED40, 0x16F720
BASE_DONE, BLEND_DONE = 0x16F0C0, 0x16F53C      # inside anim_buildPose: local transforms ready
ATTACH_POINT, SAMPLE_POINT = 0x1754A0, 0x178E18
CREATURE_STEP, PLAYER_STEP = 0x1162B0, 0x1B9520
FIRE_RANGE, MEMSET = 0x16D558, 0x3B60C0
SLOT_BASE, SLOT_SIZE = 0x6F6180, 0xF1C
SLOT_HEAD, SLOT_TAIL = 0x791E90, 0x791E8C
POSE_BASE, POSE_SIZE = 0x791EC0, 0x620
POSE_HEAD, POSE_TAIL, POSE_DEFAULT, POSE_FALLBACK = 0x7B8344, 0x7B8340, 0x7B8380, 0x7B89C0
G_DRAW_FRAME, G_SIM_FRAME, G_COSMETIC_SEED = 0x44FDD0, 0x44FDCC, 0x404460
CUE_THROTTLE, GROUP_LIMIT = 0x7B8FE0, 0x4F8A28
VU0_CODE, VU0_COUNT = 0x3E5C50, 77
CLIP_REGION, CLIP_REGION_SIZE = 0x02100000, 0x00600000


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-30s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count, share=1):
    """Sample size: a tenth with --quick, an eighth for the secondary FPU models."""
    count = max(count // 10, 4) if OPTIONS['quick'] else count
    return max(count // share, 2)


# ---------------------------------------------------------------------------------------
# VU0: an interpreter for the instruction forms the pose microprogram uses
# ---------------------------------------------------------------------------------------
class VuUnknown(Exception):
    pass


class Vu0:
    """Runs the microprogram words found at 0x3e5c50.  An instruction is a (lower, upper)
    pair; both halves read the registers as they were before the instruction."""

    def __init__(self, emu):
        self.emu = emu
        self.code = [(emu.mem.u32(VU0_CODE + 8 * i), emu.mem.u32(VU0_CODE + 8 * i + 4))
                     for i in range(VU0_COUNT)]
        self.vf = [[0, 0, 0, 0] for _ in range(32)]
        self.vf[0] = [0, 0, 0, A.ONE]
        self.acc = [0, 0, 0, 0]
        self.vi = [0] * 16
        self.i_reg = 0
        self.mem = [[0, 0, 0, 0] for _ in range(256)]
        self.instructions = 0

    def _add(self, a, b):
        return ee_emu.fp_add(a, b, self.emu.fpu_model)

    def _mul(self, a, b):
        return ee_emu.fp_mul(a, b, self.emu.fpu_model, None, self.emu.fpu_mul_bias)

    def _upper(self, w, out):
        if (w & 0x7FF) == 0x2FF:                            # NOP
            return
        op = w & 0x3F
        ft, fs, fd = (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31
        lanes = [k for k in range(4) if (w >> 21) & (8 >> k)]
        vf, acc = self.vf, self.acc
        if op >= 0x3C:                                      # second table: fd holds the opcode
            sub_op = (fd << 2) | (w & 3)
            kind, bc = sub_op & 0x3C, sub_op & 3
            if kind == 0x18:                                # MULAbc
                out.append(('acc', None, [(k, self._mul(vf[fs][k], vf[ft][bc])) for k in lanes]))
            elif kind == 0x08:                              # MADDAbc
                out.append(('acc', None, [(k, self._add(acc[k], self._mul(vf[fs][k], vf[ft][bc])))
                                          for k in lanes]))
            elif sub_op == 0x12:                            # ITOF12
                out.append(('vf', ft, [(k, self._mul(ee_emu.fp_from_int(vf[fs][k], self.emu.fpu_model),
                                                     0x39800000)) for k in lanes]))
            elif sub_op in (0x15, 0x16):                    # FTOI4, FTOI12
                scale = 0x41800000 if sub_op == 0x15 else 0x45800000
                out.append(('vf', ft, [(k, ee_emu.fp_to_int(self._mul(vf[fs][k], scale)) & M32)
                                       for k in lanes]))
            else:
                raise VuUnknown('upper special 0x%02x (word 0x%08x)' % (sub_op, w))
            return
        if op < 0x10 or 0x18 <= op < 0x1C:                  # ADDbc SUBbc MADDbc MSUBbc MULbc
            kind, t = op & 0x3C, vf[ft][op & 3]
            if kind == 0x00:
                values = [(k, self._add(vf[fs][k], t)) for k in lanes]
            elif kind == 0x04:
                values = [(k, self._add(vf[fs][k], t ^ 0x80000000)) for k in lanes]
            elif kind == 0x08:
                values = [(k, self._add(acc[k], self._mul(vf[fs][k], t))) for k in lanes]
            elif kind == 0x18:
                values = [(k, self._mul(vf[fs][k], t)) for k in lanes]
            else:
                raise VuUnknown('upper opcode 0x%02x' % op)
        elif op == 0x1E:                                    # MULi
            values = [(k, self._mul(vf[fs][k], self.i_reg)) for k in lanes]
        elif op == 0x28:                                    # ADD
            values = [(k, self._add(vf[fs][k], vf[ft][k])) for k in lanes]
        elif op == 0x2C:                                    # SUB
            values = [(k, self._add(vf[fs][k], vf[ft][k] ^ 0x80000000)) for k in lanes]
        else:
            raise VuUnknown('upper opcode 0x%02x (word 0x%08x)' % (op, w))
        out.append(('vf', fd, values))

    def _lower(self, w, pc, out):
        """Returns a branch target or None."""
        op = w >> 25
        it, is_ = (w >> 16) & 31, (w >> 11) & 31
        lanes = [k for k in range(4) if (w >> 21) & (8 >> k)]
        imm = w & 0x7FF
        imm -= 0x800 if imm & 0x400 else 0
        if op == 0x00:                                      # LQ
            src = self.mem[(self.vi[is_ & 15] + imm) & 0xFF]
            out.append(('vf', it, [(k, src[k]) for k in lanes]))
        elif op == 0x01:                                    # SQ
            out.append(('mem', (self.vi[it & 15] + imm) & 0xFF, [(k, self.vf[is_][k]) for k in lanes]))
        elif op == 0x20:                                    # B
            return (pc + 1 + imm) % 512
        elif op == 0x40 and (w & 0x7FF) == 0x33C:           # MOVE (vf0 to vf0 is the NOP)
            out.append(('vf', it, [(k, self.vf[is_][k]) for k in lanes]))
        elif op == 0x40 and (w & 0x7FF) == 0x33D:           # MR32
            src = self.vf[is_]
            out.append(('vf', it, [(k, src[(k + 1) & 3]) for k in lanes]))
        else:
            raise VuUnknown('lower word 0x%08x' % w)
        return None

    def run(self, index):
        pc, pending, last = index, None, False
        for _ in range(4096):
            lower, upper = self.code[pc]
            out = []
            self._upper(upper, out)
            target = None
            if upper & 0x80000000:                          # I bit: the lower word is a float
                self.i_reg = lower
            else:
                target = self._lower(lower, pc, out)
            touched = set()
            for kind, index, values in out:
                if kind == 'vf':
                    if index == 0:
                        continue
                    for k, value in values:
                        if (index, k) in touched:
                            raise VuUnknown('both halves write vf%d' % index)
                        touched.add((index, k))
                        self.vf[index][k] = value & M32
                elif kind == 'acc':
                    for k, value in values:
                        self.acc[k] = value & M32
                else:
                    for k, value in values:
                        self.mem[index][k] = value & M32
            self.instructions += 1
            nxt = pc + 1
            if pending is not None:
                nxt, pending = pending, None
            if target is not None:
                pending = target
            if last:
                return
            if upper & 0x40000000:                          # E bit: one more, then stop
                last = True
            pc = nxt
        raise VuUnknown('the microprogram did not end')


def install_cop2(emu, vu):
    """The COP2 instructions of anim_buildPose, at their addresses."""
    def skip(e):
        e.pc, e.npc = e.npc, (e.npc + 4) & M32

    count = 0
    for addr in range(BUILD_LO, BUILD_HI, 4):
        w = emu.mem.u32(addr)
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        if op == 0x36:                                      # LQC2 vf[rt], offset(rs)
            def hook(e, rs=rs, rt=rt, off=ee_emu.sx16(w)):
                base = (e.r[rs] + off) & M32
                if rt:
                    vu.vf[rt] = [e.mem.u32(base + 4 * k) for k in range(4)]
                skip(e)
        elif op != 0x12:
            continue
        elif w & 0x02000000:
            if (w & 0x3F) != 0x38:
                raise VuUnknown('COP2 macro instruction 0x%08x at 0x%x' % (w, addr))

            def hook(e, entry=(w >> 6) & 0x7FFF):           # VCALLMS
                vu.run(entry)
                skip(e)
        elif rs == 5:                                       # QMTC2
            def hook(e, rt=rt, rd=rd):
                lo, hi = e.r[rt], e.rh[rt]
                if rd:
                    vu.vf[rd] = [lo & M32, (lo >> 32) & M32, hi & M32, (hi >> 32) & M32]
                skip(e)
        elif rs == 1:                                       # QMFC2 (the interlock bit waits)
            def hook(e, rt=rt, rd=rd):
                v = vu.vf[rd]
                e.r[rt] = (v[0] | (v[1] << 32)) & M64
                e.rh[rt] = (v[2] | (v[3] << 32)) & M64
                skip(e)
        elif rs == 6:                                       # CTC2
            def hook(e, rt=rt, rd=rd):
                if rd < 16:
                    vu.vi[rd] = e.r[rt] & 0xFFFF
                skip(e)
        else:
            raise VuUnknown('COP2 instruction 0x%08x at 0x%x' % (w, addr))
        emu.hook(addr, hook)
        count += 1
    return count


# ---------------------------------------------------------------------------------------
# The original and the model side by side
# ---------------------------------------------------------------------------------------
class Mismatch(Exception):
    pass


def f(value):
    return C.f32(value)


class Rig:
    def __init__(self, elf, fpu=FPU_CONFIGS[0], slots=None, buffers=None):
        emu = self.emu = EE(elf, fpu_model=fpu[0])
        emu.fpu_mul_bias, emu.fpu_div_nearest = fpu[1], fpu[2]
        C.set_fpu(*fpu)
        emu.record_calls = emu.record_writes = False
        self.sp = emu.r[29]

        def memset(e):
            e.mem.write(e.r[4] & M32, bytes([e.r[5] & 0xFF]) * (e.r[6] & M32))
            return e.r[4] & M32
        emu.stub(MEMSET, function=memset)
        self.fired = []
        emu.stub(FIRE_RANGE, function=lambda e: self.fired.append(
            (e.r[4] & M32, C.s32(e.r[5]), C.s32(e.r[6]))) and 0)
        self.vu = Vu0(emu)
        self.cop2 = install_cop2(emu, self.vu)
        self.traces = []
        emu.hook(BASE_DONE, lambda e: self._capture(e, 'base'))
        emu.hook(BLEND_DONE, lambda e: self._capture(e, 'blended'))
        self.call(ANIM_INIT)
        mem = emu.mem
        limits = [mem.u8(GROUP_LIMIT + i) for i in range(256)]
        self.sys = A.AnimSystem(decoder_slots=slots or A.DECODER_SLOTS,
                                pose_buffers=buffers or A.POSE_BUFFERS, group_limits=limits)
        self.sys.trace = []
        pool = self.sys.decoders
        plain_alloc = pool.alloc

        def counted_alloc():
            if pool.order[0].owner is not None and pool.order[0].owner.flags & A.PROTECTED:
                cover('allocations that skipped a root-motion slot')
            taken = next((s for s in pool.order
                          if s.owner is None or not s.owner.flags & A.PROTECTED), None)
            if taken is not None and taken.owner is not None:
                cover('decoder slots taken from another track')
            return plain_alloc()
        pool.alloc = counted_alloc
        if slots:                                           # shorten the original's list
            top = SLOT_BASE + (slots - 1) * SLOT_SIZE
            mem.w32(SLOT_HEAD, top)
            mem.w32(top + 0x0C, 0)
        if buffers:
            top = POSE_BASE + (buffers - 1) * POSE_SIZE
            mem.w32(POSE_HEAD, top)
            mem.w32(top + 0x614, 0)
        mem.map(CLIP_REGION, CLIP_REGION_SIZE)
        self.clip_top = CLIP_REGION
        self.clip_addr, self.cell_addr, self.state_addr = {}, {}, {}
        self.out = emu.alloc(0x40)
        self.scratch = emu.alloc(0x400)
        self.set_globals(draw=10, sim=0, seed=0x12345678)

    # ---- running the original -----------------------------------------------------------
    def call(self, addr, *args, floats=()):
        emu = self.emu
        emu.r[29] = self.sp
        for index, raw in enumerate(floats):
            emu.f[12 + index] = raw & M32
        return emu.call(addr, *args, max_steps=20000000)

    def _capture(self, e, name):
        sp = e.r[29] & M32
        count = e.mem.s32(sp + 0x890)
        self.traces.append((name, [[e.mem.u32(sp + 0x20 * j + 4 * k) for k in range(7)]
                                   for j in range(max(count, 0))]))

    def set_globals(self, draw=None, sim=None, seed=None):
        mem = self.emu.mem
        if draw is not None:
            mem.w32(G_DRAW_FRAME, draw & M32)
            self.sys.draw_frame = C.s32(draw)
        if sim is not None:
            mem.w32(G_SIM_FRAME, sim & M32)
            self.sys.sim_frame = C.s32(sim)
        if seed is not None:
            mem.w32(G_COSMETIC_SEED, seed & M32)
            self.sys.cosmetic_seed = seed & M32

    # ---- building things on both sides --------------------------------------------------
    def reset_clips(self):
        self.clip_top = CLIP_REGION
        self.clip_addr = {}

    def load_clip(self, data, name='', events=None):
        """Copy a file in, let anm_relocate (0x1707b8) fix its pointers, parse it for the
        model.  events: four (seconds pattern, mask) written to both, as game code does."""
        size = (len(data) + 0x40 + 15) & ~15
        if self.clip_top + size > CLIP_REGION + CLIP_REGION_SIZE:
            raise EmuError('clip region exhausted')
        addr = self.clip_top
        self.clip_top += size
        mem = self.emu.mem
        mem.write(addr, bytes(data) + bytes(size - len(data)))
        self.call(ANM_RELOCATE, addr)
        clip = A.Clip(data, name)
        clip.key_off = struct.unpack_from('<I', data, 8)[0]
        if events:
            for k, (seconds, mask) in enumerate(events):
                mem.w32(addr + 0x14 + 8 * k, seconds)
                mem.w8(addr + 0x18 + 8 * k, mask)
                clip.events[k] = [seconds, mask]
        self.clip_addr[id(clip)] = addr
        clip.addr = addr
        return clip

    def new_state(self, capacity=8, addr=None):
        if addr is None:
            addr = self.emu.alloc(8 + 0x20 * capacity)
        self.emu.mem.write(addr, bytes(8 + 0x20 * capacity))
        self.emu.mem.w8(addr + 5, capacity)
        state = A.AnimState(capacity)
        self.adopt(state, addr)
        return state

    def adopt(self, state, addr):
        state.addr = addr
        self.state_addr[id(state)] = addr
        for index, cell in enumerate(state.tracks):
            self.cell_addr[id(cell)] = addr + 8 + 0x20 * index

    # ---- model -> expected memory image -------------------------------------------------
    def ptr(self, thing):
        if thing is None:
            return 0
        if isinstance(thing, A.DecoderSlot):
            return SLOT_BASE + SLOT_SIZE * thing.index
        if isinstance(thing, A.PoseBuffer):
            if thing is self.sys.poses.fallback:
                return POSE_FALLBACK
            if thing is self.sys.poses.default:
                return POSE_DEFAULT
            return POSE_BASE + POSE_SIZE * thing.name
        if isinstance(thing, A.Track):
            return self.cell_addr[id(thing)]
        if isinstance(thing, A.AnimState):
            return self.state_addr[id(thing)]
        if isinstance(thing, A.Clip):
            return thing.addr
        raise TypeError(thing)

    def state_image(self, state):
        out = [struct.pack('<IbbH', self.ptr(state.pose), state.count, state.capacity, state.flags)]
        for t in state.tracks:
            out.append(struct.pack('<7IHh', self.ptr(t.clip), self.ptr(t.slot), t.weight, t.rate,
                                   t.life, t.life_rate, t.time, t.flags, t.sound_idx))
        return b''.join(out)

    def slot_image(self, slot, position=None):
        order = self.sys.decoders.order
        if position is None:
            position = order.index(slot)
        before = order[position - 1] if position > 0 else None
        after = order[position + 1] if position + 1 < len(order) else None
        stream = self.ptr(slot.clip) + slot.clip.key_off if slot.clip is not None else 0
        out = [struct.pack('<IiiIIIhH', stream, slot.cursor, slot.tick, self.ptr(before),
                           self.ptr(after), self.ptr(slot.owner), slot.yaw, 0)]
        for rec in slot.joints:
            out.append(struct.pack('<hh14I', *rec))
        return b''.join(out)

    def pose_image(self, buf, full=True):
        """(offset, bytes) pieces of a pose buffer that the model defines."""
        pieces = [(4, struct.pack('<Ih', buf.tag, buf.joint_count))]
        if full:
            mats = b''.join(struct.pack('<4h', *row) for joint in buf.mats for row in joint)
            pieces.append((0x10, mats))
        order = self.sys.poses.order
        if buf in order:
            position = order.index(buf)
            before = order[position - 1] if position > 0 else None
            after = order[position + 1] if position + 1 < len(order) else None
            links = struct.pack('<II', self.ptr(before), self.ptr(after))
        else:
            links = struct.pack('<II', 0, 0)
        pieces.append((0x610, struct.pack('<I', self.ptr(buf.owner)) + links +
                       struct.pack('<I', buf.stamp & M32)))
        return pieces

    # ---- comparisons --------------------------------------------------------------------
    def expect(self, addr, image, what):
        got = self.emu.mem.read(addr, len(image))
        if got != image:
            at = next(i for i in range(len(image)) if got[i] != image[i]) & ~3
            raise Mismatch('%s +0x%x: original %s, model %s' % (
                what, at, got[at:at + 4].hex(), image[at:at + 4].hex()))

    def check_state(self, state, slots=True):
        self.expect(self.ptr(state), self.state_image(state), 'state')
        if slots:
            for cell in state.tracks:
                if cell.slot is not None:
                    self.expect(self.ptr(cell.slot), self.slot_image(cell.slot),
                                'decoder slot %d' % cell.slot.index)

    def check_pools(self):
        mem, model = self.emu.mem, self.sys
        order = model.decoders.order
        if mem.u32(SLOT_HEAD) != self.ptr(order[0]) or mem.u32(SLOT_TAIL) != self.ptr(order[-1]):
            raise Mismatch('decoder list ends')
        for position, slot in enumerate(order):
            self.expect(self.ptr(slot), self.slot_image(slot, position), 'decoder slot %d' % slot.index)
        porder = model.poses.order
        if mem.u32(POSE_HEAD) != self.ptr(porder[0]) or mem.u32(POSE_TAIL) != self.ptr(porder[-1]):
            raise Mismatch('pose list ends')
        for buf in porder + [model.poses.fallback, model.poses.default]:
            for offset, image in self.pose_image(buf):
                self.expect(self.ptr(buf) + offset, image, 'pose buffer %s' % buf.name)
        table = bytes(v for cell in model.cue_throttle for v in cell)
        self.expect(CUE_THROTTLE, table, 'sound cue table')
        if mem.u32(G_COSMETIC_SEED) != model.cosmetic_seed:
            raise Mismatch('cosmetic seed')
        for index in range(256):
            if self.vu.mem[index] != model.vu_mem[index]:
                raise Mismatch('VU0 matrix stack, quadword %d' % index)

    def check_side_effects(self):
        """Sound ranges and pose-builder traces produced by the last operation."""
        model = self.sys
        expected = [(self.ptr(clip), first, end) for clip, first, end in model.sound_log]
        if self.fired != expected:
            raise Mismatch('animsound_fireRange calls: original %r, model %r' % (
                self.fired[:4], expected[:4]))
        if self.traces != model.trace:
            raise Mismatch('local joint transforms inside anim_buildPose (%d / %d builds)' % (
                len(self.traces), len(model.trace)))
        cover('sound event ranges fired', len(expected))
        cover('pose builds', len(model.trace) // 2)
        cover('pose builds that blended two or more tracks',
              sum(1 for k in range(0, len(model.trace), 2) if model.trace[k][1] != model.trace[k + 1][1]))
        del self.fired[:], self.traces[:], model.sound_log[:], model.trace[:]

    # ---- one operation on both sides ----------------------------------------------------
    def note_step(self, state, before, events, dx, dy, yaw):
        """Coverage counters for one animation step (before: count and track times)."""
        count, times = before
        cover('animation steps')
        cover('steps that returned event bits', events != 0)
        cover('steps with a root-motion delta', bool((dx or 0) & 0x7FFFFFFF or (dy or 0) & 0x7FFFFFFF))
        cover('steps with a yaw delta', bool(yaw))
        cover('steps that removed tracks', state.count < count)
        cover('steps that reported an end (status 0x80)', bool(state.flags & A.STATUS_ENDED))
        if state.count == count:
            for cell, old in zip(state.tracks[:count], times):
                if cell.flags & A.LOOP and C.lt(cell.time, old):
                    cover('loop wraps')
                    cover('loop wraps of a root-motion track', bool(cell.flags & A.ROOT))
                    cover('loop wraps of a root-yaw track', bool(cell.flags & A.YAW))

    @staticmethod
    def before_step(state):
        return state.count, [cell.time for cell in state.tracks[:max(state.count, 0)]]

    def advance(self, state, speed, sound=True, want_root=True, want_yaw=True):
        mem, out = self.emu.mem, self.out
        mem.write(out, b'\x55' * 16)
        before = self.before_step(state)
        got = C.s32(self.call(ADVANCE, self.ptr(state), self.scratch if sound else 0,
                              out if want_root else 0, out + 8 if want_yaw else 0, floats=(speed,)))
        events, dx, dy, yaw = A.anim_advance(self.sys, speed, state, sound, want_root, want_yaw)
        if got != events:
            raise Mismatch('event bits: original %d, model %d' % (got, events))
        if want_root and (mem.u32(out), mem.u32(out + 4)) != (dx, dy):
            raise Mismatch('root delta: original %08x %08x, model %08x %08x' % (
                mem.u32(out), mem.u32(out + 4), dx, dy))
        if want_yaw and mem.s16(out + 8) != yaw:
            raise Mismatch('yaw delta: original %d, model %d' % (mem.s16(out + 8), yaw))
        self.note_step(state, before, events, dx, dy, yaw)
        return events, dx, dy, yaw

    def decode(self, state, index):
        self.call(DECODE, self.ptr(state.tracks[index]))
        A.animtrack_decode(self.sys, state.tracks[index])

    def set_time(self, state, index, raw):
        self.emu.mem.w32(self.ptr(state.tracks[index]) + 0x18, raw)
        state.tracks[index].time = raw

    def joint_matrix(self, state, joint):
        out = self.out + 0x10
        self.call(GET_MATRIX, self.ptr(state), joint & M32, out)
        got = [self.emu.mem.u32(out + 4 * k) for k in range(12)]
        want = A.anim_get_joint_matrix(self.sys, state, joint)
        if got != want:
            raise Mismatch('joint matrix %d: original %s, model %s' % (
                joint, ' '.join('%08x' % v for v in got), ' '.join('%08x' % v for v in want)))
        cover('joint matrix queries')
        cover('queries answered from the fallback buffer', state.pose is self.sys.poses.fallback)
        cover('queries answered from the default pose', state.pose is None)
        return want


# ---------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------
class Library:
    """The user's clips, read lazily."""

    def __init__(self, directory, rng):
        self.directory = directory
        self.names = sorted(n for n in os.listdir(directory) if n.lower().endswith('.anm'))
        self.rng = rng
        self.heads = {}

    def data(self, name):
        with open(os.path.join(self.directory, name), 'rb') as handle:
            return handle.read()

    def head(self, name):
        if name not in self.heads:
            with open(os.path.join(self.directory, name), 'rb') as handle:
                raw = handle.read(0x70)
            if len(raw) < 0x70:
                self.heads[name] = None
            else:
                joints, length = struct.unpack_from('<ii', raw, 0)
                self.heads[name] = (joints, length, raw[0x38:0x3C] != bytes(4))
        return self.heads[name]

    def usable(self, name, min_joints=1):
        head = self.head(name)
        return head is not None and min_joints <= head[0] <= 64 and 1 <= head[1] <= 2000

    def sample(self, count, min_joints=1):
        names = [n for n in self.names if self.usable(n, min_joints)]
        if count >= len(names):
            return names
        return self.rng.sample(names, count)

    def family(self, size, sound=False):
        """Clips that can be blended in one state: same lump prefix and joint count."""
        for _ in range(200):
            name = self.rng.choice(self.names)
            if not self.usable(name, 2):
                continue
            prefix = name.split('__')[0] + '__' if '__' in name else ''
            joints = self.head(name)[0]
            mates = [n for n in self.names if n.startswith(prefix) and self.usable(n, 2)
                     and self.head(n)[0] == joints]
            if sound and not any(self.head(n)[2] for n in mates):
                continue
            if len(mates) >= 2:
                picked = self.rng.sample(mates, min(size, len(mates)))
                if sound and not any(self.head(n)[2] for n in picked):
                    picked[0] = self.rng.choice([n for n in mates if self.head(n)[2]])
                return picked
        raise EmuError('no clip family found in the directory')


def random_events(rng, length):
    events = []
    for _ in range(4):
        if rng.random() < 0.35:
            events.append((0, 0))
        else:
            events.append((f(rng.uniform(0.0, (length + 2) / 60.0)), rng.choice((1, 2, 4, 8, 0x10, 0x40, 0x80,
                                                                              rng.randrange(256)))))
    return events


SPEEDS = (1.0, 1.0, 1.0, 1.0, 0.5, 0.25, 2.0, 1.5, 0.75, 3.0, 0.0, 0.016666668, 58.0 / 60.0)
FLAG_SETS = (0, A.LOOP, A.LOOP, A.LOOP | A.ROOT, A.LOOP | A.ROOT, A.REPORT_END, A.REPORT_END | A.PURGE_BELOW,
             A.PURGE_BELOW, A.LOOP | A.PURGE_BELOW, A.ROOT, A.ROOT | A.REPORT_END, A.LOOP | A.YAW,
             A.LOOP | A.ROOT | A.YAW, A.YAW | A.REPORT_END, A.LOOP | A.PERSISTENT, A.KEEP,
             A.LOOP | A.FIXED_STEP, A.EASE | A.REPORT_END, A.LOOP | A.EASE, A.LOOP | A.PAUSED,
             A.TALK | A.REPORT_END | A.PURGE_BELOW, A.LOOP | A.ROOT | A.PERSISTENT,
             A.LOOP | A.ROOT | A.PURGE_BELOW, 0x8000 | A.LOOP)


def random_speed(rng):
    if rng.random() < 0.15:
        return f(rng.uniform(0.0, 4.0))
    return f(rng.choice(SPEEDS))


def random_seconds(rng):
    return f(rng.choice((0.0, 0.0, 0.01, 0.016, 0.017, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, rng.uniform(0.0, 1.0))))


class Scene:
    """A few states and clips, and a seeded stream of operations applied to both sides."""

    def __init__(self, rig, rng, clips, states=2, pose=False, yaw=True, stepper='advance'):
        self.rig, self.rng, self.clips, self.pose, self.yaw = rig, rng, clips, pose, yaw
        self.stepper = stepper
        self.objects = []
        self.states = []
        for _ in range(states):
            capacity = rng.choice((8, 8, 8, 4, 2, 1)) if stepper == 'advance' else 8
            if stepper == 'advance':
                state = rig.new_state(capacity)
                self.objects.append(None)
            else:
                obj = rig.emu.alloc(0x400)
                state = rig.new_state(8, obj + 0x114)
                self.objects.append(obj)
            self.states.append(state)
        self.speed = [A.ONE] * states
        self.ops = 0
        self.frame = 10
        self.dl = rig.emu.alloc(0x4000)
        self.dl_cursor = rig.emu.alloc(16)

    def flags(self):
        flags = self.rng.choice(FLAG_SETS)
        if not self.yaw:
            flags &= ~A.YAW
        if self.room() < 3:                 # never more unstealable slots than the list holds
            flags &= ~A.PROTECTED
        return flags

    def room(self):
        """Decoder slots left when every track that may pin one has done so.  (With every
        slot pinned animcache_alloc does not return; the scenes stay clear of that.)"""
        pinned = sum(1 for s in self.states for i, c in enumerate(s.tracks)
                     if c.flags & A.PROTECTED and (i < s.count or c.slot is not None))
        return len(self.rig.sys.decoders.order) - pinned

    def step(self):
        rig, rng = self.rig, self.rng
        index = rng.randrange(len(self.states))
        state = self.states[index]
        sp = rig.ptr(state)
        clip = rng.choice(self.clips)
        cp = rig.ptr(clip)
        roll = rng.random()
        self.ops += 1
        if roll < 0.52:
            if rng.random() < 0.1:
                self.speed[index] = random_speed(rng)
            if rng.random() < 0.3:
                self.frame += rng.choice((0, 1, 1, 1, 2, 5, 300))
                rig.set_globals(draw=self.frame)
            self.advance(index)
        elif roll < 0.60:
            blend, flags = random_seconds(rng), self.flags()
            rig.call(START, sp, cp, flags, floats=(blend,))
            A.anim_start(blend, state, clip, flags)
        elif roll < 0.66:
            a, b, flags = random_seconds(rng), random_seconds(rng), self.flags()
            rig.call(START_IN_OUT, sp, cp, flags, floats=(a, b))
            A.anim_start_blend_in_out(a, b, state, clip, flags)
        elif roll < 0.71:
            flags = self.flags()
            rig.call(PUSH, sp, cp, flags)
            A.anim_push(state, clip, flags)
        elif roll < 0.74:
            if state.count >= 1:
                flags = self.flags()
                rig.call(PUSH_CHAINED, sp, cp, flags)
                A.anim_push_chained(state, clip, flags)
        elif roll < 0.76:
            flags = self.flags()
            w = [f(rng.choice((0.0, 0.25, 0.5, 1.0, rng.uniform(-0.5, 1.5)))),
                 f(rng.choice((0.0, 0.05, -0.05, 0.2))), f(rng.choice((1.0, 0.5, 2.0, 3.5))),
                 f(rng.choice((0.0, -0.05, -0.2)))]
            rig.call(PUSH_WEIGHTS, sp, cp, flags, floats=[0x7FC00000] + w)
            A.anim_push_with_weights(state, clip, flags, *w)
        elif roll < 0.79:
            blend = random_seconds(rng)
            target = rng.choice([c.clip for c in state.tracks[:state.count]] or [clip])
            rig.call(STOP, sp, rig.ptr(target), floats=(blend,))
            A.anim_stop(blend, state, target)
        elif roll < 0.80:
            rig.call(CLEAR, sp)
            A.anim_clear(state)
        elif roll < 0.81:
            rig.call(DROP, sp)
            A.anim_drop_non_persistent(state)
        elif roll < 0.83:
            rig.set_globals(sim=rng.choice((rng.randrange(0, 200000), rng.randrange(0, 600), -5)))
            rig.call(SYNC, sp)
            A.anim_sync_to_sim_frame(rig.sys, state)
        elif roll < 0.85:
            rig.call(RANDOMIZE, sp)
            A.anim_randomize_top_time(rig.sys, state)
        elif roll < 0.86:
            rig.call(JUMP_END, sp)
            A.anim_jump_top_to_end(rig.sys, state)
        elif roll < 0.87:
            rig.call(SNAP_END, sp)
            A.anim_snap_top_to_end(state)
        elif roll < 0.88:
            rig.call(SYNC_BELOW, sp)
            A.anim_sync_top_to_below(rig.sys, state)
        elif roll < 0.89:
            self.finders(state, clip)
        elif roll < 0.90:
            which = rng.randrange(3)
            value = random_seconds(rng)
            target = rng.choice([c.clip for c in state.tracks[:state.count]] or [clip])
            rig.call((FADE_IN, FADE_OUT, SET_WEIGHT)[which], sp, rig.ptr(target), floats=(value,))
            (A.anim_fade_in_track, A.anim_fade_out_track, A.anim_set_track_weight)[which](value, state, target)
        elif roll < 0.905:
            rig.call(RELEASE, sp)
            A.anim_release_caches(state)
        elif roll < 0.91 and self.stepper == 'advance' and state.capacity == 8 and self.room() > 12:
            self.copy(index)
        elif self.pose:
            self.pose_op(state, rng.random())
        else:
            self.advance(index)
        for other in self.states:
            rig.check_state(other)
        rig.check_side_effects()

    def finders(self, state, clip):
        rig = self.rig
        got = rig.call(FIND, rig.ptr(state), rig.ptr(clip)) & M32
        if got != rig.ptr(A.anim_find_track(state, clip)):
            raise Mismatch('anim_findTrack')
        mask = self.rng.choice((0x20, 0x800, 0x4000, 0x1, 0x8000, 0x1002))
        got = C.s32(rig.call(FIND_FLAG, rig.ptr(state), mask))
        if got != A.anim_find_track_by_flag(state, mask):
            raise Mismatch('anim_findTrackByFlag')

    def copy(self, index):
        """AnimState_copy into fresh memory; the copy replaces the source in the scene."""
        rig = self.rig
        src = self.states[index]
        addr = rig.emu.alloc(0x108)
        rig.emu.mem.write(addr, b'\xEE' * 0x108)
        rig.call(COPY, addr, rig.ptr(src))
        dst = A.anim_state_copy(rig.sys, src)
        rig.adopt(dst, addr)
        rig.check_state(dst)
        rig.call(DTOR, rig.ptr(src), 0)
        A.anim_state_dtor(src)
        rig.check_state(src)
        self.states[index] = dst

    def advance(self, index):
        rig, rng, state = self.rig, self.rng, self.states[index]
        speed = self.speed[index]
        if self.stepper == 'advance':
            rig.advance(state, speed, sound=rng.random() < 0.9)
            return
        obj, mem = self.objects[index], rig.emu.mem
        snapshot = rig.before_step(state)
        slow = rng.choice((0, 0, 0, 1, 10, 30, 59, 60, 61, 200))
        facing = rng.randrange(-0x8000, 0x8000)
        scale = f(rng.choice((1.0, 1.0, 0.5, 1.25, rng.uniform(0.3, 3.0))))
        mem.w8(obj + 0x2FC, slow)
        mem.w16(obj + 0x38, facing & 0xFFFF)
        mem.w16(obj + 0x31A, 0)
        if self.stepper == 'creature':
            active = rng.random() < 0.93
            quiet = rng.random() < 0.1
            mem.w16(obj + 0x232, 0)
            mem.w64(obj + 0xA8, (1 << 63 if active else 0) | (0x2000000 if quiet else 0))
            mem.w32(obj + 0xDC, scale)
            before = (mem.u32(obj + 0xBC), mem.u32(obj + 0xC0)), mem.s16(obj + 0xC4)
            got = C.s32(rig.call(CREATURE_STEP, obj, floats=(speed,)))
            want = A.creature_step_anim(rig.sys, speed, state, facing, scale, slow, not quiet, active,
                                        before[0], before[1])
            result = (got, mem.u32(obj + 0xBC), mem.u32(obj + 0xC0), mem.s16(obj + 0xC4))
        else:
            quiet = rng.random() < 0.1
            mem.w32(obj + 0x0C, 0x200000 if quiet else 0)
            got = C.s32(rig.call(PLAYER_STEP, obj, floats=(speed,)))
            want = A.player_anim_step(rig.sys, speed, state, facing, slow, not quiet)
            result = (got, mem.u32(obj + 0xBC), mem.u32(obj + 0xC0))
        if result != tuple(want):
            raise Mismatch('%s step: original %r, model %r' % (self.stepper, result, tuple(want)))
        cover('%s wrapper steps' % self.stepper)
        cover('%s wrapper steps with a slow amount 1..60' % self.stepper, 1 <= slow <= 60)
        if self.stepper == 'creature' and not active:
            cover('creature wrapper steps of an inactive creature')
        else:
            rig.note_step(state, snapshot, want[0], want[1], want[2], want[3] if len(want) > 3 else 0)

    def pose_op(self, state, roll):
        rig, rng, mem = self.rig, self.rng, self.rig.emu.mem
        joints = max(state.tracks[0].clip.joint_count if state.tracks[0].clip else 1, 1)
        joint = rng.choice((rng.randrange(joints), rng.randrange(joints), 0, -1, 70))
        facing = rng.randrange(-0x8000, 0x8000)
        scale = f(rng.choice((1.0, 0.5, 1.25, rng.uniform(0.3, 3.0))))
        pos = [f(rng.uniform(-3000, 3000)), f(rng.uniform(-3000, 3000)), f(rng.uniform(-200, 200))]
        with_state = rng.random() < 0.9
        if roll < 0.3:
            rig.joint_matrix(state, joint)
        elif roll < 0.55:                               # anim_emitPose: the draw path
            self.frame += rng.choice((0, 1, 1, 2, 5))
            rig.set_globals(draw=self.frame)
            mem.w32(self.dl_cursor, self.dl)
            rig.call(EMIT_POSE, self.dl_cursor, rig.ptr(state))
            buf = A.anim_emit_pose(rig.sys, state)
            if mem.u64(self.dl) >> 32 != rig.ptr(buf):
                raise Mismatch('anim_emitPose drew buffer 0x%x, model %s' % (mem.u64(self.dl) >> 32, buf.name))
            cover('draws (anim_emitPose)')
            cover('draws of the default pose', buf is rig.sys.poses.default)
        elif roll < 0.8:                                # model_getAttachPoint
            model = self.rig.scratch
            origin = [f(rng.uniform(-30, 30)) for _ in range(3)]
            direction = [f(rng.uniform(-1, 1)) for _ in range(3)]
            slot = rng.randrange(4)
            mem.w8(model + 0x22, 4)
            rec = model + 0x40 + 0x34 * slot
            mem.w32(rec, joint & M32)
            for k in range(3):
                mem.w32(rec + 0x10 + 4 * k, direction[k])
                mem.w32(rec + 0x28 + 4 * k, origin[k])
                mem.w32(self.rig.out + 0x30 + 4 * k, pos[k])
            want_p, want_d = rng.random() < 0.9, rng.random() < 0.7
            po, do = self.rig.out + 0x10, self.rig.out + 0x20
            rig.call(ATTACH_POINT, model, rig.out + 0x30, facing & 0xFFFF, rig.ptr(state) if with_state else 0,
                     slot, po if want_p else 0, do if want_d else 0, floats=(scale,))
            p, d = A.model_get_attach_point(rig.sys, scale, pos, facing, state if with_state else None, joint,
                                            origin if want_p else None, direction if want_d else None)
            if want_p and [mem.u32(po + 4 * k) for k in range(3)] != p:
                raise Mismatch('attach point position')
            if want_d and [mem.u32(do + 4 * k) for k in range(3)] != d:
                raise Mismatch('attach point direction')
            cover('attach point queries')
        else:                                           # model_getSamplePoint
            model = self.rig.scratch
            count = 100
            index = rng.choice((rng.randrange(count), rng.randrange(count), 44, 45, 46, 90, count, count + 7))
            joint = rng.randrange(64)
            point = (rng.randrange(-800, 800), rng.randrange(-800, 800), rng.randrange(-200, 1400),
                     C.s16((joint << 2) | (rng.randrange(256) << 8) | rng.randrange(4)))
            mem.w8(model + 0x24, 6)
            mem.w32(model + 0x60 + 4, count)
            if index < count:
                mem.write(model + 0x60 + 0x20 + index * 8 + (index // 45) * 16, struct.pack('<4h', *point))
            for k in range(3):
                mem.w32(rig.out + 0x30 + 4 * k, pos[k])
            want_m = rng.random() < 0.5
            po, ro, mo = rig.out + 0x10, rig.out + 0x20, self.dl + 0x100
            rig.call(SAMPLE_POINT, model, rig.ptr(state) if with_state else 0, rig.out + 0x30, facing & 0xFFFF,
                     index, po, ro, mo if want_m else 0, floats=(scale,))
            p, radius, matrix = A.model_get_sample_point(rig.sys, scale, pos, facing,
                                                         state if with_state else None,
                                                         point if index < count else None, want_m)
            got = [mem.u32(po + 4 * k) for k in range(3)] + [mem.u32(ro)]
            if got != p + [radius]:
                raise Mismatch('sample point %d of %d position / radius: original %s, model %s' % (
                    index, count, ' '.join('%08x' % v for v in got),
                    ' '.join('%08x' % v for v in p + [radius])))
            if want_m and [mem.u32(mo + 4 * k) for k in range(9)] != matrix:
                raise Mismatch('sample point matrix')
            cover('sample point queries')


def run_scenes(elf, library, rng, config, scenes, length, **kind):
    """Returns (operations compared, failures, examples)."""
    total, failures, examples = 0, 0, []
    slots, buffers = kind.pop('slots', None), kind.pop('buffers', None)
    rig = Rig(elf, config, slots, buffers)
    family_size = kind.pop('family', 5)
    mixed = kind.pop('mixed', False)
    for number in range(scenes):
        rig.reset_clips()
        names = library.sample(family_size) if mixed else library.family(family_size, kind.get('sound', False))
        clips = []
        for name in names:
            data = library.data(name)
            length_ticks = struct.unpack_from('<i', data, 4)[0]
            clips.append(rig.load_clip(data, name, random_events(rng, length_ticks)))
        scene = Scene(rig, rng, clips, states=rng.choice((1, 2, 3)), pose=kind.get('pose', False),
                      yaw=kind.get('yaw', True), stepper=kind.get('stepper', 'advance'))
        try:
            for step in range(length):
                scene.step()
                if step % 40 == 39:
                    rig.check_pools()
            rig.check_pools()
            for state in scene.states:                  # leave nothing attached for the next scene
                rig.call(DTOR, rig.ptr(state), 0)
                A.anim_state_dtor(state)
        except (Mismatch, EmuError, A.HostFault, VuUnknown, IndexError) as error:
            failures += 1
            examples.append('scene %d (%s) op %d: %s: %s' % (number, ', '.join(names[:3]), scene.ops,
                                                              type(error).__name__, error))
            rig = Rig(elf, config, slots, buffers)
        total += scene.ops
    return total, failures, examples


# ---------------------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------------------
def decode_times(rng, length):
    """Track times for one clip: forward steps, a seek back, fractions, out of range."""
    times = [0.0, rng.uniform(0, length), rng.uniform(0, length)]
    t = rng.uniform(0, length / 2.0)
    for _ in range(4):
        t += rng.choice((1.0, 0.99999994, 0.5, 2.0, 7.25))
        times.append(t)
    times += [rng.uniform(0, length / 4.0), float(length), length - 0.5, length + rng.choice((0.25, 3.0)),
              -0.5, -3.0, float(rng.randrange(length + 1)), 0.0]
    return [f(t) for t in times]


def prop_decoder(elf, library, rng, config, clips):
    name = 'decoder slot [%s]' % config_name(config)
    if not wanted(name):
        return
    rig = Rig(elf, config)
    cases = failures = 0
    examples = []
    states = [rig.new_state(1) for _ in range(3)]
    for number, clip_name in enumerate(clips):
        if number % 40 == 0:
            for state in states:
                rig.call(DTOR, rig.ptr(state), 0)
                A.anim_state_dtor(state)
            rig.reset_clips()
        data = library.data(clip_name)
        try:
            clip = rig.load_clip(data, clip_name)
            state = states[number % 3]
            flags = rng.choice((0, 0, A.LOOP, A.ROOT, A.ROOT | A.LOOP, A.YAW))
            rig.call(CLEAR, rig.ptr(state))
            A.anim_clear(state)
            rig.call(PUSH, rig.ptr(state), rig.ptr(clip), flags)
            A.anim_push(state, clip, flags)
            for raw in decode_times(rng, clip.length):
                rig.set_time(state, 0, raw)
                rig.decode(state, 0)
                cases += 1
                rig.check_state(state)
        except (Mismatch, EmuError, A.HostFault, IndexError) as error:
            failures += 1
            examples.append('%s: %s: %s' % (clip_name, type(error).__name__, error))
            rig = Rig(elf, config)
            states = [rig.new_state(1) for _ in range(3)]
    try:
        rig.check_pools()
    except Mismatch as error:
        failures += 1
        examples.append('final pool comparison: %s' % error)
    report(name, failures, cases, 'animtrack_decode on %d clips: the whole slot (key ticks, bases, '
           'velocities of all 64 joint records, cursor, yaw, list links), bit for bit' % len(clips), examples)


def prop_joint_values(elf, library, rng, config, clips):
    name = 'joint values [%s]' % config_name(config)
    if not wanted(name):
        return
    rig = Rig(elf, config)
    cases = failures = joints = 0
    examples = []
    state = rig.new_state(1)
    for number, clip_name in enumerate(clips):
        if number % 40 == 0:
            rig.call(DTOR, rig.ptr(state), 0)
            A.anim_state_dtor(state)
            rig.reset_clips()
        try:
            clip = rig.load_clip(library.data(clip_name), clip_name)
            rig.call(CLEAR, rig.ptr(state))
            A.anim_clear(state)
            rig.call(PUSH, rig.ptr(state), rig.ptr(clip), 0)
            A.anim_push(state, clip, 0)
            for raw in decode_times(rng, clip.length)[:6]:
                if C.lt(raw, 0):
                    continue
                rig.set_time(state, 0, raw)
                rig.call(RELEASE, rig.ptr(state))
                A.anim_release_caches(state)
                rig.joint_matrix(state, rng.randrange(clip.joint_count))
                want = [A.joint_quat(state.tracks[0].slot, j, raw) + A.joint_pos(state.tracks[0].slot, j, raw)
                        for j in range(clip.joint_count)]
                if not rig.traces or rig.traces[0] != ('base', want):
                    raise Mismatch('interpolated joint values at time %g' % C.to_float(raw))
                rig.check_side_effects()
                rig.check_state(state)
                for offset, image in rig.pose_image(state.pose):
                    rig.expect(rig.ptr(state.pose) + offset, image, 'pose buffer')
                cases += 1
                joints += clip.joint_count
        except (Mismatch, EmuError, A.HostFault, VuUnknown, IndexError) as error:
            failures += 1
            examples.append('%s: %s: %s' % (clip_name, type(error).__name__, error))
            rig = Rig(elf, config)
            state = rig.new_state(1)
    report(name, failures, cases, 'position and quaternion of every joint (%d joint samples on %d clips) '
           'as anim_buildPose forms them, bit for bit; and the one-track pose buffer' % (joints, len(clips)),
           examples)


def config_name(config):
    return config[0] + ('+mulbias' if config[1] else '') + ('+divnearest' if config[2] else '')


def prop_scenes(elf, library, rng, config, name, text, scenes, length, **kind):
    name = '%s [%s]' % (name, config_name(config))
    if not wanted(name):
        return
    total, failures, examples = run_scenes(elf, library, rng, config, scenes, length, **kind)
    report(name, failures, total, '%d sequences: %s' % (scenes, text), examples)


def find_inputs(positional):
    elf = clips = None
    for item in positional:
        if os.path.isdir(item):
            clips = item
        elif os.path.isfile(item):
            elf = item
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73'):
            if os.path.isfile(candidate):
                elf = candidate
                break
    return elf, clips


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = []
    while argv:
        arg = argv.pop(0)
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '--all':
            OPTIONS['all'] = True
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--seed':
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif arg == '-k':
            OPTIONS['filter'] = argv.pop(0)
        else:
            positional.append(arg)
    elf, clip_dir = find_inputs(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
        return 0
    if clip_dir is None or not any(n.lower().endswith('.anm') for n in os.listdir(clip_dir)):
        print('SKIP  no directory of .anm files given (extract some from your own disc with '
              'tools/gob.py and pass the directory); nothing was tested')
        return 0
    started = time.time()
    library = Library(clip_dir, random.Random(OPTIONS['seed']))
    print('executable %s, %d clips in %s, seed %d' % (elf, len(library.names), clip_dir, OPTIONS['seed']))

    for number, config in enumerate(FPU_CONFIGS):
        rng = random.Random(OPTIONS['seed'] * 31 + number)
        library.rng = rng
        share = 1 if number == 0 else 8
        if number == 0 and OPTIONS['all']:
            decode_clips = [n for n in library.names if library.usable(n)]
        else:
            decode_clips = library.sample(scaled(600, share))
        prop_decoder(elf, library, rng, config, decode_clips)
        prop_joint_values(elf, library, rng, config, library.sample(scaled(240, share)))
        prop_scenes(elf, library, rng, config, 'advance', 'every push/start/stop/sync/... and anim_advance '
                    'on mixed clips: event bits, root x/y, yaw, the whole state, its decoder slots, '
                    'sound ranges, bit for bit', scaled(120, share), 220, mixed=True, family=6)
        prop_scenes(elf, library, rng, config, 'advance, sounds', 'the same on clip families with sound '
                    'tables', scaled(40, share), 220, sound=True)
        prop_scenes(elf, library, rng, config, 'advance, 6 slots', 'the same with the decoder list cut '
                    'to 6 slots, so that slots are stolen', scaled(40, share), 220, slots=6, mixed=True,
                    family=6)
        prop_scenes(elf, library, rng, config, 'Creature_stepAnim', 'speed, slow factor, scale and facing '
                    'around anim_advance: events, world delta, yaw, state, bit for bit',
                    scaled(40, share), 200, stepper='creature')
        prop_scenes(elf, library, rng, config, 'Player_animStep', 'the same for the player wrapper',
                    scaled(30, share), 200, stepper='player', yaw=False)
        prop_scenes(elf, library, rng, config, 'pose', 'queries and draws between the operations: blended '
                    'local transforms, pose buffers, joint matrices, attach and sample points, buffer '
                    'lists and stamps, bit for bit (VU0 by the interpreter in this file)',
                    scaled(60, share), 160, pose=True)
        prop_scenes(elf, library, rng, config, 'pose, 5 buffers', 'the same with the pose list cut to 5 '
                    'buffers, so that the fallback buffer and the default pose are used',
                    scaled(30, share), 160, pose=True, buffers=5)

    if COVER:
        print('reached by the sequences (all FPU models together):')
        for what in sorted(COVER):
            print('    %-52s %7d' % (what, COVER[what]))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
