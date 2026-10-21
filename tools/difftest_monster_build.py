#!/usr/bin/env python3
"""difftest_monster_build.py - tools/ref_monster_build.py against the original functions.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_monster_build.py [SLUS_209.73] [--cases N] [--seed N] [-v]

Suites (the original runs in tools/ee_emu.py):

  arena      arena_spawnMonster 0x3065fc, both forms (a class name from the 30-entry table,
             or a0 = 0 with an existing creature).  REAL: the function, libc_strcmp,
             math_cos16, math_sin16.  STUBS: world_findFreeSpot (a seeded run of misses and
             a hit, or misses only), world_createObject, Creature_scaleStats,
             Creature_clearStatus, pool_new, creature_addSpell, and the two virtual calls
             (through a table whose entries carry a non-zero this-adjustment).
  generator  ScriptGenerator_spawn 0x265fc4 with world_createObject stubbed and the
             objects' real class tables (Skeleton, Orc, Creature, ScriptGenerator), so the
             RTTI compare runs for real; vtable slot 27 is recorded.
  intern     the name half of generateMonster 0x1473d4: entered through the handler with
             world_findObjectsByName stubbed to find nothing
  factory    world_objectFactory 0x159c94 for the 30 arena class names and case variants:
             pool_new answers, every other callee is a recording stub; the size asked of
             pool_new and the first call after it (the constructor) must be the rows of
             ref_monster_build.FACTORY_ARENA

Compared: the call-outs in order with their arguments (vectors by content, floats as
patterns), the globals the function writes, the object and spell bytes, the shared seed.
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_monster_build as B                   # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73'),
              os.path.expanduser('~/champions-re/SLUS_209.73')]
OPTIONS = {'cases': 200, 'seed': 20973, 'verbose': False}
RESULTS = []
M32 = 0xFFFFFFFF

ARENA_SPAWN, GEN_SPAWN, GENERATE, FACTORY = 0x3065FC, 0x265FC4, 0x1473D4, 0x159C94
FIND_SPOT, CREATE, SCALE, CLEAR_STATUS = 0x14ACF8, 0x14F6C8, 0x1185D8, 0x1188F8
POOL_NEW, ADD_SPELL = 0x14FDB8, 0x11A838
FIND_BY_NAME = 0x14BF58
SCR_GET_ADDR, SCR_GET_STRING = 0x1414A8, 0x141650
VT = {'Skeleton': 0x5175F8, 'Orc': 0x50FFD0, 'Creature': 0x50CC58, 'ScriptGenerator': 0x514E60}
RTTI = {'Skeleton': b'8Skeleton', 'Orc': b'3Orc', 'Creature': b'8Creature', 'ScriptGenerator': b'15ScriptGenerator'}
FAKE_FN = 0x00F00000           # unmapped addresses the fake class table points at (hooked)


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def _first(bad):
    if not bad:
        return ''
    if OPTIONS['verbose']:
        return '\n    ' + '\n    '.join('%s: %s' % b for b in bad[:8])
    return '; first: case %s: %s' % bad[0]


class Mem:
    """The reference's view: the emulator memory before the original runs (copied)."""

    def __init__(self, emu):
        self.emu = emu
        self.over = {}

    def load(self, addr, size):
        v = 0
        for k in range(size):
            a = (addr + k) & M32
            b = self.over[a] if a in self.over else (self.emu.mem.u8(a) if self.emu.mem.is_mapped(a) else 0)
            v |= b << (8 * k)
        return v

    def store(self, addr, size, value):
        for k in range(size):
            self.over[(addr + k) & M32] = (value >> (8 * k)) & 0xFF


def snapshot(emu, ranges):
    return {a: emu.mem.read(a, n) for a, n in ranges}


def apply_ref(base, mem, ranges):
    out = {}
    for a, n in ranges:
        data = bytearray(base[a])
        for k in range(n):
            if a + k in mem.over:
                data[k] = mem.over[a + k]
        out[a] = bytes(data)
    return out


