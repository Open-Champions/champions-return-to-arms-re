#!/usr/bin/env python3
"""difftest_player.py - compare tools/ref_player.py with the game's own Player_run.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_player.py [path/to/SLUS_209.73] [--quick] [--seed N] [--ticks N]
                                   [-k TEXT] [-v] [--trace-first]

    --quick       a tenth of the ticks
    --seed N      seed of the random runs (default 20973); a seed repeats exactly
    --ticks N     ticks per run (default 4000; there are 8 runs)
    -k TEXT       only the runs whose name contains TEXT
    -v            print the first mismatches of every failing property
    --trace-first stop at the first mismatching tick and print both sides

What is compared
    The ORIGINAL Player_run 0x1a5030 is executed by tools/ee_emu.py (an instruction
    interpreter, not a console) on a constructed player, once per tick, over long seeded
    random sequences of pad input.  The same tick is run through tools/ref_player.py first,
    on a copy-on-write view of the same memory.  For every tick these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
      writes   the set of bytes stored outside the stack, and their final values
      seed     the shared seed 0x404464, and that it advanced exactly as many times as the
               model says it drew
      exit     whether the function ran to its end or left early
    Floats are compared as 32-bit patterns: "equal" means identical under the
    interpreter's floating-point model ('ps2'), see docs/issues/dynamic-tests.md.

What runs for real and what is a stub
    Real: Player_run, the helpers ref_player.py models (REAL_HELPERS below), the C library
    and the software floating point (0x3a5000-0x3c0000), the three angle functions and
    GameObject_rand.  Everything else the tick calls is a recording stub whose answer
    (return value, output arguments, and the fields a real callee would change: animation
    flags, the target handle, the action state after damage ...) comes from World.respond,
    a seeded script.  The model's callbacks are answered by the same script, so both sides
    see the same world as long as they make the same calls.  A call to an address that is
    neither real nor a known stub is reported as a failure, so nothing is stubbed by
    accident.

    Driven by scripted stub answers, not by game data: animation events and flags
    (Player_animStep, anim_start), being hit and dying (Player_processDamage), landing and
    ground contact (Player_move), targets (Player_findTarget, the world queries, handle
    lists), Skill and Spell objects (virtual calls), potion use, inventory, respawn (the
    driver rebuilds the object as player_respawn would).  States 6, 7, 9, 0xd and 0xe are
    entered by the driver writing the state, as skill and vehicle code does in the game.
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
import ref_player as RP                         # noqa: E402
from ref_player import EXTERNALS, G_PLAYERS, REC_SIZE, M32      # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAYER_RUN, FUNC_END = 0x1A5030, 0x1AC7A8
CLASS_SKILLS_INIT = 0x1AC7A8
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
REAL_HELPERS = {
    'Player_idleFidget': 0x1BC2F8, 'player_canBlock': 0x1BEE48, 'Player_tryBlockMove': 0x1BF150,
    'Player_hasAnim': 0x1BF230, 'player_getSkillRank': 0x1BF330, 'player_getPassiveLevel': 0x1BED48,
    'Player_updateCast': 0x1A3F70, 'Player_regenHealth': 0x1B3B90, 'Player_regenMana': 0x1B3900,
    'Player_tickEnchantTimers': 0x1BC560, 'Player_weaponSwapInput': 0x1BB718, 'Player_castSkill': 0x1A42B8,
    'Player_usePotion': 0x1B9CB8,
}
REAL_OTHER = {0x1509D0, 0x1BEC08, 0x166630, 0x1666E0, 0x166798, 0x166C18}
STUB_BASE = 0x00F00000
STACK_LO, STACK_HI = EE.STACK_LO, EE.STACK_HI

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'ticks': 4000, 'trace_first': False}
RESULTS = []


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-34s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:4]:
            print('        ' + str(line)[:900])
    sys.stdout.flush()


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class RealSet:
    """What the interpreter runs for real: the listed functions and the C library."""

    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or LIB_LO <= target < LIB_HI


class Res:
    def __init__(self, ret=0, f=0, outs=()):
        self.ret, self.f, self.outs = ret, f, list(outs)


# ---------------------------------------------------------------------------------------
# Views: how the script reads and changes memory on each side
# ---------------------------------------------------------------------------------------
class EmuView:
    def __init__(self, emu):
        self.emu, self.mem, self.touched = emu, emu.mem, set()
        self.iter_nodes = []

    def load(self, addr, size):
        return self.mem.load(addr, size)

    def poke(self, addr, size, value):
        self.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))


class ModelView(RP.Memory):
    def __init__(self, under):
        RP.Memory.__init__(self, under)
        self.touched = set()
        self.iter_nodes = []

    def poke(self, addr, size, value):
        RP.Memory.poke(self, addr, size, value)
        self.touched.update(range(addr, addr + size))


def rd(view, addr, size=4, signed=False):
    v = view.load(addr, size)
    if signed and v >> (8 * size - 1):
        v -= 1 << (8 * size)
    return v


# ---------------------------------------------------------------------------------------
# The scripted world
# ---------------------------------------------------------------------------------------
BTN = {'attack': 0x4000, 'ability_a': 0x2000, 'ability_b': 0x8000, 'use': 0x1000, 'block': 0x0400,
       'potion_a': 0x0100, 'potion_b': 0x0200, 'swap': 0x0800}
BTN_ADDR = {'attack': RP.G_BTN_ATTACK, 'ability_a': RP.G_BTN_ABILITY_A, 'ability_b': RP.G_BTN_ABILITY_B,
            'use': 0x41B9C0, 'block': RP.G_BTN_BLOCK, 'potion_a': RP.G_BTN_POTION_A, 'potion_b': RP.G_BTN_POTION_B,
            'swap': RP.G_BTN_SWAP}
SKILL_IDS = (0x30, 0x31, 0x22, 0x2E, 0x33, 0x34, 0x35, 0x36, 0x13, 0x26, 0x47)
OLD_IDS = (0xE, 0x25, 0xC, 4, 5, 6, 0x13, 0x12, 9, 0x19, 0x15, 0x1A, 0x1B, 0x7)
FLOATS = [f32(v) for v in (0.0, 0.2, 0.6, 1.0, 1.5, 5.0, 11.0)]


class World:
    """Builds the fake game in the interpreter's memory and answers every stubbed call."""

    def __init__(self, emu, rng, net, copy, machine):
        self.emu, self.mem = emu, emu.mem
        self.net, self.copy, self.machine = net, copy, machine
        self.stub_addr, self.stub_name = {}, {}
        mem = self.mem
        self.newstyle = mem.cstr(RP.S_NEWSTYLE).encode() if isinstance(mem.cstr(RP.S_NEWSTYLE), str) \
            else mem.cstr(RP.S_NEWSTYLE)
        self.burning = mem.cstr(RP.S_BURNINGHANDS)
        self.burning = self.burning.encode() if isinstance(self.burning, str) else self.burning
        self.slot = rng.randrange(4)
        self.players = 4
        self.hit_rate = 0.02
        self.build(rng)

    # ---- construction ------------------------------------------------------------------
    def stub_for(self, name):
        if name not in self.stub_addr:
            addr = STUB_BASE + 16 * len(self.stub_addr)
            self.stub_addr[name], self.stub_name[addr] = addr, name
        return self.stub_addr[name]

    def vtable(self, cls, slots):
        table = self.emu.alloc(8 * 48)
        for slot in range(48):
            name = '%s.v%d' % (cls, slot)
            self.mem.w16(table + 8 * slot, 0)
            self.mem.w32(table + 8 * slot + 4, self.stub_for(name) if slot in slots else 0)
        return table

    def build(self, rng):
        emu, mem = self.emu, self.mem
        self.vt_player = self.vtable('Player', (17, 20, 26, 39))
        self.vt_creature = self.vtable('Creature', (12,))
        self.vt_vehicle = self.vtable('Vehicle', (17,))
        self.vt_skill = self.vtable('Skill', (1, 2, 5, 10))
        self.vt_spell = self.vtable('Spell', (1, 4))
        self.lump = emu.alloc(16)
        mem.write(self.lump, b'lump\0')
        self.anim_table = emu.alloc(0x400)
        mem.w32(self.anim_table, self.lump)
        self.anims = [0x00D00010 + 0x10 * i for i in range(6)]
        for off in range(4, 0x400, 4):
            mem.w32(self.anim_table + off, self.anims[(off // 4) % len(self.anims)])
        # skills
        self.skills = {}
        for sid in SKILL_IDS:
            skill = emu.alloc(0x80)
            mem.w32(skill + 0x60, self.vt_skill)
            self.skills[sid] = skill
            mem.w32(RP.G_SKILL_TABLE + 4 * sid, skill)
        # item definitions: one per (equipment slot, weapon class)
        self.defs = {}
        for key, (eq_slot, cls, flags) in {'sword': (0, 0, 0), 'axe2h': (2, 2, 8), 'sword2h': (2, 1, 0),
                                           'spear': (2, 3, 0), 'bow': (2, 4, 0), 'thrown': (2, 6, 0),
                                           'dual': (0, 7, 0), 'fist': (0, 5, 8), 'shield': (3, 0, 0),
                                           'arrows': (8, 0, 0), 'ring': (5, 0, 0)}.items():
            d = emu.alloc(0x40)
            name = emu.alloc(16)
            mem.write(name, key.encode() + b'\0')
            mem.w32(d, name)
            mem.w8(d + 0x1C, eq_slot)
            mem.w8(d + 0x1E, cls)
            mem.w32(d + 0x20, flags)
            self.defs[key] = d
        self.potion_defs = []
        for table in RP.G_POTION_NAMES:
            row = []
            for size in range(9):
                d = emu.alloc(0x40)
                mem.w32(d, mem.u32(table + 4 * size))
                mem.w8(d + 0x1C, 0xFF)
                mem.w8(d + 0x1D, 3 + size)
                row.append(d)
            self.potion_defs.append(row)
        self.list_cells = emu.alloc(4 * 0x23988)
        for slot in range(4):
            cell = self.list_cells + slot * 0x23988 + 0x17BB0
            mem.w32(cell, self.potion_defs[0][slot])
            mem.w16(cell + 0x22, 0x7000 + slot)
        # creatures the world queries can return
        self.creatures, self.nodes = [], {}
        for i in range(5):
            c = emu.alloc(0x400)
            mem.w32(c + 0x48, self.vt_creature)
            node = emu.alloc(0x20)
            mem.w32(node + 0xC, c)
            self.creatures.append(c)
            self.nodes[c] = node
        self.sweep_nodes = []
        for i in range(4):
            node = emu.alloc(0x20)
            self.sweep_nodes.append(node)
        self.arc_nodes = [emu.alloc(0x20) for _ in range(6)]
        self.spells = []
        for i in range(3):
            sp = emu.alloc(0x40)
            mem.w32(sp + 0x14, self.vt_spell)
            self.spells.append(sp)
        self.held_node = emu.alloc(0x20)
        self.vehicle = emu.alloc(0x100)
        mem.w32(self.vehicle + 0x48, self.vt_vehicle)
        self.pool = {size: emu.alloc(0x200) for size in (0xBC, 0x9C, 0xC0, 0xA0, 0x1C8, 0x1D0)}
        self.text = emu.alloc(0x40)
        # players
        self.objects = []
        for slot in range(4):
            obj = emu.alloc(0x600)
            self.objects.append(obj)
            mem.w32(G_PLAYERS + slot * REC_SIZE + 0x43D8, obj)
            self.init_object(obj, slot, rng)
            self.init_record(slot, rng)
            for key, addr in BTN_ADDR.items():
                mem.w32(addr + 4 * slot, BTN[key])
        self.P = self.objects[self.slot]
        self.R = G_PLAYERS + self.slot * REC_SIZE
        mem.w32(RP.G_SIM_FRAME, 1000 + rng.randrange(5000))
        mem.w8(RP.G_NETWORK_MODE, 1 if self.net else 0)
        mem.wf32(RP.G_KILL_PLANE, -100000.0)
        mem.wf32(RP.G_LIGHT_SCALE, 1.0)
        mem.w32(RP.G_WORLD, emu.alloc(16))
        mem.write(RP.G_LEVEL_NAME, b'testlevel\0')
        self.set_alive(rng)

    def init_object(self, obj, slot, rng):
        mem = self.mem
        for off in range(0, 0x600, 4):
            mem.w32(obj + off, 0)
        mem.w32(obj + 0xC, 0x4060 | (0x20000 if (self.copy and slot == self.slot) else 0))
        for i, v in enumerate((100.0 + 40 * slot, 200.0, 0.0)):
            mem.wf32(obj + 0x10 + 4 * i, v + rng.uniform(-5, 5))
        mem.wf32(obj + 0x1C, 16.0)
        mem.wf32(obj + 0x20, 72.0)
        mem.w32(obj + 0x24, self.anim_table)
        mem.w16(obj + 0x38, rng.randrange(0x10000))
        mem.w32(obj + 0x44, rng.randrange(0x10000))
        mem.w32(obj + 0x48, self.vt_player)
        mem.w8(obj + 0x230, rng.randrange(256))
        mem.w32(obj + 0x3C8, slot)
        mem.w32(obj + 0x4A8, M32)
        mem.w16(obj + 0x4B2, 30 + rng.randrange(200))
        mem.w8(obj + 0x482, 15)
        mem.w32(obj + 0x544, 0x00C00000 + slot)
        mem.w32(obj + 0x540, self.vehicle)
        mem.w32(obj + 0x58C, 2)
        mem.w8(obj + 0x118, 4)
        mem.w8(obj + 0x119, 2)
        for i in range(8):
            mem.w32(obj + 0x11C + 0x20 * i, rng.choice(self.anims))

    def new_item(self, slot, index, key, rng, quantity=1):
        mem = self.mem
        item = G_PLAYERS + slot * REC_SIZE + 0x130 + index * 0x48
        for off in range(0, 0x48, 4):
            mem.w32(item + off, 0)
        mem.w32(item, self.defs[key])
        mem.w16(item + 4, quantity)
        flags = 0
        if key == 'thrown' and rng.random() < 0.5:
            flags |= 0x1000000
        if rng.random() < 0.3:
            flags |= 0x20000000
        mem.w64(item + 8, flags)
        ids = [0x14, 0xB, 0xC, 21, 22, 24, 38, 23, 7, -1, -1, -1]
        for k in range(4):
            mem.w16(item + 0x24 + 8 * k, rng.choice(ids) & 0xFFFF)
            mem.w16(item + 0x26 + 8 * k, rng.randrange(0, 12))
            mem.w16(item + 0x28 + 8 * k, rng.randrange(0, 4))
            mem.w16(item + 0x2A + 8 * k, rng.choice((0, 1, 2, 5, 300)))
        return item

    def init_record(self, slot, rng):
        mem = self.mem
        R = G_PLAYERS + slot * REC_SIZE
        obj = mem.u32(R + 0x43D8)
        for off in range(0, REC_SIZE, 4):
            mem.w32(R + off, 0)
        mem.w32(R + 0x43D8, obj)
        cls = rng.choice((0, 1, 2, 3, 4, 5, 6))
        mem.w32(R + 0x50, cls)
        mem.wf32(R + 0xB0, 200.0)
        mem.wf32(R + 0xAC, rng.choice((200.0, 150.0, 60.0)))
        mem.wf32(R + 0xC4, 120.0)
        mem.wf32(R + 0xC0, rng.choice((120.0, 80.0, 6.0, 0.5)))
        for n in range(0x30):
            mem.w8(R + 0xEF + n, rng.choice((0, 0, 1, 3, 0xFF)))
        # bag 0: weapons, arrows
        weapon = rng.choice(('sword', 'axe2h', 'sword2h', 'spear', 'bow', 'thrown', 'dual', 'fist', None))
        other = rng.choice(('sword', 'axe2h', 'bow', 'thrown', None))
        index = 0
        items = {}
        for key in (weapon, other, 'shield', 'arrows', 'ring', 'arrows'):
            if key is None:
                index += 1
                continue
            qty = rng.choice((1, 2, 5, 19, 25, 60)) if key in ('arrows', 'thrown') else 1
            items[index] = (key, self.new_item(slot, index, key, rng, qty))
            index += 1
        mem.w32(R + 0x1330, index)
        # bag 2: potions, named by the executable's own two name tables
        count = rng.randrange(0, 7)
        for i in range(count):
            item = R + 0x2540 + i * 0x48
            kind = rng.randrange(2)
            mem.w32(item, self.potion_defs[kind][rng.choice((0, 0, 1, 2, 3, 5, 8, 8))])
            mem.w16(item + 4, rng.choice((1, 1, 2, 3, 7)))
        mem.w32(R + 0x3740, count)
        mem.w32(R + 0x2538, rng.randrange(0, 3))
        if weapon:
            item = items[0][1]
            mem.w32(R + 0x4434, item)
            eq = mem.u8(self.defs[weapon] + 0x1C)
            mem.w32(R + 0x43F0 + 4 * eq, item)
            mem.w8(R + 0x4A86, mem.u8(self.defs[weapon] + 0x1E))
            if weapon == 'dual' and rng.random() < 0.7:
                mem.w32(R + 0x443C, items[2][1])
                mem.w32(R + 0x43F4, items[2][1])
        else:
            mem.w8(R + 0x4A86, 5)
        if other:
            mem.w32(R + 0x4438, items[1][1])
        if rng.random() < 0.6 and weapon not in ('axe2h', 'sword2h', 'spear', 'bow', 'thrown'):
            mem.w32(R + 0x43FC, items[2][1])
        if rng.random() < 0.8:
            mem.w32(R + 0x4410, items[3][1])
        if rng.random() < 0.5:
            mem.w32(R + 0x4404, items[4][1])
        # ability records
        for i in range(15):
            ab = R + 0x4440 + i * 0x68
            style = rng.random()
            if style < 0.62:
                sid = rng.choice(SKILL_IDS[:8])
                mem.write(ab, self.newstyle + b'\0')
                kind = rng.choice((0, 0, 1, 7, 8, 2))
            elif style < 0.9:
                sid = rng.choice(OLD_IDS)
                mem.write(ab, self.burning + b'\0' if rng.random() < 0.3 else b'old\0')
                kind = {9: 1, 0x7: 2, 0x19: 0, 0x15: 0, 0x1A: 0, 0x1B: 0}.get(sid, rng.choice((0, 1, 2)))
            else:
                sid = -1
                mem.write(ab, b'none\0')
                kind = 0
            mem.w16(ab + 0x20, sid & 0xFFFF)
            mem.w16(ab + 0x22, rng.choice((0, 3, 20)))
            mem.w8(ab + 0x24, 0 if rng.random() < 0.1 else 1)
            mem.w8(ab + 0x25, kind)
            mem.w16(ab + 0x28, rng.randrange(40))
            mem.wf32(ab + 0x2C, rng.choice((2.0, 10.0, 999.0, 60.0)))
            for k in range(8):
                mem.w16(ab + 0x30 + 2 * k, rng.randrange(-50, 300) & 0xFFFF)
            mem.wf32(ab + 0x40, rng.choice((0.05, 0.02)))
        mem.w8(R + 0x4A84, rng.randrange(15))
        mem.w8(R + 0x4A85, rng.randrange(15))
        mem.w16(R + 0x4A60, rng.choice((0, 1)))
        # skill ranks
        pairs = [(sid, rng.randrange(0, 4)) for sid in (0x13, 0x26, 0x2E, 0x47, 0x3B) if rng.random() < 0.6]
        for n, (sid, rank) in enumerate(pairs):
            mem.w16(R + 0x4B08 + 4 * n, sid)
            mem.w16(R + 0x4B0A + 4 * n, rank)
        mem.w16(R + 0x4B08 + 4 * len(pairs), 0xFFFF)
        mem.wf32(R + 0x4C20, 1.0)
        for sid, skill in self.skills.items():
            mem.w32(skill + 4, rng.choice((0, 0, 1)))
            mem.w32(skill + 8, rng.choice((0, 0, 1, 6, 8, 7)))
            mem.w16(skill + 0xC, rng.choice((0, 5, 30)))

    def equip(self, slot, key, rng):
        """Make `key` the primary weapon of set 0 and the active one."""
        mem = self.mem
        R = G_PLAYERS + slot * REC_SIZE
        item = self.new_item(slot, 0, key, rng, rng.choice((1, 2, 5, 19, 25, 60)) if key == 'thrown' else 1)
        for eq in (0, 1, 2):
            mem.w32(R + 0x43F0 + 4 * eq, 0)
        mem.w32(R + 0x4434, item)
        mem.w32(R + 0x43F0 + 4 * mem.u8(self.defs[key] + 0x1C), item)
        mem.w8(R + 0x4A86, mem.u8(self.defs[key] + 0x1E))
        mem.w8(R + 0x4A7C, 0)
        mem.w8(R + 0x4A7D, 0)
        if key == 'bow':
            arrows = self.new_item(slot, 3, 'arrows', rng, rng.choice((0, 1, 2, 3, 19, 25, 60)))
            mem.w32(R + 0x4410, arrows if rng.random() < 0.85 else 0)
        if key == 'dual':
            second = self.new_item(slot, 2, 'sword', rng)
            mem.w32(R + 0x443C, second)
            mem.w32(R + 0x43F4, second)
        if mem.s32(R + 0x1330) < 6:
            mem.w32(R + 0x1330, 6)

    def set_ability(self, slot, index, newstyle, sid, kind, rng, cost=None, cooldown=0):
        mem = self.mem
        ab = G_PLAYERS + slot * REC_SIZE + 0x4440 + index * 0x68
        if newstyle:
            name = self.newstyle
        else:
            name = self.burning if rng.random() < 0.3 else b'old'
        mem.write(ab, name + b'\0')
        mem.w16(ab + 0x20, sid & 0xFFFF)
        mem.w16(ab + 0x22, cooldown)
        mem.w8(ab + 0x24, 1)
        mem.w8(ab + 0x25, kind)
        mem.wf32(ab + 0x2C, cost if cost is not None else rng.choice((2.0, 10.0, 999.0)))

    def set_alive(self, rng):
        mem = self.mem
        slots = [s for s in range(4) if s == self.slot or rng.random() < 0.6]
        mem.w32(RP.G_ALIVE_COUNT, len(slots))
        for i, s in enumerate(slots):
            mem.w32(RP.G_ALIVE_LIST + 4 * i, s)

    def place_creatures(self, rng):
        mem = self.mem
        px, py, pz = (mem.f32(self.P + 0x10 + 4 * i) for i in range(3))
        for c in self.creatures:
            flags = rng.choice((0x20, 0x20, 0x20, 0x60, 0x28, 0x21, 0x0, 0x1000020, 0x40))
            mem.w32(c + 0xC, flags)
            mem.wf32(c + 0x10, px + rng.uniform(-70, 70))
            mem.wf32(c + 0x14, py + rng.uniform(-70, 70))
            mem.wf32(c + 0x18, pz + rng.uniform(-10, 30))
            mem.wf32(c + 0x1C, rng.choice((8.0, 16.0, 30.0)))
            mem.wf32(c + 0x20, rng.choice((40.0, 72.0)))
            mem.w64(c + 0xA8, rng.choice((0, 0, 0x4000000)))
            mem.wf32(c + 0x308, rng.uniform(-100, 100))
            mem.wf32(c + 0x30C, rng.uniform(-100, 100))
            mem.w16(c + 0x312, rng.choice((0, 0, 0, 5)))

    # ---- answers ------------------------------------------------------------------------
    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        if handler is not None:
            return handler(args, view, rng)
        return Res()

    def flag(self, rng, p):
        return 1 if rng.random() < p else 0

    def on_net_getCamFlag(self, args, view, rng):
        return Res(self.flag(rng, 0.03))

    def on_game_isFrozen(self, args, view, rng):
        return Res(self.flag(rng, 0.03))

    def on_memcard_isBusy(self, args, view, rng):
        return Res(self.flag(rng, 0.3 if self.machine else 0.02))

    def on_dialog_isOpen(self, args, view, rng):
        return Res(self.flag(rng, 0.03))

    def on_dialog_22fbd0(self, args, view, rng):
        return Res(rng.randrange(0x10000))

    def on_task_isRunning(self, args, view, rng):
        return Res(self.flag(rng, 0.02))

    def on_net_isSlotActive(self, args, view, rng):
        return Res(1 - self.flag(rng, 0.03))

    def on_net_isLocalSlot(self, args, view, rng):
        return Res(1 if self.machine else 0)

    def on_Creature_run(self, args, view, rng):
        P = args[0]
        if rng.random() < 0.05:
            view.poke(P + 0x2FC, 1, rng.choice((0, 0, 0, 1, 10, 30, 59, 60, 61, 200)))
        if rng.random() < 0.03:
            view.poke(P + 0x374, 4, rng.choice((0, 0x30C)))
        if rng.random() < 0.03:
            view.poke(P + 0x37C, 4, rng.choice((0, 100)))
        return Res()

    def on_Player_animStep(self, args, view, rng):
        P = args[0]
        flags = rd(view, P + 0x11A, 2)
        for bit in (8, 0x10, 0x20, 0x8000):
            if flags & bit and rng.random() < 0.12:
                flags &= ~bit
        view.poke(P + 0x11A, 2, flags)
        n = rd(view, P + 0x118, 1, True)
        if n > 4 and rng.random() < 0.25:
            n -= 1
            view.poke(P + 0x118, 1, n)
        for i in range(max(n, 0)):
            if rng.random() < 0.5:
                view.poke(P + 0x124 + 0x20 * i, 4, rng.choice(FLOATS))
            if rng.random() < 0.3:
                view.poke(P + 0x12C + 0x20 * i, 4, rng.choice(FLOATS[:5]))
            if rng.random() < 0.3:
                view.poke(P + 0x134 + 0x20 * i, 4, rng.choice(FLOATS))
        r = rng.random()
        return Res(0 if r < 0.7 else rng.choice((1, 2, 4, 8, 5, 3, 9, 0x10)))

    def start_anim(self, view, P_state, anm, flags):
        P = P_state - 0x114
        n = rd(view, P + 0x118, 1, True)
        if 0 <= n < 7:
            view.poke(P + 0x11C + 0x20 * n, 4, anm)
            view.poke(P + 0x124 + 0x20 * n, 4, 0)
            view.poke(P + 0x12C + 0x20 * n, 4, 0)
            view.poke(P + 0x118, 1, n + 1)
        view.poke(P + 0x11A, 2, rd(view, P + 0x11A, 2) | (flags & 0x8038))

    def on_anim_start(self, args, view, rng):
        self.start_anim(view, args[0], args[1], args[2])
        return Res()

    def on_anim_startBlendInOut(self, args, view, rng):
        self.start_anim(view, args[0], args[1], args[2])
        return Res()

    def on_anim_findTrackByFlag(self, args, view, rng):
        P = args[0] - 0x114
        n = rd(view, P + 0x118, 1, True)
        if rd(view, P + 0x11A, 2) & args[1] and n > 0 and rng.random() < 0.9:
            return Res(rng.randrange(n))
        return Res((-1000000000) & M32 if rng.random() < 0.85 else rng.randrange(max(n, 1)))

    def on_Player_move(self, args, view, rng):
        P = args[0]
        view.poke(P + 0x482, 1, 15 if rng.random() < 0.93 else 0)
        for k in range(2):
            if rng.random() < 0.3:
                view.poke(P + 0x10 + 4 * k, 4, f32(rng.uniform(-400, 400)))
        view.poke(P + 0x4BC, 4, f32(rng.uniform(-200, 200)))
        view.poke(P + 0x4C0, 4, f32(rng.uniform(-200, 200)))
        if rng.random() < 0.3:
            view.poke(P + 0x38, 2, rng.randrange(0x10000))
        if rd(view, P + 0x58C) == 7 and rng.random() < 0.2:
            view.poke(P + 0x58C, 4, 2)
        return Res(0 if rng.random() < 0.7 else rng.choice((1, 4, 5, 2)))

    def on_Player_processDamage(self, args, view, rng):
        P = args[0]
        R = G_PLAYERS + rd(view, P + 0x3C8, 4, True) * REC_SIZE
        state = rd(view, P + 0x58C)
        r = rng.random()
        if state == 4:
            return Res()
        if rd(view, P + 0xC8) == 0x49742400 or r < 0.003:
            view.poke(R + 0xAC, 4, 0)
            view.poke(P + 0x58C, 4, 4)
            view.poke(P + 0xC, 4, rd(view, P + 0xC) | 8)
            view.poke(P + 0x448, 4, rd(view, RP.G_SIM_FRAME))
            view.poke(P + 0xC8, 4, 0)
        elif r < 0.003 + self.hit_rate:
            view.poke(P + 0x58C, 4, 3)
            view.poke(P + 0x11A, 2, rd(view, P + 0x11A, 2) | 8)
            view.poke(R + 0xAC, 4, rng.choice((f32(30.0), f32(120.0), f32(75.0))))
        return Res()

    def on_Player_usePotion(self, args, view, rng):
        P = args[0]
        R = G_PLAYERS + rd(view, P + 0x3C8, 4, True) * REC_SIZE
        if rd(view, P + 0xC) & 0x20000:
            return Res()
        if args[1] == 0:
            view.poke(R + 0xB4, 4, f32(25.0))
            view.poke(R + 0xB8, 4, f32(0.75))
        else:
            view.poke(R + 0xC8, 4, f32(25.0))
            view.poke(R + 0xBC, 4, f32(0.75))
        return Res(1)

    def on_Player_findTarget(self, args, view, rng):
        P = args[0]
        view.poke(P + 0x234, 4, self.nodes[rng.choice(self.creatures)] if rng.random() < 0.6 else 0)
        return Res()

    def on_handle_clear(self, args, view, rng):
        if args[0] != 'stack':
            view.poke(args[0], 4, 0)
        return Res()

    def on_handle_link(self, args, view, rng):
        head, obj = args[0], args[2]
        if head == 'stack':
            return Res()
        if obj in self.nodes and rng.random() < 0.95:
            view.poke(head, 4, self.nodes[obj])
        elif head == self.P + 0x588:
            view.poke(self.held_node + 0xC, 4, obj)
            view.poke(head, 4, self.held_node)
        return Res()

    def on_handle_removeNode(self, args, view, rng):
        return Res(rd(view, args[0] + 0xC))

    def on_iter_begin(self, args, view, rng):
        count = rng.choice((0, 1, 2, 3))
        view.iter_nodes = []
        for node in self.sweep_nodes[:count]:
            view.poke(node + 0xC, 4, rng.choice(self.creatures))
            view.iter_nodes.append(node)
        return self.on_iter_next(args, view, rng)

    def on_iter_next(self, args, view, rng):
        return Res(view.iter_nodes.pop(0) if view.iter_nodes else 0)

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(rng.choice(self.spells) if rng.random() < 0.35 else 0)

    def on_SpellAncestralCall_queryFor(self, args, view, rng):
        return Res(self.flag(rng, 0.7), outs=[rng.choice((0, f32(1.1), f32(1.3)))])

    def on_SpellBattleCry_affects(self, args, view, rng):
        return Res(self.flag(rng, 0.7), outs=[rng.choice((0, f32(1.15), f32(1.25)))])

    def on_SkillBerserkerRage_swingFactor(self, args, view, rng):
        return Res(f=rng.choice((f32(1.0), f32(1.25))))

    def on_SpellBlessed_getStat0(self, args, view, rng):
        return Res(rng.randrange(5, 40))

    def on_SkillRegeneration_getStat0(self, args, view, rng):
        return Res(rng.randrange(5, 40))

    def on_SpellBash_typeinfo(self, args, view, rng):
        return Res(0x909160)

    def on_SpellAncestralCall_typeinfo(self, args, view, rng):
        return Res(0x9091D0)

    def on_SpellShieldBash_typeinfo(self, args, view, rng):
        return Res(0x9094D0)

    def on_SpellBattleCry_typeinfo(self, args, view, rng):
        return Res(0x9095C0)

    def on_SpellBlessed_typeinfo(self, args, view, rng):
        return Res(0x909190)

    def on_pool_new(self, args, view, rng):
        return Res(self.pool.get(args[0], 0) if rng.random() < 0.9 else 0)

    def on_res_find(self, args, view, rng):
        return Res(rng.choice(self.anims) if rng.random() < 0.95 else 0)

    def on_libc_sprintf(self, args, view, rng):
        return Res(outs=[b'#%d' % rng.randrange(1000)])

    def on_text_lookup(self, args, view, rng):
        return Res(self.text)

    def on_hud_countActiveNotices(self, args, view, rng):
        return Res(rng.randrange(4))

    def on_item_getResourceIndex(self, args, view, rng):
        return Res(rng.randrange(3))

    def on_item_getModifiedField1a(self, args, view, rng):
        return Res(rng.randrange(100))

    def on_str_prefixDiffers(self, args, view, rng):
        return Res(rng.randrange(2))

    def on_sound_playOnObject(self, args, view, rng):
        return Res(rng.randrange(64))

    def on_pad_buttonValue(self, args, view, rng):
        return Res(f=rng.choice((0, f32(0.05), f32(0.12), f32(0.2), f32(1.0))))

    def on_model_getAttachPoint(self, args, view, rng):
        base = args[1]
        pos = tuple(f32(ee_emu.raw_to_float(b) + rng.uniform(-30, 80)) for b in base)
        direction = tuple(f32(rng.uniform(-1, 1)) for _ in range(3))
        return Res(outs=[pos, direction])

    def on_world_collectObjectsInBox(self, args, view, rng):
        found = [c for c in self.creatures if rng.random() < 0.45]
        if rng.random() < 0.3:
            found.insert(rng.randrange(len(found) + 1), self.P)
        return Res(len(found), outs=[found])

    def on_world_collectObjectsInArc(self, args, view, rng):
        return Res(outs=[[c for c in self.creatures if rng.random() < 0.3]])

    def on_Player_v20(self, args, view, rng):
        return Res(self.flag(rng, 0.6))

    def on_Player_v39(self, args, view, rng):
        return Res(rng.randrange(6))

    def on_Skill_v1(self, args, view, rng):
        return Res(self.flag(rng, 0.88))

    def on_Skill_v2(self, args, view, rng):
        return Res(rng.choice(self.spells) if rng.random() < 0.5 else 0)

    def on_Skill_v5(self, args, view, rng):
        return Res(f=rng.choice((f32(0.5), f32(3.0), f32(10.0), f32(40.0), f32(999.0))))

    def on_Skill_v10(self, args, view, rng):
        return Res(rng.randrange(1, 4))

    def on_Spell_v4(self, args, view, rng):
        return Res(self.flag(rng, 0.5))

    def on_water_disturb(self, args, view, rng):
        return Res(rng.randrange(3))

    def on_Player_interact(self, args, view, rng):
        return Res(self.flag(rng, 0.1))

    def on_Player_recalcDamage(self, args, view, rng):
        R = G_PLAYERS + rd(view, args[0] + 0x3C8, 4, True) * REC_SIZE
        view.poke(R + 0xCC, 4, rng.randrange(400))
        view.poke(R + 0xD0, 4, rng.randrange(40))
        view.poke(R + 0xD4, 4, 40 + rng.randrange(40))
        return Res()

    def on_inventory_equipItem(self, args, view, rng):
        slot, item = args[0], args[1]
        R = G_PLAYERS + slot * REC_SIZE
        d = rd(view, item)
        if d:
            eq = rd(view, d + 0x1C, 1)
            view.poke(R + 0x43F0 + 4 * eq, 4, item)
            if eq in (0, 2):
                view.poke(R + 0x43F0 + 4 * (2 - eq), 4, 0)
                view.poke(R + 0x4A86, 1, rd(view, d + 0x1E, 1))
        return Res()

    def on_inventory_removeItem(self, args, view, rng):
        slot, index = args[0], args[1]
        R = G_PLAYERS + slot * REC_SIZE
        item = R + 0x130 + index * 0x48
        view.poke(item, 4, 0)
        for off in list(range(0x43F0, 0x4434, 4)) + [0x4434, 0x4438, 0x443C]:
            if rd(view, R + off) == item:
                view.poke(R + off, 4, 0)
        return Res()

    def on_Player_pickAttackAnim(self, args, view, rng):
        view.poke(args[0] + 0x461, 1, rng.randrange(1, 5))
        return Res()

    def on_Player_meleeHit(self, args, view, rng):
        return Res()

    def on_player_countPotions(self, args, view, rng):
        return Res(rng.choice((0, 1, 3, 5, 6, 12)))

    def on_player_itemWeight(self, args, view, rng):
        return Res(f=rng.choice((f32(0.5), f32(2.0), f32(11.25))))

    def on_vars_get(self, args, view, rng):
        return Res(rng.randrange(2))


# ---------------------------------------------------------------------------------------
# The rig: stubs on the interpreter side, callbacks on the model side
# ---------------------------------------------------------------------------------------
def is_stack(v):
    return STACK_LO <= v < STACK_HI


class Rig:
    def __init__(self, elf, seed, net, copy, machine, external=()):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        emu.call(CLASS_SKILLS_INIT, max_steps=3000000)
        self.world = World(emu, self.rng, net, copy, machine)
        self.external = set(external)
        real = set(REAL_OTHER) | {addr for name, addr in REAL_HELPERS.items() if name not in self.external}
        emu.follow = RealSet(real)
        self.real = emu.follow
        self.calls, self.buffers, self.unknown = [], {}, {}
        self.eview = EmuView(emu)
        self.script_rng = None
        self.names = {}
        for name, ext in EXTERNALS.items():
            if ext.addr == 0:
                addr = self.world.stub_for(name)
            elif name in REAL_HELPERS and name not in self.external:
                continue
            else:
                addr = ext.addr
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        for name, addr in REAL_HELPERS.items():
            if name in self.external and name not in EXTERNALS:
                raise ValueError('no EXTERNALS row for ' + name)
        self.blocks = None

    # ---- interpreter side -----------------------------------------------------------------
    def decode(self, name, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind == 'i':
                canon.append(v)
            elif kind == 'p':
                if is_stack(v):
                    canon.append(('buf', self.buffers[v]) if v in self.buffers else 'stack')
                else:
                    canon.append(v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'V':
                canon.append(0 if v == 0 else tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'O':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onhq':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return canon, outs

    def make_stub(self, name, ext):
        def stub(emu):
            mem = emu.mem
            if name == 'libc_sprintf':
                buf, fmt = emu.r[4] & M32, emu.r[5] & M32
                text = mem.cstr(fmt)
                text = text.encode() if isinstance(text, str) else text
                args = (fmt, emu.r[6] & M32 if b'%' in text else None)
                self.calls.append((name, args))
                token = self.world.respond(name, args, self.eview, self.script_rng).outs[0]
                mem.write(buf, token + b'\0')
                self.buffers[buf] = token
                return 0
            canon, outs = self.decode(name, ext, emu)
            args = tuple(canon)
            self.calls.append((name, args))
            res = self.world.respond(name, args, self.eview, self.script_rng)
            given = list(res.outs)
            for kind, ptr in outs:
                value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind in 'nh' else 0))
                if kind in 'oO':
                    if ptr:
                        for j in range(3):
                            mem.w32(ptr + 4 * j, value[j])
                elif kind == 'q':
                    mem.w32(ptr, value)
                elif kind == 'n':
                    for j, obj in enumerate(value):
                        mem.w32(ptr + 4 * j, obj)
                    mem.w32(ptr + 4 * len(value), 0)
                elif kind == 'h':
                    nodes = self.world.arc_nodes
                    for j, obj in enumerate(value):
                        mem.w32(nodes[j], nodes[j + 1] if j + 1 < len(value) else 0)
                        mem.w32(nodes[j] + 0xC, obj)
                    mem.w32(ptr, nodes[0] if value else 0)
            if name in ('iter_begin', 'iter_next'):
                mem.w32((emu.r[4] & M32) + 4, res.ret)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return ee_emu.s32(res.ret)          # a 32-bit result, sign-extended as the callee would leave it
        return stub

    # ---- model side -------------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                return RP.shape_result(name, args, res.ret & M32, res.f & M32, res.outs)
            return answer

    # ---- one tick -----------------------------------------------------------------------------
    def tick(self, tick_seed, trace=False):
        emu, world = self.emu, self.world
        P = world.P
        seed_before = emu.mem.u32(RP.G_RAND_SEED)
        # the model first, on a copy-on-write view
        mview = ModelView(emu.mem)
        model = RP.Tick(mview, P, Rig.Callbacks(self, mview, random.Random(tick_seed)), external=self.external)
        model_error = None
        try:
            outcome = model.run()
        except EmuError as exc:
            model_error, outcome = exc, None
        # the original
        self.calls, self.buffers = [], {}
        self.eview.touched = set()
        self.script_rng = random.Random(tick_seed)
        emu.reset_log()
        emu.trace = [] if trace else None
        emu_error = None
        emu.r[29] = emu.stack_hi - 0x100
        try:
            emu.call(PLAYER_RUN, P, max_steps=400000)
        except EmuError as exc:
            emu_error = exc
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        result = {'model_error': model_error, 'emu_error': emu_error, 'seed_before': seed_before}
        if model_error or emu_error:
            result['fault'] = True
            return result
        result['fault'] = False
        result['calls_ok'] = model.calls == self.calls
        result['model_calls'], result['emu_calls'] = model.calls, self.calls
        ebytes = set()
        for _pc, addr, size, _value in emu.writes:
            ebytes.update(range(addr, addr + size))
        mbytes = set()
        for addr, size, _value in outcome.writes:
            mbytes.update(range(addr, addr + size))
        result['set_ok'] = ebytes == mbytes
        result['only_emu'], result['only_model'] = sorted(ebytes - mbytes), sorted(mbytes - ebytes)
        diff = []
        mem = emu.mem
        for addr in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            a, b = mem.load(addr, 1), mview.load(addr, 1)
            if a != b:
                diff.append((addr, a, b))
        result['values_ok'] = not diff
        result['diff'] = diff
        seed_after = mem.u32(RP.G_RAND_SEED)
        s = seed_before
        for _ in range(outcome.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        result['seed_ok'] = seed_after == outcome.seed == s
        result['draws'] = outcome.draws
        result['returned'] = outcome.returned
        result['writes'] = emu.writes
        return result


# ---------------------------------------------------------------------------------------
# Static shape of the function, for coverage
# ---------------------------------------------------------------------------------------
HELPER_SIZE = {'Player_idleFidget': 600, 'player_canBlock': 124, 'Player_tryBlockMove': 220, 'Player_hasAnim': 112,
               'player_getSkillRank': 104, 'player_getPassiveLevel': 132, 'Player_updateCast': 836,
               'Player_regenHealth': 504, 'Player_regenMana': 652, 'Player_tickEnchantTimers': 504,
               'Player_weaponSwapInput': 876, 'Player_castSkill': 1032, 'Player_usePotion': 2360}


def analyse(mem, start, end, table=()):
    """Basic-block leaders and conditional branch sites of one function body."""
    leaders, sites = {start}, {}
    leaders.update(table)
    for pc in range(start, end, 4):
        w = mem.u32(pc)
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        target = (pc + 4 + (ee_emu.sx16(w) << 2)) & M32
        cond = None
        if op in (4, 5, 20, 21):
            cond = not (op in (4, 20) and rs == 0 and rt == 0)
        elif op in (6, 7, 22, 23):
            cond = True
        elif op == 1 and rt in (0, 1, 2, 3):
            cond = True
        elif op == 17 and rs == 8:
            cond = True
        elif op == 2:
            leaders.add(((pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)))
            continue
        if cond is None:
            continue
        leaders.add(target)
        if cond:
            leaders.add(pc + 8)                 # the fall-through path; after an unconditional
            sites[pc] = target                  # branch the next word is padding unless targeted
    return {a for a in leaders if start <= a < end}, sites


class Coverage:
    """Which basic blocks, instructions and branch outcomes of Player_run and of the
    helpers that run for real were executed (from the interpreter's trace)."""

    def __init__(self, mem):
        self.parts = {}
        table = [mem.u32(0x536260 + 4 * i) for i in range(15)]
        self.parts['Player_run'] = (PLAYER_RUN, FUNC_END) + analyse(mem, PLAYER_RUN, FUNC_END, table)
        for name, addr in REAL_HELPERS.items():
            end = addr + HELPER_SIZE[name]
            self.parts[name] = (addr, end) + analyse(mem, addr, end)
        self.sites = {}
        for _start, _end, _leaders, sites in self.parts.values():
            self.sites.update(sites)
        self.pcs, self.taken, self.not_taken = set(), set(), set()

    def add(self, trace):
        sites = self.sites
        self.pcs.update(trace)
        n = len(trace)
        for i, pc in enumerate(trace):
            target = sites.get(pc)
            if target is None or i + 1 >= n:
                continue
            if trace[i + 1] != pc + 4:
                self.not_taken.add(pc)              # a "likely" branch that skipped its delay slot
            elif i + 2 < n:
                if trace[i + 2] == target:
                    self.taken.add(pc)
                else:
                    self.not_taken.add(pc)

    def numbers(self, name='Player_run'):
        start, end, leaders, sites = self.parts[name]
        inside = {pc for pc in self.pcs if start <= pc < end}
        outcomes = len(self.taken & set(sites)) + len(self.not_taken & set(sites))
        return len(leaders & inside), len(leaders), len(inside), (end - start) // 4, outcomes, 2 * len(sites)

    def missing(self, name='Player_run'):
        start, end, leaders, _sites = self.parts[name]
        return sorted(a for a in leaders if a not in self.pcs)


# ---------------------------------------------------------------------------------------
# The driver: pad input and what the rest of the game would do between ticks
# ---------------------------------------------------------------------------------------
class Driver:
    def __init__(self, rig):
        self.rig, self.world, self.rng = rig, rig.world, rig.rng
        self.mem = rig.emu.mem
        self.held = 0
        self.dead_ticks = 0
        self.plan = []
        self.forced_left, self.forced_state = 0, 0
        self.still = 0
        self.long_death = False
        self.theme = 'none'
        self.theme_index = rig.rng.randrange(len(self.THEMES))
        self.until_focus = 0

    def pad(self):
        rng, mem, world = self.rng, self.mem, self.world
        pad = RP.G_PADS + world.slot * RP.PAD_SIZE
        if not self.plan:
            kind = rng.random()
            n = rng.randrange(1, 40)
            ability = BTN['ability_a'] if rng.random() < 0.5 else BTN['ability_b']
            theme = self.theme
            if theme in ('cast', 'old cast', 'instant', 'old arrows', 'heavy', 'war cry', 'pound', 'multifire') \
                    and kind < 0.45:
                self.plan = [ability] * rng.randrange(1, 60)
                if theme in ('old arrows', 'multifire', 'heavy') and rng.random() < 0.6:
                    self.plan += [ability | BTN['attack']] * rng.randrange(1, 30)
            elif theme == 'two-hand' and kind < 0.4:
                # one long uninterrupted swing with the stick at rest
                self.plan = [BTN['attack']] * 2 + [0] * rng.randrange(60, 130)
                self.still = len(self.plan)
            elif theme in ('melee', 'two-hand', 'heavy', 'instant') and kind < 0.75:
                # a combo: the attack button tapped again and again
                self.plan = []
                for _ in range(rng.randrange(1, 8)):
                    self.plan += [BTN['attack']] * rng.randrange(1, 4) + [0] * rng.randrange(1, 30)
                    if rng.random() < 0.3:
                        self.plan += [ability, 0]
            elif theme == 'leap' and kind < 0.5:
                self.plan = [ability, 0, 0, ability, 0]
            elif kind < 0.25:
                self.plan = [BTN['attack']] * n
            elif kind < 0.4:
                self.plan = [BTN['ability_a'] if rng.random() < 0.5 else BTN['ability_b']] * n
            elif kind < 0.5:
                self.plan = [BTN['block']] * n
            elif kind < 0.55:
                self.plan = [BTN['block'] | BTN['swap']] * 2 + [BTN['block']] * n
            elif kind < 0.6:
                self.plan = [BTN['swap']] + [0] * rng.randrange(3)
            elif kind < 0.66:
                self.plan = [rng.choice((BTN['potion_a'], BTN['potion_b'], BTN['use']))] + [0] * 2
            elif kind < 0.8:
                self.plan = [0] * n
            else:
                self.plan = [rng.getrandbits(16) & 0xFF10 & ~0x1000 for _ in range(n)]
                if rng.random() < 0.5:
                    self.plan = [b | rng.choice(list(BTN.values())) for b in self.plan]
        held = self.plan.pop(0)
        if rng.random() < 0.08:
            held ^= rng.choice(list(BTN.values()))
        pressed = held & ~self.held
        if rng.random() < 0.05:
            pressed |= rng.choice(list(BTN.values()))
        self.held = held
        mem.w32(pad + 8, held)
        mem.w32(pad + 0xC, pressed)
        r = rng.random()
        self.still -= 1
        if r < 0.4 or self.still > 0:
            lx = ly = 0.0
        elif r < 0.5:
            lx, ly = rng.choice((0.005, -0.004)), rng.choice((0.003, 0.0))
        else:
            lx, ly = rng.uniform(-1, 1), rng.uniform(-1, 1)
        mem.wf32(pad + 0x14, lx)
        mem.wf32(pad + 0x18, ly)

    def burst(self, addr, size, value, p_on, p_off=0.25):
        """A word that is 0 most of the time and `value` for short stretches."""
        mem = self.mem
        current = mem.u8(addr) if size == 1 else mem.u32(addr)
        if current == 0:
            if self.rng.random() < p_on:
                current = self.rng.choice(value) if isinstance(value, tuple) else value
            else:
                return
        elif self.rng.random() < p_off:
            current = 0
        else:
            return
        if size == 1:
            mem.w8(addr, current)
        elif size == 2:
            mem.w16(addr, current)
        else:
            mem.w32(addr, current)

    def between(self):
        rng, mem, world = self.rng, self.mem, self.world
        P, R, slot = world.P, world.R, world.slot
        self.until_focus -= 1
        if self.until_focus <= 0 and mem.s32(P + 0x58C) == 2:
            self.until_focus = rng.randrange(50, 160)
            self.focus()
        mem.w32(RP.G_SIM_FRAME, (mem.u32(RP.G_SIM_FRAME) + 1) & M32)
        machine = world.machine
        # words that lock the controls or gate part of the tick: short bursts
        self.burst(RP.G_MENU_LOCKOUT, 4, 60, 0.02 if machine else 0.004)
        self.burst(RP.G_PAUSED, 4, 1, 0.004)
        self.burst(RP.G_LOCAL_MENU_OPEN, 1, 1, 0.05 if machine else 0.005, 0.1)
        if rng.random() < 0.02:
            mem.w32(RP.G_ITEM_LIST_CELLS, world.list_cells if rng.random() < (0.8 if machine else 0.2) else 0)
        self.burst(RP.G_SPELL_SELECTOR + 4 * slot, 4, 1, 0.03 if machine else 0.004, 0.15)
        self.burst(RP.G_RECALL_COUNTDOWN, 1, 30, 0.003)
        self.burst(RP.G_MEDAL_DIALOG_TICKS, 4, 2, 0.003)
        self.burst(RP.G_MEDAL_MISSION, 4, 1, 0.003, 0.05)
        self.burst(RP.G_ARENA_WORD, 4, 1, 0.002)
        self.burst(RP.G_HUD_BYTE, 1, 1, 0.002)
        self.burst(RP.G_POTIONS_ONLY, 4, 1, 0.003, 0.1)
        self.burst(RP.G_LEVEL_FLAGS, 4, (0x100, 0x100, 0x10000000, 0x10000100), 0.006, 0.03)
        self.burst(RP.G_CUTSCENE_ACTIVE, 1, 1, 0.003)
        self.burst(RP.G_PVP_MODE_A, 4, 1, 0.003, 0.02)
        self.burst(RP.G_DEBUG_INVULNERABLE, 4, 1, 0.003, 0.05)
        self.burst(P + 0x464, 1, 1, 0.2 if machine else 0.01, 0.5)
        self.burst(P + 0x231, 1, 1, 0.002, 0.3)
        self.burst(R + 0x4BC8, 1, (1, 3), 0.004, 0.0)
        self.burst(R + 0x4BC9, 1, (2, 5), 0.004, 0.0)
        self.burst(R + 0x4BCA, 2, (1, 40), 0.004, 0.0)
        self.burst(R + 0x4C27, 1, (1, 60), 0.004, 0.0)
        self.burst(P + 0x4B4, 2, (3, 25, 60), 0.002, 0.0)
        if rng.random() < 0.004:
            mem.wf32(RP.G_KILL_PLANE, rng.choice((-100000.0, -100000.0, -100000.0, 1000.0, -50.0)))
        elif rng.random() < 0.2:
            mem.wf32(RP.G_KILL_PLANE, -100000.0)
        if rng.random() < 0.01:
            mem.wf32(RP.G_LIGHT_SCALE, rng.choice((1.0, 0.5, 0.0)))
        if rng.random() < 0.02:
            world.set_alive(rng)
        if rng.random() < 0.1:
            world.place_creatures(rng)
        flags = mem.u32(P + 0xC)
        if flags & 0x400000:
            if mem.u8(R + 0x4BC8) == 0 and rng.random() < 0.2:
                mem.w32(P + 0xC, flags & ~0x400000)
        elif rng.random() < 0.003:
            mem.w32(P + 0xC, flags | 0x400000)
            mem.w8(R + 0x4BC8, rng.choice((0, 2, 6)))
        which = mem.s16(R + 0x4A60)
        if which not in (0, 1):
            if rng.random() < 0.3:
                mem.w16(R + 0x4A60, rng.choice((0, 1)))
        elif rng.random() < 0.002:
            mem.w16(R + 0x4A60, 2)
        if rng.random() < 0.002:
            mem.w8(R + 0x4A84, rng.randrange(15))
            mem.w8(R + 0x4A85, rng.randrange(15))
        if rng.random() < 0.01:
            mem.w32(P + 0x488, R + 0x4440 + rng.randrange(15) * 0x68)
        if rng.random() < 0.03:
            mem.wf32(R + 0xC0, rng.choice((120.0, 120.0, 60.0, 5.0, 0.5, 0.0)))
        if rng.random() < 0.01 and mem.f32(R + 0xAC) > 0.0:
            mem.wf32(R + 0xAC, rng.choice((200.0, 199.0, 60.0, 20.0)))
        if rng.random() < 0.01:
            mem.w64(P + 0xA8, rng.choice((0, 0x2000000000000000)))
        state = mem.s32(P + 0x58C)
        if self.forced_left > 0:
            self.forced_left -= 1
            if self.forced_left == 0 and mem.u32(P + 0x58C) == self.forced_state:
                mem.w32(P + 0x58C, 2)
        elif state == 2 and rng.random() < (0.06 if self.theme == 'leap' else 0.012):
            self.forced_state = rng.choice((6, 7, 9, 0xD, 0xE, 6, 7, 9, 0xD, 0xE, 0xF, 3, 10, 0xC))
            if self.theme == 'leap':
                self.forced_state = 6
            self.forced_left = rng.randrange(2, 14)
            mem.w32(P + 0x58C, self.forced_state)
            mem.w16(P + 0x11A, mem.u16(P + 0x11A) | 0x28)
            mem.w32(P + 0xF0, mem.u32(RP.G_SIM_FRAME) - rng.choice((0, 27, 28, 29)))
            mem.w8(P + 0x47D, rng.choice((0, 0, 1)))
            mem.w8(P + 0x47E, rng.choice((0, 0, 1)))
            mem.wf32(P + 0x30, rng.choice((0.0, 0.0, 200.0)))
            top = P + 0x114 + 0x20 * mem.s8(P + 0x118)
            mem.wf32(top, rng.choice((0.0, 2.0, 4.0, 4.5, 9.0)))
        if rng.random() < 0.004:
            mem.w32(P + 0x4A8, rng.choice((M32, 5)))
        if rng.random() < 0.02:
            # make the next shared draw small (below 0xe2), which is what starts an idle fidget
            want = (rng.randrange(0xE2) << 16) | rng.getrandbits(16)
            mem.w32(RP.G_RAND_SEED, ((want - 0x3C6EF35F) * pow(0x19660D, -1, 1 << 32)) & M32)
        if rng.random() < 0.01:
            mem.w8(P + 0x118, rng.choice((4, 4, 5, 6)))
        if rng.random() < 0.003:
            mem.w32(P + 0x588, rng.choice((0, world.held_node)))
            mem.w32(world.held_node + 0xC, rng.choice((0, world.spells[0])))
        for s in range(4):
            if mem.f32(G_PLAYERS + s * REC_SIZE + 0xAC) <= 0.0:
                mem.w16(RP.G_DEAD_COUNTDOWN + 2 * s, max(mem.s16(RP.G_DEAD_COUNTDOWN + 2 * s) - 1, 0))
        # respawn: player_respawn 0x1bd040 deletes the object and makes a new one
        if mem.s32(P + 0x58C) == 4:
            self.dead_ticks += 1
            if self.dead_ticks > 185 + rng.randrange(40) or (self.dead_ticks > 12 and not self.long_death
                                                             and rng.random() < 0.15):
                self.respawn()
        else:
            self.dead_ticks = 0
            self.long_death = rng.random() < 0.25

    THEMES = ('melee', 'two-hand', 'bow', 'thrown', 'cast', 'old cast', 'instant', 'old arrows', 'heavy',
              'war cry', 'pound', 'multifire', 'leap', 'none', 'melee', 'bow', 'cast', 'two-hand', 'old cast',
              'thrown', 'old arrows', 'heavy')

    def focus(self):
        """Re-equip the player and bind abilities so that one family of paths gets
        exercised for a while."""
        rng, mem, world = self.rng, self.mem, self.world
        slot, R, P = world.slot, world.R, world.P
        theme = self.THEMES[self.theme_index % len(self.THEMES)]        # every theme in turn
        self.theme_index += 1
        self.theme = theme
        world.hit_rate = 0.004 if theme in ('two-hand', 'heavy', 'old arrows', 'old cast') else 0.02
        if rng.random() < 0.25:
            hp = mem.u32(R + 0xAC)
            world.init_record(slot, rng)
            mem.w32(R + 0xAC, hp)
        if theme == 'none':
            return
        weapon = {'melee': rng.choice(('sword', 'dual', 'fist', 'spear', 'sword2h')), 'two-hand': 'axe2h',
                  'bow': 'bow', 'thrown': 'thrown', 'old arrows': rng.choice(('bow', 'bow', 'sword')),
                  'multifire': 'bow', 'heavy': rng.choice(('sword', 'axe2h', 'sword2h', 'bow')),
                  'war cry': rng.choice(('sword', 'fist', 'axe2h', 'sword2h', 'spear', 'dual', 'bow'))}.get(theme)
        if weapon is None:
            weapon = rng.choice(('sword', 'axe2h', 'sword2h', 'spear', 'bow', 'thrown', 'dual', 'fist'))
        world.equip(slot, weapon, rng)
        if theme in ('two-hand', 'heavy') and rng.random() < 0.6:
            item = R + 0x130                             # a fast weapon: modifier 0x14 (4.5% each)
            mem.w16(item + 0x24, 0x14)
            mem.w16(item + 0x26, rng.choice((8, 11, 14)))
        a, b = rng.sample(range(15), 2)
        mem.w8(R + 0x4A84, a)
        mem.w8(R + 0x4A85, b)
        if theme in ('cast', 'bow', 'thrown', 'melee', 'two-hand'):
            world.set_ability(slot, a, True, rng.choice(SKILL_IDS[:8]), rng.choice((0, 0, 1, 2, 8)), rng)
            world.set_ability(slot, b, True, rng.choice(SKILL_IDS[:8]), rng.choice((0, 1, 7, 8)), rng)
        elif theme == 'old cast':
            for index in (a, b):
                sid = rng.choice((9, 0x19, 0x15, 0x1A, 0x1B, 0x7, 0x30))
                kind = {9: 1, 0x7: 2, 0x30: rng.choice((1, 2))}.get(sid, 0)
                world.set_ability(slot, index, False, sid, kind, rng, rng.choice((2.0, 10.0)))
        elif theme == 'instant':
            world.set_ability(slot, a, True, rng.choice(SKILL_IDS[:8]), 7, rng)
            world.set_ability(slot, b, True, rng.choice(SKILL_IDS[:8]), rng.choice((7, 8, 0)), rng)
        elif theme == 'old arrows':
            world.set_ability(slot, a, False, rng.choice((4, 5, 6, 0x13, 0x12)), 0, rng, rng.choice((2.0, 10.0)))
            world.set_ability(slot, b, False, rng.choice((4, 5, 6, 0x13, 0x12)), 0, rng, 2.0, rng.choice((0, 5)))
        elif theme == 'heavy':
            world.set_ability(slot, a, False, 0x25, 0, rng)
            world.set_ability(slot, b, False, rng.choice((0x25, 0xE)), 0, rng)
        elif theme == 'war cry':
            world.set_ability(slot, a, False, 0xE, 0, rng, 2.0)
            world.set_ability(slot, b, False, 0xC, 0, rng, 2.0)
        elif theme == 'pound':
            world.set_ability(slot, a, False, 0xC, 0, rng, 2.0)
            world.set_ability(slot, b, False, 0xE, 0, rng, 999.0)
        elif theme == 'multifire':
            world.set_ability(slot, a, True, 0x2E, 8, rng)
            world.set_ability(slot, b, True, rng.choice((0x2E, 0x30)), 8, rng)
        elif theme == 'leap':
            world.set_ability(slot, a, True, 0x31, 0, rng)
            world.set_ability(slot, b, True, 0x22, 0, rng)
        mem.wf32(R + 0xC0, rng.choice((120.0, 120.0, 120.0, 30.0, 5.0)))
        mem.wf32(R + 0xC4, 120.0)
        mem.w16(P + 0x4AE, 0)
        mem.w32(P + 0x374, 0)
        mem.w16(P + 0x4B2, rng.choice((3, 10, 40)))

    def respawn(self):
        rng, mem, world = self.rng, self.mem, self.world
        world.init_object(world.P, world.slot, rng)
        mem.wf32(world.R + 0xAC, 100.0)
        mem.w16(world.P + 0x4B4, 90 if world.net else 60)
        mem.w16(RP.G_DEAD_COUNTDOWN + 2 * world.slot, 240)
        self.dead_ticks = 0


# ---------------------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------------------
def describe_calls(a, b):
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x != y:
            return 'call %d: model %s | original %s' % (i, fmt_call(x), fmt_call(y))
    return ''


def fmt_call(c):
    if c is None:
        return '(none)'
    out = []
    for a in c[1]:
        if isinstance(a, int):
            out.append('%x' % a)
        elif isinstance(a, tuple) and a and isinstance(a[0], int):
            out.append('(' + ','.join('%x' % x for x in a) + ')')
        else:
            out.append(repr(a))
    return '%s(%s)' % (c[0], ', '.join(out))


def where(world, addr):
    P, R = world.P, world.R
    if P <= addr < P + 0x600:
        return 'player+0x%x' % (addr - P)
    if R <= addr < R + REC_SIZE:
        return 'record+0x%x' % (addr - R)
    return '0x%x' % addr


def run(elf, name, seed, net, copy, machine, ticks, coverage, states, external=()):
    rig = Rig(elf, seed, net, copy, machine, external)
    driver = Driver(rig)
    world, mem = rig.world, rig.emu.mem
    if coverage[0] is None:
        coverage[0] = Coverage(mem)
    cov = coverage[0]
    bad = {'calls': [], 'writes': [], 'seed': [], 'exit': []}
    count = faults = 0
    world.place_creatures(rig.rng)
    for t in range(ticks):
        driver.pad()
        state = mem.u32(world.P + 0x58C)
        result = rig.tick(seed * 1000003 + t, trace=True)
        if rig.emu.trace:
            cov.add(rig.emu.trace)
        row = states.setdefault(state, [0, 0])
        if result['fault']:
            faults += 1
            if (result['model_error'] is None) != (result['emu_error'] is None):
                bad['exit'].append('tick %d state %d: model %r original %r'
                                   % (t, state, result['model_error'], result['emu_error']))
                row[1] += 1
            world.init_object(world.P, world.slot, rig.rng)
            world.init_record(world.slot, rig.rng)
            mem.wf32(world.R + 0xAC, 100.0)
            driver.between()
            continue
        count += 1
        row[0] += 1
        ok = True
        if not result['calls_ok']:
            ok = False
            bad['calls'].append('tick %d state %d: %s' % (t, state, describe_calls(result['model_calls'],
                                                                                    result['emu_calls'])))
        if not (result['set_ok'] and result['values_ok']):
            ok = False
            text = 'tick %d state %d:' % (t, state)
            if result['only_emu']:
                text += ' only original stores %s;' % sorted({where(world, a) for a in result['only_emu']})[:6]
            if result['only_model']:
                text += ' only model stores %s;' % sorted({where(world, a) for a in result['only_model']})[:6]
            if result['diff']:
                text += ' values differ at %s' % [(where(world, a), '%02x' % x, '%02x' % y)
                                                  for a, x, y in result['diff'][:8]]
            bad['writes'].append(text)
        if not result['seed_ok']:
            ok = False
            bad['seed'].append('tick %d state %d: model draws %d' % (t, state, result['draws']))
        if not ok:
            row[1] += 1
            if OPTIONS['trace_first']:
                print('first mismatch in run %s, tick %d, state %d' % (name, t, state))
                for key in ('calls', 'writes', 'seed'):
                    if bad[key]:
                        print('  ' + bad[key][-1])
                print('  model calls:')
                for c in result['model_calls']:
                    print('    ' + fmt_call(c))
                print('  original calls:')
                for c in result['emu_calls']:
                    print('    ' + fmt_call(c))
                sys.exit(1)
        driver.between()
    if rig.unknown:
        bad['calls'].append('calls to addresses that are neither real nor known stubs: %s'
                            % {hex(a): n for a, n in rig.unknown.items()})
    text = '%s, %s, %s' % ('prediction copy' if copy else 'real player', 'net game' if net else 'offline',
                           'machine B' if machine else 'machine A')
    report(name + ' calls', len(bad['calls']), count, 'callbacks in order with arguments; ' + text, bad['calls'])
    report(name + ' writes', len(bad['writes']), count, 'bytes stored and their final values', bad['writes'])
    report(name + ' seed', len(bad['seed']), count, 'shared seed and number of draws', bad['seed'])
    report(name + ' faults', len(bad['exit']), faults,
           'ticks where the original read unmapped memory (model must fault too)', bad['exit'])
    return count


PICK_ATTACK_ANIM = 0x1BBA88


def check_pick_attack_anim(elf, rng):
    """Player_pickAttackAnim 0x1bba88 is a callback of the model.  What the model's
    documentation says about it is checked here on the original alone: it advances the
    shared seed exactly once whatever happens, its only other store is the variant byte
    player +0x461, and the variant depends neither on the seed nor on the answer of the
    one call it makes, net_isLocalSlot at 0x1bbfe4, whose result it discards (it comes
    from g_simFrame, the record's model index +0x54, the weapon class and the old
    variant)."""
    emu = EE(elf)
    mem = emu.mem
    player = emu.alloc(0x600)
    count, bad, examples = 0, 0, []
    for _ in range(2500 if not OPTIONS['quick'] else 300):
        slot = rng.randrange(4)
        R = G_PLAYERS + slot * REC_SIZE
        mem.w32(player + 0x3C8, slot)
        mem.w32(R + 0x54, rng.randrange(12))
        cls = rng.randrange(8)
        frame, old = rng.getrandbits(32), rng.randrange(0, 7)
        results = []
        for local, seed in enumerate((rng.getrandbits(32), rng.getrandbits(32))):
            emu.stub(0x13E150, ret=local, name='net_isLocalSlot')
            mem.w32(RP.G_RAND_SEED, seed)
            mem.w32(RP.G_SIM_FRAME, frame)
            mem.w8(player + 0x461, old)
            emu.follow = RealSet(())
            emu.reset_log()
            emu.call(PICK_ATTACK_ANIM, player, cls)
            stores = {addr for _pc, addr, size, _v in emu.writes for addr in range(addr, addr + size)}
            ok = mem.u32(RP.G_RAND_SEED) == (seed * 0x19660D + 0x3C6EF35F) & M32
            ok = ok and stores <= set(range(RP.G_RAND_SEED, RP.G_RAND_SEED + 4)) | {player + 0x461}
            ok = ok and [c.target for c in emu.calls] == [0x13E150]
            results.append((ok, mem.u8(player + 0x461)))
        count += 1
        if not (results[0][0] and results[1][0] and results[0][1] == results[1][1]):
            bad += 1
            examples.append('slot %d class %d frame %x old %d: %r' % (slot, cls, frame, old, results))
    report('pickAttackAnim (original only)', bad, count,
           'one shared draw per call, only +0x461 stored, variant independent of the seed and of the '
           'local-slot answer', examples)


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
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_player: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_player: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    ticks = OPTIONS['ticks'] // 10 if OPTIONS['quick'] else OPTIONS['ticks']
    started = time.time()
    coverage, states = [None], {}
    total = 0
    for index, (copy, net, machine) in enumerate([(c, n, m) for c in (0, 1) for n in (0, 1) for m in (0, 1)]):
        name = '%s/%s/%s' % ('copy' if copy else 'real', 'net' if net else 'off', 'B' if machine else 'A')
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in name.lower():
            continue
        total += run(elf, name, OPTIONS['seed'] + index, net, copy, machine, ticks, coverage, states)
    if not OPTIONS['filter'] or 'pick' in OPTIONS['filter'].lower():
        check_pick_attack_anim(elf, random.Random(OPTIONS['seed']))
    print()
    print('action state at the start of the tick: ticks compared / ticks with any mismatch')
    for state in sorted(states):
        print('  state %2d: %7d / %d' % (state, states[state][0], states[state][1]))
    if coverage[0] is not None:
        print('coverage by the original as executed here (basic blocks, instructions, branch outcomes):')
        for part in ['Player_run'] + sorted(REAL_HELPERS):
            b, bt, i, it, o, ot = coverage[0].numbers(part)
            print('  %-26s blocks %4d of %4d (%5.1f%%)  instructions %4d of %4d (%5.1f%%)  outcomes %4d of %4d (%5.1f%%)'
                  % (part, b, bt, 100.0 * b / bt, i, it, 100.0 * i / it, o, ot, 100.0 * o / max(ot, 1)))
        if OPTIONS['verbose']:
            gaps = coverage[0].missing()
            print('  Player_run blocks never entered (%d): %s' % (len(gaps), ' '.join('%06x' % a for a in gaps)))
    print('%d ticks compared in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
