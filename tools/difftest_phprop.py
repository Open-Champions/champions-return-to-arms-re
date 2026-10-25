#!/usr/bin/env python3
"""difftest_phprop.py - compare tools/ref_phprop.py with the game's own code: the prop
chain under GutChunk_ctor (PhProp_ctor, Prop_ctorNamedLaunch, Prop_launch,
PhProp_initPhysics).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_phprop.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                      [--cases N] [-k TEXT] [-v] [--trace-first]

What is compared
    Each entry runs in tools/ee_emu.py with these bodies REAL: GutChunk_ctor 0x201958,
    PhProp_ctor 0x155a0c, Prop_ctorNamedLaunch 0x153e54, Prop_launch 0x1541a0,
    PhProp_initPhysics 0x155110, GameObject_ctor 0x14cb10, GameObject_rand 0x1509d0 and
    the C library (strcpy, sprintf).  Everything else is a recording stub answered by
    the same seeded script on both sides.  The same inputs go through ref_phprop.Model
    on a copy-on-write view; equal must be the calls with their arguments (a stack text
    buffer compared by its text), the bytes stored outside the stack, the shared seed
    0x404464 with its draw count, and the result.

Entries and scenarios
    gutChunk      GutChunk_ctor on a zero-filled 0x268 block (what pool_new hands out),
                  kinds 0-3 and other part numbers, bits 0-3, the gore word 0x44fdc0
    phprop        PhProp_ctor on zeroed or dirty blocks, every launch bit alone and in
                  mixes, with and without an item record (its word +8 with 0x20000 or
                  not), scale 0.5-3, the damping option 0x44fe08
    namedLaunch   Prop_ctorNamedLaunch with the same launch mixes and bounds of any sign
    launch        Prop_launch on dirty blocks (the +0x140 bits, +0x30 near 400)
    physics       PhProp_initPhysics on dirty blocks (+0x238, +0x150, 64-bit part masks)
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
import ref_phprop as PP                         # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
f32 = D.f32
is_stack = D.is_stack

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False, 'trace_first': False}

BODIES = {
    'GutChunk_ctor': (0x201958, 0x201A2C),
    'PhProp_ctor': (0x155A0C, 0x155BDC),
    'Prop_ctorNamedLaunch': (0x153E54, 0x154028),
    'Prop_launch': (0x1541A0, 0x154514),
    'PhProp_initPhysics': (0x155110, 0x155394),
    'PhProp_ctor2': (0x1556C0, 0x155A0C),
    'Gold_ctor2': (0x157668, 0x157754),
}
GAMEOBJECT_SPAN = (0x14CB10, 0x14CF84)
REAL = set(PP.MODELLED.values()) | {0x1509D0}

ENTRIES = {
    # key -> (address, argument kinds, result kind, method)
    'gutChunk': (0x201958, 'cvii', 'n', 'gutchunk_ctor'),
    'phprop': (0x155A0C, 'cvpppiiif', 'n', 'phprop_ctor_entry'),
    'namedLaunch': (0x153E54, 'cvpppii', 'n', 'prop_ctor_named_launch'),
    'launch': (0x1541A0, 'ci', 'n', 'prop_launch'),
    'physics': (0x155110, 'ci', 'n', 'phprop_init_physics'),
    # k: a 64-bit word in the caller's outgoing stack area, slots of 8 bytes in order
    'phprop2': (0x1556C0, 'cvippppp' + 'kkk' + 'f', 'n', 'phprop_ctor2'),
    'gold': (0x157668, 'cvi', 'n', 'gold_ctor2'),
}

LAUNCH_BITS = (1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000,
               0x8000, 0x10000)
LAUNCH_MIXES = (0xB41, 0xB41, 0x12, 0x19, 0x9, 0x11, 0x1, 0x8, 0x10, 0x81, 0x181, 0x2041, 0x6000, 0x8004, 0x10020,
                0xA00, 0x400, 0x1000, 0x1FFFF, 0)


class RealSet:
    def __contains__(self, target):
        return target in REAL or LIB_LO <= target < LIB_HI


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.argbuf = emu.alloc(0x200)
        self.blocks = [emu.alloc(0x280, align=16) for _ in range(3)]
        self.items = [emu.alloc(0x50, align=16) for _ in range(2)]
        self.names = []
        for text in (b'fx.lmp', b'gutchunks.vif', b'gutchunks.tex', b'gutchunks_yellow', b'lump_b',
                     b'a_rather_long_made_up_model_name_for_the_copy', b''):
            s = emu.alloc(0x48)
            self.mem.write(s, text + b'\0')
            self.names.append(s)
        self.gore = 0

    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name, None)
        return handler(args, view, rng) if handler is not None else D.Res()

    def on_res_find(self, args, view, rng):
        return D.Res(rng.choice((0, 0x00A10000, 0x00A10040, 0x00B20000)))

    def on_obj_getPropInt(self, args, view, rng):
        return D.Res(0)

    def on_model_getBounds(self, args, view, rng):
        def v():
            return rng.choice((0, 1, -1, 3, -7, 12, -12, 40, -40, 255, 0x7FFFFFFF, -0x80000000,
                               rng.randrange(-300, 300)))
        return D.Res(outs=[v() & M32 for _ in range(6)])

    def on_model_getMeshJoint(self, args, view, rng):
        return D.Res(rng.choice((0, 1, 5, 17, 0xFF)))

    def on_anim_getJointMatrix(self, args, view, rng):
        if rng.random() < 0.2:
            m = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]
        else:
            m = [rng.uniform(-1.2, 1.2) for _ in range(9)]
        m += [rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 80)]
        return D.Res(outs=[[f32(v) for v in m]])

    def on_resref_get(self, args, view, rng):
        return D.Res(rng.choice((0, 0x00A30000)))

    def on_sound_playOnObject(self, args, view, rng):
        return D.Res(rng.choice((0xFFFFFFFF, 3)))


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        emu.follow = RealSet()
        self.names = {}
        for name, ext in PP.EXTERNALS.items():
            self.names[ext.addr] = name
            stub = self.sprintf_stub if name == 'libc_sprintf' else self.make_stub(name, ext)
            emu.stub(ext.addr, function=stub, name=name)
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.partial, self.partial_ops = [], {}
        for start, end in list(BODIES.values()) + [GAMEOBJECT_SPAN]:
            for pc in range(start, end, 4):
                word = emu.mem.u32(pc)
                if word >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = word >> 26
                    emu.hook(pc, self.partial_hook(pc, (word >> 21) & 31, ee_emu.sx16(word)))
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def stored_bytes(self, lo, hi):
        out, pending = set(), list(self.partial)
        for pc, addr, size, _value in self.emu.writes:
            op = self.partial_ops.get(pc)
            if op is not None:
                _ppc, ea = pending.pop(0)
                if op == 0x2C:
                    first, last = ea & ~7, ea
                elif op == 0x2D:
                    first, last = ea, ea | 7
                elif op == 0x2A:
                    first, last = ea & ~3, ea
                else:
                    first, last = ea, ea | 3
            else:
                first, last = addr, addr + size - 1
            if not lo <= first < hi and not is_stack(first):
                out.update(range(first, last + 1))
        return out

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for index, kind in enumerate(ext.ints):
            reg = emu.r[4 + index]
            if kind == 'q':
                canon.append(reg & M64)
            elif kind == 'v':
                canon.append(tuple(mem.u32((reg & M32) + 4 * j) for j in range(3)))
            elif kind == 'S':
                ptr = reg & M32
                if is_stack(ptr):
                    text = bytearray()
                    while mem.u8(ptr + len(text)):
                        text.append(mem.u8(ptr + len(text)))
                    canon.append(('buf', bytes(text)))
                else:
                    canon.append(ptr)
            elif kind == 'w':
                outs.append(reg & M32)
            elif kind == 'M':
                outs.append(('M', reg & M32))
            else:
                canon.append(reg & M32)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            canon, outs = self.decode(ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, self.eview, self.script_rng)
            given = list(res.outs)
            for ptr in outs:
                if isinstance(ptr, tuple):              # a 3x4 matrix
                    words = given.pop(0) if given else [0] * 12
                    for k, word in enumerate(words):
                        emu.mem.w32(ptr[1] + 4 * k, word)
                else:
                    emu.mem.w32(ptr, given.pop(0) if given else 0)
            return res.ret
        return stub

    def sprintf_stub(self, emu):
        """libc_sprintf(buffer, format, value): recorded as (format, value); the buffer gets
        the format with its one %d rendered, as the library would write it."""
        buf, fmt, value = emu.r[4] & M32, emu.r[5] & M32, emu.r[6] & M32
        self.calls.append(('libc_sprintf', (fmt, value)))
        text = bytearray()
        while emu.mem.u8(fmt + len(text)):
            text.append(emu.mem.u8(fmt + len(text)))
        emu.mem.write(buf, PP.render(bytes(text), value) + b'\0')
        return 0

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                ext = PP.EXTERNALS[name]
                if 'M' in ext.ints:
                    return list(res.outs[0]) if res.outs else [0] * 12
                if 'w' in ext.ints:
                    n = ext.ints.count('w')
                    given = list(res.outs) + [0] * n
                    return tuple(given[:n])
                if ext.ret == 'n':
                    return None
                return res.ret & M32
            return answer

    def compare(self, key, args, call_seed):
        addr, kinds, ret_kind, method = ENTRIES[key]
        emu, mem = self.emu, self.emu.mem
        seed_before = mem.u32(RC.G_RAND_SEED)
        mview = D.ModelView(mem)
        model = PP.Model(mview, Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed)))
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None, 'draws': 0,
               'model_calls': model.calls, 'emu_calls': None}
        model_error = None
        try:
            mret = getattr(model, method)(*args)
        except EmuError as exc:
            model_error, mret = exc, None
        self.calls, self.touched, self.partial = [], set(), []
        out['emu_calls'] = self.calls
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x800
        regs, scratch, nfloat, stack = [], self.world.argbuf, 0, []
        for value, kind in zip(args, kinds):
            if kind == 'k':
                stack.append(value)
                continue
            if kind == 'v':
                for j in range(3):
                    mem.w32(scratch + 4 * j, value[j])
                regs.append(scratch)
                scratch += 0x10
            elif kind == 'f':
                emu.f[12 + nfloat] = value & M32
                nfloat += 1
            else:
                regs.append(ee_emu.s32(value & M32))
        for k, value in enumerate(stack):
            mem.w64((emu.r[29] & M32) + 8 * k, value & M64)
        emu_error = None
        try:
            eret = emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            emu_error, eret = exc, None
        self.pcs.update(emu.trace)
        for call in emu.calls:
            if call.target not in REAL and call.target not in self.names and not LIB_LO <= call.target < LIB_HI:
                self.unknown[call.target] = self.unknown.get(call.target, 0) + 1
        if model_error or emu_error:
            if (model_error is None) != (emu_error is None):
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = self.world.argbuf, self.world.argbuf + 0x200
        stored = self.stored_bytes(lo, hi)
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            out['writes'] = 'only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8],
                sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]])
        expect = seed_before
        for _ in range(model.draws):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == expect:
            out['seed'] = 'model draws %d original %08x model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), mview.load(RC.G_RAND_SEED, 4))
        out['draws'] = model.draws
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            out['result'] = 'result %08x / %08x' % (eret & M32, (mret or 0) & M32)
        return out


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------
def _pos(rng):
    return tuple(f32(rng.uniform(-4000, 4000)) for _ in range(3))


def _fill(mem, addr, size, rng, zero):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0 if zero else rng.getrandbits(32))


def _launch(rng):
    r = rng.random()
    if r < 0.35:
        return rng.choice(LAUNCH_MIXES)
    if r < 0.7:
        return rng.choice(LAUNCH_BITS)
    return rng.getrandbits(17)


def _dirty(rig, rng, obj, zero=False):
    """A block as a caller might leave it: zero-filled (pool_new) or with every field the
    chain reads set: the flags, the +0x140 bits, the item byte +0x238, the record word
    +0x150, the part mask, the speeds, the scale, the own generator."""
    mem = rig.emu.mem
    _fill(mem, obj, 0x280, rng, zero)
    if zero:
        return
    mem.w32(obj + 0xC, rng.choice((0, 0x800, 0x4000, 0x100800, rng.getrandbits(32))))
    mem.w16(obj + 0x140, rng.choice((0, 1, 2, 0x3F, rng.getrandbits(16))))
    mem.w8(obj + 0x238, rng.choice((0, 0, 1, 0x80)))
    mem.w64(obj + 0x150, rng.choice((0, 0x20000, 0x20000 | rng.getrandbits(40), rng.getrandbits(64))))
    mem.w64(obj + 0xE8, rng.choice((0, 1, 2, 0x80000000, 1 << 63, 0xFFFFFFFFFFFFFFFF, rng.getrandbits(64),
                                     rng.getrandbits(20))))
    mem.wf32(obj + 0x30, rng.choice((0.0, 130.0, 399.0, 400.0, 401.0, 480.0, -20.0)))
    mem.wf32(obj + 0xFC, rng.uniform(-300, 300))
    mem.wf32(obj + 0x100, rng.uniform(-300, 300))
    mem.wf32(obj + 0x240, rng.choice((0.5, 1.0, 1.0, 2.5, 3.0)))
    pos = _pos(rng)
    for j in range(3):
        mem.w32(obj + 0x10 + 4 * j, pos[j])


def generate(rig, key, rng):
    w, mem = rig.world, rig.emu.mem
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(PP.G_PROP_OPTIONS, rng.choice((0, 0, 0x100, 0x1FF, rng.getrandbits(32))))
    mem.w32(PP.R3.G_GORE, rng.choice((0, 1, 2, 3, 0xFFFFFFFF)))
    obj = rng.choice(w.blocks)
    if key == 'gutChunk':
        _dirty(rig, rng, obj, zero=True)
        kind = rng.choice((0, 1, 2, 3, 2, 7, 0x80000000, 0xFFFFFFFF))
        return (obj, _pos(rng), kind, rng.choice((0, 1, 2, 3, 0xFFFFFFFE)))
    zero = rng.random() < 0.4
    _dirty(rig, rng, obj, zero)
    names = lambda: rng.choice(w.names)               # noqa: E731
    if key == 'phprop':
        item = 0
        if rng.random() < 0.45:
            item = rng.choice(w.items)
            _fill(mem, item, 0x50, rng, False)
            mem.w64(item + 8, rng.choice((0, 0x20000, rng.getrandbits(64))))
        mask = rng.choice((0, 1, 2, 3, 0x80000000, 0x40000000, rng.getrandbits(32)))
        scale = f32(rng.choice((0.5, 1.0, 1.0, 2.0, 3.0)))
        return (obj, _pos(rng), names(), names(), names(), mask, _launch(rng), item, scale)
    if key == 'phprop2':
        item = 0
        if rng.random() < 0.3:
            item = rng.choice(w.items)
            _fill(mem, item, 0x50, rng, False)
            mem.w64(item + 8, rng.choice((0, 0x20000, rng.getrandbits(64))))
        bits = rng.choice((0, 1, 0x80, 0x400, 0x10000, 1 << 40, 0xFE000000000000, 1 << 63, rng.getrandbits(64)))
        launch = rng.choice((0x107, 0x107, 0x107)) if rng.random() < 0.5 else _launch(rng)
        scale = f32(rng.choice((0.5, 1.0, 1.0, 1.0, 2.0)))
        facing = rng.choice((0, 0x4000, 0xC000, 0x8000, 0xFFFF, rng.randrange(0x10000), 0xFFFF8000))
        return (obj, _pos(rng), facing, 0x00A40000, rng.choice(w.blocks) + 0x114, names(), names(), names(),
                bits, launch, item, scale)
    if key == 'gold':
        return (obj, _pos(rng), rng.choice((0, 1, 7, 25, 250, 0x7FFFFFFF, 0xFFFFFFFF)))
    if key == 'namedLaunch':
        mask = rng.choice((0, 1, 0x80000000, rng.getrandbits(32)))
        return (obj, _pos(rng), names(), names(), names(), mask, _launch(rng))
    return (obj, _launch(rng))


def main(argv):
    args, elf = list(argv), None
    while args:
        item = args.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif item == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif item == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = item
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_phprop: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_phprop: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    RC.C.set_fpu('ps2')
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    rig = Rig(elf)
    coverage = Coverage(rig.emu.mem)
    rng = random.Random(OPTIONS['seed'])
    counts, total = {}, 0
    for key in ENTRIES:
        if OPTIONS['filter'] and OPTIONS['filter'] not in key:
            continue
        bad = {'fault': [], 'calls': [], 'writes': [], 'seed': [], 'result': []}
        draws = 0
        for n in range(cases):
            call_seed = OPTIONS['seed'] * 1000003 + total
            case = generate(rig, key, rng)
            result = rig.compare(key, case, call_seed)
            total += 1
            draws += result['draws']
            failed = False
            for prop in bad:
                if result[prop]:
                    failed = True
                    bad[prop].append('case %d %s: %s' % (n, key, result[prop]))
            if failed and OPTIONS['trace_first']:
                print('first mismatch: %s case %d %s' % (key, n, case))
                for prop in bad:
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls']:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in result['emu_calls'] or ():
                    print('    ' + DC.fmt_call(call))
                return 1
        counts[key] = (cases, sum(len(v) for v in bad.values()), draws)
        for prop, examples in bad.items():
            DC.report('%s %s' % (key, prop), len(examples), cases, prop, examples)
    if rig.unknown:
        DC.report('unknown calls', len(rig.unknown), total, 'calls to neither real nor stubbed addresses',
                  ['%x x%d' % kv for kv in sorted(rig.unknown.items())])
    coverage.pcs = rig.pcs
    print()
    print('cases per entry / with any mismatch / shared draws')
    for key, (n, bad_n, draws) in counts.items():
        print('  %-14s %6d / %d / %d' % (key, n, bad_n, draws))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage.numbers(part)
        print('  %-22s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage.missing(part)))
    print('%d cases in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
