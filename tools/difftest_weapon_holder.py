#!/usr/bin/env python3
"""difftest_weapon_holder.py - compare tools/ref_weapon_holder.py with the game's own code:
the Weapon1 and WeaponShield virtual slots 1-17, creature_buildElementDamage,
damageDesc_getElement and creature_dropHeldPartAsProp.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_weapon_holder.py [path/to/SLUS_209.73] [--seed N] [--cases N]
                                             [--quick] [-v] [--trace-first]

What is compared
    Holders of both classes, with the game's own virtual table at +0, random hand bits,
    parts and descriptor ids, are handed to each slot body (taken from the table) with
    every hand number 0, 1, 2, 3, -1 and the slots' other arguments; the three helpers
    are also called directly.  Everything listed in ref_weapon_holder.EXECUTED runs for
    real; the C library too.  Callbacks (recording stubs answered by a scripted world):
    the Skills' slot 11 through their +0x60 tables (synthetic Skill objects planted in
    g_skillTable), the creature's slot 16 (a synthetic table), model_getAttachPoint,
    pool_new, PhProp_ctor.  Each call runs through the model first on a copy-on-write
    view of the same memory, and these must be equal: the callbacks in order with their
    arguments (vectors read at the call), every byte stored outside the stack, the
    shared seed 0x404464 with its draw count, the result.

MiniRig, the small rig this file defines, is also used by tools/difftest_combat_death.py.
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
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_weapon_holder as WH                  # noqa: E402
import difftest_creature as DC                  # noqa: E402

M32, M64 = RC.M32, RC.M64
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'seed': 20973, 'cases': 6000, 'quick': False, 'verbose': False, 'trace_first': False}
STUB_BASE = 0x00F80000
LCG_A, LCG_C = 0x19660D, 0x3C6EF35F


def f32(v):
    return struct.unpack('<I', struct.pack('<f', v))[0]


def find_elf(args):
    for a in args:
        if not a.startswith('-') and os.path.exists(a):
            return a
    for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
        if os.path.exists(candidate):
            return candidate
    return None


def check_elf(elf, tool):
    if elf is None or not os.path.exists(elf):
        print('%s: SLUS_209.73 not found - nothing to compare with (this is not a failure)' % tool)
        return False
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DC.EXPECTED_SHA256:
        print('%s: %s is not SLUS_209.73 US v2.00 - skipped' % (tool, elf))
        return False
    return True


# ---------------------------------------------------------------------------------------
# A small rig: real bodies, named stubs with decoders, one compare per call
# ---------------------------------------------------------------------------------------
class Answer:
    """A callback's answer: an integer result, an optional float result, and the values
    written through output pointers (applied to the interpreter's memory by the stub's
    writer; handed to the model as the call's result)."""

    def __init__(self, ret=0, f=None, outs=None):
        self.ret, self.f, self.outs = ret, f, outs


class MiniRig:
    """Runs one body for real with the listed callees real and every named callee a
    recording stub; runs the model on a copy-on-write view first; compares."""

    def __init__(self, elf, real, stubs, world):
        """real: addresses that run for real.  stubs: name -> (address or None,
        decoder(emu) -> args tuple, writer(emu, answer) or None).  An address of None
        gets a fresh address in the stub page (for synthetic tables).  world.respond(name,
        args, rng) -> Answer."""
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.mem.map(STUB_BASE, 0x1000)
        self.world = world
        self.real = set(real)
        self.addr_of, self.name_of, self.decoders = {}, {}, {}
        free = STUB_BASE
        for name, (addr, decoder, writer) in stubs.items():
            if addr is None:
                addr, free = free, free + 8
            self.addr_of[name], self.name_of[addr] = addr, name
            self.decoders[name] = decoder
            emu.stub(addr, function=self._stub(name, decoder, writer), name=name)
        emu.follow = DC.RealSet(self.real)
        self.calls, self.unknown, self.rng = [], {}, None
        self.trace = set()

    def _stub(self, name, decoder, writer):
        def run(emu):
            args = decoder(emu)
            self.calls.append((name, args))
            answer = self.world.respond(name, args, self.rng)
            if writer is not None:
                writer(emu, answer)
            if answer.f is not None:
                emu.f[0] = answer.f & M32
            return answer.ret & M64
        return run

    def callbacks(self, rng):
        world = self.world

        class CB:
            def get(self, name):
                def answer(*args):
                    a = world.respond(name, args, rng)
                    if a.outs is not None:
                        return a.outs
                    return a.f if a.f is not None else a.ret
                return answer
        return CB()

    def compare(self, entry, args, model_cls, run_model, call_seed, fargs=(), ret_kind='i'):
        """Run run_model(model_cls(view, callbacks)) and the original at entry with the
        integer args (sign-extended) and the float args (raw patterns in f12...).
        Returns a dict of mismatches."""
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        view = DC.ModelView(mem)
        model = model_cls(view, self.callbacks(random.Random(call_seed)))
        model_error = None
        try:
            mret = run_model(model)
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls = []
        self.rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        emu_error = None
        for k, raw in enumerate(fargs):
            emu.f[12 + k] = raw & M32
        try:
            eret = emu.call(entry, *[ee_emu.s32(a & M32) for a in args], max_steps=2000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        self.trace.update(emu.trace)
        for rec in emu.calls:
            if rec.target not in self.real and rec.target not in self.name_of and \
                    not DC.LIB_LO <= rec.target < DC.LIB_HI:
                self.unknown[rec.target] = self.unknown.get(rec.target, 0) + 1
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None, 'both_fault': None,
               'draws': model.draws, 'model_calls': model.calls, 'emu_calls': self.calls}
        if model_error or emu_error:
            if model_error is None or emu_error is None:
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            else:
                out['both_fault'] = True
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        ebytes = set()
        for _pc, a, size, _v in emu.writes:
            ebytes.update(range(a, a + size))
        mbytes = set()
        for a, size, _v in model.writes:
            mbytes.update(range(a, a + size))
        diff = [(a, mem.load(a, 1), view.load(a, 1)) for a in sorted(ebytes | mbytes)
                if mem.load(a, 1) != view.load(a, 1)]
        if ebytes != mbytes or diff:
            out['writes'] = 'only original %s; only model %s; values differ %s' % (
                ['%x' % a for a in sorted(ebytes - mbytes)][:8], ['%x' % a for a in sorted(mbytes - ebytes)][:8],
                [('%x' % a, '%02x' % x, '%02x' % y) for a, x, y in diff[:8]])
        s = seed_before
        for _ in range(model.draws):
            s = (s * LCG_A + LCG_C) & M32
        if not mem.u32(RC.G_RAND_SEED) == view.load(RC.G_RAND_SEED, 4) == s:
            out['seed'] = 'model draws %d, original seed %08x, model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), view.load(RC.G_RAND_SEED, 4))
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'original %08x model %08x' % (eret & M32, (mret or 0) & M32)
        return out


class Tally:
    def __init__(self, label):
        self.label = label
        self.counts, self.bad, self.both, self.draws = {}, {}, 0, 0

    def add(self, key, result, describe):
        self.counts[key] = self.counts.get(key, 0) + 1
        self.draws += result['draws']
        if result['both_fault']:
            self.both += 1
        problems = [p for p in ('fault', 'calls', 'writes', 'seed', 'result') if result[p]]
        if problems:
            self.bad.setdefault(key, []).append('%s: %s' % (describe(), '; '.join(
                '%s %s' % (p, result[p]) for p in problems)))
            if OPTIONS['trace_first']:
                print('first mismatch:', self.bad[key][-1])
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls']:
                    print('    ' + DC.fmt_call(call))
                sys.exit(1)
        return not problems

    def report(self):
        ok = True
        for key in sorted(self.counts):
            bad = self.bad.get(key, [])
            ok = ok and not bad
            print('%s  %-36s %7d calls  %d mismatches' % ('PASS' if not bad else 'FAIL', key, self.counts[key],
                                                         len(bad)))
            if bad and OPTIONS['verbose']:
                for line in bad[:5]:
                    print('        ' + line[:1000])
        return ok


def coverage_lines(trace, mem, bodies, names):
    """Per body: blocks and instructions executed (DC.analyse on [start, end))."""
    lines = []
    for start, end in bodies:
        leaders, _sites = DC.analyse(mem, start, end)
        inside = {pc for pc in trace if start <= pc < end}
        missing = sorted(a for a in leaders if a not in trace)
        lines.append((names.get(start, '%x' % start), start, len(leaders & inside), len(leaders), len(inside),
                      (end - start) // 4, missing))
    return lines


def print_coverage(lines, verbose):
    print('coverage of the original as executed here (basic blocks, instructions):')
    for name, start, b, bt, i, it, missing in lines:
        print('  %-34s %06x  blocks %3d of %3d  instructions %4d of %4d' % (name, start, b, bt, i, it))
        if verbose and missing:
            print('      never entered: %s' % ' '.join('%06x' % a for a in missing))


# ---------------------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------------------
def regs(*idx):
    return lambda emu: tuple(emu.r[i] & M32 for i in idx)


def vec_at(emu, addr):
    return tuple(emu.mem.u32(addr + 4 * k) for k in range(3))


def write_vec(reg):
    def writer(emu, answer):
        if answer.outs is not None:
            for k in range(3):
                emu.mem.w32((emu.r[reg] & M32) + 4 * k, answer.outs[k] & M32)
    return writer


HOLDER_STUBS = {
    'Skill.v11': (None, regs(4, 5, 6, 7), None),
    'Creature.v16': (None, regs(4), None),
    # (scale f12, model, position copy, facing, anim state, bone; point out, second out)
    'model_getAttachPoint': (0x1754A0, lambda e: (e.f[12] & M32, e.r[4] & M32, vec_at(e, e.r[5] & M32),
                                                   e.r[6] & M32, e.r[7] & M32, e.r[8] & M32), write_vec(9)),
    'pool_new': (0x14FDB8, regs(4), None),
    # (scale f12, block, position, lump, model, texture, part mask, flags, item record)
    'PhProp_ctor': (0x155A0C, lambda e: (e.f[12] & M32, e.r[4] & M32, vec_at(e, e.r[5] & M32))
                    + tuple(e.r[i] & M32 for i in range(6, 12)), None),
}


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
IDS = (0xFFFF, 0xFFFF, 0x15, 0x16, 0x17, 0x18, 0x1F, 0x26, 0x23, 0x14, 0, 0x7FFF, 0x8015)
SKILL_VALUES = (0, 1, 3, 7, 10, 40, 133, 255, 0x7FFF, 0x8000, 0x12345, -1, -50, 0xFFFF)
LEVELS = (1.0, 2.5, 7.9, 30.0, 61.5, 0.0, -3.0, 1e9, 99.99)


class World:
    def __init__(self, rig_emu, rng):
        self.emu, self.mem, self.rng = rig_emu, rig_emu.mem, rng
        self.blocks = []

    def build(self, stub_addr):
        emu, mem, rng = self.emu, self.mem, self.rng
        # Skill objects: +0x60 -> a table whose slot 11 (+0x58 adjust, +0x5c function) is
        # the stub; some with a non-zero 'this' adjustment
        self.skills = {}
        for index in (12, 13, 14, 25, 26):
            obj = emu.alloc(0x100)
            table = emu.alloc(0x100)
            mem.w32(obj + 0x60, table)
            mem.w16(table + 0x58, rng.choice((0, 0, 8, 0x10)))
            mem.w32(table + 0x5C, stub_addr['Skill.v11'])
            mem.w32(WH.G_SKILL_TABLE + 4 * index, obj)
            self.skills[index] = obj
        # creatures for the part drop: a synthetic table whose slot 16 is the stub
        self.ctable = emu.alloc(0x200)
        mem.w16(self.ctable + 0x80, 0)
        mem.w32(self.ctable + 0x84, stub_addr['Creature.v16'])
        self.creatures = [emu.alloc(0x400) for _ in range(3)]
        self.definitions = []
        for _ in range(3):
            d = emu.alloc(0x810)
            for k in range(0x101):
                rec = emu.alloc(0x20)
                mem.w8(rec + 0x13, rng.choice((0, 1, 5, 17, 0x80, 0xFF)))
                mem.w32(d + 8 * k + 4, rec)
                mem.w32(d + 8 * k, rng.getrandbits(32) | 1)
            self.definitions.append(d)
        self.holders = [emu.alloc(0x100) for _ in range(4)]
        self.prop_block = emu.alloc(WH.PROP_SIZE)

    def randomise_creature(self, c):
        mem, rng = self.mem, self.rng
        mem.w32(c + 0xC, rng.choice((0, 0x20, 0x22, 2, 0x4020)))
        mem.w32(c + 0x24, rng.choice(self.definitions))
        for k in range(3):
            mem.w32(c + 0x10 + 4 * k, f32(rng.uniform(-3000, 3000)))
        mem.w16(c + 0x38, rng.randrange(0x10000))
        mem.w32(c + 0x48, self.ctable)
        mem.w64(c + 0xA8, rng.choice((0, 0, 0x1000000, 0x100000000, 0x101000000, 0x2000, rng.getrandbits(64))))
        mem.w32(c + 0xDC, f32(rng.choice((1.0, 0.8, 1.25, 2.0))))

    def randomise_holder(self, h, table):
        mem, rng = self.mem, self.rng
        mem.w32(h, table)
        mem.w8(h + 4, rng.choice((0, 1, 2, 3, 3, 0xFF, 0x81)))
        mem.w8(h + 8, rng.choice((0, 0x52, 0x54, 0x5A, 0x5E, 0x60, 0x62, 0x58, rng.randrange(0x5F))))
        mem.w8(h + 0x98, rng.choice((0, 0x60, 0x62, rng.randrange(0x5F))))
        desc = h + 0x50
        for k in range(8):
            mem.w16(desc + 0x10 + 2 * k, rng.choice((0, 0, rng.randrange(0x10000))))
        for k in range(4):
            mem.w16(desc + 0x24 + 8 * k, rng.choice(IDS))
            for j in (2, 4, 6):
                mem.w16(desc + 0x24 + 8 * k + j, rng.randrange(0x10000))

    def respond(self, name, args, rng):
        if name == 'Skill.v11':
            return Answer(rng.choice(SKILL_VALUES) & M32)
        if name == 'Creature.v16':
            return Answer(rng.choice((0x00C00080, 0x00C00100, 0)))
        if name == 'model_getAttachPoint':
            if rng.random() < 0.3:
                return Answer(0)
            return Answer(0, outs=tuple(f32(rng.uniform(-3000, 3000)) for _ in range(3)))
        if name == 'pool_new':
            return Answer(self.prop_block if rng.random() < 0.8 else 0)
        return Answer(0)


HANDS = (0, 1, 1, 2, 2, 3, M32, 0x80000001)


def make_rig(elf, seed):
    world = World.__new__(World)
    rig = MiniRig(elf, set(WH.EXECUTED.values()), HOLDER_STUBS, world)
    World.__init__(world, rig.emu, random.Random(seed))
    world.build(rig.addr_of)
    return rig, world


def run(elf, seed, cases, tally):
    rig, world = make_rig(elf, seed)
    mem, rng = rig.emu.mem, world.rng
    n = 0
    for case in range(cases):
        mem.w32(RC.G_LEVEL_MONSTER_LEVEL, f32(rng.choice(LEVELS)))
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        table = rng.choice((WH.VT_WEAPON1, WH.VT_WEAPONSHIELD))
        h = rng.choice(world.holders)
        world.randomise_holder(h, table)
        c = rng.choice(world.creatures)
        world.randomise_creature(c)
        roll = rng.random()
        if roll < 0.06:                                         # the helpers on their own
            which = rng.choice(('build', 'get', 'drop'))
            if which == 'build':
                kind = rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, 0x101, 0xFF))
                fn, args = WH.BUILD_ELEMENT, (h + 4, h + 0x50, kind)
            elif which == 'get':
                fn, args = WH.GET_ELEMENT, (h + 4, h + 0x50)
            else:
                fn, args = WH.DROP_PART, (h + 4, rng.choice((0, 1, 5, 0x52, 0x5F)),
                                          rng.choice((c, c, c, 0)), rng.choice((0, rng.choice(world.definitions))),
                                          rng.choice((0, 0, 0x4001, 0x3, 0x80000000)))
            key = {WH.BUILD_ELEMENT: 'creature_buildElementDamage', WH.GET_ELEMENT: 'damageDesc_getElement',
                   WH.DROP_PART: 'creature_dropHeldPartAsProp'}[fn]
        else:
            slot = rng.choice(range(1, 18))
            fn = mem.u32(table + 8 * slot + 4)
            this = (h + mem.s16(table + 8 * slot)) & M32
            hand = rng.choice(HANDS)
            extra = (rng.choice((0, 0, 0x52, 0x60, 0x62, 0x1FF, rng.randrange(0x100))),
                     rng.randrange(0x400), rng.randrange(0x400), rng.randrange(0x400))
            if slot == 8:
                extra = (rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 0x102, 0xFF)),)
            if slot == 11:
                extra = (rng.choice((c, c, c, 0)), rng.choice((0, rng.choice(world.definitions))),
                         rng.choice((0, 0, 0x4001, 3, 0x80000000)))
            args = (this, hand) + extra
            cls = WH.SLOTS[fn][0]
            key = '%s slot %d' % (cls, slot)
        n += 1
        result = rig.compare(fn, args, WH.Model, lambda m, fn=fn, args=args: m.entry(fn, *args),
                             seed * 1000003 + case, ret_kind='i' if fn in WH.RETURNS else 'n')
        tally.add(key, result, lambda: '%s%s' % (key, tuple('%x' % (a & M32) for a in args)))
    return rig, n




