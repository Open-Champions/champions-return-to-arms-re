#!/usr/bin/env python3
"""Round 3 save-world probes against SLUS-20973 v2.00 (2026-11-09).

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world_travel.py
       /path/to/SLUS_209.73 --seed 20973

Runs original functions in tools/ee_emu.py on synthetic memory:
  * Creature_loadState 0x116920, a seed-varied cross-check of the stub-free
    t3/research-death-reload probe (difftest_death_reload_creature.py);
  * JumpGate_loadState 0x27d998 with the original light_link2 0x148bc8;
  * save_game 0x218128 checkpoint decisions with the original act table;
  * a multi-level travel sequence through the original save_storeLevelState
    0x21777c, save_writeLevelState 0x218600, save_levelStateStored 0x2182d4,
    save_clearBuffer 0x21f144 and level_loadScriptAndObjects 0x217978.
Every replaced callee is a recording stub listed in STUBS below and printed
on success.  No game bytes are stored; the act table is read from the
executable at run time and only counts and sizes are printed.
"""

import argparse
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: E402,F401 -- tools/dis.py shadows stdlib dis
sys.path.insert(0, HERE)

from ee_emu import EE  # noqa: E402
import ref_save_world as R  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'

CREATURE_LOAD = 0x116920
JUMPGATE_LOAD = 0x27D998
LIGHT_LINK2 = 0x148BC8
SAVE_GAME = 0x218128
SAVE_STORE = 0x21777C
SAVE_WRITE = 0x218600
SAVE_STORED = 0x2182D4
SAVE_CLEAR = 0x21F144
LEVEL_LOAD = 0x217978

G_SAVE_BUF = 0x895580
SAVE_SIZE = 0x4BC78
G_SAVE_DIR = 0x8AB590
G_SAVE_DATA = 0x8AB698
G_SCRATCH = 0x88D480
G_AUTO_SIZE = 0x4044D0
G_LOADED = 0x8E1AD6
G_RANK = 0x4F7108
G_SKIP = 0x4F8B58
G_ACT = 0x88D3D4
G_ACT_COUNT = 0x4F8E10
G_ACT_TABLE = 0x4F8E48
G_LEVEL_NAME = 0x41B721
G_SUBNAME = 0x41B771
G_CARD = 0x88D3A0
G_LEVEL_FLAGS = 0x44FE08
G_BIG_SAVE = 0x4F85C5
G_CLEAR_BLOCK = 0x4F8F2A
G_CLEAR_WORD = 0x4F9234
G_STRTAB = 0x5F8704
G_PLAYERS = 0x4D8AE0
G_RECORDS = 0x4D8AF0
RECORD_SIZE = 0x4C30
G_SAVE_GAME_WORD = 0x4F8F30

ORC_TYPEINFO = 0x3C4658
CREATURE_TYPEINFO = 0x3C2608
ORC_DESCRIPTOR = 0x9083F0
CREATURE_DESCRIPTOR = 0x908130

# Callees replaced by recording stubs, by probe.  Everything else that the
# probed bodies call runs as original code.
STUBS = {
    'creature': {0x14F290: 'obj_stopRunning', 0x1707B0: 'anim_clear',
                 0x170838: 'anim_push', 0x170BC8: 'anim_jumpTopToEnd',
                 0x1A1698: 'handle_clear', 'vtable+0xe8': 'variant hook',
                 'vtable+0xe0': 'death-pose hook'},
    'jumpgate': {0x17365C: 'res_find', 0x170838: 'anim_push',
                 0x14F248: 'obj_runEveryFrame'},
    'save_game': {0x19E5E8: 'task_isRunning', 0x173C84: 'text lookup',
                  0x22233C: 'level display name', 0x1D92A0: 'HUD message',
                  0x221914: 'save_build', 0x1EB5C8: 'game_sendCharacterToLobby'},
    'travel': {0x14E5C8: 'world_saveState', 0x19EE10: 'decal writer',
               0x16865C: 'automap_packExplored', 0x173558: 'level lump',
               0x171DE4: 'lump directory lookup', 0x1ED650: 'script_setCurrent',
               0x1ED694: 'script call', 0x14E808: 'world_loadRecords',
               0x1A00B0: 'decal load', 0x1686C4: 'automap unpack'},
}


def fixture(elf):
    ee = EE(elf)
    ee.record_calls = False
    ee.record_writes = False
    return ee