# ---- arena -----------------------------------------------------------------------------------------
def arena_case(elf, rng, names):
    emu = EE(elf)
    log_e = []
    wave = rng.choice([0, 1, 2, 3, 5, 14, 15, 16, 29, 30, 44, 45, -1, -4, 0x7FFF])
    count = rng.choice([5, 5, 5, 1, 3, 7, -2])
    emu.mem.w16(B.G_WAVE, wave)
    emu.mem.w16(B.G_RECIPE_COUNT, count)
    emu.mem.w16(B.G_RING_ANGLE, rng.getrandbits(16))
    emu.mem.w16(B.G_RING_STEP, rng.choice([0, 0x3333, 0x5555, 0xFFFF, rng.getrandbits(16)]))
    centre = emu.alloc(16)
    for k in range(3):
        emu.mem.wf32(centre + 4 * k, rng.uniform(-3000, 3000))
    emu.mem.w32(B.G_RING_CENTRE, centre)
    emu.mem.w32(B.G_RAND_SEED, rng.getrandbits(32))
    misses = rng.choice([0, 0, 1, 2, 5, 16, 17, 30])
    spots = [tuple(rng.getrandbits(32) for _ in range(3)) for _ in range(40)]
    by_class = rng.random() < 0.7
    name = rng.choice(names) if by_class else None
    delta = rng.choice([0, 0, 0x10])
    vtable = emu.alloc(0x200)
    for slot in (B.VSLOT_HOME_RANGE, B.VSLOT_AI_STATE):
        emu.mem.w16(vtable + 8 * slot, delta)
        emu.mem.w32(vtable + 8 * slot + 4, FAKE_FN + 8 * slot)
    obj = emu.alloc(0x400)
    for k in range(0, 0x400, 4):
        emu.mem.w32(obj + k, rng.getrandbits(32))
    emu.mem.w32(obj + 0x48, vtable)
    pool = rng.choice([0, emu.alloc(0x20)])
    if pool:
        for k in range(0, 0x18, 4):
            emu.mem.w32(pool + k, 0xA5A5A5A5)
    name_buf = 0
    if name is not None:
        name_buf = emu.alloc(len(name) + 1)
        emu.mem.write(name_buf, name + b'\0')
    ref = Mem(emu)
    ranges = [(B.G_RING_ANGLE, 2), (B.G_RAND_SEED, 4), (obj, 0x400)] + ([(pool, 0x18)] if pool else [])
    before = snapshot(emu, ranges)
    calls = {'n': 0}

    def find_spot(e):
        out, point, rang, radius, okp, anyh = (e.r[k] & M32 for k in range(4, 10))
        p = tuple(e.mem.u32(point + 4 * k) for k in range(3))
        log_e.append(('world_findFreeSpot', p, rang, radius, anyh))
        i = calls['n']
        calls['n'] += 1
        for k in range(3):
            e.mem.w32(out + 4 * k, spots[i][k])
        e.mem.w8(okp, 0 if i < misses else 1)
        return 0

    def create(e):
        n, pos, ang, props = (e.r[k] & M32 for k in range(4, 8))
        log_e.append(('world_createObject', e.mem.cstr(n).encode('latin-1'), tuple(e.mem.u32(pos + 4 * k) for k in range(3)),
                      ang & 0xFFFF, props))
        return obj

    def scale(e):
        log_e.append(('Creature_scaleStats', e.r[4] & M32) + tuple(e.f[12:17]))
        return 0

    emu.stub(FIND_SPOT, function=find_spot)
    emu.stub(CREATE, function=create)
    emu.stub(SCALE, function=scale)
    emu.stub(CLEAR_STATUS, function=lambda e: log_e.append(('Creature_clearStatus', e.r[4] & M32)) or 0)
    emu.stub(POOL_NEW, function=lambda e: log_e.append(('pool_new', e.r[4] & M32)) or pool)
    emu.stub(ADD_SPELL, function=lambda e: log_e.append(('creature_addSpell', e.r[4] & M32, e.r[5] & M32)) or 0)
    for slot in (B.VSLOT_HOME_RANGE, B.VSLOT_AI_STATE):
        emu.stub(FAKE_FN + 8 * slot, function=lambda e, s=slot: log_e.append(
            ('virtual', s, (e.r[4] - delta) & M32, e.r[5] & M32)) or 0)

    # reference
    host_calls = {'n': 0}
    host = B.Host()

    def h_find(point, rang, radius, anyh):
        i = host_calls['n']
        host_calls['n'] += 1
        return spots[i], (0 if i < misses else 1)
    host.answers = {'world_findFreeSpot': h_find, 'world_createObject': lambda *a: obj,
                    'pool_new': lambda *a: pool}
    ref_fault = emu_fault = None
    try:
        B.arena_spawn_monster(ref, host, name, obj, names)
    except B.Fault as exc:
        ref_fault = exc
    try:
        emu.reset_log()
        emu.call(ARENA_SPAWN, name_buf, obj if name is None else rng.getrandbits(32))
    except EmuError as exc:
        emu_fault = exc
    log_r = []
    for call_name, args in host.log:
        if call_name == 'world_findFreeSpot':
            log_r.append((call_name, tuple(args[0]), args[1], args[2], args[3]))
        elif call_name == 'world_createObject':
            log_r.append((call_name, args[0], tuple(args[1]), args[2] & 0xFFFF, args[3]))
        elif call_name == 'Creature_scaleStats':
            log_r.append((call_name,) + tuple(args))
        else:
            log_r.append((call_name,) + tuple(a & M32 for a in args))
    problems = []
    if (ref_fault is None) != (emu_fault is None):
        problems.append('fault on one side only: ref %r emu %r' % (ref_fault, emu_fault))
    elif ref_fault is None:
        if log_e != log_r:
            problems.append('calls emu %r ref %r' % (log_e[:3], log_r[:3]))
        got = snapshot(emu, ranges)
        want = apply_ref(before, ref, ranges)
        for a, _n in ranges:
            if got[a] != want[a]:
                k = next(i for i in range(len(got[a])) if got[a][i] != want[a][i])
                problems.append('bytes at 0x%x+0x%x: emu %02x ref %02x' % (a, k, got[a][k], want[a][k]))
    kind = ('class' if name is not None else 'creature', 'hit' if misses < 17 else 'gave up', bool(pool))
    return problems, kind, ref_fault is not None


