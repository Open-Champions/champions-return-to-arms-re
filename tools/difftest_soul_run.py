#!/usr/bin/env python3
"""difftest_soul_run.py - compare tools/ref_soul_run.py with the game's own code: the whole
of Soul_run (every state of its switch), Soul_isDemonNear inside it, and
Creature_setCharm (inside Soul_ctor and entered directly).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_soul_run.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                        [--ticks N] [-v] [--trace-first]

What is compared
    tools/difftest_combat_ctors2.py's world for the Soul class (the game's own tables of
    Demon, Player, Skelight, Skeleton, Soul and AntQueen; synthetic type descriptors),
    WITHOUT the switch patch: the original Soul_run runs to its end.  Real underneath:
    the creature base (ref_creature, ref_arena_monsters, ref_monsters_1), Soul_ctor,
    Soul_setState, Soul_getModel, Soul_isDemonNear, Creature_setCharm, the type-info
    getters, the C library, and the matrix helpers mat34_setPosRotZScale,
    mat34_rotateAxis, mat34_transformPoint, mat34_invert (with mat4_invert) and mat34_mul
    (ref_core, executed
    by tools/difftest_core.py).  Callbacks (recording stubs answered by the scripted
    world): world_collectObjectsInBox, model_getSamplePointCount, model_getSamplePoint,
    particle_spawn, terrain_height, damage_apply, obj_delete, obj_stopRunning,
    creature_getAttachMatrix0, model_getAttachMatrix, handle_clear, the anim calls.  Each
    call runs through the model first on a copy-on-write view of the same memory, and
    these must be equal: the calls with their arguments, the bytes stored outside the
    stack, the shared seed with its draw count, the result.

Scenarios
    machine A and B, 'seed' and 'seed + 1': constructions (with and without an owner,
    on "airhub" and elsewhere), then ticks of the run in any state the driver puts the
    soul in (all 35 and out-of-range numbers), with +0xf4 near the clock, the frame on
    and off the demon nibble, Demons (live and dead) planted around it, owner and thrown
    handles +0x3c8 / +0x3cc, clip flags 0x10 / 0x80, the inert byte +0x231, object flag
    2, players at the contact point of a thrown soul, sample-point counts of every sign;
    Creature_setCharm entered directly with object flags 0x20 / 0x40, +0x312 at -1 or
    not, any team and frames.
"""
import hashlib
import math
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
import ref_soul_run as SR                       # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_monsters_1 as DM                # noqa: E402
import difftest_combat_ctors as DT              # noqa: E402
import difftest_combat_ctors2 as DT2            # noqa: E402
from difftest_creature import Res, f32, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = DC.OPTIONS
OPTIONS.update({'seed': 20973, 'ticks': 3000})

REAL = set(DT2.REAL) | set(SR.MODELLED.values())         # mat4_invert: mat34_invert's own callee

BODIES = {
    'Soul_run': (0x2A9870, 0x2AA908),
    'Soul_isDemonNear': (0x2AB2B4, 0x2AB39C),
    'Creature_setCharm': (0x1189F0, 0x118A54),
    'Soul_setState': (0x2AAC38, 0x2AB298),
}

ENTRIES = dict(DT2.ENTRIES)
ENTRIES['Soul_run'] = (SR.SOUL_RUN, 'c', 'n', 'soul_run')
ENTRIES['Creature_setCharm'] = (SR.CREATURE_SET_CHARM, 'cii', 'n', 'creature_set_charm')

STATES = list(range(0, 0x23)) + [0x23, 0x24, 0x40, 0x7FFF, 0x8000, 0xFFFF]
HOT = (0, 0, 1, 1, 3, 5, 0x12, 0x14, 0x14, 0x17, 0x18, 0x19, 0x1B, 0x1B, 0x1B, 0x1D, 0x1D, 0x22, 0x22)


class RealSet:
    def __contains__(self, target):
        return target in REAL or DC.LIB_LO <= target < DC.LIB_HI