def cstr(ee, ptr, limit=64):
    return ee.mem.read(ptr & 0xFFFFFFFF, limit).split(b'\0', 1)[0]


def put_str(ee, text):
    ptr = ee.alloc(len(text) + 1)
    ee.mem.write(ptr, text + b'\0')
    return ptr


def check_creature(elf, rng):
    """Creature_loadState 0x116920."""
    alive = dead = 0
    seen = dict(anim=0, orc=0, word312=0, word312_applied=0)
    fractions = (1.0, 0.5, 0.25, 0.125, 0.0, -0.5, -1.0)
    for case in range(48):
        ee = fixture(elf)
        obj = ee.alloc(0x400)
        vt = ee.alloc(0x100)
        code = ee.alloc(0x40)
        variant_fn, pose_fn = code, code + 0x10
        ee.mem.w32(obj + 0x48, vt)
        ee.mem.w16(vt + 0xe8, 0)
        ee.mem.w32(vt + 0xec, variant_fn)
        ee.mem.w16(vt + 0xe0, 0)
        ee.mem.w32(vt + 0xe4, pose_fn)
        orc = bool(case & 1)
        ee.mem.w32(vt + 4, ORC_TYPEINFO if orc else CREATURE_TYPEINFO)

        names = [b'die%d' % i for i in range(rng.randrange(1, 5))]
        clips = ee.alloc(8 * (len(names) + 2))
        clip_ptrs = []
        for index, name in enumerate(names, 1):
            clip_ptrs.append(ee.alloc(16))
            ee.mem.w32(clips + 8 * index, put_str(ee, name))
            ee.mem.w32(clips + 8 * index + 4, clip_ptrs[-1])
        ee.mem.w32(obj + 0x24, clips)
        strtab = ee.alloc(0x40)
        ee.mem.w32(G_STRTAB, strtab)

        fraction = fractions[case % len(fractions)]
        max_hp = float(rng.randrange(8, 400))
        bits = rng.randrange(0x80)
        anim_choice = rng.randrange(3)
        anim_name = None
        handle = -1
        if anim_choice == 1:
            anim_name = rng.choice(names)
            handle = 0x10
            ee.mem.write(strtab + handle, anim_name + b'\0')
        elif anim_choice == 2:
            anim_name = b'missing'
            handle = 0x20
            ee.mem.write(strtab + handle, anim_name + b'\0')
        record = dict(variant=rng.getrandbits(32), hp_fraction=fraction, bits=bits,
                      anim_name=anim_name, word312=rng.randrange(-0x8000, 0x8000))
        flags = rng.getrandbits(32)
        h312 = -1 if rng.random() < 0.3 else rng.randrange(0, 0x7fff)
        before = dict(max_hp=max_hp, a8=rng.getrandbits(64), b231=rng.getrandbits(8),
                      h312=h312, flags=flags, s310=0, s11a=rng.getrandbits(16),
                      s28=rng.getrandbits(8), s232=rng.getrandbits(16),
                      w234=rng.getrandbits(32))
        ee.mem.write(obj + 0x22c, struct.pack('<f', max_hp))
        ee.mem.write(obj + 0xa8, struct.pack('<Q', before['a8']))
        ee.mem.w32(obj + 0xc, flags)
        ee.mem.write(obj + 0x310, struct.pack('<Q', rng.getrandbits(64)))
        ee.mem.write(obj + 0x312, struct.pack('<h', h312))
        before['s310'] = struct.unpack_from('<Q', ee.mem.read(obj + 0x310, 8))[0]
        ee.mem.w8(obj + 0x231, before['b231'])
        ee.mem.w16(obj + 0x11a, before['s11a'])
        ee.mem.w8(obj + 0x28, before['s28'])
        ee.mem.w16(obj + 0x232, before['s232'])
        ee.mem.w32(obj + 0x234, before['w234'])
        data = R.creature_record(record['variant'], fraction, bits, handle, record['word312'])
        buf = ee.alloc(0x40)
        ee.mem.write(buf, data)

        events = []
        ee.stub(variant_fn, function=lambda e: events.append(('variant', e.r[4] & 0xFFFFFFFF)) or 0)
        ee.stub(pose_fn, function=lambda e: events.append(('death_pose', e.r[4] & 0xFFFFFFFF,
                                                           e.r[5] & 0xFFFFFFFF)) or 0)
        ee.stub(0x14F290, function=lambda e: events.append(('stop_running', e.r[4] & 0xFFFFFFFF)) or 0)
        ee.stub(0x1707B0, function=lambda e: events.append(('anim_clear', e.r[4] & 0xFFFFFFFF)) or 0)
        ee.stub(0x170838, function=lambda e: events.append(('anim_push', e.r[4] & 0xFFFFFFFF,
                                                            e.r[5] & 0xFFFFFFFF, e.r[6])) or 0)
        ee.stub(0x170BC8, function=lambda e: events.append(('anim_end', e.r[4] & 0xFFFFFFFF)) or 0)
        ee.stub(0x1A1698, function=lambda e: events.append(('handle_clear', e.r[4] & 0xFFFFFFFF)) or 0)

        # Both type descriptors start zeroed in the image: the getters below
        # construct them lazily (0x3c466c / 0x3b12b8) when the corpse branch runs.
        assert ee.mem.u32(ORC_DESCRIPTOR) == 0 and ee.mem.u32(CREATURE_DESCRIPTOR) == 0
        size = ee.call(CREATURE_LOAD, obj, buf)
        want_size, want, want_events = R.creature_load(record, before, names, orc)
        descriptors_built = ee.mem.u32(CREATURE_DESCRIPTOR) != 0 and (
            not orc or ee.mem.u32(ORC_DESCRIPTOR) != 0)
        assert descriptors_built == (want['hp'] <= 0), (case, descriptors_built)
        assert size == want_size == len(data), (case, size, want_size, len(data))

        # Expand the reference's symbolic events into the addresses recorded.
        expanded = [('variant', obj)]
        for event in want_events[1:]:
            if event == 'stop_running':
                expanded.append(('stop_running', obj))
            elif event == 'anim_clear':
                expanded.append(('anim_clear', obj + 0x114))
            elif isinstance(event, tuple) and event[0] == 'anim_push':
                expanded.append(('anim_push', obj + 0x114, clip_ptrs[event[1] - 1], event[2]))
            elif event == 'anim_end':
                expanded.append(('anim_end', obj + 0x114))
            elif isinstance(event, tuple) and event[0] == 'death_pose':
                expanded.append(('death_pose', obj, 1))
            elif event == 'handle_clear':
                expanded.append(('handle_clear', obj + 0x234))
        assert events == expanded, (case, events, expanded)

        got_hp = struct.unpack('<f', ee.mem.read(obj + 0x228, 4))[0]
        assert got_hp == want['hp'], (case, got_hp, want['hp'])
        assert ee.mem.u32(obj + 0xe8) == record['variant']
        assert struct.unpack('<Q', ee.mem.read(obj + 0xa8, 8))[0] == want['a8'], case
        assert ee.mem.u8(obj + 0x231) == want['b231'], case
        assert ee.mem.u32(obj + 0xc) == want['flags'] & 0xFFFFFFFF, case
        assert ee.mem.u16(obj + 0x232) == want['s232'] & 0xFFFF, case
        assert ee.mem.u16(obj + 0x11a) == want['s11a'] & 0xFFFF, case
        assert ee.mem.u8(obj + 0x28) == want['s28'] & 0xFF, case
        got312 = struct.unpack('<h', ee.mem.read(obj + 0x312, 2))[0]
        assert got312 == want['h312'], (case, got312, want['h312'])
        low310 = ee.mem.u8(obj + 0x310)
        assert low310 == (want['s310'] & 0xFF), case
        assert ee.mem.u8(obj + 0x311) == (before['s310'] >> 8) & 0xFF, case
        assert ee.mem.read(obj + 0x314, 4) == struct.pack('<Q', before['s310'])[4:], case
        assert ee.mem.u32(obj + 0x234) == want.get('w234', before['w234']), case
        seen['anim'] += any(ev[0] == 'anim_push' for ev in events)
        seen['orc'] += want['hp'] <= 0 and orc
        seen['word312'] += bool(bits & 0x40)
        seen['word312_applied'] += any(ev[0] == 'handle_clear' for ev in events)
        if want['hp'] <= 0:
            dead += 1
        else:
            alive += 1
    assert all(seen.values()), seen
    print('PASS Creature_loadState %d cases (%d alive, %d dead; %d death clips, %d dead Orc, '
          '%d with +0x312 word, %d applied)' % (alive + dead, alive, dead, seen['anim'],
                                                seen['orc'], seen['word312'],
                                                seen['word312_applied']))


