"""Selective original-code contract for the valor WarBoar family.

This models class writes and service calls, not Creature_ctor, a complete tick,
resource loading, or a playable fight. Addresses are US v2.00 only.
"""

from ee_emu import float_to_raw, fp_mul

BOAR_CTOR = 0x2BA03C
BOAR_RUN = 0x2BA3A0
BOAR_SET_STATE = 0x2BAC60
BOAR_DEF = 0x502F80
BOAR_VTABLE = 0x517CF0
GOLD_ON_TOUCH = 0x157A9C
GOLD_RUN = 0x157B58


def ctor_fields(small):
    """Final class-owned fields after the base constructor has returned."""
    return {
        (0x48, 4): BOAR_VTABLE, (0x28, 1): 40,
        (0xB8, 4): 0, (0xB0, 4): 0x3F800000,
        (0x1C, 4): 0x41F00000, (0x232, 2): 0,
        (0xEC, 4): 0, (0xB4, 1): 3,
        (0xA8, 8): 0x200040000, (0x5C, 4): 0xBE4CCCCC,
        (0xE0, 4): 0xC1200000 if small else 0xC1700000,
        (0xDC, 4): 0x3F199999 if small else 0x3F400000,
        (0x3D0, 1): int(small), (0xE8, 4): 0, (0x220, 8): 0,
    }


def ctor_services():
    """Ordered direct class call targets, including the base and seven anim events."""
    return ([0x109D68, 0x159C20, 0x179550, 0x1707B0, 0x170838,
             0x14F2B8] + [0x118378] * 7 + [0x10A230])


def balance_factors(percentages):
    """The EE multiplies each signed percentage by its single precision 0.01."""
    return tuple(fp_mul(float_to_raw(float(p)), 0x3C23D70A) for p in percentages)


def tick_services(state, hit_event=False):
    """A bounded active tick with no target and scripted animation event bits."""
    calls = [0x110D30, 0x112948, 0x10C0F0, 0x1162B0,
             0x115EB8, 0x10DED0]
    if state == 0:
        calls += [0x10E658, 0x10EED8]
    elif state == 3:
        calls += [BOAR_SET_STATE]
    elif state == 6:
        calls += [0x113C48]
        if hit_event:
            calls += [0x119B58]
        calls += [BOAR_SET_STATE]
    elif state == 20:
        calls += [0x1108A0]
    else:
        raise ValueError(state)
    return calls


def gold_touch_services(player_flags, countdown, amount):
    """Gold_onTouch's dispatch gate and ordered external calls."""
    if player_flags & 0x20000 or countdown or not player_flags & 0x40 or not amount:
        return []
    return [0x17365C, 0x214230, 0x1DC268, 0x14F200]


def gold_countdown(countdown):
    """The bounded spawn-animation countdown before pickup can succeed."""
    if countdown <= 0:
        raise ValueError(countdown)
    return countdown - 1
