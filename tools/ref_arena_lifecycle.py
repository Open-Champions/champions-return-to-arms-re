"""Bounded recipe-0 arena corpse-save and reuse reference for US v2.00.

This composes the grid callback rules at 0x3069e8/0x306a28 with the saved
branch of arena_startWave at 0x305ed4. It models a transition, not a frame
scheduler or a natural death. See docs/spec/arena-match-probe.md, round 8.
"""

from ref_arena_modes import lcg, ring_step, s16


def empty_count(objects):
    """0x3069e8: count objects still eligible to block the next wave."""
    return sum(1 for _ptr, flags, state in objects
               if flags & 0x68 == 0x20 and s16(state) >= 0) & 0xFFFF


def save_actions(objects):
    """0x306a28: return (pointer, action) in world-walk order."""
    actions = []
    for ptr, flags, state in objects:
        if not flags & 0x20:
            action = 'skip'
        elif flags & 0x60 == 0x20 and (not flags & 0x8 or flags & 0x2) and s16(state) >= 0:
            action = 'save'
        elif flags & 0x40 and not flags & 0x8 and s16(state) >= 0:
            action = 'skip'
        else:
            action = 'destroy'
        actions.append((ptr, action))
    return actions


def reuse_seed(seed, player_spot_draws, creature_spot_draws):
    """0x305ed4 saved path: two modelled free-spot calls plus four fixed draws.

    Fixed draws: player GameObject_ctor 0x14cd7c, ring step 0x3065ec,
    reused creature at arena_spawnMonster 0x306924, and startWave 0x3061ac.
    Each free-spot draw is checked separately by ref_arena_creature_chain.
    """
    for _ in range(player_spot_draws + creature_spot_draws + 4):
        seed, _draw = lcg(seed)
    return seed


def reuse_ring(seed, count):
    """0x3065b0: one ring draw for the saved-count group."""
    return ring_step(seed, count)
