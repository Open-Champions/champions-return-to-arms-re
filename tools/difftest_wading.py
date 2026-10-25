#!/usr/bin/env python3
"""difftest_wading.py - compare tools/ref_wading.py with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_wading.py [path/to/SLUS_209.73] [--quick] [--seed N] [--cases N]
                                   [-k TEXT] [-v]

Entry points (the ORIGINAL runs in tools/ee_emu.py on constructed memory; the model runs
first on a copy-on-write view of the same memory; equal must be the calls with their
arguments, the set of bytes stored outside the stack and their values, the shared seed
0x404464 and its draw count, the cosmetic seed 0x404460, and the result)

    playerMoveWater  Player_move 0x1b4020 with water_test 0x189438, water_disturb 0x189514
                     and the chunk query 0x189240 running for real on a synthetic water
                     world: chunk table, leaf, payloads and ripple grids that the ripples
                     really write.  Water surfaces are placed on and around the edges of
                     the entry box and the wading box (ref_wading.entry_box / wade_box).
    wadeNoSpeed      the original Player_move twice from one memory snapshot, once with
                     bit 61 set (wading, the player inside water) and once clear, on a
                     frame without the entry test: every call except damage_apply, and every
                     stored byte except the ripple grids and +0xa8, must be equal - i.e.
                     wading changes nothing about the walk (an executed A/B, no model).
    footstep         Player_footstep 0x1beec8 with sound_playFoley 0x1e7c40 and newlib's
                     sprintf running for real; res_find and sound_playAtPos are stubs.

Synthetic memory only; no disc, no game data in this file.  Prints aggregate counts only.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_combat_move as CM               # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_move as MV                    # noqa: E402
import ref_water_services as W                  # noqa: E402
import ref_wading as WD                         # noqa: E402

M32 = 0xFFFFFFFF
EXPECTED_SHA256 = D.EXPECTED_SHA256
f32 = D.f32
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False}

WATER_REAL = (0x189438, 0x189514, 0x189240)
WATER_BODY = (0x189240, 0x189840)
MOVE_WATER = (0x1B4400, 0x1B4794)               # (e) and (f) of Player_move
CM.ENTRIES['playerMoveWater'] = (0x1B4020, 'iiiv', 0, 'i', 'player_move', (0x1B4020, 0x1B5330),
                                 WATER_REAL,
                                 ('creature_moveSimple', 'Player_animStep', 'Player_clampToScreen'))
NCHUNK, GRID_SIZE = 6, 0xA90 + 0x800


def redact(calls):
    """Calls for printing: C strings (names read from the executable) shown by length only."""
    return [(n, tuple('<%d bytes>' % len(a) if isinstance(a, bytes) else a for a in args)) for n, args in calls]


class WaterWorld:
    """A world object, a single leaf, a chunk table, payloads and two ripple grids."""

    def __init__(self, emu):
        self.mem = emu.mem
        self.world = emu.alloc(0x40)
        self.tree = emu.alloc(0x40)
        self.chunks = emu.alloc(0x3C * NCHUNK)
        self.payloads = emu.alloc(0x10 * NCHUNK)
        self.grids = [emu.alloc(GRID_SIZE), emu.alloc(GRID_SIZE)]

    def grid_ranges(self):
        return [(g + 0xA90, g + GRID_SIZE) for g in self.grids]

    def build(self, rng, pos, inside=None):
        """Surfaces near the player's position.  inside=True forces one water chunk under
        the wading box; False forces none."""
        mem = self.mem
        px, py, pz = (T.C.to_float(v) for v in pos)
        mem.w32(self.world + 4, self.tree)
        mem.w32(self.world + 0x24, self.chunks)
        n = rng.randrange(1, NCHUNK + 1)
        for i in range(n):
            ch, pay = self.chunks + 0x3C * i, self.payloads + 0x10 * i
            mem.w32(ch, pay)
            mem.w32(ch + 0x24, 0x80 if (inside or rng.random() < 0.9) else rng.choice((0, 0x40)))
            width = rng.choice((24.0, 120.0, 384.0, 384.0, 768.0, 30.0))
            kind = rng.random()
            if inside or kind < 0.6:
                x0 = px - rng.uniform(0.0, width)
                y0 = py - rng.uniform(0.0, width)
            else:                       # around the XY edges of both boxes (r 12, 13)
                edge = rng.choice((-14.0, -13.0, -12.5, -12.0, -11.0, 11.0, 12.0, 12.5, 13.0, 14.0))
                x0 = px + edge if edge > 0 else px + edge - width
                y0 = py - rng.uniform(0.0, width)
                if rng.random() < 0.5:
                    x0, y0 = px - rng.uniform(0.0, width), (py + edge if edge > 0 else py + edge - width)
            if inside:
                dz = rng.choice((-13.0, -12.0, 0.0, 10.0, 30.0, 48.0))
            else:
                dz = rng.choice((-14.0, -13.5, -13.0, -12.5, -12.0, -1.5, -1.0, -0.5, 0.0, 5.0,
                                 47.5, 48.0, 48.5, 59.5, 60.0, 60.5, 61.0,
                                 rng.uniform(-80, 80), rng.uniform(-20, 70)))
            zs = pz + dz
            top = zs if rng.random() < 0.8 else zs + rng.choice((0.0, 5.0, 30.0))
            for k, v in enumerate((x0, y0, zs)):
                mem.wf32(ch + 8 + 4 * k, v)
            for k, v in enumerate((x0 + width, y0 + width, top)):
                mem.wf32(ch + 0x14 + 4 * k, v)
            mem.w32(ch + 0x28, int((x0 + width / 2) * 4) & M32)
            mem.w32(ch + 0x2C, int((y0 + width / 2) * 4) & M32)
            mem.w32(pay + 8, rng.choice(self.grids + [self.grids[0], 0]) if not inside else self.grids[0])
        count = 0 if inside is False else rng.choice((0,) + (1,) * 3 + (2, 3, 4, 7))
        if inside:
            count = max(count, 1)
        if not inside and count and rng.random() < 0.25:
            # a split root (0x189288-0x189354): left leaf at +20, right leaf at +40
            axis = rng.randrange(3)
            centre = int((px, py, pz)[axis] / 4)
            for off, value in ((2, centre + rng.randrange(-12, 13)), (6, centre + rng.randrange(-12, 13))):
                value &= M32
                mem.w16(self.tree + off, value & 0xFFFF)
                mem.w16(self.tree + off + 2, value >> 16)
            mem.w16(self.tree, 0xC000 | axis)
            mem.w16(self.tree + 18, 11)
            leaves = (self.tree + 20, self.tree + 40)
        else:
            leaves = (self.tree,)
        for leaf in leaves:
            k = count if len(leaves) == 1 else rng.randrange(0, 8)
            mem.w16(leaf, k)
            for j in range(k):
                mem.w16(leaf + 2 + 2 * j, 0 if inside and j == 0 else rng.randrange(n))
        for g in self.grids:
            big = rng.random() < 0.2
            for c in range(1024):
                v = rng.choice((32700, 32767, -32768, 31000)) if big and rng.random() < 0.3 \
                    else rng.randrange(-3000, 3001)
                mem.w16(g + 0xA90 + 2 * c, v & 0xFFFF)
        mem.w8(W.G_CUT_SKIP, 0 if inside else (1 if rng.random() < 0.08 else 0))
        mem.w32(T.G_WORLD, self.world)


class WadeRig(CM.Rig):
    def __init__(self, elf, seed, key):
        CM.Rig.__init__(self, elf, seed, 'playerMoveWater')
        self.water = WaterWorld(self.emu)

    def compare(self, key, args, call_seed, round1=False):
        """CM.Rig.compare with ref_wading.WadeModel as the model."""
        addr, kinds, _nf, _rk, method, _body, _real, external = CM.ENTRIES['playerMoveWater']
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        mview = D.ModelView(mem)
        cbs = CM.Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed))
        model = WD.WadeModel(mview, cbs, external, inline_grid=True)
        ints = list(args[:len(kinds)])
        try:
            mret = getattr(model, method)(*ints)
        except (T.Unsupported, T.CompositionError, W.WaterFault) as exc:
            return 'refused: %s' % exc
        self.calls, self.touched = [], set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        regs, scratch = [], world.argbuf
        for a, k in zip(ints, kinds):
            if k == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, a[j])
                regs.append(scratch)
                scratch += 0x10
            else:
                regs.append(a & M32)
        try:
            eret = emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names and not CM.LIB_LO <= c.target < CM.LIB_HI:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        problems = []
        if model.calls != self.calls:
            first = next((i for i, (a, b) in enumerate(zip(model.calls, self.calls)) if a != b),
                         min(len(model.calls), len(self.calls)))
            problems.append('calls differ at %d: model %s / original %s' % (
                first, redact(model.calls[first:first + 3]), redact(self.calls[first:first + 3])))
        stored = self.stored_bytes(world.argbuf, world.argbuf + 0x100)
        mstored = set()
        for a, size, _v in model.writes:
            mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            problems.append('writes: only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:6], sorted('%x' % a for a in mstored - stored)[:6],
                ['%x' % a for a in diff[:6]]))
        s = seed_before
        for _ in range(model.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(T.G_RAND_SEED) == mview.load(T.G_RAND_SEED, 4) == s:
            problems.append('seed: model draws %d' % model.draws)
        if (eret & M32) != ((mret or 0) & M32):
            problems.append('result: original %08x model %08x' % (eret & M32, (mret or 0) & M32))
        grid_lo, grid_hi = self.water.grids[0] + 0xA90, self.water.grids[1] + GRID_SIZE
        self.grid_bytes = len([a for a in stored if grid_lo <= a < grid_hi])
        for a in mview.bytes:
            mem.store(a, 1, mview.bytes[a])
        self.draws += model.draws
        return problems


def generate_wade(rig, rng, stats):
    """A Player_move case (CM.generate's state) with a water world around the player."""
    mem = rig.emu.mem
    case = CM.generate(rig, 'playerMove', rng)
    P = case[0]
    wet = rng.random() < 0.5
    bit = MV.WATER_BIT
    mem.w64(P + 0xA8, (mem.u64(P + 0xA8) | bit) if wet else (mem.u64(P + 0xA8) & ~bit & ((1 << 64) - 1)))
    frame = rng.randrange(1 << 20)
    frame = frame & ~3 if rng.random() < 0.5 else frame
    frame = frame & ~0xF if rng.random() < 0.15 else frame
    mem.w32(T.G_SIM_FRAME, frame)
    mem.w32(MV.G_LEVEL_FLAGS, rng.choice((0, 0, 0x1000, 0x100)))
    pos = tuple(mem.u32(P + 0x10 + 4 * k) for k in range(3))
    rig.water.build(rng, pos)
    stats['wet_in'] += wet
    return case


def run_wade(elf, seed, cases):
    rig = WadeRig(elf, seed, 'playerMoveWater')
    rng = random.Random(seed * 31 + 7)
    out = {'compared': 0, 'failed': 0, 'refused': 0, 'shown': [], 'kinds': {}}
    stats = {'wet_in': 0, 'entered': 0, 'left': 0, 'stayed': 0, 'grid_cases': 0, 'cut': 0}
    for n in range(cases):
        case = generate_wade(rig, rng, stats)
        P = case[0]
        before = rig.emu.mem.u64(P + 0xA8) & MV.WATER_BIT
        res = rig.compare('playerMoveWater', case, rng.getrandbits(32))
        rig.world.note_cells()
        if isinstance(res, str):
            out['refused'] += 1
            out['kinds'][res[:70]] = out['kinds'].get(res[:70], 0) + 1
            continue
        out['compared'] += 1
        after = rig.emu.mem.u64(P + 0xA8) & MV.WATER_BIT
        stats['entered'] += bool(after and not before)
        stats['left'] += bool(before and not after)
        stats['stayed'] += bool(before and after)
        stats['grid_cases'] += bool(rig.grid_bytes)
        if res:
            out['failed'] += 1
            tag = res[0][:40]
            out['kinds'][tag] = out['kinds'].get(tag, 0) + 1
            if len(out['shown']) < (5 if OPTIONS['verbose'] else 1):
                out['shown'].append((n, res))
    out['draws'] = rig.draws
    out['stats'] = stats
    out['cover_move'] = (len([pc for pc in rig.trace if MOVE_WATER[0] <= pc < MOVE_WATER[1]]),
                         (MOVE_WATER[1] - MOVE_WATER[0]) // 4)
    out['cover_water'] = (len([pc for pc in rig.trace if WATER_BODY[0] <= pc < WATER_BODY[1]]),
                          (WATER_BODY[1] - WATER_BODY[0]) // 4)
    out['unknown'] = rig.unknown
    return out

# ---- the band: where the original says "in water" -------------------------------------
def band_case(rig, rng, pz, dz, dxy, wet):
    """One Player_move case: a flat 384-wide water chunk whose surface is pz + dz and whose
    nearest X edge is dxy from the player (negative: the player is over the chunk)."""
    mem, water = rig.emu.mem, rig.water
    case = CM.generate(rig, 'playerMove', rng)
    P = case[0]
    px, py = 1000.0, -500.0
    mem.wf32(P + 0x10, px)
    mem.wf32(P + 0x14, py)
    mem.wf32(P + 0x18, pz)
    word = mem.u64(P + 0xA8)
    mem.w64(P + 0xA8, (word | MV.WATER_BIT) if wet else (word & ~MV.WATER_BIT & ((1 << 64) - 1)))
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 16) << 4)          # entry test and slow ripple both run
    mem.w32(MV.G_LEVEL_FLAGS, 0)
    mem.w8(W.G_CUT_SKIP, 0)
    mem.w32(T.G_WORLD, water.world)
    mem.w32(water.world + 4, water.tree)
    mem.w32(water.world + 0x24, water.chunks)
    mem.w16(water.tree, 1)
    mem.w16(water.tree + 2, 0)
    ch = water.chunks
    mem.w32(ch, water.payloads)
    mem.w32(ch + 0x24, 0x80)
    lo_x = px + dxy                              # the chunk's minimum X edge
    for k, v in enumerate((lo_x, py - 192.0, pz + dz)):
        mem.wf32(ch + 8 + 4 * k, v)
    for k, v in enumerate((lo_x + 384.0, py + 192.0, pz + dz)):
        mem.wf32(ch + 0x14 + 4 * k, v)
    mem.w32(ch + 0x28, int((lo_x + 192.0) * 4) & M32)
    mem.w32(ch + 0x2C, int(py * 4) & M32)
    mem.w32(water.payloads + 8, water.grids[0])
    return case


def run_band(elf, seed):
    """Sweep the surface height (step 0.25) and the X distance to the chunk edge (step 0.25)
    with the original and the model; report the inclusive ranges where the player enters
    water (bit clear before) and where a wading player stays (bit set before)."""
    rig = WadeRig(elf, seed, 'playerMoveWater')
    rng = random.Random(seed * 43 + 5)
    out = {'compared': 0, 'failed': 0, 'shown': [], 'ranges': {}}
    sweeps = (('enter dz', False, [k * 0.25 for k in range(-80, 281)], lambda v: (v, -50.0)),
              ('stay dz', True, [k * 0.25 for k in range(-80, 281)], lambda v: (v, -50.0)),
              ('enter dx', False, [k * 0.25 for k in range(0, 81)], lambda v: (10.0, v)),
              ('stay dx', True, [k * 0.25 for k in range(0, 81)], lambda v: (10.0, v)))
    for pz in (0.0, 37.5, -812.25):
        for label, wet, values, place in sweeps:
            hits = []
            for v in values:
                dz, dxy = place(v)
                case = band_case(rig, rng, pz, dz, dxy, wet)
                P = case[0]
                res = rig.compare('playerMoveWater', case, rng.getrandbits(32))
                rig.world.note_cells()
                if isinstance(res, str):
                    continue
                out['compared'] += 1
                if res:
                    out['failed'] += 1
                    if len(out['shown']) < 3:
                        out['shown'].append((label, v, res))
                if rig.emu.mem.u64(P + 0xA8) & MV.WATER_BIT:
                    hits.append(v)
            key = '%s @z=%g' % (label, pz)
            out['ranges'][key] = (min(hits), max(hits)) if hits else None
    return out


def run_sequence(elf, seed):
    """Consecutive frames of the original (each also compared with the model): one player,
    one flat chunk at surface pz + dz, a fixed stick, frames f0 .. f0 + 31 with f0 % 16 == 0.
    Counts entries, exits, shared draws and frames whose ripple wrote the grid."""
    rig = WadeRig(elf, seed, 'playerMoveWater')
    rig.world.on_dialog_isOpen = lambda args, view, rng: D.Res(0)    # the stick is never zeroed
    mem = rig.emu.mem
    rng = random.Random(seed * 47 + 9)
    out = {'compared': 0, 'failed': 0, 'shown': [], 'rows': []}
    for dz, stick, wet0 in ((10.0, 1.0, False), (10.0, 0.0, False), (55.0, 1.0, False),
                            (-5.0, 1.0, False), (-12.0, 1.0, True), (-14.0, 1.0, True),
                            (50.0, 1.0, True)):
        case = band_case(rig, rng, 0.0, dz, -50.0, wet0)
        P, mode, pad, vec = case
        mode = 0
        mem.w32(P + 0x58C, 2)
        mem.w8(P + 0x481, 0)
        mem.w8(P + 0x2FC, 0)
        mem.w16(P + 0x31A, 0)
        mem.w8(P + 0x47C, 0)
        mem.w8(P + 0x47E, 0)
        mem.w32(T.G_ALIVE_COUNT, 1)
        f0 = rng.randrange(1 << 12) << 4
        row = {'dz': dz, 'stick': stick, 'wet0': wet0, 'enter': 0, 'leave': 0, 'draws': 0, 'rippled': 0}
        for i in range(32):
            mem.w32(T.G_SIM_FRAME, f0 + i)
            mem.wf32(pad + 0x14, 0.0)
            mem.wf32(pad + 0x18, stick)
            for k, v in enumerate((1000.0, -500.0, 0.0)):
                mem.wf32(P + 0x10 + 4 * k, v)
            before = mem.u64(P + 0xA8) & MV.WATER_BIT
            draws = rig.draws
            res = rig.compare('playerMoveWater', (P, mode, pad, vec), rng.getrandbits(32))
            rig.world.note_cells()
            if isinstance(res, str):
                continue
            out['compared'] += 1
            if res:
                out['failed'] += 1
                if len(out['shown']) < 3:
                    out['shown'].append((dz, i, res))
            after = mem.u64(P + 0xA8) & MV.WATER_BIT
            row['enter'] += bool(after and not before)
            row['leave'] += bool(before and not after)
            row['draws'] += rig.draws - draws
            row['rippled'] += bool(rig.grid_bytes)
        out['rows'].append(row)
    return out


# ---- Player_run: the two state-handler ripples ------------------------------------------
def run_player_run(elf, seed, ticks):
    """tools/difftest_player.py's Player_run comparison (real player, offline and net, machine
    A), counting the water_disturb calls of ticks whose calls matched, by their arguments
    (strength, radius bit patterns) and the action state the tick started in."""
    import difftest_player as DP
    counts, original_tick = {}, DP.Rig.tick

    def tick(self, tick_seed, trace=False):
        state = self.emu.mem.u32(self.world.P + 0x58C)
        result = original_tick(self, tick_seed, trace)
        if not result['fault'] and result['calls_ok']:
            for name, args in result['emu_calls']:
                if name == 'water_disturb':
                    key = (state, args[-2], args[-1])
                    counts[key] = counts.get(key, 0) + 1
        return result
    DP.Rig.tick = tick
    DP.RESULTS[:] = []
    states, coverage = {}, [None]
    try:
        for index, net in enumerate((0, 1)):
            DP.run(elf, 'real/%s/A' % ('net' if net else 'off'), seed + index, net, 0, 0, ticks, coverage, states)
    finally:
        DP.Rig.tick = original_tick
    return {'ok': all(ok for _n, ok in DP.RESULTS), 'counts': counts,
            'ticks7': states.get(7, [0, 0]), 'ticks11': states.get(0xB, [0, 0])}


# ---- the A/B: does wading change the walk? --------------------------------------------
def run_nospeed(elf, seed, cases):
    rig = WadeRig(elf, seed, 'playerMoveWater')
    emu, mem = rig.emu, rig.emu.mem
    rng = random.Random(seed * 37 + 11)
    out = {'compared': 0, 'failed': 0, 'shown': [], 'moving': 0, 'disturbed': 0}
    grids = rig.water.grid_ranges()
    for n in range(cases):
        case = CM.generate(rig, 'playerMove', rng)
        P = case[0]
        mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20) | rng.choice((1, 2, 3)))   # no entry test
        mem.w32(MV.G_LEVEL_FLAGS, rng.choice((0, 0x1000)))
        pos = tuple(mem.u32(P + 0x10 + 4 * k) for k in range(3))
        rig.water.build(rng, pos, inside=True)
        call_seed = rng.getrandbits(32)
        snap = {k: bytes(v) for k, v in mem.pages.items()}
        results = []
        for wet in (True, False):
            for k, v in snap.items():
                mem.pages[k][:] = v
            word = mem.u64(P + 0xA8)
            mem.w64(P + 0xA8, (word | MV.WATER_BIT) if wet else (word & ~MV.WATER_BIT & ((1 << 64) - 1)))
            rig.calls = []
            rig.script_rng = random.Random(call_seed)
            emu.reset_log()
            rig.partial = []
            emu.r[29] = emu.stack_hi - 0x100
            regs, scratch = [], rig.world.argbuf
            for a, k in zip(case, 'iiiv'):
                if k == 'v':
                    for j in range(3):
                        mem.w32(scratch + 4 * j, a[j])
                    regs.append(scratch)
                else:
                    regs.append(a & M32)
            emu.call(0x1B4020, *regs, max_steps=4000000)
            calls = [c for c in rig.calls if c[0] != 'damage_apply']
            stored = {}
            for _pc, addr, size, _v in emu.writes:
                for a in range(addr, addr + size):
                    if any(lo <= a < hi for lo, hi in grids) or P + 0xA8 <= a < P + 0xB0:
                        continue
                    stored[a] = mem.load(a, 1)
            gridw = len([1 for _pc, addr, _s, _v in emu.writes if any(lo <= addr < hi for lo, hi in grids)])
            results.append((calls, stored, gridw, mem.u32(T.G_RAND_SEED)))
        for k, v in snap.items():
            mem.pages[k][:] = v
        (ca, sa, ga, seeda), (cb, sb, gb, seedb) = results
        out['compared'] += 1
        out['disturbed'] += bool(ga)
        out['moving'] += any(c[0] == 'creature_moveSimple' and any(x & 0x7FFFFFFF for x in c[1][1][:2])
                             for c in ca)
        problems = []
        if ca != cb:
            problems.append('calls differ: wading %s / dry %s' % (ca[:2], cb[:2]))
        if sa != sb:
            keys = sorted(k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k))
            problems.append('stores differ at %s' % ['%x' % k for k in keys[:6]])
        if seeda != seedb:
            problems.append('seed differs')
        if problems:
            out['failed'] += 1
            if len(out['shown']) < 3:
                out['shown'].append((n, problems))
    return out


