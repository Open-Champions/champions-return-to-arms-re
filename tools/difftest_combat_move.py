#!/usr/bin/env python3
"""difftest_combat_move.py - compare the movement bodies of tools/ref_combat_move.py with the
game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_move.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                        [--cases N] [-k TEXT] [-v] [--round1]

What is compared (as in tools/difftest_combat_runtime.py, whose world and helpers this
script reuses): the ORIGINAL function runs in tools/ee_emu.py on records this script
builds; the same inputs go through ref_combat_move.MoveModel on a copy-on-write view of
that memory.  Equal must be: the calls to everything outside the model, in order and with
their arguments; the set of bytes stored outside the stack and their values; the shared
seed 0x404464 and the number of draws; the result.  Floats are compared as 32-bit
patterns under the interpreter's FPU model.

Entry points and what runs for real
    moveWithCollision  obj_moveWithCollision 0x14d4b8 (its inline grid relinks act on real
                       list words: every object of the world has a grid node in its cell)
    moveSimple         creature_moveSimple 0x1186d8 with obj_moveWithCollision running too
    playerMove         Player_move 0x1b4020; creature_moveSimple, Player_animStep and
                       Player_clampToScreen are call-outs here (each has its own entry)
    playerAnimStep     Player_animStep 0x1b9520
    clampToScreen      Player_clampToScreen 0x1b3d90 with 0x1667d8 running too
Always real: the angle functions (cos16, sin16, atan2_16, angle_approach), GameObject_rand
and the C library (soft doubles, strcmp, sprintf).  Everything else is a recording stub
answered by a seeded script, the same script that answers the model's call-outs.

--round1 runs the round-1 bodies (ref_combat_runtime.CombatModel.move_with_collision and
.player_move) on the same cases and prints how they differ; it never fails.
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_move as MV                    # noqa: E402

M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = D.LIB_LO, 0x3C1200          # newlib, with the formatter helpers above 0x3c0000
EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
Res, View, ModelView, f32, is_stack = D.Res, D.View, D.ModelView, D.f32, D.is_stack
G_PLAYERS, REC_SIZE = T.G_PLAYERS, T.REC_SIZE

EXTS = dict(D.EXTS)
EXTS.update(MV.EXTERNALS)
del EXTS['libc_sprintf']                        # runs for real (the splash sound name)
ALWAYS_REAL = {0x166630, 0x1666E0, 0x166798, 0x166C18, 0x1509D0}

# key -> (address, integer argument kinds, number of float arguments, result kind, method,
#         body (start, end) for the coverage count, other functions that run for real,
#         call-outs the model must leave as calls)
ENTRIES = {
    'moveWithCollision': (0x14D4B8, 'ivii', 0, 'i', 'move_with_collision', (0x14D4B8, 0x14DB08), (), ()),
    'moveSimple': (0x1186D8, 'iv', 0, 'i', 'move_simple', (0x1186D8, 0x118718), (0x14D4B8,), ()),
    'playerMove': (0x1B4020, 'iiiv', 0, 'i', 'player_move', (0x1B4020, 0x1B5330), (),
                   ('creature_moveSimple', 'Player_animStep', 'Player_clampToScreen')),
    'playerMoveStill': (0x1B4020, 'iiiv', 0, 'i', 'player_move', (0x1B4020, 0x1B5330), (),
                        ('creature_moveSimple', 'Player_animStep', 'Player_clampToScreen')),
    'playerAnimStep': (0x1B9520, 'i', 1, 'i', 'player_anim_step', (0x1B9520, 0x1B9658), (), ()),
    'clampToScreen': (0x1B3D90, 'iii', 0, 'i', 'player_clamp_to_screen', (0x1B3D90, 0x1B4020), (0x1667D8,), ()),
}
ROUND1 = {'moveWithCollision', 'moveSimple', 'playerMove', 'playerMoveStill'}
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False, 'round1': False}


def grid_cell(mem, obj):
    """The cell list head obj_updateGridCell picks (ref_combat_move.MoveModel.grid_cell)."""
    ix = T.s32((T.C.to_int(mem.u32(obj + 0x10)) + 0x3C00) & M32) >> 8
    iy = T.s32((T.C.to_int(mem.u32(obj + 0x14)) + 0x3C00) & M32) >> 8
    if (ix & M32) < MV.GRID_N and 0 <= iy < MV.GRID_N:
        base = MV.GRID_B if mem.u32(obj + 0xC) & 0x800 else MV.GRID_A
        return base + (iy * MV.GRID_N + ix) * 4
    return MV.GRID_OFF


class World(D.World):
    """The round-1 fake world plus grid nodes, a pad, out buffers and the answers of the
    movement call-outs."""

    def __init__(self, emu, rng):
        D.World.__init__(self, emu, rng)
        self.backs, self.grid_nodes = {}, {}
        for obj in self.everything:
            self.backs[obj] = emu.alloc(0x20)
            self.grid_nodes[obj] = emu.alloc(0x20)
        self.cells = set()
        self.pad = emu.alloc(0x40)
        self.vbuf = emu.alloc(0x10)
        self.maskbuf = emu.alloc(0x10)

    def build_grid(self):
        """Every object's grid node at the front of its cell, in the order of the objects."""
        mem = self.mem
        for cell in self.cells:
            mem.w32(cell, 0)
        self.cells = set()
        for obj in self.everything:
            back, node = self.backs[obj], self.grid_nodes[obj]
            mem.w32(obj + 8, back)
            mem.w32(back + 8, node)
            cell = grid_cell(mem, obj)
            first = mem.u32(cell)
            mem.w32(node + 4, cell)
            mem.w32(node, first)
            mem.w32(cell, node)
            if first:
                mem.w32(first + 4, node)
            self.cells.add(cell)

    def note_cells(self):
        for obj in self.everything:
            self.cells.add(grid_cell(self.mem, obj))

    # ---- answers -------------------------------------------------------------------
    def on_water_test(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)), 0, [f32(rng.uniform(-20, 20))])

    def on_water_disturb(self, args, view, rng):
        return Res(rng.choice((0, 1, 3)))

    def on_res_find(self, args, view, rng):
        return Res(rng.choice((0, 0x00C00000)))

    def on_sound_playOnObject(self, args, view, rng):
        return Res(rng.choice((0, -1)))

    def on_net_getCamYaw(self, args, view, rng):
        return Res(rng.choice((0, 0x4000, -0x1234, rng.randrange(-0x8000, 0x8000), rng.getrandbits(17))))

    def on_net_getCamFlag(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)))

    def on_SpellDrowsy_typeinfo(self, args, view, rng):
        return Res(0x3D1234)

    def on_SpellCharge_typeinfo(self, args, view, rng):
        return Res(0x3CCE9C)

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0x00C10000)))

    def on_SpellDrowsy_getStat3Fraction(self, args, view, rng):
        return Res(0, f32(rng.choice((0.5, 0.25, 1.0))))

    def on_SpellCharge_getStat3Scaled(self, args, view, rng):
        return Res(0, f32(rng.choice((0.032, 0.5, 0.016))))

    def on_Player_animStep(self, args, view, rng):
        return Res(rng.choice((0, 1, 4, 5, 0x81, 0xFF, 0x104)))

    def on_Player_clampToScreen(self, args, view, rng):
        v = args[1]
        if rng.random() < 0.5:
            v = tuple(f32(rng.uniform(-200, 200)) if rng.random() < 0.5 else x for x in v)
        return Res(rng.choice((0, 1)), 0, [v, rng.randrange(16)])

    def on_creature_moveSimple(self, args, view, rng):
        P = args[0]
        if rng.random() < 0.6:
            for i in range(2):
                old = view.load(P + 0x10 + 4 * i, 4)
                view.poke(P + 0x10 + 4 * i, 4, T.C.add(old, f32(rng.choice((0.0, 1.5, -2.0, 0.25)))))
        return Res(rng.randrange(8))

    def on_game_buildScreenEdgePlanes(self, args, view, rng):
        for i in range(4):
            for j in range(3):
                view.poke(MV.G_SCREEN_NORMALS + 12 * i + 4 * j, 4, f32(rng.uniform(-1, 1)))
                view.poke(MV.G_SCREEN_POINTS + 12 * i + 4 * j, 4, f32(rng.uniform(-3000, 3000)))
        return Res()

    def on_anim_advance(self, args, view, rng):
        root = args[2]
        if rng.random() < 0.8:
            view.poke(root, 4, f32(rng.uniform(-3, 3)))
            view.poke(root + 4, 4, f32(rng.uniform(-3, 3)))
        return Res(rng.choice((0, 1, 4, 0x10, 0x8001)))