class World(DT2.World):
    """The ctors-2 world for the Soul, plus answers for the thrown and owned states."""

    def build(self, rng):
        DT2.World.build(self, rng)
        self.sample_counts = (0, 0, 1, 2, 3, 5, 0xFFFFFFFE)

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice(self.sample_counts))

    def _matrix(self, rng):
        return [f32(rng.uniform(-1.5, 1.5)) for _ in range(9)] + [f32(rng.uniform(-200, 200)) for _ in range(3)]

    def on_creature_getAttachMatrix0(self, args, view, rng):
        return Res(outs=[self._matrix(rng)])

    def on_model_getAttachMatrix(self, args, view, rng):
        return Res(outs=[self._matrix(rng)])


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

        for name, ext in SR.EXTERNALS.items():
            if name == 'cxx_throwBadTypeid':
                continue
            if ext.addr:
                add(ext.addr, name, ext)
            elif name in self.world.stub_addr:
                add(self.world.stub_addr[name], name, ext)
        for addr, name in list(self.world.stub_name.items()) + list(self.world.addr_name.items()):
            if addr not in self.names:
                add(addr, name, SR.EXTERNALS.get(name) or RC.Ext(0, 'p', 0, 'n'))

        def throw(emu):
            self.calls.append(('cxx_throwBadTypeid', ()))
            raise EmuError('__throw_bad_typeid')
        self.names[0x3B3338] = 'cxx_throwBadTypeid'
        emu.stub(0x3B3338, function=throw, name='cxx_throwBadTypeid')
        for entry, test, _method in CT.RUN_PROLOGUES.values():     # AntQueen and Skeleton only
            if entry != SR.SOUL_RUN:
                emu.patch(test, DT.ADDIU_V0_ZERO)
        self.partial, self.partial_ops = [], {}
        for start, end in list(DC.BODIES.values()) + list(DT.DA.BODIES.values()) + list(DM.BODIES.values()) + \
                list(DT.BODIES.values()) + list(DT2.BODIES.values()) + list(BODIES.values()):
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E) and pc not in self.partial_ops:
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))

    def make_stub(self, name, ext):
        """The usual recording stub; the two matrix call-outs also write their twelve
        floats through the out pointer."""
        base = DT.Rig.make_stub(self, name, ext)
        if name not in SR.MATRIX_OUT:
            return base

        def stub(emu):
            canon, _outs = self.decode(name, ext, emu)
            args = tuple(canon)
            self.calls.append((name, args))
            res = self.world.respond(name, args, self.eview, self.script_rng)
            out = emu.r[4 + SR.MATRIX_OUT[name]] & M32
            for k, value in enumerate(res.outs[0]):
                emu.mem.w32(out + 4 * k, value)
            return 0
        return stub

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ret = res.ret & (RC.M64 if SR.EXTERNALS[name].ret == 'q' else M32)
                return SR.shape_result(name, args, ret, res.f & M32, res.outs)
            return answer

    def compare(self, key, args, call_seed, trace=None):
        saved = DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks
        DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = ENTRIES, SR.Model, Rig.Callbacks
        try:
            return DM.Rig.compare(self, key, args, call_seed, trace)
        finally:
            DM.ENTRIES, DM.M1.Model, DM.Rig.Callbacks = saved


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