# ---- the footstep ---------------------------------------------------------------------
class FootRig:
    REAL = {0x1BEEC8, 0x1E7C40}

    def __init__(self, elf):
        emu = self.emu = EE(elf)
        emu.follow = type('F', (), {'__contains__': lambda _s, t: t in self.REAL or CM.LIB_LO <= t < CM.LIB_HI})()
        self.calls, self.rng = [], None
        emu.stub(0x17365C, function=self.on_res_find, name='res_find')
        emu.stub(0x214428, function=self.on_play, name='sound_playAtPos')
        self.P = emu.alloc(0x600)
        self.items = [emu.alloc(0x20), emu.alloc(0x20)]
        self.buf = emu.alloc(0x100)
        emu.r[29] = emu.stack_hi - 0x100
        emu.call(0x3B7EF0, self.buf, MV.S_SPLASH_FMT, 1, max_steps=200000)     # newlib's own init

    def on_res_find(self, emu):
        name = bytearray()
        v = emu.r[5] & M32
        while emu.mem.load(v + len(name), 1):
            name.append(emu.mem.load(v + len(name), 1))
        self.calls.append(('res_find', (emu.r[4] & M32, bytes(name))))
        return self.rng.choice((0, 0x00C00000, 0x00C01230))

    def on_play(self, emu):
        v = emu.r[5] & M32
        self.calls.append(('sound_playAtPos', (emu.r[4] & M32, tuple(emu.mem.u32(v + 4 * j) for j in range(3)),
                                               emu.f[12] & M32)))
        return ee_emu.s32(self.rng.choice((0, 1, 0xFFFFFFFF)))


