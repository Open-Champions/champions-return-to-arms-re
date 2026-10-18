#!/usr/bin/env python3
"""difftest_levels.py - compare the round-2 parts of tools/ref_levels.py with the game's own
machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.  No disc
file is read: every lump, chunk, piece and flag word is made up here.

  python3 tools/difftest_levels.py [SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]
                                   [--no-alt]

Properties (docs/level-flow.md section 16):

  light_level      0x1e60e0-0x1e6158 with light_setLevelLight 0x14a2d8 run for real (its
                   two callees stubbed): g_worldLightLevel 0x5d347c and the two alpha
                   bytes against base_light_level, for every combination of the two flag
                   bits and random flag words
  chunk_light      0x189008-0x189070 of world_drawChunk: the constant handed to 0x149ab8
                   (or "dynamic") and the chunk's flag word afterwards, against
                   chunk_header_state
  world_pick       lump_findNthByExtension 0x171fd8 with libc strrchr/strcmp run for real,
                   on random directories, against first_entry_with_extension
  world_pick_load  game_loadLevel 0x1e5954-0x1e59c0 (lump_load stubbed to return the
                   synthetic lump): the pointer stored in g_world 0x44fdc8; a directory
                   with no .world entry must fault
  recall_tick      player_recallTick 0x1b5fa0, every callee stubbed, called once per
                   simulated tick with random cutscene flags and alive counts: the
                   countdown byte and the outcome of each call, against RecallCountdown
  move_piece       world_movePiece 0x182c98 with math_sin16/math_cos16/floorf run for
                   real: the five fields of every chunk of the piece, and nothing else
                   written, against move_piece
  move_piece_rest  one fixed case: angle 0 still moves x by a quarter unit (sin16(0) != 0)

Floats are compared as 32-bit patterns.  The default floating-point model gets the full
sample; with alternates on, a tenth of move_piece is repeated under the other adder models
and the multiplier-bias and divide-rounding switches, with ref_world and ref_core switched
the same way (as in difftest_world.py).  Agreement shows the model does the same
operations in the same order; it does not show that either matches a console in the last
bit (docs/issues/dynamic-tests.md).

Note on tools/dis.py: this script, like the others, puts tools/ at the END of sys.path so
that tools/dis.py cannot shadow the standard library's dis (which unittest imports through
inspect).  Running `python3 -m unittest` with tools/ as the current directory still breaks,
because the current directory comes first.  Proposed fix (not applied here: 24 tracked files
name the script): `git mv tools/dis.py tools/eedis.py` and update those references; no module
imports it, so nothing else changes.
"""
import hashlib
import os
import random
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE, MemoryFault              # noqa: E402
import ref_core as C                            # noqa: E402
import ref_levels as L                          # noqa: E402
import ref_world as W                           # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF

FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

# addresses
A_LIGHT_START, A_LIGHT_END = 0x1E60E0, 0x1E615C
A_SET_LEVEL_LIGHT = 0x14A2D8
A_RECALC_SUN, A_OBJ_LIGHT = 0x148018, 0x148340
G_WORLD_LIGHT_LEVEL = 0x5D347C
A_CHUNK_LIGHT, A_CHUNK_LIGHT_CONST, A_CHUNK_LIGHT_DYN = 0x189008, 0x189058, 0x189070
A_LIGHT_CONST = 0x149AB8
A_FIND_NTH_EXT = 0x171FD8
A_STRRCHR, A_STRCMP = 0x3B95D8, 0x3B8534
A_PICK_START, A_PICK_END = 0x1E5954, 0x1E59C0
A_LUMP_LOAD, A_SPRINTF, A_PRINTF, A_19EDCC = 0x173558, 0x3B7EF0, 0x355490, 0x19EDCC
G_WORLD = 0x44FDC8
A_RECALL_TICK = 0x1B5FA0
A_RECALL_AURA, A_RECALL_CLEAR, A_RECALL_PAST_CUT, A_RECALL_PAST_ALIVE = \
    0x1B5FE8, 0x1B60A4, 0x1B6124, 0x1B6134
