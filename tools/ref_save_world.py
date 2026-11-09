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


# ---- Round 3 additions (2026-11-09): load effects and travel persistence ----

CREATURE_FLAG_BITS = (0x1000000, 0x100000000, 0x400000, 0x800000, 0x2000000000000)
F32 = struct.Struct('<f')


def f32(value):
    """Round a Python float to IEEE single precision."""
    return F32.unpack(F32.pack(value))[0]


def creature_load(record, obj, clip_names, orc):
    """0x116920 on a synthetic object.  obj holds max_hp, a8, b231, h312, flags,
    s310, s11a, s28 and s232; clip_names lists the clip-table names from index 1;
    record['anim_name'] is the string the dead-animation handle resolves to (None
    for handle -1).  Returns (size, new obj fields, ordered effect list)."""
    out = dict(obj)
    events = ['variant']
    out['variant'] = record['variant']
    out['hp'] = f32(f32(obj['max_hp']) * f32(record['hp_fraction']))
    size = 12
    if out['hp'] <= 0:
        size += 4
        out['s232'] = 20
        out['flags'] |= 0x2009
        events.append('stop_running')
        name = record.get('anim_name')
        if name is not None and name in clip_names:
            index = clip_names.index(name) + 1
            events += ['anim_clear', ('anim_push', index, 4), 'anim_end', ('death_pose', 1)]
            out['s11a'] |= 0x80
        if orc:
            out['s28'] = 0x46
    bits = record['bits']
    for bit, mask in enumerate(CREATURE_FLAG_BITS):
        if bits & (1 << bit):
            out['a8'] |= mask
    out['b231'] = (out['b231'] & 0xfe) | (1 if bits & 0x20 else 0)
    if bits & 0x40:
        size += 4
        if obj['h312'] != -1 and out['flags'] & 0x20 and not out['flags'] & 0x40:
            out['s310'] &= ~0xff
            out['h312'] = record['word312']
            out['w234'] = 0
            events.append('handle_clear')
    return size, out, events


def creature_record(variant, hp_fraction, bits, dead_handle=-1, word312=None):
    """Bytes accepted by 0x116920: the writer layout of creature_state()."""
    out = bytearray(struct.pack('<If', variant, hp_fraction))
    if f32(hp_fraction) <= 0:
        out += struct.pack('<i', dead_handle)
    out += struct.pack('<I', bits)
    if bits & 0x40:
        out += struct.pack('<i', word312)
    return bytes(out)


LIGHT_GRID_AT = 0x5d34d8      # g_lightGrid, symbols/objects.tsv
LIGHT_OVERFLOW = 0x5db368     # g_lightOverflowList
LIGHT_GRID_SIDE = 90


def light_grid_cell(x, y):
    """light_link2 0x148bc8: light-grid cell for integral x/y, or the overflow list."""
    ix, iy = (int(x) + 0x2d00) >> 8, (int(y) + 0x2d00) >> 8
    if 0 <= ix < LIGHT_GRID_SIDE and 0 <= iy < LIGHT_GRID_SIDE:
        return LIGHT_GRID_AT + 4 * (iy * LIGHT_GRID_SIDE + ix)
    return LIGHT_OVERFLOW


def save_game_path(living, act, menu_running, act_found, is_row0, stored, quiet):
    """0x218128: (message, build).  message is None, 'CheckPoint' or 'level'."""
    if not living:
        return None, False
    if act == -1 or menu_running:
        return None, True
    if not act_found:
        return 'CheckPoint', False
    if is_row0 and not stored:
        return None, True
    return ('level' if quiet else 'CheckPoint'), True


def clear_keep_first(directory, row0_size):
    """0x21f144 with argument 0: only the first key survives, re-sized to act 0
    row 0's size; its first row0_size body bytes stay at +0x16118."""
    if not directory or not directory[0][0]:
        return [('', row0_size)]
    return [(directory[0][0], row0_size)]