def main(argv):
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--seed':
            OPTIONS['seed'] = int(args[i + 1], 0)
            i += 1
        elif a == '--cases':
            OPTIONS['cases'] = int(args[i + 1], 0)
            i += 1
        elif a == '--quick':
            OPTIONS['quick'] = True
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        i += 1
    elf = find_elf(args)
    if not check_elf(elf, 'difftest_weapon_holder'):
        return 0
    C.set_fpu('ps2')
    started = time.time()
    cases = OPTIONS['cases'] // 10 if OPTIONS['quick'] else OPTIONS['cases']
    tally = Tally('holder')
    total = 0
    trace, rig = set(), None
    for k in range(2):                                          # two worlds per seed
        rig, n = run(elf, OPTIONS['seed'] + k, cases // 2, tally)
        trace |= rig.trace
        total += n
        if rig.unknown:
            print('FAIL  calls to addresses neither real nor stubbed: %s' % {hex(a): n for a, n in rig.unknown.items()})
            tally.bad.setdefault('unknown', []).append(str(rig.unknown))
    ok = tally.report()
    names = {addr: '%s_slot%d' % (cls, slot) for addr, (cls, slot, _m) in WH.SLOTS.items()}
    names.update({WH.BUILD_ELEMENT: 'creature_buildElementDamage', WH.GET_ELEMENT: 'damageDesc_getElement',
                  WH.DROP_PART: 'creature_dropHeldPartAsProp'})
    bodies = sorted(WH.BODY_END.items())
    print_coverage(coverage_lines(trace, rig.emu.mem, bodies, names), OPTIONS['verbose'])
    print('%d calls compared (seed %d), %d shared draws, %d stopped on both sides; %.0f s' % (
        total, OPTIONS['seed'], tally.draws, tally.both, time.time() - started))
    return 0 if ok and 'unknown' not in tally.bad else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
