#!/usr/bin/env python3
"""Mission 4 and 5 story beats against the original script machine.

The menu requests that write wat1 and tormenta stay in difftest_story_beats.py.
Mission 3's grant, and the hub entries that make mission 4 available, stay in
difftest_story_mission3.py. This file runs the water and tormenta entries.
No dialogue text is written.

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
from ee_emu import EmuError  # noqa: E402
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
    try:
        return N.s32(rig.call(N.A['script_runByName'], pointer, max_steps=4000000)), ''
    except EmuError as exc:
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


def check_wat_start(rig, image, seed):
    checks = 0
    for evil, title, body in (
            (0, 'stopthe5b99', 'plugthe653b'),
            (1, 'floodth5019', 'penetrataf0d')):
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'start')[0] == 0, 'wat1 start')
        require(bytes_are(mem, 4, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
                'wat1 available')
        require(others_clear(mem, 4), 'wat1 other missions')
        got = dict(variables(mem))
        require(got.get('startedmission4') == 1 and got.get('currentmission') == 4, got)
        require(got.get('sawwat1') == 0, got)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'one quest')
        require(mem.cstr(PLAYERS + QUEST, 32) == title, 'quest title')
        require(mem.cstr(PLAYERS + QUEST + 0x20, 32) == body, 'quest body')
        require(mem.u32(PLAYERS + REC + QUEST_COUNT) == 0x5A5A5A5A, 'other count')
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'post')
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'pending')
        require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
        checks += 1
    mem = prepare(rig, image, seed)
    run_entry(rig, 'start')
    rig.calls = []
    rig.emu.calls.clear()
    require(N.s32(rig.call(N.A['script_runPostAction'], max_steps=4000000)) == 0, 'post')
    require(stubs(rig) == ['res_find', 'cut_start'], stubs(rig))
    require(dict(variables(mem))['sawwat1'] == 1, variables(mem))
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'post cleared')
    checks += 1
    mem = prepare(rig, image, seed)
    plant_var(rig, 'sawWat1', 1)
    require(run_entry(rig, 'start')[0] == 0, 'repeat start')
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'repeat posted')
    require(mission(mem, 0, 4) == R.available_byte(SENTINEL, 1), 'repeat available')
    checks += 1
    # waterIntro cuts whether or not the variable is already 1. start is what
    # withholds the post.
    for planted in (None, 1):
        mem = prepare(rig, image, seed)
        if planted is not None:
            plant_var(rig, 'sawWat1', planted)
        require(run_entry(rig, 'absorb')[0] == 0, 'absorb')
        require(stubs(rig) == ['res_find', 'cut_start'], stubs(rig))
        require(dict(variables(mem))['sawwat1'] == 1, variables(mem))
        checks += 1
    return checks


def check_keys_and_travel(rig, levels, seed):
    image = levels['wat1']['script.scr']
    checks = 0
    for evil, good_key, evil_key in ((0, 1, 0), (1, 0, 1)):
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'return6198')[0] == good_key, ('good key', evil))
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'return10c8')[0] == evil_key, ('evil key', evil))
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'key pending')
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
        require(run_entry(rig, entry)[0] == 0, entry)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == level, (entry, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', entry)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, entry)
        require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), entry)
        require('net_closeLocalMenus' in stubs(rig), stubs(rig))
        checks += 1
    for level in ('wate2a', 'wate2b', 'wate2c', 'watg2a', 'watg2b', 'watg2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        require(run_entry(rig, 'newWorlde6b4')[0] == 0, level)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'wat1', level)
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', level)
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, level)
        checks += 1
    return checks


def check_water1(rig, image, seed):
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'start')[0] == 0, 'water1 start')
    require(bytes_are(mem, 4, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
            'water1 available')
    require(others_clear(mem, 4), 'water1 missions')
    got = dict(variables(mem))
    require(got.get('startedmission4') == 1 and got.get('currentmission') == 4, got)
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'water1 quest')
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'water1 post')
    require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'water1 pending')
    publics, _found, pool = calls_in(image)
    require(pool.get(0) == 'steppedOnTrigger' and publics['callScri7351'] == 0, 'wrapper')
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'callScri7351')[0] == 0, 'water1 trigger')
    done = R.complete_byte(SENTINEL, -1)
    require(bytes_are(mem, 4, (done, done, done, done)), 'water1 grant')
    require(others_clear(mem, 4), 'water1 did not open mission 5')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'water1 quest edited')
    require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, 'water1 quest bytes')
    require('hud_showHelpMessage' in stubs(rig), stubs(rig))
    require('inventory_findItemBySubstring' not in stubs(rig), stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    return 3


def shard_ticks(rig, mem, count, shells, paused=0):
    rig.responder.shells = shells
    mem.w32(G_PAUSED, paused)
    last = None
    for _ in range(count):
        clear_defer(mem)
        last = run_entry(rig, 'shardCheck')
    return last


def check_shards(rig, levels, seed):
    checks = 0
    done = R.complete_byte(SENTINEL, -1)
    offered = R.complete_byte(R.available_byte(SENTINEL, 1), -1)
    # wate2 removes nothing in shardCheck. watg removes the plug quest.
    # Script offset of the `A == 25` compare inside shardCheck.
    compares = {
        'wate2a': 0x13EC, 'wate2b': 0x1374, 'wate2c': 0x1374,
        'watg2a': 0xD00, 'watg2b': 0xD00, 'watg2c': 0xD00,
    }
    jobs = (
        ('wate2a', None, True),
        ('wate2b', None, False),
        ('wate2c', None, False),
        ('watg2a', 'stopthe5b99', False),
        ('watg2b', 'stopthe5b99', False),
        ('watg2c', 'stopthe5b99', False),
    )
    for level, title, offer in jobs:
        image = levels[level]['script.scr']
        require(compare_imm(image, 'shardCheck', SHARD_TICKS) == compares[level],
                (level, compare_imm(image, 'shardCheck', SHARD_TICKS)))
        mem = prepare(rig, image, seed, shells=0)
        require(rig.image_pause == (0, 0, 0), rig.image_pause)
        if offer:
            mem.w8(PLAYERS + MISSION + 4, R.available_byte(SENTINEL, 1))
        if title:
            plant_quest(rig, title, 'plant-body')
        shard_ticks(rig, mem, SHARD_TICKS - 1, 0)
        require(bytes_are(mem, 4, (R.available_byte(SENTINEL, 1) if offer else SENTINEL,
                                   SENTINEL, SENTINEL, SENTINEL)),
                (level, 'early grant'))
        require(defer_name(mem) == 'shardCheck', (level, defer_name(mem)))
        require(stubs(rig) == [], stubs(rig))
        shard_ticks(rig, mem, 1, 1)
        want0 = offered if offer else done
        require(bytes_are(mem, 4, (want0, done, done, done)), (level, [hex(mission(mem, s, 4)) for s in range(4)]))
        require(others_clear(mem, 4), level + ' next mission')
        require(dict(variables(mem)).get('wat_gotshard') == 1, (level, variables(mem)))
        require(stubs(rig) == [
            'inventory_countItemByName', 'text_lookup', 'text_lookup',
            'hud_showHelpMessage', 'res_find', 'sound_playOnObject',
            'sound_setPlaysWhileFrozen'], stubs(rig))
        require('inventory_findItemBySubstring' not in stubs(rig), stubs(rig))
        require(defer_name(mem) == '', (level, 'queued on the grant'))
        if title:
            require(mem.u32(PLAYERS + QUEST_COUNT) == 0, (level, 'quest stayed'))
            require(mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', level)
        require(mem.u32(N.N.G_RAND_SEED) == seed, level)
        checks += 1
    image = levels['wate2a']['script.scr']
    mem = prepare(rig, image, seed)
    plant_quest(rig, 'floodth5019', 'plant-body')
    shard_ticks(rig, mem, SHARD_TICKS, 0)
    require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), 'no item, no grant')
    require(stubs(rig) == ['inventory_countItemByName'], stubs(rig))
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'wate2 removed the flood quest')
    require('wat_gotshard' not in dict(variables(mem)), variables(mem))
    checks += 1
    mem = prepare(rig, image, seed)
    shard_ticks(rig, mem, SHARD_TICKS - 1, 0, paused=0)
    shard_ticks(rig, mem, 1, 1, paused=1)
    require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), 'paused tick granted')
    require(stubs(rig) == [], stubs(rig))
    shard_ticks(rig, mem, 1, 1, paused=0)
    require(bytes_are(mem, 4, (done, done, done, done)), 'tick after the paused one')
    checks += 1
    return checks


def check_wall_and_hole(rig, levels, seed):
    checks = 0
    for level in ('wate2a', 'wate2b', 'wate2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        plant_quest(rig, 'floodth5019', 'plant-body')
        ret, err = run_entry(rig, 'brokeFinalWall')
        require(ret is None and '00146ecc' in err, (level, ret, err))
        require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), level)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, level + ' removed the quest')
        require(defer_name(mem) == 'particleLoop', (level, defer_name(mem)))
        checks += 1
    for level in ('watg2a', 'watg2b', 'watg2c'):
        mem = prepare(rig, levels[level]['script.scr'], seed)
        plant_quest(rig, 'stopthe5b99', 'plant-body')
        require(run_entry(rig, 'holeCheck')[0] == 0, level)
        require(bytes_are(mem, 4, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), level)
        require(mem.u32(PLAYERS + QUEST_COUNT) == 1, level)
        require(mem.u8(N.N.G_POST_ACTION) == 0, level)
        require(dict(variables(mem)).get('wat_complete') == 0, (level, variables(mem)))
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
    require(run_entry(rig, 'start')[0] == 0, 'tormenta start')
    require(bytes_are(mem, 5, (R.available_byte(SENTINEL, 1), SENTINEL, SENTINEL, SENTINEL)),
            'mission 5')
    require(others_clear(mem, 5), 'mission 4 or 6 moved')
    got = dict(variables(mem))
    require(got.get('startedmission5') == 1 and got.get('currentmission') == 5, got)
    require(got.get('tor_bri1') == 0 and got.get('tor_bri5') == 0, got)
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'tor quest')
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'tor post')
    require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'tor pending')
    require(stubs(rig) == [], stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    rig.calls = []
    rig.emu.calls.clear()
    require(N.s32(rig.call(N.A['script_runPostAction'], max_steps=4000000)) == 0, 'absorb post')
    require(dict(variables(mem))['tor_beenhere'] == 1, variables(mem))
    require(stubs(rig) == [], stubs(rig))
    require('cut_start' not in stubs(rig), stubs(rig))
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_beenHere', 1)
    require(run_entry(rig, 'start')[0] == 0, 'return start')
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'return still posts')
    for evil, door in ((0, 'goodstart'), (1, 'evilstart')):
        mem = prepare(rig, image, seed, evil=evil)
        require(run_entry(rig, 'preStart')[0] == 0, 'preStart')
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == door, (evil, mem.cstr(N.N.G_ENTRANCE_NAME, 32)))
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', 'preStart pending')
        require(dict(variables(mem)).get('tor_beenhere') == 0, variables(mem))
        require(stubs(rig) == ['lump_load'], stubs(rig))
        require(bytes_are(mem, 5, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), 'preStart mission')
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
        require(run_entry(rig, entry)[0] == 0, entry)
        require(dict(variables(mem))[name] == 1, variables(mem))
        if planted is None:
            require(stubs(rig) == ['res_find', 'cut_start'], stubs(rig))
        else:
            require(stubs(rig) == [], stubs(rig))
        require(bytes_are(mem, 5, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), entry)
        checks += 1
    title = arg_at(found, 0x748, 0)
    body = arg_at(found, 0x748, 1)
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'setv2725')[0] == 0, 'quest action')
    require(dict(variables(mem))['tor_talkedtogol'] == 1, variables(mem))
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


def check_endtor(rig, image, seed, found):
    title = arg_at(found, 0x1E20, 0)
    require(isinstance(title, str) and len(title) == 17, len(title) if isinstance(title, str) else title)
    done = R.complete_byte(SENTINEL, -1)
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'endtor')[0] == 0, 'endtor')
    require(bytes_are(mem, 5, (done, done, done, done)), 'grant')
    require(others_clear(mem, 5), 'endtor opened another mission')
    require(dict(variables(mem))['tor_finishedmission'] == 1, variables(mem))
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'count')
    require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, 'empty slot changed')
    require(stubs(rig) == ['res_find', 'sound_playOnObject', 'sound_setPlaysWhileFrozen'], stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    mem = prepare(rig, image, seed)
    plant_quest(rig, title, 'plant-body')
    require(run_entry(rig, 'callScri8c36')[0] == 0, 'dialog action')
    require(bytes_are(mem, 5, (done, done, done, done)), 'action grant')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'quest count')
    # Removing the last entry leaves the placeholder the quest log already
    # documents. The 17-character title is not still in the slot.
    require(mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', 'placeholder')
    mem = prepare(rig, image, seed)
    plant_var(rig, 'tor_finishedMission', 1)
    plant_quest(rig, title, 'plant-body')
    require(run_entry(rig, 'endtor')[0] == 0, 'second endtor')
    require(bytes_are(mem, 5, (SENTINEL, SENTINEL, SENTINEL, SENTINEL)), 'second grant')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'second remove')
    require(stubs(rig) == [], stubs(rig))
    return 4


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
        require(run_entry(rig, entry)[0] == 0, entry)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == dest, (entry, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == door, (entry, mem.cstr(N.N.G_ENTRANCE_NAME, 32)))
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, entry)
        require(bytes_are(mem, 5, (SENTINEL,) * 4), entry)
        require(mem.u32(N.N.G_RAND_SEED) == seed, entry)
        checks += 1
    return checks


def check_next_mission(rig, levels, seed):
    store = {'setMissibbbb', 'setMissi9389', 'setMissi4082', 'setMissi6d46'}
    quest = {'setMissicaba', 'setMissi6d46'}
    mission_of = {
        'setMissif825': 5, 'setMissibbbb': 5, 'setMissi9389': 5,
        'setMissi95d5': 6, 'setMissi4082': 6, 'setMissicaba': 6, 'setMissi6d46': 6,
    }
    checks = 0
    image = levels['hub']['script.scr']
    _publics, found, _pool = calls_in(image)
    title = body = None
    for off, name, args in found:
        if name == 'addQuest' and args and args[0] == 'destroy8fcc':
            title, body = args[0], args[1]
            break
    require(title == 'destroy8fcc' and body == 'traveltc3c3', (title, body))
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
        if entry in store:
            require(stubs(rig) == ['dialog_isOpen', 'shop_openOrStock'], (entry, stubs(rig)))
        else:
            require(stubs(rig) == [], (entry, stubs(rig)))
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
        if entry in hub2_store:
            require(stubs(rig) == ['dialog_isOpen', 'shop_openOrStock'], (entry, stubs(rig)))
        else:
            require(stubs(rig) == [], (entry, stubs(rig)))
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
    require(gol[5][0] == 'if799d' and gol[6][0] == 'if799d' and gol[7][0] == 'if799d', gol[5:8])
    require(gol[7][1] == [('', '', 8)], gol[7])
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
        ('tormenta', 0x748, 'addQuest', ('findthe85aa', 'findtheaf23')),
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
    checks = check_sites(levels)
    checks += check_links(levels)
    checks += check_wat_start(rig, levels['wat1']['script.scr'], seed)
    checks += check_keys_and_travel(rig, levels, seed)
    checks += check_water1(rig, levels['water1']['script.scr'], seed)
    checks += check_shards(rig, levels, seed)
    checks += check_wall_and_hole(rig, levels, seed)
    _publics, found, _pool = calls_in(levels['tormenta']['script.scr'])
    checks += check_tor_start(rig, levels['tormenta']['script.scr'], seed)
    checks += check_tor_cuts_and_dialog(rig, levels['tormenta']['script.scr'], seed, found)
    checks += check_endtor(rig, levels['tormenta']['script.scr'], seed, found)
    checks += check_tor_travel(rig, levels, seed)
    checks += check_next_mission(rig, levels, seed)
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
