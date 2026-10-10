#!/usr/bin/env python3
"""ref_netwire.py - reference model of the peer-to-peer wire format of Champions: Return to
Arms (SLUS_209.73): the input codec, every datagram type of the lockstep socket, the
receiver, the sender, the per-frame sync hash, pad_apply and the launch packets.

A research tool, not game code.  Every part was written from the instruction sequence at the
address given in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_netwire.py.  docs/spec/net-wire.md is the prose version.
Standard library only; no game data is embedded (the two nine-entry step tables and the
handful of constants below are the only numbers taken from the executable).

Layers, bottom up
  1  Fpu            R5900 single precision on raw 32-bit patterns (only what the decoder and
                    pad_apply need)
  2  BitWriter / BitReader   the 16-bit-word, most-significant-bit-first bit stream
  3  encode_axis / decode_axis      one stick channel             0x13c450 / 0x13c970
  4  CodecState, encode_frames, read_frames, apply_frames   a run of frames: buttons, four
                    sticks, yaw, yaw flag                          inlined in 0x137d60, 0x132e90,
                                                                  0x139e88 and 0x13b5d0
  5  build_packet / parse_packet and the small packet types       0x137d60, 0x13c078, 0x131b00
  6  Peer, Machine  the state one console keeps and what net_main, the receiver and the
                    tick do with it                                0x132e90, 0x13b5d0, 0x139e88
  7  pad_apply, sync_hash, launch packets                         0x174410, 0x13af44, 0x1354f8

Conventions
  * Frames travel as 12-byte "wire records": bytes +4..+0xf of the 24-byte input record
    (u16 buttons, four stick bytes, two pressure bytes, u32 yaw-and-flag).  rec12() builds
    one, rec12_fields() takes one apart.
  * Floats are ints holding the 32-bit pattern.  Arithmetic goes through an Fpu object.
  * Everything multi-byte is little endian.
  * Where the original leaves a byte unwritten (it then holds whatever was on its stack)
    the model writes 0 and says so: build_packet returns the offsets of such bytes, and
    apply_frames returns records whose two pressure bytes are 0.

Floating point (the only approximation)
  The stick decoder runs ten steps of a spring in single precision and truncates.  The
  console FPU is not IEEE 754: no NaN, infinity or denormal, results chopped toward zero.
  Those rules are implemented exactly.  The one thing not established from hardware is how
  many bits of the smaller operand an addition keeps.  Fpu offers the same four choices as
  tools/ee_emu.py; 'ps2' (six extra bits, the rest floored, operands 25 or more binades
  apart ignored) is the default.  Under each choice the model equals the original executed
  under that choice bit for bit, value and velocity included.  The choices themselves
  disagree: over 20,000 frames of mixed input 'ps2', 'ps2g1' and 'nearest' gave the same
  stick bytes on all but one frame, while 'chop' (the exact sum truncated) differed from
  them on 11 % of frames, always by one count (see fpu_sensitivity()).  Which of them a
  real console matches is not settled by anything in this repository.
"""
import struct

M32 = 0xFFFFFFFF
SIGN = 0x80000000
FMAX = 0x7FFFFFFF


class MalformedPacket(Exception):
    """The packet is one the original does not reject but cannot process sanely: it would
    read or write outside its buffers, or loop.  The model refuses instead of imitating."""


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & SIGN else x


