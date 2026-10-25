#!/usr/bin/env python3
"""difftest_script_items.py - tools/ref_script_items.py against the original functions.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_script_items.py [SLUS_209.73] [--cases N] [--seed N] [-k TEXT] [-v]

The original machine code runs in tools/ee_emu.py.  Suites:

  helpers   inventory_countItemByName, inventory_findItemBySubstring, player_getPassiveLevel,
            player_getSkillRank, player_itemWeight, player_recalcLoad, called directly
  limit     player_recalcStats 0x1b6458 run whole with its call-outs stubbed (except
            player_getPassiveLevel); only record +0x124 is compared
  handlers  the 12 item and gold handlers and clearAllSkills, entered with (machine,
            params) as the dispatcher enters them.  REAL: the handlers, the two bag scans,
            libc, inventory_removeItem, inventory_giveItem, item_parseDescriptor and
            everything it calls, player_itemWeight, item_getWeight, player_getPassiveLevel,
            player_getSkillRank, player_recalcLoad.  STUBS (recorded, same seeded answers on
            both sides): scr_getAddr / scr_getString (they hand over the test strings),
            player_recalcStats, player_countPotions, inventory_equipItem,
            player_resetIdleAnim, pool_new, ItemProp_ctor2, vars_get, vars_set, text_lookup,
            hud_showHelpMessage, net_isLocalSlot, the two skill complements.  A call to any
            other address outside the C library is a failure.
  missions  clearAllSkills followed by mission_isAvailable / mission_isComplete for
            difficulties 0..5: only row 0 sees the 0xff bytes
  cm1       game_scanCm1Vars(0) and (1), game_set4f7110, with the real profile_getVar

For every case: the result, the stub calls in order with their arguments (strings, vectors
and item records by content), the four player records and the shared seed must be equal.
Item records built by the parser are compared without the bytes the parser never writes
(+0x06, +0x07, +0x44..+0x47 and the values of empty modifier slots, docs/spec/items.md 2).
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, float_to_raw  # noqa: E402
import ref_items as I                           # noqa: E402
import ref_natives as N                         # noqa: E402
import ref_script_items as R                    # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73'),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')]
OPTIONS = {'cases': 200, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
M32 = 0xFFFFFFFF

COUNT, FIND, PASSIVE, RANK = 0x1C5880, 0x1C5A70, 0x1BED48, 0x1BF330
WEIGHT, GET_WEIGHT, RECALC_LOAD, RECALC_STATS = 0x1B6338, 0x103E08, 0x1BEC10, 0x1B6458
SCAN, SET_WORD, PROFILE_GET = 0x1EB950, 0x1EC830, 0x22289C
MISSION_AVAIL, MISSION_DONE = 0x1BF698, 0x1BF730
RUNTIME = (0x3A5000, 0x3CC000)
STUBS = {
    0x1B6458: 'player_recalcStats', 0x1BA5F8: 'player_countPotions', 0x1C27C0: 'inventory_equipItem',
    0x1B2470: 'player_resetIdleAnim', 0x14FDB8: 'pool_new', 0x1590EC: 'ItemProp_ctor2',
    0x1ED778: 'vars_get', 0x1ED854: 'vars_set', 0x173C84: 'text_lookup', 0x1D9830: 'hud_showHelpMessage',
    0x13E150: 'net_isLocalSlot', 0x1C3F08: 'inventory_selectIdleAnim',
    0x2FF4B4: 'skill_lightQuiverComplement', 0x2FF2E4: 'skill_axeBandolierComplement',
}
SCR_GET_ADDR, SCR_GET_STRING = 0x1414A8, 0x141650
REAL = set(R.HANDLERS.values()) | {COUNT, FIND, PASSIVE, RANK, WEIGHT, GET_WEIGHT, RECALC_LOAD,
                                   0x1C1CB0, 0x1C1868, 0x1069B8, 0x1046E0, 0x108924}
SCRATCH = 0x01FF0000
LIBC_SDIDINIT = 0x50C530        # newlib's reentrancy flag that libc_sinit 0x3b3d00 sets on first use            # the reference's stand-in for the handler's stack record


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'] in name


# ---- memory shared by both sides ----------------------------------------------------------------
class Under:
    """The pristine executable image under the reference's copy-on-write memory."""

    def __init__(self, emu):
        self.emu = emu

    def read(self, addr, size):
        out = bytearray()
        for a in range(addr, addr + size):
            out.append(self.emu.mem.u8(a) if self.emu.mem.is_mapped(a) else 0)
        return bytes(out)


