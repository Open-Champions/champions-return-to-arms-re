#!/usr/bin/env python3
"""difftest_combat_runtime.py - compare the bodies tools/ref_combat_runtime.py adds with the
game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_runtime.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                           [--cases N] [-k TEXT] [-v]

What is compared
    For each entry point below the ORIGINAL function runs in tools/ee_emu.py (an
    instruction interpreter, not a console) on records this script builds; the same
    inputs go through ref_combat_runtime.CombatModel on a copy-on-write view of that
    memory.  Equal must be: the calls to everything outside the model, in order and with
    their arguments; the set of bytes stored outside the stack and their values; the
    shared seed 0x404464 and the number of draws; the result.  Floats are compared as
    32-bit patterns under the interpreter's FPU model.

    The model refuses (Unsupported, CompositionError) what is outside the contract's
    domain; such a case is counted as refused and the original is not run for it.  The
    generator keeps most cases inside the domain.

What runs for real and what is a stub
    Real: the entry point, creature_canSeeObj (inside the hit helpers), Creature_moveBy and
    GameObject_rand (inside the knock-back), Player slot 39 0x3c3b40, the angle functions
    and the C library (soft doubles, strcmp, strstr).  Everything else is a recording stub
    answered by a seeded script; the model's call-outs are answered by the same script.
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
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
STUB_BASE = 0x00F00000
REAL_OTHER = {0x166630, 0x1666E0, 0x166798, 0x10C810, 0x113C48, 0x1509D0, 0x3C3B40}
G_PLAYERS, REC_SIZE, REC_OBJ = T.G_PLAYERS, T.REC_SIZE, T.REC_OBJ

Ext = RC.Ext
EXTS = dict(AM.EXTERNALS)
EXTS.update({
    'jumpgate_getTravelState': Ext(0x27DD68, '', 0, 'i'),
    'gfx_setColorOffset': Ext(0x19B6BC, 'iiii', 0, 'n'),
    'SpellHolyShield_typeinfo': Ext(0x3CF124, '', 0, 'i'),
    'SpellResurrect_typeinfo': Ext(0x3D162C, '', 0, 'i'),
    'SpellHarmTouch_typeinfo': Ext(0x3CDB08, '', 0, 'i'),
    'SkillStrongStance_getStat0': Ext(0x30851C, 'pi', 0, 'i'),
    'game_rebuildAlivePlayers': Ext(0x1E72F8, '', 0, 'n'),
    'net_closeLocalMenus': Ext(0x1EB000, 'i', 0, 'n'),
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i'),
    'player_voice': Ext(0x1B7BA8, 'ii', 0, 'n'),
    'dialog_isOpen': Ext(0x22FBC0, '', 0, 'i'),
    'Player_recalcDamage': Ext(0x1B7158, 'ppi', 0, 'n'),
    'Creature.v20': Ext(0, 'pp', 0, 'i'),
})

# entry points: key -> (address, integer argument kinds, number of float arguments, result kind,
#                       method, (start, end) of the body for the coverage count)
#   kinds: i integer, v vector by pointer
ENTRIES = {
    'canSeeObj': (0x10C810, 'iiiii', 3, 'i', 'can_see_obj', (0x10C810, 0x10CA6C)),
    'hitTargetInArc': (0x119938, 'iiiiiiii', 2, 'i', 'hit_target_in_arc', (0x119938, 0x119A20)),
    'hitAllEnemiesInArc': (0x119B58, 'iiiiiiii', 2, 'i', 'hit_all_enemies_in_arc', (0x119B58, 0x119D0C)),
    'findEnemyInCone': (0x10CF78, 'iii', 2, 'i', 'find_enemy_in_cone', (0x10CF78, 0x10D2A4)),
    'applyKnockback': (0x115EB8, 'i', 1, 'n', 'apply_knockback', (0x115EB8, 0x1162B0)),
    'deadUpdate': (0x1108A0, 'iivi', 1, 'n', 'dead_update', (0x1108A0, 0x110B58)),
    'playerIsEnemy': (0x1B5EA8, 'ii', 0, 'i', 'player_is_enemy', (0x1B5EA8, 0x1B5FA0)),
    'playerTakeDamage': (0x1B5330, 'iii', 1, 'n', 'player_take_damage', (0x1B5330, 0x1B5790)),
    'playerFindTarget': (0x1BB3C8, 'i', 1, 'n', 'player_find_target', (0x1BB3C8, 0x1BB718)),
    'playerProcessDamage': (0x1B2CC0, 'i', 0, 'n', 'player_process_damage', (0x1B2CC0, 0x1B3900)),
    'playerMeleeHit': (0x1B6A98, 'iiii', 1, 'n', 'player_melee_hit', (0x1B6A98, 0x1B7154)),
}
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False}


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def is_stack(v):
    return EE.STACK_LO <= v < EE.STACK_HI


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = ret, f, list(outs)


class View:
    """What the script's answers write through: the interpreter's memory or the model's."""

    def __init__(self, load, poke):
        self.load, self.poke = load, poke


