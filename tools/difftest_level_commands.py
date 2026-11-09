#!/usr/bin/env python3
"""difftest_level_commands.py - five level-script built-ins and the code below them, the
original against tools/ref_natives.py + tools/ref_level_commands.py (docs/level-commands.md).

    PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); \
      sys.argv=["difftest_level_commands.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA", \
      "--seed","20973"]; runpy.run_path("tools/difftest_level_commands.py", run_name="__main__")'

Needs the owner's US v2.00 executable and the disc's BG/DATA folder (read only: the level
scripts and object records of TORMENTA, HUB, HUB2, ISLGNOME and the soundSequence levels).
Nothing from the game is written; the output is counts, addresses and neutral ids.

The commands: autoPropSetState 0x142320, killMonster 0x144a84, soundSequence 0x143684,
preloadResource 0x14222c, activateStore 0x144010.

What runs for real (tools/ee_emu.py) - everything difftest_natives.Rig runs (handlers,
interpreter, dispatcher, script_runByName, quest variables, name lookup, obj_getPropStr,
the C library) PLUS the bodies of ref_level_commands.REAL_BODIES, which difftest_natives
stubs: the AutoProp setState / setPassable pair and what they call, the Gnome death path
down to Creature_onDeath, sound_playOnObject and lump_load.  Their own call-outs
(ref_level_commands.CALLOUTS and the ref_natives.EXT entries they reach) are recording
stubs; a call to any other address fails the case.

Groups
  binding    the table 0x403370 entry of each name, and the address scr_registerNatives
             stores for each import of every level script that calls it
  direct     each handler through the real dispatcher scr_callNative 0x141050 on seeded
             states: objects with the REAL class tables (AutoProp, AutoPropLP, Gnome)
             among stub-table objects, argument variations; compared with the model:
             result and error word, every call-out, every byte stored outside the
             stack, the seed, the script machine
  shipped    whole shipped entry points through the real script_runByName, with the
             disc's object records for the names they use: tormenta preStart / start,
             islgnome entrance1-3 (and failQuest), and every hub / hub2 entry that calls
             activateStore.  Compared as above, plus addressed expectations: what each
             target object holds afterwards, which built-ins the entry still reached, the
             machine's error word
  controls   the same cases with a deliberate change in the model (ref_level_commands.
             MUTATION, or a changed activateStore); each must be rejected
"""
import argparse
import hashlib
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_natives as D                    # noqa: E402
import ref_amx                                  # noqa: E402
import ref_level_commands as L                  # noqa: E402
import ref_natives as N                         # noqa: E402
import ref_objects as O                         # noqa: E402
import scr                                      # noqa: E402
from gob import gob_entries, lmp_entries        # noqa: E402

M32 = 0xFFFFFFFF
ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
COMMANDS = ('autoPropSetState', 'killMonster', 'soundSequence', 'preloadResource', 'activateStore')
SOUND_LEVELS = ('tormenta', 'wate2a', 'wate2b', 'wate2c', 'watg2a', 'watg2b', 'watg2c')
LEVELS = ('tormenta', 'hub', 'hub2', 'islgnome') + SOUND_LEVELS[1:]
BODY_RANGES = {                 # end-exclusive instruction ranges, for the executed-instruction counts
    'AutoProp_setState': (0x23D680, 0x23D7AC), 'AutoProp_setPassable': (0x23D7AC, 0x23D890),
    'model_buildHideMask': (0x179550, 0x1795A8), 'anim_push': (0x170838, 0x1708BC),
    'anim_jumpTopToEnd': (0x170BC8, 0x170C80), 'anim_start': (0x16CFE0, 0x16D0B8),
    'world_setPieceCollision': (0x182B00, 0x182B74), 'Gnome_setState': (0x269BB4, 0x269EB8),
    'creature_stateGate': (0x10A9C0, 0x10AB14), 'Creature_onDeath': (0x10BEB8, 0x10BFC8),
    'GameObject_rand': (0x1509D0, 0x1509F8), 'creature_stopBossMusic': (0x1192F8, 0x119324),
    'sound_playOnObject': (0x214230, 0x214424), 'sound_setPlaysWhileFrozen': (0x216AD0, 0x216B10),
    'game_isFrozen': (0x1EBDF8, 0x1EBEC4), 'lump_load': (0x173558, 0x17365C),
    'autoPropSetState': (0x142320, 0x1423E0), 'killMonster': (0x144A84, 0x144B44),
    'soundSequence': (0x143684, 0x143720), 'preloadResource': (0x14222C, 0x142264),
    'activateStore': (0x144010, 0x1440F8),
}
RESULTS = []
MODEL_BLOCK = 0x20000