class Pair:
    """One case: the emulator and the reference memory, written together."""

    def __init__(self, elf, base):
        self.emu = EE(elf)
        self.ref = N.Mem(Under(base))

    def w(self, addr, size, value):
        self.ensure(addr, size)
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.ref.store(addr, size, value)

    def wb(self, addr, data):
        self.ensure(addr, len(data))
        self.emu.mem.write(addr, data)
        self.ref.write(addr, data)

    def ensure(self, addr, size):
        if not self.emu.mem.is_mapped(addr, size):
            lo = addr & ~0xFFF
            self.emu.mem.map(lo, ((addr + size + 0xFFF) & ~0xFFF) - lo)


def tables_for(elf):
    return I.Tables(I.Exe(elf))


# ---- random state ------------------------------------------------------------------------------
class World:
    def __init__(self, tables, rng):
        self.tables, self.rng = tables, rng
        self.defs = [d for d in tables.defs]
        self.names = [d.name for d in self.defs if d.name]
        self.planted = []               # definition names put into the bags of this case

    def item_bytes(self, definition=None):
        rng = self.rng
        d = definition or rng.choice(self.defs)
        self.planted.append(d.name)
        item = I.Item(d)
        item.count = rng.choice([1, 1, 1, 2, 5, 20, -3, 0x7FFF]) if rng.random() < 0.3 else d.count
        item.flags = d.flags
        if rng.random() < 0.3:
            item.flags |= (rng.randrange(32) << 11)
        if rng.random() < 0.15:
            item.flags |= R.ITEM_FLAG_THROWN_AXE
        for k in range(rng.randrange(3)):
            item.set_modifier(rng.choice([0x24, 0x07, 0x0D, 0x1E]), rng.randrange(-50, 200))
        stale = bytes(rng.randrange(256) for _ in range(I.ITEM_SIZE))
        return item.pack(stale)

    def plant(self, pair, kind):
        rng, w = self.rng, pair.w
        n = rng.choice([1, 1, 2, 2, 3, 4, 0]) if kind != 'gold0' else rng.choice([1, 2, 3, 4])
        w(R.G_NUM_PLAYERS, 4, n)
        w(R.G_MEDAL_MISSION, 4, rng.choice([0, 0, 0, 1]))
        w(R.G_MEDAL_PLAYER, 1, rng.randrange(max(n, 1)))
        w(R.G_RAND_SEED, 4, rng.getrandbits(32))
        w(R.G_LOAD_BONUS, 4, rng.choice([0, 0, 0, 1, -7]))
        alive = list(range(max(n, 1)))
        rng.shuffle(alive)
        for k, slot in enumerate(alive):
            w(R.G_ALIVE_LIST + 4 * k, 4, slot)
        w(0x4F719C, 4, rng.choice([1, 1, 2, 3, 4, 5]))                 # difficulty (first recall hint)
        w(LIBC_SDIDINIT, 4, 1)          # stdio was set up at boot; sscanf must not do it again
        w(0x402791, 1, rng.choice([0, 0, 1]))                          # network mode
        for slot in range(4):
            mark = len(self.planted)
            self._plant_slot(pair, kind, slot, n)
            if slot >= n:
                del self.planted[mark:]

    def _plant_slot(self, pair, kind, slot, n):
        rng, w = self.rng, pair.w
        if True:
            r = R.rec(slot)
            w(r + R.P_CLASS, 4, rng.randrange(7))
            w(r + R.P_EFF_STRENGTH, 4, rng.choice([10, 46, 200, 5000, 9990, -200]))
            w(r + R.P_GOLD, 4, rng.choice([0, 1, 500, 99999990, 0x7FFFFFF0, -5, rng.getrandbits(32)]))
            w(r + R.P_SKILL_POINTS, 4, rng.getrandbits(32))
            w(r + R.P_ABILITY_MASK, 8, rng.getrandbits(64))
            pair.wb(r + R.P_PASSIVES, bytes(rng.choice([0, 0, 1, 3, 0x80, 0xFF]) for _ in range(48)))
            w(r + R.P_LOAD, 4, I.f_bits(rng.choice([0.0, 12.5, 150.0, 1e6, -3.0])))
            w(r + R.P_LOAD_LIMIT, 4, I.f_bits(rng.choice([0.0, 171.0, 9999.0, 160.0])))
            pairs = rng.randrange(49)
            for k in range(48):
                ident = rng.choice([0x49, 0x4A, 3, 7, 0x40]) if k < pairs else -1
                w(r + R.P_SKILL_PAIRS + 4 * k, 2, ident)
                w(r + R.P_SKILL_PAIRS + 4 * k + 2, 2, rng.randrange(-2, 25))
            pair.wb(r + 0x4BC8, bytes(rng.randrange(256) for _ in range(0x45)))   # countdowns, missions
            for k in range(15):
                w(r + R.P_ABILITY_SKILL + R.ABILITY_SIZE * k, 2, rng.randrange(-1, 60))
                w(r + R.P_ABILITY_SKILL + R.ABILITY_SIZE * k + 4, 1, rng.randrange(256))
            w(r + R.P_PAD_MASK, 4, rng.getrandbits(32))
            w(r + R.P_QUICK_A, 2, rng.getrandbits(16))
            w(r + 0x4C25, 1, rng.choice([0, 1]))                       # first-recall flag
            w(r + 0x4A7C, 1, rng.choice([0, 1]))                       # active set
            w(r + 0x4A86, 1, rng.randrange(8))                         # weapon class
            entries = []
            for bag in range(3):
                count = rng.choice([0, 0, 1, 2, 3, 5, 8, 64, 63]) if kind != 'empty' else 0
                base = r + R.P_BAGS + bag * R.BAG_SIZE
                for i in range(R.BAG_SLOTS):
                    if i < count:
                        pair.wb(base + i * R.ITEM_SIZE, self.item_bytes())
                        w(base + i * R.ITEM_SIZE + 0x22, 2, i)
                        entries.append(base + i * R.ITEM_SIZE)
                    else:
                        pair.wb(base + i * R.ITEM_SIZE, bytes(R.ITEM_SIZE))
                w(base + R.BAG_COUNT, 4, count)
            for k in range(17):
                w(r + 0x43F0 + 4 * k, 4, rng.choice(entries) if entries and rng.random() < 0.3 else 0)
            for k in range(3):
                w(r + R.P_SET_WEAPONS + 4 * k, 4, rng.choice(entries) if entries and rng.random() < 0.4 else 0)
            if rng.random() < 0.8:
                obj = 0x01200000 + slot * 0x1000
                pair.wb(obj, bytes(0x40))
                w(obj + R.OBJ_FLAGS, 4, rng.choice([0, 0, 0, R.OBJ_DEAD, 0x2]))
                for k in range(3):
                    w(obj + R.OBJ_POS + 4 * k, 4, I.f_bits(rng.uniform(-5000, 5000)))
                w(obj + 0x3C8, 4, slot if rng.random() < 0.85 else rng.randrange(4))
                w(r + R.P_OBJECT, 4, obj)
            else:
                w(r + R.P_OBJECT, 4, 0)


