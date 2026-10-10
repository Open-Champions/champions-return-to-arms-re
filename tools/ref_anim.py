#!/usr/bin/env python3
"""ref_anim.py - reference model of the animation system of Champions: Return to Arms
(SLUS_209.73, US v2.00): decoding a clip, advancing an animation state, building a pose.

A research tool, not game code.  Every function was written from the instruction sequence
at the address given in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_anim.py.  docs/spec/animation.md is the prose version.
Standard library plus tools/ref_core.py (the math library model); no game data is embedded:
you give it .anm files from your own disc.

    import ref_anim as A
    system = A.AnimSystem()                       # the pools and globals of anim_init
    clip = A.Clip(open('walk.anm', 'rb').read())  # one .anm file
    state = A.AnimState(capacity=8)               # what a creature embeds at +0x114
    A.anim_push(state, clip, A.LOOP | A.ROOT)
    for tick in range(100):
        events, dx, dy, yaw = A.anim_advance(system, A.ONE, state)
    matrix = A.anim_get_joint_matrix(system, state, 3)        # 12 float patterns

Floats are raw 32-bit patterns
    Animation time, weights and root motion feed the lockstep simulation, and the console's
    FPU is not IEEE 754.  As in ref_core, every float here is an int holding the 32-bit
    pattern and all arithmetic goes through ref_core's Fpu (ref_core.set_fpu selects the
    adder model for both modules).  ref_core.f32() makes a pattern from a Python float,
    ref_core.to_float() turns one back.

What each part mirrors

    Clip                       the .anm header as the code reads it; anm_relocate 0x1707b8
    DecoderPool                the decoder slots of anim_init 0x16f9a8; animcache_alloc 0x16e388
    animtrack_decode           0x16e468
    anim_clear, anim_push, anim_push_with_weights, anim_push_chained
                               0x1707b0, 0x170838, 0x1708c0, 0x170938
    anim_start, anim_start_blend_in_out, anim_stop
                               0x16cfe0, 0x16ceb0, 0x16d1a0
    anim_drop_non_persistent, anim_release_caches, anim_state_dtor
                               0x16cb50, 0x171118, 0x171098
    anim_sync_to_sim_frame, anim_randomize_top_time, anim_sync_top_to_below
                               0x1709f8, 0x16d0b8, 0x170b08
    anim_jump_top_to_end, anim_snap_top_to_end
                               0x170bc8, 0x170c80
    anim_find_track, anim_find_track_by_flag
                               0x170d88, 0x171178
    anim_fade_in_track, anim_fade_out_track, anim_set_track_weight
                               0x170e00, 0x170ee8, 0x170fc8 (no caller found)
    anim_advance               0x16d748
    anim_state_copy            AnimState_copy 0x16ffe8 (and AnimState_copySmall 0x16fbc8)
    creature_step_anim, player_anim_step
                               the part of Creature_stepAnim 0x1162b0 and Player_animStep
                               0x1b9520 around the call of anim_advance
    quat_strip_yaw             0x16caa8
    PosePool, anim_build_pose  the pose buffers of anim_init; anim_buildPose 0x16ed40 with
                               the VU0 microprogram at 0x3e5c50 (entries 2 and 4)
    anim_emit_pose             the cache side of anim_emitPose 0x16f880 (not its display list)
    anim_get_joint_matrix      0x16f720
    model_get_attach_point     0x1754a0
    model_get_sample_point     0x178e18

Memory, not objects
    The original keeps tracks in a fixed array inside the state and moves them with block
    copies; a removed track's bytes stay where they were and some of them are read again
    (a stale decoder-slot pointer by the next push, stale flags by animcache_alloc).  The
    model therefore keeps one Track cell per array element for the whole life of a state
    and copies fields between cells exactly where the original copies bytes.  A decoder
    slot keeps the values of 64 joints whatever the clip's joint count; what an earlier
    clip left there is read by the pose builder when clips of different joint counts are
    blended.

Where the model stops
    Where the original would read or write outside its own structures (a clip with more
    than 64 joints, anim_pushChained on an empty state, root motion with no output
    pointer, a decoder pool in which every slot is protected) the model raises HostFault
    and says what the original would have done.  Playing a sound event is not modelled:
    anim_advance records which event ranges it would hand to animsound_fireRange
    (0x16d558) in AnimSystem.sound_log.  That function draws from the cosmetic random
    generator, which anim_randomize_top_time also uses; a caller that needs both in step
    must advance AnimSystem.cosmetic_seed for the sounds itself.
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))   # append: tools/dis.py must not shadow the library
import ref_core as C                                    # noqa: E402

add, sub, mul, div = C.add, C.sub, C.mul, C.div
neg, from_int, to_int = C.neg, C.from_int, C.to_int
lt, le, eq = C.lt, C.le, C.eq
s16, s32 = C.s16, C.s32

M32 = 0xFFFFFFFF
ZERO = 0x00000000
ONE = 0x3F800000
FOUR = 0x40800000
SIXTY = 0x42700000              # 60.0
K60 = 0x3C888888                # 1/60 as the compiler stored it (truncated)
K_STEP = 0x3F7FFFFF             # 0.99999994: one tick of track time at speed 1
K_POS = 0x3C800000              # 1/64     initial positions, bind offsets, pose translation
K_QUAT = 0x39800000             # 1/4096   initial quaternions, pose rotation
K_PVEL = 0x3B800000             # 1/256    position velocity per tick
K_QVEL = 0x37000000             # 1/131072 quaternion velocity per tick
K_SAMPLE = 0x3D800000           # 1/16     sample point coordinates
K_BLEND_MIN = 0x3A83126E        # 0.001: a track blended with less than this is skipped
K_PI = 0x40490FDA
K_TWO_PI = 0x40C90FDA
K_MINUS_PI = 0xC0490FDA
K_RAND = 0x37800000             # 1/65536

# track flags (the u16 at track+0x1c)
LOOP = 0x0001                   # wrap at the end
PURGE_BELOW = 0x0002            # once fully blended in, delete the tracks below
REPORT_END = 0x0004             # hold the last frame and raise status 0x80 (0x400 on top)
TALK = 0x0020                   # cutscene marker; the engine does not test it
FIXED_STEP = 0x0040             # ignore the speed argument
EASE = 0x0100                   # smoothstep the blend weight
KEEP = 0x0200                   # not removed when its life reaches 0
ROOT = 0x0800                   # joint 0's x/y leave the pose and are returned as a delta
PERSISTENT = 0x1000             # survives PURGE_BELOW and anim_drop_non_persistent
PAUSED = 0x2000                 # time does not advance
YAW = 0x4000                    # joint 0's heading leaves the pose and is returned as a delta
PROTECTED = ROOT | YAW          # a decoder slot of such a track is never stolen

# status bits in state+6 (next to the union of the track flags)
STATUS_ENDED = 0x0080
STATUS_TOP_ENDED = 0x0400

MAX_JOINTS = 64
DECODER_SLOTS = 165             # anim_init: 0x9bd0c bytes / 0xf1c
POSE_BUFFERS = 100              # anim_init: 0x26480 bytes / 0x620
SLOT_NEW_TICK = 1000000         # what animcache_alloc stores in a slot's key tick
NOT_FOUND = -1000000000         # anim_find_track_by_flag

# indices into a decoder slot's per-joint record (0x3c bytes in the original)
PT, RT = 0, 1                   # tick of the last position / rotation key (s16)
PX, PY, PZ = 2, 3, 4            # position at that tick
VX, VY, VZ = 5, 6, 7            # position velocity per tick
QX, QY, QZ, QW = 8, 9, 10, 11   # quaternion at the rotation tick
RX, RY, RZ, RW = 12, 13, 14, 15  # quaternion velocity per tick


class HostFault(Exception):
    """The original would touch memory outside its own structures (or never return) here."""


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def fmin(a, b):
    """min.s fd, fs, ft: fs unless ft is smaller (equal values, +0 and -0 included, give fs)."""
    return a if C.Fpu.compare(a, b) <= 0 else b


def fmax(a, b):
    """max.s fd, fs, ft: fs unless ft is larger."""
    return a if C.Fpu.compare(a, b) >= 0 else b


# =======================================================================================
# 1. The clip
# =======================================================================================

class Clip:
    """One .anm file as the run-time code reads it (docs/formats/anim-audio.md has the file
    format).  Only what the animation core uses is kept:

      joint_count  +0x00   length +0x04 (ticks)   words: the key stream at +0x08 as 16-bit
      bind         +0x0c: per joint (x, y, z, w) s16, unit 1/64
      depth        +0x10: per joint one signed byte
      events       +0x14: four [seconds pattern, mask byte]; zero in every file, filled in
                   by game code after loading (creature_setDefEntryParams 0x118378), so the
                   list is mutable
      sound_times  +0x38: the tick of every sound event up to and including the 0x7fffffff
                   terminator, or None when the clip has no sound table
      sound_group  +0x3c   joint_mask +0x48 (u64; bit j set = joint j not driven)

    The decoder has no end test of its own: it stops because the next key's tick lies
    beyond the track time.  The exporter closes every stream with a tick delta of 255, so
    in a clip whose last key lies 255 ticks or more before its end (two on the disc) the
    original goes on to decode the padding and then whatever follows the clip in memory.
    The model raises HostFault when a record starts beyond the end of the file."""

    HEADER = 0x70

    def __init__(self, data, name=''):
        data = bytes(data)
        if len(data) < self.HEADER:
            raise ValueError('an .anm file has a 0x70-byte header')
        self.name = name
        self.data = data
        (self.joint_count, self.length, key_off, bind_off,
         depth_off) = struct.unpack_from('<iiIII', data, 0)
        self.events = []
        for k in range(4):
            seconds, mask = struct.unpack_from('<IB', data, 0x14 + 8 * k)
            self.events.append([seconds, mask])
        name_off, sound_off = struct.unpack_from('<II', data, 0x34)
        self.sound_group = data[0x3C]
        self.joint_mask = struct.unpack_from('<Q', data, 0x48)[0]
        if not 0 <= self.joint_count <= MAX_JOINTS:
            raise HostFault('joint count %d: a decoder slot and a pose buffer hold 64'
                            % self.joint_count)
        n = self.joint_count
        if bind_off + 8 * n > len(data) or depth_off + n > len(data) or key_off > len(data):
            raise ValueError('skeleton tables outside the file')
        self.bind = [struct.unpack_from('<4h', data, bind_off + 8 * j) for j in range(n)]
        self.depth = [s8(data[depth_off + j]) for j in range(n)]
        stream = data[key_off:]
        if len(stream) & 1:
            stream += b'\0'
        self.words = struct.unpack('<%dH' % (len(stream) // 2), stream)
        self.sound_times = None
        if sound_off:
            times = []
            pos = sound_off
            while True:
                if pos + 4 > len(data):
                    raise ValueError('sound event list without terminator')
                tick = struct.unpack_from('<i', data, pos)[0]
                times.append(tick)
                if tick == 0x7FFFFFFF:
                    break
                pos += 0x1C
            self.sound_times = times

    def word(self, index):
        words = self.words
        return words[index] if 0 <= index < len(words) else 0

    def __repr__(self):
        return '<Clip %s joints=%d length=%d>' % (self.name or '?', self.joint_count, self.length)


def encode_clip(joints, length, keys=(), depth=None, bind=None, joint_mask=0,
                sound_times=None, sound_group=0, width=None):
    """Build the bytes of a synthetic .anm (for tests; real clips come from the disc).

    joints   per joint ((x, y, z), (w, x, y, z)): initial position in 1/64 and quaternion
             in 1/4096, as integers
    keys     (tick, joint, 'p' or 'r', values) sorted by tick: three position velocities
             in 1/256 per tick or four quaternion velocities (w, x, y, z) in 1/131072
    depth    per joint depth (default: joint 0 a root, every other joint its child)
    bind     per joint (x, y, z) in 1/64 (default 0)
    width    fixed field width in bits; default: the smallest that holds the values
    The stream ends, as on the disc, with a tick delta of 255 and zero padding."""
    n = len(joints)
    bits = []

    def put(value, count):
        for k in range(count - 1, -1, -1):
            bits.append((value >> k) & 1)

    def need(values):
        if width is not None:
            return width
        w = 1
        while any(not -(1 << (w - 1)) <= v < (1 << (w - 1)) for v in values):
            w += 1
        if w > 16:
            raise ValueError('value does not fit 16 bits')
        return w

    for pos, quat in joints:
        w = need(pos)
        put(w - 1, 4)
        for v in pos:
            put(v, w)
        w = need(quat)
        put(w - 1, 4)
        for v in quat:
            put(v, w)
    last = 0
    for tick, joint, kind, values in keys:
        if not 0 <= tick - last <= 255:
            raise ValueError('key ticks must rise by at most 255')
        put(tick - last, 8)
        last = tick
        put(1 if kind == 'p' else 0, 1)
        put(joint, 6)
        if len(values) != (3 if kind == 'p' else 4):
            raise ValueError('a position key has 3 values, a rotation key 4')
        w = need(values)
        put(w - 1, 4)
        for v in values:
            put(v, w)
    put(255, 8)
    while len(bits) % 32:
        bits.append(0)
    stream = bytearray()
    for i in range(0, len(bits), 16):
        word = 0
        for b in bits[i:i + 16]:
            word = (word << 1) | b
        stream += struct.pack('<H', word)

    depth = list(depth) if depth is not None else [0] + [1] * (n - 1)
    bind = list(bind) if bind is not None else [(0, 0, 0)] * n
    depth_off = 0x70
    bind_off = (depth_off + n + 7) & ~7
    key_off = bind_off + 8 * n
    out = bytearray(key_off)
    struct.pack_into('<iiIII', out, 0, n, length, key_off, bind_off, depth_off)
    out[0x3C] = sound_group & 0xFF
    struct.pack_into('<Q', out, 0x48, joint_mask)
    for j in range(n):
        out[depth_off + j] = depth[j] & 0xFF
        struct.pack_into('<4h', out, bind_off + 8 * j, bind[j][0], bind[j][1], bind[j][2], 0)
    out += stream
    if sound_times is not None:
        struct.pack_into('<I', out, 0x38, len(out))
        for tick in list(sound_times) + [0x7FFFFFFF]:
            out += struct.pack('<i', tick) + bytes(0x18)
    return bytes(out)


# =======================================================================================
# 2. Decoder slots (the key-stream cache)
# =======================================================================================

class DecoderSlot:
    """One of the 165 slots of 0xf1c bytes at 0x6f6180.

      +0x00 clip    the key stream being decoded (the model keeps the Clip)
      +0x04 cursor  bit position of the next key record
      +0x08 tick    tick of the last key consumed; 1000000 right after allocation
      +0x0c/+0x10   list links (DecoderPool.order)
      +0x14 owner   the track cell using the slot, or None
      +0x18 yaw     s16: heading of joint 0 at the last root-yaw step
      +0x1c joints  64 records of 0x3c bytes, see PT..RW"""

    def __init__(self, index):
        self.index = index
        self.clip = None
        self.cursor = 0
        self.tick = 0
        self.owner = None
        self.yaw = 0
        self.joints = [[0] * 16 for _ in range(MAX_JOINTS)]


class DecoderPool:
    """The slot list of anim_init (0x16f9a8).  order[0] is the least recently used slot
    (g_animCacheLruHead 0x791e90), order[-1] the most recently used (0x791e8c).  After
    anim_init the head is slot 164 and the tail slot 0, so slots are first handed out
    from the highest address down."""

    def __init__(self, count=DECODER_SLOTS):
        if count < 2:
            raise ValueError('the list code needs at least two slots')
        self.slots = [DecoderSlot(i) for i in range(count)]
        self.order = list(reversed(self.slots))

    def touch(self, slot):
        """The move-to-tail at the top of animtrack_decode (0x16e4bc-0x16e508)."""
        order = self.order
        if order[-1] is not slot:
            order.remove(slot)
            order.append(slot)

    def alloc(self):
        """animcache_alloc 0x16e388: take the least recently used slot.

        A head slot whose owner track has ROOT or YAW set is moved to the tail instead
        and the next one is tried: for those tracks the slot holds the root-motion base,
        which is simulation state and cannot be rebuilt.  The owner's flags are read from
        the track cell as it is now, live or stale.  The previous owner loses its slot
        pointer.  Of the slot's contents only the key tick (1000000, which forces the next
        decode to start over) and joint 0's position x and y (0.0) are reset; everything
        else, the yaw at +0x18 included, keeps what the last user left."""
        order = self.order
        tries = 0
        while order[0].owner is not None and order[0].owner.flags & PROTECTED:
            order.append(order.pop(0))
            tries += 1
            if tries > len(order):
                raise HostFault('every decoder slot belongs to a root-motion track: '
                                'animcache_alloc never returns')
        slot = order.pop(0)
        if slot.owner is not None:
            slot.owner.slot = None
        order.append(slot)
        slot.tick = SLOT_NEW_TICK
        slot.joints[0][PX] = ZERO
        slot.joints[0][PY] = ZERO
        slot.owner = None
        return slot


def quat_yaw(x, y, z, w):
    """The heading of a quaternion as a 16-bit angle, inline at 0x16e878, 0x16dda8, 0x16e2c0
    and in quat_stripYaw:  atan2_16(2(xy + zw), ((xx - yy) - zz) + ww)."""
    side = add(mul(x, y), mul(z, w))
    return C.atan2_16(add(side, side), add(sub(sub(mul(x, x), mul(y, y)), mul(z, z)), mul(w, w)))


def quat_strip_yaw(q):
    """quat_stripYaw 0x16caa8 (a0 q, in place) -> (new q, yaw): multiply from the left by a
    rotation of -yaw about Z built by quat_fromAxisAngle (0x1663c0)."""
    yaw = quat_yaw(q[0], q[1], q[2], q[3])
    turn = C.quat_from_axis_angle(ZERO, ZERO, ONE, s16(-yaw))
    return C.quat_mul(turn, q), yaw


def _field(clip, bit, width):
    """width bits at bit position `bit`, most significant bit of each 16-bit word first,
    as the 32-bit pattern the code holds before its final shift."""
    index = bit >> 4
    words = clip.words
    if index + 1 < len(words):
        pair = (words[index] << 16) | words[index + 1]
    else:
        if bit + width > 16 * len(words):
            raise HostFault('the key stream ran out at bit %d: the original decodes the '
                            'memory after the clip' % bit)
        pair = (clip.word(index) << 16) | clip.word(index + 1)
    return (pair << (bit & 15)) & M32


def _unsigned(clip, bit, width):
    return _field(clip, bit, width) >> (32 - width)


def _signed(clip, bit, width):
    return s32(_field(clip, bit, width)) >> (32 - width)


def animtrack_decode(system, track):
    """animtrack_decode 0x16e468 (a0 track): bring the track's decoder slot up to the
    integer part of the track time.

    1. A track without a slot gets one from DecoderPool.alloc.  The slot becomes the most
       recently used.
    2. T = cvt.w.s(time) (toward zero, so -0.9 gives 0).  If T is less than the slot's key
       tick the slot starts over: for every joint both key ticks become 0, the initial
       position and quaternion are read and both velocities become 0.  For a ROOT track
       the x and y of joint 0 are skipped in the stream and KEEP their slot values (the
       root-motion base).  The heading of joint 0's initial quaternion goes to slot.yaw.
    3. Key records are consumed while (key tick + next delta) <= T.  A key first advances
       the joint's value to the key's tick with the old velocity, then stores the new
       velocity and the tick.

    Decoding only moves forward: seeking back (or wrapping) costs a restart, seeking
    forward is incremental.  The value of a joint at the track time t is

        position   = pos + vel * (t - PT)        quaternion = quat + qvel * (t - RT)

    with t the float time, not T; every reader below forms it that way."""
    slot = track.slot
    if slot is None:
        slot = system.decoders.alloc()
        slot.owner = track
        track.slot = slot
    system.decoders.touch(slot)
    clip = track.clip
    target = to_int(track.time)
    joints = slot.joints
    if target < slot.tick:
        slot.tick = 0
        bit = 0
        root = track.flags & ROOT
        for j in range(clip.joint_count):
            if j >= MAX_JOINTS:
                raise HostFault('joint %d: outside the decoder slot' % j)
            rec = joints[j]
            rec[PT] = rec[RT] = 0
            width = _unsigned(clip, bit, 4) + 1
            bit += 4
            if root and j == 0:
                bit += 2 * width
            else:
                rec[PX] = mul(from_int(_signed(clip, bit, width)), K_POS)
                rec[PY] = mul(from_int(_signed(clip, bit + width, width)), K_POS)
                bit += 2 * width
            rec[PZ] = mul(from_int(_signed(clip, bit, width)), K_POS)
            bit += width
            width = _unsigned(clip, bit, 4) + 1
            bit += 4
            rec[QW] = mul(from_int(_signed(clip, bit, width)), K_QUAT)
            rec[QX] = mul(from_int(_signed(clip, bit + width, width)), K_QUAT)
            rec[QY] = mul(from_int(_signed(clip, bit + 2 * width, width)), K_QUAT)
            rec[QZ] = mul(from_int(_signed(clip, bit + 3 * width, width)), K_QUAT)
            bit += 4 * width
            rec[VX] = rec[VY] = rec[VZ] = ZERO
            rec[RX] = rec[RY] = rec[RZ] = rec[RW] = ZERO
        slot.cursor = bit
        slot.clip = clip
        first = joints[0]
        slot.yaw = quat_yaw(first[QX], first[QY], first[QZ], first[QW])
    clip = slot.clip                    # the key loop reads the stream pointer of the SLOT
    if clip is None:
        raise HostFault('decoder slot without a stream')
    while True:
        bit = slot.cursor
        tick = slot.tick + _unsigned(clip, bit, 8)
        if target < tick:
            return slot
        slot.tick = tick
        is_position = _unsigned(clip, bit + 8, 1)
        rec = joints[_unsigned(clip, bit + 9, 6)]
        width = _unsigned(clip, bit + 15, 4) + 1
        bit += 19
        if is_position:
            dt = from_int(tick - rec[PT])
            dx, dy, dz = mul(rec[VX], dt), mul(rec[VY], dt), mul(rec[VZ], dt)
            rec[PX] = add(rec[PX], dx)
            rec[PY] = add(rec[PY], dy)
            rec[PZ] = add(rec[PZ], dz)
            rec[VX] = mul(from_int(_signed(clip, bit, width)), K_PVEL)
            rec[VY] = mul(from_int(_signed(clip, bit + width, width)), K_PVEL)
            rec[VZ] = mul(from_int(_signed(clip, bit + 2 * width, width)), K_PVEL)
            rec[PT] = s16(tick)
            bit += 3 * width
        else:
            dt = from_int(tick - rec[RT])
            for k in range(4):
                rec[QX + k] = add(rec[QX + k], mul(rec[RX + k], dt))
            rec[RW] = mul(from_int(_signed(clip, bit, width)), K_QVEL)
            rec[RX] = mul(from_int(_signed(clip, bit + width, width)), K_QVEL)
            rec[RY] = mul(from_int(_signed(clip, bit + 2 * width, width)), K_QVEL)
            rec[RZ] = mul(from_int(_signed(clip, bit + 3 * width, width)), K_QVEL)
            rec[RT] = s16(tick)
            bit += 4 * width
        slot.cursor = bit


def joint_quat(slot, joint, time):
    """quat + qvel * (time - RT), components x, y, z, w (not normalised)."""
    rec = slot.joints[joint]
    dt = sub(time, from_int(rec[RT]))
    return [add(rec[QX + k], mul(rec[RX + k], dt)) for k in range(4)]


def joint_pos(slot, joint, time):
    """pos + vel * (time - PT)."""
    rec = slot.joints[joint]
    dt = sub(time, from_int(rec[PT]))
    return [add(rec[PX + k], mul(rec[VX + k], dt)) for k in range(3)]


def decode_clip(clip, time, flags=0, system=None):
    """Convenience: the joint values of a clip at one time, through a private pool.
    Returns [(position xyz, quaternion xyzw)] as patterns; quaternions are not normalised
    (the pose builder does that)."""
    system = system or AnimSystem(decoder_slots=2, pose_buffers=2)
    track = Track()
    track.clip, track.flags, track.time = clip, flags, time
    slot = animtrack_decode(system, track)
    return [(joint_pos(slot, j, time), joint_quat(slot, j, time))
            for j in range(clip.joint_count)]


# =======================================================================================
# 3. The animation state
# =======================================================================================

class Track:
    """One 0x20-byte element of the track array.

      +0x00 clip   +0x04 slot (decoder slot or None)
      +0x08 weight   +0x0c rate (weight change per tick)
      +0x10 life     +0x14 life_rate (0 or negative)
      +0x18 time (ticks, a float)   +0x1c flags (u16)   +0x1e sound_idx (s16)

    The weight a track blends with is min(weight, life), limited to 0..1."""

    __slots__ = ('clip', 'slot', 'weight', 'rate', 'life', 'life_rate', 'time', 'flags',
                 'sound_idx')

    def __init__(self):
        self.clip = None
        self.slot = None
        self.weight = self.rate = self.life = self.life_rate = self.time = ZERO
        self.flags = 0
        self.sound_idx = 0

    def copy_from(self, other):
        """The 0x20-byte block copy.  The slot's owner pointer is NOT changed here; each
        caller fixes it up (or not) the way the original does."""
        if other is self:
            return
        for name in self.__slots__:
            setattr(self, name, getattr(other, name))


class AnimState:
    """The animation state every animated object embeds (a creature at +0x114).

      +0x00 pose      the pose buffer holding this state's pose, or None
      +0x04 count     s8, tracks in use; tracks[0] is the bottom layer
      +0x05 capacity  s8
      +0x06 flags     u16: union of the flags of the tracks visited by the last
                      anim_advance, plus STATUS_ENDED / STATUS_TOP_ENDED; the push and
                      start functions OR the new track's flags in at once
      +0x08 tracks    capacity cells of 0x20 bytes"""

    def __init__(self, capacity=8):
        if not 1 <= capacity <= 127:
            raise ValueError('capacity is a positive signed byte')
        self.pose = None
        self.count = 0
        self.capacity = capacity
        self.flags = 0
        self.tracks = [Track() for _ in range(capacity)]

    def top(self):
        return self.tracks[self.count - 1] if self.count > 0 else None


class AnimSystem:
    """What the animation code keeps outside the states.

      decoders       the decoder slot pool
      poses          the pose buffer pool
      vu_mem         VU0 data memory, 256 quadwords: the matrix stack of the pose builder
                     (three rows per level; level 0 is rewritten on every build, the others
                     keep what the last joint at that depth left)
      draw_frame     g_drawFrame 0x44fdd0 (rendered frames; per machine)
      sim_frame      g_simFrame 0x44fdcc
      cosmetic_seed  g_cosmeticSeed 0x404460
      cue_throttle   g_animCueThrottle 0x7b8fe0: per sound group [low byte of the draw
                     frame, count]
      group_limits   g_soundGroupLimit 0x4f8a28, one signed byte per group (game data: pass
                     the table from your executable; the default is all zero)
      sound_log      (clip, first event, one past the last) for each animsound_fireRange
      trace          None, or a list to which anim_build_pose appends ('base', values) and
                     ('blended', values): per joint [qx, qy, qz, qw, px, py, pz] after the
                     base track and after blending (what the differential test compares
                     with the original's work area)"""

    def __init__(self, decoder_slots=DECODER_SLOTS, pose_buffers=POSE_BUFFERS,
                 group_limits=None):
        self.decoders = DecoderPool(decoder_slots)
        self.poses = PosePool(pose_buffers)
        self.vu_mem = [[ZERO] * 4 for _ in range(256)]
        self.draw_frame = 0
        self.sim_frame = 0
        self.cosmetic_seed = 0
        self.cue_throttle = [[0, 0] for _ in range(256)]
        self.group_limits = list(group_limits) if group_limits is not None else [0] * 256
        self.sound_log = []
        self.trace = None


def _release_slot(track):
    if track.slot is not None:
        track.slot.owner = None
        track.slot = None


def _rate(seconds):
    """1 / (seconds * 60), or 1.0 when seconds < 1/60 (the constant 0x3c888888)."""
    if lt(seconds, K60):
        return ONE
    return div(ONE, mul(seconds, SIXTY))


def _new_track(state, index, clip, flags, reset_sound=True, time=ZERO):
    """The common tail of the push and start functions: the state's flag word takes the
    new flags, the cell is filled, and a slot pointer left in the cell by an earlier
    track is released."""
    state.count = s8(index + 1)
    state.flags = (state.flags | flags) & 0xFFFF
    track = state.tracks[index]
    stale = track.slot
    track.clip = clip
    track.time = time
    if reset_sound:
        track.sound_idx = 0
    if stale is not None:
        stale.owner = None
        track.slot = None
    track.flags = flags & 0xFFFF
    return track


def anim_clear(state):
    """anim_clear 0x1707b0: count = 0.  Nothing else: decoder slots stay attached to the
    dead cells until a push reuses the cell or animcache_alloc takes the slot, and the
    pose pointer is not cleared."""
    state.count = 0


def anim_push(state, clip, flags):
    """anim_push 0x170838 (a0 state, a1 clip, a2 flags): append at weight 1, life 1, both
    rates 0, time 0.  Ignored when clip is null or the state is full."""
    if clip is None or not state.count < state.capacity:
        return None
    track = _new_track(state, state.count, clip, flags)
    track.rate = ZERO
    track.weight = ONE
    track.life = ONE
    track.life_rate = ZERO
    return track


def anim_push_with_weights(state, clip, flags, weight, rate, life, life_rate):
    """anim_pushWithWeights 0x1708c0 (f13 weight, f14 rate, f15 life, f16 life rate, a0
    state, a1 clip, a2 flags; f12 is not read).  Ignored when the state is full."""
    if clip is None or not state.count < state.capacity:
        return None
    track = _new_track(state, state.count, clip, flags)
    track.weight, track.rate, track.life, track.life_rate = weight, rate, life, life_rate
    return track


def anim_push_chained(state, clip, flags):
    """anim_pushChained 0x170938: append at weight 1 with time = (time of the track below
    - its clip length) + 2.0, normally negative: the track waits (anim_advance only counts
    a negative time up) and starts two ticks after the track below ends.  The sound cursor
    of the cell is NOT reset: it keeps what an earlier track left in the cell.  Ignored
    when the state is full."""
    if clip is None:
        return None
    if state.count < 1:
        raise HostFault('anim_pushChained on an empty state reads the track before the array')
    below = state.tracks[state.count - 1]
    length = from_int(below.clip.length)
    if not state.count < state.capacity:
        return None
    start = add(sub(below.time, length), C.TWO)
    track = _new_track(state, state.count, clip, flags, reset_sound=False, time=start)
    track.life_rate = ZERO
    track.rate = ZERO
    track.life = ONE
    track.weight = ONE
    return track


def _start_index(state):
    """Where anim_start puts its track: a new cell, or the top cell when the state is full
    (the old top track is replaced and its decoder slot released)."""
    index = state.count
    if not index < state.capacity:
        index -= 1
        if index < 0:
            raise HostFault('start on a state with no capacity')
        _release_slot(state.tracks[index])
    return index


def anim_start(blend_in, state, clip, flags):
    """anim_start 0x16cfe0 (f12 blend-in seconds, a0 state, a1 clip, a2 flags): a track at
    weight 0 rising by 1/(blend_in*60) per tick, life 1.  In cell 0 (an empty state, or a
    full state of capacity 1) the blend time is ignored and the rate is 1: full weight
    after one tick."""
    if clip is None:
        return None
    index = _start_index(state)
    if index == 0:
        blend_in = ZERO
    track = _new_track(state, index, clip, flags)
    track.weight = ZERO
    track.rate = _rate(blend_in)
    track.life = ONE
    track.life_rate = ZERO
    return track


def anim_start_blend_in_out(blend_in, blend_out, state, clip, flags):
    """anim_startBlendInOut 0x16ceb0 (f12 blend in, f13 blend out, a0 state, a1 clip, a2
    flags): as anim_start (but the blend-in time is honoured in cell 0 too), and
    life = ((length * 1/60) * 60) * r falling by r = 1/(blend_out*60) per tick, so life
    passes 1 blend_out seconds before the end and 0 at the end."""
    if clip is None:
        return None
    index = _start_index(state)
    track = _new_track(state, index, clip, flags)
    track.weight = ZERO
    track.rate = _rate(blend_in)
    out_rate = _rate(blend_out)
    track.life_rate = neg(out_rate)
    track.life = mul(mul(mul(from_int(clip.length), K60), SIXTY), out_rate)
    return track


def anim_release_caches(state):
    """anim_releaseCaches 0x171118: detach the pose and the decoder slot of every track in
    use."""
    if state.pose is not None:
        state.pose.owner = None
        state.pose = None
    for i in range(max(state.count, 0)):
        _release_slot(state.tracks[i])


def anim_state_dtor(state):
    """AnimState_dtor 0x171098: as anim_release_caches, but over every cell up to the
    capacity (stale ones too)."""
    if state.pose is not None:
        state.pose.owner = None
        state.pose = None
    for track in state.tracks:
        _release_slot(track)


def anim_stop(blend_out, state, clip):
    """anim_stop 0x16d1a0 (f12 blend-out seconds, a0 state, a1 clip): for every track
    playing clip -

      blend_out == 0: anim_release_caches on the WHOLE state, then the track is removed
                      (the cells above move down);
      otherwise:      weight and life are capped at 1, rate = -1/(blend_out*60) (or -1),
                      life rate = 0, and flags PERSISTENT and REPORT_END are cleared.

    A faded track is not removed when its weight reaches 0: anim_advance removes tracks by
    life only.  It stays, at a weight that keeps falling, until it ends (not looping), is
    purged by a PURGE_BELOW track above it, or is replaced."""
    if clip is None or state.count <= 0:
        return
    tracks = state.tracks
    i = 0
    while True:
        track = tracks[i]
        if track.clip is clip:
            if eq(blend_out, ZERO):
                anim_release_caches(state)
                j = i
                while j < state.count - 1:
                    tracks[j].copy_from(tracks[j + 1])
                    j += 1
                state.count = s8(state.count - 1)
                i -= 1
            else:
                if lt(ONE, track.weight):
                    track.weight = ONE
                life = track.life
                track.rate = neg(_rate(blend_out))
                if lt(ONE, life):
                    track.life = ONE
                track.life_rate = ZERO
                track.flags &= 0xEFFB
        i += 1
        if not i < state.count:
            return


def _compact(state, keep):
    """Shared by anim_dropNonPersistent and the PURGE_BELOW step of anim_advance: tracks
    for which keep(index, track) is false lose their slot and are squeezed out; a kept
    track that moves takes its slot along (the slot's owner becomes the new cell and the
    old cell's slot pointer is zeroed)."""
    tracks = state.tracks
    out = 0
    for k in range(state.count):
        track = tracks[k]
        if not keep(k, track):
            _release_slot(track)
            continue
        dst = tracks[out]
        dst.copy_from(track)
        if track.slot is not None and out != k:
            track.slot = None
            dst.slot.owner = dst
        out += 1
    state.count = out


def anim_drop_non_persistent(state):
    """anim_dropNonPersistent 0x16cb50: remove every track without PERSISTENT."""
    _compact(state, lambda k, track: track.flags & PERSISTENT)


def _rebase_root(system, track):
    """The block every time-setting function runs for a ROOT track (0x16d140, 0x170a7c,
    0x170b64, 0x170c20): decode at the new time and subtract joint 0's current x/y from
    its base, so that the jump in time is not reported as movement."""
    slot = animtrack_decode(system, track)
    rec = slot.joints[0]
    dt = sub(track.time, from_int(rec[PT]))
    y = add(rec[PY], mul(rec[VY], dt))
    x = add(rec[PX], mul(rec[VX], dt))
    rec[PY] = sub(rec[PY], y)
    rec[PX] = sub(rec[PX], x)


def anim_sync_to_sim_frame(system, state):
    """anim_syncToSimFrame 0x1709f8: every track's time becomes
    fmodf((float(g_simFrame) * 1/60) * 60, float(length)); ROOT tracks are rebased.  The
    product is not the frame number for every frame (1/60 is the truncated constant)."""
    i = 0
    while i < state.count:
        track = state.tracks[i]
        frame = mul(mul(from_int(system.sim_frame), K60), SIXTY)
        track.time = C.fmodf(frame, from_int(track.clip.length))
        if track.flags & ROOT:
            _rebase_root(system, track)
        i += 1


def anim_randomize_top_time(system, state):
    """anim_randomizeTopTime 0x16d0b8: one draw of the cosmetic generator (seed =
    seed * 0x19660d + 0x3c6ef35f; the draw is the high 16 bits); the top track's time
    becomes (float(draw) * 1/65536) * float(length); a ROOT track is rebased."""
    if state.count == 0:
        return
    track = state.tracks[state.count - 1]
    system.cosmetic_seed = (system.cosmetic_seed * 0x19660D + 0x3C6EF35F) & M32
    draw = system.cosmetic_seed >> 16
    track.time = mul(mul(from_int(draw), K_RAND), from_int(track.clip.length))
    if track.flags & ROOT:
        _rebase_root(system, track)


def anim_sync_top_to_below(system, state):
    """0x170b08 (no caller found): with two or more tracks, the top track takes the time
    of the track below it, or 0 when that is at or past its own length; ROOT rebased."""
    if state.count < 2:
        return
    track = state.tracks[state.count - 1]
    track.time = state.tracks[state.count - 2].time
    if le(from_int(track.clip.length), track.time):
        track.time = ZERO
    if track.flags & ROOT:
        _rebase_root(system, track)


def anim_jump_top_to_end(system, state):
    """anim_jumpTopToEnd 0x170bc8: detach the pose; top track time = float(length); a ROOT
    track is rebased."""
    if state.pose is not None:
        state.pose.owner = None
        state.pose = None
    if state.count == 0:
        return
    track = state.tracks[state.count - 1]
    track.time = from_int(track.clip.length)
    if track.flags & ROOT:
        _rebase_root(system, track)


def anim_snap_top_to_end(state):
    """anim_snapTopToEnd 0x170c80: detach the pose; top track weight = life = 1 and time =
    float(length).  No rebase."""
    if state.pose is not None:
        state.pose.owner = None
        state.pose = None
    if state.count == 0:
        return
    track = state.tracks[state.count - 1]
    track.life = ONE
    track.weight = ONE
    track.time = from_int(track.clip.length)


def anim_find_track(state, clip):
    """anim_findTrack 0x170d88 -> the first track playing clip, or None."""
    if state is None or clip is None:
        return None
    for i in range(state.count):
        if state.tracks[i].clip is clip:
            return state.tracks[i]
    return None


def anim_find_track_by_flag(state, mask):
    """anim_findTrackByFlag 0x171178 -> index of the first track with any bit of mask, or
    -1000000000."""
    for i in range(state.count):
        if s16(state.tracks[i].flags) & mask:
            return i
    return NOT_FOUND


def anim_fade_in_track(blend_in, state, clip):
    """0x170e00 (no caller found): the track playing clip gets weight = max(min(weight,
    life), 0), rate = 1/(blend_in*60) and life = 1."""
    track = anim_find_track(state, clip)
    if track is None:
        return
    weight = fmin(track.weight, track.life)
    track.weight = ZERO if lt(weight, ZERO) else weight
    track.rate = _rate(blend_in)
    track.life = ONE


def anim_fade_out_track(blend_out, state, clip):
    """0x170ee8 (no caller found): weight = min(weight, life, 1), rate = -1/(blend_out*60)
    and life = 0 (so anim_advance removes the track on its next step unless it has KEEP)."""
    track = anim_find_track(state, clip)
    if track is None:
        return
    weight = fmin(track.weight, track.life)
    track.weight = ONE if lt(ONE, weight) else weight
    track.life = ZERO
    track.rate = neg(_rate(blend_out))


def anim_set_track_weight(weight, state, clip):
    """0x170fc8 (no caller found): weight as given, life 1, both rates 0."""
    track = anim_find_track(state, clip)
    if track is None:
        return
    track.weight = weight
    track.life = ONE
    track.life_rate = ZERO
    track.rate = ZERO


def anim_state_copy(system, src):
    """AnimState_copy 0x16ffe8 (a0 dst, a1 src; 0x108 bytes = a state of eight cells) and
    AnimState_copySmall 0x16fbc8 (0x28 bytes = a state of one cell): copy the state,
    detach the pose, and for every cell up to the capacity -

      the source cell has no slot, or the cell's flags have neither ROOT nor YAW: no slot;
      otherwise a slot of its own from animcache_alloc, with the stream, cursor, key tick
      and all 64 joint records copied from the source's slot.

    The yaw at slot+0x18 is NOT copied: the copy's first root-yaw step measures from
    whatever the freshly allocated slot held."""
    dst = AnimState(src.capacity)
    dst.count, dst.flags = src.count, src.flags
    for i in range(src.capacity):
        dst.tracks[i].copy_from(src.tracks[i])
        dst.tracks[i].slot = None
    for i in range(dst.capacity):
        cell, source = dst.tracks[i], src.tracks[i].slot
        if source is None or not cell.flags & PROTECTED:
            continue
        slot = system.decoders.alloc()
        cell.slot = slot
        slot.owner = cell
        source = src.tracks[i].slot             # re-read after the allocation
        if source is None:
            raise HostFault('the allocation took the source slot itself')
        slot.clip, slot.cursor, slot.tick = source.clip, source.cursor, source.tick
        slot.joints = [list(rec) for rec in source.joints]
    return dst


# ---- the per-tick step -------------------------------------------------------------------

def _remove_track(state, index):
    """0x16ded4-0x16dfa4: release the slot, move the cells above down one place (each
    moved slot's owner follows), zero the slot pointer of the vacated top cell."""
    tracks = state.tracks
    _release_slot(tracks[index])
    j = index
    while j < state.count - 1:
        tracks[j].copy_from(tracks[j + 1])
        if tracks[j].slot is not None:
            tracks[j].slot.owner = tracks[j]
        j += 1
    tracks[state.count - 1].slot = None
    state.count = s8(state.count - 1)


class _EventTicks:
    """The ticks of a clip's sound events as floats; an index outside the table (possible
    only through a cursor left in the cell, see anim_push_chained) is a host fault."""

    def __init__(self, times):
        self.times = times

    def raw(self, index):
        if not 0 <= index < len(self.times):
            raise HostFault('sound cursor %d outside the event table: the original reads '
                            'the memory around it' % index)
        return self.times[index]

    def __getitem__(self, index):
        return from_int(self.raw(index))

    def run_end(self, first):
        """One past the run of events that share the tick of event `first`."""
        end = first + 1
        if self.raw(end) == self.raw(first):
            while True:
                end += 1
                if self.raw(end) != self.raw(first):
                    break
        return end


def _step_sounds(system, state, track, old_time, flags):
    """The sound part of anim_advance (0x16d91c-0x16dc08): top track only, and only when
    the caller passed a position.  The track's cursor (sound_idx) is the index of the next
    event; events whose tick is below the new time are fired in runs of equal tick."""
    clip = track.clip
    ticks = _EventTicks(clip.sound_times)
    index = track.sound_idx
    if index > 0 and le(old_time, ticks[index - 1]):
        track.sound_idx = index = 0             # time went back: start over
    if lt(ticks[index], old_time):              # time went forward without sounds: skip
        while True:
            index = s16(index + 1)
            if not lt(ticks[index], old_time):
                break
        track.sound_idx = index
    muted = False
    group = clip.sound_group
    if group:
        cell = system.cue_throttle[group]
        frame = system.draw_frame & 0xFF
        if cell[0] != frame:
            cell[0], cell[1] = frame, 1
        elif s8(system.group_limits[group]) - 2 < cell[1]:
            muted = True                        # too many cues of this group this picture
        else:
            cell[1] = (cell[1] + 1) & 0xFF
    time = track.time
    index = track.sound_idx
    while lt(ticks[index], time):
        end = ticks.run_end(index)
        if not muted:
            system.sound_log.append((clip, index, end))
        track.sound_idx = index = s16(end)
    length = from_int(clip.length)
    if le(length, time) and flags & LOOP:
        wrapped = sub(time, length)
        track.sound_idx = 0
        if lt(ticks[0], wrapped):
            while True:
                first = track.sound_idx
                end = ticks.run_end(first)
                if not muted:
                    system.sound_log.append((clip, first, end))
                track.sound_idx = s16(end)
                if not lt(ticks[track.sound_idx], wrapped):
                    break


def anim_advance(system, speed, state, sound=True, want_root=True, want_yaw=True):
    """anim_advance 0x16d748 (f12 speed, a0 state, a1 sound position or 0, a2 root delta
    out[2] or 0, a3 yaw delta out or 0) -> (event bits, root dx, root dy, yaw delta).

    The event bits are a signed byte (the code sign-extends as it ORs), the deltas are
    None when the caller passed no pointer, the yaw delta is a signed 16-bit angle.

    Order of operations.  step = speed * 0.99999994.  The pose is detached.  Then, from the
    TOP track down, with `left` (the weight not yet used by tracks above) starting at 1:

      a. flags join the union.  Each of the clip's four event slots whose seconds value s
         satisfies  time/60 <= s < time/60 + step/60  (old time; 1/60 is 0x3c888888) adds
         its mask - also for a paused or waiting track, and with `step` even when the
         track advances by the fixed step.
      b. unless PAUSED: time += step (FIXED_STEP: += 0.99999994).  A track whose time is
         still negative is done for this tick.
      c. sounds (_step_sounds).
      d. raw = min(weight, life); w = clamp(min(raw, left), 0, 1) is the track's root-
         motion weight for a wrap in this tick; a clip with a zero joint mask takes
         max(raw, 0) out of `left`.
      e. at the end (float(length) <= time):
           LOOP:        ROOT: joint 0's x/y at exactly `length`, times w, goes to the root
                        delta and the base becomes 0.  YAW: the heading at `length` minus
                        the slot's yaw is added to the yaw delta.  Then time -= length
                        until it is below length.
           REPORT_END:  time = length, STATUS_ENDED joins the union (STATUS_TOP_ENDED too
                        for the top track).
           otherwise:   life = life rate = 0.
      f. weight += rate, life += life rate (each rate times `speed` - not `step` - unless
         FIXED_STEP).
      g. life <= 0 and not KEEP: the track is removed.
         Else, with PURGE_BELOW, min(weight, life) >= 1 and a track below: every track
         below without PERSISTENT is removed AND THE LOOP ENDS - surviving lower tracks
         are not stepped in this tick and their flags do not join the union.  The test
         is repeated on every tick, so they stay frozen while this track is above them
         at full weight.

    Then state.flags = union, and two more passes over the tracks that are left:

      root:  if the union has ROOT, from the top down with a fresh `left` and the weights
             as they are NOW (after step f): every ROOT track is decoded at its time, its
             x/y since the last step, times its weight, is added to the delta, and taken
             off the slot's base.  A waiting (negative-time) track is not skipped here.
      yaw:   if the union has YAW, from the bottom up: for every YAW track the heading at
             its time minus slot.yaw is added (16-bit wrap), unweighted, and stored."""
    step = mul(speed, K_STEP)
    left = ONE
    events = 0
    union = 0
    if state.pose is not None:
        state.pose.owner = None
        state.pose = None
    root = [ZERO, ZERO] if want_root else None
    yaw = 0 if want_yaw else None
    tracks = state.tracks
    i = state.count - 1
    while i >= 0:
        track = tracks[i]
        clip = track.clip
        flags = track.flags
        old_time = track.time
        union |= s16(flags)
        low = mul(old_time, K60)
        high = add(low, mul(step, K60))
        for seconds, mask in clip.events:
            if le(low, seconds) and lt(seconds, high):
                events |= mask
        time = old_time
        if not flags & PAUSED:
            time = add(old_time, K_STEP if flags & FIXED_STEP else step)
            track.time = time
        if lt(time, ZERO):
            i -= 1
            continue
        if clip.sound_times is not None and sound and i == state.count - 1:
            _step_sounds(system, state, track, old_time, flags)

        weight, life = track.weight, track.life
        raw = fmin(weight, life)
        w = fmin(raw, left)
        if lt(ONE, w):
            w = ONE
        if lt(w, ZERO):
            w = ZERO
        used = ZERO if lt(raw, ZERO) else raw
        if clip.joint_mask == 0:
            left = sub(left, used)
            if lt(left, ZERO):
                left = ZERO
        length = from_int(clip.length)
        if le(length, time):
            if flags & LOOP:
                if flags & ROOT:
                    if root is None:
                        raise HostFault('ROOT track and no root output: null pointer write')
                    track.time = length
                    slot = animtrack_decode(system, track)
                    rec = slot.joints[0]
                    dt = sub(track.time, from_int(rec[PT]))
                    base_x, base_y = rec[PX], rec[PY]
                    rec[PX] = rec[PY] = ZERO
                    y = mul(add(base_y, mul(rec[VY], dt)), w)
                    x = mul(add(base_x, mul(rec[VX], dt)), w)
                    root[1] = add(root[1], y)
                    root[0] = add(root[0], x)
                    track.time = time
                if flags & YAW:
                    if yaw is None:
                        raise HostFault('YAW track and no yaw output: null pointer write')
                    track.time = from_int(clip.length)
                    slot = animtrack_decode(system, track)
                    q = joint_quat(slot, 0, track.time)
                    heading = quat_yaw(q[0], q[1], q[2], q[3])
                    yaw = (yaw + heading - slot.yaw) & 0xFFFF
                    track.time = time
                    slot.yaw = heading
                if clip.length <= 0:
                    raise HostFault('looping clip of length 0: the wrap loop never ends')
                while True:
                    time = sub(time, length)
                    track.time = time
                    if not le(length, time):
                        break
                life = track.life
            elif flags & REPORT_END:
                track.time = length
                union |= STATUS_ENDED
                if i == state.count - 1:
                    union |= STATUS_TOP_ENDED
            else:
                track.life = ZERO
                track.life_rate = ZERO
                life = ZERO
        rate, life_rate = track.rate, track.life_rate
        if not flags & FIXED_STEP:
            rate = mul(rate, speed)
            life_rate = mul(life_rate, speed)
        track.weight = add(weight, rate)
        track.life = life = add(life, life_rate)
        if le(life, ZERO) and not flags & KEEP:
            _remove_track(state, i)
        elif flags & PURGE_BELOW and le(ONE, fmin(track.weight, life)) and i > 0:
            top = i
            _compact(state, lambda k, t: not (k < top and not t.flags & PERSISTENT))
            break
        i -= 1

    state.flags = union & 0xFFFF
    if union & ROOT:
        left = ONE
        for i in range(state.count - 1, -1, -1):
            track = tracks[i]
            if track.clip is None:
                continue
            raw = fmin(track.weight, track.life)
            w = fmin(raw, left)
            if lt(ONE, w):
                w = ONE
            if lt(w, ZERO):
                w = ZERO
            used = ZERO if lt(raw, ZERO) else raw
            if track.clip.joint_mask == 0:
                left = sub(left, used)
                if lt(left, ZERO):
                    left = ZERO
            if not track.flags & ROOT:
                continue
            if root is None:
                raise HostFault('ROOT track and no root output: null pointer write')
            slot = animtrack_decode(system, track)
            rec = slot.joints[0]
            dt = sub(track.time, from_int(rec[PT]))
            y = add(rec[PY], mul(rec[VY], dt))
            x = add(rec[PX], mul(rec[VX], dt))
            rec[PY] = sub(rec[PY], y)
            rec[PX] = sub(rec[PX], x)
            root[0] = add(root[0], mul(x, w))
            root[1] = add(root[1], mul(y, w))
    if state.flags & YAW:
        i = 0
        while i < state.count:
            track = tracks[i]
            if track.clip is not None and track.flags & YAW:
                if yaw is None:
                    raise HostFault('YAW track and no yaw output: null pointer write')
                slot = animtrack_decode(system, track)
                q = joint_quat(slot, 0, track.time)
                heading = quat_yaw(q[0], q[1], q[2], q[3])
                yaw = (yaw + heading - slot.yaw) & 0xFFFF
                slot.yaw = heading
            i += 1
    return (s8(events), root[0] if root else None, root[1] if root else None,
            s16(yaw) if yaw is not None else None)


def _slow_factor(slow):
    """float(60 - slow) for the slow amount 1..60 at creature+0x2fc, else None."""
    if 1 <= (slow & 0xFF) <= 60:
        return from_int(60 - s8(slow))
    return None


def _to_world(dx, dy, facing):
    """Rotate a model-space delta by facing - 0x4000:  (-dx*c + dy*s, -dx*s - dy*c)."""
    angle = s16(facing) - 0x4000
    c, s = C.cos16(angle), C.sin16(angle)
    nx = neg(dx)
    return add(mul(nx, c), mul(dy, s)), sub(mul(nx, s), mul(dy, c))


def creature_step_anim(system, speed, state, facing, scale, slow=0, sound=True,
                       active=True, delta=(ZERO, ZERO), yaw=0):
    """The animation part of Creature_stepAnim 0x1162b0 -> (events, world dx, world dy,
    yaw delta).

    speed is the argument after the two multipliers the function applies first (the
    player speed scale for creature kind 3, the Drowsy spell fraction).  slow is the byte
    at creature+0x2fc, facing the s16 at +0x38, scale the float at +0xdc.  `active` is
    bit 63 of the flag word at +0xa8: when clear the animation is not stepped and
    `delta` / `yaw` - the values left at +0xbc and +0xc4 by the previous call, i.e. a
    delta that is ALREADY in world space - go through the rest again.

      speed' = (speed * float(60 - slow)) * 1/60      for slow in 1..60, else speed
      events = anim_advance(speed', state, position or 0, +0xbc, +0xc4)
      dx *= scale; dy *= scale; rotate by facing - 0x4000 into world x/y
      for slow in 1..60: f = float(60 - slow) * 1/60; dx *= f; dy *= f;
                         yaw *= int(f)   - the INTEGER part, which is 0: a slowed
                         creature gets no root yaw at all."""
    events = 0
    dx, dy = delta
    factor = _slow_factor(slow)
    if active:
        stepped = speed if factor is None else mul(mul(speed, factor), K60)
        events, dx, dy, yaw = anim_advance(system, stepped, state, sound)
    dx, dy = _to_world(mul(dx, scale), mul(dy, scale), facing)
    if factor is not None:
        f = mul(factor, K60)
        dy = mul(dy, f)
        dx = mul(dx, f)
        yaw = s16(s16(yaw) * to_int(f))
    return events, dx, dy, yaw


def player_anim_step(system, speed, state, facing, slow=0, sound=True):
    """The animation part of Player_animStep 0x1b9520 -> (events, world dx, world dy).
    The speed is slowed as in creature_step_anim; the delta is rotated by
    facing - 0x4000 and neither scaled nor slowed; no yaw output is passed (a player
    state must not hold a YAW track)."""
    factor = _slow_factor(slow)
    stepped = speed if factor is None else mul(mul(speed, factor), K60)
    events, dx, dy, _ = anim_advance(system, stepped, state, sound, want_yaw=False)
    dx, dy = _to_world(dx, dy, facing)
    return events, dx, dy


# =======================================================================================
# 4. The pose
# =======================================================================================

class PoseBuffer:
    """One pose buffer of 0x620 bytes.

      +0x004 tag          VIF unpack code built from the joint count
      +0x008 joint_count  s16
      +0x010 mats         64 joints of three rows (r0, r1, r2, t): s16, rotation * 4096,
                          translation * 64
      +0x610 owner        the state whose pose this is, or None
      +0x614/+0x618       list links (PosePool.order)
      +0x61c stamp        g_drawFrame when the buffer was last drawn"""

    def __init__(self, name):
        self.name = name
        self.tag = 0
        self.joint_count = 0
        self.mats = [[[0, 0, 0, 0] for _ in range(3)] for _ in range(MAX_JOINTS)]
        self.owner = None
        self.stamp = 0


class PosePool:
    """The pose buffers of anim_init: 100 pooled buffers at 0x791ec0 in a list (order[0] =
    g_poseLruHead 0x7b8344, order[-1] = g_poseLruTail 0x7b8340; initially buffer 99 down
    to buffer 0), the static fallback buffer 0x7b89c0 and the default pose 0x7b8380 (64
    identity matrices)."""

    def __init__(self, count=POSE_BUFFERS):
        if count < 2:
            raise ValueError('the list code needs at least two buffers')
        self.buffers = [PoseBuffer(i) for i in range(count)]
        self.order = list(reversed(self.buffers))
        self.fallback = PoseBuffer('fallback')
        self.default = PoseBuffer('default')
        self.default.tag = 0x6DC18000
        self.default.joint_count = 64
        for joint in self.default.mats:
            for r in range(3):
                joint[r][r] = 0x1000

    def to_tail(self, buf):
        order = self.order
        if buf in order and order[-1] is not buf:
            order.remove(buf)
            order.append(buf)


def _ftoi(raw, shift):
    """VU FTOI12 / FTOI4: the value times 2**shift, toward zero, saturating to 32 bits."""
    exponent = (raw >> 23) & 0xFF
    if exponent == 0:
        return 0
    mant = (raw & 0x7FFFFF) | 0x800000
    e2 = exponent - 150 + shift
    if e2 >= 8:
        return -0x80000000 if raw >> 31 else 0x7FFFFFFF
    mag = mant << e2 if e2 >= 0 else mant >> -e2
    return -mag if raw >> 31 else mag


def vu0_reset_stack(system):
    """VU0 entry 2 (0x3e5c50 + 0x50): level 0 of the matrix stack = identity (three rows
    of four; the fourth column is the translation)."""
    mem = system.vu_mem
    mem[0] = [ONE, ZERO, ZERO, ZERO]
    mem[1] = [ZERO, ONE, ZERO, ZERO]
    mem[2] = [ZERO, ZERO, ONE, ZERO]


def vu0_compose_joint(system, quat, pos, bind, depth):
    """VU0 entry 4 (0x3e5c50 + 0xb0) -> three rows of four s16.

    quat (x, y, z, w) and pos are the blended local transform of one joint, bind its
    offset (x, y, z as s16 in 1/64), depth its level.  With R the rotation matrix of the
    quaternion, L = [R | pos], P = stack[depth]:

        W = P * L                          (parent first)   stack[depth + 1] = W
        out.rotation    = trunc(W.rotation * 4096)
        out.translation = trunc((W.rotation * bind + W.translation) * 4 * 16)

    and each result keeps its low 16 bits.  The operation order below is that of the
    microprogram, instruction for instruction.  The vector unit's adder and multiplier
    are taken to behave like the FPU's (ref_core.Fpu); see docs/spec/animation.md."""
    x, y, z, w = quat
    x2, y2, z2 = add(x, x), add(y, y), add(z, z)
    xx, wx = mul(x, x2), mul(w, x2)
    xy, yy, wy = mul(x, y2), mul(y, y2), mul(w, y2)
    xz, yz, zz, wz = mul(x, z2), mul(y, z2), mul(z, z2), mul(w, z2)
    local = (
        (sub(sub(ONE, yy), zz), sub(add(ZERO, xy), wz), add(add(ZERO, xz), wy), pos[0]),
        (add(xy, wz), sub(sub(ONE, xx), zz), sub(add(ZERO, yz), wx), pos[1]),
        (sub(xz, wy), add(yz, wx), sub(sub(ONE, xx), yy), pos[2]),
    )
    base = depth * 3
    if not 0 <= base <= 250:
        raise HostFault('joint depth %d: outside VU0 data memory' % depth)
    mem = system.vu_mem
    world = []
    for r in range(3):
        parent = mem[base + r]
        row = []
        for c in range(4):
            acc = mul(local[0][c], parent[0])
            acc = add(acc, mul(local[1][c], parent[1]))
            acc = add(acc, mul(local[2][c], parent[2]))
            row.append(add(acc, mul(ONE if c == 3 else ZERO, parent[3])))
        world.append(row)
    for r in range(3):
        mem[base + 3 + r] = list(world[r])
    offset = [mul(from_int(s16(bind[k]) * 64), K_QUAT) for k in range(3)]      # ITOF12
    out = []
    for r in range(3):
        row = world[r]
        acc = mul(offset[0], row[0])
        acc = add(acc, mul(offset[1], row[1]))
        acc = add(acc, mul(offset[2], row[2]))
        t = mul(add(acc, mul(ONE, row[3])), FOUR)
        out.append([s16(_ftoi(row[0], 12)), s16(_ftoi(row[1], 12)), s16(_ftoi(row[2], 12)),
                    s16(_ftoi(t, 4))])
    return out


def anim_build_pose(system, state, for_draw=False):
    """anim_buildPose 0x16ed40 (a0 state, a1 for_draw) -> the pose buffer or None.

    Buffer.  Walking from the least recently used end, take the first pooled buffer whose
    stamp is older than g_drawFrame - 3; the buffer at the most recently used end is never
    taken.  If there is none: a draw caller gets no pose (state.pose = None); any other
    caller uses the one static fallback buffer.

    Base track.  From the top track down, the first track with min(weight, life) >= 1 and
    time >= 0 at which the AND of the joint masks seen so far (among such tracks) is 0.
    Without one the state has no pose: state.pose = None (the buffer keeps its previous
    owner and contents).

    Otherwise the buffer's previous owner loses its pose pointer, the buffer becomes this
    state's and moves to the most recently used end.  The base track is decoded; for each
    of ITS joints the local quaternion and position are formed (ROOT: joint 0's x, y = 0;
    YAW: joint 0's heading stripped).  Every track above the base with time >= 0 and blend
    weight w = clamp(min(weight, life), 0, 1) (smoothstepped for EASE) of at least 0.001
    is decoded and blended in, joint by joint except those its joint mask excludes:

        the sign of the incoming quaternion is flipped when that brings it closer;
        q = q*(1-w) + q2*w;   position likewise (a ROOT track pulls joint 0's x, y to 0)

    over the BASE clip's joint count.  Each quaternion is then normalised and composed
    down the hierarchy (vu0_compose_joint).  The skeleton (depth list and bind offsets)
    is taken from the TOP track's clip, whatever its weight.  Joint n (if n < 64) is
    written as zeros."""
    pool = system.poses
    buf = None
    order = pool.order
    tail = order[-1]
    limit = s32(system.draw_frame - 3)
    for candidate in order:
        if candidate is tail:
            break
        if s32(candidate.stamp) < limit:
            buf = candidate
            break
    if buf is None:
        if for_draw:
            state.pose = None
            return None
        buf = pool.fallback
    state.pose = buf

    tracks = state.tracks
    base = state.count - 1
    mask = (1 << 64) - 1
    while base >= 0:
        track = tracks[base]
        if le(ONE, fmin(track.weight, track.life)) and le(ZERO, track.time):
            mask &= track.clip.joint_mask
            if mask == 0:
                break
        base -= 1
    if base < 0:
        state.pose = None
        return None

    if buf.owner is state:
        raise HostFault('the buffer already belongs to this state: null pointer write')
    if buf.owner is not None:
        buf.owner.pose = None
    buf.owner = state
    pool.to_tail(buf)

    track = tracks[base]
    count = track.clip.joint_count
    slot = animtrack_decode(system, track)
    time = track.time
    quats, poses = [], []
    for j in range(count):
        q = joint_quat(slot, j, time)
        if j == 0 and track.flags & YAW:
            q, _ = quat_strip_yaw(q)
        p = joint_pos(slot, j, time)
        if j == 0 and track.flags & ROOT:
            p[0] = p[1] = ZERO
        quats.append(q)
        poses.append(p)
    if system.trace is not None:
        system.trace.append(('base', [quats[j] + poses[j] for j in range(count)]))

    for i in range(base + 1, state.count):
        track = tracks[i]
        time = track.time
        if lt(time, ZERO):
            continue
        w = fmin(fmax(fmin(track.weight, track.life), ZERO), ONE)
        if track.flags & EASE:
            w = C.hermite(w, ZERO, ONE, ZERO, ZERO)
        if lt(w, K_BLEND_MIN):
            continue
        slot = animtrack_decode(system, track)
        rest = sub(ONE, w)
        for j in range(count):
            if (track.clip.joint_mask >> j) & 1:
                continue
            q2 = joint_quat(slot, j, time)
            if j == 0 and track.flags & YAW:
                q2, _ = quat_strip_yaw(q2)
            q1 = quats[j]
            total = dist = None
            for k in (3, 0, 1, 2):
                plus, minus = add(q1[k], q2[k]), sub(q1[k], q2[k])
                total = mul(plus, plus) if total is None else add(total, mul(plus, plus))
                dist = mul(minus, minus) if dist is None else add(dist, mul(minus, minus))
            if lt(total, dist):
                q2 = [neg(c) for c in q2]
            # the w component is also "unwrapped" like an angle; inert for real quaternions
            w2 = q2[3]
            guard = 0
            if lt(K_PI, sub(w2, q1[3])):
                while True:
                    w2 = sub(w2, K_TWO_PI)
                    guard += 1
                    if not lt(K_PI, sub(w2, q1[3])):
                        break
                    if guard > 100000:
                        raise HostFault('quaternion unwrap loop does not end')
            if lt(sub(q1[3], w2), K_MINUS_PI):
                while True:
                    w2 = add(w2, K_TWO_PI)
                    guard += 1
                    if not lt(sub(q1[3], w2), K_MINUS_PI):
                        break
                    if guard > 100000:
                        raise HostFault('quaternion unwrap loop does not end')
            q2[3] = w2
            quats[j] = [add(mul(q1[k], rest), mul(q2[k], w)) for k in range(4)]
            p1 = poses[j]
            if j == 0 and track.flags & ROOT:
                p1[0] = mul(p1[0], rest)
                p1[1] = mul(p1[1], rest)
                p2z = joint_pos(slot, j, time)[2]
            else:
                p2 = joint_pos(slot, j, time)
                p1[0] = add(mul(p1[0], rest), mul(p2[0], w))
                p1[1] = add(mul(p1[1], rest), mul(p2[1], w))
                p2z = p2[2]
            p1[2] = add(mul(p1[2], rest), mul(p2z, w))

    if system.trace is not None:
        system.trace.append(('blended', [quats[j] + poses[j] for j in range(count)]))
    buf.joint_count = s16(count)
    buf.tag = (((count * 3 + 1) << 16) | 0x6D008000) & M32
    skeleton = tracks[state.count - 1].clip
    vu0_reset_stack(system)
    for j in range(count):
        if j >= skeleton.joint_count:
            raise HostFault('joint %d: the top clip has no skeleton entry for it' % j)
        q = C.quat_normalize(quats[j])
        buf.mats[j] = vu0_compose_joint(system, q, poses[j], skeleton.bind[j],
                                        skeleton.depth[j])
    if count < MAX_JOINTS:
        buf.mats[count] = [[0, 0, 0, 0] for _ in range(3)]
    return buf


def anim_emit_pose(system, state):
    """The cache side of anim_emitPose 0x16f880 (the draw path) -> the buffer drawn.

    A state whose pose sits in the fallback buffer loses it first (that buffer is never
    drawn).  A state without a pose gets one built with for_draw = 1.  If it then has a
    pose, the buffer is stamped with g_drawFrame and moved to the most recently used end;
    otherwise the default pose (identity) is drawn."""
    pool = system.poses
    if state.pose is pool.fallback:
        state.pose = None
        pool.fallback.owner = None
    if state.pose is None:
        anim_build_pose(system, state, True)
    buf = state.pose
    if buf is None:
        return pool.default
    buf.stamp = system.draw_frame & M32
    pool.to_tail(buf)
    return buf


def anim_get_joint_matrix(system, state, joint):
    """anim_getJointMatrix 0x16f720 (a0 state, a1 joint, a2 out) -> mat34 (12 patterns).

    The pose is built ONLY when the state has none (anim_build_pose with for_draw = 0);
    otherwise whatever pose is attached is used, however old.  A state that still has no
    pose reads the default pose.  The joint index is clamped to 0..joint_count-1.  The
    result is in ref_core's row-vector layout (a point is transformed as v * M + t):

        M[r][k] = float(mats[joint][k][r]) * 1/4096     t[k] = float(mats[joint][k][3]) * 1/64"""
    if state.pose is None:
        anim_build_pose(system, state, False)
    buf = state.pose if state.pose is not None else system.poses.default
    j = max(joint, 0)
    last = buf.joint_count - 1
    if last < j:
        j = last
    if j < 0:
        raise HostFault('pose with no joints: the read falls before the matrices')
    rows = buf.mats[j]
    out = [mul(from_int(rows[k][r]), K_QUAT) for r in range(3) for k in range(3)]
    return out + [mul(from_int(rows[k][3]), K_POS) for k in range(3)]


def model_get_attach_point(system, scale, pos, facing, state, joint, origin=None,
                           direction=None):
    """model_getAttachPoint 0x1754a0 (f12 scale, a0 model, a1 pos, a2 facing, a3 state or
    0, t0 index, t1 position out or 0, t2 direction out or 0) -> (position, direction).

    joint, origin and direction are the fields +0x00, +0x28 and +0x10 of the model's
    attach record (docs/formats/model-texture.md); pass None for an output the caller
    does not ask for.  With M the joint matrix (identity without a state):

        p = origin * M + t;  d = direction * M
        a = facing - 0x4000, c = cos16(a), s = sin16(a)
        position  = ((-(p.x*scale))*c + (p.y*scale)*s + pos.x,
                     (-(p.x*scale))*s - (p.y*scale)*c + pos.y,   p.z*scale + pos.z)
        direction = (-d.x*c + d.y*s, -d.x*s - d.y*c, d.z)        (not scaled)"""
    if state is not None:
        m = anim_get_joint_matrix(system, state, joint)
    else:
        m = C.mat34_set_identity()
    p = C.mat34_transform_point(m, origin) if origin is not None else None
    d = C.mat34_rotate_vec(m, direction) if direction is not None else None
    angle = s16(facing) - 0x4000
    c, s = C.cos16(angle), C.sin16(angle)
    if p is not None:
        x, y, z = mul(p[0], scale), mul(p[1], scale), mul(p[2], scale)
        nx = neg(x)
        p = [add(add(mul(nx, c), mul(y, s)), pos[0]),
             add(sub(mul(nx, s), mul(y, c)), pos[1]),
             add(z, pos[2])]
    if d is not None:
        nx, y = neg(d[0]), d[1]
        d = [add(mul(nx, c), mul(y, s)), sub(mul(nx, s), mul(y, c)), d[2]]
    return p, d


def model_get_sample_point(system, scale, pos, facing, state, point, want_matrix=False):
    """model_getSamplePoint 0x178e18 (f12 scale, a0 model, a1 state or 0, a2 pos, a3
    facing, t0 index, t1 position out, t2 radius out or 0, t3 mat3 out or 0)
    -> (position, radius, matrix or None).

    point is the model's sample record (x, y, z, word), four s16, or None for an index at
    or past the model's point count (the result is then pos itself, radius 0, identity).
    The joint is the low byte of `word` shifted right by two; the radius returned is the
    WHOLE word as a signed number times the scale.

        p = (x, y, z) * 1/16 * M + t
        position = ((-p.x*c + p.y*s) * scale + pos.x, (-p.x*s - p.y*c) * scale + pos.y,
                    p.z * scale + pos.z)                    with a = facing - 0x4000
        matrix   = M's rotation with its first two columns turned by a (0x162df0)"""
    angle = s16(facing) - 0x4000
    if point is None:
        p = [ZERO, ZERO, ZERO]
        radius = ZERO
        matrix = C.mat3_set_identity() if want_matrix else None
    else:
        x, y, z, word = point
        if state is not None:
            m = anim_get_joint_matrix(system, state, (word & 0xFF) >> 2)
        else:
            m = C.mat34_set_identity()
        local = [mul(from_int(s16(v)), K_SAMPLE) for v in (x, y, z)]
        p = C.mat34_transform_point(m, local)
        radius = mul(from_int(s16(word)), scale)
        matrix = C.mat3_rotate_axis_post(m[:9], 2, s16(angle))[:9] if want_matrix else None
    c, s = C.cos16(angle), C.sin16(angle)
    nx, y = neg(p[0]), p[1]
    out_y = sub(mul(nx, s), mul(y, c))
    out_x = add(mul(nx, c), mul(y, s))
    position = [add(mul(out_x, scale), pos[0]), add(mul(out_y, scale), pos[1]),
                add(mul(p[2], scale), pos[2])]
    return position, radius, matrix


# =======================================================================================
# Command line: a small viewer for one clip
# =======================================================================================

def main(argv):
    if len(argv) < 2:
        print('usage: ref_anim.py <clip.anm> [tick ...]   joint values and model-space '
              'joint matrices at the given ticks (default 0)')
        return 2
    clip = Clip(open(argv[1], 'rb').read(), os.path.basename(argv[1]))
    print('%r  mask %#x  sound events %s' % (clip, clip.joint_mask,
          'none' if clip.sound_times is None else len(clip.sound_times) - 1))
    system = AnimSystem()
    for text in argv[2:] or ['0']:
        state = AnimState(1)
        anim_push(state, clip, 0)
        state.tracks[0].time = C.f32(float(text))
        print('tick %s' % text)
        for j in range(clip.joint_count):
            m = anim_get_joint_matrix(system, state, j)
            print('  joint %2d depth %2d  t = (%9.3f %9.3f %9.3f)' % (
                j, clip.depth[j], C.to_float(m[9]), C.to_float(m[10]), C.to_float(m[11])))
        anim_release_caches(state)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
