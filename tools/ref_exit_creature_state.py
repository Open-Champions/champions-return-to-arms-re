#!/usr/bin/env python3
"""Independent, bounded base Creature level-record rules.

Observed entry points: save 0x116780, load 0x116920. This module never reads
an executable or emulator results. It models only the synthetic fixture
contract in docs/exits-r3-creature-state.md, not a derived corpse lifecycle.
"""
from dataclasses import dataclass
import math
import struct

try:
    from . import ref_core as C
except ImportError:
    import ref_core as C

SIZE = 0x3C8
VTABLE = 0x50CC58
SAVED_CFLAGS = (1 << 24, 1 << 32, 1 << 22, 1 << 23, 1 << 49)
DEATH_CLEAR = (1 << 27) | (1 << 22) | (1 << 23)
M64 = (1 << 64) - 1


class Refusal(ValueError):
    """Outside the evidenced fixture contract; do not invent a result."""


def read(blob, offset, size):
    return int.from_bytes(blob[offset:offset + size], 'little')


def positive_max(raw):
    value = C.to_float(raw)
    if not math.isfinite(value) or value <= 0 or raw & 0x7F800000 == 0:
        raise Refusal('maximum HP must be positive finite normal float32')


@dataclass(frozen=True)
class Source:
    variant: int
    hp: int
    maximum_hp: int
    cflags: int = 0
    inert: int = 0
    charm: int = 0


def save_payload(source, animation_offset):
    """0x116780: authored payload, independent of any executed save.

    animation_offset is -1 for an unresolvable top clip, otherwise the
    independently interned synthetic resource name's offset.
    """
    positive_max(source.maximum_hp)
    hp = C.to_float(source.hp)
    if not math.isfinite(hp) or (source.hp & 0x7FFFFFFF and
                                source.hp & 0x7F800000 == 0):
        raise Refusal('HP must be finite normal float32 or zero')
    if not -32768 <= source.charm <= 32767:
        raise Refusal('charm must fit the source signed halfword')
    if not -1 <= animation_offset < 0x80000000:
        raise Refusal('unknown animation string offset')
    packed = sum(1 << bit for bit, mask in enumerate(SAVED_CFLAGS)
                 if source.cflags & mask)
    packed |= (source.inert & 1) << 5
    packed |= int(source.charm != 0) << 6
    ratio = C.div(source.hp, source.maximum_hp)
    if (not math.isfinite(C.to_float(ratio)) or
            (ratio & 0x7FFFFFFF and ratio & 0x7F800000 == 0) or
            (C.to_float(ratio) <= 0) != (hp <= 0)):
        raise Refusal('HP ratio cannot preserve the payload branch')
    words = [source.variant & 0xFFFFFFFF, ratio]
    if hp <= 0:
        words.append(animation_offset & 0xFFFFFFFF)
    words.append(packed)
    if source.charm:
        words.append(source.charm & 0xFFFFFFFF)
    return struct.pack('<' + 'I' * len(words), *words)


def intern_synthetic(names):
    """Independent bounded string-table layout: length byte, ASCII, NUL.

    Returns the table and offsets into it. Repeated names reuse their offset.
    """
    table, offsets, seen = bytearray(), [], {}
    for name in names:
        if not isinstance(name, bytes) or not name or len(name) > 127 or any(
                not 32 <= b < 127 for b in name):
            raise Refusal('only short synthetic ASCII names')
        if name not in seen:
            seen[name] = len(table) + 1
            table.extend(bytes([len(name)]) + name + b'\0')
        offsets.append(seen[name])
    return bytes(table), tuple(offsets)


@dataclass(frozen=True)
class Restore:
    image: bytes
    writes: tuple
    consumed: int
    dead: bool
    animated: bool