def s8(x):
    return R.s8(x)


# ---- stubs --------------------------------------------------------------------------------------
class Answers:
    """Seeded answers, the same on both sides."""

    def __init__(self, rng):
        self.rng = rng
        self.pool = rng.choice([0, 0x01300000])
        self.vars = rng.choice([0, 0, 1])
        self.comp = I.f_bits(rng.choice([0.5, 0.85, 0.23, 1.0, 0.0]))
        self.local = rng.choice([0, 0])
        self.text = 0x01310000

    def value(self, name):
        return {'pool_new': self.pool, 'vars_get': self.vars, 'net_isLocalSlot': self.local,
                'text_lookup': self.text, 'skill_lightQuiverComplement': self.comp,
                'skill_axeBandolierComplement': self.comp}.get(name, 0)


def mask_item(data):
    """Item bytes without what the parser leaves to chance."""
    out = bytearray(data)
    for k in (6, 7, 0x44, 0x45, 0x46, 0x47):
        out[k] = 0
    for slot in range(4):
        if struct.unpack_from('<h', out, 0x24 + 8 * slot)[0] == -1:
            out[0x26 + 8 * slot:0x2C + 8 * slot] = bytes(6)
    return bytes(out)


def normalize(name, args, read):
    """Arguments by content: read(addr, size) -> bytes of the side's memory."""
    if name == 'ItemProp_ctor2':
        block, pos, item, last = args
        pos = pos if isinstance(pos, tuple) else struct.unpack('<3I', read(pos, 12))
        return (block, tuple(pos), mask_item(read(item, R.ITEM_SIZE)), last)
    return tuple(a & M32 for a in args)