def report(name, bad, count, text, examples=()):
    ok = bad == 0 and count > 0
    RESULTS.append((name, ok))
    print('%s  %-34s %5d  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                   '' if ok else '  [%d bad]' % bad))
    if not ok:
        for line in list(examples)[:4]:
            print('        ' + str(line)[:600])
    sys.stdout.flush()


# ---------------------------------------------------------------------------------------
# The disc (read only)
# ---------------------------------------------------------------------------------------
def gob_file(data, level, filename):
    path = os.path.join(data, level.upper() + '.GOB')
    blob = open(path, 'rb').read()
    for lump_name, lo, ls in gob_entries(blob):
        if lump_name.lower() != level.lower() + '.lmp':
            continue
        lump = blob[lo:lo + ls]
        for name, off, size in lmp_entries(lump):
            if name.lower() == filename:
                return lump[off:off + size]
    raise AssertionError('%s.GOB has no %s' % (level, filename))


def object_records(blob):
    """objects.ob: (class, [property strings]) as difftest_story_route reads it."""
    count, _flags, strings = struct.unpack_from('<hHi', blob)
    off = 8
    out = []
    for _ in range(count):
        class_off, size = struct.unpack_from('<ih', blob, off)

        def text(offset):
            at = strings + offset
            return blob[at:blob.index(b'\0', at)]
        props = []
        at = off + 20
        while True:
            val, = struct.unpack_from('<i', blob, at)
            at += 4
            if val == 0:
                break
            props.append(text(val))
        out.append((text(class_off), props))
        off += size
    return out


def prop(props, key):
    for entry in props:
        k, _s, v = entry.partition(b'=')
        if k.lower() == key:
            return v
    return None


def call_sites(image, command):
    """Code offsets of every SYSREQ.C of the command, with the entry point holding it."""
    parsed = scr.parse(image)
    imports = [name for _v, name in parsed['externals']]
    if command not in imports:
        return []
    index = imports.index(command)
    entries = sorted(parsed['internals'])
    c0, c1 = parsed['code']
    words = struct.unpack_from('<%dI' % ((c1 - c0) // 4), image, c0)
    out = []
    for i in range(len(words) - 1):
        if words[i] == 0x7B and words[i + 1] == index:
            holder = [name for off, name in entries if off <= 4 * i]
            out.append((4 * i, holder[-1] if holder else None))
    return out


# ---------------------------------------------------------------------------------------
# The rig: difftest_natives.Rig with the bodies run for real
# ---------------------------------------------------------------------------------------
class Answers:
    """Answers of the body call-outs: name -> list of values, the last one repeating.
    One instance per side, made from the same table, so both sides get the same answers
    in the same order."""

    def __init__(self, table):
        self.table, self.count = table, {}

    def get(self, name):
        index = self.count.get(name, 0)
        self.count[name] = index + 1
        values = self.table.get(name, [0])
        return values[min(index, len(values) - 1)]


def make_rig(elf):
    rig = D.Rig(elf)
    emu, mem = rig.emu, rig.emu.mem
    for name in ('anim_push', 'anim_jumpTopToEnd', 'anim_start', 'sound_playOnObject',
                 'sound_setPlaysWhileFrozen', 'lump_load'):
        address = N.EXT[name].addr
        emu.unhook(address)
        rig.stub_addrs.discard(address)
    rig.real.addresses |= set(L.REAL_BODIES.values())
    rig.answers = Answers({})
    for name, address in L.CALLOUTS.items():
        emu.stub(address, function=callout_stub(rig, name), name=name)
        rig.stub_addrs.add(address)
    for start, size in ((L.G_SOUND_SEQS, L.SOUND_SEQ_SIZE * L.SOUND_SEQS), (L.G_LUMP_PENDING_NAME, 0x80),
                        (L.G_LUMP_TAGS, 0x400), (0x41BF70, 0x40), (0x503890, 8), (0x506048, 4)):
        if not mem.is_mapped(start, size):
            mem.map(start & ~0xFFF, ((start + size + 0xFFF) & ~0xFFF) - (start & ~0xFFF))
    rig.world_block = emu.alloc(0x2000, align=16)      # the level world 0x44fdc8 points at
    rig.model_block = emu.alloc(MODEL_BLOCK, align=16)  # models, clips, class definitions, caches
    rig.order = []
    for name in COMMANDS + ('setMissionAvailable', 'setv', 'postAction', 'newWorld', 'callScript', 'getv',
                            'changeSwoop', 'setEntrance', 'hideMonster', 'removeQuest', 'grantMission',
                            'addHelpMessage', 'removePlayerItem', 'playerHasItem', 'getEvil'):
        address = dict((n, a) for n, a in zip(N.NATIVE_NAMES, native_addresses(mem))).get(name)
        if address is not None:
            emu.hook(address, (lambda label: lambda e: rig.order.append(
                (label, e.r[5] & M32, e.mem.u32((e.r[5] + 4) & M32))))(name))
    return rig


def native_addresses(mem):
    """Handler of each table name, in NATIVE_NAMES order, read from 0x403370."""
    table = {}
    at = L.NATIVE_TABLE
    while mem.u32(at):
        table[mem.cstr(mem.u32(at)).encode('latin-1')] = mem.u32(at + 4)
        at += 8
    return [table.get(n.encode() if isinstance(n, str) else n) for n in N.NATIVE_NAMES]


def callout_stub(rig, name):
    def stub(emu):
        mem = emu.mem
        r = [emu.r[4 + k] & M32 for k in range(4)]

        def text(addr):
            return mem.cstr(addr).encode('latin-1')
        if name == 'world_movePiece':
            args = (r[0], r[1], tuple(mem.u32(r[2] + 4 * j) for j in range(3)), r[3])
        elif name in ('obj_delete', 'creature_bossMusicName'):
            args = (r[0],)
        elif name == 'arena_addKill' or name == 'mem_allocTagged':
            args = (r[0], r[1])
        elif name in ('task_isRunning', 'lump_findLoaded', 'cd_findFile', 'lump_prepare'):
            args = (text(r[0]),)
        elif name == 'cd_readBlocking':
            args = (text(r[0]), r[1], r[2], r[3])
        else:
            args = ()
        rig.calls.append((name, args))
        value = rig.answers.get(name)
        if name == 'cd_findFile':
            exists, size = value
            mem.w32(r[1], 0x1234)
            mem.w32(r[2], size)
            return exists
        return value
    return stub


# ---------------------------------------------------------------------------------------
# The model's host
# ---------------------------------------------------------------------------------------
class LevelHost(D.TestHost):
    """TestHost, except that a call-out or a virtual call whose code the original runs for
    real goes to ref_level_commands.Bodies (not recorded), and the bodies' own call-outs
    are recorded under the same names as the original's stubs."""

    def __init__(self, responder, world, answers):
        D.TestHost.__init__(self, responder, world)
        self.answers = answers
        self.bodies = None

    def call(self, name, *args):
        bodies = self.bodies
        if name in bodies.ext_bodies:
            return bodies.ext_bodies[name](*args)
        if name == 'virtual':
            function, this = bodies.slot_target(args[1], args[0])
            body = bodies.virtual_bodies.get(function)
            if body is not None:
                return body(this, *args[2:])
        return D.TestHost.call(self, name, *args)

    def record(self, name, *args):
        if name in L.CALLOUTS:
            self.log.append((name, args))
            return self.answers.get(name)
        return D.TestHost.call(self, name, *args)


def make_model(scene, seed, machine, table, mutate_store=False):
    mem = N.Mem(D.Under(scene.rig.emu.mem))
    world = scene.rig.world
    world.names, world.objects = O.NameTable(), {}
    objs = {}
    for entry in scene.objects:
        obj = N.Obj(mem, entry['addr'], entry['type'])
        obj.props = list(entry['props']) if entry['props'] is not None else None
        world.objects[entry['addr']] = obj
        objs[entry['addr']] = obj
    world.names.keys = list(scene.table.keys)
    world.names.objs = [None if e is None else objs[e['addr']] for e in scene.table.objs]
    host = LevelHost(D.Responder(seed, scene), world, Answers(table))
    game = N.Game(mem, world, host)
    host.game = game
    host.bodies = L.Bodies(game, host.record)
    if mutate_store:
        def n_activateStore(m, a, game=game):
            game.mem.w16(N.G_STORE_INDEX, a[0])         # control: the < 0x15 test removed
            if game.ext('dialog_isOpen') == 0:
                if game.network_mode == 0:
                    game.ext('shop_openOrStock', game.active_player & M32, 0, 1)
            else:
                game.mem.w8(N.G_STORE_PENDING, 1)
            return 0
        game.n_activateStore = n_activateStore
    game.machine = machine
    machine._bound = None
    machine.register(game.natives())
    return game, host


# ---------------------------------------------------------------------------------------
# State: difftest_natives.Scene plus objects with the real class tables
# ---------------------------------------------------------------------------------------
class LevelScene(D.Scene):
    def __init__(self, rig, rng, names, variables=None, entries=None, objects=None):
        self.real = []
        self.model_at = rig.model_block
        D.Scene.__init__(self, rig, rng, names=names, variables=variables, entries=entries, objects=objects)

    def block(self, size):
        addr = self.model_at
        self.model_at += (size + 15) & ~15
        assert self.model_at < self.rig.model_block + MODEL_BLOCK
        return addr

    def place_props(self, props):
        pointer = self.tables_at
        words = [self.cstring(entry) for entry in props] + [0]
        self.rig.poke(pointer, struct.pack('<%dI' % len(words), *words))
        self.tables_at += 4 * len(words)
        return pointer

    def new_real(self, kind, props, vtable):
        """An object of the shipped record's class: random bytes, then the fields the
        bodies read set as the record and the class constructor make them."""
        rng = self.rng
        index = len(self.objects)
        addr = self.rig.obj_base + 0x1000 * index
        blob = bytearray(rng.randbytes(0x1000))
        struct.pack_into('<I', blob, L.O_VTABLE, vtable)
        struct.pack_into('<I', blob, L.O_PROPS, self.place_props(props))
        struct.pack_into('<3I', blob, L.O_POS, *[D.rand_float(rng) for _ in range(3)])
        entry = {'addr': addr, 'type': b'10GameObject', 'props': list(props), 'kind': kind}
        self.objects.append(entry)
        self.real.append(entry)
        return entry, blob

    def anim_state(self, blob, at, rng, capacity=None):
        """An animation state at +at: cache pointer (0 or a block), count, capacity (1..3
        unless given), flags without 0x800, tracks whose old decoder links are 0 or a block."""
        cache = self.block(0x620) if rng.random() < 0.3 else 0
        struct.pack_into('<I', blob, at, cache)
        capacity = rng.choice((1, 2, 3, 3)) if capacity is None else capacity
        blob[at + 4] = rng.randrange(0, capacity + 1)
        blob[at + 5] = capacity
        struct.pack_into('<H', blob, at + 6, rng.getrandbits(16) & ~0x800)
        for k in range(capacity):
            track = at + 8 + 32 * k
            link = self.block(0x20) if rng.random() < 0.4 else 0
            struct.pack_into('<I', blob, track + 4, link)
            struct.pack_into('<H', blob, track + 0x1C, rng.getrandbits(16) & ~0x800)

    def clip(self, rng):
        addr = self.block(0x10)
        self.rig.poke(addr, struct.pack('<II', 0, rng.choice((0, 1, 30, 61, 240, 0x7FFFFFFF))))
        return addr

    def add_autoprop(self, props, vtable=None, state_choice=None):
        rng = self.rng
        mask, states, flags = L.autoprop_kind(props)
        if vtable is None:
            lp = any(prop(props, k) not in (None, b'0') for k in (b'particleemitter0', b'dynamiclight0', b'halo0'))
            vtable = L.VT_AUTOPROP_LP if lp else L.VT_AUTOPROP
        entry, blob = self.new_real('autoprop', props, vtable)
        object_flags = (rng.getrandbits(32) & ~(L.OF_DEAD | L.OF_CREATURE | 0x40)) | L.OF_AUTOPROP
        struct.pack_into('<I', blob, L.O_FLAGS, object_flags)
        model = self.block(0x20 + 16 * 12)
        groups = rng.randrange(0, 2)
        mrec = bytearray(rng.randbytes(0x20 + 16 * 12))
        struct.pack_into('<H', mrec, 0x10, rng.getrandbits(16) | (2 if rng.random() < 0.7 else 0))
        mrec[0x21] = 2 + groups
        self.rig.poke(model, bytes(mrec))
        struct.pack_into('<I', blob, L.AP_MODEL, model)
        self.anim_state(blob, L.AP_ANIM, rng, capacity=1)     # one track: the mask follows at +0xc8
        struct.pack_into('<I', blob, L.AP_KIND, mask)
        struct.pack_into('<i', blob, L.AP_STATES, states)
        for k in range(10):
            struct.pack_into('<I', blob, L.AP_ANIMS + 8 * k, self.clip(rng) if k <= max(states, 0) and
                             rng.random() < 0.9 else 0)
            struct.pack_into('<I', blob, L.AP_STATE_FLAGS + 8 * k, flags[k] | (0x10 if rng.random() < 0.5 else 0))
        state = rng.randrange(max(states, 1)) if state_choice is None else state_choice
        struct.pack_into('<i', blob, L.AP_STATE, state)
        struct.pack_into('<i', blob, L.AP_PIECE, rng.choice((-1, 0, 1, 2)))
        self.rig.poke(entry['addr'], bytes(blob))
        return entry

    def add_gnome(self, props, alive=True):
        rng = self.rng
        entry, blob = self.new_real('creature', props, L.VT_GNOME)
        flags = rng.getrandbits(32) & ~(L.OF_DEAD | L.OF_AUTOPROP | L.OF_DELETE_ON_DEATH | 0x40) | L.OF_CREATURE
        if not alive:
            flags |= L.OF_DEAD
        if rng.random() < 0.1:
            flags |= L.OF_DELETE_ON_DEATH
        struct.pack_into('<I', blob, L.O_FLAGS, flags)
        cls = self.block(0xC8)
        self.rig.poke(cls, bytes(0xC8))
        for k in range(4):
            self.rig.poke(cls + L.CLASS_DEATH_ANIMS + 8 * k, struct.pack('<I', self.clip(rng)))
        struct.pack_into('<I', blob, L.C_CLASS, cls)
        self.anim_state(blob, L.C_ANIM, rng)
        blob[L.C_HIDDEN] = rng.choice((0, 0, 0, 1))
        struct.pack_into('<h', blob, L.C_AI_STATE, rng.choice((0, 1, 3, 6, 0x10, 0x17)))
        struct.pack_into('<I', blob, L.C_TARGET, rng.choice((0, 0, 0x1234)))
        struct.pack_into('<I', blob, L.C_OWNER, 0)
        self.rig.poke(entry['addr'], bytes(blob))
        return entry

    def finish(self, extra_names=()):
        """Enter the real objects in the name table and write the table again."""
        for entry in self.real:
            name = prop(entry['props'], b'name')
            if name is not None:
                self.table.add(self.vary_case(name) if self.rng.random() < 0.3 else name, entry)
        for name, entry in extra_names:
            self.table.add(name, entry)
        keys, objs = [], []
        for slot in range(512):
            key = self.table.keys[slot]
            keys.append(0 if key is None else self.cstring(key))
            objs.append(0 if self.table.objs[slot] is None else self.table.objs[slot]['addr'])
        self.rig.poke(O.G_NAME_KEYS, struct.pack('<512I', *keys))
        self.rig.poke(O.G_NAME_OBJS, struct.pack('<512I', *objs))

    def world(self):
        """The level world 0x44fdc8: 4 piece records -> chunks."""
        rng, rig = self.rng, self.rig
        base = rig.world_block
        pieces, chunks = base + 0x100, base + 0x400
        rig.poke(base, rng.randbytes(0x100))
        rig.poke(base + 0x54, struct.pack('<I', pieces))
        rig.poke(base + 0x20, struct.pack('<I', chunks))
        for k in range(4):
            rig.poke(pieces + 28 * k, rng.randbytes(28))
            rig.poke(pieces + 28 * k + 0x18, struct.pack('<h', rng.randrange(4)))
        rig.poke(chunks, rng.randbytes(36 * 4))
        self.w(L.G_WORLD, 4, base)

    def sound_table(self):
        rng, rig = self.rng, self.rig
        for k in range(L.SOUND_SEQS):
            player = L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * k
            busy = rng.random() < 0.6
            rig.poke(player, rng.randbytes(L.SOUND_SEQ_SIZE))
            rig.poke(player + 4, bytes([1 if busy else 0, 1]))
            rig.poke(player + 6, struct.pack('<H', rng.getrandbits(16) & ~0x800))
            rig.poke(player + 8, struct.pack('<I', rig.token_base + 4 * rng.randrange(64)))
            rig.poke(player + 0xC, struct.pack('<I', 0))
        rig.poke(L.G_SOUND_GROUP_CAP, bytes(rng.choice((0, 1, 2, 5, 100)) for _ in range(256)))
        self.w(L.G_SOUND_SERIAL, 2, rng.getrandbits(16))
        for addr in (L.G_FREEZE_B, L.G_FRAME_COUNT):
            self.w(addr, 4, rng.choice((0, 0, 1, 59, 60)))
        self.w(L.G_FREEZE_C, 1, rng.choice((0, 1)))
        rig.poke(rig.token_base, bytes(rng.choice((0, 0, 1, 2)) for _ in range(0x200)))

    def globals_for_bodies(self, arena=None):
        rng = self.rng
        on = rng.random() < 0.15 if arena is None else arena
        self.w(L.G_ARENA, 4, 1 if on else 0)
        self.w(L.G_ARENA_B, 4, rng.choice((0, 1)))
        self.w(L.G_GATE_C, 4, rng.choice((0, 1)))
        self.w(L.G_GATE_D, 4, rng.choice((0, 1)))
        self.w(L.G_LUMP_TAG_INDEX, 4, rng.randrange(8))
        self.world()
        self.sound_table()

    def quest_vars(self, values):
        blob = bytearray()
        for name, value in values:
            blob += name.lower() + b'\0' + bytes([value & 0xFF])
        self.rig.poke(N.G_QUEST_VARS, bytes(blob) + bytes(0x200))


def quest_var(mem, name):
    """The signed value byte of a quest variable in the packed table 0x86da80, or None."""
    at = N.G_QUEST_VARS
    while mem.u8(at):
        key = mem.cstr(at).encode('latin-1')
        at += len(key) + 1
        if key == name:
            return N.s8(mem.u8(at))
        at += 1
    return None


def body_table(rng):
    """Answers of the body call-outs for one case."""
    loaded = rng.choice((0, 0x7A0000))
    return {'creature_bossMusicName': [rng.choice((0, 0, 0x5000))], 'task_isRunning': [rng.choice((0, 1))],
            'lump_findLoaded': [loaded, rng.choice((0x7A0040, 0))], 'cd_findFile': [(0, 0) if rng.random() < 0.1 else (1, rng.choice((0, 1, 0x800, 0x12345)))],
            'mem_allocTagged': [0x6A0000 + 0x40 * rng.randrange(16)]}


# ---------------------------------------------------------------------------------------
# One compared run
# ---------------------------------------------------------------------------------------
def run_case(rig, machine, game, host, model_run, emu_run, table):
    rig.answers = Answers(table)
    rig.order = []
    return D.compare(rig, machine, game, host, model_run, emu_run)


def written_bytes(rig, lo_image, hi_image):
    out = set()
    for _pc, addr, size, _v in rig.emu.writes:
        if lo_image <= addr < hi_image or D.STACK_LO <= addr < D.STACK_HI:
            continue
        out.update(range(addr, addr + size))
    return out


REGIONS = [('player records', N.G_PLAYERS, N.G_PLAYERS + 4 * N.REC_SIZE),
           ('quest variables', N.G_QUEST_VARS, N.G_QUEST_VARS + 0x2000),
           ('post action', N.G_POST_ACTION, N.G_POST_ACTION + 0x50),
           ('pending level and orientation', N.G_PENDING_LEVEL, N.G_PENDING_LEVEL + 0x51),
           ('entrance', N.G_ENTRANCE_NAME, N.G_ENTRANCE_NAME + 0x50),
           ('selected object', L.G_SELECTED_OBJ, L.G_SELECTED_OBJ + 4),
           ('store index', L.G_STORE_INDEX, L.G_STORE_INDEX + 2),
           ('store pending', L.G_STORE_PENDING, L.G_STORE_PENDING + 1),
           ('sound players', L.G_SOUND_SEQS, L.G_SOUND_SEQS + L.SOUND_SEQ_SIZE * L.SOUND_SEQS),
           ('sound serial', L.G_SOUND_SERIAL, L.G_SOUND_SERIAL + 2),
           ('lump pending', 0x41BF80, 0x41BFA8), ('lump name', L.G_LUMP_PENDING_NAME, L.G_LUMP_PENDING_NAME + 0x80),
           ('obj_getPropStr keys', L.S_DEATH_SCRIPT, L.S_DROP_ITEM + 9),
           ('newWorld cooldowns', 0, 0), ('missing-entry stamp', N.G_MISSING_STAMP, N.G_MISSING_STAMP + 4),
           ('chunks of the world', 0, 0), ('models/clips/caches', 0, 0), ('objects', 0, 0)]


def spans(offsets):
    out, run = [], None
    for off in sorted(offsets):
        if run and off == run[1] + 1:
            run[1] = off
        else:
            run = [off, off]
            out.append(run)
    return ' '.join('+0x%x' % a if a == b else '+0x%x-0x%x' % (a, b) for a, b in out)


def region_text(regions):
    fields = {int(k.split('+0x')[1], 16) for k in regions if k.startswith('target object')}
    rest = sorted((k, v) for k, v in regions.items() if not k.startswith('target object'))
    return '; '.join('%s %d' % kv for kv in rest) + '; target-object fields ' + spans(fields)


def classify(rig, addresses, real_objects):
    regions = {}
    world, model = rig.world_block, rig.model_block
    for addr in addresses:
        name = None
        for label, lo, hi in REGIONS:
            if lo <= addr < hi:
                name = label
                break
        if name is None:
            if world <= addr < world + 0x2000:
                name = 'chunks of the world'
            elif model <= addr < model + MODEL_BLOCK:
                name = 'models/clips/caches'
            elif rig.obj_base <= addr < rig.obj_base + 0x1000 * 200:
                base = rig.obj_base + ((addr - rig.obj_base) & ~0xFFF)
                name = 'target object +0x%x' % (addr - base) if base in real_objects else 'other objects'
            elif rig.tables <= addr < rig.tables + 0x8000 or rig.strings <= addr < rig.strings + 0x20000:
                name = 'name keys'
            else:
                name = 'OTHER 0x%x' % addr
        regions[name] = regions.get(name, 0) + 1
    return regions


# ---------------------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------------------
def group_binding(rig, images):
    mem = rig.emu.mem
    table = dict(zip(N.NATIVE_NAMES, native_addresses(mem)))
    bad, count, examples = 0, 0, []
    for name in COMMANDS:
        count += 1
        if table.get(name) != L.HANDLERS[name]:
            bad += 1
            examples.append('%s table 0x%x' % (name, table.get(name) or 0))
    report('binding: table 0x403370', bad, count, 'each name -> its handler (0x142320 0x144a84 0x143684 '
           '0x14222c 0x144010)', examples)
    bad, count, examples = 0, 0, []
    for level, image in sorted(images.items()):
        error, bound = rig.place(image)
        parsed = scr.parse(image)
        for i, (_v, name) in enumerate(parsed['externals']):
            if name in COMMANDS:
                count += 1
                value = mem.u32(rig.base + 0x60 + struct.unpack_from('<I', image, 0x60 + 0x2C)[0] + 24 * i)
                if error or bound or value != L.HANDLERS[name]:
                    bad += 1
                    examples.append('%s %s 0x%x' % (level, name, value))
    report('binding: scr_registerNatives', bad, count, 'every import of the five names in %d level scripts is '
           'bound to the handler address' % len(images), examples)


def new_machine(rig, image):
    error, bound = rig.place(image)
    assert error == 0 and bound == 0
    machine = D.new_machine(image)
    return machine, machine.snapshot()


def group_direct(rig, seed, cases, controls):
    image = D.synthetic_image()
    machine, saved = new_machine(rig, image)
    master = random.Random(seed ^ 0x1E7E1)
    names = [b'brazier1', b'brazier5', b'trigger2', b'portal', b'gnome1', b'gnome6', b'door_a', b'gob']
    stats = {'ok_returns': 0}
    for command in COMMANDS:
        tally = D.Tally()
        mutants = {'autoPropSetState': ('autoprop_bits_for_zero', 'autoprop_mode_swapped', 'passable_inverted'),
                   'killMonster': ('kill_no_deathscript', 'kill_keeps_selected', 'gnome_anim_first'),
                   'soundSequence': ('sound_first_free',), 'preloadResource': ('lump_skip_loaded_check',),
                   'activateStore': ('store_any_index',)}[command]
        rejected = {m: 0 for m in mutants}
        for case_index in range(cases):
            case_seed = master.getrandbits(32)
            for mutation in (None,) + (mutants if case_index < controls else ()):
                rng = random.Random(case_seed)
                rig.restore()
                machine.restore(saved)
                scene = LevelScene(rig, rng, names=names, entries=[b'alpha', b'delta', b'missing', b''])
                scene.globals_for_bodies(arena=rng.random() < 0.3)
                if rng.random() < 0.5:                  # the gate combination that refuses a state
                    for addr, value in ((L.G_ARENA_B, 0), (L.G_GATE_C, 1), (L.G_GATE_D, 0)):
                        scene.w(addr, 4, value)
                prop_target, gnome_target = rng.choice(names[:4]), rng.choice(names[4:6])
                for k in range(rng.randrange(1, 4)):
                    props = [b'name=' + (prop_target if k == 0 else rng.choice(names[:4])), b'autoprop=1',
                             b'states=%d' % rng.choice((1, 2, 3, 3, 0, 12)),
                             b'pokeable=1', b'passable=' + bytes(rng.choice(b'01') for _ in range(3)),
                             b'loopinganimation=' + bytes(rng.choice(b'01') for _ in range(3))]
                    if rng.random() < 0.5:
                        props.append(b'autodoor=1')
                    if rng.random() < 0.5:
                        props.append(b'particleemitter0=1')
                    scene.add_autoprop(props)
                for k in range(rng.randrange(1, 4)):
                    props = [b'name=' + (gnome_target if k == 0 else rng.choice(names[4:6])),
                             b'deathscript=' + rng.choice((b'alpha', b'delta', b'missing'))]
                    if rng.random() < 0.2:
                        props.append(b'dropitem=potion')
                    scene.add_gnome(props, alive=rng.random() < 0.8)
                scene.finish()
                case = D.Case(rig, machine, rng)
                if command == 'autoPropSetState':
                    args = [case.string(scene.vary_case(prop_target if rng.random() < 0.8 else rng.choice(names))),
                            rng.choice((0, 1, 2, 3, 11, 0x7FFFFFFF, 0, 1, 0, 1, 2))]
                elif command == 'killMonster':
                    args = [case.string(scene.vary_case(gnome_target if rng.random() < 0.8 else rng.choice(names)))]
                else:
                    args = D.make_args(D.SPEC[command], scene, case, rng)
                params = case.commit(args)
                table = body_table(rng)
                L.MUTATION = mutation if mutation != 'store_any_index' else None
                game, host = make_model(scene, case_seed, machine, table, mutate_store=mutation == 'store_any_index')
                rig.responder = D.Responder(case_seed, scene)
                index = D.INDEX[command]

                def model_run():
                    return machine._call_native(index, params)

                def emu_run():
                    rig.w32(rig.cells, 0x55555555)
                    error = N.s32(rig.call(D.SCR_CALL_NATIVE, rig.base, index, rig.cells,
                                           rig.base + machine.data_offset + params))
                    return error, rig.emu.mem.s32(rig.cells)
                try:
                    outcome = run_case(rig, machine, game, host, model_run, emu_run, table)
                finally:
                    L.MUTATION = None
                if mutation is None:
                    tally.add(outcome, '%s seed %d' % (command, case_seed))
                    if outcome.fault is None and not outcome.problems:
                        stats['ok_returns'] += 1
                elif outcome.problems or outcome.fault in ('model', 'emu'):
                    rejected[mutation] += 1
        report('direct: ' + command, tally.bad, tally.cases, 'dispatcher result 0 / error 0, call-outs, bytes '
               'stored, seed, machine; %d call-outs, %d cases where both sides stop (fault)'
               % (tally.calls, tally.faults), tally.examples)
        for mutation, hits in rejected.items():
            report('control: ' + mutation, 0 if hits else 1, min(cases, controls),
                   'the changed model is rejected in %d of %d cases' % (hits, min(cases, controls)))
    return stats


def run_entry(rig, machine, game, host, name, table, pointer):
    def model_run():
        return game.run_script(name)

    def emu_run():
        return N.s32(rig.call(D.A['script_runByName'], pointer, max_steps=40000000))
    return run_case(rig, machine, game, host, model_run, emu_run, table)


def fresh(rig, machine, saved, rng, names, variables):
    rig.restore()
    machine.restore(saved)
    scene = LevelScene(rig, rng, names=names, variables=variables, entries=[b''], objects=rng.randrange(2, 6))
    scene.globals_for_bodies(arena=False)
    scene.w(N.G_NETWORK_MODE, 1, 0)
    scene.w(N.G_IN_POST_ACTION, 1, 0)
    scene.w(N.G_JUMPGATE_TRAVEL, 4, 0)
    scene.w(N.G_PENDING_LEVEL, 0x50, 0)
    scene.w(N.G_NUM_PLAYERS, 4, scene.num_players or 1)    # mission_setAvailable writes g_numPlayers records
    return scene


def group_tormenta(rig, data, seed, cases):
    image = gob_file(data, 'tormenta', 'script.scr') + bytes(256)
    records = object_records(gob_file(data, 'tormenta', 'objects.ob'))
    sites = call_sites(image, 'autoPropSetState')
    start_sites = [off for off, holder in sites if holder == 'start']
    # the five names start passes, read from the push before each call (never printed)
    machine, saved = new_machine(rig, image)
    pool = dict(scr.strings(image, *scr.parse(image)['strings']))
    code0 = scr.parse(image)['code'][0]
    start_names = []
    for off in start_sites:
        words = struct.unpack_from('<14I', image, code0 + off - 56)
        pushes = [words[j + 1] for j in range(13) if words[j] == 0x27 and words[j + 1] in pool]
        start_names.append(pool[pushes[-1]].encode('latin-1'))
    present = {prop(p, b'name'): (c, p) for c, p in records if prop(p, b'name') is not None}
    targets = [n for n in start_names if n in present]
    targets_all = sorted({n for n in present if n.startswith((b'brazier', b'trigger'))})
    print('      tormenta start: %d autoPropSetState calls at %s; %d of their names have an object record '
          '(names T1..T5 in call order: %s present)' % (len(start_sites), ' '.join('0x%x' % s for s in start_sites),
                                                        len(targets), ''.join('T%d ' % (i + 1) for i, n in
                                                                              enumerate(start_names) if n in present)))
    shapes = sorted({('LP' if any(prop(present[n][1], k) not in (None, b'0') for k in
                                  (b'particleemitter0', b'dynamiclight0', b'halo0')) else 'plain',
                      L.autoprop_kind(present[n][1])[0], L.autoprop_kind(present[n][1])[1],
                      tuple(L.autoprop_kind(present[n][1])[2][:3])) for n in targets})
    print('      their records (AutoProp kind, +0x11c mask, States, state flags 0..2): %s' % shapes)
    tally, expect_bad, expect_n, examples = D.Tally(), 0, 0, []
    pre_bad, pre_n, pre_paths = 0, 0, {}
    regions_seen = {}
    for case_index in range(cases):
        case_seed = random.Random(seed ^ 0x70A + case_index).getrandbits(32)
        rng = random.Random(case_seed)
        variables = [b'tor_bri1', b'tor_bri2', b'tor_bri5', b'startedmission5', b'currentmission', b'tor_beenhere']
        scene = fresh(rig, machine, saved, rng, start_names + [b'blocker1', b'x'], variables)
        reals = {}
        for name in targets_all:
            entry = scene.add_autoprop(present[name][1])
            reals[name] = entry
        scene.finish()
        scene.quest_vars([(v, rng.choice((0, 0, 1, 0x5A))) for v in rng.sample(variables, rng.randrange(4))])
        difficulty = rng.randrange(4)
        scene.w(N.G_DIFFICULTY, 4, difficulty)
        before = {n: dict(state=rig.emu.mem.s32(e['addr'] + L.AP_STATE), flags=rig.emu.mem.u32(e['addr'] + L.O_FLAGS))
                  for n, e in reals.items()}
        table = body_table(rng)
        game, host = make_model(scene, case_seed, machine, table)
        rig.responder = D.Responder(case_seed, scene)
        entry_name = b'start' if case_index % 3 else b'preStart'
        outcome = run_entry(rig, machine, game, host, entry_name, table, scene.cstring(entry_name))
        tally.add(outcome, 'tormenta %s seed %d' % (entry_name.decode(), case_seed))
        mem = rig.emu.mem
        order = [item[0] for item in rig.order]
        if entry_name == b'preStart':
            pre_n += 1
            problems = []
            loaded = table['lump_findLoaded'][0]
            exists = table['cd_findFile'][0][0]
            if outcome.fault is None:
                if order.count('preloadResource') != 1 or order[-1] != 'preloadResource' or mem.u32(rig.base + 0x5C):
                    problems.append('order %s' % order)
                wrote = mem.u32(L.G_LUMP_PENDING_DATA) == table['mem_allocTagged'][0]
                if loaded and wrote or not loaded and not wrote:
                    problems.append('lump state (loaded 0x%x)' % loaded)
                pre_paths['loaded' if loaded else 'read'] = pre_paths.get('loaded' if loaded else 'read', 0) + 1
            elif outcome.fault == 'both' and not loaded and not exists:
                pre_paths['missing: both stop'] = pre_paths.get('missing: both stop', 0) + 1
            else:
                problems.append('fault %s' % outcome.fault)
            if problems:
                pre_bad += 1
                examples.append('preStart seed %d: %s' % (case_seed, '; '.join(problems)))
        if entry_name == b'start':
            expect_n += 1
            problems = []
            if order[:6] != ['autoPropSetState'] * 5 + ['setMissionAvailable']:
                problems.append('order %s' % order[:7])
            if mem.u32(rig.base + 0x5C) != 0:
                problems.append('machine error %d' % mem.u32(rig.base + 0x5C))
            byte = mem.u8(N.G_PLAYERS + 0x4BBF + difficulty * 13 + 5)
            if not byte & 1:
                problems.append('mission 5 not available')
            for name in targets:
                o = reals[name]['addr']
                passable = mem.u32(o + L.AP_STATE_FLAGS) & 1
                if (mem.s32(o + L.AP_STATE) != 0 or mem.u64(o + L.AP_REACHED) != 0
                        or (mem.u32(o + L.O_FLAGS) & 1) != passable
                        or mem.u64(o + L.AP_MASK) != L.Bodies(game, None).model_build_hide_mask(
                            mem.u32(o + L.AP_MODEL), 0) or mem.u8(o + L.AP_ANIM + 4) != (
                            1 if mem.u32(o + L.AP_ANIMS) and mem.s8(o + L.AP_ANIM + 5) > 0 else 0)):
                    problems.append('target %s fields' % name[-1:])
            for name in set(targets_all) - set(targets):
                o = reals[name]['addr']
                if mem.s32(o + L.AP_STATE) != before[name]['state'] or mem.u32(o + L.O_FLAGS) != before[name]['flags']:
                    problems.append('untouched object changed')
            if problems:
                expect_bad += 1
                examples.append('seed %d: %s' % (case_seed, '; '.join(problems)))
            ebytes = written_bytes(rig, rig.base, rig.base + rig.image_size + 0x200)
            for key, value in classify(rig, ebytes, {e['addr'] for e in reals.values()}).items():
                regions_seen[key] = regions_seen.get(key, 0) + value
    report('shipped: tormenta preStart/start', tally.bad, tally.cases, 'whole entries vs model; %d call-outs'
           % tally.calls, tally.examples)
    report('shipped: tormenta start expectations', expect_bad, expect_n,
           'five autoPropSetState calls then setMissionAvailable(5,1) (mission byte bit 0 set), error word 0; '
           'each present target: state +0x178 = 0, reached +0x180 = 0, mask +0xc8 = ~model+8, flag 0x1 = state-0 '
           'Passable bit, one track; objects of the other names untouched', examples)
    report('shipped: tormenta preStart expectations', pre_bad, pre_n,
           'preloadResource entered once as the last built-in, error word 0; pending lump data 0x41bfa0 written '
           'only when lump_findLoaded answered 0; paths %s' % ', '.join('%s %d' % kv for kv in sorted(pre_paths.items())),
           examples)
    other = sorted(k for k in regions_seen if k.startswith('OTHER'))
    report('shipped: tormenta start store regions', len(other), max(expect_n, 1),
           'bytes stored outside the script image (region: byte count): ' + region_text(regions_seen), other)


def group_islgnome(rig, data, seed, cases):
    image = gob_file(data, 'islgnome', 'script.scr') + bytes(256)
    records = object_records(gob_file(data, 'islgnome', 'objects.ob'))
    sites = call_sites(image, 'killMonster')
    machine, saved = new_machine(rig, image)
    pool = dict(scr.strings(image, *scr.parse(image)['strings']))
    code0 = scr.parse(image)['code'][0]
    kill_names = []
    for off, _holder in sites:
        words = struct.unpack_from('<14I', image, code0 + off - 56)
        pushes = [words[j + 1] for j in range(13) if words[j] == 0x27 and words[j + 1] in pool]
        kill_names.append(pool[pushes[-1]].encode('latin-1'))
    present = {prop(p, b'name'): (c, p) for c, p in records if prop(p, b'name') is not None}
    gnomes = [n for n in kill_names if n in present]
    classes = sorted({'Gnome' if present[n][0].lower().startswith(b'gnome') else '?' for n in gnomes})
    death = sorted({prop(present[n][1], b'deathscript') for n in gnomes})
    parsed = scr.parse(image)
    publics = {name for _o, name in parsed['internals']}
    print('      islgnome: %d killMonster calls at %s, all in %s; %d names G1..G%d have records of classes %s; '
          'one deathscript for all, a public entry: %s'
          % (len(sites), '-'.join('0x%x' % s for s in (sites[0][0], sites[-1][0])),
             sorted({h for _o, h in sites}), len(gnomes), len(gnomes), classes,
             len(death) == 1 and death[0].decode() in publics))
    counter = None
    tally, expect_bad, expect_n, examples = D.Tally(), 0, 0, []
    kills = deaths_refused = cleared = kept = 0
    regions_seen = {}
    for case_index in range(cases):
        case_seed = random.Random(seed ^ 0x6E0 + case_index).getrandbits(32)
        rng = random.Random(case_seed)
        variables = [b'startedquest', b'finishedquest', b'gnomesalivev']
        scene = fresh(rig, machine, saved, rng, kill_names + [b'x'], variables)
        reals = {}
        for name in gnomes:
            reals[name] = scene.add_gnome(present[name][1], alive=rng.random() < 0.8)
        trigger = scene.objects[0]
        orientation = rng.randrange(0, 256)
        trig_props = [b'orientation=%d' % orientation, b't=entrance1']
        trigger['props'] = trig_props
        scene.rig.poke(trigger['addr'] + L.O_PROPS, struct.pack('<I', scene.place_props(trig_props)))
        scene.w(L.G_SELECTED_OBJ, 4, trigger['addr'])
        arena = case_index % 5 == 4 or rng.random() < 0.15
        scene.globals_for_bodies(arena=arena)
        if case_index % 5 == 4:
            for addr, value in ((L.G_ARENA_B, 0), (L.G_GATE_C, 1), (L.G_GATE_D, 0)):
                scene.w(addr, 4, value)
        scene.finish()
        mode = case_index % 4
        started, finished = [(1, 0), (1, 0), (1, 1), (0, 0)][mode]
        alive0 = rng.randrange(0, 20)
        scene.quest_vars([(b'startedQuest', started), (b'finishedQuest', finished), (b'gnomesAliveV', alive0)])
        # the script's own gnome counter (data cell 0x26c, written by gnomeinit / gnomeDied)
        counter = alive0
        rig.poke(rig.base + machine.data_offset + 0x26C, struct.pack('<i', counter))
        machine.set_cell(0x26C, counter)
        table = body_table(rng)
        game, host = make_model(scene, case_seed, machine, table)
        rig.responder = D.Responder(case_seed, scene)
        entry_name = b'entrance%d' % (1 + case_index % 3)
        mem = rig.emu.mem
        before = {n: (mem.u32(e['addr'] + L.O_FLAGS), mem.u32(e['addr'] + L.C_RAND)) for n, e in reals.items()}
        gate = (mem.u32(L.G_ARENA) != 0 and mem.u32(L.G_ARENA_B) == 0 and mem.u32(L.G_GATE_C) != 0
                and mem.u32(L.G_GATE_D) == 0)
        outcome = run_entry(rig, machine, game, host, entry_name, table, scene.cstring(entry_name))
        tally.add(outcome, 'islgnome %s seed %d' % (entry_name.decode(), case_seed))
        expect_n += 1
        problems = []
        order = [item[0] for item in rig.order]
        killing = started == 1 and finished == 0
        kill_calls = [label for label in order if label == 'killMonster']
        if len(kill_calls) != (8 if killing else 0) or order[-1:] != ['newWorld'] or order.count('newWorld') != 1:
            problems.append('order %s' % order)
        if mem.u32(rig.base + 0x5C) != 0:
            problems.append('machine error')
        died = 0
        for name, entry in reals.items():
            o = entry['addr']
            flags0, rand0 = before[name]
            living = flags0 & (L.OF_CREATURE | L.OF_DEAD) == L.OF_CREATURE
            if killing and living:
                kills += 1
                if mem.u32(o + L.O_FLAGS) & L.KILL_FLAGS != L.KILL_FLAGS or mem.u32(o + L.C_HP) != 0:
                    problems.append('kill flags/hp')
                if gate:
                    deaths_refused += 1
                    if mem.u32(o + L.C_RAND) != rand0:
                        problems.append('refused gate drew')
                else:
                    died += 1
                    if mem.s16(o + L.C_AI_STATE) != 0x14 or mem.u32(o + L.C_RAND) == rand0:
                        problems.append('death state')
            elif mem.u32(o + L.O_FLAGS) != flags0:
                problems.append('a dead or untouched gnome changed')
        expect_var = alive0 - died if killing else alive0
        if True:
            pending = mem.cstr(N.G_PENDING_LEVEL).encode('latin-1')
            orient = mem.u8(N.G_PENDING_ORIENT)
            if pending != b'islc2':
                problems.append('pending level')
            if died:
                cleared += 1
                if orient != 0xFF or mem.u32(L.G_SELECTED_OBJ) != 0:
                    problems.append('orientation %d selected 0x%x' % (orient, mem.u32(L.G_SELECTED_OBJ)))
            else:
                kept += 1
                if orient != orientation or mem.u32(L.G_SELECTED_OBJ) != trigger['addr']:
                    problems.append('orientation kept')
            value = quest_var(mem, b'gnomesalivev')
            if value != max(-128, min(127, expect_var)):
                problems.append('gnomesAliveV %r expected %d' % (value, expect_var))
            ebytes = written_bytes(rig, rig.base, rig.base + rig.image_size + 0x200)
            for key, value in classify(rig, ebytes, {e['addr'] for e in reals.values()}).items():
                regions_seen[key] = regions_seen.get(key, 0) + value
        if problems:
            expect_bad += 1
            examples.append('seed %d %s: %s' % (case_seed, entry_name.decode(), '; '.join(problems[:4])))
    report('shipped: islgnome entrances', tally.bad, tally.cases, 'whole entries vs model; %d call-outs'
           % tally.calls, tally.examples)
    report('shipped: islgnome expectations', expect_bad, expect_n,
           'quest started and not finished: 8 killMonster then newWorld; each living gnome gets 0x2009 and hp 0; '
           'past the gate: state 0x14, one own draw, deathscript -> gnomesAliveV - 1; %d kills, %d refused by the '
           'arena gate; pending islc2 with orientation 0xff and selected object 0 after a death (%d runs) or the '
           'trigger\'s orientation with none (%d runs); other quest states: no kill, the same travel' %
           (kills, deaths_refused, cleared, kept), examples)
    other = sorted(k for k in regions_seen if k.startswith('OTHER'))
    report('shipped: islgnome store regions', len(other), max(expect_n, 1),
           'bytes stored outside the script image (region: byte count): ' + region_text(regions_seen), other)


def group_hub(rig, data, seed, cases):
    tally, expect_bad, expect_n, examples = D.Tally(), 0, 0, []
    stored = pending = opened = 0
    arguments = set()
    for level in ('hub', 'hub2'):
        image = gob_file(data, level, 'script.scr') + bytes(256)
        machine, saved = new_machine(rig, image)
        holders = sorted({h for _o, h in call_sites(image, 'activateStore')})
        strings = [s.encode('latin-1') for _o, s in scr.strings(image, *scr.parse(image)['strings'])][:60]
        for k, holder in enumerate(holders):
            for rep in range(cases):
                case_seed = random.Random(seed ^ {'hub': 0x4B1, 'hub2': 0x4B2}[level] + 31 * k + rep).getrandbits(32)
                rng = random.Random(case_seed)
                scene = fresh(rig, machine, saved, rng, strings[:20] or [b'x'], strings[:20] or [b'x'])
                scene.finish()
                dialog = rep % 2
                scene.bias = {'dialog_isOpen': float(dialog), 'memcard_isBusy': 0.2}
                scene.w(N.G_RECALL_COUNTDOWN, 1, 0)
                sentinel = rng.choice((0x5A5A, 0xA5A5))
                scene.w(N.G_STORE_INDEX, 2, sentinel)
                scene.w(N.G_STORE_PENDING, 1, 0)
                table = body_table(rng)
                game, host = make_model(scene, case_seed, machine, table)
                rig.responder = D.Responder(case_seed, scene)
                name = holder.encode()
                outcome = run_entry(rig, machine, game, host, name, table, scene.cstring(name))
                tally.add(outcome, '%s %s seed %d' % (level, holder, case_seed))
                mem = rig.emu.mem
                expect_n += 1
                problems = []
                hits = [item[2] for item in rig.order if item[0] == 'activateStore']
                if len(hits) != 1:
                    problems.append('activateStore entered %d times' % len(hits))
                else:
                    argument = hits[0]
                    arguments.add('%s 0x%x' % ('push' if call_pushes(image, holder) else 'no push', argument))
                    index = mem.u16(N.G_STORE_INDEX)
                    if argument < 0x15:
                        stored += 1
                        if index != argument & 0xFFFF:
                            problems.append('index')
                    elif index != sentinel:
                        problems.append('index written for argument 0x%x' % argument)
                opens = [c for c in rig.calls if c[0] == 'shop_openOrStock']
                if dialog:
                    pending += 1
                    if mem.u8(N.G_STORE_PENDING) != 1 or opens:
                        problems.append('pending')
                else:
                    opened += 1
                    if mem.u8(N.G_STORE_PENDING) != 0 or len(opens) != 1 or opens[0][1][1:] != (0, 1):
                        problems.append('open %r' % opens)
                if mem.u32(rig.base + 0x5C) != 0:
                    problems.append('machine error')
                if problems:
                    expect_bad += 1
                    examples.append('%s %s: %s' % (level, holder, '; '.join(problems)))
    report('shipped: hub/hub2 activateStore entries', tally.bad, tally.cases, 'whole entries vs model; %d call-outs'
           % tally.calls, tally.examples)
    report('shipped: activateStore expectations', expect_bad, expect_n,
           'one entry each; index 0x4f7150 written only for an argument < 0x15 (%d runs; arguments seen: %s); '
           'dialog open: 0x4fdd30 = 1, no shop call (%d); closed: shop_openOrStock(active, 0, 1), flag untouched (%d)'
           % (stored, '/'.join(sorted(arguments)), pending, opened), examples)


def group_sound(rig, data, seed, cases):
    tally, expect_bad, expect_n, examples = D.Tally(), 0, 0, []
    entered = after = 0
    holders_seen = []
    for level in SOUND_LEVELS:
        image = gob_file(data, level, 'script.scr') + bytes(256)
        machine, saved = new_machine(rig, image)
        holders = sorted({h for _o, h in call_sites(image, 'soundSequence')})
        holders_seen.append('%s:%d' % (level, len(holders)))
        strings = [x.encode('latin-1') for _o, x in scr.strings(image, *scr.parse(image)['strings'])][:40]
        for holder in holders:
            for rep_index in range(cases):
                case_seed = random.Random(seed ^ 0x50D + 977 * SOUND_LEVELS.index(level) + rep_index).getrandbits(32)
                rng = random.Random(case_seed)
                scene = fresh(rig, machine, saved, rng, strings[:20] or [b'x'], strings[:30] or [b'x'])
                scene.finish()
                table = body_table(rng)
                game, host = make_model(scene, case_seed, machine, table)
                rig.responder = D.Responder(case_seed, scene)
                name = holder.encode()
                outcome = run_entry(rig, machine, game, host, name, table, scene.cstring(name))
                tally.add(outcome, '%s %s seed %d' % (level, holder, case_seed))
                order = [item[0] for item in rig.order]
                if 'soundSequence' in order:
                    expect_n += 1
                    entered += 1
                    rest = order[order.index('soundSequence') + 1:]
                    after += 1 if rest else 0
                    if outcome.fault is not None or rig.emu.mem.u32(rig.base + 0x5C) != 0:
                        expect_bad += 1
                        examples.append('%s %s: fault %s' % (level, holder, outcome.fault))
    report('shipped: soundSequence entries', tally.bad, tally.cases, 'the soundSequence entries of %s, whole, '
           'vs model; %d call-outs' % (' '.join(holders_seen), tally.calls), tally.examples)
    report('shipped: soundSequence returns', expect_bad, max(expect_n, 1) if expect_n else 0,
           'runs that reached soundSequence: %d; each finished with error word 0 and no fault; %d of them ran '
           'further hooked built-ins after it' % (entered, after), examples)


def call_pushes(image, holder):
    """Whether the entry's activateStore call pushes an argument cell (PUSH.C 4 right
    before the SYSREQ.C is the byte count of a call that pushes one cell; a PUSH.C before
    that, after the previous call's STACK, is the cell)."""
    parsed = scr.parse(image)
    c0 = parsed['code'][0]
    for off, name in call_sites(image, 'activateStore'):
        if name == holder:
            w = struct.unpack_from('<6I', image, c0 + off - 16)
            return w[0] == 0x27                 # PUSH.C value, PUSH.C 4, SYSREQ.C
    return None


def coverage_line(rig):
    parts = []
    for name, (lo, hi) in sorted(BODY_RANGES.items(), key=lambda kv: kv[1][0]):
        hit = sum(1 for pc in rig.pcs if lo <= pc < hi)
        parts.append('%s 0x%x %d/%d' % (name, lo, hit, (hi - lo) // 4))
    print('      executed instructions per body: ' + ', '.join(parts))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--elf', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--cases', type=int, default=40)
    parser.add_argument('--controls', type=int, default=12)
    args = parser.parse_args(argv)
    digest = hashlib.sha256(open(args.elf, 'rb').read()).hexdigest()
    if digest != ELF_SHA256:
        print('SKIP  not the US v2.00 executable (SHA-256 %s)' % digest)
        return 2
    here = os.path.dirname(os.path.abspath(__file__))
    tools = hashlib.sha256()
    for name in ('difftest_level_commands.py', 'ref_level_commands.py', 'ref_natives.py', 'difftest_natives.py'):
        tools.update(open(os.path.join(here, name), 'rb').read())
    print('difftest_level_commands  seed %d  executable SHA-256 matches US v2.00  tools %s'
          % (args.seed, tools.hexdigest()[:16]))
    sys.setrecursionlimit(20000)
    D.OPTIONS['seed'] = args.seed
    rig = make_rig(args.elf)
    rig.checkpoint()
    images = {level: gob_file(args.data, level, 'script.scr') + bytes(256) for level in LEVELS}
    print('--- binding')
    group_binding(rig, images)
    print('--- direct')
    group_direct(rig, args.seed, args.cases, args.controls)
    print('--- shipped')
    group_tormenta(rig, args.data, args.seed, max(args.cases // 2, 6))
    group_islgnome(rig, args.data, args.seed, max(args.cases // 2, 8))
    group_hub(rig, args.data, args.seed, 2)
    group_sound(rig, args.data, args.seed, max(args.cases // 4, 4))
    coverage_line(rig)
    if rig.unknown:
        print('      calls to addresses neither real nor stubs: ' + ', '.join(
            '0x%x x%d' % kv for kv in sorted(rig.unknown.items())))
    passed = sum(1 for _n, ok in RESULTS if ok)
    print('%d properties: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
