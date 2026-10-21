#!/usr/bin/env python3
"""difftest_save.py - compare tools/ref_save.py with the original save functions.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.

  python3 tools/difftest_save.py [path/to/SLUS_209.73]

The original functions run in tools/ee_emu.py on state this script builds. The same
state goes through the model. Nothing here is a save from a disc or a memory card.
"""

import os
import sys

# tools/dis.py is not the stdlib module. inspect (via dataclasses) needs the real one,
# and a script in tools/ puts this directory first on the path.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry or '.') != _HERE]
import dis  # noqa: E402,F401
sys.path.insert(0, _HERE)

import hashlib  # noqa: E402
import random  # noqa: E402
import struct  # noqa: E402

import ref_save as S  # noqa: E402
from ee_emu import EE, EmuError, MemoryFault

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAVE_BUILD = 0x221914
SAVE_LOAD = 0x221D60
SAVE_STORE = 0x21777C
SAVE_CLEAR = 0x21F144
SAVE_COUNT = 0x218520
CHECKSUM = 0x1BDC98
AUTOMAP = 0x16865C
CONFIG = 0x1E6238
MUSIC = 0x215E78
ENCODE = 0x107EA4
DECODE = 0x107EC0
PTR_TO_INDEX = 0x216BF8
INDEX_TO_PTR = 0x216E10

G_SAVE = 0x895580
G_PLAYERS = 0x4D8AF0
G_SAVED = 0x879EC0
G_LEVEL = 0x41B721
G_SUB = 0x41B771
G_PENDING = 0x41B6D0
G_MARKER = 0x41B720
G_COMPLETE = 0x4F85C5
G_TIME = 0x88D414
G_ACT = 0x88D3D4
G_DIFF = 0x4F719C
G_NUM = 0x4D8AE0
G_MINI = 0x4F8400
G_CAM_PTR = 0x4F8450
G_CAM_POS = 0x44F038
G_CAM_MAT = 0x44F110
G_JUMP_N = 0x8E3C30
G_JUMP_D = 0x8E3A50
G_QUEST = 0x86DA80
G_COUNTS = 0x4F8E10
G_TABLES = 0x4F8E48
G_ACTS = 0x4F8E7C
G_CARD = 0x88D3A0
G_FLAG = 0x44FE08
G_MAP = 0x4044F0
G_ALIVE = 0x4F841C
G_LOADED = 0x8E1AD6
G_COUNTDOWN = 0x88D40C
G_SIDE = 0x8E1A98
G_FACE = 0x4F8410
G_SPAWN = 0x4F70D0
G_CONFIG = 0x4F8F38
G_SCHEME = 0x41B69C
G_BLOCK = 0x4F8F2A
G_LATCH = 0x4F9234
G_SHARE = 0x4F85B4
G_AUTO = 0x4044D0