def install_stubs(emu, answers, log):
    def make(addr, name):
        def run(e):
            args = tuple(e.r[4 + k] & M32 for k in range(4))
            count = {'pool_new': 1, 'vars_get': 1, 'vars_set': 2, 'text_lookup': 1, 'hud_showHelpMessage': 3,
                     'net_isLocalSlot': 1, 'player_recalcStats': 0, 'player_countPotions': 2,
                     'inventory_equipItem': 3, 'player_resetIdleAnim': 1, 'ItemProp_ctor2': 4,
                     'inventory_selectIdleAnim': 3, 'skill_lightQuiverComplement': 2,
                     'skill_axeBandolierComplement': 2}[name]
            log.append((name, normalize(name, args[:count], lambda a, n: e.mem.read(a, n))))
            value = answers.value(name)
            if name.startswith('skill_'):
                e.f[0] = value
                return None
            return value
        emu.stub(addr, function=run, name=name)
    for addr, name in STUBS.items():
        make(addr, name)


class RefHost(R.Host):
    def __init__(self, answers, mem):
        R.Host.__init__(self)
        self.answers_obj, self.mem = answers, mem

    def call(self, name, *args):
        read = lambda a, n: self.mem.read(a, n)   # noqa: E731
        self.log.append((name, normalize(name, args, read)))
        return self.answers_obj.value(name)


# ---- calling a handler as the dispatcher does ---------------------------------------------------------
def call_handler(emu, addr, cells, strings):
    """handler(machine, params): params[0] = byte count, params[1..] the cells.  A string
    cell is a token; scr_getAddr hands it back and scr_getString copies the test string."""
    params = emu.alloc(4 * (len(cells) + 1))
    emu.mem.w32(params, 4 * len(cells))
    for k, c in enumerate(cells):
        emu.mem.w32(params + 4 + 4 * k, c & M32)

    def get_addr(e):
        e.mem.w32(e.r[6] & M32, e.r[5] & M32)
        return 0

    def get_string(e):
        text = strings[e.r[5] & M32]
        e.mem.write(e.r[4] & M32, text + b'\0')
        return 0
    emu.stub(SCR_GET_ADDR, function=get_addr, name='scr_getAddr')
    emu.stub(SCR_GET_STRING, function=get_string, name='scr_getString')
    emu.reset_log()
    return emu.call(addr, 0x01100000, params, max_steps=20000000)


def bad_calls(emu):
    out = set()
    for c in emu.calls:
        t = c.target
        if t in REAL or t in STUBS or t in (SCR_GET_ADDR, SCR_GET_STRING):
            continue
        if RUNTIME[0] <= t < RUNTIME[1]:
            continue
        out.add(t)
    return out


def records(read):
    return read(R.G_PLAYERS, 4 * R.REC_SIZE)


def masked_records(data):
    """The four records with every bag entry passed through mask_item."""
    out = bytearray(data)
    for slot in range(4):
        for bag in range(3):
            for i in range(R.BAG_SLOTS):
                at = slot * R.REC_SIZE + R.P_BAGS + bag * R.BAG_SIZE + i * R.ITEM_SIZE
                out[at:at + R.ITEM_SIZE] = mask_item(bytes(out[at:at + R.ITEM_SIZE]))
    return bytes(out)


def _outside_records(addr):
    lo, hi = R.G_PLAYERS, R.G_PLAYERS + 4 * R.REC_SIZE
    if lo <= addr < hi or EE.STACK_LO <= addr < EE.STACK_HI or SCRATCH <= addr < SCRATCH + 0x100:
        return False
    return True


def written_outside(pair, mark):
    """Bytes written outside the four records, the stack and the scratch record must be the
    same set on both sides, with the same final values."""
    emu_set = set()
    for _pc, addr, size, _value in pair.emu.writes:
        emu_set.update(a for a in range(addr, addr + size) if _outside_records(a))
    ref_set = set()
    for addr, size in pair.ref.writes[mark:]:
        ref_set.update(a for a in range(addr, addr + size) if _outside_records(a))
    if emu_set != ref_set:
        only_e, only_r = sorted(emu_set - ref_set), sorted(ref_set - emu_set)
        return 'writes outside the records differ: emu only %s, ref only %s' % (
            [hex(a) for a in only_e[:4]], [hex(a) for a in only_r[:4]])
    for a in emu_set:
        if pair.emu.mem.u8(a) != pair.ref.load(a, 1):
            return 'byte 0x%x: emu %02x ref %02x' % (a, pair.emu.mem.u8(a), pair.ref.load(a, 1))
    return None


