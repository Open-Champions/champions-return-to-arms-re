#!/usr/bin/env python3
"""difftest_item_drops.py - tools/ref_item_drops.py against the original functions.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_item_drops.py [SLUS_209.73] [--cases N] [--seed N] [-k TEXT] [--full]

The original machine code runs in tools/ee_emu.py.  Suites:

  ctor     ItemProp_ctor2 0x1590ec called directly on a random 0x190-byte block, with random
           item records of the user's own tables, positions, seeds, launch flags (0, which
           every caller passes, and mixes) and the option bit 0x44fe08 & 0x100.  REAL:
           ItemProp_ctor2, Prop_ctorNamedLaunch, Prop_launch, GameObject_ctor,
           GameObject_rand, item_getResourceIndex, mat34_setPosRotZ, the C library.  STUBS
           (recorded, same seeded answers): handle_link, obj_getPropInt, res_find,
           model_getBounds, obj_updateGridCell, obj_runEveryFrame, obj_stopRunning.
  random   givePlayerRandom 0x145f18 entered as the dispatcher enters it.  REAL: the handler,
           level_monsterLevelTimesDifficulty, item_generateWithAffixes and everything it
           calls, item_parseDescriptor, inventory_giveItem, player_itemWeight,
           item_getWeight, the passive and rank lookups, player_recalcLoad, and the whole
           ItemProp_ctor2 chain above.  STUBS: those of tools/difftest_script_items.py
           (pool_new answering a fresh block or 0) minus ItemProp_ctor2, plus the chain's.
           Without --full the C library string routines are replaced by Python (as the
           -fast suites of tools/difftest_items.py do); the handler's own strstr is then one
           of them.

Every case compares the result, the stub calls in order (vectors and item records by
content), the four player records, every ground block, every byte written outside them and
the stack, and the shared seed 0x404464; a call to an address outside the listed set fails.
Item bytes that the item code never defines (+0x06, +0x07, +0x22, +0x23, +0x44..+0x47, the
values of empty modifier slots) are masked.
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_items as I                           # noqa: E402
import ref_natives as N                         # noqa: E402
import ref_script_items as R                    # noqa: E402
import ref_item_drops as D                      # noqa: E402
import difftest_script_items as DS              # noqa: E402
import difftest_items as DI                     # noqa: E402

M32 = 0xFFFFFFFF
OPTIONS = {'cases': 200, 'seed': 20973, 'filter': None, 'full': False}
RESULTS = []
CHAIN = {D.ITEMPROP_CTOR2, D.PROP_CTOR_NAMED_LAUNCH, D.PROP_LAUNCH, D.GAMEOBJECT_CTOR, D.GAMEOBJECT_RAND,
         D.RESOURCE_INDEX, D.MAT34_SET_POS_ROT_Z}
EXT_ADDR = {addr: name for name, (addr, _n) in D.EXTERNALS.items()}
BLOCK_BASE = 0x01300000
HANDLER_FRAME = 0xB0            # givePlayerRandom's frame; its record is at the new sp + 0


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def mask_item(data):
    out = bytearray(data)
    for k in (6, 7, 0x22, 0x23, 0x44, 0x45, 0x46, 0x47):
        out[k] = 0
    for slot in range(4):
        if struct.unpack_from('<h', out, 0x24 + 8 * slot)[0] == -1:
            out[0x26 + 8 * slot:0x2C + 8 * slot] = bytes(6)
    return bytes(out)


def mask_block(data):
    return bytes(data[:0x148]) + mask_item(data[0x148:0x190]) + bytes(data[0x190:])


class ChainAnswers:
    """Seeded answers to the chain's leaf call-outs and pool_new, the same on both sides."""

    def __init__(self, seed, pool_zero=0.15):
        rng = self.rng = random.Random(seed)
        self.res = [rng.choice((0, 0x00A10000, 0x00A10040)) for _ in range(64)]
        self.bounds = [[rng.choice((0, 1, -1, 3, -7, 12, -12, 40, -40, 255, rng.randrange(-300, 300)))
                        for _ in range(6)] for _ in range(16)]
        self.pool = [0 if rng.random() < pool_zero else BLOCK_BASE + 0x200 * k for k in range(32)]
        self.count = {}

    def next(self, name):
        k = self.count.get(name, 0)
        self.count[name] = k + 1
        if name == 'res_find':
            return self.res[k % 64]
        if name == 'model_getBounds':
            return [v & M32 for v in self.bounds[k % 16]]
        if name == 'pool_new':
            return self.pool[k % 32]
        if name in ('vars_get',):
            return 0
        if name == 'text_lookup':
            return 0x01310000
        if name.startswith('skill_'):
            return I.f_bits(0.5)
        return 0


