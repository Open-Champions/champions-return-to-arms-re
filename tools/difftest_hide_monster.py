#!/usr/bin/env python3
"""difftest_hide_monster.py - tools/ref_hide_monster.py against the original hideMonster
0x144c00 and showMonster 0x144db8.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_hide_monster.py [SLUS_209.73] [--cases N] [--seed N] [-k TEXT] [-v]

The world is the one of tools/difftest_objects.py: objects built in the interpreter's memory
by the original GameObject_ctor (with real pool, handle lists, grid and name table) and the
same world in tools/ref_objects.py.  On top of that world the two handlers run whole in
tools/ee_emu.py, entered as the dispatcher enters them, (machine, params).  REAL: the
handlers, world_findObjectsByName, obj_moveOffGrid, obj_updateGridCell and the C library
under them.  STUBS: scr_getAddr and scr_getString only (they hand over the test name).
Any other call made while a handler runs is a failure.

After every operation (the handlers and the random world operations between them) the rig's
full comparison runs: every list head and node, both grids and the off-grid list, the 19
words of every live object, the pool and node allocators, the name table and the shared
seed.  On top of that, byte +0x231 of every live object of 0x248 bytes or more (the bytes are
seeded on both sides at construction), and the handler's return value.

Suites:
  mixed   a random world (moves, deletes, destroys, flag changes, off-grid moves, queries,
          constructions with and without `hide`, names shared by several objects, case
          variants, names with no object) with hideMonster / showMonster interleaved
  edges   fixed cases: hide twice, show an object that is not hidden, a non-creature, a
          creature, an object in grid B, an object outside the grid, a deleted object not
          yet flushed, a name in another case, a name that finds nothing, 40 objects of one
          name, then a box query to see that hidden objects are not returned
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_objects as DO                   # noqa: E402
from ee_emu import EmuError                     # noqa: E402
import ref_core as R                            # noqa: E402
import ref_hide_monster as H                    # noqa: E402
import ref_objects as O                         # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73')]
OPTIONS = {'cases': 200, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
M32 = 0xFFFFFFFF
BIG = 0x248                                     # smallest rig size that holds +0x231
ALLOWED = {H.SCR_GET_ADDR, H.SCR_GET_STRING, H.FIND_BY_NAME, H.MOVE_OFF_GRID, H.UPDATE_GRID_CELL}
RUNTIME = (0x3A5000, 0x3CC000)                  # the C library (as in difftest_script_items)
HIDE_NAMES = DO.NAMES + (b'nobody', b'K1', b'BOSS')


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def seeded_byte(addr):
    return (addr * 29 >> 3) & 0xFF


class HideRig(DO.Rig):
    def __init__(self, elf, seed):
        super().__init__(elf, seed)
        self.sizes = {}
        self.hidden = {}                        # model: address -> byte +0x231
        self.calls_seen = set()
        self.bad_calls = set()
        self.hide_ops = {'hide': 0, 'show': 0, 'objects': 0, 'creatures': 0, 'empty': 0}
        emu = self.emu

        def get_addr(e):
            e.mem.w32(e.r[6] & M32, e.r[5] & M32)
            return 0

        def get_string(e):
            text = self.read_cstr(e.r[5] & M32)
            e.mem.write(e.r[4] & M32, text + b'\0')
            return 0
        emu.stub(H.SCR_GET_ADDR, function=get_addr, name='scr_getAddr')
        emu.stub(H.SCR_GET_STRING, function=get_string, name='scr_getString')
        self.params = emu.alloc(16)

    # construction: remember the size and seed byte +0x231 the same way on both sides
    def m_new(self, size, pos, pkey, dkey, then, flags, stale):
        addr = super().m_new(size, pos, pkey, dkey, then, flags, stale)
        if addr:
            self.sizes[addr] = size
            if size >= BIG:
                self.hidden[addr] = seeded_byte(addr)
            else:
                self.hidden.pop(addr, None)
        return addr

    def e_new(self, size, pos, pkey, dkey, then, flags, stale):
        addr = super().e_new(size, pos, pkey, dkey, then, flags, stale)
        if addr and size >= BIG:
            self.emu.mem.w8(addr + H.OFF_HIDDEN, seeded_byte(addr))
        return addr

    # the two handlers
    def m_hide(self, name):
        objs = self.model.names.find(name, H.NAME_LIMIT)
        self.hide_ops['hide'] += 1
        self._count(objs)
        return H.hide_monster(self.model, name, self.hidden)

    def m_show(self, name):
        objs = self.model.names.find(name, H.NAME_LIMIT)
        self.hide_ops['show'] += 1
        self._count(objs)
        return H.show_monster(self.model, name, self.hidden)

    def _count(self, objs):
        self.hide_ops['objects'] += len(objs)
        self.hide_ops['creatures'] += sum(1 for o in objs if o.flags & H.FLAG_CREATURE)
        self.hide_ops['empty'] += 0 if objs else 1

    def _handler(self, addr, name):
        emu = self.emu
        emu.mem.w32(self.params, 4)
        emu.mem.w32(self.params + 4, self.cstring(name))
        emu.record_calls = True
        emu.calls = []
        try:
            value = self.ecall(addr, 0x01100000, self.params)
        finally:
            emu.record_calls = False
        for c in emu.calls:
            self.calls_seen.add(c.target)
            if c.target not in ALLOWED and not (RUNTIME[0] <= c.target < RUNTIME[1]):
                self.bad_calls.add(c.target)
        emu.calls = []
        return value

    def e_hide(self, name):
        return self._handler(H.HIDE_MONSTER, name)

    def e_show(self, name):
        return self._handler(H.SHOW_MONSTER, name)

    def check(self, full=False):
        super().check(full)
        mem = self.emu.mem
        for addr, obj in self.model.objects.items():
            if self.sizes.get(addr, 0) >= BIG:
                got, want = mem.u8(addr + H.OFF_HIDDEN), self.hidden.get(addr)
                if got != want:
                    self.bad('byte +0x231 of 0x%x: original 0x%02x, model 0x%02x' % (addr, got, want))


class HideDriver(DO.Driver):
    def new_op(self, near=None, flags=None):
        op = list(super().new_op(near, flags))
        if self.rng.random() < 0.35:
            op[1] = self.rng.choice((BIG, 0x3C8, 0x500, 0x590))
            op[6] |= 0x20
        if op[1] < BIG:
            op[6] &= ~0x20
        return tuple(op)

    def hide_op(self):
        rng = self.rng
        return (rng.choice(('hide', 'hide', 'show')), rng.choice(HIDE_NAMES))


def suite_mixed(elf, cases, seed):
    rig = HideRig(elf, '%d/hide-mixed' % seed)
    driver = HideDriver(rig, cap=220)
    rng = rig.rng
    done = 0
    try:
        for _ in range(140):
            driver.top(driver.new_op(None))
        while done < cases:
            if rng.random() < 0.4:
                driver.top(driver.hide_op())
                done += 1
            else:
                driver.top(driver.random_op())
            if len(rig.model.objects) < 60:
                driver.top(driver.new_op(None))
    except DO.Diverged:
        pass
    except (EmuError, O.ObjectError, R.HandleError, R.PoolError) as exc:
        rig.bad('stopped: %s: %s' % (type(exc).__name__, exc))
    return rig, done


def suite_edges(elf, seed):
    rig = HideRig(elf, '%d/hide-edges' % seed)
    driver = HideDriver(rig, cap=400)
    pk = {}
    for props in ([b'name=boss'], [b'name=k1'], [b'name=door1'], [b'name=alpha']):
        pk[props[0]] = rig.add_props(props)
    f = DO.f32
    near = (f(10.0), f(10.0), 0)
    outside = (f(20000.0), f(0.0), 0)
    done = 0
    try:
        creature = rig.do('new', 0x590, near, pk[b'name=boss'], 0, 'frame', 0x20, 0)
        plain = rig.do('new', 0x590, near, pk[b'name=door1'], 0, 'frame', 0, 0)
        gridb = rig.do('new', 0x590, near, pk[b'name=alpha'], 0, 'frame', 0x820, 0)
        far = rig.do('new', 0x590, outside, pk[b'name=alpha'], 0, 'r60', 0x20, 0)
        for _ in range(40):
            rig.do('new', rig.rng.choice((0x4C, 0x590)), near, pk[b'name=k1'], 0, 'frame', 0, 0)
        steps = [('hide', b'boss'), ('hide', b'boss'), ('show', b'boss'), ('show', b'boss'),
                 ('show', b'door1'), ('hide', b'door1'), ('show', b'door1'),
                 ('hide', b'ALPHA'), ('show', b'alpha'), ('hide', b'nobody'), ('show', b''),
                 ('hide', b'k1'), ('box', (f(-200.0), f(-200.0), f(-1000.0)), (f(200.0), f(200.0), f(1000.0)), 256, None),
                 ('show', b'K1'), ('box', (f(-200.0), f(-200.0), f(-1000.0)), (f(200.0), f(200.0), f(1000.0)), 256, None),
                 ('delete', plain), ('hide', b'door1'), ('show', b'door1'), ('flush',), ('hide', b'door1'),
                 ('flags', creature, 0x8020), ('show', b'boss'), ('flags', gridb, 0x20), ('show', b'alpha'),
                 ('isoff', far), ('hide', b'boss'), ('isoff', creature)]
        for op in steps:
            driver.top(op)
            done += 1
    except DO.Diverged:
        pass
    except (EmuError, O.ObjectError, R.HandleError, R.PoolError) as exc:
        rig.bad('stopped: %s: %s' % (type(exc).__name__, exc))
    return rig, done


def finish(name, rig, done, what):
    ok = rig.failures == 0 and not rig.bad_calls
    extra = '' if not rig.bad_calls else ' unexpected calls %s' % sorted('%x' % c for c in rig.bad_calls)
    st = rig.hide_ops
    report(name, ok, '%d %s, %d operations compared, %d mismatches; hide %d show %d, objects %d (creatures %d), '
           'names finding nothing %d; callees %s%s' % (
               done, what, rig.steps, rig.failures, st['hide'], st['show'], st['objects'], st['creatures'], st['empty'],
               ' '.join('%x' % c for c in sorted(rig.calls_seen)), extra))
    if OPTIONS['verbose'] or rig.failures:
        for line in rig.examples:
            print('      ' + line)


def find_elf(args):
    for candidate in list(args) + CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--cases' and argv:
            OPTIONS['cases'] = int(argv.pop(0))
        elif item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif item == '-k' and argv:
            OPTIONS['filter'] = argv.pop(0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    import hashlib
    with open(elf, 'rb') as source:
        if hashlib.sha256(source.read()).hexdigest() != ELF_SHA:
            print('SKIP  %s is not the US v2.00 executable; nothing was compared' % elf)
            return 0
    DO.OPTIONS['seed'] = OPTIONS['seed']
    random.seed(OPTIONS['seed'])
    if OPTIONS['filter'] in (None, 'mixed'):
        rig, done = suite_mixed(elf, OPTIONS['cases'], OPTIONS['seed'])
        finish('mixed', rig, done, 'handler calls')
    if OPTIONS['filter'] in (None, 'edges'):
        rig, done = suite_edges(elf, OPTIONS['seed'])
        finish('edges', rig, done, 'fixed steps')
    failed = [n for n, ok in RESULTS if not ok]
    print('%d suites, %d failed (seed %d, %d cases)' % (len(RESULTS), len(failed), OPTIONS['seed'], OPTIONS['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
