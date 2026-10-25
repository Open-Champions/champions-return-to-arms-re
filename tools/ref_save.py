"""Memory-card slot image for Champions: Return to Arms (SLUS-20973 US v2.00).

The slot file is the raw save buffer: no magic and no file checksum. This module
builds and parses that image from values a test supplies. It does not contain a
save from a disc or a memory card. Whether the bytes match the original functions
is tools/difftest_save.py. The layout, with what was read and what was run, is
docs/save-format.md.

Addresses used by the original code, so a reader can find them:

  save buffer 0x895580, 0x4bc78 bytes
  save_build 0x221914, save_load 0x221d60, save_storeLevelState 0x21777c
  save_writeLevelState 0x218600, save_snapshotPlayer 0x216c80, save_fixupPlayer 0x216ea8
  player_checksum 0x1bdc98 (netplay mix; not stored in the file and not checked on load)
"""

import struct
from dataclasses import dataclass

FILE_SIZE = 0x4BC78
RECORD_SIZE = 0x4C30
BLOCK_SIZE = 0x4C3E
POSE_SIZE = 0x0E
CAMERA_SIZE = 0xC4
JUMP_SIZE = 0x1E4
JUMP_DEST_SIZE = 0x1E0
HEADER_SIZE = 0x70
PLAYERS_AT = 0x320
QUESTS_AT = 0x13418
DIRECTORY_AT = 0x16010
DATA_AT = 0x16118
DIRECTORY_SLOTS = 10
DIRECTORY_STRIDE = 0x18
QUEST_STRIDE = 0x24
PLAYER_SLOTS = 4
CONFIG_SIZE = 0x2F8
AUTOMAP_SIZE = 0x16C8
AUTOMAP_GRID_SPAN = 0x16ACE
ITEM_TABLE = 0x3F7650
ITEM_ROW = 0x40
ITEM_SIZE = 0x48
BAG_ITEM_AT = 0x130
BAG_STRIDE = 0x1208
BAG_COUNT_AT = 0x1330
BAGS = 3
BAG_CAPACITY = 64
COMPLETE_NAME = b'gameComplete\x00'
EMPTY_WORLD = bytes((0x00, 0x00, 0x01, 0x00, 0x08, 0x00, 0x00, 0x00))
EMPTY_DECAL = bytes(8)
COMPLETE_LEVEL_SIZE = 0x88B8

# player_checksum mixes these. The address term is the record pointer, shifted by the slot.
_CHECK_XOR = 0xC18DA3B1
_LEVEL_XOR = 0x023D5097


class SaveError(ValueError):
    """The image is not one this reader will hand to an importer."""


def u32(value):
    return value & 0xFFFFFFFF


def s32(value):
    value = u32(value)
    return value - 0x100000000 if value & 0x80000000 else value


