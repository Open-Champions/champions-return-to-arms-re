"""Bounded v2.00 mission-2 hostile contracts for original-function checks.

Values here are authored addresses, identifiers and expected results of isolated
calls. Resource handles, live level state and downstream damage are not modelled.
"""

from ee_emu import float_to_raw, fp_mul

# Authored placements, factory allocation, constructor, class definition,
# vtable and Clockwork sub-kind. Order follows placement count.
CLASSES = {
    "clockworkcutter": (66, 0x500, 0x24E124, 0x4FF260, 0x514300, 0),
    "clockworkhammer": (66, 0x500, 0x24E124, 0x4FF260, 0x514300, 1),
    "Droid": (30, 0x3D0, 0x27B840, 0x500A88, 0x515DA8, None),
    "IronGuardian": (1, 0x3E8, 0x27A00C, 0x500960, 0x515C60, None),
}
RUN = {"clockworkcutter": 0x24E758, "clockworkhammer": 0x24E758,
       "Droid": 0x27BA78, "IronGuardian": 0x27A390}
SET_STATE = {"clockworkcutter": 0x24F90C, "clockworkhammer": 0x24F90C,
             "Droid": 0x27C0A0, "IronGuardian": 0x27B550}
BALANCE = {
    "clockworkcutter": (100, 200, 110, 100, 129),
    "clockworkhammer": (120, 250, 139, 100, 150),
    "Droid": (60, 100, 350, 100, 100),
    "IronGuardian": (1800, 550, 400, 500, 1800),
}
EVENTS = {
    "clockworkcutter": (3, 4, 5, 12, 13, 14, 15, 22, 6, 7, 8, 16, 17, 18),
    "clockworkhammer": (3, 4, 5, 12, 13, 14, 15, 22, 6, 7, 8, 16, 17, 18),
    "Droid": (3, 9, 10),
    "IronGuardian": (3, 4, 5, 6, 13, 7, 8),
}
DROP_FLOATS = (0x42100000, 0x40000000, 0x3FCCCCCC,
               0x3F199999, 0x3FB33333, 0x3E800000)


def balance_factors(name):
    """Factors returned by balance_lookup, before Creature_setStats scaling."""
    return tuple(fp_mul(float_to_raw(float(p)), 0x3C23D70A)
                 for p in BALANCE[name])


def class_fields(name):
    """Stable class-owned fields after a zero-result constructor harness."""
    _count, _size, _ctor, _definition, vtable, variant = CLASSES[name]
    fields = {(0x48, 4): vtable, (0xB4, 1): 4}
    if variant is not None:
        fields.update({(0x3C8, 1): variant,
                       (0x1C, 4): float_to_raw(22. if variant == 0 else 28.),
                       (0xB0, 4): 0x3F199999,
                       (0x50, 4): None})  # this + 0x3d0
        if variant == 0:
            fields[(0xDC, 4)] = float_to_raw(0.9)
    elif name == "Droid":
        fields.update({(0x1C, 4): float_to_raw(15.),
                       (0xB0, 4): float_to_raw(1.4),
                       (0x3CC, 4): 3600})
    else:
        fields.update({(0x1C, 4): float_to_raw(35.),
                       (0xB0, 4): 0x3E999999,
                       (0x3C0, 4): float_to_raw(3000.),
                       (0x3C4, 4): 3000,
                       (0x3D4, 4): 0})
    return fields


TICK_PREFIX = (0x110D30, 0x112948, 0x10C0F0)
CLOCKWORK_ACTIVE = (0x118058, 0x1162B0, 0x115EB8, 0x10DED0)
OTHER_ACTIVE = (0x1162B0, 0x115EB8, 0x10DED0)


def tick_calls(name, state):
    """Synthetic active/no-target tick with lower AI and effect calls stubbed."""
    if name.startswith("clockwork"):
        tail = {0: (0x10E658, 0x10EED8), 3: (SET_STATE[name],),
                6: (0x1187E0, 0x119938, SET_STATE[name]),
                20: (0x113C48, 0x1108A0)}[state]
        effects = (0x18F3D0,)
        if name == "clockworkhammer":
            effects += (0x1509D0, 0x1509D0)
        return TICK_PREFIX + CLOCKWORK_ACTIVE + tail + effects
    head = (0x3C2738, 0x110D30, 0x3C2738, 0x112948, 0x10C0F0)
    tail = {
        "Droid": {0: (0x10E658, 0x10EED8), 3: (SET_STATE[name],),
                  6: (SET_STATE[name],), 20: ()},
        "IronGuardian": {0: (0x10E658, 0x10EED8), 3: (SET_STATE[name],),
                         6: (0x119B58, SET_STATE[name]), 20: (0x1108A0,)},
    }[name][state]
    return head + OTHER_ACTIVE + tail


def death_calls(name):
    if name.startswith("clockwork"):
        return ((0x10A9C0, 0x1509D0) + (0x24FD8C,) * 8 +
                (0x10F2C8, 0x1509D0, 0x16CFE0, 0x10BEB8))
    if name == "Droid":
        return (0x10A9C0, 0x1509D0, 0x16CFE0, 0x10BEB8)
    return (0x10A9C0, 0x10F2C8, 0x16CFE0, 0x10BEB8)


TARGETED_HIT = {
    "clockworkcutter": (0x119938, 0x40008),
    "clockworkhammer": (0x119938, 1),
    "IronGuardian": (0x119B58, 8),
}

EXPLOSION_CALLS = (
    0x3C2738, 0x110D30, 0x3C2738, 0x112948, 0x10C0F0,
    0x1162B0, 0x115EB8, 0x10DED0, 0x1EF270, 0x213EA0,
    0x1F3D00, 0x17365C, 0x214230, 0x161270, 0x1509D0,
    0x19F110, 0x14FDB8, 0x201BD8, 0x14F200,
    *((0x14FDB8, 0x155A0C) * 10),
)