class Rig(D.Rig):
    def __init__(self, elf, seed, key):
        self.key = key
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        self.world = World(emu, self.rng)
        entry = ENTRIES[key]
        real = set(ALWAYS_REAL) | {entry[0]} | set(entry[6])
        self.real = real
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in real or LIB_LO <= t < LIB_HI})()
        self.names = {}
        for name, ext in EXTS.items():
            addr = self.world.stub_for(name) if ext.addr == 0 else ext.addr
            if addr in real:
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        for addr, name in self.world.stub_name.items():
            if addr not in self.names:
                self.names[addr] = name
                ext = EXTS.get(name, D.Ext(0, 'pp', 0, 'n'))
                emu.stub(addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.unknown = [], {}
        self.trace = set()
        self.draws = 0
        self.partial, self.partial_ops = [], {}
        bodies = [entry[5]] + [(a, a + 0x700) for a in entry[6]]
        for start, end in bodies:
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.eview = View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None
        # newlib initialises its own state (0x50c530...) on the first formatted print; do
        # that once here so it is not counted as a store of the function under test
        emu.r[29] = emu.stack_hi - 0x100
        emu.call(0x3B7EF0, self.world.argbuf, MV.S_SPLASH_FMT, 1, max_steps=200000)

    def decode(self, ext, emu):
        """D.Rig.decode plus 's' (a C string, compared by its bytes) and 'V' (a vector the
        callee reads and writes back)."""
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind in 'ip':
                canon.append(v)
            elif kind in 'vV':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
                if kind == 'V':
                    outs.append(('o', v))
            elif kind == 'e':
                canon.append(v)
            elif kind == 's':
                out = bytearray()
                while mem.load(v + len(out), 1):
                    out.append(mem.load(v + len(out), 1))
                canon.append(bytes(out))
            elif kind in 'OW':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onwb':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return canon, outs

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                if name in EXTS:
                    return MV.shape(name, args, res.ret & M32, res.f & M32, res.outs, table=EXTS)
                return res.ret & M32
            return answer

    def compare(self, key, args, call_seed, round1=False):
        addr, kinds, nfloat, ret_kind, method, _body, _real, external = ENTRIES[key]
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        mview = ModelView(mem)
        cbs = Rig.Callbacks(self, View(mview.load, mview.poke), random.Random(call_seed))
        if round1:
            model = T.CombatModel(mview, cbs, external)
        else:
            model = MV.MoveModel(mview, cbs, external, inline_grid=True)
        ints, floats = list(args[:len(kinds)]), list(args[len(kinds):])
        try:
            mret = getattr(model, method)(*(ints + floats))
        except (T.Unsupported, T.CompositionError) as exc:
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
        for j, value in enumerate(floats):
            emu.f[12 + j] = value & M32
        try:
            eret = emu.call(addr, *regs, max_steps=2000000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names and not LIB_LO <= c.target < LIB_HI:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        problems = []
        if model.calls != self.calls:
            first = next((i for i, (a, b) in enumerate(zip(model.calls, self.calls)) if a != b),
                         min(len(model.calls), len(self.calls)))
            problems.append('calls differ at %d: model %s / original %s' % (
                first, model.calls[first:first + 3], self.calls[first:first + 3]))
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
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            problems.append('result: original %08x model %08x' % (eret & M32, (mret or 0) & M32))
        for a in mview.bytes:
            mem.store(a, 1, mview.bytes[a])
        self.draws += model.draws
        return problems


def scatter_close(rig, rng, mover):
    """Objects in a tight cluster, so that overlaps, push-outs and stand-on happen."""
    w, mem = rig.world, rig.emu.mem
    edge = rng.random() < 0.08
    cx = rng.choice((15300.0, -15300.0, 15420.0)) if edge else rng.uniform(-3000, 3000)
    cy = rng.uniform(-3000, 3000) if not edge or rng.random() < 0.5 else rng.choice((15300.0, -15420.0))
    cz = rng.uniform(-50, 50)
    spread = rng.choice((5.0, 15.0, 30.0, 60.0))
    for obj in w.everything:
        player = obj in w.players
        for off in range(0x8, 0x600 if player else 0x400, 4):
            mem.w32(obj + off, 0)
        mem.wf32(obj + 0x10, cx + rng.uniform(-spread, spread))
        mem.wf32(obj + 0x14, cy + rng.uniform(-spread, spread))
        mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, 2.0, -3.0, 4.0, 40.0, -40.0, 72.0)))
        mem.wf32(obj + 0x1C, rng.choice((8.0, 12.0, 16.0, 30.0)))
        mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 3.0, 4.5)))
        mem.wf32(obj + 0x30, rng.choice((0.0, 0.0, -50.0, 30.0, 400.0)))
        mem.w32(obj + 0x48, w.table_p if player else w.table_c)
        mem.w16(obj + 0x38, rng.randrange(0x10000))
        if obj == mover:
            flags = rng.choice((0x60, 0x20, 0x0, 0x60))
            for extra in (0x10, 0x400, 0x20000, 0x800):
                if rng.random() < 0.15:
                    flags |= extra
        else:
            flags = rng.choice((0x20, 0x60, 0x0, 0x1, 0x10, 0x200, 0x210, 0x20, 0x820))
        mem.w32(obj + 0xC, flags)
        if player:
            mem.w32(obj + 0x3C8, w.players.index(obj))
    w.build_grid()


