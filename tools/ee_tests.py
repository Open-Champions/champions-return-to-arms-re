#!/usr/bin/env python3
"""ee_tests.py - execute specific claims and test patches in the function-level interpreter.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/ee_tests.py [path/to/SLUS_209.73] [-v] [-k TEXT]

    -v        also print the measurement tables
    -k TEXT   run only the groups whose letter or name contains TEXT

Every line is PASS or FAIL followed by a check id and one sentence.  PASS means the code,
executed in isolation on the state this script built, did what the sentence says; where
that differs from a document the sentence says so.  FAIL means the code did not do it:
the sentence (and whatever it was taken from) is wrong, or this script's set-up is.  SKIP
means a file the check needs (a patch section, a proposal table) is not there.

Nothing here shows that a state occurs in a real game: callees are stubbed, there is no
timing, no hardware and no second machine.  docs/issues/dynamic-tests.md explains each
group and maps it to the ledger.

Groups: a codec, b pad_apply, c object pool, d pacing block and patches, e alive list /
death path / Player_clone and their patches, f cut_advance and its patch, g sync record,
h sign-in state machine, i other ledger rows, j diagnostic patches, p patch file,
x cross-check of the interpreter on library routines.
"""
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu
from ee_emu import EE, EmuError, M32, float_to_raw, raw_to_float

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNACH = os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach')
PREDICTION_DOC = os.path.join(ROOT, 'docs', 'issues', 'prediction-copy.md')
LOCAL_SIGNIN_PNACH = os.path.join(ROOT, 'local', 'SLUS-20973_4028A55F_signin.pnach')

VERBOSE = False
RESULTS = []


def check(ident, ok, text):
    RESULTS.append((ident, bool(ok)))
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    return bool(ok)


def skip(ident, text):
    print('SKIP  %-4s %s' % (ident, text))


def pnach_section_at(addr, path=None):
    """(title, [(address, word), ...]) of the patch-file section that patches addr, or
    None.  Sections are found by address because their titles change."""
    path = PNACH if path is None else path
    if not os.path.isfile(path):
        return None
    for title, entries in ee_emu.parse_pnach(path):
        if any(a == addr for a, _size, _value in entries):
            return title, [(a, value) for a, size, value in entries if size == 4]
    return None


def apply_section_at(emu, addr):
    """Apply the patch-file section that patches addr; returns its title or None."""
    found = pnach_section_at(addr)
    if found is None:
        return None
    for address, word in found[1]:
        emu.patch(address, word)
    return found[0]


def pnach_was_words(path):
    """{section title: [words quoted after "was:" in its comment]} for the checks that the
    quoted original instruction is really what the executable holds."""
    import re
    out, title = {}, None
    with open(path, encoding='utf-8-sig') as source:
        for line in source:
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                title = line[1:-1]
            elif line.startswith('//') and 'was:' in line and title is not None:
                text = line.split('was:', 1)[1].split('now:')[0]
                out[title] = [int(w, 16) for w in re.findall(r'\b[0-9A-Fa-f]{8}\b', text)]
    return out


def proposal_rows(path):
    """Patch proposals in a document: rows "| id | 0xADDRESS | ORIGINAL | NEW |" and the
    three-column routine tables "| 0xADDRESS | ORIGINAL | NEW |".  Returns
    [(id or None, address, original, new)]."""
    import re
    rows = []
    if not os.path.isfile(path):
        return rows
    with_id = re.compile(r'^\|\s*([A-Za-z][\w-]*)\s*\|\s*0x([0-9A-Fa-f]{8})\s*\|\s*([0-9A-Fa-f]{8})\s*\|\s*([0-9A-Fa-f]{8})\s*\|')
    plain = re.compile(r'^\|\s*0x([0-9A-Fa-f]{8})\s*\|\s*([0-9A-Fa-f]{8})\s*\|\s*([0-9A-Fa-f]{8})\s*\|\s*$')
    with open(path, encoding='utf-8-sig') as source:
        for line in source:
            match = with_id.match(line)
            if match:
                rows.append((match.group(1), int(match.group(2), 16), int(match.group(3), 16), int(match.group(4), 16)))
                continue
            match = plain.match(line.rstrip())
            if match:
                rows.append((None, int(match.group(1), 16), int(match.group(2), 16), int(match.group(3), 16)))
    return rows


def table(title, rows):
    if VERBOSE:
        print('      -- %s' % title)
        for row in rows:
            print('         ' + row)


def s32(value):
    return ee_emu.s32(value)


# ---------------------------------------------------------------------------------------
# a. The stick codec: netcodec_encodeAxis 0x13c450, netcodec_decodeAxis 0x13c970
# ---------------------------------------------------------------------------------------
ENCODE_AXIS, DECODE_AXIS = 0x13C450, 0x13C970
STEP_TABLE = (4, 6, 8, 12, 16, 24, 32, 48, 64)      # as listed in docs/netcode.md


class AxisCodec:
    """One encoder channel and one decoder channel driven through the game's functions."""

    def __init__(self, elf, fpu_model='ps2', mul_bias=False, div_nearest=False):
        emu = self.emu = EE(elf, fpu_model=fpu_model)
        emu.fpu_mul_bias = mul_bias
        emu.fpu_div_nearest = div_nearest
        emu.follow = set()                  # neither function is expected to call anything
        self.enc, self.dec = self.channel(), self.channel()
        self.stream = emu.alloc(0x400)
        self.writer, self.reader = emu.alloc(8), emu.alloc(8)
        self.samples, self.out = emu.alloc(0x100), emu.alloc(0x100)
        self.bits = 0
        self.bit_mismatches = 0             # frames where the decoder read a different bit count

    def channel(self):
        """Reset state: step index 0, predictor 0, smoothed 128.0, velocity 0."""
        addr = self.emu.alloc(16)
        self.emu.mem.wf32(addr + 8, 128.0)
        return addr

    def state(self, addr):
        mem = self.emu.mem
        return mem.s32(addr), mem.s32(addr + 4), mem.u32(addr + 8), mem.u32(addr + 12)

    def encode(self, values):
        emu, mem = self.emu, self.emu.mem
        mem.write(self.stream, bytes(0x400))
        mem.w32(self.writer, self.stream)
        mem.w32(self.writer + 4, 0)
        mem.write(self.samples, bytes(values))
        emu.call(ENCODE_AXIS, 0, self.writer, self.enc, self.samples, len(values))
        self.bits = mem.u32(self.writer + 4)

    def decode(self, count, skip=0):
        emu, mem = self.emu, self.emu.mem
        mem.w32(self.reader, self.stream)
        mem.w32(self.reader + 4, 0)
        mem.write(self.out, bytes([0xEE]) * 0x100)
        emu.call(DECODE_AXIS, 0, self.reader, self.dec, self.out, count - skip, skip)
        return list(mem.read(self.out, count - skip)), mem.u32(self.reader + 4)

    def frame(self, value):
        self.encode([value])
        out, used = self.decode(1)
        if used != self.bits:
            self.bit_mismatches += 1
        return out[0]


def model_predictor(index, pred, sample):
    """The adaptive delta coder as docs/netcode.md describes it."""
    step = STEP_TABLE[index]
    diff = sample - pred
    if abs(diff) >= step:
        pred = max(0, min(255, pred + (step if diff > 0 else -step)))
        index = min(8, index + 2)
    else:
        index = max(0, index - 1)
    return index, pred


SPRING_GAIN = 0x3D4CCCCC            # the constant in the decoder, just below 0.05
SPRING_SQUARE = 0x3E4CCCCC          # just below 0.2; the damping factor is 1 - sqrt(this)


def spring_damping(model='ps2', div_nearest=False):
    """The decoder computes its damping factor at run time: 1 - sqrt(0.2)."""
    return ee_emu.fp_sub(float_to_raw(1.0), ee_emu.fp_sqrt(SPRING_SQUARE, model, None, div_nearest), model)


def model_spring(value, velocity, target, value_first, model='ps2'):
    """Ten spring steps in R5900 single precision.  value_first selects the order in
    which the two state variables are updated; returns (byte, value, velocity)."""
    k1, k2 = SPRING_GAIN, spring_damping(model)
    target = ee_emu.fp_from_int(target)
    for _ in range(10):
        if value_first:
            value = ee_emu.fp_add(value, velocity, model)
            delta = ee_emu.fp_sub(target, value, model)
            velocity = ee_emu.fp_mul(ee_emu.fp_add(velocity, ee_emu.fp_mul(delta, k1, model), model), k2, model)
        else:
            delta = ee_emu.fp_sub(target, value, model)
            velocity = ee_emu.fp_mul(ee_emu.fp_add(velocity, ee_emu.fp_mul(delta, k1, model), model), k2, model)
            value = ee_emu.fp_add(value, velocity, model)
    byte = max(0, min(255, s32(ee_emu.fp_to_int(value))))
    return byte, value, velocity


