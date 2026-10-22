"""Bounded US v2.00 campaign contracts; no saved character or live fight."""

# player_initNewCharacter 0x1b1d70, record +0x54 -> +0x50.
MODEL_CLASS = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)

# player_giveStartingItems 0x1acc78 with all five debug switches cleared.
# Parser, inventory, and equip are stubbed: these are grant requests, not
# equipped item records. The two-model classes happen to share these routes.
MODEL_WEAPONS = (
    ("axe",), ("axe",), ("shortsword", "shortbow"),
    ("shortsword", "shortbow"), ("mace",), ("mace",),
    ("quarterstaff",), ("quarterstaff",), ("shortsword",),
    ("shortsword",), ("throwingaxe", "axe"), ("club",),
)
MODEL_CALL_COUNTS = tuple(
    (10, 13, 5) if model in (2, 3) else
    (8, 11, 5) if model == 10 else (7, 10, 4)
    for model in range(12)
)

# Minotaur_setState 0x28a16c death state 0x14 calls Creature_dropLoot
# 0x10f2c8. The class is present in VALOR.GOB; the parameters are unrelated
# to WarBoar's zero-gold-chance death call.
MINOTAUR_LOOT_BITS = (0x42100000, 0x40000000, 0x3fcccccc,
                      0x3f199999, 0x3fb33333, 0x3e800000)

# WarBoar ctor 0x2ba03c installs the first two event slots on attack clip
# entry 4 through Creature_setDefEntryParams 0x118378. At one step per frame,
# anim_advance 0x16d748 reports these masks on the following frames.
ATTACK_EVENTS = ((18, 1), (42, 2))