def check_jumpgate(elf, rng):
    """JumpGate_loadState 0x27d998 with the original light_link2 0x148bc8."""
    checked = 0
    for case in range(12):
        ee = fixture(elf)
        obj = ee.alloc(0x200)
        state = (rng.randrange(1, 256), 0 if case % 3 == 0 else rng.randrange(1, 128))
        buf = ee.alloc(8)
        ee.mem.write(buf, bytes(state))
        inside = case % 2 == 0
        x = float(rng.randrange(-0x2c00, 0x2c00) if inside else rng.choice((-0x3000, 0x3000)))
        y = float(rng.randrange(-0x2c00, 0x2c00))
        ee.mem.write(obj + 0x130, struct.pack('<ff', x, y))
        # Pre-link the node into a synthetic two-entry list to test the unlink.
        head = ee.alloc(8)
        other = ee.alloc(16)
        node = obj + 0x100
        ee.mem.w32(head, node)
        ee.mem.w32(node, other)
        ee.mem.w32(node + 4, head)
        ee.mem.w32(other + 4, node)
        cell = R.light_grid_cell(x, y)
        old_cell_head = ee.mem.u32(cell)
        clip = ee.alloc(16)
        events = []
        ee.stub(0x17365C, function=lambda e: events.append(('res_find', e.r[4] & 0xFFFFFFFF,
                                                            cstr(e, e.r[5]))) or clip)
        ee.stub(0x170838, function=lambda e: events.append(('anim_push', e.r[4] & 0xFFFFFFFF,
                                                            e.r[5] & 0xFFFFFFFF, e.r[6])) or 0)
        ee.stub(0x14F248, function=lambda e: events.append(('run_every_frame', e.r[4] & 0xFFFFFFFF)) or 0)
        assert ee.call(JUMPGATE_LOAD, obj, buf) == 2
        assert (ee.mem.u8(obj + 0x4d), ee.mem.u8(obj + 0x4e)) == state
        want = []
        if state[1]:
            want = [('res_find', obj + 0x90, b'jumpgate_idle.anm'),
                    ('anim_push', obj + 0xd8, clip, 3)]
            assert ee.mem.u32(head) == other and ee.mem.u32(other + 4) == head
            assert ee.mem.u32(cell) == node and ee.mem.u32(node + 4) == cell
            assert ee.mem.u32(node) == old_cell_head
        else:
            assert ee.mem.u32(head) == node and ee.mem.u32(node + 4) == head
        want.append(('run_every_frame', obj))
        assert events == want, (case, events, want)
        checked += 1
    print('PASS JumpGate_loadState %d cases (light_link2 original)' % checked)