class ModelView(RC.Memory):
    def __init__(self, under):
        RC.Memory.__init__(self, under)
        self.touched = set()

    def poke(self, addr, size, value):
        RC.Memory.poke(self, addr, size, value)
        self.touched.update(range(addr, addr + size))


RAYS = [f32(v) for v in (-1.0, -1.0, -1.0, 0.0, 0.25, 0.6, 1.0, 1.05, 1.5)]


class World:
    """The fake game in the interpreter's memory and the script that answers every stub."""

    def __init__(self, emu, rng):
        self.emu, self.mem = emu, emu.mem
        self.stub_addr, self.stub_name = {}, {}
        mem = self.mem
        mem.map(0, 0x1000)                                   # word 0x20 (Player_findTarget's defect)
        self.table_c = self.table(T.CREATURE_SLOTS, real=())
        self.table_p = self.table(T.PLAYER_SLOTS, real=(39,))
        self.creatures = [emu.alloc(0x400) for _ in range(6)]
        self.players = [emu.alloc(0x600) for _ in range(4)]
        self.everything = self.creatures + self.players
        self.nodes = {}
        for obj in self.everything:
            node = emu.alloc(0x20)
            mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.anim_table = emu.alloc(0x68 * 8)
        for k in range(0, 0x68 * 8, 4):
            mem.w32(self.anim_table + k, 0xA0000000 + k)
        self.argbuf = emu.alloc(0x100)
        mem.w32(RC.G_WORLD, emu.alloc(16))
        mem.w32(T.G_NUM_PLAYERS, 4)
        mem.w32(RC.G_EXCLUDE_MASK, 0)
        for slot, P in enumerate(self.players):
            mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, P)

    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def table(self, slots, real):
        table = self.emu.alloc(8 * 48)
        for slot in range(48):
            fn = slots.get(slot)
            if slot in real:
                self.mem.w32(table + 8 * slot + 4, fn)
            else:
                self.mem.w32(table + 8 * slot + 4, self.stub_for('Creature.v%d' % slot))
        return table

    # ---- scenario --------------------------------------------------------------------
    def scatter(self, rng, centre):
        mem = self.mem
        cx, cy, cz = centre
        for obj in self.everything:
            player = obj in self.players
            for off in range(0, 0x600 if player else 0x400, 4):
                mem.w32(obj + off, 0)
            spread = rng.choice((20, 40, 60, 120, 400))
            mem.wf32(obj + 0x10, cx + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x14, cy + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, 0.0, -30.0, 40.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 12.0, 16.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 3.0)))
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            mem.w32(obj + 0x44, rng.getrandbits(32))
            mem.w32(obj + 0x48, self.table_p if player else self.table_c)
            if player:
                flags = 0x60 | rng.choice((0, 0, 0, 8, 0x1000000))
            else:
                flags = rng.choice((0x20, 0x20, 0x20, 0x28, 0x21, 0x0, 0x40, 0x1000020, 0x20020))
            mem.w32(obj + 0xC, flags)
            mem.w64(obj + 0xA8, rng.choice((0, 0, 0, 0x4000000, 0x800, 0x100000, 1 << 63)))
            mem.w16(obj + 0x312, rng.choice((0, 0, 0, 30)))
            mem.w8(obj + 0x310, rng.choice((0xFF, 0, 1, 2)))
            mem.w32(obj + 0x24, self.anim_table)
            if player:
                mem.w32(obj + 0x3C8, self.players.index(obj))
        for slot in range(4):
            R = G_PLAYERS + slot * REC_SIZE
            mem.w8(R + 0x4C24, rng.choice((0, 1)))
            mem.wf32(R + 0xAC, rng.choice((100.0, 5.0, 0.5, 0.0)))
            mem.wf32(R + 0xDC, rng.choice((0.0, 0.5, 1.0, 2.0)))
            mem.w32(R + 0x54, rng.choice((0, 1, 2, 4, 7, 9, 11, 12)))
            mem.w8(R + 0x4A86, rng.choice((5, 5, 1, 2, 3)))
            mem.w8(R + 0x4C27, rng.choice((0, 0, 0, 2)))
            mem.w32(R + 0x43F0, 0)
            mem.w32(R + 0x43F4, 0)
            mem.w32(R + 0x4434, 0)
            mem.w32(R + 0x4438, 0)
            mem.w8(R + 0x4A7C, 0)

    # ---- answers ---------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        return handler(args, view, rng) if handler is not None else Res()

    def on_world_collectObjectsInBox(self, args, view, rng):
        limit = args[2]
        pool = list(self.everything)
        rng.shuffle(pool)
        found = pool[:rng.randrange(0, min(len(pool), max(limit - 1, 0)) + 1)]
        return Res(0, 0, [found])

    def on_terrain_raycast(self, args, view, rng):
        return Res(0, rng.choice(RAYS))

    def on_world_raycast(self, args, view, rng):
        return Res(0, rng.choice(RAYS), [0])

    def on_damage_apply(self, args, view, rng):
        return Res(rng.choice((0, 1, 1)))

    def on_handle_clear(self, args, view, rng):
        view.poke(args[0], 4, 0)
        return Res()

    def on_handle_link(self, args, view, rng):
        node = self.nodes.get(args[2])
        view.poke(args[0], 4, node if node is not None else 0)
        return Res()

    def on_world_slideMove(self, args, view, rng):
        pos, delta = args[0], args[1]
        for i in range(3):
            view.poke(pos + 4 * i, 4, T.C.add(view.load(pos + 4 * i, 4), delta[i]))
        return Res(rng.choice((0, 0, 1)), 0, [(0, 0, f32(1.0))])

    def on_terrain_heightBelow(self, args, view, rng):
        z = args[1][2]
        return Res(0, rng.choice((z, z, T.C.sub(z, f32(5.0)), T.C.add(z, f32(2.0)), f32(-100000.0))))

    def on_water_test(self, args, view, rng):
        return Res(0)

    def on_Creature_v20(self, args, view, rng):
        return Res(0 if args[1] == args[0] else rng.choice((0, 1, 1, 4)))

    def on_player_getSkillRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 3)))

    def on_SkillStrongStance_getStat0(self, args, view, rng):
        return Res(rng.choice((0, 0, 30, 100)))

    def on_net_isLocalSlot(self, args, view, rng):
        return Res(rng.choice((0, 1)))

    def on_dialog_isOpen(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 1)))

    def on_jumpgate_getTravelState(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 0, 1)))

    def on_SpellHolyShield_typeinfo(self, args, view, rng):
        return Res(0x3CF124)

    def on_SpellResurrect_typeinfo(self, args, view, rng):
        return Res(0x3D162C)

    def on_SpellHarmTouch_typeinfo(self, args, view, rng):
        return Res(0x3CDB08)

    def on_Player_recalcDamage(self, args, view, rng):
        R = G_PLAYERS + view.load(args[0] + 0x3C8, 4) * REC_SIZE
        view.poke(R + 0xCC, 4, rng.choice((20, 210, 1000)))
        low = rng.choice((1, 6, 11))
        view.poke(R + 0xD0, 4, low)
        view.poke(R + 0xD4, 4, low + rng.choice((0, 1, 5)))
        return Res()