def f32(value):
    """Pattern of the IEEE single nearest to a Python float (for test input)."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def to_float(raw):
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


# =======================================================================================
# 1. R5900 single precision
# =======================================================================================

class Fpu:
    """add, sub, mul, div, sqrt, int conversion and compare on raw patterns.

    Exponent field 0 is zero, 255 is an ordinary large number, overflow gives
    +/-0x7fffffff, underflow a signed zero; products, quotients and roots are the exact
    result truncated.  model selects the adder: 'ps2', 'ps2g1', 'chop', 'nearest' (see the
    module docstring and tools/ee_emu.py).  mul_bias and div_nearest exist to measure
    sensitivity, as there."""
    MODELS = ('ps2', 'ps2g1', 'chop', 'nearest')

    def __init__(self, model='ps2', mul_bias=False, div_nearest=False):
        if model not in self.MODELS:
            raise ValueError('model must be one of %s' % (self.MODELS,))
        self.model, self.mul_bias, self.div_nearest = model, mul_bias, div_nearest

    @staticmethod
    def _split(raw):
        exp = (raw >> 23) & 0xFF
        if exp == 0:
            return raw >> 31, 0, 0
        return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp

    @staticmethod
    def _round(sign, mag, e2, nearest):
        """Pattern of (-1)**sign * mag * 2**e2 for a positive integer mag."""
        drop = mag.bit_length() - 24
        if drop > 0:
            kept = mag >> drop
            if nearest:
                rest, half = mag - (kept << drop), 1 << (drop - 1)
                if rest > half or (rest == half and kept & 1):
                    kept += 1
                    if kept == 1 << 24:
                        kept, drop = kept >> 1, drop + 1
        else:
            kept = mag << -drop
        exp = e2 + drop + 150
        if exp > 255:
            return (sign << 31) | FMAX
        if exp < 1:
            return sign << 31
        return (sign << 31) | (exp << 23) | (kept & 0x7FFFFF)

    def add(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        if ma == 0 and mb == 0:
            return (sa & sb) << 31
        if ma == 0:
            return b & M32
        if mb == 0:
            return a & M32
        if self.model == 'ps2':
            if ea < eb:
                a, sa, ma, ea, sb, mb, eb = b, sb, mb, eb, sa, ma, ea
            gap = ea - eb
            if gap >= 25:
                return a & M32
            total = ((-ma if sa else ma) << 6) + (((-mb if sb else mb) << 6) >> gap)
            if total == 0:
                return 0
            return self._round(1 if total < 0 else 0, abs(total), ea - 156, False)
        if self.model == 'ps2g1':
            gap = ea - eb
            if gap >= 25:
                return a & M32
            if gap <= -25:
                return b & M32
            if gap > 1:
                mb &= -1 << (gap - 1)
            elif gap < -1:
                ma &= -1 << (-gap - 1)
        low = min(ea, eb)
        total = ((-ma if sa else ma) << (ea - low)) + ((-mb if sb else mb) << (eb - low))
        if total == 0:
            return 0
        return self._round(1 if total < 0 else 0, abs(total), low - 150, self.model == 'nearest')

    def sub(self, a, b):
        return self.add(a, (b ^ SIGN) & M32)

    def mul(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        sign = sa ^ sb
        if ma == 0 or mb == 0:
            return sign << 31
        product = ma * mb
        raw = self._round(sign, product, ea + eb - 300, self.model == 'nearest')
        if self.mul_bias:
            drop = product.bit_length() - 24
            exp = ea + eb - 150 + drop
            if drop > 0 and product & ((1 << drop) - 1) and 1 <= exp <= 255 and (raw & FMAX) > 0x00800000:
                raw -= 1
        return raw

    def div(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        sign = sa ^ sb
        if mb == 0:
            return (sign << 31) | FMAX
        if ma == 0:
            return sign << 31
        quotient, rest = divmod(ma << 40, mb)
        return self._round(sign, (quotient << 1) | (1 if rest else 0), ea - eb - 41,
                           self.div_nearest or self.model == 'nearest')

    def sqrt(self, a):
        sa, ma, ea = self._split(a)
        if ma == 0:
            return sa << 31
        e2 = ea - 150
        if e2 & 1:
            ma, e2 = ma << 1, e2 - 1
        wide = ma << 48
        root = _isqrt(wide)
        return self._round(0, (root << 1) | (1 if root * root != wide else 0), e2 // 2 - 25,
                           self.div_nearest or self.model == 'nearest')

    def from_int(self, value):
        """cvt.s.w"""
        value = s32(value)
        if value == 0:
            return 0
        return self._round(1 if value < 0 else 0, abs(value), 0, self.model == 'nearest')

    @staticmethod
    def to_int(a):
        """cvt.w.s: toward zero, saturating.  Returns a signed int."""
        sign, mant, exp = Fpu._split(a)
        if mant == 0:
            return 0
        if exp >= 158:
            return -0x80000000 if sign else 0x7FFFFFFF
        mag = mant << (exp - 150) if exp >= 150 else mant >> (150 - exp)
        return -mag if sign else mag

    @staticmethod
    def lt(a, b):
        """c.olt.s: sign and magnitude of the raw patterns, +0 equals -0."""
        x = -(a & FMAX) if a & SIGN else a & FMAX
        y = -(b & FMAX) if b & SIGN else b & FMAX
        return x < y


def _isqrt(n):
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + 1) // 2)
    while True:
        y = (x + n // x) // 2
        if y >= x:
            return x
        x = y


DEFAULT_FPU = Fpu()

F_ONE = 0x3F800000
F_128 = 0x43000000          # reset value of a channel's smoothed value


# =======================================================================================
# 2. The bit stream
# =======================================================================================

class BitWriter:
    """Bits are written most significant first into 16-bit words; bit position p lives in
    word p >> 4.  Each write ORs into the current word and ASSIGNS the next word (the spill,
    or 0) - exactly what the original's two stores do - so a word is never left holding old
    memory once the stream has reached it, and the word after the last one written is
    always defined.  written is the number of words the stream has stored."""

    def __init__(self):
        self.words = []
        self.pos = 0

    def start(self, first_word):
        """The encoder's preamble: word 0 = the first frame's buttons, word 1 = 0, position
        16 (0x138998-0x1389d0)."""
        self.words = [first_word & 0xFFFF, 0]
        self.pos = 16

    def put(self, value, bits):
        v16 = (value << (16 - bits)) & 0xFFFF
        index, shift = self.pos >> 4, self.pos & 15
        while len(self.words) < index + 2:
            self.words.append(0)
        self.words[index] |= v16 >> shift
        self.words[index + 1] = (v16 << (16 - shift)) & 0xFFFF
        self.pos += bits

    @property
    def written(self):
        return len(self.words)

    def tobytes(self):
        return struct.pack('<%dH' % len(self.words), *self.words)


class BitReader:
    """Reads the same stream.  Every read in the original loads two consecutive words, so
    it may touch one word past the bits it needs; words beyond the data read as 0 here."""

    def __init__(self, data, pos=0):
        if len(data) & 1:
            data = bytes(data) + b'\0'
        self.words = struct.unpack('<%dH' % (len(data) // 2), bytes(data))
        self.pos = pos

    def get(self, bits):
        index, shift = self.pos >> 4, self.pos & 15
        words = self.words
        hi = words[index] if index < len(words) else 0
        lo = words[index + 1] if index + 1 < len(words) else 0
        self.pos += bits
        return ((((hi << 16) | lo) << shift) & M32) >> (32 - bits)


# =======================================================================================
# 3. One stick channel
# =======================================================================================

STEPS = (4, 6, 8, 12, 16, 24, 32, 48, 64)       # data 0x402860 (encoder) and 0x402880 (decoder)
INDEX_ADJ = (-1, 2)                             # data 0x402878 and 0x402898: no move, move
SPRING_GAIN = 0x3D4CCCCC                        # just under 0.05, immediate at 0x13cd78
SPRING_SQUARE = 0x3E4CCCCC                      # just under 0.2, immediate at 0x13cc6c
SPRING_STEPS = 10                               # loop counter 9 down to -1, 0x13cd34


class Channel:
    """{s32 step index 0..8, s32 predictor 0..255, float value, float velocity}, 16 bytes.
    The encoder uses the first two fields only."""
    __slots__ = ('index', 'pred', 'value', 'velocity')

    def __init__(self, index=0, pred=0, value=F_128, velocity=0):
        self.index, self.pred, self.value, self.velocity = index, pred, value, velocity

    def copy(self):
        return Channel(self.index, self.pred, self.value, self.velocity)

    def pack(self):
        return struct.pack('<iiII', self.index, self.pred, self.value, self.velocity)

    @classmethod
    def unpack(cls, data):
        return cls(*struct.unpack('<iiII', bytes(data[:16])))

    def __eq__(self, other):
        return self.pack() == other.pack()

    def __repr__(self):
        return 'Channel(index=%d, pred=%d, value=0x%08x, velocity=0x%08x)' % (
            self.index, self.pred, self.value, self.velocity)


def axis_symbols(chan, samples):
    """First loop of netcodec_encodeAxis 0x13c450: reduce each sample to (move,
    direction) and advance the channel's step index and predictor.

    quotient = (sample - predictor) / step, truncated toward zero; move = min(|quotient|, 1);
    direction = 1 when the quotient is negative.  The predictor moves by move * step and is
    clamped at the end it moved toward only (0 after a downward move, 255 after an upward
    one); the index gains 2 after a move and loses 1 otherwise, clamped to 0..8."""
    out = []
    for sample in samples:
        step = STEPS[chan.index]
        diff = (sample & 0xFF) - chan.pred
        quotient = abs(diff) // step
        negative = diff < 0 and quotient != 0
        move = 1 if quotient >= 1 else 0
        if negative:
            chan.pred = max(chan.pred - move * step, 0)
        else:
            chan.pred = min(chan.pred + move * step, 255)
        chan.index = min(max(chan.index + INDEX_ADJ[move], 0), 8)
        out.append((move, 1 if negative else 0))
    return out


def write_axis_symbols(writer, symbols):
    """Second and third loops of 0x13c450: pack the (move, direction) pairs.

    Move bits: alternately a 5-bit count of zeros (31 = "31 zeros and another count
    follows"; less than 31 implies a following 1, unless the samples are exhausted) and
    groups of five literal bits, a further group following while the last one held a 1.
    Directions (only if any sample moved): one bit for the first move's direction, then
    3-bit run lengths of moves in the same direction; 7 means "seven, and the direction
    does not change"."""
    literal, seen_one, zeros = 0, False, 0
    for move, _direction in symbols:
        if literal == 0:
            if not move:
                zeros += 1
                if zeros == 31:
                    writer.put(31, 5)
                    zeros = 0
            else:
                writer.put(zeros, 5)
                zeros = 0
                literal, seen_one = 1, False
        else:
            writer.put(move, 1)
            literal += 1
            seen_one = seen_one or bool(move)
            if literal == 6:
                literal, seen_one = (1, False) if seen_one else (0, False)
    if zeros:
        writer.put(zeros, 5)
    moves = [direction for move, direction in symbols if move]
    if not moves:
        return
    current, run = moves[0], 0
    writer.put(current, 1)
    for direction in moves:
        if direction != current:
            writer.put(run, 3)
            run, current = 0, direction
        run += 1
        if run == 7:
            writer.put(7, 3)
            run = 0
    if run:
        writer.put(run, 3)


def encode_axis(writer, chan, samples):
    """netcodec_encodeAxis 0x13c450 (state, writer, channel, bytes, n)."""
    write_axis_symbols(writer, axis_symbols(chan, samples))


def read_axis_symbols(reader, total):
    """First half of netcodec_decodeAxis 0x13c970 (up to 0x13cc50): the (move,
    direction) pairs of `total` samples.  Raises MalformedPacket where a run overshoots
    the sample count (the original then writes past its scratch array)."""
    moves = []
    literal, seen_one = 0, False
    while len(moves) < total:
        if literal == 0:
            zeros = reader.get(5)
            if len(moves) + zeros > total:
                raise MalformedPacket('stick zero-run overshoots the frame count')
            moves += [0] * zeros
            if len(moves) == total:
                break
            if zeros != 31:
                moves.append(1)
                literal, seen_one = 1, False
        else:
            bit = reader.get(1)
            moves.append(bit)
            literal += 1
            seen_one = seen_one or bool(bit)
            if literal == 6:
                literal, seen_one = (1, False) if seen_one else (0, False)
    directions = [0] * total
    where = [i for i, move in enumerate(moves) if move]
    if where:
        current, done = reader.get(1), 0
        while done < len(where):
            run = reader.get(3)
            if done + run > len(where):
                raise MalformedPacket('stick direction run overshoots the moves')
            for index in where[done:done + run]:
                directions[index] = current
            done += run
            if run != 7:
                current ^= 1
    return list(zip(moves, directions))


def apply_axis_symbols(chan, symbols, fpu=DEFAULT_FPU):
    """Second half of 0x13c970 (0x13ccb8-0x13ce30): for each (move, direction) rebuild the
    predictor and run the spring; returns the stick bytes.

    predictor += or -= move * step, then clamped to 0..255 (both ends, unlike the encoder -
    the results agree because the encoder's unclamped end cannot be crossed); index as in
    the encoder.  Then ten times, in this order (0x13cdb0-0x13cdd8):
        value    = value + velocity
        velocity = (velocity + (predictor - value) * GAIN) * (1 - sqrt(SQUARE))
    and the byte is the last value converted to an integer toward zero, clamped 0..255."""
    damping = fpu.sub(F_ONE, fpu.sqrt(SPRING_SQUARE))
    out = bytearray()
    for move, direction in symbols:
        step = STEPS[chan.index] * move
        pred = chan.pred - step if direction else chan.pred + step
        chan.index = min(max(chan.index + INDEX_ADJ[move], 0), 8)
        chan.pred = pred = max(min(pred, 255), 0)
        target = fpu.from_int(pred)
        value, velocity = chan.value, chan.velocity
        for _ in range(SPRING_STEPS):
            value = fpu.add(value, velocity)
            velocity = fpu.mul(fpu.add(velocity, fpu.mul(fpu.sub(target, value), SPRING_GAIN)), damping)
        chan.value, chan.velocity = value, velocity
        out.append(max(min(fpu.to_int(value), 255), 0))
    return bytes(out)


def decode_axis(reader, chan, count, skip=0, fpu=DEFAULT_FPU):
    """netcodec_decodeAxis 0x13c970 (state, reader, channel, out, count, skip): reads
    skip + count samples from the stream and applies the last `count` of them."""
    return apply_axis_symbols(chan, read_axis_symbols(reader, count + skip)[skip:], fpu)


# =======================================================================================
# 4. A run of frames
# =======================================================================================

def rec12(buttons=0, sticks=(128, 128, 128, 128), pressure=(0, 0), yaw=0, flag=0):
    """Wire record = input record +4..+0xf: u16 buttons, stick bytes of record +6, +7, +8,
    +9, pressure bytes +0xa, +0xb, u32 = sign-extended 16-bit yaw with bit 0 replaced by
    the camera flag (0x133464-0x1334a8)."""
    word = (s16(yaw & 0xFFFE) & M32) | (flag & 1)
    return struct.pack('<H6BI', buttons & 0xFFFF, *(tuple(sticks) + tuple(pressure)), word)


def rec12_fields(record):
    """(buttons, (s6, s7, s8, s9), (p10, p11), yaw word)"""
    v = struct.unpack('<H6BI', bytes(record[:12]))
    return v[0], v[1:5], v[5:7], v[7]


WIRE_ORDER = (2, 3, 0, 1)   # stream order is record bytes +6, +7, +8, +9; they use state
                            # channels +0x20, +0x30, +0x00, +0x10 (the four calls at
                            # 0x138bc8, 0x138c20, 0x138c78, 0x138cd0)
CHANNEL_OF_BYTE = {6: 2, 7: 3, 8: 0, 9: 1}


class CodecState:
    """The 0x4c-byte codec state.
       +0x00 +0x10 +0x20 +0x30  four channels (record bytes +8, +9, +6, +7)
       +0x40 s16  previous raw yaw (encoder only)
       +0x42 s16  predicted yaw
       +0x44 s16  yaw delta per frame
       +0x46 2 bytes never referenced
       +0x48 s32  frames coded (only ever incremented; nothing reads it)"""

    def __init__(self):
        self.ch = [Channel() for _ in range(4)]
        self.yaw_prev = self.yaw_pred = self.yaw_delta = 0
        self.pad46 = 0
        self.count = 0

    def copy(self):
        other = CodecState()
        other.ch = [c.copy() for c in self.ch]
        other.yaw_prev, other.yaw_pred, other.yaw_delta = self.yaw_prev, self.yaw_pred, self.yaw_delta
        other.pad46, other.count = self.pad46, self.count
        return other

    def pack(self):
        return b''.join(c.pack() for c in self.ch) + struct.pack(
            '<hhhHi', self.yaw_prev, self.yaw_pred, self.yaw_delta, self.pad46, s32(self.count))

    @classmethod
    def unpack(cls, data):
        state = cls()
        state.ch = [Channel.unpack(data[i * 16:i * 16 + 16]) for i in range(4)]
        (state.yaw_prev, state.yaw_pred, state.yaw_delta, state.pad46,
         state.count) = struct.unpack('<hhhHi', bytes(data[0x40:0x4C]))
        return state

    def __eq__(self, other):
        return self.pack() == other.pack()

    def __repr__(self):
        return 'CodecState(%r, yaw prev %d pred %d delta %d, count %d)' % (
            self.ch, self.yaw_prev, self.yaw_pred, self.yaw_delta, self.count)


YAW_JUMP = 1000        # 0x3e9 compare: a raw change above this is sent absolute
YAW_FAR = 3000         # prediction error above this is sent absolute
YAW_NUDGE = 200        # prediction error above this adds error / 15 to the delta
YAW_KEEP = 31          # the current delta is kept while the wanted one is closer than this
STREAM_TRAILER = 0xA5A5


def _trunc_div(a, b):
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _abs32(x):
    """|x| as the code computes it: a 32-bit negate, so the most negative value stays."""
    return s32(-x) if x < 0 else x


def encode_frames(state, records):
    """The frame encoder.  It exists five times, inlined: in net_sendInputPacket (catch-up
    pass 0x137fd0-0x1388cc and main pass 0x138998-0x1391b0), in net_main (0x13385c-0x134160),
    in the tick (before 0x13a764) and in prediction (before 0x132614).  Advances `state`
    over the records and returns the BitWriter.

    Stream: 16 bits first frame's buttons; button runs; four stick channels; yaw; yaw
    flag; 16 bits 0xa5a5."""
    count = len(records)
    if count < 1:
        raise ValueError('the encoder needs at least one frame (the original reads its '
                         'stack for the first button word otherwise)')
    fields = [rec12_fields(r) for r in records]
    writer = BitWriter()
    writer.start(fields[0][0])
    state.count = s32(state.count + count)

    # buttons (from 0x1389d4): 5-bit runs; after a run under 31 a 4-bit number names
    # the lowest bit that differs and that bit is toggled; several changed bits cost a
    # zero-length run each
    current, run = fields[0][0], 0
    for buttons, _sticks, _pressure, _yaw in fields:
        if buttons == current:
            run += 1
        else:
            while buttons != current:
                writer.put(run, 5)
                run = 0
                diff = buttons ^ current
                bit = (diff & -diff).bit_length() - 1
                writer.put(bit, 4)
                current ^= 1 << bit
            run = 1
        if run == 31:
            writer.put(31, 5)
            run = 0
    if run:
        writer.put(run, 5)

    # sticks
    for position, channel in enumerate(WIRE_ORDER):
        encode_axis(writer, state.ch[channel], [f[1][position] for f in fields])

    # yaw (after the fourth stick call, 0x138cd0)
    run = 0
    for _buttons, _sticks, _pressure, word in fields:
        raw = s32(word & 0xFFFFFFFE)
        change = s32(raw - state.yaw_prev)
        state.yaw_prev = s16(raw)
        error = s32(raw - state.yaw_pred)
        absolute = not _abs32(change) < YAW_JUMP + 1 or _abs32(error) > YAW_FAR
        if not absolute:
            delta = change
            if _abs32(error) > YAW_NUDGE:
                delta = s32(change + _trunc_div(error, 15))
            if _abs32(s32(delta - state.yaw_delta)) < YAW_KEEP and s32(state.yaw_delta * change) >= 0:
                run += 1
                state.yaw_pred = s16(state.yaw_pred + state.yaw_delta)
                if run == 31:
                    writer.put(31, 5)
                    run = 0
            else:
                delta = max(min(delta, 255), -255)
                writer.put(run, 5)
                writer.put(1, 1)
                writer.put(delta & 0x1FF, 9)
                run = 0
                state.yaw_delta = s16(delta)
                state.yaw_pred = s16(state.yaw_pred + delta)
        else:
            writer.put(run, 5)
            writer.put(0, 1)
            writer.put(word & 0xFFFE, 16)
            run = 0
            state.yaw_pred = state.yaw_prev
    if run:
        writer.put(run, 5)

    # yaw flag, then the trailer (0x139170)
    current, run = fields[0][3] & 1, 0
    writer.put(current, 1)
    for _buttons, _sticks, _pressure, word in fields:
        if word & 1 != current:
            writer.put(run, 5)
            run, current = 0, word & 1
        run += 1
        if run == 31:
            writer.put(31, 5)
            run = 0
    if run:
        writer.put(run, 5)
    writer.put(STREAM_TRAILER, 16)
    return writer


class FrameSymbols:
    """What a stream says about `count` frames before any state is applied."""
    __slots__ = ('count', 'buttons', 'sticks', 'yaw', 'flags', 'bits')

    def __init__(self):
        self.count = 0
        self.buttons = []       # one 16-bit word per frame (absolute)
        self.sticks = []        # four lists (stream order) of (move, direction)
        self.yaw = []           # ('keep',) | ('delta', signed 9 bits) | ('abs', 16 bits)
        self.flags = []
        self.bits = 0           # length of the stream including the 0xa5a5


def read_frames(data, count):
    """The parsing half of the receiver's inlined decoder (0x13b868-0x13bddc), for a stream
    that starts at data[0].  Stateless: the stream is self-delimiting given the frame
    count.  The 0xa5a5 trailer is skipped, not checked (nothing checks it)."""
    if count < 1:
        raise MalformedPacket('no frames')
    reader = BitReader(data)
    out = FrameSymbols()
    out.count = count
    current = reader.get(16)
    run = reader.get(5)
    while True:
        if len(out.buttons) + run > count:
            raise MalformedPacket('button run overshoots the frame count')
        out.buttons += [current] * run
        if len(out.buttons) == count:
            break
        if run != 31:
            current ^= 1 << reader.get(4)
        run = reader.get(5)
    for _channel in WIRE_ORDER:
        out.sticks.append(read_axis_symbols(reader, count))
    while len(out.yaw) < count:
        run = reader.get(5)
        if len(out.yaw) + run > count:
            raise MalformedPacket('yaw run overshoots the frame count')
        out.yaw += [('keep',)] * run
        if len(out.yaw) == count:
            break
        if run != 31:
            if reader.get(1):
                value = reader.get(9)
                out.yaw.append(('delta', value - 0x200 if value & 0x100 else value))
            else:
                out.yaw.append(('abs', reader.get(16)))
    current = reader.get(1)
    while True:
        run = reader.get(5)
        if len(out.flags) + run > count:
            raise MalformedPacket('flag run overshoots the frame count')
        out.flags += [current] * run
        if len(out.flags) == count:
            break
        if run != 31:
            current ^= 1
    reader.get(16)
    out.bits = reader.pos
    return out


def apply_frames(state, symbols, skip=0, fpu=DEFAULT_FPU):
    """The state half of the receiver's decoder: apply frames skip.. of `symbols` to
    `state` and return their wire records.  The two pressure bytes are 0 here; the
    original never writes them (0x13be2c copies its scratch record whole, so they are
    whatever was on its stack)."""
    count = symbols.count - skip
    if count < 0 or skip < 0:
        raise ValueError('skip outside the packet')
    stick_bytes = [None] * 4
    for position, channel in enumerate(WIRE_ORDER):
        stick_bytes[position] = apply_axis_symbols(state.ch[channel], symbols.sticks[position][skip:], fpu)
    out = []
    for index in range(skip, symbols.count):
        op = symbols.yaw[index]
        if op[0] == 'keep':
            state.yaw_pred = s16(state.yaw_pred + state.yaw_delta)
        elif op[0] == 'delta':
            state.yaw_delta = s16(op[1])
            state.yaw_pred = s16(state.yaw_pred + op[1])
        else:
            state.yaw_pred = s16(op[1])
        word = ((state.yaw_pred & M32) & 0xFFFFFFFE) | symbols.flags[index]
        sticks = tuple(stick_bytes[p][index - skip] for p in range(4))
        out.append(struct.pack('<H6BI', symbols.buttons[index], *(sticks + (0, 0)), word))
    state.count = s32(state.count + count)
    return out


def decode_frames(state, data, count, skip=0, fpu=DEFAULT_FPU):
    """read_frames + apply_frames; returns (wire records of frames skip.., stream bits)."""
    symbols = read_frames(data, count)
    return apply_frames(state, symbols, skip, fpu), symbols.bits


def local_roundtrip(record, encoder, decoder, fpu=DEFAULT_FPU):
    """What the tick does to the local player's own record before using it (encoder calls
    0x13a29c-0x13a328, decoder calls 0x13a84c-0x13a99c, pad_apply at 0x13ac84): encode the
    one frame with g_simEncState 0x5bf798 and decode it with g_simDecState 0x5bf7e8, so the
    local machine sees the values every other machine decodes.  Prediction does the same
    with 0x5bf6f8 / 0x5bf748.  The two pressure bytes keep their sampled values."""
    writer = encode_frames(encoder, [record])
    decoded, _bits = decode_frames(decoder, writer.tobytes(), 1, 0, fpu)
    return decoded[0][:6] + bytes(record[6:8]) + decoded[0][8:]


def fpu_sensitivity(samples, models=Fpu.MODELS):
    """{model: decoded bytes} for one channel fed `samples` from the reset state - the
    measurement behind "where the last bit is uncertain"."""
    out = {}
    for model in models:
        enc, dec, fpu = Channel(), Channel(), Fpu(model)
        out[model] = apply_axis_symbols(dec, axis_symbols(enc, samples), fpu)
    return out


# =======================================================================================
# 5. Packets
# =======================================================================================

PKT_LAN_ANNOUNCE = 0xBD3D   # developer LAN lobby, 4 bytes, broadcast (0x1345c0)
PKT_LAN_START = 0xBD3E      # developer LAN lobby, 4 bytes, sent 8 times
PKT_INPUT = 0xBD3F
SYNC_MARKER = 0xBD40        # not a packet type: marks a sync record inside a packet
PKT_KICK_REQUEST = 0xBD41
PKT_RAW_RELAY = 0xBD42
PKT_KICKED = 0xBD43
PKT_DIRECT = 0xBD44         # .. 0xbd47, handler index = type - 0xbd44
NO_SYNC = 0xFFFFFFFF

RECV_BUFFER = 0x7C0         # size passed to sceInetRecvFrom, 0x13c140
SEND_BUFFER = 0x1390        # room in the builder's stack frame before the datagram would
                            # run into its own copy of the codec state ($fp+0x10..+0x13a0)
RAW_RELAY_DEPTH = 40        # frames before the newest that a relay carries, 0x13c370
MSG_RING = 0x2000
SEND_CYCLES = (6, 2, 4, 6)  # data 0x4027e8, indexed by the number of remote active peers


def header(kind, last, slot, mask, byte9, count, ack_delta):
    """The 12-byte header of an input packet or raw relay (0x137e1c-0x137f0c).
       0 u32 type            4 u32 last frame in the packet
       8 u8  low nibble slot the frames belong to, high nibble sender's active mask
       9 u8  input: last frame - sender's simulation frame; relay: relaying machine's slot
      10 u8  number of frames
      11 s8  newest frame the sender holds from the addressee, minus `last`"""
    return struct.pack('<IIBBBB', kind & M32, last & M32, (slot | (mask << 4)) & 0xFF,
                       byte9 & 0xFF, count & 0xFF, ack_delta & 0xFF)


class Packet:
    """Stateless view of an input packet or raw relay (parse_packet)."""

    def __init__(self):
        self.kind = self.last = self.slot = self.mask = self.byte9 = self.count = self.ack_delta = 0
        self.symbols = None         # FrameSymbols (input packet)
        self.raw_records = None     # list of 12-byte records (raw relay)
        self.stream_bytes = 0
        self.sync_offset = 0
        self.sync = None            # (frame, saved frame counter, hash) or None
        self.sync_word = 0
        self.blocks = []            # (frame, payload bytes) in packet order
        self.blocks_offset = 0

    @property
    def first(self):
        return self.last - self.count + 1

    @property
    def ack(self):
        return self.last + self.ack_delta

    @property
    def sim_frame(self):
        """Sender's simulation frame as an input packet reports it."""
        return self.last - self.byte9


def parse_packet(data):
    """Take an input packet (0xbd3f) or raw relay (0xbd42) apart without any peer state,
    following the receiver 0x13b5d0 from 0x13b7b0 on.  Message block frames are returned
    as (last - offset) & 0xff resolved against `last`, i.e. the frame the receiver's ring
    index stands for when the block is within 255 frames of `last`."""
    data = bytes(data)
    if len(data) < 16:
        raise MalformedPacket('shorter than a header and a sync word')
    pkt = Packet()
    pkt.kind, pkt.last, b8, pkt.byte9, pkt.count, ack = struct.unpack_from('<IiBBBb', data)
    if pkt.kind not in (PKT_INPUT, PKT_RAW_RELAY):
        raise MalformedPacket('not an input packet or raw relay')
    pkt.slot, pkt.mask, pkt.ack_delta = b8 & 15, b8 >> 4, ack
    if pkt.count == 0:
        raise MalformedPacket('no frames')
    if pkt.kind == PKT_INPUT:
        pkt.symbols = read_frames(data[12:], pkt.count)
        pkt.stream_bytes = (pkt.symbols.bits + 7) >> 3
    else:
        pkt.stream_bytes = pkt.count * 12
        if len(data) < 12 + pkt.stream_bytes:
            raise MalformedPacket('raw relay shorter than its frame count')
        pkt.raw_records = [data[12 + i * 12:24 + i * 12] for i in range(pkt.count)]
    pkt.sync_offset = (12 + pkt.stream_bytes + 3) & ~3
    if len(data) < pkt.sync_offset + 4:
        raise MalformedPacket('ends before the sync word')
    pkt.sync_word = struct.unpack_from('<I', data, pkt.sync_offset)[0]
    offset = pkt.sync_offset + 4
    if pkt.sync_word == SYNC_MARKER:
        if len(data) < offset + 12:
            raise MalformedPacket('ends inside the sync record')
        pkt.sync = struct.unpack_from('<III', data, offset)
        offset += 12
    pkt.blocks_offset = offset
    while offset != len(data):
        if offset + 2 > len(data) or offset + 2 + data[offset + 1] > len(data):
            raise MalformedPacket('message block runs past the end of the datagram (the '
                                  'original keeps walking through memory)')
        size = data[offset + 1]
        pkt.blocks.append((pkt.last - data[offset], data[offset + 2:offset + 2 + size]))
        offset += size + 2
    return pkt


def kick_request(requester_slot, kick_mask):
    """0xbd41, 12 bytes: {type, requester's slot, bit mask of the peers whose kick state is
    1 on the requester} (net_main 0x133148-0x133234)."""
    return struct.pack('<III', PKT_KICK_REQUEST, requester_slot & M32, kick_mask & M32)


def kicked_notice():
    """0xbd43, 4 bytes (net_main 0x132f54-0x132fdc)."""
    return struct.pack('<I', PKT_KICKED)


def direct_message(index, payload):
    """0xbd44 + index, then the payload verbatim (net_sendMsgToPeers 0x131b00).  The sender
    copies the payload into a 508-byte stack buffer without a length check."""
    if not 0 <= index < 4:
        raise ValueError('handler index 0..3')
    return struct.pack('<I', PKT_DIRECT + index) + bytes(payload)


def lan_packet(start=False):
    """Developer LAN lobby (0x1345c0, only with flag 0x402792): 4 bytes."""
    return struct.pack('<I', PKT_LAN_START if start else PKT_LAN_ANNOUNCE)


# =======================================================================================
# 6. One machine's state
# =======================================================================================

PEER_SIZE = 0x44E0
RING_OFFSET, SYNC_OFFSET, MSG_OFFSET = 0xAC, 0x18AC, 0x24AC


class Peer:
    """One entry of g_peers 0x5bf838 (0x44e0 bytes).  pack() / unpack() give the exact
    memory image; the comment on each line is the offset."""

    def __init__(self):
        self.ip = bytes(4)                  # +0x00
        self.port = 0                       # +0x04
        self.unknown8 = bytes(8)            # +0x08 not referenced by the code read
        self.recv_state = CodecState()      # +0x10 state after the newest frame received
        self.send_frame = 0                 # +0x5c frame up to which send_state is advanced
        self.send_state = CodecState()      # +0x60 state just before frame `acked`
        self.ring = bytearray(256 * 24)     # +0xac input records, index = frame & 0xff
        self.sync_ring = bytearray(256 * 12)   # +0x18ac {frame, saved counter, hash}
        self.msg_ring = bytearray(MSG_RING)    # +0x24ac game-message bytes
        self.msg_write = 0                  # +0x44ac
        self.msg_read = 0                   # +0x44b0 written by the tick, never read
        self.pad_prev = [0, 0]              # +0x44b4 pad_apply's previous buttons, repeat count
        self.newest = 0                     # +0x44bc newest frame received from this peer
        self.acked = 0                      # +0x44c0 newest of our frames it acknowledged
        self.lead = 0                       # +0x44c4 its last frame minus its simulation frame
        self.sim = 0                        # +0x44c8 its simulation frame as last reported
        self.silence = 0                    # +0x44cc net_main calls since an accepted packet
        self.heard = 0                      # +0x44d0
        self.local = 0                      # +0x44d4 u8
        self.dropped = 0                    # +0x44d5 u8
        self.kick = 0                       # +0x44d6 u8: 0, 1 negotiating, 2 negotiated
        self.oos = 0                        # +0x44d7 u8 out of sync
        self.drop_frame = 0                 # +0x44d8
        self.kicked_notice = 0              # +0x44dc

    # ---- records ----
    def record(self, frame):
        """(frame number stored, wire record, message start, message count) of ring slot
        frame & 0xff."""
        base = (frame & 0xFF) * 24
        number, start, count = struct.unpack_from('<I12xII', self.ring, base)
        return number, bytes(self.ring[base + 4:base + 16]), start, count

    def wire_record(self, frame):
        base = (frame & 0xFF) * 24
        return bytes(self.ring[base + 4:base + 16])

    def set_record(self, frame, wire, start=None, count=None):
        base = (frame & 0xFF) * 24
        struct.pack_into('<I', self.ring, base, frame & M32)
        self.ring[base + 4:base + 16] = bytes(wire)
        if start is not None:
            struct.pack_into('<I', self.ring, base + 16, start & M32)
        if count is not None:
            struct.pack_into('<I', self.ring, base + 20, count & M32)

    def msg_count(self, frame):
        return struct.unpack_from('<I', self.ring, (frame & 0xFF) * 24 + 20)[0]

    def msg_start(self, frame):
        return struct.unpack_from('<I', self.ring, (frame & 0xFF) * 24 + 16)[0]

    def sync(self, frame):
        return struct.unpack_from('<III', self.sync_ring, (frame & 0xFF) * 12)

    def set_sync(self, frame, saved, value):
        struct.pack_into('<III', self.sync_ring, (frame & 0xFF) * 12, frame & M32, saved & M32, value & M32)

    @property
    def inactive(self):
        """Out of the active mask: dropped, being kicked or out of sync (0x137df0)."""
        return bool(self.dropped or self.kick or self.oos)

    # ---- memory image ----
    def pack(self):
        return b''.join((
            self.ip, struct.pack('<I', self.port & M32), self.unknown8, self.recv_state.pack(),
            struct.pack('<i', s32(self.send_frame)), self.send_state.pack(), bytes(self.ring),
            bytes(self.sync_ring), bytes(self.msg_ring),
            struct.pack('<IIII', self.msg_write & M32, self.msg_read & M32,
                        self.pad_prev[0] & M32, self.pad_prev[1] & M32),
            struct.pack('<6i', *[s32(v) for v in (self.newest, self.acked, self.lead, self.sim,
                                                   self.silence, self.heard)]),
            bytes((self.local & 0xFF, self.dropped & 0xFF, self.kick & 0xFF, self.oos & 0xFF)),
            struct.pack('<ii', s32(self.drop_frame), s32(self.kicked_notice))))

    @classmethod
    def unpack(cls, image):
        image = bytes(image)
        if len(image) != PEER_SIZE:
            raise ValueError('a peer is 0x44e0 bytes')
        p = cls()
        p.ip, p.port, p.unknown8 = image[0:4], struct.unpack_from('<I', image, 4)[0], image[8:16]
        p.recv_state = CodecState.unpack(image[0x10:0x5C])
        p.send_frame = struct.unpack_from('<i', image, 0x5C)[0]
        p.send_state = CodecState.unpack(image[0x60:0xAC])
        p.ring = bytearray(image[RING_OFFSET:SYNC_OFFSET])
        p.sync_ring = bytearray(image[SYNC_OFFSET:MSG_OFFSET])
        p.msg_ring = bytearray(image[MSG_OFFSET:0x44AC])
        p.msg_write, p.msg_read, a, b = struct.unpack_from('<IIII', image, 0x44AC)
        p.pad_prev = [a, b]
        (p.newest, p.acked, p.lead, p.sim, p.silence, p.heard) = struct.unpack_from('<6i', image, 0x44BC)
        p.local, p.dropped, p.kick, p.oos = image[0x44D4:0x44D8]
        p.drop_frame, p.kicked_notice = struct.unpack_from('<ii', image, 0x44D8)
        return p


class Sent:
    """One datagram handed to sceInetSendTo."""
    __slots__ = ('peer', 'ip', 'port', 'data', 'undefined')

    def __init__(self, peer, ip, port, data, undefined=()):
        self.peer, self.ip, self.port, self.data, self.undefined = peer, ip, port, data, tuple(undefined)

    def __repr__(self):
        return 'Sent(peer %d, %d bytes, type 0x%x)' % (
            self.peer, len(self.data), struct.unpack_from('<I', self.data)[0] if len(self.data) >= 4 else 0)


class Machine:
    """The netcode state of one console and the operations on it.

    Only what the wire depends on is modelled.  The simulation itself is a hook
    (run_tasks), game-message handlers are hooks (handlers), the pad sample, camera yaw and
    engine_frameStep() value are arguments of net_main().

    Globals mirrored (address): lif g_localInputFrame 0x4027a4, last_sent 0x4027a8,
    net_frame g_netFrame 0x4027ac, cycle 0x4027b0, phase 0x4027b4, modem 0x4027b8,
    last_hash_frame 0x4027cc, stall 0x4027d0, ended 0x4027d8, eq 0x4027dc, min_ready
    0x4027e0, win 0x4027e4, long_stall 0x40279c, kicked 0x4027a0, kick_state 0x5d1450,
    kick_acks 0x5d1454, msg_attached 0x5d14d8, cam_yaw 0x5d0bc0, input_lock 0x5d0bc8,
    sim_enc 0x5bf798, sim_dec 0x5bf7e8, sim_frame g_simFrame 0x44fdcc, rand_seed 0x404464,
    sync_acc 0x4027c0."""

    def __init__(self, num_peers=2, local=0, fpu=DEFAULT_FPU):
        self.fpu = fpu
        self.network_mode = 1
        self.num_peers = num_peers
        self.peers = [Peer() for _ in range(4)]
        for index in range(4):
            # the launch (0x13768c) sets acked = 1 for all four; net_shutdown 0x1393f8 has
            # zeroed everything else and reset both codec states of every peer
            self.peers[index].acked = 1
        self.peers[local].local = 1
        self.lif = 1
        self.last_sent = 1
        self.net_frame = 1
        self.cycle = 0
        self.phase = 0
        self.modem = 0
        self.last_hash_frame = 1    # net_startSync 0x13dce0 copies g_netFrame into it
        self.stall = 0
        self.ended = 0
        self.eq = 0
        self.min_ready = 100
        self.win = 0
        self.long_stall = 0
        self.kicked = 0
        self.kick_state = 0
        self.kick_acks = [0, 0, 0, 0]
        self.msg_attached = 0
        self.cam_yaw = [0, 0, 0, 0]
        self.input_lock = [[0, 0, 0] for _ in range(4)]     # calls left, button mask, centre sticks
        self.sim_enc, self.sim_dec = CodecState(), CodecState()
        self.send_cycles = list(SEND_CYCLES)
        self.sim_frame = 0
        self.rand_seed = 0
        self.sync_acc = 0
        self.level_pending = False  # a level name waits in 0x41b6d0: ticks do nothing
        self.num_players = num_peers
        self.positions = [None] * 4     # per player slot: (x, y, z) float patterns or None
        self.pads = [bytearray(PAD_SIZE) for _ in range(4)]
        self.pad_globals = PadGlobals()
        self.handlers = {}          # game-message id -> callable(payload bytes)
        self.direct_handlers = [None] * 4   # callable(payload bytes)
        self.run_tasks = None       # callable(machine): the simulation step
        self.on_kill = None         # callable(slot): a kicked peer's player dies this tick
        self.first_active_hook = None   # callable(slot) when this machine announces a drop
        self.outbox = []
        self.log = []               # text the original prints (out of sync, drops)
        # Two things the original leaves to chance.  A differential test supplies what the
        # original actually had; left at None the model uses zeros.
        self.stack_bytes = None     # callable(slot, frame) -> the 2 pressure bytes a
                                    # received frame ends up with (receiver's stack)
        self.sample_garbage = None  # callable(frame) -> message-start word of a freshly
                                    # sampled local record (net_main's stack)

    # ---- small queries ----
    @property
    def local_slot(self):
        """net_getLocalPlayerSlot(0) 0x13e1f0: first peer with the local byte set, -1 if
        none; 0 when not in network mode."""
        if not self.network_mode:
            return 0
        for index in range(self.num_peers):
            if self.peers[index].local:
                return index
        return -1

    def active_mask(self):
        """Bit per peer that is not dropped, not being kicked and not out of sync
        (0x137df0-0x137e18; the same loop at 0x13b6c4-0x13b6e8)."""
        mask = 0
        for index in range(self.num_peers):
            if not self.peers[index].inactive:
                mask |= 1 << index
        return mask

    def remote_active(self):
        """Peers with local, dropped and kick all clear (0x133764): the ones packets go to.
        Out-of-sync peers are still served."""
        return [i for i in range(self.num_peers)
                if not (self.peers[i].local or self.peers[i].dropped or self.peers[i].kick)]

    def is_first_active(self):
        """net_localIsFirstActive 0x13d668: the lowest player slot that is not dropped is
        this machine's."""
        first = 0
        for index in range(self.num_players):
            alive = True
            if self.network_mode:
                alive = index < self.num_peers and not self.peers[index].dropped
            if alive:
                first = index
                break
        return first == self.local_slot

    # ---- game messages ----
    def queue_message(self, ident, payload):
        """net_sendGameMsg 0x13db38 in network mode: append {id, length, bytes} to the local
        peer's message ring.  The length is stored in one byte."""
        peer = self.peers[self.local_slot]
        size = len(payload)
        peer.msg_ring[peer.msg_write & 0x1FFF] = ident & 0xFF
        peer.msg_ring[(peer.msg_write + 1) & 0x1FFF] = size & 0xFF
        for index, byte in enumerate(bytes(payload)):
            peer.msg_ring[(peer.msg_write + 2 + index) & 0x1FFF] = byte
        peer.msg_write = (peer.msg_write + size + 2) & 0x1FFF

    def attach_messages(self):
        """net_main 0x1336c4-0x13375c: everything queued since the last attach goes onto
        one frame nobody has been sent yet - max(last_sent + 1, net_frame) - and only when
        that frame already exists (last_sent < lif - 1)."""
        if not self.last_sent < self.lif - 1:
            return None
        peer = self.peers[self.local_slot]
        if peer.msg_write == self.msg_attached:
            return None
        frame = max(self.last_sent + 1, self.net_frame)
        base = (frame & 0xFF) * 24
        count = struct.unpack_from('<I', peer.ring, base + 20)[0]
        if count == 0:
            struct.pack_into('<I', peer.ring, base + 16, self.msg_attached & M32)
        struct.pack_into('<I', peer.ring, base + 20,
                         (count + ((peer.msg_write - self.msg_attached) & 0x1FFF)) & M32)
        self.msg_attached = peer.msg_write
        return frame

    def frame_messages(self, slot, frame):
        """The {id, payload} messages attached to a frame of a peer, as the tick walks them
        (0x13ac90-0x13ad54)."""
        peer = self.peers[slot]
        left, pos = peer.msg_count(frame), peer.msg_start(frame)
        out = []
        while left != 0:
            if left < 0:
                raise MalformedPacket('message bytes of a frame do not add up (the original loops)')
            ident = peer.msg_ring[pos & 0x1FFF]
            size = peer.msg_ring[(pos + 1) & 0x1FFF]
            out.append((ident, bytes(peer.msg_ring[(pos + 2 + i) & 0x1FFF] for i in range(size))))
            left -= size + 2
            pos = (pos + size + 2) & 0x1FFF
        return out, pos

    # ---- sending ----
    def build_packet(self, dest, first, last, kind, owner, state, raw=False):
        """net_sendInputPacket 0x137d60 (peer, firstFrame, lastFrame, type, slot,
        codecState, raw).  Returns a Sent; advances last_hash_frame when a sync record goes
        out.  `state` is copied, not changed (the persistent state is advanced by net_main
        before the call).

        After the frames: aligned to 4, either 0xbd40 and the 12-byte sync record of
        `owner`'s sync ring for g_netFrame, or 0xffffffff when a record was already sent
        for this g_netFrame; then {u8 last - frame, u8 byte count, bytes} for every frame
        of the packet that has message bytes."""
        peer = self.peers[dest]
        count = last - first + 1
        if not 1 <= count <= 255:
            raise ValueError('frame count %d: outside what the header byte and the encoder allow' % count)
        if raw:
            byte9 = self.local_slot
        else:
            byte9 = last - (self.net_frame & 0xFF)
        out = bytearray(header(kind, last, owner, self.active_mask(), byte9, count, peer.newest - last))
        source = self.peers[owner]
        undefined = []
        if raw:
            for frame in range(first, last + 1):
                out += source.wire_record(frame)
        else:
            work = state.copy()
            if first > peer.send_frame:
                # the builder's own catch-up pass, 0x137fd0-0x1388cc (never needed when
                # called from net_main, which has already advanced the state)
                encode_frames(work, [source.wire_record(f) for f in range(peer.send_frame, first)])
            writer = encode_frames(work, [source.wire_record(f) for f in range(first, last + 1)])
            used = (writer.pos + 7) >> 3
            padded = (used + 3) & ~3
            stream = writer.tobytes()
            for index in range(len(stream), padded):
                undefined.append(12 + index)        # never stored by the builder
            out += (stream + bytes(padded))[:padded]
        while len(out) & 3:
            out.append(0)
        if self.last_hash_frame == self.net_frame:
            out += struct.pack('<I', NO_SYNC)
        else:
            self.last_hash_frame = self.net_frame
            out += struct.pack('<I', SYNC_MARKER)
            out += bytes(source.sync_ring[(self.net_frame & 0xFF) * 12:(self.net_frame & 0xFF) * 12 + 12])
        for frame in range(first, last + 1):
            size = source.msg_count(frame)
            if size != 0:
                start = source.msg_start(frame)
                out += bytes(((last - frame) & 0xFF, size & 0xFF))
                out += bytes(source.msg_ring[(start + i) & 0x1FFF] for i in range(size))
        if len(out) > SEND_BUFFER:
            raise ValueError('a %d-byte datagram: the original has overrun its stack buffer' % len(out))
        sent = Sent(dest, peer.ip, peer.port, bytes(out), undefined)
        self.outbox.append(sent)
        return sent

    def send_input(self, dest):
        """net_main 0x13385c-0x1341c0 for one peer: advance the persistent send state over
        the frames the peer has acknowledged since last time (they are encoded into a
        scratch stream that is thrown away), then send frames acked .. lif - 1."""
        peer = self.peers[dest]
        local = self.peers[self.local_slot]
        if peer.acked > peer.send_frame:
            encode_frames(peer.send_state, [local.wire_record(f) for f in range(peer.send_frame, peer.acked)])
            peer.send_frame = peer.acked
        elif peer.acked < peer.send_frame:
            raise ValueError('acknowledged frame went backwards')
        sent = self.build_packet(dest, peer.acked, self.lif - 1, PKT_INPUT, self.local_slot, peer.send_state)
        self.last_sent = self.lif
        return sent

    def send_direct(self, index, peer_mask, payload):
        """net_sendMsgToPeers 0x131b00 (index, peerMask, bytes, n): to every remote peer in
        the mask that is not dropped; for the local peer the registered handler is called
        instead."""
        if not self.network_mode:
            return
        data = direct_message(index, payload)
        for slot in range(self.num_peers):
            if not (peer_mask >> slot) & 1:
                continue
            peer = self.peers[slot]
            if peer.local:
                if self.direct_handlers[index]:
                    self.direct_handlers[index](bytes(payload))
            elif not peer.dropped:
                self.outbox.append(Sent(slot, peer.ip, peer.port, data))

    def kick_peer(self, slot):
        """net_kickPeer 0x131cb8: manual kick of a remote, live, not yet kicked peer."""
        if slot < self.num_peers:
            peer = self.peers[slot]
            if not (peer.local or peer.dropped or peer.kick):
                self.log.append('kick %d' % slot)
                peer.kick = 1
                peer.drop_frame = -1
                peer.kicked_notice = 1
                self.kick_acks = [0, 0, 0, 0]
                self.kick_state = 1

    # ---- receiving ----
    def receive(self, data, raw=False):
        """The receiver 0x13b5d0 (packet, length, raw) for a 0xbd3f (raw False) or 0xbd42
        (raw True) datagram.  Returns the list of frames newly stored (empty when the
        packet was ignored or brought nothing new).

        In order:
          ignored entirely unless the sender's active mask equals ours, the slot is not
            ours, not dropped, not out of sync, and not being kicked (a raw relay is taken
            for a peer being kicked);
          silence = 0, heard = 1; input: sim = last - byte 9; relay: kick_acks[byte 9] = 1;
            lead = last - sim;
          stop if last <= newest;
          acked = max(acked, last + ack byte);
          stop if the packet's first frame is later than newest + 1;
          decode, skipping the frames already held; store the new ones with message count
            0; newest = last;
          sync record: stored, and compared with this machine's own record for that frame;
          message blocks: copied into the peer's message ring for frames whose count is 0."""
        data = bytes(data)
        if len(data) < 12:
            raise MalformedPacket('shorter than the header the receiver reads')
        _kind, last, b8, byte9, count, ack = struct.unpack_from('<IiBBBb', data)
        if b8 >> 4 != self.active_mask():
            return []
        slot = b8 & 15
        if slot > 3:
            raise MalformedPacket('slot %d: the original indexes past its four-entry table' % slot)
        peer = self.peers[slot]
        if peer.local or peer.dropped:
            return []
        if peer.kick and not raw:
            return []
        if peer.oos:
            return []
        peer.silence = 0
        peer.heard = 1
        if raw:
            if byte9 > 3:
                raise MalformedPacket('relay slot %d: the original stores a byte past its '
                                      'four acknowledgement flags' % byte9)
            self.kick_acks[byte9] = 1
        else:
            peer.sim = last - byte9
        peer.lead = s32(last - peer.sim)
        if not peer.newest < last:
            return []
        peer.acked = max(peer.acked, last + ack)
        first = last - count + 1
        if peer.newest + 1 < first:
            return []
        skip = peer.newest - first + 1
        if raw:
            stream_bytes = count * 12
            if len(data) < 12 + stream_bytes:
                raise MalformedPacket('raw relay shorter than its frame count')
            records = [data[12 + i * 12:24 + i * 12] for i in range(skip, count)]
        else:
            symbols = read_frames(data[12:], count)
            records = apply_frames(peer.recv_state, symbols, skip, self.fpu)
            stream_bytes = (symbols.bits + 7) >> 3
        stored = []
        for index, record in enumerate(records):
            frame = first + skip + index
            if not raw and self.stack_bytes is not None:
                record = record[:6] + bytes(self.stack_bytes(slot, frame)) + record[8:]
            peer.set_record(frame, record, count=0)
            stored.append(frame)
        peer.newest = last
        offset = (12 + stream_bytes + 3) & ~3
        if len(data) < offset + 4:
            raise MalformedPacket('ends before the sync word')
        word = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if word == SYNC_MARKER:
            if len(data) < offset + 12:
                raise MalformedPacket('ends inside the sync record')
            frame, saved, value = struct.unpack_from('<III', data, offset)
            offset += 12
            peer.set_sync(frame, saved, value)
            mine = self.peers[self.local_slot].sync(frame)
            if mine[0] == frame and mine[0] != 0 and mine[2] != value:
                peer.oos = 1
                self.log.append('out of sync %d' % slot)
        while offset != len(data):
            if offset + 2 > len(data) or offset + 2 + data[offset + 1] > len(data):
                raise MalformedPacket('message block runs past the end of the datagram')
            frame = (last - data[offset]) & 0xFF
            size = data[offset + 1]
            base = frame * 24
            if struct.unpack_from('<I', peer.ring, base + 20)[0] == 0:
                struct.pack_into('<II', peer.ring, base + 16, peer.msg_write & M32, size)
                for index in range(size):
                    peer.msg_ring[(peer.msg_write + index) & 0x1FFF] = data[offset + 2 + index]
                peer.msg_write = (peer.msg_write + size) & 0x1FFF
            offset += size + 2
        return stored

    def dispatch(self, data):
        """One datagram through net_pumpReceive 0x13c078.  Returns the frames stored for
        input packets and relays, None otherwise."""
        data = bytes(data)
        if len(data) < 4:
            raise MalformedPacket('shorter than the type word')
        kind = struct.unpack_from('<I', data)[0]
        if PKT_DIRECT <= kind < PKT_DIRECT + 4:
            handler = self.direct_handlers[kind - PKT_DIRECT]
            if handler:
                handler(data[4:])
            return None
        if kind == PKT_KICK_REQUEST:
            if len(data) < 12:
                raise MalformedPacket('short kick request')
            requester, mask = struct.unpack_from('<Ii', data, 4)
            for slot in range(self.num_peers):
                if (mask >> slot) & 1 and not self.peers[slot].kick:
                    self.peers[slot].kick = 1
                    self.peers[slot].drop_frame = -1
                    self.kick_acks = [0, 0, 0, 0]
                    self.kick_state = 1
            if requester > 3:
                raise MalformedPacket('requester slot outside the peer table')
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                if not peer.local and not peer.dropped and (mask >> slot) & 1:
                    # the answer: the kicked peer's last 41 frames, verbatim (0x13c2e4-0x13c3a8)
                    self.build_packet(requester, max(peer.newest - RAW_RELAY_DEPTH, 0), peer.newest,
                                      PKT_RAW_RELAY, slot, None, raw=True)
            return None
        if kind == PKT_INPUT:
            return self.receive(data, raw=False)
        if kind == PKT_RAW_RELAY:
            return self.receive(data, raw=True)
        if kind == PKT_KICKED:
            self.kicked = 1
        return None

    # ---- the per-rendered-frame driver ----
    def net_main(self, sample, yaw=0, camera_flag=0, frame_step=1, no_sim=False, hold_arg=False,
                 render_frame=0, inbox=()):
        """net_main 0x132e90 (noSim, holdInput), the wire-relevant part.

        sample        8 bytes as the pad sampler 0x17421c writes them: u16 buttons, record
                      bytes +6..+0xb
        yaw           16-bit camera yaw; camera_flag = 1 when the camera mode field is not 1
        frame_step    what engine_frameStep() 0x19e3a8 returns during this call (1 or 2)
        render_frame  the rendered-frame counter 0x44fdd0 (kick requests go out when it is
                      a multiple of 30)
        inbox         datagrams waiting on the socket
        Returns (datagrams sent, held, simulation steps run)."""
        self.outbox = []
        local = self.local_slot
        for data in inbox:
            self.dispatch(data)

        # kicked notices: every 10th call for 120 calls after a manual kick (0x132f24-0x132fdc)
        if not no_sim:
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                counter = peer.kicked_notice
                if counter != 0:
                    peer.kicked_notice = counter + 1
                    if counter > 0x78:
                        peer.kicked_notice = 0
                    if counter % 10 == 0:
                        self.outbox.append(Sent(slot, peer.ip, peer.port, kicked_notice()))

        # silence: a remote, live peer not heard for more than 900 calls is kicked (0x133060-0x1330a8)
        for slot in range(self.num_peers):
            peer = self.peers[slot]
            if not (peer.local or peer.dropped or peer.kick):
                quiet = peer.silence
                peer.silence = quiet + 1
                if quiet > 900:
                    peer.kick = 1
                    peer.drop_frame = -1
                    self.kick_acks = [0, 0, 0, 0]
                    self.kick_state = 1

        # kick negotiation (0x1330c4-0x133340)
        if self.kick_state == 1 and render_frame % 30 == 0:
            everyone = True
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                if not (peer.local or peer.dropped or peer.kick) and not self.kick_acks[slot]:
                    mask = 0
                    for other in range(self.num_peers):
                        if self.peers[other].kick == 1:
                            mask |= 1 << other
                    self.outbox.append(Sent(slot, peer.ip, peer.port, kick_request(local, mask)))
                    everyone = False
            if everyone:
                self.kick_state = 2
                for slot in range(self.num_peers):
                    if self.peers[slot].kick:
                        self.peers[slot].drop_frame = self.peers[slot].newest + 1
        if self.kick_state == 2 and render_frame % 30 == 0:
            self.log.append('kick agreed')
            for slot in range(self.num_peers):
                if self.peers[slot].kick == 1:
                    self.peers[slot].kick = 2
            self.kick_state = 0

        # pacing inputs (0x13334c-0x133424)
        min_sim = self.net_frame
        min_lead = self.lif - self.net_frame
        for slot in range(self.num_peers):
            peer = self.peers[slot]
            if not (peer.local or peer.dropped or peer.kick):
                min_lead = min(min_lead, peer.lead)
                min_sim = min(min_sim, peer.sim)
        excess = (self.lif - self.net_frame) - min_lead

        # the sample, the camera word and the input lock (0x133420-0x13353c)
        buttons, s6, s7, s8, s9, p10, p11 = struct.unpack('<H6B', bytes(sample[:8]))
        word = (s16(yaw & 0xFFFE) & M32) | (1 if camera_flag else 0)
        lock = self.input_lock[local]
        if lock[0] != 0:
            lock[0] -= 1
            p10 = p11 = 0
            buttons &= ~lock[1] & 0xFFFF
            if lock[2] != 0:
                s6 = s7 = s8 = s9 = 0x80
        record = struct.pack('<H6BI', buttons, s6, s7, s8, s9, p10, p11, word)

        # hold decision (0x133548-0x133608)
        held = self.lif - min_sim > 0x26
        if excess < 5:
            self.eq = 0
        else:
            self.eq += 1
            if self.eq > 0x1E:
                self.eq = 0
                held = True
        if hold_arg:
            held = True
        window = self.win
        self.win = window + 1
        lowest = self.min_ready
        if window > 0x3C:
            self.win = 0
            self.min_ready = 100
            if lowest > 2:
                held = True
        if self.lif < 3:
            held = False

        # sample frame_step records (0x133610-0x1336b8)
        if not held:
            for _ in range(frame_step):
                start = self.sample_garbage(self.lif) if self.sample_garbage is not None else 0
                self.peers[local].set_record(self.lif, record, start=start, count=0)
                self.lif += 1

        self.attach_messages()

        # send rotation (0x133764-0x134204)
        targets = self.remote_active()
        self.cycle = self.send_cycles[len(targets)]
        if self.modem:
            self.cycle += self.cycle >> 1
        for turn, slot in enumerate(targets):
            if self.phase == (turn * self.cycle) // len(targets):
                self.send_input(slot)
        self.phase += 1
        if self.phase >= self.cycle:
            self.phase = 0

        # drops that are due (0x13420c-0x1342a4)
        for slot in range(self.num_peers):
            peer = self.peers[slot]
            if peer.kick and not peer.dropped and peer.drop_frame == self.net_frame:
                self.log.append('drop %d' % slot)
                peer.dropped = 1
                if self.is_first_active() and self.first_active_hook:
                    self.first_active_hook(slot)

        # ready scan and the tick (0x1342a8-0x134400)
        ready = 0
        limit = self.lif - self.net_frame - 1
        while ready < limit:
            frame = self.net_frame + ready
            if any(not self.peers[s].dropped and self.peers[s].record(frame)[0] != frame & M32
                   for s in range(self.num_peers)):
                break
            ready += 1
        self.min_ready = min(self.min_ready, ready)
        steps = 0 if no_sim else min(ready, frame_step)
        if steps < 1:
            self.stall += 1
        else:
            self.stall = 0
            self.tick(steps)
        if not self.ended and self.stall > 300:
            self.long_stall += 1
        else:
            self.long_stall = 0
        return list(self.outbox), held, steps

    # ---- the tick ----
    def tick(self, steps):
        """net_frameLoop 0x139e88 (steps), the part that touches netcode state.

        Per step, unless a level name is pending: for every peer that is not dropped, in
        slot order - take its record for g_netFrame (the local one through
        local_roundtrip), pad_apply it to that slot's lockstep pad with the peer's
        previous-state block, store the low 16 bits of the yaw word in cam_yaw, run the
        frame's game messages; then kill the players of peers whose drop frame this is, run
        the simulation, advance g_netFrame and store the sync record for the NEW frame
        number: hash = sync_acc + rand_seed + the truncated x, y, z of every player
        object.  The new record is compared with every remote, not dropped peer's record
        for the same frame; a different hash sets that peer's out-of-sync byte."""
        local = self.local_slot
        for _ in range(steps):
            if self.level_pending:
                continue
            frame = self.net_frame
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                if peer.dropped:
                    continue
                _number, record, _start, _count = peer.record(frame)
                if slot == local:
                    record = local_roundtrip(record, self.sim_enc, self.sim_dec, self.fpu)
                pad_apply(self.pads[slot], record, peer.pad_prev, self.pad_globals, self.fpu)
                self.cam_yaw[slot] = struct.unpack_from('<H', record, 8)[0]
                if peer.msg_count(frame) != 0:
                    messages, position = self.frame_messages(slot, frame)
                    for ident, payload in messages:
                        handler = self.handlers.get(ident)
                        if handler:
                            handler(payload)
                    if slot != local:
                        peer.msg_read = position
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                if peer.kick and peer.drop_frame == self.net_frame and self.positions[slot] is not None:
                    if self.on_kill:
                        self.on_kill(slot)
            if self.run_tasks:
                self.run_tasks(self)
            self.net_frame += 1
            value = sync_hash(self.rand_seed, self.sync_acc, self.positions[:self.num_players])
            mine = self.peers[local]
            mine.set_sync(self.net_frame, self.sim_frame, value)
            for slot in range(self.num_peers):
                peer = self.peers[slot]
                if peer.local or peer.dropped:
                    continue
                theirs = peer.sync(self.net_frame)
                if theirs[0] == self.net_frame & M32 and theirs[0] != 0 and theirs[2] != value:
                    peer.oos = 1
                    self.log.append('out of sync %d' % slot)


def sync_hash(rand_seed, sync_acc, positions):
    """The hash of a sync record (tick tail, 0x13af44-0x13b01c): g_syncAcc + g_randSeed +
    for every player slot with an object the float x, y and height each converted to an
    integer toward zero (saturating), all summed modulo 2**32.  positions: one (x, y, z)
    tuple of float patterns per slot, None for an empty slot."""
    total = sync_acc + rand_seed
    for position in positions:
        if position is not None:
            for raw in position:
                total += Fpu.to_int(raw)
    return total & M32


# =======================================================================================
# 7. pad_apply
# =======================================================================================

PAD_SIZE = 0x58
STICK_SCALE = 0x3C000000        # 1/128
STICK_DEAD = 0x3EA3D70A         # just under 0.32, radial dead zone
STICK_GAIN = 0x3FBC3C3C         # just under 1/0.68
PRESSURE_SCALE = 0x3B808080     # just above 1/255
DIGITAL = 0x3F4CCCCC            # just under 0.8


class PadGlobals:
    """The three globals pad_apply reads: start_block 0x41bfc0 (while non-zero the start
    button 0x800 is removed and the counter decremented), mute 0x41c138 (non-zero: analog
    fields zeroed, buttons masked) and allow = word 0x41bfb8 | word 0x41bfbc (the buttons
    that survive a mute)."""

    def __init__(self, start_block=0, mute=0, allow=0):
        self.start_block, self.mute, self.allow = start_block, mute, allow


def decode_stick(x, y, fpu=DEFAULT_FPU):
    """pad_decodeStick 0x174ce0 (x byte, y byte) -> (fx, fy) patterns: centre at 128, scale
    1/128, radial dead zone 0.32, then (1 - 0.32 / length) * 1.4705882 applied to both."""
    fy = fpu.mul(fpu.from_int(y - 128), STICK_SCALE)
    fx = fpu.mul(fpu.from_int(x - 128), STICK_SCALE)
    length = fpu.sqrt(fpu.add(fpu.mul(fx, fx), fpu.mul(fy, fy)))
    if fpu.lt(length, STICK_DEAD):
        return 0, 0
    scale = fpu.mul(fpu.sub(F_ONE, fpu.div(STICK_DEAD, length)), STICK_GAIN)
    return fpu.mul(fx, scale), fpu.mul(fy, scale)


def pad_apply(pad, record, prev, glob=None, fpu=DEFAULT_FPU):
    """pad_apply 0x174410 (pad, record + 4, previous-state block).

    pad    bytearray of 0x58 bytes, changed in place.  Bytes +0x00..+0x07 and +0x24..+0x27
           are not written.
    record wire record (only its first 8 bytes are read)
    prev   [previous buttons word, repeat counter], changed in place

      +0x08 u32 buttons, plus 0x800000 / 0x400000 when the first stick's x is above 0.8 /
                below -0.8 and 0x200000 / 0x100000 for its y
      +0x0c u32 newly pressed: buttons & ~previous
      +0x10 u32 the same, replaced by all held buttons on every 4th call once the same
                non-zero word has been held for more than 20 calls (auto-repeat)
      +0x14 +0x18 floats: stick of record bytes +6, +7      +0x1c +0x20: record +8, +9
      +0x28 +0x2c +0x30 +0x34 floats 1.0 / 0.0 for buttons 0x2000, 0x8000, 0x1000, 0x4000
      +0x38 float record byte +0xa * (1/255)      +0x3c float (buttons & 1)
      +0x40 +0x44 +0x48 +0x4c floats for buttons 0x20, 0x80, 0x10, 0x40
      +0x50 float record byte +0xb * (1/255)      +0x54 float for button 0x2"""
    glob = glob or PadGlobals()
    buttons, s6, s7, s8, s9, p10, p11 = struct.unpack('<H6B', bytes(record[:8]))
    previous = prev[0]
    word = buttons
    if glob.start_block != 0:
        glob.start_block -= 1
        word &= 0xF7FF

    def flag(mask):
        return F_ONE if word & mask else 0
    floats = {0x28: flag(0x2000), 0x2C: flag(0x8000), 0x30: flag(0x1000), 0x34: flag(0x4000),
              0x40: flag(0x20), 0x44: flag(0x80), 0x48: flag(0x10), 0x4C: flag(0x40),
              0x38: fpu.mul(fpu.from_int(p10), PRESSURE_SCALE), 0x3C: fpu.from_int(word & 1),
              0x50: fpu.mul(fpu.from_int(p11), PRESSURE_SCALE), 0x54: flag(0x2)}
    floats[0x1C], floats[0x20] = decode_stick(s8, s9, fpu)
    floats[0x14], floats[0x18] = decode_stick(s6, s7, fpu)
    if fpu.lt(DIGITAL, floats[0x14]):
        word |= 0x800000
    if fpu.lt(floats[0x14], DIGITAL | SIGN):
        word |= 0x400000
    if fpu.lt(DIGITAL, floats[0x18]):
        word |= 0x200000
    if fpu.lt(floats[0x18], DIGITAL | SIGN):
        word |= 0x100000
    pressed = repeat = (word ^ previous) & word
    if word == 0 or word != prev[0]:
        prev[1] = 0
    else:
        prev[1] = (prev[1] + 1) & M32
        if s32(prev[1]) >= 0x15 and prev[1] & 3 == 0:
            repeat = word
    if glob.mute != 0:
        for offset in (0x28, 0x18, 0x14, 0x20, 0x1C, 0x54, 0x3C, 0x50, 0x38, 0x4C, 0x48, 0x44,
                       0x40, 0x34, 0x30, 0x2C):
            floats[offset] = 0
        pressed &= glob.allow
        word &= glob.allow
        repeat &= glob.allow
    struct.pack_into('<III', pad, 8, word, pressed, repeat)
    for offset, raw in floats.items():
        struct.pack_into('<I', pad, offset, raw)
    prev[0] = word
    return pad


# =======================================================================================
# 8. Launch handshake packets (separate socket, 0x134c60 / 0x135638)
# =======================================================================================

LAUNCH_TYPES = {0: 'SHAKE', 1: 'SHAKE ACK', 2: 'SIZE', 3: 'SIZE ACK', 4: 'DATA', 5: 'DATA ACK',
                6: 'KEEP ALIVE', 7: 'KEEP ALIVE ACK', 8: 'HOST FORCE LAUNCH'}
LAUNCH_SIZE = 0x200             # every launch packet except DATA is sent with this length
LAUNCH_INFO = 0xD0              # the info block carried by types 0, 1 and 7
LAUNCH_MIN = 16                 # shorter datagrams are ignored (length test after the
                                # recvfrom call in net_launchUpdate 0x135638)


def launch_checksum(chunk):
    """The 16-bit checksum of a DATA chunk (sender: net_launchSendData 0x1354f8; receiver:
    the DATA case of net_launchUpdate 0x135638).  Bytes are taken as signed.  Starting from 0x217, for byte i:
        even i:  subtract (byte & 0x8f37) * (i & 7)
        odd i:   add (byte * 3) ^ 0x30e15f
    and in both cases add the chunk's first byte.  Only the low 16 bits are used.  (The
    receiver's mask constant is 0x148f37; the two extra bits lie above bit 15 and cannot
    change the low 16 bits.)"""
    chunk = bytes(chunk)
    total = 0x217
    if not chunk:
        return total
    first = s8(chunk[0])
    for index, byte in enumerate(chunk):
        value = s8(byte)
        if index & 1 == 0:
            total -= (value & 0x8F37) * (index & 7)
        else:
            total += (value * 3) ^ 0x30E15F
        total += first
    return total & 0xFFFF


def launch_packet(player_id, kind, argument, payload=b'', size=LAUNCH_SIZE):
    """{u32 sender's player id, u32 type, u32 argument, payload}.  The original sends
    `size` bytes from a stack buffer it does not clear, so everything after the payload is
    undefined; the model pads with zeros (net_launchSendPacket 0x13e2c8)."""
    body = struct.pack('<III', player_id & M32, kind & M32, argument & M32) + bytes(payload)
    if size is not None:
        if len(body) > size:
            raise ValueError('payload does not fit')
        body += bytes(size - len(body))
    return body


def launch_data_packet(player_id, sequence, chunk):
    """DATA (type 4), net_launchSendData 0x1354f8: argument = checksum << 16 | sequence;
    length = 12 + chunk.  Returns (packet, argument)."""
    argument = ((launch_checksum(chunk) << 16) | sequence) & M32
    return launch_packet(player_id, 4, argument, chunk, size=None), argument


def parse_launch_packet(data):
    """(player id, type, argument, payload) or None for a datagram the handshake ignores
    (shorter than 16 bytes)."""
    data = bytes(data)
    if len(data) < LAUNCH_MIN:
        return None
    player_id, kind, argument = struct.unpack_from('<III', data)
    return player_id, kind, argument, data[12:]


def launch_data_ok(argument, chunk):
    """The receiver's test of a DATA packet: checksum of the chunk equals argument >> 16."""
    return launch_checksum(chunk) == (argument >> 16) & 0xFFFF