def act_rows(ee):
    acts = []
    for act in range(13):
        count = ee.mem.u32(G_ACT_COUNT + 4 * act)
        table = ee.mem.u32(G_ACT_TABLE + 4 * act)
        acts.append([(cstr(ee, ee.mem.u32(table + 8 * i)), ee.mem.u16(table + 8 * i + 4))
                     for i in range(count)])
    return acts


def set_level(ee, base, sub=b''):
    ee.mem.write(G_LEVEL_NAME, base + b'\0')
    ee.mem.write(G_SUBNAME, sub + b'\0')


def check_save_game(elf, rng):
    """save_game 0x218128: which checkpoints show a message and which build."""
    checked = 0
    tally = dict(build=0, silent_build=0, message_only=0, nothing=0)
    cases = []
    for living in (True, False):
        for act, base, sub, menu, stored, quiet in (
                (0, b'hub', b'', False, False, 0), (0, b'hub', b'', False, True, 0),
                (0, b'hub', b'', False, True, 1), (0, b'hub', b'west', False, False, 0),
                (0, b'blood1', b'', False, False, 0), (0, b'blood1', b'', False, False, 1),
                (-1, b'blood1', b'', False, False, 0), (0, b'blood1', b'', True, False, 0),
                (0, b'zzz', b'', False, False, 0), (2, b'hub', b'', False, False, 0)):
            cases.append((living, act, base, sub, menu, stored, quiet))
    dead_kinds = ('hp', 'flag', 'null')
    for index, (living, act, base, sub, menu, stored, quiet) in enumerate(cases):
        ee = fixture(elf)
        acts = act_rows(ee)
        ee.mem.write(G_SAVE_DIR, bytes(11 * 0x18))
        ee.mem.w32(G_ACT, act & 0xFFFFFFFF)
        set_level(ee, base, sub)
        qualified = base + (b'_' + sub if sub else b'')
        if stored:
            ee.mem.write(G_SAVE_DIR, qualified + b'\0')
            ee.mem.w32(G_SAVE_DIR + 0x14, 0x3a98)
        players = rng.randrange(1, 5)
        ee.mem.w32(G_PLAYERS, players)
        living_slot = rng.randrange(players)
        for slot in range(players):
            rec = G_RECORDS + slot * RECORD_SIZE
            objp = ee.alloc(0x40)
            hp, flags, ptr = 0.0, 0, objp
            if living and slot == living_slot:
                hp = 10.0
            else:
                kind = dead_kinds[(index + slot) % 3]
                if kind == 'flag':
                    hp, flags = 10.0, 0x8
                elif kind == 'null':
                    hp, ptr = 10.0, 0
            ee.mem.write(rec + 0xac, struct.pack('<f', hp))
            ee.mem.w32(rec + 0x43d8, ptr)
            ee.mem.w32(objp + 0xc, flags)
        ee.mem.w32(G_SAVE_GAME_WORD, 0xA5A5A5A5)
        events = []
        text, title = ee.alloc(16), ee.alloc(16)
        ee.stub(0x19E5E8, function=lambda e: events.append(('task_isRunning', cstr(e, e.r[4])))
                or int(menu))
        ee.stub(0x173C84, function=lambda e: events.append(('text', cstr(e, e.r[4]))) or text)
        ee.stub(0x22233C, function=lambda e: events.append(('title', cstr(e, e.r[4]))) or title)
        ee.stub(0x1D92A0, function=lambda e: events.append(('message', e.r[4] & 0xFFFFFFFF, e.r[5],
                                                            e.r[6] & 0xFFFFFFFF, e.r[7])) or 0)
        ee.stub(0x221914, function=lambda e: events.append(('save_build', e.r[4], e.r[5])) or 0)
        ee.stub(0x1EB5C8, function=lambda e: events.append(('to_lobby', e.r[4] & 0xFFFFFFFF)) or 0)
        slot_arg = rng.randrange(4)
        ee.call(SAVE_GAME, slot_arg, quiet)

        found = act != -1 and any(qualified.startswith(row[0]) for rows in acts for row in rows)
        row0 = found and qualified == acts[act if act >= 0 else 0][0][0]
        message, build = R.save_game_path(living, act, menu, found, row0, stored, quiet)
        want = []
        if living and act != -1:
            want.append(('task_isRunning', b'missionmenurun'))
        if message == 'CheckPoint':
            want += [('text', b'CheckPoint'), ('message', text, 0xb4, 0xFFFFFFFF, 0)]
        elif message == 'level':
            want += [('title', qualified), ('message', title, 0xb4, 0xFFFFFFFF, 0)]
        if build:
            want += [('save_build', slot_arg, 0), ('to_lobby', 0xFFFFFFFF)]
        assert events == want, (index, events, want)
        assert ee.mem.u32(G_SAVE_GAME_WORD) == (0 if build else 0xA5A5A5A5), index
        tally['build' if build and message else 'silent_build' if build else
              'message_only' if message else 'nothing'] += 1
        checked += 1
    assert all(tally.values()), tally
    print('PASS save_game %d checkpoint cases (%s)' % (
        checked, ', '.join('%s %d' % kv for kv in tally.items())))


