"""Authored bounded Minotaur state/attack contracts, SLUS_209.73 US v2.00.

These describe class-local call-outs, not animation, collision or a whole fight.
Resource indexes here are zero-based; the constructor's event API is one-based.
"""

STATE = 0x28A16C
TICK = 0x2894B8
CTOR = 0x288FDC
DEF = 0x501200
VTABLE = 0x5165F0
CHANGE = 0x16CFE0
BLEND = 0x16CEB0
TENTH = 0x3DCCCCCC

ATTACK_CLIPS = {6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 3}
ATTACK_FLAGS = {6: 0x440001, 7: 0x440008, 8: 0x440008,
                9: 8, 10: 8, 11: 8}
EVENTS = (
    (5, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
    (6, (1, 1, 0, 0), (0x3E4CCCCC, 0x3F199999, 0, 0)),
    (7, (1, 0, 0, 0), (0x3ECCCCCC, 0, 0, 0)),
    (8, (1, 4, 0, 0), (0x3E4CCCCC, 0x3EB851EB, 0, 0)),
    (9, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
    (13, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
    (3, (1, 0, 0, 0), (0x3F199999, 0, 0, 0)),
    (4, (1, 0, 0, 0), (0x3F199999, 0, 0, 0)),
)


def state_animation(state, health_band=2, first_charge=True, draw=0):
    """Expected animation calls as (callee, resource index, flags, float words)."""
    if state in (0, 19):
        return [(CHANGE, 14, 3, (TENTH if state == 0 else 0x3E999999,))]
    if state in (1, 3, 5, 16, 23):
        index = {1: 19, 3: 19 if health_band == 1 else 16,
                 5: 15, 16: 16, 23: 9}[state]
        flags = 3 if state in (5, 23) else 0x803
        return [(CHANGE, index, flags, (TENTH,))]
    if state in ATTACK_CLIPS:
        flags = 0x4008 if state in (9, 10) else 0x4808 if state == 11 else 0x808
        return [(BLEND, ATTACK_CLIPS[state], flags, (TENTH, TENTH))]
    if state == 12:
        result = [(CHANGE, 16, 0x80B, (TENTH,))]
        if first_charge:
            result.append((BLEND, 18, 8, (TENTH, TENTH)))
        return result
    if state == 18:
        return [(BLEND, 13, 0x810, (TENTH, TENTH))]
    if state == 20:
        return [(CHANGE, 10 + (draw & 1), 0x806, (0x3E4CCCCC,))]
    return []


def stored_state(requested):
    return requested if requested in (0, 1, 3, 5, 6, 7, 8, 9, 10, 11, 12,
                                      16, 18, 19, 20, 23) else 0