def first_diff(a, b):
    for k in range(min(len(a), len(b))):
        if a[k] != b[k]:
            slot, off = divmod(k, R.REC_SIZE)
            return 'record %d +0x%x: emu %02x ref %02x' % (slot, off, a[k], b[k])
    return 'length'


# ---- suites -------------------------------------------------------------------------------------------
def pick_name(world, rng, need_substring=False):
    roll = rng.random()
    if roll < 0.35 and world.planted:
        return rng.choice(world.planted)
    if roll < 0.5:
        return world.rng.choice(world.names)
    if roll < 0.65:
        return world.rng.choice(world.names).upper()
    if roll < 0.8 and need_substring:
        a = rng.choice(world.planted) if world.planted else world.rng.choice(world.names)
        b = world.rng.choice(world.names)
        return b'xx ' + a + b' and ' + b
    if roll < 0.9:
        return world.rng.choice(world.names)[:3]
    return b''


def suite_helpers(elf, base, tables):
    rng = random.Random(OPTIONS['seed'])
    bad, cases = [], 0
    for case in range(OPTIONS['cases']):
        world = World(tables, rng)
        pair = Pair(elf, base)
        world.plant(pair, 'full')
        answers = Answers(rng)
        log_e, log_r = [], []
        install_stubs(pair.emu, answers, log_e)
        host = RefHost(answers, pair.ref)
        slot = rng.randrange(4)
        which = case % 6
        try:
            if which == 0:
                name = pick_name(world, rng)
                buf = pair.emu.alloc(len(name) + 1)
                pair.emu.mem.write(buf, name + b'\0')
                got = R.s32(pair.emu.call(COUNT, buf, slot))
                want = R.count_item_by_name(pair.ref, name, slot)
            elif which == 1:
                text = pick_name(world, rng, True)
                buf = pair.emu.alloc(len(text) + 1)
                pair.emu.mem.write(buf, text + b'\0')
                outs = pair.emu.alloc(8)
                pair.emu.mem.w32(outs + 4, 0x5A5A)
                pair.emu.call(FIND, slot, buf, outs, outs + 4)
                got = (R.s32(pair.emu.mem.u32(outs)), pair.emu.mem.u32(outs + 4))
                index, bag = R.find_item_by_substring(pair.ref, slot, text)
                want = (index, 0x5A5A if bag is None else bag)
            elif which == 2:
                mask = rng.choice([0x40, 0x10000, 0x40000, 1, 2, 4, 0x200000000])
                s = rng.choice([slot, slot, slot, 4, 5, -1])
                got = R.s32(pair.emu.call(PASSIVE, s, mask))
                want = R.passive_level(pair.ref, s, mask)
            elif which == 3:
                skill = rng.choice([0x49, 0x4A, 3, 7, 0x40, 99])
                got = R.s32(pair.emu.call(RANK, slot, skill))
                want = R.skill_rank(pair.ref, slot, skill)
            elif which == 4:
                bag = rng.randrange(3)
                count = R.mem_s32(pair.ref, R.bag_count_at(slot, bag))
                index = rng.randrange(max(count, 1))
                item = R.bag_entry(slot, bag, index) if rng.random() < 0.9 else 0
                pair.emu.call(WEIGHT, slot, item)
                got = pair.emu.f[0]
                want = R.item_weight(pair.ref, tables, host, slot, item)
            else:
                pair.emu.call(RECALC_LOAD, slot)
                got = pair.emu.mem.u32(R.rec(slot) + R.P_LOAD)
                R.recalc_load(pair.ref, tables, host, slot)
                want = pair.ref.load(R.rec(slot) + R.P_LOAD, 4)
        except EmuError as exc:
            bad.append((case, 'emulator stopped: %s' % exc))
            continue
        cases += 1
        if got != want or log_e != host.log:
            bad.append((case, 'kind %d: emu %r ref %r; calls %r / %r' % (which, got, want, log_e[:3], host.log[:3])))
        extra = bad_calls(pair.emu)
        if extra:
            bad.append((case, 'unexpected calls %s' % sorted(hex(x) for x in extra)))
    report('helpers', not bad, '%d cases, %d mismatches%s' % (cases, len(bad), _first(bad)))


