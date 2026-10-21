#!/usr/bin/env python3
"""difftest_combat_ranged.py - compare the projectile bodies of tools/ref_combat_ranged.py
with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_ranged.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                          [--cases N] [-k TEXT] [-v]

What is compared (as tools/difftest_combat_runtime.py does)
    For each entry point the ORIGINAL function runs in tools/ee_emu.py (an instruction
    interpreter, not a console) on records this script builds; the same inputs go through
    ref_combat_ranged.RangedModel on a copy-on-write view of that memory.  Equal must be:
    the calls to everything outside the model, in order and with their arguments
    (strings by content, vectors by their three words, stack scratch pointers left out);
    the set of bytes stored outside the stack and their values; the shared seed 0x404464
    and the number of draws; the result.  Floats are 32-bit patterns under the
    interpreter's FPU model.  Arguments passed on the stack (the constructors) are
    written to the caller's frame before the call.

What runs for real
    The entry point; GameObject_rand; the C library (sprintf, strcmp, rtti_typeInfoEquals).
    In the run entries also obj_moveAndCollide, MissileWeapon_onTouch (the missile's slot
    6) and obj_updateActive; in the constructors and destructors the base constructor or
    destructor they call.  Everything else is a recording stub answered by a seeded
    script, and the model's call-outs are answered by the same script.
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
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_ranged as R                   # noqa: E402
import difftest_combat_runtime as D             # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32 = 0xFFFFFFFF
LIB_LO, LIB_HI = D.LIB_LO, 0x3C01A8          # the C library, with libc_mbtowc_r 0x3c0170 that sprintf calls
STUB_BASE = 0x00F00000
G_PLAYERS, REC_SIZE, REC_OBJ = T.G_PLAYERS, T.REC_SIZE, T.REC_OBJ
f32, Res, View, ModelView, is_stack = D.f32, D.Res, D.View, D.ModelView, D.is_stack

Ext = RC.Ext
EXTS = dict(D.EXTS)
EXTS.update({
    'res_find': Ext(0x17365C, 'SS', 0, 'i'),
    'light_link': Ext(0x148AF8, 'p', 0, 'n'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n'),
    'light_dtor': Ext(0x14A490, 'pi', 0, 'n'),
    'trail_create': Ext(0x190FF8, 'iiiiiii', 1, 'i'),
    'trail_addPoint': Ext(0x192550, 'iv', 0, 'n'),
    'trail_release': Ext(0x192800, 'i', 0, 'n'),
    'sound_playSample': Ext(0x2134E8, 'iv', 3, 'i'),
    'model_getSamplePoint': Ext(0x178E18, 'ppviiOWO', 1, 'n'),
    'SkillPenetratingArrows_getStats01Fraction': Ext(0x314C88, 'pwwi', 0, 'n'),
    'SkillDodge_getStat0Fraction': Ext(0x2E8AC0, 'pi', 0, 'f'),
    'Player_blockSparks': Ext(0x1B9658, 'pi', 0, 'n'),
    'item_parseDescriptor': Ext(0x1069B8, 'S-ii', 0, 'n'),
    'item_getResourceIndex': Ext(0x1083F8, '-', 0, 'i'),
    'PhProp_ctor4': Ext(0x155BDC, 'pvppiii', 1, 'n'),
    'mat3_transpose': Ext(0x166298, '--', 0, 'n'),
    'mat3_setIdentity': Ext(0x165650, '-', 0, 'n'),
    'mat3_rotateAxis': Ext(0x162960, '-ii', 0, 'n'),
    'mat3_mul': Ext(0x165710, 'p--', 0, 'n'),
    'AutoContainer_typeinfo': Ext(0x3C9558, '', 0, 'i'),
    'Container_typeinfo': Ext(0x3C3308, '', 0, 'i'),
    'Skeleton_typeinfo': Ext(0x3CC62C, '', 0, 'i'),
    'PushPhysicsProp_typeinfo': Ext(0x3C7BC8, '', 0, 'i'),
    'GameObject_dtor': Ext(0x14CF90, 'pi', 0, 'n'),
    'pool_free': Ext(0x150470, 'p', 0, 'n'),
    'Creature.v0': Ext(0, '', 0, 'i'),
    'Creature.v1': Ext(0, 'pi', 0, 'n'),
    'Creature.v17': Ext(0, 'pp', 0, 'i'),
})

OBJ_UPDATE_ACTIVE, GAMEOBJECT_RAND = 0x14DB08, 0x1509D0
ON_TOUCH, MOVE_AND_COLLIDE = 0x152A18, 0x1509F8

# entry points: key -> (address, register kinds, stack argument count, float count, result kind,
#                       method, body (start, end), functions run for real besides the entry)
ENTRIES = {
    'moveAndCollide': (0x1509F8, 'iv', 0, 0, 'i', 'move_and_collide', (0x1509F8, 0x150E48), ()),
    'projectileCtor': (0x150E48, 'ivii', 0, 0, 'n', 'projectile_ctor', (0x150E48, 0x150EE4), ()),
    'missileCtor': (0x150EE4, 'iiiivvii', 9, 0, 'n', 'missile_ctor', (0x150EE4, 0x151454), (0x150E48,)),
    'missileOnTouch': (0x152A18, 'ii', 0, 0, 'n', 'missile_on_touch', (0x152A18, 0x153314), ()),
    'missileSlot17': (0x153314, 'ii', 0, 0, 'i', 'missile_nearest_sample', (0x153314, 0x153514), ()),
    'missileRun': (0x15153C, 'i', 0, 0, 'n', 'missile_run', (0x15153C, 0x15253C),
                   (MOVE_AND_COLLIDE, ON_TOUCH, OBJ_UPDATE_ACTIVE)),
    'missileDtor': (0x151454, 'ii', 0, 0, 'n', 'missile_dtor', (0x151454, 0x15153C), ()),
    'thrownCtor': (0x1BEF58, 'iiivviii', 8, 0, 'n', 'thrown_ctor', (0x1BEF58, 0x1BF0A8), (0x150EE4, 0x150E48)),
    'thrownRun': (0x1BA940, 'i', 0, 0, 'n', 'thrown_run', (0x1BA940, 0x1BB3C8), (MOVE_AND_COLLIDE, ON_TOUCH)),
    'thrownDtor': (0x3C6468, 'ii', 0, 0, 'n', 'thrown_dtor', (0x3C6468, 0x3C64D8), (0x151454,)),
}
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False}

FAKE_DESC = 0x00E00000                  # an authored descriptor of some other class
TYPE_DESCS = [d for d, _n in R.TYPEINFO.values()] + [FAKE_DESC]
MODEL_ROWS = R.G_MODEL_TABLE


def shape(ext, args, ret=0, fret=0, outs=None):
    """What a call-out hands back to the model (ref_creature.shape_result, for EXTS)."""
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwWbnL':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0)
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvelSOW':
            position += 1
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


class World:
    """The fake game in the interpreter's memory and the script that answers every stub."""

    def __init__(self, emu, rng):
        self.emu, self.mem = emu, emu.mem
        self.stub_addr, self.stub_name = {}, {}
        mem = self.mem
        self.table_c = self.table({})
        self.table_p = self.table({})
        self.table_m_real = self.table({6: ON_TOUCH, 4: 0x15153C})
        self.table_m_stub = self.table({4: 0x15153C})
        self.creatures = [emu.alloc(0x400) for _ in range(5)]
        self.players = [emu.alloc(0x600) for _ in range(3)]
        self.props = [emu.alloc(0x400) for _ in range(2)]
        self.missiles = [emu.alloc(0x200) for _ in range(4)]
        self.everything = self.creatures + self.players + self.props + self.missiles
        self.nodes = {}
        for obj in self.everything:
            node = emu.alloc(0x20)
            mem.w32(node + 0xC, obj)
            self.nodes[obj] = node
        self.chain = emu.alloc(0x20 * 8)               # authored pierced-list nodes
        self.link_base = emu.alloc(0x20 * 256)         # nodes handle_link hands out
        self.link_next = 0
        self.anim_table = emu.alloc(0x68 * 8)
        self.argbuf = emu.alloc(0x100)
        self.items = [emu.alloc(0x60) for _ in range(3)]
        self.defs = [emu.alloc(0x40) for _ in range(3)]
        mem.w32(RC.G_WORLD, emu.alloc(16))
        mem.w32(T.G_NUM_PLAYERS, 3)
        for slot, P in enumerate(self.players):
            mem.w32(G_PLAYERS + slot * REC_SIZE + REC_OBJ, P)
        names = emu.alloc(0x200)
        at = names
        for desc, name in list(R.TYPEINFO.values()) + [(FAKE_DESC, b'9FakeClass')]:
            if not mem.is_mapped(desc, 4):
                mem.map(desc & ~0xFFF, 0x1000)
            mem.write(at, name + b'\0')
            mem.w32(desc, at)
            at += 0x20
        self.skill_table = self.table({}, 'Skill')
        for sid in (2, 0x53, 0x5D):
            skill = emu.alloc(0x80)
            mem.w32(skill + 0x60, self.skill_table)
            mem.w32(R.G_SKILL_TABLE + 4 * sid, skill)

    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def table(self, real, cls='Creature'):
        table = self.emu.alloc(8 * 48)
        for slot in range(48):
            fn = real.get(slot)
            self.mem.w32(table + 8 * slot + 4, fn if fn is not None else self.stub_for('%s.v%d' % (cls, slot)))
        return table

    # ---- scenario --------------------------------------------------------------------
    def scatter(self, rng, centre):
        mem = self.mem
        cx, cy, cz = centre
        for obj in self.everything:
            player = obj in self.players
            size = 0x600 if player else 0x400 if obj not in self.missiles else 0x200
            for off in range(0, size, 4):
                mem.w32(obj + off, 0)
            spread = rng.choice((10, 20, 40, 120))
            mem.wf32(obj + 0x10, cx + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x14, cy + rng.uniform(-spread, spread))
            mem.wf32(obj + 0x18, cz + rng.choice((0.0, 0.0, -30.0, 40.0, -80.0)))
            mem.wf32(obj + 0x1C, rng.choice((8.0, 12.0, 16.0, 30.0)))
            mem.wf32(obj + 0x20, rng.choice((40.0, 72.0, 3.0)))
            mem.w16(obj + 0x38, rng.randrange(0x10000))
            mem.w32(obj + 0x44, rng.getrandbits(32))
            if obj in self.missiles:
                mem.w32(obj + 0x48, rng.choice((self.table_m_real, self.table_m_stub)))
                mem.w32(obj + 0xC, rng.choice((0x4081 | 0x4001, 0x4081 | 0x4001, 0x4081 | 0x4001 | 0x20000000)))
                continue
            mem.w32(obj + 0x48, self.table_p if player else self.table_c)
            if player:
                flags = 0x60 | rng.choice((0, 0, 0, 8, 0x1000000))
            elif obj in self.props:
                flags = rng.choice((0, 0x200, 0x1, 0x10, 0x20000000))
            else:
                flags = rng.choice((0x20, 0x20, 0x20, 0x28, 0x21, 0x1000020, 0x20020, 0x220))
            mem.w32(obj + 0xC, flags)
            mem.w64(obj + 0xA8, rng.choice((0, 0, 0, 1 << 41, 0x100000)))
            mem.w32(obj + 0x24, rng.choice(self.defs))
            mem.wf32(obj + 0xDC, rng.choice((1.0, 1.5)))
            if player:
                mem.w32(obj + 0x3C8, self.players.index(obj))
                mem.w32(obj + 0x544, rng.choice((0, 0xB0000000)))

    def node_list(self, rng, members):
        """An authored handle chain: head word value for `members` (front first)."""
        head = 0
        for i, obj in enumerate(reversed(members)):
            node = self.chain + 0x20 * i
            self.mem.w32(node, head)
            self.mem.w32(node + 0xC, obj)
            head = node
        return head

    # ---- answers ---------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        return handler(args, view, rng) if handler is not None else Res()

    def on_world_collectObjectsInBox(self, args, view, rng):
        pool = list(self.everything)
        rng.shuffle(pool)
        return Res(0, 0, [pool[:rng.randrange(0, min(len(pool), args[2] - 1) + 1)]])

    def on_terrain_height(self, args, view, rng):
        z = args[1][2]
        return Res(0, rng.choice((T.C.sub(z, f32(50.0)), T.C.sub(z, f32(1.0)), z, T.C.add(z, f32(3.0)),
                                  T.C.add(z, f32(40.0)), f32(-1000000.0))))

    def on_water_test(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)))

    def on_res_find(self, args, view, rng):
        return Res(rng.choice((0, 0x00A00000)))

    def on_sound_playSample(self, args, view, rng):
        return Res(rng.choice((-1 & M32, 3)))

    def on_trail_create(self, args, view, rng):
        return Res(rng.choice((0, 0x82CD00, 0x82D110)))

    def on_handle_clear(self, args, view, rng):
        view.poke(args[0], 4, 0)
        return Res()

    def on_handle_link(self, args, view, rng):
        node = self.link_base + 0x20 * (self.link_next % 256)
        self.link_next += 1
        view.poke(node, 4, view.load(args[0], 4))
        view.poke(node + 0xC, 4, args[2])
        view.poke(args[0], 4, node)
        return Res()

    def on_Creature_v0(self, args, view, rng):
        return Res(rng.choice(TYPE_DESCS))

    def on_AutoContainer_typeinfo(self, args, view, rng):
        return Res(R.TYPEINFO[0x3C9558][0])

    def on_Container_typeinfo(self, args, view, rng):
        return Res(R.TYPEINFO[0x3C3308][0])

    def on_Skeleton_typeinfo(self, args, view, rng):
        return Res(R.TYPEINFO[0x3CC62C][0])

    def on_PushPhysicsProp_typeinfo(self, args, view, rng):
        return Res(R.TYPEINFO[0x3C7BC8][0])

    def on_Creature_v16(self, args, view, rng):
        return Res(rng.choice((0, 0, 0xB0000000)))

    def on_Creature_v17(self, args, view, rng):
        return Res(rng.choice((0, 1, 3)))

    def on_Creature_v20(self, args, view, rng):
        return Res(0 if args[1] == args[0] else rng.choice((0, 1, 1, 4)))

    def on_Creature_v36(self, args, view, rng):
        return Res(rng.choice((0, 0, 4, 10)))

    def on_Skill_v11(self, args, view, rng):
        return Res(rng.choice((0, 5, 30, 100)))

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((0, 1, 3, 6)))

    def on_model_getSamplePoint(self, args, view, rng):
        base = args[2]
        point = tuple(T.C.add(base[i], f32(rng.uniform(-30, 30))) for i in range(3))
        weight = f32(rng.choice((0.0, 0.5, 0.74, 0.75, 1.0)))
        return Res(0, 0, [point, weight, (0, 0, 0)])

    def on_player_getSkillRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 1, 5)))

    def on_SkillPenetratingArrows_getStats01Fraction(self, args, view, rng):
        return Res(0, 0, [f32(rng.choice((0.0, 0.0, 0.2, 1.0))), f32(rng.choice((0.0, 0.0, 0.3, 1.0)))])

    def on_SkillDodge_getStat0Fraction(self, args, view, rng):
        return Res(0, f32(rng.choice((0.0, 0.0, 0.1, 0.5, 1.0))))

    def on_item_getResourceIndex(self, args, view, rng):
        return Res(rng.choice((0, 1, 2, 3)))

    def on_pool_new(self, args, view, rng):
        return Res(rng.choice((0, 0x00C00000)))

    def on_damage_apply(self, args, view, rng):
        return Res(rng.choice((0, 1, 1)))

    def on_obj_updateActive(self, args, view, rng):
        return Res(rng.choice((0, 1)))