class Driver(DT.Driver):
    def between_class(self):
        DT.Driver.between_class(self)
        rng, mem, world = self.rng, self.mem, self.world
        c, r = world.C, rng.random
        clock = mem.u32(c + 0x300)
        if r() < 0.15:
            mem.w16(c + 0x232, rng.choice(HOT if r() < 0.7 else STATES))
        if r() < 0.12:
            mem.w32(c + 0xF4, (clock + rng.choice((-5, -1, 0, 1, 2, 30, 400))) & M32)
        if r() < 0.25:                                           # the demon nibble: due or not
            serial = mem.s8(c + 0x230)
            frame = mem.u32(RC.G_SIM_FRAME)
            due = (frame & ~0xF) | (serial & 0xF)
            mem.w32(RC.G_SIM_FRAME, (due if r() < 0.7 else due + rng.randrange(1, 16)) & M32)
        if r() < 0.2:                                            # Demons, live or dead, among the others
            for o in world.others[:4]:
                DT2.plant(world, rng, o, rng.choice(('Demon', 'Demon', 'Player', 'Skeleton', 'Soul', 'synthetic')))
        if r() < 0.06:                                           # the thrown target (+0x3cc) or none
            mem.w32(c + 0x3CC, rng.choice([0, 0] + [world.nodes[o] for o in world.others[:3] + world.players[:2]]))
            for o in world.others[:3] + world.players[:2]:
                mem.wf32(o + 0x308, rng.choice((0.0, 150.0, -200.0)))
                mem.wf32(o + 0x30C, rng.choice((0.0, 80.0, -120.0)))
                mem.wf32(o + 0x18, mem.f32(c + 0x18) + rng.choice((0.0, 40.0, -40.0, -400.0)))
        if r() < 0.05:                                           # an owner handle (state 0x1d's matrices)
            mem.w32(c + 0x3C8, rng.choice((0, world.nodes[world.others[1]])))
        if r() < 0.1:
            mem.w16(c + 0x11A, rng.choice((0, 0x10, 0x80, 0x90, 8, 0xFFFF)))
        if r() < 0.05:
            mem.w8(c + 0x231, rng.choice((0, 0, 1)))
        if r() < 0.05:
            mem.w32(c + 0xC, mem.u32(c + 0xC) & ~2)
        if r() < 0.1:                                            # a player at the contact point of a throw
            p = rng.choice(world.players)
            mem.w32(p + 0xC, rng.choice((0x40, 0x40, 0x48)))
            f = mem.s16(c + 0x38)
            ahead = rng.choice((36.0, 36.0, 40.0, 60.0, 0.0))
            mem.wf32(p + 0x10, mem.f32(c + 0x10) + ahead * math.cos(f * math.pi / 0x8000))
            mem.wf32(p + 0x14, mem.f32(c + 0x14) + ahead * math.sin(f * math.pi / 0x8000))
            mem.wf32(p + 0x18, mem.f32(c + 0x18) + rng.choice((-30.0, -36.0, 0.0, 20.0)))
            mem.wf32(p + 0x1C, rng.choice((12.0, 16.0, 30.0)))
            mem.wf32(p + 0x20, rng.choice((72.0, 0.0)))
        if r() < 0.04:
            mem.w32(RC.G_NUM_PLAYERS, rng.choice((0, 1, 2, 4)))
        if r() < 0.05:                                           # the wander destination
            for k in range(3):
                mem.wf32(c + 0x104 + 4 * k, mem.f32(c + 0x10 + 4 * k) + rng.choice((0.0, 1.0, 30.0, -200.0)))
        if r() < 0.05:
            mem.wf32(c + 0xDC, rng.choice((1.0, 0.5, 2.0)))
        if r() < 0.03:
            mem.w16(c + 0x314, rng.choice((0, 0, 3)))


