#!/usr/bin/env python3
"""Mission 3 story beats against the original script machine.

The menu request that writes islc1 stays in difftest_story_beats.py. Hub2's
mission-3 offer stays in the mission-2 research. This file runs the island
level entries, the completion entries, and the hub entries that make mission
4 available. No dialogue text is written.

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; \
  sys.path.insert(0,"tools"); \
  sys.argv=["difftest_story_mission3.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA"]; \
  runpy.run_path("tools/difftest_story_mission3.py", run_name="__main__")'
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE  # noqa: E402
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
SENTINEL = 0xA0
FILL = 0x5A
MISSION_BYTES = 52


class Quiet:
    def __init__(self):
        self.shells = 0

    def answer(self, name, args):
        if name == 'inventory_findItemBySubstring':
            return (-1, 0)
        if name == 'inventory_countItemByName':
            return self.shells
        return 0


def lump(path, filename):
    data = open(path, 'rb').read()
    stem = os.path.basename(path).lower().replace('.gob', '.lmp')
    for name, lo, size in gob_entries(data):
        if name.lower() != stem:
            continue
        blob = data[lo:lo + size]
        for inner, off, inner_size in lmp_entries(blob):
            if inner.lower() == filename.lower():
                return blob[off:off + inner_size]
    raise AssertionError('%s missing %s' % (path, filename))


def load_levels(data):
    levels = {}
    for level in ('islc1', 'islc2', 'islcave1', 'islgnome', 'hub'):
        path = os.path.join(data, level.upper() + '.GOB')
        levels[level] = {
            'script': lump(path, 'script.scr'),
            'mermaid': lump(path, 'mermaid.dbin') if level in ('islc1', 'islc2') else None,
            'racer': lump(path, 'g_racer.dbin') if level == 'islc1' else None,
        }
    return levels


def show_imm(pool, publics, value):
    """Integers stay integers. A pool string is used at offset 0 only when that
    string is a public entry, which is how callScript names steppedOnTrigger."""
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
    found = []
    pending = []
    i = 0
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


def prepare(rig, image, seed, shells=0):
    error, bound = rig.place(image + bytes(256))
    if (error, bound) != (0, 0):
        raise AssertionError((error, bound))
    rig.responder.shells = shells
    rig.calls = []
    mem = rig.emu.mem
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
    for slot in range(4):
        base = PLAYERS + slot * REC
        mem.write(base + MISSION, bytes([SENTINEL]) * MISSION_BYTES)
        mem.write(base + QUEST, bytes([FILL]) * (8 * 0x40))
        mem.w32(base + QUEST_COUNT, 0 if slot == 0 else 0x5A5A5A5A)
    return mem


def run_entry(rig, name):
    pointer = rig.emu.alloc(64)
    rig.emu.mem.write(pointer, name.encode('ascii') + b'\0')
    rig.calls = []
    rig.emu.calls.clear()
    return N.s32(rig.call(N.A['script_runByName'], pointer, max_steps=4000000))


def called(rig, addr):
    return sum(1 for record in rig.emu.calls if record.target == addr)


def variables(mem):
    found = []
    where = N.N.G_QUEST_VARS
    while mem.u8(where) != 0 and len(found) < 16:
        name = mem.cstr(where, 64)
        found.append((name, mem.s8(where + len(name) + 1)))
        where += len(name) + 2
    return found


def mission(mem, slot, index):
    return mem.u8(PLAYERS + slot * REC + MISSION + index)


def stubs(rig):
    return [name for name, _args in rig.calls]


def plant_var(rig, name, value):
    pointer = rig.emu.alloc(64)
    rig.emu.mem.write(pointer, name.encode('ascii') + b'\0')
    rig.call(0x1ED854, pointer, value)


def plant_quest(rig, title, body):
    first = rig.emu.alloc(64)
    second = rig.emu.alloc(64)
    rig.emu.mem.write(first, title.encode('latin1') + b'\0')
    rig.emu.mem.write(second, body.encode('latin1') + b'\0')
    rig.call(0x1D386C, first, second)


def require(cond, detail):
    if not cond:
        raise AssertionError(detail)


def check_level_start(rig, image, seed, level, post):
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'start') == 0, level + ' start')
    require(mission(mem, 0, 3) == R.available_byte(SENTINEL, 1), (level, 'available'))
    require(all(mission(mem, slot, 3) == SENTINEL for slot in (1, 2, 3)), level + ' other slots')
    require(all(mission(mem, slot, 4) == SENTINEL for slot in range(4)), level + ' mission 4')
    got = dict(variables(mem))
    require(got.get('startedmission3') == 1 and got.get('currentmission') == 3,
            (level, variables(mem)))
    require(mem.u32(N.N.G_RAND_SEED) == seed, level + ' seed')
    require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'PENDING-SENTINEL', level + ' pending')
    if post:
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', level + ' post')
    else:
        require(mem.u8(N.N.G_POST_ACTION) == 0, level + ' no post')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, level + ' quest')
    return 8


def check_absorb(rig, image, seed):
    _publics, found, _pool = calls_in(image)
    require(arg_at(found, 0x4DC, 0) == 'islcave', 'script cut argument')
    mem = prepare(rig, image, seed)
    # No level name is planted, so cutScene's lump argument is ".lmp".
    require(mem.cstr(N.N.G_LEVEL_NAME, 16) == '', 'level name')
    run_entry(rig, 'start')
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'post was not queued')
    rig.calls = []
    rig.emu.calls.clear()
    rig.call(N.A['script_runPostAction'], max_steps=4000000)
    require(mem.u8(N.N.G_POST_ACTION) == 0, 'post name was kept')
    # getv of a missing sawislc is 0, then the entry negates that, so the
    # first visit requests the cut and stores 1. The next visit skips it.
    # res_find returns 0, and cut_start records the ".cut" name.
    require(rig.calls == [
        ('res_find', (b'.lmp', b'islcave.cut')),
        ('cut_start', (0, b'islcave.cut')),
    ], rig.calls)
    require(dict(variables(mem))['sawislc'] == 1, variables(mem))
    run_entry(rig, 'absorb')
    require(rig.calls == [], stubs(rig))
    require(dict(variables(mem))['sawislc'] == 1, variables(mem))
    return 6


def check_quest_action(rig, image, seed, found):
    title = arg_at(found, 0xB70, 0)
    body = arg_at(found, 0xB70, 1)
    mem = prepare(rig, image, seed)
    require(run_entry(rig, 'setvdea6') == 0, 'quest action')
    require(dict(variables(mem))['wa_metkerriel'] == 1, variables(mem))
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'count')
    require(mem.cstr(PLAYERS + QUEST, 32) == title, 'title bytes diverged from the script argument')
    require(mem.cstr(PLAYERS + QUEST + 0x20, 32) == body, 'body bytes diverged from the script argument')
    require(mem.read(PLAYERS + REC + QUEST, 8 * 0x40) == bytes([FILL]) * (8 * 0x40),
            'later player quest bytes changed')
    require(mem.u32(PLAYERS + REC + QUEST_COUNT) == 0x5A5A5A5A, 'later count')
    require(all(mission(mem, slot, index) == SENTINEL
                for slot in range(4) for index in (3, 4)), 'quest action moved a mission bit')
    return 7


def check_predicates(rig, images, seed):
    checks = 0
    image = images['islc1']['script']
    for name, value, expect in (
            ('if4257', None, 1), ('if4257', 1, 0),
            ('ifa305', None, 0), ('ifa305', 1, 1)):
        mem = prepare(rig, image, seed)
        if value is not None:
            plant_var(rig, 'wa_metKerriel', value)
        got = run_entry(rig, name)
        require(got == expect, (name, value, got))
        checks += 1
    image = images['islc2']['script']
    # One player, so playerHasItem's sum is this single stub return.
    # 0 stays 0. 1 and 2 are nonzero and both return 1.
    for shells, expect in ((0, 0), (1, 1), (2, 1)):
        mem = prepare(rig, image, seed, shells)
        got = run_entry(rig, 'iffbe4')
        require(got == expect, ('shell', shells, got, stubs(rig)))
        require(rig.calls == [('inventory_countItemByName', (b'shell', 0))], rig.calls)
        checks += 1
    for name, value, expect in (
            ('if9be1', None, 0), ('if9be1', 1, 1),
            ('iffa37', None, 1), ('iffa37', 1, 0)):
        mem = prepare(rig, image, seed)
        if value is not None:
            plant_var(rig, 'wa_gotBlessed', value)
        got = run_entry(rig, name)
        require(got == expect, (name, value, got))
        checks += 1
    return checks


def check_completion(rig, image, seed, found):
    title = arg_at(found, 0x2E0, 0)
    mem = prepare(rig, image, seed)
    plant_quest(rig, title, 'plant-body')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1, 'plant')
    # Available on the first record only. Completion must set bit 1 on all four.
    mem.w8(PLAYERS + MISSION + 3, R.available_byte(SENTINEL, 1))
    require(run_entry(rig, 'callScri8a40') == 0, 'completion action')
    require(mission(mem, 0, 3) == R.complete_byte(R.available_byte(SENTINEL, 1), -1),
            hex(mission(mem, 0, 3)))
    require(all(mission(mem, slot, 3) == R.complete_byte(SENTINEL, -1) for slot in (1, 2, 3)),
            [hex(mission(mem, slot, 3)) for slot in range(4)])
    require(all(mission(mem, slot, 4) == SENTINEL for slot in range(4)), 'mission 4 moved')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'quest remained')
    require(dict(variables(mem))['wa_gotblessed'] == 1, variables(mem))
    require('hud_showHelpMessage' in stubs(rig), stubs(rig))
    require('inventory_findItemBySubstring' in stubs(rig), stubs(rig))
    require('sound_playOnObject' in stubs(rig), stubs(rig))
    require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
    return 9


def check_cave_grant(rig, image, seed):
    mem = prepare(rig, image, seed)
    publics, found, pool = calls_in(image)
    require(pool.get(0) == 'steppedOnTrigger', 'callScript argument was not that entry')
    require(publics['callScri7351'] == 0, 'trigger wrapper')
    require(run_entry(rig, 'callScri7351') == 0, 'cave trigger')
    require(all(mission(mem, slot, 3) == R.complete_byte(SENTINEL, -1) for slot in range(4)),
            [hex(mission(mem, slot, 3)) for slot in range(4)])
    require(all(mission(mem, slot, 4) == SENTINEL for slot in range(4)), 'mission 4')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 0, 'cave grant edited the quest list')
    require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, 'cave grant wrote a quest')
    require('hud_showHelpMessage' in stubs(rig), stubs(rig))
    require('inventory_findItemBySubstring' not in stubs(rig), stubs(rig))
    return 8


def calls_of_entry(found, publics, name):
    start = publics[name]
    later = [off for off in publics.values() if off > start]
    end = min(later) if later else 1 << 30
    return [(native, args) for off, native, args in found if start <= off < end]


def check_racer(blob, publics, found):
    """islc1 g_racer.dbin node 1 names wrappers. Each wrapper only posts one travel."""
    rows = dbin_rows(blob)
    require(len(rows) == 2, len(rows))
    actions = [(action, target) for _text, action, target in rows[1][1]]
    require(actions == [
        ('postActifb1b', -1),
        ('postActi6592', -1),
        ('postActi928c', -1),
        ('postActifd9a', -1),
    ], actions)
    wrappers = (
        ('postActifb1b', 0x1FC, 'solitary'),
        ('postActi6592', 0x240, 'lostHope'),
        ('postActi928c', 0x284, 'regret'),
        ('postActifd9a', 0x2C8, 'gnome'),
    )
    for name, off, posts in wrappers:
        require(publics[name] == off, (name, hex(publics[name])))
        require(calls_of_entry(found, publics, name) == [('postAction', (posts,))],
                (name, calls_of_entry(found, publics, name)))
    return 5


def check_travel(rig, image, seed):
    routes = (
        ('lostHope', 'islsm2a'),
        ('solitary', 'islsm1'),
        ('regret', 'islsm3a'),
        ('gnome', 'islgnome'),
        ('kerriel', 'islc1'),
    )
    checks = 0
    for entry, level in routes:
        mem = prepare(rig, image, seed)
        require(run_entry(rig, entry) == 0, entry)
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == level, (entry, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'boat', (entry, mem.cstr(N.N.G_ENTRANCE_NAME, 32)))
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, (entry, mem.u8(N.N.G_PENDING_ORIENT)))
        require(all(mission(mem, 0, index) == SENTINEL for index in (3, 4)), entry + ' mission')
        checks += 1
    return checks


def check_entrances(rig, image, seed):
    # startedQuest, finishedQuest, failQuest's killMonster calls, destination.
    # None leaves the variable absent. getv creates it at 0.
    # startedQuest, finishedQuest, and how many times killMonster 0x144a84 runs
    # before the same entry still requests islc2. None leaves the name absent.
    matrix = (
        (None, None, 0),
        (1, None, 8),
        (1, 0, 8),
        (1, 1, 0),
    )
    checks = 0
    for started, finished, kills in matrix:
        for entry, door in (('entrance1', 'one'), ('entrance2', 'two'), ('entrance3', 'three')):
            mem = prepare(rig, image, seed)
            if started is not None:
                plant_var(rig, 'startedQuest', started)
            if finished is not None:
                plant_var(rig, 'finishedQuest', finished)
            require(run_entry(rig, entry) == 0, (entry, started, finished))
            require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'islc2',
                    (entry, started, finished, mem.cstr(N.N.G_PENDING_LEVEL, 32)))
            require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == door, entry)
            require(called(rig, 0x144A84) == kills,
                    (entry, started, finished, called(rig, 0x144A84)))
            checks += 1
    return checks


def check_hub_mission4(rig, image, seed):
    checks = 0
    for entry, quest in (
            ('setMissi5f9f', 0), ('setMissidce3', 0),
            ('setMissie8e9', 1), ('setMissic4', 1)):
        mem = prepare(rig, image, seed)
        require(run_entry(rig, entry) == 0, entry)
        require(mission(mem, 0, 4) == R.available_byte(SENTINEL, 1), (entry, hex(mission(mem, 0, 4))))
        require(all(mission(mem, slot, 4) == SENTINEL for slot in (1, 2, 3)), entry)
        require(all(mission(mem, slot, 3) == SENTINEL for slot in range(4)), entry + ' mission 3')
        require(mem.u32(PLAYERS + QUEST_COUNT) == quest, (entry, mem.u32(PLAYERS + QUEST_COUNT)))
        if quest:
            require(mem.u8(PLAYERS + QUEST) != FILL, entry + ' empty title')
        else:
            require(mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40, entry + ' quest bytes')
        checks += 1
    return checks


def check_dialogs(levels):
    first = dbin_rows(levels['islc1']['mermaid'])
    second = dbin_rows(levels['islc2']['mermaid'])
    require(len(first) == 3 and len(second) == 3, 'node count')
    require(first[0][0] == 'if4257' and first[1][0] == 'if4257' and first[2][0] == 'ifa305',
            [row[0] for row in first])
    require(first[0][1] == [('', '', 1)], first[0][1])
    require(first[1][1] == [('', 'setvdea6', 2)], first[1][1])
    require(first[2][1] == [('', '', -1)], first[2][1])
    require(second[0] == ('iffbe4', [('', 'callScri8a40', -1)]), second[0])
    require(second[1][0] == 'if9be1' and second[2][0] == 'iffa37', [row[0] for row in second])
    require(second[1][1] == [('', '', -1)] and second[2][1] == [('', '', -1)], 'later nodes')
    return 7


def check_seed(rig, levels, seed):
    checks = check_dialogs(levels)
    islc1 = levels['islc1']['script']
    publics, found, _pool = calls_in(islc1)
    checks += check_level_start(rig, islc1, seed, 'islc1', True)
    checks += check_absorb(rig, islc1, seed)
    checks += check_quest_action(rig, islc1, seed, found)
    checks += check_predicates(rig, levels, seed)
    checks += check_travel(rig, islc1, seed)
    checks += check_racer(levels['islc1']['racer'], publics, found)
    islc2 = levels['islc2']['script']
    _publics, found, _pool = calls_in(islc2)
    checks += check_completion(rig, islc2, seed, found)
    cave = levels['islcave1']['script']
    checks += check_level_start(rig, cave, seed, 'islcave1', False)
    checks += check_cave_grant(rig, cave, seed)
    checks += check_entrances(rig, levels['islgnome']['script'], seed)
    checks += check_hub_mission4(rig, levels['hub']['script'], seed)
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
        print('PASS seed %d: %d mission-3 checks' % (seed, count))


if __name__ == '__main__':
    main()