def suite_limit(elf, base, tables):
    rng = random.Random(OPTIONS['seed'] + 1)
    bad, cases = [], 0
    for case in range(max(OPTIONS['cases'] // 2, 20)):
        pair = Pair(elf, base)
        world = World(tables, rng)
        world.plant(pair, 'empty')
        emu = pair.emu
        emu.follow = {RECALC_STATS, PASSIVE}
        emu.default_ret = 0
        try:
            emu.call(RECALC_STATS)
        except EmuError as exc:
            bad.append((case, 'emulator stopped: %s' % exc))
            continue
        n = R.mem_s32(pair.ref, R.G_NUM_PLAYERS)
        for slot in range(4):
            r = R.rec(slot)
            if slot >= n:
                continue
            obj = pair.ref.load(r + R.P_OBJECT, 4)
            if obj == 0:
                # no player object: the record's limit is not recomputed
                want = pair.ref.load(r + R.P_LOAD_LIMIT, 4)
                strength = level = None
            else:
                # the effective strength recalcStats has just written; the passive is asked
                # for the slot the object names (+0x3c8), not the loop's record
                strength = emu.mem.s32(r + R.P_EFF_STRENGTH)
                level = R.passive_level(pair.ref, R.mem_s32(pair.ref, obj + 0x3C8), R.PASSIVE_LOAD)
                want = R.load_limit(strength, level, R.mem_s32(pair.ref, R.G_LOAD_BONUS))
            got = emu.mem.u32(r + R.P_LOAD_LIMIT)
            cases += 1
            if got != want:
                bad.append((case, 'slot %d strength %r level %r bonus %d: emu %08x ref %08x' % (
                    slot, strength, level, R.mem_s32(pair.ref, R.G_LOAD_BONUS), got, want)))
    report('limit', not bad, '%d records, %d mismatches%s' % (cases, len(bad), _first(bad)))


def _first(bad):
    if not bad:
        return ''
    if OPTIONS['verbose']:
        return '\n    ' + '\n    '.join('%s: %s' % b for b in bad[:8])
    return '; first: case %s: %s' % bad[0]


def own_item_name(pair, world, slot):
    """The definition name of a random entry of that slot's bags, or None."""
    if not 0 <= slot < 4:
        return None
    entries = []
    for bag in range(3):
        count = R.mem_s32(pair.ref, R.bag_count_at(slot, bag))
        entries += [R.bag_entry(slot, bag, i) for i in range(max(0, min(count, 64)))]
    if not entries:
        return None
    d = world.tables.by_addr.get(pair.ref.load(world.rng.choice(entries), 4))
    return d.name if d is not None else None


def handler_args(name, world, rng, pair):
    sig = R.SIGNATURES[name]
    cells, strings, values = [], {}, []
    for k, kind in enumerate(sig):
        if kind == 's':
            if name.startswith('give'):
                d = world.rng.choice(world.defs)
                text = d.name
                if rng.random() < 0.3:
                    text += rng.choice([b'+', b'+dmg5', b'+mesh2', b'+mesh-1', b'+ac3+str4'])
                if rng.random() < 0.1:
                    text = b'nosuchitem'
                if rng.random() < 0.15:
                    text = world.rng.choice(world.tables.presets).name or text
            elif name == 'onePlayerHasItem' and rng.random() < 0.6 and own_item_name(pair, world, values[0]):
                text = own_item_name(pair, world, values[0])
            elif name == 'removePlayerItem' and world.planted and rng.random() < 0.6:
                text = b'take the ' + rng.choice(world.planted) + b' away'
            else:
                text = pick_name(world, rng, name == 'removePlayerItem')
            token = 0x7000 + k
            strings[token] = text
            cells.append(token)
            values.append(text)
        else:
            if name in ('onePlayerHasItem', 'removePlayerItem', 'giveOnePlayerItem') and k == 0:
                v = rng.choice([0, 0, 0, 1, 1, 2, 3, -1, -1, 4, -2])
            elif name in ('givePlayerGold', 'takePlayerGold'):
                v = rng.choice([0, 1, 7, 100, 1000, -50, 99999999, 0x7FFFFFFF, -0x80000000])
            else:
                v = rng.choice([0, 0, 1, 2, -1])
            cells.append(v)
            values.append(v)
    return cells, strings, values


def suite_handlers(elf, base, tables):
    rng = random.Random(OPTIONS['seed'] + 2)
    names = [n for n in R.HANDLERS if wanted(n) or wanted('handlers')]
    per = {}
    for name in names:
        bad, cases, skipped = [], 0, 0
        seen = {'changed': 0, 'seed moved': 0}
        for case in range(OPTIONS['cases']):
            pair = Pair(elf, base)
            world = World(tables, rng)
            world.plant(pair, 'gold0' if 'Gold' in name else 'full')
            answers = Answers(rng)
            log_e = []
            install_stubs(pair.emu, answers, log_e)
            cells, strings, values = handler_args(name, world, rng, pair)
            host = RefHost(answers, pair.ref)
            comp = R.Composer(pair.ref, tables, host, SCRATCH)
            seed_before = pair.ref.load(R.G_RAND_SEED, 4)
            before = records(lambda addr, n: pair.ref.read(addr, n))
            mark = len(pair.ref.writes)
            ref_fault = emu_fault = None
            try:
                want = getattr(comp, name)(*values)
            except Exception as exc:     # noqa: BLE001  the reference refuses (fault, overrun)
                ref_fault = exc
            try:
                got = R.s32(call_handler(pair.emu, R.HANDLERS[name], cells, strings))
            except EmuError as exc:
                emu_fault = exc
            if ref_fault is not None or emu_fault is not None:
                if (ref_fault is None) != (emu_fault is None):
                    bad.append((case, 'fault on one side only: ref %r emu %r' % (ref_fault, emu_fault)))
                else:
                    skipped += 1
                continue
            cases += 1
            if want:
                seen['result non-zero'] = seen.get('result non-zero', 0) + 1
            for call_name, _args in host.log:
                seen[call_name] = seen.get(call_name, 0) + 1
            if records(lambda addr, n: pair.ref.read(addr, n)) != before:
                seen['changed'] += 1
            give = name.startswith('give')
            a = records(lambda addr, n: pair.emu.mem.read(addr, n))
            b = records(lambda addr, n: pair.ref.read(addr, n))
            if give:
                a, b = masked_records(a), masked_records(b)
            problems = []
            if (got & M32) != (R.s32(want) & M32):
                problems.append('result emu %d ref %d' % (got, want))
            if log_e != host.log:
                problems.append('calls emu %r ref %r' % (log_e[:4], host.log[:4]))
            if a != b:
                problems.append(first_diff(a, b))
            if pair.emu.mem.u32(R.G_RAND_SEED) != pair.ref.load(R.G_RAND_SEED, 4):
                problems.append('seed')
            if seed_before != pair.ref.load(R.G_RAND_SEED, 4):
                seen['seed moved'] += 1
            extra = bad_calls(pair.emu)
            if extra:
                problems.append('unexpected calls %s' % sorted(hex(x) for x in extra))
            outside = written_outside(pair, mark)
            if outside:
                problems.append(outside)
            if problems:
                bad.append((case, '%r: %s' % (values, '; '.join(problems))))
        per[name] = (cases, skipped, bad, seen)
        cover = ', '.join('%s %d' % kv for kv in sorted(seen.items()) if kv[1])
        report('handlers/' + name, not bad, '%d cases (%d faulted on both sides), %d mismatches [%s]%s'
               % (cases, skipped, len(bad), cover, _first(bad)))
    return per


def suite_missions(elf, base, tables):
    rng = random.Random(OPTIONS['seed'] + 3)
    bad = []
    seen = {}
    for case in range(40):
        pair = Pair(elf, base)
        World(tables, rng).plant(pair, 'empty')
        slot = pair.emu.mem.u8(R.G_MEDAL_PLAYER)
        pair.w(R.G_MEDAL_PLAYER, 1, 0)                     # the mission functions read record 0
        pair.emu.call(R.HANDLERS['clearAllSkills'], 0, 0)
        R.clear_all_skills(pair.ref)
        for d in range(6):
            for m in range(13):
                avail = pair.emu.call(MISSION_AVAIL, d, m) & M32
                done = pair.emu.call(MISSION_DONE, d, m) & M32
                byte = pair.ref.load(R.mission_byte_addr(0, d, m), 1)
                want = (byte & 1, (byte >> 1) & 1)
                if ((avail != 0), (done != 0)) != (want[0] != 0, want[1] != 0):
                    bad.append((case, 'd %d m %d emu %d/%d ref %r' % (d, m, avail, done, want)))
                at = R.P_MISSIONS + 13 * d + m
                if R.SKILL_PAIR_SPAN[0] <= at < R.SKILL_PAIR_SPAN[1]:
                    seen.setdefault(d, set()).add(m)
                    if not (avail and done):
                        bad.append((case, 'd %d m %d inside the cleared pairs but not 0xff' % (d, m)))
        del slot
    rows = sorted(seen)
    report('missions', not bad and rows == [0] and seen[0] == set(range(9)),
           'rows with bytes inside the cleared skill pairs: %s (missions %s)%s' % (
               rows, sorted(seen.get(0, ())), _first(bad)))


def suite_cm1(elf, base, tables):
    rng = random.Random(OPTIONS['seed'] + 4)
    bad, cases = [], 0
    for case in range(max(OPTIONS['cases'] // 2, 30)):
        pair = Pair(elf, base)
        game = N.Game(mem=pair.ref)
        # a profile table with some of the nine names set (any order, mixed with others)
        names = list(R.CM1_NAMES) + [b'other', b'm10cm1', b'm3cm1']
        rng.shuffle(names)
        where = N.G_PROFILE_VARS
        for name in names[:rng.randrange(len(names) + 1)]:
            value = rng.choice([0, 0, 1, -1, 5])
            pair.wb(where, name + b'\0' + bytes([value & 0xFF]))
            where += len(name) + 2
        pair.wb(where, b'\0')
        word = rng.choice([0xFFFFFFFF, 0, 3, 9, 12, 13])
        pair.w(R.G_CM1_WORD, 4, word)
        emu = pair.emu
        which = case % 3
        try:
            if which == 0:
                got = R.s32(emu.call(SCAN, 0))
                want = R.scan_cm1_vars(0, game.profile_get, word)
            elif which == 1:
                got = R.s32(emu.call(SCAN, rng.choice([1, 7, -1])))
                want = R.scan_cm1_vars(1, game.profile_get, word)
            else:
                value = rng.choice([-1, -1, 0, 4, 0x7FFFFFFF])
                emu.call(SET_WORD, value)
                R.set_cm1_word(pair.ref, value, game.profile_get)
                got = emu.mem.s32(R.G_CM1_WORD)
                want = R.mem_s32(pair.ref, R.G_CM1_WORD)
        except EmuError as exc:
            bad.append((case, 'emulator stopped: %s' % exc))
            continue
        cases += 1
        table_e = emu.mem.read(N.G_PROFILE_VARS, 0x200)
        table_r = pair.ref.read(N.G_PROFILE_VARS, 0x200)
        if got != want or table_e != table_r:
            bad.append((case, 'kind %d: emu %d ref %d, profile table %s' % (
                which, got, want, 'equal' if table_e == table_r else 'differs')))
    report('cm1', not bad, '%d cases, %d mismatches%s' % (cases, len(bad), _first(bad)))


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
    if '-k' in args:
        OPTIONS['filter'] = args[args.index('-k') + 1]
    OPTIONS['verbose'] = '-v' in args
    elf = find_elf([a for i, a in enumerate(args) if i == 0 or args[i - 1] not in ('--cases', '--seed', '-k')])
    if elf is None:
        print('SLUS_209.73 not found; nothing compared')
        return 0
    import hashlib
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != ELF_SHA:
        print('this is not SLUS_209.73 v2.00; nothing compared')
        return 0
    base = EE(elf)
    tables = tables_for(elf)
    for name, suite in (('helpers', suite_helpers), ('limit', suite_limit), ('handlers', suite_handlers),
                        ('missions', suite_missions), ('cm1', suite_cm1)):
        if OPTIONS['filter'] is None or OPTIONS['filter'] in name or name == 'handlers':
            if name == 'handlers' and OPTIONS['filter'] is not None and OPTIONS['filter'] not in name \
                    and not any(OPTIONS['filter'] in n for n in R.HANDLERS):
                continue
            suite(elf, base, tables)
    failed = [n for n, ok in RESULTS if not ok]
    print('%d suites, %d failed (seed %d, %d cases)' % (len(RESULTS), len(failed), OPTIONS['seed'], OPTIONS['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