def restore_fresh(initial, payload, *, clip, length, animation_matches):
    """0x116920: expected object image and ordered object-relative writes.

    Destination has original base vtable, empty model, no properties/handles,
    zero charm, zero object flags, empty animation with capacity 8, no pose or
    decoder cache. Selected numeric fields/cflags/inert bytes may be nonzero.
    Callers independently validate resource/table fixtures. No world lifecycle
    or runtime type-information cache writes are predicted here.
    """
    if len(initial) != SIZE or read(initial, 0x48, 4) != VTABLE:
        raise Refusal('only a base Creature image')
    for offset, size in ((0, 12), (0x0C, 4), (0x2C, 4), (0x34, 4),
                         (0x114, 5), (0x11C, 0x100), (0x234, 8),
                         (0x2E4, 4), (0x310, 8)):
        if read(initial, offset, size):
            raise Refusal('nonempty destination dependency')
    if initial[0x119] != 8 or not 0 < clip < 0x80000000 or not 1 <= length <= 4096:
        raise Refusal('unsupported animation fixture')
    maximum = read(initial, 0x22C, 4)
    positive_max(maximum)
    if len(payload) < 12 or len(payload) % 4:
        raise Refusal('truncated payload')
    variant, ratio = struct.unpack_from('<II', payload)
    ratio_value = C.to_float(ratio)
    if not math.isfinite(ratio_value) or (ratio & 0x7FFFFFFF and ratio & 0x7F800000 == 0):
        raise Refusal('unsupported HP ratio')
    hp = C.mul(maximum, ratio)
    if (not math.isfinite(C.to_float(hp)) or
            (hp & 0x7FFFFFFF and hp & 0x7F800000 == 0) or
            (C.to_float(hp) <= 0) != (ratio_value <= 0)):
        raise Refusal('unsupported restored HP')
    dead = C.to_float(hp) <= 0
    flag_offset = 12 if dead else 8
    if len(payload) < flag_offset + 4:
        raise Refusal('missing packed flags')
    flags = read(payload, flag_offset, 4)
    if flags & ~0x7F:
        raise Refusal('unknown packed flag bits')
    size = flag_offset + 4 + 4 * bool(flags & 0x40)
    if len(payload) != size:
        raise Refusal('payload length does not match destination HP branch')
    if flags & 0x40:
        charm = struct.unpack_from('<i', payload, size - 4)[0]
        if not -32768 <= charm <= 32767:
            raise Refusal('unsupported serialized charm')
    animation_offset = struct.unpack_from('<i', payload, 8)[0] if dead else -1
    if dead and animation_offset < -1:
        raise Refusal('unknown animation reference')
    animated = dead and animation_offset >= 0 and animation_matches
    out, writes = bytearray(initial), []

    def put(offset, size, value):
        value &= (1 << (size * 8)) - 1
        out[offset:offset + size] = value.to_bytes(size, 'little')
        writes.append((offset, size, value))

    put(0xE8, 4, variant)
    put(0x228, 4, hp)
    put(0x220, 8, M64)  # Empty model's complemented exclusion mask.
    if dead:
        put(0x232, 2, 0x14)
        put(0x0C, 4, read(out, 0x0C, 4) | 0x2009)
    if animated:
        put(0x118, 1, 0)
        put(0x118, 1, 1)
        put(0x11C, 4, clip)
        put(0x11A, 2, read(out, 0x11A, 2) | 4)
        put(0x134, 4, 0)
        put(0x13A, 2, 0)
        put(0x138, 2, 4)
        for offset, value in ((0x128, 0), (0x124, C.f32(1)),
                              (0x12C, C.f32(1)), (0x130, 0)):
            put(offset, 4, value)
        put(0x134, 4, C.f32(length))
        put(0x11A, 2, read(out, 0x11A, 2) | 0x80)
        put(0xA8, 8, read(out, 0xA8, 8) & ~DEATH_CLEAR)
    for bit, mask in enumerate(SAVED_CFLAGS):
        if flags & (1 << bit):
            put(0xA8, 8, read(out, 0xA8, 8) | mask)
    put(0x231, 1, out[0x231] & ~1)
    if flags & 0x20:
        put(0x231, 1, out[0x231] | 1)
    # Word is consumed, but this zero-flag destination cannot apply charm.
    # Actual player/creature charm application remains explicitly unsupported.
    return Restore(bytes(out), tuple(writes), size, dead, animated)
