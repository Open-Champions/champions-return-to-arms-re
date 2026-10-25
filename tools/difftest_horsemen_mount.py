#!/usr/bin/env python3
"""difftest_horsemen_mount.py - compare tools/ref_horsemen_mount.py with the game's own code
for the mounted Horsemen: the Nightmare mount class, the rider-mount link and its whole
lifecycle (build, riding, the mount's death and the dismount, the rider's death on foot).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_horsemen_mount.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                           [--ticks N] [-k TEXT] [-v] [--fpu MODEL]
                                           [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 20973); a seed repeats exactly
    --ticks N     ticks per run (default 1500; six runs)

What is compared
    Exactly as tools/difftest_arena_monsters.py (calls, writes, shared seed, results), on
    top of its world and rig.  Run for real under tools/ee_emu.py: everything of
    ref_horsemen_mount.MODELLED (the eight Nightmare functions, Horsemen_draw and
    Creature_angleToTarget), everything of ref_arena_monsters.MODELLED (Horsemen_ctor,
    Horsemen_run, Horsemen_setState and the rest) and of ref_creature.MODELLED.  In
    particular Horsemen_ctor's call of Nightmare_ctor is NOT a stub here: the mount is
    built by the original constructor on the block pool_new hands out, and the mount's
    set-state reaches the rider's set-state through the rider's own virtual table.

Scenarios (the run names)
    factory     four mounted Rider rows, four on-foot UndeadKnight rows and the
                standalone Nightmare row, each through its real constructor.
    damage      directed lethal rider hit while linked, lethal mount hit, then
                the on-foot rider's death after one more hit.
    nightmare   a Nightmare the factory builds on its own (no rider): the object under test
                is the mount.  Its property list is the driver's or one of the four the
                mounted Horsemen hand over.
    mounted     Horsemen_ctor(..., variant, mounted = 1): the object under test is the rider
                and the mount is the pool block.  Every tick runs Nightmare_run(mount) and
                Horsemen_run(rider) in that order; damage and killing blows go to either;
                the driver requests every state number of both.  The mount's death sends
                the rider to 0x23 and drops both links; the knight then fights on foot
                until it dies too and both are built again.
    Each on machine A and machine B, offline and in a net game.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_horsemen_mount as HM                 # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_arena_monsters as DA            # noqa: E402
from difftest_creature import Res, f32, fl, M32, is_stack      # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 1500})

DA.REAL.update(HM.MODELLED.values())            # the arena rig's "real" set, extended

BODIES = {
    'Nightmare_ctor': (0x270968, 0x270B4C), 'Nightmare_draw': (0x270B4C, 0x270BBC),
    'Nightmare_run': (0x270BBC, 0x27142C), 'Nightmare_onHitTerrain': (0x27142C, 0x271484),
    'Nightmare_onTouchList': (0x271484, 0x27155C), 'Nightmare_setState': (0x27155C, 0x2719D4),
    'Horsemen_mountSeatTransform': (0x2719D4, 0x271A6C), 'Nightmare_pickChargeTarget': (0x271A6C, 0x271C70),
    'Horsemen_ctor': (0x271C70, 0x2721F8), 'Horsemen_draw': (0x2721F8, 0x27236C),
    'Horsemen_run': (0x27236C, 0x272F4C), 'Horsemen_setState': (0x272F4C, 0x2735DC),
    'Creature_angleToTarget': (0x118840, 0x11889C),
}
DA.BODIES.update({k: v for k, v in BODIES.items() if k not in DA.BODIES})     # partial-store hooks

ENTRIES = dict(DA.ENTRIES)
ENTRIES.update({
    'Nightmare_ctor': (0x270968, 'civii', 'n', 'nightmare_ctor'),
    'Nightmare_run': (0x270BBC, 'c', 'n', 'nightmare_run'),
    'Nightmare_draw': (0x270B4C, 'c', 'n', 'nightmare_draw'),
    'Nightmare_onHitTerrain': (0x27142C, 'cv', 'n', 'nightmare_on_hit_terrain'),
    'Nightmare_onTouchList': (0x271484, 'cl', 'n', 'nightmare_on_touch_list'),
    'Nightmare_setState': (0x27155C, 'ci', 'n', 'nightmare_set_state'),
    'Horsemen_mountSeatTransform': (0x2719D4, 'ci', 'n', 'nightmare_seat_transform'),
    'Nightmare_pickChargeTarget': (0x271A6C, 'c', 'i', 'nightmare_pick_charge_target'),
    'Horsemen_draw': (0x2721F8, 'c', 'n', 'horsemen_draw'),
    'Creature_angleToTarget': (0x118840, 'c', 'i', 'angle_to_target'),
})

NIGHTMARE_STATES = list(range(0, 0x1B)) + [0x1B, 0x23, 0x40, 0xFFFFFFFF, 0, 3, 5, 6, 7, 7, 8, 8, 0x10, 0x12, 0x13,
                                           0x14, 0x17, 0x18, 0x19, 0x1A, 0x1A]


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
class World(DA.World):
    """The arena world, plus the Nightmare's class definition and table, a slot-18 holder
    stub, and answers for the draw and knock-down call-outs."""

    def build(self, rng):
        mem, emu = self.emu.mem, self.emu
        DA.World.build(self, rng)
        self.ready = False
        mem.w32(HM.DEF_NIGHTMARE + 0xC, self.model)
        mem.w32(HM.DEF_NIGHTMARE + 0x14, 0x00C00080)
        for k in range(3, 0x1C):
            rec = emu.alloc(0x40)
            mem.w32(HM.DEF_NIGHTMARE + 8 * k + 4, rec)
            self.anim_entries[rec] = (HM.DEF_NIGHTMARE, k)
        for slot in range(1, 40):
            fn = mem.u32(HM.VT_NIGHTMARE + 8 * slot + 4)
            if fn not in DA.REAL:
                self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        for table in DA.HOLDER_TABLES:
            fn = mem.u32(table + 8 * 18 + 4)
            assert self.addr_name.setdefault(fn, 'Holder.v18') == 'Holder.v18'
        self.matrix = emu.alloc(0x40)
        self.touch_list = emu.alloc(0x20)
        self.ready = True

    factory_pool = None                         # size -> block: the factory check's allocator

    def on_pool_new(self, args, view, rng):
        if self.factory_pool is None:
            return DA.World.on_pool_new(self, args, view, rng)
        block = self.factory_pool.get(args[0], 0)
        for off in range(0, (args[0] + 3) & ~3, 4):
            if block:
                view.poke(block + off, 4, 0)
        return Res(block)

    def on_creature_inKnockdownAnim(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 1)))

    def on_Creature_draw(self, args, view, rng):
        return Res(rng.choice((0, 0x00C00300)))

    def on_model_drawShadow(self, args, view, rng):
        return Res(rng.choice((0, 0x00C00340)))

    def on_model_draw(self, args, view, rng):
        return Res(rng.choice((0, 0x00C00380)))

    def on_anim_advance(self, args, view, rng):
        """The arena world's answer, with the mount's kick events (bit 2, value 4) added."""
        res = DA.World.on_anim_advance(self, args, view, rng)
        if rng.random() < 0.15:
            res.ret = rng.choice((4, 5, 6, 7))
        return res

    def on_terrain_raycast(self, args, view, rng):
        return Res(f=rng.choice(DC.RAY_ANSWERS + [f32(0.0), f32(-0.0)]))


# ---------------------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------------------
class Rig(DA.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, kind, machine, net)
        emu.follow = self.real = DA.RealSet()
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DC.EmuView(emu)
        self.script_rng = None
        self.names = {}

        def add(addr, name, ext):
            assert addr not in DA.REAL, (hex(addr), name)
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in HM.EXTERNALS.items():
            if name in HM.MODELLED:
                continue
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, HM.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))
        self.partial, self.partial_ops = [], {}
        for start, end in set(list(DC.BODIES.values()) + list(DA.BODIES.values())):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    def decode(self, name, ext, emu):
        """The arena rig's decoding plus the kind 'Q' (a whole 64-bit register)."""
        if 'Q' not in ext.ints:
            return DA.Rig.decode(self, name, ext, emu)
        before = RC.Ext(ext.addr, ext.ints.replace('Q', '-'), ext.floats, ext.ret)
        before.stack = getattr(ext, 'stack', 0)
        canon, outs = DA.Rig.decode(self, name, before, emu)
        at = ext.ints.index('Q')
        position = sum(1 for k in ext.ints[:at] if k in 'ipvelsSOW')
        canon.insert(position, emu.r[4 + at] & RC.M64)
        return canon, outs

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if HM.EXTERNALS[name].ret == 'q' else M32)
                return HM.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None, emu_run=None, model_run=None):
        """tools/difftest_arena_monsters.Rig.compare with this module's model and entry
        table, and the argument kind 'l' (a zero-terminated object list in memory).  With
        emu_run / model_run the two sides are started by those instead (a stretch of code
        that is not a function entry, such as a factory row)."""
        addr, kinds, ret_kind, method = ENTRIES[key] if key in ENTRIES else (0, '', 'n', None)
        emu, world = self.emu, self.world
        mem = emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = DC.ModelView(mem)
        model = HM.Model(mview, Rig.Callbacks(self, mview, random.Random(call_seed)))
        model_error = None
        try:
            mret = model_run(model) if model_run else getattr(model, method)(*args)
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = [] if trace is not None else None
        emu.r[29] = emu.stack_hi - 0x100
        ints, nfloat, scratch = [], 0, world.argbuf
        for a, k in zip(args, kinds):
            if k in 'ci':
                ints.append(ee_emu.s32(a & M32))
            elif k == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, a[j])
                ints.append(scratch)
                scratch += 0x10
            elif k == 'l':
                for j, obj in enumerate(a):
                    mem.w32(scratch + 4 * j, obj)
                mem.w32(scratch + 4 * len(a), 0)
                ints.append(scratch)
                scratch += 4 * (len(a) + 1)
            elif k == 'f':
                emu.f[12 + nfloat] = a & M32
                nfloat += 1
        emu_error = None
        try:
            eret = emu_run() if emu_run else emu.call(addr, *ints, max_steps=4000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        if trace is not None and emu.trace:
            trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        out = {'key': key, 'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None,
               'both_fault': None, 'draws': 0, 'model_calls': model.calls, 'emu_calls': self.calls}
        if model_error or emu_error:
            if model_error is None or emu_error is None:
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            else:
                out['both_fault'] = getattr(emu_error, 'pc', 0)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = world.argbuf, world.argbuf + 0x100
        ebytes = self.stored_bytes(lo, hi)
        mbytes = set()
        for a, size, _value in model.writes:
            mbytes.update(range(a, a + size))
        diff = []
        for a in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            x, y = mem.load(a, 1), mview.load(a, 1)
            if x != y:
                diff.append((a, x, y))
        if ebytes != mbytes or diff:
            text = ''
            if ebytes - mbytes:
                text += ' only original stores %s;' % sorted({DA.where(world, a) for a in ebytes - mbytes})[:8]
            if mbytes - ebytes:
                text += ' only model stores %s;' % sorted({DA.where(world, a) for a in mbytes - ebytes})[:8]
            if diff:
                text += ' values differ at %s' % [(DA.where(world, a), '%02x' % x, '%02x' % y) for a, x, y in diff[:8]]
            out['writes'] = text
        s = seed_before
        for _ in range(model.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d' % model.draws
        out['draws'] = model.draws
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        out['ret'] = eret
        return out


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------------------
class Driver(DA.Driver):
    def between_mount(self, m):
        """What the rest of the game does to a mount between its ticks."""
        rng, mem, world = self.rng, self.mem, self.world
        r = rng.random
        if r() < 0.03:
            world.see_bias = rng.choice((0.06, 0.5, 0.5, 0.94))
        if r() < 0.04:
            mem.w32(m + 0x234, rng.choice([0] + [world.nodes[o] for o in world.others[:4] + world.players]))
        elif not mem.u32(m + 0x234) and mem.s16(m + 0x232) != 0x14 and r() < 0.3:
            player = rng.choice(world.players)
            mem.w32(player + 0xC, 0x40)
            mem.w32(m + 0x234, world.nodes[player])
        if r() < 0.06 or (mem.s16(m + 0x232) == 7 and r() < 0.3):      # the charge's wind-up flag 0x20
            mem.w16(m + 0x11A, rng.choice(DA.ANIM_FLAGS + (0x20, 0x28, 0x30, 0x38)))
        if r() < 0.03:
            mem.w32(m + 0xF4, (mem.u32(m + 0x300) + rng.choice((-5, 0, 1, 40, 400))) & M32)
        if r() < 0.03:
            mem.w32(m + 0x3D0, (mem.u32(m + 0x300) + rng.choice((-5, -1, 0, 1, 120))) & M32)
        if r() < 0.02:
            mem.w16(m + 0x3CC, rng.choice((0, 1, 2, 97, 98, 99, 100, 120)))
        if r() < 0.02:
            mem.w32(m + 0x3D4, rng.choice((0, 1)))
        if r() < 0.02:
            for off, values in ((0xD0, (7, 30, 31, 101, 0xFFFB)), (0xD2, (9, 45, 46, 150, 0xFFF9)), (0xD4, (50, 200))):
                mem.w16(m + off, rng.choice(values))
        for off in (0x314, 0x318, 0x31C):
            if r() < 0.015:
                mem.w16(m + off, rng.choice((0, 0, 1, 30)))
        if r() < 0.02:
            mem.w16(m + 0x38, rng.randrange(0x10000))
        if r() < 0.02:                                           # players dead or alive for the charge picker
            for p in world.players:
                mem.w32(p + 0xC, 0x40 | rng.choice((0, 0, 0, 8)))
        if r() < 0.004:
            mem.w16(m + 0x232, rng.choice((2, 4, 9, 0x11, 0x15, 0x19, 0x1B, 0x30, 0xFFF0)))

    def between_knight(self, c):
        """The rider's share of the arena driver (difftest_arena_monsters' knight branch)."""
        rng, mem, world = self.rng, self.mem, self.world
        r = rng.random
        if r() < 0.03:
            mem.w32(c + 0x234, rng.choice([0] + [world.nodes[o] for o in world.others[:4] + world.players]))
        if r() < 0.05:
            mem.w16(c + 0x11A, rng.choice(DA.ANIM_FLAGS))
        if r() < 0.04:
            mem.w32(c + 0x474, (mem.u32(c + 0x300) + rng.choice((-10, -1, 0, 1, 300))) & M32)
        if r() < 0.01:
            mem.w16(c + 0x472, rng.choice((0, 1, 5, 0xFFFF)))
        if r() < 0.01:
            mem.w32(c + 0x50, 0)
        elif r() < 0.1 and not mem.u32(c + 0x50):
            mem.w32(c + 0x50, c + 0x3D0)


# Factory rows (class-string address, row entry, constructor call, variant).  The
# on-foot rows pass the record's property-list pointer through unchanged and set
# the final Horsemen_ctor argument to zero.  The rider rows set it to one.
RIDER_ROWS = ((0x532CC8, 0x15B2D8, 0x15B3D4, 0), (0x532CD8, 0x15B318, 0x15B3D4, 1),
              (0x532CE8, 0x15B358, 0x15B3D4, 2), (0x532CF8, 0x15B398, 0x15B3D4, 3))
ON_FOOT_ROWS = ((0x532DC8, 0x15B804, 0x15B900, 0), (0x532DD8, 0x15B844, 0x15B900, 1),
                (0x532DE8, 0x15B884, 0x15B900, 2), (0x532DF8, 0x15B8C4, 0x15B900, 3))
NIGHTMARE_ROW = (0x532C98, 0x15B1B0, 0x15B1E4)


def factory_chain(elf, seed, story):
    """Each row executed from its name compare through the constructor it calls, with the
    REAL Horsemen_ctor and Nightmare_ctor underneath (only the allocator, GameObject_ctor,
    the statistics, the animation and the other leaves are scripted).  The model side is
    pool_new followed by Model.horsemen_ctor / Model.nightmare_ctor; calls, writes, seed
    and faults are compared as for every other call, and the link is then checked on the
    original's memory: both handles, the rider's state 0x1b and variant, the mount's state
    0, and the property list the mount's GameObject_ctor received.  The four on-foot rows
    also prove the record's property pointer reaches their GameObject_ctor unchanged."""
    bad = []
    rows = ([(a, e, s, v, 1) for a, e, s, v in RIDER_ROWS] +
            [(a, e, s, v, 0) for a, e, s, v in ON_FOOT_ROWS] +
            [NIGHTMARE_ROW + (None, 0)])
    for index, (string_at, entry, site, variant, mounted) in enumerate(rows):
        rig = Rig(elf, seed + index, 'mounted', 0, 1)
        world, emu = rig.world, rig.emu
        mem = emu.mem
        c, mount = world.C, world.mount
        name = mem.cstr(string_at)                      # copied in memory only
        name_at = emu.alloc(32)
        mem.write(name_at, (name if isinstance(name, bytes) else name.encode('ascii')) + b'\0')
        world.clear_creature()
        world.factory_pool = {0x478: c, 0x3D8: mount if mounted else c}
        pos = (f32(2000.0), f32(3000.0), f32(10.0))
        facing = 0xFFFF9000 if index & 1 else 0x2345
        props = world.props

        def emu_run():
            for j in range(3):
                mem.w32(world.argbuf + 4 * j, pos[j])
            emu.r[16], emu.r[18], emu.r[19] = name_at, ee_emu.s32(facing), props
            emu.r[20], emu.r[5] = world.argbuf, 0x530000
            assert emu.run(entry, until=(site + 8,), max_steps=4000000) == 'stop'
            return 0

        def model_run(model):
            if variant is not None:
                model.call('pool_new', 0x478)
                model.horsemen_ctor(c, name_at, pos, facing, props, variant, mounted)
            else:
                model.call('pool_new', 0x3D8)
                model.nightmare_ctor(c, name_at, pos, facing, props)

        result = rig.compare('factory row %x' % entry, (), seed * 1000003 + index, emu_run=emu_run,
                             model_run=model_run)
        for prop in ('fault', 'calls', 'writes', 'seed'):
            if result[prop]:
                bad.append('row %x: %s %s' % (entry, prop, result[prop]))
        ctor = [args for n, args in result['emu_calls'] if n == 'GameObject_ctor']
        if mounted:
            link, back = mem.u32(c + 0x3C8), mem.u32(mount + 0x3C8)
            checks = (link and mem.u32(link + 0xC) == mount, back and mem.u32(back + 0xC) == c,
                      mem.u16(c + 0x232) == 0x1B, mem.u8(c + 0x470) == variant, mem.u16(mount + 0x232) == 0,
                      mem.u32(c + 0x48) == AM.VT_HORSEMEN, mem.u32(mount + 0x48) == HM.VT_NIGHTMARE,
                      len(ctor) == 2 and ctor[1][2] == HM.DEF_NIGHTMARE and ctor[1][3] == HM.MOUNT_PROPS + 12 * variant,
                      mem.u32(c + 0xC) & 9 == 9)
        elif variant is not None:
            checks = (mem.u32(c + 0x48) == AM.VT_HORSEMEN, mem.u32(c + 0x3C8) == 0,
                      mem.u16(c + 0x232) == 0, mem.u8(c + 0x470) == variant,
                      len(ctor) == 1 and ctor[0][3] == props,
                      not any(n == 'Nightmare_ctor' for n, _ in result['emu_calls']))
        else:
            checks = (mem.u32(c + 0x48) == HM.VT_NIGHTMARE, mem.u32(c + 0x3C8) == 0, mem.u16(c + 0x232) == 0,
                      len(ctor) == 1 and ctor[0][3] == props)
        if not all(checks):
            bad.append('row %x: link checks %s' % (entry, ['ok' if x else 'FAIL' for x in checks]))
        else:
            kind = ('rider variant %d' % variant if mounted else
                    'on-foot variant %d' % variant if variant is not None else 'Nightmare alone')
            story['factory row built (%s)' % kind] = 1
    DC.report('factory rows', len(bad), len(rows), 'four rider rows, four on-foot rows and the Nightmare row; '
              'real constructors underneath; calls, writes, seed, links', bad)
    return len(rows)


def damage_routing_chain(elf, seed, story):
    """Execute separate lethal blows to rider and mount, then the on-foot rider.

    The scripted property lookup can set IgnoreDamage, so clear that synthetic
    flag explicitly; this probe is about the original damage and state code.
    """
    rig = Rig(elf, seed, 'mounted', 0, 1)
    world, mem = rig.world, rig.emu.mem
    rider, mount = world.C, world.mount
    world.clear_creature()
    world.factory_pool = {0x3D8: mount}
    pos = (f32(2.0), f32(3.0), f32(10.0))
    bad = []

    def compare(key, args, index):
        result = rig.compare(key, args, seed * 1000003 + index)
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                bad.append('%s: %s %s' % (key, prop, result[prop]))
        return result

    compare('Horsemen_ctor', (rider, world.strings['type'], pos, 0, world.props, 0, 1), 0)
    for obj in (rider, mount):
        mem.w8(obj + 0x231, 0)
        mem.wf32(obj + 0x228, 300.0)
        mem.wf32(obj + 0x22C, 300.0)
        mem.w64(obj + 0xA8, mem.u64(obj + 0xA8) & ~0x1000000000000)
    compare('Creature_takeDamage', (rider, 0, 0, f32(5000.0)), 1)
    hit = compare('Horsemen_run', (rider,), 2)
    rider_still_riding = (mem.u16(rider + 0x232) == 0x1B and mem.u32(rider + 0x3C8) != 0 and
                          mem.u16(mount + 0x232) == 0 and fl(mem.u32(rider + 0x228)) < 0 and
                          fl(mem.u32(mount + 0x228)) == 300.0)
    award = sum(name == 'player_giveExp' for name, _args in hit['emu_calls'])
    if not rider_still_riding or not award:
        bad.append('lethal rider hit: riding=%s experience calls=%d' % (rider_still_riding, award))
    compare('Creature_takeDamage', (mount, 0, 0, f32(5000.0)), 3)
    compare('Nightmare_run', (mount,), 4)
    dismounted = (mem.u16(mount + 0x232) == 0x14 and mem.u16(rider + 0x232) == 0x23 and
                  mem.u32(rider + 0x3C8) == mem.u32(mount + 0x3C8) == 0)
    if not dismounted:
        bad.append('lethal mount hit: mount/rider state or links differ')
    compare('Creature_takeDamage', (rider, 0, 0, f32(1.0)), 5)
    compare('Horsemen_run', (rider,), 6)
    if mem.u16(rider + 0x232) != 0x14:
        bad.append('on-foot rider did not enter death state after fresh damage')
    if not bad:
        story['lethal rider hit leaves linked rider alive in state 0x1b'] = 1
        story['lethal mount hit dismounts rider; later rider damage kills on foot'] = 1
        story['lethal linked rider hit called player_giveExp'] = award
    DC.report('directed damage routing', len(bad), 7,
              'rider HP, award, mount death, dismount, on-foot death; calls, writes, seed', bad)
    return 7


RUNS = (('nightmare', 0, 1), ('nightmare', 1, 0), ('mounted', 0, 1), ('mounted', 1, 1), ('mounted', 0, 0),
        ('mounted', 1, 0))


def run(elf, name, seed, kind, machine, net, ticks, coverage, counts, story):
    rig = Rig(elf, seed, kind, machine, net)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    mount = world.mount if kind == 'mounted' else c
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    serial = [0]
    draws_by_entry = {}
    tick = 0
    state = {'mount_live': False}

    def do(key, *args):
        serial[0] += 1
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s): %s' % (tick, key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), result[prop]))
        if result['both_fault'] is not None:
            both[result['both_fault']] = both.get(result['both_fault'], 0) + 1
            DC.FAULTS[result['both_fault']] = DC.FAULTS.get(result['both_fault'], 0) + 1
        if result.get('draws'):
            draws_by_entry[key] = draws_by_entry.get(key, 0) + result['draws']
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in run %s, tick %d, %s' % (name, tick, key))
                for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls']:
                    print('    ' + DC.fmt_call(call))
                sys.exit(1)
        return result

    def note(event):
        story[event] = story.get(event, 0) + 1

    def sane_stats(obj):
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(obj + 0x228, hp)
        mem.wf32(obj + 0x22C, hp)
        mem.w8(obj + 0x231, 0)
        mem.w32(obj + 0xC8, 0)

    def construct():
        world.clear_creature()
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        type_name = rng.choice((0, world.strings['type'], world.strings['type']))
        if kind == 'nightmare':
            props = rng.choice((world.props, HM.MOUNT_PROPS + 12 * rng.randrange(4)))
            do('Nightmare_ctor', c, type_name, pos, facing, props)
            sane_stats(c)
            note('nightmare built')
            return
        variant = rng.randrange(4)
        do('Horsemen_ctor', c, type_name, pos, facing, world.props, variant, 1)
        sane_stats(c)
        linked = mem.u32(c + 0x3C8)
        state['mount_live'] = bool(linked)
        if linked:
            assert mem.u32(linked + 0xC) == mount
            back = mem.u32(mount + 0x3C8)
            assert back and mem.u32(back + 0xC) == c, 'mount not linked back to the rider'
            sane_stats(mount)
            note('rider built with a mount (variant %d)' % variant)
        else:
            note('rider built without a mount (pool empty)')

    for tick in range(ticks):
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        if kind == 'mounted':
            driver.between_knight(c)
        live = kind == 'nightmare' or state['mount_live']
        if live:
            driver.between_mount(mount)
        # damage through slot 2, to the mount and to the rider
        if live and r() < 0.08:
            attacker = rng.choice(world.others + world.players + [0])
            flags = 0
            for _k in range(rng.choice((0, 1, 1, 2))):
                flags |= rng.choice(DC.DAMAGE_FLAGS)
            do('Creature_takeDamage', mount, attacker, flags, f32(rng.choice((0.0, 3.0, 20.0, 60.0, 400.0))))
        if kind == 'mounted' and r() < 0.06:
            do('Creature_takeDamage', c, rng.choice(world.others + world.players + [0]), rng.choice(DC.DAMAGE_FLAGS),
               f32(rng.choice((3.0, 20.0, 150.0))))
        if live and r() < 0.025 and mem.s16(mount + 0x232) != 0x14:      # a killing blow to the mount
            mem.w8(mount + 0x231, 0)
            do('Creature_takeDamage', mount, rng.choice(world.players + [0]), rng.choice(DC.DAMAGE_FLAGS), f32(5000.0))
        if kind == 'mounted' and not mem.u32(c + 0x3C8) and r() < 0.03 and mem.s16(c + 0x232) != 0x14:
            mem.w8(c + 0x231, 0)                                 # a killing blow to the knight on foot
            do('Creature_takeDamage', c, rng.choice(world.players + [0]), rng.choice(DC.DAMAGE_FLAGS), f32(5000.0))
        # the ticks: the mount first, then the rider
        if live:
            before = mem.s16(mount + 0x232)
            had_rider = mem.u32(mount + 0x3C8)
            do('Nightmare_run', mount)
            if before != 0x14 and mem.s16(mount + 0x232) == 0x14:
                note('mount died in its own tick (from state %x)' % (before & 0xFFFF))
                if had_rider:
                    if mem.s16(c + 0x232) == 0x23 and not mem.u32(c + 0x3C8):
                        note('rider sent to 0x23 by the mount\'s death')
                    else:
                        note('rider left linked by the mount\'s death (rider state %x, creature flags %x, '
                             'object flags %x)' % (mem.u16(c + 0x232), mem.u64(c + 0xA8), mem.u32(c + 0xC)))
            if mem.u32(mount + 0xC) & 0x4002 == 0x4002 and mem.s16(mount + 0x232) == 0x14:
                note('dead mount faded out and was deleted')
                if kind == 'mounted':
                    state['mount_live'] = False
                else:
                    driver.respawn()
                    continue
        if kind == 'mounted':
            before = mem.s16(c + 0x232)
            do('Horsemen_run', c)
            if before != 0x14 and mem.s16(c + 0x232) == 0x14:
                note('rider died %s' % ('while linked to a mount' if mem.u32(c + 0x3C8) else 'on foot'))
            if mem.u32(c + 0x3C8) and mem.s16(c + 0x232) < 0x19:
                note('rider linked with a state below 0x19')
        # requests from the rest of the game: every number, valid or not
        if live and r() < 0.10:
            do('Nightmare_setState', mount, rng.choice(NIGHTMARE_STATES))
        if kind == 'mounted' and r() < 0.06:
            before = mem.s16(c + 0x232)
            requested = rng.choice(DA.HORSEMEN_STATES)
            do('Horsemen_setState', c, requested)
            if mem.u32(c + 0x3C8) and requested == 0x14 and mem.s16(c + 0x232) == before:
                note('rider refused state 0x14 while mounted')
        # the mount's other entry points on their own
        if live and r() < 0.05:
            do('Nightmare_onHitTerrain', mount, (f32(rng.uniform(-1, 1)), f32(rng.uniform(-1, 1)), 0))
        if live and r() < 0.06:
            touched = [rng.choice(world.players + world.others) for _ in range(rng.choice((0, 1, 2, 3)))]
            do('Nightmare_onTouchList', mount, touched)
        if live and r() < 0.04:
            do('Nightmare_pickChargeTarget', mount)
        if live and r() < 0.04:
            do('Creature_angleToTarget', mount)
        if live and r() < 0.04:
            do('Horsemen_mountSeatTransform', mount, world.matrix)
        if live and r() < 0.04:
            do('Nightmare_draw', mount)
        if kind == 'mounted' and r() < 0.04:
            do('Horsemen_draw', c)
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, machine %s, %s' % (kind, 'B' if machine else 'A', 'net game' if net else 'offline')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count,
              'calls that stopped on one side only (%d stopped on both, the same way)' % sum(both.values()),
              bad['fault'])
    return count, draws_by_entry


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--ticks':
            OPTIONS['ticks'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        elif a == '--fpu':
            OPTIONS['fpu'] = args.pop(0)
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_horsemen_mount: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_horsemen_mount: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws, story = [None], {}, {}, {}
    total = 0
    if not OPTIONS['filter'] or OPTIONS['filter'].lower() in 'factory':
        total += factory_chain(elf, OPTIONS['seed'], story)
    if not OPTIONS['filter'] or OPTIONS['filter'].lower() in 'damage':
        total += damage_routing_chain(elf, OPTIONS['seed'], story)
    for index, (kind, machine, net) in enumerate(RUNS):
        name = '%s/%s/%s' % (kind, 'B' if machine else 'A', 'net' if net else 'off')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        n, d = run(elf, name, OPTIONS['seed'] + index, kind, machine, net, ticks, coverage, counts, story)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    print()
    print('seed %d' % OPTIONS['seed'])
    print('calls compared per entry point / calls with any mismatch / shared-seed draws seen')
    for key in sorted(counts):
        print('  %-32s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('lifecycle events seen (event: count):')
    for event in sorted(story):
        print('  %-58s %d' % (event, story[event]))
    if coverage[0] is not None:
        print('coverage of the original as executed here (basic blocks, instructions):')
        tb = tbt = ti = tit = 0
        for part in BODIES:
            b, bt, i, it = coverage[0].numbers(part)
            tb, tbt, ti, tit = tb + b, tbt + bt, ti + i, tit + it
            print('  %-32s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
                  % (part, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
        print('  %-32s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)'
              % ('all', tb, tbt, 100.0 * tb / tbt, ti, tit, 100.0 * ti / tit))
    if DC.FAULTS:
        print('calls in which the original read or wrote unmapped memory, and the model did too: %s'
              % ', '.join('%d at 0x%x' % (n, pc) for pc, n in sorted(DC.FAULTS.items())))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