CAM_STRUCT = 0x01200000
OBJ_BASE = 0x01100000
RESULTS = []


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        candidates.append(env)
    candidates += [os.path.join(ROOT, 'local', 'SLUS_209.73'),
                   os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %-28s %s' % ('PASS' if ok else 'FAIL', name, detail))
    sys.stdout.flush()


def bits(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def cstr(ee, addr, limit=80):
    raw = ee.mem.read(addr, limit)
    end = raw.find(b'\x00')
    if end < 0:
        return raw
    return raw[:end]


def locate(offset):
    if offset < 0x14:
        return 'level name'
    if offset < 0x64:
        return 'level subname'
    if offset < 0x70:
        return 'header counts'
    if offset < 0x134:
        return 'camera'
    if offset < 0x318:
        return 'jump gates'
    if offset < S.PLAYERS_AT:
        return 'minimap or player count'
    if offset < S.QUESTS_AT:
        slot = (offset - S.PLAYERS_AT) // S.BLOCK_SIZE
        return 'player block %d' % slot
    if offset < S.DIRECTORY_AT:
        return 'quest variables'
    if offset < S.DATA_AT:
        return 'level directory'
    return 'level data +0x%x' % (offset - S.DATA_AT)


def compare(name, got, want):
    if got == want:
        report(name, True, '%d bytes' % len(got))
        return True
    n = min(len(got), len(want))
    at = next((i for i in range(n) if got[i] != want[i]), n)
    window = '%02x/%02x' % (got[at] if at < len(got) else 0, want[at] if at < len(want) else 0)
    report(name, False, 'first mismatch at 0x%x (%s) byte %s, lengths %d/%d' % (
        at, locate(at), window, len(got), len(want)))
    return False


def boot(elf):
    ee = EE(elf)
    ee.record_writes = False
    ee.record_calls = False
    ee.mem.auto_map = True
    return ee


def call(ee, addr, *args, steps=4000000):
    return ee.call(addr, *args, max_steps=steps) & 0xFFFFFFFF


def zero(ee, addr, size):
    ee.mem.write(addr, bytes(size))


def write_cstr(ee, addr, text):
    ee.mem.write(addr, text.encode('latin-1') + b'\x00')


def install_acts(ee, acts):
    ee.mem.w32(G_ACTS, len(acts))
    for index, levels in enumerate(acts):
        ee.mem.w32(G_COUNTS + 4 * index, len(levels))
        table = 0x01300000 + index * 0x200
        ee.mem.w32(G_TABLES + 4 * index, table)
        for row, (name, size) in enumerate(levels):
            text = 0x01310000 + index * 0x200 + row * 0x20
            write_cstr(ee, text, name)
            ee.mem.w32(table + row * 8, text)
            ee.mem.w16(table + row * 8 + 4, size)


def install_camera(ee, position, matrix, halves, words, floats, tail):
    ee.mem.w32(G_CAM_PTR, CAM_STRUCT)
    for index, value in enumerate(position):
        ee.mem.w32(G_CAM_POS + 4 * index, bits(value))
    for index, value in enumerate(matrix):
        ee.mem.w32(G_CAM_MAT + 4 * index, bits(value) if isinstance(value, float) else value & 0xFFFFFFFF)
    ee.mem.w16(CAM_STRUCT + 0x68, halves[0])
    ee.mem.w16(CAM_STRUCT + 0x6A, halves[1])
    ee.mem.w32(CAM_STRUCT + 0x54, words[0])
    ee.mem.w32(CAM_STRUCT + 0x58, words[1])
    ee.mem.w32(CAM_STRUCT + 0x90, bits(floats[0]))
    ee.mem.w32(CAM_STRUCT + 0xD4, bits(floats[1]))
    ee.mem.w32(CAM_STRUCT + 0x8C, bits(floats[2]))
    ee.mem.write(CAM_STRUCT + 0x100, tail)


def install_player(ee, slot, record, facing, position):
    base = G_PLAYERS + slot * S.RECORD_SIZE
    ee.mem.write(base, record)
    obj = OBJ_BASE + slot * 0x200
    if struct.unpack_from('<I', record, 0x43D8)[0] == obj:
        ee.mem.w8(obj + 0x38, facing & 0xFF)
        ee.mem.w8(obj + 0x39, (facing >> 8) & 0xFF)
        for index, value in enumerate(position):
            ee.mem.w32(obj + 0x10 + 4 * index, bits(value))


def make_record(name, gold, live_base, obj, define=3):
    rec = bytearray(S.RECORD_SIZE)
    raw = name.encode('latin-1')
    rec[:len(raw)] = raw
    rec[0x20:0x24] = bytes((4, 1, 2, 3))
    struct.pack_into('<ii', rec, 0x50, 1, 6)
    rec[0x58] = 3
    rec[0x59] = 4
    struct.pack_into('<i', rec, 0x5C, 5000)
    struct.pack_into('<4i', rec, 0x78, 46, 37, 24, 28)
    struct.pack_into('<i', rec, 0xE4, gold)
    struct.pack_into('<i', rec, 0xE8, 2)
    rec[0x90:0xA8] = bytes(range(24))
    struct.pack_into('<f', rec, 0xC0, 10.0)
    struct.pack_into('<f', rec, 0xC4, 20.0)
    struct.pack_into('<f', rec, 0xC8, 1.5)
    rec[0x3748] = 0x5A
    rec[0x3749] = 0xA5
    struct.pack_into('<i', rec, S.BAG_COUNT_AT, 1)
    struct.pack_into('<i', rec, S.BAG_ITEM_AT, S.definition_pointer(define))
    struct.pack_into('<h', rec, S.BAG_ITEM_AT + 4, 4)
    struct.pack_into('<i', rec, 0x43D8, obj)
    struct.pack_into('<i', rec, 0x43F0, live_base + S.BAG_ITEM_AT)
    struct.pack_into('<i', rec, 0x4434, live_base + S.BAG_ITEM_AT)
    struct.pack_into('<hh', rec, 0x4B08, 7, 2)
    struct.pack_into('<h', rec, 0x4B0C, -1)
    return bytes(rec)


def pack_quests(pairs):
    out = bytearray()
    for name, value in pairs:
        out += name.encode('latin-1') + b'\x00'
        out.append(value & 0xFF)
    out.append(0)
    return bytes(out)


def prepare(ee, inputs, position, matrix, tail, quests, acts, grid=b''):
    zero(ee, G_SAVE, S.FILE_SIZE)
    zero(ee, G_PLAYERS, S.PLAYER_SLOTS * S.RECORD_SIZE)
    zero(ee, G_SAVED, S.PLAYER_SLOTS * S.RECORD_SIZE)
    zero(ee, G_QUEST, 0x400)
    zero(ee, G_PENDING, 0xC0)
    zero(ee, G_SIDE, 0x40)
    if inputs.previous is not None:
        ee.mem.write(G_SAVE, inputs.previous)
    write_cstr(ee, G_LEVEL, inputs.level_name)
    write_cstr(ee, G_SUB, inputs.subname)
    ee.mem.w8(G_COMPLETE, 1 if inputs.game_complete else 0)
    ee.mem.w32(G_TIME, inputs.play_time)
    ee.mem.w32(G_ACT, inputs.act & 0xFFFFFFFF)
    ee.mem.w8(G_DIFF, inputs.difficulty & 0xFF)
    ee.mem.w32(G_NUM, inputs.num_players & 0xFFFFFFFF)
    ee.mem.w32(G_MINI, inputs.minimap & 0xFFFFFFFF)
    ee.mem.w32(G_CARD, inputs.memcard_state & 0xFFFFFFFF)
    ee.mem.w32(G_FLAG, inputs.block_flag & 0xFFFFFFFF)
    ee.mem.w32(G_ALIVE, inputs.alive_first & 0xFFFFFFFF)
    ee.mem.w32(G_SHARE, 0)
    ee.mem.w8(G_JUMP_N, inputs.jump_count & 0xFF)
    ee.mem.write(G_JUMP_D, inputs.jump_dest or bytes(S.JUMP_DEST_SIZE))
    ee.mem.write(G_QUEST, pack_quests(quests))
    install_acts(ee, acts)
    install_camera(ee, position, matrix, (1, 2), (3, 4), (0.25, 0.5, 0.75), tail)
    if grid:
        ee.mem.write(G_MAP, grid)
    for slot, player in enumerate(inputs.players):
        install_player(ee, slot, player.record, player.facing, player.position)


def camera_parts():
    position = (10.0, 20.0, 30.0)
    matrix = [float(i) for i in range(16)]
    tail = bytes(range(0x60))
    image = S.pack_camera(position, matrix, 1, 2, 3, 4, (0.25, 0.5, 0.75), tail)
    return position, matrix, tail, image


def run_build(ee, inputs, steps=6000000):
    call(ee, SAVE_BUILD, inputs.save_arg & 0xFF, 1 if inputs.one_player else 0, steps=steps)
    return ee.mem.read(G_SAVE, S.FILE_SIZE)


def test_checksum(elf):
    ee = boot(elf)
    record = bytes(S.RECORD_SIZE)
    ee.mem.write(0x1400000, record)
    got = call(ee, CHECKSUM, 0, 0x1400000)
    want = S.player_checksum(0, 0x1400000, record)
    report('checksum.zero', got == want, 'original 0x%08x model 0x%08x' % (got, want))
    rng = random.Random(20973)
    mismatches = 0
    cases = 0
    for index in range(12):
        blob = bytes(rng.getrandbits(8) for _ in range(S.RECORD_SIZE))
        addr = 0x1400000 + index * 0x5000
        ee.mem.write(addr, blob)
        for slot in range(4):
            cases += 1
            original = call(ee, CHECKSUM, slot, addr)
            model = S.player_checksum(slot, addr, blob)
            if original != model:
                mismatches += 1
                if mismatches == 1:
                    detail = 'slot %d addr 0x%x original 0x%08x model 0x%08x' % (slot, addr, original, model)
    report('checksum.records', mismatches == 0,
           '%d cases' % cases if mismatches == 0 else detail)


def test_automap(elf):
    ee = boot(elf)
    grid = bytearray(S.AUTOMAP_GRID_SPAN)
    grid[1] = 0xF0
    grid[5] = 0x07
    grid[9] = 0x10
    grid[13] = 0xA0
    grid[0x361] = 0x20
    grid[0x365] = 0x30
    rng = random.Random(7)
    for _ in range(40):
        grid[rng.randrange(S.AUTOMAP_GRID_SPAN)] = rng.randrange(256)
    ee.mem.write(G_MAP, bytes(grid))
    dest = 0x1500000
    call(ee, AUTOMAP, dest)
    compare('automap.pack', ee.mem.read(dest, S.AUTOMAP_SIZE), S.pack_automap(grid))


def test_items(elf):
    ee = boot(elf)
    addr = 0x1600000
    ee.mem.w32(addr, S.definition_pointer(3))
    call(ee, ENCODE, addr)
    encoded = ee.mem.s32(addr)
    ok = encoded == 3
    call(ee, DECODE, addr)
    ok = ok and ee.mem.u32(addr) == S.definition_pointer(3)
    ee.mem.w32(addr, 0)
    call(ee, ENCODE, addr)
    ok = ok and ee.mem.s32(addr) == S.definition_index(0)
    base = 0x1610000
    record = bytearray(S.RECORD_SIZE)
    struct.pack_into('<i', record, S.BAG_COUNT_AT, 1)
    ee.mem.write(base, bytes(record))
    original = call(ee, PTR_TO_INDEX, base + S.BAG_ITEM_AT, base)
    missing = call(ee, PTR_TO_INDEX, 0, base)
    restored = call(ee, INDEX_TO_PTR, 0, base)
    absent = call(ee, INDEX_TO_PTR, -1, base)
    ok = ok and original == 0 and missing == 0xFFFFFFFF and restored == base + S.BAG_ITEM_AT and absent == 0
    report('items.convert', ok, 'encode, decode, bag index 0 and the null index')


def test_config(elf):
    ee = boot(elf)
    ee.stub(MUSIC, ret=0, name='music_applyVolume')
    zero(ee, G_CONFIG, S.CONFIG_SIZE)
    ee.mem.w8(G_SCHEME, 1)
    call(ee, CONFIG, -1)
    image = ee.mem.read(G_CONFIG, S.CONFIG_SIZE)
    first = compare('config.scheme1', image, S.config_set_defaults(-1, 1))
    zero(ee, G_CONFIG, S.CONFIG_SIZE)
    ee.mem.w8(G_SCHEME, 0)
    call(ee, CONFIG, -1)
    compare('config.scheme0', ee.mem.read(G_CONFIG, S.CONFIG_SIZE), S.config_set_defaults(-1, 0))
    if first:
        parsed = S.parse_config(image)
        report('config.fields', parsed.music == 0.5 and parsed.buttons[0][0] == 0x40,
               'music 0.5, first mask 0x%x' % parsed.buttons[0][0])
    dirty = bytes([0xAB]) * S.CONFIG_SIZE
    ee.mem.write(G_CONFIG, dirty)
    ee.mem.w8(G_SCHEME, 2)
    call(ee, CONFIG, 1)
    compare('config.one_row', ee.mem.read(G_CONFIG, S.CONFIG_SIZE),
            S.config_set_defaults(1, 2, dirty))


def _players(names, golds):
    players = []
    for slot, (name, gold) in enumerate(zip(names, golds)):
        base = G_PLAYERS + slot * S.RECORD_SIZE
        obj = OBJ_BASE + slot * 0x200
        record = make_record(name, gold, base, obj)
        players.append(S.LiveCharacter(record, base, facing=0x1234 + slot, position=(1.0 + slot, 2.0, 3.0)))
    return tuple(players)


def _common(level='crypt', sub='', complete=False, players=1, one=False, quests=(),
            acts=None, previous=None, card=0, flag=0, alive=-1, grid=b''):
    if acts is None:
        acts = ((('crypt', 0x2000),),)
    position, matrix, tail, camera = camera_parts()
    dest = bytes([0xAB, 0xCD]) + bytes(S.JUMP_DEST_SIZE - 2)
    names = ('Aria', 'Bram', 'Cedric', 'Dain')[:players]
    inputs = S.SlotInputs(
        level_name=level, subname=sub, game_complete=complete, play_time=12345,
        difficulty=2, save_arg=7, act=0, one_player=one, num_players=players,
        players=_players(names, (777, 50, 1, 1)[:players]) if players else (),
        alive_first=alive, camera=camera, jump_count=2, jump_dest=dest, minimap=3,
        quests=tuple(quests), acts=acts, memcard_state=card, block_flag=flag,
        automap_grid=grid, previous=previous)
    return inputs, position, matrix, tail


def build_case(elf, name, **kwargs):
    steps = kwargs.pop('steps', 2000000)
    try:
        ee = boot(elf)
        inputs, position, matrix, tail = _common(**kwargs)
        prepare(ee, inputs, position, matrix, tail, inputs.quests, inputs.acts, inputs.automap_grid)
        original = run_build(ee, inputs, steps=steps)
        model = S.build_slot(inputs)
        return compare(name, original, model), ee, inputs, original
    except (EmuError, MemoryFault) as error:
        report(name, False, '%s: %s' % (type(error).__name__, error))
        return False, None, None, None


def test_builds(elf):
    grid = bytearray(S.AUTOMAP_GRID_SPAN)
    grid[1] = 0xF0
    grid[5] = 0x17
    grid[0x361] = 0x80
    build_case(elf, 'build.crypt', quests=(('opened', 7), ('door', -2)), grid=bytes(grid),
               players=2, steps=6000000)
    build_case(elf, 'build.unknown_level', level='nope', previous=bytes([0x5A]) * S.FILE_SIZE)
    previous = bytearray([0x11]) * S.FILE_SIZE
    build_case(elf, 'build.tail_left_in_place', card=4, previous=bytes(previous),
               quests=(('opened', 7),))
    previous = bytearray(S.FILE_SIZE)
    previous[13:0x14] = b'\x11' * 7
    build_case(elf, 'build.game_complete', complete=True, previous=bytes(previous))
    build_case(elf, 'build.one_player', players=2, one=True, card=4)
    build_case(elf, 'build.card_busy', card=4)
    build_case(elf, 'build.flag_blocks_store', flag=0x800)
    previous = bytearray(S.FILE_SIZE)
    previous[S.DATA_AT:S.DATA_AT + 4] = b'\x22\x22\x22\x22'
    S._write_cstr(previous, S.DIRECTORY_AT, 'old', 0x14)
    struct.pack_into('<I', previous, S.DIRECTORY_AT + 0x14, 0x40000)
    build_case(elf, 'build.level_does_not_fit', previous=bytes(previous))
    bare_base = G_PLAYERS
    other_base = G_PLAYERS + S.RECORD_SIZE
    bare = S.LiveCharacter(make_record('Aria', 777, bare_base, 0), bare_base, facing=1, position=(9, 9, 9))
    other = S.LiveCharacter(make_record('Bram', 50, other_base, OBJ_BASE + 0x200), other_base,
                            facing=0x2222, position=(8.0, 7.0, 6.0))
    ee = boot(elf)
    position, matrix, tail, camera = camera_parts()
    inputs = S.SlotInputs(
        level_name='crypt', acts=((('crypt', 0x2000),),), num_players=2, players=(bare, other),
        alive_first=-1, camera=camera, jump_count=0, jump_dest=bytes(S.JUMP_DEST_SIZE),
        play_time=1, difficulty=1, save_arg=1, memcard_state=4)
    prepare(ee, inputs, position, matrix, tail, (), inputs.acts)
    compare('build.pose_fallback', run_build(ee, inputs), S.build_slot(inputs))


def test_load(elf):
    ee = boot(elf)
    inputs, position, matrix, tail = _common(quests=(('opened', 7), ('door', -2)), players=2,
                                              grid=b'\x00' * 8)
    prepare(ee, inputs, position, matrix, tail, inputs.quests, inputs.acts, b'')
    original = run_build(ee, inputs, steps=6000000)
    if original != S.build_slot(inputs):
        report('load.round_trip', False, 'the built image already differs; load was not compared')
        return
    call(ee, SAVE_LOAD, steps=2000000)
    problems = []
    if cstr(ee, G_PLAYERS) != b'Aria':
        problems.append('name')
    if ee.mem.s32(G_PLAYERS + 0xE4) != 777:
        problems.append('gold')
    if ee.mem.s32(G_PLAYERS + 0x5C) != 5000:
        problems.append('xp')
    if ee.mem.u32(G_PLAYERS + S.BAG_ITEM_AT) != S.definition_pointer(3):
        problems.append('definition')
    if ee.mem.u32(G_PLAYERS + 0x43F0) != G_PLAYERS + S.BAG_ITEM_AT:
        problems.append('equipped')
    if ee.mem.u32(G_PLAYERS + 0x43D8) != 0:
        problems.append('object')
    if ee.mem.s32(G_NUM) != 2 or ee.mem.s32(G_ACT) != 0 or ee.mem.u8(G_DIFF) != 2:
        problems.append('header')
    if ee.mem.u32(G_TIME) != 12345 or ee.mem.u8(G_LOADED) != 1 or ee.mem.u32(G_COUNTDOWN) != 99:
        problems.append('time or flags')
    if cstr(ee, G_PENDING) != b'crypt' or cstr(ee, G_SIDE) != b'crypt' or ee.mem.u8(G_MARKER) != 0xFD:
        problems.append('pending level')
    if ee.mem.u16(G_FACE) != 0x1234:
        problems.append('facing')
    spawn = tuple(struct.unpack('<f', ee.mem.read(G_SPAWN + 4 * i, 4))[0] for i in range(3))
    if spawn != (1.0, 2.0, 3.0):
        problems.append('spawn %s' % (spawn,))
    saved = original[S.PLAYERS_AT + S.POSE_SIZE:S.PLAYERS_AT + S.BLOCK_SIZE]
    loaded = S.decode_loaded_record(saved, G_PLAYERS)
    live = ee.mem.read(G_PLAYERS, S.RECORD_SIZE)
    if live != loaded:
        at = next(i for i in range(S.RECORD_SIZE) if live[i] != loaded[i])
        problems.append('record +0x%x' % at)
    # The second quest byte is the value after its name and NUL.
    if ee.mem.s8(G_QUEST + len('opened') + 1) != 7 or ee.mem.s8(G_QUEST + len('opened') + 1 + 1 + len('door') + 1) != -2:
        problems.append('quests')
    report('load.round_trip', not problems, 'restored character' if not problems else ', '.join(problems))

    ee = boot(elf)
    inputs, position, matrix, tail = _common(
        level='hub', sub='west', acts=((('town', 0x1800), ('hub', 0x1000)),))
    prepare(ee, inputs, position, matrix, tail, (), inputs.acts)
    original = run_build(ee, inputs, steps=6000000)
    compare('build.hub_row0', original, S.build_slot(inputs))
    call(ee, SAVE_LOAD)
    pending = cstr(ee, G_PENDING)
    side = cstr(ee, G_SIDE)
    report('load.subname', pending == b'hub_west' and side == b'hub_west',
           'pending %r side %r' % (pending, side))

    ee = boot(elf)
    inputs, position, matrix, tail = _common(card=4)
    prepare(ee, inputs, position, matrix, tail, (), inputs.acts)
    run_build(ee, inputs)
    ee.mem.w16(G_SAVE + 0x68, 0x1111)
    call(ee, SAVE_LOAD)
    report('load.ignores_record_size',
           cstr(ee, G_PLAYERS) == b'Aria' and ee.mem.s32(G_PLAYERS + 0xE4) == 777,
           'name %r gold %s' % (cstr(ee, G_PLAYERS), ee.mem.s32(G_PLAYERS + 0xE4)))


def test_count_and_clear(elf):
    ee = boot(elf)
    inputs, position, matrix, tail = _common(players=2, one=True, card=4)
    prepare(ee, inputs, position, matrix, tail, (), inputs.acts)
    run_build(ee, inputs)
    call(ee, SAVE_COUNT, 1)
    image = ee.mem.read(G_SAVE, S.FILE_SIZE)
    model = S.set_player_count(S.build_slot(inputs), 1)
    compare('count.both_fields', image, model)

    ee = boot(elf)
    install_acts(ee, [(('keep', 32),)])
    ee.mem.write(G_SAVE, bytes([0xAB]) * S.FILE_SIZE)
    write_cstr(ee, S.DIRECTORY_AT + G_SAVE, 'keep')
    # directory is inside the buffer, so write the name after the fill
    ee.mem.write(G_SAVE + S.DIRECTORY_AT, b'keep\x00')
    ee.mem.write(G_SAVE + S.DATA_AT, bytes(range(32)))
    ee.mem.w32(G_LATCH, 0x99)
    call(ee, SAVE_CLEAR, 0)
    image = ee.mem.read(G_SAVE, S.FILE_SIZE)
    ok = (image[S.DIRECTORY_AT:S.DIRECTORY_AT + 5] == b'keep\x00'
          and image[S.DATA_AT:S.DATA_AT + 32] == bytes(range(32))
          and struct.unpack_from('<I', image, S.DIRECTORY_AT + 0x14)[0] == 32
          and image[0] == 0 and ee.mem.u32(G_LATCH) == 0)
    report('clear.keeps_first_level', ok, 'name, 32 level bytes, size 32, the rest cleared')
    ee.mem.write(G_SAVE, b'\xAB' * 16)
    call(ee, SAVE_CLEAR, 1)
    report('clear.full', ee.mem.read(G_SAVE, 16) == bytes(16), 'full clear')
    ee.mem.write(G_SAVE, b'\xCD' * 4)
    ee.mem.w8(G_BLOCK, 1)
    ee.mem.w32(G_LATCH, 7)
    call(ee, SAVE_CLEAR, 1)
    report('clear.blocked', ee.mem.read(G_SAVE, 4) == b'\xCD' * 4 and ee.mem.u32(G_LATCH) == 0,
           'blocked clear leaves the buffer and clears the latch')


def test_checksum_of_built_record(elf):
    ee = boot(elf)
    inputs, position, matrix, tail = _common(card=4)
    prepare(ee, inputs, position, matrix, tail, (), inputs.acts)
    live = inputs.players[0].record
    before = call(ee, CHECKSUM, 0, G_PLAYERS)
    run_build(ee, inputs)
    after = call(ee, CHECKSUM, 0, G_SAVED)
    saved = ee.mem.read(G_SAVED, S.RECORD_SIZE)
    ok = (before == S.player_checksum(0, G_PLAYERS, live)
          and after == S.player_checksum(0, G_SAVED, saved))
    report('checksum.live_and_saved', ok, 'live 0x%08x saved 0x%08x' % (before, after))


def main(argv=None):
    elf = find_elf(list(sys.argv[1:] if argv is None else argv))
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable (sha256 %s); nothing was compared' % (elf, digest))
        return 0
    if _elf_word(elf) != 0x16C8:
        print('SKIP  word at 0x4044d0 is not 0x16c8; the automap length would not match')
        return 0
    tests = (test_checksum, test_automap, test_items, test_config, test_builds,
             test_checksum_of_built_record, test_count_and_clear, test_load)
    for test in tests:
        try:
            test(elf)
        except (EmuError, MemoryFault, AssertionError) as error:
            report(test.__name__, False, '%s: %s' % (type(error).__name__, error))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL' % (len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    return 1 if failed else 0


def _elf_word(path):
    from ps2elf import Elf
    return Elf(path).u32(G_AUTO)


if __name__ == '__main__':
    sys.exit(main())
