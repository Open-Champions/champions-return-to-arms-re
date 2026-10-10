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


def run_log(emu):
    """What the last run did, in a form two machines can be compared by: the calls
    (site, target, first four integer arguments) and the stores outside the stack
    (pc, address, size, value), each in order."""
    return ([(c.site, c.target, tuple(a & M32 for a in c.args[:4])) for c in emu.calls],
            list(emu.writes))


def log_diff(one, other, with_args=True):
    """Where two run logs differ, order ignored: the call targets whose calls are not the
    same multiset in both, and the store addresses whose stores (address, size, value)
    are not.  with_args compares the four argument registers of each call too; that is
    only meaningful when both runs took the same path, because a function with fewer
    arguments leaves whatever the path left in the others."""
    from collections import Counter
    calls = Counter((t, a if with_args else ()) for _site, t, a in one[0])
    calls.subtract(Counter((t, a if with_args else ()) for _site, t, a in other[0]))
    stores = Counter(w[1:] for w in one[1])
    stores.subtract(Counter(w[1:] for w in other[1]))
    return (sorted({t for (t, _a), n in calls.items() if n}),
            sorted({w[0] for w, n in stores.items() if n}))


def hexes(values):
    return ', '.join('0x%x' % v for v in values) if values else 'none'


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
# k. Kill, experience, loot and pick-up (docs/issues/kill-loot-xp.md, FINDINGS K1-K8) and
#    the three patch-file sections that belong to it (0x1a5c0c; 0x1b9fcc + 0x1ba3ac; 0x1d2d30)
# ---------------------------------------------------------------------------------------
INTERACT_GATE, INTERACT_GATE_END, K1_SITE = 0x1A5B98, 0x1A5C28, 0x1A5C0C
PLAYER_INTERACT, WEAPON_SWAP_INPUT, DIALOG_IS_OPEN, NET_GET_CAM_FLAG = 0x1B2640, 0x1BB718, 0x22FBC0, 0x13E110
COLLECT_IN_BOX, G_SELECTOR_HELD, G_MENU_LOCKOUT, G_BTN_USE = 0x14A928, 0x41B818, 0x41B4FC, 0x41B9C0
G_DIALOG_DATA, G_NET_CAM_YAW, G_LOCAL_CAMERA = 0x8E2D60, 0x5D0BC0, 0x4F8450
SELECTOR_SISTER_START, SELECTOR_SISTER_END = 0x1A6DE4, 0x1A6E18
HUD_SPELL_SELECT, MASK_LOCAL_BUTTONS, MEMCARD_IS_BUSY, TASK_IS_RUNNING = 0x1DD270, 0x13E540, 0x217518, 0x19E5E8
SPELL_SELECT_STORED, SPELL_SELECT_RETURNS = 0x1DD508, (0x1DE034, 0x1DE038)
G_RAW_PAD_HELD, G_BTN_ABILITY_A, G_BTN_ABILITY_B, G_MEMCARD_STATE = 0x4028D8, 0x41B990, 0x41B9A0, 0x88D3A0
FAKE_CODE = 0x00090000              # this script's own "return" routines, used as virtual-function targets
RETURN_WORDS = [0x03E00008, 0]      # jr ra / nop


def fake_function(emu, index, function=None, ret=0, name=None):
    """A stub at an address of this script's own, for a virtual-table slot to point at."""
    addr = FAKE_CODE + index * 8
    emu.load_words(addr, RETURN_WORDS)
    emu.stub(addr, ret=ret, function=function, name=name)
    return addr


def player_run_frame(emu, pad):
    """Stack and frame slot for a stretch of Player_run entered part-way: its frame is
    0xe90 bytes and it keeps the pad pointer at sp + 0xe40."""
    sp = emu.stack_hi - 0x2000
    emu.r[29] = sp
    emu.mem.w32(sp + 0xE40, pad)
    return sp


class InteractRig:
    """Player_run from the instruction after its Player_processDamage call (0x1a5b98) to
    the instruction after its Player_interact call (0x1a5c28), entered part-way: $fp is
    the player, $s0 the base register the code addresses the lockout word from, the pad
    pointer is in Player_run's frame slot.  dialog_isOpen, net_getCamFlag and
    Player_interact run for real; the box query hands back one fake interactable object
    whose prompt (virtual slot 13) and interact (slot 14) are stubs of this script;
    Player_weaponSwapInput and what Player_interact calls for text are stubbed."""
    SLOT = 1

    def __init__(self, elf, selector=0, patched=False, network=True, paused=0, lockout=0,
                 dialog=0, cam_flag=0, copy=False, use_pressed=True):
        world = self.world = World(elf, players=2, local_slot=self.SLOT, network=network)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        if patched and apply_section_at(emu, K1_SITE) is None:
            raise LookupError('no patch-file section patches 0x%x' % K1_SITE)
        self.player = world.objects[self.SLOT]
        if copy:
            mem.w32(self.player + 0x0C, 0x20060)
        mem.w32(G_SELECTOR_HELD + 4 * self.SLOT, selector)
        mem.w32(G_PAUSED, paused)
        mem.w32(G_MENU_LOCKOUT, lockout)
        mem.w32(G_DIALOG_DATA, dialog)
        mem.w16(G_NET_CAM_YAW + 2 * self.SLOT, 0x1234 | cam_flag)     # bit 0 is the camera flag
        camera = emu.alloc(0x100)
        mem.w32(camera + 0x34, 2 if cam_flag else 1)                  # offline: mode 1 is "following"
        mem.w32(G_LOCAL_CAMERA, camera)
        self.pad = emu.alloc(0x58)
        mem.w32(G_BTN_USE + 4 * self.SLOT, 0x40)
        mem.w32(self.pad + 0x0C, 0x40 if use_pressed else 0)          # pressed-edge word of the lockstep pad
        thing, vtable = emu.alloc(0x200), emu.alloc(0x100)
        self.thing = thing
        mem.w32(thing + 0x0C, 0x100000)                               # "interactable"
        mem.wf32(thing + 0x10, 110.0)
        mem.wf32(thing + 0x14, 200.0)
        mem.w32(thing + 0x48, vtable)
        self.seen = []

        def prompt(e):
            e.mem.w16(e.r[5] & M32, 0x55)                             # a one-character prompt text
            e.mem.w16((e.r[5] & M32) + 2, 0)
            self.seen.append(('prompt', e.r[4] & M32, e.r[6] & M32))
            return 1
        mem.w32(vtable + 0x04, fake_function(emu, 0, ret=0x1234, name='type info'))
        mem.w32(vtable + 0x6C, fake_function(emu, 1, function=prompt, name='prompt (slot 13)'))
        mem.w32(vtable + 0x74, fake_function(
            emu, 2, function=lambda e: self.seen.append(('interact', e.r[4] & M32, e.r[5] & M32)) or 0,
            name='interact (slot 14)'))

        def collect(e):
            out = e.r[6] & M32
            e.mem.w32(out, thing)
            e.mem.w32(out + 4, 0)
            return 1
        emu.stub(COLLECT_IN_BOX, function=collect, name='world_collectObjectsInBox')
        mem.w32(G_SCRIPT_ACTIVE_PLAYER, 0xFFFFFFFF)

    def run(self):
        emu = self.emu
        player_run_frame(emu, self.pad)
        emu.r[30] = self.player
        emu.r[16] = 0x420000
        emu.follow = {PLAYER_INTERACT, DIALOG_IS_OPEN, NET_GET_CAM_FLAG}
        emu.reset_log()
        emu.run(start=INTERACT_GATE, until={INTERACT_GATE_END}, max_steps=20000)
        emu.follow = None
        return run_log(emu)

    def active_player(self):
        return self.mem.s32(G_SCRIPT_ACTIVE_PLAYER)


def selector_sister_test(elf, network, selector, attack_word=0):
    """Player_run 0x1a6de4-0x1a6e18, the other reader of the selector word: returns the
    "act on the button" register ($s0, 1 on entry) afterwards and whether the word was
    loaded at all."""
    emu = EE(elf)
    player = emu.alloc(0x600)
    emu.mem.w32(player + 0x3C8, 1)
    emu.mem.w32(player + 0x488, attack_word)
    emu.mem.w8(G_NETWORK_MODE, network)
    emu.mem.w32(G_SELECTOR_HELD + 4, selector)
    emu.r[30] = player
    emu.r[16] = 1
    emu.reads = []
    emu.run(start=SELECTOR_SISTER_START, until={SELECTOR_SISTER_END}, max_steps=50)
    return emu.r[16] & M32, any(addr == G_SELECTOR_HELD + 4 for _pc, addr, _n, _v in emu.reads)


def spell_select(elf, local, held, slot=1):
    """hud_spellSelect from its entry to just after its store to the selector word
    (0x1dd508) or to its early return.  held is the held-buttons word of the slot's RAW
    pad.  Returns (reached the store, the selector word afterwards, the arguments of the
    net_maskLocalButtons calls)."""
    world = World(elf, players=2, local_slot=slot if local else 1 - slot, network=True)
    emu, mem = world.emu, world.emu.mem
    camera = emu.alloc(0x100)
    mem.w32(camera + 0x34, 1)
    mem.w32(G_LOCAL_CAMERA, camera)
    mem.w32(G_MEMCARD_STATE, 0xFFFFFFFF)                # no card screen
    mem.w32(G_RAW_PAD_HELD + slot * PAD_SIZE, held)
    mem.w32(G_SELECTOR_HELD + 4 * slot, 0x77)
    for table, bit in ((G_BTN_ABILITY_A, 0x10), (G_BTN_ABILITY_B, 0x20), (G_BTN_USE, 0x40)):
        mem.w32(table + 4 * slot, bit)
    emu.follow = {IS_LOCAL_SLOT, DIALOG_IS_OPEN, MEMCARD_IS_BUSY, MASK_LOCAL_BUTTONS}
    emu.r[4], emu.r[5], emu.r[6], emu.r[7], emu.r[8] = slot, 0, 0, 0, 0
    emu.r[29] = emu.stack_hi - 0x1000
    emu.reset_log()
    emu.run(start=HUD_SPELL_SELECT, until={SPELL_SELECT_STORED} | set(SPELL_SELECT_RETURNS), max_steps=2000)
    masks = [tuple(a & M32 for a in c.args[:3]) for c in emu.calls if c.target == MASK_LOCAL_BUTTONS]
    return emu.pc == SPELL_SELECT_STORED, mem.u32(G_SELECTOR_HELD + 4 * slot), masks


def test_k1_interact(elf):
    slot = InteractRig.SLOT
    logs, seen, active = {}, {}, {}
    for network in (True, False):
        for selector in (0, 1):
            rig = InteractRig(elf, selector=selector, network=network)
            logs[network, selector] = rig.run()
            seen[network, selector], active[network, selector] = rig.seen, rig.active_player()
    targets = {key: [c[1] for c in log[0]] for key, log in logs.items()}
    open_ok = all(PLAYER_INTERACT in targets[n, 0] and [kind for kind, _o, _s in seen[n, 0]] == ['prompt', 'interact']
                  and active[n, 0] == slot for n in (True, False))
    held_ok = all(targets[n, 1] == [DIALOG_IS_OPEN, NET_GET_CAM_FLAG, WEAPON_SWAP_INPUT] and not seen[n, 1]
                  and active[n, 1] == -1 and not logs[n, 1][1] for n in (True, False))
    check('k1', open_ok and held_ok,
          'K1 in isolation (Player_run entered part-way at 0x1a5b98, run to 0x1a5c28, one '
          'interactable object in reach and the use button pressed in the lockstep pad): with the '
          'selector word 0x41b818[slot] at 0 the stretch calls Player_weaponSwapInput and '
          'Player_interact, which asks the object for its prompt, stores the slot in '
          'g_scriptActivePlayer (0x4d8ae4) and calls the object\'s interact; with the word at 1 '
          'and nothing else changed it stops after Player_weaponSwapInput - no prompt, no store '
          'at all, no interact.  Same result in a net game and offline: there is no network test')
    calls_only, stores_only = log_diff(logs[True, 0], logs[True, 1])
    table('K1: what the machine with the selector word set does not do (net game)',
          ['calls: ' + hexes(calls_only), 'stores: ' + hexes(stores_only)])
    check('k2', G_SCRIPT_ACTIVE_PLAYER in stores_only and PLAYER_INTERACT in calls_only
          and FAKE_CODE + 16 in calls_only and logs[True, 1][0] == logs[True, 0][0][:3],
          'the two runs of k1 compared call by call and store by store: up to and including '
          'Player_weaponSwapInput they are identical; everything after is missing on the machine '
          'whose selector word is set - %d calls (Player_interact, the box query, the object\'s '
          'prompt and interact, the prompt text helpers) and %d stores, at %s (the prompt icon '
          'and fade words of the slot, the prompt text buffer, g_scriptActivePlayer)'
          % (len(logs[True, 0][0]) - 3, len(logs[True, 0][1]), hexes(stores_only)))
    sister = [selector_sister_test(elf, n, s) for n in (0, 1) for s in (0, 1)]
    check('k3', sister == [(1, True), (0, True), (1, False), (1, False)],
          'the other reader of the same word in Player_run (0x1a6de8-0x1a6e14) does test the '
          'network mode first: offline a set word cancels the action, in a net game the word is '
          'not loaded at all (offline/net x word 0/1, action kept: %s) - the contrast K1 draws'
          % [kept for kept, _read in sister])
    remote = spell_select(elf, False, 0x1000)
    held = [spell_select(elf, True, bit) for bit in (0x1000, 0x2000, 0x4000, 0x8000)]
    idle = spell_select(elf, True, 0x0F0F)
    check('k4', remote == (False, 0x77, []) and idle == (True, 0, [])
          and all(h == (True, 1, [(slot, 3, 0x70)]) for h in held),
          'the writer, hud_spellSelect 0x1dd270 (entered at its start, run to just after its '
          'store at 0x1dd4ec/0x1dd504): for a slot that is not local it returns at once and '
          'leaves the word alone; for the local slot with any of the four D-pad bits held in '
          'the RAW pad it calls net_maskLocalButtons(slot, 3, abilityA | abilityB | use) and '
          'stores 1; with none held it stores 0.  That it is the ONLY writer is a search result '
          'and was not executed')
    if pnach_section_at(K1_SITE) is None:
        skip('k5', 'the patch file has no section for 0x1a5c0c; the patched runs were not made')
        return
    patched = {}
    for selector in (0, 1):
        rig = InteractRig(elf, selector=selector, patched=True)
        patched[selector] = (rig.run(), rig.seen, rig.active_player())
    check('k5', patched[0] == patched[1] and patched[1][0] == logs[True, 0] and patched[1][2] == slot,
          'patch "use button works with the spell selector open" (0x1a5c0c := no-operation): '
          'the machine with the selector word set now makes exactly the calls and stores of the '
          'machine with it clear - the per-machine difference of k1/k2 is gone, and what the '
          'patched stretch does is what an unpatched machine does for a remote player')
    same = differ = 0
    for bits in range(64):
        state = dict(paused=bits & 1, lockout=(bits >> 1) & 1, dialog=(bits >> 2) & 1,
                     cam_flag=(bits >> 3) & 1, copy=bool(bits & 16), network=bool(bits & 32))
        shipped = InteractRig(elf, selector=0, **state).run()
        for selector in (0, 1):
            if InteractRig(elf, selector=selector, patched=True, **state).run() == shipped:
                same += 1
            else:
                differ += 1
    check('k6', differ == 0 and same == 128,
          'nothing else in the stretch changes with the patch: over all 64 combinations of the '
          'five tests in front of it (pause word, menu lockout, dialog open, camera flag of the '
          'slot, prediction copy) offline and in a net game, the patched stretch with the '
          'selector word 0 or 1 makes the same calls and stores as the shipped stretch with the '
          'word 0 (%d of 128 runs)' % same)


# K2: Player_usePotion 0x1b9cb8 and what the drop message then does (inventory_dropItem 0x1c4310)
INVMSG_SEND_DROP, INVMSG_DISPATCH, INVENTORY_DROP_ITEM, INVENTORY_REMOVE_ITEM = 0x1C59D0, 0x1BFDB0, 0x1C4310, 0x1C1CB0
ITEM_SAME_IDENTITY, PLAYER_COUNT_POTIONS, PLAYER_ITEM_WEIGHT, ITEM_GET_WEIGHT = 0x108924, 0x1BA5F8, 0x1B6338, 0x103E08
PLAYER_RECALC_LOAD, PLAYER_RECALC_STATS, LIBC_STRSTR, SEND_CHARACTER_TO_LOBBY = 0x1BEC10, 0x1B6458, 0x3B96A8, 0x1EB5C8
RES_FIND, SOUND_PLAY_ON_OBJECT = 0x17365C, 0x214230
G_LOCAL_MENU_OPEN, G_ITEM_LIST_CELLS, G_ITEM_DEFS, ITEM_DEF_SIZE = 0x41B69D, 0x4EBBB0, 0x3F7650, 0x40
G_HEAL_POTION_NAMES, G_MANA_POTION_NAMES, G_HUD_POTION_COUNT = 0x4EF478, 0x4EF4A0, 0x41B940
BAG_BASE, BAG_STRIDE, BAG_COUNT, ITEM_SIZE = 0x130, 0x1208, 0x1200, 0x48
CELLS_PER_SLOT, CELLS_PER_BAG = 0x23988, 0xBDD8
K2_SITES = (0x1B9FCC, 0x1BA3AC)
POTION_BUTTONS, POTION_BUTTONS_END, G_BTN_POTION_A, G_BTN_POTION_B = 0x1A5940, 0x1A59F8, 0x41BA10, 0x41BA20


def item_defs(mem):
    """The rows of the executable's own item-definition table (address of each)."""
    row = G_ITEM_DEFS
    while mem.u32(row):
        yield row
        row += ITEM_DEF_SIZE


def find_item_def(mem, name):
    for row in item_defs(mem):
        if mem.cstr(mem.u32(row)) == name:
            return row
    raise LookupError('no item definition named as the potion table says')


def put_item(mem, record, bag, index, definition, count=1):
    """One 0x48-byte item record in a bag of a player record: definition pointer, stack
    count at +4, its own bag index at +0x22.  Returns its address."""
    item = record + BAG_BASE + bag * BAG_STRIDE + index * ITEM_SIZE
    mem.w32(item, definition)
    mem.w16(item + 4, count)
    mem.w16(item + 0x22, index)
    return item