class Host(R.Host):
    def __init__(self, answers, mem):
        R.Host.__init__(self)
        self.answers, self.mem = answers, mem

    def call(self, name, *args):
        if name == 'model_getBounds':
            self.log.append((name, (args[0] & M32, args[1])))
        else:
            self.log.append((name, tuple(a & M32 for a in args)))
        return self.answers.next(name)


def install(emu, answers, log, extra_stubs=()):
    """The chain's externals plus extra (address, name, argument count) stubs."""
    def make(name, count):
        def run(e):
            if name == 'model_getBounds':
                log.append((name, (e.r[4] & M32, e.r[5] & ((1 << 64) - 1))))
                for k, v in enumerate(answers.next(name)):
                    e.mem.w32(e.r[6 + k] & M32, v)
                return 0
            args = tuple(e.r[4 + k] & M32 for k in range(count))
            log.append((name, args))
            value = answers.next(name)
            if name.startswith('skill_'):
                e.f[0] = value
                return None
            return value
        return run
    for name, (addr, count) in D.EXTERNALS.items():
        emu.stub(addr, function=make(name, count), name=name)
    for addr, name, count in extra_stubs:
        emu.stub(addr, function=make(name, count), name=name)


class Shim:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem


def fast_library(emu):
    DI.Original._library_hooks(Shim(emu))


def bad_calls(emu, real):
    out = set()
    for c in emu.calls:
        t = c.target
        if t in real or t in emu.stub_names or DS.RUNTIME[0] <= t < DS.RUNTIME[1]:
            continue
        out.add(t)
    return out


def item_record(tables, rng, stale=None):
    d = rng.choice(tables.defs + tables.presets)
    item = I.Item(d)
    item.count = rng.choice([1, 1, 2, 7])
    item.flags = d.flags
    if rng.random() < 0.4:
        item.flags |= rng.randrange(32) << 11
    if rng.random() < 0.3:
        item.flags |= 0x1000000000
    if rng.random() < 0.3:
        item.flags |= 0x8000 << 24
    return item.pack(stale or bytes(rng.randrange(256) for _ in range(I.ITEM_SIZE)))


# ---- suite ctor ---------------------------------------------------------------------------------
MIXES = (0, 0, 0, 0, 0x1, 0x8, 0x10, 0x20, 0x40, 0x4, 0x2, 0x80, 0x180, 0x200, 0x2000, 0x4000, 0x8000,
         0x10000, 0xB41, 0x19, 0x1FFFF)