def suite_arena(elf, names):
    rng = random.Random(OPTIONS['seed'])
    bad, seen, faults = [], {}, 0
    for case in range(OPTIONS['cases']):
        problems, kind, fault = arena_case(elf, rng, names)
        seen[kind] = seen.get(kind, 0) + 1
        faults += fault
        if problems:
            bad.append((case, '; '.join(problems)))
    cover = ', '.join('%s/%s/%s %d' % (k[0], k[1], 'spell' if k[2] else 'no spell', v) for k, v in sorted(seen.items()))
    report('arena', not bad, '%d cases (%d faulted on both sides), %d mismatches [%s]%s'
           % (OPTIONS['cases'], faults, len(bad), cover, _first(bad)))


# ---- generator ----------------------------------------------------------------------------------------
def suite_generator(elf):
    rng = random.Random(OPTIONS['seed'] + 1)
    bad, seen = [], {}
    for case in range(max(OPTIONS['cases'] // 2, 40)):
        emu = EE(elf)
        gen = emu.alloc(0x60)
        for k in range(0, 0x60, 4):
            emu.mem.w32(gen + k, rng.getrandbits(32))
        cls = rng.choice(list(VT) + [None])
        obj = 0
        if cls is not None:
            obj = emu.alloc(0x480)
            for k in range(0, 0x480, 4):
                emu.mem.w32(obj + k, rng.getrandbits(32))
            emu.mem.w32(obj + 0x48, VT[cls])
        type_name = rng.choice([b'Skeleton', b'WatSkel', b'Orc', b'x'])
        tn = emu.alloc(16)
        emu.mem.write(tn, type_name + b'\0')
        log_e = []
        set_state = emu.mem.u32(VT['Skeleton'] + 8 * B.VSLOT_AI_STATE + 4)

        def create(e):
            n, pos, ang, props = (e.r[k] & M32 for k in range(4, 8))
            log_e.append(('world_createObject', e.mem.cstr(n).encode('latin-1'), tuple(e.mem.u32(pos + 4 * k) for k in range(3)),
                          ang & 0xFFFF, props))
            return obj
        emu.stub(CREATE, function=create)
        delta = emu.mem.s16(VT['Skeleton'] + 8 * B.VSLOT_AI_STATE)
        emu.stub(set_state, function=lambda e: log_e.append(('virtual', B.VSLOT_AI_STATE, (e.r[4] - delta) & M32,
                                                               e.r[5] & M32)) or 0)
        ref = Mem(emu)
        ranges = [(obj, 0x480)] if obj else []
        before = snapshot(emu, ranges)
        host = B.Host({'world_createObject': lambda *a: obj})
        B.script_generator_spawn(ref, host, gen, tn, type_name,
                                 lambda o: RTTI[cls] if cls else None)
        try:
            emu.call(GEN_SPAWN, gen, tn)
        except EmuError as exc:
            bad.append((case, 'emulator stopped: %s' % exc))
            continue
        log_r = []
        for name, args in host.log:
            if name == 'world_createObject':
                log_r.append((name, args[0], tuple(args[1]), args[2] & 0xFFFF, args[3]))
            else:
                log_r.append((name,) + tuple(a & M32 for a in args))
        problems = []
        if log_e != log_r:
            problems.append('calls emu %r ref %r' % (log_e, log_r))
        got, want = snapshot(emu, ranges), apply_ref(before, ref, ranges)
        if got != want:
            problems.append('object bytes differ')
        key = (cls or 'none', any(c[0] == 'virtual' for c in log_e))
        seen[key] = seen.get(key, 0) + 1
        if problems:
            bad.append((case, '%s: %s' % (cls, '; '.join(problems))))
    cover = ', '.join('%s%s %d' % (k[0], ' +state 0x17' if k[1] else '', v) for k, v in sorted(seen.items()))
    report('generator', not bad, '%d mismatches [%s]%s' % (len(bad), cover, _first(bad)))


# ---- intern -----------------------------------------------------------------------------------------------
def suite_intern(elf):
    rng = random.Random(OPTIONS['seed'] + 2)
    bad, cases = [], 0
    pool = [b'Skeleton', b'orc', b'Orc', b'mummyKing', b'a' * 23, b'Gnome2', b'']
    for case in range(max(OPTIONS['cases'] // 4, 30)):
        emu = EE(elf)
        count = rng.choice([0, 1, 3, 6])
        names = [rng.choice(pool) for _ in range(count)]
        for k, n in enumerate(names):
            emu.mem.write(B.G_GEN_NAMES + 24 * k, n + b'\0')
        emu.mem.w8(B.G_GEN_COUNT, count)
        ref = Mem(emu)
        before = snapshot(emu, [(B.G_GEN_COUNT, 1), (B.G_GEN_NAMES, 24 * 8)])
        cls = rng.choice(pool)
        B.intern_class_name(ref, cls)
        strings = {0x7000: b'gen', 0x7001: cls}

        def get_addr(e):
            e.mem.w32(e.r[6] & M32, e.r[5] & M32)
            return 0

        def get_string(e):
            e.mem.write(e.r[4] & M32, strings[e.r[5] & M32] + b'\0')
            return 0
        emu.stub(SCR_GET_ADDR, function=get_addr)
        emu.stub(SCR_GET_STRING, function=get_string)
        emu.stub(FIND_BY_NAME, ret=0)
        params = emu.alloc(12)
        emu.mem.w32(params, 8)
        emu.mem.w32(params + 4, 0x7000)
        emu.mem.w32(params + 8, 0x7001)
        try:
            emu.call(GENERATE, 0x01100000, params)
        except EmuError as exc:
            bad.append((case, 'emulator stopped: %s' % exc))
            continue
        ranges = [(B.G_GEN_COUNT, 1), (B.G_GEN_NAMES, 24 * 8)]
        cases += 1
        if snapshot(emu, ranges) != apply_ref(before, ref, ranges):
            bad.append((case, 'table differs for %r over %r' % (cls, names)))
    report('intern', not bad, '%d cases, %d mismatches%s' % (cases, len(bad), _first(bad)))


# ---- factory ----------------------------------------------------------------------------------------------------
def suite_factory(elf, names):
    bad, rows = [], 0
    variants = []
    for n in names:
        variants += [n, n.upper(), n.lower()]
    for name in variants:
        emu = EE(elf)
        block = emu.alloc(0x600)
        asked = []

        def pool(e):
            asked.append(e.r[4] & M32)
            return block
        emu.stub(POOL_NEW, function=pool)
        n = emu.alloc(len(name) + 1)
        emu.mem.write(n, name + b'\0')
        pos = emu.alloc(16)
        props = emu.alloc(16)
        emu.reset_log()
        # stop at the first call after pool_new: that is the constructor
        state = {'after': False, 'target': None}
        original_enter = emu._enter_call

        def enter(target, _orig=original_enter, _st=state, _emu=emu):
            if _st['after'] and _st['target'] is None:
                _st['target'] = target
                _emu.stub(target, ret=block)
            if target == POOL_NEW:
                _st['after'] = True
            return _orig(target)
        emu._enter_call = enter
        try:
            result = emu.call(FACTORY, n, pos, 0, props, max_steps=2000000)
        except EmuError as exc:
            bad.append((name, 'emulator stopped: %s' % exc))
            continue
        got = (asked[0] if asked else None, state['target'])
        want = B.factory_row(name)
        rows += 1
        if got != want:
            bad.append((name.decode('latin-1'), 'emu size/ctor %r ref %r' % (
                tuple(hex(x) if x else x for x in got), tuple(hex(x) if x else x for x in want))))
        del result
    report('factory', not bad, '%d names (30 table names, upper and lower case), %d mismatches%s'
           % (rows, len(bad), _first(bad)))


def find_elf(argv):
    for a in argv:
        if not a.startswith('-') and os.path.exists(a):
            return a
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def main(argv):
    args = list(argv)
    if '--cases' in args:
        OPTIONS['cases'] = int(args[args.index('--cases') + 1])
    if '--seed' in args:
        OPTIONS['seed'] = int(args[args.index('--seed') + 1])
    OPTIONS['verbose'] = '-v' in args
    elf = find_elf([a for i, a in enumerate(args) if i == 0 or args[i - 1] not in ('--cases', '--seed')])
    if elf is None:
        print('SLUS_209.73 not found; nothing compared')
        return 0
    import hashlib
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != ELF_SHA:
        print('this is not SLUS_209.73 v2.00; nothing compared')
        return 0
    probe = EE(elf)
    names = [probe.mem.cstr(probe.mem.u32(B.G_ARENA_CLASSES + 4 * k)) for k in range(B.ARENA_CLASS_COUNT)]
    names = [n if isinstance(n, bytes) else n.encode('latin-1') for n in names]
    suite_arena(elf, names)
    suite_generator(elf)
    suite_intern(elf)
    suite_factory(elf, names)
    failed = [n for n, ok in RESULTS if not ok]
    print('%d suites, %d failed (seed %d, %d cases)' % (len(RESULTS), len(failed), OPTIONS['seed'], OPTIONS['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