def generate(rig, key, rng):
    w, mem = rig.world, rig.emu.mem
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20))
    mem.w32(T.G_RAND_SEED, rng.getrandbits(32))
    if key in ('moveWithCollision', 'moveSimple'):
        obj = rng.choice(w.everything)
        scatter_close(rig, rng, obj)
        kind = rng.random()
        if kind < 0.15:
            vel = (0.0, 0.0, 0.0)
        elif kind < 0.3:
            vel = (rng.uniform(-1, 1), rng.uniform(-1, 1), 0.0)
        else:
            vel = (rng.uniform(-300, 300), rng.uniform(-300, 300), rng.choice((0.0, 0.0, -100.0, 50.0)))
        vel = tuple(f32(v) for v in vel)
        if key == 'moveSimple':
            return (obj, vel)
        ignore = rng.choice([0, 0] + w.everything)
        return (obj, vel, ignore, rng.choice((0, 0, 1)))
    P = rng.choice(w.players)
    w.scatter(rng, (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), 0.0))
    slot = w.players.index(P)
    R = G_PLAYERS + slot * REC_SIZE
    frame = mem.u32(T.G_SIM_FRAME)
    if key == 'playerAnimStep':
        mem.w16(P + 0x31A, rng.choice((0, 0, 0, 20)))
        mem.w8(P + 0x2FC, rng.choice((0, 0, 1, 30, 60, 61, 200)))
        mem.w32(P + 0xC, mem.u32(P + 0xC) | rng.choice((0, 0, 0x200000)))
        mem.wf32(P + 0xBC, rng.uniform(-3, 3))
        mem.wf32(P + 0xC0, rng.uniform(-3, 3))
        return (P, f32(rng.choice((1.0, 0.0, 0.5, 1.4, 2.0, rng.uniform(0, 2)))))
    if key == 'clampToScreen':
        for i in range(3):
            mem.wf32(w.vbuf + 4 * i, rng.choice((0.0, rng.uniform(-200, 200))))
        mem.w32(w.maskbuf, rng.getrandbits(32))
        return (P, w.vbuf, w.maskbuf)
    # playerMove
    mem.w8(T.G_NETWORK_MODE, rng.choice((0, 0, 0, 1)))
    mem.w32(T.G_PVP_MODE_B, rng.choice((0, 0, 1)))
    mem.w32(MV.G_PVP_WORD_C, rng.choice((0, 0, 1)))
    mem.w32(MV.G_TURN_WORD, rng.choice((0,) * 12 + (1,)))
    mem.w32(MV.G_LEVEL_FLAGS, rng.choice((0, 0, 0x1000, 0x100)))
    mem.w32(T.G_ALIVE_COUNT, rng.choice((0, 1, 1, 2, 3)))
    mem.write(T.G_LEVEL_NAME, rng.choice((b'town\0', b'watmedal\0', b'\0', b'watmedalx\0')))
    mem.wf32(T.G_RUN_SPEED, rng.choice((1.0, 1.0, 1.5, 0.5)))
    for k in range(4):
        mem.wf32(G_PLAYERS + k * REC_SIZE + 0x4C20, rng.choice((1.0, 1.0, 1.25, 1.75)))
    mem.w8(R + 0x4A86, rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 0xFF)))
    for i in range(4):
        for j in range(3):
            mem.wf32(MV.G_SCREEN_NORMALS + 12 * i + 4 * j, rng.uniform(-1, 1))
    pad = w.pad
    stick = rng.random()
    if stick < 0.2:
        lx = ly = 0.0
    elif stick < 0.3:
        lx, ly = rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01)
    else:
        lx, ly = rng.uniform(-1.4, 1.4), rng.uniform(-1.4, 1.4)
    mem.wf32(pad + 0x14, lx)
    mem.wf32(pad + 0x18, ly)
    mem.w8(P + 0x481, rng.choice((0, 0, 0, 3, 1)))
    mem.w16(P + 0x31A, rng.choice((0, 0, 0, 20)))
    state = rng.choice((0, 1, 1, 2, 2, 2, 3, 5, 8, 8, 9, 0xB))
    mem.w32(P + 0x58C, state)
    mem.wf32(P + 0x1D4, rng.uniform(0, 30))
    if rng.random() < 0.25:
        mem.w64(P + 0xA8, mem.u64(P + 0xA8) | MV.WATER_BIT)
    else:
        mem.w64(P + 0xA8, mem.u64(P + 0xA8) & ~MV.WATER_BIT & ((1 << 64) - 1))
    for off in (0x47C, 0x47D, 0x47E):
        mem.w8(P + off, rng.choice((0, 0, 1)))
    mem.wf32(P + 0x46C, rng.choice((0.0, 1.0, rng.uniform(0, 1), 0.04)))
    mem.wf32(P + 0x468, rng.choice((0.0, rng.uniform(0, 1.2))))
    mem.wf32(P + 0x134, rng.uniform(0, 10))
    mem.w32(P + 0x44C, rng.choice((0, 0, 1, 2)))
    mem.w32(P + 0x448, (frame - rng.choice((0, 5, 9, 12, 20, 25, 30, 41, 60, 95, 100, 200))) & M32)
    mem.w8(P + 0x490, rng.randrange(8))
    mem.w8(P + 0x2FC, rng.choice((0, 0, 0, 1, 30, 60, 61)))
    mem.wf32(P + 0xBC, rng.choice((0.0, rng.uniform(-3, 3))))
    mem.wf32(P + 0xC0, rng.choice((0.0, rng.uniform(-3, 3))))
    mem.wf32(P + 0x4BC, rng.uniform(-200, 200))
    mem.wf32(P + 0x4C0, rng.uniform(-200, 200))
    mem.w8(P + 0x482, rng.choice((0, 0, 3, 15)))
    mem.w8(P + 0x118, rng.choice((1, 2, 4, 5)))
    mem.w32(P + 0xC, mem.u32(P + 0xC) | rng.choice((0, 0, 0x20000, 0x200000)))
    if rng.random() < 0.05:
        mem.w32(P + 0x3C8, M32)                                     # slot -1
    mode = rng.choice((0, 0, 0, 1, 2, 3, 4, 5, 6, 7))
    ext = tuple(f32(rng.uniform(-300, 300)) for _ in range(3))
    if key == 'playerMoveStill':
        # the domain of round 1's restricted body: a still stick, the modes Player_run uses
        # for a standing (0) or swinging (3, 4) player, out of water, alone or online
        mem.wf32(pad + 0x14, 0.0)
        mem.wf32(pad + 0x18, 0.0)
        mem.w8(P + 0x481, 0)
        mem.w16(P + 0x31A, 0)
        mem.w64(P + 0xA8, mem.u64(P + 0xA8) & ~MV.WATER_BIT & ((1 << 64) - 1))
        mem.w32(T.G_ALIVE_COUNT, rng.choice((0, 1)))
        mem.w8(P + 0x47D, 0)
        mem.w32(P + 0x58C, rng.choice((1, 2)))
        mode = 0 if mem.u32(P + 0x58C) == 2 else rng.choice((3, 4))
    return (P, mode, pad, ext)


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
        elif a == '--round1':
            OPTIONS['round1'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_combat_move: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_move: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    round1 = OPTIONS['round1']
    print('%-18s %8s %8s %8s %8s  coverage' % ('entry point', 'compared', 'failed', 'refused', 'draws'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        if round1 and key not in ROUND1:
            continue
        rig = Rig(elf, OPTIONS['seed'] + index, key)
        rng = random.Random(OPTIONS['seed'] * 31 + index)
        compared = failed = refused = 0
        shown, kinds = [], {}
        for n in range(cases):
            case = generate(rig, key, rng)
            out = rig.compare(key, case, rng.getrandbits(32), round1)
            rig.world.note_cells()
            if isinstance(out, str):
                refused += 1
                kinds[out[:70]] = kinds.get(out[:70], 0) + 1
                continue
            compared += 1
            if out:
                failed += 1
                tag = out[0][:40]
                kinds[tag] = kinds.get(tag, 0) + 1
                if len(shown) < (5 if OPTIONS['verbose'] else 1):
                    shown.append((n, out))
        start, end = ENTRIES[key][5]
        hit = len([pc for pc in rig.trace if start <= pc < end])
        print('%-18s %8d %8d %8d %8d  %d of %d instructions' % (key, compared, failed, refused, rig.draws, hit,
                                                               (end - start) // 4))
        for n, out in shown:
            print('    case %d: %s' % (n, out))
        if round1 or OPTIONS['verbose']:
            for tag, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
                print('    %6d  %s' % (count, tag))
        if rig.unknown:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
            ok_all = False
        ok_all = ok_all and not failed
    print('%.0f s' % (time.time() - started))
    return 0 if ok_all or round1 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