def suite_ctor(elf, base, tables):
    rng = random.Random(OPTIONS['seed'])
    bad, cases, own = [], 0, {}
    for case in range(OPTIONS['cases']):
        pair = DS.Pair(elf, base)
        aseed = rng.getrandbits(32)
        answers = ChainAnswers(aseed)
        log_e = []
        install(pair.emu, answers, log_e)
        answers = ChainAnswers(aseed)
        block, item = BLOCK_BASE, BLOCK_BASE + 0x400
        pair.wb(block, bytes(rng.randrange(256) for _ in range(0x190)) if rng.random() < 0.5 else bytes(0x190))
        pair.wb(item, item_record(tables, rng))
        pos = [I.f_bits(rng.choice((rng.uniform(-16000, 16000), rng.uniform(-1e6, 1e6), 0.0)))
               for _ in range(3)]
        vec = BLOCK_BASE + 0x480
        pair.wb(vec, struct.pack('<3I', *pos))
        pair.w(R.G_RAND_SEED, 4, rng.getrandbits(32))
        pair.w(D.G_PROP_OPTIONS, 4, rng.choice((0, 0, 0x100, 0x101)))
        launch = rng.choice(MIXES)
        host = Host(answers, pair.ref)
        g = D.Ground(pair.ref, tables, host)
        mark = len(pair.ref.writes)
        seed0 = pair.ref.load(R.G_RAND_SEED, 4)
        ref_fault = emu_fault = None
        try:
            g.itemprop_ctor2(block, pos, item, launch)
        except (D.Fault, NotImplementedError) as exc:
            ref_fault = exc
        pair.emu.reset_log()
        try:
            pair.emu.call(D.ITEMPROP_CTOR2, block, vec, item, launch, max_steps=2000000)
        except EmuError as exc:
            emu_fault = exc
        if ref_fault or emu_fault:
            if (ref_fault is None) != (emu_fault is None):
                bad.append((case, 'fault on one side: ref %r emu %r' % (ref_fault, emu_fault)))
            continue
        cases += 1
        own[launch] = g.own_draws
        problems = []
        a, b = pair.emu.mem.read(block, 0x190), pair.ref.read(block, 0x190)
        if a != b:
            k = next(i for i in range(0x190) if a[i] != b[i])
            problems.append('block +0x%x emu %02x ref %02x' % (k, a[k], b[k]))
        if log_e != host.log:
            problems.append('calls emu %r ref %r' % (log_e[:3], host.log[:3]))
        if pair.emu.mem.u32(R.G_RAND_SEED) != pair.ref.load(R.G_RAND_SEED, 4):
            problems.append('seed')
        if ((seed0 * 0x19660D + 0x3C6EF35F) & M32) != pair.ref.load(R.G_RAND_SEED, 4):
            problems.append('not exactly one shared draw')
        extra = bad_calls(pair.emu, CHAIN)
        if extra:
            problems.append('unexpected calls %s' % sorted(hex(x) for x in extra))
        out = DS.written_outside(pair, mark)
        if out and 'differ' in out:
            problems.append(out)
        if problems:
            bad.append((case, 'launch %#x: %s' % (launch, '; '.join(problems))))
    per = ', '.join('launch %#x: %d own' % kv for kv in sorted(own.items()))
    report('ctor', not bad, '%d cases, %d mismatches, 1 shared draw each [%s]%s'
           % (cases, len(bad), per, ' first: %r' % (bad[0],) if bad else ''))


def call_handler(emu, addr):
    """handler(machine, params) with no cells (DS.call_handler with a larger step limit:
    up to 40 generator calls)."""
    params = emu.alloc(4)
    emu.mem.w32(params, 0)
    emu.reset_log()
    return emu.call(addr, 0x01100000, params, max_steps=2000000000)


def written_outside(pair, mark):
    """DS.written_outside without the ground blocks (compared whole above: the fast
    library hooks write them without the emulator's write log)."""
    def keep(a):
        return DS._outside_records(a) and not BLOCK_BASE <= a < BLOCK_BASE + 0x2000
    e = {a for _pc, addr, size, _v in pair.emu.writes for a in range(addr, addr + size) if keep(a)}
    r = {a for addr, size in pair.ref.writes[mark:] for a in range(addr, addr + size) if keep(a)}
    if e != r:
        return 'writes outside differ: emu only %s, ref only %s' % (
            [hex(a) for a in sorted(e - r)[:4]], [hex(a) for a in sorted(r - e)[:4]])
    for a in e:
        if pair.emu.mem.u8(a) != pair.ref.load(a, 1):
            return 'byte 0x%x differs' % a
    return None