class PotionRig:
    """One machine's copy of a two-player net game in which player slot 0 has 50 of 200
    hit points, 20 of 200 mana and three stacks in bag 2: [0] three of the largest
    healing potion, [1] five of the healing potion Player_usePotion picks for that
    deficit, [2] four of the mana potion it picks.  The definitions are the executable's
    own rows, found through its two potion-name tables.  local: slot 0 is this machine's
    player.  menu_open / list_loaded: g_localMenuOpen and the item-list pointer 0x4ebbb0,
    i.e. this machine's inventory screen is open and has been drawn once; the list copy
    then shows the three stacks in the first three cells of the bag-2 block."""
    COUNTS = (3, 5, 4)

    def __init__(self, elf, local, menu_open=False, list_loaded=False, patched=False):
        world = self.world = World(elf, players=2, local_slot=0 if local else 1, network=True)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        if patched:
            for site in K2_SITES:
                if apply_section_at(emu, site) is None:
                    raise LookupError('no patch-file section patches 0x%x' % site)
        record = self.record = G_PLAYERS
        self.player = world.objects[0]
        if local:
            mem.w32(self.player + 0x0C, 0x200060)
        for offset, value in ((0xAC, 50.0), (0xB0, 200.0), (0xC0, 20.0), (0xC4, 200.0)):
            mem.wf32(record + offset, value)
        heal = [mem.cstr(mem.u32(G_HEAL_POTION_NAMES + 4 * i)) for i in range(9)]
        mana = [mem.cstr(mem.u32(G_MANA_POTION_NAMES + 4 * i)) for i in range(9)]
        names = (heal[8], heal[(200 - 50 + 1) // 60], mana[(200 - 20 + 1) // 60])
        self.items = [put_item(mem, record, 2, index, find_item_def(mem, name), count)
                      for index, (name, count) in enumerate(zip(names, self.COUNTS))]
        mem.w32(record + BAG_BASE + 2 * BAG_STRIDE + BAG_COUNT, len(self.items))
        mem.w8(G_LOCAL_MENU_OPEN, 1 if menu_open else 0)
        below = emu.alloc(CELLS_PER_SLOT * 5)                 # one slot block of room below the list
        self.cells = below + CELLS_PER_SLOT
        self.shown = [self.cells + 2 * CELLS_PER_BAG + column * ITEM_SIZE for column in range(3)]
        if list_loaded:
            mem.w32(G_ITEM_LIST_CELLS, self.cells)
            for cell, item in zip(self.shown, self.items):
                mem.write(cell, mem.read(item, ITEM_SIZE))
        self.messages = []
        emu.stub(SEND_GAME_MSG, function=lambda e: self.messages.append(
            e.mem.read(e.r[5] & M32, e.r[6] & M32)) or 0, name='net_sendGameMsg')
        emu.stub(SEND_CHARACTER_TO_LOBBY, name='game_sendCharacterToLobby')
        self.below_reads = 0

    def counts(self):
        return [self.mem.u16(item + 4) for item in self.items]

    def shown_counts(self):
        return [self.mem.u16(cell + 4) for cell in self.shown]

    def drink(self, kind):
        """The potion-button stretch of Player_run, 0x1a5940-0x1a59f8, entered part-way
        with the button of that kind pressed in the lockstep pad; Player_usePotion and
        the helpers that count and weigh the bag run for real."""
        emu, mem = self.emu, self.mem
        pad = emu.alloc(PAD_SIZE)
        mem.w32(G_BTN_POTION_A, 0x100)
        mem.w32(G_BTN_POTION_B, 0x200)
        mem.w32(pad + 0x0C, 0x100 << kind)
        player_run_frame(emu, pad)
        emu.r[30], emu.r[17] = self.player, 0
        emu.follow = {USE_POTION, IS_LOCAL_SLOT, STRCMP, INVMSG_SEND_DROP, PLAYER_COUNT_POTIONS,
                      PLAYER_ITEM_WEIGHT, ITEM_GET_WEIGHT}
        emu.reset_log()
        emu.run(start=POTION_BUTTONS, until={POTION_BUTTONS_END}, max_steps=200000)
        emu.follow = None
        self.potion_calls = [(c.args[1] & M32, c.args[2] & M32, c.args[3] & M32, s32(c.args[4]))
                             for c in emu.calls if c.target == USE_POTION]
        return run_log(emu)

    def deliver(self, message):
        """The inventory-message handler on this machine: invmsg_dispatch and, for real,
        inventory_dropItem and the helpers it uses to find and count the item."""
        emu = self.emu
        buffer = emu.alloc(0x40)
        self.mem.write(buffer, message)
        emu.follow = {IS_LOCAL_SLOT, INVENTORY_DROP_ITEM, ITEM_SAME_IDENTITY, LIBC_STRSTR, PLAYER_RECALC_LOAD,
                      PLAYER_ITEM_WEIGHT, ITEM_GET_WEIGHT}
        emu.reads = []
        emu.reset_log()
        emu.call(INVMSG_DISPATCH, buffer)
        emu.follow = None
        compares = [addr for pc, addr, _n, _v in emu.reads
                    if ITEM_SAME_IDENTITY <= pc < ITEM_SAME_IDENTITY + 0x44 and addr >= EE.HEAP_LO]
        self.below_reads = (len(compares), min(compares) - self.cells, max(compares) - self.cells) if compares else None
        emu.reads = None
        return run_log(emu)


def test_k2_potion(elf):
    names = {0: 'health', 1: 'mana'}
    picked = {0: 1, 1: 2}                                 # index of the stack each kind should take
    results = {}
    for kind in (0, 1):
        owner_open, owner_closed, other = (PotionRig(elf, True, True, True), PotionRig(elf, True),
                                           PotionRig(elf, False))
        logs = [rig.drink(kind) for rig in (owner_open, owner_closed, other)]
        want = list(PotionRig.COUNTS)
        want[picked[kind]] -= 1
        message = owner_open.messages[0] if owner_open.messages else b''
        pending = [rig.mem.f32(rig.record + (0xB4 if kind == 0 else 0xC8)) for rig in (owner_open, owner_closed, other)]
        calls_diff, stores_diff = log_diff(logs[0], logs[1], with_args=False)
        sound_diff, no_store_diff = log_diff(logs[1], logs[2], with_args=False)
        results[kind] = dict(rigs=(owner_open, owner_closed, other), logs=logs, message=message)
        table('K2 %s potion: owner with inventory open against owner with it closed' % names[kind],
              ['calls that differ: ' + hexes(calls_diff), 'stores that differ: ' + hexes(stores_diff),
               'message: ' + message.hex()])
        check('k%d' % (7 + 2 * kind),
              owner_open.counts() == list(PotionRig.COUNTS) and owner_closed.counts() == want and other.counts() == want
              and message == bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0xFF, 2])
              and all(rig.potion_calls == [(kind, 0, 0, -1)] for rig in (owner_open, owner_closed, other))
              and not owner_closed.messages and not other.messages and pending[0] == pending[1] == pending[2] > 0
              and calls_diff == sorted([SEND_GAME_MSG, IS_LOCAL_SLOT, INVMSG_SEND_DROP])
              and stores_diff == sorted([G_HUD_POTION_COUNT + 16 * kind, owner_open.record + 0x120,
                                         owner_open.items[picked[kind]] + 4])
              and sound_diff == [RES_FIND, SOUND_PLAY_ON_OBJECT] and not no_store_diff,
              'K2 in isolation, %s potion (Player_run entered part-way at its potion-button test '
              '0x1a5940, which calls Player_usePotion(player, kind, 0, 0, -1); three machines with '
              'the same record): the owner\'s machine with its inventory open and '
              'drawn once (g_localMenuOpen and the list pointer 0x4ebbb0 set) adds the same %.0f '
              'points still to be delivered as the others but leaves the bag at %s and queues '
              'inventory message 0 with mode 2 for bag 2, index 0 - the item in the FIRST cell of '
              'its list, not the potion it used; the same machine with the inventory closed, and '
              'a machine that does not own the player, take the potion out directly (%s) and '
              'send nothing.  Apart from the message the only stores that differ are that stack\'s '
              'count, the carried load the function re-sums at its end (record +0x120) and a HUD '
              'potion counter of the slot; the owner-only sound is the one difference between the '
              'last two' % (names[kind], pending[0], owner_open.counts(), other.counts()))
        delivered = [rig.deliver(message) for rig in (owner_open, other)] if message else None
        final = (owner_open.counts(), other.counts())
        both = list(want)
        both[0] -= 1
        only_first = list(PotionRig.COUNTS)
        only_first[0] -= 1
        check('k%d' % (8 + 2 * kind), delivered is not None and final == (only_first, both)
              and INVENTORY_REMOVE_ITEM not in [c[1] for log in delivered for c in log[0]],
              'the same chain carried on: the queued message handed to invmsg_dispatch on the '
              'owner\'s machine and on the other machine (inventory_dropItem and its item helpers '
              'run for real; the transport in between is not executed).  Mode 2 makes no sound '
              'and no dropped object and takes ONE item off the addressed stack on both.  Bag 2 '
              'ends as %s on the owner\'s machine and %s on the other: the other machine has paid '
              'for the %s potion twice (the potion and a first-cell item), the owner once (the '
              'first-cell item) - the records disagree by one potion, as K2 says'
              % (final[0], final[1], names[kind]))
    owner_open = results[0]['rigs'][0]
    count, low, high = owner_open.below_reads or (0, 0, 0)
    check('k11', count == 2 * 675 and -CELLS_PER_BAG <= low and high < 0 and owner_open.shown_counts() == list(PotionRig.COUNTS),
          'K2 adds (executed, not in the row): the message carries the -1 that Player_run '
          'passed as the last argument, and inventory_dropItem uses it as the panel index of '
          'this machine\'s list copy.  On the owner\'s machine it therefore compares the item '
          'with 675 cells in the 0x%x bytes just BELOW the list buffer (offsets %s0x%x to %s0x%x '
          'from its start) and with none inside it, so the open screen keeps showing %s.  What '
          'lies below the buffer in a running game is Unknown; here it was zero and nothing '
          'matched' % (CELLS_PER_BAG, '-' if low < 0 else '', abs(low), '-' if high < 0 else '', abs(high),
                       owner_open.shown_counts()))
    partial = []
    for local, menu_open, list_loaded in ((True, True, False), (True, False, True), (False, True, True)):
        rig = PotionRig(elf, local, menu_open, list_loaded)
        rig.drink(0)
        partial.append((rig.counts()[1], len(rig.messages)))
    check('k12', partial == [(4, 0)] * 3,
          'the message branch needs all three at once: menu open but list pointer still 0, list '
          'loaded but menu closed, and menu open with a list on a machine that does not own the '
          'slot each take the potion out directly and send nothing')
    if any(pnach_section_at(site) is None for site in K2_SITES):
        skip('k13', 'the patch file has no section for 0x1b9fcc / 0x1ba3ac; the patched runs were not made')
        return
    ok, finals = True, []
    for kind in (0, 1):
        shipped_logs = results[kind]['logs']
        rigs = (PotionRig(elf, True, True, True, patched=True), PotionRig(elf, True, patched=True),
                PotionRig(elf, False, patched=True))
        logs = [rig.drink(kind) for rig in rigs]
        ok &= logs[0] == shipped_logs[1] and logs[1] == shipped_logs[1] and logs[2] == shipped_logs[2]
        ok &= not any(rig.messages for rig in rigs) and rigs[0].shown_counts() == list(PotionRig.COUNTS)
        finals.append([rig.counts() for rig in rigs])
    check('k13', ok and all(f[0] == f[1] == f[2] for f in finals),
          'patch "potions always leave the bag directly" (both words): the owner\'s machine with '
          'its inventory open now makes, call for call and store for store, the run of the shipped '
          'function with the inventory closed - no message, bag 2 %s after the health potion and '
          '%s after the mana potion on all three machines.  With the inventory closed, and on a '
          'machine that does not own the player, the patched run is identical to the shipped '
          'one.  The list copy on the open screen is not touched (it still shows %s), which is '
          'the cosmetic cost the patch text states' % (finals[0][0], finals[1][0], list(PotionRig.COUNTS)))



# K3: the damage lines of the stats page, stats_screen 0x1d1db8, stretch 0x1d2c20-0x1d2d80
STATS_DAMAGE_START, STATS_DAMAGE_STOPS, K3_SITE = 0x1D2C20, (0x1D2D80, 0x1D2D84, 0x1D2D88), 0x1D2D30
RECALC_DAMAGE, ITEM_DAMAGE_RANGE, ITEM_UNIT_MULT, ITEM_FIELD_1A, GET_SKILL_RANK = 0x1B7158, 0x104100, 0x1046B4, 0x103F88, 0x1BF330
STATS_DRAW_HELPERS = (0x173C84, 0x1D19C8, 0x19EA78, 0x181BF8, 0x181C10, 0x181AF8)     # text look-up, measure, draw
RECORD_ATTACK, RECORD_DAMAGE_MIN, RECORD_DAMAGE_MAX = 0xCC, 0xD0, 0xD4
RECORD_HAND_A, RECORD_HAND_B, RECORD_SET_WEAPON, RECORD_SECOND_WEAPON, RECORD_ACTIVE_SET = 0x43F0, 0x43F4, 0x4434, 0x443C, 0x4A7C
RECORD_SKILL_LIST = 0x4B08


class StatsRig:
    """A player record with two one-handed weapons whose damage ranges differ (the first
    two such rows of the executable's item table), level 10, strength 40, dexterity 30
    and no skills.  tick() is Player_weaponSwapInput, which ends in the per-tick
    Player_recalcDamage; page() is the stretch of stats_screen that prints the attack and
    damage lines, entered part-way with $s6 the record and the frame slot the function
    keeps record + 4 in.  Player_recalcDamage, the item helpers under it and the C
    library's sprintf/strcat run for real; the text look-up and draw helpers are stubs."""

    def __init__(self, elf, second_weapon=True, active_set=0, patched=False):
        world = self.world = World(elf, players=2, local_slot=0, network=True)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        if patched and apply_section_at(emu, K3_SITE) is None:
            raise LookupError('no patch-file section patches 0x%x' % K3_SITE)
        record = self.record = G_PLAYERS
        self.player = world.objects[0]
        plain = [row for row in item_defs(mem)
                 if mem.u8(row + 0x1D) == 0 and mem.u8(row + 0x1E) == 0 and mem.u32(row + 0x20) == 1
                 and mem.s16(row + 0x10) > 0]
        first = plain[0]
        other = next(row for row in plain if mem.read(row + 0x0E, 4) != mem.read(first + 0x0E, 4))
        self.weapons = [put_item(mem, record, 0, index, row) for index, row in enumerate((first, other))]
        mem.w32(record + BAG_BASE + BAG_COUNT, 2)
        mem.w32(record + RECORD_SET_WEAPON, self.weapons[0])
        mem.w32(record + RECORD_SET_WEAPON + 4, self.weapons[0])
        mem.w32(record + RECORD_HAND_A, self.weapons[0])
        if second_weapon:
            mem.w32(record + RECORD_SECOND_WEAPON, self.weapons[1])
            mem.w32(record + RECORD_HAND_B, self.weapons[1])
        mem.w8(record + RECORD_ACTIVE_SET, active_set)
        mem.w16(record + RECORD_SKILL_LIST, 0xFFFF)          # an empty (id, rank) list
        mem.w8(record + 0x58, 10)
        mem.w32(record + 0x90, 40)
        mem.w32(record + 0x98, 30)
        self.text = emu.alloc(0x100)
        self.recalc_calls = []

    def stored(self):
        return tuple(self.mem.s32(self.record + offset) for offset in (RECORD_ATTACK, RECORD_DAMAGE_MIN, RECORD_DAMAGE_MAX))

    def _note_calls(self):
        self.recalc_calls = [(c.args[1] & M32, c.args[2] & M32) for c in self.emu.calls if c.target == RECALC_DAMAGE]

    def tick(self):
        emu = self.emu
        emu.follow = {RECALC_DAMAGE, ITEM_DAMAGE_RANGE, ITEM_UNIT_MULT, ITEM_FIELD_1A, GET_SKILL_RANK}
        emu.reset_log()
        emu.call(WEAPON_SWAP_INPUT, self.player, emu.alloc(PAD_SIZE), 0)
        emu.follow = None
        self._note_calls()
        return self.stored()

    def page(self):
        emu, mem = self.emu, self.mem
        for helper in STATS_DRAW_HELPERS:
            emu.stub(helper)
        sp = emu.stack_hi - 0x1000
        emu.r[29] = sp
        mem.w32(sp + 0x228, self.record + 4)
        emu.r[22], emu.r[21], emu.r[16], emu.r[17] = self.record, self.text, emu.alloc(0x200), emu.alloc(0x10)
        emu.r[20], emu.r[23] = 100, 0
        emu.follow = None
        emu.reset_log()
        emu.run(start=STATS_DAMAGE_START, until=set(STATS_DAMAGE_STOPS), max_steps=200000)
        self._note_calls()
        return run_log(emu), mem.cstr(self.text)


def test_k3_stats(elf):
    probe = StatsRig(elf)
    primary, offhand = probe.weapons
    values = {}
    for item in probe.weapons:
        probe.emu.call(RECALC_DAMAGE, probe.player, item, 1)
        values[item] = probe.stored()
    with_page, without_page = StatsRig(elf), StatsRig(elf)
    ticked = (with_page.tick(), without_page.tick())
    tick_calls = with_page.recalc_calls
    shipped_log, text = with_page.page()
    page_calls = with_page.recalc_calls
    check('k14', values[primary] != values[offhand] and ticked == (values[primary], values[primary])
          and tick_calls == [(primary, 1)] and page_calls == [(primary, 1), (offhand, 1)]
          and with_page.stored() == values[offhand] and without_page.stored() == values[primary]
          and text == '%d-%d/%d-%d' % (values[primary][1:] + values[offhand][1:]),
          'K3 in isolation: after the per-tick recompute (Player_weaponSwapInput, which ends in '
          'Player_recalcDamage(player, primary weapon, 1)) two machines hold the same attack '
          'rating and damage range in the record, %s.  The machine that then draws the stats '
          'page for a player with a second weapon and set 0 active (stats_screen entered '
          'part-way at 0x1d2c20, run to 0x1d2d80) calls Player_recalcDamage twice - with the '
          'tick\'s arguments, then with the second weapon - prints "%s" and is left with %s in '
          'record +0xcc/+0xd0/+0xd4; the machine that does not draw the page still has %s'
          % (list(ticked[0]), text, list(with_page.stored()), list(without_page.stored())))
    no_second, set_one = StatsRig(elf, second_weapon=False), StatsRig(elf, active_set=1)
    single = [(rig.page(), rig.recalc_calls, rig.stored()) for rig in (no_second, set_one)]
    check('k15', all(calls == [(primary, 1)] and stored == values[primary] for _log, calls, stored in single),
          'the second call is made only for a second weapon with set 0 active: with no second '
          'weapon, or with set 1 active, the page makes the one call a tick makes and leaves '
          'the tick\'s values in the record')
    if pnach_section_at(K3_SITE) is None:
        skip('k16', 'the patch file has no section for 0x1d2d30; the patched runs were not made')
        return
    patched = StatsRig(elf, patched=True)
    patched.tick()
    patched_log, patched_text = patched.page()
    inner = len([c for c in shipped_log[0] if c[1] in (RECALC_DAMAGE, ITEM_DAMAGE_RANGE, ITEM_UNIT_MULT, ITEM_FIELD_1A, GET_SKILL_RANK)]) // 2
    removed, changed = log_diff(shipped_log, patched_log, with_args=False)
    text_only = all(patched.text <= addr < patched.text + 0x100
                    or patched.record + RECORD_ATTACK <= addr <= patched.record + RECORD_DAMAGE_MAX for addr in changed)
    unchanged = [(StatsRig(elf, second_weapon=False, patched=True).page(), single[0][0]),
                 (StatsRig(elf, active_set=1, patched=True).page(), single[1][0])]
    check('k16', patched.recalc_calls == [(primary, 1)] and patched.stored() == values[primary] == without_page.stored()
          and patched_text == '%d-%d/%d-%d' % (values[primary][1:] * 2)
          and removed == sorted([ITEM_DAMAGE_RANGE, ITEM_UNIT_MULT, ITEM_FIELD_1A, RECALC_DAMAGE, GET_SKILL_RANK])
          and len(shipped_log[0]) - len(patched_log[0]) == inner and text_only
          and all(got == want for got, want in unchanged),
          'patch "stats page does not rewrite stored weapon damage" (0x1d2d30 := no-operation): '
          'the same stretch makes one Player_recalcDamage call instead of two - the %d calls '
          'that disappear are the second one and the item and skill look-ups inside it - leaves '
          '%s in the record, which is what the machine without the page has, and prints "%s": '
          'the second range repeats the first, as the patch text says.  The only stores that '
          'change are the record\'s three fields and the printed text; for a player with no '
          'second weapon or with set 1 active the patched run is identical to the shipped one'
          % (inner, list(patched.stored()), patched_text))



