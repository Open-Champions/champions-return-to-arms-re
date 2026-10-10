#!/usr/bin/env python3
"""difftest_combat.py - compare tools/ref_combat.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the random samples
    --seed N  seed of the random inputs (default 20973); runs with one seed repeat exactly
    -k TEXT   run only the property groups whose name contains TEXT
    -v        print up to three failing inputs per property

Every property prints one line: PASS or FAIL, its name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL function is executed by tools/ee_emu.py (an instruction interpreter, not a
    console) on records this script builds in the interpreter's memory; the same inputs go
    through the model; outputs must be equal.  Floats are compared as 32-bit patterns, so
    "bit for bit" means: identical under the interpreter's floating-point model.  The
    default model ('ps2') gets the full sample; float-heavy groups are repeated on a smaller
    sample under the other adder models and the multiplier-bias and divide-rounding
    switches, the model switched the same way.  Agreement under all of them shows the model
    performs the same operations in the same order; it does NOT show that either matches a
    real console in the last bit (docs/issues/dynamic-tests.md).

What runs for real and what is stubbed
    A function runs for real only if it is on a list in this file or lies in the C library
    (0x3a5000-0x3c0000); a call to anything else stops the case as an error, so nothing is
    stubbed by accident.  Stubbed: sounds, particles, text formatting, the pool allocator
    (the test decides whether it has a block), handle bookkeeping, and every virtual call
    (take-damage, type-info getters, Skill statistics, skill cast, stun, "is enemy", model
    lookup), which are recording stubs that return what the test chose.  Object and spell
    constructors run for real, so their draw from the shared seed is executed code.

Integer division by zero (an elemental range with v2 = v1 - 1) does not trap on the console
and its result is not established; the interpreter is told to continue with the values the
R5900 is reported to leave (div_zero = 'r5900') and the model follows the same report.
Those cases are counted separately in the output.
"""
import hashlib
import os
import random
import struct
import sys
import time
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_combat as R                          # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF

FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-36s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + str(line)[:600])
    sys.stdout.flush()