class Rig(D.Rig):
    """difftest_combat_runtime.Rig with this script's World, externals and entries."""

    def __init__(self, elf, seed, key):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        self.world = World(emu, self.rng)
        entry = ENTRIES[key]
        real = {entry[0], GAMEOBJECT_RAND} | set(entry[7])
        self.real = real
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in real or LIB_LO <= t < LIB_HI})()
        self.names = {}
        for name, ext in EXTS.items():
            addr = self.world.stub_for(name) if ext.addr == 0 else ext.addr
            if addr in real or LIB_LO <= addr < LIB_HI:
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
        self.partial, self.partial_ops = [], {}
        bodies = [entry[6]] + [(a, a + 0x1000) for a in entry[7]]
        for start, end in bodies:
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.eview = View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def stored_bytes(self, lo, hi):
        """As difftest_combat_runtime's, without the stores the C library makes into its
        own state (newlib's reentrancy block at 0x50c5xx, written by sprintf): not game
        state, and the model formats its text without it."""
        writes = self.emu.writes
        self.emu.writes = [w for w in writes if not (LIB_LO <= w[0] < LIB_HI and w[0] not in self.partial_ops)]
        try:
            return D.Rig.stored_bytes(self, lo, hi)
        finally:
            self.emu.writes = writes

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind in 'ipe':
                canon.append(v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'S':
                canon.append(('str', mem.cstr(v, 64).encode('latin1')))
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
                ext = EXTS.get(name, Ext(0, 'pp', 0, 'n'))
                return shape(ext, args, res.ret & M32, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed):
        addr, kinds, nstack, nfloat, ret_kind, method, _body, _real = ENTRIES[key]
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        mview = ModelView(mem)
        model = R.RangedModel(mview, Rig.Callbacks(self, View(mview.load, mview.poke), random.Random(call_seed)))
        nreg = len(kinds)
        ints = list(args[:nreg + nstack])
        floats = list(args[nreg + nstack:])
        world.link_next = 0
        try:
            mret = getattr(model, method)(*(ints + floats))
        except (T.Unsupported, T.CompositionError):
            return 'refused'
        world.link_next = 0
        self.calls, self.touched = [], set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = []
        sp = emu.stack_hi - 0x200
        emu.r[29] = sp
        for i, value in enumerate(ints[nreg:]):
            mem.w64(sp + 8 * i, value & M32)
        regs, scratch = [], world.argbuf
        for a, k in zip(ints[:nreg], kinds):
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
            eret = emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            return 'original stopped: %s' % exc
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


def _vec(rng, spread, zspread):
    return (f32(rng.uniform(-spread, spread)), f32(rng.uniform(-spread, spread)), f32(rng.uniform(-zspread, zspread)))


def setup_missile(rig, rng, m, kind=None):
    """A projectile's fields as a constructor and some flight leave them."""
    w, mem = rig.world, rig.emu.mem
    owner = rng.choice(w.creatures + w.players + [0, 0])
    mem.w32(m + 0x4C, w.nodes[owner] if owner else 0)
    mem.w32(m + 0xD0, kind if kind is not None else rng.choice((0, 0, 0, 3, 1, 5, 6)))
    mem.w8(m + 0xCC, rng.choice((0, 0, 0, 0, 1, 2, 3)))
    mem.w8(m + 0xCD, rng.choice((0, 1)))
    mem.w8(m + 0x50, rng.choice((0, 0, 1)))
    members = rng.sample(w.creatures + w.players, rng.choice((0, 0, 1, 2)))
    mem.w32(m + 0x124, w.node_list(rng, members))
    mem.w32(m + 0x128, rng.choice((0, 0, 0, 0, w.nodes[rng.choice(w.creatures)])))
    for k, v in enumerate(_vec(rng, 1500, 300)):
        mem.w32(m + 0x1B0 + 4 * k, v)
    mem.w32(m + 0xD4, rng.choice((1, 4, 12)))
    mem.w32(m + 0xD8, rng.choice((2, 8, 30)))
    mem.w32(m + 0xDC, rng.getrandbits(8))
    mem.w32(m + 0xE0, rng.getrandbits(16))
    mem.w32(m + 0xE4, rng.choice((100, 504, 100000)))
    mem.w32(m + 0xE8, rng.choice((4, 0, 1, 0x20)))
    mem.w32(m + 0xEC, mem.u32(T.G_SIM_FRAME) + rng.choice((-1, 0, 1, 300)))
    mem.w32(m + 0xF4, rng.choice((0, 2)))
    mem.w16(m + 0xFA, rng.choice((0, 0, 3000, -2000 & 0xFFFF)))
    mem.w16(m + 0xFC, rng.randrange(0x10000))
    mem.w32(m + 0x12C, rng.choice((0, rng.choice(w.items))))
    mem.w32(m + 0x170, rng.choice((0, 0x82CD00)))
    mem.w32(m + 0x1BC, rng.choice((0, 0, 0x00D00000)))
    row = rng.randrange(4)
    mem.w32(m + 0x1C0, rng.choice((0, mem.u32(R.G_MODEL_TABLE + 8 + 16 * row), 0x00B10000)))
    mem.w32(m + 0x1C4, rng.choice((0, 0x00B20000)))
    mem.w8(m + 0x1CE, rng.choice((0, 4, 4, 5, 6, 7)))
    mem.w16(m + 0x1CC, rng.choice((0, 4990, 5000, -5000 & 0xFFFF, -4990 & 0xFFFF, 0x7FF0)))
    mem.w32(m + 0x1C8, w.nodes[owner] if owner and rng.random() < 0.5 else 0)


def setup_items(rig, rng):
    w, mem = rig.world, rig.emu.mem
    for item, definition in zip(w.items, w.defs):
        mem.w32(item, rng.choice((definition, definition, 0)))
        mem.w8(definition + 0x1E, rng.choice((0, 4, 6)))
        for k in range(4):
            mem.w16(item + 0x24 + 8 * k, rng.choice((0x18, 0x16, 0x15, 0x17, 0x26, 5, -1 & 0xFFFF)))
            mem.w16(item + 0x26 + 8 * k, rng.choice((0, 0, 3)))


def generate(rig, key, rng):
    """Arguments for one call (and the state they need)."""
    w, mem = rig.world, rig.emu.mem
    centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50))
    w.scatter(rng, centre)
    setup_items(rig, rng)
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20))
    mem.w32(T.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(T.G_PVP_MODE_A, rng.choice((0, 0, 1)))
    mem.w32(R.G_LEVEL_FLAGS, rng.choice((0, 0, 0x100, 0x40000, 0x40100)))
    mem.w8(T.O.G_ACTIVITY_COUNT, rng.choice((0, 1, 2)))
    for i in range(2):
        for k in range(3):
            mem.wf32(T.O.G_ACTIVITY_CENTERS + 12 * i + 4 * k, centre[k] + rng.choice((0.0, 300.0, 2000.0)))
    mem.w8(T.G_CULL_BY_CAMERA, 0)
    for m in w.missiles:
        setup_missile(rig, rng, m)
    m = rng.choice(w.missiles)
    if key == 'moveAndCollide':
        mem.w32(m + 0x48, w.table_m_stub)
        return (m, _vec(rng, 1500, 400))
    if key == 'projectileCtor':
        return (m, _vec(rng, 3000, 100), rng.choice(w.creatures + w.players + [0]), rng.choice((0, 0x00A10000)))
    if key == 'missileCtor':
        item = rng.choice((0, 0) + tuple(w.items))
        return (m, rng.choice((0, 0, 0, 1, 2, 3, 5, 6)), rng.getrandbits(32), rng.getrandbits(32),
                _vec(rng, 3000, 100), _vec(rng, 1000, 300), rng.randrange(0x10000),
                rng.choice(w.creatures + w.players + [0]),
                rng.choice((0, 0, 0x00D10000)), rng.choice((0, 0x00D20000)), rng.choice((1, 4)), rng.choice((2, 9)),
                rng.getrandbits(8), rng.getrandbits(32), rng.choice((100, 100000)), rng.choice((4, 0, 0x21)), item)
    if key == 'missileOnTouch':
        return (m, rng.choice(w.everything + [0]))
    if key == 'missileSlot17':
        return (m, rng.choice(w.creatures + w.players + [0]))
    if key == 'missileRun':
        mem.w32(m + 0x48, rng.choice((w.table_m_real, w.table_m_real, w.table_m_stub)))
        setup_missile(rig, rng, m, rng.choice((0, 0, 3)))
        if rng.random() < 0.6:
            mem.w8(m + 0xCC, 0)
            mem.w32(m + 0x128, 0)
        return (m,)
    if key == 'missileDtor':
        return (m, rng.choice((0, 1, 3)))
    if key == 'thrownCtor':
        return (m, rng.getrandbits(32), rng.getrandbits(32), _vec(rng, 3000, 100), _vec(rng, 800, 300),
                rng.randrange(0x10000), rng.choice(w.creatures + w.players + [0]), rng.choice((0, 0x00D10000)),
                rng.choice((0, 0x00D20000)), rng.choice((1, 4)), rng.choice((2, 9)), rng.getrandbits(8),
                rng.getrandbits(32), rng.choice((100, 100000)), rng.choice((0, 4, 5, 6, 7, 0xFF)),
                rng.choice((0,) + tuple(w.items)))
    if key == 'thrownRun':
        mem.w32(m + 0x48, rng.choice((w.table_m_real, w.table_m_real, w.table_m_stub)))
        setup_missile(rig, rng, m, 0)
        if rng.random() < 0.6:
            mem.w8(m + 0xCC, 0)
        return (m,)
    if key == 'thrownDtor':
        return (m, rng.choice((0, 1, 3)))
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
            elf = os.path.join(ROOT, 'local', 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_combat_ranged: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_ranged: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    total = [0, 0, 0]
    print('%-16s %8s %8s %8s %8s  coverage' % ('entry point', 'compared', 'failed', 'refused', 'draws'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rig = Rig(elf, OPTIONS['seed'] + index, key)
        rng = random.Random(OPTIONS['seed'] * 31 + index)
        compared = failed = refused = 0
        shown = []
        for n in range(cases):
            call_args = generate(rig, key, rng)
            out = rig.compare(key, call_args, rng.getrandbits(32))
            if out == 'refused':
                refused += 1
                continue
            compared += 1
            if out:
                failed += 1
                if len(shown) < (5 if OPTIONS['verbose'] else 1):
                    shown.append((n, out))
        start, end = ENTRIES[key][6]
        hit = len([pc for pc in rig.trace if start <= pc < end])
        print('%-16s %8d %8d %8d %8d  %d of %d instructions' % (key, compared, failed, refused, rig.draws, hit,
                                                               (end - start) // 4))
        total[0] += compared
        total[1] += failed
        total[2] += refused
        for n, out in shown:
            print('    case %d: %s' % (n, out))
        if OPTIONS['verbose']:
            missed = [pc for pc in range(start, end, 4) if pc not in rig.trace]
            spans, first = [], None
            for i, pc in enumerate(missed):
                if first is None:
                    first = pc
                if i + 1 == len(missed) or missed[i + 1] != pc + 4:
                    spans.append('%x-%x' % (first, pc + 4))
                    first = None
            print('    not executed: %s' % ', '.join(spans) if spans else '    every instruction executed')
        if rig.unknown:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
            ok_all = False
        ok_all = ok_all and not failed
    print('total: %d compared, %d failed, %d refused; %.0f s' % (total[0], total[1], total[2], time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