def stick_sequences(seed=20973, frames=600):
    """Deterministic test input: flicks, holds, slow sweeps, noise."""
    rng = random.Random(seed)
    seq = []
    while len(seq) < frames:
        kind = rng.randrange(4)
        if kind == 0:                                   # hold a value
            seq += [rng.randrange(256)] * rng.randrange(1, 45)
        elif kind == 1:                                 # slow sweep
            a, b, n = rng.randrange(256), rng.randrange(256), rng.randrange(5, 40)
            seq += [a + (b - a) * i // n for i in range(n)]
        elif kind == 2:                                 # jitter around a value
            c = rng.randrange(8, 248)
            seq += [c + rng.randrange(-7, 8) for _ in range(rng.randrange(5, 30))]
        else:                                           # noise
            seq += [rng.randrange(256) for _ in range(rng.randrange(1, 12))]
    return seq[:frames]


def test_codec(elf):
    # a1 / a2: the two sequences quoted in docs/netcode.md
    codec = AxisCodec(elf)
    start = [codec.frame(128) for _ in range(40)]
    check('a1', start[:6] == [77, 43, 34, 44, 78, 101],
          'from the reset state a centred stick (128) decodes as %s, as docs/netcode.md says; '
          'first frame within 4 of centre is frame %d, it settles at %d'
          % (start[:6], next(i for i, v in enumerate(start) if abs(v - 128) <= 4) + 1, start[-1]))
    push = [codec.frame(255) for _ in range(30)]
    check('a2', push[:8] == [129, 134, 143, 162, 201, 227, 239, 245],
          'after settling, a full push (255) decodes as %s on the next 8 frames, as '
          'docs/netcode.md says' % push[:8])
    check('a3', push[-1] == 251 and codec.state(codec.enc)[1] == 252,
          'a held 255 settles at %d (predictor %d), never 255: the remaining distance is '
          'below the smallest step' % (push[-1], codec.state(codec.enc)[1]))
    pull = AxisCodec(elf)
    for _ in range(40):
        pull.frame(128)
    low = [pull.frame(0) for _ in range(30)]
    check('a4', low[-1] == 0, 'a held 0 does reach %d (sequence %s ...): the limit in a3 is one-sided'
          % (low[-1], low[:8]))
    table('centre from reset', [' '.join('%3d' % v for v in start[:20])])
    table('128 -> 255', [' '.join('%3d' % v for v in push[:14])])
    table('128 -> 0', [' '.join('%3d' % v for v in low[:14])])

    # a5: predictor round trip and the documented coder, frame by frame
    seq = stick_sequences()
    codec = AxisCodec(elf)
    index = pred = 0
    value, velocity = float_to_raw(128.0), 0
    doc_value, doc_velocity = float_to_raw(128.0), 0
    state_ok = model_ok = True
    bytes_code_order = bytes_doc_order = 0
    seen_indexes = set()
    decoded = []
    for sample in seq:
        seen_indexes.add(index)
        index, pred = model_predictor(index, pred, sample)
        got = codec.frame(sample)
        decoded.append(got)
        enc_state, dec_state = codec.state(codec.enc), codec.state(codec.dec)
        state_ok &= enc_state[:2] == dec_state[:2]
        model_ok &= enc_state[:2] == (index, pred)
        byte, value, velocity = model_spring(value, velocity, pred, True)
        bytes_code_order += byte != got
        byte, doc_value, doc_velocity = model_spring(doc_value, doc_velocity, pred, False)
        bytes_doc_order += byte != got
    check('a5', state_ok and codec.bit_mismatches == 0, 'over %d frames of mixed stick input the decoder\'s step index and '
          'predictor equal the encoder\'s after every frame, and it reads exactly the bits written'
          % len(seq))
    check('a6', model_ok and seen_indexes == set(range(9)),
          'the predictor follows the rule in docs/netcode.md (steps 4..64, index +2 after a move, '
          '-1 otherwise, clamped) on every frame; all 9 step indexes were exercised')
    seen_damping = []
    probe = AxisCodec(elf)
    probe.emu.hook(0x13CD68, lambda e: seen_damping.append(e.f[4]))     # just after 1 - sqrt(...)
    probe.frame(128)
    check('a7', bytes_code_order == 0 and seen_damping == [spring_damping()],
          'the decoded byte equals ten spring steps toward the predictor, truncated and clamped, '
          'when each step adds the old velocity to the value first and then updates the velocity '
          '(%d mismatches in %d frames); gain %.9f, damping 1 - sqrt(0.2) computed at run time = '
          '%.9f' % (bytes_code_order, len(seq), raw_to_float(SPRING_GAIN), raw_to_float(spring_damping())))
    check('a8', bytes_doc_order > 0,
          'updating the velocity before the value, which is how the formula in docs/netcode.md is '
          'written, does not reproduce the decoder: %d of %d bytes differ (the numbers quoted '
          'there are right, the order in the formula is not)' % (bytes_doc_order, len(seq)))
    worst = max(abs(d - s) for d, s in zip(decoded, seq))
    table('codec error', ['largest |decoded - raw| on the same frame over the sequence: %d' % worst])

    # a9: packets of several frames; the receiver may already hold the first k of them
    packet_ok = True
    cases = 0
    for size, skip in ((1, 0), (2, 0), (5, 2), (7, 0), (31, 0), (32, 5), (40, 39), (64, 10), (90, 0)):
        a, b = AxisCodec(elf), AxisCodec(elf)
        rng = random.Random(size * 100 + skip)
        for v in [rng.randrange(256) for _ in range(10)]:
            a.frame(v)
            b.frame(v)
        for kind in range(3):
            if kind == 0:
                values = [rng.randrange(256) for _ in range(size)]
            elif kind == 1:
                values = [200] * size                    # long runs: the 31-run escape
            else:
                values = [(i * 37) % 256 for i in range(size)]
            single = [a.frame(v) for v in values]
            # The sender's state stays at the last acknowledged frame, so an earlier packet
            # with the first `skip` frames and this one start from the same encoder state.
            saved = b.emu.mem.read(b.enc, 16)
            if skip:
                b.encode(values[:skip])
                held, _ = b.decode(skip)
                packet_ok &= held == single[:skip]
                b.emu.mem.write(b.enc, saved)
            b.encode(values)
            new, used = b.decode(size, skip)
            packet_ok &= new == single[skip:] and used == b.bits
            packet_ok &= b.state(b.dec) == a.state(a.dec) and b.state(b.enc)[:2] == a.state(a.enc)[:2]
            cases += 1
    check('a9', packet_ok, 'a packet of n frames decoded with the first k skipped gives the same '
          'bytes and state as frame-by-frame coding (%d packets, n up to 90, including runs '
          'longer than 31)' % cases)

    # a10-a12: how much depends on the floating-point model
    def run(model, bias=False, div_nearest=False):
        c = AxisCodec(elf, fpu_model=model, mul_bias=bias, div_nearest=div_nearest)
        return [c.frame(v) for v in seq]

    def quoted(model):
        c = AxisCodec(elf, fpu_model=model)
        return [c.frame(128) for _ in range(40)] + [c.frame(255) for _ in range(30)]
    reference = quoted('ps2')
    check('a10', all(quoted(m) == reference for m in ('ps2g1', 'chop', 'nearest')),
          'the sequences in a1-a3 come out the same under all four floating-point models of the '
          'interpreter')
    one_guard, chop, nearest, biased = run('ps2g1'), run('chop'), run('nearest'), run('ps2', True)
    by_rounding = [(x, y) for x, y in zip(chop, nearest) if x != y]
    check('a11', len(by_rounding) > 0 and all(abs(x - y) == 1 for x, y in by_rounding),
          'the same %d input frames decode differently on %d frames (always by 1) when sums are '
          'rounded to nearest instead of truncated: two machines whose floating point differs '
          'would feed different stick bytes into the simulation (docs/netcode.md, per-machine '
          'row 11)' % (len(seq), len(by_rounding)))
    by_adder = [(x, y) for x, y in zip(decoded, chop) if x != y]
    by_guard = sum(1 for x, y in zip(decoded, one_guard) if x != y)
    by_bias = sum(1 for x, y in zip(decoded, biased) if x != y)
    by_sqrt = sum(1 for x, y in zip(decoded, run('ps2', div_nearest=True)) if x != y)
    check('a12', all(abs(x - y) == 1 for x, y in by_adder) and by_bias == 0 and by_guard == 0 and by_sqrt == 0,
          'limit of this interpreter: its two console-style adders agree on every frame (%d '
          'differ), but both differ from a plain truncated sum on %d of %d frames, always by 1 '
          '(a value resting exactly on an integer); biasing every inexact product changes %d '
          'frames, rounding the square root to nearest %d'
          % (by_guard, len(by_adder), len(seq), by_bias, by_sqrt))
    return decoded


# ---------------------------------------------------------------------------------------
# b. pad_apply 0x174410 (FINDINGS G5) and the slew measured through it (FINDINGS L6)
# ---------------------------------------------------------------------------------------
PAD_APPLY = 0x174410
PAD_SIZE = 0x58
G_PAD_START_MASK, G_PAD_MUTE = 0x41BFC0, 0x41C138


class PadRig:
    def __init__(self, elf, fill=0x00):
        self.emu = EE(elf)
        self.pad = self.emu.alloc(PAD_SIZE, fill=fill) if fill else self.emu.alloc(PAD_SIZE)
        self.record = self.emu.alloc(24)
        self.prev = self.emu.alloc(8)

    def apply(self, buttons=0, lx=128, ly=128, rx=128, ry=128, p1=0, p2=0):
        """record +4 buttons, +6/+7 one stick pair, +8/+9 the other, +0xa/+0xb pressure."""
        mem = self.emu.mem
        mem.w16(self.record + 4, buttons)
        mem.write(self.record + 6, bytes([lx, ly, rx, ry, p1, p2]))
        self.emu.reset_log()
        self.emu.call(PAD_APPLY, self.pad, self.record + 4, self.prev)
        return self.emu.mem.read(self.pad, PAD_SIZE)

    def f(self, offset):
        return self.emu.mem.f32(self.pad + offset)

    def u(self, offset):
        return self.emu.mem.u32(self.pad + offset)


def test_pad_apply(elf):
    rig = PadRig(elf, fill=0xEE)
    rig.apply(buttons=0x20F3, lx=200, ly=40, rx=90, ry=250, p1=0x33, p2=0xCC)
    written = set()
    outside = []
    for _pc, addr, size, _value in rig.emu.writes:
        if rig.pad <= addr < rig.pad + PAD_SIZE:
            written.update(range(addr - rig.pad, addr - rig.pad + size))
        elif not rig.prev <= addr < rig.prev + 8:
            outside.append(addr)
    missing = sorted(set(range(PAD_SIZE)) - written)
    spans = []
    for off in missing:
        if spans and spans[-1][1] == off - 1:
            spans[-1][1] = off
        else:
            spans.append([off, off])
    span_text = ', '.join('+0x%02x..+0x%02x' % (a, b) for a, b in spans)
    check('b1', missing == list(range(0, 8)) + list(range(0x24, 0x28)),
          'one call stores every byte of the 0x58-byte pad except %s; so "every pad field" in '
          'FINDINGS G5 holds for +0x08..+0x57 less the word at +0x24' % span_text)
    probe = PadRig(elf)
    probe.emu.reads = []
    probe.apply(buttons=0x20F3, lx=200, ly=40, rx=90, ry=250, p1=0x33, p2=0xCC)
    globals_read = sorted({addr for _pc, addr, _n, _v in probe.emu.reads if addr < 0x01000000})
    check('b2', not outside and globals_read == [G_PAD_START_MASK, G_PAD_MUTE],
          'as shipped it writes nothing outside the pad and its 8-byte previous-state block, and '
          'the only globals it reads are the two G5 names, 0x41bfc0 and 0x41c138 (both 0 in the '
          'executable)')

    clean, dirty = PadRig(elf), PadRig(elf, fill=0xA5)
    same = True
    rng = random.Random(5)
    for _ in range(60):
        args = dict(buttons=rng.randrange(0x10000), lx=rng.randrange(256), ly=rng.randrange(256),
                    rx=rng.randrange(256), ry=rng.randrange(256), p1=rng.randrange(256),
                    p2=rng.randrange(256))
        a, b = clean.apply(**args), dirty.apply(**args)
        same &= a[8:0x24] == b[8:0x24] and a[0x28:] == b[0x28:]
    check('b3', same, 'two pads that started with different stale contents are byte-identical '
          'in the stored range after the same 60 records: no stale pad state survives a call (G5)')

    rig = PadRig(elf)
    rig.apply(p1=0x33, p2=0xCC)
    check('b4', abs(rig.f(0x38) - 0x33 / 255) < 1e-6 and abs(rig.f(0x50) - 0xCC / 255) < 1e-6,
          'record bytes +0xa/+0xb reach pad +0x38/+0x50 as byte/255 (%.4f, %.4f): the two bytes '
          'docs/netcode.md says are not transmitted do land in the lockstep pad'
          % (rig.f(0x38), rig.f(0x50)))

    rig = PadRig(elf)
    rig.emu.mem.w32(G_PAD_START_MASK, 2)
    rig.apply(buttons=0x0840)
    masked = rig.u(8)
    counter = rig.emu.mem.u32(G_PAD_START_MASK)
    check('b5', masked == 0x0040 and counter == 1,
          'with 0x41bfc0 forced non-zero the function itself decrements it (2 -> %d) and drops '
          'button 0x800; G5\'s "never written anywhere" is true only while it stays 0, which is '
          'its value in the executable' % counter)
    rig = PadRig(elf)
    rig.emu.mem.w32(G_PAD_MUTE, 1)
    rig.apply(buttons=0xFFFF, lx=255, ly=255, rx=0, ry=0, p1=255, p2=255)
    check('b6', all(rig.u(o) == 0 for o in (0x14, 0x18, 0x1C, 0x20, 0x28, 0x2C, 0x30, 0x34, 0x38)),
          'with 0x41c138 forced non-zero the sticks and analog button fields are zeroed and the '
          'buttons masked to 0x%x: the second global G5 names really gates the output'
          % rig.u(8))

    # thresholds of the digital direction flags, by sweeping one axis
    def flags_for(value):
        r = PadRig(elf)
        r.apply(lx=value)
        return r.u(8), r.f(0x14)
    first_pos = next(v for v in range(128, 256) if flags_for(v)[0] & 0x800000)
    last_neg = next(v for v in range(127, -1, -1) if flags_for(v)[0] & 0x400000)
    first_move = next(v for v in range(128, 256) if flags_for(v)[1] != 0.0)
    check('b7', (first_pos, last_neg, first_move) == (239, 17, 169),
          'on one axis the stick leaves the dead zone at byte %d and sets a digital-direction '
          'flag at %d and above, or %d and below' % (first_move, first_pos, last_neg))

    # L6: the measured push sequence through the real pad_apply
    codec = AxisCodec(elf)
    for _ in range(40):
        codec.frame(128)
    rows, first_nonzero, first_flag, final = [], None, None, 0.0
    rig = PadRig(elf)
    for frame in range(1, 16):
        byte = codec.frame(255)
        rig.apply(lx=byte)
        amount, flag = rig.f(0x14), bool(rig.u(8) & 0x800000)
        rows.append('frame %2d  byte %3d  movement %.3f%s' % (frame, byte, amount, '  digital' if flag else ''))
        if first_nonzero is None and amount != 0.0:
            first_nonzero = frame
        if first_flag is None and flag:
            first_flag = frame
        final = amount
    table('full push through codec and pad_apply', rows)
    offline = PadRig(elf)
    offline.apply(lx=255)
    check('b8', first_nonzero == 5 and first_flag == 7,
          'after a full push the simulation sees no movement for 4 frames, movement from frame '
          '%d and the digital-direction flag from frame %d: the numbers of FINDINGS L6, here '
          'executed rather than modelled' % (first_nonzero, first_flag))
    other_way = AxisCodec(elf)
    for _ in range(40):
        other_way.frame(128)
    for _ in range(60):
        low_byte = other_way.frame(0)
    low = PadRig(elf)
    low.apply(lx=low_byte)
    check('b9', abs(final - 0.943) < 0.002 and abs(offline.f(0x14) - 0.989) < 0.002
          and abs(low.f(0x14) + 1.0) < 0.002,
          'a held full push toward 255 ends at %.3f through the codec against %.3f for the raw '
          'byte offline, while a held push toward 0 ends at %.3f: in a net game the stick is not '
          'symmetric (a3, a4); whether anything downstream cares was not traced'
          % (final, offline.f(0x14), low.f(0x14)))

    # the stick table of docs/issues/lag.md section 8 (a model there), executed here
    def movement(before, after, frames=10, words=None):
        c, r = AxisCodec(elf), PadRig(elf)
        for addr, word in (words or {}).items():
            c.emu.patch(addr, word)
        for value in before:
            c.frame(value)
        out = []
        for value in (list(after) + [after[-1]] * frames)[:frames]:
            r.apply(lx=c.frame(value))
            out.append(round(r.f(0x14), 2))
        return out
    rest, held = [128] * 40, [128] * 40 + [255] * 40
    rows_lag = {
        'full push': (movement(rest, [255]), [0, 0, 0, 0, 0.37, 0.67, 0.80, 0.87, 0.91, 0.93]),
        'release after a long push': (movement(held, [128]), [0.93, 0.87, 0.77, 0.55, 0.10, 0, 0, 0, 0, 0]),
        'reversal': (movement(held, [0]), [0.93, 0.87, 0.77, 0.55, 0.10, 0, -0.21, -0.61, -0.82, -0.91]),
        'push held 3 frames': (movement(rest, [255] * 3 + [128]), [0] * 10),
        'push held 5 frames': (movement(rest, [255] * 5 + [128]), [0, 0, 0, 0, 0.37, 0.36, 0.29, 0.02, 0, 0]),
    }
    table('stick value the game reads, frame by frame', ['%-26s %s' % (k, v[0]) for k, v in rows_lag.items()])
    check('b10', all(got == want for got, want in rows_lag.values()),
          'the five rows of the stick table in docs/issues/lag.md section 8 (a model there) come '
          'out identically when the game\'s encoder, decoder and pad_apply are executed: e.g. a '
          'push held for 3 frames never moves the character, a release keeps it moving 5 frames')
    longer = movement(rest, [255], words={0x13CD34: 0x24060013})
    first_move = next(i for i, v in enumerate(longer) if v) + 1
    first_digital = next(i for i, v in enumerate(longer) if v > 0.8) + 1
    check('b11', (first_move, first_digital) == (4, 6) and longer[:6] == [0, 0, 0, 0.09, 0.70, 0.89],
          'lag.md\'s remark on the spring\'s pass count (0x13cd34, 10 -> 20; not a proposed patch) '
          'executed: first movement on frame %d and the digital direction on frame %d, one frame '
          'earlier each, but the values are %s, not the shipped row shifted by one'
          % (first_move, first_digital, longer[:6]))

    # the stick conversion uses a square root and a division: does their rounding matter?
    def sweep(div_nearest, model):
        out = []
        for value in range(0, 256, 3):
            r = PadRig(elf)
            r.emu.fpu_model = model
            r.emu.fpu_div_nearest = div_nearest
            r.apply(lx=value, ly=255 - value, rx=value, ry=40)
            out.append((r.u(8), int(r.f(0x14) * 4096), int(r.f(0x18) * 4096), int(r.f(0x1C) * 4096)))
        return out
    base = sweep(False, 'ps2')
    check('b12', all(sweep(d, m) == base for d in (False, True) for m in ('ps2', 'ps2g1', 'chop', 'nearest')),
          'pad_apply gives the same buttons and the same stick values to 12 bits for 86 stick '
          'positions under every floating-point model and with division rounded either way: '
          'b7-b11 do not depend on the interpreter\'s approximations')


# ---------------------------------------------------------------------------------------
# c. pool_new 0x14fdb8, pool_free 0x150470 (FINDINGS D21)
# ---------------------------------------------------------------------------------------
POOL_INIT, POOL_NEW, POOL_FREE, POOL_COUNT_FREE = 0x14FCD8, 0x14FDB8, 0x150470, 0x150410
POOL_PRINT_HEAP = 0x150290
POOL_BASE = 0x5F88C0
POOL_CLASSES = ((0x180, 512), (0x500, 512), (3000, 32))


def pool_class_of(addr):
    base = POOL_BASE
    for index, (size, count) in enumerate(POOL_CLASSES):
        if base <= addr < base + size * count:
            return index
        base += size * count
    return None


def test_pool(elf):
    emu = EE(elf)
    printed = []
    emu.stub(POOL_PRINT_HEAP, function=lambda e: printed.append(1), name='pool_printHeap')
    emu.call(POOL_INIT)
    free0 = s32(emu.call(POOL_COUNT_FREE))
    check('c1', free0 == 1056, 'after pool_init, pool_countFree walks %d free blocks '
          '(512 + 512 + 32)' % free0)

    block = emu.call(POOL_NEW, 0x100) & M32
    emu.mem.write(block, b'\xAA' * 0x180)
    emu.call(POOL_FREE, block)
    again = emu.call(POOL_NEW, 0x100) & M32
    check('c2', again == block and emu.mem.read(block, 0x180) == bytes(0x180),
          'a freed block is handed out again first and comes back zero-filled over its whole '
          'class size (0x180 bytes)')
    emu.call(POOL_FREE, block)

    small = [emu.call(POOL_NEW, 0x148) & M32 for _ in range(512)]
    check('c3', all(pool_class_of(a) == 0 for a in small) and len(set(small)) == 512,
          '512 requests of 0x148 bytes are all served from the 0x180 class')
    spill = emu.call(POOL_NEW, 0x148) & M32
    check('c4', pool_class_of(spill) == 1 and not printed,
          'the 513th request of 0x148 bytes is served from the 0x500 class: a full class spills '
          'into the next larger one (D21)')
    emu.call(POOL_FREE, spill)
    back = emu.call(POOL_NEW, 0x400) & M32
    check('c5', back == spill, 'pool_free puts a spilled block back on the list of the class its '
          'address lies in, not the class of the size that was asked for')
    medium = [emu.call(POOL_NEW, 0x148) & M32 for _ in range(511)]
    big = [emu.call(POOL_NEW, 0x148) & M32 for _ in range(32)]
    check('c6', all(pool_class_of(a) == 1 for a in medium) and all(pool_class_of(a) == 2 for a in big),
          'with both smaller classes full, 0x148-byte requests take the 32 blocks of the '
          '3000-byte class')
    left = s32(emu.call(POOL_COUNT_FREE))
    calls_before = len(printed)
    nothing = emu.call(POOL_NEW, 0x148)
    check('c7', left == 0 and nothing == 0 and len(printed) == calls_before + 1,
          'with every class full pool_new returns 0 after calling the heap-print routine once (D21)')
    emu.call(POOL_FREE, big[5])
    too_big = emu.call(POOL_NEW, 3001)
    fits = emu.call(POOL_NEW, 3000) & M32
    check('c8', too_big == 0 and fits == big[5],
          'a request above 3000 bytes returns 0 even when a block is free; 3000 itself is served')
    writes = [a for _pc, a, _n, _v in emu.writes
              if not (POOL_BASE <= a < POOL_BASE + 0xE7700) and not (0x403A10 <= a < 0x403A50)]
    others = sorted(set(writes))
    check('c9', others == [0x4D8A24],
          'apart from the pool memory and its class table the allocator writes one global, '
          '0x4d8a24 (the last block handed out): %s' % ', '.join('0x%x' % a for a in others))



# ---------------------------------------------------------------------------------------
# d. The pacing block of net_main, 0x13354c-0x133608, and the send cycle
#    (docs/netcode.md "Pacing and lag", docs/issues/lag.md, FINDINGS L3 and L4)
# ---------------------------------------------------------------------------------------
PACING_START, PACING_HELD, PACING_SAMPLE = 0x13354C, 0x1336BC, 0x133610
MINREADY_START, MINREADY_END, ENGINE_FRAME_STEP = 0x13437C, 0x1343A8, 0x19E3A8
G_LOCAL_INPUT_FRAME, G_EXCESS_CALLS, G_MIN_READY, G_TRIM_WINDOW = 0x4027A4, 0x4027DC, 0x4027E0, 0x4027E4
# The four compare instructions of the block: address -> (original word, what the constant is)
PACING_COMPARES = {0x133554: (0x28420027, 'cap'), 0x133574: (0x2862001F, 'equalise calls'),
                   0x1335C0: (0x2863003D, 'trim window'), 0x1335E4: (0x28420003, 'trim ready count')}
# The two pacing patches that were in the patch file when this script was first written;
# docs/issues/lag.md replaced them.  Kept so that their effect stays on record.
WITHDRAWN_PACING = (('input delay drains faster', {0x133574: 0x28620008, 0x1335C0: 0x2863000B}),
                    ('lower input delay cap', {0x133554: 0x2842000F}))
LAG_DOC = os.path.join(ROOT, 'docs', 'issues', 'lag.md')
SEND_CYCLE_START, SEND_CYCLE_END = 0x133760, 0x1337EC
SEND_TURN_START, SEND_TURN_YES, SEND_TURN_NO = 0x133834, 0x133870, 0x133860
SEND_PHASE_START, SEND_PHASE_END = 0x1341E0, 0x134208
G_SEND_CYCLE_TABLE, G_SEND_CYCLE, G_SEND_PHASE, G_UART_MODEM = 0x4027E8, 0x4027B0, 0x4027B4, 0x4027B8


class Pacing:
    """Runs the hold decision of net_main as a stretch: registers and the caller's frame
    are prepared the way the preceding code leaves them, the counters live in the game's
    own globals and carry over from call to call."""

    def __init__(self, elf, words=None):
        emu = self.emu = EE(elf)
        for addr, word in (words or {}).items():
            emu.patch(addr, word)
        emu.stub(ENGINE_FRAME_STEP, ret=1, name='engine_frameStep')
        self.fp = emu.alloc(0x2600)
        self.other_writes = set()
        emu.mem.w32(G_MIN_READY, 100)          # the value a window end leaves

    def constants(self):
        """The four constants as they stand in (possibly patched) memory."""
        return {name: self.emu.mem.u32(addr) & 0xFFFF for addr, (_w, name) in PACING_COMPARES.items()}

    def hold(self, local_input, lowest_sim, excess, caller_hold=0):
        emu, mem, fp = self.emu, self.emu.mem, self.fp
        mem.w32(G_LOCAL_INPUT_FRAME, local_input)
        mem.w32(fp + 0x2430, caller_hold)
        mem.w32(fp + 0x243C, 0x5A5A5A5A)
        emu.r[2] = local_input & M32
        emu.r[3] = lowest_sim & M32
        emu.r[17] = excess & ee_emu.M64
        emu.r[30] = fp
        emu.reset_log()
        emu.run(start=PACING_START, until={PACING_HELD, PACING_SAMPLE}, max_steps=200)
        held = emu.pc == PACING_HELD
        if bool(mem.u32(fp + 0x243C)) != held:
            raise AssertionError('hold flag and branch disagree')
        for _pc, addr, _size, _value in emu.writes:
            if addr not in (G_EXCESS_CALLS, G_MIN_READY, G_TRIM_WINDOW, fp + 0x243C):
                self.other_writes.add(addr)
        return held

    def note_ready(self, ready):
        """The stretch after the ready scan that folds this call's count into the window
        minimum (0x13437c-0x1343a4)."""
        emu, mem, fp = self.emu, self.emu.mem, self.fp
        mem.w32(fp + 0x13D0, ready)
        mem.w32(fp + 0x2464, fp + 0x13D0)
        emu.r[30] = fp
        emu.run(start=MINREADY_START, until={MINREADY_END}, max_steps=200)

    def held_calls(self, calls, excess=0, ready=0, lead=10, caller_hold=0):
        out = []
        for number in range(1, calls + 1):
            if self.hold(1000 + lead, 1000, excess(number) if callable(excess) else excess, caller_hold):
                out.append(number)
            self.note_ready(ready(number) if callable(ready) else ready)
        return out


def pacing_battery(elf, words):
    """Measure the three rules with the given words patched in, and say whether each
    behaves as the constant now in memory implies.  Returns (ok, constants, text)."""
    rig = Pacing(elf, words)
    consts = rig.constants()
    cap = []
    for lead in range(2, 70):
        rig.emu.mem.w32(G_TRIM_WINDOW, 0)           # keep the other two rules out of the sweep
        rig.emu.mem.w32(G_EXCESS_CALLS, 0)
        if rig.hold(1000 + lead, 1000, 0):
            cap.append(lead)
    equalise = Pacing(elf, words).held_calls(200, excess=5)
    below = Pacing(elf, words).held_calls(200, excess=4)
    need = consts['trim ready count']
    trim = Pacing(elf, words).held_calls(200, ready=need)
    short = Pacing(elf, words).held_calls(200, ready=need - 1)
    every = max(consts['equalise calls'], 1)
    window = consts['trim window'] + 1
    ok = (cap == list(range(consts['cap'], 70))
          and equalise == list(range(every, 201, every)) and below == []
          and trim == list(range(window, 201, window)) and short == [])
    text = ('held from a lead of %d; %s while 5 or more above the smallest lead; '
            'every %s call when all calls of the window had %d or more frames ready'
            % (cap[0] if cap else -1, 'every call' if every == 1 else 'every %s call' % ordinal(every),
               ordinal(window), need))
    return ok, consts, text


def ordinal(number):
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return '%d%s' % (number, suffix)


def constant_only(words):
    """True when every word changes only the 16-bit constant of one of the four compares."""
    return all(addr in PACING_COMPARES and (word ^ PACING_COMPARES[addr][0]) >> 16 == 0
               for addr, word in words.items())


def pacing_closed_loop(elf, words, stall_calls=120, peer_lead=None, limit=8000):
    """The executed hold decision inside a small model of the rest of a call: a held call
    samples no input; a call with at least one frame ready runs one tick; ready frames
    are (lead after sampling) - 1.  peer_lead None: every machine is equally delayed
    (excess 0).  Otherwise the smallest lead reported by the others stays at that value.
    Returns (lead after the stall, calls until the lead stops shrinking, final lead)."""
    rig = Pacing(elf, words)
    local_input, net_frame = 1002, 1000

    def excess():
        return 0 if peer_lead is None else (local_input - net_frame) - min(local_input - net_frame, peer_lead)
    for _ in range(stall_calls):                    # peer input missing: nothing is ready
        if not rig.hold(local_input, net_frame, excess()):
            local_input += 1
        rig.note_ready(0)
    peak = local_input - net_frame
    calls = last_change = 0
    lead = peak
    while calls < limit:
        calls += 1
        if not rig.hold(local_input, net_frame, excess()):
            local_input += 1
        ready = max(0, local_input - 1 - net_frame)
        rig.note_ready(ready)
        if ready:
            net_frame += 1
        if local_input - net_frame != lead:
            lead, last_change = local_input - net_frame, calls
        if calls - last_change > 300:
            break
    return peak, last_change, lead


class SendCycle:
    """The three stretches of net_main that pick the send cycle, decide whether it is a
    peer's turn, and advance the phase."""

    def __init__(self, elf, words=None, peers=4, local=0, modem=0, flags=None):
        emu = self.emu = EE(elf)
        for addr, word in (words or {}).items():
            emu.patch(addr, word)
        mem = emu.mem
        self.fp = emu.alloc(0x2600)
        self.peers = peers
        mem.w32(G_NUM_PEERS, peers)
        mem.w8(G_UART_MODEM, modem)
        for slot in range(peers):
            # +0x44d4 local, +0x44d5 dropped, +0x44d6 kick state
            mem.w32(G_PEERS + slot * PEER_STRIDE + 0x44D4, (flags or {}).get(slot, 0))
        mem.w8(G_PEERS + local * PEER_STRIDE + 0x44D4, 1)
        self.remote = [slot for slot in range(peers)
                       if mem.u32(G_PEERS + slot * PEER_STRIDE + 0x44D4) & 0xFFFFFF == 0]

    def cycle(self):
        emu = self.emu
        emu.r[30] = self.fp
        emu.run(start=SEND_CYCLE_START, until={SEND_CYCLE_END}, max_steps=500)
        return emu.mem.s32(G_SEND_CYCLE), emu.mem.s32(self.fp + 0x2440)

    def calls(self, count):
        """For each call: the positions (0, 1, ...) of the peers that are sent a packet."""
        emu, mem, fp = self.emu, self.emu.mem, self.fp
        out = []
        for _ in range(count):
            _cycle, active = self.cycle()
            sent = []
            for position in range(active):
                mem.w32(fp + 0x2444, position)
                mem.w32(fp + 0x2440, active)
                emu.r[30] = fp
                emu.run(start=SEND_TURN_START, until={SEND_TURN_YES, SEND_TURN_NO}, max_steps=100)
                if emu.pc == SEND_TURN_YES:
                    sent.append(position)
            emu.run(start=SEND_PHASE_START, until={SEND_PHASE_END}, max_steps=100)
            out.append(sent)
        return out


def test_pacing(elf):
    emu = EE(elf)
    check('d1', all(emu.mem.u32(a) == w for a, (w, _n) in PACING_COMPARES.items()),
          'the four compares of the pacing block hold the constants docs/netcode.md gives: 39 at '
          '0x133554, 31 at 0x133574, 61 at 0x1335c0, 3 at 0x1335e4')

    rig = Pacing(elf)
    cap = [lead for lead in range(30, 46) if rig.hold(1000 + lead, 1000, 0)]
    check('d2', cap == list(range(39, 46)),
          'cap rule as shipped: a call is held when input is %d or more frames ahead of the '
          'slowest simulation frame, i.e. more than 38 (docs/netcode.md)' % cap[0])

    equal = Pacing(elf).held_calls(200, excess=5)
    never = Pacing(elf).held_calls(200, excess=4)
    broken = Pacing(elf).held_calls(100, excess=lambda n: 4 if n == 20 else 9)
    check('d3', equal == [31, 62, 93, 124, 155, 186] and never == [] and broken == [51, 82],
          'equalise rule as shipped: with the lead 5 or more above the smallest, calls %s are '
          'held (every 31st in a row); 4 above never holds; one call below 5 restarts the count '
          '(held %s)' % (equal[:3], broken))

    trim = Pacing(elf).held_calls(200, ready=3)
    no_trim = Pacing(elf).held_calls(200, ready=2)
    one_dip = Pacing(elf).held_calls(200, ready=lambda n: 2 if n == 70 else 5)
    check('d4', trim == [62, 124, 186] and no_trim == [] and one_dip == [62, 186],
          'trim rule as shipped: calls %s are held when every call of the 62-call window had 3 or '
          'more frames ready; never with 2; a single call with 2 ready frames cancels that '
          'window\'s hold (held %s)' % (trim, one_dip))

    rig = Pacing(elf)
    forced = rig.held_calls(5, caller_hold=1)
    early = [rig.hold(frame, 0, 50, 1) for frame in (0, 1, 2)]
    third = rig.hold(3, 0, 0, 1)
    check('d5', forced == [1, 2, 3, 4, 5] and early == [False, False, False] and third,
          'a non-zero second argument of net_main holds every call; while g_localInputFrame is '
          'below 3 no call is held whatever the other rules say')
    check('d6', not rig.other_writes and not Pacing(elf).other_writes,
          'the block stores only its three counters (0x4027dc, 0x4027e0, 0x4027e4) and the hold '
          'flag in net_main\'s frame')

    # every patch - in the file, proposed in lag.md, or withdrawn - that changes one of the
    # four constants.  Ids: dp = patch file, dq = proposal, dw = withdrawn.
    sources = []
    if os.path.isfile(PNACH):
        count = 0
        for title, entries in ee_emu.parse_pnach(PNACH):
            words = {a: v for a, size, v in entries if size == 4}
            if any(a in PACING_COMPARES for a in words):
                count += 1
                sources.append(('dp%d' % count, 'patch "%s"' % title, words))
    count = 0
    for ident, addr, original, new in proposal_rows(LAG_DOC):
        if ident and addr in PACING_COMPARES and original == PACING_COMPARES[addr][0]:
            if not any(words == {addr: new} for _i, _l, words in sources):
                count += 1
                sources.append(('dq%d' % count, 'proposal %s in docs/issues/lag.md' % ident, {addr: new}))
    count = 0
    for title, words in WITHDRAWN_PACING:
        count += 1
        if not any(w == words for _i, _l, w in sources):
            sources.append(('dw%d' % count, 'withdrawn patch "%s"' % title, words))
    shipped_consts = Pacing(elf).constants()
    for ident, label, words in sources:
        if not constant_only(words):
            check(ident, False, '%s changes more than the constant of a pacing compare' % label)
        else:
            ok, consts, text = pacing_battery(elf, words)
            changed = ', '.join('%s %d -> %d' % (k, shipped_consts[k], v)
                                for k, v in consts.items() if v != shipped_consts[k])
            check(ident, ok, '%s (%s) executed: %s' % (label, changed, text))
    number = 7

    rows = []
    results = {}
    scenarios = [('shipped', {})] + [(label, words) for _i, label, words in sources if constant_only(words)]
    for label, words in scenarios:
        alone = pacing_closed_loop(elf, words)
        behind = pacing_closed_loop(elf, words, peer_lead=2)
        results[label] = (alone, behind)
        rows.append('%-62s peak %2d | all equally delayed: %4d calls to lead %d | others at lead 2: %4d calls to lead %d'
                    % (label[:62], alone[0], alone[1], alone[2], behind[1], behind[2]))
    table('a 120-call stall, then input flows again (hold decision executed, the rest of the call modelled)', rows)
    alone, behind = results['shipped']
    check('d%d' % number, alone[0] == 39 and alone[2] == 2 and 2170 <= alone[1] <= 2300,
          'shipped block in a modelled call loop: a stall lets the lead grow to %d and no '
          'further; with every machine equally delayed it then takes %d calls (%.0f s at 60 '
          'calls/s) to drain to %d (FINDINGS L4; compare the 30 s of L11)'
          % (alone[0], alone[1], alone[1] / 60.0, alone[2]))
    number += 1
    check('d%d' % number, behind[2] == 2 and 800 <= behind[1] <= 1300,
          'same loop with the other machines steady at a lead of 2: the equalise rule (every '
          '31st call) and the trim rule (every 62nd) both fire, so the lead falls from %d to %d '
          'in %d calls (%.0f s) - two to three frames per 62 calls while 5 or more above '
          '(compare the 15 s of L11)' % (behind[0], behind[2], behind[1], behind[1] / 60.0))
    number += 1

    # the send cycle (L3) and the two table patches
    def cycles(words=None, modem=0):
        return [SendCycle(elf, words, peers=n, modem=modem).cycle()[0] for n in (1, 2, 3, 4)]
    shipped_cycles, modem_cycles = cycles(), cycles(modem=1)
    dropped = SendCycle(elf, peers=4, flags={2: 0x100, 3: 0x10000}).cycle()
    check('d%d' % number, shipped_cycles == [6, 2, 4, 6] and modem_cycles == [9, 3, 6, 9] and dropped == (2, 1),
          'L3 in isolation: the send cycle is %s calls for 0, 1, 2, 3 remote peers and %s on the '
          'modem; a dropped peer and a peer being kicked are not counted (cycle %d for the one left)'
          % (shipped_cycles, modem_cycles, dropped[0]))
    number += 1
    pattern = {n: SendCycle(elf, peers=n + 1).calls(12) for n in (1, 2, 3)}
    per_peer = {n: [[i for i, sent in enumerate(pattern[n]) if k in sent] for k in range(n)] for n in (1, 2, 3)}
    one_per_two = all(len(sent) == (1 if i % 2 == 0 else 0) for n in (1, 2, 3) for i, sent in enumerate(pattern[n]))
    check('d%d' % number, one_per_two and per_peer[3] == [[0, 6], [2, 8], [4, 10]] and per_peer[1] == [[0, 2, 4, 6, 8, 10]],
          'L3 in isolation: over 12 calls one packet leaves every second call whatever the player '
          'count, and each of 3 remote peers is served every 6th call (calls %s)' % per_peer[3])
    number += 1
    table_patches = []
    if os.path.isfile(PNACH):
        for title, entries in ee_emu.parse_pnach(PNACH):
            words = {a: v for a, size, v in entries if size == 4}
            if words and all(G_SEND_CYCLE_TABLE <= a < G_SEND_CYCLE_TABLE + 16 for a in words):
                table_patches.append((title, words))
    if not table_patches:
        skip('ds1', 'the patch file has no section that changes the send-cycle table')
    for count, (title, words) in enumerate(table_patches, 1):
        new_cycles = cycles(words)
        index = [i for i in range(4) if new_cycles[i] != shipped_cycles[i]]
        ok = len(index) == 1 and index[0] in (2, 3)
        text = 'changes more than one table entry'
        if ok:
            n = index[0]
            sends = SendCycle(elf, words, peers=n + 1).calls(12)
            idle = [i for i, sent in enumerate(sends) if not sent]
            served = [[i for i, sent in enumerate(sends) if k in sent] for k in range(n)]
            ok = (all(len(sent) <= 1 for sent in sends) and len(idle) == 12 // new_cycles[n]
                  and all(len(calls_) == 12 // new_cycles[n] for calls_ in served))
            text = ('with %d remote peers the cycle is %d instead of %d: each peer is served every '
                    '%s call, and call(s) %s of each cycle carry no packet'
                    % (n, new_cycles[n], shipped_cycles[n], ordinal(new_cycles[n]),
                       ', '.join(str(i + 1) for i in idle if i < new_cycles[n])))
        check('ds%d' % count, ok, 'patch "%s" executed: %s' % (title, text))


# ---------------------------------------------------------------------------------------
# e / g. Player_processDamage 0x1b2cc0 death path, game_rebuildAlivePlayers 0x1e72f8
# ---------------------------------------------------------------------------------------
PROCESS_DAMAGE, REBUILD_ALIVE, IS_LOCAL_SLOT = 0x1B2CC0, 0x1E72F8, 0x13E150
ALIVE_CALL_SITE = 0x1B3504
G_PLAYERS, PLAYER_STRIDE, PLAYER_OBJ, PLAYER_HP = 0x4D8AF0, 0x4C30, 0x43D8, 0xAC
G_NUM_PLAYERS, G_NETWORK_MODE, G_NUM_PEERS, G_PEERS, PEER_STRIDE = 0x4D8AE0, 0x402791, 0x4027C4, 0x5BF838, 0x44E0
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_LOCAL_COUNT, G_LOCAL_LIST, G_FIRST_LOCAL, G_PREV_LOCAL_COUNT = 0x4F8424, 0x4F8430, 0x4F841C, 0x4F8428
G_SIM_FRAME, G_FORCE_REBASE = 0x44FDCC, 0x402797


class World:
    """A player table with fake player objects; only the fields these functions read."""

    def __init__(self, elf, players=2, local_slot=0, network=True, words=None):
        emu = self.emu = EE(elf)
        for addr, word in (words or {}).items():
            emu.patch(addr, word)
        mem = emu.mem
        self.sounds = emu.alloc(0x100)
        mem.w32(G_NUM_PLAYERS, players)
        mem.w8(G_NETWORK_MODE, 1 if network else 0)
        mem.w32(G_NUM_PEERS, players if network else 0)
        mem.w32(G_SIM_FRAME, 1234)
        self.objects = []
        for slot in range(players):
            mem.w8(G_PEERS + slot * PEER_STRIDE + 0x44D4, 1 if slot == local_slot else 0)
            self.objects.append(self.new_object(slot))
            self.set_table(slot, self.objects[slot])
            self.set_hp(slot, 100.0)

    def new_object(self, slot, flags=0x60):
        """flags 0x20 creature, 0x40 player.  +0x3c8 slot, +0x58c state 2, +0x24 sound table."""
        mem = self.emu.mem
        obj = self.emu.alloc(0x600)
        mem.w32(obj + 0x0C, flags)
        for index, value in enumerate((100.0 + slot, 200.0, 0.0)):
            mem.wf32(obj + 0x10 + index * 4, value)
        mem.w32(obj + 0x24, self.sounds)
        mem.w32(obj + 0x3C8, slot)
        mem.w32(obj + 0x58C, 2)
        return obj

    def set_table(self, slot, obj):
        self.emu.mem.w32(G_PLAYERS + slot * PLAYER_STRIDE + PLAYER_OBJ, obj)

    def set_hp(self, slot, value):
        self.emu.mem.wf32(G_PLAYERS + slot * PLAYER_STRIDE + PLAYER_HP, value)

    def hp(self, slot):
        return self.emu.mem.f32(G_PLAYERS + slot * PLAYER_STRIDE + PLAYER_HP)

    def alive(self):
        mem = self.emu.mem
        count = mem.s32(G_ALIVE_COUNT)
        return [mem.s32(G_ALIVE_LIST + 4 * i) for i in range(max(0, min(count, 4)))]

    def local_lists(self):
        mem = self.emu.mem
        count = mem.s32(G_LOCAL_COUNT)
        return ([mem.s32(G_LOCAL_LIST + 4 * i) for i in range(max(0, min(count, 4)))],
                mem.s32(G_FIRST_LOCAL), mem.s32(G_PREV_LOCAL_COUNT))

    def rebuild(self):
        emu = self.emu
        saved = emu.follow
        emu.follow = None
        emu.call(REBUILD_ALIVE)
        emu.follow = saved

    def kill(self, obj, damage=500.0, follow=()):
        """Give the object pending damage and run Player_processDamage on it with every
        callee stubbed except those in follow."""
        emu = self.emu
        emu.mem.wf32(obj + 0xC8, damage)
        emu.mem.w32(obj + 0x2DC, 0)
        emu.follow = set(follow)
        emu.reset_log()
        emu.call(PROCESS_DAMAGE, obj)
        emu.follow = None
        return ([(c.site, c.target, tuple(a & M32 for a in c.args[:4])) for c in emu.calls],
                list(emu.writes))


def test_alive_list(elf):
    # g: game_rebuildAlivePlayers on a constructed table
    world = World(elf, players=4, local_slot=3)
    mem = world.emu.mem
    mem.w32(world.objects[1] + 0x0C, 0x68)             # slot 1 dead (flag 8)
    world.set_table(2, 0)                              # slot 2 has no object
    mem.w32(G_LOCAL_COUNT, 2)
    world.emu.reset_log()
    world.rebuild()
    stores = {a for _pc, a, _n, _v in world.emu.writes}
    check('g1', world.alive() == [0, 3] and world.local_lists() == ([3], 3, 2),
          'game_rebuildAlivePlayers on slots {alive, dead, no object, alive} with slot 3 local: '
          'alive list %s; local list, first local and previous local count %s'
          % (world.alive(), world.local_lists()))
    check('g2', all(0x4F841C <= a < 0x4F8450 for a in stores),
          'it stores only into 0x4f841c-0x4f844f (the alive and local lists and their counts)')
    mem.w32(G_NUM_PLAYERS, 2)
    world.rebuild()
    in_two = world.alive()
    mem.w32(G_NUM_PLAYERS, 4)
    mem.w32(G_NUM_PEERS, 0)
    world.rebuild()
    check('g3', in_two == [0] and world.local_lists()[0] == [0, 3],
          'only the first g_numPlayers slots are scanned (%s with 2); with no peers every alive '
          'slot counts as local (%s)' % (in_two, world.local_lists()[0]))

    # e: the death path, and the test patch that used to sit at 0x1b3504
    withdrawn = {ALIVE_CALL_SITE: 0}            # the withdrawn patch: the call becomes a no-operation
    shipped, patched = World(elf), World(elf, words=withdrawn)
    check('e1', shipped.emu.mem.u32(ALIVE_CALL_SITE) == 0x0C079CBE,
          'the word at 0x1b3504 is 0x0c079cbe, the call to game_rebuildAlivePlayers 0x1e72f8')
    calls_a, writes_a = shipped.kill(shipped.objects[0])
    calls_b, writes_b = patched.kill(patched.objects[0])
    obj = shipped.objects[0]
    m = shipped.emu.mem
    died = (m.u32(obj + 0x0C) & 0x109 == 0x109 and m.u32(obj + 0x58C) == 4 and shipped.hp(0) == 0.0
            and m.u32(obj + 0x2DC) == 0 and m.f32(obj + 0xC8) == 0.0)
    rebuild_calls = [c for c in calls_a if c[1] == REBUILD_ALIVE]
    check('e2', died and len(rebuild_calls) == 1 and rebuild_calls[0][0] == ALIVE_CALL_SITE,
          'as shipped, 500 damage on a 100-hp player takes the death path: flags 0x8|0x1|0x100, '
          'state 4, hp 0, and one call to game_rebuildAlivePlayers from 0x1b3504 (%d calls in all)'
          % len(calls_a))
    table('calls on the death path (all stubbed)', ['0x%06x from 0x%06x' % (c[1], c[0]) for c in calls_a])
    without = [c for c in calls_a if c[1] != REBUILD_ALIVE]
    check('e3', without == calls_b and writes_a == writes_b,
          'withdrawn patch (0x1b3504 := no-operation): the same run makes the same %d other calls '
          'with the same arguments and the same %d stores in the same order; the rebuild call is '
          'the only difference' % (len(calls_b), len(writes_b)))

    live = (REBUILD_ALIVE, IS_LOCAL_SLOT)
    shipped, patched = World(elf), World(elf, words=withdrawn)
    for world in (shipped, patched):
        world.rebuild()
    before = shipped.alive()
    shipped.kill(shipped.objects[0], follow=live)
    patched.kill(patched.objects[0], follow=live)
    on_the_spot, deferred = shipped.alive(), patched.alive()
    shipped.rebuild()
    patched.rebuild()
    check('e4', before == [0, 1] and on_the_spot == [1] and deferred == [0, 1]
          and shipped.alive() == patched.alive() == [1],
          'with the real rebuild running, a real death: shipped, the list goes %s -> %s inside '
          'the death; with the withdrawn patch it stays %s until the end-of-frame rebuild - the '
          'delay for real deaths that G21 gives as the reason for withdrawing it'
          % (before, on_the_spot, deferred))

    # G11-G13: the prediction copy dies while the table points at it
    def predicted_death(words=None, damage=500.0, live=live):
        world = World(elf, words=words)
        world.rebuild()
        real = world.objects[0]
        world.emu.mem.w32(real + 0x0C, 0x200060)                   # this machine's own player
        ghost = world.new_object(0, flags=0x20060)                 # its prediction copy
        saved_hp = world.hp(0)
        world.set_table(0, ghost)                                  # what prediction does (G3)
        calls, _ = world.kill(ghost, damage=damage, follow=live)
        world.set_table(0, real)                                   # what prediction restores
        world.set_hp(0, saved_hp)
        after_prediction = world.alive()
        world.rebuild()                                            # the next end-of-frame rebuild
        return calls, after_prediction, world.alive(), world.emu.mem.u8(G_FORCE_REBASE)
    calls, after, later, rebase = predicted_death()
    check('e5', any(c[1] == REBUILD_ALIVE for c in calls) and after == [1] and later == [0, 1],
          'G11/G13 in isolation: the copy\'s death calls the rebuild with no test for the copy; '
          'after prediction restores the table pointer and hp the alive list is %s although the '
          'real player lives, until the next rebuild makes it %s' % (after, later))
    check('e6', rebase == 1,
          'the same death sets the force-rebase flag 0x402797 for a local slot, so the dead copy '
          'is replaced after the next tick (G18: the window is short)')
    calls, after, later, _ = predicted_death(withdrawn)
    check('e7', not any(c[1] == REBUILD_ALIVE for c in calls) and after == [0, 1],
          'withdrawn patch: the copy\'s death leaves the alive list at %s' % after)

    # P1 / G24: Player_clone without pending damage (patch-file section at 0x11ea8c)
    section = pnach_section_at(CLONE_PATCH_SITE)
    if section is None:
        skip('e8', 'the patch file has no section for 0x11ea8c; the Player_clone patch was not run')
    else:
        clone_patch_checks(elf, dict(section[1]), live)

    # P2: the routine proposed in docs/issues/prediction-copy.md
    rows = proposal_rows(PREDICTION_DOC)
    if not rows:
        skip('e13', 'docs/issues/prediction-copy.md has no patch tables; its proposals were not run')
        return
    fresh = EE(elf)
    wrong = ['0x%x' % addr for _id, addr, original, _new in rows if fresh.mem.u32(addr) != original]
    check('e13', not wrong,
          'all %d "original" words quoted in the patch tables of docs/issues/prediction-copy.md '
          'are what the executable holds%s' % (len(rows), '' if not wrong else ' except at ' + ', '.join(wrong)))
    p2 = [r for r in rows if r[0] == 'P2']
    routine = {addr: new for ident, addr, _o, new in rows if ident is None and 0x321700 <= addr < 0x321724}
    if len(p2) != 1 or len(routine) != 9 or p2[0][1] != ALIVE_CALL_SITE:
        skip('e14', 'proposal P2 and its nine-word routine at 0x321700 were not found as expected')
        return
    p2_words = dict(routine)
    p2_words[ALIVE_CALL_SITE] = p2[0][3]
    live_p2 = live + (0x321700,)                 # the routine itself runs for real
    probe = World(elf, words=p2_words)
    reached = []
    probe.emu.hook(REBUILD_ALIVE, lambda e: reached.append(e.r[31] & M32))
    probe.rebuild()
    del reached[:]
    ghost = probe.new_object(0, flags=0x20060)
    probe.set_table(0, ghost)
    calls_copy, _ = probe.kill(ghost, follow=live_p2)
    copy_reached = list(reached)
    _, after, _later, _ = predicted_death(p2_words, live=live_p2)
    entered = [c for c in calls_copy if c[1] == 0x321700]
    check('e14', len(entered) == 1 and not copy_reached and after == [0, 1],
          'proposal P2 executed: when the copy dies the call goes to the routine at 0x321700, '
          'which returns without entering game_rebuildAlivePlayers; the alive list stays %s' % after)
    shipped, proposed = World(elf), World(elf, words=p2_words)
    reached = []
    proposed.emu.hook(REBUILD_ALIVE, lambda e: reached.append(e.r[31] & M32))
    for world in (shipped, proposed):
        world.rebuild()
    del reached[:]
    _, writes_s = shipped.kill(shipped.objects[0], follow=live)
    _, writes_p = proposed.kill(proposed.objects[0], follow=live_p2)
    check('e15', proposed.alive() == [1] and reached == [ALIVE_CALL_SITE + 8]
          and [w[1:] for w in writes_s] == [w[1:] for w in writes_p],
          'proposal P2 executed: for a real player the routine jumps on into '
          'game_rebuildAlivePlayers, which returns straight to 0x1b350c; the list becomes %s on '
          'the spot and every store has the same address and value as in the shipped run'
          % proposed.alive())
    r2 = {addr: new for ident, addr, _o, new in rows if ident is None and 0x321724 <= addr < 0x321748}
    if len(r2) != 9:
        skip('e16', 'the second routine (0x321724) was not found; not run')
        return

    def pool_guard(flags):
        e = EE(elf)
        for addr, word in r2.items():
            e.patch(addr, word)
        owner = e.alloc(0x100)
        e.mem.w32(owner + 0x0C, flags)
        asked = []
        e.stub(POOL_NEW, function=lambda emu: asked.append(emu.r[4] & M32) or 0x12345678, name='pool_new')
        e.r[30] = owner
        return e.call(0x321724, 0xB8) & M32, asked
    sites = [(ident, addr, original, new) for ident, addr, original, new in rows
             if ident and ident.startswith('O')]
    sites_ok = all(original == 0x0C053F6E and (new >> 26) == 3 and (new & 0x03FFFFFF) << 2 == 0x321724
                   for _i, _a, original, new in sites)
    check('e16', pool_guard(0x20060) == (0, []) and pool_guard(0x200060) == (0x12345678, [0xB8])
          and sites_ok and len(sites) == 6,
          'the second proposed routine (0x321724) executed on its own: it returns 0 without '
          'calling pool_new when the object in $fp is the copy, and otherwise passes the size '
          'through to pool_new and returns its result; the %d call-site words O1-O6 each replace '
          'a call to pool_new by a call to it (decoded, not run in place)' % len(sites))


CLONE_PATCH_SITE, PLAYER_CLONE, HANDLE_INIT_EMPTY = 0x11EA8C, 0x11E870, 0x1A1860


def run_clone(world, source, words=None):
    """Player_clone on source with pool_new stubbed to hand out a zeroed block and the
    one-instruction handle initialiser running for real; other callees stubbed."""
    emu = world.emu
    for addr, word in (words or {}).items():
        emu.patch(addr, word)
    block = emu.alloc(3000)
    emu.stub(POOL_NEW, ret=block, name='pool_new')
    emu.follow = {HANDLE_INIT_EMPTY}
    emu.reset_log()
    result = emu.call(PLAYER_CLONE, source) & M32
    emu.follow = None
    emu.unhook(POOL_NEW)
    stores = [(pc, addr - block, size, value) for pc, addr, size, value in emu.writes]
    calls = [(c.site, c.target) for c in emu.calls]
    emu.unpatch()
    return result, block, stores, calls


def clone_patch_checks(elf, words, live):
    fresh = EE(elf)
    original = fresh.mem.u32(CLONE_PATCH_SITE)
    new = words[CLONE_PATCH_SITE]
    check('e8', original == 0xE60000C8 and new == 0xAE0000C8 and len(words) == 1,
          'the word at 0x11ea8c is the store of the copied pending-damage amount to clone +0xc8 '
          '(swc1 f0, 0xc8(s0)); the patch stores integer zero to the same place')

    def patterned():
        world = World(elf)
        source = world.emu.alloc(0x600)
        rng = random.Random(11)
        world.emu.mem.write(source, bytes(rng.randrange(1, 255) for _ in range(0x590)))
        world.emu.mem.wf32(source + 0xC8, 500.0)
        return world, source
    world_a, source_a = patterned()
    world_b, source_b = patterned()
    result_a, clone_a, stores_a, calls_a = run_clone(world_a, source_a)
    _result_b, clone_b, stores_b, calls_b = run_clone(world_b, source_b, words)
    ma, mb = world_a.emu.mem, world_b.emu.mem
    copied = (ma.f32(clone_a + 0xC8) == 500.0 and ma.u32(clone_a + 0x2DC) == ma.u32(source_a + 0x2DC)
              and ma.u16(clone_a + 0x2E0) == ma.u16(source_a + 0x2E0)
              and ma.u32(clone_a + 0x2E8) == ma.u32(source_a + 0x2E8) and ma.u32(clone_a + 0x2E4) == 0
              and ma.u32(source_a + 0x2E4) != 0)
    check('e9', result_a == clone_a and copied,
          'G12/G14 in isolation: Player_clone copies pending amount +0xc8, flags +0x2dc, direction '
          '+0x2e0 and push +0x2e8 into the clone and leaves the attacker handle +0x2e4 empty '
          '(%d stores, %d calls)' % (len(stores_a), len(calls_a)))
    differing = [(a, b) for a, b in zip(stores_a, stores_b) if a != b]
    check('e10', len(stores_a) == len(stores_b) and calls_a == calls_b and len(differing) == 1
          and differing[0][0][:3] == (CLONE_PATCH_SITE, 0xC8, 4) and differing[0][1][3] == 0
          and mb.u32(clone_b + 0x2DC) == mb.u32(source_b + 0x2DC),
          'patch "prediction copy starts without pending damage": the same clone makes the same '
          'calls and the same %d stores except one - clone +0xc8 receives 0 instead of the '
          'amount; the pending flags +0x2dc are still copied' % len(stores_b))

    def clone_then_predict(patch_words):
        world = World(elf)
        world.rebuild()
        real = world.objects[0]
        mem = world.emu.mem
        mem.w32(real + 0x0C, 0x200060)
        mem.wf32(real + 0xC8, 500.0)                 # a killing blow waiting on the real player
        _, ghost, _, _ = run_clone(world, real, patch_words)
        mem.w32(ghost + 0x0C, (mem.u32(ghost + 0x0C) & ~0x200000) | 0x20000)   # as the rebase does
        saved_hp = world.hp(0)
        world.set_table(0, ghost)
        emu = world.emu
        emu.follow = set(live)
        emu.reset_log()
        emu.call(PROCESS_DAMAGE, ghost)              # pending fields are the cloned ones
        emu.follow = None
        calls = [c.target for c in emu.calls]
        dead = bool(mem.u32(ghost + 0x0C) & 8)
        world.set_table(0, real)
        world.set_hp(0, saved_hp)
        return dead, REBUILD_ALIVE in calls, world.alive(), mem.f32(real + 0xC8)
    shipped = clone_then_predict(None)
    patched = clone_then_predict(words)
    check('e11', shipped == (True, True, [1], 500.0),
          'G12 chain executed: a copy cloned while a killing blow waits on the real player dies '
          'from the cloned blow when its damage is processed, and the alive list becomes %s '
          'while the real player has not yet been hit' % shipped[2])
    check('e12', patched == (False, False, [0, 1], 500.0),
          'with the patch the same copy does not die and does not rebuild the list (%s); the '
          'blow still waits on the real player, whose own death path is not in the patched '
          'function' % patched[2])


# ---------------------------------------------------------------------------------------
# g (second half). The sync record, net_frameLoop 0x13af44-0x13b138 (docs/netcode.md, D1)
# ---------------------------------------------------------------------------------------
HASH_START, HASH_END = 0x13AF44, 0x13B138
G_NET_FRAME, G_SYNC_ACC, G_RAND_SEED, DBG_PRINTF = 0x4027AC, 0x4027C0, 0x404464, 0x355490
PEER_SYNC_RING = 0x18AC


class HashRig:
    def __init__(self, elf, positions, peers=0, local=0):
        self.world = World(elf, players=len(positions), local_slot=local, network=True)
        emu = self.emu = self.world.emu
        mem = emu.mem
        mem.w32(G_NUM_PEERS, peers)
        self.fp = emu.alloc(0x400)
        self.local = local
        self.printed = []
        emu.stub(DBG_PRINTF, function=lambda e: self.printed.append(e.mem.cstr(e.r[4] & M32)), name='dbg_printf')
        for slot, pos in enumerate(positions):
            if pos is None:
                self.world.set_table(slot, 0)
                continue
            for index, value in enumerate(pos):
                mem.wf32(self.world.objects[slot] + 0x10 + index * 4, value)

    def run(self, frame=500, seed=0x12345678, acc=0):
        emu, mem, fp = self.emu, self.emu.mem, self.fp
        mem.w32(G_NET_FRAME, frame)
        mem.w32(G_SYNC_ACC, acc)
        mem.w32(G_RAND_SEED, seed)
        mem.w32(G_SIM_FRAME, 0x7777)
        mem.w32(fp + 0x394, self.local * PEER_STRIDE)
        mem.w32(fp + 0x388, 4321)                      # the saved g_simFrame
        emu.r[30] = fp
        emu.r[21] = 0x4E0000
        emu.run(start=HASH_START, until={HASH_END}, max_steps=5000)
        new = frame + 1
        entry = G_PEERS + self.local * PEER_STRIDE + PEER_SYNC_RING + (new & 0xFF) * 12
        return (mem.u32(entry), mem.u32(entry + 4), mem.u32(entry + 8)), mem.u32(G_NET_FRAME), mem.u32(G_SIM_FRAME)

    def remote_record(self, peer, frame, value):
        entry = G_PEERS + peer * PEER_STRIDE + PEER_SYNC_RING + (frame & 0xFF) * 12
        self.emu.mem.w32(entry, frame)
        self.emu.mem.w32(entry + 8, value)

    def out_of_sync(self, peer):
        return self.emu.mem.u8(G_PEERS + peer * PEER_STRIDE + 0x44D7)


def test_sync_hash(elf):
    positions = [(100.25, -200.75, 12.9), None, (3000.0, 4000.5, -0.5)]
    rig = HashRig(elf, positions)
    record, net_frame, sim_frame = rig.run()
    expected = (0x12345678 + (100 - 200 + 12) + (3000 + 4000 + 0)) & M32
    check('g4', record == (501, 4321, expected) and net_frame == 501 and sim_frame == 4321,
          'the tick\'s tail stores {frame %d, saved frame counter, hash 0x%08x}: hash = seed + '
          'the truncated x, y and height of every player object, empty slots skipped, exactly as '
          'docs/netcode.md and D1 say' % (record[0], record[2]))
    base = record[2]
    moved = HashRig(elf, [(100.99, -200.01, 12.0), None, (3000.9, 4000.0, 0.9)]).run()[0][2]
    check('g5', moved == base,
          'positions that differ by less than one unit give the same hash (0x%08x): divergence '
          'below one unit is invisible to the check' % moved)
    swapped = HashRig(elf, [(101.25, -200.75, 12.9), None, (3000.0, 3999.5, -0.5)]).run()[0][2]
    with_acc = rig.run(acc=7)[0][2]
    check('g6', swapped == base and with_acc == (base + 7) & M32,
          'the hash is a plain sum: one player one unit east and another one unit south gives '
          'the same value; g_syncAcc is added as well (always 0 in the shipped game)')

    def compare(remote_hash_delta, remote_frame=501, dropped=False):
        r = HashRig(elf, positions, peers=2, local=0)
        if dropped:
            r.emu.mem.w8(G_PEERS + PEER_STRIDE + 0x44D5, 1)
        if remote_frame is not None:
            r.remote_record(1, remote_frame, (base + remote_hash_delta) & M32)
        r.run()
        return r.out_of_sync(1), len(r.printed)
    mismatch, equal, stale, gone = compare(1), compare(0), compare(1, remote_frame=245), compare(1, dropped=True)
    check('g7', mismatch == (1, 1) and equal == (0, 0),
          'when the peer\'s record for the same frame is already there, a different hash sets '
          'that peer\'s out-of-sync byte (+0x44d7) and prints the message; an equal hash does nothing')
    check('g8', stale == (0, 0) and gone == (0, 0),
          'a ring entry that belongs to another frame is not compared, and a dropped peer is '
          'never compared')


# ---------------------------------------------------------------------------------------
# f. cut_advance 0x199214 and the cutscene audio patch at 0x199448 (FINDINGS D8, D18)
# ---------------------------------------------------------------------------------------
CUT_ADVANCE, CUT_PATCH_SITE = 0x199214, 0x199448
STRCMP, PATH_SERVICE, FIND_TRACK, AUDIO_POSITION, AUDIO_STATUS = 0x3B8534, 0x184798, 0x171178, 0x216480, 0x211B20
SEND_GAME_MSG, COUNT_ACTIVE_PEERS, CUT_EXEC_KEY = 0x13DB38, 0x13E078, 0x196788
G_CUT_SPEAKER, G_CUT_LAST_AUDIO, G_CUT_CORRECTION, G_CUT_FRAME = 0x83D18C, 0x83D108, 0x44FD30, 0x44FCE0
G_CUT_KEYS, G_CUT_KEY_COUNT, G_CUT_KEY_INDEX, G_CUT_CLOCK = 0x83D190, 0x83D194, 0x44FCFC, 0x83D198
G_CUT_SKIP, G_CUT_NET_WAIT, G_CUT_DONE_SENT, G_CUT_DONE_COUNT, G_CUT_DONE_MSG = 0x44FCEC, 0x44FCD1, 0x44FD2C, 0x44FD28, 0x83D1C8
AUDIO_UNIT = 7.29167e-05           # seconds per unit of the stream position, from the code


class CutRig:
    def __init__(self, elf, patched=False, speaker=True, tracks=(100.0, 600.0, 250.0)):
        emu = self.emu = EE(elf)
        if patched and apply_section_at(emu, CUT_PATCH_SITE) is None:
            raise LookupError('no patch-file section patches 0x199448')
        mem = emu.mem
        self.audio = 0
        self.audio_status = 1
        self.active_peers = 2
        emu.stub(STRCMP, ret=1, name='strcmp')
        emu.stub(PATH_SERVICE, name='path_service')
        emu.stub(AUDIO_POSITION, function=lambda e: self.audio, name='audio_streamPosition')
        emu.stub(AUDIO_STATUS, function=lambda e: self.audio_status, name='audio_streamStatus')
        emu.stub(SEND_GAME_MSG, name='net_sendGameMsg')
        emu.stub(COUNT_ACTIVE_PEERS, function=lambda e: self.active_peers, name='net_countActivePeers')
        emu.stub(CUT_EXEC_KEY, name='cut_execKey')
        self.speaker = emu.alloc(0x400)
        self.tracks = tracks
        mem.w8(self.speaker + 0x118, len(tracks))             # track count of the animation state
        for index, time in enumerate(tracks):
            mem.wf32(self.speaker + 0x134 + index * 0x20, time)
            mem.w16(self.speaker + 0x138 + index * 0x20, 0x20 if index == 1 else 0)
        mem.w32(G_CUT_SPEAKER, self.speaker if speaker else 0)
        mem.w32(G_CUT_FRAME, 600)
        self.keys = emu.alloc(0x100)
        mem.w32(G_CUT_KEYS, self.keys)

    def times(self):
        return [self.emu.mem.f32(self.speaker + 0x134 + i * 0x20) for i in range(len(self.tracks))]

    def advance(self, audio=None, clock=10.0):
        if audio is not None:
            self.audio = audio
        self.emu.reset_log()
        self.emu.call(CUT_ADVANCE, fargs=(clock,))
        return ([c.target for c in self.emu.calls],
                [(pc, a, n, v) for pc, a, n, v in self.emu.writes])


def audio_units_for(track_time_frames, offset_seconds=0.0):
    """Stream position at which the code considers audio and animation aligned."""
    return int(round(0x400 + (track_time_frames / 60.0 - 0.07 + offset_seconds) / AUDIO_UNIT))


def cutscene_patch_checks(elf):
    shipped, patched, silent = CutRig(elf), CutRig(elf, patched=True), CutRig(elf, speaker=False)
    audio = audio_units_for(600.0, +1.0)
    calls_s, writes_s = shipped.advance(audio=audio)
    calls_p, writes_p = patched.advance(audio=audio)
    calls_n, writes_n = silent.advance(audio=audio)
    touched = {a for _pc, a, _n, _v in writes_s} - {a for _pc, a, _n, _v in writes_p}
    expected_touch = ({shipped.speaker + 0x134 + i * 0x20 for i in range(3)}
                      | {G_CUT_LAST_AUDIO, G_CUT_CORRECTION})
    check('f5', FIND_TRACK not in calls_p and AUDIO_POSITION not in calls_p
          and patched.times() == list(patched.tracks) and touched == expected_touch
          and [c for c in calls_s if c not in (FIND_TRACK, AUDIO_POSITION)] == calls_p,
          'with the patch the same call makes neither the track lookup nor the audio position '
          'request and leaves the speaker untouched; the stores it no longer makes are the %d '
          'track times, 0x83d108 and 0x44fd30, and nothing else changes' % len(patched.tracks))
    check('f6', calls_p == calls_n and [w[1:] for w in writes_p] == [w[1:] for w in writes_n]
          and patched.emu.f[0] == silent.emu.f[0],
          'the patched function with a speaker behaves exactly like the shipped function with no '
          'speaker (same calls, same stores, same return value)')


def test_cutscene(elf):
    emu = EE(elf)
    check('f1', emu.mem.u32(CUT_PATCH_SITE) == 0x12000060,
          'the word at 0x199448 is "skip the block if there is no speaker" (beqz); the patch makes '
          'the same branch unconditional')

    rig = CutRig(elf)
    start = rig.times()
    calls, _writes = rig.advance(audio=audio_units_for(600.0, +1.0))
    ahead = rig.times()
    step = float_to_raw(ahead[1]) != float_to_raw(start[1]) and abs(ahead[1] - start[1] - 0.1) < 1e-3
    check('f2', FIND_TRACK in calls and AUDIO_POSITION in calls and step
          and all(abs(b - a - 0.1) < 1e-3 for a, b in zip(start, ahead))
          and abs(rig.emu.mem.f32(G_CUT_CORRECTION) - 0.1) < 1e-6,
          'as shipped, with the audio stream 1 s ahead of the speaker\'s flagged track, one call '
          'adds 0.1 to the time of all %d animation tracks of the speaker (%s -> %s) (D8)'
          % (len(start), ['%.1f' % t for t in start], ['%.1f' % t for t in ahead]))

    outcomes = []
    for offset in (+1.0, -1.0, 0.0):
        r = CutRig(elf)
        r.advance(audio=audio_units_for(600.0, offset))
        outcomes.append(round(r.times()[1] - 600.0, 3))
    check('f3', outcomes == [0.1, -0.1, 0.0],
          'the same game state with three different local audio positions (1 s ahead, 1 s behind, '
          'aligned) leaves the track time changed by %s: per-machine audio timing reaches '
          'animation state' % outcomes)
    r = CutRig(elf)
    pos = audio_units_for(600.0, +1.0)
    r.advance(audio=pos)
    r.advance(audio=pos)
    held = round(r.times()[1] - 600.0, 3)
    tolerance = []
    for delta in (0.015, 0.025):
        t = CutRig(elf)
        t.advance(audio=audio_units_for(600.0, delta))
        tolerance.append(round(t.times()[1] - 600.0, 3))
    check('f4', held == 0.2 and tolerance == [0.0, 0.1],
          'while the stream position reads the same value the last correction is applied again '
          'each call (two calls: +%.1f); the dead band is 0.02 s (0.015 s off: %+.1f, 0.025 s: %+.1f)'
          % (held, tolerance[0], tolerance[1]))

    if pnach_section_at(CUT_PATCH_SITE) is None:
        skip('f5', 'the patch file has no section for 0x199448 any more; the patched runs were not made')
    else:
        cutscene_patch_checks(elf)

    # D18: the "everyone wait" key
    def wait_key(done_count, audio_status, peers, sent=0):
        r = CutRig(elf, speaker=False)
        mem = r.emu.mem
        mem.wf32(r.keys, 5.0)                       # key time, earlier than the clock
        mem.w32(r.keys + 4, 0x3FF9D)                # the wait key type
        mem.w32(G_CUT_KEY_COUNT, 1)
        mem.w32(G_CUT_KEY_INDEX, 0)
        mem.w8(G_CUT_NET_WAIT, 1)
        mem.w32(G_CUT_DONE_COUNT, done_count)
        mem.w32(G_CUT_DONE_SENT, sent)
        mem.w32(G_CUT_DONE_MSG, 0)
        mem.wf32(G_CUT_CLOCK, 10.0)
        r.audio_status, r.active_peers = audio_status, peers
        calls, _ = r.advance()
        return dict(sent=SEND_GAME_MSG in calls, ran=CUT_EXEC_KEY in calls,
                    index=mem.u32(G_CUT_KEY_INDEX), frame=mem.u32(G_CUT_FRAME),
                    clock=round(mem.f32(G_CUT_CLOCK), 4), flag=mem.u32(G_CUT_DONE_SENT))
    playing = wait_key(0, 1, 2)
    ended = wait_key(0, 0, 2)
    one_done = wait_key(1, 0, 2)
    all_done = wait_key(2, 0, 2)
    check('f7', (not playing['sent'] and not playing['ran'] and playing['index'] == 0
                 and playing['frame'] == 600 and playing['clock'] == round(10.0 - 1 / 60.0, 4)),
          'D18 in isolation: while this machine\'s stream is still playing, a wait key sends '
          'nothing, is not executed, and the cutscene frame, clock and key index are put back')
    check('f8', ended['sent'] and ended['flag'] == 1 and not ended['ran'] and not one_done['ran']
          and all_done['ran'] and all_done['index'] == 1 and all_done['flag'] == 0,
          'once the local stream has ended the "done" message is queued once; the key runs only '
          'when the done count has reached the number of active peers (2 of 2), not at 1 of 2')
# ---------------------------------------------------------------------------------------
# h. The network sign-in state machine 0x33ed70, state 5 (docs/online-setup.md)
# ---------------------------------------------------------------------------------------
SIGNIN_RUN, SIGNIN_START_CHECK = 0x33ED70, 0x1E3C84
G_DEBUG_FLAG, G_PAD0_BUTTONS = 0x4F8EE0, 0x41BFE0
SIGNIN_STATE, SIGNIN_LINK_READY, SIGNIN_SEMA = 0xDB4, 0xE00 + 0x3D94, 0xE00 + 0x3D9C


def signin_run(elf, state=5, link_ready=1, debug=0, buttons=0, local_patch=False):
    """One call of the state machine on a blank menu object with every callee stubbed.
    Returns (return value, state afterwards, whether the sign-in check was started)."""
    emu = EE(elf)
    if local_patch:
        emu.apply_pnach(LOCAL_SIGNIN_PNACH)        # words are applied, never printed
    obj = emu.alloc(0x5000)
    mem = emu.mem
    mem.w32(obj + SIGNIN_STATE, state)
    mem.w32(obj + SIGNIN_LINK_READY, link_ready)
    mem.w32(obj + SIGNIN_SEMA, 0xFFFFFFFF)         # no semaphore: skips the two kernel calls
    mem.w8(G_DEBUG_FLAG, debug)
    mem.w32(G_PAD0_BUTTONS, buttons)
    emu.follow = set()
    value = s32(emu.call(SIGNIN_RUN, obj))
    started = any(c.target == SIGNIN_START_CHECK for c in emu.calls)
    return value, mem.u32(obj + SIGNIN_STATE), started


def test_signin(elf):
    check('h1', signin_run(elf, link_ready=0) == (2, 5, False),
          'state 5 with the link-ready field clear returns 2 ("still busy") and stays in state 5')
    shipped = signin_run(elf)
    check('h2', shipped == (2, 0xC, True),
          'state 5 as shipped with the link up calls 0x1e3c84 (the start of the sign-in check), '
          'moves to state 0xc and returns %d' % shipped[0])
    shortcut = signin_run(elf, debug=1, buttons=0x400)
    half = (signin_run(elf, debug=1, buttons=0), signin_run(elf, debug=0, buttons=0x400))
    check('h3', shortcut == (4, 5, False) and half == (shipped, shipped),
          'with the debug flag 0x4f8ee0 set and pad bit 0x400 held, state 5 returns %d without '
          'starting the check; either condition alone behaves as shipped' % shortcut[0])
    ready = signin_run(elf, state=0xB)
    check('h4', ready[0] == 4 and signin_run(elf, state=0xB, link_ready=0)[0] == 2,
          'state 0xb, the normal end of the sequence, returns the same %d when the link is up: '
          'that is the "network ready" value' % ready[0])
    if os.path.isfile(LOCAL_SIGNIN_PNACH):
        patched = signin_run(elf, local_patch=True)
        down = signin_run(elf, link_ready=0, local_patch=True)
        check('h5', patched == (4, 5, False) and down == (2, 5, False),
              'with the local sign-in patch applied the shortcut path is executed: state 5 returns '
              '%d without the debug flag or a held button and without starting the check; with the '
              'link down it still returns %d' % (patched[0], down[0]))
    else:
        print('SKIP  h5   local sign-in patch file not present; the patched run was not made')


# ---------------------------------------------------------------------------------------
# i. Other ledger rows that a function-level run settles cheaply
# ---------------------------------------------------------------------------------------
COUNTER_LOOP, COUNTER_STOPS, GAME_IS_FROZEN = 0x10B898, (0x10B8D8, 0x10B8DC, 0x10B8E0, 0x10B924), 0x1EBDF8
G_PAUSED = 0x41B4F4
NEWWORLD_GATE, G_SCRIPT_ACTIVE_PLAYER, PLAYER_COOLDOWN = 0x143D04, 0x4D8AE4, 0x4BCA
OBJ_OR_GHOST, G_GHOST, OBJECT_RAND = 0x13E180, 0x4027BC, 0x1509D0
USE_POTION, SCORE_A, SCORE_B, ENGINE_STEP = 0x1B9CB8, 0x305580, 0x305650, 0x19E3A8


def counters_after(elf, counters, frozen=0):
    """Run the status-counter loop inside Creature_draw (0x10b898 onward) on a blank
    creature; returns the 16 counters afterwards and whether game_isFrozen was asked."""
    emu = EE(elf)
    creature = emu.alloc(0x600)
    for index, value in enumerate(counters):
        emu.mem.w32(creature + 0x36C + index * 4, value)
    asked = []
    emu.stub(GAME_IS_FROZEN, function=lambda e: asked.append(1) or frozen, name='game_isFrozen')
    emu.r[18] = creature
    emu.run(start=COUNTER_LOOP, until=set(COUNTER_STOPS), max_steps=500)
    stores = [a - creature for _pc, a, _n, _v in emu.writes]
    return [emu.mem.s32(creature + 0x36C + i * 4) for i in range(16)], bool(asked), stores


def test_other_rows(elf):
    # D12: the draw function's status counters
    base = [0] * 16
    idle, asked, _ = counters_after(elf, base)
    two = list(base)
    two[3], two[7] = 5, 9
    after_two, _, stores = counters_after(elf, two)
    frozen_two, _, _ = counters_after(elf, two, frozen=1)
    check('i1', idle == base and not asked and after_two[3] == 4 and after_two[7] == 9
          and stores == [0x36C + 3 * 4] and frozen_two == two,
          'D12 in isolation: the loop in Creature_draw decrements only the first non-zero of the '
          '16 counters (index 3: 5 -> %d, index 7 stays %d) and nothing while game_isFrozen '
          'returns non-zero' % (after_two[3], after_two[7]))
    twelve = list(base)
    twelve[12], twelve[13], twelve[15] = 4, 6, 8
    after_twelve, _, stores = counters_after(elf, twelve)
    check('i2', after_twelve == twelve and stores == [],
          'D12 adds: index 12 is not decremented, and because the loop stops at the first '
          'non-zero counter, counters 13-15 are not decremented either while 12 is non-zero')
    emu = EE(elf)
    emu.reads = []
    emu.mem.w8(G_NETWORK_MODE, 1)
    emu.mem.w32(G_PAUSED, 7)
    emu.follow = set()
    value = emu.call(GAME_IS_FROZEN)
    globals_read = sorted({a for _pc, a, _n, _v in emu.reads if a < 0x01000000})
    check('i3', value == 7 and globals_read == [G_NETWORK_MODE, G_PAUSED] and not emu.calls,
          'game_isFrozen in a net game returns the pause word 0x41b4f4 and reads nothing else '
          '(D12: "frozen" is only the pause flag)')

    # D20: newWorld gate
    def gate(network=1, active=1, cooldown=0, alive=2, local=0):
        e = EE(elf)
        m = e.mem
        m.w8(G_NETWORK_MODE, network)
        m.w32(G_SCRIPT_ACTIVE_PLAYER, active & M32)
        slot = active if active >= 0 else 0
        field = G_PLAYERS + slot * PLAYER_STRIDE + PLAYER_COOLDOWN
        m.w16(field, cooldown)
        m.w32(G_ALIVE_COUNT, alive)
        e.follow = set()
        e.stub(IS_LOCAL_SLOT, ret=local)
        value = s32(e.call(NEWWORLD_GATE))
        return value, m.u16(field), len([c for c in e.calls if c.target != IS_LOCAL_SLOT])
    check('i4', gate(network=0, cooldown=5) == (0, 5, 0) and gate(active=-1, cooldown=5) == (0, 5, 0)
          and gate(cooldown=0) == (0, 600, 0) and gate(cooldown=77) == (1, 77, 0)
          and gate(cooldown=77, local=1)[0] == 1 and gate(cooldown=77, local=1)[2] == 3,
          'D20 in isolation: offline or with no active player the gate allows and changes nothing; '
          'in a net game it starts a 600-frame cooldown, and refuses (returns 1, message on the '
          'local machine only) while the cooldown runs')
    alone = gate(cooldown=77, alive=1)
    check('i5', alone == (0, 600, 0),
          'D20 leaves out a condition: with fewer than two players in the alive list the gate '
          'allows the level change even while the cooldown runs, and restarts it (%d, cooldown %d) '
          '- so the gate is one more reader of the alive list (G13)' % alone[:2])

    # G6 / per-machine row 6: net_objOrGhost
    world = World(elf, players=2, local_slot=0)
    emu, mem = world.emu, world.emu.mem
    ghost = world.new_object(0, flags=0x20060)
    mem.w32(G_GHOST, ghost)
    prop = emu.alloc(0x400)
    own = emu.call(OBJ_OR_GHOST, world.objects[0]) & M32
    other = emu.call(OBJ_OR_GHOST, world.objects[1]) & M32
    plain = emu.call(OBJ_OR_GHOST, prop) & M32
    mem.w8(G_NETWORK_MODE, 0)
    offline = emu.call(OBJ_OR_GHOST, world.objects[0]) & M32
    check('i6', (own, other, plain, offline) == (ghost, world.objects[1], prop, world.objects[0]),
          'net_objOrGhost 0x13e180 returns the prediction copy for this machine\'s own player, the '
          'object itself for another player, a non-player or offline: its result differs per '
          'machine (docs/netcode.md, per-machine row 6)')

    # the per-object generator
    emu = EE(elf)
    obj = emu.alloc(0x100)
    seed = 0xCAFEF00D
    emu.mem.w32(obj + 0x44, seed)
    got = [emu.call(OBJECT_RAND, obj) & M32 for _ in range(3)]
    want = []
    for _ in range(3):
        seed = (seed * 1664525 + 1013904223) & M32
        want.append(seed >> 16)
    check('i7', got == want and emu.mem.u32(obj + 0x44) == seed,
          'GameObject_rand 0x1509d0 is state = state * 1664525 + 1013904223, result state >> 16, '
          'state at object +0x44 (docs/OVERVIEW.md "Randomness")')

    # G8 / G9: guards against the prediction copy
    world = World(elf, players=2)
    emu, mem = world.emu, world.emu.mem
    ghost = world.new_object(0, flags=0x20060)
    emu.follow = set()
    emu.reset_log()
    emu.call(USE_POTION, ghost, 0, 0, 0, 0)
    check('i8', not emu.calls and not emu.writes,
          'G8 in isolation: Player_usePotion called on an object with the copy flag 0x20000 '
          'returns without a single call or store outside its stack frame')

    def score(function, table_points_at_copy, pvp_a=0):
        w = World(elf, players=2)
        m = w.emu.mem
        if table_points_at_copy:
            w.set_table(0, w.new_object(0, flags=0x20060))
        m.w32(0x4F711C, pvp_a)
        w.emu.follow = set()
        w.emu.reset_log()
        w.emu.call(function, 0, 0)
        return [(a, n) for _pc, a, n, _v in w.emu.writes], len(w.emu.calls)
    real_a, copy_a = score(SCORE_A, False), score(SCORE_A, True)
    real_b, copy_b = score(SCORE_B, False), score(SCORE_B, True)
    check('i9', real_a[0] == [(0x50389A, 2)] and real_b[0] == [(0x50389A, 2)]
          and copy_a == ([], 0) and copy_b == ([], 0),
          'G9 in isolation: the two score functions 0x305580 and 0x305650 change the 16-bit score '
          'at 0x50389a for a real player and do nothing when the player table points at a copy')

    # L5: frames per call
    def frame_step(mode, counter=0, alt=0):
        e = EE(elf)
        e.mem.w32(0x44FD40, mode)
        e.mem.w32(0x83D2C8, counter)
        e.mem.w8(0x44FD50, alt)
        return s32(e.call(ENGINE_STEP))
    fresh = EE(elf)
    initial = (fresh.mem.u32(0x44FD40), fresh.mem.s8(0x44FD50), s32(fresh.call(ENGINE_STEP)))
    steps = [frame_step(0, counter=v) for v in (0, 1, 2, 3, 10)]
    alt_steps = [frame_step(1, alt=v) for v in (0, 1, 5)]
    check('i10', steps == [1, 1, 2, 2, 2] and alt_steps == [1, 2, 2] and initial == (1, 0, 1),
          'L5 in isolation: engine_frameStep 0x19e3a8 returns a count clamped to 1..2 (%s for a '
          'field count of 0, 1, 2, 3, 10 when 0x44fd40 is 0; %s for 0x44fd50 = 0, 1, 5 otherwise), '
          'so at most two input frames are produced per call; with the values in the executable '
          'it returns %d' % (steps, alt_steps, initial[2]))


# ---------------------------------------------------------------------------------------
# j. The four "arena diagnostic" patches (docs/issues/arena-desync.md T1, T3, T4, T5)
# ---------------------------------------------------------------------------------------
KNIGHT_SITE, REAPER_SITE, LIPSYNC_SITE, CAMERA_SITE = 0x2726F4, 0x14B9CC, 0x196AA0, 0x1E4DD4
G_POOL_FREE_COUNT, G_CULL_BY_CAMERA, G_CAMERA_PTR, G_CUTSCENE_ACTIVE = 0x403A04, 0x4039C1, 0x4F8450, 0x44FCD0
G_SKILL_SUMMON_PTR, G_CUT_LIPSYNC_READY, G_CUT_DIALOG_LINE, G_CUT_LIP_SLOTS = 0x41B19C, 0x83D180, 0x44FD0C, 0x83D170
ANIM_START, FIND_ROLE_ANIM = 0x16CFE0, 0x160928


def patched_emu(elf, site, patched):
    emu = EE(elf)
    if patched and apply_section_at(emu, site) is None:
        raise LookupError('no patch-file section patches 0x%x' % site)
    return emu


def knight_step(elf, patched, variant, can_use):
    """Horsemen_run from the variant test (0x2726ec) to either the cast exit 0x272ef0 or
    the walk call 0x27272c.  The skill's "can use" virtual is a stub."""
    emu = patched_emu(elf, KNIGHT_SITE, patched)
    mem = emu.mem
    knight, skill, vtable, fake = emu.alloc(0x600), emu.alloc(0x100), emu.alloc(0x40), 0x00090000
    emu.load_words(fake, [0x03E00008, 0])
    asked = []
    emu.stub(fake, function=lambda e: asked.append(e.r[5] & M32) or can_use, name='can use')
    mem.w8(knight + 0x470, variant)
    mem.w32(G_SKILL_SUMMON_PTR, skill)
    mem.w32(skill + 0x60, vtable)
    mem.w32(vtable + 0x0C, fake)                 # slot at +8: {s16 delta, pad, function}
    emu.r[17] = knight
    emu.run(start=0x2726EC, until={0x272EF0, 0x27272C}, max_steps=200)
    return emu.pc == 0x272EF0, asked == [knight], s32(emu.r[5]) if emu.pc == 0x272EF0 else None


def reaper_step(elf, patched, frame, allocated, stale=None):
    """runObjects from 0x14b9ac to the reaper body (0x14b9d8) or past it (0x14bb20), on
    the real pool with `allocated` blocks taken."""
    emu = patched_emu(elf, REAPER_SITE, patched)
    emu.call(POOL_INIT)
    for _ in range(allocated):
        emu.call(POOL_NEW, 0x100)
    if stale is not None:
        emu.mem.w32(G_POOL_FREE_COUNT, stale)
    emu.mem.w32(G_SIM_FRAME, frame)
    emu.r[16] = G_SIM_FRAME
    emu.follow = {POOL_COUNT_FREE}
    emu.run(start=0x14B9AC, until={0x14B9D8, 0x14BB20}, max_steps=20000)
    return emu.pc == 0x14B9D8, emu.mem.s32(G_POOL_FREE_COUNT)


def lipsync_step(elf, patched, line, ready):
    """cut_execKey from 0x196a90 to the first anim_start of whichever path is taken;
    returns the path and the flags argument of that call."""
    emu = patched_emu(elf, LIPSYNC_SITE, patched)
    mem = emu.mem
    speaker, anm = emu.alloc(0x400), emu.alloc(0x40)
    mem.w32(G_CUT_SPEAKER, speaker)
    mem.w32(G_CUT_DIALOG_LINE, line)
    mem.w32(G_CUT_LIPSYNC_READY, ready)
    for slot in range(2):
        mem.w32(G_CUT_LIP_SLOTS + slot * 8, anm)
        mem.w32(G_CUT_LIP_SLOTS + slot * 8 + 4, 1)
    emu.follow = set()
    emu.stub(FIND_ROLE_ANIM, ret=0x1234, name='obj_findRoleAnim')
    emu.r[2] = 0x1234
    emu.r[16] = 0x840000
    emu.r[18] = G_CUT_SPEAKER
    emu.r[20] = G_CUT_DIALOG_LINE
    emu.run(start=0x196A90, until={0x196AFC, 0x196BA4, 0x196C10}, max_steps=500)
    starts = [c for c in emu.calls if c.target == ANIM_START]
    path = {0x196AFC: 'lip-sync', 0x196BA4: 'generic'}.get(emu.pc, 'none')
    return path, (starts[0].args[2] & M32) if starts else None


def camera_step(elf, patched, network, cutscene, mode):
    """gameSetObjectVis from 0x1e4dac to 0x1e4de0: the byte that says "judge activity
    from the camera"."""
    emu = patched_emu(elf, CAMERA_SITE, patched)
    mem = emu.mem
    camera = emu.alloc(0x100)
    mem.w32(camera + 0x34, mode)
    mem.w32(G_CAMERA_PTR, camera)
    mem.w8(G_NETWORK_MODE, network)
    mem.w8(G_CUTSCENE_ACTIVE, cutscene)
    mem.w8(G_CULL_BY_CAMERA, 0x77)
    emu.r[2] = 0x500000
    emu.run(start=0x1E4DA8, until={0x1E4DE0}, max_steps=100)
    return mem.u8(G_CULL_BY_CAMERA)


GIANT_SITE, BOMB_SITE, IS_NEAR_VIEW = 0x250930, 0x261FD0, 0x1E77C0


def giant_step(elf, patched, beam_handle, bolt_flag):
    """CloudGiant run from the test at 0x250930 to the conjure exit 0x251d3c or past it."""
    emu = patched_emu(elf, GIANT_SITE, patched)
    giant = emu.alloc(0x600)
    emu.mem.w32(giant + 0x530, beam_handle)
    emu.mem.w32(giant + 0x508, bolt_flag)
    emu.r[18] = giant
    emu.run(start=GIANT_SITE, until={0x251D3C, 0x250944}, max_steps=50)
    return emu.pc == 0x251D3C


def bomb_step(elf, patched, near_view):
    """FireBomb_run from 0x261fc4 to just after the store of the shared seed (0x262010) or
    to the "not near the view" exit 0x262288.  Returns (launch path taken, the view test
    was asked, its arguments, the shared seed afterwards)."""
    emu = patched_emu(elf, BOMB_SITE, patched)
    thrower = emu.alloc(0x400)
    asked = []
    emu.stub(IS_NEAR_VIEW, function=lambda e: asked.append((e.r[4] & M32, e.fget(12))) or near_view,
             name='isNearView')
    emu.mem.w32(G_RAND_SEED, 0x1234)
    emu.r[17] = thrower
    emu.run(start=0x261FC4, until={0x262010, 0x262288}, max_steps=100)
    relative = [(addr - thrower, distance) for addr, distance in asked]
    return emu.pc == 0x262010, relative, emu.mem.u32(G_RAND_SEED)


def test_arena_patches(elf):
    present = {site: pnach_section_at(site) is not None
               for site in (KNIGHT_SITE, REAPER_SITE, LIPSYNC_SITE, CAMERA_SITE, GIANT_SITE, BOMB_SITE)}

    shipped = [knight_step(elf, False, v, c) for v, c in ((3, 1), (3, 0), (2, 1))]
    check('j1', shipped == [(True, True, 0x17), (False, True, None), (False, False, None)],
          'D22 in isolation: a knight whose variant byte (+0x470) is 3 calls the "can use" '
          'virtual of the skill object at 0x41b19c and takes the cast exit when it answers yes; '
          'other variants never ask')
    if present[KNIGHT_SITE]:
        patched = [knight_step(elf, True, v, c) for v, c in ((3, 1), (3, 0), (2, 1))]
        check('j2', patched == [(False, False, None)] * 3,
              'patch "knight never summons": variant 3 no longer asks and never takes the cast '
              'exit from here; other variants are unchanged')
    else:
        skip('j2', 'no patch-file section for 0x2726f4')

    below, at, off_frame = reaper_step(elf, False, 640, 757), reaper_step(elf, False, 640, 756), \
        reaper_step(elf, False, 641, 1056, stale=500)
    check('j3', below == (True, 299) and at == (False, 300) and off_frame == (False, 500),
          'D21 in isolation: on a frame divisible by 64 the count of free pool blocks is taken '
          'again (real pool, %d free) and the reaper body is entered below 300, not at %d; on '
          'other frames the stored count is used, however stale' % (below[1], at[1]))
    if present[REAPER_SITE]:
        empty = reaper_step(elf, True, 640, 1056)
        check('j4', empty == (False, 0) and reaper_step(elf, True, 640, 757) == (False, 299),
              'patch "pool reaper off": the reaper body is not entered with 299 free blocks nor '
              'with %d' % empty[1])
    else:
        skip('j4', 'no patch-file section for 0x14b9cc')

    ready, late = lipsync_step(elf, False, 2, 3), lipsync_step(elf, False, 2, 2)
    check('j5', ready == ('lip-sync', 0x26) and late == ('generic', 3),
          'engine P6 in isolation: when the dialog line number is below the count at 0x83d180 '
          'the speaker\'s animation is started with flags 0x26; otherwise the "talk" loop is '
          'started with flags 3')
    if present[LIPSYNC_SITE]:
        forced = lipsync_step(elf, True, 2, 3)
        check('j6', forced == ('generic', 3) and lipsync_step(elf, True, 2, 2) == ('generic', 3),
              'patch "generic talk animation in cutscenes": the generic path with flags 3 is '
              'taken whether or not the line is ready')
    else:
        skip('j6', 'no patch-file section for 0x196aa0')
    def nudge_after_start(flags):
        """The real anim_start puts one track on an empty speaker, then cut_advance runs."""
        rig = CutRig(elf, tracks=())
        mem = rig.emu.mem
        mem.w8(rig.speaker + 0x119, 4)                       # room for four tracks
        rig.emu.call(ANIM_START, rig.speaker + 0x114, rig.emu.alloc(0x40), flags, fargs=(0.3,))
        stored = mem.u16(rig.speaker + 0x138)
        calls, _ = rig.advance(audio=audio_units_for(0.0, +1.0))
        return stored, AUDIO_POSITION in calls, round(mem.f32(rig.speaker + 0x134), 3)
    with_flag, without = nudge_after_start(0x26), nudge_after_start(3)
    check('j7', with_flag == (0x26, True, 0.1) and without == (3, False, 0.0),
          'chain executed: anim_start stores its flags argument in the new track; cut_advance '
          'then asks for the audio position and nudges the track only for the 0x26 start, never '
          'for the generic one - which is why the patch in j6 also stops the nudge')

    def flags(patched):
        return [camera_step(elf, patched, n, c, m) for n in (0, 1) for c in (0, 1) for m in (1, 2)]
    shipped_flags = flags(False)
    check('j8', shipped_flags == [0, 1, 0, 1, 0, 0, 0, 1],
          'D6 in isolation: the byte 0x4039c1 becomes "camera mode word is not 1" offline and in '
          'a net game during a cutscene, and 0 in a net game outside a cutscene '
          '(offline/net x no cutscene/cutscene x mode 1/2: %s)' % shipped_flags)
    if present[CAMERA_SITE]:
        patched_flags = flags(True)
        check('j9', patched_flags == [0, 1, 0, 1, 0, 0, 0, 0],
              'patch "never judge activity from the camera": in a net game the byte is 0 with or '
              'without a cutscene; offline behaviour is unchanged (%s)' % patched_flags)
    else:
        skip('j9', 'no patch-file section for 0x1e4dd4')

    combos = [(beam, bolt) for beam in (0, 0x77) for bolt in (0, 1)]
    shipped_giant = [giant_step(elf, False, beam, bolt) for beam, bolt in combos]
    check('j10', shipped_giant == [True, True, False, False],
          'D28 in isolation: the conjure exit at 0x250930 is taken when the word at object +0x530 '
          '(the beam handle) is 0, whatever the flag at +0x508 says')
    if present[GIANT_SITE]:
        patched_giant = [giant_step(elf, True, beam, bolt) for beam, bolt in combos]
        check('j11', patched_giant == [True, False, True, False],
              'patch "CloudGiant king conjure test uses a shared flag": the exit now follows the '
              'word at +0x508 and ignores +0x530')
    else:
        skip('j11', 'no patch-file section for 0x250930')

    next_seed = (0x1234 * 0x19660D + 0x3C6EF35F) & M32
    far, near = bomb_step(elf, False, 0), bomb_step(elf, False, 1)
    check('j12', far == (False, [(0x10, 960.0)], 0x1234) and near == (True, [(0x10, 960.0)], next_seed),
          'D29 in isolation: FireBomb_run asks isNearView(position, 960); on "no" it leaves without '
          'touching the shared seed, on "yes" it goes on and draws from it (0x1234 -> 0x%08x)' % near[2])
    if present[BOMB_SITE]:
        forced = bomb_step(elf, True, 0)
        check('j13', forced == (True, [], next_seed),
              'patch "fire bombs ignore the view test": the view test is not called and the seed '
              'is drawn every time')
    else:
        skip('j13', 'no patch-file section for 0x261fd0')


# ---------------------------------------------------------------------------------------
# p. The patch file itself; x. the interpreter against routines whose results are known
# ---------------------------------------------------------------------------------------
def test_patch_file(elf):
    if not os.path.isfile(PNACH):
        skip('p1', 'patches/SLUS-20973_4028A55F.pnach not found')
        return
    emu = EE(elf)
    quoted = pnach_was_words(PNACH)
    for number, (title, entries) in enumerate(ee_emu.parse_pnach(PNACH), 1):
        words = [(addr, value) for addr, size, value in entries if size == 4]
        was = quoted.get(title)
        where = ', '.join('0x%06x' % addr for addr, _ in words)
        if was is None:
            check('p%d' % number, all(emu.mem.is_mapped(addr, 4) and 0x100000 <= addr < 0x3E5C40 for addr, _ in words),
                  '[%s] patches %s, inside the code; its text quotes no original word to compare' % (title, where))
        else:
            actual = [emu.mem.u32(addr) for addr, _ in words]
            check('p%d' % number, actual == was,
                  '[%s] the "was" word(s) quoted for %s are what the executable holds' % (title, where))


STRLEN, STRCMP_FN, MEMCPY, MEMSET, MEMCHR, MEMCMP = 0x3B8DC4, 0x3B8534, 0x3B5F0C, 0x3B60C0, 0x3B5D98, 0x3B5E78
SRAND, RAND, ATOI, SPRINTF, QSORT, ATAN2_16 = 0x3B70D8, 0x3B70F0, 0x3B3550, 0x3B7EF0, 0x3B66E8, 0x166798


def test_cross_check(elf):
    """Not a claim about the game: the executable's own copies of standard routines are run
    and compared with results known independently.  A wrong instruction in the interpreter
    would show here."""
    import math
    import struct
    emu = EE(elf)
    mem = emu.mem
    a, b = emu.alloc(0x400), emu.alloc(0x400)
    rng = random.Random(3)

    def put(addr, text):
        mem.write(addr, text + b'\0')

    ok = True
    for n in (0, 1, 7, 8, 9, 31, 100):
        put(a + 3, b'x' * n)
        ok &= emu.call(STRLEN, a + 3) == n
    for x, y in ((b'abc', b'abc'), (b'abc', b'abd'), (b'abd', b'abc'), (b'', b'a'),
                 (b'longer string here', b'longer string herf')):
        put(a, x)
        put(b + 1, y)
        value = s32(emu.call(STRCMP_FN, a, b + 1))
        ok &= (value > 0) - (value < 0) == (x > y) - (x < y)
    check('x1', ok, 'the executable\'s strlen and strcmp give the right answers for 12 inputs')

    ok = True
    cases = 0
    for src_off in range(9):
        for dst_off in (0, 1, 5):
            for n in (0, 1, 3, 8, 15, 16, 31, 32, 33, 64, 100, 257):
                data = bytes(rng.randrange(256) for _ in range(n))
                mem.write(a, b'\xCC' * 0x300)
                mem.write(b, b'\xDD' * 0x300)
                mem.write(a + src_off, data)
                result = emu.call(MEMCPY, b + 16 + dst_off, a + src_off, n) & M32
                want = b'\xDD' * (16 + dst_off) + data + b'\xDD' * (0x300 - 16 - dst_off - n)
                ok &= mem.read(b, 0x300) == want and result == b + 16 + dst_off
                cases += 1
    for dst_off in range(8):
        for n in (0, 1, 7, 8, 9, 16, 17, 63, 64, 65, 200):
            mem.write(a, b'\xCC' * 0x300)
            emu.call(MEMSET, a + 8 + dst_off, 0x1A5, n)
            ok &= mem.read(a, 0x300) == b'\xCC' * (8 + dst_off) + b'\xA5' * n + b'\xCC' * (0x300 - 8 - dst_off - n)
            cases += 1
    for off in (0, 1, 3):
        for pos in (0, 5, 15, 16, 17, 40, 99):
            data = bytearray(b'a' * 120)
            data[pos] = 0x7A
            mem.write(a + off, bytes(data))
            ok &= emu.call(MEMCHR, a + off, 0x7A, 120) & M32 == a + off + pos
            cases += 1
    put(a, b'hello world, hello')
    put(b, b'hello world, hellp')
    ok &= s32(emu.call(MEMCMP, a, b, 18)) < 0 and s32(emu.call(MEMCMP, a, b, 17)) == 0
    check('x2', ok, 'its memcpy, memset, memchr and memcmp are right for %d combinations of '
          'alignment and length (unaligned and 16-byte paths)' % cases)

    emu.call(SRAND, 12345)
    state, want, got = 12345, [], []
    for _ in range(5):
        got.append(emu.call(RAND) & M32)
        state = (state * 6364136223846793005 + 1) & ee_emu.M64
        want.append((state >> 32) & 0x7FFFFFFF)
    numbers = []
    for text in (b'0', b'42', b'-17', b'  123abc', b'2147483647', b'-2147483648'):
        put(a, text)
        numbers.append(s32(emu.call(ATOI, a)))
    check('x3', got == want and numbers == [0, 42, -17, 123, 2147483647, -2147483648],
          'its rand (a 64-bit multiply) reproduces the generator\'s defining formula for 5 draws, '
          'and atoi parses 6 strings correctly')

    put(b, b'%d|%5d|%x|%s|%c|%u')
    put(b + 0x100, b'str')
    emu.reset_log()
    length = s32(emu.call(SPRINTF, a, b, (-12345) & ee_emu.M64, 42, 0xBEEF, b + 0x100, 0x41, 3000000000))
    text = mem.cstr(a)
    check('x4', text == '-12345|   42|beef|str|A|3000000000' and length == len(text),
          'its sprintf formats six conversions correctly (%d instructions executed)' % emu.steps)

    compare = 0x00090000                         # this script's own four-word compare function
    emu.load_words(compare, [0x8C820000, 0x8CA30000, 0x03E00008, 0x00431023])
    values = [rng.randrange(-1000, 1000) for _ in range(40)]
    mem.write(a, b''.join(struct.pack('<i', v) for v in values))
    emu.call(QSORT, a, len(values), 4, compare)
    result = list(struct.unpack('<40i', mem.read(a, 160)))
    worst = 0.0
    for degrees in range(0, 360, 7):
        y, x = math.sin(math.radians(degrees)) * 3.0, math.cos(math.radians(degrees)) * 3.0
        raw = emu.call(ATAN2_16, fargs=(y, x)) & 0xFFFF
        want_angle = math.atan2(y, x) * 65536 / (2 * math.pi)
        worst = max(worst, abs((raw - want_angle + 32768) % 65536 - 32768))
    check('x5', result == sorted(values) and worst <= 2.0,
          'its qsort sorts 40 integers through a callback, and the engine\'s 16-bit atan2 '
          '0x166798 is within %.1f units of the true angle at 52 angles (floating point path)' % worst)


GROUPS = [
    ('a', 'codec', 'input codec 0x13c450 / 0x13c970', test_codec),
    ('b', 'pad', 'pad_apply 0x174410 and the slew limit', test_pad_apply),
    ('c', 'pool', 'object pool 0x14fdb8 / 0x150470', test_pool),
    ('d', 'pacing', 'pacing block of net_main 0x13354c-0x133608 and the pacing patches', test_pacing),
    ('e', 'alive', 'alive list: game_rebuildAlivePlayers 0x1e72f8, Player_processDamage 0x1b2cc0, Player_clone 0x11e870', test_alive_list),
    ('f', 'cutscene', 'cut_advance 0x199214 and the patch at 0x199448', test_cutscene),
    ('g', 'hash', 'sync record 0x13af44-0x13b138', test_sync_hash),
    ('h', 'signin', 'network sign-in state machine 0x33ed70, state 5', test_signin),
    ('i', 'other', 'other ledger rows', test_other_rows),
    ('j', 'arena', 'diagnostic patches (0x2726f4, 0x14b9cc, 0x196aa0, 0x1e4dd4, 0x250930, 0x261fd0)', test_arena_patches),
    ('p', 'patchfile', 'patch file: quoted original words', test_patch_file),
    ('x', 'crosscheck', 'interpreter cross-check on library routines with known results', test_cross_check),
]


def find_elf(argv):
    for arg in argv:
        if not arg.startswith('-') and os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), os.path.join(ROOT, 'SLUS_209.73'),
                      os.path.join(os.getcwd(), 'SLUS_209.73')):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    global VERBOSE
    argv = sys.argv[1:] if argv is None else list(argv)
    VERBOSE = '-v' in argv
    only = argv[argv.index('-k') + 1].lower() if '-k' in argv and argv.index('-k') + 1 < len(argv) else None
    positional = [a for i, a in enumerate(argv) if not a.startswith('-') and (i == 0 or argv[i - 1] != '-k')]
    elf = find_elf(positional)
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
    print('every result below was executed in isolation: one function or stretch, callees '
          'stubbed, state built by this script')
    for letter, name, title, function in GROUPS:
        if only and only not in (letter, name) and only not in title.lower():
            continue
        print('--- %s. %s' % (letter, title))
        try:
            function(elf)
        except EmuError as exc:
            check(letter + '!', False, 'the interpreter stopped: %s' % exc)
        except (AssertionError, LookupError, StopIteration, ValueError) as exc:
            check(letter + '!', False, 'this script could not finish the group: %r' % (exc,))
    passed = sum(1 for _, ok in RESULTS if ok)
    print('%d checks: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