class Travel:
    """Original departure store, directory lookup, clear and reload in one memory."""

    def __init__(self, elf, rng):
        self.ee = ee = fixture(elf)
        self.rng = rng
        ee.mem.write(G_SAVE_BUF, bytes(SAVE_SIZE))
        ee.mem.w32(G_AUTO_SIZE, R.AUTOMAP_SIZE)
        ee.mem.w32(G_CARD, 0xFFFFFFFF)
        ee.mem.w32(G_LEVEL_FLAGS, 0)
        ee.mem.w8(G_BIG_SAVE, 0)
        ee.mem.w8(G_CLEAR_BLOCK, 0)
        self.writes = []
        self.loads = []
        self.pending = None
        ee.stub(0x14E5C8, function=self.world_fn)
        ee.stub(0x19EE10, function=self.decal_fn)
        ee.stub(0x16865C, function=self.map_fn)
        lump, entry, ob = ee.alloc(16), ee.alloc(16), ee.alloc(16)
        ee.mem.w32(entry + 4, ob)
        ee.stub(0x173558, ret=lump)
        ee.stub(0x171DE4, function=lambda e: entry if cstr(e, e.r[5]) == b'objects.ob' else 0)
        ee.stub(0x1ED650, function=lambda e: self.loads.append('script_set_current') or 0)
        ee.stub(0x1ED694, function=lambda e: self.loads.append(cstr(e, e.r[4]).decode()) or 0)
        ee.stub(0x14E808, function=self.records_fn)
        ee.stub(0x1A00B0, function=lambda e: self.loads.append('decal_load') or 0)
        ee.stub(0x1686C4, function=self.unpack_fn)

    def body(self, tag):
        rng = self.rng
        world = bytes([tag]) + bytes(rng.getrandbits(8) for _ in range(rng.randrange(7, 48, 8)))
        decals = bytes([tag ^ 0xFF]) + bytes(rng.getrandbits(8) for _ in range(7))
        explored = bytes([tag]) * R.AUTOMAP_SIZE
        return world, decals, explored

    def world_fn(self, e):
        world = self.pending[0]
        e.mem.write(e.r[4], world)
        self.writes.append(('world', e.r[4] & 0xFFFFFFFF, e.r[5]))
        return len(world)

    def decal_fn(self, e):
        e.mem.write(e.r[4], self.pending[1])
        return len(self.pending[1])

    def map_fn(self, e):
        e.mem.write(e.r[4], self.pending[2])
        return 0

    def records_fn(self, e):
        blob = e.r[4] & 0xFFFFFFFF
        if blob == G_SCRATCH:
            self.loads.append('saved_objects')
            self.scratch_world = e.mem.read(G_SCRATCH, len(self.expect_world))
        else:
            self.loads.append('level_objects_filtered' if e.r[5] else 'level_objects_all')
        return 8

    def unpack_fn(self, e):
        self.loads.append('automap_unpack')
        self.unpacked = e.mem.read(e.r[4] & 0xFFFFFFFF, R.AUTOMAP_SIZE)
        return 0

    def store(self, name, tag):
        ee = self.ee
        self.pending = self.body(tag)
        before = len(self.writes)
        ee.call(SAVE_STORE, put_str(ee, name))
        return self.pending if len(self.writes) > before else None

    def stored(self, base, sub=b''):
        set_level(self.ee, base, sub)
        return self.ee.call(SAVE_STORED)

    def directory(self):
        out = []
        for slot in range(11):
            entry = G_SAVE_DIR + slot * 0x18
            out.append((cstr(self.ee, entry, 0x14), self.ee.mem.u32(entry + 0x14)))
        return out

    def offset(self, slot):
        return sum(size for _, size in self.directory()[:slot])

    def load(self, name, expect=None):
        ee = self.ee
        self.loads = []
        self.expect_world = expect[0] if expect else b''
        ee.mem.w8(G_LOADED, 0)
        ee.mem.w8(G_SKIP, 0)
        ee.call(LEVEL_LOAD, put_str(ee, name), put_str(ee, name))
        want = R.reload_events(expect is not None)
        assert self.loads == want, (name, self.loads, want)
        if expect:
            assert self.scratch_world == expect[0], name
            assert ee.mem.read(G_SCRATCH + len(expect[0]), len(expect[1])) == expect[1], name
            assert self.unpacked == expect[2], name

    def image(self):
        return self.ee.mem.read(G_SAVE_BUF, SAVE_SIZE)