# K5-K8: the rows that are not about a patch
LANDING_START, LANDING_END, FALLOUT_START, FALLOUT_STOPS = 0x156C0C, 0x156D08, 0x156D10, (0x156D74, 0x156D78)
ITEMPROP_CTOR3, OBJ_DELETE = 0x1592BC, 0x14F200
XP_START, XP_STOPS, GIVE_EXP, LIFETAP_FRACTION, LIBM_POWF = 0x111E3C, (0x112490, 0x112494), 0x1D3150, 0x2F8E78, 0x3A5AC8
G_EXP_TABLE, G_LIFETAP_SKILL, RODATA_LO, RODATA_HI, LIBRARY_CODE_LO = 0x41B558, 0x41B25C, 0x520000, 0x564000, 0x3A0000
LOOT_GENERATE, SOFT_DOUBLE = 0x100D54, (0x3AEF58, 0x3AF468, 0x3AF4D0, 0x3AF9B8, 0x3AFA08, 0x3AFB90)
G_COSMETIC_SEED, G_FOURTH_SEED, G_PVP_MODE_A, G_PVP_MODE_B = 0x404460, 0x404468, 0x4F711C, 0x4F7120
G_LEVEL_MONSTER_LEVEL, G_LOOT_QUALITY_ROWS = 0x4F714C, 0x3E9C18
GOLD_ON_TOUCH, ADD_GOLD_FLOATER, MENU_OPEN_INVENTORY, HUD_SHOW_MESSAGE = 0x157A9C, 0x1DC268, 0x1C15C8, 0x1D92A0
HORSEMEN_SET_STATE, FIND_OBJECT_BY_NAME, CREATURE_DROP_LOOT = 0x272F4C, 0x14F498, 0x10F2C8


def landing_conversion(elf, pool_full, real_pool=False):
    """PhProp_run 0x156c0c-0x156d08, the block that turns a flying item that has come to
    rest into a resting prop; $s1 is the flying object.  Returns (the constructor was
    called with the pool block, the objects passed to obj_delete)."""
    emu = EE(elf)
    prop = emu.alloc(0x300)
    emu.mem.w8(prop + 0x238, 1)                         # it carries an item record
    block = emu.alloc(0x200)
    if real_pool:
        emu.stub(POOL_PRINT_HEAP, name='pool_printHeap')
        emu.call(POOL_INIT)
        while pool_full and emu.call(POOL_NEW, 0x100):
            pass
    else:
        emu.stub(POOL_NEW, ret=0 if pool_full else block, name='pool_new')
    emu.r[17], emu.r[16] = prop, prop + 0x110
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = {POOL_NEW} if real_pool else set()
    emu.reset_log()
    emu.run(start=LANDING_START, until={LANDING_END}, max_steps=5000)
    built = [c.args[0] & M32 for c in emu.calls if c.target == ITEMPROP_CTOR3]
    deleted = [c.args[0] & M32 for c in emu.calls if c.target == OBJ_DELETE]
    asked = [c.args[0] & M32 for c in emu.calls if c.target == POOL_NEW]
    return asked == [0x190], len(built), deleted == [prop]


def fallout(elf, first_alive, heights, prop_height):
    """PhProp_run 0x156d10 on: is the flying object deleted for being 120 below the
    first listed alive player?"""
    world = World(elf, players=len(heights), network=True)
    emu, mem = world.emu, world.emu.mem
    for slot, height in enumerate(heights):
        mem.wf32(world.objects[slot] + 0x18, height)
    mem.w32(G_ALIVE_COUNT, len(heights))
    mem.w32(G_ALIVE_LIST, first_alive)
    prop = emu.alloc(0x300)
    mem.wf32(prop + 0x18, prop_height)
    emu.r[17] = prop
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = set()
    emu.reset_log()
    emu.run(start=FALLOUT_START, until=set(FALLOUT_STOPS), max_steps=200)
    return any(c.target == OBJ_DELETE for c in emu.calls)


def xp_model(exp_value, levels, hit_points, killer, table):
    """The experience each player is given, as docs/issues/kill-loot-xp.md section 2
    states it (steps 5, 8 and 9); this script's arithmetic, not the game's."""
    base = int(int((exp_value / sum(levels)) ** 1.4) * 0.75)
    out = []
    for slot, level in enumerate(levels):
        cap = table[level + 1] - table[level] if level < 0x50 else table[level]
        if len(levels) == 1:
            if hit_points[slot] > 0:
                out.append((slot, min(base, cap)))
            continue
        share = 0.5 if killer is None else (0.6 if slot == killer else 0.4)
        amount = int(base * share)
        if hit_points[slot] <= 0:
            amount = int(amount * 0.5)
        out.append((slot, min(amount, cap)))
    return out


def xp_split(elf, levels, hit_points, classes, killer, exp_value=5000.0, local=0, extra=None):
    """Creature_processDamage 0x111e3c to its exit: the experience block for a creature
    whose last-attacker handle names player `killer` (None: nobody).  powf, the skill-rank
    look-up and the creature's own generator run for real; player_giveExp is a stub that
    records its arguments and the life-tap fraction is stubbed to 0 (no orb)."""
    world = World(elf, players=len(levels), local_slot=local, network=True)
    emu, mem = world.emu, world.emu.mem
    for addr, value in (extra or {}).items():
        mem.w32(addr, value)
    mob = emu.alloc(0x600)
    mem.wf32(mob + 0xD8, exp_value)
    mem.wf32(mob + 0x22C, 900.0)                        # its maximum hit points
    mem.w32(mob + 0x44, 0x1234)
    for slot in range(len(levels)):
        record = G_PLAYERS + slot * PLAYER_STRIDE
        mem.w8(record + 0x59, levels[slot])
        mem.wf32(record + PLAYER_HP, hit_points[slot])
        mem.w32(record + 0x50, classes[slot])
        mem.wf32(record + 0xC0, 10.0)
        mem.wf32(record + 0xC4, 100.0)
        mem.w16(record + RECORD_SKILL_LIST, 0xFFFF)
    if killer is not None:
        node = emu.alloc(0x20)
        mem.w32(node + 0x0C, world.objects[killer])
        mem.w32(mob + 0x2E4, node)
    given = []
    emu.stub(GIVE_EXP, function=lambda e: given.append((s32(e.r[4]), s32(e.r[5]))) or 0, name='player_giveExp')
    emu.stub(LIFETAP_FRACTION, function=lambda e: e.fset(0, 0.0), ret=None, name='SkillLifeTap_getStat0Fraction')
    emu.r[18] = mob
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = None
    emu.reads = []
    emu.reset_log()
    emu.run(start=XP_START, until=set(XP_STOPS), max_steps=100000)
    globals_read = {addr for pc, addr, _n, _v in emu.reads
                    if addr < EE.HEAP_LO and not RODATA_LO <= addr < RODATA_HI and pc < LIBRARY_CODE_LO}
    table = [mem.s32(G_EXP_TABLE + 4 * i) for i in range(0x52)]
    mana = [round(mem.f32(G_PLAYERS + slot * PLAYER_STRIDE + 0xC0), 3) for slot in range(len(levels))]
    stores = sorted({addr for _pc, addr, _n, _v in emu.writes})
    return given, mana, globals_read, table, stores


def loot_rolls(elf, seed, local=0, extra=None):
    """loot_generateDrops 0x100d54 with the arguments a knight's death passes, every
    callee stubbed except the software double arithmetic (so no item or gold object is
    built and the generators' own draws are not made).  Returns (stores to the shared
    seed, other global stores, globals read, the two other seeds afterwards)."""
    world = World(elf, players=2, local_slot=local, network=True)
    emu, mem = world.emu, world.emu.mem
    for addr, value in (extra or {}).items():
        mem.w32(addr, value)
    mem.w32(G_RAND_SEED, seed)
    mem.w32(G_COSMETIC_SEED, 0x1111)
    mem.w32(G_FOURTH_SEED, 0x2222)
    emu.follow = set(SOFT_DOUBLE)
    emu.reads = []
    emu.reset_log()
    emu.call(LOOT_GENERATE, emu.alloc(0x10), 0x1000, 0, 0, fargs=(36.0, 2.0, 1.8, 0.6, 2.0, 0.25))
    draws = sum(1 for _pc, addr, _n, _v in emu.writes if addr == G_RAND_SEED)
    others = sorted({addr for _pc, addr, _n, _v in emu.writes if addr != G_RAND_SEED})
    read = {addr for pc, addr, _n, _v in emu.reads
            if addr < EE.HEAP_LO and not RODATA_LO <= addr < RODATA_HI and pc < LIBRARY_CODE_LO}
    return draws, others, read, (mem.u32(G_COSMETIC_SEED), mem.u32(G_FOURTH_SEED)), mem.u32(G_RAND_SEED)


def gold_touch(elf, toucher_flags=0x60, countdown=0, amount=250, local=0):
    world = World(elf, players=2, local_slot=local, network=True)
    emu, mem = world.emu, world.emu.mem
    gold = emu.alloc(0x100)
    mem.w8(gold + 0x4C, countdown)
    mem.w32(gold + 0x80, amount)
    toucher = world.objects[1]
    mem.w32(toucher + 0x0C, toucher_flags)
    emu.follow = set()
    emu.reset_log()
    emu.call(GOLD_ON_TOUCH, gold, toucher)
    floaters = [(c.args[0] & M32, c.args[2] & M32) for c in emu.calls if c.target == ADD_GOLD_FLOATER]
    return ([c.target for c in emu.calls], floaters, mem.u32(gold + 0x80),
            sorted({addr - gold for _pc, addr, _n, _v in emu.writes}))


def level_up(elf, local, level=5):
    """player_giveExp(0, 20) on a record 10 points short of its next level.  Returns the
    record fields afterwards, the stores (address, size, value) and the calls."""
    world = World(elf, players=2, local_slot=0 if local else 1, network=True)
    emu, mem = world.emu, world.emu.mem
    record = G_PLAYERS
    mem.w8(record + 0x58, level)
    mem.w8(record + 0x59, level)
    mem.w32(record + 0x5C, mem.u32(G_EXP_TABLE + 4 * level) - 10)
    mem.w32(record + 0xE8, 7)
    mem.w8(record + 0xEC, 2)
    for offset, value in ((PLAYER_HP, 40.0), (0xB0, 120.0), (0xC0, 5.0), (0xC4, 80.0)):
        mem.wf32(record + offset, value)
    emu.follow = {IS_LOCAL_SLOT}
    emu.reset_log()
    emu.call(GIVE_EXP, 0, 20)
    emu.follow = None
    fields = dict(ack=mem.u8(record + 0x58), level=mem.u8(record + 0x59), skill=mem.u32(record + 0xE8),
                  stat=mem.u8(record + 0xEC), hp=mem.f32(record + PLAYER_HP), mana=mem.f32(record + 0xC0))
    return world, fields, [w[1:] for w in emu.writes], [c.target for c in emu.calls]


def open_level_up_screen(world):
    """menu_openInventory(0, 1) on this machine; returns the inventory messages queued."""
    emu = world.emu
    sent = []
    emu.stub(SEND_GAME_MSG, function=lambda e: sent.append(e.mem.read(e.r[5] & M32, e.r[6] & M32)) or 0,
             name='net_sendGameMsg')
    emu.follow = {IS_LOCAL_SLOT}
    emu.reset_log()
    emu.call(MENU_OPEN_INVENTORY, 0, 1)
    emu.follow = None
    return sent, len(emu.writes), emu.mem.u8(G_LOCAL_MENU_OPEN)


def knight_dies(elf, variant, found_flags=0x20):
    """Horsemen_setState(knight, 0x14) with every callee stubbed.  Returns what it did
    with the skeleton look-up, the loot call and the two weapon-helper calls."""
    emu = EE(elf)
    mem = emu.mem
    knight, helper, skeleton = emu.alloc(0x600), emu.alloc(0x40), emu.alloc(0x100)
    tables = [emu.alloc(0x100) for _ in range(3)]
    events = []
    mem.w32(knight + 0x0C, 0x20)
    mem.w8(knight + 0x470, variant)
    mem.w32(knight + 0x24, emu.alloc(0x100))            # its animation table
    mem.w32(knight + 0x48, tables[0])
    mem.w32(knight + 0x50, helper)
    mem.w32(helper, tables[1])
    mem.w32(skeleton + 0x0C, found_flags)
    mem.w32(skeleton + 0x48, tables[2])
    mem.w32(tables[0] + 0xE4, fake_function(emu, 0, name='own slot 28', function=lambda e: events.append(
        ('on death', e.r[4] & M32, e.r[5] & M32)) or 0))
    mem.w32(tables[1] + 0x5C, fake_function(emu, 1, name='weapon helper slot 11', function=lambda e: events.append(
        ('drop part', e.r[5] & M32, e.r[6] & M32)) or 0))
    mem.w32(tables[2] + 0xDC, fake_function(emu, 2, name='skeleton slot 27', function=lambda e: events.append(
        ('skeleton state', e.r[4] & M32, e.r[5] & M32)) or 0))
    emu.stub(FIND_OBJECT_BY_NAME, name='world_findObjectByName', function=lambda e: events.append(
        ('find', e.mem.cstr(e.r[4] & M32))) or skeleton)
    emu.stub(CREATURE_DROP_LOOT, name='Creature_dropLoot', function=lambda e: events.append(
        ('loot', e.r[4] & M32, tuple(round(e.fget(i), 2) for i in range(12, 18)))) or 0)
    emu.follow = set()
    emu.call(HORSEMEN_SET_STATE, knight, 0x14)
    return events, knight, skeleton, bool(mem.u64(knight + 0xA8) & (1 << 41))


def test_k5_to_k8(elf):
    stub_full, stub_room, real_full = landing_conversion(elf, True), landing_conversion(elf, False), \
        landing_conversion(elf, True, real_pool=True)
    check('k17', stub_room == (True, 1, True) and stub_full == (True, 0, True) and real_full == (True, 0, True),
          'K5 in isolation (PhProp_run entered part-way at 0x156c0c, the landing conversion of a '
          'flying item): it asks pool_new for 0x190 bytes; with a block it calls ItemProp_ctor3 '
          'and then obj_delete on the flying object; with no block - pool_new stubbed to 0, and '
          'again with the real allocator after all 1056 blocks were taken - it skips the '
          'constructor and still deletes the flying object.  A machine whose pool is full at '
          'that moment loses the item; a machine with one block free keeps it')
    drops = [fallout(elf, first, (0.0, 400.0), 250.0) for first in (0, 1)]
    edge = [fallout(elf, 0, (0.0, 400.0), height) for height in (-119.0, -121.0)]
    check('k18', drops == [False, True] and edge == [False, True],
          'K5, second half (0x156d10 on): a flying object is deleted when its height + 120 is '
          'below the height of the player in the FIRST alive-list slot (120.0 is the constant; '
          '-119 stays, -121 goes).  With players at heights 0 and 400 and the object at 250, a '
          'machine whose list starts with slot 0 keeps it and one whose list starts with slot 1 '
          'deletes it: the list is the only per-machine input (G19)')

    cases = (([10, 12], [50.0, 60.0], [1, 0], 0), ([10, 12], [50.0, 0.0], [1, 0], 1),
             ([10, 12], [50.0, 60.0], [1, 0], None), ([10], [50.0], [0], 0), ([10], [0.0], [0], 0))
    ok, rows, reads, stores = True, [], set(), set()
    for levels, hit_points, classes, killer in cases:
        given, mana, globals_read, levels_table, written = xp_split(elf, levels, hit_points, classes, killer)
        want = xp_model(5000.0, levels, hit_points, killer, levels_table)
        bonus = [round(10.0 + 900.0 * raw_to_float(0x3D088888), 3) if classes[slot] == 0 and (
            (len(levels) == 1 and hit_points[slot] > 0) or (len(levels) > 1 and slot == killer)) else 10.0
            for slot in range(len(levels))]
        ok &= given == want and mana == bonus
        reads |= globals_read
        stores |= set(written)
        rows.append('levels %s hp %s killer %s: given %s, mana %s' % (levels, hit_points, killer, given, mana))
    capped, _m, _g, levels_table, _w = xp_split(elf, [1], [50.0], [1], 0, exp_value=500000.0)
    table('experience block of Creature_processDamage', rows)
    allowed = ({G_NUM_PLAYERS, G_LIFETAP_SKILL} | set(range(G_EXP_TABLE, G_EXP_TABLE + 0x148))
               | set(range(G_PLAYERS, G_PLAYERS + 4 * PLAYER_STRIDE)))
    record_offsets = sorted({(addr - G_PLAYERS) % PLAYER_STRIDE for addr in reads if G_PLAYERS <= addr})
    elsewhere = xp_split(elf, [10, 12], [50.0, 60.0], [1, 0], 0, local=1,
                         extra={G_ALIVE_COUNT: 1, G_ALIVE_LIST: 1, G_SELECTOR_HELD: 1, 0x44FDC0: 1, 0x44FCF8: 1})
    here = xp_split(elf, [10, 12], [50.0, 60.0], [1, 0], 0)
    check('k19', ok and capped == [(0, levels_table[2] - levels_table[1])] and reads <= allowed
          and record_offsets == [0x50, 0x59, PLAYER_HP, 0xC0, 0xC4, PLAYER_OBJ, RECORD_SKILL_LIST]
          and elsewhere[:2] == here[:2]
          and {(addr - G_PLAYERS) % PLAYER_STRIDE for addr in stores if addr < EE.HEAP_LO} == {0xC0},
          'K6, experience (Creature_processDamage entered part-way at 0x111e3c; powf and the '
          'skill look-up real, player_giveExp recorded): the amounts are those of '
          'kill-loot-xp.md section 2 in six cases - int(int(pow(expValue / sum of levels, 1.4)) '
          'x 0.75), 0.6 / 0.4 / 0.5 shares, half for a player at 0 hit points, capped at the '
          'level step, mana = monster max hp / 30 for a class-0 killer.  The stretch reads no '
          'global but g_numPlayers, the level table, the life-tap skill pointer and record '
          'fields +0x50 (class), +0x59 (level), +0xac (hit points), +0xc0/+0xc4 (mana), the '
          'object pointer and the skill list, and its only store outside the creature is record '
          'mana; a machine with another local slot, alive list, selector word and options gives '
          'the same amounts')
    draws, wrote, read, seeds = [], set(), set(), set()
    quality_rows = set(range(G_LOOT_QUALITY_ROWS, G_LOOT_QUALITY_ROWS + 12 * 12))
    for seed in range(1, 41):
        count, others, globals_read, other_seeds, _after = loot_rolls(elf, seed * 0x9E3779B1 & M32)
        draws.append(count)
        wrote |= set(others)
        read |= globals_read
        seeds.add(other_seeds)
    twin = [loot_rolls(elf, 0x51ED270B, local=local, extra=extra)[::4] for local, extra in (
        (0, None), (1, {G_ALIVE_COUNT: 1, G_ALIVE_LIST: 1, G_SELECTOR_HELD: 1, 0x44FDC0: 1, 0x44FCF8: 1}))]
    table('loot_generateDrops, 40 seeds', ['draws per call: %d to %d' % (min(draws), max(draws)),
                                           'globals read: ' + hexes(sorted(read))])
    check('k20', not wrote and seeds == {(0x1111, 0x2222)} and min(draws) >= 5 and len(set(draws)) > 1
          and read <= {G_RAND_SEED, G_NUM_PLAYERS, G_PVP_MODE_A, G_PVP_MODE_B, G_LEVEL_MONSTER_LEVEL} | quality_rows
          and twin[0] == twin[1],
          'K6, loot rolls (loot_generateDrops called with a knight\'s arguments on 40 seeds; item '
          'and gold constructors and the item generators are stubs, so only the roll logic of '
          'this one function ran): every store to a global is to the shared seed 0x404464 (%d '
          'to %d draws per call), the cosmetic seed and the fourth generator are not touched, '
          'and the globals it reads are the shared seed, g_numPlayers, the two PvP flags, the '
          'level\'s monster level 0x4f714c and the quality table 0x3e9c18.  A machine with another '
          'local slot, alive list, selector word and options draws the same.  The generators it '
          'calls, where the row says the remaining draws are, were NOT run'
          % (min(draws), max(draws)))
    plain, copy, early, empty = gold_touch(elf), gold_touch(elf, toucher_flags=0x20060), \
        gold_touch(elf, countdown=5), gold_touch(elf, amount=0)
    monster = gold_touch(elf, toucher_flags=0x20)
    there = gold_touch(elf, local=1)
    check('k21', plain[1] == [(1, 250)] and plain[2] == 0 and OBJ_DELETE in plain[0] and SEND_GAME_MSG not in plain[0]
          and plain[3] == [0x80] and all(case[0] == [] and case[2] == 250 for case in (copy, early, monster))
          and empty[0] == [] and there == plain,
          'K6, gold (Gold_onTouch 0x157a9c): a real player touching gold whose countdown is 0 '
          'gets hud_addGoldFloater(slot, position, amount), the amount is zeroed and the object '
          'queued for deletion, with no game message; the prediction copy, a monster, a running '
          'countdown or an amount of 0 do nothing.  Same calls and stores whichever slot is '
          'local')

    owner, other = level_up(elf, True), level_up(elf, False)
    sound_only = sorted(set(owner[3]) - set(other[3]))
    bands = [level_up(elf, False, level)[1]['skill'] - 7 for level in (5, 6, 15, 16, 25, 26, 35, 36)]
    check('k22', owner[1] == other[1] == dict(ack=5, level=6, skill=8, stat=5, hp=120.0, mana=80.0)
          and owner[2] == other[2] and sound_only == [RES_FIND, SOUND_PLAY_ON_OBJECT]
          and PLAYER_RECALC_STATS in other[3] and HUD_SHOW_MESSAGE in other[3] and bands == [1, 2, 2, 3, 3, 4, 4, 5],
          'K7 in isolation (player_giveExp on a record 10 points short of level 6): the level byte '
          '+0x59 goes 5 -> 6, skill points +1 (by level band: %s for levels 5, 6, 15, 16, 25, 26, '
          '35, 36), stat points +3, player_recalcStats is called and hit points and mana are '
          'set to their maxima - the same stores on the owner\'s machine and on another; the '
          'acknowledged level +0x58 stays 5.  The only difference is the sound, made on the '
          'owner\'s machine alone' % bands)
    sent, _stores, menu_flag = open_level_up_screen(owner[0])
    not_sent, other_stores, other_flag = open_level_up_screen(other[0])
    after = []
    for world in (owner[0], other[0]):
        buffer = world.emu.alloc(0x10)
        world.emu.mem.write(buffer, (sent[-1] if sent else b'') + b'\0')
        world.emu.follow = set()
        if sent:
            world.emu.call(INVMSG_DISPATCH, buffer)
        after.append(world.emu.mem.u8(G_PLAYERS + 0x58))
    check('k23', sent[-1:] == [bytes([9, 0, 6])] and menu_flag == 1 and not_sent == [] and other_stores == 0
          and other_flag == 0 and after == [6, 6],
          'K7, second half: menu_openInventory(slot, 1) on the owner\'s machine sets '
          'g_localMenuOpen and queues inventory message 9 {slot, level byte}; on a machine that '
          'does not own the slot it stores nothing and sends nothing.  The message handler '
          '(invmsg_dispatch, case 9) then stores the level in +0x58 on both machines.  That '
          'hud_run calls it when +0x58 < +0x59 (0x1db870) was not executed')

    third, second, not_creature = knight_dies(elf, 3), knight_dies(elf, 2), knight_dies(elf, 3, found_flags=0)

    def kinds(events):
        return [event[0] for event in events]
    events, knight, skeleton, flagged = third
    loot = [event for event in events if event[0] == 'loot']
    check('k24', kinds(events) == ['find', 'skeleton state', 'loot', 'drop part', 'drop part', 'on death']
          and events[0][1] == 'skelightm' and events[1][1:] == (skeleton, 0x14) and flagged
          and loot == [('loot', knight, (36.0, 2.0, 1.8, 0.6, 2.0, 0.25))]
          and [event[1:] for event in events if event[0] == 'drop part'] == [(1, knight), (2, knight)]
          and kinds(second[0]) == kinds(events)[2:] and kinds(not_creature[0]) == ['find'] + kinds(events)[2:],
          'K8 in isolation (Horsemen_setState(knight, 0x14), callees stubbed): a knight whose '
          'variant byte is 3 looks up the object named "skelightm" and, if it is a creature, '
          'calls its set-state (slot 27) with 0x14 in the same call; every variant then calls '
          'Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25) once and the weapon helper\'s slot 11 for '
          'hand 1 and hand 2, then its own slot 28.  Variant 2 makes no look-up')