def scaled(count):
    return max(count // 10, 20) if OPTIONS['quick'] else count


class Tally:
    """Counts cases and mismatches per property and keeps the first examples."""

    def __init__(self):
        self.count, self.bad, self.examples, self.order = {}, {}, {}, []

    def check(self, name, ok, example=None):
        if name not in self.count:
            self.count[name], self.bad[name], self.examples[name] = 0, 0, []
            self.order.append(name)
        self.count[name] += 1
        if not ok:
            self.bad[name] += 1
            if len(self.examples[name]) < 3:
                self.examples[name].append(example() if callable(example) else example)
        return ok

    def flush(self, texts):
        for name in self.order:
            report(name, self.bad[name], self.count[name], texts.get(name, ''), self.examples[name])


# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
TYPEINFO = {'Innoruuk': 0x3CB1A0, 'BloodLust': 0x3D0A00, 'SpiritShield': 0x3D19F0,
            'FrostArmor': 0x3D1D70, 'DiseaseEffect': 0x3CDD40, 'UndeadShield': 0x3CF3AC,
            'SecondaryUndeadShield': 0x3CF3FC, 'Retribution': 0x3D18A0, 'CriticalHit': 0x3CF000,
            'AncestralCall': 0x3CE9BC, 'GiantGrowth': 0x3D0DA8}
FAKE_CLASSES = ('Creature', 'Other', 'Third')
REAL = set(TYPEINFO.values()) | {
    0x3C2608, 0x3C7E10, 0x3C2830,                # base-class type-info getters
    0x1E8230, 0x3047B0, 0x315888, 0x318264, 0x2DDCCC, 0x2E76C4, 0x308C10, 0x308CB4, 0x314790,
    0x118950, 0x11A710, 0x1BF330, 0x166630, 0x1666E0,
    0x202158, 0x202DE8, 0x201BD8, 0x2D5594, 0x294014, 0x150E48, 0x14CB10, 0x1509D0, 0x16A964,
    0x10A620, 0x10D940, 0x1D3150, 0x1B6458, 0x1B5790, 0x103EC8, 0x103F88, 0x104100, 0x1046B4,
    0x1BED48, 0x308A7C, 0x2F8E78, 0x1B7158, 0x2DBCAC, 0x304B54, 0x314A78, 0x2E1470, 0x2E13D0,
    0x2E1420, 0x2FE49C, 0x30481C, 0x3098C8, 0x1AC7A8}

G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
G_SEED, G_COSMETIC = 0x404464, 0x404460
G_SKILL_TABLE = 0x41B170
STUB_BASE = 0x00F00000


class Unexpected(Exception):
    pass


class Policy:
    """emu.follow: the listed functions and the C library run for real, explicit stubs are
    stubs, and a call to anything else is an error instead of a silent stub."""

    def __init__(self, emu):
        self.emu = emu

    def __contains__(self, target):
        if target in REAL or LIB_LO <= target < LIB_HI or target in self.emu.hooks:
            return True
        raise Unexpected('call to 0x%08x, which is neither listed as real nor stubbed' % target)


def raw_of(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class Rig:
    """One interpreter, its stubs, and an arena for the records of one case."""
    ARENA = 0x60000

    def __init__(self, elf, config=FPU_CONFIGS[0]):
        model, bias, nearest = config
        emu = self.emu = EE(elf, fpu_model=model)
        emu.fpu_mul_bias, emu.fpu_div_nearest = bias, nearest
        emu.div_zero = 'r5900'
        emu.record_calls = False
        emu.record_writes = True
        emu.follow = Policy(emu)
        R.set_fpu(model, bias, nearest)
        self.sp = emu.r[29] - 0x400
        self.mem = emu.mem
        self.events = []
        self.scenario = None
        self.next_stub = STUB_BASE
        self.arena = emu.alloc(self.ARENA)
        self.cursor = self.used = self.arena
        self.addr = {}                      # id(model record) -> address
        self.back = {}                      # address -> model record
        self.pending = {}
        self.sparks = 0
        self.pool_blocks = []
        self._fixed()
        self._stubs()

    # ---- persistent structures -----------------------------------------------------
    def stub(self, function, ret=0):
        addr = self.next_stub
        self.next_stub += 0x10
        self.emu.stub(addr, ret=ret, function=function)
        return addr

    def _fixed(self):
        emu, mem = self.emu, self.mem
        self.descriptor = {}
        for name, getter in TYPEINFO.items():
            self.descriptor[name] = self.call(getter) & M32
        template = self.descriptor['Innoruuk']
        for name in FAKE_CLASSES:
            block = emu.alloc(0x40)
            mem.write(block + 0x10, ('7_test_%s' % name).encode() + b'\0')
            for off in (4, 8, 12):
                mem.w32(block + off, mem.u32(template + off))
            mem.w32(block, block + 0x10)
            self.descriptor[name] = block
        self.getter = {name: self.stub(None, ret=addr) for name, addr in self.descriptor.items()}
        take = self.stub(self.v_take_damage)
        model_of = self.stub(lambda e: e.r[4] & M32, ret=None)
        enemy = self.stub(self.v_enemy)
        stun = self.stub(self.v_stun)
        self.obj_vtable = {}
        for name in FAKE_CLASSES + ('Innoruuk',):
            table = emu.alloc(0x100)
            mem.w32(table + 4, self.getter[name])
            for off, target in ((0x10, take), (0x80, model_of), (0xB0, enemy), (0xF0, stun)):
                mem.w16(table + off, 0)
                mem.w32(table + off + 4, target)
            self.obj_vtable[name] = table
        self.spell_vtable = {}
        for name in TYPEINFO:
            table = emu.alloc(0x20)
            mem.w32(table + 4, self.getter[name])
            self.spell_vtable[name] = table
        table = emu.alloc(0x80)
        for off, function in ((0x10, self.v_cast), (0x50, self.v_stat), (0x60, self.v_stat_for),
                              (0x70, self.v_adjust)):
            mem.w16(table + off, 0)
            mem.w32(table + off + 4, self.stub(function))
        self.skills = emu.alloc(102 * 0x68)
        for index in range(102):
            mem.w32(self.skills + index * 0x68 + 0x60, table)
            mem.w32(G_SKILL_TABLE + 4 * index, self.skills + index * 0x68)
        self.emu.reset_log()
        emu.call(0x1AC7A8, sp=self.sp)      # classSkills_init: fills the run-time passive tables
        emu.reset_log()

    def _stubs(self):
        emu = self.emu
        ev = self.events.append
        emu.stub(0x17365C, function=lambda e: e.r[5] & M32)                         # res_find
        emu.stub(0x214230, function=lambda e: ev(('fx', e.r[4] & M32, self.tag(e.r[5]))))
        emu.stub(0x214428, function=lambda e: ev(('fx_at', e.r[4] & M32)))
        emu.stub(0x1E7E40, function=lambda e: ev(('hit_sound', e.f[12], e.r[4] & M32, s32(e.r[6]),
                                                  e.r[7] & M32, e.r[8] & M32)))
        emu.stub(0x18F3F8, function=self.s_particle)
        emu.stub(0x3B7EF0, function=self.s_sprintf)
        emu.stub(0x14FDB8, function=self.s_pool)
        emu.stub(0x1B7BA8, function=lambda e: ev(('voice', s32(e.r[4]), s32(e.r[5]))))
        emu.stub(0x1EF270, function=lambda e: ev(('fx_spawn', s32(e.r[4]))))
        emu.stub(0x3B3338, function=self.s_fail)                                    # throw bad_typeid
        emu.stub(0x1A1698, function=self.s_handle_clear)
        emu.stub(0x1A1738, function=self.s_handle_link)
        emu.stub(0x11A838, function=lambda e: ev(('add_spell', self.tag(e.r[4]), bool(e.r[5] & M32))))
        emu.stub(0x2EAEC0, function=lambda e: ev(('undead_shield', 1, self.tag(e.r[5]), self.tag(e.r[6]), s32(e.r[7]))))
        emu.stub(0x2EB5B4, function=lambda e: ev(('undead_shield', 2, self.tag(e.r[5]), self.tag(e.r[6]), s32(e.r[7]))))
        emu.stub(0x1799C8, function=lambda e: self.back[e.r[4] & M32].model_points)
        emu.stub(0x178E18)                                                          # model sample point
        emu.stub(0x14C880, function=self.s_prop_int)
        emu.stub(0x14F4C0, function=self.s_prop_str)
        emu.stub(0x14F248)                                                          # run-list link
        emu.stub(0x148AF8)                                                          # light link
        emu.stub(0x13E150, function=lambda e: self.scenario.get('local', 0))        # net_isLocalSlot
        emu.stub(0x173C84)                                                          # text lookup
        emu.stub(0x1D92A0, function=lambda e: ev(('level_up', s32(e.r[6]),
                                                  self.mem.s8(G_PLAYERS + s32(e.r[6]) * REC_SIZE + 0x59))))
        emu.hook(0x202158, lambda e: ev(('text', int(self.mem.cstr(e.r[6] & M32)), s32(e.r[7]), s32(e.r[8]),
                                         s32(e.r[9]), s32(e.r[10]))))
        emu.hook(0x202DE8, lambda e: ev(('gas', s32(e.r[7]), s32(e.r[10]), self.tag(e.r[9]))))
        emu.hook(0x2D5594, lambda e: ev(('disease', s32(e.r[5]), self.tag(e.r[7]), self.tag(e.r[8]))))
        emu.hook(0x201BD8, lambda e: ev(('light',)))
        emu.hook(0x294014, lambda e: ev(('orb', self.tag(e.r[7]))))

    # ---- stubs -----------------------------------------------------------------------
    def tag(self, addr):
        addr &= M32
        if addr == 0:
            return None
        record = self.back.get(addr)
        return record.tag if record is not None else '0x%x' % addr

    def s_fail(self, emu):
        raise Unexpected('bad_typeid thrown (null object in a typeid test)')

    def s_particle(self, emu):
        if 0x1E8230 <= (emu.r[31] & M32) < 0x1EACB8:
            self.sparks += 1
            if self.sparks == 50:
                self.sparks = 0
                self.events.append(('sparks', 50))

    def s_sprintf(self, emu):
        self.mem.write(emu.r[4] & M32, str(s32(emu.r[6])).encode() + b'\0')

    def s_pool(self, emu):
        size = s32(emu.r[4])
        ok = self.scenario['pool'](size)
        self.events.append(('pool', size, ok))
        if not ok:
            return 0
        block = self.take(size)
        self.pool_blocks.append((block, size))
        return block

    def s_handle_clear(self, emu):
        head = emu.r[4] & M32
        owner = self.back.get(head - 0x360)
        if owner is not None:
            event = ['status_source', owner.tag, None]
            self.events.append(event)
            self.pending[head] = event

    def s_handle_link(self, emu):
        head = emu.r[4] & M32
        if head in self.pending:
            self.pending[head][2] = self.tag(emu.r[5])

    def s_prop_int(self, emu):
        key = self.mem.cstr(emu.r[5] & M32).lower()
        return self.scenario.get('props', {}).get(key, 0)

    def s_prop_str(self, emu):
        return self.scenario.get('name_prop', 0)

    def v_take_damage(self, emu):
        self.events.append(('take_damage', self.tag(emu.r[4]), emu.f[12], self.tag(emu.r[5]), emu.r[6] & M32))

    def v_enemy(self, emu):
        return self.scenario['world'].enemy_fn(self.back[emu.r[4] & M32], self.back[emu.r[5] & M32])

    def v_stun(self, emu):
        self.events.append(('stun', self.tag(emu.r[4]), s32(emu.r[5])))

    def _skill(self, emu):
        return ((emu.r[4] & M32) - self.skills) // 0x68

    def v_cast(self, emu):
        self.events.append(('cast', self._skill(emu), s32(emu.r[5]), self.tag(emu.r[6]), R.s16(emu.r[8])))

    def v_stat(self, emu):
        return self.scenario['world'].stat_fn(self._skill(emu), s32(emu.r[5]), s32(emu.r[6])) & M32

    def v_stat_for(self, emu):
        caster = self.back.get(emu.r[7] & M32)
        return self.scenario['world'].stat_for_fn(self._skill(emu), s32(emu.r[5]), s32(emu.r[6]), caster,
                                                  s32(emu.r[8])) & M32

    def v_adjust(self, emu):
        return self.scenario['world'].adjust_fn(self._skill(emu), s32(emu.r[5]), s32(emu.r[6])) & M32

    # ---- running ---------------------------------------------------------------------
    def call(self, addr, *args, fargs=(), max_steps=3000000):
        emu = self.emu
        for index, value in enumerate(fargs):
            emu.f[12 + index] = value & M32
        return emu.call(addr, *args, sp=self.sp, max_steps=max_steps)

    def begin(self, scenario):
        """Start a case: clear the arena that the previous case used and the logs."""
        if self.used > self.arena:
            self.mem.write(self.arena, bytes(self.used - self.arena))
        self.cursor = self.used = self.arena
        self.addr, self.back, self.pending = {}, {}, {}
        self.pool_blocks = []
        self.sparks = 0
        del self.events[:]
        self.scenario = scenario
        self.emu.reset_log()

    def take(self, size):
        addr = (self.cursor + 15) & -16
        self.cursor = addr + size
        if self.cursor > self.arena + self.ARENA:
            raise EmuError('test arena exhausted')
        self.used = max(self.used, self.cursor)
        return addr

    def place(self, record, size):
        addr = self.take(size)
        self.addr[id(record)] = addr
        self.back[addr] = record
        return addr

    def cstring(self, text):
        addr = self.take(len(text) + 1)
        self.mem.write(addr, text.encode('latin1') + b'\0')
        return addr

    # ---- records -> memory -----------------------------------------------------------
    def put_objects(self, objects):
        mem = self.mem
        for obj in objects:
            self.place(obj, 0x5A0)
        for obj in objects:
            a = self.addr[id(obj)]
            mem.w32(a + 0x0C, obj.flags)
            for i in range(3):
                mem.w32(a + 0x10 + 4 * i, obj.pos[i])
            mem.w16(a + 0x38, obj.facing)
            mem.w32(a + 0x44, obj.own_seed)
            mem.w32(a + 0x48, self.obj_vtable[obj.cls])
            if obj.owner_link:
                link = self.take(0x10)
                mem.w32(link + 0x0C, self.addr[id(obj.owner)])
                mem.w32(a + 0x4C, link)
            for i in range(5):
                mem.w32(a + 0x5C + 4 * i, obj.res[i])
            for i in range(8):
                mem.w16(a + 0x90 + 2 * i, obj.flash[i])
            mem.w64(a + 0xA8, obj.cflags)
            mem.w8(a + 0xB4, obj.kind)
            mem.w32(a + 0xCC, obj.dot)
            mem.w32(a + 0xD8, obj.exp_value)
            mem.w32(a + 0xDC, obj.field_dc)
            mem.w16(a + 0xE4, obj.armor)
            mem.w32(a + 0xF0, obj.stamp_f0)
            mem.w32(a + 0x228, obj.hp)
            mem.w32(a + 0x22C, obj.max_hp)
            if obj.last_attacker is not None:
                link = self.take(0x10)
                mem.w32(link + 0x0C, self.addr[id(obj.last_attacker)])
                mem.w32(a + 0x2E4, link)
            for i in range(5):
                mem.w32(a + 0x340 + 4 * i, obj.status[i])
            mem.w16(a + 0x358, obj.poison_a)
            mem.w16(a + 0x35A, obj.poison_b)
            head = a + 0x364
            for spell in obj.spells:
                s = self.place(spell, 0x40)
                mem.w8(s, spell.level)
                mem.w32(s + 8, self.skills + spell.skill * 0x68)
                mem.w32(s + 0x0C, self.addr[id(spell.owner)])
                mem.w32(s + 0x14, self.spell_vtable[spell.kind])
                mem.w32(s + 0x18, spell.f18)
                mem.w32(s + 0x1C, spell.f1c)
                mem.w32(s + 0x20, spell.f20)
                mem.w32(s + 0x2C, spell.f2c)
                node = self.take(0x10)
                mem.w32(node + 0x0C, s)
                mem.w32(head, node)
                head = node
            mem.w32(a + 0x374, obj.counter2)
            mem.w32(a + 0x37C, obj.counter4)
            mem.w32(a + 0x398, obj.counter11)
            mem.w32(a + 0x39C, obj.counter12)
            mem.w32(a + 0x3C8, obj.slot)
            mem.w32(a + 0x3E0, obj.innoruuk_immune)
            mem.w32(a + 0x458, obj.attack_start)
            mem.w32(a + 0x45C, obj.attack_chain)
            for i in range(4):
                mem.w8(a + 0x474 + i, obj.bonus[i])
            mem.w32(a + 0x58C, obj.state)

    def get_object(self, obj):
        mem, a = self.mem, self.addr[id(obj)]
        out = {'flags': mem.u32(a + 0x0C), 'pos': [mem.u32(a + 0x10 + 4 * i) for i in range(3)],
               'res': [mem.u32(a + 0x5C + 4 * i) for i in range(5)],
               'flash': [mem.u16(a + 0x90 + 2 * i) for i in range(8)],
               'cflags': mem.u64(a + 0xA8), 'dot': mem.u32(a + 0xCC), 'armor': mem.s16(a + 0xE4),
               'stamp_f0': mem.u32(a + 0xF0), 'hp': mem.u32(a + 0x228), 'max_hp': mem.u32(a + 0x22C),
               'status': [mem.u32(a + 0x340 + 4 * i) for i in range(5)],
               'poison_a': mem.s16(a + 0x358), 'poison_b': mem.s16(a + 0x35A),
               'counter11': mem.u32(a + 0x398), 'counter12': mem.u32(a + 0x39C),
               'bonus': [mem.u8(a + 0x474 + i) for i in range(4)], 'own_seed': mem.u32(a + 0x44),
               'exp_value': mem.u32(a + 0xD8)}
        return out

    @staticmethod
    def model_object(obj):
        return {'flags': obj.flags & M32, 'pos': list(obj.pos), 'res': list(obj.res),
                'flash': [v & 0xFFFF for v in obj.flash], 'cflags': obj.cflags, 'dot': obj.dot,
                'armor': R.s16(obj.armor), 'stamp_f0': obj.stamp_f0 & M32, 'hp': obj.hp,
                'max_hp': obj.max_hp, 'status': list(obj.status), 'poison_a': R.s16(obj.poison_a),
                'poison_b': R.s16(obj.poison_b), 'counter11': obj.counter11 & M32,
                'counter12': obj.counter12 & M32, 'bonus': [v & 0xFF for v in obj.bonus],
                'own_seed': obj.own_seed & M32, 'exp_value': obj.exp_value}

    def get_spell(self, spell):
        mem, s = self.mem, self.addr[id(spell)]
        return (mem.u32(s + 0x18), mem.u32(s + 0x1C), mem.u32(s + 0x20), mem.u32(s + 0x2C))

    def put_item(self, item, addr=None):
        mem = self.mem
        if addr is None:
            addr = self.take(0x48)
        self.addr[id(item)] = addr
        defn = item.defn
        if id(defn) not in self.addr:
            d = self.place(defn, 0x40)
            mem.w32(d, self.cstring(defn.name))
            mem.w16(d + 0x0E, defn.dmg_min)
            mem.w16(d + 0x10, defn.dmg_max)
            mem.w16(d + 0x18, defn.armor)
            mem.w16(d + 0x1A, defn.attack)
            mem.w8(d + 0x1D, defn.category)
            mem.w8(d + 0x1E, defn.subtype)
            mem.w32(d + 0x20, defn.dmg_type)
            mem.w64(d + 0x28, defn.flags)
        mem.w32(addr, self.addr[id(defn)])
        mem.w16(addr + 4, item.count)
        mem.w64(addr + 8, item.flags)
        for i, slot in enumerate(item.mods):
            for j in range(4):
                mem.w16(addr + 0x24 + 8 * i + 2 * j, slot[j])
        return addr

    def put_desc(self, desc):
        addr = self.take(0x48)
        for i, slot in enumerate(desc):
            for j in range(4):
                self.mem.w16(addr + 0x24 + 8 * i + 2 * j, slot[j])
        return addr

    def put_world(self, w):
        mem = self.mem
        mem.w32(G_SEED, w.seed.state)
        mem.w32(G_COSMETIC, w.cosmetic.state)
        mem.w32(0x44FDCC, w.frame)
        mem.w32(0x4F711C, w.pvp_a)
        mem.w8(0x44FCD0, w.cutscene)
        mem.w32(0x44FCF8, w.numbers_option)
        mem.w8(0x402791, w.network_mode)
        mem.w32(0x4F714C, w.monster_level)
        mem.w32(0x44F048, w.focus[0])
        mem.w32(0x44F04C, w.focus[1])
        mem.write(0x4F7158, bytes(w.music))
        mem.w16(0x4F717A, w.music_index)
        mem.w32(0x4D8AE0, w.num_players)
        mem.w32(0x4F8420, len(w.alive))
        for i in range(4):
            mem.w32(0x4F8440 + 4 * i, w.alive[i] if i < len(w.alive) else 0)
        mem.w32(0x4F713C, w.medal_mission)
        mem.w32(0x4F719C, w.difficulty)
        mem.write(0x44FE18, w.level_name.encode('latin1')[:30] + b'\0')
        mem.w32(0x4D8AE8, w.load_cheat)
        for slot in range(4):
            self.put_record(slot, w.players[slot] if slot < len(w.players) else R.PlayerRec())

    def put_record(self, slot, rec):
        mem, a = self.mem, G_PLAYERS + slot * REC_SIZE
        mem.w32(a + 0x50, rec.cls)
        mem.w8(a + 0x58, rec.level58)
        mem.w8(a + 0x59, rec.level59)
        mem.w32(a + 0x5C, rec.exp)
        for i in range(4):
            mem.w32(a + 0x78 + 4 * i, rec.base[i])
            mem.w32(a + 0x90 + 4 * i, rec.eff[i])
        for off, value in ((0xAC, rec.hp), (0xB0, rec.max_hp), (0xC0, rec.mana), (0xC4, rec.max_mana),
                           (0xCC, rec.attack), (0xD0, rec.dmg_min), (0xD4, rec.dmg_max),
                           (0xDC, rec.stagger), (0xE8, rec.skill_points), (0x124, rec.load_limit)):
            mem.w32(a + off, value)
        mem.w8(a + 0xEC, rec.stat_points)
        mem.write(a + 0xEF, bytes(v & 0xFF for v in rec.passives))
        for i in range(64):
            item = rec.bag2[i] if i < len(rec.bag2) else None
            if item is None:
                mem.w32(a + 0x2540 + 0x48 * i, 0)
            else:
                self.put_item(item, a + 0x2540 + 0x48 * i)
        mem.w32(a + 0x43D8, self.addr[id(rec.obj)] if rec.obj is not None else 0)
        sets = list(rec.equip) + list(rec.weapon_sets) + [rec.second_weapon]
        for item in sets:
            if item is not None and id(item) not in self.addr:
                self.put_item(item)
        for i in range(17):
            mem.w32(a + 0x43F0 + 4 * i, self.addr[id(rec.equip[i])] if rec.equip[i] is not None else 0)
        for i in range(2):
            item = rec.weapon_sets[i]
            mem.w32(a + 0x4434 + 4 * i, self.addr[id(item)] if item is not None else 0)
        mem.w32(a + 0x443C, self.addr[id(rec.second_weapon)] if rec.second_weapon is not None else 0)
        mem.w8(a + 0x4A7C, rec.active_set)
        for i, (ident, rank) in enumerate(rec.skills):
            mem.w16(a + 0x4B08 + 4 * i, ident)
            mem.w16(a + 0x4B0A + 4 * i, rank)
        mem.w16(a + 0x4B08 + 4 * len(rec.skills), 0xFFFF)

    def get_record(self, slot):
        mem, a = self.mem, G_PLAYERS + slot * REC_SIZE
        return {'level59': mem.s8(a + 0x59), 'exp': mem.s32(a + 0x5C),
                'eff': [mem.s32(a + 0x90 + 4 * i) for i in range(4)],
                'hp': mem.u32(a + 0xAC), 'max_hp': mem.u32(a + 0xB0), 'mana': mem.u32(a + 0xC0),
                'max_mana': mem.u32(a + 0xC4), 'attack': mem.s32(a + 0xCC), 'dmg_min': mem.s32(a + 0xD0),
                'dmg_max': mem.s32(a + 0xD4), 'stagger': mem.u32(a + 0xDC),
                'skill_points': mem.s32(a + 0xE8), 'stat_points': mem.s8(a + 0xEC),
                'load_limit': mem.u32(a + 0x124)}

    @staticmethod
    def model_record(rec):
        return {'level59': R.s8(rec.level59), 'exp': R.s32(rec.exp), 'eff': [R.s32(v) for v in rec.eff],
                'hp': rec.hp, 'max_hp': rec.max_hp, 'mana': rec.mana, 'max_mana': rec.max_mana,
                'attack': R.s32(rec.attack), 'dmg_min': R.s32(rec.dmg_min), 'dmg_max': R.s32(rec.dmg_max),
                'stagger': rec.stagger, 'skill_points': R.s32(rec.skill_points),
                'stat_points': R.s8(rec.stat_points), 'load_limit': rec.load_limit}

    # ---- what the original wrote -------------------------------------------------------
    def seed_draws(self):
        return [value >> 16 for _pc, addr, size, value in self.emu.writes if addr == G_SEED and size == 4]

    def stray_writes(self, objects, spells, slots):
        """Stores outside the fields the model accounts for (and outside pool blocks)."""
        allowed = [(G_SEED, 4), (G_COSMETIC, 4), (0x4F7158, 32)]
        for obj in objects:
            a = self.addr[id(obj)]
            allowed += [(a + 0x44, 4), (a + 0x5C, 20), (a + 0x90, 16), (a + 0xCC, 4), (a + 0xD0, 12),
                        (a + 0xE4, 2), (a + 0xF0, 4), (a + 0x228, 8), (a + 0x340, 20), (a + 0x358, 4),
                        (a + 0x398, 4), (a + 0x474, 4), (a + 0x0C, 4), (a + 0x2DC, 4)]
        for spell in spells:
            allowed += [(self.addr[id(spell)] + 0x18, 4), (self.addr[id(spell)] + 0x20, 4)]
        for slot in slots:
            a = G_PLAYERS + slot * REC_SIZE
            allowed += [(a + 0x59, 1), (a + 0x5C, 4), (a + 0x90, 16), (a + 0xAC, 8), (a + 0xC0, 8),
                        (a + 0xCC, 12), (a + 0xDC, 4), (a + 0xE8, 5), (a + 0x124, 4)]
        allowed += self.pool_blocks
        stray = []
        for pc, addr, size, value in self.emu.writes:
            if not any(base <= addr and addr + size <= base + length for base, length in allowed):
                stray.append('0x%08x (%d bytes) by pc 0x%08x' % (addr, size, pc))
        return stray


def s32(value):
    value &= M32
    return value - 0x100000000 if value & 0x80000000 else value


# ---------------------------------------------------------------------------------------
# Input generation
# ---------------------------------------------------------------------------------------
def rf(rng, low, high):
    return R.f32(rng.uniform(low, high))


def hash3(a, b, c, salt):
    return (((a * 7919 + b * 104729 + (c & M32) * 31 + salt) * 2654435761) & M32) >> 8


def make_world(rng):
    w = R.World(seed=rng.getrandbits(32), cosmetic=rng.getrandbits(32))
    salt = rng.getrandbits(24)
    mod = rng.choice((8, 40, 101, 128, 128))
    w.stat_fn = lambda skill, stat, level: hash3(skill, stat, level, salt) % mod
    w.stat_for_fn = lambda skill, stat, level, caster, cap: hash3(
        skill, stat + 16 * (2 if caster is None else bool(caster.flags & 0x40)) + 64 * (cap & 0xFF),
        level, salt + 1) % mod
    if rng.random() < 0.25:
        w.adjust_fn = lambda skill, level, n: min(level, n)
    w.enemy_fn = lambda obj, other: hash3(len(obj.tag), len(other.tag), 0, salt) & 1
    return w


def gen_desc(rng):
    if rng.random() < 0.2:
        return None
    slots = []
    for _ in range(4):
        roll = rng.random()
        if roll < 0.35:
            kind = -1
        elif roll < 0.95:
            kind = rng.choice((0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F, 0x20, 0x21,
                               0x22, 0x26, 0x29))
        else:
            kind = rng.choice((0, 7, 0x1E, 0x23, 0x2A))

        def after(base):
            mode = rng.random()
            if mode < 0.55:
                return base + rng.randrange(0, 40)
            if mode < 0.78:
                return base - rng.randrange(2, 30)          # upper end below the lower end
            if mode < 0.88:
                return base - 1                             # zero divisor
            return rng.randrange(-50, 200)

        v1 = rng.choice((0, rng.randrange(1, 60), rng.randrange(1, 130), -rng.randrange(1, 20)))
        if kind == 0x29:
            v1 = rng.randrange(1, 102)
        v2 = after(v1) if kind not in (0x29, 0x21) else rng.choice((0, rng.randrange(1, 120)))
        v3 = after(v2)
        slots.append((kind, v1, v2, v3))
    return slots


SPELL_SKILL = {'BloodLust': 60, 'SpiritShield': 61, 'FrostArmor': 62, 'DiseaseEffect': 29,
               'UndeadShield': 63, 'SecondaryUndeadShield': 64, 'Retribution': 65, 'CriticalHit': 66,
               'AncestralCall': 51, 'GiantGrowth': 67}


def new_spell(rng, kind, owner):
    return R.Spell(kind=kind, skill=SPELL_SKILL[kind], level=rng.randrange(1, 21), owner=owner,
                   f18=rng.choice((0, 0, 1)), f1c=rf(rng, 0, 130), f20=rf(rng, 0, 10),
                   f2c=rng.choice((0, 1, 1)))


def gen_damage(rng):
    w = make_world(rng)
    w.frame = rng.choice((rng.randrange(1 << 20), rng.randrange(1 << 14) * 32))
    w.pvp_a = 1 if rng.random() < 0.12 else 0
    w.cutscene = 1 if rng.random() < 0.05 else 0
    w.numbers_option = 0 if rng.random() < 0.3 else 1
    w.network_mode = 1 if rng.random() < 0.3 else 0
    w.monster_level = rf(rng, 0, 150)
    w.focus = [rf(rng, -500, 500), rf(rng, -500, 500)]
    w.players = [R.PlayerRec() for _ in range(4)]
    objects = []
    free_slots = [0, 1, 2, 3]
    rng.shuffle(free_slots)

    def creature(tag, player):
        obj = R.Obj(tag=tag, flags=0x20 | (0x40 if player else 0) | (8 if rng.random() < 0.05 else 0))
        obj.pos = [rf(rng, -400, 400), rf(rng, -400, 400), rf(rng, -50, 50)]
        obj.facing = rng.randrange(0x10000)
        obj.cls = rng.choice(('Creature', 'Creature', 'Other'))
        obj.res = [rng.choice((R.ZERO, R.ZERO, rf(rng, -0.5, 1.5), R.ONE, rf(rng, 0, 1))) for _ in range(5)]
        obj.cflags = 0
        for bit, chance in ((2, .1), (4, .1), (8, .1), (0x10, .1), (0x20, .1), (0x40, .1), (0x80, .1),
                            (0x100, .1), (0x200, .2), (0x800, .03), (0x100000, .06), (1 << 45, .25)):
            if rng.random() < chance:
                obj.cflags |= bit
        obj.kind = rng.choice((0, 0, 0x10, 0x10, 0x12, 5))
        obj.dot = rng.choice((R.ZERO, rf(rng, 0, 3), rf(rng, 0, 200)))
        obj.armor = rng.choice((0, 0, rng.randrange(1, 60), rng.randrange(1, 600), rng.randrange(1, 4000),
                                -rng.randrange(1, 50)))
        obj.hp = rng.choice((R.ZERO, rf(rng, 1, 400), rf(rng, 1, 30000), rf(rng, -50, 0)))
        obj.status = [rng.choice((R.ZERO, rf(rng, 0, 70), rf(rng, -2, 0))) for _ in range(5)]
        obj.state = rng.choice((0, 1, 2, 8, 0xB))
        obj.model_points = rng.choice((0, 3, 17, 240))
        obj.boss_rank = rng.choice((0, 0, 1, 2))
        if player:
            obj.slot = free_slots.pop()
            rec = w.players[obj.slot]
            rec.obj = obj
            rec.hp = rng.choice((R.ZERO, rf(rng, 1, 900)))
            rec.max_hp = rf(rng, 100, 1000)
            rec.skills = [(skill, rng.choice((0, 0, rng.randrange(1, 21))))
                          for skill in rng.sample((9, 0x21, 0x35, 0x40, 0x51, 0x52, 0x3B), 7)]
        objects.append(obj)
        return obj

    roll = rng.random()
    if roll < 0.08:
        victim = R.Obj(tag='victim', flags=rng.choice((0, 1, 0x40)), cls='Third',
                       pos=[rf(rng, -400, 400), rf(rng, -400, 400), R.ZERO])
        objects.append(victim)
    else:
        victim = creature('victim', roll < 0.38)
        if rng.random() < 0.03:
            victim.cls, victim.innoruuk_immune = 'Innoruuk', rng.choice((0, 1))
        for kind, chance in (('BloodLust', .12), ('SpiritShield', .12), ('FrostArmor', .12),
                             ('DiseaseEffect', .1), ('UndeadShield', .08), ('SecondaryUndeadShield', .08)):
            if rng.random() < chance:
                victim.spells = victim.spells + [new_spell(rng, kind, victim)]
        if rng.random() < 0.15:
            victim.counter12 = rng.randrange(1, 100)
    roll = rng.random()
    if roll < 0.1:
        attacker = None
    elif roll < 0.13:
        attacker = victim
    elif roll < 0.2:
        owner = R.Obj(tag='owner', flags=0x20, cls=rng.choice(('Creature', 'Other')))
        attacker = R.Obj(tag='missile', flags=0x80 | rng.choice((0, 0x20)), owner_link=rng.random() < 0.85,
                         owner=owner, cls='Third', pos=[rf(rng, -400, 400), rf(rng, -400, 400), R.ZERO])
        objects += [owner, attacker]
    else:
        attacker = creature('attacker', roll < 0.6)
        attacker.cflags = 0
        if rng.random() < 0.03:
            attacker.flags |= 0x20000
        if attacker.flags & 0x40:
            for kind, chance in (('Retribution', .2), ('CriticalHit', .5)):
                if rng.random() < chance:
                    attacker.spells = attacker.spells + [new_spell(rng, kind, attacker)]
        if not victim.spell('FrostArmor') and rng.random() < 0.08:
            attacker.spells = attacker.spells + [new_spell(rng, 'FrostArmor', attacker)]
        if (not victim.spell('FrostArmor') and victim.kind != 0x10 and attacker is not victim
                and rng.random() < 0.05):
            attacker.counter12 = 5              # reflection inside a nested hit, never mutual
    # other players, for the critical-hit aura
    while free_slots and rng.random() < 0.5:
        other = creature('ally%d' % len(free_slots), True)
        other.flags &= ~8
        if attacker is not None and rng.random() < 0.8:
            reach = rng.choice((30, 300, 1200))
            other.pos = [R.f32(R.to_float(attacker.pos[i]) + rng.uniform(-reach, reach)) for i in range(3)]
        if rng.random() < 0.7:
            other.spells = [new_spell(rng, 'CriticalHit', other)]
    w.num_players = 4
    w.alive = [slot for slot in range(4) if w.players[slot].obj is not None and rng.random() < 0.9]
    base = rng.choice((rf(rng, 0, 50), rf(rng, 0, 500), R.f32(float(rng.randrange(0, 200)))))
    roll = rng.random()
    if roll < 0.55:
        dmax = R.fadd(base, rf(rng, 0, 120))
    elif roll < 0.7:
        dmax = base
    elif roll < 0.8:
        dmax = R.fsub(base, R.ONE)                  # a span of exactly zero
    elif roll < 0.9:
        dmax = rf(rng, 0, 100)
    else:
        base, dmax = rf(rng, -30, 30), rf(rng, -30, 60)
    flags = 0
    for bit, chance in ((1, .3), (4, .2), (8, .2), (0x10, .1), (0x40, .15), (0x100, .2), (0x200, .15),
                        (0x400, .05), (0x4000, .2), (0x8000, .2), (0x20000, .3), (0x800000, .12),
                        (0x1000000, .1), (0x8000000, .04), (0x10000000, .15), (0x40000000, .12)):
        if rng.random() < chance:
            flags |= bit
    plan = [rng.random() < 0.9 for _ in range(64)]
    return {'world': w, 'objects': objects, 'victim': victim, 'attacker': attacker, 'min': base,
            'max': dmax, 'attack': rng.choice((100000, 100000, rng.randrange(0, 3000), rng.randrange(0, 300),
                                               -5, 100000000)),
            'flags': flags, 'desc': gen_desc(rng), 'no_crit': 1 if rng.random() < 0.15 else 0, 'plan': plan}


def pool_plan(plan):
    """Two independent readers of the same yes/no plan: one for the original, one for the model."""
    def reader():
        position = [0]

        def take(size):
            position[0] += 1
            return plan[(position[0] - 1) % len(plan)]
        return take
    return reader(), reader()


# ---------------------------------------------------------------------------------------
# Property groups
# ---------------------------------------------------------------------------------------
def group_fpu(elf, rng):
    """The model's Fpu against the interpreter's own float routines (no game code)."""
    tally = Tally()
    count = scaled(20000)
    for model, bias, nearest in FPU_CONFIGS:
        fpu = R.Fpu(model, bias, nearest)
        for _ in range(count // len(FPU_CONFIGS)):
            a = rng.getrandbits(32) if rng.random() < 0.5 else rf(rng, -1000, 1000)
            b = rng.getrandbits(32) if rng.random() < 0.5 else rf(rng, -1000, 1000)
            got = (fpu.add(a, b), fpu.sub(a, b), fpu.mul(a, b), fpu.div(a, b), fpu.sqrt(a),
                   fpu.from_int(a), R.Fpu.to_int(a) & M32, R.Fpu.compare(a, b))
            want = (ee_emu.fp_add(a, b, model), ee_emu.fp_sub(a, b, model),
                    ee_emu.fp_mul(a, b, model, None, bias), ee_emu.fp_div(a, b, model, None, nearest),
                    ee_emu.fp_sqrt(a, model, None, nearest), ee_emu.fp_from_int(a, model),
                    ee_emu.fp_to_int(a), ee_emu.fp_cmp(a, b))
            tally.check('fpu: model vs interpreter', got == want, lambda: (model, hex(a), hex(b), got, want))
    tally.flush({'fpu: model vs interpreter': 'add sub mul div sqrt int<->float compare, six configurations'})


def double_pattern(q):
    """IEEE pattern of a Fraction that is exactly representable, or None."""
    try:
        value = float(q)
    except OverflowError:
        return None
    if Fraction(value) != q:
        return None
    return struct.unpack('<Q', struct.pack('<d', value))[0]


def group_soft_double(elf, rng):
    rig = Rig(elf)
    tally = Tally()

    def pattern_to_fraction(bits):
        return Fraction(struct.unpack('<d', struct.pack('<Q', bits))[0])

    for _ in range(scaled(4000)):
        value = rng.choice((rng.randrange(-70000, 70000), rng.getrandbits(32)))
        got = rig.call(0x3AFA08, value)
        tally.check('soft double: int -> double', pattern_to_fraction(got) == R.dbl_from_int(value))
        raw = rng.getrandbits(32) if rng.random() < 0.5 else rf(rng, -5000, 5000)
        got = rig.call(0x3AEF58, fargs=(raw,))
        tally.check('soft double: single -> double', pattern_to_fraction(got) == R.dbl_from_single(raw),
                    lambda: hex(raw))
        a = R.dbl_from_single(rf(rng, -70000, 70000)) * Fraction(rng.choice((1, 1, 3, 1 << 30)), rng.choice((1, 7, 1 << 20)))
        b = R.dbl_from_single(rng.choice((rf(rng, -70000, 70000), rf(rng, -1e-3, 1e-3), rf(rng, -1e12, 1e12))))
        a, b = R._chop(a, 53), R._chop(b, 53)
        pa, pb = double_pattern(a), double_pattern(b)
        got = rig.call(0x3AF410, pa, pb)
        tally.check('soft double: add', pattern_to_fraction(got) == R.dbl_add(a, b), lambda: (a, b))
        got = rig.call(0x3AF4D0, pa, pb)
        tally.check('soft double: multiply', pattern_to_fraction(got) == R.dbl_mul(a, b), lambda: (a, b))
        x = Fraction(rng.randrange(0, 65536))
        y = R.dbl_from_single(rng.choice((rf(rng, 1, 600), R.f32(float(rng.randrange(1, 300))), rf(rng, -40, -1))))
        got = rig.call(0x3A5A38, double_pattern(x), double_pattern(y))
        tally.check('soft double: fmod', pattern_to_fraction(got) == R.dbl_fmod(x, y), lambda: (x, y))
        q = rng.choice((a, b, a * 1000003, Fraction(rng.getrandbits(53), 1 << rng.randrange(0, 60)),
                        Fraction(2) ** rng.randrange(120, 135) * 3, Fraction(1, 2 ** rng.randrange(120, 135))))
        q = R._chop(q, 53)
        rig.call(0x3AFB90, double_pattern(q))
        tally.check('soft double: double -> single', rig.emu.f[0] == R.dbl_to_single(q),
                    lambda: (q, hex(rig.emu.f[0]), hex(R.dbl_to_single(q))))
    got = rig.call(0x3A5A38, double_pattern(Fraction(5)), 0)
    rig.call(0x3AFB90, rig.call(0x3AF410, double_pattern(Fraction(-7)), got))
    tally.check('soft double: fmod', rig.emu.f[0] == R.dbl_to_single(R.dbl_add(Fraction(-7), R.dbl_fmod(Fraction(5), Fraction(0)))))
    text = 'exact value compared; add, multiply and double -> single truncate toward zero'
    tally.flush({name: text for name in tally.order})


POW_EXPONENTS = (0x3F599999, 0x3F800000, 0x3FA9374B, 0x3FB33333, 0x3F000000, 0x40000000,
                 0x3F733333, 0xBF800000, 0x40400000, 0xBF000000, 0x00000000, 0x40A00000)


def group_powf(elf, rng):
    for index, config in enumerate(FPU_CONFIGS):
        rig = Rig(elf, config)
        tally = Tally()
        label = '' if index == 0 else ' [%s%s%s]' % (config[0], ' bias' if config[1] else '', ' div-nearest' if config[2] else '')
        for _ in range(scaled(30000 if index == 0 else 3000)):
            roll = rng.random()
            if roll < 0.55:
                x = rf(rng, 0, rng.choice((2, 40, 2000, 1e6)))
            elif roll < 0.7:
                x = rf(rng, -50, 50)
            else:
                x = rng.getrandbits(32)
            y = rng.choice(POW_EXPONENTS) if rng.random() < 0.6 else rng.choice(
                (rf(rng, -4, 4), rf(rng, -40, 40), R.f32(float(rng.randrange(-9, 10))), rng.getrandbits(32)))
            rig.call(0x3A5AC8, fargs=(x, y))
            tally.check('powf' + label, rig.emu.f[0] == R.powf(x, y),
                        lambda: (hex(x), hex(y), hex(rig.emu.f[0]), hex(R.powf(x, y))))
            if index == 0:
                rig.call(0x3A84C0, fargs=(x,))
                tally.check('sqrtf', rig.emu.f[0] == R.sqrtf(x), lambda: hex(x))
                n = rng.choice((rng.randrange(-300, 300), rng.randrange(-70000, 70000)))
                rig.emu.f[12] = x
                rig.emu.call(0x3AA810, n, sp=rig.sp)
                tally.check('scalbnf', rig.emu.f[0] == R.scalbnf(x, n), lambda: (hex(x), n))
                angle = rng.getrandbits(32)
                rig.call(0x166630, angle)
                ok = rig.emu.f[0] == R.cos16(angle)
                rig.call(0x1666E0, angle)
                tally.check('cos16 / sin16', ok and rig.emu.f[0] == R.sin16(angle), lambda: hex(angle))
        tally.flush({name: 'result pattern, bit for bit' for name in tally.order})


def group_tables(elf, rng):
    rig = Rig(elf)
    tables = R.Tables.load(elf)
    tally = Tally()
    for cls in range(7):
        got = [rig.mem.u64(0x4EF510 + cls * 0xA88 + row * 0x38 + 0x28) for row in range(48)]
        tally.check('tables: passive masks', got == tables.passive_masks[cls], lambda: cls)
    tally.check('tables: experience curve', all(rig.mem.s32(0x41B558 + 4 * i) == tables.exp_table[i] for i in range(81))
                and rig.mem.u32(0x41B698) == tables.exp_table[80] & M32)
    tally.flush({'tables: passive masks': 'run-time table built by classSkills_init (executed) vs the model\'s reader',
                 'tables: experience curve': 'the model\'s reader vs interpreter memory'})
    return tables


def group_boss_rank(elf, rng, tables):
    rig = Rig(elf)
    tally = Tally()
    names = list(tables.boss_names) + [tables.boss_gate] + [p[0] for p in tables.boss_pairs] + list(tables.boss_last)
    props = [p[1] for p in tables.boss_pairs]
    for _ in range(scaled(3000)):
        roll = rng.random()
        name = None if roll < 0.08 else rng.choice(names) if roll < 0.75 else rng.choice(('gnoll', 'rat', names[0] + 'x', names[3][:-1], ''))
        if name and rng.random() < 0.5:
            name = ''.join(c.upper() if rng.random() < 0.5 else c.lower() for c in name)
        prop = rng.choice(props + ['', 'nobody'])
        if rng.random() < 0.3:
            prop = prop.upper()
        cflags = rng.getrandbits(8)
        creature = rng.random() < 0.9
        rig.begin({})
        obj = rig.take(0x400)
        rig.mem.w32(obj + 0x0C, 0x20 if creature else 0x1)
        rig.mem.w32(obj + 0x34, rig.cstring(name) if name is not None else 0)
        rig.mem.w64(obj + 0xA8, cflags)
        rig.scenario['name_prop'] = rig.cstring(prop)
        got = rig.call(0x10D940, obj) & M32
        want = R.boss_rank(tables, creature, name, prop, cflags)
        tally.check('boss rank', got == want, lambda: (name, prop, cflags, got, want))
    tally.flush({'boss rank': 'returned rank; the name property supplied by a stub'})


def group_monster(elf, rng, tables):
    for index, config in enumerate(FPU_CONFIGS):
        rig = Rig(elf, config)
        tally = Tally()
        label = '' if index == 0 else ' [%s%s%s]' % (config[0], ' bias' if config[1] else '', ' div-nearest' if config[2] else '')
        rig.emu.stub(0x10D940, function=lambda e: rig.scenario['rank'])
        for _ in range(scaled(6000 if index == 0 else 500)):
            w = make_world(rng)
            level_byte = rng.randrange(0, 60)
            w.monster_level = rng.choice((R.f32(float(level_byte + 2)), R.f32((level_byte + 2) * 0.75 + rng.choice((34, 61, 88, 115))),
                                          rf(rng, 0.5, 160), R.ONE, R.TWO, R.THREE))
            w.num_players = rng.choice((0, 1, 1, 2, 3, 4))
            w.medal_mission = rng.choice((0, 0, 0, 1))
            w.difficulty = rng.choice((1, 2, 3, 4, 5, 0, 6))
            w.level_name = rng.choice(tuple(tables.fixed_levels) + ('town', 'drunare', tables.fixed_levels[0].upper()))
            pct = tuple(rng.choice((R.ONE, rf(rng, 0.2, 5), rf(rng, 0.2, 5), R.f32(rng.randrange(20, 400) / 100.0),
                                    rf(rng, 0, 60), R.ZERO, rf(rng, -2, 0))) for _ in range(5))
            if rng.random() < 0.02:
                pct = tuple(rng.getrandbits(32) for _ in range(5))
            rank = rng.choice((0, 0, 1, 2))
            name = rng.choice((None, tables.no_scale_name, tables.no_scale_name.upper(), 'gnoll', 'rat'))
            roll_hp = rng.random() < 0.8
            dead = rng.random() < 0.1
            own = rng.getrandbits(32)
            rig.begin({'world': w, 'rank': rank, 'props': {'dead': 1 if dead else 0}})
            obj = R.Obj(tag='monster', flags=0x20, own_seed=own, hp=rf(rng, 1, 50), max_hp=rf(rng, 1, 50))
            rig.put_world(w)
            rig.put_objects([obj])
            addr = rig.addr[id(obj)]
            rig.mem.w32(addr + 0x34, rig.cstring(name) if name is not None else 0)
            rig.emu.reset_log()
            rig.call(0x10A620, addr, 1 if roll_hp else 0, fargs=pct)
            seed = R.Seed(own)
            out = R.monster_stats(tables, w, pct, rank, name, roll_hp, own_draw=seed.draw() if roll_hp else 0, dead=dead)
            mem = rig.mem
            got = (mem.u32(addr + 0x228), mem.u32(addr + 0x22C), mem.s16(addr + 0xE4), mem.s16(addr + 0xD0),
                   mem.s16(addr + 0xD2), mem.s16(addr + 0xD4), mem.u32(addr + 0xD8), mem.u32(addr + 0x44))
            want = (out['hp'] if out['hp'] is not None else obj.hp, out['max_hp'] if out['max_hp'] is not None else obj.max_hp,
                    out['armor'], out['dmg_low'], out['dmg_high'], out['attack'], out['exp_value'],
                    seed.state if roll_hp else own)
            tally.check('monster statistics' + label, got == want,
                        lambda: ([hex(p) for p in pct], hex(w.monster_level), w.num_players, rank, name, roll_hp,
                                 [hex(v & M32) for v in got], [hex(v & M32) for v in want]))
            if index == 0:
                tally.check('monster statistics: no other store', not rig.stray_writes([obj], [], []),
                            lambda: rig.stray_writes([obj], [], []))
        tally.flush({name: 'hp, max hp, armour, damage range, attack, experience value, own seed; bit for bit'
                     for name in tally.order})


FIGURINE_FLAG = 1 << 45


def gen_item(rng, tables, defs, weapon=None):
    if weapon is None:
        weapon = rng.random() < 0.4
    name = 'thing%d' % rng.randrange(1000)
    defn = R.ItemDef(name=name, dmg_min=rng.randrange(0, 80), dmg_max=rng.randrange(0, 160),
                     armor=rng.choice((0, rng.randrange(1, 300))), attack=rng.choice((0, rng.randrange(1, 400))),
                     category=0 if weapon else rng.choice((1, 1, 2)), subtype=rng.choice((0, 0, 1, 2, 3, 4, 6)),
                     dmg_type=rng.choice((1, 4, 8, 1, 8, 0)))
    mods = []
    for _ in range(4):
        code = rng.choice((-1, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0x0D, 0x15, 0x16, 0x17, 0x18, 0x1E, 0x23, 0x26, 0x2A))
        mods.append((code, rng.choice((0, rng.randrange(-60, 120), rng.randrange(1, 30))), rng.randrange(-20, 90), rng.randrange(0, 5)))
    flags = 0
    for bit, chance in ((36, .2), (43, .15)):
        if rng.random() < chance:
            flags |= 1 << bit
    return R.Item(defn=defn, count=rng.randrange(1, 9), flags=flags, mods=mods)


def gen_players(rng, tables, w, objects):
    """Four records with objects, equipment, figurines, skills and passives."""
    w.players = []
    for slot in range(4):
        rec = R.PlayerRec(cls=rng.choice((0, 1, 2, 3, 4, 5, 6, 0, 4, 5, 6, 7)))
        rec.level58 = rng.randrange(1, 81)
        rec.level59 = rng.choice((rec.level58, rng.randrange(1, 80)))
        rec.base = [rng.choice((rng.randrange(5, 60), rng.randrange(0, 300), -rng.randrange(1, 9))) for _ in range(4)]
        rec.eff = [rng.randrange(0, 200) for _ in range(4)]
        rec.hp = rng.choice((R.ZERO, rf(rng, 1, 4000)))
        rec.max_hp = rf(rng, 1, 4000)
        rec.mana = rf(rng, 0, 4000)
        rec.max_mana = rf(rng, 1, 4000)
        rec.exp = 0
        rec.skill_points, rec.stat_points = rng.randrange(0, 50), rng.randrange(0, 60)
        rec.passives = [rng.choice((0, 0, rng.randrange(1, 21), 0xFF)) for _ in range(48)]
        rec.skills = [(skill, rng.choice((0, rng.randrange(1, 21))))
                      for skill in rng.sample((0x30, 0x3B, 0x3C, 0x3D, 0x3F, 0x47, 0x4F, 0x5C, 0x21), 9)]
        if slot == 3 and rng.random() < 0.15:
            w.players.append(rec)
            continue                                    # a slot without an object
        obj = R.Obj(tag='player%d' % slot, flags=0x60, slot=slot)
        obj.pos = [rf(rng, -300, 300), rf(rng, -300, 300), R.ZERO]
        obj.res = [rf(rng, 0, 1) for _ in range(5)]
        obj.armor = rng.randrange(0, 500)
        obj.state = rng.choice((0, 1, 1, 2))
        obj.counter2, obj.counter4 = rng.choice((0, 0, 0, 7)), rng.choice((0, 0, 0, 3))
        obj.field_dc = rng.choice((R.ZERO, rf(rng, 0.5, 2.5)))
        rec.obj = obj
        objects.append(obj)
        rec.equip = [gen_item(rng, tables, None) if rng.random() < 0.45 else None for _ in range(17)]
        rec.weapon_sets = [gen_item(rng, tables, None, True) if rng.random() < 0.7 else None for _ in range(2)]
        rec.second_weapon = gen_item(rng, tables, None, True) if rng.random() < 0.3 else None
        rec.active_set = rng.choice((0, 1))
        rec.bag2 = []
        for _ in range(rng.choice((0, 2, 6))):
            item = gen_item(rng, tables, None, False)
            stat = rng.choice(tables.figurine_stats + ('zzz',))
            tier = rng.choice(tables.figurine_tiers + ('',))
            item.defn.name = rng.choice((stat + tier, tier + '_' + stat, 'x' + stat + 'y' + tier))
            item.defn.flags = FIGURINE_FLAG if rng.random() < 0.85 else 0
            rec.bag2.append(item if rng.random() < 0.9 else None)
        w.players.append(rec)
    w.num_players = rng.choice((1, 2, 3, 4, 4))
    w.alive = [slot for slot in range(4) if w.players[slot].obj is not None and rng.random() < 0.8]
    w.load_cheat = 1 if rng.random() < 0.05 else 0
    for slot in range(4):
        obj = w.players[slot].obj
        if obj is None:
            continue
        for kind, chance in (('BloodLust', .3), ('GiantGrowth', .3), ('AncestralCall', .4)):
            if rng.random() < chance:
                obj.spells = obj.spells + [new_spell(rng, kind, obj)]


def compare_players(rig, tally, name, w, objects, extra=''):
    ok = True
    for slot in range(4):
        got, want = rig.get_record(slot), rig.model_record(w.players[slot])
        if got != want:
            ok = False
            detail = (slot, {k: (got[k], want[k]) for k in got if got[k] != want[k]})
    for obj in objects:
        got, want = rig.get_object(obj), rig.model_object(obj)
        if got != want:
            ok = False
            detail = (obj.tag, {k: (got[k], want[k]) for k in got if got[k] != want[k]})
    tally.check(name, ok, lambda: (detail, extra))
    return ok


def group_player_stats(elf, rng, tables):
    for index, config in enumerate(FPU_CONFIGS):
        rig = Rig(elf, config)
        tally = Tally()
        label = '' if index == 0 else ' [%s%s%s]' % (config[0], ' bias' if config[1] else '', ' div-nearest' if config[2] else '')
        for case in range(scaled(2500 if index == 0 else 250)):
            w = make_world(rng)
            objects = []
            gen_players(rng, tables, w, objects)
            rig.begin({'world': w, 'local': rng.choice((0, 1))})
            rig.put_objects(objects)
            rig.put_world(w)
            rig.emu.reset_log()
            mode = case % 3
            if mode == 0:
                rig.call(0x1B6458)
                R.recalc_stats(tables, w)
                compare_players(rig, tally, 'player statistics' + label, w, objects)
                if index == 0:
                    tally.check('player statistics: no other store', not rig.stray_writes(objects, [], range(4)),
                                lambda: rig.stray_writes(objects, [], range(4))[:4])
            elif mode == 1:
                slot = rng.randrange(0, 4)
                rec = w.players[slot]
                rec.exp = rng.choice((0, tables.exp_table[R.s8(rec.level59)] - rng.randrange(1, 2000),
                                      rng.randrange(0, tables.exp_table[60])))
                rig.mem.w32(G_PLAYERS + slot * REC_SIZE + 0x5C, rec.exp)
                amount = rng.choice((0, rng.randrange(0, 3000), rng.randrange(0, 400000), tables.exp_table[80]))
                rig.call(0x1D3150, slot, amount)
                R.give_exp(tables, w, slot, amount)
                ok = compare_players(rig, tally, 'level-up' + label, w, objects, (slot, amount))
                events = [e for e in rig.events if e[0] == 'level_up']
                tally.check('level-up: levels gained' + label, events == [e for e in w.events if e[0] == 'level_up'],
                            lambda: (events, w.events))
            else:
                slot = rng.choice([s for s in range(4) if w.players[s].obj is not None])
                rec, obj = w.players[slot], w.players[slot].obj
                weapon = rng.choice((None, rec.weapon_sets[0], rec.weapon_sets[1], rec.second_weapon))
                flag = rng.choice((0, 1))
                w.frame = rng.randrange(1000, 100000)
                obj.attack_chain = w.frame - rng.choice((0, 5, 26, 27, 100))
                obj.attack_start = w.frame - rng.choice((0, 10, 59, 60, 61, 400))
                w.pvp_a = 1 if rng.random() < 0.15 else 0
                rig.mem.w32(0x44FDCC, w.frame)
                rig.mem.w32(0x4F711C, w.pvp_a)
                a = rig.addr[id(obj)]
                rig.mem.w32(a + 0x458, obj.attack_start)
                rig.mem.w32(a + 0x45C, obj.attack_chain)
                rig.call(0x1B7158, a, rig.addr[id(weapon)] if weapon is not None else 0, flag)
                R.recalc_damage(tables, w, obj, weapon, flag)
                compare_players(rig, tally, 'player attack and damage' + label, w, objects,
                                (slot, rec.cls, None if weapon is None else (weapon.defn.subtype, weapon.defn.dmg_type)))
                if weapon is not None and index == 0:
                    for with_elements in (0, 1):
                        out = rig.take(8)
                        rig.call(0x104100, rig.addr[id(weapon)], out, out + 4, with_elements)
                        got = (rig.mem.s32(out), rig.mem.s32(out + 4), s32(rig.call(0x103F88, rig.addr[id(weapon)])),
                               s32(rig.call(0x103EC8, rig.addr[id(weapon)])))
                        want = R.item_damage_range(weapon, with_elements) + (R.item_attack_rating(weapon), R.item_armor_value(weapon))
                        tally.check('item damage range, attack rating, armour', got == want, lambda: (got, want))
        text = {'player statistics': 'every record and object field of all four slots',
                'level-up': 'experience, level, points, maxima, refill; all four slots',
                'player attack and damage': 'record attack rating and damage range; all four slots unchanged otherwise'}
        tally.flush({name: next((t for key, t in text.items() if name.startswith(key)), 'bit for bit') for name in tally.order})


def group_kill_xp(elf, rng, tables):
    for index, config in enumerate(FPU_CONFIGS[:3]):
        rig = Rig(elf, config)
        tally = Tally()
        label = '' if index == 0 else ' [%s]' % config[0]
        for _ in range(scaled(2500 if index == 0 else 250)):
            w = make_world(rng)
            objects = []
            gen_players(rng, tables, w, objects)
            w.num_players = rng.choice((0, 1, 1, 2, 3, 4))
            for slot in range(4):
                rec = w.players[slot]
                rec.level59 = rng.randrange(1, 81)
                rec.exp = rng.randrange(0, tables.exp_table[R.s8(rec.level59)])
                rec.skills = rec.skills + [(0x3B, rng.choice((0, 3, 12)))] if not rec.rank(0x3B) else rec.skills
            creature = R.Obj(tag='monster', flags=0x29, own_seed=rng.getrandbits(32),
                             exp_value=R.itof(rng.choice((0, rng.randrange(1, 4000), rng.randrange(1, 4000000)))),
                             max_hp=rf(rng, 10, 20000), pos=[rf(rng, -99, 99), rf(rng, -99, 99), R.ZERO])
            killer = rng.choice((-1, 0, 0, 1, 2, 3))
            if killer != -1 and (killer >= max(w.num_players, 1) or w.players[killer].obj is None):
                killer = -1
            other = R.Obj(tag='someone', flags=0x20)
            creature.last_attacker = w.players[killer].obj if killer != -1 else rng.choice((None, other))
            objects += [creature, other]
            plan = [rng.random() < 0.85 for _ in range(8)]
            original_pool, w.pool_fn = pool_plan(plan)
            rig.begin({'world': w, 'pool': original_pool, 'local': rng.choice((0, 1))})
            rig.put_objects(objects)
            rig.put_world(w)
            emu = rig.emu
            emu.reset_log()
            emu.r[18] = rig.addr[id(creature)]
            emu.r[29] = rig.sp - 0x400
            reason = emu.run(start=0x111E3C, until={0x112490, 0x112494}, max_steps=3000000)
            own = R.Seed(creature.own_seed)
            awards = R.kill_experience(tables, w, creature, killer, orb_draw=own.draw() if killer != -1 else 0)
            if killer != -1:
                creature.own_seed = own.state
            tally.check('kill experience: ran to the exit' + label, reason == 'stop')
            compare_players(rig, tally, 'kill experience: records' + label, w, objects, (w.num_players, killer, awards))
            tally.check('kill experience: draws and seed' + label,
                        rig.seed_draws() == w.seed.draws and rig.mem.u32(G_SEED) == w.seed.state)
            got = [e for e in rig.events if e[0] in ('level_up', 'orb', 'pool')]
            want = [e for e in w.events if e[0] in ('level_up', 'orb', 'pool')]
            tally.check('kill experience: orb and level-ups' + label, got == want, lambda: (got, want))
        tally.flush({name: 'stretch 0x111e3c to the function\'s exit; bit for bit' for name in tally.order})


COVER = ('take_damage', 'text', 'gas', 'disease', 'stun', 'light', 'cast', 'sparks', 'undead_shield', 'voice')


def group_damage(elf, rng, tables):
    cover = {}
    for index, config in enumerate(FPU_CONFIGS):
        rig = Rig(elf, config)
        tally = Tally()
        label = '' if index == 0 else ' [%s%s%s]' % (config[0], ' bias' if config[1] else '', ' div-nearest' if config[2] else '')
        skipped = 0
        for _ in range(scaled(12000 if index == 0 else 1000)):
            sc = gen_damage(rng)
            w, objects, victim, attacker = sc['world'], sc['objects'], sc['victim'], sc['attacker']
            sc['pool'], w.pool_fn = pool_plan(sc['plan'])
            spells = [spell for obj in objects for spell in obj.spells]
            rig.begin(sc)
            rig.put_objects(objects)
            rig.put_world(w)
            desc = rig.put_desc(sc['desc']) if sc['desc'] is not None else 0
            rig.emu.reset_log()
            rig.emu.notes = []
            try:
                ret = rig.call(0x1E8230, rig.addr[id(victim)], rig.addr[id(attacker)] if attacker is not None else 0,
                               sc['attack'] & M32, 0x1234, 0x5678, sc['flags'], desc, sc['no_crit'],
                               fargs=(sc['min'], sc['max'])) & M32
                want = R.damage_apply(w, victim, attacker, sc['min'], sc['max'], sc['attack'], sc['flags'],
                                      sc['desc'], sc['no_crit'])
            except (ee_emu.StepLimit, RecursionError):
                skipped += 1
                continue
            got_events = [tuple(e) for e in rig.events]
            want_events = [e for e in w.events if e[0] != 'thorns']
            tally.check('damage: return value' + label, ret == want, lambda: (ret, want))
            tally.check('damage: amounts handed to take-damage' + label,
                        [e for e in got_events if e[0] == 'take_damage'] == [e for e in want_events if e[0] == 'take_damage'],
                        lambda: ([e for e in got_events if e[0] == 'take_damage'], [e for e in want_events if e[0] == 'take_damage']))
            tally.check('damage: effects, in order' + label, got_events == want_events,
                        lambda: next(((i, a, b) for i, (a, b) in enumerate(zip(got_events + [None] * 99, want_events + [None] * 99)) if a != b), None))
            tally.check('damage: shared-seed draws, in order' + label, rig.seed_draws() == w.seed.draws,
                        lambda: (rig.seed_draws(), w.seed.draws))
            tally.check('damage: seeds afterwards' + label,
                        rig.mem.u32(G_SEED) == w.seed.state and rig.mem.u32(G_COSMETIC) == w.cosmetic.state)
            ok = all(rig.get_object(obj) == rig.model_object(obj) for obj in objects)
            ok = ok and all(rig.get_spell(s) == (s.f18 & M32, s.f1c, s.f20, s.f2c & M32) for s in spells)
            ok = ok and all(rig.get_record(slot) == rig.model_record(w.players[slot]) for slot in range(4))
            ok = ok and rig.mem.read(0x4F7158, 32) == bytes(w.music)
            tally.check('damage: fields written' + label, ok,
                        lambda: [(o.tag, {k: (v, rig.model_object(o)[k]) for k, v in rig.get_object(o).items() if v != rig.model_object(o)[k]}) for o in objects if rig.get_object(o) != rig.model_object(o)])
            if index == 0:
                stray = rig.stray_writes(objects, spells, range(4))
                tally.check('damage: no other store', not stray, lambda: stray[:4])
                for event in want_events:
                    if event[0] in COVER:
                        cover[event[0]] = cover.get(event[0], 0) + 1
                cover['returned 0'] = cover.get('returned 0', 0) + (want == 0)
                cover['zero divisor'] = cover.get('zero divisor', 0) + bool(rig.emu.notes)
                cover['nested hit'] = cover.get('nested hit', 0) + (len({e[1] for e in want_events if e[0] == 'take_damage'}) > 1)
                cover['critical'] = cover.get('critical', 0) + any(e[0] == 'text' and e[2] for e in want_events)
        tally.flush({name: 'bit for bit' for name in tally.order})
        if skipped:
            print('      (%d generated cases skipped: runaway recursion in both original and model)' % skipped)
    if cover:
        print('      damage paths in the full sample: ' + ', '.join('%s %d' % item for item in sorted(cover.items())))


GROUPS = (('fpu', group_fpu, False), ('soft double', group_soft_double, False), ('powf', group_powf, False),
          ('tables', None, False), ('boss rank', group_boss_rank, True), ('monster', group_monster, True),
          ('player', group_player_stats, True), ('kill experience', group_kill_xp, True),
          ('damage', group_damage, True))


def main(argv):
    args = list(argv)
    elf = os.path.join(ROOT, 'SLUS_209.73')
    while args:
        arg = args.pop(0)
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--seed':
            OPTIONS['seed'] = int(args.pop(0))
        elif arg == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif arg in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            elf = arg
    if not os.path.exists(elf):
        print('SKIP  difftest_combat: %s not found (the tests need your own copy of the executable)' % elf)
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  difftest_combat: %s is not the US v2.00 executable this was written against' % elf)
        return 0
    started = time.time()
    tables = None
    for name, function, needs_tables in GROUPS:
        if name == 'tables':
            tables = group_tables(elf, random.Random(OPTIONS['seed']))
            continue
        if not wanted(name):
            continue
        rng = random.Random('%d/%s' % (OPTIONS['seed'], name))
        if needs_tables:
            function(elf, rng, tables)
        else:
            function(elf, rng)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
