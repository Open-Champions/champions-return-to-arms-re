"""Additive physical-use model; evidence: docs/exits-r3-physical.md.

All positions are raw binary32 values using ref_core's selected EE FPU model.
Existing exit and object reference APIs are unchanged.
"""
import ref_core as F


def physical_choice(world, position, health, vehicle=0, has_player=True):
    """Return (ordered query addresses, chosen address), for supplied live state."""
    if vehicle or not F.lt(0, health) or not has_player:
        return (), None
    x, y, z = position
    lo = (F.sub(x, F.f32(48)), F.sub(y, F.f32(48)), z)
    hi = (F.add(x, F.f32(48)), F.add(y, F.f32(48)), F.add(z, F.f32(60)))
    objects = world.collect_in_box(lo, hi, 256)
    chosen, distance = None, F.f32(10000000)
    for obj in objects:
        if not obj.flags & 0x100000:
            continue
        dx, dy, dz = (F.sub(a, b) for a, b in zip(obj.pos, position))
        square = F.add(F.add(F.mul(dx, dx), F.mul(dy, dy)), F.mul(dz, dz))
        if F.lt(square, distance):
            chosen, distance = obj.addr, square
    return tuple(obj.addr for obj in objects), chosen


def dispatch(result, first_character, pressed, use_mask, display):
    """The real nonempty-prompt guard precedes simulation-only pressed edges."""
    if not first_character or display:
        return False
    return bool((result == 1 and pressed & use_mask) or
                (result == 2 and pressed & 0x10))