# ---------------------------------------------------------------------------------------
# s. Sync breakers that do not depend on a level (docs/issues/sync-breakers.md, FINDINGS
#    B1-B3, B8-B11) and the patch-file sections at 0x1375dc, 0x28da74 and 0x217448
# ---------------------------------------------------------------------------------------
ALL_PLAYERS_STATE2, G_LOBBY_LAUNCH, G_GAME_COMPLETE, RECORD_KIND = 0x1EC5D8, 0x4F7134, 0x4F85C5, 0x4C1C
MISC_SYNC_START, MISC_SYNC_STOPS, G_IN_FRONTEND = 0x1E3E4C, (0x1E3EC0, 0x1E3F14, 0x1E3F18), 0x41B510
HUD_ON_MSG, SAVE_PLAYER_BLOCK, SCRIPT_SAVE_GAME = 0x1D8CA0, 0x2184A4, 0x146C04
G_CHECKSUM_PENDING, G_CHECKSUM_FAILED, PEER_DROPPED = 0x4F7138, 0x4F7144, 0x44D5
SAVEPOINT_VTABLE, SAVEPOINT_PROMPT, SAVEPOINT_INTERACT, B9_SITE = 0x50DC78, 0x28DA58, 0x28DC30, 0x28DA74
TEXT_LOOKUP, WSTR_COPY, MENU_MUTEX_HELD, MEMCARD_REQUEST_SAVE = 0x173C84, 0x19E854, 0x22FC2C, 0x2175B4
LIGHT_LINK2, RUN_ACTION_SCRIPTS, G_PROMPT_TEXT, BUTTON_GLYPH = 0x148BC8, 0x14DCC8, 0x864F50, 0x1EACB8
G_CARD_REQUESTS_OFF, G_CARD_OP_RESULT = 0x88D3C8, 0x88D3BC
G_CARD_LATCH, G_SAVE_CLEAR_BLOCK, B10_SITE = 0x4F8F28, 0x4F8F2A, 0x1375DC
LAUNCH_CLEAR_START, LAUNCH_CLEAR_END, SAVE_CLEAR_BUFFER, G_SAVE_BUFFER = 0x1375C4, 0x1375E0, 0x21F144, 0x895580
ACT_CHANGE_START, ACT_CHANGE_END, SAVE_ACT_CHANGED = 0x320F8C, 0x321024, 0x217F70
JUMPGATE_RESET, GET_HUB_NAME, G_JUMPGATE_COUNT, G_JUMPGATE_DESTS = 0x27DB00, 0x1EC300, 0x8E3C30, 0x8E3A50
QUEST_CLEAR_ALL, REMOVE_FLAG39_ITEMS, VARS_CLEAR_ALL, SAVE_GET_ACT = 0x1D3ADC, 0x1BE1D8, 0x1ED728, 0x217EDC
CAMERA_GATE_START, CAMERA_GATE_END, CAMERA_RESET, MEMCARD_GET_STATE = 0x322DC0, 0x322E08, 0x203210, 0x217550
SAVE_SCREEN, SLOT_LIST = 0x218AFC, 0x21C3A4
DEBUG_FILE_START, DEBUG_FILE_END, DEBUG_SITE, MC_QUEUE_OP, MC_WAIT = 0x2173C8, 0x21744C, 0x217448, 0x223470, 0x22342C
G_CARD_FILE_FOUND, CHEAT_START, CHEAT_STOPS, G_PADS = 0x4F9550, 0x1DBB60, (0x1DBBEC, 0x1DBBF0), 0x41BFD8
OPTION_LISTS, OPTION_LIST_INPUT, G_BLOOD_OPTION, G_DAMAGE_NUMBERS, G_PAD_CONFIRM = (0x44F218, 0x4F6E88), 0x1A01D0, 0x44FDC0, 0x44FCF8, 0x41BFBC
GUTCHUNK_SLICES = ((0x2019D4, 0x2019F4), (0x201A74, 0x201A94), (0x201B2C, 0x201B50))
FX_SPAWN = 0x1EF270


def all_lobby(elf, network=1, lobby=1, complete=0, kinds=(2, 2)):
    emu = EE(elf)
    mem = emu.mem
    mem.w8(G_NETWORK_MODE, network)
    mem.w32(G_LOBBY_LAUNCH, lobby)
    mem.w8(G_GAME_COMPLETE, complete)
    mem.w32(G_NUM_PLAYERS, len(kinds))
    for slot, kind in enumerate(kinds):
        mem.w32(G_PLAYERS + slot * PLAYER_STRIDE + RECORD_KIND, kind)
    return s32(emu.call(ALL_PLAYERS_STATE2))


class ChecksumMachine:
    """One machine of a two-player net game launched from the lobby with lobby-stored
    characters (kind 2).  sync() is the stretch of gameMiscSync that runs the exchange
    (0x1e3e4c on); deliver() is the game-message handler hud_onMsg.  Everything they call
    runs for real - net_allPlayersState2, net_sendChecksums, player_checksum,
    save_playerBlock, net_disconnectPlayer - except the message send, which is recorded,
    and the debug print."""

    def __init__(self, elf, local, kinds=(2, 2), lobby=1):
        world = self.world = World(elf, players=2, local_slot=local, network=True)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        mem.w32(G_LOBBY_LAUNCH, lobby)
        mem.w32(G_LOCAL_CAMERA, emu.alloc(0x400))          # save_playerBlock asks the camera for a size
        for slot, kind in enumerate(kinds):
            record = G_PLAYERS + slot * PLAYER_STRIDE
            mem.w32(record + RECORD_KIND, kind)
            mem.w32(record + 0xE4, 1000 + slot)             # gold
            mem.w32(record + 0x5C, 5000 + slot)             # experience
        self.sent = []
        emu.stub(SEND_GAME_MSG, function=lambda e: self.sent.append(
            e.mem.read(e.r[5] & M32, e.r[6] & M32)) or 0, name='net_sendGameMsg')
        emu.stub(DBG_PRINTF, name='dbg_printf')

    def record(self, slot):
        return G_PLAYERS + slot * PLAYER_STRIDE

    def saved_record(self, slot):
        self.emu.follow = None
        return self.emu.call(SAVE_PLAYER_BLOCK, slot) & M32

    def sync(self, frame):
        emu = self.emu
        self.mem.w32(G_SIM_FRAME, frame)
        emu.r[17] = 0x420000
        emu.r[29] = emu.stack_hi - 0x1000
        emu.follow = None
        emu.reset_log()
        emu.run(start=MISC_SYNC_START, until=set(MISC_SYNC_STOPS), max_steps=2000000)
        return [c.target for c in emu.calls]

    def deliver(self, message):
        emu = self.emu
        buffer = emu.alloc(0x40)
        self.mem.write(buffer, message)
        emu.follow = None
        emu.call(HUD_ON_MSG, buffer)

    def state(self):
        return (self.mem.u32(G_CHECKSUM_FAILED),
                [self.mem.u8(G_PEERS + slot * PEER_STRIDE + PEER_DROPPED) for slot in (0, 1)])


def checksum_round(elf, tamper=None):
    """A whole exchange on two machines: start message, both sends, both deliveries.
    tamper(machine a, machine b) may change one machine's state first.  Returns the two
    machines, the start messages, the two checksum messages and each machine's state."""
    a, b = ChecksumMachine(elf, 0), ChecksumMachine(elf, 1)
    if tamper:
        tamper(a, b)
    for machine in (a, b):
        machine.sync(300)                                    # 300 = 240 + 60
    start = a.sent + b.sent
    for machine in (a, b):
        for message in start:
            machine.deliver(message)
        del machine.sent[:]
    pending = [machine.mem.u32(G_CHECKSUM_PENDING) for machine in (a, b)]
    calls = [machine.sync(301) for machine in (a, b)]
    sums = [list(machine.sent) for machine in (a, b)]
    for machine in (a, b):
        del machine.sent[:]
        for message in sums[0] + sums[1]:
            machine.deliver(message)
    return a, b, start, sums, pending, calls


class SavepointRig:
    """One machine's simulation of player slot 1 pressing the use button next to a save
    point: Player_interact 0x1b2640 called as Player_run calls it, with the game's own
    Savepoint virtual table on a blank object, so its slot 13 (Savepoint_interactPrompt
    0x28da58) and slot 14 (Savepoint_interact 0x28dc30) are reached through the table and
    run for real, as do memcard_isBusy and net_allPlayersState2.  card_state is this
    machine's card-screen state word (-1 idle).  The save request, the light, the action
    scripts and the text helpers are stubs."""
    SLOT = 1

    def __init__(self, elf, card_state=-1, patched=False, kinds=(1, 1), lobby=0, network=True):
        world = self.world = World(elf, players=2, local_slot=0, network=network)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        if patched and apply_section_at(emu, B9_SITE) is None:
            raise LookupError('no patch-file section patches 0x%x' % B9_SITE)
        mem.w32(G_LOBBY_LAUNCH, lobby)
        for slot, kind in enumerate(kinds):
            mem.w32(G_PLAYERS + slot * PLAYER_STRIDE + RECORD_KIND, kind)
        mem.w32(G_MEMCARD_STATE, card_state & M32)
        mem.w32(G_CARD_REQUESTS_OFF, 0)
        mem.w32(G_CARD_OP_RESULT, 0)
        self.player = world.objects[self.SLOT]
        point = self.point = emu.alloc(0x200)
        mem.w32(point + 0x0C, 0x100000)
        mem.wf32(point + 0x10, 110.0)
        mem.wf32(point + 0x14, 200.0)
        mem.w32(point + 0x48, SAVEPOINT_VTABLE)
        text = emu.alloc(0x10)
        mem.w16(text, 0x53)
        emu.stub(TEXT_LOOKUP, ret=text, name='text_lookup')
        emu.stub(BUTTON_GLYPH, ret=0x21, name='pad_buttonMaskToGlyph')

        def collect(e):
            out = e.r[6] & M32
            e.mem.w32(out, point)
            e.mem.w32(out + 4, 0)
            return 1
        emu.stub(COLLECT_IN_BOX, function=collect, name='world_collectObjectsInBox')
        self.pad = emu.alloc(PAD_SIZE)
        mem.w32(G_BTN_USE + 4 * self.SLOT, 0x40)
        mem.w32(self.pad + 0x0C, 0x40)
        mem.w32(G_SCRIPT_ACTIVE_PLAYER, 0)                  # the last player who used something: slot 0

    def run(self):
        emu, mem = self.emu, self.mem
        emu.follow = {SAVEPOINT_PROMPT, SAVEPOINT_INTERACT, MEMCARD_IS_BUSY, ALL_PLAYERS_STATE2, WSTR_COPY,
                      MENU_MUTEX_HELD}
        emu.reset_log()
        emu.call(PLAYER_INTERACT, self.player, self.pad, 0)
        emu.follow = None
        targets = [c.target for c in emu.calls]
        self.result = dict(
            active=mem.s32(G_SCRIPT_ACTIVE_PLAYER), prompt=SAVEPOINT_PROMPT in targets,
            interact=SAVEPOINT_INTERACT in targets,
            request=[c.args[0] & M32 for c in emu.calls if c.target == MEMCARD_REQUEST_SAVE],
            lit=LIGHT_LINK2 in targets, scripts=RUN_ACTION_SCRIPTS in targets,
            used=mem.u32(self.point + 0x84), mark=mem.u8(self.point + 0xC4),
            text=mem.u16(G_PROMPT_TEXT + 0x200 * self.SLOT) != 0)
        return run_log(emu)


def save_game_script(elf, kinds):
    """The script built-in saveGame, 0x146c04: the slots it asks a save screen for."""
    world = World(elf, players=len(kinds), local_slot=1, network=True)
    for slot, kind in enumerate(kinds):
        world.emu.mem.w32(G_PLAYERS + slot * PLAYER_STRIDE + RECORD_KIND, kind)
    world.emu.follow = {0x13E1F0}                           # net_getLocalPlayerSlot
    world.emu.call(SCRIPT_SAVE_GAME)
    return [c.args[0] & M32 for c in world.emu.calls if c.target == MEMCARD_REQUEST_SAVE]


def blood_toggle(elf, list_addr, start_value, button):
    """The option-list input handler 0x1a01d0 on one of the game's two option lists with
    the cursor on the blood entry.  button: 'left', 'right' or 'confirm'."""
    emu = EE(elf)
    mem = emu.mem
    index, entry = 0, list_addr
    while mem.u32(entry) and mem.u32(entry + 8) != G_BLOOD_OPTION:
        index, entry = index + 1, entry + 16
    kind = mem.u32(entry + 4)
    end = entry
    while mem.u32(end):
        end += 16
    mem.w32(end + 4, index)                                 # the cursor lives in the terminator row
    mem.wf32(0x4D8A10, 1.0)                                 # the key-repeat timer has run out
    mem.w32(G_BLOOD_OPTION, start_value)
    pad = emu.alloc(PAD_SIZE)
    mem.w32(pad + 0x10, {'left': 0x8000, 'right': 0x2000, 'confirm': mem.u32(G_PAD_CONFIRM)}[button])
    emu.follow = set()
    emu.call(OPTION_LIST_INPUT, list_addr, pad, 0, 0)
    return kind, mem.u32(G_BLOOD_OPTION)


def gutchunk_bit(elf, slice_, option):
    start, end = slice_
    emu = EE(elf)
    chunk = emu.alloc(0x300)
    emu.mem.w32(G_BLOOD_OPTION, option)
    emu.r[16], emu.r[17], emu.r[3] = 0x40, chunk, 0x510000
    emu.run(start=start, until={end}, max_steps=20)
    return emu.mem.u32(chunk + 0x248) & 1


def option_gate(elf, start, taken, skipped, option_addr, option, network):
    """A stretch that tests an option and then the network flag; True when the gated
    code is reached.  $s2 points at a blank object for the stretch that looks at one."""
    emu = EE(elf)
    emu.mem.w32(option_addr, option)
    emu.mem.w8(G_NETWORK_MODE, network)
    emu.r[18] = emu.alloc(0x100)
    emu.run(start=start, until=set(taken) | {skipped}, max_steps=20)
    return emu.pc != skipped