def check_travel(elf, rng):
    """Leave, revisit, suppress, act change: what one level remembers."""
    t = Travel(elf, rng)
    ee = t.ee
    acts = act_rows(ee)
    ee.mem.w32(G_ACT, 2)
    rows = dict(acts[2])
    a, b, c = acts[2][1][0], acts[2][2][0], acts[2][3][0]
    steps = 0

    hub1 = t.store(b'hub', 1)
    lvl_a = t.store(a, 2)
    assert t.directory()[:3] == [(b'hub', rows[b'hub']), (a, rows[a]), (b'', 0)]
    a_at = G_SAVE_DATA + rows[b'hub']
    assert ee.mem.read(a_at, 8 + len(lvl_a[0])) == struct.pack('<I', len(lvl_a[0])) + bytes(4) + lvl_a[0]
    steps += 2

    t.load(b'hub', hub1)                          # revisit uses the departure body
    hub2 = t.store(b'hub', 3)                     # leave again: slot 0 rewritten
    assert t.directory()[0] == (b'hub', rows[b'hub'])
    assert ee.mem.read(a_at, 8 + len(lvl_a[0]))[8:] == lvl_a[0]
    t.load(a, lvl_a)
    t.load(b'hub', hub2)
    steps += 4

    assert t.stored(b) == 0
    t.load(b, None)                               # never left: every objects.ob record
    steps += 2

    for word, flag in ((4, 0), (0xFFFFFFFF, 0x800)):
        ee.mem.w32(G_CARD, word)
        ee.mem.w32(G_LEVEL_FLAGS, flag)
        before = t.image()
        assert t.store(c, 9) is None and t.store(b'hub', 9) is None
        assert t.image() == before
        steps += 2
    ee.mem.w32(G_CARD, 0xFFFFFFFF)
    ee.mem.w32(G_LEVEL_FLAGS, 0)

    west = t.store(b'hub_west', 4)               # any hub* name takes row 0's size
    assert t.directory()[2] == (b'hub_west', rows[b'hub'])
    assert t.stored(b'hub', b'west') == 1 and t.stored(b'hub') == 1 and t.stored(a) == 1
    t.load(b'hub_west', west)
    steps += 3

    # Act change: mainloop_loadRequestedWorld calls save_clearBuffer(0) at
    # 0x320fcc (t3/research-exits-r3).  Here the original clear runs alone.
    hub_body = ee.mem.read(G_SAVE_DATA, rows[b'hub'])
    want_dir = R.clear_keep_first(t.directory(), acts[0][0][1])
    ee.mem.w32(G_CLEAR_WORD, 0x12345678)
    ee.call(SAVE_CLEAR, 0)
    assert t.directory()[:2] == want_dir + [(b'', 0)], t.directory()[:2]
    assert ee.mem.read(G_SAVE_DATA, rows[b'hub']) == hub_body
    assert ee.mem.read(G_SAVE_DATA + rows[b'hub'], 64) == bytes(64)
    assert ee.mem.u32(G_CLEAR_WORD) == 0
    assert t.stored(b'hub') == 1
    assert t.stored(a) == 0 and t.stored(b'hub', b'west') == 0
    t.load(b'hub', hub2)
    t.load(a, None)
    steps += 3

    # The block byte keeps everything (t3/research-saves clear.blocked).
    ee.mem.w8(G_CLEAR_BLOCK, 1)
    before = t.image()
    ee.call(SAVE_CLEAR, 0)
    assert t.image() == before
    ee.mem.w8(G_CLEAR_BLOCK, 0)
    steps += 1

    # A non-hub first entry survives too, re-sized to act 0 row 0.
    t2 = Travel(elf, rng)
    t2.ee.mem.w32(G_ACT, 0)
    first, second = acts[0][1][0], acts[0][2][0]
    body1 = t2.store(first, 5)
    t2.store(b'hub', 6)
    t2.store(second, 7)
    t2.ee.call(SAVE_CLEAR, 0)
    assert t2.directory()[:2] == [(first, acts[0][0][1]), (b'', 0)]
    assert t2.stored(first) == 1 and t2.stored(b'hub') == 0
    t2.load(first, body1)
    steps += 2

    capacity = SAVE_SIZE - 0x16118
    sums = [sum(size for _, size in rows_) for rows_ in acts]
    over = [i for i, total in enumerate(sums) if total > capacity]
    print('PASS travel sequence %d steps; act rows %d..%d, row 0 hub %d bytes in every act, '
          'largest act total %d of %d, acts over capacity %s' %
          (steps, min(map(len, acts)), max(map(len, acts)), acts[0][0][1], max(sums),
           capacity, over or 'none'))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == SHA256, 'wrong executable revision'
    rng = random.Random(args.seed)
    check_creature(args.elf, rng)
    check_jumpgate(args.elf, rng)
    check_save_game(args.elf, rng)
    check_travel(args.elf, rng)
    for probe, stubs in STUBS.items():
        print('STUBS %s: %s' % (probe, ', '.join(
            ('0x%x %s' % (k, v)) if isinstance(k, int) else '%s %s' % (k, v)
            for k, v in stubs.items())))


if __name__ == '__main__':
    main()
