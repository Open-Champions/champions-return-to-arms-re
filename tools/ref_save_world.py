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
    events = ['script_set_current', 'player_start_rank', 'preStart']
    if skip_scripts:
        events.remove('preStart')
    if saved:
        events += ['automap_unpack', 'saved_objects', 'decal_load']
    if level_objects_present:
        events.append('level_objects_filtered' if saved else 'level_objects_all')
    if not skip_scripts:
        events.append('start')
    return events
