"""Bounded SLUS-20973 v2.00 contracts for blood1 hostile classes.

Addresses, short identifiers and authored model values only. These describe
isolated original functions; they do not supply resource handles or live AI.
"""

from ee_emu import float_to_raw, fp_mul

CLASSES = {
    "Kobold": (118, 0x3D0, 0x27F0C0, 0x500AF0, 0x515EF0, 0),
    "Koboldtough": (8, 0x3D0, 0x27F0C0, 0x500AF0, 0x515EF0, 1),
    "koboldshaman": (5, 0x3D0, 0x27F0C0, 0x500AF0, 0x515EF0, 2),
    "WarWraith": (9, 0x468, 0x2C07A8, 0x5034F0, 0x517F80, None),
}
RUN = {"Kobold": 0x27F52C, "WarWraith": 0x2C0C2C}
SET_STATE = {"Kobold": 0x27FF6C, "WarWraith": 0x2C1648}
BALANCE = {
    "Kobold": (69, 100, 60, 69, 80),
    "Koboldtough": (250, 80, 100, 179, 189),
    "koboldshaman": (179, 179, 120, 139, 189),
    "WarWraith": (200, 200, 160, 100, 200),
}
KOBOLD_EVENTS = (3, 4, 5, 6, 7, 21, 17, 8, 9, 10, 11)
WRAITH_EVENTS = (3, 4, 5, 7)
# Synthetic fresh-object seed probes. A loaded level consumes other draws first.
WRAITH_WEAPON_PROBE = {20973: 15, 7: 13}
DEATH_FLOATS = {
    "Kobold": (0x42100000, 0x40000000, 0x3FCCCCCC,
               0x3E999999, 0x3FB33333, 0x3DF5C28F),
    "WarWraith": tuple(map(float_to_raw, (36., 2., 2.8, 0., 3., .25))),
}
TICK_PREFIX = (0x110D30, 0x112948, 0x10C0F0)
KOBOLD_ACTIVE = (0x1162B0, 0x115EB8, 0x10DED0, 0x10E2C0)
WRAITH_ACTIVE = (0x11B2A8, 0x1162B0, 0x10DED0, 0x115EB8, 0x1187E0)
TARGETED_ATTACK = {
    "Kobold": (KOBOLD_ACTIVE + (0x119E38, 0x119938, 0x1187E0,
                                 SET_STATE["Kobold"])),
    "WarWraith": (WRAITH_ACTIVE + (0x11B180, 0x1196E8, 0x1187E0,
                                   0x14F028, SET_STATE["WarWraith"])),
}
KOBOLD_HIT_FLAGS = {"Kobold": 8, "Koboldtough": 0x440008,
                    "koboldshaman": 8}


def balance_factors(name):
    """Original lookup's signed percentage multiplication, not final stats."""
    return tuple(fp_mul(float_to_raw(float(p)), 0x3C23D70A)
                 for p in BALANCE[name])


def class_fields(name):
    """Stable class-owned final fields under a zero-result service harness."""
    _count, _size, _ctor, _definition, vtable, variant = CLASSES[name]
    if variant is None:
        return {(0x48, 4): vtable, (0x3C8, 1): 100,
                (0xB4, 1): 0x10, (0x1C, 4): float_to_raw(18.),
                (0xB8, 4): float_to_raw(140.), (0x3C0, 4): float_to_raw(600.),
                (0x50, 4): None}  # points to this+0x3d0
    radius = (12., 20., 18.)[variant]
    return {(0x48, 4): vtable, (0x3CC, 1): variant,
            (0xE8, 4): variant, (0x1C, 4): float_to_raw(radius),
            (0xB4, 1): 9, (0x28, 1): 0x1E}


def tick_calls(name, state, _event):
    """Synthetic active/no-target tick; event bits do not reach a hit here."""
    if name != "WarWraith":
        tail = {0: (0x10E658, 0x10EED8), 3: (SET_STATE["Kobold"],),
                6: (0x119E38, SET_STATE["Kobold"]),
                7: (0x119E38, SET_STATE["Kobold"]),
                20: (0x113C48, 0x1108A0)}[state]
        return TICK_PREFIX + KOBOLD_ACTIVE + tail
    tail = {0: (0x10E658,), 3: (SET_STATE["WarWraith"],),
            6: (SET_STATE["WarWraith"],),
            7: (SET_STATE["WarWraith"],), 20: (0x14F200,)}[state]
    active = WRAITH_ACTIVE if state != 20 else tuple(
        target for target in WRAITH_ACTIVE if target != 0x10DED0)
    return TICK_PREFIX + active + tail


def death_calls(name):
    if name == "WarWraith":
        return (0x10A9C0, 0x11B080, 0x100D54, 0x1A1698,
                0x16CFE0, 0x10BEB8)
    return (0x10A9C0, 0x10F2C8, 0x1509D0, 0x16CFE0, 0x10BEB8)