class Rig:
    def __init__(self, elf, seed):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        self.world = World(emu, self.rng)
        real = set(REAL_OTHER) | {e[0] for e in ENTRIES.values()}
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
                ext = EXTS.get(name, Ext(0, 'pp', 0, 'n'))
                emu.stub(addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.unknown = [], {}
        self.trace = set()
        self.draws = 0
        # tools/ee_emu.py logs an unaligned sdl / sdr / swl / swr as a store of the whole aligned
        # word; record the real effective address of each such instruction (as
        # tools/difftest_creature.py does) so the set of bytes stored is exact.
        self.partial, self.partial_ops = [], {}
        bodies = [e[5] for e in ENTRIES.values()] + [(0x113C48, 0x1143E8), (0x1509D0, 0x150A00)]
        for start, end in bodies:
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.eview = View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def stored_bytes(self, lo, hi):
        out, partial = set(), list(self.partial)
        for pc, addr, size, _value in self.emu.writes:
            op = self.partial_ops.get(pc)
            if op is not None:
                _ppc, ea = partial.pop(0)
                first, last = {0x2C: (ea & ~7, ea), 0x2D: (ea, ea | 7), 0x2A: (ea & ~3, ea)}.get(op, (ea, ea | 3))
            else:
                first, last = addr, addr + size - 1
            if not lo <= first < hi:
                out.update(range(first, last + 1))
        return out

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind in 'ip':
                canon.append(v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'e':
                canon.append(v)
            elif kind == 'l':
                items = []
                while mem.u32(v + 4 * len(items)):
                    items.append(mem.u32(v + 4 * len(items)))
                canon.append(tuple(items))
            elif kind in 'OW':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onwb':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return canon, outs

    def make_stub(self, name, ext):
        def stub(emu):
            mem = emu.mem
            canon, outs = self.decode(ext, emu)
            args = tuple(canon)
            self.calls.append((name, args))
            res = self.world.respond(name, args, self.eview, self.script_rng)
            given = list(res.outs)
            for kind, ptr in outs:
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind == 'n' else 0))
                if kind in 'oO' and ptr:
                    for j in range(3):
                        mem.w32(ptr + 4 * j, value[j])
                elif kind in 'wW' and ptr:
                    mem.w32(ptr, value)
                elif kind == 'n':
                    for j, obj in enumerate(value):
                        mem.w32(ptr + 4 * j, obj)
                    mem.w32(ptr + 4 * len(value), 0)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return ee_emu.s32(res.ret)
        return stub

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                if name in AM.EXTERNALS:
                    return AM.shape_result(name, args, res.ret & M32, res.f & M32, res.outs)
                ext = EXTS.get(name)
                if ext is not None and ext.ret == 'n':
                    return None
                return res.ret & M32
            return answer

    def compare(self, key, args, call_seed):
        addr, kinds, nfloat, ret_kind, method, _body = ENTRIES[key]
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        mview = ModelView(mem)
        model = T.CombatModel(mview, Rig.Callbacks(self, View(mview.load, mview.poke), random.Random(call_seed)))
        ints, floats = list(args[:len(kinds)]), list(args[len(kinds):])
        try:
            mret = getattr(model, method)(*(ints + floats))
        except (T.Unsupported, T.CompositionError):
            return 'refused'
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
            return 'original stopped: %s' % exc
        self.trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names and not LIB_LO <= c.target < LIB_HI:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        problems = []
        if model.calls != self.calls:
            problems.append('calls: model %s / original %s' % (model.calls[:6], self.calls[:6]))
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
        for a in mview.bytes:                               # keep both sides in step
            mem.store(a, 1, mview.bytes[a])
        self.draws += model.draws
        return problems


