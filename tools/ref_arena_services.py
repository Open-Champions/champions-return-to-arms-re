"""Bounded arena player and gold-service properties for US v2.00.

Player_move 0x1b4020 is invoked by neutral Player_run 0x1a5030. In a dry,
no-water fixture it makes no shared draw. Gold_run 0x157b58 decrements its
+0x4c countdown and can clear it when the coin clip has ended. These are
subcontracts, not a model of input, prop physics, or the full object pass.
"""


def neutral_player_seed(seed, ticks):
    """No water or attack in this fixture: no shared draw in 0x1b4020."""
    if ticks < 0:
        raise ValueError('ticks must be nonnegative')
    return seed & 0xFFFFFFFF


def gold_countdown(countdown, ended):
    """Gold_run 0x157b58: signed byte +0x4c after one run tick."""
    countdown &= 0xFF
    if countdown == 0:
        return 0
    if ended:
        return 0
    return (countdown - 1) & 0xFF


def model_hull(blob, mesh):
    """Disc .vif hull entry read by model_getHullPoints 0x179320."""
    if not 0 <= mesh < 64 or len(blob) < 0x28:
        raise ValueError('invalid model or mesh')
    offset = blob[0x25] * 16 + mesh * 24
    if not blob[0x25] or offset + 24 > len(blob):
        raise ValueError('model has no complete hull')
    return offset, blob[offset:offset + 24]
