"""Reference contracts for bounded offline arena match helpers.

The owner's executable is never embedded here. Each function is compared with original
execution in difftest_arena_match_core.py. Floats are raw single precision patterns.
"""
import ref_core as C

SCALE_STATS = 0x1185D8
EMPTY_WAVE_VISIT = 0x3069E8
NEXT_WAVE = 0x305E9C
PREPARE_WAVE = 0x3063FC
SAVE_WAVE_VISIT = 0x306A28
SHUTDOWN = 0x304FB0
LIVE_COUNT = 0x8E733E
SAVED_COUNT = 0x8E7340
PLAYER_RECORD_BASE = 0x4D8AF0
PLAYER_RECORD_SIZE = 0x4C30
PLAYER_RESPAWN = 0x1BD040


def s16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def scale_stats(fields, factors):
    """Map offsets to the values stored by Creature_scaleStats.

    +0x228/+0x22c and +0xd8 are floats after an integer truncation of
    the product. +0xe4/+0xd0/+0xd2/+0xd4 are signed halfwords, multiplied
    as floats then truncated toward zero.
    """
    hp, armor, damage, attack, speed = factors
    return {
        0xE4: C.to_int(C.mul(C.from_int(s16(fields[0xE4])), armor)) & 0xFFFF,
        0x228: C.from_int(C.to_int(C.mul(fields[0x228], hp))),
        0x22C: C.from_int(C.to_int(C.mul(fields[0x22C], hp))),
        0xD0: C.to_int(C.mul(C.from_int(s16(fields[0xD0])), damage)) & 0xFFFF,
        0xD2: C.to_int(C.mul(C.from_int(s16(fields[0xD2])), damage)) & 0xFFFF,
        0xD4: C.to_int(C.mul(C.from_int(s16(fields[0xD4])), attack)) & 0xFFFF,
        0xD8: C.from_int(C.to_int(C.mul(fields[0xD8], speed))),
    }


def empty_wave_visit(flags, state, count):
    """Return updated live-monster count, or None when this object is skipped."""
    if flags & 0x68 != 0x20 or s16(state) < 0:
        return None
    return (count + 1) & 0xFFFF


def save_wave_visit(flags, state, count):
    """0x306a28: classify an arena creature for the saved pointer array.

    Returns (kind, new count). The array stores object pointers at 4*count before
    increment. A dead or hidden creature is destroyed through virtual slot 1.
    """
    if not flags & 0x20:
        return 'skip', count
    # Bit 0x2 keeps a dying creature in the saved array even when death bit
    # 0x8 is set. The next-wave path encounters 0x612b on a killed wave-1
    # creature when the probe has not advanced its death animation.
    if flags & 0x60 == 0x20 and (not flags & 0x8 or flags & 0x2) and s16(state) >= 0:
        return 'save', (count + 1) & 0xFFFF
    if flags & 0x40 and not flags & 0x08 and s16(state) >= 0:
        return 'skip', count
    return 'destroy', count


def prepare_wave(live_after_walk=0):
    """0x3063fc: reset live count, walk objects, copy the count to saved count."""
    return ((0x19F018, None), (0x14A610, SAVE_WAVE_VISIT)), \
        {LIVE_COUNT: 0, SAVED_COUNT: live_after_walk & 0xFFFF}


def next_wave(increment):
    """0x305e9c: screen effect, preparation, then startWave with the same argument."""
    return ((0x322954, 15), (PREPARE_WAVE, None), (0x305ED4, increment))


def shutdown(found, spawn_ptr, monster_ptr):
    """0x304fb0: lookup gate, two frees, two task removals and five cleared words."""
    calls = [(0x19E5E8, 0x551E48)]
    writes = {}
    if found:
        calls += [(0x150198, spawn_ptr), (0x150198, monster_ptr),
                  (0x19E664, 0x306B78), (0x19E664, 0x307284)]
        writes = {0x503888: 0, 0x50388C: 0, 0x503890: 0,
                  0x41B500: 0, 0x41B4FC: 0}
    return calls, writes


def restore_saved_player_record(saved):
    """Confirm path: copy the complete saved 0x4c30-byte record to its slot."""
    if len(saved) != PLAYER_RECORD_SIZE:
        raise ValueError('saved player record must be one full slot')
    return bytes(saved)


def player_respawn_body(local, network, pvp_a, placement_a, placement_b,
                        old_object, new_object, max_hp, old_object_slot1):
    """Original player_respawn wrapper, with constructor and world services as call-outs.

    Returns (call targets, direct stores, findFreeSpot range/radius or None). The
    constructor fixture must update record +0x43d8 to the new pointer before the
    protection and alive-list calls.
    """
    calls = [0x13E150]
    if local:
        calls.append(0x1EB000)
    calls += [old_object_slot1, 0x14FDB8]  # old-object virtual slot 1, pool_new
    find = None
    if new_object:
        if placement_a != -1:
            calls.append(0x14ACF8)
            find = (placement_b * 12, placement_a * 12)
        calls.append(0x1A1D28)  # Player_ctor
    calls += [0x1B8F28, 0x1E72F8]
    if network:
        calls.append(0x13E150)
        if local:
            calls += [0x207450, 0x203210, 0x207308]
    calls.append(0x203400)
    if network:
        calls.append(0x13E150)
        if local:
            calls.append(0x322954)
    stores = {0x4F84A8: 240, 0x4D8AF0 + 0xAC:
              max_hp if pvp_a else C.mul(max_hp, 0x3F000000),
              0x402797: 1}
    return calls, stores, find