def generate(rig, key, rng):
    """Arguments for one call (and the state they need), inside the domain."""
    w, mem = rig.world, rig.emu.mem
    c = rng.choice(w.creatures)
    P = rng.choice(w.players)
    centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50))
    w.scatter(rng, centre)
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20))
    mem.w32(T.G_RAND_SEED, rng.getrandbits(32))
    mem.w8(T.G_NETWORK_MODE, rng.choice((0, 0, 0, 1)))
    mem.w8(T.G_CUTSCENE_ACTIVE, 0)
    mem.w32(T.G_PVP_MODE_A, 0)
    mem.w32(T.G_PVP_MODE_B, 0)
    mem.w32(T.G_DECAL_DETAIL, 0)
    mem.w32(T.G_DEBUG_INVULNERABLE, rng.choice((0, 0, 0, 1)))
    mem.w8(T.G_RECALL_COUNTDOWN, rng.choice((0, 0, 0, 0, 1)))
    mem.w32(T.G_MENU_LOCKOUT, rng.choice((0, 0, 0, 0, 1)))
    mem.w16(T.G_EXIT_COUNTDOWN, rng.choice((0, 0, 0, 0, 2)))
    mem.w8(0x41B69D, rng.choice((0, 1)))
    mem.w32(0x20, rng.choice((0, 1)))
    mem.write(T.G_LEVEL_NAME, rng.choice((b'town\0', b'actintro\0', b'stomedal\0', b'\0')))
    fa, near = rng.randrange(0x10000), rng.choice((0.0, 0.0, 10.0, 40.0))
    far = rng.choice((30.0, 48.0, 100.0, 300.0))
    arc = rng.choice((0x1770, 0x2000, 0x4000, 0x7FFF, 0x100))
    if key == 'canSeeObj':
        mem.wf32(w.creatures[1] + 0x308, rng.uniform(-200, 200))
        mem.wf32(w.creatures[1] + 0x30C, rng.uniform(-200, 200))
        return (c, rng.choice(w.everything + [0]), fa, arc, rng.choice((0, 1, 2)), f32(near), f32(far),
                f32(rng.choice((0.0, 0.0, 0.5))))
    if key in ('hitTargetInArc', 'hitAllEnemiesInArc'):
        target = rng.choice(w.everything)
        mem.w32(c + 0x234, rng.choice((0, w.nodes[target], w.nodes[target])))
        lo = rng.choice((1, 4, 18))
        return (c, fa, arc, lo, lo + rng.choice((0, 4, 18)), rng.choice((100, 504, 100000)), rng.choice((8, 1, 0x40001)),
                0, f32(near), f32(far))
    if key == 'findEnemyInCone':
        mem.w32(c + 0x234, rng.choice((0, w.nodes[rng.choice(w.everything)])))
        mem.w32(c + 0x2E4, rng.choice((0, w.nodes[rng.choice(w.everything)])))
        return (c, fa, arc, f32(near), f32(far))
    if key == 'applyKnockback':
        mem.wf32(c + 0x2E8, rng.choice((0.0, 2.0, 100.0, 312.5, -3.0)))
        mem.w16(c + 0x2E0, rng.randrange(0x10000))
        mem.w32(c + 0xBC, f32(rng.choice((0.0, 0.5))))
        mem.w16(c + 0xC4, rng.randrange(0x100))
        mem.w32(c + 0xC, rng.choice((0x20, 0x20, 0x22, 0x60)))
        mem.w64(c + 0xA8, rng.choice((0, 0, 0x100000, 1 << 61, 1 << 63)))
        mem.w8(c + 0x231, 0)
        mem.w32(RC.G_LEVEL_FLAGS, rng.choice((0, 0, 0x100)))
        return (c, f32(rng.choice((0.7, 1.0, 0.0, -1.0))))
    if key == 'deadUpdate':
        mem.w64(c + 0xA8, rng.choice((0, 0x1000000)))
        mem.w16(c + 0x11A, rng.choice((0, 0x80, 0x88)))
        mem.w8(c + 0x118, rng.choice((1, 2)))
        mem.wf32(c + 0x2F4, rng.choice((0.0, 10.0, 71.9)))
        mem.w32(c + 0xC, rng.choice((0x29, 0x2B)))
        return (c, rng.choice((0, 0x80, 1)), (0, 0, 0), rng.choice((0, 1)), f32(rng.choice((20.0, 0.0))))
    if key == 'playerIsEnemy':
        mem.w32(T.G_PVP_MODE_A, rng.choice((0, 1)))
        return (P, rng.choice(w.everything))
    if key == 'playerTakeDamage':
        mem.w32(P + 0x58C, rng.choice((1, 2, 3, 4)))
        mem.w16(P + 0x4B4, rng.choice((0, 0, 0, 5)))
        mem.w32(P + 0x2DC, rng.choice((0, 0x2000, 0x800000)))
        mem.wf32(P + 0xC8, rng.choice((0.0, 3.0)))
        attacker = rng.choice(w.everything + [0])
        if attacker:
            mem.w32(attacker + 0xC, mem.u32(attacker + 0xC) & ~0x80 & M32)
        mem.w32(P + 0x360, rng.choice((0, w.nodes[rng.choice(w.everything)])))
        return (P, attacker, rng.choice((8, 1, 0x10000008, 0x40)), f32(rng.choice((0.0, 7.0, 150.0))))
    if key == 'playerFindTarget':
        return (P, f32(rng.choice((60.0, 72.0, 300.0))))
    if key == 'playerProcessDamage':
        mem.w32(P + 0x58C, rng.choice((1, 2, 2, 3, 4, 6, 7, 8)))
        mem.w32(P + 0x2DC, rng.choice((0, 8, 1, 0x40000 | 8, 0x400000, 0x4000000, 0x20000000, 0x40001)))
        mem.wf32(P + 0xC8, rng.choice((0.0, 3.0, 50.0, 200.0)))
        mem.w16(P + 0x2E0, rng.randrange(0x10000))
        mem.w32(P + 0x44C, rng.choice((0, 0, 1, 2)))
        mem.w8(P + 0x118, rng.choice((1, 4, 5, 6)))
        mem.w8(T.G_CUTSCENE_ACTIVE, rng.choice((0, 0, 0, 1)))
        mem.w32(T.G_NETWORK_MODE, 0)
        return (P,)
    if key == 'playerMeleeHit':
        target = rng.choice(w.everything)
        mem.w32(P + 0x448, mem.u32(T.G_SIM_FRAME) - rng.choice((5, 59, 60, 90)))
        mem.w32(P + 0x44C, rng.choice((0, 0, 1)))
        return (P, target, rng.getrandbits(8), rng.choice((0, 0, 0x40000000)), f32(0.0))
    raise KeyError(key)


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
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_combat_runtime: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_runtime: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    print('%-22s %8s %8s %8s %8s  coverage' % ('entry point', 'compared', 'failed', 'refused', 'draws'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rig = Rig(elf, OPTIONS['seed'] + index)
        rng = random.Random(OPTIONS['seed'] * 31 + index)
        compared = failed = refused = 0
        shown = []
        for n in range(cases):
            args = generate(rig, key, rng)
            out = rig.compare(key, args, rng.getrandbits(32))
            if out == 'refused':
                refused += 1
                continue
            compared += 1
            if out:
                failed += 1
                if len(shown) < (5 if OPTIONS['verbose'] else 1):
                    shown.append((n, out))
        start, end = ENTRIES[key][5]
        hit = len([pc for pc in rig.trace if start <= pc < end])
        print('%-22s %8d %8d %8d %8d  %d of %d instructions' % (key, compared, failed, refused, rig.draws, hit,
                                                                 (end - start) // 4))
        for n, out in shown:
            print('    case %d: %s' % (n, out))
        if rig.unknown:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
            ok_all = False
        ok_all = ok_all and not failed
    print('%.0f s' % (time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