def run(elf, name, seed, machine, ticks, coverage, counts):
    kind = 'soul'
    rig = Rig(elf, seed, kind, machine, 1)
    driver = Driver(rig)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    info = DT.CLASSES[kind]
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    c = world.C
    bad = {'calls': [], 'writes': [], 'seed': [], 'result': [], 'fault': []}
    both = {}
    serial = [0]
    draws_by_entry = {}
    states_seen = counts.setdefault('_states', {})
    tick = [0]

    def do(key, *args):
        serial[0] += 1
        state = mem.s16(c + 0x232)
        result = rig.compare(key, tuple(args), seed * 1000003 + serial[0], trace=cov.pcs)
        row = counts.setdefault(key, [0, 0])
        row[0] += 1
        if key == 'Soul_run':
            states_seen[state] = states_seen.get(state, 0) + 1
        failed = False
        for prop in ('fault', 'calls', 'writes', 'seed', 'result'):
            if result[prop]:
                failed = True
                bad[prop].append('tick %d %s(%s) state %#x: %s' % (tick[0], key, ', '.join(
                    '%x' % a if isinstance(a, int) else str(a) for a in args), state & 0xFFFF, result[prop]))
        if result['both_fault'] is not None:
            both[result['both_fault']] = both.get(result['both_fault'], 0) + 1
        if result.get('draws'):
            draws_by_entry[key] = draws_by_entry.get(key, 0) + result['draws']
        if failed:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in run %s, tick %d, %s state %#x' % (name, tick[0], key, state & 0xFFFF))
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

    def construct():
        world.clear_creature()
        if rng.random() < 0.3:
            world.set_level(rng.choice(DT.LEVELS))
        pos = (f32(2000.0 + rng.uniform(-50, 50)), f32(3000.0 + rng.uniform(-50, 50)), f32(10.0))
        facing = rng.choice((rng.randrange(0x10000), 0xFFFF8000 | rng.randrange(0x8000)))
        owner = rng.choice((0, 0, 0, world.others[1]))
        if rng.random() < 0.2:                                   # what Creature_setCharm tests
            mem.w16(c + 0x312, rng.choice((0xFFFF, 5)))
        values = {'c': c, 't': rng.choice(world.type_names), 'v': pos, 'f': facing, 'p': world.props, 'x': owner}
        do('Soul_ctor', *[values[k] for k in info['order']])
        hp = rng.choice((300.0, 300.0, 1200.0))
        mem.wf32(c + 0x228, hp)
        mem.wf32(c + 0x22C, hp)
        mem.w8(c + 0x231, 0)
        mem.w32(c + 0xC8, 0)

    def charm():
        saved = {off: mem.u32(c + off) for off in (0xC, 0x234, 0x310)}
        mem.w32(c + 0xC, rng.choice((0x20, 0x20, 0x60, 0x40, 0, 0x21, 0x10020)))
        mem.w16(c + 0x312, rng.choice((0, 0, 7, 0xFFFF, 0x8000)))
        mem.w32(c + 0x234, rng.choice([0] + [world.nodes[o] for o in world.others[:3]]))
        do('Creature_setCharm', c, rng.choice((0xFFFFFFFF, 0, 60, 0x12345, 0xFFFF8000)),
           rng.choice((0, 1, 2, 0xFF, 0x1FE, 0xFFFFFFFF)))
        if rng.random() < 0.8:                                   # back to the soul it was
            for off, v in saved.items():
                mem.w32(c + off, v)

    for t in range(ticks):
        tick[0] = t
        r = rng.random
        if driver.need_ctor:
            driver.need_ctor = False
            construct()
        driver.between()
        if driver.need_ctor:
            continue
        driver.between_class()
        if r() < 0.05:
            charm()
        do('Soul_run', c)
        if r() < 0.25:
            do('Soul_setState', c, rng.choice(info['states']))
        if r() < 0.005:
            construct()
        if mem.u32(c + 0xC) & 0x4000 and r() < 0.3 or mem.u32(c + 0xC) & 2 and r() < 0.1:
            driver.respawn()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = 'Soul run, machine %s' % ('B' if machine else 'A')
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
        print('difftest_soul_run: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('difftest_soul_run: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = max(OPTIONS['ticks'] // 10, 1) if OPTIONS['quick'] else OPTIONS['ticks']
    RC.C.set_fpu(OPTIONS['fpu'])
    started = time.time()
    coverage, counts, draws = [None], {}, {}
    total = 0
    for index, machine in enumerate((0, 1, 0, 1)):
        name = 'soul/%s%d' % ('B' if machine else 'A', index // 2)
        n, d = run(elf, name, OPTIONS['seed'] + index, machine, ticks, coverage, counts)
        total += n
        for key, value in d.items():
            draws[key] = draws.get(key, 0) + value
    states = counts.pop('_states', {})
    print()
    print('calls compared per entry point / calls with any mismatch / own and shared draws seen')
    for key in sorted(counts):
        print('  %-24s %7d / %d / %d' % (key, counts[key][0], counts[key][1], draws.get(key, 0)))
    print('Soul_run calls per state at entry: %s' % ', '.join('%#x:%d' % (s & 0xFFFF, n) for s, n in sorted(states.items())))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage[0].numbers(part)
        print('  %-24s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage[0].missing(part)))
    print('%d calls compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