def player_gib(elf, option, network, seed=0x1234):
    """Player_processDamage 0x1b31dc-0x1b32d8: returns (the shared seed was drawn, the
    blood effect was spawned)."""
    world = World(elf, players=1, network=bool(network))
    emu, mem = world.emu, world.emu.mem
    mem.w32(G_BLOOD_OPTION, option)
    mem.w32(G_RAND_SEED, seed)
    emu.stub(POOL_NEW, ret=0, name='pool_new')
    emu.r[16], emu.r[9] = world.objects[0], 1
    emu.fset(1, 10.0)
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = set()
    emu.reset_log()
    emu.run(start=0x1B31DC, until={0x1B32D8, 0x1B32DC, 0x1B32E4}, max_steps=200)
    return mem.u32(G_RAND_SEED) != seed, any(c.target == FX_SPAWN for c in emu.calls)


def save_screen(elf, sub_state, latch, slot_chosen=1, auto_slot=1, picker=0, card_error=0, pressed=0,
                level_pending=0, fade=8, alpha=0):
    """One call of memcard_saveScreen 0x218afc with every callee stubbed.  Returns the
    latch afterwards, the sub-state afterwards and whether the latch was stored to."""
    emu = EE(elf)
    mem = emu.mem
    mem.w8(G_NETWORK_MODE, 1)
    mem.w32(0x88D3E4, 1)                                    # the card has been checked
    mem.w32(0x88D3D8, slot_chosen)
    mem.w8(0x8E1AD8, auto_slot)                             # "save to the slot loaded from"
    mem.w32(0x88D3A8, sub_state)
    mem.w32(G_CARD_OP_RESULT, card_error)
    mem.w8(G_CARD_LATCH, latch)
    mem.w32(0x8E11FC, fade & M32)
    mem.w32(0x8E11F8, alpha)
    mem.w8(0x41B6D0, level_pending)
    mem.w32(0x4028DC, pressed)                              # pressed word of raw pad 0
    mem.w32(0x41BFB8, 0x40)
    mem.w32(G_PAD_CONFIRM, 0x40)
    emu.follow = set()
    emu.stub(SLOT_LIST, ret=picker, name='memcard_slotList')
    emu.reset_log()
    emu.call(SAVE_SCREEN)
    return (mem.u8(G_CARD_LATCH), mem.u32(0x88D3A8),
            [value for _pc, addr, _n, value in emu.writes if addr == G_CARD_LATCH],
            any(c.target == MEMCARD_REQUEST_SAVE for c in emu.calls))


class LatchMachine:
    """One machine whose card latch 0x4f8f28 has the given value, taken through the three
    stretches that concern it: the net launch code (0x1375c4-0x1375e0, with
    save_clearBuffer running for real), the act-change block of the level change
    (0x320f8c-0x321024, callees stubbed and recorded) and the camera reset test
    (0x322dc0-0x322e08)."""

    def __init__(self, elf, latch, patched=False, clear_block=0):
        emu = self.emu = EE(elf)
        mem = self.mem = emu.mem
        if patched and apply_section_at(emu, B10_SITE) is None:
            raise LookupError('no patch-file section patches 0x%x' % B10_SITE)
        mem.w8(G_CARD_LATCH, latch)
        mem.w8(G_SAVE_CLEAR_BLOCK, clear_block)
        mem.w32(G_NUM_PLAYERS, 2)
        mem.w32(G_MEMCARD_STATE, 0xFFFFFFFF)
        mem.write(G_SAVE_BUFFER, b'\x5A' * 0x100)           # something for the launch to clear

    def launch(self):
        emu = self.emu
        emu.r[29] = emu.stack_hi - 0x4000
        emu.follow = {SAVE_CLEAR_BUFFER, MEMSET}
        emu.reads = []
        emu.reset_log()
        emu.run(start=LAUNCH_CLEAR_START, until={LAUNCH_CLEAR_END}, max_steps=2000000)
        emu.follow = None
        byte_stores = [(addr, value) for pc, addr, size, value in emu.writes if pc == B10_SITE]
        read_block = any(addr == G_SAVE_CLEAR_BLOCK for _pc, addr, _n, _v in emu.reads)
        emu.reads = None
        return byte_stores, read_block, self.mem.read(G_SAVE_BUFFER, 0x100) == bytes(0x100)

    def act_change(self, changed=1, in_frontend=0):
        emu = self.emu
        self.mem.w32(G_IN_FRONTEND, in_frontend)
        emu.stub(SAVE_ACT_CHANGED, ret=changed, name='save_actChanged')
        emu.r[19] = 0x420000
        emu.r[29] = emu.stack_hi - 0x1000
        emu.follow = set()
        emu.reset_log()
        emu.run(start=ACT_CHANGE_START, until={ACT_CHANGE_END}, max_steps=500)
        emu.unhook(SAVE_ACT_CHANGED)
        return ([(c.target, c.args[0] & M32) for c in emu.calls if c.target not in (SAVE_ACT_CHANGED, TASK_IS_RUNNING)],
                sorted({addr for _pc, addr, _n, _v in emu.writes}))

    def camera_gate(self):
        emu = self.emu
        emu.follow = {MEMCARD_GET_STATE}
        emu.reset_log()
        emu.run(start=CAMERA_GATE_START, until={CAMERA_GATE_END}, max_steps=50)
        return any(c.target == CAMERA_RESET for c in emu.calls)


def jumpgate_reset(elf, latch):
    emu = EE(elf)
    mem = emu.mem
    hub = emu.alloc(0x20)
    mem.write(hub, b'hub\0')
    mem.w8(G_CARD_LATCH, latch)
    mem.w8(G_JUMPGATE_COUNT, 5)
    mem.write(G_JUMPGATE_DESTS, b'elsewhere\0')
    emu.stub(GET_HUB_NAME, ret=hub, name='game_getHubName')
    emu.follow = None
    emu.call(JUMPGATE_RESET, 0)
    return mem.u8(G_JUMPGATE_COUNT), mem.cstr(G_JUMPGATE_DESTS)


def debug_file(elf, on_card, patched=False):
    """save_init 0x2173c8-0x21744c: the card is asked about one file; on_card is what the
    card answers (the word the code reads after the file-info operation)."""
    emu = EE(elf)
    mem = emu.mem
    if patched and apply_section_at(emu, DEBUG_SITE) is None:
        raise LookupError('no patch-file section patches 0x%x' % DEBUG_SITE)
    asked = []

    def queue(e):
        if e.r[4] & M32 == 6:                               # file information
            asked.append(e.mem.cstr(e.r[5] & M32))
            e.mem.w32(G_CARD_FILE_FOUND, 1 if on_card else 0)
        return 0
    emu.stub(MC_QUEUE_OP, function=queue, name='mc_queueOp')
    emu.stub(MC_WAIT, name='mc_wait')
    mem.w8(G_DEBUG_FLAG, 0x55)
    emu.r[18] = emu.r[19] = 0x500000
    emu.r[29] = emu.stack_hi - 0x1000
    emu.reset_log()
    emu.run(start=DEBUG_FILE_START, until={DEBUG_FILE_END}, max_steps=200)
    return mem.u8(G_DEBUG_FLAG), asked, run_log(emu)


def debug_cheat(elf, flag, pressed=0x4000, held=0x8, in_frontend=0):
    """hud_run 0x1dbb60 on: what the debug flag does with slot 0's lockstep pad."""
    world = World(elf, players=2, network=True)
    emu, mem = world.emu, world.emu.mem
    mem.w8(G_DEBUG_FLAG, flag)
    mem.w32(G_IN_FRONTEND, in_frontend)
    mem.w32(G_PADS + 0x0C, pressed)
    mem.w32(G_PADS + 0x08, held)
    mem.w32(G_PLAYERS + 0xE4, 77)
    emu.follow = set()
    emu.reset_log()
    emu.run(start=CHEAT_START, until=set(CHEAT_STOPS), max_steps=200)
    return mem.u32(G_PLAYERS + 0xE4), [(c.args[0] & M32, c.args[1] & M32) for c in emu.calls if c.target == GIVE_EXP]


def test_sync_breakers(elf):
    truth = [all_lobby(elf), all_lobby(elf, network=0), all_lobby(elf, lobby=0), all_lobby(elf, complete=1),
             all_lobby(elf, kinds=(2, 1)), all_lobby(elf, kinds=(1, 2)), all_lobby(elf, kinds=(2, 2, 2, 2)),
             all_lobby(elf, kinds=(2, 2, 2, 3)), all_lobby(elf, kinds=(0x22, 0xE2))]
    check('s1', truth == [1, 0, 0, 0, 0, 0, 1, 0, 1],
          'B1 in isolation (net_allPlayersState2 0x1ec5d8): true only in a net game with the '
          'lobby-launch word 0x4f7134 set, the game-complete byte clear and the low five bits '
          'of record +0x4c1c equal to 2 for EVERY player; one player of another kind makes it '
          'false.  That only lobby character creation and the launch code write a 2 is a '
          'search result and was not executed')
    sends = {}
    for frame in (59, 60, 61, 299, 300, 301, 540):
        machines = ChecksumMachine(elf, 0), ChecksumMachine(elf, 1)
        for machine in machines:
            machine.sync(frame)
        sends[frame] = [len(machine.sent) for machine in machines]
    outsider = ChecksumMachine(elf, 0, kinds=(2, 1))
    outsider.sync(300)
    front = ChecksumMachine(elf, 0)
    front.mem.w32(G_IN_FRONTEND, 1)
    front_calls = front.sync(300)
    check('s2', sends == {59: [0, 0], 60: [1, 0], 61: [0, 0], 299: [0, 0], 300: [1, 0], 301: [0, 0], 540: [1, 0]}
          and not outsider.sent and not front.sent and ALL_PLAYERS_STATE2 not in front_calls,
          'B1/B2, when the exchange starts (gameMiscSync entered part-way at 0x1e3e4c, on two '
          'machines): game message 9 is queued on frames whose number mod 240 is 60 (60, 300, '
          '540; not 59, 61, 299, 301), by the first active machine only; never when one '
          'player is not kind 2, and in the front end the test is not even made')
    a, b, start, sums, pending, calls = checksum_round(elf)
    own_pair = [len(messages) == 1 and messages[0][:4] == bytes([10, slot, 0, 0]) and len(messages[0]) == 12
                for slot, messages in enumerate(sums)]
    check('s3', start == [bytes([9])] and pending == [1, 1] and all(0x1DE46C in c for c in calls)
          and all(own_pair) and a.state() == b.state() == (0, [0, 0])
          and [m.mem.u32(G_CHECKSUM_PENDING) for m in (a, b)] == [0, 0],
          'B2, one whole round with identical records (two machines; hud_onMsg, '
          'net_sendChecksums, player_checksum and save_playerBlock run for real): message 9 '
          'sets the pending word on both, the next gameMiscSync on each calls '
          'net_sendChecksums and clears it, each machine sends game message 10 with the two '
          'values of its OWN slot only, and after both messages have been handled on both '
          'machines no flag is set and nobody is dropped')

    def gold(machine_index, slot):
        def change(a, b):
            machine = (a, b)[machine_index]
            machine.mem.w32(machine.record(slot) + 0xE4, 999999)
        return change
    a, b, _start, _sums, _p, _c = checksum_round(elf, gold(1, 0))
    first = (a.state(), b.state(), a.sent, b.sent)
    a, b, _start, _sums, _p, _c = checksum_round(elf, gold(0, 1))
    second = (a.state(), b.state(), a.sent, b.sent)
    check('s4', first == ((0, [0, 0]), (1, [1, 0]), [], [bytes([4, 0])])
          and second == ((1, [0, 1]), (0, [0, 0]), [bytes([4, 1])], []),
          'B2, a mismatch: when slot 0\'s gold differs on machine B only, B sets the '
          'checksum-failed word 0x4f7144 and marks peer 0 dropped (net_disconnectPlayer) while '
          'A - whose own values B disagrees with - notices nothing: the drop is on the machine '
          'that sees the difference only, as the row says.  Sharper than sync-breakers.md '
          'section 1: net_disconnectPlayer asks "am I the first active machine" AFTER it has '
          'marked the peer dropped, so B, which has just dropped the only slot in front of it, '
          'answers yes and queues game message 4 for slot 0 as well.  With slot 1\'s gold '
          'different on machine A, A flags, drops peer 1 and queues message 4 for slot 1')

    def saved_gold(a, b):
        b.mem.w8(b.saved_record(0) + 0xE4, 0x77)

    def hit_points(a, b):
        b.set_hp = b.world.set_hp(0, 1.0)
    a, b, _start, _sums, _p, _c = checksum_round(elf, saved_gold)
    buffer_half = (a.state(), b.state())
    a, b, _start, _sums, _p, _c = checksum_round(elf, hit_points)
    check('s5', buffer_half == ((0, [0, 0]), (1, [1, 0])) and a.state() == b.state() == (0, [0, 0]),
          'B2, the two halves: a difference in the copy of slot 0 inside machine B\'s own save '
          'buffer (the address save_playerBlock returns) drops slot 0 on B exactly as a '
          'difference in the live record does; a difference in hit points, which the checksum '
          'does not cover, is not noticed')
    lobby_game = SavepointRig(elf, kinds=(2, 2), lobby=1)
    lobby_game.run()
    card_game = SavepointRig(elf)
    card_game.run()
    check('s6', lobby_game.result['prompt'] and not lobby_game.result['interact'] and lobby_game.result['active'] == 0
          and not lobby_game.result['text'] and card_game.result['interact'] and card_game.result['request'] == [1]
          and save_game_script(elf, (2, 2)) == [] and save_game_script(elf, (1, 2)) == []
          and save_game_script(elf, (1, 1)) == [1],
          'B3 in isolation: in a game where net_allPlayersState2 holds, Savepoint_interactPrompt '
          '(reached through the Savepoint\'s own virtual table from Player_interact) returns '
          '"nothing" with no text, so the use button neither sets the active player nor reaches '
          'Savepoint_interact; with memory-card characters the same press asks for the save '
          'screen.  The script built-in saveGame 0x146c04 asks for it only when no player is '
          'kind 2')

    toggles = {(start_value, button): [blood_toggle(elf, addr, start_value, button) for addr in OPTION_LISTS]
               for start_value in (0, 1, 2, 7) for button in ('left', 'right', 'confirm')}
    bits = [[gutchunk_bit(elf, slice_, option) for option in (0, 1, 2, 3)] for slice_ in GUTCHUNK_SLICES]
    check('s7', all(result == [(3, 1 if start_value == 0 else 0)] * 2 for (start_value, _b), result in toggles.items())
          and bits == [[1, 1, 0, 0]] * 3,
          'B8, first half: in both option lists the blood entry is type 3, and the list handler '
          '0x1a01d0 run on them turns the value into "was it 0" on left, right and confirm - 0 '
          'and 1 are the only values it can store, whatever was there (0, 1, 2 and 7 tried).  '
          'The three GutChunk constructors (0x2019d4, 0x201a74, 0x201b2c, entered part-way) '
          'set the lifetime bit for option 0 and 1 alike and not for 2 or 3')
    numbers = [option_gate(elf, 0x1EA994, (0x1EA9B4, 0x1EA9B8), 0x1EAC70, G_DAMAGE_NUMBERS, option, network)
               for network in (0, 1) for option in (0, 1)]
    gore = [option_gate(elf, 0x1113F8, (0x111418,), 0x111474, G_BLOOD_OPTION, option, network)
            for network in (0, 1) for option in (0, 1)]
    gibs = [player_gib(elf, option, network) for network in (0, 1) for option in (0, 1)]
    check('s8', numbers == [False, True, True, True] and gore == [False, True, True, True]
          and gibs == [(False, False), (True, True), (True, False), (True, True)],
          'B8, second half (three stretches, offline/net x option 0/1): the damage-number test '
          'in damage_apply (0x1ea994) and the gore test in Creature_processDamage (0x1113f8) '
          'skip their code only for option 0 OFFLINE; in a net game they go on whatever the '
          'option says (%s, %s).  Player_processDamage (0x1b31dc) likewise draws the shared '
          'seed for the gib roll in a net game with the option 0 or 1; only the blood effect '
          'itself follows the option, and that is per machine and cosmetic (seed drawn, effect '
          'spawned: %s)' % (numbers, gore, gibs))

    idle, busy = SavepointRig(elf, card_state=-1), SavepointRig(elf, card_state=3)
    idle_log, busy_log = idle.run(), busy.run()
    calls_diff, stores_diff = log_diff(idle_log, busy_log, with_args=False)
    table('B9: machine with no card screen against machine with one open (shipped)',
          ['idle: %s' % idle.result, 'busy: %s' % busy.result,
           'calls that differ: ' + hexes(calls_diff), 'stores that differ: ' + hexes(stores_diff)])
    check('s9', idle.result == dict(active=1, prompt=True, interact=True, request=[1], lit=True, scripts=True,
                                    used=1, mark=1, text=True)
          and busy.result == dict(active=0, prompt=True, interact=False, request=[], lit=False, scripts=False,
                                  used=0, mark=0, text=False)
          and G_SCRIPT_ACTIVE_PLAYER in stores_diff,
          'B9 in isolation (the same press of the use button by player 1 at a save point, '
          'simulated on two machines that differ in one word, the card-screen state 0x88d3a0): '
          'on the machine with no card screen the prompt returns 1 with a text, Player_interact '
          'stores 1 in g_scriptActivePlayer at 0x1b2b70 and calls Savepoint_interact, which '
          'asks for the save screen, sets +0x84 and +0xc4, links the light and runs the action '
          'scripts; on the machine with a card screen open the prompt returns 0 with no text '
          'and none of that happens - the active player stays 0 there')
    result_word = SavepointRig(elf)
    result_word.mem.w32(G_CARD_OP_RESULT, 5)
    result_word.run()
    off = SavepointRig(elf, card_state=3)
    off.mem.w32(G_CARD_REQUESTS_OFF, 1)
    off.run()
    check('s10', result_word.result['active'] == 0 and off.result['active'] == 1,
          'memcard_isBusy 0x217518 as the prompt uses it: an idle screen with a non-zero card '
          'result word also counts as busy (active player not set), and the "card requests off" '
          'word 0x88d3c8 makes it report not busy even with a screen open')
    if pnach_section_at(B9_SITE) is None:
        skip('s11', 'the patch file has no section for 0x28da74; the patched runs were not made')
    else:
        p_idle, p_busy = SavepointRig(elf, card_state=-1, patched=True), SavepointRig(elf, card_state=3, patched=True)
        p_idle_log, p_busy_log = p_idle.run(), p_busy.run()
        left_calls, left_stores = log_diff(p_idle_log, p_busy_log, with_args=False)
        table('B9 patched: what still differs between the two machines',
              ['idle: %s' % p_idle.result, 'busy: %s' % p_busy.result,
               'calls that differ: ' + hexes(left_calls), 'stores that differ: ' + hexes(left_stores)])
        check('s11', p_idle.result['active'] == p_busy.result['active'] == 1 and p_busy.result['interact']
              and p_busy.result['text'] and G_SCRIPT_ACTIVE_PLAYER not in left_stores
              and p_busy.result['request'] == [] and p_busy.result['used'] == 0 and p_busy.result['mark'] == 0
              and not p_busy.result['lit'] and not p_busy.result['scripts']
              and left_stores == [busy.point + 0x84, busy.point + 0xC4]
              and left_calls == sorted([RUN_ACTION_SCRIPTS, LIGHT_LINK2, MEMCARD_REQUEST_SAVE, MENU_MUTEX_HELD]),
              'patch "save-point prompt ignores this machine\'s card screen" (0x28da74 := '
              'no-operation): both machines now store 1 in g_scriptActivePlayer and both reach '
              'Savepoint_interact, so the difference B9 names is gone.  On the busy machine the '
              'prompt text is now set (the cost the patch text states) and Savepoint_interact '
              'returns at its own card test, so that machine still does not ask for a save '
              'screen - and still does not set the point\'s +0x84 and +0xc4, link its light or '
              'run its action scripts.  That residue is what sync-breakers.md section 4b calls '
              'the point\'s own effect state; the patch does not remove it')
        check('s12', p_idle_log == idle_log and p_idle.result == idle.result
              and SavepointRig(elf, kinds=(2, 2), lobby=1, patched=True).run() == lobby_game.run(),
              'nothing else changes: on a machine with no card screen the patched Player_interact '
              'makes the same calls with the same arguments and the same stores as the shipped '
              'one (the delay-slot instruction that now always runs clears a register the next '
              'call overwrites), and the all-lobby-character refusal of s6 is untouched')

    chosen = [save_screen(elf, 0, 0, slot_chosen=0, auto_slot=1), save_screen(elf, 0, 0, slot_chosen=0, auto_slot=0, picker=1)]
    backed_out = save_screen(elf, 0, 0, slot_chosen=0, auto_slot=0, picker=0)
    clean = [save_screen(elf, 4, 1, fade=-16), save_screen(elf, 4, 1, level_pending=1)]
    error = save_screen(elf, 2, 1, card_error=1)
    error_exit = [save_screen(elf, 9, 1), save_screen(elf, 9, 1, pressed=0x40), save_screen(elf, 9, 1, level_pending=1)]
    check('s13', all(c[0] == 1 and c[2] == [1] for c in chosen) and backed_out[0] == 0 and backed_out[2] == []
          and all(c[0] == 0 and c[2] == [0] for c in clean)
          and error[:3] == (1, 9, []) and all(e[0] == 1 and e[2] == [] for e in error_exit)
          and [e[3] for e in error_exit] == [False, True, False],
          'B10, the save screen (memcard_saveScreen 0x218afc, one call per case, callees '
          'stubbed): choosing a slot - either way of choosing - stores 1 in the latch 0x4f8f28; '
          'the sub-state reached after a clean write (4) stores 0 when the "saved" box closes or '
          'a level change is pending; a non-zero card result sends the screen to sub-state 9, '
          'and neither that step nor the exit from sub-state 9 (button pressed, or level change '
          'pending) stores to the latch at all - it stays 1.  With the button the exit asks for '
          'the save screen again')
    readers = {}
    for latch in (0, 1):
        machine = LatchMachine(elf, latch)
        readers[latch] = (machine.act_change(), machine.camera_gate(), jumpgate_reset(elf, latch))
    block = [SAVE_CLEAR_BUFFER, SAVE_GET_ACT, JUMPGATE_RESET, QUEST_CLEAR_ALL, REMOVE_FLAG39_ITEMS,
             REMOVE_FLAG39_ITEMS, VARS_CLEAR_ALL]
    no_change = LatchMachine(elf, 0).act_change(changed=0)
    check('s14', [target for target, _a in readers[0][0][0]] == block and readers[0][0][0][0][1] == 0
          and [arg for target, arg in readers[0][0][0] if target == REMOVE_FLAG39_ITEMS] == [0, 1]
          and readers[0][0][1] == [0x4F7118] and readers[1][0] == ([], []) and no_change == ([], [])
          and (readers[0][1], readers[1][1]) == (True, False)
          and readers[0][2] == (1, 'hub') and readers[1][2] == (5, 'elsewhere'),
          'B10, the three readers, each with the latch 0 and 1: at an act change the level '
          'change (0x320f8c-0x321024) calls save_clearBuffer(0), save_getAct, '
          'jumpgate_resetDestinations, quest_clearAll, player_removeFlag39Items for each player '
          'and vars_clearAll and stores 1 at 0x4f7118 - with the latch set it calls none of them '
          'and stores nothing; jumpgate_resetDestinations 0x27db00 resets the list to the hub '
          'name or, with the latch set, leaves count and names alone; the stretch at 0x322dc0 '
          'calls Camera_reset or skips it')
    stuck, fresh = LatchMachine(elf, 1), LatchMachine(elf, 0)
    launched = [machine.launch() for machine in (stuck, fresh)]
    after = [(machine.mem.u8(G_CARD_LATCH), machine.act_change()[0] != [], machine.camera_gate()) for machine in (stuck, fresh)]
    blocked = LatchMachine(elf, 0, clear_block=1).launch()
    check('s15', launched[0] == launched[1] == ([(G_SAVE_CLEAR_BLOCK, 0)], True, True)
          and after == [(1, False, False), (0, True, True)] and blocked[2] is False,
          'B10/B11 chain: the net launch stretch (0x1375c4-0x1375e0, save_clearBuffer(1) real) '
          'zeroes the save buffer and then stores 0 to the byte 0x4f8f2a on both machines - it '
          'does not touch the latch.  A machine that came into the launch with the latch stuck '
          'at 1 therefore still has it at 1 and at the next act change makes none of the seven '
          'clean-up calls and no camera reset, while a machine whose latch was 0 makes them '
          'all: the difference B11 infers the desync from.  (save_clearBuffer reads 0x4f8f2a '
          'on entry and skips the clear when it is non-zero; it is 0 in the executable)')
    if pnach_section_at(B10_SITE) is None:
        skip('s16', 'the patch file has no section for 0x1375dc; the patched runs were not made')
    else:
        p_stuck, p_fresh = LatchMachine(elf, 1, patched=True), LatchMachine(elf, 0, patched=True)
        p_launched = [machine.launch() for machine in (p_stuck, p_fresh)]
        p_after = [(machine.mem.u8(G_CARD_LATCH), machine.act_change(), machine.camera_gate()) for machine in (p_stuck, p_fresh)]
        shipped_logs, patched_logs = [], []
        for latch in (0, 1):
            for patched in (False, True):
                machine = LatchMachine(elf, latch, patched=patched)
                machine.launch()
                (patched_logs if patched else shipped_logs).append(run_log(machine.emu))
        only_address = all(s_log[0] == p_log[0] and len(s_log[1]) == len(p_log[1])
                           and [(x, y) for x, y in zip(s_log[1], p_log[1]) if x != y]
                           == [((B10_SITE, G_SAVE_CLEAR_BLOCK, 1, 0), (B10_SITE, G_CARD_LATCH, 1, 0))]
                           for s_log, p_log in zip(shipped_logs, patched_logs))
        check('s16', p_launched[0] == p_launched[1] == ([(G_CARD_LATCH, 0)], True, True)
              and p_after[0] == p_after[1] and p_after[0][0] == 0 and p_after[0][1] == readers[0][0]
              and p_after[0][2] is True and only_address,
              'patch "net launch clears a stuck memory-card latch" (0x1375dc): the same stretch '
              'now stores its 0 to the latch 0x4f8f28, so the machine that was stuck and the '
              'machine that was not come out equal and make the same act-change calls and the '
              'same camera reset afterwards.  Against the shipped stretch the calls are the '
              'same and exactly one store differs, its address; the byte 0x4f8f2a is no longer '
              'written (that nothing else ever sets it is a search result, not executed - if '
              'something did, a patched machine would skip the buffer clear at the next launch)')

    with_file, without = debug_file(elf, True), debug_file(elf, False)
    calls_diff, stores_diff = log_diff(with_file[2], without[2])
    check('s17', with_file[:2] == (1, ['debug.sht']) and without[:2] == (0, ['debug.sht'])
          and calls_diff == [] and stores_diff == [G_DEBUG_FLAG],
          'sync-breakers.md section 7 in isolation (save_init entered part-way at 0x2173c8): the '
          'code clears g_debugCheats 0x4f8ee0, asks the card about a file named "debug.sht" and '
          'stores 1 in it when the card says the file exists.  Two machines that differ only in '
          'that answer make the same calls and differ in that one store')
    cheat = debug_cheat(elf, 1)
    quiet = [debug_cheat(elf, 0), debug_cheat(elf, 1, pressed=0), debug_cheat(elf, 1, held=0),
             debug_cheat(elf, 1, in_frontend=1)]
    check('s18', cheat == (1500000, [(0, 20000), (1, 20000)]) and quiet == [(77, [])] * 4,
          'what the flag then does (hud_run entered part-way at 0x1dbb60, the same lockstep pad '
          'of slot 0 on both machines): with the flag set, pressed bit 0x4000 and held bit 0x8 '
          'give slot 0 gold 1,500,000 and call player_giveExp(slot, 20000) for every player; '
          'with the flag clear, or without both buttons, or in the front end, nothing - so the '
          'machine with the file and the machine without diverge on that press')
    if pnach_section_at(DEBUG_SITE) is None:
        skip('s19', 'the patch file has no section for 0x217448; the patched runs were not made')
    else:
        p_with, p_without = debug_file(elf, True, patched=True), debug_file(elf, False, patched=True)
        check('s19', p_with[0] == p_without[0] == 0 and p_with[2] == p_without[2] == without[2]
              and p_with[1] == ['debug.sht'],
              'patch "ignore the debug file on the memory card" (0x217448 := no-operation): with '
              'or without the file the flag ends 0, and the patched stretch makes the calls and '
              'stores of the shipped stretch on a card without the file - the card is still '
              'asked, only the store of 1 is gone')