A_RECALL_EPILOGUE = 0x1B6300
G_RECALL_COUNTDOWN, G_CUTSCENE_ACTIVE, G_ALIVE_COUNT, G_NUM_PLAYERS = \
    0x41B51D, 0x44FCD0, 0x4F8420, 0x4D8AE0
A_MOVE_PIECE = 0x182C98

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'alt': True}
RESULTS = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def n_cases(full):
    return max(1, full // 10) if OPTIONS['quick'] else full


def report(name, cases, failures, what):
    ok = not failures
    RESULTS.append(ok)
    print('%s %-16s %6d cases  %s' % ('PASS' if ok else 'FAIL', name, cases, what))
    if failures and OPTIONS['verbose']:
        for f in failures[:3]:
            print('     ', f)


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'] in name


class Rig:
    def __init__(self, elf):
        self.emu = EE(elf)
        self.emu.record_writes = True
        self.fresh = {}

    def set_fpu(self, config):
        model, bias, nearest = config
        self.emu.fpu_model = model
        self.emu.fpu_mul_bias = bias
        self.emu.fpu_div_nearest = nearest
        W.set_fpu(model, bias, nearest)
        C.set_fpu(model, bias, nearest)

    def alloc(self, size):
        """A zeroed block.  reset() rewinds the bump heap, and EE.alloc zeroes only pages it
        maps for the first time, so blocks are cleared here."""
        addr = self.emu.alloc(size)
        self.emu.mem.write(addr, bytes(size))
        return addr

    def cstring(self, text):
        raw = text.encode('ascii') + b'\0'
        addr = self.alloc(len(raw))
        self.emu.mem.write(addr, raw)
        return addr

    def run_stretch(self, start, stops):
        emu = self.emu
        emu.r[31] = emu.RETURN_ADDR
        reason = emu.run(start, until=stops, max_steps=200000)
        return reason, emu.pc

    def reset(self):
        emu = self.emu
        emu.reset_log()
        emu.hooks.clear()
        emu.stub_names.clear()
        emu.follow = None
        emu._heap = emu.HEAP_LO
        emu.r[29] = emu.stack_hi - 0x100


# ---- light level -------------------------------------------------------------------------

def prop_light_level(rig, rnd):
    emu = rig.emu
    flags_list = [0, L.LEVEL_FLAG_LIGHT_20, L.LEVEL_FLAG_LIGHT_40,
                  L.LEVEL_FLAG_LIGHT_20 | L.LEVEL_FLAG_LIGHT_40]
    flags_list += [rnd.getrandbits(32) for _ in range(n_cases(200))]
    fails = []
    for flags in flags_list:
        rig.reset()
        emu.stub(A_RECALC_SUN)
        emu.stub(A_OBJ_LIGHT)
        emu.mem.w32(G_WORLD_LIGHT_LEVEL, 0xDEADBEEF)
        emu.mem.w8(0x5D3473, 0x55)
        emu.mem.w8(0x5D347B, 0x55)
        emu.mem.w32(0x44FE08, flags)
        emu.set_reg('fp', 0x450000)              # lw $4, -0x1f8($fp) reads 0x44fe08
        emu.set_reg('sp', 0x01F80000)
        reason, pc = rig.run_stretch(A_LIGHT_START, (A_LIGHT_END,))
        got = (emu.mem.u32(G_WORLD_LIGHT_LEVEL), emu.mem.u8(0x5D3473), emu.mem.u8(0x5D347B))
        want = (L.base_light_level(flags), 0, 0)
        if reason != 'stop' or got != want:
            fails.append('flags %08x: game %r, model %r (%s at %08x)' % (flags, got, want, reason, pc))
    report('light_level', len(flags_list), fails,
           'g_worldLightLevel and the alpha bytes from the level flag word')


# ---- chunk light ---------------------------------------------------------------------------

def prop_chunk_light(rig, rnd):
    emu = rig.emu
    cases = []
    for bits in range(8):
        f = (0x100 if bits & 1 else 0) | (0x200 if bits & 2 else 0) | (0x2000 if bits & 4 else 0)
        cases.append(f)
        cases.append(f | 0x10 | 0x400)
    cases += [rnd.getrandbits(32) for _ in range(n_cases(200))]
    fails = []
    for flags in cases:
        rig.reset()
        seen = []
        emu.stub(A_LIGHT_CONST, function=lambda e: seen.append(W.s32(e.r[5] & M32)) or 0)
        chunk = rig.alloc(0x40)
        buf = rig.alloc(0x40)
        frame = rig.alloc(0x100)
        emu.mem.w32(chunk + 0x24, flags)
        emu.mem.w32(frame, buf)                  # sp+0 holds the packet write pointer
        emu.set_reg('s0', chunk)
        emu.set_reg('sp', frame)
        reason, pc = rig.run_stretch(A_CHUNK_LIGHT, (A_CHUNK_LIGHT_CONST, A_CHUNK_LIGHT_DYN))
        got_light = 'dynamic' if pc == A_CHUNK_LIGHT_DYN else (seen[0] if seen else None)
        got = (got_light, emu.mem.u32(chunk + 0x24))
        want = (L.chunk_header_state(flags)[3], flags & ~0x100 & M32)
        if reason != 'stop' or got != want:
            fails.append('flags %08x: game %r, model %r' % (flags, got, want))
    report('chunk_light', len(cases), fails,
           'constant light level or dynamic, and flag 0x100 cleared, per chunk flags')


# ---- WORLD entry ---------------------------------------------------------------------------

NAME_PARTS = ('a', 'lev', 'x.y', 'world', 'WORLD', 'worl', 'worlds', 'ob', 'scr', 'tex', '')


def random_names(rnd):
    names = []
    for _ in range(rnd.randint(0, 9)):
        stem = rnd.choice(('a', 'b', 'lev', 'x.y', 'z1', '', 'world'))
        kind = rnd.random()
        if kind < 0.35:
            names.append(stem + '.world')
        elif kind < 0.45:
            names.append(stem + '.world.' + rnd.choice(NAME_PARTS))
        elif kind < 0.55:
            names.append(stem)                    # no dot
        else:
            names.append(stem + '.' + rnd.choice(NAME_PARTS))
    rnd.shuffle(names)
    return names


def build_lump(rig, names):
    emu = rig.emu
    lump = rig.alloc(4 + 12 * max(1, len(names)))
    emu.mem.w16(lump, len(names))
    datas = []
    for i, name in enumerate(names):
        data = rig.alloc(16)
        datas.append(data)
        emu.mem.w32(lump + 4 + 12 * i, rig.cstring(name))
        emu.mem.w32(lump + 8 + 12 * i, data)
        emu.mem.w32(lump + 12 + 12 * i, 16)
    return lump, datas


def prop_world_pick(rig, rnd):
    emu = rig.emu
    total, fails = 0, []
    for _ in range(n_cases(300)):
        names = random_names(rnd)
        for n in (0, 1, 2):
            rig.reset()
            emu.follow = {A_STRRCHR, A_STRCMP}
            lump, _ = build_lump(rig, names)
            ext = rig.cstring('world')
            rec = emu.call(A_FIND_NTH_EXT, lump, ext, n) & M32
            got = None if rec == 0 else names[(rec - lump - 4) // 12]
            want = L.first_entry_with_extension(names, 'world', n)
            total += 1
            if got != want:
                fails.append('%r n=%d: game %r, model %r' % (names, n, got, want))
    report('world_pick', total, fails, 'n-th entry with extension world, directory order')


def prop_world_pick_load(rig, rnd):
    emu = rig.emu
    total, fails = 0, []
    for _ in range(n_cases(100)):
        names = random_names(rnd)
        rig.reset()
        lump, datas = build_lump(rig, names)
        emu.follow = {A_FIND_NTH_EXT, A_STRRCHR, A_STRCMP}
        emu.stub(A_LUMP_LOAD, ret=lump)
        emu.mem.w32(G_WORLD, 0xDEADBEEF)
        emu.set_reg('sp', 0x01F80000)            # inside the stack, away from the test heap
        emu.set_reg('s7', rig.cstring('leva'))
        emu.set_reg('s2', 0x450000)              # set in the delay slot before the start
        want = L.first_entry_with_extension(names, 'world')
        total += 1
        try:
            reason, pc = rig.run_stretch(A_PICK_START, (A_PICK_END,))
            got = emu.mem.u32(G_WORLD)
            got = names[datas.index(got)] if got in datas else ('stored %08x' % got)
        except MemoryFault as e:                 # lw 4($2) with $2 = 0 (no null test)
            got = 'fault' if (e.pc, e.addr) == (0x1E59AC, 4) else repr(e)
        if want is None:
            want = 'fault'
        if got != want:
            fails.append('%r: game %r, model %r' % (names, got, want))
    report('world_pick_load', total, fails, 'g_world after game_loadLevel step 8')


# ---- recall countdown ----------------------------------------------------------------------

def prop_recall_tick(rig, rnd):
    emu = rig.emu
    total, fails = 0, []
    starts = [0, 1, 2, 59, 60, 61, 0x7F, 0x80, 0xFF]
    starts += [rnd.randrange(256) for _ in range(n_cases(40))]
    for start in starts:
        model = L.RecallCountdown(start)
        emu.mem.w8(G_RECALL_COUNTDOWN, start)
        cut_bias = rnd.random()
        for tick in range(70):
            rig.reset()
            emu.follow = set()                   # every callee stubbed (return 0)
            seen = set()
            for addr in (A_RECALL_AURA, A_RECALL_CLEAR, A_RECALL_PAST_CUT):
                emu.hook(addr, lambda e, a=addr: seen.add(a))

            def past_alive(e):
                seen.add(A_RECALL_PAST_ALIVE)
                e.jump(A_RECALL_EPILOGUE)        # recall_finish itself is not under test
            emu.hook(A_RECALL_PAST_ALIVE, past_alive)
            cutscene = 1 if rnd.random() < cut_bias else 0
            alive = rnd.choice((0, 1, 1, 2, 4))
            emu.mem.w8(G_CUTSCENE_ACTIVE, cutscene)
            emu.mem.w32(G_ALIVE_COUNT, alive)
            emu.mem.w32(G_NUM_PLAYERS, rnd.randint(1, 4))
            for slot in range(4):                # no player objects: the aura loop calls nothing
                emu.mem.w32(0x4D8AF0 + 0x43D8 + slot * 0x4C30, 0)
            emu.call(A_RECALL_TICK)
            if A_RECALL_PAST_ALIVE in seen:
                got_event = L.RECALL_FINISH
            elif A_RECALL_PAST_CUT in seen:
                got_event = L.RECALL_DROPPED_NOBODY
            elif A_RECALL_CLEAR in seen:
                got_event = L.RECALL_DROPPED_CUTSCENE
            elif A_RECALL_AURA in seen:
                got_event = L.RECALL_AURA
            else:
                got_event = None
            got = (got_event, emu.mem.u8(G_RECALL_COUNTDOWN))
            want_event = model.tick(cutscene, alive)
            want = (want_event, model.value)
            total += 1
            if got != want:
                fails.append('start %d tick %d cut %d alive %d: game %r, model %r'
                             % (start, tick, cutscene, alive, got, want))
                break
    report('recall_tick', total, fails, 'countdown byte and outcome, one call per tick')


# ---- moving pieces -------------------------------------------------------------------------

def random_offset(rnd):
    out = []
    for _ in range(3):
        k = rnd.random()
        if k < 0.3:
            v = 0.0
        elif k < 0.5:
            v = float(rnd.randint(-300, 300))
        elif k < 0.7:
            v = rnd.randint(-4000, 4000) * 0.25
        else:
            v = rnd.uniform(-1200.0, 1200.0)
        out.append(W.f32(v))
    if rnd.random() < 0.1:
        out = [W.f32(0.0), W.f32(0.0), W.f32(-256.0)]       # AutoDoor open
    return out


def random_angle(rnd):
    if rnd.random() < 0.3:
        return rnd.choice((0, 0x4000, -0x4000, -0x8000, 1, -1, 0x637C))
    return rnd.randint(-0x8000, 0x7FFF)


def random_rest(rnd):
    if rnd.random() < 0.2:
        return rnd.randint(-0x8000, 0x7FFF), rnd.randint(-0x8000, 0x7FFF)
    if rnd.random() < 0.3:
        return rnd.choice(((32767, 0), (0, 32767), (-32767, 0), (0, -32767)))
    a = rnd.uniform(-3.14159, 3.14159)
    import math
    return int(round(math.cos(a) * 32767)), int(round(math.sin(a) * 32767))


def prop_move_piece(rig, rnd, config_index=0):
    emu = rig.emu
    total, fails = 0, []
    count = n_cases(400) if config_index == 0 else max(1, n_cases(400) // 10)
    for _ in range(count):
        rig.reset()
        n_chunks = 8
        chunks = rig.alloc(0x3C * n_chunks)
        flags = [rnd.getrandbits(32) & ~0x40 | (0x40 if rnd.random() < 0.4 else 0)
                 for _ in range(n_chunks)]
        for i, f in enumerate(flags):
            emu.mem.w32(chunks + 0x3C * i + 0x24, f)
            for off in (0x28, 0x2C, 0x30):
                emu.mem.w32(chunks + 0x3C * i + off, 0x5A5A5A5A)
            emu.mem.w16(chunks + 0x3C * i + 0x36, 0x5A5A)
            emu.mem.w16(chunks + 0x3C * i + 0x38, 0x5A5A)
        n_pieces = rnd.randint(1, 3)
        pieces = rig.alloc(0x1C * n_pieces)
        models = []
        for p in range(n_pieces):
            first = rnd.randint(0, 5)
            k = rnd.choice((1, 1, 1, 2, 3)) if rnd.random() > 0.05 else rnd.choice((0, -1))
            k = min(k, n_chunks - first)
            tx, ty, tz = (rnd.randint(-0x100000, 0x100000) for _ in range(3))
            c, s = random_rest(rnd)
            base = pieces + 0x1C * p
            emu.mem.w32(base + 0x00, first)
            emu.mem.w16(base + 0x04, k & 0xFFFF)
            for off, v in ((0x08, tx), (0x0C, ty), (0x10, tz)):
                emu.mem.w32(base + off, v & M32)
            emu.mem.w16(base + 0x14, c & 0xFFFF)
            emu.mem.w16(base + 0x16, s & 0xFFFF)
            piece = L.Piece(tx, ty, tz, c, s)
            models.append((piece, first, k))
        world = rig.alloc(0x80)
        emu.mem.w32(world + 0x24, chunks)
        emu.mem.w32(world + 0x54, pieces)
        index = rnd.randrange(n_pieces) if rnd.random() > 0.05 else -1
        offset = random_offset(rnd)
        angle = random_angle(rnd)
        opos = rig.alloc(16)
        for i, v in enumerate(offset):
            emu.mem.w32(opos + 4 * i, v)
        emu.call(A_MOVE_PIECE, world, index, opos, angle)     # sign-extended, as a caller has them
        touched = set()
        for _pc, addr, size, _v in emu.writes:
            for b in range(size):
                touched.add(addr + b)
        allowed = set()
        want_fields = {}
        if index >= 0:
            piece, first, k = models[index]
            mirrored = [bool(flags[first + i] & 0x40) for i in range(max(k, 0))]
            for i, t in enumerate(L.move_piece(piece, offset, angle, mirrored)):
                base = chunks + 0x3C * (first + i)
                want_fields[first + i] = t
                for off, size in ((0x28, 4), (0x2C, 4), (0x30, 4), (0x36, 2), (0x38, 2)):
                    allowed.update(range(base + off, base + off + size))
        got_fields = {}
        for ci in want_fields:
            base = chunks + 0x3C * ci
            got_fields[ci] = (emu.mem.s32(base + 0x28), emu.mem.s32(base + 0x2C),
                              emu.mem.s32(base + 0x30), emu.mem.s16(base + 0x36),
                              emu.mem.s16(base + 0x38))
        stray = sorted(a for a in touched - allowed
                       if not (emu.stack_lo <= a < emu.stack_hi))
        total += 1
        if got_fields != want_fields or stray:
            fails.append('piece %d angle %d offset %s: game %r, model %r, stray writes %s'
                         % (index, angle, [hex(v) for v in offset], got_fields, want_fields,
                            [hex(a) for a in stray[:4]]))
    name = 'move_piece' if config_index == 0 else 'move_piece/%s%s%s' % (
        FPU_CONFIGS[config_index][0], '+bias' if FPU_CONFIGS[config_index][1] else '',
        '+divnear' if FPU_CONFIGS[config_index][2] else '')
    report(name, total, fails, 'chunk translation and rotation words, nothing else written')


def prop_move_piece_rest(rig, rnd):
    """One fixed case: an unrotated piece (cos 32767, sin 0) at quarter-unit translation
    (400, -800, 40), opened like an AutoDoor (offset (0, 0, -256), angle 0).  math_sin16(0)
    is 2**-22, not 0, so x comes out 399, not 400."""
    emu = rig.emu
    rig.reset()
    chunks = rig.alloc(0x3C)
    pieces = rig.alloc(0x1C)
    for off, v in ((0x00, 0), (0x08, 400), (0x0C, -800), (0x10, 40)):
        emu.mem.w32(pieces + off, v & M32)
    emu.mem.w16(pieces + 0x04, 1)
    emu.mem.w16(pieces + 0x14, 32767)
    world = rig.alloc(0x80)
    emu.mem.w32(world + 0x24, chunks)
    emu.mem.w32(world + 0x54, pieces)
    offset = (W.f32(0.0), W.f32(0.0), W.f32(-256.0))
    opos = rig.alloc(16)
    for i, v in enumerate(offset):
        emu.mem.w32(opos + 4 * i, v)
    emu.call(A_MOVE_PIECE, world, 0, opos, 0)
    got = (emu.mem.s32(chunks + 0x28), emu.mem.s32(chunks + 0x2C), emu.mem.s32(chunks + 0x30),
           emu.mem.s16(chunks + 0x36), emu.mem.s16(chunks + 0x38))
    want = L.move_piece(L.Piece(400, -800, 40, 32767, 0), offset, 0)[0]
    fails = [] if got == want == (399, -800, -984, 32767, 0) else ['game %r, model %r' % (got, want)]
    report('move_piece_rest', 1, fails, 'angle 0 still moves x by one quarter unit')


PROPERTIES = (('light_level', prop_light_level), ('chunk_light', prop_chunk_light),
              ('world_pick', prop_world_pick), ('world_pick_load', prop_world_pick_load),
              ('recall_tick', prop_recall_tick), ('move_piece', prop_move_piece),
              ('move_piece_rest', prop_move_piece_rest))


def main(argv):
    elf = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            i += 1
            OPTIONS['seed'] = int(argv[i])
        elif a == '-k':
            i += 1
            OPTIONS['filter'] = argv[i]
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--no-alt':
            OPTIONS['alt'] = False
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            elf = a
        i += 1
    if elf is None:
        for cand in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(cand):
                elf = cand
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_levels: no SLUS_209.73 given or found; nothing tested (exit 0)')
        return 0
    digest = sha256(elf)
    if digest != EXPECTED_SHA256:
        print('difftest_levels: %s is not the US v2.00 executable (sha256 %s)' % (elf, digest))
        return 1
    rig = Rig(elf)
    rig.set_fpu(FPU_CONFIGS[0])
    for name, fn in PROPERTIES:
        if not wanted(name):
            continue
        fn(rig, random.Random('%d:%s' % (OPTIONS['seed'], name)))
    if OPTIONS['alt'] and wanted('move_piece'):
        for ci in range(1, len(FPU_CONFIGS)):
            rig.set_fpu(FPU_CONFIGS[ci])
            prop_move_piece(rig, random.Random('%d:move_piece:%d' % (OPTIONS['seed'], ci)), ci)
        rig.set_fpu(FPU_CONFIGS[0])
    print('%d of %d properties pass' % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
