"""Reference contracts for recipe-0 Goblin and Mummy in a neutral test world.

These are authored expectations for the plain type-name variant, a live object
without a target, and zero animation events. The difftest runs every state arm
of the original bodies with these inputs; it does not cover the other roles,
attacks, animation events or moving targets. See docs/spec/arena-goblin.md and
arena-mummy.md for that boundary and for the full observed class layout.
"""

GOBLIN = 'goblin'
MUMMY = 'mummy'

SPECS = {
    GOBLIN: dict(index=3, ctor=0x26A624, run=0x26B27C, set_state=0x26CCFC,
                 table=0x510260, definition=0x500298, holder=0x3E8,
                 holder_table=0x50CDA0, size=0x498),
    MUMMY: dict(index=1, ctor=0x298418, run=0x298D18, set_state=0x29A6F4,
                table=0x516E48, definition=0x501838, holder=0x3D0,
                holder_table=0x50CF40, size=0x480),
}

RAND = 0x1509D0
FILTER = 0x10A9C0
SET_G = SPECS[GOBLIN]['set_state']
SET_M = SPECS[MUMMY]['set_state']
START = 0x16CFE0
SWING = 0x16CEB0
PATH = 0x11A1E0
WANDER = 0x119618
ANIM_SYNC = 0x1709F8


def next_draw(seed):
    seed = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    return seed, seed >> 16


def constructor(kind, seed):
    """Expected core fields, calls and own draws with a stubbed Creature_ctor.

    The zeroed pool block gives Goblin one pre-base own draw from zero. The
    base fixture then makes GameObject_ctor's one shared draw and reseeds the
    object's own generator; later class GameObject_rand calls run for real.
    """
    shared, _ = next_draw(seed)
    own = shared
    if kind == GOBLIN:
        own, role_draw = next_draw(own)
        draws = 2
        mask = 2 if role_draw & 2 else 0
        if role_draw & 1:
            own, extra = next_draw(own)
            mask |= 1 << (extra % 3 + 5)
            draws += 1
        # the recruit's hand-one part is selected by another own draw
        own, _ = next_draw(own)
        draws += 1
        fields = {0x1C: 0x41900000, 0x28: 0x28, 0x48: 0x510260,
                  0xB0: 0x3F999999, 0xB8: 0x42700000, 0xE8: mask,
                  0xEC: 100, 0x232: 0, 0x3D4: 0, 0x3D8: 0, 0x488: 0,
                  0x48C: 0, 0x490: 0}
        calls = ([RAND, 0x109D68] + [0x17365C] * 14 + [0x159C20] * 12 +
                 [RAND] * (draws - 1) + [0x11BC18, 0x179550, 0x1707B0,
                 0x170838, 0x14F2B8] + [0x118378] * 5 + [0x10A230])
    else:
        own, mask_draw = next_draw(own)
        own, rare_draw = next_draw(own)
        assert rare_draw >= 6554  # these tested seeds do not take the rare modifier
        fields = {0x1C: 0x41700000, 0x28: 0x1E, 0x48: 0x516E48,
                  0xB0: 0x3F999999, 0xB8: 0, 0xE8: 1 << (mask_draw % 3),
                  0xEC: 100, 0x232: 0, 0x3C8: 0, 0x468: 0,
                  0x46C: 0, 0x470: 0}
        draws = 2
        calls = ([0x109D68] + [0x159C20] * 10 + [RAND, 0x11AFB0, RAND,
                 0x179550, 0x1707B0, SET_M, 0x14F2B8] +
                 [0x118378] * 12 + [0x10A230])
    return tuple(calls), draws, fields, own, shared


