#!/usr/bin/env python3
"""difftest_combat_ctors2.py - compare tools/ref_combat_ctors2.py with the game's own code:
Skeleton_isEnemy, Skeleton_takeDamage, Soul_takeDamage and the inline destructors of
AntQueen, Skeleton, Soul, Fire, LooseFire and poisonGasSpell.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_combat_ctors2.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                             [--ticks N] [--cases N] [-k TEXT] [-v]
                                             [--trace-first]

What is compared
    Part 1, the creatures: tools/difftest_combat_ctors.py's rig and world.  Each creature
    is built by its ORIGINAL constructor with the game's own table, and the creature base
    (ref_creature, ref_arena_monsters, ref_monsters_1, ref_combat_ctors) runs for real
    under the new bodies.  These are real as well: Skeleton_isEnemy (also reached from the
    real Creature_pickTarget inside the run prologue), the two take-damage slots, the
    three class destructors with Creature_dtor 0x117128 and GameObject_dtor 0x14cf90
    underneath (tools/ref_combat_monsters.py, executed by tools/difftest_combat_monsters.py),
    the type-info getters of ref_combat_ctors2.TYPEINFO and the C library (type_info ==,
    strcmp, strncmp).  Other objects carry the game's own tables of Skeleton, Skelight,
    Soul, AntQueen, Player and Demon (planted: table, flags, creature flags, team byte,
    side byte) or the world's synthetic table, whose slot 0 answers a synthetic descriptor
    (one has the name "5Demon" at another address, one "8Skeleton").

    Part 2, the GameObjects: tools/difftest_potion_ctors.py's rig.  Each Fire, LooseFire
    and poison-gas cloud is built by its ORIGINAL constructor (compared too), then the
    destructor runs with flags 0-3, with and without a property list and an owner handle.
    Fire_run and LooseFire_run, whose ends call slot 1 with 3, run with the real
    destructor behind that slot.

    Both sides must agree on: the calls to everything outside the model, in order, with
    their arguments; the bytes stored outside the stack and their values; the shared seed
    0x404464 and its draw count; the result.
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
import ref_combat_ctors as CT                   # noqa: E402
import ref_combat_ctors2 as CT2                 # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DT              # noqa: E402
import difftest_potion_ctors as DP              # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 600, 'cases': 300})

REAL = set(DT.REAL) | set(CT2.MODELLED.values())

BODIES = {
    'Skeleton_isEnemy': (0x2A7E04, 0x2A7EF0), 'Skeleton_takeDamage': (0x2A774C, 0x2A7768),
    'AntQueen_takeDamage': (0x2378FC, 0x237918),
    'Soul_takeDamage': (0x2AA908, 0x2AAB60),
    'AntQueen_dtor': (0x3C3C10, 0x3C3C78), 'Skeleton_dtor': (0x3CC5B8, 0x3CC62C),
    'Soul_dtor': (0x3CC72C, 0x3CC7A0),
}
TI_BODIES = {'typeinfo %x' % g: (g, g + (0x40 if base is None else 0x50))
             for g, (_desc, _name, base) in CT2.TYPEINFO.items()}
GO_BODIES = {'Fire_dtor': (0x3C5050, 0x3C50B4), 'LooseFire_dtor': (0x3C6778, 0x3C67E4),
             'poisonGasSpell_dtor': (0x3C7878, 0x3C78E4)}

ENTRIES = dict(DT.ENTRIES)
ENTRIES.update({
    'Skeleton_isEnemy': (0x2A7E04, 'ci', 'i', 'skeleton_is_enemy'),
    'Skeleton_takeDamage': (0x2A774C, 'ciif', 'n', 'skeleton_take_damage'),
    'Soul_takeDamage': (0x2AA908, 'ciif', 'n', 'soul_take_damage'),
    'AntQueen_takeDamage': (0x2378FC, 'ciif', 'n', 'antqueen_take_damage'),
    'AntQueen_dtor': (0x3C3C10, 'ci', 'n', 'antqueen_dtor'),
    'Skeleton_dtor': (0x3CC5B8, 'ci', 'n', 'skeleton_dtor'),
    'Soul_dtor': (0x3CC72C, 'ci', 'n', 'soul_dtor'),
})
SLOT2_OF = {'antqueen': 'AntQueen_takeDamage', 'skeleton': 'Skeleton_takeDamage', 'soul': 'Soul_takeDamage'}
DTOR_OF = {'antqueen': 'AntQueen_dtor', 'skeleton': 'Skeleton_dtor', 'soul': 'Soul_dtor'}
PLANT_TABLES = {'Skeleton': CT2.VT_SKELETON, 'Skelight': CT2.VT_SKELIGHT, 'Soul': CT2.VT_SOUL,
                'AntQueen': CT2.VT_ANTQUEEN, 'Player': CT2.VT_PLAYER, 'Demon': CT2.VT_DEMON}
# authored property strings for GameObject_dtor's 'name=' scan (not game text)
PROP_TEXTS = (b'name=alpha', b'name=beta', b'Name=gamma', b'namex=1', b'name', b'name=', b'other=2')


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


# ---------------------------------------------------------------------------------------
# Part 1: the creatures
# ---------------------------------------------------------------------------------------
class World(DT.World):
    def build(self, rng):
        DT.World.build(self, rng)
        emu, mem = self.emu, self.mem
        for table in PLANT_TABLES.values():
            for slot in range(1, 40):
                fn = mem.u32(table + 8 * slot + 4)
                if fn not in REAL:
                    self.addr_name.setdefault(fn, 'Creature.v%d' % slot)
        mem.w32(self.vt_spell + 8 * 1 + 4, self.stub_for('Spell.v1'))
        self.fake_descs = []
        for text in (b'5Ghost', b'5Demon', b'8Skeleton', b'4Soul'):
            name, desc = emu.alloc(16), emu.alloc(16)
            mem.write(name, text + b'\0')
            mem.w32(desc, name)
            self.fake_descs.append(desc)
        self.texts = []
        for t in PROP_TEXTS:
            a = emu.alloc(0x20)
            mem.write(a, t + b'\0')
            self.texts.append(a)
        self.dprops = emu.alloc(0x40)

    def on_Creature_v0(self, args, view, rng):
        return Res(rng.choice(self.fake_descs))


class Rig(DT.Rig):
    def __init__(self, elf, seed, kind, machine, net):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf, fpu_model=OPTIONS['fpu'])
        self.world = World(emu, self.rng, kind, machine, net)
        emu.follow = self.real = RealSet()
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = DC.EmuView(emu)
        self.script_rng = None
        self.names = {}

        def add(addr, name, ext):
            if addr in REAL:
                return
            assert self.names.setdefault(addr, name) == name, (hex(addr), name, self.names[addr])
            emu.stub(addr, function=self.make_stub(name, ext), name=name)

        for name, ext in CT2.EXTERNALS.items():
            if name == 'cxx_throwBadTypeid':
                continue
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, CT2.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))

        def throw(emu):
            self.calls.append(('cxx_throwBadTypeid', ()))
            raise EmuError('__throw_bad_typeid')
        self.names[0x3B3338] = 'cxx_throwBadTypeid'
        emu.stub(0x3B3338, function=throw, name='cxx_throwBadTypeid')
        for _entry, test, _method in CT.RUN_PROLOGUES.values():
            emu.patch(test, DT.ADDIU_V0_ZERO)
        # the take-damage entries are the class's own slot 2, read from its table
        info = DT.CLASSES[kind]
        assert emu.mem.u32(info['table'] + 8 * 2 + 4) == ENTRIES[SLOT2_OF[kind]][0]
        assert emu.mem.u32(info['table'] + 8 * 1 + 4) == ENTRIES[DTOR_OF[kind]][0]
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DT.DA.BODIES.values()) + list(DM.BODIES.values()) + \
                list(DT.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if CT2.EXTERNALS[name].ret == 'q' else M32)
                return CT2.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, CT2.Model, Rig.Callbacks
        try:
            return DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved


class Coverage(DC.Coverage):
    def __init__(self, mem, bodies):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in bodies.items()}
        self.pcs = set()


def plant(world, rng, obj, cls):
    """Give an other object a class: the game's table (or the synthetic one), flags,
    creature flags, team byte and side byte."""
    mem = world.mem
    if cls in PLANT_TABLES:
        mem.w32(obj + 0x48, PLANT_TABLES[cls])
    else:
        mem.w32(obj + 0x48, rng.choice((world.vt_base, world.vt_hooked)))
    flags = 0x40 if cls == 'Player' else 0x20
    mem.w32(obj + 0xC, rng.choice((flags, flags, flags, flags | 8, 0x20008, 0x30, 0, 0x60)))
    mem.w64(obj + 0xA8, rng.choice((0, 0, 0, 0, 0x4000000, 0x800, 0x100000000000)))
    c_team = mem.s8(world.C + 0x310)
    mem.w8(obj + 0x310, rng.choice((c_team & 0xFF, 0, 1, 2, 0xFF)))
    mem.w8(obj + 0x3D4, rng.choice((0, 1, 1, 2, 2, 3, 0xFF)))


def run(elf, name, seed, kind, machine, net, ticks, coverage, counts):
    rig = Rig(elf, seed, kind, machine, net)
    driver = DT.Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DT.CLASSES[kind]
    if coverage[0] is None:
        coverage[0] = Coverage(mem, dict(BODIES, **TI_BODIES))
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    serial = [0]
    stats = counts.setdefault('_results', {})
    tick = 0
    cls = info['name']

    def do(key, *args):
        serial[0] += 1
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0, 0])
        row[0] += 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s): %s' % (tick, key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), result[prop]))
        if result['both_fault'] is not None:
            row[2] += 1
            stops = counts.setdefault('_stops', {})
            where = (key, '%x' % result['both_fault'])
            stops[where] = stops.get(where, 0) + 1
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
        elif key == 'Skeleton_isEnemy' and result['both_fault'] is None:
            stats.setdefault(key, {})
            value = result.get('ret', 0) & M32
            stats[key][value] = stats[key].get(value, 0) + 1
        return result

    def construct():
        world.clear_creature()
        if kind == 'skeleton' and rng.random() < 0.3:
            mem.w32(CT.SKEL_COMMON + 4, mem.u32(CT.G_LUMP_GENERATION) ^ rng.choice((1, 0x100)))
        if rng.random() < 0.3:
            world.set_level(rng.choice(DT.LEVELS))
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        extra = rng.choice(info.get('extra', (0,)))
        if kind == 'soul':
            extra = rng.choice((0, 0, 0, world.others[1]))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': extra}
        do(cls + '_ctor', *[values[k] for k in info['order']])
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(c + 0x228, hp)
        mem.wf32(c + 0x22C, hp)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

    def destroy():
        if rng.random() < 0.7:                                  # a property list with names
            picks = [rng.choice(world.texts) for _ in range(rng.randrange(0, 6))]
            for i, t in enumerate(picks):
                mem.w32(world.dprops + 4 * i, t)
            mem.w32(world.dprops + 4 * len(picks), 0)
            mem.w32(c + 0x2C, world.dprops)
        elif rng.random() < 0.5:
            mem.w32(c + 0x2C, 0)
        if kind in ('skeleton', 'soul'):
            for off in (0x3C8, 0x3CC):
                if rng.random() < 0.5:
                    mem.w32(c + off, rng.choice([world.nodes[o] for o in world.others[:3]]))
        do(DTOR_OF[kind], c, rng.choice((0, 1, 2, 3)))
        driver.need_ctor = True

    def ti_reset():
        for desc, _name, _base in CT2.TYPEINFO.values():
            if rng.random() < 0.5:
                for k in range(3):
                    mem.w32(desc + 4 * k, 0)

    for tick in range(ticks):
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        driver.between_class()
        if r() < 0.01:
            ti_reset()
        if kind == 'skeleton':
            for _ in range(rng.choice((0, 1, 2, 3))):
                other = rng.choice(world.others + world.players)
                plant(world, rng, other, rng.choice(list(PLANT_TABLES) + ['synthetic', 'Skeleton', 'Skeleton']))
                charm = mem.u16(c + 0x312)
                if r() < 0.3:
                    mem.w16(c + 0x312, rng.choice((0, 5, 0xFFFF)))
                if r() < 0.3:
                    mem.w8(c + 0x3D4, rng.choice((0, 1, 2, 2, 3)))
                target = rng.choice((other, other, other, other, other, 0, c))
                do('Skeleton_isEnemy', c, target)
                mem.w16(c + 0x312, charm)
        if kind in ('skeleton', 'antqueen') and r() < 0.05:
            attacker = rng.choice(world.others + world.players + [0])
            do(SLOT2_OF[kind], c, attacker, rng.choice(DC.DAMAGE_FLAGS),
               f32(rng.choice((0.0, 3.0, 20.0, 400.0))))
        if kind == 'soul' and r() < 0.25:
            pick = rng.random()
            if pick < 0.03:
                attacker = 0
            elif pick < 0.15 and mem.u32(c + 0x3C8):
                attacker = mem.u32(mem.u32(c + 0x3C8) + 0xC)
            else:
                attacker = rng.choice(world.others + world.players)
                plant(world, rng, attacker, rng.choice(('Demon', 'Demon', 'Demon', 'Player', 'Skelight', 'Skeleton',
                                                        'Soul', 'synthetic', 'synthetic')))
            do('Soul_takeDamage', c, attacker, rng.choice(DC.DAMAGE_FLAGS),
               f32(rng.choice((0.0, 3.0, 20.0, 60.0, 400.0, 5000.0))))
        do(cls + '_run', c)
        for _ in range(rng.choice((0, 1, 1, 2))):
            do(cls + '_setState', c, rng.choice(info['states']))
        if r() < 0.03:
            construct()
        if r() < 0.015:
            destroy()
            continue
        if mem.s16(c + 0x232) == 0x14 and r() < 0.2 or mem.u32(c + 0xC) & 0x4000 and r() < 0.3:
            if r() < 0.5:
                destroy()
            else:
                driver.respawn()
    if not driver.need_ctor:
        destroy()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, machine %s' % (cls, 'B' if machine else 'A')
    count = serial[0]
    DC.report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    DC.report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    DC.report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    DC.report(name + ' result', len(bad['result']), count, 'returned values', bad['result'])
    DC.report(name + ' faults', len(bad['fault']), count, 'calls that stopped on one side only', bad['fault'])
    return count


RUNS = tuple((kind, machine, 1) for kind in ('skeleton', 'soul', 'antqueen') for machine in (0, 1))


# ---------------------------------------------------------------------------------------
# Part 2: the GameObjects (difftest_potion_ctors' rig)
# ---------------------------------------------------------------------------------------
GO_DTORS = {'Fire_dtor': (0x3C5050, 'ii', 'n', 'fire_dtor'),
            'LooseFire_dtor': (0x3C6778, 'ii', 'n', 'loosefire_dtor'),
            'poisonGasSpell_dtor': (0x3C7878, 'ii', 'n', 'poison_gas_dtor')}
GO_STUBS = {0x1A1698: 'handle_clear', 0x14BE58: 'objNames_remove', 0x150470: 'pool_free'}
GO_CTOR = {'Fire_dtor': 'Fire_ctor', 'LooseFire_dtor': 'LooseFire_ctor', 'poisonGasSpell_dtor': 'poisonGasSpell_ctor'}
GO_RUN = {'Fire_dtor': 'Fire_run', 'LooseFire_dtor': 'LooseFire_run'}


class GORig(DP.Rig):
    """The potion rig with the destructors real behind slot 1 and the model of
    ref_combat_ctors2.GOModel."""

    def __init__(self, elf):
        saved = dict(DP.STUBS)
        for addr in (DP.DTOR_LOOSEFIRE, DP.DTOR_FIRE):
            DP.STUBS.pop(addr, None)
        try:
            DP.Rig.__init__(self, elf)
        finally:
            DP.STUBS.clear()
            DP.STUBS.update(saved)
        emu = self.emu
        self.real = set(DP.REAL) | {0x3C5050, 0x3C6778, 0x3C7878, 0x14CF90}
        real = self.real
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in real or DP.LIB_LO <= t < DP.LIB_HI})()
        for addr, name in GO_STUBS.items():
            emu.stub(addr, function=self.make_stub(name, CT2.GO_EXTERNALS[name]), name=name)
        self.texts = []
        for t in PROP_TEXTS:
            a = emu.alloc(0x20)
            emu.mem.write(a, t + b'\0')
            self.texts.append(a)
        self.props = emu.alloc(0x40)

    def compare(self, key, args):
        saved = (DP.REAL, DP.STUBS, DP.ENTRIES, DP.PC.Model)
        stubs = {a: n for a, n in DP.STUBS.items() if a not in (DP.DTOR_LOOSEFIRE, DP.DTOR_FIRE)}
        stubs.update(GO_STUBS)
        DP.REAL, DP.STUBS, DP.ENTRIES, DP.PC.Model = self.real, stubs, dict(DP.ENTRIES, **GO_DTORS), CT2.GOModel
        try:
            return DP.Rig.compare(self, key, args)
        finally:
            DP.REAL, DP.STUBS, DP.ENTRIES, DP.PC.Model = saved


def go_part(elf, seed, cases):
    rig = GORig(elf)
    mem = rig.emu.mem
    total, failed, rows = 0, 0, []
    for key in GO_DTORS:
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rng = random.Random('%d/%s' % (seed, key))
        n_ok = n_bad = n_run = 0
        shown = []
        for n in range(cases):
            ctor = GO_CTOR[key]
            args = DP.generate(rig, ctor, rng, n)
            problems = rig.compare(ctor, args)
            obj = args[0]
            via_run = key in GO_RUN and rng.random() < 0.3
            if not problems:
                if rng.random() < 0.6:
                    picks = [rng.choice(rig.texts) for _ in range(rng.randrange(0, 6))]
                    for i, t in enumerate(picks):
                        mem.w32(rig.props + 4 * i, t)
                    mem.w32(rig.props + 4 * len(picks), 0)
                    mem.w32(obj + 0x2C, rig.props)
                if key != 'Fire_dtor' and rng.random() < 0.3:
                    mem.w32(obj + 0x4C, rig.nodes[n % 4])
                for off in (0, 4, 8):
                    if rng.random() < 0.5:
                        mem.w32(obj + off, rig.nodes[(n + off) % 4])
                if via_run:                             # the run's own end: slot 1 with 3
                    if key == 'Fire_dtor':
                        mem.w16(obj + 0x4C, rng.choice((1, 0, 0xFFFF)))
                    else:
                        mem.w32(obj + 0x50, (RC.s32(mem.u32(RC.G_SIM_FRAME)) - rng.choice((1, 50))) & M32)
                    problems = rig.compare(GO_RUN[key], (obj,))
                    n_run += 1
                else:
                    problems = rig.compare(key, (obj, rng.choice((0, 1, 2, 3))))
            total += 1
            if problems:
                n_bad += 1
                if len(shown) < 3:
                    shown.append('case %d: %s' % (n, '; '.join(problems)))
            else:
                n_ok += 1
        failed += n_bad
        rows.append((key, cases, n_bad, n_run, shown))
    if rig.unknown:
        failed += 1
        rows.append(('unknown calls', 0, len(rig.unknown), 0,
                     [', '.join('%x x%d' % kv for kv in sorted(rig.unknown.items()))]))
    return total, failed, rows, rig.pcs


# ---------------------------------------------------------------------------------------
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
        elif a == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = a
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_combat_ctors2: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_combat_ctors2: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    cases = max(OPTIONS['cases'] // 10, 8) if OPTIONS['quick'] else OPTIONS['cases']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts = [None], {}
    total = 0
    for index, (kind, machine, net) in enumerate(RUNS):
        name = '%s/%s' % (kind, 'B' if machine else 'A')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower() and \
                OPTIONS['filter'].lower() not in DTOR_OF[kind].lower():
            continue
        total += run(elf, name, OPTIONS['seed'] + index, kind, machine, net, ticks, coverage, counts)
    go_total, go_failed, go_rows, go_pcs = go_part(elf, OPTIONS['seed'], cases)
    print()
    print('part 1: calls compared per entry point / with any mismatch / stopped the same way on both sides')
    results = counts.pop('_results', {})
    stops = counts.pop('_stops', {})
    for key in sorted(counts):
        print('  %-24s %7d / %d / %d' % (key, counts[key][0], counts[key][1], counts[key][2]))
    for key, values in results.items():
        print('  %s results seen: %s' % (key, ', '.join('%d x%d' % kv for kv in sorted(values.items()))))
    for (key, pc), n in sorted(stops.items()):
        print('  stopped on both sides: %s at %s x%d%s' % (key, pc, n, ' (__throw_bad_typeid stub)' if pc == '0' else ''))
    print('part 2: cases per destructor / mismatches / of them through the run\'s own slot-1 call')
    for key, n, bad, via, shown in go_rows:
        print('  %-24s %7d / %d / %d' % (key, n, bad, via))
        for line in shown:
            print('      ' + line[:600])
    print('coverage of the original as executed here (basic blocks, instructions):')
    if coverage[0] is not None:
        for part in coverage[0].parts:
            b, bt, i, it = coverage[0].numbers(part)
            if not i:
                continue
            print('  %-24s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
            if OPTIONS['verbose'] and b != bt:
                print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    for part, (start, end) in GO_BODIES.items():
        hit = sum(1 for pc in range(start, end, 4) if pc in go_pcs)
        print('  %-24s                    instructions %4d of %4d' % (part, hit, (end - start) // 4))
        if OPTIONS['verbose'] and hit != (end - start) // 4:
            print('      not executed: %s' % ' '.join('%06x' % a for a in range(start, end, 4) if a not in go_pcs))
    print('%d creature calls and %d GameObject cases compared in %.0f s' % (total, go_total, time.time() - started))
    ok = all(ok for _name, ok in DC.RESULTS) and go_failed == 0
    print('summary: %s' % ('0 mismatches' if ok else 'MISMATCHES'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