# ---------------------------------------------------------------------------------------
# m. Player movement (docs/spec/movement-camera.md section 4, FINDINGS MV2, MV5, MV6)
# ---------------------------------------------------------------------------------------
PLAYER_MOVE, PLAYER_RUN, CREATURE_MOVE_SIMPLE, CREATURE_MOVE_BY, OBJ_MOVE_COLLIDE = 0x1B4020, 0x1A5030, 0x1186D8, 0x113C48, 0x14D4B8
APPLY_KNOCKBACK, MATH_COS16, MATH_SIN16, ANGLE_APPROACH, NET_GET_CAM_YAW = 0x115EB8, 0x166630, 0x1666E0, 0x166C18, 0x13E0C8
ATAN2_INNER = (0x3A5A80, 0x3A7328, 0x3AA558, 0x3AA7E8)      # the C library's atan2f and what it calls
G_RUN_SPEED, G_LEVEL_NAME, G_PVP_B_SUBMODE, RECORD_SPEED_MUL = 0x4F8418, 0x41B721, 0x4F7124, 0x4C20
PAD_CHOICE_START, PAD_CHOICE_END, G_ZERO_PAD, NET_IS_SLOT_ACTIVE = 0x1A5640, 0x1A5768, 0x8667F0, 0x13DD40
SPEED_OFFLINE, SPEED_NET, SPEED_CAP = 0x3F5CA86D, 0x3F400000, 0x3F999999
MOVE_ROUTINES = {PLAYER_MOVE: 'Player_move', CREATURE_MOVE_SIMPLE: 'creature_moveSimple',
                 OBJ_MOVE_COLLIDE: 'obj_moveWithCollision', CREATURE_MOVE_BY: 'Creature_moveBy'}


class MoveRig:
    """Player_move 0x1b4020 called with mode 0 on a fake player, as Player_run calls it in
    the neutral state.  The trigonometry, the angle approach, the camera-yaw and dialog
    look-ups and the software double arithmetic run for real; the animation step, the
    water test and the move itself (creature_moveSimple, which wraps
    obj_moveWithCollision) are stubs - the vector handed to the move is recorded."""

    def __init__(self, elf, network=True, speed_mul=1.0, run_speed=1.0, yaw=0x2000, facing=0, dialog=0,
                 level=b'hub', pvp_b=0, pvp_b_sub=0, record_words=None):
        world = self.world = World(elf, players=1, local_slot=0, network=network)
        emu, mem = self.emu, self.mem = world.emu, world.emu.mem
        self.player, self.record = world.objects[0], G_PLAYERS
        mem.wf32(self.record + RECORD_SPEED_MUL, speed_mul)
        mem.wf32(G_RUN_SPEED, run_speed)
        mem.write(G_LEVEL_NAME, level + b'\0')
        mem.w32(G_PVP_MODE_B, pvp_b)
        mem.w32(G_PVP_B_SUBMODE, pvp_b_sub)
        mem.w16(G_NET_CAM_YAW, yaw)
        camera = emu.alloc(0x400)
        mem.w16(camera + 0x68, yaw)
        mem.w32(camera + 0x34, 1)
        mem.w32(G_LOCAL_CAMERA, camera)
        mem.w16(self.player + 0x38, facing)
        mem.w32(G_DIALOG_DATA, dialog)
        for offset, value in (record_words or {}).items():
            mem.w32(self.record + offset, value)
        self.pad = emu.alloc(PAD_SIZE)
        self.moved = []

        def note(e):
            vector = e.r[5] & M32
            self.moved.append(tuple(e.mem.u32(vector + 4 * i) for i in range(3)))
            return 4                                            # "on the ground"
        emu.stub(CREATURE_MOVE_SIMPLE, function=note, name='creature_moveSimple')
        self.record_reads = set()

    def move(self, lx, ly, mode=0):
        """One call.  Returns (speed, direction of the velocity in 1/65536 turns, facing
        afterwards, raw velocity words, stick left in the pad)."""
        import math
        emu, mem = self.emu, self.mem
        mem.wf32(self.pad + 0x14, lx)
        mem.wf32(self.pad + 0x18, ly)
        emu.follow = {MATH_COS16, MATH_SIN16, ATAN2_16, ANGLE_APPROACH, NET_GET_CAM_YAW, DIALOG_IS_OPEN, STRCMP,
                      IS_LOCAL_SLOT, NET_GET_CAM_FLAG} | set(ATAN2_INNER) | set(SOFT_DOUBLE)
        emu.reads = []
        emu.reset_log()
        emu.call(PLAYER_MOVE, self.player, mode, self.pad, 0)
        emu.follow = None
        self.record_reads |= {addr - self.record for _pc, addr, _n, _v in emu.reads
                              if self.record <= addr < self.record + PLAYER_STRIDE}
        emu.reads = None
        vx, vy = mem.f32(self.player + 0x4BC), mem.f32(self.player + 0x4C0)
        direction = math.atan2(vy, vx) * 65536 / (2 * math.pi) if (vx or vy) else None
        return (math.hypot(vx, vy), direction, mem.s16(self.player + 0x38),
                (mem.u32(self.player + 0x4BC), mem.u32(self.player + 0x4C0)),
                (mem.f32(self.pad + 0x14), mem.f32(self.pad + 0x18)))


def angle_gap(a, b):
    return abs((a - b + 32768) % 65536 - 32768)


def pad_choice(elf, network, dialog=0, lockout=0, hit_points=100.0):
    """Player_run 0x1a5640-0x1a5768: which pad the rest of the function is given."""
    world = World(elf, players=2, local_slot=0, network=network)
    emu, mem = world.emu, world.emu.mem
    mem.w32(G_DIALOG_DATA, dialog)
    mem.w32(G_MENU_LOCKOUT, lockout)
    world.set_hp(1, hit_points)
    camera = emu.alloc(0x100)
    mem.w32(camera + 0x34, 1)
    mem.w32(G_LOCAL_CAMERA, camera)
    sp = player_run_frame(emu, 0)
    emu.r[30] = world.objects[1]
    emu.follow = {DIALOG_IS_OPEN, NET_GET_CAM_FLAG, NET_IS_SLOT_ACTIVE}
    emu.run(start=PAD_CHOICE_START, until={PAD_CHOICE_END}, max_steps=300)
    chosen = mem.u32(sp + 0xE40)
    return {G_ZERO_PAD: 'zero pad', G_PADS + PAD_SIZE: 'own pad'}.get(chosen, hex(chosen))


def player_run_moves(elf, state, network):
    """The whole of Player_run 0x1a5030 on a fake player in the given action state, every
    callee stubbed.  Returns the move routines it called (with the mode argument) and
    how often it called Creature_applyKnockback."""
    world = World(elf, players=2, local_slot=0, network=network)
    emu, mem = world.emu, world.emu.mem
    player = world.objects[1]
    mem.w32(player + 0x58C, state)
    camera = emu.alloc(0x400)
    mem.w32(camera + 0x34, 1)
    mem.w32(G_LOCAL_CAMERA, camera)
    mem.w16(G_PLAYERS + PLAYER_STRIDE + RECORD_SKILL_LIST, 0xFFFF)
    emu.follow = set()
    emu.reset_log()
    emu.call(PLAYER_RUN, player, max_steps=200000)
    return ([(MOVE_ROUTINES[c.target], c.args[1] & M32) for c in emu.calls if c.target in MOVE_ROUTINES],
            sum(1 for c in emu.calls if c.target == APPLY_KNOCKBACK))


def knockback(elf, network, flags=0x60, pvp_b=0):
    """Creature_applyKnockback(1.0, creature) with 30 units of knock-back pending."""
    emu = EE(elf)
    mem = emu.mem
    mem.w8(G_NETWORK_MODE, network)
    mem.w32(G_PVP_MODE_B, pvp_b)
    creature = emu.alloc(0x600)
    mem.w32(creature + 0x0C, flags)
    mem.wf32(creature + 0x2E8, 30.0)
    emu.follow = {MATH_COS16, MATH_SIN16}
    emu.stub(CREATURE_MOVE_BY, ret=3, name='Creature_moveBy')      # "hit something": ends the function early
    emu.reset_log()
    emu.call(APPLY_KNOCKBACK, creature, fargs=(1.0,))
    return any(c.target == CREATURE_MOVE_BY for c in emu.calls), mem.f32(creature + 0x2E8)