class FootCallbacks:
    def __init__(self, rng):
        self.rng = rng

    def get(self, name):
        if name == 'res_find':
            return lambda *a: self.rng.choice((0, 0x00C00000, 0x00C01230))
        if name == 'sound_playAtPos':
            return lambda *a: self.rng.choice((0, 1, 0xFFFFFFFF))
        return None


def run_footstep(elf, seed, cases):
    rig = FootRig(elf)
    emu, mem, P = rig.emu, rig.emu.mem, rig.P
    rng = random.Random(seed * 41 + 3)
    out = {'compared': 0, 'failed': 0, 'shown': [], 'wet': 0, 'silent': 0, 'formats': {}}
    for n in range(cases):
        slot = rng.randrange(4)
        mem.w32(P + 0x3C8, slot)
        rec = WD.G_PLAYERS + slot * WD.REC_SIZE
        for off in (WD.REC_BOOTS_A, WD.REC_BOOTS_B):
            mem.w32(rec + off, rng.choice([0, 0] + rig.items))
        for item in rig.items:
            mem.w64(item + 8, (rng.getrandbits(32) << 32) | rng.choice(
                (0, 0x80000, 0x100000, 0x200000, 0x400000, 0x300000, 0x500000, 0x780000, 0x40000,
                 0x800000, rng.getrandbits(32))))
        word = rng.getrandbits(64)
        mem.w64(P + 0xA8, word | MV.WATER_BIT if rng.random() < 0.5 else word & ~MV.WATER_BIT)
        for k in range(3):
            mem.wf32(P + 0x10 + 4 * k, rng.uniform(-4000, 4000))
        mem.w32(WD.G_COSMETIC_SEED, rng.getrandbits(32))
        mem.w32(WD.G_RAND_SEED, rng.getrandbits(32))
        call_seed = rng.getrandbits(32)
        mview = D.ModelView(mem)
        model = WD.WadeModel(mview, FootCallbacks(random.Random(call_seed)))
        mret = model.player_footstep(P)
        rig.calls, rig.rng = [], random.Random(call_seed)
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x100
        eret = emu.call(0x1BEEC8, P, max_steps=400000)
        problems = []
        if model.calls != rig.calls:
            problems.append('calls: model %s / original %s' % (redact(model.calls), redact(rig.calls)))
        ebytes = set()
        for _pc, addr, size, _v in emu.writes:
            ebytes.update(range(addr, addr + size))
        mbytes = set()
        for addr, size, _v in model.writes:
            mbytes.update(range(addr, addr + size))
        if ebytes != mbytes or any(mem.load(a, 1) != mview.load(a, 1) for a in ebytes | mbytes):
            problems.append('stores: original %s model %s' % (sorted('%x' % a for a in ebytes)[:4],
                                                             sorted('%x' % a for a in mbytes)[:4]))
        if (eret & M32) != ((mret or 0) & M32):
            problems.append('result: original %08x model %08x' % (eret & M32, (mret or 0) & M32))
        if mem.u32(WD.G_RAND_SEED) != mview.load(WD.G_RAND_SEED, 4):
            problems.append('shared seed moved')
        out['compared'] += 1
        out['wet'] += bool(mem.u64(P + 0xA8) & MV.WATER_BIT)
        out['silent'] += not rig.calls
        if rig.calls:
            name = rig.calls[0][1][1]
            out['formats'][len(name)] = out['formats'].get(len(name), 0) + 1
        for a in mview.bytes:
            mem.store(a, 1, mview.bytes[a])
        if problems:
            out['failed'] += 1
            if len(out['shown']) < 3:
                out['shown'].append((n, problems))
    out['cover'] = 0
    return out


