#!/usr/bin/env python3
"""difftest_messages.py - compare tools/ref_messages.py with the game's own message handlers.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_messages.py [path/to/SLUS_209.73] [--quick] [--seed N] [--steps N]
                                     [-k TEXT] [-v]

    --quick       a tenth of the messages
    --seed N      seed of the random runs (default 20973); a seed repeats exactly
    --steps N     messages per run (default 2500; there are 8 runs)
    -k TEXT       only the runs and properties whose name contains TEXT
    -v            print the first mismatches of every failing property

What is compared
    The ORIGINAL handlers are executed by tools/ee_emu.py (an instruction interpreter, not a
    console) exactly as the lockstep tick calls them: handler[channel](buffer, length), with
    the handler taken from the game's own table after the game's own seven registration
    calls.  The players, bags, equipment, ability records, panels and grid copies are
    constructed in the interpreter's memory; a seeded driver sends long random sequences of
    messages - as a sender would build them, stale (an item that is no longer there, an
    index past the count, another player's item) and malformed (wrong type byte, out of
    range fields, short length with the previous message's bytes behind it) - and changes
    the world between messages (new items, points, a dead or departed player, the machine's
    own menu state).  Each message goes through tools/ref_messages.py first, on a
    copy-on-write view of the same memory.  For every message these must be equal:
      calls    the sequence of calls to everything outside the model, with arguments
      writes   the set of bytes stored outside the stack, and their final values
      seed     the shared seed 0x404464 afterwards (only callees draw; the stubs do it)
      end      whether the handler returned, or stopped on memory nobody mapped
    Runs differ in the number of players (1-4), offline or net game, and which machine
    executes: the owner's (the slot is local), another one, a machine with two local
    players; with the local menu flag and the grid pointer set both ways.

    Three more properties:
      channel ids   the seven registration functions give the ids of the channel table,
                    and a second registration of a handler returns the first id
      senders       every sender function is run for real; the bytes it queues are the
                    ones the model's encoders (msg_...) give, whatever was on the stack
      K2            Player_usePotion 0x1b9cb8 itself, with the inventory screen open on the
                    owner's machine, then its drop message through the handler on both
                    machines: what the message names and what it removes

What runs for real and what is a stub
    Real: the functions listed in REAL below (the handlers, the inventory operations,
    net_sendGameMsg and net_registerMsgHandler, the equip test and the item value), the C
    library and the software floating point (0x3a5000-0x3c0000).  Everything else is a
    recording stub answered by a seeded script; the model's callbacks get the same answers.
    A call to an address that is neither real nor a known stub is reported as a failure.
    Floats are compared as 32-bit patterns under the interpreter's 'ps2' model.
"""
import os
import random
import struct
import sys
import zlib

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_items as RI                          # noqa: E402
import ref_messages as RM                       # noqa: E402
from ref_messages import EXTERNALS, G_PLAYERS, REC_SIZE, M32      # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
CLASS_SKILLS_INIT = 0x1AC7A8
DBG_PRINTF = 0x355490
SPRINTF = 0x3B7EF0
STUB_BASE = 0x00F00000
REGISTRARS = (0x19B4B4, 0x31FD38, 0x22F974, 0x1DC194, 0x1C59A8, 0x31DA4C, 0x1D13A0)
G_SHOP_STOCK = 0x866E78

# name -> (entry, size in bytes): what the interpreter runs for real and coverage is counted on
REAL = {
    'invmsg_dispatch': (0x1BFDB0, 508), 'inventory_dropItem': (0x1C4310, 1548),
    'inventory_equipItem': (0x1C27C0, 1852), 'inventory_unequipItem': (0x1C2F20, 1028),
    'inventory_unrefItem': (0x1C3350, 200), 'inventory_removeItem': (0x1C1CB0, 1128),
    'inventory_giveItem': (0x1C1868, 1084), 'inventory_onJoinPanel': (0x1C0360, 388),
    'inventory_onStatPoint': (0x1C2548, 252), 'inventory_onSkillPoint': (0x1C2648, 372),
    'game_sendCharacterToLobby': (0x1EB5C8, 300), 'player_getSkillRank': (0x1BF330, 104),
    'player_setSkillRank': (0x1BF3A0, 148), 'player_getPassiveLevel': (0x1BED48, 132),
    'player_raisePassiveLevel': (0x1BEDD0, 116), 'player_addSkillAbility': (0x1D32E4, 456),
    'player_rebuildAbilities': (0x1D34AC, 960), 'item_sameIdentityFields': (0x108924, 68),
    'hud_onMsg': (0x1D8CA0, 1456), 'hud_onQuickSlot': (0x1DE28C, 180), 'hud_onAssignSpell': (0x1DE61C, 680),
    'hud_onQuickCastWarn': (0x1DE340, 172), 'net_maskLocalButtons': (0x13E540, 80),
    'recall_execute': (0x18C230, 692), 'hud_loadLevelBody': (0x18CB80, 124),
    'shop_onMsg': (0x1C5D28, 588), 'shop_buy': (0x1D1240, 236),
    'net_sendGameMsg': (0x13DB38, 248), 'net_registerMsgHandler': (0x13DA98, 152),
}
JUMP_TABLES = {'invmsg_dispatch': (0x537CC0, 11), 'hud_onMsg': (0x53C350, 14)}
# real, but another model's or trivial: not in the coverage table
REAL_OTHER = {0x1D1380, 0x1BF5A0, 0x1C4948, 0x1024A8, 0x103EC8, 0x104100, 0x19E884, 0x19E93C, 0x19E8E4,
              0x103F88, 0x1041F0, 0x1046B4}
HANDLER_OF = {'inventory': 'invmsg_dispatch', 'game': 'hud_onMsg', 'shop': 'shop_onMsg'}

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False, 'steps': 2500}
RESULTS = []


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-30s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:6]:
            print('        ' + str(line)[:1500])
    sys.stdout.flush()


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class RealSet:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or LIB_LO <= target < LIB_HI


class EmuView:
    """The interpreter's memory as the script sees it: pokes are remembered so their bytes
    are compared too."""

    def __init__(self, emu):
        self.mem, self.touched = emu.mem, set()

    def load(self, addr, size):
        return self.mem.load(addr, size)

    def poke(self, addr, size, value):
        self.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))


class ModelView(RM.Memory):
    def __init__(self, under):
        RM.Memory.__init__(self, under)
        self.touched = set()

    def poke(self, addr, size, value):
        RM.Memory.poke(self, addr, size, value)
        self.touched.update(range(addr, addr + size))


def view_cstr(view, addr, limit=600):
    out = bytearray()
    while len(out) < limit:
        b = view.load((addr + len(out)) & M32, 1)
        if b == 0:
            break
        out.append(b)
    return bytes(out)


def view_wstr(view, addr, limit=600):
    out = bytearray()
    while len(out) < limit:
        c = view.load((addr + len(out)) & M32, 2)
        if c == 0:
            break
        out += bytes((c & 0xFF, c >> 8))
    return bytes(out)