# ---- suite random -------------------------------------------------------------------------------
def suite_random(elf, base, tables):
    rng = random.Random(OPTIONS['seed'] + 5)
    bad, cases, skipped = [], 0, 0
    seen = {}
    stub_list = [(a, n, {'pool_new': 1, 'vars_get': 1, 'vars_set': 2, 'text_lookup': 1, 'hud_showHelpMessage': 3,
                         'net_isLocalSlot': 1, 'player_recalcStats': 0, 'player_countPotions': 2,
                         'inventory_equipItem': 3, 'player_resetIdleAnim': 1, 'inventory_selectIdleAnim': 3,
                         'skill_lightQuiverComplement': 2, 'skill_axeBandolierComplement': 2}[n])
                 for a, n in DS.STUBS.items() if n != 'ItemProp_ctor2']
    real = DS.REAL | CHAIN | {D.GIVE_PLAYER_RANDOM, D.LEVEL_TIMES_DIFFICULTY, D.GENERATE_WITH_AFFIXES}
    item_code = (0x100000, 0x109000)        # the item generators, parser and helpers (docs/spec/items.md)
    for case in range(OPTIONS['cases']):
        pair = DS.Pair(elf, base)
        world = DS.World(tables, rng)
        world.plant(pair, 'full')
        n = pair.ref.load(R.G_NUM_PLAYERS, 4)
        level = rng.choice([1.0, 2.0, 3.5, 5.0, 8.0, 13.0, 22.0, 35.0, 54.0])
        pair.w(D.G_LEVEL, 4, I.f_bits(level))
        pair.w(D.G_PVP_A, 4, rng.choice([0, 0, 1]))
        pair.w(D.G_PVP_B, 4, rng.choice([0, 0, 0, 1]))
        pair.w(D.G_PROP_OPTIONS, 4, rng.choice((0, 0x100)))
        if rng.random() < 0.35:     # a small first draw: a budget the generator may not meet
            want = (rng.randrange(0, 40) << 16) | rng.getrandbits(16)
            pair.w(R.G_RAND_SEED, 4, ((want - 0x3C6EF35F) * pow(0x19660D, -1, 1 << 32)) & M32)
        frag = D.cstr(pair.ref, D.S_SPECIAL_LEVEL)
        name = (b'zz' + frag + b'q') if rng.random() < 0.35 else b'plainlevel'
        pair.wb(D.G_LEVEL_NAME, name + b'\0')
        for k in range(16):
            pair.wb(BLOCK_BASE + 0x200 * k, bytes(0x200))
        # the handler's stack record: what the stack held before
        sp = pair.emu.r[29] & M32
        rec_e = sp - HANDLER_FRAME
        stale = bytearray(rng.randrange(256) for _ in range(I.ITEM_SIZE))
        definition = 0 if rng.random() < 0.2 else rng.choice(tables.defs).addr
        struct.pack_into('<IhH', stale, 0, definition, rng.choice([1, 0, 3]), 0)
        struct.pack_into('<Q', stale, 8, rng.choice([0, rng.getrandbits(64)]))
        pair.ensure(rec_e, I.ITEM_SIZE)
        pair.emu.mem.write(rec_e, bytes(stale))
        pair.ref.write(DS.SCRATCH, bytes(stale))
        aseed = rng.getrandbits(32)
        answers = ChainAnswers(aseed, pool_zero=0.1)
        log_e = []
        install(pair.emu, answers, log_e, stub_list)
        answers = ChainAnswers(aseed, pool_zero=0.1)
        if not OPTIONS['full']:
            fast_library(pair.emu)
        host = Host(answers, pair.ref)
        comp = D.RandomGiver(pair.ref, tables, host, DS.SCRATCH)
        mark = len(pair.ref.writes)
        ref_fault = emu_fault = None
        try:
            comp.givePlayerRandom()
        except (D.Fault, R.Fault, NotImplementedError, ValueError, KeyError, IndexError) as exc:
            ref_fault = exc
        try:
            call_handler(pair.emu, D.GIVE_PLAYER_RANDOM)
        except EmuError as exc:
            emu_fault = exc
        if ref_fault or emu_fault:
            if (ref_fault is None) != (emu_fault is None):
                bad.append((case, 'fault on one side: ref %r emu %r' % (ref_fault, emu_fault)))
            else:
                skipped += 1
                key = 'fault: ' + str(ref_fault).split(' reads')[0][:40]
                seen[key] = seen.get(key, 0) + 1
            continue
        cases += 1
        for kind, _slot, what in comp.outcomes:
            seen['%s %s' % (kind, what)] = seen.get('%s %s' % (kind, what), 0) + 1
        for t in comp.tries:
            seen['tries %d' % t] = seen.get('tries %d' % t, 0) + 1
        problems = []
        if log_e != host.log:
            k = next((i for i in range(min(len(log_e), len(host.log))) if log_e[i] != host.log[i]), None)
            problems.append('calls differ at %r: emu %r ref %r' % (k, log_e[k:k + 2] if k is not None else log_e[-2:],
                                                                   host.log[k:k + 2] if k is not None else host.log[-2:]))
        a = DS.masked_records(DS.records(lambda addr, n: pair.emu.mem.read(addr, n)))
        b = DS.masked_records(DS.records(lambda addr, n: pair.ref.read(addr, n)))
        if a != b:
            problems.append(DS.first_diff(a, b))
        for k in range(16):
            blk = BLOCK_BASE + 0x200 * k
            if mask_block(pair.emu.mem.read(blk, 0x190)) != mask_block(pair.ref.read(blk, 0x190)):
                problems.append('ground block %d' % k)
                break
        if pair.emu.mem.u32(R.G_RAND_SEED) != pair.ref.load(R.G_RAND_SEED, 4):
            problems.append('seed')
        extra = {t for t in bad_calls(pair.emu, real) if not item_code[0] <= t < item_code[1]}
        if extra:
            problems.append('unexpected calls %s' % sorted(hex(x) for x in extra))
        out = written_outside(pair, mark)
        if out:
            problems.append(out)
        if problems:
            bad.append((case, 'players %d: %s' % (n, '; '.join(problems))))
    cover = ', '.join('%s %d' % kv for kv in sorted(seen.items()))
    for case, text in bad[:6]:
        print('   case %d: %s' % (case, text[:600]))
    report('random', not bad, '%d cases (%d faulted on both sides), %d mismatches [%s]%s'
           % (cases, skipped, len(bad), cover, ' first: %r' % (bad[0],) if bad else ''))


def find_elf(argv):
    for a in argv:
        if not a.startswith('-') and os.path.exists(a):
            return a
    for c in DS.CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def main(argv):
    args = list(argv)
    rest = []
    while args:
        a = args.pop(0)
        if a == '--cases':
            OPTIONS['cases'] = int(args.pop(0))
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0))
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '--full':
            OPTIONS['full'] = True
        else:
            rest.append(a)
    elf = find_elf(rest)
    if elf is None:
        print('SLUS_209.73 not found; nothing to test')
        return 0
    import hashlib
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != DS.ELF_SHA:
        print('not the US v2.00 executable')
        return 1
    base = EE(elf)
    tables = DS.tables_for(elf)
    for name, suite in (('ctor', suite_ctor), ('random', suite_random)):
        if OPTIONS['filter'] is None or OPTIONS['filter'] in name:
            suite(elf, base, tables)
    failed = sum(1 for _n, ok in RESULTS if not ok)
    print('%d suites, %d failed (seed %d, %d cases%s)' % (len(RESULTS), failed, OPTIONS['seed'], OPTIONS['cases'],
                                                          ', library original' if OPTIONS['full'] else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