def main(argv):
    args, elf = list(argv), None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(D.ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_wading: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != EXPECTED_SHA256:
        print('difftest_wading: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    seed, ok, started = OPTIONS['seed'], True, time.time()
    want = lambda k: not OPTIONS['filter'] or OPTIONS['filter'].lower() in k.lower()
    print('seed %d, %d cases per entry' % (seed, cases))
    if want('playerMoveWater'):
        r = run_wade(elf, seed, cases)
        st = r['stats']
        print('playerMoveWater  compared %d  failed %d  refused %d  shared draws %d' % (
            r['compared'], r['failed'], r['refused'], r['draws']))
        print('    entered water %d, stayed %d, left %d, cases with grid writes %d' % (
            st['entered'], st['stayed'], st['left'], st['grid_cases']))
        print('    Player_move 0x1b4400-0x1b4794: %d of %d instructions; water services 0x189240-0x189840:'
              ' %d of %d' % (r['cover_move'] + r['cover_water']))
        for n, res in r['shown']:
            print('    case %d: %s' % (n, res))
        for tag, count in sorted(r['kinds'].items(), key=lambda kv: -kv[1]):
            if OPTIONS['verbose'] or tag.startswith('refused'):
                print('    %6d  %s' % (count, tag))
        if r['unknown']:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in r['unknown'].items()})
        ok = ok and not r['failed'] and not r['unknown']
    if want('band'):
        r = run_band(elf, seed)
        print('band             compared %d  failed %d' % (r['compared'], r['failed']))
        for key, rng_ in r['ranges'].items():
            print('    %-22s in water for %s' % (key, 'none' if rng_ is None else '%g .. %g' % rng_))
        for item in r['shown']:
            print('    %s %g: %s' % item)
        ok = ok and not r['failed']
    if want('sequence'):
        r = run_sequence(elf, seed)
        print('sequence         compared %d  failed %d  (32 frames per row)' % (r['compared'], r['failed']))
        for row in r['rows']:
            print('    surface %+6.1f stick %.1f start %-5s entries %2d exits %2d shared draws %2d frames rippled %2d'
                  % (row['dz'], row['stick'], 'wet' if row['wet0'] else 'dry', row['enter'], row['leave'],
                     row['draws'], row['rippled']))
        for item in r['shown']:
            print('    dz %g frame %d: %s' % item)
        ok = ok and not r['failed']
    if want('playerRun'):
        r = run_player_run(elf, seed, max(cases, 300))
        print('playerRun        Player_run comparison %s; state 7 ticks %d (%d bad), state 0xb ticks %d (%d bad)' % (
            'PASS' if r['ok'] else 'FAIL', r['ticks7'][0], r['ticks7'][1], r['ticks11'][0], r['ticks11'][1]))
        for (state, strength, radius), count in sorted(r['counts'].items()):
            print('    water_disturb from state %2d: strength %08x radius %08x  x%d' % (state, strength, radius, count))
        ok = ok and r['ok']
    if want('wadeNoSpeed'):
        r = run_nospeed(elf, seed, max(cases // 3, 1))
        print('wadeNoSpeed      compared %d  failed %d  (moving %d, wading ripple written %d)' % (
            r['compared'], r['failed'], r['moving'], r['disturbed']))
        for n, res in r['shown']:
            print('    case %d: %s' % (n, res))
        ok = ok and not r['failed'] and r['disturbed'] > 0
    if want('footstep'):
        r = run_footstep(elf, seed, cases)
        print('footstep         compared %d  failed %d  (in water %d, silent %d, name lengths %s)' % (
            r['compared'], r['failed'], r['wet'], r['silent'], dict(sorted(r['formats'].items()))))
        for n, res in r['shown']:
            print('    case %d: %s' % (n, res))
        ok = ok and not r['failed']
    print('%.0f s' % (time.time() - started))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
