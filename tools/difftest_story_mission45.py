#!/usr/bin/env python3
"""Mission 4 and 5 story beats against the original script machine.

The menu requests that write wat1 and tormenta stay in difftest_story_beats.py.
Mission 3's grant, and the hub entries that make mission 4 available, stay in
difftest_story_mission3.py. This file runs the water and tormenta entries.
No dialogue text is written. Text keys (quest titles and bodies, help ids)
are read from the script call sites named in KEY_SITES, never written here.

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; \
  sys.path.insert(0,"tools"); \
  sys.argv=["difftest_story_mission45.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA"]; \
  runpy.run_path("tools/difftest_story_mission45.py", run_name="__main__")'
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EmuError, MemoryFault  # noqa: E402
from gob import gob_entries, lmp_entries  # noqa: E402
import difftest_natives as N  # noqa: E402
import ref_story_route as R  # noqa: E402
import scr  # noqa: E402

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYERS = 0x4D8AF0
MISSION = 0x4BBF
QUEST = 0x41D0
QUEST_COUNT = 0x43D0
REC = 0x4C30
EVIL = 0x4C1A
SENTINEL = 0xA0
FILL = 0x5A
MISSION_BYTES = 52
G_PAUSED = 0x41B4F4
G_GATE = 0x500AE8
G_CUT = 0x44FCD0
SHARD_TICKS = 25
# research-quest-log names.tsv: builtin starts. The next builtin after
# addParticleOnObject starts at 0x146f58.
ADD_PARTICLE = 0x146E20
ADD_PARTICLE_END = 0x146F58
CHANGE_SWOOP = 0x1438B0
ACTIVATE_STORE = 0x144010
SHARD_LEVELS = ('wate2a', 'wate2b', 'wate2c', 'watg2a', 'watg2b', 'watg2c')
# Script call sites that carry each text key: (level, offset, argument index).
KEY_SITES = {
    'good_title': ('wat1', 0x2E0, 0),
    'good_body': ('wat1', 0x2E0, 1),
    'evil_title': ('wat1', 0x2A4, 0),
    'evil_body': ('wat1', 0x2A4, 1),
    'water1_help_title': ('water1', 0x158, 0),
    'water1_help_body': ('water1', 0x158, 1),
    'gol_title': ('tormenta', 0x748, 0),
    'gol_body': ('tormenta', 0x748, 1),
    'endtor_title': ('tormenta', 0x1E20, 0),
    'hub_title': ('hub', 0x2410, 0),
    'hub_body': ('hub', 0x2410, 1),
}
# Per shard level: the shardCheck counter, the variable its playerHasItem
# return is compared with, the addHelpMessage site, and the watg removeQuest.
SHARD_VARS = {
    'wate2a': (0xA0, 0xA4, 0x1474, None),
    'wate2b': (0x84, 0x88, 0x13FC, None),
    'wate2c': (0x84, 0x88, 0x13FC, None),
    'watg2a': (0x80, 0x84, 0xD88, 0xDE8),
    'watg2b': (0x80, 0x84, 0xD88, 0xDE8),
    'watg2c': (0x80, 0x84, 0xD88, 0xDE8),
}
# Code offset in each level's start that stores into the compared variable.
SHARD_BASE_STORE = {
    'wate2a': 0x55C, 'wate2b': 0x4E4, 'wate2c': 0x4E4,
    'watg2a': 0x398, 'watg2b': 0x398, 'watg2c': 0x398,
}


class Quiet:
    def __init__(self):
        self.shells = 0

    def answer(self, name, args):
        if name == 'inventory_findItemBySubstring':
            return (-1, 0)
        if name == 'inventory_countItemByName':
            return self.shells
        return 0


def lump_map(path):
    data = open(path, 'rb').read()
    stem = os.path.basename(path).lower().replace('.gob', '.lmp')
    found = {}
    for name, lo, size in gob_entries(data):
        if name.lower() != stem:
            continue
        blob = data[lo:lo + size]
        for inner, off, inner_size in lmp_entries(blob):
            found[inner.lower()] = blob[off:off + inner_size]
    if 'script.scr' not in found:
        raise AssertionError(path)
    return found


def load_levels(data):
    names = (
        'wat1', 'water1', 'wate2a', 'wate2b', 'wate2c', 'watg2a', 'watg2b', 'watg2c',
        'tormenta', 'tormentb', 'torment2', 'torment3', 'hub', 'hub2',
    )
    return {name: lump_map(os.path.join(data, name.upper() + '.GOB')) for name in names}


def show_imm(pool, publics, value):
    if value == 0 and pool.get(0) in publics:
        return pool[0]
    if value >= 8 and value in pool:
        return pool[value]
    return value if value < 0x80000000 else value - 0x100000000


def calls_in(image):
    parsed = scr.parse(image)
    pool = dict(scr.strings(image, *parsed['strings']))
    natives = [name for _, name in parsed['externals']]
    entries = sorted(parsed['internals'])
    publics = {name: off for off, name in entries}
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    found, pending, i = [], [], 0
    while i < len(words):
        op = words[i]
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            raw = pending[:-1][::-1] if pending else []
            args = tuple(show_imm(pool, publics, value) if kind == 'imm' else None
                         for kind, value in raw)
            found.append((i * 4, natives[words[i + 1]], args))
            pending = []
            i += 2
            continue
        if op == 0x27:
            pending.append(('imm', words[i + 1]))
            i += 2
            continue
        if op == 0x28:
            pending.append(('var', words[i + 1]))
            i += 2
            continue
        if op in (0x24, 0x25):
            pending.append(('reg', 0))
            i += 1
            continue
        if op == 0x2C:
            pending = []
            i += 2
            continue
        if pending:
            pending = []
        if op in scr.OPS:
            _text, n = scr.OPS[op]
            i += 1 + n
        else:
            i += 1 if op in scr.NO_OPERAND else 2
    return publics, found, pool


def compare_imm(image, entry, value):
    """Code offset of `A == value` inside one entry, or None."""
    parsed = scr.parse(image)
    entries = sorted(parsed['internals'])
    publics = {name: off for off, name in entries}
    start = publics[entry]
    later = [off for off, _name in entries if off > start]
    end = min(later) if later else (parsed['code'][1] - parsed['code'][0])
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    i, limit = start // 4, end // 4
    while i < limit:
        op = words[i]
        if op == 0x69 and words[i + 1] == value:
            return i * 4
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            i += 2
            continue
        if op in scr.OPS:
            _text, n = scr.OPS[op]
            i += 1 + n
        else:
            i += 1 if op in scr.NO_OPERAND else 2
    return None


def arg_at(found, site, index):
    for off, _name, args in found:
        if off == site:
            return args[index]
    raise AssertionError(hex(site))


def entry_span(image, entry):
    parsed = scr.parse(image)
    entries = sorted(parsed['internals'])
    start = {name: off for off, name in entries}[entry]
    later = [off for off, _name in entries if off > start]
    return start, (min(later) if later else (parsed['code'][1] - parsed['code'][0]))


def calls_of(image, entry):
    start, end = entry_span(image, entry)
    _publics, found, _pool = calls_in(image)
    return [(off, name, args) for off, name, args in found if start <= off < end]


def var_writes(image, offset):
    """Code offsets of direct stores to script variable `offset`."""
    parsed = scr.parse(image)
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    found, i = [], 0
    while i < len(words):
        op = words[i]
        if op in (0x0F, 0x5B, 0x6D, 0x72) and words[i + 1] == offset:
            found.append(i * 4)
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            i += 2
            continue
        if op in scr.OPS:
            _text, n = scr.OPS[op]
            i += 1 + n
        else:
            i += 1 if op in scr.NO_OPERAND else 2
    return found


def data_addr(rig, image, offset):
    """Emulator address of script variable `offset` (data-relative)."""
    dat, = struct.unpack_from('<i', image, 0x60 + 0x10)
    return rig.base + 0x60 + dat + offset


def text_keys(levels):
    keys = {}
    for key, (level, site, index) in KEY_SITES.items():
        _publics, found, _pool = calls_in(levels[level]['script.scr'])
        value = arg_at(found, site, index)
        require(isinstance(value, str) and value, (key, level, hex(site)))
        keys[key] = value
    for level in SHARD_LEVELS:
        _publics, found, _pool = calls_in(levels[level]['script.scr'])
        help_site = SHARD_VARS[level][2]
        for index, key in ((0, 'shard_help_title'), (1, 'shard_help_body')):
            value = arg_at(found, help_site, index)
            require(keys.setdefault(key, value) == value, (level, key))
    require(len(set(keys.values())) == len(keys), 'text keys are not distinct')
    require(len(keys['endtor_title']) == 17, len(keys['endtor_title']))
    return keys


def ident(text):
    if not text or len(text) > 32:
        return ''
    if all(c.isalnum() or c in '._' for c in text):
        return text
    return ''


def dbin_rows(blob):
    count = blob[0]
    rows = []
    for node in range(count):
        row = blob[node * 0x448:(node + 1) * 0x448]
        choices, = struct.unpack_from('<i', row, 0x54)
        choice_rows = []
        for i in range(choices):
            off = 0x58 + i * 0x54
            choice_rows.append((
                ident(row[off + 0x10:off + 0x30].split(b'\0')[0].decode('latin1')),
                ident(row[off + 0x30:off + 0x50].split(b'\0')[0].decode('latin1')),
                struct.unpack_from('<i', row, off + 0x50)[0],
            ))
        rows.append((ident(row[1:0x21].split(b'\0')[0].decode('latin1')), choice_rows))
    return rows


def prepare(rig, image, seed, shells=0, evil=0):
    error, bound = rig.place(image + bytes(256))
    if (error, bound) != (0, 0):
        raise AssertionError((error, bound))
    rig.responder.shells = shells
    mem = rig.emu.mem
    # Recorded before the anti-leak write. check_image_words reads the ELF
    # values; later prepares write 0 so a paused case cannot leak.
    rig.image_pause = (mem.u32(G_PAUSED), mem.u32(G_GATE), mem.u32(G_CUT))
    mem.w32(G_PAUSED, 0)
    mem.w32(G_GATE, 0)
    mem.w32(G_CUT, 0)
    mem.w32(N.N.G_NUM_PLAYERS, 1)
    mem.w32(N.N.G_DIFFICULTY, 0)
    mem.w32(N.N.G_RAND_SEED, seed)
    mem.w8(N.N.G_NETWORK_MODE, 0)
    mem.w32(N.N.G_ACTIVE_PLAYER, 0)
    mem.w32(N.N.G_SELECTED_OBJ, 0)
    mem.write(N.O.G_NAME_KEYS, bytes(512 * 4))
    mem.write(N.O.G_NAME_OBJS, bytes(512 * 4))
    mem.write(N.N.G_QUEST_VARS, bytes(0x2000))
    mem.write(N.N.G_POST_ACTION, bytes(0x80))
    mem.write(N.N.G_PENDING_LEVEL, b'PENDING-SENTINEL\0')
    mem.w8(N.N.G_PENDING_ORIENT, 0x5A)
    mem.write(N.N.G_ENTRANCE_NAME, b'ENTRANCE-SENTINEL\0')
    mem.w32(N.N.G_DEFER_COUNT, 0)
    mem.w32(N.N.G_DEFER_QUEUED, 0)
    mem.w32(N.N.G_DEFER_FLIP, 0)
    for slot in range(4):
        base = PLAYERS + slot * REC
        mem.write(base + MISSION, bytes([SENTINEL]) * MISSION_BYTES)
        mem.write(base + QUEST, bytes([FILL]) * (8 * 0x40))
        mem.w32(base + QUEST_COUNT, 0 if slot == 0 else 0x5A5A5A5A)
        mem.w8(base + EVIL, evil)
    return mem


def plant_var(rig, name, value):
    pointer = rig.emu.alloc(64)
    rig.emu.mem.write(pointer, name.encode('ascii') + b'\0')
    rig.call(0x1ED854, pointer, value)


def plant_quest(rig, title, body):
    first = rig.emu.alloc(96)
    second = rig.emu.alloc(96)
    rig.emu.mem.write(first, title.encode('latin1') + b'\0')
    rig.emu.mem.write(second, body.encode('latin1') + b'\0')
    rig.call(0x1D386C, first, second)


def clear_defer(mem):
    mem.w32(N.N.G_DEFER_COUNT, 0)
    mem.w32(N.N.G_DEFER_QUEUED, 0)


def run_entry(rig, name):
    pointer = rig.emu.alloc(64)
    rig.emu.mem.write(pointer, name.encode('ascii') + b'\0')
    rig.calls = []
    rig.emu.calls.clear()
    rig.emu.writes.clear()
    rig.last_error = None
    try:
        return N.s32(rig.call(N.A['script_runByName'], pointer, max_steps=4000000)), ''
    except EmuError as exc:
        rig.last_error = exc
        return None, str(exc)


def stubs(rig):
    return [name for name, _args in rig.calls]


def variables(mem):
    found = []
    where = N.N.G_QUEST_VARS
    while mem.u8(where) != 0 and len(found) < 24:
        name = mem.cstr(where, 64)
        found.append((name, mem.s8(where + len(name) + 1)))
        where += len(name) + 2
    return found


def mission(mem, slot, index):
    return mem.u8(PLAYERS + slot * REC + MISSION + index)


def require(cond, detail):
    if not cond:
        raise AssertionError(detail)


def var_addr(mem, name):
    where = N.N.G_QUEST_VARS
    want = name.lower()
    while mem.u8(where) != 0:
        got = mem.cstr(where, 64)
        if got == want:
            return where + len(got) + 1
        where += len(got) + 2
    return None


def require_stored(rig, mem, name, value):
    """The value byte was stored by this entry. A zero fill is not that store."""
    addr = var_addr(mem, name)
    require(addr is not None, name)
    require(mem.s8(addr) == value, (name, mem.s8(addr), value))
    require(any(wrote == addr and size == 1 and got == (value & 0xFF)
                for _pc, wrote, size, got in rig.emu.writes),
            (name, value))


def missions_held(mem):
    return all(mission(mem, slot, index) == SENTINEL
               for slot in range(4) for index in (4, 5, 6))


def plant_mission_vars(rig, mem, names):
    for name, _expected in names:
        plant_var(rig, name, 0x5A)
        require(dict(variables(mem))[name.lower()] == 0x5A, name)


CUT_EMPTY_LUMP = b'.lmp'


def cut_calls(name):
    entry = name.encode('ascii') + b'.cut'
    return [
        ('res_find', (CUT_EMPTY_LUMP, entry)),
        ('cut_start', (0, entry)),
    ]


SHARD_COUNT_CALL = ('inventory_countItemByName', (b'shardofwater', 0))
COMPLETION_SOUND_CALLS = [
    ('res_find', (b'fx.lmp', b'quest_complete.anm')),
    ('sound_playOnObject', (0, 0, 1065353216)),
    ('sound_setPlaysWhileFrozen', (0,)),
]


def help_calls(title, body):
    return [
        ('text_lookup', (title.encode('latin1'),)),
        ('text_lookup', (body.encode('latin1'),)),
        ('hud_showHelpMessage', (0xFFFFFFFF, 0, 0)),
    ]


def shard_grant_calls(keys):
    return ([SHARD_COUNT_CALL] + help_calls(keys['shard_help_title'], keys['shard_help_body'])
            + COMPLETION_SOUND_CALLS)


def bytes_are(mem, index, values):
    return [mission(mem, slot, index) for slot in range(4)] == list(values)


def others_clear(mem, index):
    return all(mission(mem, slot, other) == SENTINEL
               for slot in range(4) for other in (4, 5, 6) if other != index)


def defer_name(mem):
    queued = mem.s32(N.N.G_DEFER_QUEUED)
    if queued <= 0:
        return ''
    half = (mem.u32(N.N.G_DEFER_FLIP) & 1) ^ 1
    return mem.cstr(N.N.G_DEFER_NAMES + half * 64 * 0x50, 32)


def check_wat_start(rig, image, seed, keys):
    checks = 0
    for evil, title, body in (
            (0, keys['good_title'], keys['good_body']),
            (1, keys['evil_title'], keys['evil_body'])):
        mem = prepare(rig, image, seed, evil=evil)
        plant_mission_vars(rig, mem, (('startedMission4', 1), ('currentMission', 4)))
        require(run_entry(rig, 'start')[0] == 0, 'wat1 start')
        require(bytes_are(mem, 4, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
                'wat1 available')
        require(others_clear(mem, 4), 'wat1 other missions')
        require_stored(rig, mem, 'startedmission4', 1)
        require_stored(rig, mem, 'currentmission', 4)
        # getv of a missing sawWat1 appends 0. The value byte is that store.
        require_stored(rig, mem, 'sawwat1', 0)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'one quest')
        require(mem.cstr(PLAYERS + QUEST, 32) == title, 'quest title')
        require(mem.cstr(PLAYERS + QUEST + 0x20, 32) == body, 'quest body')
        require(mem.u32(PLAYERS + REC + QUEST_COUNT) == 0x5A5A5A5A, 'other count')
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'post')
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'pending')
        require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
        checks += 1
    mem = prepare(rig, image, seed)
    require(mem.cstr(N.N.G_LEVEL_NAME, 16) == '', 'level name')
    run_entry(rig, 'start')
    rig.calls = []
    rig.emu.calls.clear()
    rig.emu.writes.clear()
    require(N.s32(rig.call(N.A['script_runPostAction'], max_steps=4000000)) == 0, 'post')
    require(rig.calls == cut_calls('wat1'), rig.calls)
    require_stored(rig, mem, 'sawwat1', 1)
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'post cleared')
    checks += 1
    mem = prepare(rig, image, seed)
    plant_mission_vars(rig, mem, (('startedMission4', 1), ('currentMission', 4)))
    plant_var(rig, 'sawWat1', 1)
    require(run_entry(rig, 'start')[0] == 0, 'repeat start')
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'repeat posted')
    require_stored(rig, mem, 'startedmission4', 1)
    require(mission(mem, 0, 4) == R.available_byte(SENTINEL, 1), 'repeat available')
    checks += 1
    # waterIntro cuts whether sawWat1 is absent, 0x5A, or already 1.
    # start is what withholds the post. res_find returns 0.
    for planted in (None, 0x5A, 1):
        mem = prepare(rig, image, seed)
        if planted is not None:
            plant_var(rig, 'sawWat1', planted)
        require(run_entry(rig, 'absorb')[0] == 0, 'absorb')
        require(rig.calls == cut_calls('wat1'), rig.calls)
        require_stored(rig, mem, 'sawwat1', 1)
        checks += 1
    return checks


def check_keys_and_travel(rig, levels, seed):
    image = levels['wat1']['script.scr']
    checks = 0
    for evil, good_key, evil_key in ((0, 1, 0), (1, 0, 1)):
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'return6198')[0] == good_key, ('good key', evil))
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'good key pending')
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'return10c8')[0] == evil_key, ('evil key', evil))
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'evil key pending')
        checks += 1
    routes = (
        ('newWorld57c0', 'wate2c'),
        ('newWorld9711', 'wate2b'),
        ('newWorld7517', 'wate2a'),
        ('newWorldced', 'watg2c'),
        ('newWorldf0d', 'watg2a'),
        ('newWorldd7df', 'watg2b'),
    )
    for entry, level in routes:
        mem = prepare(rig, image, seed)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0x5A, entry)
        require(missions_held(mem), entry)
        require(run_entry(rig, entry)[0] == 0, entry)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == level, (entry, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', entry)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, entry)
        require(missions_held(mem), entry + ' missions')
        # The stub returns 0, so the call does not close a menu.
        require(rig.calls == [('net_closeLocalMenus', (0,))], rig.calls)
        checks += 1
    for level in ('wate2a', 'wate2b', 'wate2c', 'watg2a', 'watg2b', 'watg2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0x5A, level)
        require(missions_held(mem), level)
        require(run_entry(rig, 'newWorlde6b4')[0] == 0, level)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'wat1', level)
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', level)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, level)
        require(missions_held(mem), level + ' missions')
        require(rig.calls == [('net_closeLocalMenus', (0,))], rig.calls)
        checks += 1
    return checks


def check_water1(rig, image, seed, keys):
    mem = prepare(rig, image, seed)
    plant_mission_vars(rig, mem, (('startedMission4', 1), ('currentMission', 4)))
    require(run_entry(rig, 'start')[0] == 0, 'water1 start')
    require(bytes_are(mem, 4, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
            'water1 available')
    require(others_clear(mem, 4), 'water1 missions')
    require_stored(rig, mem, 'startedmission4', 1)
    require_stored(rig, mem, 'currentmission', 4)
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'water1 quest')
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'water1 post')
    require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'water1 pending')
    publics, _found, pool = calls_in(image)
    require(pool.get(0) == 'steppedOnTrigger' and publics['callScri7351'] == 0, 'wrapper')
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'callScri7351')[0] == 0, 'water1 trigger')
    done = R.complete_byte(SENTINEL, -1)
    require(done == 0xA2, hex(done))
    require(bytes_are(mem, 4, (done, done, done, done)), 'water1 grant')
    require(others_clear(mem, 4), 'water1 did not open mission 5')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'water1 quest edited')
    require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, 'water1 quest bytes')
    # text_lookup returns 0, so the help callee receives empty text ids.
    require(rig.calls == help_calls(keys['water1_help_title'], keys['water1_help_body']), rig.calls)
    require('inventory_findItemBySubstring' not in stubs(rig), stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    return 3


def shard_ticks(rig, mem, count, shells, paused=0, each=None):
    rig.responder.shells = shells
    mem.w32(G_PAUSED, paused)
    last = None
    for n in range(count):
        clear_defer(mem)
        last = run_entry(rig, 'shardCheck')
        if each is not None:
            each(n + 1)
    return last


def check_shard_static(levels, level, keys):
    image = levels[level]['script.scr']
    _counter, compared, help_site, remove_site = SHARD_VARS[level]
    calls = calls_of(image, 'shardCheck')
    sites = {off: (name, args) for off, name, args in calls}
    require(sites[help_site][0] == 'addHelpMessage', (level, sites.get(help_site)))
    removes = [off for off, name, _args in calls if name == 'removeQuest']
    # wate2 shardCheck has no removeQuest call site. watg has one, whose
    # argument is the not-evil wat1 quest title.
    require(removes == ([remove_site] if remove_site else []), (level, removes))
    if remove_site:
        require(sites[remove_site][1][0] == keys['good_title'], level)
    # The compared variable has one direct store in the whole image: in
    # start, 0x10 after that entry's playerHasItem call.
    store = SHARD_BASE_STORE[level]
    require(var_writes(image, compared) == [store], (level, var_writes(image, compared)))
    start, end = entry_span(image, 'start')
    require(start <= store < end, level)
    require(any(off == store - 0x10 and name == 'playerHasItem'
                for off, name, _args in calls_of(image, 'start')), (level, 'base store'))
    want = struct.unpack_from('<i', image, 0x60 + struct.unpack_from('<i', image, 0x70)[0] + compared)[0]
    require(want == 0, (level, want))


def check_shards(rig, levels, seed, keys):
    checks = 0
    done = R.complete_byte(SENTINEL, -1)
    offered = R.complete_byte(R.available_byte(SENTINEL, 1), -1)
    require(done == 0xA2 and offered == 0xA3, (hex(done), hex(offered)))
    # Script offset of the `A == 25` compare inside shardCheck.
    compares = {
        'wate2a': 0x13EC, 'wate2b': 0x1374, 'wate2c': 0x1374,
        'watg2a': 0xD00, 'watg2b': 0xD00, 'watg2c': 0xD00,
    }
    grant_calls = shard_grant_calls(keys)
    for level in SHARD_LEVELS:
        image = levels[level]['script.scr']
        counter, compared, _help, remove_site = SHARD_VARS[level]
        require(compare_imm(image, 'shardCheck', SHARD_TICKS) == compares[level],
                (level, compare_imm(image, 'shardCheck', SHARD_TICKS)))
        check_shard_static(levels, level, keys)
        checks += 1
        # The quest wat1 start adds on the route into this level.
        title = keys['good_title'] if remove_site else keys['evil_title']

        def fresh(shells, offer=False, base=None):
            mem = prepare(rig, image, seed, shells=shells)
            require(rig.image_pause == (0, 0, 0), rig.image_pause)
            if offer:
                mem.w8(PLAYERS + MISSION + 4, R.available_byte(SENTINEL, 1))
            if base is not None:
                mem.w32(data_addr(rig, image, compared), base & 0xFFFFFFFF)
            plant_quest(rig, title, 'plant-body')
            require(mem.cstr(PLAYERS + QUEST, 32) == title, level)
            plant_var(rig, 'wat_gotShard', 0x5A)
            return mem

        def held(mem, n, offer=False):
            first = R.available_byte(SENTINEL, 1) if offer else SENTINEL
            require(bytes_are(mem, 4, (first, SENTINEL, SENTINEL, SENTINEL)), (level, n, 'grant'))
            require(others_clear(mem, 4), (level, n))
            require(dict(variables(mem))['wat_gotshard'] == 0x5A, (level, n, 'shard'))
            require(mem.u32(PLAYERS + QUEST_COUNT) == 1, (level, n, 'count'))
            require(mem.cstr(PLAYERS + QUEST, 32) == title, (level, n, 'removed'))
            require(defer_name(mem) == 'shardCheck', (level, n, defer_name(mem)))

        for shells in (0, 1, 2):
            mem = fresh(shells)
            cmp_addr = data_addr(rig, image, compared)
            ctr_addr = data_addr(rig, image, counter)
            require(mem.s32(cmp_addr) == 0, (level, 'compared'))

            def early(n):
                # Calls 1-24 at this stub value: no stub call, no grant.
                require(rig.calls == [], (level, shells, n, rig.calls))
                held(mem, n)
                require(mem.s32(ctr_addr) == n, (level, n, mem.s32(ctr_addr)))
                require(not any(w[1] == cmp_addr for w in rig.emu.writes), (level, n))
            shard_ticks(rig, mem, SHARD_TICKS - 1, shells, each=early)
            shard_ticks(rig, mem, 1, shells)
            require(mem.s32(cmp_addr) == 0 and not any(w[1] == cmp_addr for w in rig.emu.writes),
                    (level, 'compared written'))
            require(mem.s32(ctr_addr) == 0, (level, 'counter reset', mem.s32(ctr_addr)))
            if shells == 0:
                require(rig.calls == [SHARD_COUNT_CALL], (level, rig.calls))
                held(mem, SHARD_TICKS)
            else:
                require(bytes_are(mem, 4, (done,) * 4), (level, shells, 'grant'))
                require(others_clear(mem, 4), level + ' next mission')
                require_stored(rig, mem, 'wat_gotshard', 1)
                # Count stub of shardofwater for player 0. text_lookup returns 0.
                # res_find returns 0, so the sound callee receives resource 0.
                # No player object, so onePlayerHasItem does not call the finder.
                require(rig.calls == grant_calls, rig.calls)
                require(defer_name(mem) == '', (level, 'queued on the grant'))
                if remove_site:
                    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, (level, 'quest stayed'))
                    require(mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', level)
                else:
                    # SR6-1: the granting call keeps the evil quest on wate2.
                    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, (level, 'quest removed'))
                    require(mem.cstr(PLAYERS + QUEST, 32) == title, (level, 'slot'))
            require(mem.u32(N.N.G_RAND_SEED) == seed, level)
            checks += 1
        mem = fresh(1, offer=True)
        shard_ticks(rig, mem, SHARD_TICKS - 1, 1, each=lambda n: held(mem, n, offer=True))
        shard_ticks(rig, mem, 1, 1)
        require(bytes_are(mem, 4, (offered, done, done, done)), (level, 'offered'))
        checks += 1
        mem = fresh(1)
        shard_ticks(rig, mem, SHARD_TICKS - 1, 0)

        def paused(n):
            require(rig.calls == [], (level, 'paused', n, rig.calls))
            held(mem, SHARD_TICKS - 1)
            require(mem.s32(data_addr(rig, image, counter)) == SHARD_TICKS - 1, (level, 'paused count'))
        shard_ticks(rig, mem, 5, 1, paused=1, each=paused)
        shard_ticks(rig, mem, 1, 1, paused=0)
        require(bytes_are(mem, 4, (done,) * 4), (level, 'tick after the paused ones'))
        require_stored(rig, mem, 'wat_gotshard', 1)
        require(rig.calls == grant_calls, rig.calls)
        checks += 1
        # The 25th call grants only when the count stub exceeds the compared
        # variable. Planted values stand in for the start store.
        for base, shells, grants in ((1, 1, False), (1, 2, True), (-1, 0, True)):
            mem = fresh(shells, base=base)
            shard_ticks(rig, mem, SHARD_TICKS, shells)
            require(bytes_are(mem, 4, ((done,) * 4) if grants else ((SENTINEL,) * 4)),
                    (level, base, shells))
            require(rig.calls == (grant_calls if grants else [SHARD_COUNT_CALL]), (level, base, rig.calls))
            checks += 1
    return checks


def check_wall_and_hole(rig, levels, seed, keys):
    checks = 0
    for level in ('wate2a', 'wate2b', 'wate2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        plant_quest(rig, keys['evil_title'], 'plant-body')
        ret, err = run_entry(rig, 'brokeFinalWall')
        exc = rig.last_error
        require(ret is None and isinstance(exc, MemoryFault), (level, ret, err))
        # A 4-byte read of address 0x10 at pc 0x146ecc, inside
        # addParticleOnObject: that builtin was entered, the pc lies before
        # the next builtin, and the return address of its last callee does too.
        require((exc.pc, exc.addr, exc.size, exc.kind) == (0x146ECC, 0x10, 4, 'read'),
                (level, hex(exc.pc), hex(exc.addr), exc.size, exc.kind))
        require(ADD_PARTICLE <= exc.pc < ADD_PARTICLE_END, hex(exc.pc))
        require(ADD_PARTICLE <= (rig.emu.r[31] & 0xFFFFFFFF) < ADD_PARTICLE_END, hex(rig.emu.r[31]))
        require(ADD_PARTICLE in [c.target for c in rig.emu.calls], level)
        require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), level)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, level + ' removed the quest')
        require(defer_name(mem) == 'particleLoop', (level, defer_name(mem)))
        checks += 1
    for level in ('watg2a', 'watg2b', 'watg2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        plant_quest(rig, keys['good_title'], 'plant-body')
        require(run_entry(rig, 'holeCheck')[0] == 0, level)
        require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), level)
        require(missions_held(mem), level)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, level)
        require(mem.cstr(PLAYERS + QUEST, 32) == keys['good_title'], level)
        require(mem.u8(N.N.G_POST_ACTION) == 0, level)
        require_stored(rig, mem, 'wat_complete', 0)
        require('hud_showHelpMessage' not in stubs(rig), stubs(rig))
        checks += 1
    image = levels['wate2a']['script.scr']
    cases = (
        ((), 1),
        ((('wat_complete', 1),), 0),
        ((('wat_gotShard', 1),), 1),
        ((('wat_complete', 1), ('wat_gotShard', 1)), 1),
    )
    for plants, expect in cases:
        mem = prepare(rig, image, seed)
        for name, value in plants:
            plant_var(rig, name, value)
        require(run_entry(rig, 'iff46')[0] == expect, (plants, expect))
        checks += 1
    return checks


def check_tor_start(rig, image, seed):
    mem = prepare(rig, image, seed)
    plant_mission_vars(rig, mem, (('startedMission5', 1), ('currentMission', 5)))
    require(run_entry(rig, 'start')[0] == 0, 'tormenta start')
    require(bytes_are(mem, 5, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
            'mission 5')
    require(others_clear(mem, 5), 'mission 4 or 6 moved')
    require_stored(rig, mem, 'startedmission5', 1)
    require_stored(rig, mem, 'currentmission', 5)
    require_stored(rig, mem, 'tor_bri1', 0)
    require_stored(rig, mem, 'tor_bri5', 0)
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'tor quest')
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'tor post')
    require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'tor pending')
    require(stubs(rig) == [], stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    plant_var(rig, 'tor_beenHere', 0x5A)
    rig.calls = []
    rig.emu.calls.clear()
    rig.emu.writes.clear()
    require(N.s32(rig.call(N.A['script_runPostAction'], max_steps=4000000)) == 0, 'absorb post')
    require_stored(rig, mem, 'tor_beenhere', 1)
    require(rig.calls == [], stubs(rig))
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_beenHere', 1)
    require(run_entry(rig, 'start')[0] == 0, 'return start')
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'return still posts')
    for evil, door in ((0, 'goodstart'), (1, 'evilstart')):
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'preStart')[0] == 0, 'preStart')
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == door, (evil, mem.cstr(N.N.G_ENTRANCE_NAME, 32)))
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'preStart pending')
        require_stored(rig, mem, 'tor_beenhere', 0)
        require(rig.calls == [('lump_load', (b'bust.lmp',))], rig.calls)
        require(missions_held(mem), 'preStart mission')
    return 5


def check_tor_cuts_and_dialog(rig, image, seed, found):
    checks = 0
    for entry, name, planted in (
            ('if87a0', 'sawtorb', None),
            ('if87a0', 'sawtorb', 1),
            ('if3f82', 'sawtora', None),
            ('if3f82', 'sawtora', 1)):
        mem = prepare(rig, image, seed)
        if planted is not None:
            plant_var(rig, name, planted)
        require(mem.cstr(N.N.G_LEVEL_NAME, 16) == '', entry)
        require(run_entry(rig, entry)[0] == 0, entry)
        if planted is None:
            require(rig.calls == cut_calls('torb' if entry == 'if87a0' else 'tora'), rig.calls)
            require_stored(rig, mem, name, 1)
        else:
            require(rig.calls == [], stubs(rig))
            require(dict(variables(mem))[name] == 1, variables(mem))
        require(missions_held(mem), entry)
        checks += 1
    title = arg_at(found, 0x748, 0)
    body = arg_at(found, 0x748, 1)
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_talkedToGol', 0x5A)
    require(run_entry(rig, 'setv2725')[0] == 0, 'quest action')
    require_stored(rig, mem, 'tor_talkedtogol', 1)
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'count')
    require(mem.cstr(PLAYERS + QUEST, 32) == title, 'title')
    require(mem.cstr(PLAYERS + QUEST + 0x20, 32) == body, 'body')
    require(others_clear(mem, 5) and bytes_are(mem, 5, (SENTINEL,) * 4), 'quest moved a mission')
    checks += 1
    # evil, talked, expect. talked None leaves the name absent.
    matrix = (
        ('if1b74', 0, None, 0),
        ('if1b74', 1, None, 1),
        ('if1b74', 1, 1, 0),
        ('ifb0b8', 0, None, 1),
        ('ifb0b8', 1, None, 0),
        ('ifb0b8', 0, 1, 0),
        ('ifa33a', 0, None, 0),
        ('if4fec', 0, None, 0),
        ('if4fec', 0, 1, 1),
    )
    for entry, evil, talked, expect in matrix:
        mem = prepare(rig, image, seed, evil=evil)
        if entry == 'if4fec':
            if talked is not None:
                plant_var(rig, 'tor_finishedMission', talked)
        elif talked is not None:
            plant_var(rig, 'tor_talkedToGol', talked)
        require(run_entry(rig, entry)[0] == expect, (entry, evil, talked))
        checks += 1
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_talkedToGol', 1)
    plant_var(rig, 'tor_gotShard', 0)
    require(run_entry(rig, 'ifa33a')[0] == 1, 'talked, no shard')
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_talkedToGol', 1)
    plant_var(rig, 'tor_gotShard', 1)
    require(run_entry(rig, 'ifa33a')[0] == 0, 'talked and shard')
    checks += 2
    for entry in ('if5184', 'if799d'):
        mem = prepare(rig, image, seed)
        plant_var(rig, 'tor_talkedToGol', 1)
        plant_var(rig, 'tor_gotShard', 1)
        require(run_entry(rig, entry)[0] == 1, (entry, 'ready'))
        require(dict(variables(mem)).get('tor_finishedmission') == 0, variables(mem))
        mem = prepare(rig, image, seed)
        plant_var(rig, 'tor_talkedToGol', 1)
        plant_var(rig, 'tor_gotShard', 1)
        plant_var(rig, 'tor_finishedMission', 1)
        require(run_entry(rig, entry)[0] == 0, (entry, 'finished'))
        mem = prepare(rig, image, seed)
        plant_var(rig, 'tor_gotShard', 1)
        require(run_entry(rig, entry)[0] == 0, (entry, 'shard only'))
        checks += 3
    return checks


def check_endtor(rig, image, seed, keys):
    title = keys['endtor_title']
    gol = keys['gol_title']
    # The removed title is not the setv2725 (gol) title.
    require(title != gol and len(title) == 17 and title != 'NoQuests', len(title))
    done = R.complete_byte(SENTINEL, -1)
    require(done == 0xA2, hex(done))
    # callScri8c36's only call is callScript of endtor.
    calls = calls_of(image, 'callScri8c36')
    require([(name, args) for _off, name, args in calls] == [('callScript', ('endtor',))], calls)
    removes = [off for off, name, _args in calls_of(image, 'endtor') if name == 'removeQuest']
    require(removes == [0x1E20], [hex(off) for off in removes])
    checks = 0
    for entry in ('endtor', 'callScri8c36'):
        mem = prepare(rig, image, seed)
        require(run_entry(rig, entry)[0] == 0, entry)
        require(bytes_are(mem, 5, (done, done, done, done)), (entry, 'grant'))
        require(others_clear(mem, 5), (entry, 'opened another mission'))
        require_stored(rig, mem, 'tor_finishedmission', 1)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 0, (entry, 'count'))
        require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, (entry, 'empty slot changed'))
        require(rig.calls == COMPLETION_SOUND_CALLS, rig.calls)
        require(mem.u32(N.N.G_RAND_SEED) == seed, (entry, 'seed'))
        mem = prepare(rig, image, seed)
        plant_quest(rig, title, 'plant-body')
        require(mem.cstr(PLAYERS + QUEST, 32) == title, 'planted title')
        require(run_entry(rig, entry)[0] == 0, entry)
        require(bytes_are(mem, 5, (done, done, done, done)), (entry, 'planted grant'))
        require(others_clear(mem, 5), (entry, 'planted others'))
        require_stored(rig, mem, 'tor_finishedmission', 1)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 0, (entry, 'quest count'))
        require(rig.calls == COMPLETION_SOUND_CALLS, rig.calls)
        # Removing the last entry leaves the placeholder the quest log already
        # documents. The 17-character title is not still in the slot.
        require(mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', (entry, 'placeholder'))
        # The gol quest is not removed, alone or with the 17-character one in
        # either order.
        for plants in ((gol,), (gol, title), (title, gol)):
            mem = prepare(rig, image, seed)
            for planted in plants:
                plant_quest(rig, planted, 'plant-body')
            require(run_entry(rig, entry)[0] == 0, (entry, 'gol'))
            require(bytes_are(mem, 5, (done, done, done, done)), (entry, 'gol grant'))
            require(mem.u32(PLAYERS + QUEST_COUNT) == 1, (entry, len(plants), 'gol count'))
            require(mem.cstr(PLAYERS + QUEST, 32) == gol, (entry, len(plants), 'gol kept'))
        checks += 3
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_finishedMission', 1)
    plant_quest(rig, title, 'plant-body')
    require(run_entry(rig, 'endtor')[0] == 0, 'second endtor')
    require(bytes_are(mem, 5, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), 'second grant')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'second remove')
    require(stubs(rig) == [], stubs(rig))
    return checks + 1


def check_tor_travel(rig, levels, seed):
    routes = (
        ('tormenta', 'newWorld3aa4', 'tormentb', 'ENTRANCE-SENTINEL'),
        ('tormentb', 'newWorld1223', 'tormenta', 'torb'),
        ('tormentb', 'newWorld9066', 'torment2', 'frontdoor'),
        ('torment2', 'newWorlda629', 'tormentb', 'frontdoor'),
        ('torment2', 'newWorldf608', 'torment3', 'leftdoor'),
        ('torment2', 'newWorld181f', 'torment3', 'rightdoor'),
        ('torment3', 'newWorld6aa', 'torment2', 'rightdoor'),
        ('torment3', 'newWorldbc33', 'torment2', 'leftdoor'),
    )
    checks = 0
    for level, entry, dest, door in routes:
        mem = prepare(rig, levels[level]['script.scr'], seed)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0x5A, entry)
        require(missions_held(mem), entry)
        require(run_entry(rig, entry)[0] == 0, entry)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == dest, (entry, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == door, (entry, mem.cstr(N.N.G_ENTRANCE_NAME, 32)))
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, entry)
        require(missions_held(mem), entry + ' missions')
        require(rig.calls == [('net_closeLocalMenus', (0,))], rig.calls)
        require(mem.u32(N.N.G_RAND_SEED) == seed, entry)
        checks += 1
    return checks


def check_store_calls(rig, image, entry, opens):
    """changeSwoop(0) then activateStore, by call site and by executed builtin."""
    names = [(name, args) for _off, name, args in calls_of(image, entry)
             if name in ('changeSwoop', 'activateStore')]
    targets = [c.target for c in rig.emu.calls]
    if opens:
        require([name for name, _args in names] == ['changeSwoop', 'activateStore'], (entry, names))
        require(names[0][1] == (0,), (entry, names[0]))
        require(targets.count(CHANGE_SWOOP) == 1 and targets.count(ACTIVATE_STORE) == 1, entry)
        require(targets.index(CHANGE_SWOOP) < targets.index(ACTIVATE_STORE), entry)
        require(stubs(rig) == ['dialog_isOpen', 'shop_openOrStock'], (entry, stubs(rig)))
    else:
        require(names == [], (entry, names))
        require(CHANGE_SWOOP not in targets and ACTIVATE_STORE not in targets, entry)
        require(stubs(rig) == [], (entry, stubs(rig)))


def check_next_mission(rig, levels, seed, keys):
    store = {'setMissibbbb', 'setMissi9389', 'setMissi4082', 'setMissi6d46'}
    quest = {'setMissicaba', 'setMissi6d46'}
    mission_of = {
        'setMissif825': 5, 'setMissibbbb': 5, 'setMissi9389': 5,
        'setMissi95d5': 6, 'setMissi4082': 6, 'setMissicaba': 6, 'setMissi6d46': 6,
    }
    checks = 0
    image = levels['hub']['script.scr']
    title, body = keys['hub_title'], keys['hub_body']
    for entry in sorted(quest):
        adds = [args for _off, name, args in calls_of(image, entry) if name == 'addQuest']
        require(adds == [(title, body)], (entry, len(adds)))
    for entry, index in mission_of.items():
        mem = prepare(rig, image, seed)
        require(run_entry(rig, entry)[0] == 0, entry)
        require(mission(mem, 0, index) == R.available_byte(SENTINEL, 1), (entry, hex(mission(mem, 0, index))))
        require(all(mission(mem, slot, index) == SENTINEL for slot in (1, 2, 3)), entry)
        require(all(mission(mem, slot, other) == SENTINEL
                    for slot in range(4) for other in (4, 5, 6) if other != index), entry)
        if entry in quest:
            require(mem.u32(PLAYERS + QUEST_COUNT) == 1, entry)
            require(mem.cstr(PLAYERS + QUEST, 32) == title, entry)
            require(mem.cstr(PLAYERS + QUEST + 0x20, 32) == body, entry)
        else:
            require(mem.u32(PLAYERS + QUEST_COUNT) == 0, entry)
            require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, entry)
        check_store_calls(rig, image, entry, entry in store)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', entry)
        checks += 1
    hub2_store = {'setMissibbbb', 'setMissi9389', 'setMissi4082', 'setMissic3ab'}
    hub2 = {
        'setMissif825': 5, 'setMissibbbb': 5, 'setMissi9389': 5,
        'setMissi95d5': 6, 'setMissi4082': 6, 'setMissic3ab': 6,
    }
    image = levels['hub2']['script.scr']
    for entry, index in hub2.items():
        mem = prepare(rig, image, seed)
        require(run_entry(rig, entry)[0] == 0, 'hub2 ' + entry)
        require(mission(mem, 0, index) == R.available_byte(SENTINEL, 1), entry)
        require(all(mission(mem, slot, other) == SENTINEL
                    for slot in range(4) for other in (4, 5, 6) if other != index
                    or slot != 0), entry)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'hub2 quest ' + entry)
        require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, entry)
        check_store_calls(rig, image, entry, entry in hub2_store)
        checks += 1
    return checks


def prop_set(blob):
    count, _, strtab = struct.unpack_from('<hHi', blob, 0)

    def text(off):
        o = strtab + off
        return blob[o:blob.index(b'\0', o)].decode('latin1')

    found, p = set(), 8
    for _ in range(count):
        _cls, size, _pad = struct.unpack_from('<ihH', blob, p)
        q = p + 20
        while q < p + size:
            po, = struct.unpack_from('<i', blob, q)
            if po == 0:
                break
            found.add(text(po))
            q += 4
        p += size
    return found


def check_links(levels):
    wat = prop_set(levels['wat1']['objects.ob'])
    for name in ('newWorld57c0', 'newWorld9711', 'newWorld7517', 'newWorldced',
                 'newWorldf0d', 'newWorldd7df'):
        require('action=' + name in wat, name)
    require('key=return10c8' in wat and 'key=return6198' in wat, 'keys')
    water = prop_set(levels['water1']['objects.ob'])
    require('t=callScri7351' in water, water)
    gol = dbin_rows(levels['tormenta']['gol.dbin'])
    require(len(gol) == 9, len(gol))
    require(gol[0] == ('if1b74', [('', '', 2)]), gol[0])
    require(gol[1] == ('ifb0b8', [('', '', 2)]), gol[1])
    require(gol[2] == ('', [('', 'setv2725', -1)]), gol[2])
    require(gol[3] == ('ifa33a', [('', '', -1)]), gol[3])
    require(gol[4] == ('if5184', [('', '', 5)]), gol[4])
    require(gol[5] == ('if799d', [('', '', 6)]), gol[5])
    require(gol[6] == ('if799d', [('', '', 7)]), gol[6])
    require(gol[7] == ('if799d', [('', '', 8)]), gol[7])
    require(gol[8] == ('if4fec', [('', 'callScri8c36', -1)]), gol[8])
    firiona = dbin_rows(levels['hub']['firiona.dbin'])
    bak = dbin_rows(levels['hub']['firiona_bak.dbin'])
    require(firiona[14][1] == [('', 'setMissif825', -1), ('', 'setMissi9389', -1)], firiona[14])
    require(firiona[17][1] == [('', 'setMissicaba', -1), ('', 'setMissi6d46', -1)], firiona[17])
    require(bak[14][1] == [('', 'setMissif825', -1), ('', 'setMissibbbb', -1)], bak[14])
    require(bak[16][1] == [('', 'setMissi95d5', -1), ('', 'setMissi4082', -1)], bak[16])
    natasla = dbin_rows(levels['hub2']['natasla.dbin'])
    natasla_bak = dbin_rows(levels['hub2']['natasla_bak.dbin'])
    require(natasla[9][1] == [('', 'setMissif825', -1), ('', 'setMissi9389', -1)], natasla[9])
    require(natasla[11][1] == [('', 'setMissi95d5', -1), ('', 'setMissic3ab', -1)], natasla[11])
    require(natasla_bak[9][1] == [('', 'setMissif825', -1), ('', 'setMissibbbb', -1)], natasla_bak[9])
    require(natasla_bak[12][1] == [('', 'setMissi95d5', -1), ('', 'setMissi4082', -1)], natasla_bak[12])
    tor = prop_set(levels['tormenta']['objects.ob'])
    require('t=newWorld3aa4' in tor and 't=if87a0' in tor and 't=if3f82' in tor, 'tor triggers')
    require('dialogscript=startDia7a53' in tor, 'gol dialog link')
    return 16


def check_sites(levels):
    expect = (
        ('wat1', 0x314, 'setMissionAvailable', (4, 1)),
        ('wat1', 0x46C, 'postAction', ('absorb',)),
        ('wat1', 0x4F4, 'cutScene', ('wat1',)),
        ('water1', 0x78, 'setMissionAvailable', (4, 1)),
        ('water1', 0x124, 'grantMission', (4,)),
        ('tormenta', 0xD34, 'setMissionAvailable', (5, 1)),
        ('tormenta', 0xDC8, 'postAction', ('absorb',)),
        ('tormenta', 0x1D8C, 'grantMission', (5,)),
        ('tormenta', 0x748, 'addQuest', ()),
        ('tormenta', 0x1E20, 'removeQuest', ()),
        ('wat1', 0x2A4, 'addQuest', ()),
        ('wat1', 0x2E0, 'addQuest', ()),
        ('water1', 0x158, 'addHelpMessage', ()),
        ('hub', 0x2410, 'addQuest', ()),
    )
    checks = 0
    for level, off, native, args in expect:
        _publics, found, _pool = calls_in(levels[level]['script.scr'])
        got = [row for row in found if row[0] == off]
        require(len(got) == 1 and got[0][1] == native and got[0][2][:len(args)] == args,
                (level, hex(off), got[:1]))
        checks += 1
    return checks


def check_seed(rig, levels, seed):
    keys = text_keys(levels)
    checks = check_sites(levels)
    checks += check_links(levels)
    checks += check_wat_start(rig, levels['wat1']['script.scr'], seed, keys)
    checks += check_keys_and_travel(rig, levels, seed)
    checks += check_water1(rig, levels['water1']['script.scr'], seed, keys)
    checks += check_shards(rig, levels, seed, keys)
    checks += check_wall_and_hole(rig, levels, seed, keys)
    _publics, found, _pool = calls_in(levels['tormenta']['script.scr'])
    checks += check_tor_start(rig, levels['tormenta']['script.scr'], seed)
    checks += check_tor_cuts_and_dialog(rig, levels['tormenta']['script.scr'], seed, found)
    checks += check_endtor(rig, levels['tormenta']['script.scr'], seed, keys)
    checks += check_tor_travel(rig, levels, seed)
    checks += check_next_mission(rig, levels, seed, keys)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--seed', type=int, action='append', dest='seeds')
    args = parser.parse_args()
    blob = open(args.elf, 'rb').read()
    if hashlib.sha256(blob).hexdigest() != ELF_SHA256:
        raise SystemExit('unexpected executable')
    levels = load_levels(args.data)
    for seed in (args.seeds or [20973, 7]):
        rig = N.Rig(args.elf)
        rig.checkpoint()
        rig.responder = Quiet()
        count = check_seed(rig, levels, seed)
        print('PASS seed %d: %d mission-4/5 checks' % (seed, count))


if __name__ == '__main__':
    main()