# ---------------------------------------------------------------------------------------
# The scripted world: every answer a stub gives, the same for both sides
# ---------------------------------------------------------------------------------------
class Script:
    def __init__(self, emu):
        self.emu = emu
        self.texts = {}
        self.local = [0]
        self.active = {0, 1, 2, 3}
        self.answers = {}
        self.blocks, self.block_at = [], 0
        self.spot = (0, 0, 0)
        self.spot_draws = 0

    def begin_side(self):
        self.block_at = 0

    def text(self, key):
        """A 16-bit string for a text key, made on first use."""
        if key not in self.texts:
            wide = b''.join(bytes((c, 0)) for c in b'<' + key[:20] + b'>') + b'\0\0'
            addr = self.emu.alloc(len(wide) + 2, align=4)
            self.emu.mem.write(addr, wide)
            self.texts[key] = addr
        return self.texts[key]

    def draw(self, view, n):
        seed = view.load(RM.G_RAND_SEED, 4)
        for _ in range(n):
            seed = (seed * 0x19660D + 0x3C6EF35F) & M32
        view.poke(RM.G_RAND_SEED, 4, seed)

    def respond(self, name, args, view):
        """-> (integer result, out vector or None)."""
        a = self.answers
        if name == 'net_isLocalSlot':
            return int(ee_emu.s32(args[0]) in self.local), None
        if name == 'net_getLocalPlayerSlot':
            n = ee_emu.s32(args[0])
            return (self.local[n] if 0 <= n < len(self.local) else -1), None
        if name == 'net_isSlotActive':
            return int(ee_emu.s32(args[0]) in self.active), None
        if name == 'res_find':
            return 0x00E00000 | (zlib.crc32(args[0] + b'/' + args[1]) & 0xFFFF) | 1, None
        if name == 'text_lookup':
            return self.text(args[0]), None
        if name == 'pool_new':
            block = self.blocks[self.block_at] if self.block_at < len(self.blocks) else 0
            self.block_at += 1
            return block, None
        if name == 'world_findFreeSpot':
            self.draw(view, self.spot_draws)
            return 0, self.spot
        if name in ('ItemProp_ctor2', 'RecallEffect_ctor'):
            self.draw(view, 1)
            return 0, None
        if name == 'player_respawn':
            self.draw(view, 3)
            return 0, None
        return a.get(name, 0), None


class Stats:
    def __init__(self):
        self.count = self.calls = self.sets = self.values = self.seed = self.end = 0
        self.faults = self.unknown = 0
        self.examples = {'calls': [], 'writes': [], 'values': [], 'seed': [], 'end': [], 'unknown': []}
        self.kinds = {}