def s8(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def _u32_at(buf, offset):
    return struct.unpack_from('<I', buf, offset)[0]


def _s32_at(buf, offset):
    return struct.unpack_from('<i', buf, offset)[0]


def _put_u32(buf, offset, value):
    struct.pack_into('<I', buf, offset, u32(value))


def _put_s32(buf, offset, value):
    struct.pack_into('<i', buf, offset, s32(value))


def _bits(value):
    """A float's little-endian bits, or the low 32 bits of an int left unchanged."""
    if isinstance(value, int):
        return u32(value)
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def _write_cstr(buf, offset, text, limit):
    raw = text.encode('latin-1')
    if len(raw) >= limit:
        raise ValueError('string of %d bytes does not fit in %d' % (len(raw), limit))
    buf[offset:offset + len(raw) + 1] = raw + b'\x00'


def _read_cstr(buf, offset, limit):
    window = bytes(buf[offset:offset + limit])
    end = window.find(b'\x00')
    if end < 0:
        return None
    return window[:end].decode('latin-1')


def definition_index(pointer):
    """Row number stored in place of an item-definition pointer (item_encodeDefinitionIndex 0x107ea4)."""
    return s32(u32(pointer) - ITEM_TABLE) >> 6


def definition_pointer(index):
    """Pointer restored from that row number (item_decodeDefinitionIndex 0x107ec0)."""
    return u32(ITEM_TABLE + (u32(index) << 6))


def item_address(record_base, bag, index):
    return u32(record_base + BAG_ITEM_AT + bag * BAG_STRIDE + index * ITEM_SIZE)


def pointer_to_index(pointer, record_base, counts):
    """save_itemPtrToIndex 0x216bf8: bag * 1000 + slot, or -1."""
    if u32(pointer) == 0:
        return -1
    for bag in range(BAGS):
        count = counts[bag]
        if count <= 0:
            continue
        for index in range(count):
            if item_address(record_base, bag, index) == u32(pointer):
                return bag * 1000 + index
    return -1


def index_to_pointer(index, record_base, counts):
    """save_itemIndexToPtr 0x216e10. -1 and any index that is not a counted slot become 0."""
    if s32(index) == -1:
        return 0
    target = s32(index)
    base = 0
    for bag in range(BAGS):
        count = counts[bag]
        if count > 0:
            for slot in range(count):
                if slot + base == target:
                    return item_address(record_base, bag, slot)
        base += 1000
    return 0


def _bag_counts(record):
    return tuple(_s32_at(record, BAG_COUNT_AT + bag * BAG_STRIDE) for bag in range(BAGS))


def encode_saved_record(live, live_base):
    """The record save_snapshotPlayer writes: a copy, then equipment indices and definition row numbers."""
    saved = bytearray(live)
    if len(saved) < RECORD_SIZE:
        raise ValueError('record is %d bytes' % len(saved))
    counts = _bag_counts(saved)
    offsets = [0x43F0 + 4 * i for i in range(17)] + [0x4434, 0x4438, 0x443C]
    for offset in offsets:
        _put_s32(saved, offset, pointer_to_index(_u32_at(saved, offset), live_base, counts))
    for bag in range(BAGS):
        count = counts[bag]
        if count <= 0:
            continue
        for index in range(count):
            offset = BAG_ITEM_AT + bag * BAG_STRIDE + index * ITEM_SIZE
            if offset + 4 > len(saved):
                break
            _put_s32(saved, offset, definition_index(_u32_at(saved, offset)))
    return bytes(saved[:RECORD_SIZE])


def decode_loaded_record(saved, live_base):
    """The record save_fixupPlayer leaves in the live table. The object pointer is cleared."""
    live = bytearray(saved[:RECORD_SIZE])
    _put_u32(live, 0x43D8, 0)
    counts = _bag_counts(live)
    for bag in range(BAGS):
        count = counts[bag]
        if count <= 0:
            continue
        for index in range(count):
            offset = BAG_ITEM_AT + bag * BAG_STRIDE + index * ITEM_SIZE
            if offset + 4 > len(live):
                break
            _put_u32(live, offset, definition_pointer(_s32_at(live, offset)))
    offsets = [0x43F0 + 4 * i for i in range(17)] + [0x4434, 0x4438, 0x443C]
    for offset in offsets:
        _put_u32(live, offset, index_to_pointer(_s32_at(live, offset), live_base, counts))
    return bytes(live)


def mix_bytes(data):
    """First byte subtracted, every later byte added. Each byte is sign-extended. 32-bit wrap."""
    acc = 0
    for index, byte in enumerate(data):
        extended = u32(s8(byte))
        acc = u32(acc - extended) if index == 0 else u32(acc + extended)
    return acc


def _mul32(left, right):
    return u32(s32(left) * s32(right))


def _times35(value):
    """The gold mix uses shifts: ((v * 8 + v) * 4) - v."""
    value = u32(value)
    return u32(u32(u32((value << 3) + value) << 2) - value)


def _times3(value):
    value = u32(value)
    return u32(u32(value << 1) + value)


def player_checksum(slot, address, record):
    """player_checksum 0x1bdc98. Same bytes at two addresses differ, because the address is mixed in.

    Not a checksum of the file. Nothing in save_build or save_load reads or writes it.
    """
    if len(record) < 0x4434:
        raise ValueError('checksum needs the record through +0x4434')
    slot &= 31
    appearance = _mul32(u32(u32(s8(record[0x20])) + u32(s8(record[0x23])))
                        + u32(u32(s8(record[0x22])) + u32(s8(record[0x21]))), 0x35)
    levels = u32(u32(s8(record[0x58])) + u32(s8(record[0x59]))) ^ _LEVEL_XOR
    acc = u32(u32(u32(address) << slot) ^ _CHECK_XOR)
    acc = u32(u32(acc + appearance) - levels)
    acc ^= mix_bytes(record[0x5C:0x60])
    acc = u32(acc ^ _times35(mix_bytes(record[0xE4:0xE8])))
    for index in range(6):
        mixed = mix_bytes(record[0x90 + 4 * index:0x94 + 4 * index])
        acc = u32(acc + _mul32(mixed, index))
    mana = mix_bytes(record[0xC0:0xC4])
    maximum = mix_bytes(record[0xC4:0xC8])
    pending = mix_bytes(record[0xC8:0xCC])
    acc = u32(acc - u32(u32(mana + maximum) - pending))
    acc = u32(acc - _times3(mix_bytes(record[0xE8:0xEC])))
    acc = u32(s32(acc) >> slot)
    acc = u32(acc + mix_bytes(record[0x3748:0x3748 + 0xA88]))
    acc = u32(acc + mix_bytes(record[0x43F0:0x43F0 + 0x44]))
    return acc


def pack_automap(grid):
    """automap_packExplored 0x16865c. 108 rows by 54 columns, 0x16c8 bytes, no length prefix.

    Byte = (grid[off + 1] & 0xf0) + (grid[off + 5] >> 4). A short grid reads as zero past its end.
    """
    out = bytearray()
    row = 0
    for _ in range(0xD8 // 2):
        offset = row << 1
        column = 0
        while True:
            column += 4
            high = grid[offset + 1] if offset + 1 < len(grid) else 0
            low = grid[offset + 5] if offset + 5 < len(grid) else 0
            out.append(((high & 0xF0) + (low >> 4)) & 0xFF)
            offset += 8
            if column >= 0xD8:
                break
        row += 0x1B0
    return bytes(out)


def frame_level_state(world_body, decal_body, automap):
    """The three sections save_writeLevelState lays down.

    Each of the first two is a u32 length, four bytes the writer does not touch, then the body.
    The automap follows the decal body with no length of its own.
    """
    return b''.join((
        struct.pack('<I', len(world_body)), b'\x00\x00\x00\x00', world_body,
        struct.pack('<I', len(decal_body)), b'\x00\x00\x00\x00', decal_body,
        automap,
    ))


def round_reserved(original, automap_half):
    """The size save_init writes back over each act-table u16: (original + half + 1000) aligned down to 128."""
    return (original + (automap_half & 0xFFFF) + 0x3E8) & 0xFF80


def pack_camera(position, matrix, half_68, half_6a, word_54, word_58, floats, tail):
    """Camera_saveState 0x203918. Returns 0xc4 bytes.

    matrix is at least 13 floats. The stored 16 are a sliding window:
    indices 0..3, 3..6, 6..9, 9..12. floats is (cam+0x90, cam+0xd4, cam+0x8c). tail is 0x60 bytes from cam+0x100.
    """
    if len(tail) != 0x60:
        raise ValueError('camera tail is %d bytes' % len(tail))
    out = bytearray(struct.pack('<3I', *(_bits(v) for v in position)))
    window = []
    row = column = 0
    for _ in range(4):
        start = row + column
        window.extend(matrix[start:start + 4])
        column += 1
        row += 2
    if len(window) != 16:
        raise ValueError('camera matrix window is short')
    out += struct.pack('<16I', *(_bits(v) for v in window))
    out += struct.pack('<HHII', half_68 & 0xFFFF, half_6a & 0xFFFF, u32(word_54), u32(word_58))
    out += struct.pack('<3I', *(_bits(v) for v in floats))
    out += tail
    if len(out) != CAMERA_SIZE:
        raise ValueError('camera image is %d bytes' % len(out))
    return bytes(out)


def pack_jump(count, destinations):
    """jumpgate_saveDestinations 0x27dcf4: the count byte, sign-extended to a word, then 0x1e0 bytes."""
    if len(destinations) != JUMP_DEST_SIZE:
        raise ValueError('jump destinations are %d bytes' % len(destinations))
    return struct.pack('<i', s8(count)) + bytes(destinations)


def qualified_name(level_name, subname):
    if subname:
        return level_name + '_' + subname
    return level_name


def find_act(name, current, acts):
    """save_findAct 0x217d30. A table name matches when it is a prefix of name. Returns -1 when none matches."""
    if current != -1 and 0 <= current < len(acts):
        for level, _size in acts[current]:
            if name.startswith(level):
                return current
    for index, levels in enumerate(acts):
        for level, _size in levels:
            if name.startswith(level):
                return index
    return -1


def level_index(name, act, acts):
    """save_levelIndexInAct 0x2187a0. The current act only. -1 when the act itself is -1."""
    if act < 0 or act >= len(acts):
        return -1
    for index, (level, _size) in enumerate(acts[act]):
        if name.startswith(level):
            return index
    return -1


def _object_pointer(record):
    return _u32_at(record, 0x43D8)


def _pose_source(players, index, num_players, alive_first):
    if _object_pointer(players[index].record) != 0:
        return players[index]
    if 0 <= alive_first < len(players) and _object_pointer(players[alive_first].record) != 0:
        return players[alive_first]
    for other in range(min(num_players, len(players))):
        if _object_pointer(players[other].record) != 0:
            return players[other]
    return None


def _directory_name(buf, index):
    return _read_cstr(buf, DIRECTORY_AT + index * DIRECTORY_STRIDE, 0x14)


@dataclass
class LiveCharacter:
    """One live player the builder snapshots. record is the 0x4c30 live bytes, pointers included."""

    record: bytes
    live_base: int
    facing: int = 0
    position: tuple = (0.0, 0.0, 0.0)


@dataclass
class SlotInputs:
    """Everything save_build and save_storeLevelState read, apart from the empty world and decal bodies.

    world_body and decal_body default to the bodies those functions write when their tables are empty.
    A populated world is not reproduced here; pass the body if you have one.
    """

    level_name: str = 'crypt'
    subname: str = ''
    game_complete: bool = False
    play_time: int = 0
    difficulty: int = 0
    save_arg: int = 0
    act: int = 0
    one_player: bool = False
    num_players: int = 1
    players: tuple = ()
    alive_first: int = -1
    camera: bytes = None
    jump_count: int = 0
    jump_dest: bytes = None
    minimap: int = 0
    quests: tuple = ()
    acts: tuple = ()
    memcard_state: int = 0
    block_flag: int = 0
    automap_grid: bytes = b''
    previous: bytes = None
    world_body: bytes = None
    decal_body: bytes = None


def _store_level(buf, name, inputs):
    """The part of save_storeLevelState that changes the buffer. Returns without writing on every skip."""
    if inputs.memcard_state == 4 or (inputs.block_flag & 0x800):
        return
    if inputs.game_complete:
        reserved = COMPLETE_LEVEL_SIZE
    else:
        # strncmp(name, "hub", 3) == 0 selects row 0 and does not search. A shorter name does not match.
        if len(name) >= 3 and name[:3] == 'hub':
            index = 0
        else:
            index = level_index(name, inputs.act, inputs.acts)
            if index < 0:
                return
        if inputs.act < 0 or inputs.act >= len(inputs.acts) or index >= len(inputs.acts[inputs.act]):
            return
        reserved = inputs.acts[inputs.act][index][1] & 0xFFFF
    prior = 0
    chosen = None
    new = False
    for slot in range(DIRECTORY_SLOTS):
        offset = DIRECTORY_AT + slot * DIRECTORY_STRIDE
        if buf[offset] == 0:
            chosen = slot
            new = True
            break
        if _directory_name(buf, slot) == name:
            chosen = slot
            break
        prior = u32(prior + _u32_at(buf, offset + 0x14))
    if chosen is None:
        return
    if new:
        _write_cstr(buf, DIRECTORY_AT + chosen * DIRECTORY_STRIDE, name, 0x14)
        _put_u32(buf, DIRECTORY_AT + chosen * DIRECTORY_STRIDE + 0x14, reserved)
    else:
        reserved = _u32_at(buf, DIRECTORY_AT + chosen * DIRECTORY_STRIDE + 0x14)
    # Unsigned 32-bit sum, then an unsigned compare with the file size. A new name is left in place.
    total = u32(DATA_AT + u32(prior) + u32(reserved))
    if FILE_SIZE < total:
        return
    world = inputs.world_body if inputs.world_body is not None else EMPTY_WORLD
    decal = inputs.decal_body if inputs.decal_body is not None else EMPTY_DECAL
    blob = frame_level_state(world, decal, pack_automap(inputs.automap_grid))
    start = DATA_AT + prior
    buf[start:start + len(blob)] = blob


def build_slot(inputs):
    """The buffer save_build leaves, including the level directory when the store runs.

    A level that is not in the act table, and a game that is not marked complete, leaves
    the previous bytes untouched. The game-complete path writes the header and the players
    and does not call the level store.
    """
    if inputs.previous is None:
        buf = bytearray(FILE_SIZE)
    else:
        if len(inputs.previous) != FILE_SIZE:
            raise ValueError('previous image is %d bytes' % len(inputs.previous))
        buf = bytearray(inputs.previous)
    qualified = qualified_name(inputs.level_name, inputs.subname)
    if not inputs.game_complete and find_act(qualified, inputs.act, inputs.acts) < 0:
        return bytes(buf)
    if inputs.game_complete:
        buf[0:len(COMPLETE_NAME)] = COMPLETE_NAME
    else:
        _write_cstr(buf, 0, inputs.level_name, 0x14)
    _write_cstr(buf, 0x14, inputs.subname, 0x50)
    _put_u32(buf, 0x64, inputs.play_time)
    struct.pack_into('<H', buf, 0x68, RECORD_SIZE)
    listed = 1 if inputs.one_player else inputs.num_players
    struct.pack_into('<H', buf, 0x6A, listed & 0xFFFF)
    buf[0x6C] = inputs.difficulty & 0xFF
    buf[0x6D] = inputs.save_arg & 0xFF
    struct.pack_into('<H', buf, 0x6E, inputs.act & 0xFFFF)
    camera = inputs.camera if inputs.camera is not None else bytes(CAMERA_SIZE)
    if len(camera) != CAMERA_SIZE:
        raise ValueError('camera image is %d bytes' % len(camera))
    buf[HEADER_SIZE:HEADER_SIZE + CAMERA_SIZE] = camera
    destinations = inputs.jump_dest if inputs.jump_dest is not None else bytes(JUMP_DEST_SIZE)
    jump = pack_jump(inputs.jump_count, destinations)
    buf[0x134:0x134 + JUMP_SIZE] = jump
    _put_u32(buf, 0x318, inputs.minimap)
    _put_u32(buf, 0x31C, inputs.num_players)
    cursor = PLAYERS_AT
    for slot in range(PLAYER_SLOTS):
        if slot < inputs.num_players:
            player = inputs.players[slot]
            source = _pose_source(inputs.players, slot, inputs.num_players, inputs.alive_first)
            if source is None:
                buf[cursor:cursor + POSE_SIZE] = bytes(POSE_SIZE)
            else:
                struct.pack_into('<H', buf, cursor, source.facing & 0xFFFF)
                struct.pack_into('<3I', buf, cursor + 2, *(_bits(v) for v in source.position))
            saved = encode_saved_record(player.record, player.live_base)
            buf[cursor + POSE_SIZE:cursor + BLOCK_SIZE] = saved
        cursor += BLOCK_SIZE
    while cursor & 3:
        cursor += 1
    for name, value in inputs.quests:
        _write_cstr(buf, cursor, name, 0x20)
        _put_s32(buf, cursor + 0x20, value)
        cursor += QUEST_STRIDE
    if not inputs.game_complete:
        _store_level(buf, qualified, inputs)
    return bytes(buf)


def set_player_count(image, count):
    """save_setPlayerCount 0x218520 writes the u16 and the u32 count. Both become this value."""
    buf = bytearray(image)
    struct.pack_into('<H', buf, 0x6A, count & 0xFFFF)
    _put_u32(buf, 0x31C, count)
    return bytes(buf)


@dataclass
class Item:
    definition_index: int
    quantity: int
    raw: bytes


@dataclass
class Character:
    name: str
    appearance: tuple
    class_index: int
    model_index: int
    acknowledged_level: int
    level: int
    experience: int
    base_stats: tuple
    gold: int
    skill_points: int
    stat_points: int
    passives: tuple
    bags: tuple
    equipment: tuple
    weapon_sets: tuple
    offhand: int
    skills: tuple
    mission_flags: bytes
    medals: bytes
    evil_bits: int
    decision_bits: int
    kind: int
    facing: int
    position: tuple
    object_pointer: int
    raw: bytes


@dataclass
class LevelBlob:
    name: str
    size: int
    data: bytes
    world: bytes = None
    decal: bytes = None
    automap: bytes = None
    note: str = ''


@dataclass
class SlotFile:
    level_name: str
    subname: str
    play_time: int
    record_size: int
    listed_count: int
    player_count: int
    difficulty: int
    save_arg: int
    act: int
    camera: bytes
    jump_count: int
    jump_destinations: bytes
    minimap_mode: int
    characters: tuple
    quests: tuple
    levels: tuple
    raw: bytes


def _parse_items(record, bag, strict):
    count = _s32_at(record, BAG_COUNT_AT + bag * BAG_STRIDE)
    if strict and not 0 <= count <= BAG_CAPACITY:
        raise SaveError('bag %d count %d is outside 0..64' % (bag, count))
    if count < 0:
        count = 0
    items = []
    base = BAG_ITEM_AT + bag * BAG_STRIDE
    for index in range(min(count, BAG_CAPACITY)):
        offset = base + index * ITEM_SIZE
        raw = bytes(record[offset:offset + ITEM_SIZE])
        items.append(Item(_s32_at(record, offset), struct.unpack_from('<h', record, offset + 4)[0], raw))
    return tuple(items)


def _parse_character(block, strict):
    record = block[POSE_SIZE:POSE_SIZE + RECORD_SIZE]
    name = _read_cstr(record, 0, 0x20)
    if name is None:
        if strict:
            raise SaveError('character name has no terminator')
        name = ''
    skills = []
    for index in range(48):
        offset = 0x4B08 + index * 4
        ident, rank = struct.unpack_from('<hh', record, offset)
        if ident == -1:
            break
        skills.append((ident, rank))
    facing = struct.unpack_from('<H', block, 0)[0]
    position = struct.unpack_from('<3f', block, 2)
    return Character(
        name=name,
        appearance=tuple(s8(record[0x20 + i]) for i in range(4)),
        class_index=_s32_at(record, 0x50),
        model_index=_s32_at(record, 0x54),
        acknowledged_level=s8(record[0x58]),
        level=s8(record[0x59]),
        experience=_s32_at(record, 0x5C),
        base_stats=tuple(_s32_at(record, 0x78 + 4 * i) for i in range(4)),
        gold=_s32_at(record, 0xE4),
        skill_points=_s32_at(record, 0xE8),
        stat_points=s8(record[0xEC]),
        passives=tuple(s8(record[0xEF + i]) for i in range(48)),
        bags=tuple(_parse_items(record, bag, strict) for bag in range(BAGS)),
        equipment=tuple(_s32_at(record, 0x43F0 + 4 * i) for i in range(17)),
        weapon_sets=(_s32_at(record, 0x4434), _s32_at(record, 0x4438)),
        offhand=_s32_at(record, 0x443C),
        skills=tuple(skills),
        mission_flags=bytes(record[0x4BBF:0x4C0D]),
        medals=bytes(record[0x4C0D:0x4C1A]),
        evil_bits=record[0x4C1A],
        decision_bits=record[0x4C1B],
        kind=record[0x4C1C] & 0x1F,
        facing=facing,
        position=position,
        object_pointer=_u32_at(record, 0x43D8),
        raw=bytes(record),
    )


def _split_frame(blob):
    if len(blob) < 16:
        return None, None, None, 'shorter than a header'
    world_len = _u32_at(blob, 0)
    world_at = 8
    if world_len > len(blob) - world_at:
        return None, None, None, 'world length does not fit'
    decal_at_len = world_at + world_len
    if decal_at_len + 8 > len(blob):
        return None, None, None, 'decal header does not fit'
    decal_len = _u32_at(blob, decal_at_len)
    decal_at = decal_at_len + 8
    if decal_len > len(blob) - decal_at:
        return None, None, None, 'decal length does not fit'
    auto_at = decal_at + decal_len
    automap = bytes(blob[auto_at:auto_at + AUTOMAP_SIZE]) if auto_at < len(blob) else b''
    return bytes(blob[world_at:world_at + world_len]), bytes(blob[decal_at:decal_at + decal_len]), automap, ''


def parse_slot(data, strict=True):
    """Read one slot image. strict is the importer's own refusal list, which is tighter than save_load.

    save_load checks none of these. It does not look at a magic, a checksum, or the record-size field.
    """
    if len(data) != FILE_SIZE:
        raise SaveError('slot image is %d bytes, the file is %d' % (len(data), FILE_SIZE))
    record_size = struct.unpack_from('<H', data, 0x68)[0]
    listed = struct.unpack_from('<H', data, 0x6A)[0]
    player_count = _s32_at(data, 0x31C)
    if strict and record_size != RECORD_SIZE:
        raise SaveError('record size field is 0x%x' % record_size)
    if strict and not 0 <= player_count <= PLAYER_SLOTS:
        raise SaveError('player count %d is outside 0..4' % player_count)
    count = min(max(player_count, 0), PLAYER_SLOTS)
    characters = tuple(
        _parse_character(data[PLAYERS_AT + slot * BLOCK_SIZE:PLAYERS_AT + (slot + 1) * BLOCK_SIZE], strict)
        for slot in range(count))
    quests = []
    cursor = QUESTS_AT
    while cursor < DIRECTORY_AT:
        if data[cursor] == 0:
            break
        if cursor + QUEST_STRIDE > DIRECTORY_AT:
            if strict:
                raise SaveError('quest record at 0x%x runs into the level directory' % cursor)
            break
        name = _read_cstr(data, cursor, 0x20)
        if name is None:
            if strict:
                raise SaveError('quest name at 0x%x has no terminator' % cursor)
            break
        quests.append((name, _s32_at(data, cursor + 0x20)))
        cursor += QUEST_STRIDE
    levels = []
    consumed = 0
    for slot in range(DIRECTORY_SLOTS):
        offset = DIRECTORY_AT + slot * DIRECTORY_STRIDE
        if data[offset] == 0:
            break
        name = _read_cstr(data, offset, 0x14)
        if name is None:
            if strict:
                raise SaveError('level name in directory slot %d has no terminator' % slot)
            break
        size = _u32_at(data, offset + 0x14)
        start = DATA_AT + consumed
        if start + size > FILE_SIZE:
            if strict:
                raise SaveError('level %s needs %d bytes past the end of the file' % (name, size))
            break
        blob = bytes(data[start:start + size])
        world, decal, automap, note = _split_frame(blob)
        levels.append(LevelBlob(name, size, blob, world, decal, automap, note))
        consumed += size
    level_name = _read_cstr(data, 0, 0x14) or ''
    subname = _read_cstr(data, 0x14, 0x50) or ''
    if strict and _read_cstr(data, 0, 0x14) is None:
        raise SaveError('level name has no terminator')
    return SlotFile(
        level_name=level_name,
        subname=subname,
        play_time=_u32_at(data, 0x64),
        record_size=record_size,
        listed_count=listed,
        player_count=player_count,
        difficulty=data[0x6C],
        save_arg=data[0x6D],
        act=struct.unpack_from('<h', data, 0x6E)[0],
        camera=bytes(data[0x70:0x70 + CAMERA_SIZE]),
        jump_count=_s32_at(data, 0x134),
        jump_destinations=bytes(data[0x138:0x138 + JUMP_DEST_SIZE]),
        minimap_mode=_u32_at(data, 0x318),
        characters=characters,
        quests=tuple(quests),
        levels=tuple(levels),
        raw=bytes(data),
    )


def import_character(data, index=0, strict=True):
    """The character a native client takes from a slot file. index selects one of the loaded records."""
    slot = parse_slot(data, strict=strict)
    if not 0 <= index < len(slot.characters):
        raise SaveError('character %d is outside the %d loaded record(s)' % (index, len(slot.characters)))
    return slot.characters[index]


def _button_row(scheme):
    if scheme == 1:
        return (0x40, 0x20, 0x10, 0x80, 0x08, 0x02, 0x01, 0x400, 0x04)
    if scheme == 0:
        return (0x20, 0x10, 0x40, 0x80, 0x08, 0x02, 0x01, 0x400, 0x04)
    return None


def config_set_defaults(which=-1, scheme=1, image=None):
    """The image config_setDefaults 0x1e6238 writes into g_savedConfig.

    which -1 writes the option words and every button row. A slot index writes only that row.
    scheme is the byte at 0x41b69c: 1 and 0 select the two mask orders; any other value leaves the row alone.
    """
    buf = bytearray(image if image is not None else bytes(CONFIG_SIZE))
    if len(buf) < CONFIG_SIZE:
        raise ValueError('config image is short')
    if which == -1:
        struct.pack_into('<f', buf, 0x04, 0.5)
        struct.pack_into('<f', buf, 0x08, 0.5)
        struct.pack_into('<f', buf, 0x0C, 0.5)
        for offset, value in ((0x00, 0), (0x10, 1), (0x14, 1), (0x18, 1), (0x1C, 1),
                              (0x20, 1), (0x24, 0), (0x28, 1), (0x2C, 1), (0x30, 0),
                              (0xC4, 1), (0xD0, 1), (0xD4, 0)):
            _put_u32(buf, offset, value)
        struct.pack_into('<I', buf, 0xC8, 0x3E199999)
        struct.pack_into('<f', buf, 0xCC, 0.5)
        slots = range(4)
    elif 0 <= which < 4:
        slots = (which,)
    else:
        slots = ()
    row = _button_row(scheme)
    if row is not None:
        for slot in slots:
            base = 0x34 + slot * 0x24
            for index, mask in enumerate(row):
                _put_u32(buf, base + 4 * index, mask)
    return bytes(buf[:CONFIG_SIZE])


@dataclass
class ConfigFile:
    brightness: float
    music: float
    effects: float
    stereo: int
    vibration: int
    subtitles: int
    damage_numbers: int
    blood: int
    markers: int
    combat_camera: int
    reverse_yaw: int
    unnamed_18: int
    buttons: tuple
    voice: bytes
    profile: tuple
    raw: bytes


def _profile_entries(data):
    entries = []
    cursor = 0xF8
    while cursor < CONFIG_SIZE and data[cursor] != 0:
        end = data.find(b'\x00', cursor, CONFIG_SIZE)
        if end < 0 or end + 1 >= CONFIG_SIZE:
            break
        entries.append((data[cursor:end].decode('latin-1'), s8(data[end + 1])))
        cursor = end + 2
    return tuple(entries)


def parse_config(data, strict=True):
    """The 760-byte options file: a raw image of g_savedConfig, with no checksum."""
    if len(data) != CONFIG_SIZE:
        raise SaveError('config image is %d bytes, the file is %d' % (len(data), CONFIG_SIZE))
    buttons = tuple(
        tuple(_u32_at(data, 0x34 + slot * 0x24 + 4 * index) for index in range(9))
        for slot in range(4))
    return ConfigFile(
        brightness=struct.unpack_from('<f', data, 0x04)[0],
        music=struct.unpack_from('<f', data, 0x08)[0],
        effects=struct.unpack_from('<f', data, 0x0C)[0],
        stereo=_u32_at(data, 0x10),
        vibration=_u32_at(data, 0x14),
        subtitles=_u32_at(data, 0x1C),
        damage_numbers=_u32_at(data, 0x20),
        blood=_u32_at(data, 0x24),
        markers=_u32_at(data, 0x28),
        combat_camera=_u32_at(data, 0x2C),
        reverse_yaw=_u32_at(data, 0x30),
        unnamed_18=_u32_at(data, 0x18),
        buttons=buttons,
        voice=bytes(data[0xC4:0xD8]),
        profile=_profile_entries(data),
        raw=bytes(data),
    )