def test_movement(elf):
    offline, net = raw_to_float(SPEED_OFFLINE), raw_to_float(SPEED_NET)
    cases = (('offline', dict(network=False), offline), ('net game', dict(), net),
             ('net, PvP mode B, word 0x4f7124 clear', dict(pvp_b=1), offline),
             ('net, PvP mode B, word 0x4f7124 set', dict(pvp_b=1, pvp_b_sub=1), net),
             ('net, level "watmedal"', dict(level=b'watmedal'), offline))
    rows, ok = [], True
    for label, options, scale in cases:
        speed = MoveRig(elf, **options).move(0.0, -1.0)[0]
        ok &= abs(speed - 180.0 * scale) < 0.001
        rows.append('%-40s %.4f' % (label, speed))
    table('speed of a full push, units per second', rows)
    check('m1', ok,
          'MV6 in isolation (Player_move called with mode 0 and a full stick push; the velocity '
          'it stores at +0x4bc/+0x4c0 measured): %.3f offline and %.3f in a net game, i.e. 180 '
          'x 0.861945 and 180 x 0.75; a net game in PvP mode B with the word 0x4f7124 clear, or '
          'in the level "watmedal", uses the offline value' % (180 * offline, 180 * net))
    sticks = ((0.0, -1.0), (0.0, -0.5), (0.6, 0.8), (1.0, 1.0), (0.3, 0.0), (-0.2, 0.1))
    ok, rows = True, []
    for lx, ly in sticks:
        rig = MoveRig(elf)
        first = rig.move(lx, ly)
        previous, later = [rig.move(lx, ly) for _ in range(30)][-2:]
        want = 180.0 * min(net * (lx * lx + ly * ly) ** 0.5, net)
        ok &= abs(first[0] - want) < 0.001 and abs(later[0] - want) < 0.001
        ok &= angle_gap(first[1], first[2]) < 2 and angle_gap(later[1], later[2]) < 2
        ok &= first[2] != later[2] and previous[2] == later[2]
        ok &= rig.moved[0][:2] == first[3]
        rows.append('stick (%4.1f, %4.1f): speed %8.4f on the first call, %8.4f on the 31st; facing %6d then %6d'
                    % (lx, ly, first[0], later[0], first[2], later[2]))
    table('net game, six stick positions', rows)
    check('m2', ok,
          'MV6: for six stick positions the speed is 180 x min(S x stick length, S) with S = '
          '0.75, already on the first call from rest - there is no acceleration - and the '
          'velocity points along the character\'s facing (within 2/65536 of a turn), not along '
          'the stick; what lags is the facing, which is still turning on the first call and '
          'has stopped by the 31st.  The vector handed to the move routine is that velocity')
    scaled = [MoveRig(elf, speed_mul=mul, run_speed=run).move(0.0, -1.0)[0]
              for mul, run in ((1.5, 1.0), (1.0, 1.2), (0.5, 1.0), (1.5, 2.0), (4.0, 4.0))]
    cap = 180.0 * raw_to_float(SPEED_CAP)
    check('m3', all(abs(got - want) < 0.001 for got, want in zip(scaled, (202.5, 162.0, 67.5, cap, cap))),
          'MV6: S is multiplied by the record multiplier +0x4c20 and by the level\'s runSpeed '
          '0x4f8418 and then capped at 1.2 (bit pattern 0x3f999999): %s units per second for '
          '(1.5, 1), (1, 1.2), (0.5, 1), (1.5, 2), (4, 4)' % ['%.2f' % v for v in scaled])
    plain = MoveRig(elf)
    loaded = MoveRig(elf, record_words={0x78: 500, 0x7C: 500, 0x80: 500, 0x84: 500, 0x90: 400, 0x94: 400,
                                        0x98: 400, 0x9C: 400, 0x120: float_to_raw(9000.0),
                                        0x124: float_to_raw(10.0), 0x58: 80, 0x59: 80})
    same = all(plain.move(lx, ly)[3] == loaded.move(lx, ly)[3] for lx, ly in sticks)
    check('m4', same and plain.record_reads == {RECORD_SPEED_MUL} and loaded.record_reads == {RECORD_SPEED_MUL},
          'MV6: a record with base and effective statistics of 400-500, level 80 and a carried '
          'load of 9000 against a limit of 10 gives bit-identical velocities for all six stick '
          'positions; the only field of the player record Player_move loads is the multiplier '
          '+0x4c20 (read log)')
    talking = [MoveRig(elf, network=network, dialog=0x01234567).move(0.0, -1.0) for network in (True, False)]
    pads = [pad_choice(elf, network, dialog=dialog) for network in (True, False) for dialog in (0, 1)]
    lockout = [pad_choice(elf, network, lockout=1) for network in (True, False)]
    check('m5', all(result[0] == 0.0 and result[4] == (0.0, 0.0) for result in talking)
          and pads == ['own pad', 'zero pad', 'own pad', 'zero pad'] and lockout == ['own pad', 'zero pad']
          and pad_choice(elf, True, hit_points=0.0) == 'zero pad',
          'MV2 in isolation: with the dialog word 0x8e2d60 non-zero Player_move stores 0 in both '
          'stick fields of the pad it was given and the velocity is 0, and the pad choice at the '
          'top of Player_run (0x1a5640-0x1a5768, entered part-way) hands on the all-zero pad '
          '0x8667f0 - in a net game and offline alike, no network test on either.  (The menu '
          'lockout word, by contrast, swaps the pad only offline.)  That the word is written '
          'only by lockstep code is a search result and was not executed')
    states = (0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 14)
    by_state = {state: [player_run_moves(elf, state, network) for network in (True, False)] for state in states}
    table('Player_run whole, callees stubbed: move routine called (name, mode) net / offline',
          ['state %2d: %s / %s' % (state, by_state[state][0][0], by_state[state][1][0]) for state in states])
    still = all(by_state[state] == [([], 1), ([], 1)] for state in (3, 4, 10, 12))
    modes = {state: [m[0][0][1] if m[0] else None for m in by_state[state]] for state in states}
    listed = {0: [6, 1], 1: [3, 3], 2: [0, 0], 6: [5, 5], 7: [0, 0], 8: [1, 1], 9: [2, 2], 11: [1, 1],
              14: [None, None]}
    check('m6', still and all(modes[state] == want for state, want in listed.items())
          and all(by_state[state][0][1] == 1 for state in states),
          'MV5 in isolation (the whole of Player_run 0x1a5030 on a fake player, every callee '
          'stubbed, once per action state): in states 3, 4, 10 and 0xc it calls none of '
          'Player_move, creature_moveSimple, obj_moveWithCollision and Creature_moveBy - in a '
          'net game and offline - while state 2 calls Player_move with mode 0, state 0 with '
          'mode 6 in a net game and 1 offline, and the other states as the table in '
          'movement-camera.md 4.4 lists (%s).  States 5 and 0xd were NOT run: on a blank player '
          'they load through a pointer the test did not build (0x1ab604, 0x1a5ee8)'
          % ', '.join('%d: %s' % (state, modes[state][0]) for state in states))
    kb = [knockback(elf, 1), knockback(elf, 0), knockback(elf, 0, pvp_b=1), knockback(elf, 1, flags=0x20)]
    check('m7', kb == [(False, 0.0), (True, 28.0), (False, 0.0), (True, 28.0)],
          'MV5, the knock-back half (Creature_applyKnockback 0x115eb8 with 30 units pending): '
          'for a player in a net game it stores 0 at +0x2e8 and returns without a move call; '
          'offline it calls Creature_moveBy and takes 2 off the amount; offline in PvP mode B it '
          'zeroes it like a net game; a monster in a net game is moved as offline')


# ---------------------------------------------------------------------------------------
# z. Floating-point special cases (docs/issues/float-divergence.md, FINDINGS F3, F4, F7)
# ---------------------------------------------------------------------------------------
TURN_DAMP_START, TURN_DAMP_END, TURN_SQRT_DONE = 0x10BB74, 0x10BC28, 0x10BBCC
TURN_SIBLINGS = ((0x10BCA8, 0x10BCC8), (0x10BDB0, 0x10BDD0))    # (function, instruction after its sqrt.s)
DECODER_SQRT_DONE = 0x13CD28
ROOT_CHOPPED, ROOT_NEAREST = 0x3EE4F92D, 0x3EE4F92E
FIRESTORM_RUN, FIRESTORM_LIGHT_STORED, FIRESTORM_CTOR, FIRESTORM_CTOR2 = 0x2D470C, 0x2D48B4, 0x2D41F8, 0x2D4048
INSECTS_START, INSECTS_QUOTIENT_DONE, INSECTS_FIRST_USE, INSECTS_END = 0x30CDC0, 0x30CEEC, 0x30D130, 0x30D134
INSECT_SPEED = 0x434B0DA1                                        # the constant reloaded on arrival, 203.05
CAST_SLOW_START, CAST_SLOW_END, MELEE_SLOW_START, MELEE_SLOW_END = 0x1A81A0, 0x1A8200, 0x1AA178, 0x1AA23C
SLOW_BYTE_START, SLOW_BYTE_END = 0x113604, 0x113818
FP_MAX, FLAG_DIVIDE, FLAG_INVALID = 0x7FFFFFFF, 0x20, 0x40      # sticky bits of the control register


def turn_damping(elf, velocity, nearest, model='ps2'):
    """Creature_turnToward 0x10bb74-0x10bc28 with the wanted angle equal to the facing,
    so the stored angular velocity is v - int(v * sqrt(0.2)).  Returns (new velocity,
    the square root as the instruction produced it)."""
    emu = EE(elf, fpu_model=model)
    emu.fpu_div_nearest = nearest
    creature = emu.alloc(0x400)
    emu.mem.w16(creature + 0x110, velocity & 0xFFFF)
    emu.mem.w16(creature + 0x38, 1000)
    roots = []
    emu.hook(TURN_SQRT_DONE, lambda e: roots.append(e.f[1]))
    emu.r[2], emu.r[16], emu.r[17], emu.r[18] = 1000, 0, creature, 32767
    emu.run(start=TURN_DAMP_START, until={TURN_DAMP_END}, max_steps=100)
    return emu.mem.s16(creature + 0x110), roots


def sibling_root(elf, function, after, nearest, model='ps2'):
    emu = EE(elf, fpu_model=model)
    emu.fpu_div_nearest = nearest
    creature = emu.alloc(0x400)
    emu.mem.w16(creature + 0x110, 500)
    emu.mem.wf32(creature + 0xB0, 2.0)
    roots = []
    emu.hook(after, lambda e: roots.append(e.f[2]))
    emu.follow = set()
    emu.call(function, creature)
    return roots


def decoder_root(elf, nearest, model='ps2'):
    codec = AxisCodec(elf, fpu_model=model, div_nearest=nearest)
    roots = []
    codec.emu.hook(DECODER_SQRT_DONE, lambda e: roots.append(e.f[0]))
    codec.frame(128)
    return roots


def damping_model(velocity, root):
    """v - int(v * root) in the interpreter's arithmetic, wrapped to 16 bits."""
    product = ee_emu.fp_mul(root, ee_emu.fp_from_int(velocity & M32))
    return ee_emu.sx16((velocity - s32(ee_emu.fp_to_int(product))) & 0xFFFF)


def sticky(emu):
    return emu.fcr31 & (FLAG_DIVIDE | FLAG_INVALID)


def firestorm_light(elf, frames_since_start, lifetime=600, grown=0.0, radius=120):
    """FireStorm_run from its entry to the instruction after the light record is stored.
    Returns (stores made, as offsets into the object -> raw value; sticky divide/invalid
    flags; grown radius afterwards)."""
    emu = EE(elf)
    mem = emu.mem
    storm, frame = emu.alloc(0x400), 5000
    mem.w32(G_SIM_FRAME, frame)
    mem.w32(storm + 0x98, frame - 100)
    mem.w32(storm + 0x94, lifetime)
    mem.w32(storm + 0x90, frame - frames_since_start + lifetime)     # the frame it ends on
    mem.w32(storm + 0x4C, 1)
    mem.w32(storm + 0x9C, radius)
    mem.wf32(storm + 0xA0, grown)
    emu.r[4] = storm
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = {MATH_SIN16, MATH_COS16}
    emu.fcr31 &= ~(FLAG_DIVIDE | FLAG_INVALID)
    emu.reset_log()
    emu.run(start=FIRESTORM_RUN, until={FIRESTORM_LIGHT_STORED}, max_steps=5000)
    return {addr - storm: value for _pc, addr, _n, value in emu.writes}, sticky(emu), mem.f32(storm + 0xA0)


def firestorm_ctor(elf, second):
    """A FireStorm constructor with every callee stubbed: the stores of the largest float
    it makes into the object, and the sticky flags."""
    emu = EE(elf)
    storm, position, owner = emu.alloc(0x400), emu.alloc(0x10), emu.alloc(0x100)
    skill, vtable = emu.alloc(0x100), emu.alloc(0x100)
    emu.mem.w32(skill + 0x60, vtable)
    emu.mem.w32(vtable + 0x6C, fake_function(emu, 0, ret=10, name='skill statistic'))
    emu.follow = set()
    emu.fcr31 &= ~(FLAG_DIVIDE | FLAG_INVALID)
    emu.reset_log()
    if second:
        emu.call(FIRESTORM_CTOR2, storm, 5, position, owner, 0, 0, 0, fargs=(1.0,))
    else:
        emu.call(FIRESTORM_CTOR, storm, 5, owner, position, skill)
    return sorted(addr - storm for _pc, addr, _n, value in emu.writes if value == FP_MAX and addr >= storm), sticky(emu)


def insects_step(elf, swarm, victim, now, arrival):
    """SpellTagarsInsects_run 0x30cdc0-0x30d134: the speed quotient and its first use."""
    emu = EE(elf)
    mem = emu.mem
    spell, target, skill, vtable = emu.alloc(0x200), emu.alloc(0x200), emu.alloc(0x100), emu.alloc(0x100)
    for index, value in enumerate(swarm):
        mem.wf32(spell + 0x88 + 4 * index, value)
    for index, value in enumerate(victim):
        mem.wf32(target + 0x10 + 4 * index, value)
    mem.wf32(spell + 0x78, now)
    mem.wf32(spell + 0x38, arrival)                         # arrival time of victim 0
    mem.w32(spell + 8, skill)
    mem.w32(skill + 0x60, vtable)
    mem.w32(vtable + 0x64, fake_function(emu, 0, ret=2, name='skill statistic'))
    seen = {}
    emu.hook(INSECTS_QUOTIENT_DONE, lambda e: seen.setdefault('quotient', (e.f[21], sticky(e))))
    emu.hook(INSECTS_FIRST_USE, lambda e: seen.setdefault('used', e.f[21]))
    emu.stub(POOL_NEW, ret=0, name='pool_new')
    emu.r[17], emu.r[19] = spell, target
    emu.r[29] = emu.stack_hi - 0x1000
    emu.follow = {ATAN2_16, MATH_COS16, MATH_SIN16} | set(ATAN2_INNER)
    emu.fcr31 &= ~(FLAG_DIVIDE | FLAG_INVALID)
    emu.run(start=INSECTS_START, until={INSECTS_END}, max_steps=20000)
    return seen['quotient'][0], seen['quotient'][1], seen['used'], mem.s16(spell + 0x80)


def cast_release(elf, slow, release_frame=20):
    """Player_run 0x1a81a0-0x1a8200 (cast state): the release frame after the slow scale."""
    emu = EE(elf)
    player = emu.alloc(0x600)
    emu.mem.w8(player + 0x2FC, slow)
    emu.r[30], emu.r[16] = player, release_frame
    emu.fset(20, 1.0)
    emu.fcr31 &= ~(FLAG_DIVIDE | FLAG_INVALID)
    emu.run(start=CAST_SLOW_START, until={CAST_SLOW_END}, max_steps=50)
    return s32(emu.r[16]), emu.f[20], sticky(emu)


def melee_thresholds(elf, slow):
    """Player_run 0x1aa178-0x1aa23c (melee state): three float and five integer frame
    thresholds after the slow scale."""
    emu = EE(elf)
    mem = emu.mem
    player = emu.alloc(0x600)
    mem.w8(player + 0x2FC, slow)
    sp = player_run_frame(emu, 0)
    mem.w32(sp + 0xE64, 3)
    for index in range(3):
        mem.wf32(sp + 0x450 + 4 * index, 10.0 * (index + 1))
    for index in range(5):
        mem.w32(sp + 0x480 + 4 * index, 5 * (index + 1))
    emu.r[30] = player
    emu.fset(24, 1.0)
    emu.fcr31 &= ~(FLAG_DIVIDE | FLAG_INVALID)
    emu.run(start=MELEE_SLOW_START, until={MELEE_SLOW_END}, max_steps=500)
    return ([mem.u32(sp + 0x450 + 4 * index) for index in range(3)],
            [mem.s32(sp + 0x480 + 4 * index) for index in range(5)], sticky(emu))


def slow_byte(elf, counter=0, frames=0, chill=0.0, flags=0x60):
    """Creature_run 0x113604-0x113818: the slow byte +0x2fc from the chill timer +0x344
    and status counter 7 (+0x388, started `frames` ago)."""
    emu = EE(elf)
    mem = emu.mem
    creature = emu.alloc(0x600)
    mem.w32(creature + 0x0C, flags)
    mem.w32(G_SIM_FRAME, 1000)
    mem.w32(creature + 0xF0, 1000 - frames)
    mem.w32(creature + 0x388, counter)
    mem.wf32(creature + 0x344, chill)
    emu.r[17] = creature
    emu.follow = set()
    emu.run(start=SLOW_BYTE_START, until={SLOW_BYTE_END}, max_steps=200)
    return mem.u8(creature + 0x2FC)