# ---------------------------------------------------------------------------------------
# The rig: one interpreter, one constructed game
# ---------------------------------------------------------------------------------------
class Rig:
    def __init__(self, elf, seed, players, net, machine):
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        self.mem = emu.mem
        emu.mem.map(0, 0x1000)                  # low memory: what a null pointer reads
        emu.call(CLASS_SKILLS_INIT, max_steps=3000000)
        self.tables = RI.Tables(elf)
        self.players, self.net, self.machine = players, net, machine
        self.script = Script(emu)
        self.trace = set()
        self.registered = self.register()
        real = {entry for entry, _size in REAL.values()} | REAL_OTHER
        emu.follow = self.real = RealSet(real)
        self.calls, self.unknown = [], {}
        self.names = {}
        self.eview = EmuView(emu)
        self.vstub = STUB_BASE
        for name, ext in EXTERNALS.items():
            addr = ext.addr if ext.addr else self.vstub
            if addr in real:
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        emu.stub(DBG_PRINTF, ret=0)
        self.names[DBG_PRINTF] = None
        emu.stub(SPRINTF, function=self.sprintf)
        self.names[SPRINTF] = None
        self.buf = emu.alloc(0x200)
        self.build()

    # ---- start-up -------------------------------------------------------------------------
    def register(self):
        """The game's own registration functions, in the order of 0x323e50-0x323e80."""
        emu = self.emu
        emu.trace = []
        for fn in REGISTRARS:
            emu.call(fn)
        self.again = emu.call(0x13DA98, RM.H_INVENTORY)    # a second registration finds the first
        self.trace = set(emu.trace)
        emu.trace = None
        return [(family, emu.mem.u32(where), emu.mem.u32(RM.G_MSG_HANDLERS + 4 * emu.mem.u32(where)), handler)
                for family, handler, where in RM.REGISTRATION]

    def channel(self, family):
        for name, ident, _stored, _handler in self.registered:
            if name == family:
                return ident
        raise KeyError(family)

    # ---- interpreter side ---------------------------------------------------------------------
    def decode(self, ext, emu):
        mem, canon, out = emu.mem, [], None
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind in 'ip':
                canon.append(v)
            elif kind == 's':
                canon.append(view_cstr(self.eview, v))
            elif kind == 'w':
                canon.append(view_wstr(self.eview, v))
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'o':
                out = v
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return tuple(canon), out

    def make_stub(self, name, ext):
        def stub(emu):
            args, out = self.decode(ext, emu)
            self.calls.append((name, args))
            ret, vec = self.script.respond(name, args, self.eview)
            if out is not None and vec is not None:
                for j in range(3):
                    emu.mem.w32(out + 4 * j, vec[j])
            return ee_emu.s32(ret)
        return stub

    def sprintf(self, emu):
        """The handlers use sprintf only to copy a sound name that has no conversion in it.
        The library's own version keeps state outside the game's data, so it is replaced."""
        text = view_cstr(self.eview, emu.r[5] & M32)
        if b'%' in text:
            raise EmuError('sprintf with a conversion: %r' % text)
        emu.mem.write(emu.r[4] & M32, text + b'\0')
        return len(text)

    # ---- model side -----------------------------------------------------------------------------
    class Callbacks:
        def __init__(self, rig, view):
            self.rig, self.view = rig, view

        def get(self, name):
            ext, rig, view = EXTERNALS[name], self.rig, self.view

            def answer(*args):
                ret, vec = rig.script.respond(name, canon_model(ext, args, view), view)
                if 'o' in ext.ints:
                    return vec
                return ret & M32
            return answer

    # ---- construction -----------------------------------------------------------------------------
    def rec(self, slot):
        return G_PLAYERS + slot * REC_SIZE

    def build(self):
        emu, mem, rng = self.emu, self.mem, self.rng
        t = self.tables
        self.defs = {}
        for d in t.defs:
            self.defs.setdefault((d.category, d.slot), []).append(d)
        self.kinds = sorted(self.defs)
        mem.w32(RM.G_NUM_PLAYERS, self.players)
        mem.w8(RM.G_NETWORK_MODE, 1 if self.net else 0)
        mem.w32(RM.G_DIFFICULTY, 1)
        mem.w32(RM.G_SIM_FRAME, rng.randrange(1, 100000))
        mem.w32(RM.G_RAND_SEED, rng.getrandbits(32))
        self.skill_ids = [i for i in range(1, 0x66) if mem.u32(RM.G_SKILL_TABLE + 4 * i)]
        self.passive_ids = [i for i in self.skill_ids if mem.u32(mem.u32(RM.G_SKILL_TABLE + 4 * i) + 8) == 3]
        self.natural_passives = len(self.passive_ids)
        if not self.passive_ids:                # none in the table: turn three skills into kind 3
            self.passive_ids = rng.sample(self.skill_ids, 3)
            for i in self.passive_ids:
                mem.w32(mem.u32(RM.G_SKILL_TABLE + 4 * i) + 8, 3)
        self.vtable = emu.alloc(0x100)
        mem.w16(self.vtable + 0x10, 0)
        mem.w32(self.vtable + 0x14, self.vstub)
        self.objects = []
        for slot in range(4):
            obj = emu.alloc(0x590)
            self.objects.append(obj)
            self.init_object(slot)
            self.init_record(slot)
        # the machine's grid copies, with one panel of slack in front for panel -1
        self.grid_block = emu.alloc(5 * 0x23988 + 0x100)
        self.grid = self.grid_block + 0x23988
        for panel in range(2):
            P = RM.G_ITEM_PANELS + panel * RM.PANEL_SIZE
            mem.w32(P + 0x34, rng.randrange(4))
            mem.w32(P + 0x38, rng.randrange(4))
            mem.w32(P + 0x70, rng.randrange(0, 9))
        mem.w32(RM.G_PANEL_ROWS, rng.randrange(1, 60))
        # shop stock: a few records in each of the three lists
        # the recall potion and the two single-copy items, by the names the code compares with
        self.special_names = [view_cstr(self.eview, a) for a in (RM.S_RECALL_NAME, RM.S_UNIQUE_A, RM.S_UNIQUE_B)]
        self.stock, self.special_stock = [], []
        for lst in range(3):
            base = G_SHOP_STOCK + lst * 0x1208
            special = [d for d in t.defs if d.name in self.special_names and d.category == lst]
            for i in range(12):
                d = special[i] if i < len(special) else self.pick_def(rng, category=lst)
                self.write_item(base + i * 0x48, d, rng, i)
                self.stock.append(base + i * 0x48)
                if i < len(special):
                    self.special_stock.append(base + i * 0x48)
            mem.w32(base + 0x1200, 12)
        self.set_machine()

    def set_machine(self):
        """Which slots this machine owns, and its menu state."""
        mem, rng, s = self.mem, self.rng, self.script
        if self.machine == 'owner':
            s.local = list(range(self.players)) if not self.net else [0]
        elif self.machine == 'other':
            s.local = [self.players - 1] if self.net and self.players > 1 else [3]
        else:                                   # 'two': two local players
            s.local = [0, 1]
        s.active = set(range(self.players))
        self.menu_open = rng.random() < 0.5
        mem.w8(RM.G_LOCAL_MENU_OPEN, 1 if self.menu_open else 0)
        mem.w32(RM.G_ITEM_LIST_CELLS, self.grid if rng.random() < 0.6 else 0)

    def init_object(self, slot):
        mem, rng, obj = self.mem, self.rng, self.objects[slot]
        mem.write(obj, bytes(0x590))
        mem.w32(obj + 0xC, rng.getrandbits(32) & 0x00FF00FF)
        for j in range(3):
            mem.w32(obj + 0x10 + 4 * j, f32(rng.uniform(-500, 500)))
        mem.w16(obj + 0x38, rng.randrange(0x10000))
        mem.w32(obj + 0x48, self.vtable)
        mem.w32(obj + 0x3C8, slot)
        mem.w8(obj + 0x47A, rng.randrange(1, 255))
        mem.w32(obj + 0x58C, 2)

    def pick_def(self, rng, category=None):
        while True:
            kind = rng.choice(self.kinds)
            if category is None or kind[0] == category:
                return rng.choice(self.defs[kind])

    def write_item(self, addr, d, rng, stamp):
        item = RI.Item(d)
        item.count = d.count if d.count > 0 else 1
        if d.flags & 0x100 or d.slot == 8:
            item.count = rng.choice([1, 1, 2, 3, 19, 20, 21, 45])
        item.flags = d.flags
        if rng.random() < 0.5:                 # a material, so every sound is reached
            item.flags |= rng.choice([0x800000, 0x200000, 0x400000, 0x40000, 0x100000, 0x80000, 0x1000000,
                                      0x800000 | 0x20000000, 0x40000 | 0x20000000])
        if rng.random() < 0.1:                 # no material at all
            item.flags &= ~0x27FC0000
        if rng.random() < 0.3:
            item.flags |= 0x100
        if rng.random() < 0.05:
            item.flags ^= rng.choice([0x10000000000, 0x20000000000, 0x1000000000])
        if rng.random() < 0.25:
            code = rng.choice([0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x27, 0x28])
            item.set_modifier(code, rng.randrange(0, 8) if code in (0x13, 0x27, 0x28) else rng.randrange(0, 40))
        if rng.random() < 0.2:
            item.prefix = rng.randrange(len(self.tables.prefixes))
        data = bytearray(item.pack())
        struct.pack_into('<h', data, 0x22, stamp)
        self.mem.write(addr, bytes(data))

    def init_record(self, slot):
        mem, rng = self.mem, self.rng
        R = self.rec(slot)
        mem.write(R, bytes(REC_SIZE))
        mem.write(R, (b'Hero%d' % slot) + b'\0')
        mem.write(R + 0x24, rng.choice([b'None\0', b'hub\0', b'strife\0']))
        mem.w32(R + 0x50, rng.randrange(7))
        level = rng.randrange(1, 50)
        mem.w8(R + 0x58, level)
        mem.w8(R + 0x59, level + rng.randrange(0, 2))
        for i in range(4):
            mem.w32(R + 0x78 + 4 * i, rng.randrange(10, 60))
            mem.w32(R + 0x90 + 4 * i, rng.randrange(10, 70))
        mem.w32(R + 0xB0, f32(rng.uniform(50, 400)))
        mem.w32(R + 0xAC, f32(rng.uniform(1, 50)))
        mem.w32(R + 0xC4, f32(rng.uniform(20, 300)))
        mem.w32(R + 0xC0, f32(rng.uniform(0, 20)))
        mem.w32(R + 0xE4, rng.choice([0, 500, 5000, 250000, 99999990]))
        mem.w32(R + 0xE8, rng.randrange(0, 6))
        mem.w8(R + 0xEC, rng.randrange(0, 5))
        mem.w8(R + 0xEE, 1)
        for i in range(0x30):
            mem.w8(R + 0xEF + i, rng.choice([0, 0, 0, 1, 2, 19, 20]))
        mem.w32(R + 0x124, f32(rng.uniform(150, 300)))
        mem.w32(R + 0x43D4, M32)
        mem.w32(R + 0x43D8, self.objects[slot])
        for bag in range(3):
            for _ in range(rng.randrange(3, 14)):
                self.add_item(slot, bag)
        for i in range(15):
            A = R + 0x4440 + i * 0x68
            mem.w16(A + 0x20, 0xFFFF)
            mem.w64(A + 0x48, RM.M64)
        for i in range(48):
            mem.w16(R + 0x4B08 + 4 * i, 0xFFFF)
        pairs = rng.sample(self.skill_ids, rng.randrange(0, 6))
        for i, sid in enumerate(pairs):
            mem.w16(R + 0x4B08 + 4 * i, sid)
            mem.w16(R + 0x4B0A + 4 * i, rng.choice([0, 1, 3, 19, 20]))
        mem.w8(R + 0x4A7C, 0)
        mem.w8(R + 0x4A84, 0)
        mem.w8(R + 0x4A85, 1)
        mem.w8(R + 0x4A86, 5)
        mem.w8(R + 0x4C26, rng.randrange(2))

    def add_item(self, slot, bag, d=None):
        mem, rng = self.mem, self.rng
        R = self.rec(slot)
        count = mem.s32(R + 0x1330 + bag * 0x1208)
        if not 0 <= count < 63:
            return None
        if d is None and bag == 0 and rng.random() < 0.12:
            d = rng.choice([x for x in self.tables.defs if x.category == 0 and x.subtype == 4])
        if d is None:
            if rng.random() < 0.3:              # the rare kinds, so rings and ammunition come up
                rare = [k for k in self.kinds if k[0] == bag and len(self.defs[k]) < 4]
                d = rng.choice(self.defs[rng.choice(rare)]) if rare else self.pick_def(rng, bag)
            else:
                d = self.pick_def(rng, bag)
        addr = R + 0x130 + bag * 0x1208 + count * 0x48
        self.write_item(addr, d, rng, count)
        mem.w32(R + 0x1330 + bag * 0x1208, count + 1)
        return addr

    def bag_items(self, slot, bag):
        R = self.rec(slot)
        count = self.mem.s32(R + 0x1330 + bag * 0x1208)
        return [R + 0x130 + bag * 0x1208 + i * 0x48 for i in range(max(0, min(count, 64)))]

    def fill_grid(self, panel, slot):
        """Put copies of some of a player's records into a panel's grids, as the screen's
        own builder 0x1cbbe8 would (first record in the first cell)."""
        mem, rng = self.mem, self.rng
        for bag in range(3):
            base = self.grid + panel * 0x23988 + bag * 0xBDD8
            for cell in getattr(self, 'grid_used', {}).get((panel, bag), ()):
                mem.w32(cell, 0)
            used = []
            for i, item in enumerate(self.bag_items(slot, bag)[:6]):
                cell = base + (i % 3) * 0x1518 + (i // 3) * 0x48
                mem.write(cell, mem.read(item, 0x48))
                mem.w16(cell + 0x22, i)
                used.append(cell)
                if rng.random() < 0.3:          # an item two cells wide
                    mem.write(cell + 3 * 0x1518, mem.read(item, 0x48))
                    used.append(cell + 3 * 0x1518)
            self.__dict__.setdefault('grid_used', {})[(panel, bag)] = used

    # ---- one message ------------------------------------------------------------------------------
    def step(self, family, data, stats, label, stale=None):
        """Deliver one message to the model and to the original and compare."""
        emu, mem = self.emu, self.mem
        channel = self.channel(family)
        n = len(data)
        mem.write(self.buf, bytes(data))        # the bytes after n stay: the previous message's
        if stale is not None:
            mem.write(self.buf + n, stale)
        payload = mem.read(self.buf, 0x100)
        seed_before = mem.u32(RM.G_RAND_SEED)
        # the model first, on a copy-on-write view
        mview = ModelView(mem)
        self.script.begin_side()
        model = RM.Machine(mview, self.tables, Rig.Callbacks(self, mview))
        model_error = None
        try:
            model.deliver(channel, payload)
        except (EmuError, KeyError, AttributeError, ZeroDivisionError, RecursionError) as exc:
            model_error = exc
        model_calls = [(name, canon_model(EXTERNALS[name], args, mview)) for name, args in model.calls]
        # the original
        self.calls = []
        self.eview.touched = set()
        self.script.begin_side()
        emu.reset_log()
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x1000
        handler = mem.u32(RM.G_MSG_HANDLERS + 4 * channel)
        emu_error = None
        try:
            emu.call(handler, self.buf, n, max_steps=6000000)
        except EmuError as exc:
            emu_error = exc
        self.trace.update(emu.trace)
        emu.trace = None
        stats.count += 1
        stats.kinds[label] = stats.kinds.get(label, 0) + 1
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names:
                stats.unknown += 1
                if len(stats.examples['unknown']) < 6:
                    stats.examples['unknown'].append('%s: call to 0x%06x from 0x%06x' % (label, c.target, c.site))
        what = '%s %s' % (label, bytes(data).hex())
        if (model_error is None) != (emu_error is None):
            stats.end += 1
            if len(stats.examples['end']) < 6:
                stats.examples['end'].append('%s: model %r, original %r' % (what, model_error, emu_error))
            return False
        if emu_error is not None:
            stats.faults += 1
            return True
        ok = True
        if model_calls != self.calls:
            stats.calls += 1
            ok = False
            if len(stats.examples['calls']) < 6:
                stats.examples['calls'].append('%s: %s' % (what, first_difference(model_calls, self.calls)))
        ebytes = set()
        for _pc, addr, size, _value in emu.writes:
            ebytes.update(range(addr, addr + size))
        mbytes = set()
        for addr, size, _value in mview.log:
            mbytes.update(range(addr, addr + size))
        if ebytes != mbytes:
            stats.sets += 1
            ok = False
            if len(stats.examples['writes']) < 6:
                stats.examples['writes'].append('%s: only original %s, only model %s' % (
                    what, self.where(sorted(ebytes - mbytes)), self.where(sorted(mbytes - ebytes))))
        diff = []
        for addr in sorted(ebytes | mbytes | self.eview.touched | mview.touched):
            a, b = mem.load(addr, 1), mview.load(addr, 1)
            if a != b:
                diff.append((addr, a, b))
        if diff:
            stats.values += 1
            ok = False
            if len(stats.examples['values']) < 6:
                stats.examples['values'].append('%s: %s' % (what, ' '.join(
                    '%s:%02x/%02x' % (self.where([addr]), a, b) for addr, a, b in diff[:8])))
        if mem.u32(RM.G_RAND_SEED) != mview.load(RM.G_RAND_SEED, 4):
            stats.seed += 1
            ok = False
            if len(stats.examples['seed']) < 6:
                stats.examples['seed'].append('%s: before %08x original %08x model %08x' % (
                    what, seed_before, mem.u32(RM.G_RAND_SEED), mview.load(RM.G_RAND_SEED, 4)))
        return ok

    def where(self, addrs):
        out = []
        for addr in addrs[:10]:
            if G_PLAYERS <= addr < G_PLAYERS + 4 * REC_SIZE:
                slot, off = divmod(addr - G_PLAYERS, REC_SIZE)
                out.append('rec%d+%x' % (slot, off))
            elif self.grid_block <= addr < self.grid_block + 5 * 0x23988:
                out.append('grid+%x' % (addr - self.grid))
            else:
                for slot, obj in enumerate(self.objects):
                    if obj <= addr < obj + 0x590:
                        out.append('obj%d+%x' % (slot, addr - obj))
                        break
                else:
                    out.append('%x' % addr)
        if len(addrs) > 10:
            out.append('... (%d)' % len(addrs))
        return ','.join(out)


def canon_model(ext, args, view):
    """A model callback's arguments in the form the interpreter side records them."""
    out, i = [], 0
    for kind in ext.ints:
        if kind == 'o':
            continue
        v = args[i]
        i += 1
        if kind in 'ip':
            out.append(v & M32)
        elif kind == 's':
            out.append(v if isinstance(v, (bytes, bytearray)) else view_cstr(view, v))
        elif kind == 'w':
            out.append(bytes(v) if isinstance(v, (bytes, bytearray)) else view_wstr(view, v))
        elif kind == 'v':
            out.append(tuple(x & M32 for x in v))
    for _ in range(ext.floats):
        out.append(args[i] & M32)
        i += 1
    return tuple(out)


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return 'call %d: model %s, original %s' % (i, fmt_call(x), fmt_call(y))
    if len(a) != len(b):
        longer = a if len(a) > len(b) else b
        return 'model made %d calls, original %d; first extra: %s' % (len(a), len(b), fmt_call(longer[min(len(a), len(b))]))
    return 'equal'


def fmt_call(c):
    name, args = c
    parts = []
    for v in args:
        if isinstance(v, tuple):
            parts.append('(%s)' % ','.join('%x' % x for x in v))
        elif isinstance(v, (bytes, bytearray)):
            parts.append(repr(bytes(v)))
        else:
            parts.append('%x' % v)
    return '%s(%s)' % (name, ', '.join(parts))


# ---------------------------------------------------------------------------------------
# Static shape of the functions, for coverage
# ---------------------------------------------------------------------------------------
def analyse(mem, start, end, table=()):
    """Basic-block leaders of one function body."""
    leaders = {start}
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
            leaders.add(pc + 8)
    return {a for a in leaders if start <= a < end}


def coverage(mem, pcs):
    rows = []
    for name, (start, size) in REAL.items():
        table = ()
        if name in JUMP_TABLES:
            base, n = JUMP_TABLES[name]
            table = [mem.u32(base + 4 * i) for i in range(n)]
        leaders = analyse(mem, start, start + size, table)
        hit = {a for a in leaders if a in pcs}
        rows.append((name, start, len(hit), len(leaders), sorted(leaders - hit)))
    return rows


# ---------------------------------------------------------------------------------------
# The driver: messages and what the rest of the game does between them
# ---------------------------------------------------------------------------------------
class Driver:
    def __init__(self, rig):
        self.rig, self.rng, self.mem = rig, rig.rng, rig.mem

    def slot(self, wild=0.06):
        """Mostly a player of this game; sometimes a slot nobody plays."""
        rng = self.rng
        if rng.random() < wild:
            return rng.randrange(4)
        return rng.randrange(self.rig.players)

    def any_item(self, slot):
        """An item address as a sender would use it, or a stale / foreign one."""
        rig, rng = self.rig, self.rng
        R = rig.rec(slot)
        roll = rng.random()
        if roll < 0.10:                         # an empty cell of the right bag
            bag = rng.randrange(3)
            count = max(0, self.mem.s32(R + 0x1330 + bag * 0x1208))
            return R + 0x130 + bag * 0x1208 + rng.randrange(min(count, 63), 64) * 0x48
        if roll < 0.16:                         # another player's item
            other = rng.randrange(4)
            items = [i for bag in range(3) for i in rig.bag_items(other, bag)]
            if items:
                return rng.choice(items)
        if roll < 0.45:                         # something that is equipped
            held = [self.mem.u32(R + 0x43F0 + 4 * k) for k in range(17)]
            held += [self.mem.u32(R + 0x4434), self.mem.u32(R + 0x4438), self.mem.u32(R + 0x443C)]
            held = [a for a in held if a]
            if held:
                return rng.choice(held)
        bag = rng.choice([0, 0, 0, 1, 1, 2])
        items = rig.bag_items(slot, bag)
        if items:
            return rng.choice(items)
        return R + 0x130

    def drop_fields(self, slot):
        rig, rng = self.rig, self.rng
        R = rig.rec(slot)
        bag = rng.choice([0, 1, 2, 2])
        count = self.mem.s32(R + 0x1330 + bag * 0x1208)
        roll = rng.random()
        if roll < 0.12 or count <= 0:
            index = rng.randrange(max(0, min(count, 63)), 64)       # stale: nothing there
        else:
            index = rng.randrange(count)
        column, row = rng.randrange(9), rng.randrange(75)
        panel = rng.choice([0, 0, 0, 1, 2, 3, -1])
        return index, bag, column, row, panel

    def message(self):
        """-> (family, bytes, label, stale tail or None)"""
        rng, rig, mem = self.rng, self.rig, self.mem
        pack = struct.pack
        roll = rng.random()
        family = 'inventory' if roll < 0.55 else ('game' if roll < 0.85 else 'shop')
        slot = self.slot()
        R = rig.rec(slot)
        if family == 'inventory':
            kind = rng.choice([0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 4, 5, 6, 6, 7, 7, 7, 8, 9, 10, 3, 11, 0x80])
            if kind == 0:
                index, bag, column, row, panel = self.drop_fields(slot)
                mode = rng.choice([0, 0, 0, 1, 2, 2, 3])
                if rng.random() < 0.04:         # slot byte -1: the record before the table
                    slot, index, bag = -1, rng.randrange(64), rng.randrange(3)
                return family, pack('<BbhIhbbb', 0, slot, column, index, row, bag, panel, mode), 'inv0 drop', None
            if kind == 1:
                return family, pack('<BbhI', 1, rng.randrange(2), slot, self.any_item(slot)), 'inv1 equip', None
            if kind == 2:
                return family, pack('<BbhI', 2, 0, slot, self.any_item(slot)), 'inv2 unequip', None
            if kind == 4:
                return family, pack('<Bbbb', 4, rng.randrange(4), slot, rng.randrange(2)), 'inv4 join', None
            if kind == 5:
                return family, pack('<BbB', 5, slot, rng.randrange(8)), 'inv5 class', None
            if kind == 6:
                stat = rng.choice([0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, -1, -2])
                return family, pack('<Bbh', 6, slot, stat), 'inv6 stat', None
            if kind == 7:
                if rng.random() < 0.5:
                    table = RM.G_CLASS_SKILLS + mem.s32(R + 0x50) * 0xA88
                    masks = [mem.u64(table + n * 0x38) for n in range(0x30)]
                    masks = [m for m in masks if m and m < 0x80000000] or [0x40]
                    value = rng.choice(masks + [0x40, 0x80, 0x100] * 4 + [0x20000, 0x40000, 1 << rng.randrange(31)])
                    return family, pack('<BbbBI', 7, slot, 0, rng.randrange(256), value), 'inv7 passive', None
                ids = rig.passive_ids if rig.passive_ids and rng.random() < 0.3 else rig.skill_ids
                return family, pack('<BbbBI', 7, slot, 1, 0, rng.choice(ids)), 'inv7 skill', None
            if kind == 8:
                return family, pack('<BbHIII', 8, slot, 0, *[rng.getrandbits(32) for _ in range(3)]), 'inv8 combine', None
            if kind == 9:
                return family, pack('<BbB', 9, slot, rng.randrange(1, 60)), 'inv9 level', None
            if kind == 10:
                return family, pack('<Bb4h', 10, slot, rng.randrange(2), 0, 0, -1), 'inv10 potion', None
            return family, bytes([kind]) + bytes(rng.getrandbits(8) for _ in range(7)), 'inv other', None
        if family == 'game':
            kind = rng.choice([0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5, 6, 6, 7, 8, 9, 10, 10, 10, 11, 12, 13,
                               13, 13, 14, 0xFF])
            if kind == 0:
                return family, pack('<Bbbb', 0, slot, rng.randrange(2), rng.randrange(15)), 'hud0 quickslot', None
            if kind == 1:
                index = rng.randrange(15)
                if rng.random() < 0.6:
                    value = rng.choice(rig.skill_ids)
                    if rng.random() < 0.4:      # one the player already has in the first eight
                        value = mem.s16(R + 0x4460 + rng.randrange(8) * 0x68) & RM.M64
                    return family, pack('<BbbBIQ', 1, slot, index, 0, 1, value), 'hud1 skill', None
                masks = [mem.u64(RM.G_OLD_ABILITIES + r * 0x68 + 0x48) for r in range(40)]
                value = rng.choice(masks + [1 << rng.randrange(40), 0x40, 0x80, 0x100])
                if rng.random() < 0.3:
                    value = mem.u64(R + 0x4488 + rng.randrange(8) * 0x68)
                return family, pack('<BbbBIQ', 1, slot, index, 0, rng.choice([0, 2]), value), 'hud1 ability', None
            if kind == 2:
                return family, pack('<Bbbb', 2, slot, rng.choice([0, 0, 1, 1, 2, 3, -1]), 0), 'hud2 menu', None
            if kind == 3:
                return family, pack('<Bb', 3, slot), 'hud3 recall', None
            if kind == 4:
                return family, pack('<Bb', 4, slot), 'hud4 left', None
            if kind == 5:
                return family, pack('<BBBBI', 5, 0, 0, 0, rng.choice(rig.objects)), 'hud5 savepoint', None
            if kind == 6:
                return family, pack('<Bb', 6, slot), 'hud6 disconnect', None
            if kind == 7:
                name = rng.choice([b'hub', b'strife', b'x' * 79, b'', b'y' * 90])
                return family, b'\x07' + name + b'\0', 'hud7 newworld', None
            if kind == 8:
                return family, b'\x08', 'hud8 exit', None
            if kind == 9:
                return family, b'\x09', 'hud9 checkstart', None
            if kind == 10:
                good = rng.random() < 0.7
                live = mem.u32(RM.G_CHECKSUM_EXPECTED + slot * 8) if good else rng.getrandbits(32)
                saved = mem.u32(RM.G_CHECKSUM_EXPECTED + slot * 8 + 4) if rng.random() < 0.8 else rng.getrandbits(32)
                return family, pack('<BbHII', 10, slot, 0, live, saved), 'hud10 checksum', None
            if kind == 11:
                name = rng.choice([b'hub', b'blood1', b''])
                if rng.random() < 0.5:          # as sent: four bytes, the name is whatever follows
                    return family, b'\x0b\0\0\0', 'hud11 loadlevel', name + b'\0'
                return family, b'\x0b\0\0\0' + name + b'\0', 'hud11 loadlevel', None
            if kind == 12:
                return family, b'\x0c', 'hud12 medal', None
            if kind == 13:
                return family, pack('<Bbb', 13, slot, rng.randrange(15)), 'hud13 quickcast', None
            return family, bytes([kind, 1, 2, 3]), 'hud other', None
        kind = rng.choice([0, 0, 0, 1, 1, 1, 1, 2, 0x81])
        if kind == 0:
            roll = rng.random()
            if roll < 0.25:
                record = rng.choice(rig.special_stock)
            elif roll < 0.85:
                record = rng.choice(rig.stock)
            else:                               # not a stock record at all: any readable item
                items = [i for bag in range(3) for i in rig.bag_items(rng.randrange(4), bag)]
                record = rng.choice(items) if items else rng.choice(rig.stock)
            return family, pack('<BbHI', 0, slot, 0, record), 'shop0 buy', None
        if kind == 1:
            bag = rng.choice([0, 1, 2, 2])
            items = rig.bag_items(slot, bag)
            if not items:
                return family, b'\x02', 'shop other', None
            index = rng.randrange(len(items))
            return family, pack('<BbhIhbbb', 1, slot, rng.randrange(9), index, rng.randrange(75), bag,
                                rng.choice([0, 0, 1, 2]), rng.choice([1, 1, 1, 0, 2])), 'shop1 sell', None
        return family, bytes([kind, slot]), 'shop other', None

    def between(self):
        """What the rest of the game would do between two messages."""
        rng, rig, mem = self.rng, self.rig, self.mem
        s = rig.script
        mem.w32(RM.G_SIM_FRAME, (mem.u32(RM.G_SIM_FRAME) + rng.randrange(1, 5)) & 0x7FFFFFFF)
        s.answers = {
            'net_allPlayersState2': int(rng.random() < 0.5),
            'vars_get': int(rng.random() < 0.5),
            'Player_weaponSwapInput': int(rng.random() < 0.4),
            'dialog_isOpen': int(rng.random() < 0.1),
            'task_isRunning': int(rng.random() < 0.1),
            'game_inNoSaveZone': int(rng.random() < 0.15),
            'audio_streamStatus': rng.choice([0, 0x40, 0x41, 2]),
        }
        s.blocks = [(rig.emu.alloc(400) if rng.random() < 0.85 else 0) for _ in range(5)]
        s.spot = tuple(f32(rng.uniform(-900, 900)) for _ in range(3))
        s.spot_draws = rng.choice([3, 3, 6, 9, 150])
        slot = rng.randrange(4)
        R = rig.rec(slot)
        roll = rng.random()
        if roll < 0.30:                         # loot
            for _ in range(rng.randrange(1, 4)):
                rig.add_item(slot, rng.randrange(3))
        elif roll < 0.36:
            mem.w8(R + 0xEC, rng.randrange(0, 6))
            mem.w32(R + 0xE8, rng.randrange(0, 4))
        elif roll < 0.42:
            mem.w32(R + 0xE4, rng.choice([0, 100, 20000, 3000000, 99999999]))
        elif roll < 0.46:                       # dead, alive
            mem.w32(R + 0xAC, rng.choice([0, f32(-1.0), f32(40.0)]))
        elif roll < 0.49:                       # departed: no object
            mem.w32(R + 0x43D8, rng.choice([0, rig.objects[slot], rig.objects[slot]]))
        elif roll < 0.53:
            rig.set_machine()
        elif roll < 0.58:
            rig.fill_grid(rng.randrange(4), slot)
        elif roll < 0.62:
            mem.w32(R + 0x50, rng.randrange(7))
            for i in range(0x30):
                mem.w8(R + 0xEF + i, rng.choice([0, 0, 0, 1, 2, 19, 20]))
        elif roll < 0.66:
            mem.w8(RM.G_LEVEL_NAME, 0)
            name = rng.choice([b'hub\0', b'hub2\0', b'strife\0'])
            mem.write(RM.G_LEVEL_NAME, name)
        elif roll < 0.70:
            alive = rng.sample(range(4), rng.randrange(0, 4))
            mem.w32(RM.G_ALIVE_COUNT, len(alive))
            for i, a in enumerate(alive):
                mem.w32(RM.G_ALIVE_LIST + 4 * i, a)
        elif roll < 0.73:
            obj = rig.objects[slot]
            mem.w32(obj + 0x58C, rng.choice([2, 2, 1, 5]))
            mem.w32(obj + 0x488, rng.choice([0, 0, R + 0x4440]))
        elif roll < 0.76:
            for panel in range(2):
                mem.w32(RM.G_ITEM_PANELS + panel * RM.PANEL_SIZE + 0x38, rng.randrange(4))
                mem.w32(RM.G_ITEM_PANELS + panel * RM.PANEL_SIZE + 0x34, rng.randrange(4))
        elif roll < 0.79:
            mem.w8(RM.G_CHECKSUM_COUNT, rng.choice([0, 0, rig.players - 1, 1]))
            for i in range(8):
                mem.w32(RM.G_CHECKSUM_EXPECTED + 4 * i, rng.getrandbits(32))
                mem.w32(RM.G_CHECKSUM_RECEIVED + 4 * i,
                        mem.u32(RM.G_CHECKSUM_EXPECTED + 4 * i) if rng.random() < 0.8 else 1)
        elif roll < 0.82:                       # a recall potion, a named unique
            for wanted in rig.special_names:
                for d in rig.tables.defs:
                    if d.name == wanted and rng.random() < 0.7:
                        rig.add_item(slot, d.category, d)
        elif roll < 0.84:
            mem.w8(R + 0x4C25, rng.randrange(2))
            mem.w32(RM.G_DIFFICULTY, rng.choice([1, 1, 2]))
        elif roll < 0.86:
            mem.w32(RM.G_PVP_MODE_B, rng.choice([0, 0, 0, 1]))
            mem.w32(RM.G_MEDAL_MISSION, rng.choice([0, 0, 0, 3]))
        elif roll < 0.90:
            s.active = set(rng.sample(range(4), rng.randrange(1, 5)))
        elif roll < 0.93:                       # full mana and health, or above the maximum
            over = rng.choice([0, 0, 0x00800000])
            mem.w32(R + 0xC0, mem.u32(R + 0xC4) + over)
            mem.w32(R + 0xAC, mem.u32(R + 0xB0) + over)
        elif roll < 0.95:                       # the last one alive, nobody else connected
            mem.w32(RM.G_ALIVE_COUNT, 1)
            mem.w32(RM.G_ALIVE_LIST, slot)
            s.active = {slot}
        elif roll < 0.965:                      # a bag filled to the brim
            bag = rng.randrange(3)
            while rig.add_item(slot, bag) is not None:
                pass


def run(elf, name, seed, players, net, machine, steps, pcs):
    rig = Rig(elf, seed, players, net, machine)
    driver = Driver(rig)
    stats = Stats()
    for _ in range(steps):
        driver.between()
        family, data, label, stale = driver.message()
        rig.step(family, data, stats, label, stale)
    pcs.update(rig.trace)
    text = 'faults on both sides %d' % stats.faults
    report(name + ' calls', stats.calls + stats.unknown, stats.count, text,
           stats.examples['unknown'] + stats.examples['calls'])
    report(name + ' writes', stats.sets, stats.count, 'bytes stored', stats.examples['writes'])
    report(name + ' values', stats.values, stats.count, 'final values of those bytes', stats.examples['values'])
    report(name + ' seed', stats.seed, stats.count, 'shared seed', stats.examples['seed'])
    report(name + ' end', stats.end, stats.count, 'returned or stopped alike', stats.examples['end'])
    return rig, stats


def check_registration(elf):
    rig = Rig(elf, 1, 2, True, 'owner')
    want = dict((family, i) for i, (family, _h, _w) in enumerate(RM.REGISTRATION))
    bad = [r for r in rig.registered if r[1] != want[r[0]] or r[2] != r[3]]
    if rig.again != want['inventory']:
        bad.append(('second registration', rig.again))
    report('channel ids', len(bad), len(rig.registered),
           'the 7 start-up calls give ids ' + ' '.join('%s=%d' % (r[0], r[1]) for r in rig.registered), bad)
    # the model's own registration on an empty table
    view = RM.Memory()
    ids = RM.Machine(view).register_all()
    report('channel ids (model)', int(ids != want), len(ids), 'same ids from ref_messages.register_all', [ids])


# ---------------------------------------------------------------------------------------
# The senders: what each one really queues
# ---------------------------------------------------------------------------------------
SENDERS = (
    ('invmsg_sendDrop', 0x1C59D0, (1, 0x11223344, 2, 0x55, 0x66, 3, 0), RM.msg_drop(1, 0x11223344, 2, 0x55, 0x66, 3, 0)),
    ('invmsg_sendEquip', 0x1C5800, (1, 0x4D9000, 1), RM.msg_equip(1, 0x4D9000, 1)),
    ('invmsg_sendUnequip', 0x1C5840, (1, 0x4D9000), RM.msg_unequip(1, 0x4D9000)),
    ('invmsg_sendJoinPanel', 0x1C5628, (1, 2, 1), RM.msg_join_panel(1, 2, 1)),
    ('invmsg_send5', 0x1C5570, (1, 6), RM.msg_weapon_class(1, 6)),
    ('invmsg_sendStatPoint', 0x1C5780, (1, 3), RM.msg_stat_point(1, 3)),
    ('invmsg_sendSkillPoint', 0x1C57B8, (1, 1, 0x12345678), RM.msg_skill_point(1, 1, 0x12345678)),
    ('invmsg_sendCombine', 0x1C5738, (1, 0x11111111, 0x22222222, 0x33333333),
     RM.msg_combine(1, 0x11111111, 0x22222222, 0x33333333)),
    ('invmsg_send9', 0x1C55A8, (1, 17), RM.msg_level_ack(1, 17)),
    ('invmsg_sendUsePotion', 0x1C55E0, (1, 1, 2, 3, 0xFFFF), RM.msg_use_potion(1, 1, 2, 3, -1)),
    ('hudmsg_sendQuickSlot', 0x1DE06C, (1, 1, 7), RM.msg_quick_slot(1, 1, 7)),
    ('hudmsg_sendAssignSpell', 0x1DE3EC, (1, 5, 1, 0x1122334455667788), RM.msg_assign_spell(1, 5, 1, 0x1122334455667788)),
    ('hudmsg_sendMenuState', 0x1DE0DC, (1, 2, 9), RM.msg_menu_state(1, 2, 9)),
    ('hudmsg_sendRecall', 0x1DE138, (1,), RM.msg_recall(1)),
    ('hudmsg_sendPlayerLeft', 0x1DE16C, (1,), RM.msg_player_left(1)),
    ('hudmsg_sendSavepoint', 0x1DE1A0, (0x01234567,), RM.msg_savepoint(0x01234567)),
    ('hudmsg_sendDisconnectRequest', 0x1DE1E0, (), RM.msg_disconnect_request(1)),
    ('hudmsg_sendNewWorld', 0x1D9250, ('name',), RM.msg_new_world(b'strife')),
    ('hudmsg_sendExitCountdown', 0x1DE25C, (), RM.msg_exit_countdown()),
    ('hudmsg_sendLoadLevel', 0x1DE598, ('name',), RM.msg_load_level()),
    ('hudmsg_sendMedalAck', 0x1DE5EC, (), RM.msg_medal_ack()),
    ('hudmsg_sendQuickCastWarn', 0x1DE0A4, (1, 4), RM.msg_quick_cast(1, 4)),
    ('shopmsg_sendSell', 0x1D1330, (1, 0x11223344, 2, 0x55, 0x66, 3, 1), RM.msg_sell(1, 0x11223344, 2, 0x55, 0x66, 3, 1)),
    ('shopmsg_sendBuy', 0x1C5F78, (1, 'stock'), None),
    ('nullmsg_sendShopClosed', 0x1E0134, (), RM.msg_shop_closed(1)),
)


def ring_messages(mem, slot, start):
    """The messages queued in a peer's ring since position `start`."""
    peer = RM.G_PEERS + slot * RM.PEER_SIZE
    end, ring, out = mem.u32(peer + 0x44AC), peer + 0xC + 0x24A0, []
    while start != end:
        channel, n = mem.u8(ring + (start & 0x1FFF)), mem.u8(ring + ((start + 1) & 0x1FFF))
        out.append((channel, bytes(mem.u8(ring + ((start + 2 + i) & 0x1FFF)) for i in range(n))))
        start = (start + 2 + n) & 0x1FFF
    return out


def check_senders(elf):
    """Each sender is run for real in a net game (local slot 1) with two different stack
    fills; the queued bytes must be the encoder's, and must not depend on the fill."""
    results = []
    for fill in (0xAA, 0x55):
        rig = Rig(elf, 3, 2, True, 'other')
        emu, mem = rig.emu, rig.mem
        rig.script.local = [1]
        emu.follow = RealSet(rig.real.addresses | {addr for _n, addr, _a, _w in SENDERS})
        name = emu.alloc(32)
        mem.write(name, b'strife\0')
        stock = rig.stock[5]
        mem.write(stock + 0x48, mem.read(stock, 0x48))      # two equal records: the later one is sent
        row = []
        for label, addr, args, want in SENDERS:
            args = [name if a == 'name' else (stock if a == 'stock' else a) for a in args]
            if label == 'shopmsg_sendBuy':
                want = RM.msg_buy(1, stock + 0x48)
            mem.write(emu.stack_hi - 0x3000, bytes([fill]) * 0x2F00)
            start = mem.u32(RM.G_PEERS + RM.PEER_SIZE + 0x44AC)
            emu.r[29] = emu.stack_hi - 0x200
            emu.call(addr, *args)
            got = ring_messages(mem, 1, start)
            row.append((label, got, [(rig.channel(want[0]), want[1])]))
        results.append(row)
    bad = []
    for (label, got, want), (_l, got2, _w) in zip(*results):
        if got != want or got != got2:
            bad.append('%s: queued %s, encoder %s, with the other stack fill %s' % (label, got, want, got2))
    report('senders', len(bad), len(SENDERS), 'the bytes each sender queues are the encoder\'s; none are left undefined', bad)


# ---------------------------------------------------------------------------------------
# K2 as executed: what the potion's drop message names, and what its handler removes
# ---------------------------------------------------------------------------------------
PLAYER_USE_POTION, GRID_BUILDER, PICTURE_SIZE = 0x1B9CB8, 0x1CBBE8, 0x1083A4
POTION_NAMES = 0x4EF478


def k2_machine(elf, slot, owner, build_for=None):
    """A two-player net game in which `slot` is about to drink a health potion.  Bag 2 of
    that player: a non-potion (3 of them), the potion the code will choose (2), a mana
    potion (2).  On the owner's machine the inventory screen is open and the screen's own
    grid builder has run for panel 0."""
    rig = Rig(elf, 11, 2, True, 'owner')
    emu, mem, t = rig.emu, rig.mem, rig.tables
    rig.script.local = [slot] if owner else [1 - slot]
    rig.script.answers = {}
    emu.follow = RealSet(rig.real.addresses | {PLAYER_USE_POTION, 0x1C59D0, GRID_BUILDER})
    emu.unhook(PLAYER_USE_POTION)               # the real one, not the recording stub

    def picture(e):                             # item_getPictureDimensions: one cell each
        e.mem.w32(e.r[6] & M32, 31)
        e.mem.w32(e.r[7] & M32, 30)
        return 0
    emu.stub(PICTURE_SIZE, function=picture)
    rig.names[PICTURE_SIZE] = None
    R = rig.rec(slot)
    health = view_cstr(rig.eview, mem.u32(POTION_NAMES + 4))
    mana_name = view_cstr(rig.eview, mem.u32(POTION_NAMES + 0x28 + 4))
    wanted = [d for d in t.defs if d.category == 2 and d.slot == 16 and not d.flags & 0x1000100][0]
    potion = [d for d in t.defs if d.name == health][0]
    mana = [d for d in t.defs if d.name == mana_name][0]
    base = R + 0x130 + 2 * 0x1208
    mem.write(base, bytes(0x1200))
    for i, (d, count) in enumerate(((wanted, 3), (potion, 2), (mana, 2))):
        item = RI.Item(d)
        item.count, item.flags = count, d.flags
        data = bytearray(item.pack())
        struct.pack_into('<h', data, 0x22, i)
        mem.write(base + i * 0x48, bytes(data))
    mem.w32(base + 0x1200, 3)
    mem.w32(R + 0xAC, f32(10.0))
    mem.w32(R + 0xB0, f32(100.0))
    mem.w32(R + 0xB4, 0)
    mem.w32(rig.objects[slot] + 0xC, 0)
    mem.w32(R + 0x43D8, rig.objects[slot])
    mem.write(rig.grid_block, bytes(5 * 0x23988))
    mem.w32(RM.G_ITEM_LIST_CELLS, rig.grid)
    mem.w8(RM.G_LOCAL_MENU_OPEN, 1 if owner else 0)
    if owner:
        emu.r[29] = emu.stack_hi - 0x1000
        emu.call(GRID_BUILDER, slot, 0 if build_for is None else build_for, 0)
    return rig


def k2_counts(rig, slot, bag=2):
    R = rig.rec(slot)
    return [rig.mem.s16(R + 0x130 + bag * 0x1208 + i * 0x48 + 4) for i in range(3)]


def k2_drink(rig, slot):
    emu, mem = rig.emu, rig.mem
    local = rig.script.local[0]
    start = mem.u32(RM.G_PEERS + local * RM.PEER_SIZE + 0x44AC)
    emu.r[29] = emu.stack_hi - 0x1000
    rig.calls = []
    emu.call(PLAYER_USE_POTION, rig.objects[slot], 0, 0, 0, M32)
    return ring_messages(mem, local, start)


def check_k2(elf):
    bad, facts = [], []
    stats = Stats()
    # A: the owner is slot 0, the slot whose number is also the panel the screen uses
    owner, other = k2_machine(elf, 0, True), k2_machine(elf, 0, False)
    cell = owner.grid + 2 * 0xBDD8
    first = owner.rec(0) + 0x130 + 2 * 0x1208
    if owner.mem.read(cell, 0x22) != owner.mem.read(first, 0x22) or owner.mem.s16(cell + 0x22) != 0:
        bad.append('the grid builder did not put bag-2 record 0 into cell (0,0)')
    sent, sent_other = k2_drink(owner, 0), k2_drink(other, 0)
    want = RM.msg_drop(0, 0, 2, 0, 0, -1, 2)[1]
    if sent != [(owner.channel('inventory'), want)] or sent_other:
        bad.append('slot 0: owner queued %s, other machine queued %s; expected one %s' % (sent, sent_other, want.hex()))
    after_drink = (k2_counts(owner, 0), k2_counts(other, 0))
    if after_drink != ([3, 2, 2], [3, 1, 2]):
        bad.append('slot 0 after the potion: owner %s, other %s' % after_drink)
    for rig in (owner, other):
        rig.step('inventory', want, stats, 'k2 drop')
    after_message = (k2_counts(owner, 0), k2_counts(other, 0))
    if after_message != ([2, 2, 2], [2, 1, 2]):
        bad.append('slot 0 after the message: owner %s, other %s' % after_message)
    facts.append('slot 0: message %s; stacks owner %s -> %s, other %s -> %s' % (
        want.hex(), after_drink[0], after_message[0], after_drink[1], after_message[1]))
    # B: the owner is slot 1; a net game still draws panel 0, and the potion code reads panel 1
    owner, other = k2_machine(elf, 1, True), k2_machine(elf, 1, False)
    def bag0_state(rig):
        R = rig.rec(1)
        return (rig.mem.s32(R + 0x1330), rig.mem.s16(R + 0x130 + 4))
    bag0 = [bag0_state(owner), bag0_state(other)]
    sent, sent_other = k2_drink(owner, 1), k2_drink(other, 1)
    want = RM.msg_drop(1, 0, 0, 0, 0, -1, 2)[1]
    if sent != [(owner.channel('inventory'), want)] or sent_other:
        bad.append('slot 1: owner queued %s, other machine queued %s; expected one %s' % (sent, sent_other, want.hex()))
    after_drink = (k2_counts(owner, 1), k2_counts(other, 1))
    for rig in (owner, other):
        rig.step('inventory', want, stats, 'k2 drop')
    after_message = (k2_counts(owner, 1), k2_counts(other, 1))
    if after_drink != ([3, 2, 2], [3, 1, 2]) or after_message != after_drink:
        bad.append('slot 1: bag 2 after the potion %s, after the message %s' % (after_drink, after_message))
    bag0_after = [bag0_state(owner), bag0_state(other)]
    if bag0_after[0] != bag0_after[1] or bag0_after[0] == bag0[0]:
        bad.append('slot 1: bag 0 (records, first stack) before %s, after %s' % (bag0, bag0_after))
    facts.append('slot 1: message %s (bag and index read through a null pointer); bag 2 stays owner %s, other %s; '
                 'the record it names, bag 0 index 0 when address 0x1d holds 0, loses one on both machines: '
                 '(records, first stack) %s -> %s' % (want.hex(), after_message[0], after_message[1], bag0[0], bag0_after[0]))
    failures = len(bad) + stats.calls + stats.sets + stats.values + stats.seed + stats.end
    report('K2 potion message', failures, 4, '; '.join(facts),
           bad + stats.examples['calls'] + stats.examples['writes'] + stats.examples['values'] + stats.examples['end'])


RUNS = (
    ('1p offline owner', 1, False, 'owner'),
    ('2p offline two', 2, False, 'two'),
    ('2p net owner', 2, True, 'owner'),
    ('2p net other', 2, True, 'other'),
    ('3p net owner', 3, True, 'owner'),
    ('4p net other', 4, True, 'other'),
    ('4p net owner', 4, True, 'owner'),
    ('4p offline owner', 4, False, 'owner'),
)


def main(argv):
    args = list(argv[1:])
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--steps':
            OPTIONS['steps'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('SKIP: %s not found (the differential test needs your own copy of the executable)' % elf)
        return 0
    steps = OPTIONS['steps'] // (10 if OPTIONS['quick'] else 1)
    wanted = OPTIONS['filter']
    pcs = set()
    mem = None
    if not wanted or wanted in 'channel ids':
        check_registration(elf)
    if not wanted or wanted in 'senders':
        check_senders(elf)
    if not wanted or wanted in 'K2 potion message':
        check_k2(elf)
    kinds = {}
    for index, (name, players, net, machine) in enumerate(RUNS):
        if wanted and wanted not in name:
            continue
        rig, stats = run(elf, name, OPTIONS['seed'] + index, players, net, machine, steps, pcs)
        mem = rig.mem
        for label, n in stats.kinds.items():
            kinds[label] = kinds.get(label, 0) + n
    if mem is not None:
        print('messages by type: ' + ', '.join('%s %d' % (k, kinds[k]) for k in sorted(kinds)))
        print('coverage by the original as executed here (basic blocks):')
        for name, start, hit, total, missing in coverage(mem, pcs):
            print('  %-26s 0x%06x  %3d of %3d (%5.1f%%)%s' % (
                name, start, hit, total, 100.0 * hit / total,
                '' if not missing or not OPTIONS['verbose'] else '  missing ' + ' '.join('%06x' % a for a in missing)))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
