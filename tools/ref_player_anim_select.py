"""Player base clip selection for SLUS-20973 v2.00.

Addresses and limits: docs/spec/player-animation-selection.md. This models the
four direct stores of player_resetIdleAnim, not the entire Player_move routine.
"""

G_PLAYERS = 0x4D8AF0
RECORD_SIZE = 0x4C30
ROW_STRIDE = 0x68
BASE_SLOTS = (0x44, 0x4C, 0x54, 0x5C)
BASE_FLAGS = 0x1205


def resource_offset(weapon_class, slot):
    """Offset of a resolved clip pointer in the player's class definition."""
    if not 0 <= weapon_class <= 7 or slot not in BASE_SLOTS:
        raise ValueError((weapon_class, slot))
    return weapon_class * ROW_STRIDE + slot


def base_tracks(weapon_class, resource_word):
    """Four (clip, weight, life, flags) rows made by player_resetIdleAnim.

    resource_word(offset) reads an already resolved pointer; resource loading is
    outside this model. Time, rates, decoder slots and stale cells are unchanged.
    """
    clips = tuple(resource_word(resource_offset(weapon_class, k)) for k in BASE_SLOTS)
    return tuple((clip, 0x3F800000 if i == 0 else 0,
                  0x3F800000 if i == 0 else 0, BASE_FLAGS)
                 for i, clip in enumerate(clips))
