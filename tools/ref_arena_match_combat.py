"""Bounded combat expectations for recipe-0 enemies and the Orc2 recruit.

These are class-body contracts on an authored player handle and answered base
services.  Creature_filterState is stubbed to return zero, so rooted, stunned
and cooldown state rewrites are unexercised. The hit helper, damage dispatcher,
and Player_takeDamage execute in the difftest. Full Player ticks, animation
resources, and world collision do not. ORC_RUN and ORC_SET are regression pins
from original-body traces on seeds 20973 and 7, not independently derived calls.
"""

SPECS = {
    'goblin': (0x26B27C, 0x26CCFC, 0x510260, 0x500298, 0x3E8, 0x50CDA0),
    'mummy': (0x298D18, 0x29A6F4, 0x516E48, 0x501838, 0x3D0, 0x50CF40),
    'scorpion': (0x2A5068, 0x2A55EC, 0x50FE88, 0x502238, 0, 0),
    'orc2': (0x2A1848, 0x2A323C, 0x50FFD0, 0x501DF8, 0x3D8, 0x50CDA0),
}

HIT_REACH = 0x1196E8
DAMAGE_APPLY = 0x1E8230
PLAYER_TAKE_DAMAGE = 0x1B5330
PLAYER_PROCESS_DAMAGE = 0x1B2CC0
CREATURE_TAKE_DAMAGE = 0x116638
ORC_TAKE_DAMAGE = 0x2A2EAC
FILTER = 0x10A9C0
RAND = 0x1509D0

ORC_HEAD = (0x110D30, 0x112948, 0x10C0F0, 0x11B2A8,
            0x1162B0, 0x115EB8, 0x10DED0)
ORC_RUN = {
    0: (0x10E658, 0x2A323C),
    1: (0x10E658, 0x119F38),
    2: (0x10E658, 0x119F38, 0x2A323C),
    3: (0x2A323C,), 4: (0x2A323C,),
    5: (0x118D40, 0x1195E0),
    6: (0x11BDE0, 0x2A323C), 7: (0x2A323C,),
    0x10: (0x1195F0, 0x119F08), 0x11: (0x2A323C,),
    0x12: (0x2A323C,), 0x13: (0x119608,),
    0x14: (0x166630, 0x1666E0, 0x1108A0),
    0x17: (0x2A323C,),
}

ORC_SET = {
    0: (RAND, RAND, 0x16CFE0),
    1: (0x11A1E0, 0x119618, RAND, 0x16CFE0, 0x1709F8),
    2: (0x11A1E0, RAND, 0x16CFE0, 0x1709F8),
    3: (0x11A1E0, RAND, 0x16CFE0, 0x1709F8),
    4: (RAND, 0x16CFE0, 0x1709F8),
    5: (0x2A4240, RAND, 0x16CFE0),
    6: (0x3C2590, 0x3C2590, 0x3C2590, RAND, 0x16CEB0, RAND),
    7: (RAND, 0x16CEB0),
    0x10: (0x11A1E0, RAND, 0x16CFE0, 0x1709F8),
    0x11: (0x16CFE0,),
    0x12: (RAND, 0x16CEB0),
    0x13: (RAND, 0x16CFE0),
    0x14: (0x11BC90, 0x11BC90, RAND, 0x16CFE0, 0x10F2C8, 0x10BEB8),
    0x17: (RAND, 0x16CFE0, RAND),
}


def orc_neutral_calls(kind, state):
    """Run/set-state call contract for recruit, no target, no animation event."""
    if kind == 'run':
        return ORC_HEAD + ORC_RUN.get(state, ())
    if kind == 'set':
        return (FILTER,) + ORC_SET.get(state, ())
    raise ValueError(kind)


def chase_state(near):
    """Pinned-seed chase choice; distant random recruit branches remain open."""
    if not near:
        return 3
    return 6


def melee_hit(kind, player, creature):
    """Expected original hit-dispatch chain for a player target."""
    return ((HIT_REACH, creature), (DAMAGE_APPLY, player),
            (PLAYER_TAKE_DAMAGE, player))


def scorpion_sting_damage(difficulty):
    """The original sting writes its reduced damage range back to the object."""
    divisor = {2: 4, 3: 8}.get(difficulty, 1)
    return 10 // divisor, 20 // divisor