_G_SET = {
    0: (START,), 1: (PATH, WANDER, START, ANIM_SYNC),
    2: (PATH, START, ANIM_SYNC), 3: (PATH, 0x3B8534, START, ANIM_SYNC),
    4: (START, ANIM_SYNC), 5: (START,), 6: (SWING,), 7: (SWING,),
    8: (SWING,), 0x10: (PATH, START, ANIM_SYNC),
    0x11: (START,), 0x12: (SWING,), 0x13: (START,),
    0x14: (0x14C880, 0x14A928, 0x11BC90, 0x11BC90,
           0x14C880, START, 0x10F2C8, 0x10BEB8),
    0x17: (START,),
}
_M_SET = {
    0: (START,), 1: (PATH, WANDER, START, ANIM_SYNC),
    3: (PATH, START, ANIM_SYNC), 5: (START, ANIM_SYNC),
    6: (SWING,), 7: (START, SWING), 8: (SWING,),
    0x10: (PATH, START, ANIM_SYNC), 0x12: (SWING,),
    0x13: (START,), 0x14: (0x10F2C8, START, 0x11B080, 0x10BEB8),
    0x17: (START, SWING), 0x18: (PATH, START, ANIM_SYNC),
}
_G_DRAWS = {0: 1, 0x12: 1, 0x17: 1}
_M_DRAWS = {0: 1, 5: 1, 6: 1, 7: 2, 8: 1, 0x14: 1}


def set_state(kind, state, seed):
    """Calls, own draws, state and key direct fields in the neutral fixture."""
    first = next_draw(seed)[1]
    stores = {}
    if kind == GOBLIN:
        suffix = _G_SET.get(state, ())
        if state == 0:
            stores[0xF4] = 10 + 120 + first % 60
        elif state == 0x11:
            stores[0xF4] = 10 + 120
            stores[0xA8] = 0x200
        elif state == 0x17:
            stores[0xF4] = 10 + 240 + first % 240
        return (FILTER,) + suffix, _G_DRAWS.get(state, 0), state, stores
    suffix = _M_SET.get(state, ())
    if state == 0:
        stores[0xF4] = 10 + first % 120
    elif state == 5:
        stores[0xF4] = 10 + 60 + first % 120
    elif state == 7:
        second = next_draw(next_draw(seed)[0])[1]
        stores[0xF4] = 240 + (second * 120 // 65536)
    elif state == 0x17:
        stores[0x470] = 10 + 600
    return (FILTER, 0x3CF87C, 0x11A6D0) + suffix, _M_DRAWS.get(state, 0), state, stores


RUN_HEAD = (0x110D30, 0x112948, 0x10C0F0, 0x11B2A8,
            0x1162B0, 0x115EB8, 0x10DED0)
_G_RUN = {
    0: (0x10E658, 0x10EED8), 1: (0x10E658, 0x119F38),
    2: (0x10E658, 0x119F38, SET_G),
    3: (SET_G,), 4: (SET_G,), 5: (SET_G,), 6: (SET_G,),
    7: (SET_G,), 8: (SET_G,),
    0x10: (0x1195F0, 0x119F08), 0x11: (SET_G,),
    0x12: (0x170D88, SET_G), 0x13: (0x119608,),
    0x14: (0x1108A0,), 0x17: (SET_G,),
}
_M_RUN = {
    0: (0x10E658, 0x10EED8, SET_M), 1: (0x10E658, 0x119F38),
    3: (SET_M,), 5: (0x118D40, 0x1195E0),
    6: (0x113C48, SET_M),
    7: (0x113C48, 0x3CF87C, 0x11A6D0, 0x3CF87C, 0x11A6D0, SET_M),
    8: (0x113C48, SET_M),
    0x10: (0x1195F0, 0x119F08), 0x12: (0x113C48, SET_M),
    0x13: (0x119608,), 0x14: (0x113C48, 0x1108A0),
    0x17: (SET_M,), 0x18: (SET_M,),
}


def run(kind, state):
    """Calls in one active tick, no target, no events, external bodies stubbed."""
    return RUN_HEAD + (_G_RUN if kind == GOBLIN else _M_RUN).get(state, ())