def test_float_cases(elf):
    models = ('ps2', 'ps2g1', 'chop', 'nearest')
    sites = {}
    for nearest in (False, True):
        sites[nearest] = [turn_damping(elf, 500, nearest)[1], decoder_root(elf, nearest)] + \
            [sibling_root(elf, function, after, nearest) for function, after in TURN_SIBLINGS]
    by_adder = {model: turn_damping(elf, 500, False, model)[1] for model in models}
    check('z1', all(len(r) >= 1 and set(r) == {ROOT_CHOPPED} for r in sites[False])
          and all(set(r) == {ROOT_NEAREST} for r in sites[True])
          and all(by_adder[m] == [ROOT_CHOPPED] for m in ('ps2', 'ps2g1', 'chop')) and by_adder['nearest'] == [ROOT_NEAREST],
          'F7 in isolation: the sqrt.s of the constant 0x3e4ccccc is really executed at run time '
          'at all four sites (0x10bbc8 in Creature_turnToward, 0x10bcc4 and 0x10bdcc in its two '
          'siblings, 0x13cd24 in the stick decoder - each reached by running the function, the '
          'result read from the register on the next instruction).  With the interpreter\'s '
          'square root truncated the result is 0x3ee4f92d at every site, with it rounded to '
          'nearest 0x3ee4f92e; the three truncating adder models do not change it.  Which of the '
          'two a console produces is not something this interpreter can tell')
    chopped, nearest_root = ROOT_CHOPPED, ROOT_NEAREST
    differing = [v for v in range(-32768, 32768) if damping_model(v, chopped) != damping_model(v, nearest_root)]
    rng = random.Random(7)
    sample = differing + [rng.randrange(-32768, 32768) for _ in range(300)]
    agree = all(turn_damping(elf, v, False)[0] == damping_model(v, chopped)
                and turn_damping(elf, v, True)[0] == damping_model(v, nearest_root) for v in sample)
    smallest = min(abs(v) for v in differing) if differing else 0
    check('z2', len(differing) == 34 and smallest == 2889 and agree,
          'what the last bit of that root changes (MV1): the damping step of Creature_turnToward, '
          'v - int(v x root), computed in the interpreter\'s arithmetic for all 65,536 angular '
          'velocities gives a different result for %d of them, the smallest +-%d - the 34 and '
          '2889 of float-divergence.md - and the game\'s own stretch 0x10bb74-0x10bc28, executed '
          'under both square-root roundings for those %d velocities and 300 others, stores '
          'exactly the model\'s value every time' % (len(differing), smallest, len(differing)))

    young, grown_up, fading_small, fading = (firestorm_light(elf, 10), firestorm_light(elf, 31),
                                             firestorm_light(elf, 5, lifetime=20), firestorm_light(elf, 560, grown=50.0))
    ctors = [firestorm_ctor(elf, False), firestorm_ctor(elf, True)]
    light_only = all(set(stores) <= {0x6C, 0x70, 0x74, 0x78, 0xA0} for stores, _f, _g in (young, grown_up, fading_small, fading))
    check('z3', ctors == [([0x70, 0x78], FLAG_DIVIDE)] * 2
          and young[0] == {0x6C: 0, 0x74: 0, 0x70: FP_MAX, 0x78: FP_MAX} and young[1] == FLAG_DIVIDE
          and grown_up[1] == 0 and grown_up[2] == 1.0 and FP_MAX not in grown_up[0].values()
          and fading_small[0].get(0x70) == FP_MAX and fading_small[1] == FLAG_DIVIDE and fading[1] == 0 and light_only,
          'F3, FireStorm (both constructors with callees stubbed; FireStorm_run from its entry '
          'to the store of the light record): each constructor divides 1.0 by 0.0 and stores '
          'the result, the largest float 0x7fffffff, at object +0x70 and +0x78; FireStorm_run '
          'in the first 30 frames of a storm computes 1 / (0 x 0) at 0x2d4854 and stores the '
          'same value there with a radius of 0 at +0x6c/+0x74; from frame 31 the radius grows '
          'and the quotient is finite.  The fade-out branch (0x2d48a8) divides by zero only '
          'for a storm still at radius 0 in its last second (one whose whole life is under 31 '
          'frames).  The stretch stores nowhere but those four light fields and the grown '
          'radius; who reads the two fields afterwards was not executed')
    arriving, on_top, travelling, overdue = (
        insects_step(elf, (100.0, 100.0, 0.0), (160.0, 180.0, 0.0), 10.0, 10.0),
        insects_step(elf, (100.0, 100.0, 0.0), (100.0, 100.0, 0.0), 10.0, 10.0),
        insects_step(elf, (100.0, 100.0, 0.0), (160.0, 180.0, 0.0), 10.0, 12.0),
        insects_step(elf, (100.0, 100.0, 0.0), (160.0, 180.0, 0.0), 10.0, 9.99))
    check('z4', arriving[:3] == (FP_MAX, FLAG_DIVIDE, INSECT_SPEED) and on_top[:3] == (FP_MAX, FLAG_INVALID, INSECT_SPEED)
          and overdue[2] == INSECT_SPEED and overdue[1] == 0 and raw_to_float(overdue[0]) < 0
          and travelling[1] == 0 and travelling[2] == travelling[0] and abs(raw_to_float(travelling[0]) - 203.05) < 0.01
          and (arriving[3], on_top[3], travelling[3], overdue[3]) == (-1, -1, 0, -1),
          'F3, Tagar\'s Insects (SpellTagarsInsects_run entered part-way at 0x30cdc0): on the '
          'frame the stored arrival time equals "now" the speed quotient at 0x30cee8 is distance '
          '/ 0 = 0x7fffffff (0 / 0, also 0x7fffffff, with the swarm exactly on the victim); on '
          'that frame the arrival test passes, the victim index is cleared and the register is '
          'reloaded with the constant 203.05 before the instruction that first uses it '
          '(0x30d130).  A negative divisor (arrival already past) is replaced the same way.  '
          'While the swarm is still travelling the quotient is finite (%.2f) and is what is '
          'used.  So the divide by zero does not reach the position, as the row says'
          % raw_to_float(travelling[0]))
    cast = {slow: cast_release(elf, slow) for slow in (0, 1, 30, 59, 60, 61)}
    melee = {slow: melee_thresholds(elf, slow) for slow in (0, 30, 59, 60)}
    check('z5', [cast[slow][0] for slow in (0, 1, 30, 59, 61)] == [20, 20, 40, 1200, 20]
          and cast[60] == (0x7FFFFFFF, 0, FLAG_DIVIDE) and all(cast[slow][2] == 0 for slow in (0, 1, 30, 59, 61))
          and melee[0] == ([float_to_raw(v) for v in (10.0, 20.0, 30.0)], [5, 10, 15, 20, 25], 0)
          and melee[59][1] == [300, 600, 900, 1200, 1500] and melee[59][2] == 0
          and melee[60] == ([FP_MAX] * 3, [0x7FFFFFFF] * 5, FLAG_DIVIDE),
          'F4 in isolation (the two stretches of Player_run that scale by the slow byte +0x2fc, '
          'entered part-way): the cast state divides the release frame by speed x (60 - slow) x '
          '1/60 - frame 20 becomes 20, 40, 1200 for slow 1, 30, 59 - and for slow 60 the divisor '
          'is 0, the quotient the largest float and the converted frame 2147483647: the cast '
          'is never released.  The melee state divides three float and five integer thresholds '
          'by the same factor and at slow 60 all eight are the maximum.  A byte of 61 or more '
          'is outside the scaled range and leaves the values alone')
    ramp = [slow_byte(elf, counter=100, frames=f) for f in (0, 1, 10, 29, 30, 31, 100)]
    after_ramp = [slow_byte(elf, counter=c, frames=40) for c in (20, 30, 31, 40, 60, 200)]
    chilled = [slow_byte(elf, chill=c) for c in (5.0, 29.5, 45.0, 59.0, 70.0, 500.0)]
    check('z6', ramp == [0, 2, 20, 58, 60, 60, 60] and after_ramp == [20, 30, 60, 60, 60, 60]
          and chilled == [4, 29, 30, 30, 30, 30],
          'F4, how the byte reaches 60 (Creature_run entered part-way at 0x113604, a player): '
          'from the chill timer alone it is capped at 30 however large the timer (%s for 5 to '
          '500); with status counter 7 set it is twice the frames since the counter started for '
          '30 frames (%s at 0, 1, 10, 29, 30, 31, 100 frames) and then 60.  Sharper than '
          'movement-camera.md 4.6, which says "then the counter value up to 60": after the ramp '
          'the byte is 60 for any counter of 31 or more and the counter itself only below that '
          '(%s for counters 20, 30, 31, 40, 60, 200).  Whether anything sets counter 7 stays '
          'Unknown (D16)' % (chilled, ramp, after_ramp))


# ---------------------------------------------------------------------------------------
# n. The four arena-entry sections of the patch file (docs/issues/arena-entry.md, FINDINGS
#    E6, E8, E9, E13): 0x13b21c, 0x199df8, 0x217f58, 0x1dd1f0.  One check each.
# ---------------------------------------------------------------------------------------
REBASE_TEST_START, REBASE_SKIPPED, REBASE_GOES_ON, X1_SITE = 0x13B1C4, 0x13B59C, 0x13B224, 0x13B21C
G_GHOST_REBASE_FRAME, G_EXCLUDE_MASK = 0x4027D4, 0x4039B8
CUT_SKIP_START, CUT_SKIPPED, CUT_NOT_SKIPPED, X2_SITE, G_LEVEL_TEX_NAME = 0x199D90, 0x199E34, 0x199EE0, 0x199DF8, 0x44FE18
SAVE_ARM_AUTOSAVE, SAVE_DAEMON_RUN, SAVE_GAME, X3_SITE = 0x217F14, 0x2188A8, 0x218128, 0x217F58
G_AUTOSAVE_COUNTDOWN, G_MENU_OPEN_FLAG = 0x88D40C, 0x41B4F8
NOTICE_START, NOTICE_END, X4_SITE, RUN_POST_ACTION, RUN_SCRIPT_BY_NAME, LIBC_STRCPY = 0x1DD008, 0x1DD1F8, 0x1DD1F0, 0x1EDAC0, 0x1ED694, 0x3B868C
G_NOTICE_OPEN, G_POST_ACTION, HELP_BOX_START, HELP_BOX_STOPS = 0x41B518, 0x86FA80, 0x1DCF30, (0x1DCF68, 0x1DCFD8)


def rebase_test(elf, frames_since_rebase, force=0, has_object=True, patched=False):
    """net_frameLoop 0x13b1c4 on: is the prediction copy re-made on this call?  Returns
    (the code goes on to the rebase at 0x13b224, the stores it made on the way)."""
    world = World(elf, players=2, local_slot=0, network=True)
    emu, mem = world.emu, world.emu.mem
    if patched and apply_section_at(emu, X1_SITE) is None:
        raise LookupError('no patch-file section patches 0x%x' % X1_SITE)
    if not has_object:
        world.set_table(0, 0)
    mem.w32(G_NET_FRAME, 5000)
    mem.w32(G_GHOST_REBASE_FRAME, 5000 - frames_since_rebase)
    mem.w8(G_FORCE_REBASE, force)
    frame = emu.alloc(0x400)
    mem.w32(frame + 0x37C, 0)                               # the local slot, as net_frameLoop keeps it
    emu.r[30] = frame
    emu.reset_log()
    emu.run(start=REBASE_TEST_START, until={REBASE_SKIPPED, REBASE_GOES_ON}, max_steps=50)
    return emu.pc == REBASE_GOES_ON, [w[1:] for w in emu.writes]


def cutscene_skip(elf, pressed, patched=False, level=b'drunare', cut_frame=10):
    """cut_runFrame 0x199d90 on: is the cutscene ended on this call?  pressed: the
    pressed-button word of each slot's lockstep pad."""
    emu = EE(elf)
    mem = emu.mem
    if patched and apply_section_at(emu, X2_SITE) is None:
        raise LookupError('no patch-file section patches 0x%x' % X2_SITE)
    mem.write(G_LEVEL_TEX_NAME, level + b'\0')
    mem.w32(G_NUM_PLAYERS, len(pressed))
    mem.w32(G_CUT_FRAME, cut_frame)
    for slot, word in enumerate(pressed):
        mem.w32(G_PADS + slot * PAD_SIZE + 0x0C, word)
    emu.r[18] = 0x450000
    emu.follow = {STRCMP}
    emu.run(start=CUT_SKIP_START, until={CUT_SKIPPED, CUT_NOT_SKIPPED}, max_steps=2000)
    return emu.pc == CUT_SKIPPED


def entry_autosave(elf, gate_open, patched=False):
    """save_armAutosave (the call a level load ends with) and then one save_daemonRun on
    a machine whose autosave gate is open, or shut by a full-screen menu.  Returns (the
    armed word after the load, save_game calls made by the daemon, the word afterwards,
    the arming function's calls and stores)."""
    emu = EE(elf)
    mem = emu.mem
    if patched and apply_section_at(emu, X3_SITE) is None:
        raise LookupError('no patch-file section patches 0x%x' % X3_SITE)
    camera = emu.alloc(0x100)
    mem.w32(camera + 0x34, 1)
    mem.w32(G_LOCAL_CAMERA, camera)
    mem.w32(G_MEMCARD_STATE, 0xFFFFFFFF)
    mem.w32(G_MENU_OPEN_FLAG, 0 if gate_open else 1)
    mem.w8(G_NETWORK_MODE, 1)
    emu.follow = {MEMCARD_GET_STATE}
    emu.reset_log()
    emu.call(SAVE_ARM_AUTOSAVE)
    arm_log = run_log(emu)
    armed = mem.s32(G_AUTOSAVE_COUNTDOWN)
    emu.follow = set()
    emu.reset_log()
    emu.call(SAVE_DAEMON_RUN)
    saves = [(c.args[0] & M32, c.args[1] & M32) for c in emu.calls if c.target == SAVE_GAME]
    return armed, saves, mem.s32(G_AUTOSAVE_COUNTDOWN), arm_log


def notice_close(elf, notice_open, patched=False, slot=1):
    """help_task 0x1dd008-0x1dd1f8, the notice box of one slot, run twice: once with the
    confirm button up, once with it pressed in that slot's pad.  A post action named
    "after" is pending.  Returns (scripts run, the pending name afterwards, the notice
    flag and lockout word afterwards)."""
    emu = EE(elf)
    mem = emu.mem
    if patched and apply_section_at(emu, X4_SITE) is None:
        raise LookupError('no patch-file section patches 0x%x' % X4_SITE)
    mem.w8(G_NETWORK_MODE, 1)
    mem.w8(G_NOTICE_OPEN + slot, 1 if notice_open else 0)
    mem.write(G_POST_ACTION, b'after\0')
    mem.w32(G_PAD_CONFIRM, 0x40)
    ran = []
    emu.stub(RUN_SCRIPT_BY_NAME, function=lambda e: ran.append(e.mem.cstr(e.r[4] & M32)) or 0, name='script_runByName')
    for pressed in (0, 0x40):
        mem.w32(G_PADS + slot * PAD_SIZE + 0x08, pressed)
        mem.w32(G_PADS + slot * PAD_SIZE + 0x0C, pressed)
        emu.r[22], emu.r[23] = slot, slot * PAD_SIZE
        emu.r[29] = emu.stack_hi - 0x1000
        emu.follow = {RUN_POST_ACTION, LIBC_STRCPY}
        emu.run(start=NOTICE_START, until={NOTICE_END}, max_steps=5000)
    return ran, mem.cstr(G_POST_ACTION), mem.u8(G_NOTICE_OPEN + slot), mem.u32(G_MENU_LOCKOUT)


def help_box_close(elf, network):
    """The sibling path, 0x1dcf30 on: the full-screen help box closed by the confirm
    button.  Returns whether script_runPostAction was called."""
    emu = EE(elf)
    mem = emu.mem
    mem.w8(G_NETWORK_MODE, network)
    mem.w32(G_PAD_CONFIRM, 0x40)
    mem.w32(0x4028DC, 0x40)                                 # pressed word of raw pad 0
    emu.r[2], emu.r[18], emu.r[23], emu.r[30], emu.r[22] = 0x420000, 0, 0x400000, 0x420000, 0x4F0000
    emu.follow = set()
    emu.reset_log()
    emu.run(start=HELP_BOX_START, until=set(HELP_BOX_STOPS), max_steps=50)
    return any(c.target == RUN_POST_ACTION for c in emu.calls)


def test_arena_entry(elf):
    if pnach_section_at(X1_SITE) is None:
        skip('n1', 'the patch file has no section for 0x13b21c')
    else:
        shipped = {(frames, force, obj): rebase_test(elf, frames, force, obj)
                   for frames in (0, 30, 31, 100) for force in (0, 1) for obj in (True, False)}
        patched = {key: rebase_test(elf, *key, patched=True) for key in shipped}
        due = {key for key, (goes_on, _stores) in shipped.items() if goes_on}
        check('n1', due == {key for key in shipped if key[2] and (key[0] >= 31 or key[1])}
              and not any(goes_on for goes_on, _stores in patched.values())
              and all(stores == [(G_EXCLUDE_MASK, 4, 0x200000)] for _g, stores in list(shipped.values()) + list(patched.values())),
              'patch "no prediction copy" (0x13b21c) and E6 (net_frameLoop entered part-way at '
              '0x13b1c4): shipped, the code goes on to re-make the copy when 31 or more frames '
              'have passed since this machine\'s last rebase frame 0x4027d4, or the force flag is '
              'set, and the local player has an object - so two machines at the same net frame '
              'whose rebase frames are 30 and 31 behind differ, one re-clones on that call and the '
              'other does not.  Patched, no combination of the three inputs reaches the rebase '
              'code; the one store on the way (the exclude mask) is unchanged.  The rebase itself '
              '(0x13b224 on) was not run here; Player_clone is run in group e')
    if pnach_section_at(X2_SITE) is None:
        skip('n2', 'the patch file has no section for 0x199df8')
    else:
        pads = ((0, 0), (0x800, 0), (0, 0x800), (0x7FF, 0xF7FF))
        shipped = [cutscene_skip(elf, pressed) for pressed in pads]
        patched = [cutscene_skip(elf, pressed, patched=True) for pressed in pads]
        ending = [cutscene_skip(elf, (0x800, 0), patched=flag, level=b'endgood', cut_frame=frame)
                  for flag in (False, True) for frame in (300, 301)]
        check('n2', shipped == [False, True, True, False] and patched == [True] * 4
              and ending == [False, True, False, True] and not cutscene_skip(elf, (), patched=True),
              'patch "cutscenes end in the tick they start" (0x199df8), cut_runFrame entered '
              'part-way at 0x199d90: shipped, a cutscene is ended on the call in which any '
              'slot\'s LOCKSTEP pad has pressed bit 0x800, and not otherwise - the same on every '
              'machine, there is no per-machine input here; patched, it is ended on the first '
              'call whatever the pads say.  In the levels "endgood" and "endbad" both versions '
              'leave the skip test out until cutscene frame 301.  A patched and an unpatched '
              'machine given the same pads take different exits, which is the mix the patch '
              'text warns about.  What the skip path then does was not run')
    if pnach_section_at(X3_SITE) is None:
        skip('n3', 'the patch file has no section for 0x217f58')
    else:
        open_s, shut_s = entry_autosave(elf, True), entry_autosave(elf, False)
        open_p, shut_p = entry_autosave(elf, True, patched=True), entry_autosave(elf, False, patched=True)
        same_calls = open_s[3][0] == open_p[3][0]
        store_pairs = list(zip(open_s[3][1], open_p[3][1]))
        check('n3', open_s[:3] == (1, [(0, 1)], 0) and shut_s[:3] == (1, [], 1)
              and open_p[:3] == (0, [], 0) and shut_p[:3] == (0, [], 0) and same_calls
              and [(a[1:], b[1:]) for a, b in store_pairs] == [((G_AUTOSAVE_COUNTDOWN, 4, 1), (G_AUTOSAVE_COUNTDOWN, 4, 0))],
              'patch "no autosave on entering a level" (0x217f58) and E8: shipped, '
              'save_armAutosave stores 1 in 0x88d40c, and the next save_daemonRun on a machine '
              'whose gate is open (card idle, no full-screen menu, camera following) calls '
              'save_game(0, 1) and disarms, while on a machine with a full-screen menu open it '
              'saves nothing and stays armed - the snapshot is taken on a per-machine tick.  '
              'Patched, the function makes the same calls and its one store is 0 instead of 1: '
              'neither machine saves and both words end 0.  save_game itself was a stub')
    if pnach_section_at(X4_SITE) is None:
        skip('n4', 'the patch file has no section for 0x1dd1f0')
    else:
        owner, other = notice_close(elf, True), notice_close(elf, False)
        p_owner, p_other = notice_close(elf, True, patched=True), notice_close(elf, False, patched=True)
        check('n4', owner == (['after'], '', 0, 60) and other == ([], 'after', 0, 0)
              and p_owner == ([], 'after', 0, 60) and p_other == other
              and (help_box_close(elf, 1), help_box_close(elf, 0)) == (False, True),
              'patch "closing a notice box does not run the pending script" (0x1dd1f0) and E9, '
              'help_task entered part-way at 0x1dd008 in a net game with a post action pending: '
              'shipped, on the machine where the slot\'s notice flag is set, releasing and then '
              'pressing the confirm button runs the pending script (script_runPostAction real, '
              'the script itself a stub) and empties the pending name, while a machine without '
              'the flag does nothing and keeps the name - one machine has run the script and '
              'the other has not.  Patched, the name stays pending on both and no script runs; '
              'what still differs is the menu lockout word, set to 60 on the closing machine '
              'only (per machine by nature, FINDINGS D26).  The sibling path for the full-screen '
              'help box (0x1dcf30) calls script_runPostAction offline and not in a net game')


def test_kill(elf):
    test_k1_interact(elf)
    test_k2_potion(elf)
    test_k3_stats(elf)
    test_k5_to_k8(elf)


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
            if len(was) == 1 and len(actual) > 1:           # one word quoted "at both addresses"
                was = was * len(actual)
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
    ('k', 'kill', 'kill, experience, loot and pick-up: Player_run 0x1a5b98-0x1a5c28, Player_usePotion 0x1b9cb8, the stats page 0x1d2c20-0x1d2d80, and the patches at 0x1a5c0c, 0x1b9fcc, 0x1ba3ac, 0x1d2d30', test_kill),
    ('s', 'breakers', 'sync breakers: checksum exchange 0x1e3e4c / 0x1d8ca0, Savepoint prompt 0x28da58, card latch 0x4f8f28, debug file 0x2173c8, and the patches at 0x1375dc, 0x28da74, 0x217448', test_sync_breakers),
    ('m', 'movement', 'player movement: Player_move 0x1b4020, Player_run 0x1a5030, Creature_applyKnockback 0x115eb8', test_movement),
    ('z', 'float', 'float special cases: sqrt.s sites 0x10bbc8/0x10bcc4/0x10bdcc/0x13cd24, FireStorm 0x2d470c, Tagar\'s Insects 0x30cdc0, slow-byte divides 0x1a81a0 and 0x1aa178', test_float_cases),
    ('n', 'entry', 'arena-entry patches: net_frameLoop 0x13b1c4, cut_runFrame 0x199d90, save_armAutosave 0x217f14, help_task 0x1dd008', test_arena_entry),
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
