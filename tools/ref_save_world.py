"""Bounded SLUS-20973 v2.00 per-level save framing and reload order.

This models the host's calls at 0x218600 and 0x217978, not object-specific
slot 8/9 state or the native client's format. Inputs are synthetic. See
docs/save-world.md for the evidence and limits.
"""

import struct

AUTOMAP_SIZE = 0x16C8
LEVEL_DATA_AT = 0x16118
LEVEL_DIRECTORY_AT = 0x16010
LEVEL_SLOTS = 10


def chest_state(obj):
    """0x292284: hide mask, gold remainder, two kind bytes, opened word."""
    return struct.pack('<IHBBI', obj['hide_mask'], obj['gold'],
                       obj['bomb'], obj['variant'], obj['opened'])


def itemprop_item(item):
    """0x1596a4: a 0x48-byte item with its definition pointer encoded."""
    if len(item) != 0x48:
        raise ValueError('ItemProp item must be 0x48 bytes')
    out = bytearray(item)
    definition = struct.unpack_from('<I', item)[0]
    struct.pack_into('<I', out, 0, ((definition - 0x3f7650) >> 6) & 0xffffffff)
    return bytes(out)


def creature_state(variant, hp_fraction, flags64, byte231, half312, dead_anim=-1):
    """0x116780: dead records add an animation string handle before packed flags."""
    bits = sum(1 << out for out, mask in enumerate((0x1000000, 0x100000000,
                                                     0x400000, 0x800000,
                                                     0x2000000000000)) if flags64 & mask)
    bits |= 0x20 if byte231 & 1 else 0
    bits |= 0x40 if half312 else 0
    out = bytearray(struct.pack('<If', variant, hp_fraction))
    if hp_fraction <= 0:
        out += struct.pack('<i', dead_anim)
    out += struct.pack('<I', bits)
    if half312:
        out += struct.pack('<i', half312)
    return bytes(out)


def prop_suffix(handles, mask, quaternion, position):
    """0x158d8c: string handles, compact mask and quantized pose."""
    out = bytearray(struct.pack('<III', *handles))
    if mask and mask & (mask - 1) == 0:
        out.append(mask.bit_length() - 1)
    else:
        out += struct.pack('<iQb', -1, mask, 0)
    out += struct.pack('<bbbh', *quaternion)
    out += struct.pack('<hhh', *position)
    return bytes(out)


def directory_slot(names, name):
    """0x217858-0x2178c8: first empty or exact match; overflow aliases slot 10."""
    if len(names) != LEVEL_SLOTS + 1:
        raise ValueError('ten visible entries and one extra gap are required')
    for index in range(LEVEL_SLOTS):
        if not names[index] or names[index] == name:
            return index
    return LEVEL_SLOTS


def directory_lookup(names, name):
    """0x2182fc-0x218340: readers inspect at most ten contiguous entries."""
    for index, saved in enumerate(names[:LEVEL_SLOTS]):
        if not saved:
            break
        if saved == name:
            return index
    return None


def pack_level_body(world, decals, explored, reserved_size, initial=None):
    """0x218600: two 8-byte length frames followed by fixed-size automap."""
    if len(explored) != AUTOMAP_SIZE:
        raise ValueError('explored map must be 0x16c8 bytes')
    if len(world) + len(decals) + AUTOMAP_SIZE + 16 > reserved_size:
        raise ValueError('level body exceeds its reserved size')
    out = bytearray(reserved_size) if initial is None else bytearray(initial)
    if len(out) != reserved_size:
        raise ValueError('initial level body size differs from reservation')
    struct.pack_into('<I', out, 0, len(world))
    out[8:8 + len(world)] = world
    decal_at = 8 + len(world)
    struct.pack_into('<I', out, decal_at, len(decals))
    out[decal_at + 8:decal_at + 8 + len(decals)] = decals
    map_at = decal_at + 8 + len(decals)
    out[map_at:map_at + AUTOMAP_SIZE] = explored
    return bytes(out)


def unpack_level_body(body):
    """Bounds-check the two lengths before returning the three saved sections."""
    if len(body) < 16 + AUTOMAP_SIZE:
        raise ValueError('short level body')
    world_size = struct.unpack_from('<I', body, 0)[0]
    decal_at = 8 + world_size
    if decal_at + 8 > len(body):
        raise ValueError('world section exceeds level body')
    decal_size = struct.unpack_from('<I', body, decal_at)[0]
    map_at = decal_at + 8 + decal_size
    if map_at + AUTOMAP_SIZE > len(body):
        raise ValueError('decal or automap section exceeds level body')
    return (bytes(body[8:decal_at]),
            bytes(body[decal_at + 8:map_at]),
            bytes(body[map_at:map_at + AUTOMAP_SIZE]))


def reload_events(saved, level_objects_present=True, skip_scripts=False):
    """0x217978 call order. A saved body replaces most placed objects."""
    events = ['script_set_current', 'preStart']
    if skip_scripts:
        events.remove('preStart')
    if saved:
        events += ['automap_unpack', 'saved_objects', 'decal_load']
    if level_objects_present:
        events.append('level_objects_filtered' if saved else 'level_objects_all')
    if not skip_scripts:
        events.append('start')
    return events
